# Phân biệt @Autowired với jakarta.inject.Inject — Spring Framework Core Container

## 1. Hai annotation cùng giải quyết dependency injection, nhưng khác nguồn gốc

Trong Spring Core Container, **`@Autowired`** là annotation của chính Spring, còn **`@Inject`** là annotation tiêu chuẩn Dependency Injection của Jakarta, nằm trong package **`jakarta.inject`**. Spring Framework 6.2 có thể nhận biết **cả hai** khi khởi tạo bean, miễn là thư viện Jakarta Inject API hiện diện trên classpath.

Ví dụ hai constructor sau thể hiện cùng ý định cơ bản — **Spring cung cấp bean `MessageSender` cho service**:

~~~java
// Kiểu Spring:
@Autowired
public SpringClient(MessageSender sender) {
    this.sender = sender;
}

// Kiểu tiêu chuẩn Jakarta:
@Inject
public StandardClient(MessageSender sender) {
    this.sender = sender;
}
~~~

Đây là **hai snippet thuộc hai lớp khác nhau**, chưa có class/import đầy đủ; project chạy được nằm ở mục 7. Trong cả hai trường hợp, container phải tìm đúng candidate `MessageSender` và đưa **bean object** vào constructor. Annotation không tự tạo bean nếu lớp chưa được đăng ký với context.

**Mục tiêu bài học:** nắm được điểm giống, điểm khác, giới hạn của chuẩn Jakarta và cách chọn annotation hợp lý khi viết Java 17+ với Spring Framework.

Sau bài, bạn có thể:

1. Phân biệt import `org.springframework.beans.factory.annotation.Autowired` với `jakarta.inject.Inject`.
2. Dùng hai annotation trên **constructor, field hoặc method injection** trong một Spring context.
3. Hiểu `@Autowired(required=false)` **không có bản sao cùng thuộc tính** trên `@Inject`; biết dùng `Optional<T>`, nullable types hoặc provider khi dependency thực sự không bắt buộc.
4. Phân biệt `@Qualifier("...")` của Spring với `@Named("...")` của Jakarta; hiểu `jakarta.inject.Qualifier` là **meta-annotation**.
5. Dùng `jakarta.inject.Provider<T>` cho việc **lấy dependency theo nhu cầu**, đồng thời hiểu nó không tự biến một dependency thiếu thành hợp lệ.
6. Biết `@Named` có thể làm dấu hiệu đăng ký component, nhưng **không tự tạo bean nếu không có đăng ký/scan**.
7. Hiểu vì sao Spring-specific `@Value`, `@Lazy`, scope và các tính năng cấu hình khác vẫn có vai trò dù dùng `@Inject`.
8. Chạy ví dụ độc lập **Java 17+**, Maven, `javac`/`java` và đối chiếu các dòng stdout.

**Phạm vi:** so sánh **`@Autowired` và `jakarta.inject.Inject` trong Spring Framework Core Container**. Không cần Spring Boot, MVC, Servlet, JPA hoặc một CDI container khác.

## 2. Bảng đối chiếu chính xác

| Tiêu chí | Spring `@Autowired` | Jakarta `@Inject` |
| --- | --- | --- |
| Package/import | `org.springframework.beans.factory.annotation.Autowired` | `jakarta.inject.Inject` |
| Thuộc hệ sinh thái | Spring Framework | Jakarta Dependency Injection (JSR-330 lineage) |
| Injection vào constructor | Có | Có |
| Injection vào field | Có | Có |
| Injection vào method/setter | Có | Có |
| Đánh dấu dependency bắt buộc | `required=true` theo mặc định | Không có thuộc tính `required`; injection thông thường là bắt buộc |
| Tùy chọn injection | `required=false` ở injection point phù hợp; cũng hỗ trợ `Optional` | Không có `required=false`; Spring hỗ trợ `Optional<T>`, `@Nullable` ở điểm injection phù hợp |
| Chọn bean theo tên/qualifier | `@Qualifier("mainSender")` | `@Named("mainSender")` |
| Lấy bean theo nhu cầu | Spring `ObjectProvider<T>`/`ObjectFactory<T>` | Jakarta `Provider<T>` với `get()` |
| Đăng ký component theo stereotype | `@Component` | `@Named` |
| Khai báo giá trị cấu hình | Dùng `@Value` / `Environment` riêng | Không có `@Value` tương đương trong Jakarta Inject |
| Trì hoãn khởi tạo bean | Dùng `@Lazy` của Spring khi phù hợp | Không có annotation `@Lazy` tương đương trong Jakarta Inject |
| Phụ thuộc Maven thêm | Có trong Spring modules | Cần `jakarta.inject:jakarta.inject-api` trên compile/runtime classpath |
| Phụ thuộc container tại runtime | Spring nhận diện và thực hiện | Cùng Spring container cũng nhận diện và thực hiện khi Jakarta API có mặt |

**Không nói `@Inject` là “Spring annotation”:** API của nó là chuẩn Jakarta. Nhưng khi chạy trong **Spring**, chính Spring vẫn cung cấp lifecycle, candidate resolution, bean scopes và các extension points. Dùng annotation tiêu chuẩn **không tự động khiến ứng dụng Spring độc lập hoàn toàn với Spring**.

## 3. Spring nhận diện @Inject bằng cơ chế nào?

Trong cấu hình annotation-based của Spring, `AutowiredAnnotationBeanPostProcessor` tham gia phát hiện injection points và thực hiện wiring. Spring hỗ trợ các annotation `@Autowired`/`@Value` của nó, đồng thời hỗ trợ **`jakarta.inject.Inject` nếu API tương ứng hiện diện**.

Điều kiện cần:

1. Class cần inject phải **trở thành Spring bean**, ví dụ được quét từ một package phù hợp hoặc đăng ký trực tiếp bằng `AnnotationConfigApplicationContext.register(...)`.
2. Các bean collaborator phải được khai báo bằng `@Bean`, component scanning hoặc một cách đăng ký bean definition hợp lệ.
3. Container phải giải quyết được injection points theo **type**, **qualifiers**, **scope** và các quy tắc Spring.
4. Với `@Inject`, Maven phải có **Jakarta Inject API**; thiếu thư viện sẽ gây lỗi compile hoặc vấn đề classpath, không phải lỗi bản chất của DI.

~~~mermaid
flowchart TD
    A["Class đã được đăng ký thành Spring bean"] --> B["Spring xử lý injection annotations"]
    B --> C["@Autowired của Spring"]
    B --> D["@Inject của Jakarta"]
    C --> E["Tìm bean candidate phù hợp"]
    D --> E
    E --> F["Constructor / field / setter nhận object"]
    F --> G["Bean sử dụng collaborator"]
~~~

**Phân biệt hai giai đoạn:** `@Named`/`@Component` có thể là stereotype giúp Spring **phát hiện class** trong component scan, trong khi `@Inject`/`@Autowired` đánh dấu **điểm cần wiring**. Chúng phục vụ những vai trò khác nhau.

### @Named khác @Inject

- `@Named("standardClient")` trên class có thể đặt tên component trong Spring.
- `@Named("mainSender")` trên **constructor parameter** có thể làm qualifier để chọn một bean cụ thể.
- `@Inject` trên constructor thể hiện yêu cầu container **cung cấp các tham số**.
- Một class có `@Named` nhưng **nằm ngoài phạm vi scan và không đăng ký trực tiếp** sẽ không tự xuất hiện trong context.

## 4. Constructor injection: hai annotation thường hoạt động tương đương

Trong một context có duy nhất một bean `MessageSender`, hai cách sau đều được Spring xử lý:

~~~java
@Component
final class SpringConsumer {
    private final MessageSender sender;

    @Autowired
    SpringConsumer(MessageSender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }
}
~~~

~~~java
@Named
final class JakartaConsumer {
    private final MessageSender sender;

    @Inject
    JakartaConsumer(MessageSender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }
}
~~~

Cả hai là **snippets minh họa** chưa kèm định nghĩa `MessageSender`. Khi được Spring đăng ký và có collaborator hợp lệ, constructor sẽ nhận bean. Việc giữ collaborator trong `private final` và kiểm tra non-null là thiết kế **của code Java**, không phải đặc quyền của annotation nào.

### Một constructor duy nhất có thể không cần cả hai

Với Spring Framework hiện đại, nếu class đã đăng ký thành bean và **chỉ có một constructor**, Spring có thể dùng constructor đó **ngay cả khi không viết `@Autowired` hoặc `@Inject`**:

~~~java
@Component
final class PlainConsumer {
    private final MessageSender sender;

    PlainConsumer(MessageSender sender) {
        this.sender = java.util.Objects.requireNonNull(sender);
    }
}
~~~

Vì vậy đừng thêm `@Inject` chỉ vì nghĩ **mọi constructor của Spring bean bắt buộc có annotation**. Annotation hữu ích khi muốn làm rõ điểm injection, nhất là lúc class có nhiều constructors. Nếu class được tạo **bằng `new` trong một `@Bean` factory method**, Java quyết định overload cụ thể qua lời gọi `new` ấy; không tự động đồng nghĩa Spring chọn lại constructor của object được trả về.

### Nếu class có nhiều constructors

- `@Autowired` cho phép mô tả constructor required (mặc định) hoặc nhiều ứng viên `required=false` theo quy tắc Spring.
- `@Inject` **không có tham số `required`**. Đừng áp dụng cú pháp `@Inject(required=false)` — Java sẽ báo lỗi compile.
- Với nhiều overload, ưu tiên **một constructor bắt buộc rõ ràng**; đừng trông cậy vào container đoán ý định nghiệp vụ.
- Nên tránh gắn nhiều constructor `@Inject` với kỳ vọng Spring sẽ xử lý như một danh sách required=false. Một class có nhiều constructors cần một lựa chọn minh bạch.
- Không dùng constructor mặc định tạo trạng thái thiếu dependency chỉ để ứng dụng khởi động.

**Quan trọng:** `@Autowired(required=false)` trên **setter method** và trên **constructor** có ngữ nghĩa khác nhau: ở setter, phương thức có thể bị bỏ qua khi dependency không có; với nhiều constructor annotated optional, Spring chọn constructor có thể giải quyết được theo quy tắc. Đừng hiểu `required=false` là truyền null vào mọi tham số còn thiếu.

## 5. Điểm khác biệt lớn: xử lý dependency tùy chọn

### 5.1. Spring: @Autowired(required=false) trên setter

~~~java
@Component
final class OptionalMonitoring {
    private boolean metricsAttached;

    @Autowired(required = false)
    public void setMetrics(MetricsClient metrics) {
        metricsAttached = true;
    }

    boolean metricsAttached() {
        return metricsAttached;
    }
}
~~~

Đây là **snippet**; `MetricsClient` chưa được định nghĩa trong đoạn độc lập này. Nếu Spring không có bean `MetricsClient` nào phù hợp, nó có thể **không gọi setter tùy chọn**; `metricsAttached` vẫn là `false`. Ví dụ runnable ở mục 7 sẽ kiểm chứng điều này.

### 5.2. Jakarta: không có required=false; dùng Optional<T> khi phù hợp

~~~java
@Named
final class OptionalJakartaClient {
    private final java.util.Optional<MetricsClient> metrics;

    @Inject
    OptionalJakartaClient(java.util.Optional<MetricsClient> metrics) {
        this.metrics = java.util.Objects.requireNonNull(metrics);
    }

    boolean missing() {
        return metrics.isEmpty();
    }
}
~~~

**Snippet**, cần khai báo `MetricsClient`. Trong **Spring**, khi không có bean `MetricsClient` phù hợp, injection point kiểu `Optional<MetricsClient>` có thể nhận `Optional.empty()`. Điều này được tài liệu Spring hỗ trợ cho `@Inject`.

| Mong muốn | Cách biểu đạt |
| --- | --- |
| Dependency **bắt buộc** | Constructor injection thường, với `@Autowired` hoặc `@Inject` |
| Setter optional của Spring | `@Autowired(required=false)` trên setter phù hợp |
| Tham số optional trong Spring | `Optional<T>` hoặc nullable injection point với quy tắc phù hợp |
| Truy cập dependency theo nhu cầu | `jakarta.inject.Provider<T>` hoặc Spring `ObjectProvider<T>` |

**Đừng nhầm Provider với Optional.** `Provider<T>.get()` **yêu cầu lấy một instance**; nếu bean không tồn tại, việc gọi `get()` có thể thất bại. Provider giúp trì hoãn/động hóa việc truy cập, **không phải một cam kết “thiếu bean thì luôn trả null”**.

### 5.3. Optional khác “cứ chạy khi thiếu là đúng”

Nếu một service xử lý thanh toán **không thể hoạt động khi thiếu `PaymentGateway`**, đánh dấu dependency thành optional chỉ để tránh startup error là một lỗi thiết kế. Hãy giữ constructor required và để context **fail fast** khi thiếu bean.

Dùng optional cho những thành phần thực sự không thiết yếu, chẳng hạn metrics, tracing phụ, plugin hoặc tính năng có thể tắt. Khi vắng mặt, code phải định nghĩa hành vi có chủ đích; không chỉ bỏ qua `NullPointerException`.

## 6. @Qualifier, @Named, Provider và @Value

### 6.1. Chọn một bean theo tên

Nếu có nhiều beans cùng kiểu `MessageSender`, điểm injection cần chỉ rõ cái mong muốn.

**Spring:**

~~~java
@Autowired
public SpringClient(
        @Qualifier("mainSender") MessageSender sender) {
    this.sender = sender;
}
~~~

**Jakarta:**

~~~java
@Inject
public StandardClient(
        @Named("mainSender") MessageSender sender) {
    this.sender = sender;
}
~~~

Đây là **snippets của hai classes**, chưa phải file độc lập. Trong ngữ cảnh Spring, cả hai đều hướng Spring tới bean có name/qualifier tương ứng. `@Named` còn dùng trên class để đánh dấu tên component.

**Lưu ý:** `jakarta.inject.Qualifier` là **meta-annotation** để xây dựng custom qualifier, không phải annotation chứa tham số tên dạng `@Qualifier("mainSender")` của Spring. Muốn dùng tên String theo Jakarta, hãy dùng `@Named("mainSender")`.

### 6.2. Provider<T> lấy bean khi cần

~~~java
@Named
final class LazyConsumer {
    private final Provider<MessageSender> senderProvider;

    @Inject
    LazyConsumer(Provider<MessageSender> senderProvider) {
        this.senderProvider = senderProvider;
    }

    String run() {
        return senderProvider.get().send("Lan");
    }
}
~~~

**Snippet minh họa:** cần import `jakarta.inject.Provider` và kiểu `MessageSender` có method `send`. Spring hỗ trợ `Provider<T>` khi có Jakarta Inject API. Với singleton thông thường, nhiều lần `get()` vẫn trả cùng instance; với prototype, mỗi lần tra cứu có thể tạo instance mới. Không khẳng định `Provider` tự làm bean có scope prototype hay không bao giờ gọi logic tạo bean.

### 6.3. Không có @Value hay @Lazy tương đương trực tiếp trong Jakarta Inject

Jakarta `@Inject` tập trung vào injection **bean object**. Nó không cung cấp annotation tương ứng với Spring `@Value` để giải quyết trực tiếp property placeholder, hay Spring `@Lazy` để khai báo lazy initialization. Khi dùng Spring, bạn có thể kết hợp annotation Jakarta với các tính năng Spring:

~~~java
@Inject
public ConfigurableClient(
        @Named("mainSender") MessageSender sender,
        @Value("${app.prefix}") String prefix) {
    this.sender = sender;
    this.prefix = prefix;
}
~~~

Đây là **snippet**, cần class/import Spring `@Value` và cấu hình property source phù hợp; không phải file runnable. Nó cho thấy **trộn các annotations là có thể**, nhưng class lúc này **phụ thuộc Spring-specific configuration semantics**, không còn “chỉ dùng Jakarta”.

Đối với simple values, có thể đọc `Environment.getRequiredProperty(...)` tại composition root rồi truyền vào constructor; không nên biến mọi String hay int thành bean để dùng `@Inject`.

### 6.4. Scope và stereotype

Trong Spring, một class `@Named` được đăng ký như Spring bean thường vẫn có scope **singleton mặc định**, giống một class `@Component` theo Spring defaults. Dù chuẩn Jakarta có cách diễn giải scope khi không chỉ định riêng, không nên giả định Spring tự chuyển `@Named` thành prototype.

Nếu cần prototype trong Spring:

~~~java
@Named("temporaryHandler")
@org.springframework.context.annotation.Scope("prototype")
final class TemporaryHandler {
    // Một instance mới theo mỗi yêu cầu phù hợp.
}
~~~

Snippet chỉ minh họa. `jakarta.inject.Singleton` là annotation scope tiêu chuẩn, nhưng trong Spring **không cần gắn nó cho mọi bean để có singleton mặc định**.

Không thay `@ComponentScan`/registration bằng việc chỉ import `@Named`: class vẫn phải được scanner nhìn thấy hoặc đăng ký trực tiếp.

## 7. Ví dụ độc lập Java 17+ — cả hai annotation trong cùng Spring context

### 7.1. Cấu trúc và dependency

Dùng **Spring Framework 6.2.19**, **JDK 17+**, Maven và Jakarta Inject API **2.0.0**. Phiên bản được ghim cho ví dụ, không khẳng định là phiên bản mới nhất của Spring.

~~~text
spring-jakarta-inject-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── InjectionComparisonDemo.java
~~~

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-jakarta-inject-demo</artifactId>
    <version>1.0.0</version>

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
        <dependency>
            <groupId>jakarta.inject</groupId>
            <artifactId>jakarta.inject-api</artifactId>
            <version>2.0.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.InjectionComparisonDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Cần cả hai dependencies**: `spring-context` đưa Spring container vào chương trình; `jakarta.inject-api` cung cấp `Inject`, `Named` và `Provider` để compile và để Spring nhận diện chúng khi ứng dụng chạy.

### 7.2. Mã nguồn src/main/java/demo/InjectionComparisonDemo.java

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

import jakarta.inject.Inject;
import jakarta.inject.Named;
import jakarta.inject.Provider;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

public final class InjectionComparisonDemo {
    private InjectionComparisonDemo() {}

    public interface MessageSender {
        String send(String name);
    }

    public static final class ConsoleSender implements MessageSender {
        @Override
        public String send(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
            return "Xin chao, " + name.strip();
        }
    }

    public static final class EventLog {
        private final List<String> events = new ArrayList<>();

        public void record(String event) {
            events.add(event);
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    // Spring-specific constructor injection.
    @Component("springClient")
    public static final class SpringClient {
        private final MessageSender sender;
        private final EventLog log;

        @Autowired
        public SpringClient(
                @Qualifier("mainSender") MessageSender sender,
                EventLog log) {
            this.sender = Objects.requireNonNull(sender);
            this.log = Objects.requireNonNull(log);
        }

        public MessageSender sender() {
            return sender;
        }

        public String greet(String name) {
            String message = sender.send(name);
            log.record("spring:" + message);
            return message;
        }
    }

    // Jakarta standard constructor injection.
    @Named("standardClient")
    public static final class StandardClient {
        private final MessageSender sender;
        private final EventLog log;

        @Inject
        public StandardClient(
                @Named("mainSender") MessageSender sender,
                EventLog log) {
            this.sender = Objects.requireNonNull(sender);
            this.log = Objects.requireNonNull(log);
        }

        public MessageSender sender() {
            return sender;
        }

        public String greet(String name) {
            String message = sender.send(name);
            log.record("inject:" + message);
            return message;
        }
    }

    // Jakarta Provider resolves the target on get().
    @Named("providerClient")
    public static final class ProviderClient {
        private final Provider<MessageSender> provider;

        @Inject
        public ProviderClient(Provider<MessageSender> provider) {
            this.provider = Objects.requireNonNull(provider);
        }

        public boolean providesSame(MessageSender sender) {
            return provider.get() == sender;
        }
    }

    // No bean of this interface is registered in the example.
    public interface MissingMetrics {}

    @Component("optionalSpringClient")
    public static final class OptionalSpringClient {
        private boolean metricsAttached;

        public OptionalSpringClient() {}

        @Autowired(required = false)
        public void setMetrics(MissingMetrics metrics) {
            metricsAttached = true;
        }

        public boolean setterSkipped() {
            return !metricsAttached;
        }
    }

    @Named("optionalStandardClient")
    public static final class OptionalStandardClient {
        private final Optional<MissingMetrics> metrics;

        @Inject
        public OptionalStandardClient(Optional<MissingMetrics> metrics) {
            this.metrics = Objects.requireNonNull(metrics);
        }

        public boolean absent() {
            return metrics.isEmpty();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("mainSender")
        public MessageSender mainSender() {
            return new ConsoleSender();
        }

        @Bean
        public EventLog eventLog() {
            return new EventLog();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {
            context.register(AppConfig.class, SpringClient.class,
                    StandardClient.class, ProviderClient.class,
                    OptionalSpringClient.class, OptionalStandardClient.class);
            context.refresh();

            SpringClient spring = context.getBean(SpringClient.class);
            StandardClient standard = context.getBean(StandardClient.class);
            ProviderClient provider = context.getBean(ProviderClient.class);
            OptionalSpringClient optionalSpring =
                    context.getBean(OptionalSpringClient.class);
            OptionalStandardClient optionalStandard =
                    context.getBean(OptionalStandardClient.class);
            MessageSender sender = context.getBean(MessageSender.class);
            EventLog log = context.getBean(EventLog.class);

            System.out.println("springGreeting=" + spring.greet(" Lan "));
            System.out.println("injectGreeting=" + standard.greet(" Minh "));
            System.out.println("sameSender=" +
                    (spring.sender() == sender
                     && standard.sender() == sender));
            System.out.println("providerSame=" +
                    provider.providesSame(sender));
            System.out.println("autowiredSetterSkipped=" +
                    optionalSpring.setterSkipped());
            System.out.println("injectOptionalAbsent=" +
                    optionalStandard.absent());
            System.out.println("events=" + log.snapshot());
            System.out.println("standardSingleton=" +
                    (standard == context.getBean(StandardClient.class)));
        }
    }
}
~~~

**Vì sao ví dụ tự chứa:**

- Có đúng một public top-level class trùng tên tệp; collaborator classes/interfaces được khai báo nested static.
- Bean `mainSender` có kiểu `MessageSender` và được đặt tên rõ; `eventLog` là bean singleton mặc định.
- `SpringClient` inject với Spring `@Autowired`/`@Qualifier("mainSender")`.
- `StandardClient` inject cùng bean bằng Jakarta `@Inject`/`@Named("mainSender")`.
- `ProviderClient` inject `jakarta.inject.Provider<MessageSender>`; vì context chỉ có một sender singleton, `provider.get()` trả chính object đó.
- `OptionalSpringClient` không có bean `MissingMetrics`, vì vậy setter `@Autowired(required=false)` không được gọi, giá trị boolean giữ `false`.
- `OptionalStandardClient` dùng `Optional<MissingMetrics>` qua `@Inject`, nên nhận `Optional.empty()` khi thiếu dependency trong Spring.
- Hai consumers chia sẻ một `EventLog` singleton và ghi theo thứ tự main gọi. Demo không dùng random, clock hay kết quả iteration không ổn định.
- `context.register(...)` **đăng ký trực tiếp** các component classes; không cần component scanning. Chỉ gắn `@Component`/`@Named` ở source mà không đăng ký/scan sẽ không tự làm class thành bean.
- `try-with-resources` đóng context sau khi in xong. Không có bean destroy callback phát ra stdout.

### 7.3. Chạy Maven và đối chiếu stdout

Từ thư mục `spring-jakarta-inject-demo`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Đúng tám dòng stdout do chương trình Java in khi chạy thành công:**

~~~text
springGreeting=Xin chao, Lan
injectGreeting=Xin chao, Minh
sameSender=true
providerSame=true
autowiredSetterSkipped=true
injectOptionalAbsent=true
events=[spring:Xin chao, Lan, inject:Xin chao, Minh]
standardSingleton=true
~~~

Những dòng version và logging của Maven/Spring (nếu xuất hiện) không nằm trong tám dòng `System.out.println` ở trên. Các trạng thái `true`/`false` là kết quả trực tiếp của cấu hình demo, **không phải lời khẳng định mọi annotation sẽ chọn cùng instance trong mọi scope/hoàn cảnh**.

### 7.4. Dùng javac/java trực tiếp

Vì mã nguồn import Spring và `jakarta.inject.*`, compiler cần **cả hai nhóm dependency** trên classpath. Dùng Maven tạo file classpath:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/InjectionComparisonDemo.java
java -cp "out:$(cat classpath.txt)" demo.InjectionComparisonDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/InjectionComparisonDemo.java
java -cp "out;$deps" demo.InjectionComparisonDemo
~~~

Trên Unix, classpath phân tách bằng `:`, Windows bằng `;`. Cùng class `demo.InjectionComparisonDemo` nên output nghiệp vụ trùng tám dòng ở trên.

Nếu `javac` báo `package jakarta.inject does not exist`, kiểm tra dependency `jakarta.inject-api` trong POM/classpath; nếu thiếu `org.springframework...`, kiểm tra `spring-context` và các transitive JARs.

## 8. Giải thích tám dòng stdout

| Dòng | Kết luận được phép rút ra |
| --- | --- |
| `springGreeting=Xin chao, Lan` | SpringClient nhận sender và xử lý tên đã strip |
| `injectGreeting=Xin chao, Minh` | StandardClient được Spring inject qua @Inject |
| `sameSender=true` | Hai consumers giữ **cùng bean mainSender singleton** trong context này |
| `providerSame=true` | `Provider<MessageSender>.get()` ở context này trả cùng sender singleton |
| `autowiredSetterSkipped=true` | Setter tùy chọn của Spring bị bỏ qua khi thiếu bean MissingMetrics |
| `injectOptionalAbsent=true` | Optional<MissingMetrics> được resolve vắng mặt |
| `events=[spring:..., inject:...]` | Hai services cùng ghi đúng thứ tự vào EventLog |
| `standardSingleton=true` | Bean @Named do Spring quản lý là singleton mặc định ở ví dụ |

Không dùng `sameSender=true` để suy ra **prototype, scoped proxy, nhiều beans cùng type, hoặc multiple contexts** đều trả chung object. Scope và cách bean được resolve vẫn chi phối identity.

## 9. Một số hiểu nhầm thường gặp

### 9.1. “@Inject tự động thay hết mọi tính năng @Autowired”

Không. Spring hiểu `@Inject` như một annotation injection thay thế cơ bản, nhưng Jakarta annotation **không có `required` attribute**. Spring `@Autowired` cùng các facility như `@Value`, `@Lazy` và `ObjectProvider` vẫn cung cấp những tính năng riêng. Khi chuyển annotation, phải kiểm tra optional semantics, provider, qualifier và build dependencies.

### 9.2. “Dùng @Inject thì chạy được trên mọi DI container không sửa gì”

API annotation mang tính tiêu chuẩn và giúp tách bớt phụ thuộc ở **injection code**, nhưng mô hình registration, phạm vi bean, lifecycle, giải pháp external config, qualifier custom và container extensions có thể khác nhau. Cách `Optional<T>` được Spring hỗ trợ không đồng nghĩa mọi CDI/container khác nhất thiết có hành vi y hệt.

Portability là **mức độ**, không phải lời bảo đảm chuyển toàn ứng dụng Spring sang container khác bằng cách đổi một import.

### 9.3. “@Named và @Qualifier của Jakarta giống nhau”

Không. `jakarta.inject.Named` là một qualifier định danh bằng String đồng thời có thể dùng trên component class. `jakarta.inject.Qualifier` dùng như **meta-annotation** để định nghĩa custom qualifiers; không viết `@jakarta.inject.Qualifier("mainSender")`. Spring `@Qualifier("mainSender")` là annotation riêng của Spring và có value.

### 9.4. “@Named làm mọi class trong project thành bean”

Không. Với component scanning, cần chỉ đúng package; với code khởi tạo context thuần, bạn có thể register class trực tiếp. Annotation không tự kích hoạt scanner hoặc tự ghi vào registry.

### 9.5. “Provider<T> luôn cho phép dependency thiếu”

Không. Provider chủ yếu hỗ trợ **lấy dependency tại thời điểm cần**, và cũng thích hợp với prototype/scoped beans. Nếu không có bean hợp lệ, `get()` có thể ném exception. Nếu dependency thực sự tùy chọn, dùng kiểu `Optional<T>` hoặc chính sách rõ ở application layer.

### 9.6. “@Autowired(required=false) bảo đảm field có giá trị null”

Với setter được đánh dấu optional, Spring có thể **bỏ qua toàn bộ method injection** khi không resolve được collaborator. Với field có thể vẫn là null/default nếu không được inject; code phải thiết kế được hành vi thiếu đó. Không nghĩ `required=false` là lệnh luôn truyền null vào một setter.

### 9.7. “@Inject nghĩa là @Singleton”

`@Inject` chỉ đánh dấu injection point. Scope của bean do container/definition quyết định. Trong Spring, bean `@Named` thường mặc định singleton, không phải vì constructor có `@Inject`, cũng không mặc nhiên là prototype.

### 9.8. “Dùng javax.inject.Inject vì project Java cũ từng làm vậy”

Spring Framework 6+ sử dụng các Jakarta APIs trong tài liệu tiêu chuẩn. Trong project Java 17+ mới, ưu tiên `jakarta.inject.Inject`/`Named` và dependency `jakarta.inject-api`. `javax.inject.Inject` thuộc namespace Java EE/JSR-330 cũ; Spring có thể giữ hỗ trợ tương thích ở một số phiên bản/ngữ cảnh, nhưng **không trộn hai namespace** nếu không hiểu chính xác dependency và môi trường migration.

### 9.9. “Có @Inject là không cần kiểm tra null”

Dependency injection không thay thế invariant Java:

~~~java
@Inject
public BillingService(PaymentGateway gateway) {
    this.gateway = java.util.Objects.requireNonNull(gateway);
}
~~~

Snippet này chưa có định nghĩa `BillingService`/`PaymentGateway` hoàn chỉnh. Các guard tiếp tục có ích khi class được tạo **ngoài Spring** bằng `new` hoặc khi caller/adapter cung cấp dữ liệu sai. Không biến dependency bắt buộc thành nullable chỉ để bỏ qua lỗi wiring.

## 10. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng khắc phục |
| --- | --- | --- |
| `package jakarta.inject does not exist` | Chưa khai báo thư viện Jakarta Inject API | Thêm Maven dependency, cập nhật build/classpath |
| `cannot find symbol @Inject` | Import nhầm hoặc dependency không có | Import `jakarta.inject.Inject` |
| `@Inject(required=false)` không compile | Jakarta @Inject không có thuộc tính required | Dùng `Optional<T>`/nullable/provider tùy hợp đồng |
| `UnsatisfiedDependencyException` | Bean constructor required thiếu collaborator | Đăng ký bean, kiểm tra scan/qualifier |
| `NoSuchBeanDefinitionException` | Không có bean theo kiểu/tên mong muốn | Kiểm tra `@Bean`, `@Named`, cấu hình context |
| `NoUniqueBeanDefinitionException` | Nhiều bean candidates cho một tham số đơn trị | Chọn với `@Qualifier`/`@Named` hoặc policy primary |
| Setter `@Autowired(required=false)` không chạy | Bean optional không tồn tại | Đó có thể là đúng semantics; kiểm tra hợp đồng optional |
| `Provider.get()` thất bại | Không có bean thích hợp ở thời điểm lấy | Kiểm tra availability/scope, đừng coi Provider là Optional |
| `@Named` class không được phát hiện | Không có component scan hoặc explicit registration | Cấu hình phạm vi scan hoặc register đúng class |
| Dùng `@Named` để đọc property placeholder | Nhầm bean selector với cấu hình value | Dùng `@Value`/`Environment` phù hợp |
| `@Inject` nhưng thuộc tính vẫn null | Object do `new` ngoài container hoặc bean processing không hoạt động | Dùng managed bean, kiểm tra registration/post-processing |
| Khác biệt scope giữa môi trường | Áp dụng semantics container khác cho Spring | Kiểm tra scope của bean definition trong Spring |
| Đổi import `javax.inject`/`jakarta.inject` bừa bãi | Namespace khác, dependencies không đồng bộ | Chốt Jakarta namespace cho Spring 6+ và kiểm tra migrations |
| Test Spring pass nhưng logic sai | Wiring có mặt chưa chứng minh nghiệp vụ đúng | Viết unit test với fake và integration test |

**Cách debug:** xác định bean source/registration, annotation được import từ package nào, điểm injection cần type gì, có bao nhiêu candidate, có qualifier chính xác không, dependency optional hay required, rồi đọc chuỗi `Caused by` của exception. Nếu lỗi biên dịch, sửa dependencies **trước** khi phân tích runtime Spring.

## 11. Thực hành mở rộng

**Bài 1 — thiếu bean bắt buộc:** tạo class `@Named` có constructor `@Inject RequiredClient(MissingMetrics metrics)` và đăng ký nó vào **context test riêng** nhưng không đăng ký `MissingMetrics`. Dự kiến refresh thất bại; đừng mong Spring truyền null hay tự bỏ constructor.

**Bài 2 — thay qualifier:** đăng ký thêm một sender có tên `backupSender`. Giữ injection `@Qualifier("mainSender")` và `@Named("mainSender")`: cả hai consumers vẫn yêu cầu sender chính. Bỏ qualifier rồi thử giải thích nguyên nhân ambiguity nếu nhiều candidates không có lựa chọn khác.

**Bài 3 — singleton và prototype:** thay một bean hợp lệ thành `@Scope("prototype")`, sau đó dùng `Provider<T>.get()` hai lần; kiểm tra identity của object theo scope thực. Không sửa code demo ban đầu rồi vẫn yêu cầu stdout `providerSame=true`.

**Bài 4 — Optional:** đăng ký `MissingMetrics` bean trong test khác, kiểm tra `Optional<MissingMetrics>.isPresent()` thành true và setter optional được gọi. Nhớ thử cả trường hợp vắng mặt.

**Bài 5 — Java thuần:** tạo `SpringClient` hoặc `StandardClient` bằng constructor với một fake sender và fake log. Cả hai test được như class Java bình thường; không bắt buộc bật Spring chỉ để test logic greet.

### Checklist chốt bài

- [ ] Biết imports và dependency khác nhau của `@Autowired` và `@Inject`.
- [ ] Cả hai đều có thể injection constructor/field/setter trong Spring.
- [ ] Không cho rằng annotation tự đăng ký class thành bean.
- [ ] Dùng một constructor rõ cho collaborator bắt buộc.
- [ ] Biết `@Autowired` có `required`, còn `@Inject` thì không.
- [ ] Chọn Optional/nullable semantics phù hợp cho dependency thật sự tùy chọn.
- [ ] Phân biệt Provider lấy bean on-demand với Optional biểu diễn absence.
- [ ] Dùng `@Qualifier("name")` của Spring hoặc `@Named("name")` của Jakarta đúng vai trò.
- [ ] Biết `jakarta.inject.Qualifier` là meta-annotation.
- [ ] Không coi `@Named` mặc nhiên mang prototype scope trong Spring.
- [ ] Hiểu `@Value`/`@Lazy` là tính năng Spring không có annotation Jakarta thay thế trực tiếp.
- [ ] Có `jakarta.inject-api` trong pom và compile/runtime classpath.
- [ ] Chạy `mvn -q clean compile exec:java` và đối chiếu **tám dòng stdout**.
- [ ] Với `javac`/`java`, dùng đúng Spring + Jakarta JARs.
- [ ] Test cùng behavior ở unit level và wiring ở context level.

**Kết luận:** trong Spring, `@Autowired` và `jakarta.inject.Inject` đều có thể khai báo dependency injection. Hãy chọn `@Inject` nếu muốn dùng **API annotation tiêu chuẩn Jakarta** cho những yêu cầu DI cơ bản, và `@Autowired` nếu cần biểu đạt trực tiếp khả năng Spring-specific như `required=false` tại một injection point. Dù chọn cách nào, **registration, bean selection, scope và lifecycle vẫn do Spring container quyết định** khi chương trình chạy trên Spring Framework.

### Tài liệu chính thức

- [Spring Framework 6.2 — Using JSR-330 Standard Annotations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/standard-annotations.html)
- [Spring Framework 6.2 — Using @Autowired](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html)
- [Spring Framework 6.2 — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config.html)
- [Spring API — AutowiredAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/annotation/AutowiredAnnotationBeanPostProcessor.html)
