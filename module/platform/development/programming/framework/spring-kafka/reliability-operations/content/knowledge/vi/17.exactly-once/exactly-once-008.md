# Transactional producer và isolation

Khi triển khai **exactly-once processing** trên Kafka, hai thành phần phải phối hợp: **transactional producer** ghi các record và offset như một đơn vị nguyên tử, còn **consumer isolation** quyết định downstream được nhìn thấy những record nào. Chỉ bật transaction ở producer không đủ để mọi consumer đọc đúng kết quả: nếu downstream sử dụng read_uncommitted, nó vẫn có thể đọc output của transaction cuối cùng bị abort. Ngược lại, chỉ bật read_committed cho consumer cũng không làm thao tác xử lý trở thành exactly-once nếu producer và offset đầu vào không được commit trong cùng Kafka transaction.

Với Spring Kafka, mô hình tiêu biểu là **consume–transform–produce**: listener đọc record từ topic đầu vào, biến đổi dữ liệu, gửi sang topic đầu ra bằng KafkaTemplate transactional, rồi container đưa offset đã tiêu thụ vào cùng transaction. Khi transaction commit, output và tiến độ tiêu thụ cùng được ghi nhận; khi transaction abort, output transactional không hiển thị với read_committed consumer và offset đầu vào không được commit trong transaction đó.

Đây là một bảo đảm **trong phạm vi Kafka**. Nó không tự động làm database update, HTTP call, email hay thanh toán bên ngoài Kafka trở thành exactly-once. Bài học giải thích đầy đủ ranh giới bảo đảm, cấu hình Spring Kafka, hành vi isolation, các tình huống lỗi và phương pháp kiểm chứng khi vận hành.

## 1. Phân biệt delivery, processing và visibility

Trước khi cấu hình, cần phân biệt ba khái niệm có vẻ giống nhau nhưng khác nhau:

- **Delivery:** một record có thể được consumer nhận một lần hay nhiều lần.
- **Processing:** cùng một logic nghiệp vụ có thể thực thi một lần hay nhiều lần khi có retry, crash hoặc rebalance.
- **Visibility:** một record output của transaction có thể được downstream nhìn thấy trước commit hay sau khi transaction abort không.

Kafka transactions kết hợp idempotent producer, atomic output và atomic offset commit để hỗ trợ kết quả exactly-once trong luồng **đọc Kafka → xử lý → ghi Kafka** khi được cấu hình đúng. Consumer vẫn có thể thực thi listener lại sau rollback; điều quan trọng là **chỉ kết quả Kafka của transaction được commit mới trở thành kết quả hợp lệ** đối với downstream read_committed.

Ví dụ:

~~~text
orders-input (offset 150)
        |
        v
Spring Kafka listener
        |
        +-- Transform event
        |
        +-- KafkaTemplate.send("orders-output", value)
        |
        +-- Container gửi offset 151 vào transaction
        |
        v
Commit Kafka transaction
        |
        +-- Success:
        |      Output hiển thị với read_committed
        |      Consumer group lưu offset 151
        |
        +-- Abort:
               Output không hiển thị với read_committed
               Offset 151 không được commit cùng transaction
               Input offset 150 có thể được đọc lại
~~~

Nếu listener vừa ghi output Kafka vừa gọi REST API, REST side effect có thể đã xảy ra ngay cả khi Kafka transaction abort. Vì vậy, đừng suy diễn exactly-once Kafka thành exactly-once toàn bộ hệ thống.

## 2. Transactional producer là gì?

Một **transactional producer** là Kafka producer có **transactional.id** được thiết lập và được khởi tạo qua transaction protocol. Producer này có thể thực hiện nhiều send trong một transaction, rồi commit hoặc abort tất cả những record transactional đó như một đơn vị.

Vòng đời cơ bản của Kafka Producer API:

~~~java
Properties config = new Properties();
config.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "broker1:9092");
config.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
           StringSerializer.class);
config.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
           StringSerializer.class);
config.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG,
           "order-worker-instance-1");

try (KafkaProducer<String, String> producer =
         new KafkaProducer<>(config)) {

    producer.initTransactions();

    producer.beginTransaction();
    try {
        producer.send(
            new ProducerRecord<>("orders-output", "order-42", "VALIDATED")
        );
        producer.send(
            new ProducerRecord<>("orders-audit", "order-42", "VALIDATED")
        );

        producer.commitTransaction();
    }
    catch (Exception ex) {
        // Chỉ abort nếu producer và transaction vẫn cho phép;
        // xử lý fatal error/fencing theo Kafka client contract.
        producer.abortTransaction();
        throw ex;
    }
}
~~~

Đoạn code mô tả ý tưởng; không nên dùng một catch tổng quát để gọi abortTransaction vô điều kiện trong production, vì một số lỗi fatal hoặc producer fencing yêu cầu đóng producer thay vì tiếp tục điều khiển transaction cũ.

Điểm chính:

1. **initTransactions()** khởi tạo transactional producer với coordinator.
2. **beginTransaction()** mở transaction mới.
3. **send()** bổ sung record transactional vào các partition.
4. **commitTransaction()** hoàn tất commit theo protocol.
5. **abortTransaction()** hủy transaction còn có thể hủy nếu xảy ra lỗi phù hợp.

Nếu không có transactional.id, producer có thể sử dụng idempotence nhưng không có transaction để nhóm nhiều record và offset thành một atomic unit.

## 3. Transactional ID, producer ID và fencing

Kafka sử dụng **transactional.id** để định danh một logical transactional producer qua các lần khởi động. Coordinator gắn identity này với producer ID và epoch để ngăn một producer cũ tiếp tục ghi với quyền sở hữu đã hết hạn.

Ví dụ:

~~~text
Instance A: transactional.id = inventory-processor-0
        |
        +-- Đang xử lý transaction
        |
        +-- Mất mạng / restart kéo dài

Instance B: transactional.id = inventory-processor-0
        |
        +-- initTransactions() với cùng identity
        |
        +-- Producer epoch mới được thiết lập
        |
        v
Instance A trở thành producer cũ / zombie
        |
        v
Fencing ngăn A tiếp tục ghi như producer hợp lệ
~~~

Fencing là một phần quan trọng của transaction safety: một instance cũ không được tiếp tục commit output sau khi instance mới tiếp quản identity đó.

Tuy nhiên, **không được vô tình dùng cùng transactional.id cho nhiều instance đang hoạt động độc lập**. Nếu hai pod cùng dùng một identity, chúng có thể fence lẫn nhau, làm transaction abort, tăng lỗi và giảm throughput.

Spring Kafka thường tạo transactional IDs từ một **transactionIdPrefix** và các suffix thuộc producer factory. Prefix phải được thiết kế để mỗi application instance dùng vùng định danh riêng; suffix hỗ trợ nhiều producer được cache trong một instance. Cách phân bổ suffix/pool và các API quản lý prefix phụ thuộc phiên bản Spring Kafka.

## 4. Idempotent producer khác transactional producer

Hai cơ chế có liên hệ nhưng phạm vi khác nhau:

| Khả năng | Idempotent producer | Transactional producer |
|---|---|---|
| Chống duplicate do retry request producer trong session hợp lệ | Có, theo protocol sequence number | Có, dựa trên nền tảng idempotent producer |
| Nhóm nhiều record thành một atomic transaction | Không | Có |
| Đưa consumed offsets vào cùng atomic unit với output | Không | Có, khi dùng API/container phù hợp |
| Có transactional.id và fencing theo transaction identity | Không bắt buộc | Có |
| Cần downstream read_committed để ẩn aborted output | Không áp dụng với send không transactional | Có |
| Bảo đảm side effect database/HTTP exactly-once | Không | Không |

Khi cấu hình transactional.id, Kafka yêu cầu các điều kiện idempotence phù hợp. Các phiên bản Kafka hiện đại có thể tự kích hoạt idempotence theo cấu hình transaction, nhưng không nên ghi đè các producer properties theo cách xung đột, ví dụ ép enable.idempotence=false cho transactional producer.

Idempotence không tự phát hiện rằng hai lần ứng dụng gọi send() là cùng một business event. Nó bảo vệ retry protocol của producer cho một batch/record trong điều kiện tương ứng, không thay thế event ID và deduplication ở business layer.

## 5. Transaction coordinator và transaction log

Kafka có **transaction coordinator** chịu trách nhiệm quản lý transaction state của từng transactional.id. Transaction state được lưu ở topic nội bộ **__transaction_state**; coordinator sử dụng protocol để đánh dấu trạng thái và hoàn tất commit hoặc abort trên các partition tham gia.

Các thành phần:

- Transactional producer khởi tạo identity và epoch.
- Coordinator ghi nhận transaction đang diễn ra cùng các partition liên quan.
- Producer gửi record tới topic partitions.
- Nếu có consumed offsets, chúng được gửi qua transaction protocol tới consumer group coordinator phù hợp.
- Commit/abort markers và transaction state điều phối khả năng nhìn thấy output.

Không được suy luận rằng Kafka ghi mọi record vào một partition duy nhất; transaction có thể trải trên nhiều partition/topics trong cùng Kafka cluster và được phối hợp thông qua transaction coordinator.

Transaction không phải một distributed transaction chung giữa Kafka cluster A, Kafka cluster B và database. Nếu ứng dụng đồng thời ghi nhiều cluster độc lập hoặc một hệ thống bên ngoài, cần cơ chế consistency khác.

## 6. Isolation của consumer là gì?

Thuộc tính **isolation.level** ở Kafka consumer quyết định mức độ lọc các record thuộc transaction.

Hai chế độ:

~~~properties
isolation.level=read_uncommitted
~~~

và:

~~~properties
isolation.level=read_committed
~~~

### 6.1. read_uncommitted

Consumer ở chế độ read_uncommitted có thể đọc record transactional chưa commit và record thuộc transaction sau đó bị abort. Đây là lý do không nên sử dụng read_uncommitted cho downstream cần chỉ áp dụng kết quả giao dịch thành công.

read_uncommitted là mặc định của Kafka consumer ở nhiều phiên bản. Nếu pipeline cần transactional visibility, hãy cấu hình read_committed tường minh thay vì dựa vào mặc định.

### 6.2. read_committed

Consumer read_committed chỉ trả về các record transactional đã commit cùng các record không transactional có thể đọc theo protocol. Nó **không trả về** record thuộc transaction đã abort hoặc chưa hoàn tất.

Điểm dễ hiểu sai: read_committed **không có nghĩa** topic sẽ chỉ chứa record được sản xuất bằng transaction. Các record **non-transactional** vẫn có thể được read_committed consumer nhìn thấy nếu chúng nằm trong vùng dữ liệu có thể đọc.

### 6.3. Bảng so sánh

| Record trong Kafka log | read_uncommitted | read_committed |
|---|---|---|
| Record non-transactional đã ghi hợp lệ | Có thể đọc | Có thể đọc |
| Record transactional đã commit | Có thể đọc | Có thể đọc |
| Record transactional đang mở | Có thể được đọc tùy vị trí log | Không trả về trước khi commit |
| Record transactional đã abort | Có thể đọc | Bị lọc khỏi kết quả |
| Transaction control marker | Không phải event ứng dụng thông thường | Không trả về như business record |

Khi xây dựng đúng luồng exactly-once, các consumer downstream cần isolation phù hợp. Một dịch vụ đầu ra dùng read_uncommitted có thể vô tình xử lý output từ transaction đã bị hủy.

## 7. LSO, HW và LEO

Để hiểu read_committed, cần phân biệt các offset ở broker:

- **Log End Offset (LEO):** vị trí tiếp theo ở cuối log leader, biểu thị dữ liệu leader đã append đến đâu.
- **High Watermark (HW):** ranh giới dữ liệu đã replicate thỏa điều kiện để Kafka cho consumer đọc theo semantics tương ứng.
- **Last Stable Offset (LSO):** ranh giới ổn định dành cho read_committed; bị chi phối bởi transaction mở sớm nhất trong partition.

Với read_committed, fetch không trả dữ liệu transactional vượt ranh giới LSO. Một transaction còn mở có thể làm LSO nằm sau HW về mặt tiến độ, dù producer khác tiếp tục ghi vào partition đó.

Ví dụ:

~~~text
Partition events:

offset 100: record đã ổn định
offset 101: record thuộc transaction T (đang mở)
offset 102: record non-transactional từ producer khác
offset 103: record thuộc transaction U (đã commit)

                    LSO
                     |
                     v
... [100] [101] [102] [103] ...
                             |
                             v
                         HW / LEO
~~~

Trong tình huống minh họa, record 102/103 có thể phải chờ transaction T hoàn tất trước khi read_committed consumer tiếp tục trả về các record phía sau mốc LSO. Kafka đảm bảo khả năng đọc ổn định theo partition, không tự nhảy qua một transaction mở để đưa record phía sau vào kết quả read_committed.

Hình minh họa không phản ánh đầy đủ transaction control markers và mọi trạng thái replica; hãy hiểu nó như sơ đồ về giới hạn visibility.

## 8. Ví dụ commit và abort ảnh hưởng downstream thế nào?

Producer gửi hai record trong cùng transaction:

~~~text
Transaction TX-1:
  send(topic=A, key=k1, value=OUT-1)
  send(topic=B, key=k1, value=OUT-2)
  commitTransaction()
~~~

Khi commit hoàn tất, consumer read_committed trên A và B có thể nhìn thấy hai record đó khi fetch các partition tương ứng.

Nếu transaction abort:

~~~text
Transaction TX-2:
  send(topic=A, key=k2, value=TEMP-1)
  send(topic=B, key=k2, value=TEMP-2)
  abortTransaction()
~~~

read_committed consumer không trả TEMP-1 và TEMP-2 như record ứng dụng. read_uncommitted có thể đọc các record đã được append vào log trước/sau abort.

Điều quan trọng là transactional visibility độc lập với business validation. Broker không biết OUT-1 có đúng nghiệp vụ hay không; nó chỉ biết transaction đã commit hay abort theo protocol.

## 9. Exactly-once qua Kafka: vì sao phải commit offset cùng output?

Giả sử input ở offset 50 và output được gửi thành công, sau đó tiến trình chết trước khi commit offset input.

Nếu dùng producer không transactional:

~~~text
Read input offset 50
        |
        v
Send output O50 -> broker ghi thành công
        |
        v
Ứng dụng crash trước commit input offset 51
        |
        v
Restart: group đọc lại offset 50
        |
        v
Send output O50 lần nữa
        |
        v
Downstream có thể thấy duplicate
~~~

Nếu dùng Kafka transaction nhưng **output và input offset được commit riêng rẽ**, vẫn còn cửa sổ lỗi: commit output xong nhưng chưa commit offset input.

Do đó, luồng exactly-once Kafka cần **sendOffsetsToTransaction** hoặc container tương đương để đưa consumed offsets vào **cùng Kafka transaction** với output.

Khi commit transaction thành công:

- Output Kafka được commit.
- Consumed offsets được ghi nhận theo transaction.
- Consumer group tiếp tục từ offset mới khi phân công lại.

Khi abort:

- Output transaction bị ẩn với read_committed downstream.
- Offsets thuộc transaction không được commit.
- Input có thể được xử lý lại trong transaction mới.

Đây là cơ sở của EOS trong Kafka-to-Kafka stream processing.

## 10. Offset commit bằng sendOffsetsToTransaction

Với Kafka Java API thuần, producer có thể gửi map offset cùng metadata consumer group vào transaction:

~~~java
Map<TopicPartition, OffsetAndMetadata> offsets = Map.of(
    new TopicPartition("orders-input", 0),
    new OffsetAndMetadata(51L)
);

// Producer đang ở trong transaction hợp lệ.
producer.sendOffsetsToTransaction(
    offsets,
    consumer.groupMetadata()
);
~~~

Ở đây, offset **51** là vị trí **tiếp theo** của record offset 50 đã xử lý. Không commit offset 50 như thể đó là vị trí tiếp theo, vì consumer có thể đọc lại offset 50 khi restart.

Trong Spring Kafka transactional listener container, framework có thể thực hiện bước đưa offsets vào transaction thay cho application code. Không nên gọi consumer.commitSync() thủ công để commit input offset bên ngoài transaction nếu đang dựa vào EOS của container.

API cụ thể và điều kiện sử dụng sendOffsetsToTransaction thay đổi theo Kafka client version; dùng consumer.groupMetadata trong các API hiện đại để gắn offset commit với group metadata/generation phù hợp.

## 11. Cấu hình Spring Boot

Ví dụ ứng dụng Spring Boot dùng transactional producer và consumer read_committed:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - broker1:9092
      - broker2:9092
    producer:
      transaction-id-prefix: order-service-instance-a-
      acks: all
      properties:
        enable.idempotence: true
        transaction.timeout.ms: 60000
    consumer:
      group-id: orders-processor
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Ý nghĩa:

- **transaction-id-prefix:** kích hoạt khả năng tạo transactional producers thông qua Spring Kafka ProducerFactory.
- **acks=all:** producer yêu cầu acknowledgement theo cơ chế replica in-sync của Kafka.
- **enable.idempotence=true:** bảo vệ producer request retry khi phù hợp; với transactional producer phải đảm bảo các property không xung đột.
- **transaction.timeout.ms:** broker coordinator giới hạn transaction mở.
- **enable-auto-commit=false:** để listener container quản lý consumed offset.
- **read_committed:** phù hợp khi đầu vào có transactional records và consumer không được xử lý aborted output.

Consumer đọc input non-transactional vẫn có thể sử dụng read_committed; điều này không tạo transaction ở producer input. Bật read_committed ở consumer chỉ quyết định visibility của record được đọc.

**Quan trọng:** transaction-id-prefix cần được bố trí độc lập giữa các application instances chạy đồng thời. Ví dụ ở trên dùng chữ instance-a chỉ để minh họa; production nên tạo prefix dựa trên instance identity theo quy trình triển khai.

## 12. Cấu hình KafkaTemplate và KafkaTransactionManager

Spring Kafka dùng **DefaultKafkaProducerFactory**, **KafkaTemplate** và **KafkaTransactionManager** để tích hợp transaction vào ứng dụng. Trong các cấu hình Spring Boot thông dụng, có thể tự động tạo Kafka transaction manager khi cấu hình producer transaction-id-prefix; trong ứng dụng tự wiring, cần tạo transaction manager từ producer factory transactional.

Ví dụ Java:

~~~java
@Bean
ProducerFactory<String, OrderResult> producerFactory(
        Map<String, Object> producerConfig) {

    DefaultKafkaProducerFactory<String, OrderResult> factory =
        new DefaultKafkaProducerFactory<>(producerConfig);
    factory.setTransactionIdPrefix("order-service-instance-a-");
    return factory;
}

@Bean
KafkaTransactionManager<String, OrderResult> kafkaTransactionManager(
        ProducerFactory<String, OrderResult> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}

@Bean
KafkaTemplate<String, OrderResult> kafkaTemplate(
        ProducerFactory<String, OrderResult> producerFactory) {

    return new KafkaTemplate<>(producerFactory);
}
~~~

Map producerConfig phải chứa bootstrap servers, serializers và các producer properties phù hợp. Đoạn code là cấu trúc minh họa, không phải một Spring configuration file copy-paste hoàn chỉnh.

Transaction manager phải dùng đúng producer factory mà KafkaTemplate/container dựa vào. Nếu ứng dụng tạo nhiều producer factories hoặc gửi sang nhiều clusters, một KafkaTransactionManager không tự làm các cluster cùng commit nguyên tử.

## 13. Container transaction với @KafkaListener

Khi listener container được cấu hình KafkaAwareTransactionManager thích hợp, container có thể quản lý Kafka transaction quanh listener và offset commit.

Ví dụ:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        KafkaTransactionManager<String, OrderResult> kafkaTransactionManager) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
           .setKafkaAwareTransactionManager(kafkaTransactionManager);
    return factory;
}
~~~

Với các phiên bản Spring Kafka khác, tên setter hoặc phương pháp Boot tự cấu hình có thể khác. Hãy kiểm tra API đúng phiên bản; mục đích của cấu hình là liên kết container với Kafka transaction manager của transactional producer factory.

Listener:

~~~java
@KafkaListener(
    topics = "orders-input",
    groupId = "orders-processor",
    containerFactory = "ordersListenerFactory"
)
public void process(OrderEvent event) {
    OrderResult result = orderService.transform(event);
    kafkaTemplate.send(
        "orders-output",
        event.orderId(),
        result
    );
}
~~~

Luồng tổng quát:

1. Container poll record từ orders-input.
2. Container bắt đầu Kafka transaction theo phạm vi xử lý.
3. Listener gọi KafkaTemplate.send() với producer tham gia transaction.
4. Container đưa offset input đã xử lý vào cùng transaction.
5. Container commit transaction khi listener hoàn tất thành công.
6. Nếu listener ném exception hoặc transaction không thể commit, container rollback/abort và xử lý redelivery theo chính sách.

Không bật auto commit ở consumer khi muốn container kiểm soát transactional offset commit. Ngoài ra, không tự gọi acknowledge hoặc commitSync theo cách tách offset khỏi transaction mà framework quản lý.

## 14. KafkaTemplate.executeInTransaction và container transaction

KafkaTemplate cung cấp **executeInTransaction()** để thực hiện các send trong một Kafka transaction:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders-output", "order-12", result);
    operations.send("orders-audit", "order-12", auditEvent);
    return null;
});
~~~

Cách này hữu ích khi ứng dụng cần tạo một transaction cho các send Kafka mà không thông qua listener container transaction.

Nhưng có một ranh giới quan trọng: **executeInTransaction thường mở một local Kafka transaction của template**, không mặc nhiên là transaction đang do listener container quản lý. Không nên bọc toàn bộ Kafka sends trong executeInTransaction bên trong một transactional listener rồi giả định offset input tự động thuộc chính local transaction đó.

Nếu mục tiêu là consume–transform–produce EOS, hãy sử dụng KafkaTemplate cùng transaction manager do container đang quản lý và để container thực hiện transactional offset commit. Chỉ mở nested/local transaction khi hiểu chính xác semantics và ranh giới rollback của thư viện.

## 15. Một lần listener chạy lại không đồng nghĩa EOS bị phá

Giả sử record input offset 30 được xử lý:

~~~text
Lần 1:
   Input 30 -> output O30 trong TX-A
   TX-A abort

Lần 2:
   Input 30 -> output O30 trong TX-B
   TX-B commit
   Input offset 31 được commit cùng TX-B
~~~

Listener chạy hai lần, output có thể đã được append dưới hai transaction khác nhau vào log Kafka. Tuy nhiên, read_committed consumer chỉ trả về output từ TX-B (transaction đã commit). Downstream không nhìn thấy kết quả của TX-A bị abort.

Đây là cách hiểu đúng của exactly-once **effect** trong Kafka: không cần khẳng định listener Java chỉ chạy một lần. Kafka transaction và consumer isolation phối hợp để chỉ xuất ra kết quả committed hợp lệ.

Nếu listener có thêm một lời gọi HTTP tạo hóa đơn ở TX-A, HTTP side effect có thể đã xảy ra rồi. Transaction TX-A abort không xóa hóa đơn đó. Vì vậy, phần ngoài Kafka vẫn cần chống duplicate.

## 16. Spring Kafka transactional listener khi có lỗi

Với container transactional, exception từ listener thường dẫn đến rollback/abort transaction. Spring Kafka có các cơ chế xử lý sau rollback như **DefaultAfterRollbackProcessor**.

Ví dụ:

~~~text
Listener nhận Input X
      |
      +-- Gửi Output X vào Kafka TX
      |
      +-- Ném exception
              |
              v
       Transaction abort
              |
              v
       Kafka output X bị ẩn với read_committed
              |
              v
       Input offset chưa commit cùng TX
              |
              v
       AfterRollbackProcessor / redelivery
~~~

Không mặc định rằng một **DefaultErrorHandler** thiết lập cho non-transactional listener sẽ điều khiển toàn bộ retry của transactional listener. Transactional path và recovery processor cần được cấu hình theo phiên bản Spring Kafka.

Nếu sau nhiều lần xử lý thất bại ứng dụng muốn gửi record sang DLT, cần đánh giá **recovery transaction**: publish DLT và offset recovered có được xử lý theo protocol phù hợp không? Khi recovery publish lỗi, không cố ý commit input như thể record đã được lưu an toàn.

## 17. read_committed không thay thế consumer acknowledgment

Một hiểu lầm là bật isolation.level=read_committed sẽ tự bảo đảm offset input được commit exactly-once. Không đúng.

read_committed chỉ ảnh hưởng record nào consumer **được trả về bởi poll()**. Offset commit của consumer vẫn phụ thuộc container, transaction manager, AckMode và cách ứng dụng quản lý processing.

So sánh:

| Thiết lập | Kết quả |
|---|---|
| Producer transactional, downstream read_uncommitted | Downstream có thể nhìn thấy output transaction abort |
| Producer transactional, downstream read_committed | Downstream ẩn output chưa commit/đã abort |
| read_committed consumer nhưng output producer thường | Không có atomic output+offset commit |
| Transactional producer + commitSync offset riêng | Có cửa sổ output thành công nhưng offset input chưa commit |
| Transactional producer + consumed offsets trong cùng transaction + read_committed downstream | Có cơ sở cho exactly-once Kafka-to-Kafka |

Đối với một service chỉ đọc Kafka rồi ghi database, read_committed giúp tránh đọc aborted input, nhưng không làm database update và consumed offset Kafka thành một transaction nguyên tử. Lúc đó cần idempotent consumer, inbox/outbox hoặc thiết kế nhất quán khác.

## 18. Transaction timeout ảnh hưởng isolation thế nào?

Kafka producer có **transaction.timeout.ms**. Broker transaction coordinator có thể abort transaction mở quá lâu. Khi transaction bị abort, output của nó không xuất hiện với read_committed consumer.

Ví dụ:

~~~text
TX-A bắt đầu
   |
   +-- Ghi output record vào partition P
   |
   +-- Listener gọi dependency chậm 90s
   |
   +-- transaction timeout 60s
             |
             v
          Broker abort
             |
             v
read_committed consumer bỏ qua output TX-A
~~~

Tại thời điểm transaction chưa kết thúc, **LSO có thể bị giữ phía sau** và downstream read_committed tạm thời không đọc được các record nằm sau vị trí transaction đang mở trong partition. Khi transaction commit/abort, LSO có thể tiến lên.

Timeout quá thấp dẫn đến abort không cần thiết. Timeout quá lớn có thể giữ open transaction và LSO lâu khi producer bị treo. Hãy giữ transaction scope hợp lý và cấu hình timeout của HTTP/database dependency riêng.

## 19. Lag của read_committed consumer có thể gây hiểu nhầm

Một số dashboard tính consumer lag:

~~~text
lag = log_end_offset - committed_offset
~~~

Nhưng read_committed consumer có thể bị giới hạn bởi LSO, thấp hơn LEO khi transaction còn mở. Khi đó lag theo LEO tăng dù consumer không thể đọc thêm record phía sau transaction chưa hoàn tất.

Ví dụ:

- Producer ghi một transaction kéo dài.
- Một producer khác tiếp tục ghi vào cùng partition.
- LEO tăng, trong khi LSO vẫn nằm phía sau.
- read_committed consumer dừng ở mốc dữ liệu ổn định.
- Dashboard lag tăng.

Không nên chỉ tăng concurrency consumer để giải quyết. Hãy kiểm tra open transactions, producer commit/abort behavior, transaction timeout và health của coordinator.

Các công cụ tính lag khác nhau có thể dùng LEO, HW hoặc LSO; khi phân tích, xác nhận định nghĩa của exporter để tránh so sánh các metric không cùng mốc.

## 20. Producer fencing, zombie instance và duplicate

Producer fencing bảo vệ transaction khỏi instance cũ. Tuy nhiên, nó **không bảo vệ side effect bên ngoài Kafka**.

Giả sử instance A gọi Payment API thành công rồi mất kết nối. Instance B thay thế A, sử dụng transactional identity phù hợp để tiếp quản. A bị fence, không thể commit Kafka transaction cũ. Input được xử lý lại ở B.

Nếu Payment API không có idempotency, B có thể gọi API lần thứ hai. Kafka vẫn có thể chỉ commit một output hợp lệ với read_committed consumer, nhưng payment side effect đã bị lặp.

Để giải quyết:

- Dùng idempotency key dựa trên event ID ổn định.
- Lưu dấu processed trong database với unique constraint.
- Đặt kiểm tra dedup và cập nhật nghiệp vụ trong cùng database transaction.
- Với API có kết quả không rõ, đối soát trạng thái trước khi gửi lại yêu cầu có side effect.
- Dùng transactional outbox khi database là nguồn sự thật của nghiệp vụ.

Producer fencing giải quyết quyền ghi Kafka của zombie producer, không phải distributed transaction giữa tất cả dependency.

## 21. Exactly-once và database: ranh giới quan trọng

Một consumer đọc Kafka, cập nhật database, rồi commit Kafka offset có hai hệ thống bền vững độc lập:

~~~text
Kafka input
     |
     v
Database transaction commit
     |
     v
Kafka offset commit
~~~

Nếu database commit thành công nhưng ứng dụng crash trước Kafka offset commit, record được đọc lại và có thể cập nhật database lần hai.

Đảo thứ tự:

~~~text
Kafka offset commit
     |
     v
Database transaction commit
~~~

Nếu offset commit trước rồi database thất bại, record có thể bị bỏ qua đối với group.

KafkaTransactionManager và database transaction manager có thể được Spring phối hợp trong một số cấu hình, nhưng không nên gọi đó là một two-phase commit bảo đảm nguyên tử chung nếu hệ thống không thực sự sử dụng protocol có bảo đảm tương ứng. Sự cố ở ranh giới commit vẫn có thể tạo trạng thái không đồng nhất.

Giải pháp thường dùng:

- **Inbox/idempotent consumer:** event ID duy nhất, insert dedup và database update trong cùng transaction.
- **Transactional outbox:** commit business change và event intent trong cùng database transaction; publisher khác gửi outbox ra Kafka.
- **Saga/workflow:** quản lý trạng thái và compensation cho nhiều service.

Chọn một cách dựa trên nguồn dữ liệu chính và ranh giới consistency của nghiệp vụ.

## 22. Transactional outbox khác Kafka EOS thế nào?

Giả sử dịch vụ Order Service cần lưu đơn hàng trong database và phát OrderCreated:

~~~text
BEGIN DB TRANSACTION
    INSERT orders(...)
    INSERT outbox_events(event_id, payload, status)
COMMIT DB TRANSACTION

Outbox publisher:
    Đọc outbox event
    -> Publish Kafka
    -> Đánh dấu sent
~~~

Outbox giải quyết tính nhất quán giữa database business state và ý định phát event trong cùng database transaction. Publisher có thể gửi trùng nếu crash giữa publish và đánh dấu sent, vì vậy downstream cần event ID và idempotency.

Kafka EOS giải quyết atomicity của output Kafka và consumed offsets trong Kafka-to-Kafka processing. Hai cơ chế bổ sung cho nhau; không cơ chế nào tự động xóa mọi duplicate business event trong toàn bộ hệ thống.

## 23. Ordering và partition

Kafka đảm bảo thứ tự trong từng partition đối với các record đã được ghi theo log order. Transactions thêm visibility rule; chúng không tạo một global ordering duy nhất giữa nhiều partitions hay nhiều topics.

Ví dụ transaction gửi:

~~~text
TX:
   send to orders-output partition 0
   send to orders-audit partition 3
   commit
~~~

Transaction có thể làm hai record cùng được commit/abort theo protocol, nhưng consumer trên hai topic khác nhau không nhất thiết quan sát chúng tại cùng thời điểm vật lý. Một consumer có thể poll topic A trước khi consumer khác poll topic B. **Atomic commit không đồng nghĩa atomic read snapshot giữa mọi consumer**.

Nếu business logic yêu cầu ordering theo orderId, dùng partition key phù hợp và xử lý thứ tự tại đúng boundary. Transaction không giải quyết tự động dữ liệu đến muộn hoặc thay đổi key mapping sau khi tăng số partition.

## 24. Các tình huống failure cần hiểu

| Sự cố | Hệ quả Kafka transaction | Điều downstream cần |
|---|---|---|
| Listener exception trước commit | Transaction abort/rollback theo policy | read_committed ẩn output abort; redelivery input |
| Producer crash giữa các send | Transaction chưa commit; coordinator có thể abort | Không xử lý output chưa commit |
| Commit transaction thành công, ứng dụng chết trước khi nhận response | Kết quả có thể chưa rõ với ứng dụng | Fencing/idempotency và transaction protocol giúp recovery; tránh side effect ngoài Kafka lặp |
| Broker/coordinator abort vì timeout | Output transactional bị loại khỏi read_committed | Input có thể được đọc lại |
| Producer bị fence bởi instance mới | Producer cũ không còn quyền commit | Đóng producer cũ, sửa identity collision nếu sai |
| Consumer dùng read_uncommitted | Có thể thấy aborted output | Dùng read_committed khi cần EOS visibility |
| Offset được commit riêng ngoài transaction | Có cửa sổ duplicate hoặc sai tiến độ | Commit offsets cùng output transaction |
| Database ghi thành công nhưng Kafka transaction abort | DB state tồn tại, Kafka output/offset abort | Inbox/outbox/idempotency |
| DLT publish thất bại | Recovery chưa hoàn tất | Không cố ý commit offset như đã recover |

Không phải mọi lỗi request timeout đều có nghĩa broker đã abort transaction. Cần xem exception gốc, transaction state và client contract; xử lý một transaction có kết quả không rõ theo framework thay vì retry bừa thao tác commit trên producer đã lỗi.

## 25. Retry và recovery trong transactional pipeline

Một transactional listener có thể nhận cùng record nhiều lần sau rollback. Vì thế cần phân biệt:

1. Retry producer request nội bộ Kafka client.
2. Retry xử lý listener sau transaction abort.
3. Recovery record lỗi sang DLT khi hết retry.
4. Replay record từ DLT sau khi đã sửa nguyên nhân.

Transaction bảo vệ output Kafka của lần xử lý abort, nhưng mỗi tầng retry có thể tạo side effect ngoài Kafka.

Spring Kafka cung cấp **DefaultAfterRollbackProcessor** cho kịch bản xử lý sau rollback. Nếu ứng dụng sử dụng retry topic non-blocking, cần kiểm tra giới hạn của phiên bản Spring Kafka với transactional listener: pattern retry-topic tiêu chuẩn trong nhiều phiên bản không hỗ trợ container transactions và batch listeners.

Đối với DLT trong transactional path, cần xác định recovery publish cùng recovered offset có được commit theo transaction recovery phù hợp hay không. Không mặc định rằng mọi DeadLetterPublishingRecoverer đều tự động ghi DLT và offset nguồn nguyên tử chỉ vì listener dùng Kafka transaction.

## 26. Thời gian transaction và max.poll.interval.ms

Hai tham số quan trọng:

- **transaction.timeout.ms:** thời gian giao dịch producer được coordinator chấp nhận trước khi có thể abort do quá hạn.
- **max.poll.interval.ms:** giới hạn consumer không quay lại poll theo group protocol.

Listener xử lý quá lâu có thể gây cả transaction timeout lẫn consumer rebalance. Tăng một timeout không chắc giải quyết timeout còn lại.

Ví dụ:

~~~text
Listener xử lý 120 giây
      |
      +-- Kafka transaction timeout 60 giây
      |      -> coordinator có thể abort TX
      |
      +-- max.poll.interval.ms 90 giây
             -> consumer có thể mất quyền sở hữu partition
~~~

Nên:

- Giới hạn timeout HTTP/database.
- Giảm số record/khối lượng xử lý trong một transaction.
- Giữ transaction scope ngắn.
- Đo p95/p99 listener duration và producer commit latency.
- Cấu hình transaction.timeout.ms trong giới hạn broker transaction.max.timeout.ms.
- Theo dõi rebalance và transaction abort riêng rẽ.

Nếu hệ thống cần xử lý một job kéo dài nhiều phút, cân nhắc tách công việc sang workflow ngoài transaction hoặc phát event công việc rồi xử lý bất đồng bộ với idempotency.

## 27. read_committed có thể nhận record non-transactional

Một đặc điểm thường bị bỏ qua: nếu chỉ một phần producer của topic dùng transaction, read_committed consumer vẫn thấy record không transactional do producer khác gửi.

Ví dụ:

~~~text
orders-output:
   record A từ transactional producer (TX commit)
   record B từ producer thường
   record C từ transactional producer (TX abort)

read_committed consumer:
   A -> có
   B -> có
   C -> không
~~~

Nếu business requirement là mọi record của topic đều được tạo qua một transaction thành công, **đó là yêu cầu lên producer và kiến trúc**, không phải một filter có thể bật ở consumer. read_committed không kiểm tra chính sách nguồn gốc producer cho record non-transactional.

Khi nhiều team cùng ghi một topic, cần governance về serializer, producer transaction policy và quyền ghi, không chỉ cấu hình consumers.

## 28. Kiểm thử transactional producer và isolation

Một test đáng tin cậy cần quan sát cả **kết quả commit** lẫn **visibility** của consumer.

### 28.1. Transaction commit

1. Khởi tạo transactional producer.
2. beginTransaction, gửi record A.
3. commitTransaction thành công.
4. read_committed consumer đọc được A.
5. Xác nhận record A và offset theo đúng phạm vi test.

### 28.2. Transaction abort

1. beginTransaction, gửi record B.
2. abortTransaction.
3. read_committed consumer **không** nhận B như event ứng dụng.
4. read_uncommitted consumer có thể quan sát B tùy vị trí và dữ liệu log.

### 28.3. Consume–transform–produce rollback

1. Gửi input record X vào source.
2. Listener transactional gửi output Y rồi ném exception.
3. Container abort transaction.
4. read_committed downstream không thấy Y thuộc transaction abort.
5. Source offset không được commit cùng transaction abort.
6. Sau khi sửa lỗi, listener xử lý lại X và commit output/offset cùng transaction mới.

### 28.4. Producer fencing

Trong test cluster, thử khởi tạo một producer mới với cùng transactional.id khi producer cũ chưa đóng. Xác nhận producer cũ bị fence và ứng dụng không dùng lại producer đã mất quyền.

### 28.5. Open transaction và LSO

1. Mở transaction rồi gửi record vào partition.
2. Gửi các record khác sau đó.
3. Quan sát read_committed consumer bị giới hạn bởi LSO.
4. Commit hoặc abort transaction.
5. Xác nhận consumer tiếp tục đọc dữ liệu ổn định.

### 28.6. Side effect ngoài Kafka

1. Listener cập nhật database hoặc gọi mock HTTP API.
2. Ép Kafka transaction abort.
3. Redeliver record input.
4. Xác nhận side effect ngoài Kafka được bảo vệ bằng event ID/idempotency.

Tránh dùng chung cluster production cho test abort, fencing hoặc thay đổi transaction timeout. Dùng môi trường Kafka test hoặc fault injection được kiểm soát.

## 29. Quan sát và metrics

Nên theo dõi các chỉ số của producer, listener container và consumer downstream:

| Tín hiệu | Câu hỏi vận hành |
|---|---|
| Transaction begin/commit/abort rate | Có nhiều transaction abort bất thường không? |
| Transaction duration p95/p99 | Transaction có tiến gần timeout không? |
| Commit transaction latency | Coordinator hoặc broker có chậm không? |
| Producer send retries/errors | Lỗi hạ tầng có ảnh hưởng commit không? |
| Producer fencing count | Có collision transactional.id hay zombie producer không? |
| Consumer rebalance rate | max.poll.interval.ms hoặc membership có vấn đề không? |
| read_committed lag và oldest record age | Downstream đang chậm do xử lý hay LSO? |
| LSO/HW/LEO nếu exporter hỗ trợ | Transaction mở có đang giữ visibility không? |
| Listener business processing latency | Logic ứng dụng có giữ transaction quá lâu không? |
| Rollback/redelivery count | Source record có bị xử lý lại nhiều lần không? |
| DLT recovery failure | Record lỗi có được lưu an toàn không? |
| Business duplicate/idempotency conflict | Side effect ngoài Kafka có bị lặp không? |

Metric names tùy Kafka client, Spring Kafka, Micrometer và exporter. Có thể cần instrumentation ở ứng dụng để đo chính xác thời gian từ lúc transaction bắt đầu tới commit/abort.

Không dùng transaction ID hoặc event ID làm label metric có cardinality cao; dùng chúng trong log/trace với correlation ID, còn metric tổng hợp theo service, topic, group và exception class.

## 30. Runbook khi EOS không đúng kỳ vọng

### Bước 1: Xác định triệu chứng

- Downstream thấy record từ transaction abort?
- Output duplicate?
- Consumer group đọc lại input nhiều lần?
- Transaction abort hoặc producer fenced tăng?
- read_committed consumer lag tăng dù CPU thấp?

### Bước 2: Kiểm tra phía producer

- Producer factory có transactional.id/transactionIdPrefix không?
- Các instances có dùng prefix/identity riêng không?
- KafkaTemplate có tham gia đúng container transaction không?
- Producer có acks/idempotence và transaction.timeout.ms hợp lệ không?
- Có send bên ngoài transaction mà ứng dụng tưởng thuộc transaction không?

### Bước 3: Kiểm tra offset input

- Container có đang quản lý transactional offset commit không?
- Có consumer auto commit hoặc commitSync thủ công ngoài transaction không?
- Record offset N được commit thành N+1 khi xử lý thành công không?
- Khi transaction abort, offset đầu vào có bị ghi riêng không?

### Bước 4: Kiểm tra consumer isolation

- Downstream thật sự đặt isolation.level=read_committed chưa?
- Có consumer read_uncommitted ở một service khác không?
- Topic có record non-transactional từ producer khác không?
- Lag đang được đo so với LEO hay LSO?

### Bước 5: Kiểm tra ranh giới ngoài Kafka

- Duplicate xảy ra ở Kafka output hay database/API side effect?
- Có event ID/idempotency key ổn định không?
- Có outbox/inbox nếu cần nhất quán với database không?
- Có consumer replay từ DLT tạo business event mới không?

### Bước 6: Xác nhận phục hồi

Chạy lại test commit/abort, quan sát read_committed visibility, consumed offsets, transaction metrics và application side effects. Chỉ kết luận EOS đúng khi toàn bộ ranh giới đã nêu được kiểm chứng.

## 31. Các sai lầm thiết kế thường gặp

| Cách làm | Hậu quả | Hướng đúng |
|---|---|---|
| Bật transactional producer nhưng downstream read_uncommitted | Có thể đọc aborted output | Cấu hình read_committed ở downstream cần isolation |
| Bật read_committed nhưng commit input offset riêng | Không có atomic output+offset | Gửi offsets trong Kafka transaction/container |
| Dùng idempotence rồi gọi đó là multi-record EOS | Không có transaction nhóm records | Dùng transactional producer khi cần |
| Dùng cùng transactional.id giữa nhiều instance | Producer fencing lẫn nhau | Prefix/identity riêng theo instance |
| Gọi executeInTransaction trong container TX rồi giả định nested transaction dùng chung offset | Commit boundary khác kỳ vọng | Để template tham gia đúng container transaction |
| Gọi API/DB rồi tin Kafka abort sẽ rollback bên ngoài | Duplicate hoặc inconsistency | Idempotency, inbox/outbox, saga |
| Dùng retry topic non-blocking mà bỏ qua giới hạn với container transaction | Retry/offset semantics không như kỳ vọng | Chọn cơ chế recovery tương thích phiên bản |
| Tăng transaction timeout quá cao | Open TX giữ LSO lâu | Giữ transaction scope ngắn và theo dõi duration |
| Đọc lag theo LEO và kết luận consumer chậm | Bỏ sót LSO bị giữ bởi open TX | So sánh transaction state và offset metrics |
| Nghĩ read_committed chỉ đọc transactional records | Record non-transactional vẫn xuất hiện | Quản lý producer policy và topic ACL |
| Cho rằng Kafka EOS đồng nghĩa listener chạy đúng một lần | Không hiểu redelivery sau abort | Phân biệt processing attempts và committed effects |
| Tự retry mọi lỗi producer cũ sau fencing | Không thể phục hồi transaction cũ | Khởi tạo producer hợp lệ, xử lý fatal error |

## 32. Checklist cho production

Trước khi công bố một pipeline có Kafka exactly-once semantics, xác nhận:

1. Producer có transactional.id/transactionIdPrefix và không bị trùng giữa các instances đồng thời không?
2. Producer factory, KafkaTemplate và KafkaTransactionManager dùng cùng nguồn transactional producer phù hợp không?
3. Listener container có thực sự bắt đầu và commit Kafka transaction không?
4. Consumed offsets có được gửi vào **cùng transaction** với output Kafka không?
5. Consumer auto commit có tắt khi container quản lý offset không?
6. Downstream cần transactional visibility có dùng read_committed không?
7. Các producers khác có được phép ghi non-transactional vào cùng topic không?
8. Transaction timeout, broker max và max.poll.interval.ms có phù hợp thời gian xử lý không?
9. Có cơ chế rollback/redelivery phù hợp với transactional listener không?
10. Có test commit, abort, fencing, restart, coordinator outage và LSO không?
11. Có monitoring transaction abort, fencing, read_committed lag và producer errors không?
12. Khi Kafka transaction abort sau database/HTTP side effect, hệ thống có idempotency không?
13. Nếu dùng DLT, recovery publication và consumed offset có được quản lý an toàn không?
14. Có tránh áp dụng retry-topic pattern không tương thích với container transactions không?
15. Có runbook phân biệt duplicate Kafka output với duplicate nghiệp vụ ngoài Kafka không?

**Kết luận:** transactional producer và isolation là hai nửa bổ sung của một pipeline Kafka exactly-once. Transactional producer bảo đảm các output Kafka và consumed offsets được commit hoặc abort theo đúng transaction boundary; read_committed consumer chỉ quan sát output đã commit và lọc output abort. Spring Kafka có thể tự quản lý các bước này thông qua transactional ProducerFactory, KafkaTemplate và listener container. Tuy nhiên, ranh giới exactly-once vẫn là Kafka: để đạt độ tin cậy thực tế, cần giữ transaction scope phù hợp, xử lý rollback/fencing, theo dõi LSO và thiết kế idempotency cho tất cả side effect ngoài Kafka.
