# Viết constraint kiểm tra quan hệ giữa hai trường trong Spring Framework

## 1. Bài toán thực hành

Các annotation như `@NotNull`, `@Min`, `@Email` hay `@Past` thường kiểm tra **một giá trị**. Nhưng rất nhiều quy tắc nghiệp vụ chỉ có ý nghĩa khi xem **hai trường cùng lúc**:

- `startDate` phải **trước** `endDate`.
- `minPrice` không được lớn hơn `maxPrice`.
- `password` và `confirmPassword` phải khớp.
- `discountedPrice` không được lớn hơn `originalPrice`.
- `validFrom` và `validUntil` phải tạo một khoảng thời gian hợp lệ.

Một constraint đặt trên trường `endDate` không tự có quyền truy cập thuận tiện, chuẩn hóa vào `startDate` của cùng object; một constraint cấp lớp (*class-level constraint*) được thiết kế chính xác cho loại quan hệ này. Hibernate Validator, provider phổ biến của Jakarta Bean Validation, cũng dùng class-level constraint để mô tả quy tắc dựa trên tương quan giữa nhiều thuộc tính. <https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/>

Bài học xây dựng một constraint có tên `@ValidDateWindow` cho DTO `BookingForm` với quy tắc:

**Khi cả hai ngày đều có mặt và đúng kiểu, `endDate` phải sau `startDate` — không được bằng nhau.**

Ví dụ:

| startDate | endDate | Kết quả |
| --- | --- | --- |
| 2026-11-20 | 2026-11-23 | Hợp lệ |
| 2026-11-20 | 2026-11-20 | Không hợp lệ: hai ngày bằng nhau |
| 2026-11-23 | 2026-11-20 | Không hợp lệ: kết thúc trước bắt đầu |
| 2026-11-20 | null | Vi phạm `@NotNull` của endDate; cross-field validator bỏ qua |
| null | 2026-11-23 | Vi phạm `@NotNull` của startDate; cross-field validator bỏ qua |
| 2026-99-20 | 2026-11-23 | Không parse được startDate từ request; lỗi **binding** khác lỗi quan hệ |

Chúng ta sẽ:

1. Tạo annotation `@ValidDateWindow` theo hợp đồng Jakarta Bean Validation 3.0.
2. Viết `ConstraintValidator<ValidDateWindow, BookingForm>` đọc cả hai trường.
3. Ghi lỗi tại `endDate` bằng `ConstraintValidatorContext#addPropertyNode(...)` thay vì chỉ ở object-level.
4. Tách trách nhiệm null/blank/parse date giữa constraints từng field, formatter và class-level constraint.
5. Chạy chương trình Spring Boot 3.5.6/Java 17 nhận cả HTML form và JSON.
6. Kiểm thử trực tiếp bằng Jakarta `Validator` và HTTP/MVC bằng JUnit 5 + MockMvc.
7. Xử lý validation groups, nested DTO, thông điệp lỗi và những sai lầm thường gặp.

**Điều cần nhớ:** cross-field constraint là **kiểm tra tính hợp lệ**, không phải authorization. Hai ngày hợp lệ không chứng minh người gửi được quyền tạo/sửa booking đó.

## 2. Vì sao không dùng hai @NotNull hoặc một @AssertTrue tùy tiện?

### 2.1. Constraint một trường không đủ

Với:

```java
@NotNull
private LocalDate startDate;

@NotNull
private LocalDate endDate;
```

cả hai thuộc tính có thể khác null nhưng khoảng ngày vẫn sai:

```text
startDate = 2026-11-23
endDate   = 2026-11-20
```

`@NotNull` chỉ bảo đảm sự hiện diện, không kiểm tra tương quan giữa hai trường. `@Future` hay `@FutureOrPresent` cũng chỉ so sánh một thời điểm với đồng hồ, không kiểm tra `endDate` đối với `startDate`.

### 2.2. Có thể dùng @AssertTrue, nhưng không phải lúc nào cũng tốt

Một cách viết nhanh:

```java
@AssertTrue
public boolean isDateWindowValid() {
    return startDate == null
        || endDate == null
        || endDate.isAfter(startDate);
}
```

Đây là **fragment minh họa** trong một class có hai field `startDate` và `endDate`. Cách này có thể dùng cho một rule nhỏ, nhưng có hạn chế:

- Không mô tả rõ tên một **annotation nghiệp vụ tái sử dụng**.
- Violation có thể gắn với bean property `dateWindowValid` thay vì trường người dùng cần sửa.
- Khi cần groups, message templates, metadata hoặc nhiều form cùng quy tắc, logic dễ phân tán.
- Phương thức này có thể bị serializer nhận diện là boolean bean property trong một số cấu hình nếu không kiểm soát, gây rối model/API.

Một custom **class-level constraint** cho phép đặt tên rõ, test độc lập, thay đổi path lỗi và mở rộng chính sách.

### 2.3. Cross-field khác cross-parameter

- **Class-level constraint** nhận một object như `BookingForm` và đọc các trường của object.
- **Cross-parameter constraint** nhận tập tham số của một method/constructor, thường dùng `ConstraintValidator<Annotation,Object[]>` kết hợp `@SupportedValidationTarget(ValidationTarget.PARAMETERS)`.
- **Class-level validation** phù hợp khi dữ liệu request đã được gom trong một DTO.
- **Cross-parameter validation** phù hợp khi quy tắc thực sự liên quan tới nhiều method arguments mà thiết kế không có DTO, nhưng nó có quy tắc target/parameter names khác.

Trong bài này, ta chỉ tạo class-level constraint cho một DTO: đơn giản và dễ kiểm thử hơn.

## 3. Kiến trúc kiểm tra

Luồng request form:

```text
HTTP form request
    |
    v
Spring MVC @ModelAttribute("booking")
    |
    +--> WebDataBinder + ConversionService
    |       "2026-11-20" --> LocalDate
    |       "wrong-date" --> typeMismatch
    |
    v
@Valid BookingForm
    |
    +--> @NotNull(startDate)
    +--> @NotNull(endDate)
    |
    +--> @ValidDateWindow trên BookingForm
              |
              +--> isValid(form, context)
              +--> null? bỏ qua cho @NotNull
              +--> endDate.isAfter(startDate)?
                      | yes -> hợp lệ
                      | no  -> violation ở "endDate"
    |
    v
BindingResult
    |
    +--> lỗi? HTTP 400, không thực hiện thao tác ghi
    +--> hợp lệ? xử lý nghiệp vụ có authorization
```

Với JSON, Jackson giải mã body thành `BookingForm` rồi Bean Validation chạy trên đối tượng. Những lỗi JSON không thể parse có thể phát sinh tại message converter trước khi gọi validator; `@ValidDateWindow` **không phải JSON parser**.

Thực tế Spring MVC còn có cơ chế method validation cho controller method nếu có direct method constraints. Bài mẫu dùng `@Valid` trên DTO và `BindingResult` ngay kế bên để xử lý lỗi đối tượng theo đường rõ ràng.

## 4. Tạo annotation constraint đúng chuẩn

Một custom constraint cần chỉ rõ nơi đặt, runtime retention, class thực thi, message, groups và payload.

```java
package demo.booking;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = DateWindowValidator.class)
@Target({ElementType.TYPE, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidDateWindow {

    String message() default "{demo.dateWindow.invalid}";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

Đây là **file hoàn chỉnh `ValidDateWindow.java`**, được sử dụng trong dự án runnable ở mục 9.

Ý nghĩa từng thành phần:

- `@Documented`: annotation xuất hiện trong generated Javadoc nơi phù hợp.
- `@Constraint(validatedBy=DateWindowValidator.class)`: chỉ định validator implementation. Nếu thiếu, provider có thể không biết phải kiểm tra kiểu object thế nào.
- `@Target(TYPE)`: constraint gắn vào **class**, không phải một thuộc tính `LocalDate`.
- `ANNOTATION_TYPE`: cho phép dùng trong composed constraints nếu cần mở rộng.
- `@Retention(RUNTIME)`: metadata phải sẵn sàng lúc validation chạy.
- `message()`: mã thông điệp; có thể được nội suy từ `ValidationMessages.properties`.
- `groups()`: cho phép chọn validation groups khi ứng dụng dùng nhóm; mặc định `{}` nghĩa là thuộc nhóm `Default` khi gắn không chỉ định.
- `payload()`: metadata mở rộng của Bean Validation; không chứa dữ liệu từ HTTP request.

**Tại sao annotation không chứa `startField` và `endField`?** Ở bản đầu tiên, quy tắc gắn chặt vào DTO `BookingForm`, nên dùng getter typed giúp type-safe, dễ refactor, không cần reflection. Nếu muốn tái sử dụng trên nhiều lớp với field names khác nhau, mục 14 trình bày lựa chọn `@FieldsChronological(from="...",to="...")` và những rủi ro đi kèm.

## 5. Viết ConstraintValidator so sánh đúng hai ngày

```java
package demo.booking;

import java.time.LocalDate;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class DateWindowValidator
        implements ConstraintValidator<ValidDateWindow, BookingForm> {

    @Override
    public boolean isValid(
            BookingForm form,
            ConstraintValidatorContext context) {

        // Jakarta Bean Validation không tự cấm null bean.
        // Coi null là hợp lệ theo quy ước của constraint quan hệ.
        if (form == null) {
            return true;
        }

        LocalDate start = form.getStartDate();
        LocalDate end = form.getEndDate();

        // Null / thiếu trường là việc của @NotNull trên từng field.
        // Không tạo thêm lỗi so sánh làm người dùng khó hiểu.
        if (start == null || end == null) {
            return true;
        }

        // Quy tắc: kết thúc PHẢI sau bắt đầu (strict).
        if (end.isAfter(start)) {
            return true;
        }

        context.disableDefaultConstraintViolation();
        context
            .buildConstraintViolationWithTemplate(
                context.getDefaultConstraintMessageTemplate())
            .addPropertyNode("endDate")
            .addConstraintViolation();

        return false;
    }
}
```

Đây là **file hoàn chỉnh `DateWindowValidator.java`**. Nó không cần Spring annotation `@Component` để Hibernate Validator tự biết validator: Jakarta provider tạo/khởi tạo implementation từ `@Constraint(validatedBy=...)`. Trong Spring Boot, cơ chế `LocalValidatorFactoryBean` được autoconfigure khi Bean Validation starter có mặt.

### 5.1. Vì sao phải kiểm tra null trước?

Nếu `startDate=null`, gọi `end.isAfter(start)` có thể gây `NullPointerException`. Quan trọng hơn, một người dùng chỉ thiếu một ngày không nên mặc định nhận hai lỗi “bắt buộc nhập ngày” **và** “kết thúc phải sau bắt đầu”.

Cách tách trách nhiệm:

- `@NotNull`: cả hai ngày phải có.
- `@DateTimeFormat` hoặc Jackson: input phải parse thành `LocalDate`.
- `@ValidDateWindow`: khi cả hai ngày đã có, kiểm tra quan hệ thời gian.

Đây là **chính sách thiết kế**, không phải yêu cầu mọi class-level constraint phải coi mọi null là hợp lệ. Nếu nghiệp vụ muốn một khoảng ngày không bao giờ thiếu, vẫn nên có `@NotNull` riêng để khách hàng nhận thông báo chính xác.

### 5.2. Vì sao dùng isAfter mà không dùng isBefore?

Với quy tắc “ngày kết thúc sau ngày bắt đầu”:

```java
end.isAfter(start)
```

tương đương:

```java
start.isBefore(end)
```

Giá trị bằng nhau cho `false`. Nếu business cho phép bắt đầu/kết thúc cùng ngày, quy tắc sẽ là:

```java
!end.isBefore(start)
```

Hai biểu thức thể hiện **hai hợp đồng khác nhau**. Trước khi viết constraint, hãy hỏi rõ thời điểm biên có hợp lệ không, có so ngày hay thời điểm (LocalDate vs Instant/ZonedDateTime), và cách xử lý timezone.

Bài lab chọn quy tắc strict vì dễ quan sát bằng test.

### 5.3. Vì sao disableDefaultConstraintViolation?

Khi constraint gắn trên class, nếu chỉ trả `false`, violation mặc định thuộc **object node**. Ví dụ `getPropertyPath().toString()` thường là chuỗi rỗng ở root.

Người dùng lại cần biết **nên sửa trường nào**. Sau khi gọi:

```java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        context.getDefaultConstraintMessageTemplate())
    .addPropertyNode("endDate")
    .addConstraintViolation();
```

violation được đặt tại field path `endDate`. Vì vậy trong Spring MVC, lỗi có thể xuất hiện trong `BindingResult#getFieldErrors("endDate")` và gắn với control endDate trong form.

**Không quên gọi `addConstraintViolation()` ở cuối builder chain**: chỉ tạo builder mà không kết thúc node sẽ không đăng ký violation như mong muốn. Và sau khi vô hiệu hóa default violation, khi trả `false` phải tạo ít nhất một custom violation; nếu không, provider có thể báo lỗi validation do không có violation nào để phát hành.

### 5.4. Tránh phát sinh side effects trong isValid

`isValid(...)` nên là hàm kiểm tra thuần:

- Không sửa `form.setEndDate(...)`.
- Không ghi database hoặc gửi event/email.
- Không thay đổi principal/security context.
- Không ghi nguyên form hoặc giá trị ngày nhạy cảm vào log.
- Không dựa vào mutable state shared của validator khi xử lý nhiều requests.

Một `ConstraintValidator` có thể được provider cache/reuse. Trong ví dụ, validator chỉ sử dụng biến local và là thread-safe về mặt state.

## 6. Tạo DTO có cả field-level và class-level constraints

```java
package demo.booking;

import java.time.LocalDate;

import jakarta.validation.constraints.NotNull;
import org.springframework.format.annotation.DateTimeFormat;

@ValidDateWindow
public class BookingForm {

    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate startDate;

    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate endDate;

    public BookingForm() {
    }

    public BookingForm(LocalDate startDate, LocalDate endDate) {
        this.startDate = startDate;
        this.endDate = endDate;
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
}
```

Đây là **file hoàn chỉnh `BookingForm.java`** trong project.

Tương tác giữa annotations:

- `@NotNull` chạy trên từng `LocalDate` đã có trong object.
- `@DateTimeFormat(iso=ISO.DATE)` hướng dẫn **Spring property formatting/binding**, ví dụ từ form parameter `"2026-11-20"`.
- `@ValidDateWindow` đặt trên class, có quyền đọc **hai trường** sau binding.
- `@Valid` đặt trên controller argument để yêu cầu Bean Validation trên DTO.
- Không thêm `@Validated` trên class/controller chỉ để “bật” annotation này; có thể thay đường method validation và exception semantics của MVC.

**Chú ý JSON:** `@DateTimeFormat` không phải cơ chế chủ đạo để Jackson giải mã `@RequestBody`. Spring Boot Web với Jackson Java Time support thường xử lý ISO `LocalDate` trực tiếp. Nếu JSON time format đặc biệt, kiểm tra Jackson/`@JsonFormat` hay custom deserializer và test riêng. Constraint quan hệ ngày làm việc với **hai giá trị LocalDate đã được tạo**, bất kể dữ liệu đi từ form hay JSON.

## 7. Quan sát lỗi ở cấp object và cấp field

### 7.1. Không chỉ định property node

Giả sử validator chỉ làm:

```java
@Override
public boolean isValid(BookingForm form,
                       ConstraintValidatorContext context) {
    if (form == null
            || form.getStartDate() == null
            || form.getEndDate() == null) {
        return true;
    }
    return form.getEndDate().isAfter(form.getStartDate());
}
```

Đây là **fragment so sánh**, không phải file thay thế. Khi hai ngày sai quan hệ, provider tạo violation class-level mặc định. Property path ở root là empty path; khi được Spring chuyển thành errors, nó có thể xuất hiện như `ObjectError`/global error.

### 7.2. Có addPropertyNode("endDate")

Bản implementation chính tạo:

```text
ConstraintViolation.getPropertyPath() = endDate
ConstraintViolation.getMessageTemplate() = {demo.dateWindow.invalid}
ConstraintViolation.getConstraintDescriptor().getAnnotation()
    = instance của @ValidDateWindow
```

Khi gắn vào Spring MVC `BindingResult`, controller có thể thu được:

```text
field = endDate
code  = ValidDateWindow
```

**Đây là mã lỗi và path mặc định thường thấy**, có thể chịu cấu hình `MessageCodesResolver`/provider. Tests nên assert ít nhất type annotation, path và quy tắc; không dựa vào toàn bộ message tiếng Việt nếu muốn tests ít giòn.

### 7.3. Gắn lỗi vào cả hai field?

Nếu UI yêu cầu đánh dấu cả startDate và endDate khi khoảng sai, validator có thể thêm hai violations:

```java
context.disableDefaultConstraintViolation();
String template = context.getDefaultConstraintMessageTemplate();

context.buildConstraintViolationWithTemplate(template)
    .addPropertyNode("startDate")
    .addConstraintViolation();

context.buildConstraintViolationWithTemplate(template)
    .addPropertyNode("endDate")
    .addConstraintViolation();

return false;
```

Đây là **fragment tùy chọn**, không phải mã chính dùng trong lab. Nếu thêm hai violations, `ConstraintViolation` set có thể có hai entries; số lượng lỗi và HTTP response thay đổi. Chọn một field đích nhất quán với UX; tránh tạo nhiều lỗi trùng nội dung khi người dùng chỉ cần sửa một trường.

### 7.4. Nested object paths

Nếu một object cha chứa:

```java
public class BookingRequest {
    @Valid
    private BookingForm window;
}
```

đây là fragment, cần getters/imports/constructor. Validation trên cha cần `@Valid` để đi vào `window`, và path lỗi class-level từ con có thể thành:

```text
window.endDate
```

Nếu `window == null` thì cascade bỏ qua; thêm `@NotNull` nếu object con là bắt buộc. Không suy luận rằng `@Valid` tự nghĩa là “không được null”.

## 8. Kiểm thử trực tiếp bằng Jakarta Validator

Một chương trình test không cần Spring MVC để khẳng định cross-field logic. Jakarta Validation định nghĩa:

```java
ValidatorFactory factory =
    Validation.buildDefaultValidatorFactory();
Validator validator = factory.getValidator();

Set<ConstraintViolation<BookingForm>> violations =
    validator.validate(form);
```

Đây là fragment, sẽ được mở rộng thành JUnit tests hoàn chỉnh ở mục 10. Quan trọng là `Validator#validate(object)` trả về **Set** các violations; khi có vi phạm thông thường nó **không tự ném ConstraintViolationException**. Exception thường xuất hiện ở tầng method validation hoặc do code chủ động ném.

### 8.1. Test đúng ba thuộc tính của violation

Một test chặt chẽ có thể kiểm tra:

```java
ConstraintViolation<BookingForm> error =
    violations.iterator().next();

assertEquals("endDate",
    error.getPropertyPath().toString());

assertEquals(ValidDateWindow.class,
    error.getConstraintDescriptor()
        .getAnnotation()
        .annotationType());

assertEquals("{demo.dateWindow.invalid}",
    error.getMessageTemplate());
```

Đây là fragment JUnit với imports và setup. Ba assertions chứng minh:

- Violation nằm tại path người dùng cần sửa.
- Violation thực sự do **custom annotation** tạo, không phải `@NotNull`.
- Annotation dùng đúng message template.

Chỉ kiểm tra `assertFalse(violations.isEmpty())` quá yếu: một `@NotNull` trên trường khác có thể làm test pass trong khi cross-field constraint không hề chạy.

### 8.2. Những case phải kiểm tra

| Case | startDate | endDate | Kỳ vọng |
| --- | --- | --- | --- |
| Happy path | 2026-11-20 | 2026-11-23 | Không có violation |
| Hai ngày bằng nhau | 2026-11-20 | 2026-11-20 | 1 violation `ValidDateWindow` ở `endDate` |
| End trước Start | 2026-11-23 | 2026-11-20 | 1 violation `ValidDateWindow` ở `endDate` |
| Thiếu Start | null | 2026-11-23 | 1 `NotNull` tại `startDate` |
| Thiếu End | 2026-11-20 | null | 1 `NotNull` tại `endDate` |
| Thiếu cả hai | null | null | Hai `NotNull`, **không** có cross-field violation |
| LocalDate leap day hợp lệ | 2028-02-28 | 2028-02-29 | Hợp lệ |
| LocalDate không thể parse từ input | "2026-02-30" | 2026-03-01 | Lỗi binding/deserialization; không gọi constructor LocalDate từ text tùy tiện |

Việc dùng ngày cố định giúp tests **không phụ thuộc đồng hồ hệ thống**. Nếu thêm `@FutureOrPresent`, các test cần `ClockProvider` kiểm soát thời gian để tránh fail theo ngày.

## 9. Dự án Java 17 + Spring Boot 3.5.6 chạy được

### 9.1. Cấu trúc thư mục

```text
booking-window-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/booking/
    │   │   ├── BookingApplication.java
    │   │   ├── ValidDateWindow.java
    │   │   ├── DateWindowValidator.java
    │   │   ├── BookingForm.java
    │   │   └── BookingController.java
    │   └── resources/
    │       ├── application.properties
    │       └── ValidationMessages.properties
    └── test/
        └── java/demo/booking/
            ├── DateWindowConstraintTest.java
            └── BookingControllerTest.java
```

Đây là ví dụ **độc lập**. Không cần database; endpoint chỉ minh họa validation và HTTP status. Một API booking thực tế phải dùng service, kiểm tra quyền sở hữu/tình trạng phòng, transaction, đồng bộ dữ liệu và các quy tắc khác trước khi persist.

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>booking-window-lab</artifactId>
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

Ba dependencies phục vụ HTTP/Spring MVC, Jakarta Bean Validation (Hibernate Validator provider), và JUnit 5/MockMvc. Spring Boot 3.5.x sử dụng namespace `jakarta.validation.*`, **không phải `javax.validation.*` của các thế hệ cũ**.

### 9.3. application.properties

```properties
server.address=127.0.0.1
server.port=8080
spring.application.name=booking-window-lab
```

Bài lab chỉ bind loopback; không mở cổng public. Vì không cấu hình authentication/authorization, đừng xem đây là API production.

### 9.4. ValidationMessages.properties

```properties
demo.dateWindow.invalid=Ngày kết thúc phải sau ngày bắt đầu
```

File đặt tại `src/main/resources/ValidationMessages.properties`. Trong Bean Validation, message template `{demo.dateWindow.invalid}` được tìm trong bundle này. Nếu chạy ở môi trường có cấu hình message interpolator khác, nội dung localization có thể khác; hãy assert **template và constraint type** để test logic bền hơn.

### 9.5. BookingApplication.java

```java
package demo.booking;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookingApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookingApplication.class, args);
    }
}
```

Chỉ cần tạo Spring Boot app bình thường. Khi validator provider có trên classpath, Spring Boot cấu hình integration để `@Valid` trong MVC hoạt động. Không cần tự gọi `Validation.buildDefaultValidatorFactory()` trong controller.

### 9.6. ValidDateWindow.java

```java
package demo.booking;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = DateWindowValidator.class)
@Target({ElementType.TYPE, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidDateWindow {

    String message() default "{demo.dateWindow.invalid}";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

### 9.7. DateWindowValidator.java

```java
package demo.booking;

import java.time.LocalDate;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class DateWindowValidator
        implements ConstraintValidator<ValidDateWindow, BookingForm> {

    @Override
    public boolean isValid(
            BookingForm form,
            ConstraintValidatorContext context) {

        if (form == null) {
            return true;
        }

        LocalDate start = form.getStartDate();
        LocalDate end = form.getEndDate();

        if (start == null || end == null) {
            return true;
        }

        if (end.isAfter(start)) {
            return true;
        }

        context.disableDefaultConstraintViolation();
        context
            .buildConstraintViolationWithTemplate(
                context.getDefaultConstraintMessageTemplate())
            .addPropertyNode("endDate")
            .addConstraintViolation();

        return false;
    }
}
```

### 9.8. BookingForm.java

```java
package demo.booking;

import java.time.LocalDate;

import jakarta.validation.constraints.NotNull;
import org.springframework.format.annotation.DateTimeFormat;

@ValidDateWindow
public class BookingForm {

    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate startDate;

    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate endDate;

    public BookingForm() {
    }

    public BookingForm(LocalDate startDate, LocalDate endDate) {
        this.startDate = startDate;
        this.endDate = endDate;
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
}
```

### 9.9. BookingController.java

```java
package demo.booking;

import java.util.stream.Collectors;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/bookings")
public class BookingController {

    @InitBinder("booking")
    void restrictFormBinding(WebDataBinder binder) {
        binder.setAllowedFields("startDate", "endDate");
    }

    @PostMapping(
        path = "/form",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<String> fromForm(
            @Valid @ModelAttribute("booking") BookingForm booking,
            BindingResult errors) {

        return respond(booking, errors);
    }

    @PostMapping(
        path = "/json",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<String> fromJson(
            @Valid @RequestBody BookingForm booking,
            BindingResult errors) {

        return respond(booking, errors);
    }

    private ResponseEntity<String> respond(
            BookingForm booking,
            BindingResult errors) {

        // @ModelAttribute: những field ngoài allowlist có thể bị
        // suppress; không coi hasErrors()==false là chấp nhận hết.
        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                .body("INVALID|suppressed");
        }

        if (errors.hasErrors()) {
            // Demo dùng mã lỗi, KHÔNG xuất rejectedValue hay
            // exception messages chứa input người dùng.
            String codes = errors.getFieldErrors().stream()
                .map(e -> e.getField() + ":" + e.getCode())
                .distinct()
                .sorted()
                .collect(Collectors.joining(","));

            return ResponseEntity.badRequest()
                .body("INVALID|" + codes);
        }

        // Không có database/service: chỉ minh họa kết quả.
        return ResponseEntity.ok(
            "OK|" + booking.getStartDate()
                + "|" + booking.getEndDate());
    }
}
```

**Tại sao `BindingResult` đứng ngay sau `BookingForm`?** Với Spring MVC, đó là vị trí để nhận lỗi binding/validation tại controller. Nếu không có `BindingResult` và không có đường method validation thay thế, object-argument validation lỗi thường dẫn đến `MethodArgumentNotValidException`.

**Tại sao có `@InitBinder("booking")`?** Với form binding, chỉ cho phép property `startDate` và `endDate`. Đây là lớp phòng vệ bổ sung tránh extra form fields. Nhưng với JSON `@RequestBody`, Jackson xử lý deserialization qua HTTP message converter; `setAllowedFields` **không được xem là cách duy nhất chặn over-posting JSON**. Hãy giữ DTO input tối giản và test JSON riêng.

**Tại sao chỉ xuất field + code?** Trong môi trường production, nên trả thông báo phù hợp người dùng hoặc ProblemDetail được thiết kế an toàn; không serialize thẳng `BindingResult` hoặc `FieldError#getRejectedValue()`. Demo cố tình dùng một body text đơn giản để thấy lỗi `endDate:ValidDateWindow` một cách ổn định.

**Giới hạn:** Class-level constraint này chỉ kiểm tra quan hệ ngày. Nó không xác nhận người dùng có quyền tạo booking, còn chỗ trống, hạn mức số đêm, giá, tenant hoặc tính hợp lệ của business state. Các quy tắc đó cần tầng nghiệp vụ và kiểm tra quyền riêng.

## 10. Kiểm thử Jakarta Validation độc lập

### 10.1. File DateWindowConstraintTest.java

```java
package demo.booking;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotNull;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class DateWindowConstraintTest {

    private static ValidatorFactory factory;
    private static Validator validator;

    @BeforeAll
    static void setup() {
        factory = Validation.buildDefaultValidatorFactory();
        validator = factory.getValidator();
    }

    @AfterAll
    static void teardown() {
        factory.close();
    }

    private static LocalDate day(String iso) {
        return LocalDate.parse(iso);
    }

    private static Set<String> paths(BookingForm form) {
        return validator.validate(form).stream()
            .map(v -> v.getPropertyPath().toString())
            .collect(Collectors.toSet());
    }

    @Test
    void acceptsEndDateAfterStartDate() {
        BookingForm form = new BookingForm(
            day("2026-11-20"), day("2026-11-23"));

        assertTrue(validator.validate(form).isEmpty());
    }

    @Test
    void rejectsEqualDatesOnEndDateField() {
        BookingForm form = new BookingForm(
            day("2026-11-20"), day("2026-11-20"));

        Set<ConstraintViolation<BookingForm>> errors =
            validator.validate(form);

        assertEquals(1, errors.size());

        ConstraintViolation<BookingForm> error =
            errors.iterator().next();

        assertEquals("endDate",
            error.getPropertyPath().toString());

        assertEquals(ValidDateWindow.class,
            error.getConstraintDescriptor()
                .getAnnotation()
                .annotationType());

        assertEquals("{demo.dateWindow.invalid}",
            error.getMessageTemplate());
    }

    @Test
    void rejectsReverseDates() {
        BookingForm form = new BookingForm(
            day("2026-11-23"), day("2026-11-20"));

        assertEquals(Set.of("endDate"), paths(form));
    }

    @Test
    void missingStartIsOnlyNotNullViolation() {
        BookingForm form = new BookingForm(
            null, day("2026-11-23"));

        Set<ConstraintViolation<BookingForm>> errors =
            validator.validate(form);

        assertEquals(1, errors.size());
        ConstraintViolation<BookingForm> error =
            errors.iterator().next();

        assertEquals("startDate",
            error.getPropertyPath().toString());

        assertEquals(NotNull.class,
            error.getConstraintDescriptor()
                .getAnnotation()
                .annotationType());
    }

    @Test
    void missingEndIsOnlyNotNullViolation() {
        BookingForm form = new BookingForm(
            day("2026-11-20"), null);

        assertEquals(Set.of("endDate"), paths(form));
    }

    @Test
    void missingBothDatesProducesTwoFieldErrors() {
        BookingForm form = new BookingForm(null, null);

        assertEquals(
            Set.of("startDate", "endDate"),
            paths(form));
    }

    @Test
    void leapYearDateCanBeValid() {
        BookingForm form = new BookingForm(
            day("2028-02-28"), day("2028-02-29"));

        assertTrue(validator.validate(form).isEmpty());
    }

    @Test
    void validatePropertyDoesNotEvaluateClassLevelRule() {
        BookingForm form = new BookingForm(
            day("2026-11-23"), day("2026-11-20"));

        assertTrue(
            validator.validateProperty(
                form, "endDate").isEmpty());

        // Full bean validation mới kiểm tra @ValidDateWindow.
        assertFalse(validator.validate(form).isEmpty());
    }
}
```

Bộ test có **8 phương thức**. Chúng không mở HTTP server, không gọi Spring MVC, không phụ thuộc thời gian hiện tại. Trọng tâm là kiểm tra annotation, property path, null policy và kết quả từ Jakarta Validator provider thật.

**Chú ý:** `validateProperty(form,"endDate")` chỉ kiểm tra những constraints đặt trên thuộc tính `endDate`; không tự gọi class-level constraint. Vì vậy nếu cần xác minh quan hệ hai field, hãy dùng `validator.validate(form)` trên toàn object. `validateValue(BookingForm.class,"endDate",date)` cũng không có đủ hai thuộc tính để kiểm tra tương quan này.

### 10.2. Phân biệt code và message

Đối với `@ValidDateWindow`, property path được khẳng định là `endDate`, còn message template là `{demo.dateWindow.invalid}`. Khi message được nội suy, `getMessage()` có thể thành:

```text
Ngày kết thúc phải sau ngày bắt đầu
```

Test logic nên assert **message template**, annotation type và field path thay vì hardcode một thông điệp localized dễ thay đổi. Nếu ứng dụng cần kiểm thử localization tiếng Việt, hãy tạo test riêng với locale/message interpolation được cấu hình rõ.

## 11. Kiểm thử HTTP qua MockMvc

### 11.1. File BookingControllerTest.java

```java
package demo.booking;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BookingControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validFormReturnsOk() throws Exception {
        mvc.perform(post("/bookings/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("startDate", "2026-11-20")
                .param("endDate", "2026-11-23"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "OK|2026-11-20|2026-11-23"));
    }

    @Test
    void reversedFormDatesReturnFieldViolation()
            throws Exception {

        mvc.perform(post("/bookings/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("startDate", "2026-11-23")
                .param("endDate", "2026-11-20"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(
                "INVALID|endDate:ValidDateWindow"));
    }

    @Test
    void equalFormDatesAreRejected() throws Exception {
        mvc.perform(post("/bookings/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("startDate", "2026-11-20")
                .param("endDate", "2026-11-20"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(
                "INVALID|endDate:ValidDateWindow"));
    }

    @Test
    void missingEndDateIsNotNullFailure()
            throws Exception {

        mvc.perform(post("/bookings/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("startDate", "2026-11-20"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(
                "INVALID|endDate:NotNull"));
    }

    @Test
    void malformedStartDateIsBindingFailure()
            throws Exception {

        mvc.perform(post("/bookings/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("startDate", "invalid-date")
                .param("endDate", "2026-11-23"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(
                containsString("startDate:typeMismatch")));
    }

    @Test
    void extraFormFieldIsExplicitlyRejected()
            throws Exception {

        mvc.perform(post("/bookings/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("startDate", "2026-11-20")
                .param("endDate", "2026-11-23")
                .param("price", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(
                "INVALID|suppressed"));
    }

    @Test
    void validJsonUsesSameClassLevelConstraint()
            throws Exception {

        mvc.perform(post("/bookings/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"startDate\":\"2026-11-20\","
                    + "\"endDate\":\"2026-11-23\"}"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "OK|2026-11-20|2026-11-23"));
    }

    @Test
    void reversedJsonReportsEndDateViolation()
            throws Exception {

        mvc.perform(post("/bookings/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"startDate\":\"2026-11-23\","
                    + "\"endDate\":\"2026-11-20\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(
                "INVALID|endDate:ValidDateWindow"));
    }
}
```

Bộ test gồm **8 HTTP/MVC scenarios**: valid form, ngày đảo, ngày bằng, thiếu endDate, ngày sai định dạng, field thừa, JSON hợp lệ và JSON đảo ngày. Một integration test quan trọng hơn unit test ở chỗ nó xác minh Spring Boot đã tạo converter/validator và dùng `@Valid` ở đúng controller boundary.

Nếu thay controller để có direct constraints trên method parameters (ví dụ thêm `@Min` lên một `@RequestParam`), Spring MVC 6.1+ có thể dùng whole-method validation và exception flow khác. Khi ấy hãy điều chỉnh test/handler theo `HandlerMethodValidationException` thay vì giả định mọi lỗi đều đi qua cùng `BindingResult`.

### 11.2. Điều cần nhìn vào test malformedStartDate

Không phải mọi request sai ngày đều do `ValidDateWindow` phát hiện. Với `"invalid-date"`, Spring MVC không thể convert text thành `LocalDate`; `BindingResult` có thể chứa lỗi `typeMismatch` trên `startDate`.

Vì sau khi bind lỗi, `startDate` là null trong form mới, class-level validator của chúng ta **cố ý bỏ qua** phép so sánh để tránh báo thêm lỗi quan hệ. `@NotNull` có thể tạo một lỗi bổ sung tùy pipeline/provider; test chỉ assert chắc chắn có `startDate:typeMismatch` thay vì yêu cầu toàn bộ danh sách errors chỉ chứa một phần tử.

**Đây là điểm thực hành quan trọng:** cùng một người dùng thấy “ngày bắt đầu không hợp lệ”, nhưng developer cần biết nó là **lỗi parse**, **lỗi thiếu**, hay **lỗi so sánh** để kiểm tra đúng lớp.

## 12. Chạy project và kiểm tra thủ công

### 12.1. Yêu cầu

- JDK 17 hoặc mới hơn tương thích Spring Boot 3.5.x.
- Maven 3.x.
- Kết nối Maven repository lần đầu để tải dependencies.
- Không cần H2/PostgreSQL hoặc server riêng.

### 12.2. Chạy JUnit

Trong thư mục có `pom.xml`:

```bash
mvn -q test
```

Kết quả thành công được đánh giá bằng **exit code 0**. Với cờ `-q`, Maven có thể không in dòng tóm tắt cố định; báo cáo Surefire nằm tại `target/surefire-reports/`. Có tổng cộng **16 phương thức test** trong hai lớp thuộc mã bài học: 8 bài cho Jakarta Validator, 8 bài cho MVC.

Lưu ý: các assertions và output kỳ vọng trong README được xây dựng theo API Spring/Jakarta/Hibernate Validator đã mô tả, **không phải biên bản đã chạy Maven test trong môi trường này**. Khi áp dụng, cần chạy test thực tế trên phiên bản dependencies của dự án.

### 12.3. Chạy ứng dụng

```bash
mvn -q spring-boot:run
```

Server local:

```text
http://127.0.0.1:8080
```

### 12.4. Case 1 — form hợp lệ

```bash
curl -i -X POST \
  'http://127.0.0.1:8080/bookings/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'startDate=2026-11-20' \
  --data-urlencode 'endDate=2026-11-23'
```

Kỳ vọng status `200 OK` và body chính xác do controller tạo:

```text
OK|2026-11-20|2026-11-23
```

### 12.5. Case 2 — ngày kết thúc trước ngày bắt đầu

```bash
curl -i -X POST \
  'http://127.0.0.1:8080/bookings/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'startDate=2026-11-23' \
  --data-urlencode 'endDate=2026-11-20'
```

Kỳ vọng `400 Bad Request` với body:

```text
INVALID|endDate:ValidDateWindow
```

Điều đó chứng minh custom validator so sánh hai ngày và lỗi được gắn vào `endDate` thông qua property node thay vì global error.

### 12.6. Case 3 — thiếu endDate

```bash
curl -i -X POST \
  'http://127.0.0.1:8080/bookings/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'startDate=2026-11-20'
```

Kỳ vọng:

```text
INVALID|endDate:NotNull
```

Đây là lỗi từng field, không phải `ValidDateWindow`. Sự phân biệt giúp trả lời “thiếu ngày” khác với “hai ngày sai quan hệ”.

### 12.7. Case 4 — JSON cũng có quan hệ ngày sai

```bash
curl -i -X POST \
  'http://127.0.0.1:8080/bookings/json' \
  -H 'Content-Type: application/json' \
  -d '{"startDate":"2026-11-20","endDate":"2026-11-20"}'
```

Kỳ vọng:

```text
INVALID|endDate:ValidDateWindow
```

JSON parser/Jackson đọc được hai ISO dates, và Bean Validation chạy trên `BookingForm`. Nếu JSON chứa một ngày không thể parse, lỗi có thể phát sinh **trước** khi controller nhận DTO, qua `HttpMessageNotReadableException`; ví dụ controller này không định nghĩa custom handler cho JSON malformed.

### 12.8. Case 5 — field thừa trong form

```bash
curl -i -X POST \
  'http://127.0.0.1:8080/bookings/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'startDate=2026-11-20' \
  --data-urlencode 'endDate=2026-11-23' \
  --data-urlencode 'price=0'
```

Kỳ vọng:

```text
INVALID|suppressed
```

Allowlist của form binder chỉ chấp nhận startDate/endDate. Field `price` bị suppress và handler chủ động từ chối. Đừng tự đồng nhất `BindingResult#hasErrors()` với kết luận mọi input client gửi đều được chấp nhận.

## 13. Thiết kế null policy, parse policy và validation groups

### 13.1. Null policy là chủ đích, không phải mặc định bắt buộc

Có hai lựa chọn:

- **Skip null trong cross-field validator** (ví dụ chính): `@NotNull` quản lý thiếu trường; validator so sánh chỉ chạy khi dữ liệu đủ.
- **Đánh lỗi cross-field cả khi null**: có thể phù hợp cho một business rule atomic, nhưng dễ tạo nhiều lỗi khó hiểu hoặc nuốt lỗi nguyên nhân thật.

Trong form có hai trường bắt buộc, việc tách `@NotNull` và `@ValidDateWindow` thường dễ quản lý UX, error codes và tests hơn.

### 13.2. Giá trị rỗng khác không parse được

Khi Spring nhận:

```text
startDate=
```

conversion/formatter có thể coi là null hoặc có lỗi parse tùy cấu hình. Khi nhận:

```text
startDate=2026-99-20
```

nó là text sai cú pháp ngày ISO và có thể tạo `typeMismatch`. Trong trường hợp hai giá trị đã là `LocalDate` hợp lệ nhưng thứ tự sai, custom constraint mới tạo `ValidDateWindow`.

Không để custom validator đi parse raw strings. Phân công:

1. HTTP message converter / form formatter: giải mã và chuyển kiểu.
2. Field constraints: điều kiện từng thuộc tính.
3. Class-level constraint: quan hệ nhiều thuộc tính.
4. Service/domain: authorization, trạng thái, transaction và quy tắc ngoài DTO.

### 13.3. Groups: chỉ chạy constraint khi nhóm được chọn

Trong ví dụ chính, `@ValidDateWindow` thuộc `Default`. Nếu workflow có hai bước `Draft` và `Submit`, bạn có thể đặt constraint vào Submit:

```java
public interface SubmitChecks {}

@ValidDateWindow(groups = SubmitChecks.class)
public class BookingForm {
    // Các fields...
}
```

Đây là **fragment minh họa**; không thay các source files chính. Khi dùng group:

```java
validator.validate(form, SubmitChecks.class);
```

thì các constraints thuộc Default (như `@NotNull` không ghi group) **không tự chạy** cùng SubmitChecks. Nếu cần cả hai:

```java
validator.validate(
    form, Default.class, SubmitChecks.class);
```

hoặc định nghĩa group sequence theo policy. Với Spring MVC, `@Validated(SubmitChecks.class)` trên một DTO argument có thể chọn group; `@Valid` thường dùng Default. Đừng dùng group `Admin` như bằng chứng người gọi có quyền admin — groups không phải authorization.

### 13.4. Group sequence nếu cần kiểm tra theo thứ tự

Ví dụ conceptual:

```java
@GroupSequence({
    Default.class,
    SubmitChecks.class
})
public interface CompleteChecks {}
```

Trong project có `Default` và `SubmitChecks` đã khai báo/import, đây là fragment chứ không phải full file. Khi validate với `CompleteChecks`, nếu Default có lỗi, provider bỏ qua SubmitChecks trong sequence đó. Điều này có thể hữu ích khi muốn tránh chạy cross-field constraint trước khi các điều kiện cơ bản đạt, nhưng trong ứng dụng hiện tại null-safe validator đã đủ rõ.

**Quan trọng:** Khi định nghĩa `@GroupSequence` ngay trên một bean class để *redefine Default group sequence*, có các quy tắc khác, thường phải chứa chính bean class. Không tự bê nguyên sequence interface sang annotation cấp class mà không đọc Jakarta spec.

## 14. Constraint tổng quát cho hai tên trường: khi nào nên làm?

Bài mẫu viết validator type-safe cho `BookingForm`. Khi nhiều DTO có cặp LocalDate khác tên, có thể thiết kế:

```java
@FieldsChronological(
    from = "availableFrom",
    to = "availableUntil")
public class AvailabilityForm {
    private LocalDate availableFrom;
    private LocalDate availableUntil;
}
```

Đây là **một interface thiết kế giả định**, không phải annotation đã được định nghĩa trong mã runnable. Nếu triển khai generic validator, phải giải quyết:

- Đọc property qua `BeanWrapper`/getter metadata hoặc reflection có kiểm soát.
- Khởi tạo và cache field names từ annotation trong `initialize(...)`.
- Khi property không tồn tại/sai kiểu, báo lỗi configuration rõ ràng, không nuốt exception hoặc mặc định cho qua.
- Không để client truyền field names tùy ý tới annotation/validator.
- Kiểm tra null/empty; tránh phân biệt cách compare âm thầm.
- Dùng `addPropertyNode(to)` với property name đã xác minh có tồn tại.
- Dùng `Comparable`/specific date type có type-safety; đừng so strings dạng ngày theo thứ tự từ điển trừ khi contract thực sự bảo đảm canonical sortable representation.
- Nếu names có nested paths, dùng property nodes tương ứng thay vì đưa chuỗi có dấu chấm trực tiếp vào một node; `addPropertyNode` chỉ nhận tên property node đơn.
- Không dựa vào client input/reflection để truy cập thuộc tính nhạy cảm.

**Khi nào không nên generic hóa?** Nếu chỉ có một DTO và một rule, validator typed như `DateWindowValidator` dễ hiểu, khó mắc lỗi runtime và dễ refactor hơn. Chỉ tạo generic constraint khi số lượng use cases thực sự biện minh cho complexity.

## 15. Một ví dụ khác: password và confirmPassword

Quan hệ hai trường không chỉ là ngày. Với thay đổi mật khẩu, bạn có thể có:

```java
public class ChangePasswordForm {
    @NotBlank
    private String newPassword;

    @NotBlank
    private String confirmPassword;

    // getters/setters
}
```

Và một class-level validator kiểm tra:

```java
boolean same = Objects.equals(
    form.getNewPassword(),
    form.getConfirmPassword());
```

Đây là **fragments**, chưa là class có thể biên dịch độc lập. Nếu tạo `@PasswordsMatch`, hãy đặt violation vào `confirmPassword` bằng `addPropertyNode("confirmPassword")`, tương tự `endDate`.

Tuy nhiên:

- Không log giá trị password hoặc rejected values.
- Không đưa plaintext password vào validation message.
- Password strength/breach checks là quy tắc khác, không thay phép so khớp.
- Authorization, reauthentication, CSRF và safe password hashing phải được xử lý riêng.
- Không dùng `String.equalsIgnoreCase(...)` để so mật khẩu. Case sensitivity là quan trọng.
- Không nên biến một password form thành JPA entity để bind trực tiếp.

Phần chính của bài thực hành vẫn là cặp LocalDate, vì giúp giải thích quan hệ và HTTP binding một cách rõ ràng.

## 16. Lỗi thường gặp khi viết constraint hai trường

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Validator không chạy | Quên gắn `@ValidDateWindow` trên class, thiếu Bean Validation provider hoặc chưa kích hoạt validation | Kiểm tra annotation, `@Valid` và provider trên classpath |
| `UnexpectedTypeException` | ConstraintValidator generic type không khớp target bean | Dùng `ConstraintValidator<ValidDateWindow, BookingForm>` cho đúng DTO |
| `ConstraintDefinitionException` | Annotation thiếu `message/groups/payload` hoặc sai retention/target | Theo Jakarta Validation constraint contract |
| Lỗi chỉ hiện global/object | Chỉ return false, không tạo property node | Gọi `disableDefaultConstraintViolation()` và `addPropertyNode("endDate")` |
| Không có violation sau khi disable default | Quên `addConstraintViolation()` | Kết thúc builder chain và return false |
| Form thiếu startDate gây NPE | Không xử lý null trước `isAfter` | Null guard; để `@NotNull` báo missing |
| Ngày bằng nhau vẫn được chấp nhận | Dùng inclusive comparison thay vì strict | Quyết định `end.isAfter(start)` hay `!end.isBefore(start)` theo business |
| Sai định dạng ngày nhưng mong custom validator báo | Parse failure xảy ra trước khi có LocalDate | Kiểm tra `typeMismatch`/HttpMessageNotReadableException |
| Test chỉ chạy `validateProperty(endDate)` | Không đánh giá class-level constraint | Gọi `validator.validate(form)` |
| Test pass vì @NotNull chứ không phải custom | Chỉ assert `violations.size()>0` | Assert annotation type, property path và template |
| @Valid trên input JSON nhưng không thấy rule | Annotation class-level chưa đặt hoặc group không chạy | Kiểm tra `@ValidDateWindow` và groups |
| Dùng @Validated(Submit) làm @NotNull biến mất | Default và Submit là nhóm độc lập | Chọn cả groups/sequence |
| Bean cấp lớp bị validate hai lần | Có direct method constraints hoặc validator tự gọi thêm lần | Hiểu MVC 6.1+ method validation và flow |
| Lỗi HTTP không đúng | BindingResult không đứng liền sau DTO, có advice override hoặc method validation path khác | Test MockMvc theo controller signature |
| Lộ rejected values | Serialize toàn bộ `BindingResult`/exception | Trả mã lỗi được duyệt, không xuất input bí mật |
| Validation dùng database tùy tiện | Side effects trong `isValid` hoặc transaction không rõ | Chuyển quy tắc phụ thuộc DB sang service/domain |
| DTO valid nhưng người dùng không có quyền sửa | Nhầm validation với authorization | Kiểm tra principal, tenant và resource ở service |
| Validation bỏ qua nested BookingForm | Parent thiếu `@Valid` | Thêm cascade ở đúng thuộc tính/collection element |
| Kết quả test phụ thuộc giờ/ngày hiện tại | Dùng `@Future` mà không cố định clock | Test LocalDate cố định hoặc `ClockProvider` |
| Dùng @ScriptAssert tùy tiện | Phụ thuộc script engine, khó kiểm soát | Custom typed ConstraintValidator rõ logic hơn |

## 17. Checklist code review cho class-level constraint

1. Annotation đặt ở `TYPE` và có `@Constraint(validatedBy=...)`?
2. Có `@Retention(RUNTIME)` và ba members `message/groups/payload` đúng chữ ký?
3. Generic type của validator chính là loại DTO nó được gắn lên?
4. Có rõ quy tắc strict/inclusive, đơn vị thời gian, timezone và inclusive boundary?
5. Null được xử lý rõ và tránh NPE?
6. Field-level constraints bổ sung cho các trường bắt buộc đã được khai báo?
7. Với lỗi quan hệ, `getPropertyPath()` có đúng trường UI cần sửa?
8. Builder có `disableDefaultConstraintViolation()` và `addConstraintViolation()` đủ?
9. Message template ổn định, không đưa dữ liệu nhạy cảm vào thông điệp?
10. Validator không thay state, không ghi database hoặc phát side effects?
11. Có test happy path, equal, reversed, missing first, missing second, both missing?
12. Có test trực tiếp provider thực và assert annotation type/path/message template?
13. Có test `validateProperty()` để người đọc hiểu scope class-level?
14. MVC integration tests có phân biệt form conversion và JSON deserialization?
15. `BindingResult` có đứng ngay sau DTO khi muốn xử lý lỗi tại controller?
16. Có cho phép input fields thừa hoặc mass assignment ngoài DTO không?
17. Khi dùng groups, Default/Submit/sequence có được kiểm thử riêng?
18. Nested DTO có `@Valid` tại đúng association không?
19. Có loại bỏ hardcoded thời gian hiện tại gây flaky tests không?
20. Sau validation pass, business service vẫn kiểm tra authorization và các invariants còn lại?

## 18. Bài tập mở rộng

### Bài tập A — thay strict rule thành inclusive rule

Sửa constraint để khoảng ngày cùng ngày vẫn hợp lệ:

```java
return !end.isBefore(start);
```

Cập nhật test `rejectsEqualDatesOnEndDateField()` thành test chấp nhận bằng nhau. Đảm bảo test ngày đảo vẫn fail. Sau khi thay business rule, điều quan trọng là **sửa tests theo contract mới**, không chỉ xóa assertions đỏ.

### Bài tập B — ràng buộc giá min/max

Tạo DTO:

```java
public class SearchPriceForm {
    private BigDecimal minPrice;
    private BigDecimal maxPrice;
}
```

Quy tắc: nếu có cả hai, `minPrice.compareTo(maxPrice) <= 0`. Cân nhắc bổ sung `@DecimalMin("0")` cho từng field. Trường `null` có ý nghĩa khác nhau: “không giới hạn dưới” hoặc “không giới hạn trên”, vì đây là filter tùy chọn, không nhất thiết dùng `@NotNull`.

Đây là bài tập minh họa, không có trong source files runnable.

### Bài tập C — custom violation ở hai nodes

Thử tạo cả `startDate` và `endDate` violations khi quan hệ sai. Kiểm tra số lượng lỗi, property paths và API response. Sau đó đánh giá UX: người dùng nên nhận một hay hai thông báo? Đừng để việc tạo hai `FieldError` gây hiểu nhầm là có hai lỗi nghiệp vụ độc lập.

### Bài tập D — nested DTO

Thêm `BookingRequest` chứa `@Valid BookingForm window` và xác nhận path `window.endDate` khi validate toàn request. Sau đó bỏ `@Valid` và so sánh. Nếu `window=null`, chứng minh cascade không tạo `window.endDate` error; thêm `@NotNull` nếu yêu cầu window bắt buộc.

### Bài tập E — validation groups

Chuyển `@ValidDateWindow` sang nhóm `SubmitChecks` và dùng `@Validated(SubmitChecks.class)` ở endpoint submit. Thêm test chứng minh Default constraints không tự chạy, rồi thiết kế `@GroupSequence` hoặc chọn nhiều groups để tránh thiếu kiểm tra bắt buộc.

## 19. Tóm tắt

Khi một quy tắc phụ thuộc **mối quan hệ giữa hai thuộc tính của cùng một DTO**, hãy tạo **class-level custom Bean Validation constraint**:

- Annotation `@ValidDateWindow` được đặt trên `BookingForm`.
- Implementation `ConstraintValidator<ValidDateWindow, BookingForm>` đọc cả `startDate` và `endDate`.
- `@NotNull` kiểm tra thiếu dữ liệu; formatter/Jackson kiểm tra dữ liệu có parse được không; custom validator chỉ so sánh **hai ngày hợp lệ về kiểu**.
- Nếu quan hệ sai, `ConstraintValidatorContext` với `addPropertyNode("endDate")` đưa lỗi tới đúng field thay vì chỉ tạo lỗi global.
- `validator.validate(form)` là phép thử class-level constraint; `validateProperty(form,"endDate")` không thay thế nó.
- Spring MVC có thể kích hoạt cùng constraint cho cả `@ModelAttribute` và `@RequestBody` qua `@Valid`, nhưng binding errors và JSON deserialization errors cần được xử lý riêng.
- Tests nên đối chiếu annotation type, property path, null semantics và HTTP status; không chỉ kiểm tra `hasErrors()`.

Đây là mô hình có thể áp dụng cho khoảng thời gian, khoảng giá và xác nhận mật khẩu. Dù validation đúng, **phân quyền, bảo mật dữ liệu và business transaction** vẫn là những trách nhiệm riêng.

## 20. Tài liệu tham khảo

- Hibernate Validator 8 Reference Guide — Class-level constraints, custom constraints và custom property paths: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Jakarta Bean Validation 3.0 specification — Constraint declaration, class-level constraints, custom violation path và groups: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Bean Validation 3.0 API — `ConstraintValidator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintValidator.html
- Jakarta Bean Validation 3.0 API — `ConstraintValidatorContext`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintValidatorContext.html
- Jakarta Bean Validation 3.0 API — `Validator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Validator.html
- Spring Framework 6.2 — Bean Validation integration: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — Validation in Spring MVC controller methods: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — `@ModelAttribute` binding/`BindingResult`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — `@RequestBody`, JSON conversion and validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Boot 3.5 — Validation integration: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/