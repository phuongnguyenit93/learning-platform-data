# Dùng jakarta.inject.Provider và chọn thời điểm lấy bean trong Spring Core Container

## 1. Mục tiêu và bối cảnh

Trong Spring IoC Container, **dependency injection** thường giải quyết dependency ngay khi tạo bean nhận phụ thuộc. Đây là lựa chọn mặc định hợp lý cho dependency bắt buộc và ổn định. Tuy nhiên, đôi khi đối tượng cần dùng phải được lấy **vào đúng thời điểm xử lý nghiệp vụ**, chẳng hạn:

- Một singleton thực hiện nhiều công việc và mỗi công việc cần một bean `prototype` mới.
- Một dịch vụ chỉ chạm đến một bean có scope ngắn hơn khi có request đang hoạt động.
- Một dependency gây tốn chi phí hoặc liên quan đến vòng phụ thuộc, và việc truy cập nó cần được trì hoãn đến sau khi consumer đã được dựng.
- Một interface có nhiều implementation; mã sử dụng muốn nêu rõ implementation qua qualifier.

**`jakarta.inject.Provider<T>`** là một hợp đồng rất nhỏ trong Jakarta Dependency Injection: consumer nhận `Provider<T>` qua dependency injection, lưu provider và gọi `get()` khi cần đối tượng `T`. Spring Framework hỗ trợ hợp đồng này trong Core Container. Khái niệm cốt lõi là **trì hoãn việc lấy bean từ container**, không phải tự động tạo mới hoặc trì hoãn mọi khởi tạo trong toàn ứng dụng.

Sau bài này, bạn có thể giải thích cơ chế `Provider<T>`, tích hợp `jakarta.inject-api`, chọn thời điểm gọi `get()`, giải thích quan hệ với scope và kiểm thử các tình huống thiếu/nhiều bean.

## 2. Interface Provider<T> thực sự cung cấp gì?

`jakarta.inject.Provider<T>` có API tối giản:

```java
package jakarta.inject;

public interface Provider<T> {
    T get();
}
```

Đây là phần cốt lõi của interface được minh họa để học API. `T` là kiểu đối tượng mà injector/container cung cấp. Spring tạo và tiêm implementation của provider phù hợp với injection point. Bên sử dụng không phải viết implementation `Provider<T>` hoặc nhận trực tiếp `ApplicationContext`.

- `get()` **yêu cầu container cung cấp một đối tượng hoàn chỉnh và đã được inject** tại thời điểm gọi.
- Đối tượng là bean nào và có được tạo mới hay không phụ thuộc vào **bean definition, scope, qualifier và quy tắc chọn ứng viên**.
- `get()` là lookup **bắt buộc**: nếu Spring không tìm được bean hợp lệ hoặc gặp lỗi tạo bean, lời gọi có thể ném ngoại lệ runtime.
- Provider tiêu chuẩn **không** có `getIfAvailable()`, `getIfUnique()`, `stream()`, `orderedStream()` hoặc `getObject(args)`. Những khả năng này thuộc API mở rộng của Spring, như `ObjectProvider<T>`.

Trong Spring Framework 6+ và ứng dụng Spring Boot 3+, import đúng là:

```java
import jakarta.inject.Provider;
import jakarta.inject.Inject;
import jakarta.inject.Named;
```

Đừng vô tình import `javax.inject.Provider` từ hệ sinh thái Java EE/Spring đời cũ. Hai tên package là hai kiểu Java khác nhau và cần dependency tương ứng; bài này dùng namespace **`jakarta.inject`**.

### Cách hoạt động ở hai thời điểm

**Lúc tạo consumer:**

```text
Spring Container
    |
    +-- tạo WorkService
    |     |
    |     +-- inject Provider<Attempt> -- lưu provider
    |
    +-- WorkService sẵn sàng nhận tác vụ
```

**Lúc xử lý công việc:**

```text
WorkService.process()
    |
    +-- attemptProvider.get()
            |
            +-- Spring tìm bean Attempt phù hợp
            +-- áp dụng scope của Attempt
            +-- tạo hoặc tìm instance
            +-- trả instance cho lần xử lý hiện tại
```

Sơ đồ diễn giải đường đi của lookup. Nó không khẳng định bean singleton đích luôn được tạo lần đầu tại `get()`: một singleton không `@Lazy` có thể đã khởi tạo từ khi container refresh.

## 3. Vì sao cần chọn thời điểm lấy bean?

Giả sử `TaskRunner` là **singleton**, còn `Attempt` là **prototype**, mỗi instance lưu trạng thái riêng của một lần chạy.

### 3.1. Tiêm thẳng prototype vào singleton

```java
// Ví dụ cấu trúc; Attempt và TaskRunner là kiểu nghiệp vụ minh họa.
public final class TaskRunner {
    private final Attempt attempt;

    public TaskRunner(Attempt attempt) {
        this.attempt = attempt;
    }

    public void run() {
        attempt.execute();
    }
}
```

Nếu `TaskRunner` được tạo một lần, Spring giải quyết `Attempt` để cấp cho constructor **một lần**. Vì `TaskRunner` giữ nguyên tham chiếu, mỗi lần `run()` sẽ sử dụng chính đối tượng được tiêm trước đó. Annotation `@Scope("prototype")` của `Attempt` không có nghĩa Spring tự thay field ở các lần gọi tiếp theo.

### 3.2. Tiêm Provider rồi gọi get() ngay trong run()

```java
import jakarta.inject.Provider;

public final class TaskRunner {
    private final Provider<Attempt> attempts;

    public TaskRunner(Provider<Attempt> attempts) {
        this.attempts = attempts;
    }

    public void run() {
        Attempt current = attempts.get();
        current.execute();
    }
}
```

Đây cũng là đoạn minh họa cấu trúc, chưa là chương trình độc lập. Với `Attempt` scope `prototype`, **mỗi lời gọi `get()` giải quyết một bean prototype mới** theo quy tắc Spring. Nếu `Attempt` là singleton, các lần `get()` thường nhận cùng một đối tượng trong một `ApplicationContext`.

**Quyết định quan trọng:** lưu `Provider<Attempt>` trong consumer; chỉ lưu `Attempt` vào biến cục bộ khi bắt đầu một đơn vị công việc. Khi toàn bộ bước của một công việc phải dùng cùng attempt, gọi `get()` **một lần cho công việc đó** và truyền object cục bộ cho các bước. Đừng gọi `get()` lặp lại vô tình rồi tưởng các lời gọi chắc chắn cùng một attempt.

## 4. Thiết lập dự án Java 17+ với Spring Framework

Dưới đây là chương trình hoàn chỉnh dùng Spring Framework **6.2.19**, `jakarta.inject-api` **2.0.0**, Java **17+**. Ví dụ chủ ý chứng minh bốn điều: prototype được lấy muộn, scope singleton vẫn dùng lại instance, `@Named` chọn implementation giữa hai bean cùng interface, và `get()` phát sinh lỗi khi không có bean đích.

Tạo cấu trúc:

```text
provider-timing-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── ProviderTimingDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'provider-timing-demo'
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
    implementation 'jakarta.inject:jakarta.inject-api:2.0.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'ProviderTimingDemo'
}
```

`spring-context` cung cấp container và annotation cấu hình Spring. `jakarta.inject-api` cung cấp các kiểu `Provider`, `Inject` và `Named`. Trong một dự án Spring Boot có dependency management, version framework thường do BOM quản lý; khi đó không nên ép phiên bản Spring độc lập chỉ để thử provider.

**`src/main/java/ProviderTimingDemo.java`**

```java
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.inject.Named;
import jakarta.inject.Provider;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public class ProviderTimingDemo {

    record Attempt(int id) {}

    record Settings(String mode) {}

    interface Formatter {
        String format(String input);
    }

    interface OptionalMetrics {
        void record();
    }

    static final class WorkService {
        private final Provider<Attempt> attempts;
        private final Provider<Formatter> formatter;
        private final Provider<Settings> settings;
        private final Provider<OptionalMetrics> metrics;

        WorkService(
                Provider<Attempt> attempts,
                Provider<Formatter> formatter,
                Provider<Settings> settings,
                Provider<OptionalMetrics> metrics) {
            this.attempts = attempts;
            this.formatter = formatter;
            this.settings = settings;
            this.metrics = metrics;
        }

        void process(String label) {
            Attempt current = attempts.get();
            String output = formatter.get().format(label);
            System.out.println("process=" + output + "#" + current.id());
        }

        boolean sameSettings() {
            return settings.get() == settings.get();
        }

        void probeOptionalMetrics() {
            try {
                metrics.get();
                System.out.println("metrics=present");
            } catch (NoSuchBeanDefinitionException ex) {
                System.out.println("metrics=absent");
            }
        }
    }

    @Configuration
    public static class Config {
        private final AtomicInteger sequence = new AtomicInteger();

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        Attempt attempt() {
            int id = sequence.incrementAndGet();
            System.out.println("create-attempt-" + id);
            return new Attempt(id);
        }

        @Bean("mainFormatter")
        Formatter mainFormatter() {
            return input -> "main:" + input;
        }

        @Bean("backupFormatter")
        Formatter backupFormatter() {
            return input -> "backup:" + input;
        }

        @Bean
        Settings settings() {
            return new Settings("demo");
        }

        @Bean
        WorkService workService(
                Provider<Attempt> attempts,
                @Named("mainFormatter") Provider<Formatter> formatter,
                Provider<Settings> settings,
                Provider<OptionalMetrics> metrics) {
            return new WorkService(attempts, formatter, settings, metrics);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            WorkService work = context.getBean(WorkService.class);

            System.out.println("context-ready");
            System.out.println("before-first-get");
            work.process("A");
            work.process("B");
            System.out.println("singleton-same=" + work.sameSettings());
            work.probeOptionalMetrics();
        }
    }
}
```

Chạy trong thư mục `provider-timing-demo` với Gradle đã cài đặt:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows. Mã cần Spring và Jakarta Inject trên classpath, nên lệnh `javac ProviderTimingDemo.java` đơn lẻ từ thư mục mã nguồn không đủ. Tác vụ `gradle run` sẽ biên dịch mã và cung cấp dependencies đã khai báo.

**Kết quả mà `main` in ra trên stdout:**

```text
context-ready
before-first-get
create-attempt-1
process=main:A#1
create-attempt-2
process=main:B#2
singleton-same=true
metrics=absent
```

### Diễn giải kết quả

1. `Config` và `WorkService` được dựng khi context bắt đầu; việc tiêm `Provider<Attempt>` chưa tạo `Attempt` vì `Attempt` là prototype chưa được yêu cầu.
2. `context-ready` và `before-first-get` xuất hiện **trước** `create-attempt-1`: đây là dấu hiệu thời điểm lấy bean do code nghiệp vụ quyết định.
3. `process("A")` gọi `attempts.get()` và tạo attempt 1. `process("B")` gọi `get()` lần nữa và tạo attempt 2.
4. Trong context có hai `Formatter`. Annotation `@Named("mainFormatter")` gắn trên tham số provider giúp Spring chọn đúng bean mang tên đó, nên output là `main:A` và `main:B`. Nếu bỏ qualifier mà không có quy tắc xác định ứng viên khác, lookup đơn của `Provider<Formatter>` có thể thất bại vì nhiều candidate.
5. `Settings` có scope mặc định `singleton`; hai lần `settings.get()` trỏ đến cùng instance nên `singleton-same=true`.
6. Không có bean `OptionalMetrics`. Tiêm `Provider<OptionalMetrics>` được, nhưng khi `get()` thực sự chạy, Spring báo `NoSuchBeanDefinitionException`; đoạn `catch` chuyển tình huống vắng bean đã được dự kiến thành dòng `metrics=absent`.

Các dòng do Gradle hoặc môi trường build in thêm, nếu có, nằm ngoài stdout chủ động của `main`.

**Lưu ý về ví dụ tùy chọn:** cách bắt `NoSuchBeanDefinitionException` chỉ để chỉ ra semantics của `Provider.get()`. Trong code thật, nếu dependency có thể vắng mặt theo thiết kế và bạn đang dùng Spring, `ObjectProvider<T>.getIfAvailable()` hoặc `Optional<T>` thường diễn đạt hợp đồng optional rõ ràng hơn. Đừng bắt mọi `RuntimeException` và coi đó là “bean không tồn tại”, vì có thể đang che lỗi tạo bean hoặc lỗi cấu hình.

## 5. Chọn thời điểm get(): quyền kiểm soát thuộc consumer

### 5.1. Lấy tại ranh giới một tác vụ

```java
void handle(Order order) {
    ProcessingSession session = sessionProvider.get();
    session.validate(order);
    session.reserve(order);
    session.finish();
}
```

`ProcessingSession` và `Order` là các kiểu nghiệp vụ minh họa, provider đã được inject trước đó. Chỉ gọi `get()` khi `handle` bắt đầu. Cả ba bước cùng một đối tượng `session`, điều này đặc biệt quan trọng nếu bean prototype giữ trạng thái giao dịch nghiệp vụ nội bộ.

Nếu thay ba lần dùng `session` bằng ba lần gọi `sessionProvider.get()`, prototype có thể tạo ba phiên làm việc riêng: hệ quả này thường sai khi một tác vụ cần cùng trạng thái.

### 5.2. Chỉ lookup trên nhánh thực sự cần

```java
void handle(Request request) {
    if (request.requiresExport()) {
        ExportWorker worker = exportWorkers.get();
        worker.export(request);
    }
}
```

Giả định `Request`, `ExportWorker` là kiểu nghiệp vụ và `exportWorkers` là `Provider<ExportWorker>` đã inject. Nhánh không xuất dữ liệu sẽ không gọi provider. Đây là **trì hoãn truy cập từ phía consumer**; nó không bảo đảm singleton `ExportWorker` chưa từng được Spring khởi tạo lúc khởi động.

### 5.3. Không lấy sớm ngay trong constructor

```java
public ReportService(Provider<ReportBuilder> builders) {
    this.builder = builders.get();
}
```

Đoạn trên khiến bean đích được giải quyết lúc tạo `ReportService`, đánh mất mục đích chọn thời điểm của consumer. Nếu muốn mỗi báo cáo có `ReportBuilder` mới, lưu provider:

```java
public ReportService(Provider<ReportBuilder> builders) {
    this.builders = builders;
}

public Report build(Input input) {
    return builders.get().build(input);
}
```

Hai đoạn là ví dụ riêng phần; `ReportService`, `ReportBuilder`, `Report` và `Input` tượng trưng cho kiểu nghiệp vụ, không phải một chương trình chạy độc lập. Với bản thực tế, khai báo đầy đủ field, kiểu và phương thức tương ứng.

### 5.4. Không giữ prototype quá lâu

Đối tượng prototype tạo ra cho một công việc có thể chứa trạng thái mutable và tài nguyên. Chọn ranh giới thời gian sống của nó theo công việc; đừng vô tình đưa object vừa lấy vào field singleton rồi giữ vĩnh viễn. Provider trì hoãn tạo/lookup, **không tự hủy các prototype khi dùng xong**. Nếu bean prototype giữ file/socket/connection, cần thiết kế đóng tài nguyên rõ ràng, chẳng hạn `try-with-resources` khi kiểu đối tượng hỗ trợ `AutoCloseable`.

## 6. Scope quyết định get() trả về gì

| Scope bean đích | Kết quả thông thường của hai lần `get()` | Ý nghĩa của việc chọn thời điểm |
| --- | --- | --- |
| `singleton` | Cùng instance trong một container | Hoãn lần truy cập từ consumer; singleton có thể đã được tạo khi container khởi động. |
| `prototype` | Hai instance mới khi giải quyết hai lookup | Mỗi công việc có thể xin một bean độc lập đúng thời điểm. |
| `request` | Cùng instance trong cùng HTTP request, khác instance ở request khác | Phải gọi khi request scope đang hoạt động và gắn đúng request. |
| `session` | Dùng lại instance trong cùng HTTP session, tách giữa session | Cần session context phù hợp trong ứng dụng web. |
| Scope tùy biến | Phụ thuộc chính sách scope đã đăng ký | Provider tuân thủ scope; bản thân nó không định nghĩa lifetime. |

Một `Provider<T>` có thể được tiêm vào singleton dù bean `T` thuộc scope ngắn hơn. Tuy nhiên, nếu gọi bean request-scoped ở thread không gắn request, lookup có thể thất bại vì **scope không hoạt động**. Đặc biệt, dùng `ExecutorService` hoặc `@Async` không có nghĩa request context tự được truyền sang worker thread.

Với Spring, bean khai báo bằng `@Component` hay `@Named` vẫn mặc định là **singleton** nếu không khai báo scope khác. Đừng lấy mặc định scope của một DI framework khác rồi áp sang Spring. Để có prototype trong Spring:

```java
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope("prototype")
public class OneUseProcessor {
    public String run(String value) {
        return value.toUpperCase(java.util.Locale.ROOT);
    }
}
```

Đây là class Java hợp lệ khi có dependency Spring nhưng không chứa `main`. Có thể tiêm `Provider<OneUseProcessor>` vào consumer để lấy processor mỗi lần cần. Việc lựa chọn scope ở **bean đích**, không phải do đổi khai báo provider.

## 7. Kết hợp @Inject, @Named và qualifier

### 7.1. @Inject có thể dùng để tiêm Provider

```java
import jakarta.inject.Inject;
import jakarta.inject.Provider;
import org.springframework.stereotype.Component;

@Component
public final class ExportService {
    private final Provider<OneUseProcessor> processors;

    @Inject
    public ExportService(Provider<OneUseProcessor> processors) {
        this.processors = processors;
    }

    public String convert(String source) {
        return processors.get().run(source);
    }
}
```

Ví dụ này kết hợp với `OneUseProcessor` ở mục trước là các bean component có thể được Spring scan. `@Inject` đánh dấu constructor được tiêm; `@Autowired` của Spring cũng có thể sử dụng. Với một constructor duy nhất, Spring còn hỗ trợ constructor injection không cần annotation, nhưng dùng `@Inject` có ích khi bạn muốn thể hiện rõ hợp đồng Jakarta DI.

### 7.2. Chọn implementation bằng @Named ở điểm tiêm

Giả sử có hai bean cùng kiểu `MessageTransport`:

```java
@Bean("smtpTransport")
MessageTransport smtpTransport() {
    return new SmtpTransport();
}

@Bean("localTransport")
MessageTransport localTransport() {
    return new LocalTransport();
}
```

`MessageTransport` và hai implementation ở trên là kiểu minh họa, cần tự khai báo trong ứng dụng. Để chọn một bean cụ thể ở thời điểm `get()`:

```java
public NotificationService(
        @Named("smtpTransport") Provider<MessageTransport> transports) {
    this.transports = transports;
}
```

Trong class hoàn chỉnh, `NotificationService` có field `Provider<MessageTransport> transports` tương ứng. `@Named("smtpTransport")` trên **tham số provider** tạo điều kiện chọn ứng viên theo tên trong Spring. Nếu không có qualifier và nhiều bean cùng kiểu vẫn ngang nhau, `transports.get()` có thể ném `NoUniqueBeanDefinitionException`.

Nếu một bean được đánh dấu `@Primary`, Spring có thể chọn nó cho dependency theo kiểu khi không có qualifier cụ thể. Tuy nhiên, nên dùng qualifier rõ ràng khi nghiệp vụ thực sự yêu cầu một implementation xác định; đừng dựa vào sự trùng hợp của tên hoặc số lượng bean.

### 7.3. @Named trên bean và @Named tại injection point là hai vai trò khác nhau

```java
import jakarta.inject.Named;

@Named("csvExporter")
public final class CsvExporter implements Exporter {
    // Các phương thức Exporter được hiện thực ở đây.
}
```

Đây là phác họa class: `Exporter` là interface nghiệp vụ chưa được khai báo. `@Named` trên class làm bean có thể được nhận diện qua component scanning và tên được đặt; còn `@Named` trên tham số provider giúp thu hẹp ứng viên khi lấy bean. Không nhầm hai vai trò, dù cùng tên annotation.

## 8. Thiếu bean, nhiều bean và thời điểm phát sinh lỗi

Tiêm `Provider<T>` thành công không đảm bảo `get()` sau này sẽ thành công. Provider là một **cổng yêu cầu**; container chỉ giải quyết đối tượng đích khi cổng được gọi.

| Trạng thái lúc lookup | Kết quả `Provider<T>.get()` thường gặp trong Spring |
| --- | --- |
| Đúng một ứng viên hợp lệ | Trả bean theo scope của ứng viên đó. |
| Không có ứng viên | `NoSuchBeanDefinitionException`. |
| Nhiều ứng viên không phân định được | `NoUniqueBeanDefinitionException` (một dạng `NoSuchBeanDefinitionException`). |
| Bean có ứng viên nhưng khởi tạo thất bại | Ngoại lệ khởi tạo bean, như `BeanCreationException` hoặc ngoại lệ runtime liên quan. |
| Scope không hoạt động | Ngoại lệ scope, ví dụ `ScopeNotActiveException` với scope phù hợp. |

**Điểm rất dễ sai:** `NoUniqueBeanDefinitionException` là subclass của `NoSuchBeanDefinitionException` trong Spring. Vì vậy, đoạn code demo bắt `NoSuchBeanDefinitionException` có thể bắt cả trường hợp **không duy nhất**, không chỉ trường hợp thiếu hoàn toàn. Trong demo không đăng ký `OptionalMetrics` nên output `metrics=absent` đúng theo cấu hình đã biết; **không nên dùng kiểu catch đó trong ứng dụng thực để kết luận chắc chắn bean không tồn tại** khi có nhiều candidate.

Nếu cần tách hai tình huống trong Spring:

```java
try {
    TaskHandler handler = handlers.get();
    handler.handle();
} catch (org.springframework.beans.factory.NoUniqueBeanDefinitionException ex) {
    // Cấu hình nhiều bean mà không chọn được một ứng viên.
} catch (org.springframework.beans.factory.NoSuchBeanDefinitionException ex) {
    // Không có ứng viên phù hợp còn lại.
}
```

Đoạn minh họa giả định `handlers` đã inject `Provider<TaskHandler>` và `TaskHandler` có `handle()`. Cần bắt subclass **trước** superclass. Trong hệ thống thật, thường tốt hơn là đảm bảo cấu hình hợp lệ, báo lỗi rõ ràng và chỉ dùng optional khi yêu cầu nghiệp vụ thực sự cho phép.

### Khi dependency là optional

`Provider#get()` không có phương thức “nếu có thì lấy, không có thì trả null”. Nếu sử dụng Spring, có hai hướng rõ ràng hơn:

```java
// Cách 1: lookup tùy chọn tại thời điểm sử dụng.
org.springframework.beans.factory.ObjectProvider<Feature> features =
        /* được Spring inject */;
Feature feature = features.getIfAvailable();

// Cách 2: optional khi xây dựng consumer.
java.util.Optional<Feature> featureAtInjection =
        /* được Spring inject */;
```

Đây là snippet giới thiệu kiểu API, không phải biểu thức khởi tạo standalone. `ObjectProvider<T>` là API Spring mở rộng và phù hợp khi cần lookup optional nhiều lần. `Optional<T>` biểu đạt tình trạng có/không **khi injection**, không cung cấp lời gọi lookup mới ở những thời điểm tiếp theo. Tại nơi cần dependency bắt buộc, giữ `Provider.get()` để lỗi cấu hình được bộc lộ.

**Không dùng:** `provider.get() == null` như chiến lược optional chung, vì thiếu bean trong Spring có thể gây exception ngay trước phép so sánh.

## 9. Provider và vòng phụ thuộc

Một lý do hợp lệ để dùng provider là tách **thời điểm xây dựng bean** khỏi **thời điểm sử dụng bean kia**. Ví dụ luồng cấu trúc:

```text
A tạo trước
  └─ có Provider<B> nhưng chưa gọi get()
B tạo sau
  └─ constructor cần A đã tạo xong
A.callB() khi runtime
  └─ provider.get() -> B
```

Nếu cả `A` và `B` tiêm trực tiếp qua constructor, container có thể không giải quyết được vòng khởi tạo. Thay một cạnh bằng `Provider<B>` có thể giúp cả hai được tạo nếu **`A` không gọi `get()` trong constructor, `@PostConstruct` hoặc quá sớm khi graph đang được xây**.

Đoạn minh họa:

```java
@Component
class A {
    private final Provider<B> bs;

    @Inject
    A(Provider<B> bs) {
        this.bs = bs; // chưa gọi get()
    }

    String callB() {
        return bs.get().message();
    }
}

@Component
class B {
    private final A a;

    @Inject
    B(A a) {
        this.a = a;
    }

    String message() {
        return "ready";
    }
}
```

Cần import `jakarta.inject.Inject`, `jakarta.inject.Provider` và `org.springframework.stereotype.Component` để đoạn trên biên dịch trong một package. Hai class nên nằm trong package được scan. `B` nhận `A` để thể hiện cạnh phụ thuộc vòng; phương thức `message()` không gọi lại `A.callB()`, tránh recursion trong runtime.

**Giới hạn:** Provider không chữa mọi circular dependency. Nếu `A` gọi `bs.get()` trong constructor khi `B` chưa thể được tạo, vòng khởi tạo vẫn có thể thất bại. Nếu `B.message()` lập tức gọi `A.callB()`, chương trình có nguy cơ lặp đệ quy khi runtime. Cân nhắc tách trách nhiệm hoặc dùng sự kiện, service trung gian thay vì giữ thiết kế vòng quá phức tạp.

## 10. Provider so với các API khác

| Cách nhận dependency | Thời điểm giải quyết | API nổi bật | Trường hợp phù hợp |
| --- | --- | --- | --- |
| Constructor injection `T` | Lúc tạo consumer | Dùng `T` trực tiếp | Dependency bắt buộc, scope ổn định. |
| `jakarta.inject.Provider<T>` | Khi consumer gọi `get()` | `get()` | Lookup theo thời điểm với interface Jakarta DI đơn giản. |
| `ObjectFactory<T>` của Spring | Khi consumer gọi `getObject()` | `getObject()` | Tương tự Provider, sử dụng API Spring tối giản. |
| `ObjectProvider<T>` của Spring | Khi gọi method lookup/stream | `getObject()`, `getIfAvailable()`, `getIfUnique()`, `stream()` | Lookup optional hoặc nhiều bean, cần các tiện ích mở rộng Spring. |
| `@Lazy T` ở injection point | Khi proxy đích lần đầu được dùng | Dùng method của `T` qua proxy | Muốn giữ kiểu `T` nhưng trì hoãn giải quyết target; chú ý semantics proxy. |
| `Optional<T>` | Lúc inject consumer | `isPresent()`, `orElse()` | Optional được quyết định tại thời điểm tạo consumer. |
| `ApplicationContext.getBean(...)` | Khi gọi context | Lookup qua container API | Cơ sở hạ tầng thật sự cần thao tác container. |

**Không nhầm tên:** `Provider<T>` không phải `ObjectProvider<T>`; mặc dù Spring tích hợp cả hai, chúng là **hai interface khác nhau**. `jakarta.inject.Provider<T>` cũng không phải `jakarta.enterprise.inject.Instance<T>` của CDI: `Instance<T>` có thêm khả năng khám phá/lọc candidate trong môi trường CDI. Dùng đúng API của container đang chạy.

### Khi nên chọn Jakarta Provider

Bạn có thể chọn `Provider<T>` nếu chỉ cần `get()` và muốn code nghiệp vụ phụ thuộc vào **chuẩn Jakarta DI**, nhất là khi chia sẻ library với các môi trường hỗ trợ chuẩn này. Tuy nhiên, khác container có thể có chính sách scope, chọn bean và loại exception khác nhau; hợp đồng portable là `Provider.get()`, **không phải** toàn bộ chi tiết ngoại lệ Spring.

Nên chọn `ObjectProvider<T>` nếu nghiệp vụ thật sự cần trả `null` khi vắng bean, fallback, kiểm tra unique hoặc duyệt tập bean theo `stream()`/`orderedStream()`. Nên tiêm trực tiếp `T` nếu không có nhu cầu trì hoãn thực tế, vì cách đó bộc lộ lỗi dependency thiếu ngay khi khởi tạo.

## 11. Những nhầm lẫn phổ biến

### 11.1. “Mỗi lần get() là một object mới”

Sai với singleton. Provider gọi lại container; container áp dụng scope. Singleton thường cùng instance trong context, còn prototype mới cho mỗi lần giải quyết. Cần cấu hình scope bean đích cho đúng.

### 11.2. “Có Provider là bean sẽ lazy hoàn toàn”

Sai. Provider chỉ trì hoãn **lần lookup từ consumer**. Nếu target là singleton eager, container có thể đã tạo bean tại `refresh()`. Nếu mục tiêu là trì hoãn cả khởi tạo singleton, xem xét `@Lazy` ở bean definition hoặc cấu hình khác thích hợp, đồng thời kiểm tra xem có dependency khác khiến bean được tạo sớm không.

### 11.3. “Provider giúp dùng request bean từ thread bất kỳ”

Sai. Request/session scope cần context hoạt động đúng. `get()` ngoài scope hợp lệ có thể báo lỗi. Đừng dựa vào provider để truyền thread-local request context qua background executor.

### 11.4. “Có Provider nên lúc khởi động không thể thiếu bean”

Provider làm thời điểm lỗi có thể trễ đến `get()`. Nếu bean bắt buộc nhưng chỉ dùng khi production traffic chạy, cấu hình sai có thể không xuất hiện ở startup. Hãy bổ sung integration test hoặc kiểm tra cấu hình ở nơi phù hợp để phát hiện sớm.

### 11.5. “Gọi get() trong constructor vẫn là lazy lookup”

Việc lấy target đã diễn ra trong constructor, tức là **sớm**. Giữ provider đến method xử lý hoặc ranh giới hoạt động phù hợp.

### 11.6. “Provider làm prototype tự được cleanup”

Sai. Spring cung cấp lifecycle khởi tạo cho prototype nhưng không tự quản lý toàn bộ callback destruction của prototype sau khi cấp bean. Đối tượng giữ tài nguyên phải có cơ chế đóng độc lập.

### 11.7. “Bắt NoSuchBeanDefinitionException nghĩa là chắc chắn zero bean”

Sai do `NoUniqueBeanDefinitionException` kế thừa `NoSuchBeanDefinitionException` trong Spring. Ngoại lệ phải được phân loại đúng, hoặc tốt hơn là dùng qualifier và hợp đồng dependency hợp lý để loại tình trạng mơ hồ.

### 11.8. “@Named trên Provider tự tạo bean theo tên”

Sai. Qualifier giúp **chọn trong những bean đã đăng ký**. Nếu không có bean tương ứng, `get()` vẫn thất bại. Muốn Spring quản lý bean, phải đăng ký bean bằng `@Bean`, component scanning hoặc cơ chế phù hợp.

### 11.9. “Provider thread-safe đồng nghĩa target thread-safe”

Container xử lý lookup và scope; nó không biến mọi bean nhận về thành thread-safe. Một singleton mutable vẫn cần thiết kế concurrency riêng. Một prototype chỉ giúp mỗi lookup nhận object khác, không có nghĩa object được dùng an toàn khi chia sẻ giữa thread.

## 12. Cách kiểm thử để xác nhận thời điểm lấy bean

Trong unit test của consumer thuần Java, có thể truyền provider giả **không cần Spring**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import jakarta.inject.Provider;

public final class ProviderUnitDemo {
    record Attempt(int id) {}

    static final class Runner {
        private final Provider<Attempt> attempts;

        Runner(Provider<Attempt> attempts) {
            this.attempts = attempts;
        }

        int runOnce() {
            return attempts.get().id();
        }
    }

    public static void main(String[] args) {
        AtomicInteger creations = new AtomicInteger();
        Provider<Attempt> fake = () -> new Attempt(creations.incrementAndGet());

        Runner runner = new Runner(fake);
        System.out.println("before=" + creations.get());
        System.out.println("run1=" + runner.runOnce());
        System.out.println("run2=" + runner.runOnce());
        System.out.println("after=" + creations.get());
    }
}
```

Ví dụ độc lập ở mức code Java nhưng vẫn cần `jakarta.inject-api` trên compile/runtime classpath. Nếu đặt file `ProviderUnitDemo.java` trong cùng Gradle project trên, có thể chạy bằng cách đổi tạm `application.mainClass` sang `ProviderUnitDemo` hoặc dùng một Gradle run task khác.

Output của chính `main` trong `ProviderUnitDemo`:

```text
before=0
run1=1
run2=2
after=2
```

Provider lambda giả cho phép kiểm tra **consumer gọi lookup lúc nào** bằng counter. Nó không kiểm tra Spring scope/qualifier, vì behavior lambda do test tự định nghĩa. Để xác nhận thực tế với Spring, tạo `AnnotationConfigApplicationContext` và test rằng prototype cho hai object khác nhau, singleton cho cùng một object, `@Named` chọn đúng bean và lookup thiếu dependency ném exception ở thời điểm gọi.

### Checklist trước khi đưa vào production

1. Xác định dependency thực sự phải lookup theo thời điểm hay có thể tiêm trực tiếp.
2. Chọn scope của target: `singleton`, `prototype`, request hoặc scope phù hợp.
3. Quyết định một công việc cần **một** hay **nhiều** lần lookup và giữ object đúng thời gian sống.
4. Nếu có nhiều implementation, thiết kế `@Named`/qualifier hoặc `@Primary` một cách rõ ràng.
5. Xác định dependency là bắt buộc hay optional; `Provider.get()` thuộc hợp đồng bắt buộc.
6. Kiểm tra behavior khi context/scope chưa sẵn sàng, ứng viên bị thiếu và khi factory tạo bean thất bại.
7. Kiểm soát cleanup của prototype có tài nguyên và tính thread-safe của các bean được chia sẻ.

## 13. Câu hỏi tự luyện và đáp án

**Câu 1.** Một singleton tiêm `Provider<Session>`; `Session` là prototype. Vì sao `get()` trong mỗi `handle()` hữu ích hơn so với `get()` trong constructor?

**Đáp:** Mỗi `handle()` lấy một instance prototype mới theo ranh giới công việc. Gọi trong constructor sẽ giải quyết một instance sớm và, nếu giữ trong field, tái sử dụng nó.

**Câu 2.** Hai lần `provider.get()` trả cùng đối tượng. Provider có hỏng không?

**Đáp:** Không. Bean đích có thể là singleton hoặc scope khác tái sử dụng object trong phạm vi đang hoạt động. Cần nhìn vào scope, không suy đoán từ tên API.

**Câu 3.** Vì sao code tiêm `Provider<Formatter>` có thể startup thành công nhưng lúc gọi `get()` lại báo nhiều bean?

**Đáp:** Provider có thể được tiêm trước khi Spring cần chọn một `Formatter` cụ thể. Tại lookup, nếu nhiều candidate không phân định được bằng qualifier/primary/quy tắc autowire, Spring báo không duy nhất.

**Câu 4.** Có thể dùng `@Named` ở đâu để chọn đúng implementation qua provider?

**Đáp:** Đặt `@Named("beanName")` trên injection point `Provider<Interface>`, và bảo đảm một bean phù hợp được đăng ký với tên ấy.

**Câu 5.** Trong ví dụ hoàn chỉnh, nếu đổi `Attempt` thành singleton, quan sát gì thay đổi?

**Đáp:** Container có thể tạo attempt ngay khi refresh trước dòng `context-ready`; hai lần `get()` sẽ nhận cùng instance, nên cả `process("A")` và `process("B")` dùng id bằng nhau. `get()` vẫn là lookup theo thời điểm gọi, nhưng không buộc container tạo object mới.

**Câu 6.** Nếu không có bean optional, nên luôn dùng `try/catch RuntimeException` quanh `Provider.get()`?

**Đáp:** Không. Cách đó che nhiều lỗi khác nhau. Nếu đang dùng Spring và dependency optional theo thiết kế, `ObjectProvider.getIfAvailable()` hoặc `Optional<T>` là API phù hợp hơn tùy yêu cầu thời điểm; nếu bắt buộc, hãy để lỗi cấu hình bộc lộ.

## 14. Tài liệu chuẩn để đối chiếu

- [Spring Framework 6.2 — Using JSR 330 Standard Annotations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/standard-annotations.html): hỗ trợ `jakarta.inject.Provider`, `@Inject`, `@Named`, tương quan với `ObjectFactory`.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype và web scopes.
- [Spring Framework — Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html): qualifier, bean name và các quy tắc lựa chọn ứng viên.
- [Jakarta Dependency Injection — Provider API](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/inject/provider): hợp đồng `get()` và khả năng lookup theo scope.
- [Jakarta Inject — Inject API](https://javadoc.io/static/jakarta.inject/jakarta.inject-api/2.0.1/jakarta.inject/jakarta/inject/Inject.html): điểm tiêm và ngữ nghĩa `@Inject`.

**Ghi nhớ trọng tâm:** `Provider<T>` cho phép **consumer chọn lúc gọi `get()`**. Spring quyết định bean nào được cấp và tuổi thọ của nó dựa trên cấu hình IoC. Việc dùng đúng provider đòi hỏi phân biệt rạch ròi *thời điểm lookup*, *scope target* và *hợp đồng bắt buộc/tùy chọn*.
