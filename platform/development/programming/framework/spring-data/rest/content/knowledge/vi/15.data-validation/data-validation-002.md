# Khai báo Jakarta Bean Validation và xác minh điểm thực sự kích hoạt

Jakarta Bean Validation cho phép khai báo quy tắc kiểm tra dữ liệu ngay trên model bằng annotation như **`@NotNull`**, **`@NotBlank`**, **`@Email`**, **`@Size`** hoặc **`@Positive`**. Tuy nhiên, annotation chỉ mô tả constraint. Để constraint được thực thi, ứng dụng phải có một Bean Validation provider và một luồng xử lý thực sự gọi validator.

Với Spring Data REST, cần xác định rõ request đi qua điểm kích hoạt nào. Có thể dùng validator gắn với repository event **`beforeCreate`** hoặc **`beforeSave`**. Nếu dùng Spring Data JPA, persistence provider còn có thể kích hoạt Bean Validation tại lifecycle **`PrePersist`** và **`PreUpdate`**. Hai cơ chế này độc lập và có thời điểm thực thi khác nhau.

## 1. Thêm Jakarta Bean Validation provider

Nếu dùng Spring Boot, thêm dependency validation starter để có API và provider triển khai:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Với ứng dụng không dùng Spring Boot, cần khai báo Jakarta Validation API và một provider tương thích, chẳng hạn Hibernate Validator. Chỉ có annotation API mà không có provider thì không thể thực hiện việc kiểm tra constraint.

Trong Spring Framework, **`LocalValidatorFactoryBean`** khởi tạo Bean Validation provider và đồng thời thích nghi với cả hai interface:

- **`jakarta.validation.Validator`**
- **`org.springframework.validation.Validator`**

Điểm thứ hai quan trọng vì Spring Data REST đăng ký validator thông qua contract **`org.springframework.validation.Validator`**.

## 2. Khai báo constraint trên entity

Ví dụ entity Person:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @NotBlank(message = "Name must not be blank")
    @Size(max = 80, message = "Name must be at most 80 characters")
    private String name;

    @NotBlank(message = "Email is required")
    @Email(message = "Email format is invalid")
    private String email;

    @Positive(message = "Age must be greater than zero")
    private Integer age;

    // getters and setters
}
~~~

Một số constraint thường dùng:

| Annotation | Quy tắc |
|---|---|
| **`@NotNull`** | Giá trị không được null |
| **`@NotBlank`** | Chuỗi không được null, rỗng hoặc chỉ có khoảng trắng |
| **`@NotEmpty`** | Chuỗi, collection, map hoặc array không được null và phải có phần tử |
| **`@Size(min, max)`** | Giới hạn độ dài hoặc số phần tử |
| **`@Email`** | Giá trị chuỗi phải có dạng email hợp lệ theo provider |
| **`@Min`** / **`@Max`** | Giới hạn số nguyên hoặc giá trị số |
| **`@Positive`** / **`@PositiveOrZero`** | Giá trị phải dương hoặc không âm |
| **`@Pattern`** | Giá trị chuỗi phải khớp regular expression |

Cần kết hợp constraint theo ý nghĩa nghiệp vụ. Ví dụ **`@Email`** cho phép null, nên nếu email bắt buộc phải có, hãy kết hợp **`@NotBlank`** hoặc **`@NotNull`**.

Đặt annotation trên field hoặc getter theo một chiến lược nhất quán. Với JPA, vị trí annotation cũng liên quan đến cách entity truy cập field/property. Tránh khai báo cùng một constraint ở cả field và getter nếu điều đó khiến validator kiểm tra trùng.

## 3. Cascade validation với @Valid

Constraint trên một object không tự động có nghĩa các object lồng bên trong cũng được kiểm tra. Dùng **`@Valid`** tại thuộc tính cần cascade validation.

Ví dụ Address là embeddable của Person:

~~~java
import jakarta.persistence.Embeddable;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@Embeddable
public class Address {

    @NotBlank
    private String city;

    @Size(max = 120)
    private String street;

    // getters and setters
}
~~~

~~~java
import jakarta.persistence.Embedded;
import jakarta.validation.Valid;

@Entity
public class Person {

    // Các thuộc tính khác...

    @Embedded
    @Valid
    private Address address;

    // getters and setters
}
~~~

Khi Person được validate, **`@Valid`** yêu cầu validator tiếp tục kiểm tra các constraint của Address. Nếu thiếu **`@Valid`**, các constraint bên trong object lồng nhau có thể không được cascade từ lần validate Person đó.

Với JPA entity association, cần lưu ý quy tắc riêng của Jakarta Persistence: validation lifecycle mặc định không cascade sang entity association chỉ vì đặt **`@Valid`** trên association. Embeddable cần **`@Valid`** để được cascade. Nếu cần kiểm tra entity liên quan, hãy thiết kế luồng nghiệp vụ hoặc validator phù hợp và tránh vô tình tải lazy association.

## 4. Phân biệt khai báo constraint và điểm kích hoạt

Đây là điểm quan trọng nhất khi xác minh validation:

- **`@NotBlank`**, **`@Email`** và các constraint khác chỉ mô tả điều kiện.
- **`jakarta.validation.Validator`** thực thi các constraint khi được gọi.
- **`LocalValidatorFactoryBean`** kết nối Jakarta Bean Validation với Spring Validator.
- Spring Data REST gọi validator đã được gắn vào repository event.
- JPA provider có thể gọi Bean Validation trong lifecycle persistence nếu integration được bật và provider có mặt.

Vì vậy, không nên kết luận rằng validation đã hoạt động chỉ vì entity có annotation hoặc ứng dụng khởi động thành công.

## 5. Kích hoạt validation tại repository event của Spring Data REST

Spring Data REST có **`ValidatingRepositoryEventListener`** để gọi các Spring Validator tại các event tương ứng. Cách đơn giản là đặt tên bean theo tiền tố event và kiểu domain.

Ví dụ đăng ký validator cho Person khi tạo mới và khi cập nhật:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class RestValidationConfiguration {

    @Bean
    public LocalValidatorFactoryBean beforeCreatePersonValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Bean
    public LocalValidatorFactoryBean beforeSavePersonValidator() {
        return new LocalValidatorFactoryBean();
    }
}
~~~

Spring Data REST nhận diện các tên bean:

- **`beforeCreatePersonValidator`**: chạy trước khi entity Person mới được lưu.
- **`beforeSavePersonValidator`**: chạy trước khi entity Person hiện có được lưu.

**`LocalValidatorFactoryBean`** triển khai Spring Validator, nên Spring Data REST có thể gọi nó. Khi được gọi, nó thực thi các annotation Jakarta Bean Validation trên object và chuyển violation thành lỗi Spring Validation.

Có thể đăng ký cùng một validator cho nhiều event bằng cách cấu hình thủ công thay vì đặt tên bean.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfigurer;
import org.springframework.data.rest.core.event.ValidatingRepositoryEventListener;
import org.springframework.validation.Validator;

@Configuration
public class RestValidationConfiguration
        implements RepositoryRestConfigurer {

    private final Validator validator;

    public RestValidationConfiguration(Validator validator) {
        this.validator = validator;
    }

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {
        listener.addValidator("beforeCreate", validator);
        listener.addValidator("beforeSave", validator);
    }
}
~~~

Chọn một cách đăng ký phù hợp với cấu hình ứng dụng. Nếu dùng bean name prefix, kiểm tra bean có đúng tên và được Spring quản lý. Nếu đăng ký thủ công, kiểm tra **`configureValidatingRepositoryEventListener`** được gọi và validator được thêm vào đúng event.

## 6. Xác định event tương ứng với request

Các thao tác REST khác nhau phát ra các repository event khác nhau:

| Thao tác | Event trước khi xử lý | Ý nghĩa |
|---|---|---|
| **POST /people** | **`beforeCreate`** | Kiểm tra entity mới trước khi lưu |
| **PUT /people/{id}** | **`beforeSave`** | Kiểm tra entity hiện có trước khi lưu |
| **PATCH /people/{id}** | **`beforeSave`** | Kiểm tra entity hiện có trước khi lưu |
| Cập nhật association resource | **`beforeLinkSave`** | Event trước khi lưu liên kết |
| **DELETE /people/{id}** | **`beforeDelete`** | Event trước khi xóa |

Tên event được dùng khi đăng ký validator là phần tên đứng trước trong bean name, ví dụ **`beforeCreate`** và **`beforeSave`**. Có thể gắn validator riêng cho từng domain type bằng cách thêm tên entity vào bean name.

Một request GET chỉ đọc dữ liệu và không đi qua các event lưu entity này. Nếu cần kiểm tra dữ liệu đầu vào của một endpoint tìm kiếm, phải cấu hình cơ chế validation phù hợp cho endpoint đó.

## 7. Phân biệt repository event với JPA lifecycle validation

Khi dùng Spring Data JPA với provider có tích hợp Jakarta Bean Validation, persistence provider có thể tự kiểm tra entity tại các lifecycle:

- **`PrePersist`**: trước khi insert entity mới.
- **`PreUpdate`**: trước khi cập nhật entity.
- **`PreRemove`**: chỉ khi cấu hình validation group cho remove; mặc định không nên giả định thao tác xóa được validate.

Cơ chế JPA này có thể áp dụng cho thao tác persist/update từ REST, service hoặc batch vì nó chạy ở tầng persistence. Tuy nhiên, nó không phải là Spring Data REST repository event.

| Cơ chế | Điểm kích hoạt | Phạm vi |
|---|---|---|
| Spring Data REST validator | **`beforeCreate`**, **`beforeSave`**, event được đăng ký | Các thao tác đi qua REST exporter |
| JPA Bean Validation | **`PrePersist`**, **`PreUpdate`** | Các thao tác persistence qua JPA khi integration hoạt động |
| Spring MVC **`@Valid`** | Sau khi bind request body vào tham số controller | Endpoint controller có khai báo validation |
| Method validation với **`@Validated`** | Khi gọi method qua proxy validation | Method/service được cấu hình method validation |

Một validator hoạt động ở một điểm không chứng minh các điểm còn lại cũng hoạt động. Ví dụ, JPA lifecycle validation có thể chặn một lần flush trong khi Spring Data REST event validator chưa được đăng ký.

Nếu ứng dụng không dùng JPA, không thể dựa vào **`PrePersist`** hoặc **`PreUpdate`**; hãy dùng validator của Spring Data REST hoặc cơ chế validation của persistence module tương ứng.

## 8. Dùng @Valid trong controller riêng

Nếu ứng dụng có controller Spring MVC tùy chỉnh bên cạnh repository resource, có thể kích hoạt validation cho request body bằng **`@Valid`**:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PersonController {

    @PostMapping("/custom-people")
    public ResponseEntity<Void> create(
            @Valid @RequestBody PersonRequest request) {
        // Xử lý request đã được validate
        return ResponseEntity.noContent().build();
    }
}
~~~

Trong ví dụ, Spring MVC validate **`PersonRequest`** sau khi bind JSON vào object. Đây là điểm kích hoạt của controller, không phải cấu hình validator cho repository event của Spring Data REST.

Với method validation ở service, cần cấu hình method validation của Spring và dùng **`@Validated`** trên bean phù hợp. Không nhầm **`@Valid`** để cascade object với **`@Validated`** để bật method validation.

## 9. Xác minh validation thực sự chạy

Nên kiểm tra bằng integration test qua HTTP và xác nhận cả response lẫn trạng thái database.

### Kiểm tra POST — beforeCreate

Gửi dữ liệu sai constraint:

~~~http
POST /people
Content-Type: application/json
Accept: application/hal+json
~~~

~~~json
{
  "name": "   ",
  "email": "not-an-email",
  "age": -2
}
~~~

Nếu **`beforeCreatePersonValidator`** được đăng ký đúng, request phải bị từ chối bởi các constraint. Kiểm tra response lỗi validation và xác nhận không có Person không hợp lệ được lưu.

Sau đó gửi dữ liệu hợp lệ:

~~~json
{
  "name": "An Nguyen",
  "email": "an@example.com",
  "age": 28
}
~~~

Request hợp lệ phải tạo được resource theo contract của repository.

### Kiểm tra PUT hoặc PATCH — beforeSave

Tạo trước một Person hợp lệ, sau đó gửi PUT hoặc PATCH làm vi phạm constraint, ví dụ email sai định dạng. Xác nhận validator **`beforeSavePersonValidator`** chạy và dữ liệu không hợp lệ không được lưu.

### Kiểm tra JPA lifecycle riêng

Nếu muốn xác minh JPA provider, gọi repository save trong test và ép flush:

~~~java
@Test
void invalidEntityIsRejectedAtJpaLifecycle() {
    Person person = new Person();
    person.setName(" ");
    person.setEmail("invalid");

    assertThrows(
        ConstraintViolationException.class,
        () -> {
            personRepository.saveAndFlush(person);
        }
    );
}
~~~

Test này xác minh đường đi qua JPA lifecycle khi provider được cấu hình. Nó không thay thế test HTTP cho Spring Data REST event.

### Kiểm tra event thực tế

Có thể đặt breakpoint hoặc log trong validator để xác nhận:

1. Request đi vào đúng endpoint.
2. Event tương ứng được phát ra.
3. Validator được gọi với đúng domain object.
4. Constraint violation được ghi nhận.
5. Repository không lưu entity sai dữ liệu.

Nếu chỉ thấy database báo lỗi NOT NULL hoặc unique constraint, đó chưa phải bằng chứng rằng Jakarta Bean Validation đã được kích hoạt. Đó có thể là lỗi persistence/database xảy ra muộn hơn.

## 10. Nhóm validation và thông báo lỗi

Jakarta Bean Validation hỗ trợ validation group để áp dụng các quy tắc khác nhau theo ngữ cảnh:

~~~java
public interface OnCreate {
}

public interface OnUpdate {
}
~~~

~~~java
@NotBlank(groups = { OnCreate.class, OnUpdate.class })
private String name;

@NotNull(groups = OnCreate.class)
private String externalCode;
~~~

Mặc định validator chạy nhóm **`Default`**. Nếu dùng group tùy chỉnh, phải cấu hình validator hoặc luồng gọi để thực sự yêu cầu các group đó; chỉ khai báo **`groups`** trên annotation chưa đủ.

Thông báo lỗi có thể đặt trực tiếp trong annotation hoặc dùng message bundle:

~~~java
@NotBlank(message = "{person.name.required}")
private String name;
~~~

Ví dụ file **`ValidationMessages.properties`**:

~~~properties
person.name.required=Name is required.
person.email.invalid=Please enter a valid email address.
~~~

Với Spring Data REST event validator, lỗi từ Spring Validator được biểu diễn qua **`Errors`** và có thể phát sinh **`RepositoryConstraintViolationException`**. Cách trả response cuối cùng còn phụ thuộc exception handler và cấu hình ứng dụng; integration test nên kiểm tra contract thực tế mà client nhận được.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Annotation có nhưng POST vẫn lưu dữ liệu sai | Chưa có provider hoặc validator chưa gắn với **`beforeCreate`** | Kiểm tra dependency và bean name/event registration |
| POST bị chặn nhưng PUT vẫn lưu sai | Chỉ đăng ký validator cho **`beforeCreate`** | Đăng ký thêm **`beforeSave`** |
| REST event validation không chạy khi gọi service trực tiếp | Repository event của Spring Data REST không được phát ra bởi đường gọi đó | Kiểm tra JPA lifecycle hoặc gọi validator trong service |
| Object lồng nhau không được kiểm tra | Thiếu **`@Valid`** ở thuộc tính cần cascade | Thêm **`@Valid`** và kiểm tra cascade path |
| JPA không cascade validation sang entity association | Quy tắc lifecycle của JPA không cascade validation qua entity associations | Validate association trong logic nghiệp vụ phù hợp; không dựa vào cascade mặc định |
| Constraint group không được áp dụng | Validator đang chạy nhóm **`Default`** | Cấu hình group được yêu cầu tại đúng điểm gọi |
| Chỉ database constraint phát hiện lỗi | Bean Validation chưa chạy hoặc constraint không tương đương | Kiểm tra provider, event, annotation và test validator độc lập |

## 12. Checklist xác minh

- Dependency có Jakarta Validation API và provider tương thích.
- Entity có constraint đúng với quy tắc nghiệp vụ.
- Object lồng nhau có **`@Valid`** khi cần cascade.
- Spring Data REST có validator bean đúng tên hoặc đã đăng ký thủ công.
- **`beforeCreate`** được kiểm tra cho POST.
- **`beforeSave`** được kiểm tra cho PUT/PATCH.
- Nếu cập nhật quan hệ, xem xét **`beforeLinkSave`**.
- Nếu dùng JPA, kiểm tra riêng **`PrePersist`** và **`PreUpdate`**.
- Test request sai phải bị từ chối trước khi dữ liệu không hợp lệ được lưu.
- Test request đúng phải thành công.
- Xác minh qua log, breakpoint hoặc integration test để biết chính xác validator nào đã chạy.

Tài liệu tham khảo chính thức:

- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Framework — Java Bean Validation and LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jakarta Persistence — Automatic Bean Validation lifecycle events](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
- [Jakarta Validation Specification](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.pdf)
