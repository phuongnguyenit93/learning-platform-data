# Tiêm qua phương thức cấu hình có nhiều tham số trong Spring Core Container

## 1. Mục tiêu của bài

Một bean thường cần **nhiều cộng tác viên** cùng lúc: ví dụ cần repository để đọc dữ liệu, formatter để định dạng, audit sink để ghi nhật ký và metrics sink để ghi số liệu. Spring Core Container có thể tự tìm bean thích hợp và **truyền từng tham số** vào một phương thức cấu hình (*configuration method*) được đánh dấu `@Autowired`.

Điều đáng chú ý là phương thức đó:

- **Không bắt buộc có tên `set...`** như JavaBeans setter. Có thể tên `configure`, `prepare` hay `attachInfrastructure`.
- Có thể nhận **nhiều tham số với nhiều kiểu khác nhau** trong một lời gọi.
- Được Spring gọi trong **quá trình cấu hình bean**, không phải mỗi khi ứng dụng gọi một nghiệp vụ.
- Có mặc định `required=true`; nếu dùng `required=false` trên phương thức, Spring có thể **bỏ qua cả phương thức** khi một dependency cần thiết không tồn tại.
- Khác với `@Bean`: phương thức `@Bean` là **factory method tạo/công bố một bean**, còn phương thức `@Autowired` thông thường **cấu hình một bean đã được tạo**.

Bài này đi từ cơ chế, trường hợp nhiều tham số, cách chọn bean, sự khác nhau giữa dependency bắt buộc và tùy chọn, rồi tới ví dụ Spring Framework 6.2 + Java 17 độc lập có lệnh Maven và stdout cụ thể.

~~~text
ApplicationContext
    |
    | (1) gọi factory method có nhiều tham số
    |     @Bean OrderEngine orderEngine(
    |           Repository repository,
    |           Formatter formatter,
    |           @Value(...) String label)
    v
 OrderEngine instance (đã có repository, formatter, label)
    |
    | (2) BeanPostProcessor xử lý @Autowired
    |     configureExtras(AuditSink audit, MetricSink metrics)
    |            |
    |            +-- cả hai có sẵn -> gọi method một lần
    |            +-- thiếu một, required=false -> không gọi method
    |
    v
 bean sẵn sàng dùng -> execute(orderId)
~~~

Vì vậy cần phân biệt **tạo object**, **tiêm tham số để cấu hình**, và **thực thi method nghiệp vụ**. Đây là ba giai đoạn khác nhau.

## 2. `@Autowired` trên phương thức bất kỳ có nhiều tham số

### 2.1. Cú pháp cơ bản

~~~java
public final class ReportService {
    private Formatter formatter;
    private AuditSink auditSink;

    @Autowired
    public void configure(Formatter formatter, AuditSink auditSink) {
        this.formatter = formatter;
        this.auditSink = auditSink;
    }
}
~~~

Đây là **mã minh họa**, chưa runnable độc lập vì các kiểu `Formatter`, `AuditSink` và import `@Autowired` chưa được cung cấp trong khối này. Ý nghĩa quan trọng:

1. Spring tạo một `ReportService` theo bean definition.
2. `AutowiredAnnotationBeanPostProcessor` nhận diện method `configure`.
3. Spring giải quyết **mỗi parameter** theo metadata/kiểu và những qualifier phù hợp.
4. Nếu thỏa mãn các dependency cần thiết, container gọi `configure(formatterBean, auditBean)` để gán trạng thái.
5. Bean đi qua những bước initialization/lifecycle còn lại; sau đó mới nên đưa vào luồng sử dụng thông thường.

Vì method chỉ cấu hình object, thường sử dụng `void` return type. Nó có thể khai báo visibility phù hợp, không bắt buộc public, nhưng nên tránh những phương thức static cho mục đích này và tránh lạm dụng reflection/access khó kiểm soát.

**Đừng nhầm đây với mỗi lần gọi ứng dụng:** Spring **không** tự gọi `configure` trước từng lần `service.generate()`. Với singleton bean thông thường, cấu hình injection hoàn tất một lần trong quá trình tạo bean. Với prototype, mỗi object được tạo có quy trình cấu hình riêng.

### 2.2. Setter injection là một trường hợp của method injection

Setter quen thuộc:

~~~java
@Autowired
public void setFormatter(Formatter formatter) {
    this.formatter = formatter;
}
~~~

đơn giản là **method injection có một tham số**, tuân theo quy ước tên JavaBeans. Method injection có thể nhận nhiều tham số:

~~~java
@Autowired
public void configure(Formatter formatter,
                      AuditSink auditSink,
                      MetricsSink metricsSink) {
    this.formatter = formatter;
    this.auditSink = auditSink;
    this.metricsSink = metricsSink;
}
~~~

Tên `configure` không vi phạm quy tắc `@Autowired`; annotation cho Spring biết đó là injection point. Mã ở hai khối này chỉ để so sánh cấu trúc; các interface/field cần được định nghĩa khi tạo project thực.

Một phương thức có nhiều tham số phù hợp khi các dependency **cùng cấu thành một bước cấu hình có nghĩa**, ví dụ một nhóm bộ phận cần được gắn đồng thời. Không nên gom mọi cộng tác viên không liên quan vào một method chỉ để giảm số lượng setter hoặc che những vấn đề về trách nhiệm của lớp.

## 3. Required semantics: phương thức nhiều tham số là một injection point

### 3.1. `@Autowired` mặc định yêu cầu dependency

~~~java
@Autowired
public void configure(Repository repository,
                      Formatter formatter) {
    this.repository = repository;
    this.formatter = formatter;
}
~~~

Mặc định là `required=true`. Khi Spring không tìm được một tham số cần thiết, bean creation thường thất bại với lỗi dependency; nó không gọi method với một đối số ngẫu nhiên hay lặng lẽ bỏ qua injection bắt buộc.

Một số lỗi cần phân biệt:

- **Không có ứng viên** phù hợp: có thể phát sinh `UnsatisfiedDependencyException` với nguyên nhân liên quan tới `NoSuchBeanDefinitionException`.
- **Có nhiều bean cùng kiểu nhưng không phân giải được**: thường do `NoUniqueBeanDefinitionException` trong chuỗi nguyên nhân.
- **Bean ứng viên tồn tại nhưng constructor/factory của chính bean đó lỗi**: vẫn có thể làm việc tạo bean thất bại.
- **Method body ném exception khi được gọi**: không phải lỗi “thiếu dependency”; Spring có thể bọc lỗi như bean creation failure.

Nên đọc nguyên nhân gốc trong stack trace, không sửa cấu hình chỉ dựa vào tên exception ngoài cùng.

### 3.2. `@Autowired(required = false)`: bỏ qua toàn bộ method

~~~java
@Autowired(required = false)
public void configureExtras(AuditSink audit,
                            MetricSink metrics) {
    this.audit = audit;
    this.metrics = metrics;
    this.extrasConfigured = true;
}
~~~

Đây là **đoạn minh họa**, nằm trong chương trình đầy đủ ở mục 6. Quy tắc đặc biệt quan trọng:

- Nếu có **cả hai** bean, Spring có thể gọi method và truyền đủ hai argument.
- Nếu **thiếu `MetricSink`** nhưng có `AuditSink`, Spring **không gọi `configureExtras`** và không “gọi một nửa phương thức” với `null`.
- Nếu không có cả hai, method cũng bị bỏ qua.
- Những field ban đầu vẫn giữ giá trị mặc định của object, ví dụ `extrasConfigured=false`.
- `required=false` **không** giải quyết mơ hồ do hai bean ứng viên `MetricSink` và cũng không nuốt mọi lỗi khởi tạo bean.

Hãy xem nhóm hai dependency này như **một điểm cấu hình tùy chọn có tính nguyên khối** (*all-or-nothing*). Nếu muốn audit hoạt động dù metrics thiếu, **đừng** đặt cả hai vào một method non-required rồi kỳ vọng audit tự có; thay đổi cách thiết kế injection.

| Ngữ cảnh | `AuditSink` | `MetricSink` | `configureExtras` với `required=false` |
| --- | --- | --- | --- |
| Đầy đủ | Có | Có | Được gọi, gắn cả hai |
| Thiếu metrics | Có | Không | Bị bỏ qua hoàn toàn |
| Thiếu audit | Không | Có | Bị bỏ qua hoàn toàn |
| Thiếu cả hai | Không | Không | Bị bỏ qua hoàn toàn |

Bảng giả định các kiểu mỗi bên có một bean phù hợp, không có lỗi khác; nó không hứa về cơ chế mơ hồ khi nhiều candidates.

### 3.3. Khi nhiều tùy chọn độc lập, nên tách method

Ví dụ:

~~~java
@Autowired(required = false)
public void setAuditSink(AuditSink sink) {
    this.auditSink = sink;
}

@Autowired(required = false)
public void setMetricSink(MetricSink sink) {
    this.metricSink = sink;
}
~~~

Hai injection points độc lập: chỉ có audit thì setter audit vẫn được gọi; thiếu metric chỉ khiến setter metric bị bỏ qua. Cách này phù hợp nếu hai khả năng thực sự không phụ thuộc nhau.

Còn nếu hai dependency phải được cài chung để bảo đảm invariant, một method `configureExtras(audit, metrics)` là thiết kế có chủ đích, nhưng phải có **fallback hành vi** khi method bị bỏ qua.

## 4. Tùy chọn trên từng tham số: `Optional<T>`, `@Nullable` và provider

### 4.1. Một method vẫn được gọi khi tham số riêng lẻ optional

~~~java
@Autowired
public void configure(AuditSink audit,
                      java.util.Optional<MetricSink> metrics) {
    this.audit = audit;
    this.metricsEnabled = metrics.isPresent();
}
~~~

Spring có hỗ trợ `Optional<MetricSink>` như một injection point không bắt buộc. Khi có `AuditSink` nhưng thiếu `MetricSink`, method **vẫn có thể được gọi**, với `Optional.empty()` ở tham số metrics. Ngược lại, nếu **chính `AuditSink`** thiếu, method mặc định vẫn không thỏa requirement vì tham số đó bắt buộc.

Đây là khác biệt quan trọng với toàn method `@Autowired(required=false)`:

| Tình trạng | Method `required=false` có 2 tham số thường | Method `@Autowired` với `AuditSink, Optional<MetricSink>` |
| --- | --- | --- |
| Có audit và metrics | Gọi | Gọi, `Optional` chứa metrics |
| Có audit, thiếu metrics | Bỏ qua toàn method | Gọi, `Optional.empty()` |
| Thiếu audit, có metrics | Bỏ qua toàn method | Không thỏa dependency bắt buộc của audit |

Mã minh họa sẽ được triển khai trên một bean `OptionalObserver` trong chương trình chạy mục 6, để bạn so sánh kết quả cùng lúc.

### 4.2. `@Nullable` và `ObjectProvider<T>`

Trong một số phiên bản Spring, có thể khai báo parameter nullable theo annotation được Spring hỗ trợ để biểu đạt tính tùy chọn. Khi dùng Spring Framework 6.x, cần chọn đúng annotation nullability phù hợp module/phiên bản thực tế, không tùy tiện gắn một annotation bất kỳ rồi mong Spring hiểu.

`ObjectProvider<MetricSink>` là lựa chọn khác nếu **muốn tra dependency lúc cần**, thay vì chốt reference khi cấu hình:

~~~java
@Autowired
public void configure(ObjectProvider<MetricSink> metricsProvider) {
    this.metricsProvider = metricsProvider;
}
~~~

Đây là đoạn minh họa, cần import `org.springframework.beans.factory.ObjectProvider` và field tương ứng. Code có thể gọi `metricsProvider.getIfAvailable()` ở thời điểm xử lý để yêu cầu bean nếu có. Với nhiều candidates, phải xem xét quy tắc resolution; provider không tự tạo ra một ứng viên “đúng ý” khi cấu hình mơ hồ.

Dùng `Optional<T>` khi chỉ muốn một quyết định có/không tại lúc cấu hình. Dùng provider khi cần cấp bean theo nhu cầu, prototype hoặc một cơ chế lookup động có chủ đích; tránh tạo abstraction phức tạp nếu chỉ cần một tham số ổn định.

## 5. Phân biệt `@Autowired` config method và `@Bean` factory method

Hai loại method cùng nhận nhiều tham số nhưng **khác vai trò**.

### 5.1. `@Autowired` instance method

~~~java
public final class OrderEngine {
    @Autowired(required = false)
    public void configureExtras(AuditSink audit, MetricSink metrics) {
        // Lưu reference để dùng sau.
    }
}
~~~

Method thuộc **bean đã được tạo**, do Spring gọi để cấu hình object. Nó **không đăng ký một bean mới** chỉ vì được đánh dấu `@Autowired`; giá trị trả về (nếu khai báo) không phải bean product giống `@Bean`.

### 5.2. `@Bean` factory method nhận nhiều tham số

~~~java
@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean
    public OrderEngine orderEngine(Repository repository,
                                   Formatter formatter,
                                   @Value("${app.label:BASE}") String label) {
        return new OrderEngine(repository, formatter, label);
    }
}
~~~

Đây là trích đoạn từ chương trình hoàn chỉnh mục 6. Spring:

1. Xác định một bean definition qua `@Bean` method `orderEngine`.
2. Giải quyết `Repository` và `Formatter` bằng type và các metadata chọn ứng viên.
3. Resolve placeholder `${app.label:BASE}` thành chuỗi cấu hình có default `BASE`.
4. Gọi factory method với **ba argument đã xác định**; instance trả về trở thành Spring-managed bean `orderEngine`.
5. Sau đó, nếu bean class có `@Autowired` methods, các phương thức cấu hình được xử lý trong lifecycle thích hợp.

**Không cần thêm `@Autowired` lên `@Bean` method** để Spring truyền tham số. `@Bean` đã khai báo điểm tạo bean và cơ chế giải quyết factory arguments.

### Bảng phân biệt

| Tính chất | `@Autowired` config method | `@Bean` factory method |
| --- | --- | --- |
| Nằm ở đâu? | Một bean do container quản lý | Lớp `@Configuration` hoặc component cấu hình phù hợp |
| Mục đích | Thiết lập dependency lên object đã tạo | Tạo hoặc trả object để công bố thành bean |
| Có thể nhận nhiều tham số? | Có | Có |
| Tên method phải `setX`? | Không | Không |
| Return value tạo bean? | Không | **Có**, product của `@Bean` |
| `required=false` áp dụng thế nào? | Cả method có thể bị bỏ qua nếu thiếu một dependency | Thông thường factory parameters là requirements; tùy chọn thể hiện qua `Optional`/provider/default phù hợp |
| Khi nào chạy? | Trong giai đoạn cấu hình bean | Khi container cần tạo bean theo scope/lazy |
| Bản thân gọi method nghiệp vụ mỗi request? | Không | Không |

Đừng gắn `@Autowired(required=false)` lên một `@Bean` factory method chỉ để giải quyết việc thiếu bean: cơ chế resolution của factory method không nên bị hiểu như một arbitrary configuration method. Thay vào đó dùng `Optional<T>` hoặc cấu hình conditional/factory phù hợp.

## 6. Ứng dụng Spring Framework 6.2 / Java 17 chạy được

Ví dụ có **hai `ApplicationContext` độc lập**. Cả hai chứa repository, formatter và audit bean:

- **Context 1:** không có metrics bean. Phương thức `OrderEngine.configureExtras(AuditSink, MetricSink)` được gắn `@Autowired(required=false)`, vì thiếu metrics nên **không chạy**. Ngược lại, `OptionalObserver.configure(AuditSink, Optional<MetricSink>)` vẫn chạy và nhận `Optional.empty()`.
- **Context 2:** đăng ký thêm metrics bean và đưa property `app.label=CUSTOM` vào environment trước khi refresh. Cả hai phương thức đều được gọi; use case in audit và metric trước khi in kết quả.

### 6.1. Cấu trúc project

Yêu cầu **JDK 17+**, Maven và kết nối tới Maven repository ở lần tải dependencies đầu tiên. Không dùng Spring Boot, database, web server hoặc HTTP.

~~~text
multi-arg-injection/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MultiArgumentDemo.java
~~~

Tạo file `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>multi-arg-injection</artifactId>
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
                    <mainClass>demo.MultiArgumentDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. File Java hoàn chỉnh

Tạo `src/main/java/demo/MultiArgumentDemo.java`:

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.core.env.MapPropertySource;

public final class MultiArgumentDemo {
    private MultiArgumentDemo() {}

    public interface Repository {
        String find(String id);
    }

    public static final class DemoRepository implements Repository {
        @Override
        public String find(String id) {
            return "ROW(" + id + ")";
        }
    }

    public interface Formatter {
        String format(String text);
    }

    public static final class BracketFormatter implements Formatter {
        @Override
        public String format(String text) {
            return "[" + text + "]";
        }
    }

    public interface AuditSink {
        void record(String id);
    }

    public static final class ConsoleAuditSink implements AuditSink {
        @Override
        public void record(String id) {
            System.out.println("AUDIT " + id);
        }
    }

    public interface MetricSink {
        void record(String id);
    }

    public static final class ConsoleMetricSink implements MetricSink {
        @Override
        public void record(String id) {
            System.out.println("METRIC " + id);
        }
    }

    public static final class OrderEngine {
        private final Repository repository;
        private final Formatter formatter;
        private final String label;
        private AuditSink audit;
        private MetricSink metrics;
        private boolean extrasConfigured;

        public OrderEngine(Repository repository,
                           Formatter formatter,
                           String label) {
            this.repository = Objects.requireNonNull(repository);
            this.formatter = Objects.requireNonNull(formatter);
            this.label = Objects.requireNonNull(label);
        }

        // Method có tên bất kỳ và 2 tham số.
        // Nếu thiếu dù chỉ một dependency, method bị bỏ qua.
        @Autowired(required = false)
        public void configureExtras(AuditSink audit, MetricSink metrics) {
            this.audit = Objects.requireNonNull(audit);
            this.metrics = Objects.requireNonNull(metrics);
            this.extrasConfigured = true;
        }

        public boolean extrasConfigured() {
            return extrasConfigured;
        }

        public String execute(String id) {
            String row = repository.find(id);
            if (extrasConfigured) {
                audit.record(id);
                metrics.record(id);
            }
            return label + ":" + formatter.format(row);
        }
    }

    public static final class OptionalObserver {
        private boolean methodCalled;
        private boolean metricsPresent;

        @Autowired
        public void configure(AuditSink audit,
                              Optional<MetricSink> metrics) {
            Objects.requireNonNull(audit);
            this.methodCalled = true;
            this.metricsPresent = metrics.isPresent();
        }

        public boolean methodCalled() {
            return methodCalled;
        }

        public boolean metricsPresent() {
            return metricsPresent;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class CoreConfig {
        @Bean
        public Repository repository() {
            return new DemoRepository();
        }

        @Bean
        public Formatter formatter() {
            return new BracketFormatter();
        }

        @Bean
        public AuditSink auditSink() {
            return new ConsoleAuditSink();
        }

        // Factory method nhiều tham số tự được Spring resolve.
        @Bean
        public OrderEngine orderEngine(Repository repository,
                                       Formatter formatter,
                                       @Value("${app.label:BASE}") String label) {
            return new OrderEngine(repository, formatter, label);
        }

        @Bean
        public OptionalObserver optionalObserver() {
            return new OptionalObserver();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import(CoreConfig.class)
    public static class WithMetricsConfig {
        @Bean
        public MetricSink metricSink() {
            return new ConsoleMetricSink();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CoreConfig.class)) {
            OrderEngine engine = context.getBean(OrderEngine.class);
            OptionalObserver observer =
                    context.getBean(OptionalObserver.class);

            System.out.println("-- no metrics --");
            System.out.println("ENGINE_METHOD " + engine.extrasConfigured());
            System.out.println("OBSERVER_METHOD " + observer.methodCalled());
            System.out.println("OBSERVER_METRICS " + observer.metricsPresent());
            System.out.println("RESULT " + engine.execute("A1"));
        }

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Property phải được cung cấp trước refresh.
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("demo",
                            Map.of("app.label", "CUSTOM")));

            context.register(WithMetricsConfig.class);
            context.refresh();

            OrderEngine engine = context.getBean(OrderEngine.class);
            OptionalObserver observer =
                    context.getBean(OptionalObserver.class);

            System.out.println("-- with metrics --");
            System.out.println("ENGINE_METHOD " + engine.extrasConfigured());
            System.out.println("OBSERVER_METHOD " + observer.methodCalled());
            System.out.println("OBSERVER_METRICS " + observer.metricsPresent());
            System.out.println("RESULT " + engine.execute("B2"));
        }
    }
}
~~~

### 6.3. Biên dịch và chạy

Từ thư mục `multi-arg-injection` có `pom.xml`:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

Maven có thể in tiến trình tải dependencies hoặc log tùy cấu hình. **Các dòng stdout do logic `MultiArgumentDemo` chủ động in, theo đúng thứ tự:**

~~~text
-- no metrics --
ENGINE_METHOD false
OBSERVER_METHOD true
OBSERVER_METRICS false
RESULT BASE:[ROW(A1)]
-- with metrics --
ENGINE_METHOD true
OBSERVER_METHOD true
OBSERVER_METRICS true
AUDIT B2
METRIC B2
RESULT CUSTOM:[ROW(B2)]
~~~

`mvn -version` còn in thông tin Maven/JDK. Khối trên mô tả **dòng do code ví dụ in**, không hứa rằng toàn bộ output terminal chỉ có các dòng đó.

### 6.4. Phân tích từng bước kết quả

**Context 1 — không có metrics:**

1. Spring đọc `CoreConfig`, tạo ba bean dependency `Repository`, `Formatter`, `AuditSink` và các bean service theo `@Bean`.
2. Method `orderEngine(Repository, Formatter, String)` nhận repository, formatter và label từ placeholder. Không có `app.label` nên `@Value("${app.label:BASE}")` trả `BASE`.
3. Spring tạo `OrderEngine` rồi xử lý `@Autowired(required=false)` trên `configureExtras(AuditSink, MetricSink)`.
4. Vì **không có bean `MetricSink`**, toàn method bị bỏ qua, `extrasConfigured` giữ mặc định `false`. Bean audit có tồn tại nhưng **không được gắn một mình** vào engine.
5. Spring tạo `OptionalObserver` rồi gọi `configure(AuditSink, Optional<MetricSink>)`; `AuditSink` có, `MetricSink` không, nên truyền `Optional.empty()` và đặt `methodCalled=true`, `metricsPresent=false`.
6. Lệnh `execute("A1")` lấy `ROW(A1)`, áp dụng formatter thành `[ROW(A1)]`, trả `BASE:[ROW(A1)]` mà không in audit hay metric.

**Context 2 — có metrics:**

1. `MapPropertySource` cung cấp `app.label=CUSTOM` trước `refresh()`, nên factory method nhận `CUSTOM`.
2. `WithMetricsConfig` import `CoreConfig` và bổ sung bean `MetricSink`.
3. Lần này cả `AuditSink` và `MetricSink` đều tồn tại, nên Spring gọi `configureExtras(...)`; `extrasConfigured=true`.
4. `OptionalObserver.configure(...)` được gọi, và `Optional<MetricSink>` chứa giá trị, nên `metricsPresent=true`.
5. Lệnh `execute("B2")` gọi audit và metric **trước khi trả chuỗi kết quả**. Hai dòng `AUDIT B2`, `METRIC B2` xuất hiện trước dòng `RESULT CUSTOM:[ROW(B2)]` do `main` in.

Hai context không chia sẻ các singleton instance mặc định; chúng chạy tuần tự và được đóng riêng. Không có database transaction, HTTP server hay Spring AOP trong ví dụ.

**Lưu ý:** Chương trình không in dòng nào trong constructor hoặc các `@Bean` factory methods, vì thế stdout không phụ thuộc vào thứ tự tạo singleton không liên quan.

## 7. Dùng `@Qualifier` và `@Primary` với nhiều tham số

Khi hai bean cùng thực hiện một interface, chỉ type có thể chưa đủ để chọn:

~~~java
@Bean("fastFormatter")
Formatter fastFormatter() { return new FastFormatter(); }

@Bean("safeFormatter")
Formatter safeFormatter() { return new SafeFormatter(); }
~~~

Đây là ví dụ **minh họa, chưa runnable**, thiếu hai class. Nếu method nhận một `Formatter` nhưng có nhiều candidates không xác định được lựa chọn, có thể thất bại vì mơ hồ.

Cách chọn rõ ngay trên **từng tham số**:

~~~java
@Autowired
public void configure(@Qualifier("safeFormatter") Formatter formatter,
                      AuditSink audit) {
    this.formatter = formatter;
    this.audit = audit;
}
~~~

Đoạn này cần import `org.springframework.beans.factory.annotation.Qualifier` và các field/interface thích hợp.

- `@Qualifier("safeFormatter")` giúp giới hạn ứng viên của tham số formatter.
- `AuditSink` vẫn được resolve độc lập theo type/qualifier của nó.
- `@Primary` đặt trên một bean candidate có thể cung cấp ưu tiên mặc định cho single-valued injection.
- Khi có nhiều bean primary cùng phù hợp hoặc qualifier không khớp, phải xem nguyên nhân cụ thể; không nên dựa vào thứ tự khai báo bean.

**Với nhiều tham số, mỗi tham số có metadata lựa chọn riêng.** Một annotation qualifier trên tham số formatter không quyết định cách giải quyết tham số audit.

Một chi tiết cần biết: `@Resource` theo JSR-250 chủ yếu dùng cho field hoặc setter JavaBeans với **một tham số**; nó không phải công cụ thay thế trực tiếp cho một arbitrary method `@Autowired` nhiều tham số. Spring hỗ trợ tham số qualifiers trong config method phù hợp hơn cho tình huống này.

## 8. Method injection với collection và nhiều implementation

Spring có thể inject các nhóm bean theo kiểu:

~~~java
@Autowired
public void configureAll(List<Formatter> formatters,
                         Map<String, AuditSink> audits) {
    this.formatters = formatters;
    this.audits = audits;
}
~~~

Đây là **đoạn minh họa**, cần `java.util.List`, `java.util.Map` và các field/class thực tế. Khi đủ điều kiện, `List<Formatter>` nhận các formatter beans phù hợp; `Map<String, AuditSink>` dùng bean names làm keys và bean instances làm values.

Những điểm cần lưu ý:

- List, array, Set và Map có semantics riêng; không dựa vào thứ tự Map nếu chưa có quy tắc được bảo đảm.
- `@Order`/`Ordered` có thể ảnh hưởng tới thứ tự injection của collection phù hợp, nhưng **không phải metadata chọn primary cho một tham số duy nhất**.
- Với `@Autowired(required=true)` trên một method thông thường, collection rỗng có thể không thỏa requirement nếu không có bean phù hợp; có ngoại lệ ở một số đường resolution của constructor/factory method. Vì vậy nếu collection có thể rỗng, hãy thiết kế/kiểm tra theo API và phiên bản Spring thực tế.
- Một multi-argument config method có collection và scalar required vẫn phải giải quyết các tham số thích hợp theo cùng injection point.

**Không tự thêm một `@Bean List<Formatter>` chỉ để dùng nhiều formatter** khi mục tiêu thực tế là “inject tất cả beans thuộc interface”; Spring hỗ trợ collection injection trực tiếp trong tình huống tương ứng.

## 9. Thời điểm Spring gọi config method và vòng đời

`@Autowired` annotation được xử lý bởi bean post-processing của Spring:

~~~text
instantiate bean (constructor hoặc factory)
    |
    +--> populate properties / @Autowired method injection
    |
    +--> aware callbacks, @PostConstruct / init callbacks phù hợp
    |
    +--> bean sẵn sàng cho getBean / injection tiếp theo
~~~

Sơ đồ tổng quát, không phải toàn bộ thứ tự extension points trong mọi cấu hình.

Một số hệ quả:

1. **Method injection là bước cấu hình**: method nên thiết lập reference/khởi tạo cấu hình cần thiết, không phải chạy ca sử dụng của khách hàng.
2. **Thời điểm có thể sớm**: non-lazy singleton thường được tạo lúc `ApplicationContext.refresh()`, nên config method cũng có thể chạy từ startup.
3. **Scope quan trọng**: prototype bean mới có quy trình injection riêng ở mỗi lần được yêu cầu; singleton thông thường được cấu hình một lần trong container.
4. **Không tự chạy trên object tạo tay**: `new OrderEngine(...)` ngoài Spring container không kích hoạt `@Autowired` method. Unit test có thể tự gọi method cần cấu hình.
5. **Đừng tạo dependency cycle một cách vô ý**: nếu config method của A đòi B, còn B lại đòi A, bạn có thể gặp vòng phụ thuộc và lỗi khởi tạo; đừng dùng setter chỉ để che lỗi thiết kế.
6. **Không hot-reload tự động**: việc thay bean definition/PropertySource sau khi bean đã được cấu hình không có nghĩa Spring tự gọi lại mọi config method để cập nhật bean.

Phương thức nhiều tham số lý tưởng nên có tác dụng ngắn, xác định và không chứa I/O khó kiểm soát. Nếu là bean singleton dùng nhiều thread, tránh thay các field cấu hình từ thread khác sau khi bean đã chạy mà không thiết kế concurrency đúng.

## 10. Vì sao constructor injection vẫn được khuyến nghị cho dependency bắt buộc?

Nếu repository/formatter là điều kiện cần để xử lý request, giữ chúng trong constructor:

~~~java
public OrderEngine(Repository repository,
                   Formatter formatter,
                   String label) {
    this.repository = Objects.requireNonNull(repository);
    this.formatter = Objects.requireNonNull(formatter);
    this.label = Objects.requireNonNull(label);
}
~~~

Các field constructor có thể `final`; object được tạo là có đủ điều kiện tối thiểu để chạy. Những phần mở rộng audit/metrics được nhóm ở `configureExtras` vì demo muốn minh họa chúng là một **cấu hình bổ sung** có thể có hoặc không.

**Không phải quy tắc cứng rằng constructor tốt còn mọi setter sai**. Điều quan trọng là:

- Required dependency nên hiện rõ trong constructor.
- Optional dependency có thể đi qua setter/config method hoặc `Optional<T>`.
- Những dependency cần thiết lập nguyên khối có thể nhóm trong một method nhiều tham số, với semantics rõ.
- Một class có quá nhiều dependencies có thể đang ôm nhiều nhiệm vụ; cân nhắc tách responsibilities, không chỉ “chuyển hết sang config method”.

Phương thức được đánh dấu `@Autowired` không buộc domain phải khởi tạo Spring context trong test: đó vẫn là method Java bình thường, có thể gọi trực tiếp nếu cần.

## 11. Những hiểu nhầm và lỗi thường gặp

| Hiểu nhầm / lỗi | Cách hiểu đúng |
| --- | --- |
| “`@Autowired` chỉ dùng được cho constructor và setter.” | Có thể áp dụng trên arbitrary instance method nhận nhiều tham số. |
| “Method tên `prepare` sẽ bị bỏ qua vì không bắt đầu bằng `set`.” | Tên method không phải điều kiện của `@Autowired`. |
| “Method nhiều tham số được Spring gọi riêng một lần cho từng tham số.” | Spring giải quyết argument rồi gọi method như một lời gọi Java. |
| “`required=false` khiến dependency thiếu được truyền `null` và method vẫn chạy.” | Nếu thiếu một dependency, non-required method có thể bị bỏ qua **toàn bộ**. |
| “`Optional<MetricSink>` khiến toàn method mặc định tùy chọn.” | Chỉ parameter tương ứng optional; dependency khác vẫn có thể required. |
| “`required=false` xử lý luôn lỗi nhiều bean mơ hồ.” | Cần qualifier/primary hoặc lựa chọn rõ. |
| “`@Bean` method nhiều tham số cần `@Autowired` để được inject.” | Spring tự resolve factory method arguments. |
| “`@Autowired` config method tạo thêm một bean.” | Nó cấu hình bean đang tồn tại; `@Bean` method mới khai báo bean product. |
| “`@Value` tự lấy từ `application.properties` như Spring Boot.” | Spring Framework thuần cần environment/property sources phù hợp; ví dụ dùng MapPropertySource rõ ràng. |
| “`@Autowired` chạy trên bất cứ object nào tạo bằng `new`.” | Annotation xử lý bởi Spring container, không phải JVM tự gọi. |
| “Có bean thiếu nhưng vẫn cho method chạy một nửa.” | Một method invocation là nguyên khối; Spring không tự gọi với danh sách tham số thiếu. |
| “Một config method có 20 tham số là thiết kế tốt vì ít method.” | Có thể là dấu hiệu class làm quá nhiều việc, cần tách responsibility. |
| “Qualifier chọn formatter cũng chọn luôn audit.” | Từng tham số có metadata resolution riêng. |
| “Bean singleton tự động thread-safe.” | Injection/scope không tự tạo đồng bộ cho mutable state. |
| “Đặt `@Autowired` trên business method thì Spring sẽ gọi trước từng request.” | Không, nó là config injection point, không phải request interceptor. |

### Các lỗi chẩn đoán phổ biến

- `NoSuchBeanDefinitionException`: dependency type được yêu cầu mà context không có.
- `NoUniqueBeanDefinitionException`: nhiều candidates cho một tham số và không thể chọn.
- `UnsatisfiedDependencyException`: injection point không thỏa.
- `BeanCreationException`: lỗi tạo/configure/init bean, thường bọc nguyên nhân bên trong.
- `BeanCurrentlyInCreationException`: vòng phụ thuộc chưa được giải quyết.
- `IllegalArgumentException` từ config method: ví dụ setter kiểm tra tham số hoặc business invariant không hợp lệ.

Đọc **bean name và tên injection point** trong stack trace trước khi thay cấu hình. Không đánh dấu toàn bộ method `required=false` chỉ để che một dependency thực sự bắt buộc.

## 12. Bài tập kèm đáp án

**Bài 1.** Method `@Autowired(required=false) void configure(AuditSink a, MetricSink m)` có audit bean nhưng không có metrics bean. Spring sẽ gọi method với `m=null` hay không gọi?

**Đáp án:** Không gọi method trong trường hợp thiếu dependency; những field ban đầu giữ trạng thái mặc định. Đó là semantics non-required method, không phải partial injection.

**Bài 2.** Method `@Autowired void configure(AuditSink a, Optional<MetricSink> m)` với audit có, metrics thiếu sẽ xảy ra điều gì?

**Đáp án:** Method được gọi với audit bean và `Optional.empty()` cho metrics, nếu không có lỗi khác. Đây là optionality **trên một parameter**.

**Bài 3.** Một method trong `@Configuration` là `@Bean Foo foo(Bar bar, Baz baz)`. Có phải gắn `@Autowired` lên nó mới nhận đủ hai dependency?

**Đáp án:** Không. Container nhận biết factory method là điểm tạo bean qua `@Bean` và tự giải quyết các tham số thích hợp.

**Bài 4.** Vì sao context đầu tiên của demo in `ENGINE_METHOD false` nhưng `OBSERVER_METHOD true`?

**Đáp án:** Engine config method required=false thiếu `MetricSink` nên bị bỏ qua; observer method có tham số `Optional<MetricSink>` nên vẫn được gọi với `Optional.empty()`.

**Bài 5.** Vì sao `AUDIT B2` và `METRIC B2` xuất hiện trước dòng `RESULT CUSTOM:[ROW(B2)]`?

**Đáp án:** `OrderEngine.execute` gọi hai collaborator trước khi trả chuỗi. `main` chỉ in kết quả sau khi method trả về.

**Bài 6.** Nếu bean `Formatter` có hai implementation và cả hai đều được đăng ký, giải quyết thế nào?

**Đáp án:** Cung cấp một quy tắc lựa chọn có chủ đích, ví dụ qualifier ngay trên tham số hoặc bean primary phù hợp. Không dựa vào thứ tự method trong source file.

**Bài 7.** Nếu một config method lấy `List<AuditSink>`, nó có giống một tham số `AuditSink` không?

**Đáp án:** Không. Collection injection có thể nhận nhiều beans phù hợp; còn tham số đơn cần chọn đúng một candidate.

**Bài 8.** Nếu `new OrderEngine(repo, fmt, label)` bên ngoài Spring, `@Autowired(required=false) configureExtras(...)` có tự chạy không?

**Đáp án:** Không. Chỉ annotation trong class chưa đủ. Nếu cần cấu hình thủ công, gọi method hoặc dùng factory thích hợp.

**Bài 9.** Để hai tham số audit và metric tùy chọn **độc lập** với nhau, nên thiết kế sao?

**Đáp án:** Chia thành hai injection methods non-required riêng, hoặc biểu đạt tính tùy chọn độc lập bằng `Optional<T>`/provider tùy trường hợp.

## 13. Checklist cho dự án

- [ ] Phân biệt `@Autowired` configuration method với `@Bean` factory method.
- [ ] Đảm bảo bean cần được config đã đăng ký trong Spring context.
- [ ] Method được đánh dấu `@Autowired` là instance method có signature rõ ràng; tên không cần `set...`.
- [ ] Kiểm tra tất cả parameter types có ứng viên tương ứng.
- [ ] Khi có nhiều ứng viên, chọn bằng `@Qualifier`/`@Primary` đúng tham số.
- [ ] Dùng `required=true` (mặc định) cho configuration thực sự bắt buộc.
- [ ] Dùng `required=false` khi **cả nhóm dependencies** có thể vắng mặt mà object vẫn hợp lệ.
- [ ] Không kỳ vọng method non-required nhận `null` cho argument thiếu.
- [ ] Nếu từng tham số tùy chọn độc lập, dùng `Optional<T>` hoặc nhiều injection points.
- [ ] Cho dependency bắt buộc vào constructor khi hợp lý để tránh object ở trạng thái thiếu điều kiện.
- [ ] Đối với `@Bean` có nhiều parameter, để container tự resolve thay vì gọi thủ công từng `getBean`.
- [ ] Nếu có property `@Value`, validate default và cấu hình property source trước khi refresh.
- [ ] Không giấu use case business trong lifecycle method hoặc in ra output khó dự đoán tại startup.
- [ ] Test context có và không có dependency tùy chọn; kiểm tra stdout và trạng thái thực của bean.
- [ ] Không hot-swap các field của singleton không có chiến lược thread-safety.
- [ ] Đóng context sau khi ứng dụng hoàn tất.

### Tài liệu Spring chính thức

- [Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html)
- [Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)

**Kết luận:** Trong Spring Core Container, một **phương thức cấu hình `@Autowired` nhiều tham số** cho phép thiết lập nhiều collaborator trên một bean bằng một lời gọi method. Với `required=false`, method thường **bị bỏ qua toàn bộ** nếu thiếu dependency; với `Optional<T>`, tính tùy chọn được biểu đạt ở một tham số cụ thể. Ngược lại, **`@Bean` factory method nhiều tham số** tạo bean và tự được Spring cung cấp arguments. Hiểu rõ ba cơ chế này giúp bạn định nghĩa đúng dependency bắt buộc, tùy chọn và nhóm cấu hình nguyên khối, thay vì nhầm việc tạo bean với tiêm cấu hình.