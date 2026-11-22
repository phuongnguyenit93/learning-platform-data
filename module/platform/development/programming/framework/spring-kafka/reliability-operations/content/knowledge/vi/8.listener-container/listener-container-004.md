# ConcurrentKafkaListenerContainerFactory

Trong Spring Kafka, **ConcurrentKafkaListenerContainerFactory** là factory dùng để tạo các listener container cho những phương thức được đánh dấu **@KafkaListener**. Factory kết hợp **ConsumerFactory**, cấu hình container và endpoint metadata để tạo ra **ConcurrentMessageListenerContainer**. Container này quản lý một hoặc nhiều consumer Kafka, gọi listener, xử lý acknowledgement, commit offset và phối hợp các cơ chế vận hành như error handler, concurrency và transaction.

Factory là điểm cấu hình quan trọng của phần consumer trong ứng dụng Spring Kafka. Khi cần điều chỉnh cách listener chạy trong production, đội phát triển thường cấu hình factory thay vì tự tạo KafkaConsumer và tự viết vòng poll.

## 1. Factory nằm ở đâu trong kiến trúc Spring Kafka?

Một luồng listener có các thành phần chính:

- **Kafka broker** lưu record theo topic và partition, phục vụ fetch request, quản lý consumer group và lưu committed offset.
- **ConsumerFactory** tạo Kafka consumer với các cấu hình client như bootstrap servers, deserializer, group ID, security và các consumer properties.
- **ConcurrentKafkaListenerContainerFactory** tạo listener container và áp dụng các thiết lập vận hành cho container.
- **ConcurrentMessageListenerContainer** quản lý các listener container con và số consumer được cấu hình.
- **KafkaMessageListenerContainer** sở hữu một Kafka consumer, thực hiện poll và gọi listener trên luồng xử lý của nó.
- **@KafkaListener** đánh dấu phương thức nhận record hoặc batch record.

~~~mermaid
flowchart TD
    A["@KafkaListener endpoint"] --> B["Kafka listener endpoint registry"]
    B --> C["ConcurrentKafkaListenerContainerFactory"]
    D["ConsumerFactory"] --> C
    E["Container configuration<br/>AckMode, concurrency, error handler"] --> C
    C --> F["ConcurrentMessageListenerContainer"]
    F --> G["KafkaMessageListenerContainer 1"]
    F --> H["KafkaMessageListenerContainer 2"]
    F --> I["KafkaMessageListenerContainer N"]
    G --> J["Kafka consumer 1"]
    H --> K["Kafka consumer 2"]
    I --> L["Kafka consumer N"]
    J --> M["Kafka broker"]
    K --> M
    L --> M
~~~

Factory không phải Kafka broker và cũng không phải một Kafka consumer đang poll. Nó là đối tượng cấu hình và tạo container. Các consumer thực tế được tạo từ ConsumerFactory khi listener container khởi động.

## 2. Phân biệt các thành phần thường bị nhầm lẫn

| Thành phần | Trách nhiệm |
|---|---|
| **ConsumerFactory** | Tạo Kafka consumer và cung cấp cấu hình client |
| **ConcurrentKafkaListenerContainerFactory** | Tạo concurrent listener container, áp dụng concurrency và các thuộc tính container |
| **ConcurrentMessageListenerContainer** | Điều phối nhiều KafkaMessageListenerContainer con |
| **KafkaMessageListenerContainer** | Quản lý một consumer, poll record và gọi listener |
| **@KafkaListener** | Khai báo endpoint nhận message và các metadata như topic, group ID, container factory |
| **KafkaListenerEndpointRegistry** | Đăng ký và quản lý vòng đời các listener container được tạo từ endpoint |

Một cách nhớ hữu ích: **ConsumerFactory tạo client; listener container factory tạo container; container quản lý client và gọi listener**.

Không nên cấu hình nhầm consumer properties ở factory container. Ví dụ, deserializer, bootstrap servers và group ID là cấu hình của Kafka consumer, thường được cung cấp qua ConsumerFactory. AckMode, poll timeout, concurrency và error handler là các thiết lập thuộc quá trình chạy listener container.

## 3. Cách factory được sử dụng với @KafkaListener

Khi ứng dụng bật annotation-driven listener support, Spring đăng ký các endpoint được khai báo bằng **@KafkaListener**. Endpoint registry dùng factory phù hợp để tạo container cho từng endpoint.

Trong ứng dụng Spring Framework thuần, có thể bật chức năng này bằng **@EnableKafka**:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafka;

@Configuration
@EnableKafka
public class KafkaListenerEnablement {
}
~~~

Với Spring Boot, cấu hình Kafka auto-configuration thường đã thiết lập annotation-driven listener infrastructure. Không cần thêm **@EnableKafka** một cách máy móc nếu Boot đã quản lý phần này.

Ví dụ một listener:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderCreatedListener {

    @KafkaListener(
        topics = "orders.created",
        groupId = "inventory-service"
    )
    public void onOrderCreated(OrderCreated event) {
        inventoryService.reserve(event);
    }
}
~~~

Nếu ứng dụng có bean factory tên mặc định **kafkaListenerContainerFactory**, endpoint có thể sử dụng factory đó mà không cần chỉ rõ thuộc tính **containerFactory**. Khi có nhiều factory, chỉ định tên factory trên annotation:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "inventory-service",
    containerFactory = "ordersListenerFactory"
)
public void onOrderCreated(OrderCreated event) {
    inventoryService.reserve(event);
}
~~~

Giá trị **containerFactory** phải khớp với tên bean factory đã đăng ký trong Spring context. Nếu tên bean sai hoặc factory không tồn tại, endpoint không thể được tạo theo cấu hình mong muốn.

## 4. Cấu hình factory cơ bản

Một factory thường cần một ConsumerFactory, concurrency, acknowledgement mode và error handler. Ví dụ dưới đây dùng Spring Kafka API hiện đại:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        factory.setCommonErrorHandler(
                new DefaultErrorHandler(
                        new FixedBackOff(1_000L, 2L)
                )
        );

        return factory;
    }
}
~~~

Trong ví dụ:

- **setConsumerFactory** cung cấp factory tạo Kafka consumer.
- **setConcurrency(3)** yêu cầu container chạy với ba consumer con cho endpoint sử dụng factory này.
- **AckMode.RECORD** yêu cầu container commit tiến độ sau từng record được xử lý thành công theo semantics của chế độ đó.
- **DefaultErrorHandler** cung cấp chính sách xử lý exception với khoảng backoff 1 giây và tối đa hai lần retry theo cấu hình minh họa.

Các API error handler có thể khác nhau theo phiên bản Spring Kafka. Với codebase cũ, hãy đối chiếu phiên bản dependency trước khi dùng **setCommonErrorHandler** hoặc các API mới. Không trộn ví dụ cấu hình của nhiều phiên bản vào cùng một ứng dụng.

Listener có thể chọn factory bằng tên bean:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "inventory-service",
    containerFactory = "ordersListenerFactory"
)
public void onOrderCreated(OrderCreated event) {
    inventoryService.reserve(event);
}
~~~

Nếu dùng một factory mặc định cho toàn bộ ứng dụng, có thể đặt tên bean là **kafkaListenerContainerFactory**. Spring Boot thường tạo factory mặc định khi ứng dụng chưa cung cấp bean cùng tên. Khi tự định nghĩa bean mặc định, hãy kiểm tra các thiết lập Boot auto-config trước đó để không vô tình bỏ qua cấu hình như message converter hoặc customizer đang được ứng dụng sử dụng.

## 5. Cấu hình qua Spring Boot

Với các ứng dụng dùng Spring Boot, nhiều thuộc tính listener có thể được khai báo trong **application.yml**:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker-1:9092,broker-2:9092
    consumer:
      group-id: inventory-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
    listener:
      concurrency: 3
      ack-mode: record
      poll-timeout: 1s
~~~

Spring Boot có thể tự cấu hình ConsumerFactory và listener container factory mặc định từ các thuộc tính này. Đây là cách đơn giản khi ứng dụng chỉ có một nhóm consumer dùng chung chính sách.

Nếu cần nhiều cấu hình listener khác nhau, có thể khai báo factory riêng. Ví dụ, service xử lý đơn hàng cần concurrency cao hơn, còn service cập nhật báo cáo cần concurrency thấp và batch listener. Mỗi factory có thể dùng ConsumerFactory và container properties phù hợp với workload.

Cần phân biệt hai nhóm cấu hình:

| Nhóm cấu hình | Ví dụ | Nơi áp dụng |
|---|---|---|
| Kafka consumer client | bootstrap servers, group ID, deserializer, security, fetch settings | ConsumerFactory |
| Listener container | concurrency, AckMode, poll timeout, error handler, transaction manager | ConcurrentKafkaListenerContainerFactory / ContainerProperties |

Một số thuộc tính Boot có thể được bind vào factory mặc định. Khi tự tạo factory, đừng mặc định rằng mọi thuộc tính YAML đều tự áp dụng cho bean tùy chỉnh. Hãy cấu hình rõ những giá trị cần thiết hoặc dùng cơ chế customizer do phiên bản Boot đang dùng cung cấp.

## 6. Concurrency và cách container tạo consumer

Điểm quan trọng của **ConcurrentKafkaListenerContainerFactory** là khả năng cấu hình số consumer chạy song song cho một listener endpoint.

~~~java
factory.setConcurrency(3);
~~~

Khi container khởi động, **ConcurrentMessageListenerContainer** tạo và quản lý các **KafkaMessageListenerContainer** con. Mỗi container con sử dụng một Kafka consumer và thực hiện poll trên luồng riêng.

Với concurrency bằng 3, một endpoint có thể được phục vụ bởi ba consumer. Nếu các consumer tham gia cùng consumer group, Kafka phân phối các partition được subscription giữa các thành viên của group theo cơ chế assignment.

Ví dụ topic có sáu partition và listener concurrency bằng ba:

~~~mermaid
flowchart TD
    A["orders.created<br/>6 partitions"] --> B["Consumer group inventory-service"]
    B --> C["Consumer 1<br/>Partition 0, 1"]
    B --> D["Consumer 2<br/>Partition 2, 3"]
    B --> E["Consumer 3<br/>Partition 4, 5"]
~~~

Sơ đồ là một cách phân phối minh họa. Assignment thực tế phụ thuộc partition assignor, số consumer đang hoạt động, subscription của các thành viên và trạng thái group.

### Concurrency không phải số partition

Một topic có sáu partition không thể tạo ra sáu luồng xử lý song song chỉ bằng cách đặt concurrency lớn tùy ý nếu ứng dụng chỉ có sáu partition và cùng một group. Khi số consumer lớn hơn số partition có thể được giao, một số consumer sẽ không nhận partition và không xử lý record.

Với topic có một partition, tăng concurrency của cùng group không tạo thêm khả năng xử lý song song cho partition đó. Kafka vẫn giữ thứ tự record trong partition và chỉ giao partition đó cho một consumer trong group tại một thời điểm.

### Chọn concurrency

Cân nhắc các yếu tố:

- Số partition của các topic mà listener subscribe.
- Throughput cần đạt và thời gian xử lý mỗi record.
- Khả năng song song của database hoặc downstream service.
- CPU, memory và network của ứng dụng.
- Số consumer đang chạy trong cùng group ở các instance khác.
- Chi phí rebalance khi số consumer thay đổi.

Concurrency quá thấp có thể làm một số partition không được tận dụng hết. Concurrency quá cao có thể tạo consumer idle, tăng kết nối và làm downstream quá tải. Hãy đo hiệu năng trong môi trường gần production trước khi chọn giá trị.

### Concurrency giữa nhiều instance

Nếu có ba instance ứng dụng và mỗi instance tạo một listener concurrency bằng ba, tổng số consumer trong group có thể là chín. Cần tính tổng consumer trên toàn deployment, không chỉ nhìn giá trị concurrency trong một pod.

Ví dụ:

| Số instance | Concurrency mỗi instance | Tổng consumer dự kiến |
|---:|---:|---:|
| 1 | 3 | 3 |
| 2 | 3 | 6 |
| 3 | 3 | 9 |
| 4 | 2 | 8 |

Số consumer thực tế có thể thấp hơn nếu container chưa khởi động hoặc listener bị dừng. Nếu số consumer vượt số partition được giao, một số consumer không có partition để xử lý.

## 7. Một factory hay nhiều factory?

Một factory mặc định là đủ khi các listener có cùng yêu cầu về consumer, acknowledgement, concurrency, error handling và transaction.

Khi các workload có hành vi khác nhau, tách factory giúp chính sách vận hành rõ ràng hơn.

Ví dụ:

- **ordersListenerFactory** dùng record listener, concurrency 4 và retry ngắn cho lỗi tạm thời.
- **auditBatchListenerFactory** dùng batch listener, concurrency 2 và batch error handling phù hợp.
- **transactionalListenerFactory** dùng transaction manager và cấu hình transaction riêng.
- **slowDependencyListenerFactory** có concurrency thấp để bảo vệ dịch vụ downstream chậm.

Mỗi factory có thể dùng cùng một ConsumerFactory nếu các consumer client properties tương thích, hoặc dùng ConsumerFactory riêng nếu cần group ID mặc định, deserializer, security hay fetch configuration khác nhau.

Ví dụ khai báo hai factory:

~~~java
@Configuration
public class ListenerFactoriesConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(4);
        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.RECORD);

        return factory;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, AuditEvent>
    auditBatchListenerFactory(
            ConsumerFactory<String, AuditEvent> auditConsumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, AuditEvent>();

        factory.setConsumerFactory(auditConsumerFactory);
        factory.setConcurrency(2);
        factory.setBatchListener(true);

        return factory;
    }
}
~~~

Các listener chọn factory tương ứng:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "inventory-service",
    containerFactory = "ordersListenerFactory"
)
public void onOrderCreated(OrderCreated event) {
    inventoryService.reserve(event);
}

@KafkaListener(
    topics = "audit.events",
    groupId = "audit-processor",
    containerFactory = "auditBatchListenerFactory"
)
public void onAuditEvents(List<AuditEvent> events) {
    auditService.storeBatch(events);
}
~~~

Hai factory cho phép cấu hình riêng concurrency và kiểu listener. Chúng cũng làm rõ owner của từng workload khi điều tra lỗi, lag hoặc throughput.

Không tạo một factory mới cho mỗi listener nếu các thiết lập hoàn toàn giống nhau và không có lý do vận hành cụ thể. Quá nhiều factory tương tự làm cấu hình khó theo dõi và dễ phát sinh khác biệt ngoài ý muốn.

## 8. Record listener và batch listener

Factory có thể tạo container hoạt động theo kiểu record hoặc batch.

### Record listener

Đây là kiểu phổ biến khi mỗi lần gọi listener xử lý một record:

~~~java
factory.setBatchListener(false);

@KafkaListener(
    topics = "orders.created",
    containerFactory = "ordersListenerFactory"
)
public void onOrderCreated(OrderCreated event) {
    orderService.process(event);
}
~~~

Container gọi listener cho từng record. Đây là lựa chọn phù hợp khi xử lý từng event độc lập, cần phân loại lỗi theo record hoặc cần kiểm soát side effect riêng cho mỗi message.

### Batch listener

Khi bật batch mode:

~~~java
factory.setBatchListener(true);
~~~

Listener nhận một collection record từ một lần poll:

~~~java
@KafkaListener(
    topics = "audit.events",
    containerFactory = "auditBatchListenerFactory"
)
public void onAuditEvents(List<AuditEvent> events) {
    auditService.storeBatch(events);
}
~~~

Batch listener có thể giảm overhead gọi downstream hoặc ghi database theo lô. Đổi lại, error handling phức tạp hơn vì một record lỗi có thể ảnh hưởng cách xử lý cả batch. Cần xác định record nào đã xử lý, record nào thất bại và offset nào được phép commit.

Không dùng cùng một factory batch listener cho method được thiết kế nhận một record đơn lẻ. Kiểu tham số listener phải tương thích với chế độ container.

## 9. Cấu hình ContainerProperties

Factory cung cấp **getContainerProperties()** để cấu hình các thuộc tính ảnh hưởng cách container chạy.

Một số thiết lập thường gặp:

| Thuộc tính | Tác dụng |
|---|---|
| **AckMode** | Chọn thời điểm và cách container commit offset |
| **pollTimeout** | Thời gian chờ trong một lần poll |
| **ackTime** | Ngưỡng thời gian dùng với AckMode.TIME |
| **ackCount** | Ngưỡng record dùng với COUNT hoặc COUNT_TIME |
| **syncCommits** | Chọn commit đồng bộ hay bất đồng bộ |
| **shutdownTimeout** | Thời gian container chờ khi shutdown |
| **idleEventInterval** | Khoảng thời gian phát idle event khi phù hợp |
| **transactionManager** | Kết nối listener container với transaction manager theo API/version hỗ trợ |

Ví dụ:

~~~java
var properties = factory.getContainerProperties();

properties.setAckMode(ContainerProperties.AckMode.TIME);
properties.setAckTime(5_000L);
properties.setPollTimeout(1_000L);
properties.setSyncCommits(true);
~~~

Các thuộc tính cần được chọn theo delivery semantics và yêu cầu vận hành. Ví dụ, TIME gom offset theo thời gian; RECORD commit theo từng record đã xử lý; MANUAL cho phép listener chủ động xác nhận. Không chọn AckMode chỉ để giảm số request commit mà bỏ qua khả năng redelivery.

**ContainerProperties** là cấu hình của container. Các thuộc tính như deserializer, group ID và security vẫn thuộc cấu hình consumer được tạo qua ConsumerFactory.

## 10. Error handler và phục hồi lỗi

Factory là nơi có thể gắn **CommonErrorHandler** cho các container được tạo từ nó. Error handler quyết định cách container phản ứng khi listener ném exception: retry, backoff, recover hoặc chuyển record sang một quy trình xử lý khác.

Ví dụ gắn DefaultErrorHandler:

~~~java
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

factory.setCommonErrorHandler(
        new DefaultErrorHandler(
                new FixedBackOff(1_000L, 2L)
        )
);
~~~

Cấu hình minh họa retry với khoảng nghỉ 1 giây và hai lần thử lại. Chính sách thực tế cần phân loại lỗi:

- Lỗi tạm thời như downstream timeout có thể được retry với backoff.
- Lỗi dữ liệu không hợp lệ có thể không nên retry nhiều lần.
- Lỗi authorization hoặc cấu hình thường không được khắc phục bằng retry liên tục.
- Poison message cần recovery có kiểm soát, có thể chuyển vào DLT nếu producer có quyền và DLT đã được cấu hình.

Với record listener và batch listener, semantics của error handler có thể khác nhau. Batch listener cần xác định record lỗi trong batch và phần offset được xác nhận. Với các API như **BatchListenerFailedException**, ứng dụng có thể cung cấp thông tin về vị trí record thất bại cho handler phù hợp.

Factory dùng chung error handler có thể phù hợp với các listener cùng chính sách. Nếu các workload có chính sách retry khác nhau, hãy tách factory hoặc cấu hình handler riêng theo khả năng của phiên bản Spring Kafka.

## 11. Transaction và acknowledgement

Listener container có thể phối hợp với Kafka transaction manager hoặc transaction manager phù hợp khác theo cấu hình Spring Kafka.

Với Kafka transaction, container có thể xử lý record trong transaction và phối hợp offset với transaction khi commit. Nếu transaction rollback, record có thể được đọc lại tùy trạng thái và cấu hình consumer. Khi dùng transaction, phải xem semantics của transactional listener container thay vì suy luận đơn giản từ AckMode không giao dịch.

Factory có thể được cấu hình để dùng transaction manager thông qua **ContainerProperties**. API cụ thể đã thay đổi qua các phiên bản Spring Kafka; cần dùng đúng loại transaction manager và method của phiên bản ứng dụng.

Một số nguyên tắc:

- Không bắt exception trong listener rồi trả về bình thường nếu muốn transaction rollback.
- Không coi database transaction và Kafka transaction là một transaction nguyên tử tự động.
- Nếu listener cập nhật database và phát event ra Kafka, cân nhắc outbox/inbox hoặc cơ chế phối hợp phù hợp.
- Consumer vẫn cần idempotency khi có thể redeliver.
- Chỉ dùng exactly-once khi xác định rõ phạm vi tài nguyên được Kafka transaction bảo vệ.

## 12. Rebalance, ordering và thread safety

Mỗi consumer con do concurrent container quản lý tham gia consumer group. Khi số consumer thay đổi, instance khởi động/dừng hoặc partition được thêm, Kafka có thể thực hiện rebalance để phân phối lại partition.

Rebalance có thể làm:

- Partition tạm thời không được xử lý trong khi assignment thay đổi.
- Listener bắt đầu xử lý partition mới được giao.
- Record chưa commit được đọc lại.
- Consumer lag tăng trong thời gian chuyển giao.
- Side effect bị lặp nếu ứng dụng không idempotent.

Concurrency không tạo thứ tự toàn cục giữa các partition. Kafka giữ thứ tự trong một partition. Nếu cần các event của cùng một aggregate được xử lý tuần tự, producer phải chọn key ổn định để chúng vào cùng partition, và listener không nên tự chuyển side effect sang nhiều tác vụ bất đồng bộ không có cơ chế giữ thứ tự.

Vì factory có thể tạo nhiều consumer và gọi listener đồng thời, bean listener và các dependency dùng chung phải thread-safe. Tránh lưu trạng thái mutable theo từng message trong field của singleton listener nếu không có đồng bộ phù hợp. Ưu tiên listener stateless và đưa trạng thái nghiệp vụ vào database hoặc thành phần quản lý riêng.

Nếu listener gọi database hoặc API bên ngoài, hãy giới hạn concurrency theo năng lực downstream. Tăng consumer không giúp ích khi database connection pool đã bão hòa.

## 13. Vòng đời và quản lý container

Factory tạo container khi endpoint được đăng ký. Endpoint registry quản lý các container được tạo từ những phương thức **@KafkaListener** và điều khiển vòng đời theo cấu hình ứng dụng.

Các điểm cần hiểu:

- **autoStartup** quyết định container có tự khởi động theo lifecycle hay không.
- Container có thể được quản lý thông qua **KafkaListenerEndpointRegistry**.
- Khi cần dừng hoặc khởi động listener có kiểm soát, có thể thao tác với container qua registry.
- Factory là cấu hình để tạo container; thay đổi factory sau khi container đã được tạo không tự động bảo đảm mọi container đang chạy được cấu hình lại.
- Khi thay đổi cấu hình quan trọng như concurrency hoặc consumer properties, cần có quy trình restart/recreate phù hợp và xác nhận trạng thái sau triển khai.

Ví dụ lấy container theo ID:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.stereotype.Component;

@Component
public class ListenerLifecycleManager {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerLifecycleManager(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void stopOrdersListener() {
        var container = registry.getListenerContainer("ordersListener");
        if (container != null && container.isRunning()) {
            container.stop();
        }
    }

    public void startOrdersListener() {
        var container = registry.getListenerContainer("ordersListener");
        if (container != null && !container.isRunning()) {
            container.start();
        }
    }
}
~~~

Để lấy container theo ID, endpoint phải khai báo ID:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.created",
    groupId = "inventory-service",
    containerFactory = "ordersListenerFactory"
)
public void onOrderCreated(OrderCreated event) {
    inventoryService.reserve(event);
}
~~~

Dừng listener có thể làm consumer rời group và kích hoạt rebalance. Trước khi dừng, cần cân nhắc drain công việc đang xử lý, shutdown timeout, committed offset và khả năng redelivery.

## 14. Tùy chỉnh theo từng endpoint

Một factory có thể phục vụ nhiều endpoint. Nếu một endpoint cần cấu hình khác biệt, hãy xem khả năng override ở cấp annotation hoặc container customizer mà phiên bản Spring Kafka đang dùng hỗ trợ.

Các thông tin thường được quyết định ở endpoint:

- Topic hoặc pattern subscription.
- Group ID.
- Listener ID.
- Container factory được sử dụng.
- Auto startup.
- Concurrency override nếu phiên bản API hỗ trợ.
- Topic partition assignment nếu cần gán partition tường minh.

Ví dụ hai endpoint dùng cùng factory nhưng khác topic và group ID:

~~~java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.created",
    groupId = "inventory-service",
    containerFactory = "ordersListenerFactory"
)
public void onOrderCreated(OrderCreated event) {
    inventoryService.reserve(event);
}

@KafkaListener(
    id = "returnsListener",
    topics = "returns.created",
    groupId = "returns-service",
    containerFactory = "ordersListenerFactory"
)
public void onReturnCreated(ReturnCreated event) {
    returnsService.process(event);
}
~~~

Dùng chung factory nghĩa là hai endpoint chia sẻ các thiết lập container mặc định từ factory. Chúng vẫn có thể có group ID và topic riêng. Nếu yêu cầu concurrency, error handler, transaction hoặc batch mode khác nhau, cân nhắc factory riêng để tránh một thay đổi ảnh hưởng nhiều workload.

## 15. Quan sát và chẩn đoán listener factory

Khi listener không chạy hoặc throughput không đạt, kiểm tra theo từng lớp thay vì chỉ xem log của phương thức listener.

| Triệu chứng | Kiểm tra ở ứng dụng | Kiểm tra ở Kafka |
|---|---|---|
| Listener không khởi động | Bean factory có tồn tại, tên containerFactory, endpoint registration, startup exception | Bootstrap connectivity, authentication và authorization |
| Không nhận record | Topic subscription, group ID, deserializer, listener lifecycle, filter | Topic/partition, committed offset, ACL READ và group coordination |
| Concurrency không tăng throughput | Giá trị concurrency hiệu lực, số instance, xử lý listener và downstream bottleneck | Số partition, assignment và consumer group membership |
| Consumer idle | Factory có tạo đủ container, subscription và group ID | Partition assignment, số partition và topic availability |
| Rebalance liên tục | Listener processing time, poll interval, shutdown và exception | Group coordinator, network và cluster stability |
| Commit offset chậm | AckMode, ackTime/ackCount, error handler và commit configuration | Commit latency, coordinator health và network |
| Record bị xử lý lặp | Side effect, acknowledgement, transaction rollback và idempotency | Committed offset và rebalance state |
| Batch xử lý lỗi | Batch listener signature, error handler và failed record index | Record trong partition và trạng thái offset |

### Các metric nên theo dõi

- Consumer lag theo group, topic và partition.
- Số consumer đang hoạt động và partition assignment.
- Record consumption rate.
- Listener processing time.
- Commit rate và commit latency.
- Rebalance count và thời gian rebalance.
- Retry, recovery và DLT rate.
- Số listener container đang chạy hoặc bị dừng.

Tên metric phụ thuộc Kafka client, Micrometer và hệ thống monitoring. Cần gắn nhãn service, environment, group ID và listener ID để điều tra đúng workload.

## 16. Các lỗi cấu hình thường gặp

**Không có bean factory đúng tên.** Annotation trỏ tới **ordersListenerFactory** nhưng Spring context không có bean đó. Kiểm tra tên bean và package configuration scan.

**Nhiều listener dùng chung factory nhưng yêu cầu khác nhau.** Một thay đổi concurrency hoặc error handler có thể ảnh hưởng tất cả endpoint dùng factory. Tách factory khi có khác biệt vận hành thực sự.

**Nhầm ConsumerFactory với ConcurrentKafkaListenerContainerFactory.** Deserializer và security được cấu hình ở consumer client, không phải ở factory tạo container.

**Tăng concurrency vượt số partition.** Consumer tăng lên nhưng không tạo thêm partition; một số consumer có thể idle và không tăng throughput.

**Không tính số instance.** Concurrency được nhân với số instance đang chạy. Tổng consumer group có thể lớn hơn nhiều so với dự kiến.

**Dùng batch factory cho record listener.** Kiểu listener và chế độ batch phải tương thích. Cấu hình sai có thể gây lỗi chuyển đổi message hoặc listener invocation.

**Dùng error handler không phù hợp.** Batch listener và record listener có semantics khác nhau. Retry/recovery cần được thiết kế theo loại listener.

**Cho rằng thay đổi factory tự cập nhật container đang chạy.** Factory là đối tượng tạo container. Thay đổi cấu hình cần quy trình restart hoặc recreate và xác nhận runtime.

**Listener singleton chứa trạng thái không thread-safe.** Concurrency có thể khiến nhiều thread gọi cùng bean listener. Trạng thái mutable phải được bảo vệ hoặc loại bỏ.

**Tăng concurrency để xử lý downstream chậm.** Điều này có thể làm database hoặc API phụ thuộc quá tải hơn. Cần đo bottleneck trước khi tăng consumer.

## 17. Runbook khi listener factory có vấn đề

Khi một listener endpoint không hoạt động như mong đợi:

1. Xác định listener ID, topic, group ID và instance phát sinh sự cố.
2. Xác minh endpoint được đăng ký và đang dùng đúng bean **ConcurrentKafkaListenerContainerFactory**.
3. Kiểm tra ConsumerFactory mà factory đang sử dụng.
4. Đọc concurrency, AckMode, poll timeout, error handler và transaction configuration hiệu lực.
5. Xác minh số partition và tổng số consumer trên tất cả instance.
6. Kiểm tra log khởi động, authentication/authorization, deserialization và listener exception.
7. Đối chiếu consumer lag, partition assignment, commit latency và rebalance count.
8. Nếu thay đổi cấu hình, xác định endpoint nào dùng factory đó để đánh giá phạm vi ảnh hưởng.
9. Triển khai thay đổi có kiểm soát, xác minh container được tạo lại hoặc restart đúng cách.
10. Theo dõi throughput, lag, duplicate, retry và DLT sau phục hồi.

Khi sự cố ảnh hưởng nhiều listener dùng chung factory, hãy kiểm tra cấu hình chung trước khi sửa từng listener riêng lẻ. Khi chỉ một endpoint lỗi, tập trung vào endpoint metadata, subscription và factory được chọn.

## 18. Checklist trước khi đưa listener factory vào production

**Cấu trúc và cấu hình**

- [ ] ConsumerFactory được cấu hình đúng bootstrap servers, group ID, deserializer và security.
- [ ] Factory bean có tên đúng với thuộc tính **containerFactory** của listener.
- [ ] Có factory mặc định **kafkaListenerContainerFactory** nếu endpoint cần dùng mặc định.
- [ ] AckMode, poll timeout và commit behavior phù hợp với delivery semantics.
- [ ] Error handler có retry, backoff và recovery rõ ràng.

**Concurrency và listener type**

- [ ] Concurrency được chọn dựa trên số partition và tổng số instance.
- [ ] Đã kiểm tra consumer idle khi concurrency vượt số partition có thể giao.
- [ ] Record listener và batch listener dùng đúng factory mode.
- [ ] Listener và dependency dùng chung thread-safe.
- [ ] Concurrency không làm downstream quá tải.

**Vòng đời và phục hồi**

- [ ] Listener ID được khai báo nếu cần quản lý qua registry.
- [ ] Shutdown và restart có kiểm soát.
- [ ] Rebalance và redelivery đã được tính đến.
- [ ] Consumer idempotency bảo vệ side effect.
- [ ] Transaction behavior được hiểu rõ nếu có dùng transaction manager.

**Quan sát**

- [ ] Theo dõi consumer lag, throughput, processing time và commit latency.
- [ ] Theo dõi rebalance, retry, recovery và DLT.
- [ ] Log có service, environment, group ID, listener ID, topic và partition.
- [ ] Runbook nêu rõ cách xác định factory và cấu hình hiệu lực.

## 19. Nguyên tắc thiết kế

**ConcurrentKafkaListenerContainerFactory** là nơi tập trung cách Spring Kafka tạo và cấu hình listener container. Nó kết nối ConsumerFactory với endpoint **@KafkaListener**, quyết định concurrency, loại listener và các chính sách container như acknowledgement, error handling và transaction integration.

Hãy dùng factory mặc định khi các listener có cùng yêu cầu vận hành. Khi workload khác nhau về concurrency, batch processing, retry hoặc transaction, hãy tạo factory riêng và gắn rõ vào từng endpoint. Đánh giá tổng consumer trên toàn bộ deployment, giữ listener thread-safe và theo dõi lag, commit cùng rebalance để điều chỉnh cấu hình dựa trên hành vi thực tế của hệ thống.
