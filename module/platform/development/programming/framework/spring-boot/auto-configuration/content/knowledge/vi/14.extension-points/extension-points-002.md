# `ObjectProvider` cho dependency tùy chọn và truy xuất theo nhu cầu trong Spring Boot Auto Configuration

Trong Spring Boot, một auto-configuration thường muốn cung cấp tính năng **có thể hoạt động dù một bean mở rộng không tồn tại**. Ví dụ một bộ xử lý giao dịch có thể gửi sự kiện tới `AuditSink` khi ứng dụng đã cấu hình nơi lưu audit, nhưng vẫn chạy bình thường khi chưa có `AuditSink`. Một nhu cầu khác là **chỉ lấy dependency khi thực sự cần** thay vì kéo nó vào lúc khởi tạo bean tiêu thụ.

`org.springframework.beans.factory.ObjectProvider<T>` giải quyết đúng hai nhu cầu này. Đây là một interface của Spring Framework; Spring có thể tiêm trực tiếp provider theo kiểu `T` qua constructor, phương thức `@Bean` hoặc injection point. Provider là **đầu mối tra cứu bean**: gọi các phương thức của nó để lấy một bean, nhận biết không có bean, xử lý nhiều ứng viên hoặc duyệt các bean cùng kiểu.

**Ghi nhớ ngay từ đầu:** tiêm `ObjectProvider<AuditSink>` **không buộc** context phải có `AuditSink`. Tuy nhiên, **khi thực sự gọi** `getObject()` hoặc `getIfAvailable()`, Spring vẫn cần giải quyết bean theo quy tắc thông thường: có thể trả một bean, tạo lazy bean, hoặc ném lỗi nếu thiếu/không duy nhất. `ObjectProvider` không biến mọi xung đột bean thành giá trị `null`.

## 1. Vấn đề: dependency bắt buộc hay tùy chọn?

Giả sử thư viện có một interface:

```java
public interface AuditSink {
    void write(String event);
}
```

Với constructor injection thông thường:

```java
public class PaymentService {
    private final AuditSink auditSink;

    public PaymentService(AuditSink auditSink) {
        this.auditSink = auditSink;
    }
}
```

Đây là các **đoạn minh họa** cần được đặt trong tệp Java đúng tên; nếu `PaymentService` được đăng ký thành bean mà context **không có** `AuditSink`, quá trình inject dependency có thể thất bại với `NoSuchBeanDefinitionException` được lồng trong lỗi tạo bean. Ngược lại, nếu có **nhiều bean cùng kiểu** mà không có cách chọn, Spring có thể báo `NoUniqueBeanDefinitionException`.

Nhưng với một tính năng mở rộng, thiếu `AuditSink` có thể hoàn toàn hợp lệ: app vẫn xử lý thanh toán, chỉ bỏ qua bước audit. Ta muốn bean xử lý thanh toán **luôn tồn tại** và **chỉ hỏi bean audit khi phát sinh giao dịch**.

```java
import org.springframework.beans.factory.ObjectProvider;

public class PaymentService {
    private final ObjectProvider<AuditSink> auditSinks;

    public PaymentService(ObjectProvider<AuditSink> auditSinks) {
        this.auditSinks = auditSinks;
    }

    public void pay(String event) {
        // Xử lý thanh toán trước...
        AuditSink sink = auditSinks.getIfAvailable();
        if (sink != null) {
            sink.write(event);
        }
    }
}
```

Đoạn code này minh họa nguyên tắc; `AuditSink` vẫn phải tồn tại ở thời điểm **biên dịch** vì được tham chiếu trong type signature, nhưng không bắt buộc có **bean `AuditSink` trong context**. Ví dụ runnable và kiểm thử hoàn chỉnh nằm ở phần 5.

## 2. Cơ chế: tiêm provider trước, tra cứu bean sau

Một constructor nhận `ObjectProvider<T>` được Spring tiêm đối tượng provider phù hợp. Điều đó **không đòi hỏi Spring lập tức tìm và khởi tạo một instance `T`** để truyền vào constructor. Mỗi lần code gọi provider, nó yêu cầu BeanFactory giải quyết đối tượng theo kiểu `T` và các quy tắc ứng viên hiện hành.

```text
ApplicationContext bắt đầu dựng bean PaymentService
    |
    | Inject ObjectProvider<AuditSink>
    v
PaymentService được tạo dù chưa có AuditSink
    |
    | Sau đó ứng dụng gọi pay(...)
    v
auditSinks.getIfAvailable()
    |
    +-- Không có AuditSink ------> null ------> Bỏ qua audit
    |
    +-- Một bean phù hợp -------> Bean đó --> Gọi write(...)
    |
    +-- Nhiều bean, mơ hồ -----> NoUniqueBeanDefinitionException
```

Ở đây có **hai trục độc lập**:

1. **Tính tùy chọn:** `getIfAvailable()` có thể trả `null` khi không tìm thấy ứng viên, nên phần mở rộng không bắt buộc phải được cấu hình.
2. **Truy xuất theo nhu cầu:** `getIfAvailable()` hoặc `getObject()` được gọi tại thời điểm bạn lựa chọn, thay vì luôn giải quyết dependency ngay trong constructor của consumer.

**Phân biệt truy xuất muộn với tạo bean muộn:** Một singleton `AuditSink` không đánh dấu `@Lazy` có thể **đã được khởi tạo khi ApplicationContext refresh** vì Spring thường tạo sẵn các non-lazy singleton. Provider không tự làm tất cả bean đích trở thành lazy. Nếu thực sự cần hoãn tạo `AuditSink` cho đến lần truy xuất đầu, thiết kế bean đích là `@Lazy` hoặc dùng scope thích hợp và kiểm thử hành vi. Với singleton lazy, lần truy xuất đầu tạo instance; những lần sau thông thường nhận lại **cùng singleton**. Với prototype, mỗi lần tra cứu có thể tạo **instance mới**.

Provider cũng **không bảo đảm thao tác rẻ hoặc bất đồng bộ**: khi cần tạo bean có constructor tốn thời gian hoặc kết nối tài nguyên, lời gọi `getObject()` vẫn có thể chặn và ném lỗi khởi tạo.

## 3. Các phương thức quan trọng của `ObjectProvider<T>`

Nhóm API phổ biến trong Spring Framework 6.x/Spring Boot 3.x:

| API | Khi không có bean phù hợp | Khi có một ứng viên được chọn | Khi có nhiều ứng viên không thể chọn duy nhất |
| --- | --- | --- | --- |
| `getObject()` | Ném `NoSuchBeanDefinitionException` | Trả bean | Ném `NoUniqueBeanDefinitionException` |
| `getIfAvailable()` | Trả `null` | Trả bean | Có thể ném `NoUniqueBeanDefinitionException` |
| `getIfAvailable(Supplier<T>)` | Gọi supplier để lấy fallback | Trả bean, không cần fallback | Vẫn có thể ném lỗi không duy nhất |
| `ifAvailable(Consumer<T>)` | Không gọi consumer | Gọi consumer với bean | Vẫn có thể ném lỗi không duy nhất |
| `getIfUnique()` | Trả `null` | Trả bean | Trả `null` nếu không có ứng viên chính được xác định |
| `getIfUnique(Supplier<T>)` | Dùng fallback | Trả bean | Dùng fallback khi không xác định được ứng viên duy nhất |
| `ifUnique(Consumer<T>)` | Không gọi consumer | Gọi consumer | Không gọi consumer nếu không xác định được ứng viên duy nhất |
| `stream()` | Stream rỗng | Stream chứa ứng viên phù hợp | Stream của nhiều ứng viên; không đòi chọn một bean duy nhất |
| `orderedStream()` | Stream rỗng | Stream chứa ứng viên | Stream được sắp theo cơ chế `Ordered`/`@Order` tương ứng |

**Chú ý `@Primary`:** với nhiều bean cùng kiểu nhưng **một bean được Spring xác định là ứng viên ưu tiên duy nhất** bằng `@Primary`, các phép tra cứu đơn có thể chọn ứng viên đó. Vì vậy `getIfUnique()` không được hiểu máy móc là “trả `null` nếu số bean lớn hơn một”; cần xét quy tắc autowire của container.

### 3.1. `getObject()`: dependency bắt buộc tại thời điểm gọi

```java
AuditSink sink = auditSinks.getObject();
sink.write("created-order");
```

Dùng khi thao tác hiện tại **không thể tiếp tục nếu thiếu** `AuditSink`. Việc inject provider ban đầu không lỗi, nhưng **lời gọi này** sẽ ném exception nếu không tìm thấy bean hoặc không chọn được ứng viên duy nhất.

### 3.2. `getIfAvailable()` và supplier fallback

```java
AuditSink sink = auditSinks.getIfAvailable();
if (sink != null) {
    sink.write("order-paid");
}
```

Nếu muốn một implementation dự phòng **không đăng ký trong Spring context**:

```java
AuditSink sink = auditSinks.getIfAvailable(
        () -> event -> System.out.println("Local audit: " + event)
);
sink.write("order-paid");
```

Đây là **trích đoạn** dùng interface `AuditSink` có method `write(String)`. Supplier chỉ được gọi nếu không có bean thích hợp; object do supplier tạo **không tự trở thành bean** nên đừng kỳ vọng Spring tự inject dependency, chạy lifecycle callbacks hay áp dụng mọi bean post-processor lên object này. Với mặc định cần Spring quản lý, hãy thiết kế bean mặc định ở auto-configuration bằng `@ConditionalOnMissingBean`.

### 3.3. `getIfUnique()`: chỉ tiếp tục nếu chọn được một bean

```java
AuditSink unique = auditSinks.getIfUnique();
if (unique != null) {
    unique.write("only-if-unique");
}
```

Nếu không có bean hoặc nhiều ứng viên không chọn được một, `unique` là `null`. Đây là cách diễn đạt hợp lý khi tính năng chỉ nên bật nếu cấu hình không mơ hồ, nhưng không nên âm thầm bỏ qua lỗi cấu hình quan trọng của sản phẩm mà không ghi log/thông báo.

### 3.4. `ifAvailable(...)` và `ifUnique(...)`

```java
auditSinks.ifAvailable(sink -> sink.write("payment-accepted"));
auditSinks.ifUnique(sink -> sink.write("single-recipient"));
```

Hai cách này hữu ích khi chỉ thực thi side effect nếu bean được chọn. Chúng không tự làm thao tác ghi audit bất đồng bộ. `ifAvailable` vẫn không xử lý hộ xung đột nhiều ứng viên.

### 3.5. `stream()` và `orderedStream()` cho extension point nhiều bean

Nếu một tính năng được thiết kế để có **nhiều plugin** cùng kiểu:

```java
auditSinks.orderedStream()
        .forEach(sink -> sink.write("payment-accepted"));
```

`stream()` không có hợp đồng thứ tự cụ thể; `orderedStream()` dùng comparator của Spring, có thể xét `Ordered` hoặc `@Order`. Khi thứ tự xử lý plugin có ý nghĩa nghiệp vụ, hãy khai báo `@Order` trên implementation hoặc bean definition và kiểm thử thứ tự. Khi duyệt stream, **việc lấy từng bean có thể tạo instance**; đừng hiểu `stream()` là cách xem metadata mà không bao giờ khởi tạo bean.

**Không nhầm:** `ObjectProvider<List<AuditSink>>` tìm một **bean kiểu danh sách**, không tương đương với cách duyệt tất cả `AuditSink`. Nếu mục đích là nhiều bean cùng interface, dùng `ObjectProvider<AuditSink>.stream()` / `orderedStream()`.

## 4. `ObjectProvider` khác gì các kiểu optional injection khác?

| Cơ chế | Đặc điểm | Giới hạn/cân nhắc |
| --- | --- | --- |
| Constructor nhận `AuditSink` | Dependency bắt buộc, được giải quyết khi tạo consumer | Thiếu bean hoặc nhiều ứng viên không phân giải được có thể làm context không khởi động. |
| `@Autowired(required = false)` | Cho phép bỏ qua một injection point không bắt buộc | Chủ yếu dùng cho field/setter và cấu hình inject; không cung cấp API tra cứu nhiều lần như provider. |
| Constructor nhận `Optional<AuditSink>` | Diễn đạt không có bean bằng `Optional.empty()` | Thông thường resolution xảy ra tại thời điểm injection; không chủ đích là lookup lại theo nhu cầu. |
| `@Nullable AuditSink` | Có thể nhận `null` cho optional injection point | Không cung cấp cơ chế truy xuất theo thời điểm mong muốn. |
| `@Lazy` injection | Có thể tiêm lazy proxy để hoãn truy cập target | Nếu target vắng, lỗi có thể phát sinh khi proxy được dùng; phụ thuộc khả năng proxy cho kiểu đích. |
| `ObjectProvider<AuditSink>` | Có nhiều API tra cứu tùy chọn, on demand, xử lý unique và nhiều ứng viên | Consumer phải tự chọn lúc tra cứu, fallback và chính sách xử lý ambiguity. |
| `@ConditionalOnBean(AuditSink.class)` | Chỉ đăng ký một cấu hình/bean khi đã có `AuditSink` ở lúc xét condition | Nếu muốn bean consumer **vẫn tồn tại khi vắng dependency**, loại bỏ bean consumer là hành vi không phù hợp. |
| `@ConditionalOnMissingBean(MyConsumer.class)` | Cho phép người dùng thay bean consumer mặc định | Giải quyết khả năng ghi đè cấu hình, không thay cho `ObjectProvider` bên trong consumer. |

Ví dụ đối chiếu hai ý định:

```java
// Khi KHÔNG có AuditSink, vẫn tạo PaymentService:
@Bean
PaymentService paymentService(ObjectProvider<AuditSink> sinks) {
    return new PaymentService(sinks);
}
```

```java
// Khi KHÔNG có AuditSink, hoàn toàn KHÔNG đăng ký PaymentService:
@Bean
@ConditionalOnBean(AuditSink.class)
PaymentService paymentService(AuditSink sink) {
    return new PaymentService(sink);
}
```

Đây là các **trích đoạn kiến trúc** thuộc hai phương án khác nhau; `PaymentService` ở phương án thứ hai phải có constructor nhận `AuditSink`. Chúng thể hiện hai contract sản phẩm **khác nhau**. Cần quyết định sản phẩm cho phép thiếu audit hay coi audit là điều kiện bắt buộc trước khi chọn annotation.

## 5. Ví dụ chạy được: Java 17 + Spring Boot 3.3.5

Bộ kiểm thử sau sử dụng `ApplicationContextRunner` để tạo context cô lập. Một auto-configuration luôn cung cấp `AuditService` mặc định nếu user chưa cung cấp service, và tiêm `ObjectProvider<AuditSink>`. `AuditSink` là điểm mở rộng tùy chọn.

Các test chứng minh:
1. Không có `AuditSink`: `AuditService` vẫn được tạo; `getIfAvailable()` trả `null`, `getObject()` ném lỗi khi thực sự gọi.
2. Có `@Lazy AuditSink`: tạo `AuditService` **không kéo theo** khởi tạo sink; sink chỉ được tạo khi service sử dụng provider.
3. Có hai sink cùng kiểu: `orderedStream()` duyệt được cả hai theo `@Order`; `getIfAvailable()` báo không duy nhất khi không có `@Primary`.
4. Có hai sink trong đó một là `@Primary`: `getIfUnique()` có thể chọn ứng viên chính.
5. User cung cấp `AuditService`: condition `@ConditionalOnMissingBean(AuditService.class)` làm bean mặc định nhường chỗ.

### 5.1. Cấu trúc thư mục

```text
object-provider-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── ObjectProviderDemoTest.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>object-provider-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 5.2. File test độc lập

Tạo `src/test/java/demo/ObjectProviderDemoTest.java`:

```java
package demo;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Primary;
import org.springframework.core.annotation.Order;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ObjectProviderDemoTest {

    interface AuditSink {
        String id();
        String send(String event);
    }

    record NamedSink(String id) implements AuditSink {
        @Override
        public String send(String event) {
            return id + ":" + event;
        }
    }

    static final class AuditService {
        private final ObjectProvider<AuditSink> sinks;

        AuditService(ObjectProvider<AuditSink> sinks) {
            this.sinks = sinks;
        }

        String send(String event) {
            AuditSink sink = sinks.getIfAvailable();
            return sink == null ? "skipped:" + event : sink.send(event);
        }

        String sendWithFallback(String event) {
            AuditSink sink = sinks.getIfAvailable(
                    () -> new NamedSink("local"));
            return sink.send(event);
        }

        AuditSink requiredSink() {
            return sinks.getObject();
        }

        AuditSink uniqueSink() {
            return sinks.getIfUnique();
        }

        List<String> orderedSinkIds() {
            return sinks.orderedStream()
                    .map(AuditSink::id)
                    .toList();
        }
    }

    @AutoConfiguration
    static class AuditAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(AuditService.class)
        AuditService auditService(ObjectProvider<AuditSink> sinks) {
            return new AuditService(sinks);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class LazySinkConfiguration {
        @Bean
        AtomicInteger sinkCreations() {
            return new AtomicInteger();
        }

        @Bean
        @Lazy
        AuditSink lazySink(AtomicInteger sinkCreations) {
            sinkCreations.incrementAndGet();
            return new NamedSink("remote");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class MultiSinkConfiguration {
        @Bean
        @Order(20)
        AuditSink alphaSink() {
            return new NamedSink("alpha");
        }

        @Bean
        @Order(-5)
        AuditSink betaSink() {
            return new NamedSink("beta");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrimarySinkConfiguration {
        @Bean
        @Primary
        AuditSink preferredSink() {
            return new NamedSink("preferred");
        }

        @Bean
        AuditSink otherSink() {
            return new NamedSink("other");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomServiceConfiguration {
        @Bean
        AuditService customAuditService(ObjectProvider<AuditSink> sinks) {
            return new AuditService(sinks);
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            AuditAutoConfiguration.class));

    @Test
    void missingOptionalSinkDoesNotPreventServiceCreation() {
        runner.run(context -> {
            AuditService service = context.getBean(AuditService.class);

            assertThat(service.send("pay")).isEqualTo("skipped:pay");
            assertThat(service.sendWithFallback("pay"))
                    .isEqualTo("local:pay");
            assertThat(service.uniqueSink()).isNull();
            assertThat(service.orderedSinkIds()).isEmpty();
            assertThatThrownBy(service::requiredSink)
                    .isInstanceOf(NoSuchBeanDefinitionException.class);
        });
    }

    @Test
    void providerDoesNotForceLazySinkCreationAtInjectionTime() {
        runner.withUserConfiguration(LazySinkConfiguration.class)
                .run(context -> {
                    AtomicInteger creations =
                            context.getBean(AtomicInteger.class);
                    AuditService service = context.getBean(AuditService.class);

                    assertThat(creations.get()).isZero();

                    assertThat(service.send("pay")).isEqualTo("remote:pay");
                    assertThat(creations.get()).isEqualTo(1);

                    assertThat(service.send("refund"))
                            .isEqualTo("remote:refund");
                    assertThat(creations.get()).isEqualTo(1);
                });
    }

    @Test
    void multipleSinksCanBeStreamedButNotResolvedAsOne() {
        runner.withUserConfiguration(MultiSinkConfiguration.class)
                .run(context -> {
                    AuditService service = context.getBean(AuditService.class);

                    assertThat(service.orderedSinkIds())
                            .containsExactly("beta", "alpha");
                    assertThat(service.uniqueSink()).isNull();
                    assertThatThrownBy(() -> service.send("pay"))
                            .isInstanceOf(NoUniqueBeanDefinitionException.class);
                });
    }

    @Test
    void primaryCandidateCanMakeUniqueResolutionPossible() {
        runner.withUserConfiguration(PrimarySinkConfiguration.class)
                .run(context -> {
                    AuditService service = context.getBean(AuditService.class);

                    assertThat(service.uniqueSink()).isNotNull();
                    assertThat(service.uniqueSink().id())
                            .isEqualTo("preferred");
                    assertThat(service.send("pay"))
                            .isEqualTo("preferred:pay");
                });
    }

    @Test
    void customServiceMakesAutoConfiguredServiceBackOff() {
        runner.withUserConfiguration(CustomServiceConfiguration.class)
                .run(context -> {
                    assertThat(context.getBeansOfType(AuditService.class))
                            .containsOnlyKeys("customAuditService");
                });
    }
}
```

Chạy từ thư mục `object-provider-demo` bằng **Java 17+** và Maven:

```bash
mvn test
```

**Kết quả kỳ vọng:** cả năm kiểm thử thành công. Maven Surefire thường ghi tổng hợp tương đương `Tests run: 5, Failures: 0, Errors: 0, Skipped: 0`. Test không có `System.out.println` nên không phụ thuộc một dòng stdout nghiệp vụ cụ thể; log Maven có thể thay đổi theo môi trường.

| Test | Quan sát | Điều chứng minh |
| --- | --- | --- |
| `missingOptionalSinkDoesNotPreventServiceCreation` | `AuditService` tồn tại, trả `skipped:pay` hoặc fallback `local:pay` | Provider nhận được khi không có bean đích; method chọn rõ xử lý trường hợp thiếu. |
| `providerDoesNotForceLazySinkCreationAtInjectionTime` | Counter là 0 trước lần `send` đầu, 1 sau đó | Injection provider không tự khởi tạo `@Lazy` sink; singleton được dùng lại. |
| `multipleSinksCanBeStreamedButNotResolvedAsOne` | ID theo thứ tự `beta, alpha`; tra cứu một sink ném exception | `@Order` phục vụ thứ tự stream, không tự chọn một ứng viên duy nhất. |
| `primaryCandidateCanMakeUniqueResolutionPossible` | `preferredSink` được chọn | `@Primary` có thể làm các phép tra cứu đơn giải quyết được một ứng viên. |
| `customServiceMakesAutoConfiguredServiceBackOff` | Chỉ có `customAuditService` | `@ConditionalOnMissingBean` cho phép thay consumer mặc định; đây là vai trò khác provider. |

### Vì sao ví dụ hoạt động?

- `AuditService` chỉ phụ thuộc vào `ObjectProvider<AuditSink>`, nên Spring có thể tạo `AuditService` khi hoàn toàn không có `AuditSink`.
- `LazySinkConfiguration.lazySink` có `@Lazy`. Context tạo singleton `AtomicInteger` bình thường, nhưng định nghĩa `lazySink` chưa tạo instance trước khi code gọi provider. Lần đầu gọi `getIfAvailable()` tạo bean; lần sau nhận singleton đã có.
- `MultiSinkConfiguration` đăng ký hai bean cùng kiểu, mỗi bean có tên khác nhau. Không có `@Primary` nên yêu cầu **một bean duy nhất** không xác định được; `orderedStream()` vẫn lấy được cả hai.
- `PrimarySinkConfiguration` có hai bean nhưng một `@Primary`, nhờ đó container chọn được ứng viên đơn theo quy tắc autowire.
- `CustomServiceConfiguration` được xử lý trước auto-configuration và tạo bean `AuditService` do ứng dụng cung cấp. Condition `@ConditionalOnMissingBean(AuditService.class)` trong auto-configuration không khớp; default consumer nhường chỗ.
- Các lớp auto-configuration **lồng trong file test** được nạp trực tiếp bởi `AutoConfigurations.of`. Trong **starter thật**, class auto-configuration phải được nêu bằng tên đầy đủ trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

Bộ test là cách quan sát **hành vi bean resolution**, khác với việc chỉ assert annotation có tồn tại. Các nhánh thiếu bean, lazy, nhiều ứng viên và backoff được kiểm chứng trong những context tách biệt.

## 6. Áp dụng `ObjectProvider` trong một auto-configuration thực tế

### 6.1. Bean tính năng chính luôn có, bean tích hợp là tùy chọn

Ví dụ thư viện cung cấp `JobDispatcher` nhưng logging bổ sung chỉ hoạt động khi có `JobEventPublisher`:

```java
// Trích đoạn kiến trúc trong lớp auto-configuration:
@Bean
@ConditionalOnMissingBean(JobDispatcher.class)
JobDispatcher jobDispatcher(ObjectProvider<JobEventPublisher> publisher) {
    return new JobDispatcher(publisher);
}
```

`JobDispatcher` là bean của thư viện, còn `JobEventPublisher` là extension point do app có thể khai báo. Nếu app không có publisher, dispatcher vẫn sống và có thể bỏ qua bước publish hoặc dùng fallback theo thiết kế. Đây là **trích đoạn**; các class liên quan phải được định nghĩa riêng.

### 6.2. Không truy xuất provider trong `@Bean` factory method nếu muốn thực sự hoãn

So sánh:

```java
@Bean
JobDispatcher eagerResolve(ObjectProvider<JobEventPublisher> provider) {
    // Tra cứu ngay trong quá trình tạo JobDispatcher.
    JobEventPublisher publisher = provider.getIfAvailable();
    return new JobDispatcher(publisher);
}
```

với:

```java
@Bean
JobDispatcher onDemand(ObjectProvider<JobEventPublisher> provider) {
    // Chỉ lưu provider; JobDispatcher tự gọi khi thực sự publish.
    return new JobDispatcher(provider);
}
```

Đây là **hai thiết kế minh họa** cho các constructor khác nhau, không phải ví dụ đặt cạnh nhau để biên dịch nguyên trạng. Ở phiên bản đầu, tuy nhận provider nhưng code **lập tức gọi** `getIfAvailable()`: lợi ích trì hoãn lookup đã mất. Phiên bản thứ hai giữ provider trong bean consumer để giải quyết khi cần.

### 6.3. Provider không thay thế condition kích hoạt và điều kiện classpath

Nếu bean consumer **chỉ có nghĩa khi thư viện ngoài tồn tại**, vẫn nên xét `@ConditionalOnClass` ở mức cấu hình thích hợp. `ObjectProvider<ThirdPartyService>` chỉ xử lý việc **thiếu bean** tại runtime; nó không làm cho Java class `ThirdPartyService` biến mất khỏi kiểu khai báo lúc load class hay biến dependency Maven thành không cần thiết.

Nếu thiếu publisher nghĩa là chức năng **hoàn toàn không nên có**, `@ConditionalOnBean(JobEventPublisher.class)` tại mức class/`@Bean` có thể phù hợp hơn. Chỉ dùng `ObjectProvider` khi consumer vẫn có giá trị khi dependency vắng hoặc cần lấy bean vào lúc cụ thể.

Nếu starter cung cấp **bean mặc định có thể thay thế**, kết hợp `@ConditionalOnMissingBean(Consumer.class)` để back off, còn `ObjectProvider<Extension>` để consumer truy xuất extension khi chạy. Hai cơ chế có mục đích khác nhau.

### 6.4. Một ứng dụng nhiều plugin

```java
public final class ExtensionPipeline {
    private final ObjectProvider<Extension> extensions;

    public ExtensionPipeline(ObjectProvider<Extension> extensions) {
        this.extensions = extensions;
    }

    public void execute(String input) {
        extensions.orderedStream().forEach(e -> e.apply(input));
    }
}
```

Đây là **đoạn minh họa** giả định có interface `Extension` chứa `void apply(String)`. Nếu có các plugin theo mức `@Order`, thứ tự của `orderedStream()` phục vụ pipeline. Nếu không có plugin, stream rỗng và không có thao tác nào xảy ra. Nếu thao tác có side effect, phải quyết định chính sách lỗi, rollback và thứ tự thực thi; provider chỉ làm nhiệm vụ tìm bean.

## 7. Các điểm cần thận trọng

### 7.1. Thiếu bean khác với nhiều bean

`getIfAvailable()` **chỉ nhẹ nhàng xử lý trường hợp không có bean**. Nếu có hai bean `AuditSink` không được phân giải bằng `@Primary`/`@Qualifier`, nó có thể ném `NoUniqueBeanDefinitionException`. Các lựa chọn rõ ràng:

- Muốn đúng **một** sink: cấu hình một bean, dùng `@Primary` hoặc `@Qualifier` để chọn, hoặc báo lỗi khi đa nghĩa.
- Muốn **tất cả** sink cùng xử lý: dùng `orderedStream()` hoặc `stream()` rồi quyết định cách sắp thứ tự.
- Muốn **chỉ xử lý nếu chọn được duy nhất**: `getIfUnique()`/`ifUnique(...)`, và xử lý rõ tình huống không có ứng viên hợp lệ.

Đừng bắt exception rộng rồi coi mọi lỗi tạo bean là “dependency không có”. Lỗi constructor, thiếu config, lỗi I/O khi khởi tạo bean là vấn đề khác, không nên bị che bằng fallback.

### 7.2. Lazy và vòng đời bean

`ObjectProvider` làm chậm **thời điểm yêu cầu dependency**, không tự cam kết **đối tượng đích chưa được khởi tạo**. Một non-lazy singleton có thể đã được Spring tạo trong refresh. Nếu việc khởi tạo tốn tài nguyên là điều cần tránh, hãy kết hợp `@Lazy` hoặc thiết kế bean/scope đúng và test như `AtomicInteger` ở phần 5.

Nếu dependency có **prototype scope**, mỗi lần gọi provider có thể nhận đối tượng khác, vì vậy cache kết quả `getObject()` trong field làm mất ý nghĩa “truy xuất theo nhu cầu mỗi lần”. Với request/session scope, truy xuất phải nằm trong **scope đang hoạt động**, hoặc sử dụng proxy phù hợp; nếu gọi ngoài request, Spring có thể ném `ScopeNotActiveException`. Không được mặc định xem scope lỗi như bean không tồn tại.

### 7.3. Tra cứu động có giới hạn

Provider gắn với BeanFactory và mỗi lần gọi sẽ thực hiện **resolution mới dựa trên trạng thái factory tại thời điểm đó**. Tuy vậy, trong ứng dụng Boot bình thường bean definitions được thiết lập trong quá trình khởi động. `ObjectProvider` không phải cơ chế **hot reload plugin** hoặc đảm bảo bạn có thể tự ý thêm, xóa và ghi đè bean definition khi singleton đã chạy.

### 7.4. Generic type và qualifier

`ObjectProvider<AuditSink>` giải quyết theo kiểu `AuditSink`. Nếu có nhiều bean, `@Qualifier` trên injection point có thể giới hạn nhóm ứng viên:

```java
// Trích đoạn constructor trong một bean được Spring quản lý:
public AuditService(
        @Qualifier("criticalAuditSink")
        ObjectProvider<AuditSink> provider) {
    this.provider = provider;
}
```

Nếu dùng ví dụ này, cần import `org.springframework.beans.factory.annotation.Qualifier` và khai báo field `provider`. Qualifier giúp chỉ rõ bean muốn chọn; vẫn cần phân biệt lỗi thiếu bean và lựa chọn fallback. Với kiểu generic, Spring có thể dùng thông tin generic để đối sánh; tránh xóa kiểu bằng raw `ObjectProvider` vì làm resolution kém chính xác.

### 7.5. Tránh tra cứu trong mỗi vòng lặp nóng một cách vô ích

`getObject()`/`getIfAvailable()` thực hiện resolution tại thời điểm gọi. Nếu xử lý hàng triệu event/giây, chỉ gọi theo nhu cầu có ý nghĩa: đôi khi nên xây một pipeline một lần sau khi context đã ổn định. Nhưng **đừng cache nhầm** dependency có scope prototype hoặc cần resolution lại. Quyết định dựa trên vòng đời và yêu cầu thay đổi plugin, không chỉ dựa vào tên API.

## 8. Chẩn đoán khi auto-configuration hoạt động sai kỳ vọng

| Hiện tượng | Khả năng xảy ra | Cách kiểm tra/sửa |
| --- | --- | --- |
| Context báo thiếu `AuditSink` ngay khi tạo `AuditService` | Consumer inject trực tiếp `AuditSink` ở nơi khác, hoặc code gọi `provider.getObject()` trong constructor/`@Bean` | Kiểm tra call stack, giữ provider và chỉ gọi tại thời điểm cần; chọn `getIfAvailable()` nếu dependency tùy chọn. |
| `getIfAvailable()` ném `NoUniqueBeanDefinitionException` | Nhiều bean cùng kiểu, không có ứng viên đơn theo quy tắc container | Dùng `@Qualifier`/`@Primary`, hoặc duyệt `orderedStream()` nếu thiết kế hỗ trợ nhiều plugin. |
| Bean đích đã tạo dù service chỉ giữ provider | Bean đích là non-lazy singleton được pre-instantiate lúc context refresh | Đánh dấu bean đích `@Lazy` khi thích hợp, đo instance creation bằng test. |
| `getIfUnique()` trả `null` dù có bean cùng kiểu | Có nhiều ứng viên không chọn được duy nhất (hoặc đang không có bean phù hợp) | Kiểm tra bean names/types, `@Primary` và qualifier. |
| `stream()` có thứ tự khác kỳ vọng | `stream()` không hứa sắp `@Order` | Dùng `orderedStream()` cùng các khai báo order thích hợp. |
| `orderedStream()` không rỗng và plugin bị tạo sớm | Việc tiêu thụ stream có thể yêu cầu instance của từng bean | Phân biệt lúc tạo stream với lúc terminal operation, cân nhắc lifecycle/lazy. |
| Custom consumer bean có rồi mà auto-config vẫn tạo default | `@ConditionalOnMissingBean` thiếu/sai kiểu, hoặc thứ tự xử lý không đúng | Kiểm tra condition và thứ tự auto-configuration; dùng `ApplicationContextRunner`. |
| Tắt `@ConditionalOnBean` nhưng cần consumer luôn tồn tại | Condition đang loại hẳn bean consumer nếu thiếu extension | Dùng `ObjectProvider<Extension>` và thiết kế no-op/fallback trong consumer. |
| Bean request-scoped bị truy xuất ngoài request | Scope chưa hoạt động | Chỉ truy xuất trong scope hợp lệ, hoặc áp dụng scoped proxy. |

Khi cần điều tra, bật `--debug` cho ứng dụng Boot để xem **Condition Evaluation Report** (khi auto-configuration được match hoặc back off). Để phân tích **bean resolution trong runtime**, dùng test cô lập, log tên/kiểu bean và stack trace tại đúng lời gọi provider. Không nên kết luận một lỗi lookup là lỗi của condition nếu định nghĩa bean đích đã đăng ký nhưng khởi tạo thất bại.

## 9. Câu hỏi thực hành

**1.** Auto-configuration có `@Bean PaymentService paymentService(ObjectProvider<AuditSink> sinks)`. Không có `AuditSink`. `PaymentService` có thể được tạo không?  
**Đáp án:** Có, nếu không có điều kiện/lỗi khác cản. Đối tượng provider không đòi có bean `AuditSink` tại thời điểm injection.

**2.** Trong constructor, `paymentService` gọi ngay `sinks.getObject()` và hiện không có `AuditSink`. Có còn “optional” không?  
**Đáp án:** Không ở thời điểm gọi. `getObject()` yêu cầu có đối tượng và có thể ném `NoSuchBeanDefinitionException`.

**3.** Đổi `getObject()` thành `getIfAvailable()`, có hai bean cùng kiểu và không có `@Primary`. Có chắc nhận `null`?  
**Đáp án:** Không. Trường hợp thiếu và trường hợp không duy nhất khác nhau; `getIfAvailable()` có thể ném `NoUniqueBeanDefinitionException`.

**4.** Một sink được khai báo `@Bean @Lazy`. Service chỉ giữ `ObjectProvider<AuditSink>`. Sink có bắt buộc được tạo lúc dựng service không?  
**Đáp án:** Không. Trong ngữ cảnh ví dụ, sink tạo khi provider được gọi lần đầu. Không nhầm với singleton không `@Lazy` có thể đã được khởi tạo sớm.

**5.** Có ba plugin cùng kiểu cần chạy theo `@Order`. Nên dùng `getIfAvailable()` hay `orderedStream()`?  
**Đáp án:** `orderedStream()` nếu thiết kế cho phép **cả ba** chạy; `getIfAvailable()` hướng đến **một** bean.

**6.** `getIfUnique()` thấy hai bean cùng kiểu nhưng một được `@Primary`. Có nhất thiết trả `null`?  
**Đáp án:** Không. Spring có thể chọn ứng viên primary duy nhất.

**7.** Dùng `ObjectProvider` có tự động ngăn starter đăng ký bean consumer default khi ứng dụng cung cấp consumer custom không?  
**Đáp án:** Không. Dùng `@ConditionalOnMissingBean(Consumer.class)` ở auto-configuration cho cơ chế backoff; provider chỉ giải quyết dependency.

**8.** Nếu đưa `ObjectProvider<AuditSink>` vào một constructor, có thể bỏ dependency Maven chứa chính interface `AuditSink` khỏi classpath không?  
**Đáp án:** Không thể suy ra vậy. Tên kiểu vẫn xuất hiện trong chữ ký Java; phải thiết kế điều kiện classpath và tách cấu hình thích hợp nếu phần tích hợp là tùy chọn ở cấp thư viện.

## Tóm tắt kiến thức

`ObjectProvider<T>` giúp **tiêm một đầu mối tra cứu** thay vì bắt buộc tiêm ngay một instance `T`. Dùng `getIfAvailable()`/`ifAvailable(...)` khi dependency không bắt buộc; `getIfUnique()` khi chỉ dùng nếu xác định được ứng viên duy nhất; `getObject()` khi dependency bắt buộc tại lúc gọi; và `stream()`/`orderedStream()` khi thiết kế cho phép nhiều implementation. Hãy phân biệt **lookup on demand** với **lazy bean initialization**, xử lý mơ hồ nhiều bean rõ ràng và kết hợp condition trong auto-configuration theo đúng contract.

### Tài liệu tham khảo chính thức

- Spring Framework 6.1 — `ObjectProvider<T>` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/ObjectProvider.html
- Spring Framework — `BeanFactory` và cơ chế provider: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/BeanFactory.html
- Spring Framework — `@Autowired` và optional injection: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration và `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html