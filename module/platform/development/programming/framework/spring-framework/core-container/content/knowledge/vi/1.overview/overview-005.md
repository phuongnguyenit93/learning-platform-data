# Đồ thị phụ thuộc và trách nhiệm của container — Spring Framework Core Container

## 1. Mục tiêu: nhìn ứng dụng như một đồ thị

Một ứng dụng Java thường gồm nhiều đối tượng cộng tác: service dùng repository, bộ xử lý thanh toán dùng bộ tính giá và bộ ghi audit. **Đồ thị phụ thuộc (dependency graph)** biểu diễn *thành phần nào cần thành phần nào*. Spring **IoC container** đọc cấu hình bean rồi tạo, kết nối và quản lý những thành phần đó.

Sau bài học, bạn có thể:

- Vẽ graph có nhiều tầng, nhiều nhánh, nhiều consumer dùng chung dependency; xác định hướng các cạnh.
- Phân biệt **bean graph** với **method call graph** và quan hệ `extends`/`implements`.
- Giải thích trách nhiệm của `BeanFactory`, `ApplicationContext`, cấu hình bean, dependency resolution và injection.
- Lý giải eager singleton, lazy bean, prototype, vòng phụ thuộc constructor và `@DependsOn` mà không nhầm thứ tự tạo với chiều của cạnh.
- Chạy ví dụ độc lập bằng **Spring Framework 6.2.19 + Java 17+**, Maven hoặc `javac`/`java` và kiểm tra stdout.

Bài này tập trung vào **đồ thị kết nối và ranh giới quản lý của container**. Một dependency có thể được truyền bằng Java thuần mà không cần Spring; Spring giúp **tự động hóa bước lắp ghép dựa trên cấu hình**.

## 2. Node, edge và hướng mũi tên

Trong bài này, **A → B** nghĩa là **bean A phụ thuộc vào bean B**. Nó *không* có nghĩa A tạo trước B, không phải lúc nào A cũng gọi B trong mọi request, và không nói gì về kế thừa kiểu.

Ví dụ:

- `CheckoutService` cần `PriceService` để tính tổng.
- `CheckoutService` cần `AuditTrail` để ghi sự kiện.
- `PriceService` cần `ProductCatalog` để lấy đơn giá.
- Một bean tên `productCatalog` cung cấp implementation `FixedCatalog` cho interface `ProductCatalog`.

~~~mermaid
flowchart LR
    Checkout["checkoutService: CheckoutService"]
    Price["priceService: PriceService"]
    Audit["auditTrail: AuditTrail"]
    Catalog["productCatalog: ProductCatalog / FixedCatalog"]
    Checkout --> Price
    Checkout --> Audit
    Price --> Catalog
~~~

Nhìn theo cấu trúc:

~~~text
checkoutService
├── priceService
│   └── productCatalog
└── auditTrail
~~~

Khi thêm `ReportingService → ProductCatalog`, cả ReportingService và PriceService có thể dùng **cùng một bean** `productCatalog` nếu bean đó là singleton trong cùng context. Do có thể có nhiều cạnh trỏ tới một node, mô hình đúng là **đồ thị**, không chỉ là cây.

**Đọc đúng ba loại quan hệ:**

| Quan hệ | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Bean dependency graph | Bean nào cần bean nào? | `priceService → productCatalog` |
| Runtime call graph | Method nào gọi method nào? | `PriceService.total() → ProductCatalog.unitPrice()` |
| Type relationship | Class nào implements/extends kiểu nào? | `FixedCatalog implements ProductCatalog` |

Phép gọi một utility static, object được tạo tạm bằng `new` hoặc method nội bộ **không tự động tạo một cạnh bean graph**. Tương tự, cạnh dependency có thể tồn tại dù một luồng chạy cụ thể chưa gọi method của dependency.

### Đỉnh là bean definition hay object?

Cần tách:

1. **Bean definition:** metadata Spring dùng để biết tên, factory/loại bean, scope và cách khởi tạo/cấu hình.
2. **Bean instance:** object thực tế được container tạo/trả về khi cần.
3. **Loại Java:** interface hoặc class mà injection point khai báo.

Một bean definition `singleton` thường ánh xạ tới một instance trên mỗi container; một bean definition `prototype` có thể dẫn tới nhiều instance. Khi có AOP proxy, object được inject có thể là **proxy**, không đơn thuần là class triển khai ban đầu. Do đó *đồ thị definition* không luôn trùng 1–1 với *đồ thị instance tại một thời điểm*.

## 3. Container có trách nhiệm gì?

Spring không yêu cầu một sơ đồ graph nhập bằng tay. Nó đọc cấu hình và các điểm injection để xác định những collaborator cần thiết.

**Bước logic chính:**

1. **Đăng ký bean definitions:** từ `@Configuration`/`@Bean`, component scanning (`@Component`, `@Service`, `@Repository`...), XML hoặc đăng ký bằng API.
2. **Xử lý cấu hình và metadata:** nhận kiểu khai báo, tên, scope, các điều kiện và các cơ chế hậu xử lý cấu hình liên quan.
3. **Phân giải dependency:** với constructor/factory-method arguments, setter/field injection phù hợp, tìm bean ứng viên theo type, qualifier, primary và quy tắc của Spring.
4. **Tạo và cấu hình bean:** tạo các dependency cần thiết, gọi factory/constructor, gán các phụ thuộc và áp dụng extension points tương ứng.
5. **Quản lý vòng đời:** thực thi initialization hooks, giữ bean theo scope, cung cấp bean qua context và gọi destruction hooks thích hợp lúc đóng context/scope.
6. **Báo lỗi cấu hình:** thiếu bean, nhiều bean mơ hồ, chu trình khởi tạo hoặc lỗi ngay trong factory/constructor.

**Không** thuộc trách nhiệm tự động của container: thiết kế logic tính giá, duyệt đơn hàng, xử lý giao dịch nghiệp vụ, xác thực dữ liệu theo domain hoặc bảo đảm thread safety cho singleton chứa trạng thái mutable. Spring có các module khác hỗ trợ những mối quan tâm ấy, nhưng riêng IoC container **không biết nghiệp vụ của bạn**.

### BeanFactory và ApplicationContext

- `BeanFactory` là hợp đồng lõi để tra cứu và làm việc với bean.
- `ApplicationContext` mở rộng các khả năng đó: tích hợp lifecycle thuận tiện, event, message resources, môi trường cấu hình và các cơ chế khác; đây là lựa chọn thông thường khi dùng Spring.
- `AnnotationConfigApplicationContext` là một implementation có thể tạo context trực tiếp từ Java configuration class, không cần Spring Boot/Servlet container.

Ví dụ khai báo:

~~~java
@Bean
PriceService priceService(ProductCatalog catalog) {
    return new PriceService(catalog);
}
~~~

Đây chỉ là **mã minh họa bên trong configuration class**. Tham số `ProductCatalog catalog` nêu một dependency của bean `priceService`. Container giải quyết bean cho tham số ấy rồi gọi factory method.

**Thời điểm đăng ký khác thời điểm khởi tạo:** bean definition có thể đã được biết nhưng bean instance chưa được tạo; mặc định nhiều singleton không lazy được khởi tạo trong lúc `ApplicationContext.refresh()`, còn lazy/prototype có thể chờ đến lúc truy xuất.

## 4. Ví dụ Java 17+ độc lập: graph nhiều tầng

Dùng **Spring Framework 6.2.19**, Maven và JDK 17+. Không cần Spring Boot, database hoặc máy chủ web. Lần đầu Maven có thể cần kết nối Internet để tải JAR.

~~~text
bean-graph-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── DependencyGraphDemo.java
~~~

### 4.1. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-graph-demo</artifactId>
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
                    <mainClass>demo.DependencyGraphDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven tự giải quyết các dependency transitively của `spring-context`; chỉ chép mỗi `spring-context.jar` vào classpath thông thường là chưa đủ.

### 4.2. File `src/main/java/demo/DependencyGraphDemo.java`

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class DependencyGraphDemo {
    private DependencyGraphDemo() {}

    public interface ProductCatalog {
        int unitPrice(String sku);
    }

    public static final class FixedCatalog implements ProductCatalog {
        @Override
        public int unitPrice(String sku) {
            if (!"BOOK".equals(sku)) {
                throw new IllegalArgumentException("unknown sku");
            }
            return 15;
        }
    }

    public static final class PriceService {
        private final ProductCatalog catalog;

        public PriceService(ProductCatalog catalog) {
            this.catalog = Objects.requireNonNull(catalog);
        }

        public int total(String sku, int quantity) {
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            return Math.multiplyExact(catalog.unitPrice(sku), quantity);
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

    public static final class CheckoutService {
        private final PriceService prices;
        private final AuditTrail audit;

        public CheckoutService(PriceService prices, AuditTrail audit) {
            this.prices = Objects.requireNonNull(prices);
            this.audit = Objects.requireNonNull(audit);
        }

        public String confirm(String sku, int quantity) {
            int total = prices.total(sku, quantity);
            String event = sku + " x " + quantity + " => " + total;
            audit.record(event);
            return event;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public ProductCatalog productCatalog() {
            return new FixedCatalog();
        }

        @Bean
        public AuditTrail auditTrail() {
            return new AuditTrail();
        }

        @Bean
        public PriceService priceService(ProductCatalog catalog) {
            return new PriceService(catalog);
        }

        @Bean
        public CheckoutService checkoutService(
                PriceService prices, AuditTrail audit) {
            return new CheckoutService(prices, audit);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            CheckoutService checkout =
                    context.getBean(CheckoutService.class);
            AuditTrail audit = context.getBean(AuditTrail.class);

            System.out.println("confirm=" + checkout.confirm("BOOK", 2));
            System.out.println("audits=" + audit.snapshot());
            System.out.println("catalogSingleton=" +
                    (context.getBean(ProductCatalog.class) ==
                     context.getBean(ProductCatalog.class)));
            System.out.println("priceSingleton=" +
                    (context.getBean(PriceService.class) ==
                     context.getBean(PriceService.class)));
            System.out.println("priceRegistered=" +
                    context.containsBean("priceService"));
        }
    }
}
~~~

Có **một top-level public class** và các class/interface lồng bên trong, nên tên file là `DependencyGraphDemo.java`. `@Configuration(proxyBeanMethods = false)` dùng được vì các factory method **không gọi trực tiếp nhau**; Spring cung cấp collaborators thông qua tham số method. Nếu tự gọi `priceService(productCatalog())` bên trong `@Bean` ở chế độ này, bạn đang thực hiện lời gọi Java thông thường, có thể tạo instance không theo wiring/singleton mong muốn.

### 4.3. Chạy bằng Maven

Ở thư mục `bean-graph-demo`:

~~~bash
java -version
mvn -version
mvn -q clean compile exec:java
~~~

**Chính xác 5 dòng stdout do chương trình `main` in:**

~~~text
confirm=BOOK x 2 => 30
audits=[BOOK x 2 => 30]
catalogSingleton=true
priceSingleton=true
priceRegistered=true
~~~

Output của `java -version`, `mvn -version` và logging Maven/Spring (nếu cấu hình có) **không tính vào năm dòng stdout ứng dụng**.

### 4.4. Chạy bằng `javac` và `java` trực tiếp

Mã cần classpath có Spring và các thư viện transitively cần thiết. Từ thư mục gốc dự án, nhờ Maven tạo classpath:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/DependencyGraphDemo.java
java -cp "out:$(cat classpath.txt)" demo.DependencyGraphDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/DependencyGraphDemo.java
java -cp "out;$deps" demo.DependencyGraphDemo
~~~

Dấu phân cách classpath là `:` trên Unix và `;` trên Windows. Hai cách chạy thực thi **cùng một main class** và cho năm dòng output như nhau. Nếu `javac` báo `package org.springframework... does not exist`, hãy kiểm tra classpath/JAR thay vì sửa code DI.

## 5. Đọc graph từ các factory method

| Bean name | Kiểu bean | Cạnh dependency trực tiếp |
| --- | --- | --- |
| `productCatalog` | `ProductCatalog` (object thực tế `FixedCatalog`) | Không có |
| `auditTrail` | `AuditTrail` | Không có |
| `priceService` | `PriceService` | `productCatalog` |
| `checkoutService` | `CheckoutService` | `priceService`, `auditTrail` |

Container lần theo quan hệ:

1. Nó biết các factory method được `@Bean` công bố.
2. Khi cần `priceService`, nó phải có `ProductCatalog` phù hợp; một ứng viên duy nhất là `productCatalog`.
3. Khi cần `checkoutService`, nó phải có `PriceService` và `AuditTrail` phù hợp.
4. Hai lời gọi `context.getBean(ProductCatalog.class)` trong cùng context trả cùng bean **singleton** mặc định: `catalogSingleton=true`.
5. `CheckoutService.confirm(...)` tự tính tiền và ghi audit. Container **không gọi nghiệp vụ confirm tự động**, nó chỉ lắp ghép object để ứng dụng sử dụng.

### Graph hợp lệ không có nghĩa thứ tự khởi tạo được cố định

Với một đồ thị **không có chu trình** và tất cả dependency được khởi tạo trước consumer, bạn có thể suy nghĩ bằng **thứ tự topo**: cần catalog trước price, cần price và audit trước checkout. Nhưng:

- `productCatalog` và `auditTrail` độc lập, nên **không có quy tắc nghiệp vụ** bắt buộc cái nào tạo trước.
- Thứ tự xuất hiện trong sơ đồ hoặc tên method `@Bean` **không phải hợp đồng tổng quát** về startup order.
- Lazy, prototype và những cơ chế tạo theo nhu cầu khiến thời điểm tạo có thể khác.
- Graph có thể chứa **chu trình**; vì vậy không được giả định mọi dependency graph là DAG.

Không viết code dựa vào việc hai singleton **không liên quan** luôn được khởi tạo theo một thứ tự tình cờ quan sát được trên một máy.

## 6. Vòng phụ thuộc và cách xử lý

Một đồ thị không có chu trình thường dễ xây dựng: container có thể giải quyết các node phụ thuộc rồi tạo consumer. **Constructor cycle** điển hình:

~~~java
final class A {
    A(B b) {}
}
final class B {
    B(A a) {}
}
~~~

Đây chỉ là **mã minh họa**, chưa phải chương trình Spring độc lập. Nếu đăng ký A và B làm bean, mỗi constructor bắt buộc nhận bean còn lại, việc tạo A yêu cầu B trong khi tạo B lại yêu cầu A: A → B → A. Spring thường báo lỗi, ví dụ `BeanCurrentlyInCreationException` (có thể nằm trong chuỗi exception bọc khác).

**Hướng xử lý đúng:** xem lại nhiệm vụ của từng class, tách vòng sở hữu, dùng abstraction hoặc sự kiện nếu thực sự phù hợp, và làm dependency trở nên rõ. Đổi ngẫu nhiên constructor injection sang field/setter chỉ nhằm né lỗi có thể tạo bean chưa hoàn chỉnh, không giải quyết được kiến trúc.

Một số setter cycles có thể được giải quyết nhờ cơ chế reference sớm trong cấu hình nhất định, nhưng **không bảo đảm tất cả trường hợp** và không phải lý do để thiết kế vòng phụ thuộc có chủ đích.

## 7. Dependency trực tiếp, `@DependsOn` và thứ tự khởi tạo

Nếu B thực sự **sử dụng đối tượng A**, nên khai báo A là dependency qua constructor/factory argument. Nhưng đôi khi một bean cần một *tác dụng phụ khởi tạo* của bean khác, không nhận reference của nó. Khi ấy có thể dùng `@DependsOn`:

~~~java
@Bean
@org.springframework.context.annotation.DependsOn("auditBootstrap")
public AuditTrail auditTrail() {
    return new AuditTrail();
}
~~~

Đây là ví dụ minh họa, **không thay thế method `auditTrail()` trong chương trình chạy**. Nó chỉ có nghĩa khi đã đăng ký bean tên `auditBootstrap`. Container bảo đảm bean được đặt tên ấy được khởi tạo trước `auditTrail`, **không tự inject nó** làm tham số.

Với các bean singleton, quan hệ `depends-on` cũng có ý nghĩa khi hủy: bean **phụ thuộc** bị hủy trước bean **được phụ thuộc**. Không dùng `@DependsOn` thay cho dependency thực hoặc như cách che cấu trúc sai.

**Cũng không dùng `@Order` để ép mọi singleton khởi tạo theo thứ tự.** `@Order` thường áp dụng cho thứ tự của component trong những tập hợp/cơ chế có hỗ trợ, không phải quy tắc startup order tổng quát.

## 8. Thiếu bean, nhiều ứng viên và dependency được trì hoãn

Nếu injection point yêu cầu `ProductCatalog`:

- **Không có bean ứng viên:** Spring không thể hoàn tất tạo consumer (có thể xuất hiện `NoSuchBeanDefinitionException` / `UnsatisfiedDependencyException`). Kiểm tra cấu hình đăng ký, component scan, điều kiện, profile và kiểu bean được khai báo.
- **Có nhiều ứng viên:** Spring có thể không xác định được một lựa chọn duy nhất (`NoUniqueBeanDefinitionException`). Dùng `@Primary`, `@Qualifier`, hoặc sửa cấu hình để loại mơ hồ khi hợp đồng thật chỉ cần một bean.
- **Thực sự cần nhiều bean:** tùy bài toán, có thể inject `List<ProductCatalog>`, `Map<String,ProductCatalog>` hoặc truy xuất bằng `ObjectProvider<ProductCatalog>`.

**Ví dụ minh họa, chưa phải file độc lập vì `OtherCatalog` chưa khai báo:**

~~~java
@Bean ProductCatalog firstCatalog() { return new FixedCatalog(); }
@Bean ProductCatalog secondCatalog() { return new OtherCatalog(); }
~~~

Hai bean cùng interface có thể khiến điểm injection một giá trị đơn lẻ bị mơ hồ, trừ khi có quy tắc phân giải phù hợp. Đừng suy ra container có thể tự biết implementation nào đúng theo ý định nghiệp vụ.

### Scope ảnh hưởng đồ thị instance

| Scope/cơ chế | Ảnh hưởng |
| --- | --- |
| `singleton` (mặc định) | Một bean instance cho mỗi bean definition trong một context; không phải toàn JVM |
| `prototype` | Container tạo bean mỗi lần có yêu cầu tạo bean tương ứng |
| Prototype inject trực tiếp vào singleton | Thường được giải quyết khi **singleton được tạo**; không tự có prototype mới sau mỗi lời gọi method |
| `@Lazy` | Có thể trì hoãn tạo bean khi chưa cần; không xóa quan hệ dependency logic |
| `ObjectProvider<T>` | Cho phép mã có nhu cầu truy xuất bean sau, khi cần; phù hợp nếu muốn giải quyết động theo từng thao tác |
| Web request/session scope | Cần ngữ cảnh web phù hợp, không tự có trong context Java thuần |

Nếu muốn prototype mới mỗi lần xử lý từ singleton, cần thiết kế thêm cách lấy instance theo lượt (ví dụ provider), **không chỉ gắn annotation scope vào bean đích**.

### Container không tự quản lý mọi object Java

Một instance tạo bằng `new` ngoài container không tự động được inject, nhận callbacks hay được quản lý như bean. Có thể tạo cùng graph bằng tay:

~~~java
ProductCatalog catalog = new FixedCatalog();
AuditTrail audit = new AuditTrail();
PriceService prices = new PriceService(catalog);
CheckoutService checkout = new CheckoutService(prices, audit);
~~~

Đoạn trên **chỉ minh họa trong phạm vi lớp demo**, không phải tệp chạy độc lập. Đây vẫn là dependency injection theo nghĩa thiết kế; Spring cung cấp cơ chế registration, resolution và lifecycle thay vì buộc bạn tự lắp ghép mọi object.

## 9. Vòng đời bean và phần trách nhiệm người lập trình

| Container thường quản lý | Ứng dụng chịu trách nhiệm |
| --- | --- |
| Đăng ký cấu hình và bean definitions | Chia class theo đúng trách nhiệm, chọn abstraction và hợp đồng |
| Chọn ứng viên injection phù hợp | Khai báo dependency bắt buộc công khai, ưu tiên constructor injection |
| Khởi tạo/configure/hậu xử lý managed bean | Viết logic tính tiền, ghi audit, validate và lỗi nghiệp vụ |
| Scope/lifecycle callbacks thích hợp | Quản lý tài nguyên ngoài Spring, trạng thái dùng chung và thread safety |
| Cung cấp bean theo type/name và đóng context | Chọn điểm khởi động, gọi method nghiệp vụ và dừng ứng dụng đúng |

Với `@Bean` có init/destroy callback hoặc bean triển khai lifecycle interfaces, container thực hiện callbacks phù hợp. Nhưng không phải mọi bean đều được hủy như nhau: ví dụ prototype được container tạo nhưng container **không tự quản lý đầy đủ phần hủy sau khi giao cho caller**. Đối với singleton, context thường thực hiện hủy khi được đóng.

Không mặc định bean singleton có thể giữ thông tin theo từng request trong field mutable mà không đồng bộ; nhiều luồng/caller có thể cùng sử dụng instance ấy.

## 10. Debug khi graph lắp ghép thất bại

| Dấu hiệu | Nguyên nhân khả dĩ | Bước điều tra |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` hoặc `UnsatisfiedDependencyException` | Dependency bắt buộc không có ứng viên | Kiểm tra tên/type/scan/package/profile và @Bean |
| `NoUniqueBeanDefinitionException` | Quá nhiều ứng viên cùng kiểu | Dùng qualifier/primary hoặc sửa graph |
| `BeanCurrentlyInCreationException` | Một chu trình khởi tạo | Tìm A→B→…→A và xem lại thiết kế |
| Bean tạo bởi `new` không được inject | Object không do Spring quản lý | Lấy bean từ context hoặc DI thủ công |
| Bean lazy lỗi khi dùng lần đầu | Lỗi wiring bị trì hoãn | Truy các dependencies của bean vừa requested |
| Prototype không mới mỗi lời gọi trên singleton | Dependency được inject một lần | Dùng provider/lookup nếu cần mỗi lần mới |
| Muốn ép thứ tự giữa bean không liên quan | Nhầm declaration order với dependency order | Thể hiện cạnh dependency thực hoặc @DependsOn có chủ đích |
| Context refresh thất bại | Eager singleton có lỗi lúc tạo | Đọc chuỗi `Caused by` tìm dependency gốc |

**Quy trình kiểm tra:**

1. Lấy bean entry point mà ứng dụng đang yêu cầu.
2. Vẽ các cạnh từ constructor/factory method parameters; ghi bean thực tế mà interface được ánh xạ tới.
3. Xác định bean nào thiếu/trùng ứng viên; đừng chỉ nhìn exception wrapper.
4. Tìm chu trình, cả các quan hệ init-only như `@DependsOn`.
5. Kiểm tra scope, `@Lazy` và vị trí provider có thể trì hoãn giải quyết.
6. Đọc nguyên nhân gốc trong `Caused by` hoặc stack trace của bean bị lỗi.
7. Sửa dependency registration/thiết kế, chạy lại ví dụ với output mong đợi.

Không bắt mọi lỗi khởi tạo container rồi tiếp tục ứng dụng với dependency null; thông thường đó là **lỗi cấu hình cần sửa rõ ràng**.

## 11. Kiểm thử hành vi và kiểm thử wiring

Hai loại test bổ sung nhau:

- **Unit test:** tạo service bằng constructor với fake `ProductCatalog`, không cần Spring; kiểm tra `PriceService.total` có logic đúng.
- **Integration test wiring:** tạo `AnnotationConfigApplicationContext(AppConfig.class)` rồi `getBean(CheckoutService.class)` để xác nhận config đăng ký đủ dependency, không mơ hồ và đúng scope.

Đoạn sau chỉ là **minh họa dùng bên trong một method/class nơi truy cập được các nested types**:

~~~java
ProductCatalog fake = sku -> 8;
PriceService prices = new PriceService(fake);
System.out.println(prices.total("ignored", 3)); // 24.
~~~

Unit test PASS không chứng minh cấu hình bean đúng; context khởi tạo thành công cũng không chứng minh nghiệp vụ đúng. Đồ thị rõ ràng giúp **test được cả hai**.

## 12. Những nhầm lẫn cần tránh

1. **Bean graph giống call graph?** Không. Dependency không đồng nghĩa lời gọi method ở mọi đường xử lý.
2. **Spring tự quản lý mọi object được `new`?** Không. Chỉ object/bean được đăng ký và quản lý theo cơ chế phù hợp.
3. **Graph luôn là DAG?** Không. Có thể cấu hình chu trình; constructor cycle thường không được giải quyết.
4. **Có một thứ tự khởi tạo duy nhất?** Không. Dependency áp đặt ràng buộc trước/sau ở những node liên quan; node độc lập không có thứ tự tổng quát phải dựa vào.
5. **`@DependsOn` thay cho DI?** Không; nó yêu cầu init order, không truyền collaborator như constructor/factory parameter.
6. **`@Order` kiểm soát mọi thứ tự tạo singleton?** Không.
7. **`@Lazy` xóa dependency?** Không; chỉ ảnh hưởng thời điểm tạo/truy xuất trong trường hợp phù hợp.
8. **Prototype inject vào singleton tự đổi instance ở mỗi method call?** Không.
9. **Một `@Component` ở bất kỳ package nào tự xuất hiện trong context?** Không, cần đăng ký/scan phù hợp.
10. **Spring IoC container đòi Spring Boot?** Không; chương trình này chỉ dùng `spring-context` với Java 17.

## 13. Bài tập có đáp án

**Bài 1.** Service A cần B, C; cả B và C đều cần D. Vẽ graph, cho biết nếu D là singleton thì B/C có chung D không.

**Đáp án:** Có bốn node theo bean definitions A, B, C, D và các cạnh A→B, A→C, B→D, C→D. Cả B/C có thể nhận **cùng bean singleton D** nếu injection trỏ tới cùng definition trong một context. Không được suy ra toàn context chỉ có bốn object, vì còn config/infrastructure.

**Bài 2.** A nhận B qua constructor, B nhận C, C nhận A. Cần tạo A trước hay C trước?

**Đáp án:** Không có thứ tự constructor nào giải quyết vòng A→B→C→A. Cần thay đổi thiết kế hoặc hợp đồng dependency, không đảo tên các method `@Bean`.

**Bài 3.** Context có hai bean cùng interface `ProductCatalog`; `PriceService` cần một. Spring làm gì?

**Đáp án:** Nếu không có cách chọn duy nhất, injection có thể thất bại vì ambiguity. Sử dụng qualifier/primary hoặc thay đổi đăng ký bean cho rõ.

**Bài 4.** Một bean prototype được inject vào singleton. Mỗi lần singleton gọi collaborator có object mới không?

**Đáp án:** Không tự động. Thông thường singleton giữ instance đã inject khi khởi tạo; muốn mới theo lượt cần provider/lookup tương ứng.

**Bài 5.** `@DependsOn("bootstrap")` có đưa object `bootstrap` vào constructor của bean được annotation không?

**Đáp án:** Không. Nó chỉ khai báo ràng buộc khởi tạo theo tên (và ảnh hưởng thứ tự hủy singleton thích hợp), không tự cung cấp object làm đối số.

## 14. Checklist áp dụng

- [ ] Xác định node là bean nào và phạm vi của từng bean.
- [ ] Vẽ cạnh theo hướng **consumer → dependency**.
- [ ] Đọc được factory/constructor parameter tạo ra mỗi cạnh.
- [ ] Phân biệt kiểu interface, bean definition, object instance và runtime call graph.
- [ ] Kiểm tra bean thiếu/trùng và các quy tắc qualifier/primary.
- [ ] Phát hiện vòng constructor và tránh che dependency bằng service locator.
- [ ] Không dựa vào thứ tự khai báo bean không liên quan.
- [ ] Dùng `@DependsOn` chỉ khi thực sự có nhu cầu thứ tự init đặc biệt.
- [ ] Kiểm tra singleton, prototype, lazy/provider và lifecycle theo nhu cầu.
- [ ] Chạy ví dụ JDK17+ và đối chiếu đúng **năm dòng stdout**.
- [ ] Test hành vi với fake dependency và test wiring bằng context.

**Tóm lại:** Dependency graph trả lời **“bean nào cần bean nào?”**. Spring Core Container cung cấp cơ chế **đăng ký, chọn, tạo, inject và quản lý bean**, còn việc phân chia trách nhiệm và logic kinh doanh đúng vẫn thuộc về người thiết kế ứng dụng.

### Tài liệu chính thức

- [Spring Bean Dependencies](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html)
- [Java Configuration / @Bean](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html)
- [Composing Java-based Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html)
- [Using depends-on](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html)
