# Ràng buộc chéo tham số của phương thức (Cross-parameter constraints)

## 1. Khi nào cần kiểm tra *quan hệ giữa nhiều tham số*?

Trong Jakarta Bean Validation, annotation như `@NotNull`, `@Min` hoặc `@Email` thường kiểm tra **một tham số**. Nhưng có nhiều quy tắc không thể đánh giá từng tham số riêng lẻ:

- `book(startDate, endDate)`: ngày bắt đầu không được sau ngày kết thúc.
- `transfer(fromAccount, toAccount, amount)`: tài khoản nguồn và đích phải khác nhau.
- `changePassword(newPassword, confirmation)`: hai tham số phải khớp.
- `schedule(from, to, zone)`: khoảng thời gian phải hợp lệ trong múi giờ đã chọn.

Đây là **ràng buộc chéo tham số** (*cross-parameter constraint*). Annotation gắn trực tiếp lên **method** hoặc **constructor**, còn validator nhận **mảng đối số của toàn bộ lời gọi**, thay vì chỉ một giá trị. Nó thuộc nhóm *executable validation* (kiểm tra method/constructor) của Jakarta Validation và có thể sử dụng trong Spring Framework.

Phân biệt các cấp kiểm tra:

| Cấp | Annotation đặt ở đâu? | `isValid(...)` nhận gì? | Phù hợp khi |
| --- | --- | --- | --- |
| Constraint trên một tham số | `void book(@NotNull LocalDate start)` | Một giá trị tham số (ví dụ `LocalDate`) | Yêu cầu riêng của một giá trị. |
| **Cross-parameter** | `@ValidDateRange void book(LocalDate start, LocalDate end)` | **`Object[]` gồm tất cả đối số** | Quan hệ giữa nhiều tham số trong cùng lời gọi. |
| Constraint trên return value | `@NotNull String findName()` | Giá trị trả về, kiểm tra bằng API return-value validation | Hợp đồng đầu ra. |
| Class-level constraint | `@DatesConsistent class BookingRequest` | Một đối tượng DTO | Quan hệ giữa các field/properties của bean. |

Ví dụ `@ValidDateRange` ở trên là tên minh họa. Khác với class-level constraint trên DTO, cross-parameter constraint kiểm tra trực tiếp signature lời gọi mà không buộc tạo một DTO chỉ để so sánh các argument.

**Điều rất quan trọng:** annotation trên method **không tự động được chạy chỉ vì Java gọi method**. Cần một thành phần gọi `ExecutableValidator` hoặc một cơ chế tích hợp như proxy/method interceptor của Spring.

## 2. Cấu tạo bắt buộc của cross-parameter constraint

Một ràng buộc chéo tham số tự viết có hai thành phần:

1. **Annotation constraint**: khai báo vị trí đặt annotation, validator chịu trách nhiệm và thông báo.
2. **`ConstraintValidator<Annotation, Object[]>`**: đọc mảng tham số và trả `true/false`; đánh dấu `@SupportedValidationTarget(ValidationTarget.PARAMETERS)`.

Cấu trúc tổng quát:

~~~java
@Target({ElementType.METHOD, ElementType.CONSTRUCTOR,
         ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ConsistentParametersValidator.class)
public @interface ConsistentParameters {
    String message() default "Các tham số không nhất quán";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Đây là **khai báo mẫu** trong file có đủ import; chương trình tự chạy đầy đủ xuất hiện ở phần 3.

Với validator:

~~~java
@SupportedValidationTarget(ValidationTarget.PARAMETERS)
public final class ConsistentParametersValidator
        implements ConstraintValidator<ConsistentParameters, Object[]> {

    @Override
    public boolean isValid(Object[] args,
                           ConstraintValidatorContext context) {
        // Kiểm tra tương quan giữa các phần tử args.
        return true;
    }
}
~~~

Hai khai báo trên minh họa API chính, chưa phải source file độc lập. Những điều cần hiểu:

- `ElementType.METHOD` và `ElementType.CONSTRUCTOR` cho phép annotation nằm trên method và constructor. `ANNOTATION_TYPE` hữu ích nếu muốn dùng trong constraint composition.
- `@Constraint(validatedBy = ...)` nối annotation với implementation.
- `message`, `groups`, `payload` là các thuộc tính chuẩn của custom constraint.
- `@SupportedValidationTarget(ValidationTarget.PARAMETERS)` cho provider biết đây là validator của **tập tham số**, không phải của return value. Import từ `jakarta.validation.constraintvalidation`.
- Kiểu được validate ở đây là `Object[]` (Jakarta Validation cũng cho phép `Object` theo hợp đồng); một `ConstraintValidator<..., LocalDate>` thông thường sẽ chỉ phù hợp với một giá trị, không thay thế được kiểm tra chéo.
- `args[0]` là đối số đầu tiên; `args[1]` là đối số thứ hai. Chỉ số dựa trên **vị trí tham số** tại method/constructor được gắn annotation, không theo tên biến trong source.
- Quy tắc null nên có chủ đích: thường **trả `true` khi một tham số cần so sánh đang null**, đồng thời đặt `@NotNull` trên từng tham số để tránh hai thông báo cho cùng lỗi nhập thiếu. `true` ở đây chỉ có nghĩa *cross-constraint* không báo lỗi; các constraint khác vẫn có thể fail.

### Constraint chỉ kiểm tra tham số và constraint kiểm tra cả return value

Một annotation được định nghĩa **chỉ** cho cross-parameter với validator `ValidationTarget.PARAMETERS` thường không cần thuộc tính `validationAppliesTo` vì target có thể xác định. Nhưng nếu annotation hỗ trợ **cả generic/return-value và cross-parameter** thì lời khai báo trên method có thể mơ hồ. Khi đó annotation cần thuộc tính:

~~~java
ConstraintTarget validationAppliesTo() default ConstraintTarget.IMPLICIT;
~~~

Và nơi sử dụng có thể chỉ rõ `validationAppliesTo = ConstraintTarget.PARAMETERS` (hoặc `RETURN_VALUE`), đặc biệt nếu method vừa có tham số vừa có giá trị trả về và không thể suy ra target. Cần import `jakarta.validation.ConstraintTarget`. **Không thêm tùy tiện cả hai target** nếu bài toán chỉ kiểm tra đối số; một cross-parameter validator riêng sẽ dễ hiểu hơn.

## 3. Ví dụ Spring Boot 3+, Java 17+: ngày bắt đầu không sau ngày kết thúc

Ví dụ này có thể chạy với **Java 17+**, một dự án **Spring Boot 3+** tương thích Jakarta Validation, dùng Maven. Cần có dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Tạo **`src/main/java/com/example/validation/CrossParameterDemoApplication.java`** với **toàn bộ nội dung**:

~~~java
package com.example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
import jakarta.validation.Validator;
import jakarta.validation.constraintvalidation.SupportedValidationTarget;
import jakarta.validation.constraintvalidation.ValidationTarget;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.executable.ExecutableValidator;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.time.LocalDate;

@SpringBootApplication
public class CrossParameterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CrossParameterDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner runDemo(Validator validator) {
        return args -> {
            BookingService service = new BookingService();

            Method method = BookingService.class.getMethod(
                    "reserve", LocalDate.class, LocalDate.class);

            ExecutableValidator executable = validator.forExecutables();

            Object[] valid = {
                    LocalDate.of(2026, 11, 10),
                    LocalDate.of(2026, 11, 12)
            };
            Object[] invalid = {
                    LocalDate.of(2026, 11, 12),
                    LocalDate.of(2026, 11, 10)
            };
            Object[] missing = {
                    null,
                    LocalDate.of(2026, 11, 12)
            };

            var validResults =
                    executable.validateParameters(service, method, valid);
            var invalidResults =
                    executable.validateParameters(service, method, invalid);
            var missingResults =
                    executable.validateParameters(service, method, missing);

            System.out.println("valid -> " + validResults.size());
            System.out.println("reversed -> " + invalidResults.size());
            System.out.println("missing -> " + missingResults.size());

            invalidResults.forEach(v ->
                    System.out.println("message -> " + v.getMessage()));
        };
    }

    @Target({ElementType.METHOD, ElementType.CONSTRUCTOR,
             ElementType.ANNOTATION_TYPE})
    @Retention(RetentionPolicy.RUNTIME)
    @Constraint(validatedBy = DateRangeValidator.class)
    public @interface ValidDateRange {
        String message() default
                "Ngày bắt đầu không được sau ngày kết thúc";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
    }

    @SupportedValidationTarget(ValidationTarget.PARAMETERS)
    public static final class DateRangeValidator
            implements ConstraintValidator<ValidDateRange, Object[]> {

        @Override
        public boolean isValid(
                Object[] values, ConstraintValidatorContext context) {

            if (values == null || values.length != 2) {
                throw new IllegalArgumentException(
                        "@ValidDateRange yêu cầu đúng 2 tham số");
            }

            // Để @NotNull trên từng tham số phát hiện dữ liệu thiếu.
            if (values[0] == null || values[1] == null) {
                return true;
            }

            if (!(values[0] instanceof LocalDate start)
                    || !(values[1] instanceof LocalDate end)) {
                throw new IllegalArgumentException(
                        "@ValidDateRange yêu cầu 2 LocalDate");
            }

            return !start.isAfter(end);
        }
    }

    public static class BookingService {

        @ValidDateRange
        public void reserve(
                @NotNull LocalDate start,
                @NotNull LocalDate end) {
            // Nghiệp vụ đặt chỗ sẽ được xử lý ở đây.
        }
    }
}
~~~

Chạy từ thư mục dự án Spring Boot đã có Maven wrapper và plugin Boot:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows dùng `mvnw.cmd spring-boot:run`; nếu Maven đã cài dùng `mvn spring-boot:run`.

Ngoài log khởi động, **bốn dòng do `ApplicationRunner` in ra**:

~~~text
valid -> 0
reversed -> 1
missing -> 1
message -> Ngày bắt đầu không được sau ngày kết thúc
~~~

Giải thích kết quả:

1. `valid`: 10/11/2026 đến 12/11/2026, quan hệ hợp lệ; không có vi phạm.
2. `reversed`: ngày bắt đầu sau ngày kết thúc, `DateRangeValidator#isValid` trả `false`; provider tạo **một** `ConstraintViolation` dùng `message` của `@ValidDateRange`.
3. `missing`: tham số đầu tiên null. Cross-parameter validator trả `true` theo chính sách phân chia trách nhiệm, nhưng `@NotNull` trên tham số đầu tiên vẫn tạo **một** vi phạm.
4. `validateParameters(...)` chỉ kiểm tra các constraint trên các đối số; nó **không gọi** `BookingService#reserve(...)`. Vì vậy không có side effect nghiệp vụ ở ví dụ.

**Vì sao kiểm tra signature?** Annotation có thể vô tình được gắn lên method khác có số lượng/kiểu tham số không phù hợp. Validator không nên truy cập thẳng `values[1]` mà không xác minh. Việc ném `IllegalArgumentException` ở đây dành riêng cho **lỗi lập trình/khai báo sai signature**, không dành cho dữ liệu `start > end`. Provider có thể bọc lỗi từ custom validator vào `ValidationException`. Với dữ liệu không đạt quy tắc nghiệp vụ, hãy trả `false`.

**Lưu ý về ngày:** Trong code, `LocalDate.of(2026, 11, 10)` là ngày 10/11/2026. Nếu nghiệp vụ yêu cầu `start < end` nghiêm ngặt, thay `!start.isAfter(end)` bằng `start.isBefore(end)` và cập nhật thông báo/test theo đúng hợp đồng.

## 4. API `ExecutableValidator` và phạm vi thực thi

Đối tượng `jakarta.validation.Validator` cung cấp `forExecutables()`. Interface `jakarta.validation.executable.ExecutableValidator` có bốn cách kiểm tra:

| Phương thức | Dùng để |
| --- | --- |
| `validateParameters(object, method, args, groups...)` | Kiểm tra **toàn bộ ràng buộc trên các tham số method**, gồm ràng buộc riêng và cross-parameter. |
| `validateReturnValue(object, method, returnValue, groups...)` | Kiểm tra constraint trên **giá trị trả về** của method. |
| `validateConstructorParameters(constructor, args, groups...)` | Kiểm tra tham số constructor, gồm cross-parameter. |
| `validateConstructorReturnValue(constructor, createdObject, groups...)` | Kiểm tra constraint trên đối tượng mới tạo từ constructor. |

`groups...` cho phép chọn validation group; nếu bỏ qua, nhóm `Default` được dùng theo quy tắc Jakarta Validation.

Luồng method validation chủ động:

~~~text
Lấy Method bằng reflection
        |
        v
Validator.forExecutables()
        |
        v
validateParameters(service, method, actualArgs)
        |
        +-- @NotNull trên từng tham số
        |
        +-- @ValidDateRange trên toàn bộ Object[]
        |
        v
Set<ConstraintViolation<BookingService>>
        |
        +-- trống: có thể gọi method nghiệp vụ
        |
        +-- có lỗi: trả response/throw exception theo tầng ứng dụng
~~~

Chú ý: `validator.validate(service)` **không** kiểm tra tự động các tham số của những method chưa được gọi; API này kiểm tra constraint trên **bean/object**. Để kiểm tra executable, phải dùng API tương ứng hoặc cơ chế Spring được cấu hình để kích hoạt khi method được gọi.

### Constructor cross-parameter constraint

Một custom annotation có `@Target(CONSTRUCTOR)` và validator `ValidationTarget.PARAMETERS` cũng dùng được với constructor. Ví dụ định nghĩa **minh họa** (giả định `@ValidDateRange` đã có trong chương trình trên):

~~~java
public final class BookingPeriod {
    @ValidDateRange
    public BookingPeriod(LocalDate start, LocalDate end) {
    }
}
~~~

Để kiểm tra **trước khi khởi tạo**, lấy constructor:

~~~java
var constructor = BookingPeriod.class.getConstructor(
        LocalDate.class, LocalDate.class);
var violations = validator.forExecutables()
        .validateConstructorParameters(constructor,
                new Object[] {LocalDate.of(2026, 11, 12),
                              LocalDate.of(2026, 11, 10)});
~~~

Hai đoạn này là snippet minh họa trong project có các import và annotation phù hợp, không phải file Java độc lập. `validateConstructorParameters` không tự thực thi `new BookingPeriod(...)`; ứng dụng hoặc integration layer quyết định có gọi constructor hay không.

## 5. Gắn lỗi vào đúng tham số với `ConstraintValidatorContext`

Mặc định, cross-parameter violation có **đường dẫn đến tập tham số** của method, ví dụ một path chứa node có `ElementKind.CROSS_PARAMETER`. Đây là lỗi quan hệ giữa nhiều argument, không phải lỗi riêng của `start` hay `end`.

Đôi khi UI cần hiển thị lỗi bên cạnh tham số `end`. Có thể tạo custom violation và nối **parameter node ở index 1**. Thay phần cuối `isValid` trong `DateRangeValidator` ở phần 3 bằng đoạn sau (đây là **mảnh code**, không phải source file độc lập):

~~~java
if (!start.isAfter(end)) {
    return true;
}

context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        context.getDefaultConstraintMessageTemplate())
        .addParameterNode(1)
        .addConstraintViolation();
return false;
~~~

Hành vi:

- `disableDefaultConstraintViolation()` tắt vi phạm mặc định ở mức cross-parameter.
- `buildConstraintViolationWithTemplate(...)` thiết lập thông báo cho lỗi mới; `getDefaultConstraintMessageTemplate()` giữ message được cấu hình ở annotation.
- `addParameterNode(1)` định vị vi phạm tại **tham số thứ hai** của executable (`end`) theo chỉ số zero-based.
- `addConstraintViolation()` **bắt buộc** để hoàn tất builder. Nếu tắt default rồi trả `false` mà không thêm ít nhất một custom violation, provider có thể ném exception.
- `ConstraintViolation#getPropertyPath()` sẽ phản ánh parameter node thay vì chỉ cross-parameter node.

**Tên tham số trong path** phụ thuộc `ParameterNameProvider` và metadata biên dịch (ví dụ có `-parameters`) hoặc provider integration. Có thể thấy `arg1` thay vì `end`; khi kiểm thử portable, kiểm tra `ParameterNode#getParameterIndex() == 1` thay vì so khớp cứng chuỗi tên tham số.

Không nên dùng `addPropertyNode("end")` để đại diện cho **một argument của method** khi mục đích là đánh dấu parameter; API phù hợp là `addParameterNode(index)`. `addPropertyNode(...)` dùng cho property path của bean/đối tượng.

## 6. Kết hợp với Spring: kích hoạt method validation

Jakarta Validation **định nghĩa constraint và API**, nhưng không tự xen vào mọi lời gọi Java. Trong Spring có hai hướng phổ biến.

### 6.1. Service bean thông qua proxy của Spring

Với Spring Boot có Bean Validation provider và method validation được kích hoạt, đánh dấu bean bằng `@Validated` để Spring dùng method-validation interceptor/proxy. Ví dụ sau minh họa cách áp dụng annotation từ phần 3:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class BookingService {
    @ValidDateRange
    public void reserve(@NotNull LocalDate start,
                        @NotNull LocalDate end) {
        // Tác vụ nghiệp vụ.
    }
}
~~~

Đây là **snippet cho một class khác**, không thể đồng thời khai báo class có cùng tên với class trong chương trình demo. Nếu viết thành file riêng cần import `@ValidDateRange`/`@NotNull` chính xác theo package. Trong ứng dụng Spring Boot, `MethodValidationPostProcessor` thường được auto-configure khi có Bean Validation. Nếu setup tự cấu hình Spring Framework thuần, hãy đăng ký bean này; khi cần proxy bằng AOP, bảo đảm các dependency hạ tầng Spring AOP phù hợp.

Chú ý:

- Phải **gọi qua Spring bean proxy**; tự tạo `new BookingService()` rồi gọi hoặc tự gọi `this.reserve(...)` từ cùng instance sẽ không đi qua proxy method validation thông thường.
- Chỉ gắn `@Validated` không chứng minh mọi lời gọi đều được intercept: còn phụ thuộc bean lifecycle, proxy, cấu hình và cách gọi.
- Một lỗi parameter method validation qua AOP thường được báo bằng `jakarta.validation.ConstraintViolationException` (trừ khi cấu hình Spring để thích nghi thành `MethodValidationException` hoặc tích hợp khác). Không giả định luôn là một kiểu exception duy nhất.
- Constraints trên method override/interface còn chịu quy tắc method inheritance của Jakarta Validation; tránh thêm parameter constraint ở override trái hợp đồng.

### 6.2. Controller trong Spring MVC

Spring MVC từ **Spring Framework 6.1** có method validation tích hợp cho handler methods. Khi constraint annotation đặt trực tiếp trên tham số/method, method validation có thể được dùng và Spring có thể phát sinh `HandlerMethodValidationException`.

Spring khuyến nghị **bỏ `@Validated` ở class controller** nếu muốn sử dụng cơ chế MVC built-in (thay vì proxy AOP ở controller). Việc một constraint cross-parameter được xử lý và biểu diễn cụ thể còn phụ thuộc signature, cấu hình Bean Validation và phiên bản Spring. Khi thiết kế API, hãy viết integration test theo setup thực tế, bao gồm mapping của lỗi liên tham số sang phản hồi HTTP.

**Phân biệt với `@Valid @RequestBody`:** `@Valid` chủ yếu kích hoạt validation của DTO/body được bind; nếu quan hệ cần kiểm tra là **giữa các field của một DTO**, class-level constraint trên DTO thường rõ ràng hơn cross-parameter constraint. Nếu quan hệ là **giữa nhiều argument độc lập của method**, cross-parameter constraint phù hợp.

## 7. Kiểm thử JUnit 5 cho cross-parameter constraint

Trong dự án Spring Boot của ví dụ, thêm starter test nếu chưa có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo **`src/test/java/com/example/validation/CrossParameterDemoApplicationTest.java`**:

~~~java
package com.example.validation;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotNull;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.lang.reflect.Method;
import java.time.LocalDate;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class CrossParameterDemoApplicationTest {

    @Autowired
    Validator validator;

    private Set<ConstraintViolation<
            CrossParameterDemoApplication.BookingService>> check(
                    LocalDate start, LocalDate end) throws Exception {

        var service =
                new CrossParameterDemoApplication.BookingService();

        Method method = service.getClass().getMethod(
                "reserve", LocalDate.class, LocalDate.class);

        return validator.forExecutables().validateParameters(
                service, method, new Object[] {start, end});
    }

    @Test
    void acceptsChronologicalDates() throws Exception {
        assertTrue(check(
                LocalDate.of(2026, 11, 10),
                LocalDate.of(2026, 11, 12)).isEmpty());
    }

    @Test
    void reportsOneCrossParameterViolation() throws Exception {
        var violations = check(
                LocalDate.of(2026, 11, 12),
                LocalDate.of(2026, 11, 10));

        assertEquals(1, violations.size());
        var violation = violations.iterator().next();

        assertEquals(
                CrossParameterDemoApplication.ValidDateRange.class,
                violation.getConstraintDescriptor()
                        .getAnnotation().annotationType());

        assertEquals("Ngày bắt đầu không được sau ngày kết thúc",
                violation.getMessage());
    }

    @Test
    void letsNotNullReportMissingArgument() throws Exception {
        var violations = check(null, LocalDate.of(2026, 11, 12));

        assertEquals(1, violations.size());
        var annotationType = violations.iterator().next()
                .getConstraintDescriptor().getAnnotation()
                .annotationType();

        assertEquals(NotNull.class, annotationType);
    }

    @Test
    void acceptsEqualDatesAccordingToThisRule() throws Exception {
        assertTrue(check(
                LocalDate.of(2026, 11, 12),
                LocalDate.of(2026, 11, 12)).isEmpty());
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

Trên Windows: `mvnw.cmd test`. Test không cần gọi `BookingService#reserve`, vì mục tiêu là kiểm tra metadata constraint và `ExecutableValidator` trực tiếp. Các assert dùng số lượng và **loại annotation thực tế sinh vi phạm**, đáng tin cậy hơn việc giả định thứ tự của `Set<ConstraintViolation<?>>` hoặc tên node do provider tạo.

Nếu thêm custom violation `addParameterNode(1)` ở phần 5, nên có test bổ sung duyệt `violation.getPropertyPath()` và kiểm tra có `Path.ParameterNode` với `getParameterIndex() == 1`. Tránh assert raw path string vì `ParameterNameProvider` có thể thay đổi tên tham số.

## 8. Trường hợp khó và lỗi phổ biến

### 8.1. Sai số lượng hoặc kiểu tham số

Validator ở phần 3 chỉ hỗ trợ method/constructor có **đúng hai `LocalDate`**. Nếu dán `@ValidDateRange` lên `reserve(String code)`, code sẽ ném `IllegalArgumentException` khi invoked qua provider, thường bị bao bọc trong `ValidationException`. Đây là bug của developer, nên sửa annotation/signature; **không trả `false` để biến lỗi code thành lỗi nhập liệu**.

Chú ý thứ tự đặt hai tham số có ý nghĩa. Nếu đổi signature từ `(start, end)` thành `(end, start)` mà không sửa validator, logic sẽ kiểm tra ngược.

### 8.2. Đặt cross-parameter constraint lên method không có tham số

Jakarta Validation không cho phép cross-parameter constraint trên executable có **0 tham số**; có thể ném `ConstraintDeclarationException` khi provider xử lý metadata/validation. Annotation trên getter `getStatus()` không có argument không phải cách kiểm tra nhiều field của bean; hãy dùng class-level constraint.

### 8.3. Quên `@SupportedValidationTarget` hoặc sai generic type

Cross-parameter validator **phải** khai báo `@SupportedValidationTarget(ValidationTarget.PARAMETERS)`. Nếu dùng `ConstraintValidator<ValidDateRange, LocalDate>`, provider có thể hiểu sai đối tượng được validate hoặc không tìm được validator phù hợp. Cần dùng `Object[]` (hoặc `Object` theo spec) cho tập đối số và import đúng namespace `jakarta.validation.constraintvalidation`.

### 8.4. Null, ngoại lệ và thông báo trùng lặp

Một tham số null không nhất thiết làm quy tắc so sánh thất bại: thường chọn `return true` trong cross-constraint rồi thêm `@NotNull` trên tham số cần thiết. Nếu cả `@NotNull` và cross-constraint đều báo lỗi cho null, client có thể nhận hai message cho cùng nguyên nhân. Quyết định chính sách null rõ ràng và kiểm thử.

Nếu cần tạo message tùy chỉnh, `disableDefaultConstraintViolation()` phải đi kèm ít nhất một builder đã gọi `addConstraintViolation()` khi trả `false`. Không lưu `ConstraintValidatorContext` hoặc các builder trong field; chúng thuộc lần gọi hiện tại. Validator phải an toàn đồng thời vì provider có thể tái sử dụng instance.

### 8.5. Ràng buộc method và vấn đề proxy

Gọi `new BookingService().reserve(...)` sẽ không tự kích hoạt validation. Trong ví dụ phần 3, ta gọi `ExecutableValidator` chủ động; với Spring method validation, phải có một Spring bean được proxy phù hợp và lời gọi đi **qua proxy**. Self-invocation có thể bỏ qua interceptor. Với controller, cách kích hoạt khác giữa các thế hệ Spring nên cần integration test đúng phiên bản đang chạy.

### 8.6. Nhầm lỗi trả về với lỗi tham số

Cross-parameter constraint đọc `Object[]` đầu vào và hoạt động trong `validateParameters(...)`. Constraint trên **giá trị trả về** có validator khác và được kiểm tra bởi `validateReturnValue(...)`. Nếu một annotation hỗ trợ cả hai, phải giải quyết target bằng `validationAppliesTo` khi mơ hồ.

### 8.7. Không giữ đúng hợp đồng kế thừa

Method override không được tự bổ sung parameter constraints làm tăng tiền điều kiện của method cha (theo quy tắc Jakarta Validation). Các cross-parameter constraints cũng là parameter constraints; đặt sai trong quan hệ interface/lớp cha có thể gây `ConstraintDeclarationException`. Hãy khai báo hợp đồng ở tầng API phù hợp và tránh nhân đôi annotation trên override.

## 9. Checklist triển khai

- [ ] Quy tắc thực sự cần so sánh từ hai argument trở lên, thay vì chỉ kiểm tra một giá trị hoặc nhiều field trong DTO.
- [ ] Annotation có `@Target(METHOD/CONSTRUCTOR)`, `@Retention(RUNTIME)`, `@Constraint`, `message`, `groups`, `payload`.
- [ ] Validator khai báo `@SupportedValidationTarget(ValidationTarget.PARAMETERS)` và `ConstraintValidator<..., Object[]>`.
- [ ] Xác định rõ số lượng, vị trí, kiểu của arguments; nếu signature bị dùng sai, báo lỗi lập trình rõ ràng.
- [ ] Trả `true/false` cho nghiệp vụ; quy tắc null thống nhất với `@NotNull` trên tham số.
- [ ] Nếu tạo custom violation cho một tham số, dùng `addParameterNode(index)`, không phụ thuộc tên parameter trong path.
- [ ] Đảm bảo có cơ chế kích hoạt thực tế: `ExecutableValidator` hoặc Spring method validation phù hợp.
- [ ] Test dữ liệu đúng, thứ tự ngược, bằng nhau, null, metadata annotation, group và tích hợp Spring nếu dùng proxy.
- [ ] Kiểm tra method override, trường hợp no-arg, constructor, return-value target và version namespace Jakarta/Spring.

## Tài liệu tham khảo

- Jakarta Validation specification 3.1 — method and constructor constraints, cross-parameter constraints, executable validation: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Hibernate Validator Reference Guide — **Cross-parameter constraints** và `@SupportedValidationTarget`: https://docs.hibernate.org/stable/validator/reference/en-US/html_single/
- Jakarta Validation API — `ExecutableValidator`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/executable/executablevalidator
- Spring Framework Reference — **Method validation**: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC Reference — **Validation** và `HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
