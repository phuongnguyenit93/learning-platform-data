# Đăng ký bean theo interface và ảnh hưởng của kiểu trả về phương thức @Bean

Trong một ứng dụng Spring Boot, ta thường muốn service phụ thuộc vào **interface** thay vì gắn chặt với một class triển khai cụ thể. Ví dụ, `OrderService` chỉ cần khả năng gửi thông báo, nên có thể nhận `NotificationSender`. Khi chạy ứng dụng, Spring cung cấp implementation phù hợp như `EmailNotificationSender` hoặc `ConsoleNotificationSender`.

Có hai quyết định liên quan nhưng khác nhau:

- **Đăng ký bean theo interface:** ứng dụng công bố một đối tượng thực hiện hợp đồng nào để những thành phần khác có thể sử dụng hợp đồng đó.
- **Khai báo kiểu trả về của phương thức `@Bean`:** cho Spring biết kiểu mà factory method cam kết trả về. Kiểu này ảnh hưởng đến khả năng dự đoán kiểu bean và việc tìm bean theo kiểu trong quá trình container chuẩn bị tạo các đối tượng khác.

Ví dụ, hai phương thức sau đều có thể trả về cùng một object `EmailNotificationSender`:

~~~java
@Bean
EmailNotificationSender emailNotificationSender() {
    return new EmailNotificationSender();
}
~~~

và:

~~~java
@Bean
NotificationSender notificationSender() {
    return new EmailNotificationSender();
}
~~~

Nhưng metadata kiểu của bean mà Spring có thể suy ra trước khi gọi factory method không giống nhau. Sự khác biệt này quan trọng khi một bean khác yêu cầu dependency theo interface hoặc theo class triển khai cụ thể.

Bài học đi từ hợp đồng interface, cách đăng ký bean, type prediction của Spring, đến các tình huống autowiring, `@Qualifier`, `@Primary` và cách chọn kiểu trả về phù hợp.

## 1. Interface là hợp đồng mà bean có thể cung cấp

Giả sử hệ thống cần gửi thông báo sau khi tạo đơn hàng. Nghiệp vụ chỉ cần một thao tác gửi:

~~~java
package com.example.notification;

public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

`NotificationSender` mô tả **khả năng** mà ứng dụng cần. Nó không nói thông báo được gửi qua email, console, SMS hay một dịch vụ bên ngoài.

Một implementation gửi ra console:

~~~java
package com.example.notification;

public class ConsoleNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        System.out.println("[CONSOLE] To " + recipient + ": " + message);
    }
}
~~~

Một implementation khác có thể gửi email:

~~~java
package com.example.notification;

public class EmailNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        System.out.println("[EMAIL] To " + recipient + ": " + message);
        // Trong ứng dụng thực tế, phần này có thể gọi mail gateway.
    }
}
~~~

Hai class cùng triển khai một interface, nên nơi sử dụng có thể làm việc với kiểu chung:

~~~java
public class OrderService {
    private final NotificationSender notificationSender;

    public OrderService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }

    public void orderCreated(String customerEmail) {
        notificationSender.send(customerEmail, "Your order was created.");
    }
}
~~~

`OrderService` không cần import hay tạo trực tiếp `EmailNotificationSender`. Nó chỉ phụ thuộc hợp đồng `NotificationSender`. Cách thiết kế này giúp thay implementation mà không phải sửa logic nghiệp vụ.

~~~mermaid
classDiagram
    class NotificationSender {
        <<interface>>
        +send(recipient, message)
    }
    class ConsoleNotificationSender {
        +send(recipient, message)
    }
    class EmailNotificationSender {
        +send(recipient, message)
    }
    class OrderService {
        -NotificationSender notificationSender
        +orderCreated(customerEmail)
    }
    NotificationSender <|.. ConsoleNotificationSender
    NotificationSender <|.. EmailNotificationSender
    OrderService --> NotificationSender
~~~

Interface là kiểu mà bean có thể được inject. Tuy nhiên, Spring chỉ có thể cung cấp bean nếu implementation đã được đăng ký và ứng viên phù hợp với các quy tắc resolution.

## 2. Đăng ký bean bằng component scan

Một cách đăng ký implementation là đánh dấu class bằng annotation component:

~~~java
package com.example.notification;

import org.springframework.stereotype.Component;

@Component
public class ConsoleNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        System.out.println("[CONSOLE] To " + recipient + ": " + message);
    }
}
~~~

Spring component scan có thể phát hiện class và đăng ký bean definition cho nó, miễn là package nằm trong phạm vi scan và không có điều kiện loại trừ.

Một số stereotype annotation thường gặp:

| Annotation | Vai trò |
| --- | --- |
| `@Component` | Component chung do Spring quản lý |
| `@Service` | Component mang ý nghĩa tầng service/nghiệp vụ |
| `@Repository` | Component truy cập dữ liệu |
| `@Controller` | Controller trong Spring MVC |
| `@RestController` | Controller trả response body |
| `@Configuration` | Class khai báo cấu hình và factory method `@Bean` |

Nếu `ConsoleNotificationSender` được đăng ký, Spring có thể inject nó vào constructor yêu cầu `NotificationSender`:

~~~java
@Service
public class OrderService {
    private final NotificationSender notificationSender;

    public OrderService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }
}
~~~

Spring tìm bean có kiểu phù hợp với `NotificationSender`. Vì `ConsoleNotificationSender` implements interface đó, bean có thể đáp ứng injection point.

Ở đây, class triển khai có kiểu cụ thể rõ ràng trong component metadata. Tuy nhiên, khi sử dụng factory method `@Bean`, Spring còn phải suy luận kiểu bean từ khai báo của phương thức.

## 3. Đăng ký bean bằng phương thức @Bean

Khi cần tự tạo object, cấu hình một thư viện bên thứ ba hoặc kiểm soát cách khởi tạo, ta có thể dùng `@Bean`.

~~~java
package com.example.notification;

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

Phương thức `notificationSender()` là factory method. Spring gọi phương thức để nhận object và quản lý object được trả về như một bean.

Các điểm cần chú ý:

- `@Configuration` đánh dấu class chứa cấu hình bean.
- `@Bean` đánh dấu method cung cấp một bean cho container.
- Tên method thường trở thành tên bean mặc định: `notificationSender`.
- Kiểu trả về khai báo của method là `NotificationSender`.
- Object thực tế trả về là `ConsoleNotificationSender`.

Đây là đăng ký bean theo abstraction: cấu hình công bố bean qua interface `NotificationSender`. Thành phần sử dụng có thể yêu cầu interface mà không cần biết implementation.

### 3.1. Đăng ký bằng interface không có nghĩa object thực tế là interface

Interface không thể được khởi tạo bằng `new`. Trong ví dụ:

~~~java
@Bean
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

đối tượng thực tế vẫn là một instance của `ConsoleNotificationSender`. Khai báo kiểu trả về `NotificationSender` không biến object thành một instance của interface; nó chỉ khai báo kiểu mà factory method công bố.

Có thể hình dung:

~~~text
Phương thức @Bean
notificationSender()
        │
        │ khai báo kiểu trả về
        ▼
NotificationSender
        │
        │ thực tế return
        ▼
new ConsoleNotificationSender()
        │
        ▼
Object do Spring quản lý
~~~

Khi object đã được tạo, Spring có thể quan sát kiểu thực tế của nó trong những tình huống phù hợp. Nhưng **trước khi gọi factory method**, container cần dự đoán kiểu bean dựa trên metadata, và kiểu trả về khai báo của method là một thông tin quan trọng.

## 4. Kiểu trả về @Bean ảnh hưởng đến type prediction như thế nào?

Spring cần biết kiểu của bean để giải quyết dependency theo kiểu. Trong một ứng dụng, container có thể phải tạo `OrderService` và tìm bean đáp ứng tham số constructor `NotificationSender`. Nó cần đọc metadata để xác định những bean nào có thể là candidate.

Xét hai factory method:

**Phương thức A — khai báo kiểu interface**

~~~java
@Bean
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

**Phương thức B — khai báo kiểu implementation cụ thể**

~~~java
@Bean
public ConsoleNotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Cả hai trả về cùng implementation, nhưng metadata method signature khác nhau:

| Đặc điểm | Phương thức A | Phương thức B |
| --- | --- | --- |
| Kiểu trả về khai báo | `NotificationSender` | `ConsoleNotificationSender` |
| Kiểu contract thể hiện rõ | Interface | Class cụ thể |
| Spring có thể dự đoán kiểu interface từ signature | Có | Có, vì class triển khai interface |
| Spring có thể dự đoán class cụ thể từ signature | Không được bảo đảm chỉ từ kiểu interface | Có |
| Phù hợp với injection theo interface | Có | Có |
| Có thể dùng metadata signature để đáp ứng injection theo class cụ thể trước khi gọi factory method | Không được bảo đảm | Có |

Điểm mấu chốt:

- Khi kiểu trả về là `NotificationSender`, Spring biết bean cung cấp contract `NotificationSender`.
- Khi kiểu trả về là `ConsoleNotificationSender`, Spring biết bean có kiểu cụ thể đó; vì class implements `NotificationSender`, nó cũng có thể đáp ứng dependency theo interface.
- Nếu một bean yêu cầu `ConsoleNotificationSender` nhưng factory method chỉ khai báo trả về `NotificationSender`, container có thể không dự đoán được implementation cụ thể ở giai đoạn cần quyết định candidate.

**Đừng dựa vào việc Spring có thể phát hiện kiểu runtime sau khi factory method đã được gọi để thiết kế dependency theo class cụ thể.** Một bean eager có thể được tạo trong một số đường khởi động trước khi resolution khác diễn ra, nhưng thứ tự khởi tạo không phải hợp đồng ổn định để dựa vào. Type prediction dựa trên metadata cần đủ thông tin ngay từ đầu.

### 4.1. Trường hợp interface injection: kiểu trả về interface là phù hợp

Cấu hình:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    public NotificationSender notificationSender() {
        return new ConsoleNotificationSender();
    }
}
~~~

Service:

~~~java
@Service
public class OrderService {
    private final NotificationSender sender;

    public OrderService(NotificationSender sender) {
        this.sender = sender;
    }
}
~~~

Đây là cặp khai báo nhất quán:

- Factory method công bố `NotificationSender`.
- Service yêu cầu `NotificationSender`.
- Object thực tế là một implementation của interface.
- Spring có đủ kiểu công bố để giải quyết dependency theo contract.

Nếu ứng dụng không có bean nào khác cùng kiểu hoặc qualifier gây nhập nhằng, injection có thể được thực hiện.

### 4.2. Trường hợp injection theo implementation: khai báo interface có thể quá rộng

Giả sử service khác muốn gọi một API đặc thù của `ConsoleNotificationSender`:

~~~java
@Service
public class ConsoleDiagnosticsService {
    private final ConsoleNotificationSender sender;

    public ConsoleDiagnosticsService(ConsoleNotificationSender sender) {
        this.sender = sender;
    }
}
~~~

Trong khi cấu hình vẫn là:

~~~java
@Bean
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Về mặt object thực tế, factory method sẽ trả về một `ConsoleNotificationSender`. Nhưng chữ ký method chỉ công bố `NotificationSender`. Trong giai đoạn Spring phân tích candidate theo metadata, class cụ thể có thể chưa được biết. Vì thế injection theo `ConsoleNotificationSender` có thể thất bại với lỗi không tìm được bean phù hợp.

Nếu thực sự cần inject theo implementation cụ thể, khai báo kiểu trả về cụ thể:

~~~java
@Bean
public ConsoleNotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Lúc này Spring biết cả kiểu class và các interface mà class đó triển khai. Injection theo `ConsoleNotificationSender` và theo `NotificationSender` đều có thể được hỗ trợ.

Tuy vậy, nếu service chỉ cần gửi thông báo, **nên inject interface**. Chỉ inject implementation khi có lý do rõ ràng để phụ thuộc vào API riêng của class đó.

### 4.3. Một lưu ý về kiểu thực tế và thời điểm tạo bean

Spring có những cơ chế dự đoán kiểu và introspection bean factory method. Khi bean đã được tạo, container có thể biết thêm kiểu runtime của object. Một số trường hợp có thể được resolve nhờ việc bean khác đã khởi tạo trước đó.

Nhưng thứ tự khởi tạo phụ thuộc đồ thị dependency và cơ chế nội bộ; không nên dựa vào việc một bean tình cờ được tạo sớm để sửa một method signature khai báo quá rộng.

Quy tắc thiết kế ổn định là:

> Khai báo kiểu trả về @Bean đủ cụ thể để thể hiện những kiểu mà container cần nhận diện trước khi tạo bean; ở nơi sử dụng, ưu tiên phụ thuộc vào interface phù hợp với trách nhiệm.

Nếu factory method trả về interface vì muốn che giấu implementation, hãy giữ các injection point cũng dùng interface. Nếu một integration thật sự cần class cụ thể, hãy cung cấp một định nghĩa bean có kiểu khai báo đủ cụ thể hoặc thiết kế abstraction phù hợp hơn.

## 5. Ví dụ đầy đủ: service inject theo interface

Ta xây một ứng dụng Spring Boot nhỏ:

~~~text
notification-demo/
└── src/main/java/com/example/demo/
    ├── DemoApplication.java
    ├── NotificationSender.java
    ├── ConsoleNotificationSender.java
    ├── NotificationConfiguration.java
    ├── OrderService.java
    └── OrderController.java
~~~

### 5.1. Interface `NotificationSender.java`

~~~java
package com.example.demo;

public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

### 5.2. Implementation `ConsoleNotificationSender.java`

~~~java
package com.example.demo;

public class ConsoleNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        System.out.println("[CONSOLE] " + recipient + ": " + message);
    }
}
~~~

Class không gắn `@Component` vì bean sẽ được tạo từ `@Bean` method.

### 5.3. Cấu hình `NotificationConfiguration.java`

~~~java
package com.example.demo;

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

Kiểu trả về là interface vì toàn bộ ứng dụng chỉ cần contract gửi thông báo.

### 5.4. Service `OrderService.java`

~~~java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final NotificationSender notificationSender;

    public OrderService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }

    public String createOrder(String customerEmail) {
        notificationSender.send(customerEmail, "Your order has been created.");
        return "Order created for " + customerEmail;
    }
}
~~~

Service phụ thuộc interface. Nó không cần biết object thực tế là console sender hay email sender.

### 5.5. Controller `OrderController.java`

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public String create(@RequestParam String email) {
        return orderService.createOrder(email);
    }
}
~~~

Controller phụ thuộc `OrderService`. Nó không tự tạo service hoặc sender bằng `new`.

### 5.6. Lớp khởi động `DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Đặt cấu hình và component trong package `com.example.demo` hoặc package con để component scan mặc định có thể phát hiện chúng.

### 5.7. Đường đi dependency

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] --> B["NotificationConfiguration"]
    B --> C["BeanDefinition: notificationSender"]
    C --> D["ConsoleNotificationSender instance"]
    D -.-> E["NotificationSender interface"]
    E --> F["Inject vào OrderService"]
    F --> G["OrderService bean"]
    G --> H["Inject vào OrderController"]
    H --> I["HTTP request /orders"]
    I --> G
    G --> D
~~~

Sơ đồ thể hiện bean factory method cung cấp implementation, container quản lý object và inject nó theo interface. Khi request đến, controller gọi service; service gọi sender thông qua hợp đồng.

### 5.8. Chạy và quan sát

Với Maven project đã khai báo `spring-boot-starter-web` và Spring Boot Maven plugin:

~~~bash
mvn spring-boot:run
~~~

Gửi request:

~~~bash
curl -X POST "http://localhost:8080/orders?email=lan@example.com"
~~~

Response mong đợi:

~~~text
Order created for lan@example.com
~~~

Trong console server:

~~~text
[CONSOLE] lan@example.com: Your order has been created.
~~~

Kết quả chứng minh đường xử lý request đã sử dụng service và sender được kết nối trong context. Đây là ví dụ minh họa dependency wiring; phần tạo order ở đây chưa lưu dữ liệu vào database.

## 6. Thay implementation mà không sửa service

Một lợi ích lớn của đăng ký bean theo interface là có thể thay implementation ở cấu hình.

Giả sử muốn dùng email sender. Thêm class:

~~~java
package com.example.demo;

public class EmailNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        System.out.println("[EMAIL] " + recipient + ": " + message);
    }
}
~~~

Đổi factory method:

~~~java
@Bean
public NotificationSender notificationSender() {
    return new EmailNotificationSender();
}
~~~

`OrderService` không cần sửa:

~~~java
public OrderService(NotificationSender notificationSender) {
    this.notificationSender = notificationSender;
}
~~~

Lý do là service chỉ biết contract. Container vẫn cung cấp một bean phù hợp với `NotificationSender`, chỉ khác object được tạo.

~~~text
Lần 1:
NotificationConfiguration
        │
        ▼
ConsoleNotificationSender
        │ implements
        ▼
NotificationSender
        │ inject
        ▼
OrderService

Lần 2:
NotificationConfiguration
        │
        ▼
EmailNotificationSender
        │ implements
        ▼
NotificationSender
        │ inject
        ▼
OrderService
~~~

Đây là cách áp dụng **program to an interface** và Dependency Injection: phần nghiệp vụ không cần thay đổi khi cách thực hiện một khả năng được thay thế.

## 7. Khi có nhiều bean cùng triển khai interface

Một khi đăng ký nhiều implementation, Spring có thể tìm thấy nhiều candidate cho một injection point.

Ví dụ:

~~~java
@Bean
public NotificationSender consoleSender() {
    return new ConsoleNotificationSender();
}

@Bean
public NotificationSender emailSender() {
    return new EmailNotificationSender();
}
~~~

Cả hai bean đều có kiểu công bố `NotificationSender`. Service:

~~~java
@Service
public class OrderService {
    public OrderService(NotificationSender sender) {
        // ...
    }
}
~~~

có thể gặp lỗi vì container không biết phải chọn bean nào.

Một thông báo thường gặp có nội dung tương tự:

~~~text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'NotificationSender' available:
expected single matching bean but found 2
~~~

Đây là vấn đề **candidate selection**, không phải lỗi do interface hay do kiểu trả về của `@Bean`.

### 7.1. Chọn bằng `@Qualifier`

Có thể chỉ định bean cụ thể:

~~~java
@Bean
@Qualifier("primaryNotification")
public NotificationSender consoleSender() {
    return new ConsoleNotificationSender();
}

@Bean
@Qualifier("emailNotification")
public NotificationSender emailSender() {
    return new EmailNotificationSender();
}
~~~

Injection:

~~~java
@Service
public class OrderService {
    private final NotificationSender sender;

    public OrderService(
            @Qualifier("emailNotification") NotificationSender sender) {
        this.sender = sender;
    }
}
~~~

`@Qualifier` giúp lọc candidate theo qualifier. Tên bean cũng thường được dùng như qualifier mặc định trong các tình huống phù hợp, nhưng một qualifier tường minh diễn đạt ý định tốt hơn khi cấu hình phức tạp.

### 7.2. Chọn bằng `@Primary`

Nếu một implementation là lựa chọn mặc định khi có nhiều candidate:

~~~java
@Bean
@Primary
public NotificationSender consoleSender() {
    return new ConsoleNotificationSender();
}

@Bean
public NotificationSender emailSender() {
    return new EmailNotificationSender();
}
~~~

Khi injection yêu cầu một `NotificationSender` mà không có qualifier cụ thể, `@Primary` giúp Spring ưu tiên bean console.

`@Primary` không loại bỏ bean còn lại và cũng không có nghĩa mọi injection point phải sử dụng bean primary. Một qualifier rõ ràng vẫn có thể chọn candidate khác.

### 7.3. Inject tất cả implementation qua collection

Nếu nghiệp vụ cần gọi nhiều sender:

~~~java
@Service
public class BroadcastService {
    private final List<NotificationSender> senders;

    public BroadcastService(List<NotificationSender> senders) {
        this.senders = senders;
    }

    public void broadcast(String recipient, String message) {
        for (NotificationSender sender : senders) {
            sender.send(recipient, message);
        }
    }
}
~~~

Spring có thể inject collection chứa các bean phù hợp. Khi đó yêu cầu không còn là “chọn một bean”, mà là “tập hợp tất cả candidate”. Thứ tự collection có thể chịu ảnh hưởng của thứ tự bean/order metadata; nếu thứ tự có ý nghĩa nghiệp vụ, cần khai báo và kiểm soát nó rõ ràng.

## 8. Tên bean và kiểu trả về là hai thông tin khác nhau

Trong:

~~~java
@Bean
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Spring thường đăng ký bean với tên `notificationSender` và kiểu khai báo `NotificationSender`.

Bạn có thể đổi tên:

~~~java
@Bean("consoleSender")
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Hoặc:

~~~java
@Bean(name = {"consoleSender", "defaultSender"})
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Tên bean hỗ trợ truy cập theo tên và có thể tham gia lựa chọn candidate trong các tình huống phù hợp. **Tên bean không thay đổi kiểu trả về khai báo**: ở các ví dụ này, kiểu công bố vẫn là `NotificationSender`.

Tương tự, đổi tên method không biến interface thành class cụ thể. Khi thiết kế, cần tách bạch:

- **Bean name:** định danh bean trong container.
- **Declared return type:** kiểu method công bố cho container.
- **Runtime type:** class thực tế của object được trả về.
- **Qualifier/Primary:** metadata hỗ trợ chọn bean trong số các candidate.

Bốn yếu tố này có liên quan nhưng giải quyết những câu hỏi khác nhau.

## 9. Kiểu trả về @Bean và khả năng dự đoán kiểu trước khi khởi tạo

Spring phải giải quyết dependency ngay cả khi chưa tạo mọi bean. Nếu factory method khai báo kiểu trả về quá tổng quát, container có thể thiếu thông tin về implementation.

Xét ví dụ:

~~~java
@Bean
public Object notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Kiểu trả về `Object` không thể hiện contract `NotificationSender` trong method signature. Mặc dù object thực tế implements `NotificationSender`, Spring có ít thông tin hơn khi dự đoán kiểu bean trước khi gọi factory method.

Nếu service cần:

~~~java
OrderService(NotificationSender sender)
~~~

thì không nên khai báo factory method trả về `Object`. Nên dùng:

~~~java
@Bean
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Hoặc nếu ứng dụng có lý do cần biết class cụ thể:

~~~java
@Bean
public ConsoleNotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

### 9.1. Tại sao không nên trả về Object hoặc một kiểu quá chung?

Kiểu trả về tổng quát có thể làm giảm khả năng:

- Phân tích candidate theo interface.
- Phân tích candidate theo class cụ thể.
- Xác định metadata về kiểu generic.
- Tự động cấu hình hoặc autowire các dependency liên quan trước khi instance được tạo.

Một số tình huống Spring có thể suy luận thêm kiểu từ factory method hoặc instance sau khi khởi tạo. Nhưng không nên dùng điều đó làm cơ sở để khai báo kiểu quá rộng.

**Hãy khai báo kiểu trả về chính xác và có ý nghĩa nhất mà các nơi sử dụng cần nhận diện.** Nếu chỉ cần abstraction, dùng interface; nếu có nhu cầu hợp lệ về kiểu cụ thể, công bố kiểu cụ thể.

### 9.2. Kiểu trả về interface có làm mất implementation không?

Không. Object runtime vẫn có class thực tế. Bạn có thể quan sát:

~~~java
Object bean = applicationContext.getBean("notificationSender");
System.out.println(bean.getClass().getName());
~~~

Trong ví dụ, kết quả runtime có thể là:

~~~text
com.example.demo.ConsoleNotificationSender
~~~

Nhưng khả năng quan sát kiểu runtime **sau khi object tồn tại** khác với khả năng dự đoán kiểu bean **trước khi gọi factory method**. Đừng suy luận rằng vì `getClass()` thấy implementation nên mọi injection theo implementation luôn được giải quyết ổn định từ đầu.

## 10. Factory method trả về một interface generic

Trong một số ứng dụng, interface chứa tham số generic:

~~~java
public interface Store<T> {
    void save(T value);
}
~~~

Implementation:

~~~java
public class StringStore implements Store<String> {
    @Override
    public void save(String value) {
        System.out.println("Save: " + value);
    }
}
~~~

Factory method:

~~~java
@Bean
public Store<String> stringStore() {
    return new StringStore();
}
~~~

Kiểu trả về `Store<String>` cung cấp thông tin generic hữu ích cho Spring khi lựa chọn bean theo generic type ở những injection point thích hợp.

Ví dụ:

~~~java
@Service
public class MessageArchive {
    private final Store<String> store;

    public MessageArchive(Store<String> store) {
        this.store = store;
    }
}
~~~

Nếu factory method chỉ khai báo `Store<?>` hoặc `Store` raw type, thông tin generic có thể kém chính xác hơn. Khi ứng dụng có nhiều bean cùng interface nhưng khác tham số generic, kiểu generic có thể tham gia phân giải candidate.

Ví dụ:

~~~java
@Bean
Store<String> stringStore() {
    return new StringStore();
}

@Bean
Store<Integer> integerStore() {
    return new IntegerStore();
}
~~~

`IntegerStore` là implementation giả định của `Store<Integer>`. Spring có thể sử dụng generic type metadata trong các tình huống autowiring tương ứng để phân biệt `Store<String>` và `Store<Integer>`.

Không nên bỏ qua generic signature khi nó mang ý nghĩa trong contract của bean. Kiểu trả về cụ thể giúp cả compiler lẫn container hiểu rõ hơn loại dữ liệu mà factory cung cấp.

## 11. @Bean method trong @Configuration và cách gọi giữa các factory method

Một class `@Configuration` có thể có nhiều factory method:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    public MessageFormatter messageFormatter() {
        return new VietnameseMessageFormatter();
    }

    @Bean
    public NotificationSender notificationSender() {
        return new ConsoleNotificationSender();
    }
}
~~~

Nếu một bean cần bean khác, cách rõ ràng là khai báo dependency trong tham số method:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    public MessageFormatter messageFormatter() {
        return new VietnameseMessageFormatter();
    }

    @Bean
    public NotificationSender notificationSender(MessageFormatter formatter) {
        return new FormattedNotificationSender(formatter);
    }
}
~~~

`FormattedNotificationSender` là class giả định implements `NotificationSender` và nhận `MessageFormatter` qua constructor.

Spring giải quyết tham số `formatter` như dependency của bean được tạo. Cách này diễn tả quan hệ rõ ràng và không cần tự gọi method cấu hình để lấy bean.

### 11.1. Full @Configuration và lite mode

Với `@Configuration` đầy đủ, Spring thường enhancement class cấu hình bằng CGLIB để điều phối lời gọi giữa các `@Bean` method. Điều này giúp khi một `@Bean` method gọi method `@Bean` khác trong cùng class, Spring có thể trả về bean được quản lý thay vì luôn tạo object mới như một lời gọi Java thông thường.

Ví dụ:

~~~java
@Configuration
public class FullConfiguration {

    @Bean
    public MessageFormatter formatter() {
        return new VietnameseMessageFormatter();
    }

    @Bean
    public NotificationSender sender() {
        return new FormattedNotificationSender(formatter());
    }
}
~~~

Trong full configuration mode, lời gọi `formatter()` trong một factory method được xử lý qua cơ chế enhancement của Spring để tham chiếu bean container-managed.

Nếu method `@Bean` nằm trong một class không được xử lý như full `@Configuration` (lite mode), lời gọi Java trực tiếp giữa các method không nhất thiết được intercept. Nó có thể tạo object mới và không tuân theo ý định chia sẻ bean singleton.

Để code rõ ràng và ít phụ thuộc chế độ enhancement, hãy dùng tham số factory method:

~~~java
@Bean
public NotificationSender sender(MessageFormatter formatter) {
    return new FormattedNotificationSender(formatter);
}
~~~

Cách này biểu diễn dependency tường minh và phù hợp với cả việc đọc hiểu lẫn quản lý bean.

## 12. @Bean method có thể trả về kiểu cụ thể nhưng inject qua interface

Đây thường là cách linh hoạt khi muốn công bố đủ metadata cho container mà vẫn giữ abstraction ở nơi sử dụng.

Ví dụ:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    public ConsoleNotificationSender consoleNotificationSender() {
        return new ConsoleNotificationSender();
    }
}
~~~

Ở service:

~~~java
@Service
public class OrderService {
    private final NotificationSender sender;

    public OrderService(NotificationSender sender) {
        this.sender = sender;
    }
}
~~~

Vì `ConsoleNotificationSender` implements `NotificationSender`, container có thể nhận diện bean theo interface. Service vẫn không phụ thuộc implementation.

Điều này dẫn đến một quy tắc hữu ích:

- **Factory method:** có thể trả về implementation cụ thể để cung cấp metadata kiểu đầy đủ.
- **Consumer/service:** nên nhận interface để giữ coupling thấp.

Tuy nhiên, không cần luôn khai báo implementation cụ thể nếu abstraction đã đủ và không có nhu cầu injection theo class. Kiểu trả về interface trong trường hợp đó là một lựa chọn hợp lệ, có chủ đích.

## 13. Đăng ký nhiều implementation theo profile hoặc điều kiện

Một ứng dụng có thể cần implementation khác nhau ở local, test và production.

Ví dụ dùng profile:

~~~java
@Configuration
public class NotificationConfiguration {

    @Bean
    @Profile("dev")
    public NotificationSender consoleSender() {
        return new ConsoleNotificationSender();
    }

    @Bean
    @Profile("prod")
    public NotificationSender emailSender() {
        return new EmailNotificationSender();
    }
}
~~~

Khi profile `dev` được kích hoạt, bean console được đăng ký; khi `prod` được kích hoạt, bean email được đăng ký. Đây là ví dụ khái niệm; class cấu hình cần import `org.springframework.context.annotation.Profile`.

Có thể kích hoạt profile bằng:

~~~properties
spring.profiles.active=dev
~~~

Hoặc tham số chạy:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Mục tiêu là mỗi môi trường có candidate phù hợp, tránh để hai implementation cùng hoạt động rồi làm injection nhập nhằng.

Ngoài `@Profile`, Spring Boot còn có các điều kiện như `@ConditionalOnProperty` và `@ConditionalOnMissingBean` trong hệ sinh thái auto-configuration. Chúng thường hữu ích khi viết starter hoặc cấu hình mặc định có thể được người dùng thay thế.

Không nên dùng profile như cơ chế bảo mật; nó là lựa chọn cấu hình bean theo môi trường, không tự bảo vệ endpoint hay secret.

## 14. Kiểm tra bean được đăng ký theo kiểu nào

Khi gặp lỗi injection, có thể quan sát context và bean definition thay vì đoán.

### 14.1. Truy vấn bean theo interface

~~~java
@Bean
CommandLineRunner inspectSender(ApplicationContext context) {
    return args -> {
        NotificationSender sender =
                context.getBean(NotificationSender.class);

        System.out.println("Sender runtime type: " + sender.getClass().getName());
    };
}
~~~

Nếu có đúng một candidate phù hợp, lời gọi theo kiểu có thể trả bean đó. Nếu có nhiều candidate không được phân giải, truy vấn kiểu có thể báo lỗi.

Đoạn này cần import `ApplicationContext` và `CommandLineRunner`. Nó là công cụ quan sát cho bài học, không nhất thiết cần giữ trong ứng dụng production.

### 14.2. Truy vấn tên bean và kiểu runtime

~~~java
@Bean
CommandLineRunner inspectBean(ApplicationContext context) {
    return args -> {
        Object bean = context.getBean("notificationSender");
        System.out.println(bean.getClass().getName());
    };
}
~~~

Tên `notificationSender` phải khớp với tên bean thực tế đã đăng ký. Nếu dùng tên khác trong `@Bean("...")`, phải truy vấn theo tên đó.

Kết quả `getClass()` cho biết class runtime. Để biết kiểu Spring có thể dự đoán từ định nghĩa trước khi tạo object, cần xem metadata của bean definition hoặc debug quá trình resolution; không thể chỉ dùng kết quả runtime để suy ngược toàn bộ quá trình.

### 14.3. Xem danh sách bean definition

~~~java
@Bean
CommandLineRunner listDefinitions(ConfigurableApplicationContext context) {
    return args -> {
        for (String name : context.getBeanFactory().getBeanDefinitionNames()) {
            if (name.toLowerCase().contains("notification")) {
                System.out.println("Definition: " + name);
            }
        }
    };
}
~~~

Ví dụ cần import `ConfigurableApplicationContext` và `CommandLineRunner`. Danh sách này giúp xác nhận các tên definition đã được đăng ký.

Lưu ý: danh sách definition không chứng minh tất cả bean instance đã được khởi tạo. Bean lazy có thể có định nghĩa nhưng chưa có object.

## 15. Các lỗi thường gặp và cách hiểu đúng

### 15.1. Không có bean theo interface

Thông báo có thể là:

~~~text
No qualifying bean of type 'NotificationSender' available
~~~

Hãy kiểm tra:

- Implementation đã được đăng ký bằng `@Component` hay `@Bean` chưa?
- Package có nằm trong component scan không?
- Bean có bị profile hoặc condition loại khỏi context không?
- Factory method có kiểu trả về quá chung, chẳng hạn `Object`, khiến type prediction không đủ không?
- Bean có bị cấu hình khác loại trừ không?

Đừng chỉ thêm `@Autowired` vào field để mong Spring tự tạo implementation. Container cần có một bean definition hợp lệ.

### 15.2. Có nhiều bean theo interface

Thông báo thường liên quan `NoUniqueBeanDefinitionException`.

Hãy xem có bao nhiêu bean cùng kiểu, rồi quyết định:

- Chỉ đăng ký implementation cần dùng.
- Dùng `@Primary` nếu có một lựa chọn mặc định.
- Dùng `@Qualifier` nếu consumer cần một implementation cụ thể.
- Inject collection nếu nghiệp vụ cần tất cả.

Không nên đổi kiểu trả về thành class cụ thể chỉ để vô tình làm biến mất candidate khác mà chưa xác định đúng yêu cầu.

### 15.3. Injection theo implementation thất bại nhưng theo interface thành công

Một factory method khai báo:

~~~java
@Bean
NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

có thể hỗ trợ injection theo `NotificationSender` nhưng không đủ thông tin metadata để bảo đảm injection theo `ConsoleNotificationSender` trước khi object được tạo.

Nếu consumer thực sự cần implementation, cân nhắc khai báo kiểu trả về cụ thể:

~~~java
@Bean
ConsoleNotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Sau đó kiểm tra lại context. Nếu service chỉ cần thao tác gửi, đổi consumer về interface thường là thiết kế phù hợp hơn.

### 15.4. Trả về Object hoặc raw type

Ví dụ:

~~~java
@Bean
Object messageStore() {
    return new StringStore();
}
~~~

Kiểu `Object` không thể hiện contract cụ thể mà các bean khác cần. Nếu service yêu cầu `Store<String>`, khai báo trả về `Object` có thể khiến container không dự đoán được kiểu phù hợp trước khi factory method chạy.

Nên công bố kiểu có ý nghĩa:

~~~java
@Bean
Store<String> messageStore() {
    return new StringStore();
}
~~~

Hoặc kiểu implementation cụ thể khi có nhu cầu nhận diện kiểu đó.

### 15.5. Hai bean cùng tên

Bean name là định danh trong container. Nếu hai cấu hình đăng ký bean trùng tên, hành vi phụ thuộc chính sách bean definition overriding và cấu hình context. Trong các phiên bản Spring Boot hiện đại, bean definition overriding thường không được bật mặc định cho ứng dụng mới; xung đột có thể khiến startup thất bại.

Đừng dựa vào việc một bean “ghi đè” bean kia theo thứ tự file. Hãy dùng tên có chủ đích, qualifier, profile hoặc condition để xác định bean nào được đăng ký.

### 15.6. Dùng class cụ thể ở consumer làm mất lợi ích abstraction

Nếu `OrderService` nhận `ConsoleNotificationSender` trực tiếp, service sẽ bị gắn với cách gửi console. Khi đổi sang email, bạn phải sửa consumer hoặc tìm cách chuyển đổi kiểu.

Hãy nhận `NotificationSender` nếu service chỉ cần khả năng gửi. Kiểu trả về cụ thể của factory method và kiểu tham số của consumer không bắt buộc phải giống nhau.

## 16. Chọn kiểu trả về @Bean như thế nào?

Có thể dùng các nguyên tắc sau:

| Hoàn cảnh | Kiểu trả về nên cân nhắc | Lý do |
| --- | --- | --- |
| Mọi consumer chỉ cần một contract ổn định | Interface | Thể hiện abstraction, giảm coupling |
| Có consumer cần kiểu implementation cụ thể | Implementation class hoặc một bean definition riêng có kiểu đó | Giúp type prediction nhận diện class |
| Bean có generic contract quan trọng | Kiểu generic cụ thể như `Store<String>` | Cung cấp metadata generic cho resolution |
| Trả về `Object` hoặc kiểu rất chung | Tránh nếu có thể | Làm mất thông tin kiểu hữu ích |
| Factory method tạo thư viện bên thứ ba | Kiểu public API cụ thể mà consumer cần | Không cần ép class bên thứ ba thành component |
| Một factory method có nhiều implementation tùy profile | Interface nếu consumer chỉ cần contract | Giữ consumer độc lập với lựa chọn môi trường |

Không có quy tắc “mọi `@Bean` đều phải trả về interface” hoặc “mọi `@Bean` đều phải trả về class cụ thể”. Cần chọn kiểu thể hiện đúng contract và cung cấp đủ metadata cho container.

Một cách viết tốt thường như sau:

~~~java
@Bean
public NotificationSender notificationSender() {
    return new ConsoleNotificationSender();
}
~~~

khi ứng dụng muốn công bố abstraction và mọi consumer chỉ cần abstraction.

Nếu có nhu cầu hợp lệ để Spring nhận diện class cụ thể:

~~~java
@Bean
public ConsoleNotificationSender consoleNotificationSender() {
    return new ConsoleNotificationSender();
}
~~~

Consumer vẫn có thể inject theo interface:

~~~java
public OrderService(NotificationSender sender) {
    this.sender = sender;
}
~~~

Đó là sự cân bằng giữa **metadata đủ cụ thể ở nơi tạo bean** và **coupling thấp ở nơi sử dụng**.

## 17. Bài thực hành

### Bài A: Dự đoán kiểu bean

Cho:

~~~java
@Bean
public NotificationSender sender() {
    return new ConsoleNotificationSender();
}
~~~

Trả lời:

1. Tên bean mặc định là gì?
2. Kiểu trả về khai báo là gì?
3. Kiểu runtime của object là gì?
4. Consumer yêu cầu `NotificationSender` có phù hợp không?
5. Consumer yêu cầu `ConsoleNotificationSender` có thể gặp hạn chế nào?

**Gợi ý:** Tên bean thường là `sender`; declared return type là `NotificationSender`; object thực tế là `ConsoleNotificationSender`. Interface injection phù hợp. Không nên dựa vào type prediction để inject implementation cụ thể khi method chỉ công bố interface.

### Bài B: So sánh hai factory method

Viết hai cấu hình độc lập:

~~~java
@Bean
NotificationSender sender() {
    return new ConsoleNotificationSender();
}
~~~

và:

~~~java
@Bean
ConsoleNotificationSender sender() {
    return new ConsoleNotificationSender();
}
~~~

Thử tạo consumer yêu cầu interface và consumer yêu cầu implementation. Quan sát khác biệt trong quá trình khởi động context.

**Gợi ý:** Khi kiểu trả về là implementation, metadata cho phép Spring nhận diện cả class cụ thể và interface mà class triển khai. Khi kiểu trả về là interface, không nên dựa vào object runtime chưa được tạo để suy ra implementation.

### Bài C: Xử lý nhiều implementation

Đăng ký hai bean:

~~~java
@Bean
NotificationSender consoleSender() {
    return new ConsoleNotificationSender();
}

@Bean
NotificationSender emailSender() {
    return new EmailNotificationSender();
}
~~~

Hãy sửa `OrderService` để luôn dùng email sender bằng `@Qualifier`. Sau đó thử đánh dấu console sender là `@Primary` và bỏ qualifier. Quan sát candidate nào được chọn.

### Bài D: Đăng ký implementation bằng profile

Tạo hai bean `NotificationSender`, một cho `dev` và một cho `prod`. Chạy ứng dụng với từng profile và kiểm tra log để xác nhận implementation thực tế.

Hãy giải thích vì sao profile giúp tránh lỗi nhiều candidate khi mỗi môi trường chỉ đăng ký một implementation.

### Bài E: Generic interface

Tạo `Store<String>` và `Store<Integer>`. Inject từng kiểu vào hai service khác nhau. Sau đó đổi kiểu trả về factory method thành raw `Store` và quan sát việc phân giải generic type.

Mục tiêu là hiểu generic signature cũng là thông tin metadata mà Spring có thể sử dụng trong autowiring.

## 18. Câu hỏi tự kiểm tra

**1. Đăng ký bean theo interface nghĩa là gì?**

Là cung cấp một object thực hiện hợp đồng interface để các thành phần khác có thể inject và sử dụng theo kiểu abstraction. Object runtime vẫn là một class triển khai cụ thể.

**2. Vì sao kiểu trả về của phương thức `@Bean` quan trọng?**

Vì Spring sử dụng method signature và metadata để dự đoán kiểu bean, xác định candidate theo type và giải quyết dependency. Kiểu trả về quá chung có thể khiến container thiếu thông tin trước khi factory method được gọi.

**3. Nếu `@Bean` trả về `NotificationSender` nhưng object thực tế là `ConsoleNotificationSender`, service yêu cầu interface có hoạt động không?**

Có, khi bean được đăng ký và không có candidate nhập nhằng. Kiểu công bố đáp ứng đúng contract mà service yêu cầu.

**4. Nếu service yêu cầu `ConsoleNotificationSender` thì sao?**

Kiểu trả về interface không bảo đảm container dự đoán được implementation cụ thể ở giai đoạn cần resolve. Nếu cần class đó, hãy khai báo return type cụ thể hoặc thiết kế consumer phụ thuộc interface.

**5. `@Qualifier` và `@Primary` giải quyết vấn đề gì?**

Chúng giúp lựa chọn giữa nhiều bean candidate cùng đáp ứng một kiểu injection. `@Qualifier` chọn candidate theo qualifier; `@Primary` chỉ định lựa chọn ưu tiên mặc định.

**6. Bean name có thay thế declared return type không?**

Không. Tên định danh bean khác với kiểu khai báo và kiểu runtime. Đổi tên bean không làm Spring có thêm thông tin về class mà factory method công bố.

**7. Có phải factory method luôn cần trả về implementation cụ thể?**

Không. Nếu consumer chỉ cần interface và method trả về interface đó, khai báo interface là hợp lệ và thể hiện rõ abstraction. Chỉ công bố implementation khi có nhu cầu nhận diện kiểu cụ thể.

## 19. Kết luận

Đăng ký bean theo interface giúp ứng dụng phụ thuộc vào **hợp đồng** thay vì cách triển khai. Spring có thể cung cấp implementation phù hợp qua component scan hoặc factory method `@Bean`, sau đó inject bean vào constructor của những thành phần cần sử dụng.

Kiểu trả về của `@Bean` là metadata quan trọng cho container. **Trả về interface** phù hợp khi ứng dụng muốn công bố abstraction và consumer cũng yêu cầu abstraction. **Trả về class cụ thể** cung cấp thêm thông tin cho Spring khi cần nhận diện implementation theo kiểu cụ thể. Không nên trả về `Object` hoặc raw type nếu điều đó làm mất thông tin kiểu cần cho dependency resolution.

Khi thiết kế, hãy giữ rõ ba lớp thông tin: **tên bean để định danh, kiểu trả về để công bố khả năng/kiểu có thể dự đoán, và kiểu runtime của object thực tế**. Kết hợp với `@Qualifier`, `@Primary` và constructor injection, bạn có thể đăng ký nhiều implementation mà vẫn giữ các service độc lập với chi tiết triển khai.

