# Lộ trình học Spring Kafka Messaging

Trong chương **Nền tảng messaging**, bài học này định hướng cách đi từ những khái niệm Kafka cốt lõi đến việc xây dựng và vận hành một luồng sự kiện bằng Spring Kafka. Trọng tâm của module **SPRING_KAFKA_MESSAGING** là gửi và nhận sự kiện bằng **KafkaTemplate** và **@KafkaListener**, hiểu topic, partition, offset, consumer group, rồi bổ sung serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử.

Lộ trình được sắp xếp theo quan hệ phụ thuộc: trước hết hiểu cách Kafka lưu và phân phối bản ghi, sau đó mới viết producer và consumer; tiếp theo kiểm soát lỗi, tính nhất quán và khả năng vận hành. Mỗi chặng đều có mục tiêu, nội dung cần nắm và một bài thực hành để kiểm chứng.

## Kết quả cần đạt

Sau khi hoàn thành lộ trình, bạn có thể:

- Giải thích được Kafka broker, topic, partition, record, key, offset và consumer group.
- Tạo ứng dụng Spring Boot gửi sự kiện bằng KafkaTemplate và nhận sự kiện bằng @KafkaListener.
- Chọn serializer/deserializer phù hợp, thiết kế payload và quản lý thay đổi schema.
- Hiểu thời điểm commit offset, cách consumer group phân chia partition và giới hạn của thứ tự xử lý.
- Thiết kế retry, dead-letter topic (DLT) và cách phát lại bản ghi lỗi có kiểm soát.
- Phân biệt transaction trong Kafka với transaction của cơ sở dữ liệu, đồng thời xác định phạm vi thực tế của exactly-once.
- Cấu hình xử lý đồng thời, kiểm thử luồng messaging và theo dõi các chỉ số quan trọng khi vận hành.

## 1. Hiểu mô hình messaging của Kafka trước khi dùng Spring

Kafka là nền tảng lưu trữ và phân phối luồng bản ghi. Producer ghi record vào topic; broker lưu record trong các partition; consumer đọc record theo offset. Spring Kafka cung cấp API và cơ chế tích hợp để ứng dụng Java làm việc với Kafka mà không phải tự quản lý toàn bộ giao thức.

Các khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa khi xây dựng ứng dụng |
|---|---|
| Broker | Một máy chủ Kafka nhận, lưu trữ và phục vụ record. Một cluster thường có nhiều broker. |
| Topic | Luồng logic chứa các record cùng loại, ví dụ **orders.created**. |
| Partition | Phần log có thứ tự của một topic. Kafka phân phối partition trên các broker để mở rộng lưu trữ và xử lý. |
| Record | Bản ghi gồm key, value, timestamp và các header tùy chọn. |
| Key | Giá trị dùng để định tuyến record tới partition. Các record cùng key thường được đưa vào cùng partition theo partitioner mặc định. |
| Offset | Vị trí của record trong một partition. Offset không phải số thứ tự toàn cục cho cả topic. |
| Consumer group | Nhóm consumer cùng chia nhau đọc các partition của topic. Kafka lưu tiến độ đọc riêng cho từng group. |

Một topic có nhiều partition có thể được đọc song song. Trong cùng một consumer group, tại một thời điểm, một partition chỉ được gán cho tối đa một consumer trong group đó. Một partition vẫn có thể được đọc độc lập bởi các consumer group khác nhau.

~~~mermaid
flowchart LR
    P[Producer<br/>KafkaTemplate] --> T[Topic: orders.created]
    T --> A[Partition 0]
    T --> B[Partition 1]
    T --> C[Partition 2]
    A --> G1[Consumer group: fulfillment]
    B --> G1
    C --> G1
    A --> G2[Consumer group: analytics]
    B --> G2
    C --> G2
~~~

Sơ đồ thể hiện hai group độc lập cùng nhận luồng sự kiện. Trong group fulfillment, các consumer chia nhau partition; group analytics có tiến độ đọc riêng. Vì vậy, hai hệ thống nghiệp vụ có thể cùng phản ứng với một sự kiện mà không phải gọi trực tiếp lẫn nhau.

Một số hệ quả quan trọng:

- Kafka bảo đảm thứ tự trong một partition. Không có thứ tự tổng thể giữa các partition.
- Nếu cần các sự kiện của cùng một đơn hàng đi theo thứ tự, hãy dùng mã đơn hàng làm key để chúng được định tuyến nhất quán.
- Tăng số consumer trong một group chỉ tăng mức song song đến giới hạn số partition đang được gán.
- Offset được quản lý theo partition và consumer group. Việc một group đọc xong record không làm group khác mất quyền đọc record đó.
- Consumer group có thể đọc lại record khi offset chưa được commit hoặc khi ứng dụng chủ động điều chỉnh vị trí đọc.

**Bài thực hành:** tạo một topic có ba partition, gửi nhiều record với cùng một key rồi quan sát partition và offset. Tiếp tục gửi record với các key khác nhau để thấy cách phân phối thay đổi. Dùng hai consumer group để xác nhận mỗi group có thể đọc cùng một luồng độc lập.

## 2. Chuẩn bị môi trường và tích hợp Spring Kafka

Trước khi viết code, cần có nền tảng Java, Spring Boot, Maven hoặc Gradle, JSON và các thao tác dòng lệnh cơ bản. Biết Docker sẽ giúp dựng Kafka cục bộ thuận tiện hơn. Bạn cũng nên hiểu cách cấu hình ứng dụng qua file YAML hoặc biến môi trường.

Trong dự án Spring Boot, thêm dependency **org.springframework.kafka:spring-kafka** và để Spring Boot dependency management quản lý phiên bản tương thích. Khi ứng dụng khởi động, cấu hình Kafka được dùng để tạo các thành phần cần thiết như KafkaTemplate, KafkaAdmin và listener container factory theo các điều kiện auto-configuration.

Ví dụ cấu hình tối thiểu trong application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: orders-processor
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      auto-offset-reset: earliest
      properties:
        spring.json.trusted.packages: com.example.messaging.events
~~~

Đây là cấu hình minh họa cho môi trường phát triển. Địa chỉ broker, serializer, consumer group và package được tin cậy phải được điều chỉnh theo ứng dụng. Không nên mở trusted packages cho mọi package trong môi trường production nếu không có lý do rõ ràng.

Một topic có thể được khai báo bằng bean NewTopic để Spring Kafka tạo topic thông qua KafkaAdmin:

~~~java
@Bean
NewTopic ordersCreatedTopic() {
    return TopicBuilder.name("orders.created")
            .partitions(3)
            .replicas(1)
            .build();
}
~~~

Ví dụ dùng một replica phù hợp cho Kafka cục bộ. Môi trường production cần thiết kế replication factor theo số broker và yêu cầu sẵn sàng; không sao chép nguyên cấu hình một replica lên production.

**Bài thực hành:** khởi động Kafka, chạy ứng dụng Spring Boot và xác nhận ứng dụng kết nối được broker. Tạo topic, kiểm tra tên và số partition, sau đó dừng rồi khởi động lại ứng dụng để hiểu thành phần nào được khởi tạo tự động và thành phần nào thuộc cấu hình của bạn.

## 3. Xây dựng producer với KafkaTemplate

Producer chuyển một sự kiện trong ứng dụng thành record Kafka. KafkaTemplate là API chính của Spring Kafka để gửi record, đồng thời hỗ trợ key, partition, timestamp, header và callback khi thao tác gửi hoàn tất.

Trước tiên, định nghĩa event DTO thể hiện dữ liệu công khai mà consumer cần. Ví dụ:

~~~java
public record OrderCreatedEvent(
        String eventId,
        String orderId,
        Instant occurredAt,
        BigDecimal total
) {}
~~~

Event nên mô tả một sự kiện đã xảy ra, chẳng hạn OrderCreated, thay vì gửi trực tiếp entity JPA hoặc một đối tượng nội bộ có thể thay đổi theo cấu trúc database. eventId hỗ trợ truy vết và chống xử lý trùng; orderId có thể được dùng làm Kafka key.

Ví dụ publisher với Spring Kafka 3.x:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {
        return kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event
        );
    }
}
~~~

Ở ví dụ này, key là orderId và value là event. Các record của cùng một đơn hàng vì vậy thường được định tuyến tới cùng partition theo partitioner mặc định, miễn là số partition và cấu hình phân vùng không thay đổi. Điều này hữu ích khi consumer cần xử lý các thay đổi của một đơn hàng theo thứ tự.

Kết quả trả về từ send cho biết thao tác gửi đã được broker xác nhận hoặc thất bại theo cấu hình producer. Nó không chứng minh consumer đã nhận, xử lý hay commit offset. Nếu nghiệp vụ cần biết trạng thái xử lý ở hệ thống đích, cần có cơ chế phản hồi riêng như event kết quả hoặc trạng thái được lưu trữ.

Khi học producer, hãy lần lượt tìm hiểu:

1. Gửi value đơn giản rồi gửi object đã serialize.
2. Gửi kèm key và quan sát partition được chọn.
3. Đọc kết quả bất đồng bộ để ghi nhận thành công hoặc lỗi.
4. Thêm header như correlation-id hoặc event-type khi cần metadata xuyên dịch vụ.
5. Tìm hiểu các cấu hình như acks, retries, idempotence, batch.size, linger.ms và compression.type.

**Bài thực hành:** tạo API hoặc service phát hành OrderCreatedEvent. Gửi nhiều đơn hàng, xác nhận key và payload trên Kafka, sau đó thử gửi một payload không serialize được để quan sát lỗi. Bổ sung log có eventId, topic, key và kết quả gửi để thuận tiện truy vết.

## 4. Xây dựng consumer với @KafkaListener

Consumer nhận record từ topic và chuyển payload cho logic nghiệp vụ. Với Spring Kafka, cách phổ biến nhất là khai báo phương thức có @KafkaListener.

~~~java
@Component
public class OrderCreatedListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "fulfillment-service"
    )
    public void onOrderCreated(OrderCreatedEvent event) {
        // Gọi logic xử lý đơn hàng tại đây.
    }
}
~~~

Spring Kafka quản lý listener container, poll record từ broker, chuyển đổi payload và gọi phương thức listener. Khi phương thức xử lý ném exception, container và error handler sẽ quyết định cách xử lý tiếp theo theo cấu hình.

Cần hiểu rõ ba lớp hành vi:

- **Nhận record:** consumer poll dữ liệu từ partition được gán.
- **Xử lý record:** listener thực hiện logic nghiệp vụ; một lần gọi có thể thành công hoặc ném lỗi.
- **Commit offset:** Kafka ghi nhận tiến độ của group. Nếu ứng dụng dừng trước khi offset phù hợp được commit, record có thể được đọc lại.

Consumer group là ranh giới tiến độ đọc. Hai instance cùng group chia nhau partition; hai group khác nhau có thể cùng nhận toàn bộ record. Thay đổi group-id cũng đồng nghĩa ứng dụng đang dùng một tiến độ đọc khác.

Cần đặc biệt hiểu **auto-offset-reset**. Giá trị earliest hoặc latest được dùng khi group chưa có offset hợp lệ, hoặc offset đã lưu không còn dùng được. earliest chọn vị trí sớm nhất còn được giữ; latest bắt đầu từ record mới. earliest không có nghĩa là mỗi lần khởi động ứng dụng đều đọc lại toàn bộ topic nếu group đã có offset hợp lệ.

Spring Kafka cung cấp các chế độ xác nhận offset thông qua AckMode, chẳng hạn RECORD, BATCH, MANUAL và MANUAL_IMMEDIATE. Hãy chọn chế độ phù hợp với cách listener xử lý dữ liệu và hiểu thời điểm offset được commit. Với xử lý nghiệp vụ thông thường, cần bảo đảm lỗi trong listener không khiến tiến độ được ghi nhận như thể record đã xử lý thành công.

**Bài thực hành:** chạy hai instance consumer với cùng group-id và quan sát việc phân chia partition. Sau đó đổi group-id của một instance và quan sát group mới đọc luồng độc lập. Dừng ứng dụng giữa lúc xử lý, khởi động lại và kiểm tra khả năng record được giao lại.

## 5. Serialization và thiết kế hợp đồng sự kiện

Kafka lưu byte. Producer và consumer phải thống nhất cách biến object thành byte và ngược lại. Serializer chạy ở phía gửi; deserializer chạy ở phía nhận. Hai bên cấu hình sai hoặc dùng hợp đồng không tương thích sẽ gây lỗi chuyển đổi dù kết nối broker vẫn hoạt động.

Các lựa chọn thường gặp:

| Định dạng | Khi phù hợp | Điểm cần cân nhắc |
|---|---|---|
| String | Nội dung đơn giản, văn bản hoặc payload đã được xử lý riêng | Ứng dụng tự chịu trách nhiệm parse và kiểm tra dữ liệu. |
| JSON | Dễ đọc, dễ tích hợp nhiều ngôn ngữ và phù hợp giai đoạn đầu | Cần quy ước kiểu dữ liệu, field tùy chọn và cách tiến hóa schema. |
| Avro hoặc Protobuf | Hệ thống có hợp đồng dữ liệu chặt chẽ, cần schema và kiểm soát tương thích | Cần quản lý schema và quy trình phát hành phiên bản. |

Khi thiết kế event, nên ưu tiên các trường ổn định như eventId, eventType, occurredAt, aggregateId và schemaVersion nếu hệ thống cần quản lý phiên bản rõ ràng. Payload chỉ nên chứa dữ liệu consumer cần để hiểu sự kiện; tránh gửi mật khẩu, token, thông tin nhạy cảm hoặc toàn bộ entity nội bộ.

Một số nguyên tắc tiến hóa hợp đồng:

- Thêm field mới theo cách consumer cũ có thể bỏ qua hoặc dùng giá trị mặc định.
- Cân nhắc kỹ trước khi đổi tên, xóa field hoặc thay đổi ý nghĩa của field hiện có.
- Phân biệt field không có, field null và field mang giá trị mặc định nếu nghiệp vụ cần.
- Không dùng tên class Java làm hợp đồng liên dịch vụ duy nhất; package hoặc cấu trúc class có thể thay đổi khi tái tổ chức code.
- Có kiểm thử serialization/deserialization bằng payload đại diện cho các phiên bản đang được hỗ trợ.

Với JsonSerializer và JsonDeserializer của Spring Kafka, cần hiểu type headers và trusted packages. Nếu các ứng dụng dùng package hoặc model khác nhau, hãy cấu hình ánh xạ kiểu rõ ràng thay vì phụ thuộc mù quáng vào tên class được gửi trong header.

**Bài thực hành:** tạo event DTO có eventId, orderId và occurredAt; gửi JSON rồi nhận lại thành object. Thêm một field tùy chọn và kiểm tra consumer cũ. Tiếp theo thử một payload sai kiểu hoặc thiếu dữ liệu bắt buộc để quan sát lỗi deserialization và xác định lỗi xảy ra trước hay trong listener.

## 6. Partition, offset, concurrency và thứ tự xử lý

Partition quyết định mức song song ở cấp topic. Consumer group phân phối partition cho các consumer thành viên. Nếu topic có ba partition thì group không thể khai thác hơn ba consumer đang hoạt động để đọc topic đó cùng lúc; consumer dư sẽ không được gán partition của topic này.

Trong Spring Kafka, concurrency của listener container có thể được cấu hình qua listener container factory hoặc cấu hình listener phù hợp với phiên bản đang sử dụng. Khi tăng concurrency, hãy kiểm tra số partition, khả năng xử lý của database và API phụ thuộc, cũng như giới hạn tài nguyên của từng instance.

Không nên nhầm concurrency với thứ tự toàn cục. Kafka giữ thứ tự record trong từng partition. Nếu hai record của cùng aggregate có thể chạy ở hai partition khác nhau, consumer không có cơ sở để bảo đảm thứ tự giữa chúng. Dùng key ổn định như orderId là một cách phổ biến để giữ các sự kiện liên quan trong cùng partition.

Offset là tiến độ đọc của một group trên một partition. Các điểm cần nắm:

- Offset tăng theo record trong partition, không đại diện cho thời gian hoặc thứ tự giữa các partition.
- Consumer có thể đọc trước vị trí đã commit; vị trí đọc và vị trí đã commit là hai khái niệm khác nhau.
- Nếu xử lý xong nhưng dừng trước commit, record có thể được giao lại.
- Nếu commit trước khi xử lý hoàn tất, lỗi sau đó có thể khiến ứng dụng bỏ qua record khi đọc tiếp.
- Rebalance có thể xảy ra khi consumer tham gia, rời group hoặc khi việc poll không đáp ứng giới hạn cấu hình.

Vì vậy, handler nên có khả năng xử lý lặp an toàn. Một cách thường dùng là lưu eventId đã xử lý hoặc dùng khóa nghiệp vụ có ràng buộc duy nhất trong database. Khi record được giao lại, ứng dụng nhận ra sự kiện đã hoàn tất và không lặp lại tác động nghiệp vụ.

**Bài thực hành:** chạy nhiều consumer với các cấu hình concurrency khác nhau. Ghi log topic, partition, offset, key và eventId để quan sát cách phân công. Tạo một consumer xử lý chậm để theo dõi lag và thử tăng số partition hoặc concurrency; ghi lại giới hạn thực tế của hệ thống.

## 7. Retry và dead-letter topic

Lỗi khi tiêu thụ sự kiện có thể là tạm thời hoặc không thể khắc phục bằng cách thử lại. Ví dụ timeout tới dịch vụ phụ thuộc có thể hết sau vài giây; payload thiếu field bắt buộc thường sẽ tiếp tục lỗi dù thử lại nhiều lần.

Cần phân loại lỗi trước khi thiết kế retry:

- **Lỗi tạm thời:** timeout, kết nối bị gián đoạn, dịch vụ phụ thuộc tạm thời không sẵn sàng. Có thể thử lại với khoảng nghỉ.
- **Lỗi dữ liệu hoặc nghiệp vụ không thể xử lý:** payload sai định dạng, thiếu dữ liệu bắt buộc, trạng thái không hợp lệ. Thường nên chuyển sang luồng xử lý lỗi sau số lần thử phù hợp.
- **Lỗi lập trình:** null ngoài dự kiến, lỗi mapping hoặc bug. Retry không sửa được bug; cần log, cảnh báo và sửa nguyên nhân.

Spring Kafka hỗ trợ error handler cho listener container, chẳng hạn DefaultErrorHandler kết hợp BackOff và DeadLetterPublishingRecoverer. Một cấu hình minh họa:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1000L, 2L);
    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(IllegalArgumentException.class);
    return handler;
}
~~~

Trong ví dụ, record được thử lại với khoảng nghỉ một giây theo số lần cấu hình; khi phục hồi thất bại, recoverer chuyển record sang dead-letter topic theo quy tắc định tuyến mặc định hoặc quy tắc do ứng dụng cung cấp. Cần cấu hình serializer cho DLT phù hợp với kiểu record thực tế và bảo đảm topic đích tồn tại, có đủ partition tương ứng khi cách định tuyến yêu cầu điều đó.

Một hướng khác là retry topic, có thể cấu hình bằng @RetryableTopic và xử lý bản ghi cuối cùng bằng @DltHandler. Retry topic phù hợp khi muốn trì hoãn lần thử tiếp theo mà không giữ partition chính bị chặn trong suốt thời gian chờ. Tuy nhiên, cách này có thể làm thay đổi thứ tự quan sát được giữa các sự kiện liên quan: một record bị chuyển sang retry topic trong khi record sau tiếp tục được xử lý ở topic chính.

Hãy lựa chọn theo yêu cầu nghiệp vụ:

| Cách xử lý | Ưu điểm | Đánh đổi |
|---|---|---|
| Retry tại listener container | Cấu hình trực tiếp, dễ giữ luồng partition trong quá trình thử lại | Partition có thể bị chặn bởi record đang lỗi. |
| Retry topic | Có thể trì hoãn và tách lần thử khỏi luồng chính | Cần quản lý nhiều topic; thứ tự xử lý có thể thay đổi. |
| Chuyển thẳng sang DLT | Cô lập nhanh record không xử lý được | Cần quy trình kiểm tra, sửa dữ liệu và phát lại. |

DLT không phải nơi để bỏ quên dữ liệu. Một quy trình vận hành tốt cần ghi nhận nguyên nhân, topic gốc, partition, offset, key, eventId và thời điểm lỗi; theo dõi số lượng record trong DLT; xác định người hoặc hệ thống chịu trách nhiệm xử lý; đồng thời có chính sách phát lại sau khi nguyên nhân được khắc phục. Trước khi replay, cần xác nhận consumer có thể xử lý lặp an toàn và tránh tạo tác động nghiệp vụ trùng.

**Bài thực hành:** tạo một lỗi tạm thời để kiểm tra số lần retry và khoảng nghỉ. Tạo một payload không hợp lệ để chuyển vào DLT. Kiểm tra metadata của record lỗi, sửa nguyên nhân rồi phát lại một cách có kiểm soát. Thử cả retry tại container và retry topic để so sánh ảnh hưởng tới thứ tự.

## 8. Transaction và phạm vi của exactly-once

Transaction trong Kafka giúp nhóm nhiều thao tác ghi Kafka thành một đơn vị: hoặc các record trong transaction được commit, hoặc bị loại bỏ khi transaction abort. Trong luồng consume-transform-produce, Kafka có thể phối hợp việc ghi record đầu ra với việc commit offset đầu vào để tránh trường hợp đầu ra đã được ghi nhưng offset đầu vào chưa được cập nhật, hoặc ngược lại.

Spring Kafka hỗ trợ transaction thông qua producer transaction và KafkaTransactionManager. Với Spring Boot, có thể cấu hình transaction-id-prefix cho producer. Prefix cần duy nhất giữa các instance đang chạy để tránh xung đột transactional identity. Consumer đọc dữ liệu transactional thường cần isolation.level phù hợp, chẳng hạn read_committed, để chỉ thấy các transaction đã commit.

Cần phân biệt ba phạm vi:

1. **Transaction của Kafka:** bảo vệ nhóm thao tác đọc/ghi Kafka trong phạm vi cơ chế transaction mà Kafka hỗ trợ.
2. **Transaction của database:** bảo vệ các thay đổi trong database theo transaction của database.
3. **Tác động bên ngoài:** gọi HTTP, gửi email hoặc thao tác trên hệ thống không tham gia transaction Kafka.

Exactly-once trong Kafka không tự động biến toàn bộ nghiệp vụ phân tán thành exactly-once. Nếu listener ghi database rồi bị dừng trước khi offset được commit, record có thể được giao lại và câu lệnh database có thể chạy lần nữa. Nếu listener gọi một API bên ngoài rồi timeout, ứng dụng cũng có thể không biết phía nhận đã thực hiện tác động hay chưa.

Để bảo vệ nghiệp vụ qua ranh giới hệ thống, thường cần kết hợp:

- **Idempotency:** cùng một eventId hoặc idempotency key chỉ tạo ra một tác động nghiệp vụ.
- **Inbox pattern:** lưu dấu sự kiện đã nhận trong cùng transaction với thay đổi dữ liệu nghiệp vụ.
- **Outbox pattern:** ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction database; một tiến trình riêng phát bản ghi outbox sang Kafka.
- **Đối soát:** phát hiện và xử lý các trạng thái không nhất quán mà không thể loại bỏ hoàn toàn bằng transaction cục bộ.

**Bài thực hành:** xây dựng luồng consume-transform-produce, trong đó consumer nhận OrderCreatedEvent và phát InventoryReservedEvent. Kiểm tra transaction khi xử lý thành công và khi chủ động abort. Sau đó thêm một thao tác database để thấy rõ vì sao transaction Kafka không tự bao phủ thay đổi database; thiết kế idempotency hoặc outbox/inbox cho phần nghiệp vụ đó.

## 9. Kiểm thử luồng messaging

Một ứng dụng messaging không thể chỉ kiểm tra rằng phương thức publisher được gọi. Cần xác nhận record thật sự được gửi, được deserialize, được consumer xử lý, offset được quản lý đúng và lỗi được chuyển tới nơi dự kiến.

Có thể chia kiểm thử thành các lớp:

| Lớp kiểm thử | Nội dung xác minh |
|---|---|
| Unit test | Logic nghiệp vụ độc lập với Kafka; dùng mock cho collaborator khi phù hợp. |
| Serialization test | Payload được serialize/deserialize đúng, tương thích với hợp đồng sự kiện. |
| Integration test | Producer, broker, listener container và consumer hoạt động cùng nhau. |
| Failure-path test | Retry, DLT, lỗi deserialize, lỗi listener và khả năng phát lại. |
| Reliability test | Xử lý trùng, dừng consumer, rebalance và phục hồi sau lỗi. |

Spring Kafka có hỗ trợ EmbeddedKafka để kiểm thử tích hợp. Testcontainers là lựa chọn phù hợp khi muốn chạy broker thật trong môi trường test và kiểm tra gần với môi trường triển khai. Chọn công cụ theo độ tin cậy cần thiết và chi phí chạy test của dự án.

Khi kiểm thử bất đồng bộ, tránh dùng Thread.sleep với thời gian cố định để đoán lúc consumer đã xử lý xong. Hãy chờ một điều kiện cụ thể với timeout hợp lý, ví dụ dùng Awaitility hoặc cơ chế đồng bộ tương đương. Timeout giúp test kết thúc rõ ràng khi hệ thống không đạt kết quả mong đợi.

Các tình huống tối thiểu nên có:

- Producer gửi đúng topic, key, header và payload.
- Consumer nhận đúng kiểu dữ liệu và thực hiện đúng logic.
- Hai consumer group đọc độc lập cùng một topic.
- Listener lỗi dẫn đến retry hoặc DLT theo cấu hình.
- Record được giao lại không tạo tác động nghiệp vụ trùng.
- Payload không tương thích được xử lý và quan sát rõ ràng.
- Luồng transaction commit và abort cho kết quả mong đợi.

**Bài thực hành:** viết integration test cho OrderEventPublisher và OrderCreatedListener bằng EmbeddedKafka hoặc Testcontainers. Dùng Awaitility để chờ kết quả, sau đó bổ sung test cho retry, DLT và xử lý lặp.

## 10. Quan sát và chuẩn bị vận hành

Khi chạy thực tế, cần biết producer có gửi được record hay không, consumer có theo kịp tốc độ phát sinh hay không và record lỗi đang nằm ở đâu. Một số tín hiệu nên theo dõi:

- **Consumer lag:** chênh lệch giữa vị trí record mới nhất và tiến độ đã commit của group trên từng partition. Lag tăng liên tục có thể cho thấy consumer xử lý chậm hoặc không hoạt động.
- **Tốc độ gửi và nhận:** số record mỗi giây, kích thước payload và độ trễ từ lúc phát hành tới lúc xử lý.
- **Lỗi producer:** timeout, lỗi metadata, lỗi xác thực, lỗi serialize và số lần gửi thất bại.
- **Lỗi consumer:** exception theo loại, thời gian xử lý, rebalance, số lần retry và số record vào DLT.
- **Tài nguyên:** CPU, bộ nhớ, kết nối mạng, thread và khả năng đáp ứng của database hoặc dịch vụ phụ thuộc.

Log nên có topic, partition, offset, key, eventId, consumer group và correlation-id khi có thể. Không ghi toàn bộ payload nếu payload có dữ liệu cá nhân, bí mật hoặc dung lượng lớn. Metric và log cần giúp tìm được một record cụ thể mà không làm lộ dữ liệu.

Khi chuẩn bị production, cần xem xét replication factor, min.insync.replicas, acks, idempotence, retention, số partition, giới hạn kích thước record, bảo mật TLS/SASL và ACL. Các cấu hình như batch.size, linger.ms, compression.type, max.poll.records hay max.poll.interval.ms nên được điều chỉnh dựa trên số liệu tải và đặc tính xử lý, không sao chép máy móc từ một ví dụ.

## 11. Bài tập tổng hợp: luồng sự kiện đơn hàng

Sau khi hoàn thành từng chặng, hãy ghép chúng thành một luồng nghiệp vụ nhỏ:

~~~mermaid
flowchart TD
    API[Order API] --> PUB[KafkaTemplate]
    PUB --> OC[orders.created]
    OC --> INV[Consumer group: inventory]
    OC --> PAY[Consumer group: payment]
    INV --> IR[inventory.reserved]
    INV --> ID[inventory DLT khi lỗi]
    PAY --> PA[payment.authorized]
    PAY --> PD[payment DLT khi lỗi]
~~~

Yêu cầu triển khai:

1. Order API phát OrderCreatedEvent với eventId và orderId; dùng orderId làm key.
2. Inventory service và Payment service dùng hai consumer group riêng để cùng nhận OrderCreatedEvent.
3. Inventory service phát InventoryReservedEvent hoặc ghi nhận lỗi theo chính sách retry/DLT.
4. Payment service phát PaymentAuthorizedEvent hoặc chuyển record lỗi sang DLT.
5. Mỗi consumer lưu dấu eventId đã xử lý để chống tác động trùng.
6. Viết integration test cho luồng thành công, lỗi tạm thời, lỗi không thể retry và phát lại DLT.
7. Ghi log có correlation-id để theo dõi một đơn hàng qua các service.
8. Theo dõi lag và số lượng record trong retry topic/DLT khi tạo tải thử.

Không cần triển khai mọi mẫu transaction ngay từ đầu. Hãy hoàn thành luồng gửi/nhận và kiểm thử cơ bản trước, rồi thêm idempotency, retry, DLT và transaction theo từng bước. Nếu cần ghi dữ liệu database và phát event một cách nhất quán, hãy mở rộng bài tập bằng outbox pattern.

## 12. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung trọng tâm | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Nền tảng Kafka | Topic, partition, key, offset, consumer group | Giải thích được vì sao thứ tự chỉ được bảo đảm trong một partition. |
| 2. Môi trường Spring Kafka | Dependency, bootstrap server, cấu hình producer/consumer | Ứng dụng kết nối broker và tạo được topic. |
| 3. Producer | KafkaTemplate, key, header, callback | Gửi event và xác minh được kết quả gửi. |
| 4. Consumer | @KafkaListener, group-id, offset, AckMode | Nhận event, hiểu commit và kiểm tra được hành vi đọc lại. |
| 5. Serialization | JSON, serializer/deserializer, schema evolution | Hai phía trao đổi payload đúng và xử lý được thay đổi hợp đồng. |
| 6. Concurrency | Partition assignment, concurrency, ordering, lag | Giải thích được giới hạn song song và quan sát được phân công partition. |
| 7. Reliability | Retry, DLT, replay, idempotency | Phân loại lỗi và xử lý record lỗi theo chính sách rõ ràng. |
| 8. Consistency | Kafka transaction, exactly-once, outbox/inbox | Nêu đúng phạm vi transaction và bảo vệ được tác động nghiệp vụ khi giao lại. |
| 9. Testing và operations | EmbeddedKafka/Testcontainers, metrics, logs, security | Có test cho luồng thành công và thất bại; biết theo dõi lag và DLT. |

Có thể coi lộ trình hoàn thành khi bạn tự xây dựng được một ứng dụng có producer, ít nhất một consumer group, payload có hợp đồng rõ ràng, xử lý lỗi có retry/DLT, cơ chế chống xử lý trùng, integration test và log/metric đủ để truy vết. Quan trọng hơn, bạn cần giải thích được điều gì xảy ra khi consumer dừng giữa lúc xử lý, khi partition được phân công lại, khi record lỗi liên tục hoặc khi database đã cập nhật nhưng offset Kafka chưa commit.

Spring Kafka giúp tích hợp messaging vào ứng dụng Spring, còn độ tin cậy của luồng sự kiện phụ thuộc vào cách thiết kế key, hợp đồng dữ liệu, offset, retry, idempotency, transaction và kiểm thử. Học tuần tự các phần này sẽ tạo nền tảng để phát triển hệ thống xử lý sự kiện có thể mở rộng và vận hành được.

