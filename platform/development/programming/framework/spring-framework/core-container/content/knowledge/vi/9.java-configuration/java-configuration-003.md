# Tham số phương thức `@Bean` biểu diễn phụ thuộc trong Spring Java Configuration

## 1. Mục tiêu: đưa quan hệ phụ thuộc vào chữ ký phương thức

Trong Spring Core Container, một phương thức gắn `@Bean` là **factory method** để đăng ký một object do Spring quản lý. Khi object mà phương thức tạo ra cần một bean khác, bạn có thể khai báo dependency trực tiếp bằng **tham số phương thức** thay vì tự tìm bean từ `ApplicationContext` hoặc gọi một phương thức `@Bean` khác.

Ví dụ đơn giản:

```java
@Configuration(proxyBeanMethods = false)
class AppConfig {

    @Bean
    Repository repository() {
        return new InMemoryRepository();
    }

    @Bean
    OrderService orderService(Repository repository) {
        return new OrderService(repository);
    }
}
```

Đây là đoạn **minh họa** (cần tự khai báo `Repository`, `InMemoryRepository`, `OrderService` và các import). Khi tạo bean `orderService`, Spring phân giải tham số `Repository repository` từ container rồi truyền instance vào factory method. Người viết cấu hình không phải gọi `repository()` hoặc `context.getBean(...)`.

Chữ ký `orderService(Repository repository)` nói rõ ba điều:

1. Muốn tạo `OrderService`, cần một dependency kiểu `Repository`.
2. Dependency được **Spring resolve** theo kiểu và những quy tắc autowire liên quan.
3. Factory method nhận dependency đã resolve, sau đó thực hiện mã Java thông thường: `new OrderService(repository)`.

Điều này giúp tách **khai báo quan hệ phụ thuộc** khỏi **logic xây object**, thuận lợi cho kiểm thử, refactor và dùng `@Configuration(proxyBeanMethods = false)`.

Mục tiêu học tập của bài:

- Hiểu thời điểm Spring phân giải tham số `@Bean` và khác biệt với tham số của method Java thông thường.
- Sử dụng dependency bắt buộc, `@Qualifier`, `@Primary`, `Optional<T>`, `ObjectProvider<T>` và collection injection đúng ngữ nghĩa.
- Phân biệt tham số `@Bean` với gọi trực tiếp method `@Bean` trong full/lite configuration.
- Xử lý thiếu bean, nhiều ứng viên, dependency cycle, lifecycle/scope, việc khởi tạo sớm.
- Biên dịch và chạy một ví dụ Java 17+ với Spring Framework 6, Gradle và stdout kiểm chứng.

## 2. Spring xử lý tham số `@Bean` như thế nào?

Để bean được tạo từ một phương thức `@Bean`, Spring đăng ký một **bean definition** có thông tin factory method. Khi container cần tạo bean đó, container chọn lời gọi factory thích hợp, xác định từng tham số và phân giải dependency từ BeanFactory.

```text
@Configuration / @Bean được xử lý
             |
             v
  Đăng ký bean definition
     cho factory method
             |
             v
   Khi cần tạo target bean
             |
             v
  Duyệt tham số của @Bean
   - Kiểu dữ liệu / generic
   - Qualifier / annotations
   - Optional / provider / tập hợp
             |
             v
    BeanFactory tìm ứng viên
       /          |          \
     Không có   Một bean    Nhiều bean
       |          |           |
 required?       chọn      Primary/Qualifier/
       |          |         quy tắc resolution
       v          v           v
   Lỗi hoặc   Gọi factory method với dependency đã resolve
   giá trị      |
   hợp lệ       v
             Object được tạo
                |
                v
        Spring quản lý lifecycle
```

Ví dụ `@Bean OrderService orderService(Repository repository)`:

- `Repository` là **dependency bắt buộc** nếu không được diễn đạt là tùy chọn.
- Spring tìm bean phù hợp kiểu `Repository`; nếu chỉ một ứng viên hợp lệ, factory method được gọi.
- Nếu không có bean và không có chính sách optional phù hợp, context thường báo `UnsatisfiedDependencyException` với nguyên nhân liên quan `NoSuchBeanDefinitionException`.
- Nếu có nhiều bean cùng kiểu không thể phân giải còn một ứng viên, thường gặp `NoUniqueBeanDefinitionException` trong chuỗi exception.
- Nếu factory method tự ném lỗi khi chạy, đó là **lỗi thực thi factory**; đừng nhầm với lỗi Spring không tìm được dependency.

**Không cần đặt `@Autowired` lên phương thức `@Bean` chỉ để tham số được inject.** Việc phân giải tham số là một phần của cơ chế tạo bean từ factory method. Trên một constructor Java thông thường, Spring cũng có constructor injection; tuy nhiên tham số `@Bean` thuộc **factory method được container gọi**, không phải constructor của class mà object được tạo.

### 2.1. Bean definition và việc gọi phương thức là hai giai đoạn

Đọc metadata `@Bean` không có nghĩa factory method đã chạy ngay tại thời điểm quét cấu hình. Mặc định, nhiều singleton không lazy được pre-instantiate khi `ApplicationContext` refresh; nếu target bean được khai báo `@Lazy` hoặc dùng scope khác, thời điểm gọi factory có thể khác.

Trong mọi trường hợp, Spring phải resolve tham số **trước khi factory method có thể chạy**. Một lỗi dependency có thể ngăn cả method body thực thi.

## 3. Dependency bắt buộc: truyền theo type

Với:

```java
@Bean
TaxCalculator taxCalculator() {
    return new TaxCalculator(10);
}

@Bean
CheckoutService checkoutService(TaxCalculator calculator) {
    return new CheckoutService(calculator);
}
```

Spring thấy `CheckoutService` được tạo từ `checkoutService(...)` có tham số kiểu `TaxCalculator`, nên phân giải bean phù hợp. Chữ ký diễn đạt quan hệ phụ thuộc. Không cần viết:

```java
// Không khuyến nghị làm mặc định:
@Bean
CheckoutService checkoutService() {
    return new CheckoutService(taxCalculator());
}
```

Hai đoạn đều là **mã minh họa riêng**, dùng class `TaxCalculator` và `CheckoutService` theo logic ứng dụng. Điểm khác nhau quan trọng:

- Với **tham số `@Bean`**, Spring phân giải dependency qua container.
- Với **lời gọi Java `taxCalculator()`**, hành vi phụ thuộc cấu hình class có được proxy hay không; trong chế độ `proxyBeanMethods = false`, đây chỉ là lời gọi Java thông thường và có thể tạo một instance ngoài cơ chế lookup singleton mong đợi.
- Chữ ký có tham số hoạt động tự nhiên ở cả full và lite configuration, không cần dựa vào interception của method call.

Một bản cấu hình sạch thường ưu tiên:

```java
@Configuration(proxyBeanMethods = false)
class CleanConfig {

    @Bean
    TaxCalculator taxCalculator() {
        return new TaxCalculator(10);
    }

    @Bean
    CheckoutService checkoutService(TaxCalculator calculator) {
        return new CheckoutService(calculator);
    }
}
```

Đây là trích đoạn **minh họa**, không phải file Java biên dịch độc lập khi chưa khai báo các kiểu.

### 3.1. Thứ tự khai báo method không phải thứ tự dependency

`@Bean CheckoutService checkoutService(TaxCalculator calculator)` có thể xuất hiện **trước** `@Bean TaxCalculator taxCalculator()` trong file. Spring xây dependency graph dựa trên bean definitions và method parameters. Việc thay đổi vị trí hai method không phải cách thiết kế thứ tự khởi tạo.

Nếu A phụ thuộc B, B cần được chuẩn bị để tạo A. Đó là quan hệ dependency. `@Order` dùng cho ordering trong các collection hoặc extension points nhất định, **không phải công cụ thay constructor/factory dependency** để bảo đảm thứ tự khởi tạo singleton.

## 4. Khi cùng kiểu có nhiều bean: `@Qualifier` và `@Primary`

Giả sử có hai implementation cho `FeePolicy`:

```java
@Bean
@Qualifier("standard")
FeePolicy standardFee() {
    return new FixedFeePolicy("standard", 5);
}

@Bean
@Qualifier("express")
FeePolicy expressFee() {
    return new FixedFeePolicy("express", 15);
}
```

Cả hai method trả về cùng interface `FeePolicy`. Một method:

```java
@Bean
CheckoutService checkoutService(FeePolicy policy) {
    return new CheckoutService(policy);
}
```

có thể gặp lỗi ambiguous dependency nếu Spring không tìm được một ứng viên thắng. Cần xác định **đúng vai trò** của dependency:

```java
@Bean
CheckoutService checkoutService(
        @Qualifier("standard") FeePolicy policy) {
    return new CheckoutService(policy);
}
```

Các đoạn này **chỉ minh họa**: kiểu `FeePolicy` và `FixedFeePolicy` được định nghĩa trong ví dụ hoàn chỉnh ở mục 8. `@Qualifier` ở vị trí tham số là điều kiện lọc: Spring tìm các candidate vừa khớp kiểu, vừa khớp qualifier. Qualifier có thể gắn trên bean factory method và trên tham số cần tiêm; một qualifier không tự tạo được bean sai kiểu.

**Điểm cần nhớ:** tên method `standardFee` và nhãn qualifier `standard` khác nhau; không nên coi hai khái niệm đó là một. Nếu đã có bean name phù hợp, Spring có thể dùng bean name làm fallback qualifier; nhưng dùng annotation `@Qualifier("standard")` ở cả nơi khai báo bean và nơi dùng sẽ thể hiện vai trò nghiệp vụ rõ hơn.

### 4.1. `@Primary` là chính sách mặc định

Có thể gắn:

```java
@Bean
@Primary
FeePolicy standardFee() {
    return new FixedFeePolicy("standard", 5);
}
```

Khi caller tiêm một `FeePolicy` không qualifier và còn nhiều candidate cùng kiểu, `@Primary` ưu tiên bean này nếu nó là primary duy nhất trong tập ứng viên. Với `@Qualifier("express") FeePolicy policy`, Spring vẫn có thể chọn bean express nếu chỉ express khớp qualifier; primary của bean standard không cho phép nó vượt qua qualifier không khớp.

Đánh dấu **hai primary cùng được xét** không tự giải quyết ambiguity. Trên method `@Bean` có một tham số yêu cầu đơn, hãy dùng qualifier khi trách nhiệm rõ, primary cho default thực sự hợp lý.

### 4.2. `@Bean` return type ảnh hưởng khả năng phát hiện ứng viên

Spring dùng thông tin kiểu của bean definition, bao gồm kiểu trả về được khai báo ở method `@Bean`, để phân giải autowiring. Vì vậy khai báo kiểu trả về **đủ cụ thể** và đúng contract:

```java
@Bean
PaymentClient paymentClient() {
    return new DefaultPaymentClient();
}
```

Nếu factory method trả kiểu quá tổng quát như `Object`, một điểm tiêm yêu cầu `PaymentClient` có thể không được Spring nhận diện đầy đủ từ metadata type trước khi target bean được instantiate. Trong nhiều tình huống nên khai báo interface/abstract type có ích cho consumer, hoặc concrete class nếu caller thật sự cần API đó. Đừng dựa vào type thực tế của object được trả về để thay thế hoàn toàn bean definition type metadata.

Đây là đoạn minh họa, cần tự định nghĩa `PaymentClient` và `DefaultPaymentClient`.

## 5. Các tham số không bắt buộc: `Optional` và `ObjectProvider`

Không phải mọi dependency đều cần hiện diện. Một dịch vụ thanh toán có thể gửi audit nếu có module audit, và vẫn hoạt động nếu audit bị tắt.

### 5.1. `Optional<T>`: quyết định tại lúc tạo bean

```java
@Bean
ReportService reportService(Optional<AuditSink> auditSink) {
    return new ReportService(auditSink);
}
```

Với `java.util.Optional`, Spring có thể inject `Optional.empty()` khi không có ứng viên. Nếu có đúng một `AuditSink` được resolve, giá trị là `Optional.of(bean)`. Nếu nhiều bean `AuditSink` không phân giải được, optionality không nên được hiểu thành quy tắc âm thầm chọn một bean ngẫu nhiên; vẫn có thể lỗi ambiguity.

`Optional<T>` phù hợp khi factory method muốn quyết định một lần liệu dependency có sẵn khi tạo bean hay không. Ví dụ `ReportService` có thể giữ `Optional<AuditSink>` như trạng thái cấu hình tại thời điểm xây service.

**Lưu ý:** Trong một singleton, việc inject `Optional<T>` không tự làm service “quan sát” thay đổi bean registry về sau.

### 5.2. `ObjectProvider<T>`: resolve khi cần

```java
@Bean
ReportService reportService(ObjectProvider<AuditSink> auditProvider) {
    return new ReportService(auditProvider);
}
```

Spring có thể inject provider mà chưa cần tìm một `AuditSink` cụ thể ngay tại factory method của `ReportService`. Code nghiệp vụ sau đó chọn cách xử lý:

```java
AuditSink required = auditProvider.getObject();
AuditSink optional = auditProvider.getIfAvailable();
AuditSink unique = auditProvider.getIfUnique();
```

Đây là đoạn minh họa dùng biến `auditProvider` đã được cung cấp; **không độc lập** nếu thiếu class `AuditSink` và nơi khai báo biến.

| Phương thức | Không có bean | Có một ứng viên thắng | Nhiều ứng viên không phân giải được |
| --- | --- | --- | --- |
| `getObject()` | Ném `NoSuchBeanDefinitionException` | Trả bean | Ném `NoUniqueBeanDefinitionException` |
| `getIfAvailable()` | `null` | Trả bean | Ném `NoUniqueBeanDefinitionException` |
| `getIfUnique()` | `null` | Trả bean | `null` |

Nếu có nhiều bean nhưng một bean `@Primary` phù hợp được Spring chọn làm ứng viên thắng, cả ba method có thể trả bean đó. Nếu nghiệp vụ cần lazy lookup hoặc xử lý optional dependency tại thời điểm sử dụng, provider giúp diễn đạt điều đó.

**Không đánh đồng provider với lazy singleton:** non-lazy singleton `AuditSink` khác có thể đã được Spring tạo trong lúc context refresh. Provider chỉ làm thời điểm **lookup từ consumer** linh hoạt; muốn chủ động trì hoãn khởi tạo bean cần xét thêm `@Lazy` và dependency graph.

### 5.3. Dùng `@Nullable` và null có chủ đích

Spring hỗ trợ các cách biểu diễn optional dependency khác tùy annotation nullability và phiên bản. Trong Spring Framework 6.2, `@Nullable` được hỗ trợ ở injection points theo cơ chế phù hợp. Khi viết Java 17, `Optional<T>` hoặc `ObjectProvider<T>` thường diễn đạt ý định rõ hơn một tham số có thể `null` mà method body quên kiểm tra.

Không tự đánh dấu mọi dependency `@Nullable` chỉ để context startup thành công: với dependency bắt buộc, lỗi thiếu bean là một tín hiệu cấu hình quan trọng.

## 6. Tham số collection: một factory method cần cả nhóm bean

Một method có thể nhận nhiều bean cùng kiểu:

```java
@Bean
Pipeline pipeline(List<Handler> handlers) {
    return new Pipeline(handlers);
}
```

Spring tập hợp các beans phù hợp với `Handler` vào một `List<Handler>`; nếu có order metadata, thứ tự list thường được xác định bởi `Ordered`, `@Order` hoặc `@Priority` phù hợp. Method body không cần tự gọi `getBeansOfType` hoặc lặp tên bean.

Cũng có thể dùng:

- `Handler[]`: mảng các bean phù hợp;
- `Set<Handler>`: nhóm bean với semantics set, không nên dựa vào iteration order như một thứ tự pipeline bắt buộc;
- `Map<String, Handler>`: map có **bean name** làm key, bean làm value;
- `@Qualifier("fraud") List<Handler>`: tập các bean kiểu Handler phù hợp qualifier `fraud`.

**`@Primary` không lọc số phần tử của collection**; primary chỉ hỗ trợ lựa chọn một bean khi dependency đơn cần phân giải. Khi một factory method nhận `List<Handler>`, nó nói rằng bean mới cần **cả nhóm handler** chứ không phải một default handler.

### 6.1. Khi collection không có thành viên

Đừng giả định mọi factory method nhận `List<T>` sẽ tự nhận một `List.of()` khi không có bean. Tại một dependency injection point bắt buộc, Spring có thể coi việc không tìm được bean phù hợp là lỗi. Nếu “không có handler” là một trường hợp nghiệp vụ bình thường, hãy thiết kế tùy chọn rõ ràng (chẳng hạn sử dụng `ObjectProvider<Handler>` và `orderedStream()`, rồi tự tạo danh sách) và kiểm thử hành vi của phiên bản Spring đang dùng.

### 6.2. Phân biệt multi-bean collection và collection bean có sẵn

`@Bean Pipeline pipeline(List<Handler> handlers)` trong ví dụ điển hình yêu cầu Spring **thu thập các bean Handler**. Trong trường hợp ứng dụng còn tự khai báo một bean mà bản thân nó có kiểu `List<Handler>`, cơ chế lựa chọn collection bean có thể khác: bạn cần xác định rõ muốn tiêm **một bean kiểu List** hay muốn **nhiều phần tử Handler**. Hãy thiết kế tên, qualifier và generic type đủ rõ, và kiểm thử context thực khi cả hai cách cấu hình cùng tồn tại.

## 7. Tham số factory method so với gọi `@Bean` method trực tiếp

Đây là một trong những khác biệt quan trọng nhất của Java-based configuration.

### 7.1. Full `@Configuration` và `proxyBeanMethods=true`

Với cấu hình thông thường:

```java
@Configuration
class FullConfig {

    @Bean
    Engine engine() {
        return new Engine();
    }

    @Bean
    Car car() {
        return new Car(engine());
    }
}
```

Đây là **đoạn minh họa** cần class `Engine` và `Car`. `@Configuration` mặc định `proxyBeanMethods=true` cho phép Spring enhance configuration class (thường bằng CGLIB) để **chặn các lời gọi qua lại giữa `@Bean` methods**, bảo đảm theo container semantics, ví dụ trả singleton đã đăng ký thay vì `new Engine()` tùy tiện khi gọi qua proxy.

Cơ chế này có ràng buộc đối với việc enhance class và method, và làm mã cấu hình phụ thuộc vào proxy semantics. Vì vậy, ngay cả với full `@Configuration`, truyền dependency qua tham số thường dễ hiểu hơn.

### 7.2. `proxyBeanMethods=false` và lite configuration

Với:

```java
@Configuration(proxyBeanMethods = false)
class LiteConfig {

    @Bean
    Engine engine() {
        return new Engine();
    }

    @Bean
    Car car() {
        return new Car(engine());
    }
}
```

Lời gọi `engine()` trong `car()` là **lời gọi Java thông thường**, có thể tạo một `Engine` mới ngoài instance singleton mà BeanFactory quản lý. `@Bean` method vẫn được Spring xử lý để đăng ký bean, nhưng các lời gọi trực tiếp qua method không được proxy intercept.

Cách viết rõ nghĩa:

```java
@Configuration(proxyBeanMethods = false)
class ParameterConfig {

    @Bean
    Engine engine() {
        return new Engine();
    }

    @Bean
    Car car(Engine engine) {
        return new Car(engine);
    }
}
```

Đây là ba mẫu minh họa **tách biệt**, không ghép cùng một file/class mà không định nghĩa `Engine`/`Car`. Với `ParameterConfig`, dependency của `car` được lấy từ container; không cần engine method tự gọi lại.

### 7.3. Có được gọi method `@Bean` trực tiếp trong Java?

Bạn *có thể* gọi như một method Java thông thường, nhưng hành vi khi ấy phụ thuộc cách class cấu hình được tạo và proxy mode. Đặc biệt, gọi method trên một instance cấu hình tự `new` ngoài Spring không giúp Spring inject tham số và không biến object trả về thành managed bean. Vì vậy đừng coi `@Bean` là một “magic factory” hoạt động theo container semantics trong mọi lời gọi Java.

**Quy tắc thực hành:** khi bean A cần bean B, viết `@Bean A a(B b)`. Đừng dùng `@Bean A a() { return new A(b()); }` như mặc định nếu đã có khả năng truyền B qua tham số.

## 8. Ví dụ đầy đủ Java 17+ chạy được với Spring Context 6

Dự án sau thể hiện năm tính chất:

1. Tham số bắt buộc được resolve từ bean `PriceCalculator`.
2. `@Qualifier("standard")` chọn đúng một `FeePolicy` khi có hai bean cùng kiểu.
3. `ObjectProvider<AuditSink>` biểu diễn khả năng audit tùy chọn.
4. `Optional<AuditSink>` trả giá trị vắng mặt hợp lệ.
5. `List<FeePolicy>` nhận hai policies theo thứ tự `@Order` ở factory methods.

Ví dụ không cần Spring Boot, HTTP, database hoặc cấu hình ngoài. `@Configuration(proxyBeanMethods=false)` được chọn có chủ đích để chứng minh **tham số method là đủ để diễn đạt dependency**.

### 8.1. Cấu trúc dự án

```text
bean-method-parameters-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/
    └── BeanMethodParametersDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'bean-method-parameters-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'BeanMethodParametersDemo'
}
```

Dùng JDK 17+ và Gradle tương thích với JDK đang chạy. `spring-context` đem theo các module Spring cần cho `AnnotationConfigApplicationContext`, `@Bean`, `@Qualifier`, `ObjectProvider` và collection autowiring.

### 8.2. Mã nguồn hoàn chỉnh

File `src/main/java/BeanMethodParametersDemo.java`:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

public class BeanMethodParametersDemo {

    record FeePolicy(String name, int surcharge) {
    }

    record PriceCalculator(int taxPercent) {
        int total(int amount, FeePolicy fee) {
            return amount + amount * taxPercent / 100 + fee.surcharge();
        }
    }

    interface AuditSink {
        void record(int total);
    }

    record CheckoutService(
            PriceCalculator calculator,
            FeePolicy selected,
            ObjectProvider<AuditSink> auditProvider) {

        int quote(int amount) {
            int total = calculator.total(amount, selected);
            auditProvider.ifAvailable(sink -> sink.record(total));
            return total;
        }
    }

    record FeeCatalog(
            List<FeePolicy> all,
            Optional<AuditSink> audit) {

        List<String> names() {
            return all.stream().map(FeePolicy::name).toList();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {

        @Bean
        PriceCalculator priceCalculator() {
            return new PriceCalculator(10);
        }

        @Bean
        @Order(10)
        @Qualifier("standard")
        FeePolicy standardFee() {
            return new FeePolicy("standard", 5);
        }

        @Bean
        @Order(20)
        @Qualifier("express")
        FeePolicy expressFee() {
            return new FeePolicy("express", 15);
        }

        @Bean
        CheckoutService checkoutService(
                PriceCalculator calculator,
                @Qualifier("standard") FeePolicy selected,
                ObjectProvider<AuditSink> auditProvider) {
            return new CheckoutService(calculator, selected, auditProvider);
        }

        @Bean
        FeeCatalog feeCatalog(
                List<FeePolicy> allFees,
                Optional<AuditSink> audit) {
            return new FeeCatalog(List.copyOf(allFees), audit);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            var catalog = context.getBean(FeeCatalog.class);
            var checkout = context.getBean(CheckoutService.class);

            System.out.println("policies = " + catalog.names());
            System.out.println("selected = " + checkout.selected().name());
            System.out.println("quote100 = " + checkout.quote(100));
            System.out.println("optionalAudit = " +
                    catalog.audit().isPresent());
            System.out.println("providerAudit = " +
                    (checkout.auditProvider().getIfAvailable() != null));
            System.out.println("sameCheckout = " +
                    (checkout == context.getBean(CheckoutService.class)));
        }
    }
}
```

### 8.3. Lệnh chạy

Trong thư mục `bean-method-parameters-demo`:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper:

```bash
./gradlew run --quiet
```

Trên Windows PowerShell, thay bằng `.\gradlew.bat run --quiet`.

Stdout do những lệnh `System.out.println` trong code tạo ra:

```text
policies = [standard, express]
selected = standard
quote100 = 115
optionalAudit = false
providerAudit = false
sameCheckout = true
```

Các thông báo của Gradle hoặc logging từ môi trường (nếu có cấu hình thêm) không thuộc stdout nghiệp vụ trên.

### 8.4. Phân tích từng kết quả

**`policies = [standard, express]`**: `feeCatalog(List<FeePolicy> allFees, ...)` nhận cả hai bean `FeePolicy`; hai method factory có `@Order(10)` và `@Order(20)` nên danh sách có thứ tự tương ứng. Hai bean được tạo độc lập nhưng cùng interface/type `FeePolicy`.

**`selected = standard`**: tham số `@Qualifier("standard") FeePolicy selected` của method `checkoutService(...)` lọc đúng policy mang nhãn `standard`. Nếu bỏ qualifier mà vẫn có hai candidates ngang nhau, method có thể thất bại khi Spring cố phân giải một `FeePolicy`.

**`quote100 = 115`**: `PriceCalculator(10)` tính thuế 10% của 100 là 10; fee chuẩn là 5; tổng `100 + 10 + 5 = 115`. `auditProvider.ifAvailable(...)` không thực thi consumer vì context không khai báo bean `AuditSink`.

**`optionalAudit = false`**: `feeCatalog(...)` nhận `Optional.empty()`; việc thiếu `AuditSink` là một phần hợp lệ của thiết kế.

**`providerAudit = false`**: provider được inject thành công, nhưng `getIfAvailable()` tại lúc gọi cho `null` do chưa có AuditSink bean.

**`sameCheckout = true`**: `CheckoutService` do `@Bean` tạo với singleton scope mặc định; hai lần `getBean(...)` nhận cùng instance trong một context.

**Bằng chứng cốt lõi:** `checkoutService(...)` không hề gọi `priceCalculator()` hoặc `standardFee()`, và `feeCatalog(...)` không tự truy vấn bean registry. Spring resolve các tham số như một phần của quá trình gọi factory.

### 8.5. Thử thay đổi và quan sát

**Thử 1 — Thêm audit bean.** Bổ sung trong `Config`:

```java
@Bean
AuditSink auditSink() {
    return total -> System.out.println("audit = " + total);
}
```

Đây là **đoạn thêm vào ví dụ mục 8**, không phải file độc lập. Lúc này `Optional<AuditSink>` có giá trị và provider cũng phân giải được AuditSink; `checkout.quote(100)` sẽ in thêm `audit = 115` từ consumer trước dòng `quote100 = 115` của main.

**Thử 2 — Gỡ `@Qualifier("standard")` ở tham số đơn.** Spring có hai bean `FeePolicy` nhưng không có primary. Khi refresh context, Spring có thể không chọn được một ứng viên thắng và báo ambiguity. Đừng dựa vào việc tham số có tên `selected` để hy vọng chọn một trong hai.

**Thử 3 — Gắn `@Primary` lên `standardFee()`.** Với tham số đơn `FeePolicy selected` không qualifier, Spring có thể chọn standard làm default nếu là primary duy nhất. Nhưng `List<FeePolicy>` của `FeeCatalog` **vẫn chứa cả standard và express**.

**Thử 4 — Thay `@Order`.** Đổi `@Order(10)` của standard thành `@Order(30)`. Với order express là 20, list ở `FeeCatalog` đổi thành `[express, standard]`; qualifier chọn standard cho `CheckoutService` vẫn giữ nguyên. Điều này cho thấy **lọc bean** và **sắp xếp collection** là hai quyết định khác nhau.

## 9. Chu kỳ phụ thuộc và lỗi khởi tạo

Tham số factory method diễn đạt dependency graph. Nếu có vòng A → B → A, Spring không thể tự tạo hai singleton dạng constructor/factory dependencies theo cách tuyến tính bình thường.

Ví dụ cố ý sai:

```java
@Configuration(proxyBeanMethods = false)
class CyclicConfig {

    @Bean
    A a(B b) {
        return new A(b);
    }

    @Bean
    B b(A a) {
        return new B(a);
    }
}
```

Đây là **trích đoạn mô tả lỗi**, cần class `A` và `B`. Khi container cố tạo A, nó cần B; tạo B lại cần A. Với kiểu dependency cứng này, Spring thường báo circular reference / bean currently in creation, có thể được bọc trong `UnsatisfiedDependencyException` hoặc `BeanCreationException` tùy đường đi.

**Giải pháp ưu tiên là sửa thiết kế:** tách trách nhiệm, đảo chiều phụ thuộc hoặc trích xuất interface/event/collaborator không tạo vòng. `ObjectProvider<T>` hoặc `@Lazy` có thể trì hoãn một liên kết trong một số trường hợp, nhưng không bảo đảm vòng logic được giải quyết an toàn; nếu method gọi nhau vô hạn lúc runtime, trì hoãn injection cũng không chữa được.

### 9.1. Thiếu bean do chưa đăng ký configuration

Đặt `@Bean` trong một class chưa được Spring đăng ký/import/scan thì bean definition không tự xuất hiện. Khi method A yêu cầu tham số B, Spring chỉ có thể resolve B từ **container hiện tại** (bao gồm nguồn đăng ký mà context nhìn thấy), không phải từ mọi class Java trong project.

Nếu thiếu dependency, kiểm tra:

- Class configuration đã được đưa vào `AnnotationConfigApplicationContext`, `@Import` hoặc scan chưa?
- Method `@Bean` có được Spring xử lý không, hay chỉ là Java method không thuộc container?
- Có `@Profile`, `@Conditional` hoặc filter loại bean không?
- Kiểu khai báo `@Bean` có khớp kiểu tham số yêu cầu không?
- Có nhiều beans cùng type và thiếu qualifier không?
- Dependency có nằm trên runtime classpath và khả dụng lúc refresh không?

### 9.2. Lỗi trong method body

Spring có thể resolve tất cả tham số thành công nhưng method vẫn ném `IllegalStateException`, gọi API mạng lỗi hoặc trả về object không đáp ứng kỳ vọng. Thông báo lúc đó có thể là `BeanCreationException` liên quan factory method. Để debug, đọc **root cause** và phân biệt “argument resolution failed” với “factory execution failed”.

Không nên bắt exception rộng trong `@Bean` rồi trả `null` để che lỗi: container có những semantics riêng khi factory method trả `null` và caller có thể nhận kết quả rất khác mong đợi. Với bean bắt buộc, nên báo lỗi cấu hình rõ ràng.

## 10. Scope, lazy và thứ tự tạo bean

### 10.1. Singleton không có nghĩa một lần gọi Java bất kỳ

`@Bean` mặc định tạo singleton do container quản lý. Nếu method A có tham số B, container truyền instance B phù hợp. Không đồng nghĩa mỗi lời gọi tự phát đến `config.b()` trong mọi proxy mode đều trả singleton; đó là lý do parameter injection là lối viết đáng tin cậy.

### 10.2. Prototype được resolve tại thời điểm tạo consumer

Nếu bean B có `@Scope("prototype")` và singleton A nhận B như **tham số factory method**, Spring sẽ tạo một prototype instance khi tạo A; A thường giữ chính reference đó về sau, không tự nhận prototype mới ở mỗi business method call.

Muốn mỗi lần sử dụng lấy prototype mới, nhận `ObjectProvider<B>` làm dependency và gọi `getObject()` mỗi lần cần, với scope/contract phù hợp. Đây là chính sách lifecycle, không phải chỉ là cú pháp đặt tham số.

### 10.3. `@Lazy` không thay thế dependency graph

Gắn `@Lazy` lên bean definition có thể hoãn khởi tạo cho đến khi cần. Tuy nhiên, nếu một singleton khác đang được khởi tạo bắt buộc nhận bean lazy **làm tham số `@Bean`**, việc resolve dependency vẫn có thể kích hoạt tạo bean lazy ngay. Để trì hoãn lookup từ consumer, `ObjectProvider<T>` hoặc proxy phù hợp cần được xem xét riêng.

### 10.4. `@DependsOn` dùng cho phụ thuộc thứ tự không biểu diễn qua tham số

Nếu A cần B để xây object, hãy viết `@Bean A a(B b)`. Nếu A không cần reference B nhưng muốn B được khởi tạo trước để chuẩn bị side effect có chủ đích, `@DependsOn("b")` có thể biểu đạt yêu cầu thứ tự này.

```java
@Bean
@DependsOn("migrationRunner")
ReportCache reportCache() {
    return new ReportCache();
}
```

Đây là đoạn minh họa cần bean tên `migrationRunner`, class `ReportCache` và imports. `@DependsOn` dựa vào **bean name**, không phải type; không thay thế constructor/factory parameter injection cho dependency object thực sự.

## 11. So sánh với các cách khác để biểu diễn dependency

| Cách | Dependency được khai báo ở đâu? | Khi nên chọn |
| --- | --- | --- |
| Constructor injection trên `@Component`/`@Service` | Constructor của class | Class thuộc codebase và có thể đặt stereotype; dependency bắt buộc thuộc bản thân object |
| Method parameter của `@Bean` | Chữ ký factory method trong Java configuration | Muốn tạo object bằng factory, tích hợp class thư viện hoặc kiểm soát construction |
| Method `@Bean` tự gọi method `@Bean` khác | Method body | Có thể hợp lệ với full config, nhưng dễ phụ thuộc proxy semantics |
| `ApplicationContext.getBean(...)` trực tiếp | Code imperative lookup | Infrastructure code thật sự cần lookup động; tránh service locator trong business code |
| `@DependsOn` | Metadata tên bean | Cần thứ tự khởi tạo cho side effect, không có object parameter trực tiếp |
| `ObjectProvider<T>` được tiêm | Factory method/constructor nhận provider | Target có thể vắng mặt, cần lookup muộn hoặc cần scope động |

Không có một cách bắt buộc cho tất cả ứng dụng. Nhưng khi dùng `@Bean` factory method, **khai báo tham số là cách diễn đạt dependency tự nhiên**: rõ contract, tránh lấy bean theo string name và ít phụ thuộc khả năng CGLIB interception của configuration class.

## 12. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `UnsatisfiedDependencyException` lúc tạo bean từ `@Bean` | Thiếu bean của tham số bắt buộc | Đăng ký/import configuration cung cấp bean; kiểm tra type, profile, condition |
| `NoUniqueBeanDefinitionException` | Nhiều candidate cùng kiểu không có ứng viên thắng | Gắn `@Qualifier` tại tham số, chỉ định `@Primary` phù hợp hoặc thay thiết kế |
| Một bean có `@Primary` nhưng qualifier vẫn chọn bean khác | Qualifier lọc tập candidate trước khi xét ưu tiên | Kiểm tra qualifier ở method khai báo và tham số |
| Method được `@Bean` gọi trực tiếp trả object khác singleton mong đợi | Dùng `proxyBeanMethods=false` hoặc gọi class config ngoài Spring | Dùng tham số `@Bean` thay vì direct call |
| Gắn `@Autowired` cho `@Bean` vì tưởng bắt buộc | Hiểu sai factory method argument resolution | Bỏ annotation dư; Spring resolve tham số `@Bean` tự động |
| Bean ở context không thấy method khác | Configuration chưa được xử lý, nằm ngoài scan/import | Đăng ký configuration vào đúng context |
| Bật `@Lazy` nhưng bean vẫn tạo sớm | Bean khác cần dependency bắt buộc khi khởi tạo | Dùng provider/proxy thích hợp hoặc điều chỉnh dependency graph |
| Prototype không được tạo mới cho mỗi method business call | Prototype chỉ resolve một lần khi singleton được tạo | Inject `ObjectProvider<Prototype>` và lookup khi cần |
| Dùng `@Order` để “bắt bean B init trước A” | `@Order` không biểu đạt dependency khởi tạo singleton | Khai báo `@Bean A a(B b)` hoặc `@DependsOn` cho side effect |
| `@Bean` method nhận `List<T>` nhưng không có phần tử | Dependency bắt buộc không được thỏa | Dùng `ObjectProvider<T>`/stream khi hợp đồng cho phép rỗng |
| Dùng `Optional<T>` và vẫn thấy ambiguity | Optional cho phép thiếu, không chọn ngẫu nhiên từ nhiều bean | Qualifier, primary hoặc xử lý chính sách nhiều ứng viên |
| `ObjectProvider<T>` có mặt nhưng `getObject()` lỗi | Provider chỉ trì hoãn việc phân giải target | Chọn `getIfAvailable()`/`getIfUnique()` nếu chính sách cho phép; sửa cấu hình nếu bắt buộc |
| Cấu hình hai bean tạo vòng dependency | Factory parameter A→B→A | Refactor dependency graph; không dùng proxy để che lỗi logic |
| Factory parameter không resolve theo concrete class | Bean type metadata quá tổng quát (`Object`) hoặc generic không khớp | Dùng return type hợp đồng rõ, kiểm tra `ResolvableType` khi cần |
| Viết `@Bean` rồi gọi method trên `new Config()` | Gọi Java object ngoài Spring | Lấy managed bean từ `ApplicationContext`/inject dependency vào bean cần dùng |

**Kỹ thuật debug hữu ích:** tập trung vào method `@Bean` nào đang được Spring gọi, tham số nào bị lỗi và các bean names/candidate types có trong context. Việc xem riêng method body chưa đủ nếu Spring không thể resolve argument.

## 13. Bài tập thực hành và đáp án

### Bài 1 — Loại bỏ gọi trực tiếp method `@Bean`

Cho:

```java
@Configuration(proxyBeanMethods = false)
class OldConfig {
    @Bean
    ReportRepository repository() {
        return new ReportRepository();
    }

    @Bean
    ReportService service() {
        return new ReportService(repository());
    }
}
```

Viết lại để `ReportService` dùng repository do Spring quản lý.

**Đáp án:**

```java
@Bean
ReportService service(ReportRepository repository) {
    return new ReportService(repository);
}
```

Đây là hai **trích đoạn minh họa**, dùng class tự định nghĩa. Spring resolve repository theo type trong lúc tạo service; method không cần gọi `repository()` trực tiếp.

### Bài 2 — Hai candidate cùng interface

Trong cấu hình có `@Bean @Qualifier("email") Notifier email()` và `@Bean @Qualifier("sms") Notifier sms()`. Bạn muốn method `@Bean AlertManager manager(...)` lấy SMS.

**Đáp án:** khai báo `@Bean AlertManager manager(@Qualifier("sms") Notifier notifier)`, sau đó gọi constructor với `notifier`. Không dựa vào thứ tự method hoặc tự tạo `new SmsNotifier()`.

### Bài 3 — Mở rộng demo với audit

Thêm `@Bean AuditSink auditSink()` như ở mục 8.5. Dự đoán:

- `catalog.audit().isPresent()` trở thành `true`;
- `checkout.auditProvider().getIfAvailable() != null` thành `true`;
- lời gọi `checkout.quote(100)` kích hoạt consumer audit với tổng 115.

Việc truyền `Optional` và provider ở factory method **không cần đổi**.

### Bài 4 — Đổi vị trí hai factory methods

Đưa `checkoutService(...)` lên đầu class `Config` trước `priceCalculator()`. Có làm Spring mất bean calculator không?

**Đáp án:** Không, miễn cả hai `@Bean` được xử lý và dependency graph không có lỗi. Spring resolve theo bean definitions, không theo thứ tự text trong file.

### Bài 5 — Default policy và collection

Gắn `@Primary` vào bean standard nhưng giữ express. Nếu tạo:

```java
@Bean
FeeCatalog feeCatalog(List<FeePolicy> policies) {
    return new FeeCatalog(policies, Optional.empty());
}
```

Đây là **biến thể minh họa** của demo (nếu thay method `feeCatalog`). Danh sách có bao nhiêu phần tử?

**Đáp án:** Cả hai FeePolicy; primary không lọc collection. Có thể sắp thứ tự bằng `@Order` như cũ.

### Bài 6 — Singleton cần prototype

`@Bean A a(B prototypeB)` inject một instance B vào singleton A. Nếu B có scope prototype, mỗi lần gọi `a.run()` có tự nhận B mới không?

**Đáp án:** Không. A giữ B đã được resolve khi A được tạo. Muốn B mới theo mỗi lần sử dụng, thiết kế A nhận `ObjectProvider<B>` rồi lookup.

### Bài 7 — Vòng A/B

Hai factory methods `A a(B b)` và `B b(A a)` đều tạo singleton và không có cơ chế trì hoãn nào. Điều gì xảy ra?

**Đáp án:** Container không thể hoàn thành cả hai dependency cứng; thường thất bại với circular creation/unsatisfied dependency. Cần refactor graph hoặc thay quan hệ đồng bộ bằng thiết kế phù hợp.

### Bài 8 — Phân biệt missing dependency và factory error

Method:

```java
@Bean
ReportService reportService(Repository repository) {
    throw new IllegalStateException("broken factory");
}
```

Nếu Spring có repository hợp lệ, lỗi khởi tạo xảy ra ở đâu?

**Đáp án:** Spring có thể resolve tham số thành công, rồi method body ném `IllegalStateException`. Đây là lỗi factory execution, không phải thiếu bean `Repository`.

### Bài 9 — Optional không có nghĩa chọn tùy ý

Có hai bean `AuditSink` ngang nhau nhưng method nhận `Optional<AuditSink>`. Có chắc nhận `Optional.empty()` không?

**Đáp án:** Không. `Optional.empty()` diễn đạt **vắng mặt dependency**, không phải chính sách bỏ qua ambiguity của nhiều candidate. Hãy lọc bằng qualifier hoặc xem xét một chính sách selection phù hợp.

### Bài 10 — Chọn cách mô tả quan hệ phụ thuộc

Một thư viện cung cấp class `HttpClientAdapter` không mang stereotype; ứng dụng tạo class này bằng `@Bean` và nó cần bean `CredentialsProvider`. Nên tự gọi `context.getBean(CredentialsProvider.class)` trong method hay thêm tham số `CredentialsProvider credentials`?

**Đáp án:** Thêm tham số method `@Bean HttpClientAdapter adapter(CredentialsProvider credentials)`. Cách đó rõ dependency và dễ kiểm thử mà không phụ thuộc Service Locator.

## 14. Checklist khi viết phương thức `@Bean`

- Bean cần tạo có phụ thuộc object nào? Đưa **dependency bắt buộc** vào tham số factory method.
- Có nhiều ứng viên cùng type không? Dùng `@Qualifier` khi vai trò cụ thể, `@Primary` khi cần default.
- Có dependency tùy chọn không? Dùng `Optional<T>` hoặc `ObjectProvider<T>` theo thời điểm resolve và chính sách nghiệp vụ.
- Bean cần cả nhóm implementation không? Dùng `List<T>`/mảng hoặc provider stream; đừng gắn primary rồi mong chỉ còn một phần tử.
- Có đang gọi một `@Bean` method khác trực tiếp không? Cân nhắc thay bằng tham số để không phụ thuộc proxy mode.
- Return type của `@Bean` đã đủ rõ để by-type resolution chưa?
- Có cycle A→B→A, hoặc factory method có side effect/IO gây startup failure không?
- Scope và lazy policy có đúng với thời điểm tạo và dùng object không?
- Class configuration có thật sự được container đăng ký/import/scan không?
- Đã kiểm chứng bằng một `ApplicationContext` nhỏ và kiểm tra kết quả injection chưa?

## 15. Ghi nhớ và nguồn đọc

- **Tham số `@Bean` là dependency được Spring resolve** ngay trước lúc container gọi factory method.
- **Không bắt buộc `@Autowired` trên `@Bean` method** để inject tham số.
- **Dependency đơn** được chọn theo type, qualifier, primary và các quy tắc resolution; thiếu hoặc mơ hồ có thể làm tạo bean thất bại.
- **Optional/provider/collection** cho phép biểu diễn nhu cầu khác nhau: vắng mặt hợp lệ, lookup muộn hoặc nhiều beans cùng type.
- **Tham số phương thức** làm việc rõ ràng với `@Configuration(proxyBeanMethods=false)`; gọi trực tiếp method `@Bean` có semantics khác tùy proxy mode.
- **Scope/lifecycle và dependency graph** quyết định khi nào bean được tạo; `@Order` không thay thế constructor/factory dependencies.
- Một factory method có tham số rõ ràng thường dễ đọc hơn việc inject `ApplicationContext` chỉ để tự đi lấy từng dependency.

Tài liệu chính thức:

- [Spring Framework Reference — Using the `@Bean` Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html).
- [Spring Framework Reference — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html).
- [Spring Framework Reference — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html).
- [Spring Framework Reference — Fine-tuning Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html).
- [Spring Framework Reference — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html).
- [Spring Framework Javadoc — `ObjectProvider`](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/ObjectProvider.html).
