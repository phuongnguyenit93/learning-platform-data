# WebMvcConfigurer.addFormatters và getValidator — cấu hình binder trong Spring MVC

## Mục tiêu bài học

Trong Spring MVC, người dùng gửi dữ liệu dạng chuỗi qua form hoặc query string, còn controller muốn nhận các đối tượng Java có kiểu như `LocalDate`, `BigDecimal`, enum, mã định danh nghiệp vụ hoặc một form DTO. Để đi từ chuỗi đến đối tượng và quyết định đối tượng có hợp lệ hay không, Spring sử dụng hai cơ chế **khác nhau nhưng thường nối tiếp nhau**:

1. **Conversion / formatting:** biến dữ liệu nguồn thành đúng kiểu Java và hỗ trợ in lại thành chuỗi. Hook `WebMvcConfigurer.addFormatters(FormatterRegistry)` dùng để đăng ký các `Converter`, `Formatter` và bộ đăng ký định dạng cho Spring MVC.
2. **Validation:** kiểm tra các quy tắc trên đối tượng đã bind như `@NotNull`, `@NotBlank`, `@Min`, các constraint Jakarta Bean Validation và những Spring `Validator` được cấu hình. Hook `WebMvcConfigurer.getValidator()` chọn **global Validator** mà hạ tầng MVC dùng trong các tình huống như `@Valid @ModelAttribute` và `@Valid @RequestBody`.

**Một formatter không phải một validator.** Formatter biết rằng `"bk-a12"` có thể trở thành `BookingCode("BK-A12")`; validator mới biết `contactName` không được để trống, số ghế phải dương và mã có bắt buộc hiện diện hay không.

Sau bài này, bạn sẽ:

- Phân biệt `addFormatters(...)`, `getValidator()`, `@InitBinder` và các annotation `@Valid`/`@Validated`.
- Hiểu vòng đời `WebDataBinder`, `FormattingConversionService`, `BindingResult` và `FieldError`.
- Chọn đúng `Converter<S,T>`, `Formatter<T>`, `FormatterRegistrar`, `AnnotationFormatterFactory<A>`.
- Giữ được Bean Validation khi thay global validator bằng `LocalValidatorFactoryBean`.
- Viết ứng dụng Spring Boot 3 / Java 17+ gồm custom `Formatter<BookingCode>`, `WebMvcConfigurer`, form controller, Thymeleaf và MockMvc tests.
- Tránh nhầm lẫn giữa MVC binding với JSON/Jackson, Spring Boot conversion service, WebFlux và AOP method validation.

## 1. Bức tranh tổng thể: binding khác validation

Giả sử form gửi:

~~~http
POST /reservations
Content-Type: application/x-www-form-urlencoded

code=bk-a12&contactName=Lan&seats=3
~~~

DTO phía server:

~~~java
public class ReservationForm {
    private BookingCode code;
    private String contactName;
    private Integer seats;

    // getters và setters
}
~~~

Spring MVC không thể trực tiếp gán chuỗi `"bk-a12"` vào field `BookingCode code` nếu chưa có quy tắc chuyển đổi phù hợp. `addFormatters` cung cấp quy tắc đó.

Một thứ tự logic điển hình:

~~~text
HTTP request parameters / form fields
    |
    v
@ModelAttribute("reservationForm")
    |
    v
WebDataBinder
    |-- constructor/property binding
    |-- FormattingConversionService
    |     |-- Converter / Formatter / @DateTimeFormat...
    |     '-- "bk-a12" → BookingCode("BK-A12")
    |
    |-- lỗi conversion → FieldError, typeMismatch
    |
    v
@Valid / @Validated trên controller argument
    |
    v
global Validator (getValidator() hoặc mặc định)
    |-- @NotNull(code)
    |-- @NotBlank(contactName)
    '-- @Min(1)(seats)
    |
    v
BindingResult
    |-- lỗi → controller trả lại form, th:errors
    '-- hợp lệ → service / redirect
~~~

Hai nhánh lỗi cần phân biệt:

| Input | Conversion | Validation | Lỗi điển hình |
| --- | --- | --- | --- |
| `code=bk-a12` | Formatter tạo `BookingCode("BK-A12")` | `@NotNull` đạt | Không lỗi |
| `code=WRONG` | Formatter không parse được | Có thể kiểm tra thêm property còn null | `typeMismatch` trên `code` |
| `contactName=` | Chuỗi được bind bình thường | `@NotBlank` thất bại | `NotBlank` |
| `seats=0` | Chuỗi được chuyển thành Integer 0 | `@Min(1)` thất bại | `Min` |
| `seats=abc` | Không chuyển thành Integer | Không thể gán giá trị thô vào field Integer | `typeMismatch` |
| Thiếu hoàn toàn `code` | Property giữ null | `@NotNull` thất bại | `NotNull` |

**Không** kỳ vọng `@Valid` tự thay đổi dữ liệu thành đúng kiểu hay tự biến `"WRONG"` thành mã hợp lệ. Ngược lại, dù formatter parse được chuỗi, đối tượng vẫn có thể vi phạm các ràng buộc khác.

## 2. WebMvcConfigurer là gì?

`org.springframework.web.servlet.config.annotation.WebMvcConfigurer` là giao diện cấu hình Spring MVC với nhiều **default methods**. Trong ứng dụng Spring Boot dùng MVC, bạn thường viết một class `@Configuration implements WebMvcConfigurer` để điều chỉnh một phần cơ chế mặc định, thay vì thay thế cả MVC infrastructure.

Ví dụ khung:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.validation.Validator;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        // Đăng ký converter / formatter bổ sung.
    }

    @Override
    public Validator getValidator() {
        // Trả validator muốn MVC dùng.
        return null; // Giữ validator mặc định.
    }
}
~~~

Đây là **snippet giải thích API**, không phải ứng dụng độc lập. Hai phương thức có loại tham số, return type và phạm vi hoàn toàn khác nhau:

| Hook | Đầu vào/đầu ra | Vai trò | Khi nào cần |
| --- | --- | --- | --- |
| `addFormatters(FormatterRegistry)` | Nhận registry, return `void` | Thêm chiến lược convert/format | Kiểu miền riêng, định dạng nhập/xuất, formatters dùng chung |
| `getValidator()` | Return Spring `Validator` hoặc `null` | Chọn global MVC Validator | Muốn thay hoặc chủ động chọn validator toàn cục |
| `@InitBinder` | Nhận `WebDataBinder` | Tùy biến binder theo controller/model attribute | Allowed fields, validator riêng, custom editor cục bộ |
| `@Valid` / `@Validated` | Đặt trên argument hoặc bean properties | Yêu cầu validation và chọn groups | Kiểm tra nội dung object sau binding |

Phân biệt hai bước **đăng ký cấu hình** và **xử lý từng request**: Spring gọi `addFormatters(...)` khi thiết lập MVC conversion service. Đó không phải callback được gọi một lần cho mỗi field/request. Tương tự, `getValidator()` chọn validator cho infrastructure, không phải function để bạn đọc/kiểm tra dữ liệu request ngay bên trong method này.

### Tránh bật @EnableWebMvc chỉ để thêm Formatter

Trong Spring Boot:

~~~java
@Configuration
public class WebConfig implements WebMvcConfigurer {
    // Tùy biến những gì cần.
}
~~~

Thông thường là đủ. `@EnableWebMvc` chuyển quyền điều khiển cấu hình MVC về phía ứng dụng và có thể làm mất nhiều thiết lập auto-configuration của Spring Boot (static resources, converters, view configuration…). Không cần thêm `@EnableWebMvc` chỉ để thực thi `addFormatters` hoặc `getValidator`.

Nếu dự án cố ý muốn điều khiển toàn bộ Spring MVC, khi đó mới đánh giá `@EnableWebMvc` hoặc kế thừa `WebMvcConfigurationSupport`, cùng trách nhiệm cấu hình hạ tầng tương ứng.

## 3. addFormatters: khi nào dùng Converter, Formatter?

`FormatterRegistry` mở rộng registry của Spring Conversion Service, vì vậy bạn có thể đăng ký nhiều loại chiến lược.

### 3.1. Converter<S,T> — chuyển một chiều

`Converter<String, BookingCode>` thích hợp khi cần một phép biến đổi đơn giản từ chuỗi sang kiểu miền riêng:

~~~java
public final class BookingCodeConverter
        implements org.springframework.core.convert.converter
                .Converter<String, BookingCode> {

    @Override
    public BookingCode convert(String source) {
        return new BookingCode(source.trim().toUpperCase(
                java.util.Locale.ROOT));
    }
}
~~~

Đây là **snippet minh họa**, chỉ có ý nghĩa cùng định nghĩa `BookingCode` và cần bổ sung quy tắc kiểm tra cú pháp để dùng production. Đăng ký:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(new BookingCodeConverter());
}
~~~

Một `Converter<S,T>` chỉ định nghĩa phép chuyển **S → T**. Nếu view cần chuyển `BookingCode → String` để hiển thị, có thể cần converter chiều ngược lại hoặc dùng `Formatter<T>` để có cả parse và print.

### 3.2. Formatter<T> — parse và print, hỗ trợ Locale

`org.springframework.format.Formatter<T>` có hai thao tác:

~~~java
public interface Formatter<T> {
    T parse(String text, Locale locale)
            throws ParseException;

    String print(T object, Locale locale);
}
~~~

Đây là **hình thức rút gọn** của API; bạn import `java.util.Locale` và `java.text.ParseException` khi cài đặt. `Formatter<T>` giúp form hiểu cả hai chiều:

~~~text
HTTP "bk-a12"
    -> parse(...)
    -> BookingCode("BK-A12")
    -> DTO

BookingCode("BK-A12")
    -> print(...)
    -> HTML field value "BK-A12"
~~~

`locale` hữu ích cho các kiểu như tiền tệ, ngày và số. Ví dụ tiếng Việt có thể dùng dấu phân cách số khác locale tiếng Anh. Mã định danh thường không phụ thuộc locale, nên demo chuẩn hóa ký tự bằng `Locale.ROOT`.

### 3.3. GenericConverter và ConditionalGenericConverter

Khi quy tắc chuyển đổi phụ thuộc thêm metadata kiểu nguồn/đích hoặc nhiều cặp kiểu, có thể dùng `GenericConverter`. Với điều kiện động, `ConditionalGenericConverter` cho phép chỉ kích hoạt trên những cặp loại dữ liệu phù hợp.

Không dùng GenericConverter cho phép biến đổi đơn giản mà `Converter<String,T>` đã diễn đạt rõ. API phức tạp hơn đòi kiểm thử source type, target type và thứ tự converter.

### 3.4. FormatterRegistrar và AnnotationFormatterFactory

Khi cần đăng ký một nhóm formatters, dùng `FormatterRegistrar`:

~~~java
public class DateFormattingRegistration
        implements org.springframework.format.FormatterRegistrar {

    @Override
    public void registerFormatters(
            org.springframework.format.FormatterRegistry registry) {
        // Đăng ký các formatter có liên quan.
    }
}
~~~

Đây chỉ là snippet SPI; chưa đủ logic riêng để chạy. `AnnotationFormatterFactory<A>` phù hợp khi formatter được kích hoạt bằng annotation trên property (ví dụ cơ chế `@DateTimeFormat` và `@NumberFormat`), thay vì theo một kiểu Java duy nhất. Lựa chọn đúng mức trừu tượng giúp tránh áp dụng sai định dạng cho mọi field cùng kiểu.

## 4. FormatterRegistry áp dụng ở đâu?

`addFormatters(...)` trong `WebMvcConfigurer` bổ sung converter/formatter vào **FormattingConversionService dùng chung của Spring MVC**, nhờ đó có thể tác động đến các bước chuyển đổi phục vụ annotated controllers, ví dụ:

- `@RequestParam BookingCode code` từ query `?code=bk-a12`.
- `@PathVariable BookingCode code` nếu được MVC conversion service hỗ trợ ở vị trí đó.
- `@ModelAttribute ReservationForm form` với field `BookingCode code`.
- Việc in lại field qua Spring form binding/Thymeleaf `th:field`.
- Các tình huống conversion của MVC trên controller arguments khác theo resolver tương ứng.

**Không nên mở rộng kết luận ra tất cả framework**:

- JSON `@RequestBody` thường được Jackson deserialize bằng `HttpMessageConverter`. `Formatter<BookingCode>` của MVC **không tự trở thành Jackson deserializer**.
- Spring Data JPA, R2DBC, `@ConfigurationProperties` và service methods có thể dùng conversion service khác; không chắc nhìn thấy formatter trong `mvcConversionService`.
- Spring WebFlux dùng `WebFluxConfigurer` cho cấu hình web reactive, không dùng `WebMvcConfigurer`.
- Formatter không quyết định validation groups, không tự sinh lỗi `@NotBlank` và không thay thế `@Valid`.

### Default formatters và annotation có sẵn

Spring MVC đã hỗ trợ nhiều kiểu số, ngày, thời gian cùng annotation như:

~~~java
@org.springframework.format.annotation.DateTimeFormat(
        iso = org.springframework.format.annotation.DateTimeFormat.ISO.DATE)
private java.time.LocalDate startDate;

@org.springframework.format.annotation.NumberFormat(
        pattern = "#,##0.00")
private java.math.BigDecimal amount;
~~~

Đây là snippet field DTO, không phải class chạy độc lập. Thường **không cần đăng ký custom formatter** cho mỗi `LocalDate` hay `BigDecimal`. Khi muốn kiểm soát định dạng toàn cục, có thể dùng registrar/formatter; khi một property có ngoại lệ riêng, annotation có thể rõ ràng hơn.

Lưu ý: Spring có thể dùng locale của request khi parse/print. Ngược lại, browser `<input type="date">` đòi giá trị theo quy tắc chuẩn HTML, thường `yyyy-MM-dd`, dù hiển thị lịch theo locale người dùng. Không viết formatter định dạng ngày có dấu gạch chéo rồi kỳ vọng `input type="date"` luôn hiểu.

## 5. getValidator: chọn global validator

Hook thứ hai:

~~~java
@Override
public org.springframework.validation.Validator getValidator() {
    return null;
}
~~~

Theo hợp đồng `WebMvcConfigurer`, **trả `null` nghĩa là không cung cấp custom Validator** và cho cơ chế mặc định chọn validator. Nếu Jakarta Bean Validation provider có mặt (như Hibernate Validator), Spring MVC thường dùng một adapter/factory validator có khả năng đọc các annotation `jakarta.validation.constraints.*`.

`getValidator()` có return type **`org.springframework.validation.Validator`**, không phải chỉ `jakarta.validation.Validator`. Đây là hai API khác nhau:

| Thành phần | Kiểu | Phương thức tiêu biểu |
| --- | --- | --- |
| Spring Validator | `org.springframework.validation.Validator` | `supports(Class<?>)`, `validate(Object, Errors)` |
| Spring SmartValidator | `org.springframework.validation.SmartValidator` | `validate(Object, Errors, Object... hints)` |
| Jakarta Validator | `jakarta.validation.Validator` | `validate(T, Class<?>... groups)`, `forExecutables()` |
| LocalValidatorFactoryBean | Adapter Spring/Jakarta | Có thể dùng qua cả Spring Validator và Jakarta Validator |

`LocalValidatorFactoryBean` là cầu nối quan trọng. Nó khởi tạo Jakarta Validation provider, đồng thời có API Spring Validator/SmartValidator để Spring MVC dùng cho `@Valid`/`@Validated`. Khi Spring quản lý nó như bean, lifecycle initialization/shutdown được framework xử lý.

### 5.1. Tại sao trả một Spring Validator tự viết có thể làm mất @NotBlank?

Ví dụ **không nên làm tùy tiện**:

~~~java
@Override
public Validator getValidator() {
    return new MyOnlyCustomValidator();
}
~~~

Nếu `MyOnlyCustomValidator` chỉ kiểm tra một loại form với `supports(ReservationForm.class)` và chỉ gọi `errors.rejectValue(...)` theo rule tự viết, việc chọn nó làm **global MVC validator** có thể thay thế validator Jakarta mặc định. Các constraint `@NotBlank`/`@Email`/`@Min` trên form khác sẽ không tự được kiểm tra qua provider như trước.

Đây là snippet anti-pattern, giả định class custom tồn tại. Khi muốn thêm một quy tắc cho **một form**, thường nên chọn:

- Custom Jakarta `@Constraint` + `ConstraintValidator` để rule tham gia Bean Validation.
- `@InitBinder` + `binder.addValidators(...)` để bổ sung Spring Validator theo controller/attribute cụ thể.
- Một `LocalValidatorFactoryBean` được cấu hình đúng làm global validator, nếu phải thay chiến lược Jakarta provider, message interpolator hoặc các tùy chỉnh toàn cục.

Chỉ thay `getValidator()` khi hiểu rõ hệ quả đối với những controller khác.

### 5.2. Kết hợp với @Valid và @Validated

~~~java
@PostMapping("/reservations")
String create(
        @Valid @ModelAttribute("reservationForm")
        ReservationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "reservation-form";
    }
    return "redirect:/reservations/success";
}
~~~

`@Valid` trên form khiến MVC gọi validator phù hợp sau binding và ghi lỗi vào `BindingResult`, nếu có. `@Validated(Group.class)` còn cho phép chọn validation groups ở argument. Với `LocalValidatorFactoryBean`, Jakarta constraints hoạt động theo nhóm như `Default` và các marker groups.

`BindingResult` **phải đứng ngay sau** tham số `@ModelAttribute` mà nó mô tả. Nếu không nhận một `BindingResult` phù hợp, Spring MVC có thể ném `MethodArgumentNotValidException` khi argument validation thất bại; với method validation native Spring 6.1+ do direct constraints trên method, có thể gặp `HandlerMethodValidationException`. Đừng nhầm việc cấu hình global validator với AOP method validation của service.

### 5.3. Một global validator, nhiều configurers

Một ứng dụng có thể có nhiều class implements `WebMvcConfigurer`. Đăng ký formatter bằng `addFormatters(...)` là cách cộng các converter/formatter vào registry. Nhưng với `getValidator()`, nhiều configurer cùng trả các validator **khác null** không phải mô hình mặc nhiên kết hợp chúng. Cần thống nhất một global validator và tránh cấu hình xung đột; các rule bổ sung nên gắn ở điểm thích hợp thay vì mỗi module trả một global validator riêng.

## 6. Ví dụ chạy được: Spring Boot 3.5.7, Java 17, MVC + Thymeleaf

Ta tạo trang đặt chỗ chứa ba field:

- `code` là `BookingCode` chứ không phải String. Người dùng nhập `bk-a12`, formatter tạo `BookingCode("BK-A12")`.
- `contactName` là String có `@NotBlank`.
- `seats` là Integer có `@NotNull` và `@Min(1)`.

Ứng dụng cấu hình **cả hai hook** `addFormatters` và `getValidator`. `getValidator` trả về cùng `LocalValidatorFactoryBean` singleton do Spring quản lý để không làm mất Jakarta Bean Validation. Controller dùng `@InitBinder` cho allowlist các field được phép bind.

### 6.1. Cấu trúc thư mục

~~~text
mvc-formatter-validator/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/mvc/
    │   │   ├── Application.java
    │   │   ├── BookingCode.java
    │   │   ├── BookingCodeFormatter.java
    │   │   ├── ReservationForm.java
    │   │   ├── ValidationBeans.java
    │   │   ├── MvcSettings.java
    │   │   └── ReservationController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/reservation-form.html
    └── test/
        └── java/com/example/mvc/
            └── ReservationControllerTest.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-formatter-validator</artifactId>
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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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
~~~

Đây là ứng dụng **Servlet/MVC**, không phải WebFlux. `spring-boot-starter-web` cung cấp Spring MVC; `spring-boot-starter-validation` cung cấp Jakarta Validation provider; `spring-boot-starter-thymeleaf` render HTML form; test starter hỗ trợ JUnit 5 và MockMvc.

Spring Boot version trong ví dụ được cố định để dễ tái lập. Trong code production nên sử dụng BOM/patch version theo chính sách bảo mật của dự án.

### 6.3. Application.java

~~~java
package com.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 6.4. BookingCode.java — value object Java 17

~~~java
package com.example.mvc;

public record BookingCode(String value) {
}
~~~

Đây là record bất biến. Không để controller nhận thẳng String cho `code`: việc dùng kiểu riêng minh họa lý do cần formatter. Record không tự quy định cú pháp; quy tắc parse của form đặt trong `BookingCodeFormatter`.

### 6.5. BookingCodeFormatter.java — parse/print hai chiều

~~~java
package com.example.mvc;

import org.springframework.format.Formatter;

import java.text.ParseException;
import java.util.Locale;
import java.util.regex.Pattern;

public final class BookingCodeFormatter
        implements Formatter<BookingCode> {

    private static final Pattern CODE =
            Pattern.compile("BK-[A-Z0-9]{3,8}");

    @Override
    public BookingCode parse(String text, Locale locale)
            throws ParseException {

        String canonical = text.trim()
                .toUpperCase(Locale.ROOT);

        if (!CODE.matcher(canonical).matches()) {
            throw new ParseException(
                    "Booking code must match BK-XXX", 0);
        }

        return new BookingCode(canonical);
    }

    @Override
    public String print(BookingCode object, Locale locale) {
        return object.value();
    }
}
~~~

Quy tắc demo:

- `"bk-a12"` → trim, upper-case → `"BK-A12"` → record hợp lệ.
- `" BK-123 "` → `"BK-123"`.
- `"WRONG"`, `"BK-1"` hoặc `"BK-AB_12"` → `ParseException`, Spring binder ghi lỗi chuyển kiểu cho field.
- `print(new BookingCode("BK-A12"), locale)` → `"BK-A12"` để view hiển thị.

`Locale.ROOT` tránh biến đổi chữ phụ thuộc locale khi chuẩn hóa mã định danh. Tham số `Locale locale` của `Formatter` vẫn cần có trong chữ ký interface, dù rule mã nghiệp vụ này không dùng.

**Quan trọng về trách nhiệm:** pattern trong formatter xác định một chuỗi **có thể tạo thành BookingCode**; constraint `@NotNull` trên field `code` lại kiểm tra sự hiện diện của mã. Nếu business rule như “mã đã được cấp hay chưa” cần database/I/O, hãy thực hiện ở service thay vì gọi cơ sở dữ liệu bên trong formatter.

### 6.6. ReservationForm.java — Jakarta constraints

~~~java
package com.example.mvc;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ReservationForm {

    @NotNull
    private BookingCode code;

    @NotBlank
    private String contactName;

    @NotNull
    @Min(1)
    private Integer seats;

    public BookingCode getCode() {
        return code;
    }

    public void setCode(BookingCode code) {
        this.code = code;
    }

    public String getContactName() {
        return contactName;
    }

    public void setContactName(String contactName) {
        this.contactName = contactName;
    }

    public Integer getSeats() {
        return seats;
    }

    public void setSeats(Integer seats) {
        this.seats = seats;
    }
}
~~~

`@NotNull` và `@Min` là constraint của **validation**, không phải converter. Trong ví dụ, Bean Validation không cần `@Valid` trên `BookingCode` vì record `BookingCode` chưa có constraint nội tại để cascade. Nếu sau này record được thêm field constraint và muốn validate qua `ReservationForm.code`, hãy cân nhắc `@Valid` trên cạnh này hoặc một custom class-level constraint phù hợp.

### 6.7. ValidationBeans.java — validator được Spring quản lý

~~~java
package com.example.mvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationBeans {

    @Bean("appValidator")
    @Primary
    public LocalValidatorFactoryBean appValidator() {
        return new LocalValidatorFactoryBean();
    }
}
~~~

`LocalValidatorFactoryBean` là một Spring-managed singleton. Spring sẽ gọi lifecycle initialization (bao gồm thiết lập Jakarta provider) theo vòng đời bean, vì vậy không phải tự gọi `afterPropertiesSet()` trên instance mỗi request. `@Primary` làm rõ lựa chọn ưu tiên khi cùng kiểu validator có nhiều candidates.

Khi bean này có mặt, Spring Boot validation auto-configuration có thể **back off** khỏi việc tự tạo một Jakarta Validator mặc định khác. `MvcSettings.getValidator()` dưới đây trả chính instance đã quản lý; không tạo một factory mới mỗi lần gọi.

### 6.8. MvcSettings.java — cả addFormatters và getValidator

~~~java
package com.example.mvc;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.validation.Validator;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcSettings implements WebMvcConfigurer {

    private final LocalValidatorFactoryBean appValidator;

    public MvcSettings(
            @Qualifier("appValidator")
            LocalValidatorFactoryBean appValidator) {
        this.appValidator = appValidator;
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new BookingCodeFormatter());
    }

    @Override
    public Validator getValidator() {
        return appValidator;
    }
}
~~~

Đây là trọng tâm bài học:

- `addFormatters(...)` bổ sung parser/printer cho `BookingCode` vào MVC conversion service. Một class Formatter có thể được tái sử dụng cho nhiều controller/form fields cùng kiểu.
- `getValidator()` trả **Spring Validator** mà MVC sử dụng; `LocalValidatorFactoryBean` triển khai API này và vẫn hoạt động với Jakarta annotations.
- Spring quản lý bean validator nên provider/factory được khởi tạo một lần, tránh tự khởi tạo hàng loạt.
- Không có `@EnableWebMvc`: Spring Boot vẫn quản lý MVC auto-configuration của nó.
- Hai hook tác động toàn cục trong **MVC infrastructure**, khác với tùy chỉnh chỉ một form qua `@InitBinder`.

Trong ứng dụng Boot đơn giản, **chỉ override `addFormatters` và để mặc định `getValidator` là đủ** nếu đã có Bean Validation provider. Ví dụ cố ý override `getValidator` để diễn giải rõ cách chọn global validator an toàn khi bắt buộc phải tùy biến.

### 6.9. ReservationController.java — binder và validation

~~~java
package com.example.mvc;

import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class ReservationController {

    @InitBinder("reservationForm")
    void configureBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "code", "contactName", "seats");
    }

    @GetMapping("/reservations/new")
    public String newForm(Model model) {
        model.addAttribute(
                "reservationForm", new ReservationForm());
        return "reservation-form";
    }

    @PostMapping("/reservations")
    public String create(
            @Valid @ModelAttribute("reservationForm")
            ReservationForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "reservation-form";
        }

        // Sau khi hợp lệ, gọi service nghiệp vụ nếu có.
        return "redirect:/reservations/success";
    }

    @GetMapping("/reservations/success")
    @ResponseBody
    public String success() {
        return "Accepted";
    }
}
~~~

Giải thích:

1. Spring nhận form fields và dùng formatter để chuyển `code` từ String sang `BookingCode`.
2. `@Valid` kích hoạt global validator, ở đây là `LocalValidatorFactoryBean` từ `getValidator()`.
3. `BindingResult` ngay sau form giữ mọi lỗi từ conversion và validation, không yêu cầu hai exception khác nhau trong flow form HTML này.
4. Nếu có lỗi, trả `reservation-form` **trong cùng request** để người dùng nhìn lại dữ liệu đã gõ.
5. Nếu hợp lệ, redirect đến endpoint trả `Accepted`. Demo không ghi database.
6. `@InitBinder("reservationForm")` chỉ cho phép ba property được bind. Đây là chính sách bảo vệ mass assignment, không phải thêm constraint.

`setAllowedFields(...)` ở controller chỉ là cấu hình cục bộ cho binder tương ứng; nó không “đăng ký một converter toàn cục”. Nếu có nhiều form, mỗi form có thể có allowlist khác nhau, trong khi BookingCodeFormatter vẫn dùng chung.

### 6.10. templates/reservation-form.html — dùng th:field

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đặt chỗ</title>
    <style>
        .error { color: #b00020; }
        .invalid { border: 1px solid #b00020; }
    </style>
</head>
<body>
<h1>Đặt chỗ</h1>

<form th:action="@{/reservations}"
      th:object="${reservationForm}"
      method="post">

    <div>
        <label for="code">Mã đặt chỗ</label>
        <input type="text"
               th:field="*{code}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('code')}"
           th:errors="*{code}"></p>
    </div>

    <div>
        <label for="contactName">Người liên hệ</label>
        <input type="text"
               th:field="*{contactName}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('contactName')}"
           th:errors="*{contactName}"></p>
    </div>

    <div>
        <label for="seats">Số ghế</label>
        <input type="text"
               inputmode="numeric"
               th:field="*{seats}"
               th:errorclass="invalid">
        <p class="error"
           th:if="${#fields.hasErrors('seats')}"
           th:errors="*{seats}"></p>
    </div>

    <button type="submit">Đặt chỗ</button>
</form>
</body>
</html>
~~~

`th:object="${reservationForm}"` phải khớp với tên của `@ModelAttribute("reservationForm")`. `th:field="*{code}"` sử dụng Spring binding status, vì thế khi bean có `BookingCode` hợp lệ, MVC formatter có thể in lại dạng String. Khi parse thất bại, `BindingResult` có thể cung cấp **rejected value** để người dùng vẫn thấy chuỗi sai đã nhập. `th:errors` hiển thị lỗi field tương ứng.

Dùng `th:field` thay cho chỉ lấy `form.getCode().toString()`: mặc định `record.toString()` có thể là `BookingCode[value=BK-A12]` chứ không phải ký hiệu mà form muốn hiển thị. Formatter `print` xác định biểu diễn thân thiện với UI.

### 6.11. application.properties và chạy ứng dụng

~~~properties
server.port=8080
spring.thymeleaf.cache=false
~~~

Tắt template cache ở đây chỉ hỗ trợ sửa HTML trong môi trường học. Chạy:

~~~bash
mvn spring-boot:run
~~~

Mở `http://localhost:8080/reservations/new`. Các tình huống:

- `code=bk-a12`, `contactName=Lan`, `seats=3`: formatter chuẩn hóa thành `BK-A12`; Bean Validation hợp lệ; controller redirect **HTTP 302** đến `/reservations/success`.
- `code=WRONG`, `contactName=Lan`, `seats=3`: formatter parse lỗi; controller trả view form với `FieldError` tại `code` và trạng thái input đã nhập.
- `code=bk-a12`, `contactName=`, `seats=3`: formatter **thành công**, nhưng `@NotBlank` tạo lỗi `contactName`.
- `code=bk-a12`, `contactName=Lan`, `seats=0`: giá trị số bind được, `@Min(1)` không đạt.
- `code=bk-a12`, `contactName=Lan`, `seats=abc`: thất bại chuyển kiểu `Integer`, gây `typeMismatch`.
- Không gửi `code`: `@NotNull` báo lỗi vì field không hiện diện.

Đây là những hành vi dự kiến theo code; nội dung mặc định của `th:errors` có thể khác nhau tùy locale/message bundle, nên không cố định một chuỗi lỗi tiếng Anh/Việt không được cấu hình.

## 7. Kiểm thử bằng MockMvc

Tạo `src/test/java/com/example/mvc/ReservationControllerTest.java`:

~~~java
package com.example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.format.support.FormattingConversionService;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.servlet.ModelAndView;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ReservationControllerTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    @Qualifier("appValidator")
    LocalValidatorFactoryBean appValidator;

    @Autowired
    @Qualifier("mvcValidator")
    Validator mvcValidator;

    @Autowired
    @Qualifier("mvcConversionService")
    FormattingConversionService conversionService;

    @Test
    void globalMvcValidatorIsConfiguredBean() {
        assertSame(appValidator, mvcValidator);
    }

    @Test
    void formatterParsesAndPrints() {
        BookingCode code =
                conversionService.convert(
                        "bk-a12", BookingCode.class);

        assertNotNull(code);
        assertEquals("BK-A12", code.value());

        String display =
                conversionService.convert(code, String.class);

        assertEquals("BK-A12", display);
    }

    @Test
    void getFormHasBackingObject() throws Exception {
        mvc.perform(get("/reservations/new"))
                .andExpect(status().isOk())
                .andExpect(view().name("reservation-form"))
                .andExpect(model().attributeExists(
                        "reservationForm"));
    }

    @Test
    void validFormRedirects() throws Exception {
        mvc.perform(post("/reservations")
                        .param("code", "bk-a12")
                        .param("contactName", "Lan")
                        .param("seats", "3"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl(
                        "/reservations/success"));
    }

    @Test
    void formatterFailureRetainsRejectedText()
            throws Exception {

        var action = mvc.perform(post("/reservations")
                        .param("code", "WRONG")
                        .param("contactName", "Lan")
                        .param("seats", "3"))
                .andExpect(status().isOk())
                .andExpect(view().name("reservation-form"))
                .andExpect(model().attributeHasFieldErrors(
                        "reservationForm", "code"))
                .andReturn();

        ModelAndView mav = action.getModelAndView();
        assertNotNull(mav);

        BindingResult errors = (BindingResult)
                mav.getModel().get(
                        BindingResult.MODEL_KEY_PREFIX
                        + "reservationForm");

        assertNotNull(errors);

        FieldError conversionError =
                errors.getFieldErrors("code").stream()
                        .filter(FieldError::isBindingFailure)
                        .findFirst()
                        .orElseThrow();

        assertEquals("typeMismatch",
                conversionError.getCode());

        assertEquals("WRONG",
                conversionError.getRejectedValue());

        assertEquals("WRONG",
                errors.getFieldValue("code"));
    }

    @Test
    void jakartaConstraintsStillRunWithCustomGlobalValidator()
            throws Exception {

        mvc.perform(post("/reservations")
                        .param("code", "bk-a12")
                        .param("contactName", "")
                        .param("seats", "0"))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "reservationForm",
                        "contactName", "seats"));
    }

    @Test
    void codeNormalizesEvenWhenOtherFieldIsInvalid()
            throws Exception {

        var action = mvc.perform(post("/reservations")
                        .param("code", "bk-a12")
                        .param("contactName", "")
                        .param("seats", "3"))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "reservationForm", "contactName"))
                .andReturn();

        ModelAndView mav = action.getModelAndView();
        assertNotNull(mav);

        ReservationForm form = (ReservationForm)
                mav.getModel().get("reservationForm");

        assertNotNull(form);
        assertNotNull(form.getCode());
        assertEquals("BK-A12", form.getCode().value());
    }

    @Test
    void absentCodeFailsNotNullConstraint() throws Exception {
        mvc.perform(post("/reservations")
                        .param("contactName", "Lan")
                        .param("seats", "3"))
                .andExpect(status().isOk())
                .andExpect(model().attributeHasFieldErrors(
                        "reservationForm", "code"));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Tám test** có vai trò khác nhau:

1. `globalMvcValidatorIsConfiguredBean` xác nhận `getValidator()` trả bean validator đã chọn, không phải object bất ngờ khác.
2. `formatterParsesAndPrints` kiểm tra hai chiều conversion và chuỗi canonical.
3. `getFormHasBackingObject` kiểm tra GET view có đúng form model.
4. `validFormRedirects` kiểm tra POST hợp lệ.
5. `formatterFailureRetainsRejectedText` kiểm tra `FieldError.isBindingFailure()`, `typeMismatch` và rejected input.
6. `jakartaConstraintsStillRunWithCustomGlobalValidator` chứng minh lựa chọn global validator không làm mất `@NotBlank`/`@Min`.
7. `codeNormalizesEvenWhenOtherFieldIsInvalid` chứng minh conversion thành công độc lập với constraint trên field khác.
8. `absentCodeFailsNotNullConstraint` chứng minh thiếu input khác lỗi parse.

Không dựa vào thứ tự trả về của danh sách constraint violations. Với các field có thể có nhiều lỗi, tìm `FieldError` theo `isBindingFailure()` chứ không khẳng định `getFieldError()` luôn là lỗi duy nhất.

Nếu thêm Spring Security sau này, các POST MockMvc tests có thể cần CSRF token và authentication phù hợp. HTTP 403 do CSRF xảy ra **trước** khi kiểm tra form, không phải lỗi formatter hay Bean Validation.

### Giải thích bean @Qualifier trong test

`mvcConversionService` và `mvcValidator` là tên bean hạ tầng thường dùng bởi Spring MVC configuration. `@Qualifier` trong test xác định rõ đúng bean MVC thay vì vô tình lấy một conversion service/validator phục vụ mục đích khác của ứng dụng.

Trong các phiên bản Spring Boot/Spring Framework khác nhau, bean wiring và auto-configuration có thể có tùy biến; hãy kiểm tra application context thực tế trước khi đưa test phụ thuộc vào tên bean nội bộ thành một contract công khai của toàn hệ thống.

## 8. Khi nào không cần override getValidator?

Nhiều ứng dụng chỉ cần:

~~~java
@Configuration
public class MvcConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new BookingCodeFormatter());
    }
}
~~~

Đây là snippet thay thế `MvcSettings`, giả định có `BookingCodeFormatter`. Nếu Spring Boot đã có Jakarta Validation provider và global `LocalValidatorFactoryBean` phù hợp, **không cần tự định nghĩa `ValidationBeans` hoặc override `getValidator()`**. Đây thường là lựa chọn đơn giản, dễ bảo trì hơn.

Một nguyên tắc:

- **Muốn bổ sung một formatter:** override `addFormatters`.
- **Muốn giữ Bean Validation mặc định:** đừng override `getValidator` không cần thiết, hoặc trả `null`.
- **Muốn thay cách Jakarta Validation hoạt động toàn cục:** cấu hình `LocalValidatorFactoryBean`/provider một cách rõ ràng và trả instance phù hợp.
- **Muốn thêm custom rule cho một controller/form:** dùng `@InitBinder(...).addValidators(...)`, hoặc Jakarta custom constraint.
- **Muốn giới hạn property được bind:** dùng DTO riêng và `WebDataBinder.setAllowedFields(...)`.
- **Muốn thay đường thông điệp lỗi:** cấu hình `MessageSource`, `MessageCodesResolver` hoặc constraint message templates, không dùng formatter để tự viết exception presentation.

## 9. Global validator và validator cục bộ

### 9.1. Spring Validator tùy chỉnh

Spring cung cấp interface:

~~~java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

Đây là API rút gọn; không tự định nghĩa lại interface khi viết ứng dụng. Một custom validator có thể ghi lỗi theo property:

~~~java
if (form.getContactName() != null
        && form.getContactName().equalsIgnoreCase("system")) {
    errors.rejectValue(
            "contactName",
            "contactName.reserved",
            "Tên này không được sử dụng");
}
~~~

Snippet giả định `form` và `errors` thuộc phương thức `validate(...)` phù hợp. Một custom validator nên thuần dữ liệu, tránh side effects và không gọi I/O chặn không cần thiết.

### 9.2. addValidators thay vì setValidator

Nếu controller có custom validator cho `ReservationForm`:

~~~java
@InitBinder("reservationForm")
void addRules(WebDataBinder binder) {
    binder.addValidators(customReservationValidator);
}
~~~

Đây là snippet cần biến `customReservationValidator` được inject và phải triển khai `org.springframework.validation.Validator`. `addValidators(...)` **bổ sung** validator vào danh sách, còn `setValidator(...)` **thay** validator đã được thiết lập trên binder. Nếu muốn giữ Jakarta Bean Validation và thêm rule cục bộ, `addValidators` thường là lựa chọn ít rủi ro hơn.

Cần kiểm tra `supports(clazz)` để validator riêng chỉ áp dụng đúng target type. Không đính kèm một validator chỉ chấp nhận `ReservationForm` vào tất cả controller attributes rồi bỏ qua lỗi runtime khi target không phù hợp.

### 9.3. Validation groups

Jakarta Validation có nhóm mặc định `Default`. Spring `@Validated(Group.class)` trên một argument có thể chọn custom group:

~~~java
@PostMapping("/reservations/final")
String finalSubmit(
        @Validated({Default.class, FinalSubmit.class})
        @ModelAttribute("reservationForm")
        ReservationForm form,
        BindingResult errors) {
    // ...
}
~~~

Đây là snippet, cần import `jakarta.validation.groups.Default`, `org.springframework.validation.annotation.Validated` và định nghĩa `FinalSubmit` marker interface. Chỉ `@Validated(FinalSubmit.class)` có thể bỏ qua constraints thuộc `Default`; nếu yêu cầu cả hai, chọn cả hai theo ví dụ.

`LocalValidatorFactoryBean` hỗ trợ chuyển validation hints/groups từ Spring MVC vào Jakarta provider. Một Spring Validator tùy chỉnh chỉ triển khai `Validator.validate(Object, Errors)` không nhất thiết hiểu Jakarta groups giống `SmartValidator`.

## 10. Bảo đảm lỗi được hiển thị và có thể debug

### 10.1. BindingResult và rejected value

Khi `BookingCodeFormatter.parse("WRONG", ...)` thất bại, Java field `ReservationForm.code` có thể còn null. Nhưng `BindingResult` có `FieldError` ghi dữ liệu lỗi:

~~~java
FieldError error = errors.getFieldErrors("code")
        .stream()
        .filter(FieldError::isBindingFailure)
        .findFirst()
        .orElseThrow();

Object rawInput = error.getRejectedValue();
Object displayInput = errors.getFieldValue("code");
~~~

Đây là snippet giả định biến `errors` đã tồn tại; không phải class độc lập. Hai giá trị này có thể là chuỗi `"WRONG"`. `th:field="*{code}"` là cách hiển thị lại input nhờ Spring binding status; nếu chỉ đọc `form.getCode()`, UI có thể bị mất dữ liệu sai.

Khi `code` parse được thành `BookingCode` nhưng `contactName` sai, `code` không có `FieldError`; view dùng formatter `print` để hiển thị lại dạng canonical `"BK-A12"`.

### 10.2. Message codes và bản địa hóa

Spring ghi mã lỗi field theo nhiều mức ưu tiên. Ví dụ:

~~~text
typeMismatch.reservationForm.code
typeMismatch.code
typeMismatch.com.example.mvc.BookingCode
typeMismatch
~~~

Đây là **dạng mã minh họa**, không bảo đảm toàn bộ mã chính xác cho mọi message resolver, phiên bản Spring hoặc cấu hình. Hãy in `FieldError.getCodes()` thực tế nếu cần resource-bundle key.

Có thể đặt `src/main/resources/messages.properties`:

~~~properties
typeMismatch.reservationForm.code=Mã phải có dạng BK-XXX
NotNull.reservationForm.code=Vui lòng nhập mã đặt chỗ
NotBlank.reservationForm.contactName=Phải nhập người liên hệ
Min.reservationForm.seats=Số ghế phải ít nhất là 1
typeMismatch.reservationForm.seats=Số ghế phải là số nguyên
~~~

Nếu có `messages_vi.properties`, Spring có thể chọn thông điệp theo locale tiếng Việt. Lưu ý `ParseException` message từ formatter không tự trở thành message được bản địa hóa; mapping qua message codes/MessageSource giúp tách kỹ thuật từ trải nghiệm người dùng.

### 10.3. Cách đọc metadata khi nghi formatter chưa chạy

~~~java
for (FieldError error : errors.getFieldErrors()) {
    System.out.println(
            error.getField()
            + " | " + error.getCode()
            + " | binding=" + error.isBindingFailure());
}
~~~

Đoạn trên chỉ dành cho debug hoặc test. **Không** in nguyên `error.getRejectedValue()` cho field nhạy cảm (mật khẩu, token, số thẻ). Nếu nhìn thấy `typeMismatch` ở `code`, hãy kiểm tra formatter có được register hay không, nội dung parse và target type. Nếu nhìn thấy `NotBlank` ở `contactName`, converter không phải nguyên nhân của lỗi đó.

## 11. Tương tác với Spring Boot auto-configuration

Spring Boot giúp bạn có sẵn MVC setup. Dùng `WebMvcConfigurer` thường giúp **bổ sung** cấu hình mà vẫn giữ cơ chế mặc định.

Những nhầm lẫn quan trọng:

### 11.1. MVC conversion service không phải mọi ConversionService

Spring Boot có thể có conversion service khác cho việc bind configuration properties, environment hoặc các subsystems. `addFormatters` nhắm vào conversion service của Spring MVC. Nếu bạn inject một bean chỉ vì nó có kiểu `ConversionService`, không chắc đó là `mvcConversionService` đã nhận `BookingCodeFormatter`.

Cách kiểm tra trong integration tests là inject rõ `@Qualifier("mvcConversionService")` hoặc test qua chính MVC request binder; không dựa vào giả định mọi bean cùng interface đều dùng chung một registry.

### 11.2. JSON/Jackson không dùng Formatter như form

Giả sử:

~~~java
@PostMapping(
        path = "/api/reservations",
        consumes = "application/json")
ResponseEntity<?> api(
        @Valid @RequestBody ReservationForm form) {
    // ...
}
~~~

Đây là snippet minh họa, không có đầy đủ imports/return body. Jackson thường giải mã JSON theo metadata của nó trước rồi Bean Validation kiểm tra DTO. Một field JSON dạng `"code": "bk-a12"` không tự động được parse bởi custom `BookingCodeFormatter` của MVC. Nếu cần rule tương đương trong JSON, thiết kế Jackson deserializer/creator hoặc DTO JSON phù hợp, và kiểm thử riêng.

Vẫn có thể dùng cùng **global MVC Validator** để kiểm tra bean sau khi Jackson deserialize thành công, nhưng quá trình JSON decoding và String-to-BookingCode form parsing là hai chuyện khác nhau.

### 11.3. WebFlux có interface cấu hình khác

`WebMvcConfigurer` dành cho Spring MVC/Servlet. Nếu ứng dụng dùng `spring-boot-starter-webflux` và annotated controllers reactive, cơ chế cấu hình tương ứng là `WebFluxConfigurer`. Không thêm `WebMvcConfigurer` vào WebFlux rồi kết luận formatter/validator đã được kích hoạt.

### 11.4. AOP method validation là một ranh giới khác

Một Spring service class có `@Validated` ở cấp lớp, `@NotBlank` trên method parameter, được gọi qua Spring AOP proxy, có thể dùng method validation infrastructure (thường ném `ConstraintViolationException` mặc định). Điều đó **không đồng nghĩa** với `getValidator()` của Spring MVC controller binding. Nhiều ứng dụng dùng cùng Jakarta validation provider nhưng cách kích hoạt, exception và nhóm constraints có thể khác.

Nói cách khác:

~~~text
WebMvcConfigurer.getValidator()
    -> global Spring MVC argument validator

@Validated trên Spring-managed service
    -> method validation qua AOP proxy

Validator.validate(bean) gọi thủ công
    -> trả Set<ConstraintViolation<T>>
~~~

Không viết một rule trong `Formatter.parse(...)` để kỳ vọng nó tự bảo vệ mọi service method hoặc mọi API JSON.

## 12. Bảo mật và hiệu năng

### 12.1. Không bind trực tiếp entity

Một entity có thể có `id`, `role`, `approved` hoặc `balance`. Nếu cho HTTP binder ghi mọi property, client có thể gửi field không nằm trên form và cố thay đổi giá trị. Dùng DTO dành cho web input và `setAllowedFields(...)` phù hợp. `@Valid` không phải cơ chế authorization, và formatter không tự ngăn mass assignment.

### 12.2. Converter và Validator nên nhẹ, không side-effect

Formatter thường được đăng ký dùng chung. Hãy viết nó theo kiểu **stateless**, thread-safe, deterministic, không lưu request data vào field instance, không dùng `SimpleDateFormat` mutable chia sẻ thiếu đồng bộ. Với mã định danh, dùng `Pattern` bất biến và `Locale.ROOT` như ví dụ.

Không nên gọi database trong formatter hoặc dùng một validator chỉ để ghi entity. Các thao tác I/O và domain checks nên nằm ở service/repository layer với transaction/permission phù hợp.

### 12.3. Không đưa dữ liệu nhạy cảm vào lỗi

`FieldError.getRejectedValue()` và `ConstraintViolation.getInvalidValue()` có thể chứa input người dùng. Không serialize thẳng toàn bộ exception, target object hoặc rejected value vào REST response và logs. Dùng error code, field name và message đã escape/phê duyệt.

### 12.4. CSRF, quyền và input sanitization

Trong ứng dụng có Spring Security, các form POST cần CSRF token; một request bị từ chối HTTP 403 có thể chưa chạm tới binder hoặc Bean Validation. Validation không thay authentication, authorization, escaping HTML hoặc domain security rules.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `code=bk-a12` báo typeMismatch | Formatter chưa được đăng ký hoặc parse thất bại | Kiểm tra `addFormatters`, type `BookingCode`, rule parse |
| Field hiển thị `BookingCode[value=...]` | View dùng `toString()` thay vì formatter | Dùng `th:field` / Spring form tags và `Formatter.print` |
| `@NotBlank` không còn hoạt động sau khi custom getValidator | Global validator bị thay bằng Spring Validator khác không delegate Jakarta | Dùng `LocalValidatorFactoryBean` hoặc bổ sung rule cục bộ |
| `getValidator()` trả null nhưng `@Valid` vẫn chạy | Spring tự chọn validator mặc định khi provider có mặt | Đây là hành vi mong đợi |
| Tạo `new LocalValidatorFactoryBean()` mỗi lần request | Nhầm hook config với callback request | Dùng singleton bean do Spring quản lý |
| Có nhiều WebMvcConfigurer cùng trả custom Validator | Xung đột global configuration | Thống nhất một lựa chọn, dùng local validators nếu cần |
| JSON `@RequestBody` không parse BookingCode | Jackson không dùng FormatterRegistry của MVC để decode JSON | Thiết kế JSON DTO/deserializer riêng |
| `@RequestParam BookingCode` không convert | Đăng ký vào conversion service khác MVC | Sử dụng đúng MVC config và kiểm thử binder |
| `@Valid` không tạo lỗi | Thiếu Bean Validation provider/annotation, group không khớp | Kiểm tra starter, constraints và groups |
| `BindingResult` không nhận lỗi form | Đặt xa `@ModelAttribute` hoặc không nhận đúng attribute | Đặt ngay sau form argument |
| Form mất chuỗi code sai | Đọc bean property null sau conversion failure | Dùng `BindingResult.getFieldValue()` hoặc `th:field` |
| Tất cả Boot MVC settings biến mất | Thêm `@EnableWebMvc` thiếu cân nhắc | Dùng `WebMvcConfigurer` không @EnableWebMvc trong Boot |
| Test injection lấy nhầm ConversionService | App có nhiều conversion services | Qualifier `mvcConversionService` |
| Thông điệp ParseException lộ thông tin | Trả raw exception cho client | Dùng message codes/MessageSource |
| Form bị ghi field quản trị | Dùng entity làm form DTO, binder không giới hạn property | DTO riêng, `setAllowedFields`, quyền nghiệp vụ |
| Custom validator chặn cả DTO khác | Global validator có `supports` quá hẹp hoặc rule áp dụng nhầm | Dùng `@InitBinder.addValidators` / custom constraint đúng phạm vi |

## 14. Quy trình debug khi binding/validation không như dự kiến

1. **Xác minh web stack:** đây là Spring MVC/Servlet hay WebFlux? Nếu WebFlux, `WebMvcConfigurer` không phải hook phù hợp.
2. **Xem raw request:** kiểm tra `Content-Type`, request parameters, property name. Đừng nhầm `application/json` với `application/x-www-form-urlencoded`.
3. **Xem DTO:** field có kiểu đúng, getter/setter/constructor phù hợp, nested path tồn tại, field có trong allowed fields?
4. **Xem MVC configurer:** class có `@Configuration`, được component scan, có `@Override addFormatters(...)` đúng chữ ký, formatter type phù hợp?
5. **Test hai chiều:** gọi `mvcConversionService.convert("bk-a12", BookingCode.class)` rồi `convert(code, String.class)`.
6. **Xem BindingResult:** lỗi có `isBindingFailure()==true` và code `typeMismatch` hay lỗi Bean Validation `NotBlank`/`Min`?
7. **Xem validator:** `getValidator()` đang trả null hay instance nào; có Bean Validation provider, `LocalValidatorFactoryBean`, và `@Valid` trên argument?
8. **Xem thứ tự handler args:** `BindingResult` phải nằm ngay sau `@ModelAttribute` nếu controller tự render lỗi.
9. **Xem view:** `th:object` tên đúng, `th:field` dùng đúng path, rejected input có được giữ, locale phù hợp?
10. **Xem security/domain:** field có nên được bind hay không, form có CSRF token, giá trị cần kiểm tra DB có được tách khỏi Formatter/Validator không?

## 15. Bài tập vận dụng

**Bài 1 — Converter hay Formatter?** Nếu chỉ cần `String → UUID`, chọn `Converter` hay `Formatter`? Khi một kiểu `Money` còn cần in theo locale Việt Nam và parse về object, chọn interface nào hợp lý hơn?

**Bài 2 — Parse và validation:** Nhập `code=BK-1` rồi `code=BK-ABC` với `contactName=""`. Trường hợp nào là typeMismatch? Trường hợp nào là Jakarta constraint violation?

**Bài 3 — Vòng đời:** Vì sao đặt `new LocalValidatorFactoryBean()` trong một callback per-request là không tốt? Trình bày cách tạo bean singleton được Spring khởi tạo và trả từ `getValidator()`.

**Bài 4 — Chọn default:** Xóa override `getValidator()` và class `ValidationBeans` khỏi demo, giữ `spring-boot-starter-validation`. Kiểm tra `@NotBlank` và `@Min` còn hoạt động không, rồi giải thích Spring MVC chọn validator mặc định như thế nào.

**Bài 5 — Local rule:** Thêm Spring Validator cấm `contactName="system"` chỉ cho form đặt chỗ bằng `@InitBinder.addValidators(...)`. Chứng minh những form khác không tự bị áp dụng rule này.

**Bài 6 — JSON khác form:** Gửi `{"code":"bk-a12"}` vào `@RequestBody ReservationForm`. Tại sao custom Formatter có thể không được dùng? Hãy thiết kế JSON DTO có `String code` và map sang `BookingCode` ở application boundary, hoặc dùng Jackson deserialization phù hợp.

**Bài 7 — Rejected input:** Gửi `code=WRONG` rồi kiểm tra `FieldError.getRejectedValue()`, `getFieldValue("code")`, `isBindingFailure()` và HTML input được `th:field` render lại.

**Bài 8 — Locale:** Tạo `Formatter<Money>` in/parse số tiền bằng `Locale`; so sánh output tiếng Việt và tiếng Anh. Lưu ý khác biệt giữa cách hiển thị số và cú pháp cố định của `<input type="number">`.

**Bài 9 — Allowed fields:** Gửi thêm `role=ADMIN` hoặc `approved=true` vào form. Vì sao chỉ `@NotBlank` không bảo vệ được mass assignment? Kiểm thử `binder.getBindingResult().getSuppressedFields()` nếu muốn quan sát các field bị từ chối bind.

**Bài 10 — Method validation:** Đánh dấu một service `@Validated` và đặt `@NotBlank` trên method parameter. Gọi qua proxy và gọi bằng `new`, so sánh exception để hiểu vì sao `WebMvcConfigurer.getValidator()` không đồng nghĩa với AOP method validation.

## 16. Tóm tắt kiến thức

Sơ đồ ghi nhớ:

~~~text
              Spring MVC setup
                     |
         +-----------+-----------+
         |                       |
   addFormatters(...)        getValidator()
         |                       |
   FormattingConversionService   global Spring Validator
         |                       |
   String <-> Java types       @Valid / @Validated
         |                       |
         +-----------+-----------+
                     |
               WebDataBinder
                     |
               BindingResult
                     |
             Controller / View
~~~

- `addFormatters` **thêm** converter/formatter để chuyển và trình bày dữ liệu.
- `getValidator` **chọn** global validator để kiểm tra object theo rule đã khai báo.
- `@Valid`/`@Validated` **kích hoạt** validation và groups tại argument; `BindingResult` **giữ** lỗi binding/validation.
- Trong Spring Boot, thường chỉ cần override `addFormatters` và giữ validator mặc định. Nếu thực sự chọn custom global validator, dùng `LocalValidatorFactoryBean`/adapter phù hợp để không mất các constraint Jakarta.
- `@InitBinder` bổ sung tùy biến binder cục bộ và giới hạn property được phép ghi.
- Form conversion khác JSON deserialization; Spring MVC khác WebFlux; controller binding khác Spring AOP method validation.

**Kết luận:** Định dạng đúng chưa chắc dữ liệu hợp lệ, và validate đúng không thể sửa lỗi chuyển kiểu. Đặt từng trách nhiệm vào đúng hook giúp code dễ kiểm thử, bảo trì và an toàn hơn.

## Tài liệu tham khảo

- [Spring Framework 6.2 — WebMvcConfigurer API: addFormatters, getValidator](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
- [Spring Framework 6.2 — MVC config: Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html)
- [Spring Framework 6.2 — MVC config: Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html)
- [Spring Framework 6.2 — MVC configuration: @EnableWebMvc và Spring Boot](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/enable.html)
- [Spring Framework — Formatter SPI](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/Formatter.html)
- [Spring Framework — FormatterRegistry API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/FormatterRegistry.html)
- [Spring Framework — LocalValidatorFactoryBean API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html)
- [Spring Framework — BindingResult và FieldError](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Boot 3.5 — ValidationAutoConfiguration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/validation/ValidationAutoConfiguration.html)
- [Jakarta Bean Validation 3.0 specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
