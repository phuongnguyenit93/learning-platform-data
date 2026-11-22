# AfterRollbackProcessor

Trong Spring Kafka, khi listener container được cấu hình chạy **Kafka transaction**, một lỗi từ listener có thể làm transaction bị rollback. Tuy nhiên, rollback transaction mới chỉ xử lý những record và offset thuộc **transaction hiện tại**; nó không tự quyết định consumer phải đọc lại record nào, chờ bao lâu hay chuyển record lỗi đi đâu khi retry đã hết. Thành phần **`AfterRollbackProcessor`** đảm nhiệm phần quan trọng đó trong quy trình phục hồi sau rollback.

Implementation thông dụng là **`DefaultAfterRollbackProcessor`**. Nó có thể định vị lại consumer tới các offset cần đọc lại, áp dụng backoff giữa những lần thất bại và, với cấu hình phù hợp, gọi recoverer để chuyển một record liên tục lỗi sang Dead Letter Topic (DLT). Khi cần bảo đảm tính nguyên tử giữa publish DLT và xác nhận offset đã recover, nó còn có thể phối hợp một **transaction mới**.

Bài học này tập trung vào ý nghĩa của `AfterRollbackProcessor`, cách cấu hình trong Spring Kafka, các ranh giới exactly-once và cách vận hành khi transaction liên tục rollback.

## 1. Vị trí trong vòng đời một Kafka transaction

Một luồng consume-process-produce transactional điển hình:

~~~text
Kafka input topic
      |
      v
Consumer poll()
      |
      v
Listener container bắt đầu Kafka transaction
      |
      v
@KafkaListener xử lý record và phát output bằng KafkaTemplate
      |
      +---- Thành công -----------------------------+
      |                                             |
      |                                Commit output + input offset
      |                                trong cùng Kafka transaction
      |
      +---- Ném exception
                   |
                   v
             Rollback transaction
                   |
                   v
             AfterRollbackProcessor
                   |
                   +---- Seek / sắp xếp để poll lại
                   |
                   +---- Backoff và retry
                   |
                   +---- Hết retry: recovery / DLT
~~~

Điểm cốt lõi: **Kafka transaction rollback không đồng nghĩa Kafka consumer đã tự quay lại offset cũ**. Consumer có *vị trí đọc hiện tại* trong bộ nhớ và *offset đã commit* của consumer group. Sau một lần `poll()`, vị trí đọc có thể đã tiến tới sau các record vừa nhận, dù transaction xử lý chúng thất bại. Container cần điều phối việc seek/re-fetch để những record chưa được xác nhận vẫn có cơ hội được xử lý lại.

Ví dụ input partition có record ở offset 100, 101 và 102:

1. Consumer poll nhận ba record.
2. Listener xử lý offset 100, sau đó lỗi tại 101.
3. Kafka transaction rollback: output của transaction không trở thành dữ liệu đã commit; offset input của transaction cũng không được commit.
4. `AfterRollbackProcessor` giúp định vị lại consumer để xử lý lại các record cần thiết, thay vì bỏ qua phần còn lại của poll.
5. Nếu offset 101 liên tục lỗi và đã hết retry, recovery policy có thể cách ly record đó rồi để luồng xử lý tiến tiếp.

Chi tiết record nào được seek phụ thuộc record/batch listener, các record trong poll, thứ tự xử lý và chính sách recovery của phiên bản Spring Kafka đang dùng.

## 2. Phân biệt AfterRollbackProcessor và error handler

Spring Kafka có nhiều thành phần xử lý lỗi, nhưng không phải chúng thay thế nhau hoàn toàn:

| Thành phần | Ngữ cảnh chủ yếu | Nhiệm vụ |
|---|---|---|
| `CommonErrorHandler` / `DefaultErrorHandler` | Listener container, đặc biệt luồng non-transactional | Xử lý listener exception, retry/backoff, seek hoặc recover theo cấu hình. |
| `AfterRollbackProcessor` | Sau khi listener transaction rollback | Điều phối việc đọc lại các record sau rollback và recovery phù hợp transaction. |
| `DefaultAfterRollbackProcessor` | Implementation mặc định phổ biến cho transactional listener | Seek/re-fetch, backoff và recoverer sau khi vượt giới hạn thất bại. |
| `DeadLetterPublishingRecoverer` | Có thể được error handler hoặc AfterRollbackProcessor sử dụng | Publish record lỗi sang DLT cùng metadata chẩn đoán. |
| `@RetryableTopic` | Non-blocking retry bằng những topic phụ trợ | Định tuyến record sang retry topic và DLT theo lịch trì hoãn. |

Với listener dùng Kafka transaction, **exception cần dẫn đến rollback**. Spring Kafka thường không gắn một error handler chặn exception trong cấu hình container transactional mặc định để lỗi được truyền ra và transaction rollback. Nếu tự cấu hình một common error handler mà handler bắt lỗi rồi trả về như thể thành công, transaction có thể không rollback như mong muốn.

Không dùng `DefaultErrorHandler` như một thay thế máy móc cho `AfterRollbackProcessor` trong transactional container. Cũng không giả định `@RetryableTopic` tương thích với container transactions ở mọi phiên bản; non-blocking retry và container transaction có các ràng buộc riêng.

## 3. DefaultAfterRollbackProcessor hoạt động thế nào?

`DefaultAfterRollbackProcessor<K,V>` triển khai hợp đồng `AfterRollbackProcessor<K,V>`. Mô hình phổ biến với record listener:

- Khi transaction xử lý thất bại, container rollback transaction đang mở.
- Processor xác định record cần xử lý lại và điều chỉnh consumer position, thông thường bằng seek trên các topic-partition liên quan.
- Một `BackOff` quyết định khoảng chờ trước lần thử tiếp theo.
- Sau số lần retry được cấu hình, processor có thể gọi một **recoverer** cho record liên tục thất bại.
- Khi recovery thành công, processor có thể đưa consumer tiến qua record đã được xử lý theo chính sách.
- Các record khác vẫn phải tuân theo ranh giới offset của chính partition; recovery một record không được âm thầm làm mất các record chưa xử lý.

Ví dụ:

~~~text
Input partition P0: [A@10] [B@11] [C@12]

A xử lý thành công, B ném exception
         |
         v
Transaction rollback
         |
         v
Sau rollback: A/B/C có thể được giao lại theo
trạng thái transaction và cơ chế seek/re-fetch
         |
         v
B vẫn lỗi sau số lần retry đã định
         |
         v
Recover B -> DLT -> tiến tới các record tiếp theo
~~~

Vì A có thể được xử lý lại sau khi transaction rollback, không nên giả định một thao tác ngoài Kafka đã thực hiện trong lúc xử lý A sẽ tự động được đảo ngược. Database, email, HTTP và những hệ thống ngoài transaction Kafka cần idempotency hoặc chiến lược phối hợp riêng.

### 3.1. Backoff và số lần thử

`DefaultAfterRollbackProcessor` nhận một Spring `BackOff` để điều tiết retry. Ví dụ `FixedBackOff(1_000L, 2L)` biểu diễn khoảng chờ 1 giây và tối đa **hai lần retry** trong hợp đồng `FixedBackOff` (ngoài lần xử lý ban đầu).

Với exponential backoff, có thể dùng implementation `BackOff` phù hợp. Hãy đặt giới hạn hữu hạn, cân nhắc thời gian xử lý listener và ngân sách retry. Retry một lỗi dữ liệu vĩnh viễn không giới hạn sẽ làm lag của partition tăng và giữ resource không cần thiết.

### 3.2. Recovery sau khi hết retry

Recoverer thường có dạng xử lý `ConsumerRecord` cùng exception. Một lựa chọn phổ biến là `DeadLetterPublishingRecoverer` để phát record tới DLT. Nó giúp tách record “poison pill” khỏi luồng chính sau khi chính sách retry hoàn tất.

Không phải record nào cũng nên vào DLT. Có thể có luồng nghiệp vụ cần dừng container, cảnh báo vận hành hoặc chờ một dependency phục hồi. Cách recover được chọn phải phản ánh yêu cầu tính đúng đắn, không chỉ nhu cầu giảm consumer lag.

## 4. Cấu hình container transaction trong Spring Kafka

Ví dụ dưới đây minh họa các thành phần được ghép lại. Giả sử ứng dụng có một `ProducerFactory` đã được bật Kafka transaction và một `ConsumerFactory` tương ứng.

~~~java
@Configuration
@EnableKafka
public class OrderKafkaConfiguration {

    @Bean
    KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
            ProducerFactory<String, OrderEvent> producerFactory) {
        return new KafkaTransactionManager<>(producerFactory);
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory,
            KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager,
            DefaultAfterRollbackProcessor<String, OrderEvent> afterRollbackProcessor) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties()
                .setKafkaAwareTransactionManager(kafkaTransactionManager);
        factory.setAfterRollbackProcessor(afterRollbackProcessor);

        return factory;
    }
}
~~~

Trong các phiên bản Spring Kafka cũ, API để gắn transaction manager lên container có thể mang tên khác (ví dụ `setTransactionManager`). Các ví dụ trên sử dụng kiểu API của những phiên bản hỗ trợ `setKafkaAwareTransactionManager`; cần chọn đúng API của dependency đang dùng.

Ví dụ Spring Boot bật transaction phía producer:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-worker-0-
      acks: all
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

`transaction-id-prefix` cần được thiết kế duy nhất giữa các producer đang hoạt động đồng thời, đồng thời phù hợp với cơ chế fencing khi restart/failover. Không dùng cùng prefix cho mọi replica active-active nếu chúng có thể tạo trùng transactional ID.

`read_committed` đặc biệt quan trọng với **consumer downstream**: nó giúp chỉ nhìn thấy record từ transaction đã commit, không đọc các record thuộc transaction bị abort. Nó không tự bật Kafka transaction cho listener và cũng không thay thế AfterRollbackProcessor.

### 4.1. Listener tham gia transaction do container quản lý

~~~java
@Component
public class OrderListener {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;
    private final OrderService orderService;

    public OrderListener(
            KafkaTemplate<String, OrderEvent> kafkaTemplate,
            OrderService orderService) {
        this.kafkaTemplate = kafkaTemplate;
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.in",
            groupId = "order-worker",
            containerFactory = "orderListenerFactory")
    public void onOrder(ConsumerRecord<String, OrderEvent> record) {
        OrderEvent transformed = orderService.transform(record.value());
        kafkaTemplate.send("orders.out", record.key(), transformed);
    }
}
~~~

Trong listener container transactional được cấu hình phù hợp, `KafkaTemplate` tham gia transaction hiện tại. Khi listener hoàn tất thành công, offset đầu vào và output Kafka được commit nguyên tử trong phạm vi Kafka. Nếu listener ném exception, transaction rollback và AfterRollbackProcessor xử lý việc khôi phục.

Không gọi `KafkaTemplate.executeInTransaction(...)` một cách tùy tiện bên trong listener đã có container transaction rồi mong hai transaction tự hợp nhất; hãy thiết kế transaction boundary và producer factory rõ ràng.

## 5. Cấu hình DefaultAfterRollbackProcessor với recoverer

Một cấu hình thực tế sử dụng `DeadLetterPublishingRecoverer` làm đường thoát cho record lỗi:

~~~java
@Bean
DefaultAfterRollbackProcessor<String, OrderEvent> afterRollbackProcessor(
        KafkaTemplate<String, OrderEvent> kafkaTemplate) {

    var recoverer = new DeadLetterPublishingRecoverer(
            kafkaTemplate,
            (record, exception) ->
                    new TopicPartition(
                            record.topic() + ".DLT",
                            record.partition()));

    var backOff = new FixedBackOff(1_000L, 2L);

    var processor =
            new DefaultAfterRollbackProcessor<String, OrderEvent>(
                    recoverer,
                    backOff);

    processor.setKafkaTemplate(kafkaTemplate);
    processor.setCommitRecovered(true);

    return processor;
}
~~~

Các import chính:

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultAfterRollbackProcessor;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;
~~~

Trong ví dụ này:

- Recoverer định tuyến record lỗi từ topic `orders.in` sang `orders.in.DLT` và giữ partition number. Topic DLT phải có partition đích tồn tại; nếu không, publish có thể thất bại. Có thể dùng destination resolver khác theo chiến lược hạ tầng.
- `FixedBackOff` giới hạn số retry và khoảng chờ.
- `setKafkaTemplate` cung cấp Kafka operations mà processor cần cho việc xử lý recovered offset trong transaction mới.
- `setCommitRecovered(true)` dùng cùng cấu hình transaction phù hợp để gửi offset của record đã recover vào transaction mới.
- Recoverer cần dùng producer phù hợp với Kafka transaction nếu muốn DLT publish và recovered offset được commit nguyên tử.

Đây là ví dụ cho **record listener**. Nó không cam kết mọi phiên bản API, default và kiểu serializer đều giống nhau. Nếu DLT cần gửi raw `byte[]` từ record lỗi deserialization, cần serializer tương thích thay vì mặc định dùng serializer của `OrderEvent`.

### 5.1. Vì sao commitRecovered quan trọng?

Giả sử record ở offset 51 liên tục thất bại và đã được publish vào DLT. Sau đó, consumer cần tiến tới offset 52. Nếu publish DLT thành công nhưng offset của input không được xác nhận bền vững, khi restart record ở offset 51 có thể bị đọc lại và xuất hiện thêm trong DLT.

Một cấu hình recovery transactional phù hợp có thể gom:

~~~text
Transaction xử lý chính: rollback
            |
            v
Mở transaction phục hồi mới
            |
            +---- Publish record lỗi vào DLT
            |
            +---- Send offset 52 cho consumer group
            |
            v
Commit transaction phục hồi
~~~

Nếu transaction phục hồi commit, DLT output và recovered input offset cùng được xác nhận trong phạm vi Kafka. Nếu transaction thất bại hoặc bị abort, hai thao tác không được xem là commit thành công. Đây là ranh giới hữu ích để tránh tình huống “DLT đã ghi nhưng offset chưa tiến” trong phần recovery Kafka.

Tính nguyên tử này **không bao phủ các tác dụng phụ bên ngoài Kafka**. Một lần gọi HTTP thành công hoặc database commit trước đó vẫn cần idempotency/compensation riêng.

## 6. Phân biệt transaction chính và transaction phục hồi

Không thể commit một transaction đã rollback. Nếu cần DLT publish và recovered offset cùng commit, hệ thống phải thực hiện chúng trong một **transaction mới** sau rollback.

| Bước | Transaction | Kết quả khi thất bại |
|---|---|---|
| Xử lý record đầu vào và gửi output chính | Transaction listener | Rollback output Kafka và input offset thuộc transaction. |
| AfterRollbackProcessor điều phối seek/retry | Sau rollback | Chuẩn bị redelivery hoặc recovery. |
| Publish DLT và commit recovered offset | Transaction phục hồi mới khi được cấu hình | Nếu rollback, không coi recovery là đã hoàn tất. |
| Xử lý record tiếp theo | Transaction listener tiếp theo | Tuân theo ranh giới transaction mới. |

Có thể sử dụng cùng KafkaTemplate/ProducerFactory transactional cho các bước phù hợp, nhưng phải để Spring Kafka quản lý transaction context. Không tự commit offset bằng một consumer khác ngoài cơ chế container rồi kỳ vọng transaction recovery vẫn nguyên tử.

Ngoài ra, không đánh đồng việc **recoverer trả về không lỗi** với việc **DLT thực sự đã ghi thành công** trong mọi kiểu producer send. Với đường DLT đáng tin cậy, cần sử dụng cấu hình recoverer/producer chờ hoặc kiểm tra kết quả gửi phù hợp phiên bản để lỗi publish được truyền ra thay vì bị bỏ qua.

## 7. Cách chọn BackOff cho transactional listener

Backoff nên phù hợp với loại lỗi và thời gian có thể giữ partition trong lúc chờ. Một số lựa chọn thường gặp:

| Tình huống | Chiến lược |
|---|---|
| Timeout phụ thuộc ngắn hạn | Một vài lần retry với fixed hoặc exponential backoff. |
| Dịch vụ phụ thuộc bị quá tải | Exponential backoff có giới hạn, tránh retry đồng loạt. |
| Payload sai schema không thể xử lý | Giới hạn retry hoặc phân loại để recovery sớm. |
| Lỗi nghiệp vụ vĩnh viễn | Cách ly/đưa DLT theo chính sách nghiệp vụ. |
| Broker hoặc transaction coordinator bất ổn | Quan sát lỗi transaction/cluster; không chỉ tăng retry listener. |

Với retry kéo dài, cần xét `max.poll.interval.ms`, heartbeat, rebalance, thời gian transaction và cách backoff được triển khai. `DefaultAfterRollbackProcessor` có thể phối hợp các dạng BackOff và logic pause/seek phù hợp phiên bản, nhưng đừng cho rằng một sleep dài sẽ luôn an toàn cho consumer group.

Khi listener thất bại do một record khó xử lý, thiết kế giới hạn retry giúp partition không bị kẹt vô hạn. Nhưng không được tự động bỏ qua những record chứa thao tác quan trọng chỉ để làm giảm lag.

### 7.1. Exception classification

Một số exception rõ ràng là lỗi vĩnh viễn, ví dụ validation không đạt hoặc dữ liệu không thể deserialize. Có thể cấu hình phân loại exception/retry policy tại processor hoặc recoverer phù hợp API Spring Kafka hiện hành.

Một cách thiết kế là phân nhóm:

- **Retryable**: timeout tạm thời, HTTP 503, phụ thuộc chưa sẵn sàng.
- **Non-retryable**: schema sai vĩnh viễn, trường bắt buộc thiếu, trạng thái nghiệp vụ không cho phép.
- **Operator intervention**: thiếu quyền truy cập DLT, lỗi serializer của recoverer, transaction coordinator không khả dụng kéo dài.

Không nên chỉ dựa trên tên exception chung như `RuntimeException`. Hãy phân tích nguyên nhân gốc; nhiều loại lỗi trong một exception wrapper cần chính sách khác nhau.

### 7.2. Exception thay đổi qua các lần thử

Trong thực tế, một record có thể lần đầu thất bại vì timeout, sau đó thất bại vì validation khi dependency hoạt động lại. Một số phiên bản `DefaultAfterRollbackProcessor` hỗ trợ reset trạng thái backoff khi loại exception thay đổi hoặc khi recovery thất bại. Các tùy chọn như `setResetStateOnExceptionChange` và `setResetStateOnRecoveryFailure` cần được xem xét theo phiên bản.

Nếu retry state không được reset phù hợp, một lỗi mới có thể bị xử lý như đã hết retry do kế thừa trạng thái lỗi cũ. Ngược lại, reset quá thường xuyên có thể kéo dài thời gian giữ record. Chính sách nên được kiểm thử với cả chuỗi exception thay đổi.

## 8. Recovery failure và nguy cơ lặp DLT

Một tình huống dễ bị bỏ qua là **recoverer cũng thất bại**:

~~~text
Listener lỗi -> rollback -> retry hết hạn
                              |
                              v
                      Gửi record sang DLT
                              |
                         broker/ACL/serialization lỗi
                              |
                              v
                    Recovery không hoàn tất
                              |
                              v
                    Record có thể được thử lại
~~~

Nếu DLT chưa được tạo, không có quyền ghi, serializer không xử lý được payload hoặc broker từ chối request, không được xem record đã recover thành công.

Cần bảo đảm:

- DLT có đủ partition cho destination resolver.
- Producer gửi DLT có serializer cho cả record bình thường và record không deserialize được, nếu cần.
- ACL cho phép publish, và replication/acks đáp ứng độ bền dữ liệu.
- Exception khi publish DLT được quan sát và dẫn đến retry/recovery phù hợp.
- Không có vòng lặp replay vô hạn đưa chính record DLT trở lại DLT mà không giới hạn số lần.

Để điều tra, nên log topic/partition/offset gốc, loại lỗi listener, lỗi recoverer và tình trạng transaction. Không log raw payload nhạy cảm hoặc stack trace đầy đủ vào metric label.

## 9. Batch listener có ranh giới khác record listener

Với **record listener**, container biết record cụ thể gây lỗi, nên processor có thể phục hồi theo từng record trong phạm vi hỗ trợ. Với **batch listener**, listener nhận cả một danh sách record và ném exception; nếu exception không chỉ rõ phần tử nào lỗi, framework không thể dễ dàng kết luận record nào trong batch đã thành công.

Ví dụ:

~~~java
@KafkaListener(
        topics = "orders.in",
        containerFactory = "transactionalBatchFactory")
public void onBatch(List<ConsumerRecord<String, OrderEvent>> batch) {
    for (ConsumerRecord<String, OrderEvent> record : batch) {
        orderService.process(record.value());
    }
}
~~~

Nếu record thứ 8 gây lỗi, transaction của cả batch có thể rollback; những record trước đó có thể được thực thi lại khi batch được đọc lại. Tùy phiên bản, AfterRollbackProcessor có khả năng xử lý batch khác nhau; một số tính năng recover toàn batch được bổ sung ở những phiên bản mới.

Không giả định rằng cấu hình recoverer theo từng record hoạt động giống hệt trên batch listener. Nếu cần cách ly chính xác từng poison record, hãy cân nhắc record listener, cách báo lỗi biết index hoặc một quy trình xử lý batch có recovery được kiểm chứng bằng integration test.

## 10. Offset, seek và thứ tự partition

Kafka chỉ bảo đảm thứ tự record **trong cùng partition**. Khi transaction rollback, redelivery là cách để xử lý lại những record chưa được commit; điều này có thể làm tăng độ trễ của record phía sau.

Ví dụ partition có record `A -> B -> C`, trong đó B là poison pill:

~~~text
A thành công -> B lỗi -> rollback
       |
       +---- retry B (và các record cần replay)
                  |
                  +---- retry tiếp
                  |
                  +---- recover B -> DLT
                                   |
                                   v
                                   Tiếp tục C
~~~

Khi recovery B thành công và offset đã được commit theo transaction recovery, consumer có thể tiến qua B. DLT vì thế đóng vai trò lưu record lỗi để không giữ partition chính ở trạng thái kẹt mãi.

Nhưng DLT làm thay đổi **thứ tự hoàn tất nghiệp vụ**: C có thể được xử lý trong khi B chưa được xử lý thành công. Nếu B và C cùng cập nhật một entity có yêu cầu thứ tự nghiêm ngặt, không nên chọn skip-to-DLT mà không có cơ chế chống áp dụng trạng thái sai. Có thể dừng luồng, dùng versioning hoặc cơ chế sửa/replay có kiểm soát.

## 11. Fencing, zombie instance và rollback

Kafka transactional producer sử dụng `transactional.id` và producer epoch để fence phiên producer cũ khi một phiên mới giành cùng identity. Nếu instance cũ bị pause, instance thay thế có thể tăng epoch khiến transaction của instance cũ không còn hợp lệ.

Một lỗi như `ProducerFencedException` là vấn đề **quyền sở hữu producer**, không phải một lỗi nghiệp vụ có thể giải quyết bằng cách retry record vô hạn trên cùng phiên producer đã bị fence.

Khi xuất hiện lỗi transaction:

1. Phân biệt listener exception với lỗi commit/abort transaction hoặc producer fencing.
2. Xác định instance nào thực sự sở hữu transactional identity.
3. Kiểm tra transactional ID prefix có trùng nhau giữa các replica không.
4. Chỉ tiếp tục công việc trên phiên producer hợp lệ, để container quản lý transaction lại từ trạng thái an toàn.
5. Đảm bảo việc xử lý outside Kafka vẫn idempotent nếu có redelivery.

`AfterRollbackProcessor` giúp xử lý record sau rollback khi container còn hoạt động hợp lệ, nhưng không thay thế cơ chế phân quyền transactional producer và không thể tự sửa một cấu hình gây liên tục producer fencing.

## 12. So sánh recovery có và không có Kafka transaction

| Tình huống | Non-transactional consumer | Transactional container + AfterRollbackProcessor |
|---|---|---|
| Listener lỗi | CommonErrorHandler có thể retry/seek/recover | Transaction rollback, AfterRollbackProcessor điều phối retry/recovery. |
| Output Kafka trước khi listener lỗi | Có thể đã được publish thành công độc lập | Output của transaction bị abort không xuất hiện với `read_committed` consumer. |
| Offset input | Commit tùy AckMode/error handling | Offset gửi trong transaction không được commit khi rollback. |
| DLT publish | Có thể độc lập với offset commit | Có thể phối hợp DLT và recovered offset trong transaction phục hồi mới. |
| External DB/HTTP | Không nguyên tử cùng Kafka | Vẫn không nguyên tử chỉ vì Kafka transaction được bật. |
| Redelivery | Vẫn có thể | Vẫn có thể trước khi commit; nghiệp vụ phải chịu được retry. |

Kafka transaction cung cấp bảo đảm mạnh trong **phạm vi các topic/offset Kafka** khi producer và consumer được cấu hình đúng. Nó không bảo đảm exactly-once end-to-end cho hệ thống có database, REST API hay email.

## 13. Quan sát và chẩn đoán AfterRollbackProcessor

Trong production, nên theo dõi cả số lần rollback và hiệu quả phục hồi. Các chỉ số/log quan trọng:

- Số listener exception và số transaction rollback theo topic/partition/exception class.
- Thời gian từ lần xử lý đầu tiên tới khi record thành công hoặc được recover.
- Số lần retry và thời gian backoff của từng nhóm lỗi.
- Consumer lag theo partition, đặc biệt với partition có poison pill.
- Số record publish sang DLT và số lần publish thất bại.
- Lỗi `commitRecovered` hoặc lỗi transaction phục hồi.
- Lỗi transaction coordinator, producer fencing, rebalance trong lúc retry.
- Lượng record còn kẹt trong DLT cần điều tra và replay.

Một dashboard chỉ nhìn lag tổng có thể che giấu một partition đang bị rollback liên tục. Nên liên kết topic, partition, offset, event ID và exception để xác định một record cụ thể gây tắc nghẽn.

Các thông điệp debug như “seek to offset” có thể xuất hiện nhiều lần vì đây là hành vi chủ đích khi retry sau rollback. Quan trọng là liệu cùng một record có eventually success, DLT thành công hoặc đang loop vô hạn.

### Quy trình điều tra ngắn

1. Xác định exception đầu tiên gây rollback và vị trí record.
2. Kiểm tra Kafka transaction đã rollback hay lỗi ở bước commit/abort.
3. Kiểm tra backoff và recovery threshold của processor.
4. Xem record có được seek/re-fetch, hay listener đang bị chặn trong dependency.
5. Nếu hết retry, kiểm tra DLT topic, serializer, ACL và record publish.
6. Kiểm tra offset được commit sau recovery, không chỉ nhìn log recoverer.
7. Quan sát metric lag và xác nhận pipeline tiến tới record tiếp theo.
8. Nếu lỗi vẫn xảy ra, phân biệt poison record với lỗi hạ tầng hay producer fencing.

## 14. Kiểm thử transactional rollback và recovery

Dùng Kafka broker thực, ví dụ Embedded Kafka hoặc Testcontainers, để kiểm thử hành vi commit/abort và consumer offset. Test chỉ gọi trực tiếp listener Java không thể xác nhận Kafka transaction semantics.

Các tình huống nên có:

1. **Thành công:** listener phát output; xác nhận input offset và output Kafka được commit.
2. **Lỗi một lần rồi thành công:** listener ném exception ở lần đầu; xác nhận transaction đầu rollback, record được đọc lại và chỉ output commit cuối cùng được đọc bằng `read_committed`.
3. **Poison record:** listener luôn lỗi; sau số lần retry định trước, record được publish sang DLT.
4. **commitRecovered:** xác nhận DLT output và input offset của record lỗi cùng được xác nhận khi recovery transaction commit.
5. **DLT publish thất bại:** cấu hình thiếu quyền hoặc serializer không phù hợp; xác nhận record không bị âm thầm coi là đã recover.
6. **Nhiều record cùng poll:** một record giữa poll ném exception; xác nhận không bỏ sót record chưa xử lý.
7. **Batch listener:** thất bại ở một phần tử; xác nhận semantics rollback toàn batch theo cấu hình đang dùng.
8. **Restart khi retry:** dừng consumer trước commit và khởi động lại; xác nhận redelivery/idempotency.
9. **Fencing:** chạy hai phiên producer có transactional identity trùng để kiểm tra phản ứng khi phiên cũ mất quyền.
10. **External side effects:** giả lập database/HTTP đã thành công trước Kafka rollback; kiểm tra idempotency khi record được giao lại.

Nên kiểm tra topic bằng consumer có `isolation.level=read_committed`. Không chỉ đếm số record khi đọc với `read_uncommitted`, vì mode này có thể nhìn thấy record từ transaction đã abort tùy trạng thái log và cách đọc.

Đặt timeout hữu hạn cho test, dùng latch hoặc điều kiện offset/record xuất hiện thay vì `Thread.sleep()` dài. Dọn consumer group, topic và executor sau test để không gây tác động chéo.

## 15. Các sai lầm thường gặp

- **Cho rằng rollback tự động đưa consumer về offset cũ:** cần cơ chế điều phối seek/redelivery từ container/AfterRollbackProcessor.
- **Cho rằng AfterRollbackProcessor là transaction manager:** processor phục hồi sau rollback, không tự tạo ranh giới transaction chính của listener.
- **Cấu hình error handler nuốt exception:** có thể khiến transaction không rollback như mong muốn.
- **Dùng retry vô hạn cho lỗi dữ liệu vĩnh viễn:** partition có thể kẹt kéo dài và lag tăng.
- **Gửi DLT nhưng không commit recovered offset phù hợp:** record có thể bị xử lý lại và xuất hiện nhiều lần ở DLT.
- **Tin rằng recoverer trả về nghĩa là DLT bền vững:** phải xem phản hồi producer và cấu hình transaction/recoverer.
- **Dùng DLT thiếu partition so với destination resolver:** publish có thể thất bại khi giữ partition number.
- **Áp dụng record recovery cho batch listener mà không kiểm chứng:** batch có ranh giới retry và nhận diện lỗi khác.
- **Cho rằng Kafka transaction rollback database hoặc HTTP:** các side effect ngoài Kafka vẫn cần idempotency.
- **Bỏ qua isolation.level của consumer kiểm thử/downstream:** dễ kết luận sai về output bị abort.
- **Retry producer đã bị fence:** quyền sở hữu transactional producer không thể khôi phục bằng retry record thông thường.
- **Không kiểm tra thay đổi API theo phiên bản Spring Kafka:** setter, default và behavior recovery có thể khác giữa các release.

## 16. Chọn cấu hình cho production

Một thiết kế vận hành ổn định nên trả lời các câu hỏi:

- Listener container đã được cấu hình transaction manager và producer factory đúng chưa?
- Exception nào phải gây rollback, exception nào có thể recover sớm?
- Backoff và retry limit phù hợp với SLA cũng như consumer lag chưa?
- Sau khi hết retry, hệ thống có DLT/recoverer đủ quyền và serializer phù hợp không?
- Có cần DLT publish **cùng** recovered offset trong transaction mới không?
- Listener là record hay batch; recovery đang áp dụng cho đơn vị nào?
- Sau khi skip record sang DLT, thứ tự nghiệp vụ của record kế tiếp có còn hợp lệ không?
- Database/API có chống xử lý trùng khi transaction Kafka rollback không?
- Monitoring có phân biệt listener rollback, recovery failure, DLT publish failure và producer fencing không?
- Khi thay đổi Spring Kafka version, đã kiểm thử lại semantics tương ứng chưa?

**AfterRollbackProcessor** là mảnh ghép nối giữa rollback transaction và quá trình xử lý lại record. Khi dùng đúng với `DefaultAfterRollbackProcessor`, backoff, recoverer và transaction recovery, nó giúp hệ thống Spring Kafka thoát khỏi các record liên tục lỗi mà không làm mất khả năng quan sát hoặc phá vỡ ranh giới commit của Kafka. Độ tin cậy cuối cùng đến từ sự phối hợp giữa offset, output Kafka, DLT, giới hạn retry và idempotency ở những hệ thống bên ngoài Kafka.
