# Chọn listener theo kiểu event

## 1. Mục tiêu

Trong Spring Application Events, một publisher có thể phát nhiều loại event và mỗi loại event có thể được nhiều listener quan tâm. Spring cần xác định listener nào phù hợp với event đang được phát. Việc lựa chọn này dựa trên kiểu event mà listener khai báo, sau đó có thể áp dụng thêm điều kiện lọc.

Ví dụ, một ứng dụng bán hàng có thể phát OrderCreatedEvent, OrderCancelledEvent và PaymentReceivedEvent. Listener theo dõi OrderEvent có thể xử lý mọi event thuộc nhóm đơn hàng; listener chỉ khai báo OrderCreatedEvent sẽ nhận riêng event tạo đơn; listener theo dõi PaymentReceivedEvent sẽ nhận thông báo thanh toán.

Bài học tập trung vào cách Spring ghép kiểu event với listener, cách dùng @EventListener và ApplicationListener, quan hệ kế thừa/interface, POJO payload, generic event và các lỗi thường gặp khi kiểu khai báo không khớp.

Sau bài học, bạn có thể:
- Giải thích Spring chọn listener dựa trên kiểu event như thế nào.
- Viết listener cho một kiểu cụ thể hoặc một nhóm kiểu thông qua lớp cha/interface.
- Phân biệt listener nhận POJO payload với listener nhận wrapper PayloadApplicationEvent.
- Dùng điều kiện SpEL để lọc sâu hơn sau khi kiểu event đã phù hợp.
- Nhận biết giới hạn của generic type do Java type erasure và cách cung cấp thông tin kiểu lúc chạy.

## 2. Nguyên tắc ghép kiểu event

Với listener dùng @EventListener, kiểu tham số của method cho biết listener muốn nhận event nào. Spring chỉ gọi method khi kiểu event được phát tương thích với kiểu mà method khai báo.

Có thể hiểu quy tắc cơ bản như sau:

- Listener khai báo OrderCreatedEvent nhận OrderCreatedEvent.
- Listener khai báo OrderEvent nhận các event cụ thể triển khai interface OrderEvent.
- Listener khai báo một lớp cha nhận event thuộc lớp con tương ứng.
- Listener khai báo một kiểu không có quan hệ tương thích sẽ không được gọi cho event đó.

Nói theo quan hệ kiểu Java, nếu đối tượng event có thể được gán cho biến có kiểu tham số của listener, listener đó có thể là một ứng viên phù hợp. Spring sử dụng thông tin kiểu event để chọn listener trong ApplicationEventMulticaster.

Ví dụ:

~~~java
public interface OrderEvent {
    String orderId();
}

public record OrderCreatedEvent(String orderId) implements OrderEvent {
}

public record OrderCancelledEvent(String orderId) implements OrderEvent {
}
~~~

Một listener nhận OrderEvent có thể xử lý cả OrderCreatedEvent và OrderCancelledEvent. Một listener nhận riêng OrderCreatedEvent chỉ xử lý loại tạo đơn hàng. Điều này cho phép tổ chức listener theo nhóm nghiệp vụ mà không cần publisher biết danh sách listener cụ thể.

## 3. Dùng @EventListener để chọn theo kiểu

Cách phổ biến nhất trong ứng dụng Spring là đặt @EventListener trên method của bean được Spring quản lý. Tham số method chính là kiểu event mà listener quan tâm.

~~~java
@Component
public class OrderListeners {

    @EventListener
    public void onCreated(OrderCreatedEvent event) {
        System.out.println("Đơn hàng được tạo: " + event.orderId());
    }

    @EventListener
    public void onCancelled(OrderCancelledEvent event) {
        System.out.println("Đơn hàng bị hủy: " + event.orderId());
    }
}
~~~

Khi publisher phát OrderCreatedEvent, Spring gọi onCreated. Khi publisher phát OrderCancelledEvent, Spring gọi onCancelled. Hai method không cần được publisher gọi trực tiếp.

Một bean có thể có nhiều method @EventListener cho các kiểu event khác nhau. Nhiều bean cũng có thể đăng ký cùng một kiểu event; tất cả listener phù hợp đều có thể được gọi.

Listener phải thuộc một bean trong ApplicationContext. Đặt @EventListener trên một object tự tạo bằng new mà không đăng ký object đó với Spring sẽ không làm method tự động trở thành listener.

## 4. Chọn listener theo interface hoặc lớp cha

Khi nhiều event thuộc cùng một nhóm nghiệp vụ, có thể khai báo một interface hoặc lớp cha chung. Listener nhận kiểu chung đó sẽ xử lý các event cụ thể có quan hệ kế thừa hoặc triển khai tương ứng.

~~~java
public interface OrderEvent {
    String orderId();
}

public record OrderCreatedEvent(String orderId) implements OrderEvent {
}

public record OrderCancelledEvent(
        String orderId,
        String reason
) implements OrderEvent {
}
~~~

~~~java
@Component
public class OrderEventListeners {

    @EventListener
    public void onAnyOrderEvent(OrderEvent event) {
        System.out.println("Sự kiện đơn hàng: " + event.orderId());
    }

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Xử lý riêng đơn hàng mới: " + event.orderId());
    }
}
~~~

Khi phát OrderCreatedEvent, cả hai method đều phù hợp: một method nhận interface OrderEvent và method kia nhận kiểu cụ thể OrderCreatedEvent. Khi phát OrderCancelledEvent, chỉ method nhận OrderEvent phù hợp trong ví dụ trên.

Đây là cách hữu ích để tách phần xử lý chung khỏi phần xử lý riêng. Ví dụ, một listener chung có thể ghi audit cho mọi thay đổi đơn hàng, trong khi listener cụ thể gửi thông báo chỉ khi đơn hàng được tạo.

Nếu nhiều listener cùng nhận một event và thứ tự gọi có ý nghĩa, dùng @Order hoặc triển khai Ordered. Giá trị order nhỏ hơn có độ ưu tiên cao hơn. @Order chỉ sắp xếp các listener phù hợp với cùng lần dispatch; nó không thay đổi kiểu event và không biến listener không tương thích thành listener phù hợp.

Không nên lạm dụng một lớp cha chung quá rộng. Nếu interface chỉ gom những event không có ý nghĩa xử lý chung, listener nhận interface đó có thể phải kiểm tra instanceof liên tục và trở nên khó bảo trì. Chỉ tạo nhóm event khi có hành vi hoặc dữ liệu chung thực sự.

## 5. ApplicationListener và kiểu generic

Ngoài @EventListener, Spring cung cấp interface ApplicationListener<E extends ApplicationEvent>. Kiểu generic E xác định loại ApplicationEvent mà listener muốn nhận.

Ví dụ với event kế thừa ApplicationEvent:

~~~java
public class OrderCreatedApplicationEvent extends ApplicationEvent {

    private final String orderId;

    public OrderCreatedApplicationEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

~~~java
@Component
public class OrderCreatedApplicationListener
        implements ApplicationListener<OrderCreatedApplicationEvent> {

    @Override
    public void onApplicationEvent(OrderCreatedApplicationEvent event) {
        System.out.println("Đã tạo đơn: " + event.getOrderId());
    }
}
~~~

Spring đăng ký listener này theo kiểu ApplicationEvent cụ thể được khai báo. ApplicationListener phù hợp khi muốn một bean chuyên trách một kiểu event và thích triển khai theo interface. @EventListener thường ngắn gọn hơn khi một bean cần nhiều method lắng nghe các event khác nhau.

Lưu ý ràng buộc kiểu: ApplicationListener<E> nhận E là một ApplicationEvent. Nếu publisher phát một POJO hoặc record thông thường, Spring sẽ bọc payload đó trong PayloadApplicationEvent. Để nhận trực tiếp POJO payload theo kiểu của nó, dùng @EventListener với tham số là kiểu payload, hoặc dùng ApplicationListener<PayloadApplicationEvent<...>> khi thực sự muốn làm việc với wrapper.

## 6. POJO event và PayloadApplicationEvent

Từ Spring Framework 4.2, publisher có thể phát một object Java thông thường; object đó không cần kế thừa ApplicationEvent:

~~~java
eventPublisher.publishEvent(new OrderCreatedEvent("ORD-1001"));
~~~

Spring biểu diễn POJO này bằng PayloadApplicationEvent. Với @EventListener, Spring có thể ghép theo kiểu payload và truyền trực tiếp payload cho method:

~~~java
@EventListener
public void onCreated(OrderCreatedEvent event) {
    System.out.println(event.orderId());
}
~~~

Method trên nhận OrderCreatedEvent, không cần tự bóc tách PayloadApplicationEvent.

Nếu muốn nhận wrapper cùng metadata của event, có thể khai báo listener theo PayloadApplicationEvent:

~~~java
@EventListener
public void onPayload(PayloadApplicationEvent<?> event) {
    Object payload = event.getPayload();
    System.out.println("Payload type: " + payload.getClass().getName());
}
~~~

Cần phân biệt hai cách khai báo. Listener nhận kiểu payload phù hợp khi cần dữ liệu nghiệp vụ trực tiếp. Listener nhận PayloadApplicationEvent phù hợp khi cần xử lý wrapper hoặc quan sát nhiều loại payload. Không nên nhầm lẫn POJO payload với event class kế thừa ApplicationEvent.

## 7. Lọc thêm bằng điều kiện

Kiểu event xác định nhóm listener có thể nhận event. Trong một số trường hợp, listener chỉ cần xử lý một phần event thuộc cùng kiểu. @EventListener hỗ trợ thuộc tính condition để dùng biểu thức SpEL lọc thêm.

Ví dụ, chỉ xử lý thanh toán có giá trị từ 1.000 trở lên:

~~~java
@Component
public class PaymentListeners {

    @EventListener(condition = "#root.args[0].amount() >= 1000")
    public void onLargePayment(PaymentReceivedEvent event) {
        System.out.println("Thanh toán lớn: " + event.amount());
    }
}
~~~

Điều kiện được đánh giá sau khi listener đã được xem là phù hợp theo kiểu event. Nếu điều kiện trả về false, method không được gọi. #root.event tham chiếu ApplicationEvent được dispatch; với POJO/record, đó là wrapper PayloadApplicationEvent. #root.args[0] là đối số đầu tiên của listener, tức payload mà method nhận trực tiếp.

Không nên dùng condition thay cho thiết kế kiểu event rõ ràng. Nếu hai nhóm sự kiện có ý nghĩa nghiệp vụ khác nhau, hai event type riêng thường dễ đọc và dễ kiểm thử hơn một event chung với nhiều nhánh điều kiện.

## 8. Generic event và type erasure

Java xóa thông tin tham số generic ở runtime trong nhiều tình huống. Ví dụ, hai object GenericEvent<Order> và GenericEvent<Customer> có thể cùng mang class runtime GenericEvent. Vì vậy, chỉ dựa vào generic type khai báo trong source code chưa chắc đủ để phân biệt payload cụ thể khi Spring kiểm tra event lúc chạy.

Nếu cần Spring phân biệt generic event type, event có thể triển khai ResolvableTypeProvider để cung cấp ResolvableType đầy đủ:

~~~java
import org.springframework.core.ResolvableType;
import org.springframework.core.ResolvableTypeProvider;

public class EntityCreatedEvent<T> implements ResolvableTypeProvider {

    private final T entity;

    public EntityCreatedEvent(T entity) {
        this.entity = entity;
    }

    public T getEntity() {
        return entity;
    }

    @Override
    public ResolvableType getResolvableType() {
        return ResolvableType.forClassWithGenerics(
                getClass(),
                ResolvableType.forInstance(entity)
        );
    }
}
~~~

ResolvableType cho phép Spring xem xét cả kiểu tham số generic thay vì chỉ class thô. Listener có thể khai báo kiểu generic tương ứng khi event cung cấp đủ thông tin kiểu lúc chạy.

Trong ứng dụng thông thường, nếu chỉ có vài loại event khác nhau, dùng các lớp event cụ thể thường đơn giản và ít lỗi hơn. Chỉ dùng generic event khi có lý do thiết kế rõ ràng và đã kiểm thử việc ghép kiểu với cấu trúc event thực tế.

## 9. Ví dụ chạy được với Java 17+ và Spring Framework 6.2.0

Ví dụ này minh họa Spring chọn listener theo kiểu event. OrderCreatedEvent và OrderCancelledEvent cùng triển khai OrderEvent. PaymentReceivedEvent là một loại riêng. Một publisher phát lần lượt ba object và các listener phù hợp sẽ được gọi.

### 9.1. Cấu trúc dự án

~~~text
spring-listener-type/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── events/
                        ├── EventDemo.java
                        ├── Events.java
                        ├── EventPublisherService.java
                        └── EventListeners.java
~~~

### 9.2. Cấu hình Maven

Tệp pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-listener-type</artifactId>
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

### 9.3. Định nghĩa event

Tệp src/main/java/com/example/events/Events.java:

~~~java
package com.example.events;

public final class Events {

    private Events() {
    }

    public interface OrderEvent {
        String orderId();
    }

    public record OrderCreatedEvent(String orderId)
            implements OrderEvent {
    }

    public record OrderCancelledEvent(String orderId, String reason)
            implements OrderEvent {
    }

    public record PaymentReceivedEvent(String orderId, long amount) {
    }
}
~~~

OrderCreatedEvent và OrderCancelledEvent thuộc nhóm OrderEvent. PaymentReceivedEvent không triển khai interface đó nên không được listener nhận OrderEvent xử lý.

### 9.4. Tạo các listener theo kiểu

Tệp src/main/java/com/example/events/EventListeners.java:

~~~java
package com.example.events;

import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
public class EventListeners {

    @Order(1)
    @EventListener
    public void onAnyOrderEvent(Events.OrderEvent event) {
        System.out.println("OrderEvent listener: "
                + event.getClass().getSimpleName()
                + " " + event.orderId());
    }

    @Order(2)
    @EventListener
    public void onOrderCreated(Events.OrderCreatedEvent event) {
        System.out.println("OrderCreated listener: " + event.orderId());
    }

    @EventListener
    public void onPaymentReceived(Events.PaymentReceivedEvent event) {
        System.out.println("Payment listener: "
                + event.orderId() + " amount=" + event.amount());
    }
}
~~~

Listener onAnyOrderEvent nhận mọi event triển khai OrderEvent. Listener onOrderCreated chỉ nhận OrderCreatedEvent. Hai method cùng nhận OrderCreatedEvent nên @Order xác định thứ tự gọi giữa chúng. Listener onPaymentReceived chỉ nhận PaymentReceivedEvent.

### 9.5. Tạo publisher

Tệp src/main/java/com/example/events/EventPublisherService.java:

~~~java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class EventPublisherService {

    private final ApplicationEventPublisher eventPublisher;

    public EventPublisherService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void publishExamples() {
        eventPublisher.publishEvent(
                new Events.OrderCreatedEvent("ORD-1001"));

        eventPublisher.publishEvent(
                new Events.PaymentReceivedEvent("ORD-1001", 1200));

        eventPublisher.publishEvent(
                new Events.OrderCancelledEvent("ORD-1002", "Customer request"));
    }
}
~~~

Publisher chỉ phát object event. Nó không cần kiểm tra listener nào được đăng ký hoặc gọi trực tiếp từng method.

### 9.6. Khởi động ứng dụng

Tệp src/main/java/com/example/events/EventDemo.java:

~~~java
package com.example.events;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan
public class EventDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(EventDemo.class)) {
            context.getBean(EventPublisherService.class).publishExamples();
        }
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=com.example.events.EventDemo
~~~

Kết quả stdout:

~~~text
OrderEvent listener: OrderCreatedEvent ORD-1001
OrderCreated listener: ORD-1001
Payment listener: ORD-1001 amount=1200
OrderEvent listener: OrderCancelledEvent ORD-1002
~~~

Giải thích kết quả:

- OrderCreatedEvent triển khai OrderEvent nên onAnyOrderEvent được gọi; nó cũng khớp onOrderCreated. @Order(1) khiến listener nhóm chạy trước listener cụ thể có @Order(2).
- PaymentReceivedEvent không triển khai OrderEvent nên không gọi hai listener đơn hàng. Nó chỉ gọi onPaymentReceived.
- OrderCancelledEvent triển khai OrderEvent nên chỉ gọi onAnyOrderEvent trong ví dụ này.

Ví dụ dùng POJO record, vì vậy Spring tự bọc chúng trong PayloadApplicationEvent khi publish. @EventListener nhận trực tiếp record payload theo kiểu tham số đã khai báo.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra hoặc xử lý |
|---|---|---|
| Listener không chạy | Bean chưa được đăng ký trong ApplicationContext | Kiểm tra @Component, @Bean và phạm vi component scan |
| Listener không nhận event | Kiểu tham số không tương thích với event | Kiểm tra class, interface và quan hệ kế thừa |
| Listener nhận nhiều event hơn dự kiến | Listener khai báo lớp cha hoặc interface chung | Kiểm tra phạm vi kiểu cha; tách event type nếu cần ranh giới rõ |
| Listener POJO không chạy | Nhầm wrapper PayloadApplicationEvent với payload type | Dùng @EventListener với kiểu payload hoặc listener wrapper phù hợp |
| Hai listener cùng chạy nhưng sai thứ tự mong đợi | Chưa khai báo thứ tự cho listener cùng event | Dùng @Order hoặc Ordered khi thứ tự thực sự cần thiết |
| Generic listener không phân biệt được tham số | Type erasure làm mất thông tin generic lúc chạy | Dùng event type cụ thể hoặc ResolvableTypeProvider |
| Listener chạy dù dữ liệu không thỏa điều kiện | Chỉ kiểm tra kiểu event, chưa lọc theo nội dung | Dùng condition hoặc kiểm tra nghiệp vụ trong listener |

Khi debug, hãy ghi lại class runtime của event và kiểm tra listener đã được đăng ký chưa. Với payload event, kiểm tra cả kiểu payload lẫn wrapper. Với generic event, kiểm tra ResolvableType thực tế thay vì chỉ nhìn khai báo generic trong source code.

## 11. Gợi ý thiết kế

Chọn kiểu event theo ý nghĩa nghiệp vụ và nhu cầu của subscriber:

- Dùng kiểu event cụ thể khi chỉ một nhóm listener cần nhận một sự kiện.
- Dùng interface hoặc lớp cha khi nhiều event có dữ liệu và hành vi chung mà listener thực sự cần xử lý.
- Dùng @EventListener khi muốn khai báo listener ngắn gọn theo method.
- Dùng ApplicationListener khi muốn triển khai một listener chuyên biệt theo interface cho ApplicationEvent.
- Dùng condition để lọc thêm theo dữ liệu của event sau khi kiểu đã phù hợp.
- Dùng ResolvableTypeProvider khi generic event cần giữ thông tin kiểu tham số ở runtime.

Giữ event payload bất biến nếu có thể. Không nên phát một object mutable rồi tiếp tục thay đổi nó sau khi publish; listener có thể quan sát dữ liệu ở trạng thái không nhất quán. Nếu cần nhiều loại subscriber xử lý độc lập, payload nên chứa dữ liệu đủ rõ ràng và không phụ thuộc vào trạng thái nội bộ có thể thay đổi của publisher.

## 12. Checklist kiểm tra

- [ ] Event có tên và kiểu phản ánh đúng sự kiện nghiệp vụ.
- [ ] Listener là bean được Spring quản lý.
- [ ] Kiểu tham số @EventListener tương thích với kiểu event được phát.
- [ ] Quan hệ interface/lớp cha được dùng có chủ đích.
- [ ] Đã phân biệt payload POJO và PayloadApplicationEvent khi cần.
- [ ] Generic event có thông tin kiểu runtime nếu việc ghép generic phụ thuộc vào nó.
- [ ] Điều kiện SpEL chỉ được dùng cho lọc bổ sung, không che giấu mô hình event.
- [ ] Thứ tự giữa các listener cùng event được cấu hình khi nghiệp vụ yêu cầu.
- [ ] Đã kiểm thử event nào gọi listener nào và xác nhận thứ tự cần thiết.

## 13. Ghi nhớ

Spring chọn listener dựa trên kiểu event mà listener khai báo. Với @EventListener, kiểu tham số của method là kiểu được ghép; event triển khai interface hoặc kế thừa lớp cha có thể được nhận bởi listener khai báo kiểu chung đó. @Order sắp xếp các listener phù hợp với cùng một event.

Với POJO hoặc record, Spring dùng PayloadApplicationEvent làm wrapper nhưng @EventListener có thể nhận trực tiếp payload. ApplicationListener<E> dành cho các kiểu E kế thừa ApplicationEvent. Khi cần lọc theo dữ liệu, dùng condition; khi generic type cần được phân biệt lúc chạy, cung cấp thông tin ResolvableType hoặc ưu tiên event class cụ thể. Hiểu đúng các quy tắc này giúp listener chỉ xử lý những event mà nó thực sự quan tâm.
