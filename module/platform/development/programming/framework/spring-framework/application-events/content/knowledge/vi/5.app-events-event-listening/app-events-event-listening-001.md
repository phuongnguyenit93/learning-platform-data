# ApplicationListener<E>

**ApplicationListener<E>** là interface của Spring Framework dùng để đăng ký một bean nhận và xử lý application event theo kiểu E. Khi một event phù hợp được publish trong ApplicationContext, Spring gọi phương thức onApplicationEvent(event) của listener. Generic E thể hiện rõ listener quan tâm đến event nào, giúp Spring lọc listener và giúp code tránh ép kiểu thủ công.

## 1. Khai báo và ý nghĩa

Interface nằm trong package org.springframework.context. Dạng khái quát:

~~~java
@FunctionalInterface
public interface ApplicationListener<E extends ApplicationEvent>
        extends EventListener {

    void onApplicationEvent(E event);
}
~~~

Các điểm cần hiểu:

- **E extends ApplicationEvent:** kiểu event phải là ApplicationEvent hoặc lớp con của nó.
- **onApplicationEvent(E event):** callback Spring gọi khi có event tương thích.
- **extends EventListener:** marker interface cho listener.
- **Generic E:** mô tả kiểu event cụ thể mà listener xử lý.

Ví dụ:

~~~java
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("Order created: " + event.getOrderId());
    }
}
~~~

Ở đây E là OrderCreatedEvent, nên phương thức nhận trực tiếp kiểu event cụ thể. Nếu khai báo ApplicationListener<ApplicationEvent>, listener có thể nhận nhiều loại application event và phải tự phân nhánh khi xử lý. Thông thường, nên khai báo kiểu hẹp nhất mà listener thực sự cần.

## 2. Event mà listener nhận

ApplicationListener<E> yêu cầu E kế thừa ApplicationEvent. Một event nghiệp vụ có thể được định nghĩa như sau:

~~~java
import org.springframework.context.ApplicationEvent;

public class OrderCreatedEvent extends ApplicationEvent {

    private final String orderId;

    public OrderCreatedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

ApplicationEvent lưu source, tức đối tượng phát sinh event. Dữ liệu nghiệp vụ riêng được lưu trong các field của lớp con. Event nên biểu đạt điều đã xảy ra, chẳng hạn OrderCreatedEvent, PaymentCompletedEvent hoặc UserRegisteredEvent.

Ưu tiên event bất biến, chứa dữ liệu cần cho listener như ID, giá trị và thời điểm xảy ra. Tránh truyền một entity mutable lớn nếu listener chỉ cần mã định danh; điều đó làm listener phụ thuộc vào trạng thái có thể thay đổi.

Từ Spring Framework 4.2, publisher còn có thể nhận POJO hoặc record thông thường. Spring bọc payload trong **PayloadApplicationEvent**. Tuy nhiên, generic E của ApplicationListener vẫn phải là một kiểu ApplicationEvent. Nếu muốn nhận payload POJO qua interface, có thể khai báo ApplicationListener<PayloadApplicationEvent<MyPayload>> rồi gọi event.getPayload(). Nếu muốn phương thức listener nhận trực tiếp MyPayload, @EventListener thường gọn hơn.

## 3. Spring phát hiện và gọi listener

Một bean triển khai ApplicationListener và được Spring quản lý sẽ được phát hiện trong quá trình khởi tạo ApplicationContext. Context đăng ký listener với ApplicationEventMulticaster.

Luồng cơ bản:

1. ApplicationContext khởi tạo và phát hiện các bean triển khai ApplicationListener.
2. Các listener được đăng ký với ApplicationEventMulticaster của context.
3. Bean nghiệp vụ gọi ApplicationEventPublisher.publishEvent(event).
4. Context chuyển event tới multicaster.
5. Multicaster chọn listener có kiểu event phù hợp.
6. Spring gọi onApplicationEvent(event) trên listener được chọn.

Publisher không cần biết listener nào đang tồn tại. Listener cũng không cần được service phát event gọi trực tiếp. Việc kết nối được thực hiện qua context và multicaster.

### Đăng ký listener thành bean

Có thể dùng component scan:

~~~java
@Component
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Xử lý event.
    }
}
~~~

Hoặc khai báo bằng Java configuration:

~~~java
@Configuration
public class EventConfig {

    @Bean
    public OrderCreatedListener orderCreatedListener() {
        return new OrderCreatedListener();
    }
}
~~~

Điều kiện quan trọng là listener phải thuộc phạm vi quản lý của Spring. Một object được tạo bằng new ở ngoài container không tự được đăng ký với multicaster. Khi cần đăng ký thủ công, có thể dùng ConfigurableApplicationContext.addApplicationListener(...) ; trong ứng dụng thông thường, khai báo bean là cách đơn giản nhất.

## 4. Generic E giúp lọc event

Giả sử ứng dụng có hai event: OrderCreatedEvent và PaymentCompletedEvent. Ta có thể đăng ký listener riêng:

~~~java
public class OrderCreatedListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Xử lý đơn hàng mới.
    }
}

public class PaymentCompletedListener
        implements ApplicationListener<PaymentCompletedEvent> {

    @Override
    public void onApplicationEvent(PaymentCompletedEvent event) {
        // Xử lý thanh toán hoàn tất.
    }
}
~~~

Listener cho OrderCreatedEvent không cần nhận mọi event rồi dùng instanceof để tự lọc. Spring dựa vào kiểu event mà listener khai báo để chọn listener tương thích. Listener khai báo ApplicationListener<DomainEvent> có thể nhận event thuộc các lớp con của DomainEvent.

### Generic và runtime type matching

Java thực hiện type erasure đối với generic, nhưng Spring phân tích generic type của listener bằng ResolvableType và adapter nội bộ. Khi kiểu được khai báo rõ trong class hoặc hierarchy của class, Spring có thể dùng thông tin đó để lọc event.

Tránh raw type như ApplicationListener không có tham số generic. Raw type làm mất thông tin kiểu ở cấp source code, giảm an toàn kiểu và khiến ý định đăng ký listener kém rõ ràng. Hãy giữ kiểu event cụ thể trong khai báo.

## 5. Nhận payload POJO qua ApplicationListener

Có thể publish một đối tượng Java thông thường:

~~~java
public record OrderCreated(String orderId) {
}

// Trong một bean:
publisher.publishEvent(new OrderCreated("ORD-1001"));
~~~

Spring bọc object này trong PayloadApplicationEvent. Listener dùng interface có thể nhận wrapper:

~~~java
public class OrderPayloadListener
        implements ApplicationListener<PayloadApplicationEvent<OrderCreated>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<OrderCreated> event) {
        OrderCreated payload = event.getPayload();
        System.out.println(payload.orderId());
    }
}
~~~

PayloadApplicationEvent là một ApplicationEvent và mang thông tin kiểu payload để Spring phân phối phù hợp khi generic type được giữ rõ ràng.

Nếu không cần truy cập wrapper, có thể dùng annotation để nhận payload trực tiếp:

~~~java
@Component
public class OrderPayloadListener {

    @EventListener
    public void onOrderCreated(OrderCreated event) {
        System.out.println(event.orderId());
    }
}
~~~

Chọn ApplicationListener khi muốn một class có hợp đồng interface tường minh và một điểm nhận event chính. Chọn @EventListener khi muốn handler theo phương thức, nhận trực tiếp POJO, khai báo nhiều handler hoặc dùng điều kiện SpEL.

## 6. Thứ tự gọi listener

Khi nhiều listener cùng nhận một event, có thể chỉ định thứ tự bằng interface Ordered hoặc annotation @Order. Giá trị nhỏ hơn có độ ưu tiên cao hơn.

~~~java
@Component
@Order(1)
public class AuditListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("Audit: " + event.getOrderId());
    }
}

@Component
@Order(2)
public class NotificationListener
        implements ApplicationListener<OrderCreatedEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        System.out.println("Notify: " + event.getOrderId());
    }
}
~~~

Có thể triển khai Ordered nếu muốn xác định thứ tự bằng code:

~~~java
public class AuditListener
        implements ApplicationListener<OrderCreatedEvent>, Ordered {

    @Override
    public int getOrder() {
        return 1;
    }

    @Override
    public void onApplicationEvent(OrderCreatedEvent event) {
        // Ghi audit.
    }
}
~~~

Chỉ chỉ định thứ tự khi các listener thực sự phụ thuộc vào trình tự xử lý. Nếu chúng độc lập, không nên tạo phụ thuộc ngầm vào thứ tự gọi. Khi cấu hình async, thứ tự hoàn tất xử lý có thể khác với luồng đồng bộ.

## 7. Đồng bộ, bất đồng bộ và ngoại lệ

Với SimpleApplicationEventMulticaster mặc định, listener được gọi đồng bộ trên thread publish event. Vì vậy:

- publishEvent thường chỉ trả về sau khi các listener đồng bộ hoàn tất.
- Listener chậm làm tăng thời gian xử lý của service hoặc request phát event.
- Ngoại lệ từ listener đồng bộ có thể truyền ngược về publisher nếu không cấu hình ErrorHandler.

Có thể cấu hình executor cho SimpleApplicationEventMulticaster để dispatch bất đồng bộ. Khi đó listener có thể chạy trên thread khác và publisher có thể tiếp tục trước khi listener hoàn tất. Cần xem xét thread safety, thứ tự hoàn tất, transaction context và xử lý ngoại lệ trong tác vụ async.

Trong Spring Framework hiện đại, ApplicationListener có phương thức supportsAsyncExecution để listener tùy chỉnh khả năng chạy bất đồng bộ. Nếu override và trả về false, listener yêu cầu được gọi đồng bộ ngay cả khi multicaster có executor. Chỉ dùng khi có lý do rõ ràng để listener chạy trên publisher thread.

Nếu listener cần chạy sau khi transaction commit, có thể dùng @TransactionalEventListener. ApplicationListener thông thường không tự biểu đạt transaction phase. Khi nghiệp vụ phụ thuộc vào dữ liệu đã commit, hãy dùng cơ chế transaction-aware phù hợp thay vì giả định event luôn được phát sau commit.

## 8. Ví dụ hoàn chỉnh với Java 17 và Spring Framework

Ví dụ tạo một context, inject ApplicationEventPublisher vào OrderService và đăng ký hai listener triển khai ApplicationListener<OrderCreatedEvent>. Hai listener có thứ tự bằng @Order. Ví dụ dùng Java 17 và Spring Framework 6.2.0.

### Cấu trúc thư mục

~~~text
application-listener-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationListenerDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>application-listener-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### ApplicationListenerDemo.java

~~~java
package demo;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

public class ApplicationListenerDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);
            service.createOrder("ORD-1001");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        public AuditListener auditListener() {
            return new AuditListener();
        }

        @Bean
        public NotificationListener notificationListener() {
            return new NotificationListener();
        }
    }

    public static class OrderCreatedEvent extends ApplicationEvent {

        private final String orderId;

        public OrderCreatedEvent(Object source, String orderId) {
            super(source);
            this.orderId = orderId;
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public static class OrderService {

        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void createOrder(String orderId) {
            System.out.println("Created: " + orderId);
            publisher.publishEvent(new OrderCreatedEvent(this, orderId));
        }
    }

    @Order(1)
    public static class AuditListener
            implements ApplicationListener<OrderCreatedEvent> {

        @Override
        public void onApplicationEvent(OrderCreatedEvent event) {
            System.out.println("Audit: " + event.getOrderId());
        }
    }

    @Order(2)
    public static class NotificationListener
            implements ApplicationListener<OrderCreatedEvent> {

        @Override
        public void onApplicationEvent(OrderCreatedEvent event) {
            System.out.println("Notify: " + event.getOrderId());
        }
    }
}
~~~

### Biên dịch và chạy

Chạy tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ApplicationListenerDemo
~~~

Kết quả stdout:

~~~text
Created: ORD-1001
Audit: ORD-1001
Notify: ORD-1001
~~~

Luồng chạy:

1. AnnotationConfigApplicationContext khởi tạo AppConfig và các bean.
2. OrderService nhận ApplicationEventPublisher từ context qua tham số @Bean.
3. createOrder in thông tin tạo đơn và publish OrderCreatedEvent.
4. Multicaster chọn hai listener vì cả hai khai báo ApplicationListener<OrderCreatedEvent>.
5. @Order(1) khiến AuditListener được gọi trước @Order(2) NotificationListener trong dispatch đồng bộ.
6. OrderService không gọi trực tiếp listener nào; Spring thực hiện việc phân phối.

## 9. So sánh ApplicationListener và @EventListener

| Tiêu chí | ApplicationListener<E> | @EventListener |
|---|---|---|
| Hình thức | Implement interface | Đánh dấu phương thức trong bean |
| Kiểu event | E phải extends ApplicationEvent | Nhận ApplicationEvent hoặc payload POJO |
| Số handler | Một phương thức onApplicationEvent cho mỗi implementation | Một bean có thể có nhiều phương thức |
| Điều kiện lọc | Generic event type hoặc logic trong handler | Có thể dùng condition với SpEL |
| Thứ tự | Ordered hoặc @Order | Ordered hoặc @Order |
| Phù hợp | Listener có hợp đồng interface tường minh | Xử lý linh hoạt theo phương thức |

Dùng ApplicationListener khi muốn class thể hiện rõ vai trò listener qua interface, cần hợp đồng có thể tái sử dụng hoặc tích hợp với API Spring dựa trên interface. Dùng @EventListener khi muốn code ngắn, nhận trực tiếp payload hoặc khai báo nhiều handler trong cùng bean.

## 10. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng ApplicationListener raw type | Mất thông tin kiểu event và giảm an toàn kiểu | Dùng ApplicationListener<OrderCreatedEvent> |
| Dùng POJO trực tiếp làm E | Không biên dịch vì E phải extends ApplicationEvent | Dùng PayloadApplicationEvent<MyPayload> hoặc @EventListener |
| Listener không phải Spring bean | Context không tự đăng ký listener | Khai báo @Component hoặc @Bean |
| Tạo listener bằng new ngoài container | Listener không được multicaster quản lý | Để Spring tạo bean hoặc đăng ký qua context |
| Mọi listener đều nhận ApplicationEvent | Phải tự phân nhánh và tăng coupling | Khai báo event type cụ thể |
| Nghĩ listener mặc định chạy nền | Publisher vẫn phải chờ listener đồng bộ | Cấu hình executor hoặc @Async khi phù hợp |
| Dựa vào thứ tự đăng ký tình cờ | Trình tự thiếu ổn định | Dùng @Order hoặc Ordered khi cần |
| Không xử lý ngoại lệ | Lỗi listener có thể ảnh hưởng luồng publish | Xác định error handling và logging |
| Dùng event nội bộ thay message broker | Không có độ bền và giao nhận liên process mặc định | Dùng broker/outbox khi cần |

## 11. Checklist triển khai

- Xác định rõ event listener cần nhận.
- Dùng ApplicationListener với generic event type cụ thể.
- Đảm bảo E kế thừa ApplicationEvent; với payload POJO, dùng PayloadApplicationEvent hoặc @EventListener.
- Đăng ký listener thành bean trong đúng ApplicationContext.
- Giữ event bất biến và chỉ chứa dữ liệu cần thiết.
- Dùng @Order hoặc Ordered khi có yêu cầu thứ tự thực sự.
- Xác định listener chạy đồng bộ hay bất đồng bộ.
- Xử lý ngoại lệ và transaction theo yêu cầu nghiệp vụ.
- Viết unit test cho logic listener và integration test để xác nhận context đăng ký, lọc và gọi listener.

**ApplicationListener<E>** cung cấp hợp đồng tường minh để bean Spring lắng nghe event theo kiểu. Khi khai báo E cụ thể, đăng ký listener trong ApplicationContext và giữ event có cấu trúc rõ ràng, ứng dụng có thể tách nơi phát sự kiện khỏi nơi xử lý mà vẫn giữ được tính an toàn kiểu và khả năng kiểm thử.