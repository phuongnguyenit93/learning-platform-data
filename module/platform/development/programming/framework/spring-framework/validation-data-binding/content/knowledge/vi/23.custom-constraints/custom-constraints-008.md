# Ràng buộc cấp lớp cho quan hệ giữa nhiều trường trong Spring Framework

## 1. Vấn đề cần giải quyết

Một trường dữ liệu có thể hợp lệ khi xét riêng lẻ nhưng **cả đối tượng vẫn không hợp lệ** khi xét quan hệ giữa các trường. Ví dụ:

- `checkIn` và `checkOut` đều là ngày hợp lệ, nhưng ngày trả phòng không được bằng hoặc trước ngày nhận phòng.
- `startAmount` và `endAmount` đều là số hợp lệ, nhưng giới hạn dưới phải nhỏ hơn hoặc bằng giới hạn trên.
- Khi `deliveryMethod = HOME`, địa chỉ giao hàng bắt buộc; khi nhận tại cửa hàng, địa chỉ có thể để trống.
- Trong biểu mẫu liên hệ, phải có ít nhất một trong `email` hoặc `phone`.

Những quy tắc này được gọi là **cross-field validation** (kiểm tra quan hệ giữa nhiều trường). Với Jakarta Bean Validation trong Spring Framework, cách diễn đạt rõ ràng là **custom constraint đặt trên lớp/record**. Validator nhận cả đối tượng, kiểm tra các thuộc tính liên quan và tạo một hoặc nhiều `ConstraintViolation` khi điều kiện không thỏa.

Ví dụ, hai ràng buộc trên từng trường không đủ để kiểm tra thứ tự ngày:

```java
public record BookingRequest(
    @NotNull LocalDate checkIn,
    @NotNull LocalDate checkOut
) {}
```

`@NotNull` chỉ bảo đảm có giá trị. Nó không biết `checkOut` phải sau `checkIn`. Muốn mô tả quy tắc của toàn đối tượng, ta đặt một annotation cấp lớp, chẳng hạn `@ValidStayDates`, lên `BookingRequest`.

**Phân biệt phạm vi:** Jakarta Bean Validation kiểm tra tính hợp lệ của dữ liệu đầu vào theo hợp đồng của đối tượng. Quy tắc cần truy vấn cơ sở dữ liệu, xác minh quyền truy cập, kiểm tra tồn kho hoặc xử lý giao dịch thường thuộc tầng service/domain; không nên nhồi tất cả vào `ConstraintValidator`.

## 2. Luồng xử lý trong Spring MVC

Với Spring Framework 6 / Spring Boot 3 dùng namespace `jakarta.validation.*`:

1. Client gửi JSON tới controller.
2. Spring MVC/Jackson chuyển JSON thành đối tượng Java. Sai cú pháp JSON hoặc không chuyển được kiểu dữ liệu là **lỗi binding/deserialization**, xảy ra trước Bean Validation.
3. `@Valid` hoặc cấu hình `@Validated` phù hợp kích hoạt Bean Validation sau khi tạo đối tượng.
4. Provider (thường là Hibernate Validator khi dùng `spring-boot-starter-validation`) kiểm tra ràng buộc từng trường và ràng buộc cấp lớp.
5. `ConstraintValidator` của ràng buộc cấp lớp nhận toàn bộ đối tượng để đối chiếu các trường.
6. Nếu có vi phạm, Spring MVC thường phát sinh `MethodArgumentNotValidException` cho tham số `@Valid @RequestBody` không có `BindingResult` đi kèm; có thể chuyển lỗi thành HTTP 400 với `@RestControllerAdvice`.
7. Nếu không có lỗi, controller tiếp tục xử lý yêu cầu.

Biểu diễn ngắn:

```text
JSON -> Jackson/binding -> BookingRequest
                             |
                        @Valid / @Validated
                             |
                @NotNull trên từng trường
                @ValidStayDates trên đối tượng
                             |
             hợp lệ -> controller / service
             vi phạm -> BindingResult / HTTP 400
```

Lưu ý: thứ tự chạy giữa các constraint không được bảo đảm. Validator cấp lớp phải xử lý được dữ liệu có trường `null` hoặc dữ liệu đã bị ràng buộc khác báo lỗi.

## 3. Ví dụ đầy đủ: ngày nhận và trả phòng

Quy tắc được chọn cho ví dụ: **ngày trả phòng phải sau ngày nhận phòng ít nhất một ngày**. Cả hai trường đều bắt buộc. Nếu một trường thiếu, `@NotNull` phụ trách báo lỗi thiếu dữ liệu; ràng buộc cấp lớp bỏ qua việc so sánh để tránh báo thêm một lỗi khó hiểu.

### 3.1. Chuẩn bị dự án

Tạo dự án Spring Boot 3.x với Java 17 trở lên. Trong `build.gradle` (Groovy DSL), cần các dependency sau; các phiên bản plugin dưới đây là ví dụ cụ thể tương thích với Spring Boot 3.3:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-validation` đưa Jakarta Validation API và provider vào ứng dụng. Chỉ có annotation `@Constraint` mà không có provider thì không đủ để chạy kiểm tra trong ứng dụng độc lập.

Cấu trúc nguồn của ví dụ:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  api/
    BookingRequest.java
    BookingController.java
    ValidationExceptionHandler.java
  validation/
    ValidStayDates.java
    StayDatesValidator.java
src/test/java/com/example/demo/validation/
  StayDatesValidatorTest.java
```

### 3.2. Khai báo annotation cấp lớp

Tệp `src/main/java/com/example/demo/validation/ValidStayDates.java`:

```java
package com.example.demo.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = StayDatesValidator.class)
public @interface ValidStayDates {
    String message() default "Ngày trả phòng phải sau ngày nhận phòng";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

Giải thích các thành phần:

- `@Target(ElementType.TYPE)` cho phép gắn annotation vào class hoặc record thay vì một trường.
- `@Retention(RUNTIME)` giữ annotation lúc chạy để Bean Validation tìm được.
- `@Constraint(validatedBy = StayDatesValidator.class)` đăng ký lớp thực hiện logic kiểm tra.
- `message()` là thông báo mặc định, có thể ghi đè ngay tại nơi sử dụng annotation; cũng có thể dùng key message bundle như `{booking.dates.invalid}`.
- `groups()` và `payload()` là các phần bắt buộc trong hợp đồng khai báo custom constraint của Jakarta Bean Validation. `groups` cho phép chọn nhóm xác thực, `payload` dành cho metadata tùy chọn.

### 3.3. Định nghĩa DTO mang cả hai trường

Tệp `src/main/java/com/example/demo/api/BookingRequest.java`:

```java
package com.example.demo.api;

import com.example.demo.validation.ValidStayDates;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

@ValidStayDates
public record BookingRequest(
    @NotNull(message = "Ngày nhận phòng là bắt buộc")
    LocalDate checkIn,

    @NotNull(message = "Ngày trả phòng là bắt buộc")
    LocalDate checkOut
) {}
```

`@ValidStayDates` được gắn trên record nên validator có thể xem đồng thời cả hai component. `@NotNull` trên từng component vẫn kiểm tra tính bắt buộc độc lập. Đây là hai cấp ràng buộc bổ sung cho nhau, không thay thế nhau.

### 3.4. Viết `ConstraintValidator`

Tệp `src/main/java/com/example/demo/validation/StayDatesValidator.java`:

```java
package com.example.demo.validation;

import com.example.demo.api.BookingRequest;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import java.time.LocalDate;

public final class StayDatesValidator
        implements ConstraintValidator<ValidStayDates, BookingRequest> {

    @Override
    public boolean isValid(
            BookingRequest request,
            ConstraintValidatorContext context) {

        if (request == null) {
            return true;
        }

        LocalDate checkIn = request.checkIn();
        LocalDate checkOut = request.checkOut();

        // @NotNull đảm nhiệm lỗi thiếu một trong hai trường.
        if (checkIn == null || checkOut == null) {
            return true;
        }

        if (checkOut.isAfter(checkIn)) {
            return true;
        }

        // Chuyển lỗi ràng buộc cấp lớp vào field "checkOut".
        context.disableDefaultConstraintViolation();
        context
            .buildConstraintViolationWithTemplate(
                context.getDefaultConstraintMessageTemplate())
            .addPropertyNode("checkOut")
            .addConstraintViolation();

        return false;
    }
}
```

Hai kiểu generic của `ConstraintValidator<A, T>` rất quan trọng: `A` là annotation `ValidStayDates`; `T` là kiểu đối tượng được kiểm tra, ở đây là `BookingRequest`. Nếu áp dụng `@ValidStayDates` lên một kiểu khác mà validator này không hỗ trợ, provider có thể báo lỗi không tìm thấy validator phù hợp.

Phương thức `isValid` trả `true` nếu hợp lệ, `false` nếu vi phạm. Theo hợp đồng Bean Validation, `null` thường được kiểm tra bằng ràng buộc bắt buộc riêng; điều đó giúp tránh các lỗi trùng lặp. Nếu nghiệp vụ thật sự muốn báo lỗi cấp lớp khi toàn đối tượng `null` thì cần thiết kế ràng buộc và điểm kích hoạt cho trường hợp đó một cách riêng biệt.

Đoạn:

```java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        context.getDefaultConstraintMessageTemplate())
    .addPropertyNode("checkOut")
    .addConstraintViolation();
```

đặt đường dẫn lỗi thành `checkOut` thay vì lỗi ở cấp đối tượng. Điều này hữu ích cho giao diện biểu mẫu vì có thể hiện thông báo cạnh ô ngày trả phòng. Tên trong `addPropertyNode(...)` phải khớp tên thuộc tính thực tế của DTO. Nếu quan hệ giữa các trường không có một trường nào là nơi sửa hợp lý, có thể giữ **violation mặc định ở cấp lớp** bằng cách bỏ đoạn tạo property node tùy chỉnh; khi ấy lỗi thuộc `ObjectError` hoặc đường dẫn gốc.

**Không lưu dữ liệu của từng request vào field mutable của validator.** Provider có thể tái sử dụng instance validator; chỉ dùng biến cục bộ trong `isValid` hoặc trạng thái cấu hình bất biến được khởi tạo qua `initialize(...)`.

### 3.5. Kích hoạt ở controller

Tệp `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Tệp `src/main/java/com/example/demo/api/BookingController.java`:

```java
package com.example.demo.api;

import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/bookings")
public class BookingController {

    @PostMapping
    public ResponseEntity<Map<String, String>> create(
            @Valid @RequestBody BookingRequest request) {

        // Chỉ minh họa validation; chưa ghi dữ liệu xuống database.
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("status", "accepted"));
    }
}
```

`@Valid` trên tham số `@RequestBody` là điểm kích hoạt quan trọng. Chỉ khai báo `@ValidStayDates` trên DTO mà quên kích hoạt validation ở điểm nhận dữ liệu thì không thể kỳ vọng Spring tự kiểm tra ở mọi ngữ cảnh.

Đối với biểu mẫu `@ModelAttribute`, có thể đặt `@Valid` trên đối số và nhận `BindingResult` ngay sau đó để xử lý lỗi ở controller. Với những luồng dùng validation groups, `@Validated(SomeGroup.class)` cho phép chỉ định nhóm. Việc kiểm tra tham số/phương thức Spring MVC hoặc service có các cơ chế và loại exception riêng; không nên giả định mọi lỗi validation đều là `MethodArgumentNotValidException`.

### 3.6. Chuyển lỗi thành phản hồi API

Tệp `src/main/java/com/example/demo/api/ValidationExceptionHandler.java`:

```java
package com.example.demo.api;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> handle(
            MethodArgumentNotValidException exception) {

        List<Map<String, String>> errors = new ArrayList<>();

        for (FieldError error
                : exception.getBindingResult().getFieldErrors()) {
            errors.add(Map.of(
                "field", error.getField(),
                "message", error.getDefaultMessage()
            ));
        }

        for (ObjectError error
                : exception.getBindingResult().getGlobalErrors()) {
            errors.add(Map.of(
                "field", error.getObjectName(),
                "message", error.getDefaultMessage()
            ));
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("errors", errors);
        return ResponseEntity.badRequest().body(body);
    }
}
```

`getFieldErrors()` bao gồm vi phạm được gắn vào `checkOut` nhờ `addPropertyNode`. `getGlobalErrors()` nhận lỗi cấp đối tượng nếu ta giữ violation mặc định. Tùy yêu cầu API, có thể chuẩn hóa thành danh sách lỗi có `field`, `code`, `message` và không phụ thuộc vào thứ tự lỗi mà provider trả về. Handler này minh họa riêng lỗi `MethodArgumentNotValidException`; lỗi JSON không parse được, lỗi ở mức method validation và lỗi nghiệp vụ có thể cần handler khác.

### 3.7. Chạy và quan sát

Từ thư mục dự án có Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows, dùng `gradlew.bat bootRun`. Gửi request hợp lệ:

```bash
curl -i -X POST http://localhost:8080/bookings \
  -H "Content-Type: application/json" \
  -d '{"checkIn":"2026-11-10","checkOut":"2026-11-12"}'
```

Kết quả kỳ vọng: HTTP `201 Created` và JSON `{"status":"accepted"}`.

Thử thứ tự ngày sai:

```bash
curl -i -X POST http://localhost:8080/bookings \
  -H "Content-Type: application/json" \
  -d '{"checkIn":"2026-11-12","checkOut":"2026-11-10"}'
```

Kết quả kỳ vọng: HTTP `400 Bad Request` với nội dung tương đương (thứ tự khóa JSON không quan trọng):

```json
{
  "errors": [
    {
      "field": "checkOut",
      "message": "Ngày trả phòng phải sau ngày nhận phòng"
    }
  ]
}
```

Nếu bỏ `checkIn`, lỗi phải gắn vào `checkIn` do `@NotNull`; validator cấp lớp trả `true` khi một ngày vắng mặt. Nếu gửi ngày có định dạng không thể chuyển thành `LocalDate`, lỗi phát sinh ở bước chuyển đổi JSON trước khi chạy quy tắc so sánh.

## 4. Kiểm thử tự động

Có thể kiểm tra validator trực tiếp bằng Jakarta Validation mà không cần khởi động server hay gọi HTTP. Tệp `src/test/java/com/example/demo/validation/StayDatesValidatorTest.java`:

```java
package com.example.demo.validation;

import com.example.demo.api.BookingRequest;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StayDatesValidatorTest {

    @Test
    void acceptsValidDateOrder() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            var request = new BookingRequest(
                LocalDate.of(2026, 11, 10),
                LocalDate.of(2026, 11, 12)
            );

            assertTrue(validator.validate(request).isEmpty());
        }
    }

    @Test
    void rejectsWrongDateOrderOnCheckOutField() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            var request = new BookingRequest(
                LocalDate.of(2026, 11, 12),
                LocalDate.of(2026, 11, 10)
            );

            var violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertEquals(
                "checkOut",
                violations.iterator().next().getPropertyPath().toString()
            );
        }
    }

    @Test
    void delegatesMissingDateToNotNull() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            var request = new BookingRequest(
                null,
                LocalDate.of(2026, 11, 12)
            );

            var violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertEquals(
                "checkIn",
                violations.iterator().next().getPropertyPath().toString()
            );
        }
    }
}
```

Chạy:

```bash
./gradlew test
```

Các kiểm thử minh họa ba trạng thái cần thiết: dữ liệu hợp lệ, quan hệ giữa hai trường không hợp lệ, và một trường vắng mặt. Với hệ thống thực tế, hãy bổ sung trường hợp hai ngày bằng nhau, cả hai trường trống, input JSON sai định dạng, mapping sang HTTP 400, validation groups (nếu có) và nhiều vi phạm xuất hiện đồng thời.

## 5. Áp dụng cho quy tắc giữa các trường khác

Cùng một mẫu annotation + validator có thể diễn đạt các điều kiện có phụ thuộc:

| Tình huống | Điều kiện trên toàn đối tượng | Vị trí báo lỗi gợi ý |
| --- | --- | --- |
| Khoảng số | `min <= max` | `max` |
| Giao hàng | `method = HOME` thì `address` không trống | `address` |
| Đăng ký liên hệ | Có ít nhất một trong `email`, `phone` | Cấp đối tượng hoặc cả hai trường |
| Thời gian sự kiện | `endAt` sau `startAt` | `endAt` |
| Đơn đặt hàng | `discountCode` chỉ dùng với loại `promotionType` phù hợp | `discountCode` |

Ví dụ với địa chỉ giao hàng: kiểm tra field `address` độc lập bằng `@NotBlank` sẽ từ chối cả những đơn nhận tại cửa hàng. Ràng buộc cấp lớp cho phép diễn đạt chính xác *chỉ bắt buộc khi* `deliveryMethod == HOME`. Nếu lỗi có thể sửa trên một trường cụ thể, đặt `addPropertyNode("address")`. Nếu cần trả nhiều lỗi từ một lần kiểm tra, sau `disableDefaultConstraintViolation()` hãy xây dựng từng property-node violation và kết thúc mỗi nhánh bằng `addConstraintViolation()`; không chỉ trả `false` mà quên thêm violation.

Để hỗ trợ cùng một annotation cho nhiều kiểu đối tượng, phải thiết kế các `ConstraintValidator` tương ứng hoặc một abstraction phù hợp. Không nên ép kiểu sang DTO không tương thích, truyền tên field tùy ý rồi dùng reflection khắp nơi, hoặc gom nhiều quy tắc không liên quan vào một validator chỉ để tái sử dụng annotation.

## 6. Những điểm dễ nhầm

**Ràng buộc cấp lớp không tự biến thành lỗi ở một trường.** Mặc định vi phạm có đường dẫn đối tượng; muốn giao diện hiển thị cạnh một input, dùng `ConstraintValidatorContext` và `addPropertyNode` như ví dụ. Với Spring MVC, lỗi cấp đối tượng thường hiện trong `getGlobalErrors()`, còn lỗi có property node trong `getFieldErrors()`.

**`@Valid` và `@Validated` chỉ có tác dụng tại điểm được framework/validator gọi.** Chúng không khiến mọi thao tác `new BookingRequest(...)` tự động ném exception. Khi tạo đối tượng trong service, batch job hoặc test, phải có điểm validation tường minh hoặc đi qua cơ chế tích hợp thích hợp.

**Không bỏ qua null và lỗi kiểu dữ liệu.** Validator quan hệ phải định nghĩa chính xác trường hợp thiếu một phần dữ liệu; các annotation như `@NotNull`, `@NotBlank`, `@Email` kiểm tra từng trường. Bean Validation không sửa được JSON sai cú pháp hay lỗi parse ngày.

**Không giả định thứ tự constraint.** Provider có thể kiểm tra annotation cấp trường/cấp lớp theo thứ tự khác nhau. Dựa vào group sequence nếu thực sự cần tổ chức trình tự kiểm tra, nhưng thông thường chỉ cần logic null-safe, không tạo lỗi trùng.

**Không nhầm class-level constraint với cross-parameter constraint.** Class-level constraint so sánh các thuộc tính của **một đối tượng**. Cross-parameter validation dành cho quan hệ giữa các **tham số của một phương thức/constructor** và có hợp đồng validator khác.

**Không đặt tác dụng phụ vào `isValid`.** Tránh sửa DTO, ghi database, gọi API từ xa, gửi sự kiện hoặc giữ trạng thái của request trong validator. Điều này giúp validation ổn định, có thể tái sử dụng và kiểm thử dễ dàng.

**Chọn đúng định nghĩa nghiệp vụ.** `checkOut.isAfter(checkIn)` không cho phép hai ngày bằng nhau. Nếu yêu cầu cho phép bằng nhau, dùng `!checkOut.isBefore(checkIn)`. Với thời điểm có múi giờ, cần chọn kiểu thời gian và quy tắc timezone đúng; so sánh `LocalDate` chỉ là so sánh ngày lịch.

**Phân biệt Java/Spring phiên bản.** Ví dụ áp dụng Spring Framework 6 / Spring Boot 3 với `jakarta.validation.*`. Dự án Spring Boot 2 thường dùng `javax.validation.*` và dependency tương ứng, không trộn hai namespace trong cùng một ví dụ.

**Không thay thế invariant miền và bảo vệ dữ liệu.** Kiểm tra ở API giúp trả lỗi sớm; nếu quy tắc phải luôn đúng bất kể đường vào dữ liệu, hãy kiểm tra tại tầng domain/service và dùng ràng buộc cơ sở dữ liệu thích hợp khi khả thi.

## 7. Checklist khi tự triển khai

1. Viết quy tắc bằng một câu rõ ràng, bao gồm toán tử biên (`<` hay `<=`, có cho phép trống không).
2. Giữ annotation kiểm tra tính đơn lẻ trên trường; khai báo annotation `@Target(TYPE)` cho điều kiện liên trường.
3. Implement `ConstraintValidator<Annotation, DtoType>`, xử lý null rõ ràng và không dùng state của request.
4. Gắn annotation cấp lớp vào đúng DTO, record hoặc bean; kích hoạt bằng `@Valid`/`@Validated` tại boundary.
5. Chọn vị trí trả lỗi (object hay field) và định dạng API; không giả định tất cả exception validation có cùng kiểu.
6. Kiểm thử đủ ca hợp lệ, sai quan hệ, giá trị biên, thiếu trường và binding input sai.
7. Bảo đảm logic validation ở API nhất quán với invariant của nghiệp vụ; không dùng validator để thay cho kiểm tra cần truy vấn hoặc giao dịch.

**Điểm cốt lõi:** Khi tính hợp lệ phụ thuộc vào quan hệ giữa các trường, hãy kiểm tra ở cấp đối tượng bằng custom Bean Validation constraint; báo vi phạm tới trường phù hợp bằng `ConstraintValidatorContext`, đồng thời giữ các ràng buộc từng trường và logic nghiệp vụ ở đúng trách nhiệm của chúng.
