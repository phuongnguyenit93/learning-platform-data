# Kiểu event và cơ chế chọn listener

## Mục tiêu

Sau bài này, bạn có thể giải thích Spring xác định loại event được publish như thế nào, cách ApplicationEventMulticaster chọn listener phù hợp, sự khác nhau giữa lọc theo kiểu và lọc bằng điều kiện SpEL, cách generic type ảnh hưởng đến việc chọn listener, và cách kiểm soát thứ tự cũng như phương thức đăng ký listener.

## 1. Vì sao Spring cần xác định kiểu event?

Một ứng dụng có thể phát nhiều loại sự kiện: OrderPlaced, OrderCancelled, PaymentReceived, UserRegistered hoặc ContextRefreshedEvent. Cùng một thời điểm, trong ApplicationContext có thể có hàng chục listener. Mỗi listener chỉ nên được gọi khi sự kiện phù hợp với trách nhiệm của nó.

Ví dụ:

- Listener gửi email xác nhận chỉ quan tâm OrderPlaced.
- Listener hoàn tiền chỉ quan tâm OrderCancelled.
- Listener audit có thể quan tâm cả OrderPlaced và OrderCancelled.
- Listener theo dõi vòng đời Spring có thể quan tâm ContextRefreshedEvent.

Nếu Spring gọi tất cả listener cho mọi event, mỗi listener phải tự kiểm tra kiểu và bỏ qua phần lớn sự kiện. Cách đó vừa tốn công vừa khiến logic phân phối bị lặp ở nhiều nơi.

Spring giải quyết bằng cơ chế **event type matching**: listener khai báo kiểu event mà nó nhận, Spring đối chiếu kiểu đó với kiểu event thực tế trước khi gọi listener.

## 2. Hai thành phần chính: publisher và multicaster

Publisher chịu trách nhiệm công bố một sự kiện thông qua ApplicationEventPublisher. ApplicationContext triển khai hợp đồng này và chuyển việc phân phối đến một ApplicationEventMulticaster.

ApplicationEventMulticaster là thành phần quản lý danh sách listener và phát event đến các listener phù hợp. Trong cấu hình mặc định, Spring dùng SimpleApplicationEventMulticaster.

Luồng tổng quát:

1. Publisher gọi publishEvent(event).
2. ApplicationContext xác định event và kiểu ResolvableType tương ứng.
3. ApplicationEventMulticaster lấy các listener đã đăng ký.
4. Spring lọc listener theo event type; với listener hỗ trợ, có thể lọc thêm theo source type.
5. Các listener phù hợp được sắp xếp theo thứ tự ưu tiên rồi được gọi.
6. Với listener dùng điều kiện SpEL, Spring đánh giá condition trước khi thực thi phương thức.

Có thể hình dung:

~~~text
Publisher
   |
   | publishEvent(event)
   v
ApplicationContext
   |
   v
ApplicationEventMulticaster
   |
   +-- Listener A: event type phù hợp? ---- condition đúng? ---> gọi
   |
   +-- Listener B: event type không phù hợp ------------------> bỏ qua
   |
   +-- Listener C: event type phù hợp? ---- condition sai? ---> bỏ qua
   |
   +-- Listener D: event type phù hợp? ---- condition đúng? ---> gọi
~~~

Việc chọn listener là một bước của hạ tầng Spring. Publisher chỉ cần phát sự kiện đúng thời điểm và đúng dữ liệu, không cần tự tìm hoặc gọi từng listener.

## 3. Kiểu event được xác định từ đâu?

### Với ApplicationEvent

Nếu publisher truyền một đối tượng kế thừa ApplicationEvent, kiểu của lớp event là cơ sở để Spring xác định listener phù hợp.

Ví dụ:

~~~java
public class OrderPlacedEvent extends ApplicationEvent {

    private final String orderId;

    public OrderPlacedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

Listener có thể khai báo đúng kiểu:

~~~java
@EventListener
void onOrderPlaced(OrderPlacedEvent event) {
    System.out.println(event.getOrderId());
}
~~~

Listener chỉ khai báo OrderPlacedEvent sẽ không được gọi cho một event khác không có quan hệ kiểu tương thích.

### Với payload là đối tượng thông thường

Spring Framework cho phép publish một POJO hoặc record không kế thừa ApplicationEvent:

~~~java
eventPublisher.publishEvent(
        new OrderPlaced("DH-3001", new BigDecimal("120000"), "WEB"));
~~~

Spring bọc đối tượng này trong PayloadApplicationEvent. Khi xác định listener cho payload, Spring sử dụng thông tin kiểu của payload để hỗ trợ listener khai báo trực tiếp kiểu OrderPlaced.

~~~java
@EventListener
void onOrderPlaced(OrderPlaced event) {
    System.out.println(event.orderId());
}
~~~

Listener không phải khai báo PayloadApplicationEvent<OrderPlaced> nếu chỉ cần dữ liệu nghiệp vụ. Khi cần đọc wrapper, listener có thể khai báo kiểu PayloadApplicationEvent<OrderPlaced> và truy cập getPayload().

### Kiểu lớp cha và kiểu con

Việc chọn listener dựa trên khả năng tương thích kiểu. Nếu một event có kiểu con của kiểu listener khai báo, listener cho kiểu cha có thể nhận event đó.

Ví dụ, OrderPlacedEvent kế thừa OrderEvent:

~~~java
abstract class OrderEvent extends ApplicationEvent {

    protected OrderEvent(Object source) {
        super(source);
    }
}

final class OrderPlacedEvent extends OrderEvent {

    public OrderPlacedEvent(Object source) {
        super(source);
    }
}
~~~

Listener nhận mọi loại OrderEvent:

~~~java
@EventListener
void auditOrder(OrderEvent event) {
    System.out.println("Audit order event");
}
~~~

Listener nhận riêng OrderPlacedEvent:

~~~java
@EventListener
void sendConfirmation(OrderPlacedEvent event) {
    System.out.println("Send confirmation");
}
~~~

Khi OrderPlacedEvent được phát, cả hai listener đều có kiểu tương thích. Nếu phát một event khác cũng kế thừa OrderEvent, listener audit vẫn có thể nhận, còn listener sendConfirmation sẽ không được gọi.

Đây là lý do nên tổ chức event hierarchy theo quan hệ nghiệp vụ có ý nghĩa. Không nên tạo một lớp cha quá rộng chỉ để nhiều listener cùng nhận event một cách tiện lợi.

## 4. ApplicationListener khai báo kiểu nhận event

ApplicationListener là interface có tham số generic:

~~~java
public interface ApplicationListener<E extends ApplicationEvent> {
    void onApplicationEvent(E event);
}
~~~

Tham số generic E xác định loại ApplicationEvent listener quan tâm.

Ví dụ:

~~~java
@Component
public class OrderPlacedListener
        implements ApplicationListener<OrderPlacedEvent> {

    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        System.out.println("Order placed");
    }
}
~~~

Spring có thể đọc kiểu generic OrderPlacedEvent để xác định listener phù hợp. Cách này có ưu điểm là rõ ràng và type-safe, nhưng một class thường tập trung vào một loại event được khai báo ở generic parameter.

Với event là payload thông thường, ApplicationListener không nhận trực tiếp một POJO tùy ý vì generic của interface bị giới hạn bởi ApplicationEvent. Có thể đăng ký ApplicationListener<PayloadApplicationEvent<OrderPlaced>> nếu cần làm việc ở cấp wrapper, hoặc dùng @EventListener để khai báo trực tiếp kiểu payload.

## 5. @EventListener suy luận event type từ chữ ký phương thức

@EventListener cho phép đăng ký listener bằng một phương thức trong bean do Spring quản lý:

~~~java
@Component
class OrderListeners {

    @EventListener
    void onOrderPlaced(OrderPlaced event) {
        // Xử lý OrderPlaced
    }

    @EventListener
    void onOrderCancelled(OrderCancelled event) {
        // Xử lý OrderCancelled
    }
}
~~~

Với một event type, tham số phương thức thường chính là kiểu event mà listener nhận. Spring dùng chữ ký phương thức để tạo adapter triển khai ApplicationListener ở phía sau.

Quá trình xử lý annotation được thực hiện bởi EventListenerMethodProcessor. Processor phát hiện các phương thức @EventListener trên bean được quản lý và đăng ký listener tương ứng với ApplicationEventMulticaster.

Điều kiện quan trọng là bean phải được Spring quản lý và được phát hiện trong quá trình khởi tạo context. Không nên đánh dấu bean chứa @EventListener là lazy nếu muốn listener được đăng ký ngay khi context khởi động; bean lazy có thể chưa được khởi tạo nên phương thức listener chưa được đăng ký.

### Một phương thức nhận nhiều event type

Nếu phương thức không cần tham số event, có thể khai báo nhiều lớp trên annotation:

~~~java
@EventListener(classes = {
        ContextStartedEvent.class,
        ContextRefreshedEvent.class
})
void handleContextLifecycle() {
    System.out.println("Context lifecycle changed");
}
~~~

Khi classes chứa nhiều kiểu event, phương thức không được khai báo tham số. Nếu chỉ có một kiểu trong classes, phương thức có thể nhận một tham số phù hợp.

Cách này hữu ích khi nhiều event cần kích hoạt cùng một thao tác không phụ thuộc dữ liệu cụ thể của event. Nếu cần dữ liệu riêng của từng event, nên dùng các phương thức listener có kiểu tham số cụ thể.

## 6. Generic event và ResolvableType

Spring có thể lọc event theo generic type khi thông tin generic được xác định tại runtime.

Ví dụ, một hệ thống phát event khi tạo entity. Listener chỉ muốn nhận entity kiểu Person:

~~~java
@EventListener
void onPersonCreated(EntityCreatedEvent<Person> event) {
    // Xử lý Person
}
~~~

Do Java sử dụng type erasure, generic parameter có thể bị mất ở runtime. Nếu chỉ phát một instance của lớp generic chung mà không cung cấp thêm thông tin, Spring có thể không biết T thực tế là Person hay một kiểu khác.

Có hai cách phổ biến để giữ thông tin generic:

### Cách 1: Dùng lớp con cố định generic type

~~~java
class EntityCreatedEvent<T> extends ApplicationEvent {

    private final T entity;

    public EntityCreatedEvent(Object source, T entity) {
        super(source);
        this.entity = entity;
    }

    public T getEntity() {
        return entity;
    }
}

final class PersonCreatedEvent
        extends EntityCreatedEvent<Person> {

    public PersonCreatedEvent(Object source, Person person) {
        super(source, person);
    }
}
~~~

Lớp con PersonCreatedEvent cố định T là Person. Spring có thể phân giải kiểu generic thông qua hierarchy của lớp.

### Cách 2: Cung cấp ResolvableTypeProvider

Nếu muốn dùng trực tiếp lớp generic mà không tạo nhiều lớp con, event có thể triển khai ResolvableTypeProvider:

~~~java
public class EntityCreatedEvent<T>
        extends ApplicationEvent
        implements ResolvableTypeProvider {

    private final T entity;

    public EntityCreatedEvent(Object source, T entity) {
        super(source);
        this.entity = entity;
    }

    public T getEntity() {
        return entity;
    }

    @Override
    public ResolvableType getResolvableType() {
        return ResolvableType.forClassWithGenerics(
                getClass(),
                ResolvableType.forInstance(entity));
    }
}
~~~

Khi publish event, ResolvableTypeProvider cung cấp kiểu thực tế của payload để Spring dùng trong quá trình chọn listener.

Với payload object thông thường, PayloadApplicationEvent cũng cung cấp metadata kiểu cho payload. Tuy nhiên, nếu payload chứa generic parameter đã bị type erasure và runtime không thể suy ra, cần cung cấp metadata phù hợp thay vì giả định Spring luôn biết được kiểu phần tử.

## 7. GenericApplicationListener và lọc theo source type

ApplicationListener thông thường khai báo event type bằng generic parameter. Khi cần kiểm soát nâng cao hơn, Spring cung cấp GenericApplicationListener.

Interface này cho phép listener khai báo hai khả năng:

- supportsEventType(ResolvableType): listener có nhận event type này không?
- supportsSourceType(Class<?>): listener có nhận event được phát từ kiểu source này không?

Ví dụ minh họa:

~~~java
public final class WebOrderListener
        implements GenericApplicationListener {

    @Override
    public boolean supportsEventType(ResolvableType eventType) {
        return ResolvableType.forClass(OrderPlacedEvent.class)
                .isAssignableFrom(eventType);
    }

    @Override
    public boolean supportsSourceType(Class<?> sourceType) {
        return sourceType != null
                && WebOrderPublisher.class.isAssignableFrom(sourceType);
    }

    @Override
    public void onApplicationEvent(ApplicationEvent event) {
        OrderPlacedEvent orderEvent = (OrderPlacedEvent) event;
        System.out.println(orderEvent.getOrderId());
    }
}
~~~

Ví dụ này minh họa ý tưởng lọc hai chiều: loại event và loại source. Trong code production, cần chọn đúng chiều kiểm tra assignability theo kiểu event thực tế, và đăng ký listener với ApplicationContext hoặc multicaster.

GenericApplicationListener hữu ích khi xây dựng hạ tầng listener dùng chung, plugin hoặc cơ chế tích hợp có quy tắc lọc riêng. Với nghiệp vụ thông thường, @EventListener hoặc ApplicationListener thường dễ đọc và dễ bảo trì hơn.

## 8. Lọc runtime bằng condition

Event type matching xác định listener nào có thể nhận event theo kiểu. Đôi khi kiểu event đã phù hợp nhưng chỉ một số event instance cần kích hoạt listener.

@EventListener hỗ trợ thuộc tính condition chứa biểu thức SpEL:

~~~java
@EventListener(condition = "#a0.channel() == 'WEB'")
void notifyWebOrder(OrderPlaced event) {
    System.out.println("Notify web order");
}
~~~

Trong ví dụ, listener chỉ được gọi khi payload có channel là WEB.

SpEL context của event listener cung cấp:

- event hoặc #root.event: event gốc được publish.
- args hoặc #root.args: mảng tham số dùng để gọi listener.
- #a0 hoặc #p0: tham số đầu tiên.
- Tên tham số như #orderPlaced: có thể dùng khi tên tham số được giữ trong bytecode.

Dùng #a0 hoặc #p0 khi không chắc compiler có bật tùy chọn lưu tên tham số. Điều kiện được đánh giá khi event đến và sau khi listener đã được xác định là phù hợp về kiểu.

Không nên đặt toàn bộ logic nghiệp vụ phức tạp vào condition. Hãy giữ điều kiện ngắn, dễ đọc và chuyển xử lý chính vào phương thức listener.

## 9. Thứ tự gọi listener

Nhiều listener có thể cùng nhận một event. Nếu cần xác định thứ tự, dùng @Order:

~~~java
@EventListener
@Order(1)
void writeAudit(OrderPlaced event) {
    System.out.println("Audit");
}

@EventListener
@Order(2)
void sendNotification(OrderPlaced event) {
    System.out.println("Notification");
}
~~~

Giá trị order nhỏ hơn được ưu tiên trước. Có thể dùng Ordered hoặc @Order trên ApplicationListener tương ứng.

Chỉ dùng thứ tự khi nó có ý nghĩa thực sự. Nếu listener thứ hai bắt buộc phải chạy sau listener thứ nhất vì phụ thuộc dữ liệu hoặc kết quả, có thể hai bước đó nên nằm trong một service orchestration rõ ràng thay vì phụ thuộc ngầm vào thứ tự listener.

## 10. Event return value cũng tạo ra event mới

Một phương thức @EventListener có thể trả về một đối tượng khác không phải void:

~~~java
@EventListener
OrderAuditedEvent audit(OrderPlaced event) {
    // Ghi audit...
    return new OrderAuditedEvent(event.orderId());
}
~~~

Spring publish giá trị trả về như một event mới. Nếu phương thức trả về array hoặc Collection, mỗi phần tử được publish thành một event riêng.

Cơ chế này hữu ích cho chuỗi phản ứng ngắn, dễ hiểu. Tuy nhiên, nếu chuỗi event trở nên dài, có nhiều nhánh hoặc cần kiểm soát transaction và lỗi chặt chẽ, nên dùng service điều phối hoặc một workflow rõ ràng.

Listener bất đồng bộ không hỗ trợ việc publish event tiếp theo thông qua giá trị trả về. Khi xử lý bất đồng bộ mà cần phát event khác, hãy inject ApplicationEventPublisher và gọi publishEvent tường minh.

## 11. Đăng ký listener, thực thi và lỗi

### Cách đăng ký

Có ba cách thường gặp:

- Bean triển khai ApplicationListener<E>: Spring phát hiện listener interface khi bean được đăng ký trong context.
- Phương thức @EventListener: EventListenerMethodProcessor tạo adapter và đăng ký phương thức làm listener.
- Đăng ký bằng code: gọi addApplicationListener(...) trên ConfigurableApplicationContext hoặc ApplicationEventMulticaster khi cần quản lý listener động.

Không nên đăng ký cùng một listener nhiều lần nếu không muốn nó bị gọi lặp.

### Multicaster mặc định

Spring mặc định sử dụng SimpleApplicationEventMulticaster và gọi listener đồng bộ trong luồng publishEvent. Vì vậy, publisher đợi các listener đồng bộ hoàn tất trước khi tiếp tục.

Có thể cấu hình task executor cho multicaster hoặc dùng @Async cho một listener cụ thể. Khi chạy bất đồng bộ, exception không truyền ngược về publisher theo cách đồng bộ; cần quan sát lỗi qua cơ chế xử lý async phù hợp. ThreadLocal và logging context cũng không tự được truyền sang thread khác.

### Xử lý exception

Với thực thi đồng bộ mặc định và không cấu hình ErrorHandler, exception runtime từ listener có thể truyền ngược đến nơi publish event. Điều đó có nghĩa một listener lỗi có thể làm luồng phát event bị lỗi.

Có thể cấu hình ErrorHandler cho SimpleApplicationEventMulticaster nếu muốn thay đổi cách xử lý exception. Không nên nuốt lỗi một cách im lặng nếu việc xử lý listener là quan trọng đối với nghiệp vụ.

## 12. Ví dụ hoàn chỉnh với Java 17 và Spring Framework

Ví dụ dùng hai payload event cùng triển khai một interface OrderEvent. Một listener nhận tất cả event thuộc interface, một listener chỉ nhận OrderPlaced và chỉ xử lý đơn hàng từ kênh WEB, listener còn lại chỉ nhận OrderCancelled.

### Cấu trúc dự án

~~~text
listener-selection-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ListenerSelectionDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>listener-selection-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.ListenerSelectionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### ListenerSelectionDemo.java

~~~java
package demo;

import java.math.BigDecimal;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Configuration
@ComponentScan(basePackageClasses = ListenerSelectionDemo.class)
public class ListenerSelectionDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             ListenerSelectionDemo.class)) {

            context.publishEvent(
                    new OrderPlaced("DH-3001",
                            new BigDecimal("120000"), "WEB"));

            context.publishEvent(
                    new OrderPlaced("DH-3002",
                            new BigDecimal("80000"), "STORE"));

            context.publishEvent(
                    new OrderCancelled("DH-3003", "Customer request"));
        }
    }
}

sealed interface OrderEvent
        permits OrderPlaced, OrderCancelled {

    String orderId();
}

record OrderPlaced(
        String orderId,
        BigDecimal total,
        String channel) implements OrderEvent {
}

record OrderCancelled(
        String orderId,
        String reason) implements OrderEvent {
}

@Component
class OrderEventListeners {

    @EventListener
    @Order(1)
    void audit(OrderEvent event) {
        System.out.println(
                "Audit: " + event.getClass().getSimpleName()
                        + " " + event.orderId());
    }

    @EventListener(condition = "#a0.channel() == 'WEB'")
    @Order(2)
    void notifyWebOrder(OrderPlaced event) {
        System.out.println("Web notification: " + event.orderId());
    }

    @EventListener
    @Order(3)
    void handleCancellation(OrderCancelled event) {
        System.out.println("Cancellation follow-up: " + event.orderId());
    }
}
~~~

### Chạy chương trình

Tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java
~~~

Kết quả:

~~~text
Audit: OrderPlaced DH-3001
Web notification: DH-3001
Audit: OrderPlaced DH-3002
Audit: OrderCancelled DH-3003
Cancellation follow-up: DH-3003
~~~

### Phân tích kết quả

- OrderPlaced và OrderCancelled đều triển khai OrderEvent. Vì vậy, listener audit nhận cả hai payload.
- notifyWebOrder chỉ khai báo OrderPlaced, nên không được gọi khi publish OrderCancelled.
- Condition của notifyWebOrder chỉ đúng với payload có channel là WEB. Đơn DH-3002 từ STORE vẫn phù hợp về kiểu nhưng bị loại ở bước kiểm tra condition.
- handleCancellation chỉ nhận OrderCancelled.
- @Order(1), @Order(2), @Order(3) giúp xác định thứ tự các listener cùng phù hợp với event tương ứng.
- Publisher chỉ publish ba đối tượng. Nó không kiểm tra channel, không tự lọc listener và không gọi các phương thức xử lý.

## 13. Các lỗi thường gặp

### Nghĩ rằng mọi listener đều nhận mọi event

Listener được chọn theo kiểu event đã khai báo. Listener nhận một kiểu cụ thể sẽ bỏ qua các event không tương thích. Nếu muốn nhận nhiều loại, hãy dùng kiểu cha/interface chung có ý nghĩa hoặc khai báo classes trên @EventListener.

### Nhầm event type matching với condition

Kiểu event xác định listener có đủ điều kiện nhận event hay không. SpEL condition lọc tiếp từng event instance. Dùng condition để thay thế một kiểu event rõ ràng thường làm cấu hình khó hiểu hơn.

### Generic type không được resolve

Do type erasure, listener khai báo EntityCreatedEvent<Person> chỉ lọc chính xác khi kiểu generic của event được xác định qua lớp con hoặc ResolvableTypeProvider. Không nên dựa vào generic trong source code mà bỏ qua metadata runtime.

### Bean listener không được Spring quản lý

Một đối tượng được tạo bằng new bên ngoài ApplicationContext không tự động trở thành listener. Với @EventListener, bean phải được Spring quản lý và phương thức phải được phát hiện bởi EventListenerMethodProcessor.

### Dựa vào thứ tự listener để điều phối nghiệp vụ

@Order chỉ kiểm soát thứ tự gọi các listener phù hợp. Nó không tạo transaction chung, không bảo đảm retry và không biến nhiều listener thành một workflow có kết quả nguyên tử.

### Dùng async nhưng vẫn mong exception truyền về publisher

Listener chạy bất đồng bộ không thể truyền exception về luồng publishEvent theo cách đồng bộ. Cần cấu hình và theo dõi lỗi ở executor hoặc AsyncUncaughtExceptionHandler.

## 14. Ghi nhớ

Spring chọn listener dựa trên kiểu event được publish và kiểu mà listener khai báo. ApplicationEventMulticaster quản lý việc đăng ký, lọc và gọi listener. ApplicationListener dùng generic parameter; @EventListener suy luận kiểu từ chữ ký phương thức và có thể bổ sung classes hoặc condition.

ResolvableType giúp xử lý event generic khi thông tin kiểu được giữ lại. GenericApplicationListener cho phép lọc nâng cao theo event type và source type. @Order điều khiển thứ tự, còn @Async thay đổi cách thực thi. Hiểu rõ các bước này giúp dự đoán listener nào sẽ được gọi và tránh để logic nghiệp vụ phụ thuộc vào các quy tắc phân phối ẩn.

## Tài liệu tham khảo chính thức

- [Additional Capabilities of the ApplicationContext — Spring Framework 6.2](https://docs.spring.io/spring/reference/6.2/core/beans/context-introduction.html)
- [ApplicationEventMulticaster — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
- [GenericApplicationListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/GenericApplicationListener.html)
- [EventListener — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [ResolvableTypeProvider — Spring Framework 6.2 API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/ResolvableTypeProvider.html)
