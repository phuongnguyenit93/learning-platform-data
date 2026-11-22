# Dead-letter và thao tác bù trong Spring Application Events

## 1. Bối cảnh và mục tiêu

Một ứng dụng hướng sự kiện không thể giả định mọi listener và mọi hệ thống bên ngoài luôn thành công. Thanh toán có thể timeout, API vận chuyển tạm ngừng, một message chứa payload sai định dạng, hoặc tiến trình chết giữa lúc thay đổi dữ liệu và gửi thông báo. Khi bàn về **độ tin cậy**, hai cơ chế rất quan trọng là **dead-letter** và **thao tác bù (compensation)**.

**Dead-letter queue/topic (DLQ/DLT)** là nơi chuyển một message không thể xử lý theo chính sách hiện tại để lưu giữ, theo dõi, điều tra hoặc phát lại có kiểm soát. **Thao tác bù** là hành động nghiệp vụ mới nhằm xử lý hậu quả của các bước đã thành công trong một workflow sau khi bước sau thất bại: giải phóng tồn kho, hoàn tiền, hủy đặt chỗ hoặc thu hồi một quyền đã cấp.

Chúng không đồng nghĩa: **một message đi vào DLQ không tự động yêu cầu hủy đơn hàng**; ngược lại, một workflow có thể chủ động bù ngay sau lỗi nghiệp vụ mà không cần đợi DLQ.

Trong Spring, cần tách rạch ròi ba lớp:

1. **Spring Framework Application Events**: ApplicationEventPublisher, @EventListener, ApplicationEventMulticaster, @TransactionalEventListener. Phân phối trong cùng ApplicationContext; mặc định đồng bộ trong bộ nhớ. Không tự có durable queue, retry/acknowledgment, DLQ hoặc replay sau crash.
2. **Messaging integration** như Spring Kafka và Spring AMQP/RabbitMQ: listener containers, broker, retry, recovery, DLT/DLX và các quy tắc xác nhận thông điệp riêng.
3. **Thiết kế nghiệp vụ bền vững**: transactional outbox/inbox, state machine, saga/process manager, idempotency, compensation và vận hành redrive.

Sau bài học, bạn cần giải thích khi nào retry, khi nào dead-letter, khi nào bù, và làm sao tránh tạo thêm lỗi hoặc side effect trùng trong quá trình phục hồi.

## 2. Phân biệt Application Events với durable messaging

Một Spring bean phát event rất đơn giản:

~~~java
// Snippet minh họa bên trong service được Spring quản lý.
publisher.publishEvent(new OrderPlaced(orderId));
~~~

Listener xử lý:

~~~java
// Snippet minh họa.
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    paymentGateway.charge(event.orderId());
}
~~~

Với SimpleApplicationEventMulticaster mặc định, callback thường thực thi **đồng bộ ngay trên thread phát event**. Nếu charge ném RuntimeException, lỗi có thể lan về caller của publishEvent. Spring không tự ghi event lỗi vào một DLQ để phát lại sau restart.

Nếu dùng @Async @EventListener, callback chạy trên executor khác, nhưng queue của ThreadPoolTaskExecutor thường vẫn là **bộ nhớ của JVM**. Một tác vụ chưa xử lý khi JVM chết có thể mất. @Async thay đổi ranh giới thread và error handling, **không tự bảo đảm durable delivery**.

~~~text
ApplicationEventPublisher
    |
    +-- SimpleApplicationEventMulticaster mặc định
    |       +-- callback đồng bộ
    |       +-- exception có thể lan tới publisher
    |
    +-- @Async hoặc multicaster với TaskExecutor
            +-- callback chạy trên worker thread
            +-- queue thường in-memory
            +-- không tự có ACK/retry/DLQ sau crash
~~~

Nếu yêu cầu nghiệp vụ là “message phải được xử lý cuối cùng kể cả khi service restart”, phải có storage/broker bền vững hoặc một cơ chế tương đương, không chỉ một event listener in-process.

### Các thuật ngữ

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| Event | Thông tin về sự kiện đã xảy ra như OrderPlaced |
| Attempt | Một lần thực thi xử lý message |
| Retry | Thử lại sau lỗi, có chính sách và giới hạn |
| DLQ/DLT | Điểm lưu message không thể xử lý theo chính sách hiện hành |
| Redrive/replay | Xử lý lại message được giữ trong DLQ/history |
| Compensation | Hành động nghiệp vụ để xử lý hậu quả bước đã hoàn thành |
| Idempotency | Không nhân đôi side effect khi cùng ý định được giao lại |
| Outbox | Bản ghi event được commit cùng dữ liệu nghiệp vụ |
| Inbox/processed-events | Dấu vết xử lý giúp consumer chống duplicate |
| Saga | Chuỗi transaction cục bộ có bước tiếp tục hoặc bù |
| Poison message | Message liên tục gây lỗi, có thể là lỗi dữ liệu/chương trình |

Dead-letter **không đồng nghĩa xử lý thành công**. Đây thường là chuyển trạng thái sang “ngừng retry tự động, cần workflow vận hành khác”.

## 3. Phân loại thất bại trước khi retry

Không phải mọi exception đều đáng retry. Phân loại theo tính chất nghiệp vụ và kỹ thuật.

### Lỗi tạm thời

Ví dụ: HTTP 503, network timeout, API đối tác bị rate limit, deadlock DB có thể phục hồi hoặc broker gián đoạn. Dùng **bounded retries** với backoff, jitter, timeout và giới hạn tổng thời gian.

### Lỗi vĩnh viễn theo dữ liệu hiện tại

Ví dụ: payload sai schema, thiếu trường bắt buộc, event version chưa được hỗ trợ, lệnh vượt quy tắc nghiệp vụ hoặc mã khách hàng không hợp lệ. Retry cùng payload hàng trăm lần thường vô ích. Có thể đưa DLQ ngay, phản hồi business rejection hoặc gửi quy trình làm sạch dữ liệu.

### Kết quả mơ hồ

Đặc biệt nguy hiểm là timeout sau khi gọi thanh toán/hoàn tiền: request có thể **đã thành công ở bên ngoài**, nhưng caller không nhận được response. Nếu retry với ID mới, khách hàng có thể bị charge/refund nhiều lần.

Cách xử lý an toàn:

1. Lưu operationId/idempotency key ổn định.
2. Query trạng thái thực tế ở nhà cung cấp nếu có API.
3. Nếu đã thành công, hoàn thành workflow mà không gọi lại.
4. Nếu chắc chắn chưa thực hiện, mới thử lại theo chính sách.
5. Nếu không thể xác minh, đưa trạng thái vào **PENDING_RECONCILIATION** và yêu cầu can thiệp phù hợp.

Không suy ra “timeout = thất bại” hoặc “HTTP 400 = luôn không retry”: hợp đồng của API bên ngoài mới quyết định.

## 4. Thiết kế retry và dead-letter policy

Một quy trình mẫu:

~~~text
Delivery lần 1
   |
   +-- thành công -> mark processed / ACK phù hợp
   |
   +-- transient failure
   |     |
   |     +-- đợi 1s (+ jitter), retry 1
   |     +-- đợi 2s (+ jitter), retry 2
   |     +-- đợi 4s (+ jitter), retry 3
   |     +-- vẫn lỗi -> DLQ + alert
   |
   +-- permanent failure -> DLQ / reject nghiệp vụ ngay
   |
   +-- ambiguous outcome -> query trạng thái / reconciliation
~~~

Cần xác định rõ:

- **Max attempts**: số tổng lần thực thi hay số lần retry sau lần đầu? “3 attempts” thường là 1 ban đầu + 2 retry.
- **Backoff**: tăng thời gian đợi, jitter tránh retry storm.
- **Timeout**: mỗi attempt phải hữu hạn; task chết treo không được giữ worker mãi.
- **Deadline/TTL**: message quá cũ có thể hết ý nghĩa.
- **Concurrency/rate limit**: retry traffic không chiếm hết tài nguyên của request mới.
- **Exception classification**: retryable, non-retryable, ambiguous.
- **Recovery**: chuyển DLQ, tiếp tục saga, yêu cầu thao tác bù hay báo người vận hành.
- **Monitoring**: attempts, errors, queue depth, oldest age và business impact.

Một bẫy là bắt mọi Exception, log rồi return bình thường: container/broker có thể tưởng message đã xử lý và ACK, khiến lỗi không bao giờ được retry hoặc dead-letter.

## 5. Dead-letter record nên chứa dữ liệu gì?

Một envelope minh họa:

~~~java
// Snippet Java: dữ liệu mô tả một message thất bại.
public record DeadLetterEnvelope(
        String originalEventId,
        String eventType,
        int schemaVersion,
        String aggregateId,
        String correlationId,
        String causationId,
        String consumerName,
        int attempts,
        String errorCode,
        String originalDestination,
        String failedAtIso8601,
        String payloadReference
) {}
~~~

**Các trường quan trọng:**

- originalEventId phải giữ ổn định qua redelivery.
- eventType/schemaVersion giúp nâng cấp schema hoặc sửa message.
- aggregateId xác định đối tượng đang bị ảnh hưởng.
- correlationId/causationId truy nguyên chuỗi sự kiện.
- consumerName phân biệt cùng event nhưng nhiều consumers khác nhau.
- attempts/errorCode hỗ trợ phân tích retry; errorCode nên ổn định hơn exception text.
- originalDestination ghi topic, partition hoặc queue ban đầu khi có.
- failedAt để theo dõi tuổi message; dùng timestamp rõ timezone.
- payloadReference trỏ tới payload được lưu an toàn; không mặc định ghi mọi dữ liệu nhạy cảm vào DLQ.

DLQ phải có **chủ sở hữu**, thời gian lưu, phân quyền, chính sách bảo mật và trạng thái vận hành như NEW, INVESTIGATING, READY_TO_REDRIVE, RESOLVED. Nếu không, DLQ trở thành nơi tích tụ message mà không ai phục hồi.

### Có nên lưu stack trace?

Có thể giữ thông tin lỗi phục vụ điều tra, nhưng hãy giới hạn kích thước, redaction PII/tokens và retention. Với một số broker, liên tục redrive rồi dead-letter lại có thể làm exception headers/phần lịch sử tăng rất lớn.

## 6. Dead-letter và compensation là hai quyết định khác nhau

Phân tích theo workflow:

~~~text
OrderPlaced
  |
  +-- ReserveInventory       (đã thành công)
  |
  +-- ChargePayment
        |
        +-- thành công -> OrderPaid -> tiếp tục giao hàng
        |
        +-- tạm thời -> retry có giới hạn
        |
        +-- cuối cùng không thể hoàn thành
                |
                +-- ghi failed-message/DLQ
                +-- quyết định nghiệp vụ
                     |
                     +-- CancelAndReleaseInventory
                     +-- hoặc PendingManualReview
                     +-- hoặc ForwardRecovery
~~~

**Không nên thiết kế quy tắc “bất kỳ entry DLQ nào cũng hủy order”.**

- Nếu email thông báo lỗi, đơn hàng đã PAID vẫn có thể hoàn toàn hợp lệ.
- Nếu payment bị từ chối vĩnh viễn, release inventory có thể đúng.
- Nếu kết quả charge đang mơ hồ, release hoặc refund ngay có thể sai.
- Nếu sản phẩm đã SHIPPED, thao tác “hủy” đơn không thể mặc định đảo lại vận chuyển.

DLQ là hiện tượng kỹ thuật của **một consumer/operation**. Compensation là quyết định của **business workflow** tại trạng thái hiện tại. Có thể dead-letter xong mới review và quyết định bù; cũng có thể bù ngay theo một quy tắc đủ an toàn rồi vẫn giữ DLQ record để audit.

## 7. Ví dụ Spring Framework Java 17+ chạy được

Ví dụ sau sử dụng **Java 17+**, Maven và **Spring Framework 6.2.12**. Không cần Spring Boot, database, Kafka hay RabbitMQ.

**Giới hạn bắt buộc hiểu đúng:** DeadLetters trong mã là một Map **in-memory mô phỏng DLQ**, không có persistence. Retry thực hiện đồng bộ không backoff để kết quả ổn định. Đây là **demo ngữ nghĩa** dead-letter/compensation, không phải giải pháp production hay reliable queue thực sự.

### Yêu cầu của tình huống

- Khi đặt hai đơn hàng, tồn kho được reserved.
- **order-good**: PaymentGateway giả lập lỗi hai lần rồi thành công lần ba.
- **order-bad**: PaymentGateway giả lập lỗi cả ba lần.
- Khi hết retry, listener ghi event-bad vào dead-letter Map và publish một yêu cầu bù **CancelAndRelease**.
- Compensation listener release inventory, đổi trạng thái sang CANCELLED.
- Nếu cùng yêu cầu bù hoặc event gốc được gửi lại, state guard ngăn tác động lặp.
- Output xác định nhờ multicaster mặc định đồng bộ, không có clock/sleep.

Cấu trúc:

~~~text
dead-letter-compensation-demo/
├── pom.xml
└── src/main/java/demo/DeadLetterCompensationDemo.java
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>dead-letter-compensation-demo</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.2. src/main/java/demo/DeadLetterCompensationDemo.java

~~~java
package demo;

import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class DeadLetterCompensationDemo {

    // Retry cùng event phải giữ nguyên eventId.
    public record OrderPlaced(String orderId, String eventId) {}

    // Action bù có ID riêng, liên kết được với nguyên nhân.
    public record CancelAndRelease(String orderId, String actionId) {}

    public enum Status { RESERVED, PAID, CANCELLED }

    public static final class TemporaryGatewayFailure
            extends RuntimeException {
        public TemporaryGatewayFailure() {
            super("Temporary gateway failure");
        }
    }

    // In-memory model. Production cần DB/transaction/concurrency guard.
    public static final class OrderState {
        private final Map<String, Status> statuses = new LinkedHashMap<>();
        private final Set<String> reservedInventory = new LinkedHashSet<>();

        public void reserve(String orderId) {
            if (statuses.putIfAbsent(orderId, Status.RESERVED) != null) {
                throw new IllegalArgumentException("Duplicate order");
            }
            reservedInventory.add(orderId);
        }

        public Status status(String orderId) {
            Status status = statuses.get(orderId);
            if (status == null) {
                throw new IllegalArgumentException("Unknown order");
            }
            return status;
        }

        public void markPaid(String orderId) {
            if (status(orderId) != Status.RESERVED) {
                throw new IllegalStateException("Invalid payment state");
            }
            statuses.put(orderId, Status.PAID);
        }

        public boolean cancelAndReleaseOnce(String orderId) {
            if (status(orderId) != Status.RESERVED) {
                return false;
            }
            reservedInventory.remove(orderId);
            statuses.put(orderId, Status.CANCELLED);
            return true;
        }
    }

    // Stub tất định: good thành công lần 3; bad luôn thất bại.
    public static final class PaymentGateway {
        private final Map<String, Integer> attempts = new LinkedHashMap<>();

        public void charge(String orderId) {
            int attempt = attempts.merge(orderId, 1, Integer::sum);

            if ("order-good".equals(orderId) && attempt == 3) {
                System.out.println(
                    "gateway order-good attempt=3 SUCCESS");
                return;
            }

            System.out.println(
                "gateway " + orderId + " attempt=" + attempt + " FAIL");
            throw new TemporaryGatewayFailure();
        }
    }

    public record DeadLetter(
            OrderPlaced original, int attempts, String errorCode) {}

    public static final class DeadLetters {
        private final Map<String, DeadLetter> records =
                new LinkedHashMap<>();

        public void save(OrderPlaced event, int attempts, String errorCode) {
            records.putIfAbsent(
                event.eventId(), new DeadLetter(event, attempts, errorCode));
        }

        public int size() {
            return records.size();
        }
    }

    public static final class PaymentListener {
        private static final int MAX_ATTEMPTS = 3;

        private final OrderState orders;
        private final PaymentGateway gateway;
        private final DeadLetters deadLetters;
        private final ApplicationEventPublisher publisher;

        public PaymentListener(
                OrderState orders,
                PaymentGateway gateway,
                DeadLetters deadLetters,
                ApplicationEventPublisher publisher) {
            this.orders = orders;
            this.gateway = gateway;
            this.deadLetters = deadLetters;
            this.publisher = publisher;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            Status current = orders.status(event.orderId());

            if (current != Status.RESERVED) {
                System.out.println(
                    "duplicate " + event.orderId()
                    + " ignored status=" + current);
                return;
            }

            // Demo: retry đồng bộ. Production cần backoff và retry scheduler.
            for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
                try {
                    gateway.charge(event.orderId());
                    orders.markPaid(event.orderId());
                    System.out.println(
                        "payment " + event.orderId() + " captured");
                    return;
                } catch (TemporaryGatewayFailure ex) {
                    if (attempt == MAX_ATTEMPTS) {
                        deadLetters.save(
                            event, attempt, "GATEWAY_UNAVAILABLE");
                        System.out.println(
                            "dlq " + event.eventId()
                            + " attempts=" + attempt);

                        // Đây là lệnh bù mới, không phải database rollback.
                        publisher.publishEvent(new CancelAndRelease(
                            event.orderId(), "release:" + event.eventId()));
                    }
                }
            }
        }
    }

    public static final class CompensationListener {
        private final OrderState orders;

        public CompensationListener(OrderState orders) {
            this.orders = orders;
        }

        @EventListener
        public void releaseInventory(CancelAndRelease event) {
            if (orders.cancelAndReleaseOnce(event.orderId())) {
                System.out.println(
                    "compensation " + event.orderId()
                    + " inventory-released");
            } else {
                System.out.println(
                    "compensation " + event.orderId() + " skipped");
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public OrderState orderState() {
            return new OrderState();
        }

        @Bean
        public PaymentGateway paymentGateway() {
            return new PaymentGateway();
        }

        @Bean
        public DeadLetters deadLetters() {
            return new DeadLetters();
        }

        @Bean
        public PaymentListener paymentListener(
                OrderState orders,
                PaymentGateway gateway,
                DeadLetters letters,
                ApplicationEventPublisher publisher) {
            return new PaymentListener(orders, gateway, letters, publisher);
        }

        @Bean
        public CompensationListener compensationListener(OrderState orders) {
            return new CompensationListener(orders);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            OrderState orders = context.getBean(OrderState.class);
            DeadLetters dlq = context.getBean(DeadLetters.class);

            orders.reserve("order-good");
            orders.reserve("order-bad");

            context.publishEvent(
                new OrderPlaced("order-good", "event-good"));
            context.publishEvent(
                new OrderPlaced("order-bad", "event-bad"));

            // Trùng yêu cầu bù: không release thêm lần thứ hai.
            context.publishEvent(
                new CancelAndRelease("order-bad", "release:event-bad"));

            // Redelivery của event gốc sau khi đơn đã CANCELLED.
            context.publishEvent(
                new OrderPlaced("order-bad", "event-bad"));

            System.out.println(
                "final order-good=" + orders.status("order-good"));
            System.out.println(
                "final order-bad=" + orders.status("order-bad"));
            System.out.println("dlq-count=" + dlq.size());
        }
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.DeadLetterCompensationDemo
~~~

Những dòng do **chính chương trình** in ra:

~~~text
gateway order-good attempt=1 FAIL
gateway order-good attempt=2 FAIL
gateway order-good attempt=3 SUCCESS
payment order-good captured
gateway order-bad attempt=1 FAIL
gateway order-bad attempt=2 FAIL
gateway order-bad attempt=3 FAIL
dlq event-bad attempts=3
compensation order-bad inventory-released
compensation order-bad skipped
duplicate order-bad ignored status=CANCELLED
final order-good=PAID
final order-bad=CANCELLED
dlq-count=1
~~~

Maven/Spring có thể in log bổ sung. Output trên là dự kiến từ System.out.println trong mã, không phải khẳng định đã chạy Maven tại máy thật.

### 7.3. Giải thích chi tiết

- **order-good** có ba attempt nhưng chỉ **một original eventId**. Gateway thành công lần thứ ba; state trở thành PAID, không có DLQ/compensation.
- **order-bad** thất bại cả ba lần. PaymentListener lưu DeadLetter theo event-bad, in trạng thái và phát CancelAndRelease.
- Vì multicaster mặc định đồng bộ, CompensationListener nhận event bù ngay. Nó release inventory và chuyển order-bad sang CANCELLED.
- Cùng action bù được phát lại sau đó. State không còn RESERVED, nên lần này in skipped. Đây là một ví dụ state guard idempotent.
- Cùng OrderPlaced event-bad được publish lại. PaymentListener thấy state CANCELLED, bỏ qua và không gọi payment gateway lần nữa.
- DLQ count vẫn bằng 1: bản ghi lỗi được giữ lại để phân tích dù việc bù đã hoàn tất.

**Mô phỏng này không kiểm chứng**: durability, database atomicity, concurrency, broker ACK, asynchronous retry, crash recovery, exactly-once payments hoặc khả năng lưu DLQ khi hệ thống chết. Các tính chất ấy phải được thiết kế và test riêng.

### 7.4. Những giới hạn cố ý của demo

- Mọi Map/Set chỉ tồn tại trong JVM, không thread-safe cho nhiều writers; thực tế cần storage, unique constraint và optimistic locking.
- Retry ngay không có backoff để output rõ ràng. Thực tế phải có timeout, bounded backoff/jitter và phân loại failure.
- Stub payment không thật sự thu tiền; cổng thanh toán thật cần external idempotency key và đối soát kết quả mơ hồ.
- Tác vụ bù được publish đồng bộ trong JVM; nếu process crash giữa ghi dead-letter và yêu cầu bù, có thể mất hành động bù.
- State guard theo trạng thái là một lớp bảo vệ; production còn cần actionId và version để chống lặp ở cấp message/consumer.

## 8. Compensation khác rollback

Một database transaction có thể rollback những thay đổi **chưa commit** trong phạm vi transaction đó. Nhưng một workflow phân tán thường đã commit nhiều local transactions:

~~~text
T1: InventoryService giữ sản phẩm            COMMITTED
T2: PaymentService thu tiền                  COMMITTED
T3: ShippingService tạo vận đơn              FAILED
~~~

Rollback JDBC ở ShippingService không tự xóa T1 hoặc hoàn tiền T2. Hệ thống cần các hành động **mới**:

~~~text
ShippingFailed
    |
    +-- RequestPaymentRefund
    |       +-- RefundCompleted (khi xác nhận thực tế)
    |
    +-- RequestInventoryRelease
    |       +-- InventoryReleased
    |
    +-- OrderCancellationCompleted
~~~

Các thao tác bù cũng có thể thất bại. Refund có thể mất nhiều ngày; shipment có thể đã giao cho đối tác; inventory release có thể bị xung đột. Vì thế **bù không đồng nghĩa đảo hoàn hảo lịch sử**.

### Bù cần tính idempotent

- compensationActionId cố định qua các retry.
- Unique constraint theo actionId/consumer khi lưu processed action.
- Kiểm tra expectedState/aggregateVersion và transition hợp lệ.
- Dùng idempotency key của cổng thanh toán khi refund.
- Nếu timeout không rõ refund thành công chưa, query kết quả thay vì tạo refund mới.
- Lưu trạng thái PENDING, RUNNING, COMPLETED, FAILED để không suy luận “đã gửi yêu cầu = đã thành công”.

Không được thực thi một cancellation message cũ trên order đã SHIPPED chỉ vì message thuộc workflow cũ. Cần so trạng thái hiện tại và quyền hành động.

## 9. Saga orchestration và choreography

**Saga** là chuỗi local transactions; khi một bước thất bại, hệ thống có thể thử thực hiện tiếp hoặc chạy các bước bù.

### Choreography

Các service tự lắng nghe events và phát events kế tiếp:

~~~text
OrderCreated -> InventoryReserved -> PaymentCaptured -> ShipmentCreated
                      |
                      +-- PaymentFailed -> ReleaseInventory -> OrderCancelled
~~~

Ưu điểm là loose coupling. Nhược điểm: khó quan sát khi nhiều modules; chu kỳ event, duplicate và lựa chọn bù có thể bị phân tán qua nhiều listeners.

### Orchestration

Một **process manager/saga orchestrator** lưu trạng thái bền:

~~~text
sagaId=checkout-17
state=COMPENSATION_PENDING
failedStep=CHARGE_PAYMENT
nextAction=RELEASE_INVENTORY
attempt=2
nextRetryAt=...
~~~

Orchestrator xác định hành động kế tiếp, timeout, phương án forward recovery hoặc compensation. Quan trọng: trạng thái của orchestrator phải **persist**, không dùng static Map trong một JVM production.

Không có một annotation duy nhất trong Spring Context tự biến @EventListener thành distributed saga. Cần thiết kế state machine, transactions, messaging và monitoring theo yêu cầu.

## 10. Transactional outbox và idempotent inbox

Khi OrderService commit thành công nhưng process chết trước khi publish integration event, thông điệp có thể mất nếu chỉ dựa vào callback in-process.

**Transactional outbox** lưu thay đổi nghiệp vụ và event cần gửi **trong cùng transaction database**:

~~~text
BEGIN
    UPDATE orders SET status = 'RESERVED' ...
    INSERT INTO outbox_events ...
COMMIT
    |
    +-- relay đọc outbox
    +-- publish broker
    +-- consumer xử lý (idempotent)
~~~

Sơ đồ SQL minh họa (kiểu dữ liệu thực tế tùy DB):

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(100) PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload_json TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE compensation_actions (
    action_id VARCHAR(100) PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

**Vì sao cần inbox/unique constraint?** Relay có thể publish thành công, rồi crash trước khi đánh dấu outbox đã gửi. Khi restart, cùng event được phát lại. Consumer cần bảo đảm việc đánh dấu processed và cập nhật database nghiệp vụ nằm trong **cùng transaction**. Chỉ SELECT xem đã có eventId rồi side effect không có transaction/unique constraint vẫn dễ gặp race.

Với API bên ngoài, idempotency của chính API hoặc bước reconcile là cần thiết; unique constraint trong DB của bạn không tự ngăn đối tác thực hiện side effect hai lần nếu kết quả từ xa mơ hồ.

### Khi lưu compensation

Thay vì chỉ phát CancelAndRelease in-process sau khi nhận failure, có thể **lưu compensation intent** cùng transition Order -> CANCELLATION_PENDING rồi worker bền vững lấy action và thực hiện. Nếu worker chết, action vẫn còn để retry. Khi hoàn tất, cập nhật trạng thái và phát CompensationCompleted theo hợp đồng.

Outbox tăng độ bền nhưng **không tự đảm bảo exactly-once end-to-end**; duplicate vẫn có thể xảy ra tại broker hoặc external API.

## 11. Dead-letter trong Spring Kafka

**Spring Kafka** cung cấp framework khác với Spring Context @EventListener. Với @KafkaListener, có thể cấu hình:

- **DefaultErrorHandler** để điều khiển retries, classify exceptions và recovery.
- **DeadLetterPublishingRecoverer** để gửi message thất bại sang dead-letter topic.
- **FixedBackOff** hoặc exponential backoff hữu hạn.
- Container ACK/offset và transaction policy được thiết kế đúng.

Ví dụ **snippet cấu hình**, không thuộc demo Spring Context ở mục 7:

~~~java
// Cần spring-kafka, KafkaTemplate phù hợp và cấu hình container.
@Bean
DefaultErrorHandler errorHandler(KafkaTemplate<Object, Object> template) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    // Lần đầu + 2 retries = tối đa 3 attempts.
    return new DefaultErrorHandler(
            recoverer, new FixedBackOff(1_000L, 2L));
}
~~~

Cần imports cho DefaultErrorHandler, DeadLetterPublishingRecoverer, KafkaTemplate và org.springframework.util.backoff.FixedBackOff. Quan trọng: **phải gắn handler vào Kafka listener container factory thực sự được dùng**; không suy ra mọi Kafka listener tự dùng bean này nếu không có auto-configuration tương ứng.

Theo Spring Kafka docs, resolver mặc định của DeadLetterPublishingRecoverer có thể dùng topic hậu tố **-dlt** và partition tương ứng của record gốc; đảm bảo DLT tồn tại, partition count phù hợp hoặc tự cấu hình resolver. Cần chú ý hành vi nếu publish DLT **cũng thất bại**; không được ACK/commit nguồn như thể recovery hoàn tất nếu chính sách yêu cầu phải lưu dead-letter bền vững.

DLT ghi lỗi ở consumer level; muốn bù nghiệp vụ cần consumer/process manager quyết định và phát command hoặc event bù riêng.

## 12. Dead-letter trong RabbitMQ/Spring AMQP

Với RabbitMQ, thường dùng **dead-letter exchange (DLX)** gắn với queue, routing key và dead-letter queue. Message có thể được dead-letter khi consumer reject/nack với requeue=false, TTL hết hạn hoặc do các điều kiện queue phù hợp.

Cần xác định:

1. Original queue và cơ chế consumer acknowledgment.
2. Dead-letter exchange, dead-letter routing key và target queue.
3. Retry topology, TTL/delay và số lần tối đa; tránh lặp qua DLX vô hạn.
4. Chính sách requeue khi lỗi transient so với permanent.
5. Message ID, redelivery metadata, idempotency và ordering.
6. Điều gì xảy ra nếu dead-letter routing/publish thất bại.
7. Monitoring, retention và redrive.

Spring AMQP có listener container, retry interceptor, recoverer riêng; không lấy nguyên cấu hình Spring Kafka để áp dụng cho RabbitMQ. DLX cũng không tự tạo DLQ cho @EventListener nội bộ của Spring Context.

## 13. Redrive: phát lại message từ DLQ một cách an toàn

Redrive là **thao tác có thể tạo side effect trùng**, vì trạng thái nghiệp vụ đã thay đổi trong lúc message nằm ở DLQ.

Quy trình vận hành đề xuất:

1. Xác định original eventId, consumerName, aggregate, schema version, errorCode và attempts.
2. Xác nhận bug/downstream/schema đã được sửa; nếu chưa, redrive chỉ tạo vòng lỗi mới.
3. Đối chiếu business state **hiện tại** cùng trạng thái compensation.
4. Kiểm tra idempotency key và external outcome: liệu charge/refund/email/booking đã thực sự xảy ra?
5. Quyết định **replay original event**, **tạo command mới** hoặc **mark resolved**. Không xem ba lựa chọn là tương đương.
6. Nếu sửa payload, lưu audit: ai sửa, phiên bản mới, hash/correlation và lý do.
7. Redrive theo batch nhỏ, rate limit và có số lần redrive tối đa.
8. Kiểm tra side effect, business state và đóng DLQ entry có bằng chứng.

Nếu order đã CANCELLED và tồn kho đã release, đừng tự động publish lại PaymentRequested cũ làm đơn thành PAID. Muốn phục hồi giao dịch, thường cần **workflow mới có thẩm quyền**.

### Vòng lặp DLQ

Message được đẩy từ DLQ về queue chính, fail và lại về DLQ có thể tạo vòng lặp vô hạn. Nên lưu redriveAttemptCount, thời điểm thử cuối, quyết định người duyệt và trạng thái terminal để giới hạn chu kỳ.

## 14. Khi thao tác bù cũng thất bại

Một bước bù phải được xử lý nghiêm túc như một thao tác nghiệp vụ:

~~~text
CancelAndRelease
    |
    +-- thành công -> OrderCancelled
    |
    +-- InventoryService timeout
           |
           +-- retry bounded cùng actionId
           +-- COMPENSATION_PENDING
           +-- cạn retry -> COMPENSATION_FAILED
                              +-- compensation DLQ/alert/manual recovery
~~~

Các trạng thái có ý nghĩa:

- BUSINESS_STEP_FAILED: bước chính không hoàn tất.
- COMPENSATION_REQUESTED: đã quyết định bù nhưng chưa xác nhận.
- COMPENSATION_RUNNING: worker đang thực thi/retry.
- COMPENSATION_COMPLETED: đã xác nhận tác động bù.
- COMPENSATION_FAILED: không thể hoàn tất tự động; cần hành động.
- RECONCILIATION_REQUIRED: kết quả không rõ, thường gặp với thanh toán.

Không chuyển Order sang CANCELLED chỉ vì đã gửi một command release trong khi chưa có bằng chứng inventory đã release, nếu business contract yêu cầu xác nhận đó. Cân nhắc **forward recovery** khi đảo ngược không còn phù hợp, ví dụ shipment đã qua bước không thể hủy.

## 15. @TransactionalEventListener không thay thế DLQ

Spring hỗ trợ listener gắn với phase transaction:

~~~java
// Snippet minh họa trong Spring bean.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderCommit(OrderPlaced event) {
    // Chỉ xử lý sau commit thành công của transaction nguồn.
}
~~~

Các phase gồm BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, AFTER_COMPLETION. Mặc định AFTER_COMMIT; nếu không có transaction, listener thường không được gọi khi fallbackExecution=false.

Nhưng **AFTER_COMMIT không phải durable queue**. Một process có thể chết sau commit nguồn trước khi callback hoàn thành, và Spring Application Events thuần không tự phát lại. Cần outbox/broker nếu yêu cầu khôi phục sau crash.

Khi listener sau commit cần ghi thêm DB, tài nguyên cũ có thể vẫn bound trong giai đoạn completion; thường cần một **transaction mới** (ví dụ một service @Transactional(propagation = REQUIRES_NEW) gọi qua proxy) hoặc đặt công việc cần atomicity vào transaction gốc.

Không copy TransactionSynchronizationManager sang worker để “mang transaction cũ” khi dùng @Async.

## 16. Phân biệt các định danh để chống lặp

| ID | Phạm vi và cách dùng |
| --- | --- |
| eventId | Một event occurrence gốc, giữ qua redelivery |
| deliveryId | Định danh một lần giao qua broker; có thể thay đổi |
| correlationId | Gắn toàn bộ workflow/saga |
| causationId | Event/command trực tiếp gây ra event mới |
| aggregateId | Đối tượng nghiệp vụ |
| compensationActionId | Một yêu cầu bù, giữ nguyên khi retry |
| externalIdempotencyKey | Khóa chống trùng tại API đối tác |

Nếu mỗi retry tự tạo một eventId mới, consumer dedup theo eventId sẽ coi chúng là các sự kiện khác nhau. Ngược lại, compensation là **một intent nghiệp vụ mới**: nên có actionId/eventId riêng nhưng liên kết original event bằng causationId/correlationId.

Cùng một event có thể được **nhiều consumers** xử lý hợp lệ; processed-events store thường dùng khóa (consumerName, eventId), không nên dùng eventId toàn cục để chặn mọi consumer khác.

## 17. Concurrency và thứ tự

Ví dụ race:

~~~text
Consumer A nhận PaymentCaptured(order-17)
Consumer B nhận CancelOrder(order-17)
~~~

Nếu cả hai cùng xử lý song song, thứ tự message đến không đủ để đảm bảo trạng thái cuối. Dùng:

- State machine và transition có precondition.
- Optimistic locking hoặc khóa database phù hợp.
- Unique constraint cho event/action ID.
- Partition/serialize theo aggregateId khi cần order.
- Saga state/version bền vững.
- Kiểm tra expectedState trước mỗi side effect quan trọng.

Một synchronized block trong một JVM **không có hiệu lực giữa nhiều instances**. Demo in-memory ở mục 7 chỉ minh họa flow một thread.

## 18. Bảo mật của DLQ và công cụ redrive

Dead-letter records có thể chứa payload, headers, thông tin cá nhân, số tài khoản hoặc lỗi từ hệ thống ngoài. Cần:

- Quyền **xem DLQ** và quyền **redrive/sửa payload** riêng biệt.
- Redaction tokens, bí mật và dữ liệu nhạy cảm.
- Retention/deletion policy phù hợp.
- Audit người phê duyệt, sửa event, redrive và đóng record.
- Validate schema và authorization trước replay.
- Tránh lưu nguyên stack trace nhạy cảm hoặc headers không giới hạn.
- Hạn chế tự động refund/cancel theo giá trị lỗi có thể bị attacker điều khiển.

DLQ là một phần của hệ thống vận hành, không phải kho dữ liệu công khai hoặc API tự do phát lại mọi command.

## 19. Quan sát và cảnh báo

| Metric gợi ý | Ý nghĩa |
| --- | --- |
| consumer.processed / failed | Tổng số xử lý thành công/thất bại |
| retry.attempts | Số attempts theo loại lỗi |
| retry.age | Tuổi message/độ trễ retry |
| dlq.depth | Số message còn chờ giải quyết |
| dlq.oldest_age | Entry lâu nhất chưa được xử lý |
| dlq.redrive.success / failed | Chất lượng quy trình replay |
| compensation.pending / failed | Workflow chưa được đưa về trạng thái an toàn |
| compensation.duration | Thời gian từ lỗi tới hoàn tất bù |
| duplicate.skipped | Tác động trùng bị chặn |
| reconciliation.pending | Business result còn mơ hồ |

Đây là **tên metric gợi ý**, không phải danh sách được Spring Framework tự động phát ra đầy đủ.

Nên alert dựa trên oldest age, tỉ lệ lỗi, compensation pending và hậu quả nghiệp vụ, không chỉ tổng DLQ depth. Trong metrics, tránh gắn eventId/orderId vào labels có cardinality cao; đưa ID vào structured logs/traces.

Runbook tối thiểu: nhận diện event và consumer, phân loại lỗi, xem business state, kiểm tra compensation, quyết định retry/reconcile/manual approval, redrive có rate limit, xác minh side effect rồi cập nhật trạng thái DLQ.

## 20. Kiểm thử độ tin cậy

### Retry/DLQ

- Lỗi transient N-1 lần rồi thành công ở N: không sinh dead-letter.
- Luôn lỗi: giới hạn attempts đúng policy; DLQ giữ original ID và errorCode.
- Permanent failure: không retry vô ích.
- Publish DLT thất bại: không ACK source theo nhầm lẫn khiến message mất.
- Nhiều retries dưới tải: không gây retry storm hoặc queue vô hạn.

### Compensation

- Payment fail sau reserve: inventory release đúng **một lần**.
- Duplicate compensationActionId: không side effect lần hai.
- Order PAID/SHIPPED không bị cancellation cũ hủy sai.
- Compensation fail: state PENDING/FAILED và có retry/escalation.
- Timeout khi refund: query trạng thái trước khi retry với cùng key.
- Redrive event sau compensation: không tự làm sống lại workflow cũ.

### Crash/concurrency

- Crash sau commit state nhưng trước publish: outbox còn record.
- Crash sau broker publish nhưng trước mark SENT: duplicate được consumer xử lý idempotent.
- Crash sau external API thành công nhưng trước ACK: outcome query hoặc idempotency key ngăn side effect trùng.
- Hai workers trên cùng aggregate: transaction/unique/version chống race.
- Saga đang bù mà service restart: compensation intent còn và worker có thể tiếp tục.

### Kiểm thử Spring

- @EventListener đồng bộ có thể lan exception về publisher.
- @Async @EventListener không có durable retry; test completion và lỗi worker riêng.
- @TransactionalEventListener(AFTER_COMMIT) không chạy khi transaction rollback; event ngoài transaction mặc định bị bỏ.
- Với Spring Kafka/RabbitMQ, phải test broker ACK/retry/DLQ bằng test integration phù hợp; không coi Map in-memory là chứng minh production.

## 21. Những sai lầm phổ biến

| Hiểu sai | Hậu quả | Cách đúng |
| --- | --- | --- |
| “Có @EventListener là có DLQ” | Event mất khi process chết | Chọn broker/storage bền vững |
| “@Async tự retry sau restart” | Queue in-memory mất | Outbox/durable messaging |
| “Retry vô hạn cho mọi lỗi” | Storm, tăng phí và backlog | Bounded retry, jitter, classifier |
| “DLQ nào cũng phải hủy order” | Compensation sai nghiệp vụ | Quyết định dựa business state |
| “Đã gửi RefundRequested = đã hoàn tiền” | Trạng thái sai | Xác nhận RefundCompleted/outcome |
| “Compensation là rollback phân tán” | Mất tính nhất quán | Local transactions + saga |
| “Timeout = chưa charge” | Charge trùng | Idempotency key và reconciliation |
| “Mỗi lần retry cấp eventId mới” | Dedup vô hiệu | Giữ original eventId |
| “Check rồi insert không cần transaction” | Race giữa consumers | Unique constraint + transaction |
| “Redrive toàn bộ DLQ sau deploy” | Replay sai business state | Audit, rate limit, approval |
| “Compensation không thể lỗi” | Saga mắc kẹt không ai biết | Durable retry và escalation |
| “AFTER_COMMIT bảo đảm replay” | Vẫn có crash gap | Outbox/broker |
| “DLQ lưu mọi stack trace/payload” | Rò thông tin nhạy cảm | RBAC, redact, retention |

## 22. Checklist triển khai

1. Đây là **event in-memory** hay **message bền vững** đi qua broker?
2. Có phân loại transient, permanent, ambiguous outcome không?
3. Retry policy có max attempts, timeout, backoff, jitter và deadline không?
4. Khi retry cạn, DLQ có thật sự lưu bền vững, và publish DLT thất bại xử lý ra sao?
5. DLQ envelope có original eventId, aggregateId, schema version, attempts và correlation không?
6. Có owner và runbook redrive DLQ không?
7. Có quyết định rõ **dead-letter không đồng nghĩa compensation** không?
8. Compensation action có ID ổn định, state guard và idempotency không?
9. Nếu compensation thất bại có đường retry/escalation/alert không?
10. Có outbox/inbox hoặc kiến trúc tương đương cho crash recovery không?
11. Redrive có kiểm tra trạng thái hiện tại và tránh side effect trùng không?
12. Đã test concurrency, duplicate, crash, ambiguous payment và compensation fail chưa?

**Kết luận:** Dead-letter giữ thông tin về công việc chưa thể xử lý; compensation là **một hành động nghiệp vụ có điều kiện** để đưa workflow về trạng thái an toàn. Trong Spring Application Events nội bộ, không có sẵn DLQ/durable retries. Với hệ thống quan trọng, hãy kết hợp **bounded retry, broker/outbox, idempotent consumer, saga state, compensation bền vững, redrive có kiểm soát và observability**, thay vì chỉ thêm @Async hoặc hy vọng callback AFTER_COMMIT không bao giờ bị mất.

## Tài liệu chính thức

- Spring Framework 6.2 — Application Events: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 — ApplicationEventPublisher Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Kafka — Error handling, retries, DefaultErrorHandler và DLT: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- Spring AMQP — RabbitMQ messaging: https://docs.spring.io/spring-amqp/reference/
- RabbitMQ — Dead Letter Exchanges: https://www.rabbitmq.com/docs/dlx
