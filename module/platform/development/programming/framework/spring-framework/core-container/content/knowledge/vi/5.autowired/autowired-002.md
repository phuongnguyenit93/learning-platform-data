# Lớp có một hàm khởi tạo không cần ghi `@Autowired`

## 1. Quy tắc cốt lõi của Spring

Trong Spring Framework hiện đại (từ **Spring Framework 4.3**), khi một class được Spring quản lý dưới dạng **bean** và class đó chỉ có **một constructor**, Spring có thể chọn chính constructor ấy để tạo bean và tự giải quyết các tham số dependency của nó. **Không cần đặt `@Autowired` lên constructor duy nhất.**

Ví dụ:

~~~java
public final class OrderService {
    private final PriceCalculator calculator;

    public OrderService(PriceCalculator calculator) {
        this.calculator = calculator;
    }
}
~~~

Đoạn trên chỉ minh họa: `PriceCalculator` cần được định nghĩa và đăng ký trong context. Spring có thể thấy constructor `OrderService(PriceCalculator)`, tìm bean `PriceCalculator` phù hợp rồi gọi constructor. Nếu mọi tham số đều thỏa mãn, `OrderService` được tạo mà không cần `@Autowired`.

**Điều kiện quan trọng nhất:** `OrderService` phải thực sự được **đăng ký để container tạo/quản lý**. Việc một class có đúng một constructor không tự khiến nó xuất hiện trong Spring ApplicationContext.

~~~text
Class Java có đúng một constructor
            |
            +-- Object do Spring tạo qua bean definition
            |       |
            |       +-- Spring chọn constructor duy nhất
            |       +-- Spring tìm bean cho các tham số
            |       +-- Spring gọi constructor
            |       +-- Object trở thành managed bean
            |
            +-- Object do người dùng gọi new
                    |
                    +-- Java chỉ gọi constructor với các argument
                        mà chính người dùng đã truyền
                    +-- Không tự lookup bean / autowire
~~~

Quy tắc này làm mã constructor injection **gọn hơn**, chứ không thay đổi bản chất của Dependency Injection: service khai báo dependency và nhận implementation từ bên ngoài.

## 2. Phải phân biệt “có một constructor” với “được Spring đăng ký”

Một constructor Java bình thường:

~~~java
public CheckoutService(InventoryPort inventory) {
    this.inventory = java.util.Objects.requireNonNull(inventory);
}
~~~

là đủ biểu diễn **dependency bắt buộc**. Nhưng container chỉ xử lý nó khi class được đưa vào bean graph theo một con đường hợp lệ.

### Ba cách đăng ký phổ biến

| Cách | Spring biết class bằng cách nào? | Ai thực sự gọi constructor? |
| --- | --- | --- |
| `@Component` và component scanning | Scan package rồi phát hiện component | Spring thực hiện bean instantiation |
| `AnnotationConfigApplicationContext.register(MyService.class)` | Code đăng ký bean class tường minh | Spring thực hiện bean instantiation |
| `@Bean MyService service(Dependency d) { return new MyService(d); }` | Factory method cung cấp object | Chính body `@Bean` gọi constructor, tham số factory được Spring inject |

**Lưu ý ở dòng `@Bean`:** nếu code factory method viết `return new MyService(d);`, Spring không tự động “chọn constructor của `MyService`” ở bước đó. Spring giải quyết **tham số của phương thức factory** `service(Dependency d)`; còn chính phương thức Java gọi `new MyService(d)`. Điều này vẫn là DI, nhưng không phải ví dụ trực tiếp chứng minh quy tắc chọn constructor duy nhất của class bean.

**Không bắt buộc có `@Component`:** class có thể giữ hoàn toàn thuần Java nếu được đăng ký tường minh bằng `register(...)`, hoặc instance được tạo bằng `@Bean`.

### Ví dụ component scanning

~~~java
@Component
public class ReportService {
    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }
}
~~~

Đây là **trích đoạn minh họa**, không chạy độc lập vì còn cần import `Component`, định nghĩa `ReportRepository` và bật component scanning. Khi container phát hiện `ReportService`, constructor duy nhất được dùng cho injection mà không đòi annotation `@Autowired`. Nếu không có bean `ReportRepository`, bean creation sẽ thất bại.

### Ví dụ đăng ký class trực tiếp

~~~java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

context.register(AppConfig.class, ReportService.class);
context.refresh();
ReportService service = context.getBean(ReportService.class);
context.close();
~~~

Đây cũng là **mã minh họa**: cần khai báo các class và import Spring thích hợp. Trong phần ứng dụng chạy được ở mục 5, ta dùng chính cách đăng ký này để loại bỏ khả năng nhầm với cơ chế `@Bean` tạo service.

## 3. Vì sao constructor injection phù hợp với dependency bắt buộc?

So với field injection hoặc setter injection, constructor mang những lợi ích thiết kế rõ:

- **Dependency hiện ngay ở public API của class:** chỉ cần đọc constructor là thấy service cần collaborator gì.
- **Fail sớm:** thiếu dependency cần thiết sẽ khiến Spring không tạo được bean; khi dùng Java thuần, code buộc phải cung cấp argument.
- **Có thể dùng `final` fields:** các reference cần thiết được gán một lần khi tạo object, không bị gán lại qua setter thông thường.
- **Test Java thuần đơn giản:** tạo fake implementation và truyền vào constructor, không cần khởi động Spring.
- **Không cần service giữ ApplicationContext:** lớp nghiệp vụ không phải tự lookup bean.
- **Tái sử dụng dễ:** business class không cần import Spring nếu không có các annotation/phụ thuộc Spring khác.

Ví dụ:

~~~java
public final class CheckoutService {
    private final InventoryPort inventory;
    private final ReceiptPort receipts;

    public CheckoutService(InventoryPort inventory, ReceiptPort receipts) {
        this.inventory = java.util.Objects.requireNonNull(inventory);
        this.receipts = java.util.Objects.requireNonNull(receipts);
    }
}
~~~

Đây là **đoạn thiết kế minh họa**. Nó có một constructor với **hai tham số**. Quy tắc “một constructor không cần `@Autowired`” vẫn áp dụng: không hề giới hạn constructor chỉ được có **một tham số**. Spring có thể resolve từng tham số theo type và các qualifier phù hợp.

**`final` không có nghĩa tất cả collaborator tự immutable hay thread-safe.** Nó chỉ bảo đảm field reference không bị gán lại sau khi constructor hoàn thành. Bean singleton chứa mutable state vẫn cần thiết kế đồng thời thích hợp.

## 4. Đừng nhầm ba khái niệm “một” khác nhau

| Cụm từ | Ý nghĩa | Đúng hay sai? |
| --- | --- | --- |
| **Một constructor** | Class khai báo đúng một constructor để Spring xem xét | Đây là điều kiện của quy tắc không cần `@Autowired` |
| Một tham số | Constructor nhận đúng một argument | Không bắt buộc; có thể nhận nhiều argument |
| Một bean trong context | Chỉ một instance hoặc một bean definition tương ứng | Không đồng nghĩa; scope/ứng viên dependency là vấn đề khác |

Một class có duy nhất constructor gồm ba argument vẫn thuộc quy tắc:

~~~java
public BillingService(AccountRepository accounts,
                      ExchangeRateClient rates,
                      ReceiptSender receipts) {
    this.accounts = accounts;
    this.rates = rates;
    this.receipts = receipts;
}
~~~

Đoạn minh họa này cần field và interface phù hợp nếu muốn compile. Spring phải có **cách giải quyết mỗi dependency**; việc chỉ có một constructor **không miễn trừ lỗi thiếu bean**.

Lớp không khai báo constructor tường minh có một **constructor mặc định không tham số** do Java cung cấp (khi đủ điều kiện). Nếu class đó được tạo như Spring bean, nó có thể được tạo không cần constructor arguments. Nhưng điều này **không chứng minh injection**: không có dependency nào được inject vào constructor không tham số.

## 5. Ví dụ Maven/Spring Framework 6.2, Java 17 runnable

Ứng dụng console chứng minh trực tiếp:

1. `OrderService` có **một constructor tham số**, **không có `@Autowired`** và **không có `@Component`**.
2. `PricePolicy` có một implementation được đăng ký bằng `@Bean`.
3. `context.register(AppConfig.class, OrderService.class)` làm Spring biết class service.
4. Spring tự cấp bean `PricePolicy` cho constructor `OrderService`.
5. `getBean(OrderService.class)` lấy được service hoạt động, hai lần lookup singleton nhận cùng reference.

### 5.1. Yêu cầu và cấu trúc thư mục

Cần JDK 17+ và Apache Maven. Ví dụ dùng Spring Framework **6.2.0** qua `spring-context`, không dùng Spring Boot, web server hoặc database.

~~~text
one-constructor-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SingleConstructorDemo.java
~~~

Tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>one-constructor-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.SingleConstructorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. File Java hoàn chỉnh

Lưu file `src/main/java/demo/SingleConstructorDemo.java`:

~~~java
package demo;

import java.util.Objects;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class SingleConstructorDemo {
    private SingleConstructorDemo() {}

    // Một hợp đồng Java: không phụ thuộc Spring.
    public interface PricePolicy {
        int calculate(int unitPrice, int quantity);
    }

    // Implementation do configuration chọn.
    public static final class StandardPricePolicy implements PricePolicy {
        @Override
        public int calculate(int unitPrice, int quantity) {
            return Math.multiplyExact(unitPrice, quantity);
        }
    }

    // Không có @Component và cũng KHÔNG có @Autowired.
    // Có duy nhất MỘT constructor với một dependency bắt buộc.
    public static final class OrderService {
        private final PricePolicy policy;

        public OrderService(PricePolicy policy) {
            this.policy = Objects.requireNonNull(policy, "policy");
        }

        public String checkout(String sku, int unitPrice, int quantity) {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank() || unitPrice < 0 || quantity <= 0) {
                throw new IllegalArgumentException("Invalid order input");
            }
            return sku + "=" + policy.calculate(unitPrice, quantity);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public PricePolicy pricePolicy() {
            return new StandardPricePolicy();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Đăng ký class service để Spring trực tiếp dùng constructor.
            context.register(AppConfig.class, OrderService.class);
            context.refresh();

            OrderService service = context.getBean(OrderService.class);

            System.out.println("ORDER_BEANS "
                    + context.getBeanNamesForType(OrderService.class).length);
            System.out.println("RESULT "
                    + service.checkout("BOOK", 30, 2));
            System.out.println("SAME_INSTANCE "
                    + (service == context.getBean(OrderService.class)));
        }
    }
}
~~~

### 5.3. Biên dịch và chạy với Maven

Tại thư mục `one-constructor-demo`:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

Các dòng **stdout do chính `SingleConstructorDemo` in ra**, theo thứ tự:

~~~text
ORDER_BEANS 1
RESULT BOOK=60
SAME_INSTANCE true
~~~

Lệnh `mvn -version` sẽ in thông tin phiên bản. Maven/plugin có thể in log hoặc tải dependency khi chạy lần đầu, vì thế **ba dòng trên không bao gồm mọi log terminal**.

### 5.4. Giải thích thứ tự thực thi

1. Lệnh `new AnnotationConfigApplicationContext()` tạo context chưa được refresh.
2. `context.register(AppConfig.class, OrderService.class)` đăng ký **cả cấu hình** và **class service**. `OrderService` không cần `@Component` vì đã được đăng ký trực tiếp.
3. `context.refresh()` xử lý `@Configuration` và `@Bean pricePolicy()`, tạo bean `PricePolicy`; container cũng tạo các singleton non-lazy thích hợp.
4. Khi cần tạo `OrderService`, Spring nhận ra class có **duy nhất constructor `OrderService(PricePolicy)`**, dù không gắn `@Autowired`.
5. Spring giải quyết bean tương thích với `PricePolicy` (chính `StandardPricePolicy` được công bố qua `@Bean`) rồi gọi constructor với instance đó.
6. `getBean(OrderService.class)` trả service đã nhận dependency; nó **không tự gọi constructor mới mỗi lần lookup** với scope singleton mặc định.
7. Trong context này chỉ có một bean `OrderService` nên `getBeanNamesForType(...)` có độ dài 1.
8. `checkout("BOOK",30,2)` gọi `Math.multiplyExact(30,2)` trong policy, cho kết quả 60 và tạo chuỗi `BOOK=60`.
9. Lookup lại bean type `OrderService` trong cùng context trả cùng reference, cho `SAME_INSTANCE true`.
10. `try-with-resources` đóng context. Các callback hủy phù hợp được Spring xử lý cho managed beans.

Điểm nhấn: việc `OrderService` **không có annotation Spring** không ngăn constructor injection; **bean registration** mới là yếu tố để Spring biết tạo đối tượng.

## 6. Java 17 thuần: constructor injection vẫn dùng được khi không có Spring

Để chứng minh constructor injection không phải một cú pháp đặc biệt của Spring, hãy thử chương trình **độc lập** chỉ dùng JDK.

Tạo `src/main/java/demo/PlainConstructorDemo.java`:

~~~java
package demo;

import java.util.Objects;

public final class PlainConstructorDemo {
    private PlainConstructorDemo() {}

    @FunctionalInterface
    public interface GreetingPort {
        String hello(String name);
    }

    public static final class GreetingService {
        private final GreetingPort greeting;

        public GreetingService(GreetingPort greeting) {
            this.greeting = Objects.requireNonNull(greeting);
        }

        public String greet(String name) {
            return greeting.hello(name);
        }
    }

    public static void main(String[] args) {
        GreetingPort fake = name -> "Hello " + name;
        GreetingService service = new GreetingService(fake);
        System.out.println(service.greet("Lan"));
    }
}
~~~

Từ thư mục `one-constructor-demo`, biên dịch và chạy **không dùng Maven/Spring**:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/main/java/demo/PlainConstructorDemo.java
java -cp out demo.PlainConstructorDemo
~~~

**Stdout chính xác:**

~~~text
Hello Lan
~~~

Trong ví dụ Java thuần, **`main` tự cung cấp argument** `fake` cho constructor. JVM không tự tìm implementation của `GreetingPort`. Khi dùng Spring, container thực hiện phần lựa chọn và cung cấp dependency trong một bean graph tương ứng.

### Khi tự gọi `new` thì `@Autowired` có tác dụng không?

Ví dụ minh họa:

~~~java
OrderService service = new OrderService(new StandardPricePolicy());
~~~

Đây là cách tạo trực tiếp và truyền dependency thủ công; nó hợp lệ nếu các class nằm trong phạm vi truy cập. Nhưng object được `new` bên ngoài container **không tự trở thành Spring-managed bean**, cũng không tự nhận bean post-processing, lifecycle hoặc proxy của Spring. Việc không cần `@Autowired` với constructor duy nhất là **quy tắc chọn constructor của Spring khi tạo bean**, không phải phép màu kích hoạt trên mọi `new`.

## 7. Khi nào cần ghi `@Autowired` rõ ràng?

### 7.1. Một constructor: annotation thường dư thừa

~~~java
@Component
final class ShippingService {
    private final ShippingRatePolicy rates;

    public ShippingService(ShippingRatePolicy rates) {
        this.rates = rates;
    }
}
~~~

Mã **minh họa**, cần khai báo `ShippingRatePolicy`, import `Component` và component scan. Khi `ShippingService` là Spring bean và có đúng một constructor, không cần thêm `@Autowired` để chọn constructor đó.

Viết:

~~~java
@Autowired
public ShippingService(ShippingRatePolicy rates) {
    this.rates = rates;
}
~~~

có thể được dùng để **biểu đạt ý định** hoặc giữ tính nhất quán trong dự án, nhưng **không thay đổi yêu cầu có dependency** trong tình huống một constructor duy nhất. Đừng gắn annotation chỉ vì nghĩ Java sẽ không chạy được nếu thiếu nó.

### 7.2. Nhiều constructor: phải làm rõ chiến lược lựa chọn

~~~java
@Component
class MultiConstructorService {
    private final ReportRepository repository;

    public MultiConstructorService() {
        this.repository = null;
    }

    @Autowired
    public MultiConstructorService(ReportRepository repository) {
        this.repository = repository;
    }
}
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. Với nhiều constructor, quy tắc “chỉ một constructor thì được dùng ngầm” **không còn áp dụng**. Đánh dấu constructor mong muốn bằng `@Autowired` giúp Spring biết đó là constructor cần dùng; nếu dependency cần thiết thiếu, tạo bean có thể thất bại.

Không nên thêm một constructor không tham số chỉ để “cho Spring dễ tạo”, nhất là nếu nó làm object thiếu field bắt buộc. Một class nghiệp vụ nên cố gắng có **một constructor duy nhất với tất cả required dependencies** khi thiết kế cho phép.

Nếu class có nhiều constructor mà không có annotation, Spring còn có những quy tắc và khả năng suy luận constructor theo bean definition/argument types/version. **Không được suy ra rằng Spring luôn chọn constructor dài nhất, constructor đầu tiên hoặc constructor “có nhiều bean thỏa” một cách vô điều kiện.**

### 7.3. `@Autowired(required = false)` trên constructor không giống optional field

Một số developer thêm `required=false` để biến constructor bắt buộc thành tùy chọn. Đây là cách hiểu dễ sai. Với nhiều constructor, Spring có thể xem các constructor được annotation non-required là candidates và chọn constructor phù hợp theo quy tắc resolution, nhưng **không có nghĩa Spring truyền `null` vào mọi tham số bị thiếu**, hay biến một class bất kỳ thành hợp lệ không dependency.

Nếu collaborator là optional, hãy cân nhắc **`Optional<T>`**, `@Nullable` phù hợp, `ObjectProvider<T>`, hoặc setter injection có default/hành vi an toàn. Đừng làm loãng constructor mandatory chỉ để che lỗi thiếu bean.

## 8. Đúng một constructor mà vẫn có thể lỗi

Một constructor được Spring chọn tự động **không bảo đảm tạo bean thành công**. Xét những trường hợp:

### Thiếu bean dependency

Nếu `OrderService` cần `PricePolicy` mà `AppConfig` không đăng ký implementation tương ứng, Spring không thể resolve parameter. Trong ví dụ singleton eager, lỗi có thể xuất hiện **ngay lúc `refresh()`**, thường qua `UnsatisfiedDependencyException` với nguyên nhân thiếu bean.

~~~java
// Minh họa thử lỗi: không thêm AppConfig vào context.
context.register(OrderService.class);
context.refresh(); // Có thể fail do thiếu PricePolicy.
~~~

Đoạn này chỉ để minh họa tình huống, không nên chèn vào chương trình chạy chính nếu muốn giữ stdout mục 5.

### Có nhiều bean cùng interface

Nếu có hai bean `PricePolicy` mà injection point cần đúng một và không có quy tắc phân giải, có thể gặp `NoUniqueBeanDefinitionException`. Giải pháp thường là `@Primary`, `@Qualifier` hoặc chọn bean name/type rõ ràng ở nơi đăng ký.

Ví dụ:

~~~java
public OrderService(@Qualifier("standardPolicy") PricePolicy policy) {
    this.policy = policy;
}
~~~

Đây là **đoạn minh họa**; cần import `org.springframework.beans.factory.annotation.Qualifier` và khai báo bean name `standardPolicy`. Quy tắc một constructor không cần `@Autowired` **không cấm** dùng `@Qualifier` cho parameter.

### Constructor tự ném exception

Nếu `Objects.requireNonNull(policy)`, logic validate hoặc constructor của dependency ném lỗi, việc tạo bean vẫn thất bại. `@Autowired` không phải exception handler và không tự phục hồi object graph.

### Dependency vòng tròn qua constructor

Một sơ đồ như `A(B)` và `B(A)` là constructor cycle không thể giải quyết bình thường khi cả hai cần nhau để tồn tại. Việc bỏ `@Autowired` không tự giải quyết được chu kỳ; cần thiết kế lại trách nhiệm hoặc dùng cơ chế trì hoãn có chủ đích khi thật sự phù hợp.

### Class chưa đăng ký

Ngay cả khi constructor hợp lệ và bean `PricePolicy` có sẵn, nếu `OrderService` không được khai báo `@Bean`, không được component-scan và không được `register(...)`, `context.getBean(OrderService.class)` vẫn có thể thất bại với `NoSuchBeanDefinitionException`.

**Kết luận của mục này:** annotation không phải chìa khóa sửa mọi lỗi autowiring. Cần kiểm tra **registration**, **constructor selection**, **dependency resolution** và **lifecycle** theo thứ tự.

## 9. `@Bean` cũng có constructor injection, nhưng ở một vị trí khác

So sánh hai kiểu wiring.

### Cách A: Spring khởi tạo class bean trực tiếp

~~~java
context.register(OrderService.class);
context.refresh();
~~~

Khi `OrderService` có duy nhất constructor `OrderService(PricePolicy)` và dependency đã tồn tại, container trực tiếp gọi constructor. Đây là tình huống tiêu biểu cho quy tắc một constructor không cần `@Autowired`.

### Cách B: `@Bean` factory method tự new service

~~~java
@Bean
OrderService orderService(PricePolicy policy) {
    return new OrderService(policy);
}
~~~

Spring giải quyết `PricePolicy` vào **tham số method `orderService`**. Mã Java trong factory **tự** gọi constructor. Với cách này, class `OrderService` có thể được thiết kế không import Spring và không cần component scan.

**Đừng nhầm**: cả A và B đều có thể thực hiện Dependency Injection hiệu quả, nhưng cách Spring quyết định gọi constructor có khác nhau.

Với `@Bean` method, Spring thường không cần `@Autowired` để tự resolve factory method parameters; đó là hành vi của bean factory infrastructure.

## 10. Unit test không cần Spring: lợi ích của một constructor rõ ràng

Với business class đơn giản:

~~~java
public interface PricePolicy {
    int calculate(int unitPrice, int quantity);
}
~~~

và `OrderService(PricePolicy policy)`, test có thể tự truyền fake:

~~~java
PricePolicy fake = (unitPrice, quantity) -> 123;
OrderService service = new OrderService(fake);

String actual = service.checkout("BOOK", 30, 2);

if (!"BOOK=123".equals(actual)) {
    throw new AssertionError("Expected BOOK=123 but got " + actual);
}
~~~

Hai khối là **trích đoạn minh họa trong cùng context với các class mục 5**, không phải file chạy độc lập. Fake không cần database, HTTP client hoặc Spring context. Điều cần assert là **kết quả và tương tác đúng hợp đồng**, không chỉ “không ném exception”.

### Khi muốn kiểm thử Spring wiring

Một integration test có thể khởi động `AnnotationConfigApplicationContext` và kiểm tra lấy được `OrderService`. Việc chạy context kiểm tra:

- Bean class và configuration đã đăng ký đúng.
- `PricePolicy` có ứng viên được lựa chọn duy nhất.
- Constructor duy nhất được resolve thành công.
- Bean đủ điều kiện để dùng.
- Scope và lifecycle theo cấu hình.

Không cần khởi động container trong **mọi unit test** của `OrderService`; cách đó làm test gắn thêm với hạ tầng mà logic nghiệp vụ không cần.

## 11. Bảng đối chiếu nhanh

| Tình huống | Cần `@Autowired` trên constructor không? | Điểm quan trọng |
| --- | --- | --- |
| Spring tạo bean class có đúng một constructor | **Không cần** | Constructor được Spring chọn ngầm |
| Constructor duy nhất có 2–4 tham số | **Không cần** | Từng tham số vẫn cần resolve được |
| Class có `@Component` và được scan, một constructor | **Không cần** | Scan phải được bật và trúng package |
| Class được `context.register(MyClass.class)`, một constructor | **Không cần** | Container biết bean definition |
| Object tự `new MyClass(dep)` ngoài Spring | Không liên quan tới Spring autowiring | Người gọi tự truyền dep |
| `@Bean MyClass myClass(Dep dep)` tự gọi `new` | Không cần trên constructor để factory hoạt động | Factory method được Spring inject |
| Class có nhiều constructor cần chỉ định một constructor | **Thường nên dùng** | Tránh ambiguity và chọn sai constructor |
| Có một constructor nhưng thiếu bean dependency | Viết annotation không chữa được | Cần bean definition/candidate hợp lệ |
| Có một constructor nhưng nhiều bean cùng type | Viết annotation không chữa được | Cần qualifier/primary/quy tắc chọn |
| Cần injection vào setter/field thay vì constructor | Annotation hoặc metadata injection phù hợp | Quy tắc single-constructor chỉ nói về constructor |

## 12. Lỗi phổ biến khi học `@Autowired`

| Hiểu nhầm | Điều đúng |
| --- | --- |
| “Constructor nào cũng phải gắn `@Autowired`.” | Không; Spring 4.3+ tự dùng constructor duy nhất của bean. |
| “Không có `@Autowired` thì Java không biết truyền tham số.” | Java luôn đòi người tạo object truyền argument; Spring chỉ cung cấp tự động khi nó tạo bean. |
| “Có một constructor thì Spring tự scan class.” | Không; cần bean registration/component scan/`@Bean` thích hợp. |
| “Chỉ một constructor nghĩa là constructor không tham số.” | Không; constructor duy nhất có thể có nhiều tham số. |
| “Bỏ `@Autowired` sẽ bỏ yêu cầu bean dependency.” | Không; tham số constructor vẫn phải được giải quyết. |
| “`@Autowired` xử lý được cả thiếu bean và nhiều bean mơ hồ.” | Không; phải xử lý candidate và cấu hình đúng. |
| “Class đã có `@Service` nên chắc chắn được scan.” | Annotation không đủ nếu scanning không bao phủ package/class. |
| “Một constructor thì constructor đó chạy trước khi dependency được tạo.” | Spring thường phải giải quyết dependency để gọi constructor; dependency được cung cấp vào thời điểm invocation. |
| “Không cần `@Autowired` cũng không cần DI.” | Vẫn là DI; chỉ bỏ annotation thừa. |
| “Constructor injection đồng nghĩa tất cả state immutable.” | `final` reference và tính immutable/thread safety là những vấn đề riêng. |
| “`new` ngoài container sẽ được tiêm tự động.” | Không; phải truyền argument thủ công hoặc dùng managed bean. |
| “`@Bean` method argument được inject nhờ annotation trên constructor sản phẩm.” | Factory method arguments được container resolve theo `@Bean` infrastructure. |
| “Nhiều constructor Spring luôn chọn constructor dài nhất.” | Không có quy tắc đơn giản đúng cho mọi cấu hình. |
| “Thêm constructor mặc định là cách sửa dependency lỗi.” | Có thể khiến object tồn tại ở trạng thái thiếu required collaborators. |
| “Đánh dấu `@Autowired(required=false)` biến mọi dependency bắt buộc thành optional.” | Constructor candidate resolution phức tạp hơn; không đồng nghĩa inject null an toàn. |

## 13. Bài tập và đáp án

**Bài 1.** Class `ReportService` có duy nhất constructor nhận `ReportRepository`, được Spring component-scan và có bean repository. Có cần `@Autowired` không?

**Đáp án:** Không. Với Spring 4.3+ Spring có thể dùng constructor duy nhất và tự resolve repository.

**Bài 2.** Class có duy nhất constructor ba tham số. Quy tắc này có áp dụng không?

**Đáp án:** Có. Số **constructor** là 1; số **tham số** có thể là 3. Mỗi tham số vẫn phải có dependency phù hợp.

**Bài 3.** Class có một constructor, nhưng không đăng ký bean và cũng không bật scan. `getBean(Class)` có thể tìm được chỉ nhờ constructor không?

**Đáp án:** Không. Spring cần biết bean definition trước khi tạo/lookup.

**Bài 4.** Service không có `@Autowired`, nhưng một constructor bắt buộc nhận `PricePolicy`, context lại không có bean `PricePolicy`. Thêm annotation có sửa được không?

**Đáp án:** Không. Cần cung cấp bean implementation hoặc sửa cấu hình dependency; thiếu bean không phải do quên annotation trong tình huống một constructor.

**Bài 5.** Vì sao chương trình in `SAME_INSTANCE true`?

**Đáp án:** `OrderService` là bean singleton mặc định trong cùng context; hai lần lookup trả một instance. Điều này **không có nghĩa** chỉ tồn tại một instance toàn JVM.

**Bài 6.** Trong ví dụ `@Bean OrderService service(PricePolicy p)` trả `new OrderService(p)`, ai cung cấp `p` và ai gọi constructor?

**Đáp án:** Spring giải quyết `p` khi gọi factory method; **body `@Bean`** gọi constructor bằng `new`.

**Bài 7.** Nếu thêm một constructor không tham số vào `OrderService`, có thể bỏ qua mọi chú ý tới constructor selection không?

**Đáp án:** Không. Bây giờ có nhiều constructor, nên quy tắc constructor duy nhất không còn áp dụng. Cần chỉ rõ chiến lược, thường đánh dấu constructor cần dùng bằng `@Autowired`.

**Bài 8.** Khi chỉ có một constructor, có được dùng `@Qualifier` trên tham số mà không có `@Autowired` trên constructor không?

**Đáp án:** Có, khi muốn xác định rõ bean candidate cho tham số trong constructor được Spring chọn. Phải khai báo qualifier/bean names khớp cấu hình thực.

**Bài 9.** Tại sao `@Autowired` trên field thường không được khuyến khích bằng constructor injection cho dependency bắt buộc?

**Đáp án:** Field injection làm dependency kém hiển thị, khó tạo unit test Java thuần hơn và không thuận lợi cho `final` fields. Constructor biểu đạt required dependencies từ lúc tạo object.

**Bài 10.** Nếu dùng một constructor với hai dependency nhưng class quá nhiều trách nhiệm, bỏ `@Autowired` có làm kiến trúc tốt hơn không?

**Đáp án:** Không. Bỏ annotation chỉ làm ngắn mã. Chất lượng thiết kế phụ thuộc cách chia trách nhiệm, hợp đồng và vòng đời collaborator.

## 14. Checklist để áp dụng vào dự án

- [ ] Xác định **class thực sự là Spring-managed bean**: component scan, register hoặc `@Bean`.
- [ ] Đếm **số constructor** của bean class, không đếm số tham số.
- [ ] Nếu chỉ có **một constructor**, với Spring Framework 4.3+ thông thường không cần `@Autowired`.
- [ ] Đưa required dependencies vào constructor và kiểm tra argument khi cần.
- [ ] Đảm bảo mỗi parameter có bean candidate phù hợp trong context.
- [ ] Nếu nhiều bean cùng type, dùng qualifier/primary hoặc chính sách chọn rõ.
- [ ] Không thêm constructor không tham số chỉ để che lỗi thiếu dependency.
- [ ] Nếu nhiều constructor, thiết kế strategy selection rõ ràng thay vì đoán.
- [ ] Không cho rằng `@Component` tự được scan khi package không nằm trong cấu hình scan.
- [ ] Với `@Bean` factory method, nhớ Spring inject các factory parameters.
- [ ] Phân biệt object tạo bằng `new` với instance do Spring quản lý.
- [ ] Unit test service bằng fake Java thuần; integration test riêng wiring Spring.
- [ ] Rà scope/lifecycle và tác động của proxy khi mở rộng AOP/transaction.
- [ ] Không coi constructor injection là bảo đảm thread safety hay transactional consistency.
- [ ] Kiểm tra stdout ứng dụng tách biệt log Maven và xác nhận Java 17 compatibility.

### Tài liệu Spring tham khảo

- [Using `@Autowired` — constructor injection](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Constructor-based Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java/basic-concepts.html)

**Kết luận:** Nếu Spring đã biết tạo một bean và bean class có **đúng một constructor**, constructor đó thường được Spring sử dụng dù không gắn `@Autowired`. Điều này làm constructor injection ngắn gọn, rõ required dependencies và dễ test. Nhưng nó **không thay thế** bean registration, không tự chọn ứng viên khi thiếu/nhiều bean và không làm Java `new` ngoài container tự động nhận dependency.