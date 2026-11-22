# @Target, @Retention và khả năng áp dụng lặp của ràng buộc tùy chỉnh

Trong Spring Framework, một ràng buộc Jakarta Validation tùy chỉnh thường được khai báo bằng một **annotation** và một lớp triển khai `ConstraintValidator`. Ba meta-annotation của Java quyết định annotation đó có thể đặt **ở đâu**, còn tồn tại **đến lúc nào**, và có thể viết **nhiều lần trên cùng một vị trí** hay không:

- `@Target`: những vị trí Java cho phép gắn annotation.
- `@Retention`: thời điểm annotation được giữ lại đến đâu; Bean Validation cần đọc metadata lúc chạy.
- `@Repeatable`: cho phép lặp một loại annotation với các tham số khác nhau trên cùng phần tử; Jakarta Validation xử lý từng ràng buộc được khai báo.

Ba khái niệm này có vai trò khác nhau. Chúng cũng **không tự kích hoạt validation**: annotation phải là constraint hợp lệ (`@Constraint`, `message`, `groups`, `payload` và validator phù hợp), ứng dụng cần một Jakarta Validation provider, và cần có điểm kích hoạt xác thực (ví dụ `Validator.validate(...)` hoặc tích hợp validation của Spring).

## 1. `@Target`: constraint được phép đặt ở đâu?

`@Target` nhận một hay nhiều hằng từ `java.lang.annotation.ElementType`. Trình biên dịch kiểm tra việc sử dụng annotation theo các vị trí này; chúng không phải danh sách các kiểu dữ liệu mà validator hỗ trợ.

| `ElementType` | Ý nghĩa đối với custom constraint | Ví dụ |
|---|---|---|
| `FIELD` | Trường của bean, kể cả trường `private` | `@Matches private String code;` |
| `METHOD` | Phương thức, thường là getter/giá trị trả về | Gắn lên `getCode()` |
| `PARAMETER` | Tham số phương thức hoặc constructor | `void save(@Matches String code)` |
| `CONSTRUCTOR` | Bản thân constructor, khi ràng buộc giá trị trả về hoặc quy tắc thực thi phù hợp | Constraint trên constructor |
| `ANNOTATION_TYPE` | Dùng làm meta-annotation để ghép constraint | Đặt constraint này trên annotation khác |
| `TYPE_USE` | Một vị trí sử dụng kiểu, đặc biệt type argument của collection | `List<@Matches String>` |
| `TYPE` | Khai báo class/interface/record | Constraint kiểm tra cả đối tượng |

Chọn các target theo **ngữ nghĩa của validator**, thay vì sao chép mọi target có thể có. Chẳng hạn, validator `ConstraintValidator<Matches, String>` chỉ hiểu chuỗi nên annotation mẫu bên dưới không khai báo `TYPE` để áp dụng lên cả một class. `TYPE_USE` hữu ích cho `List<@Matches String>`; nó không có nghĩa là provider tự biết cách kiểm tra mọi cấu trúc generic bất kỳ. Container element validation còn phụ thuộc value extractor mà Jakarta Validation hỗ trợ.

Ví dụ (rút gọn, chỉ minh họa vị trí):

~~~java
// FIELD: kiểm tra thuộc tính khi bean được validate.
@Matches(regexp = "[A-Z]+")
private String code;

// PARAMETER: hợp lệ về cú pháp nhờ ElementType.PARAMETER.
// Việc kiểm tra lúc gọi method cần có cơ chế method validation.
void submit(@Matches(regexp = "[A-Z]+") String code) { }

// TYPE_USE: áp dụng từng String trong container được hỗ trợ.
private java.util.List<@Matches(regexp = "[A-Z]+") String> codes;
~~~

Nếu `@Target` chỉ có `FIELD` mà lại đặt annotation trên phương thức, `javac` báo lỗi vị trí áp dụng không hợp lệ. Ngược lại, cho phép `PARAMETER` chưa đủ để mọi lệnh gọi phương thức bị chặn: Spring cần được cấu hình và đi qua cơ chế method validation thích hợp. `METHOD` trên getter và `FIELD` trên field có thể cùng biểu đạt một thuộc tính; tránh vô tình khai báo hai constraint tương đương gây ra nhiều lỗi trùng nội dung.

## 2. `@Retention`: tại sao custom constraint cần `RUNTIME`?

`@Retention` nhận một giá trị `RetentionPolicy`:

| Policy | Sau biên dịch | Đọc bằng reflection lúc chạy? | Phù hợp Jakarta Validation? |
|---|---|---|---|
| `SOURCE` | Không được giữ trong file `.class` | Không | Không |
| `CLASS` | Có trong `.class` nhưng không được giữ cho runtime reflection | Không | Không |
| `RUNTIME` | Được giữ trong `.class` và hiện diện ở runtime | Có | **Có** |

Nếu không khai báo `@Retention`, mặc định Java là `CLASS`. Với ràng buộc Jakarta Validation, dùng:

~~~java
@Retention(RetentionPolicy.RUNTIME)
~~~

Provider như Hibernate Validator cần tìm constraint metadata khi xác thực đối tượng. Annotation `@Constraint` không thể bù cho việc chính custom annotation đã bị giữ ở `SOURCE` hoặc `CLASS`. `RUNTIME` bảo đảm metadata có thể được quan sát, nhưng **không bảo đảm constraint sẽ chạy** nếu thiếu provider, validator, hoặc lời gọi validation.

`@Documented` là meta-annotation khác giúp annotation xuất hiện trong Javadoc; nó không thay thế `@Retention(RUNTIME)` và không kích hoạt logic kiểm tra.

## 3. `@Repeatable`: nhiều điều kiện độc lập trên cùng một phần tử

Một mã có thể phải đồng thời thỏa hai quy tắc: bắt đầu bằng chữ in hoa **và** chỉ chứa 4–12 chữ cái. Nếu cùng dùng `@Matches` hai lần trên một field, Java yêu cầu annotation `Matches` được khai báo repeatable.

Mẫu chuẩn gồm hai thành phần:

1. Trên annotation chính: `@Repeatable(Matches.List.class)`.
2. Một **container annotation** `Matches.List` có phần tử `Matches[] value()`; container có `@Retention(RUNTIME)` và target tương thích với `Matches`.

Ví dụ cách sử dụng mong muốn:

~~~java
@Matches(regexp = "[A-Z].*", message = "Phải bắt đầu bằng chữ hoa")
@Matches(regexp = "[A-Za-z]{4,12}", message = "Chỉ chữ cái, dài 4–12 ký tự")
private String value;
~~~

Cả hai ràng buộc đều được kiểm tra khi đối tượng được validate; với giá trị `"a3"`, cả hai đều vi phạm. `@Repeatable` cho phép **nhiều khai báo cùng loại**, không làm constraint “lặp cho đến khi đạt”, không tự tạo vòng lặp và không thay thế `@Valid`.

Ở mức Java, trình biên dịch có thể đóng các annotation lặp vào container `Matches.List`. Để đọc đúng các lần khai báo qua reflection, dùng `getAnnotationsByType(Matches.class)` hoặc `getDeclaredAnnotationsByType(Matches.class)`; `getAnnotation(Matches.class)` có thể trả về `null` khi hai annotation đã được lưu dưới container. Jakarta Validation có quy tắc nhận dạng multi-valued constraint annotation: các phần tử trong `value()` của container được xử lý như những constraint độc lập.

Cú pháp container tường minh sau có hiệu ứng validation tương đương trong ngữ cảnh này:

~~~java
@Matches.List({
    @Matches(regexp = "[A-Z].*", message = "Phải bắt đầu bằng chữ hoa"),
    @Matches(regexp = "[A-Za-z]{4,12}", message = "Chỉ chữ cái, dài 4–12 ký tự")
})
private String value;
~~~

Tên `List` là quy ước được Jakarta Validation khuyến nghị, **không** phải `java.util.List`. Nếu container không có `value()` kiểu `Matches[]`, hoặc retention/target không tương thích, Java sẽ từ chối thiết kế repeatable. Container thông thường **không** được đánh dấu `@Constraint` riêng: nó là vỏ chứa các constraint con, không phải một logic kiểm tra thứ ba.

## 4. Ví dụ hoàn chỉnh: một custom constraint có thể lặp trong Spring Boot

Ví dụ dùng **Java 17+**, `jakarta.validation.*`, một ứng dụng Spring Boot đã cấu hình dependency `spring-boot-starter-validation` (và Spring Boot parent/BOM). Các lớp nằm cùng package `com.example.validation`. Provider trong starter thực thi constraint; `CommandLineRunner` tạo dữ liệu sai, gọi `Validator` và in số lỗi. Đây là chương trình chạy được **khi đặt trong project Spring Boot hợp lệ**, không phải ví dụ thuần JDK chỉ cần `javac`.

### 4.1. Khai báo annotation — `Matches.java`

~~~java
package com.example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Constraint(validatedBy = MatchesValidator.class)
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Matches.List.class)
public @interface Matches {
    String regexp();

    String message() default "Giá trị không khớp {regexp}";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};

    @Documented
    @Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE,
        ElementType.TYPE_USE
    })
    @Retention(RetentionPolicy.RUNTIME)
    @interface List {
        Matches[] value();
    }
}
~~~

Điểm cần đọc đúng:

- `@Constraint(validatedBy = MatchesValidator.class)` khai báo validator cho constraint.
- `regexp()` là tham số cấu hình riêng của constraint; `message`, `groups`, `payload` là các phần tử chuẩn của một định nghĩa Jakarta Validation.
- `@Target` và `@Retention` xuất hiện ở cả annotation chính và container; `@Repeatable` chỉ gắn lên annotation chính.
- `@Documented` giúp Javadoc rõ ràng; không ảnh hưởng kết quả kiểm tra.

### 4.2. Logic kiểm tra — `MatchesValidator.java`

~~~java
package com.example.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import java.util.regex.Pattern;

public final class MatchesValidator
        implements ConstraintValidator<Matches, String> {

    private Pattern pattern;

    @Override
    public void initialize(Matches annotation) {
        this.pattern = Pattern.compile(annotation.regexp());
    }

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {
        return value == null || pattern.matcher(value).matches();
    }
}
~~~

`initialize` lấy cấu hình `regexp` của **từng lần khai báo `@Matches`**, biên dịch regex, rồi `isValid` kiểm tra giá trị. Trả về `true` khi `null` là cách thiết kế thông dụng để tách kiểm tra tính hợp lệ về định dạng khỏi yêu cầu bắt buộc nhập; nếu cần chống `null`, kết hợp `@NotNull`. `Pattern.matcher(...).matches()` đòi hỏi **toàn bộ chuỗi** khớp regex. Với regex phức tạp, cân nhắc kiểm tra/cố định cấu hình regex ở thời điểm xây dựng annotation để phát hiện cấu hình lỗi sớm.

### 4.3. Đối tượng nhận ràng buộc — `AccountCode.java`

~~~java
package com.example.validation;

public final class AccountCode {

    @Matches(
        regexp = "[A-Z].*",
        message = "Phải bắt đầu bằng chữ hoa")
    @Matches(
        regexp = "[A-Za-z]{4,12}",
        message = "Chỉ chữ cái, dài 4–12 ký tự")
    private final String value;

    public AccountCode(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

Đây là **hai constraint instances** có cùng kiểu, cùng field, nhưng cấu hình và thông báo khác nhau. `"ABcd"` đạt cả hai; `"a3"` vi phạm cả hai; `"Abc"` đạt điều kiện đầu nhưng không đạt độ dài tối thiểu. Mỗi constraint được đánh giá trong lần gọi `validator.validate(...)` theo ngữ nghĩa mặc định; thứ tự trả về các `ConstraintViolation` không được bảo đảm.

### 4.4. Kích hoạt validation và quan sát kết quả — `DemoApplication.java`

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
    public void run(String... args) throws NoSuchFieldException {
        var violations = validator.validate(new AccountCode("a3"));

        System.out.println("Số lỗi: " + violations.size());
        violations.stream()
            .map(v -> v.getMessage())
            .sorted()
            .forEach(System.out::println);

        var declared = AccountCode.class
            .getDeclaredField("value")
            .getAnnotationsByType(Matches.class);

        System.out.println(
            "Số @Matches qua reflection: " + declared.length);
    }
}
~~~

Dependency cần có trong `pom.xml` của project Spring Boot đang quản lý phiên bản dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Chạy tại thư mục project Maven đã có Spring Boot parent/BOM và Spring Boot Maven plugin:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows, dùng `mvnw.cmd spring-boot:run`. Ngoài các dòng log khởi động Spring Boot, đoạn demo in chính xác bốn dòng sau (đã sắp xếp thông báo để kết quả ổn định):

~~~text
Số lỗi: 2
Chỉ chữ cái, dài 4–12 ký tự
Phải bắt đầu bằng chữ hoa
Số @Matches qua reflection: 2
~~~

Nếu thay `"a3"` bằng `"ABcd"`, số lỗi là `0` còn số annotation quan sát qua reflection vẫn là `2`: **khai báo ràng buộc** không phụ thuộc giá trị đầu vào, còn **vi phạm** phụ thuộc giá trị được kiểm tra.

## 5. Liên hệ với Spring MVC, binding và container elements

**Binding và validation là hai giai đoạn liên quan nhưng khác nhau.** Spring có thể bind dữ liệu HTTP thành object; việc các constraint được thực thi phụ thuộc điểm kích hoạt validation.

Ví dụ một DTO:

~~~java
public class CreateAccountRequest {
    @Matches(regexp = "[A-Z].*")
    @Matches(regexp = "[A-Za-z]{4,12}")
    private String code;

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }
}
~~~

Với Spring MVC được cấu hình Jakarta Validation, tham số controller kiểu `@Valid @RequestBody CreateAccountRequest request` là một đường kích hoạt kiểm tra object sau binding. Annotation được phép đặt lên field nhờ `FIELD`, có ở runtime nhờ `RUNTIME`, và được áp dụng hai lần nhờ `@Repeatable`. Cách xử lý lỗi HTTP thực tế phụ thuộc cấu hình/controller exception handling.

Đối với `List<@Matches(regexp = "[A-Z]+") String>`, `TYPE_USE` cho phép constraint gắn lên **phần tử chuỗi** của container khi provider hỗ trợ value extraction. Đối với `List<@Valid Address>`, `@Valid` là cơ chế **cascade** để đi vào bean `Address`; nó khác với `@Repeatable`. Một annotation áp dụng trên tham số phương thức cũng cần cơ chế method validation phù hợp; việc method tồn tại và được gọi chưa đủ để tự chạy Jakarta Validation.

## 6. Lỗi phổ biến và cách chẩn đoán

| Biểu hiện | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
|---|---|---|
| Compile error khi đặt trên field, method hoặc type argument | `@Target` thiếu `FIELD`, `METHOD`, `PARAMETER` hoặc `TYPE_USE` tương ứng | So sánh vị trí sử dụng thực tế với danh sách `ElementType` |
| Constraint không được phát hiện lúc runtime | Dùng `SOURCE`, `CLASS` hoặc bỏ `@Retention` nên mặc định là `CLASS` | Đặt `@Retention(RUNTIME)` cho annotation chính và container |
| Compiler báo annotation không repeatable | Viết hai annotation cùng loại nhưng chưa có `@Repeatable`/container hợp lệ | Khai báo `@Repeatable(Matches.List.class)` và `Matches[] value()` |
| Compile error trong định nghĩa `@Repeatable` | Container có retention ngắn hơn, target không tương thích hoặc `value()` sai kiểu | Đối chiếu `@Target`, `@Retention` của hai annotation |
| Reflection thấy container nhưng không thấy từng annotation | Đọc qua `getAnnotation(Matches.class)` khi có nhiều lần khai báo | Dùng `getAnnotationsByType(Matches.class)` |
| Không có lỗi dù dữ liệu sai | Chưa có Jakarta Validation provider, chưa kích hoạt validation, hoặc validator trả về `true` | Xác nhận starter/provider, `@Constraint`, `Validator.validate` hoặc điểm kích hoạt Spring |
| `UnexpectedTypeException` | Áp constraint cho kiểu mà `ConstraintValidator<..., String>` không hỗ trợ | Điều chỉnh target/vị trí, kiểu dữ liệu hoặc thêm validator đúng kiểu |
| Có lỗi trùng hoặc kết quả ngoài dự kiến | Gắn constraint tương đương cả field và getter, hoặc lặp cùng điều kiện | Xem metadata từng vị trí và ý đồ của từng constraint |
| `null` vẫn hợp lệ | Validator cố ý cho `null` đi qua | Thêm `@NotNull` nếu trường bắt buộc |
| Không tự kiểm tra tham số khi gọi method | `PARAMETER` chỉ cho phép đặt annotation về cú pháp | Kích hoạt method validation theo cơ chế Spring đang sử dụng |

## 7. Checklist thiết kế constraint có thể lặp

Trước khi đưa annotation custom vào codebase, tự trả lời:

1. **Vị trí nào hợp lệ?** Chỉ khai báo những `ElementType` đúng với ý nghĩa và kiểu dữ liệu hỗ trợ; thêm `TYPE_USE` nếu cần container element constraints.
2. **Metadata có còn ở runtime?** Annotation chính và container đều `@Retention(RUNTIME)`.
3. **Có cần áp cùng một constraint nhiều lần không?** Nếu có, khai báo `@Repeatable` và container `List` với `value()` là mảng annotation chính.
4. **Đây có thật sự là constraint?** Có `@Constraint`, `message`, `groups`, `payload`, và `ConstraintValidator`/composition hợp lệ.
5. **Ai kích hoạt kiểm tra?** `@Valid`/`@Validated` ở nơi phù hợp hoặc `Validator.validate(...)`; hiểu rõ method validation và bean validation trong ứng dụng.
6. **Kết quả có đáng tin?** Thử mẫu hợp lệ, vi phạm một quy tắc, vi phạm nhiều quy tắc, `null`, type không hỗ trợ, và đọc lại annotation bằng `getAnnotationsByType`.

**Ghi nhớ:** `@Target` = *đặt ở đâu*; `@Retention(RUNTIME)` = *có thể được tìm thấy lúc chạy*; `@Repeatable` + container = *được khai báo nhiều lần*. Ba điều này phối hợp với `@Constraint`, `ConstraintValidator` và điểm kích hoạt validation để tạo một ràng buộc tùy chỉnh hoạt động đúng trong Spring.

## Tài liệu gốc

- [Jakarta Validation 3.1 Specification — Constraint definition & Applying multiple constraints](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#constraintdefinition)
- [Jakarta Validation API — `@Constraint`](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/constraint)
- [Java SE 21 — `@Repeatable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Repeatable.html)
- [Java SE 21 — `@Retention`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Retention.html)
- [Java SE 21 — `AnnotatedElement.getAnnotationsByType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [Spring Framework — Java Bean Validation & custom constraints](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
