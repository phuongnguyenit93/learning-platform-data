# Phân biệt sự kiện ApplicationContext và thông điệp liên tiến trình

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích sự kiện của Spring ApplicationContext được phát và nhận như thế nào.
- Phân biệt sự kiện nội bộ trong một ứng dụng với thông điệp đi qua ranh giới tiến trình.
- Chọn đúng cơ chế cho giao tiếp giữa các bean, giữa các dịch vụ và cho xử lý nền.
- Nhận biết ảnh hưởng của transaction, bất đồng bộ, retry, duplicate và độ bền thông điệp.
- Thiết kế event contract đủ ổn định khi nhiều dịch vụ cùng sử dụng.

## 1. Hai cơ chế giải quyết hai phạm vi khác nhau

**Sự kiện ApplicationContext** là cơ chế thông báo giữa các bean được quản lý bởi Spring trong cùng một ApplicationContext. Một bean phát sự kiện qua ApplicationEventPublisher; Spring chuyển sự kiện đến các listener phù hợp trong context. Cơ chế này dựa trên Observer pattern và chủ yếu phục vụ giao tiếp nội bộ trong một ứng dụng.

**Thông điệp liên tiến trình** là dữ liệu được gửi từ một tiến trình hoặc dịch vụ sang một tiến trình khác qua một ranh giới giao tiếp. Ranh giới đó thường là message broker hoặc middleware như RabbitMQ, Kafka, JMS broker; cũng có thể là một giao thức giao tiếp khác. Hai phía có thể chạy ở các JVM, container hoặc máy chủ khác nhau và có vòng đời triển khai độc lập.

Sự khác biệt cốt lõi nằm ở ranh giới giao tiếp:

~~~text
Sự kiện nội bộ:
OrderService
    -> ApplicationEventPublisher
    -> ApplicationEventMulticaster
    -> @EventListener trong cùng ApplicationContext

Thông điệp liên tiến trình:
Service A
    -> client gửi message
    -> broker / transport qua mạng
    -> queue hoặc topic
    -> consumer trong Service B
~~~

Một sự kiện nghiệp vụ như OrderPlaced có thể được phát nội bộ bằng ApplicationContext hoặc được đóng gói thành thông điệp gửi sang dịch vụ khác. Tên gọi của sự kiện không quyết định phạm vi truyền tải; cơ chế gửi và nhận mới quyết định phạm vi đó.

Cũng cần phân biệt **event** và **command**:

- Event mô tả một sự việc đã xảy ra, thường đặt tên ở thì quá khứ: OrderPlaced, PaymentReceived.
- Command yêu cầu một bên thực hiện hành động: PlaceOrder, CapturePayment.
- Message là đơn vị dữ liệu được truyền đi. Một message có thể mang event hoặc command.

## 2. Sự kiện trong Spring ApplicationContext hoạt động ra sao?

Spring cung cấp giao diện ApplicationEventPublisher để phát sự kiện. Bean có thể nhận giao diện này qua dependency injection và gọi publishEvent(...). Từ Spring Framework 4.2, đối tượng được phát không bắt buộc phải kế thừa ApplicationEvent; một POJO hoặc Java record cũng có thể được dùng làm event.

Một bean listener có thể triển khai ApplicationListener<T> hoặc khai báo phương thức với @EventListener. Spring đăng ký listener khi tạo bean và chọn listener dựa trên kiểu sự kiện. Có thể dùng @Order để điều chỉnh thứ tự gọi các listener đồng bộ.

Các đặc điểm cần nhớ:

1. **Phạm vi:** listener thuộc ApplicationContext nhận sự kiện được phát trong context đó. Nếu ứng dụng dùng context cha-con, sự kiện phát từ context con được chuyển tiếp lên context cha; sự kiện ở context cha không tự động được phát xuống các context con. Điều này vẫn là giao tiếp trong một cây context của ứng dụng, không phải truyền qua mạng.
2. **Mặc định đồng bộ:** SimpleApplicationEventMulticaster mặc định gọi listener trên thread đang phát sự kiện. publishEvent(...) vì vậy thường chờ các listener đồng bộ hoàn tất trước khi trả về.
3. **Ảnh hưởng lỗi:** trong chế độ đồng bộ mặc định, exception từ listener có thể truyền ngược về nơi phát và làm dừng lượt multicast hiện tại. Có thể cấu hình ErrorHandler để xử lý lỗi theo chính sách riêng.
4. **Transaction:** listener đồng bộ chạy trong cùng luồng xử lý và có thể tham gia transaction đang tồn tại của publisher. Đây là một đặc điểm hữu ích nhưng cũng có nghĩa listener chậm có thể kéo dài transaction.
5. **Không có lưu trữ bền:** ApplicationContext không tự ghi event vào database hay broker. Nếu tiến trình dừng trước khi listener xử lý xong, event không có hàng đợi bền để phát lại.

### Ví dụ hoàn chỉnh: phát một event nội bộ

Ví dụ dùng Java 17 và Spring Framework 6.2.9. OrderService phát một record sau khi mô phỏng thao tác tiếp nhận đơn hàng. AuditListener nhận event trong cùng ApplicationContext.

Cấu trúc thư mục:

~~~text
application-event-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ApplicationEventDemo.java
~~~

Tệp pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>application-event-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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

Tệp src/main/java/demo/ApplicationEventDemo.java:

~~~java
package demo;

import java.math.BigDecimal;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ApplicationEventDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            context.getBean(OrderService.class)
                    .placeOrder("ORD-1001", new BigDecimal("125.00"));
        }
    }
}

@Configuration(proxyBeanMethods = false)
class AppConfig {

    @Bean
    OrderService orderService(ApplicationEventPublisher publisher) {
        return new OrderService(publisher);
    }

    @Bean
    AuditListener auditListener() {
        return new AuditListener();
    }
}

record OrderPlacedEvent(String orderId, BigDecimal total) {}

class OrderService {

    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void placeOrder(String orderId, BigDecimal total) {
        System.out.println("Order accepted: " + orderId);
        publisher.publishEvent(new OrderPlacedEvent(orderId, total));
    }
}

class AuditListener {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        System.out.printf(
                "Audit: order=%s, total=%s%n",
                event.orderId(),
                event.total()
        );
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.5.0:java -Dexec.mainClass=demo.ApplicationEventDemo
~~~

Kết quả stdout:

~~~text
Order accepted: ORD-1001
Audit: order=ORD-1001, total=125.00
~~~

Hai dòng xuất hiện theo thứ tự trên vì listener mặc định chạy đồng bộ trên thread phát event. Ví dụ chỉ mô phỏng thao tác nghiệp vụ, chưa kết nối database. Điểm cần quan sát là OrderService chỉ phụ thuộc vào ApplicationEventPublisher; nó không cần biết AuditListener tồn tại.

## 3. Thông điệp liên tiến trình trong hệ sinh thái Spring

Khi hai tiến trình cần trao đổi, dữ liệu phải đi qua một transport có thể truy cập từ cả hai phía. Với kiến trúc message-driven, một broker thường đảm nhiệm việc định tuyến và lưu giữ message theo cấu hình.

Một luồng RabbitMQ điển hình:

1. Service A tạo payload theo một contract đã thống nhất.
2. RabbitTemplate gửi payload đến exchange cùng routing key.
3. Exchange định tuyến message đến queue phù hợp.
4. Broker giữ message theo chính sách queue và cấu hình lưu trữ.
5. Service B nhận message qua listener container và phương thức @RabbitListener.
6. Consumer xử lý, sau đó message được acknowledge hoặc được xử lý theo chính sách retry/reject đã cấu hình.

### Ví dụ gửi và nhận bằng Spring AMQP

Đây là hai đoạn minh họa, không phải ứng dụng RabbitMQ hoàn chỉnh. Ứng dụng thực tế cần dependency Spring AMQP, ConnectionFactory, RabbitTemplate, exchange, queue, binding và listener container. Có thể khai báo hạ tầng bằng Spring AMQP hoặc dùng auto-configuration của Spring Boot.

Phía gửi:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

class OrderEventPublisher {

    private final RabbitTemplate rabbitTemplate;

    OrderEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishOrderPlaced() {
        String payload = """
                {"eventId":"evt-1001","eventType":"OrderPlaced",
                 "schemaVersion":1,"orderId":"ORD-1001","total":125.00}
                """;

        rabbitTemplate.convertAndSend(
                "orders.exchange",
                "order.placed",
                payload
        );
    }
}
~~~

Phía nhận:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
class OrderProjectionListener {

    @RabbitListener(queues = "order-events")
    public void onMessage(String payload) {
        System.out.println("Received order event: " + payload);
    }
}
~~~

Trong ví dụ, exchange orders.exchange phải được bind đến queue order-events bằng routing key order.placed. String payload được dùng để minh họa contract truyền qua transport; trong hệ thống thực tế, producer và consumer cần thống nhất định dạng, encoding, schema và chính sách tương thích.

Các lựa chọn thường gặp:

- **Spring AMQP / RabbitMQ:** RabbitTemplate gửi message đến exchange; @RabbitListener nhận message từ queue. Phù hợp với routing linh hoạt, queue và xử lý nền.
- **Spring for Apache Kafka:** KafkaTemplate gửi record đến topic; consumer đọc theo partition và quản lý offset. Hữu ích cho event stream, retention và khả năng replay.
- **Spring JMS:** JmsTemplate gửi đến queue hoặc topic của JMS provider; listener container nhận message. Phù hợp khi hệ thống dùng chuẩn JMS.
- **Spring Integration:** cung cấp Message, MessageChannel, adapter và gateway để kết nối các hệ thống. Cần phân biệt abstraction với transport: một MessageChannel trong bộ nhớ không tự biến thành giao tiếp liên tiến trình. Phải có adapter hoặc transport thực sự như JMS, Kafka, AMQP, MQTT...

Spring Framework không tự biến ApplicationEventPublisher thành message broker. Nếu một listener nhận ApplicationContext event rồi gửi tiếp bằng RabbitTemplate hoặc KafkaTemplate, chính listener đó đang đóng vai trò bridge từ event nội bộ sang hệ thống messaging.

## 4. So sánh trực tiếp

| Tiêu chí | ApplicationContext event | Thông điệp liên tiến trình |
|---|---|---|
| Ranh giới | Các bean trong cùng ApplicationContext hoặc cây context liên quan | Giữa các process/service qua transport |
| Thành phần phát | ApplicationEventPublisher | RabbitTemplate, KafkaTemplate, JmsTemplate hoặc client tương ứng |
| Thành phần nhận | @EventListener hoặc ApplicationListener | @RabbitListener, Kafka listener, JMS listener... |
| Vận chuyển | Spring gọi listener trong ứng dụng | Network, broker hoặc middleware |
| Payload | Có thể là Java object hoặc record trong cùng ứng dụng | Contract cần serialize/deserialize, thường là JSON, Avro, Protobuf hoặc định dạng thống nhất |
| Độ trễ | Thường thấp vì không qua mạng | Có thêm network và broker; có thể xử lý bất đồng bộ |
| Lưu trữ | Không có durable queue mặc định | Có thể lưu bền nếu broker và message được cấu hình phù hợp |
| Khi consumer lỗi | Listener đồng bộ có thể làm lỗi truyền ngược về publisher; async cần cơ chế xử lý riêng | Broker có thể redeliver, retry hoặc chuyển DLQ tùy cấu hình |
| Duplicate | Không có broker redelivery; logic ứng dụng vẫn có thể phát event nhiều lần | Redelivery hoặc retry có thể tạo duplicate; consumer cần idempotency |
| Thứ tự | Có thể điều khiển thứ tự listener đồng bộ bằng @Order | Phụ thuộc queue, partition, số consumer và cấu hình broker |
| Transaction | Listener đồng bộ có thể chạy trong transaction của publisher | Transaction giữa database và broker cần thiết kế riêng; không mặc định là một transaction nguyên tử |
| Mở rộng | Phụ thuộc vòng đời và tài nguyên của ứng dụng chứa context | Consumer có thể triển khai, scale và khởi động độc lập |
| Phù hợp | Phối hợp nội bộ giữa các bean | Tích hợp dịch vụ, xử lý nền, buffering và trao đổi giữa các hệ thống |

Không nên diễn giải bảng thành quy tắc tuyệt đối về hiệu năng hay độ tin cậy. Messaging không mặc định bền vững hoặc exactly-once; kết quả phụ thuộc broker, topology, acknowledgement, persistence, retry và cách consumer cập nhật dữ liệu.

## 5. Đồng bộ, bất đồng bộ và transaction

### @Async không có nghĩa là liên tiến trình

Có thể đặt @Async trên phương thức @EventListener và bật xử lý bất đồng bộ bằng @EnableAsync. Khi đó listener có thể chạy trên executor thread khác. Tuy nhiên:

- Listener vẫn thuộc ứng dụng và ApplicationContext hiện tại.
- Không có broker, durable queue hay khả năng replay tự động.
- Exception từ async listener không truyền ngược về publisher như lời gọi đồng bộ; cần cấu hình AsyncUncaughtExceptionHandler hoặc cơ chế ghi nhận lỗi phù hợp.
- ThreadLocal, logging context và transaction context không tự được truyền sang thread khác.
- Không nên giả định các listener async hoàn tất theo thứ tự chúng được phát.

Nếu mục tiêu chỉ là tránh giữ thread gọi lâu, async listener có thể hữu ích. Nếu cần giao tiếp giữa các tiến trình hoặc cần lưu message để xử lý lại, phải dùng một transport phù hợp.

### Dùng @TransactionalEventListener khi kết quả phụ thuộc transaction

Một listener thông thường có thể chạy ngay tại thời điểm publishEvent(...), kể cả khi transaction của nghiệp vụ chưa commit. Nếu listener cần phản ứng sau khi transaction thành công, dùng @TransactionalEventListener:

~~~java
@Component
class OrderSearchIndexer {

    @TransactionalEventListener
    public void afterOrderCommitted(OrderPlacedEvent event) {
        // Cập nhật chỉ mục sau khi transaction commit.
    }
}
~~~

Mặc định listener được gắn với phase AFTER_COMMIT. Có thể chọn BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK hoặc AFTER_COMPLETION qua thuộc tính phase. Nếu không có transaction đang hoạt động, listener mặc định không được gọi; fallbackExecution = true thay đổi hành vi đó và chỉ nên bật khi có chủ đích.

Điểm quan trọng: AFTER_COMMIT không biến event thành dữ liệu bền vững. Có một khoảng thời gian giữa lúc database commit và lúc listener hoàn tất. Nếu process dừng trong khoảng đó, công việc hậu commit có thể bị mất.

### Transactional Outbox cho tích hợp cần độ tin cậy

Khi một giao dịch vừa cập nhật database vừa phải phát message sang broker, việc ghi database và gửi message bằng hai thao tác độc lập tạo ra tình huống lỗi:

- Database commit thành công nhưng gửi message thất bại.
- Message đã gửi nhưng transaction database rollback hoặc kết quả commit không như mong đợi.
- Process dừng giữa hai thao tác.

Transactional Outbox giải quyết khoảng trống này bằng cách:

1. Trong cùng một transaction database, cập nhật dữ liệu nghiệp vụ và ghi một bản ghi vào bảng outbox.
2. Một publisher nền hoặc CDC đọc các bản ghi outbox và gửi chúng đến broker.
3. Publisher ghi nhận trạng thái đã gửi hoặc dùng checkpoint phù hợp; lỗi có thể được retry.
4. Consumer xử lý idempotent dựa trên eventId để duplicate không tạo tác động nghiệp vụ lặp lại.

Outbox không tự đảm bảo mọi thành phần đều exactly-once. Nó giúp bảo đảm ý định phát message được lưu cùng transaction nghiệp vụ; publisher và consumer vẫn phải xử lý retry, duplicate và trạng thái lỗi.

## 6. Độ bền, acknowledgement, retry và duplicate

Với broker, cần cấu hình rõ ràng thay vì giả định message sẽ luôn tồn tại:

- **Durability:** queue/topic và message cần cấu hình persistence phù hợp; khả năng lưu bền còn phụ thuộc loại broker, replication và chính sách lưu trữ.
- **Publisher confirmation:** producer cần biết broker đã xác nhận việc nhận message ở mức nào. Việc lời gọi gửi không ném exception chưa đủ để kết luận message đã đến đúng queue.
- **Consumer acknowledgement:** chỉ acknowledge khi xử lý đạt trạng thái mong muốn. Acknowledge quá sớm có thể làm mất message nếu consumer dừng trước khi hoàn tất tác động nghiệp vụ.
- **Retry:** giới hạn số lần thử, khoảng chờ và phân loại lỗi tạm thời với lỗi không thể khắc phục. Retry vô hạn có thể làm nghẽn queue.
- **Dead-letter queue (DLQ):** đưa message lỗi kéo dài sang nơi riêng để điều tra và xử lý lại có kiểm soát.
- **Idempotency:** dùng eventId hoặc khóa nghiệp vụ duy nhất để một message được xử lý lại mà không tạo tác động trùng lặp.
- **Ordering:** chỉ dựa vào thứ tự trong phạm vi mà broker bảo đảm. Ví dụ Kafka bảo toàn thứ tự trong một partition; nhiều partition hoặc consumer song song có thể xử lý hoàn tất theo thứ tự khác.
- **Schema evolution:** thêm schemaVersion, giữ tương thích ngược khi có thể, và tránh đổi tên hoặc đổi ý nghĩa field mà không có kế hoạch migration.

Đừng mặc định hệ thống có exactly-once end-to-end. Một broker có thể cung cấp một số bảo đảm giao nhận trong phạm vi nhất định, nhưng việc cập nhật database, gọi API ngoài và xử lý side effect vẫn có thể bị lặp. Thiết kế consumer idempotent là yêu cầu thực tế trong nhiều hệ thống.

## 7. Chọn cơ chế nào?

| Nhu cầu | Hướng lựa chọn |
|---|---|
| Một bean cần thông báo cho một vài bean khác trong cùng ứng dụng | ApplicationContext event |
| Muốn tách listener khỏi publisher nhưng vẫn chấp nhận vòng đời và lỗi của cùng ứng dụng | ApplicationContext event; cân nhắc listener đồng bộ hay async |
| Chỉ cần chạy tác vụ nền trong cùng ứng dụng | Executor, @Async hoặc event listener async |
| Hai service triển khai độc lập cần trao đổi | Message broker hoặc giao thức liên tiến trình |
| Consumer có thể tạm dừng, cần buffering, retry hoặc replay | Broker với persistence, acknowledgement và retention được cấu hình |
| Nhiều consumer độc lập cần nhận cùng một event | Pub/sub qua topic hoặc exchange phù hợp |
| Cần yêu cầu một service thực hiện thao tác và chờ kết quả ngay | Gọi service trực tiếp qua API như HTTP/gRPC; dùng request-reply messaging khi tính bất đồng bộ phù hợp |
| Cập nhật database và phát integration event phải nhất quán | Transactional Outbox hoặc giải pháp CDC tương đương |

Một quy tắc thực tế: bắt đầu bằng ApplicationContext event khi ranh giới chỉ nằm giữa các bean trong cùng ứng dụng. Chuyển sang messaging khi consumer cần độc lập về process, deployment, khả năng chịu lỗi, buffering hoặc mở rộng.

## 8. Lỗi thiết kế thường gặp

1. **Cho rằng @Async tạo ra message bền vững.** Nó chỉ chuyển việc xử lý sang executor; khi process dừng, task đang chờ không tự được khôi phục.
2. **Dùng ApplicationContext event để gọi một dịch vụ từ xa.** Event publisher không biết địa chỉ mạng, retry, authentication hoặc contract của dịch vụ đích. Cần một client hoặc bridge có transport rõ ràng.
3. **Đưa entity hoặc object nội bộ vào contract liên tiến trình.** Hai dịch vụ có thể khác phiên bản code và mô hình dữ liệu. Nên dùng DTO/event contract độc lập, có schema và version.
4. **Đặt xử lý nặng trong listener đồng bộ.** Publisher bị chặn và transaction có thể kéo dài. Chuyển sang tác vụ nền hoặc broker nếu phù hợp.
5. **Giả định @TransactionalEventListener bảo đảm phát message.** Nó chỉ điều chỉnh thời điểm listener chạy theo transaction; không lưu event bền vững.
6. **Retry mà không có idempotency.** Một message được giao lại có thể tạo đơn hàng, thanh toán hoặc email trùng lặp.
7. **Không theo dõi message lỗi.** Cần log có eventId/correlationId, metrics, retry policy và DLQ để tìm nguyên nhân.
8. **Dùng message contract thay đổi tùy tiện.** Producer và consumer có thể triển khai ở thời điểm khác nhau; cần quy tắc tương thích schema và kiểm thử contract.

## 9. Checklist trước khi triển khai

- [ ] Xác định consumer nằm trong cùng ApplicationContext hay process độc lập.
- [ ] Xác định event là thông báo sự việc đã xảy ra hay command yêu cầu hành động.
- [ ] Chọn đồng bộ, executor async hay broker dựa trên yêu cầu thực tế.
- [ ] Xác định hành vi khi listener hoặc consumer lỗi.
- [ ] Nếu dùng broker, cấu hình durability, acknowledgement, retry, DLQ và publisher confirmation phù hợp.
- [ ] Đặt eventId/correlationId và thiết kế consumer idempotent.
- [ ] Xác định yêu cầu transaction; cân nhắc Outbox khi cần đồng bộ database với message.
- [ ] Định nghĩa schema, version và chính sách tương thích.
- [ ] Có log, metrics và cảnh báo cho message bị lỗi hoặc tồn đọng.

## 10. Kết luận

ApplicationContext event là cơ chế Observer nội bộ của Spring, thuận tiện để giảm phụ thuộc trực tiếp giữa các bean trong cùng ứng dụng. Thông điệp liên tiến trình là cơ chế giao tiếp qua transport, phù hợp khi các thành phần có thể chạy và triển khai độc lập. @Async không thay thế broker; @TransactionalEventListener không thay thế outbox; broker cũng không tự cung cấp exactly-once cho toàn bộ tác động nghiệp vụ. Hãy chọn dựa trên ranh giới process, yêu cầu transaction, độ bền, khả năng retry và mức độ độc lập giữa producer với consumer.

## Tài liệu tham khảo chính thức

- [Spring Framework Reference: Additional Capabilities of the ApplicationContext](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html) — ApplicationEventPublisher, ApplicationListener, @EventListener và cơ chế multicast.
- [Spring Framework Reference: Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) — @TransactionalEventListener và các transaction phase.
- [Spring Framework Javadoc: SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html) — executor, xử lý đồng bộ và ErrorHandler.
- [Spring AMQP Reference: AmqpTemplate](https://docs.spring.io/spring-amqp/reference/amqp/template.html) — gửi message, retry, publisher confirms và returns.
- [Spring Integration Reference: Core Messaging](https://docs.spring.io/spring-integration/reference/core.html) — Message, MessageChannel, adapter và enterprise integration patterns.
- [Spring Integration Reference: JMS Support](https://docs.spring.io/spring-integration/reference/jms.html) — adapter và gateway cho giao tiếp JMS.
