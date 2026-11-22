# Tên event theo quá khứ trong thiết kế domain event với Spring Application Events

## 1. Một domain event phải kể lại điều gì?

Trong thiết kế hướng domain (DDD), **domain event** là lời khẳng định rằng **một sự thật nghiệp vụ đáng quan tâm đã xảy ra**. Vì vậy tên event thường dùng **dạng quá khứ**:

- `OrderPlaced`: đơn hàng đã được đặt.
- `PaymentAuthorized`: một khoản thanh toán đã được cho phép.
- `PaymentCaptured`: khoản tiền đã được thu/capture.
- `InventoryReserved`: lượng hàng đã được giữ.
- `InvoiceIssued`: hóa đơn đã được phát hành.
- `OrderCancelled`: đơn đã bị hủy.
- `SubscriptionExpired`: thuê bao đã hết hạn.

Cách đặt tên này giúp producer và consumer cùng hiểu: producer không **ra lệnh** cho consumer; producer công bố một **fact** mà consumer có thể phản ứng theo nhu cầu của mình. Một sự kiện không nên có tên như `SendEmail` chỉ vì có một listener dùng nó để gửi email. Tên đúng phải mô tả chuyện **đã xảy ra trong domain**, ví dụ `OrderPlaced`; gửi email là một phản ứng tùy consumer.

~~~text
Khách hàng         Application use case       Domain/Repository        Listeners
    |                     |                           |                    |
    | PlaceOrder command  |                           |                    |
    +-------------------->| validate                  |                    |
    |                     +-------------------------->| thay đổi trạng thái |
    |                     |<--------------------------+                    |
    |                     | publish(OrderPlaced)                           |
    |                     +----------------------------------------------->|
    |                     |                       ghi audit / cập nhật UI  |
~~~

**Quy tắc cốt lõi:** đặt tên event bằng ngôn ngữ nghiệp vụ ở quá khứ, phát khi sự thật đó thực sự được xác lập theo quy tắc domain; không phát event kết quả thành công chỉ vì mới tiếp nhận một yêu cầu.

## 2. Phân biệt command, event, query

| Loại | Thông điệp có nghĩa là gì? | Cách đặt tên | Ví dụ |
| --- | --- | --- | --- |
| **Command** | “Hãy làm điều này”; có thể được chấp nhận hoặc từ chối | Động từ hành động + đối tượng | `PlaceOrder`, `CancelOrder`, `CapturePayment` |
| **Domain event** | “Điều này đã xảy ra”; ghi nhận sự thật nghiệp vụ | Đối tượng + động từ quá khứ | `OrderPlaced`, `OrderCancelled`, `PaymentCaptured` |
| **Query** | “Hãy đọc/tra cứu dữ liệu” | Động từ đọc + đối tượng | `GetOrder`, `FindCustomerOrders` |

Ví dụ `PlaceOrder` là yêu cầu đặt đơn. Use case còn phải kiểm tra địa chỉ, giá, số lượng, trạng thái khách hàng… `OrderPlaced` chỉ nên xuất hiện khi hệ thống **đã chấp nhận việc đặt đơn**.

Một yêu cầu thất bại **không tự tạo event thành công**. Tuy nhiên, một sự thật thất bại cũng có thể là domain event nếu domain cần lưu/quan sát nó:

- `OrderRejected`: việc từ chối đơn **đã xảy ra** theo quyết định nghiệp vụ.
- `PaymentDeclined`: tổ chức thanh toán **đã từ chối** giao dịch.
- `InventoryReservationFailed`: việc giữ hàng **đã thất bại** theo hợp đồng domain (nếu được mô hình hóa như một fact).

Tránh biến mọi `RuntimeException` kỹ thuật thành `OrderRejected`. Timeout DB không mặc nhiên là một quyết định nghiệp vụ từ chối đơn.

### “Requested” cũng có thể là quá khứ

`RefundRequested` mô tả sự thật “yêu cầu hoàn tiền đã được ghi nhận”, khác với command `RequestRefund` và khác với `PaymentRefunded` (“tiền đã hoàn”). Vì vậy nguyên tắc quan trọng hơn việc gắn hậu tố `-ed` là **chính xác điều nào đã xảy ra**.

## 3. Công thức và quy ước ngôn ngữ

Quy ước phổ biến với Java:

~~~text
<Domain Noun><Past Participle / Past Verb>

Order         + Placed     -> OrderPlaced
Payment       + Captured   -> PaymentCaptured
Invoice       + Issued     -> InvoiceIssued
CustomerEmail + Changed    -> CustomerEmailChanged
Shipment      + Dispatched -> ShipmentDispatched
Subscription  + Expired    -> SubscriptionExpired
~~~

Sử dụng **PascalCase** cho tên lớp/record, tên trường theo `camelCase`. Chọn từ ngữ tự nhiên: không phải động từ nào cũng thêm `-ed` (ví dụ `Sent`, `Paid`, `Sold`). Nên ưu tiên tên **ngắn, rõ đối tượng và có nghĩa nghiệp vụ**.

Hai kiểu tên sau đều có thể dùng:

~~~java
public record OrderPlaced(long orderId) { }
public record OrderPlacedEvent(long orderId) { }
~~~

`OrderPlaced` ngắn và đọc như một fact. `OrderPlacedEvent` ghi rõ loại ở những dự án thích hậu tố `Event`. Chọn **một quy ước nhất quán** trong module hoặc bounded context; việc lúc thêm, lúc bỏ hậu tố không phải lỗi runtime của Spring nhưng làm code khó đọc và khó tìm kiếm.

Không nên đặt tên quá dài như `OrderWasSuccessfullyPlacedByCustomerEvent` khi `OrderPlaced` đã đủ. Ngược lại, `DataChanged` quá chung. Người đọc cần biết **aggregate hoặc khái niệm domain nào thay đổi**, và **chuyển trạng thái cụ thể là gì**.

## 4. Quá khứ đúng ngữ pháp chưa đủ: phải đúng mốc nghiệp vụ

Một domain có thể có nhiều bước:

~~~text
OrderDraftCreated
       |
       v
OrderPlaced
       |
       +--> OrderRejected (tùy mô hình)
       |
       v
OrderConfirmed
       |
       v
PaymentCaptured
       |
       v
OrderShipped
       |
       v
OrderDelivered
~~~

Sơ đồ chỉ là **ví dụ trạng thái**, không phải quy trình bắt buộc cho mọi doanh nghiệp. Các event sau có ý nghĩa khác nhau:

| Event | Hợp đồng cần đúng |
| --- | --- |
| `OrderCreated` | Đơn/record đã được tạo; có thể còn là draft |
| `OrderPlaced` | Hệ thống đã chấp nhận hành động đặt đơn |
| `OrderConfirmed` | Đơn đã được xác nhận theo quy tắc nghiệp vụ |
| `PaymentAuthorized` | Cổng thanh toán đã cho phép giao dịch, chưa nhất thiết thu tiền |
| `PaymentCaptured` | Capture/thu tiền đã thành công |
| `OrderPaid` | Domain đơn hàng đã ghi nhận đơn đạt trạng thái “paid” |
| `InventoryReserved` | Hàng đã được giữ trước |
| `OrderShipped` | Đơn đã được giao cho bước vận chuyển theo định nghĩa hệ thống |
| `PaymentRefunded` | Giao dịch hoàn tiền đã thực sự hoàn tất |

Không xem `PaymentAuthorized` và `PaymentCaptured` là đồng nghĩa. Cũng không thay `OrderPlaced` bằng `OrderCreated` chỉ vì ứng dụng gọi `repository.save(...)`. Tên nên bắt nguồn từ **ubiquitous language** của chuyên gia nghiệp vụ chứ không phải API kỹ thuật.

Nếu một fact có thể bị đảo ngược về sau, fact đó vẫn là lịch sử. Ví dụ `PaymentCaptured` có thể được theo sau bởi `PaymentRefunded`, chứ không cần xóa bỏ event capture đã xảy ra.

## 5. Đặt sự kiện ở đúng điểm của use case

Quy trình hợp lý:

1. Nhận command, ví dụ `PlaceOrder`.
2. Kiểm tra cú pháp và điều kiện nghiệp vụ.
3. Yêu cầu aggregate thực hiện chuyển trạng thái hợp lệ.
4. Ghi nhận kết quả theo chính sách persistence/transaction.
5. Công bố domain event `OrderPlaced` theo thời điểm phù hợp.
6. Các listener thực hiện hành vi bổ sung như audit, projection, gửi thông báo.

Phản ví dụ (mã phác thảo, các service/type phải có trong dự án):

~~~java
// SAI: event khẳng định "đã đặt" trước khi kiểm tra và lưu đơn.
public void placeOrder(PlaceOrder command) {
    publisher.publishEvent(new OrderPlaced(command.orderId()));
    Order order = domainService.validateAndPlace(command);
    orderRepository.save(order);
}
~~~

Nếu validation/repository thất bại, listener đã có thể nhận `OrderPlaced` dù nghiệp vụ chưa hoàn tất. Tên **đã đặt** trở nên sai.

Viết tốt hơn ở cấp luồng xử lý:

~~~java
// MINH HỌA: xác lập trạng thái hợp lệ rồi mới publish.
public void placeOrder(PlaceOrder command) {
    Order order = domainService.validateAndPlace(command);
    orderRepository.save(order);
    publisher.publishEvent(new OrderPlaced(order.getId()));
}
~~~

Ở đây vẫn cần phân biệt **lúc event được publish** và **lúc transaction đã commit** (phần 8). Đổi thứ tự `save`/`publish` có ý nghĩa đối với trạng thái domain, nhưng không tự biến mọi side effect của listener thành giao dịch nguyên tử.

## 6. Ví dụ Java 17+: Command PlaceOrder và event OrderPlaced

Ví dụ chạy với **Spring Framework 6.2.8**, JDK 17+, không cần Spring Boot. Để tập trung vào naming và lifecycle của event, ví dụ dùng **kho dữ liệu trong bộ nhớ**, không kết nối DB.

Mục tiêu: khi command hợp lệ, service lưu trạng thái rồi publish `OrderPlaced`; listener nhận fact và ghi log. Khi command bị từ chối vì tổng âm, **không** có event thành công.

### 6.1. Cấu trúc thư mục

~~~text
domain-event-naming/
├── pom.xml
└── src/main/java/DomainEventNamingDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>domain-event-naming</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>DomainEventNamingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. DomainEventNamingDemo.java

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class DomainEventNamingDemo {

    // Command: yêu cầu hành động, có thể bị từ chối.
    public record PlaceOrder(long orderId, long totalVnd) { }

    // Domain event: fact "đơn đã được đặt".
    public record OrderPlaced(long orderId, long totalVnd) { }

    public static final class InMemoryOrders {
        private final Map<Long, Long> totals = new ConcurrentHashMap<>();

        public boolean insertNew(long orderId, long totalVnd) {
            return totals.putIfAbsent(orderId, totalVnd) == null;
        }

        public int size() {
            return totals.size();
        }
    }

    public static final class OrderService {
        private final InMemoryOrders store;
        private final ApplicationEventPublisher publisher;

        public OrderService(
                InMemoryOrders store,
                ApplicationEventPublisher publisher
        ) {
            this.store = store;
            this.publisher = publisher;
        }

        public void handle(PlaceOrder command) {
            if (command.orderId() <= 0 || command.totalVnd() < 0) {
                throw new IllegalArgumentException("Invalid order");
            }
            if (!store.insertNew(
                    command.orderId(), command.totalVnd())) {
                throw new IllegalStateException("Duplicate order");
            }

            System.out.println(
                "STATE_CHANGED order=" + command.orderId()
            );

            // Đã chuyển trạng thái; giờ công bố fact.
            publisher.publishEvent(
                new OrderPlaced(command.orderId(), command.totalVnd())
            );
        }
    }

    public static final class AuditListener {
        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println(
                "EVENT OrderPlaced order=" + event.orderId()
                + " totalVnd=" + event.totalVnd()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        InMemoryOrders inMemoryOrders() {
            return new InMemoryOrders();
        }

        @Bean
        OrderService orderService(
                InMemoryOrders store,
                ApplicationEventPublisher publisher
        ) {
            return new OrderService(store, publisher);
        }

        @Bean
        AuditListener auditListener() {
            return new AuditListener();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            OrderService service = context.getBean(OrderService.class);
            InMemoryOrders store = context.getBean(InMemoryOrders.class);

            service.handle(new PlaceOrder(101, 230_000));

            try {
                service.handle(new PlaceOrder(102, -10));
            } catch (IllegalArgumentException ex) {
                System.out.println("REJECTED negative total");
            }

            System.out.println("TOTAL_ORDERS=" + store.size());
        }
    }
}
~~~

Chạy từ thư mục `domain-event-naming`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng `stdout` chương trình in ra, bỏ qua thông báo phụ của Maven:

~~~text
STATE_CHANGED order=101
EVENT OrderPlaced order=101 totalVnd=230000
REJECTED negative total
TOTAL_ORDERS=1
~~~

### 6.4. Vì sao kết quả như vậy?

- `PlaceOrder(101, 230_000)` là **command**. Service kiểm tra input, lưu trạng thái và in `STATE_CHANGED`.
- Sau khi trạng thái được chấp nhận, `publisher.publishEvent(new OrderPlaced(...))` công bố **fact**. `AuditListener` có phương thức `@EventListener` với tham số `OrderPlaced` nên Spring gọi nó.
- Cấu hình `SimpleApplicationEventMulticaster` mặc định xử lý listener thông thường **đồng bộ trên luồng publisher**, nên log của listener xuất hiện trước khi `handle` trở về.
- `PlaceOrder(102, -10)` bị validation từ chối trước khi insert; không có dòng `EVENT OrderPlaced` cho order 102.
- `TOTAL_ORDERS=1` cho thấy chỉ command hợp lệ làm tăng số đơn.

**Giới hạn cố ý của ví dụ:** `ConcurrentHashMap` không phải cơ sở dữ liệu có transaction. Nếu listener ném lỗi sau `insertNew`, thay đổi map không tự rollback. Ví dụ minh họa **đặt tên, sự thật nghiệp vụ, thứ tự phát event**, không chứng minh giao dịch nguyên tử hay durability.

## 7. Spring nhận event bằng kiểu, không phải kiểm tra thì ngữ pháp

Spring Framework từ phiên bản 4.2 cho phép phát **POJO/record** qua `ApplicationEventPublisher.publishEvent(Object)`. `OrderPlaced` không bắt buộc extends `ApplicationEvent`:

~~~java
public record OrderPlaced(long orderId) { }

@EventListener
public void onOrderPlaced(OrderPlaced event) {
    // Xử lý event đúng kiểu OrderPlaced.
}
~~~

Đây là mã minh họa đặt trong các lớp/bean thích hợp. Trong ứng dụng thực, bean chứa listener phải được Spring quản lý; tên method có thể là `onOrderPlaced` hoặc `handle` nhưng tham số `OrderPlaced` xác định loại event nhận được. Thêm hậu tố `Event` vào class chỉ là **quy ước**; Spring không đọc tên để đoán ý nghĩa command/event.

Khi có nhiều listener cùng nghe `OrderPlaced`, mỗi listener có thể có công việc độc lập: audit, cập nhật projection, gửi notification. Producer không nên đổi tên sự kiện thành `SendConfirmationEmail` vì một listener cụ thể. **Tên domain event phải độc lập với cách consumer phản ứng.**

### Event không phải lời ra lệnh cho hệ thống khác

Một consumer của `OrderPlaced` có thể chọn không xử lý vì không thuộc phạm vi mình, hoặc chỉ ghi nhận thông tin. Nhưng khi event được mô hình hóa là fact, consumer **không nên giữ vai trò quyết định liệu việc đặt đơn có thành công hay không**. Những kiểm tra bắt buộc phải nằm trong use case, domain service hoặc workflow/command được điều phối rõ ràng.

## 8. “Đã xảy ra” có đồng nghĩa database đã commit?

**Không tự động.** Với một use case dùng `@Transactional`:

~~~java
@Transactional
public void placeOrder(PlaceOrder command) {
    Order order = domainService.place(command);
    orderRepository.save(order);
    publisher.publishEvent(new OrderPlaced(order.getId()));
}
~~~

Đây là **mã phác thảo** trong dự án có sẵn domain service/repository và cấu hình transaction. Nó không phải tệp biên dịch độc lập.

`publisher.publishEvent(...)` có thể được gọi **trước khi transaction thực sự commit**. Nếu commit thất bại hoặc mã về sau ném exception làm rollback, listener `@EventListener` đồng bộ có thể đã xử lý sự kiện. Nếu nó gửi email hoặc gọi API bên ngoài ngay, các tác động đó không được rollback cùng database.

Vì vậy cần phân biệt:

- **Domain fact trong luồng xử lý:** aggregate đã hoàn thành transition trong phạm vi use case, nên event có thể được tạo/công bố nội bộ.
- **Fact đã được commit bền vững:** transaction chứa trạng thái nguồn đã commit. Consumer bên ngoài thường cần mức bảo đảm này.
- **Event đã được giao đến consumer:** đây là vấn đề delivery riêng; commit database không tự bảo đảm listener/service ngoài đã nhận và xử lý.

### 8.1. Listener chỉ chạy sau commit

Spring hỗ trợ `@TransactionalEventListener` để gắn handler với pha transaction:

~~~java
@Component
public class NotificationListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlaced event) {
        // Chỉ xử lý khi transaction đã commit thành công.
    }
}
~~~

Đoạn minh họa cần import `Component`, `TransactionalEventListener` và `TransactionPhase` cùng kiểu `OrderPlaced`. Phase mặc định của `@TransactionalEventListener` là `AFTER_COMMIT`; khi transaction rollback, callback phase này không được thực thi. Nếu publish ngoài transaction, listener mặc định không chạy (trừ `fallbackExecution=true` được bật có chủ đích).

Hãy chọn **đúng cơ chế theo nhu cầu**, không đổi tên `OrderPlaced` thành `OrderWillBePlaced` chỉ để che một vấn đề thời điểm xử lý.

### 8.2. Khi cần giao event bền vững: transactional outbox

`@TransactionalEventListener(AFTER_COMMIT)` **không phải hàng đợi bền vững**. Tiến trình có thể dừng sau commit nhưng trước khi công việc listener hoàn tất; việc gửi thông báo quan trọng có thể bị mất.

Với tích hợp liên hệ thống cần retry, một lựa chọn phổ biến là **transactional outbox**:

1. Trong cùng transaction, ghi trạng thái đơn và bản ghi outbox chứa `OrderPlaced` cùng event ID.
2. Nếu rollback, cả đơn và outbox rollback; nếu commit, cả hai tồn tại.
3. Một dispatcher đọc outbox đã commit và gửi tới broker hoặc service đích.
4. Consumer dùng event ID/aggregate ID để xử lý idempotent; dispatcher theo dõi retry và trạng thái đã gửi.

Outbox thường thiết kế theo **at-least-once delivery**; nó không tự có “exactly once” xuyên mọi hệ thống. Nguyên tắc đặt tên vẫn như cũ: `OrderPlaced` diễn tả sự thật nghiệp vụ, còn outbox/broker là **cơ chế vận chuyển**.

## 9. Thiết kế payload để consumer hiểu fact

Một event nên mang **thông tin về điều đã xảy ra**, không nhúng lệnh consumer phải làm gì. Ví dụ metadata khi dùng qua nhiều process:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
    UUID eventId,
    long orderId,
    long aggregateVersion,
    Instant occurredAt,
    long totalVnd
) { }
~~~

Trong hệ thống thật:

- `eventId` dùng để nhận diện event và hỗ trợ deduplication khi retry.
- `orderId` xác định aggregate có trạng thái liên quan.
- `aggregateVersion` hoặc sequence giúp kiểm soát thứ tự event nếu consumer cần.
- `occurredAt` là thời gian fact nghiệp vụ được ghi nhận; không mặc nhiên bằng thời gian được gửi hay nhận.
- `totalVnd` phải được định nghĩa rõ (trước/sau thuế, phí, giảm giá). Số nguyên VND chỉ là mô hình đơn giản.

Các điểm thiết kế quan trọng:

- Ưu tiên payload bất biến như `record`; hạn chế truyền JPA entity đang managed hoặc object mutable sang listener async.
- Không đưa connection, entity manager, request context hay thông tin bí mật không cần thiết vào payload.
- Với integration event, cân nhắc version schema, tương thích ngược và thay đổi tên/field có ảnh hưởng đến consumer hiện hữu.
- Một tên ở thì quá khứ **không tự bảo đảm event duy nhất**. Nếu consumer có retry, phải có idempotency/ordering phù hợp.

## 10. Những tên dễ gây hiểu sai và cách cải thiện

| Tên gây khó hiểu | Vì sao chưa ổn | Cách chọn tốt hơn |
| --- | --- | --- |
| `CreateOrderEvent` | Trông như command yêu cầu tạo đơn | `OrderCreated` nếu thực sự tạo record; `OrderPlaced` nếu đơn đã được đặt |
| `PayOrderEvent` | Không biết yêu cầu trả tiền hay đã thu tiền | `CapturePayment` command; `PaymentCaptured` fact |
| `SendEmailEvent` | Hướng dẫn một listener cụ thể | `OrderPlaced` hoặc `CustomerRegistered` nếu email chỉ là phản ứng |
| `UserUpdated` | Quá chung nếu có nhiều loại thay đổi | `CustomerEmailChanged`, `AccountSuspended` khi đúng domain |
| `OrderSuccessEvent` | Không rõ thành công ở bước nào | `OrderPlaced`, `OrderConfirmed` hoặc `OrderPaid` tùy mốc |
| `PaymentWasSuccessfullyCapturedEvent` | Dài và trùng nghĩa | `PaymentCaptured`/`PaymentCapturedEvent` |
| `RefundRequest` | Có thể là entity, command hoặc event | `RequestRefund` cho command; `RefundRequested` cho fact |
| `OrderError` | Lỗi kỹ thuật hay business rejection? | `OrderRejected` chỉ khi domain thật sự đã từ chối |
| `OrderChange` | Không ở dạng fact rõ ràng | `OrderAddressChanged`, `OrderCancelled`, `OrderConfirmed` |
| `DeliveryDone` | Thuật ngữ không rõ | `OrderDelivered` hoặc `PackageDelivered` tùy thực thể |

Không phải tên nào có `Updated`, `Created` hay `Changed` cũng sai. Nếu domain quan tâm đúng sự kiện “cập nhật profile đã xảy ra”, `ProfileUpdated` có thể hợp lệ. Nhưng khi domain phân biệt nhiều transition quan trọng, tên chuyên biệt sẽ giảm suy đoán và coupling.

### Bounded context có thể dùng từ khác nhau

Trong Sales, `OrderPaid` có thể là trạng thái đã áp dụng vào order. Trong Payment, `PaymentCaptured` là sự thật do hệ thanh toán xác nhận. Một listener của Sales có thể nhận `PaymentCaptured` rồi thực hiện lệnh nội bộ ghi nhận thanh toán, sau đó phát `OrderPaid` nếu aggregate Sales thực sự thay đổi. **Không được tự coi hai sự kiện là cùng một fact** nếu ranh giới nghiệp vụ không tương ứng.

## 11. Checklist review tên event

Trước khi merge một lớp `...Event` mới, kiểm tra:

1. **Fact:** đây là điều đã xảy ra hay chỉ là điều cần làm?
2. **Thì quá khứ:** tên dùng động từ quá khứ đúng và tự nhiên?
3. **Chủ thể:** tên chỉ rõ aggregate/khái niệm nghiệp vụ?
4. **Mốc nghiệp vụ:** Created/Placed/Confirmed/Paid/Delivered có bị nhầm?
5. **Producer:** bên phát có quyền xác nhận sự thật đó?
6. **Điểm phát:** validation và transition đã thành công trước khi event được tạo?
7. **Transaction:** consumer cần thấy fact sau commit hay một bước cùng transaction?
8. **Delivery:** nếu không được mất event, đã có outbox/retry và idempotency?
9. **Payload:** có ID, phiên bản/thời điểm khi cần và tránh dữ liệu thừa/nhạy cảm?
10. **Tương thích:** đổi tên/schema có ảnh hưởng consumer hoặc contract ngoài hệ thống?
11. **Consistency:** thống nhất dùng `OrderPlaced` hay `OrderPlacedEvent`?
12. **Test:** các đường thành công/từ chối/rollback/duplicate đều có kỳ vọng rõ?

Quy ước có thể ghi vào tài liệu kiến trúc:

~~~text
Command: Verb + Noun        -> PlaceOrder, CancelOrder
Event:   Noun + Past Verb   -> OrderPlaced, OrderCancelled
Query:   Read Verb + Noun   -> GetOrder, FindOrders
Handler: on + EventName     -> onOrderPlaced, onPaymentCaptured
~~~

Đây là **quy ước thiết kế**, không phải điều kiện bắt buộc để Spring phát sự kiện. Spring route event chủ yếu theo **kiểu Java/annotation**, không kiểm tra tiếng Anh có chia thì quá khứ hay không.

## 12. Kiểm thử ngữ nghĩa event

Đối với `OrderPlaced`, không chỉ test listener nhận event mà phải xác định **khi nào event được phép xuất hiện**:

| Tình huống | Kỳ vọng |
| --- | --- |
| Command hợp lệ và đơn chuyển trạng thái thành công | Có `OrderPlaced` theo hợp đồng |
| Command không hợp lệ, bị từ chối trước transition | Không có `OrderPlaced` |
| Command trùng, không tạo state transition mới | Không phát thêm fact nếu domain không thực sự có transition mới |
| Capture chưa xong, mới authorize | Chỉ có `PaymentAuthorized` nếu cần; không có `PaymentCaptured` |
| Refund mới được yêu cầu | Có thể có `RefundRequested`, không có `PaymentRefunded` |
| Transaction bị rollback | Consumer cần fact đã commit không được hành động sai; dùng after-commit/outbox |
| Retry cùng event ID | Consumer không tạo side effect trùng nếu idempotency là yêu cầu |
| Hai event cho cùng aggregate bị đảo thứ tự | Projection cần dùng version/sequence để không ghi lùi trạng thái |

Với demo mục 6, có thể thay `System.out.println` bằng một listener lưu event vào `List<OrderPlaced>` trong test, gọi command hợp lệ và không hợp lệ rồi xác nhận **chỉ đúng một event được publish**. Với JPA/JDBC transaction thật, hãy kiểm tra **trạng thái sau commit/rollback**, không chỉ kiểm tra publisher đã được gọi trong một transaction chưa kết thúc.

## 13. Sai lầm thường gặp

1. **Đặt event như command:** `CreateOrderEvent` làm mơ hồ một lời yêu cầu và một sự thật.
2. **Tên đúng quá khứ nhưng sai ý nghĩa:** `PaymentCaptured` cho một khoản mới được authorize.
3. **Phát event trước validation/persistence:** consumer nhận “đã xảy ra” trong khi use case chưa chấp nhận.
4. **Tin rằng tên quá khứ là bảo đảm transaction commit:** `publishEvent` có thể chạy trước commit; sau-commit/outbox mới xử lý mốc tương ứng.
5. **Đặt tên theo hành động listener:** `SendWelcomeEmail` không phải tên tốt cho event khách đã đăng ký.
6. **Dùng tên quá chung:** `EntityUpdated` buộc consumer suy đoán.
7. **Đồng nhất lỗi hạ tầng với sự thật domain:** exception database chưa phải `OrderRejected`.
8. **Đổi hậu tố Event không nhất quán:** trộn nhiều tên cho cùng loại fact.
9. **Nhầm event với state hiện tại:** event là lịch sử; aggregate có thể đã chuyển tiếp sang trạng thái khác.
10. **Chia sẻ mutable entity trong payload:** listener chạy muộn có thể nhận trạng thái khác, gặp lazy loading hoặc phụ thuộc session đã đóng.
11. **Bỏ qua duplicate/retry:** event ID và idempotency vẫn cần ở những đường vận chuyển có thể gửi lại.
12. **Đổi tên lớp vô tình phá hợp đồng liên hệ thống:** tên/schema integration event cần version và kế hoạch migration.

## 14. Bài tập tự kiểm tra

1. Phân loại `PlaceOrder`, `OrderPlaced` và `GetOrder` theo command/event/query.
2. Cổng thanh toán báo authorize thành công nhưng chưa capture: nên phát `PaymentAuthorized` hay `PaymentCaptured`? Vì sao?
3. Một yêu cầu hoàn tiền vừa được ghi nhận vào hàng chờ: hãy phân biệt `RequestRefund`, `RefundRequested` và `PaymentRefunded`.
4. Vì sao `OrderCreated` không luôn đồng nghĩa `OrderPlaced`?
5. Vì sao tên `SendEmailAfterOrderPlacedEvent` gây coupling vào consumer, và bạn sẽ đặt tên nào?
6. Nếu `publisher.publishEvent(new OrderPlaced(...))` chạy trong `@Transactional` nhưng DB rollback, listener đồng bộ có thể đã xử lý không? Làm thế nào để chỉ xử lý khi commit?
7. Một công việc phải được giao bền vững sau commit. `@TransactionalEventListener(AFTER_COMMIT)` đã đủ chống mất event khi tiến trình chết chưa?
8. `OrderPlaced` có cần extends `ApplicationEvent` không?
9. Nếu consumer xử lý lại message, trường metadata nào giúp deduplicate?
10. Hãy viết tên sự kiện quá khứ cho “đã giữ kho”, “đã phát hành hóa đơn” và “đã hủy đăng ký”.

**Gợi ý trả lời:** (1) command/event/query; (2) `PaymentAuthorized`; (3) command, fact yêu cầu đã ghi nhận, fact hoàn tiền thành công; (4) Created có thể chỉ là draft; (5) `OrderPlaced`/`CustomerRegistered` theo domain; (6) có thể, dùng after-commit; (7) chưa, dùng transactional outbox/retry nếu không được mất; (8) không; (9) `eventId`; (10) `InventoryReserved`, `InvoiceIssued`, `SubscriptionCancelled`.

## Tài liệu tham khảo

- Spring Framework Reference, *Standard and Custom Events / Annotation-based Event Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference, *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Reference, *Using @Transactional*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2 Javadoc, *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 Javadoc, *EventListener*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/EventListener.html
