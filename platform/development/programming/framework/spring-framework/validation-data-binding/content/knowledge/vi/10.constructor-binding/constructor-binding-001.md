# Constructor binding của DataBinder từ Spring Framework 6.1

## 1. Vấn đề mà constructor binding giải quyết

Khi Spring nhận dữ liệu bên ngoài, chẳng hạn các tham số của form đăng ký, nó cần tạo một đối tượng Java. Với cách bind thuộc tính quen thuộc, ứng dụng tạo sẵn một JavaBean rồi Spring gọi các setter tương ứng. Từ **Spring Framework 6.1**, `org.springframework.validation.DataBinder` còn hỗ trợ **constructor binding**: đọc các giá trị đầu vào theo tên tham số constructor, chuyển đổi kiểu khi cần, rồi **gọi constructor để tạo target**.

Ví dụ dữ liệu:

```text
name = Mai
age  = 21
```

và kiểu bất biến:

```java
public record Registration(String name, int age) {}
```

Không có setter cho `name` và `age`. Constructor binding vẫn tạo được `Registration[name=Mai, age=21]` bằng cách chuyển chuỗi `"21"` sang `int` và gọi constructor chuẩn của record.

Hai cách bind có cùng mục đích là đưa dữ liệu vào đối tượng, nhưng khác nhau về thời điểm tạo object và bề mặt dữ liệu có thể được ghi:

| Khía cạnh | Constructor binding (Spring 6.1+) | Property/setter binding |
| --- | --- | --- |
| Object lúc bắt đầu | Thường là `null`; binder biết trước loại `targetType` | Thường đã có instance |
| Cách đưa dữ liệu vào | Gọi constructor với tham số được resolve | Gọi setter hoặc cập nhật trường theo cấu hình |
| Mô hình phù hợp | Record, DTO bất biến, object có constructor rõ ràng | JavaBean có setter, mô hình cần cập nhật nhiều thuộc tính |
| Các API nổi bật | `setTargetType(...)`, `construct(ValueResolver)` | `bind(PropertyValues)` |
| Phạm vi thuộc tính có thể nhận | Tham số constructor và object lồng nhau cần dựng | Các thuộc tính có thể ghi theo cấu hình binder |
| Chuyển đổi kiểu/lỗi | Thông qua hệ thống conversion, báo binding errors | Thông qua hệ thống conversion, báo binding errors |
| Validation | Vẫn là bước cần kích hoạt và kiểm tra riêng | Vẫn là bước cần kích hoạt và kiểm tra riêng |

**Điểm quan trọng:** constructor binding **không phải** `@Autowired` constructor injection của Spring IoC. Cùng sử dụng constructor nhưng một bên lấy giá trị từ **dữ liệu cần bind**, bên kia cung cấp các **dependency của bean**. Constructor binding cũng không phải tự động gọi `jakarta.validation.Validator`: quá trình tạo object và quá trình kiểm tra các constraint là hai mối quan tâm riêng.

## 2. Ba bước bắt buộc của DataBinder.construct

Để dùng trực tiếp API `DataBinder`, trình tự cơ bản theo tài liệu Spring 6.1 là:

```java
DataBinder binder = new DataBinder(null, "registration");
binder.setTargetType(ResolvableType.forClass(Registration.class));
binder.construct(valueResolver);
```

Trong đó:

1. **Tạo binder có target `null`**: `new DataBinder(null, "registration")` thông báo hiện chưa có instance. `"registration"` là object name để báo lỗi, không phải tên class.
2. **Chỉ định kiểu object phải tạo**: `setTargetType(ResolvableType.forClass(Registration.class))`. `ResolvableType` thuộc `org.springframework.core`, hỗ trợ mô tả cả kiểu có generic khi cần.
3. **Cung cấp cách tìm giá trị rồi gọi `construct(...)`**: `DataBinder.ValueResolver` ánh xạ tên tham số constructor sang giá trị đầu vào. Spring chọn constructor phù hợp, chuyển đổi kiểu và dựng target.

Sau khi dựng:

```java
Object target = binder.getTarget();
BindingResult errors = binder.getBindingResult();
```

Các dòng trên chỉ minh họa cách đọc kết quả; chúng nằm trong method đã có `binder`. Ứng dụng phải xét `errors.hasErrors()` trước khi coi target là dữ liệu hợp lệ để sử dụng. Khi dựng thành công, `getTarget()` trả instance mới. Khi binding/constructor gặp lỗi, xử lý theo `BindingResult` và exception thực tế thay vì mặc định luôn tồn tại object sử dụng được.

### Tại sao không bắt đầu từ new Registration(...)

Nếu đã tự gọi `new Registration("Mai", 21)` thì không còn nhu cầu để binder xây dựng đối tượng từ input nữa. Với constructor binding, bạn giao cho binder việc chọn các tham số và chuyển đổi kiểu từ dữ liệu chưa có kiểu Java chính xác. Constructor được dùng như **hợp đồng đầu vào**; quá trình này đặc biệt hữu ích trong cơ chế `@ModelAttribute` của Spring MVC hoặc dữ liệu form/query.

## 3. DataBinder.ValueResolver nhận và trả gì?

`DataBinder.ValueResolver` là giao diện cho chiến lược lấy dữ liệu đầu vào. Phương thức chính có chữ ký:

```java
Object resolveValue(String name, Class<?> type);
```

- `name`: tên tham số mà Spring muốn lấy. Nó có thể là tên đơn như `age` hoặc đường dẫn lồng nhau như `address.city`.
- `type`: kiểu Java của tham số constructor mà Spring đang cố bind, chẳng hạn `String.class` hoặc `int.class`.
- Kết quả: giá trị nguồn, thường là `String`, `String[]` hoặc object tương thích; có thể `null` nếu input không cung cấp.
- Nếu giá trị trả về chưa đúng kiểu, Spring dùng khả năng type conversion được cấu hình để chuyển trước khi gọi constructor.

Từ các phiên bản **Spring 6.1.2 trở lên**, giao diện còn có phương thức `getNames()` trả `Set<String>` các tên giá trị khả dụng. Nó giúp xử lý những tình huống như object lồng nhau, collection hoặc các key có chỉ số. Ví dụ bên dưới **triển khai cả `resolveValue` và `getNames`** để tương thích với Spring 6.1.14 được dùng trong bài.

Một resolver dùng dữ liệu từ map có thể viết:

```java
final class MapValueResolver implements DataBinder.ValueResolver {
    private final Map<String, String> values;

    MapValueResolver(Map<String, String> values) {
        this.values = values;
    }

    @Override
    public Object resolveValue(String name, Class<?> type) {
        return values.get(name);
    }

    @Override
    public Set<String> getNames() {
        return values.keySet();
    }
}
```

Đây là đoạn mã minh họa class cần import `java.util.Map`, `java.util.Set` và `DataBinder`; chương trình hoàn chỉnh có đủ import ở mục 5. `resolveValue` **không cần tự parse `int`** nếu chọn để Spring thực hiện chuyển đổi. Trường hợp input có nhiều giá trị hoặc dữ liệu nguồn đặc biệt, resolver phải quyết định định dạng và lựa chọn giá trị tương ứng; không phải cứ trả về một chuỗi ngẫu nhiên là Spring sẽ hiểu đúng.

### Một NameResolver khác ValueResolver thế nào?

- `ValueResolver` quyết định **tìm giá trị ở đâu và trả về giá trị gì** cho một tên.
- `DataBinder.NameResolver` quyết định **dùng tên nào** để tra cứu giá trị của tham số constructor.

Mặc định, Spring dùng tên tham số constructor, lấy từ thông tin phù hợp của class. Có thể cấu hình `setNameResolver(...)` để thay đổi quy ước tên. Trong Spring MVC/WebFlux, annotation `@BindParam` có thể chỉ định tên tham số dữ liệu bên ngoài khác tên tham số Java. `@BindParam` thuộc tầng web; một `DataBinder` độc lập sẽ không tự động sử dụng mọi quy ước annotation của MVC nếu chưa cấu hình `NameResolver` tương ứng.

Ví dụ về ánh xạ tên trong tầng Spring MVC:

```java
import org.springframework.web.bind.annotation.BindParam;

public record ContactForm(
    @BindParam("full_name") String name,
    String email
) {}
```

Đây là snippet minh họa trong ứng dụng Spring Web; `full_name` là key bên ngoài, còn `name` là tên thuộc tính trong record. Không cần đổi tên property của Java để khớp mọi tên biến phía HTML. Tương tự, có thể viết `NameResolver` riêng khi dùng `DataBinder` trực tiếp.

## 4. Spring chọn constructor như thế nào?

Constructor binding dựa trên **constructor dùng để dựng dữ liệu**, không phải tự động gọi mọi constructor có thể tìm thấy. Theo tài liệu Spring Framework 6.1:

- Kiểu nên có **một constructor dữ liệu rõ ràng**, có thể public hoặc constructor phù hợp với cách Spring tìm constructor chính.
- Record Java có constructor chuẩn gắn với record components; `record Registration(String name, int age)` là ví dụ tự nhiên.
- Constructor có tên tham số nhận diện được là điều quan trọng. Với Java class thông thường, biên dịch có `-parameters` hoặc dùng `@ConstructorProperties` nếu phù hợp.
- Nếu có nhiều constructor và có constructor không tham số, Spring có thể chọn default constructor, rồi hướng đến property binding; không nên phó mặc cho việc đoán constructor trong mô hình có nhiều lựa chọn.
- Với nhiều public constructors hoặc class thiếu một đường dựng rõ ràng, cần kiểm tra chiến lược chọn constructor của phiên bản Spring đang dùng thay vì khẳng định Spring sẽ đoán đúng.

Ví dụ class dùng `@ConstructorProperties`:

```java
import java.beans.ConstructorProperties;

public final class CustomerForm {
    private final String customerCode;
    private final int quantity;

    @ConstructorProperties({"customerCode", "quantity"})
    public CustomerForm(String customerCode, int quantity) {
        this.customerCode = customerCode;
        this.quantity = quantity;
    }

    public String getCustomerCode() {
        return customerCode;
    }

    public int getQuantity() {
        return quantity;
    }
}
```

Đây là ví dụ class độc lập về cách công bố tên constructor arguments. `@ConstructorProperties` không thực hiện binding; nó cung cấp metadata tên cho framework. Cần để tên khai báo khớp đúng ý nghĩa từng tham số. Với Java 17 records, Spring hỗ trợ nhận diện canonical constructor/record component names; biên dịch có `-parameters` vẫn là thói quen tốt khi làm việc với Java classes thông thường.

## 5. Chương trình Java 17 chạy được

Chương trình dùng **Spring Framework 6.1.14** và Java 17, không cần Spring Boot, servlet container, controller hay JSON. Ta cho binder nhận map gồm hai chuỗi `"Mai"` và `"21"`; sau `construct`, record mới có `name` kiểu `String` và `age` kiểu `int`.

Cấu trúc thư mục:

```text
constructor-binding-demo/
├── pom.xml
└── src/main/java/demo/ConstructorBindingDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>constructor-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

Nội dung `src/main/java/demo/ConstructorBindingDemo.java`:

```java
package demo;

import java.util.Map;
import java.util.Set;
import org.springframework.core.ResolvableType;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class ConstructorBindingDemo {

    // Không có setter: Spring phải dùng constructor của record.
    public record Registration(String name, int age) {}

    public static final class MapValueResolver
            implements DataBinder.ValueResolver {

        private final Map<String, String> values;

        public MapValueResolver(Map<String, String> values) {
            this.values = values;
        }

        @Override
        public Object resolveValue(String name, Class<?> type) {
            return values.get(name);
        }

        @Override
        public Set<String> getNames() {
            return values.keySet();
        }
    }

    public static void main(String[] args) {
        Map<String, String> input = Map.of(
            "name", "Mai",
            "age", "21"
        );

        // Ban đầu không có Registration instance.
        DataBinder binder = new DataBinder(null, "registration");

        // Spring 6.1+: khai báo kiểu cần được tạo.
        binder.setTargetType(
            ResolvableType.forClass(Registration.class)
        );

        // Đọc các giá trị theo tên và gọi constructor.
        binder.construct(new MapValueResolver(input));

        BindingResult errors = binder.getBindingResult();
        if (errors.hasErrors()) {
            throw new IllegalStateException(
                "Constructor binding errors: " + errors
            );
        }

        Registration registration =
            (Registration) binder.getTarget();

        System.out.println(registration);
        System.out.println("errors=" + errors.getErrorCount());
    }
}
```

Chạy trong thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConstructorBindingDemo
```

**Hai dòng do chương trình in ra** trong trường hợp input hợp lệ (không tính thông báo/log riêng của Maven hoặc framework):

```text
Registration[name=Mai, age=21]
errors=0
```

Vì sao:

1. `binder.getTarget()` ban đầu là `null`.
2. `setTargetType(...)` cho Spring biết cần tạo `Registration`.
3. Spring đọc tên component `name` và `age` của record, hỏi `MapValueResolver` lấy dữ liệu tương ứng.
4. Resolver trả `"Mai"` và `"21"`.
5. Conversion từ `String "21"` sang `int 21` được Spring thực hiện theo kiểu constructor parameter.
6. Canonical constructor tạo `new Registration("Mai", 21)` về mặt kết quả; binder lưu target này.
7. Không có lỗi binding, nên `BindingResult.getErrorCount()` là `0`. Vì record cung cấp `toString()` theo khuôn mẫu tên và component, dòng đầu hiển thị như trên.

Đoạn mã **không tự bật Jakarta Bean Validation** và không kiểm tra `name` có rỗng hay `age` có đủ lớn. Nó minh họa **khả năng tạo và chuyển kiểu dữ liệu**. Phần validation là bước bổ sung sẽ được nói rõ sau.

## 6. Nested constructor binding và đường dẫn tên

Constructor binding không chỉ dùng cho các tham số đơn giản. Spring 6.1 hỗ trợ **dựng đối tượng lồng nhau** bằng constructor, từ các input có đường dẫn như `address.city`.

Giả sử mô hình:

```java
public record Address(String city) {}

public record Registration(
    String name,
    int age,
    Address address
) {}
```

Dữ liệu ngoài có thể mang các key:

```text
name = Mai
age = 21
address.city = Ha Noi
```

Lúc Spring đang dựng `Registration`, nó nhận ra tham số `address` có kiểu object cần dựng tiếp. Nó có thể gọi constructor của `Address`, tra cứu dữ liệu với tên lồng nhau `address.city`, rồi truyền `Address("Ha Noi")` vào constructor `Registration`. Đây là **mô tả cơ chế**, không phải phần thay thế code runnable ở mục 5.

Với một `ValueResolver` tùy biến, bạn cần hỗ trợ **tên đầy đủ** mà Spring yêu cầu. Ví dụ resolver kiểu map có thể tra trực tiếp `values.get("address.city")`. Ở Spring 6.1.2+, `getNames()` hỗ trợ framework biết có những tên lồng sâu nào được cung cấp. Nếu resolver không liệt kê đúng các key của input, các nhánh lồng nhau hoặc collection có thể không được khởi tạo như dự kiến.

### Collections và Map

Spring còn có thể dựng các tham số kiểu `List`, `Map` hoặc array từ giá trị đầu vào có cấu trúc phù hợp. Ví dụ các tên:

```text
items[0].sku = A01
items[1].sku = B02
attributes[COLOR] = blue
```

Đây là biểu diễn các key đầu vào, không phải code Java. Khi dùng kiểu dữ liệu phức tạp, cần xem xét type parameters (`List<Item>`), cách Spring giải mã index/key, conversion và giới hạn số phần tử. Không nên mở rộng tùy ý quy mô object graph do input bên ngoài điều khiển. Một `ValueResolver` dùng map phẳng đơn giản là điểm bắt đầu, nhưng trong ứng dụng web thực tế thường sử dụng resolver do Spring MVC/WebFlux cung cấp.

## 7. Binding errors khi constructor argument không hợp lệ

Constructor binding làm **type conversion**, nên có thể phát sinh **lỗi gắn dữ liệu** trước khi đến bước kiểm tra ràng buộc nghiệp vụ. Xét input:

```text
name = Mai
age = abc
```

`"abc"` không thể chuyển thành `int` theo conversion mặc định. Spring ghi nhận lỗi thích hợp trong `BindingResult` (thường là field error có error code gốc `typeMismatch`). Một ứng dụng cần đọc:

```java
BindingResult result = binder.getBindingResult();

if (result.hasFieldErrors()) {
    result.getFieldErrors().forEach(error ->
        System.out.println(error.getField()
                + " -> " + error.getCode()));
}
```

Đây là snippet đặt sau `construct(...)` trong chương trình đã cấu hình binder. Đừng giả định constructor luôn được gọi thành công khi conversion thất bại; việc tạo target phụ thuộc cấu trúc constructor và cách Spring xử lý lỗi. Cần kiểm tra kết quả trước khi dùng `getTarget()`. Một constructor tự ném exception vì quy tắc nội bộ còn có thể dẫn tới `BeanInstantiationException` hoặc exception tương ứng, khác với lỗi chuyển đổi đơn giản được biểu diễn trong `BindingResult`.

### Binding không phải validation

Hai ví dụ lỗi khác nhau:

- `age = "abc"`: lỗi **binding/conversion** vì chưa tạo được giá trị `int` hợp lệ.
- `age = "16"`: conversion sang `int 16` thành công nhưng có thể **không đạt luật nghiệp vụ** như tuổi tối thiểu 18. `DataBinder.construct(...)` không tự tạo luật tuổi tối thiểu.

Nếu muốn validation sau khi dựng object, đăng ký validator phù hợp rồi yêu cầu validation theo API Spring:

```java
// Khi binder đã có target hợp lệ:
binder.addValidators(registrationValidator);
binder.validate();

BindingResult errors = binder.getBindingResult();
if (errors.hasErrors()) {
    // Báo lỗi, không đưa object vào quy trình nghiệp vụ.
}
```

Đây là đoạn minh họa với `registrationValidator` do ứng dụng định nghĩa và hỗ trợ đúng target type. Với Jakarta Validation, có thể sử dụng adapter `LocalValidatorFactoryBean` và provider tương thích trong ngữ cảnh Spring. Bản thân `construct` chỉ là một phần của toàn bộ luồng xử lý dữ liệu.

### Giá trị thiếu và null

Nếu resolver không tìm thấy `age`, nó có thể trả `null`. Kết quả phụ thuộc kiểu tham số (`int` nguyên thủy khác `Integer`), chiến lược chuyển đổi/khởi tạo và quy tắc kiểm tra được cấu hình. Vì vậy không nên mặc định "thiếu dữ liệu sẽ lập tức có lỗi `required`" trong mọi constructor. Dùng kiểu thích hợp, constraint như `@NotNull` khi có provider/validation và các kiểm tra bắt buộc ở entry point phù hợp. Nếu muốn phân biệt *input thiếu* với *input không chuyển được*, hãy thiết kế rõ trách nhiệm của resolver và validation thay vì dựa vào một giá trị primitive mặc định.

## 8. So sánh construct(...) và bind(...)

Hai API thường gặp trên `DataBinder`:

```java
binder.construct(valueResolver);
binder.bind(propertyValues);
```

Ý nghĩa:

- `construct(ValueResolver)` tạo target bằng constructor, phù hợp khi target chưa tồn tại.
- `bind(PropertyValues)` cập nhật **thuộc tính có thể ghi** của target đang có, theo quy tắc property binding. `PropertyValues` là một đối tượng chứa các cặp tên/giá trị thuộc tính; `MutablePropertyValues` là một triển khai phổ biến.
- Có thể kết hợp constructor binding và property binding khi model thực sự cần cả hai, nhưng phải cân nhắc rất kỹ những trường nào được phép nhận giá trị từ client.

Ví dụ mô hình có constructor và setter:

```java
public final class TicketForm {
    private final String ticketCode;
    private String comment;

    public TicketForm(String ticketCode) {
        this.ticketCode = ticketCode;
    }

    public String getTicketCode() {
        return ticketCode;
    }

    public String getComment() {
        return comment;
    }

    public void setComment(String comment) {
        this.comment = comment;
    }
}
```

Đây là snippet về thiết kế model; nếu binder đã tạo được `TicketForm`, property binding có thể cập nhật `comment` nếu cấu hình cho phép. Với **record không có setter**, `bind(...)` không phải cách cập nhật các record components đã được constructor gán.

Không nên sử dụng property binding không giới hạn trên domain entity có các thuộc tính nhạy cảm (ví dụ `role`, `isAdmin`, `balance`). Người dùng có thể gửi các field ngoài form dự kiến để cố thay đổi những giá trị nội bộ. Constructor binding hướng tới thiết kế model nhận đúng dữ liệu đầu vào, nhưng **không tự động bảo vệ** nếu constructor của DTO phơi bày các tham số nhạy cảm.

## 9. Bảo vệ dữ liệu: declarativeBinding từ Spring 6.1

Spring Framework 6.1 có cấu hình:

```java
binder.setDeclarativeBinding(true);
```

Mục đích là giới hạn binder vào những trường được chủ động cho phép:

- **Constructor binding** thông qua `construct(...)` vẫn được hỗ trợ.
- **Property binding** chỉ thực hiện với các field đã được cho phép, khi cấu hình `setAllowedFields(...)` phù hợp.
- Nếu bật declarative binding nhưng **không** thiết lập allowed fields, Spring không tự động bind mọi setter của object chỉ vì request chứa key cùng tên.

Ví dụ ý tưởng:

```java
binder.setDeclarativeBinding(true);
binder.setAllowedFields("comment");
```

Đây là snippet đặt trong cấu hình binder cho một model có thuộc tính `comment`, không phải chương trình độc lập. Nó cho phép chủ động phân ranh giới: constructor nhận các tham số cần thiết, setter chỉ được cập nhật với field đã allowlist. Khi chỉ dùng constructor binding, có thể bật declarative mode và không thêm allowed field cho property binding.

**Không hiểu nhầm:** `setAllowedFields(...)` là cấu hình **property binding**, không phải công tắc để Spring bỏ qua một tham số constructor đã nằm trong constructor mà ứng dụng chọn. Nếu constructor DTO nhận tham số `role` từ request, bản thân chữ ký constructor đang phơi bày khả năng nhận giá trị đó. Muốn an toàn, thiết kế constructor DTO với đúng những dữ liệu client được phép cung cấp, và quyết định role thực tế ở tầng nghiệp vụ/authorization.

Các biện pháp hỗ trợ:

1. Dùng DTO đầu vào chuyên biệt, tách khỏi entity chứa trạng thái nội bộ.
2. Giữ constructor chỉ nhận những trường người dùng được phép cung cấp.
3. Bật declarative binding hoặc allowlist property fields khi cần setter binding.
4. Xác thực/cấp quyền ở tầng nghiệp vụ, không dựa vào constructor binding như một cơ chế authorization.
5. Giới hạn kích thước, chiều sâu, collection/index hợp lý khi nhận dữ liệu không tin cậy.

## 10. Trong Spring MVC và WebFlux

### @ModelAttribute

Trong Spring MVC/WebFlux từ 6.1, cơ chế binding của các model attributes có thể tạo đối tượng bằng constructor thay vì đòi hỏi một JavaBean đã có sẵn. Ví dụ:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RestController;

record SearchForm(String keyword, int page) {}

@RestController
class SearchController {

    @GetMapping("/search")
    String search(@ModelAttribute SearchForm form) {
        return "keyword=" + form.keyword() + ", page=" + form.page();
    }
}
```

Đoạn này là snippet **minh họa trong ứng dụng Spring Web MVC** có cấu hình web đầy đủ. Nó không thuộc chương trình Java SE ở mục 5. Với request `GET /search?keyword=java&page=2`, một model attribute có thể được tạo bằng constructor của `SearchForm` và giá trị `page` được chuyển sang `int`. Không cần setter cho record. Nếu cần xét binding errors trong controller, có thể khai báo `BindingResult` ngay sau `@ModelAttribute`; không trông đợi mọi lỗi chuyển kiểu đều đến dưới cùng một dạng khi tham số bị thiếu.

Khi dùng `@BindParam` trong Spring MVC/WebFlux, framework có thể thay ánh xạ tên input cho constructor argument. Ví dụ `full_name` trong form được ánh xạ sang tham số `name` của DTO. Để tự sử dụng `DataBinder` mà không có web framework, bạn phải cấu hình resolver/name strategy tương ứng nếu tên input khác với tên constructor parameter.

### @RequestBody có cùng cơ chế không?

Không nên đánh đồng `@ModelAttribute` form/query binding và `@RequestBody` JSON deserialization:

- `@ModelAttribute` chủ yếu đi qua hệ thống `WebDataBinder`/model-attribute binding, hỗ trợ constructor binding được đề cập.
- `@RequestBody` đọc payload bằng `HttpMessageConverter`, chẳng hạn Jackson JSON, để tạo đối tượng. Jackson cũng có thể tạo record bằng constructor nhưng đó là **cơ chế deserialization của Jackson**, không chứng minh rằng `DataBinder.construct(...)` đã được gọi cho JSON đó.
- Sau khi một trong hai con đường tạo được object, Spring có thể kích hoạt validation qua `@Valid`/`@Validated` khi được cấu hình phù hợp.

Tách rõ đường đi của dữ liệu giúp giải thích chính xác lỗi chuyển đổi, validation, mã lỗi và thời điểm tạo target.

### Có phải dùng @Autowired cho constructor DTO?

Không. `@Autowired` là cơ chế inject dependency của Spring IoC container cho bean, còn model-attribute constructor binding đọc **request/form parameters** để tạo một object dữ liệu. Đừng thêm `@Autowired` lên constructor DTO với hy vọng nó sẽ tự lấy dữ liệu HTTP.

## 11. Tương thích phiên bản và những điểm cần kiểm tra

Constructor binding qua `DataBinder.setTargetType(...)` và `DataBinder.construct(ValueResolver)` là API được giới thiệu ở **Spring Framework 6.1**. Cần lưu ý:

- Kiểm tra Spring Framework đang chạy đúng nhánh 6.1+; chương trình Java SE ở đây sử dụng `spring-context:6.1.14`.
- Với Spring 6.x, JDK tối thiểu thường là Java 17; ví dụ sử dụng Java records và cấu hình compiler Java 17.
- Kiểm tra tên tham số constructor có thể được Spring đọc: records, `-parameters` hoặc `@ConstructorProperties` khi phù hợp.
- Trong Spring Boot, nên dùng phiên bản Spring Framework do Boot BOM quản lý thay vì tự ghim `spring-context` lệch với các module Spring khác.
- Hành vi xử lý kiểu phức tạp và các API hỗ trợ resolver có thể phát triển giữa các bản minor/patch. Ví dụ `ValueResolver.getNames()` được thêm sau bản 6.1.0, nên khi sao chép ví dụ từ nhiều tài liệu, cần so với Javadoc phiên bản thực tế.
- Không tự suy đoán constructor sẽ được chọn trong class nhiều constructor; tránh thiết kế mơ hồ.
- Nếu dùng nested constructor binding/collections, kiểm tra đúng cấu trúc key đầu vào và generic type, không ép mọi kiểu phức tạp thành chuỗi không có converter.

## 12. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Gọi `construct` khi binder đã có target | Constructor binding kỳ vọng target chưa được tạo | Bắt đầu bằng `new DataBinder(null, ...)` |
| Chưa gọi `setTargetType(...)` | Binder không biết cần tạo kiểu nào | Dùng `ResolvableType.forClass(...)` trước `construct` |
| Constructor argument nhận null dù input có giá trị | Tên constructor parameter không tìm được hoặc resolver dùng sai key | Kiểm tra `-parameters`, record metadata, `@ConstructorProperties`, `NameResolver` |
| String tuổi không đổi sang int | Không có converter/editor phù hợp hoặc giá trị không parse được | Kiểm tra `BindingResult` và conversion configuration |
| Chọn nhầm no-args constructor | Class có nhiều constructors/đường dựng không rõ ràng | Thiết kế data constructor rõ ràng; kiểm tra quy tắc lựa chọn |
| Dữ liệu lồng nhau không hiện diện | Key `address.city` sai hoặc resolver không liệt kê tên cần thiết | Kiểm tra `resolveValue`, `getNames` và nested path |
| Dùng `bind(...)` để tạo record từ null | `bind` là property binding, không phải API dựng constructor target | Dùng `setTargetType` và `construct` |
| Bỏ qua lỗi vì getTarget khác null | Object có thể đã được dựng trong một trạng thái chưa thỏa điều kiện | Kiểm tra binding errors và validation trước khi sử dụng |
| Nghĩ constructor binding tự kiểm tra `@NotBlank` | Binding và Bean Validation là hai bước khác nhau | Cấu hình validator/provider và kích hoạt validation |
| Tưởng `@RequestBody` luôn gọi DataBinder.construct | JSON body thường qua Jackson/HttpMessageConverter | Phân biệt model attribute với request body |
| Chỉ dùng field allowlist để hạn chế constructor arguments | `setAllowedFields` điều khiển property binding, không thay hợp đồng constructor | Thiết kế DTO constructor chỉ với input được phép |
| Dùng @Autowired trên form constructor | Nhầm IoC dependency injection với request data binding | Bỏ `@Autowired` khỏi DTO request |

## 13. Câu hỏi tự kiểm tra

1. Vì sao `DataBinder(null, "form")` phải được kết hợp với `setTargetType(...)` trước `construct(...)`?
2. `DataBinder.ValueResolver.resolveValue(name, type)` khác `DataBinder.NameResolver` ở nhiệm vụ nào?
3. Vì sao record `Registration(String name, int age)` thích hợp cho constructor binding?
4. Input `"21"` được chuyển sang `int` ở bước nào? Nếu nhập `"abc"`, nên kiểm tra kết quả ở đâu?
5. Tại sao gọi `construct(...)` không đồng nghĩa `@NotBlank` hoặc `@Min` đã được áp dụng?
6. `@ModelAttribute` record và `@RequestBody` JSON record đi qua hai con đường dữ liệu nào?
7. `setDeclarativeBinding(true)` ảnh hưởng property binding và constructor binding ra sao?
8. Tại sao DTO constructor nhận `isAdmin` từ user input có thể gây rủi ro dù đang dùng constructor binding?
9. Khi nested object nhận input `address.city`, resolver cần đảm bảo điều gì về đường dẫn tên?
10. Nếu đối tượng có nhiều constructors, vì sao nên kiểm tra constructor được Spring chọn?

**Ghi nhớ:** Với Spring Framework 6.1+, `DataBinder` có thể **tạo một đối tượng mới bằng constructor**. Chuỗi thao tác nền tảng là **target `null` → `setTargetType(...)` → `construct(ValueResolver)` → kiểm tra `BindingResult` → thực hiện validation nếu cần**. Cơ chế này phù hợp cho DTO bất biến và giúp giới hạn bề mặt dữ liệu đầu vào khi constructor được thiết kế cẩn thận.

## Tài liệu tham khảo

- Spring Framework 6.1 — Data Binding, Constructor Binding: https://docs.spring.io/spring-framework/reference/6.1/core/validation/beans-beans.html
- Spring Framework 6.1 — DataBinder Javadoc: https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.1 — DataBinder.ValueResolver Javadoc: https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.ValueResolver.html
- Spring Framework 6.1 Release Notes: https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes
- Spring Framework — Model Design for web data binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
