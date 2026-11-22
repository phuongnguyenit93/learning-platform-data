# isolation.level và read_committed

Trong Kafka, producer có thể ghi nhiều record trong một transaction rồi **commit** hoặc **abort** toàn bộ transaction. Consumer cần một cách xác định record nào đã thuộc về transaction hoàn tất và record nào vẫn đang chờ kết quả. Thuộc tính **isolation.level** điều khiển cách consumer đọc các record transactional đó.

Hai giá trị chính là:

- **read_uncommitted**: đọc record mà Kafka đã cho phép consumer nhìn thấy theo giới hạn replication, kể cả record thuộc transaction đang mở hoặc sau đó bị abort.
- **read_committed**: chỉ trả về record transactional thuộc transaction đã commit; bỏ qua record thuộc transaction bị abort và tạm dừng ở ranh giới của transaction chưa hoàn tất.

Trong chương **Consumer bền vững**, isolation level là một phần của hợp đồng đọc dữ liệu. Nếu ứng dụng đọc kết quả từ một producer có sử dụng Kafka transaction, lựa chọn **read_committed** giúp consumer chỉ xử lý các kết quả đã commit. Tuy nhiên, nó không tự tạo exactly-once cho toàn bộ ứng dụng và không thay thế commit offset, idempotency nghiệp vụ hay transaction của database.

## 1. Transaction của Kafka và góc nhìn của consumer

Kafka transaction cho phép producer gửi một nhóm record đến một hoặc nhiều partition, sau đó kết thúc nhóm đó bằng commit hoặc abort. Ví dụ, một service có thể đọc event **OrderCreated**, tạo event **InventoryReserved** và **PaymentRequested**, rồi ghi cả hai event đầu ra trong cùng một transaction Kafka.

Nếu transaction commit, các record đầu ra được xem là hợp lệ đối với consumer dùng **read_committed**. Nếu transaction abort, các record đó không được trả về cho consumer **read_committed**.

Luồng tổng quát:

~~~mermaid
flowchart TD
    P["Transactional producer"] --> B["beginTransaction"]
    B --> S["send record(s) to Kafka"]
    S --> D{"Kết quả nghiệp vụ"}
    D -->|Thành công| C["commitTransaction"]
    D -->|Thất bại| A["abortTransaction"]
    C --> R["read_committed consumer nhận record"]
    A --> X["read_committed consumer bỏ qua record"]
    S --> U["read_uncommitted consumer có thể thấy record trước khi kết thúc"]
~~~

Điểm cốt lõi là transaction status do Kafka quản lý. Consumer không tự suy luận transaction đã thành công từ payload, key hoặc header của record. Broker ghi nhận trạng thái transaction và phát các control marker tương ứng trong log partition.

Một transaction có thể chứa record ở nhiều partition và topic. Kafka phối hợp transaction coordinator với các partition tham gia để hoàn tất transaction. Consumer **read_committed** dựa trên trạng thái đó để quyết định record nào được trả về.

### 1.1 Những loại record consumer có thể gặp

Về mặt ứng dụng, cần phân biệt ba trường hợp:

1. **Record không thuộc transaction**: record được gửi bằng producer thông thường. Record này vẫn có thể được đọc bởi cả **read_uncommitted** và **read_committed** khi đã nằm trong phạm vi có thể đọc.
2. **Record thuộc transaction đã commit**: cả hai isolation level đều có thể trả về record này.
3. **Record thuộc transaction đang mở hoặc đã abort**: **read_uncommitted** có thể trả về record; **read_committed** chờ transaction hoàn tất và loại bỏ record nếu transaction abort.

Vì vậy, **read_committed** không có nghĩa là consumer chỉ đọc những record được gửi bởi transactional producer. Record non-transactional vẫn được trả về. Nếu một topic trộn dữ liệu transactional và non-transactional, consumer có thể nhận cả hai loại.

### 1.2 Transaction marker

Kafka lưu các marker nội bộ để thể hiện transaction commit hoặc abort trên các partition có record tham gia transaction. Các marker này là control record phục vụ broker và consumer protocol; ứng dụng không nhận chúng như message nghiệp vụ thông thường.

Consumer không cần tự đọc marker hay tự lọc theo header. Broker và client áp dụng isolation level để quyết định record nào được trả về.

## 2. Hai giá trị của isolation.level

Kafka consumer hỗ trợ hai giá trị cho cấu hình **isolation.level**:

| Giá trị | Hành vi | Khi phù hợp |
|---|---|---|
| **read_uncommitted** | Đọc record transactional ngay khi record nằm trong phạm vi có thể fetch, kể cả transaction chưa kết thúc hoặc sau đó abort | Consumer cần quan sát mọi record đã được ghi và chấp nhận xử lý dữ liệu transactional chưa commit |
| **read_committed** | Chỉ trả về record thuộc transaction đã commit; bỏ qua record thuộc transaction abort; chờ ở ranh giới transaction đang mở | Consumer dùng kết quả transactional như dữ liệu nghiệp vụ đã xác nhận |

Giá trị mặc định của Kafka consumer là **read_uncommitted** nếu ứng dụng không cấu hình khác. Do đó, chỉ bật transaction ở producer không tự động buộc mọi consumer phải đọc ở chế độ committed. Mỗi consumer client cần có isolation level phù hợp.

### 2.1 read_uncommitted

**read_uncommitted** là chế độ đọc mặc định của Kafka consumer. Tên gọi dễ gây nhầm: nó không có nghĩa consumer đọc dữ liệu chưa được replication theo cách tùy ý. Consumer vẫn bị giới hạn bởi phạm vi record mà broker cho phép fetch theo replication state. Khác biệt ở đây là trạng thái transaction.

Với **read_uncommitted**:

- Record non-transactional được đọc bình thường.
- Record thuộc transaction đang mở có thể được trả về trước khi producer commit.
- Record thuộc transaction sau đó bị abort vẫn có thể đã được ứng dụng xử lý.
- Consumer không thể thu hồi side effect đã thực hiện nếu producer abort sau đó.

Ví dụ, một producer gửi **PaymentApproved** bên trong transaction nhưng chưa commit. Consumer **read_uncommitted** có thể nhận record và gửi email xác nhận. Nếu producer abort transaction sau đó, Kafka đánh dấu record là aborted, nhưng email đã gửi không thể tự động được thu hồi.

Chế độ này phù hợp với các use case cần quan sát dữ liệu sớm và chấp nhận khả năng record transactional sẽ bị abort, chẳng hạn một số công cụ giám sát hoặc luồng phân tích chấp nhận dữ liệu tạm thời. Với consumer thực hiện nghiệp vụ không thể đảo ngược, cần cân nhắc kỹ.

### 2.2 read_committed

**read_committed** lọc record theo trạng thái transaction:

- Trả về record non-transactional khi record nằm trong phạm vi đọc.
- Trả về record transactional sau khi transaction commit.
- Bỏ qua record thuộc transaction đã abort.
- Không trả về record của transaction đang mở.
- Không đọc vượt qua ranh giới của transaction chưa hoàn tất trên partition liên quan.

Chế độ này phù hợp khi consumer cần xử lý kết quả đã commit từ transactional producer, đặc biệt trong pipeline consume-transform-produce hoặc các luồng nghiệp vụ sử dụng Kafka transaction.

Consumer **read_committed** không biết một transaction có đúng nghiệp vụ hay không. Nó chỉ biết Kafka transaction đã commit. Nếu producer commit một record sai nội dung, consumer vẫn nhận record đó. Kiểm tra nghiệp vụ, schema validation và idempotency vẫn cần được thực hiện ở ứng dụng.

## 3. Last Stable Offset và giới hạn đọc

Khác biệt quan trọng nhất khi vận hành **read_committed** là **Last Stable Offset (LSO)**.

Kafka partition có nhiều mốc offset. Hai mốc cần phân biệt trong ngữ cảnh này:

- **High Watermark (HW)**: ranh giới replication mà consumer **read_uncommitted** thường có thể đọc đến.
- **Last Stable Offset (LSO)**: ranh giới an toàn cho consumer **read_committed**, được giới hạn bởi transaction đang mở sớm nhất trên partition.

LSO đánh dấu vị trí mà consumer committed có thể đọc đến trước khi phải chờ transaction chưa hoàn tất. Nếu có một transaction đang mở tại offset thấp, các record ở offset cao hơn trên cùng partition có thể bị giữ lại đối với **read_committed**, kể cả khi các record đó đã được append và replicate.

Ví dụ partition có các record sau:

| Offset | Nội dung | Trạng thái |
|---:|---|---|
| 100 | OrderCreated | Non-transactional |
| 101 | InventoryReserved | Transaction T1 đang mở |
| 102 | PaymentRequested | Transaction T1 đang mở |
| 103 | CustomerNotified | Non-transactional |
| 104 | AuditRecorded | Non-transactional |

Khi T1 chưa commit hoặc abort:

- **read_uncommitted** có thể đọc đến HW và nhìn thấy các record ở 101, 102, 103, 104.
- **read_committed** có thể đọc record 100, nhưng dừng ở ranh giới LSO tại transaction chưa hoàn tất.
- Record 103 và 104 phải chờ dù chúng không thuộc T1, vì chúng nằm phía sau transaction đang mở trên cùng partition.

Sau khi T1 commit, LSO tiến lên và **read_committed** có thể đọc 101, 102, 103, 104. Nếu T1 abort, consumer bỏ qua 101 và 102 rồi tiếp tục đọc các record hợp lệ phía sau.

~~~mermaid
flowchart LR
    A["Offset 100<br/>non-transactional"] --> B["Offset 101-102<br/>transaction đang mở"]
    B --> C["Offset 103-104<br/>record phía sau"]
    subgraph RU["read_uncommitted"]
      R1["Có thể đọc qua transaction đang mở"]
    end
    subgraph RC["read_committed"]
      R2["Đọc đến ranh giới LSO rồi chờ"]
    end
~~~

Sơ đồ thể hiện một partition. Transaction đang mở ở partition này không tự động chặn partition khác. Consumer vẫn có thể nhận record từ các partition khác nếu chúng có LSO tiến triển.

### 3.1 Vì sao LSO có thể làm consumer chậm?

Một transaction mở lâu có thể giữ LSO ở một offset cũ. Khi đó:

- Record mới vẫn được producer append.
- Broker có thể tiếp tục replication.
- HW có thể tăng.
- LSO không tăng vượt qua transaction chưa hoàn tất.
- Consumer **read_committed** không nhận được record nằm sau ranh giới đó.

Nhìn từ ứng dụng, consumer có thể còn sống, không có exception và vẫn poll thành công nhưng không nhận thêm record từ partition bị chặn. Lag tính theo log end hoặc HW có thể tăng trong khi lag tính theo LSO lại không phản ánh cùng một con số.

Đây là lý do cần theo dõi tuổi transaction, trạng thái transaction coordinator, HW/LSO và consumer lag cùng lúc. Chỉ nhìn consumer process hoặc tổng lag không đủ để kết luận nguyên nhân.

### 3.2 Transaction mở lâu và timeout

Transaction nên có thời gian sống ngắn và hữu hạn. Producer cần commit hoặc abort trong khoảng thời gian được broker cho phép. Cấu hình **transaction.timeout.ms** ở producer xác định timeout transaction; broker giới hạn giá trị tối đa bằng cấu hình tương ứng như **transaction.max.timeout.ms**.

Nếu producer bị treo, chết hoặc không hoàn tất transaction, transaction coordinator có thể kết thúc transaction theo timeout. Khi transaction bị abort, LSO có thể tiến lên sau khi trạng thái và marker được xử lý.

Không nên tăng timeout thật lớn chỉ để tránh transaction timeout. Transaction kéo dài có thể giữ LSO, làm consumer **read_committed** chờ lâu và tăng độ trễ của các partition tham gia. Cần điều tra lý do transaction không kết thúc: downstream chậm, code giữ transaction quá lâu, network lỗi, coordinator không khả dụng hay producer bị kẹt.

## 4. Offset, record bị lọc và khoảng trống trong log

Kafka offset là vị trí trong partition log. Offset không phải số thứ tự liên tục của các record mà ứng dụng nhìn thấy.

Với **read_committed**, record thuộc transaction abort bị lọc khỏi kết quả trả về, nhưng offset của record đó vẫn tồn tại trong lịch sử log. Vì vậy, consumer có thể nhận record ở offset 100 rồi record tiếp theo ở offset 104. Các offset 101–103 có thể thuộc transaction abort hoặc không được trả về vì lý do isolation/compaction khác.

Khoảng trống offset là hành vi bình thường. Không nên giả định:

- Offset kế tiếp luôn bằng offset hiện tại cộng một.
- Số record nhận được trong poll bằng chênh lệch offset.
- Mỗi offset bị bỏ qua là một record bị mất.
- Consumer phải tự tăng offset từng đơn vị để vượt qua record abort.

Kafka client quản lý vị trí đọc và consumer group offset dựa trên offset log. Ứng dụng nên dùng metadata offset thực tế của từng record để log và điều tra.

### 4.1 Commit offset và transaction commit là hai khái niệm khác nhau

Cần tách biệt:

- **Producer transaction commit**: xác nhận nhóm record transactional đã hoàn tất và được phép hiển thị cho consumer **read_committed**.
- **Consumer offset commit**: lưu vị trí mà consumer group đã xử lý để lần khởi động sau tiếp tục đọc.
- **Database transaction commit**: xác nhận thay đổi dữ liệu trong database.

Ba loại commit này không tự động tương đương. Một producer transaction commit không có nghĩa consumer đã xử lý record. Consumer offset commit không có nghĩa database side effect đã commit. Database commit không tự động làm Kafka record được đánh dấu committed.

Trong một pipeline Kafka exactly-once, ứng dụng có thể phối hợp việc ghi record đầu ra và commit offset đầu vào trong cùng một Kafka transaction. Khi đó, consumer downstream dùng **read_committed** để chỉ nhìn thấy đầu ra của transaction đã commit.

## 5. Cấu hình isolation.level trong Kafka consumer

**isolation.level** là consumer configuration. Nó không phải cấu hình của producer và không thay đổi ACK hoặc replication policy.

Giá trị hợp lệ:

~~~properties
isolation.level=read_committed
~~~

Hoặc nếu cần giữ chế độ mặc định:

~~~properties
isolation.level=read_uncommitted
~~~

Có thể cấu hình trực tiếp qua Java client:

~~~java
Properties props = new Properties();

props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
          "kafka-1:9092,kafka-2:9092,kafka-3:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG,
          "billing-read-model");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
          StringDeserializer.class);
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
          StringDeserializer.class);
props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG,
          "read_committed");
~~~

Đặt **read_committed** trên từng consumer instance cần đọc dữ liệu transaction theo trạng thái commit. Nếu ứng dụng có nhiều consumer factory hoặc nhiều loại listener, hãy kiểm tra cấu hình thực tế của từng factory.

### 5.1 Cấu hình trong Spring Boot

Spring Boot có thể truyền isolation level qua consumer properties. Ví dụ:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    consumer:
      group-id: billing-read-model
      auto-offset-reset: earliest
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Trong các phiên bản Spring Boot hỗ trợ property chuyên biệt, có thể cấu hình bằng **spring.kafka.consumer.isolation-level**. Dùng một cách cấu hình phù hợp với phiên bản Boot của dự án và xác nhận consumer factory nhận đúng giá trị.

**enable-auto-commit: false** thường được dùng để container hoặc ứng dụng kiểm soát thời điểm commit offset. Nó không phải điều kiện bắt buộc để **read_committed** hoạt động; hai cấu hình giải quyết hai vấn đề khác nhau.

### 5.2 Cấu hình Java cho DefaultKafkaConsumerFactory

Nếu tự tạo factory:

~~~java
@Bean
ConsumerFactory<String, OrderEvent> consumerFactory() {
    Map<String, Object> props = new HashMap<>();

    props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
              "kafka-1:9092,kafka-2:9092,kafka-3:9092");
    props.put(ConsumerConfig.GROUP_ID_CONFIG,
              "order-read-model");
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
              StringDeserializer.class);
    props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
              JsonDeserializer.class);
    props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG,
              "read_committed");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
              false);

    return new DefaultKafkaConsumerFactory<>(props);
}
~~~

Nếu ứng dụng có nhiều **ConsumerFactory**, cấu hình một factory không tự động áp dụng cho các factory còn lại. Cần kiểm tra listener container factory mà từng **@KafkaListener** đang sử dụng.

## 6. Kết hợp read_committed với transactional producer

**read_committed** chỉ có ý nghĩa về transaction khi producer thực sự sử dụng Kafka transaction. Producer cần một **transactional.id** ổn định theo instance logic và transaction API để bắt đầu, commit hoặc abort transaction.

Ví dụ Java client:

~~~java
Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
          "kafka-1:9092,kafka-2:9092,kafka-3:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
          StringSerializer.class);
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
          StringSerializer.class);
props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG,
          "inventory-service-instance-1");

KafkaProducer<String, String> producer =
    new KafkaProducer<>(props);

producer.initTransactions();

try {
    producer.beginTransaction();

    producer.send(new ProducerRecord<>(
        "inventory-events", "sku-42", "InventoryReserved"
    ));

    producer.send(new ProducerRecord<>(
        "order-events", "order-1001", "OrderReady"
    ));

    producer.commitTransaction();
} catch (Exception ex) {
    producer.abortTransaction();
    throw ex;
}
~~~

Trong ví dụ, hai record được gửi tới hai topic khác nhau trong cùng transaction. Consumer **read_committed** sẽ chỉ nhận các record này khi transaction commit. Nếu transaction abort, consumer committed bỏ qua chúng.

Trong code production, cần xử lý các loại exception transaction đúng theo Kafka client version. Một số exception là retriable; một số lỗi yêu cầu đóng producer hoặc tạo producer mới. Không nên gọi **abortTransaction()** một cách mù quáng khi producer đã ở trạng thái fatal hoặc đã bị fencing. Hãy dùng đúng lifecycle và error handling của client.

### 6.1 transactional.id và producer fencing

**transactional.id** cho phép Kafka nhận diện producer có khả năng tiếp tục một transaction identity qua lần khởi động. Khi một producer mới khởi tạo cùng transactional ID, producer cũ có thể bị fencing để tránh hai producer cùng ghi bằng một identity.

Điều này bảo vệ tính đúng đắn của transaction nhưng yêu cầu ID được quản lý chính xác:

- Mỗi producer instance đang hoạt động cần identity phù hợp.
- Không dùng cùng một transactional ID cho hai instance độc lập cùng chạy.
- Khi restart cùng logical instance, cơ chế fencing giúp vô hiệu producer cũ.
- Xử lý **ProducerFencedException** như lỗi cần dừng producer cũ và phục hồi theo lifecycle mới.

Trong hệ thống nhiều pod, cần tạo transactional ID hoặc prefix duy nhất cho mỗi instance đang chạy. Không đặt một ID tĩnh giống nhau cho mọi pod.

### 6.2 Transaction commit và abort

Khi **commitTransaction()** thành công, Kafka hoàn tất transaction và record trở nên nhìn thấy được với **read_committed**. Khi **abortTransaction()** thành công, record thuộc transaction bị đánh dấu aborted và bị consumer committed bỏ qua.

Nếu ứng dụng mất kết nối trong lúc commit, kết quả có thể không rõ ràng đối với caller. Không nên giả định transaction chắc chắn abort chỉ vì client timeout. Cần dựa vào transaction lifecycle, producer identity và quy trình phục hồi; khi gửi lại nghiệp vụ, vẫn nên có event id để deduplicate ở tầng ứng dụng nếu cần.

## 7. Consume-transform-produce và exactly-once trong Kafka

Một use case quan trọng của **read_committed** là pipeline consume-transform-produce:

1. Consumer đọc input record.
2. Ứng dụng thực hiện chuyển đổi.
3. Producer ghi output record.
4. Offset của input record được gửi vào cùng transaction với output.
5. Kafka commit transaction.
6. Consumer downstream dùng **read_committed** đọc output đã commit.

Nếu transaction abort, cả output record và offset đầu vào được gửi trong transaction đó đều không được commit. Input có thể được xử lý lại theo cơ chế consumer recovery.

~~~mermaid
sequenceDiagram
    participant C as Input consumer
    participant A as Application
    participant K as Kafka
    participant D as Downstream consumer
    C->>K: Poll input record
    K-->>C: Input record
    C->>A: Process
    A->>K: Begin transaction
    A->>K: Produce output record
    A->>K: Add input offset to transaction
    A->>K: Commit transaction
    K-->>A: Commit success
    D->>K: Fetch with read_committed
    K-->>D: Committed output record
~~~

Đây là cơ sở của Kafka exactly-once semantics trong phạm vi Kafka. Để đạt được, cần phối hợp transactional producer, việc gửi offset vào transaction và consumer isolation phù hợp.

### 7.1 Vì sao phải đưa input offset vào transaction?

Nếu output được commit nhưng input offset không được commit cùng transaction, khi ứng dụng restart có thể đọc lại input và tạo output lần nữa. Nếu input offset commit trước khi output commit, lỗi giữa hai bước có thể làm mất output.

Đưa offset vào cùng transaction giúp Kafka hoàn tất cả hai kết quả như một đơn vị:

- Transaction commit: output được công bố và input offset được cập nhật.
- Transaction abort: output không được công bố với **read_committed**, input offset cũng không được cập nhật bởi transaction đó.

Trong Java client, producer hỗ trợ **sendOffsetsToTransaction(...)**. Trong Spring Kafka, listener container có thể quản lý transaction và offset cho luồng consume-transform-produce khi được cấu hình transactional.

### 7.2 read_committed ở consumer downstream

Consumer đọc output của pipeline nên đặt **isolation.level=read_committed**. Nếu downstream dùng **read_uncommitted**, nó có thể nhận output trước khi transaction kết thúc hoặc nhận output của transaction sau đó bị abort. Khi đó, lợi ích của transaction ở upstream bị mất ở ranh giới đọc downstream.

Mỗi consumer trong chuỗi cần được cấu hình nhất quán với semantics mong muốn. Một topic không tự ép consumer phải dùng **read_committed**.

### 7.3 Giới hạn của exactly-once

Exactly-once của Kafka transaction không tự mở rộng sang mọi side effect bên ngoài Kafka.

Ví dụ listener:

- Ghi database.
- Gửi email.
- Gọi HTTP API.
- Ghi file hoặc object storage.

Nếu database commit thành công nhưng Kafka transaction abort, database vẫn giữ thay đổi. Kafka không thể rollback database transaction nếu không có cơ chế phối hợp riêng. Tương tự, email đã gửi không thể được thu hồi khi Kafka transaction abort.

Với side effect ngoài Kafka, cần dùng các mẫu phù hợp như:

- Transactional outbox khi database là nguồn dữ liệu nghiệp vụ.
- Inbox/deduplication table khi consumer cần xử lý event lặp an toàn.
- Idempotency key khi gọi API bên ngoài.
- Saga hoặc compensation khi nghiệp vụ gồm nhiều hệ thống độc lập.

Không nên mô tả một pipeline là exactly-once end-to-end chỉ vì đã bật Kafka transaction.

## 8. Spring Kafka và read_committed

Spring Kafka cung cấp integration cho transactional producer và listener container. Khi cấu hình đúng, container có thể bắt đầu Kafka transaction cho lần xử lý listener, tham gia gửi output qua **KafkaTemplate** và gửi offset input vào transaction.

### 8.1 Cấu hình Spring Boot

Ví dụ cấu hình minh họa:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1:9092,kafka-2:9092,kafka-3:9092
    producer:
      transaction-id-prefix: ${INSTANCE_ID}-orders-
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
    listener:
      ack-mode: record
~~~

Ý nghĩa:

- **transaction-id-prefix** bật khả năng tạo transactional producer cho Spring Kafka.
- Prefix phải duy nhất giữa các application instance đang hoạt động. Giá trị **INSTANCE_ID** cần được cấp ổn định và khác nhau theo pod/instance.
- **isolation.level: read_committed** giúp consumer chỉ nhận kết quả transactional đã commit.
- **enable-auto-commit: false** để container quản lý offset theo lifecycle xử lý.
- **ack-mode** cần phù hợp với cách listener và transaction container được cấu hình. Với container-managed transaction, offset được gửi vào transaction theo cơ chế của container; không tự ý trộn manual ack nếu chưa hiểu semantics.

Khi Boot/Spring Kafka version hỗ trợ, cấu hình **spring.kafka.consumer.isolation-level** cũng có thể được dùng thay cho property map. Hãy kiểm tra property binding của phiên bản dự án và xác nhận giá trị cuối cùng trong ConsumerFactory.

### 8.2 Transactional KafkaTemplate

Ví dụ listener consume một event, tạo event đầu ra và gửi qua **KafkaTemplate**:

~~~java
@Component
class OrderProcessor {

    private final KafkaTemplate<String, OrderReady> kafkaTemplate;

    OrderProcessor(KafkaTemplate<String, OrderReady> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(
        topics = "orders",
        groupId = "order-processor"
    )
    public void handle(OrderCreated event) {
        OrderReady output = new OrderReady(
            event.orderId(),
            event.customerId()
        );

        kafkaTemplate.send(
            "order-ready",
            event.orderId(),
            output
        );
    }
}
~~~

Khi listener container được cấu hình để dùng Kafka transaction, send qua transactional **KafkaTemplate** có thể tham gia transaction đang được container quản lý. Container sẽ kết thúc transaction và xử lý offset input theo lifecycle transaction.

Nếu listener ném exception, transaction thường bị rollback và input offset không được commit trong transaction đó; record có thể được giao lại. Cần cấu hình rollback/retry/DLT theo chính sách nghiệp vụ. Không bắt exception rồi chỉ log nếu muốn transaction rollback: khi exception bị nuốt và listener trả về bình thường, container có thể xem lần xử lý là thành công.

### 8.3 Transaction manager và container factory

Với cấu hình Java, có thể tạo transactional producer factory và Kafka transaction manager. Ví dụ minh họa:

~~~java
@Bean
ProducerFactory<String, Object> producerFactory(
        KafkaProperties kafkaProperties,
        @Value("${app.instance-id}") String instanceId) {

    Map<String, Object> props =
        kafkaProperties.buildProducerProperties();

    DefaultKafkaProducerFactory<String, Object> factory =
        new DefaultKafkaProducerFactory<>(props);

    factory.setTransactionIdPrefix(
        instanceId + "-orders-"
    );

    return factory;
}

@Bean
KafkaTransactionManager<String, Object> kafkaTransactionManager(
        ProducerFactory<String, Object> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Đây là ví dụ cấu trúc, cần điều chỉnh generic type, property builder và listener container factory theo Spring Boot/Spring Kafka version đang sử dụng. Spring Boot có thể tự cấu hình một số bean khi transaction prefix được khai báo; không tạo bean trùng nếu auto-configuration đã cung cấp bean tương ứng.

Điều quan trọng là listener container phải thật sự sử dụng transactional producer/transaction manager dự kiến. Chỉ khai báo một **KafkaTransactionManager** trong application context không đảm bảo mọi listener đã chạy trong transaction nếu container factory không được cấu hình đúng.

### 8.4 Kiểm tra cấu hình thực tế

Khi vận hành, nên xác nhận:

- ConsumerFactory của listener có **isolation.level=read_committed**.
- ProducerFactory có transaction ID/prefix.
- Prefix khác nhau giữa các instance đang hoạt động.
- Listener container dùng transaction manager hoặc cơ chế container transaction đúng dự kiến.
- **KafkaTemplate** được inject sử dụng producer factory transactional tương ứng.
- Offset input được gửi vào transaction khi yêu cầu EOS.
- Consumer downstream cũng dùng **read_committed**.

Không chỉ kiểm tra file YAML. Có thể có nhiều factory, customizer hoặc profile ghi đè cấu hình. Hãy kiểm tra ConsumerFactory/ProducerFactory được listener sử dụng trong runtime.

## 9. Xử lý lỗi và phục hồi trong transactional listener

Transaction thay đổi cách listener xử lý lỗi. Một exception có thể khiến toàn bộ Kafka transaction rollback, bao gồm output record đã gửi trong transaction và offset input.

### 9.1 Listener lỗi trước khi commit

Ví dụ:

1. Listener nhận input.
2. Listener gửi output bằng transactional KafkaTemplate.
3. Một bước xử lý tiếp theo ném exception.
4. Container rollback transaction.
5. Output record trong transaction không được consumer **read_committed** nhìn thấy.
6. Offset input không được commit trong transaction.
7. Input có thể được đọc lại theo cơ chế recovery.

Điều này giúp tránh trạng thái output đã công bố trong khi offset input đã tiến lên mà không có cơ chế phối hợp.

### 9.2 Retry và rollback

Cần phân biệt lỗi tạm thời và lỗi không thể phục hồi:

- Lỗi tạm thời như timeout downstream hoặc broker interruption có thể retry với backoff.
- Lỗi dữ liệu vĩnh viễn có thể được chuyển vào DLT sau số lần thử phù hợp.
- Lỗi cấu hình hoặc xác thực diện rộng cần cảnh báo và sửa nguyên nhân, không retry vô hạn.

Với transactional listener, việc rollback và redelivery cần được cấu hình bằng error handler/AfterRollbackProcessor phù hợp. Nếu cần publish DLT trong một transaction mới, phải cấu hình recovery transaction rõ ràng theo Spring Kafka version. Không mặc định rằng mọi DLT publish đều tự động nằm trong cùng transaction đã rollback.

### 9.3 Transaction bị abort

Record thuộc transaction abort không được consumer **read_committed** trả về. Nếu consumer dùng **read_uncommitted**, record có thể đã được xử lý trước khi abort. Vì thế, khi một luồng downstream cần semantics transactional, isolation level phải được đặt nhất quán từ đầu.

### 9.4 Producer fencing

Nếu producer cũ bị fencing do transactional ID được dùng bởi producer instance mới, thao tác transaction của producer cũ có thể thất bại. Đây thường là dấu hiệu cấu hình ID bị trùng hoặc lifecycle instance có vấn đề.

Không retry vô hạn trên producer đã bị fencing. Dừng producer cũ và để instance có ownership hợp lệ tiếp tục theo cơ chế phục hồi.

## 10. Quan sát read_committed trong production

Consumer **read_committed** có thể bị chặn bởi transaction đang mở ngay cả khi broker vẫn nhận và replicate record. Cần quan sát các tín hiệu liên quan đến transaction và tiến triển đọc.

### 10.1 Consumer metrics

Theo dõi:

- Consumer lag theo group, topic và partition.
- Số record nhận được mỗi poll.
- Thời gian giữa các lần poll và processing latency.
- Consumer position và committed offset.
- Partition assignment và rebalance.
- Số lần listener rollback/retry.
- Tuổi record lâu nhất được xử lý.
- Thời gian không có progress theo partition.

Cần hiểu cách công cụ tính lag. Một dashboard so sánh committed offset với log end/HW có thể hiển thị lag lớn hơn số record hiện có thể đọc theo LSO. Không nên kết luận consumer chậm chỉ từ một con số tổng.

### 10.2 Transaction và partition metrics

Khi có thể, theo dõi:

- Số transaction đang mở và tuổi transaction.
- Transaction commit/abort rate.
- Transaction timeout và lỗi transaction coordinator.
- Producer fencing events.
- LSO và HW theo partition hoặc chênh lệch giữa chúng.
- ISR/replication health vì transaction marker cũng cần được ghi và replicate.
- Partition có LSO không tiến triển trong thời gian dài.

Tên metric cụ thể phụ thuộc Kafka version và hệ thống monitoring. Cần xác định metric thực tế được exporter cung cấp trước khi tạo alert.

### 10.3 Dấu hiệu transaction giữ LSO

Một mẫu sự cố thường gặp:

- Producer vẫn gửi record.
- HW tiếp tục tăng.
- LSO của một partition đứng yên.
- Consumer **read_committed** không nhận record mới trên partition đó.
- Consumer process không có lỗi rõ ràng.
- Các partition khác vẫn xử lý bình thường.

Khi gặp tình huống này, hãy kiểm tra transaction mở lâu, producer bị treo, coordinator state và timeout. Nếu chỉ tăng consumer concurrency, consumer mới cũng không thể đọc vượt qua LSO của partition đang bị chặn.

### 10.4 Phân biệt lag do transaction với lag do xử lý

Lag tăng có thể đến từ nhiều nguyên nhân:

- Producer tăng throughput.
- Consumer xử lý chậm.
- Consumer không poll hoặc rebalance liên tục.
- Downstream bị nghẽn.
- LSO bị giữ bởi transaction mở.
- Partition không có leader hoặc replication suy giảm.

Đối chiếu producer rate, HW, LSO, consumer position, processing latency và downstream metrics. Cần xác định record chưa thể đọc, record đã đọc nhưng chưa xử lý, hay record đã xử lý nhưng chưa commit offset.

## 11. Các tình huống vận hành thường gặp

| Tình huống | read_uncommitted | read_committed | Hướng xử lý |
|---|---|---|---|
| Producer gửi record non-transactional | Có thể đọc | Có thể đọc | Không có khác biệt về transaction |
| Transaction commit thành công | Đọc record | Đọc record | Xác nhận transaction và downstream progress |
| Transaction abort | Có thể đã đọc record trước khi abort | Bỏ qua record | Dùng read_committed cho consumer nghiệp vụ cần kết quả committed |
| Transaction còn mở | Có thể đọc record trong transaction | Chờ ở LSO | Kiểm tra producer và thời gian transaction |
| Transaction mở lâu ở offset thấp | Có thể đọc record phía sau đến giới hạn fetch | Record phía sau trên cùng partition bị chặn | Tìm transaction giữ LSO |
| Consumer restart sau khi bỏ qua record abort | Tiếp tục theo offset đã commit | Tiếp tục theo offset đã commit, offset có thể có gap | Không coi gap offset là mất dữ liệu |
| Producer bị fencing | Có thể thấy record đã được ghi trước đó | Chỉ thấy transaction đã commit | Khôi phục producer ownership và transaction lifecycle |

## 12. Những hiểu nhầm cần tránh

**“read_committed có nghĩa mọi record đều phải được producer gửi bằng transaction.”** Sai. Record non-transactional vẫn được trả về. Isolation level chỉ lọc record theo transaction status khi record thuộc transaction.

**“read_uncommitted đọc dữ liệu chưa replication.”** Sai. Khác biệt chính là transaction isolation. Consumer vẫn bị giới hạn bởi ranh giới đọc do Kafka quy định.

**“read_committed tự bật transaction cho producer.”** Sai. Producer phải được cấu hình transactional và sử dụng transaction API. Consumer isolation không thay đổi cách producer gửi record.

**“read_committed giống READ COMMITTED của database.”** Không hoàn toàn. Tên gọi tương tự nhưng cơ chế khác. Kafka lọc record theo trạng thái Kafka transaction và LSO; nó không tạo snapshot isolation trên database.

**“Nếu transaction abort thì mọi side effect đã chạy sẽ được rollback.”** Sai. Kafka có thể loại bỏ output record transactional và không commit offset trong transaction, nhưng email, HTTP call hoặc database commit bên ngoài không tự được rollback.

**“Bật read_committed là đủ để có exactly-once.”** Sai. Cần phối hợp transactional producer, input offset trong transaction, consumer group semantics và các thành phần phù hợp. Side effect ngoài Kafka vẫn cần cơ chế riêng.

**“Consumer không nhận record tức là producer chưa ghi.”** Sai. Record có thể đã append và replicate nhưng đang bị giữ phía sau LSO của transaction chưa hoàn tất.

**“Offset bị nhảy có nghĩa record bị mất.”** Sai. Consumer committed bỏ qua record thuộc transaction abort; offset log vẫn có thể tăng qua các vị trí đó.

**“Tăng consumer concurrency sẽ xử lý được partition bị giữ ở LSO.”** Sai. Nhiều consumer cùng đọc partition vẫn không thể vượt qua ranh giới transaction chưa hoàn tất.

## 13. Quy trình điều tra khi read_committed không nhận record

Khi producer báo gửi thành công nhưng consumer không thấy record, hãy khoanh vùng theo thứ tự:

1. Xác định topic, partition, key, event id và offset dự kiến.
2. Xác nhận producer có dùng transaction hay gửi non-transactional.
3. Nếu transactional, xác nhận transaction đã commit hay abort; kiểm tra kết quả **commitTransaction()** và lỗi coordinator.
4. Kiểm tra consumer thực tế có **isolation.level=read_committed** hay không.
5. Xem record nằm trước hay sau LSO của partition.
6. So sánh LSO và HW để xác định transaction đang mở có giữ ranh giới đọc hay không.
7. Kiểm tra tuổi transaction, producer health, transactional ID và fencing.
8. Kiểm tra consumer assignment, position, committed offset và lỗi deserialization/listener.
9. Sau khi transaction kết thúc, xác nhận LSO tiến lên và consumer tiếp tục nhận record.
10. Đối chiếu event id và business effect để tránh gửi lại một nghiệp vụ đã được commit nhưng chỉ bị chậm hiển thị.

Không nên lập tức reset consumer group offset khi chưa biết record bị abort, đang nằm sau LSO hay đã được consumer xử lý. Reset offset có thể gây replay và tạo side effect trùng.

## 14. Kiểm thử read_committed

Nên kiểm thử trong môi trường staging có broker và transaction configuration tương tự production.

### 14.1 Transaction commit

- Tạo transactional producer.
- Gửi một record trong transaction.
- Giữ transaction mở và xác nhận consumer **read_committed** chưa nhận record.
- Commit transaction.
- Xác nhận consumer **read_committed** nhận record.
- Xác nhận consumer **read_uncommitted** có thể nhìn thấy record trước khi commit.

### 14.2 Transaction abort

- Gửi record trong transaction.
- Cho **read_uncommitted** poll khi transaction còn mở.
- Abort transaction.
- Xác nhận consumer **read_committed** không trả về record đã abort.
- Xác nhận consumer **read_uncommitted** có thể đã nhận record trước khi abort.
- Kiểm tra offset của các record hợp lệ tiếp theo có thể có khoảng trống.

### 14.3 Transaction giữ LSO

- Mở transaction và ghi record ở partition thử nghiệm.
- Giữ transaction chưa kết thúc.
- Ghi thêm record phía sau trên cùng partition.
- Xác nhận **read_committed** dừng tại LSO.
- Commit hoặc abort transaction.
- Xác nhận LSO tiến lên và consumer tiếp tục đọc.

### 14.4 Consume-transform-produce

- Consumer đọc input.
- Producer transactional ghi output và gửi input offset vào transaction.
- Commit transaction.
- Xác nhận downstream **read_committed** nhận output và input offset được cập nhật.
- Lặp lại với transaction abort; xác nhận output không được công bố và input có thể được xử lý lại.

### 14.5 Producer fencing và timeout

- Khởi tạo producer transactional.
- Khởi tạo producer khác với cùng transactional ID trong môi trường thử nghiệm.
- Xác nhận producer cũ bị fencing theo cơ chế Kafka.
- Kiểm tra transaction timeout và khả năng LSO tiến lên sau khi transaction kết thúc.
- Ghi nhận lỗi và thời gian phục hồi.

Mỗi bài kiểm thử cần có topic/partition riêng, event id dễ truy vết, điều kiện dừng và tiêu chí thành công. Không thực hiện fault injection hoặc fencing trên producer production đang phục vụ nghiệp vụ thật.

## 15. Checklist cấu hình và vận hành

**Consumer**

- [ ] Consumer cần đọc kết quả transactional đã cấu hình **isolation.level=read_committed**.
- [ ] Tất cả consumer factory liên quan được cấu hình nhất quán.
- [ ] Consumer group offset được quản lý theo yêu cầu xử lý.
- [ ] Ứng dụng chấp nhận offset gap và không giả định offset liên tiếp.
- [ ] Có metric cho lag, position, commit và processing progress.

**Producer transaction**

- [ ] Producer transactional có **transactional.id** hoặc prefix được quản lý đúng.
- [ ] Transactional ID/prefix duy nhất giữa các instance đang hoạt động.
- [ ] Transaction có thời gian sống hữu hạn và commit/abort rõ ràng.
- [ ] Có xử lý retriable, fatal và fencing exception phù hợp.
- [ ] Không giữ transaction mở trong lúc chờ công việc ngoài Kafka quá lâu.

**Consume-transform-produce**

- [ ] Output record và input offset được đưa vào cùng Kafka transaction khi yêu cầu EOS.
- [ ] Downstream consumer dùng **read_committed**.
- [ ] Listener exception dẫn đến rollback theo chính sách mong muốn.
- [ ] Retry, DLT và recovery transaction được cấu hình rõ.
- [ ] Side effect ngoài Kafka có idempotency/outbox/inbox hoặc compensation phù hợp.

**Quan sát và phục hồi**

- [ ] Theo dõi transaction commit/abort, transaction age và fencing.
- [ ] Theo dõi LSO/HW và partition không có tiến triển.
- [ ] Phân biệt lag do xử lý với lag do transaction giữ LSO.
- [ ] Có runbook điều tra record không xuất hiện sau producer send.
- [ ] Đã kiểm thử commit, abort, LSO stall và producer fencing trong môi trường phù hợp.

**isolation.level=read_committed** giúp consumer chỉ xử lý kết quả của Kafka transaction đã commit. Để cơ chế này phát huy hiệu quả, producer phải quản lý transaction đúng cách, consumer phải dùng đúng isolation level và hệ thống phải theo dõi LSO cũng như transaction đang mở. Khi phối hợp với việc commit input offset trong cùng transaction, đây là nền tảng cho consume-transform-produce exactly-once trong phạm vi Kafka; các side effect bên ngoài Kafka vẫn cần được bảo vệ bằng thiết kế riêng.

