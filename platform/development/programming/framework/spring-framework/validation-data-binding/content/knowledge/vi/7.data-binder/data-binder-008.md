# DataBinder: `getTarget()` và `getBindingResult()` sau xử lý

Sau khi Spring Framework nhận một tập dữ liệu đầu vào và áp dụng **data binding**, hai API thường được đọc ngay sau đó là `DataBinder.getTarget()` và `DataBinder.getBindingResult()`. Chúng trả lời **hai câu hỏi khác nhau**:

- **`getTarget()`:** đối tượng đích hiện tại là gì, và những thuộc tính nào của nó đã được gán?
- **`getBindingResult()`:** quá trình bind và các lần validation đã chạy có ghi nhận lỗi nào, giá trị nào bị từ chối, hoặc trường nào bị chặn hay không?

Đọc đúng hai kết quả giúp tránh lỗi nghiêm trọng: **đối tượng đích có dữ liệu không có nghĩa toàn bộ request đã hợp lệ**. Một vài field có thể được gán thành công trong khi các field khác bị lỗi chuyển kiểu; validator có thể tiếp tục ghi lỗi; field ngoài danh sách cho phép có thể bị loại bỏ. Vì vậy, quyết định thực thi nghiệp vụ phải dựa vào kết quả kiểm tra, không chỉ nhìn object.

Bài này tập trung vào `org.springframework.validation.DataBinder` và `org.springframework.validation.BindingResult`; các ví dụ sử dụng Java 17+ và Spring Framework 6.x.

## 1. Luồng xử lý của `DataBinder`

Với **property binding** vào một JavaBean có sẵn, quy trình điển hình như sau:

~~~text
Raw input: {"customer":"Lan", "quantity":"3"}
                         |
                         v
             DataBinder(target, "order")
                         |
                   cấu hình binder
           allowed fields, converter,
               validator, required fields
                         |
                         v
          binder.bind(propertyValues)
                         |
                 +-------+-------+
                 |               |
       Gán được thuộc tính    Lỗi conversion /
           trên target        field bị chặn
                 |               |
                 +-------+-------+
                         |
                         v
               binder.validate()
                         |
                         v
             +---------------------+
             | getTarget()         | -> trạng thái hiện tại của object
             | getBindingResult()  | -> lỗi bind + lỗi validation
             +---------------------+
                         |
                         v
         Kiểm tra lỗi / suppressed fields
                         |
                   +-----+-----+
                   |           |
                Có vấn đề   Hợp lệ
                   |           |
              Từ chối    Kiểm tra nghiệp vụ
                            rồi mới ghi dữ liệu
~~~

Ví dụ gọi trực tiếp:

~~~java
OrderInput input = new OrderInput();
DataBinder binder = new DataBinder(input, "order");

binder.setValidator(new OrderValidator());
binder.bind(propertyValues);
binder.validate();

Object target = binder.getTarget();
BindingResult result = binder.getBindingResult();

if (result.hasErrors()) {
    // Không tiếp tục thao tác ghi dữ liệu.
}
~~~

Đây là **đoạn minh họa**: `OrderInput`, `OrderValidator` và `propertyValues` cần được định nghĩa trong ứng dụng. Ví dụ đầy đủ có thể biên dịch/chạy được nằm ở mục 4.

Ba điểm cần nhớ ngay từ đầu:

1. `bind(...)` thực hiện **binding và conversion**, có thể tạo lỗi trong `BindingResult`. Nó **không đồng nghĩa** với việc đã chạy toàn bộ ràng buộc nghiệp vụ.
2. `validate()` gọi các `Validator` đã cấu hình cho binder; nếu không cấu hình hoặc không gọi, các lỗi validation mong đợi có thể chưa được thêm vào kết quả.
3. `getTarget()` không tự kết luận “hợp lệ”; `getBindingResult()` mới cung cấp lỗi cần đọc. Cả hai thuộc **cùng một phiên làm việc của binder** và cần được xem xét trong ngữ cảnh đó.

## 2. `getTarget()`: trạng thái hiện tại của đối tượng đích

Khai báo API:

~~~java
@Nullable
public Object getTarget()
~~~

`getTarget()` trả đối tượng binder đang làm việc với; do kiểu trả về là `Object`, ứng dụng cần cast nếu muốn gọi getter cụ thể. Giá trị **có thể là `null`**, tùy cách khởi tạo và giai đoạn xử lý.

### 2.1. Khi bind vào một JavaBean đã có

~~~java
OrderInput order = new OrderInput();
DataBinder binder = new DataBinder(order, "order");

// Sau khi binder.bind(...):
OrderInput bound = (OrderInput) binder.getTarget();
~~~

Trong tình huống property binding thông thường, binder cập nhật **chính instance** được đưa vào lúc tạo binder; `bound` và `order` tham chiếu cùng đối tượng. Nó không tự tạo một bản sao bất biến và cũng không “commit” dữ liệu chỉ khi mọi field hợp lệ.

Ví dụ DTO ban đầu có `quantity = 5`, request chứa `customer=Lan` và `quantity=abc`:

- `customer` có thể được gán thành `"Lan"`;
- `quantity` không chuyển được thành `Integer`, nên binder ghi nhận lỗi `typeMismatch`;
- `quantity` trên target có thể **vẫn là 5**, tức giá trị cũ, chứ không phải chứng cứ rằng người dùng gửi 5.

Do đó, đọc `getTarget()` sẽ cho biết **trạng thái object sau lần bind**, không phải một bản ghi chính xác toàn bộ input gốc và càng không phải một cam kết rằng input đã qua kiểm tra.

### 2.2. Khi target ban đầu bằng `null`

Spring Framework 6.1+ còn có **constructor binding**. Ứng dụng có thể tạo binder với target `null`, cấu hình kiểu đích bằng `setTargetType(...)` và gọi `construct(valueResolver)` để Spring dựng đối tượng từ giá trị cung cấp. Nếu dựng thành công, `getTarget()` sau `construct(...)` trả instance đã được tạo; lỗi conversion hoặc lỗi tạo đối tượng được ghi nhận theo cơ chế binding tương ứng.

Sơ đồ:

~~~text
new DataBinder(null, "order")
    -> setTargetType(...)
    -> construct(valueResolver)
    -> getBindingResult() để đọc lỗi
    -> getTarget() nếu object đã được tạo
~~~

Không suy diễn rằng `getTarget() != null` luôn đúng: trường hợp chỉ sử dụng binder để convert một tham số, chưa construct, hoặc không dựng được target có thể khiến nó `null`. Khi không có target, không được cast và dereference ngay.

Với bài toán chỉ có JavaBean có sẵn, `new DataBinder(existingObject, objectName)` là đường đơn giản và dễ quan sát hơn.

### 2.3. Target là dữ liệu sau bind, không phải dữ liệu đã được chấp nhận

Một hệ thống cần xác nhận số lượng dương và mã khuyến mại hợp lệ. Trong request, `quantity=3` bind thành công nhưng `discountCode` có thể vi phạm validation. `getTarget()` vẫn có thể cho thấy `quantity=3`; nếu ứng dụng lập tức lưu object này, một số dữ liệu từ request lỗi đã đi vào hệ thống. Vì vậy nên:

~~~java
binder.bind(properties);
binder.validate();

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    return; // Từ chối trước khi gọi service ghi dữ liệu.
}

OrderInput accepted = (OrderInput) binder.getTarget();
// Sau đó vẫn kiểm tra quyền và điều kiện nghiệp vụ cần thiết.
~~~

Chỉ chặn lỗi validation ở controller cũng chưa thay thế được các ràng buộc đồng thời tại service/DB, chẳng hạn tài nguyên đã hết hoặc một giá trị unique bị tranh chấp.

## 3. `getBindingResult()`: bằng chứng bind và validation

Khai báo API:

~~~java
public BindingResult getBindingResult()
~~~

`BindingResult` mở rộng giao diện `Errors` và tập trung **trạng thái lỗi** trong quá trình bind/validate của một object. Khi lấy sau cả `bind(...)` và `validate()`, kết quả có thể chứa:

- **Lỗi chuyển đổi kiểu**: ví dụ chuỗi `"abc"` không chuyển được sang số nguyên; lỗi thường có code `typeMismatch`.
- **Lỗi trường bắt buộc** do cấu hình binder như `setRequiredFields(...)`: code thường là `required`.
- **Lỗi được validator thêm vào** qua `errors.rejectValue(...)` hoặc `errors.reject(...)`.
- **Danh sách field bị suppression** nếu đã cấu hình giới hạn input như `setAllowedFields(...)`. Lưu ý: đây là thông tin riêng, **không mặc định trở thành `hasErrors() == true`**.

Các API hữu ích:

| API | Ý nghĩa |
| --- | --- |
| `hasErrors()` | Có ít nhất một lỗi bind hoặc validation được ghi nhận. |
| `getErrorCount()` | Tổng số lỗi trong kết quả. |
| `getAllErrors()` | Danh sách `ObjectError` và `FieldError`. |
| `getFieldErrors()`, `getFieldError("quantity")` | Các lỗi gắn với một thuộc tính. |
| `getGlobalErrors()` | Lỗi mức object, ví dụ quan hệ hai ngày không hợp lệ. |
| `getSuppressedFields()` | Field đầu vào bị binder chặn, ví dụ ngoài `allowedFields`. |
| `getObjectName()` | Tên logic của đối tượng (`"order"` trong ví dụ). |
| `getTarget()` | Đối tượng đích được phản ánh từ phía kết quả. |
| `getModel()` | Map gồm object và `BindingResult` theo các key dùng cho cơ chế model/view. |
| `getFieldValue("quantity")` | Giá trị mà kết quả binding dùng khi hiển thị field; **có thể là rejected value** nếu field có lỗi. |
| `getRawFieldValue("quantity")` | Giá trị thô của field trên target theo cơ chế truy cập thuộc tính của result. |
| `resolveMessageCodes(...)` | Danh sách code theo thứ tự phân giải thông điệp cho field hoặc object. |

Một `FieldError` có thể cho biết:

~~~java
FieldError failure = result.getFieldError("quantity");
if (failure != null) {
    String field = failure.getField();
    String code = failure.getCode();
    Object rejected = failure.getRejectedValue();
    boolean conversionFailed = failure.isBindingFailure();
}
~~~

`rejected` có thể chứa input do người dùng cung cấp; **không đưa nguyên giá trị bị từ chối vào log/response** khi nó có thể là dữ liệu nhạy cảm. `isBindingFailure()` giúp phân biệt lỗi do binder/conversion với lỗi do validator ghi nhận trong các trường hợp thông thường.

### Vì sao `getFieldValue` có thể khác giá trị trên target?

Đây là khác biệt dễ nhầm:

~~~text
Request: quantity = "abc"
Object trước bind: quantity = 5
               |
       binder.bind(...)
               |
  +------------+-------------------------+
  |                                      |
target.quantity vẫn có thể là 5    FieldError.rejectedValue = "abc"
                                         |
                              BindingResult.getFieldValue(...)
                              có thể trả "abc" để hiển thị
~~~

Khi một field có `FieldError`, `BindingResult.getFieldValue(...)` có thể ưu tiên **rejected value** để biểu mẫu cho phép người dùng thấy và sửa dữ liệu vừa nhập. Bởi vậy, không được xem `result.getFieldValue("quantity")` như cách duy nhất lấy giá trị Java hợp lệ. Nếu cần dữ liệu đã gán lên object, hãy đọc từ `getTarget()` hoặc getter của DTO; nếu cần giải thích lý do từ chối, đọc `FieldError`.

### `getModel()` không thay thế các bước kiểm tra

~~~java
Map<String, Object> model = result.getModel();

Object form = model.get("order");
Object errors = model.get(
        BindingResult.MODEL_KEY_PREFIX + "order");
~~~

`getModel()` tạo map mới cho trạng thái hiện tại, thường gồm key tên object và key ghép từ `BindingResult.MODEL_KEY_PREFIX` với tên object. Nó hữu ích khi tự chuẩn bị model cho view; **mỗi lần gọi trả map mới**, nên sửa map tạm rồi gọi lại `getModel()` sẽ không giữ các sửa đổi đó. Không cần dùng `getModel()` chỉ để quyết định đầu vào có lỗi hay không: `hasErrors()` trực tiếp hơn.

## 4. Ví dụ Java 17+ hoàn chỉnh: object có thể đã thay đổi dù binding thất bại

Ví dụ dùng **Spring Framework 6.2.0**, `DataBinder`, một `Validator` và danh sách field cho phép. Chương trình chạy ba trường hợp:

1. Dữ liệu hợp lệ.
2. Sai kiểu của `quantity`, thiếu `customer` hợp lệ và cố gửi field không được phép `role`.
3. Dữ liệu hợp lệ nhưng cố gửi `role`; điều này minh họa **suppressed field không nhất thiết làm `hasErrors()` thành true**.

Tạo cấu trúc:

~~~text
databinder-results/
├── pom.xml
└── src/main/java/demo/DataBinderResultsDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>databinder-results</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.DataBinderResultsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/DataBinderResultsDemo.java`:

~~~java
package demo;

import java.util.Arrays;
import java.util.List;
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class DataBinderResultsDemo {

    public static class OrderInput {
        private String customer;
        private Integer quantity = 5;
        private String role = "USER";

        public String getCustomer() {
            return customer;
        }

        public void setCustomer(String customer) {
            this.customer = customer;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }
    }

    public static class OrderValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return OrderInput.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            OrderInput order = (OrderInput) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "customer", "customer.required",
                    "Tên khách hàng là bắt buộc");

            // Tránh phát sinh lỗi số lượng chồng lên lỗi conversion.
            if (!errors.hasFieldErrors("quantity")
                    && (order.getQuantity() == null
                        || order.getQuantity() <= 0)) {
                errors.rejectValue(
                        "quantity", "quantity.positive",
                        "Số lượng phải lớn hơn 0");
            }
        }
    }

    private static void run(
            String name, Map<String, String> properties) {

        OrderInput target = new OrderInput();
        DataBinder binder = new DataBinder(target, "order");

        // Ngăn client tự gán thuộc tính "role".
        binder.setAllowedFields("customer", "quantity");
        binder.setValidator(new OrderValidator());

        binder.bind(new MutablePropertyValues(properties));
        binder.validate();

        OrderInput current = (OrderInput) binder.getTarget();
        BindingResult result = binder.getBindingResult();

        List<String> fieldCodes = result.getFieldErrors()
                .stream()
                .map(error -> error.getField()
                        + ":" + error.getCode())
                .sorted()
                .toList();

        System.out.println(name + " target: quantity="
                + current.getQuantity()
                + ", role=" + current.getRole());
        System.out.println(name + " sameTarget="
                + (current == target && result.getTarget() == target));
        System.out.println(name + " errors="
                + result.getErrorCount() + ", fields=" + fieldCodes);
        System.out.println(name + " suppressed="
                + Arrays.toString(result.getSuppressedFields()));

        boolean proceed = !result.hasErrors()
                && result.getSuppressedFields().length == 0;
        System.out.println(name + " proceed=" + proceed);
    }

    public static void main(String[] args) {
        run("valid",
                Map.of("customer", "Lan", "quantity", "3"));

        run("invalid",
                Map.of("customer", "  ",
                       "quantity", "abc",
                       "role", "ADMIN"));

        run("suppressedOnly",
                Map.of("customer", "Lan",
                       "quantity", "3",
                       "role", "ADMIN"));
    }
}
~~~

Chạy bằng Maven với **JDK 17+**:

~~~bash
mvn -q compile exec:java
~~~

Kết quả mong đợi:

~~~text
valid target: quantity=3, role=USER
valid sameTarget=true
valid errors=0, fields=[]
valid suppressed=[]
valid proceed=true
invalid target: quantity=5, role=USER
invalid sameTarget=true
invalid errors=2, fields=[customer:customer.required, quantity:typeMismatch]
invalid suppressed=[role]
invalid proceed=false
suppressedOnly target: quantity=3, role=USER
suppressedOnly sameTarget=true
suppressedOnly errors=0, fields=[]
suppressedOnly suppressed=[role]
suppressedOnly proceed=false
~~~

Đọc kết quả theo từng trường hợp:

- **`valid`:** `"3"` được chuyển thành `Integer 3`. Validator không ghi lỗi. `getTarget()` và `BindingResult.getTarget()` đều hướng tới cùng DTO, nên ở trường hợp này ứng dụng có thể tiếp tục kiểm tra nghiệp vụ.
- **`invalid`:** chuỗi `"abc"` không thể chuyển thành `Integer` nên `BindingResult` có `typeMismatch`. Vì target khởi tạo `quantity = 5`, thuộc tính này giữ lại 5 sau lỗi chuyển đổi; đây là minh họa quan trọng cho việc **không tin mỗi target khi quyết định hợp lệ**. `customer` chỉ có dấu cách nên validator tạo thêm lỗi `customer.required`. `role` bị loại khỏi binding.
- **`suppressedOnly`:** hai field hợp lệ, `hasErrors()` trả `false`. Nhưng `role=ADMIN` vẫn bị suppression. Chương trình chọn chính sách **từ chối request chứa field không được phép**, nên `proceed=false` dù `getErrorCount()==0`.

Đây là **chính sách minh họa của ứng dụng**: Spring không tự bắt buộc từ chối tất cả request có suppressed field. Tùy contract, ứng dụng có thể chủ động trả lỗi, ghi nhận sự kiện bảo mật hoặc bỏ qua field ngoài danh sách. Trong hệ thống nhạy cảm, từ chối một cố gắng gán field ngoài allowlist thường dễ kiểm soát hơn.

Để đơn giản hóa, ví dụ chỉ dùng setter/property binding. Khai báo field `role` có setter nhằm cho thấy tác dụng của allowlist; trong ứng dụng thực tế nên thiết kế input DTO **không chứa trường đặc quyền** nếu request không được quyền cập nhật trường đó.

## 5. Đọc `BindingResult` đúng chỗ trong luồng xử lý

Một trình tự an toàn ở tầng tiếp nhận input:

~~~java
DataBinder binder = new DataBinder(input, "order");
binder.setAllowedFields("customer", "quantity");
binder.setValidator(new OrderValidator());

binder.bind(propertyValues);
binder.validate();

BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    // Trả danh sách lỗi để client sửa input.
    return;
}

if (result.getSuppressedFields().length > 0) {
    // Xử lý theo chính sách: ví dụ từ chối field không được phép.
    return;
}

OrderInput accepted = (OrderInput) binder.getTarget();
// Kiểm tra quyền và bất biến nghiệp vụ trong service rồi mới lưu.
~~~

Đoạn trên là ví dụ luồng logic, chưa phải một phương thức Java hoàn chỉnh vì `propertyValues` và bối cảnh `return` do tầng gọi cung cấp.

**Thời điểm lấy result quan trọng:** `getBindingResult()` có thể được gọi trước hay sau các thao tác, nhưng bạn nên **đánh giá kết quả sau các bước đã dự định chạy**. Nếu lấy rồi kiểm tra trước `validate()`, sẽ không thể kết luận validator không tạo lỗi vì nó chưa chạy. `BindingResult` phản ánh các lỗi đã được thêm vào trong phiên binder; nó không tự kích hoạt validator khi bạn đọc.

**Lỗi không đồng nghĩa exception ngay lập tức:** `binder.bind(...)` có thể thu thập lỗi conversion vào `BindingResult` để ứng dụng xử lý; không phải mọi input sai kiểu đều khiến lời gọi `bind(...)` lập tức ném exception ra ngoài. Dù vậy, lỗi cấu hình, truy cập thuộc tính hoặc lỗi lập trình vẫn có thể gây exception; đừng xem `BindingResult` là một cơ chế bắt tất cả loại exception.

### Mã lỗi và phản hồi cho người dùng

Trong ứng dụng web, không nên chỉ trả thông điệp `result.toString()`. Hãy dựng cấu trúc gồm field, error code và thông điệp phù hợp. Ví dụ API contract do ứng dụng tự định nghĩa:

~~~json
{
  "code": "INVALID_INPUT",
  "errors": [
    {
      "field": "quantity",
      "code": "typeMismatch",
      "message": "Số lượng phải là số nguyên"
    },
    {
      "field": "customer",
      "code": "customer.required",
      "message": "Tên khách hàng là bắt buộc"
    }
  ]
}
~~~

Dùng `MessageSource` và danh sách mã lỗi nếu cần bản địa hóa; `FieldError.getCode()` thường là mã khái quát, trong khi `getCodes()` chứa các phương án mã theo thứ tự ưu tiên. Giữ định dạng phản hồi ổn định để frontend có thể đánh dấu đúng input.

## 6. `getTarget()` và `getBindingResult()` không thể thay thế nhau

| Góc nhìn | `getTarget()` | `getBindingResult()` |
| --- | --- | --- |
| Kiểu trả về | `Object` có thể `null` | `BindingResult` |
| Mục đích | Xem object hiện tại | Xem lỗi bind, lỗi validator, field bị suppression |
| Phản ánh giá trị đã gán thành công | Có | Có thể truy xuất gián tiếp; mục đích chính là kết quả binding |
| Ghi nhận chuỗi đầu vào bị từ chối vì sai kiểu | Không bảo đảm | `FieldError.getRejectedValue()` và `getFieldValue(...)` có thể lưu để hiển thị |
| Xác định “request hợp lệ” bằng một phép đọc | Không | `hasErrors()`, kết hợp quy tắc suppression và nghiệp vụ |
| Target có thể đã thay đổi dù có lỗi | Có | Result ghi lại những lỗi đã phát sinh |
| Dùng cho form model | Object của form | Lỗi của form; `getModel()` có thể kết hợp cả hai |
| Dùng trong controller/service | Đọc DTO để truyền tiếp **sau kiểm tra** | Quyết định nhánh lỗi, dựng phản hồi, quan sát lỗi |

**Một target không `null` không chứng minh bind thành công toàn bộ.** **Một `BindingResult` không có lỗi cũng không chứng minh business rule/authorization đã được kiểm tra.** Hai API giúp ứng dụng phân biệt “dữ liệu hiện có” và “kết quả xử lý dữ liệu đầu vào”.

## 7. Các tình huống dễ hiểu sai

### 7.1. Input thiếu field khác với input sai kiểu

Giả sử object ban đầu có `quantity=5`.

- Không gửi `quantity`: property binding thường giữ `5`; nếu muốn bắt buộc có field, cần ràng buộc phù hợp, ví dụ `setRequiredFields("quantity")` hoặc validation/contract kiểm tra sự hiện diện.
- Gửi `quantity=7`: conversion thành công, target mang `7`.
- Gửi `quantity=abc`: có thể có `typeMismatch`, target vẫn mang `5`.
- Gửi giá trị rỗng: kết quả phụ thuộc kiểu trường, converter và cấu hình; không giả định mọi chuỗi rỗng luôn tạo cùng lỗi.

Với một DTO mới khởi tạo và trường `Integer quantity` chưa được đặt, thiếu field thường để lại `null`. Khi đó `@NotNull` (nếu Bean Validation được cấu hình/chạy) hoặc custom validator có thể phát hiện trường thiếu. Nếu đã gán giá trị mặc định từ trước, kiểm tra `@NotNull` trên target không tự phát hiện sự vắng mặt của field.

### 7.2. Validator không tự chạy từ `getBindingResult()`

~~~java
binder.bind(propertyValues);

BindingResult beforeValidation = binder.getBindingResult();
// Lúc này mới có những lỗi bind đã được ghi nhận.

binder.validate();

BindingResult afterValidation = binder.getBindingResult();
// Sau validate, đọc toàn bộ lỗi bind + các lỗi mà validator đã thêm.
~~~

`getBindingResult()` không phải một lệnh “tự động kiểm tra lại mọi thứ”. Trong Spring MVC, framework có thể gọi validation trong vòng đời controller khi bạn dùng `@Valid`/`@Validated`; còn với `DataBinder` lập trình thủ công, việc gọi `validate()` là trách nhiệm của đoạn mã sử dụng.

### 7.3. Nhầm `BindingResult` với `Errors` hoặc `Validator.validateObject`

`BindingResult` kế thừa `Errors` và có thêm các chức năng liên quan binding. `Validator.validateObject(...)` (từ Spring 6.1) lại trả một `Errors` cho validation trực tiếp bằng `SimpleErrors`. Đây là API tiện dùng cho object đã có sẵn; nó **không thay cho `DataBinder.bind(...)`** và không tự sinh đầy đủ lỗi conversion của một request.

Khi cần kết hợp bind rồi validate, sử dụng `DataBinder.getBindingResult()` giúp đọc **cùng một tập lỗi** trong phiên bind. Không ép kết quả `Errors` của `validateObject(...)` thành `BindingResult`.

### 7.4. Bỏ qua suppressed fields

~~~java
binder.setAllowedFields("customer", "quantity");
binder.bind(propertyValues);

String[] blocked = binder.getBindingResult()
        .getSuppressedFields();
~~~

Nếu client gửi `role=ADMIN`, nhưng `role` không nằm trong allowlist, Spring có thể bỏ qua thay đổi này và ghi nhận `"role"` trong `blocked`. `hasErrors()` có thể vẫn là `false`. Vì thế đừng kết luận “không có `FieldError`” nghĩa là request không chứa field đáng ngờ.

### 7.5. Bind thẳng entity có field đặc quyền

Nếu bind request vào entity chứa `isAdmin`, `accountBalance` hoặc `ownerId`, getter của `getTarget()` có thể phản ánh các thay đổi không nên cho phép. Phân quyền ở service không sửa được việc đã dùng DTO sai mục đích. Dùng DTO chỉ chứa field người dùng được sửa, kết hợp allowlist khi cần, và ánh xạ có kiểm soát vào domain entity. Đối với giao dịch dữ liệu quan trọng, tiếp tục kiểm tra ràng buộc nghiệp vụ và DB trong transaction phù hợp.

### 7.6. Dùng lại một binder cho nhiều request

`DataBinder` và `BindingResult` chứa trạng thái gắn với một quá trình xử lý. Thông thường tạo binder riêng cho mỗi object/lượt input; không chia sẻ một binder mutable giữa các request hoặc nhiều luồng. Một binder chứa lỗi của lượt trước không phải một phiên validation mới sạch để xử lý request khác.

## 8. Kiểm thử điều gì để chứng minh xử lý đúng?

Khi viết test cho đoạn code sử dụng `getTarget()` và `getBindingResult()`, cần bao phủ **cả object và kết quả lỗi**:

| Kịch bản | Kiểm tra target | Kiểm tra result | Quyết định |
| --- | --- | --- | --- |
| Input đúng kiểu và đạt validation | Giá trị đã bind như mong đợi | `hasErrors() == false`; không suppressed field | Có thể tiếp tục kiểm tra nghiệp vụ |
| Một field sai kiểu | Field hợp lệ khác có thể đã thay đổi; field sai có thể giữ giá trị cũ | Có `FieldError` dạng `typeMismatch` | Từ chối |
| Field bắt buộc không hợp lệ | Target vẫn có thể chứa giá trị rỗng | Có `FieldError` được validator thêm | Từ chối |
| Input có field ngoài allowlist | Thuộc tính bị cấm không bị cập nhật | `getSuppressedFields()` có field bị chặn | Quyết định theo chính sách, ví dụ từ chối |
| Không gọi `validate()` | Dữ liệu đã bind vào object | Chỉ có những lỗi bind đã được ghi nhận | Không coi đây là validation hoàn chỉnh |
| Constructor binding với target ban đầu `null` | Có thể có instance sau `construct(...)` hoặc vẫn `null` | Có thể có lỗi khởi tạo/bind | Phải đọc result và kiểm tra target trước khi dùng |

Với ứng dụng có service ghi dữ liệu, nên bổ sung test xác minh **không gọi service** khi `result.hasErrors()` hoặc khi request vi phạm chính sách suppressed fields. Chỉ assert nội dung field trong DTO không đủ chứng minh hệ thống chặn input lỗi.

## 9. Checklist ngắn khi áp dụng

1. Tạo `DataBinder` cho đúng input DTO; cấu hình danh sách field được phép và bộ converter/validator cần thiết.
2. Thực thi binding (`bind(...)` hoặc `construct(...)` theo đường xử lý), rồi gọi `validate()` nếu ứng dụng cần chạy các validator đã đăng ký.
3. Đọc `BindingResult result = binder.getBindingResult()` sau các bước dự định chạy.
4. Kiểm tra `hasErrors()`, đọc `FieldError`/`ObjectError` và `getSuppressedFields()` để quyết định nhánh lỗi.
5. Chỉ đọc/cast `binder.getTarget()` sau khi đã xác nhận target tồn tại và đủ điều kiện dùng; nhớ rằng object có thể đã bị cập nhật một phần dù có lỗi.
6. Thực hiện kiểm tra quyền và ràng buộc nghiệp vụ còn lại trước các side effect như ghi DB, gửi message hoặc gọi API thay đổi trạng thái.

### Tài liệu Spring chính thức

- [Spring — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring — Configuring a DataBinder and validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring — DataBinder API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring — FieldError API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/FieldError.html)
