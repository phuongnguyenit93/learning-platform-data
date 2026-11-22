# Thông báo thiếu bản dịch và giá trị mặc định trong Spring Framework

## 1. Vấn đề thực tế: người dùng chọn tiếng Việt nhưng không phải khóa nào cũng có bản dịch

Một hệ thống Spring MVC phục vụ cả tiếng Việt và tiếng Anh. API xác thực form đăng ký gồm tên và tuổi:

```http
POST /api/signup
Content-Type: application/json
Accept-Language: vi

{"name":" ","age":16}
```

Quy tắc không phụ thuộc ngôn ngữ: `name` phải có nội dung, `age` tối thiểu 18. Tuy nhiên khi trả lỗi, ứng dụng có thể gặp một trong ba tình huống:

1. **Có bản dịch tiếng Việt:** `NotBlank.signupInput.name` → “Tên không được bỏ trống”.
2. **Thiếu bản dịch tiếng Việt nhưng còn thông báo ở base bundle:** `Min.signupInput.age` → “Age must be at least 18”.
3. **Không có khóa ở bất cứ resource bundle nào:** `ui.notProvided` → sử dụng một chuỗi mặc định do lập trình viên truyền, hoặc phát sinh `NoSuchMessageException` nếu dùng overload không có mặc định.

Cần phân biệt **thiếu bản dịch** với **không có thông báo**. Một mã có thể thiếu ở `messages_vi.properties` nhưng vẫn được tìm thấy ở `messages.properties`, một mã khác trong danh sách `FieldError#getCodes()` hoặc một parent `MessageSource`.

Bài này giải thích các cơ chế fallback, cách lựa chọn giá trị mặc định, những bẫy của `useCodeAsDefaultMessage`, và cách viết API/tests để **không biến lỗi thiếu nội dung i18n thành lỗi server không mong muốn**.

**Phạm vi:** Spring Framework 6.1–6.2, Spring Boot 3.x, Jakarta Validation 3.x, Servlet Spring MVC, Java 17+. Ví dụ thực hành dùng Spring Boot 3.3.6. Các lớp Spring WebFlux (như `WebExchangeBindException`) khác với các lớp MVC đang được trình bày.

## 2. Ba tầng fallback không giống nhau

| Tầng | Nguồn | Ví dụ | Phải nhớ |
| --- | --- | --- | --- |
| **Locale fallback** | `LocaleResolver` | Header `fr` không hỗ trợ → chọn `en` | Xảy ra trước hoặc trong quá trình xác định ngôn ngữ request |
| **Resource bundle / error-code fallback** | `MessageSource` | Key thiếu ở `messages_vi.properties` → có ở `messages.properties`; `FieldError` thử nhiều codes | Chỉ quyết định tra được văn bản nào |
| **Explicit defaultMessage** | Lời gọi `getMessage` | Không tìm được `ui.unknown` → “Information unavailable” | Do ứng dụng cung cấp tại điểm tra message |

Một trường hợp khác là **lỗi nội dung dịch**: khóa tồn tại nhưng giá trị rỗng, placeholder mất hoặc sai chính tả. Lookup có thể thành công về mặt kỹ thuật nhưng trải nghiệm chưa đạt. Không nhầm trường hợp đó với missing key.

### 2.1. Ví dụ đối chiếu

Giả sử:

```properties
# messages.properties (base English)
ui.hello=Hello, {0}!
ui.baseOnly=This text is available only in the base bundle
```

```properties
# messages_vi.properties
ui.hello=Xin chào, {0}!
# Không khai báo ui.baseOnly
```

Với locale `vi`:

- `getMessage("ui.hello", ...)` → “Xin chào, Lan!”.
- `getMessage("ui.baseOnly", ...)` → “This text is available only in the base bundle”.
- `getMessage("ui.notProvided", ...)` → dùng explicit default hoặc có thể ném `NoSuchMessageException`, vì key vắng mặt ở cả base và vi.

Thử với locale `fr` khi `LocaleResolver` chỉ hỗ trợ vi/en là một thử nghiệm **khác**: resolver có thể chọn locale English mặc định. Đừng kết luận “key thiếu bản dịch Pháp” chỉ từ việc response hiện English.

## 3. MessageSource và ba overload quan trọng nhất

Spring dùng interface:

```java
org.springframework.context.MessageSource
```

### 3.1. Có defaultMessage: fallback mềm

```java
String text = messageSource.getMessage(
        "ui.notProvided",
        null,
        "Information is currently unavailable",
        locale
);
```

Với code không tồn tại, phương thức dùng `defaultMessage`. Nếu default chứa placeholders và có arguments, Spring có thể render theo `MessageFormat`:

```java
String text = messageSource.getMessage(
        "ui.greeting.notProvided",
        new Object[]{"Lan"},
        "Hello, {0}!",
        Locale.ENGLISH
);
```

Kết quả minh họa:

```text
Hello, Lan!
```

**Chú ý nullable:** overload có bốn tham số cho phép truyền `null` làm default; khi không tìm thấy thông báo, kết quả có thể là `null`:

```java
String optional = messageSource.getMessage(
        "ui.notProvided",
        null,
        (String) null,
        locale
);
```

Không dùng `Map.of("message", optional)` nếu chưa bảo đảm `optional` khác null: `Map.of` không nhận giá trị null. Nếu API luôn cần `message`, hãy cung cấp default không-null, ví dụ thông báo chung đã được kiểm duyệt.

### 3.2. Không defaultMessage: strict lookup

```java
String text = messageSource.getMessage(
        "ui.notProvided",
        null,
        locale
);
```

Nếu code không được resolve và không có cấu hình đặc biệt, Spring ném:

```java
org.springframework.context.NoSuchMessageException
```

Cách strict có giá trị ở **test/CI hoặc startup validation**: thiếu một key quan trọng thì phát hiện ngay. Nhưng dùng nó vô điều kiện trong `@ExceptionHandler` đang xử lý lỗi input 400 có thể khiến thiếu một bản dịch gây thêm exception, làm client nhận 500 thay vì lỗi ban đầu.

Mục tiêu không phải “không bao giờ để ứng dụng ném `NoSuchMessageException`”; mục tiêu là **dùng đúng nơi**:

- CI: phát hiện missing keys và yêu cầu hoàn thiện trước deploy.
- Error response production: fallback an toàn và metrics.
- Mã cấu hình bắt buộc: strict là hợp lý nếu vi phạm cấu hình phải dừng tiến trình khởi động.

### 3.3. MessageSourceResolvable: nhiều code và default riêng

```java
String translated = messageSource.getMessage(
        fieldError,
        locale
);
```

`FieldError` và `ObjectError` implements `MessageSourceResolvable`. Một error có thể mang nhiều code theo độ cụ thể, ví dụ:

```text
NotBlank.signupInput.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
```

`getMessage(error,locale)` thử danh sách đó và có thể dùng `error.getDefaultMessage()` nếu các code không phù hợp. Nếu không resolve được mã nào **và resolvable không có default**, `NoSuchMessageException` vẫn có thể xảy ra.

**Đừng đồng nhất overload này với `getMessage(error.getCode(),...)`.** Truyền một mã duy nhất sẽ bỏ qua code cụ thể theo field, default message và arguments của Spring.

## 4. Những “default” có tên giống nhau nhưng ý nghĩa khác

| Cấu hình / giá trị | Vai trò |
| --- | --- |
| `resolver.setDefaultLocale(Locale.ENGLISH)` | Locale fallback khi không chọn được ngôn ngữ yêu cầu |
| `messages.properties` | Base bundle, cung cấp thông báo khi locale-specific bundle thiếu |
| `getMessage(code,args,"Safe text",locale)` | Explicit default nếu không tìm được code |
| `FieldError#getDefaultMessage()` | Default message gắn với validation/binding error |
| `AbstractMessageSource#setUseCodeAsDefaultMessage(true)` | Debug fallback trả **chính mã code** khi không tìm được thông báo |
| `@RequestParam(defaultValue="guest")` | Giá trị mặc định cho **request parameter**, không phải i18n |
| `ValidationMessages.properties` | Bundle mặc định cho Jakarta Validation message interpolation, khác Spring messages |

Ví dụ sau nhấn mạnh phân biệt:

```java
@GetMapping("/welcome")
public String welcome(
        @RequestParam(defaultValue = "visitor") String name,
        Locale locale) {

    return messageSource.getMessage(
            "ui.welcome",
            new Object[]{name},
            "Welcome, {0}!",
            locale
    );
}
```

`"visitor"` là default của **input HTTP**, còn `"Welcome, {0}!"` là default của **lời tra message**. Cả hai có thể tồn tại trong cùng một phương thức nhưng hoàn toàn độc lập.

## 5. Bundle lookup, system-locale fallback và base bundle

Trong Spring Boot, thông thường tạo:

```text
src/main/resources/
  application.properties
  messages.properties
  messages_vi.properties
  messages_en.properties      # chỉ nếu cần ghi đè base English
  messages_vi_VN.properties   # khi có variant theo vùng
```

Cấu hình:

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

Ý nghĩa:

- `spring.messages.basename`: chọn basename; có thể khai báo nhiều base như `messages,i18n/errors`.
- `spring.messages.encoding=UTF-8`: đọc đúng tiếng Việt có dấu.
- `spring.messages.fallback-to-system-locale=false`: khi không tìm được locale-specific resource, **không thử locale của hệ điều hành**. Điều này giúp kết quả nhất quán ở máy dev, CI và production.
- Tắt system locale fallback **không tắt** base fallback từ `messages_vi.properties` về `messages.properties`.

**Quan trọng:** Spring Boot tự cấu hình `MessageSource` khi tìm thấy base bundle đã khai báo. Nếu chỉ tạo `messages_vi.properties` mà không có `messages.properties`, auto-configuration có thể không xuất hiện theo ý định. Luôn kiểm tra sự tồn tại của base file.

### 5.1. Chuỗi rỗng không giống mã vắng mặt

```properties
ui.banner=
```

Key `ui.banner` tồn tại với value rỗng. Lookup có thể coi đó là một message hợp lệ và trả chuỗi rỗng, **không tự sử dụng** explicit default. Do đó kiểm tra thiếu bản dịch phải xét cả:

- Không có key.
- Key có value rỗng/chỉ khoảng trắng.
- Template thiếu `{0}`, `{1}` hoặc sai escaping.
- Bản dịch có nội dung nhưng không đúng ngôn ngữ sản phẩm.
- Nội dung chứa thông tin riêng tư hoặc HTML không được escape phù hợp.

### 5.2. Locale tag có region

`vi` và `vi-VN` là hai `Locale` khác nhau. Khi ứng dụng hỗ trợ `vi`, đừng mặc nhiên tuyên bố mọi header `vi-VN` đều được resolver xử lý giống hệt, nếu chưa test rules của `AcceptHeaderLocaleResolver`. Tương tự `en-US` và `en`.

Nếu muốn người dùng thay đổi ngôn ngữ bằng `?lang=vi`, `LocaleChangeInterceptor` cần `LocaleResolver` hỗ trợ `setLocale` (như `CookieLocaleResolver` hoặc `SessionLocaleResolver`). `AcceptHeaderLocaleResolver` không hỗ trợ việc server ghi lại header request theo cách đó.

## 6. useCodeAsDefaultMessage: bẫy khi xử lý lỗi

`AbstractMessageSource` có setter:

```java
messageSource.setUseCodeAsDefaultMessage(true);
```

Đây là snippet giả định `messageSource` có kiểu `AbstractMessageSource`/subclass, không phải interface `MessageSource`.

Khi bật, một mã không tìm được có thể trở thành chính văn bản được trả:

```text
validation.user.internalOwnerId.invalid
```

Điều này tiện **debug**, nhưng không nên là fallback cho người dùng cuối. Raw code thường khó hiểu và đôi khi chứa cấu trúc field/class nội bộ.

### 6.1. Parent MessageSource có thể làm mất fallback codes

Javadoc của `AbstractMessageSource` cảnh báo: với `MessageSourceResolvable` có **nhiều codes** (như `FieldError`) và parent source bật `useCodeAsDefaultMessage`, source cha có thể trả **code đầu tiên** trước khi hệ thống có cơ hội tìm bản dịch từ các codes dự phòng.

Ví dụ:

```text
NotBlank.signupInput.name
NotBlank.name
NotBlank
```

Nếu `NotBlank.signupInput.name` không tồn tại nhưng `NotBlank.name` có bản dịch, bật trả code sớm ở parent có thể khiến client nhìn thấy `NotBlank.signupInput.name` thay vì thông báo phù hợp. Để tránh:

1. Giữ `useCodeAsDefaultMessage=false` trong production.
2. Không lạm dụng parent message source khi chỉ cần một số resource bundles.
3. Cấu hình các code có ngữ nghĩa rõ ràng.
4. Đo độ phủ bản dịch trực tiếp từ files trong CI.
5. Test những `FieldError` có nhiều error codes để phát hiện fallback bị thay đổi.

Nếu cần thông báo generic, dùng **explicit defaultMessage** chứ không lấy raw key làm bản dịch.

## 7. BindingResult và missing translation của Bean Validation errors

### 7.1. FieldError có nhiều mã

Spring `DefaultMessageCodesResolver` tạo danh sách codes ưu tiên theo độ cụ thể. Ví dụ `@NotBlank` của trường `SignupInput.name` có thể có:

```text
NotBlank.signupInput.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
```

Với một thông báo ở `messages.properties` và không có bản vi, `messages.getMessage(fieldError,Locale.forLanguageTag("vi"))` có thể vẫn trả base English.

`FieldError#getCode()` thích hợp làm **error code** trong JSON; `MessageSource#getMessage(fieldError,locale)` phù hợp để tính **localized text**. Đừng bắt frontend so sánh literal Vietnamese/English string để điều khiển validation UI.

### 7.2. ObjectError và class-level constraints

Nếu có custom constraint cấp lớp như “ngày kết thúc phải sau ngày bắt đầu”, Spring có thể tạo `ObjectError` không gắn một field cụ thể. Do đó, adapter cho lỗi API nên dùng:

```java
bindingResult.getAllErrors()
```

thay vì chỉ `getFieldErrors()`. `ObjectError` cũng là `MessageSourceResolvable` nên được tra bundle theo cùng mô hình. Nếu schema cần `field`, có thể biểu diễn global error với chuỗi rỗng hoặc một mảng `globalErrors` riêng.

### 7.3. Missing translation không làm validation PASS

Khi `age=16` vi phạm `@Min(18)`, kết quả kiểm tra vẫn **không hợp lệ**, kể cả key `Min.signupInput.age` bị thiếu trong file vi. Hệ thống cần trả HTTP 400, không đổi business logic chỉ vì thiếu message.

### 7.4. Binding errors khác validation errors

Với HTML form `@ModelAttribute`:

```text
age=abc
```

Spring có thể tạo code `typeMismatch.signupForm.age` khi chuyển chuỗi thành Integer thất bại. Đây không phải lỗi `@Min`. Bạn có thể khai báo:

```properties
# messages.properties
typeMismatch.signupForm.age=Age must be a number
```

```properties
# messages_vi.properties
typeMismatch.signupForm.age=Tuổi phải là một số
```

Trong `@Valid @RequestBody` JSON, nếu Jackson không parse được JSON, thông thường lỗi là `HttpMessageNotReadableException`. Không tạo `FieldError` giả rồi gọi nó là constraint failure.

## 8. Jakarta Validation MessageInterpolator và resource bundle riêng

Jakarta Validation có một cơ chế khác: **`MessageInterpolator`** nội suy templates của constraints.

```java
@NotBlank(message = "{signup.name.required}")
String name;

@Size(min = 4, max = 12, message = "{signup.code.size}")
String code;
```

Provider thường tìm templates trong:

```text
ValidationMessages.properties
ValidationMessages_vi.properties
```

Ví dụ:

```properties
# ValidationMessages.properties
signup.name.required=Name is required
signup.code.size=Code length must be between {min} and {max}
```

```properties
# ValidationMessages_vi.properties
signup.name.required=Tên là bắt buộc
signup.code.size=Độ dài mã phải từ {min} đến {max}
```

`{min}` và `{max}` thuộc constraint metadata của Jakarta Validation. Chúng **khác** placeholders `{0}`/`{1}` trong Spring `MessageFormat`.

Những điểm quan trọng:

- `messages.properties` phục vụ Spring `MessageSource`.
- `ValidationMessages.properties` phục vụ Jakarta Validation message interpolation.
- Chúng không tự động là một file.
- Provider có thể tạo default message cho `FieldError` trước khi Spring adapter lại tra `MessageSource` theo `FieldError#getCodes()`.
- Nếu cần cùng một nguồn, có thể cấu hình `LocalValidatorFactoryBean#setValidationMessageSource(...)` theo Spring và provider phù hợp; nhưng không tự coi đó là portable với mọi provider. Không cấu hình đồng thời `setValidationMessageSource` và `setMessageInterpolator` trên một bean validator theo hướng dẫn Spring.

Trong ví dụ thực hành, chúng ta **chỉ dùng Spring messages bundles để điều khiển API responses**; không tạo `ValidationMessages*.properties`, để tránh hai hệ thống chồng chéo làm khó việc minh họa missing translations.

## 9. Dự án thực hành Spring Boot 3.3.6, Java 17

Mục tiêu:

- Tra key có bản vi.
- Tra key chỉ có ở base English.
- Tra key hoàn toàn không tồn tại, có explicit default.
- Test strict lookup ném `NoSuchMessageException`.
- Test default nullable trả null.
- Trả lỗi `@Valid` với tên đã dịch tiếng Việt và tuổi **cố ý thiếu bản vi** để minh họa fallback.
- Bắt JSON malformed riêng với Bean Validation.
- Kiểm tra HTTP bằng `MockMvc`.

### 9.1. Cấu trúc source

```text
message-fallback-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/messagefallback/
        MessageFallbackApplication.java
        WebLocaleConfiguration.java
        SignupInput.java
        FieldIssue.java
        ApiError.java
        MessageController.java
        ApiErrorAdvice.java
      resources/
        application.properties
        messages.properties
        messages_vi.properties
    test/
      java/com/example/messagefallback/
        MessageFallbackTest.java
```

### 9.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'message-fallback-demo'
```

`build.gradle`:

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

`spring-boot-starter-web` cung cấp Servlet Spring MVC và Jackson; `spring-boot-starter-validation` có Jakarta Validation provider phù hợp với Spring Boot BOM. Chỉ đặt `@Valid` trên DTO mà không có provider và boundary validation phù hợp không bảo đảm ràng buộc được thực thi.

### 9.3. Main application

`src/main/java/com/example/messagefallback/MessageFallbackApplication.java`:

```java
package com.example.messagefallback;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MessageFallbackApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessageFallbackApplication.class, args);
    }
}
```

### 9.4. Locale resolver

`src/main/java/com/example/messagefallback/WebLocaleConfiguration.java`:

```java
package com.example.messagefallback;

import java.util.List;
import java.util.Locale;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.i18n.AcceptHeaderLocaleResolver;

@Configuration
public class WebLocaleConfiguration {

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

`Accept-Language: vi` chọn tiếng Việt; `en` chọn tiếng Anh; `fr` không nằm trong danh sách hỗ trợ nên fallback English. Nếu sản phẩm dùng `vi-VN` hay `en-US`, cần cấu hình/test thêm language tags phù hợp, không suy ra tự động giống hệt.

### 9.5. Resource bundle configurations

`src/main/resources/application.properties`:

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

`src/main/resources/messages.properties` (base tiếng Anh):

```properties
ui.hello=Hello, {0}!
ui.baseOnly=This text is available only in the base bundle
api.validation=Invalid input
api.invalidJson=Cannot read the request JSON

NotBlank.signupInput.name=Name must not be blank
NotBlank.name=Name must not be blank
Min.signupInput.age=Age must be at least 18
Min.age=Age must be at least 18
NotNull.signupInput.age=Age is required
NotNull.age=Age is required
```

`src/main/resources/messages_vi.properties`:

```properties
ui.hello=Xin chào, {0}!
api.validation=Dữ liệu không hợp lệ
api.invalidJson=Không thể đọc JSON của yêu cầu

NotBlank.signupInput.name=Tên không được bỏ trống
NotBlank.name=Tên không được bỏ trống

# Cố ý không có ui.baseOnly trong file vi
# Cố ý không có Min.signupInput.age và Min.age trong file vi
# Cố ý không có ui.notProvided trong bất cứ file nào
```

Đây là một bài tập minh họa missing translation. Trong production cần hoàn thiện:

```properties
Min.signupInput.age=Tuổi phải từ 18
Min.age=Tuổi phải từ 18
ui.baseOnly=Thông điệp đã có bản dịch tiếng Việt
```

Nếu thêm các key này, test kỳ vọng **fallback English** sẽ cần đổi thành kỳ vọng tiếng Việt; đó là thay đổi có chủ đích.

### 9.6. DTO nhận input

`src/main/java/com/example/messagefallback/SignupInput.java`:

```java
package com.example.messagefallback;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record SignupInput(
        @NotBlank String name,
        @NotNull @Min(18) Integer age
) {}
```

Cần `@NotNull` trên `age` vì `@Min` tự nó cho phép null. `@NotBlank` bắt chuỗi rỗng hoặc chỉ có khoảng trắng.

### 9.7. DTO lỗi

`src/main/java/com/example/messagefallback/FieldIssue.java`:

```java
package com.example.messagefallback;

public record FieldIssue(
        String field,
        String code,
        String message
) {}
```

`src/main/java/com/example/messagefallback/ApiError.java`:

```java
package com.example.messagefallback;

import java.util.List;

public record ApiError(
        String code,
        String message,
        List<FieldIssue> fields
) {}
```

`code` là thông tin máy/client có thể xử lý; `message` dành để hiển thị; `field` xác định vị trí lỗi. Thay đổi ngôn ngữ không được thay đổi các giá trị `code` hoặc HTTP status.

### 9.8. Controller

`src/main/java/com/example/messagefallback/MessageController.java`:

```java
package com.example.messagefallback;

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
public class MessageController {

    private final MessageSource messages;

    public MessageController(MessageSource messages) {
        this.messages = messages;
    }

    @GetMapping("/messages/hello")
    public Map<String, String> hello(
            @RequestParam(defaultValue = "visitor") String name,
            Locale locale) {

        String text = messages.getMessage(
                "ui.hello",
                new Object[]{name},
                "Hello, {0}!",
                locale
        );
        return Map.of("message", text);
    }

    @GetMapping("/messages/base-only")
    public Map<String, String> baseOnly(Locale locale) {
        String text = messages.getMessage(
                "ui.baseOnly",
                null,
                "Information not available",
                locale
        );
        return Map.of("message", text);
    }

    @GetMapping("/messages/unknown")
    public Map<String, String> unknown(Locale locale) {
        String text = messages.getMessage(
                "ui.notProvided",
                null,
                "Information not available",
                locale
        );
        return Map.of("message", text);
    }

    @PostMapping(
        path = "/signup",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Map<String, Object>> signup(
            @Valid @RequestBody SignupInput input) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of(
                        "name", input.name(),
                        "age", input.age()
                ));
    }
}
```

Ở đây, ba GET endpoints không chấp nhận arbitrary message code từ client; ứng dụng kiểm soát keys cần hiển thị. Một “lookup mọi key” endpoint không nên để public vì có thể làm lộ messages nội bộ.

### 9.9. Exception advice: validation và parser errors

`src/main/java/com/example/messagefallback/ApiErrorAdvice.java`:

```java
package com.example.messagefallback;

import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import org.springframework.context.MessageSource;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorAdvice {

    private final MessageSource messages;

    public ApiErrorAdvice(MessageSource messages) {
        this.messages = messages;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalid(
            MethodArgumentNotValidException exception,
            Locale locale) {

        List<FieldIssue> fields = exception.getBindingResult()
                .getAllErrors()
                .stream()
                .map(error -> toIssue(error, locale))
                .sorted(Comparator
                        .comparing(FieldIssue::field)
                        .thenComparing(FieldIssue::code))
                .toList();

        String summary = messages.getMessage(
                "api.validation",
                null,
                "Invalid input",
                locale
        );

        return ResponseEntity.badRequest()
                .body(new ApiError("VALIDATION_ERROR", summary, fields));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException exception,
            Locale locale) {

        String summary = messages.getMessage(
                "api.invalidJson",
                null,
                "Cannot read the request JSON",
                locale
        );

        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_JSON", summary, List.of()));
    }

    private FieldIssue toIssue(ObjectError error, Locale locale) {
        String field = error instanceof FieldError fieldError
                ? fieldError.getField()
                : "";

        String code = Objects.toString(
                error.getCode(), "invalid"
        );

        // ObjectError/FieldError chứa toàn bộ codes và default.
        String message = messages.getMessage(error, locale);
        return new FieldIssue(field, code, message);
    }
}
```

`getAllErrors()` lấy cả `FieldError` và `ObjectError` (class-level validation). `getMessage(error, locale)` tận dụng danh sách error codes, arguments và default của error. `messages.getMessage("api.validation",..., "Invalid input",locale)` có fallback rõ ràng nếu một ứng dụng khác chưa cấu hình summary key.

Để trả lỗi an toàn, adapter không phản chiếu `FieldError#getRejectedValue()`, raw exception message hoặc stack trace. Chúng có thể chứa dữ liệu cá nhân, token, SQL hoặc cấu trúc Java nội bộ.

## 10. Gửi request và quan sát fallback

Khởi chạy sau khi tạo Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows:

```powershell
.\gradlew.bat bootRun
```

### 10.1. Có key tiếng Việt

```bash
curl -i 'http://localhost:8080/api/messages/hello?name=Lan' \
  -H 'Accept-Language: vi'
```

HTTP 200:

```json
{"message":"Xin chào, Lan!"}
```

### 10.2. Thiếu riêng bản vi nhưng base có key

```bash
curl -i 'http://localhost:8080/api/messages/base-only' \
  -H 'Accept-Language: vi'
```

HTTP 200:

```json
{"message":"This text is available only in the base bundle"}
```

### 10.3. Key không có ở bất cứ bundle nào

```bash
curl -i 'http://localhost:8080/api/messages/unknown' \
  -H 'Accept-Language: vi'
```

HTTP 200:

```json
{"message":"Information not available"}
```

Đây là **explicit default**. Không phải “Spring đã tự dịch key còn thiếu”.

### 10.4. Lỗi validation với bản dịch tiếng Việt chưa đủ

```bash
curl -i -X POST 'http://localhost:8080/api/signup' \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: vi' \
  -d '{"name":" ","age":16}'
```

HTTP **400 Bad Request**:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Dữ liệu không hợp lệ",
  "fields": [
    {
      "field": "age",
      "code": "Min",
      "message": "Age must be at least 18"
    },
    {
      "field": "name",
      "code": "NotBlank",
      "message": "Tên không được bỏ trống"
    }
  ]
}
```

Phần tiếng Anh ở `age` là **kết quả cố ý minh họa thiếu dịch**; trong sản phẩm, nên thêm key `Min.signupInput.age` vào `messages_vi.properties` và cập nhật tests.

### 10.5. JSON không parse được

```bash
curl -i -X POST 'http://localhost:8080/api/signup' \
  -H 'Content-Type: application/json' \
  -H 'Accept-Language: vi' \
  -d '{"name":"Lan","age":'
```

HTTP 400 với `code=INVALID_JSON`, thông báo “Không thể đọc JSON của yêu cầu”. Đây là lỗi **deserialization**, không phải `@Min(18)` violation.

## 11. MockMvc + MessageSource tests

Tệp `src/test/java/com/example/messagefallback/MessageFallbackTest.java`:

```java
package com.example.messagefallback;

import java.util.Locale;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.MessageSource;
import org.springframework.context.NoSuchMessageException;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MessageFallbackTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    MessageSource messages;

    private static final Locale VI = Locale.forLanguageTag("vi");

    @Test
    void availableVietnameseKeyIsUsed() throws Exception {
        mvc.perform(get("/api/messages/hello")
                .param("name", "Lan")
                .header("Accept-Language", "vi"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("Xin chào, Lan!"));
    }

    @Test
    void englishHeaderUsesBaseEnglish() throws Exception {
        mvc.perform(get("/api/messages/hello")
                .param("name", "Lan")
                .header("Accept-Language", "en"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("Hello, Lan!"));
    }

    @Test
    void missingVietnameseKeyFallsBackToBaseBundle()
            throws Exception {

        mvc.perform(get("/api/messages/base-only")
                .header("Accept-Language", "vi"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("This text is available only in the base bundle"));
    }

    @Test
    void missingKeyEverywhereUsesExplicitDefault() throws Exception {
        mvc.perform(get("/api/messages/unknown")
                .header("Accept-Language", "vi"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("Information not available"));
    }

    @Test
    void strictMissingKeyThrowsNoSuchMessageException() {
        assertThrows(
                NoSuchMessageException.class,
                () -> messages.getMessage("ui.notProvided", null, VI)
        );
    }

    @Test
    void nullableExplicitDefaultReturnsNull() {
        String result = messages.getMessage(
                "ui.notProvided", null, (String) null, VI
        );
        assertNull(result);
    }

    @Test
    void explicitDefaultIsReturnedForAbsentKey() {
        String result = messages.getMessage(
                "ui.notProvided", null, "Safe fallback", VI
        );
        assertEquals("Safe fallback", result);
    }

    @Test
    void validationWithMissingViTranslationFallsBackToEnglish()
            throws Exception {

        mvc.perform(post("/api/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "vi")
                .content("""
                        {"name":" ","age":16}
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.message")
                    .value("Dữ liệu không hợp lệ"))
            .andExpect(jsonPath("$.fields[0].field").value("age"))
            .andExpect(jsonPath("$.fields[0].code").value("Min"))
            .andExpect(jsonPath("$.fields[0].message")
                    .value("Age must be at least 18"))
            .andExpect(jsonPath("$.fields[1].field").value("name"))
            .andExpect(jsonPath("$.fields[1].code")
                    .value("NotBlank"))
            .andExpect(jsonPath("$.fields[1].message")
                    .value("Tên không được bỏ trống"));
    }

    @Test
    void unsupportedLocaleUsesDefaultEnglish() throws Exception {
        mvc.perform(get("/api/messages/hello")
                .param("name", "Lan")
                .header("Accept-Language", "fr"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message")
                    .value("Hello, Lan!"));
    }

    @Test
    void malformedJsonHasASeparateLocalizedError() throws Exception {
        mvc.perform(post("/api/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "vi")
                .content("{\"name\":\"Lan\",\"age\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"))
            .andExpect(jsonPath("$.message")
                    .value("Không thể đọc JSON của yêu cầu"));
    }

    @Test
    void validSignupPasses() throws Exception {
        mvc.perform(post("/api/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .header("Accept-Language", "vi")
                .content("""
                        {"name":"Lan","age":24}
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

**Kỳ vọng** có 11 tests thành công khi môi trường có Java 17, wrapper và dependencies tương ứng. Việc cung cấp mã nguồn và expected results **không** đồng nghĩa với việc Gradle/JUnit đã được chạy trong bước soạn bài.

Tests chứng minh khác biệt giữa:

- Có key vi → tiếng Việt.
- Key vi thiếu, base có → English.
- Key thiếu hoàn toàn, có default → text an toàn.
- Key thiếu hoàn toàn, strict overload → `NoSuchMessageException`.
- Default null → kết quả null.
- Locale client không được hỗ trợ → locale mặc định.
- Input validation vẫn HTTP 400 với machine codes bất biến.
- JSON malformed đi qua một exception khác.

Advice đã **sort errors theo field và code**, nên test có thể dựa vào thứ tự `age` trước `name`. Nếu bỏ sort, thứ tự violations từ provider không được cam kết; khi đó cần test theo danh sách field/code thay vì index.

## 12. Translation coverage: đừng để runtime fallback che giấu vấn đề

Một test đơn giản:

```java
assertEquals(
        "Age must be at least 18",
        messages.getMessage("Min.signupInput.age", null, VI)
);
```

**không** chứng minh khóa đó đã được dịch sang vi. Nó có thể chỉ đang lấy từ `messages.properties`.

Muốn đo completeness, phải kiểm tra **locale bundle cụ thể**, không dùng API đã bật fallback để đo missing keys.

### 12.1. Ví dụ test kiểm tra thiếu khóa

Snippet JUnit dưới đây **không thuộc 11 tests ở phần trên**; nếu chạy với file `messages_vi.properties` của bài, nó **cố ý fail** để cảnh báo các bản dịch còn thiếu:

```java
@Test
void allPublicKeysMustBeTranslatedToVietnamese() throws Exception {
    Properties base = new Properties();
    Properties vi = new Properties();

    try (Reader reader = new InputStreamReader(
            Objects.requireNonNull(getClass()
                    .getResourceAsStream("/messages.properties")),
            StandardCharsets.UTF_8)) {
        base.load(reader);
    }

    try (Reader reader = new InputStreamReader(
            Objects.requireNonNull(getClass()
                    .getResourceAsStream("/messages_vi.properties")),
            StandardCharsets.UTF_8)) {
        vi.load(reader);
    }

    List<String> missing = base.stringPropertyNames()
            .stream()
            .filter(key -> key.startsWith("ui.")
                    || key.startsWith("api.")
                    || key.startsWith("Min."))
            .filter(key -> !vi.containsKey(key)
                    || vi.getProperty(key).isBlank())
            .sorted()
            .toList();

    assertTrue(missing.isEmpty(),
            "Missing vi translations: " + missing);
}
```

Cần imports `java.util.Properties`, `java.util.Objects`, `java.util.List`, `java.io.Reader`, `java.io.InputStreamReader`, `java.nio.charset.StandardCharsets` và JUnit `assertTrue`. Trong codebase thật, có thể viết module i18n-lint riêng để duy trì danh sách keys public-facing bắt buộc phải dịch.

### 12.2. So sánh placeholders

```properties
# Base
ui.invite=Invite {0} to {1}

# Vi thiếu thông tin (sai về nội dung)
ui.invite=Mời tham gia
```

Key tồn tại nhưng mất `{0}`/`{1}`. CI nên so sánh tập placeholder indices, các type format và escaping rules của `MessageFormat`. Lỗi này không tự biểu hiện dưới dạng `NoSuchMessageException`.

### 12.3. Định nghĩa severity theo loại message

- **Bắt buộc mọi ngôn ngữ:** validation errors và những lời hướng dẫn UI cốt lõi.
- **Có thể fallback tạm thời:** nội dung ít xuất hiện nhưng vẫn có base English rõ ràng.
- **Internal-only:** log messages và diagnostics không hiển thị cho người dùng; có thể không cần mọi locale.
- **Security-sensitive:** messages không được chứa secrets hoặc chi tiết hạ tầng, kể cả ở default fallback.

Tránh biến linter quá thô thành một nguyên nhân chặn release không cần thiết; phân loại keys và locale requirements theo sản phẩm.

## 13. Thiết kế fallback cho production

Một chiến lược có thể kết hợp các lớp:

1. **Base bundle đầy đủ** làm nền, ví dụ English.
2. **Locale bundles** có những message thực sự được dịch.
3. **Safe explicit defaultMessage** cho error summary/unknown code tại boundary.
4. **Strict translation coverage tests** cho user-facing keys bắt buộc.
5. **Log/metrics** cho missing codes (không log raw user input nhạy cảm).
6. **Stable error codes** độc lập với ngôn ngữ.
7. **Thông báo parser/error nội bộ được kiểm soát**, không đẩy raw exception messages tới client.

### 13.1. Không trả code thô cho frontend

Nếu bật `useCodeAsDefaultMessage` production, người dùng có thể thấy:

```text
validation.user.internalOwnerId.missing
```

Nó khó hiểu và có thể tiết lộ tên field nội bộ. Chỉ bật trong môi trường debug có kiểm soát nếu thực sự cần; production nên có bản dịch hoặc safe fallback.

### 13.2. Không để lỗi dịch làm đổi 400 thành 500

Một `@Min` vi phạm phải trả lỗi input (thường HTTP 400) khi client gửi dữ liệu không hợp lệ. Nếu error adapter gọi `getMessage("Min.signupInput.age",null,locale)` ở dạng strict và thiếu key trong mọi bundle, lỗi tra dịch có thể làm **mất response validation ban đầu**.

Kết hợp base bundle đầy đủ và error adapter có default hợp lý. Đồng thời ghi nhận translation gap trong CI để không che giấu chất lượng kém.

### 13.3. Không gửi dữ liệu nhạy cảm trong default

`FieldError#getRejectedValue()` có thể chứa password, email, token hoặc dữ liệu cá nhân. `exception.getMessage()` có thể chứa JSON/raw SQL/class paths. Không sử dụng chúng làm default message gửi client:

```java
// Không nên làm:
messages.getMessage(
        "api.error",
        null,
        exception.getMessage(),
        locale
);
```

Thay vào đó dùng văn bản đã được kiểm soát:

```java
messages.getMessage(
        "api.error",
        null,
        "Unable to complete the request",
        locale
);
```

Nếu message parameters chứa user input để hiển thị trên HTML, view cần escape để chống XSS; `MessageSource` không phải HTML sanitizer.

## 14. ProblemDetail và missing translation

Spring Framework 6 có `ProblemDetail` (RFC 9457) và `ResponseEntityExceptionHandler`. Khi dùng `ErrorResponse`, framework hỗ trợ tra MessageSource cho các fields như `type`, `title`, `detail` theo những code riêng của exception.

Một API tự dùng `ApiError` như ví dụ vẫn hợp lệ; nếu dùng ProblemDetail, cần xác định rõ ai chịu trách nhiệm gán localized title/detail và code nào là public contract.

Ví dụ **phương thức minh họa**, không nằm trong source runnable:

```java
@ExceptionHandler(SomeBusinessException.class)
ResponseEntity<ProblemDetail> conflict(
        SomeBusinessException error,
        Locale locale) {

    ProblemDetail detail = ProblemDetail.forStatus(409);
    detail.setTitle(messages.getMessage(
            "problem.conflict.title", null, "Conflict", locale));
    detail.setDetail(messages.getMessage(
            "problem.conflict.detail",
            null,
            "Operation conflicts with the current state",
            locale
    ));

    return ResponseEntity.status(409).body(detail);
}
```

Snippet giả định `SomeBusinessException` và bean `messages` đã được định nghĩa. Cần import `org.springframework.http.ProblemDetail`, `ResponseEntity` và các annotation Spring.

Trong Spring MVC 6.1+, `HandlerMethodValidationException` còn phân biệt lỗi input HTTP 400 và return contract error HTTP 500 thông qua `isForReturnValue()`. Một bản dịch thiếu ở response error 500 không biến nó thành lỗi client; hãy giữ status semantics riêng và fallback message an toàn.

## 15. Những lỗi phổ biến

**1. Nghĩ thiếu key tiếng Việt luôn ném NoSuchMessageException.** Nếu base bundle có mã, Spring có thể trả English.

**2. Nghĩ explicit default được dùng ngay khi file vi thiếu key.** Nếu key vẫn được resolve từ base/parent/alternate codes, default tường minh không được sử dụng.

**3. Dùng strict overload trong mọi @ExceptionHandler.** Một key thiếu làm exception handler có thể ném thêm exception và đánh mất HTTP 400 ban đầu.

**4. Truyền default=null và dùng kết quả làm chuỗi không-null.** Overload cho phép trả null; xử lý rõ trong response schema.

**5. Chỉ tạo messages_vi.properties mà không có base.** Spring Boot auto-config có thể không phát hiện MessageSource như mong muốn.

**6. Tưởng fallback-to-system-locale=false tắt base fallback.** Nó chỉ tránh thử locale của host server.

**7. Bật useCodeAsDefaultMessage trên parent MessageSource.** Có thể làm một FieldError nhiều codes trả raw code trước khi fallback khác được tìm.

**8. Chỉ resolve FieldError#getCode().** Bỏ qua codes cụ thể theo field và arguments.

**9. Tin getDefaultMessage() luôn đúng locale request.** Nó có thể do Jakarta MessageInterpolator tính trước; Spring MessageSource có thể dịch thêm hoặc dùng bản fallback.

**10. Quên @NotNull khi dùng @Min.** `@Min` thường coi null hợp lệ, do đó thiếu field vẫn có thể không vi phạm `@Min`.

**11. Không gắn @Valid tại controller boundary.** Constraint trên DTO không mặc nhiên tự chạy trong mọi đường deserialization.

**12. Coi JSON malformed là Bean Validation error.** Chưa có object để validate; xử lý `HttpMessageNotReadableException` riêng.

**13. Bỏ ObjectError.** `getAllErrors()` giữ cả lỗi class-level và field-level.

**14. Coi key giá trị rỗng là missing key.** Lookup có thể trả chuỗi rỗng; cần lint nội dung.

**15. Dùng MessageSource fallback để đo coverage translation.** Base bundle che giấu việc thiếu locale key; kiểm tra files cụ thể.

**16. Bỏ sót placeholders khi dịch.** Key vẫn tồn tại nhưng message mất dữ liệu hoặc sai định dạng.

**17. Dùng Locale.setDefault(...) trong mỗi request.** Là trạng thái toàn JVM, gây nhiễu các request song song.

**18. Không test vi vs vi-VN và en vs en-US.** Locale matching phụ thuộc resolver configuration và supported locales.

**19. Trả raw rejectedValue/parser exception làm default message.** Có thể lộ dữ liệu riêng tư và chi tiết framework.

**20. Frontend phân nhánh bằng literal translated message.** Ngôn ngữ thay đổi làm vỡ logic; dùng stable error code và field.

## 16. Checklist triển khai

1. Có base `messages.properties` và locale bundles như `messages_vi.properties`.
2. Cấu hình đúng UTF-8, basename và system-locale fallback.
3. Xác định supported locales và default locale; test headers thực tế.
4. Phân biệt locale fallback, bundle fallback, error-code fallback và explicit default.
5. Dùng overload có default cho các thông điệp public có thể thiếu ở runtime.
6. Dùng strict overload trong CI/startup để kiểm tra key bắt buộc.
7. Không để code thô trở thành fallback production.
8. Dùng `getMessage(ObjectError/FieldError,locale)` nếu cần giải nhiều codes/arguments.
9. Dùng `getAllErrors()` để không mất lỗi class-level.
10. Tách `messages*.properties` của Spring và `ValidationMessages*.properties` của Jakarta provider.
11. Không phản chiếu rejected value hoặc exception message nhạy cảm.
12. Trả stable error codes độc lập localized text và giữ HTTP status đúng.
13. Viết MockMvc tests cho vi/en, base-only, unknown key, strict exception, null default, validation và parser failure.
14. Lint trực tiếp locale bundle để phát hiện key thiếu/blank.
15. So sánh placeholders `{0}`/`{1}`, escaping và nội dung message.
16. Cấu hình caching HTTP đúng nếu response phụ thuộc `Accept-Language` (cân nhắc `Vary: Accept-Language`).
17. Khi nâng Spring Boot/Framework, kiểm tra API/bundle behavior bằng integration tests.
18. Đưa missing translation vào QA/observability thay vì im lặng mãi mãi.

**Kết luận:** thiếu một bản dịch locale không đồng nghĩa không có message. Spring có thể tìm bản ở base bundle, thử các error codes khác, tra parent hoặc dùng explicit default. Nên giữ **fallback runtime an toàn** để không làm mất response quan trọng và **translation coverage tests** để phát hiện thiếu bản dịch trước production. `MessageSource` giúp chọn thông điệp; `LocaleResolver` giúp chọn ngôn ngữ; `MessageInterpolator` của Jakarta Validation xử lý constraint templates; trách nhiệm của từng lớp phải rõ ràng.

## Tài liệu tham khảo

- [Spring Framework — MessageSource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/MessageSource.html): overload với defaultMessage, strict overload và MessageSourceResolvable.
- [Spring Framework — AbstractMessageSource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/context/support/AbstractMessageSource.html): useCodeAsDefaultMessage, parent, multiple codes.
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/reference/features/internationalization.html): base bundle, basename và fallback-to-system-locale.
- [Spring Framework — MVC Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): ErrorResponse, ProblemDetail và i18n.
- [Spring Framework — Locale Resolver](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/localeresolver.html): Accept-Language và default locale.
- [Jakarta Validation 3.0 specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): message interpolation và constraint validation.
