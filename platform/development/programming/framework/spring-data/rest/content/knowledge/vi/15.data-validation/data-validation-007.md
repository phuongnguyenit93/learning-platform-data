# Kiểm tra trường bắt buộc, ràng buộc chéo trường và thông báo đa ngôn ngữ trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể khai báo trường bắt buộc bằng Bean Validation; kiểm tra quan hệ giữa nhiều trường trong cùng một entity; kích hoạt validator đúng thời điểm Spring Data REST tạo hoặc cập nhật resource; kiểm tra object lồng; và trả thông báo lỗi theo ngôn ngữ của client.

## 1. Validation nằm ở đâu trong luồng ghi dữ liệu?

Một request ghi dữ liệu đi qua nhiều bước: Spring Data REST nhận request, chuyển body thành domain object, chạy các bước xử lý trước khi lưu, gọi repository và cuối cùng persistence provider ghi dữ liệu.

Validation nên chạy trước khi dữ liệu được lưu để request không hợp lệ bị từ chối tại ranh giới API. Có thể chia quy tắc thành ba nhóm:

- **Ràng buộc từng trường:** tên không được để trống, email đúng định dạng, số lượng phải dương.
- **Ràng buộc giữa nhiều trường:** ngày kết thúc không trước ngày bắt đầu, ngày giao hàng nằm trong khoảng cho phép, hoặc một trường bắt buộc khi trường khác có giá trị nhất định.
- **Quy tắc nghiệp vụ phụ thuộc hệ thống:** email đã được sử dụng chưa, người dùng có quyền tạo bản ghi trong tenant đó không, hoặc trạng thái có được phép chuyển đổi không.

Jakarta Bean Validation phù hợp với hai nhóm đầu vì quy tắc có thể khai báo ngay trên domain model và tái sử dụng. Nhóm thứ ba thường cần service hoặc validator có thể truy cập repository và security context. Không nên đặt side effect như gửi email hoặc ghi database trong `ConstraintValidator`.

## 2. Thêm Bean Validation và khai báo trường bắt buộc

Với Spring Boot 3 trở lên, dùng dependency `spring-boot-starter-validation`. Các annotation thuộc namespace `jakarta.validation`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Ví dụ entity Booking:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;
import java.time.LocalDate;

@Entity
public class Booking {

    @Id
    @GeneratedValue
    private Long id;

    @NotBlank(message = "{booking.customer.required}")
    @Size(max = 120, message = "{booking.customer.size}")
    private String customerName;

    @NotNull(message = "{booking.startDate.required}")
    private LocalDate startDate;

    @NotNull(message = "{booking.endDate.required}")
    private LocalDate endDate;

    @NotNull(message = "{booking.amount.required}")
    @Positive(message = "{booking.amount.positive}")
    private BigDecimal amount;

    protected Booking() {
    }

    // Constructor, getters và setters
}
```

Một số annotation thường dùng:

| Annotation | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `@NotNull` | Giá trị không được là null | Không kiểm tra chuỗi rỗng hoặc khoảng trắng |
| `@NotBlank` | Chuỗi phải có ít nhất một ký tự không phải khoảng trắng | Dùng cho `String` hoặc `CharSequence` |
| `@NotEmpty` | Chuỗi, collection, map hoặc array không được rỗng | Không thay thế kiểm tra nội dung từng phần tử |
| `@Size(min, max)` | Giới hạn độ dài hoặc số phần tử | Giá trị null thường vẫn hợp lệ; kết hợp `@NotNull` nếu cần |
| `@Email` | Kiểm tra hình dạng địa chỉ email | Không chứng minh mailbox tồn tại; kết hợp `@NotBlank` nếu email bắt buộc |
| `@Positive`, `@Min`, `@Max` | Giới hạn số | Chọn kiểu số và giới hạn phù hợp nghiệp vụ |
| `@Past`, `@Future` | Ràng buộc ngày/giờ so với hiện tại | Kiểm tra múi giờ và thời điểm tham chiếu nếu nghiệp vụ nhạy với thời gian |

Ví dụ, `@Email` không tự làm email thành trường bắt buộc vì giá trị null có thể được xem là hợp lệ đối với constraint này. Nếu email bắt buộc, kết hợp:

```java
@NotBlank(message = "{customer.email.required}")
@Email(message = "{customer.email.invalid}")
private String email;
```

Không dùng một annotation duy nhất để biểu diễn nhiều ý nghĩa khác nhau. Tách quy tắc giúp thông báo lỗi chính xác và client biết cần sửa điều gì.

## 3. Đăng ký validator vào vòng đời Spring Data REST

Spring Data REST phát các repository events quanh thao tác tạo, cập nhật, thay đổi association và xóa. Hai thời điểm thường dùng để kiểm tra entity là:

- `beforeCreate`: trước khi lưu entity mới được tạo qua collection resource.
- `beforeSave`: trước khi lưu entity đang được cập nhật qua item resource.

Spring Data REST hỗ trợ hai cách gắn validator:

1. Đặt tên bean theo mẫu `<event><DomainType>Validator`, ví dụ `beforeCreateBookingValidator`.
2. Đăng ký thủ công validator với `ValidatingRepositoryEventListener` trong `RepositoryRestConfigurer`.

Ví dụ đăng ký Bean Validation cho cả thao tác tạo và cập nhật:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.event.ValidatingRepositoryEventListener;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class RepositoryValidationConfiguration
        implements RepositoryRestConfigurer {

    private final LocalValidatorFactoryBean beanValidator;

    public RepositoryValidationConfiguration(
            LocalValidatorFactoryBean beanValidator) {
        this.beanValidator = beanValidator;
    }

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {

        listener.addValidator("beforeCreate", beanValidator);
        listener.addValidator("beforeSave", beanValidator);
    }
}
```

Trong Spring Boot, provider Bean Validation thường được cung cấp qua dependency validation starter. Nếu ứng dụng chưa có bean `LocalValidatorFactoryBean`, có thể khai báo một bean:

```java
@Bean
LocalValidatorFactoryBean beanValidator(MessageSource messageSource) {
    LocalValidatorFactoryBean validator = new LocalValidatorFactoryBean();
    validator.setValidationMessageSource(messageSource);
    return validator;
}
```

Đặt method `@Bean` trong một lớp `@Configuration` và inject cùng validator vào configurer. Nếu ứng dụng đã có validator được Spring Boot cấu hình, hãy dùng bean hiện có và chỉ cấu hình message source khi cần. Không tạo nhiều validator không cần thiết hoặc đăng ký cùng một validator nhiều lần cho cùng event.

Có thể dùng event name `beforeLinkSave` khi cần kiểm tra một association trước khi lưu liên kết. Các event khác như `afterCreate`, `afterSave`, `beforeDelete` và `afterDelete` phục vụ những thời điểm khác trong vòng đời resource; validator dùng để từ chối dữ liệu nên thường chạy ở event trước khi lưu.

Lưu ý: việc khai báo `@NotBlank` trên entity không tự bảo đảm mọi đường ghi trong ứng dụng đều chạy qua Spring Data REST validation listener. Nếu service hoặc custom controller ghi trực tiếp qua repository, hãy gọi Bean Validation hoặc áp dụng validation ở service/controller tương ứng.

## 4. Kiểm tra object lồng bằng @Valid

Nếu entity chứa object lồng, constraint trên object con chỉ được kiểm tra đệ quy khi bật cascade validation bằng `@Valid`.

Ví dụ:

```java
import jakarta.persistence.Embeddable;
import jakarta.persistence.Embedded;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

@Embeddable
public class ContactDetails {

    @NotBlank(message = "{contact.phone.required}")
    @Pattern(
        regexp = "^[0-9+() -]{8,20}$",
        message = "{contact.phone.invalid}"
    )
    private String phone;

    @NotBlank(message = "{contact.country.required}")
    private String country;

    // Getters và setters
}

@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    @NotNull(message = "{customer.contact.required}")
    @Valid
    @Embedded
    private ContactDetails contactDetails;

    // Constructor, getters và setters
}
```

Hai annotation có vai trò riêng:

- `@NotNull` trên `contactDetails` yêu cầu object con phải tồn tại.
- `@Valid` yêu cầu validator tiếp tục kiểm tra các constraint bên trong `ContactDetails`.

Nếu chỉ có `@Valid` mà không có `@NotNull`, object con null không có nội dung để kiểm tra và không tự bị coi là lỗi. Với collection, có thể dùng container element validation như `List<@Valid LineItem>` để kiểm tra từng phần tử; thêm `@NotEmpty` nếu collection bắt buộc phải có ít nhất một phần tử.

## 5. Ràng buộc chéo trường bằng class-level constraint

Các annotation như `@NotNull`, `@Positive` hoặc `@Size` thường kiểm tra từng property. Khi quy tắc phụ thuộc đồng thời vào nhiều property, tạo custom constraint ở cấp class.

Ví dụ yêu cầu `endDate` phải bằng hoặc sau `startDate`. Trước hết, khai báo annotation:

```java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Constraint(validatedBy = BookingPeriodValidator.class)
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidBookingPeriod {

    String message() default "{booking.period.invalid}";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

Tiếp theo, triển khai validator:

```java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class BookingPeriodValidator
        implements ConstraintValidator<ValidBookingPeriod, Booking> {

    @Override
    public boolean isValid(
            Booking booking,
            ConstraintValidatorContext context) {

        if (booking == null
                || booking.getStartDate() == null
                || booking.getEndDate() == null) {
            // @NotNull trên từng trường chịu trách nhiệm kiểm tra null.
            return true;
        }

        boolean valid =
                !booking.getEndDate().isBefore(booking.getStartDate());

        if (!valid) {
            context.disableDefaultConstraintViolation();
            context.buildConstraintViolationWithTemplate(
                    context.getDefaultConstraintMessageTemplate())
                .addPropertyNode("endDate")
                .addConstraintViolation();
        }

        return valid;
    }
}
```

Gắn constraint lên entity:

```java
@Entity
@ValidBookingPeriod
public class Booking {

    @NotNull(message = "{booking.startDate.required}")
    private LocalDate startDate;

    @NotNull(message = "{booking.endDate.required}")
    private LocalDate endDate;

    // Các property, constructor, getters và setters
}
```

Validator trả về true nếu khoảng ngày hợp lệ. Khi ngày kết thúc trước ngày bắt đầu, nó tạo violation gắn với property `endDate`, giúp client biết trường nào cần sửa. Hai trường null được xử lý bởi `@NotNull` riêng nên không phát sinh thêm lỗi khoảng ngày gây nhiễu.

Cùng kỹ thuật này có thể dùng cho:

- `password` và `confirmPassword` phải trùng nhau.
- `minimumPrice` không lớn hơn `maximumPrice`.
- Chỉ yêu cầu `companyTaxCode` khi `customerType = COMPANY`.
- Ngày hiệu lực phải nằm trong khoảng thời hạn của hợp đồng.

Với quy tắc cần truy vấn database hoặc quyền của người dùng, dùng Spring Validator/service phù hợp thay vì biến constraint thành nơi thực hiện nghiệp vụ có side effect.

## 6. Thông báo validation đa ngôn ngữ

Không hard-code thông báo tiếng Việt hoặc tiếng Anh trực tiếp trong annotation nếu API phục vụ nhiều locale. Dùng message key:

```java
@NotBlank(message = "{booking.customer.required}")
private String customerName;
```

Đặt resource bundle ở classpath root. Ví dụ `messages.properties` chứa thông điệp mặc định:

```properties
booking.customer.required=Customer name is required.
booking.customer.size=Customer name must not exceed {max} characters.
booking.startDate.required=Start date is required.
booking.endDate.required=End date is required.
booking.amount.required=Amount is required.
booking.amount.positive=Amount must be greater than zero.
booking.period.invalid=End date must be on or after start date.
contact.phone.required=Phone number is required.
contact.phone.invalid=Phone number format is invalid.
contact.country.required=Country is required.
customer.contact.required=Contact details are required.
```

Tạo file `messages_vi.properties` cho tiếng Việt:

```properties
booking.customer.required=Vui lòng nhập tên khách hàng.
booking.customer.size=Tên khách hàng không được vượt quá {max} ký tự.
booking.startDate.required=Vui lòng nhập ngày bắt đầu.
booking.endDate.required=Vui lòng nhập ngày kết thúc.
booking.amount.required=Vui lòng nhập số tiền.
booking.amount.positive=Số tiền phải lớn hơn 0.
booking.period.invalid=Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.
contact.phone.required=Vui lòng nhập số điện thoại.
contact.phone.invalid=Số điện thoại không đúng định dạng.
contact.country.required=Vui lòng nhập quốc gia.
customer.contact.required=Vui lòng cung cấp thông tin liên hệ.
```

Có thể thêm `messages_en.properties` nếu muốn quản lý tiếng Anh riêng. Spring Boot tự cấu hình `MessageSource` khi có bundle mặc định `messages.properties`; cấu hình basename nếu dùng tên hoặc vị trí khác:

```properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

Spring Boot tích hợp application `MessageSource` với việc phân giải thông điệp Bean Validation. Với ứng dụng Spring không dùng cấu hình Boot này, `LocalValidatorFactoryBean.setValidationMessageSource(messageSource)` cho phép dùng Spring `MessageSource` thay cho bundle mặc định của Bean Validation.

Nếu locale resolver của ứng dụng lấy ngôn ngữ từ HTTP `Accept-Language`, client có thể yêu cầu thông báo tiếng Việt:

```http
POST /bookings
Content-Type: application/json
Accept: application/hal+json
Accept-Language: vi
```

Locale thực tế còn phụ thuộc cấu hình locale resolver và message source. Hãy kiểm tra request đi qua Spring MVC/Spring Data REST có dùng đúng locale mong muốn hay không; không suy luận ngôn ngữ chỉ từ nội dung JSON.

Trong message template, `{max}`, `{min}` và các thuộc tính constraint khác được nội suy thành giá trị tương ứng. Giữ nguyên placeholder trong các file dịch để thông báo vẫn hiển thị giới hạn chính xác.

## 7. API trả lỗi validation như thế nào?

Khi validator được đăng ký cho event và dữ liệu không hợp lệ, Spring Data REST từ chối thao tác trước khi lưu. Với validator kiểu Spring `Errors`, lỗi được đóng gói trong `RepositoryConstraintViolationException`; exception này giữ lại danh sách lỗi để tầng REST tạo response.

Validation failure thường được trả như lỗi request, phổ biến là `400 Bad Request`. Cấu trúc body cụ thể phụ thuộc phiên bản Spring Data REST, media type, exception handler và cấu hình của ứng dụng. Hãy đọc response thực tế thay vì giả định mọi phiên bản có cùng JSON error schema.

Ví dụ client gửi khoảng ngày không hợp lệ:

```http
POST /bookings
Content-Type: application/json
Accept: application/hal+json
Accept-Language: vi

{
  "customerName": "Ada",
  "startDate": "2026-06-20",
  "endDate": "2026-06-10",
  "amount": 150
}
```

Kết quả mong đợi là request bị từ chối và thông báo `booking.period.invalid` được phân giải theo locale hiện tại. Không có Booking mới được lưu.

Với API công khai, nên giữ thông báo ngắn, có thể hành động và không để lộ stack trace, SQL, tên bảng, dữ liệu nhạy cảm hoặc thông tin nội bộ. Nếu client cần xử lý lỗi bằng mã ổn định, trả thêm error code riêng thay vì buộc client phân tích câu chữ đã dịch.

## 8. Kiểm tra validation trên POST và PATCH/PUT

Kiểm tra ít nhất các trường hợp sau:

1. Bỏ trường bắt buộc như `customerName`; xác nhận `@NotBlank` hoặc `@NotNull` phát hiện lỗi.
2. Gửi chuỗi chỉ chứa khoảng trắng; xác nhận `@NotBlank` từ chối.
3. Gửi số âm cho `amount`; xác nhận `@Positive` từ chối.
4. Gửi ngày kết thúc trước ngày bắt đầu; xác nhận class-level constraint phát hiện lỗi chéo trường.
5. Bỏ toàn bộ object `contactDetails`; xác nhận `@NotNull` trên object cha phát hiện lỗi.
6. Gửi object `contactDetails` nhưng thiếu `phone`; xác nhận `@Valid` kích hoạt validation lồng.
7. Gửi cùng payload với `Accept-Language: vi` và `Accept-Language: en`; xác nhận message bundle được chọn đúng.
8. Cập nhật resource bằng `PATCH` hoặc `PUT`; xác nhận validator được gắn vào `beforeSave` và trạng thái entity sau binding vẫn thỏa các quy tắc.

Ví dụ dùng curl để kiểm tra thông báo tiếng Việt:

```bash
curl -i -X POST http://localhost:8080/bookings \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -H "Accept-Language: vi" \
  -d '{
    "customerName": "Ada",
    "startDate": "2026-06-20",
    "endDate": "2026-06-10",
    "amount": 150
  }'
```

Với `PATCH`, Spring Data REST áp dụng body lên resource hiện có rồi phát event lưu. Kiểm tra trạng thái sau khi binding để tránh hiểu nhầm rằng mọi field không có trong payload đều trở thành null. Nếu cần quy tắc khác nhau giữa tạo và cập nhật, cân nhắc validation groups hoặc validator riêng cho `beforeCreate` và `beforeSave`.

## 9. Phân biệt validation ứng dụng với ràng buộc database

Bean Validation cải thiện thông báo lỗi và chặn dữ liệu sai trước khi lưu, nhưng không thay thế constraint ở database.

Ví dụ kiểm tra email đã tồn tại bằng cách query repository trước khi lưu có thể giúp trả thông báo thân thiện. Tuy nhiên, hai request đồng thời vẫn có thể cùng vượt qua bước kiểm tra. Unique constraint ở database mới là lớp bảo vệ cuối cùng cho tính duy nhất.

Nên kết hợp:

- Bean Validation cho required fields, định dạng, giới hạn và ràng buộc chéo trường.
- Service/domain logic cho quy tắc phụ thuộc dữ liệu hiện tại hoặc người dùng.
- Database constraints cho tính toàn vẹn cần được bảo đảm ngay cả khi có request đồng thời hoặc đường ghi khác API.
- Exception handling để chuyển lỗi persistence thành response ổn định, không lộ chi tiết nội bộ.

## 10. Các lỗi cấu hình thường gặp

**Annotation có nhưng request vẫn được lưu**

Kiểm tra validation starter/provider có trên classpath không; validator có được Spring Data REST đăng ký vào đúng event không; bean name có đúng mẫu nếu dùng auto-wiring theo tên không; hoặc configurer đã gọi `addValidator` chưa.

**Tạo mới được kiểm tra nhưng cập nhật không được kiểm tra**

Có thể validator chỉ đăng ký ở `beforeCreate`. Thêm validator vào `beforeSave` nếu quy tắc cũng phải áp dụng cho PUT/PATCH.

**Object lồng không bị kiểm tra**

Thêm `@Valid` trên property hoặc container element cần cascade. Nếu object bắt buộc phải có, thêm `@NotNull` riêng.

**Lỗi chéo trường không xuất hiện**

Bảo đảm constraint được đặt ở cấp class bằng `@Target(ElementType.TYPE)`, validator được đăng ký qua Bean Validation và class-level annotation thực sự nằm trên entity đang được validate.

**Thông báo chỉ có key hoặc không đổi ngôn ngữ**

Kiểm tra file bundle mặc định có tồn tại, tên basename, encoding UTF-8, message key viết đúng và locale của request. Nếu dùng Spring `MessageSource` trực tiếp, cấu hình `LocalValidatorFactoryBean.setValidationMessageSource(...)`.

**Custom endpoint không chạy validator của Spring Data REST**

Repository event listener chỉ xử lý các thao tác đi qua luồng event của Spring Data REST. Với controller/service tự viết, kích hoạt validation bằng `@Valid`, `@Validated` hoặc gọi validator phù hợp trong chính luồng đó.

## Tóm tắt

- Dùng `@NotBlank`, `@NotNull`, `@Size`, `@Email` và các constraint phù hợp để kiểm tra từng trường.
- Dùng class-level constraint cùng `ConstraintValidator` cho quy tắc phụ thuộc nhiều trường; gắn violation vào property liên quan để client dễ sửa.
- Dùng `@Valid` để cascade validation vào object lồng; kết hợp `@NotNull` nếu object con bắt buộc phải có.
- Đăng ký validator vào Spring Data REST qua bean name như `beforeCreateBookingValidator` hoặc qua `RepositoryRestConfigurer` và `ValidatingRepositoryEventListener`.
- Gắn validator vào cả `beforeCreate` và `beforeSave` nếu quy tắc áp dụng cho tạo mới lẫn cập nhật.
- Dùng message key và resource bundle theo locale; kiểm tra `Accept-Language`, `MessageSource` và locale resolver.
- Kết hợp validation ứng dụng với business rules và database constraints để bảo đảm dữ liệu hợp lệ trên mọi đường ghi.

## Tài liệu tham khảo

- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Spring Boot — Internationalization](https://docs.spring.io/spring-boot/reference/features/internationalization.html)
- [RepositoryConstraintViolationException API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/RepositoryConstraintViolationException.html)
