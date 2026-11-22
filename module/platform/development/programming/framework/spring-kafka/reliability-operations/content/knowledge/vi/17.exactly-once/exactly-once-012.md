# EOS và batch listener

## 1. EOS trong Spring Kafka có nghĩa là gì?

**Exactly-once semantics (EOS)** là một mục tiêu reliability quan trọng của Kafka khi ứng dụng vừa đọc record, vừa tạo record Kafka mới. Trong phạm vi Kafka, transaction có thể phối hợp **output records** với **consumer offsets** để bảo đảm phần output và vị trí đã tiêu thụ được commit hoặc abort như một đơn vị.

Khi ứng dụng dùng **batch listener**, một lần gọi listener nhận nhiều record. Nếu cả batch xử lý thành công, container có thể commit output Kafka và offset đầu vào trong cùng transaction. Nếu một record trong batch gây lỗi và exception được truyền ra ngoài listener, transaction có thể abort; những output thuộc transaction đó không được consumer read_committed nhìn thấy, và offset đầu vào chưa được commit bằng transaction lỗi.

Ví dụ:

~~~text
Topic: orders.created
          |
          v
Consumer poll -> [R0, R1, R2, R3]
          |
          v
Transactional batch listener
          |
          +-- transform R0 -> Output0
          +-- transform R1 -> Output1
          +-- transform R2 -> Output2
          +-- transform R3 -> Output3
          |
          v
Transaction:
    output Kafka + input offsets
          |
    +-----+------+
    |            |
  COMMIT       ABORT
    |            |
    v            v
 Output visible  Output not visible to read_committed
 Offset moves    Offset not committed by aborted transaction
~~~

Điểm cần hiểu ngay từ đầu: **EOS không có nghĩa mỗi dòng code trong listener chỉ chạy đúng một lần**. Khi transaction thất bại, listener có thể phải xử lý lại cả batch. EOS liên quan đến kết quả commit Kafka; side effect tới database, HTTP API, email hoặc hệ thống thanh toán vẫn cần idempotency hoặc cơ chế phối hợp riêng.

## 2. Batch listener là gì?

Spring Kafka hỗ trợ hai kiểu listener phổ biến:

- **Record listener:** phương thức được gọi cho từng record riêng.
- **Batch listener:** phương thức nhận danh sách record từ một lần poll hoặc từ cơ chế batch được container cấu hình.

Ví dụ batch listener:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "order-transformers",
    containerFactory = "transactionalBatchFactory"
)
public void process(
        List<ConsumerRecord<String, OrderCreated>> records) {

    for (ConsumerRecord<String, OrderCreated> record : records) {
        OrderValidated output = validator.validate(record.value());
        kafkaTemplate.send(
            "orders.validated",
            record.key(),
            output
        );
    }
}
~~~

Trong ví dụ, listener nhận danh sách record và tạo một output Kafka cho từng input. Để có EOS, điều kiện **không phải chỉ cần method nhận List**: listener container phải được cấu hình để bắt đầu Kafka transaction, KafkaTemplate phải tham gia transaction đang hoạt động và container phải đưa input offsets vào cùng transaction.

### 2.1. Một poll có thể có nhiều partition

Ví dụ:

~~~text
Index 0 -> partition 0, offset 20
Index 1 -> partition 0, offset 21
Index 2 -> partition 2, offset 40
Index 3 -> partition 2, offset 41
~~~

Một batch không nhất thiết chỉ chứa một partition. Offsets phải được quản lý riêng cho từng partition, không có một offset số học chung cho cả batch.

Nếu tất cả record trong ví dụ hoàn tất, transaction có thể chứa offset tiếp theo:

~~~text
partition 0 -> commit offset 22
partition 2 -> commit offset 42
~~~

**Offset được commit là vị trí đọc tiếp theo**, không phải offset của record cuối cùng đã xử lý. Kafka transaction dùng offset của từng partition và metadata consumer group để phối hợp commit đúng scope.

### 2.2. Batch size không cố định

**max.poll.records** đặt giới hạn trên số record trả về trong một poll, không bảo đảm mỗi lần nhận đúng số đó. Khi topic ít dữ liệu, poll có thể trả ít record. Khi producer phát nhiều dữ liệu, batch có thể lớn hơn trong giới hạn được cấu hình.

Nếu có nhiều consumer con do concurrency, mỗi consumer quản lý poll batch và transaction của chính nó; không có một transaction chung tự động bao phủ mọi consumer trong cùng group.

## 3. EOS bảo đảm điều gì, không bảo đảm điều gì?

| Phạm vi | Có thể được bảo vệ bởi Kafka EOS? | Ghi chú |
|---|---|---|
| Ghi nhiều record Kafka trong một transaction | Có | Commit hoặc abort theo transaction |
| Phối hợp output Kafka với offset input trong consume-transform-produce | Có | Container và producer phải được cấu hình đúng |
| Ẩn record thuộc aborted transaction với downstream | Có | Downstream dùng read_committed |
| Ngăn producer retry tạo duplicate output trong phạm vi idempotence | Có theo semantics Kafka | Idempotent producer là nền tảng của transaction |
| Ngăn listener method bị gọi lại | Không | Rollback hoặc crash có thể khiến record được giao lại |
| Atomic commit giữa Kafka và database | Không tự động | Kafka transaction không phải XA transaction DB |
| Atomic commit giữa Kafka và HTTP API | Không | API có lifecycle riêng |
| Ngăn email hoặc thanh toán được thực hiện hai lần | Không | Cần idempotency key hoặc outbox/inbox |
| Đảm bảo nhiều downstream service cùng hoàn tất tức thời | Không | Mỗi service có poll/processing schedule riêng |

Một cách nói chính xác hơn là: **EOS của Kafka có thể tạo kết quả exactly-once cho chuỗi đọc Kafka → tính toán → ghi Kafka**, khi việc commit output và offset input được kết hợp trong cùng transaction và downstream đọc read_committed. Nó không xóa nhu cầu thiết kế reliability ở ranh giới bên ngoài Kafka.

## 4. Những thành phần tham gia Kafka transaction

| Thành phần | Vai trò |
|---|---|
| KafkaConsumer | Đọc input records và tham gia consumer group |
| Transactional KafkaProducer | Ghi output records trong transaction |
| KafkaTemplate | Giao diện Spring để gửi output Kafka |
| ProducerFactory | Tạo transactional producer có transactional.id |
| KafkaTransactionManager hoặc Kafka-aware transaction infrastructure | Điều phối transaction cho producer/container |
| Kafka listener container | Bắt đầu transaction, gọi batch listener và đưa offsets vào transaction |
| Transaction coordinator | Quản lý trạng thái commit/abort trên broker |
| Downstream consumer read_committed | Chỉ giao record transactional đã commit |

**KafkaTemplate.send()** được gọi trong listener không tự động tạo EOS. Nếu không có active Kafka transaction hoặc dùng nhầm ProducerFactory, output có thể không được phối hợp với input offsets.

Đối với consume-transform-produce, **listener container** phải là thành phần chủ động bắt đầu transaction trước khi gọi listener và hoàn tất transaction sau khi xử lý kết thúc.

## 5. Producer transaction và transactional.id

Transactional producer cần **transactional.id** để Kafka quản lý producer identity, epoch và fencing. Spring Kafka thường dùng **transaction ID prefix** rồi tạo các transactional IDs khác nhau cho producer do factory quản lý.

Ví dụ:

~~~text
transaction-id-prefix: orders-transformer-pod-a-tx-

Producer transaction IDs:
    orders-transformer-pod-a-tx-0
    orders-transformer-pod-a-tx-1
    orders-transformer-pod-a-tx-2
~~~

Khi hai producer đang chạy dùng cùng transactional.id, producer mới có thể khiến producer cũ bị **fenced**. Vì vậy, ứng dụng nhiều pod nên có prefix hoặc instance namespace riêng để tránh xung đột giữa các producer đồng thời.

**ProducerFencedException** không phải một exception nên retry vô hạn trên cùng producer đã bị fence. Khi gặp lỗi này, cần kiểm tra instance identity, transaction prefix và producer lifecycle.

### 5.1. Vì sao transactional.id cần ổn định theo instance?

Một transaction ID không nên tạo mới trên từng event: như vậy producer management và khả năng quan sát trở nên phức tạp. Nhưng cũng không nên dùng một ID cố định chung cho mọi pod đang chạy.

Một quy ước thực tế:

~~~text
<application>-<environment>-<instance>-tx-
~~~

Ví dụ:

~~~text
order-transformer-prod-pod-17-tx-
~~~

Cấu hình deployment phải bảo đảm instance ID thật sự khác nhau giữa các pod đang hoạt động, đặc biệt trong rolling update.

## 6. Cấu hình Spring Boot cho EOS với batch listener

Một cấu hình nền tảng:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    consumer:
      group-id: order-transformers
      enable-auto-commit: false
      isolation-level: read_committed
      max-poll-records: 100

    producer:
      transaction-id-prefix: order-transformer-pod-a-tx-
      acks: all
      properties:
        "[enable.idempotence]": true

    listener:
      type: batch
      ack-mode: batch
      concurrency: 2
~~~

Ý nghĩa các thiết lập:

- **enable-auto-commit=false**: offset không bị Kafka client tự commit độc lập với kết quả xử lý của listener.
- **isolation-level=read_committed**: consumer đầu vào không đọc những record Kafka đã bị abort từ upstream transactional producers.
- **transaction-id-prefix**: tạo nền tảng cho transactional ProducerFactory.
- **acks=all** và idempotence: hỗ trợ ghi producer đáng tin cậy; transaction cần producer có cấu hình tương thích.
- **listener.type=batch**: listener nhận nhiều record trong một lần gọi.
- **ack-mode=batch**: mô tả chính sách container với poll batch; **không phải cờ tự tạo EOS**.
- **concurrency=2**: tạo khả năng xử lý song song giữa các consumer con trên partition khác nhau.

Đây là ví dụ cấu hình đơn giản cho một instance development. Trong production, không được dùng cố định cùng transaction-id-prefix trên mọi replica nếu nó dẫn đến transactional IDs trùng.

### 6.1. Transaction Manager không tự suy ra từ ack-mode

Bật **ack-mode=batch** và **listener.type=batch** không đủ để container có Kafka transaction. Cần bảo đảm listener container factory thực sự được cấu hình với Kafka-aware transaction manager hoặc cơ chế transaction tương ứng của Spring Kafka version đang dùng.

Spring Boot có thể auto-configure KafkaTransactionManager khi producer transaction prefix được khai báo và những điều kiện khác thỏa mãn. Tuy nhiên, một **custom listener factory** có thể không thừa hưởng đầy đủ cấu hình này nếu ứng dụng tạo factory riêng mà không dùng Boot configurer.

Do đó, khi xây dựng EOS cần xác định factory thực tế của @KafkaListener, ProducerFactory, transaction manager và KafkaTemplate tham gia transaction nào.

## 7. Ví dụ cấu hình listener factory bằng Java

Trong các phiên bản Spring Kafka hiện đại có API Kafka-aware transaction manager trên container properties, có thể cấu hình tương tự:

~~~java
@Configuration
public class KafkaBatchConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            transactionalBatchFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory,
                    KafkaTransactionManager<String, OrderValidated>
                        kafkaTransactionManager) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);

        factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTransactionManager);

        return factory;
    }
}
~~~

Ví dụ trên giả định KafkaTransactionManager được tạo từ transactional ProducerFactory và KafkaTemplate gửi output dùng producer factory tương thích.

**Lưu ý phiên bản:** API gắn transaction manager vào container properties thay đổi giữa các dòng Spring Kafka. Một số version sử dụng phương thức **setTransactionManager**, trong khi version mới sử dụng **setKafkaAwareTransactionManager**. Cần dùng API của dependency thực tế.

Không nên tạo KafkaTransactionManager và ProducerFactory thứ hai một cách tùy tiện: nếu KafkaTemplate dùng ProducerFactory khác với cái được transaction manager quản lý, output có thể không tham gia transaction như dự định.

### 7.1. Mối quan hệ KafkaTemplate và producer factory

Ví dụ khai báo template dùng cùng producer factory:

~~~java
@Bean
public KafkaTemplate<String, OrderValidated> kafkaTemplate(
        ProducerFactory<String, OrderValidated> producerFactory) {

    return new KafkaTemplate<>(producerFactory);
}
~~~

Với ứng dụng Spring Boot đơn giản, auto-configured KafkaTemplate thường đủ. Trong hệ thống có nhiều producer factories cho nhiều event type, cần ghi rõ bean nào tham gia transaction nào.

## 8. Viết transactional batch listener

Một ví dụ service chỉ làm công việc Kafka-to-Kafka:

~~~java
@Service
public class OrderValidationListener {

    private final KafkaTemplate<String, OrderValidated> kafkaTemplate;
    private final OrderValidator validator;

    public OrderValidationListener(
            KafkaTemplate<String, OrderValidated> kafkaTemplate,
            OrderValidator validator) {

        this.kafkaTemplate = kafkaTemplate;
        this.validator = validator;
    }

    @KafkaListener(
        topics = "orders.created",
        groupId = "order-transformers",
        containerFactory = "transactionalBatchFactory"
    )
    public void process(
            List<ConsumerRecord<String, OrderCreated>> records) {

        for (ConsumerRecord<String, OrderCreated> record : records) {
            OrderValidated output =
                validator.validate(record.value());

            kafkaTemplate.send(
                "orders.validated",
                record.key(),
                output
            ).join();
        }
    }
}
~~~

Giả định:

1. Batch listener factory thực sự mở một Kafka transaction trước khi gọi listener.
2. KafkaTemplate tham gia transaction đó.
3. Các producer sends dùng serializer tương thích với OrderValidated.
4. Listener không ghi side effect ngoài Kafka cần atomicity.
5. Downstream consumer dùng read_committed.
6. Exception không bị nuốt rồi coi xử lý thành công.

**join()** ở đây làm send failure xuất hiện trong scope listener. Nếu send future lỗi, exception truyền ra ngoài và container có cơ hội abort transaction. Nếu code chỉ log lỗi bất đồng bộ nhưng trả về thành công, transaction boundary có thể kết thúc không phù hợp với kỳ vọng nghiệp vụ.

### 8.1. Có cần @Transactional trên listener?

Trong mô hình container-managed Kafka transaction, không cần tự mở một Kafka transaction khác trong listener bằng @Transactional. Container quản lý transaction và consumer offsets.

Chỉ thêm @Transactional không thay thế việc cấu hình transactional container. Ngược lại, thêm @Transactional với một transaction manager khác có thể tạo sự phức tạp không cần thiết về transaction boundary.

Một nguyên tắc thực hành: **chọn một nơi làm chủ Kafka transaction boundary**, thường là listener container đối với consume-transform-produce.

## 9. Luồng thành công: output và offsets cùng commit

Giả sử poll trả về bốn record thuộc hai partition:

~~~text
Input:
    P0 offset 8
    P0 offset 9
    P1 offset 20
    P1 offset 21
~~~

Listener tạo bốn record output rồi kết thúc bình thường.

Container có thể gửi offsets sau xử lý vào transaction:

~~~text
Output topic orders.validated:
    V0, V1, V2, V3

Input offset commit:
    P0 -> 10
    P1 -> 22
~~~

Sau đó container yêu cầu commit Kafka transaction:

~~~text
Transaction T1
    |
    +-- output V0..V3
    +-- offset P0=10
    +-- offset P1=22
    |
    v
COMMIT
~~~

Khi transaction commit thành công:

- Downstream read_committed có thể nhận V0..V3.
- Consumer group input có thể tiếp tục từ offsets 10 và 22.
- Nếu consumer restart, nó không cần đọc lại những record này theo offsets được transaction commit, trừ các tình huống replay chủ động hoặc thay đổi group/offset.

Đây là mối liên hệ cốt lõi giữa EOS và batch listener: **tất cả output Kafka và tiến độ input của batch được commit theo một quyết định Kafka transaction**.

## 10. Luồng thất bại: rollback toàn batch

Giả sử listener xử lý:

~~~text
R0 -> phát V0 thành công
R1 -> phát V1 thành công
R2 -> validator ném exception
R3 -> chưa xử lý
~~~

Nếu exception được truyền tới container, transaction có thể abort:

~~~text
Transaction T1
    |
    +-- V0
    +-- V1
    +-- exception tại R2
    |
    v
ABORT
    |
    +-- V0, V1 không hiện với read_committed consumer
    +-- input offsets không commit trong T1
    |
    v
Recovery / redelivery theo transactional container
~~~

Nếu batch được giao lại, listener có thể chạy lại R0 và R1, tạo các output mới ở transaction T2. Khi T2 commit, downstream read_committed thấy output từ transaction thành công mà không thấy V0/V1 của transaction abort.

Đây là lý do EOS không đồng nghĩa **listener chỉ xử lý mỗi record đúng một lần trong RAM**.

### 10.1. Vì sao không nên nuốt exception?

Ví dụ nguy hiểm:

~~~java
for (var record : records) {
    try {
        process(record);
    }
    catch (RuntimeException ex) {
        log.error("Cannot process record", ex);
        // Nuốt lỗi và tiếp tục.
    }
}
~~~

Nếu listener kết thúc bình thường, container có thể xem batch đã hoàn thành và commit offsets, kể cả khi một record chưa tạo output hợp lệ.

Nếu nghiệp vụ cho phép bỏ qua record, cần thực hiện recovery hoặc chuyển DLT **theo một policy rõ ràng** rồi mới cho phép tiến offset. Log lỗi không phải là bằng chứng recovery thành công.

## 11. Một batch chứa nhiều partition: hệ quả của rollback

Một poll có thể chứa record từ nhiều partition của cùng consumer:

~~~text
Batch:
  index 0 -> P0/10
  index 1 -> P1/40
  index 2 -> P0/11   (lỗi)
  index 3 -> P1/41
~~~

Nếu transaction cho batch abort, những output của transaction và những offsets chưa commit trong transaction đều bị ảnh hưởng.

Ngay cả record P1/40 đã xử lý thành công cũng có thể được giao lại khi batch được xử lý lại, tùy vị trí offset đã committed trước đó và recovery behavior. Transaction không cung cấp một cơ chế tự động “partial commit Kafka transaction cho vài record trong cùng transaction”.

Muốn cách ly lỗi, phải dùng error/recovery strategy có semantics rõ ràng; không thể tự chọn commit một phần của transaction đã abort.

### 11.1. Tại sao concurrency không giải quyết mọi vấn đề?

Nếu tăng concurrency, các consumer con có thể xử lý các partition khác nhau trên những transaction khác nhau. Điều này giảm mức ảnh hưởng giữa các consumer, nhưng một consumer vẫn có thể nhận nhiều partition trong cùng poll.

Tăng concurrency vượt số partition có ích không tạo thêm song song. Quan sát assignment và hot partitions trước khi scale.

## 12. DefaultErrorHandler và AfterRollbackProcessor

Đây là khác biệt quan trọng giữa xử lý lỗi thường và xử lý lỗi trong transaction.

**Non-transactional listener:** Spring Kafka thường dùng **DefaultErrorHandler** để retry, seek, recover và có thể phối hợp commit phần record đã hoàn tất.

**Transactional listener:** exception thường khiến Kafka transaction rollback. Sau rollback, container sử dụng cơ chế **AfterRollbackProcessor** để xác định cách seek, redeliver hoặc recover, tùy version và cấu hình.

~~~text
Non-transactional batch listener
       |
       v
DefaultErrorHandler
       |
       +-- retry/seek/recover theo policy

Transactional batch listener
       |
       v
Exception -> Kafka transaction ABORT
       |
       v
AfterRollbackProcessor
       |
       +-- seek/redeliver/recover theo cấu hình
~~~

Không áp dụng nguyên xi ví dụ DefaultErrorHandler non-transactional vào transactional listener mà không kiểm tra chính sách rollback. Nếu dùng sai handler hoặc nhầm transaction boundary, ứng dụng có thể hiểu sai offset được commit và record sẽ được giao lại.

### 12.1. Batch rollback và record-level recovery

Với batch listener, một exception chung không cho container biết record nào thất bại. Vì vậy **cả batch có thể được xử lý lại**.

**BatchListenerFailedException** cung cấp index record lỗi và thường được dùng cùng DefaultErrorHandler trong non-transactional batch handling. Tuy nhiên, khả năng recover từng record của transactional batch listener phụ thuộc version Spring Kafka và AfterRollbackProcessor; không nên giả định cứ ném BatchListenerFailedException thì transactional container sẽ commit phần trước lỗi giống non-transactional mode.

Khi business cần partial recovery của batch transactional, hãy kiểm tra JavaDoc/reference của version chạy thực tế và viết integration test với record lỗi đầu/giữa/cuối batch.

### 12.2. Tại sao batch retry cần idempotency?

Ngay cả khi Kafka output của transaction abort không nhìn thấy được với read_committed, listener có thể đã:

- Ghi database.
- Gọi REST API.
- Gửi email.
- Thay đổi cache bên ngoài.
- Gửi metric, log hoặc audit ngoại hệ thống.

Các side effect này không được Kafka rollback. Khi batch được giao lại, chúng có thể lặp. Vì vậy, thiết kế EOS luôn phải nói rõ **phạm vi transaction** và điểm nào là side effect ngoài Kafka.

## 13. BatchListenerFailedException có thay được Kafka transaction không?

Không. **BatchListenerFailedException** là thông tin lỗi, không phải transaction manager.

Nó hữu ích khi biết một record thất bại và cần báo vị trí trong batch:

~~~java
for (int index = 0; index < records.size(); index++) {
    try {
        process(records.get(index));
    }
    catch (RuntimeException ex) {
        throw new BatchListenerFailedException(
            "Record failed",
            ex,
            index
        );
    }
}
~~~

Với non-transactional batch listener và error handler phù hợp, failed index có thể giúp xử lý phần thành công trước lỗi và redeliver phần lỗi.

Với transactional batch listener, exception vẫn làm transaction đang hoạt động abort theo semantics. Không thể coi các output của record trước failed index là committed nếu chúng thuộc transaction đã abort. Cần xác nhận AfterRollbackProcessor/recovery mode hỗ trợ đến đâu trong phiên bản cụ thể.

## 14. DLT trong transactional pipeline

Dead-letter topic (DLT) là nơi lưu các record không thể xử lý để không chặn luồng chính mãi.

Khi một batch gặp poison record:

1. Container rollback transaction chứa output của batch lỗi.
2. Retry/redelivery xảy ra theo AfterRollbackProcessor.
3. Khi policy cho phép recovery, record lỗi có thể được gửi sang DLT.
4. Luồng chính chỉ nên tiến offset khi recovery đã thành công theo policy.
5. Các record còn lại tiếp tục được xử lý theo semantics của container.

### 14.1. DLT và offset input cần phối hợp an toàn

Một rủi ro lớn:

~~~text
Poison record tại input offset 90
         |
         v
DLT publish thất bại
         |
         v
Input offset vẫn commit 91
         |
         v
Record lỗi bị bỏ qua mà chưa lưu được DLT
~~~

Với transactional pipeline, cần thiết kế cách phối hợp recovery output và input offset. Tùy version và cấu hình, AfterRollbackProcessor có thể hỗ trợ xử lý recovery trong một Kafka transaction mới để record DLT và offset input được commit an toàn.

Không nên giả định một KafkaTemplate gửi DLT ngoài transaction tự động bảo đảm atomicity với input offset. Hãy kiểm tra cấu hình cụ thể và thử tình huống DLT broker/serializer/ACL lỗi.

### 14.2. Những điều kiện vận hành DLT

- DLT topic đã tồn tại và có partition mapping phù hợp.
- Recoverer dùng producer với serializer cho key/value tương ứng.
- Principal có quyền WRITE trên DLT.
- Có log/metrics cho recovery success hoặc failure.
- Payload nhạy cảm được bảo vệ bằng ACL, retention và encryption.
- Có quy trình triage và replay record từ DLT.
- Replay phải idempotent hoặc có cơ chế deduplication.

DLT không phải một thành công nghiệp vụ; nó là recovery state cần theo dõi và xử lý tiếp.

## 15. EOS không có nghĩa mỗi record chỉ chạy một lần

Cần phân biệt ba lớp:

| Lớp | Sự kiện có thể lặp? |
|---|---|
| Listener Java method được gọi | Có, sau rollback, rebalance hoặc restart |
| Kafka transactional output được read_committed downstream nhận | Output abort không được giao; output committed tuân theo EOS trong scope Kafka |
| Side effect DB/HTTP/email từ listener | Có thể lặp nếu không có idempotency |

Ví dụ:

~~~text
Batch T1:
  R0 -> DB update thành công
  R1 -> HTTP request thành công
  R2 -> lỗi, Kafka transaction ABORT

Retry batch T2:
  R0 -> DB update lần thứ hai
  R1 -> HTTP request lần thứ hai
  R2 -> lần này thành công
  Kafka transaction COMMIT
~~~

Kafka sẽ bảo vệ output Kafka, nhưng không rollback DB update hoặc HTTP request ở T1. Để toàn hệ thống có kết quả nghiệp vụ đúng, cần idempotency hoặc một kiến trúc chuyên biệt.

## 16. Kết hợp database bằng outbox/inbox

Nếu một batch listener vừa ghi DB vừa phát Kafka, không nên mặc định Kafka transaction bao phủ thay đổi DB.

Một thiết kế thường gặp là **transactional outbox** khi database là nguồn sự thật:

~~~text
Consumer nhận OrderCreated
         |
         v
DB transaction:
   +-- cập nhật order state
   +-- ghi outbox event
         |
         v
      DB COMMIT
         |
         v
Outbox publisher
         |
         v
Kafka producer gửi output
~~~

Outbox đảm bảo cập nhật DB và ý định phát event được lưu cùng một DB transaction. Tuy nhiên, publisher có thể gửi lại cùng event sau crash, nên downstream cần idempotency.

**Inbox pattern** giúp consumer nhận diện event đã xử lý bằng một event ID ổn định và unique constraint trong DB:

~~~sql
CREATE TABLE processed_event (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Khi retry batch, nếu event ID đã được ghi thành công trong cùng DB transaction với business side effect, consumer có thể bỏ qua duplicate một cách an toàn.

Không chỉ dựa vào thao tác kiểm tra **existsById** trước insert, vì hai consumer hoặc hai luồng xử lý có thể gặp race condition. Unique constraint ở DB là lớp bảo vệ quan trọng.

## 17. Kafka transaction không phải XA transaction

Một code mẫu dễ gây hiểu nhầm:

~~~java
@Transactional
public void processOrder(OrderCreated event) {
    orderRepository.save(...);
    kafkaTemplate.send("orders.validated", ...);
}
~~~

Nếu @Transactional dùng JpaTransactionManager, nó có thể bao DB transaction chứ không phải Kafka transaction. Nếu dùng KafkaTransactionManager, DB vẫn không tự nằm trong cùng một atomic transaction.

Spring transaction synchronization có thể phối hợp thứ tự commit giữa DB và Kafka trong một số cấu hình, nhưng vẫn tồn tại failure window:

~~~text
DB COMMIT thành công
        |
        v
Kafka COMMIT thất bại
        |
        v
Business state đã đổi
nhưng output Kafka chưa committed
~~~

Vì vậy, với workflow yêu cầu nhất quán giữa DB và Kafka, cần đánh giá outbox, inbox, idempotent process hoặc saga/compensation. **EOS Kafka không thay thế thiết kế consistency giữa nhiều hệ thống**.

## 18. read_committed và aborted records

Để downstream không xử lý output của transaction abort, hãy cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      isolation-level: read_committed
~~~

Nếu dùng read_uncommitted, consumer có thể thấy record transactional chưa được commit hoặc đã abort, làm mất ý nghĩa của transaction đối với downstream processing.

### 18.1. Last Stable Offset

Consumer read_committed có thể bị giới hạn bởi **Last Stable Offset (LSO)** khi có transaction mở chưa được giải quyết. Điều này có nghĩa record phía sau một open transaction chưa chắc đã được giao, ngay cả khi broker đã lưu nhiều record hơn.

Một transaction mở quá lâu có thể khiến read_committed consumer lag tăng. Khi chẩn đoán consumer chậm, cần kiểm tra cả transaction duration, transaction coordinator và LSO.

## 19. Batch size, max.poll.interval.ms và transaction timeout

Một batch lớn cần thời gian xử lý dài hơn. Khi container giữ một Kafka transaction trong suốt thời gian gọi listener, batch processing time ảnh hưởng cả consumer liveness lẫn transaction lifetime.

Các giới hạn quan trọng:

| Cấu hình | Ảnh hưởng |
|---|---|
| max.poll.records | Số record tối đa trả về mỗi poll |
| max.poll.interval.ms | Khoảng thời gian tối đa giữa các poll hợp lệ |
| transaction.timeout.ms | Giới hạn thời gian transaction phía producer/broker |
| delivery.timeout.ms | Giới hạn tổng thời gian producer delivery |
| request.timeout.ms | Giới hạn chờ request/response |
| concurrency | Số consumer con xử lý song song theo partition |
| max.partition.fetch.bytes | Giới hạn fetch bytes liên quan tới partition |

Nếu xử lý batch quá lâu, có thể:

- Transaction timeout và bị abort.
- Consumer vượt poll interval, rời group hoặc gây rebalance.
- Các record phía sau bị chặn bởi open transaction.
- Kafka transaction coordinator và producer cache chịu thêm tải.
- Retry làm batch processing time tăng hơn nữa.

### 19.1. Ví dụ thời gian xử lý

Giả sử mỗi record cần 20 ms để transform:

~~~text
100 records x 20 ms = 2.000 ms = 2 giây
500 records x 20 ms = 10.000 ms = 10 giây
~~~

Nếu một batch còn gọi downstream trong 15 giây hoặc retry ba lần, thời gian transaction có thể tăng vượt dự kiến. Cần đo p95/p99 chứ không chỉ thời gian trung bình.

Đừng tăng transaction timeout hoặc max.poll.interval.ms vô hạn để che downstream bị nghẽn. Hãy đặt timeout cho I/O, giới hạn batch size, backoff phù hợp và giảm thao tác ngoài Kafka trong transaction.

### 19.2. Có nên dùng batch listener với EOS?

Batch listener vẫn phù hợp khi có thể giảm overhead xử lý hoặc bulk-transform nhiều record một cách hiệu quả. Nhưng nếu batch dài, chứa side effect khó idempotent hoặc poison record thường xuyên, record listener đôi khi dễ vận hành hơn.

Không có quy tắc “EOS bắt buộc batch listener” hoặc “batch listener không dùng EOS”. Cần chọn dựa trên throughput, transaction duration, fault isolation và yêu cầu ordering.

## 20. Concurrency và phân phối transaction

Giả sử topic orders.created có 12 partition, ứng dụng chạy hai pod, mỗi pod concurrency=3:

~~~text
Pod A:
  consumer A1 -> batch / transaction riêng
  consumer A2 -> batch / transaction riêng
  consumer A3 -> batch / transaction riêng

Pod B:
  consumer B1 -> batch / transaction riêng
  consumer B2 -> batch / transaction riêng
  consumer B3 -> batch / transaction riêng

Tổng 6 consumer chia 12 partition
~~~

Mỗi consumer có poll loop và transaction boundary riêng; không tồn tại một Kafka transaction duy nhất bao phủ mọi pod.

Nếu một consumer xử lý batch lỗi và transaction abort, các consumer khác có thể vẫn xử lý những partition được gán cho chúng. Tuy nhiên, rebalance hoặc broker failure vẫn có thể ảnh hưởng nhiều consumer cùng group.

Khi scale:

- Tính tổng consumer = replicas × concurrency.
- So sánh với số partition hữu ích.
- Đảm bảo producer transactional IDs không trùng.
- Kiểm tra producer cache và khả năng transaction coordinator.
- Đo consumer lag theo partition và transaction commit latency.
- Tránh tăng concurrency vượt downstream capacity.

## 21. Ordering trong EOS batch

Kafka giữ thứ tự theo partition. Batch có record từ nhiều partition nên không có một thứ tự toàn cục đáng tin cậy giữa tất cả record trong batch.

Nếu event cùng orderId cần được xử lý theo thứ tự:

1. Producer dùng key ổn định, thường là orderId.
2. Partitioner đưa các event liên quan vào cùng partition.
3. Consumer xử lý thứ tự record trên partition phù hợp.
4. Tránh dùng executor song song làm đảo thứ tự side effect nếu nghiệp vụ yêu cầu ordering.
5. Khi retry/rollback, cân nhắc record phía sau không được vượt qua record lỗi một cách không kiểm soát.

EOS không tự sửa lỗi ordering do ứng dụng xử lý bất đồng bộ. Kafka transaction giúp output/offset commit nhưng không tạo một hàng đợi tuần tự toàn hệ thống qua nhiều partition.

## 22. Error handling: retry, poison record và backoff

Một batch có thể thất bại do:

- Lỗi transient: DB timeout, HTTP 503, broker/network chập chờn.
- Lỗi deterministic: JSON/schema mismatch, validation không hợp lệ.
- Lỗi producer: serializer không tạo được bytes, thiếu ACL, transaction timeout.
- Lỗi môi trường: producer fenced, coordinator unavailable.
- Lỗi business: vi phạm invariant nghiệp vụ.

Hướng xử lý cần phân loại lỗi:

| Loại lỗi | Chiến lược |
|---|---|
| Transient dependency failure | Retry có giới hạn, backoff phù hợp |
| Invalid payload/schema | Recovery/DLT, không retry vô hạn |
| ProducerFencedException | Tạo producer hợp lệ, kiểm tra transactional ID collision |
| Transaction timeout | Giảm thời gian transaction hoặc điều chỉnh policy |
| DLT publish failure | Không coi recovery thành công khi chưa xác nhận |
| Business invariant failure | Policy nghiệp vụ, có thể DLT hoặc xử lý thủ công |

Với transactional listener, hãy cấu hình **AfterRollbackProcessor** và recovery policy phù hợp với version. Không dùng DefaultErrorHandler non-transactional như một lời giải mặc định cho mọi lỗi.

### 22.1. Poison record và blocking transaction

Một poison record có thể làm batch rollback liên tục, khiến nhiều record hợp lệ cũng bị xử lý lại. Hãy giới hạn retry, có DLT và cảnh báo backlog. Không để một record lỗi giữ partition bị kẹt vô hạn nếu chính sách nghiệp vụ cho phép cô lập nó.

## 23. Tác động tới metrics và observability

Không đủ nếu chỉ quan sát send success. Cần phân biệt **batch invocation**, **Kafka transaction outcome** và **business side effect outcome**.

| Metric/tín hiệu | Ý nghĩa |
|---|---|
| Transaction commit rate | Số Kafka transaction commit theo thời gian |
| Transaction abort rate | Số transaction rollback/abort |
| Transaction duration p95/p99 | Thời gian mở transaction, phát hiện transaction dài |
| Batch size | Phân bố số record mỗi poll/listener invocation |
| Batch processing time | Thời gian xử lý batch |
| Consumer lag by partition | Partition nào chậm hoặc bị poison record |
| Rebalance count | Group có bị mất ổn định do xử lý chậm không |
| Producer fencing errors | Có transactional ID collision không |
| Producer send failure | Serializer, network, ACL hoặc broker lỗi |
| AfterRollbackProcessor recovery | Retry/recover có thành công không |
| DLT ingress/failure | Record lỗi được cô lập an toàn không |
| read_committed lag / LSO | Open transaction có đang trì hoãn downstream không |
| Duplicate external side effects | Idempotency có đang ngăn lặp DB/HTTP không |

Tên metric phụ thuộc Kafka client, Spring Kafka, Micrometer, JMX exporter và instrumentation hiện có. Một số chỉ số như “business side effect đã hoàn tất” phải được ghi nhận ở ứng dụng.

### 23.1. Structured log

Ví dụ:

~~~text
listener=orders-batch
groupId=order-transformers
topic=orders.created
batchSize=74
transactionOutcome=aborted
exceptionClass=InvalidOrderException
transactionDurationMs=950
action=rollback
~~~

Không dùng event ID, order ID hay transactional ID tạo động làm metric labels với cardinality cao. Những ID này phù hợp hơn với log/trace có kiểm soát.

### 23.2. Phân biệt send acknowledged và transaction committed

Khi KafkaTemplate.send future hoàn tất thành công, broker đã xác nhận ghi record theo producer delivery configuration, nhưng transaction vẫn có thể abort sau đó. Nếu dashboard chỉ đếm send success, nó có thể báo quá nhiều “event thành công”.

Hãy instrument transaction commit/abort ở boundary thích hợp và xem read_committed downstream để xác nhận output đã committed.

## 24. Kịch bản kiểm thử EOS với batch listener

Một integration test tốt nên dùng Embedded Kafka hoặc Testcontainers có broker hỗ trợ Kafka transactions.

### 24.1. Test batch thành công

1. Cấu hình transactional ProducerFactory, KafkaTemplate, batch listener container.
2. Gửi bốn input record tới topic.
3. Listener transform và gửi bốn output.
4. Đợi transaction commit.
5. Consumer read_committed đọc output.
6. Xác nhận output tương ứng được committed.
7. Xác nhận input group offsets tiến sau batch.

### 24.2. Test batch thất bại ở giữa

1. Gửi batch có R0, R1, R2, R3.
2. Cho R2 ném exception.
3. Xác nhận transaction abort.
4. Consumer read_committed không nhận output của transaction abort.
5. Xác nhận input offsets chưa được commit bởi transaction thất bại.
6. Xác nhận retry/redelivery theo AfterRollbackProcessor thực tế.
7. Sau khi loại bỏ lỗi, xác nhận output transaction thành công và offset tiến.
8. Đối chiếu số lần listener method chạy với số output committed; chúng có thể khác nhau.

### 24.3. Test crash và restart

- Crash process sau khi KafkaTemplate gửi output nhưng trước transaction commit.
- Restart consumer group với transactional ID policy phù hợp.
- Xác nhận aborted transaction không tạo output đọc được với read_committed.
- Xác nhận record input được xử lý lại nếu offset chưa commit.
- Xác nhận transaction mới có thể hoàn tất.

### 24.4. Test side effect ngoài Kafka

- Listener ghi DB trước khi Kafka transaction commit.
- Chủ động gây rollback Kafka.
- Xác nhận DB side effect có thể còn tồn tại nếu transaction DB đã commit.
- Chứng minh inbox/idempotency ngăn việc replay tạo side effect thứ hai.

### 24.5. Test DLT và recovery failure

- Gửi poison record không thể xử lý.
- Giới hạn retry và kích hoạt recovery.
- Xác nhận DLT publish thành công trước khi cho phép tiến offset theo policy.
- Gây lỗi serializer/ACL của DLT publisher.
- Kiểm tra record không bị “mất im lặng” khi recovery thất bại.

## 25. Ví dụ tổng hợp: Batch Order Validation

Giả sử Order Validation service đọc **orders.created**, xác thực schema và nghiệp vụ, rồi gửi **orders.validated**. Đây là một Kafka-to-Kafka pipeline không ghi DB.

Một batch gồm:

~~~text
R0: order-100 -> valid
R1: order-101 -> valid
R2: order-102 -> valid
R3: order-103 -> valid
~~~

Listener transform bốn event và gửi bốn output trong transaction do container quản lý. Sau khi method hoàn tất, container đưa input offsets vào transaction rồi commit.

Nếu batch có một event không hợp lệ:

~~~text
R0: order-100 -> valid
R1: order-101 -> valid
R2: order-102 -> invalid
R3: order-103 -> not reached
~~~

Listener ném exception và transaction abort. Các output Kafka của R0/R1 thuộc transaction abort không được read_committed downstream nhận. Sau đó AfterRollbackProcessor quyết định redelivery/recovery.

Nếu sau một lần retry code đã sửa hoặc payload hợp lệ trong điều kiện mới, transaction kế tiếp có thể commit output. Nếu record luôn invalid, error policy cần tránh retry vô hạn và xử lý DLT có kiểm soát.

Điểm quan trọng của ví dụ:

- **EOS Kafka:** output Kafka và input offsets được commit atomically trong transaction thành công.
- **Batch rollback:** có thể phải gọi lại listener cho record trước lỗi.
- **Read committed:** downstream không đọc output từ transaction abort.
- **DLT:** phải có policy để cô lập poison record mà không commit nhầm.
- **External side effects:** nếu bổ sung DB/HTTP vào listener, cần idempotency hoặc outbox/inbox.

## 26. Runbook khi EOS batch listener gặp sự cố

1. Xác định listener ID, consumer group, topic và partition có lag.
2. Kiểm tra listener container có Kafka transaction manager thực sự không.
3. Xác nhận KafkaTemplate dùng transactional ProducerFactory tham gia transaction đó.
4. Kiểm tra producer transaction ID prefix và instance uniqueness.
5. Xem transaction commit/abort count và transaction duration.
6. Xác định exception gốc: business, serializer, network, ACL hay fencing.
7. Kiểm tra AfterRollbackProcessor, retry policy và redelivery behavior.
8. Nếu poison record, kiểm tra DLT và policy recovery có bảo toàn dữ liệu không.
9. Kiểm tra input offsets có tiến chỉ sau commit hợp lệ không.
10. Xác nhận downstream dùng read_committed.
11. Kiểm tra LSO/open transactions nếu downstream lag bất thường.
12. Nếu có DB/HTTP side effect, kiểm tra duplicate detection và idempotency.
13. Đánh giá max.poll.records, max.poll.interval.ms và transaction.timeout.ms.
14. Test lại commit/abort sau khi thay đổi cấu hình.
15. Ghi nhận nguyên nhân, impact, recovery result và biện pháp ngăn tái diễn.

## 27. Sai lầm thường gặp

**“Dùng batch listener là có EOS.”** Không đúng. Phải có transactional producer/container và offset coordination.

**“Bật ack-mode=batch là bật transaction.”** Không đúng. AckMode là chính sách acknowledgment, không thay cho KafkaTransactionManager.

**“KafkaTemplate.send thành công nghĩa là batch đã commit.”** Không đúng. Send acknowledgement đến trước kết quả commit transaction.

**“Khi R2 lỗi, output R0 và R1 chắc chắn được giữ lại.”** Nếu chúng nằm trong transaction đã abort, read_committed consumer không nhận chúng.

**“EOS nghĩa là listener chỉ chạy một lần.”** Rollback có thể khiến cùng input được xử lý lại.

**“BatchListenerFailedException luôn cho phép partial commit trong transaction.”** Khả năng recovery batch tùy version/AfterRollbackProcessor; không thể commit một phần của transaction đã abort.

**“DefaultErrorHandler non-transactional hoạt động y hệt trong transactional listener.”** Transaction rollback có cơ chế AfterRollbackProcessor riêng.

**“Kafka rollback được DB hoặc HTTP.”** Không đúng. Side effect ngoài Kafka cần outbox/inbox hoặc idempotency.

**“Consumer mặc định sẽ ẩn aborted transactional records.”** Không nên giả định; phải cấu hình read_committed khi yêu cầu.

**“Tăng max.poll.records luôn cải thiện throughput.”** Batch lớn có thể làm transaction timeout và tăng thời gian rollback.

**“Nhiều pod dùng cùng transactional ID đều ổn.”** Có thể gây producer fencing và lỗi kéo dài.

**“DLT publish thất bại nhưng vẫn commit offset là an toàn.”** Có thể làm record bị bỏ qua mà không có bằng chứng recovery.

## 28. Ghi nhớ

**EOS và batch listener** trong Spring Kafka có nghĩa là kết hợp batch processing với Kafka transaction sao cho **output Kafka và input offsets được commit/abort cùng nhau**. Để có hành vi đó, cần transactional ProducerFactory, KafkaTemplate tham gia transaction của listener container, configuration đúng cho consumer group và downstream dùng read_committed.

Khi batch thất bại, toàn transaction có thể abort và batch có thể được giao lại. Những output Kafka của transaction abort không được read_committed consumer xử lý, nhưng method listener và side effect ngoài Kafka vẫn có thể chạy lặp. Vì vậy, EOS không thay thế idempotency, outbox/inbox hay recovery policy.

Một hệ thống đáng tin cậy phải kiểm soát transaction duration, partition assignment, rollback/retry qua AfterRollbackProcessor, DLT, transactional ID fencing, input offset commit và các tình huống crash. Hãy chứng minh các bảo đảm bằng integration test commit, abort, replay và recovery failure trước khi áp dụng ở production.
