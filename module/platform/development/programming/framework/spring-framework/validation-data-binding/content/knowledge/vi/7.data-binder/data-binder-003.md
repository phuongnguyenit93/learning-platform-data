# DataBinder.bind: gắn tập giá trị vào đối tượng trong Spring Framework

## 1. `bind` giải quyết việc gì?

`org.springframework.validation.DataBinder` là thành phần của Spring dùng để **gắn tập giá trị đầu vào (property values)** vào một đối tượng Java đã có, dựa trên tên thuộc tính. Khi ứng dụng nhận dữ liệu từ form, request parameters hoặc nguồn cấu hình tương tự, những giá trị này thường là chuỗi; binder tìm property tương ứng, chuyển đổi kiểu nếu cần, gọi setter hoặc cơ chế truy cập phù hợp, rồi lưu các lỗi binding.

Ví dụ: một `PersonForm` có `name` là `String`, `age` là `Integer` và `address.city` là thuộc tính lồng nhau. Tập dữ liệu có khóa `name`, `age`, `address.city` có thể được chuyển thành các lời gọi gán property trên object.

```text
MutablePropertyValues:
  name         -> "An"
  age          -> "21"
  address.city -> "Hà Nội"
         |
         v
DataBinder.bind(PropertyValues)
         |
         +--> xác định property path
         +--> kiểm tra property có được phép bind không
         +--> chuyển "21" thành Integer(21)
         +--> gán giá trị vào object đích
         +--> ghi lỗi vào BindingResult nếu có
```

Không nên nhầm ba bước:

- **Binding**: gán giá trị đầu vào vào thuộc tính đích qua `bind`.
- **Conversion/formatting**: chuyển dữ liệu đầu vào sang kiểu Java mà property yêu cầu; có thể dùng `PropertyEditor`, `ConversionService`, `Formatter` tùy cấu hình.
- **Validation**: kiểm tra các quy tắc nghiệp vụ hoặc ràng buộc dữ liệu thông qua `validate()` và các `Validator`; gọi `bind()` **không tự động đồng nghĩa** đã chạy validation.

## 2. Các thành phần chính

| Thành phần | Vai trò |
| --- | --- |
| `DataBinder` | Kết nối dữ liệu đầu vào với object đích, quản lý cấu hình binder và lỗi |
| `MutablePropertyValues` | Tập các cặp `propertyName -> value` có thể chỉnh sửa để đưa vào `bind()` |
| `PropertyValues` | Hợp đồng biểu diễn một tập giá trị property, không phụ thuộc nguồn HTTP |
| `BeanWrapper`/property access | Truy cập và ghi các JavaBean properties, bao gồm nested paths trong các điều kiện thích hợp |
| `ConversionService` | Chuyển đổi kiểu dữ liệu, chẳng hạn `String` sang `Integer` hoặc `LocalDate` |
| `BindingResult` | Ghi nhận field errors, global errors và các thông tin binding cho phép phản hồi |
| `WebDataBinder` | Mở rộng `DataBinder` cho các kịch bản web và khả năng binding dữ liệu request |

`DataBinder` thuộc hạ tầng Spring Framework và có thể sử dụng bên ngoài Spring MVC. `WebDataBinder` được dùng trong web stack; nó bổ sung hành vi liên quan request, còn `DataBinder.bind(PropertyValues)` vẫn là cơ chế nền tảng.

## 3. Ví dụ Java 17+: bind giá trị và tự chuyển kiểu

Tạo tệp `DataBinderDemo.java`:

```java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class DataBinderDemo {
    public static class PersonForm {
        private String name;
        private Integer age;

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }
        public Integer getAge() { return age; }
        public void setAge(Integer age) { this.age = age; }
    }

    public static void main(String[] args) {
        PersonForm form = new PersonForm();
        DataBinder binder = new DataBinder(form, "person");

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("name", "An");
        values.add("age", "21");

        binder.bind(values);
        BindingResult result = binder.getBindingResult();

        System.out.println(form.getName());
        System.out.println(form.getAge());
        System.out.println(result.hasErrors());
    }
}
```

Kết quả:

```text
An
21
false
```

Giải thích:

1. `new DataBinder(form, "person")` tạo binder với object đích và object name dùng trong thông tin lỗi.
2. `MutablePropertyValues` chứa dữ liệu nguồn; chuỗi `"21"` được chuyển thành `Integer` nhờ hạ tầng chuyển đổi mặc định khả dụng trong binder.
3. `binder.bind(values)` tìm các property `name` và `age`, thực hiện chuyển đổi/gán giá trị.
4. `getBindingResult()` lấy kết quả lỗi; dữ liệu hợp lệ nên `hasErrors()` trả `false`.

Ví dụ sử dụng API từ Spring (`spring-context` hoặc module Spring liên quan và các dependency đúng phiên bản) nên cần các JAR trên compile/runtime classpath. Nếu đã có classpath đầy đủ trong biến môi trường `SPRING_CP` trên Linux/macOS:

```bash
javac -cp "$SPRING_CP" DataBinderDemo.java
java -cp ".:$SPRING_CP" DataBinderDemo
```

Trên Windows, classpath separator là `;`. Lệnh `javac DataBinderDemo.java` thuần túy không đủ vì JDK không chứa Spring Framework.

## 4. Binding thất bại: lỗi kiểu dữ liệu được ghi vào `BindingResult`

Nếu người dùng gửi chuỗi không phù hợp với kiểu property, binder có thể ghi `FieldError` thay vì gán giá trị. Ví dụ sau có thể đặt trong `main` của chương trình trên:

```java
PersonForm invalidForm = new PersonForm();
DataBinder invalidBinder = new DataBinder(invalidForm, "person");
MutablePropertyValues badValues = new MutablePropertyValues();
badValues.add("age", "không-phải-số");

invalidBinder.bind(badValues);
BindingResult errors = invalidBinder.getBindingResult();

System.out.println(errors.hasFieldErrors("age"));
System.out.println(errors.getFieldError("age").getCode());
System.out.println(invalidForm.getAge());
```

Kết quả điển hình với cấu hình binder mặc định:

```text
true
typeMismatch
null
```

Đây là đoạn mã **bổ sung vào một phương thức đang tồn tại**, không phải Java file độc lập. Với property wrapper `Integer`, giá trị khởi tạo vẫn `null` khi gán thất bại. `FieldError` mang mã lỗi chung `typeMismatch` và các message codes cụ thể để phục vụ thông báo quốc tế hóa. Không nên dựa vào nguyên văn exception message của converter vì nó có thể thay đổi giữa các phiên bản.

**Phân biệt binding error với validation error:** `"không-phải-số"` không thể parse thành `Integer`; trong khi `age = -5` parse được nhưng có thể bị validator từ chối vì quy tắc tuổi. Các tình huống này có nguyên nhân và cách xử lý khác nhau.

## 5. Property path và nested properties

Khi object có quan hệ lồng nhau, tên property có thể dùng dấu chấm:

```java
public static class Address {
    private String city;
    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }
}

public static class PersonForm {
    private Address address = new Address();
    public Address getAddress() { return address; }
    public void setAddress(Address address) { this.address = address; }
}
```

Trong một ví dụ riêng (không khai báo trùng `PersonForm` ở cùng file), binder có thể nhận:

```java
MutablePropertyValues values = new MutablePropertyValues();
values.add("address.city", "Huế");
binder.bind(values);
```

Khi đối tượng `address` đã tồn tại và có getter/setter phù hợp, binder truy cập nó để gán `city`. Spring cũng có cơ chế tự tạo nested path trong một số cấu hình, nhưng không nên mặc định mọi object, constructor, collection hoặc immutable type đều có thể tạo tự động. Với target phức tạp, hãy kiểm thử hành vi theo phiên bản Spring và cấu hình `autoGrowNestedPaths`/`autoGrowCollectionLimit` khi thích hợp.

Indexed hoặc mapped paths như `items[0].name` hay `attributes[key]` cũng có thể được hỗ trợ nếu kiểu property, accessor và chính sách binder phù hợp. Chúng có thể mở rộng rất nhiều vùng object graph được ghi, vì vậy cần giới hạn các trường được phép bind từ input không tin cậy.

## 6. Chọn property nào được phép gán

Binding từ HTTP request cần kiểm soát cẩn thận vì client có thể tự thêm parameter không xuất hiện trong giao diện. Nếu object chứa trường nội bộ `admin`, `ownerId`, `approved` hoặc `price`, bind tự động các tên đó có thể gây **mass assignment**.

Giới hạn rõ các property được phép:

```java
DataBinder binder = new DataBinder(form, "person");
binder.setAllowedFields("name", "age");
binder.bind(values);
```

Khi đã đặt allowed fields, những property khác không thuộc danh sách này bị loại khỏi quá trình bind. Có thể dùng `setDisallowedFields(...)` cho các trường cấm, nhưng danh sách cho phép thường dễ kiểm soát hơn vì mặc định từ chối các field chưa được duyệt. Tên field có thể hỗ trợ pattern tùy API; hãy chọn mẫu có phạm vi hẹp và kiểm thử các nested path.

Ví dụ thiết kế:

```text
Client submits: name=An, age=21, admin=true
Allowed fields:  name, age
Bound fields:    name, age
Suppressed:      admin
```

Các field bị suppress có thể được kiểm tra qua `BindingResult.getSuppressedFields()`; chúng không có nghĩa mặc nhiên sẽ tạo một `FieldError`. Với input nhạy cảm, ứng dụng có thể chủ động từ chối request khi xuất hiện suppressed fields.

`setRequiredFields("name")` chỉ là quy tắc yêu cầu dữ liệu đầu vào ở mức binding; nó không thay thế Jakarta Bean Validation (`@NotBlank`) hoặc quy tắc nghiệp vụ trên object. Tùy nguồn dữ liệu và cấu hình, trường missing và chuỗi rỗng cũng có semantics khác nhau.

## 7. Sử dụng `ConversionService` và converter riêng

Khi dữ liệu nguồn là chuỗi nhưng kiểu đích là value object của miền nghiệp vụ, có thể cung cấp `ConversionService` phù hợp:

```java
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.core.convert.converter.Converter;

record CustomerCode(String value) {}

DefaultConversionService conversion = new DefaultConversionService();
conversion.addConverter(new Converter<String, CustomerCode>() {
    @Override
    public CustomerCode convert(String source) {
        if (!source.matches("CUS-[0-9]{4}")) {
            throw new IllegalArgumentException("Invalid customer code");
        }
        return new CustomerCode(source);
    }
});

DataBinder binder = new DataBinder(customerForm);
binder.setConversionService(conversion);
binder.bind(new MutablePropertyValues(java.util.Map.of(
        "code", "CUS-0007")));
```

**Đây là snippet minh họa** nằm trong method có class `customerForm` với property `CustomerCode code`; không biên dịch độc lập. `ConversionService` nhận converter theo kiểu nguồn/đích và binder có thể áp dụng khi setter cần `CustomerCode`. Hãy dùng kiểu đích cụ thể và báo lỗi có kiểm soát khi chuỗi không hợp lệ.

### Custom `PropertyEditor` và `Formatter`

Spring cũng hỗ trợ `PropertyEditor` để chuyển đổi kiểu, nhưng với kiểu miền nghiệp vụ mới thường ưu tiên `Converter` hoặc `Formatter` vì API rõ ràng và có thể tái sử dụng. `Formatter<T>` hữu ích khi parsing/printing phụ thuộc `Locale` (chẳng hạn ngày và số theo ngôn ngữ/vùng). Không nên tự đăng ký editor/converter toàn cục nếu nó thay đổi ngoài ý muốn những property khác.

## 8. `bind()` và `validate()` là hai lời gọi khác nhau

`DataBinder` cho phép gắn `Validator` rồi chạy validation sau binding:

```java
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

class PersonValidator implements Validator {
    @Override
    public boolean supports(Class<?> type) {
        return DataBinderDemo.PersonForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        DataBinderDemo.PersonForm form = (DataBinderDemo.PersonForm) target;
        if (form.getAge() != null && form.getAge() < 18) {
            errors.rejectValue("age", "age.tooYoung");
        }
    }
}
```

Khi dùng trong method có biến `form` và `values`:

```java
DataBinder binder = new DataBinder(form, "person");
binder.addValidators(new PersonValidator());
binder.bind(values);
binder.validate();
BindingResult result = binder.getBindingResult();
```

`bind(values)` thực hiện gán và ghi lỗi chuyển đổi; `validate()` gọi validators đã đăng ký. Trong ví dụ, `age = -5` có thể bind thành `Integer(-5)` thành công rồi bị `PersonValidator` ghi lỗi `age.tooYoung`. Nếu age không parse được, validator cần bảo đảm xử lý giá trị chưa gán hoặc null an toàn. Thứ tự binding rồi validation thường là thứ tự hợp lý cho input.

## 9. `DataBinder` so với binding trong Spring MVC

Spring MVC thường tạo và cấu hình `WebDataBinder` thông qua hạ tầng như `WebDataBinderFactory`, resolver và `@InitBinder`. Trong controller:

```java
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PersonController {
    @PostMapping("/people")
    String create(@ModelAttribute DataBinderDemo.PersonForm form,
                  BindingResult result) {
        if (result.hasErrors()) {
            return "Invalid input";
        }
        return form.getName() + " (" + form.getAge() + ")";
    }
}
```

Đây là **controller snippet** trong ứng dụng MVC đã cấu hình, không phải file có `main`. Nếu request form có `name=An&age=21`, binder giải quyết property mapping và conversion. `BindingResult` phải ở ngay sau tham số model tương ứng để controller nhận lỗi. Khi cần validation nghiệp vụ, dùng `@Validated` hoặc `@Valid` và validator/provider thích hợp. `@RequestBody` JSON thường qua `HttpMessageConverter` (ví dụ Jackson), nên không thể coi cơ chế deserialization JSON là lời gọi `DataBinder.bind(PropertyValues)` đơn thuần.

Với Spring MVC, có thể chỉ định allowed fields qua binder:

```java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("personForm")
void initPersonBinder(WebDataBinder binder) {
    binder.setAllowedFields("name", "age");
}
```

Tên object trong `@InitBinder` cần khớp tên model attribute thực tế; nếu dùng `@ModelAttribute("personForm")`, cấu hình sẽ dễ xác định hơn. Đừng tin rằng một `@InitBinder` giới hạn tên sẽ áp dụng cho mọi handler và object bất kể scope.

## 10. Cơ chế property access: JavaBean và direct field

Theo cách phổ biến, binder dùng JavaBean property access: getter và setter cho phép đọc/ghi property. `initDirectFieldAccess()` chuyển binder sang chế độ truy cập trực tiếp field, có thể hữu ích cho một số cấu trúc dữ liệu nhưng thay đổi ranh giới encapsulation và hành vi binding.

```java
DataBinder binder = new DataBinder(form);
binder.initDirectFieldAccess();
binder.bind(values);
```

Không tự bật direct field access như cách chữa mọi lỗi setter. Cần chọn chiến lược phù hợp với mô hình dữ liệu, quyền ghi trường, validation và chính sách bảo vệ dữ liệu.

Các model immutable (record, object chỉ có constructor, không có setter) thường cần cơ chế constructor binding hoặc mapping khác được Spring hỗ trợ ở ngữ cảnh cụ thể; không nên kỳ vọng property-binding thông thường có thể sửa trực tiếp trạng thái immutable.

## 11. Các lỗi thường gặp

- **Tên property sai:** khóa `first_name` không tự nhiên ánh xạ vào `firstName` trong mọi cấu hình binder; cần quy ước tên hoặc mapping rõ.
- **Setter vắng mặt:** property không thể ghi theo JavaBean property access; xem accessor hoặc chiến lược binding.
- **Chuỗi không chuyển được sang kiểu đích:** binder ghi `typeMismatch`, cần kiểm tra `BindingResult` và trả thông báo field thích hợp.
- **Gọi `bind()` rồi tưởng đã validate:** cần gọi `validate()` hoặc kích hoạt validation tương ứng qua framework.
- **Bind trực tiếp entity có field nhạy cảm:** dùng DTO chuyên biệt và allowlist; đừng để client thay đổi quyền hoặc ID nội bộ.
- **Bật `ignoreUnknownFields` không đúng nhu cầu:** tên field không tồn tại và field hợp lệ nhưng conversion fail là hai loại vấn đề; cấu hình phải theo contract input.
- **Nhầm suppressed fields với validation error:** sử dụng `getSuppressedFields()` để kiểm tra dữ liệu bị chặn nếu chính sách ứng dụng yêu cầu báo lỗi.
- **Tự grow nested path/collection không kiểm soát:** giới hạn số phần tử và trường được phép bind khi input do client điều khiển.
- **Tái sử dụng cùng `DataBinder` cho nhiều target/request:** binder gắn với target và trạng thái lỗi; tạo binder phù hợp với từng thao tác để tránh chia sẻ trạng thái không đúng.

## 12. Checklist áp dụng

1. Xác định rõ kiểu object đích và bộ input fields được phép gán.
2. Tạo `DataBinder(target, objectName)` hoặc để Spring MVC tạo binder theo request.
3. Chuẩn bị `PropertyValues`, khai báo converter/formatter nếu có kiểu đặc biệt.
4. Gọi `bind(values)` và đọc `getBindingResult()` để nhận `typeMismatch`, field errors, suppressed fields.
5. Đăng ký validator phù hợp và chạy validation nếu có quy tắc nghiệp vụ.
6. Không sử dụng object như đã hợp lệ trước khi kiểm tra mọi lỗi binding và validation liên quan.
7. Kiểm thử input hợp lệ, sai kiểu, tên field lạ, nested path, collection và các field nhạy cảm.

**Điểm cốt lõi:** `DataBinder.bind(PropertyValues)` là thao tác đưa các giá trị nguồn vào property của object đích, cùng hạ tầng chuyển đổi kiểu và ghi lỗi binding. Nó không tự thay thế validation hay chính sách kiểm soát các trường client được phép cập nhật.