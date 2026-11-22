# Gắn giá trị vào constructor hoặc thuộc tính trong Spring Data Binding

## 1. Bước này nằm ở đâu trong luồng xử lý?

Khi Spring MVC nhận dữ liệu form hoặc query string cho một tham số `@ModelAttribute`, framework cần tạo hoặc lấy đối tượng đích, chuyển các giá trị đầu vào (thường là chuỗi) sang kiểu Java và **gắn chúng vào đúng vị trí**. Hai cách gắn chính là:

- **Constructor binding:** lấy giá trị theo tên tham số constructor, chuyển kiểu rồi truyền vào constructor khi **tạo đối tượng**. Phù hợp với `record` và DTO bất biến.
- **Property binding (setter binding):** dùng tên thuộc tính để tìm đường dẫn property có thể ghi và gọi setter trên **đối tượng đã tồn tại**. Phù hợp với JavaBean có trạng thái thay đổi được.

Ví dụ request `POST /registrations` có body `application/x-www-form-urlencoded`:

```text
email=lan@example.com&age=24
```

Spring có thể biến hai chuỗi `"lan@example.com"` và `"24"` thành một `Registration(String email, Integer age)` bằng constructor, hoặc thành các lệnh `setEmail(...)` và `setAge(...)` trên JavaBean. `"24"` phải được chuyển từ `String` sang `Integer` trước khi gán.

Luồng khái quát:

```text
HTTP request (form/query/path/header)
    -> chọn/tạo đối tượng @ModelAttribute
    -> đọc tên và giá trị đầu vào
    -> đổi kiểu bằng ConversionService / Formatter / PropertyEditor
    -> truyền tham số constructor và/hoặc gọi setter
    -> ghi nhận lỗi chuyển kiểu / binding vào BindingResult
    -> (nếu được yêu cầu) chạy validation
    -> chuyển đối tượng tới controller
```

Đây là **data binding**, khác với dependency injection (`@Autowired`, constructor injection của Spring bean) và khác với JSON body dùng `@RequestBody` / `HttpMessageConverter`. Trong Spring MVC, nguồn binding của `@ModelAttribute` chủ yếu gồm request parameters (form và query), đồng thời có thể gồm URI variables hoặc headers nếu không trùng tên với request parameter.

## 2. Gắn giá trị bằng constructor

### Cách hoạt động

1. Spring xác định lớp đích và constructor dữ liệu phù hợp.
2. Với mỗi tham số constructor, tìm giá trị đầu vào theo **tên tham số**; có thể đổi tên bằng `@BindParam`.
3. Chuyển kiểu từng giá trị, ví dụ `age=24` thành `Integer.valueOf(24)`.
4. Gọi constructor để tạo đối tượng. Với đối tượng lồng nhau, Spring có thể dựng đệ quy bằng các đường dẫn thuộc tính tương ứng.
5. Đưa lỗi binding/chuyển kiểu vào `BindingResult` nếu có; chỉ xem đối tượng đã được tạo thành công khi việc khởi tạo thực sự thành công.

Ví dụ controller đầy đủ trong **một ứng dụng Spring MVC đã cấu hình**, dùng Java 17+ và Spring Framework 6.1+:

```java
package demo;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {

    public record Registration(String email, Integer age) {}

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<String> create(
            @ModelAttribute Registration registration,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body("Invalid registration");
        }

        return ResponseEntity.ok(
                registration.email() + " / " + registration.age());
    }
}
```

Sau khi chạy ứng dụng Spring MVC chứa controller trên:

```bash
curl -i -X POST http://localhost:8080/registrations -d "email=lan@example.com&age=24"
```

Phần **response body** dự kiến:

```text
lan@example.com / 24
```

`Registration` là `record`; các component được truyền qua constructor chuẩn và không cần setter. Ở ví dụ này, `BindingResult` bắt lỗi chuyển kiểu như `age=abc`, nhưng **không tự kiểm tra** email đúng định dạng hoặc tuổi hợp lệ nếu chưa khai báo quy tắc validation.

### Tên tham số phải khớp

Với lớp Java thông thường dùng constructor có tham số, tên tham số cần có trong metadata bytecode (thường biên dịch với `-parameters`) hoặc được khai báo ánh xạ thích hợp. Với tên request khác tên Java, dùng `@BindParam`:

```java
import org.springframework.web.bind.annotation.BindParam;

public record PersonInput(
        @BindParam("full-name") String fullName,
        Integer age) {}
```

Khi đó `full-name=Lan%20Nguyen&age=24` có thể đi vào `fullName`. `@BindParam` là ánh xạ tên dữ liệu cho constructor binding; nó không thay thế kiểm tra hợp lệ của dữ liệu.

**Lưu ý chọn constructor:** một lớp dùng cho constructor binding nên có một data constructor rõ ràng. Nếu nhiều constructor cùng tồn tại, quy tắc chọn constructor của Spring có thể ưu tiên constructor mặc định khi có; không nên để lựa chọn mơ hồ. Với trường hợp dữ liệu web, `record` hoặc DTO có constructor chính minh bạch thường dễ hiểu hơn.

## 3. Gắn giá trị bằng thuộc tính (property/setter binding)

### Cách hoạt động

1. Đối tượng đích đã được tạo hoặc lấy từ model (ví dụ qua no-arg constructor).
2. `DataBinder` sử dụng cơ chế property của `BeanWrapper` để tìm property tương ứng với khóa đầu vào.
3. Chuyển giá trị về kiểu khai báo của setter/property.
4. Gọi setter như `setDisplayName("Lan")`, `setAge(24)`; giá trị mới thay đổi trạng thái của đối tượng.
5. Ghi nhận lỗi gán/chuyển kiểu trong `BindingResult`.

Ví dụ controller khác, cũng dùng trong một ứng dụng Spring MVC đã cấu hình:

```java
package demo;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/profiles")
public class ProfileController {

    public static class ProfileForm {
        private String displayName;
        private Integer age;

        public ProfileForm() {}

        public String getDisplayName() { return displayName; }
        public void setDisplayName(String value) { this.displayName = value; }

        public Integer getAge() { return age; }
        public void setAge(Integer value) { this.age = value; }
    }

    @InitBinder("profileForm")
    void configureBinder(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "age");
    }

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<String> update(
            @ModelAttribute("profileForm") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest().body("Invalid profile");
        }

        return ResponseEntity.ok(form.getDisplayName() + " / " + form.getAge());
    }
}
```

Gửi thử:

```bash
curl -i -X POST http://localhost:8080/profiles -d "displayName=Lan&age=27&role=ADMIN"
```

Phần **response body** dự kiến là `Lan / 27`. Khóa `role` không nằm trong danh sách `allowedFields` nên không được dùng để set property. Các trường bị loại có thể kiểm tra bằng `errors.getSuppressedFields()`. Ví dụ này dùng DTO riêng, không đặt thuộc tính `role` trong DTO, nên nó còn tránh cả việc vô tình phơi bày trạng thái nghiệp vụ.

**Không đồng nhất field Java với writable property.** Với chế độ mặc định, `BeanWrapper` ghi thông qua JavaBean setter. Một field `private` không có setter không đương nhiên được gán bằng property binding; direct field access là cấu hình khác (`initDirectFieldAccess()`), không phải hành vi mặc định.

## 4. Spring chọn constructor hay property binding?

| Tiêu chí | Constructor binding | Property binding |
| --- | --- | --- |
| Thời điểm | Trong lúc tạo object | Sau khi đã có object |
| Đích gán | Tham số constructor | Setter / writable property |
| Thiết kế phù hợp | `record`, DTO bất biến | JavaBean mutable |
| Cần setter? | Không | Thường có |
| Nguồn tên | Tên tham số, có thể `@BindParam` | Tên property / đường dẫn property |
| Điều chỉnh trạng thái sau tạo | Không qua setter nếu bất biến | Có thể thay đổi nhiều property |
| Ranh giới input | Chỉ các tham số constructor khai báo | Phải hạn chế tập writable property |

**Điểm dễ nhầm:** `@ModelAttribute` **mặc định có thể dùng cả hai**: Spring tạo đối tượng bằng constructor (khi cần), rồi áp dụng property binding cho các thuộc tính có thể ghi. Vì vậy việc có constructor **không có nghĩa** mọi setter tự bị vô hiệu hóa. Với DTO bất biến, không có setter để gán tiếp; với DTO mutable, cần kiểm soát các property có thể được gán.

Trong tầng core, `DataBinder` thể hiện rõ hai thao tác:

- Constructor: tạo binder với target ban đầu là `null`, đặt `targetType`, rồi gọi `construct(ValueResolver)`. `ValueResolver` cung cấp giá trị theo tên tham số.
- Property: tạo binder với object hiện hữu, rồi gọi `bind(PropertyValues)` để đặt các thuộc tính.

Ví dụ property binding trực tiếp qua `DataBinder` (đoạn này dùng class `ProfileForm` đã định nghĩa ở trên, cần Spring trên classpath):

```java
import java.util.Map;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

ProfileController.ProfileForm form = new ProfileController.ProfileForm();
DataBinder binder = new DataBinder(form);
binder.setAllowedFields("displayName", "age");
binder.bind(new MutablePropertyValues(
        Map.of("displayName", "Mai", "age", "29")));

if (!binder.getBindingResult().hasErrors()) {
    System.out.println(form.getDisplayName() + " / " + form.getAge());
}
```

Kết quả in dự kiến khi chạy trong chương trình Java có Spring dependencies:

```text
Mai / 29
```

Đoạn trực tiếp này là **snippet cần đặt trong method**; không phải tệp Java độc lập. Nó giúp thấy `DataBinder.bind(...)` nhận dữ liệu dạng property/value, còn kết quả là các setter của cùng object `form` được gọi.

## 5. Đường dẫn lồng nhau, danh sách và chuyển kiểu

Tên key là phần quan trọng của việc gắn giá trị:

| Input key | Ý nghĩa |
| --- | --- |
| `name` | Property `name` hoặc tham số constructor `name` |
| `address.city` | Property `city` của object `address` |
| `lines[0].sku` | `sku` của phần tử đầu tiên trong danh sách `lines` |
| `labels[home]` | Phần tử ứng với key `home` trong `Map` |

Ví dụ form có `address.city=Hanoi`: với property binding, binder đi qua property `address` rồi gán `city`; với constructor binding, nếu tham số `address` là một object hỗ trợ dựng từ các tham số tương ứng, Spring có thể dựng object lồng nhau. Đừng giả định mọi collection hoặc object tùy ý đều tự tạo thành công: nó phụ thuộc kiểu dữ liệu, constructor/setter, tên key và cấu hình binder.

Chuyển kiểu được thực hiện trước khi gán, chẳng hạn:

- `"29"` → `Integer 29`; nếu gửi `"xyz"` vào `Integer` sẽ có lỗi kiểu.
- Chuỗi ngày có thể chuyển thành `LocalDate` nếu đã có converter/formatter tương ứng, ví dụ `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)`.
- Giá trị tập hợp có thể đi qua các key đánh chỉ số hoặc cách chuyển đổi được hỗ trợ.

`ConversionService`, `Converter`, `Formatter` và `PropertyEditor` giúp điều khiển cách chuyển kiểu. `@InitBinder` cho phép đăng ký cấu hình riêng theo controller hoặc model attribute. **Có thể đọc được một chuỗi không có nghĩa chuỗi đó hợp lệ về nghiệp vụ**; sau binding vẫn cần validation thích hợp.

## 6. Lỗi binding và validation xuất hiện lúc nào?

**Binding/conversion** trả lời: “Có đưa đầu vào vào đúng kiểu và vị trí không?”. **Validation** trả lời: “Giá trị sau binding có thỏa các ràng buộc không?”.

Ví dụ phân biệt:

- `age=abc` với property kiểu `Integer`: **lỗi chuyển kiểu/binding**.
- `age=-5`: vẫn chuyển thành `Integer -5`; chỉ bị từ chối nếu có quy tắc như `@Min(0)` hoặc validator tương ứng.
- `email=`: với `String` có thể là chuỗi rỗng; muốn bắt buộc có giá trị cần `@NotBlank` hoặc kiểm tra khác.
- Field không nằm trong `allowedFields`: có thể bị loại/suppressed, không nhất thiết sinh `hasErrors() == true`. Nếu muốn trả lỗi khi client cố gán field lạ, kiểm tra `getSuppressedFields()`.

Có thể yêu cầu Bean Validation và bắt lỗi ngay trong controller:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;

// Đặt trong DTO:
public record CheckedRegistration(
        @NotBlank String email,
        @Min(0) Integer age) {}

// Đặt trong chữ ký handler:
public String submit(
        @Valid @ModelAttribute CheckedRegistration input,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "form-with-errors";
    }
    return "success";
}
```

Đây là **minh họa theo ngữ cảnh**, gồm khai báo record và chữ ký method, cần đặt trong class/controller phù hợp. `@Valid` yêu cầu có Bean Validation provider được cấu hình; nó không thay thế xử lý lỗi chuyển kiểu. `BindingResult` phải đứng **ngay sau** đối số `@ModelAttribute` tương ứng. Nếu không nhận `BindingResult` và binding/validation thất bại, Spring MVC xử lý lỗi bằng cơ chế exception thông thường (ví dụ `MethodArgumentNotValidException` trong trường hợp phù hợp).

## 7. An toàn khi nhận dữ liệu không tin cậy

Property binding là công cụ mạnh nhưng có thể gây **mass assignment/over-posting** nếu đưa trực tiếp entity chứa thuộc tính nhạy cảm ra làm đích. Ví dụ một entity có `role`, `approved`, `price`: client có thể gửi thêm tên các property ấy nếu chúng writable và không được giới hạn.

Cách xử lý:

1. **Ưu tiên request DTO riêng**, chỉ có các giá trị client được phép gửi; dùng `record`/constructor binding khi hợp lý.
2. Với property binding, khai báo `binder.setAllowedFields("displayName", "age")` để chỉ nhận các field được dự kiến. Không dựa duy nhất vào danh sách cấm vì khó theo kịp thuộc tính mới.
3. Có thể gọi `binder.setDeclarativeBinding(true)` (Spring Framework 6.1+) để mặc định chỉ constructor binding; property binding chỉ diễn ra nếu có `allowedFields` phù hợp. Đây là lựa chọn hữu ích khi cần kiểm soát binding theo khai báo.
4. Sau khi binding và validation thành công, **service quyết định** các giá trị server-owned như ID, quyền, trạng thái phê duyệt; controller không tin các giá trị đó từ request.
5. Với form có cập nhật object hiện hữu, phải kiểm soát cả **quyền sửa object** và **quyền sửa từng thuộc tính**, vì binding tự nó không phải cơ chế authorization.

Ví dụ chỉ cho phép constructor binding trong một controller:

```java
@InitBinder
void constructorOnly(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

Đoạn trên nằm trong class `@Controller`/`@RestController` (và cần import `WebDataBinder`, `InitBinder`). Nếu muốn một số property vẫn writable, kết hợp `setAllowedFields(...)` với cấu hình này.

## 8. Các lỗi thường gặp và cách kiểm tra

- **Tên request không trùng tên Java:** `full-name` khác `fullName`; sử dụng `@BindParam` cho tham số constructor hoặc sửa key của form.
- **Thiếu metadata tên constructor:** với class thông thường, biên dịch có `-parameters` khi cần. Ví dụ `javac -parameters MyDto.java` nếu chỉ biên dịch một DTO Java thuần; ứng dụng Spring vẫn phải có dependencies riêng.
- **Chờ setter chạy trên record:** record không có JavaBean setters; giá trị vào record chủ yếu qua constructor.
- **Cho rằng có constructor thì setter binding tự tắt:** Spring MVC mặc định có thể kết hợp cả hai; cần thiết kế immutable hoặc cấu hình binder để khống chế.
- **Dùng field private không setter:** mặc định property binding không thể tự set một private field chỉ vì tên trùng.
- **Gửi JSON rồi chờ `@ModelAttribute` xử lý như `@RequestBody`:** JSON body có đường xử lý khác, thường qua Jackson/`HttpMessageConverter`.
- **Tưởng `@Valid` làm việc chuyển kiểu:** type conversion xảy ra trong binding; validation áp dụng quy tắc hợp lệ trên dữ liệu.
- **Không đặt `BindingResult` sát đối tượng được bind:** Spring có thể không liên kết lỗi như dự kiến.
- **Bind entity trực tiếp:** có thể mở đường sửa những field ngoài ý định; ưu tiên DTO và giới hạn allowed fields.

### Bảng tự kiểm tra nhanh

| Request / đối tượng | Điều cần quan sát |
| --- | --- |
| `email=lan@example.com&age=24` → `Registration` record | Constructor nhận `String` và `Integer 24` |
| `displayName=Lan&age=27` → `ProfileForm` | Setter ghi tên và tuổi |
| `age=abc` | `BindingResult.hasErrors()` do chuyển kiểu thất bại |
| `role=ADMIN` trong ví dụ `ProfileController` | Không có property role được phép bind; có thể xem suppressed fields |
| `full-name=Lan` → `@BindParam("full-name")` | Dữ liệu vào tham số `fullName` |
| `age=-5` với `@Min(0)` và `@Valid` | Binding kiểu số thành công, validation thất bại |

**Ghi nhớ:** constructor binding quyết định dữ liệu nào tham gia **tạo object**; property binding quyết định dữ liệu nào có thể **thay đổi object** sau khi tạo. Cả hai đều phụ thuộc tên key, chuyển kiểu và xử lý lỗi; đối với dữ liệu từ client, phạm vi được phép gán phải được thiết kế rõ ràng.

## Tài liệu tham khảo

- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — Data Binding / Model Design](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring MVC — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html)
