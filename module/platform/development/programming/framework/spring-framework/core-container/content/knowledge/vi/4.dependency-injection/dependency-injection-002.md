# Tiêm qua hàm khởi tạo và bảo đảm trạng thái hợp lệ — Spring Framework Core Container

## 1. Vấn đề cần giải quyết

Giả sử `CheckoutService` muốn tính tiền một đơn hàng và ghi lại giao dịch. Nó phụ thuộc vào `PricingPolicy` để tính tổng tiền và `AuditTrail` để ghi lịch sử. Cả hai là **dependency bắt buộc**: nếu một dependency chưa được cung cấp, service **không nên được tạo thành công rồi đợi tới lúc gọi method mới báo `NullPointerException`**.

**Constructor injection** (tiêm phụ thuộc qua hàm khởi tạo) là thiết kế trong đó những dependency bắt buộc xuất hiện trong **tham số constructor**; caller hoặc Spring container phải cung cấp chúng tại thời điểm tạo object. Constructor có thể kiểm tra chúng, bảo đảm object không thoát ra ngoài trong trạng thái thiếu thành phần thiết yếu.

~~~mermaid
flowchart LR
    Container["Spring IoC Container"] -->|"tạo và cung cấp"| P["pricingPolicy : PricingPolicy"]
    Container -->|"tạo và cung cấp"| A["auditTrail : AuditTrail"]
    P -->|"constructor parameter"| S["checkoutService : CheckoutService"]
    A -->|"constructor parameter"| S
    S -->|"đã có các collaborator"| Use["checkout(...)"]
~~~

Trong hình, mũi tên từ dependency tới service là **luồng cung cấp object vào constructor**. Nếu vẽ *dependency graph* theo quy ước **consumer → dependency**, bạn sẽ viết `CheckoutService → PricingPolicy` và `CheckoutService → AuditTrail`. Không nên nhầm hai quy ước hướng mũi tên.

Sau bài học bạn có thể:

1. Viết constructor nhận dependency bắt buộc thay vì `new` hoặc gọi `ApplicationContext.getBean(...)` từ code nghiệp vụ.
2. Hiểu cách Spring tự chọn **constructor duy nhất** của một bean (không bắt buộc `@Autowired` với một constructor).
3. Bảo đảm tham chiếu không null và giá trị cấu hình hợp lệ **ngay tại ranh giới khởi tạo**, kể cả khi object được tạo thủ công ngoài Spring.
4. Sử dụng `private final` hợp lý, hiểu giới hạn của nó đối với tính bất biến và thread safety.
5. Kiểm thử được wiring, constructor guards, logic nghiệp vụ và ca thiếu bean.
6. Chạy ví dụ Java 17+ dùng **Spring Framework Core Container thuần**, Maven, `javac`/`java` và stdout chính xác.
7. Phân biệt constructor injection với setter/field injection, dependency tùy chọn, scope/lazy và vòng phụ thuộc.

**Giới hạn:** bài học tập trung vào **constructor injection và tính hợp lệ của trạng thái sau khởi tạo**, không đi sâu Spring Boot, MVC, JPA, transaction hoặc các framework validation bên ngoài.

## 2. Tiêm phụ thuộc là gì nếu bỏ Spring ra khỏi bài toán?

Trong Java thuần, một lớp có thể tự tạo collaborator:

~~~java
public final class CheckoutService {
    private final PricingPolicy pricing = new PricingPolicy(150);
    // Service tự quyết định giá, khó thay bằng fake khi test.
}
~~~

**Snippet minh họa**, không phải file Java hoàn chỉnh; `PricingPolicy` là lớp nghiệp vụ được định nghĩa trong project ở mục 5. Ở đây service chịu cả trách nhiệm tính tiền **và chọn/cấu hình một dependency**.

Thiết kế với constructor injection:

~~~java
public final class CheckoutService {
    private final PricingPolicy pricing;
    private final AuditTrail audit;

    public CheckoutService(PricingPolicy pricing, AuditTrail audit) {
        this.pricing = Objects.requireNonNull(pricing, "pricing is required");
        this.audit = Objects.requireNonNull(audit, "audit is required");
    }
}
~~~

**Snippet minh họa**, cần import `Objects` cùng định nghĩa hai collaborator. Tại đây:

- Class tuyên bố minh bạch cần `PricingPolicy` và `AuditTrail` để tồn tại hợp lệ.
- Caller **phải chọn và cung cấp** dependency ở lúc gọi constructor.
- Không có constructor mặc định cho phép tạo một `CheckoutService` “rỗng” rồi quên inject.
- `Objects.requireNonNull` ném `NullPointerException` **trong constructor** nếu tham số null, thay vì tạo object hỏng.
- `private final` bảo đảm field được gán một lần trên những đường constructor hợp lệ; code bên ngoài không thể tùy ý thay field.

Java thuần đã có DI:

~~~java
PricingPolicy pricing = new PricingPolicy(150);
AuditTrail audit = new AuditTrail();
CheckoutService service = new CheckoutService(pricing, audit);
~~~

Đây là snippet minh họa *manual wiring*. Spring không phát minh ra constructor của Java; nó thực hiện **lắp ghép object graph theo bean definitions** và cung cấp các tham số constructor cho những bean nó tạo.

### Ba tầng khác nhau

| Tầng | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Hợp đồng của class | Định nghĩa thứ gì bắt buộc, kiểm tra invariant | `CheckoutService(PricingPolicy, AuditTrail)` |
| Composition/wiring | Chọn instance đúng để đưa vào constructor | Spring resolve hai beans theo type |
| Sử dụng nghiệp vụ | Gọi method trên object đã hợp lệ | `checkout("BOOK", 2)` |

**Invariant** là điều kiện phải đúng với object ở trạng thái hợp lệ. Ở ví dụ này: hai dependency không null. Trong `PricingPolicy`, giá đơn vị phải dương. Trong method `checkout(...)`, input phải hợp lệ trước khi ghi audit. Hai loại kiểm tra *constructor invariant* và *business input validation* không thay thế nhau.

## 3. Constructor giúp tránh trạng thái khởi tạo dở dang

So sánh với field/setter injection cho dependency bắt buộc:

~~~java
class UnsafeCheckoutService {
    private PricingPolicy pricing;
    private AuditTrail audit;

    void setPricing(PricingPolicy pricing) {
        this.pricing = pricing;
    }

    void setAudit(AuditTrail audit) {
        this.audit = audit;
    }
}
~~~

**Mã minh họa**, không phải file runnable. Với API như thế, caller có thể tạo một instance rồi chỉ gọi một setter hoặc không gọi setter nào. Trước khi được cấu hình xong, object đã tồn tại nhưng **chưa đáp ứng invariant**.

Constructor injection không cho phép tạo instance qua **constructor công khai đó** nếu thiếu những tham số bắt buộc. Khi Spring container tạo một bean, nó phải tìm dependency cho constructor, tạo hoặc lấy dependency phù hợp và truyền vào **trước khi trả bean đã khởi tạo** cho consumer theo vòng đời bình thường.

| Đặc điểm | Constructor injection | Setter injection | Field injection |
| --- | --- | --- | --- |
| Dependency bắt buộc hiển thị rõ trong API | Có, ở constructor | Thường không | Không trong chữ ký constructor |
| Có thể tạo service Java thuần để unit test | Dễ | Cần gọi setters | Cần framework/reflection hoặc API phụ |
| Có thể dùng `final` cho reference | Tự nhiên | Thường không | Không hợp lý với field injection thông thường |
| Bắt buộc trạng thái hợp lệ từ cuối constructor | Có thể bằng validation | Cần cơ chế bổ sung | Phụ thuộc lifecycle/injection của container |
| Hợp lý cho giá trị thật sự tùy chọn sau tạo | Có thể, nhưng thường không phải mục tiêu chính | Phù hợp hơn trong một số thiết kế | Ít minh bạch hơn |

**Không tuyệt đối hóa:** setter injection có chỗ đứng cho dependency *thật sự tùy chọn* hoặc đối tượng cần reconfiguration. Một class có thể cần nhiều kiểu injection vì API của thư viện bên thứ ba. Nhưng với collaborator bắt buộc để thực thi nghiệp vụ, constructor injection thường là lựa chọn mặc định dễ kiểm thử và bảo trì.

### Lỗi thường gặp: tưởng final làm object tự động immutable

Trường:

~~~java
private final AuditTrail audit;
~~~

chỉ bảo đảm **reference `audit` không bị gán lại** sau khởi tạo. Nếu `AuditTrail` có danh sách mutable, những method của nó vẫn có thể thay đổi nội dung. Vì vậy:

- `final reference` không đồng nghĩa *deep immutability*.
- Bean singleton được nhiều thread gọi vẫn phải bảo đảm **thread safety** cho state mutable.
- Không để lộ một danh sách mutable qua getter rồi nghĩ rằng service đã bất biến.
- Validation ở constructor không bảo đảm mọi method sau đó luôn thành công; nó chỉ bảo đảm **object ban đầu hợp lệ theo invariant đã kiểm tra**.

Ví dụ dùng `List.copyOf(...)` khi công bố snapshot của audit, tránh trao một reference danh sách nội bộ cho caller sửa.

## 4. Spring chọn constructor bằng cách nào?

Một bean được Spring quản lý có **chỉ một constructor** có thể viết:

~~~java
@Component
public class OrderService {
    private final PricingPolicy pricing;

    public OrderService(PricingPolicy pricing) {
        this.pricing = Objects.requireNonNull(pricing);
    }
}
~~~

**Đây là snippet, không phải mã đầy đủ của project**. Nếu Spring đã đăng ký `OrderService` làm bean và biết bean `PricingPolicy` thích hợp, Spring 4.3+ có thể tự dùng constructor duy nhất mà **không yêu cầu viết `@Autowired`** trên constructor.

Với nhiều constructors hoặc candidate phức tạp, phải xem quy tắc chọn constructor:

~~~java
@Component
public class OtherService {
    private final PricingPolicy pricing;

    public OtherService() {
        throw new IllegalStateException("unsupported configuration");
    }

    @Autowired
    public OtherService(PricingPolicy pricing) {
        this.pricing = Objects.requireNonNull(pricing);
    }
}
~~~

Snippet chỉ minh họa annotation và cách chọn constructor, không phải source runnable độc lập; trong cấu hình như thế, đánh dấu constructor dự kiến bằng `@Autowired` để lựa chọn minh bạch. Không thêm constructor không tham số chỉ để làm Spring vui lòng rồi để service ở trạng thái thiếu dependency.

**Một số quy tắc đáng nhớ:**

- Một class có **một constructor**: constructor đó thường được Spring chọn, kể cả không gắn `@Autowired`.
- Nhiều constructors: nên làm rõ constructor dùng cho dependency bắt buộc; đừng trông chờ Spring suy đoán ý định nghiệp vụ.
- Một constructor gắn `@Autowired(required=true)` phải là lựa chọn bắt buộc; không gắn nhãn required cho nhiều constructors khác nhau.
- Nếu nhiều constructors được gắn `@Autowired(required=false)`, Spring chọn theo khả năng giải quyết dependency theo quy tắc của nó; cách viết này có thể khó đọc hơn một constructor rõ ràng.
- Spring chọn **bean candidate** dựa vào type, qualifier, primary và các quy tắc phù hợp. Nếu thiếu hoặc không xác định được một ứng viên bắt buộc, quá trình tạo bean thất bại.

**Đăng ký class khác với có source Java:** một class có `@Component` chưa tự xuất hiện trong context nếu không được component scanning hoặc đăng ký bằng cách khác. Trong ví dụ runnable, ta gọi trực tiếp `context.register(AppConfig.class, CheckoutService.class)` để không lệ thuộc quét toàn bộ package.

## 5. Ví dụ hoàn chỉnh Java 17+ và Spring Core Container

Chương trình sau chứng minh bốn điều:

1. Spring có thể tạo `CheckoutService` **qua constructor duy nhất không có `@Autowired`**.
2. Container cung cấp đúng **hai bean bắt buộc** đã đăng ký.
3. Sau khởi tạo, service có thể chạy nghiệp vụ, và giữ **chính reference** mà context đang quản lý.
4. Nếu tạo object bằng Java thường với null dependency hoặc giá không hợp lệ, constructor **fail fast** ngay.

Dùng **JDK 17+**, Maven và **Spring Framework 6.2.19** qua module `spring-context`. Phiên bản ghim cho tính tái lập, không khẳng định mới nhất. Không cần Spring Boot hoặc HTTP server.

Cấu trúc thư mục:

~~~text
constructor-di-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ConstructorInjectionDemo.java
~~~

### 5.1. File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>constructor-di-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.ConstructorInjectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven sẽ tải `spring-context` và các dependency transitively liên quan. Muốn chạy `javac` thủ công phải đưa Spring JAR và dependency đầy đủ vào classpath; đừng chỉ đặt một file `spring-context.jar` rồi kỳ vọng compiler/runtime có tất cả modules.

### 5.2. File src/main/java/demo/ConstructorInjectionDemo.java

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

public final class ConstructorInjectionDemo {
    private ConstructorInjectionDemo() {}

    public static final class PricingPolicy {
        private final int unitPrice;

        public PricingPolicy(int unitPrice) {
            if (unitPrice <= 0) {
                throw new IllegalArgumentException("unitPrice must be positive");
            }
            this.unitPrice = unitPrice;
        }

        public int total(int quantity) {
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            return Math.multiplyExact(unitPrice, quantity);
        }
    }

    public static final class AuditTrail {
        private final List<String> events = new ArrayList<>();

        public void record(String event) {
            events.add(event);
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    @Component("checkoutService")
    public static final class CheckoutService {
        private final PricingPolicy pricing;
        private final AuditTrail audit;

        // Constructor duy nhất: không bắt buộc @Autowired.
        public CheckoutService(PricingPolicy pricing, AuditTrail audit) {
            this.pricing = Objects.requireNonNull(
                    pricing, "pricing is required");
            this.audit = Objects.requireNonNull(
                    audit, "audit is required");
        }

        public PricingPolicy pricing() {
            return pricing;
        }

        public AuditTrail audit() {
            return audit;
        }

        public String checkout(String sku, int quantity) {
            if (!"BOOK".equals(sku)) {
                throw new IllegalArgumentException("unknown sku");
            }
            String receipt = sku + " x " + quantity
                    + " = " + pricing.total(quantity);
            audit.record(receipt);
            return receipt;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public PricingPolicy pricingPolicy() {
            return new PricingPolicy(150);
        }

        @Bean
        public AuditTrail auditTrail() {
            return new AuditTrail();
        }
    }

    private static void runWithSpring() {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {
            // Register trực tiếp, không cần component scan.
            context.register(AppConfig.class, CheckoutService.class);
            context.refresh();

            CheckoutService service =
                    context.getBean(CheckoutService.class);
            PricingPolicy pricing = context.getBean(PricingPolicy.class);
            AuditTrail audit = context.getBean(AuditTrail.class);

            System.out.println("registered=" +
                    context.containsBean("checkoutService"));
            System.out.println("pricingInjected=" +
                    (service.pricing() == pricing));
            System.out.println("auditInjected=" +
                    (service.audit() == audit));
            System.out.println("serviceSingleton=" +
                    (service == context.getBean(CheckoutService.class)));
            System.out.println("receipt=" + service.checkout("BOOK", 2));
            System.out.println("audit=" + audit.snapshot());
        }
    }

    private static void checkConstructorGuards() {
        try {
            new CheckoutService(null, new AuditTrail());
            System.out.println("nullGuard=UNEXPECTED");
        } catch (NullPointerException failure) {
            System.out.println("nullGuard=" + failure.getMessage());
        }

        try {
            new PricingPolicy(0);
            System.out.println("invalidPrice=UNEXPECTED");
        } catch (IllegalArgumentException failure) {
            System.out.println("invalidPrice=" + failure.getMessage());
        }
    }

    public static void main(String[] args) {
        runWithSpring();
        checkConstructorGuards();
    }
}
~~~

**Điểm Java/Spring đáng chú ý:**

- `CheckoutService` được đánh dấu `@Component("checkoutService")` và được đăng ký **trực tiếp** qua `context.register(..., CheckoutService.class)`. Không cần `@ComponentScan` hoặc `@Autowired`.
- `CheckoutService` có **một constructor công khai** nhận `PricingPolicy` và `AuditTrail`. Spring tìm hai bean đang đăng ký và cung cấp chúng khi tạo service.
- Hai dependency được cung cấp bằng hai factory methods `@Bean` thuộc `AppConfig`. Chúng chỉ phụ trách khởi tạo collaborators; service không tự tra bean factory.
- `Objects.requireNonNull(...)` bảo vệ constructor ngay cả khi một caller tạo service bằng `new` ngoài Spring và truyền null.
- `PricingPolicy(150)` hợp lệ; `PricingPolicy(0)` ném exception tại lúc khởi tạo, không tạo ra một chính sách giá sai.
- `Math.multiplyExact` giúp báo lỗi nếu phép nhân số nguyên bị overflow thay vì âm thầm trả số sai; `quantity <= 0` bị chặn.
- `AuditTrail.snapshot()` trả một bản copy chỉ đọc từ những event đã ghi. Ví dụ dùng list đơn giản vì gọi trên một thread, **không khẳng định bean mutable này đã thread-safe**.
- Context được đóng khi rời `try-with-resources`. Bài không dựa vào thứ tự tạo các bean không có cạnh phụ thuộc hoặc vào tên class do Spring sinh ra.

### 5.3. Chạy bằng Maven

Từ thư mục `constructor-di-demo`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Đúng 8 dòng stdout do chương trình Java tự in trong happy path + kiểm tra constructor:**

~~~text
registered=true
pricingInjected=true
auditInjected=true
serviceSingleton=true
receipt=BOOK x 2 = 300
audit=[BOOK x 2 = 300]
nullGuard=pricing is required
invalidPrice=unitPrice must be positive
~~~

Lệnh in phiên bản JDK/Maven và log do Maven/Spring (nếu có) không nằm trong **tám dòng stdout của chương trình**. Các dòng `nullGuard=...` và `invalidPrice=...` không do Spring tự ném: chúng minh họa **constructor validation của code Java** ngay cả khi không có container.

### 5.4. Tự biên dịch bằng javac và chạy java

Vì code import Spring, `javac` cần compile classpath và `java` cần runtime classpath chứa Spring dependencies. Từ thư mục dự án:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

Linux/macOS (bash hoặc zsh):

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/ConstructorInjectionDemo.java
java -cp "out:$(cat classpath.txt)" demo.ConstructorInjectionDemo
~~~

Windows PowerShell:

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/ConstructorInjectionDemo.java
java -cp "out;$deps" demo.ConstructorInjectionDemo
~~~

Dấu ngăn classpath là `:` trên Unix, `;` trên Windows. Hai cách chạy gọi cùng `main` với cùng tám dòng stdout ứng dụng. Nếu compiler báo thiếu package `org.springframework...`, hãy kiểm tra Maven/classpath; lúc đó chương trình chưa tới bước DI của Spring.

## 6. Dựa vào đâu để khẳng định constructor injection đã đúng?

| Output | Bằng chứng | Không chứng minh điều gì? |
| --- | --- | --- |
| `registered=true` | Bean được Spring biết theo tên `checkoutService` | Không chứng minh mọi đường nghiệp vụ đúng |
| `pricingInjected=true` | Service giữ đúng bean `PricingPolicy` context trả về | Không đảm bảo mọi giá tính đều hợp lệ |
| `auditInjected=true` | Service giữ đúng bean `AuditTrail` trong context | Không đảm bảo AuditTrail thread-safe |
| `serviceSingleton=true` | Service có một instance trên mỗi bean definition của context này | Không có nghĩa singleton toàn JVM |
| `receipt=BOOK x 2 = 300` | Price 150 nhân quantity 2, hợp đồng checkout hoạt động | Không phải kiểm thử toàn bộ sản phẩm/SKU |
| `audit=[BOOK x 2 = 300]` | Audit đã được ghi sau lời gọi checkout thành công | Không bảo đảm lưu trữ bền vững |
| `nullGuard=pricing is required` | Constructor không chấp nhận collaborator null | Không xác nhận hành vi Spring khi thiếu bean |
| `invalidPrice=unitPrice must be positive` | Constructor PricingPolicy reject cấu hình giá 0 | Không có bean invalid object nào được tạo từ ca test này |

Ở cấu hình minh họa, `AppConfig` có đúng một bean `PricingPolicy` và một bean `AuditTrail`. Vì vậy injection theo kiểu là rõ ràng. Trong project thực, nếu có nhiều beans cùng type thì cần xác định candidate bằng qualifier/primary hoặc sửa cấu hình, thay vì đoán rằng Spring sẽ chọn theo thứ tự khai báo.

**Đọc hai kiểm chứng khác nhau:** object đã tạo **không null** nhờ constructor guards là một yêu cầu; object là **đúng bean mong muốn** lại là yêu cầu khác. Identity checks trong ví dụ cho thấy wiring của hai collaborator singleton cùng context, chứ không phải quy tắc cho mọi scope.

## 7. Fail fast khi dependency thiếu và khi cấu hình không hợp lệ

### 7.1. Thiếu bean bắt buộc

Nếu `CheckoutService` được đăng ký nhưng context không có bean `AuditTrail` tương thích, Spring **không thể hoàn tất constructor** của service. Với singleton không lazy (mặc định), vấn đề thường bị phát hiện trong `context.refresh()`; chuỗi lỗi thường xuất hiện `UnsatisfiedDependencyException` hoặc nguyên nhân `NoSuchBeanDefinitionException`.

Ví dụ negative test **minh họa**, không phải file Java độc lập:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {
    context.register(CheckoutService.class); // Thiếu PricingPolicy và AuditTrail
    context.refresh(); // Dự kiến thất bại khi tạo bean bắt buộc.
}
~~~

Nếu có `@Lazy` hoặc scope khác, lỗi có thể bị trì hoãn cho tới lúc Spring thật sự tạo bean. **Đừng kết luận context không báo lỗi tức là mọi dependency ở mọi scope đều đã kiểm tra thành công.**

**Không dùng `@Autowired(required=false)` hoặc `Optional<T>` chỉ để che thiếu dependency bắt buộc.** Một service không có chính sách giá không thể xử lý đúng; khởi động với giá trị null/default giả tạo là thiết kế không hợp lệ.

### 7.2. Dependency tồn tại nhưng có trạng thái sai

Giả sử factory khai báo:

~~~java
@Bean
PricingPolicy pricingPolicy() {
    return new PricingPolicy(0);
}
~~~

Snippet minh họa **thay cho** factory trong `AppConfig` của demo, không dùng song song hai method cùng tên. Context có bean definition, nhưng khi factory chạy, `new PricingPolicy(0)` ném `IllegalArgumentException`. Spring có thể bọc nó trong `BeanCreationException` của bean đang tạo.

**Hai kiểu fail-fast khác nhau:**

- **Missing dependency:** container không resolve đủ bean để gọi constructor service.
- **Invalid dependency:** có bean/factory được chọn, nhưng chính constructor/factory từ chối giá trị không hợp lệ.

Cả hai đều tốt hơn việc đưa một object nửa hợp lệ ra phục vụ request. Tuy vậy, fail fast còn phụ thuộc *khi nào* bean được tạo (eager/lazy/prototype).

### 7.3. Hai dependency cùng kiểu nhưng không chọn được

Nếu có `primaryPricingPolicy` và `secondaryPricingPolicy` đều kiểu `PricingPolicy`, tiêm đơn trị có thể bị mơ hồ:

~~~java
public CheckoutService(
        @Qualifier("primaryPricingPolicy") PricingPolicy pricing,
        AuditTrail audit) {
    this.pricing = Objects.requireNonNull(pricing);
    this.audit = Objects.requireNonNull(audit);
}
~~~

Snippet **chỉ minh họa**; cần import `org.springframework.beans.factory.annotation.Qualifier`, có bean tương ứng và đặt đoạn trong class phù hợp. Spring hỗ trợ đặt qualifier tại tham số constructor; nếu số lượng ứng viên nhiều, nêu rõ selection policy thay vì dựa vào tên parameter vô tình.

`@Primary` phù hợp khi muốn một bean mặc định; collection/provider phù hợp khi nghiệp vụ cần nhiều instance, không phải khi chỉ một chính sách được phép.

## 8. Vòng phụ thuộc constructor: vì sao không thể tạo object nào trước?

Ví dụ:

~~~java
final class Alpha {
    Alpha(Beta beta) {}
}
final class Beta {
    Beta(Alpha alpha) {}
}
~~~

Snippet là hai class phụ thuộc nhau, chưa có Spring registration. Nếu Spring được yêu cầu tạo cả hai như managed beans qua constructors bắt buộc, graph có chu trình:

~~~mermaid
flowchart LR
    A["Alpha"] --> B["Beta"]
    B --> A
~~~

Để tạo Alpha cần Beta, để tạo Beta cần Alpha, nhưng chưa có cái nào tạo xong. Spring thông thường báo lỗi liên quan `BeanCurrentlyInCreationException` hoặc exception wrapper khác.

**Đừng sửa bằng cách đổi mọi constructor thành field injection cho Spring “lách vòng”**, vì kết quả có thể là object khởi tạo dở dang và các quan hệ sở hữu khó kiểm soát. Nên tái phân chia trách nhiệm, tách dịch vụ chung, dùng sự kiện hoặc một abstraction làm cho graph không còn chu trình bắt buộc khi khởi tạo.

Một số cơ chế setter-based cycle có thể được Spring giải quyết trong những điều kiện nhất định; điều đó **không phải bảo đảm an toàn cho mọi vòng** và cũng không làm constructor cycle trở nên hợp lệ.

## 9. Giá trị cấu hình cũng phải được kiểm tra tại ranh giới

Constructor injection không chỉ áp dụng với những collaborator là interface. Một bean cấu hình như `PricingPolicy` còn cần **dữ liệu hợp lệ**.

Ví dụ:

~~~java
public PricingPolicy(int unitPrice) {
    if (unitPrice <= 0) {
        throw new IllegalArgumentException("unitPrice must be positive");
    }
    this.unitPrice = unitPrice;
}
~~~

Dù `unitPrice` đến từ literal, `Environment.getRequiredProperty(...)`, `@Value` hay cơ chế cấu hình khác, constructor vẫn phải bảo vệ invariant khi có thể. Container có thể resolve/convert một value nhưng **không tự hiểu mọi quy tắc nghiệp vụ**, ví dụ giá phải dương hoặc số lần thử tối đa.

Các bước thiết kế hợp lý:

1. **Khai báo invariant:** giá đơn vị dương, mã tiền tệ hợp lệ, dependency không null.
2. **Resolve dữ liệu:** lấy property/bean đúng nguồn, đúng tên, đúng kiểu.
3. **Validate tại constructor/factory:** không lưu trạng thái không hợp lệ.
4. **Test negative paths:** thiếu bean, null được truyền thủ công, sai value, ambiguity.
5. **Cho phép lỗi bootstrap có ý nghĩa:** không catch xong dùng fallback sai nghiệp vụ để che cấu hình.

Nếu dependency cần một thay đổi cấu hình hợp lệ trong suốt vòng đời, chọn thiết kế immutable value object hoặc chính sách cập nhật có kiểm soát. Constructor validation chỉ có tác dụng **tại thời điểm khởi tạo**; nó không tự ngăn một collaborator mutable bị thay đổi sai về sau.

## 10. Constructor injection với interface và unit testing

Một ưu điểm mạnh của constructor DI là test không cần Spring. Ví dụ hợp đồng:

~~~java
interface PriceLookup {
    int unitPrice(String sku);
}

final class OrderCalculator {
    private final PriceLookup lookup;

    OrderCalculator(PriceLookup lookup) {
        this.lookup = Objects.requireNonNull(lookup);
    }

    int total(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity");
        }
        return Math.multiplyExact(lookup.unitPrice(sku), quantity);
    }
}
~~~

Các class trên là snippet Java có thể đặt trong một file/test thích hợp; **không phải chương trình độc lập với `main`**. Trong unit test, inject một fake lambda:

~~~java
PriceLookup fake = sku -> 25;
OrderCalculator calculator = new OrderCalculator(fake);
System.out.println(calculator.total("ANY", 3)); // 75
~~~

Có thể kiểm tra cả null guard, input, overflow và behavior không cần tải Spring framework. Đó là khác biệt lớn so với service tự gọi container bằng **service locator pattern**:

~~~java
// Phản ví dụ minh họa:
PricingPolicy pricing = applicationContext.getBean(PricingPolicy.class);
~~~

Nếu mọi method nghiệp vụ đều tự lấy bean theo cách đó, danh sách dependency bị ẩn khỏi constructor, test cần mock container hoặc setup phức tạp, và runtime error có thể xuất hiện muộn.

**Không bắt buộc mọi collaborator phải là interface.** Khi chỉ có một implementation ổn định hoặc một value object, constructor nhận concrete class vẫn hợp lệ. Interface hữu ích khi có nhiều strategy, cần tách domain/infrastructure hoặc fake trong unit test.

## 11. Khi constructor có nhiều dependency

Constructor injection làm những dependency bắt buộc lộ rõ trong API. Nếu chữ ký chứa 12–15 collaborator, hãy kiểm tra **những trách nhiệm và lý do thay đổi** của class, thay vì coi một số lượng tham số cụ thể là lỗi. Một orchestrator có nhiều bước liên quan vẫn có thể hợp lý.

Đừng rút ngắn chữ ký bằng cách giấu collaborator trong `ApplicationContext`, field injection hoặc một `Dependencies` bag khổng lồ: độ phức tạp thực tế vẫn tồn tại. Lập nhóm method theo phần nghiệp vụ chúng sử dụng, rồi cân nhắc tách các trách nhiệm ít liên quan; chỉ gom thành value object khi những giá trị có cùng ý nghĩa và invariant. Việc tách phải được kiểm chứng để không làm đổi thứ tự xử lý và side effects.

## 12. Scope, lazy và trạng thái hợp lệ

| Trường hợp | Điều cần nhớ |
| --- | --- |
| Singleton không lazy (mặc định) | Thường được khởi tạo trong `ApplicationContext.refresh()`; dependency missing thường fail sớm |
| Singleton `@Lazy` | Có thể được tạo khi yêu cầu lần đầu; lỗi constructor có thể xuất hiện muộn |
| Prototype | Mỗi yêu cầu tạo bean thường chạy constructor mới và kiểm tra invariant riêng |
| Prototype inject trực tiếp vào singleton | Dependency thường được giải quyết một lần khi singleton được khởi tạo, không tự tạo prototype mới sau mỗi method call |
| Scoped proxy/provider | Có thể ảnh hưởng thời điểm/identity object được đưa vào; không đồng nghĩa constructor guard tự kiểm tra target cuối ở mọi request |
| Object được `new` thủ công | Spring không can thiệp, nhưng chính constructor guards Java vẫn hoạt động |
| Context đã đóng | Không tạo/lấy thêm managed dependencies từ context đã shutdown |

**Không đồng nhất “Spring đã inject non-null reference” với “mọi thao tác remote/database chắc chắn thành công”.** Một collaborator có thể không null nhưng kết nối ngoại vi lỗi sau đó. Constructor kiểm tra những invariant **khả thi và ổn định** tại thời điểm tạo; lỗi nghiệp vụ/ngoại vi vẫn cần được xử lý ở đúng lớp trách nhiệm.

Một bean singleton có state mutable phục vụ nhiều luồng phải được thiết kế thread-safe; `final` trên field chỉ bảo đảm reference không bị gán lại, không làm object phía sau tự thread-safe.

## 13. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `UnsatisfiedDependencyException` lúc startup | Constructor cần một bean không có candidate phù hợp | Kiểm tra `@Bean`, component registration/scan, type và qualifier |
| `NoSuchBeanDefinitionException` | Spring không có bean theo tên/kiểu bắt buộc | Đăng ký collaborator, kiểm tra cấu hình được nạp |
| `NoUniqueBeanDefinitionException` | Có nhiều bean ứng viên cho một tham số đơn trị | Dùng `@Qualifier`, `@Primary` hoặc tách lựa chọn nghiệp vụ |
| `BeanCurrentlyInCreationException` | Dependency cycle ở constructors/factories | Vẽ graph, tách trách nhiệm; không che chu trình bằng field injection |
| Bean service được `new` ngoài Spring rồi dependency null | Caller bypass container và không cung cấp hợp đồng | Constructor `requireNonNull`, manual wiring đúng hoặc lấy bean từ context |
| Bean factory tạo object với giá 0/âm | Cấu hình sai giá trị cần thiết | Validate ở `PricingPolicy` constructor; fail fast |
| `@Autowired` ở nhiều constructors required | Spring không rõ constructor bắt buộc | Giữ một constructor rõ, hoặc khai báo theo quy tắc lựa chọn được hỗ trợ |
| Quá nhiều constructor arguments | Service có thể chứa quá nhiều trách nhiệm | Refactor ranh giới lớp, không chỉ ẩn arguments bằng setters |
| Muốn `final` nên inject field trực tiếp | Field injection không phù hợp với mô hình final constructor assignment | Ưu tiên constructor injection |
| Nhiều threads sửa cùng singleton AuditTrail | Mutable list không tự thread-safe | Synchronization hoặc collection phù hợp/thiết kế stateless |
| Unit test phải khởi động cả Spring để tạo một service | Service phụ thuộc container/service locator | Truyền collaborator qua constructor; test bằng fake |
| Context khởi động thành công nhưng service vẫn lỗi ở request khác | Chỉ test một input; remote calls/logic có thể fail | Tách wiring test và nghiệp vụ/edge cases |
| Lỗi chỉ xuất hiện lần đầu `getBean` | Bean lazy/prototype trì hoãn instantiation | Kiểm tra thời điểm tạo, không chỉ nhìn trạng thái context |
| Thêm constructor mặc định tạo service thiếu dependency | Cho phép object tồn tại trong trạng thái sai | Bỏ constructor vô nghĩa, bắt buộc dependencies qua constructor |

**Quy trình debug:** xác định bean đang tạo, xem danh sách tham số constructor, kiểm tra các candidates cùng type, theo chuỗi `Caused by` đến lỗi gốc. Nếu đó là `IllegalArgumentException` từ constructor, xem cấu hình giá trị; nếu là missing/ambiguous bean, sửa registration/qualifier. Đừng catch `BeansException` ở bootstrap rồi cho ứng dụng hoạt động với null dependencies.

## 14. Kiểm thử ở hai cấp độ

**Unit test (không Spring):** tạo `PricingPolicy`, `AuditTrail` và `CheckoutService` bằng Java thuần; kiểm tra:

- `new CheckoutService(null, audit)` bị từ chối ngay.
- `new CheckoutService(pricing, null)` bị từ chối ngay.
- `new PricingPolicy(0)` bị từ chối.
- `checkout("BOOK", 2)` có receipt đúng và audit thêm đúng một event.
- `checkout("BOOK", 0)` bị từ chối; audit không được ghi.
- `checkout("UNKNOWN", 1)` bị từ chối theo hợp đồng SKU.

**Spring wiring test:** tạo context với `AppConfig` và `CheckoutService.class`, kiểm tra:

~~~java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {
    context.register(AppConfig.class, CheckoutService.class);
    context.refresh();

    CheckoutService service = context.getBean(CheckoutService.class);
    PricingPolicy pricing = context.getBean(PricingPolicy.class);
    if (service.pricing() != pricing) {
        throw new IllegalStateException("unexpected pricing bean");
    }
}
~~~

Đây là **snippet trích từ ngữ cảnh class demo**, không phải một file độc lập. Nó chứng minh *wiring*, không tự chứng minh mọi ca nghiệp vụ.

**Negative Spring integration test:** dùng cấu hình cố ý thiếu `AuditTrail` hoặc có hai bean `PricingPolicy` cùng type không chọn rõ. Kiểm tra loại lỗi/nguyên nhân, không khóa test theo toàn bộ nguyên văn stack trace vì thông điệp có thể thay đổi theo phiên bản Spring/JDK.

**Không dùng Java `assert` mặc định làm kiểm tra bắt buộc**, vì assertions có thể bị tắt nếu JVM chạy không có `-ea`. Dùng assertion của test framework hoặc biểu thức kiểm tra rồi ném exception.

## 15. Bài tập tự luyện có đáp án

**Bài 1 — Khởi tạo hợp lệ.** Service có constructor `S(A a, B b)`, không constructor khác. Nếu A tồn tại nhưng B không được đăng ký, Spring có thể trả một `S` với B=null được không?

**Đáp án:** Với dependency bắt buộc theo cơ chế constructor resolution bình thường, Spring phải giải quyết B; nếu thiếu, việc tạo bean thất bại, không nên âm thầm tạo service có B=null.

**Bài 2 — @Autowired.** Một bean Spring chỉ có một constructor công khai nhận hai collaborators. Có cần `@Autowired` không?

**Đáp án:** Không bắt buộc từ Spring Framework 4.3; container có thể chọn constructor duy nhất. Cần bảo đảm bean được đăng ký và dependencies resolve được.

**Bài 3 — Object bên ngoài Spring.** Ai đó gọi `new CheckoutService(null, new AuditTrail())`. Spring có chặn trước không?

**Đáp án:** Spring không tham gia lời gọi `new` này. Nhưng chính `Objects.requireNonNull(pricing)` trong constructor ném exception; invariant của class không phụ thuộc vào container.

**Bài 4 — final.** `private final AuditTrail audit` có làm danh sách nội bộ AuditTrail bất biến và thread-safe không?

**Đáp án:** Không. Nó chỉ giữ reference không đổi; state của `AuditTrail` vẫn có thể mutable. Cần thiết kế bảo vệ state riêng.

**Bài 5 — Config sai.** `PricingPolicy(0)` bị từ chối khi nào?

**Đáp án:** Ngay trong constructor PricingPolicy. Nếu Spring tạo bean từ factory trả `new PricingPolicy(0)`, lỗi thường được bọc trong bean creation exception.

**Bài 6 — Vòng phụ thuộc.** A constructor cần B, B constructor cần A. Chỉ cần đổi thứ tự định nghĩa bean để khởi động được không?

**Đáp án:** Không. Đây là vòng bắt buộc A→B→A, không có thứ tự tạo object đầy đủ nào giải quyết được; cần sửa thiết kế.

**Bài 7 — Nhiều candidates.** Context có hai PricingPolicy. Bản thân constructor một tham số `PricingPolicy pricing` có đủ để Spring biết chọn cái nào không?

**Đáp án:** Không nhất thiết; Spring còn xem qualifier, primary và các quy tắc phân giải khác. Khi thực sự mơ hồ, phải chỉ rõ lựa chọn hoặc cấu hình lại.

**Bài 8 — Trạng thái hợp lệ.** Constructor đã kiểm tra tất cả references khác null. Vậy mọi lời gọi checkout đều thành công?

**Đáp án:** Không. Method còn validate SKU, số lượng và có thể gặp overflow/ngoại lệ nghiệp vụ. Constructor valid state và method input validation là hai tầng khác nhau.

## 16. Checklist áp dụng

- [ ] Liệt kê dependency **bắt buộc** và đưa chúng vào constructor công khai.
- [ ] Tránh service tự `new` hoặc tự `getBean(...)` dependency ở chỗ không thuộc composition root.
- [ ] Giữ reference bắt buộc trong `private final` fields khi phù hợp.
- [ ] Dùng `Objects.requireNonNull`/validation rõ ràng cho invariant, không rely chỉ vào Spring.
- [ ] Không tạo constructor mặc định khiến object thiếu dependencies.
- [ ] Với một constructor, hiểu vì sao không bắt buộc `@Autowired`.
- [ ] Nếu nhiều constructors, nêu rõ constructor được chọn và semantics cần thiết.
- [ ] Kiểm tra class có được đăng ký thành bean không; annotation trong source không tự tạo bean.
- [ ] Phân giải candidate theo type/qualifier/primary thay vì dựa vào may rủi.
- [ ] Tránh dependency cycles và constructor với quá nhiều trách nhiệm.
- [ ] Phân biệt reference `final` với object mutable và thread safety.
- [ ] Phân biệt lỗi missing bean với constructor reject giá trị cấu hình không hợp lệ.
- [ ] Kiểm tra lazy/prototype nếu lỗi không xuất hiện ngay startup.
- [ ] Chạy Java 17+ và đối chiếu **đúng tám dòng stdout**.
- [ ] Với `javac`/`java`, sử dụng đầy đủ classpath Spring.
- [ ] Test riêng constructor invariants, business behavior và Spring wiring.

**Ghi nhớ:** Constructor injection không chỉ là cách “đưa bean A vào bean B”; đó còn là một **hợp đồng khởi tạo**. Khi dependency bắt buộc được khai báo trong constructor và kiểm tra hợp lệ ở cùng ranh giới, object không thoát ra dưới trạng thái thiếu collaborator thiết yếu. Spring Core Container lo **giải quyết và cung cấp các dependency đã đăng ký**, còn **thiết kế invariant và validation** vẫn do code Java bảo đảm.

### Tài liệu chính thức

- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [AnnotationConfigApplicationContext API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/AnnotationConfigApplicationContext.html)
