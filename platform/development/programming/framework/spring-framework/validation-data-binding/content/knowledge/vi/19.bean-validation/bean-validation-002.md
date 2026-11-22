# LocalValidatorFactoryBean: tích hợp Bean Validation provider với Spring

## 1. Mục tiêu: nối chuẩn Jakarta Bean Validation với hạ tầng Spring

`LocalValidatorFactoryBean` trong package `org.springframework.validation.beanvalidation` là cầu nối giữa **Jakarta Bean Validation** và hệ sinh thái **Spring Framework**. Nó khởi tạo một `jakarta.validation.ValidatorFactory` thông qua provider thực thi (ví dụ **Hibernate Validator**), công bố `Validator` mặc định cho ứng dụng, đồng thời chuyển kết quả xác thực thành dạng lỗi mà Spring Data Binding và Spring MVC hiểu được.

Hãy phân biệt ba vai trò:

- **Jakarta Validation API** (`jakarta.validation.*`): định nghĩa `@Valid`, `Validator`, `ConstraintValidator`, `ConstraintViolation` và các annotation chuẩn như `@NotNull`, `@NotBlank`, `@Size`.
- **Bean Validation provider** (thường là thư viện `org.hibernate.validator:hibernate-validator`): tìm metadata constraint, thực thi kiểm tra, nội suy thông báo lỗi, quản lý vòng đời các validator.
- **Spring `LocalValidatorFactoryBean`**: bootstrap và cấu hình provider, đưa nó thành Spring bean, hỗ trợ dependency injection trong custom `ConstraintValidator` và chuyển `ConstraintViolation` sang `Errors`/`FieldError` của Spring.

Sơ đồ luồng:

```text
DTO/bean với @NotBlank, @Size, @Valid, @Constraint ...
                       |
                @Valid / Validator
                       |
          LocalValidatorFactoryBean (Spring bean)
                       |
       jakarta.validation.ValidatorFactory
                       |
       Provider thực thi (ví dụ Hibernate Validator)
                       |
           ConstraintViolation<?> 
                       |
       +---------------+----------------+
       |                                |
 Jak​​arta Validator               Spring Validator
 Set<ConstraintViolation>         Errors / FieldError
       |                                |
 Service, kiểm thử trực tiếp       WebDataBinder, Spring MVC
```

**Cốt lõi:** `LocalValidatorFactoryBean` **không tự trở thành engine xác thực**; nó sử dụng provider thực sự có trên classpath. Đưa mỗi thư viện `jakarta.validation-api` vào dự án chưa đủ để thực hiện validation nếu không có provider.

## 2. Hai hệ interface trên cùng một bean

`LocalValidatorFactoryBean` đồng thời triển khai các contract chính:

| Interface | Mục đích | Cách sử dụng |
| --- | --- | --- |
| `jakarta.validation.ValidatorFactory` | Tạo/tra cứu validator, cấu hình ngữ cảnh | `factory.getValidator()`, `factory.usingContext()` |
| `jakarta.validation.Validator` | Kiểm tra bean bằng Bean Validation | `validator.validate(command)` |
| `org.springframework.validation.Validator` | Kiểm tra bean qua `Errors` | `springValidator.validate(command, errors)` |
| `org.springframework.validation.SmartValidator` | Spring validator có hỗ trợ validation hints/groups | `smartValidator.validate(command, errors, Create.class)` |

Do **cả Jakarta và Spring đều định nghĩa tên `Validator`**, nên trong code thực tế hãy dùng import rõ ràng hoặc fully qualified name:

```java
private final jakarta.validation.Validator jakartaValidator;
private final org.springframework.validation.Validator springValidator;
```

Khác nhau ở kết quả:

```java
// Kiểu Jakarta: tập hợp các vi phạm constraint.
Set<ConstraintViolation<UserInput>> violations =
        jakartaValidator.validate(userInput);

// Kiểu Spring: đưa lỗi vào BindingResult/Errors.
BindingResult errors =
        new BeanPropertyBindingResult(userInput, "userInput");
springValidator.validate(userInput, errors);
```

Hai đoạn trên chỉ minh họa cách gọi, giả định `UserInput` là model đang có và các biến `jakartaValidator`, `springValidator` đã được inject; cần import phù hợp. Spring adapter chuyển `ConstraintViolation` của provider thành `FieldError` hoặc `ObjectError` rồi ghi vào `Errors`. Đây là lý do constraint chuẩn hoạt động cùng `BindingResult` của Spring MVC.

**Không nhầm:** `@Valid` (Jakarta) là dấu yêu cầu validation/cascade theo ngữ cảnh tích hợp; nó **không tự chạy chỉ vì đối tượng vừa được `new`**. Nếu tự khởi tạo object trong code thường, phải chủ động gọi `Validator.validate(...)` hoặc dùng một entry point mà Spring hỗ trợ validation.

## 3. Dependency, phiên bản và cơ chế bootstrap

Với **Spring Framework 6+/Spring Boot 3+**, sử dụng `jakarta.validation.*`. Dự án Spring 5/Boot 2 cũ dùng `javax.validation.*`; trộn annotation `javax` đời cũ với hạ tầng `jakarta` dễ dẫn tới constraint không được nhận diện. Cần chọn dependency phù hợp *cùng một thế hệ API*.

### Spring Boot

Với dự án Spring Boot dùng Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Starter thường cung cấp API và provider Hibernate Validator, kèm các dependency runtime cần thiết theo BOM. **Không cần tự tạo `LocalValidatorFactoryBean` trong hầu hết ứng dụng Boot**: auto-configuration của Boot có thể đăng ký validator mặc định khi Bean Validation provider hiện diện. Nếu tự định nghĩa bean, hãy kiểm tra cấu hình tự động và bean nào thực sự được MVC sử dụng.

### Spring Framework cấu hình trực tiếp

Trong ứng dụng Spring Framework không dùng Boot, khai báo:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationConfiguration {
    @Bean
    public LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
```

Đây là **lớp cấu hình Spring**, cần Spring Context, Jakarta Validation API và provider tương thích trên classpath. Khi ApplicationContext tạo bean, Spring gọi `afterPropertiesSet()`: Spring chuẩn bị cấu hình provider, gọi bootstrap chuẩn Bean Validation, lấy `Validator` mặc định và chuẩn bị adapter. Khi context đóng, `destroy()` đóng `ValidatorFactory` được sở hữu bởi bean.

**Provider được tìm như thế nào?** Theo cơ chế bootstrap chuẩn Jakarta Validation, provider được phát hiện qua service discovery/metadata trong classpath (hoặc được chọn tường minh nếu cấu hình). Nếu không có provider thích hợp, bootstrap thường thất bại; `OptionalValidatorFactoryBean` là biến thể có hành vi bỏ qua khi provider không có, nên tránh dùng nó để che lỗi thiếu dependency trong ứng dụng thực sự cần validation.

## 4. Ví dụ Spring Boot 3.5 và Java 17 có thể chạy

Ví dụ này cho thấy **một bean `LocalValidatorFactoryBean` do Boot cấu hình** phục vụ đồng thời hai API, và cho phép custom `ConstraintValidator` nhận một Spring dependency qua `@Autowired`.

Cấu trúc file:

```text
validation-demo/
├── pom.xml
└── src/main/java/example/validation/ValidationBridgeApplication.java
```

**`pom.xml`** — dùng bản Spring Boot 3.5.8 đã phát hành, Java 17:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>validation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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
```

**`src/main/java/example/validation/ValidationBridgeApplication.java`** — chương trình hoàn chỉnh:

```java
package example.validation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
import jakarta.validation.constraints.NotBlank;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.validation.BeanPropertyBindingResult;

@SpringBootApplication
public class ValidationBridgeApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationBridgeApplication.class, args);
    }

    @Bean
    AllowedPrefixes allowedPrefixes() {
        return new AllowedPrefixes();
    }

    @Bean
    CommandLineRunner demo(
            jakarta.validation.Validator jakartaValidator,
            org.springframework.validation.Validator springValidator) {
        return args -> {
            Registration invalid = new Registration("", "US-42");

            long jakartaErrors =
                    jakartaValidator.validate(invalid).size();
            System.out.println("Jakarta violations: " + jakartaErrors);

            BeanPropertyBindingResult errors =
                    new BeanPropertyBindingResult(
                            invalid, "registration");
            springValidator.validate(invalid, errors);
            System.out.println("Spring field errors: "
                    + errors.getFieldErrorCount());
            System.out.println("Code message: "
                    + errors.getFieldError("code").getDefaultMessage());
        };
    }

    // Dependency bất biến; provider không cần tự tạo nó.
    public static final class AllowedPrefixes {
        boolean accepts(String code) {
            return code.startsWith("VN-");
        }
    }

    @Target(ElementType.FIELD)
    @Retention(RetentionPolicy.RUNTIME)
    @Constraint(validatedBy = AllowedPrefixValidator.class)
    public @interface AllowedPrefix {
        String message() default "code must start with VN-";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
    }

    // SpringConstraintValidatorFactory tạo và inject đối tượng này.
    public static final class AllowedPrefixValidator
            implements ConstraintValidator<AllowedPrefix, String> {

        @Autowired
        private AllowedPrefixes prefixes;

        @Override
        public boolean isValid(
                String value, ConstraintValidatorContext context) {
            return value == null || prefixes.accepts(value);
        }
    }

    public static final class Registration {
        @NotBlank(message = "name required")
        private final String name;

        @AllowedPrefix
        private final String code;

        public Registration(String name, String code) {
            this.name = name;
            this.code = code;
        }

        public String getName() {
            return name;
        }

        public String getCode() {
            return code;
        }
    }
}
```

Chạy ở thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Trong log khởi động Spring Boot sẽ xuất hiện **đúng các dòng do ví dụ in ra**:

```text
Jakarta violations: 2
Spring field errors: 2
Code message: code must start with VN-
```

**Giải thích từng bước:**

1. Boot tìm thấy provider trên classpath nhờ `spring-boot-starter-validation` và cung cấp validator qua cấu hình tích hợp.
2. `@NotBlank` trên `name` bác bỏ chuỗi rỗng; custom `@AllowedPrefix` trên `code` bác bỏ `US-42`.
3. Provider gọi `AllowedPrefixValidator.isValid`. Vì Spring tạo validator constraint thông qua `SpringConstraintValidatorFactory`, field `prefixes` được inject từ bean `AllowedPrefixes`.
4. API Jakarta trả về hai `ConstraintViolation`. API Spring chạy cùng các constraint và ghi hai `FieldError` vào `BeanPropertyBindingResult`.
5. `getFieldError("code")` trả thông báo custom của annotation; chúng ta không phụ thuộc thứ tự của các phần tử trong tập `ConstraintViolation`.

Hàm `isValid` nhận `null` là hợp lệ theo cách viết ở đây vì **quy tắc prefix** chỉ áp dụng khi có giá trị. Nếu `code` là bắt buộc, kết hợp thêm `@NotBlank` hoặc `@NotNull`. Đừng mặc định một constraint kiểm tra format cũng kiểm tra tính bắt buộc.

## 5. Vì sao custom `ConstraintValidator` có thể inject Spring bean?

Jakarta Bean Validation tạo validator constraint qua `ConstraintValidatorFactory`. `LocalValidatorFactoryBean` **mặc định dùng `SpringConstraintValidatorFactory`**, kết nối với `AutowireCapableBeanFactory` của ApplicationContext để khởi tạo và inject các class `ConstraintValidator`. Vì vậy một constraint có thể gọi service tra cứu chính sách, repository hoặc bean cấu hình:

```java
public final class CustomerCodeValidator
        implements ConstraintValidator<ValidCustomerCode, String> {

    @Autowired
    private CustomerCodePolicy policy;

    @Override
    public boolean isValid(
            String value, ConstraintValidatorContext context) {
        return value == null || policy.isAllowed(value);
    }
}
```

Đây là **đoạn minh họa**, giả định đã có annotation `ValidCustomerCode`, interface/class `CustomerCodePolicy` và import tương ứng. Ở đây dùng **field injection để làm rõ cơ chế**, không có nghĩa mọi validator đều phải field-inject. Có thể dùng constructor injection khi Spring tạo đối tượng và các dependency đã được quản lý đúng cách.

**Các điều kiện cần:**

- Lớp validator phải có type/signature phù hợp với `@Constraint(validatedBy = ...)`; annotation constraint cần định nghĩa `message`, `groups` và `payload` theo Jakarta Validation.
- Bean được inject phải có trong cùng Spring context và không gây vòng phụ thuộc.
- Nếu ứng dụng tự gọi `Validation.buildDefaultValidatorFactory()` và dùng factory ấy độc lập, quá trình tạo constraint validator **không đi qua `SpringConstraintValidatorFactory` mặc định của Spring**. Khi đó `@Autowired` có thể không được xử lý như mong muốn.
- Provider có thể cache/reuse các `ConstraintValidator`. `initialize(...)` dùng để chuẩn bị thông tin annotation; `isValid(...)` nên tránh ghi dữ liệu của request vào field dùng chung. Tránh để một instance mutable chứa thông tin của lần validate trước; bảo đảm thread safety của state và các dependency.
- Không nhất thiết gắn `@Component` vào từng class validator constraint; mặc định factory có thể tạo và autowire chúng theo nhu cầu. Nếu gắn thêm stereotype, phải hiểu provider vẫn có thể tạo các instance riêng, thay vì dùng đúng singleton bean mà bạn tưởng.

Việc Spring hỗ trợ inject chỉ giải quyết **cách tạo đối tượng và nối dependency**, không thay thế contract về concurrency, giới hạn API hoặc validation logic của provider.

## 6. Tích hợp với Spring MVC và `WebDataBinder`

Khi một request được bind:

1. Spring đọc JSON qua `HttpMessageConverter` hoặc bind form/query parameters qua cơ chế binding tương ứng.
2. Spring kiểm tra conversion/binding và nhận diện dấu `@Valid`/`@Validated` tại vị trí hỗ trợ.
3. MVC gọi validator đã cấu hình cho request/model; thông thường là một `LocalValidatorFactoryBean` (nếu provider hiện diện).
4. Provider kiểm tra constraint, và Spring chuyển các violation thành lỗi trên `BindingResult`.
5. Controller có thể xử lý `BindingResult` ngay tại method hoặc để cơ chế exception handling trả phản hồi lỗi.

Ví dụ **đoạn controller** trong Spring MVC (giả sử `RegistrationRequest` có các annotation Bean Validation trên field/getter):

```java
@PostMapping("/registrations")
public ResponseEntity<?> create(
        @Valid @RequestBody RegistrationRequest body,
        BindingResult errors) {

    if (errors.hasErrors()) {
        var messages = errors.getFieldErrors().stream()
                .map(e -> e.getField() + ": " + e.getDefaultMessage())
                .toList();
        return ResponseEntity.badRequest().body(messages);
    }
    return ResponseEntity.ok().build();
}
```

Đây là **phương thức minh họa không độc lập**, cần class controller, model, import `jakarta.validation.Valid`, `org.springframework.validation.BindingResult`, `org.springframework.http.ResponseEntity` và các Spring MVC annotation tương ứng. Khi dùng cách xử lý lỗi này, đặt `BindingResult` **ngay sau đối số được validate**. Nếu không có đối số `Errors`/`BindingResult` liền kề và validation thất bại, Spring MVC thường ném một exception dành cho đối số không hợp lệ (ví dụ `MethodArgumentNotValidException`). Với **method validation** có constraint trực tiếp trên tham số hoặc giá trị trả về, cơ chế/loại exception có thể khác theo phiên bản và chữ ký phương thức (ví dụ `HandlerMethodValidationException` trong MVC hiện đại).

`@Validated` của Spring cho phép chỉ định **validation groups** khi cần. Trong Spring MVC hiện đại, validation method-level được hỗ trợ tích hợp; việc đặt `@Validated` ở cấp class của controller có thể kích hoạt cơ chế proxy/AOP thay vì cơ chế tích hợp mới. Vì vậy chỉ thêm `@Validated` ở cấp class khi thật sự biết mình cần kiểu method validation nào.

### Spring MVC chọn validator nào?

Trong cấu hình MVC thông thường, nếu có Bean Validation provider trên classpath, Spring có thể đăng ký `LocalValidatorFactoryBean` làm **global validator**; Spring Boot cũng có tự động cấu hình riêng. Nếu muốn dùng một validator đã tùy biến, có thể khai báo qua `WebMvcConfigurer#getValidator()`:

```java
@Configuration
public class MvcValidatorConfiguration implements WebMvcConfigurer {
    private final LocalValidatorFactoryBean validator;

    public MvcValidatorConfiguration(LocalValidatorFactoryBean validator) {
        this.validator = validator;
    }

    @Override
    public org.springframework.validation.Validator getValidator() {
        return validator;
    }
}
```

Đây là **lớp cấu hình minh họa**; cần import `@Configuration`, `WebMvcConfigurer`, `LocalValidatorFactoryBean` và bảo đảm thực sự có bean validator được inject. Dùng khi cần kiểm soát MVC validator đang hoạt động, **không thêm vào mọi Boot app** nếu auto-configuration đã dùng đúng bean.

Controller có thể gắn validator cục bộ với `@InitBinder`/`WebDataBinder.addValidators(...)` cho một model cụ thể; những validator đó cũng có thể chạy cùng global validator theo cấu hình. Không thay thế global validator một cách vô tình khi nghiệp vụ vẫn cần các constraint Jakarta.

## 7. Cơ chế chuyển `ConstraintViolation` sang Spring `Errors`

Ví dụ một model có:

```java
@NotBlank(message = "Name is required")
private String name;

@Size(min = 2, max = 16)
private String nickname;
```

Với `name=""` và `nickname="X"`, API Jakarta có thể cho hai `ConstraintViolation` mang các thông tin:

- `getPropertyPath()`: ví dụ `name` hoặc `nickname`.
- `getMessage()`: thông báo lỗi đã nội suy.
- `getMessageTemplate()`: mẫu gốc, ví dụ `{jakarta.validation.constraints.Size.message}`.
- `getInvalidValue()` và `getConstraintDescriptor()`: giá trị sai và metadata constraint.

Spring adapter đọc các vi phạm và đăng ký thành `FieldError`/`ObjectError` trong `Errors`; gọi `errors.getFieldErrors("name")` hoặc `errors.getAllErrors()` theo yêu cầu UI/API. `FieldError` chứa field, rejected value, code và thông báo đã nội suy, cho phép Spring MVC hiển thị lỗi cạnh input.

**Khác biệt rất quan trọng:**

- **Type conversion/binding error** xảy ra khi dữ liệu không chuyển sang kiểu target được, ví dụ `"abc"` gán vào `Integer`. Nó không phải `ConstraintViolation` do `@Min` tạo.
- **Bean Validation error** xảy ra khi đối tượng đã có dữ liệu và quy tắc constraint thất bại.
- Có thể tồn tại cả hai nhóm lỗi trong `BindingResult` của cùng lần bind. Controller không nên giả định mọi `FieldError` đều là lỗi từ Jakarta Validation.

Khi dùng API Jakarta trực tiếp (ở service hoặc test), bạn nhận `Set<ConstraintViolation<T>>` và tự quyết định cách trả lỗi. Khi dùng Spring binder, nên tận dụng `BindingResult`, `MessageCodesResolver` và cơ chế xử lý ngoại lệ của ứng dụng.

## 8. Constraint groups và validation lồng nhau

### Nhóm validation

Jakarta Validation có nhóm mặc định `jakarta.validation.groups.Default`. Muốn tách quy tắc tạo mới và sửa:

```java
public interface OnCreate {}

public class AccountInput {
    @NotBlank(groups = OnCreate.class)
    private String password;
}
```

Đây là các **khai báo minh họa**, cần import `@NotBlank` và đặt class/interface trong source phù hợp. Tại controller:

```java
@PostMapping("/accounts")
public void create(@Validated(OnCreate.class)
                   @RequestBody AccountInput input) {
    // ...
}
```

Với `SmartValidator`, validation hints thường được dùng làm nhóm:

```java
BindingResult errors =
        new BeanPropertyBindingResult(input, "accountInput");
smartValidator.validate(input, errors, OnCreate.class);
```

Đây là đoạn trích có các biến đã được khởi tạo. **Lưu ý nhóm được chọn:** nếu chỉ yêu cầu `OnCreate`, các constraint chỉ thuộc `Default` không tự động chạy trừ khi nhóm/lược đồ nhóm được cấu hình phù hợp (ví dụ group inheritance/sequence). Hãy kiểm thử kết quả thực tế thay vì cho rằng mọi annotation luôn chạy.

### Cascade `@Valid`

`@Valid` trên thuộc tính nested kích hoạt kiểm tra đối tượng bên trong:

```java
public class CheckoutRequest {
    @NotNull
    @Valid
    private Address deliveryAddress;
}

public class Address {
    @NotBlank
    private String city;
}
```

Đây là đoạn class minh họa. Nếu thiếu `@Valid`, provider thường chỉ kiểm tra constraint đặt trên thuộc tính `deliveryAddress` chứ không tự duyệt quy tắc trên `Address.city`. Nếu `deliveryAddress == null` thì `@Valid` không làm nó thành bắt buộc; `@NotNull` xử lý phần đó.

**Group sequence**, group conversion và cascaded validation cần được thiết kế khi dữ liệu phức tạp, nhưng chúng là tính năng của **Bean Validation provider**, không phải logic riêng mà `LocalValidatorFactoryBean` tự triển khai.

## 9. Thông báo lỗi và i18n: `ValidationMessages.properties` vs Spring `MessageSource`

Thông thường, provider nội suy thông báo constraint từ `ValidationMessages.properties` ở classpath và từ các message mặc định của provider. Ví dụ:

```properties
# src/main/resources/ValidationMessages.properties
user.name.required=Name must not be blank
user.code.invalid=Code must start with VN-
```

Annotation:

```java
@NotBlank(message = "{user.name.required}")
private String name;
```

Provider giải quyết message template `{user.name.required}` thành chuỗi tương ứng.

Nếu muốn dùng chung **Spring `MessageSource`** cho thông báo validation, `LocalValidatorFactoryBean` có setter:

```java
@Bean
public LocalValidatorFactoryBean validator(MessageSource messageSource) {
    LocalValidatorFactoryBean factory =
            new LocalValidatorFactoryBean();
    factory.setValidationMessageSource(messageSource);
    return factory;
}
```

Đây là **đoạn khai báo Spring bean**, cần import `@Bean`, `MessageSource`, `LocalValidatorFactoryBean` và cấu hình `messageSource` thực sự có các key mong muốn. Javadoc Spring lưu ý tích hợp `setValidationMessageSource` dựa vào khả năng của Hibernate Validator/`ResourceBundleMessageInterpolator`; khi đổi provider, phải kiểm tra tương thích. **Không gọi `setMessageInterpolator(...)` và `setValidationMessageSource(...)` đồng thời**: cả hai cùng chi phối message interpolation. Cấu hình `MessageSource` dùng cho validator nên cho phép fallback hợp lý, tránh `useCodeAsDefaultMessage=true` làm mất thông báo mặc định của provider.

Có hai tầng thông báo:

1. Provider nội suy `ConstraintViolation.getMessage()` từ key constraint.
2. Spring tạo error codes/messages cho `BindingResult` để UI hoặc handler có thể dùng `MessageSource` hiển thị thông báo theo field, object và locale.

Không nhầm việc đặt tên key constraint với cơ chế Spring `MessageCodesResolver`; chúng có thể phối hợp nhưng không phải cùng một API.

## 10. Các điểm tùy biến chính của `LocalValidatorFactoryBean`

| API/cấu hình | Tác dụng | Khi cần |
| --- | --- | --- |
| `setProviderClass(...)` | Chỉ định provider class cụ thể | Có nhiều provider, cần chọn rõ |
| `setValidationProviderResolver(...)` | Thay cơ chế tìm provider | Môi trường classloader/plugin đặc biệt |
| `setConstraintValidatorFactory(...)` | Thay cách tạo custom constraint validator | Factory tùy biến; tránh làm mất cơ chế Spring DI |
| `setValidationMessageSource(...)` | Dùng Spring messages cho nội suy constraint | Đồng bộ i18n với ứng dụng |
| `setMessageInterpolator(...)` | Cung cấp bộ nội suy Jakarta tùy biến | Quy tắc message riêng |
| `setMappingLocations(...)` | Nạp mapping constraint từ XML resource | Hệ thống dùng XML constraint mapping |
| `setValidationProperties(...)` hoặc `setValidationPropertyMap(...)` | Chuyển thuộc tính cấu hình cho provider | Thiết lập provider-specific |
| `setTraversableResolver(...)` | Quy tắc truy cập/đi qua graph khi validate | Tích hợp persistence hoặc ngữ cảnh đặc biệt |
| `setParameterNameDiscoverer(...)` | Tùy chỉnh cách tra tên tham số | Kiểm tra method/constructor constraints |
| `setConfigurationInitializer(...)` | Callback tùy chỉnh `jakarta.validation.Configuration<?>` trước build | Cần truy cập tùy chọn bootstrap đặc biệt |

Những setter này phải được cấu hình **trước khi Spring hoàn tất khởi tạo validator bean**. Ví dụ:

```java
@Bean
LocalValidatorFactoryBean customValidator() {
    LocalValidatorFactoryBean factory =
            new LocalValidatorFactoryBean();
    factory.setValidationPropertyMap(
            Map.of("hibernate.validator.fail_fast", "true"));
    return factory;
}
```

Đoạn **bean minh họa** cần import `java.util.Map` và annotation Spring. `hibernate.validator.fail_fast` là thuộc tính riêng của **Hibernate Validator**, không phải thuộc tính chung được mọi Bean Validation provider bảo đảm. Chế độ fail-fast có thể dừng sớm khi gặp vi phạm, do đó **không dùng số lượng/thứ tự lỗi cố định khi tính năng này bật**.

**Cân nhắc trước khi thay provider:** Hibernate Validator là implementation của Jakarta Validation, khác thư viện Hibernate ORM/JPA. Việc có Hibernate ORM không đồng nghĩa luôn có đúng Bean Validation provider tương thích; hãy kiểm tra dependency runtime. Nếu có nhiều provider, thứ tự lựa chọn mặc định không nên được coi là quy tắc nghiệp vụ; hãy chọn provider rõ ràng khi cần tính xác định.

## 11. Vòng đời, hiệu năng và thread safety

`LocalValidatorFactoryBean` được quản lý như Spring bean và thường sống suốt ApplicationContext:

1. Khởi tạo: Spring nhận cấu hình, ApplicationContext và `ConstraintValidatorFactory`.
2. Bootstrap provider: tạo `ValidatorFactory`, lấy validator mặc định.
3. Sử dụng: nhiều service/binder/controller có thể tái sử dụng cùng bean `Validator` cho các lần xác thực độc lập.
4. Dọn dẹp: khi Spring context đóng, `LocalValidatorFactoryBean` giải phóng underlying factory.

**Nên** tái sử dụng `ValidatorFactory`/`Validator` đã cấu hình; liên tục tạo factory mới cho từng request là tốn kém và dễ làm sai dependency/lifecycle. Provider chịu trách nhiệm quản lý cache metadata và các instance constraint validator theo quy ước API.

**Không nên** lưu target bean đang được validate hoặc dữ liệu request trong field mutable của một custom `ConstraintValidator` có thể tái sử dụng. Nếu constraint cần tham số từ annotation, lưu thông tin cấu hình ổn định trong `initialize(...)`; nếu cần service bên ngoài, inject một service có chính sách thread safety rõ ràng. Với tác vụ I/O, kiểm tra external service có phù hợp trong luồng validation hay không; việc tra DB trong mỗi constraint có thể tạo query lặp, làm tăng độ trễ, khó test và dẫn đến tương tác transaction ngoài ý muốn.

**Không khởi tạo validator thủ công trong business method** khi có sẵn Spring-managed bean:

```java
// Tránh làm điều này lặp lại trên từng request:
ValidatorFactory factory = Validation.buildDefaultValidatorFactory();
try {
    Validator validator = factory.getValidator();
    validator.validate(input);
} finally {
    factory.close();
}
```

Đây là đoạn Java minh họa; nó không dùng Spring bean đang có, và cách tạo factory độc lập không tự có `SpringConstraintValidatorFactory` để inject dependency. Thay bằng dependency injection của `jakarta.validation.Validator` do Spring quản lý.

## 12. Validation ở service: phân biệt đối tượng và method

`Validator.validate(bean)` kiểm tra constraint trên **đối tượng cụ thể** tại thời điểm gọi; không tự kiểm tra mọi đối số của mọi method.

Đối với method/constructor constraints (ví dụ `@NotNull` trên tham số service method hoặc `@Min` trên giá trị trả về), có hai cơ chế đáng phân biệt:

- Jakarta Validation có **`ExecutableValidator`** qua `validator.forExecutables()`, cho phép gọi validate parameter/return value rõ ràng.
- Spring có hỗ trợ **method validation** qua `MethodValidationPostProcessor` và các cơ chế tích hợp liên quan; `@Validated` trên Spring-managed service thường dùng với AOP proxy trong cấu hình thích hợp. Không giả định annotation trên một lời gọi nội bộ (`this.someMethod()`) tự đi qua proxy. Với Spring MVC hiện đại, method validation ở controller có thêm cơ chế tích hợp riêng.

Đây là **một vùng tích hợp có cấu hình và phiên bản cụ thể**. Có `LocalValidatorFactoryBean` không có nghĩa mọi method tự động được kiểm tra chỉ nhờ gắn constraint. Hãy kiểm tra cách kích hoạt method validation và viết test thực sự gọi qua Spring bean/proxy khi cần.

## 13. Kiểm thử đúng các lớp tích hợp

Các tầng cần test khác nhau:

**A. Provider + custom constraint:** dùng `@SpringBootTest` hoặc ApplicationContext gọn nhẹ để inject `jakarta.validation.Validator`; tạo model sai và gọi `validate(...)`. Khẳng định violation property path và message; nếu kiểm tra custom dependency, mock/test bean bên ngoài theo cách nhất quán.

**B. Bridge sang Spring:** inject `org.springframework.validation.Validator`, tạo `BeanPropertyBindingResult` và gọi `validate(target, errors)`; kiểm tra `hasFieldErrors("code")`/`getFieldErrorCount()`. Điều này bắt lỗi khi cấu hình provider hoạt động nhưng Spring adapter không được sử dụng.

**C. MVC request flow:** test endpoint bằng `MockMvc` để xác nhận `@Valid`/`@Validated` kích hoạt và error response đúng. Đặc biệt, kiểm tra vị trí `BindingResult` và cơ chế exception handler.

**D. Nhóm/cascade:** test `@Valid` trên nested bean, `@Validated(SomeGroup.class)`, null nested field và các constraint chỉ thuộc `Default`.

**E. i18n:** truyền locale, kiểm tra key message thực sự được nội suy; không chỉ khẳng định provider trả về một chuỗi mặc định.

**F. Vòng đời/DI:** test custom `ConstraintValidator` có dependency Spring, và xác nhận không tạo một validator factory thứ hai ngoài context trong đường xử lý chính.

Ví dụ test ngắn ở tầng Jakarta (đây là **method minh họa** với các bean đã sẵn):

```java
var violations = jakartaValidator.validate(invalidRegistration);
assertEquals(2, violations.size());
assertTrue(violations.stream()
        .anyMatch(v -> v.getPropertyPath().toString().equals("code")));
```

Cần import hoặc static import assertion từ JUnit 5, có đối tượng `invalidRegistration`, `jakartaValidator` đã được inject và test dependency phù hợp. **Thứ tự phần tử trong `Set<ConstraintViolation>` không được bảo đảm**; kiểm tra theo path/message thay vì theo phần tử thứ nhất.

## 14. Lỗi cấu hình hay gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `NoProviderFoundException` khi tạo factory | Chỉ có API, thiếu implementation | Bổ sung provider tương thích; với Boot dùng starter validation |
| Constraint bị bỏ qua | Import `javax.validation.*` cũ hoặc quên `@Valid`/`@Validated` tại điểm kích hoạt | Đồng bộ Jakarta/Spring version; xác minh đường chạy validation |
| `@Autowired` trong custom validator là null | Tạo `ValidatorFactory` độc lập hoặc thay default factory | Dùng Spring-managed `LocalValidatorFactoryBean`/`SpringConstraintValidatorFactory` |
| Provider chạy nhưng `BindingResult` không có lỗi | MVC đang dùng validator khác hoặc không kích hoạt binding validation | Kiểm tra global/local validators, annotation và chính xác đối tượng bind |
| Hai bean kiểu `Validator` gây ambiguous injection | Boot auto config và bean cấu hình thủ công cùng tồn tại | Loại cấu hình trùng, đặt `@Primary` hoặc `@Qualifier` khi thật cần |
| `@Size` không bắt null | Constraint size mặc định cho null là hợp lệ | Kết hợp `@NotNull`/`@NotBlank` |
| Nested object không được kiểm tra | Quên `@Valid` trên field nested | Đặt cascade `@Valid` và kiểm thử path nested |
| Validation groups cho kết quả thiếu | Chỉ chọn một group khác `Default` | Kiểm tra khai báo groups và cách kích hoạt |
| Thông báo key không được nội suy | Thiếu resource bundle hoặc cấu hình `MessageSource`/provider sai | Kiểm tra base name, locale, nội suy và fallback |
| Test custom validator chạy độc lập nhưng MVC khác | MVC dùng cấu hình validator khác, hoặc test không tải context | Test với Spring ApplicationContext và `MockMvc` |
| Validation chậm bất thường | Tạo factory lặp, constraint truy cập DB/I/O nhiều | Chia sẻ validator bean, tối ưu chính sách lookup |
| Concurrent request làm sai logic custom constraint | ConstraintValidator giữ mutable request state | Giữ `isValid` stateless, dependency được quản lý thread-safe |

**Chẩn đoán theo thứ tự:** (1) có provider không? (2) Spring có đúng bean `LocalValidatorFactoryBean` không? (3) entry point có thực sự gọi validation không? (4) constraint có đúng annotation/type/group không? (5) custom `ConstraintValidatorFactory` và injection có hoạt động không? (6) Spring MVC đang dùng validator nào? (7) lỗi conversion có bị nhầm với validation không?

## 15. Tự kiểm tra

**1. Chỉ thêm `jakarta.validation-api` đã đủ để `@NotBlank` chạy chưa?** Chưa. API mô tả constraint; cần provider tương thích và một entry point gọi validation.

**2. Vì sao có thể inject `jakarta.validation.Validator` lẫn `org.springframework.validation.Validator` từ cùng một Spring bean?** Vì `LocalValidatorFactoryBean` triển khai/cung cấp cả API Jakarta và adapter Spring; nó chuyển vi phạm Jakarta thành `Errors` khi được gọi theo giao diện Spring.

**3. `@Autowired` trong custom `ConstraintValidator` đến từ đâu?** Từ `SpringConstraintValidatorFactory` do `LocalValidatorFactoryBean` cấu hình mặc định, sử dụng Spring bean factory.

**4. Có thể tạo `Validation.buildDefaultValidatorFactory()` mỗi request để thay Spring bean không?** Không nên: tốn nguồn lực và bỏ qua cấu hình/injection của Spring nếu không cấu hình lại thủ công.

**5. `@Valid` trên field kiểu `Address` đã khiến field null trở thành lỗi chưa?** Chưa; `@Valid` chỉ cascade khi có đối tượng. Kết hợp `@NotNull` để bắt buộc tồn tại.

**6. `@Validated(OnCreate.class)` có luôn chạy mọi constraint thuộc `Default` không?** Không. Phải xem group selection và quan hệ group cụ thể.

**7. Vì sao không nên assert phần tử đầu tiên của `Set<ConstraintViolation>`?** Vì thứ tự không được API bảo đảm; assert theo path, constraint hoặc message.

**Ghi nhớ:** `LocalValidatorFactoryBean` là **một Spring bean khởi tạo và kết nối provider**, cho phép dùng **chung một nền tảng Bean Validation** ở các tầng Jakarta, Spring Binding, MVC và custom constraint có dependency injection.

## Tài liệu chính thức

- Spring Framework Reference — Java Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework Reference — Spring Validation: https://docs.spring.io/spring-framework/reference/core/validation/validator.html
- Spring Framework Reference — MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html
- Spring Framework Reference — MVC Validation & Method Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework API — LocalValidatorFactoryBean: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html
- Spring Framework API — SpringConstraintValidatorFactory: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/SpringConstraintValidatorFactory.html
- Jakarta Validation specification: https://jakarta.ee/specifications/bean-validation/
- Hibernate Validator documentation: https://hibernate.org/validator/documentation/
