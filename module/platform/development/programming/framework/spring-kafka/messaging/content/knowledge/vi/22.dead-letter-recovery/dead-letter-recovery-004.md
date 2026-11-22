# Xác định partition đích

Khi Spring Kafka chuyển một record lỗi sang Dead Letter Topic (DLT), hệ thống phải quyết định hai thông tin: topic đích và partition đích. `DeadLetterPublishingRecoverer` thực hiện việc publish record đã recover; destination resolver quyết định record lỗi được gửi đến đâu.

Partition đích ảnh hưởng cách các record lỗi được phân phối, khả năng giữ quan hệ với partition nguồn, thứ tự đọc trong DLT và năng lực xử lý của consumer chuyên trách. Chọn partition theo cùng chỉ số partition nguồn là cách mặc định phổ biến, nhưng chỉ an toàn khi DLT có đủ partition tương ứng. Nếu DLT tập trung nhiều topic hoặc có số partition khác nguồn, cần thiết kế quy tắc ánh xạ rõ ràng.

Bài học thuộc chương **Dead letter và recoverer** của module **SPRING_KAFKA_MESSAGING**. Module tập trung xây dựng ứng dụng gửi nhận sự kiện bằng Spring Kafka, `KafkaTemplate` và `@KafkaListener`, hiểu topic, partition, offset và consumer group; đồng thời học serialization, retry, dead-letter, transaction, exactly-once, xử lý đồng thời và kiểm thử để vận hành luồng messaging tin cậy.

## 1. Partition đích được chọn ở bước nào?

Khi listener xử lý record thất bại và retry đã hết hoặc error handler quyết định recover, `DeadLetterPublishingRecoverer` tạo một record mới để gửi sang DLT. Record mới có topic và partition đích riêng.

~~~mermaid
flowchart TD
    A[Record từ topic nguồn] --> B[Listener xử lý thất bại]
    B --> C[ErrorHandler retry]
    C --> D{Còn retry?}
    D -->|Có| B
    D -->|Không| E[DeadLetterPublishingRecoverer]
    E --> F[Destination resolver]
    F --> G[Chọn DLT topic]
    F --> H[Chọn DLT partition]
    G --> I[ProducerRecord đích]
    H --> I
    I --> J[Kafka producer]
    J --> K[DLT partition]
~~~

Destination resolver là thành phần quyết định route. Với Spring Kafka, resolver có thể nhận record nguồn và exception rồi trả về `TopicPartition` gồm tên topic đích và partition đích.

Chọn partition đích không thay đổi partition hoặc offset của record nguồn. Recoverer publish một record mới; broker cấp offset mới trong partition DLT.

## 2. Default destination resolver

Khi tạo `DeadLetterPublishingRecoverer` bằng KafkaTemplate mà không truyền resolver tùy chỉnh, Spring Kafka dùng quy tắc mặc định phổ biến:

- Tên topic đích là topic nguồn cộng hậu tố `.DLT`.
- Partition đích giữ cùng chỉ số với partition nguồn.

Ví dụ:

~~~text
Topic nguồn: order-events

order-events-0, offset 100  --> order-events.DLT-0
order-events-1, offset 250  --> order-events.DLT-1
order-events-2, offset 90   --> order-events.DLT-2
~~~

Cấu hình:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(dltTemplate);
}
~~~

Với resolver mặc định, nếu record đến từ partition 2 thì recoverer gửi record sang partition 2 của `order-events.DLT`. DLT phải có partition index tương ứng; nếu không, publish có thể thất bại.

Cách mặc định hữu ích khi mỗi topic nguồn có một DLT riêng và DLT được tạo với số partition ít nhất bằng topic nguồn. Nó giúp truy vết và phân phối tải theo partition nguồn đơn giản.

## 3. Vì sao cần quan tâm số partition của DLT?

Giả sử topic nguồn có 12 partition, nhưng DLT chỉ có 3 partition. Record từ partition nguồn 8 không thể được publish vào partition 8 của DLT vì partition đó không tồn tại.

Nếu resolver yêu cầu partition cụ thể, partition index phải nằm trong phạm vi partition thực tế của topic đích:

\[
0 \leq p_{\text{đích}} < P_{\text{DLT}}
\]

Trong đó `P_DLT` là số partition của topic DLT.

| Topic nguồn | DLT | Kết quả khi giữ nguyên partition |
| --- | --- | --- |
| 6 partition | 6 partition | Ánh xạ 0→0 đến 5→5 hợp lệ. |
| 6 partition | 10 partition | Ánh xạ cùng index hợp lệ; các partition DLT 6–9 không được dùng bởi route này. |
| 10 partition | 4 partition | Partition nguồn 4–9 không có partition đích cùng index. |
| 1 partition | 1 partition | Ánh xạ 0→0 hợp lệ. |

Khi DLT có ít partition hơn nguồn, phải chọn một chiến lược khác: remap partition, để producer chọn partition hoặc chia DLT theo nguồn/nhóm lỗi với topology phù hợp.

Không nên giả định Kafka tự động co chỉ số partition vượt giới hạn về một partition hợp lệ. Nếu muốn remap, phải thực hiện rõ trong resolver.

## 4. Tạo resolver tùy chỉnh

`DeadLetterPublishingRecoverer` cho phép truyền destination resolver. Resolver thường là `BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition>`.

Ví dụ giữ nguyên topic nguồn cộng hậu tố và partition nguồn:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition> resolver =
        (record, exception) -> new TopicPartition(
            record.topic() + ".DLT",
            record.partition()
        );

    return new DeadLetterPublishingRecoverer(dltTemplate, resolver);
}
~~~

Ví dụ trên thể hiện lại quy tắc mặc định nhưng làm rõ điểm có thể tùy chỉnh. Từ cùng hai đầu vào record và exception, resolver có thể chọn topic hoặc partition khác dựa trên chính sách ứng dụng.

Nên giữ resolver:

- Xác định và có tính lặp lại: cùng record và cùng điều kiện nên cho cùng route.
- Nhanh: không gọi dịch vụ từ xa hoặc truy vấn database cho mỗi record lỗi.
- Có kiểm tra topology: partition đích phải tồn tại.
- Có log/metric đủ để giải thích quyết định route.
- Không làm mất metadata nguồn cần điều tra.

Resolver không nên ném lỗi do thiếu cấu hình một cách âm thầm. Nếu không thể xác định destination, recovery thất bại và error handler phải tiếp tục xử lý theo chính sách thay vì commit record nguồn như đã recover thành công.

## 5. Chiến lược 1: giữ nguyên partition nguồn

Đây là chiến lược phù hợp khi mỗi topic nguồn có một DLT riêng với số partition bằng hoặc lớn hơn nguồn.

~~~text
order-events:
  P0 -> order-events.DLT P0
  P1 -> order-events.DLT P1
  P2 -> order-events.DLT P2
  P3 -> order-events.DLT P3
~~~

Ưu điểm:

- Dễ truy vết record lỗi về partition nguồn.
- Dễ chia tải DLT consumer theo cùng số partition.
- Các record lỗi từ cùng partition nguồn đi vào cùng partition DLT.
- Không cần tính toán ánh xạ partition riêng.

Giới hạn:

- DLT phải duy trì topology tương ứng.
- Nếu DLT tập trung nhiều nguồn có partition count khác nhau, việc giữ nguyên index có thể không phù hợp.
- Partition nguồn không biểu thị thứ tự toàn topic; giữ index không tạo ordering giữa các partition khác nhau.

Đây thường là lựa chọn đơn giản cho mô hình một DLT trên mỗi topic nguồn.

## 6. Chiến lược 2: ánh xạ modulo vào DLT nhỏ hơn

Khi muốn dùng một DLT có ít partition hơn topic nguồn, có thể ánh xạ partition nguồn về một partition đích theo modulo:

\[
p_{\text{đích}} = p_{\text{nguồn}} \bmod P_{\text{DLT}}
\]

Ví dụ topic nguồn có 12 partition, DLT có 4 partition:

~~~text
Nguồn P0, P4, P8   -> DLT P0
Nguồn P1, P5, P9   -> DLT P1
Nguồn P2, P6, P10  -> DLT P2
Nguồn P3, P7, P11  -> DLT P3
~~~

Resolver minh họa:

~~~java
private static final int DLT_PARTITIONS = 4;

private TopicPartition mapToSharedDlt(
        ConsumerRecord<?, ?> record) {

    int targetPartition = Math.floorMod(
        record.partition(),
        DLT_PARTITIONS
    );

    return new TopicPartition(
        "dead-letter-events",
        targetPartition
    );
}
~~~

Dùng `Math.floorMod` giúp kết quả không âm nếu partition index đầu vào có giá trị âm do một tình huống đặc biệt trong code; partition nguồn Kafka hợp lệ vốn không âm.

Ưu điểm là giảm số partition cần vận hành trong DLT. Nhược điểm là nhiều partition nguồn cùng dồn vào một partition DLT, có thể tạo hot partition và tăng độ trễ xử lý lỗi.

Modulo chỉ là một quy tắc ánh xạ. Số partition DLT phải đồng bộ với cấu hình resolver; nếu thay đổi số partition DLT mà không cập nhật chính sách, route có thể thay đổi hoặc mất cân bằng.

## 7. Chiến lược 3: để Kafka producer chọn partition

Resolver có thể chỉ định topic nhưng không khóa partition cụ thể. Trong Spring Kafka, trả về `TopicPartition` với partition âm (thường dùng `-1`) để biểu thị không chỉ định partition; producer sẽ chọn partition theo partitioner đang cấu hình.

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(
        dltTemplate,
        (record, exception) ->
            new TopicPartition("dead-letter-events", -1)
    );
}
~~~

Khi partition không được chỉ định, producer partitioner có thể dựa trên key đã serialize. Với key khác null và partitioner mặc định, các record cùng key thường được đưa vào cùng partition trong cùng topology. Với key null, producer có thể dùng chiến lược sticky partitioning hoặc chiến lược được cấu hình.

Ưu điểm:

- Không cần giữ nguyên chỉ số partition nguồn.
- Có thể dùng DLT tập trung với số partition độc lập.
- Tận dụng partitioner của producer và key record.

Hạn chế:

- Không đảm bảo record lỗi vào cùng partition index với nguồn.
- Mapping theo key phụ thuộc key serializer và partitioner.
- Với key null, không có affinity theo entity.
- Thay đổi partition count của DLT có thể thay đổi key-to-partition mapping.

Chỉ dùng chiến lược này khi việc giữ nguyên partition nguồn không phải yêu cầu vận hành. Nếu cần truy vết, recoverer vẫn bổ sung metadata nguồn trong header của record DLT.

## 8. Chiến lược 4: chọn partition theo loại lỗi hoặc nguồn

Resolver nhận cả record và exception, vì vậy có thể định tuyến theo topic nguồn, loại lỗi hoặc một thuộc tính đã được kiểm soát.

Ví dụ chia DLT theo nhóm lỗi:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> dltTemplate) {

    return new DeadLetterPublishingRecoverer(
        dltTemplate,
        (record, exception) -> {
            String destination;

            if (exception instanceof InvalidEventException) {
                destination = "invalid-events.DLT";
            }
            else {
                destination = "processing-errors.DLT";
            }

            return new TopicPartition(destination, -1);
        }
    );
}
~~~

Ở ví dụ này, partition âm yêu cầu producer chọn partition của topic đích. Có thể thay bằng partition index cụ thể nếu DLT topology được quản lý đồng bộ.

Có thể phân loại theo nguồn:

~~~java
private TopicPartition resolveDestination(
        ConsumerRecord<?, ?> record,
        Exception exception) {

    String destination = switch (record.topic()) {
        case "order-events" -> "order-errors.DLT";
        case "payment-events" -> "payment-errors.DLT";
        default -> "unclassified-errors.DLT";
    };

    return new TopicPartition(destination, -1);
}
~~~

Không nên đưa mọi exception vào một topic duy nhất nếu retention, quyền truy cập, người sở hữu hoặc quy trình replay của từng domain khác nhau. Ngược lại, tạo quá nhiều DLT nhỏ cũng tăng gánh nặng quản lý topic. Hãy chọn ranh giới theo ownership và cách khôi phục thực tế.

Exception truyền vào resolver có thể là exception được error handler chuyển tiếp, có cause chain chứa nguyên nhân sâu hơn. Không nên chỉ dựa vào chuỗi message vì message có thể thay đổi theo phiên bản hoặc ngôn ngữ.

Có thể duyệt cause chain:

~~~java
private boolean hasCause(
        Throwable error,
        Class<? extends Throwable> expectedType) {

    Throwable current = error;

    while (current != null) {
        if (expectedType.isInstance(current)) {
            return true;
        }
        current = current.getCause();
    }

    return false;
}
~~~

Sau đó dùng loại exception đã chuẩn hóa để chọn destination:

~~~java
if (hasCause(exception, InvalidEventException.class)) {
    return new TopicPartition("invalid-events.DLT", -1);
}
return new TopicPartition("processing-errors.DLT", -1);
~~~

Không nên phân loại lỗi bằng tên class bất kỳ từ payload hoặc header do producer kiểm soát. Route nên dựa trên exception type và rule nội bộ đã được review.

Nếu nhiều exception được bọc qua các lớp framework, hãy test cause chain thực tế. Có thể cần phân loại thêm theo DeserializationException, validation exception hoặc lỗi tạm thời để tránh đưa lỗi hạ tầng vào DLT dữ liệu sai.

## 10. Partition đích và key của record

`DeadLetterPublishingRecoverer` thường giữ key và value của record nguồn khi tạo record DLT, đồng thời thêm các header mô tả nguồn và exception. Key vì thế có thể tiếp tục tham gia chọn partition nếu resolver để producer quyết định partition.

Cần phân biệt hai cơ chế:

- Resolver chỉ định partition cụ thể: producer gửi vào đúng partition được chọn.
- Resolver để partition chưa chỉ định: producer partitioner quyết định dựa trên key/configuration.

Nếu key bị lỗi deserialize, giá trị key object có thể null trong record được xử lý; raw key bytes được giữ trong metadata lỗi của ErrorHandlingDeserializer. DLT producer phải có serializer hỗ trợ raw byte[] để bảo toàn key lỗi khi publish.

Nếu key null thật, partitioner không thể dùng key để giữ affinity. Khi đó producer có thể phân phối theo sticky partitioning hoặc custom partitioner.

Không nên tự tính partition bằng hash của `record.key().hashCode()` trong resolver nếu muốn khớp partitioner Kafka. Hash Java object không nhất thiết giống hash trên serialized key bytes hoặc thuật toán partitioner đang dùng.

## 11. Partition đích không phải offset nguồn

Khi record được publish sang DLT, Kafka broker cấp offset mới trong partition đích. Offset mới không nhất thiết bằng offset nguồn.

~~~text
Nguồn:
  order-events-2, offset 1050

DLT:
  order-events.DLT-2, offset 87
~~~

Recoverer có thể thêm các header nguồn như topic, partition, offset và consumer group để phục vụ điều tra. Vì vậy:

- `record.partition()` khi consumer đọc DLT là partition đích.
- Header original partition mô tả partition nguồn.
- `record.offset()` khi đọc DLT là offset mới trong DLT.
- Header original offset mô tả vị trí record trong topic nguồn.

Không dùng offset DLT để suy ra offset nguồn. Nếu cần replay chính xác, phải lưu và đọc metadata nguồn, đồng thời xem xét record nguồn đã được commit sau recovery hay chưa.

## 12. DLT tập trung và nhiều topic nguồn

Một DLT tập trung có thể nhận lỗi từ nhiều topic:

~~~text
order-events-0 ─────┐
payment-events-3 ───┼──> dead-letter-events
inventory-events-1 ─┘
~~~

Khi nhiều topic có partition count khác nhau, không thể mặc định dùng partition index nguồn cho mọi record nếu DLT có ít partition hơn nguồn lớn nhất.

Các lựa chọn:

1. DLT có partition count đủ lớn cho partition index lớn nhất của mọi nguồn.
2. Resolver ánh xạ source partition về một tập partition DLT nhỏ hơn.
3. Resolver trả partition không chỉ định để producer chọn theo key/partitioner.
4. Tách DLT theo domain hoặc topic nguồn để mỗi DLT có topology phù hợp.

DLT tập trung giúp một đội vận hành xử lý lỗi chung, nhưng có thể trộn retention, ACL, ownership và tốc độ tiêu thụ của nhiều domain. Nên cân nhắc liệu một DLT có cần cùng chính sách lưu trữ và replay cho mọi nguồn hay không.

Nếu consumer DLT cần biết record thuộc nguồn nào, dùng các header metadata do recoverer thêm và kiểm tra chúng trong integration test. Không nên chỉ dựa vào tên DLT khi nhiều nguồn cùng publish vào một topic.

## 13. Tạo và quản lý topology DLT

DLT cần được tạo trước hoặc có cơ chế quản lý topic phù hợp với môi trường. Khi thiết kế topology, hãy xác định:

- Số partition và replication factor.
- Retention time/size.
- Cleanup policy.
- ACL cho producer, consumer và đội vận hành.
- Schema/wire format của key/value.
- Chính sách headers và kích thước record.
- Consumer group xử lý DLT.
- Quy trình replay hoặc chuyển đổi record lỗi.

Nếu giữ nguyên partition nguồn, số partition DLT phải đủ để chứa mọi partition index mà resolver có thể trả về. Nếu resolver trả partition `-1`, số partition DLT vẫn cần đủ throughput và phù hợp partitioner; producer tự chọn một partition hợp lệ nhưng không tạo thêm capacity.

Không nên chỉ tạo DLT một partition vì tiện lợi nếu nguồn có nhiều partition và lượng lỗi lớn. Một partition DLT có thể trở thành bottleneck, đặc biệt khi nhiều topic cùng gửi lỗi vào đó.

## 14. Thay đổi số partition DLT có ảnh hưởng gì?

Nếu resolver ánh xạ modulo hoặc producer partitioner chọn theo key, thay đổi số partition DLT có thể thay đổi route của record mới.

Ví dụ DLT từ 4 partition tăng lên 8:

- Với modulo, `sourcePartition % 4` và `sourcePartition % 8` có thể cho kết quả khác.
- Với key-based partitioner, hash key modulo partition count có thể chọn partition khác.
- Record cũ vẫn nằm ở partition cũ; record mới có thể vào partition khác.

Điều này không thay đổi dữ liệu đã lưu nhưng có thể làm cùng một key xuất hiện ở nhiều partition DLT qua thời gian. Nếu quy trình recovery phụ thuộc ordering theo key, cần đánh giá trước khi mở rộng partition.

Hãy coi partition count của DLT là một phần của contract vận hành. Nếu phải thay đổi, ghi nhận thời điểm thay đổi, kiểm tra mapping mới và bảo đảm consumer recovery không giả định một partition cố định cho toàn bộ lịch sử.

## 15. Ordering trong DLT

Kafka bảo đảm thứ tự trong từng partition DLT theo offset được append. Tuy nhiên, việc chuyển record lỗi sang DLT không tạo thứ tự toàn cục với topic nguồn.

Một số điểm cần nhớ:

- Các record lỗi từ cùng partition nguồn có thể cùng đi vào partition DLT nếu resolver giữ nguyên partition.
- Retry/backoff có thể khiến record lỗi được publish DLT muộn hơn record lỗi phát sinh sau.
- Nhiều consumer hoặc nhiều source partition có thể gửi vào cùng partition DLT.
- Resolver để producer chọn partition theo key có thể thay đổi mapping khi partition count đổi.
- Thứ tự DLT phản ánh thứ tự publish vào DLT, không nhất thiết là thứ tự event ban đầu ở topic nguồn.

Nếu cần replay theo thứ tự nghiệp vụ, hãy dùng metadata nguồn như original topic/partition/offset cùng event ID hoặc sequence nghiệp vụ. Không dựa riêng vào offset DLT để tái tạo thứ tự nguồn.

## 16. Tùy chỉnh resolver và log route

Resolver nên ghi lại quyết định route ở mức metadata đủ dùng. Ví dụ:

~~~java
private TopicPartition resolve(
        ConsumerRecord<?, ?> record,
        Exception exception) {

    String targetTopic = record.topic() + ".DLT";
    int targetPartition = record.partition();

    log.warn(
        "Route failed record sourceTopic={} sourcePartition={} sourceOffset={} targetTopic={} targetPartition={} exception={}",
        record.topic(),
        record.partition(),
        record.offset(),
        targetTopic,
        targetPartition,
        exception.getClass().getSimpleName()
    );

    return new TopicPartition(targetTopic, targetPartition);
}
~~~

Không log toàn bộ payload hoặc key nhạy cảm. Log route giúp xác định vì sao một record được gửi vào DLT cụ thể và hỗ trợ đối chiếu với header metadata sau publish.

Resolver không nên thực hiện side effect như ghi database hoặc gửi HTTP request. Nếu cần lưu audit, thực hiện ở một thành phần có transaction/error handling rõ ràng; resolver nên tập trung xác định destination.

Nếu route phụ thuộc cấu hình runtime, hãy validate cấu hình khi application khởi động. Không để một typo trong tên DLT chỉ được phát hiện khi record lỗi đầu tiên xuất hiện.

## 17. Cấu hình recoverer với resolver theo partition

Ví dụ đầy đủ cho trường hợp giữ nguyên partition nguồn:

~~~java
@Configuration
public class DeadLetterConfiguration {

    @Bean
    public DeadLetterPublishingRecoverer deadLetterRecoverer(
            KafkaTemplate<Object, Object> dltTemplate) {

        return new DeadLetterPublishingRecoverer(
            dltTemplate,
            (record, exception) -> {
                String dltTopic = record.topic() + ".DLT";
                int dltPartition = record.partition();

                return new TopicPartition(
                    dltTopic,
                    dltPartition
                );
            }
        );
    }

    @Bean
    public DefaultErrorHandler kafkaErrorHandler(
            DeadLetterPublishingRecoverer deadLetterRecoverer) {

        return new DefaultErrorHandler(
            deadLetterRecoverer,
            new FixedBackOff(1_000L, 2L)
        );
    }
}
~~~

Gắn error handler vào factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

Đây là cấu hình minh họa cho record listener. Với deserialization failure, DLT template còn phải hỗ trợ raw bytes theo cấu hình ErrorHandlingDeserializer. Với batch listener hoặc transaction, cần kiểm thử semantics recovery riêng.

## 18. Kiểm thử destination resolver

Không nên chỉ test rằng recoverer được gọi. Hãy xác nhận đúng topic và partition đích.

Các trường hợp nên kiểm thử:

1. Source partition 0 được route sang DLT partition 0 khi giữ nguyên partition.
2. Source partition lớn nhất vẫn có partition tương ứng ở DLT.
3. Source partition ngoài phạm vi DLT được remap đúng khi dùng modulo.
4. Resolver trả partition âm để producer chọn partition khi chính sách cho phép.
5. Exception type khác nhau được route đến topic đúng.
6. Nhiều topic nguồn được route đúng DLT.
7. Key lỗi và value lỗi vẫn giữ raw bytes trong DLT.
8. Header original topic/partition/offset phản ánh nguồn.
9. DLT publish thất bại không làm record nguồn bị coi là recovered.
10. DLT consumer đọc record theo partition và có thể tra cứu nguồn.

Ví dụ unit test cho quy tắc modulo:

~~~java
@Test
void shouldMapSourcePartitionToDltPartition() {
    ConsumerRecord<String, OrderEvent> record =
        new ConsumerRecord<>(
            "order-events",
            10,
            123L,
            "order-100",
            new OrderEvent("order-100")
        );

    int dltPartition = Math.floorMod(record.partition(), 4);

    assertThat(dltPartition).isEqualTo(2);
}
~~~

Test này kiểm tra phép ánh xạ thuần. Integration test cần tạo topic nguồn và DLT, gửi record lỗi thật, để error handler recover, rồi đọc DLT và xác nhận record thực sự nằm ở partition đích mong muốn.

## 19. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| DLT publish báo partition không tồn tại | DLT ít partition hơn nguồn nhưng resolver giữ nguyên index | Tăng partition DLT hoặc remap/để producer chọn |
| Mọi record dồn vào một partition DLT | Resolver hard-code partition 0 hoặc DLT chỉ có một partition | Phân phối theo source partition/key và tăng capacity |
| Record từ nhiều nguồn trộn lẫn | Dùng một DLT tập trung | Dùng original topic metadata hoặc tách DLT theo domain |
| Không giữ được cùng partition index | Resolver dùng partition âm hoặc remap | Kiểm tra chiến lược route và metadata nguồn |
| Key lỗi không còn ở DLT | DLT serializer không hỗ trợ raw byte[] | Cấu hình serializer cho key/value raw bytes |
| Record cùng key nằm ở nhiều DLT partition | Partition count hoặc partitioner thay đổi | Ổn định topology và key serializer; kiểm tra lịch sử mapping |
| Replay sai thứ tự | Dựa vào DLT offset thay vì metadata nguồn/sequence | Dùng original offset và sequence nghiệp vụ |
| DLT publish thất bại nhưng nguồn vẫn bị bỏ qua | Recovery/commit semantics cấu hình sai | Kiểm tra recoverer result, error handler và transaction |
| Route sai topic | Resolver dùng rule không đầy đủ hoặc cấu hình typo | Validate route lúc startup và test từng nguồn |
| Resolver chậm làm recovery chậm | Truy vấn remote/database trong resolver | Dùng rule local, deterministic và cache cấu hình |

## 20. Checklist chọn partition đích

Trước khi triển khai DLT, hãy xác nhận:

1. DLT dùng riêng theo topic nguồn hay tập trung nhiều nguồn?
2. Resolver mặc định có phù hợp không?
3. DLT có đủ partition nếu giữ nguyên partition nguồn không?
4. Nếu DLT ít partition hơn, dùng modulo hay để producer chọn?
5. Quy tắc ánh xạ có deterministic và được kiểm thử không?
6. Key serializer và partitioner có tương thích với route theo key không?
7. Raw key/value bytes có được bảo toàn khi deserialize failure không?
8. Original topic/partition/offset headers có được giữ để điều tra không?
9. DLT partition count, retention, replication và ACL đã được provision chưa?
10. Có theo dõi hot partition và DLT consumer lag không?
11. Thay đổi partition count có ảnh hưởng mapping và ordering không?
12. Có integration test cho publish success, publish failure và replay không?

Partition đích do destination resolver của DeadLetterPublishingRecoverer quyết định. Giữ nguyên partition nguồn là lựa chọn dễ truy vết khi DLT có đủ partition; modulo giúp gom nhiều partition nguồn vào DLT nhỏ hơn; partition âm cho phép producer chọn theo partitioner và key. Cần hiểu rõ record partition/offset mới trong DLT khác metadata partition/offset nguồn, đồng thời kiểm thử topology và recovery trước khi vận hành.


