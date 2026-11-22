# MessageInterpolator và cơ chế nội suy thông báo trong Spring Framework

## 1. Message interpolation là gì?

Khi kiểm tra dữ liệu bằng Jakarta Bean Validation, một constraint có thể khai báo thông báo lỗi dạng văn bản hoặc **mẫu thông báo** (message template, còn gọi là message descriptor). **`MessageInterpolator`** là thành phần biến mẫu đó thành chuỗi dễ đọc để trả cho người dùng. Nó giải mã khóa trong resource bundle, thay giá trị thuộc tính annotation, xử lý biểu thức khi được bật và chọn ngôn ngữ phù hợp.

Ví dụ:

```java
@Size(min = 4, max = 12,
      message = "{order.code.size}")
private String code;
```

Giả sử trong `ValidationMessages_vi.properties` có:

```properties
order.code.size=Mã đơn phải có từ {min} đến {max} ký tự
```

Với `Locale` tiếng Việt, khi `code = "ab"`, constraint thất bại và thông báo được nội suy thành:

```text
Mã đơn phải có từ 4 đến 12 ký tự
```

Có hai hành động khác nhau:

1. **Kiểm tra quy tắc**: `@Size` xác định độ dài `"ab"` là 2, nhỏ hơn `min = 4`.
2. **Nội suy thông báo**: `MessageInterpolator` lấy template `"{order.code.size}"`, tìm bản dịch và thay `{min}`, `{max}` bằng thuộc tính của `@Size`.

Thành phần nội suy **không quyết định một giá trị hợp lệ hay không**, không dịch tên trường tự động, không sửa dữ liệu và không tự tạo định dạng HTTP. Việc tạo HTTP 400 và cấu trúc JSON là trách nhiệm của lớp xử lý web/exception.

Phạm vi bài này: Jakarta Validation 3.x, Spring Framework 6.x và Spring Boot 3.x, Java 17+. Các ví dụ sử dụng package `jakarta.validation.*`; dự án Spring Boot 2.x dùng namespace `javax.validation.*`.

## 2. Các thuật ngữ và thành phần cần phân biệt

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Constraint | `@Size(min=4, max=12)` | Quy tắc dữ liệu |
| Message descriptor/template | `"{order.code.size}"` | Mẫu thông báo trước nội suy |
| User resource bundle | `ValidationMessages_vi.properties` | Bản dịch do ứng dụng cung cấp |
| Provider bundle | Thông báo mặc định của Hibernate Validator | Thông báo có sẵn cho constraint tiêu chuẩn |
| Constraint attribute | `min=4`, `max=12` | Giá trị dùng cho `{min}` và `{max}` |
| Message parameter | `{order.code.size}`, `{min}` | Khóa bundle hoặc tên thuộc tính constraint |
| EL expression | `${validatedValue}` | Biểu thức Jakarta Expression Language |
| MessageInterpolator | `jakarta.validation.MessageInterpolator` | Nội suy descriptor theo context và locale |
| ConstraintViolation | `getMessageTemplate()`, `getMessage()` | Chứa cả template gốc và thông báo đã nội suy |
| Spring MessageSource | `messages.properties` và `MessageSource` | Hệ thống giải mã thông báo/i18n của Spring, có thể tích hợp vào Bean Validation |

Đường đi thông thường:

```text
@Size(message="{order.code.size}", min=4, max=12)
                |
                v
ConstraintValidator xác định vi phạm
                |
                v
MessageInterpolator(template, context, locale)
                |
      +---------+----------+
      |                    |
ValidationMessages    thuộc tính @Size
      |                    |
      +---------+----------+
                |
                v
"Mã đơn phải có từ 4 đến 12 ký tự"
                |
                v
ConstraintViolation#getMessage()
                |
                v
Spring FieldError / BindingResult / API response
```

Chú ý sự khác nhau giữa hai API:

- `violation.getMessageTemplate()` trả về template, ví dụ `"{order.code.size}"`.
- `violation.getMessage()` trả về thông báo đã nội suy, ví dụ `"Mã đơn phải có từ 4 đến 12 ký tự"`.
- `violation.getPropertyPath()` mô tả vị trí lỗi; nó độc lập với ngôn ngữ và nội dung thông báo.

## 3. Quy tắc nội suy mặc định của Jakarta Validation

Để hiểu chính xác `MessageInterpolator`, cần biết thứ tự xử lý chuẩn. Với descriptor như `"{order.code.size}"`, provider dùng thuật toán sau:

1. **Tìm trong bundle của ứng dụng** có basename `ValidationMessages` theo locale. Nếu `{key}` tồn tại, thay bằng giá trị của key; thực hiện **đệ quy** với các key có trong giá trị vừa chèn cho đến khi không còn phép thay thế qua bundle này.
2. **Tìm trong bundle tích hợp của provider** (ví dụ các thông báo mặc định của Hibernate Validator). Những thay thế từ bundle provider ở bước này **không lặp đệ quy**.
3. Nếu bước 2 có phép thay thế, **chạy lại bước 1** để bundle ứng dụng có cơ hội ghi đè/định nghĩa khóa được nhắc đến trong thông báo provider.
4. Thay các tham số còn lại có tên trùng thuộc tính của annotation constraint, ví dụ `{min}` thành `4`, `{max}` thành `12`. Giá trị thuộc tính được chèn ở bước này **không được nội suy tiếp**.
5. Đánh giá các biểu thức `${...}` bằng Jakarta Expression Language (EL) trong mức tính năng được phép.

Thuật toán đặt **bundle của ứng dụng trước bundle provider** để có thể tùy biến cả thông báo của constraint tiêu chuẩn. Việc thay tham số `{...}` có thứ tự ưu tiên trước EL `${...}` nhằm tương thích với các phiên bản Bean Validation cũ; cần để ý điểm này nếu dùng cú pháp có tên trùng nhau.

### 3.1. Minh họa từng bước với key lồng nhau

```java
@Size(
    min = 4,
    max = 12,
    message = "{order.code.size}"
)
String code;
```

```properties
# ValidationMessages_vi.properties
order.code.label=Mã đơn
order.code.size={order.code.label} phải có từ {min} đến {max} ký tự
```

Quá trình:

```text
{order.code.size}
  -> {order.code.label} phải có từ {min} đến {max} ký tự
  -> Mã đơn phải có từ {min} đến {max} ký tự
  -> Mã đơn phải có từ 4 đến 12 ký tự
```

Hai lần thay `{order...}` đầu là tìm key đệ quy trong bundle. Thay `{min}` và `{max}` sau đó là lấy thuộc tính của `@Size` (khi bundle không cung cấp các key cùng tên). Điều này cho phép một message template dùng lại cho nhiều annotation cấu hình khác nhau.

**Tránh tạo vòng tham chiếu** giữa các key resource bundle, chẳng hạn `a={b}` và `b={a}`. Nên thiết kế chuỗi tham chiếu ngắn, rõ ràng; kiểm thử thông báo sau khi thêm key mới.

### 3.2. Phân biệt các dạng cú pháp

| Descriptor | Cách hiểu |
| --- | --- |
| `"Mã không hợp lệ"` | Chuỗi cố định; không cần tra bundle |
| `"{order.code.size}"` | Tra key từ bundle theo locale |
| `"Từ {min} tới {max}"` | Tham số có thể đến từ thuộc tính constraint |
| `"Giá trị là ${validatedValue}"` | Jakarta EL khi được hỗ trợ/bật |
| `"order.code.size"` | Chuỗi literal; thiếu cặp ngoặc `{}` nên không được tra bundle như key |

Các ký tự có ý nghĩa đặc biệt trong message descriptor cần escape nếu muốn xuất hiện nguyên văn: `\{`, `\}`, `\$` và `\\`. Khi viết các descriptor trong **Java string** hoặc **file `.properties`**, còn phải tuân theo quy tắc escape riêng của Java/Properties; vì vậy hãy kiểm tra giá trị runtime thực tế nếu cần hiển thị ngoặc hoặc dấu `$` nguyên văn.

## 4. Xây dựng ví dụ Spring Boot có hai ngôn ngữ

Ta tạo API `POST /orders` nhận mã đơn gồm 4–12 ký tự. Gửi mã `"ab"` với `Accept-Language: vi` sẽ nhận lỗi tiếng Việt; với `Accept-Language: en` sẽ nhận lỗi tiếng Anh. Ngoài thông báo theo locale, ví dụ còn minh họa key lồng nhau và tham số `{min}`, `{max}`.

### 4.1. Dependency và cấu trúc dự án

Sử dụng Gradle/Groovy với Java 17 và Spring Boot 3.3.x. Ví dụ `build.gradle` có thể chạy độc lập khi dự án đã có Gradle wrapper:

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

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-validation` cung cấp Jakarta Validation API, Hibernate Validator (provider) và tích hợp cần thiết. Chỉ có annotation API mà không có provider sẽ không tạo được hệ thống validation thực tế. Spring Boot 3.3.x sử dụng Hibernate Validator 8.x theo dependency management của bản phát hành.

```text
src/
  main/
    java/com/example/interpolation/
      DemoApplication.java
      api/OrderRequest.java
      api/OrderController.java
      api/ValidationExceptionHandler.java
    resources/
      ValidationMessages.properties
      ValidationMessages_vi.properties
  test/
    java/com/example/interpolation/
      OrderApiValidationTest.java
```

### 4.2. DTO khai báo message template

Tệp `src/main/java/com/example/interpolation/api/OrderRequest.java`:

```java
package com.example.interpolation.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record OrderRequest(
    @NotBlank(message = "{order.code.required}")
    @Size(min = 4, max = 12, message = "{order.code.size}")
    String code
) {}
```

`@NotBlank` báo lỗi khi null/rỗng/chỉ khoảng trắng; `@Size` báo lỗi khi chuỗi không đúng độ dài (nó xem `null` là hợp lệ theo hợp đồng của constraint). Một input rỗng có thể vi phạm đồng thời hai constraint; đó là hành vi bình thường, không nên dựa vào thứ tự của các lỗi trong danh sách.

### 4.3. Khai báo bundle gốc và bản dịch

Tệp `src/main/resources/ValidationMessages.properties` là bundle mặc định (fallback), ở đây dùng tiếng Anh:

```properties
order.code.label=Order code
order.code.required=Order code must not be blank
order.code.size={order.code.label} must contain {min} to {max} characters
```

Tệp `src/main/resources/ValidationMessages_vi.properties`:

```properties
order.code.label=Mã đơn
order.code.required=Mã đơn không được để trống
order.code.size={order.code.label} phải có từ {min} đến {max} ký tự
```

Điểm cần nhớ:

- Tên mặc định là **`ValidationMessages`**, không phải `ValidationMessage` hay `messages`; phải đặt file trên classpath, thường là `src/main/resources`.
- Suffix locale đi sau basename, ví dụ `_vi`, `_en`, `_en_US`. Cơ chế fallback dựa trên `ResourceBundle` và cấu hình locale thực tế. Có file gốc giúp hành vi fallback rõ ràng.
- Nếu một key biến mất khỏi bản dịch Việt, hệ thống có thể dùng giá trị fallback (tùy chuỗi bundle được tìm thấy). Đừng để việc thiếu key chỉ được phát hiện sau khi deploy.
- `ValidationMessages*.properties` dùng cho nội suy Bean Validation. Bộ file `messages*.properties` mà Spring Boot thường dùng cho `MessageSource` là **một cơ chế riêng**, trừ khi bạn cấu hình cho chúng liên kết.
- Lưu file bằng UTF-8 và kiểm tra cách provider/JDK đọc properties trong môi trường thực tế; không chuyển mã dấu tiếng Việt thành ký tự hỏng.

### 4.4. Spring Boot application và controller

Tệp `src/main/java/com/example/interpolation/DemoApplication.java`:

```java
package com.example.interpolation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Tệp `src/main/java/com/example/interpolation/api/OrderController.java`:

```java
package com.example.interpolation.api;

import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    @PostMapping
    public ResponseEntity<Map<String, String>> create(
            @Valid @RequestBody OrderRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("code", request.code()));
    }
}
```

`@Valid` kích hoạt Bean Validation cho `@RequestBody` sau bước Jackson deserialize. Với Spring MVC dùng `LocalValidatorFactoryBean`, Spring có adapter `LocaleContextMessageInterpolator` để chuyển locale của `LocaleContextHolder` cho provider. Trong một HTTP request được xử lý bình thường, Spring MVC xác định locale theo `LocaleResolver`; cấu hình thông dụng dùng header `Accept-Language`. Điều này cho phép message được nội suy theo từng request thay vì thay đổi `Locale.setDefault(...)` cho toàn JVM.

Nếu khởi tạo validator riêng bằng `Validation.buildDefaultValidatorFactory()` **ngoài Spring**, thuật toán mặc định của Jakarta Validation sử dụng `Locale.getDefault()`, nên không thể mặc nhiên mong đợi nó đọc locale của HTTP request. Hãy phân biệt hai ngữ cảnh.

### 4.5. Định dạng lỗi HTTP

Tệp `src/main/java/com/example/interpolation/api/ValidationExceptionHandler.java`:

```java
package com.example.interpolation.api;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> handle(
            MethodArgumentNotValidException exception) {

        List<Map<String, String>> errors =
                exception.getBindingResult().getFieldErrors().stream()
                .map(this::toError)
                .toList();

        return ResponseEntity.badRequest()
                .body(Map.of("errors", errors));
    }

    private Map<String, String> toError(FieldError error) {
        return Map.of(
                "field", error.getField(),
                "message", Objects.toString(error.getDefaultMessage(), "")
        );
    }
}
```

Handler này chỉ minh họa **field violations**; ứng dụng thực tế có thể cần bổ sung `getGlobalErrors()` cho ràng buộc cấp lớp, xử lý lỗi deserialize (`HttpMessageNotReadableException`) và lỗi method validation. Lỗi `MethodArgumentNotValidException` là đường đi thường thấy khi `@Valid @RequestBody` vi phạm Bean Validation và không có `BindingResult` ngay sau tham số.

**Mối quan hệ với Spring:** `FieldError` được tạo từ violation, chứa các message code và default message. Lời gọi `error.getDefaultMessage()` trong ví dụ nhận thông báo đã nội suy của Bean Validation. Ở tầng hiển thị khác, Spring `MessageSource` còn có thể tra `MessageSourceResolvable`/mã lỗi như `Size.orderRequest.code` để chọn bản dịch của tầng giao diện. Hai quá trình đều có thể ảnh hưởng chuỗi người dùng thấy, nhưng không phải cùng một bước.

### 4.6. Gửi request và dự đoán kết quả

Khởi động:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`.

Gửi request lỗi, yêu cầu tiếng Việt:

```bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"code":"ab"}'
```

Kỳ vọng HTTP `400 Bad Request`, body có nội dung (thứ tự trường trong JSON không được bảo đảm):

```json
{
  "errors": [
    {
      "field": "code",
      "message": "Mã đơn phải có từ 4 đến 12 ký tự"
    }
  ]
}
```

Đổi sang tiếng Anh:

```bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -H "Accept-Language: en" \
  -d '{"code":"ab"}'
```

Kỳ vọng HTTP `400 Bad Request` với message:

```text
Order code must contain 4 to 12 characters
```

Gửi input hợp lệ:

```bash
curl -i -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -d '{"code":"ORD-2048"}'
```

Kỳ vọng HTTP `201 Created` và body `{"code":"ORD-2048"}`. Khi dữ liệu hợp lệ, không có `ConstraintViolation` để cần nội suy thông báo lỗi.

## 5. Kiểm thử locale và nội suy tự động

Tệp `src/test/java/com/example/interpolation/OrderApiValidationTest.java`:

```java
package com.example.interpolation;

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
class OrderApiValidationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void vietnameseMessageInterpolatesKeyAndConstraintAttributes()
            throws Exception {

        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                .content("{\"code\":\"ab\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].field").value("code"))
            .andExpect(jsonPath("$.errors[0].message")
                .value("Mã đơn phải có từ 4 đến 12 ký tự"));
    }

    @Test
    void englishMessageUsesDefaultBundle() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.ACCEPT_LANGUAGE, "en")
                .content("{\"code\":\"ab\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errors[0].message")
                .value("Order code must contain 4 to 12 characters"));
    }

    @Test
    void validOrderPassesValidation() throws Exception {
        mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"code\":\"ORD-2048\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.code").value("ORD-2048"));
    }
}
```

Chạy:

```bash
./gradlew test
```

Ba bài test tách bạch: nội suy key lồng nhau + `{min}`/`{max}` trong locale Việt, fallback tiếng Anh và request hợp lệ. Chúng xác minh hành vi qua điểm vào HTTP thực tế, nơi `Accept-Language` có ý nghĩa. Nếu một test locale thất bại, kiểm tra trước tiên tên file bundle, vị trí classpath và cấu hình `LocaleResolver`/validator mà dự án đang dùng.

Để quan sát template gốc và kết quả sau nội suy bằng API Jakarta, có thể lấy từ cùng một violation như sau (đoạn minh họa giả sử biến `validator` kiểu `jakarta.validation.Validator` đang được cung cấp và locale đã được xác định):

```java
var violations = validator.validate(new OrderRequest("ab"));
for (var violation : violations) {
    System.out.println(violation.getMessageTemplate());
    System.out.println(violation.getMessage());
}
```

Trong ví dụ này, một violation `@Size` có template `{order.code.size}`; chuỗi `getMessage()` phụ thuộc vào locale mà interpolator đang dùng. Không assert chuỗi bản dịch khi test không cố định được locale.

## 6. Locale được quyết định ở đâu?

### 6.1. Jakarta Validation thuần

Theo thuật toán chuẩn, nếu gọi trực tiếp:

```java
var factory = jakarta.validation.Validation
        .buildDefaultValidatorFactory();
var validator = factory.getValidator();
```

thì mặc định dùng `Locale.getDefault()` khi không có locale được truyền tường minh. Không có tham số `locale` ở `Validator#validate(...)`; locale được chọn bởi `MessageInterpolator` ở thời điểm tạo thông báo, không phải bởi phương thức `validate(...)`.

Interface `jakarta.validation.MessageInterpolator` khai báo hai overload:

```java
String interpolate(
        String messageTemplate,
        MessageInterpolator.Context context);

String interpolate(
        String messageTemplate,
        MessageInterpolator.Context context,
        java.util.Locale locale);
```

`Context` có `getConstraintDescriptor()` để đọc annotation metadata và `getValidatedValue()` để truy cập giá trị đang được kiểm tra. Phương thức có `Locale` cho phép wrapper chỉ định ngôn ngữ ở từng lần nội suy. Các implementation phải **thread-safe** vì có thể được dùng chung cho nhiều validator và request.

### 6.2. Spring MVC và Accept-Language

Spring MVC sử dụng `LocaleResolver` để tìm locale request; ví dụ với resolver dựa trên header, `Accept-Language: vi` dẫn đến `Locale` tiếng Việt trong `LocaleContextHolder`. Khi sử dụng `LocalValidatorFactoryBean` được Spring cấu hình chuẩn, `LocaleContextMessageInterpolator` bọc interpolator của provider và truyền locale hiện hành.

Đường đi tổng quát:

```text
HTTP Accept-Language
    -> Spring LocaleResolver
    -> LocaleContextHolder
    -> LocaleContextMessageInterpolator
    -> provider MessageInterpolator (được truyền Locale)
    -> ConstraintViolation#getMessage()
```

Không dùng `Locale.setDefault(...)` trong controller để đổi ngôn ngữ từng request: nó thay đổi trạng thái JVM dùng chung, dễ gây lẫn ngôn ngữ giữa các request song song. Nếu dùng validation trong scheduled job/message listener, cần thiết kế locale rõ ràng cho luồng đó; đừng giả định có HTTP context.

## 7. Tích hợp Spring MessageSource với Bean Validation

Nhiều ứng dụng Spring Boot có sẵn:

```text
src/main/resources/messages.properties
src/main/resources/messages_vi.properties
```

Spring Boot thường auto-configure `MessageSource` cho basename `messages` khi tìm thấy bundle gốc `messages.properties` (có thể đổi bằng `spring.messages.basename`). Trong khi đó, **Jakarta Bean Validation** theo mặc định tra `ValidationMessages.properties`. Chỉ đổi `spring.messages.basename` không phải là bảo đảm mọi `@Size(message="{...}")` sẽ dùng đúng các file i18n của Bean Validation trong mọi cấu hình.

Nếu muốn cùng dùng `MessageSource` của Spring, có thể cấu hình `LocalValidatorFactoryBean#setValidationMessageSource(...)`. Ví dụ **thay thế** đường mặc định dựa trên `ValidationMessages` ở ứng dụng có `messages.properties`:

```java
package com.example.interpolation;

import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationMessageSourceConfig {

    @Bean
    public LocalValidatorFactoryBean validator(MessageSource messageSource) {
        LocalValidatorFactoryBean factory =
                new LocalValidatorFactoryBean();
        factory.setValidationMessageSource(messageSource);
        return factory;
    }
}
```

Đoạn này thuộc **phương án cấu hình riêng**, không cần thêm khi chạy ví dụ ở mục 4–5. Nếu áp dụng, hãy chuyển các key tùy chỉnh sang các bundle `messages*.properties` tương ứng, kiểm tra validator được MVC thực sự sử dụng và kiểm thử lại `Accept-Language`. Để không làm mất fallback thông báo provider, `MessageSource` nên cho phép trả về không tìm thấy key; đừng bật `useCodeAsDefaultMessage` cho nguồn này.

`LocalValidatorFactoryBean` còn có `setMessageInterpolator(...)` để cắm một interpolator tùy chỉnh. Theo API Spring, **không cấu hình đồng thời `setValidationMessageSource(...)` và `setMessageInterpolator(...)` trên cùng factory** vì chúng là hai cách lựa chọn cơ chế nội suy. Nếu cần cả behavior đặc biệt và nguồn bản dịch Spring, hãy xây dựng/decorate interpolator phù hợp thay vì lần lượt ghi đè hai setter.

Một quy tắc vận hành hữu ích là thống nhất **một nguồn key chuẩn** cho message validation, định rõ cách chọn locale rồi kiểm thử API bằng ít nhất hai locale.

## 8. Khi nào phải tự viết MessageInterpolator?

Thông thường **không cần** viết lại thuật toán nội suy tiêu chuẩn. Hãy ưu tiên:

1. Thay `message = "{custom.key}"` và thêm bundle theo ngôn ngữ nếu chỉ muốn đổi thông báo.
2. Dùng `setValidationMessageSource` nếu cần tái sử dụng Spring `MessageSource`.
3. Tùy chỉnh `LocaleResolver` hoặc chọn locale trong các tác vụ nền nếu chỉ muốn điều khiển ngôn ngữ.
4. Chỉ tạo `MessageInterpolator` tùy chỉnh khi có chính sách đặc biệt về locale, dữ liệu ngữ cảnh hoặc cách chọn nguồn bản dịch mà khả năng có sẵn không đáp ứng.

Với Jakarta Validation thuần, một cách an toàn để cưỡng bức locale trong một validator factory riêng là **bọc interpolator chuẩn**, ủy quyền phần nội suy cho nó. Ví dụ tệp độc lập `FixedLocaleInterpolator.java` (cần nhập vào dự án có Jakarta Validation):

```java
package com.example.interpolation;

import jakarta.validation.MessageInterpolator;
import java.util.Locale;
import java.util.Objects;

public final class FixedLocaleInterpolator implements MessageInterpolator {
    private final MessageInterpolator delegate;
    private final Locale fixedLocale;

    public FixedLocaleInterpolator(
            MessageInterpolator delegate,
            Locale fixedLocale) {
        this.delegate = Objects.requireNonNull(delegate);
        this.fixedLocale = Objects.requireNonNull(fixedLocale);
    }

    @Override
    public String interpolate(String template, Context context) {
        return delegate.interpolate(template, context, fixedLocale);
    }

    @Override
    public String interpolate(
            String template, Context context, Locale locale) {
        return delegate.interpolate(template, context, locale);
    }
}
```

Cách đăng ký (đoạn minh họa API bootstrap, không thay cho cấu hình HTTP Spring MVC):

```java
var configuration = jakarta.validation.Validation
        .byDefaultProvider().configure();
var defaultInterpolator = configuration.getDefaultMessageInterpolator();

try (var factory = configuration.messageInterpolator(
        new FixedLocaleInterpolator(
                defaultInterpolator, java.util.Locale.forLanguageTag("vi")))
        .buildValidatorFactory()) {

    var validator = factory.getValidator();
    // validator.validate(...) dùng locale Việt ở overload không có Locale.
}
```

Cần tránh bẫy tạo interpolator wrapper rồi trong `interpolate(...)` gọi lại chính nó vô hạn, hoặc mỗi lần nội suy lại xây dựng `ValidatorFactory` mới. Khởi tạo một factory phù hợp vòng đời ứng dụng; `ValidatorFactory` cần được đóng khi ngừng sử dụng trong đường bootstrap thủ công. Không giữ mutable locale theo request trong field của singleton interpolator.

Đối với ứng dụng nhiều ngôn ngữ, ví dụ `FixedLocaleInterpolator` chỉ là minh họa cách delegate; nên chọn locale từng request hoặc từng job thay vì cố định một ngôn ngữ toàn hệ thống.

## 9. EL, message parameter và tùy biến nâng cao

### 9.1. EL khác với placeholder bundle

Cú pháp `{min}` là message parameter; cú pháp `${...}` là **Jakarta Expression Language**. Với EL, context chuẩn có thể cung cấp:

- Thuộc tính annotation constraint, như `min`, `max`, `inclusive`.
- `validatedValue` (giá trị đang được kiểm tra).
- `formatter` cho định dạng phụ thuộc locale, ví dụ định dạng số.

Ví dụ minh họa descriptor trên `@DecimalMin`:

```java
@DecimalMin(
    value = "10",
    inclusive = false,
    message = "Giá trị phải ${inclusive ? 'lớn hơn hoặc bằng' : 'lớn hơn'} {value}"
)
private java.math.BigDecimal amount;
```

Với `inclusive = false`, kết quả nội suy mong đợi là `"Giá trị phải lớn hơn 10"` nếu provider hỗ trợ EL và mức tính năng được bật cho biểu thức này. Phần `{value}` lấy từ thuộc tính của `@DecimalMin`, còn `${inclusive ? ...}` được đánh giá bởi EL.

**Không phụ thuộc EL** khi môi trường không có implementation phù hợp. Hibernate Validator có `ParameterMessageInterpolator` hỗ trợ tham số nhưng **không đánh giá EL**; các biểu thức `${...}` có thể còn nguyên. Trong nhiều tình huống, key bundle + `{min}`/`{max}` vừa đủ, đơn giản và dễ i18n hơn.

### 9.2. Thông báo tạo bằng ConstraintValidatorContext

Trong một custom constraint, có thể gọi:

```java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        "{order.code.custom.invalid}")
    .addConstraintViolation();
return false;
```

Descriptor truyền vào `buildConstraintViolationWithTemplate(...)` vẫn được xử lý qua message interpolation khi constraint vi phạm. Nếu dùng Hibernate Validator, extension `HibernateConstraintValidatorContext#addMessageParameter(...)` cho phép gắn tham số `{name}` bổ sung. `addExpressionVariable(...)` là đường khác, dành cho EL `${name}` khi tính năng EL được bật.

Hibernate Validator 8.x giới hạn mức EL theo ngữ cảnh: custom violations tạo thủ công bằng `ConstraintValidatorContext` **tắt EL mặc định**; muốn dùng EL cần chủ động bật ở API mở rộng với mức phù hợp. Các mức như `NONE`, `VARIABLES`, `BEAN_PROPERTIES`, `BEAN_METHODS` có quyền khác nhau. Đặc biệt, đừng bật khả năng gọi phương thức trên bean nếu không có nhu cầu rõ ràng.

**An toàn:** Không ghép trực tiếp chuỗi do người dùng nhập vào message template có thể được đưa qua EL. Hãy dùng message key cố định và dữ liệu qua tham số/biến đã được API thiết kế cho việc đó. Cũng không nên chèn dữ liệu nhạy cảm từ `validatedValue` vào lỗi trả client.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| API trả `{order.code.size}` nguyên văn | Sai tên key, thiếu bundle, sai basename/classpath | Kiểm tra `ValidationMessages*.properties` và cú pháp `message="{...}"` |
| `{min}`/`{max}` chưa được thay | Không có thuộc tính tương ứng; dùng sai descriptor hoặc custom logic | Kiểm tra annotation và template thật từ `getMessageTemplate()` |
| Luôn trả tiếng Anh | Locale không được truyền, cấu hình resolver khác kỳ vọng, file `_vi` vắng | Test với `Accept-Language`, kiểm tra locale, resource bundle và validator |
| Ứng dụng có `messages_vi.properties` nhưng Bean Validation không dịch | Đang nhầm `MessageSource` với `ValidationMessages` | Dùng bundle Jakarta chuẩn hoặc cấu hình `setValidationMessageSource(...)` |
| EL xuất hiện nguyên `${...}` | EL không có/bị tắt, biểu thức không hợp lệ hoặc dùng `ParameterMessageInterpolator` | Kiểm tra provider, implementation EL và feature level |
| Thông báo sai số giới hạn | Chưa hiểu thay thế `{min}`, `{max}` hay annotation có giá trị khác | Xem metadata `ConstraintDescriptor#getAttributes()` |
| Lỗi dịch sai giữa request đồng thời | Đổi `Locale.setDefault(...)` theo request hoặc interpolator giữ mutable locale | Dùng `LocaleResolver`/`LocaleContextHolder`, giữ interpolator thread-safe |
| Test thông báo thất bại không ổn định | Test dựa vào locale JVM, thứ tự vi phạm hoặc fallback không cố định | Chọn locale tường minh và assert lỗi có đường dẫn/constraint xác định |
| HTTP trả lỗi định dạng JSON/binding trước validation | Jackson không parse được input thành DTO | Phân biệt bước deserialize với bước constraint validation |

Các nguyên tắc áp dụng thực tế:

- Dùng **key có namespace rõ ràng**, ví dụ `order.code.size`, để tránh trùng với message của module khác.
- Cung cấp bundle mặc định và các bundle theo ngôn ngữ; có kiểm tra thiếu key, placeholder và fallback trong CI.
- Giữ template ngắn gọn, thể hiện đúng business rule; không đưa exception stack trace, thông tin nội bộ hoặc giá trị nhạy cảm vào message.
- Kiểm tra cả `getMessageTemplate()` và `getMessage()` khi debug; chúng giúp phân biệt lỗi chọn message với lỗi nội suy.
- Trong i18n thực tế, tránh dựng câu phức tạp bằng cách ghép từ vựng nhỏ nếu ngữ pháp các ngôn ngữ khác nhau; chọn message hoàn chỉnh theo locale.
- Để chuẩn hóa API, trả mã lỗi ổn định (chẳng hạn `ORDER_CODE_SIZE`) bên cạnh bản dịch người dùng, thay vì bắt client phân tích chuỗi thông báo.
- Kiểm thử ở boundary thực tế: HTTP dùng request locale; xử lý nền dùng locale đã chọn; test thuần dùng validator factory rõ cấu hình.
- Nâng cấp Spring/Hibernate Validator phải chạy lại test locale và EL vì chính sách khả năng EL hoặc tích hợp message source có thể thay đổi theo phiên bản.

## 11. Checklist triển khai

1. Xác định constraint, điều kiện vi phạm và nội dung message muốn trả.
2. Khai báo `message = "{my.key}"`; đặt key và bản dịch vào bundle đúng cơ chế mà validator sử dụng.
3. Nếu message cần giá trị annotation, dùng `{min}`/`{max}`/thuộc tính tương ứng; kiểm tra thứ tự giải mã tham số.
4. Cấu hình và kiểm thử `Locale` theo đúng ngữ cảnh HTTP, background job hoặc Java thuần.
5. Dùng `@Valid`/`@Validated` ở điểm kích hoạt phù hợp và chuyển violation sang response nhất quán.
6. Chỉ thêm custom `MessageInterpolator`/EL khi cần; delegate thuật toán chuẩn và giữ thread safety.
7. Kiểm thử template, message đã dịch, fallback locale, thiếu key và những trường hợp input không hợp lệ.

**Kết luận:** `MessageInterpolator` là cầu nối từ **message template** của Bean Validation đến **thông báo lỗi đã nội suy theo locale**. Nắm thứ tự bundle → thuộc tính annotation → EL, phân biệt `ValidationMessages` với Spring `MessageSource`, và hiểu nguồn của locale trong Spring MVC sẽ giúp thông báo chính xác, có thể bản địa hóa và dễ kiểm thử.

## Tài liệu tham khảo

- [Jakarta Validation 3.1 — Message interpolation, `6.3](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#message-interpolation)
- [Hibernate Validator 8 — Interpolating constraint error messages](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/#chapter-message-interpolation)
- [Spring Framework — LocalValidatorFactoryBean API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/reference/features/internationalization.html)
