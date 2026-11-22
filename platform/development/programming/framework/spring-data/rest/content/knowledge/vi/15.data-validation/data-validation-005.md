# Đăng ký tường minh qua configureValidatingRepositoryEventListener

## Mục tiêu

Spring Data REST cung cấp các repository event để ứng dụng can thiệp vào vòng đời tạo, lưu, liên kết và xóa resource. Một cách đăng ký validation tường minh là triển khai `RepositoryRestConfigurer` và ghi đè callback `configureValidatingRepositoryEventListener(...)`.

Callback này nhận `ValidatingRepositoryEventListener`. Ứng dụng có thể đăng ký một hoặc nhiều Spring `Validator` cho từng lifecycle event, ví dụ:

- `beforeCreate`: kiểm tra dữ liệu trước khi tạo resource mới.
- `beforeSave`: kiểm tra dữ liệu trước khi lưu/cập nhật resource.
- `beforeLinkSave`: kiểm tra thay đổi association trước khi lưu liên kết.

Cách này đặt validation ở đúng thời điểm trong luồng repository REST, kể cả khi request đi qua endpoint được Spring Data REST tự tạo và không có controller riêng.

## 1. Repository event nằm ở đâu trong luồng request?

Giả sử repository Person được export tại `/api/people`. Một request POST tạo Person sẽ đi qua các bước khái quát:

1. Spring Data REST nhận diện collection resource và HTTP method POST.
2. Request body được chuyển thành domain object Person.
3. Các repository event trước khi tạo được phát ra.
4. `ValidatingRepositoryEventListener` gọi các validator đã đăng ký cho event tương ứng.
5. Nếu không có lỗi validation, Spring Data REST tiếp tục lưu entity qua repository.
6. Event sau thao tác được phát ra và response HTTP được tạo.

Với PUT/PATCH trên item, luồng cập nhật phát ra event trước khi lưu. Validator đăng ký cho `beforeSave` có thể kiểm tra trạng thái cuối cùng trước khi repository ghi dữ liệu.

Có thể hình dung:

~~~text
HTTP POST / PUT / PATCH
          |
          v
Spring Data REST resource handler
          |
          v
Deserialize request -> domain object
          |
          v
Repository lifecycle event
          |
          v
ValidatingRepositoryEventListener
          |
          +----> Validators registered for event
          |
          +----> Errors?
                    |
             yes    |    no
              v     |     v
       Reject request| Repository save
       (4xx response)|       |
                     |       v
                     |   HTTP response
~~~

Validation ở đây là một phần của luồng repository event. Nó không phải controller validation bằng `@Valid @RequestBody`, dù cả hai có thể cùng tồn tại trong một ứng dụng.

## 2. RepositoryRestConfigurer và callback đăng ký validator

`RepositoryRestConfigurer` là điểm cấu hình của Spring Data REST. Ta có thể triển khai interface này và ghi đè callback:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfigurer;
import org.springframework.data.rest.core.event.ValidatingRepositoryEventListener;

@Configuration
public class RepositoryRestValidationConfig
        implements RepositoryRestConfigurer {

    private final PersonValidator personValidator;

    public RepositoryRestValidationConfig(
            PersonValidator personValidator) {
        this.personValidator = personValidator;
    }

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener validatingListener) {

        validatingListener.addValidator("beforeCreate", personValidator);
        validatingListener.addValidator("beforeSave", personValidator);
    }
}
~~~

Các điểm cần chú ý:

- `configureValidatingRepositoryEventListener` được Spring Data REST gọi khi cấu hình validating event listener.
- `addValidator(eventName, validator)` gắn validator vào tên lifecycle event.
- Một validator có thể được đăng ký cho nhiều event nếu cùng quy tắc áp dụng.
- Callback này là nơi đăng ký; logic kiểm tra dữ liệu nên nằm trong lớp validator riêng để dễ đọc và tái sử dụng.

Trong ví dụ, cùng một `PersonValidator` được gọi trước khi tạo và trước khi lưu. Nếu quy tắc tạo mới và cập nhật khác nhau, hãy tạo validator riêng cho từng event hoặc phân nhánh theo trạng thái/use case một cách rõ ràng.

## 3. Viết một Spring Validator

Spring `Validator` có hai phương thức chính:

- `supports(Class<?> clazz)`: cho biết validator có xử lý kiểu object được truyền vào không.
- `validate(Object target, Errors errors)`: kiểm tra object và ghi lỗi vào `Errors`.

Ví dụ validator cho Person:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component
public class PersonValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return Person.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (!StringUtils.hasText(person.getFirstName())) {
            errors.rejectValue(
                "firstName",
                "person.firstName.required",
                "First name is required"
            );
        }

        if (!StringUtils.hasText(person.getLastName())) {
            errors.rejectValue(
                "lastName",
                "person.lastName.required",
                "Last name is required"
            );
        }

        if (person.getEmail() != null
                && !person.getEmail().contains("@")) {
            errors.rejectValue(
                "email",
                "person.email.invalid",
                "Email address is invalid"
            );
        }
    }
}
~~~

Giải thích:

- `supports` giúp validator chỉ nhận kiểu Person.
- `StringUtils.hasText` kiểm tra chuỗi không null, không rỗng và không chỉ chứa khoảng trắng.
- `rejectValue` ghi lỗi gắn với một field.
- Mã lỗi như `person.firstName.required` có thể được dùng để tra message trong message bundle.
- Validator không tự lưu entity; nó chỉ báo lỗi hoặc xác nhận dữ liệu hợp lệ.

Nếu validator dùng chung cho nhiều domain type, hãy kiểm tra kiểu bằng `supports` và tránh ép kiểu không an toàn. Mỗi validator nên có một phạm vi trách nhiệm rõ ràng.

## 4. Đăng ký theo từng lifecycle event

Tên event là chuỗi mà `ValidatingRepositoryEventListener` dùng để chọn validator. Các event trước thao tác thường gặp:

| Event name | Thời điểm | Ví dụ use case |
|---|---|---|
| `beforeCreate` | Trước khi tạo resource mới | POST vào collection |
| `beforeSave` | Trước khi lưu resource | PUT/PATCH hoặc thao tác save |
| `beforeLinkSave` | Trước khi lưu thay đổi liên kết | Gán hoặc thay đổi association |

Ví dụ đăng ký các validator khác nhau:

~~~java
@Override
public void configureValidatingRepositoryEventListener(
        ValidatingRepositoryEventListener listener) {

    listener.addValidator("beforeCreate", personCreateValidator);
    listener.addValidator("beforeSave", personUpdateValidator);
    listener.addValidator("beforeLinkSave", personLinkValidator);
}
~~~

Chọn event theo mục đích của quy tắc:

- Kiểm tra field bắt buộc khi tạo mới: `beforeCreate`.
- Kiểm tra trạng thái hợp lệ trước khi cập nhật: `beforeSave`.
- Kiểm tra association có được phép gắn vào entity hay không: `beforeLinkSave`.

Không đăng ký một validator cho mọi event chỉ để “chắc chắn”. Validator phải nhận đúng target type và kiểm tra đúng trạng thái tại thời điểm event. Với các thao tác có semantics khác nhau, tách validator giúp tránh áp dụng nhầm quy tắc.

Tên event phải khớp chính xác với event key được Spring Data REST hỗ trợ. Nếu gõ sai tên, validator sẽ không chạy ở lifecycle mong muốn. Hãy kiểm tra tên event trong API/version Spring Data REST đang dùng.

## 5. Validation lỗi được phản ánh ra HTTP như thế nào?

Nếu validator thêm lỗi vào `Errors`, Spring Data REST dừng thao tác ghi và trả lỗi validation cho client. Một response thường gặp là `400 Bad Request`, với representation mô tả field/global errors tùy phiên bản và cấu hình.

Ví dụ client gửi:

~~~http
POST /api/people
Content-Type: application/json
Accept: application/hal+json

{
  "firstName": "",
  "lastName": "Nguyen",
  "email": "invalid-email"
}
~~~

Vì `firstName` rỗng và email không hợp lệ, validator thêm hai lỗi. Repository không nên tiếp tục lưu entity khi các lỗi validation này được phát hiện.

Response lỗi có thể chứa các chi tiết tương tự:

~~~json
{
  "errors": [
    {
      "entity": "Person",
      "property": "firstName",
      "message": "First name is required"
    },
    {
      "entity": "Person",
      "property": "email",
      "message": "Email address is invalid"
    }
  ]
}
~~~

Đây là ví dụ minh họa cấu trúc lỗi; tên field, message, media type và hình dạng response thực tế phụ thuộc phiên bản Spring Data REST, exception handler và cấu hình ứng dụng.

Nếu validation thành công, luồng xử lý tiếp tục lưu entity và trả response thành công theo thao tác, ví dụ 201 Created cho POST tạo resource.

## 6. Phân biệt repository event validation với Bean Validation

Có nhiều lớp validation trong ứng dụng Spring:

| Cơ chế | Được kích hoạt ở đâu? | Dùng khi nào? |
|---|---|---|
| Spring `Validator` đăng ký qua repository event | Trong lifecycle của Spring Data REST repository | Quy tắc cần chạy khi resource được tạo/lưu/liên kết qua repository REST |
| Bean Validation (`@NotNull`, `@NotBlank`, `@Email`) | Thông qua Bean Validation provider và tích hợp framework | Ràng buộc khai báo ngay trên DTO/domain property |
| Controller validation (`@Valid`) | Khi Spring MVC bind và validate controller argument | Endpoint custom controller nhận request DTO |
| Service/domain validation | Trong application service hoặc domain method | Quy tắc nghiệp vụ cần áp dụng cho nhiều loại giao diện/API |

Các cơ chế này có thể bổ sung cho nhau. Ví dụ, Bean Validation kiểm tra email đúng định dạng, còn repository event validator kiểm tra quy tắc phụ thuộc vào trạng thái entity hoặc dữ liệu hiện tại.

Không nên đặt toàn bộ quy tắc ở một tầng duy nhất nếu cùng nghiệp vụ có thể được gọi qua REST, batch job, message consumer hoặc service khác. Quy tắc domain quan trọng cần được bảo vệ ở service/domain boundary để không bị bỏ qua khi request không đi qua Spring Data REST.

## 7. Validation không thay thế authorization

Validator trả lời câu hỏi: **dữ liệu có hợp lệ để tiếp tục thao tác không?** Authorization trả lời câu hỏi: **người dùng hiện tại có được phép thực hiện thao tác này không?**

Ví dụ:

- Email có đúng định dạng không? Đây là validation.
- Người dùng có quyền đổi email của Person này không? Đây là authorization.
- Trạng thái hiện tại có cho phép chuyển sang APPROVED không? Đây là business rule/state transition.
- Người dùng có thuộc tenant sở hữu Person không? Đây thường là authorization theo resource.

Không dùng validator như cơ chế phân quyền duy nhất. Validator có thể không có đủ context về principal, tenant, policy hoặc resource ownership. Hãy thực thi quyền bằng Spring Security và application service/domain policy phù hợp.

## 8. Đăng ký validator theo cách dễ bảo trì

Một cấu trúc thường dùng:

~~~text
config/
  RepositoryRestValidationConfig.java

validation/
  PersonValidator.java
  PersonCreateValidator.java
  PersonUpdateValidator.java
  PersonLinkValidator.java

repository/
  PersonRepository.java

domain/
  Person.java
~~~

Quy ước:

- Đặt validator trong package được component scan.
- Đăng ký rõ ràng qua callback cấu hình.
- Dùng constructor injection thay vì tự tạo validator bằng `new` nếu validator có dependency.
- Giữ `supports` chính xác với domain type.
- Tách quy tắc dùng chung thành service/helper nếu nhiều validator cần dùng.
- Không thực hiện side effect trong validator, chẳng hạn lưu dữ liệu, gửi email hoặc gọi hệ thống ngoài.
- Validator nên dễ kiểm thử độc lập.

Ví dụ validator cần repository để kiểm tra email trùng:

~~~java
@Component
public class PersonCreateValidator implements Validator {

    private final PersonRepository repository;

    public PersonCreateValidator(PersonRepository repository) {
        this.repository = repository;
    }

    @Override
    public boolean supports(Class<?> clazz) {
        return Person.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (person.getEmail() != null
                && repository.existsByEmail(person.getEmail())) {
            errors.rejectValue(
                "email",
                "person.email.duplicate",
                "Email address is already in use"
            );
        }
    }
}
~~~

Khi cập nhật, kiểm tra trùng cần loại trừ chính entity hiện tại. Vì vậy, validator cho `beforeSave` có thể cần logic khác với validator tạo mới. Tránh dùng một truy vấn exists đơn giản khiến một Person bị báo email trùng với chính email của nó.

## 9. Kiểm tra bằng integration test

Nên kiểm tra cả hai nhánh: dữ liệu hợp lệ được lưu và dữ liệu không hợp lệ bị từ chối.

Ví dụ với MockMvc:

~~~java
mockMvc.perform(
        post("/api/people")
            .contentType("application/json")
            .accept("application/hal+json")
            .content("""
                {
                  "firstName": "An",
                  "lastName": "Nguyen",
                  "email": "an@example.com"
                }
                """)
    )
    .andExpect(status().isCreated());
~~~

Kiểm tra dữ liệu không hợp lệ:

~~~java
mockMvc.perform(
        post("/api/people")
            .contentType("application/json")
            .accept("application/hal+json")
            .content("""
                {
                  "firstName": "",
                  "lastName": "Nguyen",
                  "email": "invalid"
                }
                """)
    )
    .andExpect(status().isBadRequest());
~~~

Ngoài HTTP integration test, kiểm thử trực tiếp validator:

~~~java
PersonValidator validator = new PersonValidator();
Person person = new Person();
person.setFirstName("");
person.setLastName("Nguyen");

BeanPropertyBindingResult errors =
        new BeanPropertyBindingResult(person, "person");

validator.validate(person, errors);

assertThat(errors.hasErrors()).isTrue();
assertThat(errors.hasFieldErrors("firstName")).isTrue();
~~~

Tên constructor, dependency và cấu hình test cần điều chỉnh theo project. Integration test xác nhận callback đã đăng ký validator đúng event; unit test xác nhận logic validate từng trường hợp.

## 10. Lỗi thường gặp khi validator không chạy

Nếu request không bị từ chối dù dữ liệu sai, kiểm tra:

1. Class cấu hình có được Spring component scan và được Spring Data REST nhận diện không?
2. Class có triển khai đúng `RepositoryRestConfigurer` không?
3. Có ghi đè đúng signature `configureValidatingRepositoryEventListener(ValidatingRepositoryEventListener)` không?
4. Event key có chính xác, ví dụ `beforeCreate` hay `beforeSave`?
5. Validator có được đăng ký cho đúng event của thao tác đang thử không?
6. `supports(clazz)` có trả true cho domain type thực tế không?
7. Logic có ghi lỗi qua `Errors` hay chỉ log message?
8. Request có thực sự đi qua Spring Data REST repository endpoint hay qua custom controller khác?
9. Có cấu hình exception handler làm thay đổi error response không?
10. Có test chứng minh validator chạy ở cả create và update không?

Nếu validator chạy nhưng request vẫn được lưu, hãy kiểm tra cách đăng ký và việc validator có thêm lỗi vào Errors. Chỉ log lỗi hoặc ném log message không thay thế việc báo lỗi qua cơ chế validation mà listener mong đợi.

## 11. Ghi nhớ

- `configureValidatingRepositoryEventListener` là callback của `RepositoryRestConfigurer` để đăng ký validator cho repository lifecycle events.
- `ValidatingRepositoryEventListener.addValidator(eventName, validator)` gắn Spring Validator với một event.
- `beforeCreate` thường dùng cho POST tạo resource; `beforeSave` dùng cho thao tác lưu/cập nhật; `beforeLinkSave` dùng cho thay đổi association.
- Spring `Validator` triển khai `supports` và `validate`; ghi lỗi bằng `Errors`.
- Validation lỗi thường khiến thao tác bị từ chối với 400 Bad Request; response chi tiết phụ thuộc cấu hình/version.
- Repository event validation khác với controller `@Valid` và Bean Validation, dù có thể phối hợp.
- Validation không thay thế authorization hoặc domain policy.
- Không tạo side effect trong validator; giữ logic kiểm tra dễ kiểm thử và đăng ký đúng event.

## Tài liệu tham khảo

- [Spring Data REST Reference — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST Reference — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST API — RepositoryRestConfigurer](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/config/RepositoryRestConfigurer.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
