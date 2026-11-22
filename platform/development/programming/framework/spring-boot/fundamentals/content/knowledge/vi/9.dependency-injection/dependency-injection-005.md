# Tiêm bean theo interface để tách mã nghiệp vụ khỏi phần hiện thực

Một service trong ứng dụng Spring Boot có thể cần gửi email, ghi dữ liệu, tính phí thanh toán hoặc gọi một dịch vụ bên ngoài. Nếu service tự tạo và gọi trực tiếp một class cụ thể, logic nghiệp vụ sẽ bị gắn với cách thực hiện kỹ thuật đó. Khi muốn thay nhà cung cấp, chuyển sang môi trường khác hoặc kiểm thử mà không gọi hệ thống thật, bạn phải sửa hoặc dựng lại nhiều thành phần.

Một cách thiết kế linh hoạt là để mã nghiệp vụ phụ thuộc vào **interface mô tả khả năng nó cần**, sau đó để Spring IoC container tiêm một bean triển khai interface ấy vào service.

Ví dụ:

~~~java
public interface PaymentGateway {
    PaymentResult charge(Money amount);
}
~~~

Service chỉ cần biết hợp đồng `PaymentGateway`. Một class như `CardPaymentAdapter` có thể triển khai hợp đồng và gọi nhà cung cấp thanh toán. Khi cấu hình ứng dụng thay implementation, service vẫn giữ nguyên.

Bài học này tập trung vào cách **Dependency Injection theo interface** tách chính sách nghiệp vụ khỏi chi tiết hiện thực. Ta sẽ đi từ thiết kế Java thuần, nguyên lý Dependency Inversion, cách Spring đăng ký và chọn bean, đến kiểm thử và những lỗi thường gặp.

## 1. Vì sao mã nghiệp vụ không nên gắn chặt với một implementation?

Giả sử ứng dụng có chức năng đặt hàng. Khi tạo đơn, hệ thống cần gửi thông báo cho khách hàng.

Một cách viết ban đầu:

~~~java
public class OrderService {

    public void createOrder(String customerEmail) {
        // Lưu đơn hàng và xử lý các quy tắc nghiệp vụ...

        EmailNotificationSender sender =
                new EmailNotificationSender();

        sender.send(customerEmail, "Your order has been created.");
    }
}
~~~

Đoạn code dễ hiểu, nhưng `OrderService` đang chịu trách nhiệm cả hai việc:

- Điều phối nghiệp vụ tạo đơn hàng.
- Chọn và khởi tạo một cách gửi thông báo cụ thể.

Nếu sau này ứng dụng chuyển sang một nhà cung cấp email khác, dùng message queue hoặc chỉ muốn ghi thông báo ra console trong môi trường phát triển, service phải thay đổi dù quy tắc tạo đơn không đổi.

Đây là dạng **coupling (sự phụ thuộc/gắn kết)** trực tiếp vào chi tiết hiện thực.

### 1.1. Những hệ quả của phụ thuộc trực tiếp

**Khó thay đổi implementation.** Mỗi nơi gọi class cụ thể có thể phải sửa khi thay công nghệ.

**Khó kiểm thử độc lập.** Unit test của service có thể vô tình khởi tạo client thật, truy cập mạng hoặc cần cấu hình credential.

**Khó kiểm soát vòng đời.** Service tự tạo dependency nên Spring không quản lý object đó như một bean. Các cơ chế cấu hình, proxy, lifecycle hoặc thay thế bean không tự áp dụng cho object được tạo bằng `new`.

**Khó tách chính sách nghiệp vụ khỏi hạ tầng.** Quy tắc “khi nào cần gửi thông báo” bị trộn với quy tắc “gửi thông báo bằng SMTP hay HTTP”.

Không phải mọi lệnh `new` đều xấu. Tạo một value object nhỏ hoặc một đối tượng nội bộ không cần container thường hoàn toàn hợp lý. Vấn đề xuất hiện khi mã nghiệp vụ tự tạo các collaborator có vòng đời, cấu hình hoặc chi tiết hạ tầng mà nó không nên sở hữu.

## 2. Đưa interface vào giữa service và implementation

Thay vì phụ thuộc `EmailNotificationSender`, ta định nghĩa hợp đồng:

~~~java
public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

Implementation cụ thể:

~~~java
public class EmailNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        // Gọi email provider hoặc SMTP client.
    }
}
~~~

Service nhận interface qua constructor:

~~~java
public class OrderService {
    private final NotificationSender notificationSender;

    public OrderService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }

    public void createOrder(String customerEmail) {
        // Xử lý quy tắc tạo đơn hàng...

        notificationSender.send(
                customerEmail,
                "Your order has been created."
        );
    }
}
~~~

Đồ thị phụ thuộc đã thay đổi:

~~~mermaid
flowchart TD
    A["Trước: OrderService"] --> B["EmailNotificationSender"]
    C["Sau: OrderService"] --> D["NotificationSender interface"]
    E["EmailNotificationSender"] -. "implements" .-> D
~~~

Service chỉ biết khả năng cần thiết. Implementation chịu trách nhiệm thực hiện khả năng ấy.

Có thể thay implementation mà không sửa service:

~~~java
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println(recipient + ": " + message);
    }
}
~~~

Hoặc:

~~~java
public class QueueNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        // Đưa thông báo vào message queue.
    }
}
~~~

Cả ba class đều đáp ứng cùng contract. Đây là **polymorphism (đa hình)** của Java: mã gọi thông qua kiểu interface, còn method được thực thi là method của object runtime.

## 3. Interface là contract, không phải bản sao của implementation

Một interface tốt mô tả **điều mà consumer cần**, không phơi bày mọi thao tác nội bộ của nhà cung cấp.

Ví dụ service cần yêu cầu gửi một thông báo:

~~~java
public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

Consumer không cần biết:

- Email client kết nối SMTP ra sao.
- HTTP adapter thêm authorization header thế nào.
- Queue producer chọn topic nào.
- Nhà cung cấp có SDK và exception riêng nào.

Những chi tiết đó thuộc implementation.

### 3.1. Thiết kế interface theo nhu cầu sử dụng

Không nên tạo interface quá lớn:

~~~java
public interface NotificationPlatform {
    void sendEmail(String recipient, String subject, String body);
    void sendSms(String phoneNumber, String body);
    void publishKafkaMessage(String topic, String payload);
    void connectSmtp();
    void refreshProviderToken();
    void openAdminDashboard();
}
~~~

Một service chỉ cần gửi thông báo email lại bị phụ thuộc vào cả SMS, Kafka, SMTP và dashboard. Những implementation không hỗ trợ mọi thao tác sẽ khó tuân thủ contract.

Có thể tách thành các interface nhỏ, tập trung vào khả năng:

~~~java
public interface EmailSender {
    void send(String recipient, String subject, String body);
}

public interface SmsSender {
    void send(String phoneNumber, String message);
}
~~~

`OrderService` chỉ nhận interface phù hợp với trách nhiệm của nó. Đây là cách áp dụng **Interface Segregation Principle**: consumer không nên bị buộc phụ thuộc vào những method mà nó không sử dụng.

### 3.2. Contract nên mô tả cả ý nghĩa và hành vi lỗi

Một interface không chỉ là danh sách method. Nó còn cần có ý nghĩa rõ ràng:

- `send` gửi đồng bộ hay chỉ xếp hàng?
- Method trả về khi nhà cung cấp xác nhận hay khi request được tiếp nhận?
- Lỗi được ném ra dưới dạng exception nào?
- Consumer có thể retry không?
- Gửi trùng có thể gây tác dụng phụ gì?

Nếu contract nói “đã gửi” nhưng implementation chỉ “đã đưa vào queue”, consumer có thể hiểu sai kết quả. Tên method, kiểu trả về, exception và tài liệu cần thể hiện đúng ngữ nghĩa.

Ví dụ một contract rõ hơn khi cần kết quả:

~~~java
public interface NotificationSender {
    NotificationReceipt send(NotificationMessage message);
}
~~~

`NotificationMessage` và `NotificationReceipt` là các kiểu thuộc ứng dụng, mô tả nội dung yêu cầu và kết quả mà nghiệp vụ cần. Tránh trả trực tiếp một kiểu response riêng của SDK nhà cung cấp nếu điều đó khiến service phụ thuộc vào vendor.

## 4. Dependency Injection và Dependency Inversion khác nhau thế nào?

Hai thuật ngữ thường xuất hiện cùng nhau nhưng giải quyết hai câu hỏi khác nhau.

**Dependency Injection (DI)** trả lời: “Ai cung cấp object mà class này cần?” Thay vì tự tạo dependency, class nhận nó từ bên ngoài, thường qua constructor.

**Dependency Inversion Principle (DIP)** trả lời: “Các module nên phụ thuộc vào abstraction nào?” Nguyên lý này khuyến khích chính sách cấp cao không bị ràng buộc trực tiếp với chi tiết cấp thấp; cả hai nên phụ thuộc vào abstraction phù hợp.

Ví dụ:

~~~text
Chính sách nghiệp vụ:
OrderService
      │
      ▼
NotificationSender (abstraction)
      ▲
      │
Chi tiết hạ tầng:
EmailNotificationSender
~~~

`OrderService` là phần điều phối nghiệp vụ. `EmailNotificationSender` là chi tiết thực hiện gửi. Cả hai liên hệ qua `NotificationSender`.

### 4.1. DI không tự động bảo đảm DIP

Đây vẫn là Dependency Injection:

~~~java
public class OrderService {
    private final EmailNotificationSender sender;

    public OrderService(EmailNotificationSender sender) {
        this.sender = sender;
    }
}
~~~

Object được truyền từ ngoài, nhưng service vẫn phụ thuộc class cụ thể. DI đã có, nhưng ranh giới abstraction chưa được tạo.

Ngược lại, chỉ khai báo interface mà service tự tạo implementation cũng chưa phải DI đúng nghĩa:

~~~java
public class OrderService {
    private final NotificationSender sender =
            new EmailNotificationSender();
}
~~~

Service vẫn quyết định implementation và tự khởi tạo nó.

Thiết kế thường mong muốn kết hợp cả hai:

1. Interface thể hiện khả năng cần dùng.
2. Service nhận interface qua constructor.
3. Một thành phần cấu hình hoặc IoC container chọn implementation.
4. Spring quản lý và kết nối các bean.

## 5. Constructor injection trong Java thuần

Trước khi dùng Spring, hãy hiểu cơ chế bằng Java thuần.

~~~java
public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

Implementation:

~~~java
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("[CONSOLE] " + recipient + ": " + message);
    }
}
~~~

Service:

~~~java
public class OrderService {
    private final NotificationSender sender;

    public OrderService(NotificationSender sender) {
        this.sender = sender;
    }

    public void createOrder(String email) {
        // Giả lập quy tắc tạo đơn hàng thành công.
        sender.send(email, "Order created.");
    }
}
~~~

Composition root (điểm lắp ghép đối tượng) có thể là `main`:

~~~java
public class Main {
    public static void main(String[] args) {
        NotificationSender sender = new ConsoleNotificationSender();
        OrderService orderService = new OrderService(sender);

        orderService.createOrder("lan@example.com");
    }
}
~~~

Kết quả:

~~~text
[CONSOLE] lan@example.com: Order created.
~~~

Nếu muốn dùng implementation khác, chỉ thay phần lắp ghép:

~~~java
NotificationSender sender = new EmailNotificationSender();
OrderService orderService = new OrderService(sender);
~~~

`OrderService` không cần thay đổi.

**Constructor injection** đặc biệt phù hợp với dependency bắt buộc vì:

- Constructor thể hiện rõ các cộng tác viên mà class cần.
- Object không thể được tạo theo constructor này nếu thiếu dependency.
- Field có thể là `final`.
- Unit test dễ tạo object bằng cách truyền fake implementation.
- Không cần khởi tạo Spring context chỉ để kiểm tra logic service.

Spring sẽ thực hiện phần lắp ghép tương tự trong ứng dụng thật.

## 6. Đăng ký implementation thành Spring bean

Spring IoC container chỉ có thể inject một implementation nếu bean đó đã được đăng ký và phù hợp với điều kiện cấu hình.

Có hai cách thường dùng.

### 6.1. Component scan

Đánh dấu implementation:

~~~java
import org.springframework.stereotype.Component;

@Component
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("[CONSOLE] " + recipient + ": " + message);
    }
}
~~~

Nếu package của class nằm trong phạm vi component scan, Spring đăng ký bean definition cho implementation.

Service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final NotificationSender sender;

    public OrderService(NotificationSender sender) {
        this.sender = sender;
    }

    public void createOrder(String email) {
        sender.send(email, "Order created.");
    }
}
~~~

Khi tạo `OrderService`, Spring tìm bean đáp ứng kiểu `NotificationSender`. `ConsoleNotificationSender` implements interface nên có thể được chọn nếu không có candidate nhập nhằng.

### 6.2. Factory method @Bean

Nếu implementation thuộc thư viện ngoài hoặc bạn muốn tự kiểm soát cách tạo object, khai báo trong class cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class NotificationConfiguration {

    @Bean
    public NotificationSender notificationSender() {
        return new ConsoleNotificationSender();
    }
}
~~~

Phương thức `@Bean` công bố bean qua kiểu interface. Object runtime vẫn là `ConsoleNotificationSender`.

Service tiếp tục inject interface:

~~~java
@Service
public class OrderService {
    private final NotificationSender sender;

    public OrderService(NotificationSender sender) {
        this.sender = sender;
    }
}
~~~

Ở đây, cấu hình chịu trách nhiệm lựa chọn implementation. Service chỉ sử dụng contract.

### 6.3. Vì sao không tự gọi getBean() trong service?

Một cách viết không nên dùng làm mặc định:

~~~java
@Service
public class OrderService {
    private final NotificationSender sender;

    public OrderService(ApplicationContext context) {
        this.sender = context.getBean(NotificationSender.class);
    }
}
~~~

Cách này khiến service phụ thuộc trực tiếp vào container và tự truy vấn dependency. Nó chuyển service sang mô hình **Service Locator** thay vì để container inject dependency qua constructor.

Constructor injection rõ ràng hơn vì:

- Các dependency thể hiện ngay trên chữ ký constructor.
- Service không cần biết Spring ApplicationContext.
- Unit test không cần tạo hoặc giả lập container.
- Logic nghiệp vụ có thể dùng ngoài Spring nếu cần.

Hãy để Spring điều phối object ở ranh giới ứng dụng; giữ service tập trung vào nghiệp vụ.

## 7. Ví dụ Spring Boot hoàn chỉnh: nghiệp vụ tạo đơn dùng interface

Ta xây một ví dụ nhỏ có controller, service và sender. Phần gửi thông báo mặc định ghi ra console, nhưng service không biết điều đó.

### 7.1. Cấu trúc project

~~~text
order-notification/
└── src/main/java/com/example/orders/
    ├── OrderApplication.java
    ├── application/
    │   ├── NotificationSender.java
    │   └── OrderService.java
    ├── infrastructure/
    │   └── ConsoleNotificationSender.java
    └── web/
        └── OrderController.java
~~~

Cách chia package trên thể hiện ranh giới trách nhiệm:

- `application` chứa contract và use case nghiệp vụ.
- `infrastructure` chứa implementation kỹ thuật.
- `web` chứa adapter nhận HTTP request.

Đây là một cách tổ chức minh họa; dự án nhỏ có thể dùng cấu trúc đơn giản hơn miễn là ranh giới dependency rõ ràng.

### 7.2. Lớp khởi động

`OrderApplication.java`:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Đặt lớp này ở package gốc để component scan mặc định phát hiện các package con.

### 7.3. Interface nghiệp vụ cần dùng

`application/NotificationSender.java`:

~~~java
package com.example.orders.application;

public interface NotificationSender {
    void sendOrderCreated(String recipient, String orderId);
}
~~~

Contract được đặt trong application layer vì use case tạo đơn là bên cần khả năng gửi thông báo. Tên method diễn đạt hành vi nghiệp vụ cần thiết, không phơi bày cách gửi email hay tên API của một vendor.

### 7.4. Service nghiệp vụ

`application/OrderService.java`:

~~~java
package com.example.orders.application;

import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
public class OrderService {
    private final NotificationSender notificationSender;

    public OrderService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }

    public String createOrder(String customerEmail) {
        String orderId = UUID.randomUUID().toString();

        // Ở ứng dụng thực tế, đây là nơi kiểm tra và lưu đơn hàng.
        notificationSender.sendOrderCreated(customerEmail, orderId);

        return orderId;
    }
}
~~~

Service tạo mã đơn hàng, thực hiện phần nghiệp vụ minh họa và gọi contract. Nó không import implementation cụ thể.

Trong hệ thống thật, cần xác định rõ thứ tự lưu đơn và gửi thông báo, transaction boundary, retry, idempotency và cách xử lý khi gửi thất bại. Ví dụ hiện tại chỉ tập trung vào dependency wiring.

### 7.5. Implementation hạ tầng

`infrastructure/ConsoleNotificationSender.java`:

~~~java
package com.example.orders.infrastructure;

import com.example.orders.application.NotificationSender;
import org.springframework.stereotype.Component;

@Component
public class ConsoleNotificationSender implements NotificationSender {

    @Override
    public void sendOrderCreated(String recipient, String orderId) {
        System.out.printf(
                "[NOTIFICATION] To=%s, orderId=%s%n",
                recipient,
                orderId
        );
    }
}
~~~

Class này thực hiện contract và nằm ở infrastructure. Nó có thể được thay bằng email provider hoặc queue adapter mà không cần sửa `OrderService`.

### 7.6. Controller

`web/OrderController.java`:

~~~java
package com.example.orders.web;

import com.example.orders.application.OrderService;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public CreateOrderResponse create(@RequestParam String email) {
        String orderId = orderService.createOrder(email);
        return new CreateOrderResponse(orderId);
    }

    public record CreateOrderResponse(String orderId) {
    }
}
~~~

Controller chỉ nhận HTTP request và gọi use case. Nó cũng không cần biết implementation sender.

### 7.7. Luồng runtime

~~~mermaid
flowchart TD
    A["HTTP POST /orders?email=..."] --> B["OrderController"]
    B --> C["OrderService"]
    C --> D["NotificationSender interface"]
    E["ConsoleNotificationSender bean"] -. "implements" .-> D
    D --> E
    E --> F["Ghi thông báo ra console"]
    C --> G["Trả orderId"]
    G --> B
    B --> H["HTTP response"]
~~~

Trong lúc startup, Spring phát hiện controller, service và sender component. Khi tạo `OrderService`, container inject bean `ConsoleNotificationSender` thông qua kiểu `NotificationSender`.

Khi request đến, service gọi method trên interface. Java dynamic dispatch chuyển lời gọi đến implementation của object runtime.

### 7.8. Chạy ứng dụng

Với Maven project đã khai báo `spring-boot-starter-web` và Spring Boot Maven plugin:

~~~bash
mvn spring-boot:run
~~~

Gửi request:

~~~bash
curl -X POST "http://localhost:8080/orders?email=lan@example.com"
~~~

Response có dạng:

~~~json
{
  "orderId": "một-uuid-được-tạo-khi-chạy"
}
~~~

Trong console của ứng dụng, có log tương tự:

~~~text
[NOTIFICATION] To=lan@example.com, orderId=...
~~~

Mã UUID thay đổi theo mỗi lần gọi. Kết quả cho thấy request đi qua controller, service và implementation sender đã được inject.

## 8. Thay implementation theo môi trường mà không sửa service

Một ứng dụng có thể dùng console sender ở local, email sender ở production hoặc fake sender trong test.

### 8.1. Dùng @Profile

Tạo implementation console chỉ hoạt động trong profile `dev`:

~~~java
@Component
@Profile("dev")
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void sendOrderCreated(String recipient, String orderId) {
        System.out.println("[DEV] " + recipient + ": " + orderId);
    }
}
~~~

Implementation production:

~~~java
@Component
@Profile("prod")
public class EmailNotificationSender implements NotificationSender {
    @Override
    public void sendOrderCreated(String recipient, String orderId) {
        // Gửi thông báo qua email provider đã cấu hình.
    }
}
~~~

Khi kích hoạt `dev`, bean console được đăng ký. Khi kích hoạt `prod`, bean email được đăng ký. Mỗi profile phải cung cấp một bean đáp ứng contract nếu `OrderService` cần nó.

Kích hoạt bằng file cấu hình:

~~~properties
spring.profiles.active=dev
~~~

Hoặc tham số dòng lệnh:

~~~bash
java -jar order-notification.jar --spring.profiles.active=prod
~~~

Ví dụ này yêu cầu cả hai class có import `org.springframework.context.annotation.Profile`. Tên file JAR chỉ mang tính minh họa.

Profile là cơ chế lựa chọn cấu hình/bean theo môi trường. Nó không tự bảo vệ endpoint và không thay thế quản lý secret. Email provider vẫn cần cấu hình credentials an toàn.

### 8.2. Dùng @ConditionalOnProperty

Khi muốn lựa chọn implementation bằng thuộc tính, có thể dùng điều kiện Spring Boot:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "notification.mode",
            havingValue = "console",
            matchIfMissing = true
    )
    NotificationSender consoleSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @ConditionalOnProperty(
            name = "notification.mode",
            havingValue = "email"
    )
    NotificationSender emailSender(EmailClient emailClient) {
        return new EmailNotificationSender(emailClient);
    }
}
~~~

`EmailClient` là dependency giả định cần được đăng ký/cấu hình riêng. `EmailNotificationSender` ở đây có constructor nhận `EmailClient`.

Cấu hình:

~~~properties
notification.mode=console
~~~

Hoặc:

~~~properties
notification.mode=email
~~~

Điều kiện giúp chọn bean dựa trên thuộc tính. Nếu chọn email nhưng thiếu `EmailClient`, context vẫn không thể tạo bean tương ứng. Điều kiện không tự cung cấp hạ tầng mà implementation yêu cầu.

### 8.3. Dùng @Qualifier khi có nhiều implementation cùng tồn tại

Nếu ứng dụng cần cả console và email sender cùng lúc, không nên dùng profile để loại một trong hai. Đăng ký cả hai với qualifier:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    @Qualifier("console")
    NotificationSender consoleSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @Qualifier("email")
    NotificationSender emailSender(EmailClient emailClient) {
        return new EmailNotificationSender(emailClient);
    }
}
~~~

Consumer chọn rõ bean:

~~~java
@Service
public class OrderService {
    private final NotificationSender sender;

    public OrderService(@Qualifier("email") NotificationSender sender) {
        this.sender = sender;
    }
}
~~~

`@Qualifier` lọc các candidate theo qualifier. Tên bean mặc định cũng có thể tham gia lựa chọn theo tên trong một số trường hợp, nhưng qualifier tường minh giúp thể hiện ý định rõ ràng.

### 8.4. Khi nào dùng @Primary?

Nếu có nhiều bean cùng kiểu và một bean nên là lựa chọn mặc định:

~~~java
@Bean
@Primary
NotificationSender consoleSender() {
    return new ConsoleNotificationSender();
}
~~~

`@Primary` ưu tiên bean này khi injection point yêu cầu một bean và không có qualifier cụ thể hơn. Nó không xóa những implementation còn lại.

Hãy dùng `@Primary` khi thực sự có một lựa chọn mặc định hợp lý. Nếu từng consumer cần lựa chọn khác nhau, `@Qualifier` thường rõ ràng hơn.

## 9. Kiểm thử service độc lập với implementation thật

Một lợi ích trực tiếp của interface injection là có thể test service mà không cần khởi động Spring context hay gọi hệ thống bên ngoài.

### 9.1. Dùng fake implementation

Tạo fake sender trong test:

~~~java
class RecordingNotificationSender implements NotificationSender {
    private String recipient;
    private String orderId;

    @Override
    public void sendOrderCreated(String recipient, String orderId) {
        this.recipient = recipient;
        this.orderId = orderId;
    }

    String recipient() {
        return recipient;
    }

    String orderId() {
        return orderId;
    }
}
~~~

Test service bằng Java/JUnit:

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderServiceTest {

    @Test
    void createsOrderAndRequestsNotification() {
        RecordingNotificationSender sender =
                new RecordingNotificationSender();

        OrderService service = new OrderService(sender);

        String orderId = service.createOrder("lan@example.com");

        assertNotNull(orderId);
        assertEquals("lan@example.com", sender.recipient());
        assertEquals(orderId, sender.orderId());
    }
}
~~~

Test này:

- Tạo fake implementation.
- Truyền fake vào constructor của service.
- Gọi use case.
- Xác nhận service đã yêu cầu gửi thông báo với dữ liệu phù hợp.

Không cần `@SpringBootTest` vì mục tiêu là kiểm tra logic service và cách service cộng tác với contract. Test cũng không gọi email provider thật.

### 9.2. Dùng Mockito khi cần xác minh tương tác

Nếu dự án đã dùng Mockito qua `spring-boot-starter-test`:

~~~java
import org.junit.jupiter.api.Test;

import static org.mockito.Mockito.*;

class OrderServiceMockitoTest {

    @Test
    void sendsNotificationAfterCreatingOrder() {
        NotificationSender sender = mock(NotificationSender.class);
        OrderService service = new OrderService(sender);

        String orderId = service.createOrder("lan@example.com");

        verify(sender).sendOrderCreated("lan@example.com", orderId);
    }
}
~~~

Mockito tạo mock của interface và ghi nhận lời gọi để test có thể xác minh tương tác. Fake thường hữu ích khi muốn có hành vi đơn giản, còn mock phù hợp khi cần xác nhận method nào được gọi với tham số gì.

Không nên lạm dụng mock để kiểm tra từng chi tiết nội bộ của service. Hãy kiểm tra hành vi có ý nghĩa đối với contract.

### 9.3. Unit test khác integration test

| Loại kiểm thử | Mục tiêu | Có cần Spring context? |
| --- | --- | --- |
| Unit test service | Logic nghiệp vụ và tương tác qua interface | Thường không |
| Integration test wiring | Bean được đăng ký và inject đúng trong context | Có |
| Web integration test | Endpoint, controller, service và adapter phối hợp | Thường có |
| Contract/integration test adapter | Implementation giao tiếp đúng với hệ thống ngoài hoặc sandbox | Tùy cách thiết kế |

Một unit test pass không chứng minh Spring đã đăng ký bean đúng profile. Ngược lại, context khởi động thành công cũng không chứng minh quy tắc nghiệp vụ đúng. Mỗi loại test trả lời một câu hỏi riêng.

## 10. Tách contract khỏi thư viện của nhà cung cấp

Giả sử ứng dụng dùng một SDK thanh toán cụ thể. Không nên để service nghiệp vụ nhận trực tiếp request/response type của SDK nếu điều đó khiến toàn bộ tầng nghiệp vụ phụ thuộc vendor.

Thay vào đó, tạo contract của ứng dụng:

~~~java
public interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}
~~~

Các kiểu `PaymentRequest` và `PaymentResult` nên là kiểu thuộc ứng dụng, mô tả dữ liệu và kết quả nghiệp vụ cần thiết.

Implementation chuyển đổi giữa contract nội bộ và SDK:

~~~java
@Component
public class VendorPaymentAdapter implements PaymentGateway {

    private final VendorPaymentClient client;

    public VendorPaymentAdapter(VendorPaymentClient client) {
        this.client = client;
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        VendorChargeRequest vendorRequest =
                new VendorChargeRequest(request.amount());

        VendorChargeResponse response =
                client.charge(vendorRequest);

        return new PaymentResult(
                response.transactionId(),
                response.approved()
        );
    }
}
~~~

Các kiểu `VendorPaymentClient`, `VendorChargeRequest` và `VendorChargeResponse` là kiểu giả định của SDK. Adapter chuyển đổi giữa mô hình của ứng dụng và API của nhà cung cấp.

Đồ thị:

~~~mermaid
flowchart LR
    A["OrderService / application policy"] --> B["PaymentGateway (port/interface)"]
    C["VendorPaymentAdapter"] -. "implements" .-> B
    C --> D["Vendor SDK"]
    D --> E["Payment Provider"]
~~~

Đây là ý tưởng của **Ports and Adapters (Hexagonal Architecture)**:

- Port là contract mà application cần.
- Adapter là thành phần chuyển đổi contract đó sang một công nghệ cụ thể.
- Spring DI giúp kết nối port với adapter phù hợp lúc runtime.

Không nhất thiết mọi ứng dụng Spring Boot đều phải triển khai đầy đủ kiến trúc Hexagonal. Nhưng tư duy ranh giới này rất hữu ích khi ứng dụng tích hợp nhiều hệ thống ngoài.

## 11. Đặt interface ở đâu trong kiến trúc?

Một câu hỏi quan trọng là: interface thuộc package của service hay package của infrastructure?

Nếu interface được tạo ra để phục vụ nhu cầu của application, có thể đặt nó ở application layer:

~~~text
com.example.orders
├── application
│   ├── OrderService.java
│   └── port
│       └── out
│           └── NotificationSender.java
└── infrastructure
    └── notification
        └── EmailNotificationAdapter.java
~~~

Lúc này:

- Application định nghĩa contract cần thiết.
- Infrastructure phụ thuộc contract để triển khai.
- Application không import package của vendor hoặc adapter.
- Spring configuration lắp ghép hai phía.

Cách tổ chức khác cũng có thể hợp lý trong dự án nhỏ. Điều quan trọng là **hướng dependency trong mã nguồn** phải phù hợp: nghiệp vụ không bị kéo theo chi tiết kỹ thuật mà nó sử dụng.

Một interface đặt trong infrastructure rồi được application import có thể khiến hướng phụ thuộc ngược với mục tiêu ban đầu. Hãy đặt abstraction ở nơi sở hữu nhu cầu về nó, trừ khi có lý do kiến trúc cụ thể khác.

## 12. Khi nào nên tạo interface, khi nào không?

Không phải mọi class đều cần một interface riêng. Tạo abstraction chỉ có ích khi nó thể hiện một ranh giới thực sự.

### Nên cân nhắc interface khi:

- Có nhiều implementation hợp lệ hoặc khả năng thay đổi implementation là yêu cầu thực tế.
- Thành phần là ranh giới với hệ thống ngoài: email, payment, storage, messaging, external API.
- Muốn kiểm thử service độc lập với hạ tầng.
- Muốn tách chính sách nghiệp vụ khỏi cách thực hiện.
- Cần module khác cung cấp implementation theo một contract ổn định.
- Muốn thay implementation theo môi trường hoặc cấu hình.

### Chưa cần tạo interface chỉ vì:

- Class chỉ là một value object đơn giản.
- Không có ranh giới biến thể hoặc cộng tác viên cần thay thế.
- Interface chỉ lặp lại nguyên xi mọi method của một class mà không mang ý nghĩa contract.
- Tạo interface khiến người đọc phải nhảy qua nhiều file mà không cải thiện khả năng hiểu hay thay đổi.
- Chưa rõ consumer cần abstraction nào.

Một service có thể inject class cụ thể nếu class đó là dependency ổn định và không có lý do để trừu tượng hóa. Thiết kế tốt không đo bằng số interface mà đo bằng mức độ rõ ràng của trách nhiệm và dependency.

## 13. Các lỗi thường gặp khi inject theo interface

### 13.1. Không có bean nào triển khai interface

Service:

~~~java
@Service
public class OrderService {
    public OrderService(NotificationSender sender) {
        // ...
    }
}
~~~

Nhưng chưa có implementation nào được đăng ký. Spring có thể báo:

~~~text
No qualifying bean of type 'NotificationSender' available
~~~

Cách xử lý:

- Tạo implementation phù hợp.
- Đăng ký bằng `@Component` hoặc `@Bean`.
- Kiểm tra package scan và điều kiện profile.
- Kiểm tra cấu hình auto-configuration nếu bean dự kiến được starter cung cấp.

Spring không tự tạo implementation cho interface do ứng dụng định nghĩa.

### 13.2. Có nhiều bean cùng triển khai interface

Nếu `ConsoleNotificationSender` và `EmailNotificationSender` đều được đăng ký mà service chỉ yêu cầu `NotificationSender`, Spring có thể báo `NoUniqueBeanDefinitionException`.

Dùng `@Qualifier` để chọn rõ, `@Primary` để đặt mặc định, hoặc dùng profile/condition để chỉ đăng ký implementation phù hợp.

Đừng đổi service sang class cụ thể chỉ để né thông báo lỗi nếu nghiệp vụ thực sự chỉ cần interface.

### 13.3. Implementation không nằm trong component scan

Một class có `@Component` nhưng nằm ngoài package scan vẫn có thể không được đăng ký.

Kiểm tra package chứa `@SpringBootApplication`, vị trí implementation và cấu hình scan. Nếu class thuộc module ngoài, có thể đăng ký qua `@Bean` trong cấu hình được import phù hợp.

### 13.4. Service tự tạo implementation bằng new

~~~java
@Service
public class OrderService {
    private final NotificationSender sender =
            new ConsoleNotificationSender();
}
~~~

Cách này bỏ qua bean mà Spring có thể quản lý và khóa service vào implementation. Hãy chuyển dependency sang constructor:

~~~java
public OrderService(NotificationSender sender) {
    this.sender = sender;
}
~~~

### 13.5. Interface làm lộ chi tiết của vendor

Nếu contract trả về một object response riêng của SDK, service vẫn phụ thuộc nhà cung cấp dù đã có interface.

Hãy chuyển đổi sang kiểu dữ liệu do ứng dụng sở hữu. Adapter là nơi xử lý mapping và dịch lỗi giữa hai mô hình.

### 13.6. Circular dependency

Nếu `OrderService` cần `NotificationService`, còn `NotificationService` lại cần `OrderService`, hai dependency có thể tạo vòng.

Đừng vội dùng setter hoặc lazy injection để che vòng phụ thuộc. Xem lại trách nhiệm và tách logic chung hoặc orchestration thành thành phần khác nếu phù hợp.

### 13.7. Interface quá rộng hoặc thiếu ngữ nghĩa

Một contract có nhiều method không liên quan khiến implementation giả và test trở nên khó viết. Tách theo vai trò consumer, đặt tên method rõ nghĩa và mô tả hành vi lỗi.

## 14. Lựa chọn implementation không nên nằm trong service

Một dấu hiệu thiết kế chưa tốt là service tự chọn implementation:

~~~java
public class OrderService {
    public OrderService(boolean useEmail) {
        if (useEmail) {
            // tự tạo EmailNotificationSender
        } else {
            // tự tạo ConsoleNotificationSender
        }
    }
}
~~~

Service đang biết cả các implementation và quy tắc môi trường. Nếu thay nhà cung cấp, code nghiệp vụ lại phải thay đổi.

Đưa quyết định sang configuration:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    @Profile("dev")
    NotificationSender devSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @Profile("prod")
    NotificationSender productionSender(EmailClient emailClient) {
        return new EmailNotificationSender(emailClient);
    }
}
~~~

Đây là ví dụ minh họa; `EmailClient` phải được cấu hình riêng. Mỗi profile phải đảm bảo chỉ có một candidate phù hợp nếu consumer yêu cầu một `NotificationSender` duy nhất.

Lúc này, service không cần biết môi trường đang chạy. Container quyết định bean theo cấu hình, rồi inject contract vào service.

## 15. Transaction, exception và tác dụng phụ vẫn cần thiết kế

Tách implementation qua interface không tự giải quyết mọi vấn đề vận hành.

Ví dụ, service lưu đơn rồi gọi sender:

~~~java
public String createOrder(Order order) {
    repository.save(order);
    notificationSender.sendOrderCreated(order.customerEmail(), order.id());
    return order.id();
}
~~~

Nếu database commit nhưng gửi thông báo thất bại, trạng thái hệ thống có thể không nhất quán với kỳ vọng nghiệp vụ. Nếu gửi trước khi transaction commit, thông báo có thể được gửi dù transaction sau đó rollback.

Đây là vấn đề **thời điểm và tính nhất quán của side effect**, không phải chỉ là cách inject interface.

Một hệ thống thực tế có thể cần:

- Gửi event sau khi transaction commit.
- Transactional outbox để lưu sự kiện cùng transaction dữ liệu.
- Retry có giới hạn và xử lý idempotency.
- Ghi nhận trạng thái gửi và khả năng xử lý lỗi.
- Tách thao tác đồng bộ khỏi xử lý bất đồng bộ nếu phù hợp.

Interface giúp tách nơi gọi khỏi công nghệ gửi, nhưng contract vẫn phải mô tả đúng semantics và application phải thiết kế độ tin cậy phù hợp.

## 16. Bài thực hành

### Bài A: Chuyển phụ thuộc từ class sang interface

Cho service ban đầu:

~~~java
public class ReportService {
    private final PdfReportExporter exporter;

    public ReportService() {
        this.exporter = new PdfReportExporter();
    }

    public void export(Report report) {
        exporter.export(report);
    }
}
~~~

Hãy:

1. Tạo interface `ReportExporter`.
2. Cho `PdfReportExporter` implements interface.
3. Thay constructor `ReportService` để nhận `ReportExporter`.
4. Tạo object trong `main` và truyền implementation vào.
5. Thêm một `CsvReportExporter` mà không sửa logic service.

Mục tiêu: phân biệt phần nghiệp vụ yêu cầu “export report” với chi tiết xuất PDF/CSV.

### Bài B: Đăng ký hai bean Spring

Tạo hai bean cùng implements `NotificationSender`:

- `ConsoleNotificationSender`.
- `EmailNotificationSender`.

Cho `OrderService` nhận `NotificationSender`. Quan sát lỗi nếu không có lựa chọn. Sau đó sửa bằng `@Qualifier` hoặc `@Primary`.

Hãy giải thích tại sao lỗi xuất hiện ở bước khởi tạo context chứ không phải lúc gửi thông báo.

### Bài C: Dùng profile

Đăng ký console sender cho `dev` và email sender cho `prod`. Chạy ứng dụng với từng profile. Xác nhận log cho thấy implementation phù hợp mà service không thay đổi.

### Bài D: Unit test bằng fake

Tạo `RecordingNotificationSender` để lưu recipient và message nhận được. Tạo `OrderServiceTest` bằng constructor injection thuần Java. Xác nhận use case truyền đúng dữ liệu cho sender.

Không cần tạo Spring context trong unit test này. Sau đó viết một integration test riêng nếu muốn xác minh bean wiring.

### Bài E: Thiết kế contract cho hệ thống ngoài

Ứng dụng cần lưu file vào local disk trong môi trường dev và object storage trong production.

Hãy thiết kế:

~~~java
public interface DocumentStorage {
    StoredDocument store(DocumentContent content);
}
~~~

Tạo hai implementation tương ứng và quyết định:

- Interface nên nằm ở package nào?
- Kiểu dữ liệu nào thuộc application?
- API riêng của object storage nên được che ở đâu?
- Spring chọn implementation theo profile hay property?
- Test service bằng fake storage thế nào?

Bài tập này giúp áp dụng cùng nguyên lý sang một ranh giới hạ tầng khác.

## 17. Câu hỏi tự kiểm tra

**1. Vì sao service nên nhận interface thay vì implementation cụ thể?**

Vì service chỉ cần một khả năng, còn cách thực hiện có thể thay đổi. Interface giữ contract ổn định và giảm coupling đến hạ tầng.

**2. Interface có tự làm cho dependency được inject không?**

Không. Cần có bean implementation đã được đăng ký và có thể được Spring chọn cho injection point.

**3. Dependency Injection và Dependency Inversion có giống nhau không?**

Không. DI là kỹ thuật cung cấp dependency từ bên ngoài; DIP là nguyên lý thiết kế hướng dependency đến abstraction phù hợp.

**4. Khi có hai bean cùng implements một interface, Spring làm gì?**

Nếu injection point yêu cầu một bean duy nhất mà không có quy tắc chọn rõ ràng, Spring có thể báo lỗi nhiều candidate. Dùng qualifier, primary, profile/condition hoặc inject collection theo nhu cầu.

**5. Tại sao constructor injection thường được ưu tiên?**

Vì dependency bắt buộc được thể hiện rõ, object có thể dùng ngay sau khi tạo hợp lệ, field có thể final và unit test dễ viết bằng Java thuần.

**6. Có nên tạo interface cho mọi class không?**

Không. Chỉ tạo khi abstraction thể hiện ranh giới, contract hoặc khả năng thay thế có ý nghĩa. Interface hình thức không tự làm thiết kế tốt hơn.

**7. Nếu adapter đổi từ SDK nhà cung cấp A sang B, phần nào nên thay đổi?**

Implementation adapter và cấu hình bean. Application service cùng contract nên giữ nguyên nếu semantics mà ứng dụng cần không đổi.

## 18. Kết luận

Tiêm bean theo interface là cách kết nối các thành phần Spring Boot để **mã nghiệp vụ phụ thuộc vào khả năng nó cần thay vì phụ thuộc vào class thực hiện khả năng đó**. Interface định nghĩa contract; implementation đảm nhiệm chi tiết; constructor injection thể hiện dependency; Spring IoC container đăng ký, lựa chọn và cung cấp bean phù hợp.

Cách tổ chức này kết hợp Dependency Injection với Dependency Inversion, giúp thay implementation theo môi trường, kiểm thử service độc lập và giữ các chi tiết của nhà cung cấp ở ranh giới infrastructure. Hãy tạo interface khi nó biểu diễn một contract có ý nghĩa, đăng ký implementation rõ ràng và để consumer nhận dependency qua constructor. Khi đó, thay đổi công nghệ gửi email, thanh toán, lưu trữ hoặc gọi API ngoài có thể được xử lý tại adapter/configuration mà không làm xáo trộn chính sách nghiệp vụ.

