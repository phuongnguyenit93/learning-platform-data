# Tên thuộc tính đơn và đường dẫn dạng `address.city` trong Spring Data Binding

## 1. Property name và property path là gì?

Khi Spring gắn dữ liệu lên một Java object, nó cần biết **thuộc tính đích** được xác định bằng tên nào. Tên thuộc tính đơn (simple property name) là một segment như `name`, `age` hoặc `city`. Đường dẫn thuộc tính (property path) có thể gồm nhiều segment nối bằng dấu chấm để truy cập object lồng nhau, ví dụ `address.city`.

```text
CustomerForm
  name: String
  address: Address
             city: String

Property name: "name"           -> CustomerForm.name
Property path: "address.city"   -> CustomerForm.address.city
```

Spring thường sử dụng các property path trong `BeanWrapper`, `DataBinder`, `WebDataBinder`, `BindingResult`, Spring form binding và thông báo lỗi field. Các tên này mô tả **cấu trúc object**, không phải tên database column hay JSON path theo nghĩa tổng quát.

Ví dụ nếu một object có `getAddress()` và `getAddress().getCity()`, `address.city` là một đường truy cập hợp lý. Còn `address_city`, `address/city`, `Address.City` không tự động tương đương khi dùng các API property access thông thường.

## 2. JavaBean properties và tên thuộc tính đơn

Với chế độ property access mặc định, Spring nhận biết các property thông qua JavaBeans getter/setter. Ví dụ:

```java
public class CustomerForm {
    private String name;
    private int age;

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public int getAge() { return age; }
    public void setAge(int age) { this.age = age; }
}
```

`name` và `age` là simple property names. Khi bind `name=An` và `age=21`, binder có thể gọi setter tương ứng, chuyển kiểu `"21"` sang `int` trước khi gán.

| Tên nguồn | Property đích | Kiểu đích | Hành vi |
| --- | --- | --- | --- |
| `name` | `setName(String)` | `String` | Gán giá trị dạng chuỗi |
| `age` | `setAge(int)` | `int` | Cần chuyển chuỗi thành số nguyên khi input là `String` |
| `address.city` | `getAddress().setCity(String)` | `String` | Điều hướng qua object `address` |

Các JavaBean properties **không nhất thiết trùng** với tên private field: Spring ưu tiên contract getter/setter trong bean property access. Property chỉ có getter thường đọc được nhưng không ghi được theo đường setter thông thường. Có thể chọn direct-field access bằng API riêng, nhưng đó là một chế độ truy cập khác và nên cân nhắc thiết kế/bảo mật.

## 3. Đường dẫn lồng nhau: `address.city`

Giả sử hai lớp:

```java
public class Address {
    private String city;
    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }
}

public class CustomerForm {
    private Address address = new Address();
    public Address getAddress() { return address; }
    public void setAddress(Address address) { this.address = address; }
}
```

Để đọc `address.city`, Spring trước tiên lấy `CustomerForm.address`, sau đó lấy property `city` của `Address`. Để ghi, Spring cần điều hướng đến `Address` rồi gán `city` thông qua setter hoặc cơ chế field access được cấu hình.

Đường dẫn có thể sâu hơn, chẳng hạn `shippingAddress.country.code`, nếu từng segment hợp lệ và các object trung gian tồn tại hoặc có thể được tự tạo theo cấu hình. Không mặc định rằng Spring có thể tạo mọi nested object: constructor, access level, kiểu abstract/interface và giới hạn auto-grow đều ảnh hưởng.

### Dấu chấm không phải reflection thuần túy

`BeanWrapper` sử dụng Spring property access abstractions; nó không tương đương với chuỗi thao tác Java reflection viết tay. Spring xử lý metadata, conversion, exception và các kiểu path được hỗ trợ.

Đối với nested JavaBean property, đường dẫn được hiểu **theo từng đoạn** và mỗi đoạn phải hợp lệ trong mô hình target. Nếu `address` bị `null` mà auto-grow tắt, yêu cầu ghi `address.city` có thể phát sinh `NullValueInNestedPathException`. Nếu auto-grow bật và Spring tạo được một `Address`, quá trình có thể thành công. Trạng thái mặc định của từng API, constructor và phiên bản có thể khác; kiểm tra trực tiếp cấu hình khi cần đảm bảo hành vi.

## 4. Ví dụ Java 17+ đầy đủ với `BeanWrapper`

`BeanWrapper` là API cho phép thao tác property name và nested property path ngoài HTTP. Lưu tệp `PropertyPathDemo.java`:

```java
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;

public class PropertyPathDemo {
    public static class Address {
        private String city;
        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
    }

    public static class CustomerForm {
        private String name;
        private Address address = new Address();

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }
        public Address getAddress() { return address; }
        public void setAddress(Address address) { this.address = address; }
    }

    public static void main(String[] args) {
        CustomerForm customer = new CustomerForm();
        BeanWrapper wrapper = new BeanWrapperImpl(customer);

        wrapper.setPropertyValue("name", "An");
        wrapper.setPropertyValue("address.city", "Đà Nẵng");

        System.out.println(wrapper.getPropertyValue("name"));
        System.out.println(wrapper.getPropertyValue("address.city"));
        System.out.println(customer.getAddress().getCity());
    }
}
```

Stdout:

```text
An
Đà Nẵng
Đà Nẵng
```

Ở đây `wrapper` không tạo một bản sao: nó tác động đến chính instance `customer`. `setPropertyValue` dùng property name cho `name`, nested path cho `address.city`; `getPropertyValue` đọc lại giá trị đã gán.

Ví dụ này cần các thư viện Spring Framework tương thích (ít nhất module chứa `BeanWrapper` và những dependency của nó). Nếu đã có toàn bộ JAR trong biến `SPRING_CP`, trên Linux/macOS:

```bash
javac -cp "$SPRING_CP" PropertyPathDemo.java
java -cp ".:$SPRING_CP" PropertyPathDemo
```

Trên Windows, dùng dấu `;` thay vì `:` trong classpath. Đây là một chương trình có `main` Java 17+; `javac PropertyPathDemo.java` không kèm Spring dependency sẽ thất bại vì JDK không cung cấp `org.springframework.beans.*`.

## 5. Ví dụ `DataBinder.bind()` với simple name và nested path

`DataBinder` tiếp nhận `PropertyValues` và áp dụng các property paths lên target. Ví dụ dưới đây sử dụng **hai lớp lồng nhau đã khai báo trong `PropertyPathDemo`**; snippet được đặt trong method của một lớp khác hoặc trong `main` có import phù hợp:

```java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

PropertyPathDemo.CustomerForm form =
        new PropertyPathDemo.CustomerForm();
DataBinder binder = new DataBinder(form, "customer");

MutablePropertyValues values = new MutablePropertyValues();
values.add("name", "Bình");
values.add("address.city", "Hà Nội");

binder.bind(values);
BindingResult result = binder.getBindingResult();

System.out.println(form.getName());
System.out.println(form.getAddress().getCity());
System.out.println(result.hasErrors());
```

Kết quả khi dùng cùng `CustomerForm` với `address` đã khởi tạo:

```text
Bình
Hà Nội
false
```

`MutablePropertyValues` giữ các cặp key/value. Binder dựa vào tên key để tìm đúng JavaBean properties, có thể chuyển giá trị trước khi gán và lưu các lỗi phát sinh trong `BindingResult`. Nếu `address.city` không tồn tại hoặc không thể ghi, kết quả có thể bị ảnh hưởng bởi `ignoreUnknownFields`, `ignoreInvalidFields` và các chính sách binder; cần thiết kế hành vi chấp nhận/từ chối input rõ ràng.

## 6. Đường dẫn với collection và map

Bên cạnh simple names và dot notation, Spring property access có thể hỗ trợ cú pháp indexed/mapped khi kiểu dữ liệu và accessor cho phép:

```text
items[0].sku              -> thuộc tính sku của phần tử đầu trong items
addresses[1].city         -> city của phần tử thứ hai
attributes[region]        -> giá trị theo key region trong map
```

Đây là ví dụ **cú pháp path** chứ không bảo đảm mọi collection/map đều tự mở rộng. Việc bind thành công phụ thuộc cấu trúc Java object, kiểu collection/map, kiểu generic (nếu Spring suy luận được), trạng thái null, giới hạn auto-grow và conversion. Ví dụ `items[99999999].name` cần được chặn bằng giới hạn cấu hình, không nên cho client mở rộng collection tùy ý.

### Giới hạn auto-grow

`DataBinder` có cơ chế kiểm soát `autoGrowNestedPaths` và `autoGrowCollectionLimit`. Nếu bật auto-grow, Spring có thể tạo các object trung gian hoặc mở rộng collection trong phạm vi cho phép. Tính năng này thuận tiện cho form binding, nhưng có thể tốn tài nguyên và tạo ra surface cho input do người dùng điều khiển. Dùng allowlist, DTO và giới hạn kích thước/độ sâu khi nhận dữ liệu không tin cậy.

## 7. Binding không đồng nghĩa truy cập tự do tất cả field

Đường dẫn property chính là những tên mà client có thể thử cung cấp, vì vậy **mass assignment** là rủi ro cần quản lý. Ví dụ:

```java
public class AccountForm {
    private String displayName;
    private boolean admin;
    // getters/setters ...
}
```

Nếu ứng dụng bind mọi parameter vào `AccountForm` mà không giới hạn, input `admin=true` có thể thay đổi field không dành cho client. Với nested path, input `owner.permissions[0]` cũng có nguy cơ truy cập sâu vào object graph nếu được phép.

Dùng allowlist để giới hạn:

```java
DataBinder binder = new DataBinder(form, "customer");
binder.setAllowedFields("name", "address.city");
binder.bind(values);
```

Tên trong allowed fields phải phù hợp property path thực tế. Những path khác, chẳng hạn `address.country` hoặc `admin`, bị suppress khi không khớp chính sách. Có thể kiểm tra `binder.getBindingResult().getSuppressedFields()` để phát hiện input bị chặn. **Không coi suppressed field mặc định là FieldError:** ứng dụng có thể cần chủ động trả lỗi khi phát hiện đường dẫn không được phép.

## 8. Property path và đường dẫn lỗi trong `BindingResult`

Khi một field lỗi, Spring lưu tên property path trong `FieldError`. Ví dụ nếu form có property `address.zipCode` kiểu số và client gửi `abc`, error field có thể là `address.zipCode` cùng mã như `typeMismatch`.

```java
BindingResult result = binder.getBindingResult();
boolean cityInvalid = result.hasFieldErrors("address.city");
var fieldError = result.getFieldError("address.city");
```

Snippet này giả định biến `binder` tồn tại. Nếu có lỗi của field `address.city`, `fieldError` cung cấp code, rejected value và các thông tin khác. Nếu không có lỗi, `getFieldError(...)` có thể trả `null`; cần kiểm tra trước khi dereference.

Trong validator, `Errors.rejectValue("address.city", "city.required")` có thể ghi field error theo nested property path. Nếu dùng `errors.pushNestedPath("address")`, các lời gọi reject với field `city` được áp dụng relative vào nested path và cần `popNestedPath()` để khôi phục. Không gọi `pushNestedPath` mà quên pop khi tiếp tục validate field khác.

## 9. So sánh với cú pháp ở những tầng khác

| Ngữ cảnh | Ý nghĩa của `address.city` |
| --- | --- |
| `BeanWrapper` | Đường dẫn property trong Java object |
| `DataBinder` | Tên property dùng để bind input vào object |
| `BindingResult` | Tên field/property path để theo dõi lỗi |
| Spring MVC `@ModelAttribute` | Có thể là tên form parameter để bind nested property |
| JSON request body | JSON object được deserializer xử lý; không nhất thiết gọi `DataBinder.bind(PropertyValues)` |
| SQL | Không phải mặc nhiên cú pháp cột; tùy schema và truy vấn |

Ví dụ với HTTP form data:

```text
name=An&address.city=Huế
```

đại diện hai key là `name` và `address.city`. Khi server dùng Spring MVC model attribute binding và cho phép hai property, binder có thể gán hai giá trị tương ứng.

Với JSON, dữ liệu lồng nhau thường có hình:

```json
{
  "name": "An",
  "address": { "city": "Huế" }
}
```

Spring MVC có thể dùng Jackson hoặc message converter phù hợp để deserialize `@RequestBody`; đây không phải việc tự động tách khóa JSON thành string `address.city` theo cùng đường property-binding. Ngoài ra `@RequestParam("address.city")` lấy một request parameter có tên `address.city`, khác với việc dùng nested path của một model attribute.

## 10. Các lỗi phổ biến

- **Nhầm tên field với property:** property `getFirstName()` thường được gọi là `firstName`, không phải mọi biến thể `first_name` hoặc `firstname` đều khớp.
- **Đảo thứ tự segment:** `city.address` không thể thay thế `address.city` khi object root là `CustomerForm`.
- **Đối tượng trung gian null:** nếu `address == null` và không thể auto-grow, nested path sẽ không bind được.
- **Thiếu setter hoặc type không writable:** getter-only property thường không ghi được theo JavaBean property access.
- **Sai kiểu input:** đường dẫn đúng nhưng giá trị không thể convert dẫn đến lỗi conversion/binding (ví dụ `typeMismatch`).
- **Sai cấu trúc collection:** `items[0].sku` cần collection và element type phù hợp, không chỉ có string key.
- **Assume trường lạ luôn báo lỗi:** default ignore-unknown của binder có thể bỏ qua path không nhận biết; cần thiết lập chính sách phù hợp.
- **Cho phép path quá rộng:** nguy cơ mass assignment và mở rộng object graph không kiểm soát.
- **Nhầm `DataBinder` với validation:** bind vào path không tự đảm bảo giá trị đáp ứng quy tắc nghiệp vụ; gọi validator khi cần.

## 11. Checklist thực hành

1. Xác định root object và tên JavaBean properties thực tế.
2. Dùng tên đơn (`name`) hoặc nested path (`address.city`) đúng cấu trúc.
3. Đảm bảo object trung gian tồn tại hoặc cấu hình auto-grow phù hợp.
4. Kiểm tra property có thể đọc/ghi và converter cho các kiểu dữ liệu không phải chuỗi.
5. Đặt allowlist các property path từ nguồn dữ liệu không tin cậy.
6. Kiểm tra `BindingResult`, gồm field errors và suppressed fields.
7. Kiểm thử input hợp lệ, null nested object, sai tên, sai kiểu và đường dẫn collection quá sâu.

**Ghi nhớ:** `name` là một property đơn; `address.city` là chuỗi các property nối nhau để truy cập vào nested object. Spring dùng property paths để bind và báo lỗi, nhưng khả năng ghi được và mức độ an toàn phụ thuộc cấu trúc JavaBean, conversion, cấu hình binder và quyền truy cập mà ứng dụng thiết lập.
