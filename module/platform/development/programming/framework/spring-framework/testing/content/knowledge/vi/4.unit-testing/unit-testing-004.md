# Kiểm thử quy tắc validation và chuyển đổi dữ liệu thuần

Validation và chuyển đổi dữ liệu là hai nhóm quy tắc xuất hiện ở nhiều lớp của ứng dụng Spring. Validation xác định dữ liệu có đáp ứng điều kiện nghiệp vụ hoặc cấu trúc hay không; chuyển đổi dữ liệu biến một biểu diễn thành kiểu dữ liệu mà phần còn lại của ứng dụng có thể sử dụng. Những quy tắc này thường có thể kiểm thử trực tiếp bằng unit test mà không cần khởi động Spring ApplicationContext.

Ví dụ, một form đăng ký có thể yêu cầu email không được để trống, mật khẩu đạt độ dài tối thiểu và ngày sinh không nằm trong tương lai. Một converter có thể chuyển chuỗi trạng thái `" pending "` thành enum `PENDING`, hoặc một formatter chuyển chuỗi ngày theo định dạng của người dùng thành `LocalDate`. Ta có thể kiểm tra các quy tắc đó bằng dữ liệu đầu vào, kết quả hoặc lỗi cụ thể, sau đó kiểm tra riêng việc Spring đăng ký và sử dụng chúng ở tầng tích hợp khi cần.

## 1. Phân biệt validation và chuyển đổi dữ liệu

Hai hoạt động thường xuất hiện liên tiếp trong một luồng xử lý nhưng có mục đích khác nhau.

| Hoạt động | Câu hỏi cần trả lời | Ví dụ | Kết quả thường gặp |
|---|---|---|---|
| Validation | Dữ liệu hiện có có hợp lệ theo quy tắc không? | Email có đúng định dạng? Số lượng có lớn hơn 0? | Hợp lệ, danh sách lỗi hoặc `ConstraintViolation` |
| Conversion | Biểu diễn nguồn tương ứng với giá trị đích nào? | Chuỗi `"42"` thành `Integer`; `"2026-11-12"` thành `LocalDate` | Giá trị đích hoặc lỗi chuyển đổi |
| Formatting | Giá trị được biểu diễn thành văn bản thế nào trong locale cụ thể? | `LocalDate` thành `12/11/2026` | Chuỗi hoặc lỗi parse |

Conversion không tự động có nghĩa là validation đã hoàn tất. Chuyển chuỗi `"0"` thành số nguyên `0` có thể thành công về mặt kiểu dữ liệu, nhưng quy tắc nghiệp vụ có thể yêu cầu số lượng phải lớn hơn 0. Ngược lại, một chuỗi ngày có thể đúng định dạng nhưng đại diện cho ngày không được phép trong nghiệp vụ.

Một luồng HTTP điển hình có thể gồm:

```text
Request dạng văn bản / JSON
          |
          v
Chuyển đổi sang kiểu dữ liệu Java
          |
          v
Validation cấu trúc và quy tắc nghiệp vụ
          |
          v
Gọi service khi dữ liệu hợp lệ
```

Tùy loại endpoint và cơ chế binding, thứ tự chi tiết có thể khác nhau. Điểm quan trọng khi thiết kế unit test là xác định đang kiểm tra quy tắc nào: converter, formatter, validator hay toàn bộ quá trình binding của web layer.

## 2. Xác định hợp đồng cần kiểm thử

Trước khi viết test, hãy mô tả rõ dữ liệu đầu vào, kết quả hợp lệ và hành vi khi dữ liệu không hợp lệ.

Với validation, cần xác định:

- Đối tượng và trường dữ liệu được kiểm tra.
- Điều kiện hợp lệ, ví dụ bắt buộc, độ dài, khoảng giá trị hoặc quan hệ giữa nhiều trường.
- Cách xử lý `null`, chuỗi rỗng và chuỗi chỉ có khoảng trắng.
- Mã lỗi, đường dẫn thuộc tính hoặc nhóm constraint cần được trả về.
- Có nhiều lỗi đồng thời hay chỉ báo lỗi đầu tiên.
- Validation có phụ thuộc trạng thái bên ngoài hay chỉ dựa trên dữ liệu của đối tượng.

Với conversion và formatting, cần xác định:

- Kiểu nguồn và kiểu đích.
- Quy tắc chuẩn hóa như trim, chữ hoa/chữ thường hoặc đơn vị đo.
- Giá trị biên và độ chính xác.
- Hành vi với `null`, chuỗi rỗng và khoảng trắng.
- Cách xử lý đầu vào không thể chuyển đổi.
- Locale, múi giờ hoặc định dạng nào ảnh hưởng đến kết quả.
- Có yêu cầu round-trip hay không: parse rồi print có phải khôi phục cùng biểu diễn hoặc cùng giá trị không.

Một test case có thể được ghi theo mẫu:

| Trường | Nội dung ví dụ |
|---|---|
| Quy tắc | Số lượng đặt hàng phải lớn hơn 0 |
| Đầu vào | `0` |
| Điều kiện khác | Không cần trạng thái bên ngoài |
| Kết quả mong đợi | Có lỗi tại trường `quantity` |
| Tác động phụ | Không gọi repository hoặc service lưu dữ liệu |

Với converter:

| Trường | Nội dung ví dụ |
|---|---|
| Quy tắc | Chuỗi trạng thái được chuẩn hóa rồi ánh xạ thành enum |
| Đầu vào | `" pending "` |
| Kiểu đích | `OrderStatus` |
| Kết quả mong đợi | `OrderStatus.PENDING` |
| Đầu vào lỗi | `"unknown"` |
| Kết quả lỗi | `IllegalArgumentException` theo hợp đồng converter |

Khi hợp đồng rõ ràng, test sẽ tập trung vào hành vi cần bảo vệ thay vì chỉ kiểm tra rằng một phương thức đã được gọi.

## 3. Kiểm thử Spring Validator thuần

Spring Framework cung cấp giao diện `org.springframework.validation.Validator` cho các validator tự viết. Giao diện này có hai phương thức chính:

- `supports(Class<?> clazz)`: cho biết validator có hỗ trợ kiểu đối tượng được yêu cầu hay không.
- `validate(Object target, Errors errors)`: kiểm tra đối tượng và ghi nhận lỗi vào `Errors` nếu có.

Có thể kiểm thử validator bằng `BeanPropertyBindingResult` mà không cần Spring context. Test tạo đối tượng đầu vào, tạo vùng chứa lỗi, gọi `validate` rồi kiểm tra lỗi theo field hoặc object.

### 3.1. Ví dụ validator kiểm tra form đăng ký

Giả sử form có email và mật khẩu:

```java
public class RegistrationForm {

    private String email;
    private String password;

    public RegistrationForm(String email, String password) {
        this.email = email;
        this.password = password;
    }

    public String getEmail() {
        return email;
    }

    public String getPassword() {
        return password;
    }
}
```

Validator áp dụng quy tắc cụ thể:

```java
import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

@Component
public class RegistrationFormValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return RegistrationForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        RegistrationForm form = (RegistrationForm) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "email", "email.required");

        if (!errors.hasFieldErrors("email")
                && !form.getEmail().matches("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")) {
            errors.rejectValue("email", "email.invalid");
        }

        String password = form.getPassword();
        if (password == null || password.length() < 12) {
            errors.rejectValue("password", "password.tooShort");
        }
    }
}
```

Regex trong ví dụ chỉ là quy tắc minh họa cho một validator đơn giản, không phải bộ kiểm tra email đầy đủ theo mọi tiêu chuẩn. Ứng dụng thực tế nên chọn chính sách email phù hợp với nghiệp vụ và quy trình xác minh địa chỉ.

### 3.2. Kiểm tra validator bằng JUnit Jupiter

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;

import static org.junit.jupiter.api.Assertions.*;

class RegistrationFormValidatorTest {

    private RegistrationFormValidator validator;

    @BeforeEach
    void setUp() {
        validator = new RegistrationFormValidator();
    }

    @Test
    void supportsRegistrationForm() {
        assertTrue(validator.supports(RegistrationForm.class));
    }

    @Test
    void rejectsBlankEmailAndShortPassword() {
        var form = new RegistrationForm("   ", "short");
        Errors errors = new BeanPropertyBindingResult(form, "registrationForm");

        validator.validate(form, errors);

        assertTrue(errors.hasFieldErrors("email"));
        assertEquals("email.required", errors.getFieldError("email").getCode());
        assertTrue(errors.hasFieldErrors("password"));
        assertEquals("password.tooShort", errors.getFieldError("password").getCode());
    }

    @Test
    void acceptsValidForm() {
        var form = new RegistrationForm("user@example.com", "long-password-123");
        Errors errors = new BeanPropertyBindingResult(form, "registrationForm");

        validator.validate(form, errors);

        assertFalse(errors.hasErrors());
    }
}
```

`BeanPropertyBindingResult` là implementation phù hợp để kiểm tra lỗi gắn với thuộc tính JavaBean. Test kiểm tra mã lỗi ổn định do validator phát ra; nội dung thông báo hiển thị cho người dùng thường được resolve qua `MessageSource` ở tầng cấu hình hoặc web, nên không cần khóa unit test validator vào một câu thông báo đã dịch.

### 3.3. Phân vùng đầu vào của validator

Một validator thường cần nhiều nhóm dữ liệu hơn hai ví dụ trên. Với email, có thể lập ma trận:

| Nhóm | Dữ liệu đại diện | Kết quả mong đợi |
|---|---|---|
| `null` | `null` | Lỗi bắt buộc |
| Rỗng | `""` | Lỗi bắt buộc |
| Chỉ khoảng trắng | `"   "` | Lỗi bắt buộc |
| Thiếu phần local | `"@example.com"` | Lỗi định dạng |
| Thiếu domain | `"user@"` | Lỗi định dạng |
| Hợp lệ theo quy tắc đã chọn | `"user@example.com"` | Không có lỗi |

Với mật khẩu có độ dài tối thiểu 12 ký tự, nên kiểm tra 11, 12 và 13 ký tự để phát hiện lỗi biên. Cũng cần xác định rõ khoảng trắng đầu/cuối có được tính vào độ dài hay phải chuẩn hóa trước khi kiểm tra. Quyết định đó thuộc hợp đồng nghiệp vụ và phải được thể hiện trong test.

Có thể dùng `@ParameterizedTest` để kiểm tra nhiều đầu vào cùng một quy tắc:

```java
@ParameterizedTest
@NullAndEmptySource
@ValueSource(strings = {" ", "   ", "\t"})
void rejectsMissingEmail(String email) {
    var form = new RegistrationForm(email, "long-password-123");
    Errors errors = new BeanPropertyBindingResult(form, "registrationForm");

    validator.validate(form, errors);

    assertEquals("email.required", errors.getFieldError("email").getCode());
}
```

`@NullAndEmptySource` và `@ValueSource` là các nguồn tham số của JUnit Jupiter. Nếu dự án dùng dependency `junit-jupiter` tổng hợp, module tham số thường đã được đưa vào cấu hình test.

### 3.4. Kiểm tra lỗi cấp đối tượng và quan hệ giữa nhiều trường

Một số quy tắc không thuộc riêng một field. Ví dụ, ngày kết thúc phải sau ngày bắt đầu, hoặc ít nhất một trong hai phương thức liên hệ phải được cung cấp. Với những quy tắc này, validator có thể gọi `errors.reject(...)` để ghi object error thay vì `rejectValue(...)`.

```java
if (form.getStartDate() != null
        && form.getEndDate() != null
        && !form.getEndDate().isAfter(form.getStartDate())) {
    errors.reject("dateRange.invalid");
}
```

Test cần kiểm tra `errors.hasGlobalErrors()` và mã lỗi tương ứng. Nếu quy tắc gắn với một field cụ thể theo hợp đồng giao diện, hãy dùng `rejectValue` để lỗi có đường dẫn phù hợp.

Với lỗi lồng nhau, có thể kiểm tra field path như `address.postalCode`. Cần dựng đúng đối tượng lồng nhau và xác nhận validator trả về đường dẫn mà binding layer mong đợi.

## 4. Kiểm thử Jakarta Bean Validation

Ngoài giao diện `org.springframework.validation.Validator`, Spring có thể tích hợp với Jakarta Bean Validation (trước đây là Bean Validation API) thông qua provider tương ứng. Các constraint như `@NotBlank`, `@Email`, `@Size`, `@Min`, `@Max` và `@NotNull` được đặt trên field, getter, tham số hoặc kiểu đối tượng.

Khi chỉ kiểm tra constraint, có thể dùng `jakarta.validation.Validator` trực tiếp. Việc này kiểm tra quy tắc Bean Validation mà không cần khởi động toàn bộ Spring ApplicationContext.

### 4.1. Đối tượng có constraint

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class CreateAccountRequest {

    @NotBlank
    @Email
    private String email;

    @NotBlank
    @Size(min = 12, max = 72)
    private String password;

    public CreateAccountRequest(String email, String password) {
        this.email = email;
        this.password = password;
    }

    public String getEmail() {
        return email;
    }

    public String getPassword() {
        return password;
    }
}
```

Giới hạn `max = 72` ở đây chỉ nhằm minh họa một hợp đồng cụ thể; giới hạn thực tế phải phù hợp với thuật toán lưu mật khẩu và yêu cầu của ứng dụng. Không nên sao chép giới hạn ví dụ mà chưa kiểm tra chính sách bảo mật.

### 4.2. Tạo Validator và kiểm tra ConstraintViolation

```java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;
import java.util.Set;
import java.util.stream.Collectors;

class CreateAccountRequestValidationTest {

    @Test
    void reportsEmailAndPasswordViolations() {
        try (ValidatorFactory factory = Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            var request = new CreateAccountRequest(" ", "short");

            var violations = validator.validate(request);
            Set<String> invalidProperties = violations.stream()
                    .map(violation -> violation.getPropertyPath().toString())
                    .collect(Collectors.toSet());

            assertTrue(invalidProperties.contains("email"));
            assertTrue(invalidProperties.contains("password"));
        }
    }

    @Test
    void acceptsRequestWithValidValues() {
        try (ValidatorFactory factory = Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            var request = new CreateAccountRequest(
                    "user@example.com", "a-long-valid-password");

            assertTrue(validator.validate(request).isEmpty());
        }
    }
}
```

Ví dụ giả định một Bean Validation provider đã có trên test runtime classpath. `Validation.buildDefaultValidatorFactory()` tìm provider theo cơ chế của Jakarta Validation; nếu chỉ có API mà không có provider, test không thể tạo validator. `ValidatorFactory` nên được đóng sau khi dùng, vì vậy ví dụ sử dụng try-with-resources.

Khi kiểm tra constraint, thường nên ưu tiên property path, annotation/constraint descriptor hoặc mã lỗi do ứng dụng định nghĩa. Nội dung message có thể phụ thuộc locale và bundle dịch. Chỉ kiểm tra chuỗi thông báo chính xác khi nội dung đó là một phần hợp đồng cần bảo vệ.

### 4.3. Kiểm thử custom constraint

Khi có constraint riêng, cần kiểm tra cả annotation và `ConstraintValidator` tương ứng. Ví dụ, `@ValidPhoneNumber` có thể dùng `PhoneNumberValidator` để kiểm tra định dạng theo chính sách của hệ thống.

Các nhóm trường hợp nên gồm:

- Giá trị hợp lệ điển hình.
- `null` nếu hợp đồng cho phép hoặc từ chối `null`.
- Chuỗi rỗng và khoảng trắng.
- Độ dài ngắn nhất, dài nhất và ngay ngoài giới hạn.
- Ký tự không được hỗ trợ.
- Giá trị có dạng đúng nhưng không đáp ứng quy tắc nghiệp vụ.

Với custom constraint, hãy xác định rõ `@Constraint(validatedBy = ...)`, kiểu dữ liệu mục tiêu và cách xử lý `null`. Trong Bean Validation, validator thường để `null` được coi là hợp lệ để constraint khác như `@NotNull` chịu trách nhiệm bắt buộc trường; tuy nhiên, nếu custom constraint có hợp đồng khác thì cần ghi rõ và test theo hợp đồng đó.

### 4.4. Groups, nested object và class-level constraint

Bean Validation hỗ trợ validation groups để áp dụng tập constraint khác nhau theo ngữ cảnh, chẳng hạn tạo mới và cập nhật. Khi test groups, hãy gọi `validator.validate(object, Create.class)` hoặc group tương ứng rồi xác minh constraint nào được áp dụng. Nếu có group sequence, cần kiểm tra thứ tự và quy tắc dừng khi group trước có lỗi.

Với thuộc tính lồng nhau, `@Valid` yêu cầu validator tiếp tục kiểm tra object con. Test cần dựng object cha và object con, sau đó xác nhận property path có đầy đủ đường dẫn, ví dụ `address.postalCode`.

Với class-level constraint, kết quả thường là violation trên cấp đối tượng hoặc một property node do validator cấu hình. Hãy kiểm tra đúng đường dẫn theo hợp đồng mà API hoặc form cần hiển thị.

### 4.5. Khi nào cần LocalValidatorFactoryBean hoặc Spring context?

`LocalValidatorFactoryBean` là adapter của Spring cho Jakarta Bean Validation và Spring `Validator`. Nếu mục tiêu chỉ là kiểm tra constraint và provider, dùng validator từ `Validation.buildDefaultValidatorFactory()` là đủ. Nếu cần xác minh Spring cấu hình validator, tích hợp `MessageSource`, inject validator vào bean hoặc áp dụng cấu hình provider do Spring quản lý, hãy kiểm tra `LocalValidatorFactoryBean` trong test Spring phù hợp.

Tương tự, method validation dựa trên `@Validated` thường cần Spring AOP proxy và cấu hình method validation. Một unit test gọi trực tiếp đối tượng Java không đi qua proxy sẽ không chứng minh được interceptor đã áp dụng constraint lên method. Trường hợp đó cần integration test có Spring context hoặc test proxy được cấu hình rõ ràng.

## 5. Kiểm thử Converter của Spring

Spring Core cung cấp giao diện `org.springframework.core.convert.converter.Converter<S, T>` để chuyển một giá trị kiểu nguồn `S` thành kiểu đích `T`.

```java
@FunctionalInterface
public interface Converter<S, T> {
    T convert(S source);
}
```

Converter thường là thành phần thuần Java: nhận một giá trị và trả về giá trị tương ứng. Nếu converter không cần dependency ngoài, có thể khởi tạo trực tiếp trong test và kiểm tra kết quả.

### 5.1. Ví dụ chuyển chuỗi thành enum

```java
import org.springframework.core.convert.converter.Converter;

import java.util.Locale;

public class StringToOrderStatusConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Order status is required");
        }

        try {
            return OrderStatus.valueOf(source.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(
                    "Unsupported order status: " + source, exception);
        }
    }
}
```

Enum giả định:

```java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    CANCELLED
}
```

Test trực tiếp:

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class StringToOrderStatusConverterTest {

    private final StringToOrderStatusConverter converter =
            new StringToOrderStatusConverter();

    @Test
    void trimsAndNormalizesInput() {
        assertEquals(OrderStatus.PENDING, converter.convert(" pending "));
        assertEquals(OrderStatus.CONFIRMED, converter.convert("CONFIRMED"));
    }

    @Test
    void rejectsBlankInput() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("   "));
    }

    @Test
    void rejectsUnknownValue() {
        assertThrows(IllegalArgumentException.class,
                () -> converter.convert("ARCHIVED"));
    }
}
```

Ví dụ này cố ý định nghĩa converter từ chối `null` và chuỗi trống. Trong một luồng sử dụng `ConversionService`, framework có thể xử lý `null` trước khi gọi converter; vì vậy test trực tiếp converter và test thông qua service có thể có hành vi quan sát khác nhau với `null`. Hãy xác định hợp đồng ở đúng ranh giới đang kiểm thử.

### 5.2. Kiểm tra Converter qua ConversionService

Khi cần xác minh converter đã đăng ký và được `ConversionService` chọn đúng, hãy dùng implementation nhẹ như `DefaultConversionService`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.core.convert.support.DefaultConversionService;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderStatusConversionServiceTest {

    @Test
    void convertsStringWhenCustomConverterIsRegistered() {
        var conversionService = new DefaultConversionService();
        conversionService.addConverter(new StringToOrderStatusConverter());

        OrderStatus result = conversionService.convert(
                " pending ", OrderStatus.class);

        assertEquals(OrderStatus.PENDING, result);
    }
}
```

Test này vẫn không cần ApplicationContext. Nó kiểm tra thêm bước đăng ký converter vào registry và chuyển đổi thông qua API mà các thành phần Spring có thể sử dụng.

Nên tách hai mục tiêu thành hai test khi cần chẩn đoán rõ ràng:

- Test converter trực tiếp bảo vệ thuật toán chuyển đổi.
- Test `ConversionService` bảo vệ việc đăng ký và lựa chọn converter.

Nếu converter đúng nhưng test service thất bại, hãy xem registry có chứa converter hay không, cặp kiểu nguồn/đích có khớp hay không và có converter khác cạnh tranh hay không.

### 5.3. ConverterFactory và GenericConverter

`ConverterFactory<S, R>` phù hợp khi một kiểu nguồn có thể chuyển thành nhiều kiểu đích thuộc cùng một họ. Ví dụ, chuyển chuỗi thành các enum khác nhau có thể dùng một factory tổng quát. Test cần kiểm tra nhiều kiểu đích, không chỉ một enum cụ thể.

`GenericConverter` phù hợp khi cần khai báo nhiều cặp kiểu nguồn/đích hoặc cần thông tin `TypeDescriptor`, chẳng hạn metadata về collection hoặc annotation. Khi kiểm thử, cần xác nhận:

- `getConvertibleTypes()` khai báo đúng cặp kiểu.
- Converter được chọn cho đúng cặp nguồn/đích.
- Kiểu generic hoặc metadata cần thiết được giữ đúng.
- Trường hợp không hỗ trợ không bị chuyển nhầm sang converter khác.

Không nên dùng `GenericConverter` nếu một `Converter<S, T>` đơn giản đã diễn đạt đầy đủ quy tắc. API càng tổng quát thì test càng cần mô tả rõ cặp kiểu và metadata mà nó phụ thuộc.

## 6. Kiểm thử Formatter và quy tắc locale

`Formatter<T>` của Spring kết hợp hai chiều: parse chuỗi thành đối tượng và print đối tượng thành chuỗi. Formatter thường phụ thuộc locale, nên cùng một giá trị có thể có cách hiển thị khác nhau theo ngôn ngữ hoặc vùng.

Giao diện có hai phương thức chính:

```java
public interface Formatter<T> extends Printer<T>, Parser<T> {
    // print(T object, Locale locale)
    // parse(String text, Locale locale) throws ParseException
}
```

### 6.1. Ví dụ formatter cho ngày

```java
import org.springframework.format.Formatter;

import java.text.ParseException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;

public class LocalDateFormatter implements Formatter<LocalDate> {

    @Override
    public LocalDate parse(String text, Locale locale) throws ParseException {
        DateTimeFormatter formatter = DateTimeFormatter
                .ofPattern("dd/MM/uuuu", locale);
        try {
            return LocalDate.parse(text, formatter);
        } catch (DateTimeParseException exception) {
            ParseException parseException = new ParseException(
                    "Invalid date: " + text, exception.getErrorIndex());
            parseException.initCause(exception);
            throw parseException;
        }
    }

    @Override
    public String print(LocalDate object, Locale locale) {
        return DateTimeFormatter.ofPattern("dd/MM/uuuu", locale).format(object);
    }
}
```

Ở ví dụ này, pattern được giữ cố định để minh họa cách truyền locale cho formatter. Với định dạng ngày phụ thuộc quy ước từng vùng, có thể dùng `DateTimeFormatter.ofLocalizedDate(...)` và `FormatStyle` phù hợp. Cần chọn một chính sách thống nhất giữa đầu vào và đầu ra.

### 6.2. Test parse và print

```java
import org.junit.jupiter.api.Test;

import java.text.ParseException;
import java.time.LocalDate;
import java.util.Locale;

import static org.junit.jupiter.api.Assertions.*;

class LocalDateFormatterTest {

    private final LocalDateFormatter formatter = new LocalDateFormatter();

    @Test
    void parsesDateUsingExpectedPattern() throws ParseException {
        LocalDate result = formatter.parse("12/11/2026", Locale.forLanguageTag("vi-VN"));

        assertEquals(LocalDate.of(2026, 11, 12), result);
    }

    @Test
    void printsDateUsingExpectedPattern() {
        String result = formatter.print(
                LocalDate.of(2026, 11, 12), Locale.forLanguageTag("vi-VN"));

        assertEquals("12/11/2026", result);
    }

    @Test
    void rejectsImpossibleDate() {
        assertThrows(ParseException.class,
                () -> formatter.parse("31/02/2026", Locale.ROOT));
    }
}
```

Các test trên kiểm tra trực tiếp hợp đồng của formatter và không phụ thuộc locale mặc định của máy. Không nên gọi `Locale.getDefault()` trong test nếu mục tiêu là một locale xác định, vì kết quả có thể khác giữa máy cá nhân và CI.

### 6.3. Locale và trạng thái toàn cục

Khi test formatter thông qua Spring `FormattingConversionService`, một số formatter được gọi với locale lấy từ `LocaleContextHolder`. Đây là trạng thái theo thread và có thể ảnh hưởng đến test nếu không được khôi phục.

Nếu test cần đặt locale tạm thời:

```java
import org.springframework.context.i18n.LocaleContext;
import org.springframework.context.i18n.LocaleContextHolder;

import java.util.Locale;

LocaleContext previous = LocaleContextHolder.getLocaleContext();
try {
    LocaleContextHolder.setLocale(Locale.forLanguageTag("vi-VN"));
    // thực hiện conversion/formatting cần locale
} finally {
    LocaleContextHolder.setLocaleContext(previous);
}
```

Nếu test không cần locale context của Spring, gọi trực tiếp `parse(text, locale)` và `print(value, locale)` sẽ đơn giản và ít trạng thái hơn.

## 7. Kiểm thử các trường hợp biên của chuyển đổi dữ liệu

Một converter có thể chạy đúng với dữ liệu thông thường nhưng sai ở khoảng trắng, giá trị lớn, độ chính xác hoặc ký tự đặc biệt. Nên lập nhóm trường hợp dựa trên kiểu dữ liệu và quy tắc thực tế.

### 7.1. Chuỗi và enum

- Chuỗi rỗng, chỉ có khoảng trắng, `null`.
- Chữ hoa/chữ thường và khoảng trắng đầu/cuối.
- Giá trị hợp lệ, giá trị không được hỗ trợ và ký tự Unicode nếu được phép.
- Alias hoặc tên cũ nếu hệ thống hỗ trợ tương thích dữ liệu.

### 7.2. Số và tiền tệ

- Số nguyên âm, 0, dương và giới hạn kiểu dữ liệu.
- Số thập phân có nhiều chữ số hơn scale được cho phép.
- Dấu thập phân và dấu phân nhóm theo locale.
- Quy tắc làm tròn hoặc từ chối phần thập phân dư.
- Đơn vị tiền tệ, số chữ số thập phân và chuyển đổi đơn vị.

Với tiền tệ, nên dùng `BigDecimal` thay vì `double` để tránh sai số nhị phân. Test nên so sánh bằng `compareTo` khi hợp đồng chỉ quan tâm giá trị số và không yêu cầu scale cụ thể; nếu scale là một phần hợp đồng, hãy kiểm tra cả `scale()` hoặc biểu diễn đã chuẩn hóa.

```java
BigDecimal expected = new BigDecimal("1234.50");
BigDecimal actual = converter.convert("1234.50");

assertEquals(0, expected.compareTo(actual));
```

Nếu quy tắc yêu cầu giữ scale hai chữ số, cần assertion bổ sung cho scale hoặc biểu diễn tương ứng. Không nên dùng `new BigDecimal(0.1)` trong test tiền tệ; dùng chuỗi thập phân để tạo giá trị xác định.

### 7.3. Ngày, giờ và múi giờ

- Ngày hợp lệ và ngày không tồn tại, ví dụ 31 tháng 2.
- Năm nhuận và ngày 29 tháng 2.
- Đầu/cuối tháng, đầu/cuối năm.
- Thời điểm có offset hoặc zone khác nhau.
- Khoảng thời gian chuyển giờ mùa hè (DST) nếu ứng dụng dùng múi giờ có DST.
- Locale và pattern được hỗ trợ.

`LocalDate` biểu diễn ngày lịch không có múi giờ; `LocalDateTime` biểu diễn ngày giờ không gắn múi giờ; `Instant` là một thời điểm trên timeline; `ZonedDateTime` và `OffsetDateTime` mang thông tin zone hoặc offset. Không nên chuyển đổi giữa các kiểu này mà bỏ qua ngữ nghĩa múi giờ. Test cần cố định zone và instant nếu kết quả phụ thuộc thời gian.

### 7.4. Collection và kiểu generic

Khi chuyển đổi danh sách hoặc tập hợp, cần xác định:

- Có giữ thứ tự phần tử không?
- Có loại bỏ phần tử trùng lặp không?
- Một phần tử không hợp lệ làm hỏng cả collection hay được bỏ qua?
- Collection rỗng và `null` có ý nghĩa khác nhau không?
- Kiểu phần tử đích có được xác định đầy đủ không?

Đặc biệt với `GenericConverter`, `TypeDescriptor` có thể mang thông tin generic mà `Class<?>` đơn lẻ không biểu diễn đủ. Test cần dùng đúng descriptor nếu hành vi converter phụ thuộc kiểu phần tử hoặc metadata.

## 8. Kiểm thử chuyển đổi và validation như các bước độc lập

Một quy tắc chuyển đổi thành công chưa chứng minh dữ liệu hợp lệ. Ví dụ chuỗi `"-5"` chuyển thành số nguyên thành công nhưng số lượng sản phẩm âm có thể bị từ chối. Ngược lại, một giá trị có thể hợp lệ về nghiệp vụ nhưng không thể parse do định dạng sai.

Nên tách test theo trách nhiệm:

1. **Converter/Formatter test:** xác minh biểu diễn nguồn được chuyển thành giá trị đích hoặc lỗi parse đúng hợp đồng.
2. **Validator test:** xác minh giá trị Java sau chuyển đổi có thỏa điều kiện nghiệp vụ hay không.
3. **Binding/integration test:** xác minh Spring kết hợp conversion và validation trong một luồng request khi đó là hành vi cần bảo vệ.

Ví dụ, với `quantity`:

| Chuỗi đầu vào | Conversion sang `Integer` | Validation `quantity > 0` |
|---|---|---|
| `"5"` | Thành công, giá trị 5 | Hợp lệ |
| `"0"` | Thành công, giá trị 0 | Không hợp lệ |
| `"-2"` | Thành công, giá trị -2 | Không hợp lệ |
| `"abc"` | Lỗi conversion | Chưa có giá trị Integer để validate |
| `""` | Phụ thuộc quy tắc binding/converter | Cần xác định null/rỗng được xử lý thế nào |

Việc phân chia này giúp xác định lỗi nằm ở bước nào và tránh viết một test quá lớn chỉ cho biết request cuối cùng thất bại.

## 9. Kiểm tra đăng ký converter và validator trong Spring

Unit test trực tiếp chứng minh quy tắc của lớp. Tuy nhiên, một converter hoặc validator đúng vẫn có thể không được Spring sử dụng nếu cấu hình đăng ký bị thiếu hoặc không áp dụng cho đúng phạm vi.

### 9.1. Đăng ký converter trong ConversionService

Spring cho phép đăng ký converter với `ConversionService` hoặc thông qua `ConverterRegistry`. Trong ứng dụng, việc đăng ký có thể đến từ cấu hình Java, `WebMvcConfigurer#addFormatters`, hoặc cấu hình auto-configuration phù hợp.

Với kiểm thử nhẹ, tạo `DefaultConversionService`, gọi `addConverter` và xác minh cặp kiểu chuyển đổi. Với test cấu hình ứng dụng, nạp Spring context và inject `ConversionService` để xác nhận converter thực sự được đăng ký.

Không cần nạp toàn bộ context chỉ để kiểm tra thuật toán converter. Chỉ dùng integration test khi mục tiêu bao gồm cấu hình bean, thứ tự đăng ký hoặc hành vi của web binding.

### 9.2. Đăng ký Validator trong web layer

Một `org.springframework.validation.Validator` có thể được gọi thủ công trong controller, được đăng ký qua cấu hình MVC hoặc được dùng trong luồng binding thích hợp. Việc test `validate()` trực tiếp không chứng minh controller đã gọi validator đó.

Nếu cần xác minh web layer:

- Dùng Spring MVC Test/MockMvc để gửi request.
- Kiểm tra status và response lỗi theo hợp đồng API.
- Kiểm tra field path hoặc error code được trả ra nếu đó là dữ liệu công khai.
- Xác minh service không được gọi khi validation thất bại.

Với `@Valid` hoặc `@Validated`, hãy kiểm tra đúng đối tượng và vị trí annotation. Đối với method validation, cần cấu hình Spring AOP/method validation để lời gọi đi qua proxy. Một unit test gọi trực tiếp validator vẫn có giá trị, nhưng nó bảo vệ một lớp trách nhiệm khác.

## 10. Viết test dễ đọc bằng Arrange–Act–Assert

Mỗi test nên thể hiện rõ ba phần:

- **Arrange:** tạo đối tượng, validator/converter, locale và dữ liệu đầu vào.
- **Act:** gọi đúng một hành vi cần kiểm tra.
- **Assert:** kiểm tra giá trị, lỗi, property path hoặc tác động phụ.

Ví dụ tên test:

```java
@Test
void validate_whenPasswordIsTooShort_addsPasswordFieldError() {
    // Arrange
    var form = new RegistrationForm("user@example.com", "short");
    Errors errors = new BeanPropertyBindingResult(form, "form");

    // Act
    validator.validate(form, errors);

    // Assert
    assertTrue(errors.hasFieldErrors("password"));
}
```

Tên test mô tả điều kiện và kết quả, giúp báo cáo chỉ ra quy tắc nào thất bại. Tránh tên chung như `testValidation` hoặc `testConvert` vì chúng không nói được trường hợp đang được bảo vệ.

Với nhiều đầu vào cùng một quy tắc, dùng parameterized test. Với các trường hợp có cách chuẩn bị hoặc kết quả khác nhau đáng kể, viết test riêng sẽ dễ đọc hơn một phương thức chứa nhiều nhánh `if`.

## 11. Những lỗi thường gặp khi kiểm thử validation và conversion

**Chỉ kiểm tra dữ liệu hợp lệ.** Một validator thường có nhiều nhánh từ chối; một converter cần xử lý đầu vào sai định dạng. Hãy kiểm tra các lớp tương đương và giá trị biên.

**Nhầm lỗi conversion với lỗi validation.** `"abc"` không thể parse thành số nguyên là lỗi chuyển đổi; `-1` parse được nhưng không thỏa quy tắc số lượng là lỗi validation. Hai lỗi có thể được hiển thị khác nhau ở API.

**Không xác định hành vi với `null` và chuỗi rỗng.** Một số converter không được gọi khi nguồn là `null` qua `ConversionService`; validator có thể coi `null` là hợp lệ để constraint `@NotNull` xử lý. Test phải phản ánh đúng ranh giới API.

**Phụ thuộc locale mặc định của máy.** Test chạy trên máy cá nhân có thể khác CI. Hãy truyền `Locale` tường minh hoặc đặt và khôi phục `LocaleContextHolder` khi cần.

**So sánh số thập phân bằng `double`.** Với tiền tệ và dữ liệu cần độ chính xác, dùng `BigDecimal` và xác định rõ scale, rounding mode.

**Kiểm tra nguyên văn thông báo đã dịch.** Message có thể thay đổi theo bundle và locale. Ưu tiên kiểm tra error code, property path và constraint descriptor, trừ khi nội dung message là hợp đồng.

**Khởi động toàn bộ Spring context cho quy tắc thuần.** Validator hoặc converter không phụ thuộc Spring có thể được tạo trực tiếp. Nạp context chỉ khi cần xác minh tích hợp hoặc cấu hình.

**Kiểm tra converter riêng nhưng bỏ qua registry.** Test trực tiếp không chứng minh converter được đăng ký. Nếu đăng ký là phần có rủi ro, thêm test `ConversionService` hoặc integration test cấu hình.

**Để trạng thái toàn cục rò rỉ giữa các test.** Locale, system property, timezone và cache có thể ảnh hưởng test sau. Khôi phục trạng thái trong `finally` hoặc dùng extension quản lý tài nguyên.

## 12. Quy trình xây dựng bộ test

Khi triển khai test cho validation và chuyển đổi dữ liệu trong dự án Spring, có thể thực hiện theo trình tự:

1. Xác định quy tắc thuộc validation, conversion hay formatting.
2. Ghi rõ kiểu nguồn/đích, field, dữ liệu biên và hành vi với `null`/rỗng.
3. Tách quy tắc thuần khỏi web binding, dependency bên ngoài và Spring context nếu có thể.
4. Viết unit test trực tiếp cho validator, converter hoặc formatter bằng JUnit Jupiter.
5. Dùng parameterized test cho các nhóm đầu vào có cùng kết quả mong đợi.
6. Kiểm tra mã lỗi, property path, giá trị đích hoặc exception theo hợp đồng ổn định.
7. Thêm test `ConversionService` hoặc `LocalValidatorFactoryBean` nếu cần xác minh adapter/registry của Spring.
8. Thêm MVC hoặc Spring context integration test khi cần bảo vệ việc đăng ký, binding, `@Valid`, `@Validated` hoặc method validation.
9. Đảm bảo test độc lập với locale, timezone, dữ liệu dùng chung và thứ tự chạy.

Khi các bước này được tách bạch, test sẽ chỉ ra chính xác quy tắc nào sai: dữ liệu không parse được, giá trị sau chuyển đổi không hợp lệ, validator phát lỗi sai field, hay Spring chưa đăng ký đúng thành phần. Đây là nền tảng để bảo vệ các quy tắc dữ liệu của ứng dụng Spring bằng unit test nhanh, dễ đọc và ổn định.
