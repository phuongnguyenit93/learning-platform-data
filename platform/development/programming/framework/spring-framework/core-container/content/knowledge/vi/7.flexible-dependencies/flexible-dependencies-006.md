# Spring ObjectProvider: phân biệt `getObject()`, `getIfAvailable()` và `getIfUnique()`

## 1. Vấn đề: khi một dependency có thể thiếu hoặc có nhiều bean

Khi một class cần sử dụng một service được quản lý bởi Spring IoC Container, cách thông thường là constructor injection:

```java
// Minh họa: PaymentGateway phải có đúng một bean phù hợp.
PaymentService(PaymentGateway gateway) {
    this.gateway = gateway;
}
```

Cách này lý tưởng với dependency **bắt buộc**: khi thiếu bean hoặc có nhiều ứng viên không phân giải được, lỗi sẽ xuất hiện trong lúc tạo đối tượng. Nhưng một số tính năng là tùy chọn, phụ thuộc vào cấu hình, hoặc cần chọn bean tại thời điểm sử dụng. Khi đó, thay vì yêu cầu ngay `PaymentGateway`, ta có thể tiêm:

```java
// Minh họa: constructor của một bean Spring.
PaymentService(ObjectProvider<PaymentGateway> gatewayProvider) {
    this.gatewayProvider = gatewayProvider;
}
```

`ObjectProvider<T>` thuộc package `org.springframework.beans.factory` và là một biến thể của `ObjectFactory<T>`. Nó cho phép **lấy bean theo yêu cầu** và kiểm soát cách ứng xử khi bean không tồn tại hoặc khi có nhiều bean cùng kiểu. Đối tượng provider gắn với Spring `BeanFactory`; mỗi lần gọi phương thức của provider, việc phân giải target bean có thể được thực hiện lại dựa trên trạng thái của factory.

Ba phương thức trọng tâm:

- `getObject()`: **yêu cầu phải lấy được một bean**; thiếu bean hoặc nhiều bean mơ hồ thì báo lỗi.
- `getIfAvailable()`: **cho phép không có bean** và trả `null` nếu không có; nhưng **không bỏ qua lỗi nhiều bean mơ hồ**.
- `getIfUnique()`: **chỉ trả bean khi có ứng viên thắng duy nhất**; trả `null` khi không có bean hoặc không thể chọn duy nhất.

**Điểm dễ nhầm nhất:** Tên `getIfAvailable` không có nghĩa là “cứ có bean bất kỳ thì trả một bean ngẫu nhiên”; tên `getIfUnique` cũng không có nghĩa “chỉ được có đúng một bean definition trong cả container”. Cả hai vẫn tuân theo cơ chế chọn ứng viên của Spring, trong đó một bean có `@Primary` phù hợp có thể được chọn làm kết quả duy nhất từ nhiều bean cùng kiểu.

## 2. Bảng hành vi cần nhớ

Giả sử `ObjectProvider<PaymentGateway> provider` đang yêu cầu một bean kiểu `PaymentGateway` và không có qualifier nào thu hẹp lựa chọn.

| Trạng thái ứng viên | `getObject()` | `getIfAvailable()` | `getIfUnique()` |
| --- | --- | --- | --- |
| Không có bean phù hợp | Ném `NoSuchBeanDefinitionException` | `null` | `null` |
| Có đúng một bean phù hợp | Trả bean đó | Trả bean đó | Trả bean đó |
| Có hai bean, không chọn được một ứng viên thắng | Ném `NoUniqueBeanDefinitionException` | Ném `NoUniqueBeanDefinitionException` | `null` |
| Có hai bean, đúng một bean `@Primary` | Trả bean primary | Trả bean primary | Trả bean primary |
| Có nhiều bean, nhưng qualifier chỉ giữ một ứng viên | Trả bean phù hợp | Trả bean phù hợp | Trả bean phù hợp |

`NoUniqueBeanDefinitionException` là một dạng `NoSuchBeanDefinitionException` trong hệ phân cấp exception của Spring; khi muốn phân biệt hai trường hợp, hãy `catch (NoUniqueBeanDefinitionException)` **trước** `catch (NoSuchBeanDefinitionException)`.

Bảng này mô tả kết quả khi bản thân việc tạo bean diễn ra bình thường. Nếu factory gọi constructor/factory method và xảy ra lỗi khởi tạo bean, các phương thức provider vẫn có thể ném `BeansException` liên quan. `getIfAvailable()` và `getIfUnique()` **không phải** cơ chế nuốt mọi lỗi bean creation.

### “Unique” nghĩa là kết quả chọn được một ứng viên

Spring sử dụng chính sách lựa chọn của container để phân giải tính duy nhất. Ngoài trường hợp thực sự chỉ có một bean, các tín hiệu như:

- `@Primary`: một ứng viên được đánh dấu primary rõ ràng.
- `@Fallback` từ Spring Framework 6.2: khi có một bean không phải fallback trong số các ứng viên fallback, bean bình thường có thể được chọn.
- Metadata default-candidate và các quy tắc phân giải ứng viên khác của container.

có thể giúp xác định một ứng viên thắng. Vì thế, **không nên tự kiểm tra `provider.stream().count() == 1` rồi cho rằng kết quả đó luôn tương đương `getIfUnique()`**: đếm tất cả bean không mô phỏng toàn bộ chính sách phân giải singular dependency.

## 3. `getObject()`: lấy một bean bắt buộc

Cú pháp:

```java
PaymentGateway gateway = provider.getObject();
```

Hành vi:

1. Spring tìm các bean thỏa kiểu generic `PaymentGateway`, qualifier và điều kiện ứng viên liên quan.
2. Nếu có một ứng viên phù hợp, hoặc có một ứng viên thắng sau phân giải, provider trả object đó.
3. Nếu không có ứng viên, ném `NoSuchBeanDefinitionException`.
4. Nếu còn nhiều ứng viên mà không có một lựa chọn duy nhất, ném `NoUniqueBeanDefinitionException`.
5. Nếu tạo bean thất bại, lỗi khởi tạo bean vẫn được phản ánh cho caller.

`getObject()` phù hợp khi **tại thời điểm thực hiện tính năng, bắt buộc phải có dependency**. Chẳng hạn chức năng thanh toán chính thức chỉ hoạt động nếu gateway đã được cấu hình đúng; báo lỗi là chính sách đúng, thay vì âm thầm chạy một gateway mặc định không được cấp phép.

Có thể bắt lỗi để thêm thông tin nghiệp vụ, nhưng cần phân biệt lỗi thiếu cấu hình với lỗi lập trình:

```java
// Minh họa trong method có biến provider kiểu ObjectProvider<PaymentGateway>.
try {
    PaymentGateway gateway = provider.getObject();
    gateway.pay();
} catch (NoUniqueBeanDefinitionException ex) {
    throw new IllegalStateException("Có nhiều payment gateway chưa được phân giải", ex);
} catch (NoSuchBeanDefinitionException ex) {
    throw new IllegalStateException("Chưa cấu hình payment gateway", ex);
}
```

Đoạn này chỉ minh họa API và chính sách lỗi; method `pay()` thuộc interface nghiệp vụ giả định, được triển khai trong dự án thực tế. Không nên bắt `Exception` chung rồi trả giá trị giả, vì làm mất thông tin lỗi cấu hình của hệ thống.

### `getObject(Object... args)`

Ngoài phiên bản không tham số, `getObject(Object... args)` có thể truyền **đối số tạo bean** cho factory trong những trường hợp phù hợp, đặc biệt khi lấy bean scope prototype qua constructor/factory method nhận tham số. Đây **không phải** API truyền qualifier, không phải cách chọn bean bằng tên, và không nên dùng để thay đổi dữ liệu khởi tạo của singleton đã tồn tại. Nếu dùng overload này, hãy kiểm tra cách tạo bean và scope cụ thể.

## 4. `getIfAvailable()`: cho phép dependency vắng mặt

Cú pháp:

```java
PaymentGateway gateway = provider.getIfAvailable();
if (gateway != null) {
    gateway.pay();
}
```

`getIfAvailable()` trả `null` khi **không có bean đáp ứng điều kiện**. Khác với `getObject()`, tình huống thiếu bean được xem là một kết quả hợp lệ. Tuy nhiên, nếu có hai gateway ngang nhau và không xác định được ứng viên thắng, lời gọi **vẫn ném `NoUniqueBeanDefinitionException`**.

Một tình huống thích hợp là dịch vụ gửi email tùy chọn:

```java
// Đoạn minh họa dùng NotificationSender do ứng dụng tự định nghĩa.
final class OrderService {
    private final ObjectProvider<NotificationSender> senders;

    OrderService(ObjectProvider<NotificationSender> senders) {
        this.senders = senders;
    }

    void completed(Order order) {
        senders.ifAvailable(sender -> sender.send(order));
    }
}
```

Đoạn này minh họa cách dùng, không phải file Java chạy độc lập: `NotificationSender` và `Order` là các kiểu nghiệp vụ chưa được định nghĩa. Ý nghĩa của `ifAvailable(Consumer<T>)` là chỉ gọi callback khi một bean có thể được phân giải. Nếu không có bean, không gọi callback. Nếu nhiều bean mơ hồ, vẫn có thể phát sinh `NoUniqueBeanDefinitionException`.

### Cung cấp giá trị mặc định bằng `Supplier`

`getIfAvailable(Supplier<T> defaultSupplier)` cho phép tạo object thay thế khi **không có bean**:

```java
PaymentGateway selected = provider.getIfAvailable(
        () -> new OfflinePaymentGateway()
);
```

Đây là đoạn minh họa với các kiểu ứng dụng; chỉ chạy sau khi định nghĩa `PaymentGateway` và `OfflinePaymentGateway`.

Điểm cần nhớ:

- Supplier thường **chỉ được gọi khi không có bean phù hợp**. Không nên thực hiện side effect trong supplier.
- Supplier **không được dùng để che lỗi ambiguity**. Hai gateway không primary vẫn khiến `getIfAvailable(supplier)` ném `NoUniqueBeanDefinitionException`.
- Object do supplier tự tạo bằng `new` **không mặc nhiên là bean do Spring quản lý**: không tự có dependency injection, lifecycle callbacks, proxy AOP hay destruction callback của container.
- Nếu fallback là đối tượng cần Spring quản lý, nên khai báo fallback như bean có điều kiện phù hợp, hoặc thiết kế cơ chế lựa chọn bean minh bạch.

Với chính sách “tính năng tùy chọn”, dùng `getIfAvailable()` hoặc `ifAvailable(...)` thường diễn đạt đúng hơn việc bắt exception từ `getObject()` rồi bỏ qua.

## 5. `getIfUnique()`: không có lựa chọn rõ ràng thì không lấy

Cú pháp:

```java
PaymentGateway gateway = provider.getIfUnique();
if (gateway == null) {
    // Không có ứng viên nào hoặc vẫn còn nhiều ứng viên ngang nhau.
}
```

Khác biệt quan trọng so với `getIfAvailable()` là **`getIfUnique()` trả `null` cả khi có nhiều bean nhưng không thể chọn một bean duy nhất**. Do đó nó thích hợp khi một hành vi chỉ nên bật nếu dependency có thể được suy ra an toàn từ cấu hình, và việc bỏ qua chức năng là chấp nhận được.

Hạn chế: giá trị `null` **không chỉ ra lý do**. Nếu nghiệp vụ cần báo lỗi thiếu cấu hình khác với cấu hình mơ hồ, `getIfUnique()` không đủ thông tin để phân biệt; nên chọn `getObject()`/`getIfAvailable()` và xử lý exception tương ứng.

Dạng có giá trị mặc định:

```java
PaymentGateway gateway = provider.getIfUnique(
        () -> new OfflinePaymentGateway()
);
```

`getIfUnique(Supplier<T>)` dùng fallback **khi không có ứng viên hoặc khi không thể xác định ứng viên thắng**. Đây chính là khác biệt với `getIfAvailable(Supplier<T>)`.

Ngoài ra, `ifUnique(Consumer<T>)` chạy callback nếu chọn được một bean duy nhất, còn khi không có bean hoặc nhiều bean mơ hồ thì không gọi callback. Các lỗi thực sự khi khởi tạo bean vẫn có thể được ném ra.

### Khi nào là “im lặng sai”?

Đừng dùng `getIfUnique()` cho quy trình bắt buộc cần đúng một gateway đã cấu hình: nếu hệ thống vô tình có hai gateway ngang nhau, `null` có thể làm bạn tưởng rằng tính năng bị tắt hợp lệ. Với dependency bắt buộc, `getObject()` sẽ phát hiện lỗi cấu hình sớm hơn tại thời điểm gọi.

## 6. Ví dụ Java 17+ hoàn chỉnh: bốn tình huống bean resolution

Ví dụ sau tạo **bốn `ApplicationContext` tách biệt** để kiểm tra bảng hành vi: không có gateway, có một gateway, có hai gateway không primary, và có hai gateway với một primary. Mỗi context dùng `@Configuration` và `@Bean` tiêu chuẩn; không cần Spring Boot.

### 6.1. Cấu trúc

```text
object-provider-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── ObjectProviderDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'object-provider-demo'
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
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'ObjectProviderDemo'
}
```

Sử dụng Spring Framework `6.2.19` (artifact có trên Maven Central) và JDK 17 trở lên. Gradle cần là phiên bản tương thích với JDK được sử dụng.

### 6.2. Mã nguồn `src/main/java/ObjectProviderDemo.java`

```java
import java.util.function.Supplier;

import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

public class ObjectProviderDemo {

    interface Gateway {
        String name();
    }

    record NamedGateway(String name) implements Gateway {
    }

    @Configuration(proxyBeanMethods = false)
    static class EmptyConfig {
        // Không có Gateway bean.
    }

    @Configuration(proxyBeanMethods = false)
    static class SingleConfig {
        @Bean
        Gateway card() {
            return new NamedGateway("card");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AmbiguousConfig {
        @Bean
        Gateway card() {
            return new NamedGateway("card");
        }

        @Bean
        Gateway bank() {
            return new NamedGateway("bank");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrimaryConfig {
        @Bean
        @Primary
        Gateway card() {
            return new NamedGateway("card");
        }

        @Bean
        Gateway bank() {
            return new NamedGateway("bank");
        }
    }

    private static String describe(Supplier<Gateway> action) {
        try {
            Gateway gateway = action.get();
            return gateway == null ? "null" : gateway.name();
        } catch (NoUniqueBeanDefinitionException ex) {
            return "NoUniqueBeanDefinitionException";
        } catch (NoSuchBeanDefinitionException ex) {
            return "NoSuchBeanDefinitionException";
        }
    }

    private static void runCase(String label, Class<?> configuration) {
        try (var context =
                     new AnnotationConfigApplicationContext(configuration)) {
            ObjectProvider<Gateway> provider =
                    context.getBeanProvider(Gateway.class);

            System.out.println("== " + label + " ==");
            System.out.println("getObject: " +
                    describe(provider::getObject));
            System.out.println("getIfAvailable: " +
                    describe(provider::getIfAvailable));
            System.out.println("getIfUnique: " +
                    describe(provider::getIfUnique));
            System.out.println("available/default: " +
                    describe(() -> provider.getIfAvailable(
                            () -> new NamedGateway("fallback"))));
            System.out.println("unique/default: " +
                    describe(() -> provider.getIfUnique(
                            () -> new NamedGateway("fallback"))));
        }
    }

    public static void main(String[] args) {
        runCase("EMPTY", EmptyConfig.class);
        runCase("SINGLE", SingleConfig.class);
        runCase("AMBIGUOUS", AmbiguousConfig.class);
        runCase("PRIMARY", PrimaryConfig.class);
    }
}
```

### 6.3. Chạy chương trình

Trong thư mục dự án:

```bash
gradle run --quiet
```

Nếu sử dụng Gradle Wrapper thì dùng `./gradlew run --quiet` trên macOS/Linux hoặc `.\gradlew.bat run --quiet` trên Windows PowerShell.

Các dòng do `System.out.println` của chương trình tạo ra:

```text
== EMPTY ==
getObject: NoSuchBeanDefinitionException
getIfAvailable: null
getIfUnique: null
available/default: fallback
unique/default: fallback
== SINGLE ==
getObject: card
getIfAvailable: card
getIfUnique: card
available/default: card
unique/default: card
== AMBIGUOUS ==
getObject: NoUniqueBeanDefinitionException
getIfAvailable: NoUniqueBeanDefinitionException
getIfUnique: null
available/default: NoUniqueBeanDefinitionException
unique/default: fallback
== PRIMARY ==
getObject: card
getIfAvailable: card
getIfUnique: card
available/default: card
unique/default: card
```

### 6.4. Phân tích từng cấu hình

**EMPTY:** Không có bean kiểu `Gateway`. `getObject()` ném lỗi; hai phương thức `getIf...` không có supplier trả `null`. Cả hai overload với supplier trả object `NamedGateway("fallback")` do code tạo ra.

**SINGLE:** Chỉ một bean `card`; mọi phương thức đều trả bean đó, fallback supplier không cần thực thi.

**AMBIGUOUS:** `card` và `bank` đều cùng kiểu, không có `@Primary` hay dấu hiệu phân giải duy nhất. `getObject()` và cả hai biến thể `getIfAvailable` ném `NoUniqueBeanDefinitionException`. `getIfUnique()` trả `null`; biến thể có supplier trả `fallback`.

**PRIMARY:** Vẫn có hai bean nhưng `card` là primary duy nhất. Cả ba phương thức đều trả `card`, không có ambiguity. Điều này chứng minh `getIfUnique()` không đòi container chỉ có đúng một bean definition.

Các chuỗi lỗi xuất hiện ở đây do helper `describe` **bắt và in tên exception**. Nếu bỏ helper và gọi `getObject()` trực tiếp trong trường hợp EMPTY/AMBIGUOUS, chương trình sẽ phát sinh exception thay vì in tên exception. Ví dụ được thiết kế để kiểm thử mọi case trong cùng một lần chạy.

## 7. Cách tiêm `ObjectProvider` vào bean ứng dụng

### 7.1. Constructor injection

`ObjectProvider<T>` thường được truyền qua constructor, giống các dependency khác:

```java
// Mã minh họa sử dụng kiểu Gateway của ứng dụng.
final class CheckoutService {
    private final ObjectProvider<Gateway> gateways;

    CheckoutService(ObjectProvider<Gateway> gateways) {
        this.gateways = gateways;
    }

    String checkout() {
        Gateway selected = gateways.getObject();
        return "Using " + selected.name();
    }
}
```

Đây là đoạn mã **minh họa**, không tự compile nếu chưa khai báo `Gateway` và đăng ký `CheckoutService` làm bean. Constructor chỉ giữ provider; bean mục tiêu được resolve khi gọi `checkout()`. Nếu nghiệp vụ luôn yêu cầu một `Gateway` và không có lý do resolve muộn, tiêm trực tiếp `Gateway` vẫn đơn giản hơn và kiểm tra cấu hình ngay khi khởi tạo service.

### 7.2. Phối hợp với `@Qualifier`

Khi có nhiều gateway, qualifier giúp thu hẹp tập ứng viên **trước khi** ba phương thức thực hiện phân giải:

```java
// Đoạn minh họa: khai báo ở bean.
@Bean
@Qualifier("external")
Gateway stripeGateway() {
    return new NamedGateway("stripe");
}

// Đoạn minh họa: tham số constructor một bean khác.
CheckoutService(
        @Qualifier("external") ObjectProvider<Gateway> externalGateway) {
    this.gateways = externalGateway;
}
```

Nếu chỉ có một gateway cùng kiểu mang qualifier `external`, `externalGateway.getObject()`, `getIfAvailable()` và `getIfUnique()` đều có thể chọn nó. Nếu có hai bean cùng qualifier và không có ứng viên thắng rõ ràng thì ambiguity vẫn xảy ra như trong bảng.

**Lưu ý:** Không dùng `ObjectProvider<Gateway>` rồi mong Spring tự chọn bean theo tên tham số trong mọi trường hợp. Khi vai trò nghiệp vụ rõ ràng, sử dụng `@Qualifier` hoặc tên bean/metadata có chủ đích.

### 7.3. Lấy provider từ `ApplicationContext`/`BeanFactory`

Ví dụ ở mục 6 gọi:

```java
ObjectProvider<Gateway> provider =
        context.getBeanProvider(Gateway.class);
```

Cách này hữu ích trong code điều phối container, tích hợp framework hoặc ở một điểm đã có `ApplicationContext`. Trong business service, constructor injection của `ObjectProvider<T>` thường diễn đạt dependency rõ hơn và giúp unit test dễ dàng hơn.

Với generic phức tạp (ví dụ `Repository<Customer>`), cách tìm bằng `getBeanProvider(Class<?>)` chỉ biểu diễn raw class. Có thể dùng biến thể nhận `ResolvableType` hoặc `ParameterizedTypeReference` khi cần giữ thông tin generic. Đừng cố truyền `List<Gateway>` vào `getBeanProvider(...)` và cho rằng Spring sẽ tự tổng hợp mọi Gateway; muốn duyệt nhiều bean, lấy provider theo kiểu **phần tử** rồi dùng `stream()`/`orderedStream()`.

## 8. Provider giải quyết lúc dùng: lazy, scope và cache

Một đặc tính quan trọng là **thời điểm resolve**. Tiêm `ObjectProvider<Gateway>` chưa bắt caller chọn ngay một `Gateway` ở constructor. Tuy nhiên, điều này **không tự bảo đảm mọi singleton Gateway được trì hoãn khởi tạo**.

Với Spring container mặc định, các **singleton không đánh dấu lazy** có thể được tạo sẵn khi context `refresh()`. Để trì hoãn việc tạo target bean đến lúc thật sự cần, cần kết hợp cơ chế thích hợp như `@Lazy` trên bean definition:

```java
@Bean
@Lazy
Gateway expensiveGateway() {
    return new ExpensiveGateway();
}
```

Đây là đoạn minh họa, cần định nghĩa `ExpensiveGateway` và import `@Lazy` trong dự án thực tế. Khi một code khác trực tiếp cần bean đó, Spring vẫn có thể khởi tạo nó; lazy là thuộc tính vòng đời và nhu cầu sử dụng thực tế, không phải cam kết bean không bao giờ được tạo.

### Mỗi lần gọi có tạo object mới không?

**Không nhất thiết.** Provider phân giải bean qua Spring container; **scope** mới quyết định có dùng lại instance hay tạo instance mới:

| Scope của target bean | Hai lần gọi `provider.getObject()` |
| --- | --- |
| `singleton` (mặc định) | Thông thường cùng một instance Spring quản lý |
| `prototype` | Thông thường tạo instance mới cho mỗi lần resolve |
| Request/session scope | Tùy scope hiện đang hoạt động và proxy được cấu hình |

Nếu một application phải tạo mới một đối tượng xử lý theo từng request, hãy dùng scope phù hợp hoặc factory có chủ đích. **`ObjectProvider` không có nghĩa là prototype**.

### Provider có “nhìn thấy” thay đổi bean registry không?

Provider thu được từ `BeanFactory` hoạt động trên state của factory. Về nguyên tắc, lời gọi tiếp theo có thể resolve theo trạng thái hiện tại của container, kể cả các thay đổi đăng ký bean được hỗ trợ. Tuy nhiên, application không nên coi việc thêm/xóa bean động sau khi context vận hành như một cơ chế tùy ý an toàn cho production: nhiều cấu trúc bean lifecycle/extension point giả định container đã được cấu hình ổn định. Sử dụng provider trước tiên cho optionality, lazy lookup và chọn bean theo tiêu chí.

## 9. Chọn API nào theo chính sách nghiệp vụ?

| Nhu cầu | Gợi ý | Lý do |
| --- | --- | --- |
| Tại lúc sử dụng bắt buộc có một bean hợp lệ | `getObject()` | Thiếu và ambiguity đều được phát hiện như lỗi cấu hình |
| Tính năng tùy chọn, thiếu bean là bình thường, nhiều bean là lỗi | `getIfAvailable()` | Trả `null` nếu thiếu, vẫn báo ambiguity |
| Cần object thay thế khi không đăng ký bean | `getIfAvailable(supplier)` | Fallback chỉ cho trường hợp không tìm thấy bean |
| Chỉ sử dụng bean khi chọn được một ứng viên thắng; còn lại bỏ qua | `getIfUnique()` | Trả `null` nếu thiếu **hoặc** ambiguity |
| Bỏ qua bean khi thiếu/mơ hồ, thay bằng object khác | `getIfUnique(supplier)` | Fallback được dùng cho cả hai trường hợp |
| Thực hiện side effect khi có ứng viên hợp lệ | `ifAvailable(consumer)` / `ifUnique(consumer)` | Không phải tự kiểm tra `null` |
| Muốn duyệt tất cả bean cùng kiểu | `stream()` / `orderedStream()` | Tránh buộc một bean thắng trong selection đơn |
| Dependency bắt buộc ngay từ lúc tạo service | Tiêm trực tiếp `T` | Ngắn gọn và phát hiện sai cấu hình khi tạo bean |
| Dependency tùy chọn được resolve một lần ở constructor | `Optional<T>` có thể phù hợp | Nhưng không có chính sách linh hoạt khi nhiều ứng viên mơ hồ |

Cần phân biệt các trường hợp “không có”, “không duy nhất” và “tạo bean thất bại”. Không đưa cùng một fallback cho tất cả nếu chúng mang ý nghĩa nghiệp vụ khác nhau.

### `Optional<T>` khác `ObjectProvider<T>` ở đâu?

Constructor injection với `Optional<Gateway>` biểu diễn “Gateway có thể không tồn tại” tại thời điểm tạo bean. Khi có nhiều Gateway mơ hồ, đó vẫn là vấn đề phân giải bean. `ObjectProvider<Gateway>` cung cấp handle để **truy vấn về sau**, có thể gọi nhiều lần và chọn chính sách `getObject`, `getIfAvailable` hoặc `getIfUnique` tùy tình huống.

Nếu một đối tượng chỉ cần đọc một dependency tùy chọn đúng một lần, `Optional<T>` có thể làm ý định rõ hơn. Nếu cần lazily resolve hoặc đếm/duyệt tập bean, `ObjectProvider<T>` thích hợp hơn.

## 10. Lỗi thường gặp và hướng sửa

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `getObject()` ném `NoSuchBeanDefinitionException` | Không có bean phù hợp kiểu/qualifier | Kiểm tra `@Component`/`@Bean`, component scan, profile, conditional configuration |
| `getIfAvailable()` vẫn ném exception dù tên chứa “Available” | Có nhiều bean và không có ứng viên thắng | Thêm `@Qualifier`/`@Primary` theo thiết kế, hoặc dùng `getIfUnique()` nếu bỏ qua ambiguity là đúng |
| `getIfUnique()` trả `null` dù có nhiều bean | Không chọn được ứng viên thắng duy nhất | Đây là hành vi thiết kế; quyết định rõ muốn fallback hay báo lỗi |
| `getIfUnique()` trả bean mặc dù có hai bean cùng kiểu | Có một bean được Spring ưu tiên, ví dụ `@Primary` | Xem selection policy, không đếm bean thô để kết luận |
| `getIfAvailable(supplier)` không chạy supplier khi hai bean mơ hồ | Supplier chỉ dùng khi thiếu bean | Dùng `getIfUnique(supplier)` nếu chính sách cho phép fallback lúc không duy nhất |
| Ném `NullPointerException` sau `getIfAvailable()` | Không kiểm tra kết quả `null` | Dùng `if (bean != null)`, `ifAvailable(...)` hoặc overload supplier |
| Object fallback không được AOP/inject | Tạo trực tiếp bằng `new` trong supplier | Đăng ký fallback với container hoặc tự cung cấp đầy đủ dependency |
| Provider không làm giảm thời gian startup | Target singleton vẫn eager | Kiểm tra `@Lazy` và dependency graph; chỉ tiêm provider không bảo đảm lazy-init |
| Hai lần `getObject()` trả cùng instance dù mong đối tượng mới | Target bean scope singleton | Chuyển sang prototype khi thật sự phù hợp hoặc dùng factory rõ ràng |
| `NoUniqueBeanDefinitionException` bị bắt như lỗi “không có bean” | Exception này là subtype của `NoSuchBeanDefinitionException` | Catch subtype trước, sau đó catch superclass |
| Cache nhầm `getIfUnique() == null` thành “không cấu hình” | `null` có thể nghĩa thiếu **hoặc** mơ hồ | Chỉ cache kết luận nếu ứng dụng thật sự không cần phân biệt hai tình huống |
| `getBeanProvider(List.class)` không tìm được tập Gateway | Tìm bean có kiểu List, không tổng hợp mọi Gateway | Dùng `getBeanProvider(Gateway.class).stream()`/`orderedStream()` |

## 11. Bài tập tự kiểm tra

**Bài 1 — Giá trị mặc định.** Trong `AmbiguousConfig` ở mục 6, dự đoán kết quả của hai lời gọi:

```java
provider.getIfAvailable(() -> new NamedGateway("fallback"));
provider.getIfUnique(() -> new NamedGateway("fallback"));
```

Đáp án: lời gọi thứ nhất ném `NoUniqueBeanDefinitionException`; lời gọi thứ hai trả `fallback`. “Có bean” không đồng nghĩa “có một bean có thể chọn”.

**Bài 2 — Chọn ứng viên primary.** Gắn `@Primary` cho bean `bank()` của `AmbiguousConfig`. Khi đó ba lời gọi `getObject()`, `getIfAvailable()` và `getIfUnique()` đều trả bean nào? Đáp án: `bank`, giả sử không có điều kiện khác làm bean này không hợp lệ.

**Bài 3 — Hai primary.** Nếu cả `card()` và `bank()` đều được gắn `@Primary` thì `getObject()` và `getIfAvailable()` có thể phân giải bằng primary không? Không: primary không còn duy nhất, có thể phát sinh `NoUniqueBeanDefinitionException`. `getIfUnique()` thường trả `null` khi không thể phân giải một ứng viên thắng (các lỗi tạo bean độc lập vẫn có thể được ném).

**Bài 4 — Optional feature.** Module hiển thị hóa đơn chỉ gửi email khi có bean `InvoiceMailer`; thiếu mailer là bình thường, nhưng hai mailer cùng kiểu là lỗi triển khai. Nên chọn gì? `getIfAvailable()` hoặc `ifAvailable(...)`: cho phép thiếu bean, vẫn phát hiện ambiguity.

**Bài 5 — Cấu hình nhập nhằng.** Một plugin chỉ chạy nếu hệ thống có lựa chọn `Plugin` được xác định rõ; nếu không có hoặc không chọn được, hãy bỏ qua an toàn. Nên chọn gì? `getIfUnique()`/`ifUnique(...)`, nếu thực sự chấp nhận bỏ qua tình huống ambiguity.

**Bài 6 — Vòng đời.** Hai lần `provider.getObject()` có luôn tạo hai instance mới không? Không; điều đó phụ thuộc scope của bean. Với singleton thông thường, hai lần trả cùng instance.

**Bài 7 — Điều gì bị che giấu?** Một developer đổi tất cả lời gọi `getObject()` thành `getIfUnique()` rồi kiểm tra `null`. Rủi ro là gì? Cấu hình hai bean không phân giải được có thể bị xem nhầm như “tính năng tùy chọn chưa cấu hình”, khiến lỗi thiết lập không được báo cáo.

## 12. Kết luận và nguồn tham khảo

- `getObject()`: **phải có một bean thắng**, nếu không báo lỗi.
- `getIfAvailable()`: **thiếu bean trả null**, nhưng **nhiều bean mơ hồ vẫn báo lỗi**.
- `getIfUnique()`: **thiếu hoặc mơ hồ trả null**, chỉ trả bean khi Spring phân giải được một lựa chọn duy nhất.
- Hai overload nhận `Supplier<T>` có chính sách fallback **khác nhau**, không được hoán đổi tùy ý.
- `@Primary`/`@Qualifier` và các quy tắc candidate resolution ảnh hưởng kết quả; tính unique là **unique sau phân giải**, không phải đơn giản đếm bean.
- `ObjectProvider` giải quyết *thời điểm và chính sách truy xuất*; scope và lazy initialization quyết định vòng đời instance.

Tài liệu chính thức:

- [Spring Framework 6.2 — `ObjectProvider<T>` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectProvider.html).
- [Spring Reference — Annotation-based container configuration và autowiring](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html).
- [Spring Reference — Primary và Fallback](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html).
- [Spring Reference — Fine-tuning autowiring with qualifiers](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html).
- [Spring Framework 6.2 — `BeanFactory` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/BeanFactory.html).
