# So sánh ứng dụng có container với cách lắp ghép thủ công

## 1. Cùng một bài toán, hai cách tạo đồ thị đối tượng

Trong Java, một object thường cần object khác để hoàn thành nhiệm vụ. Ví dụ `GreetingService` cần một `Formatter` để tạo lời chào và một `ResourceProbe` mô phỏng tài nguyên phải đóng khi kết thúc ứng dụng.

Có **hai cách hợp lệ** để dựng đồ thị phụ thuộc ấy:

1. **Lắp ghép thủ công (manual wiring):** mã khởi động tự dùng `new`, truyền các object vào constructor, giữ reference và tự đóng tài nguyên đúng thời điểm.
2. **Dùng Spring IoC Container:** một class cấu hình khai báo bean definitions. `ApplicationContext` tạo các bean, giải quyết tham số phụ thuộc, cung cấp bean theo scope và gọi callback hủy thích hợp khi context đóng.

Điều quan trọng là **business logic có thể giữ nguyên**. Sự khác biệt chính nằm ở **ai chịu trách nhiệm tạo, chọn, kết nối, cấu hình và quản lý vòng đời của các đối tượng**, không phải ở thuật toán xử lý lời chào.

| Câu hỏi | Tự lắp ghép | Spring Core Container |
| --- | --- | --- |
| Ai tạo `Formatter`? | Composition root gọi `new VietnameseFormatter()` | Factory method `@Bean formatter()` trả về object |
| Ai chọn dependency cho service? | Caller truyền qua constructor | Container resolve tham số của `@Bean greetingService(...)` |
| Ai gọi `GreetingService` constructor? | Caller trực tiếp | Factory method của bean gọi constructor với dependency đã được Spring cấp |
| Ai quyết định chia sẻ instance? | Code tự giữ/reuse references | Bean scope; mặc định `singleton` theo definition/container |
| Ai gọi cleanup? | Caller phải chủ động | Container gọi destroy callback của các bean phù hợp khi `close()` |
| Có cần `ApplicationContext`? | Không | Có một implementation context/bean factory phù hợp |
| Logic nghiệp vụ có nhất thiết phụ thuộc Spring API? | Không | **Cũng không**; có thể giữ service là Java thuần |
| Có tự động đúng mọi cấu hình không? | Không | Không; thiếu/mơ hồ dependency vẫn làm bootstrap thất bại |

**Không đánh đồng “manual wiring” với thiết kế xấu.** Constructor injection là kỹ thuật Java thuần và cũng là nền để Spring inject các phụ thuộc. Với chương trình nhỏ, lắp ghép thủ công có thể là giải pháp dễ hiểu nhất. Khi dependency graph, môi trường cấu hình và lifecycle phức tạp, container giúp tập trung các trách nhiệm ấy.

## 2. Đọc đồ thị đối tượng và xác định ranh giới trách nhiệm

Hai đường khởi tạo sẽ tạo **cùng hình dạng đồ thị**:

~~~text
                    GreetingService
                     /           \
                    v             v
               Formatter      ResourceProbe
                    |              |
                    v              v
            VietnameseFormatter  close()

    MANUAL COMPOSITION                SPRING COMPOSITION
    ------------------                ------------------
    new VietnameseFormatter()          @Bean Formatter
    new ResourceProbe()                 @Bean ResourceProbe
    new GreetingService(f, p)           @Bean GreetingService(f, p)
    gọi p.close()                       context.close()
~~~

`GreetingService` chỉ nhận **hai reference**, không cần biết chúng đến từ biến local của `main` hay từ container. Trong ví dụ, nó **không gọi `new VietnameseFormatter()` bên trong constructor**; nếu làm vậy, service bị buộc vào implementation và khó thay bằng fake trong kiểm thử.

**Composition root** là nơi ứng dụng tập trung việc kết nối các phụ thuộc (thường tại `main`, bootstrap hoặc một module cấu hình). Ở phương án thủ công, `main` tự thực hiện; ở phương án Spring, `AppConfig` diễn đạt graph bằng `@Bean`, còn context tổ chức việc instantiate và wiring.

**Ranh giới ownership:** nơi **tạo/đăng ký** tài nguyên thường cần quyết định nơi **đóng** nó. Spring hỗ trợ callback theo scope, nhưng không thể tự dọn mọi object do code Java tùy ý tạo ra ở bên ngoài container.

## 3. Cấu trúc project Java 17 + Spring Framework thuần

Chúng ta đặt **cả hai cách trong cùng một file Java**, để khác biệt không đến từ hai implementation business logic. Không cần Spring Boot, database, component scanning hay HTTP server.

Yêu cầu: **JDK 17+**, **Maven 3.9+**, và quyền truy cập Maven Central/mirror ở lần tải dependencies đầu. Sử dụng Spring Framework `7.0.9` để phiên bản trong ví dụ nhất quán.

~~~text
manual-vs-spring-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ManualVsSpringDemo.java
~~~

Tạo tệp `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>manual-vs-spring-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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
                    <mainClass>demo.ManualVsSpringDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp `AnnotationConfigApplicationContext`, `@Configuration` và `@Bean`. Maven giải quyết các Spring dependencies cần thiết transitively, nên bạn không phải tải thủ công từng JAR. `maven.compiler.release=17` yêu cầu biên dịch theo API và bytecode Java 17.

**Lưu ý:** phần manual trong file vẫn có thể chạy **mà không có container** về mặt thiết kế; nhưng vì **cùng tệp** còn chứa import/class cấu hình Spring, việc biên dịch toàn bộ tệp demo vẫn cần `spring-context` trên classpath. Muốn làm chương trình hoàn toàn không có thư viện Spring, hãy tách các interface/class nghiệp vụ và entry point manual ra một project Java thuần.

## 4. Mã hoàn chỉnh: một service, hai composition roots

Tạo `src/main/java/demo/ManualVsSpringDemo.java`:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class ManualVsSpringDemo {

    private ManualVsSpringDemo() {
    }

    // Hợp đồng business: không nhập bất kỳ API Spring nào.
    interface Formatter {
        String format(String name);
    }

    static final class VietnameseFormatter implements Formatter {
        @Override
        public String format(String name) {
            return "Xin chao, " + name;
        }
    }

    // Mô phỏng một resource có trạng thái đóng.
    // Không phải kết nối mạng/file thật.
    public static final class ResourceProbe {
        private boolean closed;

        public boolean isClosed() {
            return closed;
        }

        public void close() {
            closed = true;
        }
    }

    static final class GreetingService {
        private final Formatter formatter;
        private final ResourceProbe probe;

        GreetingService(Formatter formatter, ResourceProbe probe) {
            this.formatter = formatter;
            this.probe = probe;
        }

        String greet(String name) {
            return formatter.format(name) + "!";
        }

        boolean hasDependencies(Formatter f, ResourceProbe p) {
            return formatter == f && probe == p;
        }
    }

    // Spring-only composition root.
    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public Formatter formatter() {
            return new VietnameseFormatter();
        }

        @Bean(destroyMethod = "close")
        public ResourceProbe resourceProbe() {
            return new ResourceProbe();
        }

        @Bean
        public GreetingService greetingService(
                Formatter formatter, ResourceProbe resourceProbe) {
            return new GreetingService(formatter, resourceProbe);
        }
    }

    public static void main(String[] args) {
        // ----- 1) Manual wiring -----
        Formatter manualFormatter = new VietnameseFormatter();
        ResourceProbe manualProbe = new ResourceProbe();
        GreetingService manualService =
                new GreetingService(manualFormatter, manualProbe);

        String manualMessage = manualService.greet("Lan");
        System.out.println("manual.message=" + manualMessage);
        System.out.println("manual.wiring="
                + manualService.hasDependencies(manualFormatter, manualProbe));
        System.out.println("manual.closed.before=" + manualProbe.isClosed());

        // Caller sở hữu và tự đóng resource trong ví dụ manual.
        manualProbe.close();
        System.out.println("manual.closed.after=" + manualProbe.isClosed());

        // ----- 2) Spring Container wiring -----
        ResourceProbe managedProbe;
        String springMessage;

        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            Formatter managedFormatter = context.getBean(Formatter.class);
            managedProbe = context.getBean(ResourceProbe.class);
            GreetingService managedService =
                    context.getBean(GreetingService.class);

            springMessage = managedService.greet("Lan");
            System.out.println("spring.message=" + springMessage);
            System.out.println("spring.wiring="
                    + managedService.hasDependencies(
                            managedFormatter, managedProbe));
            System.out.println("spring.singleton="
                    + (managedService == context.getBean(GreetingService.class)));
            System.out.println("spring.closed.before=" + managedProbe.isClosed());
        }

        // try-with-resources đã gọi context.close(),
        // và Spring gọi destroyMethod="close" trên bean ResourceProbe.
        System.out.println("spring.closed.after=" + managedProbe.isClosed());
        System.out.println("same.business.result="
                + manualMessage.equals(springMessage));
    }
}
~~~

### Giải thích vì sao so sánh này công bằng

1. Hai cách dùng **cùng** `GreetingService`, `Formatter`, `VietnameseFormatter` và `ResourceProbe`. Không viết thuật toán riêng cho Spring.
2. Manual `main` tạo formatter và probe rồi đưa **chính hai reference ấy** vào constructor `GreetingService`.
3. Spring `AppConfig` khai báo ba `@Bean` factory methods. Khi tạo bean `greetingService`, Spring resolve `Formatter` và `ResourceProbe` từ context theo type rồi truyền cho factory method.
4. `@Configuration(proxyBeanMethods = false)` phù hợp vì các phương thức `@Bean` **không gọi trực tiếp lẫn nhau**. Nếu trong method `greetingService()` tự gọi `formatter()` ở chế độ này, đó có thể là lời gọi Java thông thường tạo thêm object ngoài lookup singleton. Ví dụ tránh sai sót ấy bằng injection qua **tham số factory method**.
5. `GreetingService` và các dependency của nó dùng scope mặc định `singleton` trong context hiện tại. Vì vậy hai lần lookup cùng bean `GreetingService` trả cùng reference.
6. Với manual, programmer chủ động gọi `manualProbe.close()`. Với Spring, factory `@Bean(destroyMethod="close")` chỉ rõ callback; `try-with-resources` đóng context và Spring sẽ gọi callback ấy theo vòng đời singleton.

`ResourceProbe` chỉ là **dụng cụ quan sát trạng thái** để tạo kết quả xác định. Trong ứng dụng thật, đối tượng cần đóng có thể là connection pool, client hoặc file handle; cách đóng phải theo API và ownership cụ thể. Tránh dùng một biến boolean `closed` như bằng chứng bảo đảm đã giải phóng tài nguyên hệ điều hành.

## 5. Chạy chương trình và đối chiếu chính xác stdout

Trong terminal tại thư mục `manual-vs-spring-demo` (nơi có `pom.xml`), kiểm tra phiên bản công cụ:

~~~bash
java -version
javac -version
mvn -version
~~~

Sau đó biên dịch và chạy:

~~~bash
mvn -q clean compile exec:java
~~~

Lệnh Maven gọi compiler với target Java 17, tạo class và chạy `demo.ManualVsSpringDemo` với classpath gồm Spring libraries.

**Mười dòng stdout chính xác do `System.out.println` trong `main` in ra**, không tính output của lệnh kiểm tra môi trường, Maven build hoặc logger:

~~~text
manual.message=Xin chao, Lan!
manual.wiring=true
manual.closed.before=false
manual.closed.after=true
spring.message=Xin chao, Lan!
spring.wiring=true
spring.singleton=true
spring.closed.before=false
spring.closed.after=true
same.business.result=true
~~~

### Ý nghĩa từng dòng

| Quan sát | Giải thích |
| --- | --- |
| `manual.message` và `spring.message` giống nhau | Business behavior **không đổi** dù cách tạo graph khác |
| `manual.wiring=true` | Service giữ đúng hai object mà manual composition root truyền vào |
| `spring.wiring=true` | Bean service giữ đúng hai bean dependency lấy lại từ cùng context |
| `spring.singleton=true` | Hai lần `getBean(GreetingService.class)` trả **cùng instance** trong context |
| `manual.closed.before=false` / `after=true` | Manual caller trực tiếp gọi `close()` của probe |
| `spring.closed.before=false` / `after=true` | `ApplicationContext.close()` gọi callback destroy đã đăng ký |
| `same.business.result=true` | Hai cách lắp ráp tạo cùng kết quả `String` từ cùng thuật toán |

`==` trong `hasDependencies` và `spring.singleton` được dùng đúng mục đích: **so danh tính reference**. `String.equals` được dùng đúng mục đích: **so giá trị lời chào**. Không sử dụng `==` để kết luận hai chuỗi khác object có cùng nội dung hay không.

**Trường hợp thay đổi code:** nếu thêm một formatter bean thứ hai trong context mà không có quy tắc phân giải, `getBean(Formatter.class)` hoặc injection có thể mơ hồ. Khi ấy output chuẩn **không còn áp dụng**, và context có thể fail lúc startup trước khi in phần Spring. Không chép nguyên thông báo exception vì nó có thể khác theo patch.

## 6. Container có thay thế constructor injection không?

**Không.** Constructor injection vốn là một kỹ thuật thiết kế Java thuần. Đoạn:

~~~java
Formatter f = new VietnameseFormatter();
ResourceProbe p = new ResourceProbe();
GreetingService service = new GreetingService(f, p);
~~~

không dùng Spring vẫn là **Dependency Injection thủ công**, vì dependency được **truyền vào** service thay vì do service tự tìm/tự khởi tạo.

Spring DI có điểm khác: **container tự giải quyết** dependency trên cơ sở các bean definitions và cấu hình scope/qualifier, gọi factory/constructor thích hợp và quản lý lifecycle theo hợp đồng của container. Trong demo, phương thức:

~~~java
@Bean
public GreetingService greetingService(
        Formatter formatter, ResourceProbe resourceProbe) {
    return new GreetingService(formatter, resourceProbe);
}
~~~

không tạo `Formatter` hoặc `ResourceProbe` bên trong nó. Spring cung cấp cả hai tham số khi khởi tạo bean, rồi code Java dùng chúng theo cách thường. Các đoạn trên là **snippet minh họa**, phải đặt trong class/ngữ cảnh có import/type phù hợp; chương trình biên dịch độc lập là toàn bộ file ở mục 4.

Tránh hai hiểu lầm:
- **“Có Spring thì không được dùng `new`.”** Sai. Spring vẫn dùng constructor/factory method; trong `@Bean`, bạn hoàn toàn có thể `return new ...`. Quan trọng là container đăng ký/quản lý **object trả về**.
- **“Có `@Autowired` thì code business tự động độc lập.”** Không nhất thiết. Để business dễ test, hãy giữ các phụ thuộc rõ ràng qua constructor/interface, tránh truy cập global context không cần thiết.

## 7. Khi đồ thị lớn lên: nơi lợi ích và chi phí xuất hiện

Giả sử `GreetingService` được thay bằng hệ có `OrderService`, `PaymentClient`, `TaxPolicy`, `InventoryRepository` và `AuditPublisher`.

Với manual wiring, bạn có thể viết một composition root **rất rõ ràng**:

~~~java
// Pseudocode Java: các class ở ví dụ kiến trúc này chưa được định nghĩa.
var repository = new InventoryRepository(config);
var taxPolicy = new TaxPolicy(config);
var payment = new PaymentClient(config);
var audit = new AuditPublisher(config);
var orderService = new OrderService(
        repository, taxPolicy, payment, audit);
~~~

Điểm mạnh: nhìn vào code biết chính xác implementation nào được tạo, thứ tự/ownership dễ kiểm soát nếu thiết kế tốt; không cần framework. Điểm yếu: khi số cấu hình, scope, alternative implementations, environment và lifecycle tăng, phần lắp ghép có thể dài và dễ lệch giữa nhiều entry points.

Với Spring, composition root được biểu diễn bằng các bean definitions:

~~~java
// Pseudocode cấu hình: cần định nghĩa các type và cấu hình thật.
@Configuration(proxyBeanMethods = false)
class OrderConfig {
    @Bean
    OrderService orderService(
            InventoryRepository repository,
            TaxPolicy taxPolicy,
            PaymentClient payment,
            AuditPublisher audit) {
        return new OrderService(repository, taxPolicy, payment, audit);
    }
}
~~~

Điểm mạnh: container quản lý graph, resolve dependency theo quy tắc, hỗ trợ scopes, lifecycle, condition/configuration và nhiều extension points. Điểm yếu: **trừu tượng nhiều hơn**, startup/metadata/proxy có chi phí, và lỗi thiếu/mơ hồ bean đôi khi chỉ xuất hiện lúc tạo context. Một cấu hình Spring sai không được container “đoán” rồi sửa thành đúng.

**Điều Spring không tự làm:** viết business logic, bảo đảm thread safety cho singleton, xử lý mọi vòng phụ thuộc constructor, tự động giải phóng object prototype sau khi caller nhận, hoặc thay thế unit test. Container là công cụ quản lý đối tượng chứ không phải “bộ sửa kiến trúc” tự động.

## 8. So sánh vòng đời và phạm vi chia sẻ

### Manual wiring

- Bạn tự quyết định reference có được chia sẻ không: truyền cùng `Formatter` vào 5 services hay tạo 5 formatter khác nhau đều là quyết định của code.
- Một resource do code tạo phải có owner chịu trách nhiệm cleanup. Với resource implement `AutoCloseable`, có thể dùng `try-with-resources` như Java thông thường.
- Nếu composition root quên đóng object hoặc đóng hai lần không an toàn, Spring không thể tự chữa hành vi xảy ra hoàn toàn bên ngoài container.

### Container wiring

- `singleton` là scope mặc định: thường một instance được chia sẻ **trên mỗi bean definition trong mỗi context**.
- `prototype` cấp instance mới khi yêu cầu. Nếu inject prototype trực tiếp vào constructor của một singleton, dependency đó thường chỉ được resolve **một lần khi singleton được tạo**, không tự đổi object mỗi lần gọi method.
- Bean singleton không `@Lazy` trong `ApplicationContext` thường được **khởi tạo ngay lúc refresh**, không nhất thiết đến khi gọi `getBean` lần đầu.
- Khi `close()`, Spring gọi destruction callbacks của bean phù hợp; với prototype, container thường **không tự quản lý toàn bộ destruction callbacks** sau khi giao instance cho caller.
- Nếu cần request/session scope, phải có ngữ cảnh web phù hợp; console context của bài không tự hỗ trợ HTTP request scope.

**Phạm vi trách nhiệm của `ResourceProbe`:** `@Bean(destroyMethod="close")` bảo đảm callback được đăng ký cho bean và được Spring xử lý khi context đóng bình thường. Nó **không** biến một object Java khác bạn tạo ngoài container thành Spring bean và **không** bảo đảm callback chạy nếu JVM bị kill cưỡng bức.

## 9. Kiểm thử: nên dùng manual fake hay context thật?

Một trong những lý do tốt nhất để thiết kế service nhận dependency qua constructor là **unit test không cần khởi động Spring**.

Ví dụ đặt trong ngữ cảnh cùng các type ở mục 4:

~~~java
Formatter fake = name -> "TEST-" + name;
ResourceProbe probe = new ResourceProbe();
GreetingService service = new GreetingService(fake, probe);

System.out.println(service.greet("Lan"));
probe.close();
~~~

Stdout do đoạn minh họa ấy in ra:

~~~text
TEST-Lan!
~~~

`Formatter` là interface có một abstract method, nên Java 17 cho phép dùng lambda. Test kiểu này kiểm tra **logic của service** mà không phụ thuộc bean registration, context startup hoặc auto-configuration. Đây là snippet cần đặt trong class/method có quyền truy cập các nested types; nó **không** phải một file `.java` độc lập.

Khi nào cần tạo Spring context trong test? Khi bạn muốn xác minh **chính wiring/configuration/bean scopes/lifecycle** hoặc extension points của framework. Một test context có thể phát hiện thiếu bean hoặc lựa chọn sai `@Qualifier` mà unit test thuần Java không kiểm tra.

**Phân chia mục tiêu kiểm thử:**
- Unit test Java thuần: logic thuật toán, edge cases, fake dependency, tốc độ nhanh.
- Integration test có context: graph cấu hình, DI, proxy/lifecycle và behavior gắn với framework.
- End-to-end test: các tầng bên ngoài như HTTP/database/messaging khi có nhu cầu.

Không khởi động context cho mọi unit test chỉ vì dự án sử dụng Spring. Tương tự, không suy luận rằng unit test pass thì Spring config luôn đúng: hai loại kiểm tra chứng minh các điều khác nhau.

## 10. Những lỗi thường gặp khi so sánh

| Nhận định/sai sót | Cách hiểu hoặc cách xử lý đúng |
| --- | --- |
| “Manual wiring không phải DI.” | Truyền dependency từ caller qua constructor **là DI thủ công** |
| “Spring tạo object mà không có `new`.” | Constructor/factory method vẫn tạo object Java; Spring tổ chức và quản lý |
| “Hai cách phải khác thuật toán.” | **Có thể dùng cùng class service**; chỉ đổi cách tạo/cấp dependency |
| “`@Bean` trên method tự đủ mà không có context.” | Cần class cấu hình được đăng ký/được Spring xử lý trong context |
| “Bean `@Component` ở đâu cũng tự được quét.” | Phải cấu hình scan/registration đúng package |
| “Singleton nghĩa là một object duy nhất trên JVM.” | Mặc định Spring singleton theo definition và container |
| “Spring sẽ luôn chọn đúng một interface implementation.” | Nhiều bean cùng type không có qualifier/primary phù hợp có thể gây ambiguity |
| “Gọi `@Bean` method trực tiếp luôn lấy singleton.” | Với `proxyBeanMethods=false`, lời gọi thường có thể tạo object mới |
| “Dùng Spring thì không cần quản lý tài nguyên.” | Cần scope, destroy callback, shutdown đúng; object ngoài context vẫn thuộc owner riêng |
| “Dùng `==` để kiểm tra business string bằng nhau.” | Dùng `.equals` cho giá trị; `==` ở đây chỉ để quan sát reference |
| “Prototype sẽ đổi dependency trong singleton ở mỗi lần gọi.” | Constructor injection thường xảy ra một lần; cần provider/lookup có chủ đích |
| “Boot và Core Container là một.” | Spring Boot dùng Core Container của Framework, thêm conventions/auto-config |

### Nếu chạy không giống stdout

- Kiểm tra đã **thay đổi source** khi làm bài tập hay chưa; bản gốc dùng ba singleton beans trong một context.
- Nếu Spring startup ném `NoSuchBeanDefinitionException`/`NoUniqueBeanDefinitionException`, kiểm tra `@Bean` methods và parameter types; đó là vấn đề graph/metadata, không mặc định là lỗi Maven.
- Nếu `package org.springframework... does not exist`, kiểm tra dependency `spring-context`, Maven resolution và compile classpath.
- Nếu `spring.closed.after=false`, xác minh bean `ResourceProbe` là Spring-managed singleton, `destroyMethod="close"` và context đã đóng bình thường. Đừng nhầm đóng context với garbage collection.
- Nếu Maven/logging in thêm dòng, đối chiếu **10 dòng của ứng dụng**, không đếm toàn bộ output của terminal.
- Nếu `manual.wiring=false`, kiểm tra có tạo thêm dependency bằng `new` giữa lúc inject và lúc so reference.
- Nếu `same.business.result=false`, xem implementation/đầu vào có còn giống nhau không; khác cách wiring **không bắt buộc** phải tạo ra cùng kết quả nếu bạn đã cấu hình dependency khác nhau.

## 11. Bài tập có kiểm chứng

Thực hiện từng bài riêng rồi khôi phục mã gốc để đối chiếu stdout:

1. **Đổi implementation:** viết `EnglishFormatter`, trả `"Hello, " + name`, rồi thay implementation ở *cả hai* composition roots. Kiểm tra `same.business.result` vẫn `true`.
2. **Đổi một bên:** chỉ thay formatter bean trong `AppConfig` mà giữ manual formatter cũ. Dự đoán `same.business.result=false` dù `spring.wiring=true`.
3. **Thêm dependency:** tạo `Clock` (fake trả giờ cố định) và inject vào service. So sánh số chỗ phải thay trong manual root và `AppConfig`. Tránh đọc đồng hồ hệ thống trực tiếp nếu muốn expected output bất biến.
4. **Đổi scope:** gắn `@Scope("prototype")` lên bean `greetingService`, gọi `getBean` hai lần và dự đoán `spring.singleton=false`. Nhãn nên đổi thành `spring.sameInstance` để đúng nghĩa.
5. **Thiếu bean:** tạm xóa `@Bean formatter()` trong bản sao. Context có thể fail startup do `GreetingService` không resolve được tham số `Formatter`.
6. **Nhiều candidate:** thêm một bean `Formatter` khác, thử `@Primary` hoặc `@Qualifier` để kiểm soát lựa chọn.
7. **Quên cleanup:** bỏ `manualProbe.close()` và quan sát `manual.closed.after`. Sau đó khôi phục code và mô tả ảnh hưởng nếu `ResourceProbe` là file/network resource thật.
8. **Đóng context:** bỏ `try-with-resources` trong bản sao rồi chủ động `context.close()` tại điểm thích hợp; giải thích cách xử lý exception để tránh rò tài nguyên.
9. **Test không Spring:** dùng lambda fake ở mục 9 để kiểm tra service, rồi giải thích test nào cần context để xác minh `@Bean`/lifecycle.
10. **Hai contexts:** tạo hai context với cùng `AppConfig`, so reference của hai `GreetingService`. Giải thích singleton không đồng nghĩa object được chia sẻ giữa hai contexts.

### Checklist đã hiểu

- [ ] Nêu được phần giống và khác giữa **manual constructor injection** với **container-managed DI**.
- [ ] Chỉ ra **composition root** trong hai cách và nơi quyết định implementation.
- [ ] Xác định được Spring quản lý bean **trong context**, không phải mọi object từ `new`.
- [ ] Giải thích vì sao `manual.wiring`/`spring.wiring` đều `true`.
- [ ] Phân biệt `spring.singleton` với `same.business.result`.
- [ ] Dự đoán chính xác 10 dòng stdout khi chạy file Java không chỉnh sửa.
- [ ] Biết đóng resource theo ownership, chọn unit test không context và test wiring có context.

## 12. Tóm tắt và tài liệu tra cứu

**Kết luận chính:** Spring Core Container không thay thế các nguyên tắc thiết kế Java. Nó **thay thế phần lắp ghép và quản lý đồ thị đối tượng do ứng dụng tự viết** bằng một cơ chế được cấu hình tập trung, có các quy tắc bean scope, dependency resolution và lifecycle. Cả hai cách đều có thể dùng constructor injection và giữ business class không phụ thuộc framework.

- Với đồ thị nhỏ, lắp ghép thủ công rõ ràng và có thể đủ dùng.
- Với đồ thị lớn, nhiều cấu hình và lifecycle, Spring có thể giảm mã bootstrap lặp lại nhưng đòi hiểu bean registration, context, scope và error diagnostics.
- Dù dùng cách nào, hãy giữ dependency tường minh, xác định ownership, viết test đúng mức và không dựa vào “container magic” thay cho việc hiểu Java.

Tài liệu chính thức:

- [Spring – Introduction to the IoC Container](https://docs.spring.io/spring-framework/reference/core/beans/introduction.html)
- [Spring – Dependencies and Configuration in Detail](https://docs.spring.io/spring-framework/reference/core/beans/dependencies.html)
- [Spring – Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring – Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring – Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring – Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring – Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)

Bài tập cốt lõi: giữ nguyên `GreetingService`, thay riêng **composition root** giữa `new` và `ApplicationContext`; đo **kết quả**, **reference dependencies**, **scope** và **cleanup**. Khi bốn yếu tố ấy rõ ràng, bạn đã hiểu sự khác biệt thực tế giữa ứng dụng Java tự lắp ghép với ứng dụng có Spring container.