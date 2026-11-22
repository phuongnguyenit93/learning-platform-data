# Tiêm phụ thuộc qua SpringConstraintValidatorFactory

Khi viết **ràng buộc tùy chỉnh** (custom constraint) bằng Jakarta Validation trong Spring Framework, lớp `ConstraintValidator` đôi khi cần dùng một thành phần do Spring quản lý: service, repository, cấu hình, clock hoặc một chính sách nghiệp vụ. Ví dụ, validator kiểm tra mã khách hàng có tồn tại trong danh mục cho phép. Nếu Jakarta Validation provider tự khởi tạo validator bằng cơ chế mặc định, dependency của Spring có thể không được tiêm và validator thất bại khi chạy.

`SpringConstraintValidatorFactory` giải quyết điểm giao này: nó là một triển khai `jakarta.validation.ConstraintValidatorFactory`, dùng `AutowireCapableBeanFactory` của Spring để **tạo và chuẩn bị các instance `ConstraintValidator`** khi Jakarta Validation provider yêu cầu. Vì vậy constructor injection, `@Autowired` và các cơ chế tiêm phụ thuộc có thể hoạt động trong custom validator.

Điều quan trọng là phân biệt:

- `@Constraint` và `ConstraintValidator` định nghĩa **kiểm tra điều gì**.
- `SpringConstraintValidatorFactory` quyết định **validator được tạo và tiêm dependency như thế nào**.
- `LocalValidatorFactoryBean` kết nối **Spring Validation API** với **Jakarta Validation provider** và có thể dùng factory của Spring.
- `@Valid`, `@Validated`, hoặc lệnh `Validator.validate(...)` quyết định **khi nào quá trình kiểm tra được kích hoạt**.

Factory không tự tạo quy tắc validation, không tự quét yêu cầu HTTP và không tự gọi `isValid` mỗi khi giá trị Java thay đổi.

## 1. Vì sao custom validator cần dependency injection?

Xem một constraint kiểm tra mã tài liệu có nằm trong danh mục nghiệp vụ được cho phép. Có hai trách nhiệm riêng:

1. `AllowedCodeCatalog` chứa/chọn chính sách danh mục được Spring quản lý.
2. `RegisteredCodeValidator` áp dụng chính sách đó cho từng giá trị cần validate.

Validator chỉ cần hỏi `catalog.contains(code)`. Nhờ tiêm phụ thuộc, chính sách có thể thay đổi thành bean đọc cấu hình, cache hoặc repository mà không thay đổi API của constraint. Ví dụ này sử dụng một danh mục trong bộ nhớ để minh họa rõ cơ chế mà không yêu cầu database.

**Sai lầm thường gặp:** nghĩ rằng cứ thêm `@Autowired` vào `ConstraintValidator` thì Jakarta Validation provider luôn tiêm được bean. Điều đó chỉ đúng khi đường khởi tạo validator đang sử dụng một `ConstraintValidatorFactory` tương thích Spring. Nếu code tự gọi `Validation.buildDefaultValidatorFactory()` với cấu hình mặc định, provider không đương nhiên biết về `ApplicationContext` của Spring.

## 2. Đường đi của một lần validation

~~~text
Validator.validate(bean)
         |
         v
Spring LocalValidatorFactoryBean
         |
         v
Jakarta Validation provider (ví dụ Hibernate Validator)
         |
         | tìm constraint descriptor
         | yêu cầu instance ConstraintValidator
         v
ConstraintValidatorFactory.getInstance(RegisteredCodeValidator.class)
         |
         v
SpringConstraintValidatorFactory
         |
         v
AutowireCapableBeanFactory.createBean(RegisteredCodeValidator.class)
         |
         | constructor injection / Spring BeanPostProcessors
         v
RegisteredCodeValidator(AllowedCodeCatalog)
         |
         | provider gọi initialize(...) khi cần
         | provider gọi isValid(value, context)
         v
ConstraintViolation (nếu không hợp lệ)
~~~

Sau khi không còn cần instance, provider có thể gọi `ConstraintValidatorFactory.releaseInstance(...)` để trả lại vòng đời cho factory. Trong triển khai Spring, `SpringConstraintValidatorFactory` dùng bean factory để tạo instance và thực hiện hủy bean khi được release. **Không giả định mỗi lần `validate` đều tạo một validator mới**: provider có thể cache và dùng lại các instance sau khi khởi tạo.

| Thành phần | API/package | Vai trò |
|---|---|---|
| `ConstraintValidator<A, T>` | `jakarta.validation` | Logic xác thực annotation `A` đối với kiểu `T` |
| `ConstraintValidatorFactory` | `jakarta.validation` | Hợp đồng tạo và giải phóng validator instances |
| `SpringConstraintValidatorFactory` | `org.springframework.validation.beanvalidation` | Factory dùng Spring để tạo/autowire validator |
| `AutowireCapableBeanFactory` | `org.springframework.beans.factory.config` | Tạo instance, tiêm dependency và chạy các bean post-processors |
| `LocalValidatorFactoryBean` | `org.springframework.validation.beanvalidation` | Bean `Validator` của Spring/Jakarta, cấu hình và bootstrap provider |
| `Validator` | `jakarta.validation` | API gọi `validate(...)`, `validateProperty(...)`, `validateValue(...)` |

Trong Spring Boot có dependency validation starter và provider phù hợp, auto-configuration thường tạo `LocalValidatorFactoryBean` giúp custom validators được autowire. Với Spring Framework không dùng Boot, ứng dụng có thể khai báo `LocalValidatorFactoryBean` như một bean; khi được Spring quản lý, nó mặc định dùng `SpringConstraintValidatorFactory` phù hợp nếu không bị thay thế bởi một factory khác.

## 3. Ví dụ chạy được: kiểm tra mã bằng service của Spring

Ví dụ dùng **Java 17+**, Spring Boot 3.x và namespace `jakarta.validation`. Các file Java nằm cùng package `com.example.validation`. Ứng dụng dùng constructor injection nên sẽ không thể xây dựng `RegisteredCodeValidator` chỉ với constructor rỗng.

### 3.1. Dependency trong Gradle

Trong một project Spring Boot đã có Spring Boot Gradle plugin và quản lý phiên bản dependency, thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Starter cung cấp Jakarta Validation API, provider triển khai và tích hợp auto-configuration của Boot. Ví dụ command `./gradlew bootRun` ở cuối phần này giả định project có Gradle wrapper, Spring Boot plugin và class chính như đoạn mã dưới đây; **không thể chỉ chạy `javac` trên các file độc lập vì chúng phụ thuộc thư viện Spring/Jakarta**.

Nếu tạo project mới, chọn Spring Boot 3.x, Java 17+, build tool Gradle và dependency **Validation**. Trong Spring Boot 2.x, package Bean Validation phổ biến là `javax.validation`; không trộn mã `javax.validation.*` từ Boot 2 với `jakarta.validation.*` của Boot 3/Spring 6.

### 3.2. Bean cung cấp chính sách — `AllowedCodeCatalog.java`

~~~java
package com.example.validation;

import java.util.Set;
import org.springframework.stereotype.Service;

@Service
public class AllowedCodeCatalog {

    private final Set<String> allowed = Set.of("SPR-01", "SPR-02");

    public boolean contains(String code) {
        return allowed.contains(code);
    }
}
~~~

`@Service` đăng ký bean để Spring quản lý và tiêm vào các thành phần khác. Danh mục là immutable nên an toàn khi nhiều lần validation cùng đọc; trong ứng dụng thực, có thể thay bằng adapter cache/repository với chiến lược thời gian đáp ứng thích hợp.

### 3.3. Định nghĩa constraint — `RegisteredCode.java`

~~~java
package com.example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Constraint(validatedBy = RegisteredCodeValidator.class)
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
public @interface RegisteredCode {

    String message() default "Mã không nằm trong danh mục cho phép";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

`@Constraint(validatedBy = ...)` chỉ đến validator triển khai logic. `message`, `groups` và `payload` là các phần tử chuẩn của custom constraint. `RUNTIME` cần thiết để provider đọc annotation khi ứng dụng chạy; `@Target` cho phép sử dụng trên các vị trí phù hợp, nhưng không thay thế cơ chế kích hoạt validation.

### 3.4. Validator nhận bean qua constructor — `RegisteredCodeValidator.java`

~~~java
package com.example.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class RegisteredCodeValidator
        implements ConstraintValidator<RegisteredCode, String> {

    private final AllowedCodeCatalog catalog;

    public RegisteredCodeValidator(AllowedCodeCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {
        return value == null || catalog.contains(value);
    }
}
~~~

Đây là điểm then chốt: class `RegisteredCodeValidator` **không khai báo `@Component`** nhưng constructor vẫn có thể nhận `AllowedCodeCatalog` vì `SpringConstraintValidatorFactory` tạo nó bằng Spring bean factory. Việc tiêm một constructor duy nhất không nhất thiết phải gắn `@Autowired` trong cấu hình Spring hiện đại; có thể thêm `@Autowired` rõ ràng để nhấn mạnh ý định nếu codebase yêu cầu.

Method `isValid` trả về `true` với `null` nhằm tách kiểm tra **có thuộc danh mục không** khỏi yêu cầu **phải có giá trị**. Nếu dữ liệu không được `null`, thêm `@NotNull` vào thuộc tính. Không nên gọi `new RegisteredCodeValidator(...)` từ mã ứng dụng để tự chạy validation: hãy gọi Jakarta `Validator` và để provider quản lý metadata, group, lifecycle cùng danh sách lỗi.

### 3.5. Bean cần xác thực — `DocumentRequest.java`

~~~java
package com.example.validation;

import jakarta.validation.constraints.NotNull;

public final class DocumentRequest {

    @NotNull
    @RegisteredCode
    private final String code;

    public DocumentRequest(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
~~~

`@NotNull` và `@RegisteredCode` có nhiệm vụ khác nhau. Một mã `null` chỉ vi phạm `@NotNull` do validator tùy chỉnh cho phép `null`; mã `"BAD-01"` không null nhưng không nằm trong danh mục nên vi phạm `@RegisteredCode`.

### 3.6. Gọi validation trong Spring Boot — `DemoApplication.java`

~~~java
package com.example.validation;

import jakarta.validation.Validator;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication implements CommandLineRunner {

    private final Validator validator;

    public DemoApplication(Validator validator) {
        this.validator = validator;
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Override
    public void run(String... args) {
        System.out.println(
            "BAD-01: " + validator.validate(
                new DocumentRequest("BAD-01")).size());

        System.out.println(
            "SPR-01: " + validator.validate(
                new DocumentRequest("SPR-01")).size());

        System.out.println(
            "null: " + validator.validate(
                new DocumentRequest(null)).size());
    }
}
~~~

Từ thư mục project Gradle hợp lệ chạy:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng `gradlew.bat bootRun`. Trong console sẽ có log khởi động Spring Boot; **ba dòng do chương trình in** là:

~~~text
BAD-01: 1
SPR-01: 0
null: 1
~~~

Giải thích chính xác:

- `BAD-01` không có trong `AllowedCodeCatalog`, nên một violation từ `@RegisteredCode`.
- `SPR-01` nằm trong danh mục và khác null, nên không có violation.
- `null` được `RegisteredCodeValidator` cho qua, nhưng `@NotNull` tạo một violation.
- Nếu thiếu cơ chế tạo validator hỗ trợ Spring, constructor `RegisteredCodeValidator(AllowedCodeCatalog)` không thể được provider mặc định khởi tạo như trong ví dụ; lỗi thường bộc lộ khi chạy validation.

Kết quả chỉ đếm violation; không dựa vào thứ tự `ConstraintViolation` vì API không hứa thứ tự ổn định. Khi dùng một provider cụ thể, thông báo hoặc kiểu exception cấu hình lỗi có thể khác nhau.

## 4. Cấu hình `LocalValidatorFactoryBean` và factory

### 4.1. Trường hợp thông dụng: Spring Boot tự cấu hình

Với Spring Boot 3.x, khi validation provider và validation starter có mặt, ứng dụng thường có bean `LocalValidatorFactoryBean` được tạo sẵn. Khi inject `jakarta.validation.Validator` vào service/controller, bạn nhận integration đã kết nối với Spring bean factory. **Trong trường hợp đó, không cần tự tạo `SpringConstraintValidatorFactory` trong từng validator**.

Luồng khởi tạo ứng dụng là:

1. Spring tạo `ApplicationContext`, các bean như `AllowedCodeCatalog` và bean cung cấp Jakarta `Validator`.
2. `LocalValidatorFactoryBean` bootstrap Jakarta Validation provider và cấu hình factory tạo constraint validator.
3. Khi `Validator.validate(...)` gặp `@RegisteredCode`, provider yêu cầu instance từ factory.
4. Spring tạo `RegisteredCodeValidator` và inject `AllowedCodeCatalog`.
5. Provider gọi `isValid(...)` và đưa ra tập `ConstraintViolation`.

Việc Spring Boot có tạo bean mặc định hay không phụ thuộc điều kiện auto-configuration và bean bạn đã tự định nghĩa. Nếu ứng dụng cung cấp custom `Validator` hoặc custom factory, hãy kiểm tra cấu hình **đang có hiệu lực**, thay vì giả định mặc định của Boot luôn được sử dụng.

### 4.2. Spring Framework thuần hoặc muốn khai báo rõ factory

Trong một ứng dụng Spring không dùng Boot, bạn có thể đăng ký `LocalValidatorFactoryBean`:

~~~java
package com.example.validation;

import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.validation.beanvalidation.SpringConstraintValidatorFactory;

@Configuration
@ComponentScan("com.example.validation")
public class ValidationConfiguration {

    @Bean
    public LocalValidatorFactoryBean validator(
            ApplicationContext applicationContext) {

        LocalValidatorFactoryBean result =
            new LocalValidatorFactoryBean();

        result.setConstraintValidatorFactory(
            new SpringConstraintValidatorFactory(
                applicationContext.getAutowireCapableBeanFactory()));

        return result;
    }
}
~~~

Đoạn này là **cấu hình thay thế/riêng** để minh họa kết nối rõ ràng; không chép nó vào ví dụ Boot ở trên nếu Boot đã tự tạo validator phù hợp. Tên bean và kiểu trả về giúp Spring cung cấp `Validator` cho nơi cần inject. `LocalValidatorFactoryBean` sẽ được khởi tạo qua lifecycle Spring; không cần gọi thủ công `afterPropertiesSet()` hay `close()` của nó.

Trong Spring Framework hiện đại, khi `LocalValidatorFactoryBean` được quản lý bởi Spring và không bị gán custom factory, nó thường tự chọn `SpringConstraintValidatorFactory` dựa trên bean factory của application context. Vì vậy gọi `setConstraintValidatorFactory(...)` như trên là cách **thể hiện tường minh cơ chế**, không phải bước bắt buộc trong mọi ứng dụng.

### 4.3. Bootstrap Jakarta Validation thủ công khi thật sự cần

Nếu cần dùng API bootstrap của Jakarta Validation trực tiếp trong một thành phần đã có `ApplicationContext`, phải kết nối factory rõ ràng để vẫn nhận dependency injection:

~~~java
import jakarta.validation.Validation;
import org.springframework.context.ApplicationContext;
import org.springframework.validation.beanvalidation.SpringConstraintValidatorFactory;

// applicationContext là context Spring đang hoạt động.
try (var factory = Validation.byDefaultProvider()
        .configure()
        .constraintValidatorFactory(
            new SpringConstraintValidatorFactory(
                applicationContext.getAutowireCapableBeanFactory()))
        .buildValidatorFactory()) {

    var validator = factory.getValidator();
    var violations = validator.validate(
        new DocumentRequest("BAD-01"));
    System.out.println(violations.size()); // 1
}
~~~

Đây là đoạn minh họa **trong ngữ cảnh đã có biến `applicationContext`**; không phải một class Java độc lập. `ValidatorFactory` được tạo thủ công nên người tạo phải đóng nó để giải phóng tài nguyên. Không mở/đóng factory mới trong mỗi request: bootstrap provider thường tương đối tốn kém và ứng dụng nên tái sử dụng validator factory do container quản lý.

Lệnh dễ gây nhầm lẫn:

~~~java
var factory = jakarta.validation.Validation
    .buildDefaultValidatorFactory();
~~~

Nếu không cấu hình constraint validator factory tương thích Spring, câu lệnh trên dùng bootstrap mặc định của provider. Nó không tự tra bean Spring theo tên class, và có thể báo lỗi khởi tạo khi custom validator chỉ có constructor cần dependency. Việc annotation class validator bằng `@Component` cũng **không** biến bootstrap mặc định đó thành Spring-aware.

## 5. Chi tiết vòng đời: tạo, tiêm, initialize, dùng lại, release

`ConstraintValidatorFactory` có hai hợp đồng chính:

~~~java
<T extends jakarta.validation.ConstraintValidator<?, ?>> T
    getInstance(Class<T> key);

void releaseInstance(
    jakarta.validation.ConstraintValidator<?, ?> instance);
~~~

Khai báo trên diễn tả **chữ ký logic** trong interface, không phải lớp chạy độc lập. Với `SpringConstraintValidatorFactory`:

- `getInstance(Class<T>)` sử dụng bean factory của Spring để tạo instance `T` và áp dụng tiêm phụ thuộc/các post-processor tương ứng.
- Jakarta Validation provider quản lý cách gọi `ConstraintValidator.initialize(annotation)` và `isValid(value, context)`.
- `releaseInstance(...)` được gọi theo vòng đời của provider; Spring factory chuyển thao tác giải phóng sang bean factory để chạy xử lý hủy tương ứng.

Điểm cần tránh là viết validator có **trạng thái thay đổi theo từng giá trị cần kiểm tra**:

~~~java
// Phản ví dụ: không an toàn khi một instance được dùng cho nhiều validation.
private String lastValidatedCode;

@Override
public boolean isValid(
        String value,
        ConstraintValidatorContext context) {
    lastValidatedCode = value; // trạng thái dùng chung không cần thiết
    return value == null || catalog.contains(value);
}
~~~

Provider có thể lưu/cache instance cho cùng constraint descriptor và sử dụng qua nhiều lần validation, kể cả từ nhiều thread. Giữ validator **không có mutable per-call state** là lựa chọn đúng. Các trường `final` tham chiếu tới dependency hoặc cấu hình bất biến có thể sử dụng; nếu `initialize(...)` đọc tham số annotation và lưu một cấu hình cố định như `Pattern`, hãy đảm bảo cấu hình đó bất biến sau khi khởi tạo.

**Không tự tạo một singleton `ConstraintValidator` trong `@Bean` và mặc nhiên nghĩ provider sẽ dùng chính bean ấy.** `SpringConstraintValidatorFactory` tạo validator thông qua `AutowireCapableBeanFactory` theo yêu cầu của provider; instance nhận được không nhất thiết là một singleton `@Component` cùng class đang tồn tại trong container. Nếu muốn dùng Spring bean bên trong validator, inject **bean cộng tác** như `AllowedCodeCatalog`.

### `@Autowired` field injection và constructor injection

Cả hai có thể hoạt động qua Spring factory:

~~~java
public class AnotherCodeValidator
        implements ConstraintValidator<RegisteredCode, String> {

    @org.springframework.beans.factory.annotation.Autowired
    private AllowedCodeCatalog catalog;

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {
        return value == null || catalog.contains(value);
    }
}
~~~

Đoạn trên chỉ minh họa một **biến thể thay thế** của validator, không sử dụng song song với `RegisteredCodeValidator` trong khai báo `@Constraint`. Constructor injection thường rõ ràng hơn: dependency bắt buộc, có thể khai báo `final`, dễ kiểm thử, và tránh cảm giác field luôn sẵn sàng ngay cả khi object được tự tạo bằng `new`.

## 6. Validation được kích hoạt tại đâu trong Spring?

Tiêm dependency chỉ giải quyết **khởi tạo validator**. Để `isValid(...)` chạy, phải có một điểm gọi Bean Validation.

| Điểm kích hoạt | Ví dụ | Điều kiện quan trọng |
|---|---|---|
| Programmatic Bean Validation | `jakarta.validation.Validator.validate(bean)` | Có Jakarta Validator/provider được cấu hình đúng |
| Spring MVC DTO | `@Valid @RequestBody CreateDocumentForm form` | Có Spring MVC + JSON binding và validator integration |
| Spring MVC form binding | `@Valid @ModelAttribute CreateDocumentForm form` | Dữ liệu được bind thành object và validation được yêu cầu |
| Service method | Bean `@Validated` với constraint trên tham số/return value | Method-validation interception được cấu hình và lời gọi đi qua Spring proxy |
| Container element | `List<@RegisteredCode String>` | Annotation cho phép `TYPE_USE` và provider hỗ trợ value extractor |

Ví dụ controller **chỉ minh họa vị trí kích hoạt**, yêu cầu thêm Spring MVC/web starter và một DTO tương thích JSON binding:

~~~java
@PostMapping("/documents")
public void submit(@Valid @RequestBody CreateDocumentForm form) {
    documentService.submit(form.getCode());
}
~~~

Ở đây `@Valid` yêu cầu kiểm tra DTO sau data binding; validator tùy chỉnh được tạo qua factory đã cấu hình. `@Valid` không phải cách tiêm service; Spring factory lo nhiệm vụ đó.

Đối với business service:

~~~java
@Service
@Validated
public class DocumentService {

    public void submit(@RegisteredCode String code) {
        // Xử lý nghiệp vụ sau khi đầu vào hợp lệ.
    }
}
~~~

Đây cũng là đoạn minh họa cơ chế, không thuộc project demo độc lập ở trên. Với method validation kiểu AOP, Spring phải có cơ chế chặn method validation hoạt động (chẳng hạn `MethodValidationPostProcessor` ở cấu hình phù hợp) và lời gọi phải đi qua Spring proxy. Lời gọi nội bộ kiểu `this.submit(...)` có thể bỏ qua interception. Spring MVC các phiên bản mới còn có cơ chế method validation trực tiếp cho controller: phân biệt cơ chế này với AOP method validation của service khi tìm nguyên nhân thiếu lỗi.

**Data binding thành công không đồng nghĩa validation thành công**, và ngược lại lỗi convert kiểu từ HTTP có thể xảy ra trước khi bất cứ `ConstraintValidator` nào được gọi. Đối với controller cần kiểm tra cả việc bind và cấu hình xử lý lỗi, không chỉ kiểm tra constructor injection.

## 7. Kiểm thử để chứng minh dependency injection hoạt động

Một unit test tự `new RegisteredCodeValidator(new AllowedCodeCatalog())` sẽ kiểm tra logic nhưng **không chứng minh SpringConstraintValidatorFactory được sử dụng**. Muốn kiểm tra kết nối thực, lấy `jakarta.validation.Validator` từ Spring context rồi chạy validate trên bean có annotation.

Với Spring Boot và `spring-boot-starter-test`, có thể dùng integration test:

~~~java
package com.example.validation;

import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class RegisteredCodeIntegrationTest {

    @Autowired
    private Validator validator;

    @Test
    void usesSpringManagedCodeCatalog() {
        assertEquals(0, validator.validate(
            new DocumentRequest("SPR-02")).size());
        assertEquals(1, validator.validate(
            new DocumentRequest("UNKNOWN")).size());
        assertEquals(1, validator.validate(
            new DocumentRequest(null)).size());
    }
}
~~~

Test này nằm tại `src/test/java/com/example/validation/RegisteredCodeIntegrationTest.java`. Thêm dependency test vào project Boot:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Chạy `./gradlew test` (hoặc `gradlew.bat test` trên Windows). Kết quả kỳ vọng: test **PASS** nếu Spring context, provider và factory kết nối thành công. Vì validator có **duy nhất constructor cần `AllowedCodeCatalog`**, provider không có Spring-aware factory thường không thể tạo được instance để hoàn thành bài test.

Nếu chỉ cần unit test logic, có thể gọi `isValid` trực tiếp với một fake/stub `AllowedCodeCatalog`, nhưng test kiểu đó không chứng thực metadata `@Constraint`, quá trình `initialize`, group selection, service injection hay factory lifecycle.

## 8. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| `@Autowired` trong validator bằng `null` hoặc constructor injection thất bại | Provider dùng factory không tương thích Spring, hoặc validator được tạo bằng `new` ngoài context | Kiểm tra bean `Validator`/`LocalValidatorFactoryBean` đang sử dụng, cách bootstrap provider và `SpringConstraintValidatorFactory` |
| Thông báo kiểu “unable to instantiate ConstraintValidator” | Provider không tạo được validator, thường do constructor cần tham số mà factory mặc định không hỗ trợ | Đảm bảo factory Spring được cấu hình và bean dependency tồn tại |
| `NoSuchBeanDefinitionException` / `UnsatisfiedDependencyException` | `AllowedCodeCatalog` chưa thành bean, component scan không bao phủ package, hoặc có nhiều bean không phân giải | Kiểm tra `@Service`, package scan, `@Qualifier`/`@Primary` khi cần |
| Validator hoạt động khi gọi trực tiếp nhưng không chạy trên DTO | Chưa gọi `Validator.validate` hoặc thiếu `@Valid` ở điểm kích hoạt | Xem luồng controller/service và validator integration |
| Tự tạo `Validation.buildDefaultValidatorFactory()` rồi mất injection | Dùng factory mặc định của Jakarta Validation provider | Inject validator Spring quản lý hoặc cấu hình explicit `ConstraintValidatorFactory` |
| Dùng `javax.validation.*` trong ứng dụng Boot 3 | Không khớp Jakarta namespace với Spring 6/Boot 3 | Thống nhất `jakarta.validation.*` cho API, annotation và provider |
| Validator được gọi nhiều lần hoặc có trạng thái sai | Provider cache/reuse instance; code lưu mutable state của từng request | Giữ `isValid` stateless, xử lý mọi dữ liệu trong tham số method |
| Gọi service method nội bộ không thấy method constraint chạy | Self-invocation không đi qua Spring AOP proxy trong chế độ AOP method validation | Gọi qua bean/proxy hợp lệ và xác nhận method validation configured |
| Constraint trên field có kiểu không khớp | Validator chỉ triển khai `ConstraintValidator<RegisteredCode, String>` nhưng dùng trên kiểu khác | Thêm đúng validator cho kiểu khác hoặc giới hạn nơi áp dụng |
| Muốn xác thực `null` nhưng không có lỗi | Validator trả về `true` với `null` | Kết hợp `@NotNull` hoặc `@NotBlank` tùy ngữ nghĩa |
| Mỗi request tự bootstrap validator factory | Dễ tốn tài nguyên và làm khó lifecycle/dependency management | Tái sử dụng `LocalValidatorFactoryBean`/`Validator` do Spring cung cấp |

Khi debug, đi theo thứ tự **annotation hiện diện ở runtime → có provider → có điểm kích hoạt validation → provider dùng factory nào → Spring có bean dependency hay không → `isValid` có đúng logic không**. Thứ tự này thường tìm nguyên nhân nhanh hơn việc chỉ thêm `@Component` vào lớp validator.

## 9. Lưu ý thiết kế cho môi trường production

**Giữ validation dự đoán được.** `isValid` nên trả về kết quả dựa trên dữ liệu và chính sách hiện hành, tránh ghi database, gửi message, hoặc làm thay đổi trạng thái nghiệp vụ. Nếu dependency gọi network/database, quan tâm latency, retry, timeout, lỗi tạm thời và tải khi validate một collection lớn. Một ràng buộc dùng nhiều lần có thể gây nhiều lần gọi vào dependency.

**Không lưu trạng thái request vào field của validator.** Provider quyết định việc cache instance và lifecycle, trong khi cùng một validator instance có thể xử lý nhiều giá trị. Dependency singleton có thể được inject vào validator instance mà không có nghĩa validator tự mang scope request.

**Tách điều kiện bắt buộc và điều kiện nghiệp vụ.** `@NotNull`, `@NotBlank` hay các constraint chuẩn làm nhiệm vụ đơn giản; `@RegisteredCode` kiểm tra danh mục. Nếu cần policy phụ thuộc người dùng hiện tại, cân nhắc chỗ đặt validation: constraint cần quy tắc rõ ràng và không nên phụ thuộc ngầm vào trạng thái request khó kiểm thử.

**Không dựa vào thứ tự constraint hay validator invocation.** Một bean có thể có nhiều constraint. Theo cấu hình/group và provider, thứ tự vi phạm không phải hợp đồng ổn định. Không đặt logic mà tính đúng đắn phụ thuộc “constraint A chạy trước B”.

**Kiểm soát cấu hình tùy chỉnh.** Nếu thay `LocalValidatorFactoryBean` bằng bean hoặc factory mới, phải xác nhận phần ứng dụng thực sự sử dụng instance đó. Nhiều `Validator` trong context có thể dẫn đến việc controller, service và code tự gọi nhận những cấu hình khác nhau.

## 10. Tự kiểm tra kiến thức

1. Vì sao một `ConstraintValidator` có constructor dependency có thể chạy trong Spring Boot nhưng thất bại khi được Jakarta provider mặc định tự tạo? — Vì `SpringConstraintValidatorFactory` dùng Spring để khởi tạo/autowire instance, còn factory mặc định không tự biết dependency trong `ApplicationContext`.
2. Có cần gắn `@Component` lên mọi lớp `ConstraintValidator` không? — Không. Spring factory có thể tạo và autowire validator class trực tiếp; bean cộng tác như `AllowedCodeCatalog` cần được Spring quản lý.
3. `SpringConstraintValidatorFactory` có tự gọi `isValid` không? — Không. Jakarta Validation provider quản lý việc gọi `initialize`/`isValid` sau khi lấy instance từ factory.
4. Vì sao bài demo có lỗi với `null` dù `RegisteredCodeValidator.isValid(null, ...)` trả về `true`? — Vì `@NotNull` là constraint riêng.
5. Vì sao không nên lưu `lastValidatedValue` trên một field của `ConstraintValidator`? — Instance có thể được provider cache/tái sử dụng qua nhiều validation và thread.
6. Khi cần tự cấu hình Spring Framework không dùng Boot, dùng thành phần nào để kết nối? — Đăng ký `LocalValidatorFactoryBean` trong Spring context và, nếu cần cấu hình tường minh, truyền `SpringConstraintValidatorFactory(applicationContext.getAutowireCapableBeanFactory())`.
7. Nếu controller bind được DTO nhưng không báo lỗi constraint, kiểm tra điều gì? — Kiểm tra điểm kích hoạt `@Valid`/`@Validated` hoặc `Validator.validate`, provider, factory và xử lý lỗi; dependency injection chỉ là một khâu.

**Ghi nhớ:** `SpringConstraintValidatorFactory` là cầu nối **Jakarta Validation provider → Spring BeanFactory** để khởi tạo custom `ConstraintValidator` có phụ thuộc Spring. `LocalValidatorFactoryBean` thường là điểm cấu hình tích hợp; các lệnh validate hoặc annotation kích hoạt validation mới khiến logic được thực thi.

## Tài liệu tham khảo

- [Spring Framework Reference — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring API — SpringConstraintValidatorFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/SpringConstraintValidatorFactory.html)
- [Spring API — LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring API — AutowireCapableBeanFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/AutowireCapableBeanFactory.html)
- [Jakarta Validation API — ConstraintValidatorFactory](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraintvalidatorfactory)
- [Jakarta Validation API — ConstraintValidator](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraintvalidator)
