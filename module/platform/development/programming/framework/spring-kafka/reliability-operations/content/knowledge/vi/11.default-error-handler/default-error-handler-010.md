# BatchListenerFailedException

## 1. Vai trò trong xử lý batch của Spring Kafka

Khi một batch listener nhận nhiều record trong một lần gọi, listener có thể xử lý một số record thành công rồi gặp lỗi ở một record cụ thể. Nếu chỉ ném một exception thông thường, container không biết record nào trong batch đã hoàn tất và record nào gây lỗi.

**BatchListenerFailedException** là exception đặc biệt của Spring Kafka dùng để thông báo vị trí record thất bại trong batch. Khi được sử dụng cùng **DefaultErrorHandler**, nó giúp error handler phân biệt phần record đã xử lý thành công với record lỗi và các record đứng sau nó.

Ví dụ, một lần poll trả về năm record:

~~~text
Index trong batch:   0       1       2       3       4
Record:             A       B       C       D       E
Kết quả:          thành   thành    lỗi    chưa    chưa
                   công    công            xử lý   xử lý
~~~

Nếu record C gây lỗi, listener có thể ném **BatchListenerFailedException** với index bằng 2. **DefaultErrorHandler** biết record ở index 0 và 1 đã hoàn tất, còn record C là điểm bắt đầu cần retry hoặc recovery.

Exception này không tự retry record, không tự gửi DLT và không commit offset. Nó cung cấp thông tin cho error handler đang được container cấu hình.

## 2. Vì sao cần xác định chính xác record lỗi?

Batch listener thường được dùng để xử lý nhiều record cùng lúc nhằm giảm overhead hoặc tận dụng bulk operation. Nhưng một batch có thể chứa record hợp lệ và record lỗi xen kẽ.

Giả sử listener nhận các event:

| Index | Event | Kết quả xử lý |
|---:|---|---|
| 0 | Order A | Thành công |
| 1 | Order B | Thành công |
| 2 | Order C | Lỗi dữ liệu |
| 3 | Order D | Chưa được xử lý |
| 4 | Order E | Chưa được xử lý |

Nếu listener chỉ ném **RuntimeException**, error handler không biết lỗi phát sinh tại Order C. Với batch listener, **DefaultErrorHandler** có thể phải retry toàn bộ batch vì không có thông tin để xác định ranh giới chính xác.

Khi listener ném **BatchListenerFailedException** và chỉ rõ index 2, error handler có thể:

1. Xem các record trước index 2 là đã xử lý.
2. Commit offset tương ứng với phần đã hoàn tất theo semantics của container.
3. Seek hoặc redeliver từ record lỗi trở đi.
4. Retry record lỗi theo BackOff đã cấu hình.
5. Khi retry hết, gọi recoverer cho record lỗi nếu có.
6. Tiếp tục xử lý các record còn lại theo chính sách của error handler.

Cách xử lý cụ thể còn phụ thuộc phiên bản Spring Kafka, container configuration, error handler và recovery policy. Điểm cốt lõi là exception cho biết record lỗi nằm ở đâu trong batch.

## 3. Cấu trúc và cách sử dụng exception

Lớp **BatchListenerFailedException** nằm trong package:

~~~java
org.springframework.kafka.listener.BatchListenerFailedException
~~~

Một constructor thường dùng khi listener biết index của record lỗi:

~~~java
throw new BatchListenerFailedException(
    "Could not process order event",
    cause,
    failedIndex
);
~~~

Trong đó:

- Message mô tả lỗi ở mức dễ đọc.
- Cause là exception gốc phát sinh từ nghiệp vụ hoặc dependency.
- **failedIndex** là vị trí record lỗi trong danh sách batch, bắt đầu từ 0.

Ví dụ, nếu record thứ ba trong danh sách gây lỗi thì index truyền vào là 2.

Không truyền số thứ tự tính từ 1, offset Kafka, partition number hoặc index của một batch khác. Error handler cần index tương ứng chính xác với danh sách record listener hiện tại đang xử lý.

### 3.1. Index là vị trí trong batch

Giả sử listener nhận:

~~~java
List<ConsumerRecord<String, OrderCreated>> records
~~~

Khi record tại **records.get(3)** lỗi, hãy truyền index 3:

~~~java
throw new BatchListenerFailedException(
    "Order validation failed",
    exception,
    3
);
~~~

Index này không phải Kafka offset. Một record có thể có offset 50 nhưng nằm ở index 0 trong batch. Một batch có thể chứa record từ nhiều partition, vì vậy offset cũng không tạo thành một dãy liên tục duy nhất.

| Khái niệm | Ví dụ | Dùng làm failedIndex? |
|---|---|---|
| Index trong List | **records.get(2)** | Có |
| Kafka offset | **record.offset() == 102** | Không |
| Partition | **record.partition() == 3** | Không |
| Số thứ tự record tính từ 1 | Record thứ 3 | Không, phải đổi thành index 2 |

### 3.2. Giữ lại metadata bằng ConsumerRecord

Batch listener có thể nhận danh sách payload hoặc danh sách **ConsumerRecord**. Khi cần xác định chính xác record lỗi, **ConsumerRecord** cung cấp metadata hữu ích như topic, partition, offset, key, timestamp và headers.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    // Xử lý batch
}
~~~

Giữ danh sách record giúp log và điều tra lỗi dễ hơn. Nếu listener chỉ nhận **List<OrderCreated>**, index vẫn có thể dùng được, nhưng ứng dụng cần bảo đảm payload và metadata được ánh xạ nhất quán.

## 4. Kết hợp với DefaultErrorHandler

**DefaultErrorHandler** là error handler phổ biến của Spring Kafka để retry, seek và recovery khi listener xử lý record thất bại. Với batch listener, nó có thể dùng **BatchListenerFailedException** để xác định record lỗi.

Ví dụ cấu hình recoverer gửi record lỗi sang dead-letter topic:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Bean
public DefaultErrorHandler kafkaErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
    var backOff = new FixedBackOff(1_000L, 2L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

Trong ví dụ, **FixedBackOff(1_000L, 2L)** yêu cầu khoảng nghỉ 1 giây giữa các lần retry và cho phép hai lần retry sau lần xử lý ban đầu. Sau khi retry hết, recoverer được gọi để xử lý record thất bại.

Gắn error handler vào batch listener container factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        batchKafkaListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setBatchListener(true);
    factory.setCommonErrorHandler(kafkaErrorHandler);

    return factory;
}
~~~

Các ví dụ giả định ứng dụng đã cấu hình **ConsumerFactory**, serializer/deserializer và KafkaTemplate phù hợp. DLT publisher cần có quyền ghi topic đích, và topic DLT cần được tạo hoặc được phép tự tạo theo chính sách cluster.

## 5. Ví dụ batch listener ném BatchListenerFailedException

Một cách dùng điển hình là xử lý từng record trong danh sách và ném exception tại index gây lỗi:

~~~java
@Service
public class OrderBatchListener {

    private final FulfillmentService fulfillmentService;

    public OrderBatchListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-fulfillment",
        containerFactory = "batchKafkaListenerContainerFactory"
    )
    public void consume(
            List<ConsumerRecord<String, OrderCreated>> records) {

        for (int i = 0; i < records.size(); i++) {
            ConsumerRecord<String, OrderCreated> record = records.get(i);

            try {
                fulfillmentService.process(record.value());
            }
            catch (RuntimeException ex) {
                log.error(
                    "Order event processing failed: topic={}, partition={}, offset={}",
                    record.topic(),
                    record.partition(),
                    record.offset(),
                    ex
                );

                throw new BatchListenerFailedException(
                    "Could not process order event",
                    ex,
                    i
                );
            }
        }
    }
}
~~~

Nếu record ở index 2 gây lỗi, listener dừng vòng lặp và ném exception với index 2. Error handler có đủ thông tin để xử lý phần trước và phần sau record lỗi.

Không nên tiếp tục xử lý các record sau lỗi rồi vẫn ném exception với index cũ nếu nghiệp vụ không bảo đảm trạng thái của các record đó. Khi handler redeliver phần còn lại, side effect có thể bị lặp. Nếu muốn xử lý song song trong batch, cần thiết kế kết quả theo từng record và xác định rõ record nào đã hoàn tất trước khi báo lỗi.

## 6. Luồng xử lý khi có BatchListenerFailedException

Giả sử poll trả về năm record trên cùng một partition:

~~~text
Poll batch:
  index 0 -> offset 100
  index 1 -> offset 101
  index 2 -> offset 102  <-- lỗi
  index 3 -> offset 103
  index 4 -> offset 104
~~~

Listener xử lý offset 100 và 101 thành công, nhưng offset 102 thất bại. Nó ném **BatchListenerFailedException** với index 2.

Với **DefaultErrorHandler** và cơ chế seek thông thường, luồng xử lý khái quát là:

~~~text
Batch listener
     |
     | xử lý offset 100, 101
     | offset 102 phát sinh lỗi
     v
BatchListenerFailedException(index=2)
     |
     v
DefaultErrorHandler
     |
     +-- ghi nhận phần trước index 2 đã xử lý
     |
     +-- commit offset phù hợp cho phần đã hoàn tất
     |
     +-- seek/redeliver từ offset 102 trở đi
               |
               v
         Retry record lỗi
               |
        +------+------+
        |             |
      Thành công    Hết retry
        |             |
        v             v
    Tiếp tục       Recover record
    batch          lỗi (ví dụ DLT)
                      |
                      v
                Xử lý record sau
~~~

Với cùng partition, nếu offset 100 và 101 đã hoàn tất, offset commit có thể tiến tới 102, nghĩa là consumer sẽ đọc tiếp từ offset 102. Khi có nhiều partition trong batch, offset được quản lý riêng theo từng partition; không thể lấy index trong list để tính một offset commit chung.

Sau khi record lỗi được xử lý hoặc recover, các record còn lại được tiếp tục theo hành vi retry/recovery của error handler. Cần quan sát log và offset thực tế trong phiên bản đang chạy nếu ứng dụng có batch phức tạp hoặc nhiều partition.

## 7. Điều gì xảy ra nếu không dùng BatchListenerFailedException?

Nếu batch listener ném exception thông thường, chẳng hạn **IllegalStateException**, error handler không biết record nào gây lỗi.

Trong trường hợp đó, **DefaultErrorHandler** sử dụng fallback batch retry behavior: toàn bộ batch có thể được retry. Đây là lựa chọn an toàn khi không có thông tin để phân biệt phần thành công và phần thất bại, nhưng có thể làm các record đã xử lý thành công bị chạy lại.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    for (ConsumerRecord<String, OrderCreated> record : records) {
        fulfillmentService.process(record.value());
    }
}
~~~

Nếu **process()** ném exception, listener không cung cấp index lỗi. Error handler phải xử lý batch theo fallback policy của nó.

So sánh:

| Cách ném lỗi | Thông tin error handler nhận được | Hệ quả thường gặp |
|---|---|---|
| **BatchListenerFailedException** có index | Biết record thất bại | Có thể commit phần trước và retry từ record lỗi |
| Exception thông thường | Không biết record nào thất bại | Có thể retry toàn bộ batch |
| Listener bắt lỗi rồi không ném lại | Container có thể xem listener hoàn tất | Offset có thể được commit dù nghiệp vụ lỗi |

Nếu listener có thể xác định record lỗi, hãy cung cấp thông tin đó. Nếu lỗi xảy ra ở thao tác bulk áp dụng cho toàn batch và không thể xác định record riêng lẻ, exception thông thường có thể là lựa chọn phù hợp hơn.

## 8. Retry và BackOff

**DefaultErrorHandler** kết hợp BackOff để quyết định thời gian và số lần thử lại. Ví dụ:

~~~java
var backOff = new FixedBackOff(2_000L, 3L);
var errorHandler = new DefaultErrorHandler(recoverer, backOff);
~~~

Với cấu hình trên, handler nghỉ 2 giây giữa các lần retry và cho phép ba lần retry theo chính sách BackOff. Tổng thời gian xử lý còn phụ thuộc thời gian listener, network, broker, DLT publish và các lần retry khác ở tầng ứng dụng.

### 8.1. Lỗi tạm thời và lỗi không thể retry

Không phải mọi exception đều nên retry theo cùng cách.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời | DB connection reset, HTTP 503, timeout dependency | Retry có giới hạn và backoff |
| Lỗi dữ liệu | Payload sai định dạng, field bắt buộc thiếu | Thường không retry lâu; recover hoặc DLT |
| Lỗi cấu hình | Sai topic, thiếu ACL, serializer không tương thích | Sửa cấu hình/quyền, không retry vô hạn |
| Lỗi nghiệp vụ có thể khắc phục | Trạng thái order chưa sẵn sàng do eventual consistency | Chọn retry policy phù hợp với thời gian chờ nghiệp vụ |

Có thể cấu hình exception không retry bằng các API phân loại exception của **DefaultErrorHandler**, ví dụ:

~~~java
errorHandler.addNotRetryableExceptions(IllegalArgumentException.class);
~~~

Chỉ áp dụng phân loại này nếu exception đó thực sự biểu thị lỗi không thể khắc phục bằng retry. Nếu một exception có thể bọc lỗi tạm thời, hãy phân loại dựa trên cause và semantics của ứng dụng.

### 8.2. Retry hết và recoverer

Khi số lần retry đã hết, recoverer được gọi cho record lỗi. Recoverer có thể:

- Ghi log và đánh dấu record đã recover theo policy.
- Publish record sang DLT.
- Lưu record vào kho lỗi riêng.
- Kích hoạt quy trình xử lý thủ công.

Nếu recoverer gửi DLT thất bại, cần bảo đảm lỗi publish không bị xem là recovery thành công. Hãy cấu hình principal có quyền WRITE trên DLT, quan sát publish future và xử lý lỗi recovery theo chính sách vận hành.

## 9. Dead-letter topic và record lỗi

**DeadLetterPublishingRecoverer** thường được dùng để publish record đã hết retry sang DLT. Nó có thể giữ lại payload, key và headers gốc, đồng thời thêm headers mô tả exception và nguồn record tùy cấu hình.

Một ví dụ tạo recoverer:

~~~java
@Bean
public DeadLetterPublishingRecoverer deadLetterPublishingRecoverer(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    return new DeadLetterPublishingRecoverer(kafkaTemplate);
}
~~~

Mặc định, destination có thể được suy ra từ topic gốc và partition của record. Nếu dùng chiến lược đặt tên DLT riêng hoặc partition mapping riêng, cấu hình destination resolver phù hợp với topology.

Khi dùng DLT, cần lưu ý:

- DLT phải tồn tại hoặc broker phải cho phép tạo topic theo chính sách.
- Số partition của DLT cần phù hợp với chiến lược ánh xạ partition.
- Principal của producer cần quyền WRITE trên DLT.
- Consumer điều tra/replay cần quyền READ trên DLT và quyền READ trên group của nó.
- Dữ liệu nhạy cảm trong payload/header cần được bảo vệ như topic gốc.
- Phải có quy trình replay hoặc xử lý thủ công, tránh để DLT backlog tồn tại vô thời hạn.

**BatchListenerFailedException** xác định record lỗi; recoverer quyết định xử lý record đó sau khi retry hết. Hai thành phần có vai trò khác nhau.

## 10. Xử lý batch chứa nhiều partition

Một poll có thể trả về record từ nhiều partition. Index trong **BatchListenerFailedException** là index trong danh sách listener nhận được, không phải offset và không đại diện cho partition.

Ví dụ:

~~~text
Index 0 -> partition 0, offset 10
Index 1 -> partition 1, offset 20
Index 2 -> partition 0, offset 11  <-- lỗi
Index 3 -> partition 1, offset 21
~~~

Nếu index 2 thất bại, record lỗi là partition 0, offset 11. Record trước nó trong danh sách có thể thuộc partition 1. Error handler cần quản lý offset theo từng partition chứ không đơn giản commit mọi offset nhỏ hơn index lỗi.

Đây là lý do nên truyền index đúng với danh sách được listener nhận, giữ metadata **ConsumerRecord** và để **DefaultErrorHandler** thực hiện commit/seek theo Kafka partition semantics.

Không tự tính offset bằng cách lấy offset của record lỗi trừ một. Offset trong partition có thể không liên tục do compaction, transaction marker hoặc các khoảng offset không có record mà consumer nhìn thấy. Hãy để framework quản lý offset dựa trên các record thực tế trong poll.

## 11. Cấu hình batch listener đầy đủ

Một ví dụ tổng hợp gồm consumer factory, batch listener factory và error handler:

~~~java
@Configuration
public class KafkaBatchConfiguration {

    @Bean
    public DefaultErrorHandler batchErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        var recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
        var backOff = new FixedBackOff(1_000L, 2L);

        return new DefaultErrorHandler(recoverer, backOff);
    }

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            batchKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory,
                    DefaultErrorHandler batchErrorHandler) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setCommonErrorHandler(batchErrorHandler);

        return factory;
    }
}
~~~

Listener:

~~~java
@Service
public class OrderBatchListener {

    private final FulfillmentService fulfillmentService;

    public OrderBatchListener(FulfillmentService fulfillmentService) {
        this.fulfillmentService = fulfillmentService;
    }

    @KafkaListener(
        id = "orders-batch-listener",
        topics = "orders.created",
        groupId = "order-fulfillment",
        containerFactory = "batchKafkaListenerContainerFactory"
    )
    public void consume(
            List<ConsumerRecord<String, OrderCreated>> records) {

        for (int index = 0; index < records.size(); index++) {
            var record = records.get(index);

            try {
                fulfillmentService.process(record.value());
            }
            catch (RuntimeException ex) {
                throw new BatchListenerFailedException(
                    "Failed to process order event",
                    ex,
                    index
                );
            }
        }
    }
}
~~~

Đoạn mã minh họa cách nối listener với error handler. Trong ứng dụng thật, cần bổ sung imports, deserializer, producer serializer cho DLT, security properties và cấu hình topic đích. Không nên tạo nhiều bean error handler có cùng mục đích nhưng khác retry policy mà không gắn rõ factory nào sử dụng bean nào.

## 12. BatchListenerFailedException và xử lý song song

Một batch listener có thể muốn xử lý record song song bằng executor hoặc reactive pipeline. Khi đó cần thận trọng với index.

Nếu các tác vụ chạy đồng thời, record index 4 có thể thất bại trước khi index 1 hoàn tất. **BatchListenerFailedException** chỉ ra vị trí lỗi, nhưng nó không tự quản lý những side effect đang chạy ở các thread khác.

Trước khi ném exception, ứng dụng cần biết:

- Những record nào đã hoàn tất side effect.
- Những record nào vẫn đang chạy.
- Những record nào chưa bắt đầu.
- Có thể dừng hoặc hủy công việc còn lại an toàn không.
- Retry record đã hoàn tất có gây duplicate không.

Một chiến lược đơn giản hơn là xử lý tuần tự trong batch và ném exception ngay khi gặp lỗi. Nếu cần xử lý song song, hãy thu thập kết quả theo index, đợi các tác vụ kết thúc hoặc hủy theo chính sách, rồi mới báo lỗi cho container. Side effect phải idempotent vì crash có thể xảy ra ở mọi thời điểm trước commit.

Không ném exception với index thấp hơn hoặc cao hơn record thực sự thất bại chỉ để điều khiển retry. Làm vậy có thể khiến record đã hoàn tất bị chạy lại hoặc record lỗi bị bỏ qua.

## 13. BatchListenerFailedException và Kafka transaction

Khi listener container sử dụng Kafka transaction, xử lý lỗi đi theo semantics rollback của transaction và cấu hình **AfterRollbackProcessor**. Không nên áp dụng máy móc mô tả commit/seek của **DefaultErrorHandler** non-transactional vào container transactional.

Trong transactional consume-transform-produce, listener xử lý batch và gửi output trong transaction. Nếu exception làm transaction abort, output trong transaction không được commit cùng offset input. Sau rollback, **AfterRollbackProcessor** quyết định cách redeliver hoặc recover record.

**BatchListenerFailedException** có thể cung cấp vị trí record lỗi cho các luồng xử lý batch có hỗ trợ semantics này, nhưng hành vi cụ thể phụ thuộc phiên bản Spring Kafka và cấu hình rollback processor. Khi dùng transaction, cần kiểm tra tài liệu/API của đúng phiên bản, đặc biệt cách commit offset của phần batch trước record lỗi và cách recover sau rollback.

Kafka transaction không bao gồm transaction của DB hoặc HTTP service. Nếu listener đã ghi DB rồi Kafka transaction rollback, DB không tự rollback. Dùng outbox/inbox hoặc DB transaction cùng idempotency để xử lý ranh giới này.

## 14. Quan sát và chẩn đoán

Khi vận hành **BatchListenerFailedException**, nên log đủ metadata của record lỗi và quan sát retry/recovery.

| Chỉ số/thông tin | Ý nghĩa |
|---|---|
| Failed record topic | Topic chứa record gây lỗi |
| Failed record partition | Partition của record lỗi |
| Failed record offset | Vị trí record trong partition |
| Failed batch index | Vị trí record trong danh sách listener nhận |
| Exception class | Loại lỗi và khả năng retry |
| Retry attempt | Số lần thử xử lý record |
| BackOff delay | Thời gian chờ giữa các lần retry |
| Recovery result | Record đã được recover, publish DLT hay tiếp tục lỗi |
| DLT ingress rate | Số record được chuyển sang DLT |
| Consumer lag | Mức backlog trong group |
| Processing duration | Thời gian xử lý batch và từng record |

Ví dụ log có cấu trúc:

~~~text
listener=orders-batch-listener
groupId=order-fulfillment
topic=orders.created
partition=2
offset=1052
batchIndex=3
exception=OrderValidationException
action=retry
~~~

Không đưa event ID hoặc order ID vào metric label có cardinality cao. Có thể ghi chúng trong log hoặc trace để truy vết một event cụ thể.

### 14.1. Dấu hiệu cần điều tra

- Cùng một index thất bại liên tục: kiểm tra dữ liệu record và tính deterministic của lỗi.
- Retry rate tăng nhưng DLT không tăng: xem BackOff, thời gian xử lý và khả năng retry thành công.
- DLT ingress tăng đột biến: kiểm tra schema, producer version và downstream dependency.
- Consumer lag tăng trong khi batch processing duration tăng: xem listener có bulk call chậm hoặc xử lý đồng bộ quá lâu không.
- Record trước index lỗi bị xử lý lại: kiểm tra offset commit, rebalance, transaction và side effect idempotency.
- DLT publish thất bại: kiểm tra producer principal, ACL, topic tồn tại và serializer.

## 15. Những lỗi sử dụng thường gặp

**Dùng index bắt đầu từ 1.** Index của Java List bắt đầu từ 0. Truyền sai index làm error handler xử lý sai ranh giới batch.

**Truyền Kafka offset thay cho index.** Offset là vị trí trong partition, còn failed index là vị trí trong danh sách listener nhận.

**Ném exception thông thường dù biết record lỗi.** Error handler có thể phải retry toàn bộ batch, làm record đã xử lý chạy lại.

**Bắt exception rồi chỉ ghi log.** Listener kết thúc bình thường có thể khiến container coi batch đã xử lý thành công.

**Ném BatchListenerFailedException sau khi tiếp tục xử lý các record còn lại.** Handler có thể redeliver các record đã tạo side effect; cần xác định trạng thái của từng record trước khi báo lỗi.

**Cho rằng exception tự gửi record sang DLT.** Recoverer được cấu hình trong error handler mới quyết định recovery; exception chỉ cung cấp thông tin record lỗi.

**Không cấu hình retry policy.** BackOff mặc định có thể không phù hợp với latency và dependency của ứng dụng. Chọn retry count và delay có chủ đích.

**Không phân biệt lỗi tạm thời và lỗi dữ liệu.** Retry một payload sai định dạng nhiều lần không làm payload trở nên hợp lệ.

**Quên quyền DLT.** Error handler có thể xử lý đúng nhưng publish recovery thất bại do thiếu WRITE trên topic DLT.

**Không làm side effect idempotent.** Record có thể được redeliver sau crash, rebalance hoặc rollback. Database/API cần bảo vệ khỏi tác động lặp.

**Dùng semantics non-transactional cho listener transactional.** Transactional container có rollback processor và commit behavior riêng; cần kiểm tra đúng cấu hình.

## 16. Quy trình áp dụng

1. Xác nhận listener thực sự là batch listener và container dùng **DefaultErrorHandler** hoặc handler có hỗ trợ semantics tương ứng.
2. Nhận batch dưới dạng danh sách có thứ tự ổn định; ưu tiên **ConsumerRecord** khi cần metadata.
3. Xử lý từng record và giữ index của record đang thực hiện.
4. Khi một record thất bại, ném **BatchListenerFailedException** với cause và index zero-based chính xác.
5. Chọn BackOff phù hợp với loại lỗi, SLO và giới hạn thời gian xử lý.
6. Cấu hình recoverer nếu cần DLT hoặc cơ chế lưu lỗi khác.
7. Bảo đảm DLT publisher có serializer, topic và ACL phù hợp.
8. Làm side effect idempotent để chịu được redelivery.
9. Theo dõi failed index, topic/partition/offset, retry, recovery, DLT và consumer lag.
10. Nếu dùng Kafka transaction, xác minh semantics rollback và **AfterRollbackProcessor** theo phiên bản Spring Kafka đang chạy.
11. Thử tình huống lỗi ở record đầu, giữa và cuối batch trong môi trường kiểm thử để xác nhận hành vi thực tế.
12. Ghi lại retry/recovery policy và quy trình xử lý DLT trong runbook.

## 17. Ví dụ tổng hợp: xử lý batch OrderCreated

Một consumer nhận batch gồm bốn event:

~~~text
Index 0: OrderCreated(order-100) -> thành công
Index 1: OrderCreated(order-101) -> thành công
Index 2: OrderCreated(order-102) -> lỗi validation
Index 3: OrderCreated(order-103) -> chưa xử lý
~~~

Listener:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "batchKafkaListenerContainerFactory"
)
public void consume(List<ConsumerRecord<String, OrderCreated>> records) {
    for (int index = 0; index < records.size(); index++) {
        var event = records.get(index).value();

        try {
            fulfillmentService.process(event);
        }
        catch (OrderValidationException ex) {
            throw new BatchListenerFailedException(
                "Invalid order event",
                ex,
                index
            );
        }
    }
}
~~~

Với index 2, **DefaultErrorHandler** biết record lỗi là OrderCreated(order-102). Các record trước lỗi có thể được ghi nhận đã xử lý, còn record lỗi được retry theo BackOff. Nếu retry hết và recoverer publish thành công, record lỗi được chuyển tới DLT; record sau đó có thể được đọc lại và xử lý tiếp.

Để tránh tạo fulfillment hai lần khi có replay, service có thể dùng **eventId** ổn định và bảng inbox với unique constraint. Việc ghi nhận event ID và tạo fulfillment cần nằm trong cùng transaction DB. Nếu consumer crash sau khi DB commit nhưng trước khi Kafka commit offset, lần giao lại sẽ nhận ra event đã được xử lý.

Nếu OrderCreated(order-102) là lỗi dữ liệu không thể khắc phục, retry nhiều lần chỉ làm chậm batch. Có thể cấu hình loại exception này không retry hoặc dùng retry ngắn rồi chuyển DLT. Nếu lỗi là DB timeout tạm thời, retry với backoff có thể giúp xử lý thành công mà không cần can thiệp thủ công.

## 18. Ghi nhớ

**BatchListenerFailedException** là tín hiệu để Spring Kafka biết record nào trong batch listener đã thất bại. Index phải là vị trí zero-based trong danh sách record của lần gọi listener hiện tại; nó không phải Kafka offset hoặc partition number.

Khi kết hợp với **DefaultErrorHandler**, exception giúp framework xử lý phần record trước lỗi, retry record lỗi và tiếp tục phần còn lại theo retry/recovery policy. Nếu không xác định được record lỗi và chỉ ném exception thông thường, handler có thể phải retry toàn bộ batch.

Exception không tự retry, commit hay publish DLT. Hãy cấu hình error handler, BackOff và recoverer rõ ràng, ghi log metadata của record lỗi và bảo vệ side effect bằng idempotency. Với transactional listener, xác nhận thêm semantics rollback và **AfterRollbackProcessor** theo phiên bản Spring Kafka thực tế.

