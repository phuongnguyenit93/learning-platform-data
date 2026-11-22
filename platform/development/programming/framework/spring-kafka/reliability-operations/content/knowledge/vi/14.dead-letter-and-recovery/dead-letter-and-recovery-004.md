# Chọn DLT theo topic và partition trong Spring Kafka

Trong Spring Kafka, **Dead Letter Topic (DLT)** là nơi lưu lại record không thể xử lý thành công sau các lần retry hoặc gặp lỗi được phân loại không nên retry. Khi xây dựng một hệ thống Kafka có khả năng phục hồi, không chỉ cần quyết định *khi nào* record được đưa vào DLT mà còn phải quyết định **DLT topic nào nhận record và partition nào sẽ chứa record đó**.

Một lựa chọn định tuyến DLT tốt cần đáp ứng đồng thời ba mục tiêu: không làm mất record chưa xử lý được, giữ đủ ngữ cảnh để điều tra hoặc replay, và không tạo thêm sự cố vì số partition, serializer, ACL hoặc thứ tự xử lý không phù hợp.

Spring Kafka cung cấp DeadLetterPublishingRecoverer và một destination resolver để chọn TopicPartition cho record lỗi. Với cơ chế non-blocking retry dựa trên @RetryableTopic hoặc RetryTopicConfiguration, framework cũng tạo topology retry/DLT và có các tùy chọn riêng để định tuyến đích. Hai cơ chế này liên quan nhưng không nên xem chúng có cùng quy tắc đặt tên hoặc cùng cấu hình mặc định.

## 1. DLT nằm ở đâu trong luồng xử lý lỗi?

Một consumer thường xử lý record theo luồng:

~~~text
Producer
   |
   v
orders.events (topic nguồn)
   |
   v
Spring Kafka consumer
   |
   v
@KafkaListener
   |
   +--> thành công
   |       |
   |       v
   |   Tiến offset theo ack mode
   |
   +--> exception
           |
           v
    DefaultErrorHandler
           |
           +--> retry với BackOff
           |        |
           |        +--> retry thành công
           |
           +--> hết retry / non-retryable
                         |
                         v
             DeadLetterPublishingRecoverer
                         |
                         +--> Chọn topic đích
                         |
                         +--> Chọn partition đích
                         |
                         v
                   DLT record
~~~

Trong trường hợp dùng DefaultErrorHandler, recoverer được gọi khi error handler quyết định record không còn được xử lý lại tại topic nguồn. Nếu gửi DLT thành công và recovery được xem là hoàn tất, container có thể tiến offset theo acknowledgement và error-handling policy. Nếu gửi DLT thất bại, không nên coi record đã được recovery an toàn.

**DLT không phải dấu hiệu nghiệp vụ thành công.** Nó là một nơi lưu dữ liệu cần xử lý tiếp. Record ở DLT phải có quy trình giám sát, điều tra, sửa nguyên nhân, replay hoặc đóng sự cố theo quyết định của người vận hành.

## 2. Topic và partition có ý nghĩa khác nhau

Trong Kafka, topic chứa nhiều partition. Partition xác định một log có thứ tự offset riêng. Mỗi consumer trong cùng consumer group được gán các partition để đọc.

Ví dụ:

~~~text
orders.events
   |
   +--> partition 0: offset 100, 101, 102, ...
   +--> partition 1: offset 210, 211, 212, ...
   +--> partition 2: offset  80,  81,  82, ...

orders.events.DLT
   |
   +--> partition 0: offset  10,  11, ...
   +--> partition 1: offset   5,   6, ...
   +--> partition 2: offset  20,  21, ...
~~~

Nếu record lỗi đến từ orders.events, partition 2, offset 81, ta có hai thông tin riêng:

- **Nguồn:** orders.events / partition 2 / offset 81.
- **Đích:** ví dụ orders.events.DLT / partition 2 / một offset mới của DLT.

Offset tại DLT **không phải offset của topic nguồn**. Kafka cấp một offset mới khi append record vào DLT partition. Khi điều tra cần dùng metadata nguồn trong headers hoặc một trường audit, không suy ra offset nguồn từ offset DLT.

Một TopicPartition đích gồm tên topic và số partition. Quyết định này ảnh hưởng tới khả năng gửi thành công, cách tổ chức DLT consumers, thứ tự trong DLT và quy trình replay.

## 3. Hành vi mặc định của DeadLetterPublishingRecoverer

Trong cấu hình DefaultErrorHandler phổ biến, DeadLetterPublishingRecoverer mặc định tạo tên topic đích bằng cách nối hậu tố **.DLT** vào tên topic nguồn, đồng thời chọn **cùng số partition** như record nguồn.

~~~text
Topic nguồn                     DLT mặc định
-----------------------------   -----------------------------
orders.events / partition 0 -> orders.events.DLT / partition 0
orders.events / partition 1 -> orders.events.DLT / partition 1
orders.events / partition 2 -> orders.events.DLT / partition 2

payments.events / partition 3 -> payments.events.DLT / partition 3
~~~

Cấu hình cơ bản:

~~~java
@Bean
DefaultErrorHandler orderErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
    );
}
~~~

Ở đây, FixedBackOff(1000, 2) cho phép hai lần retry sau lần xử lý đầu tiên, cách nhau một giây. Sau khi hết retry, recoverer chọn DLT theo mặc định.

### Điều kiện khi giữ nguyên partition

Nếu DLT dùng **cùng số partition**, DLT phải có partition tương ứng với mọi partition nguồn có thể được định tuyến tới đó.

Ví dụ topic nguồn có sáu partition (0 đến 5), DLT chỉ có ba partition (0 đến 2). Khi một record lỗi ở nguồn partition 5 được gửi đích đến partition 5, producer không thể giả định partition 5 tồn tại trên DLT.

Một số phiên bản Spring Kafka có cơ chế kiểm tra hoặc điều chỉnh partition đích khi destination không tồn tại, nhưng không nên dựa vào hành vi cứu hộ ngầm. Hãy chủ động provision đúng số partition hoặc chọn partition tự động và kiểm thử trên phiên bản framework đang chạy.

Giữ nguyên partition giúp tổ chức DLT theo vị trí nguồn nhưng không làm hai log có chung offset, cũng không tạo một transaction hay exactly-once guarantee giữa chúng.

## 4. Tự chọn destination bằng BiFunction

DeadLetterPublishingRecoverer cho phép truyền một hàm nhận ConsumerRecord và Exception để trả về TopicPartition:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    dltTemplate,
                    (record, exception) -> new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()
                    )
            );

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
    );
}
~~~

Resolver nhận hai thông tin:

- record: topic nguồn, partition, offset, key, value, headers và timestamp của record lỗi.
- exception: lỗi được error handler chuyển đến recoverer.

Resolver trả về TopicPartition thể hiện **đích cần publish**, không phải một chỉ dẫn về consumer offset. Logic chọn destination thường nên thuần túy, nhanh, dễ quan sát và không gọi HTTP/database trên thread consumer.

Có thể thay công thức record.topic() + ".DLT" bằng tên cố định, bảng mapping theo topic hoặc quy tắc theo loại lỗi. Nhưng topic đích phải là một topic hợp lệ đã tồn tại hoặc có thể được tạo bằng cơ chế quản trị đã thiết kế.

## 5. Chọn partition: giữ nguyên hay để producer tự chọn?

Đây là quyết định cốt lõi khi thiết kế DLT.

### Phương án A: giữ partition nguồn

~~~java
(record, exception) -> new TopicPartition(
        record.topic() + ".DLT",
        record.partition()
)
~~~

Ưu điểm:

- Dễ xem mỗi partition nguồn tương ứng với partition DLT nào.
- Thuận tiện phân vùng tải hoặc điều tra theo partition.
- Phù hợp khi DLT được provision với số partition đủ và sơ đồ partition không thay đổi bất ngờ.

Đánh đổi:

- DLT phải có ít nhất những partition được tham chiếu.
- Khi số partition của topic nguồn tăng, cấu hình DLT cần được cập nhật tương ứng.
- Nếu nhiều topic nguồn cùng đổ về một DLT, partition số 2 của các topic khác nhau sẽ hội tụ về cùng partition số 2 của DLT; điều này không tạo thứ tự toàn cục.

### Phương án B: để producer chọn partition

Trong destination resolver của DeadLetterPublishingRecoverer, trả về **partition âm, thường là -1**, để tạo ProducerRecord không có partition được chỉ định; Kafka producer sẽ chọn partition đích theo cơ chế partitioner/client và key.

~~~java
(record, exception) -> new TopicPartition(
        record.topic() + ".DLT",
        -1
)
~~~

Ưu điểm:

- DLT có thể có số partition khác với nguồn.
- Thuận tiện khi nhiều topic nguồn dùng chung một DLT.
- Có thể để Kafka phân phối record dựa trên key hoặc chiến lược producer đang dùng.

Đánh đổi:

- Không còn bảo đảm DLT partition trùng với partition nguồn.
- DLT consumer phải dựa vào headers metadata để biết partition nguồn.
- Sự phân phối phụ thuộc Kafka producer, serializer, key và phiên bản partitioning logic; không nên hứa một partition cụ thể.

**-1 không có nghĩa là ghi vào partition -1 trên broker.** Nó là tín hiệu cho recoverer không ép partition đích khi xây ProducerRecord. Kafka topic không có partition âm.

### Bảng lựa chọn

| Nhu cầu | Phương án thường phù hợp |
|---|---|
| Một DLT riêng cho một topic nguồn với số partition đồng bộ | Giữ partition nguồn |
| DLT ít partition hơn nguồn | Dùng -1 hoặc thiết kế mapping hợp lệ |
| Nhiều topic nguồn chia sẻ một DLT | Thường chọn -1 |
| Phải phục hồi theo partition nguồn | Giữ partition hoặc lưu metadata đầy đủ |
| Muốn phân phối DLT theo Kafka key | Dùng -1 với key ổn định |
| Cần kiểm soát chính xác số partition đích | Resolver trả về partition hợp lệ, có kiểm thử |

## 6. Chọn DLT riêng cho từng topic nguồn

Một chính sách phổ biến là mỗi topic nguồn có DLT riêng.

~~~text
orders.created  ------------> orders.created.DLT
orders.cancelled ------------> orders.cancelled.DLT
payments.events ------------> payments.events.DLT
notifications.email --------> notifications.email.DLT
~~~

Ưu điểm:

- Tách biệt quyền truy cập theo nghiệp vụ.
- Retention và cảnh báo có thể đặt theo mức độ quan trọng.
- Không trộn payload/serializer của các event không tương thích.
- Điều tra và replay dễ biết event xuất phát từ luồng nào.

Nhược điểm:

- Tăng số lượng topic cần quản trị.
- Mỗi topic phải có partition, replication, ACL, retention và monitoring.
- Tổ chức có nhiều topic nhỏ sẽ cần tự động hóa provision và ownership.

Ví dụ resolver tường minh:

~~~java
(record, exception) -> switch (record.topic()) {
    case "orders.created" ->
            new TopicPartition("orders.created.DLT", record.partition());

    case "payments.events" ->
            new TopicPartition("payments.events.DLT", record.partition());

    default ->
            new TopicPartition("platform.unknown.DLT", -1);
}
~~~

Ví dụ dùng Java switch expression. Với Java version cũ hơn, có thể dùng if/else hoặc Map. Việc định tuyến unknown topic cần có chủ đích: có thể từ chối cấu hình chưa được khai báo hoặc đưa đến một DLT dùng chung đã được provision và giám sát.

Không lấy nguyên một header bất kỳ từ record rồi coi đó là tên DLT để publish. Header có thể do producer gửi và không đáng tin; topic đích nên đến từ allowlist do ứng dụng quản lý.

## 7. Một DLT chung cho nhiều topic nguồn

Trong một số hệ thống, nhiều luồng có cùng quy trình xử lý lỗi có thể dùng một DLT tập trung:

~~~text
orders.created -------+
orders.cancelled ------+--> platform.events.DLT
notifications.email ---+
~~~

Ví dụ:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                dltTemplate,
                (record, exception) -> new TopicPartition(
                        "platform.events.DLT",
                        -1
                )
        );
~~~

Một DLT chung giảm số topic nhưng tạo thêm yêu cầu:

1. DLT consumer phải nhận diện event type/schema tương ứng.
2. Producer serializer phải hỗ trợ nhiều loại payload.
3. DLT cần partition count và throughput đủ cho tổng lưu lượng lỗi.
4. ACL và retention phải đáp ứng loại dữ liệu nhạy cảm nhất được đưa vào DLT.
5. Monitoring phải phân tách lỗi theo topic nguồn, không chỉ topic DLT.
6. Replay phải định tuyến ngược về đúng topic nguồn theo metadata đã được xác minh.

Nếu chung DLT nhưng payload là nhiều class Java khác nhau, hãy dùng serializer phù hợp hoặc chuẩn hóa envelope. Nếu có record deserialize thất bại chứa raw bytes, cần xử lý thêm dạng byte[] thay vì giả định tất cả value đều là object domain.

**Tập trung topic không đồng nghĩa tập trung trách nhiệm nghiệp vụ.** Mỗi loại sự kiện vẫn cần người sở hữu, SLA và quy trình phục hồi riêng.

## 8. Định tuyến theo exception

Có thể chọn DLT không chỉ dựa vào topic nguồn mà còn dựa trên loại lỗi.

Ví dụ:

~~~text
orders.events
    |
    +--> InvalidOrderEventException --> orders.invalid.DLT
    |
    +--> AuthorizationException ---> security.events.DLT
    |
    +--> Lỗi retryable đã hết lượt --> orders.failed.DLT
~~~

Resolver minh họa:

~~~java
@Bean
DefaultErrorHandler classifiedErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(
                    dltTemplate,
                    (record, exception) -> {

                        Throwable root = exception;
                        while (root.getCause() != null
                                && root.getCause() != root) {
                            root = root.getCause();
                        }

                        if (root instanceof InvalidOrderEventException) {
                            return new TopicPartition(
                                    "orders.invalid.DLT", -1);
                        }

                        if (root instanceof UnauthorizedEventException) {
                            return new TopicPartition(
                                    "security.events.DLT", -1);
                        }

                        return new TopicPartition(
                                record.topic() + ".DLT",
                                record.partition()
                        );
                    }
            );

    DefaultErrorHandler handler =
            new DefaultErrorHandler(
                    recoverer,
                    new FixedBackOff(2_000L, 3L)
            );

    handler.addNotRetryableExceptions(
            InvalidOrderEventException.class,
            UnauthorizedEventException.class
    );

    return handler;
}
~~~

Logic trên dùng root cause để minh họa phân loại; trong một số dự án, exception domain quan trọng nằm ở lớp giữa của cause chain chứ không phải nguyên nhân sâu nhất. Khi đó, nên dùng một classifier có quy tắc rõ ràng thay vì chỉ so sánh root cause.

Chọn DLT theo exception hữu ích vì:

- Có thể đặt ACL/retention chặt hơn cho lỗi bảo mật.
- Có thể giao DLT invalid payload cho nhóm producer/schema.
- Có thể theo dõi riêng lỗi tạm thời hết retry và lỗi dữ liệu cố định.

Đánh đổi là số lượng topic và quy trình vận hành tăng lên. Nếu mỗi exception class tạo một topic riêng, số topic có thể phát triển không kiểm soát. Thường nên phân loại thành một số nhóm lỗi hữu hạn.

## 9. Topic mapping nên dựa trên nghiệp vụ, không dựa vào input tùy ý

Một sai lầm phổ biến là lấy tenantId, eventType hoặc một chuỗi do producer gửi để ghép tên DLT:

~~~java
// Tránh định tuyến topic bằng một chuỗi tự do từ payload hoặc header.
String target = "dlt." + tenantIdFromUntrustedEvent;
~~~

Một nguồn gửi lỗi hoặc cố ý gây hại có thể tạo vô số tên topic, làm tốn metadata broker hoặc chuyển dữ liệu vào topic không có ACL phù hợp.

Thay vào đó:

- Quản lý danh sách destination topics trong configuration.
- Dùng mapping tường minh từ topic nguồn sang DLT.
- Với nhiều tenant, nhóm theo policy hữu hạn thay vì topic theo tenant tùy ý.
- Kiểm tra quyền của nguồn gửi trước khi dùng dữ liệu điều khiển.
- Không ghi dữ liệu nhạy cảm vào DLT có retention hoặc ACL lỏng hơn topic nguồn.
- Đặt chính sách fallback rõ ràng cho topic chưa được hỗ trợ.

Khi nhiều tenant chung một DLT, cần bảo đảm người đọc DLT không thể thấy thông tin của tenant khác ngoài phạm vi được cấp phép.

## 10. Cấu hình DefaultErrorHandler và destination resolver hoàn chỉnh

Ví dụ sau minh họa một chính sách kết hợp topic và partition.

~~~java
@Configuration
public class KafkaFailureConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> dltTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        dltTemplate,
                        (record, exception) -> {
                            String sourceTopic = record.topic();

                            if ("orders.events".equals(sourceTopic)) {
                                return new TopicPartition(
                                        "orders.events.DLT",
                                        record.partition()
                                );
                            }

                            if ("notifications.email".equals(sourceTopic)) {
                                return new TopicPartition(
                                        "notifications.email.DLT",
                                        -1
                                );
                            }

                            return new TopicPartition(
                                    "platform.general.DLT",
                                    -1
                            );
                        }
                );

        DefaultErrorHandler handler =
                new DefaultErrorHandler(
                        recoverer,
                        new FixedBackOff(1_000L, 2L)
                );

        handler.addNotRetryableExceptions(
                InvalidEventException.class
        );

        return handler;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderListenerContainerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            DefaultErrorHandler kafkaErrorHandler) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setCommonErrorHandler(kafkaErrorHandler);
        return factory;
    }
}
~~~

Cấu hình minh họa các lựa chọn:

- orders.events giữ nguyên partition trên DLT.
- notifications.email để producer tự chọn partition DLT.
- Topic chưa nằm trong mapping được đưa vào DLT chung.
- InvalidEventException không phải chờ đủ hai lần retry.
- DefaultErrorHandler áp dụng recovery sau khi retry hết hoặc gặp lỗi non-retryable.

Các class OrderEvent, InvalidEventException và cấu hình serializer thuộc ứng dụng. Nếu nhiều listener có payload khác nhau, cần tổ chức ConsumerFactory/ContainerFactory tương ứng; không giả định một factory với generic OrderEvent có thể xử lý tất cả topic.

**Quan trọng:** Code trên chỉ cấu hình recoverer; nó không tự tạo các DLT topic, ACL hay serializer phù hợp. Những thành phần đó phải được cấu hình riêng.

## 11. Provision DLT topic và kiểm soát partition count

Nếu quyết định giữ partition nguồn, hãy provision DLT với partition count tương ứng ngay từ đầu.

Ví dụ dùng KafkaAdmin và NewTopic:

~~~java
@Configuration
public class DltTopicConfiguration {

    @Bean
    NewTopic ordersDlt() {
        return TopicBuilder.name("orders.events.DLT")
                .partitions(6)
                .replicas(3)
                .build();
    }

    @Bean
    NewTopic notificationsDlt() {
        return TopicBuilder.name("notifications.email.DLT")
                .partitions(3)
                .replicas(3)
                .build();
    }
}
~~~

Các con số là ví dụ. Cluster cần đủ broker cho replication factor ba. Trong môi trường production, có thể provision bằng IaC hoặc công cụ quản trị thay vì tự động tạo topic khi ứng dụng khởi động.

Hãy theo dõi thay đổi partition count của topic nguồn. Nếu orders.events tăng từ 6 lên 12 partition nhưng orders.events.DLT vẫn chỉ có 6 partition, resolver giữ nguyên partition có thể chọn một destination không tồn tại.

Một số hướng xử lý:

- Tăng partition count của DLT theo nguồn trước hoặc cùng lúc.
- Chọn -1 để Kafka producer tự chọn partition đích.
- Dùng một mapping hợp lệ đã thiết kế rõ ràng, thay vì giả định trùng partition.

Không giảm partition count Kafka topic như một phương án sửa chữa đơn giản; Kafka không hỗ trợ giảm số partition theo cách vận hành thông thường.

## 12. Metadata nguồn cần được bảo toàn

Khi record đi sang DLT, phục hồi cần biết nó xuất phát từ đâu, vì offset của DLT khác offset nguồn.

DeadLetterPublishingRecoverer có thể bổ sung các headers DLT liên quan tới record và exception, như:

- Tên topic gốc.
- Partition gốc.
- Offset gốc.
- Timestamp gốc.
- Exception class.
- Exception message và stack trace theo cấu hình/phiên bản.
- Nhóm thông tin consumer group hoặc metadata bổ sung tùy phiên bản.

Spring Kafka dùng các tên header được chuẩn hóa trong framework, ví dụ nhóm KafkaHeaders.DLT_ORIGINAL_TOPIC, DLT_ORIGINAL_PARTITION và DLT_ORIGINAL_OFFSET. Kiểm tra tên header và cách lấy giá trị theo dependency thực tế.

Một DLT record có thể có:

~~~text
Destination:
  topic       = orders.events.DLT
  partition   = 2
  offset      = 55

Original metadata:
  topic       = orders.events
  partition   = 2
  offset      = 1042
  eventId     = evt-812
  exception   = InvalidEventException
~~~

Trong ví dụ, offset 55 là vị trí trong DLT; offset 1042 là vị trí trong nguồn. Khi replay, phải lấy topic nguồn và event ID từ metadata đã được xác minh.

Nếu sử dụng một DLT chung, lưu metadata nguồn là bắt buộc về mặt vận hành; nếu thiếu, operator khó biết phải chuyển record về topic nào.

## 13. DLT khi deserialization thất bại

Một record có thể bị lỗi trước khi listener nhận được payload, ví dụ JSON hỏng hoặc type header không hợp lệ. Khi dùng ErrorHandlingDeserializer, Spring Kafka có thể lưu thông tin lỗi deserialize để container error handler và recoverer xử lý.

Ví dụ cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.key.delegate.class]": org.apache.kafka.common.serialization.StringDeserializer
        "[spring.deserializer.value.delegate.class]": org.springframework.kafka.support.serializer.JsonDeserializer
        "[spring.json.trusted.packages]": com.example.events
~~~

Với record lỗi deserialize, dữ liệu value gốc có thể cần được xuất sang DLT dưới dạng byte[] thay vì domain object. DLT KafkaTemplate cần có serializer đáp ứng kiểu dữ liệu này.

Nếu dùng một template JSON cho mọi record, cần xác minh cách nó serialize byte[] và cách DLT consumer đọc lại raw payload. Có thể dùng serializer phân loại theo kiểu value hoặc template riêng cho từng dạng key/value.

Topic và partition resolver vẫn có thể sử dụng metadata của ConsumerRecord, nhưng không nên gọi getter domain trên value vì value có thể null hoặc không phải object dự kiến.

## 14. DLT và non-blocking retry topic có quy tắc riêng

Spring Kafka hỗ trợ hai cơ chế thường gặp:

**Blocking retry / recovery bằng DefaultErrorHandler**

- DeadLetterPublishingRecoverer có thể dùng destination resolver.
- Quy tắc mặc định thường là sourceTopic + ".DLT" và cùng partition.
- Có thể tự chọn DLT topic và partition bằng TopicPartition.

**Non-blocking retry bằng @RetryableTopic hoặc RetryTopicConfiguration**

- Framework xây dựng topology gồm source, retry destinations và DLT.
- Tên topic có thể dùng hậu tố như "-retry" hoặc "-dlt" tùy cấu hình.
- DLT routing và reuse strategy được cấu hình theo API retry-topic tương ứng.
- Cần kiểm tra hỗ trợ phân loại exception và DLT strategy theo phiên bản.

Ví dụ annotation:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 2_000),
        dltTopicSuffix = "-dlt"
)
@KafkaListener(topics = "orders.events", groupId = "orders-service")
public void onOrder(OrderEvent event) {
    orderService.process(event);
}
~~~

Với cấu hình trên, không nên giả định DLT sẽ là orders.events.DLT như mặc định của DeadLetterPublishingRecoverer trong cấu hình blocking retry. Hãy phân biệt rõ naming conventions của hai cơ chế.

Ngoài ra, non-blocking retry có thể thay đổi thứ tự xử lý vì một record lỗi được chuyển ra topic khác; record phía sau ở nguồn có thể được xử lý trước. Cần kiểm tra hỗ trợ với batch listener hoặc transactional container theo phiên bản Spring Kafka đang dùng.

## 15. Recovery thành công, publish DLT và commit offset

Thời điểm commit offset nguồn quyết định record có thể được giao lại sau crash hay không. Trong một luồng recovery, ứng dụng thường muốn:

1. Listener thất bại.
2. Error handler retry theo policy.
3. Recoverer publish record sang DLT.
4. Kết quả publish được xác nhận theo chính sách cần thiết.
5. Container xử lý record nguồn là recovered và tiến offset theo ack/error-handler mode.

Nếu producer dùng để publish DLT báo lỗi, record nguồn không nên được đánh dấu recovered như thể DLT đã lưu an toàn.

Trong cấu hình thực tế, cần kiểm tra:

- Recoverer có chờ kết quả send hay không và lỗi publish được truyền ra sao.
- Kafka producer properties như acks, idempotence, delivery.timeout.ms.
- AckMode và các tùy chọn commit recovered offset của DefaultErrorHandler.
- Hành vi khi listener dùng Kafka transaction manager.
- Khả năng record nguồn đã được ghi DLT nhưng crash trước khi offset nguồn commit.

**Có thể xảy ra duplicate DLT.** Ví dụ publish DLT thành công, sau đó ứng dụng dừng trước khi commit offset nguồn. Khi consumer khác đọc lại record nguồn, recoverer có thể publish cùng event thêm lần nữa. DLT consumer hoặc quy trình replay cần idempotency.

DLT không tự cung cấp exactly-once end-to-end cho database hoặc API bên ngoài.

## 16. Thứ tự dữ liệu và lựa chọn partition DLT

Giữ cùng partition số không có nghĩa bảo toàn một thứ tự toàn cục xuyên qua topic nguồn và DLT.

Ví dụ:

~~~text
orders.events / partition 1:
  offset 110: event A (lỗi -> DLT)
  offset 111: event B (thành công)
  offset 112: event C (thành công)

orders.events.DLT / partition 1:
  offset 20: event A

Khi operator replay event A:
  B và C có thể đã được áp dụng nghiệp vụ.
~~~

Nếu event A, B, C là các thay đổi tuần tự của cùng order, phát lại A sau B/C có thể tạo trạng thái sai.

Cần:

- Dùng event ID để chống xử lý trùng.
- Dùng event version hoặc sequence để phát hiện dữ liệu cũ.
- Kiểm tra state transition trước khi áp dụng.
- Có quy trình reconciliation cho các side effect quan trọng.
- Cân nhắc blocking retry khi thứ tự nghiêm ngặt và không thể xử lý bù.

Chọn cùng partition tại DLT giúp truy vết, nhưng không giải quyết bài toán ordering giữa topic nguồn và DLT.

## 17. Replay từ DLT phải định tuyến ngược có kiểm soát

Một quy trình replay thường gồm:

~~~text
DLT topic
    |
    v
Operator / replay service
    |
    +--> kiểm tra lỗi gốc
    |
    +--> xác minh topic và partition nguồn
    |
    +--> xác minh schema và payload
    |
    +--> kiểm tra quyền replay
    |
    v
Publish lại vào topic nguồn hoặc topic phục hồi
    |
    v
Consumer xử lý với idempotency
~~~

Nếu DLT partition khác partition nguồn do đã chọn -1, không dùng partition hiện tại của DLT để quyết định replay. Lấy partition nguồn từ metadata nếu nghiệp vụ cần khôi phục partition. Cũng cần xác minh topic nguồn thuộc allowlist, không tin tuyệt đối một header bị sửa hoặc dữ liệu do producer kiểm soát.

Một số hệ thống replay vào topic riêng rồi chạy một consumer có kiểm soát thay vì ghi lại topic sản xuất ban đầu. Phương án này giảm nguy cơ tạo vòng DLT mới hoặc làm ảnh hưởng thứ tự của luồng chính.

Không replay hàng loạt chỉ vì DLT có backlog. Nếu producer chưa sửa schema hoặc consumer chưa sửa bug, dữ liệu sẽ lại thất bại và quay về DLT.

## 18. ACL, retention và phân tách trách nhiệm

Khi chọn topic/partition DLT, không thể bỏ qua vận hành Kafka:

| Yếu tố | Cần quyết định |
|---|---|
| Topic ownership | Nhóm nào chịu trách nhiệm DLT |
| ACL ghi | Principal nào được recoverer publish |
| ACL đọc | Ai được điều tra và replay |
| Partition count | Dựa vào mapping đích và throughput |
| Replication factor | Mức durability cần bảo đảm |
| Retention | Thời gian cần điều tra và yêu cầu pháp lý |
| Encryption | Bảo vệ dữ liệu khi truyền và khi lưu |
| Monitoring | Lag, publish errors, backlog và oldest age |
| Serializer | Hỗ trợ payload hợp lệ và raw bytes |
| Replay | Approval, audit, idempotency và thứ tự |

DLT có thể chứa payload lỗi bao gồm dữ liệu nhạy cảm, token hoặc thông tin cá nhân. Không log toàn bộ payload và không mở ACL DLT rộng hơn topic nguồn nếu không có lý do hợp lệ.

DLT dùng chung cho nhiều domain có thể gây khó khăn về retention và quyền truy cập. Khi mức độ nhạy cảm rất khác nhau, DLT tách theo domain/topic thường dễ vận hành hơn.

## 19. Những lỗi định tuyến thường gặp

### DLT không đủ số partition

Record nguồn ở partition 7 nhưng DLT chỉ có partition 0 đến 3. Nếu resolver ép partition 7, gửi có thể thất bại hoặc gặp hành vi kiểm tra destination tùy phiên bản. Provision DLT tương ứng hoặc dùng -1 để producer chọn partition.

### Đổi partition count của topic nguồn mà quên DLT

Sau khi tăng partition nguồn, DLT cấu hình giữ partition có thể không còn tương thích. Đưa kiểm tra partition count vào quy trình thay đổi topic.

### Dùng cùng một DLT nhưng serializer không hỗ trợ nhiều schema

Recoverer có thể định tuyến đúng topic nhưng producer không thể serialize value. Dùng template/serializer phù hợp với từng loại hoặc chuẩn hóa envelope, đồng thời giữ metadata type.

### DLT topic được chọn bằng header không đáng tin

Một producer có thể điều khiển tên topic đích. Dùng allowlist mapping ở consumer, không tạo topic tùy ý theo payload.

### Nhầm offset DLT với offset nguồn

Mỗi topic/partition có log offset độc lập. Dùng original-topic/partition/offset headers hoặc metadata audit để replay và đối chiếu.

### Nhầm mặc định .DLT với cấu hình @RetryableTopic

Retry topic infrastructure có naming convention và destination mapping riêng. Đọc cấu hình của cơ chế đang dùng thay vì áp một quy tắc mặc định cho tất cả.

### Publish DLT thất bại nhưng listener vẫn tiến offset

Kiểm tra cách recoverer báo lỗi và chính sách commit recovered offset. Recovery chỉ an toàn nếu record lỗi đã được lưu ở đích với mức xác nhận yêu cầu.

### DLT backlog tăng nhưng không có ownership

Đặt cảnh báo, phân công nhóm xử lý và quy trình replay. Không xem DLT là nơi lưu tạm không cần theo dõi.

## 20. Quan sát hệ thống và xử lý sự cố

Nên đo theo cả topic nguồn và topic DLT:

| Metric/tín hiệu | Ý nghĩa |
|---|---|
| DLT publish rate | Tốc độ record đi vào DLT |
| DLT publish failure count | Recoverer thất bại khi ghi DLT |
| DLT backlog/oldest age | Số record chưa xử lý và tuổi record cũ nhất |
| Error count theo loại exception | Phân biệt lỗi dữ liệu và hạ tầng |
| Consumer retry count | Mức độ retry trước recovery |
| Consumer lag theo partition nguồn | Partition bị giữ bởi record lỗi |
| DLT ingress theo original topic | Domain nào gây lỗi nhiều |
| Invalid destination partition | Phát hiện mapping partition không hợp lệ |
| Recovery/replay duplicate count | Phát hiện phát lại trùng |
| End-to-end event age | Thời gian từ record nguồn đến recovery hoàn tất |

Tên metric cụ thể phụ thuộc Kafka client, Spring Kafka, Micrometer và exporter. Một số tín hiệu cần ứng dụng ghi thêm, đặc biệt phân loại theo source topic, error code và DLT destination.

Log có cấu trúc nên có eventId, original topic, original partition, original offset, destination topic, destination partition, exception class, recovery status và lỗi publish nếu có. Tránh dùng eventId làm metric label có cardinality không giới hạn.

### Tình huống: producer ghi DLT bị timeout

Timeout không nhất thiết chứng minh broker chưa ghi record. Recovery có thể bị retry và tạo duplicate. Cần idempotency và khả năng đối chiếu bằng event ID.

### Tình huống: DLT reader không đọc được JSON

Kiểm tra class/type mapping, trusted packages, serializer đã dùng để publish DLT, và dữ liệu raw byte[] từ deserialization failures.

### Tình huống: DLT cùng partition nhưng replay bị sai thứ tự

Giữ partition chỉ giữ khả năng truy vết và phân phối, không bảo đảm thứ tự với record đã xử lý ở topic nguồn. Dùng sequence/versioning hoặc một quy trình phát lại tuần tự có kiểm soát.

## 21. Quy trình chọn DLT topic và partition

Có thể thiết kế chính sách từ các câu hỏi sau:

1. **Topic nguồn thuộc domain nào?** Domain có yêu cầu dữ liệu và retention riêng không?
2. **Có cần DLT riêng cho mỗi topic?** Nếu cần phân quyền hoặc serializer khác nhau, tách DLT.
3. **Lỗi có cần chia nhóm không?** Security violations, invalid payload và transient failures có thể có quy trình riêng.
4. **DLT cần bao nhiêu partition?** Nếu giữ partition nguồn, provision tương ứng; nếu DLT chung có kích thước khác, dùng -1.
5. **Có cần truy vết partition gốc không?** Lưu original-topic/partition/offset headers.
6. **Ai được publish và đọc DLT?** Cấp ACL tối thiểu.
7. **DLT lưu trong bao lâu?** Đặt retention theo SLA điều tra và dữ liệu nhạy cảm.
8. **Serializer có nhận raw bytes không?** Kiểm tra ErrorHandlingDeserializer và template dùng để recover.
9. **Commit offset nguồn khi nào?** Xác nhận hành vi khi publish DLT thành công hoặc thất bại.
10. **Replay sẽ đi đâu?** Topic nguồn hay topic phục hồi riêng, có idempotency và audit không?
11. **Có thay đổi partition nguồn trong tương lai không?** Bổ sung kiểm tra topic topology trong quá trình deploy.
12. **Có monitoring không?** Cần metric DLT destination, recovery failure và backlog.

Một chính sách khả thi cho service có ít topic thường là **mỗi topic nguồn một DLT, giữ partition nếu partition count được quản lý đồng bộ**. Khi dùng một DLT chung cho nhiều nguồn hoặc có số partition khác nhau, **để producer chọn partition bằng -1** là lựa chọn linh hoạt hơn, đi kèm việc giữ nguyên metadata nguồn và thiết kế replay.

## 22. Checklist trước khi triển khai production

- DLT routing có owner và quy tắc rõ ràng theo topic nguồn.
- Resolver chỉ trả về các topic thuộc allowlist đã được provision.
- Mỗi destination topic có partition count phù hợp với mapping.
- Nếu giữ partition, DLT được cập nhật khi tăng partition nguồn.
- Nếu dùng -1, hệ thống không giả định DLT partition bằng partition nguồn.
- Không nhầm offset DLT với original offset.
- DefaultErrorHandler và recoverer được đăng ký đúng listener factory.
- KafkaTemplate có serializers, ACL và acks phù hợp.
- Lỗi deserialization có đường publish raw bytes sang DLT.
- Phân loại exception retryable/non-retryable có giới hạn.
- Publish DLT thất bại không bị coi là recovery thành công.
- DLT có retention, replication và quota phù hợp.
- Security-sensitive records không bị định tuyến tới DLT không được bảo vệ.
- DLT consumer/replay service có quyền hạn tối thiểu.
- Replay có kiểm tra schema, topic gốc, event ID và idempotency.
- Thứ tự giữa topic nguồn và DLT được xử lý bằng versioning hoặc quy trình riêng.
- Có monitoring cho destination, publish failures, backlog và tuổi record.
- Đã thử record lỗi trên partition cao hơn DLT, broker outage, crash trước commit, lỗi serializer và replay trùng.

Lựa chọn DLT theo topic và partition là một phần của thiết kế reliability, không chỉ là việc ghép hậu tố vào tên topic. DeadLetterPublishingRecoverer cho phép quyết định tường minh đích cần ghi; phần còn lại của hệ thống phải đảm bảo destination tồn tại, record được publish an toàn, metadata nguồn được giữ lại và DLT có thể được điều tra, phát lại đúng cách.

