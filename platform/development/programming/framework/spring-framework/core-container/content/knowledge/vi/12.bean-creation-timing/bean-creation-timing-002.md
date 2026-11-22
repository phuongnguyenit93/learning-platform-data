# Trì hoãn tạo bean bằng @Lazy và lazy-init trong Spring Core Container

## 1. Đặt vấn đề

Khi một ứng dụng Spring khởi động, `ApplicationContext` thông thường **tạo sẵn các singleton beans không đánh dấu lazy** trước khi hoàn tất `refresh()`. Đây là chiến lược *eager pre-instantiation*: container kiểm tra constructor, dependency injection và nhiều lỗi cấu hình ngay lúc startup, thay vì để lỗi chỉ xuất hiện khi người dùng gọi chức năng vào một thời điểm muộn hơn.

Tuy nhiên, một số bean có thể rất tốn chi phí tạo: client kết nối dịch vụ tùy chọn, bộ giải mã lớn, thành phần chỉ được sử dụng ở tính năng ít gặp, adapter dùng trong một workflow đặc biệt. Nếu eager initialization không cần thiết, Spring hỗ trợ **lazy initialization**:

- Dùng **`@Lazy`** trên Java `@Bean` method hoặc component class.
- Dùng **`lazy-init="true"`** trên XML `<bean>`.
- Đặt **`@Lazy`** trên một `@Configuration` class để áp dụng mặc định cho các `@Bean` methods của class đó.
- Đặt **`default-lazy-init="true"`** trên XML `<beans>` để đặt mặc định cho các bean definitions trong tài liệu đó.
- Dùng **`@Lazy` ở injection point** để inject *lazy-resolution proxy* thay vì resolve ngay target bean tại thời điểm tạo consumer.

Những lựa chọn này **không tương đương về tác dụng trong mọi tình huống**. Một bean được đánh dấu lazy vẫn có thể bị tạo lúc startup nếu một non-lazy singleton cần nó. Và `@Lazy` đặt trên bean definition không giống `@Lazy` trên tham số injection.

### Mục tiêu của bài

Sau bài, bạn có thể:

1. Giải thích các pha **đăng ký BeanDefinition → tạo singleton lúc refresh → lookup/use**.
2. Phân biệt eager, lazy, singleton, prototype và request/session/custom scope.
3. Cấu hình Java `@Lazy` và XML `lazy-init` đúng vị trí; hiểu giá trị `true`/`false`.
4. Giải thích tác động của eager dependencies, `@DependsOn`, XML `depends-on`, inject vào collections và các callback bootstrap.
5. Dùng `@Lazy` tại injection point để trì hoãn resolution với lazy proxy; biết các hạn chế về optional dependency, type/proxy và thời điểm lỗi.
6. So sánh `@Lazy` với `ObjectProvider<T>`, `Provider<T>`, `@Scope` và cơ chế bootstrap chạy nền.
7. Chạy một ví dụ Java 17+ với Spring Framework 6.2.19, quan sát bộ đếm constructors trước/sau lookup.
8. Quyết định nơi nên dùng lazy, cân nhắc độ trễ request đầu tiên, phát hiện lỗi muộn và quản lý tài nguyên.

**Ngữ cảnh:** Đây là chủ đề trong nhóm **Thời điểm tạo bean** của Spring Framework Core Container. Bài tập trung vào **lifecycle và thời điểm instantiation**, không nhầm với deferred configuration parsing hoặc runtime asynchronous programming.

## 2. Eager và lazy thực chất kiểm soát điều gì?

Một `BeanDefinition` là metadata về tên, Java type, scope, factory method, arguments, lazy flag và lifecycle. Nó có thể tồn tại trong registry **trước khi bean instance được tạo**.

```text
XML <bean> / Java @Bean / @ComponentScan
                |
                v
       BeanDefinitionRegistry
                |
                v
          refresh() của context
                |
                +--> tạo non-lazy singleton beans
                |
                +--> giữ lazy singleton definitions chưa tạo
                |
                v
          context đã khởi động
                |
          getBean(lazyName) / dependency lookup
                |
                v
          tạo lazy singleton nếu cần
                |
                v
          tái sử dụng instance trong context
```

Trên `ApplicationContext` thông thường:

- **Non-lazy singleton (mặc định):** Spring cố gắng pre-instantiate nó lúc container khởi động.
- **Lazy singleton:** Spring không pre-instantiate chỉ vì definition tồn tại; bean được tạo khi có yêu cầu giải quyết thực sự.
- **Prototype:** không được pre-instantiate như singleton thông thường; container tạo instance mỗi lần bean được yêu cầu, dù lazy flag có thể xuất hiện trong metadata.
- **Scoped beans (request/session/custom):** thời điểm tạo phụ thuộc scope implementation và ngữ cảnh hoạt động; không thể suy luận giống singleton.

Với lazy singleton, hai lần `getBean("reportClient")` trong **cùng context** sau khi bean đã được tạo thường trả **cùng một instance**. `@Lazy` thay *thời điểm tạo*, không thay singleton thành prototype.

### 2.1. Tại sao Spring mặc định eager?

Lợi ích quan trọng của pre-instantiation:

1. Phát hiện sớm thiếu bean và xung đột injection.
2. Phát hiện sớm lỗi constructor/factory method.
3. Kiểm tra cấu hình/tài nguyên cần thiết trước khi nhận lưu lượng.
4. Tránh chuyển chi phí khởi tạo sang request đầu tiên.
5. Làm startup diagnostics dễ lý giải.

Lazy initialization đổi lấy khả năng rút ngắn một phần startup khi bean chưa cần dùng, nhưng có thể **hoãn lỗi** và **dồn latency** sang lần sử dụng đầu tiên. Do đó, không nên bật cho mọi bean mà không đo hiệu quả.

## 3. @Lazy trên Java @Bean

Một Java configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;

@Configuration(proxyBeanMethods = false)
public class AdapterConfig {
    @Bean
    @Lazy
    ExternalReportClient reportClient() {
        return new ExternalReportClient();
    }

    @Bean
    RequestRouter requestRouter() {
        return new RequestRouter();
    }
}
```

Đây là ví dụ **cấu trúc**; `ExternalReportClient` và `RequestRouter` phải là Java classes có constructors phù hợp và được đưa vào project. Khi configuration được nạp:

- `reportClient` có bean definition được đánh dấu **lazy**.
- `requestRouter` là non-lazy singleton theo mặc định.
- Nếu `requestRouter` không phụ thuộc vào `reportClient` và không có infrastructure nào lấy reportClient sớm, Spring có thể khởi tạo requestRouter trong refresh nhưng hoãn reportClient.
- Khi lần đầu lookup `reportClient`, Spring gọi factory method `reportClient()` và quản lý kết quả.

**Lưu ý:** annotation cần import đúng package `org.springframework.context.annotation.Lazy`. Nó khác các annotation `Lazy` của thư viện bên thứ ba hoặc tự định nghĩa.

### 3.1. @Lazy có giá trị mặc định true

```java
@Lazy
@Bean
ExternalReportClient reportClient() {
    return new ExternalReportClient();
}
```

tương đương:

```java
@Lazy(true)
@Bean
ExternalReportClient reportClient() {
    return new ExternalReportClient();
}
```

`@Lazy(false)` là một cách tường minh chọn **eager initialization**, đặc biệt khi kế thừa mặc định lazy từ configuration class hoặc các chính sách khác.

### 3.2. Vị trí annotation

`@Lazy` có thể dùng trên:

- Một type mang `@Component` hoặc stereotype hợp lệ.
- Method `@Bean`.
- Class `@Configuration`, ảnh hưởng mặc định lazy của các `@Bean` methods trong configuration class ấy.
- Field, constructor hoặc parameter ở **injection point** cùng `@Autowired`/`@Inject`, với semantics **lazy-resolution proxy**.

**Đừng gộp hai semantics:** `@Lazy` trên **definition** điều khiển target bean có bị pre-instantiate không; `@Lazy` trên **injection point** điều khiển resolution dependency khi inject consumer.

## 4. @Lazy trên component class

Ví dụ service mang stereotype:

```java
package com.example.report;

import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Service;

@Service
@Lazy
public class ReportRenderer {
    public String render() {
        return "report";
    }
}
```

Nếu class nằm trong package mà `@ComponentScan` hoặc XML `<context:component-scan>` bao phủ, Spring đăng ký bean definition `reportRenderer` dưới dạng lazy. Bean không bị khởi tạo chỉ vì scanner tìm thấy class; khi `getBean(ReportRenderer.class)` hoặc dependency eager thực sự cần nó, Spring tạo bean.

### 4.1. @Lazy không tự bật component scanning

Class có `@Service @Lazy` nhưng **chưa được Spring đăng ký** thì không có bean definition để lazy/eager. Cần `@ComponentScan`, XML component-scan hoặc một con đường registration phù hợp.

### 4.2. @Lazy trên class không do Spring tạo

```java
ReportRenderer renderer = new ReportRenderer();
```

Object tạo qua `new` ở Java code ngoài BeanFactory không được áp lifecycle lazy của Spring. Annotation là metadata được container diễn giải khi class được Spring quản lý; nó không chặn constructor của Java.

## 5. @Lazy trên @Configuration class

`@Lazy` đặt trên class `@Configuration` thiết lập mặc định lazy cho các `@Bean` methods bên trong:

```java
@Configuration(proxyBeanMethods = false)
@Lazy
public class OptionalModuleConfig {
    @Bean
    ArchiveReader archiveReader() {
        return new ArchiveReader();
    }

    @Bean
    ReportExporter reportExporter() {
        return new ReportExporter();
    }

    @Bean
    @Lazy(false)
    HealthIndicator healthIndicator() {
        return new HealthIndicator();
    }
}
```

Đây là snippet Java minh họa; cần imports `@Bean`, `@Configuration`, `@Lazy` và ba Java types thực. Ý nghĩa:

- `archiveReader` và `reportExporter` mặc định lazy.
- `healthIndicator` override thành non-lazy nhờ `@Lazy(false)`.
- `@Configuration` class vẫn cần được Spring **đăng ký/parse** trong context.
- Không nên đồng nhất việc tạo configuration class instance với việc chạy mỗi `@Bean` factory method. Configuration metadata được xử lý trong startup dù một số target bean instances bị hoãn.

### 5.1. @Lazy trên component stereotype với @Bean methods

Spring hỗ trợ `@Lazy` trên type được đánh dấu `@Component`. Tuy nhiên, nếu muốn mặc định lazy cho **toàn bộ các factory methods**, hãy dùng `@Configuration @Lazy` đúng mục đích và test rõ imported configurations cùng các method overrides. Đừng suy luận mọi class do `@Import` từ một configuration lazy đều tự inherit lazy flag; phạm vi annotation phải được hiểu trên từng definition.

## 6. XML lazy-init="true" trên <bean>

Trong XML configuration:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="eagerClient" class="com.example.EagerClient"/>

    <bean id="lazyClient"
          class="com.example.ExpensiveClient"
          lazy-init="true"/>
</beans>
```

Trong ví dụ này:

- `eagerClient` là non-lazy singleton theo mặc định.
- `lazyClient` có bean definition lazy và thường không được tạo trong pre-instantiation.
- `context.getBean("lazyClient")` có thể làm Spring tạo bean ngay lần đầu được gọi.
- Nếu một singleton eager khác cần `lazyClient`, Spring vẫn phải tạo lazyClient để thỏa dependency (xem mục 8).

`lazy-init` là **XML bean-definition attribute**, không phải Java field, không phải property của target class, cũng không phải cơ chế network lazy connect riêng của thư viện.

### 6.1. Explicit false

```xml
<bean id="importantClient"
      class="com.example.ImportantClient"
      lazy-init="false"/>
```

Dùng `false` khi muốn rõ rằng bean này cần được tạo lúc startup; nó đặc biệt hữu ích để override default-lazy-init của XML resource.

### 6.2. Không nhầm với scope="prototype"

```xml
<bean id="builder"
      class="com.example.Builder"
      scope="prototype"
      lazy-init="true"/>
```

Scope prototype thường đã có semantics **tạo khi yêu cầu**; nó không có singleton pre-instantiation thông thường. Đặt lazy-init vào prototype thường không đem lại điểm khác biệt như singleton. Hai lần lookup prototype vẫn có thể tạo hai instances.

## 7. XML default-lazy-init="true"

Spring hỗ trợ đặt mặc định ở root `<beans>`:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       default-lazy-init="true">

    <bean id="optionalClient"
          class="com.example.OptionalClient"/>

    <bean id="criticalMonitor"
          class="com.example.CriticalMonitor"
          lazy-init="false"/>
</beans>
```

Đây là một snippet cấu trúc; trong file thật nên khai báo schemaLocation như những XML hoàn chỉnh ở phần demo. Mọi `<bean>` không override có thể kế thừa mặc định lazy của tài liệu XML. `criticalMonitor` được đánh dấu rõ **eager**.

### 7.1. Tác dụng là theo metadata XML resource

`default-lazy-init` không phải một “global JVM flag” áp lên mọi bean của mọi context. Nó là mặc định trong tài liệu XML tương ứng, theo cơ chế parse BeanDefinitions. Những definitions có nguồn Java configuration, programmatic registration hoặc file XML khác có thể có lazy flags riêng.

Với nhiều XML imports hoặc nested `<beans>`, hãy xem cấu hình thực tế từng resource và định nghĩa. Không kết luận một flag trong `settings.xml` tự thay metadata của mọi bean trong ứng dụng.

### 7.2. Có nên bật toàn bộ?

Chỉ nên bật sau khi cân nhắc:

- Những bean nào phải fail-fast trước khi app nhận traffic?
- Có startup event listener hoặc health check cần bean ngay không?
- Tài nguyên cần thiết có được kiểm tra ở startup không?
- Request đầu tiên của feature có chịu được thời gian khởi tạo không?
- Các bean lazy có bị dependency eager kéo vào startup không?

Nếu dùng Spring Boot, còn có `spring.main.lazy-initialization=true`; đó là **tính năng Boot**, không đồng nhất với một XML `default-lazy-init` trong Spring Framework thuần.

## 8. Bẫy quan trọng: eager dependency có thể tạo lazy bean ngay lúc startup

Giả sử `ExpensiveService` là singleton `@Lazy`, nhưng `EagerController` là singleton không lazy và nhận trực tiếp `ExpensiveService` trong factory method:

```java
@Bean @Lazy
ExpensiveService expensiveService() { return new ExpensiveService(); }

@Bean
EagerController eagerController(ExpensiveService service) {
    return new EagerController(service);
}
```

Khi `ApplicationContext.refresh()` tạo controller, Spring **phải phân giải dependency** trước khi gọi factory method. Vì thế `expensiveService` bị tạo trong startup; `@Lazy` trên definition chỉ loại bean khỏi lượt tự pre-instantiate, không từ chối một yêu cầu dependency thực tế.

Lúc debug, xác định đường nào yêu cầu target: constructor, field/setter, tham số `@Bean`, `depends-on`, component infrastructure hoặc explicit `getBean`. XML `lazy-init="true"` cũng không tránh được một eager `<constructor-arg ref="..."/>`. Đừng chỉ di chuyển vị trí khai báo bean hoặc thêm `@DependsOn`: những cách đó không hoãn dependency.

Nếu consumer thực sự có thể chạy trước khi cần target, hãy cân nhắc **`@Lazy` ở injection point** (proxy trì hoãn việc tra cứu) hoặc `ObjectProvider<T>` (lookup tường minh tại thời điểm xử lý). Bài tiếp theo kiểm tra riêng chuỗi eager→lazy qua nhiều cấp phụ thuộc; mục dưới đây tập trung vào cách cấu hình lazy-resolution proxy.

## 9. @Lazy trên injection point: lazy-resolution proxy

`@Lazy` có thể đặt trên constructor parameter, field hoặc method injection point phù hợp. Ví dụ:

```java
@Component
public class CheckoutService {
    private final InvoiceApi invoiceApi;

    public CheckoutService(@Lazy InvoiceApi invoiceApi) {
        this.invoiceApi = invoiceApi;
    }

    public String issueInvoice() {
        return invoiceApi.issue();
    }
}
```

Đây là snippet minh họa; `InvoiceApi` cần là interface/bean type phù hợp và imports `@Component`, `@Lazy`. Khi Spring tạo `CheckoutService`, nó có thể inject một **lazy-resolution proxy** thay vì instantiate target ngay.

### 9.1. Hai cách đặt @Lazy khác nhau

**Đặt trên target bean definition:**

```java
@Bean
@Lazy
InvoiceApi invoiceApi() {
    return new DefaultInvoiceApi();
}
```

tác động đến **pre-instantiation của target**.

**Đặt tại injection point:**

```java
@Bean
CheckoutService checkoutService(@Lazy InvoiceApi invoiceApi) {
    return new CheckoutService(invoiceApi);
}
```

tác động đến **thời điểm dependency được resolve/đưa target thật vào consumer**.

Để target thật sự chưa được tạo lúc startup trong một chương trình đơn giản, thông thường cần bảo đảm **cả target definition là lazy** *và* **consumer nhận lazy proxy**, đồng thời không có eager bean khác buộc tạo target.

### 9.2. Khi proxy được sử dụng lần đầu

Một lần gọi business method trên proxy khiến Spring resolve target thực. Với singleton target, lần resolution sau thường dùng target singleton đã tạo. Với non-singleton scope, proxy có thể tái resolve target ở các lần gọi thích hợp theo phạm vi/lifecycle.

Proxy không phải target instance; kiểm tra `proxy.getClass() == target.getClass()` không phải cách xác nhận target đã được khởi tạo. Và việc gọi một số method trên proxy có thể kích hoạt target resolution, kể cả khi bạn chỉ định log hoặc inspect proxy.

### 9.3. Không dùng @Lazy injection proxy như optional dependency detector

Javadoc Spring nêu rõ lazy-resolution proxy **luôn được inject** tại điểm tiêm phù hợp. Nếu target dependency thực tế không có, lỗi có thể chỉ phát sinh khi gọi method trên proxy, khiến các checks kiểu `invoiceApi != null` không phát hiện thiếu dependency.

Với optional/conditional dependencies, Spring khuyến nghị những API rõ nghĩa hơn như:

```java
public CheckoutService(ObjectProvider<InvoiceApi> invoiceApiProvider) {
    this.invoiceApiProvider = invoiceApiProvider;
}
```

hoặc một interface `Provider<T>` tương ứng khi dependency và stack có hỗ trợ. Với `ObjectProvider`, bạn chủ động gọi `getIfAvailable()`/`getObject()`, kiểm tra absence và chính sách fallback. Cần import `org.springframework.beans.factory.ObjectProvider` trong đoạn Java hoàn chỉnh.

### 9.4. Proxy có những giới hạn thiết kế nào?

- Interface injection point thường phù hợp với JDK proxy; injection theo concrete class có thể cần class-based proxy.
- Final classes, final methods, visibility và module access có thể làm proxy khó hoặc không thể tạo.
- Sử dụng proxy cho method dựa trên identity/`equals`/`hashCode` cần hiểu proxy semantics.
- Không nên buộc constructor của bean consumer gọi ngay method của lazy proxy nếu mục tiêu là trì hoãn target.
- Nếu target bean là eager do cấu hình khác, lazy proxy **không đảm bảo target chưa được tạo**.
- Proxy có thể làm exception phát sinh ở request đầu tiên thay vì tại startup.

**Nguyên tắc:** lazy proxy là một cơ chế **deferred dependency resolution**, không phải phép màu biến mọi class thành lazy-safe.

## 10. Ví dụ thực hành Java 17+ với Spring Framework 6.2.19

Bài thực hành dùng:

1. **XML bean lazy-init:** so sánh eager và lazy singleton.
2. **XML default-lazy-init:** áp dụng mặc định lazy và override một bean thành eager.
3. **Java @Bean @Lazy:** xem Java config tương đương XML.
4. **Eager consumer ép lazy dependency khởi tạo:** chứng minh anti-assumption quan trọng.
5. **@Lazy tại injection point:** tạo consumer eager nhưng chỉ khởi tạo target khi thực sự gọi method.

Để kết quả quan sát **không bị nhiễu bởi logging hay đồng hồ**, mỗi Java class được kiểm chứng bằng `AtomicInteger` counter tăng trong constructor. Chương trình in giá trị counter ngay sau `refresh()`, sau `getBean()` hoặc sau method invocation.

### 10.1. Cấu trúc project

```text
spring-lazy-timing-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LazyTimingDemo.java
        └── resources/
            ├── xml-lazy.xml
            └── xml-default-lazy.xml
```

Toàn bộ Java demo nằm trong **một source file**, dùng các nested static classes để dễ copy/paste. Trong XML, tên binary của nested classes là `demo.LazyTimingDemo$NestedClass`. Ký tự `$` ở đây biểu thị dấu đô la trong Java binary name; trong hai file XML hoàn chỉnh dưới đây, cú pháp dùng đúng tên nested class.

### 10.2. Gradle build

**`settings.gradle`**

```groovy
rootProject.name = 'spring-lazy-timing-demo'
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
    mainClass = 'demo.LazyTimingDemo'
}
```

Dùng Java 17+, một phiên bản Gradle tương thích Java toolchains và kết nối Maven Central khi cần lấy dependency lần đầu. Không có Spring Boot, servlet container hoặc database.

### 10.3. XML #1 — một eager, một lazy singleton

**`src/main/resources/xml-lazy.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="xmlEager" class="demo.LazyTimingDemo$XmlEager"/>

    <bean id="xmlLazy"
          class="demo.LazyTimingDemo$XmlLazy"
          lazy-init="true"/>
</beans>
```

`XmlEager` phải được tạo khi context khởi động, còn `XmlLazy` sẽ chưa tạo cho đến khi lookup nếu không có dependency ép khởi tạo.

### 10.4. XML #2 — default-lazy-init và explicit override

**`src/main/resources/xml-default-lazy.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd"
       default-lazy-init="true">

    <bean id="xmlDefaultLazy"
          class="demo.LazyTimingDemo$XmlDefaultLazy"/>

    <bean id="xmlOverrideEager"
          class="demo.LazyTimingDemo$XmlOverrideEager"
          lazy-init="false"/>
</beans>
```

Vì `default-lazy-init="true"`, `xmlDefaultLazy` không pre-instantiate; vì explicit `lazy-init="false"`, `xmlOverrideEager` được tạo trong refresh.

### 10.5. Java source đầy đủ

**`src/main/java/demo/LazyTimingDemo.java`**

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class LazyTimingDemo {

    private static final AtomicInteger XML_EAGER = new AtomicInteger();
    private static final AtomicInteger XML_LAZY = new AtomicInteger();
    private static final AtomicInteger XML_DEFAULT = new AtomicInteger();
    private static final AtomicInteger XML_OVERRIDE = new AtomicInteger();

    private static final AtomicInteger JAVA_EAGER = new AtomicInteger();
    private static final AtomicInteger JAVA_LAZY = new AtomicInteger();
    private static final AtomicInteger FORCED = new AtomicInteger();
    private static final AtomicInteger PROXY_TARGET = new AtomicInteger();

    public static final class XmlEager {
        public XmlEager() {
            XML_EAGER.incrementAndGet();
        }
    }

    public static final class XmlLazy {
        public XmlLazy() {
            XML_LAZY.incrementAndGet();
        }
    }

    public static final class XmlDefaultLazy {
        public XmlDefaultLazy() {
            XML_DEFAULT.incrementAndGet();
        }
    }

    public static final class XmlOverrideEager {
        public XmlOverrideEager() {
            XML_OVERRIDE.incrementAndGet();
        }
    }

    public static final class JavaEager {
        public JavaEager() {
            JAVA_EAGER.incrementAndGet();
        }
    }

    public static final class JavaLazy {
        public JavaLazy() {
            JAVA_LAZY.incrementAndGet();
        }
    }

    public static final class ForcedDependency {
        public ForcedDependency() {
            FORCED.incrementAndGet();
        }
    }

    public static final class ForcedConsumer {
        private final ForcedDependency dependency;

        public ForcedConsumer(ForcedDependency dependency) {
            this.dependency = dependency;
        }

        public boolean ready() {
            return dependency != null;
        }
    }

    public interface JobWorker {
        String work();
    }

    public static final class RealWorker implements JobWorker {
        public RealWorker() {
            PROXY_TARGET.incrementAndGet();
        }

        @Override
        public String work() {
            return "work-done";
        }
    }

    public static final class JobConsumer {
        private final JobWorker worker;

        public JobConsumer(JobWorker worker) {
            this.worker = worker;
        }

        public String run() {
            return worker.work();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class JavaBasicConfig {
        @Bean
        JavaEager javaEager() {
            return new JavaEager();
        }

        @Bean
        @Lazy
        JavaLazy javaLazy() {
            return new JavaLazy();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class JavaForcedConfig {
        @Bean
        @Lazy
        ForcedDependency forcedDependency() {
            return new ForcedDependency();
        }

        @Bean
        ForcedConsumer forcedConsumer(ForcedDependency dependency) {
            return new ForcedConsumer(dependency);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ProxyConfig {
        @Bean
        @Lazy
        JobWorker jobWorker() {
            return new RealWorker();
        }

        @Bean
        JobConsumer jobConsumer(@Lazy JobWorker worker) {
            return new JobConsumer(worker);
        }
    }

    public static void main(String[] args) {

        // 1. XML: eager bean tạo lúc refresh, lazy tạo khi lookup.
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("xml-lazy.xml")) {

            System.out.println("xml.eager.after-refresh="
                    + XML_EAGER.get());
            System.out.println("xml.lazy.after-refresh="
                    + XML_LAZY.get());

            XmlLazy first = context.getBean("xmlLazy", XmlLazy.class);
            System.out.println("xml.lazy.after-get=" + XML_LAZY.get());
            System.out.println("xml.lazy.singleton="
                    + (first == context.getBean(XmlLazy.class)));
        }

        // 2. XML: default lazy và override eager.
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext(
                             "xml-default-lazy.xml")) {

            System.out.println("xml.default.after-refresh="
                    + XML_DEFAULT.get());
            System.out.println("xml.override.after-refresh="
                    + XML_OVERRIDE.get());

            context.getBean(XmlDefaultLazy.class);
            System.out.println("xml.default.after-get="
                    + XML_DEFAULT.get());
        }

        // 3. Java @Bean @Lazy.
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             JavaBasicConfig.class)) {

            System.out.println("java.eager.after-refresh="
                    + JAVA_EAGER.get());
            System.out.println("java.lazy.after-refresh="
                    + JAVA_LAZY.get());

            context.getBean(JavaLazy.class);
            System.out.println("java.lazy.after-get="
                    + JAVA_LAZY.get());
        }

        // 4. Non-lazy consumer ép lazy dependency tạo sớm.
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             JavaForcedConfig.class)) {

            System.out.println("forced.after-refresh="
                    + FORCED.get());
            System.out.println("forced.consumer.ready="
                    + context.getBean(ForcedConsumer.class).ready());
        }

        // 5. Lazy bean + @Lazy injection point: proxy trì hoãn target.
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             ProxyConfig.class)) {

            System.out.println("proxy.target.after-refresh="
                    + PROXY_TARGET.get());

            JobConsumer consumer = context.getBean(JobConsumer.class);
            System.out.println("proxy.result=" + consumer.run());
            System.out.println("proxy.target.after-use="
                    + PROXY_TARGET.get());
            System.out.println("proxy.again=" + consumer.run());
            System.out.println("proxy.target.after-second-use="
                    + PROXY_TARGET.get());
        }
    }
}
```

### 10.6. Lệnh biên dịch/chạy

Trong thư mục `spring-lazy-timing-demo`:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper, dùng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows.

Cách dùng `javac LazyTimingDemo.java` đơn độc **không đủ** vì phải cung cấp Spring libraries qua compile/runtime classpath. Plugin `application` của Gradle xử lý việc build, chạy và copy `src/main/resources` lên classpath.

### 10.7. Stdout dự kiến của chương trình

```text
xml.eager.after-refresh=1
xml.lazy.after-refresh=0
xml.lazy.after-get=1
xml.lazy.singleton=true
xml.default.after-refresh=0
xml.override.after-refresh=1
xml.default.after-get=1
java.eager.after-refresh=1
java.lazy.after-refresh=0
java.lazy.after-get=1
forced.after-refresh=1
forced.consumer.ready=true
proxy.target.after-refresh=0
proxy.result=work-done
proxy.target.after-use=1
proxy.again=work-done
proxy.target.after-second-use=1
```

Chương trình chủ động in **17 dòng** này bằng `System.out.println`. Gradle/framework có thể in thêm log tùy môi trường; log không thuộc các kết quả mà chương trình tính.

### 10.8. Giải thích chính xác từng cụm kết quả

**Cụm XML một bean lazy:** `XmlEager` không có lazy flag, nên constructor chạy trong refresh và counter bằng 1. `XmlLazy` có `lazy-init="true"`, nên counter vẫn 0 sau refresh. Lookup lần đầu tạo instance (counter 1), lookup lần hai trả **cùng singleton**.

**Cụm XML mặc định:** `default-lazy-init="true"` làm `xmlDefaultLazy` chưa tạo sau refresh; `lazy-init="false"` override khiến `xmlOverrideEager` khởi tạo sớm. Lấy `XmlDefaultLazy` sau đó làm count 1.

**Cụm Java:** `JavaEager` là non-lazy singleton và `JavaLazy` được đánh dấu `@Lazy`. Sau refresh counters tương ứng 1 và 0; sau `getBean(JavaLazy.class)` count lazy thành 1.

**Cụm dependency bắt buộc:** `forcedDependency` được đánh dấu `@Lazy` nhưng `forcedConsumer` là eager singleton có factory method parameter cần `ForcedDependency`. Spring phải tạo dependency trong refresh, nên `forced.after-refresh=1`. Consumer giữ dependency non-null.

**Cụm proxy:** `jobWorker` có `@Lazy` trên bean definition; `jobConsumer` inject `@Lazy JobWorker worker` ở **tham số factory method**. Consumer được tạo sớm với lazy-resolution proxy, target `RealWorker` chưa được tạo (`counter=0`). Gọi `consumer.run()` resolve `jobWorker` lần đầu, tăng counter thành 1. Gọi lần hai vẫn dùng singleton target đã được tạo, nên counter giữ 1.

### 10.9. Những giới hạn của ví dụ

Bộ đếm chỉ ghi nhận constructors của các classes được đo. Nó **không** tuyên bố rằng Spring chưa tạo bất kỳ infrastructure bean hoặc configuration class instance nào trong startup. `@Configuration` metadata vẫn được xử lý, và container vẫn cần processors/registry.

Không dùng counter snapshot để ước lượng hiệu năng production: thời gian thực tế còn phụ thuộc I/O, DNS, network handshake, classloading, AOT, GC, cache và thread scheduling. Với production, đo bằng profiling/metrics thay vì đếm constructors.

## 11. @Lazy(false) khi muốn chủ động eager

Trên Java config:

```java
@Configuration(proxyBeanMethods = false)
@Lazy
public class MostlyLazyConfig {
    @Bean
    Formatter formatter() {
        return new Formatter();
    }

    @Bean
    @Lazy(false)
    CriticalHealthCheck criticalHealthCheck() {
        return new CriticalHealthCheck();
    }
}
```

Đây là snippet có kiểu `Formatter`/`CriticalHealthCheck` minh họa. `criticalHealthCheck` vẫn là non-lazy singleton dù class configuration đặt `@Lazy`; `formatter` theo mặc định lazy. Điều này tương tự XML `default-lazy-init="true"` với một `<bean lazy-init="false">`.

### Khi nào nên override?

- Health-check validator cần chứng minh cấu hình chính xác trước khi service nhận requests.
- Data schema/migration preflight cần fail-fast trước traffic.
- Security policy/key validation không nên trì hoãn đến request đầu tiên.
- Publisher/background scheduler cần được khởi tạo chủ động, không phải lần đầu ai đó gọi `getBean()`.
- Component cần đăng ký callback/event handler trước khi context bắt đầu phát sự kiện quan trọng.

Để tránh bất ngờ, những beans có vai trò bootstrap nên được tài liệu hóa và test rõ thời điểm init.

## 12. Eager dependency và @DependsOn

### 12.1. Dependency thực qua constructor/factory method

Nếu `CheckoutService` eager cần `PricingClient` lazy trong constructor, Spring tạo pricingClient trước khi CheckoutService được tạo. Đây là **dependency graph** bình thường.

### 12.2. depends-on là ràng buộc khởi tạo tường minh

```xml
<bean id="metricsRegistry"
      class="com.example.MetricsRegistry"
      lazy-init="true"/>

<bean id="appCoordinator"
      class="com.example.AppCoordinator"
      depends-on="metricsRegistry"/>
```

Giả sử `appCoordinator` là non-lazy singleton, Spring phải khởi tạo `metricsRegistry` trước để đáp ứng `depends-on`, mặc dù target registry là lazy. Với `@DependsOn("metricsRegistry")` trên bean/configuration tương ứng, ý nghĩa tương tự.

`depends-on` không cung cấp object reference như constructor injection; nó thể hiện **initialization prerequisite**. Nếu thực sự consumer dùng object, hãy biểu diễn dependency trực tiếp thay vì chỉ kiểm soát thứ tự.

### 12.3. @DependsOn có giúp lazy hoãn hơn không?

Không. `@DependsOn` thường làm **nhiều** beans phải init sớm hơn, không phải ít hơn. Nếu muốn trì hoãn, cần xác định vì sao bean eager đang yêu cầu target, không thêm depends-on tùy tiện.

## 13. @Lazy khác ObjectProvider<T> như thế nào?

Hai cơ chế đều hữu ích để tránh lấy dependency quá sớm, nhưng dùng cách khác nhau.

### 13.1. Lazy-resolution proxy

```java
public ReportJob(@Lazy ReportClient reportClient) {
    this.reportClient = reportClient;
}
```

Spring inject proxy để consumer giữ một dependency có cùng API; lúc gọi method, proxy resolve target. Cách này ít thay đổi business method signatures, nhưng ẩn thời điểm lookup và có các caveat của proxy.

### 13.2. ObjectProvider

```java
public ReportJob(ObjectProvider<ReportClient> provider) {
    this.provider = provider;
}

public void execute() {
    ReportClient reportClient = provider.getObject();
    reportClient.send();
}
```

Snippet minh họa, cần import `org.springframework.beans.factory.ObjectProvider` và types phù hợp. `ObjectProvider` làm **điểm lookup** tường minh. Nó hỗ trợ `getIfAvailable()`, `ifAvailable(...)`, `getIfUnique()` trong các trường hợp optional/multiple candidates.

### 13.3. Bảng đối chiếu

| Khía cạnh | @Lazy trên injection point | ObjectProvider<T> |
| --- | --- | --- |
| Hình thức consumer nhận | Proxy implement/extend type phù hợp | Provider object |
| Lúc lookup target | Khi proxy được gọi (có thể ở method đầu) | Khi caller gọi provider API |
| Optional target | Có thể nhận proxy dù target vắng; lỗi trễ | Có API `getIfAvailable()` |
| Scope prototype | Có thể tái resolve mỗi lần proxy interaction | Có thể gọi `getObject()` mỗi lần cần |
| Proxy limitations | Có: final class, method, type proxy | Thường không cần proxy target injection |
| Tính rõ ràng | Dễ dùng nhưng timing ẩn | Lookup tường minh trong code |
| Khi phù hợp | API ổn định, dependency thường có mặt | Optional/conditional/sophisticated runtime lookup |

**Quan trọng:** cả hai không nhất thiết giúp target chưa được tạo nếu bean definition của target **vẫn eager** và context đã pre-instantiate nó trong startup. Khi cần trì hoãn thật, phải xét cả **target definition** lẫn **consumer graph**.

## 14. Lazy, prototype, scoped proxy và singleton không giống nhau

### Singleton lazy

Một instance trên một container khi target lần đầu được tạo, sau đó tái sử dụng. Bean definition vẫn được đăng ký từ đầu.

### Prototype

Mỗi lần `BeanFactory.getBean(...)` được yêu cầu thường tạo instance mới. Scope không đồng nghĩa lazy annotation, dù cả hai liên quan timing.

### Request/session scopes

Những web scopes yêu cầu context/request/session hạ tầng. Có thể dùng scoped proxies để injection vào singleton; proxy trỏ tới instance theo scope đang active. Đây là cơ chế khác lazy-resolution proxy đơn giản. Đừng đặt `@Lazy` và cho rằng request scope tự vận hành trong một standalone `AnnotationConfigApplicationContext` không có web context.

### FactoryBean và SmartFactoryBean

Các beans triển khai `FactoryBean<T>` hoặc `SmartFactoryBean<T>` có semantics riêng về factory/product, type prediction và eager-init hints. Một thao tác tra type/metadata có thể có side effects trong một số trường hợp. Nếu lazy behavior bất ngờ khi dùng FactoryBean, cần kiểm tra factory vs product và hạ tầng đang thực hiện lookup.

## 15. Lazy ảnh hưởng lifecycle như thế nào?

### 15.1. Constructor và init callback

Nếu bean lazy chưa được tạo, constructor và initialization callbacks của target chưa chạy. Khi bean được lấy lần đầu, Spring tạo instance, resolve dependencies và áp BeanPostProcessors/init callbacks trước khi trả managed instance phù hợp.

### 15.2. @PostConstruct

`@PostConstruct` không chạy lúc context khởi động nếu bean lazy thực sự chưa được tạo. Khi bean được tạo, callback chạy nếu Jakarta annotation API và `CommonAnnotationBeanPostProcessor` infrastructure tương ứng có mặt.

**Không đồng nhất**: có annotation trên class chưa đủ để callback hoạt động. Và `@Lazy` không tự kích hoạt `@PostConstruct`.

### 15.3. Destroy callback

Một **singleton lazy chưa từng được tạo** không có target instance để Spring destroy. Một singleton lazy **đã được tạo và được context quản lý** có thể nhận destroy callback khi context đóng, nếu có destroy-method/`@PreDestroy`/interface tương ứng và infrastructure phù hợp.

Prototype beans thường có lifecycle destruction responsibility khác singleton; đừng suy luận container tự hủy mọi prototype khi close chỉ vì nó mang `@Lazy`.

### 15.4. Resource ownership

Nếu bean mở network connection, file, executor hoặc pool trong constructor/init:

- Trì hoãn constructor có thể dời thời điểm acquire resource.
- Lỗi network có thể chuyển từ startup sang request đầu tiên.
- Khi target đã tạo, vẫn cần đóng resource đúng cách.
- Có thể dùng explicit warm-up sau khi container sẵn sàng nếu feature quan trọng.

### 15.5. Thread safety

Singleton lazy được BeanFactory quản lý với cơ chế singleton registration/creation thread-safe ở cấp container. Nhưng class nghiệp vụ vẫn phải tự bảo đảm thread safety của mutable state. `@Lazy` không tự biến một class có mutable fields không đồng bộ thành thread-safe.

## 16. Có nên bật lazy cho bean hạ tầng?

Không nên blanket cho mọi bean. Đặc biệt, những BeanFactoryPostProcessors/BeanPostProcessors và một số framework infrastructures cần chạy trước regular singleton creation để container hoạt động đúng. Một số loại infrastructure có cơ chế đăng ký sớm hoặc cần được khởi tạo dù thông thường bean khác có thể lazy.

Nếu muốn trì hoãn resource đắt tiền mà bean hạ tầng cần để điều khiển toàn container, hãy thiết kế bootstrap boundaries rõ ràng thay vì cố ép mọi processor lazy. Không dựa vào “lazy được đánh dấu” như hợp đồng tuyệt đối khi có framework internals/eager dependencies.

### BeanPostProcessor và vấn đề eager creation

Một BeanPostProcessor custom không nên constructor-inject quá nhiều business services, vì điều đó có thể tạo chúng trước giai đoạn autoproxy/processor bình thường. Tách configuration metadata khỏi runtime collaborators khi cần. Đây không chỉ là vấn đề lazy; còn liên quan **eligibility for processing by all post-processors**.

## 17. Spring Boot lazy initialization: điểm đối chiếu

Nếu ứng dụng dùng **Spring Boot** (khác demo Spring Framework thuần), Boot hỗ trợ:

```properties
spring.main.lazy-initialization=true
```

để yêu cầu lazy initialization rộng hơn theo cơ chế `SpringApplication`. Có thể bật/tắt qua API hoặc property, và override một số beans bằng `@Lazy(false)`.

Nhưng:

1. Đây là **tính năng Boot**, không phải property tự được Spring Framework Core Container thuần xử lý.
2. Nó không bảo đảm mọi bean ở mọi infrastructure/version đều chờ đến request đầu tiên.
3. Eager dependency và bootstrap requirements vẫn có thể làm target được tạo sớm.
4. Nó có thể làm **startup nhanh hơn** ở một số hệ thống nhưng chuyển chi phí/lỗi sang lần sử dụng đầu tiên.
5. Cần quan sát memory usage vì khi traffic thực tế kích hoạt nhiều beans, heap cần đủ chứa tất cả instances.
6. Bật toàn cục nên có monitoring, warm-up phù hợp và kế hoạch fail-fast cho resources quan trọng.

Nếu project chỉ khai báo dependency `spring-context` như demo, `spring.main.lazy-initialization=true` trong một file properties không tự kích hoạt cơ chế Boot vì Boot không có trong runtime.

## 18. Lazy vs những cơ chế bị nhầm tên

| Cơ chế | Chức năng chính | Có phải thay thế @Lazy? |
| --- | --- | --- |
| `@Lazy` trên bean definition | Bỏ qua singleton eager pre-instantiation | Chính là cơ chế được học |
| XML `lazy-init="true"` | Bỏ qua eager singleton creation cho XML bean | Cơ chế tương đương trong XML |
| `@Lazy` trên injection point | Inject lazy-resolution proxy | Bổ sung, không giống target definition |
| `ObjectProvider<T>` | Lookup lúc consumer gọi provider API | Lựa chọn cho dynamic/optional lookup |
| `@Scope("prototype")` | Tạo object mỗi lần lookup | Khác scope, không chỉ timing |
| `@DependsOn` | Ép prerequisite initialization order | Thường khiến init sớm hơn |
| `DeferredImportSelector` | Trì hoãn **parse/import selection** trong configuration processing | Không trực tiếp trì hoãn bean instantiation |
| `@Bean(bootstrap=BACKGROUND)` trong Spring 6.2 | Hỗ trợ initialization trên background thread trong startup | Khác lazy, có interaction riêng |
| `@Async` | Method invocation chạy bất đồng bộ qua proxy/executor | Không điều khiển bean pre-instantiation |
| Application event listener | Phản ứng với lifecycle/events | Không phải cách mặc định để trì hoãn bean |
| Request/session scope | Định nghĩa vòng đời object theo web scope | Khác lazy flag |

### 18.1. DeferredImportSelector không phải @Lazy

`DeferredImportSelector` điều khiển **thời điểm chọn import config class** khi Spring phân tích metadata, còn `@Lazy` điều khiển **bean instance creation**. Deferred imported configuration vẫn có thể chứa eagerly instantiated singletons.

### 18.2. Background initialization trong Spring Framework 6.2

Spring Framework 6.2 có option `@Bean(bootstrap=BACKGROUND)` cho background initialization của một số beans. Đây là cơ chế nhằm **thực hiện creation trên background thread trong startup**, không phải chỉ trì hoãn đến lần lookup đầu tiên; các dependencies và việc chờ kết quả có quy tắc riêng. Chỉ dùng khi đã xem tài liệu/khả năng version và quản lý executor/lifecycle phù hợp.

Đừng bật background bootstrap vì chỉ thấy một bean startup chậm mà chưa xác định nguyên nhân và thread safety.

## 19. Các lỗi thường gặp

### Lỗi 1 — Đặt @Lazy nhưng bean vẫn tạo lúc startup

Thường vì một non-lazy singleton cần nó qua constructor, method parameter, field hoặc `depends-on`. Xem dependency graph.

### Lỗi 2 — Nghĩ @Lazy trên bean definition tự inject proxy

Không. Target bean lazy không đồng nghĩa consumer sẽ nhận proxy. Với eager consumer và dependency trực tiếp, container vẫn có thể tạo target ngay. Muốn proxy, đặt `@Lazy` tại injection point phù hợp.

### Lỗi 3 — Tưởng @Lazy ở injection point luôn làm target chưa tạo

Nếu target definition vẫn eager hoặc được bean khác lookup, target có thể đã được tạo lúc refresh. Phải xem cả bean definition lazy flag và dependency graph.

### Lỗi 4 — Không đăng ký @Component nên @Lazy không có hiệu lực

Annotation không tự tạo bean. Cần component scan/`@Import`/Java `@Bean` hoặc programmatic registration.

### Lỗi 5 — Ghi lazy-init="true" nhưng bean ở scope prototype

Prototype vốn không được pre-instantiated như singleton. Flag thường không mang ý nghĩa tối ưu tương tự singleton; cần hiểu scope khi đo.

### Lỗi 6 — Dùng default-lazy-init cho toàn hệ thống mà không warm-up

Có thể làm startup có vẻ tốt hơn nhưng request đầu tiên rất chậm; lỗi tài nguyên cũng xuất hiện muộn. Chọn critical bean eager hoặc warm-up riêng.

### Lỗi 7 — Gọi getBean trong test/bootstrapping rồi kết luận Spring không lazy

`getBean` là yêu cầu tạo target. Nếu gọi trong startup hook/test setup, bạn đã kích hoạt lazy bean. Muốn đo sau refresh, dùng constructor counters hoặc `containsSingleton` thích hợp trước lookup.

### Lỗi 8 — Nhầm containsBean với instance đã tạo

`context.containsBean("lazyClient")` có thể true vì definition tồn tại dù target instance chưa được tạo. Không dùng containsBean làm thước đo constructor execution.

### Lỗi 9 — Cấu hình @Lazy(false) nhưng vẫn tạo muộn

Kiểm tra scope, configuration registration, outer lazy lifecycle hoặc target thực tế là một bean khác. `@Lazy(false)` liên quan eager singleton pre-instantiation trong bean factories có hỗ trợ startup pre-instantiation, không ép prototype thành singleton.

### Lỗi 10 — Proxy lazy không hoạt động với final class

Một lazy-resolution proxy có thể cần tạo subclass nếu injection type không phải interface. Final type/final methods, visibility hoặc module boundaries có thể làm proxy không khả dụng. Ưu tiên interface hoặc `ObjectProvider<T>` tùy trường hợp.

### Lỗi 11 — Dùng @Lazy proxy để kiểm tra optional dependency

Proxy có thể vẫn được inject dù target không tồn tại, lỗi chỉ xuất hiện khi gọi method. Với optional target, dùng `ObjectProvider.getIfAvailable()` hoặc hợp đồng nullable/conditional rõ.

### Lỗi 12 — Đo println trong constructor mà không hiểu contexts

Hai independent ApplicationContexts có singleton caches riêng; nếu khởi động cả hai, mỗi context có thể tạo bean tương ứng của riêng nó. Không suy luận “singleton toàn JVM”.

### Lỗi 13 — Bean lazy có @PostConstruct nhưng callback không chạy lúc startup

Đó là behavior mong đợi nếu target chưa được tạo. Callback thực hiện khi bean được khởi tạo, với annotation processing phù hợp.

### Lỗi 14 — Gọi một method trên proxy chỉ để logging

Method invocation có thể trigger target resolution. Để quan sát state, dùng metrics/counters hoặc BeanFactory metadata APIs đúng mức, tránh làm thay đổi thời điểm bằng thao tác đo.

### Lỗi 15 — Trì hoãn resource critical khiến readiness sai

Health check có thể trả UP trong khi một bean chỉ dùng khi request đến chưa kết nối được database/remote service. Nếu service không thể hoạt động thiếu resource, cân nhắc tạo/validate eager hoặc thêm readiness check thực sự.

### Lỗi 16 — Cho rằng lazy luôn tiết kiệm memory lâu dài

Lazy chỉ tránh tạo bean khi **chưa dùng**. Khi sử dụng, singleton vẫn tồn tại và chiếm memory đến lúc context đóng. Có thể giảm startup memory nhưng không nhất thiết giảm steady-state heap.

### Lỗi 17 — Dùng @DependsOn để “sửa” lazy

`@DependsOn` làm dependency phải khởi tạo trước, thường càng khiến lazy target được tạo sớm hơn. Sử dụng để diễn đạt initialization prerequisite thật sự.

### Lỗi 18 — Nhầm Spring Boot property với Core XML

`spring.main.lazy-initialization` là Boot feature. Cấu hình XML thuần vẫn dùng `lazy-init` hoặc Java `@Lazy`/custom registry API.

### Lỗi 19 — Ngộ nhận @Lazy là asynchronous startup

`@Lazy` không tạo thread nền; nó hoãn việc instantiate cho đến khi cần. `@Async`/background init là cơ chế khác.

### Lỗi 20 — Lười kiểm tra lỗi dependency đến lần sử dụng đầu tiên

Lazy bean có thể fail do thiếu class, password sai, constructor exception, unresolved property hoặc resource unavailable khi được gọi lần đầu. Integration test/health checks nên chủ động exercise chức năng quan trọng.

## 20. Debug một bean có thật sự lazy không

### 20.1. Kiểm tra metadata, không tạo instance

Với `AnnotationConfigApplicationContext` hoặc một `ConfigurableApplicationContext` có BeanFactory truy cập được:

```java
var factory = context.getBeanFactory();
var definition = factory.getBeanDefinition("javaLazy");

System.out.println("lazy-flag=" + definition.isLazyInit());
System.out.println("created=" + factory.containsSingleton("javaLazy"));
```

Đoạn này dùng Java context `JavaBasicConfig` của project demo. `isLazyInit()` cho biết BeanDefinition lazy flag. `containsSingleton(name)` quan sát singleton instance đang nằm trong cache, không chủ động gọi `getBean`. Cả hai cung cấp thông tin hỗ trợ debug, nhưng với `FactoryBean`, aliases và special scopes phải phân biệt bean factory cache/bean product semantics.

### 20.2. Không dùng getBean để kiểm tra “chưa tạo”

```java
context.getBean("javaLazy");
```

**Thao tác này chính là một yêu cầu tạo/lookup bean**. Nếu target chưa tồn tại, nó có thể được tạo ngay. Bài demo deliberately đọc counters **trước** lời gọi đó.

### 20.3. Thứ tự kiểm tra

1. Bean name có được đăng ký?
2. Scope là singleton, prototype hay custom?
3. BeanDefinition lazy flag có đúng không?
4. Bean có được lookup trước khi đo không?
5. Có non-lazy singleton hoặc post-processor nào cần target không?
6. Có `@DependsOn`/`depends-on`/constructor dependency bắt buộc không?
7. Có injection point proxy được bật không?
8. Có configuration class chứa `@Lazy` nhưng method đã `@Lazy(false)` không?
9. Có framework-specific startup policies/Boot global lazy options không?
10. Có thể đo constructor/initialization callback rõ ràng trong integration test không?

### 20.4. Kiểm tra request đầu tiên

Nếu lazy bean giữ client đắt tiền, hãy đo thời gian riêng cho:

- startup toàn app;
- bước lazy target creation;
- lần business call đầu;
- những business calls kế tiếp;
- memory/threads sau warm-up;
- lỗi dưới concurrent first use.

Một cấu hình làm startup ngắn hơn nhưng tăng tail latency request đầu rất lớn có thể không phù hợp yêu cầu vận hành.

## 21. Thực hành mở rộng

### Bài 1 — Thử Java @Lazy(false)

Đặt `@Lazy` lên class `JavaBasicConfig`, sau đó thêm `@Lazy(false)` cho method `javaEager()`. Chạy lại. Giải thích vì sao bean `JavaEager` vẫn được pre-instantiate và `JavaLazy` được trì hoãn.

### Bài 2 — Bỏ lazy-init trên XML

Đổi `xmlLazy` thành `lazy-init="false"` trong `xml-lazy.xml`. Kỳ vọng `xml.lazy.after-refresh=1`; `xml.lazy.after-get` vẫn là 1 do singleton reuse.

### Bài 3 — XML default-lazy-init

Trong `xml-default-lazy.xml`, bỏ `lazy-init="false"` trên `xmlOverrideEager`. Kỳ vọng `xml.override.after-refresh=0`. Sau đó gọi `getBean(XmlOverrideEager.class)` và xác minh constructor counter tăng thành 1.

### Bài 4 — Trực tiếp inject eager consumer

Ở `ProxyConfig`, bỏ `@Lazy` trên parameter của `jobConsumer(...)` trong khi vẫn giữ `@Lazy` trên `jobWorker()`. Dự đoán `proxy.target.after-refresh=1` vì eager consumer yêu cầu target thật. Đây là bài tập quan trọng để phân biệt lazy target và lazy injection point.

### Bài 5 — Đổi JobWorker thành concrete final class

Cho `JobConsumer` constructor nhận concrete `RealWorker` đã khai báo `final` rồi đặt `@Lazy` trên parameter. Cân nhắc vì sao class-based proxy có thể không tạo được và thử chuyển sang interface `JobWorker` hoặc `ObjectProvider<RealWorker>`. Đừng dùng final type như một mặc định khi thiết kế target cần proxy.

### Bài 6 — Sử dụng ObjectProvider

Đổi `JobConsumer` nhận `ObjectProvider<JobWorker>`. Gọi `getObject().work()` trong `run()`, quan sát target creation timing. Thử `getIfAvailable()` cho optional target để hiểu semantics khi bean không tồn tại.

### Bài 7 — Đo readiness

Thêm một critical bean mô phỏng kiểm tra cấu hình ở startup và một optional bean khởi tạo đắt tiền. Chọn bean nào phải eager để fail-fast, bean nào có thể lazy, rồi viết integration test xác nhận lỗi xuất hiện đúng thời điểm dự định.

### Bài 8 — Prototype

Đổi `jobWorker` thành prototype đồng thời vẫn dùng proxy hoặc ObjectProvider. Theo dõi số constructor calls qua nhiều lần use. Phân biệt lifetime singleton proxy/consumer với các target instances theo scope.

## 22. Câu hỏi ôn tập có đáp án

**Câu 1.** Mặc định `ApplicationContext` thường tạo beans nào ngay trong startup?

**Đáp:** Các singleton non-lazy thông thường; còn scopes đặc biệt và infrastructure có quy tắc riêng.

**Câu 2.** `@Lazy` trên `@Bean` method có tạo bean vào thread khác không?

**Đáp:** Không. Nó hoãn pre-instantiation cho đến khi bean được thực sự yêu cầu.

**Câu 3.** `lazy-init="true"` là thuộc tính XML của class Java không?

**Đáp:** Không. Nó là metadata trên `<bean>` XML mà Spring BeanFactory xử lý.

**Câu 4.** Bean `@Lazy` vẫn bị tạo trong refresh có phải Spring sai không?

**Đáp:** Không. Nếu eager singleton cần bean ấy làm dependency, Spring phải tạo target để thỏa dependency.

**Câu 5.** `@Lazy` trên injection point khác trên bean definition thế nào?

**Đáp:** Injection-point `@Lazy` tạo lazy-resolution proxy; bean-definition `@Lazy` ngăn singleton pre-instantiation bình thường. Để hoãn target khi consumer eager, có thể cần cả hai.

**Câu 6.** `@Lazy` trên `@Configuration` ảnh hưởng các `@Bean` methods ra sao?

**Đáp:** Đặt mặc định lazy cho các `@Bean` methods trong class; method `@Lazy(false)` có thể override.

**Câu 7.** `<beans default-lazy-init="true">` có biến mọi bean trong JVM thành lazy không?

**Đáp:** Không. Nó thiết lập default cho definitions được parse trong XML resource tương ứng; những registration sources khác có metadata riêng.

**Câu 8.** Lazy singleton có trở thành prototype không?

**Đáp:** Không. Khi được tạo, singleton vẫn được tái sử dụng trong container.

**Câu 9.** Vì sao `containsBean("lazy")` có thể true mà constructor chưa chạy?

**Đáp:** Bean definition đã đăng ký, còn instance chưa cần tạo.

**Câu 10.** Tại sao lazy proxy không phù hợp để kiểm tra optional dependency bằng `!= null`?

**Đáp:** Proxy có thể được inject dù target vắng; lỗi xuất hiện khi invoke. Dùng `ObjectProvider.getIfAvailable()` nếu cần optional semantics rõ.

**Câu 11.** `@DependsOn` thường làm bean lazy tạo muộn hơn không?

**Đáp:** Không. Nó buộc dependency khởi tạo trước dependent bean, nên có thể kéo lazy bean vào startup.

**Câu 12.** Nếu bean chưa từng được tạo, Spring có gọi destroy callback lên target instance không?

**Đáp:** Không có instance target để destroy. Nếu singleton lazy đã tạo và được quản lý, callback phù hợp có thể chạy khi context đóng.

**Câu 13.** `spring.main.lazy-initialization=true` có chạy trong project chỉ có `spring-context` không?

**Đáp:** Không tự động. Đây là property được Spring Boot xử lý.

**Câu 14.** DeferredImportSelector có cùng nghĩa với @Lazy không?

**Đáp:** Không. DeferredImportSelector liên quan import selection trong configuration parsing; `@Lazy` liên quan bean instantiation.

**Câu 15.** Dùng global lazy có thể gây ảnh hưởng vận hành gì?

**Đáp:** Có thể giảm một phần startup work nhưng trì hoãn lỗi, tăng độ trễ sử dụng đầu, thay cách đánh giá readiness và ảnh hưởng memory footprint sau warm-up.

## 23. Checklist triển khai thực tế

- [ ] Xác định bean nào **không cần** cho startup/health-critical workflows.
- [ ] Với Java bean, đặt `@Lazy` đúng trên definition hoặc `@Configuration` scope.
- [ ] Với XML bean, đặt `lazy-init="true"`; cân nhắc `default-lazy-init` và overrides.
- [ ] Kiểm tra target có bị eager singleton khác cần trực tiếp không.
- [ ] Nếu consumer eager cần dependency lazy, cân nhắc `@Lazy` trên injection point hoặc `ObjectProvider`.
- [ ] Dùng interface/proxy-friendly type khi chọn lazy proxy.
- [ ] Không dùng lazy proxy làm optional dependency existence test.
- [ ] Kiểm tra bean scope trước khi suy luận singleton identity.
- [ ] Không suy luận lazy flag là bảo đảm không ai gọi `getBean()` trong startup.
- [ ] Đảm bảo critical configuration/resources fail-fast khi cần.
- [ ] Kiểm tra initialization/destruction lifecycle với lazy target.
- [ ] Dùng integration test thật để đo trạng thái **sau refresh, trước lookup, sau lookup**.
- [ ] Đo startup, first-use latency và memory dưới workload thực tế.
- [ ] Phân biệt Core `@Lazy`/XML lazy-init với Spring Boot property, background bootstrap và deferred parsing.

## 24. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html): mặc định eager singleton, `@Lazy`, `lazy-init`, `default-lazy-init` và eager dependency.
- [Spring Framework 6.2.19 — Lazy Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/Lazy.html): TYPE/METHOD/CONSTRUCTOR/PARAMETER/FIELD, config-class defaults, lazy-resolution proxies.
- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): `@Bean`, injection-point `@Lazy` và `ObjectProvider`.
- [Spring Framework 6.2 — Using depends-on](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html): phụ thuộc khởi tạo, destroy ordering.
- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html): eager singleton pre-instantiation và graph injection.
- [Spring Framework 6.2 — Java Config Composition](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): `@Lazy`, `@DependsOn` và background initialization options trong Spring 6.2.
- [Spring Boot — SpringApplication Lazy Initialization](https://docs.spring.io/spring-boot/reference/features/spring-application.html): property `spring.main.lazy-initialization`, trade-off startup/first-use.

**Tóm lại:** Spring thường pre-instantiate **non-lazy singleton beans** trong startup. `@Lazy` và XML `lazy-init="true"` trì hoãn **target bean instance creation**, nhưng một dependency từ eager singleton vẫn có thể tạo target sớm. `@Lazy` trên **injection point** tạo lazy-resolution proxy và nên được phân biệt rõ với `@Lazy` trên **bean definition**. Hãy kiểm thử bằng lifecycle/counter, cân nhắc fail-fast, tài nguyên và độ trễ lần dùng đầu trước khi áp dụng lazy trên diện rộng.
