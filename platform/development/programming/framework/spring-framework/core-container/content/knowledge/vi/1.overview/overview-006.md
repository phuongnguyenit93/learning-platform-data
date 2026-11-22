# `BeanFactory`, `ApplicationContext` và các dịch vụ bổ sung của Spring Core Container

## 1. Bức tranh tổng thể: ai tạo và nối các bean?

Trong ứng dụng Spring, **IoC container** nắm vai trò khởi tạo, cấu hình, kết nối và quản lý những đối tượng được đăng ký là **Spring bean**. Mã nghiệp vụ thường khai báo các phụ thuộc qua constructor thay vì tự tìm hoặc tự tạo toàn bộ cộng tác viên.

Hai API quan trọng trong Spring Core Container:

- **`BeanFactory`** (`org.springframework.beans.factory.BeanFactory`): giao diện nền tảng để truy xuất bean theo tên hoặc kiểu và để mô tả khả năng quản lý dependency của container.
- **`ApplicationContext`** (`org.springframework.context.ApplicationContext`): giao diện cấp cao **mở rộng năng lực `BeanFactory`**, bổ sung cách làm việc thống nhất với môi trường, tài nguyên, thông điệp quốc tế hóa, sự kiện ứng dụng và những cơ chế khởi tạo/tích hợp khác.

Một `ApplicationContext` cũng có thể được dùng như một `BeanFactory` để gọi `getBean(...)`, nhưng **không phải mọi đối tượng `BeanFactory` đều là `ApplicationContext`**.

~~~text
                  BeanFactory
        tạo/tra cứu bean, dependency, scope
                       ^
                       | API mở rộng
                ApplicationContext
             /         |          \
       Environment  MessageSource  ResourceLoader
          profiles    i18n          Resource
                       |
              ApplicationEventPublisher
                    sự kiện
~~~

Sơ đồ chỉ nêu các chức năng chính, không phải toàn bộ quan hệ kế thừa interface trong thư viện Spring. Ở tầng thực thi, `ApplicationContext` vẫn dùng những thành phần bean factory để thực hiện khởi tạo và nối bean.

## 2. `BeanFactory`: hợp đồng quản lý và truy xuất bean cốt lõi

`BeanFactory` định nghĩa các thao tác quen thuộc:

~~~java
Object bean = factory.getBean("orderService");
OrderService service = factory.getBean(OrderService.class);
boolean known = factory.containsBean("orderService");
boolean singleton = factory.isSingleton("orderService");
~~~

Đây là **mã minh họa**, với biến `factory` và lớp `OrderService` được giả định đã tồn tại. Gọi `getBean` có thể kích hoạt tạo bean tùy container, scope và trạng thái khởi tạo hiện tại.

Những nhiệm vụ liên quan tới bean factory bao gồm:

1. Tra cứu bean bằng **tên, kiểu** hoặc kết hợp tên/kiểu.
2. Áp dụng cấu hình tạo bean: constructor, factory method, dependency và scope.
3. Quản lý một số khía cạnh vòng đời của bean, như khởi tạo và hủy, khi container/bean factory được cấu hình phù hợp.
4. Báo lỗi khi thiếu bean, có nhiều bean cùng phù hợp hoặc cấu hình dependency không thể giải quyết.

**Phân biệt giao diện và lớp thực thi:** `BeanFactory` là interface, không phải constructor dùng như `new BeanFactory()`. `DefaultListableBeanFactory` là một implementation thường dùng khi cần thao tác cấp thấp, ví dụ đăng ký `BeanDefinition` bằng tay.

Một `BeanFactory` đơn giản thường tạo bean **khi lần đầu được yêu cầu**. Tuy nhiên, điều này **không có nghĩa mọi bean factory luôn lazy**, và cũng không phải mỗi lời gọi `getBean` lại tạo một bean mới: điều đó còn tùy scope.

Ví dụ:

~~~java
DefaultListableBeanFactory factory = new DefaultListableBeanFactory();
factory.registerBeanDefinition(
        "greeting", new RootBeanDefinition(Greeting.class));
Greeting greeting = factory.getBean(Greeting.class);
~~~

Đoạn này cần các import từ `org.springframework.beans.factory.support` và lớp `Greeting` có constructor phù hợp. Ví dụ chạy đầy đủ sẽ xuất hiện ở mục 6.

## 3. `ApplicationContext`: bean factory trong ngữ cảnh ứng dụng

Một `ApplicationContext` cung cấp khả năng truy xuất bean như `BeanFactory` **và** tập hợp các dịch vụ thường cần trong ứng dụng. Một số cách triển khai phổ biến:

| Loại context | Công dụng điển hình |
| --- | --- |
| `AnnotationConfigApplicationContext` | Khởi tạo từ lớp `@Configuration` hoặc các lớp component được đăng ký; phù hợp ví dụ Java thuần không cần web |
| `ClassPathXmlApplicationContext` | Đọc cấu hình XML trên classpath khi bảo trì hệ thống dùng XML |
| `FileSystemXmlApplicationContext` | Đọc cấu hình XML từ đường dẫn kiểu file system theo quy tắc của Spring |
| `GenericApplicationContext` | Context có thể đăng ký bean definition hoặc customizer bằng chương trình |
| `WebApplicationContext` | Biến thể dành cho môi trường ứng dụng web khi có Spring Web |

Không cần Spring Boot mới tạo được context. **Spring Framework `spring-context` đã cung cấp `ApplicationContext`**; Spring Boot giúp tự động cấu hình và khởi chạy ứng dụng ở tầng cao hơn.

Ví dụ Java configuration:

~~~java
@Configuration
class AppConfig {
    @Bean
    Notifier notifier() {
        return new ConsoleNotifier();
    }

    @Bean
    OrderService orderService(Notifier notifier) {
        return new OrderService(notifier);
    }
}
~~~

Đây là mã minh họa; `Notifier`, `ConsoleNotifier` và `OrderService` cần được định nghĩa. Spring thấy tham số `Notifier notifier` của `@Bean` và giải quyết bean phụ thuộc tương ứng. Cách tạo bean cụ thể nằm ở lớp cấu hình, không lẫn vào mã nghiệp vụ.

### Vòng đời khởi động: khác biệt cần nhớ

Thông thường, khi gọi `refresh()`, `ApplicationContext` xử lý cấu hình, đăng ký/cài đặt các bộ mở rộng liên quan và **khởi tạo trước các singleton không đánh dấu lazy**. Sau `refresh()`, các bean singleton thông thường đã sẵn sàng để sử dụng.

Với `DefaultListableBeanFactory` dựng thủ công, việc gọi `getBean()` có thể mới tạo instance lần đầu; các processor/phần mở rộng phải được đăng ký hoặc kích hoạt theo cách phù hợp. Vì vậy **không nên kết luận “`BeanFactory` thiếu lifecycle, còn `ApplicationContext` mới có lifecycle”**. Hai loại đều có cơ chế quản lý bean; khác biệt nổi bật là **mức độ tự động thiết lập và tích hợp các dịch vụ ứng dụng**.

- `@Lazy` và scope như `prototype` có thể thay đổi thời điểm tạo bean.
- `singleton` trong Spring là **một instance theo bean definition trong từng container**, không phải một singleton toàn JVM.
- Khởi tạo sớm singleton không đồng nghĩa ứng dụng không bao giờ tạo object về sau.
- Một bean tạo thủ công bằng `new` ngoài container không tự trở thành Spring bean.

## 4. Các dịch vụ bổ sung quan trọng

| Khả năng | `BeanFactory` cơ bản | `ApplicationContext` |
| --- | --- | --- |
| Tra cứu bean, DI, scope | Có | Có |
| Bean definition, khởi tạo và vòng đời | Có qua implementation/cấu hình phù hợp | Có, đồng thời tích hợp và tự phát hiện nhiều extension point khi `refresh` |
| `Environment` / property / profile | Không phải dịch vụ chuẩn của interface `BeanFactory` | Có qua `getEnvironment()` |
| `MessageSource` / i18n | Không phải khả năng chuẩn trực tiếp của interface | Context hỗ trợ qua API `getMessage(...)` |
| `ResourceLoader` | Không phải API trực tiếp trên `BeanFactory` | `getResource(...)` |
| Publish application events | Không phải API trực tiếp trên `BeanFactory` | `publishEvent(...)` |
| Quản lý context lifecycle | Tùy implementation và cách dùng | `refresh`, `close` hoặc `start`/`stop` tùy interface/implementation |
| Phân cấp context | Một số cơ chế bean factory hỗ trợ parent | Các context có thể có parent; phạm vi tên/visibility phụ thuộc cấu hình |

Bảng so sánh **hợp đồng API và cách dùng thông thường**, không tuyên bố rằng không thể tự tích hợp các khả năng tương tự vào một `BeanFactory` cấp thấp.

### 4.1. `Environment`, property và profile

`Environment` đọc các nguồn property như system properties, environment variables hoặc `PropertySource` do ứng dụng thêm vào. Context có thể dùng profile để chọn những bean phù hợp môi trường:

~~~java
String appName = context.getEnvironment()
                        .getProperty("app.title", "Untitled");
~~~

Đây là đoạn minh họa với `context` đã được tạo. Nếu muốn cấu hình profile, thường cần **đặt profile trước khi gọi `refresh()`**. Ví dụ:

~~~java
context.getEnvironment().setActiveProfiles("dev");
context.register(AppConfig.class);
context.refresh();
~~~

Một bean đánh dấu `@Profile("dev")` chỉ được đăng ký khi điều kiện profile phù hợp. **Profile không bảo đảm tính bảo mật**, không phải cơ chế để tự động che bí mật cấu hình, và tên profile cũng không tự tạo bean nếu thiếu định nghĩa tương ứng.

Với nhiều nguồn cấu hình, cần hiểu thứ tự ưu tiên property sources. Những giá trị trùng key có thể bị nguồn ưu tiên cao hơn ghi đè khi truy vấn.

### 4.2. `MessageSource`: thông điệp theo locale

`ApplicationContext` triển khai `MessageSource`, cung cấp:

~~~java
String text = context.getMessage(
        "order.saved", new Object[]{"A01"}, Locale.US);
~~~

Dùng để tra cứu văn bản bằng key và tham số theo locale. Nếu không có mã thông điệp phù hợp mà không cung cấp default, API có thể ném `NoSuchMessageException`.

Khi cấu hình bằng bean, tên đặc biệt **`messageSource`** được context dùng để xác định nguồn thông điệp riêng của ứng dụng. Có thể dùng `ResourceBundleMessageSource` cho các tệp properties ở nhiều locale, hoặc `StaticMessageSource` cho ví dụ/test không cần file ngoài.

`MessageSource` giải quyết chuyện **thông điệp hiển thị**; nó không thay thế `Environment` cho các property cấu hình tùy ý.

### 4.3. `ResourceLoader`: tài nguyên thống nhất

~~~java
Resource resource = context.getResource(
        "classpath:demo/SpringServicesDemo.class");
boolean exists = resource.exists();
~~~

Đây là đoạn minh họa; `Resource` nằm trong `org.springframework.core.io`. Spring hỗ trợ các tiền tố như `classpath:` và `file:` theo cơ chế resource loader và đường dẫn được chỉ định. `Resource` không đồng nghĩa mọi nguồn có thể quy về `java.io.File`:

- Resource trong JAR có thể đọc qua stream nhưng không nhất thiết có một đường dẫn file hệ điều hành thông thường.
- Nếu cần đọc nội dung, dùng `getInputStream()` và **đóng stream** sau sử dụng.
- `getResource` là cơ chế tìm một tài nguyên; việc tìm nhiều tài nguyên theo pattern là khả năng nâng cao của `ResourcePatternResolver`, không nên đánh đồng với mọi URL.

### 4.4. `ApplicationEventPublisher`: sự kiện trong ứng dụng

Context có thể công bố sự kiện:

~~~java
context.publishEvent(new OrderSavedEvent(source, "A01"));
~~~

Một `ApplicationListener<OrderSavedEvent>` hoặc một method `@EventListener` đã đăng ký có thể nhận thông báo. **Mặc định, multicaster chuẩn gọi listener đồng bộ** trong cùng luồng phát sự kiện. Có thể tùy chỉnh executor/cơ chế listener làm thay đổi cách chuyển sự kiện; đừng mặc định event Spring là message queue bền vững, giao dịch phân tán hoặc đảm bảo retry.

Sự kiện giúp các thành phần bớt cần biết trực tiếp về nhau ở bước thông báo, nhưng listener vẫn chạy trong tiến trình/container theo cách cấu hình. Không nên dùng event để che những dependency bắt buộc hoặc biến luồng điều khiển nghiệp vụ thành chuỗi side effect khó theo dõi.

## 5. Khi nào cần `BeanFactory`, khi nào dùng `ApplicationContext`?

Với phần lớn ứng dụng Spring, **`ApplicationContext` là lựa chọn thông thường** vì có DI, vòng đời và những dịch vụ bổ sung được tích hợp. Làm việc trực tiếp với `BeanFactory`/`DefaultListableBeanFactory` hữu ích khi:

- Nghiên cứu cơ chế bean definition, bean creation và extension point của Spring Core Container.
- Viết một thành phần framework/infrastructure có nhu cầu điều khiển bean factory cấp thấp.
- Muốn dựng ví dụ nhỏ để thấy khác biệt giữa API cốt lõi và context.

Không nên chọn `BeanFactory` chỉ vì nghe có vẻ “nhẹ hơn” nếu ứng dụng thực sự cần `Environment`, messages, event listeners và lifecycle tự động: tự lắp những phần này có thể tạo thêm công việc. Cũng không nên dựng cả context cho những object nhỏ không cần quản lý bởi Spring.

Trong mã nghiệp vụ, hãy ưu tiên **constructor injection** vào lớp dịch vụ thay vì đưa `ApplicationContext` vào mọi lớp rồi gọi `getBean(...)` tùy tiện. Cách truy vấn bean mọi nơi giống **Service Locator**, khiến dependency ẩn và unit test khó hơn.

## 6. Ví dụ chạy được bằng Spring Framework 6 và Java 17

Ví dụ này chạy bằng **Spring Framework 6.2.0** và Maven, **không dùng Spring Boot**, không cần server, database hoặc Internet khi chương trình chạy. Lần đầu biên dịch Maven cần tải dependency nếu chưa có cache. Các thông điệp và nguồn cấu hình được thiết lập trực tiếp trong code để đầu ra dễ kiểm chứng.

### 6.1. Cấu trúc project và `pom.xml`

~~~text
spring-services/
├── pom.xml
└── src/main/java/demo/SpringServicesDemo.java
~~~

Tạo file `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>spring-services</artifactId>
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
                    <mainClass>demo.SpringServicesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. File `SpringServicesDemo.java`

~~~java
package demo;

import java.util.Locale;
import java.util.Map;

import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationListener;
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.StaticMessageSource;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.io.Resource;

public class SpringServicesDemo {

    // Đối tượng đơn giản để thử BeanFactory cấp thấp.
    public static final class Greeting {
        public String text() {
            return "hello";
        }
    }

    // Event kiểu ApplicationEvent; có thể dùng event object thông thường khác.
    public static final class OrderSavedEvent extends ApplicationEvent {
        private final String orderId;

        public OrderSavedEvent(Object source, String orderId) {
            super(source);
            this.orderId = orderId;
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public static final class OrderListener
            implements ApplicationListener<OrderSavedEvent> {
        @Override
        public void onApplicationEvent(OrderSavedEvent event) {
            System.out.println("EVENT " + event.getOrderId());
        }
    }

    public static final class OrderService {
        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void place(String orderId) {
            System.out.println("ORDER " + orderId);
            publisher.publishEvent(new OrderSavedEvent(this, orderId));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        // Tên bean messageSource có ý nghĩa đặc biệt với ApplicationContext.
        @Bean("messageSource")
        public MessageSource messageSource() {
            StaticMessageSource messages = new StaticMessageSource();
            messages.addMessage("order.saved", Locale.US,
                    "Saved order {0}");
            return messages;
        }

        @Bean
        public OrderListener orderListener() {
            return new OrderListener();
        }

        // Spring cung cấp ApplicationEventPublisher khi tạo bean.
        @Bean
        public OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }

    public static void main(String[] args) {
        // BeanFactory trực tiếp: đăng ký bean definition thủ công.
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();
        factory.registerBeanDefinition(
                "greeting", new RootBeanDefinition(Greeting.class));
        System.out.println(
                "BeanFactory: " + factory.getBean(Greeting.class).text());

        // ApplicationContext: cấu hình và dịch vụ ở cấp ứng dụng.
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("demo",
                            Map.of("app.title", "OrdersDemo")));

            context.register(AppConfig.class);
            context.refresh();

            System.out.println("Environment: "
                    + context.getEnvironment().getProperty("app.title"));
            System.out.println("MessageSource: "
                    + context.getMessage("order.saved",
                            new Object[]{"A01"}, Locale.US));

            Resource resource = context.getResource(
                    "classpath:demo/SpringServicesDemo.class");
            System.out.println("Resource exists: " + resource.exists());

            context.getBean(OrderService.class).place("A01");
        }
    }
}
~~~

Từ thư mục chứa `pom.xml`, dùng **JDK 17+** và Maven:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

Hai dòng đầu kiểm tra Maven/JDK, dòng sau biên dịch rồi chạy. **Những dòng stdout do ứng dụng in, theo thứ tự:**

~~~text
BeanFactory: hello
Environment: OrdersDemo
MessageSource: Saved order A01
Resource exists: true
ORDER A01
EVENT A01
~~~

Maven, logging hoặc môi trường xây dựng có thể in thông báo riêng; đây là **stdout do mã ví dụ chủ động in**, không cam kết bản ghi terminal luôn chỉ gồm sáu dòng.

### 6.3. Vì sao có kết quả này?

1. `DefaultListableBeanFactory` đăng ký `Greeting` bằng `RootBeanDefinition`; lời gọi `getBean(Greeting.class)` yêu cầu instance và in `hello`.
2. `AnnotationConfigApplicationContext` tạo context nhưng chưa refresh. Ta thêm `MapPropertySource` vào `Environment`, sau đó đăng ký `AppConfig` và gọi `refresh()`.
3. `getEnvironment().getProperty("app.title")` tra key vừa thêm, trả `OrdersDemo`.
4. Bean đặc biệt `messageSource` cung cấp template `Saved order {0}` cho `Locale.US`; `getMessage` chèn `A01` vào vị trí số 0.
5. `classpath:demo/SpringServicesDemo.class` tồn tại vì Maven đã biên dịch file vào classpath; `Resource.exists()` trả `true`.
6. Spring tạo `OrderService` với đối tượng `ApplicationEventPublisher` do context cung cấp. `place("A01")` in `ORDER A01` và công bố sự kiện.
7. `OrderListener` là bean implement `ApplicationListener<OrderSavedEvent>`, nên nhận event và in `EVENT A01` theo cơ chế multicast đồng bộ mặc định.
8. `try-with-resources` đóng context sau khối. Nếu bean có callback hủy tài nguyên được cấu hình đúng, container sẽ xử lý theo vòng đời tương ứng.

Ví dụ cố ý dùng **hai container riêng**: `factory` để minh họa `BeanFactory` cấp thấp; `context` để minh họa tích hợp dịch vụ. Bean `greeting` chỉ tồn tại trong `factory`; nó **không tự xuất hiện** trong `context`.

## 7. Đọc thiết kế và tránh hiểu nhầm

### 7.1. `getBean` không thay constructor injection trong code nghiệp vụ

~~~java
// Ít nên làm tràn lan trong domain/service:
OrderService service = context.getBean(OrderService.class);
~~~

Gọi trên ở **biên khởi động/demo** là hợp lý để lấy entry point. Nhưng nếu mọi service đều giữ một `ApplicationContext` và tự gọi `getBean` liên tục, đồ thị phụ thuộc bị che khuất.

Mẫu dùng ổn định hơn là khai báo:

~~~java
public OrderService(Notifier notifier, OrderRepository repository) {
    this.notifier = notifier;
    this.repository = repository;
}
~~~

Đây là cú pháp minh họa; `Notifier` và `OrderRepository` cần được định nghĩa. Bean factory/context có thể cung cấp hai dependency thông qua constructor mà code nghiệp vụ không cần biết context.

### 7.2. Metadata và instance dưới góc nhìn API

`BeanFactory` lưu các bean definitions và cung cấp bean object qua `getBean(...)`; `ApplicationContext` dùng chính nền tảng ấy, đồng thời chuẩn bị các dịch vụ như environment, message, resource và event. Bean definition có thể tồn tại trước bean instance, còn `@Component`/`@Bean` chỉ có hiệu lực khi cấu hình liên quan được đăng ký hoặc quét vào context. Bài về *bean definition và instance* đã giải thích sâu trường hợp scope, alias và proxy.

### 7.3. Khác biệt về thời điểm tạo

| Tình huống | Hành vi cần hiểu |
| --- | --- |
| `DefaultListableBeanFactory` mới đăng ký bean definition, chưa `getBean` | Thông thường instance chưa cần tạo |
| `ApplicationContext.refresh()` với singleton không lazy | Thường pre-instantiate singleton khi refresh |
| `@Lazy` | Có thể hoãn tạo tùy cách bean được yêu cầu và phụ thuộc |
| `prototype` | Context/bean factory thường tạo instance mới theo mỗi lần yêu cầu, không tự quản lý đầy đủ bước hủy như singleton |
| Hai `ApplicationContext` riêng cùng một cấu hình | Không nhất thiết chia sẻ singleton instance giữa các context |

Nếu bean có side effect khi khởi tạo, việc khởi động context có thể kích hoạt side effect trước cả khi code gọi `getBean()`. Vì thế tránh để constructor thực hiện I/O khó kiểm soát hoặc công việc kéo dài không cần thiết.

## 8. Lỗi phổ biến khi dùng `ApplicationContext`

| Triệu chứng / hiểu nhầm | Nguyên nhân cần kiểm tra và hướng xử lý |
| --- | --- |
| `NoSuchBeanDefinitionException` | Bean chưa được đăng ký, package chưa scan, profile không khớp, hoặc chọn sai tên/kiểu |
| `NoUniqueBeanDefinitionException` | Nhiều bean ứng viên cùng kiểu; phân biệt bằng `@Qualifier`, `@Primary` hoặc cấu hình hợp lệ |
| `UnsatisfiedDependencyException` | Dependency yêu cầu không thể giải quyết; xem nguyên nhân gốc trong stack trace |
| `BeanCreationException` | Constructor, factory method, injection hoặc initialization gặp lỗi |
| `NoSuchMessageException` | Thiếu key/locale trong `MessageSource`; khai báo message hoặc default phù hợp |
| Resource không tồn tại | Sai tiền tố `classpath:`/`file:` hoặc sai classpath/đường dẫn |
| Event không được nhận | Listener chưa thành bean, không đúng loại event, context chưa sẵn sàng hoặc event được publish vào context khác |
| Tưởng `publishEvent` luôn async | Multicaster chuẩn mặc định đồng bộ; async cần cấu hình có chủ đích |
| `@Profile` không hoạt động | Profile chưa active trước `refresh`, hoặc cấu hình component scan không bao gồm class |
| Bean singleton có lỗi đồng thời | Singleton chỉ nói về số lượng instance theo container; thread safety phải tự thiết kế |
| Đóng context quá sớm | Không dùng bean/nguồn do context quản lý sau khi vòng đời kết thúc |
| Tự tạo đối tượng bằng `new` rồi chờ annotation Spring có hiệu lực | Object ngoài container không tự được xử lý như bean managed |

Cần đặc biệt phân biệt **lỗi cấu hình bean** với lỗi API nghiệp vụ. Ví dụ thiếu bean `OrderService` gây lỗi startup/lookup; còn một đối số `orderId` trống là lỗi validation trong mã nghiệp vụ, không phải nhiệm vụ `ApplicationContext` tự đoán.

## 9. Tự kiểm tra kiến thức

**Câu 1. `ApplicationContext` có thay thế hoàn toàn `BeanFactory` không?**

Không theo nghĩa phủ nhận `BeanFactory`. `ApplicationContext` **kế thừa các khả năng tra cứu bean** và thêm những dịch vụ cấp ứng dụng. Nó sử dụng cơ chế bean factory để thực thi việc quản lý bean.

**Câu 2. Vì sao người dùng Spring thường làm việc với `ApplicationContext`?**

Vì ngoài DI/lookup, context tích hợp cấu hình môi trường, tra thông điệp i18n, truy cập resource, sự kiện ứng dụng và vòng đời khởi động/hủy bean.

**Câu 3. `BeanFactory` chỉ hỗ trợ bean lazy, không hỗ trợ lifecycle — đúng không?**

Không. Đây là cách đơn giản hóa dễ gây sai. Việc lazy hay eager phụ thuộc implementation/cấu hình và quá trình khởi tạo; quản lý lifecycle tồn tại ở tầng bean factory, còn `ApplicationContext` tích hợp và tự động hóa nhiều bước.

**Câu 4. Muốn đổi thông điệp "Saved order A01" sang ngôn ngữ khác thì dùng gì?**

Định nghĩa thông điệp tương ứng locale trong một `MessageSource` thích hợp và gọi `getMessage` với locale mong muốn. Với ứng dụng lớn, file `messages_*.properties` qua `ResourceBundleMessageSource` thường dễ duy trì hơn định nghĩa từng message trong code.

**Câu 5. Vì sao `Resource` không nên luôn ép sang `File`?**

Vì resource có thể nằm trong JAR hoặc nguồn khác không có path file vật lý trực tiếp; đọc stream qua `Resource.getInputStream()` khi phù hợp.

**Câu 6. Một `ApplicationListener` có phải tự động là hệ thống hàng đợi durable không?**

Không. Event nội bộ Spring context mặc định được giao đồng bộ. Nếu cần hàng đợi bền vững, retry, bảo đảm nhận thông điệp giữa process, cần giải pháp tương ứng bên ngoài phần event nội bộ này.

**Câu 7. Có nên inject `ApplicationContext` vào mọi service để tự gọi `getBean` không?**

Thông thường không. Constructor injection làm dependency rõ ràng, dễ unit test; `ApplicationContext` nên nằm ở biên khởi động hoặc trong những thành phần infrastructure thực sự cần dùng dịch vụ của context.

## 10. Checklist áp dụng trong dự án

1. Xác định các lớp thật sự cần là Spring-managed bean.
2. Chọn `@Configuration` + `@Bean` hoặc component scanning một cách rõ ràng.
3. Với dependency bắt buộc, ưu tiên constructor injection.
4. Đăng ký các bean theo scope đúng vòng đời; không tự suy ra singleton là thread-safe.
5. Nếu cấu hình thay đổi theo môi trường, dùng `Environment`/property/profile phù hợp thay vì hard-code ở nhiều nơi.
6. Nếu cần đa ngôn ngữ, dùng `MessageSource` thay vì nhét câu chữ trực tiếp vào mọi service.
7. Khi tải tài nguyên, chọn prefix/path rõ ràng và xử lý stream đúng vòng đời.
8. Nếu publish event, xác định listener, cơ chế đồng bộ/bất đồng bộ và chính sách lỗi.
9. Dùng context ở biên tích hợp; tránh Service Locator tràn lan trong nghiệp vụ.
10. Kiểm tra lỗi thiếu bean, nhiều bean, vòng phụ thuộc và thời điểm lifecycle của bean khi chạy test.

**Kết luận:** `BeanFactory` cung cấp hợp đồng nền tảng để quản lý và truy xuất bean. `ApplicationContext` xây dựng trên nền tảng ấy và tích hợp những dịch vụ ứng dụng như `Environment`, `MessageSource`, `ResourceLoader` và application events. Hiểu rõ ranh giới này giúp chọn API phù hợp, cấu hình Spring có chủ đích và giữ cho lớp nghiệp vụ phụ thuộc vào những cộng tác viên được khai báo rõ ràng, thay vì phụ thuộc ẩn vào container.