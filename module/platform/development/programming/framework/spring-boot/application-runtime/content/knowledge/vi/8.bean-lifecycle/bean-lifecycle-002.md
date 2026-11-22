# Constructor, tiêm phụ thuộc và các callback Aware trong vòng đời bean Spring Boot

## 1. Vị trí trong vòng đời bean

Trong Spring Boot, một **bean** là đối tượng được container quản lý theo một định nghĩa (bean definition). Container không chỉ gọi constructor: nó chọn cách tạo object, phân giải các dependency, tiêm field/setter khi cần, gọi những callback hạ tầng và khởi tạo, rồi mới công bố bean để các thành phần khác sử dụng.

Ba khái niệm cần phân biệt:

- **Constructor** là phương thức khởi tạo một đối tượng Java. Với constructor injection, Spring phải cung cấp các dependency đầu vào để gọi được constructor.
- **Dependency injection (DI)** là cơ chế container cung cấp collaborator cho bean qua constructor, setter, field, hoặc tham số của factory method. Nó giúp bean không phải tự đi tìm và tạo dependency.
- **Aware callbacks** là những interface đặc biệt mà bean có thể triển khai để nhận thông tin/hạ tầng của container, như bean name, `BeanFactory`, `ApplicationContext` hoặc `Environment`. Các callback này xảy ra sau lúc constructor đã hoàn tất.

~~~mermaid
flowchart TD
  A["BeanDefinition đã được đăng ký"] --> B["Chọn constructor, giải quyết dependencies"]
  B --> C["Tạo instance bằng constructor / factory method"]
  C --> D["Tiêm field, setter và các thuộc tính cần thiết"]
  D --> E["BeanNameAware, BeanFactoryAware..."]
  E --> F["BeanPostProcessor trước init, Aware context, @PostConstruct"]
  F --> G["InitializingBean.afterPropertiesSet, custom init-method"]
  G --> H["BeanPostProcessor sau init, có thể tạo AOP proxy"]
  H --> I["Bean sẵn sàng để được inject/sử dụng"]
  I --> J["Khi scope/context kết thúc: destroy callback phù hợp"]
~~~

Đây là thứ tự logic của một **singleton bean thông thường** trong Spring `ApplicationContext`. Với `@Bean` factory method, các scope khác, lazy bean, `FactoryBean`, bean post-processor tùy biến hoặc proxy, một số chi tiết có thể khác. Sơ đồ cũng **không** cam kết thứ tự khởi tạo của tất cả các bean trong toàn ứng dụng.

Một hệ quả quan trọng: nếu bạn lưu `ApplicationContext` trong field qua `ApplicationContextAware.setApplicationContext(...)`, field đó **chưa có** giá trị ở constructor của cùng bean.

## 2. Constructor injection là gì và vì sao được khuyến nghị?

Xét một service cần repository:

~~~java
package com.example.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public String describe(long id) {
        return repository.describe(id);
    }
}
~~~

Đây là đoạn minh họa một phần: dự án phải có interface/class `OrderRepository` phù hợp thì mới compile. Khi tạo `OrderService`, container chọn constructor, tìm bean `OrderRepository`, tạo hoặc lấy bean đó, rồi truyền tham chiếu vào constructor.

Constructor injection mang lại các lợi ích:
1. Dependency bắt buộc thể hiện trong chữ ký: không thể tạo object hợp lệ mà không đưa collaborator vào.
2. Field có thể khai báo `final`, làm tham chiếu ít thay đổi và dễ hiểu hơn.
3. Unit test có thể truyền fake/stub trực tiếp vào constructor, không cần dựng container chỉ để gán field.
4. Thiếu bean hoặc phụ thuộc vòng thường bộc lộ sớm, khi Spring đang tạo bean.
5. Constructor có quá nhiều tham số làm lộ dấu hiệu class có quá nhiều trách nhiệm.

Spring Boot khuyến nghị constructor injection đối với component do Spring quản lý.

### Một constructor và nhiều constructor

Với **một constructor duy nhất**, Spring hiện đại tự dùng constructor đó; không phải thêm `@Autowired`. Với **nhiều constructor**, cần tuân thủ quy tắc chọn constructor của Spring và thường đánh dấu constructor mong muốn bằng `@Autowired`.

~~~java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
class BillingService {
    private final BillingRepository repository;

    @Autowired
    BillingService(BillingRepository repository) {
        this.repository = repository;
    }

    BillingService() {
        this.repository = null;
    }
}
~~~

Snippet trên chỉ minh họa chọn constructor và cần định nghĩa `BillingRepository`; **không nên** dùng thiết kế cho phép tạo một service thiếu dependency bắt buộc. Trong ứng dụng mới, giữ một constructor rõ ràng thường tốt hơn.

### Khi có nhiều bean cùng kiểu

Giả sử `CardGateway` và `BankGateway` đều triển khai `PaymentGateway`. Nếu service chỉ yêu cầu một `PaymentGateway` mà không có quy tắc chọn đủ rõ, container có thể báo `NoUniqueBeanDefinitionException`.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(@Qualifier("cardGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Đoạn này cần interface `PaymentGateway` và bean được đăng ký với tên `cardGateway`; nó không phải chương trình độc lập. `@Qualifier` giúp chọn candidate tại điểm inject, còn `@Primary` có thể đánh dấu một implementation mặc định. Cả hai liên quan đến **chọn dependency**, không phải callback Aware và cũng không phải cho phép hai bean definition trùng tên.

### Cách xử lý dependency có thể thiếu

Nếu collaborator thực sự là tùy chọn, có thể dùng `Optional<T>` hoặc `ObjectProvider<T>`; nếu cần tập hợp strategy, có thể inject `List<T>` hoặc `Map<String,T>`. Ví dụ:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
class AuditFacade {
    private final ObjectProvider<AuditWriter> writer;

    AuditFacade(ObjectProvider<AuditWriter> writer) {
        this.writer = writer;
    }

    void record(String event) {
        AuditWriter available = writer.getIfAvailable();
        if (available != null) {
            available.write(event);
        }
    }
}
~~~

Cần cung cấp `AuditWriter` nếu dùng snippet này. `ObjectProvider` hoãn việc lấy object thật tới thời điểm gọi; nếu nhiều candidate mà không có cách lựa chọn phù hợp, việc lookup vẫn có thể lỗi không duy nhất. Đừng dùng provider để giấu dependency quan trọng.

### Tiêm qua setter và field

| Cơ chế | Thời điểm | Sử dụng phù hợp | Hạn chế |
| --- | --- | --- | --- |
| Constructor injection | Trong giai đoạn tạo instance | Dependency bắt buộc, field `final` | Constructor cycle không có thứ tự giải quyết hợp lệ |
| Setter injection | Sau khi object tồn tại | Dependency tùy chọn/có thể tái cấu hình | Trạng thái object có thể chưa hoàn chỉnh trước setter |
| Field injection qua `@Autowired` | Sau constructor trong giai đoạn population/post-processing | Gặp trong code cũ hoặc test | Khó test bằng Java thuần, ít thể hiện yêu cầu của constructor |
| Tham số `@Bean` factory method | Khi container gọi factory method | Đăng ký đối tượng từ thư viện ngoài | Phải resolve tham số factory tương tự dependency khác |

Setter có `@Autowired` mặc định **không** đồng nghĩa optional: container vẫn cần dependency phù hợp, trừ khi được cấu hình optional theo hợp đồng API.

### Constructor là thời điểm rất sớm

Trong constructor của bean, nên kiểm tra tham số, gán field và tạo invariant đơn giản. Không nên mở luồng xử lý nghiệp vụ dài, gọi remote API, tự tra bean từ context hoặc giả định các field chỉ được inject sau đó đã có giá trị. Nếu gọi method gắn `@Transactional` hay `@Async` của chính bean từ constructor, không thể mặc định kỳ vọng proxy đã sẵn sàng để áp dụng interception.

## 3. Callback Aware: bean nhận thông tin hạ tầng của Spring

Các giao diện `Aware` cho bean biết những thông tin mà chỉ container mới có thể cung cấp chính xác. Chúng không phải mechanism tổng quát để giải quyết mọi dependency nghiệp vụ.

| Interface | Callback | Dữ liệu nhận được | Điểm sử dụng thường gặp |
| --- | --- | --- | --- |
| `BeanNameAware` | `setBeanName(String name)` | Tên bean được đăng ký | Chẩn đoán hoặc bean hạ tầng cần biết định danh |
| `BeanClassLoaderAware` | `setBeanClassLoader(ClassLoader loader)` | ClassLoader dùng cho bean class | Cơ chế load class/resource ở thư viện |
| `BeanFactoryAware` | `setBeanFactory(BeanFactory factory)` | BeanFactory quản lý bean | Infrastructure extension cần làm việc với factory |
| `ApplicationContextAware` | `setApplicationContext(ApplicationContext context)` | Context đang quản lý bean | Framework integration, lookup đặc biệt |
| `EnvironmentAware` | `setEnvironment(Environment env)` | Các property source và profile | Infrastructure component cần trạng thái cấu hình |
| `ResourceLoaderAware` | `setResourceLoader(ResourceLoader loader)` | Bộ tải resource | Thư viện cần giải quyết classpath/URL resources |
| `ApplicationEventPublisherAware` | `setApplicationEventPublisher(ApplicationEventPublisher publisher)` | Bộ phát event | Infrastructure phát event qua context |
| `MessageSourceAware` | `setMessageSource(MessageSource messages)` | Dịch vụ xử lý message/i18n | Message lookup trong extension |
| `ServletContextAware` | `setServletContext(ServletContext context)` | Servlet context hiện hành | Ứng dụng/tích hợp servlet web |

`ServletContextAware` chỉ phù hợp nếu có servlet context; ứng dụng command-line hoặc reactive thuần không nhất thiết có một servlet context. Với Spring Boot 3.x, các API Servlet dùng package `jakarta.servlet.*`, khác nhiều bài viết cũ dùng `javax.servlet.*`.

### BeanNameAware

~~~java
import org.springframework.beans.factory.BeanNameAware;
import org.springframework.stereotype.Component;

@Component("shipmentRouter")
class ShipmentRouter implements BeanNameAware {
    private String beanName;

    @Override
    public void setBeanName(String name) {
        this.beanName = name;
    }

    String getRegisteredName() {
        return beanName;
    }
}
~~~

Sau khi container gọi callback, tên nhận được là `shipmentRouter`. Trong constructor của class này, `beanName` chưa được gán bởi `setBeanName`. Đừng nhầm bean name với simple class name: tên có thể do `@Component("...")`, `@Bean(name=...)` hoặc cấu hình khác đặt.

### BeanFactoryAware và ApplicationContextAware

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.BeanFactoryAware;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.stereotype.Component;

@Component
class InfrastructureAdapter
        implements BeanFactoryAware, ApplicationContextAware {
    private BeanFactory beanFactory;
    private ApplicationContext applicationContext;

    @Override
    public void setBeanFactory(BeanFactory factory)
            throws BeansException {
        this.beanFactory = factory;
    }

    @Override
    public void setApplicationContext(ApplicationContext context)
            throws BeansException {
        this.applicationContext = context;
    }
}
~~~

Bean factory là cơ chế quản lý/tra cứu bean. `ApplicationContext` cung cấp API rộng hơn, ngoài bean lookup còn có event publication, resource/message access và những khả năng ở mức ứng dụng.

Các callback `BeanNameAware`, `BeanClassLoaderAware` và `BeanFactoryAware` thường được bean factory gọi trực tiếp trong khâu khởi tạo. Các context-oriented Aware interface như `ApplicationContextAware` được Spring `ApplicationContext` xử lý thông qua processor. Chúng xảy ra **trước initialization callback**, nhưng không nên suy ra mọi Aware implementation tùy biến có cùng một thứ tự cố định.

## 4. Aware khác với dependency injection như thế nào?

Có thể nhận `Environment` thông qua hai cách khác nhau:

~~~java
// Cách 1: callback Aware, Spring gọi sau khi bean được tạo
class RuntimeAware implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }
}
~~~

~~~java
// Cách 2: constructor injection, có sẵn ngay trong constructor
@Component
class RuntimeConsumer {
    private final Environment environment;

    RuntimeConsumer(Environment environment) {
        this.environment = environment;
    }
}
~~~

Hai snippet cần các import phù hợp từ `org.springframework.context`, `org.springframework.core.env` và `org.springframework.stereotype` nếu được tách thành file riêng.

Nếu service chỉ cần một cấu hình như timezone hoặc retry limit, `@ConfigurationProperties` thường rõ ràng hơn việc giữ cả `Environment`. Nếu service chỉ cần một bean khác, hãy tiêm **chính bean đó**.

| Tiêu chí | Constructor injection | Aware callback |
| --- | --- | --- |
| Khi nào nhận đối tượng | Trong constructor | Sau khi constructor trả về |
| Dependency biểu diễn ở đâu | Chữ ký constructor | Interface callback được implements |
| Mục đích nổi bật | Collaboration giữa các bean | Kết nối với hạ tầng container |
| Unit test thuần Java | Truyền fake/stub trực tiếp | Cần mô phỏng callback nếu logic thực sự dựa vào nó |
| Rủi ro lạm dụng | Constructor phình to | Phụ thuộc sâu vào Spring, dùng service locator |

**Nguyên tắc:** Aware dành cho nhu cầu hạ tầng cụ thể. Việc một business service implement `ApplicationContextAware` chỉ để gọi `getBean(Repository.class)` thường làm code khó hiểu hơn so với inject `Repository` qua constructor.

## 5. Thứ tự cụ thể: BeanPostProcessor và các callback khởi tạo

Với bean thông thường, sau khi tạo instance và populate dependency:

1. Bean factory gọi các Aware callback cơ bản như `setBeanName` và `setBeanFactory`.
2. Các `BeanPostProcessor.postProcessBeforeInitialization` được thực thi. Trong context tiêu chuẩn, `ApplicationContextAwareProcessor` xử lý các callback context phù hợp, còn processor liên quan Jakarta annotations có thể gọi `@PostConstruct`.
3. Nếu bean implement `InitializingBean`, Spring gọi `afterPropertiesSet()`.
4. Nếu bean definition có `initMethod` tùy chỉnh, Spring gọi method đó.
5. Bean post-processors chạy pha sau khởi tạo qua `postProcessAfterInitialization`; các thành phần như AOP có thể trả một proxy.

Khi một bean cấu hình đủ **ba hook khởi tạo khác tên** (annotation, interface và custom init method), thứ tự được tài liệu Spring Framework mô tả là:

~~~text
@PostConstruct
InitializingBean.afterPropertiesSet()
custom init-method
~~~

Với Spring Boot 3.x / Spring Framework 6.x, import annotation là:

~~~java
import jakarta.annotation.PostConstruct;
~~~

Không dùng `javax.annotation.PostConstruct` lấy từ ví dụ Java EE cũ rồi mong nó tự compile trong Boot 3.x.

### @PostConstruct có phải lúc toàn bộ app ready?

Không. `@PostConstruct` thuộc vòng đời **một bean**. Nó có thể được gọi trong `ApplicationContext.refresh()` khi nhiều bean khác còn chưa khởi tạo xong. Đây là thời điểm thích hợp để kiểm tra cấu hình hoặc chuẩn bị cấu trúc nội bộ nhẹ, không phải để chạy batch dài hay phát tín hiệu toàn ứng dụng đã sẵn sàng.

Các runner của Spring Boot (`ApplicationRunner` / `CommandLineRunner`) chạy sau refresh và trước `ApplicationReadyEvent`. Nếu việc cần làm phụ thuộc nhiều bean đã sẵn sàng hoặc cần một process startup, runner hoặc một lifecycle/event hook thích hợp có thể rõ ràng hơn callback Aware.

### Vì sao không nên tự gọi @Transactional ở @PostConstruct?

AOP proxy có thể được tạo trong quá trình `BeanPostProcessor.postProcessAfterInitialization`. Gọi một method có `@Transactional` từ constructor, `@PostConstruct` hoặc qua `this.method()` của chính bean không bảo đảm đi qua proxy. Đây là nguyên nhân thường gặp khiến logic tưởng đã nằm trong transaction nhưng không có interception như mong đợi.

## 6. Ví dụ hoàn chỉnh Java 17+ và Spring Boot 3.5.x

Dự án dưới đây dùng Spring Boot starter cơ bản, Maven và Java 17+. Có **hai bean thành phần** và một `CommandLineRunner`. Chúng ta theo dõi thứ tự callback **trên cùng một bean** mà không cần chạy HTTP server.

Cấu trúc:

~~~text
bean-lifecycle-demo/
├── pom.xml
└── src/main/java/com/example/lifecycle/
    ├── LifecycleDemoApplication.java
    ├── GreetingCatalog.java
    └── LifecycleReportService.java
~~~

**File `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>bean-lifecycle-demo</artifactId>
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
~~~

**File `src/main/java/com/example/lifecycle/LifecycleDemoApplication.java`:**

~~~java
package com.example.lifecycle;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LifecycleDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifecycleDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner showResult(LifecycleReportService service) {
        return args ->
                System.out.println("07.runner=" + service.message());
    }
}
~~~

**File `src/main/java/com/example/lifecycle/GreetingCatalog.java`:**

~~~java
package com.example.lifecycle;

import org.springframework.stereotype.Component;

@Component
public class GreetingCatalog {
    public String greeting() {
        return "Xin chao Spring";
    }
}
~~~

**File `src/main/java/com/example/lifecycle/LifecycleReportService.java`:**

~~~java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.BeanFactoryAware;
import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.stereotype.Service;

@Service("lifecycleReportService")
public class LifecycleReportService
        implements BeanNameAware, BeanFactoryAware,
                   ApplicationContextAware, InitializingBean {

    private final GreetingCatalog catalog;
    private String beanName;
    private ApplicationContext applicationContext;

    public LifecycleReportService(GreetingCatalog catalog) {
        this.catalog = catalog;
        System.out.println("01.constructor=" + catalog.greeting());
    }

    @Override
    public void setBeanName(String name) {
        this.beanName = name;
        System.out.println("02.beanName=" + name);
    }

    @Override
    public void setBeanFactory(BeanFactory factory)
            throws BeansException {
        System.out.println("03.beanFactory="
                + factory.containsBean("greetingCatalog"));
    }

    @Override
    public void setApplicationContext(ApplicationContext context)
            throws BeansException {
        this.applicationContext = context;
        System.out.println("04.applicationContext="
                + context.containsBean("greetingCatalog"));
    }

    @PostConstruct
    void initialize() {
        if (beanName == null || applicationContext == null) {
            throw new IllegalStateException("Aware callbacks missing");
        }
        System.out.println("05.postConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("06.afterPropertiesSet");
    }

    public String message() {
        return catalog.greeting();
    }
}
~~~

Thực hiện ở thư mục chứa `pom.xml`:

~~~bash
mvn -q -DskipTests package
java -jar target/bean-lifecycle-demo-0.0.1-SNAPSHOT.jar
~~~

**Những dòng do chương trình ví dụ chủ động in ra, theo thứ tự tương đối:**

~~~text
01.constructor=Xin chao Spring
02.beanName=lifecycleReportService
03.beanFactory=true
04.applicationContext=true
05.postConstruct
06.afterPropertiesSet
07.runner=Xin chao Spring
~~~

Spring Boot có thể in thêm startup logs tùy phiên bản và cấu hình; khối trên không phải toàn bộ stdout.

Giải thích:
1. Spring tạo `GreetingCatalog` và truyền instance cho constructor `LifecycleReportService(GreetingCatalog)`. Vì service có một constructor, không cần `@Autowired`.
2. `@Service("lifecycleReportService")` đăng ký tên rõ ràng, nên `setBeanName` nhận chuỗi `lifecycleReportService`.
3. `setBeanFactory` nhận factory đang quản lý bean; `containsBean("greetingCatalog")` là `true` vì bean catalog đã được đăng ký để phục vụ constructor dependency.
4. `setApplicationContext` nhận context quản lý bean; trong context thông thường, catalog vẫn có thể được tìm theo tên.
5. `@PostConstruct` kiểm tra hai field callback trước khi báo khởi tạo thành công.
6. `afterPropertiesSet` chạy sau `@PostConstruct`.
7. `CommandLineRunner` được gọi sau refresh thành công để sử dụng service đã hoàn tất khởi tạo.

**Về thứ tự:** các dòng `01`–`06` minh họa một bean cụ thể trong cấu hình trên. Nếu thêm bean post-processor tùy biến, các hook đặc biệt, lazy, scope khác hoặc AOP, thứ tự tương tác phức tạp hơn. Không dựa vào ví dụ này để áp đặt một thứ tự toàn cục cho tất cả bean.

## 7. Refactor ví dụ về thiết kế thường dùng trong production

Mục tiêu của demo là thấy rõ Aware callback. Một service nghiệp vụ đơn giản có thể chỉ cần constructor injection:

~~~java
package com.example.lifecycle;

import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public class WelcomeService {
    private final GreetingCatalog catalog;

    public WelcomeService(GreetingCatalog catalog) {
        this.catalog = Objects.requireNonNull(catalog);
    }

    public String welcome(String name) {
        return catalog.greeting() + ", " + name;
    }
}
~~~

Không cần giữ `ApplicationContext` để gọi `getBean(GreetingCatalog.class)`; Spring đã tiêm `GreetingCatalog` vào constructor. Có thể kiểm thử bằng Java thuần với đoạn nằm trong một method hoặc trong test class:

~~~java
WelcomeService service = new WelcomeService(new GreetingCatalog());
System.out.println(service.welcome("Lan"));
~~~

Output:

~~~text
Xin chao Spring, Lan
~~~

Cách này rõ dependency và dễ dựng fake catalog trong test. Nếu chỉ cần `Environment`, `ApplicationEventPublisher` hay `ResourceLoader`, cũng có thể inject **interface hẹp đó** qua constructor thay vì implement một loạt callback Aware.

## 8. Những biến thể và ngoại lệ cần hiểu

### Bean từ @Bean factory method

Không phải bean nào cũng được tạo từ component scan. Ví dụ:

~~~java
@Configuration
class ClockConfiguration {
    @Bean
    java.time.Clock utcClock() {
        return java.time.Clock.systemUTC();
    }

    @Bean
    TimeService timeService(java.time.Clock clock) {
        return new TimeService(clock);
    }
}
~~~

Ví dụ chỉ có giá trị nếu bổ sung import `@Configuration`/`@Bean` và class `TimeService` tương ứng. Container resolve tham số `clock` trước khi gọi factory method. Object được trả về vẫn có thể được container áp dụng các callback lifecycle thích hợp.

### Bean singleton, prototype và lazy

- **Singleton:** thông thường chỉ có một instance cho một bean definition trên mỗi container. Non-lazy singleton thường được khởi tạo ở giai đoạn refresh; có thể được tạo sớm hơn nếu dependency khác cần.
- **Prototype:** mỗi lần yêu cầu tạo instance có thể chạy constructor, injection và init callback lại. Container không tự quản lý toàn bộ destroy callback cho prototype sau khi đã giao object cho client.
- **Lazy:** trì hoãn tạo instance đến lần bean được cần thực sự; thứ tự log khác ví dụ eager bean không đồng nghĩa bug.

### Constructor thất bại và callback chưa xảy ra

Nếu constructor ném exception, container không thể tiếp tục khởi tạo bean bình thường, nên `setBeanName` hoặc `@PostConstruct` của bean đó chưa được gọi. Nếu callback `@PostConstruct` ném exception, bean có thể không được công bố cho các consumer. Phải đọc stack trace để xác định **phase** thực sự lỗi.

### Proxy và self-invocation

Bean mà consumer nhìn thấy có thể là proxy do AOP tạo, khác object gốc chạy constructor và init callback. Khi một bean gọi `this.someTransactionalMethod()`, lời gọi nội bộ không mặc nhiên đi qua proxy. Đây là khác biệt giữa Java object lifecycle và semantics của advice Spring.

### Vòng phụ thuộc constructor

~~~text
ReportService -> AuditService -> ReportService
~~~

Nếu cả hai cần nhau ngay ở constructor, container không có object hoàn chỉnh để tạo tiếp. Spring thường báo lỗi liên quan `BeanCurrentlyInCreationException`, đôi khi được bọc trong `UnsatisfiedDependencyException`. Để sửa đúng, tách trách nhiệm chung, đảo chiều phụ thuộc hoặc đưa orchestration lên một tầng độc lập. Không kỳ vọng `spring.main.allow-circular-references=true` giải quyết được vòng constructor-to-constructor.

## 9. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Constructor không có bean để inject | Bean chưa đăng ký, ngoài component scan, bị `@Profile`/conditional loại bỏ | Kiểm tra package, configuration và condition, đọc nested cause |
| Nhiều bean cho cùng interface | Không xác định được candidate | Dùng `@Qualifier`/`@Primary` theo thiết kế hoặc inject collection nếu thật sự cần |
| `ApplicationContext` field null trong constructor | Callback `ApplicationContextAware` chưa chạy | Inject dependency vào constructor; dùng context sau callback |
| Bean name không đúng như tưởng tượng | `@Bean(name=...)`/`@Component("...")` hoặc naming strategy | Dựa vào callback `setBeanName` khi thật sự cần tên |
| `@PostConstruct` không được gọi khi dùng `new` | Object không qua Spring container | Để Spring quản lý bean thay vì tự tạo object |
| I/O trong Aware callback làm startup treo | Truy cập bean/hệ thống ngoài quá sớm | Callback chỉ chuẩn bị hạ tầng nhẹ; chọn runner/lifecycle hook cho việc khác |
| `@Transactional` không có hiệu lực trong init | Target/proxy chưa được sử dụng như mong đợi | Gọi qua collaborator/proxy sau khởi tạo, tránh self-invocation |
| `javax.annotation.PostConstruct` không compile | Dùng namespace cũ với Boot 3.x | Đổi sang `jakarta.annotation.PostConstruct` |
| Vòng dependency constructor | A cần B, B cần A để tạo | Refactor đồ thị dependency, tách interface/điều phối |
| Chỉ một số lần xuất hiện log constructor | Bean scope hoặc lazy | Kiểm tra singleton/prototype và thời điểm request |
| Context refresh fail trước khi runner chạy | Exception trong constructor/injection/init | Xem cause đầu tiên trong log, sửa trước khi xét runner |

### Vì sao không nên dùng Aware thay cho thiết kế DI?

Triển khai `ApplicationContextAware` rồi gọi `getBean(...)` khắp business code khiến quan hệ phụ thuộc bị ẩn trong method. Unit test phải giả lập context và dễ bỏ sót vấn đề thiếu bean. Với những collaborator bắt buộc, constructor injection làm yêu cầu rõ hơn. Aware vẫn có chỗ đứng trong infrastructure extension, nhưng dùng đúng mục đích.

### Sự khác nhau giữa init một bean và ready toàn ứng dụng

`@PostConstruct` và `InitializingBean.afterPropertiesSet` chỉ phản ánh khâu khởi tạo **đối tượng ấy**. `ApplicationReadyEvent` thuộc lifecycle startup của **toàn bộ Spring Boot application** sau khi các runner hoàn tất thành công. Một callback Aware cũng không chứng minh database, HTTP listener hoặc các thành phần bên ngoài đều ready.

## 10. Tự kiểm tra kiến thức

**Câu 1:** Một `@Service` có đúng một constructor cần `UserRepository` có buộc ghi `@Autowired` không?  
**Đáp án:** Không, Spring hiện đại nhận diện constructor duy nhất và resolve dependency.

**Câu 2:** `setApplicationContext(...)` chạy trước constructor hay sau?  
**Đáp án:** Sau. Constructor không thể đọc field chỉ được gán ở callback này.

**Câu 3:** Vì sao `@Qualifier("cardGateway")` hữu ích?  
**Đáp án:** Chọn candidate khi có nhiều bean cùng loại; không thay thế cơ chế Aware.

**Câu 4:** Bean được tạo bằng `new` trực tiếp có tự nhận `BeanFactoryAware` không?  
**Đáp án:** Không; chỉ đối tượng đi qua lifecycle quản lý của container mới được gọi callback theo cách đó.

**Câu 5:** Thứ tự giữa `@PostConstruct` và `afterPropertiesSet()`?  
**Đáp án:** Trong cấu hình chuẩn, `@PostConstruct` được gọi trước `InitializingBean.afterPropertiesSet()`.

**Câu 6:** Khi muốn đọc một property trong service, có bắt buộc implement `EnvironmentAware` không?  
**Đáp án:** Không; có thể inject `Environment` hoặc dùng `@ConfigurationProperties` theo nhu cầu.

**Câu 7:** Một constructor cycle A → B → A có biến mất nếu bật cờ cho phép circular references?  
**Đáp án:** Không; vòng constructor-to-constructor không thể tự hoàn tất.

**Câu 8:** Vì sao callback Aware không phù hợp để chạy một job dài khi ứng dụng start?  
**Đáp án:** Nó chạy trong quá trình tạo bean, có thể trước nhiều bean khác, khiến startup khó kiểm soát; dùng lifecycle hook phù hợp hơn.

**Câu 9:** Tại sao ví dụ in `03.beanFactory=true`?  
**Đáp án:** Bean `greetingCatalog` đã được đăng ký và resolve để tạo dependency của service.

**Câu 10:** Một bean có thể được trả dưới dạng AOP proxy thay vì instance gốc không?  
**Đáp án:** Có. BeanPostProcessor sau initialization có thể bọc target bằng proxy.

## 11. Nguồn tài liệu chính thức

- [Spring Boot — Spring Beans and Dependency Injection](https://docs.spring.io/spring-boot/reference/using/spring-beans-and-dependency-injection.html)
- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework — BeanPostProcessor Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)

Các ví dụ sử dụng Spring Boot 3.5.x, Java 17+ và namespace Jakarta. Với dự án Spring Boot hoặc Spring Framework phiên bản khác, đối chiếu dependency thực tế và API cùng phiên bản trước khi áp dụng.