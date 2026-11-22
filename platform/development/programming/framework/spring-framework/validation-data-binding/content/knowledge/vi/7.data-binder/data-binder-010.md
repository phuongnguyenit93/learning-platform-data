# Vòng đời DataBinder theo một lần xử lý dữ liệu trong Spring Framework

## 1. DataBinder sống trong phạm vi nào?

`org.springframework.validation.DataBinder` là đối tượng điều phối việc đưa giá trị đầu vào vào một object đích, chuyển đổi kiểu dữ liệu và tích lũy lỗi binding/validation. Trong một luồng xử lý dữ liệu, binder thường được **tạo cho một target cụ thể**, được cấu hình, thực hiện bind, có thể thực hiện validate rồi trả `BindingResult`.

Không nên coi `DataBinder` là một singleton dùng chung cho tất cả request: nó giữ tham chiếu đến target, tên object, tập lỗi và cấu hình của lượt bind. Trong Spring MVC, framework thông thường tạo `WebDataBinder` phù hợp cho từng model attribute/request binding; application code cũng có thể tự tạo `DataBinder` khi không có HTTP.

Một vòng đời điển hình:

```text
(1) Chuẩn bị object target / objectName
                 |
                 v
(2) Tạo DataBinder hoặc WebDataBinder
                 |
                 v
(3) Cấu hình binder
    - allowedFields / requiredFields
    - ConversionService / formatter / editor
    - Validator và chính sách field access
                 |
                 v
(4) bind(PropertyValues) / binding do framework thực hiện
    - xác định property path
    - chuyển đổi kiểu dữ liệu
    - gán giá trị và ghi binding errors
                 |
                 v
(5) validate() nếu có yêu cầu
    - kiểm tra quy tắc sau binding
    - ghi validation errors
                 |
                 v
(6) Lấy BindingResult, xử lý lỗi hoặc dùng target
                 |
                 v
(7) Kết thúc lượt xử lý, bỏ tham chiếu binder
```

Đây là **luồng khái niệm**; Spring MVC có thể thực hiện constructor binding, property binding và validation theo handler/resolver/configuration cụ thể. Không nên kết luận rằng mọi argument đều trải qua đúng các lời gọi trên hoặc mọi target đều được tạo bằng constructor không tham số.

## 2. Giai đoạn 1: chuẩn bị target

Đối với property binding trực tiếp, ứng dụng có thể tạo object trước:

```java
public class OrderForm {
    private String customer;
    private Integer quantity;

    public String getCustomer() { return customer; }
    public void setCustomer(String customer) { this.customer = customer; }

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }
}
```

Từ đó:

```java
OrderForm form = new OrderForm();
DataBinder binder = new DataBinder(form, "orderForm");
```

`objectName` như `"orderForm"` được dùng trong `BindingResult` và các mã lỗi. Nó không cần trùng tên Java variable nhưng nên ổn định theo contract ứng dụng.

Khi dùng Spring MVC với `@ModelAttribute`, framework có thể lấy model attribute từ model, tạo instance mới hoặc dùng constructor binding dựa trên khả năng và cấu hình phiên bản hiện hành. Vì vậy, quy trình tạo target trong web layer có thể phức tạp hơn ví dụ thủ công.

## 3. Giai đoạn 2: cấu hình binder trước khi gắn dữ liệu

Một số thiết lập quan trọng:

| Thiết lập | Mục đích | Khi áp dụng |
| --- | --- | --- |
| `setAllowedFields(...)` | Giới hạn field được phép gán | Trước khi bind input không tin cậy |
| `setDisallowedFields(...)` | Loại trừ các field bị cấm | Trước khi bind |
| `setRequiredFields(...)` | Yêu cầu các field xuất hiện trong nguồn dữ liệu | Trước khi bind |
| `setConversionService(...)` | Định nghĩa đường chuyển đổi kiểu | Trước khi bind |
| `registerCustomEditor(...)` | Dùng `PropertyEditor` cho kiểu/property cụ thể | Trước khi bind |
| `addValidators(...)` hoặc `setValidator(...)` | Đăng ký bộ kiểm tra dữ liệu | Trước `validate()` |
| `initDirectFieldAccess()` | Chuyển sang truy cập field trực tiếp | Trước khi thực hiện binding/property access |
| `setAutoGrowNestedPaths(...)` | Kiểm soát hành vi phát triển nested path khi thích hợp | Trước khi bind |

Đây là các lựa chọn cho từng tình huống, không phải danh sách phương thức buộc phải gọi. Giữ mặc định khi nó đáp ứng yêu cầu và chỉ thay đổi những điểm thực sự cần.

**Thứ tự có ý nghĩa:** nếu bạn thiết lập allowed fields sau `bind()`, nó không thể đảo ngược những giá trị đã được gán. Nếu bạn đăng ký validator sau `validate()`, validator mới không tham gia lượt validation đã diễn ra.

### Ví dụ thiết lập allowlist

```java
DataBinder binder = new DataBinder(form, "orderForm");
binder.setAllowedFields("customer", "quantity");
```

Trong form gửi từ client, một field không được cho phép như `approved=true` có thể bị suppress; ứng dụng đọc `binder.getBindingResult().getSuppressedFields()` để phát hiện. Với dữ liệu nhạy cảm, nên từ chối request nếu có field bị suppress và dùng DTO chỉ chứa những property thực sự được client cập nhật. Không nên chỉ dựa vào `setDisallowedFields` để kiểm soát mọi field mới được thêm trong tương lai.

## 4. Giai đoạn 3: bind dữ liệu đầu vào

Phương thức `DataBinder.bind(PropertyValues)` áp dụng các giá trị đầu vào lên target:

```java
MutablePropertyValues values = new MutablePropertyValues();
values.add("customer", "An");
values.add("quantity", "3");

binder.bind(values);
```

Trong luồng property access thông thường, binder:

1. Xác định tên property được gửi và kiểm tra chính sách allowed/disallowed/required fields.
2. Truy cập property thông qua getter/setter hoặc direct field access theo cấu hình.
3. Chuyển `"3"` thành `Integer(3)` bằng hạ tầng conversion/property editors phù hợp.
4. Gán giá trị được chuyển đổi cho target.
5. Ghi lỗi binding nếu không tìm được đường chuyển đổi hoặc setter không chấp nhận giá trị.

`bind()` **không** có kết quả trả về kiểu `boolean`; các lỗi được lưu trong `BindingResult`.

Nếu client gửi `quantity=abc`, lỗi chuyển đổi có thể được ghi thành `FieldError` với mã `typeMismatch`. Những field đã bind thành công có thể vẫn nằm trong target: binding không mặc nhiên là một transaction có khả năng rollback tất cả field khi một field lỗi.

## 5. Giai đoạn 4: validation sau binding

`DataBinder` có thể dùng Spring `Validator` để kiểm tra các quy tắc sau khi gắn dữ liệu. Ví dụ số lượng phải dương:

```java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

class OrderValidator implements Validator {
    @Override
    public boolean supports(Class<?> clazz) {
        return OrderForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        OrderForm form = (OrderForm) target;
        if (form.getQuantity() == null || form.getQuantity() <= 0) {
            errors.rejectValue("quantity", "quantity.positive");
        }
    }
}
```

Sau khi đăng ký `binder.addValidators(new OrderValidator())`, ứng dụng gọi `binder.validate()`. `validate()` là một bước riêng biệt: bản thân `bind()` không tự động gọi nó.

`supports(Class<?>)` xác định validator có phù hợp với lớp target không. Nếu validators không hỗ trợ target, việc đăng ký hoặc sử dụng có thể bị từ chối tùy API và đường thực thi; không đăng ký tùy tiện một validator chỉ dành cho `OrderForm` vào binder của kiểu khác.

Khi cần truyền validation groups/hints, `SmartValidator` có overload nhận `Object... validationHints`; `binder.validate(hints)` có thể chuyển tiếp chúng cho `SmartValidator` tương ứng. Đừng hiểu việc gọi `validate()` nhiều lần luôn là không tác dụng phụ: lỗi có thể được tích lũy, và validator tùy chỉnh có thể ghi thêm lỗi.

## 6. Ví dụ đầy đủ Java 17+: một vòng đời binder

Lưu file `DataBinderLifecycleDemo.java`:

```java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class DataBinderLifecycleDemo {
    public static class OrderForm {
        private String customer;
        private Integer quantity;

        public String getCustomer() { return customer; }
        public void setCustomer(String customer) { this.customer = customer; }

        public Integer getQuantity() { return quantity; }
        public void setQuantity(Integer quantity) { this.quantity = quantity; }
    }

    static class OrderValidator implements Validator {
        @Override
        public boolean supports(Class<?> clazz) {
            return OrderForm.class.isAssignableFrom(clazz);
        }

        @Override
        public void validate(Object target, Errors errors) {
            OrderForm form = (OrderForm) target;
            if (form.getQuantity() == null || form.getQuantity() <= 0) {
                errors.rejectValue("quantity", "quantity.positive");
            }
        }
    }

    public static void main(String[] args) {
        // (1) Target và (2) binder cho một lượt xử lý
        OrderForm form = new OrderForm();
        DataBinder binder = new DataBinder(form, "orderForm");

        // (3) Cấu hình trước khi bind
        binder.setAllowedFields("customer", "quantity");
        binder.addValidators(new OrderValidator());

        // (4) Tập giá trị nguồn và thực hiện property binding
        MutablePropertyValues input = new MutablePropertyValues();
        input.add("customer", "An");
        input.add("quantity", "3");
        input.add("approved", "true");
        binder.bind(input);

        // (5) Validation sau khi bind
        binder.validate();

        // (6) Đọc kết quả và target
        BindingResult result = binder.getBindingResult();
        System.out.println(form.getCustomer());
        System.out.println(form.getQuantity());
        System.out.println(result.hasErrors());
        System.out.println(result.getSuppressedFields().length);
    }
}
```

Kết quả mong đợi:

```text
An
3
false
1
```

Giải thích kết quả: `customer` và `quantity` được bind thành công; `quantity` chuyển từ chuỗi sang `Integer`. Validator không báo lỗi do số lượng dương. Field `approved` nằm ngoài allowlist nên bị suppress, và không tự động tăng số lỗi. Chính sách ứng dụng có thể kiểm tra suppressed fields để báo input không được phép.

Ví dụ có `main` chạy độc lập với HTTP nhưng cần Spring Framework trên classpath. Với Java 17+ và `SPRING_CP` chứa đầy đủ JAR Spring phù hợp trong môi trường Linux/macOS:

```bash
javac -cp "$SPRING_CP" DataBinderLifecycleDemo.java
java -cp ".:$SPRING_CP" DataBinderLifecycleDemo
```

Trên Windows dùng dấu `;` làm classpath separator. Không có Spring dependencies, `javac DataBinderLifecycleDemo.java` thuần túy sẽ không biên dịch vì thiếu `org.springframework.*`.

## 7. Ví dụ vòng đời khi binding lỗi

Đối với `quantity=abc`, binder vẫn được cấu hình và nhận input, nhưng chuyển kiểu thất bại. Xem đoạn code có thể đặt trong một method đang xử lý `OrderForm`:

```java
OrderForm invalid = new OrderForm();
DataBinder binder = new DataBinder(invalid, "orderForm");
binder.setAllowedFields("customer", "quantity");

MutablePropertyValues values = new MutablePropertyValues();
values.add("customer", "An");
values.add("quantity", "abc");

binder.bind(values);
BindingResult result = binder.getBindingResult();

System.out.println(invalid.getCustomer());
System.out.println(result.hasFieldErrors("quantity"));
System.out.println(result.getFieldError("quantity").getCode());
```

Kết quả điển hình theo binder conversion mặc định:

```text
An
true
typeMismatch
```

Bài học từ trường hợp này: `customer` đã được gán dù `quantity` thất bại. Nếu dữ liệu chỉ được phép sử dụng khi tất cả field hợp lệ, ứng dụng phải xem `BindingResult` trước khi thực hiện hành động nghiệp vụ.

Nếu sau đó gọi một validator nghiệp vụ, nó phải xử lý trường `quantity == null` an toàn. Phần mềm không nên giả định `validate()` sửa được dữ liệu chưa parse thành công.

## 8. Vòng đời binder trong Spring MVC

Trong controller MVC, developer thường không trực tiếp tạo `DataBinder`. Spring phối hợp argument resolver, binder factory và `WebDataBinder` để tạo/bind các model attributes. Mô hình đơn giản:

```text
HTTP request
    |
    v
Handler method argument resolver
    |
    +--> lấy hoặc tạo model attribute
    |
    +--> WebDataBinderFactory tạo WebDataBinder
    |       |
    |       +--> cấu hình ConversionService/Validator
    |       +--> gọi các @InitBinder tương ứng
    |
    +--> bind dữ liệu request (nếu được phép)
    |
    +--> validate nếu annotation/đường thực thi yêu cầu
    |
    +--> tạo BindingResult
    |
    v
Controller method
    |
    +--> xử lý lỗi hoặc sử dụng model
```

Một controller minh họa:

```java
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {
    @InitBinder("orderForm")
    void configureOrderBinder(WebDataBinder binder) {
        binder.setAllowedFields("customer", "quantity");
        binder.addValidators(new OrderValidator());
    }

    @PostMapping("/orders")
    String submit(
            @Validated @ModelAttribute("orderForm") OrderForm form,
            BindingResult result) {
        if (result.getSuppressedFields().length > 0) {
            return "Unsupported fields";
        }
        if (result.hasErrors()) {
            return "Invalid order";
        }
        return "Saved: " + form.getCustomer();
    }
}
```

Đây là snippet ứng dụng Spring MVC, không tự chạy nếu không có ứng dụng web và các class `OrderForm`/`OrderValidator` được định nghĩa trong scope phù hợp. Nó minh họa thời điểm `@InitBinder` cấu hình binder, `@Validated` kích hoạt validation và `BindingResult` được truyền ngay sau model attribute để controller đọc lỗi.

Nếu request chứa dữ liệu hợp lệ (`customer=An&quantity=3`), handler có thể trả `Saved: An`. Nếu có `approved=true`, field đó bị suppress và controller trả `Unsupported fields` theo chính sách ví dụ. Nếu `quantity=abc`, conversion error được ghi lại; controller trả `Invalid order`.

**Lưu ý:** ví dụ trả chuỗi mô tả và mặc định không đặt HTTP 400 cho các nhánh lỗi; ứng dụng production cần chọn status/body thích hợp bằng `ResponseEntity` hoặc exception handling. Ngoài ra `@RequestBody` JSON thường đi qua `HttpMessageConverter` (ví dụ Jackson); không đồng nhất JSON deserialization với toàn bộ quá trình property binding của `DataBinder`.

## 9. Những giới hạn thời gian sống và trạng thái

### Không chia sẻ binder giữa các request

Một binder gắn với target và `BindingResult` của một lần bind. Đặt nó làm mutable field của singleton controller hoặc service có thể gây chia sẻ trạng thái, dữ liệu giữa request và vấn đề concurrency. Hãy cấu hình binder qua `@InitBinder` hoặc tạo đối tượng mới cho thao tác độc lập.

### Không kỳ vọng binder rollback thay bạn

Binding có thể cập nhật nhiều field trước khi một field lỗi. Nếu target là domain entity được quản lý bởi ORM hoặc được chia sẻ, việc bind trực tiếp rồi báo lỗi có thể để lại trạng thái ngoài ý muốn. Dùng request DTO, kiểm tra lỗi/validation rồi mới chuyển sang entity ở tầng nghiệp vụ; thực hiện transaction khi cập nhật dữ liệu thực sự.

### Cấu hình chỉ đúng tại thời điểm sử dụng

Một lần bind nên chuẩn bị đầy đủ allowlist, converter và validator trước bước thực thi tương ứng. Nếu có yêu cầu khác cho các loại request, cấu hình binder riêng hoặc tách DTO. Đừng sửa binder sau khi đã dùng rồi kỳ vọng những giá trị đã gán tự động được xử lý lại.

### Phạm vi object và vòng đời cleanup

`DataBinder` không yêu cầu bước `close()` như `ApplicationContext`; nó không phải một resource connection. Sau khi xử lý request hoặc method kết thúc và không còn tham chiếu, object có thể được GC. Tuy nhiên target có thể tham chiếu tới tài nguyên khác; quy tắc đóng tài nguyên thuộc về chính những đối tượng đó, không phải binder.

## 10. Kiểm thử đúng theo từng giai đoạn

Bộ kiểm thử nên bao phủ những tình huống sau:

| Giai đoạn | Input/thao tác | Kỳ vọng |
| --- | --- | --- |
| Chuẩn bị | Target mới | Property khởi tạo đúng |
| Cấu hình | Allowlist chỉ có `customer`, `quantity` | Field khác bị suppress |
| Bind hợp lệ | `quantity="3"` | Property thành `Integer(3)` |
| Bind sai kiểu | `quantity="abc"` | `BindingResult` có lỗi `typeMismatch` |
| Validate | `quantity=-2` | Validator ghi lỗi nghiệp vụ |
| Kết quả | Có bất kỳ lỗi binding/validation | Không cập nhật dữ liệu nghiệp vụ |
| Phạm vi | Hai lượt bind độc lập | Binder/result không chia sẻ trạng thái |

Có thể thử riêng `DataBinder` mà không khởi động server để kiểm tra mapping và conversion. Với Spring MVC, thêm integration test hoặc `MockMvc` để xác minh `@InitBinder`, annotation validation và cách HTTP response thực sự được tạo.

## 11. Các lỗi phổ biến và cách tránh

- **Dùng lại binder sau nhiều request:** có thể trộn target, suppressed fields và binding errors; tạo theo từng lượt.
- **Cấu hình allowlist quá muộn:** field nhạy cảm đã có thể được gán; cấu hình trước `bind`.
- **Gọi `bind` rồi quên `validate`:** các ràng buộc nghiệp vụ không tự chạy.
- **Chạy validate trước bind:** validator kiểm tra trạng thái cũ hoặc mặc định thay vì dữ liệu vừa nhập.
- **Không kiểm tra `BindingResult`:** request có một phần property đã được gán nhưng có lỗi chưa được xử lý.
- **Giả định lỗi converter sẽ luôn ném exception ra controller:** trong property binding, một số lỗi được ghi trong `BindingResult`; cần hiểu đường xử lý hiện tại.
- **Nhầm missing/unknown/suppressed field:** mỗi loại có cách xử lý khác; `getSuppressedFields()` không giống `getFieldErrors()`.
- **Binding trực tiếp entity chứa field quyền hạn:** gây rủi ro mass assignment, nên dùng DTO và allowlist.
- **Cho rằng `@Valid` hoặc `@Validated` luôn chạy bất kể kiểu tham số:** cần kiểm tra validation integration thực tế của handler/argument resolver.

## 12. Checklist khi hoàn thành một lượt binding

1. Target có đúng type và ownership cho lượt xử lý?
2. Binder được tạo đúng target và đã cấu hình allowed fields, conversion, validator trước khi xử lý?
3. Input được bind thành property mong muốn, bao gồm các giá trị lồng nhau nếu cần?
4. Tất cả lỗi binding, suppressed fields và validation đã được kiểm tra?
5. Chỉ khi hợp lệ mới chuyển dữ liệu sang domain model hoặc gọi nghiệp vụ?
6. Binder/result có kết thúc cùng scope của lượt xử lý, không bị lưu lại trong singleton?

**Ghi nhớ:** Vòng đời `DataBinder` là một lần tạo và cấu hình binder cho target, bind input, kiểm tra dữ liệu, đọc `BindingResult`, rồi kết thúc lượt xử lý. Những bước này giúp tách đúng lỗi chuyển đổi, validation và trách nhiệm cập nhật nghiệp vụ.