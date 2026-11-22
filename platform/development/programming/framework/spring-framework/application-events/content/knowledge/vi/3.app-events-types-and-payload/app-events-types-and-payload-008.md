# Event chứa ID hay chứa toàn bộ trạng thái?

## 1. Bài toán thiết kế payload

Khi phát một event, publisher cần quyết định dữ liệu nào sẽ đi cùng event. Có hai lựa chọn thường gặp:

- Event chỉ mang định danh, chẳng hạn OrderCreatedEvent(String orderId). Listener nhận ID rồi tự truy vấn đơn hàng khi cần.
- Event mang snapshot dữ liệu của đối tượng tại thời điểm phát, chẳng hạn mã đơn, khách hàng, các dòng hàng, tổng tiền và trạng thái.

Giữa hai lựa chọn còn có dạng kết hợp: event mang ID để định danh tài nguyên và một số trường snapshot cần thiết để listener xử lý mà không phải truy vấn lại.

Không có một cấu trúc payload phù hợp cho mọi event. Quyết định phụ thuộc vào ý nghĩa của sự kiện, cách listener sử dụng dữ liệu, thời điểm xử lý, yêu cầu nhất quán, kích thước message, bảo mật và khả năng thay đổi hợp đồng theo thời gian.

Sau bài học, bạn có thể:
- Phân biệt event chỉ chứa ID, event chứa snapshot và event kết hợp.
- Chọn payload theo nhu cầu đọc dữ liệu của subscriber và thời điểm xử lý.
- Tránh phát JPA entity hoặc object mutable làm payload.
- Hiểu tác động của transaction, xử lý bất đồng bộ và dữ liệu thay đổi sau khi phát.
- Thiết kế event DTO bất biến, đủ dữ liệu và có khả năng phát triển hợp đồng.

## 2. Ba dạng payload phổ biến

### 2.1. Event chỉ chứa ID

Ví dụ:

~~~java
public record OrderCreatedEvent(String orderId) {
}
~~~

Publisher chỉ gửi mã đơn hàng. Listener cần chi tiết đơn hàng sẽ dùng repository hoặc một service để tải dữ liệu:

~~~java
@Component
public class OrderNotificationListener {

    private final OrderRepository orderRepository;

    public OrderNotificationListener(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        Order order = orderRepository.findById(event.orderId())
                .orElseThrow(() -> new IllegalStateException(
                        "Order not found: " + event.orderId()));

        System.out.println("Send notification for " + order.getId());
    }
}
~~~

Event ID-only phù hợp khi:
- Listener chỉ cần biết đối tượng nào đã thay đổi.
- Listener cần đọc trạng thái mới nhất tại thời điểm nó xử lý.
- Dữ liệu đầy đủ lớn, nhạy cảm hoặc không nên sao chép vào nhiều message.
- Có nhiều subscriber với nhu cầu dữ liệu khác nhau; mỗi subscriber tự lấy phần dữ liệu được phép truy cập.
- ID là hợp đồng ổn định, còn cấu trúc nội bộ của aggregate có thể thay đổi.

Đổi lại, listener phụ thuộc vào khả năng truy cập nguồn dữ liệu. Mỗi subscriber có thể tạo thêm truy vấn, tăng tải database và có thể gặp lỗi khi bản ghi đã bị xóa hoặc chưa thể đọc.

Một hệ quả quan trọng là listener có thể đọc trạng thái khác với trạng thái tại thời điểm event được phát. Ví dụ, OrderCreatedEvent được phát khi đơn hàng ở trạng thái CREATED, nhưng khi listener chạy, đơn hàng đã chuyển sang SHIPPED. Listener ID-only đọc SHIPPED vì nó đọc trạng thái hiện tại. Đây là hành vi đúng nếu yêu cầu là “hãy xử lý trạng thái hiện tại”, nhưng sai nếu listener cần biết chính xác dữ liệu tại thời điểm tạo đơn.

### 2.2. Event chứa snapshot

Snapshot là một bản dữ liệu chỉ đọc mô tả đối tượng tại một thời điểm. Ví dụ:

~~~java
public record OrderSnapshot(
        String orderId,
        String customerId,
        String status,
        BigDecimal total
) {
}

public record OrderCreatedEvent(OrderSnapshot order) {
}
~~~

Listener nhận dữ liệu trực tiếp:

~~~java
@Component
public class OrderAuditListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        OrderSnapshot order = event.order();
        System.out.println(
                "Order " + order.orderId()
                + " created with total " + order.total());
    }
}
~~~

Event snapshot phù hợp khi:
- Listener cần biết dữ liệu chính xác tại thời điểm sự kiện xảy ra.
- Subscriber cần xử lý độc lập, không muốn truy vấn ngược về service phát event.
- Công việc được xử lý bất đồng bộ hoặc chuyển qua message broker.
- Cần audit, tạo tài liệu, gửi thông báo hoặc ghi nhận dữ liệu lịch sử theo trạng thái lúc phát.
- Nguồn dữ liệu có thể thay đổi hoặc biến mất trước khi listener xử lý.

Snapshot giúp listener không phải truy vấn lại để tái tạo trạng thái lịch sử. Tuy nhiên, payload lớn hơn và có thể lặp lại dữ liệu ở nhiều event. Nếu snapshot chứa thông tin cá nhân hoặc dữ liệu nội bộ, mỗi nơi lưu message sẽ trở thành một nơi lưu dữ liệu đó. Cần giới hạn trường được phát và kiểm soát quyền truy cập, log, retention cũng như mã hóa ở các hệ thống liên quan.

Snapshot không nhất thiết phải chứa toàn bộ aggregate. Chỉ đưa vào những trường mà hợp đồng event cần công bố. Ví dụ, listener gửi email có thể chỉ cần orderId, customerEmail và tổng tiền; listener analytics có thể cần các dòng hàng và phân loại sản phẩm. Không nên phát mọi trường chỉ vì object nguồn đang có sẵn chúng.

### 2.3. Event kết hợp ID và snapshot

Một lựa chọn thực tế là mang ID cùng các trường snapshot cần thiết:

~~~java
public record OrderCreatedEvent(
        String orderId,
        String customerId,
        BigDecimal total,
        Instant occurredAt
) {
}
~~~

ID dùng để định danh và truy vấn khi cần; snapshot cung cấp một số dữ liệu ổn định tại thời điểm phát. Listener đơn giản có thể xử lý ngay bằng các trường có sẵn. Listener cần dữ liệu chi tiết hơn có thể dùng ID để truy vấn thêm.

Dạng kết hợp phù hợp khi subscriber thường cần một nhóm trường nhỏ nhưng vẫn cần khả năng tra cứu tài nguyên gốc. Hãy xác định rõ trường nào là dữ liệu snapshot và trường nào chỉ là định danh. Nếu cùng một thông tin xuất hiện hai lần, chẳng hạn orderId vừa ở event vừa ở snapshot, phải có một nguồn chuẩn hoặc kiểm tra chúng luôn nhất quán.

## 3. So sánh và cách lựa chọn

| Tiêu chí | Chỉ chứa ID | Chỉ chứa snapshot | Kết hợp ID và snapshot |
|---|---|---|---|
| Kích thước event | Nhỏ | Có thể lớn | Trung bình |
| Truy vấn bổ sung | Thường cần | Thường không cần cho dữ liệu đã mang theo | Tùy listener |
| Dữ liệu tại thời điểm phát | Không được bảo toàn nếu chỉ đọc lại hiện tại | Được bảo toàn cho các trường trong snapshot | Được bảo toàn cho các trường snapshot |
| Phụ thuộc database của publisher | Cao hơn ở phía listener | Thấp hơn cho dữ liệu đã mang theo | Trung bình |
| Phù hợp audit/lịch sử | Cần lưu hoặc tái tạo lịch sử riêng | Tốt nếu snapshot đủ trường | Tốt cho dữ liệu chọn lọc |
| Rủi ro lộ dữ liệu | Ít dữ liệu trong event | Có thể nhiều dữ liệu hơn | Cần chọn trường cẩn thận |
| Thay đổi schema | ID thường ổn định | Cần quản lý hợp đồng snapshot | Cần quản lý cả ID và snapshot |

Có thể dùng quy tắc quyết định sau:

1. Nếu listener cần trạng thái hiện tại, ID thường là đủ.
2. Nếu listener cần sự thật đúng tại thời điểm event xảy ra, hãy mang theo snapshot của các trường cần thiết.
3. Nếu một số listener cần xử lý nhanh nhưng vẫn có trường hợp cần tra cứu sâu, dùng dạng kết hợp.
4. Nếu event đi qua ranh giới service hoặc được lưu bền vững, hãy thiết kế payload như một hợp đồng tích hợp độc lập, không phụ thuộc trực tiếp vào entity nội bộ.

Trước khi chọn, hãy hỏi: “Nếu listener chạy sau vài giây, vài phút hoặc sau khi dữ liệu đã thay đổi, nó phải xử lý trạng thái mới nhất hay trạng thái tại thời điểm phát?” Câu trả lời thường quyết định phần lớn cấu trúc payload.

## 4. Phân biệt snapshot event với event sourcing

Snapshot trong payload không đồng nghĩa với event sourcing.

Trong ứng dụng thông thường, event là thông báo một sự kiện vừa xảy ra. Snapshot có thể là một phần dữ liệu được sao chép vào event để subscriber xử lý.

Trong event sourcing, các event được lưu như nguồn sự thật chính để tái dựng trạng thái aggregate. Hệ thống phải quản lý thứ tự, version, replay, tính tương thích schema và các quy tắc chuyển trạng thái. Một event Spring được publish trong bộ nhớ không tự cung cấp các bảo đảm đó.

Vì vậy, việc gửi OrderSnapshot trong OrderCreatedEvent không biến ứng dụng thành event-sourced. Ngược lại, nếu kiến trúc thực sự dùng event sourcing, cần thiết kế event store và hợp đồng event riêng thay vì xem ApplicationEventPublisher là nơi lưu lịch sử.

## 5. Đừng phát trực tiếp JPA entity hoặc object mutable

Không nên dùng JPA entity làm payload event, đặc biệt khi listener có thể chạy bất đồng bộ hoặc chạy sau khi transaction kết thúc.

Một entity có thể:
- Chứa lazy association cần persistence context để tải.
- Có proxy hoặc collection do ORM quản lý.
- Bị thay đổi sau khi event đã được phát.
- Chứa trường nội bộ không nên chia sẻ với subscriber.
- Gắn với vòng đời transaction và session.

Nếu listener chạy sau khi persistence context đóng, truy cập lazy field có thể gây LazyInitializationException. Nếu publisher tiếp tục sửa entity, listener có thể quan sát giá trị đã thay đổi thay vì dữ liệu tại thời điểm phát.

Hãy ánh xạ entity sang event DTO riêng trước khi publish. DTO chỉ nên chứa dữ liệu được công bố và nên bất biến.

Java record cung cấp tính bất biến ở mức tham chiếu của các component, nhưng không tự động tạo deep immutability. Ví dụ, record chứa List vẫn có thể tham chiếu tới một list mutable. Hãy tạo defensive copy:

~~~java
public record OrderSnapshot(
        String orderId,
        List<OrderLineSnapshot> lines
) {
    public OrderSnapshot {
        lines = List.copyOf(lines);
    }
}

public record OrderLineSnapshot(
        String sku,
        int quantity,
        BigDecimal unitPrice
) {
}
~~~

List.copyOf tạo danh sách không thể sửa thông qua tham chiếu được trả về. Các phần tử bên trong cũng cần là object bất biến hoặc được sao chép riêng nếu chúng mutable. BigDecimal, Instant, String và record chỉ chứa các trường bất biến là những lựa chọn thuận tiện cho payload.

## 6. Transaction và thời điểm đọc dữ liệu

Payload ID-only có một vấn đề thường gặp: listener truy vấn database quá sớm.

Giả sử service lưu đơn hàng trong transaction rồi phát event:

~~~java
@Transactional
public void createOrder(Order order) {
    orderRepository.save(order);
    eventPublisher.publishEvent(new OrderCreatedEvent(order.getId()));
}
~~~

Với listener @EventListener đồng bộ mặc định, listener được gọi ngay trong luồng publishEvent, khi transaction của publisher vẫn đang thực hiện. Listener có thể tham gia cùng transaction nếu dùng cùng transaction manager và tài nguyên; không nên giả định mọi truy vấn ở listener đều hoạt động như một transaction độc lập đã commit.

Nếu listener cần chạy sau khi transaction commit, dùng @TransactionalEventListener:

~~~java
@Component
public class OrderReadListener {

    private final OrderRepository orderRepository;

    public OrderReadListener(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterOrderCreated(OrderCreatedEvent event) {
        Order order = orderRepository.findById(event.orderId())
                .orElseThrow();
        System.out.println("Committed order: " + order.getId());
    }
}
~~~

Mặc định, @TransactionalEventListener dùng phase AFTER_COMMIT. Listener cần event được phát trong transaction đang hoạt động; nếu không có transaction, listener không được gọi trừ khi bật fallbackExecution = true.

Đối với snapshot, publisher có thể tạo DTO sau khi đã xác định dữ liệu nghiệp vụ cần công bố. Tuy nhiên, việc publish event trước commit vẫn có nghĩa listener đồng bộ có thể chạy trước khi transaction hoàn tất. Nếu listener thực hiện side effect bên ngoài như gửi email hoặc gọi API, rollback sau đó có thể khiến side effect không khớp với dữ liệu đã commit.

Nếu cần bảo đảm event không bị mất khi process dừng giữa commit và gửi message, hãy cân nhắc transactional outbox: ghi dữ liệu nghiệp vụ và bản ghi outbox trong cùng transaction, sau đó một publisher riêng gửi message từ outbox. Đây là vấn đề về độ bền của việc phát event; chỉ chọn ID hay snapshot không tự giải quyết được.

## 7. Bất đồng bộ và tính nhất quán theo thời gian

Khi listener chạy bất đồng bộ, khoảng thời gian giữa lúc phát event và lúc xử lý có thể dài hơn. Điều này làm khác biệt giữa ID và snapshot trở nên rõ ràng:

- Với ID-only, listener có thể đọc dữ liệu đã thay đổi, đã bị xóa hoặc không còn tồn tại.
- Với snapshot, listener vẫn có dữ liệu tại thời điểm phát, nhưng snapshot có thể cũ so với trạng thái hiện tại.
- Với payload kết hợp, listener có thể dùng snapshot để xử lý quyết định dựa trên thời điểm phát và dùng ID khi cần tra cứu trạng thái mới nhất.

Không có lựa chọn nào tự động đúng trong mọi trường hợp. Hãy đặt tên trường và mô tả hợp đồng rõ ràng, ví dụ occurredAt, orderStatusAtCreation hoặc totalAtCreation, để listener không hiểu nhầm snapshot là trạng thái hiện tại.

Nếu xử lý async, payload phải được tạo xong và không bị thay đổi sau khi gửi vào executor. Tránh truyền object mutable hoặc entity còn được sửa bởi publisher. Cần có chính sách retry, idempotency và xử lý trường hợp dữ liệu nguồn không còn tồn tại.

## 8. Bảo mật và quyền riêng tư của payload

Event payload có thể được ghi vào log, tracing, dead-letter queue, broker, file backup hoặc hệ thống phân tích. Vì vậy, thêm dữ liệu vào event đồng nghĩa với việc mở rộng phạm vi nơi dữ liệu đó có thể xuất hiện.

Trước khi đưa trường vào snapshot, hãy kiểm tra:
- Listener có thực sự cần trường đó không?
- Trường có chứa dữ liệu cá nhân, bí mật, token, thông tin thanh toán hoặc dữ liệu nội bộ không?
- Có thể gửi ID hoặc một giá trị đã được giảm thiểu/thay thế không?
- Log và hệ thống lưu message có chính sách truy cập, retention và mã hóa phù hợp không?
- Subscriber có quyền nhận toàn bộ snapshot hay chỉ một phần dữ liệu?

Không nên đưa password, access token, thông tin xác thực hoặc dữ liệu nhạy cảm không cần thiết vào event. Nếu subscriber cần dữ liệu hạn chế, hãy dùng API có kiểm soát quyền truy cập để lấy dữ liệu theo danh tính của subscriber.

## 9. Thiết kế hợp đồng event có thể phát triển

Một event có thể được nhiều listener sử dụng. Thay đổi payload vì vậy là thay đổi hợp đồng giữa publisher và subscriber.

Một số nguyên tắc hữu ích:

- Dùng tên event mô tả sự kiện đã xảy ra, chẳng hạn OrderCreatedEvent.
- Đặt tên trường theo ý nghĩa và thời điểm của dữ liệu. totalAtCreation rõ nghĩa hơn total nếu đó là giá trị snapshot.
- Thêm eventId nếu cần nhận diện duy nhất một lần phát hoặc hỗ trợ idempotency.
- Thêm occurredAt để thể hiện thời điểm sự kiện xảy ra; không nhầm với thời điểm listener nhận hoặc xử lý.
- Có thể thêm correlationId để nối các event trong cùng một quy trình.
- Với message tích hợp qua broker, cân nhắc schemaVersion và quy tắc tương thích giữa producer/consumer.
- Tránh đổi nghĩa một trường hiện có. Thêm trường tùy chọn thường dễ tương thích hơn đổi kiểu hoặc tái sử dụng tên trường với nghĩa khác.

Nếu dùng Java record nội bộ trong cùng ứng dụng, việc đổi component vẫn có thể ảnh hưởng đến mọi nơi khởi tạo record. Nếu event được serialize và lưu bền vững, còn cần quản lý tương thích dữ liệu cũ. Không nên giả định việc thêm trường vào class luôn an toàn cho message đã lưu.

## 10. Ví dụ chạy được với Java 17+ và Spring Framework 6.2.0

Ví dụ dưới đây tạo ba biến thể payload để so sánh: chỉ ID, snapshot và kết hợp. Trong ứng dụng thật, ba biến thể là các lựa chọn thiết kế thay thế nhau; ví dụ phát cả ba chỉ để quan sát cấu trúc và listener tương ứng.

### 10.1. Cấu trúc dự án

~~~text
spring-event-payload-choice/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── events/
                        └── EventPayloadDemo.java
~~~

### 10.2. Cấu hình Maven

Tệp pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-event-payload-choice</artifactId>
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

### 10.3. Tạo chương trình minh họa

Tệp src/main/java/com/example/events/EventPayloadDemo.java:

~~~java
package com.example.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

@Configuration
public class EventPayloadDemo {

    public record OrderLineSnapshot(
            String sku,
            int quantity,
            BigDecimal unitPrice
    ) {
    }

    public record OrderSnapshot(
            String orderId,
            String customerId,
            List<OrderLineSnapshot> lines,
            BigDecimal total,
            String status,
            Instant createdAt
    ) {
        public OrderSnapshot {
            lines = List.copyOf(lines);
        }
    }

    public record OrderCreatedByIdEvent(String orderId) {
    }

    public record OrderCreatedWithSnapshotEvent(OrderSnapshot order) {
    }

    public record OrderCreatedHybridEvent(
            String orderId,
            String customerId,
            BigDecimal total,
            Instant occurredAt
    ) {
    }

    public static class OrderPublisher {

        private final ApplicationEventPublisher eventPublisher;

        public OrderPublisher(ApplicationEventPublisher eventPublisher) {
            this.eventPublisher = eventPublisher;
        }

        public void publishAlternatives(OrderSnapshot order) {
            eventPublisher.publishEvent(
                    new OrderCreatedByIdEvent(order.orderId()));

            eventPublisher.publishEvent(
                    new OrderCreatedWithSnapshotEvent(order));

            eventPublisher.publishEvent(
                    new OrderCreatedHybridEvent(
                            order.orderId(),
                            order.customerId(),
                            order.total(),
                            order.createdAt()
                    ));
        }
    }

    public static class IdOnlyListener {

        @EventListener
        public void handle(OrderCreatedByIdEvent event) {
            System.out.println(
                    "ID-only listener: orderId=" + event.orderId());
        }
    }

    public static class SnapshotListener {

        @EventListener
        public void handle(OrderCreatedWithSnapshotEvent event) {
            OrderSnapshot order = event.order();
            System.out.println(
                    "Snapshot listener: orderId=" + order.orderId()
                    + ", lines=" + order.lines().size()
                    + ", total=" + order.total());
        }
    }

    public static class HybridListener {

        @EventListener
        public void handle(OrderCreatedHybridEvent event) {
            System.out.println(
                    "Hybrid listener: orderId=" + event.orderId()
                    + ", customerId=" + event.customerId()
                    + ", total=" + event.total()
                    + ", occurredAt=" + event.occurredAt());
        }
    }

    @Bean
    OrderPublisher orderPublisher(ApplicationEventPublisher publisher) {
        return new OrderPublisher(publisher);
    }

    @Bean
    IdOnlyListener idOnlyListener() {
        return new IdOnlyListener();
    }

    @Bean
    SnapshotListener snapshotListener() {
        return new SnapshotListener();
    }

    @Bean
    HybridListener hybridListener() {
        return new HybridListener();
    }

    public static void main(String[] args) {
        Instant createdAt = Instant.parse("2026-11-11T03:00:00Z");

        OrderSnapshot order = new OrderSnapshot(
                "ORD-1001",
                "CUST-7",
                List.of(
                        new OrderLineSnapshot(
                                "SKU-A", 2, new BigDecimal("25.00")),
                        new OrderLineSnapshot(
                                "SKU-B", 1, new BigDecimal("75.00"))
                ),
                new BigDecimal("125.00"),
                "CREATED",
                createdAt
        );

        try (var context =
                     new AnnotationConfigApplicationContext(
                             EventPayloadDemo.class)) {
            context.getBean(OrderPublisher.class)
                    .publishAlternatives(order);
        }
    }
}
~~~

Các record lồng trong EventPayloadDemo là kiểu static ngầm định. OrderSnapshot sao chép danh sách lines bằng List.copyOf để tránh người gọi sửa danh sách gốc sau khi tạo snapshot. Các phần tử OrderLineSnapshot cũng là record chỉ chứa String, int và BigDecimal.

### 10.4. Chạy chương trình

Từ thư mục chứa pom.xml, chạy:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=com.example.events.EventPayloadDemo
~~~

Stdout dự kiến:

~~~text
ID-only listener: orderId=ORD-1001
Snapshot listener: orderId=ORD-1001, lines=2, total=125.00
Hybrid listener: orderId=ORD-1001, customerId=CUST-7, total=125.00, occurredAt=2026-11-11T03:00:00Z
~~~

Spring dùng kiểu payload để chọn từng listener. Mỗi event có một record riêng nên listener nhận đúng dạng dữ liệu mà nó khai báo. Trong cấu hình mặc định, listener đồng bộ được gọi ngay trong từng lần publishEvent; publisher hoàn tất lần dispatch trước khi phát biến thể tiếp theo.

Chương trình cố ý phát cả ba dạng để minh họa. Khi triển khai thực tế, hãy chọn một hợp đồng phù hợp với nhu cầu của subscriber thay vì phát ba event trùng nghĩa cho cùng một thao tác.

## 11. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ gửi ID nhưng listener cần dữ liệu lịch sử | Listener đọc trạng thái mới hơn hoặc không tìm thấy bản ghi | Gửi snapshot của các trường cần bảo toàn |
| Gửi toàn bộ entity | Payload chứa lazy proxy, dữ liệu nội bộ hoặc tham chiếu mutable | Ánh xạ sang event DTO riêng |
| Snapshot chứa quá nhiều trường | Message lớn, tăng rủi ro lộ dữ liệu và khó đổi schema | Chỉ gửi trường subscriber cần |
| Gửi ID và snapshot nhưng không xác định nguồn chuẩn | Các giá trị trùng nhau có thể mâu thuẫn | Xác định trường snapshot là dữ liệu tại thời điểm nào và kiểm tra tính nhất quán |
| Listener ID-only chạy trước commit | Truy vấn có thể không thấy dữ liệu đã commit hoặc hành vi phụ thuộc transaction | Dùng AFTER_COMMIT khi cần đọc sau commit |
| Listener async nhận object mutable | Listener có thể thấy dữ liệu bị sửa sau khi publish | Dùng DTO bất biến và defensive copy |
| Dùng snapshot như trạng thái hiện tại | Subscriber xử lý dữ liệu cũ | Đặt tên trường thể hiện thời điểm và truy vấn lại nếu cần trạng thái hiện tại |
| Phát dữ liệu nhạy cảm vào mọi subscriber | Mở rộng nơi lưu trữ và người có thể truy cập dữ liệu | Data minimization, phân quyền và kiểm soát retention |

## 12. Checklist trước khi công bố event

- [ ] Xác định subscriber cần trạng thái hiện tại hay dữ liệu tại thời điểm phát.
- [ ] Chọn ID-only, snapshot hoặc hybrid theo nhu cầu thật.
- [ ] Chỉ đưa vào payload các trường có mục đích rõ ràng.
- [ ] Dùng event DTO riêng, không phát trực tiếp JPA entity.
- [ ] Sao chép collection và tránh tham chiếu mutable.
- [ ] Đặt tên trường thể hiện rõ ý nghĩa và thời điểm của dữ liệu.
- [ ] Xem xét transaction commit/rollback và cách listener đọc database.
- [ ] Xem xét dữ liệu cá nhân, bí mật, logging và retention.
- [ ] Xác định event contract có cần version, eventId hoặc correlationId.
- [ ] Kiểm thử listener với dữ liệu đã thay đổi, bản ghi bị xóa và xử lý bất đồng bộ.

## 13. Ghi nhớ

Event chỉ chứa ID giúp payload nhỏ và cho listener quyền đọc trạng thái hiện tại, nhưng listener phải truy vấn lại và có thể thấy dữ liệu đã thay đổi. Event chứa snapshot bảo toàn các trường được chọn tại thời điểm phát và giúp subscriber xử lý độc lập, nhưng làm tăng kích thước payload, phạm vi dữ liệu được chia sẻ và trách nhiệm quản lý schema. Dạng hybrid kết hợp ID với một snapshot nhỏ khi listener vừa cần dữ liệu tức thời vừa cần khả năng tra cứu.

Hãy chọn payload dựa trên thời điểm dữ liệu mà subscriber cần. Dùng DTO bất biến thay cho entity, chỉ công bố trường cần thiết và thiết kế transaction/độ bền riêng khi event phải phản ánh dữ liệu đã commit. Snapshot trong event là một hợp đồng dữ liệu; nó không tự biến ứng dụng thành event-sourced và không tự bảo đảm event được giao bền vững.
