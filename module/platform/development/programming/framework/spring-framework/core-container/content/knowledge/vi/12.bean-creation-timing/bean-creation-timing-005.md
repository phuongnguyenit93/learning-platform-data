# @DependsOn cho phụ thuộc khởi tạo không thể hiện bằng DI trong Spring Core Container

## 1. Vấn đề: hai bean không inject nhau nhưng vẫn cần thứ tự khởi tạo

Trong Spring IoC Container, cách đúng nhất để biểu diễn **một object cần dùng object khác** thường là dependency injection (DI): constructor argument, `@Autowired` hoặc XML `ref`. Nếu `OrderService` cần `OrderRepository`, việc đưa repository vào constructor khiến Spring biết phải chuẩn bị repository trước khi tạo service.

Nhưng có một kiểu phụ thuộc khác: bean B **không nhận bean A như một tham số Java**, tuy nhiên B chỉ hoạt động đúng nếu **A đã được khởi tạo và hoàn tất initialization callback**. Ví dụ:

- Một component đăng ký một handler vào shared infrastructure.
- Một bean thiết lập registry toàn cục, trong khi bean khác chỉ sử dụng static/global registry.
- Một initializer cần chạy trước bean consumer nhưng consumer không cần giữ object initializer.
- Một bean nạp dữ liệu tham chiếu vào một nơi dùng chung trước khi bean khác bắt đầu công việc.

Spring cung cấp **`@DependsOn`** trong Java configuration và **`depends-on`** trong XML để diễn đạt loại **phụ thuộc thứ tự khởi tạo** này.

```java
@Bean
@DependsOn("registryInitializer")
JobDispatcher jobDispatcher() {
    return new JobDispatcher();
}
```

Ý nghĩa: Spring phải **tạo và khởi tạo bean có tên `registryInitializer` trước** khi tạo `jobDispatcher`, mặc dù phương thức `jobDispatcher()` không nhận tham số nào.

**Quan trọng:** `@DependsOn` không phải một dạng injection; nó không chuyển object `registryInitializer` vào `JobDispatcher`. Nó diễn đạt **lifecycle ordering constraint** trong BeanFactory.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Phân biệt **dependency được thể hiện bằng DI** với **dependency chỉ yêu cầu thứ tự khởi tạo**.
2. Hiểu `@DependsOn("beanName")`, `@DependsOn({"beanA","beanB"})` và XML `depends-on="..."`.
3. Giải thích chính xác Spring đảm bảo gì về **initialization** và **destruction** của singleton beans.
4. Phân biệt thứ tự được bảo đảm bởi quan hệ phụ thuộc với thứ tự in code, classpath scan, annotation `@Order` hoặc thứ tự khai báo `@Bean`.
5. Dùng `@DependsOn` trên `@Bean` methods và trên class `@Component` được component-scanned; biết giới hạn của class-level annotation khi đăng ký bằng XML.
6. Kiểm tra tương tác với `@Lazy`, `lazy-init`, prototype và các scoped beans.
7. Phát hiện circular depends-on, missing bean name, bean aliases và các trường hợp side effect không còn hợp lý.
8. Chạy ví dụ Java 17+ / Spring Framework 6.2.19 dùng Java configuration, XML, component scan và lazy bean, đồng thời kiểm chứng cả startup lẫn shutdown order.
9. Biết khi nào **không nên dùng @DependsOn** và nên chọn constructor injection, lifecycle hooks hay sự kiện ứng dụng thay thế.

**Phạm vi:** Chủ đề thuộc **Thời điểm tạo bean** của Spring Framework Core Container. Mục tiêu là đồng bộ **creation/initialization order của bean definitions**, không mô phỏng một task scheduler hay cơ chế dependency orchestration phân tán.

## 2. DI đã biểu diễn thứ tự trong trường hợp bình thường

Một dependency thật bằng constructor injection:

```java
public final class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
```

Nếu Spring tạo `OrderService` thông qua bean definition hợp lệ và resolve `OrderRepository`, nó phải tạo/chuẩn bị repository trước khi truyền vào constructor. Đây là **phụ thuộc object trực tiếp**, có thể được biểu đạt bằng:

```java
@Bean
OrderService orderService(OrderRepository repository) {
    return new OrderService(repository);
}
```

hoặc XML:

```xml
<bean id="orderRepository" class="com.example.OrderRepository"/>
<bean id="orderService" class="com.example.OrderService">
    <constructor-arg ref="orderRepository"/>
</bean>
```

Những snippets trên cần Java classes `OrderService` và `OrderRepository` phù hợp.

### Không thêm @DependsOn nếu constructor đã diễn đạt đúng dependency

Trong trường hợp này, thêm:

```java
@DependsOn("orderRepository")
@Bean
OrderService orderService(OrderRepository repository) {
    return new OrderService(repository);
}
```

thường **thừa**: tham số `repository` đã làm Spring biết phải có repository. `@DependsOn` không cải thiện type safety và có thể làm người đọc nhầm rằng tồn tại một lifecycle side effect riêng.

**Quy tắc:** Nếu bean B **thực sự cần giữ/thao tác trên object A**, hãy **inject A**, thay vì chỉ thêm tên A vào `@DependsOn`.

## 3. Khi nào DI không biểu diễn được phụ thuộc?

Có những requirements không truyền object trực tiếp.

### 3.1. Registry global của thư viện legacy

Một bean `PluginRegistrar` gọi API đăng ký plugin trong init callback; một bean `PluginLauncher` sau đó dùng một static registry, không nhận `PluginRegistrar` vào constructor:

```text
PluginRegistrar.initialize()
    |
    +--> SharedPlugins.register("pdf", PdfPlugin)
    |
    v
PluginLauncher được phép bắt đầu hoạt động
    |
    +--> SharedPlugins.lookup("pdf")
```

Thư viện cũ không expose một injectable registry abstraction, nên có thể cần:

```java
@Bean("pluginRegistrar")
PluginRegistrar pluginRegistrar() {
    return new PluginRegistrar();
}

@Bean("pluginLauncher")
@DependsOn("pluginRegistrar")
PluginLauncher pluginLauncher() {
    return new PluginLauncher();
}
```

Đây là cấu trúc minh họa, chưa phải source runnable; các Java types và lifecycle code phải được cung cấp. `@DependsOn` buộc registrar **được khởi tạo trước**, qua đó initialization callback của nó có cơ hội đăng ký plugin. Nó không tự hiểu plugin registry và cũng không truyền plugin object cho launcher.

### 3.2. Cấu hình native/static initialization

Một bean thực hiện side effect ban đầu như nạp native library, đăng ký driver, cài đặt global registry hoặc warm-up một cơ chế đồng bộ. Bean B phụ thuộc vào side effect đó, dù không có reference đến initializer. Tài liệu Spring nêu tình huống tương tự khi một **static initializer cần được trigger**.

### 3.3. Chuyển tiếp kiến trúc legacy

Khi chưa thể refactor code thành DI thuần, `@DependsOn` là bridge rõ nghĩa để loại bỏ sự phụ thuộc tình cờ vào thứ tự component scan hoặc thứ tự khai báo bean.

Tuy vậy, **đừng dùng @DependsOn để duy trì mãi một global mutable state** nếu có thể thay thế bằng dependency được inject, interface/registry bean thực sự, hoặc hạ tầng lifecycle có contract rõ.

## 4. @DependsOn đảm bảo điều gì?

Javadoc Spring mô tả: các beans được liệt kê trong `@DependsOn` được container tạo **trước** bean mang annotation. Ngữ cảnh gồm việc thực hiện initialization theo lifecycle do Spring quản lý.

```text
bean "appWorker" có @DependsOn("setup")
                 |
                 v
BeanFactory kiểm tra "setup"
                 |
                 +--> tạo setup nếu chưa có
                 +--> resolve dependencies của setup
                 +--> chạy các init callbacks đồng bộ của setup
                 |
                 v
BeanFactory tạo "appWorker"
                 |
                 +--> resolve dependencies của appWorker
                 +--> chạy init callbacks của appWorker
                 |
                 v
Cả hai sẵn sàng theo bean lifecycle
```

**Giới hạn quan trọng:** nếu `setup` khởi động một asynchronous task và `init()` return **trước khi task hoàn thành**, Spring chỉ biết bước initialization đồng bộ của setup hoàn tất. `@DependsOn` **không mặc định chờ mọi Future, thread, remote service hoặc distributed operation** đạt trạng thái ready.

### 4.1. Initialization order ≠ invocation order của mọi method

Spring có thể bảo đảm:

```text
setup.init trước appWorker.init
```

nhưng không vì thế mà bảo đảm:

```text
mọi lời gọi appWorker.run() đều chờ setup's background task thật sự xong
```

Nếu workload cần barrier rõ ràng, hãy thiết kế readiness contract (ví dụ `CompletableFuture`/latch/health state với timeout) hoặc lifecycle orchestration phù hợp, thay vì chỉ dùng annotation tên bean.

### 4.2. Tên dùng trong @DependsOn là bean name

```java
@DependsOn("registryInitializer")
```

`registryInitializer` là **bean name** (hoặc một alias có thể resolve trong container), không phải tên field, Java type đơn lẻ hoặc package name. Khi dùng `@Bean("registryInitializer")`, tên này là contract khai báo.

Nếu đổi tên bean mà quên cập nhật annotation, context có thể fail trong quá trình tạo bean phụ thuộc.

## 5. Cú pháp @DependsOn trên @Bean method

Một dependency:

```java
@Configuration(proxyBeanMethods = false)
class AppConfig {

    @Bean("bootstrapState")
    BootstrapState bootstrapState() {
        return new BootstrapState();
    }

    @Bean("reportWorker")
    @DependsOn("bootstrapState")
    ReportWorker reportWorker() {
        return new ReportWorker();
    }
}
```

Đoạn minh họa yêu cầu imports `Configuration`, `Bean`, `DependsOn` và Java types thật. Method `reportWorker()` **không nhận `BootstrapState`**: relation được khai báo qua metadata, không phải tham số DI.

**Đặt `@DependsOn` lên method bean cần được tạo *sau***, không đặt nó lên prerequisite rồi kỳ vọng nghĩa đảo chiều.

### 5.1. Nhiều prerequisites

```java
@Bean("dataReporter")
@DependsOn({"driverRegistration", "schemaValidation"})
DataReporter dataReporter() {
    return new DataReporter();
}
```

Ý nghĩa: cả hai named beans phải được initialized trước `dataReporter`. Nhưng `@DependsOn({"A","B"})` **không nên được coi là API buộc A trước B**. Nếu có quan hệ A phải trước B, hãy khai báo trực tiếp **B depends on A**, rồi C depends on B hoặc biểu diễn graph tương ứng.

### 5.2. Một mảng names, không phải expression language

```java
@DependsOn({"cacheBootstrap", "metricsBootstrap"})
```

là literal array of bean names. Nó không tự parse Spring Expression Language thành các bean khác hay khám phá mọi implementation của một interface. Nếu bean names động/condition-dependent, cân nhắc thiết kế khác hoặc programmatic BeanDefinition registration với explicit dependency metadata.

### 5.3. Constructor injection và @DependsOn có thể cùng tồn tại

Nếu consumer cần bean repository thực sự **và** cần side effect của bootstrap:

```java
@Bean("orderProcessor")
@DependsOn("globalCodecRegistrar")
OrderProcessor orderProcessor(OrderRepository repository) {
    return new OrderProcessor(repository);
}
```

Đây là snippet cấu trúc; DI xử lý repository object, `@DependsOn` xử lý side effect prerequisite. Hai quan hệ khác bản chất, có thể dùng chung.

## 6. @DependsOn trên @Component: giới hạn quan trọng

Javadoc `@DependsOn` cho phép dùng ở **TYPE** và **METHOD**. Nhưng class-level annotation có caveat:

> Class-level @DependsOn chỉ có hiệu lực khi component scanning được dùng để đăng ký class ấy.

Ví dụ:

```java
@Component("searchIndexer")
@DependsOn("indexRegistry")
public class SearchIndexer {
    public SearchIndexer() {
    }
}
```

Nếu scanner tìm `SearchIndexer`, metadata `@DependsOn("indexRegistry")` có thể được áp cho bean definition của component.

**Nếu class đó chỉ được khai báo qua XML:**

```xml
<bean id="searchIndexer" class="com.example.SearchIndexer"/>
```

thì annotation cấp class `@DependsOn` **không được áp dụng theo cách XML BeanDefinition này**; hãy cấu hình:

```xml
<bean id="searchIndexer"
      class="com.example.SearchIndexer"
      depends-on="indexRegistry"/>
```

Điểm này được Javadoc Spring nêu rất rõ, nên không thể chỉ nhìn annotation trên Java class mà bỏ qua **đường đăng ký bean**.

### 6.1. @Configuration class có thể là @Component specialization

Một `@Configuration` class cũng thuộc hệ thống component stereotypes. Nhưng `@DependsOn` cấp class không nên được hiểu như cách ép **tất cả `@Bean` methods** trong class đó lần lượt phụ thuộc vào cùng một prerequisite theo mọi cách đăng ký.

Nếu mục tiêu là thứ tự khởi tạo của một bean cụ thể, cách rõ ràng nhất là gắn `@DependsOn` **trực tiếp lên `@Bean` method** tương ứng. Nếu mục tiêu là hạ tầng bootstrap toàn context, cân nhắc đúng extension point/lifecycle hook thay vì ẩn order trong annotation trên configuration container.

## 7. XML depends-on="..." tương đương ở tầng bean definition

Trong XML:

```xml
<bean id="initializationRegistry"
      class="com.example.InitializationRegistry"/>

<bean id="backgroundWorker"
      class="com.example.BackgroundWorker"
      depends-on="initializationRegistry"/>
```

XML attribute `depends-on` mô tả **initialization order constraint**. Nó không tự tạo reference tới registry bên trong Java `BackgroundWorker`.

### 7.1. Nhiều bean names trong XML

```xml
<bean id="reportWorker"
      class="com.example.ReportWorker"
      depends-on="cacheWarmup, schemaCheck"/>
```

Spring cho phép phân cách các names bằng dấu **phẩy, khoảng trắng hoặc chấm phẩy** trong XML `depends-on`.

Tương đương ý nghĩa trong Java:

```java
@DependsOn({"cacheWarmup", "schemaCheck"})
```

**Không đưa class names vào depends-on** nếu class được đăng ký bằng một bean name khác. Ví dụ nếu `@Bean("cacheWarmup")` trả `CacheWarmupService`, tên constraint là `cacheWarmup`.

### 7.2. XML ref không thay cho depends-on trong trường hợp side effect

```xml
<bean id="reportWorker" class="com.example.ReportWorker">
    <constructor-arg ref="cacheWarmup"/>
</bean>
```

dùng `ref` để **đưa object dependency vào constructor**; Java class phải có constructor phù hợp. Nếu worker không nhận/không dùng object đó, chỉ tạo constructor parameter giả để điều khiển thứ tự là một anti-pattern. Dùng `depends-on` mới đúng nghĩa khi thật sự chỉ yêu cầu initialization side effect.

### 7.3. Có thể dùng cả hai

```xml
<bean id="reportWorker"
      class="com.example.ReportWorker"
      depends-on="bootstrapRegistrar">
    <constructor-arg ref="businessRepository"/>
</bean>
```

DI cung cấp `businessRepository`, depends-on buộc `bootstrapRegistrar` init trước. Đây là hai loại dependency riêng.

## 8. Hệ quả khi đóng context: hủy dependent trước prerequisite

`@DependsOn("registry")` trên bean `worker` tạo quan hệ **worker phụ thuộc registry**. Khi cả hai là managed singleton có destruction callbacks, Spring có thể giữ registry tồn tại tới khi worker đã được hủy:

```text
Initialization: registry -> worker
Destruction:    worker   -> registry
```

Điều này hữu ích nếu worker cần unregister callback hoặc flush qua registry lúc `destroy()`. Nó không tự đóng unmanaged threads, chờ future, hoàn tất external transaction hay tạo total order cho những bean không liên hệ.

Ví dụ Java: `@Bean @DependsOn("registry") Worker worker()`; XML: `<bean id="worker" depends-on="registry" .../>`. Với **prototype**, container không tự áp dụng toàn bộ destruction callback như singleton. Bài cuối chương đi sâu vào dependency registry (`getDependentBeans`, `registerDependentBean`), DI relationships và graceful shutdown; ở đây chỉ cần lưu ý hệ quả lifecycle của metadata `@DependsOn`.

## 9. @DependsOn với @Lazy: không phải cách trì hoãn

Giả sử:

```java
@Bean("slowSetup")
@Lazy
SlowSetup slowSetup() {
    return new SlowSetup();
}

@Bean("readyWorker")
@DependsOn("slowSetup")
ReadyWorker readyWorker() {
    return new ReadyWorker();
}
```

Nếu `readyWorker` là non-lazy singleton, Spring cần tạo `slowSetup` **trước** readyWorker, dù slowSetup được đánh dấu lazy. Tức là depends-on có thể **kéo một lazy bean vào startup**.

Một bảng:

| Bean prerequisite | Bean dependent | Dự kiến |
| --- | --- | --- |
| Non-lazy singleton | Non-lazy singleton | prerequisite initialized trước dependent |
| Lazy singleton | Non-lazy singleton có `@DependsOn` | lazy prerequisite bị tạo sớm để thỏa constraint |
| Lazy singleton | Lazy singleton dependent chưa được lookup | có thể cả hai chưa tạo |
| Lazy singleton | Lazy dependent được lookup | prerequisite được tạo trước dependent |
| Prototype prerequisite | Singleton dependent | prerequisite có thể được tạo khi dependent được tạo; destroy semantics khác singleton |
| Scoped prerequisite | Bean ở scope khác | còn phụ thuộc active scope và cách lookup; không xem như ordering toàn cục |

**Đừng dùng @DependsOn để tối ưu startup time.** Nó thêm prerequisite, thường khiến thứ tự và chi phí khởi tạo chặt hơn. Muốn tránh lấy dependency quá sớm, dùng `@Lazy` tại injection point, `ObjectProvider<T>` hoặc điều chỉnh lifecycle contract theo tình huống — nhưng phải bảo toàn correctness.

## 10. Ví dụ Java 17+: Java @Bean, XML, component scan và lazy prerequisite

Ví dụ sau kiểm chứng bằng **thứ tự sự kiện**, không dựa vào thứ tự đăng ký bean hay thời gian wall-clock. Tất cả beans trong demo đều là Spring-managed objects bình thường.

Có bốn contexts **độc lập** để so sánh:

1. `JavaConfig`: `@DependsOn` trên một `@Bean` method.
2. `xml-depends.xml`: XML `depends-on`.
3. `ScanConfig`: `@DependsOn` trên một class được scanner tìm thấy.
4. `LazyConfig`: target `@Lazy` vẫn bị eager dependent kéo vào startup.

Trong mỗi context, một `Tracked` class ghi `construct`, `init` và `destroy` qua `InitializingBean` và `DisposableBean`. `worker` không giữ reference đến `setup`; quan hệ chỉ nằm trong metadata depends-on.

### 10.1. Cây thư mục

```text
depends-on-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── DependsOnDemo.java
        └── resources/
            └── xml-depends.xml
```

Một file Java chứa nested static classes, Spring config và `main`. XML sử dụng **binary class name** có ký tự đô la cho Java nested class: `demo.DependsOnDemo$Tracked`.

### 10.2. Cấu hình Gradle

**`settings.gradle`**

```groovy
rootProject.name = 'depends-on-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.DependsOnDemo'
}
```

Java 17+ và một Gradle version hỗ trợ Java toolchains là đủ. Không cần Spring Boot, database, Jakarta lifecycle annotation hay web server. Spring Context kéo theo Beans/Core và các dependencies cần thiết.

### 10.3. xml-depends.xml

**`src/main/resources/xml-depends.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- Khai báo dependent trước để thấy ordering không dựa vào thứ tự dòng. -->
    <bean id="xmlWorker"
          class="demo.DependsOnDemo$Tracked"
          depends-on="xmlSetup">
        <constructor-arg value="xmlWorker"/>
    </bean>

    <bean id="xmlSetup"
          class="demo.DependsOnDemo$Tracked">
        <constructor-arg value="xmlSetup"/>
    </bean>

</beans>
```

Cả hai là singleton mặc định. `xmlWorker` được khai báo **trước** nhưng `depends-on` buộc `xmlSetup` khởi tạo trước.

### 10.4. Java source đầy đủ

**`src/main/java/demo/DependsOnDemo.java`**

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.annotation.FilterType;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.stereotype.Component;

public final class DependsOnDemo {

    private static final List<String> EVENTS = new ArrayList<>();

    // Không field dependency nào tới bean setup khác.
    public static class Tracked
            implements InitializingBean, DisposableBean {

        private final String name;

        public Tracked(String name) {
            this.name = name;
            EVENTS.add(name + ".construct");
        }

        @Override
        public void afterPropertiesSet() {
            EVENTS.add(name + ".init");
        }

        @Override
        public void destroy() {
            EVENTS.add(name + ".destroy");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class JavaConfig {

        // Deliberately declared before its prerequisite.
        @Bean("javaWorker")
        @DependsOn("javaSetup")
        Tracked javaWorker() {
            return new Tracked("javaWorker");
        }

        @Bean("javaSetup")
        Tracked javaSetup() {
            return new Tracked("javaSetup");
        }
    }

    // Class-level annotation is honored on a scanned component.
    @Component("scanWorker")
    @DependsOn("scanSetup")
    public static class ScanWorker extends Tracked {
        public ScanWorker() {
            super("scanWorker");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(
        basePackageClasses = DependsOnDemo.class,
        useDefaultFilters = false,
        includeFilters = @ComponentScan.Filter(
            type = FilterType.ASSIGNABLE_TYPE,
            classes = ScanWorker.class
        )
    )
    public static class ScanConfig {
        @Bean("scanSetup")
        Tracked scanSetup() {
            return new Tracked("scanSetup");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class LazyConfig {
        @Bean("lazySetup")
        @Lazy
        Tracked lazySetup() {
            return new Tracked("lazySetup");
        }

        @Bean("activeWorker")
        @DependsOn("lazySetup")
        Tracked activeWorker() {
            return new Tracked("activeWorker");
        }
    }

    private static void exercise(
            String label,
            Supplier<? extends ConfigurableApplicationContext> factory) {

        EVENTS.clear();
        int beforeClose;

        try (ConfigurableApplicationContext context = factory.get()) {
            // Construct + init callbacks xảy ra trong refresh().
            System.out.println(label + ".start="
                    + String.join(" > ", EVENTS));

            beforeClose = EVENTS.size();

            // Không chủ động getBean() các prerequisites ở đây.
            // Context close() sẽ gọi destroy callbacks.
        }

        System.out.println(label + ".destroy="
                + String.join(" > ",
                    EVENTS.subList(beforeClose, EVENTS.size())));
    }

    public static void main(String[] args) {
        exercise("java",
                () -> new AnnotationConfigApplicationContext(
                        JavaConfig.class));

        exercise("xml",
                () -> new ClassPathXmlApplicationContext(
                        "xml-depends.xml"));

        exercise("scan",
                () -> new AnnotationConfigApplicationContext(
                        ScanConfig.class));

        exercise("lazy",
                () -> new AnnotationConfigApplicationContext(
                        LazyConfig.class));
    }
}
```

### 10.5. Chạy

Ở thư mục `depends-on-demo`:

```bash
gradle run --quiet
```

Nếu đã có Gradle Wrapper trong project, dùng `./gradlew run --quiet` (Linux/macOS) hoặc `gradlew.bat run --quiet` (Windows). Dùng `javac DependsOnDemo.java` đơn lẻ không đủ khi không có Spring libraries trong compile/runtime classpath; Gradle cấu hình dependencies và copy XML lên classpath.

### 10.6. Stdout dự kiến

```text
java.start=javaSetup.construct > javaSetup.init > javaWorker.construct > javaWorker.init
java.destroy=javaWorker.destroy > javaSetup.destroy
xml.start=xmlSetup.construct > xmlSetup.init > xmlWorker.construct > xmlWorker.init
xml.destroy=xmlWorker.destroy > xmlSetup.destroy
scan.start=scanSetup.construct > scanSetup.init > scanWorker.construct > scanWorker.init
scan.destroy=scanWorker.destroy > scanSetup.destroy
lazy.start=lazySetup.construct > lazySetup.init > activeWorker.construct > activeWorker.init
lazy.destroy=activeWorker.destroy > lazySetup.destroy
```

Chương trình in tám dòng theo `System.out.println`. Gradle/framework có thể in log tùy môi trường, không tính vào tám dòng chủ động này.

### 10.7. Phân tích kết quả Java config

- `javaWorker` được khai báo ở `JavaConfig` **trước** method `javaSetup`.
- `@DependsOn("javaSetup")` yêu cầu BeanFactory tạo/setup prerequisite trước worker.
- `Tracked` ghi constructor và `afterPropertiesSet()`; vì thế `javaSetup.init` được in trước `javaWorker.construct`.
- Khi context đóng, `javaWorker.destroy` đến trước `javaSetup.destroy`.
- `javaWorker` không có reference tới `javaSetup`; quan hệ hoàn toàn ở bean definition metadata.

Điều này minh họa đúng tình huống **phụ thuộc khởi tạo không thể hiện bằng DI**.

### 10.8. Phân tích kết quả XML

- `xmlWorker` xuất hiện trước `xmlSetup` trong XML.
- BeanFactory vẫn phải tạo `xmlSetup` trước để thỏa `depends-on="xmlSetup"`.
- Vì cả hai implement `InitializingBean` và `DisposableBean`, demo ghi được init/destroy qua Spring interfaces, không cần Java `@PostConstruct` hay `@PreDestroy`.
- Shutdown order ngược với startup relation.

### 10.9. Phân tích kết quả component scan

- `ScanConfig` bật `@ComponentScan` nhưng **tắt default filters** để demo chỉ scan chính class `ScanWorker` qua một include filter assignable type.
- `ScanWorker` là public static nested class, có `@Component("scanWorker")` và `@DependsOn("scanSetup")` ở **class level**.
- `scanSetup` được đăng ký bởi method `@Bean` của `ScanConfig`.
- Khi scanner đăng ký ScanWorker, constraint class-level được nhận diện và áp dụng; lifecycle cho thấy setup init trước worker constructor.
- Cách này khác khai báo trực tiếp `<bean class="...ScanWorker"/>` trong XML, vì Javadoc lưu ý annotation class-level không được áp dụng cho BeanDefinition chỉ đăng ký theo XML.

### 10.10. Phân tích kết quả lazy prerequisite

- `lazySetup` mang `@Lazy`, bình thường có thể không được pre-instantiate.
- `activeWorker` là **non-lazy singleton** và có `@DependsOn("lazySetup")`.
- Spring cần tạo lazySetup **trong refresh**, nên nó thực thi `lazySetup.construct` và `lazySetup.init` trước activeWorker.
- Ví dụ này chứng minh **`@Lazy` không ghi đè dependency ordering**.
- Khi đóng context, activeWorker bị destroy trước lazySetup.

### 10.11. Vì sao dùng counter/events thay vì timestamp?

Timestamp và thread scheduling tạo ra các kết quả không ổn định. `List<String> EVENTS` trong demo không bị concurrent mutation vì các configs này dùng startup đồng bộ bình thường và `exercise` chạy tuần tự. Việc in đúng tên và thứ tự của callbacks giúp kiểm chứng hợp đồng `depends-on`.

Nếu chuyển demo sang background initialization hoặc async init, sẽ cần một recorder thread-safe và assertions phù hợp, không được giả định các callbacks luôn chạy cùng thread.

## 11. @DependsOn so với @Order và @Priority

Đây là nhóm annotations thường bị nhầm:

| Annotation | Dùng để làm gì? | Có bảo đảm prerequisite init trước? |
| --- | --- | --- |
| `@DependsOn` | Tạo initialization relationship giữa bean definitions theo names | Có, trong phạm vi Spring BeanFactory lifecycle |
| XML `depends-on` | Tương đương metadata ordering cho XML bean | Có |
| `@Order` | Precedence của ordered components, lists of injected beans hoặc extension point phù hợp | Không phải general-purpose bean initialization dependency |
| `@Priority` | Priority selection/ordering trong những framework APIs tương ứng | Không phải general-purpose init dependency |
| `@Primary` | Ưu tiên candidate trong dependency injection theo type | Không |
| `@Qualifier` | Thu hẹp/chọn dependency candidate | Không trực tiếp |
| `@Lazy` | Trì hoãn eager singleton pre-instantiation | Không; có thể bị depends-on kéo vào startup |
| `@DependsOn` cùng `@Bean` | Ép target named beans init trước bean method target | Có |
| `@Import` / `DeferredImportSelector` | Chọn configuration classes tham gia parsing | Không phải bean instance ordering |
| `@Conditional` | Quyết định một definition có được register không | Không |
| `@Bean(bootstrap=BACKGROUND)` | Hỗ trợ concurrent bean initialization ở Spring 6.2 khi có bootstrap executor | Ordering/await có quy tắc riêng, không đồng nghĩa @DependsOn |

**Đặc biệt:** `@Order(1)` trên service A và `@Order(2)` trên service B không phải cách tin cậy để bảo đảm A được instantiate trước B. Nếu B phải init sau A, dùng **DI** hoặc **`@DependsOn("A")`** theo bản chất quan hệ.

## 12. Khi nào BeanDefinition reader áp dụng depends-on?

Không phải processor tìm runtime annotations mỗi khi gọi method nghiệp vụ. Việc khai báo depends-on trở thành **metadata của BeanDefinition**. BeanFactory biết names cần resolve trước khi tạo bean phụ thuộc.

Quy trình khái niệm:

```text
Đọc @DependsOn trên @Bean hoặc scanned component
   / đọc depends-on từ XML
                  |
                  v
   BeanDefinition.setDependsOn("setup", ...)
                  |
                  v
       BeanFactory.getBean("dependent")
                  |
                  +-- kiểm tra registered prerequisite names
                  +-- detect dependency cycle theo graph
                  +-- getBean("setup") trước
                  +-- sau đó instantiate dependent
                  |
                  v
         register dependency relationship
                  |
                  v
       destruction order cho singletons
```

Đừng dùng diagram này để suy ra mọi bước nội bộ/version giống hệt nhau; nó mô tả **hợp đồng quan hệ** và vì sao dependency order không cần inject object trực tiếp.

### 12.1. Đọc BeanDefinition metadata khi debug

Trong một `AnnotationConfigApplicationContext`:

```java
var definition =
        context.getBeanFactory().getBeanDefinition("javaWorker");
String[] required = definition.getDependsOn();
```

Với demo, mảng này chứa `"javaSetup"`. `getDependsOn()` có thể trả `null` nếu bean không có explicit depends-on. Đây là cách xác minh metadata mà không cần in constructor timestamps.

### 12.2. Bean names và aliases

Spring BeanFactory có cơ chế resolve aliases. Dùng bean name đúng/đã đăng ký hoặc alias hợp lệ trong `@DependsOn`. Tuy nhiên, đối với maintainability nên trỏ tới **canonical bean name** ổn định, đặc biệt khi nhiều XML sources và Java configs được ghép vào một context.

Nếu prerequisite được đăng ký dưới tên `"pluginRegistry"` mà `@DependsOn("PluginRegistry")` dùng Java class short name sai, context không tự đoán type. Hãy kiểm tra tên thực tế bằng `getBeanDefinitionNames()` hoặc metadata.

## 13. Nhiều prerequisites và thứ tự giữa chúng

Ví dụ:

```java
@Bean("worker")
@DependsOn({"cacheSetup", "metricsSetup"})
Worker worker() {
    return new Worker();
}
```

Quan hệ được yêu cầu:

```text
cacheSetup -----+
                +--> worker
metricsSetup ---+
```

Không có yêu cầu nghiệp vụ nào nói `cacheSetup` phải xảy ra trước `metricsSetup`, trừ khi bạn khai báo thêm quan hệ đó. Nếu thực tế cần:

```text
cacheSetup --> metricsSetup --> worker
```

thì **metricsSetup** cần phụ thuộc cacheSetup, **worker** cần phụ thuộc metricsSetup. Không nên chỉ đặt hai names trong một mảng và dựa vào thứ tự liệt kê như chính sách bắt buộc giữa hai prerequisites.

### 13.1. Nguyên tắc thiết kế dependency graph

- Mỗi quan hệ chỉ nên tồn tại khi có một invariant thật.
- Tránh gắn “mọi bean phụ thuộc globalSetup” nếu không liên quan.
- Dependency graph nên là đồ thị có hướng không chu trình.
- Xác định rõ ai sở hữu initialization side effect.
- Coi ordering metadata là API cấu hình, cần regression test.

### 13.2. Vì sao không nên chỉ sắp @Bean methods?

Java source order không phải cơ chế quản lý dependency graph mà application nên dựa vào. Spring có thể parse metadata, resolve constructor dependencies, ưu tiên infrastructure và hoạt động khác qua versions. Sử dụng depends-on/DI để diễn đạt **điều kiện bắt buộc**, không phải thứ tự dòng mã.

## 14. Lỗi vòng phụ thuộc depends-on

Vòng constraint:

```java
@Bean("alpha")
@DependsOn("beta")
Alpha alpha() {
    return new Alpha();
}

@Bean("beta")
@DependsOn("alpha")
Beta beta() {
    return new Beta();
}
```

là một graph không thể thỏa: alpha yêu cầu beta tạo trước, beta lại yêu cầu alpha tạo trước. Spring có thể báo lỗi circular depends-on/circular dependency trong startup hoặc lookup. Không sửa bằng đổi thứ tự khai báo methods: **phải phá vòng phụ thuộc thiết kế**.

Một chain hợp lệ:

```text
driverRegistration --> registrySetup --> worker
```

Trong khi cycle:

```text
A --> B --> C --> A
```

không thể có total init order.

### 14.1. Circular DI và circular depends-on khác nhau

Circular constructor injection giữa A/B cũng là vấn đề, nhưng ở đó các constructors yêu cầu object instances của nhau. Với circular depends-on, có thể cả hai classes đều no-arg constructors mà vẫn lỗi chỉ vì metadata ordering tạo vòng. Hai loại cycle có nguyên nhân và cách khắc phục khác nhau.

### 14.2. Debug graph

Khi gặp exception liên quan `Circular depends-on relationship`, xem `@DependsOn`/XML `depends-on` của **tất cả bean names trong cycle**, bao gồm alias resolution và registrations từ nhiều config sources. Đừng chỉ xem Java fields vì depends-on có thể không được phản ánh trong type-level dependency graph.

## 15. Missing bean và điều kiện đăng ký

`@DependsOn("registry")` yêu cầu bean name `registry` tồn tại khi dependent được tạo. Nếu registry không được đăng ký (không scan, profile tắt, `@Conditional` loại, thiếu XML import), Spring không tự tạo bean tương ứng bằng cách tìm class cùng tên.

### Ví dụ với @Profile

```java
@Configuration
class FeaturesConfig {
    @Bean("optionalRegistry")
    @Profile("reporting")
    Registry optionalRegistry() {
        return new Registry();
    }

    @Bean("reportWorker")
    @DependsOn("optionalRegistry")
    ReportWorker reportWorker() {
        return new ReportWorker();
    }
}
```

Đây là snippet minh họa cần imports và types phù hợp. Nếu profile `reporting` không active, `optionalRegistry` không được register, còn `reportWorker` vẫn active, việc tạo reportWorker sẽ lỗi vì missing required depends-on bean. Nếu worker chỉ có ý nghĩa khi feature bật, đặt profile/condition phù hợp cho **cả hai**, hoặc thiết kế optional dependency contract rõ ràng.

**Đừng dùng @DependsOn để chỉ ra một *optional* bean không chắc tồn tại.** Đây là hard prerequisite.

## 16. @DependsOn và Spring singleton destruction

Nhắc lại quy tắc:

```text
A depends on B
Init: B trước A
Destroy (singletons): A trước B
```

Điều này đặc biệt có ích khi A trong `destroy()` muốn dùng infrastructure B:

```java
final class ClientSession implements DisposableBean {
    private final Registry registry;

    ClientSession(Registry registry) {
        this.registry = registry;
    }

    @Override
    public void destroy() {
        registry.unregister(this);
    }
}
```

Ở snippet này **DI đã tự thể hiện dependency** qua constructor, Spring có thể theo dõi dependent registration khi resolve dependencies, nên không tự động phải thêm `@DependsOn` nếu chỉ để làm rõ thứ tự. Nếu legacy client dùng static `Registry.global()` (không có injected reference), `@DependsOn("registry")` có thể có giá trị thêm để hướng dẫn destruction order.

### 16.1. Những điều không được đảm bảo

- Không quản lý thứ tự dừng của bất kỳ thread tự sinh nào nếu chúng nằm ngoài Spring lifecycle.
- Không đảm bảo thời điểm close resources theo hệ phân tán nhiều JVM/Pods.
- Không thay quyền sở hữu tài nguyên giữa hai contexts khác nhau.
- Không tạo một tổng thứ tự destruction chính xác cho mọi bean không liên hệ.
- Không thay thế các semantics của `SmartLifecycle` phases khi cần startup/shutdown coordination nhiều bước.
- Không tự đảm bảo rằng external database hay broker thật sự sẵn sàng khi bean init kết thúc.

## 17. Sự khác biệt giữa init callback và async ready

Giả sử:

```java
class AsyncWarmup {
    public void initialize() {
        new Thread(this::loadCache).start();
    }

    private void loadCache() {
        // Tải dữ liệu đắt tiền ở thread khác.
    }
}
```

Đây là mã minh họa, không khuyến nghị tạo unmanaged thread trong initializer. Nếu `initialize()` return ngay, Spring có thể coi bean đã init hoàn tất theo callback contract và tiếp tục tạo dependent bean, mặc dù `loadCache()` còn chạy.

### Khi cần readiness thật

Cân nhắc:

- Một init operation đồng bộ có timeout rõ, nếu startup buộc phải chờ.
- `SmartLifecycle` và thứ tự phases khi cần quản lý start/stop.
- `ApplicationListener<ContextRefreshedEvent>` hoặc `@EventListener` nếu logic chỉ nên chạy sau refresh.
- Một readiness signal/health check được đo riêng với quá trình tạo bean.
- Dependency injection qua service có method `awaitReady()` hoặc API explicit, nếu caller cần chờ readiness.
- External orchestration nếu phụ thuộc database, Kafka broker hoặc service mạng khác.

**Không coi `@DependsOn` là distributed readiness barrier.** Nó chỉ quản lý thứ tự lifecycle mà Spring biết và thực thi.

## 18. Spring 6.2 background initialization và phụ thuộc

Spring Framework 6.2 hỗ trợ option `@Bean(bootstrap=BACKGROUND)` cho một số singleton bean initializations khi có hạ tầng bootstrap executor phù hợp. Đây là cơ chế **concurrent startup**, khác với `@Lazy` và `@DependsOn`.

Nếu background bean có prerequisite, Spring phải giải quyết dependency constraints trước khi thực sự có instance dependent hợp lệ. Spring docs nêu background initialization và `@DependsOn` phối hợp để một bean required được initialized trước khi background initialization của bean phụ thuộc khởi động, theo startup infrastructure.

Nhưng do có thread concurrency, bạn **không nên dựa vào thứ tự log/timestamp của hai unrelated background beans** như hợp đồng. Với dependency thực, dùng DI hoặc depends-on; với completion of asynchronous external work, cần readiness contract rõ ràng. Demo mục 10 cố ý dùng **synchronous startup** để output ổn định.

## 19. @DependsOn không phải global @Order cho tất cả beans

Một anti-pattern thường thấy:

```java
@DependsOn("allInfrastructureReady")
@Component
public class EveryService {
}
```

Nếu mọi service đều phụ thuộc một “mega initializer” không có clear lifecycle ownership, điều này biến application startup thành chuỗi cứng, khó test và dễ tạo cycle khi phát triển.

Một thiết kế tốt hơn:

- Chỉ annotate **những beans thực sự cần side effect**.
- Nếu nhiều consumers dùng resource/API, expose injectable service thay cho global shared mutable state.
- Dùng infrastructure-specific lifecycle hook nếu cần một phase tổng thể.
- Chia feature dependencies thành graph nhỏ dễ hiểu.
- Dùng integration tests đo chính xác order của một vài critical beans.

### @DependsOn không bảo đảm bean hoàn tất business workflow

Nếu `OrderConsumer` được tạo sau `PaymentGateway`, điều đó không nói `PaymentGateway` đã xử lý hết outstanding payments. Bean initialization chỉ liên quan readiness cơ bản của instance theo callback contract, không điều khiển mọi runtime workflow.

## 20. Checklist khi dùng @DependsOn

1. Có một side effect prerequisite **thật sự cần** trước khi dependent bean được khởi tạo không?
2. Nếu phụ thuộc là object thật, có thể thay bằng constructor injection không?
3. Prerequisite bean đã có **tên ổn định** trong context chưa?
4. Target được đăng ký qua `@Bean`, component scan hay XML? Chọn đúng vị trí annotation/attribute.
5. Đã tránh nhầm class-level `@DependsOn` cho bean chỉ được đăng ký bằng XML chưa?
6. Quan hệ phụ thuộc có làm lazy prerequisite khởi tạo sớm không?
7. Có nhiều prerequisites không? Nếu chúng phụ thuộc lẫn nhau, đã biểu diễn edges riêng chưa?
8. Graph có cycle nào không?
9. Nếu bean profile-/condition-dependent, prerequisite và dependent có active cùng điều kiện hợp lý không?
10. Initialization callback của prerequisite có **đồng bộ thật sự** hoàn thành side effect cần thiết không?
11. Shutdown order của singleton beans có cần thiết/đúng semantics không?
12. Có thread/remote system nào cần readiness riêng ngoài BeanFactory lifecycle không?
13. Đã test startup **và** shutdown order bằng recorded events chưa?
14. Trong code review, annotation có giải thích “vì sao cần ordering” không?

## 21. Cách debug khi @DependsOn không như mong đợi

### 21.1. Bean name sai

Nếu `@DependsOn("cacheInit")` mà bean thực có name `cacheInitializer`, Spring không chọn target theo Java type. Kiểm tra names đã được register, bao gồm aliases.

### 21.2. Class-level annotation không được áp dụng

Nếu `@DependsOn` đặt trên một class rồi class được đăng ký bằng XML `<bean>`, hãy dùng XML `depends-on`. Javadoc lưu ý điểm khác biệt này.

### 21.3. Bean chưa được đăng ký

Nếu target chưa được component scan, XML import hoặc Java config xử lý, depends-on không thể “tự tìm class trên classpath”.

### 21.4. Dependency cycle

Xác định graph constraints theo names. Cắt quan hệ vòng thay vì đổi thứ tự source code.

### 21.5. Lazy bean vẫn init sớm

Đó là semantics đúng nếu dependent non-lazy cần nó. Muốn true laziness, loại bỏ ordering constraint không cần thiết hoặc thiết kế cách resolve khác.

### 21.6. Init callback return trước khi side effect sẵn sàng

Tự đồng bộ readiness, thay đổi lifecycle hook hoặc design API. Depends-on chỉ bảo đảm callback đồng bộ đã return.

### 21.7. Có nhiều contexts

Depends-on chỉ có ý nghĩa với BeanFactory/context mà names được resolve. Root và child contexts không phải một global mutable registry duy nhất; object ownership và shutdown order liên-context cần thiết kế riêng.

### 21.8. Test bằng log không ổn định

Dùng một recorder trong constructor/`afterPropertiesSet`/`destroy` như demo. Assertions có thể kiểm tra quan hệ `setup.init < worker.construct` và `worker.destroy < setup.destroy` (với singletons).

### 21.9. Không thực sự dùng container tạo bean

Nếu Java code tự `new Worker()`, metadata `@DependsOn` không tự điều khiển constructor. Bean lifecycle ordering cần Spring quản lý object.

### 21.10. @Order được thêm mà lỗi vẫn còn

`@Order` không tạo depends-on metadata. Dùng đúng annotation/constructor injection.

## 22. Câu hỏi ôn tập có đáp án

**Câu 1.** Khi nào `@DependsOn` có giá trị hơn constructor injection?

**Đáp:** Khi quan hệ chỉ là prerequisite side effect / initialization order, không cần truyền object dependency vào constructor.

**Câu 2.** `@DependsOn("setup")` đặt trên bean A nghĩa là gì?

**Đáp:** Bean `setup` phải được Spring tạo/khởi tạo trước A, theo container lifecycle.

**Câu 3.** `@DependsOn` có inject object setup vào A không?

**Đáp:** Không. Muốn A giữ object setup, phải dùng DI.

**Câu 4.** Với A depends on B, destruction order singleton thế nào?

**Đáp:** A được destroy trước B; thứ tự init là B trước A.

**Câu 5.** `@Order(1)` trên A và `@Order(2)` trên B có bảo đảm A init trước B không?

**Đáp:** Không. @Order không phải lifecycle dependency declaration.

**Câu 6.** XML `depends-on` cho hai prerequisites viết ra sao?

**Đáp:** `depends-on="registry,metrics"` hoặc danh sách names dùng delimiter hợp lệ.

**Câu 7.** Class-level `@DependsOn` có áp dụng khi class chỉ được XML `<bean>` đăng ký không?

**Đáp:** Theo Javadoc, không; dùng `depends-on` XML.

**Câu 8.** Bean prerequisite có `@Lazy` nhưng dependent là eager singleton, prerequisite có thể init trong refresh không?

**Đáp:** Có. Ordering constraint buộc Spring tạo prerequisite trước dependent.

**Câu 9.** Một initializer mở thread nền và return ngay, `@DependsOn` có đợi thread đó xử lý xong không?

**Đáp:** Không tự động. Cần đồng bộ readiness theo hợp đồng khác.

**Câu 10.** `@DependsOn({"A","B"})` có yêu cầu A được init trước B không?

**Đáp:** Mục đích chính là cả A và B init trước dependent. Nếu A cần trước B, khai báo thêm B depends on A.

**Câu 11.** Tại sao cycle A depends on B, B depends on A là lỗi dù constructors không có tham số?

**Đáp:** Vì metadata ordering tạo constraint bất khả thi.

**Câu 12.** Có thể đặt `@DependsOn` trên method `@Bean` không?

**Đáp:** Có, đây là một vị trí được Javadoc hỗ trợ và phù hợp khi muốn điều khiển thứ tự bean cụ thể.

**Câu 13.** Vì sao @DependsOn không phải cách kiểm tra service mạng đã sẵn sàng?

**Đáp:** Nó quản lý Spring bean initialization, không xác minh external service health hoặc asynchronous task completion.

**Câu 14.** Nếu metadata `getDependsOn()` của BeanDefinition là null, điều đó nói gì?

**Đáp:** Definition không có explicit depends-on names trong metadata đó; không có nghĩa không có constructor/setter DI dependency.

**Câu 15.** Một singleton dependent được destroy trước prerequisite có ích khi nào?

**Đáp:** Khi dependent cần prerequisite infrastructure để unregister/flush/cleanup trong lúc shutdown.

**Câu 16.** Nếu JavaConfig khai báo worker trước setup trong source, có thể dựa vào thứ tự dòng để tạo đúng không?

**Đáp:** Không. Đặt `@DependsOn("setup")` hoặc dùng DI là cách nói rõ constraint.

## 23. Bài tập thực hành

### Bài 1 — Bỏ @DependsOn

Xóa `@DependsOn("javaSetup")` của `javaWorker`. Dự đoán ordering có còn được bảo đảm không. Chạy demo để xem kết quả trong môi trường của bạn, nhưng nhớ: **một lần chạy có thể tình cờ setup trước worker không đồng nghĩa có contract**.

### Bài 2 — Trỏ tới tên bean không tồn tại

Đổi `@DependsOn("javaSetup")` thành `@DependsOn("wrongSetup")`. Dự đoán context creation failure vì bean prerequisite không tồn tại.

### Bài 3 — Tạo cycle

Gắn thêm `@DependsOn("javaWorker")` lên method `javaSetup`. Dự đoán dependency cycle error. Không sửa bằng đổi thứ tự khai báo.

### Bài 4 — XML nhiều prerequisites

Thêm bean `xmlMetrics` và đặt `depends-on="xmlSetup,xmlMetrics"` trên `xmlWorker`. Kiểm chứng cả hai prerequisites có init events trước worker. Đừng dùng output này để suy ra thứ tự business-level giữa hai prerequisites không liên quan.

### Bài 5 — Chuyển scan sang XML

Thử nạp class `ScanWorker` bằng XML `<bean id="scanWorker"...>`, không dùng component scan, và **không** đặt `depends-on` XML. So sánh behavior với scanner-based case; sau đó thêm `depends-on="scanSetup"` vào XML để khôi phục constraint.

### Bài 6 — Lazy prerequisite

Đổi `activeWorker` thành `@Lazy` và không gọi `getBean("activeWorker")` ngay. Xem liệu `lazySetup` còn bị tạo trong refresh không. Sau đó lookup activeWorker và quan sát thứ tự hai constructors.

### Bài 7 — Async initializer

Cho `Tracked.afterPropertiesSet()` của prerequisite mở task async return ngay, rồi mô phỏng dependent cần dữ liệu từ task. Thiết kế lại synchronization/readiness để không có race. Tránh lấy `Thread.sleep()` ngẫu nhiên làm giải pháp production.

### Bài 8 — Tách side effect khỏi business bean

Nếu bạn có `GlobalRegistry` static, thử refactor thành một interface `Registry` và inject vào consumer qua constructor. Giải thích vì sao type-safe DI dễ test hơn và có thể loại bỏ `@DependsOn` không cần thiết.

## 24. Tài liệu tham khảo chính thức

- [Spring Framework Reference — Using depends-on](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html): lý do sử dụng, XML syntax, nhiều prerequisites và shutdown order.
- [Spring Framework 6.2.19 Javadoc — DependsOn](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/DependsOn.html): đối tượng/điểm gắn annotation, constructor/initialization semantics và caveat với class-level XML registration.
- [Spring Framework Reference — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html): DI dependency đã đủ biểu diễn thứ tự khởi tạo.
- [Spring Framework Reference — Java @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): phương thức factory và dependency method parameters.
- [Spring Framework Reference — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html): lazy singleton có thể bị eager dependency kéo vào startup.
- [Spring Framework Reference — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html): `@DependsOn` và background initialization trong Spring 6.2.
- [Spring Framework Reference — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `InitializingBean`, `DisposableBean`, lifecycle ordering.
- [Spring Framework 6.2.19 Javadoc — BeanDefinition](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html): `getDependsOn()` và bean metadata.

**Kết luận:** `@DependsOn` (Java) và `depends-on` (XML) dành cho các **phụ thuộc khởi tạo không được thể hiện trực tiếp bằng object injection**. Spring tạo các prerequisite beans trước dependent bean và, với singleton relationships, destroy dependent trước prerequisite. Đây là **bean lifecycle ordering**, không phải DI, `@Order`, background-task completion, hay readiness của một hệ thống phân tán. Hãy ưu tiên constructor injection cho object dependencies thật; chỉ sử dụng depends-on khi có side effect prerequisite rõ ràng và kiểm chứng bằng integration tests.
