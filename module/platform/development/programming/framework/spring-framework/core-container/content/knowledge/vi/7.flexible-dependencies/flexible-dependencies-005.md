# Tra cứu trì hoãn bằng ObjectFactory và ObjectProvider trong Spring Core Container

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **tra cứu trì hoãn (on-demand lookup)**: tiêm một đối tượng cung cấp quyền tra cứu, rồi chỉ yêu cầu bean đích tại thời điểm thực sự cần dùng.
- Phân biệt `ObjectFactory<T>` và `ObjectProvider<T>`, chọn đúng API khi dependency bắt buộc, tùy chọn hoặc có nhiều implementation.
- Dự đoán tác động của scope `singleton`, `prototype` và scope theo request đối với kết quả `getObject()`.
- Viết mã Spring theo constructor injection, kiểm soát trường hợp không có bean, nhiều bean và thứ tự các bean.
- Tránh nhầm tra cứu trì hoãn với mặc định khởi tạo lười, tạo mới mỗi lần hoặc quản lý vòng đời tự động.

**Bối cảnh:** Spring IoC Container chịu trách nhiệm tạo bean, xác định dependency và quản lý scope. Khi một singleton cần dùng một đối tượng prototype mới cho mỗi lượt xử lý, hoặc một plugin chỉ có ở một số cấu hình, việc tiêm trực tiếp một bean đích từ lúc khởi tạo thường không diễn đạt được nhu cầu ấy.

## 2. Vấn đề: tiêm bean trực tiếp so với tra cứu khi cần

Cách tiêm trực tiếp:

```java
public class JobService {
    private final JobContext context;

    public JobService(JobContext context) {
        this.context = context;
    }

    public void runJob() {
        context.execute();
    }
}
```

Đây là ví dụ cấu trúc, giả định `JobContext` có phương thức `execute()`. `JobService` nắm một tham chiếu `JobContext` đã được giải quyết khi tạo service. Nếu `JobService` là singleton còn `JobContext` là prototype, tham chiếu ấy **không tự đổi** thành một prototype mới ở mỗi lần gọi `runJob()`.

Thay vào đó:

```java
import org.springframework.beans.factory.ObjectProvider;

public class JobService {
    private final ObjectProvider<JobContext> contexts;

    public JobService(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    public void runJob() {
        JobContext current = contexts.getObject();
        current.execute();
    }
}
```

Spring tiêm một provider có thể tra cứu `JobContext`. Mỗi lời gọi `getObject()` sẽ yêu cầu container giải quyết bean ở **thời điểm gọi**, theo quy tắc scope, qualifier và ứng viên hiện có. Trường hợp bean prototype, mỗi lần có thể nhận đối tượng mới; bean singleton vẫn thường trả cùng đối tượng. Hai đoạn trên chỉ minh họa cách tiêm, chưa phải chương trình chạy độc lập.

### Trình tự cơ chế

1. Spring tạo `JobService` và tiêm `ObjectProvider<JobContext>` (hoặc `ObjectFactory<JobContext>`).
2. Service lưu đối tượng tra cứu, không nhất thiết lưu bean `JobContext`.
3. Khi xử lý một công việc, service gọi `getObject()` hoặc API khác trên provider.
4. Container chọn ứng viên hợp lệ, giải quyết scope và cung cấp bean; lỗi về thiếu/không duy nhất hoặc lỗi khởi tạo có thể xuất hiện **tại lần tra cứu**.

**Cần phân biệt:** Provider trì hoãn việc *giải quyết dependency qua provider*, nhưng không đảm bảo tất cả singleton ứng viên đều chưa được khởi tạo. Các singleton không đánh dấu lazy có thể đã được Spring tạo trong giai đoạn khởi động context.

## 3. Hai interface liên hệ với nhau thế nào?

Cả hai thuộc package `org.springframework.beans.factory`:

```java
@FunctionalInterface
public interface ObjectFactory<T> {
    T getObject();
}

// Quan hệ kiểu; lược bỏ các phương thức khác để tập trung vào ý chính.
public interface ObjectProvider<T> extends ObjectFactory<T> {
    // getIfAvailable(), getIfUnique(), stream(), orderedStream(), ...
}
```

Đây là phác họa quan hệ interface, **không phải mã thay thế source Spring**. `ObjectFactory<T>` là hợp đồng tối giản với một thao tác `getObject()`. `ObjectProvider<T>` mở rộng interface đó bằng tra cứu tùy chọn, tra cứu khi duy nhất, cung cấp tham số tạo bean và duyệt nhiều ứng viên. Vì vậy một `ObjectProvider<T>` cũng dùng được ở nơi chấp nhận `ObjectFactory<T>`.

| Nhu cầu | `ObjectFactory<T>` | `ObjectProvider<T>` |
| --- | --- | --- |
| Lấy một bean khi gọi | `getObject()` | `getObject()` |
| Thiếu bean mà muốn nhận `null` hoặc fallback | Không có API riêng | `getIfAvailable()`, `getIfAvailable(Supplier)` |
| Không có ứng viên duy nhất thì bỏ qua | Không có API riêng | `getIfUnique()`, `getIfUnique(Supplier)` |
| Chỉ xử lý nếu có bean/bean duy nhất | Không có API riêng | `ifAvailable(Consumer)`, `ifUnique(Consumer)` |
| Lấy nhiều bean cùng kiểu | Không có API riêng | `stream()`, `orderedStream()`, `iterator()` |
| Truyền đối số tạo bean tại thời điểm gọi | Không hỗ trợ trực tiếp | `getObject(Object... args)` |

Trong ứng dụng Spring thông thường, **ưu tiên `ObjectProvider<T>` nếu cần optional, nhiều ứng viên, sắp thứ tự hoặc fallback**; `ObjectFactory<T>` đủ khi chỉ cần một hàm lấy bean bắt buộc.

## 4. Chọn API theo hợp đồng của dependency

`ObjectFactory<T>` chỉ có `getObject()`: khi gọi, phải phân giải được một bean phù hợp; thiếu bean hoặc nhiều ứng viên không phân định được đều là lỗi. `ObjectProvider<T>` mở rộng lựa chọn cho đúng nhu cầu của consumer:

| Nhu cầu tại thời điểm gọi | API | Khi không có bean | Khi nhiều ứng viên vẫn mơ hồ |
| --- | --- | --- | --- |
| Bắt buộc lấy một bean | `getObject()` | Ném lỗi thiếu bean | Ném lỗi không duy nhất |
| Thiếu bean là hợp lệ | `getIfAvailable()` / `ifAvailable(...)` | Trả `null` / không chạy callback | Vẫn có thể ném lỗi |
| Chỉ xử lý khi chọn được một bean | `getIfUnique()` / `ifUnique(...)` | Trả `null` / không chạy callback | Trả `null` / không chạy callback |
| Chạy toàn bộ plugin phù hợp | `stream()` / `orderedStream()` | Stream rỗng | Duyệt nhiều bean, không ép chọn một |

`@Qualifier`, `@Primary` và metadata của bean vẫn tham gia phân giải: có nhiều bean nhưng một bean primary hợp lệ thì phép tra cứu đơn vẫn có thể thành công. Các overload nhận `Supplier<T>` chỉ tạo fallback khi đúng điều kiện thiếu/không chọn được của từng API; object tự tạo trong supplier không mặc nhiên được Spring quản lý. Không phương thức nào nuốt lỗi khởi tạo bean. Bài tiếp theo phân tích riêng từng phương thức bằng bốn cấu hình bean và output cụ thể; ở bài này, điểm cần ghi nhớ là **`ObjectFactory` tối giản, còn `ObjectProvider` cho consumer chọn chính sách lookup**.

## 5. Ví dụ hoàn chỉnh chạy được với Spring Framework và Java 17+

Ví dụ dùng **Spring Framework 6.2.19** để có phiên bản phụ thuộc cụ thể, không cần Spring Boot. Ta sẽ quan sát bean prototype được tạo khi gọi, plugin tùy chọn vắng mặt và thứ tự nhiều bean theo `@Order`.

Tạo ba file:

```text
provider-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/Demo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'provider-demo'
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
    mainClass = 'Demo'
}
```

**`src/main/java/Demo.java`**

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

import org.springframework.beans.factory.ObjectFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;
import org.springframework.core.annotation.Order;

public class Demo {
    interface RequestToken {
        int number();
    }

    static final class Token implements RequestToken {
        private final int number;

        Token(int number) {
            this.number = number;
        }

        @Override
        public int number() {
            return number;
        }
    }

    interface OptionalNotifier {
        void notifyUser(String message);
    }

    interface Formatter {
        String name();
    }

    static final class ConsumerService {
        private final ObjectFactory<RequestToken> tokenFactory;
        private final ObjectProvider<RequestToken> tokenProvider;
        private final ObjectProvider<OptionalNotifier> notifierProvider;
        private final ObjectProvider<Formatter> formatterProvider;

        ConsumerService(
                ObjectFactory<RequestToken> tokenFactory,
                ObjectProvider<RequestToken> tokenProvider,
                ObjectProvider<OptionalNotifier> notifierProvider,
                ObjectProvider<Formatter> formatterProvider) {
            this.tokenFactory = tokenFactory;
            this.tokenProvider = tokenProvider;
            this.notifierProvider = notifierProvider;
            this.formatterProvider = formatterProvider;
        }

        void demonstrate() {
            System.out.println("before-lookup");

            RequestToken first = tokenFactory.getObject();
            RequestToken second = tokenProvider.getObject();

            System.out.println("different=" + (first != second));
            System.out.println("numbers=" + first.number() + "," + second.number());
            System.out.println("notifier=" +
                    (notifierProvider.getIfAvailable() == null ? "absent" : "present"));
            System.out.println("unique-formatter=" +
                    (formatterProvider.getIfUnique() == null ? "none" : "one"));
            System.out.println("formatters=" + formatterProvider.orderedStream()
                    .map(Formatter::name)
                    .collect(Collectors.joining(",")));
        }
    }

    @Configuration
    public static class Config {
        private final AtomicInteger sequence = new AtomicInteger();

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        RequestToken requestToken() {
            int next = sequence.incrementAndGet();
            System.out.println("create-token-" + next);
            return new Token(next);
        }

        @Bean
        @Order(10)
        Formatter plainFormatter() {
            return () -> "plain";
        }

        @Bean
        @Order(1)
        Formatter jsonFormatter() {
            return () -> "json";
        }

        @Bean
        ConsumerService consumerService(
                ObjectFactory<RequestToken> tokenFactory,
                ObjectProvider<RequestToken> tokenProvider,
                ObjectProvider<OptionalNotifier> notifierProvider,
                ObjectProvider<Formatter> formatterProvider) {
            return new ConsumerService(
                    tokenFactory, tokenProvider, notifierProvider, formatterProvider);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            System.out.println("context-ready");
            context.getBean(ConsumerService.class).demonstrate();
        }
    }
}
```

**Chạy** tại thư mục `provider-demo` với Gradle có sẵn và JDK tương thích toolchain:

```bash
gradle run --quiet
```

Hoặc dùng `./gradlew run --quiet` khi dự án có Gradle Wrapper (trên Windows dùng `gradlew.bat run --quiet`). Chương trình Java được biên dịch qua tác vụ Gradle `compileJava`; không thể chạy `javac Demo.java` đơn lẻ nếu chưa cung cấp Spring JAR lên classpath.

**Các dòng do chương trình in ra (stdout):**

```text
context-ready
before-lookup
create-token-1
create-token-2
different=true
numbers=1,2
notifier=absent
unique-formatter=none
formatters=json,plain
```

**Giải thích từng quan sát:**

1. `requestToken()` tạo **prototype**. Context khởi động nhưng chưa tạo token, vì không ai yêu cầu bean đích trước `demonstrate()`.
2. `tokenFactory.getObject()` và `tokenProvider.getObject()` mỗi lần dẫn tới một lượt tạo prototype, nên `different=true`; counter tăng từ 1 lên 2.
3. Không có `@Bean OptionalNotifier`. Việc tiêm `ObjectProvider<OptionalNotifier>` vẫn thực hiện được, `getIfAvailable()` trả `null`.
4. Có hai `Formatter`, không có ứng viên được chọn là duy nhất, nên `getIfUnique()` trả `null`.
5. `orderedStream()` duyệt cả hai formatter theo thứ tự Spring xác định từ `@Order(1)` rồi `@Order(10)`: `json,plain`. `stream()` thông thường không cam kết thứ tự này.

Bản demo đủ để thực hành cả hai interface và thấy rõ tác động của scope. Các log cấu hình môi trường/Gradle, nếu có, không nằm trong bảng stdout do `Demo` tự in.

## 6. Scope quyết định ý nghĩa “mỗi lần gọi”

| Scope bean đích | Hai lần `provider.getObject()` trong cùng điều kiện | Lưu ý |
| --- | --- | --- |
| `singleton` (mặc định) | Thường **cùng instance** trong một container | Provider không biến singleton thành prototype; non-lazy singleton có thể đã được khởi tạo từ lúc refresh. |
| `prototype` | **Hai instance khác nhau** trong các lần giải quyết thông thường | Mỗi lookup tạo mới; container không quản lý hủy prototype đầy đủ sau khi cấp. |
| `request` | Thường cùng instance trong **cùng HTTP request**; request khác có instance khác | Chỉ tra cứu khi request scope đang hoạt động, trừ khi đã có cơ chế proxy phù hợp. |
| `session` | Thường cùng instance trong một session; session khác có instance khác | Không tự kéo dài/đổi scope của bean bằng provider. |

Ví dụ một singleton gọi `provider.getObject()` hai lần thì có thể nhận cùng singleton. Thêm `@Scope("prototype")` ở **bean đích** mới thay đổi quy tắc tạo instance; không cần đổi scope của consumer.

Với prototype chứa tài nguyên cần đóng (socket, file, client...), phải thiết kế cơ chế kết thúc vòng đời thích hợp; đừng suy luận rằng `getObject()` tự đăng ký hủy tất cả prototype. Nếu cần dùng request-scoped dependency trong singleton, provider là cách lấy đối tượng theo scope tại thời điểm xử lý request, nhưng gọi từ thread không có request context có thể phát sinh `ScopeNotActiveException`.

## 7. Nhiều bean, @Qualifier và @Primary

Giả sử có hai implementation `PaymentGateway`:

```java
@Bean("cardGateway")
PaymentGateway cardGateway() {
    return new CardGateway();
}

@Bean("bankGateway")
PaymentGateway bankGateway() {
    return new BankGateway();
}
```

Đây là đoạn cấu hình minh họa; `PaymentGateway`, `CardGateway` và `BankGateway` là các kiểu nghiệp vụ giả định. Nếu consumer tiêm `ObjectProvider<PaymentGateway>` không có qualifier và container không chọn được ứng viên rõ ràng, gọi `getObject()` / `getIfAvailable()` có thể báo nhiều ứng viên.

**Chỉ định đích ở injection point:**

```java
public PaymentService(
        @org.springframework.beans.factory.annotation.Qualifier("cardGateway")
        ObjectProvider<PaymentGateway> gateways) {
    this.gateways = gateways;
}
```

Với các field và constructor tương ứng trong `PaymentService`, provider này được gắn điều kiện ứng viên `cardGateway`; `getObject()` sẽ tra cứu theo điều kiện đó. Đây là đoạn minh họa constructor, không phải một class hoàn chỉnh để biên dịch riêng.

**Nếu muốn một ứng viên mặc định**, có thể khai báo `@Primary` trên bean phù hợp. Spring có thể ưu tiên primary trong tra cứu đơn; `getIfUnique()` không đơn giản đếm tất cả định nghĩa rồi luôn trả null khi số lượng lớn hơn một. **Nếu muốn dùng tất cả implementation**, gọi `stream()` hoặc `orderedStream()` và tránh tra cứu đơn.

```java
// Đặt trong một bean đã được tiêm ObjectProvider<PaymentGateway>.
gateways.orderedStream().forEach(gateway -> gateway.healthCheck());
```

Trong ví dụ trên, `PaymentGateway` cần khai báo phương thức `healthCheck()`. `orderedStream()` dùng quy tắc thứ tự của Spring như `Ordered`/`@Order`; `stream()` không có cam kết sắp xếp cố định. Việc lấy stream và tiêu thụ stream có thể kích hoạt giải quyết/tạo các bean phù hợp; không dùng stream chỉ để kiểm tra sự tồn tại nếu bạn không muốn khởi tạo tất cả.

## 8. Tiện ích API thường dùng khi viết ứng dụng

### 8.1. Fallback chỉ khi cần

```java
NotificationSender sender =
        senders.getIfAvailable(() -> new ConsoleNotificationSender());
```

`senders` có kiểu `ObjectProvider<NotificationSender>`; hai lớp/interface trong ví dụ là kiểu nghiệp vụ giả định. Nếu có ứng viên hợp lệ, Spring cấp bean đã cấu hình. Chỉ khi không có bean, lambda mới tạo đối tượng mặc định **ngoài container**. Vì vậy fallback tự tạo không mặc nhiên nhận lifecycle, proxy, AOP hay dependency injection như Spring-managed bean.

Nếu yêu cầu là chỉ chạy khi ứng viên duy nhất:

```java
senders.ifUnique(sender -> sender.send("ready"));
```

`NotificationSender` được giả định có `send(String)`. Nếu không có bean hoặc không chọn được duy nhất, action không chạy.

### 8.2. Truyền đối số khi khởi tạo bean

`ObjectProvider<T>` có `getObject(Object... args)` để yêu cầu bean với đối số runtime, thường hữu ích cho prototype có constructor hoặc factory method nhận tham số. Đoạn cấu hình minh họa:

```java
public record ExportTask(String format) {}

@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
ExportTask exportTask(String format) {
    return new ExportTask(format);
}

// Trong bean consumer đã được tiêm:
ExportTask csv = tasks.getObject("csv");
// tasks có kiểu ObjectProvider<ExportTask>.
```

`getObject("csv")` yêu cầu tạo đối tượng prototype với đối số `format="csv"`. Đây **không phải** phương thức bổ sung của `ObjectFactory<T>` và không nên dùng để truyền tham số tùy tiện vào một singleton đã được tạo. Đối với code hoàn chỉnh, đặt record, factory method và provider injection vào class/configuration hợp lệ như ở ví dụ `Demo`.

### 8.3. Duyệt nhiều bean

```java
List<String> formatterNames = formatterProvider.orderedStream()
        .map(Formatter::name)
        .toList();
```

Snippet dùng `Formatter`/`formatterProvider` từ chương trình `Demo` và Java 17. `orderedStream()` phù hợp cho pipeline plugin/filter có ưu tiên. `stream()` hoặc for-each qua provider phù hợp khi thứ tự không có ý nghĩa nghiệp vụ. Từ Spring Framework 6.2 có thêm một số overload cho lọc candidate; cần kiểm tra Javadoc của đúng phiên bản nếu sử dụng API đó.

## 9. So sánh với những cách tiêm dependency khác

| Cách | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| Tiêm trực tiếp `T` | Dependency được giải quyết lúc tạo consumer | Dependency bắt buộc, dùng thường xuyên, scope tương thích. |
| `ObjectFactory<T>` | Lấy một đối tượng khi gọi `getObject()` | Cần runtime lookup tối giản, chẳng hạn lấy prototype theo mỗi lần xử lý. |
| `ObjectProvider<T>` | Runtime lookup, optional, unique và nhiều ứng viên | Feature tùy chọn, plugin, prototype, nhiều implementation. |
| `@Lazy T` tại injection point | Spring thường tiêm proxy và giải quyết target khi proxy được sử dụng | Muốn giữ API gọi như đối tượng trực tiếp; khó biểu đạt điều kiện thiếu bean và nhiều ứng viên. |
| `Optional<T>` | Thể hiện optional tại **thời điểm injection** | Chỉ cần biết có/không tại thời điểm khởi tạo consumer, không cần lookup lặp lại. |
| `jakarta.inject.Provider<T>` | API chuẩn `get()` theo JSR-330/Jakarta Inject | Muốn phụ thuộc vào API DI tiêu chuẩn; cần dependency Jakarta Inject tương ứng. |
| `ApplicationContext.getBean(...)` | Tra cứu trực tiếp qua context | Mã hạ tầng thật sự cần thao tác container; không nên rải trong business service. |

**Phân biệt `ObjectFactory<T>` và `FactoryBean<T>`:** `ObjectFactory` là handle tra cứu được đưa cho bên sử dụng; `FactoryBean` là điểm mở rộng để một thành phần trong container **sản xuất** object cho bean definition. Chúng không đồng nghĩa và không nên hoán đổi chỉ vì tên gần giống.

## 10. Những lỗi thường gặp và cách sửa

**Lỗi 1 — Nghĩ provider luôn tạo instance mới.**

Sai: “Gọi `getObject()` hai lần luôn nhận hai đối tượng khác nhau.”

Đúng: kết quả do **scope bean đích** quyết định. Kiểm tra bean có `@Scope("prototype")` hay không; với singleton, việc tái sử dụng instance là hành vi dự kiến.

**Lỗi 2 — Nghĩ `getIfAvailable()` nuốt cả lỗi nhiều bean.**

Khi không có bean, method trả `null`. Nhưng nếu có nhiều ứng viên ngang nhau, lỗi `NoUniqueBeanDefinitionException` vẫn có thể xảy ra. Nếu cần bỏ qua sự mơ hồ, dùng `getIfUnique()`; nếu cần tất cả, dùng `stream()`; nếu phải chọn một, thiết kế qualifier/primary.

**Lỗi 3 — Gọi `getObject()` ngay trong constructor của consumer.**

```java
// Kém hiệu quả nếu mục tiêu là lookup mỗi lần xử lý:
this.worker = workerProvider.getObject();
```

Gọi sớm như vậy thực chất giải quyết và lưu một bean tại lúc dựng consumer. Nếu muốn prototype mới mỗi lượt xử lý, lưu **provider** và gọi `getObject()` trong phương thức xử lý.

**Lỗi 4 — Quên xử lý kết quả `null`.**

```java
// Có thể NPE nếu không có bean:
provider.getIfAvailable().run();

// An toàn hơn:
provider.ifAvailable(service -> service.run());
```

Giả định bean có phương thức `run()`. Nếu không có bean nhưng hành vi là bắt buộc, `getObject()` mới phản ánh đúng hợp đồng.

**Lỗi 5 — Dùng provider thay cho việc thiết kế scope và lifecycle.**

Provider không tạo ra một request context, không giải quyết việc prototype cần đóng tài nguyên, và không tự động làm một đối tượng trở nên thread-safe. Chỉ tra cứu bean trong context/scope hợp lệ và giữ thời gian sử dụng phù hợp.

**Lỗi 6 — Dựa vào thứ tự không được bảo đảm.**

Nếu pipeline có thứ tự quan trọng, sử dụng `orderedStream()` cùng metadata `@Order`/`Ordered`, không dựa vào thứ tự đăng ký bean hay thứ tự ngẫu nhiên của `stream()`.

**Lỗi 7 — Che lỗi cấu hình bằng fallback tùy ý.**

Fallback có thể làm chương trình “chạy được” nhưng thiếu chức năng bắt buộc. Chỉ dùng `getIfAvailable` cho dependency thực sự **optional**; các thành phần cốt lõi nên dùng `getObject()` hoặc tiêm trực tiếp để fail fast.

## 11. Checklist thiết kế và kiểm thử

Trước khi chọn API, tự trả lời bốn câu hỏi:

1. Dependency **bắt buộc hay tùy chọn**? Bắt buộc: `getObject()`; tùy chọn: `getIfAvailable()`/`ifAvailable()`.
2. Có **nhiều implementation** không? Nếu cần tất cả, dùng stream; nếu cần duy nhất, quy định bằng qualifier/primary hoặc dùng `getIfUnique()`.
3. Bean đích có scope gì? Singleton không thay đổi instance theo từng lookup; prototype tạo mới; web scope cần context phù hợp.
4. Có cần **thời điểm truy cập** do consumer kiểm soát không? Nếu không, constructor injection trực tiếp thường đơn giản và rõ ràng hơn.

Các tình huống nên thử trong test:

- Không đăng ký `OptionalNotifier`: consumer vẫn khởi động và `getIfAvailable() == null`.
- Đăng ký một notifier hợp lệ: provider trả notifier; callback `ifAvailable` chạy.
- Đăng ký hai formatter không primary: `getIfUnique() == null`, `getObject()`/`getIfAvailable()` có thể báo không duy nhất.
- Đăng ký `@Primary` trên một formatter: kiểm tra khả năng chọn bean mặc định bằng lookup đơn.
- Gọi lấy `RequestToken` prototype hai lần: hai instance khác nhau; đổi scope thành singleton: cùng instance.
- So sánh `orderedStream()` với khai báo `@Order`; kiểm tra logic dựa trên thứ tự mong đợi.

**Câu hỏi tự luyện:**

1. Vì sao inject `ObjectFactory<PrototypeBean>` vào singleton giúp lấy đối tượng prototype mới trên từng lần dùng?
2. `getIfAvailable()` và `getIfUnique()` khác gì khi có hai ứng viên ngang nhau?
3. Thay `@Scope("prototype")` bằng singleton trong ví dụ `Demo` thì các dòng liên quan đến token thay đổi ra sao?
4. Khi nào `@Lazy` hợp lý hơn, và khi nào `ObjectProvider<T>` diễn đạt ý định rõ hơn?

**Gợi ý đáp án:** (1) Service giữ handle tra cứu; mỗi lượt gọi container áp dụng scope prototype. (2) `getIfAvailable()` có thể ném lỗi không duy nhất; `getIfUnique()` trả `null`. (3) Bean token thường được tạo một lần và hai lookup nhận cùng instance; không còn bảo đảm hai lần tạo và `different` trở thành `false`. (4) `@Lazy` tiện khi chỉ cần proxy để trì hoãn sử dụng một target; provider phù hợp khi consumer phải tự quyết định thời điểm tra cứu, tính optional hoặc nhiều ứng viên.

## 12. Tài liệu chuẩn để đối chiếu

- [Spring Framework — ObjectFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectFactory.html)
- [Spring Framework — ObjectProvider Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectProvider.html)
- [Spring Framework — Scoped Beans as Dependencies](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring Framework — Autowiring Collaborators](https://docs.spring.io/spring-framework/reference/core/beans/autowire.html)
- [Spring Framework — Classpath Scanning and @Lazy injection points](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)

**Ghi nhớ:** `ObjectFactory` và `ObjectProvider` cho phép **lookup khi cần**; chính **scope và quy tắc lựa chọn bean** quyết định cái gì được trả về, còn phương thức provider quyết định cách xử lý tình huống thiếu/không duy nhất.
