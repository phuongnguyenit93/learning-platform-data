# Phân biệt Spring Validator, Jakarta Validation và thư viện triển khai

## 1. Ba khái niệm ở ba vai trò khác nhau

Khi ứng dụng nhận một đối tượng đăng ký thành viên, ta muốn bảo đảm `name` không rỗng và `age >= 18`. Có thể gặp cả `org.springframework.validation.Validator`, `jakarta.validation.Validator` và Hibernate Validator trong cùng dự án. Chúng **không phải ba API đồng nghĩa**:

- **Spring Validator**: hợp đồng kiểm tra đối tượng do Spring Framework cung cấp, tập trung vào `supports(Class<?>)`, `validate(Object, Errors)` và hệ thống lỗi `Errors`/`BindingResult`. Lập trình viên thường tự viết luật kiểm tra bằng Java.
- **Jakarta Validation** (còn gọi là Jakarta Bean Validation): **đặc tả/API chuẩn** định nghĩa các annotation ràng buộc như `@NotBlank`, `@Min`, `@Valid`, cũng như `jakarta.validation.Validator`, `ValidatorFactory` và `ConstraintViolation`. API quy định cách yêu cầu và nhận kết quả validation, không tự cung cấp toàn bộ bộ máy thực thi.
- **Provider/implementation**: thư viện hiện thực Jakarta Validation, phổ biến là **Hibernate Validator**; ngoài ra có Apache BVal. Provider đọc metadata ràng buộc và thật sự đánh giá đối tượng. Hibernate Validator **khác Hibernate ORM/JPA**.

Bức tranh tích hợp thường là:

```text
HTTP request -> deserialize / data binding -> đối tượng Java
                           |
                           +-> Spring WebDataBinder / Errors / BindingResult
                           |        ^ có thể gọi Spring Validator tự viết
                           |        ^ hoặc adapter LocalValidatorFactoryBean
                           |
                           +-> Jakarta Validation API (Validator, constraints)
                                             |
                                             v
                                Provider (ví dụ Hibernate Validator)
                                             |
                                             v
                                   ConstraintViolation
```

Spring Framework có cơ chế **chuyển lỗi Jakarta Validation sang lỗi Spring** khi cần làm việc với `BindingResult`. Vì thế một đối tượng khai báo annotation Jakarta vẫn được xử lý tự nhiên trong Spring MVC.

## 2. Spring Validator: lập trình kiểm tra và ghi lỗi theo kiểu Spring

Interface `org.springframework.validation.Validator` có hai phương thức cốt lõi:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

- `supports` xác định kiểu đối tượng validator này xử lý được; cần phù hợp với kiểu mà `DataBinder` sẽ đưa vào.
- `validate` đọc trạng thái đối tượng rồi ghi lỗi qua `errors.reject(...)` cho lỗi tổng thể hoặc `errors.rejectValue("field", "error.code")` cho lỗi thuộc một trường.
- `Errors` chứa các mã lỗi, đối số thông điệp và thông tin trường; `BindingResult` mở rộng `Errors` để cung cấp thông tin binding và `FieldError`/`ObjectError`.
- `DataBinder` có thể đăng ký một hoặc nhiều validator và gọi `validate()`. Trong Spring MVC, `WebDataBinder` được sử dụng để gắn dữ liệu request và có thể cấu hình bằng `@InitBinder`.

Ví dụ một luật không thuộc annotation có sẵn:

```java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class PasswordMatchValidator implements Validator {
    @Override
    public boolean supports(Class<?> type) {
        return SignupForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        SignupForm form = (SignupForm) target;
        if (form.getPassword() != null
                && !form.getPassword().equals(form.getConfirmPassword())) {
            errors.rejectValue(
                "confirmPassword", "password.mismatch",
                "Mật khẩu xác nhận không khớp"
            );
        }
    }
}
```

*Đoạn này minh họa validator, cần lớp `SignupForm` có các getter tương ứng; ví dụ chạy độc lập ở mục 6.* Spring Validator thích hợp với luật phức tạp, phụ thuộc nhiều trường hoặc quy trình form/binding, và khi cần tự kiểm soát mã lỗi để tra thông điệp từ `MessageSource`. Một luật liên trường cũng có thể được hiện thực bằng custom Jakarta constraint; lựa chọn phụ thuộc mức độ cần tái sử dụng ngoài Spring.

**Điểm cần nhớ:** interface Spring `Validator` không tự quét `@NotBlank`/`@Min`. Việc xử lý các annotation đó là công việc của Jakarta Validation provider hoặc adapter phù hợp.

## 3. Jakarta Validation: hợp đồng chuẩn và ràng buộc khai báo

Các thành phần chính thuộc namespace `jakarta.validation` và `jakarta.validation.constraints`:

| Thành phần | Chức năng |
| --- | --- |
| `@NotNull` | Giá trị khác `null`; chuỗi rỗng hoặc chỉ chứa khoảng trắng vẫn hợp lệ. |
| `@NotBlank` | Chuỗi `CharSequence` phải khác `null` và có ít nhất một ký tự không phải khoảng trắng. |
| `@NotEmpty` | Chuỗi, collection, map, array… phải khác `null` và không rỗng; chuỗi chỉ có dấu cách vẫn có thể hợp lệ. |
| `@Size(min, max)` | Độ dài/kích thước hợp lệ; không thay thế `@NotNull`. |
| `@Min`, `@Max`, `@Positive`, `@Email`, `@Pattern` | Các luật số, định dạng hoặc biểu thức tương ứng; `@Email` không thay thế kiểm tra địa chỉ thật sự tồn tại. |
| `@Valid` | Yêu cầu validation lan xuống đối tượng/phần tử lồng nhau tại điểm đã cấu hình cascade. |
| `@ConvertGroup`, `groups` | Chọn/chuyển nhóm ràng buộc trong các kịch bản khác nhau. |
| `Validator#validate` | Thực thi validation thông qua provider và trả về `Set<ConstraintViolation<T>>`. |

Ví dụ một DTO:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record RegistrationRequest(
    @NotBlank String name,
    @Min(18) int age,
    @NotNull @Valid Address address
) {}

record Address(@NotBlank String city) {}
```

Khi provider validate `RegistrationRequest`, `@Valid` cho phép kiểm tra `Address.city`. Nếu bỏ `@Valid` ở trường `address`, các ràng buộc bên trong `Address` sẽ không tự động được duyệt theo đường cascade đó. `@Valid` **không phải ràng buộc chống null**; vì vậy ví dụ kết hợp với `@NotNull`. Các constraint như `@NotBlank`, `@Min` không hoạt động chỉ vì annotation xuất hiện trong mã: phải có một entry point gọi validation, ví dụ `jakarta.validation.Validator#validate`, Spring MVC kích hoạt validation cho request, hoặc một cơ chế method validation đã cấu hình.

Kết quả Jakarta Validation là các đối tượng `ConstraintViolation` chứa đường dẫn thuộc tính (`getPropertyPath()`), thông điệp (`getMessage()`), giá trị không hợp lệ (`getInvalidValue()`), descriptor của constraint… Chúng **không phải** `FieldError` của Spring.

## 4. Provider: thư viện thật sự đánh giá constraint

`jakarta.validation-api` chỉ định nghĩa hợp đồng. **Hibernate Validator** là một provider của hợp đồng đó: nhận metadata annotation, chạy các `ConstraintValidator` và trả kết quả theo API chuẩn. Khi chạy độc lập, có thể khởi tạo bằng:

```java
try (jakarta.validation.ValidatorFactory factory =
         jakarta.validation.Validation.buildDefaultValidatorFactory()) {
    jakarta.validation.Validator validator = factory.getValidator();
    var violations = validator.validate(object);
}
```

Provider được tìm qua cơ chế bootstrap của Jakarta Validation. Nếu chỉ có API mà **không có provider hợp lệ trên runtime classpath**, `buildDefaultValidatorFactory()` sẽ không tạo được factory (thường báo `NoProviderFoundException`). Trong Spring Boot 3, dependency `spring-boot-starter-validation` là lựa chọn thông dụng để kéo API cùng provider tương thích, thay vì thêm mỗi API rồi mong annotation tự chạy.

Một provider có thể có extension nằm trong namespace riêng, chẳng hạn `org.hibernate.validator.constraints`. Dùng constraint thuộc chuẩn `jakarta.validation.constraints` khi có thể để tránh khóa vào một triển khai. Không nên mặc định phiên bản Hibernate Validator mới nhất luôn phù hợp: chọn phiên bản được Spring Boot BOM quản lý hoặc kiểm tra mức tương thích giữa Spring, Jakarta Validation và provider.

### Adapter của Spring: LocalValidatorFactoryBean

`org.springframework.validation.beanvalidation.LocalValidatorFactoryBean` là cầu nối giữa hai thế giới. Nó cấu hình/khởi tạo Jakarta `ValidatorFactory` thông qua provider và đồng thời thích ứng với hợp đồng `org.springframework.validation.Validator`, giúp Spring chuyển các `ConstraintViolation` thành `Errors`/`BindingResult` khi cần.

Trong cấu hình Spring MVC thông dụng, khi Bean Validation provider nằm trên classpath, Spring có thể đăng ký `LocalValidatorFactoryBean` làm validator toàn cục. Điều này giải thích tại sao `@Valid @RequestBody` hoạt động trong controller và lỗi constraint có thể xuất hiện dưới dạng `FieldError`, dù DTO không có một Spring Validator tự viết. **Adapter không phải provider**; nó vẫn cần thư viện triển khai bên dưới.

## 5. So sánh nhanh

| Tiêu chí | Spring Validator | Jakarta Validation | Provider (Hibernate Validator) |
| --- | --- | --- | --- |
| Bản chất | API/hợp đồng của Spring | Đặc tả và API chuẩn Jakarta | Thư viện hiện thực chuẩn |
| Namespace tiêu biểu | `org.springframework.validation.*` | `jakarta.validation.*` | `org.hibernate.validator.*` (cùng API Jakarta) |
| Khai báo quy tắc | Mã Java trong `validate` | Annotation hoặc constraint tùy biến | Đọc và thực thi rule của đặc tả; có extension riêng |
| Đầu vào | `Object` + `Errors` | Đối tượng + nhóm validation | Được gọi qua Jakarta API/adapter |
| Kết quả thường thấy | `FieldError`, `ObjectError` qua `BindingResult` | `ConstraintViolation` | Tạo violation theo hợp đồng Jakarta |
| Phụ thuộc Spring? | Có | Không | Không bắt buộc |
| Cần provider Jakarta? | Không, nếu chỉ dùng luật Spring tự viết | Có, để thực thi chuẩn | Chính nó là provider |
| Khi nên chọn | Form binding, lỗi nghiệp vụ tùy biến, cần mã lỗi Spring | DTO/domain dùng rule khai báo, tái sử dụng nhiều tầng | Chọn implementation tương thích cho Jakarta Validation |

Đừng nhầm hai interface trùng tên: `org.springframework.validation.Validator` **khác** `jakarta.validation.Validator`. Trong một file Java dùng cả hai, nên viết tên đầy đủ ở nơi dễ gây nhầm lẫn; Java không hỗ trợ alias import.

## 6. Ví dụ Java 17 chạy được: cùng dữ liệu, hai cách validation

Ví dụ này chạy **Spring Validator tự viết** và **Jakarta Validation qua Hibernate Validator** trên cùng một đối tượng. Dùng Maven và JDK 17+, không cần khởi động HTTP server.

Cấu trúc:

```text
validation-comparison/
├── pom.xml
└── src/main/java/demo/ValidationComparisonDemo.java
```

File `pom.xml` (Spring Boot 3.3.5 quản lý các dependency Java 17/Spring 6/Jakarta; phiên bản được cố định ở đây để ví dụ tái lập được):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>validation-comparison</artifactId>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/ValidationComparisonDemo.java`:

```java
package demo;

import java.util.List;
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;

public class ValidationComparisonDemo {

    public static final class Member {
        @NotBlank
        private final String name;

        @Min(18)
        private final int age;

        public Member(String name, int age) {
            this.name = name;
            this.age = age;
        }

        public String getName() {
            return name;
        }

        public int getAge() {
            return age;
        }
    }

    public static final class MemberSpringValidator
            implements org.springframework.validation.Validator {

        @Override
        public boolean supports(Class<?> type) {
            return Member.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "name", "name.required"
            );
            Member member = (Member) target;
            if (member.getAge() < 18) {
                errors.rejectValue("age", "age.under18");
            }
        }
    }

    public static void main(String[] args) {
        Member member = new Member(" ", 16);

        // Luồng 1: validator của Spring -> BindingResult / FieldError.
        DataBinder binder = new DataBinder(member, "member");
        binder.addValidators(new MemberSpringValidator());
        binder.validate();
        List<String> springErrors = binder.getBindingResult()
            .getFieldErrors().stream()
            .map(error -> {
                String[] codes = error.getCodes();
                String baseCode = codes[codes.length - 1];
                return error.getField() + ":" + baseCode;
            })
            .sorted()
            .toList();
        System.out.println("Spring: " + springErrors);

        // Luồng 2: Jakarta API -> provider -> ConstraintViolation.
        try (ValidatorFactory factory =
                 Validation.buildDefaultValidatorFactory()) {
            jakarta.validation.Validator validator = factory.getValidator();
            List<String> jakartaErrors = validator.validate(member).stream()
                .map(violation -> violation.getPropertyPath() + ":"
                    + violation.getConstraintDescriptor()
                        .getAnnotation().annotationType().getSimpleName())
                .sorted()
                .toList();
            System.out.println("Jakarta: " + jakartaErrors);
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ValidationComparisonDemo
```

Hai dòng mà mã chương trình in ra (log của thư viện, nếu có, có thể xuất hiện thêm):

```text
Spring: [age:age.under18, name:name.required]
Jakarta: [age:Min, name:NotBlank]
```

Giải thích: cả hai phát hiện `name` chỉ có khoảng trắng và `age` nhỏ hơn 18. Spring trả lỗi với **mã do người lập trình đặt** (`age.under18`, `name.required`); Jakarta trả **violation gắn với loại constraint chuẩn** (`Min`, `NotBlank`). Ở Spring, mã lỗi sau khi qua `MessageCodesResolver` có thể được mở rộng theo object/field/type; ví dụ chủ động lấy phần tử cuối của `getCodes()` để hiển thị mã cơ sở ổn định.

## 7. Trong Spring MVC, mỗi vai trò tham gia ở đâu?

Với Spring Boot 3 + Spring MVC, cần `spring-boot-starter-web` cho controller và `spring-boot-starter-validation` cho Bean Validation provider. Đây là **đoạn mã controller minh họa**, đặt trong ứng dụng Boot Web đã cấu hình; không phải chương trình độc lập ở mục 6:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

record CreateMemberRequest(@NotBlank String name, @Min(18) int age) {}

@RestController
class MemberController {
    @PostMapping("/members")
    ResponseEntity<Void> create(@Valid @RequestBody CreateMemberRequest request) {
        // Chỉ xử lý khi request vượt qua validation cho đối số này.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Luồng thường gặp:

1. Spring MVC đọc JSON, chuyển thành `CreateMemberRequest` (deserialization/binding).
2. `@Valid` yêu cầu chạy Jakarta Bean Validation trên object; adapter `LocalValidatorFactoryBean` chuyển công việc cho provider.
3. Nếu có violation và không đặt `Errors`/`BindingResult` ngay sau tham số đó, validation ở mức đối số sẽ dẫn tới `MethodArgumentNotValidException` (thường thành HTTP 400 theo cấu hình MVC mặc định).
4. Nếu muốn xử lý lỗi tại controller, có thể đặt `BindingResult` **ngay sau** tham số được validate, ví dụ `create(@Valid @RequestBody CreateMemberRequest request, BindingResult errors)`, rồi tự xét `errors.hasErrors()` và trả response phù hợp.

**Phân biệt thêm method validation:** từ Spring Framework 6.1, khi controller có constraint trực tiếp trên tham số/phương thức (chẳng hạn `@RequestParam @Min(1) int page`), cơ chế method validation tích hợp MVC có thể áp dụng và lỗi thuộc nhóm `HandlerMethodValidationException`. Nó khác validation của một đối tượng `@Valid @RequestBody` thông thường. Với controller cần cơ chế MVC tích hợp này, tránh đặt `@Validated` ở cấp lớp chỉ để bật validation vì annotation cấp lớp sẽ chuyển sang đường AOP proxy.

Để thêm validator Spring riêng cho một controller, có thể đăng ký qua `@InitBinder`:

```java
@InitBinder("memberForm")
void initMemberBinder(WebDataBinder binder) {
    binder.addValidators(new MemberSpringValidator());
}
```

Đoạn này minh họa cấu hình trong `@Controller` có model attribute tên `memberForm`, với target type phù hợp `supports`; cần import `org.springframework.web.bind.WebDataBinder` và `org.springframework.web.bind.annotation.InitBinder`. `addValidators` cho phép bổ sung luật thay vì thay thế validator toàn cục. Không áp dụng mù quáng validator chỉ hỗ trợ kiểu `Member` vào một DTO khác.

Tại tầng service, method validation dùng Jakarta constraints nhưng việc đánh giá có thể được Spring kích hoạt bằng `MethodValidationPostProcessor` và `@Validated` trên bean được gọi qua AOP proxy (Spring Boot có thể tự cấu hình khi thỏa điều kiện). Gọi nội bộ từ một method sang method khác trên chính `this` thường không đi qua proxy, nên không nên giả định constraints trên method sẽ luôn được kiểm tra. Ngoài Spring, có thể dùng API Jakarta để tự gọi `validator.validate(...)` một cách tường minh.

## 8. Chọn giải pháp theo tình huống

- **DTO request có ràng buộc đơn giản và tái sử dụng được:** dùng Jakarta constraints như `@NotBlank`, `@Size`, `@Min`; bảo đảm có provider và có nơi kích hoạt validation.
- **Luật phức tạp phụ thuộc nhiều trường và cần gắn với Spring form/binding:** cân nhắc tự viết Spring `Validator` cùng mã lỗi `Errors`; hoặc custom Jakarta class-level constraint nếu muốn luật độc lập Spring.
- **Muốn chạy validation ngoài Spring (batch job, Java SE, shared library):** phụ thuộc Jakarta API + provider tương thích và gọi `Validator#validate`.
- **Ứng dụng Spring Boot Web muốn nhận lỗi đúng chuẩn:** dùng Jakarta annotations qua `@Valid`/`@Validated`, xử lý `BindingResult` hay exception phù hợp; bổ sung Spring Validator khi thật sự có luật bổ sung.
- **Muốn cấu hình thông điệp lỗi:** Jakarta có thuộc tính `message`/message interpolation; Spring có `MessageSource` và cơ chế giải mã error codes. Hai cơ chế có thể được kết nối qua adapter nhưng không đồng nhất.

## 9. Những nhầm lẫn dễ gây lỗi

1. **Chỉ thêm `jakarta.validation-api` rồi kỳ vọng annotation tự chạy.** API không thay provider hay bước kích hoạt validation. Cần thư viện triển khai và gọi đúng entry point.
2. **Nhầm `@Valid` và `@Validated`.** `@Valid` là annotation Jakarta cho cascade/kích hoạt validation nơi framework hỗ trợ; `@Validated` là annotation Spring có thể chọn groups và tham gia cấu hình method validation. Chúng không phải hai provider khác nhau.
3. **Nhầm `javax.validation.*` với `jakarta.validation.*`.** Spring Framework 6 / Boot 3 dùng Jakarta; mã cho Spring 5 / Boot 2 thường dùng namespace cũ. Không trộn bừa annotation, API và provider khác thế hệ.
4. **Dùng `@NotNull` để cấm chuỗi trắng.** `@NotNull` chỉ cấm null; muốn cấm null/rỗng/khoảng trắng ở chuỗi, dùng `@NotBlank`.
5. **Tưởng chuyển đổi dữ liệu là validation.** JSON sai định dạng, số không parse được, thiếu converter… có thể hỏng trước bước constraint validation và dẫn tới loại lỗi khác. Cần phân biệt binding/conversion error với violation.
6. **Tưởng `BindingResult` và `ConstraintViolation` là một.** `BindingResult` là mô hình lỗi của Spring, có thể gồm cả binding errors lẫn constraint errors đã được adapter chuyển đổi.
7. **Dùng provider-specific constraint vô thức.** `org.hibernate.validator.constraints.*` không phải tất cả đều nằm trong chuẩn Jakarta; kiểm tra tính portable và tương thích.
8. **Tưởng mọi lời gọi service đều được method validation tự động chặn.** Với AOP-based method validation, phải có bean/proxy phù hợp và lời gọi đi qua proxy; self-invocation có thể bỏ qua.
9. **Không đặt `BindingResult` sát đối số được validate.** Với luồng hỗ trợ xử lý lỗi cục bộ, thứ tự tham số ảnh hưởng cách Spring MVC xử lý exception.
10. **Tưởng Hibernate Validator chính là Hibernate ORM.** Hai thư viện có mục đích khác nhau; chỉ vì dùng Spring Data JPA/Hibernate ORM không có nghĩa provider Bean Validation đã được cấu hình đúng.

## 10. Tự kiểm tra kiến thức

- Nếu chỉ có `@NotBlank` trên một DTO nhưng không có provider hoặc không ai gọi validation, điều gì xảy ra?
- Vì sao `Spring Validator` có thể chạy mà không phụ thuộc `Hibernate Validator`?
- Tại sao `LocalValidatorFactoryBean` vẫn cần provider dù nó được Spring đăng ký?
- Tình huống nào trả `ConstraintViolation`, tình huống nào trả `BindingResult`?
- Với Spring MVC 6.1+, khác biệt giữa `MethodArgumentNotValidException` và `HandlerMethodValidationException` xuất hiện trong trường hợp nào?

**Kết luận:** Spring Validator là hợp đồng validation và mô hình lỗi do Spring cung cấp; Jakarta Validation là chuẩn độc lập framework để định nghĩa/kiểm tra constraints; Hibernate Validator là một thư viện hiện thực chuẩn đó. Spring dùng adapter để kết hợp chúng, vì vậy hoàn toàn có thể sử dụng cả hai cơ chế trong cùng ứng dụng khi đúng nhu cầu.

### Tài liệu tham khảo

- Spring Framework — Validation, Data Binding, and Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework — Java Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Hibernate Validator — Getting Started: https://hibernate.org/validator/documentation/getting-started/
