# Reason FENCED

Trong Spring Kafka, **Reason.FENCED** là một giá trị của **ConsumerStoppedEvent.Reason**. Nó cho biết một consumer listener container đã dừng sau khi **transactional Kafka producer bị fenced**, với điều kiện thuộc tính **stopContainerWhenFenced** của container được bật. Đây là sự kiện lifecycle quan trọng trong các ứng dụng xử lý Kafka transaction, nhất là luồng **consume → process → produce**.

FENCED không đơn thuần có nghĩa là một partition vừa bị rebalance, cũng không phải tên của một exception do business listener ném ra. Nó là **lý do dừng consumer được Spring Kafka ghi nhận** khi container gặp tình trạng transactional producer không còn quyền tiếp tục transaction và chính sách yêu cầu dừng container.

Trong một hệ thống cần reliability cao, phải hiểu vì sao producer bị fenced, offset nào có thể chưa commit, liệu partition đã thuộc một consumer khác hay chưa, và khi nào có thể khởi động container trở lại mà không tạo vòng lặp lỗi hoặc thực hiện side effect trùng.

## 1. Reason.FENCED xuất hiện ở đâu?

Spring Kafka phát hành các application events cho vòng đời listener container. Một event quan trọng là **ConsumerStoppedEvent**, được phát sau khi consumer đóng. Event này có **reason** để giải thích nguyên nhân dừng.

Các reason thường gặp:

| Reason | Ý nghĩa |
|---|---|
| **NORMAL** | Consumer được dừng theo lifecycle thông thường của container |
| **FENCED** | Transactional producer bị fenced và container bật stopContainerWhenFenced |
| **AUTH** | Gặp lỗi authentication/authorization mà không có cấu hình retry tương ứng |
| **NO_OFFSET** | Không tìm thấy offset và chính sách auto.offset.reset là none |
| **ERROR** | Có java.lang.Error nghiêm trọng được ném |
| **ABNORMAL** | Một số phiên bản Spring Kafka bổ sung lý do dừng bất thường |

Các enum constants có thể khác giữa các phiên bản. Đối với bài này, đối tượng cần nhận diện là:

~~~java
ConsumerStoppedEvent.Reason.FENCED
~~~

**Điều kiện cốt lõi**:

~~~text
Kafka transactional producer bị fenced
              |
              v
Listener container nhận tình huống fencing
              |
              v
stopContainerWhenFenced == true ?
              |
      +-------+-------+
      |               |
     true            false
      |               |
      v               v
Container stop     Không suy ra sẽ có
      |            ConsumerStoppedEvent
      v            với reason FENCED
ConsumerStoppedEvent
  reason = FENCED
~~~

Vì vậy, **không phải mọi ProducerFencedException đều đồng nghĩa với việc chắc chắn sẽ nhận được ConsumerStoppedEvent.Reason.FENCED**. Phải xét chính sách stopContainerWhenFenced và vòng đời container.

## 2. Fencing là gì trong Kafka transaction?

Kafka transaction sử dụng **transactional.id** để xác định một transactional producer logic. Kafka broker/transaction coordinator quản lý trạng thái, epoch và các transaction của identity đó.

Khi một producer khác được khởi tạo với cùng transactional.id hoặc coordinator xác định producer cũ không còn hợp lệ, producer cũ có thể bị **fenced**. Producer cũ không được tiếp tục commit transaction như một producer hợp lệ.

~~~text
Producer A
  transactional.id = orders-worker-1
  epoch cũ
        |
        | có một transaction đang xử lý
        v
Producer B khởi tạo cùng transactional.id
  epoch mới
        |
        v
Coordinator vô hiệu producer A
        |
        v
Producer A tiếp tục send / commit
        |
        v
ProducerFencedException hoặc lỗi epoch liên quan
~~~

Fencing là **cơ chế bảo vệ** để tránh hai producer cùng sử dụng một transactional identity và cùng tạo kết quả transaction trái ngược. Không nên coi broker fencing chỉ là một network error có thể retry vô hạn trên producer cũ.

Sau khi producer thực sự bị fenced, ứng dụng cần để producer đi qua lifecycle đóng/thay thế thích hợp. Việc tiếp tục dùng chính producer đó cho transaction tiếp theo không phải cách phục hồi an toàn.

## 3. Vì sao chủ đề FENCED gắn với rebalance?

Trong consumer-initiated Kafka transaction, listener container đọc input record, mở Kafka transaction, gửi output và đưa consumed offsets vào transaction. Kafka cần bảo đảm consumer vẫn có quyền xử lý những partition tương ứng khi transaction hoàn tất.

Nếu consumer group rebalance trong lúc một transaction đang diễn ra, partition có thể được giao lại cho member khác. Consumer cũ không còn nên tiếp tục ghi nhận output/offset như thể mình vẫn là owner hợp lệ.

Ví dụ:

~~~text
orders/P2@51 thuộc Consumer A
          |
          v
Consumer A bắt đầu Kafka transaction T1
          |
          +-- gửi output trong T1
          +-- listener xử lý quá lâu
          |
          v
Rebalance xảy ra
          |
          v
P2 chuyển sang Consumer B
          |
          v
Consumer A cố hoàn tất T1
          |
          v
Transaction gặp fencing / commit failure
          |
          v
Container có thể stop với reason FENCED
~~~

Sơ đồ là tình huống điển hình về mất quyền xử lý hoặc quyền hoàn tất transaction. **Không nên khẳng định cứ rebalance là ProducerFencedException**: phần lớn rebalance bình thường được xử lý qua revoke/assign callbacks mà không cần dừng container theo reason FENCED.

Spring Kafka cũng không phải lúc nào phân biệt rõ được producer fencing là hậu quả của rebalance, transaction timeout hay transactional.id hết hạn. Vì sự không chắc chắn đó, việc cố seek lại partition khi ownership có thể đã mất là nguy hiểm.

## 4. Reason.FENCED khác ProducerFencedException thế nào?

Hai khái niệm thuộc hai tầng khác nhau:

| Khái niệm | Tầng | Thông tin biểu đạt |
|---|---|---|
| **ProducerFencedException** | Kafka client / producer | Producer không còn quyền thực hiện transaction với identity hiện tại |
| **ConsumerStoppedEvent.Reason.FENCED** | Spring Kafka listener container lifecycle | Consumer đã dừng do producer fencing khi cấu hình dừng-on-fence được bật |
| **onPartitionsRevoked** | Kafka consumer rebalance lifecycle | Partition chuẩn bị được thu hồi |
| **onPartitionsLost** | Kafka consumer rebalance lifecycle | Consumer đã mất ownership của partition |

ProducerFencedException là **nguyên nhân kỹ thuật**, còn Reason.FENCED là **tín hiệu hậu quả lifecycle** cho phía Spring application.

Có thể thấy ProducerFencedException trong log nhưng không thấy ConsumerStoppedEvent.Reason.FENCED nếu:

- stopContainerWhenFenced không được bật.
- Lỗi xảy ra ngoài listener container đang theo dõi.
- Một tầng framework khác chuyển đổi hoặc xử lý exception.
- Process dừng đột ngột trước khi publish lifecycle event.
- Phiên bản hoặc cấu hình listener container có hành vi khác với giả định.

Ngược lại, khi đã nhận ConsumerStoppedEvent.Reason.FENCED, cần điều tra producer fencing thực sự, không chỉ tiếp tục bật listener như thể đó là lần rebalance bình thường.

## 5. Điều kiện stopContainerWhenFenced

Spring Kafka cung cấp thuộc tính **stopContainerWhenFenced** trên ContainerProperties. Khi đặt **true**, container sẽ dừng khi phát sinh ProducerFencedException trong đường xử lý transaction mà container quản lý; sau khi consumer đóng, ConsumerStoppedEvent có thể có reason FENCED.

Giá trị mặc định được tài liệu Spring Kafka của nhiều phiên bản liệt kê là **false**. Do đó, nếu hệ thống muốn quan sát chính xác lifecycle stop-on-fence, nên cấu hình tường minh và xác nhận phiên bản dependency hiện tại.

Ví dụ:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        transactionalListenerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                KafkaTransactionManager<String, OrderResult> kafkaTxManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTxManager);
    factory.getContainerProperties()
            .setStopContainerWhenFenced(true);

    return factory;
}
~~~

Đoạn mã minh họa một listener container có Kafka transaction manager và chính sách stop-on-fence. Các kiểu OrderCreated/OrderResult là model của ứng dụng ví dụ. ProducerFactory mà kafkaTxManager sử dụng phải được cấu hình transactional.

Tên setter của transaction manager và cách wiring có thể khác giữa các phiên bản Spring Kafka, nhưng phần cấu hình trực tiếp liên quan bài học là:

~~~java
factory.getContainerProperties().setStopContainerWhenFenced(true);
~~~

Không bật thuộc tính này với kỳ vọng nó **ngăn** producer bị fenced. Nó không ngăn fencing; nó xác định cách listener container phản ứng **sau khi** fencing xảy ra.

## 6. Luồng ConsumerStoppedEvent.Reason.FENCED

Sau khi producer bị fenced và container quyết định dừng:

~~~text
Transactional listener container
       |
       v
Kafka transaction gặp producer fencing
       |
       v
Container nhận lỗi nghiêm trọng cho transaction
       |
       v
stopContainerWhenFenced = true
       |
       v
Container dừng consumer
       |
       v
ConsumerStoppedEvent
  reason = FENCED
       |
       v
Spring @EventListener / ApplicationListener
       |
       +-- log incident
       +-- alert
       +-- cập nhật health/operational state
       +-- quyết định restart có kiểm soát
~~~

**ConsumerStoppedEvent được phát sau khi consumer đóng**, nên event này không phải nơi tiếp tục sử dụng KafkaConsumer cũ để poll hoặc commit offsets.

Với concurrent listener container, nhiều child consumers có thể phát lifecycle events riêng. Một consumer bị fenced không có nghĩa tất cả child consumers cùng dừng trong đúng một callback; mức độ ảnh hưởng cần xác định từ container/child ID và trạng thái thực tế.

## 7. Lắng nghe Reason.FENCED trong Spring

Có thể đăng ký Spring application event listener:

~~~java
@Component
public class KafkaConsumerLifecycleObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerLifecycleObserver.class);

    @EventListener
    public void onConsumerStopped(ConsumerStoppedEvent event) {
        ConsumerStoppedEvent.Reason reason = event.getReason();

        if (reason == ConsumerStoppedEvent.Reason.FENCED) {
            MessageListenerContainer stoppedContainer =
                    event.getSource(MessageListenerContainer.class);

            log.error(
                    "Kafka consumer stopped after producer fencing; " +
                    "listenerId={}, reason={}",
                    stoppedContainer.getListenerId(),
                    reason);

            // Ghi nhận sự cố và kích hoạt quy trình khôi phục có kiểm soát.
        }
    }
}
~~~

Trong ví dụ cần import ConsumerStoppedEvent, MessageListenerContainer, Spring @EventListener và logger tương ứng. getSource(MessageListenerContainer.class) là cách lấy container theo type được tài liệu Spring Kafka mô tả.

Với hệ thống có nhiều listeners, nên ghi nhận thêm instance ID, consumer group, transactional.id prefix và timestamp. **Không log toàn bộ object producer hoặc Kafka credentials**.

Application event có thể được dispatch trên thread publish event tùy cấu hình ApplicationEventMulticaster. Không nên tự thao tác KafkaConsumer từ một listener bất đồng bộ nếu event chứa tham chiếu consumer; KafkaConsumer không phải object có thể sử dụng tùy ý xuyên threads.

## 8. Có nên tự khởi động lại container ngay không?

Spring Kafka cho phép lấy tham chiếu container từ ConsumerStoppedEvent và khởi động lại nó. Tài liệu mô tả khả năng này để phục hồi sau tình huống FENCED.

Tuy nhiên, **không nên restart vô điều kiện ngay khi nhận Reason.FENCED**. Nếu nguyên nhân là hai application instances dùng trùng transactional.id, container vừa restart có thể bị instance còn lại fence tiếp. Kết quả là vòng lặp:

~~~text
FENCED
   |
   v
stop container
   |
   v
restart ngay lập tức
   |
   v
producer mới vẫn dùng transactional.id xung đột
   |
   v
FENCED lần nữa
   |
   v
restart loop
~~~

Khôi phục an toàn thường là:

1. Xác định instance và transactional.id đang bị lỗi.
2. Xem có producer khác đang sử dụng cùng transactional.id hay không.
3. Kiểm tra lịch sử restart, scaling, deployment và rebalance.
4. Kiểm tra transaction timeout và thời gian xử lý listener.
5. Đóng/loại bỏ producer đã bị fenced theo container lifecycle.
6. Chỉ restart khi điều kiện gây fencing đã được giải quyết hoặc có chính sách retry được kiểm soát.
7. Giới hạn số lần restart, có backoff và alert nếu thất bại liên tục.

Không tự gọi restart bằng một vòng lặp vô hạn trong Spring event listener. Với hệ thống nhiều listeners, dùng một lifecycle coordinator hoặc orchestration policy để theo dõi và kiểm soát restart ở cấp ứng dụng.

## 9. Tại sao ProducerFencedException không nên xử lý bằng retry thông thường?

Lỗi mạng tạm thời có thể retry trên một producer đang khỏe; **producer fencing** khác về bản chất. Broker đã coi transactional identity/epoch hiện tại không còn hợp lệ để tiếp tục transaction.

Ví dụ nguy hiểm:

~~~java
try {
    kafkaTemplate.send("orders.result", result).join();
}
catch (Exception ex) {
    // Không nên retry vô hạn mọi exception trên cùng producer.
}
~~~

Nếu lỗi gốc là fencing, retry liên tục trên producer cũ không làm producer đó lấy lại quyền. Thay vào đó, hệ thống phải để transaction thất bại, producer được đóng/thay thế và consumer phục hồi từ một vị trí Kafka hợp lệ.

Với transactional listener, exception cần được truyền đến container/transaction manager để container thực hiện vòng đời phù hợp. Nếu business code bắt và nuốt một lỗi transaction nghiêm trọng, container có thể đánh giá sai trạng thái xử lý hoặc phát sinh lỗi muộn khi commit.

Không biến ProducerFencedException thành lỗi nghiệp vụ thông thường để đẩy ngay vào DLT; DLT thường dành cho **record không xử lý được**, trong khi fencing là lỗi **transactional infrastructure hoặc ownership**.

## 10. Vì sao Spring Kafka có thể bỏ qua AfterRollbackProcessor khi fenced?

Trong transactional listener thông thường, khi business listener ném exception, container rollback transaction rồi có thể dùng **DefaultAfterRollbackProcessor** để seek/retry record.

Khi producer bị fenced, tình huống khác:

~~~text
Business exception thông thường
     |
     v
Kafka transaction rollback
     |
     v
AfterRollbackProcessor
     |
     v
Seek/retry theo ownership hợp lệ

Producer fencing
     |
     v
Không chắc còn sở hữu partition
     |
     v
Không nên seek bừa từ consumer cũ
     |
     v
Container stop khi stopContainerWhenFenced=true
~~~

Spring Kafka documentation lưu ý rằng trong các trường hợp fencing liên quan rebalance, container không thể giả định consumer vẫn được assign các partitions cũ. Vì vậy, **không nên chạy after-rollback seek như khi xử lý một business exception**.

Sự khác biệt này rất quan trọng: cố seek hoặc commit một partition không còn thuộc quyền quản lý có thể gây lỗi hoặc khiến ứng dụng đưa ra quyết định phục hồi sai.

Khi partition được giao cho consumer mới, consumer mới tiếp tục từ committed offset hợp lệ. Những records chưa được commit có thể được xử lý lại theo chính sách của ứng dụng.

## 11. Reason.FENCED và onPartitionsRevoked

**onPartitionsRevoked** là callback rebalance thông thường khi consumer chuẩn bị nhường partitions; **Reason.FENCED** là lý do container đã dừng do transactional producer bị fenced.

| Khía cạnh | onPartitionsRevoked | ConsumerStoppedEvent.Reason.FENCED |
|---|---|---|
| Tầng API | ConsumerRebalanceListener / ConsumerAwareRebalanceListener | Spring Kafka application lifecycle event |
| Khi xảy ra | Trong quá trình thu hồi assignment | Sau khi consumer đóng vì fencing và chính sách stop được bật |
| Phạm vi | Một tập TopicPartition đang bàn giao | Một consumer/container bị dừng |
| Có chắc transaction producer lỗi? | Không | Có nguyên nhân producer fencing |
| Có chắc consumer đã dừng? | Không | Có, ConsumerStoppedEvent phát sau khi consumer đóng |
| Hành động chính | Flush/release state, phối hợp commit nếu còn ownership | Điều tra fencing, đánh giá restart và phục hồi lifecycle |

Rebalance bình thường có thể xảy ra hàng ngày khi scale, deploy hoặc thay đổi membership. FENCED thường là tín hiệu cần điều tra nghiêm túc hơn vì nó liên quan đến khả năng tiếp tục Kafka transaction.

Không suy luận mọi revoke là fencing, hoặc mỗi Reason.FENCED đều có một revoke callback trước đó. Process có thể gặp exception và dừng theo nhiều chuỗi lifecycle khác nhau.

## 12. Reason.FENCED và onPartitionsLost

**onPartitionsLost** cho biết consumer đã mất partition ownership mà không thể bàn giao theo đường revoke thông thường. Trong trường hợp đó, không nên tiếp tục commit offsets hoặc ghi state như owner cũ.

Reason.FENCED có thể xuất hiện trong bối cảnh mất ownership hoặc transactional identity, nhưng hai sự kiện không đồng nghĩa:

~~~text
Consumer A xử lý P1@200
    |
    +-- P1 bị gán cho Consumer B
    |
    +-- A nhận tình huống mất ownership
    |       (có thể có onPartitionsLost)
    |
    +-- Producer transaction của A bị fenced
    |
    +-- Container A stop với Reason.FENCED
            nếu cấu hình stop-on-fence
~~~

Sơ đồ chỉ mô tả một chuỗi có thể xảy ra, không phải lời hứa về thứ tự callback. Nếu process bị kill hoặc mất kết nối, có thể không nhận đầy đủ các sự kiện mong muốn.

Đối với cả partition lost và producer fenced, **không tự commit offsets thuộc partition cũ để "đánh dấu đã xử lý"**. Để consumer mới tiếp tục từ committed offset đã được Kafka công nhận, đồng thời bảo vệ side effects bằng idempotency.

## 13. transactional.id phải duy nhất giữa các instance active

Một nguồn fencing dễ kiểm soát là các service instances dùng trùng transactional.id prefix và dẫn đến trùng identity thực tế của producer.

Ví dụ sai:

~~~text
Pod A:
  transaction-id-prefix = orders-tx-
  transactional.id      = orders-tx-0

Pod B:
  transaction-id-prefix = orders-tx-
  transactional.id      = orders-tx-0

Pod A và Pod B đều đang active
-> có thể fence lẫn nhau
~~~

Một cấu hình đúng phải phân biệt các instances hoạt động đồng thời:

~~~text
Pod A:
  transaction-id-prefix = orders-pod-a-tx-
  transactional.id      = orders-pod-a-tx-0

Pod B:
  transaction-id-prefix = orders-pod-b-tx-
  transactional.id      = orders-pod-b-tx-0
~~~

Đây là các giá trị minh họa; Spring Kafka ProducerFactory có thể tạo nhiều suffix cho transactional producers từ cùng prefix. **Mục tiêu không chỉ là prefix nhìn khác nhau, mà là mọi transactional.id thực tế không xung đột giữa các active producer instances**.

Khi deploy Kubernetes, cần lưu ý:

- Rolling update có thể khiến pod cũ và pod mới cùng sống trong một khoảng thời gian.
- Nếu dùng instance ID sinh từ hostname, phải xác minh tính duy nhất giữa các pod.
- Nếu dùng một cấu hình cố định cho tất cả replicas, nguy cơ xung đột tăng.
- Một pod mới thay thế pod cũ dùng lại identity có thể fence producer cũ theo cơ chế Kafka; điều đó có thể là hành vi mong muốn khi fencing zombie instance, nhưng phải đánh giá orchestration và shutdown.
- Tăng concurrency làm tăng số transactional producers và suffix mà factory cần quản lý.

Không sửa lỗi fencing chỉ bằng cách bỏ Kafka transaction nếu nghiệp vụ cần output và consumed offset được commit nguyên tử.

## 14. transaction timeout và producer expiration

Không phải mọi fencing đều do hai pods trùng transactional.id. Một số trường hợp liên quan **transaction.timeout.ms**, **transactional.id.expiration.ms** hoặc producer bị idle quá lâu.

Hai cấu hình thường bị nhầm:

| Thông số | Tầng | Vai trò |
|---|---|---|
| **transaction.timeout.ms** | Kafka transactional producer | Giới hạn thời gian transaction tồn tại theo chính sách broker |
| **transactional.id.expiration.ms** | Kafka broker | Thời gian transactional identity có thể bị loại khỏi coordinator state khi idle theo điều kiện broker |
| **max.poll.interval.ms** | Kafka consumer | Giới hạn khoảng thời gian giữa các lần poll theo consumer group protocol |

Ví dụ:

~~~text
transaction.timeout.ms = 60 giây

Listener:
  DB lock wait        40 giây
  External API call   30 giây
  Produce + commit     5 giây
  ---------------------------
  Tổng                 75 giây
~~~

Transaction có nguy cơ vượt timeout trước khi xử lý hoàn tất. Khi tiếp tục commit, producer có thể gặp lỗi transactional state/fencing tùy tình huống và phiên bản client.

**Không đánh đồng transaction timeout với max.poll.interval.ms.** Một giới hạn thuộc producer transaction, giới hạn kia thuộc consumer polling và group membership. Cả hai cần được tính trong listener processing budget.

Nếu transactional producer bị idle trong thời gian rất dài, cached producer cũng có thể bị ảnh hưởng bởi transactional.id expiration. Một số phiên bản Spring Kafka hỗ trợ DefaultKafkaProducerFactory maxAge để chủ động thay producer cache trước khi hết hạn.

## 15. Cấu hình transaction timeout có giới hạn

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-instance-a-tx-
      properties:
        "[transaction.timeout.ms]": 120000
    consumer:
      group-id: orders-transformer
      enable-auto-commit: false
      properties:
        "[max.poll.interval.ms]": 300000
~~~

Ví dụ minh họa transaction timeout 120 giây và max poll interval 300 giây. Các giá trị này **không phải khuyến nghị cố định cho production**. Broker có giới hạn transaction timeout tối đa; producer không thể tùy tiện đặt lớn hơn giới hạn broker cho phép.

Khi điều chỉnh:

1. Đo transaction duration thực tế, bao gồm listener, produce, callback và commit.
2. Đo p95/p99 latency của database và downstream APIs.
3. Kiểm tra max.poll.interval.ms cùng với max.poll.records.
4. Đánh giá broker transaction state expiration và producer cache maxAge.
5. Tránh giữ transaction mở để chờ retry backoff nhiều phút.
6. Cấu hình timeout có đủ biên an toàn nhưng không che giấu sự cố treo.

Tăng timeout chỉ giúp tránh false timeout trong công việc hợp lệ. Nó không giải quyết producer IDs trùng nhau hoặc group rebalance do thay đổi membership.

## 16. Reason.FENCED ảnh hưởng tới offset như thế nào?

Trong Kafka consume-process-produce transaction, container có thể đưa consumed offsets vào cùng transaction với các output Kafka.

Ví dụ:

~~~text
Input:
  orders.input / P0 / offset 99

Transaction T1:
  produce orders.output / key O-1001
  send source offset 100 vào transaction

Nếu COMMIT:
  output committed
  group offset 100 committed

Nếu transaction bị abort/fenced trước commit:
  không được coi output và source offset của T1 là committed
~~~

**Original record offset 99** khác với **committed offset 100**. Offset 100 chỉ vị trí tiếp theo mà consumer group cần đọc sau khi record 99 được xử lý thành công.

Nếu producer bị fenced, ứng dụng không nên tự ghi offset 100 bằng consumer.commitSync() để "giải phóng" partition. Làm vậy có thể khiến group bỏ qua một record mà output chưa được commit.

Khi consumer mới nhận partition, nó đọc từ committed offset hợp lệ. Record chưa được commit có thể được xử lý lại; đây là lý do phải giữ idempotency ở các side effects ngoài Kafka.

## 17. read_committed và dữ liệu output sau fencing

Khi transactional listener gửi output, record có thể đã được Kafka broker nhận trước khi transaction commit. Nếu transaction cuối cùng abort, downstream consumer dùng **read_committed** không thấy record thuộc transaction đã abort.

~~~text
Transaction T1:
  produce output A
  producer fenced
  transaction không commit

Downstream read_committed:
  không xem output A của T1 như committed
~~~

Consumer dùng **read_uncommitted** có thể đọc cả records thuộc aborted transactions. Nếu hệ thống downstream cần semantics Kafka transaction, hãy cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
~~~

Không suy luận transaction đã abort chỉ vì log application thấy timeout ở thời điểm commit; một số lỗi phản hồi có thể khiến client không chắc trạng thái cuối cùng. Hãy kiểm tra transaction outcome và dữ liệu committed theo cách có kiểm soát.

Ngoài Kafka, nếu listener đã cập nhật database hoặc gọi HTTP API trước khi bị fenced, các thao tác đó có thể đã hoàn tất. read_committed không rollback những side effects này.

## 18. FENCED không phải lỗi của payload

Khi một record sai schema hoặc business rule, listener có thể ném exception được phân loại retryable/non-retryable và cuối cùng chuyển DLT. Với FENCED, nguyên nhân nằm ở **producer transaction/consumer lifecycle**, không phải chắc chắn ở nội dung record.

| Loại sự cố | Cách xử lý thường phù hợp |
|---|---|
| Payload không deserialize được | ErrorHandlingDeserializer, recovery hoặc DLT giữ original bytes |
| Business validation thất bại | Non-retryable classification, DLT hoặc quy trình nghiệp vụ |
| Downstream timeout ngắn | Retry có backoff hữu hạn |
| ProducerFencedException | Dừng/đóng producer cũ, xác định ownership và transactional identity, phục hồi container an toàn |
| Rebalance thông thường | ConsumerRebalanceListener, revoke/assign và offset management |

Không cấu hình một catch-all business error handler để đưa ProducerFencedException vào DLT như thể record không hợp lệ. Làm vậy có thể bỏ qua nguyên nhân hạ tầng và mất điều kiện commit offset atomically.

Nếu cùng một event luôn dẫn tới lỗi nghiệp vụ sau khi restart, hãy điều tra event riêng. Nhưng Reason.FENCED không cung cấp bằng chứng rằng event ấy là nguyên nhân.

## 19. Phân biệt FENCED với FencedInstanceIdException

Kafka client có những khái niệm "fenced" ở nhiều tầng. **ProducerFencedException** là lỗi của transactional producer. Trong các consumer group dùng static membership, có thể gặp lỗi liên quan đến **FencedInstanceIdException**, nghĩa là identity của một static group member không còn hợp lệ.

Hai trường hợp không giống nhau:

~~~text
Transactional producer fencing:
  transactional.id / producer epoch
  -> ProducerFencedException
  -> có thể dẫn đến ConsumerStoppedEvent.Reason.FENCED

Static consumer membership fencing:
  group.instance.id / member identity
  -> FencedInstanceIdException
  -> consumer group membership problem
~~~

Không dùng cùng một remediation cho cả hai mà chưa xem exception class thực tế. Trùng transactional.id cần kiểm tra producer factory/prefix; trùng group.instance.id cần kiểm tra static member identity và consumer assignment.

**Reason.FENCED theo mô tả của Spring Kafka là producer fenced khi stopContainerWhenFenced=true**, không phải một nhãn tổng quát cho mọi Kafka exception có chữ "fenced".

## 20. Concurrency và child containers

Một ConcurrentMessageListenerContainer thường quản lý nhiều KafkaMessageListenerContainer con, mỗi child có consumer thread và partition assignment riêng.

~~~text
Concurrent container: orders-transformer
    |
    +-- child 0: consumer A -> P0, P1
    +-- child 1: consumer B -> P2, P3
    +-- child 2: consumer C -> P4, P5
~~~

Nếu child 1 gặp producer fencing, event ConsumerStoppedEvent có thể gắn với child container đó. Cần phân biệt **listener ID của child**, trạng thái parent và các child còn lại để tránh kết luận toàn bộ service đã stop.

Khi xử lý event:

- Log source container cụ thể và parent listener ID nếu có.
- Xem trạng thái thực tế của toàn bộ concurrent container trước khi restart.
- Tránh gọi start trên nhiều containers trùng nhau từ nhiều event listeners.
- Không dùng một boolean global như "allKafkaConsumersStopped" chỉ vì một ConsumerStoppedEvent.
- Kiểm tra transactional ID prefix/suffix theo số producer có thể được tạo khi concurrency tăng.

Việc tăng concurrency có thể tăng nhu cầu transactional producer cache và khả năng xuất hiện lỗi khi cấu hình transactional IDs bị xung đột. Nhưng tăng concurrency tự thân không nhất thiết tạo fencing nếu transaction infrastructure được quản lý đúng.

## 21. Restart policy an toàn

Khi nhận Reason.FENCED, có thể xây dựng **controlled recovery**:

~~~text
ConsumerStoppedEvent(reason=FENCED)
        |
        v
Log và alert
        |
        v
Lấy listener/container ID, instance ID,
transaction ID prefix và exception context
        |
        v
Root cause có thể tự phục hồi?
        |
   +----+----+
   |         |
  Có       Chưa rõ / không
   |         |
   v         v
Backoff   Giữ container stopped,
giới hạn  điều tra xung đột,
   |      tránh restart loop
   v
Restart qua lifecycle manager
   |
   v
Quan sát group assignment,
offset và transaction success
~~~

Restart chỉ nên được đánh giá là thành công khi container thực sự bắt đầu consume, nhận assignment và transaction commit lại bình thường, không phải chỉ vì method start() trả về mà không ném exception.

Khi có nhiều replicas, cần coordination để không tạo một loạt restart đồng thời dẫn đến rebalance storm. Với lỗi lặp, nên giới hạn retries, tăng backoff và cảnh báo cho người vận hành.

Một quy trình có thể dựa vào Kubernetes restart policy hoặc một lifecycle manager trong Spring. Chọn đúng cơ chế để tránh **hai hệ thống cùng restart** gây tác dụng ngược.

## 22. Phục hồi partition state sau FENCED

Khi container dừng, các partition đang thuộc consumer có thể được giao cho consumer khác. Bất kỳ partition-scoped in-memory state nào cũng cần được xử lý như state của owner cũ, không tiếp tục ghi nhận tiến độ trên partition đã mất.

Ví dụ:

~~~text
Consumer A:
  P2@51 được xử lý một phần
  In-memory cache đã cập nhật
  Kafka transaction chưa commit

FENCED:
  A dừng
  P2 chuyển sang B

Consumer B:
  đọc lại từ committed offset hợp lệ
  tái dựng state hoặc xử lý idempotent
~~~

Không nên tự seek consumer mới đến "last seen offset" do container cũ lưu trong bộ nhớ. Vị trí đó có thể bao gồm records chưa xử lý thành công và chưa được commit.

Nếu state không thể tái dựng, ứng dụng cần cơ chế checkpoint bền vững và consistency giữa checkpoint với Kafka offset. FENCED không phải thời điểm đảm bảo có thể flush hoàn chỉnh state cục bộ; process có thể mất membership hoặc dừng đột ngột trước cleanup.

## 23. Side effects ngoài Kafka sau fencing

Một transactional listener có thể đồng thời:

- Cập nhật database.
- Gọi REST API.
- Trừ tồn kho.
- Gửi email hoặc notification.
- Publish Kafka output.

Kafka transaction chỉ bảo vệ phần Kafka tham gia transaction đó. Khi producer fenced và Kafka transaction không commit, các side effects bên ngoài có thể đã thực hiện.

~~~text
Attempt 1:
  UPDATE database -> thành công
  Kafka output -> producer fenced
  Kafka transaction không commit

Attempt 2:
  Input được consumer khác đọc lại
  UPDATE database -> nguy cơ chạy lần hai
~~~

Vì vậy:

1. Dùng event ID ổn định qua mọi lần xử lý.
2. Ghi dấu event đã xử lý trong cùng DB transaction với side effect nếu cần deduplicate.
3. Dùng unique constraint/version check để tránh race condition.
4. Với API hỗ trợ idempotency key, truyền key ổn định.
5. Với business state + Kafka event quan trọng, cân nhắc transactional outbox/CDC.

Không nhầm Kafka read-process-write exactly-once semantics với exactly-once business effects.

## 24. Logging và metrics nên theo dõi

Một incident Reason.FENCED cần đủ thông tin để phân biệt xung đột transactional ID, transaction timeout và rebalance:

~~~text
event=consumer_stopped
reason=FENCED
listenerId=orders-transformer-1
instanceId=orders-pod-a
groupId=orders-transformer
transactionIdPrefix=orders-pod-a-tx-
lastInput=orders.input/P2@51
transactionOutcome=failed_or_unknown
action=investigate_before_restart
~~~

Đây là structured log ứng dụng tự thiết kế; không phải output mặc định của Spring Kafka.

Các metrics hữu ích:

- Số ConsumerStoppedEvent theo reason và listener.
- Tỷ lệ FENCED trên mỗi instance/deployment.
- Transaction commit/abort/fencing errors.
- Transaction duration p95/p99.
- Consumer rebalance count/duration.
- Consumer lag theo partition.
- Số listener containers running/stopped.
- Restart attempts và restart failures.
- Thời gian từ FENCED đến khi consumer tiếp tục commit thành công.
- Producer cache exhaustion hoặc transactional producer initialization errors.

Không dùng event ID, offset hoặc full transactional.id làm metric label nếu tạo cardinality cao. Những chi tiết đó phù hợp hơn với log/trace có giới hạn truy cập.

## 25. Chẩn đoán nguyên nhân theo triệu chứng

| Triệu chứng | Nguyên nhân cần kiểm tra | Hành động |
|---|---|---|
| FENCED lặp ngay sau mỗi restart | Trùng transactional.id giữa active instances | Kiểm tra prefix/suffix và pod lifecycle |
| FENCED trùng thời điểm scale/deploy | Rebalance hoặc producer identity conflict | Xem assignment, rollout overlap và commit failure |
| FENCED sau listener xử lý quá lâu | Transaction timeout hoặc consumer mất membership | Đo transaction duration, DB/API time và poll interval |
| FENCED sau thời gian idle rất dài | Transactional identity expiration / cached producer stale | Kiểm tra broker expiration và producer maxAge |
| Output không visible trên downstream | Transaction chưa commit hoặc đã abort | Kiểm tra read_committed, transaction outcome và offset |
| Record input bị xử lý lại | Offset nguồn chưa commit do transaction lỗi | Bảo vệ side effects bằng idempotency |
| ConsumerStoppedEvent không có FENCED dù log có ProducerFencedException | stopContainerWhenFenced=false, context khác hoặc event chưa được phát | Kiểm tra container props và event source |
| Pod có nhiều event FENCED nhưng vài partitions vẫn tiếp tục | Một số child containers dừng, số khác còn chạy | Kiểm tra child/parent container lifecycle |

Một quy trình điều tra:

1. Tìm ProducerFencedException và exception chain trong log cùng thời điểm.
2. Xác định listener ID, instance ID và transactional.id/prefix liên quan.
3. Kiểm tra ứng dụng có nhiều replicas dùng cùng prefix không.
4. So sánh thời gian FENCED với deployment, rebalance và consumer restarts.
5. Xem transaction timeout, max.poll.interval.ms và p99 listener latency.
6. Kiểm tra broker transaction coordinator và trạng thái producer.
7. Xác nhận consumed offset cuối cùng đã committed.
8. Kiểm tra output Kafka với downstream read_committed.
9. Đánh giá side effects ngoài Kafka có bị lặp hoặc chưa hoàn tất không.
10. Quyết định restart có kiểm soát hoặc sửa cấu hình trước.

## 26. Tình huống ví dụ: hai pods cùng transactional.id

Giả sử hai replicas do lỗi deployment cùng sử dụng prefix orders-tx-. Mỗi instance tự tạo transactional producer có suffix 0:

~~~text
Pod A:
  KafkaProducer(tx.id=orders-tx-0)
  bắt đầu transaction T1

Pod B:
  KafkaProducer(tx.id=orders-tx-0)
  khởi tạo producer mới

Kafka coordinator:
  producer epoch của identity được cập nhật

Pod A:
  commit T1 -> ProducerFencedException

Container A:
  stopContainerWhenFenced=true
  stop consumer
  emit ConsumerStoppedEvent.Reason.FENCED
~~~

Với cấu hình này, bật auto-restart ngay trên Pod A không giải quyết xung đột: cả hai pods lại có thể giành cùng transactional ID. Cần sửa cách tạo instance-specific prefix, rolling deployment hoặc producer lifecycle.

Sau khi sửa, container mới dùng transactional producer hợp lệ và consumer có thể đọc lại các records chưa commit từ group offset. Nếu listener đã tạo database side effect trước khi fenced, lần xử lý lại phải idempotent.

## 27. Tình huống ví dụ: transaction dài và rebalance

Giả sử consumer A nhận event và mở transaction, sau đó chờ database lock quá lâu:

~~~text
00:00  poll orders/P0@500
00:01  bắt đầu T1
00:02  gọi DB và chờ lock
01:10  consumer group rebalance / transaction timeout
01:20  DB trả kết quả
01:21  producer cố hoàn tất T1
01:22  transaction commit failure / fencing
01:23  container dừng, reason FENCED nếu bật
~~~

Thời điểm trong sơ đồ chỉ minh họa. Không phải mọi long-running listener đều phát sinh đúng thứ tự lỗi này.

Các biện pháp:

- Giảm thời gian chờ DB lock và timeout các call ngoài.
- Không giữ Kafka transaction mở để chờ backoff dài.
- Điều chỉnh max.poll.records, transaction timeout và max.poll.interval.ms hợp lý.
- Dùng circuit breaker hoặc fail-fast để rollback nhanh khi downstream unavailable.
- Đảm bảo process cũ không tiếp tục làm business side effect sau khi mất ownership.

Không mặc định mở rộng mọi timeout lên nhiều giờ. Transaction càng dài càng tăng rủi ro coordinator failure và làm chậm downstream read_committed.

## 28. Tình huống ví dụ: fenced sau idle lâu

Một application có lưu lượng rất thấp dùng transactional producer cache. Broker có thể hết hạn trạng thái của transactional.id sau thời gian idle phù hợp cấu hình. Khi producer cache cũ được tái sử dụng, có thể xuất hiện lỗi epoch/transactional identity.

~~~text
Application:
  transactional producer được cache
  topic không có records trong thời gian dài

Broker:
  transactional.id state hết hạn theo cấu hình

Record mới:
  container dùng producer cũ
  transaction gặp lỗi producer identity
~~~

Với những phiên bản Spring Kafka hỗ trợ, cấu hình **DefaultKafkaProducerFactory.maxAge** nhỏ hơn thời gian broker expiration có thể giúp thay cached producer trước khi producer trở nên stale.

Không bật định kỳ một "empty transaction" chỉ vì muốn giữ producer sống mà chưa đánh giá overhead và lifecycle; trước tiên kiểm tra tính năng producer maxAge và nguyên nhân thực tế.

## 29. Kiểm thử Reason.FENCED

Kiểm thử nên tập trung vào hai thành phần: **fencing thực sự xảy ra** và **Spring Kafka container phát lifecycle event tương ứng**.

### Test 1: cấu hình event listener

1. Tạo Kafka listener container có KafkaTransactionManager.
2. Bật stopContainerWhenFenced=true.
3. Đăng ký @EventListener nhận ConsumerStoppedEvent.
4. Khi phát event reason FENCED, xác nhận observer ghi nhận incident đúng listener ID.
5. Xác nhận code không tự commit offset hoặc thao tác KafkaConsumer sau khi stop.

Unit test có thể giả lập ConsumerStoppedEvent để kiểm tra observer, nhưng không chứng minh producer thực tế bị fenced.

### Test 2: hai producers dùng cùng transactional.id

1. Dùng Kafka broker test như Testcontainers Kafka.
2. Tạo producer A với transactional.id cố định.
3. Bắt đầu transaction ở A.
4. Khởi tạo producer B với cùng transactional.id để fence A.
5. Cho A thực hiện thao tác transaction tiếp theo và quan sát lỗi fencing.
6. Với container được cấu hình phù hợp, kiểm tra ConsumerStoppedEvent.Reason.FENCED và trạng thái stopped.

Không để test dùng chính transactional ID production. Các lỗi fencing có thể xuất hiện ở bước send/commit tùy Kafka client, nên test cần chờ theo điều kiện và không phụ thuộc một điểm ném exception duy nhất.

### Test 3: không tự restart vô hạn

1. Giả lập nhiều sự kiện FENCED liên tiếp.
2. Kiểm tra restart coordinator giới hạn số lần thử và dùng backoff.
3. Kiểm tra alert được phát nếu xung đột cấu hình không giải quyết.
4. Xác nhận không có vòng lặp start/stop làm CPU và rebalance tăng vô hạn.

### Test 4: pending offsets và output

1. Listener nhận input record và gửi output trong Kafka transaction.
2. Gây fencing trước transaction commit.
3. Consumer downstream dùng read_committed để kiểm tra output chưa được commit không visible.
4. Khởi chạy consumer mới và xác nhận input chưa commit được đọc lại.
5. Kiểm tra idempotency nếu listener có thao tác database ngoài Kafka.

### Test 5: graceful shutdown so với FENCED

1. Dừng container bình thường.
2. Xác nhận ConsumerStoppedEvent có reason NORMAL.
3. Gây fencing thật với stopContainerWhenFenced=true.
4. Xác nhận reason FENCED, không phân loại chung thành NORMAL.
5. Kiểm tra metrics và alert phân biệt hai tình huống.

### Test 6: concurrency

1. Tạo concurrent listener container có nhiều child consumers.
2. Gây fencing ở một transactional producer mà child đang sử dụng.
3. Xác định child nào dừng và event source là container nào.
4. Xác nhận lifecycle manager không restart nhầm toàn bộ group hoặc lặp cùng child.
5. Kiểm tra partitions được redispatch và không mất dữ liệu.

Trong integration tests, dùng condition-based wait có timeout, đối chiếu group committed offsets và downstream read_committed. Không chỉ dựa vào log có chữ "fenced" rồi coi event/lifecycle đã chính xác.

## 30. Những hiểu nhầm thường gặp

**Reason.FENCED là tên exception của Kafka producer.** Không đúng. Nó là giá trị reason trong Spring Kafka ConsumerStoppedEvent; exception liên quan là ProducerFencedException hoặc lỗi transactional epoch tương ứng.

**Cứ ProducerFencedException là chắc chắn có event Reason.FENCED.** Không đúng. Phải xét stopContainerWhenFenced=true, event lifecycle và nơi exception phát sinh.

**FENCED nghĩa là record nghiệp vụ bị lỗi.** Không đúng. Fencing thuộc transaction identity/lifecycle; payload có thể hoàn toàn hợp lệ.

**Mọi rebalance đều dẫn tới Reason.FENCED.** Không đúng. Rebalance bình thường thường xử lý qua revoke/assign callbacks.

**Restart container ngay sẽ sửa mọi lỗi fencing.** Không đúng. Nếu transaction IDs vẫn trùng hoặc timeout chưa được xử lý, restart sẽ lặp lỗi.

**Có thể retry trên producer đã fenced.** Không đúng. Producer cũ không còn quyền thực hiện transaction và cần được thay thế theo lifecycle.

**AfterRollbackProcessor luôn được chạy khi producer fenced.** Không đúng. Không thể tự seek partitions khi ownership có thể đã mất; Spring Kafka có logic riêng cho fencing.

**FENCED đồng nghĩa FencedInstanceIdException.** Không đúng. Một trường hợp thuộc transactional producer identity, trường hợp kia thuộc static consumer group membership.

**Kafka transaction rollback cả SQL update.** Không đúng. Database hoặc API bên ngoài phải có transaction/idempotency riêng.

**Consumer dừng thì toàn bộ consumer group đã dừng.** Không nhất thiết. Concurrent container có nhiều child consumers và nhiều application replicas.

**Tăng transaction.timeout.ms vô hạn sẽ ngăn fencing.** Không đúng. Timeout chỉ là một nguyên nhân có thể; trùng transactional.id hoặc mất ownership vẫn có thể xảy ra.

**Có thể commit input offset thủ công sau fencing để tránh retry.** Không nên. Offset có thể tiến qua output chưa commit, làm mất dữ liệu nghiệp vụ.

## 31. Hướng dẫn triển khai và vận hành

Với ứng dụng Spring Kafka dùng Kafka transaction, nên thiết kế policy cho Reason.FENCED ngay khi xây dựng listener:

1. Bảo đảm transactional ProducerFactory dùng transactionIdPrefix hợp lệ và không xung đột giữa active instances.
2. Cấu hình KafkaTransactionManager và transactional listener container đúng producer factory.
3. Chọn stopContainerWhenFenced một cách tường minh, hiểu giá trị mặc định của phiên bản đang chạy.
4. Đăng ký ConsumerStoppedEvent listener để phân loại NORMAL, FENCED và các lý do khác.
5. Ghi nhận listener/child container ID, group ID, instance ID, transactional ID prefix và transaction failure context.
6. Không dùng ProducerFencedException như một lỗi business retry thông thường.
7. Không seek/commit partitions đã mất ownership trong đường recovery của producer fencing.
8. Xác minh transaction timeout, max.poll.interval.ms và producer cache lifecycle bằng metrics.
9. Thiết kế bounded restart policy với backoff, chống restart loop và alert nếu xung đột chưa được giải quyết.
10. Đảm bảo downstream dùng read_committed nếu cần bỏ qua aborted Kafka output.
11. Bảo vệ mọi side effect ngoài Kafka bằng event ID, idempotency hoặc transactional outbox.
12. Kiểm thử producer fencing thật, restart, transaction abort, offset recovery và consumer concurrency.

**Reason.FENCED** là một tín hiệu cho thấy transactional producer đã bị fencing nghiêm trọng đến mức Spring Kafka listener container được cấu hình phải dừng. Nó giúp ứng dụng phân biệt một lần dừng vì lỗi transaction với dừng bình thường. Xử lý đúng không phải là cố chạy tiếp producer cũ, mà là **khôi phục identity và ownership hợp lệ, để Kafka bảo toàn committed offsets/output, rồi restart container có kiểm soát**. Chính cách xử lý lifecycle này, kết hợp idempotency và giám sát, giúp consumer phục hồi mà không đánh đổi tính đúng đắn của dữ liệu.
