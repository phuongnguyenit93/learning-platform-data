# Annotation chỉ có hiệu lực khi cơ chế kiểm tra được gọi (Bean Validation trong Spring)

## 1. Ý nghĩa của đề bài

Khi viết một DTO, entity hoặc Java bean như sau:

```java
public class RegisterRequest {
    @NotBlank
    private String username;

    @Email
    private String email;
}
```

các annotation `@NotBlank` và `@Email` **mô tả quy tắc xác thực dữ liệu**. Chúng không tự chạy khi constructor được gọi, không tự quan sát mọi lần setter thay đổi giá trị và không mặc nhiên chặn việc tạo một đối tượng không hợp lệ.

Để ràng buộc được **thực thi**, phải có **cơ chế gọi kiểm tra**: một lệnh trực tiếp như `jakarta.validation.Validator.validate(object)`, một lần `DataBinder.validate()` đã cấu hình validator, một điểm vào Spring MVC có `@Valid`/`@Validated` phù hợp, hoặc interceptor method validation của Spring khi thực sự đi qua Spring proxy.

Quy tắc cần nhớ:

> **Annotation là metadata khai báo constraint. Validation engine hoặc cơ chế tích hợp phải được gọi thì constraint mới được đánh giá.**

Trong Bean Validation, việc một trường có annotation không đồng nghĩa đối tượng luôn ở trạng thái hợp lệ. Ví dụ `new RegisterRequest()`, gán field bằng setter hay nhận dữ liệu JSON đều là thao tác tạo/gán dữ liệu; **validation là một bước riêng** khi có entry point kích hoạt.

## 2. Bốn thành phần phải phân biệt

| Thành phần | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| **Constraint annotation** | Khai báo điều kiện dữ liệu | `@NotNull`, `@NotBlank`, `@Size`, `@Email`, `@Min` |
| **Cascade marker** | Yêu cầu kiểm tra các đối tượng lồng nhau *khi một lượt validation diễn ra* | `jakarta.validation.Valid` |
| **Validation engine** | Đọc metadata, chạy `ConstraintValidator` và trả violation | Provider Hibernate Validator; `jakarta.validation.Validator` |
| **Trigger/integration** | Quyết định **khi nào** yêu cầu engine chạy | `validator.validate(...)`, Spring MVC `@Valid`, `DataBinder.validate()`, method validation proxy |

`@Validated` là annotation của Spring, hỗ trợ chọn **validation groups** và, khi đặt ở cấp type cùng cấu hình phù hợp, đánh dấu Spring bean đủ điều kiện cho **method validation** bằng interceptor/proxy. Nó không biến một đối tượng Java được tạo bằng `new` thành một đối tượng tự kiểm tra.

### Luồng xử lý bản chất

```text
new DTO / setter / JSON deserialize / bind form
                  |
            Có dữ liệu trong bean
                  |
       Có validation trigger không?
           /                 \
         KHÔNG                CÓ
           |                   |
  Không chạy constraint    Spring/API gọi Validator
           |                   |
  Đối tượng có thể sai      Provider kiểm tra metadata
                               |
                    ConstraintViolation / Errors
                               |
                  Controller/service xử lý lỗi
```

**Một validator có mặt trong classpath là điều kiện về khả năng, chưa phải điều kiện thực thi.** Cần có provider tương thích (ví dụ Hibernate Validator) *và* có một lượt kiểm tra thực sự.

## 3. Những tình huống nào thực sự chạy validation?

| Tình huống | Có tự thực thi Bean Validation? | Vì sao |
| --- | --- | --- |
| `new User("", ...)`, setter hoặc builder gán field | **Không** | Chỉ tạo/gán đối tượng |
| Field có `@NotBlank`, không có code kiểm tra | **Không** | Annotation chỉ là metadata |
| `validator.validate(user)` với provider hoạt động | **Có** | Gọi API kiểm tra trực tiếp |
| `validator.validateProperty(user, "name")` | **Có**, cho property được chọn | Lệnh chủ động của caller |
| `DataBinder.bind(values)` | **Không tự bảo đảm có Bean Validation** | Binding và validation là hai bước |
| `binder.setValidator(v); binder.validate()` | **Có** | Đã thiết lập và gọi validator |
| Spring MVC `@Valid @RequestBody Dto dto` | **Có** nếu MVC validation được cấu hình và tham số phù hợp | Argument resolver kích hoạt kiểm tra |
| Spring MVC `@Valid @ModelAttribute Form form` | **Có** trong luồng xử lý hỗ trợ | Binder/argument resolver kiểm tra |
| Spring MVC chỉ có `@RequestBody Dto dto` | **Không do `@Valid`**, vì không được yêu cầu | Deserialize không đồng nghĩa validate |
| Spring MVC `@RequestParam @Min(1) int page` | **Có** trong MVC hỗ trợ method validation | Constraint đặt trực tiếp trên tham số |
| Spring-managed service `@Validated` + tham số `@NotBlank` + gọi qua proxy | **Có** khi method validation đã được kích hoạt | Interceptor gọi provider |
| Tự gọi `new Service().method(...)` dù class có `@Validated` | **Không tự động** | Không đi qua Spring proxy |
| Method nội bộ gọi `this.otherMethod(...)` trên service proxy thông thường | **Thường không qua interceptor** | Self-invocation bỏ qua proxy |
| `@Valid` trên field nested, nhưng không validate object cha | **Không** | Cascade chỉ chạy trong một lượt validation |
| JPA entity có `@NotNull` trước khi gọi `persist` | **Không chỉ nhờ annotation** | ORM callbacks là tích hợp tùy cấu hình, không phải kiểm tra tức thời |

Lưu ý: trong một số tích hợp (Spring Boot configuration properties, JPA lifecycle, Spring MVC, method validation), framework **có thể** tự gọi validator tại điểm vào được cấu hình. Vì vậy không có nghĩa phải viết `validate()` thủ công ở khắp nơi; phải hiểu **entry point cụ thể** đang chạy.

## 4. Ví dụ Java 17+ hoàn chỉnh: khác biệt giữa annotation và lời gọi validation

Ví dụ chạy bằng Spring Boot 3.5, Java 17 và Maven. Nó minh họa lần lượt:

1. Tạo đối tượng sai mà constructor vẫn hoàn tất.
2. Gọi Jakarta `Validator.validate(...)` thì nhận **hai violation**.
3. Bỏ `@Valid` ở thuộc tính lồng nhau thì constraint trong object con **không được duyệt**.
4. Dùng Spring `DataBinder.validate()` thì lỗi nằm trong `BindingResult`.
5. Gọi service thông qua Spring bean `@Validated` thì tham số method được kiểm tra.

Cấu trúc:

```text
annotation-validation-demo/
├── pom.xml
└── src/main/java/demo/AnnotationValidationDemo.java
```

### `pom.xml`

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

    <groupId>demo</groupId>
    <artifactId>annotation-validation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-validation` cung cấp tích hợp Jakarta Validation/provider; `spring-boot-starter-aop` bảo đảm cơ sở proxy/AOP cho ví dụ service. Spring Boot hỗ trợ bật method validation của Spring-managed beans khi provider tương thích hiện diện. Không cần tự tạo `ValidatorFactory` cho từng request.

### `src/main/java/demo/AnnotationValidationDemo.java`

```java
package demo;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.validation.DataBinder;
import org.springframework.validation.annotation.Validated;

@SpringBootApplication
public class AnnotationValidationDemo {

    public static void main(String[] args) {
        SpringApplication.run(AnnotationValidationDemo.class, args);
    }

    @Bean
    BookingService bookingService() {
        return new BookingService();
    }

    @Bean
    ApplicationRunner demonstrate(
            jakarta.validation.Validator jakartaValidator,
            org.springframework.validation.Validator springValidator,
            BookingService service) {

        return args -> {
            Registration invalid =
                    new Registration("", new Contact(""));

            // new chỉ tạo object. Chưa có lời gọi validation.
            System.out.println("Constructed: no automatic validation");

            long errors = jakartaValidator.validate(invalid).size();
            System.out.println("Jakarta violations: " + errors);

            // Thiếu @Valid ở field contact => không kiểm tra bên trong.
            WithoutCascade noCascade =
                    new WithoutCascade(new Contact(""));
            System.out.println("Without cascade: "
                    + jakartaValidator.validate(noCascade).size());

            DataBinder binder = new DataBinder(invalid);
            binder.setValidator(springValidator);
            binder.validate(); // Có lệnh gọi validation rõ ràng.
            System.out.println("Spring binder errors: "
                    + binder.getBindingResult().getErrorCount());

            System.out.println("Service valid: " + service.book("OK"));
            try {
                // Gọi qua Spring proxy, không gọi new BookingService().
                service.book("");
            } catch (ConstraintViolationException ex) {
                System.out.println("Service violations: "
                        + ex.getConstraintViolations().size());
            }
        };
    }

    public static class Registration {
        @NotBlank
        private final String username;

        @Valid
        private final Contact contact;

        Registration(String username, Contact contact) {
            this.username = username;
            this.contact = contact;
        }

        public String getUsername() {
            return username;
        }

        public Contact getContact() {
            return contact;
        }
    }

    public static class Contact {
        @NotBlank
        private final String email;

        Contact(String email) {
            this.email = email;
        }

        public String getEmail() {
            return email;
        }
    }

    public static class WithoutCascade {
        // Cố ý không khai báo @Valid ở đây.
        private final Contact contact;

        WithoutCascade(Contact contact) {
            this.contact = contact;
        }

        public Contact getContact() {
            return contact;
        }
    }

    @Validated
    public static class BookingService {
        public String book(@NotBlank String code) {
            return "booked";
        }
    }
}
```

Chạy trong thư mục dự án:

```bash
mvn spring-boot:run
```

Bên cạnh log khởi động của Spring Boot, các dòng do chương trình tự in ra lần lượt là:

```text
Constructed: no automatic validation
Jakarta violations: 2
Without cascade: 0
Spring binder errors: 2
Service valid: booked
Service violations: 1
```

**Vì sao kết quả như trên?**

- `new Registration("", new Contact(""))` không ném exception chỉ vì có annotation. Lúc này có **hai giá trị rỗng**, nhưng chưa ai yêu cầu kiểm tra.
- `jakartaValidator.validate(invalid)` gọi provider; `@NotBlank` trên `username` không đạt, `@Valid` đưa provider tới `Contact.email` và thấy `@NotBlank` thứ hai → **2** violation. Số lượng xác định trong mô hình này vì mỗi field có đúng một constraint và giá trị đều sai.
- `WithoutCascade` giữ một `Contact` rỗng nhưng không đánh dấu field bằng `@Valid`, nên lượt validate object cha không đi sâu vào object con → **0** violation.
- `DataBinder` chỉ chạy khi ta gọi `binder.validate()`. Spring `Validator` chuyển hai vi phạm thành lỗi trên `BindingResult` → **2**.
- `BookingService` là Spring bean có `@Validated`; khi gọi `service.book("")` qua proxy method-validation được cấu hình, `@NotBlank` trên tham số bị vi phạm. Mặc định Spring interceptor ném `ConstraintViolationException` → **1**.
- Thay `service` bằng `new BookingService()` sẽ bỏ qua interceptor. Bản thân class và tham số vẫn mang annotation, nhưng không có proxy gọi validation.

**Phạm vi ví dụ:** yêu cầu Spring Boot 3.x, Java 17, Maven và dependencies đã nêu; kết quả stdout liệt kê chỉ bao gồm các dòng `System.out.println` của ứng dụng, không bao gồm log framework. Với Spring Framework thuần (không dùng Boot), phải cấu hình `LocalValidatorFactoryBean` và `MethodValidationPostProcessor` theo cách của project.

## 5. Lời gọi thủ công qua Jakarta `Validator`

Jakarta Validation có giao diện `jakarta.validation.Validator`; các thao tác phổ biến:

```java
Set<ConstraintViolation<Registration>> violations =
        validator.validate(registration);
```

Đây là **đoạn minh họa**, cần biến `validator` lấy từ Spring context, class `Registration` và import Jakarta tương ứng. `validate` trả về một `Set` các vi phạm; **không tự ném exception khi có constraint sai**. Caller cần kiểm tra `isEmpty()` rồi quyết định trả lỗi, ném exception hoặc từ chối xử lý.

Các API hữu ích:

- `validate(bean, groups...)`: kiểm tra ràng buộc của bean, theo nhóm chỉ định; nếu không chỉ định thì dùng `Default`.
- `validateProperty(bean, "name", groups...)`: kiểm tra constraint trên một property cụ thể; **không cascade** xuống đối tượng của property đó.
- `validateValue(SomeBean.class, "name", proposedValue, groups...)`: thử kiểm tra giá trị dự kiến mà chưa cần có instance bean; không thực hiện cascade.
- `getConstraintsForClass(...)`: đọc metadata constraint mà không cần thực thi validation.
- `forExecutables()`: API để kiểm tra parameter/return value của method/constructor theo chủ đích.

Ví dụ phát hiện lỗi:

```java
Set<ConstraintViolation<Registration>> violations =
        validator.validate(registration);

if (!violations.isEmpty()) {
    String paths = violations.stream()
            .map(v -> v.getPropertyPath().toString())
            .sorted()
            .collect(java.util.stream.Collectors.joining(", "));
    throw new IllegalArgumentException(
            "Invalid registration fields: " + paths);
}
```

Đoạn trên **không phải chương trình độc lập**: cần import `java.util.Set` và `jakarta.validation.ConstraintViolation`; giả định `validator` và `registration` đã có. Với registration sai ở ví dụ trên, message sẽ liệt kê các path theo thứ tự đã sort như `contact.email, username`.

**Lưu ý về test:** thứ tự duyệt phần tử trong `Set<ConstraintViolation<?>>` không được API bảo đảm. Nếu kiểm tra output, hãy sort theo property path hoặc assert theo tập path, không dựa vào "vi phạm đầu tiên".

## 6. Spring `DataBinder`: bind dữ liệu không đồng nghĩa validate

`DataBinder`/`WebDataBinder` có trách nhiệm map dữ liệu đầu vào vào thuộc tính Java, theo cấu hình conversion và binding. Spring cho phép đăng ký Spring `Validator`, trong đó `LocalValidatorFactoryBean` có thể làm adapter tới Jakarta Validation.

```java
DataBinder binder = new DataBinder(target);
binder.setValidator(springValidator);

binder.bind(new MutablePropertyValues(
        java.util.Map.of("username", "")));

// Đây mới là điểm kích hoạt validation đã đăng ký:
binder.validate();

BindingResult result = binder.getBindingResult();
System.out.println(result.hasErrors());
```

Đây là **đoạn trích minh họa**, giả định `target` có property `username` có thể ghi được, `springValidator` hỗ trợ class của target và đã cấu hình. Cần import `org.springframework.validation.DataBinder`, `BindingResult` và `org.springframework.beans.MutablePropertyValues`.

- `binder.bind(...)` có thể tạo *binding/type-conversion errors* khi giá trị không chuyển được sang kiểu đích.
- `binder.validate()` kích hoạt các validator được đăng ký, bổ sung *validation errors*.
- `BindingResult` gom cả lỗi binding và validation; không suy rằng mỗi `FieldError` nhất định do Jakarta `@NotBlank` sinh ra.
- Gọi `binder.setValidator(...)` mà không gọi `binder.validate()` trong mã dùng trực tiếp **chưa** chạy kiểm tra. Spring MVC có thể thực hiện bước này thay cho ứng dụng tại entry point được hỗ trợ.

Nếu muốn kiểm tra thêm business rules bằng Spring `Validator` tự viết, có thể kết hợp với validator toàn cục qua `addValidators(...)` trong bối cảnh phù hợp. Đừng vô tình thay mất validator Bean Validation và làm mất khả năng áp dụng constraint Jakarta.

## 7. Spring MVC: lúc nào `@Valid` và `@Validated` kích hoạt?

### `@RequestBody`: JSON deserialize trước, validation sau

Ví dụ một REST controller trong Spring MVC (đây là **đoạn minh họa**, yêu cầu import Spring MVC/Jakarta và class `RegistrationRequest` phù hợp):

```java
@PostMapping("/registrations")
public ResponseEntity<?> register(
        @Valid @RequestBody RegistrationRequest request,
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

Khi Spring MVC xử lý request:

1. `HttpMessageConverter` (thường dùng Jackson) đọc JSON và tạo DTO.
2. Argument resolver nhận thấy `@Valid` hoặc `@Validated` trên tham số hỗ trợ.
3. Validator được MVC cấu hình kiểm tra các constraint trên DTO.
4. Vi phạm được đưa vào `BindingResult`, hoặc dẫn tới ngoại lệ khi controller không nhận kết quả lỗi ở vị trí cho phép.
5. Controller hoặc global exception handler quyết định phản hồi HTTP.

**`BindingResult`/`Errors` phải đặt ngay sau tham số cần kiểm tra** để Spring có thể truyền lỗi cho method ở các tình huống hỗ trợ. Nếu không có `BindingResult` tương ứng, trong MVC 6.1+ các tình huống chỉ validate object argument thường ném `MethodArgumentNotValidException`; khi constraint đặt trực tiếp trên tham số method thì có thể sử dụng cơ chế *method validation*, ném `HandlerMethodValidationException`. Các loại exception và phạm vi áp dụng phụ thuộc chữ ký method, loại tham số và cấu hình.

Nếu bỏ `@Valid` khỏi `RegistrationRequest` ở tham số `@RequestBody` và không có trigger khác, dữ liệu rỗng vẫn có thể được deserialize thành DTO mà các Bean Validation constraints không được kiểm tra.

**Đừng nhầm lỗi JSON với lỗi Bean Validation:** JSON sai cú pháp, field không thể deserialize hoặc enum không hợp lệ có thể thất bại **trước khi** validation có cơ hội chạy. Việc catch mỗi `MethodArgumentNotValidException` không bao phủ mọi lỗi request body.

### `@ModelAttribute`: form/query object

```java
@PostMapping("/profiles")
public String save(
        @Valid @ModelAttribute("profile") ProfileForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "profile-form";
    }
    return "redirect:/profiles";
}
```

Đây là **đoạn method minh họa**, cần class form/controller và import. Spring bind field vào `ProfileForm` rồi chạy validation vì có `@Valid`; lỗi được đưa vào `BindingResult` ngay sau tham số. Một form có annotation trên field nhưng controller không đánh dấu `@Valid`/`@Validated` **không được bảo đảm** chạy Bean Validation chỉ nhờ quá trình binding.

### Constraint đặt trực tiếp trên tham số

```java
@GetMapping("/products")
public List<Product> list(@RequestParam @Min(1) int page) {
    return productService.findPage(page);
}
```

Đây là **đoạn minh họa** với `Product` và `productService` của ứng dụng. Trong Spring MVC 6.1+ hỗ trợ built-in method validation, `@Min(1)` trực tiếp trên tham số là constraint và có thể làm MVC thực hiện method validation. `@Valid` đơn thuần **không phải constraint annotation** nên tự nó không kích hoạt cơ chế method validation kiểu này; nó là marker yêu cầu cascade các đối tượng khi một lượt validation diễn ra.

Spring Framework lưu ý: với controller mới sử dụng built-in MVC method validation, **không đặt `@Validated` ở cấp controller class nếu không cần AOP method validation đời cũ**. Class-level `@Validated` có thể khiến method validation diễn ra qua proxy, dẫn đến cách xử lý khác với cơ chế built-in.

## 8. Spring service: `@Validated` cần proxy và cơ chế method validation

Bean Validation của **đối số method service** không được kích hoạt chỉ bằng cách viết:

```java
@Service
public class OrderService {
    public void create(@NotBlank String orderCode) {
        // logic
    }
}
```

Đây là **class minh họa**; nếu không có method-validation interceptor hoặc lời gọi kiểm tra thủ công, `@NotBlank` trên tham số `orderCode` vẫn chỉ là metadata.

Cấu hình với Spring Framework thuần:

```java
@Configuration
public class MethodValidationConfig {

    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        return new MethodValidationPostProcessor();
    }
}
```

Trong Spring Boot, method validation thường được tự động kích hoạt khi Bean Validation provider có mặt. Còn bean đích phải được đánh dấu `@Validated` ở cấp type để eligible cho Spring-driven method validation:

```java
@Service
@Validated
public class OrderService {

    public void create(@NotBlank String orderCode) {
        // Khi đi qua Spring proxy có interceptor,
        // orderCode rỗng sẽ vi phạm.
    }
}
```

Hai đoạn trên là **lớp minh họa cho project Spring**, cần import `@Configuration`, `@Bean`, `@Service`, `@Validated`, `@NotBlank` và `MethodValidationPostProcessor`.

Các giới hạn thực tế:

- Gọi qua Spring bean/proxy, ví dụ service được inject vào controller, thì interceptor có cơ hội kiểm tra.
- Tự `new OrderService()`, dùng object ngoài Spring hoặc gọi phương thức qua `this` trong cùng bean thường **bỏ qua proxy**.
- Với AOP proxy thông thường, các method không thể được proxy/advised (như nhiều trường hợp method `private`/`final`) không nên là nơi dựa vào validation interceptor.
- Nếu ứng dụng tự viết `@Bean MethodValidationPostProcessor`, kiểm tra cấu hình đang có để không tạo xử lý trùng hoặc proxy ngoài dự kiến.
- Mặc định, vi phạm method validation của Spring interceptor thường thành `ConstraintViolationException`. Có thể cấu hình phương án thích ứng thành `MethodValidationException` ở những Spring version/API hỗ trợ.
- Kích hoạt method validation cho **lớp service** khác với cơ chế tự động validate command object của **MVC controller**.

### Self-invocation: lỗi khó phát hiện

```java
@Validated
@Service
public class AccountService {

    public void register() {
        updateEmail(""); // Lời gọi nội bộ có thể bỏ qua AOP proxy.
    }

    public void updateEmail(@NotBlank String email) {
        // ...
    }
}
```

Đoạn này **không phải chương trình độc lập**. Một lời gọi `accountService.updateEmail("")` từ bean khác qua proxy có thể bị chặn; một lời gọi `updateEmail("")` trực tiếp trong cùng instance thường bỏ qua advice. Hãy tách trách nhiệm sang bean khác, gọi qua public Spring-managed boundary thực sự hoặc đặt validation explicit tại nơi cần bảo đảm quy tắc. Không dựa vào annotation như biện pháp duy nhất bảo vệ bất biến trong các đường gọi không đi qua proxy.

## 9. `@Valid`, `@Validated` và groups: tương tự tên, khác tác dụng

| Cú pháp | Vai trò | Tự sinh lượt validation? |
| --- | --- | --- |
| `@NotNull`, `@NotBlank`, `@Size`, `@Email` | Khai báo constraint | Không |
| `@Valid` trên field nested | Cascade khi object cha được validate | Không |
| `@Valid` trên parameter Spring MVC được hỗ trợ | Yêu cầu MVC validate DTO | Có, vì MVC integration gọi engine |
| `@Validated` trên MVC DTO parameter | Yêu cầu validate, chọn nhóm khi cần | Có trong luồng MVC hỗ trợ |
| `@Validated` ở cấp Spring service class | Đánh dấu bean cho method validation proxy | Chỉ khi interceptor/proxy được cấu hình và thực sự đi qua |
| `@Validated(SomeGroup.class)` | Chọn validation group | Chỉ tại điểm kích hoạt tương ứng |

Ví dụ groups:

```java
public interface OnCreate {}

public class UserInput {
    @NotBlank(groups = OnCreate.class)
    private String password;

    @NotBlank
    private String displayName;
}
```

Khi `validator.validate(user)` không chỉ định group, engine dùng `Default` và kiểm tra `displayName`; `password` chỉ thuộc `OnCreate` nên không chạy. Khi `validator.validate(user, OnCreate.class)`, constraint của nhóm `OnCreate` chạy; `Default` không tự được thêm nếu chưa có quan hệ nhóm phù hợp. Spring MVC có thể chọn `OnCreate` bằng `@Validated(OnCreate.class)` trên tham số command object.

**Một annotation có thể không cho thấy lỗi** vì nhóm của nó chưa được chọn, chứ không nhất thiết do provider bị hỏng. Hãy kiểm tra cả **trigger**, **group selection** và **các đường cascade**.

## 10. Validation lồng nhau: tại sao `@Valid` không được bỏ qua?

```java
public class Checkout {
    @NotNull
    @Valid
    private Address address;
}

public class Address {
    @NotBlank
    private String city;
}
```

Đây là **mô hình minh họa**. Khi validate `Checkout`:

- Nếu `address == null`, `@NotNull` báo lỗi; `@Valid` không tự biến null thành lỗi.
- Nếu `address != null` nhưng `city == ""`, `@Valid` yêu cầu provider duyệt vào `Address` và phát hiện `@NotBlank` trên `city`.
- Nếu thiếu `@Valid` ở `Checkout.address`, gọi `validate(checkout)` không tự kiểm tra constraint của `Address.city` chỉ vì có quan hệ đối tượng.
- Nếu chỉ khởi tạo `Checkout` mà không validate, **cả `@NotNull` lẫn cascade `@Valid` đều chưa được đánh giá**.

Cascaded validation cũng áp dụng cho phần tử container theo khả năng Jakarta Validation (ví dụ `List<@Valid Address>` và container element constraints), với các quy tắc về value extractors và group propagation của provider. Không suy từ việc ghi `List<Address>` rằng provider sẽ tự kiểm tra từng phần tử khi thiếu cascade metadata.

## 11. Custom `ConstraintValidator`: `isValid(...)` chỉ chạy khi provider đến được constraint

Ví dụ annotation tùy biến:

```java
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = PrefixValidator.class)
public @interface HasPrefix {
    String message() default "prefix invalid";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

Và implementation:

```java
public final class PrefixValidator
        implements ConstraintValidator<HasPrefix, String> {

    @Override
    public boolean isValid(
            String value, ConstraintValidatorContext context) {
        return value == null || value.startsWith("VN-");
    }
}
```

Hai đoạn trên là **mã minh họa**, cần tách thành các file đúng tên và import `java.lang.annotation.*` cùng `jakarta.validation.*`; application phải có provider. Dù annotation `@HasPrefix` đã được gắn lên field, `isValid(...)` chỉ được provider gọi nếu field đó tham gia vào **lượt validation thực sự**, theo group và đường cascade thích hợp.

- Trong Spring, `LocalValidatorFactoryBean` thường bootstrap provider và dùng `SpringConstraintValidatorFactory` để giúp inject dependency vào constraint validator.
- Nếu class/constraint không nằm trong lượt kiểm tra, `ConstraintValidator` không chạy dù nó có thể là Spring-managed hoặc được provider khởi tạo.
- Việc custom validator tự gọi DB/service là logic cần kiểm soát; không đặt side effect quan trọng vào `isValid(...)`, vì framework có thể validate nhiều lần hoặc theo thứ tự không xác định.
- Một số provider có thể tái sử dụng `ConstraintValidator`; tránh giữ trạng thái biến đổi theo request trong instance có thể được chia sẻ.

## 12. Một số tích hợp khác có thể gọi validation giúp bạn

### `@ConfigurationProperties` trong Spring Boot

Spring Boot có thể validate bean cấu hình được bind từ properties/YAML khi bean được đặt `@Validated` và provider phù hợp trên classpath, theo quy tắc binder/khởi tạo của Boot. Đây là một **entry point riêng** trong vòng đời ứng dụng, không phải tác dụng của annotation `@NotNull` trên mọi object.

### JPA entity lifecycle

Với JPA/Hibernate ORM và tích hợp Bean Validation đã được kích hoạt, provider có thể được gọi ở các lifecycle events như `pre-persist`/`pre-update`. Tuy nhiên:

- Không mặc định entity được kiểm tra lúc `new Entity()`.
- Không xem `repository.save(entity)` trong mọi công nghệ lưu trữ là bảo đảm đã validate.
- Khi JPA kiểm tra tại flush/commit, thời điểm phát sinh ngoại lệ có thể **muộn hơn** lời gọi `save(...)`.
- Ngữ nghĩa nhóm/lifecycle và việc có chạy hay không phụ thuộc provider, cấu hình persistence và transaction.

### Testing, messaging, batch job, scheduled job

Một DTO nhận từ queue, file import, unit test hoặc scheduled job **không tự động** được kiểm tra chỉ vì có annotation. Người xây dựng pipeline phải bố trí lệnh `Validator.validate(...)` hoặc cấu hình integration point rõ ràng. Spring MVC không "phủ" mặc định các dữ liệu được tạo ở luồng nghiệp vụ khác.

## 13. Những nhầm lẫn phổ biến

| Hiện tượng | Nhận định sai | Nguyên nhân/hướng xử lý |
| --- | --- | --- |
| `new User()` vẫn nhận `name=""` | "`@NotBlank` bị hỏng" | Chưa có lượt validation; gọi validator hoặc vào Spring MVC đúng cách |
| REST nhận JSON thiếu field vẫn xử lý | "Có annotation nên Spring phải chặn" | Thiếu `@Valid`/`@Validated` ở tham số hoặc MVC validator chưa cấu hình |
| Gọi `service.create("")` không lỗi | "`@NotBlank` trên method không hoạt động" | Thiếu `@Validated`, thiếu post-processor/proxy, gọi nội bộ hoặc tự `new` |
| Đối tượng con sai nhưng không báo lỗi | "Bean Validation không đọc annotation của con" | Thiếu `@Valid` trên quan hệ/cascade |
| Tham số null không bị `@Email` báo lỗi | "Constraint không được gọi" | Nhiều constraint format cho phép null; kết hợp `@NotNull`/`@NotBlank` khi bắt buộc |
| Constraint thuộc group không chạy | "Annotation không nhận diện" | Group đang chạy khác group gắn trên annotation |
| Không tạo `FieldError` dù đã bind | "Binder tự động gọi validator" | Bind rồi phải gọi `binder.validate()` khi dùng API trực tiếp |
| Chỉ có `jakarta.validation-api` và khởi động lỗi | "Annotation không hoạt động" | Thiếu Bean Validation provider tương thích |
| Đổi `javax.validation.*` sang `jakarta.validation.*` chưa nhất quán | "Provider tự hiểu cả hai" | Phải đồng bộ thế hệ Spring/Boot/API và dependency |
| Lỗi parse JSON xuất hiện trước constraint | "Validator bị bỏ qua" | Deserialize chưa tạo được DTO để validate |
| Mong method validation luôn ném HTTP 400 | "Mọi validation error cùng xử lý" | MVC object, MVC method, service AOP và manual API có cơ chế lỗi khác nhau |
| Thử `@Valid` bằng một unit test tự `new` controller | "Test chứng minh endpoint không validate" | Test cần gọi qua MVC infrastructure hoặc trực tiếp Validator |

Đừng dùng `@NotNull` hoặc `@Validated` như cơ chế duy nhất để bảo vệ dữ liệu khỏi mọi đường đi. Validation là hàng rào đầu vào ở **những điểm gọi cụ thể**; các bất biến quan trọng còn cần kiểm tra ở business boundary, database constraints hoặc quy tắc domain phù hợp.

## 14. Phân biệt *validation không được gọi* và *validation đã gọi nhưng không lỗi*

Trước khi sửa code, kiểm tra lần lượt:

1. **Provider có hiện diện?** Maven/Gradle đã bao gồm Bean Validation API và provider tương thích chưa? Với Spring Boot 3+/Framework 6+, dùng `jakarta.validation.*`.
2. **Có entry point?** `Validator.validate(...)`, `DataBinder.validate()`, Spring MVC `@Valid`/`@Validated`, method-validation proxy, JPA lifecycle hay Boot binder nào thực sự chạy?
3. **Đối tượng nào được validate?** Field annotation nằm trên DTO/bean mà entry point nhận, hay trên một object khác được tạo trước đó?
4. **Đúng loại constraint?** `@Email` thường chấp nhận null; `@Size` cũng không thay `@NotNull`. Với số, dùng loại constraint tương thích với type.
5. **Cascade và group?** Đã có `@Valid` trên nested path? Nhóm `Default`/`OnCreate` có được kích hoạt?
6. **Service proxy?** Bean được Spring quản lý hay tạo `new`? Có `@Validated` ở cấp type? Method có được interceptor advice? Có self-invocation không?
7. **Nhìn đúng đầu ra?** API Jakarta trả `Set<ConstraintViolation>`; Spring binder ghi `BindingResult`; MVC có thể ném exception; không phải tất cả đều tự ném cùng một lỗi.
8. **Lỗi sớm hơn?** JSON parse, type conversion hoặc binding có thể thất bại trước constraint validation.
9. **Test đúng điểm vào?** Dùng `MockMvc` cho MVC, inject service thật từ `ApplicationContext` cho method-validation proxy, và gọi `Validator` trực tiếp cho validation engine.

### Chiến lược kiểm thử

Với service và DTO, có thể có ba bài test riêng:

- **DTO/engine test:** inject `jakarta.validation.Validator`, gọi `validate(new UserInput(...))`, assert tập property paths của vi phạm. Test này xác nhận constraint metadata + provider.
- **MVC test:** dùng `MockMvc` gửi request sai tới endpoint thực, xác nhận HTTP response/`BindingResult` theo contract. Test này xác nhận annotation đặt đúng chỗ *và* MVC có trigger.
- **Service method test:** inject bean `@Validated` từ Spring context và gọi method với tham số sai; xác nhận exception hoặc kết quả lỗi tùy cấu hình. Không khởi tạo service bằng `new` nếu muốn test AOP trigger.

Việc cả ba test riêng tồn tại giúp phân biệt "constraint hoạt động" với "cơ chế tích hợp đã thực sự gọi constraint".

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một Java record có `@NotBlank` trên `name`; gọi `new Person("")` có tự ném `ConstraintViolationException` không?  
**Đáp:** Không chỉ vì annotation. Phải có code constructor riêng kiểm tra hoặc một lời gọi validation/entry point khác.

**Câu 2.** Service dùng `@Validated` và method có `@NotBlank`, nhưng gọi `this.method("")` từ cùng service thì sao?  
**Đáp:** Với Spring AOP proxy thông thường, lời gọi nội bộ không đi qua proxy nên có thể không được kiểm tra.

**Câu 3.** DTO trong `@RequestBody` có `@NotBlank`; đặt `@Valid` ở tham số controller để làm gì?  
**Đáp:** Yêu cầu Spring MVC gọi validator sau khi binding/deserialization thành công, trong cơ chế hỗ trợ.

**Câu 4.** `@Valid` trên field `Address` có chạy khi chưa hề validate object cha?  
**Đáp:** Không. Nó chỉ yêu cầu cascade khi lượt validation diễn ra.

**Câu 5.** `validator.validate(dto)` tự ném exception nếu có vi phạm?  
**Đáp:** Không theo API Jakarta thông thường; nó trả `Set<ConstraintViolation<T>>` và caller xử lý.

**Câu 6.** `@NotNull` trên entity có bảo đảm object không bao giờ mang null?  
**Đáp:** Không. Nó được đánh giá khi cơ chế Bean Validation được gọi; database constraint là một tầng khác.

**Câu 7.** Để xác minh Spring service proxy thật sự hoạt động, nên test bằng object `new` hay bean inject từ context?  
**Đáp:** Bean được inject từ context và gọi qua public boundary có interceptor.

**Thông điệp cần nhớ:** **Viết constraint là khai báo luật; gọi đúng validation mechanism là thực thi luật.** Hãy xác định rõ *ai gọi, gọi ở đâu, khi nào, trên đối tượng nào và với group nào*.

## Tài liệu tham khảo chính thức

- Spring Framework Reference — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework Reference — Spring Validation và DataBinder: https://docs.spring.io/spring-framework/reference/core/validation/validator.html
- Spring Framework Reference — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework Reference — Global MVC Validator: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html
- Spring Boot Reference — Validation và method validation: https://docs.spring.io/spring-boot/reference/io/validation.html
- Spring API — `@Validated`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/annotation/Validated.html
- Jakarta Validation specification: https://jakarta.ee/specifications/bean-validation/
