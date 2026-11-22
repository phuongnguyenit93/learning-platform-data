# Đăng ký validator bằng tiền tố bean beforeCreate và beforeSave

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích Spring Data REST gọi validator tại các thời điểm nào trong vòng đời tài nguyên.
- Đăng ký validator bằng tên bean có tiền tố **beforeCreate** hoặc **beforeSave**.
- Viết validator theo giao diện **org.springframework.validation.Validator**.
- Sử dụng **supports**, **validate** và **Errors** để kiểm tra dữ liệu.
- Phân biệt quy tắc khi tạo mới với quy tắc trước khi lưu/cập nhật.
- Kiểm tra validation qua HTTP và biết khi nào nên dùng đăng ký thủ công.

## 1. Vì sao cần validator trong Spring Data REST?

Spring Data REST tự công bố repository thành HTTP API. Client có thể gửi POST để tạo entity hoặc PUT/PATCH để thay đổi một entity hiện có. Trước khi dữ liệu được lưu, ứng dụng cần kiểm tra các quy tắc nghiệp vụ như:

- Tên bắt buộc phải có.
- Email phải được cung cấp khi tạo tài khoản.
- Tuổi hoặc số lượng không được âm.
- Trạng thái mới phải phù hợp với trạng thái hiện tại.
- Một trường không được thay đổi sau khi tài nguyên đã được tạo.

Spring Data REST cung cấp cơ chế validation gắn với repository events. Bạn có thể đăng ký một **Validator** cho một event cụ thể để kiểm tra entity tại thời điểm phù hợp. Cơ chế này hữu ích khi muốn kiểm soát dữ liệu đi vào qua REST endpoint do Spring Data REST tạo ra.

## 2. Hai tiền tố bean quan trọng

Cách đăng ký đơn giản nhất là đặt tên bean theo mẫu:

~~~text
<event><DomainType>Validator
~~~

Trong đó:

- **event** là tiền tố event mà Spring Data REST nhận biết.
- **DomainType** là tên class domain, thường dùng simple class name với chữ hoa đầu.
- **Validator** là hậu tố dễ nhận biết cho bean.

Ví dụ với domain class **Person**:

| Tên bean | Event được gắn | Thời điểm sử dụng |
|---|---|---|
| **beforeCreatePersonValidator** | **beforeCreate** | Trước khi tạo một Person mới |
| **beforeSavePersonValidator** | **beforeSave** | Trước khi lưu một Person |

Hai tiền tố biểu thị hai event khác nhau:

- **beforeCreate** dùng cho quy tắc chỉ áp dụng khi tạo tài nguyên mới, thường là request POST tới collection.
- **beforeSave** dùng cho quy tắc cần chạy trước khi lưu tài nguyên, thường gặp khi cập nhật item qua PUT hoặc PATCH.

Đừng đặt tên bean tùy ý rồi mong Spring Data REST tự đoán event. Tiền tố phải khớp chính xác với tên event; phần tên domain type cũng phải khớp với class mà validator hỗ trợ.

## 3. Validator cần triển khai giao diện nào?

Spring Data REST sử dụng giao diện **org.springframework.validation.Validator** của Spring Framework.

Một validator có hai phương thức chính:

~~~java
public interface Validator {

    boolean supports(Class<?> clazz);

    void validate(Object target, Errors errors);
}
~~~

Ý nghĩa:

- **supports(Class<?> clazz)** cho biết validator có xử lý loại object được đưa vào hay không.
- **validate(Object target, Errors errors)** kiểm tra object và ghi lỗi vào đối tượng Errors nếu dữ liệu không hợp lệ.

Khi có lỗi, dùng **errors.rejectValue(...)** để gắn lỗi với một thuộc tính cụ thể. Spring Data REST đọc các lỗi này trong quá trình xử lý event và ngăn dữ liệu không hợp lệ tiếp tục được lưu.

Không nên tự tạo HTTP response từ validator. Validator chỉ chịu trách nhiệm kiểm tra dữ liệu và ghi nhận lỗi; tầng Spring Data REST xử lý kết quả validation.

## 4. Đăng ký validator cho beforeCreate

Giả sử entity Person có tên, email và tuổi:

~~~java
public class Person {

    private Long id;
    private String name;
    private String email;
    private Integer age;

    // Constructors, getters and setters
}
~~~

Tạo validator chạy trước khi tạo mới:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component("beforeCreatePersonValidator")
public class BeforeCreatePersonValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return Person.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (!StringUtils.hasText(person.getName())) {
            errors.rejectValue(
                "name",
                "person.name.required",
                "Tên không được để trống"
            );
        }

        if (!StringUtils.hasText(person.getEmail())) {
            errors.rejectValue(
                "email",
                "person.email.required",
                "Email là bắt buộc khi tạo mới"
            );
        }

        if (person.getAge() == null || person.getAge() < 0) {
            errors.rejectValue(
                "age",
                "person.age.invalid",
                "Tuổi phải là số không âm"
            );
        }
    }
}
~~~

Điểm quyết định là tên bean:

~~~java
@Component("beforeCreatePersonValidator")
~~~

Spring Data REST nhận ra tiền tố **beforeCreate**, xác định event cần gắn và liên kết validator với domain type Person.

Validator này tập trung vào dữ liệu cần có khi tạo mới. Ví dụ, nếu email là bắt buộc khi đăng ký Person mới, quy tắc đó có thể được đặt tại beforeCreate.

Nếu bean được tạo bằng phương thức **@Bean**, tên phương thức cũng chính là tên bean mặc định:

~~~java
@Bean
Validator beforeCreatePersonValidator() {
    return new BeforeCreatePersonValidator();
}
~~~

Chọn một cách đăng ký phù hợp với cấu trúc ứng dụng: **@Component** hoặc **@Bean**. Không cần tạo hai bean cùng tên.

## 5. Đăng ký validator cho beforeSave

Khi cập nhật một Person đã tồn tại, ứng dụng có thể cần kiểm tra các quy tắc trước khi lưu. Tạo validator riêng:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component("beforeSavePersonValidator")
public class BeforeSavePersonValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return Person.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (!StringUtils.hasText(person.getName())) {
            errors.rejectValue(
                "name",
                "person.name.required",
                "Tên không được để trống"
            );
        }

        if (person.getAge() != null && person.getAge() < 18) {
            errors.rejectValue(
                "age",
                "person.age.minimum",
                "Tuổi phải từ 18 trở lên"
            );
        }
    }
}
~~~

Tên bean:

~~~java
@Component("beforeSavePersonValidator")
~~~

Tiền tố **beforeSave** gắn validator với event BeforeSave. Quy tắc trong ví dụ yêu cầu Person có tuổi tối thiểu 18 khi được lưu qua luồng cập nhật.

Hai validator có thể chứa các quy tắc khác nhau:

- beforeCreate kiểm tra dữ liệu bắt buộc khi đăng ký.
- beforeSave kiểm tra các điều kiện phải đúng trước khi lưu thay đổi.

Nếu một quy tắc phải đúng ở cả hai thời điểm, hãy đặt nó trong cả hai validator hoặc tổ chức logic dùng chung để tránh lặp code. Đừng chỉ kiểm tra ở beforeCreate nếu dữ liệu đó vẫn có thể bị thay đổi về sau.

## 6. Cách đặt tên cho domain type khác

Tiền tố event đứng trước tên domain class. Ví dụ với **PurchaseOrder**:

~~~java
@Component("beforeCreatePurchaseOrderValidator")
public class BeforeCreatePurchaseOrderValidator implements Validator {
    // supports và validate
}
~~~

Với event lưu:

~~~java
@Component("beforeSavePurchaseOrderValidator")
public class BeforeSavePurchaseOrderValidator implements Validator {
    // supports và validate
}
~~~

Một số ví dụ tên bean:

| Domain type | Trước khi tạo | Trước khi lưu |
|---|---|---|
| Person | **beforeCreatePersonValidator** | **beforeSavePersonValidator** |
| Product | **beforeCreateProductValidator** | **beforeSaveProductValidator** |
| PurchaseOrder | **beforeCreatePurchaseOrderValidator** | **beforeSavePurchaseOrderValidator** |

Hãy dùng đúng simple class name của domain type. Nếu class có tên PurchaseOrder, không đặt tên bean thành beforeCreateOrderValidator trừ khi domain type thực sự là Order.

Phương thức **supports** vẫn cần kiểm tra class. Tên bean giúp Spring Data REST gắn validator với event/domain type; supports xác nhận validator có thể xử lý object nhận được.

## 7. Đăng ký thủ công qua RepositoryRestConfigurer

Nếu không muốn dựa vào quy ước tên bean, Spring Data REST cho phép đăng ký validator trực tiếp với **ValidatingRepositoryEventListener**.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.event.ValidatingRepositoryEventListener;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

@Configuration
public class RestValidationConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {

        listener.addValidator(
            "beforeCreate",
            new BeforeCreatePersonValidator()
        );

        listener.addValidator(
            "beforeSave",
            new BeforeSavePersonValidator()
        );
    }
}
~~~

Phương thức **addValidator(eventName, validator)** gắn validator với event được chỉ định. Tên event ở đây là **beforeCreate** và **beforeSave**.

Đây là cách thay thế cho đăng ký bằng bean name. Nếu đã dùng bean name convention cho cùng validator, không đăng ký lại cùng logic thủ công, vì có thể khiến một quy tắc chạy nhiều lần.

Nếu ứng dụng đã có một lớp RepositoryRestConfigurer, hãy bổ sung cấu hình vào lớp hiện có thay vì tạo nhiều cấu hình cạnh tranh.

## 8. Bean name convention và đăng ký thủ công

| Tiêu chí | Bean name convention | Đăng ký thủ công |
|---|---|---|
| Cách làm | Đặt tên bean theo event và domain type | Gọi addValidator trong RepositoryRestConfigurer |
| Ví dụ | **beforeCreatePersonValidator** | **addValidator("beforeCreate", validator)** |
| Ưu điểm | Ít cấu hình, dễ tìm theo domain type | Chủ động kiểm soát cách gắn validator |
| Phù hợp | Phần lớn trường hợp thông thường | Khi cần tập trung đăng ký hoặc tạo validator theo cấu hình |
| Lưu ý | Tên bean phải đúng quy ước | Phải gắn đúng event và tránh đăng ký trùng |

Spring Data REST khuyến nghị cách đặt tiền tố bean cho phần lớn tình huống. Đăng ký thủ công hữu ích khi ứng dụng cần quản lý validator tập trung hoặc muốn xây dựng validator theo điều kiện cấu hình.

## 9. Validation hoạt động trong luồng HTTP như thế nào?

Giả sử PersonRepository được công bố:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Client gửi POST để tạo Person:

~~~http
POST /api/people
Content-Type: application/json
Accept: application/hal+json

{
  "name": "",
  "email": "",
  "age": -1
}
~~~

Spring Data REST chuyển body thành object Person, phát event trước khi tạo và gọi validator đã đăng ký cho event đó. Validator ghi lỗi vào Errors. Khi có lỗi validation, thao tác lưu bị từ chối và response trả thông tin lỗi cho client; status thường là **400 Bad Request**.

Một request hợp lệ có thể là:

~~~http
POST /api/people
Content-Type: application/json
Accept: application/hal+json

{
  "name": "Lan",
  "email": "lan@example.com",
  "age": 25
}
~~~

Với thao tác cập nhật item:

~~~http
PUT /api/people/42
Content-Type: application/json
Accept: application/hal+json

{
  "name": "Lan Nguyen",
  "email": "lan@example.com",
  "age": 25
}
~~~

Luồng lưu item sử dụng event beforeSave. Validator tương ứng kiểm tra object trước khi thay đổi được lưu.

Chi tiết body lỗi có thể thay đổi theo phiên bản Spring Data REST, cấu hình exception handling và cách ứng dụng tùy chỉnh error representation. Client nên kiểm tra status code và đọc response body thay vì phụ thuộc vào một cấu trúc lỗi cố định.

## 10. Kiểm tra validator bằng curl

Thử tạo dữ liệu không hợp lệ:

~~~bash
curl -i -X POST \
  -H "Accept: application/hal+json" \
  -H "Content-Type: application/json" \
  -d '{"name":"","email":"","age":-1}' \
  http://localhost:8080/api/people
~~~

Quan sát:

- Status code có báo validation failure không.
- Response body có chỉ ra field nào không hợp lệ không.
- Thông báo lỗi có đúng với rejectValue đã khai báo không.
- Entity có bị lưu khi validation thất bại không.

Sau đó thử dữ liệu hợp lệ:

~~~bash
curl -i -X POST \
  -H "Accept: application/hal+json" \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","email":"lan@example.com","age":25}' \
  http://localhost:8080/api/people
~~~

Đọc Location hoặc self link trong response để xác định URI của Person vừa tạo. Dùng URI đó để thử cập nhật với dữ liệu vi phạm quy tắc beforeSave.

Ví dụ cập nhật tuổi không hợp lệ:

~~~bash
curl -i -X PATCH \
  -H "Accept: application/hal+json" \
  -H "Content-Type: application/merge-patch+json" \
  -d '{"age":16}' \
  http://localhost:8080/api/people/42
~~~

Media type và semantics PATCH phụ thuộc cấu hình Spring Data REST của ứng dụng. Nếu API không bật merge patch, hãy dùng phương thức cập nhật và Content-Type mà API hỗ trợ. Mục đích của phép thử là xác nhận validator beforeSave được gọi trong luồng lưu item.

## 11. Phân biệt Spring Validator và Bean Validation

Spring có nhiều cách kiểm tra dữ liệu. Không nên nhầm **org.springframework.validation.Validator** với **Jakarta Bean Validation**.

| Cơ chế | Đặc điểm | Ví dụ |
|---|---|---|
| Spring Validator | Viết logic Java trong supports/validate và ghi lỗi qua Errors | **beforeCreatePersonValidator** |
| Jakarta Bean Validation | Khai báo constraint trên field/property hoặc class | **@NotBlank**, **@Email**, **@Min** |
| Repository event handler | Xử lý event theo domain type, có thể phục vụ logic ngoài validation | **@HandleBeforeSave** |

Bean Validation phù hợp với constraint khai báo được và có thể tái sử dụng ở nhiều tầng. Spring Validator phù hợp với logic cần code, cần kiểm tra nhiều field cùng lúc hoặc phụ thuộc trạng thái nghiệp vụ.

Có thể kết hợp hai cơ chế, nhưng cần hiểu chúng được kích hoạt và cấu hình như thế nào trong ứng dụng. Không mặc định rằng chỉ đặt annotation Bean Validation là mọi luồng ghi Spring Data REST đều đã chạy đầy đủ quy tắc mong muốn.

## 12. Giới hạn và nguyên tắc sử dụng

### Validator gắn với Spring Data REST event

Validator được đăng ký theo các event của REST exporter. Nó phù hợp để bảo vệ luồng ghi qua repository resource do Spring Data REST quản lý.

Nếu service khác gọi trực tiếp **repository.save(...)**, không nên mặc định validator gắn với Spring Data REST event cũng được gọi. Nếu quy tắc phải áp dụng cho mọi luồng ghi, hãy đặt logic ở domain/service hoặc dùng cơ chế validation phù hợp với tất cả entry point.

### Không đặt side effect trong validator

Validator nên kiểm tra và ghi nhận lỗi. Tránh gửi email, gọi hệ thống ngoài, ghi audit hoặc thay đổi dữ liệu khác trong phương thức validate. Những side effect đó phù hợp hơn với service hoặc event handler chuyên trách sau khi thao tác đã thành công.

### Không dùng validator thay authorization

Validator kiểm tra dữ liệu có hợp lệ hay không. Nó không xác định người dùng có quyền sửa entity hoặc field hay không. Authorization phải được thực hiện riêng ở server.

### Quy tắc cập nhật có thể cần so sánh trạng thái cũ

Trong beforeSave, object có thể đã được bind từ request. Nếu quy tắc cần biết giá trị trước khi cập nhật, hãy lấy trạng thái cũ qua service/repository theo cách an toàn và kiểm soát transaction. Đừng giả định validator luôn có sẵn một bản snapshot của entity trước khi thay đổi.

### Kiểm tra đúng event

Nếu validator không chạy, kiểm tra tên bean, domain type, supports và repository có được Spring Data REST phát hiện hay không. Nếu dùng đăng ký thủ công, kiểm tra event name truyền cho addValidator. Đồng thời kiểm tra request có thực sự đi qua endpoint Spring Data REST hay được xử lý bởi controller khác.

## 13. Lỗi thường gặp

### Bean được tạo nhưng validator không chạy

Tên bean không có tiền tố event hợp lệ hoặc phần domain type sai. Dùng tên như **beforeCreatePersonValidator** và kiểm tra component scan.

### supports trả về false

Validator được gắn đúng event nhưng không nhận class thực tế. Kiểm tra điều kiện supports và kiểu domain object.

### Gắn nhầm beforeCreate và beforeSave

Quy tắc chỉ dành cho tạo mới được đặt ở beforeSave hoặc ngược lại. Xác định event phù hợp với thao tác HTTP và đăng ký đúng tiền tố.

### Lỗi field không xuất hiện như mong đợi

Tên field trong rejectValue phải khớp property của object. Kiểm tra lỗi binding và cấu hình error response.

### Validator chạy hai lần

Cùng logic được đăng ký cả bằng bean name và addValidator thủ công. Chọn một cách đăng ký cho mỗi validator/event.

### Validation chỉ chạy khi gọi REST API

Đây là phạm vi của Spring Data REST event integration. Nếu dữ liệu còn được ghi qua service, batch job hoặc message consumer, hãy đặt quy tắc dùng chung ở tầng phù hợp.

### Dùng validator để sửa dữ liệu

Validator có thể đọc object và ghi lỗi. Chuẩn hóa dữ liệu hoặc thay đổi trạng thái nên được xử lý rõ ràng ở tầng chuyển đổi/service phù hợp để tránh side effect khó dự đoán.

## 14. Ghi nhớ

- Spring Data REST gắn Validator với event thông qua tiền tố bean name.
- **beforeCreatePersonValidator** chạy ở event trước khi tạo Person.
- **beforeSavePersonValidator** gắn với event trước khi lưu Person.
- Validator triển khai **supports(Class<?>)** và **validate(Object, Errors)**.
- Dùng **errors.rejectValue(...)** để ghi lỗi theo field.
- Có thể đăng ký thủ công bằng **ValidatingRepositoryEventListener.addValidator(...)** trong RepositoryRestConfigurer.
- Chọn một cơ chế đăng ký cho mỗi validator/event để tránh chạy trùng.
- Validator của Spring Data REST bảo vệ luồng ghi qua REST exporter; quy tắc dùng chung cần được đặt ở tầng phù hợp.
- Validation không thay thế authorization, transaction hoặc kiểm soát side effect.

## Tài liệu tham khảo

- [Spring Data REST Reference — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST Reference — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Framework — Validator API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/Validator.html)
