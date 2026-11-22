# Khi nào bean cần nhận thông tin từ container? — Callback Aware trong Spring

## 1. Vấn đề cần giải quyết

Một bean Spring thông thường chỉ cần cộng tác viên nghiệp vụ như repository, HTTP client hoặc service khác. Spring IoC Container truyền những dependency đó qua constructor, setter hoặc field injection. Bean không cần biết container tồn tại, được khởi tạo ở đâu hay có tên gì.

Đôi khi, một **bean hạ tầng** lại cần nhận thông tin mà chỉ container nắm giữ: tên bean thực tế, BeanFactory đã tạo nó, ApplicationContext đang sở hữu nó, bộ nạp Resource, Environment, bộ phát application event hoặc MessageSource. Spring hỗ trợ nhóm giao diện có hậu tố **`Aware`** để truyền những thông tin này vào bean qua callback.

Câu hỏi “Khi nào bean cần nhận thông tin từ container?” nên được trả lời dựa trên **trách nhiệm của chính bean**:

- **Nên dùng Aware** khi bean triển khai framework extension, adapter hạ tầng, công cụ chẩn đoán hoặc cần metadata/capability liên quan trực tiếp đến Spring container.
- **Ưu tiên constructor injection** khi bean chỉ cần một dependency nghiệp vụ hoặc một interface hạ tầng cụ thể mà Spring có thể inject trực tiếp.
- **Ưu tiên `ObjectProvider<T>`** khi cần lấy một bean theo nhu cầu, ví dụ prototype mới cho mỗi công việc, mà không cần giữ toàn bộ `BeanFactory`.
- **Tránh dùng ApplicationContext như service locator** trong mọi business method; cách này che giấu dependency, tăng coupling với Spring và làm unit test khó hơn.

Sau bài này, người học có thể hiểu đúng từng callback Aware, khi nào nó chạy trong bean lifecycle, chọn một interface tối thiểu và chạy được ví dụ Java 17 trên Spring Framework 6.1.x.

## 2. Bản chất của giao diện `Aware`

`org.springframework.beans.factory.Aware` là một **marker interface**. Nó không tự định nghĩa phương thức callback. Các interface con định nghĩa method riêng; Spring hoặc một `BeanPostProcessor` thích hợp phải nhận diện và gọi những method ấy.

Ba ví dụ phổ biến:

~~~java
// Chữ ký API rút gọn để minh họa, không cần tự định nghĩa lại.
public interface BeanNameAware extends Aware {
    void setBeanName(String name);
}

public interface BeanFactoryAware extends Aware {
    void setBeanFactory(BeanFactory beanFactory) throws BeansException;
}

public interface ApplicationContextAware extends Aware {
    void setApplicationContext(ApplicationContext context)
        throws BeansException;
}
~~~

Package thật:

- `BeanNameAware` và `BeanFactoryAware` nằm tại `org.springframework.beans.factory`.
- `ApplicationContextAware` nằm tại `org.springframework.context`.
- `Aware` nằm tại `org.springframework.beans.factory`.

**Không phải cứ đặt tên interface kết thúc bằng Aware là Spring tự gọi callback.** Với interface mới do ứng dụng tự định nghĩa, cần có processor hoặc infrastructure rõ ràng để xử lý.

### Hai cách thể hiện dependency

Cách đúng cho phần lớn service:

~~~java
@Service
public class CheckoutService {
    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public void checkout() {
        gateway.charge();
    }
}
~~~

Đây là đoạn minh họa cần định nghĩa `PaymentGateway` và import Spring. Dependency `PaymentGateway` hiện rõ trong constructor.

Cách dễ bị lạm dụng:

~~~java
@Service
public class CheckoutService implements ApplicationContextAware {
    private ApplicationContext context;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.context = context;
    }

    public void checkout() {
        context.getBean(PaymentGateway.class).charge();
    }
}
~~~

Đây là phiên bản **thay thế**, không ghép cùng tên class trong một dự án. Cả hai đều có thể hoạt động khi được cấu hình đúng, nhưng phiên bản thứ hai che giấu dependency chính trong method, làm class phụ thuộc vào container và khiến kiểm thử không còn đơn giản bằng cách truyền một fake gateway.

Với một service nghiệp vụ, constructor injection thường dễ hiểu và an toàn hơn. Callback Aware được sinh ra cho trường hợp thực sự cần **thông tin của container**.

## 3. Bảng quyết định nhanh theo thông tin cần nhận

| Interface | Container cung cấp gì? | Nơi dùng phù hợp |
| --- | --- | --- |
| `BeanNameAware` | Tên thực tế của bean trong bean factory | Registry, metric tag, log chẩn đoán theo tên bean |
| `BeanFactoryAware` | `BeanFactory` sở hữu bean | Adapter hạ tầng cần tra cứu bean hoặc metadata theo nhu cầu |
| `ApplicationContextAware` | `ApplicationContext` chứa bean | Framework integration cần nhiều khả năng của context, phân tích hierarchy |
| `EnvironmentAware` | `Environment` | Hạ tầng phân tích profile, property sources hoặc cấu hình runtime |
| `ResourceLoaderAware` | `ResourceLoader` | Adapter đọc resource từ classpath/file/URL |
| `ApplicationEventPublisherAware` | `ApplicationEventPublisher` | Hạ tầng phát event ứng dụng |
| `MessageSourceAware` | `MessageSource` | Thành phần đa ngôn ngữ, giải quyết message theo locale |
| `BeanClassLoaderAware` | `ClassLoader` dùng bởi bean factory | Plugin/class scanning, bytecode/tooling |
| `EmbeddedValueResolverAware` | `StringValueResolver` | Framework xử lý placeholders và embedded value |
| `ServletContextAware` | `ServletContext` của web application | Tích hợp Servlet container |
| `ServletConfigAware` | `ServletConfig` trong web environment thích hợp | Extension gắn servlet |
| `LoadTimeWeaverAware` | `LoadTimeWeaver` khi được cấu hình | Tích hợp load-time weaving, hạ tầng đặc biệt |

Một số interface khác như `ApplicationStartupAware` và `ImportAware` chỉ hữu ích trong tình huống framework/instrumentation chuyên biệt. Không cần triển khai mọi interface chỉ vì Spring hỗ trợ.

Cần phân biệt **bean có thể nhận thông tin** với **bean nên nhận thông tin**. Một lớp chỉ cần phát event thường chỉ cần `ApplicationEventPublisher`; giữ cả `ApplicationContext` là thừa quyền.

## 4. Callback Aware chạy ở thời điểm nào?

Một bean **phải được tạo trước khi** Spring có thể gọi Aware setter. Trong đường khởi tạo thông thường của `ApplicationContext`:

```text
Bean definition → constructor / @Bean factory method
               → dependency injection / property population
               → BeanNameAware / BeanClassLoaderAware / BeanFactoryAware
               → BeanPostProcessor trước initialization:
                   các Aware cấp ApplicationContext; @PostConstruct
               → InitializingBean.afterPropertiesSet()
               → custom init method
               → BeanPostProcessor sau initialization (có thể proxy)
               → bean đã hoàn tất initialization
```

Ba callback liên quan `BeanFactory` được xử lý trực tiếp; `ApplicationContextAware`, `ResourceLoaderAware` và các interface cấp context được `ApplicationContextAwareProcessor` xử lý trước initialization. Thứ tự giữa **những BeanPostProcessor khác nhau** có thể phụ thuộc cấu hình/ordering. Bài 185 chứng minh từng mốc bằng log và giải thích thứ tự nội bộ của processor.

**Lưu ý về readiness:** nhận `ApplicationContext` khi container **đang refresh** chưa chứng minh mọi singleton hay listener đã sẵn sàng. Trong callback, chỉ nên lưu reference/xác thực nhẹ; không kích hoạt hàng loạt `getBean()` để chạy công việc dài. Một constructor chưa thể đọc field được gán bởi Aware setter; nếu collaborator cần ngay lúc tạo bean, dùng constructor injection.

## 5. `BeanNameAware`: biết tên mà container gán

`BeanNameAware.setBeanName(String)` nhận **bean name thực tế** mà Spring dùng cho definition đang tạo:

```java
class NamedAdapter implements BeanNameAware {
    private String beanName;

    @Override public void setBeanName(String name) {
        this.beanName = name;
    }

    String label() { return "adapter=" + beanName; }
}
```

Khi khai báo `@Bean("paymentAdapter")` trả một `NamedAdapter`, callback nhận `paymentAdapter` và `label()` cho chuỗi `adapter=paymentAdapter`. Đoạn này cần import `BeanNameAware` và đăng ký bean qua configuration. Tên này thích hợp cho diagnostic/metric ở component hạ tầng, **không phải business ID hoặc unique instance ID**: nhiều prototype instances có thể dùng cùng bean name; tên có thể đổi khi refactor. Bài 182 giải thích thêm aliases và tên được sinh tự động.

## 6. `BeanFactoryAware`: quyền lookup cấp factory

`BeanFactoryAware.setBeanFactory(BeanFactory)` cấp factory đang quản lý bean. Adapter hạ tầng có thể lookup một plugin theo tên đã được kiểm tra:

```java
class PluginBridge implements BeanFactoryAware {
    private BeanFactory beanFactory;

    @Override public void setBeanFactory(BeanFactory supplied) {
        beanFactory = supplied;
    }

    Plugin getPlugin(String beanName) {
        return beanFactory.getBean(beanName, Plugin.class);
    }
}
```

Đây là snippet cần imports và type `Plugin` do ứng dụng định nghĩa. Tên bean từ input bên ngoài phải được map/allowlist trước khi lookup. Factory lookup trả singleton hoặc tạo prototype theo **scope thực tế**, không mặc định object mới. Nếu biết dependency type mà chỉ cần lấy muộn, inject `ObjectProvider<Plugin>` qua constructor và gọi `getObject()` khi cần: hợp đồng hẹp hơn, giảm phụ thuộc vào toàn bộ factory. Không gọi lookup một loạt trong setter Aware khi bean đang khởi tạo.

## 7. `ApplicationContextAware`: khi cần nhiều khả năng của context

`ApplicationContextAware.setApplicationContext(ApplicationContext)` cấp context chứa bean. API này bao gồm bean lookup, resource loading, events, messages và metadata về parent/child context:

```java
class ContextInspector implements ApplicationContextAware {
    private ApplicationContext context;

    @Override public void setApplicationContext(ApplicationContext supplied) {
        context = supplied;
    }

    boolean hasBean(String name) { return context.containsBean(name); }
}
```

Đây là snippet cần imports của Spring. Dùng khi chính trách nhiệm bean là **framework integration, diagnostics hoặc quản lý hạ tầng theo context**. Với service chỉ cần event, resource hoặc message, hãy inject interface `ApplicationEventPublisher`, `ResourceLoader` hoặc `MessageSource` tương ứng. Một bean thuộc parent context không tự biến thành bean child khi child lookup nó; tránh static `ApplicationContextHolder` vì có thể giữ reference cũ qua nhiều context hoặc test.

## 8. `EnvironmentAware`: thông tin cấu hình runtime

`EnvironmentAware.setEnvironment(Environment)` cấp abstraction dùng để đọc property sources, active/default profiles và property precedence:

```java
class RegionResolver implements EnvironmentAware {
    private Environment environment;

    @Override public void setEnvironment(Environment env) {
        environment = env;
    }

    String region() {
        return environment.getProperty("app.region", "default");
    }
}
```

Snippet cần imports `org.springframework.context.EnvironmentAware` và `org.springframework.core.env.Environment`. Nếu chỉ cần một vài giá trị business, inject cấu hình đã bind/validate qua constructor; tránh log secrets từ `Environment`. Bài 183 giải thích rõ profiles, property conversion và trường hợp đổi cấu hình sau refresh.

## 9. `ResourceLoaderAware`: sử dụng cơ chế resource của Spring

`ResourceLoaderAware.setResourceLoader(ResourceLoader)` giúp adapter resolve resource location động, chẳng hạn `classpath:templates/info.txt` hoặc `file:/opt/app/data.txt`.

```java
Resource resource = loader.getResource("classpath:templates/info.txt");
try (var input = resource.getInputStream()) {
    String content = new String(input.readAllBytes(),
            java.nio.charset.StandardCharsets.UTF_8);
}
```

Đây là fragment trong method có field `ResourceLoader loader` và khai báo/handle `IOException`. `Resource.getFile()` không phù hợp với mọi resource trong JAR; ưu tiên stream. Nếu chỉ đọc một tài nguyên cố định, có thể inject trực tiếp `Resource`. Bài 183 trình bày resource patterns với `ResourcePatternResolver`, trường hợp IO lỗi và i18n.

## 10. Các interface Aware chuyên biệt khác

Ngoài tên/factory/context, Spring có các hợp đồng **đủ hẹp cho một năng lực**:

| Interface | Callback/capability | Giới hạn quan trọng |
| --- | --- | --- |
| `ApplicationEventPublisherAware` | Nhận `ApplicationEventPublisher` để `publishEvent` | Không tự tạo listener hoặc biến event thành durable queue; xem bài 184 |
| `MessageSourceAware` | Nhận `MessageSource` để tra key theo locale | Phải có message codes/bundle/fallback phù hợp; không phải Kafka/JMS |
| `BeanClassLoaderAware` | Class loader được BeanFactory sử dụng | Dành cho plugin, class loading hoặc instrumentation |
| `EmbeddedValueResolverAware` | Resolver cho placeholder/expression | Thuộc infrastructure xử lý embedded values |
| `ServletContextAware` / `ServletConfigAware` | Thông tin Servlet container | Cần web context/processor thích hợp, không có trong CLI context thuần |
| `LoadTimeWeaverAware` | Load-time weaver nếu đã cấu hình | Không kích hoạt weaving chỉ nhờ interface |
| `ImportAware` | Metadata từ `@Import` | Thuộc infrastructure xử lý configuration |

Ví dụ phát event chỉ cần publisher:

```java
class JobEvents implements ApplicationEventPublisherAware {
    private ApplicationEventPublisher publisher;

    @Override public void setApplicationEventPublisher(
            ApplicationEventPublisher supplied) {
        publisher = supplied;
    }

    void finished(String jobId) {
        publisher.publishEvent(new JobFinished(jobId));
    }

    record JobFinished(String id) {}
}
```

Đây là class minh họa cần imports; bean phải do Spring quản lý để nhận setter callback. Listener và synchronous/async dispatch là cơ chế khác; nếu chỉ cần publisher cho nghiệp vụ, constructor injection là lựa chọn thường gọn hơn. Với i18n, `MessageSource.getMessage` giải quyết text theo `Locale`; nó không gửi thông điệp qua mạng. Không tự định nghĩa interface chỉ có tên kết thúc `Aware` rồi trông đợi Spring nhận diện mà thiếu processor.

## 11. Ví dụ hoàn chỉnh Java 17 + Spring 6.1: BeanNameAware, BeanFactoryAware, EnvironmentAware và ApplicationContextAware

Ứng dụng này không cần Spring Boot, HTTP server hoặc database. Nó chứng minh Aware callback chạy trước `InitializingBean.afterPropertiesSet()`, đồng thời so sánh constructor DI với lookup từ factory.

### 11.1. Cấu trúc dự án

~~~text
aware-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── aware/
                        └── AwareDemo.java
~~~

### 11.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>aware-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>com.example.aware.AwareDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 11.3. `src/main/java/com/example/aware/AwareDemo.java`

~~~java
package com.example.aware;

import java.util.Map;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.BeanFactoryAware;
import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.context.EnvironmentAware;
import org.springframework.context.ResourceLoaderAware;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.io.ResourceLoader;

public class AwareDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.getEnvironment().getPropertySources().addFirst(
                new MapPropertySource(
                    "demo-properties", Map.of("demo.region", "VN")));

            context.register(Config.class);
            context.refresh();

            Inspector bean = context.getBean(Inspector.class);

            System.out.println("beanName=" + bean.beanName());
            System.out.println("greeting=" + bean.greeting());
            System.out.println(
                "factoryLookupSame=" + bean.factorySeesSameGreeting());
            System.out.println("sameContext=" + bean.hasContext(context));
            System.out.println("region=" + bean.region());
            System.out.println(
                "classResourceExists=" + bean.classResourceExists());
            System.out.println("initialized=" + bean.initialized());
        }
    }

    public interface Greeting {
        String sayHello();
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        Greeting greeting() {
            return () -> "Hello";
        }

        @Bean(name = "inspector")
        Inspector inspector(Greeting greeting) {
            return new Inspector(greeting);
        }
    }

    public static class Inspector
            implements BeanNameAware, BeanFactoryAware,
                       EnvironmentAware, ResourceLoaderAware,
                       ApplicationContextAware, InitializingBean {

        private final Greeting greeting;
        private String beanName;
        private BeanFactory beanFactory;
        private ApplicationContext context;
        private Environment environment;
        private ResourceLoader resourceLoader;
        private boolean initialized;

        public Inspector(Greeting greeting) {
            this.greeting = greeting;
        }

        @Override
        public void setBeanName(String name) {
            beanName = name;
        }

        @Override
        public void setBeanFactory(BeanFactory factory)
                throws BeansException {
            beanFactory = factory;
        }

        @Override
        public void setEnvironment(Environment suppliedEnvironment) {
            environment = suppliedEnvironment;
        }

        @Override
        public void setResourceLoader(ResourceLoader suppliedLoader) {
            resourceLoader = suppliedLoader;
        }

        @Override
        public void setApplicationContext(ApplicationContext suppliedContext)
                throws BeansException {
            context = suppliedContext;
        }

        @Override
        public void afterPropertiesSet() {
            if (beanName == null || beanFactory == null ||
                environment == null || resourceLoader == null ||
                context == null || greeting == null) {
                throw new IllegalStateException("Aware callbacks incomplete");
            }
            initialized = true;
        }

        public String beanName() {
            return beanName;
        }

        public String greeting() {
            return greeting.sayHello();
        }

        public boolean factorySeesSameGreeting() {
            return beanFactory.getBean(Greeting.class) == greeting;
        }

        public boolean hasContext(ApplicationContext expected) {
            return context == expected;
        }

        public String region() {
            return environment.getProperty("demo.region", "missing");
        }

        public boolean classResourceExists() {
            return resourceLoader.getResource(
                "classpath:com/example/aware/AwareDemo.class").exists();
        }

        public boolean initialized() {
            return initialized;
        }
    }
}
~~~

### 11.4. Chạy và quan sát output

Yêu cầu JDK 17+ và Maven 3.9.x. Từ thư mục `aware-demo`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng `System.out.println` của chương trình:

~~~text
beanName=inspector
greeting=Hello
factoryLookupSame=true
sameContext=true
region=VN
classResourceExists=true
initialized=true
~~~

Maven hoặc logging framework có thể in thêm thông tin theo cấu hình; các dòng trên là stdout được chủ động tạo ra trong code.

**Tại sao output như vậy?**

1. `@Bean(name = "inspector")` cung cấp bean name, nên `BeanNameAware` nhận `inspector`.
2. `Greeting` được Spring inject qua **tham số factory method và constructor**, nên `greeting=Hello`.
3. `Greeting` là singleton mặc định. `BeanFactory.getBean(Greeting.class)` trả cùng object được inject, nên `factoryLookupSame=true`.
4. `ApplicationContextAware` nhận chính context đã tạo bean, nên `sameContext=true`.
5. `MapPropertySource` thêm `demo.region=VN` trước khi context refresh, nên `EnvironmentAware` đọc được `region=VN`.
6. File class `AwareDemo.class` được Maven compile vào classpath nên `ResourceLoader` xác định được resource, trả `classResourceExists=true`.
7. `afterPropertiesSet()` chạy sau các callback cần thiết và xác nhận field đều được cung cấp, nên `initialized=true`.

Ví dụ cố ý dùng nhiều Aware interface trên cùng một class để học và kiểm chứng. Trong dự án thật, chỉ nên chọn giao diện thật sự cần, tránh tạo một service nắm mọi quyền của Spring container.

## 12. Constructor injection có thể thay thế nhiều Aware callback

Spring có thể inject một số infrastructure dependency trực tiếp khi phù hợp. Ví dụ với constructor:

~~~java
@Component
public class TemplateService {
    private final ResourceLoader loader;
    private final ApplicationEventPublisher publisher;

    public TemplateService(
            ResourceLoader loader,
            ApplicationEventPublisher publisher) {
        this.loader = loader;
        this.publisher = publisher;
    }
}
~~~

Đây là class minh họa với import `Component`, `ResourceLoader` và `ApplicationEventPublisher`. Nếu service cần hai thứ đó, constructor làm rõ dependency và hỗ trợ unit test dễ hơn.

So sánh:

| Mục tiêu | Callback Aware | Constructor injection |
| --- | --- | --- |
| Code Spring callback-style | Tự implements interface, Spring gọi setter | Spring giải quyết dependency qua constructor |
| Dependency thể hiện rõ ngay khi tạo object | Không nhất thiết | Có |
| Class có thể tạo bằng `new` độc lập | Cần tự gọi callback nếu phụ thuộc Aware field | Chỉ cần truyền fake/mock dependency |
| Dùng với framework extension yêu cầu interface Aware | Phù hợp | Tùy integration API |
| Chỉ cần một collaborator cụ thể | Thường quá nhiều ceremony | Thường tốt hơn |

Đối với `ApplicationContextAware`, còn có thể inject trực tiếp `ApplicationContext` vào constructor của Spring bean. Việc hỗ trợ injection không có nghĩa nên đưa container vào mọi class. Hãy thu hẹp dependency trước khi quyết định.

## 13. Những cạm bẫy khi dùng Aware

### 13.1. Dùng field Aware ngay trong constructor

~~~java
public BadAdapter() {
    // beanFactory có thể vẫn null tại đây.
    beanFactory.getBean("helper");
}
~~~

Đây là đoạn constructor minh họa thuộc class có field `beanFactory` được set bởi `BeanFactoryAware`. Constructor chạy trước callback, nên gọi field có thể gây `NullPointerException`. Nếu collaborator cần ngay khi tạo object, inject qua constructor.

### 13.2. Gọi `getBean()` quá sớm trong callback

~~~java
@Override
public void setApplicationContext(ApplicationContext context) {
    this.context = context;
    context.getBeansOfType(Plugin.class); // Có thể tạo bean quá sớm.
}
~~~

Đoạn này minh họa trong class implements `ApplicationContextAware` có interface `Plugin`. Tra cứu hàng loạt bean khi context còn refresh có thể gây early instantiation, circular dependency hoặc làm lệch thứ tự khởi tạo. Nếu cần lookup runtime, trì hoãn đến thời điểm hoạt động hợp lệ hoặc thiết kế registry/injection phù hợp.

### 13.3. Biến ApplicationContext thành global static

~~~java
public static ApplicationContext GLOBAL_CONTEXT;
~~~

Giữ context trong static field tạo implicit global state, dễ sai khi có nhiều application contexts, test context reload và shutdown. Tạo “helper lấy mọi bean bằng tên” có thể che giấu dependency và khiến framework reference sống quá lâu. Hãy dùng DI hoặc abstraction hẹp.

### 13.4. Nhầm bean name với tên class hay định danh instance

`BeanNameAware` nhận tên thực tế của bean definition, có thể do `@Bean(name=...)`, `@Component`, alias hoặc cách đăng ký khác quyết định. Inner beans có thể được tạo tên khác. Không dùng bean name làm unique ID cho transaction hoặc request.

### 13.5. Dùng Aware để truy cập dữ liệu scope không active

Một request-scoped bean implements `ApplicationContextAware` không có nghĩa có HTTP request ở mọi thread. Nếu singleton, scheduler hoặc executor gọi request-scoped proxy ngoài request, nó vẫn có thể gặp `ScopeNotActiveException`. Aware không thay đổi quy tắc scope.

### 13.6. Tưởng một marker interface đủ để được callback

~~~java
public interface MyRegistryAware extends Aware {
    void setRegistry(MyRegistry registry);
}
~~~

Đây là interface tùy biến minh họa. Spring không tự biết cách gọi `setRegistry`. Phải có infrastructure/`BeanPostProcessor` tương ứng hoặc dùng constructor injection thông thường.

## 14. Aware và thứ tự bean lifecycle: cách kiểm tra chính xác

Có thể xác minh thứ tự callback bằng một bean implement `BeanNameAware`, `ApplicationContextAware` và `InitializingBean`:

```java
class CallbackProbe implements BeanNameAware,
        ApplicationContextAware, InitializingBean {
    private final List<String> events = new ArrayList<>();

    @Override public void setBeanName(String name) {
        events.add("BeanNameAware");
    }
    @Override public void setApplicationContext(ApplicationContext context) {
        events.add("ApplicationContextAware");
    }
    @Override public void afterPropertiesSet() {
        events.add("InitializingBean");
    }
    List<String> events() { return List.copyOf(events); }
}
```

Snippet cần imports `List`, `ArrayList` và ba interface Spring; đăng ký nó thành bean trong `AnnotationConfigApplicationContext` rồi so thứ tự ba nhãn. Trong đường mặc định, kết quả là `BeanNameAware → ApplicationContextAware → InitializingBean`. Đây là bằng chứng cho **một bean cụ thể**, không khẳng định thứ tự khởi tạo mọi bean trong application. Bài 185 có demo đầy đủ ghi log cả BeanFactory, sáu interface context-aware, BeanPostProcessor và destruction.

## 15. Aware có hoạt động với prototype, singleton và scoped proxy không?

**Singleton:** callback chạy khi Spring tạo/initialize instance singleton (thường trong refresh đối với non-lazy singleton). Gọi `context.getBean()` lần sau không chạy lại callback trên chính singleton ấy.

**Prototype:** mỗi lần container tạo target prototype mới, quá trình initialization và các Aware callback phù hợp được thực hiện cho instance mới. Hai instances có thể nhận cùng bean name/context reference vì chúng được tạo từ một definition trong cùng context.

**Request/session scope:** callbacks chạy trên target khi scope thực sự tạo target; scoped proxy giúp bean sống lâu tham chiếu target theo request/session. Proxy được inject thành công không có nghĩa target đã tồn tại hoặc scope active trong scheduler thread.

**Object tạo bằng `new`:** không được Spring tự quản lý, nên không nhận Aware callbacks tự động. Nếu class cần hoạt động độc lập container, đưa dependency vào constructor là thiết kế tốt hơn.

**Chú ý destroy callback:** Aware là callback cung cấp thông tin lúc initialization. Nó không biến một prototype thành bean được Spring tự hủy sau khi giao ra; resource cleanup vẫn là trách nhiệm của bên sở hữu.

## 16. Custom Aware interface và BeanPostProcessor

Nếu đang phát triển **framework extension** riêng, bạn có thể tạo contract tùy biến:

~~~java
public interface RegistryAware {
    void setRegistry(PluginRegistry registry);
}
~~~

Đây là ví dụ tự định nghĩa cần interface/class `PluginRegistry`. Muốn Spring gọi callback, có thể viết processor:

~~~java
import org.springframework.beans.factory.config.BeanPostProcessor;

public final class RegistryAwareProcessor implements BeanPostProcessor {
    private final PluginRegistry registry;

    public RegistryAwareProcessor(PluginRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Object postProcessBeforeInitialization(
            Object bean, String beanName) {
        if (bean instanceof RegistryAware aware) {
            aware.setRegistry(registry);
        }
        return bean;
    }
}
~~~

Đây là class Java minh họa; cần khai báo interface `RegistryAware`, kiểu `PluginRegistry`, và đăng ký `RegistryAwareProcessor` làm bean post-processor trong context đủ sớm. Nếu không đăng ký processor, method tùy biến sẽ không được Spring gọi.

Dùng pattern này nếu một thư viện framework cần cung cấp registry cho nhiều component theo callback contract riêng. Với code nghiệp vụ, constructor injection `PluginRegistry` đơn giản hơn rất nhiều.

**Rủi ro của BeanPostProcessor:** processor thường được tạo sớm; eager dependency phức tạp bên trong processor có thể khiến một số bean được tạo trước khi toàn bộ processors/proxies hoàn tất. Tránh biến processor thành một service nghiệp vụ lớn.

## 17. Tình huống sử dụng thực tế

Nhu cầu khác nhau dẫn tới interface khác nhau. Một adapter tạo nhiều bản cấu hình muốn ghi metric theo **bean definition name** có thể dùng `BeanNameAware`; nếu nhãn metric là hợp đồng nghiệp vụ lâu dài, inject nhãn cấu hình riêng. Plugin resolver phải chọn bean theo ID runtime có thể dùng `BeanFactoryAware` trong **adapter đã kiểm soát tên**, trong khi tập plugin ổn định có thể inject `Map<String, Plugin>`.

Một thư viện hỗ trợ template `classpath:`/`file:` có thể dùng `ResourceLoaderAware`; adapter đọc profile/property sources sử dụng `EnvironmentAware`; công cụ diagnostic đa context có thể cần `ApplicationContextAware`. Service nghiệp vụ chỉ cần phát domain event thì constructor-inject `ApplicationEventPublisher` là đủ; nếu event phụ thuộc transaction commit, còn phải chọn listener/transaction strategy phù hợp. Quyết định phụ thuộc trách nhiệm bean, không phải số lượng Aware có sẵn.

## 18. Quy trình quyết định trước khi implements Aware

1. **Bean có cần Spring infrastructure không?** Nếu chỉ cần cộng tác viên nghiệp vụ, dùng constructor DI.
2. **Cần một interface hẹp hay toàn bộ context?** Nếu có interface hẹp như `ResourceLoader`, `Environment`, `ApplicationEventPublisher`, hãy inject nó.
3. **Cần metadata của chính bean?** `BeanNameAware` thích hợp khi bean name thật sự hữu ích.
4. **Có cần lookup runtime không?** Thử `ObjectProvider<T>`, `List<T>` hoặc `Map<String,T>` trước khi inject `BeanFactory`.
5. **Việc nhận thông tin có xảy ra đúng thời điểm?** Aware callback chạy sau constructor, trước initialization; tránh kích hoạt bean khác quá sớm.
6. **Có môi trường hỗ trợ không?** `ServletContextAware` chỉ trong web-aware context phù hợp.
7. **Có nguy cơ reference toàn cục hoặc hierarchy?** Tránh static holders; xác định context thực sự sở hữu bean.
8. **Kiểm thử thế nào?** Dùng unit test cho logic thuần và integration test tạo Spring context để xác minh callbacks.

Nếu không thể diễn đạt rõ **vì sao container metadata là dependency thật**, đó là dấu hiệu nên trở lại constructor injection.

## 19. Lỗi phổ biến và cách khắc phục

| Lỗi | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `ApplicationContext` là null trong constructor | Callback chưa chạy | Dùng constructor injection cho dependency cần ngay |
| Aware callback không chạy | Bean được tạo bằng `new` hoặc không có processor cần thiết | Đăng ký bean đúng context; test thực |
| `BeanNameAware` trả tên không như dự kiến | Bean name có alias, factory method hoặc generated name | Xem bean definition thực tế; tránh dựa vào business ID |
| Service có quá nhiều `getBean()` | Lạm dụng Service Locator | Constructor DI, provider hoặc inject collection |
| Circular dependency khi callback chạy | Gọi lookup quá sớm lúc context refresh | Trì hoãn lookup hoặc thiết kế lại dependency graph |
| Resource không đọc được trong JAR | Coi classpath resource là file vật lý | `getInputStream()`, xử lý IOException |
| Property khác giữa môi trường | Precedence của PropertySources | Kiểm tra profile/source, typed config |
| Bean web không nhận `ServletContext` | Dùng non-web context | Chọn đúng web-aware context |
| Prototype nhận cùng bean name | Name thuộc definition, không thuộc instance | Sinh instance ID riêng |
| Callback custom interface không chạy | Chưa có processor | Đăng ký BeanPostProcessor hoặc dùng DI |
| Bean trong child thấy context khác mong đợi | Parent/child hierarchy và ownership | Xác nhận bean đăng ký tại context nào |
| Scoped bean lỗi ngoài request | Không có active scope | Gọi target đúng request hoặc truyền snapshot dữ liệu |
| Unit test bằng `new` thất bại | Không có Spring callback | Inject dependencies trực tiếp hoặc dựng context integration |
| Bean bị tạo quá sớm | Lookup cả registry trong Aware callback | Lưu reference và dùng đúng thời điểm |

## 20. Tự kiểm tra kiến thức

**Câu 1.** Một `OrderService` cần `OrderRepository`. Vì sao constructor injection thường tốt hơn `ApplicationContextAware`?

**Đáp án:** Dependency được khai báo rõ; Spring resolve khi tạo bean; dễ unit test bằng fake repository và không phụ thuộc runtime lookup toàn container.

**Câu 2.** Bean implements `BeanNameAware` nhận cùng tên trong hai instance prototype, có phải Spring tạo nhầm singleton?

**Đáp án:** Không. Bean name định danh bean definition; scope prototype vẫn có thể tạo nhiều instances khác nhau từ cùng definition.

**Câu 3.** Có thể gọi `beanFactory.getBean(...)` trong constructor khi field `beanFactory` chỉ được set bằng `BeanFactoryAware` không?

**Đáp án:** Không nên: constructor chạy trước callback, field chưa được gán. Nếu cần dependency trong constructor, hãy inject nó trực tiếp.

**Câu 4.** Khi cần phát application event, nên inject gì?

**Đáp án:** `ApplicationEventPublisher` là dependency hẹp phù hợp; `ApplicationEventPublisherAware` cũng có thể dùng với framework callback style, còn `ApplicationContextAware` thường quá rộng.

**Câu 5.** Một bean implements interface tùy biến `MyContextAware` nhưng không có processor, Spring có tự gọi method không?

**Đáp án:** Không. `Aware` là marker; callback tùy biến cần infrastructure rõ ràng hoặc chuyển sang constructor DI.

**Câu 6.** `@RequestScope` bean nhận `ApplicationContext` qua callback có chạy trong `@Scheduled` task được không?

**Đáp án:** Callback không tạo HTTP request. Target request-scoped vẫn đòi hỏi request scope active; background task nên dùng dữ liệu snapshot hoặc một dependency không bị ràng buộc request.

**Câu 7.** Một singleton cần prototype mới mỗi lần xử lý thì nên dùng interface nào?

**Đáp án:** Thường chọn `ObjectProvider<PrototypeType>`, lấy bean tại đầu mỗi nghiệp vụ và quản lý cleanup nếu giữ resource. Không cần nhận toàn bộ `BeanFactory` chỉ để làm việc đó.

## 21. Tài liệu Spring chính thức

- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `ApplicationContextAware`, `BeanNameAware` và các interface Aware khác.
- [`Aware` Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/Aware.html): marker interface và callback contract.
- [`BeanNameAware` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/BeanNameAware.html): bean name và thời điểm callback.
- [`BeanFactoryAware` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/BeanFactoryAware.html): factory ownership và dependency lookup.
- [`ApplicationContextAware` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ApplicationContextAware.html): reference tới context và initialization timing.
- [`ApplicationContext` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ApplicationContext.html): bean lookup, events, resources, messages và context hierarchy.
- [Spring Framework — Annotation-based Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html): lựa chọn constructor/field/method injection.
