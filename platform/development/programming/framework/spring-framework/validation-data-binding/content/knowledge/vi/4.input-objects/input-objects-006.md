# Đối tượng con, danh sách, mảng và Map trong dữ liệu đầu vào

> Phạm vi: Spring Framework Data Binding (đặc biệt là Spring MVC với `@ModelAttribute`), Java 17+. Bài tập trung vào cách Spring đọc **đường dẫn thuộc tính** để tạo hoặc cập nhật **object graph** từ dữ liệu form/query, xử lý collection, mảng, Map và các giới hạn cần kiểm soát.

## 1. Vì sao dữ liệu đầu vào có thể chứa cấu trúc phức tạp?

Một request HTTP dùng `application/x-www-form-urlencoded` có thể gửi một tập cặp `tên=giá trị`. Tên trường không nhất thiết chỉ là `name` hoặc `email`: Spring có thể hiểu `customer.address.city`, `lines[0].sku`, `tags[1]` và `options[theme]` để bind vào cấu trúc Java bên trong một đối tượng đích.

Ví dụ đơn hàng gồm người nhận, các dòng sản phẩm, thẻ phân loại và một Map tùy chọn:

```text
customer.name=Mai
customer.address.city=Huế
lines[0].sku=PEN
lines[0].quantity=2
lines[1].sku=BOOK
lines[1].quantity=3
tags[0]=gift
tags[1]=office
options[delivery]=express
```

Dữ liệu này có thể tạo ra hình dạng:

```text
OrderInput
├── customer : CustomerInput
│   ├── name = "Mai"
│   └── address : AddressInput
│       └── city = "Huế"
├── lines : List<LineInput>
│   ├── [0] { sku = "PEN", quantity = 2 }
│   └── [1] { sku = "BOOK", quantity = 3 }
├── tags : String[]
│   ├── [0] "gift"
│   └── [1] "office"
└── options : Map<String, String>
    └── ["delivery"] = "express"
```

Từ `"2"` thành `int 2` hay `"true"` thành `Boolean.TRUE` là **chuyển đổi kiểu** (type conversion). Đưa kết quả vào `customer.address.city` hoặc `lines[0].quantity` là **property binding**. Khi target được tạo mới qua constructor, Spring còn hỗ trợ **constructor binding** cho cấu trúc lồng nhau, `List`, mảng và `Map`.

Đây là dữ liệu **từ client, chưa đáng tin cậy**. Tên thuộc tính, chỉ số và khóa Map đều có thể do client tự tạo; không được xem chúng là bằng chứng quyền truy cập hoặc số lượng phần tử hợp lệ.

## 2. Quy tắc đặt tên đường dẫn thuộc tính

Spring Core dùng cơ chế truy cập JavaBeans (thường thông qua `BeanWrapper`) để hiểu những biểu thức như sau:

| Tên trường trong request | Đích Java | Ý nghĩa |
| --- | --- | --- |
| `name` | `form.getName()` | Thuộc tính trực tiếp |
| `customer.name` | `form.getCustomer().getName()` | Thuộc tính của đối tượng con |
| `customer.address.city` | `form.getCustomer().getAddress().getCity()` | Lồng nhiều tầng |
| `lines[0]` | `form.getLines().get(0)` | Phần tử đầu tiên của danh sách |
| `lines[1].quantity` | `form.getLines().get(1).getQuantity()` | Thuộc tính của phần tử danh sách |
| `tags[1]` | `form.getTags()[1]` | Phần tử thứ hai của mảng |
| `options[delivery]` | `form.getOptions().get("delivery")` | Giá trị Map theo khóa |
| `details[sku-1].caption` | `form.getDetails().get("sku-1").getCaption()` | Object nằm trong Map |
| `options['theme.dark']` | `form.getOptions().get("theme.dark")` | Cú pháp đặt khóa có dấu chấm trong ngoặc kép đơn |

Cú pháp `.` diễn tả đi xuống một object; `[index]` đánh chỉ số (thường bắt đầu từ `0`); `[key]` chọn một khóa Map. Cú pháp dấu ngoặc nháy giúp biểu thị khóa chứa ký tự có thể gây nhầm với cấu trúc đường dẫn. Trong URL/form thực tế, các dấu `[`, `]`, dấu nháy và ký tự Unicode phải được mã hóa theo quy tắc HTTP; nên dùng thư viện HTTP/form thay vì tự nối chuỗi URL.

**Không thêm tiền tố tên model attribute theo thói quen.** Với `@ModelAttribute("orderInput") OrderInput form`, các field thông thường là `customer.name` và `lines[0].sku`, không phải `orderInput.customer.name`. Tên `orderInput` là tên của đối tượng đích trong Model/BindingResult, không tự động thành một property của chính object đó.

Cách đặt tên có thể khác với **JSON**: `@RequestBody` nhận JSON rồi deserialize qua `HttpMessageConverter`. Dữ liệu JSON dùng object/array thực sự thay vì những chuỗi tên form kiểu `lines[0].sku`.

## 3. Đối tượng con (nested object)

### 3.1. Property binding đi qua nhiều tầng

Cho mô hình `OrderInput.customer.address.city`. Để bind `customer.address.city=Huế`, Spring cần đi qua `customer` rồi `address` và cuối cùng ghi thuộc tính `city`.

```java
public class AddressInput {
    private String city;

    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }
}

public class CustomerInput {
    private AddressInput address;

    public AddressInput getAddress() { return address; }
    public void setAddress(AddressInput address) { this.address = address; }
}

public class OrderInput {
    private CustomerInput customer;

    public CustomerInput getCustomer() { return customer; }
    public void setCustomer(CustomerInput customer) { this.customer = customer; }
}
```

Đây là các class minh họa; khi lưu riêng từng class public cần file cùng tên và tuân thủ quy tắc Java. Với JavaBeans mutable, mặc định `DataBinder` bật `autoGrowNestedPaths`: nếu `customer` hoặc `address` là `null`, binder **có thể** tạo đối tượng tương ứng bằng cách khởi tạo phù hợp, rồi tiếp tục gán `city`. Điều này đòi hỏi kiểu con có thể khởi tạo và đường dẫn property có thể truy cập/ghi.

Có thể chủ động khởi tạo object trong constructor để có ý định rõ ràng:

```java
private CustomerInput customer = new CustomerInput();
```

Việc tự tạo object lồng nhau **không phải lời hứa** rằng Spring luôn có thể khởi tạo interface, lớp abstract, class không có constructor thích hợp hoặc object bất biến qua setter. Khi đường dẫn không thể truy cập, cần xem loại lỗi cụ thể và thiết kế DTO.

### 3.2. Không nhầm auto-grow với constructor binding

- **Property binding:** dùng getter/setter hoặc chế độ truy cập field đã cấu hình, có thể tự tạo phần tử con `null` trong quá trình duyệt property path.
- **Constructor binding:** từ Spring Framework 6.1+, tạo object mới bằng cách lấy tên tham số constructor, chuyển đổi giá trị và **tạo object con đệ quy**. Với record lồng nhau, không cần setter cho mỗi trường. Phạm vi có thể bao gồm cả `List`, mảng và `Map`.

Ví dụ thiết kế record cho dữ liệu lồng nhau (mã khai báo kiểu, chưa phải một chương trình độc lập):

```java
public record AddressInput(String city) {}
public record CustomerInput(String name, AddressInput address) {}
public record OrderInput(CustomerInput customer) {}
```

Các key `customer.name` và `customer.address.city` cho phép Spring dựng `CustomerInput` và `AddressInput` thông qua data constructor phù hợp trong luồng `@ModelAttribute`. Với class Java thường, hãy bảo đảm tên tham số constructor có sẵn ở runtime (ví dụ biên dịch với `-parameters`); record ghi nhận tên thành phần một cách tự nhiên.

## 4. `List<T>`: chỉ số phần tử và đối tượng bên trong danh sách

Một `List<LineInput>` thể hiện tập phần tử có thứ tự và có chỉ số:

```java
public class LineInput {
    private String sku;
    private int quantity;

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public int getQuantity() { return quantity; }
    public void setQuantity(int quantity) { this.quantity = quantity; }
}

public class OrderInput {
    private List<LineInput> lines = new ArrayList<>();

    public List<LineInput> getLines() { return lines; }
    public void setLines(List<LineInput> lines) { this.lines = lines; }
}
```

Cần `import java.util.List;` và `import java.util.ArrayList;` nếu tách các class trên thành file Java. Từ form:

```text
lines[0].sku=PEN
lines[0].quantity=2
lines[1].sku=BOOK
lines[1].quantity=3
```

Khi bind thành công, `lines.size() == 2`; `lines.get(0).getSku()` là `"PEN"`, `lines.get(1).getQuantity()` là `3`.

Các điểm cần nắm:

1. Chỉ số **bắt đầu từ 0**. `lines[1]` là dòng thứ hai, không phải dòng có ID nghiệp vụ bằng `1`.
2. `lines[0].quantity` cần kiểu phần tử đủ rõ (thường `List<LineInput>`); nếu khai báo raw `List`, Spring thiếu thông tin generic để suy ra kiểu element khi khởi tạo/chuyển đổi.
3. Với property binding và `autoGrowNestedPaths=true`, Spring có thể mở rộng List và tạo phần tử để xử lý chỉ số mới. Việc khởi tạo item mới vẫn phụ thuộc kiểu item và khả năng tạo object.
4. Index thưa như `lines[5].sku` có thể khiến List tăng tới vị trí thứ sáu, với những vị trí trung gian chưa có dữ liệu nghiệp vụ đầy đủ. Cần validate số dòng, tính liên tục của index và phần tử rỗng nếu nghiệp vụ yêu cầu.
5. `Set` không có quy ước vị trí ổn định như `List`. Đừng dựa vào `set[0]` để ánh xạ form theo thứ tự; dùng `List` cho input có thứ tự hoặc dạng khóa định danh trong Map.
6. Khi người dùng thêm/xóa/reorder dòng trên UI, phải đồng bộ lại field names. Nếu gửi lại các index cũ không liên tục, object graph và lỗi có thể không khớp vị trí nhìn thấy trên màn hình.
7. Không cho client biến `lines[0].id` hoặc `lines[0].price` thành lệnh cập nhật bản ghi thực. ID, giá và quyền chỉnh sửa phải được xác minh ở phía server.

Đối với danh sách scalar như `List<Integer> quantities`, `quantities[0]=4` và `quantities[1]=8` được conversion sang số nguyên. Việc gửi chuỗi tách bởi dấu phẩy như `quantities=4,8` có thể được hỗ trợ khi converter phù hợp; không nên giả định mọi kiểu collection/object phức tạp đều hỗ trợ một chuỗi CSV.

## 5. Mảng: `String[]`, `int[]` và giới hạn tăng kích thước

Mảng là cấu trúc có thứ tự, độ dài cố định đối với **một instance array**. Property binding có thể tạo mảng mới lớn hơn khi cần giải quyết chỉ số, rồi cập nhật thuộc tính mảng của bean nếu đường dẫn cho phép. Ví dụ:

```java
public class TagForm {
    private String[] tags = new String[0];

    public String[] getTags() { return tags; }
    public void setTags(String[] tags) { this.tags = tags; }
}
```

Với `tags[0]=gift` và `tags[1]=office`, ta kỳ vọng `Arrays.toString(form.getTags())` trả `"[gift, office]"` nếu binder cho phép cả hai field và không có lỗi.

Một số khác biệt so với `List`:

| Tính chất | `List<T>` | `T[]` |
| --- | --- | --- |
| Kiểu container | Interface/implementation như `ArrayList` | Array của JVM |
| Thêm phần tử thủ công | `add`/`set` theo API List | Phải tạo array khác nếu đổi độ dài |
| Tên input | `lines[0].sku` | `tags[0]` |
| Generic/kiểu phần tử | Nên khai báo `List<LineInput>` | Phần tử nằm trong kiểu `String[]` hoặc `int[]` |
| Auto-grow khi property binding | Có thể nới List trong giới hạn | Có thể tạo array lớn hơn rồi gán lại property trong giới hạn |

Các dạng `tags[0]`, `tags[1]` khác với việc lặp nhiều input cùng tên `tags` hoặc truyền `tags=gift,office`. Kết quả của các dạng sau phụ thuộc conversion, loại collection và cấu hình binding; hãy kiểm thử đúng form payload mình sử dụng.

`int[]` nhận giá trị kiểu số, ví dụ `scores[0]=10`. Nếu gửi `scores[0]=abc`, binder cần báo lỗi chuyển kiểu thay vì âm thầm xem `abc` là số hợp lệ.

## 6. Map: khóa không phải chỉ số vị trí

`Map<K,V>` ánh xạ một **khóa** đến một **giá trị**. Các trường:

```text
options[delivery]=express
options[language]=vi
limits[booking]=5
flags[featured]=true
```

có thể gắn vào các property như:

```java
private Map<String, String> options = new LinkedHashMap<>();
private Map<String, Integer> limits = new HashMap<>();
private Map<String, Boolean> flags = new HashMap<>();
```

Nhờ generic, binder có thông tin để chuyển `"5"` thành `Integer` và `"true"` thành `Boolean`. Nếu bản thân **khóa** có kiểu khác `String` (ví dụ `Map<Long, String>`), quá trình conversion còn phải chuyển key; cần converter/editor thích hợp.

### 6.1. Map có giá trị là đối tượng con

Với `Map<String, DetailInput> details` và class `DetailInput` có setter `caption`, `details[SKU-A].caption=Ghi chú` có thể bind vào `details.get("SKU-A").getCaption()`. Nếu entry chưa tồn tại, khả năng tự tạo phụ thuộc kiểu phần tử, cách khởi tạo Map, cấu hình binder và cơ chế binding đang dùng. Nên khởi tạo Map, khai báo generic rõ ràng và xác minh bằng test. Không dựa vào khả năng auto-grow List để suy luận rằng Map bị giới hạn giống List.

**Khóa trong Map và index trong List khác nhau:** `details[7]` với `Map<String, DetailInput>` thường dùng khóa `"7"`, còn `lines[7]` là vị trí thứ tám. Không coi `details[7]` là vị trí thứ tám của Map.

### 6.2. Khóa chứa ký tự đặc biệt

Với khóa có dấu chấm như `theme.dark`, dùng cú pháp khóa được bao bằng dấu nháy trong ngoặc: `options['theme.dark']`. Với tên key chứa dấu nháy hoặc ngoặc, phải chọn cú pháp và mã hóa chuỗi đầu vào phù hợp với phiên bản/framework; kiểm thử case thật, không ghép thủ công chuỗi path không tin cậy.

`Map` không nhất thiết duy trì thứ tự. Nếu giao diện cần hiển thị thứ tự chèn, chọn `LinkedHashMap` ở tầng dữ liệu; nếu nghiệp vụ cần **danh sách dòng có vị trí**, dùng `List`. Không dựa vào thứ tự duyệt `HashMap` để xác định bản ghi “đầu tiên”.

### 6.3. Map và dữ liệu khóa động

Các input như `metadata[role]=ADMIN` hoặc `prices[item-1]=0` cho thấy client có thể tự tạo **key bất kỳ**. Ngay cả khi tên property `metadata` được cho phép, giới hạn collection không tự giải quyết số lượng key, độ dài key, kiểu nội dung hoặc quyền thay đổi các key nhạy cảm. Cần whitelist key theo nghiệp vụ hoặc validate từng entry, giới hạn số lượng/phần tử từ tầng request/application, và loại bỏ dữ liệu không được phép trước khi xử lý.

## 7. Ví dụ Java 17 chạy độc lập với `DataBinder`

Ví dụ dưới đây dùng **Spring Core DataBinder**, không cần khởi động web server. Nó chứng minh cùng lúc object con, List, mảng, Map, chuyển đổi kiểu, giới hạn trường được phép và field bị từ chối. Vì đây là một chương trình Java hoàn chỉnh, mọi class phụ nằm trong một file.

Tạo cấu trúc:

```text
nested-binding-demo/
├── pom.xml
└── src/main/java/example/NestedBindingDemo.java
```

Nội dung `pom.xml` (ví dụ với Spring Framework 6.2.10, Java 17):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>nested-binding-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.10</version>
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
        <version>3.5.1</version>
        <configuration>
          <mainClass>example.NestedBindingDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

Nội dung `src/main/java/example/NestedBindingDemo.java`:

```java
package example;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

public class NestedBindingDemo {

    public static class Address {
        private String city;

        public Address() {}

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
    }

    public static class Line {
        private String sku;
        private int quantity;

        public Line() {}

        public String getSku() { return sku; }
        public void setSku(String sku) { this.sku = sku; }

        public int getQuantity() { return quantity; }
        public void setQuantity(int quantity) { this.quantity = quantity; }
    }

    public static class Form {
        private Address address;
        private List<Line> lines = new ArrayList<>();
        private String[] tags = new String[0];
        private Map<String, Integer> stock = new LinkedHashMap<>();

        public Form() {}

        public Address getAddress() { return address; }
        public void setAddress(Address address) { this.address = address; }

        public List<Line> getLines() { return lines; }
        public void setLines(List<Line> lines) { this.lines = lines; }

        public String[] getTags() { return tags; }
        public void setTags(String[] tags) { this.tags = tags; }

        public Map<String, Integer> getStock() { return stock; }
        public void setStock(Map<String, Integer> stock) { this.stock = stock; }
    }

    public static void main(String[] args) {
        Form form = new Form();
        DataBinder binder = new DataBinder(form, "form");

        // Giới hạn tăng List/array trong property binding.
        binder.setAutoGrowCollectionLimit(8);

        // Chỉ cho bind đúng các đường dẫn dự kiến.
        binder.setAllowedFields(
            "address.city",
            "lines[*].sku",
            "lines[*].quantity",
            "tags[*]",
            "stock[pen]"
        );

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("address.city", "Ha Noi");
        values.add("lines[0].sku", "PEN");
        values.add("lines[0].quantity", "2");
        values.add("lines[1].sku", "NOTE");
        values.add("lines[1].quantity", "4");
        values.add("tags[0]", "gift");
        values.add("tags[1]", "office");
        values.add("stock[pen]", "12");
        values.add("role", "ADMIN"); // Không nằm trong allowedFields.

        binder.bind(values);

        System.out.println(form.getAddress().getCity());
        System.out.println(form.getLines().size());
        System.out.println(
            form.getLines().get(1).getSku() + ":"
            + form.getLines().get(1).getQuantity()
        );
        System.out.println(Arrays.toString(form.getTags()));
        System.out.println(form.getStock().get("pen"));
        System.out.println(binder.getBindingResult().hasErrors());
        System.out.println(
            Arrays.toString(binder.getBindingResult().getSuppressedFields())
        );
    }
}
```

Chạy ở thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

Kết quả chuẩn mong đợi của chương trình, không tính log tải thư viện nếu môi trường Maven in thêm:

```text
Ha Noi
2
NOTE:4
[gift, office]
12
false
[role]
```

Giải thích lần lượt:

- `address` ban đầu `null` nhưng được khởi tạo để nhận `city`.
- List ban đầu rỗng; `lines[0]` và `lines[1]` được tạo/ghi dữ liệu, `"4"` chuyển thành `int 4`.
- Mảng `tags` ban đầu dài 0 và được nới để nhận hai phần tử.
- `stock[pen]` được chuyển từ `String` sang `Integer` theo kiểu Map đã khai báo.
- `hasErrors()` trả `false` vì các trường **được bind** có kiểu hợp lệ.
- `role` bị loại bởi allowlist; `getSuppressedFields()` cho biết field bị chặn. Field bị suppress không đồng nghĩa với lỗi chuyển đổi, và không nên dựa vào `hasErrors()` để kết luận request hoàn toàn không có trường ngoài danh sách.

Lưu ý: ví dụ dùng instance `Form` tạo sẵn rồi gọi `bind(PropertyValues)`, nên minh họa **property binding**. Nó không tự kiểm chứng đường constructor binding cho record; đó là một đường riêng của API `DataBinder`.

## 8. Kết nối vào controller Spring MVC

Giả sử ứng dụng nhận form HTML với các `name` giống phần 2. Một handler có thể khai báo:

```java
@PostMapping("/orders")
public String createOrder(
        @Valid @ModelAttribute("orderInput") OrderInput input,
        BindingResult result) {
    if (result.hasErrors()) {
        return "orders/new";
    }
    orderService.createOrder(input);
    return "redirect:/orders";
}
```

Đoạn này là **mã tích hợp**, cần `@Controller`, dependency web/validation, DTO `OrderInput`, service và view tương ứng. Phải đặt `BindingResult` **ngay sau** model attribute của nó. `@Valid` kích hoạt validation khi có provider/cấu hình phù hợp; nó không tự đưa ra giới hạn số dòng, whitelist Map key hay xác thực nghiệp vụ nếu không khai báo các constraint đó.

Cấu hình một binder theo tên Model attribute:

```java
@InitBinder("orderInput")
void configureOrderBinder(WebDataBinder binder) {
    binder.setAutoGrowCollectionLimit(20);
    binder.setAllowedFields(
        "customer.name",
        "customer.address.city",
        "lines[*].sku",
        "lines[*].quantity",
        "tags[*]",
        "options[delivery]"
    );
}
```

Đây là cấu hình **mang tính ví dụ**: cần điều chỉnh các field và giới hạn theo nghiệp vụ. Spring hỗ trợ wildcard `*` trong pattern của `allowedFields`, kể cả đường dẫn nested/indexed. `lines[*].sku` cho phép tên `lines[0].sku`, `lines[7].sku` v.v.; nó không chứng thực số dòng hay cho phép sửa mọi field của Line. `options[delivery]` chỉ chấp nhận key `delivery`, an toàn hơn việc cho mọi key kiểu `options*` khi danh sách key cần hữu hạn.

Tạo form HTML động:

```html
<form action="/orders" method="post">
  <input name="customer.name" value="Mai">
  <input name="customer.address.city" value="Hue">

  <input name="lines[0].sku" value="PEN">
  <input name="lines[0].quantity" value="2">

  <input name="lines[1].sku" value="BOOK">
  <input name="lines[1].quantity" value="3">

  <input name="tags[0]" value="gift">
  <input name="options[delivery]" value="express">
  <button type="submit">Tạo đơn</button>
</form>
```

Đây là ví dụ về **tên field**, không bao gồm cấu hình CSRF, trang web, giao diện thêm/xóa dòng hay xác thực người dùng. Trong ứng dụng thực tế, giữ cơ chế CSRF/authorization và validate phía server. Không dùng `disabled` của HTML hoặc JavaScript để làm ranh giới bảo mật; client hoàn toàn có thể gửi tên trường tự ý.

## 9. Constructor binding với nested object và container

Khi thiết kế immutable DTO/record, constructor binding thay vì gọi setter lấy tham số constructor theo tên và tạo graph. Spring Framework hỗ trợ các tham số constructor kiểu object con, `List`, mảng và `Map`; các giá trị có thể đến từ key có index như `lines[0].sku` hoặc `options[delivery]`. Với một số kiểu scalar, chuỗi phân tách bằng dấu phẩy có thể được chuyển thành list/array nếu có converter phù hợp.

Ví dụ kiểu dữ liệu (không phải chương trình độc lập):

```java
public record AddressInput(String city) {}

public record LineInput(String sku, int quantity) {}

public record OrderInput(
    AddressInput address,
    List<LineInput> lines,
    String[] tags,
    Map<String, String> options
) {}
```

Với parameter `@ModelAttribute("orderInput") OrderInput input`, request có thể gồm:

```text
address.city=Hue
lines[0].sku=PEN
lines[0].quantity=2
lines[1].sku=BOOK
lines[1].quantity=3
tags[0]=gift
options[delivery]=express
```

Điểm khác: Spring tạo `OrderInput` qua constructor, đồng thời có thể khởi tạo `AddressInput` và `LineInput` lồng nhau. Các record không có setter để property binding tùy ý cập nhật sau khi tạo. Không cần giả lập `autoGrowNestedPaths` bằng setters trong trường hợp này.

Từ Spring 6.1+, có thể cấu hình `binder.setDeclarativeBinding(true)` để constructor binding vẫn hoạt động, còn property binding chỉ chạy khi có `allowedFields`. Cách này hữu ích với mô hình có cả constructor và setter; tuy nhiên **không có nghĩa mọi cấu trúc nested do client gửi lên đều an toàn**. Tất cả constructor argument được dự kiến trong DTO cũng cần được kiểm tra độ dài, số lượng phần tử, key Map, quyền thao tác và ràng buộc nghiệp vụ.

Chú ý giới hạn `setAutoGrowCollectionLimit` thường áp dụng cho **array/list tự tăng trong property binding**, không nên xem đây là một giới hạn chung cho Map hoặc constructor binding. Nếu dùng constructor binding với collection lớn, hãy đặt giới hạn ở tầng request, DTO/validation và ứng dụng tương ứng.

## 10. Validation và lỗi trong cấu trúc lồng nhau

### 10.1. Validation của element cần cascade

Với Jakarta Bean Validation, ví dụ:

```java
public class OrderInput {
    @Valid
    @NotNull
    private CustomerInput customer;

    @NotEmpty
    @Size(max = 20)
    private List<@Valid LineInput> lines;

    @Size(max = 10)
    private String[] tags;

    @Size(max = 5)
    private Map<String, String> options;

    // Getters/setters và khởi tạo được khai báo theo thiết kế DTO.
}

public class LineInput {
    @NotBlank
    private String sku;

    @Positive
    private int quantity;

    // Getters/setters tương ứng.
}
```

Đây là **đoạn minh họa constraint**, không phải file hoàn chỉnh; cần import `jakarta.validation.Valid`, `jakarta.validation.constraints.*`, provider Bean Validation và các class liên quan. `@Valid` trên object con hoặc kiểu phần tử của List yêu cầu **cascade** vào element; chỉ đặt `@Valid` trên root parameter chưa đủ nếu DTO không khai báo các quan hệ cascade phù hợp. `@Size(max=20)` giới hạn kích thước collection đã bind, nhưng không thay cho kiểm soát payload/index trước khi quá trình bind có thể cấp phát.

### 10.2. FieldError mang đường dẫn đầy đủ

Ví dụ client gửi:

```text
customer.address.city=Hue
lines[0].sku=PEN
lines[0].quantity=abc
```

Spring không chuyển được `"abc"` thành `int`. Khi cơ chế binding ghi nhận lỗi, `BindingResult` có thể chứa field path `lines[0].quantity` với lỗi kiểu `typeMismatch`; các lỗi validator cũng có thể mang path như `customer.address.city` hoặc `lines[1].sku`.

```java
for (FieldError error : result.getFieldErrors()) {
    System.out.println(error.getField() + ": " + error.getCode());
}
```

Đây là **đoạn code thuộc handler**, giả định có biến `BindingResult result` và import `org.springframework.validation.FieldError`. Không khẳng định số lượng/thứ tự lỗi hay nội dung text cụ thể của message, vì phụ thuộc binding/validation và cấu hình message resolver. Với nested collection, trả error path chính xác giúp UI gắn lỗi đúng dòng và đúng field.

Lỗi có thể phát sinh trước khi object graph được tạo hoàn chỉnh, hoặc khi truy cập một đường dẫn không hợp lệ. `BindingResult` chứa các lỗi có thể thu thập được; trường hợp lỗi khởi tạo hay cấu hình nghiêm trọng vẫn có thể phát sinh exception. Không nên mặc định mọi lỗi nested đều biến thành một object hợp lệ với `hasErrors=true`.

### 10.3. Phân biệt lỗi bind và lỗi nghiệp vụ

| Tình huống | Tầng cần xử lý |
| --- | --- |
| `lines[0].quantity=abc` không chuyển sang `int` | Binding/type conversion, trả lỗi field |
| `lines[0].quantity=-3` chuyển kiểu thành công nhưng không hợp lệ | Bean Validation với `@Positive` hoặc validator riêng |
| `lines` có 10.000 phần tử/index rất lớn | Giới hạn request/binder và kiểm tra kích thước |
| `options[admin]=true` là key không được phép | Allowlist + kiểm tra key |
| `lines[0].productId` thuộc sản phẩm người dùng không được quyền đặt | Authorization/logic nghiệp vụ phía server |
| `lines[0].price=0` cố thay giá bán | Không bind giá từ client; lấy giá chuẩn từ dữ liệu phía server |

## 11. Giới hạn và an toàn dữ liệu đầu vào

Một khi bean có nested path, List hay Map, client có thể cố gửi các field không xuất hiện trên giao diện:

```text
lines[999999].sku=PEN
customer.role=ADMIN
options[internalMode]=enabled
customer.address.otherSensitiveField=value
```

Các biện pháp cần phối hợp:

1. **Dùng input DTO chuyên biệt.** Không bind trực tiếp vào entity domain có các field như `role`, `price`, `approved`, `ownerId`, `balance`.
2. **Giới hạn property binding.** `setAllowedFields(...)` phải liệt kê path an toàn; wildcard nên hẹp và có mục đích. Với `setDeclarativeBinding(true)`, property binding chỉ diễn ra khi khai báo `allowedFields`.
3. **Giới hạn tăng List/array.** `WebDataBinder.setAutoGrowCollectionLimit(n)` ảnh hưởng auto-grow ở setter/property binding; mặc định của `DataBinder` là 256. Giảm khi biểu mẫu chỉ có ít phần tử. Nó **không** phải quota tổng request, không phải giới hạn kích thước Map và không khống chế constructor binding.
4. **Giới hạn độ sâu và độ phức tạp của payload.** Không cho phép client tạo object graph vô hạn bằng nested path. Tùy phiên bản Spring có thêm cấu hình depth; thiết kế DTO nông, hạn chế field path được phép và giới hạn request ở gateway/server vẫn quan trọng.
5. **Giới hạn key Map.** Chỉ cho phép tập key được hỗ trợ; kiểm tra số key, độ dài key/value, định dạng và semantics. Không tin rằng `Map<String, String>` tự loại bỏ các key bất thường.
6. **Validate graph sau bind.** `@NotNull`, `@Size`, `@Valid`, constraint từng element và validator nghiệp vụ. Phân biệt validation với conversion; không gọi service khi binding đã lỗi.
7. **Không tin client index/ID.** Index chỉ dùng để tổ chức vị trí input. Định danh bản ghi persisted phải được tra cứu lại, xác nhận ownership và quyền trên server.
8. **Tránh xử lý dữ liệu suppressed như hợp lệ.** `getSuppressedFields()` cho biết field bị từ chối bởi allowlist; quyết định từ chối toàn bộ request hoặc log/quan sát bất thường theo chính sách ứng dụng.
9. **Kiểm thử payload bất thường.** Test index âm/lớn, sparse index, trùng key, key Map lạ, nested null, element sai kiểu, thiếu phần tử và request quá lớn.

Với Map giá trị object hoặc List được triển khai bằng class tùy biến, còn có nguy cơ xử lý cấp phát bất ngờ khi truy cập index/key. Ưu tiên các kiểu collection chuẩn, áp dụng bản vá bảo mật của phiên bản Spring đang dùng và thực thi hạn chế request phù hợp.

## 12. Checklist và bài tập tự kiểm tra

### Kiểm tra nhanh khi triển khai

- Model có getters/setters phù hợp (property binding) hoặc data constructor phù hợp (constructor binding) không?
- Field names dùng cú pháp `address.city`, `lines[0].sku`, `tags[1]` và `options[key]` chính xác với cấu trúc DTO không?
- Kiểu element của List/Map có được khai báo generic đủ rõ để conversion không?
- Nested object hoặc phần tử còn `null` có thể được tạo khi cần không? Có constructor/accessor khả dụng không?
- Có phân biệt Map key và List index khi xử lý ID nghiệp vụ không?
- Có giới hạn List/array growth, số lượng Map key, độ dài payload và độ sâu object graph không?
- Allowlist có chặn được field nhạy cảm ở bất kỳ tầng nào không?
- Nested `@Valid` và constraint trên collection/element đã được cấu hình chưa?
- Khi lỗi chuyển kiểu tại `lines[1].quantity`, UI có hiển thị đúng vị trí và dừng xử lý nghiệp vụ không?

### Bài tập 1 — Đọc object graph

Cho `CatalogForm` có `List<ProductInput> products`, `Map<String, String> settings` và `CustomerInput customer`. Input:

```text
products[0].sku=ABC
products[1].sku=XYZ
settings[locale]=vi
customer.address.city=Da Nang
```

Hãy mô tả ba đường dẫn và giá trị tương ứng. **Đáp án:** `products.get(0).getSku() = "ABC"`, `products.get(1).getSku() = "XYZ"`; `settings.get("locale") = "vi"`; `customer.getAddress().getCity() = "Da Nang"` (giả định binding thành công và cấu trúc DTO có thể khởi tạo).

### Bài tập 2 — Tìm lỗi thiết kế

Một endpoint để sửa giỏ hàng bind trực tiếp `CartEntity` có `List<CartLine> lines`; `CartLine` chứa `productId`, `quantity`, `unitPrice` và `sellerId`. Form chỉ hiển thị quantity, nhưng endpoint không cấu hình allowlist. **Vấn đề:** client có thể cố bind thêm `lines[0].unitPrice`/`sellerId`. **Hướng sửa:** nhận DTO input chỉ chứa product reference và quantity cần thiết, giới hạn field paths, kiểm tra quyền sở hữu/giá bên service, validate số dòng và quantity.

### Bài tập 3 — Lỗi do chỉ số

Form có ba dòng sản phẩm, gửi `lines[0]` và `lines[2]` nhưng không gửi `lines[1]`. Hỏi: có thể mặc định danh sách đúng hai phần tử không? **Không.** Trong property binding có auto-grow, đường dẫn index 2 có thể khiến container đủ ba vị trí, gồm vị trí trung gian chưa được điền nghiệp vụ đầy đủ. Cần quy định index liên tục/normalization ở UI và validate dữ liệu sau bind; không dựa vào việc đếm số key request làm số item đã nhận.

## Tài liệu chính thức để tra cứu

- [Spring Framework — Core Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): nested property paths, `BeanWrapper`, constructor và property binding.
- [Spring MVC — Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html): thiết kế DTO, `allowedFields`, `declarativeBinding` và an toàn.
- [Spring MVC — `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): các nguồn input, constructor binding, `BindingResult` và validation.
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): Bean Validation, lỗi và cơ chế method validation.
- [Spring Framework Javadoc — `DataBinder`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html): `autoGrowNestedPaths`, `autoGrowCollectionLimit`, `setAllowedFields` và `getBindingResult`.
