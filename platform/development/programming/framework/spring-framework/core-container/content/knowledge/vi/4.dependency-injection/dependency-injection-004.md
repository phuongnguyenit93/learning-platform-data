# Tiêm trực tiếp vào trường và ảnh hưởng tới kiểm thử trong Spring

## 1. Khái niệm field injection và vấn đề cốt lõi

**Field injection** là hình thức Dependency Injection (DI) trong đó Spring IoC Container gán bean cộng tác vào **trường của một object đã được tạo**. Cách viết quen thuộc:

~~~java
// Mã minh họa; interface GreetingRepository có trong ví dụ đầy đủ ở mục 5.
class FieldWiredGreeter {
    @Autowired
    private GreetingRepository repository;

    String greet(String name) {
        return repository.greet(name);
    }
}
~~~

`@Autowired` trên field là một cơ chế hợp lệ của Spring. Nhưng `new FieldWiredGreeter()` bằng Java thuần **không kích hoạt autowiring**, khiến `repository` chưa được gán. Lời gọi `greet()` có thể gây `NullPointerException` dù code **biên dịch thành công**. Đó là hệ quả của **dependency bị ẩn khỏi chữ ký constructor**.

Hãy tách ba câu hỏi:
1. **Dependency cần thiết gì?** Ví dụ `GreetingRepository` là bắt buộc để service tạo lời chào.
2. **Ai cấp dependency?** Caller Java thuần truyền vào constructor hay Spring container resolve bean?
3. **Có thể kiểm thử logic mà không dựng container không?** Nếu dependency hiển thị trong constructor, truyền fake rất dễ. Nếu nó chỉ nằm ở private field có `@Autowired`, người viết test thường phải dựng Spring hoặc can thiệp vào field.

| Đặc điểm | Field injection | Constructor injection |
| --- | --- | --- |
| Vị trí khai báo dependency | `@Autowired` trên field | Tham số constructor |
| `new Service()` khi thiếu dependency | Có thể tạo object thiếu wiring | Không compile nếu chỉ có constructor bắt buộc tham số |
| Reference `final` | Không phù hợp với cách gán sau construction | Tự nhiên, dễ tạo immutable wiring |
| Unit test Java thuần | Cần giải pháp để cấp private field | `new Service(fake)`, không cần Spring |
| Dấu hiệu class có nhiều dependencies | Nằm rải ở fields/annotations | Nhìn thấy trong constructor |
| Autowiring khi Spring quản lý bean | Có | Có |
| Khả năng lỗi vì thiếu bean trong Spring | Có | Có |

**Không kết luận field injection luôn sai.** Nó được Spring hỗ trợ, và có hệ thống legacy hoặc integration adapter vẫn dùng. Mục đích là nhận diện **ảnh hưởng cụ thể lên testability, trạng thái khởi tạo và chất lượng API** để chọn cơ chế DI phù hợp.

## 2. Spring thực hiện injection khi nào?

Khi container tạo một **Spring-managed bean**, các annotation post-processors như `AutowiredAnnotationBeanPostProcessor` xử lý `@Autowired` và tìm bean tương thích để gán vào field. Việc này xảy ra **sau constructor** (trước khi bean được khởi tạo xong để sử dụng thông thường).

~~~text
Nguồn cấu hình @Bean hoặc @Component + scan
                    |
                    v
          Đăng ký BeanDefinition
                    |
                    v
           Spring tạo object Java
                    |
                    v
       Xử lý @Autowired private field
                    |
           Resolve dependency
              /           \
       Có candidate      Thiếu required
            |                 |
            v                 v
     Gán reference       Bean creation fail
            |
            v
       Initialization callbacks
            |
            v
      Bean sẵn sàng để sử dụng
~~~

Trường `private` vẫn có thể được Spring inject qua reflection/access mechanism phù hợp. Điều đó không có nghĩa Java tự bỏ qua encapsulation cho mọi caller. Trong môi trường **Java module path (JPMS)**, quyền truy cập reflection/module openness có thể cần cấu hình thích hợp; ví dụ này chạy trên **classpath truyền thống**.

**Quan trọng:** chỉ đặt annotation trên class/field **không tự tạo bean**. Đối tượng phải được container quản lý bằng một cấu hình hợp lệ: component scan, `@Bean`, XML hoặc API đăng ký tương ứng. `AnnotationConfigApplicationContext` tự thiết lập annotation processors phù hợp khi được khởi tạo bằng Java configuration.

Với field-injected bean:

~~~java
@Autowired
private GreetingRepository repository;
~~~

Đừng truy cập `repository` trong constructor nếu bạn phụ thuộc vào việc Spring inject nó: ở giai đoạn đó field vẫn có giá trị mặc định hoặc giá trị khởi tạo trực tiếp từ Java. Trước khi chuyển một bean cho client, container thông thường đã hoàn tất injection hoặc đã báo lỗi wiring.

**`@Autowired` mặc định required.** Thiếu bean phù hợp thường khiến Spring fail khi tạo bean. Với singleton không lazy trong `ApplicationContext`, lỗi có thể xuất hiện ngay ở `refresh()`/startup; với lazy/prototype, có thể xuất hiện ở lần yêu cầu bean. Điều này khác với việc Java tự `new` object rồi nhận field null.

## 3. Vì sao unit test cho field injection thường khó hơn?

### Dependency ẩn trong object được tạo

Một unit test viết:

~~~java
// Đoạn minh họa:
FieldWiredGreeter service = new FieldWiredGreeter();
service.greet("An");
~~~

đã tạo được object nhưng chưa cấp repository. Người viết test chỉ phát hiện dependency bằng cách đọc các fields/annotations hoặc khi runtime lỗi. Trong khi đó:

~~~java
// Đoạn minh họa của một class có constructor dependency:
ConstructorWiredGreeter service =
        new ConstructorWiredGreeter(name -> "Fake:" + name);
System.out.println(service.greet("An"));
~~~

có thể hoạt động hoàn toàn bằng Java thuần; lambda fake thực thi một interface có một abstract method.

### Những chiến lược test field-injected bean

| Chiến lược | Test được gì | Hạn chế |
| --- | --- | --- |
| Dựng một `ApplicationContext` nhỏ | Container có inject đúng, bean có hoạt động không | Test phải chuẩn bị Spring config và chạy lifecycle |
| Dùng Spring Test `ReflectionTestUtils.setField` hoặc reflection thuần | Business behavior sau khi ép dependency | Test phụ thuộc tên field/chi tiết triển khai; cần `spring-test` nếu dùng tiện ích |
| Thêm setter/package-level seam cho test | Cho phép cấp dependency thủ công | Có thể tạo API test-only, làm object mutable và thiếu invariant |
| Refactor sang constructor injection | Unit test business bằng fake, không cần Spring | Cần cập nhật constructor và composition root |
| Mockito `@InjectMocks` (khi dùng Mockito) | Tạo subject và thử inject mocks | Hành vi công cụ mock không thay thế test Spring wiring; dependency/runner riêng |

Trong code mới có quyền thay đổi, **constructor injection + unit test thuần Java** thường ít tốn công bảo trì hơn việc phản chiếu private fields. Với mã không sửa được, test context nhỏ là lựa chọn minh bạch nếu mục tiêu thật sự là xác nhận Spring autowiring.

**Unit test behavior khác integration test wiring:** logic `greet("An")` có thể đúng nhưng cấu hình Spring thiếu bean; hoặc cấu hình Spring pass nhưng business logic trả giá trị sai. Vì thế nên có đúng loại kiểm chứng cho từng mục tiêu.

## 4. Constructor injection, `final` và thiết kế bất biến

Cách khai báo được khuyến nghị cho dependency bắt buộc:

~~~java
// Snippet; cần import java.util.Objects và interface GreetingRepository.
final class ConstructorWiredGreeter {
    private final GreetingRepository repository;

    ConstructorWiredGreeter(GreetingRepository repository) {
        this.repository =
                Objects.requireNonNull(repository, "repository");
    }

    String greet(String name) {
        return repository.greet(name);
    }
}
~~~

**Ưu điểm:**
- API constructor làm rõ rằng object cần `GreetingRepository` ngay từ đầu.
- Java caller có thể truyền fake/in-memory repository, không cần Spring.
- `Objects.requireNonNull` fail-fast cả khi gọi từ code Java thuần.
- Trường `final` giúp đảm bảo reference không bị gán lại sau constructor.
- Khi constructor có rất nhiều dependencies, code review dễ nhận diện class đang gánh quá nhiều trách nhiệm.

Lưu ý: `final` **không biến bản thân repository thành immutable hoặc thread-safe**. Repository vẫn có thể giữ state mutable hoặc thực hiện I/O; Spring singleton cũng không tự đồng bộ các lời gọi đa luồng.

Spring Framework hỗ trợ autowiring cho một **constructor duy nhất** của component mà thông thường **không cần đặt `@Autowired`**. Với `@Bean` configuration, bạn cũng có thể để Spring inject qua tham số factory method. Nhiều constructors cần tuân thủ quy tắc chọn constructor; không nên trông đợi Spring tùy ý đoán đúng overload.

**Không cần tránh mọi lệnh `new` trong Spring.** Một `@Bean` factory method có thể trả về `new ConstructorWiredGreeter(repository)`; điều Spring giúp thực hiện là **resolve `repository` và quản lý object trả về** như bean trong container.

## 5. Project Maven Java 17: một chương trình đối chiếu hai kiểu injection

Ví dụ dùng **Spring Framework thuần**, không cần Spring Boot, HTTP server hoặc database. Chương trình quan sát:
1. `new FieldWiredGreeter()` ở Java thuần **không có repository**.
2. Constructor service nhận fake Java thuần và **hoạt động được ngay**.
3. Một Spring context đăng ký cả hai service: **cả field và constructor injection đều hoạt động**.
4. Constructor-injected service giữ đúng bean dependency được lấy qua context.

Yêu cầu JDK **17+**, Maven **3.9+**, Maven Central/mirror để tải dependency khi cần. Version bài học: **Spring Framework 7.0.9**, **JUnit Jupiter 5.12.2**.

### 5.1. Cấu trúc

~~~text
field-injection-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/FieldInjectionDemo.java
    └── test/
        └── java/demo/FieldInjectionDemoTest.java
~~~

### 5.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>field-injection-demo</artifactId>
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
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.3</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.FieldInjectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp `AnnotationConfigApplicationContext`, `@Configuration`, `@Bean` và hỗ trợ xử lý `@Autowired`; Maven tự resolve những Spring artifacts nền cần thiết. `junit-jupiter` là dependency thuộc **test scope**; Surefire chạy các test qua JUnit Platform. POM không cần `spring-test` vì test context ví dụ được mở trực tiếp bằng `AnnotationConfigApplicationContext`.

### 5.3. `src/main/java/demo/FieldInjectionDemo.java`

~~~java
package demo;

import java.util.Objects;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class FieldInjectionDemo {
    private FieldInjectionDemo() {
    }

    @FunctionalInterface
    interface GreetingRepository {
        String greet(String name);
    }

    static final class FieldWiredGreeter {
        @Autowired
        private GreetingRepository repository;

        boolean hasRepository() {
            return repository != null;
        }

        String greet(String name) {
            return repository.greet(name);
        }
    }

    static final class ConstructorWiredGreeter {
        private final GreetingRepository repository;

        ConstructorWiredGreeter(GreetingRepository repository) {
            this.repository =
                    Objects.requireNonNull(repository, "repository");
        }

        GreetingRepository dependency() {
            return repository;
        }

        String greet(String name) {
            return repository.greet(name);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public GreetingRepository greetingRepository() {
            return name -> "Hello, " + name + "!";
        }

        @Bean
        public FieldWiredGreeter fieldWiredGreeter() {
            return new FieldWiredGreeter();
        }

        @Bean
        public ConstructorWiredGreeter constructorWiredGreeter(
                GreetingRepository repository) {
            return new ConstructorWiredGreeter(repository);
        }
    }

    public static void main(String[] args) {
        // new thuần Java không thực thi @Autowired.
        var plainField = new FieldWiredGreeter();
        System.out.println("plain.field.ready="
                + plainField.hasRepository());

        try {
            plainField.greet("Lan");
        } catch (NullPointerException expected) {
            System.out.println("plain.field.callFailed=true");
        }

        // Constructor nhận fake: không cần context.
        var plainConstructor = new ConstructorWiredGreeter(
                name -> "Fake:" + name);
        System.out.println("plain.constructor.greet="
                + plainConstructor.greet("Lan"));

        // Đối chứng có Spring container.
        try (var context = new AnnotationConfigApplicationContext(
                AppConfig.class)) {
            var field = context.getBean(FieldWiredGreeter.class);
            var constructor = context.getBean(
                    ConstructorWiredGreeter.class);
            var repository = context.getBean(GreetingRepository.class);

            System.out.println("spring.field.ready="
                    + field.hasRepository());
            System.out.println("spring.field.greet="
                    + field.greet("Lan"));
            System.out.println("spring.constructor.greet="
                    + constructor.greet("Lan"));
            System.out.println("spring.constructor.sameDependency="
                    + (constructor.dependency() == repository));
            System.out.println("spring.constructor.singleton="
                    + (constructor == context.getBean(
                            ConstructorWiredGreeter.class)));
        }
    }
}
~~~

**Giải thích:**

- `plainField` là object được tạo ngoài Spring nên field annotation **không được xử lý**. Lỗi null trong demo được catch có chủ đích; **không** dùng catch `NullPointerException` làm cách xử lý thiếu dependency trong sản phẩm.
- `plainConstructor` nhận fake qua lambda một phương thức, kiểm chứng API testable mà không cần container.
- `AppConfig` cung cấp bean `GreetingRepository` và hai services. Dù `FieldWiredGreeter` được trả về từ một factory method `@Bean` (không có `@Component`), Spring **vẫn post-process bean ấy và tiêm `@Autowired` field**.
- `constructorWiredGreeter(GreetingRepository repository)` nhận dependency qua **Spring-resolved `@Bean` method parameter**. `ConstructorWiredGreeter` chỉ phụ thuộc Java API `Objects`, không import Spring.
- `@Configuration(proxyBeanMethods=false)` phù hợp vì các factory methods không tự gọi nhau để lấy bean. Scope mặc định singleton giúp hai lần lấy `ConstructorWiredGreeter` từ **cùng context** trả cùng object.

### 5.4. Biên dịch/chạy và expected stdout

Đứng tại thư mục `field-injection-demo` chứa `pom.xml`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

Maven Compiler Plugin biên dịch bằng `javac` với `--release 17`; Exec Plugin đưa Spring dependencies vào runtime classpath. Ba lệnh kiểm tra phiên bản đầu có output phụ thuộc máy.

**8 dòng stdout do code `main` in**, không tính log Maven/Spring tùy môi trường:

~~~text
plain.field.ready=false
plain.field.callFailed=true
plain.constructor.greet=Fake:Lan
spring.field.ready=true
spring.field.greet=Hello, Lan!
spring.constructor.greet=Hello, Lan!
spring.constructor.sameDependency=true
spring.constructor.singleton=true
~~~

Kết quả chứng minh **không phải field injection luôn thất bại**: ở Spring-managed bean, nó hoạt động. Sự khác biệt là khi test dùng `new`, field-injected service không có API constructor để cung cấp dependency bắt buộc, còn constructor service có thể nhận fake rõ ràng.

## 6. JUnit 5: tách unit test không Spring và test bean wiring

Tệp hoàn chỉnh **`src/test/java/demo/FieldInjectionDemoTest.java`**:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

final class FieldInjectionDemoTest {

    @Test
    void constructorBehaviorWithoutSpring() {
        FieldInjectionDemo.GreetingRepository fake =
                name -> "Test:" + name;
        var service = new FieldInjectionDemo.ConstructorWiredGreeter(fake);

        assertEquals("Test:Lan", service.greet("Lan"));
        assertSame(fake, service.dependency());
        assertThrows(NullPointerException.class,
                () -> new FieldInjectionDemo.ConstructorWiredGreeter(null));
    }

    @Test
    void plainFieldObjectIsUnwired() {
        var service = new FieldInjectionDemo.FieldWiredGreeter();

        assertFalse(service.hasRepository());
        assertThrows(NullPointerException.class,
                () -> service.greet("Lan"));
    }

    @Test
    void springManagesBothInjectionStyles() {
        try (var context = new AnnotationConfigApplicationContext(
                FieldInjectionDemo.AppConfig.class)) {
            var field = context.getBean(
                    FieldInjectionDemo.FieldWiredGreeter.class);
            var constructor = context.getBean(
                    FieldInjectionDemo.ConstructorWiredGreeter.class);
            var repository = context.getBean(
                    FieldInjectionDemo.GreetingRepository.class);

            assertTrue(field.hasRepository());
            assertEquals("Hello, Lan!", field.greet("Lan"));
            assertEquals("Hello, Lan!", constructor.greet("Lan"));
            assertSame(repository, constructor.dependency());
        }
    }
}
~~~

Chạy:

~~~bash
mvn -q test
~~~

**Kết quả kiểm thử mong đợi:** 3 test methods thành công, **0 failures, 0 errors, 0 skipped**. Báo cáo Surefire có thể đọc tại `target/surefire-reports/demo.FieldInjectionDemoTest.txt`, hoặc bỏ `-q` khi chạy Maven để xem summary. **Không có một stdout cố định cho toàn bộ Maven/Surefire**, nên không giả vờ rằng mỗi lần chạy đều in đúng cùng một đoạn terminal.

**Ba mục đích khác nhau:**
1. `constructorBehaviorWithoutSpring`: kiểm tra business logic và null invariant, **không** dùng context.
2. `plainFieldObjectIsUnwired`: negative test cho `new` field-injected object, không phải khẳng định Spring DI sai.
3. `springManagesBothInjectionStyles`: integration test nhỏ xác nhận bean registration/post-processing và wiring thật.

Một unit test cho service không cần Spring có thể dùng fake/spy/mock để kiểm tra logic; integration test có context cần khi đang kiểm tra configuration. Với ứng dụng lớn, tách loại test giúp rút ngắn vòng phản hồi và tránh phụ thuộc vào nhiều beans không liên quan.

## 7. Java 17 thuần với `javac`/`java`: injection không phải đặc quyền Spring

Tạo file riêng **`PlainJavaGreeter.java`** ngoài project Maven (hoặc tại một thư mục ví dụ độc lập):

~~~java
import java.util.Objects;

public class PlainJavaGreeter {
    interface Greeter {
        String greet(String name);
    }

    static final class Service {
        private final Greeter greeter;

        Service(Greeter greeter) {
            this.greeter = Objects.requireNonNull(greeter);
        }

        String greet(String name) {
            return greeter.greet(name);
        }
    }

    public static void main(String[] args) {
        Service service = new Service(name -> "Fake:" + name);
        System.out.println("pure.fake=" + service.greet("Lan"));

        try {
            new Service(null);
        } catch (NullPointerException expected) {
            System.out.println("pure.rejectsNull=true");
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17+, **không Maven hoặc Spring**:

~~~bash
javac PlainJavaGreeter.java
java PlainJavaGreeter
~~~

Stdout:

~~~text
pure.fake=Fake:Lan
pure.rejectsNull=true
~~~

Bài học: thiết kế DI qua constructor là kỹ thuật Java cơ bản. Spring bổ sung **automatic bean resolution và lifecycle**, không thay thế trách nhiệm tạo một class có hợp đồng rõ ràng.

## 8. Field injection với optional dependency, qualifiers và giới hạn

### `@Autowired(required=false)`

~~~java
// Snippet (đặt trong class có type Repository phù hợp):
@Autowired(required = false)
private GreetingRepository repository;
~~~

Nếu không tìm được bean phù hợp, Spring có thể **không gán field**, giữ giá trị khởi tạo mặc định (`null` nếu chưa gán). Điều đó **chỉ đúng** nếu dependency thực sự tùy chọn theo hợp đồng class và tất cả chỗ sử dụng đều xử lý trường hợp vắng. Với một repository bắt buộc, chuyển thành optional chỉ để tránh lỗi startup là rủi ro.

Nếu nhiều beans `GreetingRepository` cùng type và không có cách chọn rõ ràng, Spring vẫn có thể báo `NoUniqueBeanDefinitionException`. `required=false` **không phải công tắc “chọn bừa một bean”**.

### `@Qualifier`, `@Primary`

Có thể giải quyết nhiều candidates ở field injection:

~~~java
@Autowired
@Qualifier("primaryGreetingRepository")
private GreetingRepository repository;
~~~

Cần import `org.springframework.beans.factory.annotation.Qualifier` và bean thực có qualifier/name thích hợp. Với constructor injection, bạn có thể đặt `@Qualifier` lên **tham số constructor** tương ứng; chuyển cơ chế injection không tự xử lý ambiguity.

### `final` và thread safety

Không cố biến field injection thành `private final Repository repository` rồi kỳ vọng Spring sẽ bypass hoàn toàn invariant construction. Trong code thông thường, `final` phải được khởi tạo đúng lúc xây object; constructor injection là con đường rõ ràng.

Tuy nhiên, giữ reference `final` chỉ giúp **stable wiring**, không bảo đảm repository object bất biến hoặc xử lý concurrency an toàn. Một singleton có mutable fields vẫn có thể xảy ra race khi dùng từ nhiều threads. Cần thiết kế stateless hoặc kiểm soát synchronization phù hợp.

### Circular dependency

Field/setter injection đôi khi khiến một số chu trình phụ thuộc được xử lý thông qua early references, nhưng không phải mọi trường hợp. Những object chưa hoàn tất initialization có thể khó hiểu; **không dùng field injection làm giải pháp mặc định cho vòng phụ thuộc**. Hãy xem lại hướng phụ thuộc, trách nhiệm của class và cách tách services.

## 9. Khi nào nên giữ field injection, khi nào nên refactor?

**Ưu tiên constructor injection** khi:
- Dependency **bắt buộc** để object hoạt động đúng.
- Cần unit test service bằng fake/stub/mock mà không khởi động Spring.
- Muốn fields `final` và construction invariant rõ.
- Business class phải dùng được trong console/batch hoặc Java code độc lập.
- Muốn review dependency graph qua constructor và phát hiện class có quá nhiều phụ thuộc.

**Có thể tạm giữ field injection** khi:
- Bảo trì mã legacy có số lượng class lớn; thay constructor có thể đòi chỉnh sửa nhiều entry points.
- Mã thuộc framework adapter do Spring luôn quản lý, cần xác minh chủ yếu qua context và không có nhu cầu new trực tiếp.
- Đang chuyển dần sang constructor injection theo từng bước có test bảo vệ; không nên refactor một cách máy móc nếu ảnh hưởng hành vi chưa kiểm chứng.

Khi không sửa được class legacy, test có thể dùng context nhỏ hoặc reflection helper. Nhưng phải ghi rõ rằng **test phụ thuộc implementation detail** như tên field và yêu cầu quyền reflection. Spring Test `ReflectionTestUtils` cần artifact `spring-test` trong test scope; **POM ví dụ này không có artifact đó** vì không sử dụng reflection để chạy test.

Một phép so sánh thực tế: field injection rút ngắn code constructor vài dòng, nhưng có thể tăng số thao tác setup và số assumptions ở mỗi unit test. Đánh giá theo **tổng độ phức tạp** thay vì chỉ độ dài class.

## 10. Những lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| `new FieldWiredGreeter()` rồi gọi `greet()` bị NPE | Java không chạy Spring post-processors | Dùng constructor injection khi test Java thuần hoặc test thông qua context |
| `@Autowired` field trên object tạo bằng `new` vẫn null | Object không được container quản lý | Đăng ký bean đúng hoặc thiết kế class không phụ thuộc container |
| Spring startup lỗi thiếu repo | Field required không có candidate | Xem bean registration, component scan và type/qualifier |
| Nhiều repositories cùng type | Candidate mơ hồ | `@Qualifier`, `@Primary` hoặc cấu hình rõ |
| Field được dùng trong constructor | Injection diễn ra sau construction | Truyền required dependency qua constructor |
| Test không thể gán private field | Dependency không có seam để truyền vào | Refactor constructor; legacy mới cân nhắc context/reflection |
| `final` field vẫn cho phép thay đổi nội dung object con | `final` khóa reference, không khóa object graph | Immutable value objects/defensive copies/concurrency design |
| `@Autowired(required=false)` vẫn gây NPE | Field null nhưng business code không kiểm tra | Xác định dependency thật sự optional hay required |
| Test quá chậm vì phải mở Spring cho từng method | Dùng context cả cho test behavior đơn giản | Tách unit tests dùng fake và integration tests wiring |
| Field/circular dependency dẫn tới object nửa khởi tạo | Graph phụ thuộc vòng hoặc lifecycle không rõ | Phá vòng, dùng design với hướng phụ thuộc đơn giản |
| Lỗi Maven `package org.springframework...` | Thiếu Spring trên compile classpath | Đúng `spring-context`, sync Maven, kiểm JDK |
| Kết quả stdout khác bản gốc | Source/config đã chỉnh hoặc log nền xen vào | Chạy source gốc, phân biệt stdout ứng dụng với diagnostic |

**Phân tầng lỗi:** thiếu JAR là lỗi classpath/build; thiếu bean required là lỗi container wiring; tạo đối tượng Java bằng `new` rồi dùng field null là lỗi construction contract; business trả kết quả sai là lỗi nghiệp vụ. Không dùng một loại giải pháp cho tất cả.

## 11. Bài tập thực hành và checklist

Làm từng thử nghiệm trên **bản sao**, khôi phục source giữa các bài để so với stdout gốc:

1. **Refactor:** đổi `FieldWiredGreeter` sang constructor nhận `GreetingRepository`, sửa factory `fieldWiredGreeter(repo)`, rồi viết unit test thuần Java không cần context.
2. **Giữ field, dùng Spring:** thêm test assert reference của repository trong field bean sau khi context khởi tạo (qua một method quan sát, không yêu cầu reflection).
3. **Bỏ bean repo:** xóa `@Bean greetingRepository()` trong bản sao; quan sát startup failure và cause chain.
4. **Thêm candidate thứ hai:** đăng ký thêm bean `GreetingRepository`; dự đoán ambiguity ở field và factory-method injection.
5. **Dùng qualifier:** chỉ định bean được chọn, xác nhận cả hai services nhận implementation mong đợi.
6. **Thử `@Autowired(required=false)`:** giả định không có repo; giải thích vì sao service phải có fallback hợp lệ trước khi đổi thành optional.
7. **Test fake khác:** sửa lambda fake trong JUnit thành `name -> "TEST2:" + name`, cập nhật assertion mà không sửa business class.
8. **Kiểm `final`:** thử gán lại repository sau constructor trong constructor service; quan sát lỗi compiler.
9. **Gọi dependency từ constructor field service:** mô tả vì sao dùng field injected quá sớm.
10. **Bỏ context:** dùng `PlainJavaGreeter` để kiểm tra thuật toán `greet` và null validation chỉ với `javac`/`java`.
11. **Nhiều contexts:** so sánh object identity qua hai contexts, giải thích singleton có phạm vi theo container.
12. **Thiết kế test suite:** lập nhóm pure unit test cho logic và integration tests cho bean wiring, xác định test nào nên chạy thường xuyên hơn.

**Checklist:**
- [ ] Field injection dùng `@Autowired` trên field của **Spring-managed bean**.
- [ ] Spring xử lý field sau construction; `new` Java không tự kích hoạt wiring.
- [ ] Constructor injection cho phép tạo object hợp lệ với fake trong unit test.
- [ ] `final` là ràng buộc reference, không đồng nghĩa deep immutability hoặc thread safety.
- [ ] 8 dòng stdout Maven và 2 dòng stdout Java thuần dự đoán đúng.
- [ ] 3 bài test JUnit phân biệt được behavior, negative scenario và Spring wiring.
- [ ] `@Autowired(required=false)` chỉ phù hợp dependency tùy chọn thực sự.
- [ ] Xử lý thiếu/mơ hồ bean với cấu hình đúng, không che lỗi bằng annotation.
- [ ] Biết khi nào dùng test context, khi nào dùng fake Java thuần và vì sao reflection test dễ giòn.

## 12. Tóm tắt và nguồn tham khảo

Field injection **hoạt động trong Spring** nhưng làm required dependency ít rõ trong API khởi tạo: unit test trực tiếp với `new` dễ tạo ra object chưa được tiêm. Constructor injection hiển thị hợp đồng, hỗ trợ `private final`, fail-fast với null guard và cho phép kiểm thử hành vi bằng fake thuần Java. Với Spring app, hai cơ chế vẫn cần bean configuration chính xác.

Các nguồn chính thức để tra cứu:
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — Annotation-based Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework — Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [JUnit 5.12.2 Guide](https://docs.junit.org/5.12.2/user-guide/)
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)

**Ghi nhớ:** Tối ưu testability không phải bỏ DI hay bỏ Spring, mà là **đặt dependency vào hợp đồng rõ ràng của đối tượng**, dùng Spring để lắp ráp graph và chỉ dựng container trong những test thật sự cần xác nhận Spring wiring.