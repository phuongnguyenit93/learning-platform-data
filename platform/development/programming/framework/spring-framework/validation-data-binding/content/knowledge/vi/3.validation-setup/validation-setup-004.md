# Cấu hình LocalValidatorFactoryBean bằng Java Configuration trong Spring Framework

`LocalValidatorFactoryBean` là lớp cầu nối giữa **Jakarta Bean Validation** và hệ thống **Spring Validation**. Khi cấu hình bằng Java, bạn khai báo nó dưới dạng một Spring bean bằng `@Configuration` và `@Bean`, sau đó có thể dùng cùng validator ở tầng Spring MVC và trong các service cần kiểm tra đối tượng.

Mục tiêu của bài: tạo và tùy chỉnh `LocalValidatorFactoryBean` bằng Java Configuration; hiểu quan hệ giữa Spring `Validator`, Jakarta `Validator` và Bean Validation provider; nối validator vào Spring MVC; cấu hình thông báo lỗi qua `MessageSource`; biết khi nào cần cấu hình thủ công, cách kiểm tra và tránh các lỗi tích hợp thường gặp.

## 1. Hiểu đúng vai trò của LocalValidatorFactoryBean

Một yêu cầu HTTP có thể được chuyển thành đối tượng Java nhưng đối tượng ấy vẫn vi phạm các ràng buộc, chẳng hạn tên rỗng hoặc tuổi quá nhỏ. Các annotation như `@NotBlank`, `@Email`, `@Min` mô tả **quy tắc**; một Bean Validation provider (thường là Hibernate Validator) thực hiện **việc đánh giá quy tắc**. Spring cần một cách nối provider đó với cơ chế kiểm tra đối tượng, data binding và MVC.

```text
DTO với các annotation jakarta.validation.constraints.*
          │
          ▼
      @Valid / @Validated
          │
          ▼
Spring MVC / Spring Validation cần Validator
          │
          ▼
LocalValidatorFactoryBean (Spring bean)
          │ khởi tạo và quản lý ValidatorFactory
          ▼
Jakarta Bean Validation provider (ví dụ Hibernate Validator)
          │
          ▼
ConstraintViolation / Spring Errors / BindingResult
```

Các thành phần cần phân biệt:

| Thành phần | Vai trò |
| --- | --- |
| `jakarta.validation.Valid` | Yêu cầu kiểm tra ràng buộc của đối tượng hoặc kiểm tra lồng nhau; bản thân nó không phải một constraint. |
| `jakarta.validation.constraints.*` | Các annotation khai báo điều kiện hợp lệ, ví dụ `@NotBlank` hoặc `@Min`. |
| `jakarta.validation.Validator` | API Jakarta để gọi `validate(object)` và nhận `Set<ConstraintViolation<T>>`. |
| `org.springframework.validation.Validator` | Hợp đồng của Spring với `supports(Class<?>)` và `validate(Object, Errors)`; phục vụ tích hợp binding/MVC. |
| `LocalValidatorFactoryBean` | Adapter triển khai cả hai vai trò validator nói trên, đồng thời quản lý `jakarta.validation.ValidatorFactory`. |
| Bean Validation provider | Cài đặt thực tế thực thi constraints; chỉ có các annotation/API mà không có provider là chưa đủ. |
| `WebMvcConfigurer#getValidator()` | Điểm mở rộng để khai báo validator toàn cục mà Spring MVC sẽ sử dụng. |

`LocalValidatorFactoryBean` kế thừa `SpringValidatorAdapter` và đồng thời cung cấp `SmartValidator`. Khi Spring quản lý bean, quá trình khởi tạo gọi `afterPropertiesSet()` để bootstrap validator factory; khi đóng context, Spring gọi cơ chế hủy bean. Vì vậy **không tự gọi các phương thức vòng đời** và không tạo một `new LocalValidatorFactoryBean()` cho mỗi request.

## 2. Khi nào cần Java Configuration?

Nếu Bean Validation provider đã có trên classpath, Spring MVC thường tự tạo validator toàn cục cho `@Valid` và `@Validated`. Spring Boot có starter validation để cung cấp cấu hình phổ biến. **Không bắt buộc khai báo `LocalValidatorFactoryBean` thủ công cho mọi dự án.**

Cấu hình bằng Java hữu ích khi cần:

- Đăng ký một `Validator` bean để tiêm vào các thành phần khác và chủ động quản lý nó.
- Tùy chỉnh nội dung thông báo validation thông qua Spring `MessageSource` hoặc cấu hình riêng của provider.
- Chỉ định rõ validator Spring MVC dùng, thay vì dựa vào lựa chọn mặc định.
- Thiết lập nâng cao như provider, mapping, `ConstraintValidatorFactory` hoặc thuộc tính cấu hình validation.

Phần ví dụ dưới đây dùng **Spring Framework 6.x / Spring Boot 3.x và Java 17+**, nên các annotation thuộc namespace `jakarta.validation`. Ở Spring Framework 5 / Boot 2, namespace từng là `javax.validation`; không trộn hai hệ khi biên dịch.

### Dependency cần có

Trong một dự án Spring Boot 3.x đã cấu hình Gradle plugin của Spring Boot, bổ sung:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

Starter web cung cấp Spring MVC và hạ tầng HTTP/JSON; starter validation cung cấp API cùng Bean Validation provider phù hợp với phiên bản Boot. Trong dự án Spring Framework thuần, bạn phải tự cung cấp `spring-webmvc`, Jakarta Validation API và một provider tương thích. Lỗi thiếu provider không thể giải quyết chỉ bằng việc thêm annotation `@Valid`.

## 3. Cấu hình cơ bản với @Configuration và @Bean

Trường hợp đơn giản nhất chỉ cần định nghĩa bean:

```java
package demo.validation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class BasicValidationConfiguration {

    @Bean
    public LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
```

Đây là **một tệp Java cấu hình**, không phải chương trình độc lập có `main`. Spring phải quét/đăng ký lớp `@Configuration` trong application context. Sau đó bean `validator` được tạo đúng một lần theo phạm vi singleton mặc định, nhận các callback vòng đời và có thể được tiêm vào nơi khác.

Ví dụ một service muốn kiểm tra DTO thủ công có thể tiêm `jakarta.validation.Validator`:

```java
package demo.validation;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.Set;
import org.springframework.stereotype.Service;

@Service
public class InputCheckService {

    private final Validator validator;

    public InputCheckService(Validator validator) {
        this.validator = validator;
    }

    public <T> Set<ConstraintViolation<T>> check(T input) {
        return validator.validate(input);
    }
}
```

`validate` trả về tập vi phạm; nó **không tự biến việc kiểm tra ở service thành HTTP 400**, không tự lưu dữ liệu và không thay thế quy tắc nghiệp vụ. Khi dùng constructor injection, bảo đảm chỉ có một bean phù hợp hoặc chỉ rõ bean được ưu tiên.

Để chắc chắn **Spring MVC** sử dụng validator đã tùy chỉnh, có thể triển khai `WebMvcConfigurer` và trả về validator ở `getValidator()`. Bản hoàn chỉnh tiếp theo minh họa cả cách nối này lẫn việc sử dụng `MessageSource`.

## 4. Ví dụ hoàn chỉnh: validator Java Config với thông báo tiếng Việt

Cấu trúc tệp trong dự án Spring Boot 3.x:

```text
src/main/
├── java/demo/validation/
│   ├── ValidationDemoApplication.java
│   ├── ValidationConfiguration.java
│   ├── RegistrationRequest.java
│   ├── RegistrationController.java
│   └── ValidationErrorHandler.java
└── resources/
    └── messages.properties
```

### 4.1. Điểm khởi động ứng dụng

Tệp `src/main/java/demo/validation/ValidationDemoApplication.java`:

```java
package demo.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationDemoApplication.class, args);
    }
}
```

Lớp này đặt cùng package với các thành phần còn lại để component scanning của Spring Boot phát hiện controller, advice và configuration.

### 4.2. Khai báo MessageSource và LocalValidatorFactoryBean

Tệp `src/main/java/demo/validation/ValidationConfiguration.java`:

```java
package demo.validation;

import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.context.support.ReloadableResourceBundleMessageSource;
import org.springframework.validation.Validator;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class ValidationConfiguration implements WebMvcConfigurer {

    @Bean
    public MessageSource messageSource() {
        ReloadableResourceBundleMessageSource source =
                new ReloadableResourceBundleMessageSource();
        source.setBasename("classpath:messages");
        source.setDefaultEncoding("UTF-8");
        return source;
    }

    @Bean
    @Primary
    public LocalValidatorFactoryBean validator() {
        LocalValidatorFactoryBean factory =
                new LocalValidatorFactoryBean();
        factory.setValidationMessageSource(messageSource());
        return factory;
    }

    @Override
    public Validator getValidator() {
        return validator();
    }
}
```

Ý nghĩa của từng điểm:

1. `@Configuration` đưa lớp cấu hình vào Spring application context.
2. `messageSource()` khai báo bean đọc các thông báo từ `messages.properties`. Chúng ta dùng `ReloadableResourceBundleMessageSource` và chỉ rõ UTF-8 để có thể viết thông báo tiếng Việt.
3. `validator()` tạo `LocalValidatorFactoryBean` một lần và gọi `setValidationMessageSource(...)` để các mã thông báo trong constraint được giải quyết qua Spring `MessageSource`.
4. `@Primary` ưu tiên bean này khi một nơi tiêm dependency theo kiểu validator mà có nhiều bean cùng phù hợp. Annotation này **không thay thế** việc chỉ định validator toàn cục của MVC.
5. `getValidator()` là phương thức của `WebMvcConfigurer`; Spring MVC gọi nó để dùng chính validator đã cấu hình làm validator toàn cục.

Trong ví dụ, `getValidator()` gọi `validator()` và `validator()` gọi `messageSource()`. Điều này an toàn vì `@Configuration` dùng chế độ proxy bean methods mặc định: các lời gọi `@Bean` trong cùng lớp được Spring chuyển đến bean singleton đã quản lý. **Nếu đổi thành `@Configuration(proxyBeanMethods = false)`, không nên tự gọi các bean methods kiểu này**; hãy chuyển sang tiêm dependency giữa các lớp cấu hình hoặc dùng `ObjectProvider`. Không tự ý đổi proxy mode mà giữ nguyên đoạn mã trên.

### 4.3. Khai báo DTO và constraint

Tệp `src/main/java/demo/validation/RegistrationRequest.java`:

```java
package demo.validation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record RegistrationRequest(
        @NotBlank(message = "{registration.name.required}")
        String name,

        @NotBlank(message = "{registration.email.required}")
        @Email(message = "{registration.email.invalid}")
        String email,

        @NotNull(message = "{registration.age.required}")
        @Min(value = 18, message = "{registration.age.min}")
        Integer age
) {}
```

Các mã trong `message = "{...}"` không phải nội dung tiếng Việt viết cứng trong Java. Validator sẽ tra mã đó qua cơ chế message interpolation đã cấu hình. Ở đây `Integer` được dùng để `@NotNull` phát hiện trường `age` bị thiếu; `@Min` không tự buộc một giá trị khác `null`.

Tệp `src/main/resources/messages.properties`:

```properties
registration.name.required=Tên không được để trống
registration.email.required=Email không được để trống
registration.email.invalid=Email không đúng định dạng
registration.age.required=Tuổi là bắt buộc
registration.age.min=Phải đủ 18 tuổi
```

Mã thông báo phải khớp **chính xác** giữa `message` trên DTO và khóa trong tệp properties. Không đặt `setUseCodeAsDefaultMessage(true)` cho `MessageSource` dùng ở đây: nó có thể khiến cơ chế nội suy không còn fallback đúng sang các thông báo chuẩn của Hibernate Validator. Nếu cần nhiều ngôn ngữ, có thể thêm bundle theo locale như `messages_en.properties` và kiểm tra sự lựa chọn locale trong ứng dụng.

### 4.4. Dùng validator trong Spring MVC

Tệp `src/main/java/demo/validation/RegistrationController.java`:

```java
package demo.validation;

import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {

    @PostMapping
    public ResponseEntity<Map<String, String>> register(
            @Valid @RequestBody RegistrationRequest request) {

        return ResponseEntity.status(HttpStatus.CREATED).body(
                Map.of("status", "accepted", "name", request.name()));
    }
}
```

Khi nhận JSON hợp cú pháp và có thể chuyển thành `RegistrationRequest`, Spring sẽ chạy các constraint của Bean Validation vì tham số có `@Valid`. Nếu hợp lệ, controller trả HTTP 201. Đây là endpoint minh họa: **chưa lưu vào cơ sở dữ liệu, chưa kiểm tra email trùng và chưa có nghiệp vụ đăng ký thực sự**.

### 4.5. Trả lỗi validation có cấu trúc

Nếu không định nghĩa handler riêng, Spring MVC thường trả HTTP 400 khi `@Valid @RequestBody` thất bại, nhưng phần thân lỗi mặc định tùy phiên bản và cấu hình. Để minh họa thông báo đã tùy chỉnh, tạo tệp `src/main/java/demo/validation/ValidationErrorHandler.java`:

```java
package demo.validation;

import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationErrorHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> invalid(
            MethodArgumentNotValidException exception) {

        List<Map<String, String>> errors = exception
                .getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> Map.of(
                        "field", error.getField(),
                        "message", error.getDefaultMessage() == null
                                ? "Dữ liệu không hợp lệ"
                                : error.getDefaultMessage()))
                .toList();

        Map<String, Object> body = Map.of("errors", errors);
        return ResponseEntity.badRequest().body(body);
    }
}
```

`MethodArgumentNotValidException` là tình huống điển hình khi một đối tượng `@RequestBody` có `@Valid` nhưng vi phạm Bean Validation. Handler trên trả tên trường cùng thông báo đã nội suy. Thứ tự nhiều lỗi không phải hợp đồng cần phụ thuộc; ở ứng dụng thực tế, bạn có thể sắp xếp lỗi theo tên trường và thống nhất mã lỗi riêng. Ngoài ra cần xử lý riêng lỗi JSON không đọc được, lỗi chuyển kiểu và các trường hợp method validation.

## 5. Chạy và kiểm chứng đầu cuối

Trong dự án đã cấu hình Spring Boot Gradle plugin, chạy:

```bash
./gradlew bootRun
```

Lệnh sau dùng Bash hoặc Git Bash; có thể gửi các JSON tương đương qua HTTP client khác.

**Trường hợp hợp lệ:**

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lan","email":"lan@example.com","age":20}'
```

Kỳ vọng HTTP **201 Created**. JSON phản hồi có các trường `status` bằng `"accepted"` và `name` bằng `"Lan"` (thứ tự các khóa trong JSON có thể thay đổi).

**Trường hợp vi phạm một constraint:**

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":" ","email":"lan@example.com","age":20}'
```

Kỳ vọng HTTP **400 Bad Request** với dữ liệu lỗi về trường `name`:

```json
{"errors":[{"field":"name","message":"Tên không được để trống"}]}
```

Đây là cách kiểm chứng cả chuỗi: `@Valid` kích hoạt validation → `LocalValidatorFactoryBean` gọi provider → message key được tra qua `MessageSource` → `ValidationErrorHandler` lấy kết quả và tạo JSON.

**Trường hợp nhiều constraint sai:**

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":"","email":"bad-email","age":16}'
```

Kỳ vọng HTTP 400 và ba thông báo tương ứng cho `name`, `email`, `age`. Thứ tự phần tử trong `errors` không cố định; không viết kiểm thử dựa vào thứ tự đó.

**Trường hợp lỗi trước validation:**

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lan","email":"lan@example.com","age":"abc"}'
```

Với kiểu `Integer`, chuỗi `"abc"` không chuyển được thành giá trị tuổi. Spring/Jackson thường báo lỗi đọc hoặc chuyển đổi body (`HttpMessageNotReadableException`) và HTTP 400; handler dành riêng cho `MethodArgumentNotValidException` phía trên **không xử lý lỗi này**. Điều đó giúp phân biệt lỗi cú pháp/kiểu đầu vào với constraint violation của một DTO đã tạo được.

## 6. Bean dùng ở đâu và các cách tích hợp

### 6.1. Validator toàn cục trong Spring MVC

`WebMvcConfigurer#getValidator()` chọn validator áp dụng cho quy trình kiểm tra đối tượng của MVC. Khi có `@Valid` trên `@RequestBody`, `@ModelAttribute` hoặc `@RequestPart` thuộc trường hợp được hỗ trợ, MVC chuyển việc kiểm tra đến validator thích hợp. Một số trường hợp có `BindingResult` đặt ngay sau đối tượng có thể nhận lỗi để controller xử lý thay vì ném exception.

Không thêm `@EnableWebMvc` vào ứng dụng **Spring Boot** chỉ vì muốn cấu hình validator: annotation đó trao quyền kiểm soát cấu hình MVC cho ứng dụng và làm thay đổi nhiều cơ chế tự cấu hình của Boot. Ở ứng dụng Spring MVC thuần quản lý bằng Java Configuration, `@EnableWebMvc` có thể là một phần của cấu hình MVC. Ví dụ Boot ở trên chỉ cần `@Configuration` và `WebMvcConfigurer`.

### 6.2. Validator được tiêm để kiểm tra thủ công

Có thể tiêm cùng bean thông qua `jakarta.validation.Validator` hoặc `LocalValidatorFactoryBean` để kiểm tra đối tượng ngoài controller. Khi gọi `validator.validate(entity)`, kết quả là tập `ConstraintViolation`, không phải `BindingResult`. Nếu muốn chuyển sang xử lý nghiệp vụ hay HTTP, tầng gọi phải quyết định xử lý tập vi phạm ấy.

Đồng thời, `LocalValidatorFactoryBean` cũng có API của Spring `Validator`/`SmartValidator`, phù hợp để tích hợp với `Errors` và `DataBinder`. Cần import đúng kiểu theo phương thức sử dụng:
- `org.springframework.validation.Validator` cho `WebMvcConfigurer#getValidator()`.
- `jakarta.validation.Validator` cho `validate(object)` và `ConstraintViolation`.
- `jakarta.validation.Valid` cho annotation kiểm tra DTO.

### 6.3. Validator cục bộ và kiểm tra phương thức

Bên cạnh validator toàn cục, một controller có thể đăng ký thêm Spring `Validator` bằng `@InitBinder` khi có quy tắc binding đặc thù cho một form. Điều này không yêu cầu tạo một validator toàn cục khác.

Kiểm tra constraint đặt trực tiếp trên tham số phương thức, như `@RequestParam @Min(1) int page`, thuộc nhóm **method validation** và có thể phát sinh `HandlerMethodValidationException` trong Spring MVC 6.1+. Trên service, `@Validated` kết hợp hạ tầng method validation/AOP phù hợp là câu chuyện riêng; việc có bean `LocalValidatorFactoryBean` không bảo đảm mọi method service tự được chặn và kiểm tra. Khi xây API lỗi thống nhất, cân nhắc cả `MethodArgumentNotValidException` lẫn `HandlerMethodValidationException` nếu chữ ký controller dùng cả hai kiểu validation.

## 7. Những cấu hình nâng cao và giới hạn của chúng

### 7.1. Thông báo và nội suy

`setValidationMessageSource(MessageSource)` cho phép tái sử dụng Spring message bundle thay cho chỉ dùng `ValidationMessages.properties` mặc định của Bean Validation. Tính năng này dựa vào hỗ trợ nội suy của Hibernate Validator; nếu đổi provider, hãy kiểm tra khả năng tương thích. Không cấu hình `setValidationMessageSource(...)` và `setMessageInterpolator(...)` đồng thời vì chúng là hai cách điều khiển cùng một thành phần nội suy.

Nếu dự án chỉ cần các thông báo chuẩn, bỏ `setValidationMessageSource` và dùng `new LocalValidatorFactoryBean()` là đủ. Nếu đã có bean `messageSource` do ứng dụng tạo sẵn, **dùng lại bean hiện hữu** thay vì khai báo thêm bean cùng tên. Ví dụ trên tự khai báo để dễ hiểu và chạy độc lập trong dự án mẫu.

### 7.2. Provider, mapping và cấu hình khác

`LocalValidatorFactoryBean` có các điểm mở rộng như `setProviderClass(...)` để chỉ định provider tương thích, `setMappingLocations(...)` để nạp XML constraint mapping, `setConstraintValidatorFactory(...)` để thay đổi cách khởi tạo constraint validator, và `setValidationPropertyMap(...)` để truyền thuộc tính cấu hình cho provider. Không dùng những phương thức này chỉ để “bật @Valid”: ứng dụng cơ bản thường không cần.

Mặc định, factory hỗ trợ cơ chế tạo `ConstraintValidator` có tích hợp Spring để các validator tùy biến có thể dùng dependency injection. Thay `ConstraintValidatorFactory` mà không có lý do có thể làm mất khả năng tiêm các dependency cần thiết. Các thuộc tính riêng của Hibernate Validator phải được kiểm tra theo phiên bản provider đang chạy.

### 7.3. Nhiều bean Validator và lựa chọn bean

Có thể có validator do MVC xây mặc định, validator do ứng dụng định nghĩa, hoặc validator cục bộ của một controller. `@Primary` giải quyết ưu tiên **dependency injection theo kiểu**, còn `getValidator()` chỉ định **validator toàn cục của MVC**. Nếu tồn tại nhiều lớp `WebMvcConfigurer` cùng trả về validator khác nhau, việc chọn một validator toàn cục có thể trở nên khó hiểu; nên tập trung cấu hình này vào một chỗ có chủ đích.

## 8. Kiểm thử cấu hình: nên chứng minh điều gì?

Không dừng ở việc application context khởi động được. Một bài kiểm thử tích hợp của ứng dụng nên chứng minh:

| Trường hợp | Kết quả cần kiểm chứng |
| --- | --- |
| JSON hợp lệ | Controller được gọi, phản hồi thành công theo hợp đồng. |
| `name` chỉ chứa khoảng trắng | Trả 400 và thông báo từ `messages.properties`. |
| `email` sai định dạng | Vi phạm `@Email`; không đi vào xử lý thành công. |
| `age` thiếu hoặc nhỏ hơn 18 | Bị chặn bởi `@NotNull` hoặc `@Min` tương ứng. |
| `age` không giải mã thành `Integer` | Lỗi chuyển kiểu/body, phân biệt với `MethodArgumentNotValidException`. |
| Tiêm `jakarta.validation.Validator` vào service | Có bean thích hợp và `validate(...)` trả violations đúng. |
| Dùng locale khác | Đúng bundle/language dự kiến nếu hệ thống hỗ trợ đa ngôn ngữ. |

Với Spring Boot, có thể dùng `@SpringBootTest` và `MockMvc` để kiểm tra việc nối validator, status HTTP và nội dung phản hồi. Test chỉ gọi `new LocalValidatorFactoryBean()` không thay cho test tích hợp vì không chứng minh MVC đang sử dụng bean cấu hình. Nếu cần kiểm thử logic constraint thuần, một test trực tiếp qua `jakarta.validation.Validator` lại rất phù hợp.

## 9. Lỗi phổ biến và cách chẩn đoán

1. **Có `@Valid` nhưng không thấy lỗi:** kiểm tra starter/provider, kiểu DTO, vị trí `@Valid` và lời gọi MVC. Đừng nhầm import `javax.validation.*` với `jakarta.validation.*` ở Spring 6.
2. **Khởi động lỗi không tìm được provider:** bổ sung một Bean Validation provider tương thích; chỉ có API/annotation là chưa đủ.
3. **Thông báo trả về là chuỗi mã trong ngoặc nhọn:** kiểm tra tên resource bundle, khóa, encoding, bean `messageSource` và cấu hình `setValidationMessageSource`.
4. **Tiêm `Validator` bị ambiguous:** kiểm tra hai interface trùng tên, số lượng bean và sử dụng `@Primary` hoặc `@Qualifier` một cách có chủ đích.
5. **`getValidator()` tạo đối tượng khác bean đang tiêm:** kiểm tra có gọi `new` mỗi lần hay dùng `@Configuration(proxyBeanMethods = false)` trong khi tự gọi `@Bean` method không.
6. **Thêm `@EnableWebMvc` làm cấu hình Boot đổi hành vi:** dùng `WebMvcConfigurer` để mở rộng thay vì vô tình thay thế cấu hình MVC do Boot cung cấp.
7. **Chỉ bắt `MethodArgumentNotValidException` mà bỏ sót lỗi khác:** lỗi chuyển kiểu/đọc body và method validation có exception riêng; thống nhất phản hồi theo từng nhóm.
8. **Dùng Bean Validation để xử lý tất cả nghiệp vụ:** constraint DTO không thay thế xác thực, phân quyền, kiểm tra dữ liệu trùng hoặc bất biến của database.
9. **Dùng `@NotNull` trên chuỗi và tưởng đã cấm chuỗi rỗng:** dùng `@NotBlank` khi không cho phép chuỗi chỉ chứa khoảng trắng.
10. **Tạo bean tùy chỉnh trong Boot dù không cần:** cấu hình mặc định đủ cho nhiều ứng dụng; chỉ thêm Java Configuration khi có yêu cầu thực tế.

## 10. Ghi nhớ quy trình

Một cấu hình đúng cần trả lời bốn câu hỏi: **provider có mặt chưa?** → **Spring quản lý validator nào?** → **Spring MVC/service thực sự dùng validator đó chưa?** → **ràng buộc, thông báo và đường xử lý lỗi đã được kiểm chứng chưa?**

- Khi chỉ cần `@Valid` theo mặc định: thêm provider/starter phù hợp và dùng DTO constraints.
- Khi cần một bean dùng chung: khai báo `@Bean LocalValidatorFactoryBean` trong `@Configuration`.
- Khi cần điều khiển MVC: triển khai `WebMvcConfigurer#getValidator()`.
- Khi cần thông báo tùy biến: cấu hình `MessageSource` và `setValidationMessageSource(...)`, sau đó kiểm tra qua request lỗi thực tế.

**Tài liệu chính thức để đào sâu:**
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring MVC — Cấu hình validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring MVC — Kiểm tra đối số controller](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
