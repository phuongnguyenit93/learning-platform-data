# EnvironmentAware, ResourceLoaderAware và MessageSourceAware trong Spring Framework Core Container

## 1. Aware callback là gì và dùng trong tình huống nào?

Spring IoC Container thường truyền dependency cho bean bằng constructor injection, setter injection hoặc khai báo `@Bean`. Ngoài các dependency nghiệp vụ, đôi khi một component **hạ tầng** cần biết môi trường đang chạy, mở resource có đường dẫn được quyết định lúc runtime hoặc tra thông điệp theo ngôn ngữ của người dùng. Spring hỗ trợ nhóm callback interface có hậu tố **Aware** để container chủ động cung cấp những đối tượng framework tương ứng.

Ba interface của bài này:

| Interface | Method callback | Đối tượng Spring cung cấp | Mục đích |
| --- | --- | --- | --- |
| `EnvironmentAware` | `void setEnvironment(Environment environment)` | `org.springframework.core.env.Environment` | Đọc properties, active/default profiles, kiểm tra profiles |
| `ResourceLoaderAware` | `void setResourceLoader(ResourceLoader resourceLoader)` | `org.springframework.core.io.ResourceLoader` | Resolve URI/đường dẫn thành `Resource` (classpath, file, URL…) |
| `MessageSourceAware` | `void setMessageSource(MessageSource messageSource)` | `org.springframework.context.MessageSource` | Tra cứu thông điệp, tham số và locale (i18n) |

Các interface này đều thuộc package `org.springframework.context` và kế thừa marker interface `org.springframework.beans.factory.Aware`. Marker `Aware` **không tự chứa logic**: phải có Spring container cùng processor thích hợp nhận biết và gọi callback. Đối tượng tạo bằng `new` không được Spring tự gọi các method này.

Ví dụ ý tưởng:

```text
Spring ApplicationContext tạo bean InfrastructureReporter
    |
    +-- constructor / @Bean factory method
    +-- inject dependency/property thông thường
    |
    +-- setEnvironment(context.getEnvironment())
    +-- setResourceLoader(context)
    +-- setMessageSource(context)
    |     (context tự implement ResourceLoader và MessageSource)
    |
    +-- @PostConstruct (nếu có)
    +-- InitializingBean.afterPropertiesSet() (nếu có)
    +-- custom init-method (nếu có)
    |
    +-- bean sẵn sàng sử dụng
```

Khi chạy trong `ApplicationContext` thông thường, ba callback được thực hiện **sau khi populate các bean properties**, **trước initialization callbacks**. Chúng không đồng nghĩa một lần context hoàn thành toàn bộ `refresh()`, không chứng minh mọi singleton khác đã tạo xong, và không thay thế dependency injection cho mọi loại service.

**Quy tắc thiết kế:** Aware rất hữu ích cho adapter, registrar, loader, message resolver hoặc component framework; ở service nghiệp vụ, ưu tiên truyền cụ thể `Environment`, `ResourceLoader`, `MessageSource` hoặc value cần thiết qua constructor để biểu lộ dependency và dễ unit test hơn.

## 2. Cơ chế Spring gọi Aware và thời điểm chính xác

Trong Spring `ApplicationContext`, một `ApplicationContextAwareProcessor` tham gia `BeanPostProcessor.postProcessBeforeInitialization` để xử lý nhiều interface Aware cấp context, bao gồm ba interface đang học. Nó lấy các đối tượng hạ tầng của context hiện tại rồi gọi setter callback của bean.

Vòng đời điển hình một bean bình thường:

```text
1. Phân tích bean definition
2. Chọn constructor/factory method và tạo instance
3. Population: @Autowired, @Value, setter, property values...
4. Aware callbacks của BeanFactory như BeanNameAware/BeanFactoryAware
5. BeanPostProcessor trước initialization
     - ApplicationContextAwareProcessor xử lý:
       EnvironmentAware
       EmbeddedValueResolverAware (nếu có)
       ResourceLoaderAware
       ApplicationEventPublisherAware (nếu có)
       MessageSourceAware
       ApplicationContextAware (nếu có)
     - CommonAnnotationBeanPostProcessor có thể xử lý @PostConstruct
6. InitializingBean.afterPropertiesSet()
7. custom init method (@Bean(initMethod = "..."))
8. BeanPostProcessor sau initialization (có thể tạo proxy)
9. Bean đã initialized và có thể được cung cấp cho consumer
```

Đối với bộ ba trong cùng một bean ở đường xử lý chuẩn của Spring `ApplicationContextAwareProcessor`, thứ tự gọi là **`setEnvironment` → `setResourceLoader` → `setMessageSource`** (processor có thể gọi các interface khác xen giữa nếu bean implement chúng). Không nên suy từ thứ tự này ra quy tắc tổng quát cho mọi `BeanPostProcessor` tự viết: thứ tự processor còn liên quan priority/order và cách context được cấu hình.

Các callback cấp `ApplicationContext` được xử lý trước initialization (như `@PostConstruct` trong cấu hình mặc định), nên bạn có thể sử dụng các reference đã được cung cấp bên trong method init. Không đưa logic nghiệp vụ nặng vào các setter Aware nếu logic ấy đòi dependency khác đã initialize hoặc một context đã hoàn tất refresh; setter nên **nhận và lưu reference**, sau đó xử lý ở pha hợp lý.

**Phân biệt BeanFactory với ApplicationContext:** `BeanNameAware` và `BeanFactoryAware` được BeanFactory hỗ trợ trực tiếp trong khâu initialization. Với `EnvironmentAware`, `ResourceLoaderAware` và `MessageSourceAware`, cách xử lý thông thường dựa vào hạ tầng ApplicationContext. Một `DefaultListableBeanFactory` cấp thấp tự khởi tạo, không đăng ký processor cấp context, không có nghĩa ba callback sẽ tự chạy.

## 3. EnvironmentAware: lấy Environment của context

Chữ ký API:

```java
import org.springframework.context.EnvironmentAware;
import org.springframework.core.env.Environment;

public class FeatureReporter implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    public boolean isDemoProfile() {
        return environment.acceptsProfiles(
                org.springframework.core.env.Profiles.of("demo"));
    }
}
```

Đây là Java class có thể biên dịch khi có `spring-context`, nhưng để thấy Spring gọi `setEnvironment` thì class phải được đăng ký thành bean trong một ApplicationContext. `Environment` mô tả **profiles** và cách tìm **properties** từ những property sources đang áp dụng trong context. `setEnvironment` nhận object Environment, không phải một bản sao các property tại một thời điểm.

### 3.1. Properties và thứ tự ưu tiên

`Environment.getProperty("app.mode")` tìm key trong các `PropertySource` theo thứ tự. Ví dụ nguồn thường gặp: command-line arguments (tùy framework), Java system properties, OS environment variables, properties do `@PropertySource` hoặc Spring Boot thêm, và nguồn được ứng dụng tự khai báo.

```java
String mode = environment.getProperty("app.mode", "normal");
int limit = environment.getProperty("app.limit", Integer.class, 100);
String required = environment.getRequiredProperty("app.region");
```

Ba dòng là fragment trong một bean đã có field `Environment environment`. `getProperty(key, default)` cho giá trị mặc định khi key thiếu; `getRequiredProperty` ném `IllegalStateException` nếu không tìm thấy; overload có `Class<T>` dùng conversion service để chuyển kiểu khi phù hợp. Chuyển `"not-a-number"` sang `Integer` có thể lỗi chuyển đổi, đừng coi default luôn xử lý cả dữ liệu cấu hình sai.

`EnvironmentAware` không tự động “refresh lại” các `@Value` field hoặc tái tạo bean khi property source đổi sau startup. Quy tắc tạo bean theo `@Profile`/`@Conditional` thường được quyết định trong quá trình xử lý bean definitions. Đổi active profiles sau `refresh()` không làm cấu hình đã khởi tạo tự quay ngược về giai đoạn lựa chọn definitions.

### 3.2. Active và default profiles

`Environment` có `getActiveProfiles()`, `getDefaultProfiles()` và `acceptsProfiles(Profiles.of("..."))`. Khi không có active profile, default profiles được dùng trong việc đánh giá profile theo hợp đồng Spring.

```java
boolean production = environment.acceptsProfiles(
        org.springframework.core.env.Profiles.of("prod"));
boolean notProduction = environment.acceptsProfiles(
        org.springframework.core.env.Profiles.of("!prod"));
```

Cú pháp profile expression có thể kết hợp `!`, `&`, `|` theo quy tắc `Profiles.of(...)`; dùng ngoặc khi cần để tránh mơ hồ. Nếu chỉ muốn giá trị đã bind, constructor injection với `@Value` hoặc một bean `@ConfigurationProperties` được validation trong Spring Boot thường rõ hơn việc lưu cả `Environment`.

### 3.3. Dùng đúng ngữ cảnh

Nên dùng `EnvironmentAware` khi component hạ tầng cần truy vấn nhiều property động hoặc profile decision ở các bước khởi tạo. Nếu service chỉ cần `app.discount-rate`, hãy inject đúng giá trị/typed configuration. Không biến method `setEnvironment` thành một nơi gọi database, start thread, hoặc quét lại BeanFactory.

## 4. ResourceLoaderAware: resolve tài nguyên thay vì phụ thuộc file vật lý

`ResourceLoaderAware` nhận `ResourceLoader`, có method trọng tâm `getResource(String location)` trả về `Resource`. Trong `ApplicationContext` thông thường, Spring truyền chính context (nó implement `ResourceLoader`).

```java
import org.springframework.context.ResourceLoaderAware;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

public class TemplateLocationResolver implements ResourceLoaderAware {
    private ResourceLoader loader;

    @Override
    public void setResourceLoader(ResourceLoader loader) {
        this.loader = loader;
    }

    public Resource loadTemplate(String name) {
        return loader.getResource("classpath:templates/" + name);
    }
}
```

Đây là class minh họa, không phải chương trình runnable độc lập: cần bean được Spring quản lý và resource thật trên classpath. Khi dựng đường dẫn từ tên không tin cậy, phải validate/allowlist `name`; ví dụ không minh họa kiểm soát bảo mật.

### 4.1. Các tiền tố location phổ biến

| Location | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `classpath:lesson/banner.txt` | Một resource từ classpath qua `ClassPathResource` | Dùng được trong JAR nếu đọc stream |
| `file:/opt/app/config.properties` | Resource từ filesystem qua `FileSystemResource` | File có thể không tồn tại hoặc không đọc được |
| `https://example.org/data.txt` | URL resource, khi loader hỗ trợ | Network I/O, timeout và SSRF nếu URI đến từ user |
| `lesson/banner.txt` | Đường dẫn không có prefix, phụ thuộc `ResourceLoader` cụ thể | `ClassPathXmlApplicationContext` và web context có thể resolve khác nhau |
| `classpath*:META-INF/spring/*.xml` | Pattern nhiều resource, **không dùng `getResource` cho pattern** | Dùng `ResourcePatternResolver.getResources(...)` |

`ResourceLoader.getResource(location)` lấy **một** Resource handle; nó không đồng nghĩa mở file hoặc khẳng định resource tồn tại. `Resource` cung cấp `exists()`, `getInputStream()`, `contentLength()` và một số phương thức truy cập metadata/URL/file tùy implementation.

**Không mặc định gọi `resource.getFile()` cho classpath resource:** khi đóng gói ứng dụng thành executable JAR, resource có thể là entry bên trong archive, không có path file độc lập. Dùng `getInputStream()` với try-with-resources để đọc tài liệu đóng gói:

```java
Resource resource = loader.getResource("classpath:lesson/banner.txt");
try (java.io.InputStream in = resource.getInputStream()) {
    String text = new String(in.readAllBytes(),
            java.nio.charset.StandardCharsets.UTF_8);
    System.out.println(text.strip());
}
```

Fragment cần field `loader` và một resource có tồn tại. `getInputStream` có thể ném `IOException`; kiểm tra và xử lý lỗi theo nghiệp vụ. Không duy trì stream mở qua nhiều request và không assume `Resource` nào cũng đọc lại được nhiều lần (ví dụ `InputStreamResource` thường gắn một stream).

### 4.2. ResourcePatternResolver không phải ResourceLoader đơn lẻ

Nếu cần nạp nhiều resource khớp pattern, dùng interface `ResourcePatternResolver` với `getResources("classpath*:META-INF/spring/*.xml")`. `ApplicationContext` thông thường cũng là `ResourcePatternResolver` và `ResourceLoaderAware` được truyền context nên có thể kiểm tra kiểu này. Tuy nhiên việc cast tùy vào loader thực tế; nếu ứng dụng được chạy với loader thay thế, không mặc định mọi `ResourceLoader` là `ResourcePatternResolver`.

```java
if (loader instanceof org.springframework.core.io.support.ResourcePatternResolver patternLoader) {
    Resource[] matching =
            patternLoader.getResources("classpath*:META-INF/spring/*.xml");
    // Xử lý từng Resource riêng, lưu ý IOExceptions.
}
```

Đoạn này là fragment, cần đặt trong method khai báo/handle `IOException` và import `Resource`. Nó minh họa khác biệt giữa một resource và một resource pattern. Giới hạn truy cập filesystem/network khi location đến từ input không tin cậy.

### 4.3. Khi nào chọn injection khác?

Đối với một resource cố định:

```java
@Component
class HelpDocument {
    private final Resource resource;

    HelpDocument(@Value("classpath:docs/help.txt") Resource resource) {
        this.resource = resource;
    }
}
```

Mã trên minh họa dependency của một component, cần `Component`/`Value` imports và file resource thật. Ưu điểm: rõ ràng bean phụ thuộc resource gì, không cần lưu toàn bộ loader. Với nhiều resource động theo plugin/tenant, nhận `ResourceLoader` có thể phù hợp hơn.

## 5. MessageSourceAware: lấy message resolver và dùng locale

`MessageSourceAware` nhận `MessageSource` của context, thường là chính `ApplicationContext` đang implement interface này; sau đó bạn có thể gọi `getMessage` để tra key, thay placeholder và chọn ngôn ngữ.

```java
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.context.MessageSourceAware;

public class LocalizedPresenter implements MessageSourceAware {
    private MessageSource messages;

    @Override
    public void setMessageSource(MessageSource messageSource) {
        this.messages = messageSource;
    }

    public String greet(String name, Locale locale) {
        return messages.getMessage("hello", new Object[]{name}, locale);
    }
}
```

Đây là class cần đăng ký thành Spring bean và một nguồn message có mã `hello`. Nếu mã thiếu và dùng overload không default, `NoSuchMessageException` có thể được ném. `MessageSource` không tự xác định locale HTTP hiện tại: code phải cung cấp `Locale` phù hợp (hoặc nhận từ resolver/web request khác theo ứng dụng).

### 5.1. Nguồn và tên bean messageSource

Trong ApplicationContext, tên bean quy ước **`messageSource`** có ý nghĩa đặc biệt. Nếu khai báo một `MessageSource` bean với tên đó, Spring sử dụng nó để resolve thông điệp. Nếu không khai báo, Spring cung cấp message source mặc định kiểu delegating để tích hợp parent/default messages theo cấu hình; đừng kỳ vọng nó tự có mọi key.

Các implementation thường dùng:
- `StaticMessageSource`: thêm message trực tiếp trong Java config; tiện cho demo và test.
- `ResourceBundleMessageSource`: lấy từ `messages.properties`, `messages_vi.properties` hoặc các basename tương ứng.
- `ReloadableResourceBundleMessageSource`: hỗ trợ thiết lập cơ chế cache/refresh khi nguồn resource tương ứng cho phép.

Ví dụ bảng mã i18n:

| Code | Locale | Text pattern |
| --- | --- | --- |
| `hello` | `vi-VN` | `Xin chào {0}!` |
| `hello` | `en-US` | `Hello {0}!` |
| `error.required` | `vi-VN` | `Trường {0} là bắt buộc.` |

`getMessage("hello", new Object[]{"Mai"}, Locale.forLanguageTag("vi-VN"))` tạo text `Xin chào Mai!` với một `MessageSource` chứa bản dịch trên. Placeholder dùng `MessageFormat`, cú pháp và cách escape dấu nháy đơn phải được xử lý đúng khi bản dịch có dấu apostrophe đặc biệt.

### 5.2. Overload với fallback

```java
String text = messages.getMessage(
        "notice.unknown", null, "Không có bản dịch", Locale.forLanguageTag("vi-VN"));
```

Đây là fragment khi field `messages` đã được inject. Overload có `defaultMessage` cho phép trả chuỗi fallback khi không tìm thấy code. Với overload `getMessage(code, args, locale)` không có default, mã thiếu có thể ném `NoSuchMessageException`; chọn overload theo chính sách lỗi thực sự của ứng dụng.

### 5.3. MessageSource không đồng nghĩa Message Broker

`MessageSource` dành cho **internationalization/text messages**, không liên quan Kafka/JMS/STOMP message transport. `MessageSourceAware` không đăng ký consumer, không gửi message queue và không quản lý application event; đó là các tính năng khác. Tên “message” ở đây là văn bản hiển thị cho người dùng theo locale.

## 6. Ví dụ Spring Core hoàn chỉnh chạy được với Java 17+

Ví dụ tích hợp **cả ba Aware interface trong một bean**, chứng minh Spring gọi callbacks trước khi `InitializingBean.afterPropertiesSet()`. Nó sử dụng Java 17+, Maven 3.9+ và Spring Framework 6.2.18, không cần Spring Boot, servlet container, database hay internet vào runtime. Cần tải Maven dependencies lần đầu.

Project:

```text
aware-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/edu/example/aware/
        │   ├── AppConfig.java
        │   ├── AwareReport.java
        │   └── Main.java
        └── resources/lesson/
            └── banner.txt
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
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
            <version>6.2.18</version>
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
                    <mainClass>edu.example.aware.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/resources/lesson/banner.txt**

```text
READY
```

**src/main/java/edu/example/aware/AwareReport.java**

```java
package edu.example.aware;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.EnvironmentAware;
import org.springframework.context.MessageSource;
import org.springframework.context.MessageSourceAware;
import org.springframework.context.ResourceLoaderAware;
import org.springframework.core.env.Environment;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

public final class AwareReport implements EnvironmentAware,
        ResourceLoaderAware, MessageSourceAware, InitializingBean {

    private Environment environment;
    private ResourceLoader resourceLoader;
    private MessageSource messageSource;
    private boolean ready;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
        System.out.println("aware: environment");
    }

    @Override
    public void setResourceLoader(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
        System.out.println("aware: resourceLoader");
    }

    @Override
    public void setMessageSource(MessageSource messageSource) {
        this.messageSource = messageSource;
        System.out.println("aware: messageSource");
    }

    @Override
    public void afterPropertiesSet() throws Exception {
        String mode = environment.getRequiredProperty("app.mode");
        Resource resource =
                resourceLoader.getResource("classpath:lesson/banner.txt");

        String banner;
        try (InputStream input = resource.getInputStream()) {
            banner = new String(input.readAllBytes(), StandardCharsets.UTF_8)
                    .strip();
        }

        String greeting = messageSource.getMessage(
                "hello", new Object[]{"Spring"}, Locale.forLanguageTag("vi-VN"));

        if (!"learning".equals(mode) || !"READY".equals(banner)) {
            throw new IllegalStateException("Invalid demo configuration");
        }

        System.out.println("init: mode=" + mode);
        System.out.println("init: resource=" + banner);
        System.out.println("init: message=" + greeting);
        ready = true;
    }

    public boolean isReady() {
        return ready;
    }
}
```

**src/main/java/edu/example/aware/AppConfig.java**

```java
package edu.example.aware;

import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.StaticMessageSource;

@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean(name = "messageSource")
    public MessageSource messageSource() {
        StaticMessageSource source = new StaticMessageSource();
        source.addMessage(
                "hello", Locale.forLanguageTag("vi-VN"), "Xin chào {0}!");
        return source;
    }

    @Bean
    public AwareReport awareReport() {
        return new AwareReport();
    }
}
```

**src/main/java/edu/example/aware/Main.java**

```java
package edu.example.aware;

import java.util.Map;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.core.env.MapPropertySource;

public final class Main {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {

            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("demo", Map.of("app.mode", "learning")));
            context.getEnvironment().setActiveProfiles("demo");
            context.register(AppConfig.class);
            context.refresh();

            AwareReport report = context.getBean(AwareReport.class);
            System.out.println("main: ready=" + report.isReady());
        }
    }
}
```

Trong thư mục `aware-demo`, chạy:

```bash
mvn -q compile exec:java
```

**Các dòng do chương trình tự in ra `System.out`, theo thứ tự:**

```text
aware: environment
aware: resourceLoader
aware: messageSource
init: mode=learning
init: resource=READY
init: message=Xin chào Spring!
main: ready=true
```

Các log Maven/Spring tùy môi trường có thể xuất hiện thêm. Các dòng trên được cố định bởi việc Spring gọi ba callback cho cùng `AwareReport` trong `ApplicationContextAwareProcessor`, sau đó chạy `afterPropertiesSet()`, rồi `Main` lấy bean đã được tạo.

Giải thích:
1. `new AnnotationConfigApplicationContext()` tạo context chưa refresh. Ta thêm `MapPropertySource` trước nên `app.mode` có giá trị `learning`.
2. `context.register(AppConfig.class)` khai báo Java configuration, chưa phải lệnh hoàn tất tất cả bean.
3. `context.refresh()` xử lý bean definitions, chuẩn bị bean factory và message source, tạo singleton eager `awareReport`.
4. `AwareReport` nhận ba dependency hạ tầng bằng các Aware setter callback; code minh họa chỉ in tên callback, không chạy IO ngay trong setter.
5. `afterPropertiesSet()` chạy khi các callback đã được xử lý; nó đọc `app.mode`, mở classpath resource bằng stream và tra message theo `vi-VN`.
6. Sau `refresh()`, `getBean(...)` trả bean đã initialized nên `ready=true`.
7. `try-with-resources` đóng context đúng cách; vì ví dụ không đăng ký destroy callback tự in log nên không có thêm dòng `System.out` sau dòng `main`.

**Độ tin cậy của ví dụ:** Không cần tạo HTTP request, không dựa vào thư mục làm việc để đọc file, và không dùng `Resource.getFile()`. Tệp `banner.txt` ở đúng `src/main/resources/lesson/` được Maven đặt vào classpath. `MessageSource` dùng `StaticMessageSource` để ví dụ độc lập với file properties i18n. Nếu bỏ tệp resource, sẽ gặp `IOException` trong init; nếu bỏ message, lookup `hello` không có fallback sẽ không tìm thấy code và bean khởi tạo thất bại.

## 7. Dùng @Autowired / constructor injection thay cho Aware khi hợp lý

Spring không bắt buộc mọi service muốn dùng `Environment`, `ResourceLoader` hay `MessageSource` đều phải implement Aware. Trong một context có autowiring, có thể inject các type này như các dependency khác:

```java
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.core.env.Environment;
import org.springframework.core.io.ResourceLoader;
import org.springframework.stereotype.Service;

@Service
public class NoticeService {
    private final Environment environment;
    private final ResourceLoader resourceLoader;
    private final MessageSource messages;

    public NoticeService(Environment environment,
                         ResourceLoader resourceLoader,
                         MessageSource messages) {
        this.environment = environment;
        this.resourceLoader = resourceLoader;
        this.messages = messages;
    }

    public String describe(Locale locale) {
        String mode = environment.getProperty("app.mode", "normal");
        String greeting =
                messages.getMessage("hello", null, "Hello", locale);
        return greeting + " / mode=" + mode;
    }

    // Có thể dùng resourceLoader trong method khác nếu cần resource động.
}
```

Đây là một Spring component độc lập về cú pháp Java khi dependency hợp lệ; nó cần context có messageSource code thích hợp để được kết quả đúng kỳ vọng. Constructor injection làm dependencies bắt buộc rõ ràng, field `final`, dễ mock/fake trong unit tests. Nếu service chỉ cần một key cấu hình, tốt hơn nhận value đã bind thay vì cả `Environment`.

| Tình huống | Hướng ưu tiên |
| --- | --- |
| Infrastructure adapter cần hỏi nhiều key/profile trong runtime | `EnvironmentAware` hoặc inject `Environment` |
| Service chỉ cần một giá trị bắt buộc | Typed configuration/constructor argument |
| Loader phải resolve nhiều resource động | `ResourceLoaderAware` hoặc inject `ResourceLoader` |
| Chỉ cần một classpath file đã biết | Inject `Resource` bằng `@Value("classpath:...")` |
| Component hạ tầng cần dịch text cho nhiều locale | `MessageSourceAware` hoặc inject `MessageSource` |
| Web controller cần một message localized | Inject `MessageSource`, nhận `Locale` từ request/resolver |
| Cần ApplicationContext chỉ để lấy ba service này | Chọn interface chuyên biệt hoặc inject trực tiếp, tránh lấy toàn context |
| Unit test muốn chạy không có Spring | Constructor injection với stub dependency |

Một lưu ý thực tế: đặt `@Autowired` constructor ở class implement `Aware` vẫn được, nhưng nếu đã cung cấp dependency cùng type bằng constructor thì Aware callback có thể thừa và tạo hai đường wiring khó bảo trì. Chỉ kết hợp khi có lý do kỹ thuật rõ, chẳng hạn framework contract phải hỗ trợ cả mode container-aware và standalone.

## 8. MessageSource dùng trong i18n thực tế

Với `ResourceBundleMessageSource`, bạn có thể tạo files:

```text
src/main/resources/i18n/messages.properties
src/main/resources/i18n/messages_vi.properties
src/main/resources/i18n/messages_en.properties
```

Ví dụ:

```properties
# i18n/messages_vi.properties
hello=Xin chào {0}!
error.required=Trường {0} là bắt buộc.
```

```properties
# i18n/messages_en.properties
hello=Hello {0}!
error.required=Field {0} is required.
```

Config:

```java
@Bean(name = "messageSource")
MessageSource messageSource() {
    ResourceBundleMessageSource source = new ResourceBundleMessageSource();
    source.setBasename("i18n/messages");
    source.setDefaultEncoding("UTF-8");
    return source;
}
```

Đây là fragment cần import `MessageSource`, `ResourceBundleMessageSource` và `Bean`; không phải cấu hình thứ hai cần chèn cùng lúc vào ví dụ `StaticMessageSource` ở mục 6. Chọn **một** bean `messageSource` theo thiết kế. Locale `Locale.forLanguageTag("vi-VN")` thường fallback qua ngôn ngữ `vi` nếu không có bundle `vi_VN` riêng. Quy tắc fallback còn chịu cách loader và default locale được cấu hình; test với locale thực tế của ứng dụng.

Khi dùng Spring Boot, convention file `messages.properties` và cấu hình `spring.messages.basename` có thể được Boot tự nhận; còn bài này tập trung **Spring Framework Core Container**, nên các message source được khai báo rõ.

### Thông điệp thiếu và tính nhất quán

Đối với error code không tồn tại, lựa chọn:
- Ném exception rõ để phát hiện thiếu translations trong CI/test.
- Có defaultMessage hợp lý, tránh làm request fail chỉ vì thiếu một bản dịch không quan trọng.
- Log metrics cho missing codes và viết kiểm thử mọi locale bắt buộc.

Đừng dùng text bản dịch làm key nghiệp vụ hoặc key database. Message key `error.required` ổn định hơn text từng ngôn ngữ; việc dịch chỉ ở presentation layer.

## 9. Phạm vi, proxy, lifecycle và thread safety

### 9.1. Singleton, prototype, request và session

Với một singleton eager thông thường, Aware callback của target được gọi khi target tạo lần đầu trong container. Với prototype, mỗi lần Spring thực sự khởi tạo target prototype, callback tương ứng được xử lý. Với request/session-scoped target, callback thuộc lần khởi tạo **target theo scope**, không phải mỗi lần method trên scoped proxy được gọi.

Ví dụ singleton inject request-scoped bean qua proxy có thể giữ proxy lâu dài; reference `Environment`, `ResourceLoader` và `MessageSource` vẫn thuộc context, trong khi dữ liệu request chỉ xuất hiện ở target lúc resolve. Đừng giả định Aware tạo request-specific `Environment` hay `MessageSource` cho mỗi request.

### 9.2. Có thể đọc các reference này từ nhiều thread không?

Cả ba dependency thường là hạ tầng dùng chung, dùng để đọc config, resolve resource và tra message. Nhiều singleton có thể nhận cùng reference. **Không** vì thế mà mọi operation ta tự viết trong callback đều thread-safe: nếu component của bạn duy trì cache mutable, thay property sources hoặc sửa catalog translations lúc runtime, cần kiểm soát synchronization/publication.

Ví dụ không nên viết trong setter:

```java
@Override
public void setEnvironment(Environment environment) {
    this.environment = environment;
    this.lastUser = environment.getProperty("user"); // Sai mô hình per-request.
}
```

Đây là fragment minh họa anti-pattern, phụ thuộc field `lastUser`. `Environment` là cấu hình ứng dụng, không phải storage của từng HTTP user. Với dữ liệu user/request, dùng method parameter, authentication principal hoặc request-scoped context được thiết kế đúng.

### 9.3. Proxy/AOP không tự chặn callback

Aware method được Spring gọi trong initialization của target bean, trước khi một số proxy cuối cùng được tạo. Đừng dựa vào `@Transactional`, `@Async` hoặc `@Cacheable` đặt trên chính `setEnvironment`/`setResourceLoader`/`setMessageSource` để kích hoạt AOP advice. Nếu callback tự gọi method khác trên `this`, nó có thể bypass proxy. Giữ callback đơn giản và không gửi side effect nghiệp vụ từ đó.

### 9.4. Không đồng nghĩa application đã ready

Các callback chạy khi **một bean** được tạo; context có thể còn trong `refresh()`. Ví dụ cần load một external translation service có thể sử dụng fallback local `MessageSource` trước, và chuyển startup/check readiness sang cơ chế sau refresh hoặc lifecycle component phù hợp nếu cần.

## 10. BeanFactory, custom contexts và kiểm thử

### 10.1. Khi chỉ dùng BeanFactory

`BeanFactory` mức thấp không tự là `ApplicationContext`, `MessageSource` hoặc `ResourceLoader`. Một bean implement interface Aware cấp context có thể **không nhận callback** nếu không có processor nhận diện. Trái lại, `BeanNameAware`/`BeanFactoryAware` có cơ chế core bean factory xử lý. Không dùng unit test chỉ `new AwareReport()` để kiểm chứng thứ tự callback Spring.

### 10.2. Unit test Aware đơn giản

Có thể kiểm logic bằng cách tự gọi setters với các dependency giả:

```java
AwareReport report = new AwareReport();
report.setEnvironment(testEnvironment);
report.setResourceLoader(testResourceLoader);
report.setMessageSource(testMessageSource);
report.afterPropertiesSet();
```

Đây chỉ là **test fragment**, không runnable nếu thiếu ba biến test và resource/message phù hợp. Nó kiểm logic xử lý dependency nhưng không chứng minh container đã tự gọi các callback. Integration test muốn kiểm lifecycle thực phải tạo `AnnotationConfigApplicationContext`, đăng ký `AppConfig`, gọi `refresh()` và assert trạng thái target.

### 10.3. Kiểm tra callback đúng context

Nếu có parent-child `ApplicationContext`, mỗi bean thuộc context tạo nó. `EnvironmentAware`, `ResourceLoaderAware`, `MessageSourceAware` của bean nhận ngữ cảnh/hạ tầng tương ứng; việc parent và child cùng có property sources hoặc messageSource inheritance không đồng nghĩa chúng có cùng bean instance. Một child có thể override message code hoặc property sources. Đừng cache reference toàn cục rồi giả định nó áp dụng cho mọi context.

### 10.4. Mocking và dependency visibility

Với Aware callback, fields thường không final vì Spring gọi setter sau constructor. Nếu bạn cần invariant “không thể tạo bean thiếu dependency”, constructor injection làm contract rõ hơn. Với Aware bean, có thể kiểm trong `afterPropertiesSet()` và ném exception nếu thiếu một callback được kỳ vọng:

```java
@Override
public void afterPropertiesSet() {
    if (environment == null || resourceLoader == null ||
            messageSource == null) {
        throw new IllegalStateException(
                "Aware infrastructure not initialized");
    }
}
```

Đây là fragment minh họa thuộc class đã có các field; chỉ cần dùng khi container wiring không bảo đảm sẵn sàng hoặc bean phải hỗ trợ chạy ở nhiều môi trường.

## 11. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Giải pháp |
| --- | --- | --- |
| `setEnvironment` không chạy | Bean tạo bằng `new` hoặc không được ApplicationContext xử lý | Khai báo `@Bean`/`@Component`, dùng context đúng |
| `setResourceLoader` không chạy | Dùng BeanFactory trần không đăng ký processor | Dùng ApplicationContext hoặc bổ sung infrastructure phù hợp |
| `setMessageSource` nhận object khác bean `messageSource` | Callback thường nhận ApplicationContext như MessageSource façade | Gọi interface `getMessage`, không ép cast sang implementation của bean |
| `getProperty` trả null | Key không tồn tại hoặc source precedence khác dự kiến | Kiểm tra property sources, profile, spelling và defaults |
| Đổi active profile sau startup nhưng bean không thay | `@Profile` được xử lý lúc chọn definitions | Đặt profile trước refresh, thiết kế runtime config riêng |
| `@Value` và `Environment` cho kết quả lệch | Khác thời điểm resolve/cấu hình property sources | Xác định semantics binding, tránh mutate config tùy tiện sau init |
| `Resource.getFile()` lỗi khi đóng gói JAR | Classpath resource không phải file riêng | Dùng `getInputStream()` và đóng stream |
| `getResource("classpath*:...")` không trả danh sách | API chỉ trả một resource | Dùng `ResourcePatternResolver.getResources(...)` |
| `IOException` khi mở resource | Location sai, resource không có, permission/network | Kiểm tra location, exists và xử lý IO |
| `NoSuchMessageException` | Thiếu code/bundle hoặc locale không có fallback | Thêm translation, defaultMessage hoặc kiểm tra basename |
| Message không đổi khi locale đổi | Dùng locale cố định hoặc resolver không truyền locale đúng | Truyền Locale phù hợp mỗi request |
| Lẫn `MessageSource` với Kafka/JMS | Hai API khác mục đích | Dùng đúng API messaging tương ứng |
| Callback chạy khi App chưa ready | Aware thuộc init một bean | Dùng callback lifecycle cấp context/startup phù hợp |
| Callback tự gọi method `@Transactional` nhưng không có transaction | Initialization/self-invocation bypass AOP proxy | Chuyển logic nghiệp vụ sang bean được gọi qua proxy sau startup |
| Bean lazy chưa nhận Aware | Target chưa được tạo | Callback chạy khi bean thực sự instantiate |
| Logic nội bộ lưu mutable shared state | Aware không bảo đảm thread safety cho object | Thiết kế immutable snapshot hoặc đồng bộ đúng |
| Unit test `new` bean rồi thất bại vì field null | Test bypass Spring | Inject mock qua constructor hoặc gọi setter test tường minh |

## 12. Checklist thiết kế và bài tập tự đánh giá

Trước khi dùng Aware cho một component, hãy tự trả lời:
1. Component có thật sự cần API hạ tầng, hay chỉ cần một giá trị cố định?
2. Nó được Spring ApplicationContext tạo hay có trường hợp dùng bằng `new`?
3. Callback có đang làm việc nặng/side effect trước context refresh không?
4. Bean dùng `Environment` để đọc cấu hình hay đang lẫn với request/user state?
5. Resource có chắc tồn tại trong packaged JAR và được mở bằng stream không?
6. Đường dẫn resource có lấy từ input không tin cậy không?
7. MessageSource có bean name `messageSource` và bản dịch/default policy đúng không?
8. Có dùng đúng `Locale`, kiểm thử thiếu code, dấu tiếng Việt và placeholder không?
9. Trong unit test có cách inject stub mà không khởi động context không?
10. Khi có parent-child contexts, bean thuộc context nào và property/message precedence ra sao?

**Câu hỏi luyện tập:**

1. Bean implement `EnvironmentAware` có được callback nếu chỉ gọi constructor `new` không?
2. Vì sao method `setEnvironment` chạy sau constructor? Nó chạy trước hay sau `afterPropertiesSet()`?
3. `Environment.getProperty("timeout", Integer.class, 30)` khác `getRequiredProperty("timeout")` thế nào?
4. Muốn bật một bean `@Profile("dev")` cần đặt active profile trước hay sau `refresh()`?
5. `ResourceLoaderAware` nhận trực tiếp một `Resource` hay một object có thể resolve nhiều resource?
6. Resource trong executable JAR nên đọc qua `getFile()` hay `getInputStream()`?
7. Nếu cần tìm `classpath*:META-INF/spring/*.xml`, nên dùng interface nào?
8. Tên bean `messageSource` có ý nghĩa gì trong ApplicationContext?
9. `getMessage("unknown", null, locale)` có thể ném exception nào?
10. Muốn greeting tiếng Việt, phải cung cấp `Locale` nào và message pattern ra sao?
11. Bean implement ba Aware interface có thể dùng ba dependency đó trong `@PostConstruct` không?
12. Aware callback có nghĩa toàn bộ ứng dụng đã startup thành công chưa?
13. Vì sao constructor injection thuận lợi hơn Aware cho một service thông thường?
14. Bean request-scoped được proxied: Aware callbacks của target chạy vào lúc nào?
15. Vì sao `MessageSourceAware` không giúp subscribe Kafka topic?

**Đáp án:** (1) Không, Spring không quản lý object ấy. (2) Vì processor cấp context gọi khi initialization sau property population, trước `afterPropertiesSet()`. (3) Overload đầu có default + conversion, overload sau yêu cầu key phải có. (4) Trước. (5) ResourceLoader. (6) InputStream. (7) ResourcePatternResolver. (8) Spring dùng làm strategy message lookup. (9) `NoSuchMessageException`. (10) `vi-VN` (có fallback language `vi` tùy bundle) và pattern `Xin chào {0}!`. (11) Có trong đường Spring thông thường. (12) Chưa. (13) Dependency hiển lộ, immutable fields và unit test đơn giản. (14) Khi target thật được tạo theo scope, không phải mỗi method trên proxy. (15) MessageSource chỉ cung cấp i18n text lookup.

## Tài liệu tham khảo chính thức

- Spring Framework — Customizing the Nature of a Bean, Other Aware Interfaces: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — Resources / ResourceLoaderAware Interface: https://docs.spring.io/spring-framework/reference/core/resources.html
- Spring Framework — Internationalization using MessageSource: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework 6.2 — EnvironmentAware Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/EnvironmentAware.html
- Spring Framework 6.2 — ResourceLoaderAware Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/ResourceLoaderAware.html
- Spring Framework 6.2 — MessageSourceAware Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/MessageSourceAware.html
- Spring Framework 6.2 — ApplicationContextAwareProcessor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/support/ApplicationContextAwareProcessor.html
- Spring Framework 6.2 — ResourcePatternResolver Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/io/support/ResourcePatternResolver.html
- Spring Framework 6.2 — MessageSource Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/MessageSource.html
