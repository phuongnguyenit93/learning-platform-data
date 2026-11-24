# Producer chỉ phát và cách xác định ranh giới giao dịch

Một ứng dụng Spring Cloud Stream có thể chỉ làm nhiệm vụ phát message: một Supplier tạo sự kiện theo lịch, REST controller gọi StreamBridge khi nhận yêu cầu, hoặc một service nghiệp vụ gửi nhiều record đến Kafka. Khi chỉ phát một record trong mỗi lần gọi, producer thông thường có thể đã đáp ứng yêu cầu nếu ứng dụng chờ kết quả gửi và cấu hình mức xác nhận phù hợp. Kafka transaction trở nên hữu ích khi nhiều lần gửi có quan hệ với nhau và cần được công bố như một đơn vị nguyên tử.

Điểm cần xác định trước khi bật transaction là **ranh giới giao dịch**: những record nào phải cùng commit hoặc cùng bị abort? Với producer-only, ranh giới đó thường là một phương thức nghiệp vụ, một batch sự kiện hoặc một thao tác phát đến nhiều topic. Spring Cloud Stream Kafka Binder cung cấp transactional producer; Spring Kafka cung cấp KafkaTransactionManager và TransactionTemplate để bao quanh các lần gửi bằng một transaction rõ ràng.

## 1. Producer-only transaction là gì?

Producer-only transaction là giao dịch Kafka do phía ứng dụng phát message khởi tạo, không bắt đầu từ một consumer listener. Trong transaction, producer có thể gửi một hoặc nhiều record đến một hay nhiều topic thuộc cùng Kafka cluster. Khi transaction commit, các record được công bố như một đơn vị; khi transaction abort, các record của giao dịch đó không được consumer read_committed nhìn thấy.

Ví dụ, một thao tác chốt đơn hàng cần phát đồng thời:

- OrderConfirmed đến topic orders.events.
- InventoryReservationRequested đến topic inventory.commands.
- InvoiceRequested đến topic billing.commands.

Nếu ba record đại diện cho cùng một quyết định nghiệp vụ, ứng dụng có thể muốn tất cả cùng xuất hiện hoặc không record nào xuất hiện. Producer-only transaction cho phép nhóm các lần gửi Kafka đó vào cùng một transaction.

~~~text
Ứng dụng producer
       |
       v
beginTransaction
       |
       +---- send orders.events
       |
       +---- send inventory.commands
       |
       +---- send billing.commands
       |
       v
   commitTransaction
       |
       v
Consumer read_committed thấy cả nhóm record
~~~

Nếu một bước gửi hoặc logic nghiệp vụ ném exception trước commit, transaction có thể rollback:

~~~text
beginTransaction
       |
       +---- send orders.events
       |
       +---- send inventory.commands
       |
       +---- lỗi ở bước tiếp theo
       |
       v
   abortTransaction
       |
       v
Consumer read_committed không thấy record đã abort
~~~

Transaction bảo đảm tính nguyên tử của các lần ghi Kafka nằm trong cùng giao dịch. Nó không tự bao gồm cập nhật database, gọi HTTP API, gửi email hoặc thao tác ở broker khác.

## 2. Khi nào cần transaction và khi nào không?

Không nên bật transaction chỉ vì ứng dụng có dùng Kafka. Hãy chọn theo yêu cầu của thao tác phát:

| Tình huống | Hướng xử lý thường phù hợp |
|---|---|
| Một lần gọi chỉ phát một record độc lập | Producer gửi đồng bộ nếu cần chờ kết quả; cấu hình acks theo durability |
| Supplier phát một record mỗi chu kỳ | Thường không cần transaction; cân nhắc synchronous producer |
| REST request phát một record | Thường không cần transaction nhiều record |
| Một thao tác phát nhiều record phải cùng xuất hiện hoặc cùng bị hủy | Producer-only transaction |
| Một thao tác phát đến nhiều topic Kafka trong cùng cluster | Producer-only transaction nếu các binding dùng cùng transactional producer factory |
| Một thao tác vừa ghi Kafka vừa cập nhật database | Cần thiết kế đồng bộ transaction và xử lý lỗi commit; cân nhắc outbox |
| Consumer đọc, xử lý rồi phát output và commit offset cùng nhau | Consumer-initiated transaction; đây là ranh giới khác với producer-only |

Với một record duy nhất, transaction tạo thêm chi phí mở, commit và quản lý producer. Spring Cloud Stream Kafka Binder hỗ trợ sync: true để chờ kết quả gửi. Kết hợp với mức xác nhận Kafka phù hợp, cách này thường đủ khi chỉ cần biết lần gửi đơn lẻ đã được broker xác nhận.

Ví dụ cấu hình gửi đồng bộ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvent-out-0:
          destination: orders.events
      kafka:
        binder:
          required-acks: all
        bindings:
          orderEvent-out-0:
            producer:
              sync: true
~~~

sync: true khiến producer chờ kết quả gửi thay vì chỉ trả về sau khi đưa record vào luồng gửi bất đồng bộ. required-acks: all yêu cầu Kafka chờ các replica hiện nằm trong ISR xác nhận theo semantics của Kafka. Đây không phải transaction nhóm nhiều record; nó chỉ làm rõ kết quả của lần gửi.

## 3. Bật transactional producer trong Kafka Binder

Kafka Binder bật transactional producer khi có cấu hình transaction-id-prefix khác rỗng:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders.events
          content-type: application/json
      kafka:
        binder:
          brokers: localhost:9092
          transaction:
            transaction-id-prefix: ${INSTANCE_ID}-order-producer-
~~~

Trong ví dụ, INSTANCE_ID phải là giá trị duy nhất cho từng instance đang chạy, chẳng hạn mã pod hoặc mã tiến trình được nền tảng triển khai cấp. Nếu chạy nhiều instance với cùng prefix, producer có thể dùng trùng transactional.id; Kafka có thể fence producer cũ khi một producer khác khởi tạo cùng định danh. Với môi trường local một instance, có thể dùng prefix cố định; production cần giá trị duy nhất trên từng instance.

transaction-id-prefix yêu cầu binder tạo transactional producer factory. Kafka producer factory sinh các transactional.id cụ thể từ prefix và hậu tố quản lý nội bộ. Prefix phải đủ khác nhau giữa các instance đồng thời, đồng thời có độ dài phù hợp giới hạn cấu hình của Kafka.

Khi binder đã ở chế độ transactional, các producer binding dùng chung producer factory và các thuộc tính producer cần được cấu hình ở spring.cloud.stream.kafka.binder.transaction.producer.*. Các thuộc tính producer Kafka đặt riêng từng binding có thể bị bỏ qua trong chế độ này. Hãy đặt cấu hình dùng chung ở đúng phạm vi và kiểm tra tài liệu phiên bản binder đang sử dụng.

## 4. Một send không đồng nghĩa một transaction nghiệp vụ nhiều record

Một điểm dễ nhầm: chỉ bật transaction-id-prefix chưa đủ để gom nhiều lần gọi StreamBridge.send() thành một transaction chung.

Khi không có transaction Spring đang hoạt động, binder có thể mở và commit một transaction riêng cho từng lần gửi:

~~~java
for (int i = 0; i < 3; i++) {
    streamBridge.send("orderEvents-out-0", events.get(i));
}
~~~

Với cấu hình transactional binder nhưng không có transaction manager bao quanh vòng lặp, ba lần gửi có thể trở thành ba transaction riêng. Nếu lần thứ ba thất bại, hai lần trước có thể đã commit và consumer đã nhìn thấy chúng.

Muốn ba record là một đơn vị nguyên tử, cần:

1. Bật transactional producer bằng transaction-id-prefix.
2. Tạo KafkaTransactionManager từ chính transactional producer factory của Kafka Binder.
3. Dùng TransactionTemplate hoặc @Transactional để bao quanh toàn bộ các lần gửi.
4. Để exception thoát khỏi transaction callback hoặc đánh dấu rollback-only khi cần hủy giao dịch.

## 5. Lấy ProducerFactory từ Kafka Binder

Với producer-only transaction trong source application hoặc một thread tùy ý như @Scheduled, Kafka Binder yêu cầu ứng dụng lấy transactional producer factory và tạo KafkaTransactionManager từ factory đó.

~~~java
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.cloud.stream.binder.BinderFactory;
import org.springframework.cloud.stream.binder.kafka.KafkaMessageChannelBinder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.transaction.KafkaTransactionManager;
import org.springframework.messaging.MessageChannel;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
class KafkaProducerTransactionConfiguration {

    @Bean
    KafkaTransactionManager<byte[], byte[]> kafkaTransactionManager(
            BinderFactory binders) {

        KafkaMessageChannelBinder kafkaBinder =
                (KafkaMessageChannelBinder) binders.getBinder(
                        null, MessageChannel.class);

        ProducerFactory<byte[], byte[]> producerFactory =
                kafkaBinder.getTransactionalProducerFactory();

        return new KafkaTransactionManager<>(producerFactory);
    }

    @Bean
    TransactionTemplate kafkaTransactionTemplate(
            KafkaTransactionManager<byte[], byte[]> kafkaTransactionManager) {
        return new TransactionTemplate(kafkaTransactionManager);
    }
}
~~~

Ví dụ dùng null ở tên binder vì giả định ứng dụng chỉ cấu hình một binder. Nếu ứng dụng có nhiều binder, truyền đúng tên Kafka binder vào getBinder("kafka", MessageChannel.class) hoặc tên binder thực tế của hệ thống.

Điểm quan trọng nhất là KafkaTransactionManager phải dùng **cùng ProducerFactory mà Kafka Binder dùng cho output binding**. Nếu tạo một producer factory độc lập, StreamBridge có thể tiếp tục gửi bằng factory riêng của binder, không tham gia transaction đang được manager quản lý.

Khi bật transaction bằng thuộc tính của Spring Boot spring.kafka.producer.transaction-id-prefix, Spring Boot có thể tạo producer factory và transaction manager riêng. Trong ứng dụng Spring Cloud Stream dùng Kafka Binder, không nên mặc định manager tự cấu hình của Boot đang dùng cùng factory với binder. Hãy dùng spring.cloud.stream.kafka.binder.transaction.transaction-id-prefix và lấy factory trực tiếp từ binder như ví dụ.

## 6. Xác định ranh giới bằng TransactionTemplate

TransactionTemplate làm rõ phạm vi bắt đầu và kết thúc transaction trong mã. Ví dụ, một lệnh chốt đơn cần phát ba sự kiện liên quan:

~~~java
import java.util.List;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

record OrderEvent(String eventId, String orderId, String eventType) {}

@Service
class OrderBatchPublisher {

    private final StreamBridge streamBridge;
    private final TransactionTemplate kafkaTransactionTemplate;

    OrderBatchPublisher(
            StreamBridge streamBridge,
            TransactionTemplate kafkaTransactionTemplate) {
        this.streamBridge = streamBridge;
        this.kafkaTransactionTemplate = kafkaTransactionTemplate;
    }

    void publishAll(List<OrderEvent> events) {
        kafkaTransactionTemplate.executeWithoutResult(status -> {
            for (OrderEvent event : events) {
                boolean accepted = streamBridge.send(
                        "orderEvents-out-0", event);

                if (!accepted) {
                    throw new IllegalStateException(
                            "Kafka binding did not accept event " + event.eventId());
                }
            }
        });
    }
}
~~~

Khi callback hoàn tất bình thường, transaction manager commit giao dịch. Nếu send trả về false hoặc một thao tác trong callback ném exception, transaction callback kết thúc bất thường và Spring rollback transaction.

Giá trị true từ StreamBridge.send cho biết message đã được chấp nhận qua binding/channel. Nó không phải bằng chứng độc lập rằng broker đã commit transaction. Việc commit Kafka do transaction manager thực hiện sau khi callback hoàn tất; nếu cần kiểm tra kết quả gửi chi tiết, có thể bổ sung record metadata channel hoặc quan sát kết quả producer theo khả năng binder.

Không bắt exception rồi bỏ qua bên trong callback nếu nghiệp vụ yêu cầu rollback. Nếu cần bắt để ghi log, hãy ném lại exception hoặc gọi status.setRollbackOnly() để đánh dấu transaction không được commit.

## 7. Dùng @Transactional để nhóm nhiều lần gửi

Có thể dùng @Transactional thay cho TransactionTemplate. Phương thức được đánh dấu phải chạy qua Spring transaction proxy và transaction manager phải là KafkaTransactionManager dùng cùng producer factory của binder.

~~~java
import java.util.List;

import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class TransactionalOrderPublisher {

    private final StreamBridge streamBridge;

    TransactionalOrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @Transactional(transactionManager = "kafkaTransactionManager")
    public void publishBatch(List<OrderEvent> events) {
        for (OrderEvent event : events) {
            if (!streamBridge.send("orderEvents-out-0", event)) {
                throw new IllegalStateException(
                        "Could not enqueue event " + event.eventId());
            }
        }
    }
}
~~~

Đặt bean transaction manager có tên kafkaTransactionManager để khớp với thuộc tính transactionManager trong annotation. Nếu ứng dụng có nhiều transaction manager, luôn chỉ định rõ manager cần dùng; không dựa vào lựa chọn mặc định.

Gọi phương thức transactional từ một Spring bean khác:

~~~java
@Service
class OrderApplicationService {

    private final TransactionalOrderPublisher publisher;

    OrderApplicationService(TransactionalOrderPublisher publisher) {
        this.publisher = publisher;
    }

    void confirm(Order order) {
        List<OrderEvent> events = createEvents(order);
        publisher.publishBatch(events);
    }
}
~~~

Không gọi phương thức @Transactional từ một phương thức khác trong cùng instance bằng this.publishBatch(...) rồi kỳ vọng proxy tự kích hoạt. Self-invocation thường bỏ qua proxy của Spring, vì vậy transaction interceptor không được gọi. Ngoài ra, mặc định Spring rollback với RuntimeException và Error; checked exception cần cấu hình rollbackFor nếu muốn rollback.

## 8. Một transaction có thể bao phủ nhiều topic

Kafka transaction có thể gửi record đến nhiều topic thuộc cùng cluster bằng cùng transactional producer. Ví dụ:

Các kiểu lệnh dưới đây đại diện cho payload của hai output binding bổ sung:

~~~java
record InventoryCommand(String orderId, String sku, int quantity) {}

record InvoiceCommand(String orderId, long totalMinorUnits) {}
~~~

Khai báo cả ba output binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderEvents-out-0:
          destination: orders.events
          content-type: application/json
        inventoryCommands-out-0:
          destination: inventory.commands
          content-type: application/json
        invoiceCommands-out-0:
          destination: billing.commands
          content-type: application/json
~~~

~~~java
@Service
class OrderDecisionPublisher {

    private final StreamBridge streamBridge;
    private final TransactionTemplate kafkaTransactionTemplate;

    OrderDecisionPublisher(
            StreamBridge streamBridge,
            TransactionTemplate kafkaTransactionTemplate) {
        this.streamBridge = streamBridge;
        this.kafkaTransactionTemplate = kafkaTransactionTemplate;
    }

    void publishDecision(OrderEvent orderEvent,
                         InventoryCommand inventoryCommand,
                         InvoiceCommand invoiceCommand) {

        kafkaTransactionTemplate.executeWithoutResult(status -> {
            requireAccepted(
                    streamBridge.send("orderEvents-out-0", orderEvent));
            requireAccepted(
                    streamBridge.send("inventoryCommands-out-0", inventoryCommand));
            requireAccepted(
                    streamBridge.send("invoiceCommands-out-0", invoiceCommand));
        });
    }

    private void requireAccepted(boolean accepted) {
        if (!accepted) {
            throw new IllegalStateException("An output binding rejected a message");
        }
    }
}
~~~

Các output binding cần được khai báo và kết nối đến những topic Kafka trong cùng cluster, đồng thời phải dùng transactional producer factory phù hợp. Nếu các binding thuộc hai Kafka cluster khác nhau hoặc hai binder có producer factory khác nhau, một Kafka transaction không thể biến chúng thành một giao dịch phân tán nguyên tử.

Nếu một send thất bại sau khi các send trước đã được chấp nhận, exception phải làm transaction rollback. Consumer read_committed sẽ không thấy các record thuộc transaction bị abort.

## 9. Ranh giới transaction và transaction manager

Ranh giới nên bao phủ đúng các lần gửi cùng đại diện cho một quyết định nghiệp vụ:

| Ranh giới | Ví dụ | Nhận xét |
|---|---|---|
| Một lần gửi | Một sự kiện độc lập | Thường dùng sync send nếu cần xác nhận |
| Một batch | Nhiều sự kiện của cùng thao tác chốt đơn | Có thể commit/abort cùng nhau |
| Nhiều topic | Một quyết định phát lệnh cho đơn hàng, kho và hóa đơn | Phải dùng cùng Kafka cluster và producer factory |
| Một chu kỳ scheduler | Một batch snapshot cần công bố đồng bộ | Có thể dùng TransactionTemplate quanh batch |
| Toàn bộ request kéo dài | Gồm gọi API ngoài, chờ người dùng hoặc nhiều tác vụ dài | Không nên giữ Kafka transaction mở trong toàn bộ thời gian đó |

Transaction càng dài càng giữ producer và transaction coordinator lâu hơn, tăng nguy cơ timeout và làm giảm khả năng xử lý. Chỉ đặt các lệnh gửi có liên hệ nguyên tử vào transaction. Thực hiện validation, truy vấn hoặc tính toán tốn thời gian trước khi mở transaction nếu có thể; không gọi dịch vụ ngoài trong transaction nếu không cần.

## 10. transaction-id-prefix và fencing giữa các instance

Kafka dùng transactional.id để nhận diện producer có transaction. Khi producer mới khởi tạo cùng transactional ID, Kafka có thể fence producer cũ để ngăn hai tiến trình đồng thời tiếp tục ghi bằng cùng định danh.

Với ứng dụng chạy nhiều replica:

- Mỗi instance cần prefix duy nhất.
- Không dùng một prefix cố định chung cho mọi pod.
- Đưa instance ID ổn định trong vòng đời tiến trình vào cấu hình.
- Khi restart hoặc triển khai rolling update, bảo đảm hai instance đang hoạt động không vô tình chia sẻ cùng prefix.
- Theo dõi ProducerFencedException và lỗi khởi tạo transaction.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: ${POD_UID}-orders-
~~~

Nếu môi trường không có POD_UID, dùng biến định danh instance do nền tảng cấp. Giá trị mặc định như local chỉ phù hợp khi chắc chắn một instance duy nhất.

## 11. Transaction timeout và giao dịch quá dài

Kafka producer có thuộc tính transaction.timeout.ms, giới hạn thời gian broker cho phép một transaction chưa hoàn tất. Broker cũng có giới hạn transaction.max.timeout.ms; giá trị producer yêu cầu không thể tùy ý vượt giới hạn cluster.

Transaction quá dài có thể:

- Hết thời gian và bị abort.
- Giữ producer đang được transaction manager sử dụng lâu hơn dự kiến.
- Làm chậm consumer read_committed ở phạm vi partition liên quan do transaction chưa hoàn tất.
- Tăng nguy cơ timeout khi ứng dụng gọi API hoặc chờ I/O bên ngoài.

Đặt timeout theo thời gian thực tế của batch và độ trễ broker, nhưng giữ transaction ngắn. Không tăng timeout để che một quy trình xử lý kéo dài vốn nên tách thành nhiều bước độc lập.

## 12. Producer-only transaction khác consumer-initiated transaction

Trong producer-only transaction, ứng dụng tự mở transaction rồi gửi record. Không có offset đầu vào nào được thêm vào transaction.

Trong processor pattern của Spring Cloud Stream, consumer listener có thể khởi tạo Kafka transaction. Các record được gửi trên consumer thread tham gia transaction đó; khi listener kết thúc bình thường, listener container đưa offset đã xử lý vào transaction rồi commit. Như vậy output records và offset input có thể được commit cùng nhau.

| Đặc điểm | Producer-only | Consumer-initiated |
|---|---|---|
| Ai bắt đầu transaction | TransactionTemplate, @Transactional hoặc producer transaction API | Kafka listener container |
| Có input offset trong transaction | Không | Có, khi container commit offset vào transaction |
| Mục đích | Nhóm nhiều lần phát thành một đơn vị | Đảm bảo consume-process-produce theo transaction Kafka |
| Ranh giới thường gặp | Một thao tác phát hoặc batch | Một lần xử lý record/batch của listener |
| Thành phần Spring | KafkaTransactionManager / TransactionTemplate | Transaction-aware listener container và binder |

Không gọi producer-only transaction là exactly-once processing cho toàn hệ thống. Nó bảo đảm tính nguyên tử của nhóm record Kafka được gửi trong transaction. Exactly-once consume-process-produce cần kết hợp offset đầu vào và output trong cùng transaction, consumer phù hợp và read_committed ở phía đọc.

## 13. Consumer isolation.level và cách quan sát transaction

Consumer mặc định có thể đọc cả record thuộc transaction chưa commit hoặc đã abort nếu isolation level là read_uncommitted. Consumer dùng read_committed chỉ trả về record từ transaction đã commit và record không thuộc transaction.

Với Kafka Binder, có thể cấu hình isolation level cho consumer qua binder configuration:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          configuration:
            isolation.level: read_committed
~~~

Đây là cấu hình cho consumer client của binder. Nếu dùng nhiều consumer có yêu cầu khác nhau, cân nhắc phạm vi cấu hình theo binding và kiểm tra tài liệu phiên bản binder.

Để kiểm chứng ranh giới:

1. Gửi hai record trong một transaction.
2. Commit và xác nhận consumer read_committed nhận cả hai.
3. Gửi hai record khác rồi cố ý ném exception trước khi commit.
4. Xác nhận consumer read_committed không nhận các record đã abort.
5. So sánh với consumer read_uncommitted trong môi trường kiểm thử để hiểu sự khác biệt quan sát.

Không dùng Thread.sleep làm bằng chứng duy nhất về transaction. Hãy xác nhận trạng thái commit/abort và kết quả đọc bằng consumer có isolation level được chỉ định.

## 14. Transaction và database: giới hạn của ranh giới

Producer-only transaction chỉ bao phủ Kafka. Nếu phương thức vừa gửi Kafka vừa ghi database, KafkaTransactionManager không tự rollback database và transaction database cũng không tự rollback Kafka nếu hai resource không được đồng bộ.

Spring có thể đồng bộ hai transaction manager theo thứ tự commit. Tuy nhiên, đây không phải distributed two-phase commit nguyên tử giữa Kafka và database. Một transaction có thể commit trước, transaction còn lại thất bại sau đó; ứng dụng cần xử lý trạng thái lệch và có phương án bù trừ.

Với dữ liệu nghiệp vụ quan trọng, transactional outbox thường là lựa chọn bền vững:

1. Trong một transaction database, ghi thay đổi nghiệp vụ và bản ghi outbox.
2. Một publisher đọc outbox và gửi sự kiện sang Kafka.
3. Sau khi gửi thành công, publisher đánh dấu outbox đã phát.
4. Consumer idempotent để xử lý khả năng publisher gửi lại nếu tiến trình dừng giữa publish và cập nhật trạng thái.

Outbox tránh khoảng trống giữa database commit và việc ghi ý định phát sự kiện. Kafka transaction vẫn có thể dùng để nhóm nhiều record Kafka, nhưng không thay thế tính nhất quán database.

## 15. Lỗi thường gặp khi dùng producer-only transaction

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Mỗi send commit riêng | Chỉ bật transaction-id-prefix, không có transaction manager bao quanh nhiều lần gửi | Dùng KafkaTransactionManager cùng producer factory của binder |
| @Transactional không rollback | Self-invocation, bean không qua proxy hoặc không có đúng transaction manager | Gọi qua Spring bean proxy và chỉ định manager |
| StreamBridge không tham gia transaction | Manager dùng producer factory khác binder | Lấy getTransactionalProducerFactory() từ KafkaMessageChannelBinder |
| Producer bị fencing | Nhiều instance dùng chung transaction ID prefix | Cấp prefix duy nhất cho từng instance |
| Transaction bị abort do timeout | Batch quá dài hoặc gọi dịch vụ ngoài trong transaction | Thu hẹp ranh giới và điều chỉnh timeout hợp lý |
| Consumer vẫn thấy record đã abort | Consumer dùng read_uncommitted | Dùng isolation.level=read_committed khi cần chỉ đọc dữ liệu đã commit |
| Chỉ một số topic nhận record | Các binding không dùng cùng cluster/factory hoặc transaction boundary không bao phủ tất cả send | Xác nhận binder, cluster và transaction manager |
| Ghi DB thành công nhưng Kafka thất bại | Hai hệ thống không nằm trong cùng transaction nguyên tử | Dùng outbox hoặc quy trình bù trừ |

## 16. Kiểm thử ranh giới transaction

Một bộ kiểm thử hữu ích cần kiểm tra cả đường commit và rollback:

- **Commit:** phát nhiều record, kết thúc callback bình thường, consumer read_committed nhận đủ record.
- **Rollback:** phát một phần record rồi ném exception, consumer read_committed không nhận record nào của transaction đó.
- **Nhiều topic:** gửi đến hai topic và xác nhận cả hai cùng commit hoặc cùng abort.
- **Transaction manager:** xác nhận manager lấy đúng producer factory từ Kafka Binder.
- **Nhiều instance:** xác nhận prefix khác nhau và không phát sinh producer fencing.
- **Consumer visibility:** kiểm tra isolation level của consumer được cấu hình đúng.
- **Timeout:** mô phỏng transaction kéo dài và xác nhận lỗi được ghi nhận, không âm thầm bỏ qua.
- **Database interaction:** nếu có DB, kiểm tra outbox và trạng thái phục hồi khi một bước commit thất bại.

Test binder có thể kiểm tra logic hàm và wiring ở cấp Spring Cloud Stream, nhưng không thay thế kiểm thử Kafka transaction coordinator, transactional producer, abort và read_committed. Dùng Kafka broker thật hoặc môi trường tích hợp tương đương để xác minh các bảo đảm này.

## 17. Quan sát giao dịch trong môi trường chạy

Khi phát triển hoặc điều tra lỗi, có thể bật TRACE có chọn lọc:

~~~yaml
logging:
  level:
    org.springframework.transaction: TRACE
    org.springframework.kafka.transaction: TRACE
    org.springframework.kafka.producer: TRACE
    org.springframework.kafka.core: TRACE
~~~

Log có thể cho thấy chuỗi beginTransaction, send, commitTransaction hoặc abortTransaction. Khi dùng TransactionTemplate bao quanh nhiều send, một nhóm gửi thành công cần tương ứng với một transaction boundary, không phải một chuỗi begin/commit riêng cho từng send.

Trong production, theo dõi:

- Số transaction commit và abort.
- Lỗi producer fencing, transaction timeout và lỗi commit.
- Thời gian mở transaction và số record trong mỗi transaction.
- Tỷ lệ send thất bại, producer error channel và retry ở tầng ứng dụng.
- Consumer lag và hành vi của consumer read_committed.

Không ghi payload nhạy cảm vào log transaction. Dùng event ID, transaction correlation ID và topic để truy vết.

## 18. Checklist xác định ranh giới

- Một lần gửi đơn lẻ có thật sự cần transaction hay synchronous send là đủ?
- Những record nào phải cùng xuất hiện hoặc cùng bị abort?
- Các output binding có thuộc cùng Kafka cluster và cùng transactional producer factory?
- transaction-id-prefix đã được bật và duy nhất cho từng instance?
- KafkaTransactionManager lấy producer factory từ chính Kafka Binder?
- TransactionTemplate hoặc @Transactional bao quanh toàn bộ các lần gửi liên quan?
- Exception có thoát khỏi callback để rollback hay transaction đã bị đánh dấu rollback-only?
- Consumer cần read_committed để chỉ thấy transaction đã commit?
- Transaction có ngắn và tránh gọi API ngoài hoặc chờ lâu?
- Nếu có database, đã dùng outbox hoặc thiết kế bù trừ cho lỗi commit chéo hệ thống?
- Đã kiểm thử cả commit, abort, nhiều topic và producer fencing với Kafka thật?

Producer-only transaction phù hợp khi nhiều lần phát Kafka thuộc cùng một quyết định nghiệp vụ và cần được công bố nguyên tử. transaction-id-prefix bật transactional producer của Kafka Binder, còn KafkaTransactionManager dùng đúng producer factory của binder để xác định ranh giới thực tế qua TransactionTemplate hoặc @Transactional. Một send đơn lẻ thường không cần transaction nhiều record; khi có database hoặc hệ thống ngoài, cần thiết kế riêng cho tính nhất quán vì Kafka transaction không tự mở rộng sang các hệ thống đó.

## Tài liệu tham khảo

- [Spring Cloud Stream — Transactional Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/transactional.html)
- [Spring Blog — Producer Initiated Transactions in Spring Cloud Stream Kafka Applications](https://spring.io/blog/2023/09/28/producer-initiated-transactions-in-spring-cloud-stream-kafka-applications/)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
