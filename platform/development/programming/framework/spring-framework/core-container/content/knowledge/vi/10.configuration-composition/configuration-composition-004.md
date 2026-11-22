# Nhập cấu hình XML bằng @ImportResource trong Spring Core Container

## Mục tiêu

Spring Framework cho phép ứng dụng khai báo bean bằng **Java configuration** (`@Configuration` và `@Bean`), **component scanning** (`@Component` và các stereotype) hoặc **XML configuration** (`<beans>`, `<bean>`, `<property>`, `<constructor-arg>`). Trong một dự án lâu năm, việc chuyển toàn bộ cấu hình XML sang Java trong một lần có thể không cần thiết hoặc quá rủi ro. Một phần cấu hình cũ vẫn có giá trị, nhất là khi liên quan tới XML namespaces hoặc các integration đã hoạt động ổn định.

Annotation **`@ImportResource`** trong Spring Core Container giải quyết bài toán **dùng cấu hình Java làm điểm vào chính nhưng nhập thêm bean definitions từ tài nguyên XML**:

```java
@Configuration
@ImportResource("classpath:legacy-beans.xml")
public class AppConfig {
    // Có thể khai báo thêm các @Bean methods ở đây.
}
```

Sau khi Spring nạp `AppConfig` vào `AnnotationConfigApplicationContext`, các bean definitions trong `legacy-beans.xml` được đưa vào **cùng BeanFactory/ApplicationContext** với các bean khai báo bằng `@Bean`. Vì cùng container, chúng có thể tham chiếu và được tiêm qua lại theo cơ chế dependency injection của Spring.

Sau bài này bạn sẽ:

1. Hiểu `@ImportResource` làm gì, hoạt động ở giai đoạn nào và khác `@Import` ra sao.
2. Khai báo đúng đường dẫn `classpath:`, `file:` và nhiều tài nguyên XML.
3. Viết XML có `<beans>`, `<bean>`, `<property>`, `<constructor-arg>` và `<alias>` hợp lệ.
4. Tiêm một bean từ XML vào tham số `@Bean` của Java và tham chiếu **ngược lại** từ XML tới Java bean.
5. Dùng XML namespace `context:property-placeholder` với Java `@Value` khi cần.
6. Phân biệt tên bean, alias, số lượng bean độc lập, scope và lifecycle khi kết hợp hai nguồn cấu hình.
7. Chẩn đoán lỗi không tìm thấy XML, sai namespace/schema, thiếu bean hoặc đăng ký trùng.
8. Chuyển dần từ XML sang Java configuration mà vẫn giữ hợp đồng bean names và kiểm thử tương thích.

**Tư tưởng chính:** `@ImportResource` **nhập bean definitions**, không sao chép object, không tạo một container thứ hai và không tự chuyển đổi cú pháp XML thành phương thức `@Bean` trong source code.

## 1. Bối cảnh: tại sao cần nhập XML từ cấu hình Java?

Giả sử hệ thống đã có tài nguyên:

```xml
<!-- src/main/resources/legacy-beans.xml -->
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
          http://www.springframework.org/schema/beans
          https://www.springframework.org/schema/beans/spring-beans.xsd">
    <bean id="legacyClient" class="com.example.legacy.LegacyClient"/>
</beans>
```

Đây là ví dụ **minh họa**: `com.example.legacy.LegacyClient` phải thực sự tồn tại trên classpath để sử dụng.

Đồng thời ứng dụng mới chủ yếu dùng:

```java
@Configuration(proxyBeanMethods = false)
class BillingConfig {
    @Bean
    BillingService billingService(LegacyClient legacyClient) {
        return new BillingService(legacyClient);
    }
}
```

Nếu chỉ đăng ký `BillingConfig` mà chưa nạp XML, Spring không biết bean `legacyClient` nằm ở đâu. Có thể giải quyết bằng cách nhập XML:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-beans.xml")
class BillingConfig {
    @Bean
    BillingService billingService(LegacyClient legacyClient) {
        return new BillingService(legacyClient);
    }
}
```

Ở đây `@ImportResource` giữ nguyên cấu hình XML cũ trong khi service mới tiếp tục dùng **dependency injection qua tham số phương thức `@Bean`**. Không cần tạo `LegacyClient` thêm một lần trong Java chỉ vì nó đến từ XML.

### Một BeanFactory, nhiều nguồn metadata

```text
             AnnotationConfigApplicationContext
                          |
                Đăng ký AppConfig
                          |
           +--------------+--------------+
           |                             |
    @Bean methods Java          @ImportResource(...)
           |                             |
    BeanDefinition A              Đọc legacy-beans.xml
    BeanDefinition B                       |
           |                        BeanDefinition C
           |                        BeanDefinition D
           +--------------+--------------+
                          |
                        BeanFactory
                          |
             Dependency resolution
               theo type / name / qualifier
                          |
                    Managed beans
```

Mỗi bean definition sau cùng được Spring xử lý theo scope, lifecycle, autowiring, post-processors, factory methods, metadata và các điều kiện liên quan. **Nguồn khai báo** là Java hay XML không tự quyết định bean đó có được singleton, inject, proxy hay cleanup như bean bình thường hay không.

## 2. @ImportResource nằm ở đâu và có những thuộc tính nào?

Annotation `@ImportResource` thuộc:

```java
import org.springframework.context.annotation.ImportResource;
```

Đây là annotation cấp **TYPE** — thường đặt trên class `@Configuration`:

```java
@Configuration
@ImportResource("classpath:legacy-beans.xml")
public class AppConfig {
}
```

Ý nghĩa chính của các thuộc tính:

| Thuộc tính | Mục đích | Ví dụ |
| --- | --- | --- |
| `value` | Danh sách resource locations cần nhập; là alias với `locations` | `@ImportResource("classpath:legacy.xml")` |
| `locations` | Tên tường minh của danh sách resource locations | `@ImportResource(locations = {"classpath:a.xml", "classpath:b.xml"})` |
| `reader` | Chọn implementation `BeanDefinitionReader` chuyên dụng khi cần | `@ImportResource(reader = XmlBeanDefinitionReader.class, locations = "classpath:legacy.xml")` |

Trong trường hợp XML thông thường, **không phải chỉ định `reader`**: Spring sử dụng `XmlBeanDefinitionReader` mặc định cho XML. Theo API 6.2, tài nguyên có đuôi `.groovy` được xử lý bằng reader phù hợp cho Groovy khi có hạ tầng tương ứng; đó là khả năng của annotation, không có nghĩa mọi ứng dụng Spring mặc định cần cấu hình Groovy.

`value` và `locations` là **hai tên thay thế của cùng danh sách tài nguyên**, không phải hai nguồn nhập độc lập cần cộng lại. Hãy chọn **một cách viết** để tránh khó đọc.

### Import một file XML

```java
@ImportResource("classpath:legacy-beans.xml")
```

### Import nhiều file XML

```java
@ImportResource(locations = {
    "classpath:legacy/repositories.xml",
    "classpath:legacy/integrations.xml"
})
```

Mỗi file được đọc và đóng góp bean definitions vào cùng container. **Không tạo hai contexts** chỉ vì có hai file.

### Có cần @Configuration không?

Annotation được thiết kế chủ yếu để kết hợp cùng một class cấu hình được Spring xử lý. Cách dễ đọc, dễ kiểm chứng nhất là:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-beans.xml")
class RootConfig {
}
```

Đăng ký `RootConfig.class` vào `AnnotationConfigApplicationContext` hoặc import từ một configuration class khác. Việc tự viết `new RootConfig()` trong một Java method **không kích hoạt** Spring import XML; annotation phải được Spring configuration processing nhận diện.

## 3. @ImportResource khác @Import, <import/> và ClassPathXmlApplicationContext

Dù tên đều có chữ *import*, phạm vi rất khác nhau.

| Cơ chế | Nhận đối số gì? | Vai trò |
| --- | --- | --- |
| `@Import(OtherConfig.class)` | Class/configuration/component/selector theo hợp đồng annotation | Nhập cấu hình Java hoặc thành phần Spring liên quan |
| `@ImportResource("classpath:legacy.xml")` | Resource location string | Nhập bean definitions từ XML hoặc định dạng được reader hỗ trợ |
| XML `<import resource="other.xml"/>` | Đường dẫn tài nguyên nằm trong XML | XML nhập thêm một file cấu hình XML khác |
| `ClassPathXmlApplicationContext("legacy.xml")` | Tên resource XML | Tạo context theo lối XML-centric |
| `@ComponentScan(basePackages = "...")` | Tên package/class marker | Quét các class mang stereotype |

Ví dụ kết hợp Java config khác và XML:

```java
@Configuration(proxyBeanMethods = false)
@Import(RepositoryJavaConfig.class)
@ImportResource("classpath:legacy-integration.xml")
class ApplicationConfig {
}
```

Đây là **đoạn minh họa**; `RepositoryJavaConfig` phải là class hợp lệ trong dự án. `@Import` không thay `@ImportResource` khi đối số là file XML. Ngược lại, `@ImportResource` không có nhiệm vụ quét package Java để tìm các `@Service`.

### Hai hướng kết hợp Java và XML

Spring hỗ trợ cả hai cách tổ chức:

- **Java-centric:** Khởi động bằng `AnnotationConfigApplicationContext(AppConfig.class)` rồi `@ImportResource` nạp các file XML cần giữ lại.
- **XML-centric:** Khởi động bằng `ClassPathXmlApplicationContext`, rồi XML khai báo/import class `@Configuration` thích hợp và bật infrastructure annotation processing khi cần.

Bài này tập trung **Java-centric** đúng yêu cầu “Nhập cấu hình XML bằng `@ImportResource`”. Không cần tự tạo cả hai loại context cho một ứng dụng đơn giản rồi chuyển object qua lại.

## 4. Đường dẫn tài nguyên: classpath:, file: và nhiều files

Vì `@ImportResource` yêu cầu **resource locations**, đường dẫn phải khớp nơi XML thật sự được đóng gói/chạy.

### 4.1. classpath: là lựa chọn thông dụng

Với Maven layout:

```text
my-app/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/AppConfig.java
        └── resources/
            ├── legacy-beans.xml
            └── legacy/
                └── adapters.xml
```

Maven đưa tài nguyên trong `src/main/resources` vào runtime classpath. Vì vậy:

```java
@ImportResource("classpath:legacy-beans.xml")
```

tìm file ở gốc classpath, còn:

```java
@ImportResource("classpath:legacy/adapters.xml")
```

tìm file ở thư mục `legacy` bên trong classpath.

**Sai phổ biến:** Viết `@ImportResource("src/main/resources/legacy-beans.xml")` rồi nghĩ đây là đường dẫn luôn đúng khi đóng gói JAR. Đường dẫn source tree không phải resource location ổn định ở runtime.

`classpath:/legacy-beans.xml` cũng thường được dùng để nhấn mạnh gốc classpath. Khi app được đóng gói, Spring tìm trên classpath, không phụ thuộc IDE đang mở thư mục nào.

### 4.2. file: trỏ đến filesystem

```java
@ImportResource("file:/opt/myapp/config/legacy-beans.xml")
```

`file:` dùng đường dẫn ngoài JAR, hữu ích cho cấu hình do deployment quản lý. Cần bảo đảm:

- File tồn tại ở nơi **máy/container runtime** có thể đọc.
- Đường dẫn phù hợp hệ điều hành và volume mount.
- Quyền truy cập, versioning, integrity và cách rollout được kiểm soát.
- Đừng nhúng secrets hay dựa vào file ngoài mà không có chính sách bảo mật, cấu hình và lỗi rõ ràng.

Đoạn này là minh họa; file `/opt/myapp/config/legacy-beans.xml` không thuộc dự án runnable ở mục 7.

### 4.3. classpath*: và resource patterns

Spring có cơ chế `ResourcePatternResolver` hỗ trợ patterns như `classpath*:` trong một số ngữ cảnh. Khi dùng resource patterns cần hiểu số lượng match có thể khác giữa IDE, JAR và nhiều dependency có resource trùng tên.

Ví dụ dạng minh họa:

```java
@ImportResource("classpath*:META-INF/spring/legacy-context.xml")
```

Có thể nhận nhiều resource trên classpath phù hợp theo pattern resolver. **Đừng** áp dụng wildcard rộng chỉ để chắc chắn “sẽ tìm được XML”: import nhiều bản XML ngoài ý muốn có thể gây duplicate bean definitions hoặc tạo các component không được phép. Với một file rõ ràng, `classpath:legacy-beans.xml` thường đơn giản và an toàn hơn.

### 4.4. Resource không tìm thấy sẽ làm gì?

Nếu location không tồn tại/không đọc được, quá trình parse/register XML có thể ném exception và context không khởi động thành công. `@ImportResource` **không có nghĩa** XML là optional. Không giả định thiếu file sẽ bị bỏ qua như một dependency tùy chọn.

Đừng bắt mọi lỗi startup rồi tiếp tục ứng dụng trong trạng thái cấu hình thiếu; hãy xác định đúng file và cách đóng gói.

## 5. Cách khai báo XML cơ bản để nhập

Một XML Spring hiện đại thường bắt đầu bằng namespace và schema như sau:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="legacyFormatter"
          class="com.example.legacy.LegacyFormatter">
        <property name="prefix" value="LEGACY:"/>
    </bean>
</beans>
```

Đây là ví dụ **minh họa**: class `com.example.legacy.LegacyFormatter` cần có constructor/property setter tương ứng. Đối với bean do XML tạo:

- `id` thường là bean name chính.
- `class` là **fully qualified Java class name** mà classloader phải tìm được.
- `<property name="prefix" value="..."/>` thiết lập thuộc tính qua setter/JavaBean property phù hợp.
- `<constructor-arg>` truyền tham số constructor.
- `ref="otherBean"` tham chiếu bean definition có tên tương ứng trong **cùng container**, dù bean kia được khai báo bằng Java.
- XML có thể khai báo `scope`, `init-method`, `destroy-method` theo lifecycle mong muốn.

Một bean XML bình thường không cần đồng thời gắn `@Component` lên Java class; nếu đã được khai báo bằng `<bean>`, Spring có bean definition từ XML.

### Dùng constructor-arg thay property

```xml
<bean id="legacyProcessor"
      class="com.example.legacy.LegacyProcessor">
    <constructor-arg ref="legacyFormatter"/>
</bean>
```

Đây cũng là đoạn minh họa, yêu cầu `LegacyProcessor` có constructor phù hợp. Chọn constructor injection khi dependency bắt buộc; property injection hữu ích cho những thư viện JavaBean cũ có setter, nhưng không nên dùng nó chỉ vì XML trông ngắn hơn.

### Alias trong XML

```xml
<alias name="legacyFormatter" alias="oldFormatter"/>
```

Alias `oldFormatter` trỏ tới **cùng bean definition** với `legacyFormatter`. Nó **không tạo** một bean `LegacyFormatter` mới. Với singleton mặc định, gọi hai tên cho cùng reference. Đừng nhầm alias với hai thẻ `<bean>` có `id` khác nhau, vốn tạo hai definitions độc lập.

## 6. Bean XML và Java tương tác hai chiều như thế nào?

Khi import XML vào cùng một `AnnotationConfigApplicationContext`, dependency resolution không chia thành “vùng Java” và “vùng XML”.

### 6.1. Java @Bean nhận dependency do XML khai báo

Ví dụ XML:

```xml
<bean id="legacyGateway"
      class="com.example.gateway.LegacyGateway"/>
```

Còn Java config:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-gateway.xml")
class PaymentConfig {

    @Bean
    PaymentService paymentService(LegacyGateway legacyGateway) {
        return new PaymentService(legacyGateway);
    }
}
```

Đây là minh họa cần các class và file thực. Spring tìm bean `LegacyGateway` trong BeanFactory và truyền vào factory method `paymentService`. Không cần `new LegacyGateway()` trong Java config.

Nếu có nhiều bean `LegacyGateway` cùng type, dependency có thể nhập nhằng; chọn bằng `@Qualifier`/`@Primary` hoặc cấu trúc interface rõ. XML bean có thể dùng `primary="true"` hoặc `autowire-candidate` trong những tình huống tương ứng.

### 6.2. XML ref tới bean được khai báo trong Java

Java config:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-dashboard.xml")
class AppConfig {

    @Bean("reportService")
    ReportService reportService() {
        return new ReportService();
    }
}
```

XML:

```xml
<bean id="legacyDashboard"
      class="com.example.legacy.LegacyDashboard">
    <property name="reportService" ref="reportService"/>
</bean>
```

Spring sẽ phân giải `ref="reportService"` trong cùng BeanFactory. Điều kiện là bean `reportService` phải tồn tại và tương thích với property setter `setReportService(...)`. Cấu hình Java được import XML thông qua `@ImportResource`, nhưng bean definitions vẫn được xử lý chung trong quá trình dựng context; XML không bắt buộc phải xuất hiện sau bean Java trong source để được resolve.

**Nhớ:** `ref` tham chiếu **tên bean**, khác với `value` truyền chuỗi literal. Đừng viết `value="reportService"` nếu property mong một instance `ReportService`.

### 6.3. Khai báo dependency bằng type hay name?

- Trong Java, factory method parameter như `ReportService service` biểu diễn dependency theo **kiểu**, có thể kết hợp qualifier.
- Trong XML, `ref="reportService"` biểu diễn dependency theo **tên bean**.
- Cùng một bean có thể được lấy bằng cả type và name, nếu lựa chọn ứng viên không nhập nhằng.
- Alias trong XML có thể cung cấp một tên tương thích với code cũ mà vẫn cùng bean.

Đây là một lý do cần giữ **bean names ổn định** khi di trú cấu hình XML sang Java: consumer XML cũ thường tham chiếu tên tường minh.

## 7. Dự án runnable Java 17: XML ↔ Java trong một ApplicationContext

Ví dụ này có thể chạy với **JDK 17+, Maven và Spring Framework 6.2**. Nó không dùng database, mạng hay Spring Boot.

Chúng ta sẽ tạo:

1. Bean `xmlStore` và `formatter` bằng XML.
2. Alias XML `legacyStore` trỏ tới `xmlStore`.
3. Bean `messageService` bằng `@Bean`, nhận `MessageStore` và `PrefixFormatter` từ XML.
4. Bean `xmlDashboard` bằng XML, có property `messageService` tham chiếu ngược tới bean được tạo từ Java.
5. ApplicationContext chỉ được tạo **một lần** qua `AnnotationConfigApplicationContext`.

### 7.1. Cấu trúc thư mục

```text
import-resource-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── ImportResourceDemo.java
        └── resources/
            └── legacy-beans.xml
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>import-resource-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. Mã Java đầy đủ

Tạo file `src/main/java/demo/ImportResourceDemo.java`:

```java
package demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportResource;

public class ImportResourceDemo {

    public interface MessageStore {
        String persist(String formatted);
    }

    // Class công khai, static để Spring XML instantiation không
    // cần instance của outer class ImportResourceDemo.
    public static class XmlMessageStore implements MessageStore {

        public XmlMessageStore() {
        }

        @Override
        public String persist(String formatted) {
            return "stored[" + formatted + "]";
        }
    }

    public static class PrefixFormatter {
        private String prefix;

        public PrefixFormatter() {
        }

        public void setPrefix(String prefix) {
            this.prefix = prefix;
        }

        public String format(String message) {
            return prefix + message;
        }
    }

    public static class MessageService {
        private final MessageStore store;
        private final PrefixFormatter formatter;

        public MessageService(MessageStore store,
                              PrefixFormatter formatter) {
            this.store = store;
            this.formatter = formatter;
        }

        public String submit(String message) {
            return store.persist(formatter.format(message));
        }
    }

    public static class XmlDashboard {
        private MessageService messageService;

        public XmlDashboard() {
        }

        public void setMessageService(MessageService service) {
            this.messageService = service;
        }

        public String status() {
            return "xml->java:" + messageService.submit("dashboard");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ImportResource("classpath:legacy-beans.xml")
    public static class AppConfig {

        @Bean
        public MessageService messageService(
                @Qualifier("xmlStore") MessageStore store,
                PrefixFormatter formatter) {
            return new MessageService(store, formatter);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            System.out.println("xmlBean=" +
                    context.containsBean("xmlStore"));
            System.out.println("javaBean=" +
                    context.containsBean("messageService"));
            System.out.println("aliasSame=" +
                    (context.getBean("xmlStore") ==
                     context.getBean("legacyStore")));

            MessageService service =
                    context.getBean(MessageService.class);
            XmlDashboard dashboard =
                    context.getBean(XmlDashboard.class);

            System.out.println("service=" +
                    service.submit("order-42"));
            System.out.println("dashboard=" +
                    dashboard.status());
            System.out.println("storeBeanCount=" +
                    context.getBeanNamesForType(MessageStore.class).length);
        }
    }
}
```

Giải thích ngắn về Java file:

- `XmlMessageStore` và `PrefixFormatter` là **public static nested classes**. Trong Spring XML, tên binary class của chúng chứa ký tự `$`. Việc dùng `public static` tránh cần tạo outer instance khi XML instantiate object.
- `@ImportResource` đặt trên `AppConfig`. `AnnotationConfigApplicationContext` nạp class này, từ đó xử lý thêm XML.
- `messageService(...)` nhận hai dependency **do Spring cung cấp**; `@Qualifier("xmlStore")` thể hiện rõ bean XML cần lấy.
- `proxyBeanMethods=false` hoàn toàn phù hợp vì method `@Bean` không gọi trực tiếp một `@Bean` method khác.
- `XmlDashboard` có setter vì ví dụ chủ đích minh họa **property injection từ XML tới bean Java**; ở code nghiệp vụ mới, constructor injection thường tốt hơn nếu dependency bắt buộc.

### 7.4. XML khai báo hai bean và tham chiếu trở lại Java

Tạo file `src/main/resources/legacy-beans.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- XML-defined bean, được Java @Bean inject theo type + qualifier. -->
    <bean id="xmlStore"
          class="demo.ImportResourceDemo$XmlMessageStore"/>

    <!-- Bí danh tương thích cho cùng một bean. -->
    <alias name="xmlStore" alias="legacyStore"/>

    <!-- Setter property injection vào bean được định nghĩa bằng XML. -->
    <bean id="formatter"
          class="demo.ImportResourceDemo$PrefixFormatter">
        <property name="prefix" value="XML:"/>
    </bean>

    <!-- XML-defined bean tham chiếu ngược Java @Bean messageService. -->
    <bean id="xmlDashboard"
          class="demo.ImportResourceDemo$XmlDashboard">
        <property name="messageService" ref="messageService"/>
    </bean>

</beans>
```

**Quan trọng khi copy code:**

- Tên XML class dùng `demo.ImportResourceDemo$XmlMessageStore` chứ không dùng `demo.ImportResourceDemo.XmlMessageStore`. Dấu `$` là cách JVM định danh nested class trong tên binary class.
- XML được lưu tại **`src/main/resources/legacy-beans.xml`**, tương ứng trực tiếp với `classpath:legacy-beans.xml`.
- `<property name="prefix" value="XML:"/>` truyền **chuỗi** cho setter `setPrefix`.
- `<property name="messageService" ref="messageService"/>` yêu cầu Spring tìm **bean Java có tên `messageService`**, không phải chuỗi “messageService”.
- `legacyStore` là alias của `xmlStore`. Hai tên đều được chấp nhận khi tra cứu bean singleton.

### 7.5. Lệnh chạy

Từ thư mục dự án chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ImportResourceDemo
```

Yêu cầu JDK 17+ và Maven. Những dòng **do chương trình tự in ra** (không tính thông điệp/log Maven hoặc Spring):

```text
xmlBean=true
javaBean=true
aliasSame=true
service=stored[XML:order-42]
dashboard=xml->java:stored[XML:dashboard]
storeBeanCount=1
```

### 7.6. Tại sao output đúng?

**`xmlBean=true`:** `xmlStore` được Spring đọc từ `legacy-beans.xml` khi xử lý `@ImportResource`. Nó là bean definition trong cùng context.

**`javaBean=true`:** `messageService` được đóng góp bởi Java `@Bean MessageService messageService(...)`; tên mặc định là tên method.

**`aliasSame=true`:** XML `<alias name="xmlStore" alias="legacyStore"/>` thêm một **tên khác** cho cùng singleton. Hai lời gọi `getBean` trả cùng reference.

**`service=stored[XML:order-42]`:** Java bean `MessageService` nhận `PrefixFormatter` có prefix `XML:` từ XML property injection. Service format `order-42` thành `XML:order-42` rồi gọi bean store, trả về `stored[XML:order-42]`.

**`dashboard=xml->java:stored[XML:dashboard]`:** Bean `xmlDashboard` được định nghĩa bằng XML, nhưng property `messageService` tham chiếu bean Java. Method `status()` gọi service được inject để tạo chuỗi có tiền tố `xml->java:`.

**`storeBeanCount=1`:** `getBeanNamesForType(MessageStore.class)` trả danh sách **bean definitions thực** theo type. Alias `legacyStore` không phải một `MessageStore` bean thứ hai. Không có một `new XmlMessageStore()` khác được khai báo trong Java.

### 7.7. Những thay đổi có thể tự thử

1. **Đổi tên alias** `legacyStore` thành `oldStore` trong XML, sửa lời gọi `getBean("oldStore")` rồi chạy. Tên chính `xmlStore` vẫn không đổi.
2. **Đổi prefix** từ `XML:` thành `LEGACY:` ở XML. Hai dòng `service` và `dashboard` đổi theo; không phải sửa Java factory method.
3. **Xóa `@ImportResource`** khỏi `AppConfig`. Context sẽ không tìm được các dependency XML cần thiết cho `messageService`, nên quá trình tạo bean sẽ thất bại, thay vì in output như trên.
4. **Đổi XML `ref="messageService"` thành `ref="unknownService"`**. Spring không có bean với tên đó và báo lỗi resolution. Đây là ví dụ vì sao bean names là hợp đồng giữa Java và XML.
5. **Thêm XML bean thứ hai cũng implement `MessageStore`**. Parameter `MessageStore` có `@Qualifier("xmlStore")` nên vẫn chọn bean phù hợp; nếu bỏ qualifier và không có ứng viên thắng, Spring có thể báo `NoUniqueBeanDefinitionException`.

## 8. Cấu hình placeholder từ XML và @Value trong Java

Một ứng dụng có thể giữ cấu hình property placeholder trong XML nhưng dùng giá trị ấy tại Java `@Configuration`. Đây là trường hợp Spring tài liệu chính thức nêu để minh họa `@ImportResource`.

Ví dụ một tài nguyên `properties-config.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/context
         https://www.springframework.org/schema/context/spring-context.xsd">

    <context:property-placeholder
            location="classpath:application-legacy.properties"/>
</beans>
```

File `src/main/resources/application-legacy.properties`:

```properties
app.label=legacy-enabled
app.retryLimit=3
```

Java config:

```java
// Đoạn minh họa: CustomClient là một class ứng dụng.
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:properties-config.xml")
class PropertyConfig {

    @Bean
    CustomClient customClient(
            @Value("${app.label}") String label,
            @Value("${app.retryLimit}") int retryLimit) {
        return new CustomClient(label, retryLimit);
    }
}
```

Cần import `org.springframework.beans.factory.annotation.Value` và các annotation `Configuration`, `ImportResource`, `Bean`. Đây là **đoạn mở rộng minh họa**, không thuộc chương trình chạy độc lập ở mục 7. Sau khi import XML, `<context:property-placeholder>` đăng ký hạ tầng xử lý property placeholders phù hợp để `@Value` đọc giá trị.

**Điểm cần chú ý:**

- `${app.label}` là cú pháp placeholder của Spring, **không phải** cú pháp nội suy biến của Java.
- Spring đọc file từ runtime classpath. Nếu file missing, placeholder chưa giải quyết hoặc kiểu không chuyển được, cấu hình có thể lỗi tùy context/policy xử lý placeholder.
- `retryLimit` ở Java có kiểu `int`; Spring sẽ chuyển chuỗi property `3` thành số khi cơ chế conversion phù hợp.
- Nếu ứng dụng đã có `PropertySourcesPlaceholderConfigurer` hoặc một cơ chế property resolver khác, tránh vô tình đăng ký nhiều processors có chính sách xung đột.
- Trong Spring Framework thuần cũng có thể khai báo property source hoàn toàn bằng Java, không nhất thiết giữ XML nếu chỉ còn một property file đơn giản.

### @PropertySource có thay được @ImportResource không?

`@PropertySource("classpath:application.properties")` thêm property source vào Spring Environment; nó **không** tự đọc các `<bean>` definitions từ XML. Nếu mục tiêu duy nhất là đọc key-value, `@PropertySource`/`Environment` hoặc cấu hình Boot tương ứng có thể đủ. Nếu mục tiêu là giữ bean definitions hay XML namespaces, dùng `@ImportResource`.

## 9. Nạp XML namespace: khi nào Java-centric vẫn hợp lý?

Một số integration lâu năm hoặc thư viện third-party cung cấp XML namespaces để khai báo hạ tầng ngắn gọn, ví dụ `<context:property-placeholder>`. Spring có thể xử lý namespace handlers khi JAR chứa các metadata/schema handlers tương ứng được đưa lên classpath.

`@ImportResource` cho phép ứng dụng Java-centric chỉ nhập những tài nguyên XML này:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource({
    "classpath:legacy/namespace-config.xml",
    "classpath:legacy/adapters.xml"
})
public class ApplicationConfig {
}
```

Đây là minh họa nhiều file. Không cần viết lại mọi XML namespace trước khi bắt đầu dùng Java configuration.

Tuy nhiên:

- XML namespace phải được khai báo đúng `xmlns` và `xsi:schemaLocation`.
- Namespace handler/schema tương ứng phải được cung cấp bởi dependencies hợp lệ trên runtime classpath.
- Một namespace không được hỗ trợ hoặc một version API đã bị loại bỏ có thể gây lỗi parse XML.
- Di trú nên giảm dần XML đã lỗi thời, không biến `@ImportResource` thành cơ chế che mã cấu hình mà nhóm không còn hiểu rõ.

Có thể giữ những phần XML đang ổn định lâu dài nếu phù hợp chi phí/bảo trì; không có yêu cầu rằng mọi Spring Framework project phải chuyển 100% sang annotations.

## 10. Bean names và aliases khi XML và @Bean cùng container

Bean names là hợp đồng đặc biệt quan trọng trong cấu hình lai.

### Java @Bean có tên mặc định

```java
@Bean
PaymentService paymentService(PaymentGateway gateway) {
    return new PaymentService(gateway);
}
```

Tên bean mặc định là `paymentService`. XML có thể tham chiếu:

```xml
<property name="paymentService" ref="paymentService"/>
```

Nếu đổi Java method `paymentService()` thành `createService()` mà không đặt tên tường minh, bean name thay đổi. XML cũ có thể bị hỏng dù type Java không đổi.

### Giữ bean name tường minh khi refactor

```java
@Bean("paymentService")
PaymentService createPaymentService(PaymentGateway gateway) {
    return new PaymentService(gateway);
}
```

Tên chính vẫn là `paymentService` trong khi tên factory method thay đổi. Đây là phương án hữu ích cho quá trình chuyển đổi cấu hình mà XML consumer còn tồn tại.

### Bean-name aliases ở hai định dạng

Java:

```java
@Bean(name = {"paymentService", "legacyPaymentService"})
PaymentService createPaymentService(PaymentGateway gateway) {
    return new PaymentService(gateway);
}
```

XML:

```xml
<alias name="paymentService" alias="oldPaymentService"/>
```

Hai ví dụ cho thấy nhiều tên có thể chỉ về một bean. Không nên tự động dùng **cả hai** mà không kiểm tra xung đột. Alias giải quyết tương thích tên; nó không phải phương tiện tạo hai implementations hoặc copy trạng thái của bean.

### Tránh trùng tên giữa XML và Java

Nếu XML đăng ký:

```xml
<bean id="paymentService" class="com.example.LegacyPaymentService"/>
```

và Java cũng đăng ký `@Bean("paymentService")`, hai definitions tranh cùng tên. Hành vi cụ thể tùy container và chính sách bean definition overriding; ứng dụng có thể lỗi hoặc một definition thay definition khác theo rules hiện hành. **Đừng dựa vào thứ tự đọc file để cố tình override** mà chưa cấu hình chính sách rõ và chưa test.

Với Spring Boot, mặc định overriding có thể bị từ chối; với plain Spring Framework, BeanFactory có các cờ điều khiển overriding. Hãy coi trùng tên không chủ đích là **lỗi thiết kế cần giải quyết**, thay vì mặc định là “Java luôn ghi đè XML”.

## 11. Scope, lazy bean và lifecycle trong cấu hình lai

Một bean được khai báo từ XML vẫn là bean bình thường của Spring:

```xml
<bean id="client"
      class="com.example.LegacyClient"
      scope="singleton"
      lazy-init="true"
      init-method="initialize"
      destroy-method="shutdown"/>
```

Các metadata trong ví dụ trên có ý nghĩa tương ứng:

- `scope="singleton"`: một managed instance trong phạm vi BeanFactory.
- `lazy-init="true"`: cố trì hoãn tạo singleton cho tới khi có nhu cầu; eager dependency có thể vẫn khiến nó được tạo sớm.
- `init-method="initialize"`: callback khởi tạo khi Spring tạo managed bean.
- `destroy-method="shutdown"`: callback cleanup cho bean phù hợp khi container hủy, thường là lúc close context đối với singleton.

Một bean tạo bằng Java `@Bean` cũng có thể dùng `@Scope`, `@Lazy`, `initMethod`/`destroyMethod`. Không có một bộ quy tắc lifecycle tách biệt chỉ vì bean đến từ XML.

### Nhận dependency XML qua parameter là an toàn

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-beans.xml")
class ServiceConfig {

    @Bean
    ModernService modernService(LegacyClient client) {
        return new ModernService(client);
    }
}
```

Cách này để **BeanFactory** xử lý scope và lifecycle của `LegacyClient`. Không cần và không nên viết `new ClassPathXmlApplicationContext(...)` bên trong `@Bean modernService()` để lấy client, vì như vậy bạn tạo một context **thứ hai** với singleton/lifecycle riêng, dễ leak và gây khác bean identity.

### Prototype và bean được inject vào singleton

Nếu XML bean là `scope="prototype"` nhưng Java singleton service nhận nó qua constructor/factory parameter một lần, service thường giữ reference tới prototype đã được tạo tại thời điểm inject. Điều này không có nghĩa service sẽ tự được inject prototype mới mỗi request. Nếu cần lấy bean theo từng lượt, cân nhắc `ObjectProvider<LegacyClient>` hoặc factory hợp lý.

### Cleanup

Khi tạo `AnnotationConfigApplicationContext` bằng Java, hãy đóng context:

```java
try (var context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Dùng các bean từ XML và Java.
}
```

Context đóng sẽ kích hoạt cleanup/lifecycle callbacks cho các managed singleton phù hợp. Với prototype, Spring không mặc định quản lý destruction giống singleton sau khi cấp object cho client.

## 12. XML không thể cứu một class Java chưa có trên classpath

`@ImportResource` đọc **metadata**, không tải bytecode của những class bị thiếu từ Internet và không tự thêm Maven dependency.

Nếu XML chứa:

```xml
<bean id="legacyAdapter"
      class="com.vendor.legacy.Adapter"/>
```

nhưng `com.vendor.legacy.Adapter` không có trong runtime dependencies, container có thể báo `CannotLoadBeanClassException` hoặc một bean creation/classloading exception tương ứng. Sửa đường dẫn `@ImportResource` không khắc phục được class missing.

Khi di trú multi-module:

1. Đảm bảo module/JAR có class implementation trên runtime classpath.
2. Đảm bảo XML nằm ở resource path đúng.
3. Đảm bảo XML schema/namespace dependencies tương thích phiên bản Spring hiện tại.
4. Đảm bảo bean names và kiểu property/constructor arguments phù hợp.
5. Test ApplicationContext tạo được cả Java và XML beans.

Đừng chỉ kiểm tra build compile thành công của Java code: XML bean class names là **chuỗi**, lỗi rename package/class đôi khi chỉ xuất hiện khi Spring parse/instantiate context.

## 13. So sánh với những phương án cấu hình khác

| Nhu cầu | Phương án thường phù hợp | Lý do |
| --- | --- | --- |
| Giữ XML cũ, Java là điểm bootstrap chính | `@ImportResource` | Chèn XML bean definitions vào cùng context |
| Import một Java configuration class khác | `@Import` | Type-safe class reference và composition |
| Chỉ đọc properties | `@PropertySource`, `Environment` hoặc cơ chế Boot | Không cần parser XML cho key-value thuần |
| Đăng ký class ứng dụng có stereotype | `@ComponentScan` | Quét package, không cần liệt kê XML bean |
| Đăng ký client third-party bằng builder | `@Bean` | Factory method Java rõ kiểu, tham số |
| XML làm điểm bootstrap chính | `ClassPathXmlApplicationContext` | Hợp với hệ thống XML-centric |
| Chia một file XML thành nhiều modules | XML `<import resource="..."/>` | Composition ngay trong DSL XML |
| Chọn bean cụ thể khi có nhiều type matches | `@Qualifier`/`@Primary` | Giải quyết ambiguity, không quyết định nguồn cấu hình |

Đây là các công cụ **bổ sung**, không phải thứ hạng tốt–xấu tuyệt đối. Một dự án mới có thể không cần XML; một dự án legacy vẫn có thể dùng `@ImportResource` như bước đệm ổn định.

## 14. Di trú từ XML sang Java theo từng bước

Một kế hoạch chuyển đổi an toàn nên đặt trọng tâm vào **hợp đồng container và behavior**, không chỉ đổi cú pháp.

### Bước 1 — Xác định ranh giới XML cần giữ

Ví dụ dự án có ba file:

```text
legacy/
├── repositories.xml
├── integrations.xml
└── properties.xml
```

Phân loại:

- Bean hạ tầng nào cần giữ vì dùng namespace/integration đặc thù?
- Bean nào là class ứng dụng có thể dùng `@Service`/`@Repository` hoặc Java `@Bean` rõ ràng?
- Bean names, aliases, qualifiers và scope nào đang được consumer XML/Java tham chiếu?
- Có tài nguyên/lifecycle nào cần test chính xác không?

Không cần đổi tất cả cùng lúc.

### Bước 2 — Tạo một root Java configuration

```java
@Configuration(proxyBeanMethods = false)
@ImportResource({
    "classpath:legacy/repositories.xml",
    "classpath:legacy/integrations.xml",
    "classpath:legacy/properties.xml"
})
class RootConfig {
}
```

Bây giờ có thể khởi động từ `AnnotationConfigApplicationContext(RootConfig.class)`, trong khi bean definitions cũ vẫn đến từ XML.

### Bước 3 — Chuyển một bean mỗi lần

Giả sử XML có:

```xml
<bean id="catalogRepository"
      class="com.example.catalog.JdbcCatalogRepository"/>
```

Khi chuyển sang Java:

```java
@Bean("catalogRepository")
CatalogRepository catalogRepository(DataSource dataSource) {
    return new JdbcCatalogRepository(dataSource);
}
```

Đây là minh họa; cần các class ứng dụng và `DataSource` có sẵn. **Không để cả XML và Java cùng đăng ký bean name `catalogRepository` trong cùng context** mà chưa có chính sách rõ. Hãy xóa/loại định nghĩa XML đã chuyển trong cùng thay đổi có kiểm chứng.

Điều quan trọng là **giữ đúng bean name** khi các consumer cũ còn tham chiếu `ref="catalogRepository"`.

### Bước 4 — Giữ scope, qualifiers và lifecycle tương đương

Chuyển:

```xml
<bean id="cacheClient"
      class="com.example.CacheClient"
      init-method="connect"
      destroy-method="close"/>
```

thành ý tưởng:

```java
@Bean(name = "cacheClient",
      initMethod = "connect",
      destroyMethod = "close")
CacheClient cacheClient() {
    return new CacheClient();
}
```

Đây là ví dụ cấu trúc, cần class `CacheClient` tương ứng. Nếu bean cũ là prototype, lazy hoặc có property injection/constructor arguments đặc biệt, phải chuyển những metadata này có chủ đích thay vì chỉ copy tên.

### Bước 5 — Kiểm thử context sau mỗi bước

Xác nhận:

- Bean names chính/aliases tồn tại đúng.
- Số lượng bean theo các interface không vô tình tăng.
- Dependency Java ↔ XML còn resolve đúng.
- Init/destroy callbacks không bị gọi hai lần hoặc mất.
- Profiles/properties/conditionals giống yêu cầu môi trường.
- Những class đã được chuyển không còn đăng ký trùng.
- Không có kết nối ngoài hoặc workflow nghiệp vụ vô tình chạy khi test context.

### Bước 6 — Chỉ loại @ImportResource khi không còn lý do

Nếu XML không còn định nghĩa bean cần thiết và không còn XML namespace processor phải giữ, bỏ `@ImportResource` cùng tài nguyên không còn dùng. Nếu ứng dụng vẫn cần một file XML ổn định, giữ nó là một lựa chọn kỹ thuật có thể chấp nhận.

## 15. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| `FileNotFoundException`/`BeanDefinitionStoreException` khi startup | `@ImportResource` trỏ sai classpath/file | Đối chiếu thư mục `src/main/resources` và runtime JAR; sửa location |
| XML parse error hoặc namespace không được nhận diện | Sai `xmlns`, `xsi:schemaLocation`, thiếu dependency cung cấp namespace handler | Sửa schema/namespace và dependency |
| `CannotLoadBeanClassException` | `class="..."` sai package, nested class name hoặc JAR thiếu | Sửa tên fully qualified/binary class và runtime classpath |
| `NoSuchBeanDefinitionException` | XML chưa import, bean Java chưa register, `ref`/qualifier sai | Kiểm tra root `@Configuration` và tên/kiểu bean |
| `UnsatisfiedDependencyException` | Java factory parameter cần bean XML không tồn tại hoặc không phù hợp | Xem bean XML có được đăng ký, đúng exposed type/qualifier không |
| `NoUniqueBeanDefinitionException` | XML và Java đăng ký nhiều beans cùng interface không có ứng viên thắng | `@Qualifier`/`@Primary`/registry phù hợp, loại bean trùng nếu vô tình |
| Bean name collision | XML `id` trùng `@Bean(name=...)` | Đặt tên rõ; di trú cùng lúc bỏ definition cũ |
| `ref="messageService"` không được giải quyết | Bean Java thực tế có tên khác hoặc configuration không được nạp | Giữ explicit name hoặc sửa ref |
| Bean có property nhưng không được set | Sai tên `<property>`/setter hoặc conversion không phù hợp | Kiểm tra JavaBean setter và property type |
| Placeholder `${app.label}` không giải quyết | Không nạp property placeholder config hoặc property file missing | Xác minh `@ImportResource` XML, namespace context và file properties |
| Alias bị coi là bean thứ hai | Nhầm `<alias>` với `<bean>` | Dùng `getBeanNamesForType`/`isAlias` để xác nhận |
| Scope/proxy không như mong đợi | Tự tạo context thứ hai hay tự gọi `new` ngoài container | Giữ một context, lấy managed beans qua DI |
| XML parse thành công nhưng logic không chạy đúng | Mismatched constructor/property types, lifecycle, config values | Integration test behavior thay vì chỉ kiểm tra file tồn tại |
| Test pass trên IDE nhưng lỗi khi đóng gói | Resource path chỉ đúng trong source tree hoặc JAR thiếu XML | Test artifact runtime classpath và cấu hình Maven resource |
| Class service bị đăng ký hai lần | Vừa `@ComponentScan` class, vừa khai báo `<bean>` XML | Giữ một bean definition hoặc đặt tên/qualifier rõ nếu cố ý |
| Security concern khi load XML từ nguồn ngoài | Tài nguyên cấu hình không đáng tin, thay đổi ngoài kiểm soát | Giới hạn đường dẫn và nguồn XML, review triển khai và dependency |

### Quy trình chẩn đoán gọn

1. **Metadata:** `@ImportResource` có nằm trên class cấu hình đã được Spring register/import/scanned đúng không?
2. **Location:** file có thật trên **runtime classpath** hoặc filesystem được cấu hình?
3. **XML:** cú pháp namespace/schema, `class` name, `id`, `ref`, `property` có hợp lệ?
4. **Bean definitions:** bean có được đăng ký không? Có trùng tên hoặc type ambiguity không?
5. **Dependency:** Java parameter và XML `ref` có trỏ đúng type/name không?
6. **Lifecycle/scope:** bean có lazy/prototype/proxy hay init callback cần chú ý không?
7. **Readiness:** resource ngoài đã được cấu hình an toàn chưa? Đừng chạy nghiệp vụ nặng ngay trong XML/Java factory.
8. **Test:** dùng một ApplicationContext thật để xác nhận cả hai chiều wiring và output.

## 16. Kiểm thử cấu hình lai

### 16.1. Không chỉ kiểm tra XML file tồn tại

Một XML hợp lệ về mặt cú pháp có thể chứa class name sai, property setter không có, bean ref thiếu, hoặc một thứ tự khởi tạo gây vòng phụ thuộc. Vì vậy test cần **tạo ApplicationContext** và lấy các bean quan trọng.

Trong dự án mục 7:

```java
// Đoạn kiểm tra bổ sung, đặt bên trong try có context.
if (!context.containsBean("xmlStore")) {
    throw new AssertionError("XML store missing");
}
if (!context.containsBean("messageService")) {
    throw new AssertionError("Java service missing");
}
if (context.getBean("xmlStore") !=
        context.getBean("legacyStore")) {
    throw new AssertionError("Alias must resolve same singleton");
}
if (!"stored[XML:order-42]".equals(
        context.getBean(MessageService.class).submit("order-42"))) {
    throw new AssertionError("Cross-config wiring incorrect");
}
```

Nếu các điều kiện đúng, đoạn assert không in thêm stdout. Đây là **bổ sung tùy chọn**, không nằm trong output mặc định của `main`.

### 16.2. Kiểm tra chiều tham chiếu XML → Java

```java
// Cũng đặt bên trong try có context của mục 7.
String status = context.getBean(XmlDashboard.class).status();
if (!"xml->java:stored[XML:dashboard]".equals(status)) {
    throw new AssertionError("XML reference to Java bean failed");
}
```

Test này xác nhận `<property ... ref="messageService"/>` trong XML tìm đúng bean `@Bean` của Java.

### 16.3. Kiểm tra không đăng ký trùng

```java
// Dùng MessageStore từ ví dụ đầy đủ.
String[] stores = context.getBeanNamesForType(MessageStore.class);
if (stores.length != 1 || !"xmlStore".equals(stores[0])) {
    throw new AssertionError("Unexpected MessageStore definitions");
}
```

Chỉ có một bean `MessageStore` trong ví dụ chính. Nếu sau khi migration một Java `@Bean` mới tạo thêm một `MessageStore`, test sẽ phát hiện ứng viên tăng lên thay vì coi alias là bean thứ hai.

### 16.4. Unit test không cần XML cho logic thuần Java

Việc cấu hình lai không buộc mọi unit test phải đọc XML. `MessageService` chỉ cần `MessageStore` và `PrefixFormatter`; có thể tạo fake implementations và gọi business method bằng Java thuần. Dùng **integration test** để chứng minh Spring wiring và resource import hoạt động, còn unit test để kiểm tra logic của service nhanh và ổn định.

### 16.5. Tự tạo context bằng Java phải đóng context

```java
try (var context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Assertions trên bean XML và bean Java.
}
```

`try-with-resources` giúp gọi `close()` ngay cả khi assert thất bại, giảm rò rỉ tài nguyên ở integration test.

## 17. Bài tập thực hành

### Bài 1 — Import một file

File `src/main/resources/legacy/orders.xml` chứa bean `orderRepository`. Viết annotation trên class `@Configuration` để Spring nhập file đó từ classpath.

**Đáp án:**

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy/orders.xml")
class OrdersConfig {
}
```

Không dùng đường dẫn `src/main/resources/...` trong resource location.

### Bài 2 — Phân biệt @Import và @ImportResource

Bạn có class `MonitoringConfig` chứa `@Bean` methods và file `legacy/metrics.xml` chứa `<bean>` definitions. Nên dùng annotation nào cho mỗi nguồn?

**Đáp án:** `@Import(MonitoringConfig.class)` cho Java class; `@ImportResource("classpath:legacy/metrics.xml")` cho XML file. Có thể dùng cả hai trên cùng root config.

### Bài 3 — Nạp nhiều XML files

Hai resource `legacy/a.xml` và `legacy/b.xml` cùng tồn tại. Viết `@ImportResource` nhập cả hai.

**Đáp án:**

```java
@ImportResource(locations = {
    "classpath:legacy/a.xml",
    "classpath:legacy/b.xml"
})
```

Cả hai đóng góp bean definitions vào cùng context, không có context riêng cho từng file.

### Bài 4 — XML bean → Java @Bean

XML khai báo `<bean id="reportRepository" class="..."/>`. Một Java factory cần instance theo interface `ReportRepository`. Làm sao inject đúng mà không tạo context thứ hai?

**Đáp án:**

```java
@Bean
ReportService reportService(
        @Qualifier("reportRepository") ReportRepository repository) {
    return new ReportService(repository);
}
```

Đây là mẫu minh họa; phải có `ReportRepository`/`ReportService` phù hợp và import `@Qualifier`. Spring dùng BeanFactory hiện tại để resolve dependency, không cần gọi `ClassPathXmlApplicationContext` trong factory.

### Bài 5 — Java @Bean → XML ref

`@Bean("priceCalculator")` tạo bean `PriceCalculator`. XML của `LegacyCheckout` có setter `setPriceCalculator`. Viết property injection tương ứng.

**Đáp án:**

```xml
<property name="priceCalculator" ref="priceCalculator"/>
```

Tên `priceCalculator` phải đúng bean name của Java factory, còn setter phải nhận kiểu tương thích.

### Bài 6 — Alias có tạo bean mới không?

XML:

```xml
<bean id="primaryClient" class="com.example.Client"/>
<alias name="primaryClient" alias="oldClient"/>
```

Có bao nhiêu bean definitions? Với singleton, `getBean("primaryClient") == getBean("oldClient")` là gì?

**Đáp án:** Một bean definition và một alias; hai tên trả cùng singleton reference nên phép so sánh là `true` trong cùng container, nếu bean được tạo thành công.

### Bài 7 — Refactor tên method @Bean

XML cũ tham chiếu `ref="paymentService"`. Java `@Bean PaymentService paymentService()` được đổi tên method thành `createPaymentService()`. Cách nào giữ XML không phải sửa?

**Đáp án:** Dùng `@Bean("paymentService")` trên factory method mới để giữ explicit bean name cũ.

### Bài 8 — Duplicate bean

XML và Java cùng khai báo `id/name="customerRepository"`. Có nên dựa vào “nguồn nào đọc cuối” để chọn implementation mong muốn?

**Đáp án:** Không. Hãy xóa definition cũ khi chuyển, hoặc cấu hình override thật minh bạch với integration test và lý do hợp lệ. Tránh collision không chủ đích.

### Bài 9 — Resource path trong JAR

`@ImportResource("src/main/resources/legacy.xml")` chạy ở thư mục project nhưng lỗi sau khi đóng gói JAR. Sửa thế nào?

**Đáp án:** Đặt file ở `src/main/resources/legacy.xml` và import bằng `@ImportResource("classpath:legacy.xml")` để dùng resource path trên runtime classpath.

### Bài 10 — Placeholder chưa resolve

XML có `<context:property-placeholder location="classpath:settings.properties"/>` và Java có `@Value("${app.timeout}")`. Nhưng bean tạo lỗi vì thiếu property. Kiểm tra những gì?

**Đáp án:** File `settings.properties` có thật trên runtime classpath, key `app.timeout` tồn tại, XML namespace context được khai báo đúng, XML được `@ImportResource` nhập, không có các property processors xung đột, kiểu target có thể convert và cấu hình môi trường đúng.

### Bài 11 — Kết quả chương trình

Trong ví dụ mục 7, vì sao `storeBeanCount=1` dù có hai tên `xmlStore` và `legacyStore`?

**Đáp án:** `legacyStore` chỉ là alias tới `xmlStore`. `getBeanNamesForType(MessageStore.class)` đếm các bean definitions tương thích, không đếm alias như bean độc lập.

### Bài 12 — Chiến lược migration

Ứng dụng còn 50 XML bean definitions nhưng 10 bean đơn giản có thể chuyển sang Java. Hãy nêu trình tự hạn chế regression.

**Đáp án định hướng:** Tạo root Java config có `@ImportResource`; ghi nhận bean names/aliases/scopes/dependencies/lifecycle; chuyển từng nhóm sang `@Bean` hoặc stereotype; xóa definitions XML tương ứng để tránh trùng; giữ tên public khi consumer cũ cần; chạy integration tests sau mỗi bước; chỉ gỡ `@ImportResource` khi không còn XML cần thiết.

## 18. Checklist áp dụng thực tế

- [ ] `@ImportResource` nằm trên class cấu hình **được Spring xử lý**, không phải class không bao giờ được đăng ký.
- [ ] Đường dẫn resource đúng runtime classpath/filesystem và phù hợp khi đóng gói JAR.
- [ ] XML có `<beans>` root, namespaces/schema đúng và bean class names hợp lệ.
- [ ] Các thư viện cung cấp XML namespace handlers có trên classpath.
- [ ] Java `@Bean` và XML `<bean>` không tạo trùng tên/kiểu ngoài ý định.
- [ ] Bean name/alias công khai được giữ tương thích khi refactor/migration.
- [ ] Java factory methods nhận dependency XML qua **method parameters** thay vì tự tạo một ApplicationContext mới.
- [ ] XML `ref` trỏ đúng bean names do Java `@Bean` hoặc các nguồn metadata khác đăng ký.
- [ ] Đã xác nhận `scope`, `lazy-init`, `init/destroy` semantics cho các bean legacy.
- [ ] Placeholder processors/`@Value` hoạt động với property files đúng môi trường.
- [ ] Các bean chưa có trên runtime classpath không bị “che” chỉ nhờ file XML còn tồn tại.
- [ ] Integration test mở một context, kiểm tra hai chiều Java ↔ XML wiring, alias identity và ứng viên theo type.
- [ ] Tài nguyên ngoài/bean lifecycle được cleanup qua context close, không tạo/leak context thứ hai.
- [ ] Sau migration không còn các file XML không được sử dụng hoặc references cũ chưa được sửa.
- [ ] Không đưa tài nguyên XML không tin cậy vào đường nạp cấu hình của hệ thống.

## Tổng kết

`@ImportResource` là cầu nối **Java-centric configuration ↔ XML bean definitions** trong Spring Core Container. Annotation đọc XML resources và nhập bean definitions vào **cùng ApplicationContext**, nhờ đó:

- Java `@Bean` methods có thể nhận dependencies từ XML thông qua dependency injection bình thường.
- XML `<bean>` có thể dùng `ref` để trỏ tới bean do Java `@Bean` khai báo.
- Tên chính, aliases, scope và lifecycle được quản lý bởi cùng BeanFactory.
- Dự án có thể chuyển đổi từ XML sang Java theo từng phần, không cần thay toàn bộ trong một lần.

Hãy dùng resource paths chính xác, giữ public bean-name contracts, tránh duplicate definitions và test cả hai chiều wiring. Khi không còn XML hoặc XML namespace thực sự cần thiết, bạn có thể loại `@ImportResource` và duy trì cấu hình bằng Java thuần.

## Tài liệu Spring chính thức

- [Spring Framework 6.2 — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): mục **Combining Java and XML Configuration**, ví dụ Java-centric `@ImportResource` và XML-centric integration.
- [Spring Framework 6.2 — ImportResource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportResource.html): `value`, `locations`, `reader` và lựa chọn bean definition reader.
- [Spring Framework 6.2 — The IoC Container: XML Bean Definition Basics](https://docs.spring.io/spring-framework/reference/6.2/core/beans/basics.html): cấu trúc `<beans>`/`<bean>`, XML imports và resource locations.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): parameter injection và bean metadata.
- [Spring Framework 6.2 — Using PropertyPlaceholderConfigurer](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-placeholderconfigurer.html): property placeholders và integration.
