# Callback @PostConstruct sau khi hoàn tất cung cấp phụ thuộc trong Spring Framework

## 1. @PostConstruct giải quyết vấn đề gì?

Trong Spring IoC Container, Spring thường tạo bean bằng constructor hoặc factory method, cung cấp các dependency và property đã khai báo, sau đó mới chạy các callback khởi tạo. Annotation `@PostConstruct` đánh dấu một method cần được Spring gọi **sau khi việc dependency injection và property population thông thường của bean đã hoàn tất**, trước khi bean được coi là hoàn thành giai đoạn khởi tạo thông thường.

```java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class ExampleService {
    @PostConstruct
    public void initialize() {
        // Chuẩn bị trạng thái cần thiết sau khi dependency đã được inject.
    }
}
```

Đoạn trên là một component Spring; muốn callback được chạy phải tạo bean bằng container đã đăng ký processor cho annotation tương ứng. Gọi `new ExampleService()` trực tiếp sẽ **không** khiến Spring tự gọi `initialize()`.

Đây là hook vòng đời **mỗi lần một bean target được tạo và được Spring khởi tạo**, không phải hook mỗi HTTP request, mỗi lần gọi method, hay toàn bộ hệ thống đã khởi động thành công. Với singleton eager thông thường, callback được gọi một lần trong một `ApplicationContext` cho bean definition ấy. Với prototype hoặc scoped target, callback gắn với **mỗi lần target được tạo**; với lazy singleton, callback thường chờ đến lần bean được khởi tạo thật.

### Khi nào dùng?

Các tác vụ phù hợp với `@PostConstruct` gồm:

- Kiểm tra ràng buộc của cấu hình sau khi inject `@Value` hoặc dependency qua setter.
- Chuẩn bị một immutable lookup table, bộ chuyển đổi, parser hoặc cấu trúc dữ liệu dùng nhiều lần trong bean.
- Tính một giá trị phụ thuộc cả constructor argument lẫn property được Spring gán sau constructor.
- Đăng ký tài nguyên nội bộ nhỏ, xác lập trạng thái "ready" có kiểm soát trước khi bean được sử dụng bình thường.
- Phát hiện lỗi cấu hình sớm bằng exception rõ ràng ngay trong quá trình khởi tạo bean.

Hạn chế dùng hook này cho network call dài, blocking mãi, tự chạy background thread, gửi sự kiện nghiệp vụ hoặc thực thi hành động có side effect khó rollback. Các tác vụ đó có thể cần cơ chế startup sau khi context refresh (`ApplicationRunner`/`CommandLineRunner` trong Spring Boot, `ContextRefreshedEvent`, `SmartLifecycle` tùy bài toán) và cơ chế shutdown riêng.

## 2. @PostConstruct đứng ở đâu trong vòng đời bean?

Một đường đi điển hình của Spring-managed bean không có vòng tham chiếu bất thường:

```text
1. Spring tìm bean definition và chọn constructor / factory method
                          |
                          v
2. Khởi tạo instance: constructor chạy
                          |
                          v
3. Populate properties và dependency injection:
   @Autowired field, @Autowired setter, @Value, @Resource ...
                          |
                          v
4. Aware callbacks liên quan (BeanNameAware, BeanFactoryAware ...)
   và các BeanPostProcessor chạy trước initialize
                          |
                          v
5. @PostConstruct                <-- hook của bài học này
                          |
                          v
6. InitializingBean.afterPropertiesSet()
                          |
                          v
7. Custom init method (ví dụ @Bean(initMethod = "init"))
                          |
                          v
8. BeanPostProcessor sau initialize
   (có thể tạo/wrap AOP proxy)
                          |
                          v
9. Bean được cung cấp cho consumer và hoạt động
                          |
                          v
10. Khi destroy scope/container: callback hủy phù hợp
```

Đây là sơ đồ học tập cho quy trình tạo bean thông thường. Chính xác hơn, `CommonAnnotationBeanPostProcessor` xử lý `@PostConstruct` trong pha `postProcessBeforeInitialization`. Có thể có nhiều `BeanPostProcessor` chạy trước/sau initialization; thứ tự giữa các processor tùy cấu hình và quy tắc ordering. Do đó sơ đồ không bảo đảm toàn bộ processor chạy trước `@PostConstruct`, và Spring có thể có các trường hợp phức tạp như early reference/proxy và circular dependency.

Điều Spring cam kết là callback khởi tạo chạy khi dependency đã được **cung cấp** cho bean theo bean definition. Nó **không** có nghĩa:
- Mọi singleton trong context đã khởi tạo hết.
- Mọi lazy dependency/proxy đã resolve target bên trong.
- Ứng dụng HTTP đã sẵn sàng nhận traffic.
- Tất cả database/messaging service bên ngoài đang hoạt động.
- Không còn bất kỳ công việc bất đồng bộ nào đang diễn ra.
- Một bean được quản lý bởi một container khác cũng đã sẵn sàng.

Phần lớn quan hệ dependency trực tiếp bình thường đã được resolve trước khi callback trên bean consumer chạy. Nếu cần thứ tự giữa các bean không có injection relationship, khai báo quan hệ rõ ràng bằng dependency hoặc `@DependsOn` theo nhu cầu; `@Order` không phải công cụ phổ quát điều khiển startup order.

## 3. Phân biệt constructor injection, field/setter injection và @PostConstruct

### Constructor injection

```java
@Component
class InvoiceService {
    private final TaxPolicy taxPolicy;

    InvoiceService(TaxPolicy taxPolicy) {
        this.taxPolicy = taxPolicy;
        // taxPolicy đã có sẵn trong constructor.
    }
}
```

`TaxPolicy` là interface/bean của ứng dụng cần định nghĩa riêng; đoạn mã chỉ minh họa và cần import `Component`. Nếu toàn bộ dữ liệu cần thiết nằm trong constructor và object có thể được khởi tạo hoàn toàn ngay lúc đó, **constructor là lựa chọn ưu tiên**: dependency bắt buộc thể hiện rõ và field có thể `final`.

### Setter hoặc field injection

```java
@Component
class InvoiceService {
    @Autowired
    private TaxPolicy taxPolicy;

    InvoiceService() {
        // Ở đây taxPolicy vẫn chưa được gán bằng @Autowired.
    }

    @PostConstruct
    void init() {
        // taxPolicy đã được inject trong đường khởi tạo bình thường.
    }
}
```

Cần import `Component`, `Autowired`, `PostConstruct` và định nghĩa `TaxPolicy`. Với field injection, constructor chạy **trước** khi Spring gán field. Với `@Autowired` setter, setter được gọi trong giai đoạn population. Vì thế không nên truy cập field-injected dependency trong constructor. Sau khi injection thông thường kết thúc, `@PostConstruct` có thể dùng chúng để chuẩn bị dữ liệu dẫn xuất.

Không coi "đã inject" là "luôn non-null" nếu bạn tự khai báo injection optional, `@Autowired(required = false)`, `Optional<T>`, `@Nullable` hoặc property không bắt buộc. Callback vẫn cần kiểm tra constraint thật.

### @Value và cấu hình

```java
@Component
class RuntimeSettings {
    @Value("${features.max-items:100}")
    private int maxItems;

    @PostConstruct
    void validate() {
        if (maxItems <= 0) {
            throw new IllegalStateException(
                    "features.max-items must be positive");
        }
    }
}
```

Trong một Spring context có `@Value` property resolution phù hợp, callback kiểm tra giá trị **sau khi binding/injection**. Nhưng với Spring Boot, nếu nhiều cấu hình liên quan nhau, `@ConfigurationProperties` kết hợp validation thường phù hợp hơn cho cấu hình kiểu dữ liệu rõ ràng. Ví dụ trên là fragment minh họa, không phải Java executable độc lập.

## 4. API đúng trong Java 17+ và Spring Framework hiện đại

Dùng `jakarta.annotation.PostConstruct` trong Spring Framework 6.x/7.x (đã chuyển từ namespace Java EE/Jakarta cũ). **Không** nhập nhầm `javax.annotation.PostConstruct` khi build Spring 6+/Boot 3+.

```java
import jakarta.annotation.PostConstruct;
```

Java SE 17 không tích hợp sẵn Jakarta Annotations API. Với Maven/Spring Framework, cần có dependency chứa `jakarta.annotation`; thường Spring Boot starter đã cung cấp thông qua dependency graph, nhưng ứng dụng Spring Core tối thiểu nên khai báo rõ nếu cần.

Các nguyên tắc cho method:
- Phương thức instance, không truyền tham số, kiểu trả về `void`.
- Không là static method.
- Nên có tên thể hiện nghiệp vụ, ví dụ `validateConfiguration` hoặc `buildIndex`.
- Nên tránh checked exception; nếu cần báo lỗi khởi tạo, ném `IllegalStateException`/exception không checked có ý nghĩa.
- Có thể là method private/package-private/public theo điều kiện truy cập của runtime; dùng phương thức đơn giản không phụ thuộc proxy là cách an toàn khi làm việc với Java module access.
- Không yêu cầu return object hoặc gán lại field reference; Spring chỉ gọi method, không lấy return value.
- Với nhiều method `@PostConstruct`, thứ tự giữa các hook trong hierarchy/phạm vi xử lý annotation có thể phức tạp; nên gom các bước có phụ thuộc thứ tự vào một callback rõ ràng.
- Tránh chỉ định lại cùng logic qua các lifecycle hook khác nếu không cần.

Theo hợp đồng Jakarta `PostConstruct`, method thực hiện initialization sau injection, chỉ chạy một lần cho mỗi instance target được khởi tạo trong vòng đời quản lý tương ứng. Spring có thể hỗ trợ phương thức visibility khác nhau, nhưng khi dùng JPMS cần để ý package/module access.

### Điều kiện Spring nhận ra annotation

Trong ứng dụng cấu hình bằng `AnnotationConfigApplicationContext` hoặc Spring Boot, `CommonAnnotationBeanPostProcessor` thường được đăng ký tự động. Cơ chế này xử lý cả `@PostConstruct`, `@PreDestroy` và `@Resource`. Với `BeanFactory` mức thấp hoặc cấu hình XML tối giản, phải đăng ký annotation processors/`<context:annotation-config/>` thích hợp; nếu không Spring có thể tạo bean mà bỏ qua annotation.

Một object do ứng dụng tạo bằng `new`, object được deserialize hoặc object được framework khác tạo mà không đi qua Spring bean lifecycle sẽ **không tự chạy** callback của Spring. Nếu cần wiring object đã tạo sẵn, phải chủ động dùng API/container phù hợp và hiểu rõ lifecycle/ownership của đối tượng đó.

## 5. Ví dụ Spring Core hoàn chỉnh: quan sát constructor → injection → @PostConstruct

Ví dụ này dùng **Java 17+, Maven 3.9+, Spring Framework 6.2.12** và chỉ cần Core Container, không cần web server. Tất cả source đều được liệt kê, không dùng DB. Ta tạo một `Catalog` bằng constructor injection, nhận thêm `Formatter` qua setter `@Autowired`, rồi tạo snapshot đã xử lý trong `@PostConstruct`. Chương trình đồng thời minh họa thứ tự của `InitializingBean`, `@Bean(initMethod=...)` và các callback hủy.

Cấu trúc dự án:

```text
postconstruct-demo/
├── pom.xml
└── src/main/java/edu/example/lifecycle/
    ├── Main.java
    ├── AppConfig.java
    ├── SourceData.java
    ├── Formatter.java
    └── Catalog.java
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>postconstruct-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>2.1.1</version>
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
                    <mainClass>edu.example.lifecycle.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/edu/example/lifecycle/SourceData.java**

```java
package edu.example.lifecycle;

public record SourceData(String text) {
}
```

**src/main/java/edu/example/lifecycle/Formatter.java**

```java
package edu.example.lifecycle;

public class Formatter {
    public String format(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
```

**src/main/java/edu/example/lifecycle/Catalog.java**

```java
package edu.example.lifecycle;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.annotation.Autowired;

public class Catalog implements InitializingBean, DisposableBean {
    private final SourceData source;
    private Formatter formatter;
    private String preparedValue;

    public Catalog(SourceData source) {
        this.source = source;
        System.out.println("1. constructor: " + source.text());
    }

    @Autowired
    public void setFormatter(Formatter formatter) {
        this.formatter = formatter;
        System.out.println("2. @Autowired setter");
    }

    @PostConstruct
    public void prepare() {
        // Cả constructor dependency lẫn setter dependency đều có sẵn.
        preparedValue = formatter.format(source.text());
        System.out.println("3. @PostConstruct: " + preparedValue);
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("4. afterPropertiesSet()");
    }

    public void customInit() {
        System.out.println("5. custom init()");
    }

    public String value() {
        return preparedValue;
    }

    @PreDestroy
    public void beforeDestroy() {
        System.out.println("7. @PreDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("8. DisposableBean.destroy()");
    }

    public void customDestroy() {
        System.out.println("9. custom destroy()");
    }
}
```

**src/main/java/edu/example/lifecycle/AppConfig.java**

```java
package edu.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean
    public SourceData sourceData() {
        return new SourceData("spring");
    }

    @Bean
    public Formatter formatter() {
        return new Formatter();
    }

    @Bean(initMethod = "customInit", destroyMethod = "customDestroy")
    public Catalog catalog(SourceData sourceData) {
        return new Catalog(sourceData);
    }
}
```

**src/main/java/edu/example/lifecycle/Main.java**

```java
package edu.example.lifecycle;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            Catalog catalog = context.getBean(Catalog.class);
            System.out.println("6. value(): " + catalog.value());
        }
        // try-with-resources đóng context, gọi các destroy callbacks
    }
}
```

Tại thư mục `postconstruct-demo`, chạy:

```bash
mvn -q compile exec:java
```

**Các dòng stdout do ứng dụng in:**

```text
1. constructor: spring
2. @Autowired setter
3. @PostConstruct: SPRING
4. afterPropertiesSet()
5. custom init()
6. value(): SPRING
7. @PreDestroy
8. DisposableBean.destroy()
9. custom destroy()
```

Spring/Maven có thể tạo thêm log phụ thuộc môi trường, nhưng các dòng `System.out.println` ở trên có thứ tự xác định trong ví dụ một bean không có cycle/proxy tùy biến. `AnnotationConfigApplicationContext(AppConfig.class)` refresh context ngay trong constructor, khiến `catalog` singleton được khởi tạo **trước** khi `context.getBean(...)` trong `Main`. Bởi vậy thứ tự 1–5 xuất hiện trước 6. `try-with-resources` đóng context khi kết thúc block nên callback hủy 7–9 chạy tiếp.

Điểm quan trọng nhất của mẫu: constructor chỉ có `SourceData`; `Formatter` được inject về sau bằng `@Autowired` setter. Trong `prepare()`, cả hai đã sẵn sàng. Nếu viết `formatter.format(...)` ở constructor của `Catalog`, `formatter` còn `null` và gây lỗi.

Ba cơ chế khởi tạo khác nhau áp dụng trên cùng bean ở thứ tự `@PostConstruct` → `InitializingBean.afterPropertiesSet()` → configured `initMethod`. Ba cơ chế hủy tương ứng chạy theo `@PreDestroy` → `DisposableBean.destroy()` → custom destroy method, nếu bean được hủy qua lifecycle do Spring quản lý. Trong ứng dụng thật, thường chỉ chọn **một** cách cho mỗi mục đích để giữ code gọn.

## 6. Cách Spring thực thi @PostConstruct bên dưới

Annotation chỉ là metadata. `CommonAnnotationBeanPostProcessor` (thông qua cơ chế `InitDestroyAnnotationBeanPostProcessor`) là thành phần nhận diện và gọi method được đánh dấu.

Một phiên bản rút gọn của quá trình:

```text
createBeanInstance()
  └─ resolve constructor/factory dependencies
  └─ construct instance

populateBean()
  └─ AutowiredAnnotationBeanPostProcessor inject @Autowired/@Value...
  └─ các processor/property population phù hợp khác

initializeBean()
  └─ invoke Aware callbacks như BeanNameAware
  └─ apply BeanPostProcessors.beforeInitialization(...)
       └─ CommonAnnotationBeanPostProcessor gọi @PostConstruct
  └─ invoke InitializingBean.afterPropertiesSet()
  └─ invoke configured init methods
  └─ apply BeanPostProcessors.afterInitialization(...)
       └─ có thể wrap bean bằng proxy
```

Các API ở trên mô tả logic ở mức khái niệm, không phải source copy đầy đủ của một phiên bản Spring. Với BeanPostProcessor do ứng dụng viết, thứ tự thực tế còn phụ thuộc priority/order; tuyệt đối không dùng sơ đồ này để bảo đảm rằng tất cả bean khác đã tạo hoặc tất cả AOP advice đã bắt đầu có hiệu lực.

**Hệ quả khi dùng AOP:** `@PostConstruct` thường được gọi trên **raw target bean**, trước khi target được bao bởi AOP proxy cuối cùng. Do đó một lệnh tự gọi method có `@Transactional`, `@Async`, `@Cacheable` hoặc advice khác từ `@PostConstruct` không phải con đường đáng tin để kích hoạt advice đó. Ngay cả với method public, self-invocation trên target bỏ qua Spring AOP proxy.

Ví dụ cần tránh:

```java
@Service
class CacheBootstrap {
    @PostConstruct
    void init() {
        refreshInTransaction(); // Không kỳ vọng proxy @Transactional intercept.
    }

    @Transactional
    public void refreshInTransaction() {
        // Tương tác DB...
    }
}
```

Snippet này cần import `@Service`, `@PostConstruct`, `@Transactional` và cấu hình transaction, chỉ minh họa chống pattern, không phải chương trình chạy độc lập. Nếu cần thực thi transaction tại startup, chuyển lời gọi qua bean collaborator được Spring quản lý và chọn thời điểm phù hợp khi transaction infrastructure đã sẵn sàng; thường initialization hook sau context refresh phù hợp hơn với startup task.

## 7. @PostConstruct so với các lifecycle hook khác

| Cơ chế | Khi nào chạy? | Mục đích và lưu ý |
| --- | --- | --- |
| Constructor / `@Bean` factory | Tạo instance | Phù hợp nhất để thiết lập bất biến và dependency bắt buộc qua constructor |
| Setter / field `@Autowired`, `@Value` | Giai đoạn inject/populate | Cung cấp dependency/config chưa có trong constructor |
| `@PostConstruct` | Sau injection, trong pha trước init của BeanPostProcessor | Validate và chuẩn bị state sau khi inject |
| `InitializingBean.afterPropertiesSet()` | Sau `@PostConstruct` | Hook Spring-specific cho initialization |
| `@Bean(initMethod = "...")` / XML init-method | Sau `afterPropertiesSet()` khi cùng bean kết hợp đủ cơ chế | Hook cấu hình bên ngoài class |
| `BeanPostProcessor.postProcessAfterInitialization` | Sau các init callback | Có thể wrap bean, ví dụ tạo AOP proxy |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | Sau khi pre-instantiation của singleton không-lazy kết thúc | Phù hợp logic cần đa số singleton eager đã sẵn sàng; không đồng nghĩa mọi bean lazy/prototype đã tạo |
| `ContextRefreshedEvent` | Context refresh thành công | Hook cấp ApplicationContext; có thể nhận nhiều lần nếu refresh |
| `ApplicationRunner` / `CommandLineRunner` (Boot) | Sau Spring Boot context startup theo quy trình Boot | Chạy startup logic cấp ứng dụng; không thay thế bean init |
| `SmartLifecycle` | Theo phase start/stop container | Quản lý các thành phần sống dài như listener/consumer |
| `@PreDestroy` | Trong destruction lifecycle phù hợp | Dọn tài nguyên trước các callback destroy khác |

**Chọn hook theo việc cần biết:**
- Cần dependency riêng của bean → constructor hoặc `@PostConstruct`.
- Cần hầu hết eager singleton đã tạo → `SmartInitializingSingleton`.
- Cần việc cấp application sau khi Spring Boot khởi động context → runner hoặc event tương ứng.
- Cần kiểm soát start/stop service lâu dài → `SmartLifecycle`.
- Cần giải phóng tài nguyên → `@PreDestroy`/`destroyMethod`, với giới hạn scope.

Một `ApplicationReadyEvent` trong Spring Boot là sự kiện Boot báo ứng dụng ready theo quy trình startup; đây cũng **không** chứng minh tất cả external dependency đang healthy. Đừng dùng `@PostConstruct` chỉ để chạy một lần tác vụ sau khi server nhận request, vì thời điểm bean được tạo có thể trước server sẵn sàng.

## 8. Khác nhau theo singleton, prototype và web scopes

| Scope | Số lần `@PostConstruct` được gọi | Destruction callback |
| --- | --- | --- |
| `singleton` | Một lần khi target bean được tạo trong container (mặc định eager) | Khi container shutdown đúng quy trình |
| Lazy singleton | Một lần ở thời điểm target lần đầu được khởi tạo | Khi context shutdown nếu target đã tồn tại |
| `prototype` | Mỗi lần Spring tạo một prototype target và khởi tạo nó | Spring **không** tự theo dõi để hủy từng prototype như singleton; consumer chịu trách nhiệm cleanup |
| `request` | Một lần cho mỗi request-scoped target được sử dụng/tạo | Thường khi request scope kết thúc |
| `session` | Một lần cho mỗi HTTP-session-scoped target được tạo | Khi session hết hạn/invalidate |
| `application` | Một lần cho mỗi target trong ServletContext scope | Khi scope/context ứng dụng được kết thúc |
| `websocket` (STOMP) | Một lần cho mỗi WebSocket-session-scoped target được tạo | Khi phiên WebSocket kết thúc |

Một request có thể không tạo request-scoped bean nếu không có đường truy cập đến nó. Tương tự, WebSocket session tồn tại không tự tạo mọi bean websocket scope. `@PostConstruct` chạy khi **instance mục tiêu được khởi tạo**, không phải ngay khi scope được khai báo.

Với bean `prototype` được inject vào singleton bằng constructor, target prototype thường chỉ được tạo một lần **tại thời điểm injection của singleton**. `@PostConstruct` của prototype đó không chạy mỗi lần singleton gọi method của dependency. Muốn mỗi nghiệp vụ có prototype mới, dùng `ObjectProvider<T>.getObject()` vào đúng thời điểm; mỗi target mới sẽ đi qua initialization riêng. Nếu dùng prototype scoped proxy thì việc resolve target có thể diễn ra ở mỗi intercepted method call; cân nhắc state cần giữ nhiều bước.

Với request/session scoped proxy, singleton có thể giữ reference proxy nhưng target `@PostConstruct` thường chạy lần đầu có request/session cần target. Callback thuộc target, **không phải mỗi lời gọi qua proxy**. Proxy cũng không tự mang request context sang thread `@Async`.

## 9. Xử lý exception tại @PostConstruct

Nếu `@PostConstruct` ném runtime exception khi tạo một singleton eager, Spring thường dừng quá trình tạo bean và dẫn đến lỗi khởi tạo context (ví dụ `BeanCreationException` bọc nguyên nhân). Đây là cơ chế **fail fast** hữu ích nếu config bắt buộc không hợp lệ.

```java
@PostConstruct
void validateAndPrepare() {
    if (endpoint == null || endpoint.isBlank()) {
        throw new IllegalStateException("endpoint must be configured");
    }
    parsedEndpoint = java.net.URI.create(endpoint);
}
```

Ví dụ là một fragment của bean có field `endpoint` và `parsedEndpoint`; chúng cần được định nghĩa/inject trong class. Throw làm startup thất bại nếu bean được eagerly instantiated. Nhưng nếu bean lazy hoặc scoped target chưa được tạo, lỗi sẽ xuất hiện muộn tại lần resolve đầu tiên; không được khẳng định mọi validation sẽ xảy ra ngay lúc application startup.

Một số nguyên tắc:
- Thông báo exception nên chứa key cấu hình và hành động sửa, tránh lộ token/password trong error.
- Tránh bắt exception rồi chỉ log và cho bean đi tiếp ở trạng thái nửa khởi tạo.
- Nếu mở file/socket trước lúc throw, cân nhắc try/finally hoặc cleanup ngay trong method. Không dựa vào `@PreDestroy` để rollback mọi trường hợp initialize thất bại: container có thể chưa đăng ký destroy callback cho bean bị lỗi khởi tạo.
- Với external service có thể tạm thời không sẵn sàng, phân biệt **config invalid** (fail fast) với **dependency unavailable** (retry/backoff/readiness). Không dùng busy loop vô hạn trong initialization thread.

## 10. An toàn luồng, công bố trạng thái và tác vụ nền

Một use case tốt là build immutable snapshot trước khi bean được publish:

```java
import java.util.List;
import java.util.Map;
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
class RouteIndex {
    private Map<String, Integer> index = Map.of();

    @PostConstruct
    void prepare() {
        List<String> routes = List.of("/users", "/orders");
        index = Map.of(routes.get(0), 1, routes.get(1), 2);
    }

    int priority(String route) {
        return index.getOrDefault(route, 0);
    }
}
```

Lần publish bình thường của bean qua Spring container giúp consumer truy cập bean đã khởi tạo, và map sau khi build không bị mutate. Trong ví dụ, map immutable rất phù hợp cho nhiều request cùng đọc. Điều đó **không** có nghĩa mọi `HashMap` mutable ghi sau startup đều an toàn: nếu có runtime update, cần lock, immutable replacement qua `volatile`/`AtomicReference`, hoặc concurrent data structure đúng invariant.

### Không khởi động thread bằng cách làm rò rỉ this trong callback

```java
@PostConstruct
void riskyStart() {
    new Thread(() -> useAllBeanState()).start();
}
```

Fragment trên không tự biên dịch vì thiếu method `useAllBeanState`. Nó cố ý mô tả cách dùng cần thận trọng: thread được khởi chạy trước khi các callback init còn lại kết thúc và trước khi bean được publish dưới dạng proxy cuối cùng, có thể quan sát state không đúng kỳ vọng. Việc quản lý stop/join thread cũng phức tạp, nhất là khi bean khởi tạo lỗi hoặc container shutdown.

Nếu cần worker/thread pool:
- Để Spring quản lý `TaskExecutor`/`TaskScheduler` hoặc component có lifecycle phù hợp.
- Chuẩn bị cấu hình nhẹ trong `@PostConstruct`.
- Bắt đầu thực sự khi application/bean lifecycle cho phép, với cơ chế shutdown và error handling rõ.
- Đừng dùng `Thread.sleep` trong init như thủ thuật "đợi mọi bean".
- Giữ method initialize đủ nhanh để tránh kéo dài thời gian khởi động ứng dụng.

## 11. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `@PostConstruct` không chạy | Object tạo bằng `new`, không do Spring quản lý; annotation processor chưa đăng ký | Để Spring tạo bean, dùng `AnnotationConfigApplicationContext`/Boot hoặc đăng ký processor |
| Không compile được import `javax.annotation.PostConstruct` trên Spring 6+ | Dùng namespace cũ / thiếu dependency | Import `jakarta.annotation.PostConstruct` và dependency Jakarta tương thích |
| Field `@Autowired` null trong constructor | Constructor chạy trước field/setter injection | Dùng constructor injection hoặc trì hoãn thao tác đến `@PostConstruct` |
| `@PostConstruct` vẫn thấy null | Injection optional, property chưa khai báo, object ngoài container, xử lý cycle bất thường | Kiểm tra bean wiring, required/Optional và container ownership |
| `@Transactional`/`@Async` trên method được gọi trong `@PostConstruct` không có hiệu lực | Initialization xảy ra trước final AOP proxy; self-invocation | Đưa logic sang collaborator được proxy và trigger ở lifecycle thích hợp |
| Startup chậm/hang | Block network/DB hoặc chạy job dài trong init | Tách workload startup, timeout/retry hợp lý, dùng runner/lifecycle |
| Bean lazy chỉ chạy callback khi request đầu tiên đến | Target chưa được khởi tạo trước đó | Đây là bình thường; nếu cần eager validation, thiết kế dependency/trigger rõ |
| Prototype có callback init nhưng cleanup không chạy | Container không tự quản lý đầy đủ destruction của prototype | Consumer tự đóng resource hoặc dùng scope/lifecycle phù hợp |
| Test với Mockito `new` object và kỳ vọng hook chạy | Unit test không tạo Spring bean | Gọi setup tường minh trong pure unit test hoặc dùng integration test với context |
| `@PostConstruct` lặp lại trên nhiều app instance | Mỗi replica/pod/context có lifecycle riêng | Không dùng làm global exactly-once job; cần distributed coordination |
| Method init được gọi trước khi tất cả bean khác ready | Hook per-bean, không phải whole-app ready event | Dùng lifecycle cấp context/runner nếu cần |
| Runtime cập nhật state sau `@PostConstruct` gây race | Init xong không làm field shared mutable tự thread-safe | Immutable snapshot/lock/atomic theo invariant |

### Chẩn đoán theo từng bước

1. Bean có thực sự được Spring quản lý và được tạo chưa? Kiểm tra container scan/`@Bean`, singleton lazy, active profile, condition.
2. Method có import đúng `jakarta.annotation.PostConstruct`, signature không tham số và `void` không?
3. Có `CommonAnnotationBeanPostProcessor` trong context hiện tại không?
4. Dependency đã được cung cấp chưa, và có optional/lazy/proxy nào có thể resolve muộn không?
5. Có exception sớm hoặc circular reference làm bean initialization thất bại không?
6. Logic đang chạy trên raw target ở init hay đang cần advice chỉ có khi lời gọi đi qua proxy?
7. Callback dự kiến chạy mỗi bean instance, mỗi request hay chỉ một lần toàn cluster? Nếu kỳ vọng khác, hãy đổi thiết kế lifecycle.

## 12. Tình huống thực hành và câu hỏi tự đánh giá

**Tình huống A — cache danh mục đọc nhiều lần:** Một bean inject `ProductRepository` và cần xây một chỉ mục bất biến trước khi service bắt đầu nhận lời gọi. Dùng `@PostConstruct` được nếu dữ liệu nhỏ, lấy dữ liệu nhanh, muốn thất bại khi cấu hình sai và không đòi hỏi transaction/advice qua self-call. Nếu cần load hàng triệu record từ remote service, cân nhắc readiness và startup orchestration khác.

**Tình huống B — kiểm tra cấu hình:** Bean được Spring inject `@Value("${file.format:csv}")`, cần báo lỗi nếu giá trị khác `csv`/`json`. `@PostConstruct` là vị trí hợp lý để validate sau binding. Nếu tham số cấu hình nhiều field và có constraint cấu trúc, hãy xem `@ConfigurationProperties` validation.

**Tình huống C — tự khởi động subscriber:** Bean muốn mở connection, register listener, retry khi disconnect. `@PostConstruct` có thể chuẩn bị dependency/config, nhưng startup/shutdown của listener có trạng thái kéo dài nên thường hợp với `SmartLifecycle` hoặc listener container đã được Spring quản lý.

Câu hỏi:
1. Vì sao `@Autowired` field không có sẵn trong constructor nhưng có thể có sẵn ở `@PostConstruct`?
2. Nếu bean implement `InitializingBean` và có `@Bean(initMethod="customInit")`, thứ tự ba callback init là gì?
3. `@PostConstruct` của singleton lazy chạy khi nào?
4. Prototype bean được yêu cầu tạo ba lần, mỗi target có `@PostConstruct`: sẽ chạy bao nhiêu lần?
5. Vì sao `@PreDestroy` không đáng tin để hủy một prototype bean do Spring tạo?
6. Một method `@PostConstruct` gọi `this.fetch()` với `@Transactional`: có được Spring AOP tự đảm bảo transaction không?
7. Một bean `@RequestScope` đã được proxied nhưng target chưa từng resolve: callback init của target chạy chưa?
8. Bean có `@PostConstruct` chạy xong có nghĩa server HTTP và toàn bộ integration bên ngoài đã ready chưa?
9. Tại sao gọi `new MyComponent()` trong test không tự gọi `@PostConstruct`?
10. Khi nào nên dùng constructor thay cho callback init?

**Đáp án:** (1) Field injection xảy ra sau constructor, trước initialization. (2) `@PostConstruct` → `afterPropertiesSet()` → custom init method. (3) Khi bean thật được tạo lần đầu, không mặc định khi context refresh. (4) Ba lần, nếu cả ba instance thực sự do Spring khởi tạo. (5) Container không quản lý automatic destroy cho prototype. (6) Không, self-invocation/raw target có thể bypass proxy. (7) Chưa; callback gắn với target khi tạo. (8) Chưa. (9) Vì object không đi qua Spring lifecycle processors. (10) Khi đủ dependency bắt buộc để thiết lập invariant tại thời điểm construction.

## Tài liệu chính thức

- Spring Framework — Using @PostConstruct and @PreDestroy: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html
- Spring Framework — Customizing the Nature of a Bean (lifecycle callbacks, order): https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — Annotation-based Container Configuration: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html
- Spring Framework — Using @Autowired: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html
- Spring Framework — Using the @Bean Annotation: https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html
- Spring Framework — Container Extension Points (BeanPostProcessor): https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Jakarta Annotations specification — @PostConstruct: https://jakarta.ee/specifications/annotations/2.1/apidocs/jakarta.annotation/jakarta/annotation/postconstruct
