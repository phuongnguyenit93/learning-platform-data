# MessageSource và Locale khi hiển thị lỗi trong Spring Framework

## 1. Tại sao phải tách quy tắc validation khỏi ngôn ngữ?

Một REST API Spring có thể phục vụ người dùng Việt Nam và quốc tế. Với cùng một request sai:

```json
{"name":" ","age":17,"email":"lan@example.org"}
```

quy tắc nghiệp vụ vẫn như nhau: `name` không được để trống, `age` phải từ 18. Nhưng thông báo có thể là:

| Locale | Trường `name` | Trường `age` |
| --- | --- | --- |
| `vi` | Tên không được bỏ trống | Tuổi phải từ 18 |
| `en` | Name must not be blank | Age must be at least 18 |

Để triển khai đúng, cần phân biệt:

1. **Constraint** như `@NotBlank`, `@Min`: quyết định dữ liệu đúng/sai; không phụ thuộc ngôn ngữ.
2. **Error code** như `NotBlank.accountRequest.name`, `Min.accountRequest.age`: mô tả loại lỗi để tra message.
3. **`Locale`** như `vi`, `en`, `vi-VN`: định danh ngôn ngữ/vùng cần hiển thị.
4. **`MessageSource`**: tra một message code và các arguments theo locale.
5. **MessageInterpolator của Jakarta Validation**: nội suy message template của constraint, ví dụ `{account.name.required}` hoặc `{min}`/`{max}`.

Bài này tập trung vào **Spring Framework – validation/data binding**, Java 17+, Spring Boot 3.x và Servlet Spring MVC. Các ví dụ runnable dùng Spring Boot 3.3.6 (Spring Framework 6.1.x); Spring WebFlux có đường exception/binding khác.

### Kết quả cần đạt

- Chọn đúng locale từ `Accept-Language`.
- Định nghĩa bản dịch trong `messages.properties` và `messages_vi.properties`.
- Dùng `MessageSource.getMessage(FieldError, locale)` thay vì chỉ in default message.
- Trả HTTP 400 có mã lỗi ổn định, field path và thông báo theo ngôn ngữ.
- Phân biệt lỗi conversion/JSON malformed với constraint validation.
- Hiểu lúc nào `ValidationMessages.properties` được sử dụng.
- Test được tiếng Việt, tiếng Anh và fallback với `MockMvc`.

## 2. Cơ chế hoạt động trong Spring MVC

```text
HTTP POST /api/accounts
Accept-Language: vi
Content-Type: application/json
             |
             v
DispatcherServlet / LocaleResolver
             | chọn Locale vi
             v
HttpMessageConverter / Jackson
             | JSON -> AccountRequest
             v
@Valid / Jakarta Validator
             | @NotBlank(name), @Min(age)
             v
BindingResult / FieldError / ObjectError
             | codes: NotBlank.accountRequest.name,
             |        NotBlank.name, NotBlank...
             v
@RestControllerAdvice
             | MessageSource.getMessage(error, locale)
             v
messages_vi.properties
             | Tên không được bỏ trống
             v
HTTP 400 JSON: field + code + localized message
```

**Binding** chuyển request thành Java object; **validation** quyết định giá trị có đạt ràng buộc; **message resolution** chọn thông báo hiển thị. Cả ba là các bước riêng. Dịch một message không làm thay đổi HTTP status, giá trị của constraint hay nghiệp vụ.

Với `@ModelAttribute` form/query, Spring `WebDataBinder` có thể tạo `BindingResult` chứa cả lỗi conversion (ví dụ `age=abc`) và lỗi Bean Validation. Với `@RequestBody` JSON, message converter phải parse được JSON trước; khi JSON không parse được, thường là `HttpMessageNotReadableException` chứ không phải một `FieldError` sinh từ `@Min`.

## 3. MessageSource là gì?

`org.springframework.context.MessageSource` là contract tra thông báo. Một số method quan trọng:

```java
// Có fallback nếu code không tồn tại:
String a = messages.getMessage(
        "api.validation.failed", null, "Invalid input", locale);

// Không có fallback: có thể ném NoSuchMessageException:
String b = messages.getMessage(
        "api.validation.failed", null, locale);

// Tra thông báo từ toàn bộ danh sách codes của Spring:
String c = messages.getMessage(fieldError, locale);
```

Đoạn trên là snippet: giả sử `messages` là bean `MessageSource`, `locale` là `Locale` và `fieldError` là `FieldError`.

### 3.1. Thay thế arguments

Bundle:

```properties
api.hello=Welcome, {0}!
api.age.range=Age must be between {0} and {1}
```

Java:

```java
String text = messages.getMessage(
        "api.hello",
        new Object[]{"Lan"},
        locale
);
```

Với locale tiếng Anh, kết quả là:

```text
Welcome, Lan!
```

`{0}`, `{1}` trong Spring MessageSource theo ngữ nghĩa `MessageFormat`. Đừng nhầm với `{min}` và `{max}` trong template Bean Validation, hay biến EL `${validatedValue}` do Jakarta/Hibernate Validator nội suy.

### 3.2. FieldError là MessageSourceResolvable

Spring `FieldError` và `ObjectError` có:

- `getCode()`: mã lỗi đơn giản, ví dụ `NotBlank`.
- `getCodes()`: danh sách codes cụ thể → tổng quát.
- `getArguments()`: arguments cho message.
- `getDefaultMessage()`: thông báo mặc định đã có hoặc được provider nội suy.
- `getField()` với `FieldError`: tên trường lỗi.
- `getRejectedValue()`: giá trị bị từ chối, **không tự trả ra client vì có thể chứa dữ liệu nhạy cảm**.

Khi gọi:

```java
String localized = messages.getMessage(fieldError, locale);
```

Spring có thể thử một loạt codes rồi dùng default message nếu các bundle không có code phù hợp. Gọi `getCode()` rồi tìm duy nhất mã `NotBlank` sẽ bỏ qua bản dịch đặc biệt cho một DTO/field.

## 4. DefaultMessageCodesResolver và độ ưu tiên của mã lỗi

Giả sử một DTO tên `AccountRequest` có `@NotBlank String name`. Lỗi field `name` thường nhận các codes theo thứ tự:

```text
NotBlank.accountRequest.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
```

`DefaultMessageCodesResolver` giúp Spring thử code chi tiết nhất trước. Nhờ đó:

```properties
NotBlank.accountRequest.name=Name must not be blank
NotBlank.name=A name is required
NotBlank=Text is required
```

có thể phục vụ nhiều mức tùy biến. Những tên code thực tế còn phụ thuộc `objectName`, kiểu trường, nested property path và loại lỗi. Không hardcode danh sách trên cho mọi trường hợp.

Với Spring validator tự viết:

```java
errors.rejectValue("name", "app.name.blocked");
```

và object name `signup`, Spring có thể tạo:

```text
app.name.blocked.signup.name
app.name.blocked.name
app.name.blocked.java.lang.String
app.name.blocked
```

Chỉ cần đặt khóa thích hợp vào bundle; không buộc phải viết code dịch ngay trong validator. Ngược lại, **mã do Spring `rejectValue` đăng ký không nhất thiết là annotation của Jakarta Validation**.

### 4.1. Global errors

Custom constraint cấp lớp có thể tạo `ObjectError` chứ không phải `FieldError`. Khi dựng response, nên kiểm tra `getAllErrors()` hoặc kết hợp `getFieldErrors()` và `getGlobalErrors()`. Nếu chỉ đọc field errors, ứng dụng có thể bỏ sót ràng buộc kiểm tra quan hệ nhiều trường. Trong dự án runnable, dùng `getAllErrors()` và biểu diễn lỗi cấp object bằng `field=""`.

## 5. Locale trong Spring MVC

### 5.1. Accept-Language

Client có thể gửi:

```http
Accept-Language: vi
```

hoặc:

```http
Accept-Language: en-US,en;q=0.9,vi;q=0.8
```

Spring MVC dùng `LocaleResolver` để chọn locale cho request. `AcceptHeaderLocaleResolver` thường đọc header và có thể xét danh sách locales hỗ trợ, default locale.

Khi request đi qua `DispatcherServlet`, các controller methods và `@ExceptionHandler` trong MVC có thể nhận trực tiếp tham số `Locale locale`:

```java
@GetMapping("/hello")
public String hello(Locale locale) {
    return locale.toLanguageTag();
}
```

Dùng `Locale` request-specific giúp máy chủ phục vụ nhiều người dùng khác ngôn ngữ đồng thời mà không đổi locale toàn JVM.

### 5.2. Supported locales không tự chuẩn hóa mọi language tag

`vi` và `vi-VN` là hai locale khác nhau; tương tự `en` và `en-US`. `AcceptHeaderLocaleResolver#setSupportedLocales` có quy tắc matching, trong đó locale gồm language + country thường cần khớp đầy đủ; muốn fallback language-only, cần khai báo locale đó thích hợp. Hãy test các header mà client thật sự gửi.

Trong bài runnable, cố ý hỗ trợ `vi` và `en` trực tiếp, và fallback English cho mã ngôn ngữ khác.

### 5.3. Đừng kết hợp sai với LocaleChangeInterceptor

`LocaleChangeInterceptor` phục vụ chọn locale qua request parameter như `?lang=vi` khi có resolver hỗ trợ `setLocale(...)`. `AcceptHeaderLocaleResolver` **không hỗ trợ setter này**; server không thể sửa HTTP Accept-Language do client đã gửi.

Nếu ứng dụng muốn lưu ngôn ngữ người dùng bằng cookie hoặc session, hãy cân nhắc `CookieLocaleResolver` hoặc `SessionLocaleResolver`. Không thêm interceptor chỉ vì thấy hướng dẫn sử dụng query parameter mà chưa đổi resolver.

### 5.4. Tránh Locale.setDefault khi xử lý request

Sai:

```java
Locale.setDefault(Locale.forLanguageTag("vi"));
```

Điều này đổi mặc định **toàn JVM**, có thể làm các request tiếng Anh nhận bản dịch sai trong môi trường nhiều luồng. Đúng hướng: lấy `Locale` đã được resolve cho request và truyền thẳng vào `MessageSource`. `LocaleContextHolder` hữu ích trong code đồng bộ có request context, nhưng không thay cách truyền tường minh nếu logic chạy bất đồng bộ hay ngoài request.

## 6. Resource bundles và cấu hình Spring Boot

Cấu trúc điển hình:

```text
src/main/resources/
  application.properties
  messages.properties
  messages_vi.properties
  messages_en.properties         # Tùy chọn nếu base là tiếng Anh
  messages_vi_VN.properties      # Tùy chọn nếu có khác biệt theo vùng
```

Spring Boot có MessageSource auto-configuration. Với basename `messages`, hãy bảo đảm có **base file `messages.properties`**. Chỉ có `messages_vi.properties` mà thiếu base có thể khiến auto-configuration không tạo MessageSource mong muốn.

`application.properties`:

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

Ý nghĩa:

- `basename` là gốc tên tài nguyên. Có thể dùng nhiều basename như `messages,i18n/errors` khi thật sự có hai bộ resource files.
- `encoding=UTF-8` để đọc tiếng Việt đúng.
- `fallback-to-system-locale=false` tránh dùng locale của host server khi không tìm được file locale mong muốn; dùng base fallback theo thiết kế.
- Trong production có thể cấu hình caching thích hợp; không tạo `ResourceBundleMessageSource` mới trên từng request.

Nếu ứng dụng tự khai báo bean `MessageSource` có tên `messageSource`, hãy hiểu Boot có thể nhường chỗ cho bean do ứng dụng quản lý. Khi đó cấu hình basename/encoding/fallback phải được xử lý nhất quán.

### 6.1. Spring MessageSource và Jakarta ValidationMessages là hai đường khác nhau

Jakarta Validation cho phép:

```java
@NotBlank(message = "{account.name.required}")
private String name;

@Size(min = 4, max = 12, message = "{account.code.size}")
private String code;
```

Provider có thể tìm các khóa này trong:

```text
ValidationMessages.properties
ValidationMessages_vi.properties
```

Ví dụ:

```properties
# ValidationMessages.properties
account.name.required=Name is required
account.code.size=Code length must be from {min} to {max}
```

```properties
# ValidationMessages_vi.properties
account.name.required=Tên là bắt buộc
account.code.size=Mã phải có từ {min} đến {max} ký tự
```

`{min}`/`{max}` là attributes của constraint `@Size`, không phải Spring `MessageFormat` arguments `{0}`/`{1}`. Kết quả interpolation có thể trở thành default message trong một `FieldError`, còn `MessageSource#getMessage(fieldError, locale)` có thể override thông báo đó theo danh sách codes của Spring.

Khi muốn thống nhất nguồn bundle, Spring `LocalValidatorFactoryBean#setValidationMessageSource(...)` hỗ trợ tích hợp, nhưng cần hiểu giới hạn provider, không cấu hình cả `setValidationMessageSource` và `setMessageInterpolator` cùng lúc. Tài liệu Spring lưu ý khả năng này liên quan tới Hibernate Validator's interpolation support; nó không phải tính năng “portable” của mọi Jakarta provider. Đừng tự tạo một validator bean khác rồi tin rằng MVC chắc chắn dùng nó; phải kiểm tra Spring Boot và web MVC configuration thực tế.

Trong dự án runnable dưới đây **chỉ dùng `messages*.properties` cho lỗi API**, còn template Jakarta giữ mặc định. Nhờ vậy có thể quan sát rõ Spring resolution.

## 7. Dự án runnable: Spring Boot, Java 17, API lỗi vi/en

Ứng dụng demo có:

- `POST /api/accounts`: JSON request, `@Valid`, HTTP 201 nếu hợp lệ.
- Lỗi `@NotBlank`, `@Min`, `@NotNull`: HTTP 400 và localized messages.
- `GET /api/hello?name=Lan`: ví dụ `MessageFormat` với argument `{0}`.
- JSON không đọc được: HTTP 400 với code `INVALID_PAYLOAD` riêng.
- `MockMvc` test tiếng Việt, tiếng Anh, fallback, thiếu field và JSON malformed.

### 7.1. Cấu trúc source

```text
i18n-validation-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/i18nvalidation/
        I18nValidationApplication.java
        LocaleConfiguration.java
        AccountRequest.java
        AccountController.java
        Violation.java
        ApiError.java
        ValidationAdvice.java
      resources/
        application.properties
        messages.properties
        messages_vi.properties
    test/
      java/com/example/i18nvalidation/
        I18nValidationTest.java
```

### 7.2. Build Gradle

Tệp `settings.gradle`:

```groovy
rootProject.name = 'i18n-validation-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` mang Servlet Spring MVC/Jackson; `spring-boot-starter-validation` cung cấp Jakarta Validation provider thông thường (Hibernate Validator qua Spring Boot BOM). Nếu thiếu provider, chỉ có `@Valid` trên source không bảo đảm validation tự chạy.

### 7.3. Spring Boot application

`src/main/java/com/example/i18nvalidation/I18nValidationApplication.java`:

```java
package com.example.i18nvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class I18nValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(I18nValidationApplication.class, args);
    }
}
```

### 7.4. Cấu hình locale

`src/main/java/com/example/i18nvalidation/LocaleConfiguration.java`:

```java
package com.example.i18nvalidation;

import java.util.List;
import java.util.Locale;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.i18n.AcceptHeaderLocaleResolver;

@Configuration
public class LocaleConfiguration {

    @Bean
    public LocaleResolver localeResolver() {
        AcceptHeaderLocaleResolver resolver =
                new AcceptHeaderLocaleResolver();

        resolver.setSupportedLocales(List.of(
                Locale.ENGLISH,
                Locale.forLanguageTag("vi")
        ));
        resolver.setDefaultLocale(Locale.ENGLISH);
        return resolver;
    }
}
```

`Accept-Language: vi` chọn Việt; `en` chọn Anh; `fr` không thuộc danh sách nên dùng English fallback. Đối với clients gửi `vi-VN`/`en-US`, hãy thêm/test locale support thực tế khi sản phẩm yêu cầu.

### 7.5. Các resource files

`src/main/resources/application.properties`:

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

`src/main/resources/messages.properties` (base tiếng Anh):

```properties
api.validation.failed=Input is invalid
api.invalid.json=Request JSON cannot be read
api.hello=Welcome, {0}!

NotBlank.accountRequest.name=Name must not be blank
NotBlank.name=Name must not be blank
Min.accountRequest.age=Age must be at least 18
Min.age=Age must be at least 18
NotNull.accountRequest.age=Age is required
NotNull.age=Age is required
Email.accountRequest.email=Email format is invalid
Email.email=Email format is invalid
```

`src/main/resources/messages_vi.properties`:

```properties
api.validation.failed=Dữ liệu không hợp lệ
api.invalid.json=Không thể đọc JSON của yêu cầu
api.hello=Xin chào, {0}!

NotBlank.accountRequest.name=Tên không được bỏ trống
NotBlank.name=Tên không được bỏ trống
Min.accountRequest.age=Tuổi phải từ 18
Min.age=Tuổi phải từ 18
NotNull.accountRequest.age=Tuổi là bắt buộc
NotNull.age=Tuổi là bắt buộc
Email.accountRequest.email=Định dạng email không hợp lệ
Email.email=Định dạng email không hợp lệ
```

Khi Spring tạo `FieldError` cho record `AccountRequest`, các codes chi tiết như `NotBlank.accountRequest.name` và `Min.accountRequest.age` được tìm trước; các code `NotBlank.name` và `Min.age` cũng cung cấp fallback. `api.validation.failed` và `api.invalid.json` là **application codes** riêng, không phải tên Jakarta constraints.

### 7.6. DTO có constraints

`src/main/java/com/example/i18nvalidation/AccountRequest.java`:

```java
package com.example.i18nvalidation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record AccountRequest(
        @NotBlank String name,
        @NotNull @Min(18) Integer age,
        @Email String email
) {}
```

`age` cần cả `@NotNull` và `@Min`: `@Min` tự nó coi null hợp lệ. `email` tùy chọn trong demo (`@Email` không cấm null); thêm `@NotBlank` nếu business contract bắt buộc email.

### 7.7. DTO lỗi có code ổn định

`src/main/java/com/example/i18nvalidation/Violation.java`:

```java
package com.example.i18nvalidation;

public record Violation(
        String field,
        String code,
        String message
) {}
```

`src/main/java/com/example/i18nvalidation/ApiError.java`:

```java
package com.example.i18nvalidation;

import java.util.List;

public record ApiError(
        String code,
        String message,
        List<Violation> errors
) {}
```

`code` dùng cho logic client, `message` để hiển thị; `field` xác định vị trí lỗi. Khi localize, `field`/`code` không nên thay đổi theo ngôn ngữ.

### 7.8. Controller

`src/main/java/com/example/i18nvalidation/AccountController.java`:

```java
package com.example.i18nvalidation;

import jakarta.validation.Valid;
import java.util.Locale;
import java.util.Map;
import org.springframework.context.MessageSource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class AccountController {

    private final MessageSource messages;

    public AccountController(MessageSource messages) {
        this.messages = messages;
    }

    @PostMapping(
        path = "/accounts",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Map<String, Object>> create(
            @Valid @RequestBody AccountRequest input) {

        return ResponseEntity.status(HttpStatus.CREATED).body(
                Map.of("name", input.name(), "age", input.age())
        );
    }

    @GetMapping("/hello")
    public Map<String, String> hello(
            @RequestParam(defaultValue = "visitor") String name,
            Locale locale) {

        return Map.of(
                "message",
                messages.getMessage(
                        "api.hello",
                        new Object[]{name},
                        locale
                )
        );
    }
}
```

Đối với POST, Spring phải deserialize JSON, validate `AccountRequest` rồi mới gọi `create` nếu không có lỗi. Đối với GET, tham số `Locale` được Spring MVC resolve theo request và dùng để tra `api.hello`.

### 7.9. Advice dùng MessageSource để tạo response

`src/main/java/com/example/i18nvalidation/ValidationAdvice.java`:

```java
package com.example.i18nvalidation;

import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import org.springframework.context.MessageSource;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationAdvice {

    private final MessageSource messages;

    public ValidationAdvice(MessageSource messages) {
        this.messages = messages;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalid(
            MethodArgumentNotValidException ex,
            Locale locale) {

        String summary = messages.getMessage(
                "api.validation.failed", null, locale
        );

        return ResponseEntity.badRequest().body(
                toApiError(ex.getBindingResult(), locale, summary)
        );
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException ex,
            Locale locale) {

        String text = messages.getMessage(
                "api.invalid.json", null, locale
        );

        return ResponseEntity.badRequest().body(
                new ApiError("INVALID_PAYLOAD", text, List.of())
        );
    }

    private ApiError toApiError(
            BindingResult result,
            Locale locale,
            String summary) {

        List<Violation> errors = result.getAllErrors()
                .stream()
                .map(error -> asViolation(error, locale))
                .sorted(Comparator
                        .comparing(Violation::field)
                        .thenComparing(Violation::code))
                .toList();

        return new ApiError("VALIDATION_ERROR", summary, errors);
    }

    private Violation asViolation(
            ObjectError error,
            Locale locale) {

        String field = error instanceof FieldError fieldError
                ? fieldError.getField()
                : "";

        String code = Objects.toString(error.getCode(), "invalid");

        // Tra toàn bộ codes/arguments, không chỉ error.getCode().
        String message = messages.getMessage(error, locale);

        return new Violation(field, code, message);
    }
}
```

**Giải thích:**

- `MethodArgumentNotValidException` là đường exception thường gặp khi `@Valid @RequestBody` command object không đạt Bean Validation.
- `getAllErrors()` giữ cả `FieldError` và `ObjectError` (cấp lớp). Với global error, ví dụ đặt `field=""`.
- `messages.getMessage(error, locale)` giải theo tất cả codes và dùng default message khi cần.
- Sort theo `field` rồi `code` giúp response có thứ tự ổn định do ứng dụng định nghĩa; thứ tự kiểm tra constraints không được Jakarta bảo đảm.
- Handler `HttpMessageNotReadableException` dành riêng cho JSON không deserialize được. Không gọi nó là lỗi `@NotBlank` khi object chưa được tạo.
- API không trả rejected values hoặc raw parser exception để tránh rò rỉ dữ liệu nhạy cảm.

## 8. Kiểm thử với MockMvc

`src/test/java/com/example/i18nvalidation/I18nValidationTest.java`:

```java
package com.example.i18nvalidation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class I18nValidationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void invalidInputIsTranslatedIntoVietnamese() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "vi")
                .content("""
                        {
                          "name": " ",
                          "age": 17,
                          "email": "lan@example.org"
                        }
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.message")
                    .value("Dữ liệu không hợp lệ"))
            .andExpect(jsonPath("$.errors[0].field").value("age"))
            .andExpect(jsonPath("$.errors[0].code").value("Min"))
            .andExpect(jsonPath("$.errors[0].message")
                    .value("Tuổi phải từ 18"))
            .andExpect(jsonPath("$.errors[1].field").value("name"))
            .andExpect(jsonPath("$.errors[1].message")
                    .value("Tên không được bỏ trống"));
    }

    @Test
    void sameConstraintsDisplayEnglish() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "en")
                .content("""
                        {
                          "name": " ",
                          "age": 17,
                          "email": "lan@example.org"
                        }
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message").value("Input is invalid"))
            .andExpect(jsonPath("$.errors[0].message")
                    .value("Age must be at least 18"))
            .andExpect(jsonPath("$.errors[1].message")
                    .value("Name must not be blank"));
    }

    @Test
    void localizedGreetingUsesAnArgument() throws Exception {
        mvc.perform(get("/api/hello")
                .param("name", "Lan")
                .header("Accept-Language", "vi"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("Xin chào, Lan!"));

        mvc.perform(get("/api/hello")
                .param("name", "Lan")
                .header("Accept-Language", "en"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("Welcome, Lan!"));
    }

    @Test
    void unsupportedLocaleFallsBackToEnglish() throws Exception {
        mvc.perform(get("/api/hello")
                .param("name", "Lan")
                .header("Accept-Language", "fr"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("Welcome, Lan!"));
    }

    @Test
    void missingAgeUsesNotNullTranslation() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "vi")
                .content("""
                        {
                          "name": "Lan",
                          "email": "lan@example.org"
                        }
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].field").value("age"))
            .andExpect(jsonPath("$.errors[0].code").value("NotNull"))
            .andExpect(jsonPath("$.errors[0].message")
                    .value("Tuổi là bắt buộc"));
    }

    @Test
    void malformedJsonIsNotValidationError() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "vi")
                .content("{\"name\":\"Lan\",\"age\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_PAYLOAD"))
            .andExpect(jsonPath("$.message")
                    .value("Không thể đọc JSON của yêu cầu"));
    }

    @Test
    void validRequestSucceeds() throws Exception {
        mvc.perform(post("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "vi")
                .content("""
                        {
                          "name": "Lan",
                          "age": 24,
                          "email": "lan@example.org"
                        }
                        """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.name").value("Lan"))
            .andExpect(jsonPath("$.age").value(24));
    }
}
```

Chạy:

```bash
./gradlew test
```

Trên Windows:

```powershell
.\gradlew.bat test
```

**Kết quả mong đợi:** bảy test PASS khi đúng dependency/resource files. Cùng một request lỗi trả message khác theo locale, trong khi HTTP status, `code` và `field` không đổi.

Trong demo, advice tự **sort errors theo field**, vì vậy `errors[0]` là `age` và `errors[1]` là `name`. Nếu bỏ sort, không nên assert vị trí trong danh sách lỗi vì provider có thể kiểm tra constraint theo thứ tự khác.

Không nên hiểu việc viết test trong bài là bằng chứng đã chạy Gradle trên máy; cần thực thi `./gradlew test` trong project thực tế trước khi deploy.

## 9. Thử API bằng curl

Khởi chạy:

```bash
./gradlew bootRun
```

**Tiếng Việt:**

```bash
curl -i -X POST http://localhost:8080/api/accounts \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: vi' \
  -d '{"name":" ","age":17,"email":"lan@example.org"}'
```

Kỳ vọng HTTP **400 Bad Request**, body tương ứng:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Dữ liệu không hợp lệ",
  "errors": [
    {
      "field": "age",
      "code": "Min",
      "message": "Tuổi phải từ 18"
    },
    {
      "field": "name",
      "code": "NotBlank",
      "message": "Tên không được bỏ trống"
    }
  ]
}
```

**Tiếng Anh:**

```bash
curl -i -X POST http://localhost:8080/api/accounts \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: en' \
  -d '{"name":" ","age":17,"email":"lan@example.org"}'
```

HTTP vẫn **400**, nhưng messages là `Age must be at least 18` và `Name must not be blank`. Trường `code` vẫn là `Min` và `NotBlank`.

**Chào hỏi:**

```bash
curl -i 'http://localhost:8080/api/hello?name=Lan' \
  -H 'Accept-Language: vi'
```

Body:

```json
{"message":"Xin chào, Lan!"}
```

Đây là ví dụ trực quan cho việc một message code có nhiều bản dịch và arguments; business method không cần viết `if(locale...)`.

## 10. Xử lý lỗi form @ModelAttribute

`@ModelAttribute` thường đi qua `WebDataBinder`, có thể tạo cả lỗi conversion và lỗi Jakarta constraints. Một controller có thể tự xử lý `BindingResult` nếu đặt nó **ngay sau** argument:

```java
@PostMapping("/signup")
public ResponseEntity<Map<String, Object>> signup(
        @Valid @ModelAttribute("signup") SignupForm form,
        BindingResult errors,
        Locale locale) {

    if (errors.hasErrors()) {
        List<String> texts = errors.getAllErrors().stream()
                .map(error -> messages.getMessage(error, locale))
                .toList();
        return ResponseEntity.badRequest()
                .body(Map.of("messages", texts));
    }

    return ResponseEntity.ok(Map.of("status", "created"));
}
```

Đây là **snippet minh họa** không thuộc ứng dụng runnable; giả sử đã định nghĩa `SignupForm` và inject bean `MessageSource messages`.

Với `age=abc` trong form `Integer age`, binder có thể tạo lỗi `typeMismatch.signup.age`. Bạn có thể dịch:

```properties
# messages.properties
typeMismatch.signup.age=Age must be a number
```

```properties
# messages_vi.properties
typeMismatch.signup.age=Tuổi phải là một số
```

Đó là lỗi **chuyển đổi kiểu** chứ không phải vi phạm `@Min`. Nếu JSON body sai cú pháp, thường controller còn không được gọi, nên `BindingResult` không phải công cụ xử lý lỗi parser; cần `@ExceptionHandler` thích hợp.

### Vị trí BindingResult

Đúng:

```java
method(@Valid @ModelAttribute Form form, BindingResult errors)
```

Sai:

```java
method(@Valid @ModelAttribute Form form,
       @RequestParam String referrer,
       BindingResult errors)
```

Đây là các đoạn chữ ký method minh họa. `BindingResult` phải đứng sát argument mà nó liên kết. Nếu Spring MVC 6.1+ sử dụng **method validation** do có direct constraints trên signature, cần đối chiếu thêm `HandlerMethodValidationException`; không mặc định mọi lỗi đều là `MethodArgumentNotValidException`.

## 11. Tích hợp với ProblemDetail và method validation

Spring Framework hỗ trợ `ProblemDetail` và `ResponseEntityExceptionHandler`. Khi dùng cơ chế `ErrorResponse`, các message codes cho `type`, `title`, `detail` có thể được giải qua `MessageSource`. Đây là lựa chọn tốt nếu API đã tiêu chuẩn hóa RFC 9457 thay vì tự dùng `ApiError`.

Trong Spring MVC 6.1+, một handler có direct constraint như:

```java
@GetMapping("/pages")
public String page(@RequestParam @Min(1) int page) {
    return "page=" + page;
}
```

thường dùng `HandlerMethodValidationException` thay vì `MethodArgumentNotValidException` cho input validation. Exception có `isForReturnValue()` để phân biệt:

- Input constraint vi phạm → thường HTTP **400**.
- Return-value constraint vi phạm → lỗi hợp đồng server, thường HTTP **500**.

Khi localize method validation errors, hãy giữ sự phân loại này; đừng bắt mọi validation exception rồi trả 400. Các `MessageSourceResolvable` trong method validation results có thể được resolve theo request locale, hoặc dùng `ResponseEntityExceptionHandler` để hỗ trợ i18n chung. Đối với nhiều handler/advice, cần kiểm tra thứ tự ưu tiên `@Order` và tránh khai báo trùng nhau gây xung đột.

## 12. Lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Khắc phục |
| --- | --- | --- |
| Có `messages_vi.properties` mà không có `messages.properties` | Boot MessageSource auto-config không như mong đợi | Thêm base bundle |
| Lỗi luôn hiện English | Locale sai, key thiếu hoặc chỉ dùng `getDefaultMessage()` | Kiểm tra Accept-Language, resolver và `getMessage(error, locale)` |
| Lỗi `NoSuchMessageException` | Gọi getMessage không fallback với key thiếu | Bổ sung key hoặc dùng overload có default |
| Bản dịch thiếu field-specific semantics | Chỉ resolve `getCode()` | Dùng toàn `FieldError` là `MessageSourceResolvable` |
| `@Valid` không hoạt động | Thiếu provider hoặc kích hoạt sai điểm | Kiểm tra starter validation, annotation boundary |
| `@Min` không báo khi field null | `@Min` cho phép null | Thêm `@NotNull` |
| Lỗi ràng buộc lớp bị mất | Chỉ đọc `getFieldErrors()` | Dùng `getAllErrors()` |
| Lỗi JSON malformed trả như Bean Validation | Không tách parser exception | Handler `HttpMessageNotReadableException` |
| `LocaleChangeInterceptor` không đổi language | Đang dùng AcceptHeaderLocaleResolver | Dùng Cookie/Session resolver nếu cần query language |
| Thấy `TÃªn` thay vì `Tên` | Encoding/terminal sai | Đọc bundle UTF-8, kiểm tra response/client |
| Thay language làm frontend sai | Frontend so sánh literal message | Dùng `code` ổn định và `field` |
| Mã và message phụ thuộc provider | API đưa raw constraint text làm code | Map sang business error code ổn định |
| Thông báo chứa secret | Dùng rejectedValue/parser text trong message | Trả text kiểm soát, không lộ giá trị |
| Error response toàn 400 | Không phân biệt input vs output contract | Return violation thường 500 |
| Khác biệt `vi` và `vi-VN` | Supported locale matching không đúng kỳ vọng | Khai báo/test BCP 47 tags thực tế |
| Trộn `javax.validation` và `jakarta.validation` | Namespace Spring Boot 2 vs 3 | Dùng Jakarta cho Spring Boot 3 |
| HTTP cache trả sai ngôn ngữ | Cache không xét `Accept-Language` | Xem xét `Vary: Accept-Language`, cache key |
| Formatting số/ngày sai timezone | Nhầm Locale với timezone | Cấu hình timezone riêng khi cần |

### Bảo mật thông điệp

`FieldError#getRejectedValue()` có thể chứa password, token hoặc PII. Không trả giá trị bị từ chối ra JSON chỉ vì muốn “giúp người dùng sửa”. Tương tự, raw `HttpMessageNotReadableException#getMessage()` có thể lộ cấu trúc Java/Jackson hoặc nội dung request. Hãy dùng mã lỗi và thông báo được kiểm soát, đồng thời ghi log an toàn với correlation ID ở phía server.

`MessageSource` không phải bộ sanitize HTML. Nếu chèn message hoặc arguments do người dùng cung cấp vào trang HTML, lớp view phải escape output thích hợp để tránh XSS.

### Hiệu năng và môi trường

Không tạo mới `ResourceBundleMessageSource` cho từng request. Tận dụng bean được Spring quản lý, caching hợp lý và chuẩn bị bundles đầy đủ khi deploy. Không dùng `Locale.setDefault` để thay ngôn ngữ request. Với `@Async`, scheduled jobs hoặc Reactive pipeline, không suy rằng ThreadLocal `LocaleContextHolder` luôn tự chuyển cùng nhiệm vụ; truyền `Locale` tường minh khi cần.

## 13. Checklist triển khai

1. Chốt danh sách ngôn ngữ/region thực sự hỗ trợ (`vi`/`en`, nếu cần thêm `vi-VN`/`en-US`).
2. Tạo `messages.properties` base và mỗi bản dịch; bảo đảm UTF-8.
3. Cấu hình `spring.messages.basename`, fallback và encoding.
4. Dùng `LocaleResolver` thích hợp với nguồn locale của sản phẩm.
5. Không dùng `Locale.setDefault(...)` cho từng request.
6. Bật Jakarta Validation provider và kích hoạt `@Valid`/`@Validated` tại đúng boundary.
7. Với Spring binding errors, dùng `MessageSource#getMessage(FieldError/ObjectError, Locale)` để giải toàn bộ codes.
8. Giữ `error.code` và `error.field` ổn định; chỉ localized text thay đổi.
9. Phân biệt `ValidationMessages`/`MessageInterpolator` với `messages`/`MessageSource`; tích hợp có chủ đích khi cần.
10. Xử lý cả field errors, global errors, conversion errors và parser exceptions đúng loại.
11. Không trả rejected values, raw stack traces hay dữ liệu nhạy cảm.
12. MockMvc test Việt/Anh/fallback, thiếu key, thiếu field, sai kiểu, JSON malformed, request hợp lệ.
13. Nếu dùng `ProblemDetail`, xác định rõ lớp chịu trách nhiệm dịch `type/title/detail` và thứ tự advice.
14. Nếu response khác nhau theo Accept-Language và có caching, xem xét `Vary: Accept-Language`/cache key.
15. Kiểm tra tương thích namespace Jakarta và BOM Spring Boot khi nâng cấp.

**Kết luận:** `MessageSource` trả lời “với mã lỗi và locale này, hiển thị câu nào?”, `LocaleResolver` xác định ngôn ngữ của request, còn `FieldError`/`ObjectError` chỉ ra quy tắc nào bị vi phạm. Jakarta Validation `MessageInterpolator` là một cơ chế khác để nội suy template constraint. Khi giữ các tầng độc lập, cùng một API có thể trả thông báo tiếng Việt/tiếng Anh đúng ngữ cảnh, trong khi validation rules, HTTP status và machine-readable error codes vẫn nhất quán.

## Tài liệu tham khảo

- [Spring Framework — Resolving Codes to Error Messages](https://docs.spring.io/spring-framework/reference/6.2/core/validation/conversion.html): `DefaultMessageCodesResolver` và thứ tự mã lỗi.
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/reference/features/internationalization.html): `spring.messages.*`, quy tắc base bundle.
- [Spring Framework — Locale](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/localeresolver.html): `LocaleResolver`, `Accept-Language` và lựa chọn ngôn ngữ.
- [Spring Framework — AcceptHeaderLocaleResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/servlet/i18n/AcceptHeaderLocaleResolver.html): danh sách supported locales và giới hạn `setLocale`.
- [Spring Framework — LocalValidatorFactoryBean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html): kết nối Jakarta validation với Spring MessageSource.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): argument/method validation và exception.
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): resource bundles và MessageInterpolator.
