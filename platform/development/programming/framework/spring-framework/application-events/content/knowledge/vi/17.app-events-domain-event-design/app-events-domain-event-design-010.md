# Không để domain phụ thuộc trực tiếp vào Spring khi thiết kế Domain Event

## 1. Mục tiêu: domain thuần Java, Spring ở vòng ngoài

Khi thiết kế **domain event** trong ứng dụng Spring Framework, một nguyên tắc quan trọng của Domain-Driven Design (DDD), Clean Architecture và Hexagonal Architecture là: **quy tắc nghiệp vụ và mô hình domain không được phụ thuộc trực tiếp vào cơ chế event, annotation hoặc container của Spring**.

Domain event mô tả một **sự thật nghiệp vụ đã xảy ra**: ví dụ **OrderConfirmed**, **InvoicePaid**, **AccountActivated**. Sự thật này phải giữ nguyên ý nghĩa khi ứng dụng thay Spring bằng một framework khác, chạy trong một ứng dụng CLI hoặc được kiểm thử không cần khởi động **ApplicationContext**.

Phân biệt ba việc:

1. **Domain quyết định điều gì đã xảy ra:** aggregate thực hiện hành vi hợp lệ, cập nhật trạng thái và tạo domain event.
2. **Application layer điều phối việc lưu và chuyển sự kiện:** gọi repository port, quyết định transaction boundary và yêu cầu dispatch event.
3. **Infrastructure adapter kết nối tới Spring:** thực hiện port bằng **ApplicationEventPublisher.publishEvent(Object)**, message broker hoặc transactional outbox.

**Quy tắc:** domain không import **org.springframework.***, không cần **@Component**, **@Service**, **@Autowired**, **@Transactional**, **@EventListener** hoặc **ApplicationEventPublisher**. Những công cụ đó có thể hữu ích ở application/infrastructure, nhưng không phải bản chất của nghiệp vụ.

Cách tách này không phải mục tiêu hình thức “ít annotation” mà giúp: kiểm thử domain nhanh bằng Java thuần; đổi cơ chế giao tiếp không sửa quy tắc; tránh event handler vô tình trở thành nơi quyết định bất biến nghiệp vụ; và làm rõ trách nhiệm giao dịch/lưu bền vững.

## 2. Vấn đề nếu domain gọi thẳng ApplicationEventPublisher

Thiết kế dễ gặp:

~~~java
// PHẢN VÍ DỤ: lớp domain bị gắn trực tiếp với Spring.
import org.springframework.context.ApplicationEventPublisher;

public final class Order {
    private final ApplicationEventPublisher publisher;

    public Order(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void confirm() {
        // Kiểm tra và thay đổi trạng thái nghiệp vụ...
        publisher.publishEvent(new OrderConfirmed(/* dữ liệu */));
    }
}
~~~

Đoạn trên **chỉ minh họa kiến trúc sai**, không phải chương trình độc lập. Nó tạo ra những ràng buộc:

- Aggregate **Order** không thể tạo/kiểm thử đơn giản nếu thiếu một Spring-specific dependency.
- Domain tự quyết định *cách và lúc* publish, dù chưa biết repository đã lưu thành công hoặc transaction có commit hay không.
- Một thay đổi từ Spring in-process events sang Kafka, RabbitMQ hay outbox buộc sửa domain.
- Listener có thể bị gọi khi aggregate còn ở trạng thái chưa lưu hoặc khi transaction sau đó rollback.
- Việc gọi **publishEvent(...)** bị đặt lẫn với việc duy trì invariant; dễ dẫn tới nghiệp vụ phụ thuộc side effect không rõ ràng.

Đặc biệt, **ApplicationEventPublisher** không bảo đảm “giao đến nơi” và không tự tạo transaction. Nó là cơ chế hand-off trong ứng dụng; với **SimpleApplicationEventMulticaster** mặc định, listener thường chạy đồng bộ, nhưng đó là lựa chọn hạ tầng, không phải hợp đồng của domain event.

### Một phụ thuộc khác cần tránh: domain event kế thừa ApplicationEvent

Không cần khai báo:

~~~java
// PHẢN VÍ DỤ: buộc bản thân domain event kế thừa lớp của Spring.
public final class OrderConfirmed extends ApplicationEvent {
    // ...
}
~~~

Spring Framework hỗ trợ **publishEvent(Object)** và **@EventListener** với **POJO event**. Vì vậy, có thể dùng **Java record** hoặc class thuần Java làm domain event mà không kế thừa **ApplicationEvent**. Khi publish một object không phải ApplicationEvent, Spring có thể bao nó bằng **PayloadApplicationEvent** trong cơ chế nội bộ; listener kiểu POJO vẫn nhận payload phù hợp. Không yêu cầu domain biết wrapper này.

## 3. Hướng phụ thuộc đúng

Một cấu trúc dễ kiểm soát:

~~~text
                  Spring Framework / Infrastructure
                  +-----------------------------------+
                  | SpringDomainEventAdapter         |
                  | JpaOrderRepository / Outbox      |
                  | @EventListener handlers           |
                  +------------------+----------------+
                                     |
                                     | implements ports
                                     v
                  +-----------------------------------+
                  | Application Layer                 |
                  | ConfirmOrderService               |
                  | OrderRepository (port)             |
                  | DomainEventDispatcher (port)       |
                  +------------------+----------------+
                                     |
                                     | uses
                                     v
                  +-----------------------------------+
                  | Domain Layer                      |
                  | Order aggregate                  |
                  | DomainEvent                      |
                  | OrderConfirmed record            |
                  | Invariants / domain services      |
                  +-----------------------------------+
                             (Java thuần)
~~~

Các import phải đi **từ ngoài vào trong** hoặc từ application đến domain; domain không import ngược application/infrastructure/Spring. Infrastructure được phép biết **ApplicationEventPublisher** và **@EventListener** để biến các sự kiện Java thuần thành sự kiện được dispatch trong Spring.

### Ranh giới trách nhiệm

| Thành phần | Được biết gì? | Không nên làm gì? |
| --- | --- | --- |
| **Order aggregate** | ID, trạng thái, invariant, event OrderConfirmed | Inject publisher, mở transaction, gọi network hoặc chọn broker |
| **OrderConfirmed** | Dữ liệu nghiệp vụ cần thiết và tên sự kiện | Kế thừa ApplicationEvent, chứa EntityManager hoặc Spring bean |
| **ConfirmOrderService** | Use case, repository port, dispatcher port | Nhúng chi tiết Spring multicaster vào domain |
| **DomainEventDispatcher port** | Hợp đồng công bố event | Ép mọi domain event triển khai giao diện Spring |
| **SpringDomainEventAdapter** | **ApplicationEventPublisher**, mapping/dispatch | Chứa quy tắc xác nhận đơn hàng |
| **Listener ở infrastructure/application** | Xử lý phản ứng sau event | Thay thế việc aggregate bắt buộc phải kiểm tra invariant |
| **Outbox adapter** | Bền vững, retry, serialization, publication | Làm domain phụ thuộc broker hoặc schema transport |

Có thể đặt **OrderRepository** ở domain hoặc application tùy chuẩn dự án; điều quan trọng là interface thuộc lớp bên trong còn implementation DB thuộc lớp ngoài, không có chiều import ngược.

## 4. Thiết kế event bằng Java thuần

Một domain event tốt thường:

- Có tên **quá khứ**, chỉ sự thật đã xảy ra: **OrderConfirmed**, không phải lệnh **ConfirmOrder**.
- **Bất biến (immutable)** sau khi tạo; Java **record** là lựa chọn gọn khi dữ liệu nhỏ.
- Chứa những giá trị cần cho subscriber: **aggregate ID**, ID nghiệp vụ, thời điểm/phiên bản nếu cần.
- Không chứa **ApplicationContext**, entity JPA đang được quản lý, repository, service, connection hoặc object mang lifecycle framework.
- Phân biệt **event của domain** với **integration event** gửi ra ngoài. Cùng ý nghĩa nghiệp vụ nhưng schema/retention/versioning và dữ liệu công khai có thể khác.

Ví dụ:

~~~java
package example.domain;

public interface DomainEvent {
}
~~~

~~~java
package example.domain;

import java.util.Objects;

public record OrderConfirmed(String orderId) implements DomainEvent {
    public OrderConfirmed {
        Objects.requireNonNull(orderId, "orderId");
    }
}
~~~

Hai đoạn trên là **hai file riêng**, không yêu cầu bất kỳ Spring dependency nào. **record** tự tạo constructor, accessor **orderId()**, **equals/hashCode** và **toString**. Với việc công bố event trong process, không cần ép domain implement **Serializable** chỉ vì sử dụng Spring event publisher.

Trong hệ thống có message broker, nên có một **mapping** riêng từ domain event sang message envelope có **eventId**, **aggregateId**, **occurredAt**, **schemaVersion** và **correlationId** nếu phù hợp. Cách mapping giữ domain không bị khóa vào Kafka header, JSON serialization hoặc version của external contract.

## 5. Aggregate tự ghi nhận event, không tự phát chúng

Thay vì inject publisher, aggregate lưu các sự kiện chưa dispatch trong một danh sách nội bộ. Ví dụ:

~~~java
package example.domain;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class Order {

    private final String id;
    private boolean confirmed;
    private final List<DomainEvent> pendingEvents = new ArrayList<>();

    public Order(String id) {
        this.id = Objects.requireNonNull(id, "id");
    }

    public String id() {
        return id;
    }

    public boolean isConfirmed() {
        return confirmed;
    }

    public void confirm() {
        if (confirmed) {
            throw new IllegalStateException("order already confirmed");
        }
        confirmed = true;
        pendingEvents.add(new OrderConfirmed(id));
    }

    public List<DomainEvent> drainEvents() {
        List<DomainEvent> snapshot = List.copyOf(pendingEvents);
        pendingEvents.clear();
        return snapshot;
    }
}
~~~

**Order.confirm()** bảo đảm invariant “đã xác nhận không thể xác nhận lần nữa”, cập nhật trạng thái và **ghi nhận** OrderConfirmed. Nó **không** gửi event hay phụ thuộc vào việc listener chạy thành công.

Điều này cho phép unit test:

1. Tạo **Order** bằng constructor thường.
2. Gọi **confirm()**.
3. Kiểm tra **isConfirmed()** và **drainEvents()** trả về đúng **OrderConfirmed**.
4. Gọi **confirm()** lần hai và xác nhận bị từ chối.
5. Không cần Spring Context, database hay message broker.

**Lưu ý quan trọng:** cách **drainEvents()** xóa danh sách ngay khi lấy ra chỉ an toàn cho demo in-memory, nơi các failure không cần phục hồi. Trong production, nếu save/publish thất bại sau khi drain, event có thể bị mất. Cần quy tắc xác nhận dispatch hoặc **outbox** giao dịch; domain vẫn không phải biết cơ chế đó.

## 6. Đặt port ở application layer

**DomainEventDispatcher** là interface do application sử dụng. Interface không nhắc đến Spring:

~~~java
package example.application;

import example.domain.DomainEvent;

public interface DomainEventDispatcher {
    void publish(DomainEvent event);
}
~~~

Repository cũng là port:

~~~java
package example.application;

import example.domain.Order;

public interface OrderRepository {
    Order load(String id);
    void save(Order order);
}
~~~

Use case chỉ biết các port này:

~~~java
package example.application;

import example.domain.DomainEvent;
import example.domain.Order;

public final class ConfirmOrderService {

    private final OrderRepository orders;
    private final DomainEventDispatcher dispatcher;

    public ConfirmOrderService(
            OrderRepository orders,
            DomainEventDispatcher dispatcher) {
        this.orders = orders;
        this.dispatcher = dispatcher;
    }

    public void confirm(String id) {
        Order order = orders.load(id);
        order.confirm();
        orders.save(order);

        for (DomainEvent event : order.drainEvents()) {
            dispatcher.publish(event);
        }
    }
}
~~~

**ConfirmOrderService** không có **@Service**, **@Transactional**, **ApplicationEventPublisher** hay import Spring. Nó giữ đúng trình tự ứng dụng: nạp aggregate, thực hiện nghiệp vụ, lưu aggregate, rồi yêu cầu dispatch event.

**Trình tự trong demo không phải bảo đảm atomicity.** **save()** và **publish()** có thể thành công/thất bại độc lập; khi dùng DB thật, cần transaction boundary và lựa chọn cách xử lý phù hợp với yêu cầu nhất quán. Phần dưới phân tích riêng.

### Vì sao interface do application sở hữu?

Application định nghĩa **nó cần điều gì**, ví dụ “công bố một domain event”. Infrastructure quyết định **làm bằng gì**: Spring event bus, outbox hoặc broker. Nếu interface port lại chứa **ApplicationEvent**, **ApplicationContext** hoặc kiểu của Kafka, dependency inversion chưa đạt mục tiêu.

Nếu hệ thống muốn domain hoàn toàn độc lập cả với application, đặt port ở application là cách đơn giản. Domain chỉ có event types và hành vi của nó; nó thậm chí không biết port dispatcher tồn tại.

## 7. Spring adapter: chỉ infrastructure phụ thuộc Spring

Adapter nối port với **ApplicationEventPublisher**:

~~~java
package example.infrastructure;

import example.application.DomainEventDispatcher;
import example.domain.DomainEvent;
import org.springframework.context.ApplicationEventPublisher;

public final class SpringDomainEventAdapter
        implements DomainEventDispatcher {

    private final ApplicationEventPublisher publisher;

    public SpringDomainEventAdapter(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void publish(DomainEvent event) {
        publisher.publishEvent(event);
    }
}
~~~

Handler có thể nhận thẳng **OrderConfirmed**:

~~~java
package example.infrastructure;

import example.domain.OrderConfirmed;
import org.springframework.context.event.EventListener;

public final class OrderConfirmedListener {

    @EventListener
    public void on(OrderConfirmed event) {
        System.out.println("listener: confirmed " + event.orderId());
    }
}
~~~

**@EventListener** nằm trong infrastructure, không phải domain. Spring tự tìm method khi listener là **Spring bean** đã đăng ký và listener adapter được khởi tạo.

Điều đáng chú ý: **DomainEvent** và **OrderConfirmed** là Java thuần; Spring vẫn có thể dispatch object. Không cần một event wrapper kế thừa **ApplicationEvent** trong domain.

## 8. Ví dụ hoàn chỉnh Java 17+ chạy được

Dự án Gradle này chỉ dùng **Spring Framework 6.2.9** trong composition root và infrastructure. Các package **domain** và **application** không import Spring.

Cấu trúc:

~~~text
domain-events-decoupled/
  build.gradle
  src/main/java/example/Main.java
  src/main/java/example/domain/DomainEvent.java
  src/main/java/example/domain/OrderConfirmed.java
  src/main/java/example/domain/Order.java
  src/main/java/example/application/DomainEventDispatcher.java
  src/main/java/example/application/OrderRepository.java
  src/main/java/example/application/ConfirmOrderService.java
  src/main/java/example/infrastructure/InMemoryOrderRepository.java
  src/main/java/example/infrastructure/SpringDomainEventAdapter.java
  src/main/java/example/infrastructure/OrderConfirmedListener.java
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

application {
    mainClass = 'example.Main'
}
~~~

Tạo đúng các file dưới đây.

**src/main/java/example/domain/DomainEvent.java**:

~~~java
package example.domain;

public interface DomainEvent {
}
~~~

**src/main/java/example/domain/OrderConfirmed.java**:

~~~java
package example.domain;

import java.util.Objects;

public record OrderConfirmed(String orderId) implements DomainEvent {
    public OrderConfirmed {
        Objects.requireNonNull(orderId, "orderId");
    }
}
~~~

**src/main/java/example/domain/Order.java**:

~~~java
package example.domain;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class Order {
    private final String id;
    private boolean confirmed;
    private final List<DomainEvent> pending = new ArrayList<>();

    public Order(String id) {
        this.id = Objects.requireNonNull(id, "id");
    }

    public String id() {
        return id;
    }

    public boolean isConfirmed() {
        return confirmed;
    }

    public void confirm() {
        if (confirmed) {
            throw new IllegalStateException("order already confirmed");
        }
        confirmed = true;
        pending.add(new OrderConfirmed(id));
    }

    public List<DomainEvent> drainEvents() {
        List<DomainEvent> result = List.copyOf(pending);
        pending.clear();
        return result;
    }
}
~~~

**src/main/java/example/application/DomainEventDispatcher.java**:

~~~java
package example.application;

import example.domain.DomainEvent;

public interface DomainEventDispatcher {
    void publish(DomainEvent event);
}
~~~

**src/main/java/example/application/OrderRepository.java**:

~~~java
package example.application;

import example.domain.Order;

public interface OrderRepository {
    Order load(String id);
    void save(Order order);
}
~~~

**src/main/java/example/application/ConfirmOrderService.java**:

~~~java
package example.application;

import example.domain.DomainEvent;
import example.domain.Order;

public final class ConfirmOrderService {
    private final OrderRepository orders;
    private final DomainEventDispatcher dispatcher;

    public ConfirmOrderService(
            OrderRepository orders,
            DomainEventDispatcher dispatcher) {
        this.orders = orders;
        this.dispatcher = dispatcher;
    }

    public void confirm(String id) {
        Order order = orders.load(id);
        order.confirm();
        orders.save(order);

        for (DomainEvent event : order.drainEvents()) {
            dispatcher.publish(event);
        }
    }
}
~~~

**src/main/java/example/infrastructure/InMemoryOrderRepository.java**:

~~~java
package example.infrastructure;

import java.util.HashMap;
import java.util.Map;

import example.application.OrderRepository;
import example.domain.Order;

public final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> data = new HashMap<>();

    public void seed(Order order) {
        data.put(order.id(), order);
    }

    @Override
    public Order load(String id) {
        Order result = data.get(id);
        if (result == null) {
            throw new IllegalArgumentException("order not found: " + id);
        }
        return result;
    }

    @Override
    public void save(Order order) {
        data.put(order.id(), order);
    }
}
~~~

**src/main/java/example/infrastructure/SpringDomainEventAdapter.java**:

~~~java
package example.infrastructure;

import example.application.DomainEventDispatcher;
import example.domain.DomainEvent;
import org.springframework.context.ApplicationEventPublisher;

public final class SpringDomainEventAdapter
        implements DomainEventDispatcher {

    private final ApplicationEventPublisher publisher;

    public SpringDomainEventAdapter(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void publish(DomainEvent event) {
        publisher.publishEvent(event);
    }
}
~~~

**src/main/java/example/infrastructure/OrderConfirmedListener.java**:

~~~java
package example.infrastructure;

import example.domain.OrderConfirmed;
import org.springframework.context.event.EventListener;

public final class OrderConfirmedListener {
    @EventListener
    public void on(OrderConfirmed event) {
        System.out.println("listener: confirmed " + event.orderId());
    }
}
~~~

**src/main/java/example/Main.java**:

~~~java
package example;

import example.application.ConfirmOrderService;
import example.application.DomainEventDispatcher;
import example.application.OrderRepository;
import example.domain.Order;
import example.infrastructure.InMemoryOrderRepository;
import example.infrastructure.OrderConfirmedListener;
import example.infrastructure.SpringDomainEventAdapter;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class Main {

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        OrderRepository orderRepository() {
            InMemoryOrderRepository repository = new InMemoryOrderRepository();
            repository.seed(new Order("ORD-7"));
            return repository;
        }

        @Bean
        DomainEventDispatcher domainEvents(ApplicationEventPublisher publisher) {
            return new SpringDomainEventAdapter(publisher);
        }

        @Bean
        ConfirmOrderService confirmOrderService(
                OrderRepository repository,
                DomainEventDispatcher events) {
            return new ConfirmOrderService(repository, events);
        }

        @Bean
        OrderConfirmedListener confirmedListener() {
            return new OrderConfirmedListener();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            var service = context.getBean(ConfirmOrderService.class);
            System.out.println("caller: begin");
            service.confirm("ORD-7");
            System.out.println("caller: end");
        }
    }
}
~~~

Tại thư mục **domain-events-decoupled**, với **JDK 17+** và **Gradle 8.x** đã cài:

~~~bash
gradle --console=plain -q run
~~~

**Stdout do chương trình tự in ra**:

~~~text
caller: begin
listener: confirmed ORD-7
caller: end
~~~

**Vì sao có thứ tự đó?**

- **caller: begin** được in trước khi application service chạy.
- Aggregate ghi nhận **OrderConfirmed** trong danh sách pending; nó không biết Spring.
- Service lưu aggregate vào **InMemoryOrderRepository**, lấy event và gọi **DomainEventDispatcher**.
- **SpringDomainEventAdapter** gọi **ApplicationEventPublisher.publishEvent(event)**.
- **SimpleApplicationEventMulticaster** của context với cấu hình mặc định dispatch listener đồng bộ; **OrderConfirmedListener** in **listener: confirmed ORD-7**.
- Khi **publishEvent(...)** trả về, service tiếp tục và main in **caller: end**.

**Cảnh báo độ tin cậy của demo:** repository in-memory giữ cùng object, không có transaction hoặc tính bền vững. Nếu listener ném exception, state trong memory đã đổi; event đã bị drain. Demo chỉ chứng minh **hướng phụ thuộc và cơ chế POJO event**, không phải mẫu delivery đúng cho hệ thống sản xuất.

### Kiểm chứng domain có thể biên dịch không cần Spring

Dù toàn dự án dùng Spring Framework, ba file domain có thể được **javac** biên dịch riêng. Ví dụ từ thư mục gốc dự án:

~~~bash
javac -encoding UTF-8 -d domain-classes \
  src/main/java/example/domain/DomainEvent.java \
  src/main/java/example/domain/OrderConfirmed.java \
  src/main/java/example/domain/Order.java
~~~

Đây là cú pháp shell dùng ký tự nối dòng **\**; trên **PowerShell** hãy viết cùng lệnh trên **một dòng**:

~~~powershell
javac -encoding UTF-8 -d domain-classes src/main/java/example/domain/DomainEvent.java src/main/java/example/domain/OrderConfirmed.java src/main/java/example/domain/Order.java
~~~

Không có **spring-context.jar** trong classpath của lệnh javac; domain vẫn biên dịch vì chỉ import JDK. Đây là cách kiểm chứng cụ thể rằng lớp domain không phụ thuộc Spring ở cấp biên dịch.

## 9. Transaction: domain không phụ thuộc Spring vẫn cần tính nhất quán

Tách domain khỏi Spring **không tự giải quyết** vấn đề save–publish. Phải xác định ý nghĩa của event và yêu cầu hoàn tất.

### 9.1. @EventListener thông thường có thể chạy trước DB commit

Nếu một application service production được bọc trong **@Transactional**, một lời gọi **publishEvent(event)** ở giữa method sẽ xảy ra **khi transaction vẫn đang hoạt động**. Với multicaster đồng bộ mặc định, **@EventListener** có thể chạy ngay trong call stack đó. Listener đọc dữ liệu từ transaction khác có thể **chưa nhìn thấy** state mới; nếu giao dịch chính rollback sau đó, side effect như email đã gửi không thể tự thu hồi.

Ví dụ quy trình có rủi ro:

~~~text
BEGIN TX
  -> Order.confirm()
  -> orderRepository.save(order)
  -> publishEvent(OrderConfirmed)
       -> listener gửi email NGAY
  -> lỗi khác, ROLLBACK DB
Kết quả: email đã gửi, nhưng đơn chưa commit xác nhận.
~~~

Đây không phải lỗi do record domain; lỗi là **chọn thời điểm side effect trong hạ tầng**.

### 9.2. @TransactionalEventListener(AFTER_COMMIT) thuộc adapter/handler

Nếu một phản ứng chỉ được chạy sau khi transaction commit thành công, Spring infrastructure có thể dùng:

~~~java
package example.infrastructure;

import example.domain.OrderConfirmed;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.event.TransactionPhase;

@Component
public final class ConfirmationNotificationHandler {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderConfirmed event) {
        // Chỉ thực hiện phản ứng sau khi transaction commit thành công.
        // Thao tác mạng nên có timeout, retry và idempotency phù hợp.
    }
}
~~~

**Đây là đoạn minh họa cho ứng dụng có transaction manager**, không thuộc chương trình in-memory mục 8. Nó yêu cầu Spring-managed bean và một transaction thực sự đang hoạt động khi event được publish. Mặc định transactional listener **không chạy** nếu không có transaction phù hợp (**fallbackExecution=false**).

**Quan trọng:** AFTER_COMMIT không thể rollback commit đã hoàn tất. Nếu handler cần ghi một record DB mới, thường cần transaction mới (**REQUIRES_NEW**) ở service được Spring quản lý, không tưởng rằng transaction cũ vẫn commit thêm thay đổi. Lời gọi tới HTTP/email hay broker vẫn không tự trở thành atomic với database.

### 9.3. Khi yêu cầu không được mất event: transactional outbox

Nếu **OrderConfirmed** phải được chuyển sang hệ thống khác dù tiến trình chết, một callback AFTER_COMMIT trong memory vẫn chưa đủ. Kịch bản:

~~~text
BEGIN TX
  -> save(order)
  -> ghi OutboxMessage cho OrderConfirmed
COMMIT DB
       |
       +--> worker lấy outbox row
             -> publish Kafka/RabbitMQ/HTTP
             -> retry khi lỗi
             -> đánh dấu đã gửi
~~~

**Outbox record** được ghi trong **cùng DB transaction** với thay đổi aggregate. Domain vẫn chỉ tạo event thuần Java; application/infrastructure map event sang outbox message. Worker xử lý retry và idempotency.

Nếu đã commit nhưng worker chết, outbox vẫn còn. Nếu worker gửi được rồi chết trước khi đánh dấu sent, sự kiện có thể bị gửi lặp; consumer cần **idempotent handling** dựa trên event/message ID. Outbox thường cung cấp điều kiện để đạt **at-least-once delivery**, không mặc nhiên exactly-once toàn hệ thống.

### 9.4. Ba phương án dispatch và trade-off

| Kiểu dispatch | Khi phù hợp | Giới hạn |
| --- | --- | --- |
| **@EventListener** đồng bộ tại publish | Phản ứng cục bộ, nhanh, cần trả lỗi ngay, transaction được hiểu rõ | Chạy trước commit nếu publish trong transaction; caller bị block |
| **@TransactionalEventListener(AFTER_COMMIT)** | Phản ứng chỉ có ý nghĩa khi DB commit thành công, không đòi hỏi bảo đảm tuyệt đối trước crash | Callback nằm trong bộ nhớ; không tự retry/durable; nếu event không được publish trong transaction thì listener mặc định bỏ qua |
| **Transactional outbox + worker/queue** | Công việc phải được lưu bền vững và hoàn thành về sau | Cần schema, relay/worker, retry, idempotency, monitoring |

Không dùng quy tắc “domain event nào cũng phải bất đồng bộ”. **Sự kiện** là mô hình hóa sự thật; **đồng bộ/bất đồng bộ/bền vững** là lựa chọn ở vòng ngoài tùy hợp đồng nghiệp vụ.

## 10. Phân biệt domain event, application event và integration event

Ba từ này liên quan nhưng không đồng nghĩa:

**Domain event:** diễn đạt sự thật quan trọng bên trong bounded context; do domain tạo; ví dụ **OrderConfirmed(orderId)**. Nó không cần biết truyền đi bằng Spring hay message broker.

**Spring application event:** cơ chế gửi/nhận object nội bộ trong một ApplicationContext thông qua **ApplicationEventPublisher**. Một domain event Java thuần *có thể* được dùng làm payload của cơ chế này. Không phải mọi Spring event đều là domain event: **ContextRefreshedEvent**, **ContextClosedEvent** là sự kiện vòng đời framework.

**Integration event:** hợp đồng giao tiếp giữa bounded contexts, services hoặc hệ thống bên ngoài. Thường yêu cầu schema version, event ID, timestamp, correlation, serialization, khả năng mở rộng và quy tắc tương thích. Không nên mặc định export nguyên object domain qua wire.

Ví dụ mapping khi xuất qua broker:

~~~text
Domain:
  OrderConfirmed(orderId = "ORD-7")

Infrastructure mapping:
  type          = "order.confirmed.v1"
  eventId       = <mã duy nhất do adapter tạo>
  aggregateId   = "ORD-7"
  schemaVersion = 1
  payload       = {"orderId":"ORD-7"}
  occurredAt    = <thời điểm domain/application xác nhận phù hợp>
~~~

Đây là **mô tả cấu trúc**, không phải JSON schema phải giữ nguyên. Adapter có thể tạo **eventId** khi ghi outbox và gắn metadata cần thiết theo hợp đồng. Tránh publish trực tiếp toàn bộ entity với password, thông tin nhạy cảm hoặc lazy-loaded associations.

## 11. Kiểm thử không cần Spring: lợi ích thực sự

Với domain thuần Java, kiểm thử logic bất biến không cần startup container:

~~~java
// Đoạn minh họa trong một JUnit 5 test class;
// cần import @Test, assertions và các domain types.
@Test
void confirmRecordsOneDomainEvent() {
    Order order = new Order("ORD-7");

    order.confirm();

    assertTrue(order.isConfirmed());
    assertEquals(
            List.of(new OrderConfirmed("ORD-7")),
            order.drainEvents());
    assertTrue(order.drainEvents().isEmpty());
    assertThrows(IllegalStateException.class, order::confirm);
}
~~~

Test này xác nhận: state đã đổi, event được ghi nhận đúng một lần, drain xóa pending list, xác nhận lần hai bị từ chối. Nó **không cần Spring container** và không test **ApplicationEventPublisher**. Vì là snippet JUnit 5, cần thêm dependency test và class khi tích hợp vào dự án thật; chương trình độc lập mục 8 vẫn chạy không cần JUnit.

### Fake publisher để kiểm thử application service

Để kiểm thử tầng application, dùng implementation của port:

~~~java
final class RecordingDispatcher implements DomainEventDispatcher {
    private final List<DomainEvent> recorded = new ArrayList<>();

    @Override
    public void publish(DomainEvent event) {
        recorded.add(event);
    }

    public List<DomainEvent> events() {
        return List.copyOf(recorded);
    }
}
~~~

Đây là **đoạn minh họa** cần đặt trong class test với import **DomainEvent**, **DomainEventDispatcher**, **List**, **ArrayList**. Không cần mock **ApplicationEventPublisher** trong mỗi unit test nghiệp vụ; chỉ test mapping adapter với Spring ở một số integration test riêng.

### Integration test cho Spring adapter

Tạo **AnnotationConfigApplicationContext**, đăng ký bean của adapter và **@EventListener**, gọi use case rồi xác nhận listener nhận **OrderConfirmed**. Đây là phạm vi test khác với unit test domain.

Nếu dùng **@TransactionalEventListener(AFTER_COMMIT)**, test cần transaction manager thật hoặc tương đương phù hợp, kiểm tra commit/rollback và publication context; gọi trực tiếp listener method không chứng minh Spring đã điều phối phase.

## 12. Kiểm tra kiến trúc ở build/CI

Tách package là điều kiện cần nhưng không đủ. Domain vẫn có thể vô tình import Spring nếu team không có kiểm tra.

Các cách bảo vệ:

1. **Module độc lập:** đặt **domain** thành Java/Gradle module không khai báo bất kỳ Spring dependency nào. Nếu domain cố import **org.springframework.***, compile sẽ fail.
2. **Quy tắc kiến trúc:** dùng ArchUnit hoặc static check ở CI để kiểm tra package **..domain..** không phụ thuộc **org.springframework..**, **..infrastructure..** hay công cụ transport.
3. **Dependency review:** tránh “dependency thông qua utility chung” từ domain ngược ra infrastructure.
4. **Test thuần Java:** unit tests của aggregate phải chạy mà không tạo **ApplicationContext**.
5. **API review:** event types không chứa trực tiếp **ApplicationEvent**, **Message<?>**, **KafkaTemplate**, **EntityManager**, HTTP request hoặc container types.

Ví dụ quy tắc ArchUnit **minh họa**, không phải file runnable độc lập:

~~~java
noClasses()
    .that().resideInAPackage("..domain..")
    .should().dependOnClassesThat()
    .resideInAnyPackage("org.springframework..", "..infrastructure..");
~~~

Để dùng trong dự án, cần dependency ArchUnit và import API tương ứng; snippet chỉ diễn đạt ý nghĩa rule. Với kiến trúc nghiêm ngặt, tách module vật lý tạo bảo đảm compile-time mạnh hơn kiểm tra bằng code review.

**Lưu ý về Spring Data @DomainEvents:** Spring Data có annotation **@DomainEvents** và **@AfterDomainEventPublication** để publication thuận tiện từ aggregate repository. Tuy nhiên đặt annotation Spring Data trực tiếp trong aggregate đồng nghĩa **domain phụ thuộc framework**. Nếu mục tiêu là domain thuần Java nghiêm ngặt, dùng pending-events thông thường và adapter/application port, hoặc đưa việc lấy event vào repository adapter mà không import Spring vào domain. Chấp nhận coupling này có thể là quyết định có chủ ý của một codebase thực dụng, nhưng không được gọi là domain hoàn toàn độc lập Spring.

## 13. Lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Domain entity inject **ApplicationEventPublisher** | Domain lệ thuộc Spring và thời điểm dispatch | Aggregate ghi nhận event; application/adapter publish |
| Domain event **extends ApplicationEvent** | Event không còn thuần Java | Dùng class/record POJO, publish qua **publishEvent(Object)** |
| Đánh **@EventListener** trực tiếp lên class domain | Domain gắn với container, khó unit test | Listener ở application/infrastructure |
| Dùng event để né invariant của aggregate | Trạng thái có thể sai nếu listener không chạy | Invariant phải được kiểm tra trong domain/use case bắt buộc |
| Domain gọi Kafka/HTTP trong **confirm()** | Side effect xảy ra trước commit, khó retry | Mapping/integration tại adapter và dùng outbox khi cần |
| Publish trước DB commit rồi gửi email ngay | Email phản ánh giao dịch có thể rollback | **AFTER_COMMIT** hoặc outbox |
| Chỉ dùng **@Async** để “bảo đảm eventually” | Có thể mất task khi JVM chết | Persistent queue/outbox + retry + idempotency |
| Drain pending events trước khi save thành công | Event bị mất nếu save lỗi | Transaction/unit of work hoặc outbox có xử lý failure |
| Publish cùng event ở nhiều nơi | Listener xử lý lặp, metric sai | Chọn owner publication, idempotency/event ID khi cần |
| Đưa JPA entity/proxy vào event | Lazy loading, transaction leak, dữ liệu nhạy cảm | Snapshot dữ liệu cần thiết và ID thuần Java |
| Dùng chung event domain làm contract public vĩnh viễn | Thay domain phá schema khách hàng | Mapping sang integration event có version |
| Tách package nhưng module domain vẫn phụ thuộc Spring | Coupling vẫn tồn tại | Kiểm tra dependency bằng module/CI |
| Unit test domain luôn cần @SpringBootTest | Test chậm, domain khó tái sử dụng | Dùng unit test thuần Java; integration test riêng cho adapter |

## 14. Checklist khi triển khai domain event độc lập framework

Trước khi merge, hãy xác nhận:

- **Event có mô tả sự thật đã xảy ra?** Tên quá khứ, dữ liệu cần thiết, không phải command trá hình.
- **Domain chỉ import Java/contract nội bộ phù hợp?** Không chứa Spring annotations, ApplicationEventPublisher hoặc các loại transport.
- **Aggregate tự giữ invariant?** Nếu một listener không chạy, quy tắc cốt lõi vẫn đúng.
- **Application service sử dụng port?** Dependency hướng vào domain, implementation ở infrastructure.
- **Spring adapter nhận POJO event?** **@EventListener** nằm trên bean ở lớp ngoài.
- **Biết event được publish trước hay sau commit?** Không mặc định **publishEvent(...)** đồng nghĩa commit.
- **Nếu event không được mất thì có outbox/retry/idempotency?** Không dùng in-memory callback làm durable queue.
- **Event schema cho external consumers có được version riêng?** Không xuất thẳng object domain nếu không có hợp đồng tương thích.
- **Unit test domain không khởi động Spring?** Có integration test riêng cho adapter/transaction?
- **CI có chặn phụ thuộc ngược?** Có module boundary hoặc rule ArchUnit phù hợp?

**Kết luận:** Thiết kế domain event tốt giữ **sự thật nghiệp vụ trong domain** và **cơ chế công bố ở vòng ngoài**. Spring Framework hoàn toàn có thể dispatch **POJO event**, vì vậy không cần cho domain kế thừa **ApplicationEvent** hay inject **ApplicationEventPublisher**. Với kiến trúc này, bạn có thể đổi adapter từ in-process events sang outbox/message broker mà vẫn giữ nguyên quy tắc nghiệp vụ và bộ unit test domain.

### Tài liệu chính thức

- Spring Framework Reference — *Application Events*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Javadoc — *ApplicationEventPublisher.publishEvent(Object)*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Data Commons Reference — *Publishing Events from Aggregate Roots*: https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html
