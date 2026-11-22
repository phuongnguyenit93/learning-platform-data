# Event biểu diễn điều gì đã xảy ra

## 1. Domain event là một sự thật nghiệp vụ

**Domain event** là thông điệp mô tả **một sự việc có ý nghĩa đối với nghiệp vụ đã xảy ra trong domain**. Tên event thường dùng thì quá khứ: `OrderPlaced` (đơn hàng đã được đặt), `PaymentCaptured` (đã thu tiền), `InventoryReserved` (đã giữ hàng), `ShipmentDispatched` (kiện hàng đã được bàn giao vận chuyển).

Ví dụ, khi hệ thống chấp nhận và tạo một đơn hàng hợp lệ, event có thể nói:

> Đơn hàng 101 của khách hàng 8 đã được đặt, với tổng giá trị 250.000 đồng, vào thời điểm 10:15 UTC.

Đó là **một phát biểu về trạng thái nghiệp vụ**. Nó không yêu cầu người nhận phải gửi email, trừ tiền, giao hàng hay làm bất kỳ việc nào. Những hành động ấy, nếu cần, là quyết định của các thành phần tiêu thụ event dựa trên quy tắc riêng.

~~~text
Khách hàng gửi yêu cầu ĐẶT HÀNG
             |
             v
     OrderService xử lý
       ├─ Kiểm tra yêu cầu
       ├─ Áp dụng quy tắc nghiệp vụ
       └─ Đơn hàng được chấp nhận
             |
             v
         OrderPlaced
             |
        +----+-----+
        |          |
        v          v
   Audit handler   Notification handler
   ghi nhận        quyết định có gửi thông báo hay không
~~~

**Điểm cốt lõi:** event kể lại **điều đã xảy ra**. Nó không phải lệnh điều khiển một đối tượng cụ thể và cũng không bảo đảm mọi hành động tiếp theo sẽ thành công.

Trong **Spring Framework Application Events**, domain event có thể là một object Java thông thường được đưa vào `ApplicationEventPublisher`. Spring cung cấp cơ chế chuyển event đến listener, còn **ý nghĩa nghiệp vụ, thời điểm công bố và tính nhất quán dữ liệu** vẫn là trách nhiệm thiết kế của ứng dụng.

## 2. Phân biệt command, event và state

Ba khái niệm thường xuất hiện trong cùng use case nhưng trả lời những câu hỏi khác nhau:

| Khái niệm | Câu hỏi được trả lời | Ví dụ | Tính chất |
| --- | --- | --- | --- |
| **Command** | “Hãy thử làm gì?” | `PlaceOrder`, `CapturePayment`, `ReserveInventory` | Diễn đạt ý định/yêu cầu, có thể thành công hoặc thất bại |
| **Domain event** | “Việc gì đã xảy ra?” | `OrderPlaced`, `PaymentCaptured`, `InventoryReserved` | Diễn đạt sự thật sau một chuyển trạng thái hợp lệ |
| **State** | “Hiện tại đối tượng đang như thế nào?” | `Order.status = PLACED` | Là trạng thái đang được lưu, có thể tiếp tục thay đổi |

Giả sử nhận command `PlaceOrder(orderId=101)`:

1. Service kiểm tra khách hàng, sản phẩm và giá trị đơn.
2. Nếu dữ liệu không hợp lệ, command bị từ chối. **Không phát `OrderPlaced`**.
3. Nếu quy tắc được thỏa mãn, đơn hàng chuyển sang trạng thái `PLACED`. Domain có thể tạo `OrderPlaced` với dữ liệu của sự việc vừa xảy ra.
4. Listener nhận thông báo và tự quyết định xử lý.

Một số cặp tên dễ nhầm:

| Không nên dùng khi thực chất là command | Event diễn đạt sự thật đúng hơn |
| --- | --- |
| `CreateOrderEvent` với nghĩa “hãy tạo đơn” | `OrderPlaced` sau khi đơn được chấp nhận |
| `SendEmailEvent` với nghĩa “hãy gửi email” | `OrderPlaced`; listener thông báo tự quyết định gửi email |
| `ChargeCreditCardEvent` với nghĩa “hãy thu tiền” | `PaymentCaptured` **chỉ sau khi** đã thực sự thu tiền |
| `OrderNeedsApproval` với nghĩa “hãy xét duyệt” | `OrderSubmittedForApproval` khi đơn đã được đưa vào quy trình duyệt |

Tên “ở thì quá khứ” là quy ước tốt, nhưng **ý nghĩa mới là tiêu chuẩn**. Đổi `SendEmailEvent` thành `EmailSent` khi email thực tế chưa gửi là sai; nó biến mong muốn thành phát biểu không đúng sự thật.

## 3. Một event nên có nội dung gì?

Event cần mô tả đủ để người tiêu thụ **hiểu sự việc** mà không phải đoán nội dung từ tên lớp. Các trường thường gặp:

- **Danh tính sự việc:** `eventId` có thể dùng để theo dõi, phát hiện xử lý lặp hoặc đối chiếu log trong hệ thống có retry.
- **Danh tính aggregate/thực thể:** `orderId` xác định đơn hàng xảy ra chuyển trạng thái; có thể thêm `customerId` khi đó là dữ liệu cần thiết, phù hợp chính sách dữ liệu.
- **Dữ liệu nghiệp vụ ở thời điểm xảy ra:** `totalCents`, `currency`, số lượng hoặc trạng thái mới. Nên chọn dữ liệu thật sự cần thiết; không sao chép cả entity graph.
- **Thời gian:** `occurredAt` là thời điểm domain ghi nhận sự việc. Nếu cần phân biệt thời điểm lưu DB, phát lên bus, nhận ở consumer, dùng tên trường riêng như `recordedAt` hoặc `publishedAt`; các thời điểm này không đồng nhất.
- **Phiên bản hợp đồng** (khi event được lưu hoặc tích hợp nhiều hệ thống): ví dụ `schemaVersion` hoặc version trong envelope để consumer biết cách đọc payload.
- **Thông tin tương quan** (nếu dùng workflow phân tán): `correlationId`, `causationId` để tra vết. Đừng đưa vào mọi event chỉ vì có thể.

Ví dụ mô hình giá trị:

~~~java
import java.time.Instant;
import java.util.UUID;

// Một phần mô hình, không phải chương trình độc lập.
public record OrderPlaced(
    UUID eventId,
    long orderId,
    long customerId,
    long totalCents,
    String currency,
    Instant occurredAt,
    int schemaVersion
) {}
~~~

### Giữ event ổn định và khó bị thay đổi

Event diễn đạt **một sự việc đã qua**, vì thế payload nên là một snapshot giá trị được giữ ổn định sau khi tạo:

- `record` trong Java 17+ phù hợp cho event nhỏ, có cấu trúc rõ. Tuy nhiên, `record` chỉ bảo đảm tính bất biến của các **tham chiếu field**, không tự làm immutable các `List`, `Map` hay object con có thể thay đổi; hãy tạo bản sao bất biến khi cần.
- Thay vì mang một đối tượng JPA `OrderEntity` còn gắn persistence context, nên mang ID và các giá trị nghiệp vụ cần thiết. Entity có thể bị sửa, lazy-load ngoài transaction hoặc chứa dữ liệu không nên tiết lộ.
- Dùng kiểu dữ liệu rõ nghĩa cho tiền. Ví dụ demo sẽ dùng `long totalCents` để tránh làm tròn số thực; ứng dụng đa tiền tệ cần nêu rõ đơn vị/loại tiền và quy tắc làm tròn.
- Không tự động nhét mật khẩu, token, số thẻ, thông tin cá nhân không cần thiết vào event vì có thể bị ghi log, lưu trữ hoặc gửi tới nhiều consumer.

**Quan trọng:** khi tên event là `OrderPlaced`, payload phải diễn đạt **thời điểm đơn được đặt**, không bị thay bằng trạng thái hiện tại `SHIPPED` ở lần đọc sau.

## 4. Chọn đúng ranh giới nghiệp vụ trước khi phát event

Một domain event nên được tạo khi **một quy tắc nghiệp vụ xác nhận có chuyển trạng thái có ý nghĩa**. Đừng phát `OrderPlaced` ngay khi HTTP request vừa tới, vì request có thể bị từ chối.

Phân biệt ba thời điểm:

~~~text
[1] Command đến
      |
      | Kiểm tra + xử lý
      v
[2] Domain xác nhận thay đổi hợp lệ
      |
      | Có thể tạo pending domain event
      v
[3] Giao dịch lưu dữ liệu thành công (nếu có DB)
      |
      v
Các consumer bên ngoài transaction được phép xem sự việc là đã commit
~~~

Trong hệ thống dùng DB transaction, việc **tạo object event ở bước [2]** không tự có nghĩa DB đã commit. Nếu transaction sau đó rollback, việc công bố ra bên ngoài từ quá sớm có thể làm consumer tin rằng đơn hàng tồn tại dù DB đã hủy thay đổi.

Các lựa chọn triển khai tùy mục đích:

1. **Công việc phải cùng transaction:** xử lý trong transaction hiện tại, hoặc dùng cơ chế phù hợp trước commit khi yêu cầu consistency. Nếu lỗi của consumer cần rollback cả use case, callback sau commit không đáp ứng yêu cầu này.
2. **Công việc chỉ nên xảy ra sau commit:** dùng `‎@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` trong ứng dụng quản lý transaction phù hợp. Listener sau commit không tự được cấp transaction ghi DB mới; nếu cần ghi tiếp, tổ chức transaction mới rõ ràng.
3. **Cần chuyển event bền vững sang hệ thống khác:** ghi domain change và bản ghi **outbox** trong cùng transaction; tiến trình khác gửi event với retry/idempotency. Không coi application event trong bộ nhớ là durable message queue.

Trong reactive transaction do `ReactiveTransactionManager` quản lý, context được lưu trong **Reactor Context**, không phải ThreadLocal. Khi dùng transaction-bound event listener, cần công bố theo cơ chế `TransactionalEventPublisher` của Spring để mang transaction context vào event source. Đây là chi tiết kỹ thuật của cơ chế công bố, không thay đổi ý nghĩa `OrderPlaced`.

## 5. Ví dụ Java 17+ với Spring: phát “OrderPlaced” khi đặt đơn thành công

Ví dụ này cố ý **không có database**, để minh họa rõ sự khác nhau giữa **command yêu cầu đặt đơn**, **domain quyết định đặt thành công** và **listener nhận sự thật đã xảy ra**. `OrderService` lưu tạm đơn hàng trong một `Map`; nếu command trùng ID hoặc giá trị không hợp lệ thì không phát event.

Dự án:

~~~text
domain-event-fact-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/DomainEventDemo.java
~~~

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'domain-event-fact-demo'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'demo.DomainEventDemo'
}
~~~

Tạo `src/main/java/demo/DomainEventDemo.java`:

~~~java
package demo;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class DomainEventDemo {

    // Command: một yêu cầu, chưa nói rằng đã đặt đơn thành công.
    public record PlaceOrder(
        long orderId,
        long customerId,
        long totalCents
    ) {}

    // Domain event: snapshot của một sự việc đã được chấp nhận.
    public record OrderPlaced(
        long orderId,
        long customerId,
        long totalCents,
        Instant occurredAt
    ) {}

    public static final class OrderService {
        private final ApplicationEventPublisher publisher;
        private final Clock clock;

        // Demo một luồng, chỉ lưu trong bộ nhớ.
        private final Map<Long, OrderPlaced> orders =
            new LinkedHashMap<>();

        public OrderService(ApplicationEventPublisher publisher,
                            Clock clock) {
            this.publisher = publisher;
            this.clock = clock;
        }

        public void place(PlaceOrder command) {
            if (command.orderId() <= 0 ||
                command.customerId() <= 0 ||
                command.totalCents() <= 0) {
                throw new IllegalArgumentException(
                    "Invalid order data"
                );
            }

            if (orders.containsKey(command.orderId())) {
                throw new IllegalStateException(
                    "Order already exists"
                );
            }

            // Với Map trong demo, đây là thời điểm trạng thái
            // được chấp nhận; không có DB transaction.
            OrderPlaced event = new OrderPlaced(
                command.orderId(),
                command.customerId(),
                command.totalCents(),
                Instant.now(clock)
            );

            orders.put(command.orderId(), event);

            // Spring nhận payload object thông thường.
            publisher.publishEvent(event);
        }

        public int count() {
            return orders.size();
        }
    }

    public static final class OrderPlacedListener {

        @EventListener
        public void whenOrderPlaced(OrderPlaced event) {
            System.out.println(
                "event: order " + event.orderId()
                + " placed for customer " + event.customerId()
                + ", totalCents=" + event.totalCents()
                + ", occurredAt=" + event.occurredAt()
            );
        }
    }

    @Configuration
    public static class DemoConfig {
        @Bean
        public Clock fixedClock() {
            return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
            );
        }

        @Bean
        public OrderService orderService(
                ApplicationEventPublisher publisher, Clock clock) {
            return new OrderService(publisher, clock);
        }

        @Bean
        public OrderPlacedListener orderPlacedListener() {
            return new OrderPlacedListener();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                DemoConfig.class)) {
            OrderService service = context.getBean(
                OrderService.class
            );

            // Thành công: tạo trạng thái và phát OrderPlaced.
            service.place(new PlaceOrder(101, 8, 25_000));

            // Thất bại: không được phát thêm OrderPlaced.
            try {
                service.place(new PlaceOrder(101, 8, 25_000));
            } catch (IllegalStateException ignored) {
                System.out.println("duplicate rejected");
            }

            try {
                service.place(new PlaceOrder(102, 9, -1));
            } catch (IllegalArgumentException ignored) {
                System.out.println("invalid amount rejected");
            }

            System.out.println("orders stored: " + service.count());
        }
    }
}
~~~

Chạy với JDK 17+ và Gradle tại thư mục dự án:

~~~bash
gradle run --quiet
# Nếu có Gradle Wrapper: ./gradlew run --quiet
# Trên Windows: gradlew.bat run --quiet
~~~

Các dòng do chính chương trình in ra, theo thứ tự (có thể có log riêng tùy cấu hình môi trường):

~~~text
event: order 101 placed for customer 8, totalCents=25000, occurredAt=2026-01-01T00:00:00Z
duplicate rejected
invalid amount rejected
orders stored: 1
~~~

Giải thích:

- `PlaceOrder(101, 8, 25000)` là command. Sau khi kiểm tra hợp lệ và ghi trạng thái trong `Map`, service phát **một event `OrderPlaced`**.
- Listener `@EventListener` nhận trực tiếp tham số kiểu `OrderPlaced`, dù payload không kế thừa `ApplicationEvent`. Spring hỗ trợ kiểu payload này thông qua cơ chế application event.
- Lần đặt đơn trùng ID bị từ chối trước khi ghi lại trạng thái/phát event. Lệnh có giá trị âm cũng thất bại. Vì vậy chỉ có **một dòng event**.
- `Clock.fixed` giúp `occurredAt` cố định để output có thể đối chiếu; ứng dụng thật thường inject `Clock.systemUTC()` và dùng clock đã được thống nhất.
- Trong demo, `Map` chỉ là ví dụ lưu tạm **không thread-safe, không bền vững và không có rollback**. Không áp dụng trực tiếp quy tắc “`put` rồi publish” cho hệ thống DB có transaction; cần giải quyết ranh giới commit ở mục 4.

**Giới hạn quan trọng của demo:** `ApplicationEventPublisher` không phải transaction manager. Listener đồng bộ mặc định có thể chạy ngay trong lời gọi `publishEvent`; nếu listener ném exception, exception có thể lan về service, trong khi `Map` đã thay đổi. Demo chỉ kiểm tra hợp lệ rồi phát event, chưa xây cơ chế rollback và retry. Nếu nghiệp vụ đòi tính nhất quán/độ bền, cần transaction hoặc outbox phù hợp.

## 6. Event nói “đã xảy ra” chứ không nói “kết quả tương lai sẽ thành công”

Một event tốt phải đủ chính xác để consumer **không suy diễn quá mức**.

Ví dụ:

~~~text
OrderPlaced
    ├─ Đúng: đơn đã được chấp nhận/đặt theo quy tắc domain.
    ├─ Chưa có nghĩa: thẻ đã bị thu tiền.
    ├─ Chưa có nghĩa: hàng đã được đóng gói.
    └─ Chưa có nghĩa: email xác nhận đã gửi.

PaymentCaptured
    └─ Đúng: hệ thống đã xác nhận tiền được thu theo nghĩa domain.

ShipmentDispatched
    └─ Đúng: kiện hàng đã thực sự bước vào trạng thái bàn giao.
~~~

Với quy trình gồm đặt đơn → thanh toán → vận chuyển, hãy dùng event cho **mỗi sự việc thực sự quan trọng**; đừng phát một `OrderCompleted` chỉ vì đã nhận yêu cầu đặt đơn.

Nếu thanh toán thất bại, tùy mô hình có thể ghi sự việc cụ thể như `PaymentDeclined` (đã bị từ chối), thay vì phát `PaymentCaptured` rồi thêm cờ `success=false`. Một event phải có ngữ nghĩa rõ ràng ngay từ tên và bất biến của payload.

Đối với một thao tác cố gắng nhưng chưa có kết quả cuối, dùng command hoặc trạng thái nghiệp vụ `PENDING` phù hợp. Trong hệ thống xử lý bất đồng bộ, event có thể nói `PaymentRequested` hoặc `PaymentProcessingStarted` nếu những **sự việc đó thực sự đã xảy ra**; đừng ngụy trang chúng thành `PaymentCaptured`.

## 7. Domain event và integration event không nhất thiết giống nhau

Domain event chủ yếu thuộc **ngôn ngữ của bounded context** và diễn tả sự việc trong mô hình nghiệp vụ. Integration event là hợp đồng dành cho **hệ thống hoặc bounded context khác**. Một domain event có thể được chuyển thành integration event, nhưng việc truyền nguyên object nội bộ ra ngoài thường tạo coupling không cần thiết.

| Tiêu chí | Domain event nội bộ | Integration event gửi hệ thống khác |
| --- | --- | --- |
| Phạm vi | Trong một domain/bounded context | Qua ranh giới hệ thống hoặc đội sở hữu |
| Payload | Phù hợp model domain, có thể dùng kiểu Java | Hợp đồng ổn định, serialize được, cân nhắc versioning |
| Vận chuyển | Có thể dùng Spring `ApplicationEventPublisher` | Broker/API/outbox hoặc cơ chế tích hợp rõ ràng |
| Độ bền | Spring application event mặc định ở bộ nhớ | Phụ thuộc transport, cơ chế lưu, ACK/retry |
| Tránh lặp | Tùy nghiệp vụ | Thường cần `eventId` và consumer idempotent |

Ví dụ một app có thể phát `OrderPlaced` nội bộ, rồi một adapter tạo `OrderSubmittedV1` theo schema công khai cho dịch vụ kho. Mapping phải bảo toàn ngữ nghĩa sự việc và không tạo thêm lời hứa không có thật.

Đừng nhầm **domain event** với **event sourcing**: một ứng dụng có domain event **không tự động** lưu toàn bộ lịch sử event để tái tạo trạng thái. Event sourcing là một lựa chọn kiến trúc riêng, đòi hỏi event log, thứ tự, versioning và quy tắc replay.

## 8. Consumer nên phản ứng thế nào với sự thật nghiệp vụ?

Consumer nên nhận đúng event, sử dụng dữ liệu cần thiết, rồi đưa ra hành động theo trách nhiệm của mình. Publisher không nên hardcode toàn bộ những việc mỗi consumer phải làm.

Ví dụ minh họa, không phải chương trình độc lập:

~~~java
@Component
class OrderNotificationHandler {

    private final NotificationService notifications;

    OrderNotificationHandler(NotificationService notifications) {
        this.notifications = notifications;
    }

    @EventListener
    public void onOrderPlaced(OrderPlaced event) {
        notifications.enqueueConfirmation(event.orderId());
    }
}
~~~

Đoạn trên giả định có `OrderPlaced`, `NotificationService` và import tương ứng. Phương thức `enqueueConfirmation(...)` là **hành động của consumer**, không phải nội dung “đã gửi email” mà event cam kết.

Lưu ý khi thiết kế listener:

- **Đặt tên theo hành động của consumer** như `createAuditEntry` hoặc `enqueueOrderConfirmation`, trong khi event vẫn có tên dạng fact `OrderPlaced`.
- **Không lẫn thất bại của consumer với sự thật domain**. Nếu email gửi thất bại, điều đó không làm câu “đơn hàng đã được đặt” trở thành sai; hãy quyết định retry/cảnh báo hoặc compensation theo yêu cầu nghiệp vụ.
- **Bảo đảm idempotency khi có retry hoặc delivery lặp**. Với integration event, có thể đặt unique constraint theo `eventId` ở phía xử lý để không ghi audit hoặc gửi thông báo trùng. Spring local event mặc định không tự bảo đảm exactly-once cho mọi hạ tầng.
- **Không phụ thuộc thứ tự callback giữa listener** trừ khi cấu hình và kiểm thử rõ ràng. Listener không nên ngầm dựa vào việc một listener khác đã tạo xong dữ liệu.
- **Xem xét transaction của side effect**. Listener cần ghi DB sau commit phải mở transaction phù hợp; listener gọi API mạng hoặc broker cần tính tới timeout, lỗi tạm thời và crash.
- **Đoạn event payload nên an toàn cho log**. Nếu chứa dữ liệu cá nhân, chính sách bảo mật và thời gian lưu giữ vẫn áp dụng.

## 9. Các dấu hiệu một event đang bị thiết kế sai

### Sai 1: Event là command được đổi tên

~~~java
// Tên “Event” nhưng đang yêu cầu một hành động:
record SendWelcomeEmailEvent(long customerId) {}
~~~

Nếu mục tiêu là yêu cầu gửi email, đó là **command/intent**. Nếu mục tiêu là phản ứng với sự việc đã đăng ký thành công, có thể phát `CustomerRegistered` và để notification handler quyết định gửi gì.

### Sai 2: Event phát khi nghiệp vụ chưa thành công

~~~java
publisher.publishEvent(new OrderPlaced(...));
repository.save(order); // Có thể thất bại.
~~~

Đoạn này **chỉ minh họa anti-pattern**, không phải code có thể biên dịch độc lập. Nếu lưu thất bại hoặc transaction rollback, consumer có thể đã xử lý một fact không được commit. Sắp xếp publication theo ranh giới nhất quán phù hợp (transaction-bound callback hoặc outbox).

### Sai 3: Payload là object sống có thể thay đổi

~~~java
record OrderPlacedWithEntity(OrderEntity order) {}
~~~

Đoạn minh họa cần class `OrderEntity`. Dù wrapper là `record`, `order` vẫn có thể bị thay đổi, có lazy association hoặc lộ cấu trúc lưu trữ. Mang identifier và snapshot giá trị có chủ ý sẽ an toàn hơn.

### Sai 4: Tên event quá chung

Các tên như `DataChanged`, `SystemUpdated`, `SomethingHappened` khiến consumer phải kiểm tra nhiều cờ hoặc truy vấn bổ sung để hiểu nghiệp vụ. Ưu tiên `OrderCancelled`, `PriceAdjusted`, `StockDepleted` khi đúng với ngôn ngữ domain.

### Sai 5: Event khẳng định quá nhiều

`OrderPlacedAndPaidAndShipped` tạo cảm giác ba sự việc luôn xảy ra nguyên tử. Nếu chúng thuộc ba giao dịch độc lập, cần mô tả từng fact ở đúng thời điểm. Chỉ dùng event tổng hợp khi domain **thực sự** có một milestone tổng hợp với ý nghĩa xác định.

### Sai 6: Event bị dùng như database model để mọi consumer chỉnh sửa

Consumer không nên chỉnh object event rồi hy vọng publisher nhìn thấy trạng thái mới. Event là thông báo, không phải entity cho nhiều bên cùng cập nhật. Mỗi consumer có thể tạo trạng thái riêng trong hệ thống của mình.

## 10. Checklist trước khi đặt tên và công bố domain event

Hãy trả lời từng câu:

1. **Điều gì thật sự đã xảy ra?** Nếu chưa có chuyển trạng thái hợp lệ, đó có thể chỉ là command hoặc intent.
2. **Tên lớp có phản ánh một fact cụ thể?** `OrderPlaced` diễn đạt rõ hơn `OrderEvent`.
3. **Sự việc xảy ra khi nào?** Có cần `occurredAt` và phân biệt thời điểm publish/commit không?
4. **Consumer cần nhận diện đối tượng nào?** Có `orderId`/`aggregateId` và dữ liệu snapshot tối thiểu chưa?
5. **Nội dung event có vô tình lộ thông tin nhạy cảm hay entity mutable không?**
6. **Nếu transaction rollback, consumer có thể vẫn nhận event không?** Nếu có, cần sửa ranh giới publication.
7. **Nếu publish thất bại hoặc process crash, hệ thống có mất thông báo không?** Với yêu cầu bền vững hãy xem outbox/transport phù hợp.
8. **Nếu event đến trùng hoặc đến muộn, consumer xử lý ra sao?** Có `eventId`, version, idempotency hoặc quy tắc thứ tự khi thực sự cần không?
9. **Tên event có khẳng định một kết quả chưa được chứng minh?** Ví dụ `PaymentCaptured` chỉ sau khi tiền đã được thu theo hợp đồng domain.
10. **Test có kiểm tra trường hợp thất bại không phát fact sai?** Đây là tiêu chí trực tiếp để phân biệt event với command.

Bảng kiểm thử hữu ích cho ví dụ đặt hàng:

| Tình huống | State | Event mong đợi |
| --- | --- | --- |
| Đặt đơn hợp lệ | Có đơn mới | Một `OrderPlaced` đúng ID/giá trị/thời điểm |
| Đơn trùng ID | Không tạo đơn mới | Không phát `OrderPlaced` mới |
| Tổng tiền không hợp lệ | Không tạo đơn | Không phát `OrderPlaced` |
| DB transaction rollback (ở phiên bản dùng DB) | Không có commit | Consumer chỉ nhận fact “đã được commit” nếu publication được thiết kế đúng |
| Consumer xử lý lỗi | Fact ban đầu không tự đảo ngược | Retry/compensation theo hợp đồng đã thiết kế |

## 11. Ghi nhớ

~~~text
Command:        “Hãy đặt đơn 101”
                    |
                    v
             Quy tắc nghiệp vụ
                    |
        Thành công  |   Thất bại
           |        |      |
           v        |      v
       OrderPlaced   |   Không có OrderPlaced
           |
           v
   Những consumer quan tâm đến sự thật này
   tự quyết định hành động phù hợp
~~~

**Domain event là câu khẳng định về một sự việc đã xảy ra trong nghiệp vụ.** Trong Spring, `ApplicationEventPublisher` và `@EventListener` chuyển và nhận thông điệp đó; chúng không thay thế việc bảo đảm tính đúng đắn của domain, thời điểm commit, tính bền vững hoặc hợp đồng với các hệ thống khác.

## Tài liệu tham khảo

- [Spring Framework — Standard and Custom Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/event/EventListener.html)
