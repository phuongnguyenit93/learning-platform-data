# Kiểm thử Spring Validator bằng BeanPropertyBindingResult

`BeanPropertyBindingResult` là một công cụ quan trọng để viết **unit test cho Spring `Validator` mà không phải khởi động Spring Boot, Servlet container hay ApplicationContext**. Thay vì gửi HTTP request, bạn tạo JavaBean chứa dữ liệu cần kiểm tra, tạo một `BeanPropertyBindingResult` cho bean đó, gọi `Validator.validate(target, errors)` rồi kiểm tra cấu trúc lỗi.

Mẫu ba bước:

~~~java
BookingForm form = new BookingForm();
BeanPropertyBindingResult errors =
    new BeanPropertyBindingResult(form, "booking");

new BookingValidator().validate(form, errors);

boolean invalid = errors.hasErrors();
~~~

Đây là đoạn minh họa; các class đầy đủ và kiểm thử chạy được nằm ở phần 7. **Constructor không tự bind hoặc validate**. Chính lệnh `validate` mới chạy logic của Spring `Validator` do bạn viết.

Bài học thuộc nhóm **Kiểm thử** của module **Spring Framework — validation-data-binding**. Nội dung gồm hợp đồng `supports/validate`, tạo fixture, kiểm tra `FieldError`/`ObjectError`, nhiều lỗi, nested property paths, `ValidationUtils`, message codes và đa ngữ, sự khác nhau giữa `BeanPropertyBindingResult` và `DataBinder`, ví dụ Java 17+/Spring Framework 6.2/JUnit 5, cách debug và checklist.

## 1. Khi nào cần test Validator thuần?

Spring có interface:

~~~java
package org.springframework.validation;

public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

Đây là **chữ ký rút gọn** của API Spring. Một validator xác định kiểu object mà nó hỗ trợ, kiểm tra object và ghi các lỗi vào `Errors`. Nó không phải một HTTP handler, không tự kết nối database và không tự trả status HTTP.

Ví dụ rule của một booking:

- `customer` phải có nội dung khác whitespace;
- `seats` phải có số ghế và tối thiểu là 1;
- `startDate` và `endDate` không được thiếu;
- `endDate` phải sau `startDate` — đây là lỗi **toàn object**, không chỉ một field;
- `contact.email` không được để trống;
- nếu `contact` null, báo lỗi field `contact`, không cố đọc email và gây `NullPointerException`.

Một unit test chất lượng cần kiểm tra **mã lỗi, field path, số lỗi và loại lỗi**, thay vì chỉ kiểm tra một boolean `hasErrors()==true`.

| Loại thử nghiệm | Công cụ | Nó chứng minh gì? |
|---|---|---|
| Logic custom `Validator` | `BeanPropertyBindingResult` + JUnit | Rule nào reject field/object nào |
| JavaBean binding/type conversion | `DataBinder` + `MutablePropertyValues` | Chuỗi input có chuyển được thành Java property không |
| Jakarta `@NotNull`/`@Min` | `jakarta.validation.Validator` hoặc Spring adapter | Constraint provider chạy đúng |
| Spring MVC form/JSON | MockMvc | Argument resolution, `@Valid`, `@InitBinder`, HTTP status/advice |
| Thông báo đa ngữ | `StaticMessageSource` hoặc messages bundles | Error code được dịch đúng locale |

**Không nhầm Spring `Validator` với Jakarta Bean Validation.** Một bean có `@NotNull` không tự được kiểm tra chỉ vì bạn tạo `BeanPropertyBindingResult`. Test Spring `Validator` thuần phải gọi `validate`, còn Jakarta annotations cần provider/adapter được kích hoạt.

## 2. `BeanPropertyBindingResult`: class và constructors

Package:

~~~java
org.springframework.validation.BeanPropertyBindingResult
~~~

Class này implements `Errors` và `BindingResult`, sử dụng **JavaBean property access** để đọc fields qua getter/property descriptor, đồng thời hỗ trợ nested paths.

Hai constructors:

~~~java
new BeanPropertyBindingResult(target, objectName);

new BeanPropertyBindingResult(
    target, objectName,
    autoGrowNestedPaths,
    autoGrowCollectionLimit);
~~~

Trong đó:

- `target` là bean mà các lỗi liên quan tới.
- `objectName` là tên logic của object, ví dụ `booking`; tên này ảnh hưởng **message codes**.
- `autoGrowNestedPaths` quyết định hành vi hỗ trợ nested path growth trong property access.
- `autoGrowCollectionLimit` giới hạn auto-grow collection, không phải giới hạn kích thước JSON/request bytes.

Với unit test validator, thông thường chỉ cần constructor hai tham số.

### Những thứ constructor KHÔNG làm

- Không gọi `supports` hay `validate`.
- Không đọc HTTP request hoặc JSON.
- Không chạy `@Valid`/`@Validated` hoặc Jakarta provider.
- Không tự chuyển `"abc"` thành `Integer`.
- Không làm cho một `@ControllerAdvice` tạo lỗi HTTP.
- Không reset lỗi tự động nếu object `BindingResult` cũ được tái sử dụng.

Vì thế mẫu chuẩn là:

~~~java
BookingForm fixture = validBooking();
BeanPropertyBindingResult result =
    new BeanPropertyBindingResult(fixture, "booking");

validator.validate(fixture, result);

assertFalse(result.hasErrors());
~~~

Đoạn trên là snippet trong một test có các hàm/biến đã khai báo. Mỗi test nên tạo **result mới** để tránh shared mutable state.

## 3. Kiểm tra `supports(Class<?>)` trước khi kiểm tra logic

Một validator cho `BookingForm` có thể triển khai:

~~~java
@Override
public boolean supports(Class<?> type) {
    return BookingForm.class.isAssignableFrom(type);
}
~~~

Với implementation này:

~~~java
assertTrue(validator.supports(BookingForm.class));
assertFalse(validator.supports(String.class));
~~~

Tại sao cần test riêng? Gọi trực tiếp `validator.validate(form, result)` **không tự thực thi `supports(...)` trước**. Do đó validate có thể chạy trong unit test dù `supports` bị lập trình sai; khi kết nối với `DataBinder`/framework, validator có thể bị từ chối vì không hỗ trợ target.

`ValidationUtils.invokeValidator(...)` là helper có kiểm tra target/type compatibility, nên cũng có thể dùng khi cần mô phỏng cách framework invoke validator, nhưng bài thực hành gọi `validate(...)` trực tiếp để đơn giản và test `supports` riêng.

### Không đặt business rule vào `supports`

`supports` chỉ xác nhận Java type, không dùng nó để kiểm tra `seats`, `startDate` hoặc trạng thái của một instance. Các rule giá trị thuộc `validate`; nếu để logic dựa vào object instance trong `supports`, bạn đang dùng sai contract.

## 4. FieldError: lỗi thuộc một property

Khi số ghế không hợp lệ:

~~~java
errors.rejectValue(
    "seats",
    "seats.min",
    new Object[] {1},
    "Seats must be at least {0}");
~~~

Spring ghi một `FieldError` có tên field `seats`, mã gốc `seats.min`, arguments và default message. Cách kiểm tra:

~~~java
FieldError issue = result.getFieldError("seats");

assertNotNull(issue);
assertEquals("seats", issue.getField());
assertEquals("seats.min", issue.getCode());
assertEquals(0, issue.getRejectedValue());
assertFalse(issue.isBindingFailure());
~~~

**`isBindingFailure()==false`** vì lỗi này do custom validation `rejectValue` tạo, không phải conversion error từ data binding. Trái lại, nếu `DataBinder` cố gắn `"abc"` vào `Integer seats` và thất bại, `FieldError.isBindingFailure()` thường bằng true với mã `typeMismatch`.

`FieldError.getRejectedValue()` hữu ích cho synthetic test fixtures, nhưng không serialize nguyên rejected values ra API công khai hoặc log sản xuất nếu có mật khẩu, token hay dữ liệu riêng tư.

### Một field có thể có nhiều lỗi

`result.getFieldError("seats")` chỉ lấy **một lỗi đầu tiên**. Nếu field có nhiều rule vi phạm, dùng `getFieldErrors("seats")`. `getFieldErrorCount()` đếm **error entries**, không phải số tên field duy nhất.

Với test behavior, hãy assert field name + code + count; `assertTrue(result.hasErrors())` quá chung, có thể PASS ngay cả khi lỗi bị ghi nhầm field.

## 5. ObjectError: lỗi thuộc quan hệ giữa nhiều fields

Một quy tắc như “ngày kết thúc phải sau ngày bắt đầu” không nên đổ lỗi cho một field ngẫu nhiên nếu muốn frontend hiển thị lỗi ở phần chung của form.

~~~java
if (form.getStartDate() != null
        && form.getEndDate() != null
        && !form.getEndDate().isAfter(form.getStartDate())) {
    errors.reject(
        "booking.range.invalid",
        "End date must be after start date");
}
~~~

`errors.reject(...)` tạo **`ObjectError`/global error**. `errors.rejectValue(...)` tạo **`FieldError`**. Kiểm thử:

~~~java
assertEquals(0, result.getFieldErrorCount());
assertEquals(1, result.getGlobalErrorCount());

ObjectError error = result.getGlobalError();
assertNotNull(error);
assertEquals("booking", error.getObjectName());
assertEquals("booking.range.invalid", error.getCode());
~~~

Không kiểm tra range nếu một ngày đang null. Khi một field chưa parse được hoặc thiếu, rule quan hệ không có đủ thông tin; nên để field-level validation/binding ghi lỗi tương ứng.

### Đếm đúng tổng lỗi

`FieldError` kế thừa `ObjectError`. Do đó:

- `result.getFieldErrors()`: chỉ các lỗi theo trường.
- `result.getGlobalErrors()`: chỉ các lỗi toàn object.
- `result.getAllErrors()`: **cả hai loại**.

Nếu có ba field errors và một global error:

~~~text
getFieldErrorCount() = 3
getGlobalErrorCount() = 1
getErrorCount() = 4
getAllErrors().size() = 4
~~~

Không dùng `getAllErrors()` để tạo riêng danh sách global errors vì sẽ bị trùng/nhầm field errors.

## 6. ValidationUtils và đường dẫn lồng nhau

Spring cung cấp:

~~~java
ValidationUtils.rejectIfEmptyOrWhitespace(
    errors,
    "customer",
    "required",
    "Customer is required");
~~~

Helper này đọc property trên bean qua `Errors`; nó reject `null`, `""` hoặc một chuỗi chỉ chứa whitespace. Khác với `ValidationUtils.rejectIfEmpty(...)`, helper không có từ `OrWhitespace` chỉ reject null/empty string, không reject mọi chuỗi chứa khoảng trắng.

### Test nested `contact.email`

Giả sử `BookingForm` có property `contact` thuộc class `Contact`, trong đó có `email`. Spring `Errors` hỗ trợ scope:

~~~java
errors.pushNestedPath("contact");
try {
    ValidationUtils.rejectIfEmptyOrWhitespace(
        errors, "email", "required",
        "Contact email is required");
}
finally {
    errors.popNestedPath();
}
~~~

Khi nested path là `contact.`, lỗi sẽ có `getField()=="contact.email"`. Test cần xác minh:

~~~java
assertTrue(result.hasFieldErrors("contact.email"));
assertEquals("", result.getNestedPath());
~~~

`finally` bảo đảm nested path được phục hồi ngay cả khi có exception. Không quên `popNestedPath()` vì các lỗi tiếp theo có thể bị gắn prefix sai.

Nếu `contact==null`, hãy xử lý trước khi gọi nested validator; ví dụ dưới đây sẽ báo `FieldError("contact","required")` để không làm test văng `NullPointerException`.

## 7. Dự án Java 17 + Spring 6.2 + JUnit 5 có thể chạy

Ví dụ là **unit test Spring Validator thuần**, không cần server. Tạo project Gradle với cấu trúc:

~~~text
validator-unit-tests/
  settings.gradle
  build.gradle
  src/main/java/com/example/validation/
    BookingForm.java
    BookingValidator.java
  src/test/java/com/example/validation/
    BookingValidatorTest.java
    BindingAndMessageTest.java
~~~

### `settings.gradle`

~~~groovy
rootProject.name = 'validator-unit-tests'
~~~

### `build.gradle`

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

test {
    useJUnitPlatform()
}
~~~

`spring-context` kéo các Spring dependencies cần cho `Validator`, `BeanPropertyBindingResult` và `StaticMessageSource`. JUnit Jupiter có API và engine để chạy tests. Các versions được cố định để demo dễ tái hiện trên Spring 6.2; không có ý nói đây luôn là bản mới nhất. Nếu project dùng Spring Boot BOM, để BOM quản lý versions của Spring thay vì pin một phiên bản có thể xung đột.

### `BookingForm.java`

`src/main/java/com/example/validation/BookingForm.java`:

~~~java
package com.example.validation;

import java.time.LocalDate;

public class BookingForm {

    private String customer;
    private Integer seats;
    private LocalDate startDate;
    private LocalDate endDate;
    private Contact contact = new Contact();

    public BookingForm() {
    }

    public String getCustomer() {
        return customer;
    }

    public void setCustomer(String customer) {
        this.customer = customer;
    }

    public Integer getSeats() {
        return seats;
    }

    public void setSeats(Integer seats) {
        this.seats = seats;
    }

    public LocalDate getStartDate() {
        return startDate;
    }

    public void setStartDate(LocalDate startDate) {
        this.startDate = startDate;
    }

    public LocalDate getEndDate() {
        return endDate;
    }

    public void setEndDate(LocalDate endDate) {
        this.endDate = endDate;
    }

    public Contact getContact() {
        return contact;
    }

    public void setContact(Contact contact) {
        this.contact = contact;
    }

    public static class Contact {

        private String email;

        public Contact() {
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }
    }
}
~~~

Đây là JavaBean có constructor không tham số, getters/setters và nested object có thể truy cập theo property path. `BeanPropertyBindingResult` dùng bean-property access nên việc dựng fixture rõ ràng giúp test ổn định.

### `BookingValidator.java`

`src/main/java/com/example/validation/BookingValidator.java`:

~~~java
package com.example.validation;

import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public final class BookingValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return BookingForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        BookingForm form = (BookingForm) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
            errors, "customer", "required",
            "Customer is required");

        if (form.getSeats() == null) {
            errors.rejectValue(
                "seats", "required",
                "Number of seats is required");
        }
        else if (form.getSeats() < 1) {
            errors.rejectValue(
                "seats", "seats.min",
                new Object[] {1},
                "Number of seats must be at least {0}");
        }

        if (form.getStartDate() == null) {
            errors.rejectValue(
                "startDate", "required",
                "Start date is required");
        }

        if (form.getEndDate() == null) {
            errors.rejectValue(
                "endDate", "required",
                "End date is required");
        }

        if (form.getStartDate() != null
                && form.getEndDate() != null
                && !form.getEndDate().isAfter(
                    form.getStartDate())) {
            errors.reject(
                "booking.range.invalid",
                "End date must be after start date");
        }

        if (form.getContact() == null) {
            errors.rejectValue(
                "contact", "required",
                "Contact is required");
        }
        else {
            errors.pushNestedPath("contact");
            try {
                ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "email", "required",
                    "Contact email is required");
            }
            finally {
                errors.popNestedPath();
            }
        }
    }
}
~~~

Các quyết định trong code có chủ ý:

- `seats=null` và `seats=0` ghi **mã lỗi khác nhau**, không ghi lỗi trùng.
- Trường ngày thiếu được kiểm tra trước. Quan hệ hai ngày chỉ xét khi cả hai có giá trị.
- `errors.reject(...)` lưu lỗi toàn object.
- `contact==null` được phát hiện trước khi truy cập nested path.
- `pushNestedPath/popNestedPath` luôn cân bằng nhờ `finally`.
- Validator không gọi database, HTTP client, không tự thay đổi object.

**Không có annotation `@Valid` trong project**, vì ta gọi custom Spring Validator trực tiếp ở unit tests. Nếu bạn thêm Jakarta annotations lên bean, các annotation đó vẫn **không tự chạy** trong code này.

## 8. JUnit: kiểm tra từng nhóm hành vi

`src/test/java/com/example/validation/BookingValidatorTest.java`:

~~~java
package com.example.validation;

import java.time.LocalDate;

import org.junit.jupiter.api.Test;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.ValidationUtils;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BookingValidatorTest {

    private final BookingValidator validator =
        new BookingValidator();

    static BookingForm good() {
        BookingForm form = new BookingForm();
        form.setCustomer("Lan");
        form.setSeats(2);
        form.setStartDate(LocalDate.of(2026, 12, 20));
        form.setEndDate(LocalDate.of(2026, 12, 22));
        form.getContact().setEmail("lan@example.org");
        return form;
    }

    private BeanPropertyBindingResult check(BookingForm form) {
        BeanPropertyBindingResult errors =
            new BeanPropertyBindingResult(form, "booking");
        validator.validate(form, errors);
        return errors;
    }

    @Test
    void supportsCorrectType() {
        assertTrue(validator.supports(BookingForm.class));
        assertFalse(validator.supports(String.class));
    }

    @Test
    void validFormHasNoErrors() {
        BeanPropertyBindingResult errors = check(good());

        assertFalse(errors.hasErrors());
        assertEquals(0, errors.getErrorCount());
        assertEquals("booking", errors.getObjectName());
    }

    @Test
    void blankCustomerCreatesFieldError() {
        BookingForm form = good();
        form.setCustomer("   ");

        BeanPropertyBindingResult errors = check(form);
        FieldError field = errors.getFieldError("customer");

        assertNotNull(field);
        assertEquals("required", field.getCode());
        assertEquals("customer", field.getField());
        assertEquals("   ", field.getRejectedValue());
        assertFalse(field.isBindingFailure());
        assertEquals(1, errors.getFieldErrorCount());
    }

    @Test
    void missingSeatsIsDifferentFromZero() {
        BookingForm form = good();
        form.setSeats(null);

        BeanPropertyBindingResult errors = check(form);

        assertTrue(errors.hasFieldErrors("seats"));
        assertEquals("required",
            errors.getFieldError("seats").getCode());
        assertEquals(1, errors.getErrorCount());
    }

    @Test
    void zeroSeatsCreatesMinFieldError() {
        BookingForm form = good();
        form.setSeats(0);

        BeanPropertyBindingResult errors = check(form);
        FieldError field = errors.getFieldError("seats");

        assertNotNull(field);
        assertEquals("seats.min", field.getCode());
        assertEquals(0, field.getRejectedValue());
        assertEquals(0, errors.getGlobalErrorCount());
    }

    @Test
    void invalidRangeIsOneGlobalError() {
        BookingForm form = good();
        form.setEndDate(form.getStartDate());

        BeanPropertyBindingResult errors = check(form);

        assertEquals(0, errors.getFieldErrorCount());
        assertEquals(1, errors.getGlobalErrorCount());

        ObjectError global = errors.getGlobalError();
        assertNotNull(global);
        assertEquals("booking", global.getObjectName());
        assertEquals("booking.range.invalid",
            global.getCode());
    }

    @Test
    void missingDatesAreFieldErrors() {
        BookingForm form = good();
        form.setStartDate(null);
        form.setEndDate(null);

        BeanPropertyBindingResult errors = check(form);

        assertTrue(errors.hasFieldErrors("startDate"));
        assertTrue(errors.hasFieldErrors("endDate"));
        assertEquals(2, errors.getFieldErrorCount());
        assertEquals(0, errors.getGlobalErrorCount());
    }

    @Test
    void nestedEmailHasFullFieldPath() {
        BookingForm form = good();
        form.getContact().setEmail(" ");

        BeanPropertyBindingResult errors = check(form);
        FieldError field =
            errors.getFieldError("contact.email");

        assertNotNull(field);
        assertEquals("contact.email", field.getField());
        assertEquals("required", field.getCode());
        assertEquals("", errors.getNestedPath());
    }

    @Test
    void nullContactIsHandledGracefully() {
        BookingForm form = good();
        form.setContact(null);

        BeanPropertyBindingResult errors = check(form);

        assertTrue(errors.hasFieldErrors("contact"));
        assertEquals("required",
            errors.getFieldError("contact").getCode());
        assertFalse(errors.hasFieldErrors("contact.email"));
    }

    @Test
    void multipleFieldAndGlobalErrorsStaySeparate() {
        BookingForm form = good();
        form.setCustomer("");
        form.setSeats(0);
        form.setEndDate(form.getStartDate());
        form.getContact().setEmail("");

        BeanPropertyBindingResult errors = check(form);

        assertEquals(3, errors.getFieldErrorCount());
        assertEquals(1, errors.getGlobalErrorCount());
        assertEquals(4, errors.getErrorCount());
        assertEquals(4, errors.getAllErrors().size());
    }

    @Test
    void messageCodesHaveExpectedPriority() {
        BookingForm form = good();
        form.setCustomer("");

        BeanPropertyBindingResult errors = check(form);
        FieldError field = errors.getFieldError("customer");

        assertNotNull(field);
        assertArrayEquals(
            new String[] {
                "required.booking.customer",
                "required.customer",
                "required.java.lang.String",
                "required"
            },
            field.getCodes());
    }

    @Test
    void constructorDoesNotValidate() {
        BookingForm invalid = new BookingForm();
        BeanPropertyBindingResult result =
            new BeanPropertyBindingResult(invalid, "booking");

        assertFalse(result.hasErrors());
        validator.validate(invalid, result);
        assertTrue(result.hasErrors());
    }

    @Test
    void emptyAndWhitespaceHelpersDiffer() {
        BookingForm form = good();
        form.setCustomer("   ");

        BeanPropertyBindingResult result =
            new BeanPropertyBindingResult(form, "booking");

        ValidationUtils.rejectIfEmpty(
            result, "customer", "required");
        assertFalse(result.hasErrors());

        ValidationUtils.rejectIfEmptyOrWhitespace(
            result, "customer", "required");
        assertTrue(result.hasFieldErrors("customer"));
    }
}
~~~

**13 test methods** ở class này cover: supports, valid form, whitespace, missing/zero seats, global rule, null dates, nested path, nested bean null, nhiều lỗi đồng thời, message codes, constructor không tự validate và helper behavior. Mỗi case tạo `BeanPropertyBindingResult` **mới**, giúp tests độc lập.

Test không assert thứ tự `getAllErrors()` giữa nhiều fields. Spring Validator ở đây ghi lỗi theo một thứ tự source cụ thể, nhưng test điều quan trọng hơn là **đúng field/code/count**, tránh tạo contract không cần thiết về thứ tự.

## 9. Test DataBinder và MessageSource riêng

Khi cần phân biệt type conversion errors và custom validation errors, dùng `DataBinder`. Khi cần kiểm tra tiếng Việt/tiếng Anh, dùng `StaticMessageSource`.

`src/test/java/com/example/validation/BindingAndMessageTest.java`:

~~~java
package com.example.validation;

import java.util.Locale;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.context.support.StaticMessageSource;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;
import org.springframework.validation.ValidationUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BindingAndMessageTest {

    @Test
    void invalidIntegerIsBindingFailure() {
        BookingForm form = BookingValidatorTest.good();
        DataBinder binder = new DataBinder(form, "booking");

        binder.bind(new MutablePropertyValues(
            Map.of("seats", "not-a-number")));

        BindingResult result = binder.getBindingResult();
        FieldError field = result.getFieldError("seats");

        assertNotNull(field);
        assertTrue(field.isBindingFailure());
        assertEquals("typeMismatch", field.getCode());
        assertEquals("not-a-number",
            field.getRejectedValue());
    }

    @Test
    void directResultDoesNotBindProperties() {
        BookingForm form = BookingValidatorTest.good();
        BeanPropertyBindingResult result =
            new BeanPropertyBindingResult(form, "booking");

        assertEquals(2, form.getSeats());
        assertFalse(result.hasErrors());
        assertEquals(form, result.getTarget());
    }

    @Test
    void translatesFieldErrorToVietnamese() {
        BookingForm form = BookingValidatorTest.good();
        form.setCustomer("");

        BeanPropertyBindingResult result =
            new BeanPropertyBindingResult(form, "booking");

        ValidationUtils.rejectIfEmptyOrWhitespace(
            result, "customer", "required");

        FieldError field = result.getFieldError("customer");
        assertNotNull(field);

        Locale vi = Locale.forLanguageTag("vi");
        StaticMessageSource source = new StaticMessageSource();

        source.addMessage(
            "required.booking.customer",
            vi,
            "Vui lòng nhập tên khách.");
        source.addMessage(
            "required",
            vi,
            "Trường này bắt buộc.");

        assertEquals(
            "Vui lòng nhập tên khách.",
            source.getMessage(field, vi));
    }

    @Test
    void translatesSameCodeToEnglish() {
        BookingForm form = BookingValidatorTest.good();
        form.setCustomer("");

        BeanPropertyBindingResult result =
            new BeanPropertyBindingResult(form, "booking");

        ValidationUtils.rejectIfEmptyOrWhitespace(
            result, "customer", "required");

        FieldError field = result.getFieldError("customer");
        assertNotNull(field);

        StaticMessageSource source = new StaticMessageSource();
        source.addMessage(
            "required.booking.customer",
            Locale.ENGLISH,
            "Customer name is required.");

        assertEquals(
            "Customer name is required.",
            source.getMessage(field, Locale.ENGLISH));
    }
}
~~~

**Tổng 17 tests trong project:** 13 tests của `BookingValidatorTest` và 4 tests của `BindingAndMessageTest`. Đây là thiết kế kiểm thử dự kiến; không tuyên bố đã chạy Gradle trong môi trường bài viết.

### Chạy

Nếu đã có Gradle wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu đây là project mới tạo chỉ có `build.gradle` và máy đã cài Gradle, có thể tạo wrapper:

~~~bash
gradle wrapper
./gradlew test
~~~

Các tests dùng Spring classes nhưng không khởi động server. `StaticMessageSource` là source in-memory nên không cần file `messages_vi.properties`; nó cho phép chứng minh message code fallback độc lập với filesystem/locale của CI.

## 10. `BeanPropertyBindingResult` và `DataBinder` không giống nhau

Một lỗi dễ mắc là xem `BeanPropertyBindingResult` như bộ chuyển đổi dữ liệu HTTP. Thực tế:

~~~java
BookingForm form = new BookingForm();
BeanPropertyBindingResult result =
    new BeanPropertyBindingResult(form, "booking");
~~~

chỉ tạo error holder. Để chuyển chuỗi request/form sang Java properties:

~~~java
DataBinder binder = new DataBinder(form, "booking");
MutablePropertyValues input = new MutablePropertyValues();

input.add("seats", "abc");
binder.bind(input);

BindingResult result = binder.getBindingResult();
~~~

`binder.bind(...)` thực hiện property binding và type conversion. Nếu `"abc"` không thể chuyển thành `Integer`, có thể xuất hiện `FieldError` `typeMismatch`/`isBindingFailure()==true`. Nếu muốn chạy custom validator **sau** bind:

~~~java
DataBinder binder = new DataBinder(form, "booking");
binder.setValidator(new BookingValidator());

binder.bind(input);
binder.validate();

BindingResult result = binder.getBindingResult();
~~~

Đây là snippet trong nơi có biến `form`/`input`. Lỗi binding và lỗi validation cùng có thể nằm trong một `BindingResult` của binder, nhưng không có nghĩa mọi lỗi đều cùng nguồn.

**Đừng tự tạo một `BeanPropertyBindingResult` khác để đọc kết quả của DataBinder.** Hãy lấy chính `binder.getBindingResult()`.

### Tại sao kiểm thử theo nhiều tầng?

| Mục tiêu | Công cụ nên dùng |
|---|---|
| `BookingValidator` reject dữ liệu sai nào | `BeanPropertyBindingResult` |
| `"123"` chuyển thành `Integer 123` | `DataBinder` |
| `"abc"` gây `typeMismatch` | `DataBinder` |
| `@InitBinder` có gắn validator vào MVC không | MockMvc |
| `@Valid @ModelAttribute` được thực thi đúng không | MockMvc |
| `@RequestBody` parse JSON và trả HTTP 400 đúng không | MockMvc |
| Jakarta constraint trên DTO có hiệu lực không | Jakarta Validator/test context phù hợp |
| `MessageSource` chọn bản dịch chính xác không | `StaticMessageSource` hoặc integration test bundles |

Unit test giúp tìm đúng lỗi trong logic nhỏ; integration test giúp kiểm tra wiring và runtime behavior. Không tự động bắt buộc `@SpringBootTest` cho mọi `Validator` unit test.

## 11. Message codes, getCode và đa ngữ

`BeanPropertyBindingResult` thường dùng `DefaultMessageCodesResolver`. Với `errors.rejectValue("customer","required",...)` trên object `booking` và Java type `String`, các mã có thể là:

~~~text
required.booking.customer
required.customer
required.java.lang.String
required
~~~

**Thứ tự từ cụ thể đến tổng quát** để `MessageSource` tra cứu. Phân biệt:

- `error.getCodes()[0]`: key cụ thể nhất (trong cấu hình mặc định).
- `error.getCode()`: mã gốc/default code, thường là phần tử cuối, ví dụ `required`.
- `error.getDefaultMessage()`: message fallback khi các keys không được resolve.
- `messageSource.getMessage(error, locale)`: thông báo thực tế theo locale.

Lỗi toàn object `booking.range.invalid` trên object `booking` thường có:

~~~text
booking.range.invalid.booking
booking.range.invalid
~~~

Với field lồng `contact.email` hoặc indexed property như `items[0].sku`, resolver có thể sinh thêm biến thể keys có/không nested index. **Không giả định mọi field error luôn chỉ có bốn keys**.

### Vì sao test i18n cần tách riêng?

Nếu chỉ assert `getDefaultMessage()` chứa một câu tiếng Anh, test **không chứng minh** app đã dịch sang tiếng Việt. `StaticMessageSource` cho phép đăng ký keys rõ ràng rồi gọi `getMessage(field,Locale.forLanguageTag("vi"))`.

Với ứng dụng nhiều controllers, có thể dùng `messages.properties` và `messages_vi.properties` thông qua Spring Boot MessageSource auto-configuration, nhưng đây là integration layer khác, không thuộc unit test thuần.

## 12. Nested path, JavaBeans và collection

`BeanPropertyBindingResult` đọc nested property paths như `contact.email` qua JavaBean access. Nếu model có `List<Item> items`, validator có thể:

~~~java
for (int i = 0; i < form.getItems().size(); i++) {
    errors.pushNestedPath("items[" + i + "]");
    try {
        ValidationUtils.rejectIfEmptyOrWhitespace(
            errors, "sku", "required");
    }
    finally {
        errors.popNestedPath();
    }
}
~~~

Đây là snippet **không thuộc project chính**; cần class có `getItems()` và item JavaBeans với `getSku()`. Nó minh họa cách lỗi có field path `items[0].sku`.

Cần kiểm tra collection null/empty, phần tử null, index biên, số lượng phần tử và state nested path sau vòng lặp. `BeanPropertyBindingResult` có thể hỗ trợ auto-grow một số nested paths theo cấu hình, nhưng **không** nên dựa vào auto-grow để “vá” fixture thiếu object: hãy dựng dữ liệu test rõ ràng.

**Bean property access vs direct field:** Nếu project cố ý bind qua fields trực tiếp không có getter/setter, Spring có `DirectFieldBindingResult`; đừng kỳ vọng `BeanPropertyBindingResult` tự có cùng semantics. Với immutable records/constructor binding, cần kiểm tra riêng cơ chế tạo/bind DTO.

## 13. Những lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `hasErrors()==false` dù fixture sai | Chỉ new result, chưa gọi `validate` | Gọi `validator.validate(target,result)` |
| Test tự gọi validate PASS nhưng MVC không dùng validator | `supports` sai/chưa đăng ký qua binder | Test supports và thêm integration test |
| Lỗi có field tên `email` thay vì `contact.email` | Thiếu nested path | Push `contact`, reject `email`, pop |
| Lỗi sau email thành `contact.seats` | Quên pop nested path | Dùng `try/finally` |
| `NullPointerException` khi contact null | Validator không kiểm tra object con | Reject field `contact` trước |
| `getAllErrors()` nhiều hơn `getFieldErrors()` | Có global errors | Kiểm tra hai danh sách riêng |
| Cross-field rule xuất hiện dưới `endDate` | Dùng `rejectValue` thay vì `reject` | Chọn global error khi rule thuộc toàn object |
| Error code theo object khác production | Test dùng objectName khác `@ModelAttribute` | Dùng cùng tên logic |
| Unit validator không báo typeMismatch cho chuỗi `"abc"` | Không có bước bind | Dùng `DataBinder` test |
| `isBindingFailure()==false` trên custom reject | Đây là validation error | Đúng behavior; khác conversion |
| `@NotNull` annotation không được thực thi | Chưa gọi Jakarta provider | Test Jakarta Validation riêng |
| `getDefaultMessage()` không phải tiếng Việt | Chưa resolve MessageSource | Dùng `messageSource.getMessage(error,vi)` |
| Test khác nhau chạy gây lỗi lặp | Shared mutable `BindingResult`/DTO | Tạo fixture và result mới |
| Test field với hai lỗi nhưng chỉ thấy một | Dùng `getFieldError(field)` | Dùng `getFieldErrors(field)` |
| Thay `String` thành `Integer` làm assertion codes fail | Fallback key có Java field type | Kiểm tra `getCodes()` và contract |
| MockMvc không phản ánh test unit | Wiring/binding/annotation khác | Phân biệt test logic và test framework |
| Test dump nguyên rejected password | Rò rỉ synthetic/real secret trong logs | Chỉ assert keys/codes với dữ liệu giả |

### Trình tự debug

1. Validator có triển khai đúng `supports(...)` không?
2. Fixture là JavaBean có getter cho field đang kiểm tra không?
3. `BeanPropertyBindingResult` được tạo cho **đúng target và objectName** chưa?
4. Đã gọi `validator.validate(...)` chưa?
5. Lỗi được ghi bằng `rejectValue` hay `reject`?
6. `getFieldErrorCount()`/`getGlobalErrorCount()` phản ánh loại lỗi đúng không?
7. Nested path có được phục hồi không?
8. `getCode()` và `getCodes()` có đúng nghĩa không?
9. Đây có phải lỗi conversion, tức cần `DataBinder`, không phải Validator?
10. Nếu lỗi chỉ xảy ra qua HTTP, đã có MockMvc integration test chưa?

## 14. Bài tập tự luyện

**1. Constructor `BeanPropertyBindingResult` có tự gọi `validate` không?** Không.

**2. Tại sao test `supports` riêng?** Vì gọi `validate` trực tiếp không bắt buộc thực hiện supports check.

**3. `rejectValue("seats","seats.min")` tạo gì?** Một `FieldError` trên `seats`.

**4. `reject("booking.range.invalid")` tạo gì?** Một `ObjectError`/global error.

**5. `getAllErrors()` có bao gồm field errors không?** Có, vì `FieldError` kế thừa `ObjectError`.

**6. Chuỗi ba spaces bị `rejectIfEmpty` từ chối không?** Không chỉ vì whitespace; `rejectIfEmptyOrWhitespace` mới xử lý.

**7. Nested field email được lưu dưới tên gì khi push `contact`?** `contact.email`.

**8. Vì sao dùng `try/finally` với `pushNestedPath`?** Bảo đảm pop và không làm hỏng path của lỗi sau.

**9. `getCode()` có phải luôn mã cụ thể nhất không?** Không, nó là default code; `getCodes()[0]` thường mới cụ thể nhất theo resolver mặc định.

**10. Khi client gửi text không chuyển được sang Integer, unit Validator test có đủ không?** Không, cần `DataBinder`/HTTP binding test.

**11. Có cần full Spring ApplicationContext cho `StaticMessageSource` không?** Không, có thể tạo instance và đăng ký messages trong unit test.

**12. Vì sao không serialize nguyên `BindingResult` ra REST API?** Có thể lộ target object, rejected values, thông tin nội bộ/PII.

## 15. Checklist kiểm thử

- [ ] Dùng đúng `org.springframework.validation.BeanPropertyBindingResult`.
- [ ] Chọn `objectName` trùng tên model trong trường hợp cần so message codes.
- [ ] Test `supports` cho đúng và sai class.
- [ ] Mỗi test có một fixture/result mới.
- [ ] Gọi `validate(target,result)` rõ ràng.
- [ ] Có happy-path test không lỗi.
- [ ] Có null, blank, whitespace, zero và các boundary values.
- [ ] Assert field path, code và scope cho lỗi.
- [ ] Assert riêng `getFieldErrors`/`getGlobalErrors` và tổng count.
- [ ] Với nested bean, xử lý null và bảo đảm pop nested path.
- [ ] Dùng `getFieldErrors(field)` khi có nhiều lỗi một field.
- [ ] Không nhầm validation với binding/type conversion.
- [ ] Nếu cần i18n, test `MessageSource` bằng locale rõ.
- [ ] Không phụ thuộc thứ tự errors không được cam kết.
- [ ] Đừng serialize/log rejected values nhạy cảm.
- [ ] Bổ sung DataBinder/MockMvc tests nếu yêu cầu bao trùm HTTP.
- [ ] Chạy `./gradlew test` trên project thực trước khi tuyên bố build đã PASS.

**Ghi nhớ:** `BeanPropertyBindingResult` giúp kiểm thử Spring `Validator` ở mức **object → errors**: dựng JavaBean, tạo result với đúng object name, gọi `validate` và assert những `FieldError`/`ObjectError` được ghi. Nó không tự bind HTTP, không tự kích hoạt Jakarta Bean Validation và không thay thế integration tests. Dùng `DataBinder` cho type conversion, `MessageSource` cho đa ngữ và MockMvc cho Spring MVC lifecycle.

## Tài liệu tham khảo chính thức

- [Spring 6.2 — BeanPropertyBindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/BeanPropertyBindingResult.html)
- [Spring 6.2 — Validator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/Validator.html)
- [Spring — Validation with Spring Validator](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
- [Spring 6.2 — ValidationUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/ValidationUtils.html)
- [Spring 6.2 — Errors Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/Errors.html)
- [Spring 6.2 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring 6.2 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring 6.2 — DefaultMessageCodesResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html)
- [Spring — Resolving Error Codes to Error Messages](https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html)
- [JUnit 5.11.4 — User Guide](https://docs.junit.org/5.11.4/user-guide/)
