# Nhiều phương thức listener trong một bean Spring

## Mục tiêu

Sau bài này, bạn có thể:

- Đăng ký nhiều phương thức @EventListener trong cùng một bean.
- Cho một bean xử lý nhiều kiểu event và nhiều phương thức cùng nhận một kiểu event.
- Kiểm soát thứ tự bằng @Order và lọc event bằng condition.
- Dùng giá trị trả về của listener để phát một event tiếp theo.
- Hiểu cách các phương thức listener tương tác với xử lý bất đồng bộ.
- Tổ chức listener trong bean có trách nhiệm rõ ràng và kiểm thử được.

## 1. Một bean có thể có nhiều listener method

Trong Spring, @EventListener được đặt trên phương thức. Spring phát hiện các phương thức được đánh dấu trong những bean do ApplicationContext quản lý và đăng ký từng phương thức như một event listener riêng.

Vì vậy, một bean có thể chứa nhiều phương thức listener:

- Mỗi phương thức có thể nhận một kiểu event khác nhau.
- Nhiều phương thức có thể cùng nhận một kiểu event.
- Mỗi phương thức có thể có điều kiện và thứ tự xử lý riêng.
- Một phương thức có thể trả về event mới để Spring phát tiếp.

Ví dụ, OrderEventListeners có thể chứa auditCreation(OrderCreatedEvent), notifyCreation(OrderCreatedEvent) và handlePayment(PaymentCompletedEvent). Khi OrderCreatedEvent được phát, hai phương thức đầu đều có thể chạy. Khi PaymentCompletedEvent được phát, phương thức handlePayment được gọi.

Các phương thức này không cần gọi trực tiếp lẫn nhau. Publisher chỉ phát event, còn Spring chọn những listener có kiểu event phù hợp.

## 2. Spring tìm listener method như thế nào?

Khi ApplicationContext khởi động, Spring tìm các bean có phương thức được đánh dấu @EventListener và đăng ký các phương thức đó. Khi một event được phát, Spring chọn những listener có kiểu tham số phù hợp với kiểu event.

Ví dụ:

~~~java
@Component
public class OrderEventListeners {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Order created: " + event.orderId());
    }

    @EventListener
    public void onPaymentCompleted(PaymentCompletedEvent event) {
        System.out.println("Payment completed: " + event.orderId());
    }
}
~~~

Trong ví dụ trên:

- onOrderCreated chỉ xử lý OrderCreatedEvent.
- onPaymentCompleted chỉ xử lý PaymentCompletedEvent.
- Hai phương thức nằm trong cùng một bean nhưng được đăng ký như hai listener riêng.
- Publisher không cần biết tên bean hoặc tên phương thức.

Một phương thức listener thông thường khai báo một tham số event. Spring suy ra kiểu event từ kiểu tham số đó. Event có kiểu con cũng có thể phù hợp với listener nhận kiểu cha tương ứng.

Bean chứa listener phải được Spring quản lý, ví dụ có @Component hoặc được khai báo bằng @Bean. Nếu tự tạo đối tượng bằng từ khóa new, Spring không tự phát hiện các phương thức @EventListener trên đối tượng đó.

## 3. Nhiều phương thức cùng nhận một kiểu event

Đây là trường hợp hữu ích khi một sự kiện cần kích hoạt nhiều hành động độc lập trong cùng một nhóm trách nhiệm.

~~~java
@Component
public class OrderEventListeners {

    @EventListener
    public void auditCreation(OrderCreatedEvent event) {
        System.out.println("Audit order " + event.orderId());
    }

    @EventListener
    public void notifyCustomer(OrderCreatedEvent event) {
        System.out.println("Notify customer for " + event.orderId());
    }

    @EventListener
    public void updateMetrics(OrderCreatedEvent event) {
        System.out.println("Update metrics for " + event.orderId());
    }
}
~~~

Khi publisher phát một OrderCreatedEvent, cả ba phương thức đều là listener phù hợp và được Spring gọi. Không cần tạo ba event khác nhau chỉ vì có ba hành động.

Không nên dựa vào thứ tự khai báo phương thức trong file Java để quyết định thứ tự xử lý. Nếu thứ tự có ý nghĩa nghiệp vụ, hãy khai báo @Order.

## 4. Kiểm soát thứ tự bằng @Order

Có thể đặt @Order trên từng listener method. Giá trị nhỏ hơn có độ ưu tiên cao hơn và được gọi trước trong nhóm listener xử lý event đó.

~~~java
@Component
public class OrderEventListeners {

    @EventListener
    @Order(1)
    public void auditCreation(OrderCreatedEvent event) {
        System.out.println("1. Audit " + event.orderId());
    }

    @EventListener
    @Order(2)
    public void notifyCustomer(OrderCreatedEvent event) {
        System.out.println("2. Notify " + event.orderId());
    }

    @EventListener
    @Order(3)
    public void updateMetrics(OrderCreatedEvent event) {
        System.out.println("3. Metrics " + event.orderId());
    }
}
~~~

Khi nhận một OrderCreatedEvent, thứ tự dự kiến là:

~~~text
1. Audit ORD-1001
2. Notify ORD-1001
3. Metrics ORD-1001
~~~

Nếu không khai báo @Order, listener dùng mức ưu tiên mặc định thấp nhất. Nếu nhiều listener có cùng mức ưu tiên, không nên dựa vào thứ tự tương đối của chúng để thực hiện nghiệp vụ.

@Order điều khiển thứ tự gọi listener đồng bộ trong quá trình dispatch. Nó không bảo đảm thứ tự hoàn thành của các listener chạy bất đồng bộ.

## 5. Một phương thức có thể nhận nhiều kiểu event

Nếu nhiều kiểu event chỉ cần kích hoạt cùng một thao tác không cần đọc payload, có thể dùng thuộc tính classes của @EventListener:

~~~java
@Component
public class BusinessActivityListener {

    @EventListener(classes = {
            OrderCreatedEvent.class,
            PaymentCompletedEvent.class
    })
    public void recordBusinessActivity() {
        System.out.println("A business event was received");
    }
}
~~~

Khi dùng thuộc tính classes, phương thức không khai báo tham số. Spring gọi phương thức khi một trong các kiểu event được liệt kê được phát.

Nếu cần đọc dữ liệu cụ thể của từng event, hãy tạo các phương thức riêng với tham số tương ứng. Cách đó làm rõ kiểu dữ liệu và tránh phải phân nhánh hoặc ép kiểu thủ công.

## 6. Lọc listener bằng condition

Có thể thêm điều kiện SpEL để một phương thức chỉ chạy khi event thỏa mãn một biểu thức.

Ví dụ, chỉ xử lý thông báo ưu tiên cao:

~~~java
@Component
public class OrderEventListeners {

    @EventListener(
            condition = "#root.args[0].priority() == 'HIGH'"
    )
    public void handleHighPriority(OrderCreatedEvent event) {
        System.out.println(
                "High priority order: " + event.orderId()
        );
    }
}
~~~

Với phương thức có tham số event, #root.args là mảng các đối số truyền vào listener. #root.args[0] là event đầu tiên. Trong ví dụ, priority() trả về mức ưu tiên của đơn hàng.

Điều kiện được đánh giá trước khi gọi phương thức. Nếu biểu thức trả về false, phương thức listener đó bị bỏ qua; các listener khác phù hợp với cùng event vẫn được xử lý.

Dùng condition để lọc những trường hợp đơn giản. Nếu logic điều kiện phức tạp, cần truy vấn dữ liệu hoặc có nhiều nhánh nghiệp vụ, hãy chuyển phần quyết định vào một service riêng để dễ kiểm thử.

## 7. Giá trị trả về có thể phát event tiếp theo

Một phương thức @EventListener có thể trả về một object khác null. Spring sẽ phát giá trị trả về đó như một event mới trong cùng ApplicationContext.

Ví dụ:

~~~java
@Component
public class OrderEventListeners {

    @EventListener
    public InventoryCheckRequestedEvent requestInventory(
            OrderCreatedEvent event
    ) {
        System.out.println(
                "Request inventory for " + event.orderId()
        );

        return new InventoryCheckRequestedEvent(event.orderId());
    }

    @EventListener
    public void checkInventory(InventoryCheckRequestedEvent event) {
        System.out.println(
                "Check inventory for " + event.orderId()
        );
    }
}
~~~

Luồng xử lý:

1. Publisher phát OrderCreatedEvent.
2. requestInventory nhận event và tạo InventoryCheckRequestedEvent.
3. Spring phát event được trả về.
4. checkInventory nhận InventoryCheckRequestedEvent.

Cách này hữu ích khi một listener chuyển sự kiện sang bước tiếp theo mà không cần tự inject ApplicationEventPublisher.

Nếu phương thức trả về Collection, từng phần tử trong collection được phát như một event riêng. Nếu không muốn phát event tiếp theo, hãy khai báo phương thức trả về void.

Tránh tạo chuỗi event vòng lặp. Ví dụ, listener A phát event B, listener B lại phát event A mà không có điều kiện dừng. Vòng lặp như vậy có thể làm ứng dụng xử lý liên tục hoặc gây tràn stack trong dispatch đồng bộ.

## 8. Ví dụ hoàn chỉnh với Java 17 và Spring Boot

Ví dụ này dùng một bean OrderEventListeners có nhiều phương thức nhận hai kiểu event. Hai phương thức xử lý OrderCreatedEvent có thứ tự rõ ràng; một phương thức khác chỉ chạy khi đơn hàng có priority là HIGH.

### Cấu trúc thư mục

~~~text
spring-multiple-listeners-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── events/
                        ├── MultipleListenersApplication.java
                        ├── OrderCreatedEvent.java
                        ├── PaymentCompletedEvent.java
                        ├── OrderService.java
                        └── OrderEventListeners.java
~~~

### 8.1. Dependency

File pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-multiple-listeners-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
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
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.2. Định nghĩa các event

File OrderCreatedEvent.java:

~~~java
package com.example.events;

public record OrderCreatedEvent(
        String orderId,
        String customerId,
        String priority
) {
}
~~~

File PaymentCompletedEvent.java:

~~~java
package com.example.events;

import java.math.BigDecimal;

public record PaymentCompletedEvent(
        String orderId,
        BigDecimal amount
) {
}
~~~

Đây là các record chỉ chứa kiểu dữ liệu bất biến, phù hợp để truyền thông tin sự kiện giữa các bean.

### 8.3. Publisher phát event

File OrderService.java:

~~~java
package com.example.events;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void createOrder(String orderId, String customerId) {
        publisher.publishEvent(
                new OrderCreatedEvent(orderId, customerId, "HIGH")
        );
    }

    public void completePayment(String orderId, BigDecimal amount) {
        publisher.publishEvent(
                new PaymentCompletedEvent(orderId, amount)
        );
    }
}
~~~

OrderService chỉ phát event. Nó không biết bean nào có bao nhiêu listener method.

### 8.4. Một bean chứa nhiều listener method

File OrderEventListeners.java:

~~~java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
public class OrderEventListeners {

    @EventListener
    @Order(1)
    public void auditCreation(OrderCreatedEvent event) {
        System.out.println(
                "Audit: created order " + event.orderId()
        );
    }

    @EventListener
    @Order(2)
    public void notifyCustomer(OrderCreatedEvent event) {
        System.out.println(
                "Notify: created order " + event.orderId()
        );
    }

    @EventListener(
            condition = "#root.args[0].priority() == 'HIGH'"
    )
    @Order(3)
    public void handleHighPriority(OrderCreatedEvent event) {
        System.out.println(
                "Priority queue: HIGH order " + event.orderId()
        );
    }

    @EventListener
    @Order(1)
    public void auditPayment(PaymentCompletedEvent event) {
        System.out.println(
                "Audit: payment completed " + event.orderId()
        );
    }

    @EventListener
    @Order(2)
    public void notifyPayment(PaymentCompletedEvent event) {
        System.out.println(
                "Notify: payment received for " + event.orderId()
        );
    }
}
~~~

Có năm listener method trong cùng một bean:

- Ba phương thức nhận OrderCreatedEvent.
- Hai phương thức nhận PaymentCompletedEvent.
- Mỗi phương thức chỉ xử lý đúng kiểu event được khai báo.
- @Order quyết định thứ tự gọi trong nhóm listener tương ứng.
- handleHighPriority chỉ chạy khi priority là HIGH.

### 8.5. Khởi chạy ứng dụng

File MultipleListenersApplication.java:

~~~java
package com.example.events;

import java.math.BigDecimal;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultipleListenersApplication implements CommandLineRunner {

    private final OrderService orderService;

    public MultipleListenersApplication(OrderService orderService) {
        this.orderService = orderService;
    }

    public static void main(String[] args) {
        SpringApplication.run(MultipleListenersApplication.class, args);
    }

    @Override
    public void run(String... args) {
        orderService.createOrder("ORD-1001", "CUS-01");

        orderService.completePayment(
                "ORD-1001",
                new BigDecimal("125000.00")
        );
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Bỏ qua log khởi động của Spring Boot, output do ứng dụng in ra:

~~~text
Audit: created order ORD-1001
Notify: created order ORD-1001
Priority queue: HIGH order ORD-1001
Audit: payment completed ORD-1001
Notify: payment received for ORD-1001
~~~

Ba dòng đầu được in khi OrderCreatedEvent được phát. Hai dòng cuối được in khi PaymentCompletedEvent được phát. Publisher chỉ gọi publishEvent hai lần; Spring tự dispatch đến tất cả phương thức listener phù hợp.

## 9. Kết hợp nhiều listener method với @Async

Có thể đánh dấu một hoặc nhiều phương thức listener bằng @Async để chạy trên executor. Cần bật async bằng @EnableAsync:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

Ví dụ thêm một listener method vào bean:

~~~java
@Async
@EventListener
public void sendCustomerEmail(OrderCreatedEvent event) {
    System.out.println(
            "Sending email for " + event.orderId()
    );
}
~~~

Phương thức này chạy bất đồng bộ nếu cấu hình async hoạt động và bean được Spring quản lý. Publisher không chờ phương thức hoàn tất.

Các điểm cần nhớ:

- @Order không đảm bảo thứ tự hoàn thành của các listener bất đồng bộ.
- Nhiều phương thức async trong cùng bean có thể chạy đồng thời.
- Không dùng field mutable dùng chung giữa các phương thức async nếu không có cơ chế đồng bộ phù hợp.
- Exception từ listener async không truyền ngược về publisher như listener đồng bộ; cần cấu hình và giám sát xử lý lỗi của executor.
- Giá trị trả về của listener async không được dùng để phát event tiếp theo. Nếu cần phát event tiếp, inject ApplicationEventPublisher và gọi publishEvent một cách tường minh trong listener.

Một bean chứa nhiều phương thức listener không có nghĩa các phương thức đó luôn chạy tuần tự. Hãy xác định rõ phương thức nào đồng bộ, phương thức nào bất đồng bộ và dữ liệu nào được chia sẻ.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chỉ một trong các phương thức được gọi | Một số phương thức thiếu @EventListener hoặc kiểu tham số không khớp event. | Đánh dấu từng phương thức và kiểm tra kiểu event. |
| Các listener chạy sai thứ tự mong muốn | Dựa vào thứ tự khai báo trong source code hoặc không đặt @Order. | Đặt @Order rõ ràng cho các listener có phụ thuộc thứ tự. |
| Phương thức không nhận được event thứ hai | Phương thức được khai báo cho kiểu event khác. | Kiểm tra kiểu tham số hoặc thuộc tính classes. |
| Lỗi khi dùng classes và tham số event | Phương thức khai báo tham số trong khi dùng thuộc tính classes. | Khi dùng classes, khai báo phương thức không có tham số. |
| Listener chạy dù không mong muốn | Thiếu condition hoặc điều kiện SpEL sai. | Kiểm tra biểu thức và dữ liệu event; kiểm thử cả trường hợp true và false. |
| Event bị phát lặp vô hạn | Các listener phát event tạo thành chu trình không có điều kiện dừng. | Thiết kế luồng event có điểm kết thúc và kiểm tra điều kiện phát tiếp. |
| Dữ liệu dùng chung bị race condition | Nhiều listener async truy cập cùng trạng thái mutable. | Dùng payload bất biến và quản lý trạng thái dùng chung bằng cơ chế phù hợp. |
| Listener không chạy | Bean không được đăng ký trong ApplicationContext. | Đảm bảo class có @Component hoặc được khai báo bằng @Bean trong phạm vi scan. |

## 11. Tổ chức bean listener hợp lý

Đặt nhiều listener method trong cùng bean khi chúng thuộc cùng một nhóm trách nhiệm và có thể được hiểu như một bộ xử lý event thống nhất. Ví dụ, OrderEventListeners có thể gom các thao tác audit, thông báo và theo dõi trạng thái đơn hàng.

Khi số lượng phương thức tăng lên hoặc các hành động thuộc các module khác nhau, nên tách thành nhiều bean:

- OrderAuditListeners: ghi lịch sử.
- OrderNotificationListeners: gửi thông báo.
- OrderMetricsListeners: cập nhật số liệu.

Việc tách bean giúp mỗi nhóm có dependency, cấu hình async, chính sách lỗi và kiểm thử riêng. Dù tách hay gộp, các listener vẫn có thể nhận cùng một event được phát trong ApplicationContext.

Không nên tạo một listener method chỉ để chuyển tiếp lời gọi sang một phương thức khác trong cùng bean nếu không có lý do về điều phối event. Hãy giữ event phản ánh sự việc có ý nghĩa trong nghiệp vụ.

## 12. Tự kiểm tra

1. Spring đăng ký các phương thức @EventListener trong cùng một bean như thế nào?
2. Khi một event có ba listener method phù hợp trong cùng bean, có bao nhiêu phương thức được gọi?
3. Vì sao không nên dựa vào thứ tự khai báo phương thức trong file Java?
4. Khi dùng @EventListener(classes = ...), phương thức có được khai báo tham số không?
5. @Order và condition giải quyết hai vấn đề khác nhau như thế nào?
6. Khi listener trả về một object event, Spring xử lý giá trị đó ra sao?
7. Vì sao @Order không đảm bảo thứ tự hoàn thành khi listener chạy với @Async?
8. Khi nào nên tách nhiều listener method thành các bean riêng?

**Kết quả cần nắm:** Một bean Spring có thể chứa nhiều phương thức @EventListener và mỗi phương thức được đăng ký độc lập. Một event có thể kích hoạt nhiều phương thức phù hợp; dùng @Order để sắp xếp, condition để lọc và giá trị trả về để phát event tiếp theo. Khi dùng async, cần quản lý concurrency và không phụ thuộc vào thứ tự hoàn thành.
