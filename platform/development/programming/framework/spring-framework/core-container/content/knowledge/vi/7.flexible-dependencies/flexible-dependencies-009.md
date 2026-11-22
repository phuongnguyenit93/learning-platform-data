# Giới hạn sử dụng provider để tránh che giấu phụ thuộc trong Spring Core Container

## 1. Mục tiêu và vấn đề thiết kế

**`ObjectProvider<T>`** của Spring cho phép trì hoãn việc tra cứu bean và biểu diễn những trường hợp phụ thuộc có thể thiếu, có nhiều ứng viên hoặc cần lấy lại theo scope. Công cụ này hữu ích, nhưng nếu đặt provider ở khắp các lớp nghiệp vụ, dependency vốn bắt buộc có thể bị biến thành tra cứu ngầm. Ứng dụng có thể khởi động dù thiếu thành phần quan trọng, rồi chỉ thất bại khi chạy một nhánh nghiệp vụ, hoặc tệ hơn là lặng lẽ bỏ qua một hành động bắt buộc.

Ví dụ: một dịch vụ thanh toán **bắt buộc** cần `PaymentGateway` để thu tiền. Nếu thay constructor `PaymentGateway` bằng `ObjectProvider<PaymentGateway>` rồi gọi `getIfAvailable()` và bỏ qua khi trả `null`, lỗi cấu hình đã bị biến thành tình huống "không có gateway" được chấp nhận. Đó là **che giấu phụ thuộc**: chữ ký class không còn nói rõ chức năng không thể hoàn thành nếu thiếu gateway.

Bài học hướng tới việc dùng provider **có giới hạn và có chủ đích**:

- Nêu rõ khi nào một dependency là **bắt buộc**, **tùy chọn** hay **chỉ cần tra cứu khi chạy**.
- Phân biệt constructor injection với Service Locator; nhận biết việc provider bị lạm dụng như công cụ tìm bất cứ bean nào từ container.
- Giữ lỗi thiếu thành phần cốt lõi xuất hiện sớm (*fail fast*).
- Dùng `ObjectProvider<T>` phù hợp tại ranh giới tích hợp, factory theo scope, tính năng bổ trợ hoặc tập plugin.
- Hiểu chính xác `getObject()`, `getIfAvailable()`, `getIfUnique()`, `ifAvailable()`, `stream()` và `orderedStream()`.
- Viết ví dụ Java 17 + Spring Framework 6.2 chạy được và các kiểm thử cho trường hợp thiếu bean.
- Tránh coi lazy lookup là cách sửa vòng phụ thuộc, xử lý lỗi hoặc cấu hình thiếu.

**Nguyên tắc xuyên suốt:** Nếu một class **không thể hoàn thành cam kết nghiệp vụ** khi thiếu `T`, hãy khai báo `T` trực tiếp trong constructor. Chỉ đưa `ObjectProvider<T>` vào khi có một lý do đúng về thời điểm lấy, số lượng hoặc tính tùy chọn của bean.

## 2. Bản chất của `ObjectProvider<T>`

`ObjectProvider<T>` nằm trong `org.springframework.beans.factory`, được Spring ràng buộc với BeanFactory và kiểu `T` của injection point. Nó là một đối tượng cung cấp khả năng **yêu cầu bean khi cần**, không phải bản sao của bean `T`. Những lời gọi provider được phân giải trên trạng thái BeanFactory tại thời điểm gọi; kết quả còn phụ thuộc kiểu bean, qualifier, scope và các quy tắc chọn ứng viên.

Các phương thức thường gặp:

| Phương thức | Ý nghĩa cơ bản | Điều cần cảnh giác |
| --- | --- | --- |
| `getObject()` | Lấy một bean `T` bắt buộc | Thiếu bean gây `NoSuchBeanDefinitionException`; nhiều ứng viên không chọn được gây `NoUniqueBeanDefinitionException`; lỗi tạo bean vẫn có thể xảy ra |
| `getIfAvailable()` | Lấy một bean nếu có | Trả `null` khi không có ứng viên; **không tự giải quyết** nhập nhằng hoặc lỗi khởi tạo |
| `getIfAvailable(supplier)` | Lấy bean hoặc gọi supplier tạo mặc định khi thiếu | Fallback có thể che cấu hình sai nếu `T` thực ra bắt buộc |
| `ifAvailable(consumer)` | Chỉ chạy hành động nếu lấy được bean | Phù hợp tác vụ bổ trợ; không dùng để âm thầm bỏ qua bước bắt buộc |
| `getIfUnique()` | Lấy bean nếu phân giải được ứng viên duy nhất | Có thể trả `null` khi không có bean hoặc không có ứng viên thắng theo quy tắc chọn |
| `stream()` | Duyệt 0..n bean phù hợp | Không cam kết thứ tự |
| `orderedStream()` | Duyệt 0..n bean theo comparator của Spring | Chỉ phù hợp khi thứ tự nghiệp vụ được khai báo rõ và kiểm thử |

**Điểm dễ nhầm:** provider **không mặc định** làm mọi dependency trở thành tùy chọn. Nếu service gọi `getObject()` khi chạy, thiếu bean vẫn gây exception, chỉ là exception chuyển từ lúc khởi tạo service sang thời điểm thực thi. Nếu service gọi `getIfAvailable()` rồi bỏ qua `null`, nó có thể đã thay đổi hợp đồng nghiệp vụ thành "được phép thiếu".

Provider cũng không bảo đảm bean đích chưa được tạo: singleton mặc định có thể đã khởi tạo khi context khởi động. Provider là cơ chế tra cứu linh hoạt, không phải công tắc lazy tuyệt đối.

## 3. Thế nào là che giấu phụ thuộc?

Một constructor là nơi thể hiện rõ những thứ cần thiết để tạo một đối tượng hoạt động đúng. So sánh hai thiết kế.

### 3.1. Hợp đồng rõ ràng: dependency bắt buộc

```java
// Minh họa: PaymentGateway là interface của ứng dụng.
final class PaymentService {
    private final PaymentGateway gateway;

    PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    String pay(String orderId) {
        return gateway.charge(orderId);
    }
}
```

Service không tồn tại hợp lệ khi thiếu gateway. Khi Spring tạo bean `PaymentService` bằng constructor injection mà không tìm được bean `PaymentGateway`, quá trình tạo bean thất bại và nguyên nhân được báo tại khởi động context (thường được bọc thành `UnsatisfiedDependencyException`). Đây là tín hiệu cấu hình thiếu cần được sửa.

### 3.2. Phản ví dụ: provider được dùng như công cụ né lỗi

```java
// PHẢN VÍ DỤ minh họa: không dùng cho nghiệp vụ thanh toán thật.
final class HiddenPaymentService {
    private final ObjectProvider<PaymentGateway> gatewayProvider;

    HiddenPaymentService(ObjectProvider<PaymentGateway> gatewayProvider) {
        this.gatewayProvider = gatewayProvider;
    }

    String pay(String orderId) {
        PaymentGateway gateway = gatewayProvider.getIfAvailable();

        if (gateway == null) {
            return "SKIPPED:" + orderId; // Giả vờ hoàn tất luồng chính!
        }

        return gateway.charge(orderId);
    }
}
```

Đoạn này là minh họa thiết kế sai, cần khai báo `PaymentGateway` và import `ObjectProvider` trong dự án chứa nó; không phải chương trình độc lập. Vấn đề không nằm ở việc Spring cho phép `getIfAvailable()`; vấn đề là nghiệp vụ **đòi thanh toán** nhưng code coi thiếu gateway là điều hợp lệ. Hệ thống có thể khởi động, chạy qua nhiều lớp, và chỉ khi nhận đơn hàng mới phát hiện không thể thu tiền hoặc trả về trạng thái sai.

Ngay cả khi dùng:

```java
PaymentGateway gateway = gatewayProvider.getObject();
return gateway.charge(orderId);
```

thì dependency vẫn bị che đi phần nào: chữ ký `HiddenPaymentService(ObjectProvider<PaymentGateway>)` không nói trực tiếp nó **bắt buộc** cần một gateway, còn sự thiếu bean bị báo muộn lúc `pay` chạy. Khi không cần lazy lookup/scope, nhận `PaymentGateway` trực tiếp rõ ràng hơn.

### 3.3. Dấu hiệu lạm dụng provider

Hãy xem xét lại thiết kế nếu thấy một trong các dấu hiệu sau:

1. Hầu như mọi constructor đều nhận nhiều `ObjectProvider<...>` mặc dù các service hoạt động ngay với những dependency đó.
2. Nhiều method gọi `getIfAvailable()` hoặc `getIfUnique()` và âm thầm bỏ qua việc không lấy được bean.
3. Code gọi `ApplicationContext.getBean(...)` hoặc `BeanFactory.getBean(...)` bằng chuỗi tên class/bean thay vì khai báo dependency trong constructor.
4. Một service tự hỏi container xem nó có thể thanh toán, lưu dữ liệu hoặc kiểm soát quyền hay không, thay vì nhận thành phần bắt buộc cho các nhiệm vụ đó.
5. Unit test phải dựng Spring context thật chỉ để chạy một hàm nghiệp vụ thuần Java.
6. Thiếu bean chỉ được phát hiện khi người dùng gọi endpoint hiếm gặp hoặc khi tải tăng cao.
7. Provider xuất hiện để né một vòng phụ thuộc mà không thay đổi quan hệ trách nhiệm giữa các class.

Đây là **tín hiệu cần kiểm tra**, không phải lệnh cấm mọi provider. Một adapter thật sự cần tạo prototype bean theo từng request có lý do chính đáng để dùng provider ngay cả khi prototype đó là thành phần quan trọng.

## 4. Phân loại dependency trước khi chọn kiểu injection

Câu hỏi đầu tiên là: **Nếu bean này không tồn tại, chức năng có còn thực hiện đúng hợp đồng không?**

| Loại phụ thuộc | Ví dụ | Kiểu nên ưu tiên | Hành vi khi thiếu |
| --- | --- | --- | --- |
| Bắt buộc | `PaymentGateway` để thu tiền, repository để lưu dữ liệu | Constructor `PaymentGateway`/`Repository` | Lỗi cấu hình càng sớm càng tốt |
| Tùy chọn đơn lẻ | Adapter gửi telemetry/audit bổ trợ | `Optional<AuditSink>` nếu chỉ cần phân giải một lần | Bỏ qua hoặc dùng fallback được quy định rõ |
| Tùy chọn nhiều implementation | Các plugin ghi chỉ số, listener mở rộng | `List<Hook>` hoặc `ObjectProvider<Hook>.stream()` | Tập rỗng là trường hợp hợp lệ |
| Cần lazy lookup theo thời điểm | Một tác vụ chỉ kích hoạt plugin hiếm dùng | `ObjectProvider<Plugin>` tại ranh giới sử dụng | Phải quyết định rõ 0/1/n bean có nghĩa gì |
| Cần instance theo scope | Object `prototype` hoặc scoped bean cần lấy mỗi lần | `ObjectProvider<Worker>` hoặc factory chuyên dụng | Không suy đoán mỗi lần lấy đều là instance mới; xem scope |
| Cần chọn động theo nghiệp vụ | Chọn bộ xử lý theo tenant/mã kênh | Interface `StrategyRegistry` / factory hoặc map tường minh | Thiếu chiến lược phải có chính sách nghiệp vụ rõ |

**Đừng chọn kiểu chỉ để Spring khởi động được.** Chọn kiểu để thể hiện hợp đồng đúng. Nếu thật sự được phép thiếu một thành phần, hãy mô tả fallback, điều kiện kích hoạt và cách đo lường; nếu thành phần đó bắt buộc, giữ constructor injection tường minh.

Có thể dùng `@Qualifier` để xác định implementation yêu cầu:

```java
// Đoạn minh họa trong bean do Spring quản lý:
OrderService(@Qualifier("primaryPaymentGateway") PaymentGateway gateway) {
    this.gateway = gateway;
}
```

Điều này vẫn thể hiện **dependency bắt buộc**, đồng thời chọn đúng bean mong muốn. `@Primary` giải quyết một số tình huống nhiều ứng viên, nhưng không thay thế thiết kế hợp đồng.

## 5. Ví dụ hoàn chỉnh: cốt lõi bắt buộc, phần mở rộng tùy chọn

Ta xây một ứng dụng nhỏ sử dụng **constructor injection trực tiếp cho `PaymentGateway`**, và chỉ dùng provider ở **ranh giới các hook sau thanh toán**, vốn có thể không có hoặc có nhiều implementation.

Ứng dụng tạo hai Spring context riêng:

- Context chỉ có cấu hình lõi: gateway tồn tại, không có hook; thanh toán vẫn thành công.
- Context có cấu hình lõi và hook: thanh toán vẫn thực hiện, thêm hai hook phụ trợ theo thứ tự.

Mục tiêu là kiểm chứng provider được dùng để **mở rộng hành vi**, không phải hợp thức hóa việc thiếu thành phần chính.

### 5.1. Cấu trúc dự án

```text
bounded-provider/
├── pom.xml
└── src/main/java/demo/BoundedProviderDemo.java
```

Nội dung `pom.xml` (Spring Framework thuần, Java 17):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bounded-provider</artifactId>
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

Nội dung `src/main/java/demo/BoundedProviderDemo.java`:

```java
package demo;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

public class BoundedProviderDemo {

    interface PaymentGateway {
        String charge(String orderId);
    }

    interface PaymentHook {
        void afterPayment(String receipt);
    }

    static final class PaymentService {
        private final PaymentGateway gateway;

        PaymentService(PaymentGateway gateway) {
            this.gateway = gateway;
        }

        String pay(String orderId) {
            return gateway.charge(orderId);
        }
    }

    static final class CheckoutFacade {
        private final PaymentService payments;
        private final ObjectProvider<PaymentHook> hooks;

        CheckoutFacade(PaymentService payments,
                       ObjectProvider<PaymentHook> hooks) {
            this.payments = payments;
            this.hooks = hooks;
        }

        void checkout(String orderId) {
            String receipt = payments.pay(orderId);
            System.out.println("receipt=" + receipt);

            // Hook là phần mở rộng: không có hook vẫn hợp lệ.
            hooks.orderedStream().forEach(hook -> hook.afterPayment(receipt));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CoreConfig {

        @Bean
        PaymentGateway paymentGateway() {
            return orderId -> "PAID:" + orderId;
        }

        @Bean
        PaymentService paymentService(PaymentGateway gateway) {
            return new PaymentService(gateway);
        }

        @Bean
        CheckoutFacade checkoutFacade(
                PaymentService payments,
                ObjectProvider<PaymentHook> hooks) {
            return new CheckoutFacade(payments, hooks);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class OptionalHooksConfig {

        @Bean
        @Order(10)
        PaymentHook auditHook() {
            return receipt -> System.out.println("audit=" + receipt);
        }

        @Bean
        @Order(20)
        PaymentHook metricsHook() {
            return receipt -> System.out.println("metrics=" + receipt);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(CoreConfig.class)) {
            System.out.println("core only:");
            context.getBean(CheckoutFacade.class).checkout("42");
        }

        try (var context = new AnnotationConfigApplicationContext(
                CoreConfig.class, OptionalHooksConfig.class)) {
            System.out.println("core plus hooks:");
            context.getBean(CheckoutFacade.class).checkout("42");
        }
    }
}
```

Chạy trong thư mục `bounded-provider` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BoundedProviderDemo
```

Các dòng do **chính chương trình** in ra (không tính log riêng của Maven hoặc môi trường):

```text
core only:
receipt=PAID:42
core plus hooks:
receipt=PAID:42
audit=PAID:42
metrics=PAID:42
```

### 5.2. Vì sao cách thiết kế này hợp lý?

**`PaymentService` nhận `PaymentGateway` trực tiếp.** Trong cả hai context, gateway là thành phần bắt buộc. Nếu bỏ bean `paymentGateway()` khỏi `CoreConfig` mà vẫn giữ `PaymentService`, context sẽ không tạo được service thành công do thiếu dependency. Điều đó đúng với yêu cầu "không thể thanh toán nếu không có gateway".

**`CheckoutFacade` nhận `ObjectProvider<PaymentHook>` tại ranh giới extension.** Số hook được phép là 0, 1 hoặc nhiều. Với context đầu tiên, `orderedStream()` rỗng nên không có output audit/metrics. Với context thứ hai, hai hook chạy theo `@Order(10)` rồi `@Order(20)`.

**Phạm vi provider có chủ đích.** Provider không được rải vào `PaymentService`, không được dùng để tìm `PaymentGateway` khi đến lệnh `pay`, và không thay đổi hợp đồng cốt lõi của nó. Lớp ranh giới `CheckoutFacade` điều phối phần mở rộng được phép vắng mặt.

**Hai context là hai cấu hình khởi động độc lập.** Ví dụ không tuyên bố rằng bạn có thể thêm bean động vào một ApplicationContext đã refresh rồi mọi provider sẽ tự hot-plug chúng trong mọi hoàn cảnh.

**Về xử lý lỗi hook:** Ví dụ không bắt exception từ hook. Nếu một hook ném exception sau khi gateway đã trả receipt, `checkout` sẽ gặp lỗi mặc dù thanh toán có thể đã hoàn tất. Trong ứng dụng thật, phải xác định chính sách lỗi, idempotency và thời điểm phát sự kiện (thí dụ sau khi transaction commit) trước khi để hook chạy đồng bộ; **provider không quyết định chính sách này**.

## 6. Chọn chính sách lỗi theo vai trò của dependency

Việc chọn `ObjectProvider` chỉ hợp lý khi consumer **chủ động xác định điều kiện nào được phép thiếu và điều kiện nào phải báo lỗi**. Thay vì học lại bảng API, hãy kiểm tra ba tình huống nghiệp vụ:

| Vai trò | Cách truy cập nên dùng | Khi thiếu hoặc nhập nhằng |
| --- | --- | --- |
| Gateway bắt buộc, dùng ngay | Constructor nhận `PaymentGateway` trực tiếp | Context báo thiếu/mơ hồ sớm; không trả thành công giả |
| Adapter phụ trợ tùy chọn duy nhất | `Optional<AuditSink>` hoặc `getIfAvailable()` nếu cần lookup muộn | Được phép thiếu, **nhập nhằng vẫn cần báo lỗi** |
| Extension point cho 0..n hook | `ObjectProvider<Hook>.stream()` / `orderedStream()` | Tập rỗng hợp lệ; nhiều hook phải được xử lý đủ |
| Chỉ bật tính năng nếu có lựa chọn duy nhất | `getIfUnique()` hoặc `ifUnique(...)` | Cả thiếu và mơ hồ đều bỏ qua **chỉ khi đó là chính sách đã được duyệt** |

`getIfAvailable(Supplier)` và `getIfUnique(Supplier)` không tương đương: fallback thứ nhất dành cho thiếu bean, fallback thứ hai còn áp dụng khi không chọn được ứng viên duy nhất. Một `@Primary` hợp lệ có thể giúp chọn một bean từ nhiều ứng viên; fallback không thay thế việc xử lý lỗi khởi tạo bean. Nếu fallback được tạo bằng `new`, nó không tự nhận injection, proxy và vòng đời từ Spring.

Trong ví dụ checkout, `PaymentService` nhận gateway trực tiếp để fail fast, còn `CheckoutFacade` duyệt toàn bộ hook ở ranh giới mở rộng. Đây là ranh giới thiết kế cần đánh giá; chi tiết exception và kết quả của từng phương thức đã được mô phỏng ở bài chuyên sâu về `getObject`/`getIfAvailable`/`getIfUnique`.

## 7. Bắt lỗi ở nơi đúng thay vì né phụ thuộc

Một mẫu dễ gây hiểu lầm:

```java
// PHẢN VÍ DỤ: không dùng cho nghiệp vụ bắt buộc.
try {
    repositoryProvider.getObject().save(order);
} catch (Exception ignored) {
    // Lặng lẽ bỏ qua mọi lỗi lưu dữ liệu.
}
```

Đoạn này có ít nhất ba vấn đề: dependency quan trọng được tìm muộn, lỗi thiếu bean bị trộn với lỗi lưu dữ liệu, và ngoại lệ bị nuốt không để lại dấu vết. Hệ thống có thể báo giao dịch thành công dù dữ liệu chưa được lưu.

Cách phù hợp hơn là **constructor injection trực tiếp** và xử lý lỗi nghiệp vụ bằng chính sách tường minh:

```java
// Minh họa trong lớp đã khai báo OrderRepository, Order và Receipt.
final class OrderApplicationService {
    private final OrderRepository repository;

    OrderApplicationService(OrderRepository repository) {
        this.repository = repository;
    }

    Receipt submit(Order order) {
        repository.save(order);
        return new Receipt(order.id());
    }
}
```

Đây là mã minh họa: `OrderRepository`, `Order` và `Receipt` là các kiểu do ứng dụng định nghĩa. Khi repository không đăng ký, Spring phát hiện thiếu dependency khi tạo bean. Khi `save` thất bại vì hạ tầng, exception đi ra đúng đường để transactional boundary, error handler và hệ thống quan sát xử lý. Dependency injection không thay cho chính sách transaction hoặc retry.

Nếu một thao tác thật sự "best effort" (ví dụ phát một metric không bắt buộc), có thể bắt lỗi **của thao tác phụ trợ**, log/đếm lỗi một cách phù hợp và xác định ảnh hưởng tới request. Nhưng nên phân biệt **không có plugin** với **plugin tồn tại nhưng chạy lỗi**; tự động coi hai tình huống như nhau làm khó vận hành.

## 8. Nơi provider được phép xuất hiện: ranh giới có chủ ý

Provider có giá trị ở những nơi nó thực sự giúp kiểm soát thời điểm hoặc số lượng bean.

### 8.1. Extension point có 0..n bean

```java
// Minh họa trong lớp ranh giới, không phải ứng dụng chạy độc lập.
final class HookDispatcher {
    private final ObjectProvider<DomainHook> hooks;

    HookDispatcher(ObjectProvider<DomainHook> hooks) {
        this.hooks = hooks;
    }

    void dispatch(Event event) {
        hooks.orderedStream().forEach(hook -> hook.onEvent(event));
    }
}
```

`DomainHook` và `Event` là kiểu ứng dụng. Nếu thiếu toàn bộ hook vẫn không ảnh hưởng nghiệp vụ, provider là hợp lý. Nếu cần đảm bảo luôn có một hook kiểm toán vì yêu cầu pháp lý, **đừng** tự coi stream rỗng là thành công; hãy kiểm tra điều kiện cấu hình hoặc khai báo thành phần bắt buộc.

### 8.2. Factory khi cần đối tượng prototype theo lượt

```java
// Minh họa: JobWorker là bean prototype trong cấu hình.
final class JobWorkerFactory {
    private final ObjectProvider<JobWorker> workers;

    JobWorkerFactory(ObjectProvider<JobWorker> workers) {
        this.workers = workers;
    }

    JobWorker newWorker() {
        return workers.getObject();
    }
}
```

Đây là ví dụ dùng provider để **lấy đúng thời điểm**, không để làm `JobWorker` trở thành tùy chọn. Khi thiếu bean, `getObject()` phát lỗi thay vì âm thầm tạo công việc giả. Có thể giấu chi tiết Spring phía sau một interface domain factory như `WorkerFactory` để các lớp nghiệp vụ khác không cần biết `ObjectProvider`.

Nếu bean có `@Scope("prototype")`, mỗi yêu cầu phân giải bean có thể tạo instance mới; nếu vẫn là singleton, provider thường trả singleton đó. Không suy luận scope chỉ từ việc code dùng provider.

### 8.3. Tích hợp tùy chọn một bean

Với dependency hiếm dùng, cho phép thiếu và chỉ phân giải **một lần** lúc tạo consumer, `Optional<T>` thường đơn giản hơn:

```java
// Đoạn minh họa trong một bean Spring-managed:
final class NotificationFacade {
    private final java.util.Optional<NotificationAdapter> adapter;

    NotificationFacade(java.util.Optional<NotificationAdapter> adapter) {
        this.adapter = adapter;
    }

    void notifyCreated(String id) {
        adapter.ifPresent(value -> value.send(id));
    }
}
```

Ngược lại, nếu muốn tra cứu khi được gọi hoặc phụ thuộc scope, provider có thể là lựa chọn phù hợp. Tránh dùng `ObjectProvider<T>` chỉ vì "linh hoạt hơn" khi thực tế không có nhu cầu linh hoạt nào.

### 8.4. Chọn implementation theo runtime key

Một service nhận mã phương thức vận chuyển và cần chọn đúng chiến lược có thể dùng **registry** thay vì tự quét BeanFactory trên mỗi nhánh:

```java
// Minh họa interface và consumer, không phải chương trình độc lập.
interface CarrierRegistry {
    Carrier forCode(String code);
}

final class ShippingService {
    private final CarrierRegistry registry;

    ShippingService(CarrierRegistry registry) {
        this.registry = registry;
    }

    void ship(String carrierCode, Parcel parcel) {
        registry.forCode(carrierCode).send(parcel);
    }
}
```

`Carrier` và `Parcel` là kiểu ứng dụng. Registry có thể nhận `Map<String, Carrier>`, `List<Carrier>` hoặc `ObjectProvider<Carrier>` ở **lớp hạ tầng** rồi áp dụng chính sách chọn và kiểm tra trùng khóa. Lớp `ShippingService` chỉ biết giao diện nghiệp vụ `CarrierRegistry`. Như vậy quyết định tra cứu bean tập trung ở một nơi dễ kiểm thử, không lan qua mọi service.

## 9. Service Locator và dependency ẩn

**Service Locator** là một kiểu thiết kế mà class tự yêu cầu một kho chung cung cấp dependency khi chạy, ví dụ lấy trực tiếp `ApplicationContext` rồi gọi `getBean("paymentGateway")` trong method.

```java
// PHẢN VÍ DỤ, minh họa mùi thiết kế.
final class LocatorCheckoutService {
    private final ApplicationContext context;

    LocatorCheckoutService(ApplicationContext context) {
        this.context = context;
    }

    String checkout(String id) {
        PaymentGateway gateway =
                context.getBean(PaymentGateway.class);
        return gateway.charge(id);
    }
}
```

Dù Spring hỗ trợ `ApplicationContext`, đây là ví dụ **trách nhiệm nghiệp vụ và cơ chế IoC bị trộn**. Constructor chỉ thấy `ApplicationContext`, không thấy `PaymentGateway` cần thiết. Lỗi cấu hình có thể bị đẩy đến thời điểm `checkout`. Unit test khó hơn vì phải mô phỏng container hoặc dùng Spring context.

`ObjectProvider<PaymentGateway>` tốt hơn locator tổng quát ở chỗ kiểu `PaymentGateway` còn xuất hiện trong chữ ký constructor, nhưng lạm dụng nó vẫn có thể tạo **lookup ngầm** và đẩy lỗi sang thời điểm chạy. Quy tắc thực hành:

- Đưa dependency bắt buộc vào constructor dưới dạng **interface cụ thể**.
- Nếu cần lazy/prototype, đặt provider trong một **factory hoặc adapter có trách nhiệm rõ**.
- Không truyền `ApplicationContext` xuyên qua nhiều tầng domain chỉ để "cần gì lấy nấy".
- Không giấu dependency bằng cách truyền `ObjectProvider<Object>` hoặc tìm bean theo chuỗi tên tùy ý.
- Nếu giới hạn cần thiết là "tất cả các plugin loại X", dùng `ObjectProvider<X>` đúng kiểu tại extension boundary; qualifier cũng có thể lọc nhóm.

Trong một số thành phần framework/infrastructure, truy cập `ApplicationContext` trực tiếp có thể hợp lý. Tiêu chí đánh giá là **mức độ phụ thuộc vào Spring bị lộ ra** và **độ rõ ràng của hợp đồng** của class, không phải cấm tuyệt đối một API.

## 10. Provider có giải quyết vòng phụ thuộc không?

Không nên dùng provider như cách né vòng phụ thuộc cấu trúc một cách vô điều kiện.

Giả sử `OrderService` phụ thuộc `InvoiceService` và `InvoiceService` lại phụ thuộc `OrderService`. Đổi một nhánh thành `ObjectProvider<OrderService>` có thể **trì hoãn** thời điểm yêu cầu bean, nhưng mối quan hệ trách nhiệm hai chiều vẫn tồn tại. Nếu gọi `provider.getObject()` ngay trong constructor hoặc khi hai bean còn đang khởi tạo, lỗi vòng phụ thuộc có thể vẫn xuất hiện.

Các hướng sửa thiết kế có chủ đích:

1. Tách trách nhiệm chung sang service thứ ba mà cả hai cùng phụ thuộc.
2. Tách hành động hậu xử lý qua sự kiện/domain event nếu nghiệp vụ cho phép.
3. Đưa một luồng điều phối vào orchestration service thay vì để hai service gọi qua lại.
4. Chỉ dùng provider khi cần đúng **thời điểm truy vấn** và vòng đời thực sự đòi hỏi nó; kiểm thử trường hợp bootstrap lẫn chạy thực tế.

`@Lazy` cũng là công cụ thay đổi thời điểm khởi tạo hoặc dereference trong những tình huống phù hợp. Nhưng thêm `@Lazy` không thay đổi sự thật một class đang cần dịch vụ nào, và không tự làm quan hệ hai chiều trở nên hợp lý về mặt kiến trúc.

## 11. Provider, scope và thời điểm phát hiện lỗi

Cùng một provider có thể mang rủi ro khác nhau tùy scope.

| Điều kiện | Khi gọi provider | Ý nghĩa thiết kế |
| --- | --- | --- |
| Singleton thường | Có thể trả bean đã được tạo sẵn | Provider không tự làm singleton lazy |
| Singleton `@Lazy` | Có thể tạo khi được yêu cầu lần đầu | Lỗi khởi tạo có thể đến muộn hơn |
| Prototype | Có thể tạo instance mới theo từng lần phân giải | Cần nhận thức về chi phí, vòng đời và cleanup resource |
| Scoped proxy/request scope | Có thể dùng proxy và resolve theo scope hiện hành | Gọi ngoài scope phù hợp có thể gây lỗi |
| Tập nhiều bean qua `stream()` | Resolve các ứng viên khi duyệt stream | Chỉ truy vấn khi cần, nhưng terminal operation có thể tạo nhiều bean |

Nếu nghiệp vụ bắt buộc phải có một adapter nhưng vì lý do hiệu năng bạn không muốn khởi tạo nó trước khi chạy tác vụ, có thể giữ provider trong factory/layer điều phối với tên method thể hiện **bắt buộc** (ví dụ `requiredWorker()` gọi `getObject()`). Điều quan trọng là **không biến thất bại thành "không có gì để làm"** và phải có kiểm thử cho nhánh hiếm dùng.

Nếu bean chỉ được yêu cầu theo một đường chạy đặc biệt (ví dụ job chạy cuối tuần), provider có thể khiến lỗi cấu hình chỉ lộ ra khi job được kích hoạt. Để khắc phục, bạn có thể thêm startup validation phù hợp hoặc một integration test kích hoạt đường này. Tránh cho rằng ứng dụng khởi động thành công nghĩa là mọi dependency được gọi động đều đã phân giải thành công.

## 12. Cân nhắc hiệu năng và tính quan sát

Provider không phải phương tiện tăng hiệu năng tự động. Mỗi lần gọi có thể cần bean resolution; một số lời gọi stream duyệt nhiều bean và có thể kích hoạt khởi tạo. Khi provider được gọi trong vòng lặp lớn hoặc request nóng, việc tra cứu liên tục có thể gây chi phí không cần thiết.

Có thể áp dụng:

- Nếu tập ứng viên cố định, inject `List<T>` hoặc thu snapshot `provider.orderedStream().toList()` một lần tại nơi phù hợp.
- Nếu cần tính động, chỉ gọi provider tại thời điểm thực sự cần; tránh gọi `getObject()` lặp lại mà không hiểu scope.
- Nếu hook chạy trên đường xử lý đồng bộ, xác định timeout, failure policy và trách nhiệm lỗi của từng hook; provider không tự cung cấp isolation/retry.
- Nếu "không có plugin" là trạng thái bình thường, ghi nhận qua log/metrics phù hợp ở tầng vận hành, nhưng không spam log trong mỗi request.
- Nếu "không có gateway" là sự cố cấu hình, để chương trình báo lỗi rõ; không đánh đồng với trạng thái tùy chọn.
- Đừng log thông tin nhạy cảm chỉ vì cần debug danh sách bean; xem metadata bean name là thông tin kỹ thuật, không phải dữ liệu nghiệp vụ.

**Chi phí test và maintainability** cũng là chi phí quan trọng. Một class có constructor `PaymentService(PaymentGateway gateway)` dễ test bằng một fake gateway; constructor `PaymentService(ApplicationContext context)` yêu cầu mock phức tạp hơn và người đọc phải dò phương thức nội bộ mới biết service thật sự dùng bean nào.

## 13. Kiểm thử để provider không che mất cấu hình sai

Một chiến lược test tốt phải kiểm tra **cả thiếu dependency hợp lệ lẫn thiếu dependency không hợp lệ**.

### 13.1. Thiếu optional hook phải thành công

Với `CoreConfig` ở ví dụ đầy đủ, context không đăng ký `PaymentHook` nào nhưng checkout vẫn trả receipt. Đây là một contract test cho extension point. Nếu một lần refactor làm code ném lỗi khi không có hook, test sẽ phát hiện.

### 13.2. Có nhiều hook phải chạy đúng thứ tự

Khi thêm `OptionalHooksConfig`, cả audit và metrics phải chạy. `@Order(10)` trước `@Order(20)`; test nên xác nhận **cả membership và thứ tự**, thay vì dựa vào thứ tự method khai báo hay component scan.

### 13.3. Thiếu gateway bắt buộc phải khiến context thất bại

Có thể thêm đoạn sau vào **cùng class `BoundedProviderDemo`** ở mục 5 để kiểm tra fail-fast bằng một configuration không khai báo gateway:

```java
// Đoạn bổ sung: khai báo bên trong BoundedProviderDemo.
@Configuration(proxyBeanMethods = false)
static class MissingGatewayConfig {
    @Bean
    PaymentService paymentService(PaymentGateway gateway) {
        return new PaymentService(gateway);
    }
}

static void verifyRequiredDependency() {
    try (var context = new AnnotationConfigApplicationContext(
            MissingGatewayConfig.class)) {
        throw new AssertionError("Context should reject missing gateway");
    } catch (org.springframework.beans.factory.UnsatisfiedDependencyException expected) {
        System.out.println("missing gateway rejected");
    }
}
```

Đây là **đoạn kiểm tra bổ sung**, không nằm trong output mặc định của `main()`. Muốn chạy, gọi `verifyRequiredDependency()` từ `main`. Nó cố tình tạo `PaymentService` mà không có `PaymentGateway`; khi Spring thất bại do thiếu dependency, ta bắt `UnsatisfiedDependencyException` và in:

```text
missing gateway rejected
```

Tùy logging configuration, Spring còn có thể ghi thông điệp chẩn đoán ra log. Đoạn thử nghiệm này chỉ hợp lệ khi context riêng thật sự **không đăng ký** bất kỳ `PaymentGateway` nào.

Trong unit test thuần Java, có thể tạo `PaymentService` bằng fake `PaymentGateway` và assert đầu ra; không cần Spring cho logic `pay`. Với `CheckoutFacade`, nên ưu tiên một abstraction như `PaymentHookDispatcher` nếu muốn unit test nghiệp vụ không phụ thuộc trực tiếp API Spring; integration test sẽ xác nhận adapter thực hiện lookup/orderedStream đúng hợp đồng.

### 13.4. Những trường hợp test không được bỏ sót

| Kịch bản | Kết quả kỳ vọng |
| --- | --- |
| Không có hook tùy chọn | Nghiệp vụ lõi hoàn tất, không gọi hook |
| Có một hook | Hook được gọi một lần tại thời điểm quy định |
| Có nhiều hook | Duyệt đầy đủ, đúng thứ tự/nhóm qualifier nếu có |
| Thiếu gateway bắt buộc | Context không tạo được service tương ứng |
| Có hai gateway cạnh tranh không phân giải được | Báo lỗi nhập nhằng, không âm thầm chọn ngẫu nhiên |
| Hook có bean nhưng khởi tạo thất bại | Lỗi được nhận diện là tạo bean thất bại, không giả làm "hook không tồn tại" |
| Hook ném lỗi khi chạy | Tác động tới checkout tuân theo chính sách lỗi đã thiết kế |
| Bean prototype/nhạy scope | Số lần tạo instance và thời điểm lookup được kiểm chứng |

Không cần mock mọi method của `ObjectProvider` để kiểm thử lớp nghiệp vụ. Với logic phức tạp, thường dễ hơn nếu giới hạn provider trong adapter và test adapter bằng Spring context nhỏ, còn service domain dùng interface thuần Java.

## 14. Checklist review mã nguồn

Khi review một constructor nhận `ObjectProvider<T>`, hãy trả lời:

1. **Vì sao cần provider?** Vì bean tùy chọn, vì có nhiều implementation, vì prototype/scope, vì lazy lookup, hay chỉ vì ngại khai báo dependency?
2. **Nếu không có bean `T` thì sao?** Chức năng chính có còn đúng không? Có fallback cụ thể, test và monitoring không?
3. **Nếu có nhiều bean `T` thì sao?** Cần tất cả, cần đúng một theo qualifier, hay cần registry theo khóa nghiệp vụ?
4. **Khi nào bean được lấy?** Lúc startup, lúc request, hay khi job chạy? Việc phát hiện lỗi bị trì hoãn đến mức nào?
5. **Nếu bean tạo lỗi hoặc chạy lỗi thì sao?** Code có phân biệt lỗi cấu hình/hạ tầng với vắng mặt hợp lệ không?
6. **Provider nằm ở lớp nào?** Ở adapter/factory/extension point hay lan vào domain service không cần biết Spring?
7. **Scope có được hiểu đúng không?** Singleton, prototype, request scope và lazy initialization có tạo ra hành vi mong muốn?
8. **Có thể dùng kiểu rõ hơn không?** `T` bắt buộc, `Optional<T>` tùy chọn một lần, `List<T>` nhóm cố định hoặc một interface factory/registry tường minh?
9. **Test có bao phủ thiếu/multiple bean không?** Đặc biệt kiểm thử rằng thiếu dependency cốt lõi phải gây lỗi.
10. **Người mới đọc constructor có hiểu service cần gì không?** Nếu phải vào từng method mới thấy service tìm gì từ context, thiết kế có thể đã ẩn dependency.

Checklist không đồng nghĩa "provider là xấu". Một provider được đặt đúng chỗ, có hợp đồng rõ, giới hạn phạm vi và kiểm thử hành vi thiếu bean là một công cụ hữu ích của Spring Core Container.

## 15. Lỗi thường gặp và cách sửa

| Biểu hiện | Sai lầm | Hướng khắc phục |
| --- | --- | --- |
| Ứng dụng khởi động nhưng thanh toán lỗi khi có đơn | `PaymentGateway` bắt buộc bị giấu trong provider | Constructor inject `PaymentGateway` trực tiếp |
| Thiếu bean mà code tiếp tục như thành công | `getIfAvailable()`/`ifAvailable()` bỏ qua hành động bắt buộc | Fail fast hoặc ném lỗi nghiệp vụ rõ ràng; kiểm thử trường hợp thiếu |
| `getIfAvailable()` vẫn ném exception | Có nhiều ứng viên không phân giải được hoặc bean tạo lỗi | Sửa qualifier/primary/bean factory; không giả định "if available" nuốt mọi lỗi |
| Không gọi đủ plugin | Dùng `getIfUnique()` cho extension point 0..n | Dùng `stream()`/`orderedStream()` khi cần mọi plugin |
| Unit test buộc khởi động Spring | Domain class giữ `ApplicationContext` và tự tra cứu bean | Constructor inject interface nghiệp vụ; giới hạn provider trong adapter/factory |
| Service A/B phụ thuộc vòng vẫn khó hiểu | Dùng provider chỉ để né lỗi circular dependency | Tách trách nhiệm, dùng orchestration/event khi phù hợp |
| Rule chạy sai thứ tự | Gọi `stream()` rồi phụ thuộc thứ tự đăng ký | Dùng `orderedStream()` và metadata `@Order` rõ |
| Tưởng dùng provider nghĩa là luôn tạo bean mới | Không xem bean scope | Phân biệt singleton/prototype/scoped proxy |
| Lỗi xuất hiện rất muộn | Provider trì hoãn lookup một dependency cốt lõi | Tiêm trực tiếp hoặc thêm startup/integration validation |
| Khó đo lỗi plugin | Bắt `Exception` và bỏ qua toàn bộ | Chính sách retry/fallback/log/metrics cụ thể theo loại hook |

## 16. Bài tập và đáp án định hướng

**Bài 1 — Chọn đúng kiểu phụ thuộc.** Một `ReportService` **bắt buộc** cần `ReportRepository` để lưu báo cáo, nhưng có thể gửi metric sang `MetricsSink` nếu bean này được đăng ký. Constructor nào diễn đạt hợp đồng tốt hơn?

```java
// Lựa chọn A
ReportService(ObjectProvider<ReportRepository> repository,
              ObjectProvider<MetricsSink> metrics) { }

// Lựa chọn B
ReportService(ReportRepository repository,
              java.util.Optional<MetricsSink> metrics) { }
```

**Đáp án:** B hợp lý khi metrics là tùy chọn được phân giải một lần. Repository là dependency bắt buộc nên constructor có thể phát hiện thiếu bean sớm. Nếu metrics thực sự cần lookup động/lazy, vẫn có thể dùng provider **chỉ cho metrics**.

**Bài 2 — Nhiều bean.** Nếu ứng dụng có ba `AuditHook` cùng kiểu và cần chạy cả ba, gọi `provider.getIfAvailable()` có đúng ý nghĩa không?

**Đáp án:** Không. Method này muốn trả một bean; khi nhiều ứng viên không chọn được duy nhất có thể ném exception. Với hook 0..n, dùng `stream()` hoặc `orderedStream()` tùy yêu cầu thứ tự.

**Bài 3 — Provider che lỗi.** Một service gọi `getIfUnique()` cho `FraudDetector`. Khi có hai detector không có ứng viên thắng, service nhận `null` rồi bỏ qua phát hiện gian lận. Lỗi nằm ở đâu?

**Đáp án:** Nếu phát hiện gian lận là bước bắt buộc, thiếu hoặc nhập nhằng detector phải được xem là sai cấu hình. Nên khai báo dependency bắt buộc, chọn đúng detector bằng qualifier/primary, hoặc thiết kế pipeline nhiều detector rõ ràng. Không dùng `null` làm "cho qua".

**Bài 4 — Prototype.** Mỗi job cần một `JobWorker` mới có state riêng. Có thể inject thẳng một `JobWorker` prototype vào singleton manager rồi gọi nhiều lần để luôn có worker mới không?

**Đáp án:** Không nên mặc định như vậy: dependency của singleton thường được phân giải lúc singleton được tạo, nên manager có thể giữ cùng một worker. Provider hoặc factory lấy prototype tại mỗi job phù hợp hơn, với scope được cấu hình đúng.

**Bài 5 — Ranh giới thiết kế.** Nếu mười service cùng giữ `ObjectProvider<PaymentGateway>` để gọi `getObject()` trước khi thu tiền, refactor như thế nào?

**Đáp án:** Trước hết xác định liệu mỗi service thật sự cần gateway. Chuyển dependency bắt buộc thành `PaymentGateway` hoặc một abstraction nghiệp vụ như `Payments` qua constructor. Nếu chỉ một adapter cần lazy/prototype semantics, giữ provider **bên trong adapter/factory đó**, cung cấp API thuần Java cho phần còn lại. Viết test xác nhận thiếu gateway là lỗi, không phải thành công.

## Kết luận

`ObjectProvider<T>` là công cụ **linh hoạt hóa thời điểm và cách phân giải bean**, không phải giấy phép biến mọi dependency thành tùy chọn. Giữ phụ thuộc bắt buộc dưới dạng constructor parameter kiểu `T` để lỗi cấu hình lộ ra sớm. Dùng provider cho extension point 0..n bean, lazy/prototype lookup hoặc factory/registry thật sự cần truy vấn động; giới hạn nó tại ranh giới hạ tầng có trách nhiệm rõ.

Trước khi thêm provider, hãy mô tả chính xác hành vi khi **không có**, **có một**, **có nhiều**, hoặc **có bean nhưng tạo/chạy lỗi**. Nếu những điều kiện đó chưa rõ, tăng mức "linh hoạt" bằng provider có thể làm giảm khả năng hiểu, kiểm thử và vận hành của hệ thống.

## Tài liệu tham khảo

- [Spring Framework — ObjectProvider API (6.2)](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/ObjectProvider.html): `getObject()`, `getIfAvailable()`, `getIfUnique()`, `stream()`, `orderedStream()` và các điều kiện chọn bean.
- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html): constructor injection, dependency bắt buộc và tùy chọn, collection injection.
- [Spring Framework — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html): cách ràng buộc ứng viên theo qualifier.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): singleton, prototype và các scope khác.
- [Spring Framework — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html): sự khác nhau giữa lazy initialization và dependency resolution.
