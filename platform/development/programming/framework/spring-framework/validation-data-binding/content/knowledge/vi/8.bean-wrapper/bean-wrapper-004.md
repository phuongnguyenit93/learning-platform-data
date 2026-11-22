# BeanWrapper: getPropertyValue và setPropertyValue

`BeanWrapper` là API của Spring Framework để **đọc và ghi property của một đối tượng Java theo tên hoặc đường dẫn dạng chuỗi**. Hai phương thức thường dùng nhất là:

```java
Object value = wrapper.getPropertyValue("propertyName");
wrapper.setPropertyValue("propertyName", newValue);
```

Trong bài này, “property” là đặc tính được JavaBeans introspection nhận diện, thường qua cặp `getX()/setX(...)` hoặc `isX()` cho boolean. Nó không nhất thiết trùng một field truy cập trực tiếp. `getPropertyValue` dùng để lấy giá trị hiện tại; `setPropertyValue` đi qua cơ chế property access, hỗ trợ đường dẫn lồng nhau, danh sách/Map và chuyển đổi kiểu trong phạm vi được cấu hình.

Mục tiêu là sử dụng đúng hai API này, hiểu **chúng tìm getter/setter và di chuyển trên object graph thế nào**, phân biệt lỗi khi đọc/ghi, đồng thời biết khi nào dùng `BeanWrapper` trực tiếp và khi nào giao cho `DataBinder` của Spring.

## 1. Bối cảnh: property, target và wrapper

Giả sử có JavaBean:

```java
public class Customer {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Đoạn trên là một định nghĩa class, chưa có `main`. Với JavaBeans convention, property `name` thường có:

- **getter** `getName()` để đọc;
- **setter** `setName(String)` để ghi;
- **kiểu property** `String`;
- một instance `Customer` làm **target** của thao tác.

Không cần viết sẵn `customer.getName()` trong mã gọi; khi property name được xác định ở runtime (ví dụ từ cấu hình, mapping hoặc metadata), có thể dùng:

```java
Customer customer = new Customer();
BeanWrapper wrapper = PropertyAccessorFactory.forBeanPropertyAccess(customer);

wrapper.setPropertyValue("name", "An");
Object value = wrapper.getPropertyValue("name");
```

Đây là đoạn sử dụng API, cần import `org.springframework.beans.BeanWrapper` và `org.springframework.beans.PropertyAccessorFactory`.

```text
target: Customer instance
             |
             v
BeanWrapper(target)
     |                     |
     | getPropertyValue    | setPropertyValue
     v                     v
 tìm getter             tìm setter
     |                     |
     v                     v
 lấy giá trị            chuyển kiểu khi cần
                           |
                           v
                       gán vào target
```

**Điểm quan trọng:** wrapper quản lý cách truy cập tới **cùng instance** đã đưa vào. Với `setPropertyValue`, giá trị trong target có thể thay đổi ngay lập tức. Wrapper không tự tạo bản sao target, không mặc định lưu snapshot, không có cơ chế transaction và không tự thực hiện validation nghiệp vụ.

## 2. Tạo BeanWrapper đúng cách

Spring cung cấp interface `BeanWrapper` và implementation phổ biến `BeanWrapperImpl`. Hai cách tạo thông dụng:

```java
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.PropertyAccessorFactory;

Customer customer = new Customer();

// Cách 1: lấy qua factory, giữ phần code gọi phụ thuộc interface.
BeanWrapper viaFactory =
        PropertyAccessorFactory.forBeanPropertyAccess(customer);

// Cách 2: tạo implementation trực tiếp nếu cần cấu hình cụ thể.
BeanWrapperImpl viaConstructor = new BeanWrapperImpl(customer);
```

Đoạn trên cần class `Customer` từ phần 1. Cả hai wrapper đều hướng đến JavaBean property access. Khi không có yêu cầu riêng, `PropertyAccessorFactory.forBeanPropertyAccess(target)` diễn đạt ý định rõ ràng; khi cần cấu hình tùy biến có thể dùng `BeanWrapperImpl`.

Để so sánh, Spring còn cung cấp `PropertyAccessorFactory.forDirectFieldAccess(target)` với đường truy cập trực tiếp field. **Direct field access và BeanWrapper property access không đồng nghĩa**. Đối với JavaBean thông thường, đọc/ghi qua getter/setter có thể kích hoạt logic có trong các method đó; truy cập trực tiếp field có đặc điểm khác và không tuân cùng contract getter/setter.

| Cách truy cập | Đi qua getter/setter? | Phù hợp khi |
| --- | --- | --- |
| `BeanWrapper` / `BeanWrapperImpl` | Theo JavaBeans property descriptor | Object có API property công khai, form/bean mutable |
| `DirectFieldAccessor` (từ factory) | Dùng field access | Kiểu object hoặc trường hợp có yêu cầu đọc/ghi field trực tiếp |
| Gọi `customer.getName()/setName(...)` | Có, được kiểm tra kiểu tại compile time | Biết property ngay trong source code |
| Reflection tự viết | Phụ thuộc cách triển khai | Cần cơ chế đặc thù hơn và sẵn sàng tự xử lý metadata/lỗi |

Không nên thay mọi lời gọi getter/setter bằng chuỗi property name. Khi đã biết tên property tại compile time, gọi method trực tiếp đơn giản, dễ refactor và có lợi thế kiểm tra kiểu.

## 3. getPropertyValue(String): đọc giá trị bằng tên property

Cú pháp:

```java
Object value = wrapper.getPropertyValue("name");
```

`getPropertyValue` nhận **tên/đường dẫn property**, trả về `Object`. Khi property là `int`, giá trị được trả có thể là một `Integer` đã boxing. Caller cần cast đúng kiểu hoặc dùng các thông tin type do wrapper cung cấp.

Ví dụ:

```java
String name = (String) wrapper.getPropertyValue("name");
int age = (Integer) wrapper.getPropertyValue("age");
```

Đoạn trên giả định target có property `name: String` và `age: int`. Với property có thể là `null`, nên kiểm tra trước khi unbox; `(Integer) null` khi gán vào `int` gây `NullPointerException` do unboxing.

### Khi nào một property đọc được?

Property có thể đọc khi Spring xác định được đường đọc thích hợp, thường là getter có thể gọi. Có setter không có nghĩa chắc chắn đọc được. Dùng:

```java
if (wrapper.isReadableProperty("name")) {
    Object value = wrapper.getPropertyValue("name");
}
```

Đối với trường hợp property không tồn tại hoặc không có getter thích hợp, `getPropertyValue` có thể ném `NotReadablePropertyException` (thuộc nhóm `BeansException`); đừng giả định kết quả sẽ là `null`. **Property không tồn tại** khác **property hợp lệ nhưng hiện có giá trị null**.

### Getter có thể thực thi code

Nếu `getName()` tính toán giá trị, ghi log, gọi service hoặc ném exception, `getPropertyValue("name")` có thể kích hoạt hành vi tương ứng. `BeanWrapper` không miễn trừ side effect của getter. Vì vậy, gọi đọc property lặp lại trong một vòng lặp lớn có thể tốn chi phí hoặc tạo hành vi không mong đợi nếu getter không thuần.

## 4. setPropertyValue(String, Object): ghi qua cơ chế property access

Cú pháp:

```java
wrapper.setPropertyValue("name", "Bình");
wrapper.setPropertyValue("age", 20);
```

Spring tìm property đích và thực hiện phép gán phù hợp. Khi target dùng mutable JavaBean, setter tương ứng thường được gọi:

```java
customer.setName("Bình");
```

So với gọi setter trực tiếp, `setPropertyValue` hữu ích khi **tên property động**: đọc từ mapping, cấu hình hoặc một workflow có danh sách property cần cập nhật. Tuy nhiên, vì tên và value là dữ liệu runtime, các lỗi đường dẫn và chuyển kiểu thường chỉ phát hiện lúc chạy.

Các trường hợp cần phân biệt:

- **Property writable:** có setter (hoặc cơ chế property access khác phù hợp), nên có thể ghi.
- **Property read-only:** có getter nhưng không có setter; đọc được nhưng ghi có thể ném `NotWritablePropertyException`.
- **Property write-only:** có setter nhưng không có getter; ghi có thể được, đọc không được.
- **Property không tồn tại:** không thể suy ra member phù hợp, có thể ném lỗi truy cập property.
- **Property có setter kiểm tra điều kiện:** setter có thể tự từ chối và ném exception; wrapper không tự “chữa” logic setter.

Kiểm tra trước khi ghi:

```java
if (!wrapper.isWritableProperty("name")) {
    throw new IllegalArgumentException("Property không cho phép ghi");
}
wrapper.setPropertyValue("name", "Bình");
```

Đây là kiểm tra khả năng truy cập theo metadata, **không phải kiểm tra bảo mật hoặc validation dữ liệu**. Nếu tên property do client gửi, không nên chỉ dựa vào `isWritableProperty` để quyết định được phép sửa gì; cần allowlist rõ ràng và kiểm soát quyền ứng dụng.

### Đọc lại để xác nhận thay đổi

```java
wrapper.setPropertyValue("name", "Mai");
Object after = wrapper.getPropertyValue("name");
```

Nếu setter biến đổi đầu vào (ví dụ `trim`), `after` có thể khác chính xác chuỗi đã truyền. Giá trị sau khi set nên được xác nhận bằng getter nếu nghiệp vụ đòi hỏi, thay vì giả định setter giữ nguyên mọi ký tự.

## 5. Các dạng property path: đơn, nested, indexed và Map

`BeanWrapper` hỗ trợ **property path** phức tạp:

| Path | Ý nghĩa | Ví dụ kiểu Java |
| --- | --- | --- |
| `customerName` | Property trực tiếp trên target | `String customerName` |
| `shipping.city` | Property `city` của bean nằm trong `shipping` | `Address shipping` |
| `lines[0].quantity` | Property `quantity` của phần tử thứ 0 | `List<Line> lines` |
| `labels[channel]` | Giá trị Map tại key `channel` | `Map<String,String> labels` |
| `codes[1]` | Phần tử index 1 trong array/list được hỗ trợ | `String[] codes` |

Ví dụ đọc:

```java
Object city = wrapper.getPropertyValue("shipping.city");
Object quantity = wrapper.getPropertyValue("lines[0].quantity");
Object label = wrapper.getPropertyValue("labels[channel]");
```

Ví dụ ghi:

```java
wrapper.setPropertyValue("shipping.city", "Đà Nẵng");
wrapper.setPropertyValue("lines[0].quantity", 4);
wrapper.setPropertyValue("labels[channel]", "mobile");
```

**Một dấu chấm không đơn thuần là chuỗi chứa tên field.** Spring cần di chuyển qua đối tượng `shipping` để tới `city`. Nếu `shipping == null` và chế độ tự tạo nested object không được bật/không thực hiện được, thao tác có thể gặp `NullValueInNestedPathException`.

**Index phải hợp lệ.** `lines[0]` là phần tử đầu tiên; không nên giả định list có index đó hoặc mọi đối tượng có thể tự tạo. Spring có khả năng tự mở rộng một số collection theo cấu hình, nhưng cần chú ý giới hạn, kiểu phần tử, constructor và an toàn dữ liệu.

**Map key phải được xử lý đúng ngữ nghĩa.** Với `Map<String,String> labels`, `labels[channel]` truy cập key `"channel"`. Một số key đặc biệt chứa ký tự cú pháp có thể cần xử lý path riêng; khi input thiếu tin cậy, hạn chế key/property cho phép thay vì tự ghép chuỗi tùy ý.

## 6. Ví dụ Java 17+ đầy đủ: đọc và ghi cả bốn dạng property

Đây là chương trình console dùng Spring Framework **6.2.12**. Nó minh họa `getPropertyValue` và `setPropertyValue` trên property đơn, nested bean, `List` và `Map`, đồng thời dùng introspection để kiểm tra khả năng đọc/ghi và kiểu property.

Cấu trúc Maven:

```text
beanwrapper-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── BeanWrapperDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>beanwrapper-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-beans</artifactId>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Nội dung `src/main/java/BeanWrapperDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.BeanWrapper;
import org.springframework.beans.PropertyAccessorFactory;

public class BeanWrapperDemo {
    public static class Address {
        private String city;

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
    }

    public static class Line {
        private String sku;
        private int quantity;

        public String getSku() { return sku; }
        public void setSku(String sku) { this.sku = sku; }

        public int getQuantity() { return quantity; }
        public void setQuantity(int quantity) { this.quantity = quantity; }
    }

    public static class Checkout {
        private String customer = "An";
        private int count = 1;
        private Address shipping = new Address();
        private List<Line> lines = new ArrayList<>();
        private Map<String, String> labels = new LinkedHashMap<>();

        public Checkout() {
            shipping.setCity("Hue");

            Line first = new Line();
            first.setSku("BK1");
            first.setQuantity(1);
            lines.add(first);

            labels.put("channel", "web");
        }

        public String getCustomer() { return customer; }
        public void setCustomer(String customer) { this.customer = customer; }

        public int getCount() { return count; }
        public void setCount(int count) { this.count = count; }

        public Address getShipping() { return shipping; }
        public void setShipping(Address shipping) { this.shipping = shipping; }

        public List<Line> getLines() { return lines; }
        public void setLines(List<Line> lines) { this.lines = lines; }

        public Map<String, String> getLabels() { return labels; }
        public void setLabels(Map<String, String> labels) { this.labels = labels; }
    }

    public static void main(String[] args) {
        Checkout checkout = new Checkout();
        BeanWrapper wrapper =
                PropertyAccessorFactory.forBeanPropertyAccess(checkout);

        System.out.println("read.customer=" +
                wrapper.getPropertyValue("customer"));
        System.out.println("read.city=" +
                wrapper.getPropertyValue("shipping.city"));
        System.out.println("read.line=" +
                wrapper.getPropertyValue("lines[0].quantity"));
        System.out.println("read.label=" +
                wrapper.getPropertyValue("labels[channel]"));

        System.out.println("readable=" +
                wrapper.isReadableProperty("customer"));
        System.out.println("writable=" +
                wrapper.isWritableProperty("customer"));
        System.out.println("count.type=" +
                wrapper.getPropertyType("count").getSimpleName());

        wrapper.setPropertyValue("customer", "Binh");
        wrapper.setPropertyValue("count", "3");
        wrapper.setPropertyValue("shipping.city", "Da Nang");
        wrapper.setPropertyValue("lines[0].quantity", 2);
        wrapper.setPropertyValue("labels[channel]", "mobile");

        System.out.println("after.customer=" + checkout.getCustomer());
        System.out.println("after.count=" + checkout.getCount());
        System.out.println("after.city=" +
                checkout.getShipping().getCity());
        System.out.println("after.line=" +
                checkout.getLines().get(0).getQuantity());
        System.out.println("after.label=" +
                checkout.getLabels().get("channel"));
    }
}
```

Chạy từ thư mục `beanwrapper-demo` với JDK 17+ và Maven (lần chạy đầu Maven cần tải dependency):

```bash
mvn -q compile exec:java -Dexec.mainClass=BeanWrapperDemo
```

Đầu ra chuẩn từ các câu lệnh `System.out.println` trong ví dụ:

```text
read.customer=An
read.city=Hue
read.line=1
read.label=web
readable=true
writable=true
count.type=int
after.customer=Binh
after.count=3
after.city=Da Nang
after.line=2
after.label=mobile
```

**Giải thích từng thao tác:**

1. `PropertyAccessorFactory.forBeanPropertyAccess(checkout)` tạo wrapper hướng tới cùng instance `Checkout`.
2. `getPropertyValue("customer")` đọc property trực tiếp (qua `getCustomer()`).
3. `getPropertyValue("shipping.city")` đi qua getter `getShipping()` rồi `getCity()`.
4. `getPropertyValue("lines[0].quantity")` lấy phần tử đầu tiên của `lines` rồi đọc số lượng.
5. `getPropertyValue("labels[channel]")` lấy giá trị ứng với key `channel` trong Map.
6. `isReadableProperty` và `isWritableProperty` kiểm tra khả năng truy cập theo JavaBeans; `getPropertyType("count")` trả kiểu `int.class`.
7. `setPropertyValue("customer","Binh")` thay giá trị property.
8. `setPropertyValue("count","3")` minh họa cơ chế chuyển đổi String sang `int` phổ biến được Spring BeanWrapper hỗ trợ.
9. Các lệnh set còn lại thay đổi nested bean, phần tử list và entry Map; đọc trực tiếp từ `checkout` sau đó xác nhận wrapper đã cập nhật target gốc.

**Vì sao dùng `String "3"` cho `int count`?** Nó giúp nhìn thấy property type conversion. Spring có cơ chế property editors/chuyển đổi kiểu để hỗ trợ các trường hợp thông dụng như chuỗi số sang kiểu số. Nếu truyền `"abc"` vào `int`, phép gán có thể thất bại với `TypeMismatchException`; `setPropertyValue` không tự trả `false` hoặc một object `BindingResult`.

**Phạm vi kiểm chứng:** đây là chương trình hoàn chỉnh với dependency được khai báo, khác với các đoạn API lẻ trong bài. Đầu ra được suy ra từ logic trên và các getter/setter; khi đưa vào một môi trường khác hoặc thay đổi converter/editor, cần chạy thực tế để kiểm tra.

## 7. Biết trước kiểu và quyền truy cập: introspection hữu ích

Trước khi đọc/ghi property name động, có thể kiểm tra thông tin mà wrapper đã nhận diện:

```java
boolean canRead = wrapper.isReadableProperty("customer");
boolean canWrite = wrapper.isWritableProperty("customer");
Class<?> type = wrapper.getPropertyType("count");
```

`wrapper.getPropertyType(...)` trả kiểu property nếu xác định được, hoặc có thể trả `null` trong trường hợp không tìm được. Với primitive `int`, `type.getSimpleName()` là `"int"`. Với `List<Line>`, kiểu property cơ bản là `List`; muốn biết kiểu phần tử generic hoặc property nested cần dựa trên type descriptor/metadata phù hợp thay vì tự suy đoán từ `List.class`.

Một pattern kiểm tra đơn giản:

```java
String path = "shipping.city";

if (!wrapper.isReadableProperty(path)) {
    throw new IllegalArgumentException("Không thể đọc: " + path);
}

Object value = wrapper.getPropertyValue(path);
```

Đây là đoạn dùng trong ngữ cảnh có `wrapper`. **Chú ý:** kiểm tra trước không đảm bảo thao tác luôn thành công; getter vẫn có thể ném lỗi, target nested có thể thay đổi, hoặc một object graph bị chỉnh sửa giữa hai lời gọi.

### Read-only và write-only property

```java
public class ExampleBean {
    private String token;

    public void setToken(String token) { this.token = token; }

    public String getMaskedToken() {
        return token == null ? "" : "****";
    }
}
```

Đây là định nghĩa class minh họa. `token` có setter nhưng không có `getToken()` nên thường là **write-only property**; `maskedToken` có getter nhưng không có `setMaskedToken(...)` nên thường là **read-only property**. Wrapper có thể ghi `token` và đọc `maskedToken`; không thể mặc nhiên làm cả hai chiều cho mỗi property.

Ví dụ này chỉ giải thích khả năng truy cập. Thiết kế thực tế phải tránh giữ token/mật khẩu nhạy cảm lâu hơn cần thiết; không dùng `BeanWrapper` như cơ chế bảo mật.

## 8. Nested null, auto-grow và giới hạn truy cập

Với target có `shipping == null`:

```java
wrapper.setPropertyValue("shipping.city", "Hue");
```

Nếu không có cách tạo instance `Address` trung gian, Spring có thể ném `NullValueInNestedPathException`. Khi có mục đích rõ ràng, BeanWrapper implementation hỗ trợ **auto-grow nested paths**:

```java
import org.springframework.beans.BeanWrapperImpl;

// Checkout và Address từ ví dụ phần 6.
Checkout form = new Checkout();
form.setShipping(null);

BeanWrapperImpl wrapper = new BeanWrapperImpl(form);
wrapper.setAutoGrowNestedPaths(true);
wrapper.setPropertyValue("shipping.city", "Hue");

System.out.println(form.getShipping().getCity()); // Hue
```

Đây là đoạn độc lập về mặt luồng gọi nhưng cần hai class `Checkout` và `Address` của ví dụ đầy đủ. `Address` có constructor không tham số mặc định và setter công khai, nên có thể tạo nested instance trong điều kiện cho phép. Nếu kiểu con là interface/abstract class, thiếu constructor phù hợp, hoặc không có đường gán, auto-grow không nhất thiết thành công.

Với indexed property, việc tự mở rộng collection cũng phải có giới hạn và dựa trên khả năng suy ra/khởi tạo kiểu phần tử. Không để chuỗi path do client kiểm soát tự do yêu cầu index cực lớn, vì có thể gây tiêu tốn bộ nhớ hoặc thao tác ngoài ý muốn. Với web binding nên sử dụng DTO, allowlist và hạn chế số phần tử mà ứng dụng chấp nhận.

### Immutable object/record

```java
record Point(int x, int y) {}
```

Một record không có setter cho `x`/`y` nên không phải target tự nhiên cho `BeanWrapper.setPropertyValue("x", ...)`. Đọc property có thể được hỗ trợ tùy cơ chế introspection/phiên bản và cách truy cập, nhưng **đừng giả định record component là writable JavaBean property**.

Khi muốn binding vào object immutable, hãy dùng **constructor binding** hoặc tạo instance mới qua constructor/builder phù hợp. Đây là vấn đề cơ chế tạo object, không thể giải quyết đơn giản bằng cách gọi `setPropertyValue` nhiều lần.

## 9. Chuyển đổi kiểu khi ghi và cách cấu hình

`setPropertyValue` nhận `Object` nhưng property đích có kiểu cụ thể. Do đó wrapper phải kiểm tra tính tương thích và có thể chuyển đổi thông qua cơ chế của Spring:

```text
value đầu vào: "3" (String)
          |
          v
setPropertyValue("count", "3")
          |
          v
PropertyDescriptor: count là int
          |
          v
TypeConverter / PropertyEditor / ConversionService (nếu cấu hình)
          |
          v
setter setCount(3)
```

Ví dụ `"3"` sang `int` thuộc nhóm chuyển đổi kiểu thông dụng. Ngược lại, `"ba"` sang `int` không tạo được số hợp lệ và có thể phát sinh lỗi. Với kiểu domain tùy biến, một `Converter` hoặc `PropertyEditor` được đăng ký đúng phạm vi giúp Spring hiểu cách chuyển đổi; không nên viết các nhánh `instanceof` rải rác trong code calling layer.

Ví dụ áp dụng `ConversionService` cho một `BeanWrapperImpl`:

```java
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.core.convert.support.DefaultConversionService;

BeanWrapperImpl wrapper = new BeanWrapperImpl(target);
DefaultConversionService service = new DefaultConversionService();

wrapper.setConversionService(service);
wrapper.setPropertyValue("count", "3");
```

Đây là **đoạn minh họa cấu hình**; `target` phải là instance có property `count` kiểu số. `DefaultConversionService` chứa nhiều converter tiêu chuẩn. Với định dạng theo locale như số `"1,5"` hoặc ngày địa phương, `FormattingConversionService` và `Formatter` có thể thích hợp hơn; cần xác định locale và phạm vi đăng ký.

**Đọc khác ghi:** `getPropertyValue` trả giá trị property đang có; nó không tự chuyển mọi giá trị thành chuỗi định dạng cho UI. Muốn trình bày số, ngày, tiền theo `Locale`, hãy dùng formatter/View layer phù hợp, không gộp nhiệm vụ đó vào semantics của `getPropertyValue`.

## 10. Lỗi truy cập property: nhận diện thay vì nuốt lỗi

Các nhóm lỗi thường gặp khi sử dụng API theo path:

| Trường hợp | Biểu hiện/exception thường gặp | Hướng xử lý |
| --- | --- | --- |
| Đọc property thiếu getter hoặc tên không tồn tại | `NotReadablePropertyException` | Kiểm tra chính tả path và getter |
| Ghi property thiếu setter hoặc không writable | `NotWritablePropertyException` | Kiểm tra setter/thiết kế object |
| Nested object là `null` | `NullValueInNestedPathException` | Khởi tạo object hoặc bật auto-grow có kiểm soát |
| Kiểu giá trị không chuyển được | `TypeMismatchException` hoặc lỗi conversion liên quan | Kiểm tra type, converter/editor, input |
| Index vượt phạm vi hoặc path không hợp lệ | `InvalidPropertyException` hoặc lỗi truy cập khác | Kiểm tra collection, key, path và giới hạn |
| Getter/setter ném exception | Exception được Spring bọc/lan truyền tùy nhánh truy cập | Kiểm tra nguyên nhân gốc trong accessor |
| Property thay đổi đồng thời | Kết quả không ổn định | Tránh chia sẻ target mutable không đồng bộ |

Những loại exception cụ thể phụ thuộc operation, path và version Spring; bảng là **hướng chẩn đoán**, không cam kết một exception duy nhất cho mọi trường hợp.

Ví dụ xử lý có mục đích:

```java
import org.springframework.beans.NotWritablePropertyException;
import org.springframework.beans.TypeMismatchException;

try {
    wrapper.setPropertyValue("count", "abc");
} catch (NotWritablePropertyException ex) {
    // Property không tồn tại hoặc không có đường ghi thích hợp.
} catch (TypeMismatchException ex) {
    // Value không tương thích và không chuyển được sang kiểu đích.
}
```

Đây là đoạn áp dụng với một `wrapper` đã có. Trong một số cấu hình, lỗi có thể đi qua lớp exception liên quan khác; việc phục hồi cần dựa trên root cause, không chỉ dựa tên exception.

**Không nên xử lý chung mọi lỗi bằng catch rồi bỏ qua.** Nếu người dùng nhập sai, cần trả một lỗi có thể sửa được; nếu lập trình sai property path, cần sửa code và có log phù hợp. Nuốt lỗi khiến trạng thái target có thể bị cập nhật một phần mà caller vẫn tưởng thành công.

## 11. Ghi nhiều property: atomicity không được bảo đảm

`BeanWrapper` hỗ trợ cả `setPropertyValues(...)`, nhưng khi gọi nhiều setter, đây **không phải giao dịch có rollback**:

```java
wrapper.setPropertyValue("customer", "Mai");
wrapper.setPropertyValue("count", "not-a-number");
```

Lệnh đầu có thể đã đổi `customer`; lệnh thứ hai có thể thất bại vì chuyển kiểu. Target khi đó **đã thay đổi một phần**. Ngay cả khi dùng `setPropertyValues(...)`, không nên giả định tính atomic của nhiều phép gán.

Với dữ liệu đầu vào không đáng tin cậy hoặc cần nhất quán nghiệp vụ, nên:

1. Bind vào DTO thích hợp, không tùy ý vào entity đang quản lý.
2. Thu thập lỗi binding và validation.
3. Chỉ tiếp tục tới tầng service/domain nếu dữ liệu hợp lệ.
4. Thiết kế cơ chế transaction/đổi trạng thái nhất quán ở tầng nghiệp vụ phù hợp.

`BeanWrapper` cung cấp thao tác property, không giải quyết hết transaction, bảo mật và consistency.

## 12. BeanWrapper khác DataBinder như thế nào?

`DataBinder` của Spring xây trên cơ chế property access/conversion để xử lý luồng bind input vào target, quản lý allowed/disallowed fields và đưa lỗi vào `BindingResult`. `BeanWrapper` trực tiếp gần thao tác đọc/ghi property hơn và thường **ném exception** khi gặp lỗi truy cập/chuyển kiểu.

| Nhu cầu | BeanWrapper | DataBinder |
| --- | --- | --- |
| Đọc property động | `getPropertyValue(path)` | Không phải API chính để đọc từng property |
| Ghi property động | `setPropertyValue(path,value)` | `bind(PropertyValues)` |
| Nested/indexed path | Có, với điều kiện object graph phù hợp | Có, theo cấu hình binding |
| Chuyển kiểu khi cần | Có cơ chế conversion/editor | Có, thông qua binder |
| Thu thập lỗi binding thành kết quả | Thường ném exception ở call trực tiếp | `getBindingResult()` |
| Gọi validator | Không tự kích hoạt validation | `setValidator/addValidators`, rồi `validate()` |
| Giới hạn input fields | Caller tự bảo vệ path/value | `setAllowedFields` cho property binding |
| Tích hợp controller MVC | Thường là cơ chế nền | `WebDataBinder` được MVC dùng |

Một đoạn `DataBinder` dùng cùng tư tưởng:

```java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

Checkout form = new Checkout();
DataBinder binder = new DataBinder(form, "checkout");
binder.setAllowedFields("customer", "count", "shipping.city");

MutablePropertyValues values = new MutablePropertyValues();
values.add("customer", "Mai");
values.add("count", "3");
values.add("shipping.city", "Da Nang");

binder.bind(values);
BindingResult result = binder.getBindingResult();
if (result.hasErrors()) {
    // Xử lý lỗi binding thay vì xem mọi exception là lỗi hệ thống.
}
```

Đây là đoạn độc lập về cách dùng API nhưng cần class `Checkout` từ phần 6. Nếu muốn chạy các rule nghiệp vụ (ví dụ `count > 0`), phải thêm validator phù hợp và gọi `binder.validate()` hoặc dùng luồng MVC kích hoạt validation tương ứng.

**Ranh giới cần nhớ:** `@ModelAttribute` và `WebDataBinder` trong Spring MVC phục vụ binding form/query parameters; `@RequestBody` JSON thường đi qua HTTP message converter như Jackson trước. Không coi `BeanWrapper.setPropertyValue` là con đường bắt buộc cho mọi dữ liệu JSON của ứng dụng.

## 13. An toàn khi property name đến từ bên ngoài

Một pattern rủi ro:

```java
// Không sử dụng cho property name do client kiểm soát.
wrapper.setPropertyValue(requestParameterName, requestParameterValue);
```

Nếu target có các property như `admin`, `role`, `ownerId` hoặc `price`, dữ liệu từ client có thể yêu cầu ghi những trường ngoài ý định. Dù `isWritableProperty` trả `true`, caller **vẫn cần quyền nghiệp vụ** và danh sách property được phép.

Cách kiểm soát tối thiểu khi không dùng `DataBinder`:

```java
import java.util.Set;

Set<String> allowed = Set.of("customer", "count");
String path = requestParameterName;

if (!allowed.contains(path)) {
    throw new IllegalArgumentException("Field không được phép cập nhật");
}
wrapper.setPropertyValue(path, requestParameterValue);
```

Đây là đoạn minh họa: các biến `requestParameterName` và `requestParameterValue` phải được caller cung cấp, và allowlist trên chỉ phù hợp với contract tương ứng. Với path nested, phải kiểm soát **toàn bộ đường dẫn**, không chỉ tiền tố (chấp nhận `shipping` không đồng nghĩa cho phép `shipping.internalFlag`).

Trong ứng dụng web, ưu tiên DTO/command object có trường cần nhập, giới hạn binding và kiểm tra quyền ở tầng service. `BeanWrapper` là tiện ích truy cập; nó không tự xác thực người gọi và không xác định property nào hợp lệ theo nghiệp vụ.

## 14. Khi nào nên dùng getPropertyValue và setPropertyValue?

**Các trường hợp hợp lý:**

- Hệ thống mapping/transform có schema property được kiểm soát, cần đọc/ghi theo tên runtime.
- Công cụ cấu hình hoặc adapter đọc metadata bean để hiển thị trạng thái, với allowlist phù hợp.
- Framework infrastructure, binder, biểu mẫu động hoặc component cần truy cập property nested.
- Test/utilities kiểm tra trạng thái JavaBean mà không muốn hardcode mọi getter.

**Các trường hợp thường không cần:**

- Logic nghiệp vụ đã biết thuộc tính tại compile time: dùng getter/setter trực tiếp.
- Thay đổi domain object immutable: dùng constructor/builder.
- Trả JSON HTTP: dùng serializer có contract rõ, không tự truy cập property tùy ý.
- Ghi dữ liệu từ request vào entity có field nhạy cảm: dùng DTO, binding có kiểm soát và service.

## 15. Checklist khi debug hai phương thức

| Triệu chứng | Câu hỏi chẩn đoán | Cách khắc phục |
| --- | --- | --- |
| `getPropertyValue("x")` ném lỗi | Có getter `getX()/isX()` không? Path đúng không? | Kiểm tra `isReadableProperty` và JavaBean convention |
| `setPropertyValue("x",...)` không ghi | Có setter phù hợp không? | Kiểm tra `isWritableProperty` và setter |
| `shipping.city` lỗi | `shipping` đã được khởi tạo? | Khởi tạo object hoặc auto-grow khi hợp lý |
| `lines[0].quantity` lỗi | List có phần tử 0? Kiểu phần tử có getter/setter? | Chuẩn bị collection và giới hạn index |
| Gán chuỗi vào kiểu số thất bại | Có conversion cho kiểu đích? Chuỗi hợp lệ? | Kiểm tra kiểu property, converter/editor |
| Setter có hiệu ứng không mong muốn | Getter/setter chứa logic nào? | Đọc implementation, tránh gọi lặp vô ý |
| Ghi nhiều field để lại dữ liệu dở dang | Có giả định atomicity? | Bind/validate trên DTO, thực hiện thay đổi nghiệp vụ có kiểm soát |
| Record không set được component | Có setter không? | Constructor binding hoặc tạo instance mới |
| Client cập nhật được field không nên phép | Có allowlist và kiểm tra quyền? | Giới hạn field path/DTO và authorization |

Một quy trình thực dụng khi xử lý lỗi:

1. Xác minh **target instance** và class thật đang được wrap.
2. In **property path** dự kiến (chỉ khi không chứa dữ liệu nhạy cảm).
3. Kiểm tra `isReadableProperty`/`isWritableProperty` và `getPropertyType`.
4. Kiểm tra nested object/list/map có cấu trúc phù hợp.
5. Với `setPropertyValue`, kiểm tra kiểu nguồn và cơ chế conversion.
6. Nếu setter được gọi nhưng trạng thái không như ý, kiểm tra logic setter.
7. Với dữ liệu từ người dùng, kiểm tra allowlist và cách trả lỗi có thể sửa được.

## 16. Tự kiểm tra

**Câu 1.** `getPropertyValue("name")` trả `Object` có thể là `null`. Làm sao phân biệt property hợp lệ đang null với property không đọc được?  
Dùng `isReadableProperty("name")` và kiểm tra lỗi truy cập; `null` là giá trị hợp lệ, còn path không hợp lệ có thể gây exception.

**Câu 2.** Một JavaBean có `getCode()` nhưng không có `setCode(...)`. Có đọc và ghi `code` được không?  
Thông thường đọc được, ghi không; `isWritableProperty("code")` sẽ phản ánh trạng thái writable.

**Câu 3.** Với `lines` là `List<Line>` chứa phần tử đầu tiên, muốn sửa `quantity` của phần tử đó nên dùng path nào?  
`lines[0].quantity`. Cần item ở index 0 và đường ghi phù hợp cho property `quantity`.

**Câu 4.** Vì sao `setPropertyValue("count", "3")` có thể thành công dù setter nhận `int`?  
BeanWrapper hỗ trợ cơ chế chuyển kiểu; chuỗi số hợp lệ có thể được chuyển thành `int` trước khi gọi setter. Không có nghĩa mọi chuỗi đều chuyển được.

**Câu 5.** `setPropertyValue("customer","Mai")` thành công, sau đó set `count` thất bại. Spring có tự rollback `customer` không?  
Không. `BeanWrapper` không cung cấp transaction cho tập thao tác property.

**Câu 6.** Có thể dùng `isWritableProperty` làm kiểm tra quyền cập nhật dữ liệu không?  
Không. Đó là metadata về khả năng truy cập theo JavaBean; quyền cập nhật phải do contract/authorization quyết định.

**Câu 7.** Khi nào chọn `DataBinder` thay vì gọi hàng chục `setPropertyValue`?  
Khi cần bind input từ người dùng vào DTO, giới hạn field, xử lý conversion error tập trung qua `BindingResult` và chạy validator theo quy trình ứng dụng.

**Ghi nhớ:** `getPropertyValue` **đọc** thông qua đường property; `setPropertyValue` **ghi** thông qua đường property và có thể chuyển kiểu. Hai lời gọi làm việc với **target hiện tại**, có thể đi qua **nested/indexed/Map path**, chịu lỗi truy cập lúc runtime, và **không tự thay thế validation, authorization hoặc transaction**.

## Tài liệu tham khảo chính thức

- [Spring Framework — BeanWrapper and JavaBeans API](https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html)
- [Spring Framework — BeanWrapper interface (Javadoc 6.2)](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/beans/BeanWrapper.html)
- [Spring Framework — PropertyAccessor interface (Javadoc 6.2)](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/beans/PropertyAccessor.html)
- [Spring Framework — BeanWrapperImpl (Javadoc 6.2)](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/beans/BeanWrapperImpl.html)
- [Spring Framework — PropertyAccessorFactory (Javadoc 6.2)](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/beans/PropertyAccessorFactory.html)
- [Spring Framework — Validation, Data Binding, and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
