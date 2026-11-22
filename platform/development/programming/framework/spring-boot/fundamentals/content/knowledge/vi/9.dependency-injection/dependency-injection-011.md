# Giữ dependency tường minh thay vì tra cứu context rải rác trong nghiệp vụ

Trong một ứng dụng Spring Boot, các thành phần thường cần gọi nhau để hoàn thành một use case. Ví dụ, `CheckoutService` cần một `PaymentGateway` để thanh toán, một `OrderRepository` để lưu đơn hàng và có thể cần một `NotificationSender` để gửi thông báo. Những thành phần này là **dependency** của service.

Spring cung cấp `ApplicationContext` để quản lý bean và cho phép truy xuất bean bằng `getBean(...)`. Vì có sẵn cơ chế đó, đôi khi lập trình viên truyền cả `ApplicationContext` vào service rồi gọi `getBean` ở bất cứ nơi nào cần một đối tượng. Cách này có vẻ linh hoạt, nhưng nó làm cho dependency trở nên ẩn: nhìn constructor không biết service thực sự cần những thành phần nào, và lỗi thiếu bean có thể chỉ xuất hiện khi một nhánh nghiệp vụ được thực thi.

Trong thiết kế ứng dụng, nên **khai báo dependency trực tiếp qua constructor hoặc một hợp đồng rõ ràng**. Container có trách nhiệm lắp ghép object graph; service tập trung vào nghiệp vụ. Khi cần lựa chọn implementation động, dependency tùy chọn hoặc tạo instance theo yêu cầu, có những abstraction của Spring như `ObjectProvider`, factory hoặc registry giúp thể hiện nhu cầu đó mà không biến toàn bộ nghiệp vụ thành nơi tra cứu container.

## 1. Dependency là gì và vì sao cần nhìn thấy nó?

Một dependency là thành phần mà một đối tượng cần để thực hiện trách nhiệm của mình. Ví dụ:

~~~text
CheckoutController
       |
       v
CheckoutService
   |          |
   v          v
OrderRepository  PaymentGateway
~~~

`CheckoutService` phụ thuộc vào `OrderRepository` và `PaymentGateway`. Hai quan hệ này là một phần cấu trúc của service, không phải chi tiết ngẫu nhiên của một dòng code.

Một cách viết tường minh:

~~~java
@Service
public class CheckoutService {
    private final OrderRepository orderRepository;
    private final PaymentGateway paymentGateway;

    public CheckoutService(
            OrderRepository orderRepository,
            PaymentGateway paymentGateway
    ) {
        this.orderRepository = orderRepository;
        this.paymentGateway = paymentGateway;
    }
}
~~~

Nhìn constructor, người đọc có thể biết ngay service cần hai cộng tác viên. Spring cũng biết cần tìm bean phù hợp cho từng kiểu tham số khi tạo `CheckoutService`.

Ngược lại, nếu constructor chỉ nhận `ApplicationContext`:

~~~java
@Service
public class CheckoutService {
    private final ApplicationContext context;

    public CheckoutService(ApplicationContext context) {
        this.context = context;
    }
}
~~~

thì constructor chỉ thể hiện một dependency là container, trong khi logic bên trong có thể sử dụng rất nhiều bean khác nhau. Các dependency nghiệp vụ bị giấu sau những lần tra cứu.

### Dependency tường minh đem lại điều gì?

- **Dễ hiểu:** constructor cho thấy service cần gì để hoạt động.
- **Dễ kiểm thử:** test có thể truyền fake hoặc mock qua constructor mà không cần dựng toàn bộ Spring context.
- **Phát hiện lỗi sớm:** dependency bắt buộc bị thiếu thường khiến context thất bại khi khởi tạo bean.
- **Giảm coupling:** service phụ thuộc vào interface nghiệp vụ, không cần biết cách container tìm implementation.
- **Dễ refactor:** thay đổi một dependency thường làm lộ rõ những nơi bị ảnh hưởng qua kiểu dữ liệu và constructor.
- **Dễ quan sát đồ thị:** quan hệ giữa các thành phần có thể được lần theo từ constructor, cấu hình và interface.

Dependency tường minh không có nghĩa phải truyền mọi giá trị vào constructor. Dữ liệu của từng request như `customerId`, `orderId` hoặc `quantity` thường là tham số phương thức. Dependency là cộng tác viên hoặc tài nguyên mà đối tượng cần để thực hiện trách nhiệm, còn dữ liệu đầu vào thay đổi theo từng lần gọi nên được truyền qua API nghiệp vụ.

## 2. Tra cứu bean qua ApplicationContext là gì?

`ApplicationContext` là giao diện container phổ biến của Spring. Nó mở rộng khả năng cơ bản của `BeanFactory` và cung cấp thêm các dịch vụ của môi trường ứng dụng. Một trong các khả năng của nó là tìm bean theo kiểu hoặc tên:

~~~java
PaymentGateway gateway =
        applicationContext.getBean(PaymentGateway.class);
~~~

Hoặc:

~~~java
Object bean = applicationContext.getBean("paymentGateway");
~~~

Cách này gọi là **tra cứu dependency** (*dependency lookup*) hoặc thường được xếp vào mẫu **Service Locator** khi một đối tượng tự hỏi container để lấy cộng tác viên lúc chạy.

Service Locator không phải một API sai trong mọi hoàn cảnh. Nó có thể hữu ích ở tầng hạ tầng hoặc trong một hệ thống plugin thực sự cần khám phá thành phần động. Vấn đề xuất hiện khi các service nghiệp vụ dùng nó như cách tiêm dependency thông thường.

### Ví dụ tra cứu rải rác trong nghiệp vụ

~~~java
@Service
public class CheckoutService {
    private final ApplicationContext context;

    public CheckoutService(ApplicationContext context) {
        this.context = context;
    }

    public Receipt checkout(CheckoutCommand command) {
        OrderRepository repository =
                context.getBean(OrderRepository.class);

        PaymentGateway gateway =
                context.getBean(PaymentGateway.class);

        Order order = repository.findDraft(command.orderId())
                .orElseThrow();

        PaymentResult result = gateway.charge(
                new ChargeCommand(order.id(), order.total())
        );

        if (result.success()) {
            repository.markPaid(order.id());
        }

        return new Receipt(order.id(), result.reference());
    }
}
~~~

Đoạn code minh họa việc service tự tra cứu các cộng tác viên. Nó vẫn có thể chạy nếu các bean tồn tại, nhưng có một số vấn đề:

1. **Constructor không mô tả đủ dependency.** Người đọc phải tìm toàn bộ thân phương thức để biết service cần repository, gateway và có thể còn nhiều bean khác.
2. **Lỗi bị trì hoãn.** Nếu thiếu `PaymentGateway`, ứng dụng có thể vẫn khởi động được; lỗi chỉ xảy ra khi gọi `checkout`.
3. **Khó unit test.** Test cần một `ApplicationContext` hoặc phải tạo một context giả, dù mục tiêu chỉ là kiểm tra logic checkout.
4. **Service phụ thuộc vào Spring API.** Logic nghiệp vụ biết cách truy cập container, khiến việc tái sử dụng ngoài Spring khó hơn.
5. **Tra cứu theo tên dễ sai.** Chuỗi bean name có thể không còn đúng sau khi đổi tên hoặc cấu hình.
6. **Khó kiểm soát thời điểm và số lần tra cứu.** Một nhánh có thể lấy implementation khác với nhánh khác nếu context hoặc cấu hình có nhiều ứng viên.
7. **Khó lần theo đồ thị phụ thuộc.** Công cụ đọc constructor, IDE và người review không dễ nhận ra các quan hệ ẩn.

Vấn đề không nằm ở số ký tự gọi `getBean`. Vấn đề là service đang **tự chịu trách nhiệm khám phá và lấy dependency**, thay vì khai báo nhu cầu của nó.

## 3. Dependency Injection và Service Locator khác nhau ra sao?

Hai cách có thể trả về cùng một bean, nhưng quyền kiểm soát được đặt ở những nơi khác nhau.

~~~text
Dependency Injection

Spring ApplicationContext
       |
       | tìm và cung cấp bean
       v
CheckoutService(repository, gateway)
       |
       +---- dùng repository
       |
       +---- dùng gateway


Service Locator

CheckoutService(ApplicationContext)
       |
       +---- getBean(OrderRepository.class)
       |
       +---- getBean(PaymentGateway.class)
       |
       +---- có thể tiếp tục tìm thêm bean
~~~

| Tiêu chí | Dependency Injection | Service Locator / context lookup |
|---|---|---|
| Dependency được khai báo ở đâu? | Constructor hoặc API tạo đối tượng | Trong thân phương thức hoặc nơi gọi locator |
| Ai tìm implementation? | Container tại điểm lắp ghép | Đối tượng sử dụng tự yêu cầu locator |
| Có thể nhìn thấy dependency khi đọc class? | Thường có | Thường không đầy đủ |
| Lỗi thiếu dependency bắt buộc | Thường xuất hiện lúc tạo bean | Có thể chỉ xuất hiện khi chạy nhánh lookup |
| Unit test | Truyền fake/mock trực tiếp | Phải cung cấp locator/context hoặc thay đổi cách tra cứu |
| Coupling với Spring | Có thể thấp ở lớp nghiệp vụ | Cao nếu lớp nghiệp vụ gọi trực tiếp Spring API |
| Phù hợp nhất | Dependency ổn định, bắt buộc của đối tượng | Một số hạ tầng cần khám phá thành phần động, có ranh giới rõ |

DI và Service Locator đều có thể dùng container phía sau. Sự khác biệt nằm ở việc **consumer có khai báo rõ những gì nó cần hay tự đi tìm chúng khi chạy**.

## 4. Constructor injection: cách khai báo dependency mặc định nên ưu tiên

Trong Spring, constructor injection là cách rõ ràng để thể hiện các dependency bắt buộc.

~~~java
@Service
public class CheckoutService {
    private final OrderRepository orderRepository;
    private final PaymentGateway paymentGateway;

    public CheckoutService(
            OrderRepository orderRepository,
            PaymentGateway paymentGateway
    ) {
        this.orderRepository = orderRepository;
        this.paymentGateway = paymentGateway;
    }

    public Receipt checkout(CheckoutCommand command) {
        // Dùng hai dependency đã được cung cấp.
        return null;
    }
}
~~~

Spring tìm bean phù hợp với từng tham số constructor và cung cấp chúng khi tạo service. Nếu class chỉ có một constructor, trong trường hợp thông thường không cần viết thêm `@Autowired` trên constructor đó.

### Vì sao constructor phù hợp với dependency bắt buộc?

Một đối tượng chỉ nên được tạo khi đã có đủ những cộng tác viên cần thiết. Constructor là ranh giới tự nhiên để bảo đảm điều đó:

~~~java
public CheckoutService(
        OrderRepository orderRepository,
        PaymentGateway paymentGateway
) {
    this.orderRepository = Objects.requireNonNull(orderRepository);
    this.paymentGateway = Objects.requireNonNull(paymentGateway);
}
~~~

Nếu tạo thủ công, người gọi cũng phải cung cấp đủ dependency. Nếu Spring tạo, container phải giải quyết đủ dependency trước khi hoàn thành bean. Trường `final` giúp tham chiếu không bị thay đổi sau khi constructor hoàn tất.

### Constructor còn là một bản mô tả trách nhiệm

Nếu một service có mười lăm dependency, constructor dài là tín hiệu đáng xem xét. Có thể class đang đảm nhận nhiều use case hoặc điều phối quá nhiều phần khác nhau. Giải pháp không nhất thiết là chuyển tất cả sang `ApplicationContext` để constructor ngắn hơn; nên kiểm tra trách nhiệm, chia use case hoặc tạo một abstraction có ý nghĩa.

**Đừng che độ phức tạp bằng cách giấu dependency.** Một constructor dài đôi khi là thông tin thiết kế hữu ích: nó cho thấy class đang biết quá nhiều.

## 5. Ví dụ Spring Boot hoàn chỉnh: checkout với dependency tường minh

Xây dựng một ví dụ nhỏ gồm controller, service, repository và cổng thanh toán. Các lớp đặt dưới cùng package gốc `com.example.shop` để Spring Boot có thể component scan theo mặc định. Ví dụ dùng Java 17+ và Spring MVC; trong dự án thực tế cần starter web tương ứng và các cấu hình phù hợp.

### 5.1. Kiểu dữ liệu nghiệp vụ

~~~java
package com.example.shop;

public record CheckoutCommand(Long orderId) {}

public record ChargeCommand(Long orderId, long amount) {}

public record PaymentResult(
        boolean success,
        String reference
) {}

public record Receipt(
        Long orderId,
        String paymentReference
) {}
~~~

Các record này là dữ liệu đầu vào/đầu ra. Chúng không nhất thiết phải là bean vì được tạo theo từng thao tác nghiệp vụ.

### 5.2. Khai báo hợp đồng repository và gateway

~~~java
package com.example.shop;

import java.util.Optional;

public interface OrderRepository {
    Optional<Order> findDraft(Long orderId);
    void markPaid(Long orderId);
}
~~~

~~~java
package com.example.shop;

public interface PaymentGateway {
    PaymentResult charge(ChargeCommand command);
}
~~~

Interface xác định điều service cần. Nó không yêu cầu service biết implementation dùng JPA, JDBC, HTTP client hay SDK của nhà cung cấp thanh toán.

### 5.3. Cung cấp implementation dưới dạng bean

Repository giả lập:

~~~java
package com.example.shop;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryOrderRepository implements OrderRepository {
    private final Map<Long, Order> orders = Map.of(
            101L, new Order(101L, 250_000L)
    );

    @Override
    public Optional<Order> findDraft(Long orderId) {
        return Optional.ofNullable(orders.get(orderId));
    }

    @Override
    public void markPaid(Long orderId) {
        // Chỉ minh họa. Repository thật sẽ cập nhật trạng thái lưu trữ.
    }
}
~~~

Kiểu `Order`:

~~~java
package com.example.shop;

public record Order(Long id, long total) {}
~~~

Gateway giả lập:

~~~java
package com.example.shop;

import org.springframework.stereotype.Component;

@Component
public class DemoPaymentGateway implements PaymentGateway {
    @Override
    public PaymentResult charge(ChargeCommand command) {
        return new PaymentResult(
                true,
                "DEMO-" + command.orderId()
        );
    }
}
~~~

Các annotation stereotype giúp Spring component scan đăng ký implementation. Trong ứng dụng thật, repository và gateway sẽ có logic lưu trữ hoặc gọi nhà cung cấp bên ngoài; mục tiêu ở đây là minh họa quan hệ dependency.

### 5.4. Service nhận dependency qua constructor

~~~java
package com.example.shop;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {
    private final OrderRepository orderRepository;
    private final PaymentGateway paymentGateway;

    public CheckoutService(
            OrderRepository orderRepository,
            PaymentGateway paymentGateway
    ) {
        this.orderRepository = orderRepository;
        this.paymentGateway = paymentGateway;
    }

    @Transactional
    public Receipt checkout(CheckoutCommand command) {
        Order order = orderRepository.findDraft(command.orderId())
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Không tìm thấy đơn hàng"
                        )
                );

        PaymentResult payment = paymentGateway.charge(
                new ChargeCommand(order.id(), order.total())
        );

        if (!payment.success()) {
            throw new IllegalStateException(
                    "Thanh toán không thành công"
            );
        }

        orderRepository.markPaid(order.id());

        return new Receipt(order.id(), payment.reference());
    }
}
~~~

`@Transactional` chỉ có ý nghĩa khi transaction infrastructure và cơ chế gọi qua proxy phù hợp được cấu hình. Ví dụ này không mô tả đầy đủ các vấn đề nhất quán giữa database và nhà cung cấp thanh toán bên ngoài; một giao dịch database không tự rollback được một khoản thanh toán đã xử lý thành công ở hệ thống ngoài. Với quy trình thật, cần cân nhắc idempotency, retry và saga/outbox tùy yêu cầu.

### 5.5. Controller cũng nhận service tường minh

~~~java
package com.example.shop;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CheckoutController {
    private final CheckoutService checkoutService;

    public CheckoutController(CheckoutService checkoutService) {
        this.checkoutService = checkoutService;
    }

    @PostMapping("/checkout")
    public Receipt checkout(@RequestBody CheckoutCommand command) {
        return checkoutService.checkout(command);
    }
}
~~~

Đồ thị dependency:

~~~text
CheckoutController
        |
        v
CheckoutService
    |          |
    v          v
OrderRepository  PaymentGateway
    ^                  ^
    |                  |
InMemoryOrderRepository  DemoPaymentGateway
~~~

Khi Spring khởi động, container phát hiện các bean và giải quyết constructor của `CheckoutController` và `CheckoutService`. Không có service nào cần biết `ApplicationContext` hoặc gọi `getBean`.

### 5.6. Điều gì thay đổi nếu implementation đổi?

Giả sử sau này thay `InMemoryOrderRepository` bằng `JpaOrderRepository`. Nếu ứng dụng chỉ đăng ký một bean phù hợp với `OrderRepository`, `CheckoutService` vẫn giữ nguyên constructor và logic. Tương tự, `DemoPaymentGateway` có thể được thay bằng một gateway thật.

Đây là lợi ích của việc phụ thuộc vào hợp đồng: **consumer biết khả năng cần dùng, không biết cách container tìm implementation**.

## 6. Cấu hình bean bên ngoài không có nghĩa service phải tra cứu context

Có trường hợp đối tượng không mang annotation Spring, ví dụ client từ thư viện bên thứ ba. Ta có thể tạo bean bằng `@Bean`:

~~~java
@Configuration
public class PaymentConfiguration {

    @Bean
    public VendorClient vendorClient(
            VendorSettings settings
    ) {
        return new VendorClient(
                settings.endpoint(),
                settings.apiKey()
        );
    }

    @Bean
    public PaymentGateway paymentGateway(
            VendorClient vendorClient
    ) {
        return new VendorPaymentGateway(vendorClient);
    }
}
~~~

`VendorClient`, `VendorSettings` và `VendorPaymentGateway` là các kiểu minh họa cần được định nghĩa trong dự án hoặc thư viện tích hợp. Điểm quan trọng là **phương thức factory nhận dependency qua tham số**. Spring tự cung cấp `VendorSettings` cho `vendorClient` và `VendorClient` cho `paymentGateway` nếu các bean tương ứng có thể được giải quyết.

Không cần viết:

~~~java
@Bean
public PaymentGateway paymentGateway(ApplicationContext context) {
    VendorClient client = context.getBean(VendorClient.class);
    return new VendorPaymentGateway(client);
}
~~~

Cách thứ hai có thể hoạt động, nhưng làm mờ dependency của factory method. Trong cấu hình Spring, tham số phương thức `@Bean` đã là cơ chế injection tự nhiên.

### Cấu hình là composition root

Có thể xem những lớp `@Configuration` và phương thức `@Bean` như một phần của **composition root**: nơi quyết định implementation nào được kết nối với nhau. Cấu hình có thể biết về Spring và chi tiết tích hợp; service nghiệp vụ không cần mang trách nhiệm đó.

~~~text
Configuration / ApplicationContext
       |
       +--> tạo VendorClient
       |
       +--> tạo VendorPaymentGateway(client)
       |
       +--> tạo CheckoutService(repository, gateway)
                         |
                         v
                  logic checkout
~~~

Đây là nơi thích hợp để tập trung cấu hình, qualifier, profile và điều kiện tạo bean.

## 7. Khi có nhiều implementation, inject tập hợp hoặc dùng registry

Tra cứu context rải rác thường bắt đầu từ một tình huống hợp lý: ứng dụng có nhiều implementation và muốn chọn một implementation theo dữ liệu đầu vào. Nhưng việc lựa chọn động không bắt buộc phải gọi `getBean`.

Ví dụ, hệ thống hỗ trợ nhiều phương thức thanh toán:

~~~java
public enum PaymentMethod {
    CARD,
    BANK_TRANSFER
}
~~~

Hợp đồng:

~~~java
public interface PaymentGateway {
    boolean supports(PaymentMethod method);
    PaymentResult charge(ChargeCommand command);
}
~~~

Các implementation:

~~~java
@Component
public class CardPaymentGateway implements PaymentGateway {
    @Override
    public boolean supports(PaymentMethod method) {
        return method == PaymentMethod.CARD;
    }

    @Override
    public PaymentResult charge(ChargeCommand command) {
        // Gọi nhà cung cấp thẻ.
        return new PaymentResult(true, "CARD-REF");
    }
}
~~~

~~~java
@Component
public class BankTransferGateway implements PaymentGateway {
    @Override
    public boolean supports(PaymentMethod method) {
        return method == PaymentMethod.BANK_TRANSFER;
    }

    @Override
    public PaymentResult charge(ChargeCommand command) {
        // Tạo yêu cầu chuyển khoản.
        return new PaymentResult(true, "BANK-REF");
    }
}
~~~

Một resolver nhận danh sách các gateway:

~~~java
@Component
public class PaymentGatewayResolver {
    private final List<PaymentGateway> gateways;

    public PaymentGatewayResolver(List<PaymentGateway> gateways) {
        this.gateways = List.copyOf(gateways);
    }

    public PaymentGateway resolve(PaymentMethod method) {
        return gateways.stream()
                .filter(gateway -> gateway.supports(method))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Không hỗ trợ phương thức thanh toán"
                        )
                );
    }
}
~~~

Service sử dụng resolver:

~~~java
@Service
public class CheckoutService {
    private final PaymentGatewayResolver gatewayResolver;

    public CheckoutService(PaymentGatewayResolver gatewayResolver) {
        this.gatewayResolver = gatewayResolver;
    }

    public PaymentResult pay(
            PaymentMethod method,
            ChargeCommand command
    ) {
        return gatewayResolver.resolve(method).charge(command);
    }
}
~~~

Ở đây, dependency của resolver là **tập hợp các gateway**. Nó có thể lựa chọn theo phương thức thanh toán mà không cần tra cứu ApplicationContext. Mỗi gateway tự khai báo khả năng hỗ trợ qua hợp đồng.

Trong ứng dụng thực tế, nên xử lý trường hợp có nhiều gateway cùng trả `supports` là true nếu quy tắc yêu cầu duy nhất. Có thể kiểm tra số lượng ứng viên và báo lỗi cấu hình rõ ràng thay vì chọn phần tử đầu tiên theo thứ tự tình cờ.

### Inject Map khi bean name là một phần của cấu hình

Spring có thể inject `Map<String, PaymentGateway>`, trong đó key thường là bean name và value là bean tương ứng:

~~~java
@Component
public class GatewayRegistry {
    private final Map<String, PaymentGateway> gateways;

    public GatewayRegistry(Map<String, PaymentGateway> gateways) {
        this.gateways = Map.copyOf(gateways);
    }
}
~~~

Đây vẫn là dependency tường minh: constructor thể hiện registry cần một tập các gateway. Tuy nhiên, nếu mã nghiệp vụ phải tự ghép chuỗi tên bean từ dữ liệu người dùng rồi tìm trong map, nó vẫn đang phụ thuộc vào quy ước container. Nên chuyển đổi input thành enum/kiểu miền và dùng resolver kiểm tra hợp lệ.

## 8. Khi dependency thực sự tùy chọn hoặc cần lấy muộn

Không phải mọi dependency đều bắt buộc có mặt. Ví dụ, tính năng gửi thông báo có thể tắt trong môi trường local. Nếu service không thể hoạt động khi thiếu một dependency, constructor injection bắt buộc là phù hợp. Nếu dependency thật sự tùy chọn, hãy biểu đạt điều đó bằng kiểu dữ liệu hoặc abstraction phù hợp.

### Dùng Optional cho dependency tùy chọn

~~~java
@Service
public class ReceiptService {
    private final Optional<ReceiptArchive> archive;

    public ReceiptService(Optional<ReceiptArchive> archive) {
        this.archive = archive;
    }

    public void archiveIfConfigured(Receipt receipt) {
        archive.ifPresent(value -> value.store(receipt));
    }
}
~~~

`Optional<ReceiptArchive>` cho biết dependency có thể không tồn tại. Cách này phù hợp với một dependency tùy chọn đơn giản. Nếu có nhiều bean cùng kiểu, cần hiểu quy tắc phân giải; Optional không tự quyết định giữa nhiều implementation mơ hồ.

### Dùng ObjectProvider khi cần tra cứu muộn qua abstraction có kiểu

Spring cung cấp `ObjectProvider<T>` để lấy bean khi cần, xử lý trường hợp không có bean hoặc truy cập tập hợp ứng viên:

~~~java
@Service
public class NotificationService {
    private final ObjectProvider<NotificationSender> senderProvider;

    public NotificationService(
            ObjectProvider<NotificationSender> senderProvider
    ) {
        this.senderProvider = senderProvider;
    }

    public void notifyIfEnabled(Notification message) {
        NotificationSender sender = senderProvider.getIfAvailable();

        if (sender != null) {
            sender.send(message);
        }
    }
}
~~~

Cần import `org.springframework.beans.factory.ObjectProvider`. `getIfAvailable()` trả về `null` khi không có bean phù hợp; nếu có nhiều bean không thể chọn duy nhất, nó có thể ném lỗi không duy nhất. Nếu cần xử lý nhiều ứng viên, dùng `orderedStream()` hoặc một danh sách/registry được inject rõ ràng.

`ObjectProvider` hữu ích khi:

- Bean có thể không tồn tại theo cấu hình.
- Cần trì hoãn việc lấy bean đến thời điểm sử dụng.
- Cần lấy instance mới của một bean prototype mỗi lần gọi.
- Cần truy cập tập hợp bean theo kiểu.
- Muốn thể hiện rõ kiểu dependency mà không truyền toàn bộ `ApplicationContext`.

Tuy vậy, không nên thay mọi trường constructor bằng `ObjectProvider` để tránh liệt kê dependency. Nếu bean luôn bắt buộc, inject trực tiếp `T` đơn giản và dễ hiểu hơn.

### Prototype bean và thời điểm lấy instance

Giả sử `ReportSession` có scope prototype:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ReportSession {
    // Trạng thái riêng của một lần tạo báo cáo.
}
~~~

Nếu một singleton service inject trực tiếp `ReportSession` vào constructor, Spring tạo prototype tại thời điểm tạo singleton; service sẽ giữ cùng instance đó trong trường của nó. Nếu cần instance mới cho từng báo cáo:

~~~java
@Service
public class ReportService {
    private final ObjectProvider<ReportSession> sessionProvider;

    public ReportService(ObjectProvider<ReportSession> sessionProvider) {
        this.sessionProvider = sessionProvider;
    }

    public void generate() {
        ReportSession session = sessionProvider.getObject();
        // Dùng session cho lần tạo báo cáo này.
    }
}
~~~

Provider giữ yêu cầu lấy bean rõ ràng và cho phép container áp dụng scope. Tuy nhiên, với object dữ liệu thuần không cần lifecycle Spring, tạo bằng factory Java thông thường có thể đơn giản hơn.

### Dùng @Lazy khi cần trì hoãn khởi tạo

`@Lazy` có thể đặt ở bean hoặc injection point để trì hoãn khởi tạo theo cơ chế Spring. Ví dụ:

~~~java
@Service
public class LargeReportService {
    private final ReportEngine reportEngine;

    public LargeReportService(@Lazy ReportEngine reportEngine) {
        this.reportEngine = reportEngine;
    }
}
~~~

Cách này có thể hữu ích nếu khởi tạo engine tốn tài nguyên và có thể không được sử dụng. Nhưng `@Lazy` không phải công cụ che một dependency sai hoặc chữa vòng phụ thuộc một cách mặc định. Proxy/lazy resolution có semantics riêng và lỗi có thể chỉ xuất hiện lúc gọi bean thật.

## 9. Đừng đưa dữ liệu nghiệp vụ qua ApplicationContext

Một dạng lạm dụng khác là dùng container để tìm đối tượng dựa trên dữ liệu của request:

~~~java
public Receipt checkout(String customerType, CheckoutCommand command) {
    CustomerPolicy policy = context.getBean(
            customerType + "CustomerPolicy",
            CustomerPolicy.class
    );
    // ...
}
~~~

Ở đây, `customerType` là dữ liệu nghiệp vụ. Nó không nên được ghép thành tên bean rồi chuyển cho container để tra cứu. Cách đó buộc quy tắc nghiệp vụ biết bean name và biến input thành một phần của cơ chế cấu hình.

Thay vào đó, hãy tạo một registry có kiểu, inject các policy cần thiết và lựa chọn bằng dữ liệu miền:

~~~java
public enum CustomerType {
    REGULAR,
    PREMIUM
}
~~~

~~~java
public interface CustomerPolicy {
    CustomerType type();
    Discount calculate(CheckoutCommand command);
}
~~~

~~~java
@Component
public class CustomerPolicyResolver {
    private final Map<CustomerType, CustomerPolicy> policies;

    public CustomerPolicyResolver(List<CustomerPolicy> candidates) {
        EnumMap<CustomerType, CustomerPolicy> map =
                new EnumMap<>(CustomerType.class);

        for (CustomerPolicy policy : candidates) {
            CustomerPolicy previous = map.put(policy.type(), policy);
            if (previous != null) {
                throw new IllegalStateException(
                        "Trùng policy cho " + policy.type()
                );
            }
        }

        this.policies = Map.copyOf(map);
    }

    public CustomerPolicy resolve(CustomerType type) {
        CustomerPolicy policy = policies.get(type);
        if (policy == null) {
            throw new IllegalArgumentException(
                    "Không có policy cho " + type
            );
        }
        return policy;
    }
}
~~~

Lớp resolver này nhận các implementation tường minh qua constructor và xây dựng bảng tra cứu theo kiểu miền. Dữ liệu request chỉ chọn một policy trong tập đã đăng ký; nó không được quyền yêu cầu container tạo hoặc tìm một bean bất kỳ.

Nguyên tắc là: **dùng dữ liệu để chọn trong một tập lựa chọn đã được kiểm soát**, không biến dữ liệu thành lệnh truy cập container.

## 10. Giữ ranh giới giữa nghiệp vụ và Spring Framework

Một lợi ích lớn của dependency tường minh là phần nghiệp vụ có thể ít phụ thuộc vào framework hơn.

Ví dụ, service Java thuần:

~~~java
public class PriceCalculator {
    private final PricingPolicy pricingPolicy;

    public PriceCalculator(PricingPolicy pricingPolicy) {
        this.pricingPolicy = pricingPolicy;
    }

    public long calculate(long unitPrice, int quantity) {
        if (quantity < 1) {
            throw new IllegalArgumentException("quantity phải dương");
        }
        return pricingPolicy.total(unitPrice, quantity);
    }
}
~~~

Lớp này không cần import Spring. Spring có thể tạo nó bằng:

~~~java
@Configuration
public class PricingConfiguration {

    @Bean
    public PriceCalculator priceCalculator(
            PricingPolicy pricingPolicy
    ) {
        return new PriceCalculator(pricingPolicy);
    }
}
~~~

Hoặc lớp có thể được đánh dấu stereotype nếu dự án muốn component scan. Trong cả hai cách, `PriceCalculator` không cần biết ApplicationContext tồn tại.

### Vì sao việc giảm coupling có ích?

- Có thể sử dụng logic trong một chương trình Java khác hoặc test thuần.
- Có thể thay container hoặc cơ chế khởi tạo mà không phải sửa logic nghiệp vụ.
- Các interface nghiệp vụ trở thành ranh giới giữa module.
- Người đọc không cần hiểu Spring API để hiểu thuật toán cốt lõi.
- Những thay đổi của framework được tập trung ở composition root và adapter.

Không cần loại bỏ hoàn toàn Spring annotation khỏi mọi lớp. `@Service` hoặc `@Transactional` có thể là lựa chọn thực dụng trong ứng dụng Spring. Mục tiêu của bài học là tránh việc **nghiệp vụ tự tra cứu container như một kho đối tượng toàn cục**.

## 11. Vì sao ApplicationContext lookup làm kiểm thử khó hơn?

Giả sử test cần kiểm tra cách checkout xử lý thanh toán thất bại. Với constructor injection, test có thể cung cấp các fake đơn giản:

~~~java
OrderRepository repository = new FakeOrderRepository();
PaymentGateway failingGateway = command ->
        new PaymentResult(false, null);

CheckoutService service =
        new CheckoutService(repository, failingGateway);

// Gọi service và kiểm tra hành vi lỗi.
~~~

Không cần khởi động Spring. Test chỉ dựng đúng các cộng tác viên liên quan đến hành vi cần kiểm tra.

Với service locator:

~~~java
CheckoutService service =
        new CheckoutService(applicationContext);
~~~

test phải cung cấp context có các bean phù hợp, hoặc tạo một mock `ApplicationContext` và mô phỏng từng lời gọi `getBean`. Điều đó khiến test phụ thuộc vào cách triển khai lookup thay vì tập trung vào nghiệp vụ.

### Unit test bằng Mockito

Ví dụ với JUnit 5 và Mockito:

~~~java
@ExtendWith(MockitoExtension.class)
class CheckoutServiceTest {

    @Mock
    OrderRepository orderRepository;

    @Mock
    PaymentGateway paymentGateway;

    @Test
    void usesInjectedDependencies() {
        CheckoutService service =
                new CheckoutService(orderRepository, paymentGateway);

        // Arrange dữ liệu giả và kết quả mock.
        // Gọi service.
        // Assert kết quả và verify lời gọi cần thiết.
    }
}
~~~

Đây là skeleton minh họa; test thực tế cần khai báo dữ liệu, stubbing và assertion theo API của service. Điểm đáng chú ý là test có thể tạo service trực tiếp với các dependency đã kiểm soát.

### Khi nào vẫn cần kiểm thử Spring context?

Unit test không kiểm tra component scan, bean condition, qualifier hay cấu hình auto-configuration. Để xác nhận wiring thực tế, có thể viết integration test hoặc `@SpringBootTest`:

~~~java
@SpringBootTest
class CheckoutContextTest {

    @Autowired
    CheckoutService checkoutService;

    @Test
    void contextProvidesCheckoutService() {
        assertNotNull(checkoutService);
    }
}
~~~

Hai loại test bổ sung cho nhau:

| Kiểm thử | Câu hỏi chính |
|---|---|
| Unit test | Logic service có đúng khi nhận các dependency đã kiểm soát không? |
| Spring context test | Container có đăng ký và kết nối các bean như cấu hình mong muốn không? |
| Integration test | Các thành phần có phối hợp đúng với database, HTTP client hoặc hệ thống ngoài không? |

Không nên dùng `@SpringBootTest` cho mọi test đơn vị chỉ vì ứng dụng sử dụng Spring. Nếu một service có thể kiểm thử bằng constructor Java, hãy tận dụng điều đó.

## 12. Static ApplicationContext holder: một biến toàn cục trá hình

Một anti-pattern thường gặp là tạo lớp giữ context tĩnh:

~~~java
@Component
public class SpringContextHolder implements ApplicationContextAware {
    private static ApplicationContext context;

    @Override
    public void setApplicationContext(ApplicationContext applicationContext) {
        context = applicationContext;
    }

    public static <T> T getBean(Class<T> type) {
        return context.getBean(type);
    }
}
~~~

Sau đó ở bất cứ đâu:

~~~java
PaymentGateway gateway =
        SpringContextHolder.getBean(PaymentGateway.class);
~~~

Cách này tạo cảm giác có thể truy cập mọi bean toàn cục mà không cần truyền dependency. Nhưng nó mang lại các vấn đề:

- **Global state:** lớp nào cũng có thể truy cập container, không có ranh giới phụ thuộc rõ.
- **Thứ tự khởi tạo:** gọi holder trước khi Spring gán context có thể gặp `null`.
- **Nhiều ApplicationContext:** test, parent/child context hoặc nhiều ứng dụng trong cùng JVM có thể khiến một biến static không đại diện đúng context.
- **Khó test độc lập:** test cần reset trạng thái static, có nguy cơ rò rỉ giữa test.
- **Khó thay đổi kiến trúc:** mọi lớp đã gọi holder đều phụ thuộc vào cơ chế toàn cục này.
- **Che lỗi cấu hình:** bean chỉ được yêu cầu lúc chạy nên lỗi thiếu bean có thể bị phát hiện muộn.

Một lớp infrastructure chuyên biệt có thể cần tương tác với context trong những hệ thống framework hoặc plugin đặc thù. Nhưng không nên biến cơ chế đó thành API chung cho tất cả service nghiệp vụ.

Nếu code cũ đã có holder, có thể chuyển đổi dần: xác định từng loại bean đang được tra cứu, thêm dependency constructor tương ứng, chuyển nơi lựa chọn động sang registry/factory, rồi xóa những đường truy cập toàn cục khi không còn người dùng.

## 13. Khi nào context lookup có thể chấp nhận được?

Không nên biến nguyên tắc “giữ dependency tường minh” thành quy tắc cấm tuyệt đối mọi lần truy cập container. Có một số tình huống hạ tầng thực sự cần khả năng khám phá bean động:

- Một framework extension cần tìm handler theo metadata tại runtime.
- Một cơ chế tích hợp generic phải làm việc với nhiều loại bean chưa biết lúc biên dịch.
- Một thành phần bootstrap hoặc công cụ quản trị cần truy vấn context để quan sát cấu trúc ứng dụng.
- Một adapter ở ranh giới framework phải tương tác với container vì hợp đồng bên ngoài yêu cầu như vậy.

Trong những tình huống đó, hãy đặt lookup trong **một thành phần hạ tầng có trách nhiệm cụ thể**, rồi công bố API có kiểu cho phần còn lại của ứng dụng.

~~~text
Business service
      |
      v
PluginRegistry (hợp đồng rõ)
      |
      v
Spring-backed PluginRegistryAdapter
      |
      v
ApplicationContext / bean discovery
~~~

`PluginRegistryAdapter` là nơi hiểu Spring và có thể dùng context nếu thật sự cần. Service nghiệp vụ chỉ biết `PluginRegistry` và phương thức mà nó công bố.

Một tiêu chí hữu ích: nếu xóa Spring khỏi class nghiệp vụ, ta có còn hiểu và kiểm thử được trách nhiệm của class không? Nếu câu trả lời là không chỉ vì class liên tục gọi `getBean`, nên xem xét đưa lookup ra ngoài.

### Truy cập context trong cấu hình và bootstrap

Ở tầng cấu hình, Spring đã cung cấp cơ chế tham số cho `@Bean`; nên dùng cơ chế đó thay cho lookup. Ở code bootstrap, quản trị hoặc tích hợp framework, việc giữ tham chiếu tới `ApplicationContext` có thể hợp lý nếu mục đích thật sự là thao tác với container.

Sự khác biệt nằm ở **ranh giới sử dụng**. Một ứng dụng có thể có vài thành phần hạ tầng biết về Spring mà vẫn giữ phần lớn nghiệp vụ độc lập với container.

## 14. Dependency tường minh giúp quản lý vòng đời và scope dễ hiểu hơn

Khi một class khai báo dependency trong constructor, quan hệ scope giữa các bean cũng dễ được nhìn nhận. Ví dụ, một singleton service nhận một bean repository singleton thường phù hợp với vòng đời ứng dụng. Nhưng nếu service singleton nhận trực tiếp prototype bean, nó chỉ giữ instance được cung cấp lúc khởi tạo singleton.

Tra cứu context trong phương thức có thể khiến scope thay đổi theo thời điểm mà người đọc khó nhận ra:

~~~java
public void generate() {
    ReportSession session =
            applicationContext.getBean(ReportSession.class);
}
~~~

Nếu `ReportSession` là prototype, mỗi lần gọi `getBean` có thể nhận instance mới. Nhưng ý định này bị ẩn sau một lời gọi container. Dùng `ObjectProvider<ReportSession>` làm rõ kiểu và nhu cầu lấy bean muộn hơn:

~~~java
@Service
public class ReportService {
    private final ObjectProvider<ReportSession> sessionProvider;

    public ReportService(ObjectProvider<ReportSession> sessionProvider) {
        this.sessionProvider = sessionProvider;
    }

    public void generate() {
        ReportSession session = sessionProvider.getObject();
        // ...
    }
}
~~~

Người đọc biết ngay service có một provider cho `ReportSession` và sẽ yêu cầu instance lúc gọi `generate`. Đây là một dependency có kiểu và được giới hạn rõ hơn so với việc nhận toàn bộ context.

Tuy nhiên, nếu `ReportSession` chỉ là một object dữ liệu ngắn hạn, không cần Spring scope hay lifecycle, một factory Java thuần cũng có thể phù hợp:

~~~java
public interface ReportSessionFactory {
    ReportSession create();
}
~~~

Factory được inject vào service và tự tạo object bằng Java. Lựa chọn giữa provider và factory phụ thuộc vào việc object có thực sự cần lifecycle/scope của container hay không.

## 15. @Qualifier và @Primary giải quyết lựa chọn, không cần tự lookup

Khi có hai bean cùng implement một interface, container cần biết bean nào phù hợp với injection point.

Ví dụ:

~~~java
@Component("cardGateway")
public class CardPaymentGateway implements PaymentGateway {
    // ...
}

@Component("bankGateway")
public class BankTransferGateway implements PaymentGateway {
    // ...
}
~~~

Một consumer có thể chọn rõ:

~~~java
@Service
public class CardCheckoutService {
    private final PaymentGateway paymentGateway;

    public CardCheckoutService(
            @Qualifier("cardGateway") PaymentGateway paymentGateway
    ) {
        this.paymentGateway = paymentGateway;
    }
}
~~~

Hoặc đánh dấu một bean mặc định:

~~~java
@Component
@Primary
public class CardPaymentGateway implements PaymentGateway {
    // ...
}
~~~

`@Primary` giúp chọn bean ưu tiên khi có nhiều ứng viên cho một injection point không có qualifier cụ thể. `@Qualifier` biểu đạt lựa chọn tại nơi tiêu thụ. Cả hai đều giữ quan hệ dependency ở constructor và cấu hình, thay vì viết `context.getBean("cardGateway")` trong thân phương thức.

Nếu lựa chọn thay đổi theo dữ liệu request, dùng resolver/registry inject danh sách như phần trước. `@Qualifier` không phải công cụ để chọn một bean khác nhau cho mỗi lần gọi phương thức; nó quyết định wiring của bean tại thời điểm container tạo đối tượng.

## 16. Cấu hình theo profile và property vẫn có thể giữ dependency tường minh

Giả sử local dùng gateway giả lập, production dùng gateway thật. Có thể đăng ký implementation theo profile:

~~~java
@Component
@Profile("dev")
public class DemoPaymentGateway implements PaymentGateway {
    // ...
}
~~~

~~~java
@Component
@Profile("prod")
public class LivePaymentGateway implements PaymentGateway {
    // ...
}
~~~

`CheckoutService` vẫn chỉ khai báo:

~~~java
public CheckoutService(PaymentGateway paymentGateway) {
    this.paymentGateway = paymentGateway;
}
~~~

Profile quyết định bean nào có mặt; constructor injection kết nối implementation đang hoạt động. Service không cần kiểm tra `spring.profiles.active`, gọi `getBean` theo profile hoặc tự tạo gateway.

Nếu không có profile nào cung cấp `PaymentGateway`, context thường báo thiếu bean. Đây là lỗi cấu hình sớm và dễ nhận biết hơn việc để service chạy đến một nhánh mới phát hiện không tìm thấy bean.

Với tính năng tùy chọn, có thể dùng `@ConditionalOnProperty` để điều khiển bean hoặc cấu hình, nhưng consumer phải biểu đạt đúng tính bắt buộc/tùy chọn của dependency. Nếu một dependency không tồn tại là trạng thái hợp lệ, dùng `Optional`, `ObjectProvider` hoặc một implementation mặc định có ngữ nghĩa rõ.

## 17. Những cách viết nên tránh và cách chuyển đổi

| Cách viết | Vấn đề | Hướng thay thế |
|---|---|---|
| Service inject `ApplicationContext` rồi gọi `getBean` cho mọi dependency | Che dependency, coupling với Spring | Constructor injection |
| Gọi `getBean("...")` bằng chuỗi trong nhiều phương thức | Tên bean rải rác, dễ sai khi refactor | `@Qualifier` hoặc registry có kiểu |
| Static holder giữ context | Global state, khó test, khó quản lý nhiều context | Inject dependency hoặc adapter hạ tầng |
| Truyền context qua nhiều lớp chỉ để lớp cuối lấy bean | Lan truyền coupling framework | Tiêm trực tiếp bean mà lớp cuối cần |
| Dùng lookup để né constructor dài | Che trách nhiệm quá rộng của service | Tách use case hoặc thành phần có trách nhiệm riêng |
| Dùng lookup theo giá trị người dùng gửi lên | Dữ liệu request điều khiển truy cập bean tùy ý | Resolver kiểm tra kiểu miền và tập implementation cho phép |
| Dùng `ObjectProvider` cho mọi dependency | Làm dependency bắt buộc trông như tùy chọn/lazy | Inject trực tiếp kiểu bean khi cần ngay |
| Dùng `@Lazy` để che circular dependency | Lỗi thiết kế vẫn còn, chỉ đổi thời điểm phát hiện | Tách trách nhiệm, tạo hướng phụ thuộc một chiều |

### Chuyển đổi một service đang dùng context

Giả sử code cũ:

~~~java
@Service
public class InvoiceService {
    private final ApplicationContext context;

    public InvoiceService(ApplicationContext context) {
        this.context = context;
    }

    public Invoice create(InvoiceCommand command) {
        InvoiceRepository repository =
                context.getBean(InvoiceRepository.class);

        TaxCalculator calculator =
                context.getBean(TaxCalculator.class);

        // ...
        return null;
    }
}
~~~

Có thể chuyển thành:

~~~java
@Service
public class InvoiceService {
    private final InvoiceRepository repository;
    private final TaxCalculator calculator;

    public InvoiceService(
            InvoiceRepository repository,
            TaxCalculator calculator
    ) {
        this.repository = repository;
        this.calculator = calculator;
    }

    public Invoice create(InvoiceCommand command) {
        // Dùng repository và calculator đã được cung cấp.
        return null;
    }
}
~~~

Quá trình chuyển đổi theo từng bước:

1. Tìm tất cả lời gọi `getBean` trong class và ghi nhận kiểu bean thực sự được dùng.
2. Xác định dependency nào bắt buộc, tùy chọn hoặc được lựa chọn theo dữ liệu runtime.
3. Thêm tham số constructor cho dependency bắt buộc; dùng interface phù hợp thay vì implementation cụ thể nếu có ranh giới cần bảo vệ.
4. Với nhiều implementation, cấu hình `@Qualifier`/`@Primary` hoặc tạo resolver nhận danh sách bean.
5. Với dependency optional/lazy/prototype, cân nhắc `Optional`, `ObjectProvider` hoặc factory.
6. Xóa trường `ApplicationContext` và các lookup đã được thay thế.
7. Cập nhật unit test để tạo service bằng constructor với fake/mock.
8. Dùng test context để xác nhận Spring vẫn tìm và kết nối đúng bean ở môi trường tương ứng.

Không nên chuyển đổi cơ học bằng cách thêm tất cả bean vào constructor nếu class thực chất đang điều phối quá nhiều chức năng. Có thể cần chia class trước hoặc trong quá trình chuyển đổi để giữ mỗi service một trách nhiệm dễ hiểu.

## 18. Đọc lỗi sau khi chuyển sang dependency tường minh

Sau khi thay lookup bằng constructor injection, một số lỗi có thể xuất hiện sớm hơn lúc ứng dụng khởi động. Đây thường là dấu hiệu hữu ích vì container phát hiện đồ thị chưa hoàn chỉnh.

| Thông báo hoặc triệu chứng | Ý nghĩa thường gặp | Hướng điều tra |
|---|---|---|
| `NoSuchBeanDefinitionException` | Không có bean phù hợp với dependency bắt buộc | Component scan, `@Bean`, profile, conditional, classpath |
| `NoUniqueBeanDefinitionException` | Có nhiều bean phù hợp nhưng chưa có lựa chọn rõ | `@Qualifier`, `@Primary`, danh sách/registry |
| `UnsatisfiedDependencyException` | Một dependency trong chuỗi khởi tạo không thỏa | Đọc các nguyên nhân lồng nhau để tìm bean gốc |
| Circular dependency error | Các bean tạo thành vòng phụ thuộc | Tách trách nhiệm và thiết kế hướng gọi một chiều |
| Context chạy được nhưng lookup lỗi khi gọi phương thức | Lookup bị trì hoãn tới runtime hoặc chỉ xảy ra ở nhánh hiếm | Tìm các lần `getBean` còn lại và điều kiện thực thi |
| Test đơn vị cần khởi động cả ứng dụng | Class phụ thuộc container hoặc quá nhiều thành phần | Tách logic, inject dependency, dùng fake/mock |

Constructor injection không đảm bảo ứng dụng không còn lỗi runtime. Nó giúp những dependency **bắt buộc và có thể giải quyết lúc khởi tạo** được kiểm tra sớm hơn. Lỗi database mất kết nối, thanh toán thất bại hoặc dữ liệu sai vẫn cần xử lý ở use case tương ứng.

## 19. Bài tập tư duy

Giả sử ứng dụng Spring Boot có một service:

~~~java
@Service
public class ShippingService {
    private final ApplicationContext context;

    public ShippingService(ApplicationContext context) {
        this.context = context;
    }

    public void ship(ShipmentCommand command) {
        ShipmentRepository repository =
                context.getBean(ShipmentRepository.class);

        ShippingProvider provider =
                context.getBean("expressProvider",
                        ShippingProvider.class);

        // Tạo shipment và gọi nhà vận chuyển.
    }
}
~~~

Hãy phân tích:

1. Những dependency thực sự của `ShippingService` là gì?
2. Vì sao người review không thể biết đầy đủ chúng chỉ từ constructor?
3. Nếu `ShippingProvider` thiếu bean, lỗi sẽ xuất hiện ở thời điểm nào?
4. Có cần `ShippingProvider` là dependency tùy chọn hay bắt buộc?
5. Nếu có `ExpressProvider` và `EconomyProvider`, nên chọn bằng qualifier cố định hay resolver theo lựa chọn giao hàng của khách?
6. Làm thế nào để test logic tạo shipment mà không khởi động Spring?
7. Nếu provider đến từ SDK bên ngoài, nên tạo bean ở lớp nào?

Một thiết kế có thể là `ShippingService(ShipmentRepository, ShippingProviderResolver)`. Resolver nhận các provider được inject tường minh và lựa chọn theo một kiểu `ShippingMethod` đã được xác thực. Như vậy, service vẫn thể hiện những gì nó cần; lựa chọn runtime nằm trong một thành phần có trách nhiệm riêng.

## 20. Những nguyên tắc cần giữ

- **Dependency bắt buộc nên xuất hiện trong constructor.** Đừng giấu chúng sau một tham chiếu `ApplicationContext`.
- **Business service nên phụ thuộc vào hợp đồng có ý nghĩa.** Service không cần biết bean được đăng ký bằng `@Component`, `@Bean` hay auto-configuration.
- **Dữ liệu nghiệp vụ nên đi qua tham số hoặc object command.** Không dùng dữ liệu request để ghép bean name và tra cứu container.
- **Lựa chọn động nên được đóng gói trong resolver/registry có kiểu.** Inject tập hợp implementation thay vì yêu cầu context tìm bean tùy ý.
- **Optional và lazy phải là nhu cầu thật.** Dùng `Optional` hoặc `ObjectProvider` khi việc vắng mặt hoặc trì hoãn được thiết kế rõ ràng.
- **Context lookup nên được giới hạn ở ranh giới hạ tầng cần nó.** Nếu không thể tránh, bọc trong adapter có API hẹp.
- **Không dùng Service Locator để che class có quá nhiều trách nhiệm.** Constructor dài là tín hiệu cần xem xét thiết kế.
- **Kiểm thử theo đúng tầng.** Unit test cho logic bằng constructor Java; integration test cho wiring và cấu hình Spring.

## Kết luận

Spring ApplicationContext có thể tra cứu bean, nhưng khả năng đó không nên trở thành cách mặc định để service nghiệp vụ lấy mọi cộng tác viên. **Giữ dependency tường minh** bằng constructor injection giúp người đọc thấy cấu trúc đối tượng, giúp container phát hiện dependency bắt buộc ngay khi khởi tạo và giúp unit test không cần phụ thuộc vào toàn bộ Spring context.

Khi cần lựa chọn động, nhiều implementation, dependency tùy chọn hoặc tạo instance muộn, hãy biểu đạt nhu cầu bằng một resolver, registry, factory, `Optional` hoặc `ObjectProvider` có kiểu. Nếu thật sự cần truy cập ApplicationContext, hãy giới hạn nó trong phần hạ tầng có trách nhiệm rõ. Nhờ vậy, container tiếp tục làm đúng vai trò lắp ghép object graph, còn mã nghiệp vụ tập trung vào quy tắc và hành vi mà ứng dụng cần cung cấp.
