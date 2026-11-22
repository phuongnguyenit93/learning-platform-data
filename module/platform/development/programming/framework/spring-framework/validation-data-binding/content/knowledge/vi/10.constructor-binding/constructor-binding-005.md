# Lựa chọn constructor và thông tin tên tham số trong Spring constructor binding

## 1. Mục tiêu

**Constructor binding** là cơ chế Spring tạo một đối tượng đầu vào bằng cách chọn constructor, tìm giá trị nguồn theo **tên tham số**, chuyển kiểu, sau đó gọi constructor. Cơ chế này rất hữu ích cho request DTO, form object bất biến và Java record.

Ví dụ nguồn gửi:

```text
attendee=Lan
seats=2
```

Đối tượng đích:

```java
public record BookingForm(String attendee, int seats) {}
```

Spring phải giải quyết ba câu hỏi riêng: **constructor nào**, **tham số tên gì**, và **chuỗi đầu vào đổi sang kiểu tham số thế nào**. Nếu chọn đúng constructor nhưng không nhận diện tên `attendee`, `seats` thì framework vẫn không có đủ thông tin ghép dữ liệu.

Hai cơ chế khác thường bị nhầm với bài này:

- **Dependency injection:** Spring tạo các bean `@Service`, `@Component` từ dependency qua constructor (thường liên quan `@Autowired`). Nguồn dữ liệu là container, không phải HTTP input.
- **JSON deserialization:** `@RequestBody` thường dùng Jackson, có quy tắc chọn constructor/creator và annotation riêng như `@JsonCreator`, `@JsonProperty`. Không được áp mặc định quy tắc ấy cho `@ModelAttribute`.
- **Constructor data binding:** `DataBinder.construct(...)` hoặc cơ chế `@ModelAttribute` của MVC lấy giá trị từ request hay `ValueResolver`, không tự lấy service từ IoC container.

Mục tiêu thực hành là biết chọn một data constructor rõ ràng, giữ tên tham số trong bytecode, sử dụng `@ConstructorProperties` hoặc `@BindParam` khi tên nguồn khác tên Java, và biết các trường hợp dễ lỗi do overload hoặc setter binding ngoài ý muốn.

## 2. Luồng xử lý: chọn constructor trước, phân giải tên sau

```text
HTTP form / nguồn ValueResolver:
    attendee="Lan"
    seats="2"
          |
          v
DataBinder xác định target type
          |
          v
Chọn constructor hợp lệ
    (String attendee, int seats)
          |
          v
Đọc tên từng tham số
    ["attendee", "seats"]
          |
          v
Tra giá trị theo tên
    "Lan", "2"
          |
          v
ConversionService / PropertyEditor
    String "2" -> int 2
          |
          v
new BookingForm("Lan", 2)
          |
          v
BindingResult: lỗi nếu binding thất bại
          |
          v
Validator (nếu được kích hoạt)
          |
          v
Controller / use case
```

Điểm quan trọng: tên thuộc tính nhận qua constructor **không nhất thiết trùng** với field hay setter của class. Spring cần metadata của **constructor parameter**. Ngược lại, property binding dùng tên property/đường dẫn và setter hoặc cơ chế field access.

| Câu hỏi | Constructor binding | Property binding |
| --- | --- | --- |
| Đối tượng đã tồn tại? | Thường chưa, cần tạo mới | Đã có |
| Điểm gán giá trị | Constructor arguments | Setter / field |
| Tên được tra | Tên parameter hoặc tên được ánh xạ | Tên property |
| Class phù hợp | Record, immutable DTO, data constructor | JavaBean có setter |
| Nguồn lỗi | Constructor selection, tên parameter, conversion | Setter/property path, conversion |
| An toàn đầu vào | Tốt khi chỉ khai báo tham số được phép nhập | Nên giới hạn `allowedFields` |

Trong Spring MVC, mặc định framework có thể thực hiện **cả constructor binding lẫn property binding**. Vì vậy chỉ định nghĩa một constructor không đồng nghĩa mọi setter ngoài constructor sẽ bị vô hiệu hóa. Muốn hạn chế setter binding, xem phần 9 về `declarativeBinding`.

## 3. Quy tắc chọn constructor

### 3.1. Một constructor có tham số: trường hợp nên ưu tiên

```java
public final class CreateOrderForm {
    private final String customer;
    private final int quantity;

    public CreateOrderForm(String customer, int quantity) {
        this.customer = customer;
        this.quantity = quantity;
    }

    public String getCustomer() { return customer; }
    public int getQuantity() { return quantity; }
}
```

Khi class có **một public data constructor**, Spring có mục tiêu rõ ràng cho constructor binding. Hạ tầng cũng có thể nhận một **constructor không public duy nhất có tham số** nếu reflection/access cho phép. Tuy nhiên, để API dễ hiểu và tránh rắc rối Java modules/native image, DTO web thông thường nên có một constructor dữ liệu rõ ràng.

Khác với setter binding, không bắt buộc có constructor không tham số. Các field có thể là `final`, không có setter.

### 3.2. Nhiều constructor và constructor mặc định

```java
public class OrderForm {
    private String customer;

    public OrderForm() {}

    public OrderForm(String customer) {
        this.customer = customer;
    }

    public String getCustomer() { return customer; }
    public void setCustomer(String customer) { this.customer = customer; }
}
```

Nếu có **nhiều constructor**, Spring constructor resolution có thể chọn **default/no-args constructor** nếu có. Hệ quả:

- Đối tượng có thể được tạo bằng constructor rỗng.
- Nếu property binding tiếp tục được cho phép, setter có thể điền `customer`.
- Nếu cấu hình **chỉ constructor binding** và không có property binding, `customer` có thể vẫn `null`.

Không nên suy luận “constructor dài nhất thắng”. Với nhiều constructor có tham số nhưng không có lựa chọn primary/single/default rõ ràng, thiết kế dễ mơ hồ hoặc lỗi. Dùng record hoặc một DTO với duy nhất data constructor sẽ ít bất ngờ hơn.

### 3.3. Java record và canonical constructor

```java
public record OrderForm(String customer, int quantity) {}
```

Record công bố các components `customer` và `quantity` cùng **canonical constructor** tương ứng. Spring có thể dùng constructor này cho dữ liệu đầu vào; không cần setter. Record có thể có constructor phụ hoặc compact constructor, nhưng thiết kế DTO dễ nhất vẫn là một canonical contract rõ ràng.

Với Kotlin data class, Spring cũng có hỗ trợ primary constructor; cần chú ý Kotlin metadata, reflection và cấu hình phiên bản thư viện. Đừng áp máy móc quy tắc getter/setter JavaBean cho record hoặc Kotlin data class.

### 3.4. Phân biệt constructor của bean DI

```java
// Snippet minh họa cho dependency injection, không phải class hoàn chỉnh.
@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
```

Constructor này nhận `OrderRepository` do Spring container cung cấp. Nó **không** ghép tham số request `repository=...` như `DataBinder.construct(...)`. Các quy tắc `@Autowired`/constructor injection và quy tắc data constructor là hai ngữ cảnh khác nhau.

## 4. Tại sao tên tham số constructor quan trọng?

Đoạn Java sau nhìn thấy tên rất rõ trong source:

```java
public CreateOrderForm(String customer, int quantity) {
    // ...
}
```

Nhưng JVM không nhất thiết giữ những tên đó trong bytecode của **class Java thông thường**. Nếu chỉ còn kiểu `String`, `int` và thứ tự tham số thì Spring không thể biết request key `customer` tương ứng với tham số nào mà không có metadata tên đáng tin cậy.

Java Reflection cung cấp:

- `Constructor.getParameters()`: danh sách `Parameter`.
- `Parameter.getName()`: tên mà reflection biết.
- `Parameter.isNamePresent()`: tên thực có được lưu trong metadata hay không.

Nếu thiếu metadata, reflection có thể trả tên giả như `arg0`, `arg1`, và `isNamePresent() == false`. Đây **không** phải hợp đồng input có ý nghĩa. Không nên yêu cầu client gửi field `arg0` để “sửa” việc thiếu tên.

## 5. Giữ tên tham số với -parameters

Với `javac`:

```bash
javac -parameters CreateOrderForm.java
```

Khi dùng Maven và Java 17, có thể cấu hình compiler plugin:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Đây chỉ là **đoạn plugin Maven**, cần đặt trong `project/build/plugins` của POM thật.

Code kiểm tra metadata:

```java
// Snippet; cần import java.lang.reflect.Constructor, Parameter
Constructor<?> c = CreateOrderForm.class.getDeclaredConstructors()[0];
for (Parameter p : c.getParameters()) {
    System.out.println(p.getName() + ": " + p.isNamePresent());
}
```

Với bytecode biên dịch có `-parameters`, kỳ vọng:

```text
customer: true
quantity: true
```

**Lưu ý:**

- Bật option trên **module thực sự biên dịch DTO**, không chỉ module chạy Spring MVC. Nếu DTO nằm trong một JAR được build riêng, cần biên dịch lại JAR ấy.
- `-g` (debug info) không phải một sự thay thế đáng tin cậy cho `-parameters` trong Spring hiện đại.
- IDE có thể chạy bytecode khác với bản đã đóng gói; kiểm tra cấu hình Maven/Gradle và `mvn clean compile` thay vì chỉ đọc source.
- `javap -v` cho phép xem phần metadata `MethodParameters` nếu cần chẩn đoán.
- Record giữ tên canonical components theo đặc trưng của record, nhưng bật option cho toàn bộ codebase vẫn hữu ích vì có các class thường.

## 6. @ConstructorProperties: tên logic khác tên biến Java

JDK cung cấp `java.beans.ConstructorProperties`. Spring `BeanUtils.getParameterNames(Constructor<?>)` xét annotation này khi có:

```java
import java.beans.ConstructorProperties;

public final class LegacyOrderForm {
    private final String customer;
    private final int quantity;

    @ConstructorProperties({"customer", "quantity"})
    public LegacyOrderForm(String buyer, int count) {
        this.customer = buyer;
        this.quantity = count;
    }

    public String getCustomer() { return customer; }
    public int getQuantity() { return quantity; }
}
```

Tên biến trong Java source là `buyer` và `count`, nhưng annotation khai báo tên logic `customer`, `quantity` cho constructor arguments **theo thứ tự**. Nếu input map có hai key đó, Spring có thể ghép đúng giá trị ngay cả khi tên biến Java khác.

Điều kiện quan trọng:

1. Số tên trong annotation phải bằng số tham số constructor.
2. Thứ tự tên phải trùng thứ tự tham số.
3. Tên là hợp đồng dữ liệu; đổi tên hoặc thứ tự mà không cập nhật request/test có thể phá binding.
4. Annotation này không cung cấp validation, conversion, authentication hay authorization.
5. Trong class có nhiều constructor, annotation đặt tên **không đồng nghĩa** framework chắc chắn sẽ chọn đúng constructor mình mong muốn; vẫn phải xem quy tắc constructor resolution.

Ví dụ hai tham số `(String buyer, int count)` nhưng khai báo `{"quantity", "customer"}` là sai thứ tự: Spring có thể cố chuyển email/tên thành số hoặc gán sai dữ liệu.

## 7. @BindParam và DataBinder.NameResolver trong Spring MVC

Khi tên input bên ngoài khác quy ước Java, ví dụ:

```text
attendee-name=Lan
quantity=2
```

Spring MVC và WebFlux hỗ trợ `@BindParam` để đổi tên request parameter:

```java
import org.springframework.web.bind.annotation.BindParam;

public record BookingForm(
        @BindParam("attendee-name") String attendeeName,
        int quantity) {}
```

Đối với model attribute, key `attendee-name` được dùng cho tham số constructor Java `attendeeName`. Có thể đặt `@BindParam` trên constructor parameter hoặc field tương ứng theo cơ chế framework.

**Giới hạn quan trọng:** `@BindParam` là name mapping của constructor binding trong Spring MVC/WebFlux. Nếu tự tạo `DataBinder` thuần túy ngoài web, không nên mặc nhiên trông chờ annotation được xử lý y như MVC. `DataBinder` cho phép cài một `NameResolver` tùy chỉnh khi cần:

```java
// Snippet minh họa; binder là DataBinder đã được tạo.
binder.setNameResolver(parameter -> {
    // Có thể đọc annotation trên MethodParameter.
    // Trả null để Spring tiếp tục tra tên mặc định.
    return null;
});
```

Ở đây lambda chỉ minh họa chữ ký của resolver, chưa thực hiện chuyển tên. Một resolver có ý nghĩa cần định nghĩa rõ quy tắc đổi tên, xử lý đụng tên và đường dẫn lồng nhau.

| Nhu cầu | Giải pháp thường dùng |
| --- | --- |
| Java record với tên component trùng input | Canonical constructor |
| Class thường với tên Java trùng input | `-parameters` |
| Constructor do thư viện cũ tạo, tên Java khác | `@ConstructorProperties` khi phù hợp |
| Form HTTP dùng `first-name` nhưng Java dùng `firstName` | `@BindParam("first-name")` trong MVC |
| Binder tự tạo với quy ước tên riêng | `DataBinder.NameResolver` |
| JSON `@RequestBody` cần custom creator/property | Cấu hình Jackson, không dùng `@BindParam` thay thế |

Phân biệt kỹ **tên tham số dùng để bind** với tên field của database, tên JSON property và tên biến Java ở lúc debug.

## 8. Ví dụ chạy được: Spring DataBinder.construct và metadata constructor

Ví dụ sau dùng **Java 17**, **Spring Framework 6.2.6**, Maven, không yêu cầu web server hay database. Nó minh họa record, class có `@ConstructorProperties` và class có hai constructor trong cùng một chương trình.

### 8.1. Cấu trúc

```text
constructor-binding-demo/
├── pom.xml
└── src/main/java/demo/ConstructorBindingDemo.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>constructor-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ConstructorBindingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. src/main/java/demo/ConstructorBindingDemo.java

```java
package demo;

import java.beans.ConstructorProperties;
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;
import java.util.Arrays;
import java.util.Map;
import java.util.Set;

import org.springframework.beans.BeanUtils;
import org.springframework.core.ResolvableType;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class ConstructorBindingDemo {

    public record MemberRequest(String name, int seats) {
    }

    public static final class LegacyRequest {
        private final String email;
        private final int seats;

        @ConstructorProperties({"contact-email", "seats"})
        public LegacyRequest(String email, int seats) {
            this.email = email;
            this.seats = seats;
        }

        public String getEmail() {
            return email;
        }

        public int getSeats() {
            return seats;
        }
    }

    public static final class HybridRequest {
        public HybridRequest() {
        }

        public HybridRequest(String name) {
        }
    }

    private static <T> T construct(
            Class<T> targetType, Map<String, String> values) {

        DataBinder binder = new DataBinder(null, "request");
        binder.setTargetType(ResolvableType.forClass(targetType));
        binder.setDeclarativeBinding(true);

        binder.construct(new DataBinder.ValueResolver() {
            @Override
            public Object resolveValue(String name, Class<?> type) {
                return values.get(name);
            }

            @Override
            public Set<String> getNames() {
                return values.keySet();
            }
        });

        BindingResult result = binder.getBindingResult();
        if (result.hasErrors() || binder.getTarget() == null) {
            throw new IllegalStateException(
                    "Cannot construct " + targetType.getSimpleName());
        }

        return targetType.cast(binder.getTarget());
    }

    private static String[] reflectionNames(Constructor<?> constructor) {
        return Arrays.stream(constructor.getParameters())
                .map(Parameter::getName)
                .toArray(String[]::new);
    }

    public static void main(String[] args) {
        Constructor<?> recordCtor =
                BeanUtils.getResolvableConstructor(MemberRequest.class);
        System.out.println("record.parameters=" +
                recordCtor.getParameterCount());
        System.out.println("record.names=" +
                Arrays.toString(BeanUtils.getParameterNames(recordCtor)));

        MemberRequest member = construct(
                MemberRequest.class,
                Map.of("name", "Lan", "seats", "3"));

        System.out.println("member.name=" + member.name());
        System.out.println("member.seats=" + member.seats());

        Constructor<?> legacyCtor =
                BeanUtils.getResolvableConstructor(LegacyRequest.class);
        System.out.println("legacy.reflect.names=" +
                Arrays.toString(reflectionNames(legacyCtor)));
        System.out.println("legacy.spring.names=" +
                Arrays.toString(BeanUtils.getParameterNames(legacyCtor)));
        System.out.println("legacy.namesPresent=" +
                legacyCtor.getParameters()[0].isNamePresent());

        LegacyRequest legacy = construct(
                LegacyRequest.class,
                Map.of("contact-email", "lan@example.com", "seats", "2"));

        System.out.println("legacy.email=" + legacy.getEmail());
        System.out.println("legacy.seats=" + legacy.getSeats());

        Constructor<?> hybridCtor =
                BeanUtils.getResolvableConstructor(HybridRequest.class);
        System.out.println("hybrid.parameters=" +
                hybridCtor.getParameterCount());
    }
}
```

Mã này dùng `DataBinder.ValueResolver`, với hai phương thức trong Spring 6.2:

- `resolveValue(String name, Class<?> type)` tìm giá trị từ nguồn. Ở đây trả chuỗi từ `Map`.
- `getNames()` trả danh sách key nguồn để binder có thể nhận diện cấu trúc, đặc biệt khi có nested paths.

`setTargetType(...)` xác định class cần tạo vì `DataBinder(null, ...)` chưa có target. `construct(...)` chọn constructor, ghép tên tham số và chuyển chuỗi như `"3"` sang `int 3`. Sau đó `getBindingResult()` cho biết có lỗi binding không. Đặt `setDeclarativeBinding(true)` không làm ngưng constructor binding; cờ này hữu ích nếu sau đó còn có bước property binding trong MVC.

### 8.4. Chạy

Trong thư mục `constructor-binding-demo`, có JDK 17+ và Maven:

```bash
mvn -q clean compile exec:java
```

**Stdout dự kiến của chương trình:**

```text
record.parameters=2
record.names=[name, seats]
member.name=Lan
member.seats=3
legacy.reflect.names=[email, seats]
legacy.spring.names=[contact-email, seats]
legacy.namesPresent=true
legacy.email=lan@example.com
legacy.seats=2
hybrid.parameters=0
```

Giải thích:

1. `MemberRequest` là record có canonical constructor hai tham số `name`, `seats`.
2. `LegacyRequest` được biên dịch với `-parameters`, nên Java reflection thấy tên `email`, `seats`; nhưng `BeanUtils.getParameterNames` ưu tiên annotation `@ConstructorProperties({"contact-email", "seats"})`.
3. Bản đồ input sử dụng `contact-email` thay vì `email`. `getEmail()` vẫn trả đúng giá trị bên trong.
4. `HybridRequest` có hai constructor public, trong đó có một no-args constructor. Cơ chế `getResolvableConstructor` chọn no-args constructor.
5. Spring chuyển số ghế từ chuỗi sang `int`; không phải code người dùng gọi `Integer.parseInt` trong chương trình.

Stdout trên được suy ra từ mã và quy tắc API; cần đối chiếu khi thực chạy. Bài này không tuyên bố đã biên dịch hoặc chạy test trong môi trường dự án.

### 8.5. Nếu chuyển kiểu thất bại

Thử thay bản đồ của `MemberRequest` bằng:

```java
Map.of("name", "Lan", "seats", "abc")
```

Đây chỉ là snippet thay thế giá trị trong chương trình. `"abc"` không phải số nguyên, nên binder ghi nhận lỗi conversion, thường có mã cơ sở `typeMismatch`. Hàm `construct` minh họa sẽ thấy `result.hasErrors()` và ném `IllegalStateException`. Khi đã đổi input sang lỗi, **stdout hợp lệ ở phần 8.4 không còn đúng**.

Trong ứng dụng thực, cần trả lỗi nhập liệu cho người dùng qua `BindingResult` hoặc exception handler, không gửi stack trace nội bộ.

## 9. Tích hợp với Spring MVC @ModelAttribute

Spring MVC lấy giá trị từ form/query/path/header theo cơ chế `@ModelAttribute`, khởi tạo object bằng constructor khi phù hợp rồi có thể tiếp tục property binding.

Ví dụ dưới đây là **snippet controller**, không phải một class độc lập:

```java
// Cần Spring MVC, Bean Validation provider và import tương ứng.
public record BookingForm(
        @BindParam("attendee-name")
        @jakarta.validation.constraints.NotBlank String attendeeName,
        @jakarta.validation.constraints.Min(1) int seats) {
}

@PostMapping(path = "/bookings",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public ResponseEntity<?> create(
        @Valid @ModelAttribute("bookingForm") BookingForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "Invalid booking form"));
    }

    return ResponseEntity.ok(Map.of(
            "attendee", form.attendeeName(),
            "seats", form.seats()));
}
```

Cấu trúc request minh họa:

```http
POST /bookings HTTP/1.1
Content-Type: application/x-www-form-urlencoded

attendee-name=Lan&seats=2
```

Với dữ liệu hợp lệ, JSON body logic:

```json
{"attendee":"Lan","seats":2}
```

`@BindParam("attendee-name")` giải quyết khác biệt giữa tên input `attendee-name` và tham số Java `attendeeName`. `BindingResult` phải đứng **ngay sau** tham số `@Valid @ModelAttribute` tương ứng nếu controller muốn tự xử lý lỗi chuyển kiểu và validation. Validation cần một Bean Validation provider phù hợp trong runtime.

Đừng nhầm `@ModelAttribute` với `@RequestBody`:

| `@ModelAttribute` | `@RequestBody` |
| --- | --- |
| Bind form/query và nguồn MVC vào model attribute | Đọc body qua HttpMessageConverter, thường Jackson cho JSON |
| Có constructor/property binding theo MVC | Jackson có quy tắc creator riêng |
| `@BindParam` có thể đổi tên request parameter | Không mặc định áp `@BindParam` vào JSON key |
| `BindingResult` có thể đứng sau attribute | Lỗi JSON syntax/deserialization có thể xảy ra trước validation và cần xử lý khác |

## 10. Chỉ cho phép constructor binding khi cần

Tạo object bằng constructor **không tự động khóa tất cả setters**. Xem class:

```java
public class CreateUserForm {
    private final String email;
    private String role;

    public CreateUserForm(String email) {
        this.email = email;
    }

    public String getEmail() { return email; }
    public String getRole() { return role; }
    public void setRole(String role) { this.role = role; }
}
```

Nếu property binding vẫn được áp dụng, request gửi `role=ADMIN` **có thể** gọi `setRole` dù constructor chỉ nhận `email`. Khi muốn cấu hình declarative binding trong MVC:

```java
// Snippet trong @Controller hoặc @ControllerAdvice.
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
}
```

Cờ này luôn cho phép constructor binding, và chỉ cho phép property binding khi đã cấu hình `allowedFields` phù hợp. Nếu cần setter binding cho một số field, khai báo cụ thể:

```java
@InitBinder
void initBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields("comment");
}
```

Đoạn cuối là ví dụ về policy, giả sử object thực có property `comment` hợp lệ. `allowedFields` chủ yếu giới hạn **property binding**; không phải bộ lọc cho tất cả tham số constructor. Vì vậy một form constructor có tham số `role` nhạy cảm vẫn không tự an toàn nếu client có thể gửi `role`. Cần DTO riêng cho tác vụ, thiết kế constructor chỉ chứa input hợp lệ và service kiểm tra quyền.

Nguyên tắc bảo mật: **“Có tham số constructor hoặc setter” không đồng nghĩa “client có quyền cập nhật trường đó.”** ID, trạng thái, giá tiền, quyền, trường audit thường phải lấy hoặc tính ở phía server.

## 11. Khi constructor binding lỗi, kiểm tra theo trình tự nào?

1. **Constructor được chọn:** Có đúng một data constructor không? Có constructor rỗng khác chen vào không? Có overload gây mơ hồ không?
2. **Metadata tên:** `Constructor.getParameters()` trả tên gì? `Parameter.isNamePresent()` có true không? `BeanUtils.getParameterNames` trả ra tên gì?
3. **Cấu hình build:** Bật `-parameters` cho module chứa DTO chưa? Đã clean/rebuild JAR chưa?
4. **Annotation tên:** `@ConstructorProperties` có đúng số phần tử và thứ tự không? `@BindParam` có khớp key thực của request không?
5. **Conversion:** String số/ngày có chuyển được sang kiểu Java không? Có `ConversionService`/formatter cần thiết không?
6. **Field thiếu:** Dùng kiểu primitive hay reference? Quy tắc null/required là gì? Có validation sau binding không?
7. **Nested objects:** Target lồng nhau có data constructor hợp lệ không? Tên nguồn có đúng dạng `address.city` không?
8. **Setter binding sau constructor:** Có field ngoài ý muốn bị gán không? Cần `setDeclarativeBinding(true)` hoặc `allowedFields` không?
9. **HTTP khác JSON:** Lỗi có thật sự ở `@ModelAttribute` hay do Jackson của `@RequestBody`?
10. **Giới hạn ràng buộc:** Có giới hạn kích cỡ request, nested depth, số phần tử list và kiểm tra quyền server không?

### Lỗi phổ biến và cách xử lý

| Tình huống | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Không tra được tham số `customer` | Thiếu tên trong bytecode | Bật `-parameters` hoặc annotation tên phù hợp |
| Thấy `arg0` và `arg1` | Java reflection không có tên thật | Rebuild và kiểm tra metadata |
| Chọn constructor rỗng | Có nhiều constructor, no-args là lựa chọn | Dùng một data constructor hoặc record |
| Tên request `first-name` không map sang `firstName` | Hợp đồng tên khác | Dùng `@BindParam` trong MVC |
| Giá trị số không parse được | Type mismatch | Xem `BindingResult`, cấu hình converter/formatter |
| Tham số `Integer` bị null | Client không gửi hoặc tên lookup không khớp | Kiểm tra input key và `@NotNull` |
| Constructor viết trong source đổi thứ tự | `@ConstructorProperties` không được cập nhật | Sửa đúng thứ tự và viết test |
| DTO có setter `role` bị bind | Property binding vẫn chạy | DTO riêng + declarative binding |
| `@Autowired` không giúp bind HTTP form | Sai cơ chế | Phân biệt dependency injection với data binding |
| `@JsonProperty` không ảnh hưởng @ModelAttribute | Annotation phục vụ Jackson | Dùng metadata của constructor binder |
| Validation không xuất hiện | Chưa bật/đăng ký validator | Dùng `@Valid` và Bean Validation provider hoặc gọi `binder.validate()` |
| Legacy class dùng Lombok/codegen | Constructor thật khác source đang nhìn | Xem bytecode/runtime reflection và build config |

## 12. Đối tượng lồng nhau và collections

Spring constructor binding còn có thể đệ quy dựng đối tượng lồng nhau:

```java
public record AddressForm(String city, String zipCode) {}

public record CheckoutForm(
        String customer,
        AddressForm address) {}
```

Nguồn dữ liệu:

```text
customer=Lan
address.city=Hue
address.zipCode=530000
```

Nếu đủ metadata và kiểu hợp lệ, binder có thể tạo `AddressForm` rồi truyền vào constructor `CheckoutForm`. Tương tự, list/map/array có thể nhận key theo indexed/mapped syntax như `items[0].sku` hoặc `accounts[KEY].name`.

Nhưng cần phân biệt **khả năng hỗ trợ cú pháp** với **bảo đảm mọi input đều tạo được object**. Constructor lồng nhau có thể không hợp lệ, input thiếu dữ liệu, conversion lỗi hoặc cấu trúc quá lớn. Với dữ liệu từ client, cần giới hạn số phần tử, độ sâu và kích thước request; đừng cho phép xây dựng một object graph tùy ý.

## 13. Kiểm thử và tự đánh giá

Bộ test nên có ít nhất các tình huống:

- Class một public constructor với bytecode giữ `-parameters`; ghép tên đúng.
- Record canonical constructor có tên component đúng.
- Class có `@ConstructorProperties`, tên logic khác tên biến Java.
- Class có no-args và data constructor; xác nhận lựa chọn thực.
- Missing parameter, `null` và sai kiểu (ví dụ `seats=abc`).
- Form HTTP dùng `@BindParam("attendee-name")` và input chính xác `attendee-name`.
- Object lồng nhau và danh sách có giới hạn kích thước.
- Constructor có dữ liệu hợp lệ nhưng bean validation không đạt.
- Request thêm trường `role` hoặc `price` không được phép.
- Đổi compiler flags/annotation và test hồi quy tên tham số.

**Câu hỏi 1:** Tại sao không chọn constructor dựa trên số lượng tham số? Vì Spring dùng quy tắc primary/single/default; constructor dài nhất không phải một hợp đồng chung.

**Câu hỏi 2:** Có tên tham số trong source Java rồi, có cần `-parameters` không? Đối với class Java thông thường, thường cần bật option này hoặc nguồn metadata thay thế để Spring đọc tên đáng tin cậy ở runtime.

**Câu hỏi 3:** `@ConstructorProperties` làm gì? Nó ánh xạ **tên logic theo thứ tự tham số constructor**; không tự chọn constructor, convert hay validate.

**Câu hỏi 4:** `@BindParam` có tác dụng với mọi `@RequestBody` JSON không? Không. Nó hỗ trợ name mapping cho constructor binding của MVC/WebFlux; JSON thường thuộc Jackson.

**Câu hỏi 5:** Dùng record có loại bỏ hoàn toàn vấn đề mass assignment không? Không. Record chỉ bảo vệ cấu trúc khỏi setter binding thông thường; nếu constructor có trường nhạy cảm và client được phép gửi trường đó, bảo mật vẫn sai ở mức hợp đồng.

**Câu hỏi 6:** Khi `@ModelAttribute` có `BindingResult`, đặt ở đâu? Ngay sau tham số model attribute liên quan.

## 14. Checklist áp dụng

1. Xác định tác vụ và đúng các trường client được phép gửi.
2. Chọn record hoặc một data constructor duy nhất dễ hiểu.
3. Quyết định metadata tên: record, `-parameters`, `@ConstructorProperties` hoặc `@BindParam` phù hợp.
4. Đối chiếu tên input, kiểu tham số, optional/required, nested paths.
5. Nếu dùng `DataBinder.construct(...)` thủ công: khởi tạo target `null`, đặt `targetType`, cung cấp `ValueResolver`, kiểm tra `BindingResult`.
6. Trong Spring MVC: dùng `@ModelAttribute`, validation và xử lý lỗi đúng; cân nhắc bật `declarativeBinding`.
7. Giới hạn property binding và tuyệt đối không lấy quyền/giá/trạng thái từ request nếu nghiệp vụ không cho phép.
8. Test metadata bytecode thực, constructor selection, sai kiểu, thiếu trường, overposting và các thay đổi contract.

**Kết luận:** Constructor binding hoạt động chính xác khi Spring **chọn được constructor phù hợp** và **đọc được tên từng tham số** để tìm giá trị đầu vào. Biên dịch với `-parameters`, dùng metadata tên rõ ràng và thiết kế DTO theo tác vụ giúp tránh phần lớn lỗi khó phát hiện.

## 15. Tài liệu chính thức

- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): constructor selection, tên tham số và nested constructor binding.
- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): constructor của model attribute, `@BindParam` và `BindingResult`.
- [Spring MVC — Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html): constructor/property binding, `declarativeBinding`, `allowedFields`.
- [Spring MVC — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html): cấu hình WebDataBinder trong controller.
- [Spring Javadoc — BeanUtils](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/beans/BeanUtils.html): `getResolvableConstructor` và `getParameterNames`.
- [Spring Javadoc — DataBinder](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/DataBinder.html): `construct`, `ValueResolver`, `NameResolver`.
- [JDK 17 — java.lang.reflect.Parameter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html): tên runtime và `isNamePresent()`.
- [JDK 17 — java.beans.ConstructorProperties](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/ConstructorProperties.html): chú thích danh sách tên theo vị trí.
