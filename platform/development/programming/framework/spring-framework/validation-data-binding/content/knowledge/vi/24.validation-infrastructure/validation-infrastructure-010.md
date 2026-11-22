# ValidationException, ConstraintDeclarationException và GroupDefinitionException

## 1. Ba exception nói gì về hạ tầng Jakarta Validation?

**Jakarta Bean Validation** kiểm tra dữ liệu bằng các constraint như `@NotNull`, `@NotBlank`, `@Size` và constraint tự viết. Spring Framework/Spring Boot tích hợp cơ chế này để validate DTO, bean, phương thức và dữ liệu được bind từ request.

Điều cần phân biệt đầu tiên:

- **Input không đạt một constraint hợp lệ** là tình huống nghiệp vụ bình thường. Gọi `jakarta.validation.Validator#validate(bean)` trả `Set<ConstraintViolation<T>>` chứa các vi phạm; tập rỗng nghĩa là không phát hiện vi phạm trong các nhóm được kiểm tra.
- **Constraint, group hoặc hạ tầng thực hiện validation bị cấu hình sai/lỗi thực thi** có thể ném `ValidationException` hay các subclass của nó. Đây không phải lỗi field thông thường và cần sửa nguyên nhân ở mã nguồn/cấu hình.

Bài học này tập trung đúng ba lớp:

1. `jakarta.validation.ValidationException`: exception nền cho các sự cố bất thường trong validation.
2. `jakarta.validation.ConstraintDeclarationException`: constraint được **khai báo hoặc áp dụng sai quy tắc** trên element, kiểu dữ liệu hay hợp đồng phương thức.
3. `jakarta.validation.GroupDefinitionException`: **định nghĩa group/sequence** không hợp lệ.

Ví dụ dùng **Java 17+, Spring Boot 3+ và `jakarta.validation.*`**. Spring Boot 2.x thường dùng namespace `javax.validation.*`; không trộn hai hệ thư viện.

### Kết quả sai dữ liệu khác exception hạ tầng

Đoạn minh họa sau giả định đã có biến `validator` kiểu `jakarta.validation.Validator`:

~~~java
class UserForm {
    @jakarta.validation.constraints.NotBlank
    String username = "";
}

var violations = validator.validate(new UserForm());
System.out.println(violations.size()); // 1
~~~

Đây là đoạn code mẫu trong một hàm, không phải file Java độc lập. `@NotBlank` đặt trên `String` là khai báo hợp lệ; khi gặp chuỗi rỗng, provider trả **một `ConstraintViolation`**. Không cần ném `ValidationException`.

## 2. Sơ đồ kế thừa và bảng phân biệt

~~~text
java.lang.RuntimeException
└── jakarta.validation.ValidationException
    ├── ConstraintDeclarationException
    │   └── UnexpectedTypeException
    ├── GroupDefinitionException
    ├── ConstraintDefinitionException
    └── ... các subclass Jakarta Validation khác
~~~

| Exception | Ý nghĩa | Dấu hiệu điển hình | Cách xử lý |
| --- | --- | --- | --- |
| `ValidationException` | Lỗi chung khi hạ tầng/engine hoặc extension validation không thực hiện được yêu cầu. | `isValid` ném runtime exception, provider/factory hỏng, mapping lỗi. | Xem `getCause()`, stack trace và bước đang chạy. |
| `ConstraintDeclarationException` | Cách đặt/ap dụng constraint không hợp lệ. | Subtype thêm constraint vào parameter của override; khai báo group conversion sai. | Kiểm tra vị trí annotation, kiểu dữ liệu, kế thừa method, group conversion. |
| `GroupDefinitionException` | Quy tắc định nghĩa group/sequence sai. | Sequence vòng lặp; default sequence trên class thiếu chính class. | Sửa `@GroupSequence` và thứ tự nhóm. |

Cả hai exception cụ thể đều kế thừa `ValidationException`. Vì vậy `catch (ValidationException ex)` có thể bắt chúng, nhưng loại cụ thể và nguyên nhân gốc quyết định cách sửa.

**Hai loại dễ nhầm thêm:**

- `ConstraintDefinitionException`: **bản thân định nghĩa custom constraint annotation** sai chuẩn (ví dụ thiếu `message`, `groups` hoặc `payload`). Đây là loại khác với lỗi *sử dụng* một constraint vốn hợp lệ.
- `UnexpectedTypeException`: subclass của `ConstraintDeclarationException` khi provider không phân giải được `ConstraintValidator` phù hợp/duy nhất cho annotation và kiểu được validate; ví dụ `@NotBlank Integer id`.
- `ConstraintViolation` là đối tượng biểu diễn lỗi dữ liệu; `ConstraintViolationException` là exception riêng có thể do một tầng tích hợp ném khi mang theo violations. Đừng dùng tên gần giống để suy ra cùng nguyên nhân.
- Tham số không hợp lệ truyền trực tiếp cho API (`validate(null)`, một số đối số null/sai định dạng khác) có thể gây `IllegalArgumentException` theo hợp đồng của phương thức, không bắt buộc là `ValidationException`.

## 3. `ValidationException`: lỗi không thể tiếp tục validation bình thường

`ValidationException` là unchecked exception (con của `RuntimeException`), biểu diễn sự cố bất thường trong Jakarta Validation. Nó cũng là lớp cha của những exception chuyên biệt, vì vậy **đọc chính xác runtime type** trước khi phân tích.

Các nguồn lỗi gồm:

- Không tạo được `ValidatorFactory`, thiếu provider, cấu hình XML hoặc mapping lỗi.
- Lỗi trong `ConstraintValidatorFactory`, `MessageInterpolator`, `ValueExtractor`, `ConstraintValidator` và các extension khác.
- Exception ném từ `ConstraintValidator#initialize` hoặc `ConstraintValidator#isValid`; validation engine bao bọc lỗi runtime từ extension bằng `ValidationException`.
- Khai báo constraint/group không hợp lệ, lúc metadata được xử lý hoặc lúc validation thực thi.

Ví dụ custom validator **cố ý có bug**:

~~~java
@Override
public boolean isValid(String value,
                       ConstraintValidatorContext context) {
    throw new IllegalStateException("Dịch vụ phụ thuộc không sẵn sàng");
}
~~~

Đây chỉ là thân phương thức minh họa trong `ConstraintValidator`. Nếu provider gọi `isValid`, lỗi `IllegalStateException` được bọc thành `ValidationException` (Hibernate Validator thường báo thông tin lỗi thực thi validator trong message). Việc này khác `return false`: nó báo hạ tầng/logic không thể kiểm tra, không tạo kết quả "field không hợp lệ" bình thường.

**Cách viết đúng cho quy tắc dữ liệu không đạt**:

~~~java
@Override
public boolean isValid(String value,
                       ConstraintValidatorContext context) {
    if (value == null) {
        return true; // @NotNull có thể xử lý trường hợp null.
    }
    return value.startsWith("CUS-");
}
~~~

Nếu muốn thông báo riêng, xây violation qua `ConstraintValidatorContext`, sau đó trả `false`. **Không ném `ValidationException` chỉ vì người dùng nhập sai mẫu mã**; exception phù hợp khi có lỗi bất thường mà validation không thể xử lý đúng.

Khi điều tra, in/log `ex.getClass().getName()`, `ex.getCause()` và toàn bộ stack trace ở phía server. Một code của Hibernate Validator dạng `HV000...` giúp định vị vấn đề trong implementation nhưng không phải hợp đồng ổn định để viết nhánh nghiệp vụ dựa vào chuỗi message.

## 4. `ConstraintDeclarationException`: khai báo constraint sai chỗ hoặc sai hợp đồng

`ConstraintDeclarationException` xuất hiện khi **constraint annotation có thể hợp lệ**, nhưng cách sử dụng rơi vào tình huống bị cấm bởi Jakarta Validation. Các nguồn phổ biến:

1. **Method constraints trong quan hệ kế thừa:** subtype thêm parameter constraint vào method override, làm **siết tiền điều kiện** mà caller của kiểu cha không biết.
2. **Group conversion bất hợp lệ:** dùng `@ConvertGroup` ngoài vị trí được phép, chẳng hạn không gắn với cascading validation `@Valid` phù hợp, hoặc khai báo conversion trùng/không hợp lệ.
3. **Cross-parameter constraint đặt sai:** annotation yêu cầu nhiều tham số nhưng sử dụng sai target hoặc thuộc tính `validationAppliesTo`.
4. **Container-element/cascaded validation:** provider không xác định được value extractor thích hợp/duy nhất.
5. **Không có validator phù hợp với kiểu dữ liệu:** thường có subclass cụ thể `UnexpectedTypeException`.

### 4.1. Ví dụ sai khi override method

~~~java
class BaseService {
    public void send(String code) {
    }
}

class StrictService extends BaseService {
    @Override
    public void send(@NotNull String code) {
        // SAI: subtype thêm constraint lên tham số của override.
    }
}
~~~

Đây là snippet cần import `jakarta.validation.constraints.NotNull`, chưa phải chương trình độc lập. Hợp đồng của `BaseService#send` cho phép caller gửi null; lớp con tự thêm `@NotNull` làm tiền điều kiện chặt hơn. Theo quy tắc method validation, provider phải báo `ConstraintDeclarationException` khi phát hiện khai báo này, chẳng hạn lúc truy vấn metadata của `StrictService` hoặc chạy executable validation.

Sửa bằng cách **đặt constraint ở hợp đồng cha** nếu mọi implementation cần ràng buộc đó:

~~~java
class BaseService {
    public void send(@NotNull String code) {
    }
}

class StrictService extends BaseService {
    @Override
    public void send(String code) {
    }
}
~~~

Ràng buộc trên method cha được kế thừa trong method validation. Không cần (và không nên) khai báo lại trên parameter ở override. Việc đặt annotation không tự làm Java kiểm tra tham số khi gọi method: cần `ExecutableValidator` hoặc tích hợp method validation tương ứng của Spring.

### 4.2. `UnexpectedTypeException`: sai kiểu được constraint hỗ trợ

~~~java
class BadField {
    @NotBlank
    Integer id = 42; // @NotBlank áp dụng cho text, không phải Integer.
}
~~~

Khi validate, provider không tìm thấy `ConstraintValidator<NotBlank,Integer>` phù hợp, nên ném `UnexpectedTypeException`, một `ConstraintDeclarationException` chuyên biệt. Sửa bằng `@NotNull`, `@Min(1)`/`@Positive` khi kiểm tra số, hoặc viết custom constraint hỗ trợ đúng kiểu.

**Phân biệt lỗi định nghĩa:** custom constraint thiếu thuộc tính `groups()`, `payload()` hay `message()` là vấn đề `ConstraintDefinitionException`. Trong khi đó annotation `@NotBlank` đúng chuẩn nhưng áp dụng lên Integer là vấn đề phân giải validator/khai báo.

## 5. `GroupDefinitionException`: định nghĩa group sequence sai

Validation groups cho phép nhóm constraint. Khi cần thứ tự, `@GroupSequence` định nghĩa các group chạy lần lượt. Nếu group phía trước có violations, group phía sau không được chạy. Một định nghĩa group bất hợp lệ có thể ném `GroupDefinitionException`.

Hai nguyên nhân điển hình:

- Chu trình trong định nghĩa thứ tự group (qua sequence/quan hệ nhóm).
- Định nghĩa lại nhóm `Default` của class bằng `@GroupSequence` nhưng **không đưa chính class đó vào sequence**.

### 5.1. Default group sequence trên class phải chứa chính class

~~~java
interface ExtraChecks {
}

@GroupSequence({ExtraChecks.class}) // SAI: không có Order.class
class Order {
    @NotNull String code;
}
~~~

`@GroupSequence` đặt **trên class `Order`** là cách định nghĩa lại nhóm `Default` của class. Theo specification, sequence phải chứa `Order.class`. Nếu thiếu, provider ném `GroupDefinitionException` khi validate class hoặc yêu cầu metadata liên quan.

Sửa:

~~~java
interface ExtraChecks {
}

@GroupSequence({Order.class, ExtraChecks.class})
class Order {
    @NotNull String code;
}
~~~

Ở đây constraint thuộc nhóm mặc định của class chạy tại bước `Order.class`, rồi mới đến `ExtraChecks.class` nếu bước trước không sinh violations. Đừng thay `Order.class` bằng `Default.class` khi mục tiêu là **redefine Default trên chính class**.

Ngược lại, khi định nghĩa sequence **trên interface nhóm** để dùng độc lập, cú pháp có thể là:

~~~java
@GroupSequence({Default.class, ExtraChecks.class})
interface OrderedChecks {
}
~~~

Đây là một nhóm trình tự riêng, được gọi ví dụ bằng `validator.validate(order, OrderedChecks.class)`; không áp dụng quy tắc "phải chứa class Order" của default-sequence redefinition.

### 5.2. Sequence vòng lặp

~~~java
@GroupSequence({GroupB.class})
interface GroupA {
}

@GroupSequence({GroupA.class})
interface GroupB {
}
~~~

Khi đánh giá `GroupA`, nhóm A phụ thuộc B, B lại phụ thuộc A, gây `GroupDefinitionException`. Cần thiết kế đồ thị group sequence không tạo phụ thuộc vòng. Đừng đoán thứ tự kiểm tra các constraint không thuộc một sequence được khai báo rõ: specification không bảo đảm mọi group sẽ luôn chạy theo thứ tự mong muốn.

## 6. Demo chạy được: 5 tình huống trong một ứng dụng Spring Boot

Dùng dự án Maven **Spring Boot 3+**, Java 17+, có dependency sau trong `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Tạo file **`src/main/java/com/example/validation/ValidationExceptionDemoApplication.java`**. Toàn bộ source chạy trong một file; những lớp khai báo sai có chủ đích để minh họa exception:

~~~java
package com.example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.GroupSequence;
import jakarta.validation.Payload;
import jakarta.validation.ValidationException;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@SpringBootApplication
public class ValidationExceptionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationExceptionDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner runExamples(Validator validator) {
        return args -> {
            System.out.println("ordinary -> violations="
                    + validator.validate(new UserForm()).size());

            show("declaration", () -> {
                validator.getConstraintsForClass(StrictService.class);
            });

            show("group", () -> {
                validator.validate(new BadDefaultSequence());
            });

            show("type", () -> {
                validator.validate(new WrongConstraintType());
            });

            show("execution", () -> {
                validator.validate(new BrokenData());
            });
        };
    }

    private static void show(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + " -> no exception");
        } catch (ValidationException ex) {
            System.out.println(label + " -> "
                    + ex.getClass().getSimpleName());
        }
    }

    static final class UserForm {
        @NotBlank
        String username = "";
    }

    static class BaseService {
        public void send(String code) {
        }
    }

    static final class StrictService extends BaseService {
        @Override
        public void send(@NotNull String code) {
        }
    }

    interface ExtraChecks {
    }

    @GroupSequence({ExtraChecks.class})
    static final class BadDefaultSequence {
        @NotNull
        String code = "OK";
    }

    static final class WrongConstraintType {
        @NotBlank
        Integer id = 42;
    }

    @Target(ElementType.FIELD)
    @Retention(RetentionPolicy.RUNTIME)
    @Constraint(validatedBy = BrokenValidator.class)
    public @interface BrokenCheck {
        String message() default "Không hợp lệ";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
    }

    public static final class BrokenValidator
            implements ConstraintValidator<BrokenCheck, String> {
        @Override
        public boolean isValid(
                String value, ConstraintValidatorContext context) {
            throw new IllegalStateException("Demo: runtime failure");
        }
    }

    static final class BrokenData {
        @BrokenCheck
        String value = "test";
    }
}
~~~

Chạy trong thư mục gốc dự án đã cấu hình Spring Boot Maven plugin:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows: `mvnw.cmd spring-boot:run`; hoặc `mvn spring-boot:run` nếu đã có Maven. Ngoài log Spring Boot, với **Hibernate Validator mặc định** theo các quy tắc Jakarta Validation, dự kiến có các dòng:

~~~text
ordinary -> violations=1
declaration -> ConstraintDeclarationException
group -> GroupDefinitionException
type -> UnexpectedTypeException
execution -> ValidationException
~~~

Giải thích:

1. `ordinary`: có một dữ liệu không hợp lệ và được báo bằng `ConstraintViolation`.
2. `declaration`: provider phân tích metadata của `StrictService`, phát hiện parameter constraint thêm ở override.
3. `group`: `BadDefaultSequence` đặt `@GroupSequence` trên class nhưng quên chính `BadDefaultSequence.class`.
4. `type`: `@NotBlank` áp dụng lên Integer không phù hợp, gây `UnexpectedTypeException`.
5. `execution`: `BrokenValidator#isValid` ném `IllegalStateException`; provider bọc lỗi từ extension trong `ValidationException`.

`show(...)` bắt `ValidationException` **chỉ để trình diễn** và tiếp tục các trường hợp khác. Không dùng cách bắt rồi bỏ lỗi như vậy trong hệ thống thực. Provider có thể phát hiện một số lỗi khai báo khi lấy metadata hoặc khi validate; message/mã nội bộ có thể khác theo phiên bản/cấu hình.

## 7. Kiểm thử JUnit 5 để xác nhận đúng loại exception

Bổ sung `spring-boot-starter-test` trong `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo **`src/test/java/com/example/validation/ValidationExceptionDemoApplicationTest.java`**:

~~~java
package com.example.validation;

import jakarta.validation.ConstraintDeclarationException;
import jakarta.validation.GroupDefinitionException;
import jakarta.validation.UnexpectedTypeException;
import jakarta.validation.ValidationException;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class ValidationExceptionDemoApplicationTest {

    @Autowired
    Validator validator;

    @Test
    void wrongInputReturnsViolations() {
        assertEquals(1, validator.validate(
                new ValidationExceptionDemoApplication.UserForm()).size());
    }

    @Test
    void wrongOverrideThrowsDeclarationException() {
        assertThrows(ConstraintDeclarationException.class,
                () -> validator.getConstraintsForClass(
                        ValidationExceptionDemoApplication.StrictService.class));
    }

    @Test
    void wrongSequenceThrowsGroupDefinitionException() {
        assertThrows(GroupDefinitionException.class,
                () -> validator.validate(
                        new ValidationExceptionDemoApplication
                                .BadDefaultSequence()));
    }

    @Test
    void wrongTypeThrowsUnexpectedTypeException() {
        assertThrows(UnexpectedTypeException.class,
                () -> validator.validate(
                        new ValidationExceptionDemoApplication
                                .WrongConstraintType()));
    }

    @Test
    void thrownValidatorFailureBecomesValidationException() {
        assertThrows(ValidationException.class,
                () -> validator.validate(
                        new ValidationExceptionDemoApplication.BrokenData()));
    }
}
~~~

Chạy `./mvnw test` (Windows: `mvnw.cmd test`). Những test này xác nhận **kiểu exception và khác biệt với violations**, thay vì phụ thuộc text của message. Chúng cũng chủ động yêu cầu metadata/validation của các class để kích hoạt lỗi: không thể giả định provider buộc phải phát hiện mọi lỗi ngay khi Spring Boot khởi động.

Trong CI có thể viết riêng test metadata cho các DTO/method và group sequence quan trọng nhằm phát hiện cấu hình sai trước khi đưa ứng dụng vào production.

## 8. Spring MVC: khi nào là HTTP 400, khi nào là lỗi server?

Với controller sử dụng `@Valid @RequestBody`:

~~~java
@PostMapping("/register")
ResponseEntity<?> register(@Valid @RequestBody UserRequest input) {
    return ResponseEntity.ok().build();
}
~~~

Đây là **snippet**, giả định đã có controller, DTO `UserRequest` và import Spring MVC/Jakarta phù hợp. Khi input vi phạm một constraint khai báo đúng, Spring MVC thông thường báo lỗi validation ở request. Trường hợp điển hình là `MethodArgumentNotValidException` với phản hồi HTTP 400. Nếu muốn xử lý thủ công, đặt tham số `BindingResult` ngay sau tham số được validate và đọc các field/object errors.

Nhưng khi provider ném `ValidationException` do lỗi code/cấu hình, **không nên mặc định phản hồi 400 như thể người dùng nhập dữ liệu sai**. Cần:

- Ghi đầy đủ exception type, stack trace, cause và constraint/group/method liên quan tại server.
- Trả response lỗi server an toàn theo chính sách của ứng dụng, không công khai class name, stack trace hoặc dữ liệu nội bộ.
- Sửa lỗi ở annotation, validator, group sequence hoặc dependency; không coi exception như tập violations rỗng.
- Kiểm tra cơ chế Spring đang dùng: với method validation có thể gặp `HandlerMethodValidationException` hoặc `ConstraintViolationException` ở tầng tích hợp khác, không đồng nhất với kết quả trực tiếp của `Validator#validate`.

Không viết một global handler bắt mọi `ValidationException` và trả 400: như vậy có thể biến bug server thành lỗi được quy cho client, gây khó theo dõi vận hành.

## 9. Quy trình chẩn đoán và checklist sửa lỗi

Khi gặp một exception trong hạ tầng kiểm tra:

1. **Phân loại runtime type**: đọc `ex.getClass().getName()`; có phải subclass của `ValidationException` không?
2. **Theo cause chain**: nếu là `ValidationException` chung, kiểm tra `getCause()`; thường tìm được extension hoặc dependency gây lỗi.
3. **Xác định thời điểm**: bootstrap provider, đọc metadata (`getConstraintsForClass`), gọi `validate` hay executable validation.
4. **Nếu `ConstraintDeclarationException`**: đối chiếu kiểu dữ liệu với annotation; kiểm tra method override/interface, cross-parameter, `@ConvertGroup` và cascading.
5. **Nếu `GroupDefinitionException`**: kiểm tra `@GroupSequence` có cycle không, và sequence đặt trên class có chứa chính class đó không.
6. **Viết test tái hiện**: một class nhỏ + một lời gọi metadata/validate + `assertThrows` cho lớp exception cụ thể.
7. **Sau sửa**: chạy lại cả test lỗi cấu hình và test dữ liệu hợp lệ/không hợp lệ thông thường; bảo đảm `validate` không bị chuyển thành luồng throw không cần thiết.

| Triệu chứng | Nguyên nhân thường gặp | Hướng sửa |
| --- | --- | --- |
| `UnexpectedTypeException` với `@NotBlank Integer` | Annotation/kiểu dữ liệu không khớp. | `@NotNull` hoặc constraint số phù hợp. |
| `ConstraintDeclarationException` ở method override | Thêm constraint vào parameter của subtype. | Đặt ở hợp đồng cha, không siết tiền điều kiện tại subtype. |
| `GroupDefinitionException` ở `@GroupSequence` trên class | Thiếu chính class đó, hoặc sequence có cycle. | Thêm class, loại bỏ chu trình. |
| `ValidationException` kèm cause từ `isValid` | Validator hoặc dependency ném runtime exception. | Sửa bug/điều kiện hạ tầng; dùng `return false` cho dữ liệu sai thông thường. |
| `ConstraintViolation` trả trong Set | Input không thỏa constraint hợp lệ. | Xử lý và hiển thị lỗi nhập liệu. |

### Sai lầm dễ mắc

- Nghĩ **mọi lỗi validation đều là exception**: input không đạt constraint hợp lệ thường chỉ tạo violations.
- Bắt `ValidationException` rộng rồi nuốt lỗi hoặc trả HTTP 400 cho mọi trường hợp.
- Nhầm **constraint definition** (annotation tự định nghĩa sai) với **constraint declaration** (annotation được dùng sai).
- Đặt `@GroupSequence({Default.class, Extra.class})` lên class để thay Default; class-level sequence phải có chính class đó.
- Cố đoán lỗi từ một thông báo `HV000...` thay vì xem exception class và root cause.
- Chỉ test dữ liệu tốt/xấu mà không kiểm tra metadata, sequence và exception ở custom validator.
- Trộn `javax.validation.*` cũ với `jakarta.validation.*` mới trong Spring Boot 3+.

## Tài liệu tham khảo

- Jakarta Validation 3.1 specification — **Exception model**: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation API 3.1.1 — các exception trong package `jakarta.validation`: https://javadoc.io/static/jakarta.validation/jakarta.validation-api/3.1.1/jakarta/validation/package-summary.html
- Hibernate Validator 8 Reference Guide — method constraints, groups và custom constraints: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC — request-body validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
