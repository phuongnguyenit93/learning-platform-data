# @Configuration, @Bean và @Import trong cấu hình bằng Java

## 1. Bài toán: ai tạo và kết nối đối tượng trong ứng dụng?

Trong Java thông thường, mã nghiệp vụ có thể tự gọi `new` rồi truyền đối tượng cho nhau. Trong ứng dụng Spring, cách làm phổ biến là khai báo đối tượng nào do **Spring container** quản lý và để container tạo, kết nối, theo dõi vòng đời của chúng. Đối tượng được quản lý gọi là **bean**; nơi chứa và cung cấp bean thường được truy cập qua `ApplicationContext`.

**Cấu hình bằng Java (Java-based configuration)** là cách mô tả việc đăng ký những bean đó bằng lớp và phương thức Java. Ba annotation nền tảng có nhiệm vụ khác nhau:

- `@Configuration`: đánh dấu **một lớp là nguồn khai báo cấu hình Spring**.
- `@Bean`: đánh dấu **một phương thức tạo hoặc cung cấp đối tượng để container đăng ký thành bean**.
- `@Import`: **đưa thêm lớp cấu hình hoặc thành phần khác vào tập cấu hình được xử lý**, kể cả khi nó nằm ngoài phạm vi component scan.

Hình dung ba lớp trách nhiệm:

~~~text
Java configuration được đưa vào ApplicationContext
    |
    +-- @Configuration: đây là lớp nguồn cấu hình
    |       |
    |       +-- @Bean: đăng ký cách tạo BeanDefinition cho object A
    |       +-- @Bean: đăng ký cách tạo BeanDefinition cho object B
    |                       ^
    |                       | Spring giải quyết phụ thuộc bằng injection
    |
    +-- @Import(OtherConfiguration.class)
            |
            +-- @Bean: thêm định nghĩa object C

BeanDefinition được đăng ký
    -> Spring tạo instance theo nhu cầu/phạm vi/vòng đời
    -> bean có thể được tra cứu/inject từ ApplicationContext
~~~

Không đồng nhất **lớp cấu hình**, **định nghĩa bean** (`BeanDefinition`) và **instance bean**. Spring có thể biết cách tạo bean từ rất sớm, nhưng bean singleton lazy hoặc prototype chưa chắc đã được tạo ngay. Cũng không phải mọi object Java đều là bean: đối tượng tạo bằng `new` bên ngoài quy trình của container không tự động được quản lý.

### Vị trí của ba annotation trong Spring Boot

`@SpringBootApplication` bao gồm `@SpringBootConfiguration`, `@EnableAutoConfiguration` và `@ComponentScan`. `@SpringBootConfiguration` là một dạng cấu hình Spring; còn `@EnableAutoConfiguration` sử dụng cơ chế nhập cấu hình để chọn các auto-configuration phù hợp. Vì thế, hiểu `@Configuration`, `@Bean`, `@Import` là điều kiện nền trước khi tìm hiểu vì sao một auto-configuration có thể tạo hoặc không tạo bean.

Tuy nhiên, **một `@Configuration` thông thường không tự động trở thành auto-configuration**. Trong Spring Boot 3.x, auto-configuration thư viện cần được giới thiệu qua `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, thường kèm các điều kiện `@Conditional...`. `@Import(MyConfig.class)` là nhập **tường minh**; cơ chế lựa chọn auto-configuration dựa trên danh sách ứng viên và điều kiện là một bước rộng hơn.

## 2. `@Configuration`: khai báo một nguồn bean definitions

Một lớp được chú thích `@Configuration` cho Spring biết rằng lớp này có thể khai báo những bean và nhập thêm cấu hình khác. Ví dụ đơn giản:

~~~java
package example.config;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {
    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

Khi `TimeConfiguration` được đưa vào `ApplicationContext`, phương thức `applicationClock()` được phân tích để đăng ký bean kiểu `Clock`, mặc định có tên `applicationClock`. Việc khai báo lớp `TimeConfiguration` trong project **chưa đủ**: nó cần được xử lý thông qua component scan, `@Import`, đăng ký trực tiếp với context, hoặc cơ chế nhập cấu hình khác.

### Đưa lớp `@Configuration` vào ứng dụng

Các đường đi phổ biến:

1. **Component scan:** đặt class trong gói được quét bởi `@ComponentScan`; `@Configuration` mang đặc tính của `@Component`.
2. **Nhập tường minh:** dùng `@Import(TimeConfiguration.class)` trên một cấu hình đã được xử lý.
3. **Đăng ký trực tiếp:** dùng `AnnotationConfigApplicationContext.register(TimeConfiguration.class)` trong ứng dụng Spring Framework thuần.
4. **Auto-configuration của Spring Boot:** lớp phù hợp được nạp thông qua cơ chế ứng viên auto-configuration; đây là quy trình riêng có điều kiện và chọn lọc.

Ví dụ, đặt `DemoApplication` trong gói `example.app`, `TimeConfiguration` trong `example.config` thì component scan mặc định từ `example.app` không tự quét sang gói ngang cấp. `@Import` là cách nhập có chủ đích, rõ ràng ở mã nguồn.

### `@Configuration` là bean hay chỉ là khai báo?

Bản thân lớp cấu hình thường cũng được container đăng ký và khởi tạo để phục vụ các phương thức factory, nhưng điều đó không biến **mọi method** của nó thành bean. Chỉ những method đáp ứng cơ chế xử lý tương ứng (như `@Bean`) mới đóng góp định nghĩa bean. `@Configuration` không có nghĩa mỗi class trong cùng package đều được tạo.

## 3. `@Bean`: khai báo cách tạo và quản lý một bean

Annotation `@Bean` đặt trên phương thức factory. Spring xử lý khai báo đó thành `BeanDefinition` và gọi phương thức khi cần tạo đối tượng.

~~~java
@Configuration
public class ClientConfiguration {
    @Bean
    ApiClient apiClient() {
        return new ApiClient("https://example.org");
    }
}
~~~

*Đây là đoạn minh họa; `ApiClient` là kiểu giả định, chưa có định nghĩa trong ví dụ.* Trong một chương trình hoàn chỉnh, container có thể cung cấp bean `ApiClient` cho nơi khác qua constructor injection.

### Tên, kiểu và phụ thuộc

- **Tên:** mặc định trùng tên phương thức, ví dụ `apiClient`; có thể đặt `@Bean("primaryClient")` hoặc các tên/alias theo cú pháp annotation.
- **Kiểu:** dựa vào kiểu trả về được khai báo và đối tượng thực tế; khi các điều kiện cần nhận diện kiểu, nên khai báo kiểu trả về có thông tin hữu ích, thay vì kiểu quá chung như `Object`.
- **Tham số:** Spring giải quyết tham số phương thức `@Bean` bằng cơ chế dependency injection. Khi cần `Clock`, hãy khai báo `myService(Clock clock)` thay vì tự gọi trực tiếp `clock()`.
- **Phạm vi:** mặc định bean có scope singleton trong một container; có thể đổi bằng `@Scope`. `@Lazy` ảnh hưởng thời điểm tạo instance.
- **Vòng đời:** đối tượng có thể tham gia khởi tạo/hủy theo callback Spring; ví dụ `@Bean(initMethod = "start", destroyMethod = "close")` nếu kiểu đối tượng có các method tương ứng.

Tham số phương thức bean là **dependency** được giải quyết theo quy tắc autowiring, không nhất thiết là biến lấy từ một method khác trong cùng class:

~~~java
@Configuration(proxyBeanMethods = false)
class ReportConfiguration {
    @Bean
    ReportRepository reportRepository() {
        return new ReportRepository();
    }

    @Bean
    ReportService reportService(ReportRepository repository) {
        return new ReportService(repository);
    }
}
~~~

*Đoạn minh họa: giả sử có sẵn hai class `ReportRepository` và `ReportService` với constructor tương ứng.* Spring lấy bean `ReportRepository` để truyền cho `reportService`. Cách viết này làm quan hệ phụ thuộc rõ ràng và vẫn đúng khi tắt cơ chế proxy của `@Configuration`.

### Khi có nhiều bean cùng kiểu

Nếu container có hai bean `PaymentGateway`, một injection theo kiểu `PaymentGateway` đơn lẻ có thể mơ hồ. Khi thích hợp, dùng `@Qualifier` để chọn tên/qualifier cụ thể, `@Primary` để đặt ưu tiên mặc định, hoặc tiêm danh sách/map các bean. **`@Bean("someName")` không đồng nghĩa với bean này luôn được chọn khi inject theo kiểu**.

Không nhầm **trùng tên bean** và **nhiều bean cùng kiểu**: đây là hai tình huống khác nhau. Spring Boot mặc định hạn chế việc vô tình ghi đè định nghĩa trùng tên, còn nhiều bean cùng kiểu có thể hợp lệ nếu injection được phân giải đúng.

## 4. Hai chế độ của `@Configuration`: `proxyBeanMethods`

Đây là chỗ dễ hiểu sai nhất khi học cấu hình bằng Java.

### Chế độ mặc định: `@Configuration(proxyBeanMethods = true)`

Theo mặc định, Spring tăng cường (enhance) lớp cấu hình bằng một subclass tạo lúc chạy để chặn các lời gọi đến phương thức `@Bean` theo cách phù hợp vòng đời bean. Với một bean singleton, lời gọi trực tiếp giữa các phương thức bean trên **instance cấu hình do Spring quản lý** có thể trả lại đúng đối tượng singleton từ container, thay vì cứ tạo đối tượng mới.

~~~java
@Configuration // proxyBeanMethods mặc định là true
class FullConfiguration {
    @Bean
    Store store() {
        return new Store();
    }

    @Bean
    Checkout checkout() {
        return new Checkout(store());
    }
}
~~~

*Đoạn minh họa: `Store` và `Checkout` là kiểu giả định, `Checkout` nhận `Store` qua constructor.* Khi Spring gọi `checkout()`, lời gọi `store()` trong class được tăng cường sẽ tuân theo quản lý bean. Cơ chế này gọi là **inter-bean method reference**.

Điều kiện đi kèm: lớp và phương thức cần tương thích với việc tạo subclass/proxy; không được khai báo class `final` hay method `@Bean` `final`/`private` khi cần interception kiểu này. Đây là proxy phục vụ cấu hình, khác với proxy AOP cho `@Transactional`.

### Chế độ không can thiệp lời gọi method: `proxyBeanMethods = false`

~~~java
@Configuration(proxyBeanMethods = false)
class LiteConfiguration {
    @Bean
    Store store() {
        return new Store();
    }

    @Bean
    Checkout checkout() {
        return new Checkout(store()); // Lời gọi Java trực tiếp.
    }
}
~~~

Nếu các class giả định là class thông thường, `store()` ở dòng thứ hai là lời gọi Java và tạo **một Store mới**, không phải cách bảo đảm lấy bean `store` đã đăng ký. Container vẫn đăng ký bean singleton tên `store` từ factory method riêng; nhưng object `Store` được tạo khi gọi trực tiếp ở `checkout()` có thể là object khác và không được quản lý như một bean riêng. Điều này có thể gây hai instance ngoài ý định.

Cách an toàn với `proxyBeanMethods = false`:

~~~java
@Configuration(proxyBeanMethods = false)
class LiteConfiguration {
    @Bean
    Store store() {
        return new Store();
    }

    @Bean
    Checkout checkout(Store store) {
        return new Checkout(store);
    }
}
~~~

Spring truyền bean `Store` đang quản lý vào phương thức `checkout`. Đây cũng là cách nên ưu tiên khi viết auto-configuration hoặc các cấu hình factory độc lập, bởi nó làm dependency rõ ràng và không cần interception giữa các method.

| Khía cạnh | `proxyBeanMethods=true` | `proxyBeanMethods=false` |
| --- | --- | --- |
| Lời gọi `anotherBeanMethod()` trong class cấu hình | Được Spring can thiệp để tôn trọng scope và bean trong context | Lời gọi method Java thông thường |
| Class/method `final` | Bị giới hạn bởi yêu cầu subclass/interception | Không cần subclass để chặn method bean |
| Cách khai báo dependency được khuyến nghị | Method parameters vẫn rõ ràng, dễ kiểm tra | Method parameters là cách an toàn, nên dùng |
| Mục đích | Cần semantics inter-bean direct calls | Các factory method độc lập, giảm yêu cầu proxy |

**Phân biệt:** `@Bean` trong class `@Component` thông thường cũng có cơ chế xử lý kiểu *lite*; đừng kỳ vọng direct call tới method bean ở đó được Spring chặn như trong `@Configuration(proxyBeanMethods=true)`.

## 5. `@Import`: ghép các phần cấu hình bằng Java

`@Import` có thể đặt trên một lớp cấu hình hoặc trên annotation tùy biến. Nó đưa các lớp đã chỉ rõ vào quá trình xử lý cấu hình. Trường hợp cơ bản nhất:

~~~java
@Configuration(proxyBeanMethods = false)
@Import({DataConfiguration.class, ServiceConfiguration.class})
class ApplicationConfiguration {
}
~~~

Spring xử lý `DataConfiguration` và `ServiceConfiguration` cùng các khai báo bean của chúng, mặc dù các lớp đó có thể nằm ngoài phạm vi component scan.

`@Import` không tạo bản sao bean chỉ vì bạn khai báo cùng class ở hai nơi. Điều quan trọng là **lớp nào được đăng ký** và **các bean definitions nào được tạo**; không nên cố dùng import nhiều lần làm chiến lược tạo nhiều instance.

### Có thể import gì?

- **Class `@Configuration`:** tình huống chính, để mang vào các `@Bean` và import tiếp theo.
- **Class component thông thường:** các class có thể được Spring đăng ký như thành phần cấu hình/bean phù hợp, không nhất thiết phải được đánh dấu `@Configuration`.
- **`ImportSelector`:** logic chọn danh sách tên lớp cần nhập dựa trên metadata annotation.
- **`ImportBeanDefinitionRegistrar`:** logic đăng ký `BeanDefinition` bằng mã, khi cú pháp `@Bean` hoặc nhập lớp thông thường không đủ.

Hai SPI sau là phần mở rộng nâng cao. Ở mức nền tảng, chỉ cần hiểu `@Import(SomeConfiguration.class)`; không cần viết `ImportSelector` cho mỗi chức năng.

### `@Import` so với các cách “import” dễ nhầm

| Cơ chế | Thứ được đưa vào | Điểm khác biệt |
| --- | --- | --- |
| Java `import java.time.Clock;` | Tên kiểu vào phạm vi biên dịch | **Không** đăng ký bean |
| `@ComponentScan` | Các component được tìm theo package/filter | Quét theo quy tắc phạm vi |
| `@Import(X.class)` | Class cấu hình, component hoặc SPI nhập được chỉ định | Tường minh theo class |
| `@ImportResource("classpath:...")` | Bean definitions từ tài nguyên cấu hình như XML | Dành cho cấu hình dựa trên resource |
| Spring Boot `spring.config.import` | Tài liệu thuộc tính/cấu hình ngoài (`.properties`, `.yml`...) | Thuộc đường nạp **configuration data**, không nhập Java `@Configuration` |
| Spring Boot `AutoConfiguration.imports` | Danh sách lớp **ứng viên** auto-configuration trong JAR | Boot chọn và đánh giá điều kiện trước khi đóng góp bean |

### Import có điều kiện

Có thể đặt `@Conditional` trên lớp cấu hình hoặc `@Bean` bên trong lớp được import. Import chỉ làm lớp đó được **xem xét**, không có nghĩa mọi điều kiện đều đạt. Ví dụ trong Spring Boot, auto-configuration thường kết hợp `@ConditionalOnClass`, `@ConditionalOnProperty` và `@ConditionalOnMissingBean` để quyết định bean nào thực sự được đăng ký.

Đối với thư viện, không thay cơ chế `AutoConfiguration.imports` bằng lời gọi `@Import` thủ công từ ứng dụng rồi gọi đó là “tự cấu hình”. Nếu người dùng phải import class rõ ràng, đó là cấu hình nhập tường minh. Có thể dùng `@Import` **bên trong** auto-configuration để tách cấu hình con theo chức năng.

## 6. Ví dụ hoàn chỉnh: cấu hình ở ngoài component scan, nhập bằng `@Import`

Ví dụ này dùng **Java 17+**, **Spring Boot 3.3.13** và **Maven 3.9+**. Nó chứng minh cả ba annotation trong một ứng dụng chạy được, đồng thời làm rõ:

1. Cấu hình ở gói không được quét chỉ tham gia do `@Import`.
2. `@Bean` đăng ký `Clock` và `GreetingService`.
3. Spring dùng tham số `@Bean` để inject đúng đối tượng `Clock`.
4. `proxyBeanMethods=false` an toàn vì factory methods không gọi trực tiếp lẫn nhau.

### Cấu trúc file

~~~text
java-config-demo/
├── pom.xml
└── src/main/java/
    └── lesson/
        ├── app/
        │   └── DemoApplication.java
        ├── config/
        │   ├── CoreConfiguration.java
        │   └── FeatureConfiguration.java
        └── domain/
            └── GreetingService.java
~~~

#### `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>lesson</groupId>
    <artifactId>java-config-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter` đủ cho ví dụ console dùng `ApplicationContext`. Không cần chạy web server.

#### `src/main/java/lesson/domain/GreetingService.java`

~~~java
package lesson.domain;

import java.time.Clock;
import java.time.LocalDate;

public final class GreetingService {
    private final Clock clock;

    public GreetingService(Clock clock) {
        this.clock = clock;
    }

    public String greet(String name) {
        return "Xin chào " + name + " ngày " + LocalDate.now(clock);
    }
}
~~~

`GreetingService` là class Java bình thường, không có `@Component`. Nó chỉ trở thành bean khi được một cấu hình đăng ký.

#### `src/main/java/lesson/config/CoreConfiguration.java`

~~~java
package lesson.config;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CoreConfiguration {
    @Bean
    public Clock appClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
~~~

`Clock.fixed` làm ngày chạy ổn định, nên có thể dự đoán chính xác kết quả ở mọi máy và mọi thời điểm. Bean tên `appClock` có kiểu `Clock`.

#### `src/main/java/lesson/config/FeatureConfiguration.java`

~~~java
package lesson.config;

import java.time.Clock;
import lesson.domain.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@Configuration(proxyBeanMethods = false)
@Import(CoreConfiguration.class)
public class FeatureConfiguration {
    @Bean("greetingService")
    public GreetingService greetingService(Clock appClock) {
        return new GreetingService(appClock);
    }
}
~~~

`@Import(CoreConfiguration.class)` thêm cấu hình cung cấp `Clock`. Tham số `Clock appClock` được Spring inject theo kiểu. Không có lời gọi `new CoreConfiguration()` hay `appClock()` thủ công, nên không phụ thuộc vào cơ chế chặn lời gọi method.

#### `src/main/java/lesson/app/DemoApplication.java`

~~~java
package lesson.app;

import java.util.Arrays;
import lesson.config.FeatureConfiguration;
import lesson.domain.GreetingService;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Import;

@SpringBootApplication(scanBasePackages = "lesson.app")
@Import(FeatureConfiguration.class)
public class DemoApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(DemoApplication.class, args)) {
            GreetingService greeting = context.getBean(
                "greetingService", GreetingService.class
            );
            String[] names = context.getBeanNamesForType(
                GreetingService.class
            );
            Arrays.sort(names);

            System.out.println("names=" + Arrays.toString(names));
            System.out.println(greeting.greet("Lan"));
            System.out.println("clock=" + context.containsBean("appClock"));
        }
    }
}
~~~

Việc chỉ quét `lesson.app` là có chủ ý: `lesson.config` là gói ngang cấp, **không** được tự quét. Nhờ `@Import(FeatureConfiguration.class)`, ứng dụng nhập `FeatureConfiguration`; lớp này tiếp tục nhập `CoreConfiguration`. Mỗi cấu hình sau đó đóng góp các `@Bean` tương ứng.

### Chạy ứng dụng

Đặt năm file đúng đường dẫn ở trên, vào thư mục chứa `pom.xml` rồi chạy:

~~~bash
java -version
mvn -version
mvn -q spring-boot:run
~~~

Các dòng do chính chương trình `System.out.println` ghi ra, theo đúng thứ tự, là:

~~~text
names=[greetingService]
Xin chào Lan ngày 2026-01-01
clock=true
~~~

Các log Spring Boot, nếu có, xuất hiện thêm tùy môi trường. Ví dụ này không sử dụng ngày hệ thống vì `Clock` là fixed clock.

### Lần theo quá trình tạo bean

~~~text
DemoApplication
  @SpringBootApplication(scanBasePackages="lesson.app")
  @Import(FeatureConfiguration.class)
          |
          v
FeatureConfiguration (@Configuration)
  @Import(CoreConfiguration.class)
  @Bean greetingService(Clock appClock)
          |                     ^
          v                     |
CoreConfiguration (@Configuration)
  @Bean appClock(): Clock -------+
          |
          v
Spring đăng ký BeanDefinition cho appClock và greetingService
          |
          v
Tạo Clock -> truyền vào factory method greetingService(...)
          |
          v
ApplicationContext có bean "appClock" và "greetingService"
~~~

Thứ tự trên mô tả **phụ thuộc logic**, không khẳng định Spring luôn thực thi từng bước theo đúng thứ tự dòng khi xử lý mọi loại scope. Định nghĩa có thể được đăng ký trước khi các instance được tạo.

## 7. Ba phép thử để thấy rõ vai trò từng annotation

### Thử 1: bỏ `@Import` ở `DemoApplication`

Xóa đúng dòng `@Import(FeatureConfiguration.class)` nhưng giữ `scanBasePackages = "lesson.app"`. Vì hai lớp cấu hình nằm trong `lesson.config`, chúng không còn đường nạp theo component scan trong chương trình này.

Khi mã chạy đến `context.getBean("greetingService", GreetingService.class)`, nó ném `NoSuchBeanDefinitionException`. Do ứng dụng không bắt exception ấy, không có ba dòng output thành công nêu trên. Kết luận: chỉ có file Java chứa `@Configuration`/`@Bean` không bảo đảm container nhận được định nghĩa bean.

### Thử 2: giữ import ngoài, bỏ import bên trong

Giữ `@Import(FeatureConfiguration.class)`, nhưng xóa `@Import(CoreConfiguration.class)` trên `FeatureConfiguration`. Bean `greetingService` vẫn có định nghĩa factory method, nhưng không còn bean `Clock` do `CoreConfiguration` cung cấp. Khi Spring tạo singleton `GreetingService`, việc giải quyết tham số `Clock` thất bại; ứng dụng không hoàn tất khởi động bình thường, thường có chuỗi lỗi `UnsatisfiedDependencyException` dẫn tới `NoSuchBeanDefinitionException`. Thông điệp chi tiết có thể khác theo phiên bản/môi trường.

Kết luận: `@Bean` có tham số nghĩa là một yêu cầu dependency mà container phải giải quyết. Việc có bean definition của dịch vụ chưa bảo đảm có đủ dependency để khởi tạo instance.

### Thử 3: thêm một `Clock` tùy chọn trong app

Trong một class cấu hình được xử lý, giả sử khai báo thêm bean `Clock` khác. Khi `greetingService(Clock appClock)` cần injection theo kiểu, nó có thể trở nên mơ hồ nếu có nhiều `Clock` và không có thông tin ưu tiên. Sửa bằng `@Qualifier("appClock")` trên tham số hoặc thiết kế một bean `@Primary` phù hợp; đừng dựa vào thứ tự khai báo method để chọn ngẫu nhiên.

Ví dụ thay chữ ký và thêm import (chỉ là đoạn thay thế cho code hoàn chỉnh):

~~~java
import org.springframework.beans.factory.annotation.Qualifier;

@Bean("greetingService")
public GreetingService greetingService(@Qualifier("appClock") Clock clock) {
    return new GreetingService(clock);
}
~~~

Lưu ý: đây là **đoạn thay thế** trong `FeatureConfiguration` sau khi thêm import tương ứng, không phải một lớp Java độc lập. Nếu muốn kiểm chứng case nhiều bean, cần thực sự khai báo bean `Clock` thứ hai ở cấu hình được nạp.

## 8. `@Configuration`, `@Bean`, `@Import` tham gia auto-configuration như thế nào?

Các mảnh kiến thức vừa học liên hệ trực tiếp với cơ chế Spring Boot:

~~~text
@SpringBootApplication
   |
   +-- @SpringBootConfiguration -> nguồn cấu hình gốc của ứng dụng
   |
   +-- @ComponentScan -> tìm component/config của ứng dụng
   |
   +-- @EnableAutoConfiguration
          |
          +-- cơ chế selector (DeferredImportSelector)
               |
               +-- đọc danh sách AutoConfiguration.imports
               +-- lọc exclusions và điều kiện
               +-- nhập auto-configuration phù hợp
                    |
                    +-- @AutoConfiguration (một dạng @Configuration)
                         |
                         +-- @Import(...) nếu muốn chia cấu hình con
                         +-- @Bean ... @Conditional... -> bean definitions
~~~

Điểm quan trọng là **nhập cấu hình** và **thỏa điều kiện** là hai bước có thể phân biệt:

- `@Import(FooConfiguration.class)` của người viết ứng dụng thể hiện lựa chọn tường minh: đưa `FooConfiguration` vào tập cần xử lý.
- `@EnableAutoConfiguration` trong Boot dựa trên một bộ chọn nhập cấu hình, lấy danh sách ứng viên từ `AutoConfiguration.imports` rồi xét exclusions/conditions phù hợp.
- Một lớp `@AutoConfiguration` dùng những cơ chế `@Configuration`/`@Bean` quen thuộc để khai báo bean; thêm `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty`... để bean mặc định nhường chỗ hoặc chỉ bật khi môi trường đủ điều kiện.
- `@Import` trên một lớp auto-configuration có thể nhập các lớp `@Configuration` phụ. Điều kiện đặt trên class/bean được nhập vẫn được xét theo quy tắc của chính nó.

Ví dụ minh họa một auto-configuration thư viện:

~~~java
@AutoConfiguration
@ConditionalOnClass(RemoteClient.class)
public class RemoteClientAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(RemoteClient.class)
    RemoteClient remoteClient() {
        return new RemoteClient();
    }
}
~~~

Đây là **đoạn minh họa**, giả định có kiểu `RemoteClient` và dependency phù hợp. Để trở thành auto-configuration tự động được phát hiện trong Boot 3.x, tên đầy đủ của class còn phải được khai báo trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Nếu ứng dụng đã khai báo bean `RemoteClient` phù hợp, phương thức mặc định thường nhường chỗ do điều kiện `@ConditionalOnMissingBean`. Không sử dụng `@ConditionalOnMissingBean` bừa bãi trong mọi lớp cấu hình thông thường: kết quả điều kiện phụ thuộc vào những định nghĩa bean đã được xử lý tại thời điểm đánh giá; tài liệu Spring Boot khuyến nghị nhóm điều kiện `OnBean`/`OnMissingBean` trong auto-configuration để phù hợp thứ tự nạp.

### Khi nào dùng kiểu nào?

| Nhu cầu | Lựa chọn |
| --- | --- |
| Đăng ký dịch vụ/hạ tầng do ứng dụng sở hữu | `@Configuration` và `@Bean` |
| Tách cấu hình lớn thành các phần rõ ràng | `@Import(PartConfiguration.class)` |
| Để Spring tìm các component trong một gói | `@ComponentScan` hoặc scan mặc định từ `@SpringBootApplication` |
| Cung cấp cấu hình mặc định cho thư viện dùng lại trong nhiều ứng dụng Boot | `@AutoConfiguration` + file `AutoConfiguration.imports` + điều kiện phù hợp |
| Nạp tài liệu thuộc tính ngoài | `spring.config.import`, không phải `@Import` |

## 9. Những lỗi thường gặp và cách lần ra nguyên nhân

| Triệu chứng/quan niệm | Nguyên nhân có thể và cách kiểm tra |
| --- | --- |
| Đã tạo class `@Configuration` nhưng không có bean | Class chưa được scan/import/đăng ký. Xem gói của main class và phạm vi component scan. |
| Có `@Bean` mà thiếu bean khi inject | Cấu hình không được xử lý, điều kiện không đạt hoặc bean chưa tạo được do thiếu dependency. |
| Dùng `new SomeConfiguration().bean()` | Đây là lời gọi ngoài container, không đại diện cho cách Spring quản lý bean/lifecycle. |
| Tắt `proxyBeanMethods` nhưng gọi `otherBean()` trực tiếp | Có thể tạo object Java mới không phải bean đang được quản lý; dùng tham số factory method thay thế. |
| Tạo hai bean cùng kiểu và injection lỗi | Dùng `@Qualifier`/`@Primary` hoặc thay chữ ký dependency theo ý nghĩa thực sự. |
| Thấy `@Import` nhưng tưởng quét cả package | `@Import` nhập chính xác class/SPI được chỉ định; `@ComponentScan` mới quét các lớp phù hợp trong package. |
| Tưởng Java `import` tạo bean | Java `import` chỉ hỗ trợ dùng tên kiểu trong mã nguồn. |
| Tưởng `spring.config.import` nạp Java config | Thuộc tính này nạp configuration data, không thay thế `@Import`. |
| Dùng `@AutoConfiguration` trong package scan rồi kỳ vọng cơ chế auto-config | Auto-configuration nên được nạp bằng `AutoConfiguration.imports`, nằm ngoài component scan. |
| Đoán thứ tự bean từ thứ tự các method/import | Quy tắc đăng ký định nghĩa và thứ tự **khởi tạo** phụ thuộc vào quan hệ dependency, scope, lifecycle. |

### Quy trình chẩn đoán bằng bằng chứng

1. Tìm bean cần kiểm tra, xác nhận **tên và kiểu** dự kiến.
2. Tìm phương thức `@Bean` hoặc component cung cấp bean đó.
3. Kiểm tra class sở hữu có thực sự được nạp bằng scan, `@Import` hoặc auto-configuration hay không.
4. Nếu bean có tham số factory, kiểm tra container có cung cấp các dependency đó không.
5. Nếu liên quan auto-configuration, kiểm tra điều kiện và lý do khớp/không khớp bằng `--debug` hoặc báo cáo điều kiện của Spring Boot.
6. Xác thực trạng thái thực tế bằng `ApplicationContext#getBeanNamesForType`, `containsBean`, và khi cần các API truy vấn `BeanDefinition`.

Không suy từ “file Java tồn tại” rằng bean được tạo; cũng không coi exception thiếu bean ở một điểm injection là bằng chứng đủ để kết luận lỗi nằm ở `@Bean` được đề cập.

## 10. Luyện tập và câu hỏi tự kiểm tra

1. Vì sao `TimeConfiguration` ở `example.config` có thể không hoạt động khi main class nằm ở `example.app`? Nêu hai cách chủ động đăng ký nó.
2. Phân biệt ba kết quả: một class được đưa vào cấu hình, một `BeanDefinition` được đăng ký, một singleton instance được khởi tạo.
3. Giải thích sự khác nhau giữa `@Import(FeatureConfiguration.class)` và `@ComponentScan("lesson.config")` trong ví dụ.
4. Giải thích vì sao gọi `store()` trong `checkout()` khác nhau giữa `proxyBeanMethods=true` và `false`. Viết lại phương thức sử dụng tham số bean.
5. Bỏ từng annotation `@Import` theo hai phép thử ở mục 7. Dự đoán lỗi và xác nhận bằng log; phân biệt **không có BeanDefinition** với **có định nghĩa nhưng thiếu dependency khi tạo instance**.
6. Tại sao thêm `@AutoConfiguration` vào class của thư viện vẫn chưa đủ để nó được Spring Boot 3.x phát hiện tự động? Nêu tên file đăng ký chính xác.
7. Trong trường hợp có hai bean `Clock`, dùng `@Qualifier` có ý nghĩa gì so với dùng `@Primary`? Khi nào nên áp dụng mỗi cách?

**Tự đánh giá:** bạn có thể chỉ ra nơi cấu hình được phát hiện, nơi định nghĩa bean xuất hiện, cách Spring giải quyết tham số phương thức factory, và điểm phân biệt cấu hình nhập tường minh với auto-configuration có điều kiện.

## 11. Ghi nhớ để học các cơ chế tiếp theo

**`@Configuration` khai báo nguồn cấu hình; `@Bean` khai báo bean; `@Import` nối các nguồn cấu hình.** Cả ba đều tham gia xây dựng `ApplicationContext`; auto-configuration của Spring Boot sử dụng chính nền tảng ấy để nhập có chọn lọc cấu hình mặc định theo classpath, property, điều kiện và bean ứng dụng đã cung cấp.

Với những cấu hình mới, cách viết dễ kiểm tra là chia theo trách nhiệm, nhập tường minh khi cần, khai báo dependency bằng tham số `@Bean`, chọn `proxyBeanMethods=false` khi không cần gọi chéo method bean, và xác minh bean thực tế trong context thay vì đoán từ annotation.

**Tài liệu chính thức:**
- [Spring Framework — Using `@Configuration`](https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html)
- [Spring Framework — `@Bean` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Bean.html)
- [Spring Framework — `@Import` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Import.html)
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
