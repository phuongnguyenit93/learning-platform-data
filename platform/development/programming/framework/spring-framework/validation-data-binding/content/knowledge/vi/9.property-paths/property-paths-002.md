# Chỉ số phần tử trong đường dẫn thuộc tính: items[0].name

Khi một biểu mẫu chứa **danh sách đối tượng**, Spring Framework cần biết từng giá trị đầu vào thuộc phần tử nào và thuộc tính nào của phần tử đó. Cú pháp như `items[0].name` là **đường dẫn thuộc tính có chỉ số** (*indexed property path*), dùng bởi cơ chế JavaBean property access và data binding của Spring.

Ví dụ một đơn hàng gồm hai dòng:

~~~text
items[0].name=Bút
items[0].quantity=3
items[1].name=Vở
items[1].quantity=5
~~~

Spring có thể ánh xạ bốn cặp tên–giá trị này vào một đối tượng `OrderForm` chứa `List<ItemForm>`. Mỗi phần tử của danh sách có thuộc tính `name` và `quantity`; phần tử thứ nhất được chọn bằng `[0]`, phần tử thứ hai bằng `[1]`.

Bài này tập trung vào ý nghĩa đường dẫn `items[0].name`, cách binder đi qua đối tượng lồng nhau và danh sách, cơ chế tự mở rộng phần tử, lỗi và validation theo chỉ số, cùng các biện pháp tránh chấp nhận những đường dẫn không mong muốn từ request.

## 1. Phân tích cú pháp items[0].name

Đường dẫn có ba phần:

~~~text
items[0].name
│    │   │
│    │   └── property name của đối tượng ItemForm
│    └────── chỉ số 0, phần tử đầu tiên của List/array
└────────── property items của đối tượng gốc
~~~

Nếu đối tượng gốc là:

~~~java
public class OrderForm {
    private List<ItemForm> items;
    // getters và setters
}
~~~

và mỗi phần tử là:

~~~java
public class ItemForm {
    private String name;
    private Integer quantity;
    // getters và setters
}
~~~

thì việc gán đường dẫn `items[0].name` tương đương về **đích dữ liệu** với:

~~~java
order.getItems().get(0).setName("Bút");
~~~

Tuy nhiên, khi gọi binder, Spring còn xử lý chuyển kiểu, giới hạn field được phép, tạo đối tượng trung gian (nếu cấu hình hỗ trợ), và thu thập lỗi; vì thế không nên xem binding là một lời gọi setter Java thuần túy.

**Chỉ số bắt đầu từ 0** đối với `List` và array:

| Đường dẫn | Đích trên đối tượng |
|---|---|
| `items[0].name` | `items.get(0).getName()` |
| `items[0].quantity` | `items.get(0).getQuantity()` |
| `items[1].name` | `items.get(1).getName()` |
| `items[2].quantity` | `items.get(2).getQuantity()` |
| `items[0]` | Toàn bộ phần tử tại chỉ số 0 (khi kiểu và converter cho phép) |

Ký tự `.` phân cách các thuộc tính lồng nhau, còn `[0]` chọn một phần tử trong cấu trúc có thể truy cập theo chỉ số. Với Map, dấu ngoặc vuông lại chỉ **key**, chẳng hạn `attributes[sku]` hoặc `entries[ABC].value`; loại collection khai báo trên target quyết định cách hiểu, không phải chỉ riêng hình dạng chuỗi.

## 2. Cơ chế Spring nhận đường dẫn có chỉ số

Cơ chế lõi của Spring là `BeanWrapper` (và hạ tầng `PropertyAccessor`) có thể đọc/ghi thuộc tính JavaBean đơn giản, lồng nhau và có chỉ số. `DataBinder` dùng cơ chế này khi thực hiện **property binding**; trong Spring MVC, `WebDataBinder` thường phục vụ việc bind tham số form/query vào `@ModelAttribute`.

Luồng điển hình với `items[1].quantity=5`:

1. Nhận tên property `items[1].quantity` và giá trị đầu vào là chuỗi `"5"`.
2. Tìm property `items` trên `OrderForm`.
3. Truy cập phần tử có chỉ số 1 trong `List<ItemForm>`; khi đủ điều kiện, binder tự tạo phần tử cần thiết.
4. Tìm property `quantity` của `ItemForm` tại chỉ số 1.
5. Chuyển `"5"` thành `Integer.valueOf(5)` qua hạ tầng type conversion.
6. Gọi setter hoặc cơ chế property access tương ứng để gán giá trị.
7. Nếu không chuyển/gán được theo loại lỗi mà binder có thể thu thập, ghi lỗi vào `BindingResult`, gắn tên trường đầy đủ như `items[1].quantity`.

~~~text
Form/query parameters
  "items[0].name"        = "Bút"
  "items[0].quantity"    = "3"
  "items[1].name"        = "Vở"
  "items[1].quantity"    = "5"
             │
             ▼
           DataBinder
             │
             ▼
         OrderForm
             │
             └── items: List<ItemForm>
                    │
                    ├── [0] ItemForm
                    │       name     = "Bút"
                    │       quantity = 3
                    │
                    └── [1] ItemForm
                            name     = "Vở"
                            quantity = 5
~~~

**Đây là cú pháp dành cho property path**, không phải JSONPath, tên field trong database, biểu thức Spring Expression Language tổng quát hay cách tự suy ra cấu trúc từ một chuỗi tùy ý. `DataBinder` sẽ làm việc dựa trên metadata, kiểu và cấu hình của đối tượng đích.

## 3. Mô hình JavaBean phù hợp để bind danh sách

Ví dụ JavaBean:

~~~java
import java.util.ArrayList;
import java.util.List;

public class OrderForm {
    private List<ItemForm> items = new ArrayList<>();

    public List<ItemForm> getItems() {
        return items;
    }

    public void setItems(List<ItemForm> items) {
        this.items = items;
    }
}

public class ItemForm {
    private String name;
    private Integer quantity;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

Hai lớp ở trên là **hai tệp Java riêng** nếu dùng `public class` cấp cao nhất: `OrderForm.java` và `ItemForm.java`. Phần dưới có chương trình độc lập đặt hai kiểu vào lớp lồng nhau để có thể chạy bằng một tệp.

Những điều kiện quan trọng:

- Target phải có property `items` đọc/ghi được theo chế độ access đã chọn. Hình thức JavaBean getter/setter hoạt động tốt với property binding mặc định.
- Kiểu phần tử `ItemForm` cần đủ thông tin để Spring tạo/truy cập phần tử khi auto-grow. Một lớp cụ thể có constructor không tham số là trường hợp thuận tiện; abstract class, interface hoặc kiểu không thể khởi tạo có thể cần cấu hình khác.
- Khai báo generic `List<ItemForm>` giúp Spring biết kiểu phần tử. `List` raw hoặc kiểu quá mơ hồ làm việc suy luận/khởi tạo kiểu khó khăn hơn.
- `Integer` cho phép biểu diễn `null`, hữu ích để phân biệt trường chưa nhập hoặc không chuyển được; `int` mặc định bằng 0, khiến một số tình huống thiếu giá trị khó phân biệt.
- Việc khởi tạo `new ArrayList<>()` giúp rõ ràng trạng thái ban đầu. Nếu `items == null`, khả năng tự tạo danh sách phụ thuộc cấu hình auto-grow và khả năng xác định kiểu.
- Binder thông thường làm việc với **đối tượng dữ liệu đầu vào chuyên dụng**, không nên nhận trực tiếp một JPA entity với nhiều property nội bộ hoặc quan hệ nhạy cảm.

## 4. Ví dụ chạy được: bind nhiều phần tử, một phần tử sai kiểu

Ví dụ này sử dụng **Java 17+** và **Spring Framework 6.2.x**; tệp chính `IndexedBindingDemo.java` chạy độc lập về mặt chương trình nhưng cần Spring JAR trên classpath. Maven giúp tải dependency tương thích và thực thi dễ dàng.

Cấu trúc thư mục:

~~~text
indexed-binding-demo/
├── pom.xml
└── src/main/java/demo/IndexedBindingDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>indexed-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/IndexedBindingDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public final class IndexedBindingDemo {

    public static class OrderForm {
        private List<ItemForm> items = new ArrayList<>();

        public List<ItemForm> getItems() {
            return items;
        }

        public void setItems(List<ItemForm> items) {
            this.items = items;
        }
    }

    public static class ItemForm {
        private String name;
        private Integer quantity;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

    public static void main(String[] args) {
        OrderForm order = new OrderForm();
        DataBinder binder = new DataBinder(order, "order");

        // Quy định trước khi bind; 10 là số phần tử tối đa
        // binder được phép tự mở rộng trong ví dụ.
        binder.setAutoGrowCollectionLimit(10);
        binder.setAllowedFields("items[*].name", "items[*].quantity");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("items[0].name", "Bút");
        input.add("items[0].quantity", "3");
        input.add("items[1].name", "Vở");
        input.add("items[1].quantity", "abc");

        binder.bind(input);
        BindingResult result = binder.getBindingResult();

        System.out.println("items.size=" + order.getItems().size());
        System.out.println("items[0].name="
                + order.getItems().get(0).getName());
        System.out.println("items[0].quantity="
                + order.getItems().get(0).getQuantity());
        System.out.println("items[1].name="
                + order.getItems().get(1).getName());
        System.out.println("items[1].quantity="
                + order.getItems().get(1).getQuantity());

        FieldError error = result.getFieldError("items[1].quantity");
        if (error == null) {
            throw new AssertionError("Expected typeMismatch error");
        }

        System.out.println("error.field=" + error.getField());
        System.out.println("error.code=" + error.getCode());
        System.out.println("error.rejected=" + error.getRejectedValue());
        System.out.println("error.bindingFailure=" + error.isBindingFailure());
        System.out.println("field.type="
                + result.getFieldType("items[1].quantity").getName());
        System.out.println("hasErrors=" + result.hasErrors());
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.IndexedBindingDemo
~~~

Các dòng chương trình in ra:

~~~text
items.size=2
items[0].name=Bút
items[0].quantity=3
items[1].name=Vở
items[1].quantity=null
error.field=items[1].quantity
error.code=typeMismatch
error.rejected=abc
error.bindingFailure=true
field.type=java.lang.Integer
hasErrors=true
~~~

**Vì sao kết quả như vậy?**

1. Danh sách ban đầu rỗng, nhưng `DataBinder` được bật auto-grow theo chế độ property binding thông thường. Các đường dẫn tới `[0]` và `[1]` giúp Spring tạo hai `ItemForm`.
2. `items[0].name` và `items[1].name` nhận chuỗi hợp lệ; `items[0].quantity="3"` chuyển sang `Integer(3)`.
3. `items[1].quantity="abc"` không thể chuyển thành `Integer`. Binder ghi `FieldError` cho **đúng đường dẫn đầy đủ** `items[1].quantity`. Trường này giữ giá trị ban đầu `null`, trong khi các trường khác đã gán vẫn giữ kết quả.
4. `getRejectedValue()` cho giá trị `"abc"`; `getFieldType(...)` xác định kiểu target là `Integer.class`. Hai thông tin này giải thích lỗi nhưng không biến chuỗi sai thành dữ liệu hợp lệ.
5. `hasErrors() == true` nghĩa là ứng dụng **không được tiếp tục lưu order** như thể toàn bộ request đã hợp lệ.

`DataBinder` trong ví dụ chỉ thực hiện binding, chưa tự gọi validator. Với Bean Validation ở Spring MVC, còn có thể xuất hiện lỗi `@NotBlank`, `@NotNull`, `@Min`... sau bước bind.

## 5. Tự mở rộng danh sách: auto-grow nested paths

Spring hỗ trợ **auto-grow nested paths** ở property binding trên `DataBinder` tiêu chuẩn. Với đường dẫn `items[2].name` trên danh sách rỗng, binder có thể mở rộng danh sách tới phần tử thứ ba và tạo đối tượng trung gian để tới property `name`.

Các API cấu hình liên quan:

~~~java
DataBinder binder = new DataBinder(order, "order");

binder.setAutoGrowNestedPaths(true);
binder.setAutoGrowCollectionLimit(20);
~~~

Giải thích:

- `setAutoGrowNestedPaths(true)`: cho phép tạo giá trị mặc định ở một phần nested path đang `null`, đồng thời cho phép auto-grow phần tử collection khi truy cập index ngoài kích thước hiện tại theo những điều kiện hỗ trợ. Giá trị mặc định ở `DataBinder` thông thường là `true`.
- `setAutoGrowCollectionLimit(20)`: giới hạn quy mô mở rộng tự động của array/collection; nên chọn theo nghiệp vụ. Giá trị mặc định ở các phiên bản Spring 6.x là 256, song không nên dựa vào giá trị mặc định như một hợp đồng phân trang hoặc hạn mức sản phẩm.
- Cần gọi các setter cấu hình **trước khi binder khởi tạo bộ quản lý binding nội bộ**, thường là trước `bind(...)` hoặc `getBindingResult()`.
- Khả năng tạo phần tử còn phụ thuộc vào kiểu danh sách, generic type, constructor, accessor và trạng thái ban đầu; không hứa mọi kiểu immutable collection, interface tùy ý hoặc entity phức tạp đều tự tạo được.

Ví dụ đường dẫn `items[3].name` có thể khiến `List` chứa bốn vị trí (chỉ số 0–3), nhưng các phần tử trung gian chưa chắc đã có dữ liệu hợp lệ. **Không đồng nhất “đã tạo được phần tử” với “người dùng đã nhập đủ bốn phần tử”.** Nếu muốn một đơn hàng có tối đa 20 dòng và các dòng liên tiếp, cần kiểm tra thêm kích thước, các phần tử thiếu, trường trống và chính sách đánh số chỉ số.

### Chỉ số lớn hoặc bất thường

Các tên như:

~~~text
items[999999].name=...
items[-1].name=...
items[not-an-index].name=...
~~~

không nên được xem là một cách nhập dữ liệu bình thường cho `List`. Chỉ số vượt giới hạn, không hợp lệ hoặc path không thể giải quyết có thể dẫn đến ngoại lệ property access hoặc phản hồi lỗi HTTP tùy binder và cách xử lý exception. **Không bảo đảm mọi lỗi chỉ số đều được chuyển thành `FieldError`** giống `typeMismatch`.

Thiết kế an toàn bao gồm:

- Đặt `setAutoGrowCollectionLimit` phù hợp với giới hạn số dòng nghiệp vụ.
- Hạn chế field bằng allowlist, ví dụ `items[*].name` và `items[*].quantity`; không cho phép tự ý gán `items[*].id`, `items[*].ownerId`, `items[*].approved` nếu đó là trường do server quản lý.
- Giới hạn kích thước request ở tầng web/server; kiểm tra số lượng dòng và định dạng chỉ số trong hợp đồng API.
- Dùng DTO/input object đơn giản, danh sách với hành vi index dự đoán được; cẩn trọng với custom collection có thể tạo phần tử khi gọi `get(index)`.
- Không dùng auto-grow thay cho validation: một danh sách đã mở rộng vẫn có thể thiếu tên, số lượng, hoặc có các vị trí rỗng không hợp lệ.

## 6. HTML form gửi tên field theo chỉ số

Ví dụ một form gửi hai dòng hàng:

~~~html
<form action="/orders" method="post">
  <div>
    <input name="items[0].name" value="Bút">
    <input name="items[0].quantity" type="number" value="3">
  </div>
  <div>
    <input name="items[1].name" value="Vở">
    <input name="items[1].quantity" type="number" value="5">
  </div>
  <button type="submit">Gửi đơn</button>
</form>
~~~

Đây là **mẫu HTML minh họa tên tham số**; một ứng dụng thực tế còn cần CSRF token nếu áp dụng CSRF protection, giao diện lỗi, xác thực và chính sách gửi request thích hợp.

Browser gửi tên field đúng như `items[0].name`; trong `application/x-www-form-urlencoded`, các ký tự ngoặc có thể được mã hóa khi truyền trên HTTP. Khi Spring MVC nhận lại tên tham số đã giải mã, `WebDataBinder` có thể sử dụng chúng như property path của `@ModelAttribute`.

Khi render form động, ứng dụng cần tạo `name` có index rõ ràng cho từng dòng. Một danh sách 5 phần tử **không đồng nghĩa** rằng đã có đủ các index 0–4 nếu người dùng xóa/chèn dòng trong trình duyệt mà không đánh số lại.

Ví dụ khi xóa dòng ở giữa:

~~~text
items[0].name=Bút
items[2].name=Thước
~~~

Phía server có thể phải xử lý phần tử tại `[1]` được tự tạo nhưng thiếu dữ liệu. Tùy hợp đồng, frontend nên đánh số lại tuần tự 0,1 hoặc backend chủ động nhận các ID dòng và xác định cách xử lý dòng thiếu. Không dựa vào index làm danh tính lâu dài của bản ghi.

## 7. Trong Spring MVC với @ModelAttribute và BindingResult

Một controller MVC cho danh sách item có thể nhận biểu mẫu theo cấu trúc:

~~~java
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
public class OrderController {

    @InitBinder("order")
    void initOrderBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "items[*].name",
                "items[*].quantity");
        binder.setAutoGrowCollectionLimit(20);
    }

    @PostMapping("/orders")
    String submit(
            @Valid @ModelAttribute("order") OrderForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "orders/form";
        }

        // Tại đây mới gọi service sau khi kiểm tra nghiệp vụ.
        return "orders/confirmation";
    }
}
~~~

Đây là **đoạn code cần tích hợp vào ứng dụng Spring MVC**, dùng `OrderForm` tương thích ở mục 3, có view templates, cấu hình web và service tương ứng. Không phải chương trình `javac` độc lập.

Điểm cần hiểu:

- `@ModelAttribute("order")`: Spring tạo/lấy form object rồi liên kết dữ liệu request với các property, bao gồm `items[0].name`.
- `@InitBinder("order")`: cấu hình binder dành cho model attribute mang tên `order`, giới hạn field được bind và mức tự mở rộng của collection.
- `@Valid`: kích hoạt validation khi có provider và các annotation/ràng buộc thích hợp; không tự bảo đảm item trong danh sách được kiểm tra nếu DTO chưa khai báo cascade validation.
- `BindingResult` phải **đứng ngay sau** tham số model attribute mà nó mô tả để method có thể xử lý lỗi binding/validation.
- Khi một quantity sai kiểu, lỗi thường dùng đường dẫn đầy đủ `items[1].quantity`, nhờ đó view biết vị trí chính xác cần báo.
- Giá trị đã bind thành công ở các dòng khác vẫn có thể nằm trong `form`; nhưng phải xử lý lỗi trước khi lưu.

**Phạm vi:** Cách trên là **property binding** cho `@ModelAttribute`. Với `@RequestBody` JSON, Jackson/HTTP message conversion xử lý việc tạo object từ JSON và lỗi parse/deserialization theo cơ chế khác. Một mảng JSON `{"items":[{"name":"Bút"}]}` không có các key văn bản `items[0].name` theo nghĩa form-url-encoded, dù đối tượng Java cuối cùng có cùng cấu trúc.

## 8. Validation cho từng phần tử và tên lỗi có index

Một form thực tế có thể cần bảo đảm mỗi dòng có tên không rỗng và số lượng dương. Bean Validation dùng cascade validation để đi từ form vào các phần tử.

Ví dụ **bổ sung cho DTO khi tích hợp Spring MVC**, yêu cầu có Jakarta Validation API và provider (Spring Boot thường dùng starter validation):

~~~java
import java.util.ArrayList;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class OrderForm {
    @NotEmpty
    @Size(max = 20)
    @Valid
    private List<ItemForm> items = new ArrayList<>();

    public List<ItemForm> getItems() {
        return items;
    }

    public void setItems(List<ItemForm> items) {
        this.items = items;
    }
}

public class ItemForm {
    @NotBlank
    @Size(max = 100)
    private String name;

    @NotNull
    @Min(1)
    @Max(1000)
    private Integer quantity;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

Hai `public class` ở đây thuộc **hai file Java riêng**. Annotation `@Valid` ở property danh sách yêu cầu cascade xuống các `ItemForm`; `@NotBlank`, `@NotNull`, `@Min`, `@Max` đặt quy tắc cho từng dòng. Đặt `@Size(max = 20)` là kiểm tra nghiệp vụ **sau binding**, không thay thế `setAutoGrowCollectionLimit(20)` để giới hạn mở rộng khi đang xử lý property path.

Ví dụ hai trường hợp:

- `items[1].quantity=abc`: lỗi chuyển kiểu, thường có code `typeMismatch`, `FieldError.getField()` là `items[1].quantity`, `isBindingFailure()` là `true`.
- `items[1].quantity=0`: chuyển thành `Integer(0)` thành công, nhưng `@Min(1)` từ chối. Lỗi validation có thể gắn cùng đường dẫn `items[1].quantity` với mã tương ứng `Min`.

Để đọc và trình bày:

~~~java
if (errors.hasErrors()) {
    for (var fieldError : errors.getFieldErrors()) {
        String path = fieldError.getField();
        String code = fieldError.getCode();

        // path có thể là "items[1].quantity".
        // Chuyển code thành thông báo thân thiện và an toàn.
    }
}
~~~

Không giả định lỗi nào cũng thuộc `items[*]`: `BindingResult` còn có thể chứa lỗi tổng thể từ `@NotEmpty` trên `items`, lỗi ở trường khác, hoặc `ObjectError`. Khi cần mọi lỗi, xét `getAllErrors()` và phân biệt lỗi field với lỗi cấp đối tượng.

## 9. Đọc lỗi và giá trị theo đúng đường dẫn

Với lỗi ở phần tử thứ hai, truyền **đúng path đầy đủ**:

~~~java
String field = "items[1].quantity";

boolean invalid = result.hasFieldErrors(field);
var error = result.getFieldError(field);

if (error != null) {
    Object rejected = error.getRejectedValue();
    boolean bindingFailed = error.isBindingFailure();
}

Class<?> expectedType = result.getFieldType(field);
Object displayValue = result.getFieldValue(field);
~~~

Các API trong ví dụ:

| API | Cách hiểu |
|---|---|
| `hasFieldErrors("items[1].quantity")` | Có lỗi được ghi cho trường quantity tại index 1 hay không |
| `getFieldError("items[1].quantity")` | Lỗi đầu tiên của trường đó, có thể `null` |
| `getFieldErrors("items[1].quantity")` | Tất cả lỗi gắn với trường đó |
| `getFieldType("items[1].quantity")` | Kiểu Java property đích nếu xác định được (trong ví dụ: `Integer.class`) |
| `getFieldValue("items[1].quantity")` | Giá trị phục vụ báo lỗi/hiển thị; khi binding thất bại có thể là chuỗi bị từ chối |
| `FieldError.getRejectedValue()` | Giá trị mà lỗi cụ thể từ chối, ví dụ `"abc"` |
| `FieldError.isBindingFailure()` | Phân biệt lỗi binding với lỗi validation trong nhiều trường hợp thông thường |

Với một quantity không chuyển được, `order.getItems().get(1).getQuantity()` có thể là `null` hay giá trị cũ, trong khi `getFieldValue("items[1].quantity")` vẫn phản ánh đầu vào bị từ chối để render form. Không nên lấy target value rồi kết luận người dùng đã nhập `null`.

**Nếu index không có thật**, lời gọi truy cập property theo path có thể không đọc được, trả kết quả không xác định hoặc ném ngoại lệ tùy cách triển khai và trạng thái form. Đừng dùng API lấy giá trị field như một cách duyệt index vô hạn từ request. Đối với lỗi đã thu thập, nên duyệt trực tiếp `getFieldErrors()`.

## 10. Các kiểu property path có liên quan

| Ví dụ | Dạng truy cập | Chú ý |
|---|---|---|
| `customer.name` | Thuộc tính lồng nhau | Không có index; `customer` phải đọc/tạo được |
| `items[0].name` | Thuộc tính của phần tử đầu `List`/array | Index 0 là phần tử đầu tiên |
| `items[1].quantity` | Thuộc tính của phần tử thứ hai | Có thể cần chuyển kiểu sang số |
| `items[0].options[2].code` | Đường dẫn lồng nhau với hai cấp index | Cần cả hai collection và đối tượng trung gian khả dụng |
| `attributes[locale]` | Giá trị Map theo key `locale` | Không mang nghĩa phần tử thứ `locale` |
| `matrix[1][2]` | Dạng truy cập nhiều chỉ số | Phụ thuộc kiểu dữ liệu và bộ truy cập |
| `items[*].name` | Mẫu wildcard khi cấu hình `allowedFields` | **Không phải** property path chỉ đến một phần tử cụ thể để gán |

Điểm cuối đặc biệt quan trọng: `items[*].name` trong `setAllowedFields` là một **mẫu cho phép nhiều tên trường** như `items[0].name`, `items[19].name`; nó không có nghĩa Spring sẽ tự bind một giá trị duy nhất lên tất cả phần tử. Với một giá trị gửi lên, key vẫn phải mang index cụ thể.

Trong khai báo Spring MVC, cũng có thể thấy dữ liệu gốc được đặt trong thuộc tính `items` của JSON, hoặc đối tượng constructor record chứa `List<Item>`. Những cách này có thể tạo cùng kết quả Java nhưng có **cơ chế mapping, quy tắc lỗi và kiểm soát đầu vào khác nhau**. Không đánh đồng mọi kỹ thuật với `DataBinder.bind(PropertyValues)`.

## 11. Index động: thêm, xóa, sắp xếp và danh tính của phần tử

Khi người dùng thêm một dòng mới, frontend có thể tạo tên:

~~~text
items[2].name=Tẩy
items[2].quantity=2
~~~

nếu đã có hai dòng chỉ số 0,1. Khi xóa, frontend thường đánh số lại liên tiếp trước khi gửi. Nếu không đánh số lại, cần có quy tắc server rõ ràng cho những khoảng trống.

**Index chỉ mô tả vị trí trong request**, không phải ID nghiệp vụ. Nếu đơn hàng đã lưu có `orderLineId` riêng, chỉ số `[1]` có thể thay đổi mỗi lần người dùng kéo thả dòng. Server không nên dựa duy nhất vào `[1]` để xác định bản ghi được quyền sửa, xóa hoặc sở hữu.

Đối với cập nhật có định danh:

- Nhận danh sách DTO chỉ chứa các field mà client được phép cung cấp.
- Nếu client cần gửi ID dòng, xác thực mỗi ID thuộc đơn hàng hiện tại và người dùng có quyền tác động.
- Xác định ngữ nghĩa với dòng bị thiếu, dòng được thêm, dòng cần xóa và thứ tự mới.
- Kiểm tra trùng ID, trùng position hoặc số lượng dòng vượt ngưỡng theo yêu cầu nghiệp vụ.
- Lựa chọn cập nhật toàn danh sách hay cập nhật một phần bằng hợp đồng API cụ thể; tránh gán trực tiếp input vào quan hệ JPA mà không đối chiếu bản ghi.

Tương tự, nếu request chỉ có `items[4].name`, binder có thể phải tạo các vị trí 0–4 tùy cấu hình. Hãy validate danh sách kết quả và diễn giải chính sách index, thay vì coi đó là năm dòng được người dùng hoàn thành hợp lệ.

## 12. Bảo mật và giới hạn tài nguyên của indexed binding

Đường dẫn thuộc tính có chỉ số rất hữu ích nhưng cũng cho phép client yêu cầu truy cập sâu vào một cấu trúc dữ liệu. Các rủi ro phải được kiểm soát ngay ở ranh giới input.

### 12.1. Mass assignment qua nested paths

Giả sử một entity có `items[0].priceApproved` hoặc `items[0].ownerId` do server kiểm soát. Nếu dùng entity trực tiếp làm form, client có thể thử gửi:

~~~text
items[0].name=Bút
items[0].ownerId=999
items[0].approved=true
~~~

Dùng request DTO chỉ chứa các trường được phép, thêm `allowedFields` cho property binding:

~~~java
binder.setAllowedFields("items[*].name", "items[*].quantity");
~~~

Các trường bị loại bởi allowlist có thể được truy cập thông qua `BindingResult.getSuppressedFields()`; chúng **không nhất thiết** sinh `FieldError` thông thường. Nếu chính sách cần từ chối request chứa field cấm, phải xử lý việc suppressed field rõ ràng.

### 12.2. Tăng trưởng collection quá lớn

Tên như `items[1000000].name` có thể dẫn đến tiêu tốn bộ nhớ hoặc lỗi property access nếu không có giới hạn. Cấu hình mức auto-grow nhỏ, phù hợp với nghiệp vụ, đồng thời giới hạn request size và validate số dòng. Không suy ra `setAutoGrowCollectionLimit` tự giải quyết mọi trường hợp custom collection hoặc cơ chế constructor binding khác property binding.

### 12.3. Đường dẫn rất sâu hoặc collection đặc biệt

Các nested property path phức tạp `items[0].components[0].parts[0]...` làm tăng chi phí resolve và rủi ro lỗi trên dữ liệu không mong đợi. Thiết kế form DTO nông, có mục tiêu; không cho phép tùy ý đi sâu vào các đối tượng domain nhạy cảm. Với phiên bản Spring đang dùng, cần theo dõi bản vá bảo mật của cơ chế data binding.

### 12.4. Validation và authorization là hai việc khác nhau

`@NotBlank` trên `items[0].name` chỉ nói về chất lượng giá trị, không chứng minh người gọi được sửa một item đã lưu. Service phải kiểm tra quyền trên resource và từng phần tử nếu dữ liệu liên quan quyền sở hữu, giao dịch hoặc tài sản.

## 13. Các lỗi phổ biến và cách khắc phục

**Không có getter/setter phù hợp.** Binder không thể đọc/ghi `items` hoặc `name` theo chế độ JavaBean. Kiểm tra kiểu, accessor và việc có bật direct field access hay không; không giả định private field tự động bind qua property access.

**Danh sách có kiểu phần tử không thể tạo.** Với `List<ItemInterface>` hoặc kiểu trừu tượng, auto-grow có thể không biết khởi tạo phần tử nào. Chọn DTO cụ thể, tự khởi tạo phần tử, hoặc thiết kế cách bind khác thích hợp.

**Nhầm `items[1]` là phần tử đầu tiên.** Index 1 là phần tử thứ hai. Kiểm tra cách sinh thuộc tính `name` trên form.

**Các index bị hổng.** Client gửi `items[0]` và `items[3]`, dẫn đến phần tử trung gian thiếu dữ liệu hoặc lỗi. Đánh số lại hoặc kiểm tra rõ khoảng trống theo hợp đồng.

**Đặt `setAutoGrowCollectionLimit` quá muộn.** Đặt trước binding và trước khi binder tạo hạ tầng kết quả/property access; đừng thay cấu hình lúc đang xử lý một request.

**Mong `getFieldError("quantity")` bắt lỗi ở mọi phần tử.** Lỗi thuộc `items[1].quantity` có tên field đầy đủ. Duyệt `getFieldErrors()`, hoặc truy vấn đúng path; không bỏ mất tên collection và index.

**Cho rằng lỗi sai chỉ số luôn thành FieldError.** Một property path không hợp lệ hoặc index ngoài bounds có thể ném exception. Cần kiểm soát đầu vào và xử lý lỗi HTTP thống nhất.

**Dùng `items[*].name` như tham số request.** Dấu `*` chỉ là ký tự wildcard trong mẫu allowlist; tham số dữ liệu cần index thực như `items[0].name`.

**Không cascade validation.** Nếu chỉ `@Valid` trên controller mà không yêu cầu validate từng `ItemForm`, các ràng buộc trên item có thể không được đánh giá. Đặt `@Valid` ở list/element theo kiểu bean và Bean Validation provider được sử dụng.

**Tin rằng đã bind thành công là đã hợp lệ.** Số lượng `0` có thể chuyển kiểu thành công nhưng vẫn vi phạm `@Min(1)`; kiểm tra cả binding và validation trước khi lưu.

## 14. Bộ kiểm thử nên có

Với `DataBinder` và Spring MVC, có thể kiểm tra các tình huống sau:

| Test | Kết quả mong đợi |
|---|---|
| Form có `items[0].name` và `items[0].quantity` hợp lệ | Tạo phần tử đầu tiên, gán đúng tên và số |
| Có `items[1].name` trong danh sách ban đầu rỗng | Auto-grow khi cấu hình cho phép và kiểu phần tử tạo được |
| `items[1].quantity=abc` | `FieldError` gắn đúng `items[1].quantity`, rejected `abc`, còn field hợp lệ khác được bind |
| `items[0].quantity=0`, có `@Min(1)` | Binding thành công nhưng validation từ chối |
| `items[0].name` rỗng, có `@NotBlank` | Validation xác định đúng field ở index 0 |
| Index vượt giới hạn auto-grow | Bị từ chối/exception phù hợp; không cấp phát số phần tử quá lớn |
| Gửi `items[0].ownerId` trong form bị giới hạn | Field không được gán; có thể ghi trong suppressed fields |
| Gửi index bị hổng `[0]`, `[3]` | Phát hiện các phần tử thiếu dữ liệu theo hợp đồng |
| Gửi nhiều dòng vượt hạn mức | Request bị từ chối theo giới hạn đã công bố |
| Đổi thứ tự dòng đã lưu | Không coi index trong request là ID ổn định của entity |
| Form có lỗi | Không gọi service để lưu hoặc gây side effect |

Đối với `MockMvc`, hãy gửi tham số đúng cú pháp:

~~~java
mockMvc.perform(post("/orders")
        .param("items[0].name", "Bút")
        .param("items[0].quantity", "3")
        .param("items[1].name", "Vở")
        .param("items[1].quantity", "abc"))
    .andExpect(model().attributeHasFieldErrors(
            "order", "items[1].quantity"));
~~~

Đoạn `MockMvc` là **minh họa bên trong một bài test đã cấu hình Spring MVC**, cần các static imports `post`, `model` và setup controller/view tương ứng. Không chạy độc lập chỉ bằng `javac` như chương trình ở mục 4.

## 15. Ghi nhớ

- `items[0].name` là một **indexed property path**: đi đến property `items`, lấy phần tử chỉ số 0, rồi thao tác property `name`.
- Đối với `List` và array, index bắt đầu từ 0; với `Map`, phần trong `[...]` là key và phải được hiểu theo kiểu đích.
- Spring `DataBinder`/ `WebDataBinder` có thể sử dụng các đường dẫn này để bind form/query vào danh sách JavaBean, thực hiện type conversion và tập hợp lỗi theo tên trường đầy đủ.
- Auto-grow giúp biểu mẫu động thuận tiện nhưng cần **giới hạn kích thước, allowlist thuộc tính, DTO chuyên dụng và validation**.
- Lỗi hoặc validation của `items[1].quantity` phải hiển thị ở đúng phần tử. Một lỗi ở một dòng không chứng minh cả danh sách hợp lệ hay vô hiệu mọi giá trị đã bind thành công.
- **Index là vị trí trong payload, không phải danh tính bền vững của dòng dữ liệu**; với thao tác cập nhật, backend phải kiểm tra quyền và định danh thực của từng phần tử.

### Tài liệu chính thức để đọc thêm

- Spring Framework Reference: Data Binding; phần Property Binding with BeanWrapper và Setting and Getting Basic and Nested Properties.
- Spring Framework Reference: Spring MVC Data Binding; phần Allowed Fields và Model Design.
- Spring Framework Javadoc: `DataBinder`, `BeanWrapper`, `BindingResult`, `FieldError`.
- Spring Framework Reference: Validation và Handling Form Submission trong Spring MVC.
