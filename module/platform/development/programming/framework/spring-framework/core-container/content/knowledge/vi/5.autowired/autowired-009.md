# Vì sao đối tượng tự tạo ngoài container không được tự động tiêm — @Autowired trong Spring Core Container

## 1. Hiện tượng: cùng một class, khác cách tạo, khác kết quả injection

Xét một Java class có field:

~~~java
@Component
public class GreetingClient {
    @Autowired
    private Formatter formatter;
}
~~~

Nhiều người nghĩ rằng chỉ cần gắn `@Component` hoặc `@Autowired`, bất cứ object nào thuộc class này cũng sẽ có giá trị `formatter`. **Đó là hiểu nhầm.** Annotation là **metadata**, không phải một lệnh tự chạy mỗi khi Java cấp phát object bằng `new`.

So sánh:

~~~java
GreetingClient a = new GreetingClient();
GreetingClient b = context.getBean(GreetingClient.class);
~~~

Đây là **snippet giải thích**, chưa phải file Java đầy đủ. Với Spring context đã đăng ký bean và có đúng một bean `Formatter` tương thích:

- Object `a` được tạo trực tiếp bằng Java `new`. Nó **không tự đi qua quá trình autowiring của Spring**, nên field `formatter` giữ giá trị mặc định `null` nếu constructor/code khác không gán.
- Object `b` được trả từ Spring `ApplicationContext`. Nó đã qua **bước xử lý injection** trong vòng đời Spring-managed bean; `formatter` được Spring gán bằng collaborator đã resolve.
- Hai objects cùng Java class nhưng **không cùng ownership**. Việc một object thuộc class đã có bean definition **không biến mọi object khác của class đó thành managed bean**.
- Annotation `@Component` khiến class **có thể được đăng ký thông qua scanning**; riêng object do Java `new` bên ngoài container không tự được Spring “nhận nuôi”.

**Mục tiêu bài:** hiểu *vì sao* Spring không tự inject vào object tạo ngoài container, *hậu quả*, *cách sửa đúng theo kiến trúc* và *giới hạn của các API có thể hỗ trợ đối tượng do framework khác tạo*.

Sau bài bạn có thể:

1. Giải thích vai trò của `ApplicationContext`, `BeanFactory`, `BeanDefinition` và `BeanPostProcessor` trong quá trình tạo và inject bean.
2. Phân biệt object `new`, Spring-managed bean được `getBean(...)`, manual constructor injection và external object được `autowireBean(...)`.
3. Hiểu vì sao `@Autowired` trên field/method của một object bình thường không được JVM tự xử lý.
4. Biết ưu tiên **constructor injection**, giữ collaborators bắt buộc trong `private final` fields và tách trách nhiệm tạo object.
5. Biết trường hợp tích hợp cần dùng `AutowireCapableBeanFactory.autowireBean(existingObject)`, cùng **giới hạn về registry và lifecycle**.
6. Phân tích lỗi `NullPointerException` do object không được inject, lỗi thiếu bean, trùng candidate, tạo object sai chỗ và bất cẩn trong unit tests.
7. Chạy ví dụ **Spring Framework + Java 17+** thuần, không cần Spring Boot, với Maven, `javac`/`java` và stdout chính xác.

**Phạm vi:** bài này tập trung vào việc **object tự tạo ngoài container không tự nhận `@Autowired`**. Các cơ chế AspectJ, JPA, Servlet và factory của framework khác được nhắc ở mức nhận diện, không biến chúng thành điều kiện bắt buộc của demo.

## 2. Cơ chế: annotation tự nó không tiêm dependency

Annotation trong Java được lưu trong metadata của class/method/field (theo retention của annotation), nhưng **JVM không có quy tắc chung “thấy `@Autowired` thì tự tìm bean và gán vào field”**.

Spring phải chủ động thực hiện các bước cần thiết:

1. **Đăng ký class hoặc factory method:** từ `@ComponentScan`, `@Bean`, XML, programmatic bean definition hoặc `context.register(SomeClass.class)` phù hợp.
2. **Nhận diện một bean cần tạo:** Spring dùng definition, tên bean, scope và thông tin constructor/factory.
3. **Khởi tạo object:** có thể bằng constructor được Spring resolve hoặc một factory method cung cấp object.
4. **Giải quyết collaborator:** Spring tìm candidate bằng type, qualifier, primary, name và các quy tắc autowiring.
5. **Áp dụng injection annotations:** các post-processors như `AutowiredAnnotationBeanPostProcessor` xử lý `@Autowired` trên field/method phù hợp, sau khi object được tạo và trước khi dùng nó như bean đã khởi tạo.
6. **Hoàn thành lifecycle:** callbacks, các `BeanPostProcessor` khác và có thể tạo proxy; container công bố bean theo scope và quản lý những bước lifecycle mà nó chịu trách nhiệm.

Một sơ đồ giản lược:

~~~mermaid
flowchart TD
    A["BeanDefinition / đăng ký class"] --> B["Spring tạo hoặc nhận bean instance"]
    B --> C["Bean post-processing"]
    C --> D["Resolve @Autowired fields / methods"]
    D --> E["Initialization, proxies (nếu có)"]
    E --> F["Bean được getBean(...) trả về"]
    N["new SomeClass() bên ngoài Spring"] --> X["Object Java thường"]
    X -.->|"KHÔNG tự qua"| C
~~~

Sơ đồ cố tình đơn giản: constructor injection phải được resolve **khi tạo object**, không chờ đến field/method post-processing; ngoài ra, chu trình khởi tạo có những extension points và xử lý dependency phức tạp hơn. Dù vậy, ranh giới quan trọng vẫn là **có đi qua pipeline Spring hay không**.

Spring có thể đọc annotation khi xử lý **một bean được quản lý**. Một object được `new` trong method nghiệp vụ **không tự đăng ký** vào BeanFactory và không tự gọi bean post-processors.

### Phân biệt ba việc thường bị trộn lẫn

| Công việc | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Đăng ký **bean definition** | `context.register(GreetingClient.class)` | Spring biết **cách tạo** một bean khi context xử lý registration |
| Lấy managed **bean instance** | `context.getBean(GreetingClient.class)` | Spring cấp bean theo scope, với injection/lifecycle tương ứng |
| Tạo object Java bình thường | `new GreetingClient()` | JVM cấp object; Spring không tự được thông báo hay áp dụng injection |

Không được hiểu `@Component` là “hễ xuất hiện class này ở đâu đều sẽ thành Spring bean”. Component stereotype làm class đủ điều kiện được phát hiện **khi đúng package được scan**, hoặc class có thể được đăng ký theo cách khác. Nó không phải cơ chế giám sát mọi lời gọi `new`.

## 3. Trường hợp dễ gặp nhất: @Autowired field null sau new

~~~java
@Component
final class ReportService {
    @Autowired
    private Formatter formatter;

    String render(String input) {
        return formatter.format(input);
    }
}
~~~

Đây là **snippet**, thiếu định nghĩa `Formatter` và không phải mã độc lập. Lời gọi:

~~~java
ReportService report = new ReportService();
report.render("book"); // Có thể NPE vì formatter chưa được inject.
~~~

Nếu không có code nào khác gán field, Java khởi tạo reference field mặc định là `null`. Annotation `@Autowired` nằm trên field không tự chạy; gọi `render(...)` có thể ném `NullPointerException`.

Với bean do container quản lý:

~~~java
ReportService report = context.getBean(ReportService.class);
String result = report.render("book");
~~~

khi `ReportService` thực sự được đăng ký, có đúng dependency và injection thành công, `formatter` đã được container cấp trước khi sử dụng thông thường. Nhưng **không được suy ra bất kỳ `getBean` nào đều luôn thành công**: thiếu `Formatter`, nhiều candidates mơ hồ hoặc dependency khởi tạo lỗi có thể khiến việc tạo bean thất bại.

**Lỗi không nằm ở việc field private.** Spring có cơ chế xử lý/tiêm vào field được annotate phù hợp. Vấn đề là **người tạo object đã bỏ qua vòng đời Spring**.

### Tại sao thêm @Autowired vào constructor cũng không cứu một lời gọi new tùy ý?

Với:

~~~java
final class ReportService {
    private final Formatter formatter;

    @Autowired
    ReportService(Formatter formatter) {
        this.formatter = java.util.Objects.requireNonNull(formatter);
    }
}
~~~

Nếu code gọi `new ReportService(formatter)`, **caller Java** đã tự cung cấp dependency. Annotation không bị JVM “kích hoạt” theo cơ chế DI; constructor chỉ chạy bình thường. Nếu code gọi `new ReportService()`, Java **không biên dịch được** nếu class không có constructor không tham số. Đây là một ưu điểm: dependency bắt buộc hiện rõ trong API.

Đừng thêm constructor mặc định tạo trạng thái thiếu `formatter` để một nơi nào đó dễ gọi `new`. Hãy sửa nơi tạo object để cấp dependency hoặc lấy managed bean đúng ranh giới.

## 4. Ai tạo object quyết định ai chịu trách nhiệm injection

### Khi Spring tạo/quản lý bean

- `@Component` được phát hiện qua scan/registration hoặc `@Bean` factory đưa object vào Spring.
- Spring giải quyết các dependencies đã khai báo và thực hiện những injection callbacks thích hợp.
- Bean thường có scope singleton mặc định, nên hai lời gọi `getBean("...")` trong cùng context trả cùng instance theo semantics singleton.
- Initialization, AOP proxy, scoped semantics, và destruction callbacks có thể được áp dụng theo cấu hình/lifecycle.
- Consumer không nên tự instantiate thêm một bản song song rồi giả định nó được cấu hình giống bean.

### Khi business code tự new

- Object do Java tạo có thể hoạt động bình thường **nếu mọi dependency đã được truyền trực tiếp** qua constructor/setter.
- Field có `@Autowired` mà không được xử lý sẽ giữ mặc định, thường là `null`.
- Spring **không tự đăng ký** object này trong bean registry, không tự áp dụng `@Value`, `@PostConstruct`, proxy `@Transactional`, `@Async` hoặc `@PreDestroy` như trên một managed bean.
- Việc object được tạo **ở bên trong một method của Spring-managed bean** không làm cho object con tự nhiên được managed. Container biết parent bean, không theo dõi từng lệnh `new` trong JVM.
- Nếu object giữ tài nguyên hoặc mở kết nối, caller thường phải chịu trách nhiệm dọn dẹp nếu object không thuộc lifecycle do Spring quản lý.

**Một ngoại lệ cần phân biệt:** object do factory method `@Bean` gọi `new` để **trả về cho Spring** có thể trở thành managed bean chính vì factory method là **một đường tạo bean được container sử dụng**. Tức là không phải từ khóa `new` bị cấm; quan trọng là **object có được đưa vào pipeline quản lý của container không**.

## 5. Cách khắc phục ưu tiên: constructor injection và tách nơi tạo object

Hãy ưu tiên loại class để dependency bắt buộc được truyền rõ:

~~~java
public final class GreetingService {
    private final Formatter formatter;

    public GreetingService(Formatter formatter) {
        this.formatter = java.util.Objects.requireNonNull(
                formatter, "formatter is required");
    }

    public String greet(String raw) {
        return formatter.format(raw);
    }
}
~~~

**Snippet có thể đưa vào một file phù hợp sau khi khai báo `Formatter`**, không phải chương trình hoàn chỉnh. Hai cách tạo hợp lệ:

~~~java
// Java thuần, không cần Spring:
Formatter fake = raw -> "TEST:" + raw;
GreetingService unit = new GreetingService(fake);

// Spring tại composition root:
Formatter managedFormatter = context.getBean(Formatter.class);
GreetingService manuallyComposed =
        new GreetingService(managedFormatter);
~~~

Trong cả hai trường hợp, object tự tạo **có đầy đủ collaborator** nhờ constructor Java; nó **không tự trở thành Spring bean** chỉ vì collaborator lấy từ context.

Cách thiết kế thường tốt hơn trong Spring application: **đăng ký cả `GreetingService` làm bean** và inject nó vào bean controller/job/service cần dùng. Không gọi `getBean(...)` rải rác khắp các method nghiệp vụ.

### Khi nào được dùng new bình thường?

Dùng `new` tự nhiên với object **không cần container quản lý**: DTO, value object, immutable domain data, collection, class thuần Java có tham số rõ, hoặc helper local không cần injection/AOP/lifecycle. **Không ép mọi object Java trở thành Spring bean.**

Một quy tắc thực tế:

- **Có framework-managed dependencies hoặc lifecycle?** Cho Spring quản lý/định nghĩa rõ factory.
- **Có collaborator nhưng dễ truyền qua constructor?** Manual DI hoàn toàn hợp lệ.
- **Là value object không có service dependency?** `new` bình thường là đúng.
- **Object do thư viện bên ngoài tạo, bạn không kiểm soát constructor?** Cân nhắc adapter hoặc API hỗ trợ autowiring existing instances có chủ đích.

**Constructor injection làm bug dễ thấy hơn:** `Objects.requireNonNull` từ chối reference thiếu ở lúc tạo object; `private final` giữ reference không bị thay. Nhưng field final không làm collaborator mutable tự thread-safe và không tự áp dụng Spring AOP.

## 6. Một ngoại lệ tích hợp: AutowireCapableBeanFactory.autowireBean(...)

Spring có API cấp thấp để **tiêm dependency vào object đã tồn tại**:

~~~java
LegacyClient external = new LegacyClient();
context.getAutowireCapableBeanFactory().autowireBean(external);
~~~

**Đây là snippet**, class/context đầy đủ có ở mục 7. Phương thức `autowireBean(existingObject)` của `AutowireCapableBeanFactory` áp dụng những **after-instantiation callbacks/property post-processing**, trong đó có annotation-driven injection như `@Autowired` lên field/setter của instance.

Đây là API phục vụ các tình huống **tích hợp với hệ thống khác đang sở hữu việc tạo object**, không phải kỹ thuật mặc định cho toàn bộ business code.

### Có gì và chưa có gì?

| Việc | Kết quả khi gọi `autowireBean(external)` |
| --- | --- |
| Instance đã tồn tại được Java tạo từ trước | Giữ nguyên instance do caller đưa vào |
| `@Autowired` field/method phù hợp | Có thể được xử lý/điền nếu dependency resolve được |
| Constructor `@Autowired` của class đã được `new` | **Không chạy lại constructor** và không thay đổi cách object đã được tạo |
| Tự thêm một bean definition vào registry | **Không** |
| `context.getBean(LegacyClient.class)` tự tìm thấy object external | **Không**, trừ khi có registration khác |
| Bảo đảm full init/post-processors/AOP proxy như managed bean | **Không thể kết luận chỉ từ `autowireBean`** |
| Bảo đảm full destruction callback lúc context đóng | **Không**; caller vẫn phải quản lý lifecycle phù hợp |
| Dependency thiếu hoặc mơ hồ | Vẫn có thể ném lỗi injection, không “tha thứ” vì external object |

Đây là chi tiết rất dễ bị diễn giải sai: **được inject không đồng nghĩa được đăng ký làm Spring bean**. Có thể thấy `external.formatter != null` sau `autowireBean` nhưng `getBeanNamesForType(LegacyClient.class)` vẫn rỗng. Trên object ấy, các cơ chế liên quan bean name, singleton registry, proxy và teardown có thể không giống managed bean thông thường.

### Các API liên quan không giống nhau

- `autowireBean(Object)`: xử lý dependency annotations/property post-processing của **instance đang có**, không tự sinh bean registry entry.
- `createBean(Class<T>)`: nhờ bean factory **tạo một instance mới và chạy tạo/khởi tạo qua những post-processors phù hợp**, nhưng không mặc định đồng nghĩa đăng ký nó dưới một tên singleton trong application context.
- `initializeBean(Object, name)`: áp dụng các callback initialization và bean post-processing lên object đã có; **không phải API thay thế đơn giản cho autowireBean trong việc tiêm field**.
- `configureBean(Object, name)`: cấu hình existing object theo **bean definition của name đã có** và thực hiện thêm các callback; yêu cầu một definition tương ứng, nên khác hẳn “cứ truyền object vào là được”.
- `registerSingleton(name, instance)` là một thao tác đăng ký instance có chủ đích trên BeanFactory thích hợp, nhưng **không tự thực hiện đầy đủ callbacks của quá trình tạo bean thông thường**; không dùng bừa để thay `@Bean`.

**Không xâu chuỗi các API này theo cảm giác** để mong đạt cùng semantics với container-managed bean. Phải chọn đúng khả năng tài liệu mô tả và kiểm tra tác động lifecycle/proxy/ownership. Với code nghiệp vụ có thể kiểm soát, ưu tiên khai báo bean/factory rõ ràng hoặc constructor injection.

## 7. Ví dụ Java 17+ tự chứa, Spring Framework thuần

Ví dụ sau chạy một Spring Context và quan sát bốn trường hợp:

1. `new FieldClient()`: field `@Autowired` không được gán tự động.
2. `context.getBean(FieldClient.class)`: cùng class nhưng Spring quản lý và inject thành công.
3. `new ConstructorClient(formatter)`: object không được đăng ký nhưng hoạt động đúng vì được **manual constructor injection**.
4. `new LegacyClient()` rồi gọi `autowireBean(external)`: field được inject có chủ đích, **nhưng object không được đăng ký vào registry**.

**Yêu cầu:** JDK 17+, Maven, Spring Framework **6.2.19** ghim để tái lập. Không cần Spring Boot, Servlet container hoặc DB. Phiên bản ghim không phải tuyên bố đây là bản Spring mới nhất.

~~~text
external-object-autowiring/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ExternalObjectDemo.java
~~~

### 7.1. File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>external-object-autowiring</artifactId>
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
                    <mainClass>demo.ExternalObjectDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Framework dependencies còn được Maven giải quyết transitively. Nếu dùng `javac` trực tiếp, classpath phải gồm đủ các thư viện do Maven resolve.

### 7.2. File src/main/java/demo/ExternalObjectDemo.java

~~~java
package demo;

import java.util.Locale;
import java.util.Objects;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

public final class ExternalObjectDemo {
    private ExternalObjectDemo() {}

    public interface Formatter {
        String format(String raw);
    }

    public static final class UppercaseFormatter implements Formatter {
        @Override
        public String format(String raw) {
            if (raw == null || raw.isBlank()) {
                throw new IllegalArgumentException("name is required");
            }
            return "Xin chao, " + raw.strip().toUpperCase(Locale.ROOT);
        }
    }

    @Component("fieldClient")
    public static final class FieldClient {
        @Autowired
        private Formatter formatter;

        public FieldClient() {}

        public boolean injected() {
            return formatter != null;
        }

        public String reply(String name) {
            if (formatter == null) {
                throw new IllegalStateException("formatter not injected");
            }
            return formatter.format(name);
        }
    }

    public static final class ConstructorClient {
        private final Formatter formatter;

        public ConstructorClient(Formatter formatter) {
            this.formatter = Objects.requireNonNull(
                    formatter, "formatter required");
        }

        public String reply(String name) {
            return formatter.format(name);
        }
    }

    public static final class LegacyClient {
        @Autowired
        private Formatter formatter;

        public LegacyClient() {}

        public boolean injected() {
            return formatter != null;
        }

        public String reply(String name) {
            if (formatter == null) {
                throw new IllegalStateException("formatter not injected");
            }
            return formatter.format(name);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public Formatter formatter() {
            return new UppercaseFormatter();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        AppConfig.class, FieldClient.class)) {

            // Case 1: Java new, không chạy autowiring.
            FieldClient plain = new FieldClient();
            System.out.println("newInjected=" + plain.injected());
            try {
                plain.reply("Lan");
                System.out.println("newCall=UNEXPECTED");
            } catch (IllegalStateException ex) {
                System.out.println("newCall=BLOCKED");
            }

            // Case 2: Spring bean có cùng class, field đã được inject.
            FieldClient managed = context.getBean(FieldClient.class);
            System.out.println("managedInjected=" + managed.injected());
            System.out.println("managedReply=" + managed.reply(" Lan "));

            // Case 3: manual constructor injection, không đăng ký.
            Formatter formatter = context.getBean(Formatter.class);
            ConstructorClient manual = new ConstructorClient(formatter);
            System.out.println("manualReply=" + manual.reply(" Minh "));
            System.out.println("manualRegistered=" +
                    (context.getBeanNamesForType(ConstructorClient.class)
                            .length > 0));

            // Case 4: autowireBean trên existing external instance.
            LegacyClient external = new LegacyClient();
            System.out.println("externalBefore=" + external.injected());
            context.getAutowireCapableBeanFactory()
                    .autowireBean(external);
            System.out.println("externalAfter=" + external.injected());
            System.out.println("externalRegistered=" +
                    (context.getBeanNamesForType(LegacyClient.class)
                            .length > 0));
            System.out.println("externalReply=" + external.reply(" An "));

            System.out.println("managedSingleton=" +
                    (managed == context.getBean(FieldClient.class)));
        }
    }
}
~~~

### 7.3. Kết quả mong đợi chính xác

Tại thư mục `external-object-autowiring`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Đúng 11 dòng stdout do phương thức `main` in khi chạy thành công:**

~~~text
newInjected=false
newCall=BLOCKED
managedInjected=true
managedReply=Xin chao, LAN
manualReply=Xin chao, MINH
manualRegistered=false
externalBefore=false
externalAfter=true
externalRegistered=false
externalReply=Xin chao, AN
managedSingleton=true
~~~

Các dòng thông tin phiên bản, downloading dependency hay log của Maven/Spring nếu xuất hiện không nằm trong 11 dòng do code ví dụ trực tiếp in.

**Giải thích kỹ thuật của từng dòng:**

| Kết quả | Bằng chứng |
| --- | --- |
| `newInjected=false` | Java `new` không tự kích hoạt Spring annotation injection |
| `newCall=BLOCKED` | Code có guard; lỗi sớm, không truy cập collaborator null |
| `managedInjected=true` | Bean được tạo qua Spring context có field `@Autowired` được xử lý |
| `managedReply=Xin chao, LAN` | Managed bean sử dụng collaborator thật |
| `manualReply=Xin chao, MINH` | Manual constructor injection cho phép object Java bình thường hoạt động |
| `manualRegistered=false` | ConstructorClient không tự được đăng ký chỉ vì được tạo bằng `new` |
| `externalBefore=false` | LegacyClient chưa qua injection |
| `externalAfter=true` | `autowireBean(external)` đã xử lý field `@Autowired` |
| `externalRegistered=false` | Đã inject không đồng nghĩa có bean registry entry |
| `externalReply=Xin chao, AN` | External object đã nhận formatter object từ container |
| `managedSingleton=true` | Spring-managed FieldClient là singleton mặc định trong context này |

Mã ví dụ tránh timestamp, số ngẫu nhiên, identity hash và collection order; stdout dự kiến không phụ thuộc các yếu tố đó. Phần mã và output ở đây được trình bày để người học chạy và tự xác nhận.

### 7.4. Chạy trực tiếp bằng javac/java

Vì chương trình import Spring, Maven có thể tạo classpath cho mọi transitive dependency:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/ExternalObjectDemo.java
java -cp "out:$(cat classpath.txt)" demo.ExternalObjectDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/ExternalObjectDemo.java
java -cp "out;$deps" demo.ExternalObjectDemo
~~~

Trên Unix các phần classpath ngăn bằng `:`, trên Windows bằng `;`. Hai cách chạy đều gọi `demo.ExternalObjectDemo`, do đó cho cùng 11 dòng stdout. Nếu `javac` báo không tìm thấy `org.springframework...`, sửa dependency/classpath trước khi chẩn đoán behavior autowiring.

## 8. Một số tình huống thực tế: controller, listener, task, helper

**Một anti-pattern phổ biến trong Spring MVC:**

~~~java
// Sai nếu muốn ReportService này được Spring inject:
ReportService service = new ReportService();
return service.render("book");
~~~

Ngay cả khi `ReportService` có `@Service`, nếu tự `new` nó trong một controller, instance ấy không tự được quản lý. Dùng constructor injection vào controller:

~~~java
@RestController
public class ReportController {
    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }
}
~~~

**Hai đoạn trên là snippets về Spring MVC, không phải phần của project runnable Core Container**; chúng còn cần thư viện Spring Web, khai báo service, import và các method thật. Ý chính: controller do Spring quản lý **nhận service bean**, không tự tạo phiên bản unmanaged của service.

**Một lỗi tương tự trong background tasks:**

~~~java
new Thread(new EmailJob()).start();
~~~

Nếu `EmailJob` chứa field `@Autowired` mà không được container tạo/xử lý, code chạy trong thread cũng không tự được inject. Dùng scheduler/executor được cấu hình phù hợp và tạo task với dependencies qua constructor, hoặc để Spring quản lý phần service cần DI. **Không đồng nghĩa mọi Runnable nên là singleton**: dữ liệu riêng mỗi tác vụ vẫn nên là object riêng, còn dependency managed có thể được truyền vào constructor.

**Trong unit test Java thuần:** nếu viết `new SomeService()` rồi mong field `@Autowired` được gán, test sẽ sai giả định. Dùng constructor injection với fake/mock, hoặc dùng Spring Test context thực sự khi đang kiểm tra Spring wiring; **không khởi động cả context chỉ để unit test một phép tính đơn giản**.

**Trong JPA entities, objects deserialize, objects do thư viện khác tạo:** framework có thể sở hữu việc tạo object. Đừng kỳ vọng `@Autowired` trên entity/DTO tự hoạt động. Tốt hơn là truyền dữ liệu vào một managed service xử lý entity, hoặc dùng integration API có kiểm soát tại ranh giới. Những hệ sinh thái có cơ chế injection riêng chỉ hoạt động khi đã được cấu hình cho cơ chế đó, không phải vì có annotation ở đâu đó.

## 9. Vì sao @Configurable không mặc nhiên sửa được new?

Spring có tích hợp AspectJ cho một số object được tạo **ngoài** IoC container, ví dụ dùng `@Configurable` kết hợp `@EnableSpringConfigured`/`spring-aspects` và **AspectJ weaving** phù hợp. Nhưng:

- Chỉ thêm `@Configurable` vào class **không đủ** để Spring tự inject mọi lời gọi `new`.
- Cần cấu hình hỗ trợ và load-time/compile-time weaving tương ứng; đây là một kỹ thuật nâng cao, có giới hạn runtime/classloader và chi phí vận hành.
- Nó không phải lý do bỏ constructor injection và biến mọi value/domain object thành một dependency lookup point.
- Không dùng AOP proxy thông thường của Spring để giả định JVM intercept được mọi `new` trong bất cứ file Java nào.

**Quy tắc thực hành:** chỉ dùng weaving khi có yêu cầu tích hợp được đánh giá và kiểm thử cụ thể; constructor injection và bean registration rõ ràng thường dễ hiểu, dễ test và ít bất ngờ hơn.

## 10. Hậu quả nếu cố sử dụng object unmanaged như managed bean

### 10.1. Không có injection annotations

`@Autowired` field/method không được xử lý, nên collaborator có thể null. `@Value` property cũng không tự resolve; `@Inject`/`@Resource` có giới hạn tương tự khi không có bộ xử lý của container phù hợp.

### 10.2. Không có bảo đảm bean lifecycle

`@PostConstruct`, `InitializingBean`, `@PreDestroy`, destroy methods và lifecycle management bình thường thuộc quá trình mà framework cần chủ động gọi. Object `new` bên ngoài container không tự chạy các callback Spring chỉ vì class có annotation.

### 10.3. Không có proxy của Spring

Với features dựa vào proxy như `@Transactional`, `@Async`, caching hoặc security interceptors, một object `new` ngoài context thường **không phải proxy managed**. Method call trên instance ấy có thể bỏ qua interceptor cần thiết. Hơn nữa, **self-invocation** trên managed bean cũng có giới hạn proxy riêng; không dùng self-invocation làm cách kiểm chứng bean ownership.

### 10.4. Không tuân theo bean scope

Một Spring singleton được hiểu trong phạm vi bean name/container. `new SomeService()` tạo instance Java khác với singleton được `getBean(...)` trả về. Tên class giống nhau không đồng nghĩa singleton identity.

### 10.5. Không tự có qualifier/primary resolution

Nếu một field muốn bean `Formatter`, annotation trên unmanaged object không khiến Spring chạy candidate resolution. Các quy tắc `@Qualifier`/`@Primary` chỉ có hiệu lực khi đúng một injection mechanism đang thực hiện giải quyết dependency.

### 10.6. Không được container giám sát việc cleanup

Nếu object external mở stream/socket/thread pool, code tạo/nhận nó phải đóng đúng cách. Gọi `autowireBean(external)` chỉ để inject một field **không biến Spring thành owner mặc định của mọi tài nguyên external**.

## 11. Phân biệt lỗi DI với lỗi Java và cấu hình

| Triệu chứng | Nguyên nhân thường gặp | Hướng sửa |
| --- | --- | --- |
| `@Autowired` field vẫn null, object do `new` | Instance không đi qua pipeline Spring | Lấy managed bean hoặc truyền dependency qua constructor |
| `@Component` class vẫn không nằm trong context | Không scan package hoặc không register class | Cấu hình `@ComponentScan` hoặc `context.register(...)` đúng |
| `NoSuchBeanDefinitionException` | Injection được xử lý nhưng không có bean candidate tương ứng | Đăng ký dependency, kiểm tra type/name/qualifier |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng type mà không chọn được một | Dùng `@Qualifier`/`@Primary` hoặc sửa cấu hình |
| `UnsatisfiedDependencyException` | Constructor/field/method cần dependency không resolve được | Đọc `Caused by`; sửa bean registration/injection point |
| `NullPointerException` khi gọi service new | Collaborator field mặc định null, không guard | Không new service cần DI; dùng constructor non-null guard |
| Unit test chạy bằng new báo lỗi null | Không khởi động Spring và không cấp dependency | Constructor-inject fake trong unit test; context test cho wiring |
| `autowireBean` xong `getBean(LegacyClient.class)` vẫn fail | Autowire existing instance **không register** nó | Nếu cần managed bean, khai báo definition/factory từ đầu |
| `@Transactional` bị bỏ qua | Đang gọi object ngoài proxy/container | Lấy đúng proxied bean, kiểm tra proxy mode/scope |
| `@PostConstruct` không chạy trên external instance | Chỉ new hoặc chỉ autowireBean, không full lifecycle | Giao ownership rõ; dùng lifecycle API đúng mục đích |
| `@Configurable` không có tác dụng | Chưa cấu hình AspectJ weaving/infrastructure cần thiết | Tránh đoán, thiết lập weaving có chủ đích hoặc đổi kiến trúc |
| `ObjectProvider.getObject()` thiếu bean | Provider lookup thật sự không tìm thấy candidate | Đăng ký bean hoặc xử lý optional đúng hợp đồng |
| `@Autowired(required=false)` để service chạy với null | Che dependency thực sự bắt buộc | Thiết kế constructor required và fail fast |
| `javac` báo thiếu Spring packages | Compile classpath không có Spring JAR | Kiểm tra pom và Maven dependency classpath |
| ApplicationContext đã close | Object external vẫn giữ collaborator dùng tài nguyên đã shutdown | Làm rõ lifecycle của owner/caller, không dùng context đã đóng |

**Mẹo chẩn đoán:** khi một field `@Autowired` bất ngờ null, hỏi ngay **“Ai tạo instance này?”**. Xác định địa chỉ tạo bằng `new`, constructor/factory method, component scan, plugin loader, framework deserializer hay test runner. Sau đó mới kiểm tra qualifier/type/scope. Nếu instance chưa hề được Spring xử lý, lỗi không nằm ở `@Qualifier`.

## 12. Các cách dùng đúng trong kiến trúc ứng dụng

### Cách A — Inject managed service vào managed consumer (ưu tiên)

~~~java
@Component
public class OrderHandler {
    private final OrderService orders;

    public OrderHandler(OrderService orders) {
        this.orders = java.util.Objects.requireNonNull(orders);
    }
}
~~~

**Snippet**, cần `OrderService` được đăng ký làm bean và import `@Component`. Spring sẽ tạo/resolve dependencies khi tạo `OrderHandler`. Nếu `OrderService` thiếu bean, startup có thể fail sớm, giúp tránh silent null.

### Cách B — Tạo value object bằng new và truyền dữ liệu

~~~java
public record OrderRequest(String sku, int count) {
    public OrderRequest {
        if (sku == null || sku.isBlank() || count <= 0) {
            throw new IllegalArgumentException("invalid request");
        }
    }
}
~~~

Snippet record Java 17 hợp lệ trong một file phù hợp. Domain record này không cần `@Autowired`; tạo bằng `new OrderRequest("BOOK", 2)` là tự nhiên và không có DI bị thiếu.

### Cách C — Factory có dependency managed nhưng tạo object mới có constructor hợp lệ

~~~java
@Component
public class ReportFactory {
    private final Formatter formatter;

    public ReportFactory(Formatter formatter) {
        this.formatter = java.util.Objects.requireNonNull(formatter);
    }

    public ReportJob newJob(String title) {
        return new ReportJob(formatter, title);
    }
}
~~~

**Snippet**, cần class `ReportJob` và import phù hợp. ReportFactory là bean nên nhận `Formatter` qua constructor; từng `ReportJob` do factory tạo là Java object riêng nhưng **đã có dependency**, không cần tự field-inject. Những ReportJob đó không tự trở thành managed beans; giữ lifecycle/tài nguyên theo ownership phù hợp.

### Cách D — Autowire object bên ngoài khi tích hợp bắt buộc

Nếu thư viện third-party bắt buộc gọi no-arg constructor và chỉ cung cấp object sau đó, integration boundary có thể gọi `autowireBean(existingObject)`. Hãy document rõ:

- Ai tạo và ai hủy object?
- Có cần `@PostConstruct`/proxy/transaction không?
- Có cần bean name/scope trong registry không?
- Nếu thật sự cần full managed bean, có thể đổi registration/factory hoặc adapter không?

API hỗ trợ object external là **phương án tích hợp**, không phải cách mặc định để chữa các service được `new` lung tung.

## 13. Kiểm thử và bài tập có đáp án

### Unit test không Spring

Tạo một `Formatter` fake và constructor-inject vào một class Java thuần. Không cần context:

~~~java
Formatter fake = raw -> "FAKE:" + raw;
ConstructorClient client = new ConstructorClient(fake);
System.out.println(client.reply("Lan")); // FAKE:Lan
~~~

**Snippet này cần đứng trong phạm vi có quyền truy cập các nested types của demo.** Nó chứng minh constructor injection được kiểm thử thuần Java mà không dùng field reflection hoặc chạy container.

### Integration test Spring

Tạo context với `AppConfig.class` và `FieldClient.class`, lấy `FieldClient` bằng `getBean(...)`; xác nhận collaborator không null và hành vi đúng. Test riêng `new FieldClient()` cho `injected()==false`. Nếu integration buộc `autowireBean`, kiểm tra external object sau wiring nhưng **không** mặc định kỳ vọng `containsBean(...)` hoặc destruction tự động.

Không dùng Java `assert` làm kiểm tra runtime bắt buộc trong ví dụ nếu không bật `-ea`; dùng test framework assertions hoặc `if (...) throw ...`.

**Bài 1.** Class có `@Component` và field `@Autowired`, bạn gọi `new MyService()` trong controller. Vì sao field null?

**Đáp án:** Object mới do Java tạo không đi qua Spring injection post-processors; `@Component` không intercept mọi lệnh `new`. Inject managed service vào controller hoặc cấp dependency qua constructor.

**Bài 2.** `@Bean MyService service() { return new MyService(); }` có phải luôn không được inject vì có `new`?

**Đáp án:** Không. Object được trả về như **bean của factory method do Spring gọi** sẽ qua những bước processing tương ứng. Vấn đề không phải cú pháp `new` tự thân mà là **có được container tiếp nhận/quản lý như bean không**.

**Bài 3.** `autowireBean(external)` làm external trở thành singleton mặc định có bean name không?

**Đáp án:** Không. API có thể xử lý annotation-driven injection trên existing object, nhưng không tự thêm registry entry/singleton definition.

**Bài 4.** Nếu `LegacyClient` có constructor cần `Formatter` và bạn đã gọi `new LegacyClient(null)` thì `autowireBean(...)` có chạy lại constructor để sửa null không?

**Đáp án:** Không. Constructor đã hoàn tất khi Java tạo object. API chỉ xử lý injection đối với existing instance theo hỗ trợ của nó; hãy sửa caller/constructor để bảo vệ invariant.

**Bài 5.** Object được `new` ở trong method của một bean Spring có tự managed không?

**Đáp án:** Không. Scope bean của object cha không khiến mọi object do nó tự tạo trở thành managed. Tuy nhiên, người tạo có thể truyền dependencies hợp lệ qua constructor.

**Bài 6.** Một request DTO không có collaborator Spring. Có nên đăng ký DTO thành bean singleton rồi `getBean` mỗi request?

**Đáp án:** Thường không. DTO/value object mang dữ liệu request được tạo riêng theo nhu cầu; tạo bằng `new` hoàn toàn hợp lý và không có lỗi DI.

**Bài 7.** Vì sao `manualReply=Xin chao, MINH` nhưng `manualRegistered=false` trong demo?

**Đáp án:** ConstructorClient nhận một Formatter hợp lệ qua constructor Java nên hoạt động đúng, nhưng chưa bao giờ được Spring đăng ký như bean.

**Bài 8.** Có thể gắn `@Configurable` vào class để mọi `new` được inject ngay không?

**Đáp án:** Không chỉ nhờ annotation. Tích hợp AspectJ còn cần weaving và infrastructure phù hợp; bài học thông thường nên ưu tiên constructor injection/factory bean rõ ràng.

**Bài 9.** Vì sao test chạy không có Spring có thể fail với field injection mà không fail với constructor injection?

**Đáp án:** Field injection cần một bộ xử lý Spring thực hiện gán; constructor Java chỉ cần caller cung cấp fake/real collaborator hợp lệ nên dễ unit test độc lập.

### Checklist hoàn thành

- [ ] Biết `@Autowired` là metadata do Spring xử lý, không phải JVM tự tiêm sau mọi `new`.
- [ ] Phân biệt đăng ký class/definition với tạo object Java.
- [ ] Nắm BeanPostProcessor/AutowiredAnnotationBeanPostProcessor hoạt động trong pipeline bean.
- [ ] Không suy ra `@Component` biến mọi instance cùng class thành managed.
- [ ] Biết `@Bean` factory có thể gọi `new` mà kết quả vẫn là managed bean khi trả về container.
- [ ] Với service bắt buộc dependency, ưu tiên constructor injection và `Objects.requireNonNull`.
- [ ] Không gọi `ApplicationContext.getBean(...)` khắp method nghiệp vụ chỉ để sửa lỗi ownership.
- [ ] Biết `autowireBean(existing)` có thể inject nhưng không register/full lifecycle.
- [ ] Phân biệt autowireBean/createBean/initializeBean/configureBean/registerSingleton theo khả năng thật.
- [ ] Không kỳ vọng proxy/AOP/lifecycle/scope của managed bean trên unmanaged object.
- [ ] Xác định owner khi object do controller, task framework, mapper, ORM hoặc test tạo ra.
- [ ] Dùng `new` bình thường với value objects/DTOs không cần DI.
- [ ] Chạy Java 17+ và đối chiếu **11 dòng stdout chính xác**.
- [ ] Khi dùng `javac`/`java`, cung cấp đầy đủ Spring compile/runtime classpath.
- [ ] Có unit test Java thuần và wiring smoke test; negative tests ở cấu hình riêng.

**Kết luận:** `@Autowired` không tự tạo dependency cho mọi object Java. Spring tiêm collaborator **khi chính container quản lý hoặc được yêu cầu xử lý một instance theo API rõ ràng**. Object do `new` bên ngoài container mặc định không đi qua quy trình đó, vì vậy trường annotated có thể vẫn null. Hướng giải quyết tốt nhất là **cho Spring sở hữu service cần DI hoặc truyền dependencies qua constructor**; chỉ dùng API autowire existing instance khi thực sự tích hợp đối tượng do hệ thống khác quản lý.

### Tài liệu Spring chính thức

- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html)
- [Spring Framework — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config.html)
- [AutowireCapableBeanFactory API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/config/AutowireCapableBeanFactory.html)
- [Spring Framework — Using AspectJ with Spring Applications](https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html)
