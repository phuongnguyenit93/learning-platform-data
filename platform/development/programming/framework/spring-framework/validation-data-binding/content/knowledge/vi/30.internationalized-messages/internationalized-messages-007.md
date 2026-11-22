# validationMessageSource của LocalValidatorFactoryBean: thông báo validation đa ngữ trong Spring

## 1. Mục tiêu bài học

Một ứng dụng có người dùng Việt Nam và quốc tế cần hiển thị lỗi nhập liệu theo ngôn ngữ tương ứng, chẳng hạn:

~~~text
Request với locale=vi:
  name=" "   -> Họ tên không được để trống
  age=16     -> Tuổi phải từ 18 trở lên

Request với locale=en:
  name=" "   -> Name must not be blank
  age=16     -> Age must be at least 18
~~~

Cùng một Java DTO, cùng annotations và cùng quy tắc kiểm tra, nhưng **message thay đổi theo `Locale`**. Ở tầng Bean Validation (Jakarta Validation), thông báo trong `@NotBlank(message=...)` hoặc `@Min(message=...)` được chuyển thành văn bản qua `MessageInterpolator`. Ở tầng Spring, `MessageSource` cung cấp catalog thông báo theo locale. `LocalValidatorFactoryBean` là cầu nối giữa hai hệ thống đó.

API trọng tâm:

~~~java
LocalValidatorFactoryBean validator = new LocalValidatorFactoryBean();
validator.setValidationMessageSource(messageSource);
~~~

**`validationMessageSource` là một thuộc tính JavaBean của `LocalValidatorFactoryBean`**, được thiết lập qua `setValidationMessageSource(MessageSource)`. Đây **không phải** tên bắt buộc của một Spring bean, và cũng không phải tên file mặc định. Ta có thể truyền bean tên `messageSource` của ứng dụng, hoặc một `MessageSource` dành riêng cho validation.

Bài này làm rõ:
1. Vai trò của `LocalValidatorFactoryBean`, `MessageSource` và `MessageInterpolator`.
2. Cách cấu hình `setValidationMessageSource` và bundles `messages.properties`, `messages_vi.properties`, `messages_en.properties`.
3. Cách hoạt động của template như `{signup.name.required}` và tham số constraint `{value}`.
4. Cách locale được chọn khi gọi validator trực tiếp hoặc khi request qua Spring MVC.
5. Khác biệt giữa Boot auto-configuration và cấu hình thủ công.
6. Test chính xác hai locale, fallback, và đường `@Valid @RequestBody`.
7. Các lỗi thường gặp trong i18n/validation và cách kiểm tra chúng.

Ví dụ chính dùng **Java 17, Spring Boot 3.5.7, Spring Framework 6.2, Jakarta Validation**. Phần kiến thức về `LocalValidatorFactoryBean` cũng có thể áp dụng trong Spring MVC/WebFlux và Spring services, nhưng ví dụ HTTP runnable dùng Spring MVC để tránh trộn Servlet với reactive stack.

## 2. Bốn khái niệm không nên nhầm

### 2.1. Jakarta Bean Validation constraint message

Ví dụ:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class SignupRequest {
    @NotBlank(message = "{signup.name.required}")
    private String name;

    @Min(value = 18, message = "{signup.age.min}")
    private int age;
}
~~~

`@NotBlank` và `@Min` mô tả **điều kiện hợp lệ**. Thuộc tính `message` chứa **message template**, có thể là chuỗi cố định hoặc khóa tham chiếu đến resource bundle. Dấu ngoặc nhọn như `{signup.age.min}` biểu diễn một mã được tìm trong nguồn message để tạo văn bản cho người dùng.

Nếu dùng literal message:

~~~java
@NotBlank(message = "Name is required")
private String name;
~~~

thì đoạn literal không tự trở thành tiếng Việt khi locale là `vi`. Muốn i18n linh hoạt, ưu tiên **khóa có tên ổn định**, ví dụ `{signup.name.required}`.

### 2.2. Spring `MessageSource`

`org.springframework.context.MessageSource` có các phương thức như:

~~~java
String getMessage(
        String code,
        Object[] args,
        Locale locale);
~~~

Trong ứng dụng Spring Boot, `MessageSource` thường đọc một nhóm files:

~~~text
src/main/resources/
  messages.properties
  messages_en.properties
  messages_vi.properties
~~~

Với locale `vi`, key `signup.name.required` được tìm trong bundle tiếng Việt. Với locale `en`, key tương ứng được tìm trong bundle tiếng Anh, sau đó fallback theo cấu hình.

`MessageSource` không tự chạy validation. Nó chỉ **tra cứu và định dạng thông điệp**; việc phát hiện dữ liệu sai thuộc về `Validator`.

### 2.3. `MessageInterpolator` trong Bean Validation

`jakarta.validation.MessageInterpolator` nhận message template, context constraint và locale, rồi tạo thông báo cuối. Một provider như Hibernate Validator triển khai bộ interpolation có thể:
- Tra khóa `{signup.age.min}` trong message resource bundle.
- Thay thuộc tính annotation như `{value}` của `@Min(value = 18)` thành `18`.
- Xử lý các biểu thức/escape của Bean Validation theo spec và provider.

Đừng đồng nhất interpolation của Bean Validation với `MessageFormat` của Spring. Ví dụ `{value}` là **constraint attribute** trong Bean Validation, trong khi `{0}` thường là **vị trí tham số** khi gọi Spring `MessageSource#getMessage(code,args,locale)`. Hai cú pháp có thể xuất hiện trong hệ thống nhưng có ý nghĩa khác nhau.

### 2.4. `LocalValidatorFactoryBean`

`org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` là adapter Spring cho Jakarta Bean Validation. Nó:
- Tạo và quản lý một `ValidatorFactory` của provider.
- Expose đối tượng tương thích `jakarta.validation.Validator`.
- Triển khai `org.springframework.validation.SmartValidator` cho Spring binding/validation.
- Tham gia `@Valid`/`@Validated` trong tích hợp Spring.
- Cho phép thiết lập provider, message source, message interpolator, constraint validator factory và những tùy chọn khác.

Phương thức quan trọng:

~~~java
void setValidationMessageSource(MessageSource messageSource);
~~~

Theo Spring Javadoc, nó dùng **Spring MessageSource để giải quyết validation messages thay cho việc chỉ dựa vào `ValidationMessages.properties` mặc định của Jakarta Validation**. Trong Spring Framework 6.2, tích hợp này dựa vào lớp hỗ trợ interpolation của Hibernate Validator; nếu chọn provider khác, cần kiểm tra Hibernate Validator resource-bundle interpolation classes có sẵn như yêu cầu Javadoc.

## 3. Sơ đồ giải quyết message

~~~text
User gửi request, Spring chọn Locale
             |
             v
@Valid @RequestBody SignupRequest
             |
             v
LocalValidatorFactoryBean
             |
             v
Jakarta Validator / Hibernate Validator
             |
             +--> @NotBlank(message="{signup.name.required}")
             |       |
             |       v
             |    MessageSource (messages_vi, messages_en...)
             |       |
             |       v
             |    "Họ tên không được để trống"
             |
             +--> @Min(value=18, message="{signup.age.min}")
                     |
                     v
                  MessageSource
                     |
                     v
                  "Tuổi phải từ {value} trở lên"
                     |
                     v
                  Provider interpolation
                     |
                     v
                  "Tuổi phải từ 18 trở lên"
             |
             v
ConstraintViolation.getMessage()
             |
             v
Spring BindingResult / FieldError / HTTP error response
~~~

Quan trọng: `ConstraintViolation#getMessageTemplate()` trả **template ban đầu** (ví dụ `"{signup.age.min}"`), còn `getMessage()` trả **nội dung đã được interpolated** theo locale, ví dụ `"Tuổi phải từ 18 trở lên"`. Nếu ứng dụng tự gửi `getMessageTemplate()` tới UI mà không resolve, người dùng sẽ thấy một key thay vì thông điệp.

Tương tự, `FieldError#getDefaultMessage()` trong Spring MVC thường là thông báo được chuyển từ constraint violation (hoặc thông báo binding error), nhưng trường `FieldError#getCodes()` còn có các mã dành cho Spring `MessageCodesResolver`. Không coi chúng là một chuỗi message duy nhất: code và message phục vụ hai mục đích khác nhau.

## 4. Cấu hình `setValidationMessageSource` như thế nào?

### 4.1. Java Configuration cơ bản

~~~java
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationConfiguration {

    @Bean
    LocalValidatorFactoryBean validator(MessageSource messageSource) {
        LocalValidatorFactoryBean bean = new LocalValidatorFactoryBean();
        bean.setValidationMessageSource(messageSource);
        return bean;
    }
}
~~~

Đây là **file cấu hình độc lập** nếu project có Spring context, Jakarta Validation provider và `MessageSource`. Tạo `LocalValidatorFactoryBean` như một Spring bean để Spring thực hiện lifecycle (bao gồm việc khởi tạo provider sau khi các properties được set). Không tạo đối tượng bằng `new` rồi gọi `validate` ngay trước khi factory được khởi tạo.

**Đừng tự gọi `afterPropertiesSet()` trên bean do Spring quản lý** chỉ để “chắc chắn”; Spring sẽ thực hiện init lifecycle. Khi xây test thuần ngoài Spring, nếu dùng `new LocalValidatorFactoryBean()` thì phải tự hoàn tất lifecycle theo cách tương ứng.

### 4.2. JavaBean property khác với tên Spring bean

Trong XML configuration lịch sử, property là `validationMessageSource`:

~~~xml
<bean id="validator"
      class="org.springframework.validation.beanvalidation.LocalValidatorFactoryBean">
    <property name="validationMessageSource" ref="messageSource"/>
</bean>
~~~

Tên property tương ứng setter `setValidationMessageSource`. Nhưng trong Java configuration, `messageSource` có thể là tên bean do Spring Boot tạo từ `messages.properties`, còn bean validator có thể tên `validator`, `localValidatorFactoryBean` hoặc một tên khác.

Nếu tự khai báo một bean tên `validationMessageSource` nhưng **không kết nối nó vào validator**, chỉ cái tên đó không đủ làm Bean Validation tìm thấy resource bundle.

### 4.3. Dùng một nguồn chung hoặc nguồn tách biệt?

**Dùng chung:** truyền application `MessageSource` đang phục vụ labels, UI và error messages. Ưu điểm là một hệ thống i18n thống nhất. Nhược điểm là cần quản lý namespace keys để tránh trùng.

**Dùng riêng:** cấu hình `MessageSource` chỉ cho validation, ví dụ `validation-messages.properties` và các bản địa phương hóa. Ưu điểm là tách ownership và vòng đời nội dung. Khi dùng nguồn riêng, phải bảo đảm nó có fallback thích hợp và biết provider defaults vẫn được giải quyết đúng.

Một thiết lập riêng có thể dùng:

~~~java
@Bean("validationTextSource")
MessageSource validationTextSource() {
    ReloadableResourceBundleMessageSource source =
            new ReloadableResourceBundleMessageSource();
    source.setBasename("classpath:validation-messages");
    source.setDefaultEncoding("UTF-8");
    source.setFallbackToSystemLocale(false);
    return source;
}

@Bean
LocalValidatorFactoryBean validator(
        @Qualifier("validationTextSource") MessageSource source) {
    LocalValidatorFactoryBean bean = new LocalValidatorFactoryBean();
    bean.setValidationMessageSource(source);
    return bean;
}
~~~

Đoạn trên là **phương án minh họa**, cần imports cho `@Qualifier` và `ReloadableResourceBundleMessageSource`, và không được chép đè lên bean `validator` của ví dụ runnable ở mục 6. Chỉ chọn **một** phương án trong một context để tránh trùng bean definitions.

### 4.4. Không thiết lập hai đường interpolator cùng lúc

Javadoc `LocalValidatorFactoryBean` yêu cầu chọn một trong hai:
- `setValidationMessageSource(messageSource)`; **hoặc**
- `setMessageInterpolator(customInterpolator)`.

Không set cả hai trên cùng factory. Nếu cần một `MessageInterpolator` tùy chỉnh, hãy hiểu cách tạo một interpolator có `ResourceBundleLocator` dựa trên Spring, hoặc dùng API provider phù hợp. Chồng hai cấu hình lên nhau khiến luồng chọn message không rõ ràng.

### 4.5. Đặc biệt: `useCodeAsDefaultMessage`

Nếu cấu hình custom `MessageSource`, không bật `useCodeAsDefaultMessage=true` trên nguồn được truyền vào `LocalValidatorFactoryBean`. Spring Javadoc lưu ý điều này có thể **ngăn fallback tới thông báo mặc định của Hibernate Validator** khi một key không tồn tại.

Ví dụ tránh:

~~~java
ReloadableResourceBundleMessageSource source =
        new ReloadableResourceBundleMessageSource();
source.setBasename("classpath:validation-messages");
source.setUseCodeAsDefaultMessage(true); // Không nên cho validation.
~~~

Nếu provider cần tra key `{jakarta.validation.constraints.NotNull.message}` mà `MessageSource` trả về nguyên code như một message “đã tìm thấy”, cơ chế fallback có thể không diễn ra đúng. Hãy để optional lookup trả “không có” khi key không tồn tại; provider có thể sử dụng bundle defaults của nó.

## 5. Các file messages và luật fallback

### 5.1. Cấu trúc bundle

Với Spring Boot, mặc định basename là `messages` ở root classpath. Đặt:

~~~text
src/main/resources/
  application.properties
  messages.properties
  messages_en.properties
  messages_vi.properties
~~~

`messages.properties` là **bundle gốc** và cũng đóng vai trò fallback khi không có locale-specific entry. Spring Boot auto-config `MessageSource` khi có base bundle thích hợp; nếu chỉ tạo `messages_vi.properties` mà thiếu `messages.properties`, Boot có thể **không auto-config** message source như bạn mong muốn.

### 5.2. `messages.properties`

~~~properties
signup.name.required=Name must not be blank
signup.age.min=Age must be at least {value}
signup.received=Registration received
~~~

### 5.3. `messages_en.properties`

~~~properties
signup.name.required=Name must not be blank
signup.age.min=Age must be at least {value}
signup.received=Registration received
~~~

### 5.4. `messages_vi.properties`

~~~properties
signup.name.required=Họ tên không được để trống
signup.age.min=Tuổi phải từ {value} trở lên
signup.received=Đã nhận đăng ký
~~~

**Chú ý về `{value}`:** đây là tên thuộc tính trong `@Min(value=18)`. Spring `MessageSource` cung cấp template, sau đó Hibernate Validator xử lý substitution của Bean Validation; kết quả kỳ vọng là `"Tuổi phải từ 18 trở lên"`. Không tự thay `{value}` bằng một chuỗi cứng nếu muốn tái dùng quy tắc với nhiều ngưỡng.

Không nhầm `{value}` với `{0}` của `MessageFormat`. Khi gọi `messageSource.getMessage("some.code", new Object[]{18}, locale)`, cú pháp `{0}` có ý nghĩa với chính Spring MessageSource. Nhưng Bean Validation interpolation có tập quy tắc riêng, gồm constraint attributes, bundle parameters và các giới hạn của provider.

### 5.5. `application.properties`

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

- `basename` trỏ đến `messages.properties` và các biến thể ngôn ngữ cùng base.
- `encoding=UTF-8` hỗ trợ file chứa dấu tiếng Việt; cũng nên kiểm tra IDE/build pipeline lưu UTF-8.
- `fallback-to-system-locale=false` giúp hành vi dễ dự đoán: nếu một locale không có bản dịch, quay về base bundle thay vì dùng locale của hệ điều hành nơi server chạy.

Không cấu hình locale mặc định của cả JVM chỉ để thử messages. Trong test, chọn locale theo request hoặc đặt `LocaleContextHolder` với `finally` để không làm rò bối cảnh sang test khác.

### 5.6. Các file `ValidationMessages.properties` khác gì?

Chuẩn Jakarta Validation dự kiến bundle mặc định **`ValidationMessages.properties`**. Khi dùng thẳng:

~~~java
try (ValidatorFactory factory =
        Validation.buildDefaultValidatorFactory()) {
    Validator validator = factory.getValidator();
}
~~~

provider tự xử lý mặc định dựa trên các bundles của Jakarta Validation. Nó **không tự biết Spring bean `messageSource`** trong application context.

Khi gọi `LocalValidatorFactoryBean#setValidationMessageSource`, Spring cắm nguồn messages của ứng dụng vào cơ chế interpolation provider, thay cho con đường mặc định chỉ tra `ValidationMessages.properties`. Nếu một ứng dụng đang có cả hai bộ resources, phải xác định nguồn nào được dùng trong flow nào và test migration. Không copy “tình cờ chạy” của `Validation.buildDefaultValidatorFactory()` sang `LocalValidatorFactoryBean` rồi mặc định chúng đọc cùng một nguồn.

## 6. Project chạy được: Java 17 + Spring Boot 3.5.7 + MVC

Project minh họa chủ động cấu hình `setValidationMessageSource`, truyền cùng validator cho Spring MVC, gửi request với hai locale và kiểm tra bằng `MockMvc`. Dùng `spring-boot-starter-validation` và Spring MVC. Không cần database.

### 6.1. Cây thư mục

~~~text
pom.xml
src/main/
  java/com/example/i18n/
    I18nApplication.java
    SignupRequest.java
    ValidationConfiguration.java
    SignupController.java
    ApiValidationAdvice.java
  resources/
    application.properties
    messages.properties
    messages_en.properties
    messages_vi.properties
src/test/java/com/example/i18n/
  ValidationMessageSourceTest.java
  SignupControllerTest.java
~~~

### 6.2. Maven `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>validation-message-source-demo</artifactId>
    <version>1.0.0</version>

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
</project>
~~~

`spring-boot-starter-web` thiết lập Servlet Spring MVC, `spring-boot-starter-validation` đưa Jakarta Validation provider (thường là Hibernate Validator) vào classpath, `spring-boot-starter-test` cung cấp JUnit và MockMvc.

### 6.3. Main application

~~~java
// src/main/java/com/example/i18n/I18nApplication.java
package com.example.i18n;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class I18nApplication {
    public static void main(String[] args) {
        SpringApplication.run(I18nApplication.class, args);
    }
}
~~~

### 6.4. Request DTO với message templates

~~~java
// src/main/java/com/example/i18n/SignupRequest.java
package com.example.i18n;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class SignupRequest {

    @NotBlank(message = "{signup.name.required}")
    private String name;

    @Min(value = 18, message = "{signup.age.min}")
    private int age;

    // Không định nghĩa message riêng để kiểm tra provider default.
    @Email
    private String email;

    public SignupRequest() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

`@Email` thường chấp nhận `null`; muốn email bắt buộc, thêm `@NotBlank` hoặc `@NotNull` theo yêu cầu. Trong bài, field email giúp kiểm tra **provider default validation message**: không phải mọi constraint đều cần key riêng trong application catalog.

### 6.5. `ValidationConfiguration`: kết nối bean MessageSource với factory

~~~java
// src/main/java/com/example/i18n/ValidationConfiguration.java
package com.example.i18n;

import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ValidationConfiguration {

    @Bean
    public LocalValidatorFactoryBean validator(
            MessageSource messageSource) {

        LocalValidatorFactoryBean factory =
                new LocalValidatorFactoryBean();
        factory.setValidationMessageSource(messageSource);
        return factory;
    }

    @Bean
    public WebMvcConfigurer mvcValidatorConfigurer(
            LocalValidatorFactoryBean validator) {

        return new WebMvcConfigurer() {
            @Override
            public org.springframework.validation.Validator
                    getValidator() {
                return validator;
            }
        };
    }
}
~~~

**Tại sao có hai bean?**

1. Bean `LocalValidatorFactoryBean` minh họa **trực tiếp** `setValidationMessageSource(messageSource)`. Spring khởi tạo provider sau khi set property, và factory có thể được inject để gọi `validator.validate(...)`.
2. `WebMvcConfigurer#getValidator()` bảo đảm MVC argument validation sử dụng đúng factory này. Nhờ vậy `@Valid @RequestBody` ở ví dụ sẽ nhận cùng message bundles như các direct validation tests.

Cấu hình này phục vụ **demo minh bạch**, không phải yêu cầu rằng mọi dự án Spring Boot đều phải tự viết `WebMvcConfigurer`. Trên Spring Boot 3.5, khi Bean Validation provider nằm trên classpath, auto-configuration đã hỗ trợ tích hợp application MessageSource với constraint message parameters. Nếu chỉ muốn dùng `messages.properties` cho các message templates và không cần tùy biến riêng, **nhiều ứng dụng không cần tạo một `LocalValidatorFactoryBean` thủ công**.

Khi đã tự công bố factory và global MVC validator như trên, tránh khai báo thêm một bean `LocalValidatorFactoryBean` khác hoặc một `WebMvcConfigurer` cạnh tranh trả validator khác. Với dự án lớn, cần rà soát bean precedence và test `@Valid` chạy đúng instance.

### 6.6. REST controller

~~~java
// src/main/java/com/example/i18n/SignupController.java
package com.example.i18n;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/signups")
public class SignupController {

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> create(
            @Valid @RequestBody SignupRequest request) {

        return Map.of("status", "accepted");
    }
}
~~~

Nếu name toàn khoảng trắng hoặc age nhỏ hơn 18, Bean Validation chặn handler, Spring MVC thường ném `MethodArgumentNotValidException` vì đây là **validation trên một request object**, không có direct method constraints khác. Handler không tự viết `try/catch` để ném lỗi: Spring MVC kích hoạt validation khi xử lý `@Valid`.

### 6.7. Xử lý lỗi thành API response có cấu trúc

~~~java
// src/main/java/com/example/i18n/ApiValidationAdvice.java
package com.example.i18n;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.LinkedHashMap;
import java.util.Map;

@RestControllerAdvice
public class ApiValidationAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> invalidBody(
            MethodArgumentNotValidException ex) {

        Map<String, String> messages = new LinkedHashMap<>();

        for (FieldError error :
                ex.getBindingResult().getFieldErrors()) {
            messages.putIfAbsent(
                    error.getField(),
                    error.getDefaultMessage());
        }

        return ResponseEntity.badRequest().body(messages);
    }
}
~~~

`FieldError#getDefaultMessage()` ở đây phản ánh message đã nội suy cho locale của request. Chúng ta chỉ trả **tên field + thông báo**, không trả `getRejectedValue()`, raw request body, token hoặc stack trace. Trong API production, cân nhắc mã lỗi ổn định riêng với bản dịch: text không phải contract tốt cho client dùng để branching logic.

Nếu controller có direct method constraints từ Spring MVC 6.1+, có thể nhận thêm `HandlerMethodValidationException`. Demo này cố tình chỉ kiểm tra object-level `@Valid @RequestBody` và xử lý `MethodArgumentNotValidException`; không áp một handler cho mọi loại lỗi.

### 6.8. Đặt bundles vào đúng thư mục

Nội dung của **`src/main/resources/application.properties`**:

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

Nội dung của **`src/main/resources/messages.properties`**:

~~~properties
signup.name.required=Name must not be blank
signup.age.min=Age must be at least {value}
signup.received=Registration received
~~~

Nội dung của **`src/main/resources/messages_en.properties`**:

~~~properties
signup.name.required=Name must not be blank
signup.age.min=Age must be at least {value}
signup.received=Registration received
~~~

Nội dung của **`src/main/resources/messages_vi.properties`**:

~~~properties
signup.name.required=Họ tên không được để trống
signup.age.min=Tuổi phải từ {value} trở lên
signup.received=Đã nhận đăng ký
~~~

Viết chính xác tên bundle `messages_vi.properties` (dấu gạch dưới, **không phải** `messages-vi.properties`) và để chúng dưới root `src/main/resources`; sau khi Maven build, các files cần xuất hiện ở classpath.

### 6.9. Chạy application và gửi HTTP requests

~~~bash
mvn spring-boot:run
~~~

Request tiếng Việt:

~~~bash
curl -i -X POST http://localhost:8080/api/signups \
  -H "Content-Type: application/json" \
  -H "Accept-Language: vi" \
  -d '{"name":" ","age":16,"email":"test@example.com"}'
~~~

Body JSON kỳ vọng (không cam kết thứ tự fields):

~~~json
{
  "name": "Họ tên không được để trống",
  "age": "Tuổi phải từ 18 trở lên"
}
~~~

Request tiếng Anh:

~~~bash
curl -i -X POST http://localhost:8080/api/signups \
  -H "Content-Type: application/json" \
  -H "Accept-Language: en" \
  -d '{"name":" ","age":16,"email":"test@example.com"}'
~~~

Body JSON kỳ vọng:

~~~json
{
  "name": "Name must not be blank",
  "age": "Age must be at least 18"
}
~~~

Cả hai có HTTP **400** vì dữ liệu không hợp lệ. Request hợp lệ như `{"name":"Lan","age":21,"email":"test@example.com"}` nhận JSON `{"status":"accepted"}` và HTTP 200.

**Chú ý:** `Accept-Language` trong ví dụ hoạt động với locale resolution mặc định thường gặp ở Spring MVC/Boot. Nếu ứng dụng tùy biến `LocaleResolver`, một cookie, header khác hoặc cơ chế người dùng đã đăng nhập có thể xác định locale. Không giả định `Accept-Language` luôn có quyền ghi đè một lựa chọn ngôn ngữ được thiết kế riêng.

## 7. Kiểm thử i18n trực tiếp trên LocalValidatorFactoryBean

### 7.1. Test theo Spring LocaleContextHolder

Spring có `LocaleContextMessageInterpolator`, một wrapper áp locale được quản lý bởi Spring lên interpolator của provider. Trong HTTP handler, framework đặt locale request tương ứng; trong một direct unit/integration test ta có thể thiết lập `LocaleContextHolder` tạm thời.

~~~java
// src/test/java/com/example/i18n/ValidationMessageSourceTest.java
package com.example.i18n;

import jakarta.validation.ConstraintViolation;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ValidationMessageSourceTest {

    @Autowired
    LocalValidatorFactoryBean validator;

    private SignupRequest invalidSignup() {
        SignupRequest input = new SignupRequest();
        input.setName(" ");
        input.setAge(16);
        input.setEmail("test@example.com");
        return input;
    }

    private Map<String, String> messages(
            Set<ConstraintViolation<SignupRequest>> violations) {

        return violations.stream().collect(
                Collectors.toMap(
                        v -> v.getPropertyPath().toString(),
                        ConstraintViolation::getMessage));
    }

    @Test
    void vietnameseMessagesAndConstraintAttributes() {
        LocaleContextHolder.setLocale(
                Locale.forLanguageTag("vi"));
        try {
            Map<String, String> errors =
                    messages(validator.validate(invalidSignup()));
            assertEquals(2, errors.size());
            assertEquals("Họ tên không được để trống",
                    errors.get("name"));
            assertEquals("Tuổi phải từ 18 trở lên",
                    errors.get("age"));
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }

    @Test
    void englishMessagesAreResolvedFromSameConstraints() {
        LocaleContextHolder.setLocale(Locale.ENGLISH);
        try {
            Map<String, String> errors =
                    messages(validator.validate(invalidSignup()));
            assertEquals(2, errors.size());
            assertEquals("Name must not be blank",
                    errors.get("name"));
            assertEquals("Age must be at least 18",
                    errors.get("age"));
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }

    @Test
    void originalTemplateRemainsAccessible() {
        LocaleContextHolder.setLocale(Locale.ENGLISH);
        try {
            var violation = validator.validate(invalidSignup())
                    .stream()
                    .filter(v -> "name".equals(
                            v.getPropertyPath().toString()))
                    .findFirst()
                    .orElseThrow();

            assertEquals("{signup.name.required}",
                    violation.getMessageTemplate());
            assertEquals("Name must not be blank",
                    violation.getMessage());
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }

    @Test
    void providerDefaultStillResolvesWithoutCustomKey() {
        LocaleContextHolder.setLocale(Locale.ENGLISH);
        try {
            SignupRequest input = new SignupRequest();
            input.setName("Valid");
            input.setAge(21);
            input.setEmail("not-an-email");

            var violations = validator.validate(input);
            assertEquals(1, violations.size());
            var emailViolation = violations.iterator().next();

            assertEquals("email",
                    emailViolation.getPropertyPath().toString());
            assertTrue(
                    !emailViolation.getMessage().isBlank());
            assertTrue(
                    !emailViolation.getMessage().startsWith("{"));
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
~~~

Điểm cần nhớ:
- `LocaleContextHolder.resetLocaleContext()` trong `finally` tránh ảnh hưởng locale đến test/thread khác.
- Test 1 và 2 kiểm tra **cùng DTO, cùng constraints, khác locale**.
- Test 3 chỉ ra `messageTemplate` và `message` không đồng nhất.
- Test 4 kiểm tra fallback của provider cho `@Email` khi ứng dụng không khai báo custom key riêng; không assert nguyên văn câu của Hibernate Validator vì wording có thể thay đổi theo version/locale.

`LocaleContextHolder` dùng ThreadLocal. Với xử lý bất đồng bộ, Reactor/WebFlux, thread switching hoặc queue consumers, **không tự suy ra locale sẽ tự truyền qua mọi thread**; cần cơ chế locale/context propagation phù hợp và test thực tế. Trong bài này, direct tests chạy trong một thread và luôn reset trong `finally`.

### 7.2. Vì sao không dùng `Validation.buildDefaultValidatorFactory()` trong test này?

Nếu test viết:

~~~java
try (var factory =
        jakarta.validation.Validation.buildDefaultValidatorFactory()) {
    var standalone = factory.getValidator();
    // Không tự kết nối Spring MessageSource vào factory này.
}
~~~

factory thuần Jakarta **không thuộc Spring context**, do đó không nhận bean `messageSource` mà ta cấu hình. Nếu chỉ muốn test việc Bean Validation provider có thể chạy, cách này hợp lệ; nhưng nó **không phải test cho `setValidationMessageSource`**.

Để xác nhận tích hợp đang triển khai, inject chính `LocalValidatorFactoryBean` (hoặc inject `jakarta.validation.Validator` đúng bean) từ Spring context và kiểm tra messages theo locale.

## 8. Kiểm thử HTTP bằng MockMvc

~~~java
// src/test/java/com/example/i18n/SignupControllerTest.java
package com.example.i18n;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Locale;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SignupControllerTest {

    @Autowired
    MockMvc mvc;

    private static final String INVALID_JSON = """
        {"name":" ","age":16,"email":"test@example.com"}
        """;

    @Test
    void vietnameseRequestGetsVietnameseValidationErrors()
            throws Exception {

        mvc.perform(post("/api/signups")
                    .locale(Locale.forLanguageTag("vi"))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(INVALID_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.name")
                        .value("Họ tên không được để trống"))
                .andExpect(jsonPath("$.age")
                        .value("Tuổi phải từ 18 trở lên"));
    }

    @Test
    void englishRequestGetsEnglishValidationErrors()
            throws Exception {

        mvc.perform(post("/api/signups")
                    .locale(Locale.ENGLISH)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(INVALID_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.name")
                        .value("Name must not be blank"))
                .andExpect(jsonPath("$.age")
                        .value("Age must be at least 18"));
    }

    @Test
    void validBodyDoesNotReturnErrors() throws Exception {

        mvc.perform(post("/api/signups")
                    .locale(Locale.ENGLISH)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"name":"Lan","age":21,
                         "email":"test@example.com"}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status")
                        .value("accepted"));
    }
}
~~~

Trong `MockMvc`, `.locale(...)` đặt locale của mock request một cách tường minh để test ổn định, trong khi `curl` ở mục 6 minh họa `Accept-Language` qua HTTP. Đây là **hai cách chọn locale** cho cùng contract. Trong hệ thống có custom locale resolver, test phải dùng đúng cơ chế locale thật của production.

Chạy:

~~~bash
mvn test
~~~

**Kết quả dự kiến: 7 JUnit tests PASS** (4 test trên `LocalValidatorFactoryBean` và 3 test `MockMvc`) nếu toàn bộ mã và bundles được đặt đúng như mục 6–8. Đây là **kết quả kỳ vọng theo API và logic**, không phải báo cáo đã chạy Maven thực tế. Nếu cần chỉ chạy một lớp test:

~~~bash
mvn -Dtest=ValidationMessageSourceTest test
~~~

Test HTTP chứng minh rằng giải quyết message không chỉ hoạt động khi gọi `validator.validate(...)` bằng tay, mà còn hoạt động khi request đi qua `@Valid @RequestBody` của Spring MVC.

## 9. Boot auto-configuration và custom validator: chọn khi nào?

### 9.1. Spring Boot 3.5 có khả năng gì mặc định?

Tài liệu Spring Boot Validation nêu rõ: **application `MessageSource` được dùng khi resolve `{parameters}` trong constraint messages**, cho phép dùng `messages.properties` của ứng dụng trong Bean Validation. Khi đã resolve các parameters đó, provider vẫn thực hiện interpolation.

Do đó, với use case cơ bản:

~~~java
@NotBlank(message = "{signup.name.required}")
private String name;
~~~

và các `messages.properties`/`messages_vi.properties` hợp lệ trên classpath, **bạn có thể không cần viết bean `LocalValidatorFactoryBean` thủ công**. Khung Boot đã hỗ trợ tích hợp. Không viết cấu hình tùy biến chỉ vì thấy tài liệu cũ nói phải dùng `setValidationMessageSource`.

### 9.2. Khi nào cần explicit `setValidationMessageSource`?

Các tình huống có giá trị:
- Muốn tách nguồn text dành riêng cho validation khỏi UI labels.
- Đang cấu hình Spring Framework **không dùng Boot** hoặc tự quản lý validators.
- Cần thay provider settings/custom interpolation một cách rõ ràng.
- Muốn test/kiểm soát chính xác bean factory dùng chung cho controllers và services.
- Đang migrate từ `ValidationMessages.properties` cũ sang một `MessageSource` chung.

Khi tự khai báo, phải bảo đảm ứng dụng không có nhiều factory beans competing, và MVC/WebFlux configuration thực sự sử dụng factory mong muốn.

### 9.3. Chọn `MessageSource` hay tự làm `MessageInterpolator`?

| Nhu cầu | Lựa chọn |
| --- | --- |
| Dịch cùng một message key sang nhiều ngôn ngữ | Spring `MessageSource` |
| Dùng message bundles `messages_vi`/`messages_en` | `MessageSource` |
| Thay thế toàn bộ thuật toán Bean Validation interpolation | `MessageInterpolator` tùy chỉnh |
| Chỉ muốn đổi văn bản cho `@NotBlank` | Khóa `message="{...}"` trong annotations |
| Thay thứ tự/locale resolution trên HTTP | `LocaleResolver`/request locale strategy |
| Thêm rule kiểm tra dữ liệu mới | Jakarta constraint/`ConstraintValidator` hoặc Spring `Validator`, không phải `MessageSource` |

`MessageSource` chỉ cung cấp text; nó không thể bắt đầu kiểm tra một field chưa hề có constraint. Nếu một locale không có bản dịch, chỉnh bundle/fallback; không sửa `ConstraintValidator` để “dịch” lỗi.

## 10. Locale: HTTP request, test, batch job và async

### 10.1. Trong Spring MVC

Ứng dụng MVC có `LocaleResolver`, thường dùng header `Accept-Language` hoặc một cơ chế tùy biến theo cookie/session/profile. `LocalValidatorFactoryBean` sử dụng một `MessageInterpolator` được bọc để lấy **Spring-managed locale** khi phù hợp, qua `LocaleContextHolder`.

~~~text
Accept-Language: vi
       |
       v
Spring MVC LocaleResolver
       |
       v
LocaleContextHolder (locale=vi)
       |
       v
LocalValidatorFactoryBean / MessageInterpolator
       |
       v
messages_vi.properties -> ConstraintViolation message
~~~

Nếu frontend muốn chuyển ngôn ngữ bằng query `?lang=vi`, không chỉ đọc query rồi kỳ vọng message tự đổi; phải cấu hình resolver/interceptor hoặc xử lý locale rõ ràng. Không lấy locale mặc định của server làm chuẩn cho mọi người dùng.

### 10.2. Trong service hoặc command-line job

Một service method không chạy dưới HTTP request có thể dùng JVM default locale hoặc locale đang được gắn vào `LocaleContextHolder`. Nếu cần tiếng Việt cho một tác vụ độc lập, thiết lập context có giới hạn:

~~~java
Locale previous = LocaleContextHolder.getLocale();
try {
    LocaleContextHolder.setLocale(
            Locale.forLanguageTag("vi"));
    // validator.validate(bean)
} finally {
    LocaleContextHolder.setLocale(previous);
}
~~~

Đây là đoạn minh họa, phù hợp khi bạn kiểm soát ngữ cảnh đồng bộ. Nếu muốn khôi phục đầy đủ locale context (bao gồm timezone), lưu và khôi phục `LocaleContext` thay vì chỉ `Locale`; trong test đơn giản có thể dùng `resetLocaleContext()` khi chắc chắn không có context trước đó.

### 10.3. Spring WebFlux và Reactor

Spring WebFlux không nên dựa vào việc ThreadLocal tự di chuyển theo reactive chain: execution có thể đổi thread. Framework WebFlux có cơ chế locale riêng từ `ServerWebExchange` và tích hợp validation phù hợp; khi viết custom reactive infrastructure, kiểm tra cách locale context được truyền vào interpolator và dùng Reactor Context/locale propagation thích hợp.

Bài này dùng MVC cho example runnable nên không khẳng định đoạn `LocaleContextHolder.setLocale(...)` bên trong một async `flatMap` bất kỳ là portable. Với WebFlux, viết integration tests bằng `WebTestClient` có cả `Accept-Language` để xác minh thực tế.

## 11. Những tình huống nâng cao: template, fallback, message codes

### 11.1. Thông báo có `{value}`, `{min}` và `{max}`

Ví dụ:

~~~java
@Size(min = 3, max = 20,
      message = "{signup.username.size}")
private String username;
~~~

Bundle:

~~~properties
signup.username.size=Username must contain {min} to {max} characters
~~~

Sau interpolation, kết quả dự kiến là `Username must contain 3 to 20 characters`. Các từ `min` và `max` là **attribute names của `@Size`**, không phải placeholders thứ tự `{0}`, `{1}`.

Nếu muốn bản dịch tiếng Việt:

~~~properties
signup.username.size=Tên đăng nhập cần từ {min} đến {max} ký tự
~~~

Giữ nguyên tên attributes để provider thay đúng số. Với constraint tùy chỉnh, chỉ những thuộc tính thực sự tồn tại trên annotation mới có thể được thay theo quy tắc provider.

### 11.2. Nội suy EL và an toàn

Hibernate Validator và Bean Validation có những quy tắc nâng cao cho expression language và dynamic values. Không nối trực tiếp input do người dùng nhập vào message template, sau đó cho provider đánh giá nó như một biểu thức. Nội dung bundle là **code/config đáng tin cậy**, còn tên, email, mã sản phẩm do client gửi là **dữ liệu không đáng tin cậy**.

Nếu cần chèn một giá trị động vào error message, sử dụng API constraint validation/provider theo hướng dẫn (ví dụ addMessageParameter khi có hỗ trợ), tránh template injection. Trong đa số API, chỉ cần trả **field + error code + translated message**; không cần in raw rejected values.

### 11.3. Spring `FieldError#getCodes()` không phải messageTemplate

Khi `@Valid @RequestBody` thất bại, Spring có thể cung cấp các codes ưu tiên từ cụ thể đến tổng quát, ví dụ các dạng:

~~~text
NotBlank.signupRequest.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
~~~

Đây là mô hình **message codes cho Spring binding**, có thể khác tùy `MessageCodesResolver`, object name và type. Trong khi đó, `ConstraintViolation#getMessageTemplate()` ở example là `{signup.name.required}`. Đừng lấy code Spring rồi cho rằng nó chắc chắn chính là key `signup.name.required` của Bean Validation.

Ứng dụng có thể dùng `MessageSource` thêm một lần để dịch Spring binding errors (ví dụ `typeMismatch`); đó là **một lượt resolution khác** với thông báo đã được Hibernate Validator interpolated.

### 11.4. Đa ngữ cho binding errors

Khi client gửi `age=abc` vào property Integer/int, lỗi thuộc **conversion**, không phải `@Min(18)`. `LocalValidatorFactoryBean#setValidationMessageSource` chủ yếu kết nối **Bean Validation constraint messages**, không tự biến mọi `typeMismatch` từ `DataBinder` thành câu đã dịch.

Muốn dịch binding errors, cần có keys kiểu `typeMismatch`/`typeMismatch.signupRequest.age` trong Spring `MessageSource` và resolver/controller advice dùng codes phù hợp:

~~~properties
typeMismatch=Invalid value format
typeMismatch.signupRequest.age=Age must be a number
~~~

Bản tiếng Việt:

~~~properties
typeMismatch=Giá trị sai định dạng
typeMismatch.signupRequest.age=Tuổi phải là số
~~~

Đây là cách bổ sung, **không thay thế** `setValidationMessageSource`. Test cả type conversion errors và constraint violations để bảo đảm API đa ngữ thật sự đồng nhất.

### 11.5. Fallback nếu locale/key không tồn tại

Với `spring.messages.fallback-to-system-locale=false`, thiếu `messages_fr.properties` khiến bundle mặc định `messages.properties` có thể cung cấp key. Nếu một key chưa có ở bản `messages_vi`, Spring còn tìm ở các bundle thích hợp theo quy tắc fallback.

Khi không có một message key ở đâu:
- `MessageSource#getMessage(...)` có thể ném `NoSuchMessageException` hoặc trả default tùy overload.
- ResourceBundle locator cho Hibernate Validator thường cần **optional resolution** để provider fallback.
- Nếu template vẫn hiển thị `{signup.name.required}` nguyên văn, kiểm tra cả bundle path, basename, bean instance và provider interpolation.

### 11.6. Đổi locale không có nghĩa recompile annotation

Annotation message template không thay đổi theo locale; provider interpolates thông điệp khi kiểm tra constraint. Không tạo DTO class riêng `SignupRequestVi` và `SignupRequestEn` chỉ để đổi câu lỗi. Giữ rules chung, dịch catalog riêng và để locale resolver quyết định bản dịch.

## 12. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Response hiển thị `{signup.name.required}` | Không tìm được key hoặc validator không dùng MessageSource mong muốn | Kiểm tra basename, bundle, bean factory và annotation template |
| `messages_vi.properties` không được đọc | Sai tên file/thư mục, thiếu base `messages.properties`, sai locale | Đặt đúng `src/main/resources`, kiểm tra Boot message source |
| Tiếng Việt bị lỗi dấu | Encoding của resource bundle/build/editor | Dùng UTF-8, kiểm tra file bytes và `spring.messages.encoding` |
| Thông báo luôn tiếng Anh | Request locale không phải `vi`, default locale/fallback, provider khác | Kiểm tra `LocaleResolver`, `LocaleContextHolder`, integration test |
| `{value}` vẫn nguyên | Bypass Bean Validation interpolation, template không thuộc constraint metadata | Truy qua `LocalValidatorFactoryBean` và provider đúng |
| Test `Validation.buildDefaultValidatorFactory()` không dịch theo `messages_vi` | Factory thuần Jakarta không tự dùng Spring context | Inject `LocalValidatorFactoryBean` từ Spring |
| Dịch `@NotBlank` nhưng `typeMismatch` vẫn tiếng Anh | Binding errors dùng Spring message codes, không chỉ constraint templates | Bổ sung Spring binding error messages |
| Custom bean làm mất `@Valid` trong controller | MVC/WebFlux đang chọn validator khác hoặc bean config ghi đè | Chỉ định global validator phù hợp, test HTTP |
| Provider default `@Email` thành literal code | MessageSource bật `useCodeAsDefaultMessage` hoặc cấu hình interpolation sai | Tắt option ấy, giữ provider fallback |
| Vừa set `validationMessageSource` vừa set `messageInterpolator` | Hai đường cấu hình cạnh tranh | Chọn một; nếu custom interpolator cần Spring bundle locator |
| Locale trong async code không theo request | ThreadLocal không tự propagate | Dùng reactive/context propagation thích hợp và test |
| Message chứa dữ liệu cá nhân | Ghép raw rejected values vào response/log | Trả field/code/message an toàn |
| `MessageSource` tồn tại nhưng khóa không được resolve | Sai key hoặc chỉ đổi bean name, chưa kết nối | Kiểm tra `setValidationMessageSource` hoặc Boot auto config |
| Một bản dịch có `{min}` nhưng annotation không có `min` | Placeholder không khớp constraint attribute | Soát loại annotation và test interpolation |
| Câu Việt/Anh khác quy tắc | Translations drift, reviewer chỉ kiểm tra một locale | Test các locale, dùng error code ổn định và review nội dung |
| Response HTTP 500 cho lỗi nhập liệu thông thường | Exception mapping sai hoặc lỗi runtime provider | Phân biệt binding, method validation, config và domain lỗi |

### Quy trình debug có thể lặp

1. Kiểm tra Spring Boot/Spring Framework version và dependency `spring-boot-starter-validation`.
2. Xác minh bean `MessageSource` thực sự được tạo, classpath chứa `messages.properties` cùng các bản locale.
3. Đọc `@Constraint(message="{...}")`, xác nhận key và attributes.
4. Inject `LocalValidatorFactoryBean`, test trực tiếp bằng `LocaleContextHolder` cho `vi` và `en`.
5. So sánh `ConstraintViolation#getMessageTemplate()` với `getMessage()`.
6. Nếu direct test đúng mà HTTP sai, kiểm tra global MVC/WebFlux validator và resolver chọn locale.
7. Nếu binding error sai ngôn ngữ, kiểm tra Spring `FieldError#getCodes()` riêng.
8. Nếu provider defaults sai, kiểm tra `useCodeAsDefaultMessage` và việc cài hai interpolators.
9. Test fallback cho locale không có bundle và field không có custom message.
10. Đừng sửa string hard-coded trong mỗi controller; sửa ở message catalog và giữ test đa ngữ.

## 13. Checklist code review

- [ ] Các constraint messages cần i18n dùng khóa `{namespace.key}` ổn định, không hard-code text đa ngôn ngữ trong annotations.
- [ ] Có `messages.properties` ở root classpath để Boot auto-config MessageSource, cùng các `messages_vi.properties`/`messages_en.properties`.
- [ ] Chỉ tự tạo `LocalValidatorFactoryBean` khi thật sự cần; nếu có, dùng `setValidationMessageSource` và test wiring.
- [ ] Không cấu hình đồng thời `setValidationMessageSource` và `setMessageInterpolator` trên cùng factory.
- [ ] MessageSource dùng cho validation không bật `useCodeAsDefaultMessage=true`.
- [ ] Các placeholders `{value}`, `{min}`, `{max}` khớp constraint attributes.
- [ ] Locale request được giải quyết rõ ràng; test ít nhất `vi` và `en`, không phụ thuộc JVM default.
- [ ] Test direct `ConstraintViolation` cùng `@Valid` HTTP integration, không chỉ một tầng.
- [ ] Tách Bean Validation messages khỏi typeMismatch/binding errors.
- [ ] API không trả raw rejected values, thông tin cá nhân hoặc stack traces trong validation responses.
- [ ] Kiểm tra fallback khi key/locale thiếu, cũng như provider default messages.
- [ ] Với reactive/async code, có chiến lược locale context propagation tường minh.

## 14. Tài liệu tham khảo

- Spring Framework 6.2, LocalValidatorFactoryBean Javadoc, `setValidationMessageSource`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html
- Spring Framework 6.2, LocaleContextMessageInterpolator Javadoc: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/beanvalidation/LocaleContextMessageInterpolator.html
- Spring Framework 6.2, Bean Validation support: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2, Spring MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Boot 3.5, Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Boot 3.5, Internationalization: https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html
- Jakarta Validation 3.1 specification, Message interpolation: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Hibernate Validator reference, Message interpolation: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/#chapter-message-interpolation
