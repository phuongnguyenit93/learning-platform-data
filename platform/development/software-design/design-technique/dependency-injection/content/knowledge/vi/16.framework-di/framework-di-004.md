# Vai trò của cấu hình Java, phương thức tạo đối tượng và đăng ký tường minh

> **Chương:** DI trong framework  
> **Bối cảnh:** Dependency Injection (DI) và Inversion of Control (IoC) giúp tách việc *sử dụng* dependency khỏi việc *tạo và lắp ghép* đối tượng. Bài học đi từ constructor injection và composition root bằng Java thuần đến cách DI container tiếp nhận cấu hình Java, factory method và đăng ký bean tường minh.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **cấu hình Java** giữ vai trò gì trong việc định nghĩa object graph của một DI container.
2. Phân biệt **phương thức tạo đối tượng** (factory method), **phương thức đăng ký bean** và **phương thức nghiệp vụ**.
3. Hiểu sự khác nhau giữa đăng ký thông qua `@Configuration`/`@Bean`, đăng ký bằng API lập trình và quét tự động (`component scanning`).
4. Nhận biết vì sao dùng `new` trong một phương thức `@Bean` khác với dùng `new` trong code nghiệp vụ, và khi nào một instance được container quản lý.
5. Thực hành cấu hình và constructor injection bằng **Java thuần**, rồi đọc cách viết tương ứng bằng Spring.
6. Cân nhắc phạm vi sống (`scope`), quyền sở hữu tài nguyên (`ownership`), callback vòng đời, việc chọn implementation và kiểm thử khi lắp ghép bằng framework.

## 2. Bài toán: nơi nào quyết định sử dụng lớp cụ thể?

Giả sử `OrderService` cần một đối tượng gửi thông báo. Ở môi trường demo, ta dùng `ConsoleMessageSender`; về sau có thể thay bằng adapter HTTP hoặc email. Lớp nghiệp vụ chỉ cần biết hợp đồng `MessageSender`.

Nếu tự tạo adapter trong service:

```java
// Phản ví dụ: OrderService quyết định cả nghiệp vụ lẫn hạ tầng.
final class OrderService {
    private final MessageSender sender = new ConsoleMessageSender();

    void confirm(String orderId) {
        sender.send(orderId, "Đơn hàng đã xác nhận");
    }
}
```

ta đã gắn một quyết định về **lớp cụ thể** vào code nghiệp vụ. Việc đổi adapter có thể buộc sửa `OrderService`, còn kiểm thử cần kiểm soát cả console hoặc dịch vụ ngoài.

Thiết kế tách trách nhiệm hơn:

```java
final class OrderService {
    private final MessageSender sender;

    OrderService(MessageSender sender) {
        this.sender = java.util.Objects.requireNonNull(sender, "sender");
    }

    void confirm(String orderId) {
        sender.send(orderId, "Đơn hàng đã xác nhận");
    }
}
```

Service yêu cầu một `MessageSender` qua constructor, nhưng **không chọn implementation**. Một thành phần bên ngoài quyết định sẽ truyền instance nào. Phần **chọn, tạo, cấu hình, kết nối và khởi động** các thành phần này được gọi chung là công việc của **composition root**.

Với Java thuần, root có thể viết trực tiếp bằng `new`. Với một DI container, root cung cấp **định nghĩa/đăng ký** để container thực hiện phần lớn việc lắp ghép. **Cấu hình Java** là một cách diễn đạt những quyết định ấy bằng code Java, thay vì chỉ bằng XML hay quy ước quét class.

## 3. Java thuần trước: factory method tại composition root

Ta có thể hiểu vai trò của cấu hình framework bằng cách tự viết code lắp ghép. Ví dụ sau **chạy được chỉ với JDK**, không cần Spring hoặc thư viện DI nào.

Tạo `Main.java`:

```java
import java.util.Objects;

interface MessageSender {
    void send(String recipient, String message);
}

final class ConsoleMessageSender implements MessageSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("SEND " + recipient + ": " + message);
    }
}

final class AuditedMessageSender implements MessageSender {
    private final MessageSender delegate;

    AuditedMessageSender(MessageSender delegate) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
    }

    @Override
    public void send(String recipient, String message) {
        delegate.send(recipient, message);
        System.out.println("AUDIT " + recipient);
    }
}

final class OrderService {
    private final MessageSender sender;

    OrderService(MessageSender sender) {
        this.sender = Objects.requireNonNull(sender, "sender");
    }

    void confirm(String orderId) {
        if (orderId == null || orderId.trim().isEmpty()) {
            throw new IllegalArgumentException("orderId is required");
        }
        sender.send(orderId, "Đơn hàng đã xác nhận");
    }
}

// Tập trung các phương thức tạo và lắp ghép.
final class JavaWiring {
    private JavaWiring() {}

    static MessageSender messageSender(boolean audited) {
        MessageSender base = new ConsoleMessageSender();
        return audited ? new AuditedMessageSender(base) : base;
    }

    static OrderService orderService(MessageSender sender) {
        return new OrderService(sender);
    }
}

public class Main {
    public static void main(String[] args) {
        boolean audited = args.length > 0 && "audited".equals(args[0]);

        // Composition root: tạo dependency trước rồi tạo consumer.
        MessageSender sender = JavaWiring.messageSender(audited);
        OrderService orders = JavaWiring.orderService(sender);
        orders.confirm("ORD-101");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 Main.java
java Main
java Main audited
```

Lần chạy mặc định:

```text
SEND ORD-101: Đơn hàng đã xác nhận
```

Lần chạy với `audited`:

```text
SEND ORD-101: Đơn hàng đã xác nhận
AUDIT ORD-101
```

Hai phương thức của `JavaWiring` có **vai trò tạo/lắp ghép**, không phải xử lý nghiệp vụ. Chúng quyết định lớp cụ thể, còn `OrderService` chỉ làm việc qua `MessageSender`.

Đây đã là **constructor injection** và **IoC ở mức lắp ghép**, dù không hề có container. Việc dùng framework về sau chủ yếu giúp tự động hóa và chuẩn hóa một phần công việc lặp lại khi object graph lớn.

## 4. Cấu hình Java trong DI framework là gì?

Trong Spring, có thể khai báo những quyết định lắp ghép bằng một lớp `@Configuration` và các phương thức `@Bean`.

Ý tưởng gần giống `JavaWiring`, nhưng khác ở điểm quan trọng: **container đọc các khai báo này, đăng ký bean definition, gọi factory method khi cần, xử lý injection và scope theo cấu hình**. Giá trị trả về từ một phương thức `@Bean` là bean được đăng ký trong context tương ứng.

### 4.1. Ví dụ Spring dùng cùng các lớp nghiệp vụ

Ví dụ dưới đây cần các thư viện Spring phù hợp (đặc biệt `spring-context` và các dependency liên quan). **Nó không chạy chỉ bằng JDK trống**. Giả sử các kiểu `MessageSender`, `ConsoleMessageSender` và `OrderService` được định nghĩa như trong `Main.java` ở mục 3 và cùng package.

Tạo `SpringMain.java`:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SpringMain {
    @Configuration(proxyBeanMethods = false)
    static class ApplicationConfiguration {
        @Bean
        MessageSender messageSender() {
            return new ConsoleMessageSender();
        }

        @Bean
        OrderService orderService(MessageSender sender) {
            return new OrderService(sender);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             ApplicationConfiguration.class)) {

            OrderService orders = context.getBean(OrderService.class);
            orders.confirm("ORD-101");
        }
    }
}
```

Ở đây:

1. `ApplicationConfiguration` mô tả **các quyết định wiring** bằng Java.
2. `messageSender()` là **factory method đăng ký bean `MessageSender`**. Phương thức trả về một đối tượng cụ thể `ConsoleMessageSender`.
3. `orderService(MessageSender sender)` là một factory method khác. Container **cung cấp tham số `sender`** khi tạo bean `OrderService`, dựa trên các binding hiện có.
4. `SpringMain.main` khởi tạo context và lấy service đã hoàn tất lắp ghép để bắt đầu công việc.
5. Đóng context ở cuối `try-with-resources` kích hoạt quy trình shutdown của context và các callback hủy phù hợp cho bean mà nó quản lý.

Điểm cốt lõi nằm ở **tham số của factory method**:

```java
@Bean
OrderService orderService(MessageSender sender) {
    return new OrderService(sender);
}
```

Nhờ tham số `MessageSender sender`, phương thức **không cần tự gọi `messageSender()`**. Container có thể giải quyết dependency đúng theo scope, qualifier và binding đã cấu hình. Cách này làm các cạnh phụ thuộc được mô tả tường minh hơn.

> **Phân biệt:** `new ConsoleMessageSender()` **bên trong phương thức `@Bean` được container gọi và đăng ký kết quả** không giống `new ConsoleMessageSender()` trong một business service rồi giữ riêng. Trường hợp thứ nhất trả về instance tham gia vào cơ chế quản lý của container; trường hợp thứ hai thông thường không tự đăng ký instance đó làm bean.

### 4.2. Cấu hình Java không yêu cầu component scanning

`@ComponentScan` cho phép Spring tìm các lớp có annotation stereotype thích hợp để đăng ký. Tuy nhiên, dùng `@Bean` trong `@Configuration` là cách **đăng ký tường minh**: ta chủ động nêu ra kiểu và cách tạo.

Một số tình huống đặc biệt phù hợp với đăng ký tường minh:

- Adapter từ **thư viện bên thứ ba** không thể thêm `@Component`.
- Implementation cần tham số khởi tạo phức tạp: URL, timeout, credential, pool, SSL hoặc cấu hình môi trường.
- Muốn chọn một triển khai khác giữa demo/test và runtime thực tế.
- Muốn xem **object graph quan trọng** tại một chỗ thay vì suy từ các annotation rải trong code.
- Cần cấu hình rõ cách tạo, phạm vi chia sẻ hoặc đóng tài nguyên.

Quét tự động và `@Bean` **không đối lập tuyệt đối**. Một ứng dụng có thể dùng cả hai: quét các service đơn giản, đăng ký tường minh những adapter hoặc resource cần kiểm soát chi tiết.

## 5. Phương thức tạo đối tượng làm những việc gì?

Một factory method không chỉ là nơi đặt `new`. Nó là **điểm xây dựng dependency phù hợp hợp đồng**, có thể bao gồm:

| Công việc | Ví dụ | Điều cần tránh |
| --- | --- | --- |
| **Chọn lớp cụ thể** | Chọn adapter console hoặc adapter HTTP theo cấu hình. | Đưa nhánh môi trường vào nghiệp vụ. |
| **Truyền dependency** | Nhận `MessageSender` làm tham số rồi tạo `OrderService`. | Tự tra cứu container sâu trong service. |
| **Cấu hình instance** | Truyền timeout, endpoint, policy retry ở bootstrap. | Để từng request sửa cấu hình dùng chung tùy tiện. |
| **Thiết lập scope** | Singleton, prototype, request scope nếu môi trường hỗ trợ. | Giả định một instance ngắn hạn phù hợp mọi nơi dùng. |
| **Khai báo vòng đời** | Đăng ký cách hủy resource có `close()` hoặc `shutdown()`. | Để consumer không phải owner tự đóng dependency. |
| **Xác thực cấu hình** | Từ chối thiếu URL/khóa, mode không hợp lệ. | Im lặng dùng fallback nguy hiểm ngoài ý định. |

Nên giữ các factory method **dễ hiểu và có trách nhiệm rõ**. Phương thức tạo `OrderService` không nên thực hiện đơn hàng thật, gửi thông báo, trừ tiền hoặc xử lý logic nghiệp vụ phát sinh từ request.

### 5.1. Tham số của `@Bean` là một dạng injection

Spring có thể giải quyết tham số của phương thức `@Bean` từ context:

```java
// Minh họa, PaymentGateway và PaymentService là các kiểu giả định.
@Bean
PaymentService paymentService(PaymentGateway gateway) {
    return new PaymentService(gateway);
}
```

Đây là **method parameter injection tại điểm tạo bean**; kết quả vẫn có thể tuân theo constructor injection của lớp `PaymentService`. Không nên nhầm nó với việc mỗi lần gọi phương thức nghiệp vụ đều được container tự cung cấp tham số.

Nếu có nhiều bean cùng kiểu, container có thể không biết chọn bean nào. Ta cần mô tả lựa chọn rõ hơn, ví dụ thông qua qualifier hoặc chính sách ưu tiên của framework.

### 5.2. Khi có nhiều implementation cùng interface

Ví dụ Spring sau minh họa đặt tên và chọn đúng bean bằng `@Qualifier`; các kiểu `MessageSender`, `ConsoleMessageSender`, `AuditedMessageSender`, `OrderService` vẫn lấy từ mục 3:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class NotificationConfiguration {
    @Bean("consoleSender")
    MessageSender consoleSender() {
        return new ConsoleMessageSender();
    }

    @Bean("auditedSender")
    MessageSender auditedSender(
            @Qualifier("consoleSender") MessageSender base) {
        return new AuditedMessageSender(base);
    }

    @Bean
    OrderService orderService(
            @Qualifier("auditedSender") MessageSender sender) {
        return new OrderService(sender);
    }
}
```

Trong ví dụ này, hai bean `MessageSender` có thể cùng tồn tại. `@Qualifier` nói rõ **bean nào được dùng tại từng cạnh của object graph**, tránh dựa vào thứ tự đăng ký.

Một cách khác của Spring là `@Primary` khi có một implementation mặc định ưu tiên. Nhưng nếu sự lựa chọn là quyết định quan trọng về môi trường hoặc nghiệp vụ, cấu hình rõ tên/qualifier thường dễ rà soát hơn việc ngầm đoán.

## 6. Đăng ký tường minh không nhất thiết phải dùng annotation

Đăng ký bằng `@Bean` là **đăng ký khai báo thông qua cấu hình Java**. Ngoài ra, một số framework cung cấp API **đăng ký theo lập trình**.

Trong Spring, `AnnotationConfigApplicationContext` có API `registerBean(...)`. Ta có thể dùng nó ở **composition root** khi cần tạo binding động hoặc cấu hình tối giản.

Ví dụ minh họa (phụ thuộc Spring; dùng các class `MessageSender`, `ConsoleMessageSender` và `OrderService` đã định nghĩa):

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class ProgrammaticMain {
    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.registerBean(
                    MessageSender.class,
                    ConsoleMessageSender::new);

            context.registerBean(
                    OrderService.class,
                    () -> new OrderService(
                            context.getBean(MessageSender.class)));

            context.refresh();

            context.getBean(OrderService.class).confirm("ORD-102");
        }
    }
}
```

Điều quan trọng:

- `registerBean(...)` **đăng ký bean definition cùng supplier**; khi container tạo bean, supplier trả về instance đã được lắp ghép theo code của ta.
- `refresh()` hoàn tất giai đoạn khởi tạo context theo mô hình này.
- `context.getBean(...)` ở trên xuất hiện **chỉ trong code wiring tại composition root/supplier khởi tạo**, không phải trong `OrderService`.
- Một số API đăng ký **instance có sẵn** (khác với đăng ký bean definition) có quy tắc riêng về post-processing và destruction. Không thể suy rằng mọi dạng đăng ký đều mang lại lifecycle/proxy giống nhau.

**So sánh lựa chọn:** `@Bean` với tham số tường minh thường dễ đọc hơn khi object graph ổn định. `registerBean(...)` hữu ích khi cấu hình cần sinh động theo điều kiện runtime hoặc module plugin, nhưng dùng đại trà có thể làm quan hệ phụ thuộc khó thấy hơn. Chọn cách đơn giản phù hợp bối cảnh.

> **Cảnh báo về Service Locator:** Dùng `context.getBean(...)` trong **bootstrap** để ghép đối tượng có thể chấp nhận được. Gọi `context.getBean(...)` trong từng phương thức nghiệp vụ để lấy tùy ý repository/gateway/logger sẽ giấu dependency thật, khiến service phụ thuộc trực tiếp container.

## 7. Một chi tiết dễ nhầm: gọi trực tiếp phương thức `@Bean`

Xét cách viết:

```java
@Bean
MessageSender messageSender() {
    return new ConsoleMessageSender();
}

@Bean
OrderService orderService() {
    return new OrderService(messageSender());
}
```

Đoạn này **có sự khác biệt theo cơ chế cấu hình của Spring**:

- Với **full `@Configuration` được tăng cường proxy mặc định** (`proxyBeanMethods = true`), Spring có thể chặn lời gọi giữa các phương thức `@Bean` để trả bean do context quản lý theo quy tắc scope.
- Với **`@Configuration(proxyBeanMethods = false)`** hoặc các trường hợp phương thức `@Bean` không được proxy theo cách đó, `messageSender()` chỉ là lời gọi Java bình thường; nó có thể tạo **thêm một instance** ngoài instance container đang quản lý.
- Lời gọi `messageSender()` từ một object cấu hình do code tự `new` cũng không mặc nhiên có ngữ nghĩa gọi qua proxy của Spring.

Nếu ta muốn `OrderService` dùng chính bean `MessageSender` mà container quản lý, cách **không phụ thuộc cơ chế intercept lời gọi method** là khai báo dependency tại tham số:

```java
@Bean
OrderService orderService(MessageSender sender) {
    return new OrderService(sender);
}
```

Đây cũng là một lợi thế về khả năng đọc: chữ ký của phương thức `@Bean` mô tả ngay dependency cần giải quyết.

**Không nên** tự gọi lại một bean-creating method nhiều lần trong code nghiệp vụ rồi giả định nó luôn trả singleton; nếu cần instance do container quản lý, hãy nhận bean qua DI.

## 8. Scope và vòng đời: cấu hình chịu trách nhiệm đến đâu?

Container có thể quản lý nhiều scope; trong Spring, **singleton là scope mặc định** của bean trong một context. Điều đó không phải lời hứa rằng đối tượng luôn bất biến hoặc an toàn đa luồng. Đây là hai khía cạnh riêng:

| Khía cạnh | Ví dụ | Cần xác định |
| --- | --- | --- |
| **Singleton** | Một `MessageSender` được dùng chung trong context. | Adapter có an toàn khi nhiều request gọi đồng thời không? |
| **Prototype** | Mỗi lần container được yêu cầu tạo bean sẽ có instance mới. | Ai chịu trách nhiệm dọn dẹp từng instance sau khi nhận? |
| **Request scope** | Một object sống trong một HTTP request khi web context hỗ trợ. | Có bị giữ lại sau request bởi singleton hoặc task async không? |
| **Resource lifecycle** | Pool/HTTP client/executor cần `close()` hoặc `shutdown()`. | Container có thực sự sở hữu resource và biết đúng callback hủy không? |
| **Đối tượng từ factory riêng** | Một bean factory trả `new Task(...)` trong method. | Task trả về có được đăng ký vào container hay vẫn do caller/factory sở hữu? |

### 8.1. Bean `prototype` không có nghĩa “mỗi method call là một instance mới”

Khi một bean `prototype` được inject trực tiếp vào constructor của **singleton**, dependency thường được giải quyết **tại lúc singleton được tạo**, không tự tạo lại mỗi khi singleton xử lý một request.

Nếu cần đối tượng mới mỗi thao tác, có thể sử dụng một **factory/provider được định kiểu rõ**, ví dụ `ObjectProvider<ReportSession>` trong Spring hoặc một interface `ReportSessionFactory` của ứng dụng.

Provider cần có contract: gọi `get()` có tạo mới không, có ngoại lệ không, object thuộc scope nào, ai đóng nếu nó chứa tài nguyên. Tránh thay mọi dependency bằng một provider tổng quát có khả năng tra cứu mọi bean.

### 8.2. Container không tự đóng mọi resource từng xuất hiện

Nếu container quản lý một bean là resource, có thể khai báo callback hủy phù hợp:

```java
// Minh họa Spring; ManagedTransport là kiểu AutoCloseable giả định.
@Bean(destroyMethod = "close")
ManagedTransport transport() {
    return new ManagedTransport(/* cấu hình hạ tầng */);
}
```

Ý nghĩa là khai báo cách đóng **bean do context quản lý** khi vòng đời thích hợp kết thúc. Đoạn này là ví dụ cấu hình, không phải mã Java thuần chạy độc lập vì `ManagedTransport` chưa được định nghĩa.

Đồng thời:

- Một bean được cấp cho consumer không có nghĩa **consumer sở hữu quyền đóng**; thường consumer chỉ mượn dependency dùng chung.
- Một resource mà một service tự tạo bên trong method không nhất thiết được container biết để đóng.
- Spring **không tự động thực hiện callback hủy từng prototype sau khi bàn giao cho caller** theo cùng cơ chế của singleton.
- Nếu factory trả một connection/session ngắn hạn, caller hoặc scope manager có thể chịu trách nhiệm `close()`, dù bản thân factory là bean.

Nguyên tắc từ Java thuần không thay đổi: **ai tạo, ai sử dụng, ai sở hữu và ai đóng** phải được quy định rõ.

### 8.3. Thứ tự shutdown và tác vụ bất đồng bộ

Nếu bean có executor hoặc resource phục vụ tác vụ nền, đóng context **trước khi các task kết thúc** có thể khiến task tiếp tục truy cập dependency đã đóng. Cần thiết kế shutdown: ngừng nhận công việc mới, đợi/hủy công việc còn chạy theo chính sách, rồi đóng resource nền.

Đây là trách nhiệm về lifecycle của toàn ứng dụng, không tự được giải quyết bởi việc một class có `@Bean`.

## 9. Khi nào nên ưu tiên cấu hình Java và đăng ký tường minh?

Cấu hình tường minh đặc biệt hữu ích khi:

1. **Có nhiều implementation** của một interface và cần biết chính xác implementation nào được inject.
2. **Tích hợp thư viện ngoài** với constructor hoặc builder phức tạp.
3. **Cấu hình khác nhau theo môi trường**, cần xác thực các tham số trước khi khởi động.
4. **Resource có lifecycle** rõ như connection pool, client, scheduler hoặc executor.
5. **Muốn test composition root** để phát hiện thiếu binding/nhầm qualifier sớm.
6. **Hệ thống có module tách biệt**, cần định nghĩa ranh giới bean và trách nhiệm tạo object graph.

Ngược lại, quét component có thể giảm boilerplate cho những lớp đơn giản, độc lập, chỉ cần constructor injection. Không phải mọi bean đều cần một factory method riêng nếu việc tạo của chúng đã hoàn toàn tường minh và không có quyết định cấu hình đáng kể.

### 9.1. Cấu hình tường minh không có nghĩa viết `new` ở mọi nơi

Những câu lệnh `new` để tạo adapter nên được tập trung trong root/configuration/factory do root điều phối. Việc tạo **đối tượng dữ liệu** như `new OrderLine(...)` hoặc `new Money(...)` trong nghiệp vụ vẫn có thể hoàn toàn hợp lý.

Hãy tránh đưa logic “đơn được miễn phí vận chuyển khi nào” hay “tính thuế bao nhiêu” vào các phương thức `@Bean`. Cấu hình mô tả **cách xây dịch vụ**, không phải **dịch vụ giải quyết yêu cầu thế nào**.

## 10. Kiểm thử: tách unit test nghiệp vụ và test wiring

Service được thiết kế bằng constructor injection có thể được kiểm thử **mà không chạy Spring**. Giữ `Main.java` ở mục 3, tạo `OrderServiceTest.java`:

```java
final class RecordingSender implements MessageSender {
    int count;
    String lastRecipient;
    String lastMessage;

    @Override
    public void send(String recipient, String message) {
        count++;
        lastRecipient = recipient;
        lastMessage = message;
    }
}

public class OrderServiceTest {
    public static void main(String[] args) {
        RecordingSender fake = new RecordingSender();
        OrderService service = new OrderService(fake);

        service.confirm("ORD-A");
        check(fake.count == 1, "Must send exactly once");
        check("ORD-A".equals(fake.lastRecipient), "Wrong recipient");
        check("Đơn hàng đã xác nhận".equals(fake.lastMessage),
                "Wrong message");

        boolean invalidRejected = false;
        try {
            service.confirm(" ");
        } catch (IllegalArgumentException expected) {
            invalidRejected = true;
        }
        check(invalidRejected, "Blank orderId must be rejected");
        check(fake.count == 1, "Invalid order must not send");

        boolean missingDependencyRejected = false;
        try {
            new OrderService(null);
        } catch (NullPointerException expected) {
            missingDependencyRejected = true;
        }
        check(missingDependencyRejected, "Sender is required");

        System.out.println("PASS");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

```bash
javac -encoding UTF-8 Main.java OrderServiceTest.java
java OrderServiceTest
```

Kết quả mong đợi: `PASS`. Test này kiểm tra **hành vi của `OrderService` với fake**, không cần context của Spring.

Để kiểm tra cấu hình framework, cần một **test wiring** hoặc **smoke test context** riêng:

- Context có khởi tạo thành công với cấu hình đã cho không?
- Bean `OrderService` có nhận đúng `MessageSender` mong muốn không?
- Khi có nhiều bean cùng kiểu, qualifier/primary có chọn đúng bean không?
- Có resource nào cần cleanup mà context chưa có callback hủy không?
- Scope có phù hợp với cách chia sẻ object và nhiệm vụ đồng thời không?

**Đừng dùng mỗi unit test nghiệp vụ để kết luận cấu hình Spring đúng.** Unit test chỉ xác nhận lớp hoạt động khi dependency được cung cấp; wiring test xác nhận container cung cấp đúng object graph.

## 11. Các lỗi điển hình khi dùng cấu hình Java

### 11.1. Quên đăng ký cấu hình

Viết một lớp `@Configuration` không có nghĩa mọi context trong JVM đều tự nhìn thấy lớp đó. Ứng dụng phải có cơ chế **đăng ký hoặc quét** cấu hình phù hợp. Với `AnnotationConfigApplicationContext(ApplicationConfiguration.class)` ở mục 4, lớp cấu hình được truyền tường minh.

### 11.2. Nhầm instance tự tạo với bean được container quản lý

`new OrderService(sender)` trong một service khác không tự tạo ra một bean của context. Trái lại, `new OrderService(sender)` trong phương thức `@Bean` mà container gọi để đăng ký kết quả **có thể** trở thành managed bean. Không đồng nhất hai trường hợp.

### 11.3. Truyền sai implementation khi có nhiều bean

Khi hai bean cùng thực hiện `MessageSender`, inject chỉ theo kiểu có thể gây mơ hồ. Dùng qualifier, tên bean, primary hoặc thiết kế factory chuyên biệt theo đúng ngữ cảnh.

### 11.4. Gọi trực tiếp method `@Bean` rồi giả định luôn lấy singleton

Hành vi phụ thuộc chế độ proxy của `@Configuration` và cách method được gọi. Dùng **tham số factory method** để nhận đúng dependency do container giải quyết; tránh ràng buộc logic vào cơ chế interceptor ngầm.

### 11.5. Đăng ký factory mà quên lifecycle của sản phẩm

Container có thể quản lý `TaskFactory`, nhưng các `Task` do factory tự `new` bên trong `create()` **không mặc nhiên** được đăng ký thành bean và nhận đầy đủ callback hủy/proxy/scope tương ứng.

### 11.6. Coi đăng ký có sẵn và tạo bean definition là một

Một API đăng ký **existing singleton instance** có thể bỏ qua các bước khởi tạo/post-processing thông thường hoặc có quy tắc đóng riêng. Không suy từ tên “register” rằng mọi dạng đăng ký đều có cùng ý nghĩa.

### 11.7. Cài Service Locator vào code nghiệp vụ

Một `OrderService` tự gọi `applicationContext.getBean(PaymentGateway.class)` che mất dependency thật và gắn nghiệp vụ vào framework. Hãy chuyển việc resolve đó về bootstrap hoặc cấu hình, và truyền gateway qua constructor.

### 11.8. Tưởng container tự sửa vòng phụ thuộc hoặc sai scope

Container có thể phát hiện một số vòng constructor, nhưng nó không thay việc phân chia trách nhiệm. Tương tự, inject được một request-scoped dependency vào thành phần sống lâu **không chứng minh** việc dùng nó sau request hợp lệ. Scope và logic phải được thiết kế chủ động.

## 12. Quy trình chuyển từ Java thuần sang cấu hình framework

Một lộ trình an toàn:

1. **Xác định hợp đồng phụ thuộc:** ví dụ `OrderService(MessageSender sender)`; giữ constructor rõ ràng.
2. **Viết và chạy test Java thuần:** chứng minh service hoạt động với fake.
3. **Đặt việc chọn adapter ở composition root:** có thể dùng các phương thức factory Java như `JavaWiring.messageSender(...)`.
4. **Chuyển quyết định lắp ghép sang cấu hình framework:** dùng `@Configuration`/`@Bean` hoặc API đăng ký tường minh.
5. **Để container giải quyết dependency qua tham số:** tránh lạm dụng lời gọi trực tiếp các phương thức tạo bean.
6. **Khai báo scope/lifecycle:** đối tượng dùng chung, resource cần đóng, factory trả object ngắn hạn, xử lý shutdown.
7. **Kiểm tra wiring bằng context test:** phát hiện thiếu bean, nhiều implementation chưa phân biệt, cấu hình sai.
8. **Giữ code nghiệp vụ độc lập framework nếu có thể:** adapter và phần khởi động biết framework; use case biết các hợp đồng cần dùng.

Quy trình này cho thấy DI container là **công cụ lắp ghép**, không phải điều kiện cần để có DI. Khi object graph còn đơn giản, Java thuần có thể là phương án đủ tốt; framework có lợi rõ hơn khi số lượng bean, cấu hình môi trường và yêu cầu lifecycle lớn lên.

## 13. Bài tập tự luyện

**Bài 1 — Xác định vai trò.** Trong ví dụ `SpringMain`, phương thức `messageSender()` và `orderService(MessageSender sender)` đóng vai trò gì? Ai gọi chúng và ai chịu trách nhiệm bắt đầu xử lý đơn hàng?

**Bài 2 — Phân biệt hai lệnh `new`.** So sánh `return new ConsoleMessageSender()` trong `@Bean` với `new ConsoleMessageSender()` bên trong `OrderService.confirm(...)`. Instance nào có thể được container quản lý, vì sao?

**Bài 3 — Lựa chọn implementation.** Đã đăng ký `consoleSender` và `auditedSender` cùng kiểu `MessageSender`. Hãy viết một phương thức `@Bean` tạo `OrderService` và chọn tường minh `auditedSender` bằng `@Qualifier`.

**Bài 4 — Scope.** Một singleton service được inject trực tiếp bean `prototype`. Mỗi lần gọi method của singleton có tự nhận một prototype mới không? Nếu cần phiên mới mỗi request, nên thay thiết kế ra sao?

**Bài 5 — Vòng đời.** Một phương thức `@Bean` tạo HTTP client dùng chung. Hai service sử dụng client; service đầu tiên gọi `close()` sau mỗi request. Chỉ ra lỗi ownership và cách cấu hình hoặc tổ chức shutdown hợp lý.

**Bài 6 — Proxy.** Với `@Configuration(proxyBeanMethods = false)`, việc gọi trực tiếp một phương thức `@Bean` từ phương thức `@Bean` khác có gì cần lưu ý? Vì sao phương án nhận dependency qua tham số ít rủi ro hơn?

**Gợi ý đối chiếu:**

1. `messageSender` và `orderService` là phương thức tạo/đăng ký bean; Spring gọi theo quá trình tạo bean, còn `main` lấy service đã lắp ghép rồi điều phối bắt đầu công việc.
2. Giá trị `@Bean` trả về được đăng ký trong context; object tự `new` trong nghiệp vụ thường nằm ngoài cơ chế quản lý bean.
3. `@Bean OrderService orderService(@Qualifier("auditedSender") MessageSender sender) { return new OrderService(sender); }`.
4. Không. Singleton thường nhận dependency đã resolve lúc khởi tạo; cần typed factory/provider hoặc scope phù hợp nếu cần instance mới theo request.
5. Service là borrower, không được đóng client dùng chung; owner/context hoặc lifecycle manager đóng khi các service đã ngừng sử dụng.
6. Lời gọi trực tiếp là lời gọi Java thông thường nên có thể tạo object mới; tham số cho phép container resolve đúng bean và scope.

## 14. Ghi nhớ

**Cấu hình Java** giúp mô tả việc chọn và lắp ghép implementation tại ranh giới khởi động; **factory method `@Bean`** nêu cách tạo bean, còn **đăng ký tường minh** cho phép đưa các quyết định đó vào container mà không cần hoàn toàn dựa vào quét tự động. Những cơ chế này không thay thế constructor injection, contract hoặc composition root: chúng hỗ trợ tự động hóa phần wiring.

Hãy giữ code nghiệp vụ sử dụng dependency, không tự tra cứu container; dùng tham số phương thức `@Bean` để thể hiện quan hệ phụ thuộc; và luôn kiểm tra **scope, ownership, lifecycle, tính thay thế giữa các implementation**. Nắm chắc bản Java thuần trước sẽ giúp bạn đọc và kiểm chứng cấu hình DI framework chính xác hơn.
