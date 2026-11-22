# ApplicationContext, BeanFactory và định nghĩa bean trong quá trình khởi động

## 1. Tại sao phải hiểu ba khái niệm này?

Khi ứng dụng Spring Boot khởi động, không phải cứ tìm thấy một lớp `@Component` hay một phương thức `@Bean` là Spring lập tức tạo đối tượng tương ứng. Trước hết Spring **đọc cấu hình và đăng ký các định nghĩa bean (bean definitions)**; sau đó **container** dựa vào các định nghĩa ấy để tạo đối tượng, giải quyết dependency, áp dụng các xử lý vòng đời và quản lý bean trong suốt thời gian ứng dụng chạy.

Ba khái niệm có mối liên hệ:

- **`BeanDefinition`**: bản mô tả/metadata cho biết một bean phải được tạo và cấu hình như thế nào.
- **`BeanFactory`**: hợp đồng lõi của Spring IoC container, có khả năng cung cấp bean theo tên hoặc kiểu, giải quyết dependency và quản lý vòng đời bean. Một triển khai quan trọng là `DefaultListableBeanFactory`.
- **`ApplicationContext`**: bề mặt container cấp ứng dụng, mở rộng khả năng tra cứu bean và bổ sung môi trường (`Environment`), tài nguyên, thông điệp quốc tế hóa, sự kiện ứng dụng và điều phối vòng đời. Trong các triển khai phổ biến, context sử dụng một `BeanFactory` bên trong.

Spring Boot **không thay thế** những thành phần này. `SpringApplication.run(...)` chuẩn bị và làm mới (`refresh`) một `ApplicationContext` của Spring Framework. Auto-configuration đóng góp thêm **định nghĩa bean có điều kiện** vào container ấy.

Sơ đồ tư duy:

```text
Nguồn cấu hình
  @Component / @Service / @Repository / @Controller
  @Configuration + @Bean / @Import
  BeanDefinitionRegistry / ImportBeanDefinitionRegistrar
  Spring Boot auto-configuration
                |
                v
       BeanDefinitionRegistry
          (danh sách định nghĩa)
                |
                v
        BeanFactory bên trong
   (giải quyết DI, tạo bean, scope,
        vòng đời, hậu xử lý)
                |
                v
       ApplicationContext
   (API của ứng dụng, Environment,
        events, resources, ...)
                |
                v
    Bean instance được sử dụng
```

Đây là **sơ đồ về trách nhiệm**, không mô tả từng bước chính xác của nội bộ Spring. Cũng không nên đồng nhất `BeanDefinitionRegistry` với một đối tượng vật lý hoàn toàn tách khỏi `BeanFactory`: `DefaultListableBeanFactory` là một ví dụ triển khai đồng thời nhiều hợp đồng này.

## 2. Bean, BeanDefinition và đối tượng Java thường khác nhau ra sao?

Một **bean** là đối tượng do Spring container quản lý. Một đối tượng tạo bằng `new` trong code ứng dụng chỉ là đối tượng Java thông thường, trừ khi nó được đăng ký hoặc được quản lý thông qua các cơ chế của container.

Một **`BeanDefinition`** là bản mô tả để container biết cách tạo và xử lý bean. Nó thường nắm các thông tin như:

| Thông tin | Ý nghĩa thực tế |
| --- | --- |
| Tên bean | Khóa nhận diện trong container, ví dụ `paymentService` |
| Bean class hoặc factory method | Tạo trực tiếp từ lớp hay gọi phương thức `@Bean`/factory |
| Scope | `singleton`, `prototype`, hoặc scope được cung cấp thêm |
| Lazy initialization | Có trì hoãn khởi tạo cho đến khi cần không |
| Dependency / constructor arguments | Dữ liệu và tham chiếu phục vụ việc tạo bean |
| Điều kiện và nguồn cấu hình liên quan | Quyết định bean definition có được đăng ký hay không; một phần điều kiện được đánh giá **trước lúc** có định nghĩa |
| Lifecycle metadata | Init/destroy method và thông tin phục vụ xử lý vòng đời khi có khai báo |

Ví dụ:

```java
@Configuration
class FeatureConfig {
    @Bean
    ReportFormatter reportFormatter() {
        return new ReportFormatter();
    }
}
```

Khi Spring xử lý `FeatureConfig`, nó có thể đăng ký bean definition tên `reportFormatter` gắn với factory method `reportFormatter()`. Điều này **chưa đồng nghĩa** đã có một `ReportFormatter` được tạo. Với singleton không lazy, Spring thường tạo bean trong giai đoạn hoàn tất `refresh()`; với bean được đánh dấu `@Lazy`, việc tạo có thể lùi đến lần sử dụng đầu tiên.

`BeanDefinition` không phải bản sao của đối tượng; nó cũng không phải bản ghi mọi giá trị runtime. Ví dụ, đối tượng tạo từ factory method có thể là AOP proxy sau các `BeanPostProcessor`, và kiểu cuối cùng của đối tượng sử dụng có thể không trùng hoàn toàn kiểu class được khai báo.

### Bean name, bean type và scope

- Có thể truy xuất bean bằng tên (`getBean("reportFormatter")`) hoặc bằng type (`getBean(ReportFormatter.class)`). Tra cứu theo type có thể không xác định nếu nhiều bean cùng type và không có cơ chế lựa chọn phù hợp.
- `singleton` là mặc định của Spring: **một instance cho mỗi bean definition trong một container**, không phải “một instance duy nhất trên toàn JVM”. Nhiều `ApplicationContext` có thể có các singleton khác nhau.
- `prototype` thường tạo đối tượng mới mỗi lần container được yêu cầu cung cấp bean. Spring không tự quản lý toàn bộ quá trình hủy của một prototype đã được trao cho client như đối với singleton.
- Một bean definition có thể đã được đăng ký trong khi singleton tương ứng **chưa được tạo**. Đây là điều rất quan trọng khi quan sát startup và điều kiện auto-configuration.

## 3. BeanFactory làm gì?

`BeanFactory` là API nền tảng của IoC container. Những lời gọi thường gặp:

```java
Object beanByName = beanFactory.getBean("reportFormatter");
ReportFormatter beanByType = beanFactory.getBean(ReportFormatter.class);
boolean exists = beanFactory.containsBean("reportFormatter");
```

Đoạn này minh họa cách gọi API và giả định đã có biến `beanFactory` cùng định nghĩa bean phù hợp; nó **không phải chương trình Java độc lập**.

Với `DefaultListableBeanFactory`, Spring có thể đăng ký các bean definition, tìm ứng viên autowiring, kiểm tra scope và quản lý singleton. Trong một ứng dụng thông thường, nhà phát triển không tự khởi tạo `DefaultListableBeanFactory` rồi gọi từng thao tác; `ApplicationContext` và các processor đảm nhiệm quá trình đó.

Khi tạo một bean, container có thể phải:

1. Đọc bean definition và xác định constructor hoặc factory method phù hợp.
2. Giải quyết các dependency, có thể cần tạo thêm bean khác trước.
3. Khởi tạo đối tượng và inject các giá trị/tham chiếu cần thiết.
4. Áp dụng các callback hoặc `BeanPostProcessor` thích hợp; bean cuối cùng có thể được bọc bằng proxy.
5. Giữ lại instance cho các lần tra cứu sau theo scope, đặc biệt với singleton.
6. Thực hiện callback hủy thích hợp khi container đóng, tùy scope và cách quản lý.

Vì thế lời gọi `getBean()` đôi khi chỉ đọc instance singleton đã tồn tại, nhưng cũng có thể **kích hoạt việc tạo bean** và cả chuỗi dependency. Tránh xem `getBean()` như thao tác tra cứu map thuần túy trong mọi tình huống.

### Các giao diện mở rộng cần phân biệt

- `ListableBeanFactory`: có thể liệt kê và tìm bean theo type, thay vì chỉ tra cứu một tên.
- `ConfigurableListableBeanFactory`: cấp thêm API cấu hình/quan sát bean factory, bao gồm tra cứu `BeanDefinition`.
- `BeanDefinitionRegistry`: đăng ký, truy vấn và xóa định nghĩa bean; thường dùng bởi infrastructure tạo cấu hình.
- `BeanFactoryPostProcessor`: can thiệp **metadata/BeanFactory sau khi các định nghĩa đã được nạp**, trước giai đoạn khởi tạo phần lớn bean thông thường.
- `BeanDefinitionRegistryPostProcessor`: một dạng `BeanFactoryPostProcessor` có thêm cơ hội đăng ký bean definitions. `ConfigurationClassPostProcessor` là một ví dụ then chốt trong xử lý Java configuration.
- `BeanPostProcessor`: tác động tới **bean instance** trước/sau initialization; liên quan đến injection, callback và nhiều cơ chế proxy.

Nhớ thứ tự khái niệm: **registry và factory processor làm việc với định nghĩa; bean post-processor làm việc với instance.** Tuy nhiên framework có nhiều pha xử lý và một số infrastructure được khởi tạo sớm, nên sơ đồ tổng quát không thay thế việc đọc lifecycle cụ thể.

## 4. ApplicationContext thêm những gì?

`ApplicationContext` kế thừa những giao diện truy cập bean của Spring, đồng thời cung cấp nhiều năng lực ứng dụng:

| Năng lực | Ví dụ | Vì sao hữu ích |
| --- | --- | --- |
| Tra cứu bean, DI | `getBean(...)`, autowiring | Dùng các đối tượng đã đăng ký |
| Environment và profiles | `getEnvironment()`, `@Profile` | Đọc cấu hình hiệu lực và phân tách môi trường |
| Resource loading | `getResource(...)` | Truy xuất tài nguyên theo quy tắc Spring |
| Application events | `publishEvent(...)` | Thông báo sự kiện trong ứng dụng |
| Message resolution | `getMessage(...)` | Hỗ trợ i18n |
| Parent-child context | `getParent()` | Hệ phân cấp container trong kiến trúc cần thiết |
| Lifecycle | `refresh()`, `close()` trên `ConfigurableApplicationContext` | Điều phối startup/shutdown |

Không phải mọi `ApplicationContext` đều có cùng cơ chế khởi tạo web server. Những triển khai thường gặp:

- `AnnotationConfigApplicationContext` cho môi trường ứng dụng dựa trên annotation, không cần web server.
- `AnnotationConfigServletWebServerApplicationContext` trong ứng dụng Spring Boot web servlet có embedded server.
- `AnnotationConfigReactiveWebServerApplicationContext` trong ứng dụng Spring Boot reactive web có embedded server.

Boot thường suy ra loại ứng dụng từ classpath, đồng thời có thể bị điều chỉnh bằng cấu hình như `spring.main.web-application-type`. **Loại context phụ thuộc cách khởi động và stack sử dụng**, không phải mọi dự án Boot đều tự động tạo web server.

### Khi nào dùng `ApplicationContext` trực tiếp?

Phần lớn mã nghiệp vụ nên nhận dependency qua constructor:

```java
@Service
class ReportService {
    private final ReportFormatter formatter;

    ReportService(ReportFormatter formatter) {
        this.formatter = formatter;
    }
}
```

Đây là đoạn minh họa, cần định nghĩa `ReportFormatter`/import phù hợp trong ứng dụng thật. Constructor injection giúp dependency rõ ràng và thuận tiện kiểm thử. Gọi `applicationContext.getBean(...)` khắp mã nghiệp vụ dễ che giấu dependency, làm ứng dụng khó kiểm thử và dễ rơi vào kiểu *service locator*. API context trực tiếp phù hợp hơn khi viết integration, infrastructure, công cụ quan sát hoặc logic thực sự cần tra cứu động.

## 5. SpringApplication.run và chu trình refresh()

Hãy xem xét cách xử lý của một ứng dụng Boot cơ bản:

```java
@SpringBootApplication
public class ExampleApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExampleApplication.class, args);
    }
}
```

`@SpringBootApplication` hợp nhất `@SpringBootConfiguration`, `@EnableAutoConfiguration` và `@ComponentScan`. Boot tham gia chuẩn bị khởi chạy, còn Spring Framework quản lý lifecycle thực tế của context và bean.

Mốc thời gian khái niệm:

```text
main()
  |
  v
SpringApplication.run(...)
  |
  +--> xác định loại ứng dụng và chuẩn bị Environment
  +--> tạo loại ApplicationContext thích hợp
  +--> đăng ký primary sources và các initializer
  |
  v
ApplicationContext.refresh()  [Spring Framework]
  |
  +--> chuẩn bị BeanFactory
  +--> chạy BeanDefinitionRegistryPostProcessor /
  |    BeanFactoryPostProcessor
  |      |
  |      +--> xử lý @Configuration, @ComponentScan, @Import, @Bean
  |      +--> @EnableAutoConfiguration tìm ứng viên và xét điều kiện
  |      +--> đăng ký những BeanDefinition hợp lệ
  |
  +--> đăng ký các BeanPostProcessor
  +--> chuẩn bị các hạ tầng khác của context
  +--> khởi tạo phần lớn non-lazy singleton
  |      +--> resolve dependency
  |      +--> instantiate / populate / initialize / post-process
  +--> hoàn tất refresh và phát sự kiện lifecycle tương ứng
  |
  v
SpringApplication gọi ApplicationRunner / CommandLineRunner
  |
  v
Ứng dụng sẵn sàng phục vụ; context tiếp tục quản lý bean
```

Các nhánh trong `refresh()` trên đây được **rút gọn để hiểu trách nhiệm**. Chúng không cam kết thứ tự tuyệt đối của từng listener, processor, condition, dependency hoặc bean. `ApplicationContext` có loại triển khai khác nhau nên một số giai đoạn hạ tầng có thể thay đổi.

Các mốc cần phân biệt:

1. **Đăng ký định nghĩa**: Spring đã biết *cách* tạo bean, nhưng chưa chắc đã tạo.
2. **Xử lý điều kiện**: Boot và Spring quyết định cấu hình nào đủ điều kiện được đăng ký; ở Spring Boot 3.x, các auto-configuration được đưa vào qua cơ chế import danh sách ứng viên.
3. **Khởi tạo bean**: factory thực thi constructor/`@Bean`, giải quyết dependency, chạy callback và các post-processor.
4. **Hoàn tất khởi động**: runner của Boot được gọi sau khi context refresh thành công; lỗi tạo bean bắt buộc có thể khiến `SpringApplication.run` thất bại.

Với mặc định thông thường, phần lớn singleton không lazy được tạo trong lúc `refresh()`; tuy nhiên `@Lazy`, prototype, một số factory hoặc xử lý đặc biệt có thể trì hoãn việc tạo instance đến sau.

## 6. @Configuration, @Bean và @Component đi vào registry ra sao?

Hãy phân biệt hai đường đi phổ biến.

### Quét component

```java
@Component
class ExchangeRateService {
    // ...
}
```

Khi package này nằm trong phạm vi `@ComponentScan`, Spring có thể đăng ký bean definition cho class `ExchangeRateService`. Container sau đó chọn constructor, giải quyết dependency và tạo instance khi cần. Các stereotype như `@Service`, `@Repository` và `@Controller` đều liên quan cơ chế component scan này.

### Phương thức @Bean

```java
@Configuration
class PaymentConfiguration {
    @Bean
    PaymentGateway paymentGateway() {
        return new PaymentGateway();
    }
}
```

Sau khi xử lý `@Configuration`, Spring đăng ký bean definition cho `paymentGateway`, trong đó metadata trỏ tới factory method. Khi cần bean, Spring gọi phương thức tương ứng. Các đoạn code ở đây là minh họa, giả định `PaymentGateway` đã được định nghĩa.

Hai đường đi đưa ra **bean definitions với nguồn khác nhau**, nhưng đều được Spring IoC container quản lý. Nếu cùng một bean name xuất hiện từ nhiều nguồn, còn có các quy tắc xung đột/overriding cần xem xét; không nên giả định bean cuối cùng luôn được chọn theo “file xuất hiện sau”.

### Tại sao @Configuration đặc biệt?

Một class `@Configuration` đầy đủ với mặc định `proxyBeanMethods=true` có thể được Spring tăng cường để lời gọi giữa các phương thức `@Bean` đi qua container, nhằm tuân thủ semantics của bean. Với `proxyBeanMethods=false`, cách gọi Java trực tiếp giữa các `@Bean` không được intercept theo cơ chế này. **Constructor injection hoặc khai báo tham số vào phương thức `@Bean`** là cách rõ ràng để nhận đúng bean do container quản lý, không lệ thuộc vào việc tự gọi phương thức cấu hình.

Những cơ chế này là bước xử lý cấu hình trước/đồng thời đăng ký bean definition; không phải mỗi annotation `@Bean` tự động tạo instance ngay tại thời điểm JVM tải class.

## 7. Auto-configuration bổ sung bean definitions ở đâu?

Trong Spring Boot 3.x, danh sách những lớp auto-configuration của một thư viện được khai báo trong:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

`@EnableAutoConfiguration` kích hoạt lựa chọn những ứng viên này. Những lớp `@AutoConfiguration` là cấu hình Spring được áp dụng **có điều kiện**, ví dụ:

```java
@AutoConfiguration
@ConditionalOnClass(ExternalClient.class)
class ExternalClientAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(ExternalClient.class)
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
```

Đây là **đoạn minh họa**: `ExternalClient` là kiểu giả định và code không phải ứng dụng chạy độc lập. Ý nghĩa là:

- Nếu `ExternalClient` không có trên classpath, điều kiện class không khớp và phần cấu hình này không được áp dụng.
- Nếu class có mặt nhưng ứng dụng đã cung cấp bean `ExternalClient` phù hợp, cấu hình với `@ConditionalOnMissingBean` nhường chỗ cho bean ứng dụng.
- Nếu những điều kiện cần đều thỏa, Spring đăng ký định nghĩa bean `externalClient`; việc tạo instance sau đó thuộc về BeanFactory.

Một **điều kiện không khớp thường khiến bean definition không xuất hiện**, khác với trường hợp bean definition có sẵn nhưng bean chưa được tạo do `@Lazy`. Hai hiện tượng có thể đều khiến ta “chưa thấy instance”, nhưng cách gỡ lỗi hoàn toàn khác.

Các điều kiện phổ biến khác gồm `@ConditionalOnProperty`, `@ConditionalOnBean`, `@ConditionalOnWebApplication` và điều kiện tài nguyên. Điều kiện bean phụ thuộc trạng thái bean definitions tại thời điểm đánh giá; đó là lý do auto-configuration được tổ chức để xử lý sau cấu hình ứng dụng và có các quy tắc sắp thứ tự. Không nên dùng `@ConditionalOnMissingBean` tùy tiện trong cấu hình nghiệp vụ rồi cho rằng kết quả luôn giống auto-configuration chính thức.

### Auto-configuration có đồng nghĩa bean ghi đè bean không?

Không. Một bean mặc định được cấu hình để **back off** sẽ không đăng ký nếu đã tồn tại bean ứng dụng phù hợp. **Bean definition overriding** lại là cơ chế một định nghĩa trùng tên thay định nghĩa khác; Spring Boot thường không cho phép bean definition overriding theo mặc định. Ngoài ra, `@Primary` giúp ưu tiên một ứng viên khi autowiring theo type nhưng **không xóa** các bean definition còn lại. Cần phân biệt ba tình huống trước khi sửa lỗi:

| Cơ chế | Việc xảy ra | Dấu hiệu |
| --- | --- | --- |
| Condition back off | Bean mặc định không được đăng ký | Không tìm thấy definition mặc định, đã có bean ứng dụng |
| Bean definition overriding | Một definition thay definition cùng tên | Có thể bị báo xung đột tên nếu không được phép |
| `@Primary`/`@Qualifier` | Chọn giữa nhiều bean cùng type | Nhiều bean vẫn tồn tại, một ứng viên được chọn cho dependency |

## 8. Ví dụ runnable: đã có BeanDefinition nhưng chưa có bean instance

Ví dụ dùng **Java 17+**, **Spring Boot 3.3.13**, Maven và `spring-boot-starter` để chạy một ứng dụng không có web server. Mục đích là quan sát ba việc trên cùng một context:

1. Sau `SpringApplication.run()`, bean definition do `@Bean` tạo đã có sẵn.
2. `@Lazy` làm singleton chưa được khởi tạo ngay.
3. `getBean()` yêu cầu BeanFactory tạo instance; lần tra cứu sau trả về cùng một singleton.

Cấu trúc:

```text
context-fundamentals/
├── pom.xml
└── src/main/java/demo/
    └── ContextFundamentalsApplication.java
```

**`pom.xml`:**

```xml
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
    <groupId>example</groupId>
    <artifactId>context-fundamentals</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
```

**`src/main/java/demo/ContextFundamentalsApplication.java`:**

```java
package demo;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;

@SpringBootApplication
public class ContextFundamentalsApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(ContextFundamentalsApplication.class, args)) {

            String name = "trainingGreetingService";
            BeanDefinition definition =
                context.getBeanFactory().getBeanDefinition(name);

            System.out.println("DEFINITION_FOUND: "
                + context.containsBeanDefinition(name));
            System.out.println("FACTORY_METHOD: "
                + definition.getFactoryMethodName());
            System.out.println("CREATED_BEFORE_GET: "
                + context.getBeanFactory().containsSingleton(name));

            GreetingService first = context.getBean(GreetingService.class);
            GreetingService second = context.getBean(name, GreetingService.class);

            System.out.println("CREATED_AFTER_GET: "
                + context.getBeanFactory().containsSingleton(name));
            System.out.println("SAME_SINGLETON: " + (first == second));
            System.out.println("MESSAGE: " + first.greet("Boot"));
        }
    }

    @Bean
    @Lazy
    GreetingService trainingGreetingService() {
        System.out.println("CREATE_GREETING");
        return new GreetingService("Xin chào");
    }

    public static final class GreetingService {
        private final String prefix;

        public GreetingService(String prefix) {
            this.prefix = prefix;
        }

        public String greet(String name) {
            return prefix + ", " + name + "!";
        }
    }
}
```

Từ thư mục chứa `pom.xml`, với JDK 17+ và Maven:

```bash
mvn -q -DskipTests package
java -jar target/context-fundamentals-0.0.1-SNAPSHOT.jar --spring.main.web-application-type=none
```

Bỏ qua banner và log khởi động, các dòng do ví dụ tự in theo thứ tự:

```text
DEFINITION_FOUND: true
FACTORY_METHOD: trainingGreetingService
CREATED_BEFORE_GET: false
CREATE_GREETING
CREATED_AFTER_GET: true
SAME_SINGLETON: true
MESSAGE: Xin chào, Boot!
```

Giải thích từng mốc:

- `DEFINITION_FOUND: true`: `@Bean` đã được parser của Spring xử lý và đăng ký thành định nghĩa tên `trainingGreetingService`.
- `FACTORY_METHOD: trainingGreetingService`: bean definition chứa tên phương thức tạo đối tượng. Đối tượng chưa nhất thiết xuất hiện.
- `CREATED_BEFORE_GET: false`: vì `@Lazy`, bean singleton của ví dụ chưa nằm trong singleton cache sau `refresh()` (và không có consumer nào yêu cầu nó sớm).
- `getBean(GreetingService.class)` là yêu cầu thực sự khiến container gọi phương thức `@Bean`, từ đó có `CREATE_GREETING`.
- `CREATED_AFTER_GET: true`: instance đã được đăng ký trong cache singleton của factory.
- `SAME_SINGLETON: true`: tra cứu theo type và theo name đều trả về cùng instance cho definition singleton này.
- `MESSAGE`: hành vi của đối tượng sau khi được Spring tạo.

`containsBeanDefinition(name)` và `containsSingleton(name)` trả lời **hai câu hỏi khác nhau**: *có bản mô tả bean?* và *có singleton instance đã được đăng ký?* Không suy ra sự tồn tại của instance chỉ từ việc tìm thấy definition.

Lưu ý rằng `@Lazy` trên bean **không bảo đảm tuyệt đối** nó sẽ không được tạo trong mọi ứng dụng: nếu một singleton không lazy khác cần bean đó để khởi tạo, container vẫn phải tạo dependency. Ví dụ trên chủ động không có consumer nào như vậy trước đoạn `getBean()` trong `main`.

## 9. Vòng đời một bean và vai trò của các processor

Khi Spring quyết định khởi tạo một bean thông thường, các bước tổng quan gồm:

```text
BeanDefinition (metadata)
   |
   v
Resolve constructor / factory method và dependency
   |
   v
Instantiate (tạo đối tượng)
   |
   v
Populate properties / dependency injection
   |
   v
Aware callbacks (nếu có)
   |
   v
BeanPostProcessor trước initialization
   |
   v
Initialization callbacks (@PostConstruct,
InitializingBean, custom init method nếu có)
   |
   v
BeanPostProcessor sau initialization
   |  [có thể trả về proxy]
   v
Bean sẵn sàng để sử dụng
   |
   v
Destruction callbacks khi context đóng (nếu áp dụng)
```

Đây là sơ đồ tổng quát: `InstantiationAwareBeanPostProcessor`, `FactoryBean`, AOP và những extension khác có thể tạo ra nhánh xử lý bổ sung. Không phải mọi bean đều chạy tất cả callback.

Ví dụ, một bean `@Transactional` có thể được cung cấp qua proxy sau xử lý liên quan; code ứng dụng nhận một bean theo contract mong muốn nhưng class runtime có thể khác class khai báo. Vì vậy, khi debug, cần tách **bean definition**, **instance gốc** và **instance/proxy thực sự được truy xuất**.

Hai điểm dễ nhầm:

- `BeanFactoryPostProcessor` can thiệp metadata của container **trước giai đoạn khởi tạo singleton thông thường**. `BeanPostProcessor` can thiệp các instance được tạo.
- Không nên gọi `getBean()` tùy tiện trong một factory post-processor: yêu cầu khởi tạo bean quá sớm có thể khiến bean không đi qua đầy đủ mọi `BeanPostProcessor` hoặc làm thay đổi thứ tự mong đợi.

Một bean có `@PreDestroy` hoặc custom destroy method được container quản lý theo vòng đời tương ứng; bean prototype sau khi được trao cho client thường cần được client tự quản lý cleanup. Đóng `ApplicationContext` là thao tác quan trọng trong ứng dụng độc lập hoặc trong ví dụ kiểm thử.

## 10. Các tình huống cần biết trong startup

### 10.1. Có definition nhưng injection vẫn lỗi

Định nghĩa có thể đã được đăng ký nhưng quá trình tạo instance thất bại: thiếu dependency, dependency vòng, lỗi trong constructor/factory method, binding properties không hợp lệ hoặc callback khởi tạo ném exception. Trong những trường hợp đó, `containsBeanDefinition` có thể đúng nhưng `getBean()` hoặc `SpringApplication.run()` vẫn thất bại.

Các lỗi thường xuất hiện:

- `NoSuchBeanDefinitionException`: không có ứng viên phù hợp tại thời điểm cần resolve.
- `NoUniqueBeanDefinitionException`: có nhiều ứng viên, không đủ thông tin chọn.
- `BeanCreationException`: không thể tạo hoặc khởi tạo bean; cần đọc root cause bên dưới.
- `BeanCurrentlyInCreationException`: thường liên quan cycle hoặc yêu cầu bean khi đang tạo.

Các exception thực tế phụ thuộc ngữ cảnh; một lỗi có thể được bọc bên trong `UnsatisfiedDependencyException` hoặc `BeanCreationException`.

### 10.2. Bean mặc định không xuất hiện

Hãy kiểm tra riêng hai câu hỏi:

1. **Auto-configuration có được lựa chọn và điều kiện có khớp không?** Kiểm tra classpath, property, loại web context, exclusion và bean người dùng đã có.
2. **Bean definition được đăng ký rồi nhưng chưa tạo hay tạo lỗi?** Kiểm tra lazy initialization, dependencies và initialization exceptions.

Có thể bật thông tin chẩn đoán bằng:

```bash
java -jar target/context-fundamentals-0.0.1-SNAPSHOT.jar --debug --spring.main.web-application-type=none
```

Boot in Conditions Evaluation Report trong output chẩn đoán. *Positive matches* và *Negative matches* giúp giải thích phần cấu hình tự động. Report nói về điều kiện cấu hình; nó không thay thế việc xem stack trace khi bean creation thất bại.

### 10.3. Hai bean cùng type

Ví dụ ứng dụng đăng ký hai bean `PaymentGateway` khác nhau thì constructor chỉ có tham số `PaymentGateway` có thể bị mơ hồ. Có thể dùng `@Qualifier`, `@Primary` hoặc thiết kế lại API. `@Primary` không xóa một bean; nó ảnh hưởng chọn ứng viên. Khi xét auto-configuration, phải đọc chính xác điều kiện theo **type** hay **name** để biết bean tùy chỉnh có ngăn mặc định được đăng ký hay không.

### 10.4. Hai context độc lập

Hai `ApplicationContext` độc lập có thể cùng chứa bean tên `trainingGreetingService` mà mỗi bên giữ một singleton riêng. `singleton` không có nghĩa JVM-global. Trong context phân cấp parent-child, quy tắc nhìn thấy bean và shadowing có thể khác; cần xác định context nào sở hữu definition và bean thực tế.

### 10.5. Lazy không phải cách chữa mọi vấn đề khởi động

Đặt `@Lazy` hoặc `spring.main.lazy-initialization=true` có thể lùi thời điểm tạo một số bean và rút ngắn giai đoạn startup, nhưng lỗi cấu hình có thể chỉ lộ ra lúc request đầu tiên sử dụng bean. Những bean cần được dùng sớm vẫn có thể bị tạo. Khi tối ưu, nên đo thời gian startup thực tế và cân nhắc yêu cầu fail-fast của dịch vụ.

## 11. Cách quan sát trong ứng dụng thật

Khi điều tra một bean, hãy thu thập dữ kiện theo trình tự:

1. **Xác định context đang chạy:** servlet, reactive hay non-web; có parent context không.
2. **Tìm nguồn definition:** `@Component`, phương thức `@Bean`, auto-configuration import hay đăng ký chương trình.
3. **Đọc điều kiện và exclusion:** đặc biệt với auto-configuration, tra Conditions Evaluation Report.
4. **Kiểm tra thời điểm tạo:** eager singleton, lazy singleton, prototype hay scope riêng.
5. **Xem dependency và post-processing:** dependency bị thiếu, type mơ hồ, vòng phụ thuộc hoặc proxy.
6. **Kiểm tra instance runtime và vòng đời:** bean có được tạo/khởi tạo thành công, context có đang đóng hay không.

Trong code chẩn đoán, `ConfigurableApplicationContext#getBeanFactory()` cung cấp `ConfigurableListableBeanFactory`, từ đó đọc định nghĩa bằng `getBeanDefinition(name)`. Nên hạn chế dùng những API này cho nghiệp vụ thông thường vì chúng làm code phụ thuộc trực tiếp vào infrastructure Spring.

### Những điều cần tránh khi can thiệp startup

- Tự thay đổi bean definitions trong bean constructor/`@PostConstruct` để “bổ sung cấu hình”: thường đã quá muộn đối với những xử lý cần diễn ra trước khởi tạo.
- Gọi `getBean()` trong `BeanFactoryPostProcessor` để thử chạy sớm một nghiệp vụ: có thể gây khởi tạo trước khi chuỗi post-processors hoàn chỉnh.
- Dùng `@Primary` để mong auto-configuration không tạo bean: đó là hai cơ chế riêng.
- Đọc tên class của bean proxy rồi kết luận mất bean definition: proxy là một phần có thể xảy ra của quá trình xử lý instance.
- Giả định mọi singleton đều tạo tại cùng một thời điểm hoặc mọi `@Bean` đều lazy.
- Đoán nguyên nhân `NoSuchBeanDefinitionException` từ tên dependency mà không đọc Conditions Evaluation Report và root cause.

## 12. Tự kiểm tra

**Câu 1.** Sau `refresh()`, `containsBeanDefinition("x")` trả `true` nhưng `containsSingleton("x")` trả `false`. Điều này có mâu thuẫn không?

**Trả lời:** Không. Bean definition có thể tồn tại trước khi bean instance được tạo, ví dụ bean lazy. Ngoài ra cần hiểu scope và bean name đang kiểm tra.

**Câu 2.** Khi muốn bổ sung bean definition trước khi các singleton bình thường được tạo, loại extension nào phù hợp hơn: `BeanDefinitionRegistryPostProcessor` hay `BeanPostProcessor`?

**Trả lời:** `BeanDefinitionRegistryPostProcessor`, vì nó được thiết kế cho pha đăng ký định nghĩa. `BeanPostProcessor` xử lý instance.

**Câu 3.** Tại sao Spring Boot có thể cung cấp cấu hình tự động nhưng vẫn dùng DI của Spring Framework?

**Trả lời:** Boot chọn và đăng ký bean definitions có điều kiện; Spring container sử dụng các định nghĩa hợp lệ để tạo bean, resolve dependency và quản lý vòng đời.

**Câu 4.** `@Primary`, bean overriding và `@ConditionalOnMissingBean` có giống nhau không?

**Trả lời:** Không. `@Primary` ưu tiên ứng viên khi inject; overriding thay thế bean definition trùng tên (nếu được phép); `@ConditionalOnMissingBean` quyết định **không đăng ký** bean mặc định khi đã có bean phù hợp.

**Câu 5.** Nếu `SpringApplication.run()` ném lỗi tạo bean, có nên chỉ tìm lỗi ở `main()`?

**Trả lời:** Không. Cần đọc chuỗi exception nguyên nhân, xem bean được khởi tạo khi nào, dependency nào thiếu, cấu hình nào điều kiện không khớp và callback nào thất bại.

## Tài liệu tham khảo

- Spring Framework — The IoC Container: https://docs.spring.io/spring-framework/reference/core/beans.html
- Spring Framework — Bean Overview and BeanDefinition: https://docs.spring.io/spring-framework/reference/core/beans/definition.html
- Spring Framework — Customizing the Nature of a Bean: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
