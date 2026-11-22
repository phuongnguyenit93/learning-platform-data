# transactionIdPrefix

Trong Spring Kafka, **`transactionIdPrefix`** là tiền tố mà `DefaultKafkaProducerFactory` dùng để cấp `transactional.id` cho các Kafka producer có khả năng thực hiện transaction. Đây là cấu hình quan trọng với ứng dụng cần ghi nhiều record lên Kafka như một đơn vị nguyên tử hoặc cần ghi record đầu ra và commit offset đầu vào trong cùng Kafka transaction.

`transactionIdPrefix` không chỉ là một tên để hiển thị trong log. Từ tiền tố này, Spring Kafka tạo những định danh producer transactional; Kafka transaction coordinator dùng chúng để quản lý producer ID, epoch và phát hiện producer cũ hoặc trùng danh tính. Nếu nhiều instance cùng dùng một `transactional.id` thực tế, chúng có thể **fence** lẫn nhau, gây abort, lỗi listener, retry và consumer lag.

Bài học này tập trung vào cách đặt và quản lý prefix đúng trong hệ thống có nhiều replica, cách tích hợp với Spring Boot và Kafka listener transaction, những giới hạn của Kafka exactly-once semantics và các tình huống vận hành thường gặp.

## 1. Phân biệt transactionIdPrefix và transactional.id

Kafka producer thuần dùng cấu hình `transactional.id`. Spring Kafka cho phép khai báo `transactionIdPrefix` ở producer factory; factory ghép tiền tố này với suffix do nó quản lý để tạo `transactional.id` đầy đủ cho từng transactional producer.

Ví dụ một service có ba instance:

~~~text
Deployment        : orders-service
Environment       : production

Instance 0:
  transactionIdPrefix = prod-orders-0-tx-
  transactional.id    = prod-orders-0-tx-<suffix>

Instance 1:
  transactionIdPrefix = prod-orders-1-tx-
  transactional.id    = prod-orders-1-tx-<suffix>

Instance 2:
  transactionIdPrefix = prod-orders-2-tx-
  transactional.id    = prod-orders-2-tx-<suffix>
~~~

Phần `<suffix>` ở đây chỉ có tính minh họa; hình thức và vòng đời suffix thay đổi theo phiên bản Spring Kafka và chiến lược producer factory. Không viết mã phụ thuộc vào giả định rằng suffix luôn bắt đầu bằng 0 hoặc luôn tương ứng một partition cụ thể.

| Định danh | Do ai quản lý? | Vai trò |
|---|---|---|
| `transactionIdPrefix` | Ứng dụng/Spring Kafka producer factory | Tạo namespace cho transactional producer của một instance. |
| `transactional.id` | Kafka producer, được factory tạo từ prefix và suffix | Danh tính dùng với Kafka transaction coordinator. |
| Producer ID và epoch | Kafka broker và producer protocol | Theo dõi thế hệ producer, fencing producer cũ và bảo đảm tính đúng đắn của transaction. |
| `client.id` | Kafka client | Dùng cho log, metrics, quota; không thay thế transactional ID. |
| `group.id` | Kafka consumer | Định danh consumer group và offset; không phải producer transaction ID. |
| `group.instance.id` | Static consumer member | Giữ danh tính consumer qua restart, độc lập với producer prefix. |

**Nguyên tắc:** hai producer có thể đồng thời hoạt động để xử lý hai transaction độc lập không được dùng chung `transactional.id` thực tế. Định danh phải độc lập giữa các application instance, producer factory hoặc nguồn tạo producer có thể sinh trùng suffix.

## 2. Vì sao Kafka cần một transactional ID ổn định?

Một transaction Kafka có thể bao gồm nhiều lần `send()` đến nhiều partition/topic. Producer bắt đầu transaction, gửi record, rồi commit hoặc abort. Kafka coordinator gắn trạng thái transaction với `transactional.id`; khi producer mới khởi tạo cùng ID, broker có thể cấp producer epoch mới và **fence** producer thuộc thế hệ cũ.

~~~mermaid
sequenceDiagram
    participant F as Spring Kafka ProducerFactory
    participant P as Transactional KafkaProducer
    participant C as Transaction Coordinator
    participant T as Kafka output topics
    F->>P: Cấp producer với transactional.id
    P->>C: initTransactions
    C-->>P: producerId và epoch hợp lệ
    P->>C: beginTransaction
    P->>T: send A
    P->>T: send B
    alt Xử lý thành công
        P->>C: commitTransaction
        C-->>P: Commit thành công
    else Xử lý thất bại
        P->>C: abortTransaction
        C-->>P: Transaction aborted
    end
~~~

Fencing ngăn một producer cũ tiếp tục ghi khi một producer khác đã trở thành chủ sở hữu của transactional ID đó. Điều này hữu ích khi một instance restart nhưng process cũ vẫn đang hoạt động hoặc bị kẹt mạng.

Tuy nhiên, nếu hai replica hợp lệ được cấu hình cùng prefix và factory của chúng cấp cùng suffix, broker không thể biết đây là hai công việc độc lập. Chúng có thể lần lượt khởi tạo cùng transactional ID rồi fence nhau. Lỗi `ProducerFencedException` hoặc lỗi liên quan producer epoch cần được xem là tín hiệu điều tra identity/lifecycle, không đơn giản là một network timeout.

### Kafka transaction khác idempotent producer

Idempotent producer giảm duplicate do retry ghi dữ liệu từ một producer session. Kafka transaction bổ sung ranh giới commit/abort cho nhiều record, và có thể đưa offset consumer vào cùng transaction trong luồng consume–transform–produce.

`transactionIdPrefix` là thành phần cấp danh tính cho các producer transactional của Spring Kafka. Nó không tự kích hoạt transaction trên mọi lời gọi `send()` và không thay thế việc cấu hình transaction manager/container đúng cách.

## 3. Cấu hình với Spring Boot

Spring Boot cung cấp thuộc tính `spring.kafka.producer.transaction-id-prefix`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.internal:9092
    producer:
      transaction-id-prefix: prod-orders-instance-0-tx-
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: orders-transformer
      enable-auto-commit: false
      properties:
        "[isolation.level]": read_committed
    listener:
      ack-mode: record
~~~

Đây là một cấu hình minh họa **cho một instance duy nhất**. Khi chạy nhiều replica, phải thay `instance-0` bằng định danh tương ứng. Không copy nguyên prefix cố định cho mọi pod.

Trong những điều kiện auto-configuration phù hợp, Spring Boot có thể tạo `KafkaTransactionManager` từ producer factory đã cấu hình prefix. Container listener có thể sử dụng transaction manager đó nếu wiring tương ứng được thiết lập. Nhưng **có prefix không đủ chứng minh mọi `@KafkaListener` đều transactional**: cần kiểm tra container factory thực tế, đặc biệt khi có nhiều factory hoặc custom configuration.

`isolation.level=read_committed` ở ví dụ là cấu hình **consumer** nhằm chỉ đọc những record thuộc transaction đã commit. Nó không bật producer transaction và cũng không tạo transaction với database.

### Nguồn cấp prefix cho nhiều replica

Một cách thường dùng là chuẩn hóa:

~~~text
<environment>-<application>-<instance-id>-tx-

production-orders-orders-0-tx-
production-orders-orders-1-tx-
staging-orders-orders-0-tx-
~~~

Biến môi trường `INSTANCE_ID` cần được hệ thống triển khai cấp theo từng replica và không được rơi về cùng một fallback ở mọi process. Với Kubernetes StatefulSet, ordinal thường là nguồn identity ổn định. Với Kubernetes Deployment, pod name/UID có thể giúp tránh collision giữa các incarnation đang chạy, nhưng thay đổi qua lần tạo lại; cần đánh giá vòng đời transaction khi rollout và scale.

Nếu nhiều môi trường chia sẻ một Kafka cluster, prefix nên mang cả environment/namespace. Chỉ dùng `group.id` làm prefix là không đủ vì mọi consumer trong group có thể dùng chung group ID.

## 4. Cấu hình DefaultKafkaProducerFactory trực tiếp

Khi không dùng toàn bộ Spring Boot auto-configuration, ứng dụng có thể thiết lập tiền tố bằng `setTransactionIdPrefix(...)`:

~~~java
@Bean
ProducerFactory<String, OrderEvent> orderProducerFactory() {
    Map<String, Object> config = new HashMap<>();
    config.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "kafka-1.example.internal:9092");
    config.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class);
    config.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            JsonSerializer.class);

    DefaultKafkaProducerFactory<String, OrderEvent> factory =
            new DefaultKafkaProducerFactory<>(config);
    factory.setTransactionIdPrefix("prod-orders-instance-0-tx-");
    return factory;
}

@Bean
KafkaTemplate<String, OrderEvent> orderKafkaTemplate(
        ProducerFactory<String, OrderEvent> orderProducerFactory) {
    return new KafkaTemplate<>(orderProducerFactory);
}
~~~

Trong ví dụ, địa chỉ broker và prefix là placeholder cho mục đích minh họa. Production nên lấy từ cấu hình được quản lý, bảo đảm unique giữa các instance. Bean factory trên tạo producer transactional theo cách Spring Kafka hỗ trợ; việc **dùng transaction** vẫn phải được thực hiện bởi transaction manager, local transaction của `KafkaTemplate` hoặc container phù hợp.

Không cấu hình cùng một raw `ProducerConfig.TRANSACTIONAL_ID_CONFIG` cho mọi producer đồng thời rồi mong Spring Kafka tự xử lý collision. Đó là cách dễ tạo fencing. Hãy để producer factory quản lý hậu tố và việc tái sử dụng producer.

### Local producer transaction

Nếu muốn publish nhiều record Kafka trong cùng transaction mà không có consumer listener:

~~~java
public void publishChanges(OrderCreated created, OrderConfirmed confirmed) {
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders.events", created.orderId(), created);
        operations.send("orders.events", confirmed.orderId(), confirmed);
        return null;
    });
}
~~~

Ví dụ giả định template dùng producer factory transactional và kiểu serializer phù hợp. `executeInTransaction` tạo một **local Kafka producer transaction** để gom hai lần gửi. Nó không tự đưa offset đầu vào của một listener vào transaction. Phải phân biệt local transaction với listener container transaction.

## 5. Sử dụng trong consume–transform–produce

Khi xử lý một record nguồn rồi tạo record kết quả trên Kafka, Spring Kafka có thể phối hợp producer transaction và offset nguồn trong cùng Kafka transaction.

~~~mermaid
sequenceDiagram
    participant I as Input topic
    participant C as Transactional listener container
    participant L as Listener
    participant P as KafkaTemplate
    participant K as Kafka transaction coordinator
    participant O as Output topic
    I-->>C: poll record offset N
    C->>K: begin Kafka transaction
    C->>L: gọi listener
    L->>P: send kết quả
    P->>O: Ghi record trong transaction
    alt Listener thành công
        C->>K: sendOffsetsToTransaction offset N+1
        C->>K: commit transaction
        Note over I,O: Output cùng offset nguồn đã được commit
    else Listener ném exception
        C->>K: abort transaction
        C->>C: AfterRollbackProcessor xử lý
        Note over I,O: Transaction thất bại không commit offset nguồn
    end
~~~

Ví dụ listener:

~~~java
@KafkaListener(
        topics = "orders.commands",
        groupId = "orders-transformer",
        containerFactory = "transactionalListenerFactory")
public void transform(ConsumerRecord<String, OrderCommand> record) {
    OrderResult result = orderService.transform(record.value());
    resultKafkaTemplate.send(
            "orders.results",
            record.key(),
            result);
}
~~~

`transactionalListenerFactory` là tên bean giả định của một listener container factory **đã được cấu hình** Kafka transaction manager phù hợp. `resultKafkaTemplate` cũng phải dùng producer factory đúng để tham gia Kafka transaction của container. Không suy ra transaction là hợp lệ chỉ từ tên bean hoặc vì method có annotation `@KafkaListener`.

Khi listener trả về bình thường và các thao tác Kafka thành công, container gửi offset của record đã xử lý vào transaction rồi commit. Nếu listener ném exception, container rollback và sử dụng xử lý sau rollback (ví dụ `DefaultAfterRollbackProcessor`) để giao lại hoặc recovery theo cấu hình.

Không bắt rồi nuốt exception khi nghiệp vụ thất bại. Nếu listener trả về thành công dù một bước bắt buộc chưa hoàn tất, container có thể tiếp tục commit transaction với kết quả không đầy đủ.

### read_committed ở downstream

Consumer downstream cần `isolation.level=read_committed` nếu chỉ muốn nhận dữ liệu đã commit từ transactional producer. Consumer dùng `read_uncommitted` có thể nhìn thấy record thuộc transaction chưa commit hoặc đã abort theo ngữ nghĩa Kafka.

`read_committed` không có nghĩa mọi tác động ngoài Kafka đều exactly-once. Nó chỉ kiểm soát khả năng nhìn thấy Kafka transactional records.

## 6. Prefix phải duy nhất trong phạm vi nào?

`transactional.id` có ý nghĩa với transaction coordinator của **Kafka cluster**, không chỉ trong một `group.id`. Vì vậy, namespace của prefix cần tránh trùng giữa các service, môi trường và producer factory nếu chúng có thể tạo cùng ID đầy đủ trên cùng cluster.

| Triển khai | Cách cấp ID phù hợp | Nguy cơ cần tránh |
|---|---|---|
| Một pod đơn lẻ | Prefix cố định riêng cho pod | Vô tình nhân bản cấu hình khi scale. |
| StatefulSet | Service + namespace + ordinal | Hai process cùng ordinal/prefix hoạt động trong rollout overlap. |
| Deployment | Service + môi trường + pod identity riêng | Prefix fallback giống nhau hoặc ID thay đổi không được quản lý. |
| VM cố định | Service + instance ID ổn định | Clone VM với cấu hình giống hệt. |
| Nhiều KafkaTemplate/factory | Namespace phân biệt hoặc cùng factory có quản lý suffix an toàn | Hai factory độc lập sinh cùng transactional ID. |
| Nhiều environment dùng chung cluster | Thêm environment/tenant vào namespace | Staging fence producer production. |

Định danh **ổn định** có lợi cho fencing producer cũ khi một logical instance khởi động lại. Định danh **duy nhất giữa các incarnation** cũng có thể tránh collision, nhưng phải kiểm soát producer lifecycle và metadata transaction cũ. Lựa chọn phụ thuộc mô hình triển khai; điều bất biến là không có hai producer transactional độc lập đang chạy chung một ID đầy đủ.

Không sử dụng UUID mới cho từng record hoặc từng attempt để \"tránh fencing\". Cách đó tạo quá nhiều transactional identities, tăng chi phí coordinator, khó quản lý cache và che giấu lỗi vận hành.

## 7. Producer cache, concurrency và suffix strategy

Spring Kafka có thể tạo hoặc tái sử dụng nhiều transactional producer từ một `DefaultKafkaProducerFactory`. Một instance có nhiều listener thread, local transaction hoặc tác vụ publish song song có thể cần nhiều producer cùng lúc. Vì vậy, factory quản lý suffix và cache để tránh trùng transactional ID giữa những producer đang được dùng đồng thời.

Trong các phiên bản hỗ trợ, Spring Kafka cung cấp `TransactionIdSuffixStrategy` / `DefaultTransactionIdSuffixStrategy` để điều khiển cách cấp suffix, trong đó có các cơ chế pool suffix hữu hạn. Khi số transaction đồng thời vượt khả năng cấp producer của pool, ứng dụng có thể gặp `NoProducerAvailableException`.

Các điều cần nhớ:

- Prefix là namespace của instance/factory, **không phải** số lượng producer.
- Suffix tách biệt producer transactional được sử dụng đồng thời trong cùng namespace.
- Cache producer giảm chi phí khởi tạo producer/transactional identity.
- Quá ít producer hoặc suffix gây tranh chấp khi concurrency tăng.
- Quá nhiều producer/suffix có thể tăng tài nguyên, kết nối và trạng thái transaction không cần thiết.
- Chi tiết cấp và tái sử dụng suffix thay đổi qua phiên bản Spring Kafka; không hard-code suffix theo partition.

Ví dụ một service có `concurrency=4` và đồng thời có nhiều tác vụ `executeInTransaction`. Chọn cache chỉ phục vụ một producer có thể không đủ. Cần đo số transaction đồng thời, thời lượng transaction và workload thực tế để chọn sizing.

### Đóng producer không nhất thiết đóng kết nối

Với producer factory transactional của Spring Kafka, producer wrapper có thể được trả về cache sau khi transaction kết thúc, thay vì đóng producer vật lý ngay. Producer factory quản lý vòng đời và có thể đóng toàn bộ producer được quản lý khi ứng dụng shutdown. Không tự can thiệp vào producer underlying hoặc gọi transaction API từ thread khác nếu Spring Kafka đang điều phối transaction.

## 8. transactional.id expiration và maxAge

Kafka broker có cấu hình `transactional.id.expiration.ms` quản lý metadata của transactional ID không hoạt động trong một khoảng thời gian. Nếu producer được giữ trong cache rất lâu rồi tái sử dụng sau khi broker đã hết hạn identity, ứng dụng có thể gặp lỗi trong lần transaction kế tiếp.

Ở những phiên bản Spring Kafka có hỗ trợ, `DefaultKafkaProducerFactory` cung cấp `maxAge` để chủ động thay mới producer cached đã quá tuổi trước khi broker hết hạn transactional ID. Khi có producer ít được sử dụng hoặc workload có nhiều khoảng idle, hãy kiểm tra version và chọn `maxAge` đủ nhỏ so với ngưỡng broker, có biên an toàn.

| Tham số | Vị trí | Điều khiển |
|---|---|---|
| `transactional.id.expiration.ms` | Broker | Thời hạn metadata của transactional ID không hoạt động. |
| `maxAge` | Spring Kafka producer factory (nếu hỗ trợ) | Làm mới producer transactional đang cache theo tuổi. |
| `transaction.timeout.ms` | Kafka producer | Thời gian tối đa cho một transaction trước nguy cơ abort. |
| `max.poll.interval.ms` | Kafka consumer | Giới hạn khoảng cách giữa hai lần poll. |

Không nhầm lỗi fencing do **trùng transactional ID** với lỗi producer cache quá tuổi. Tăng một timeout không giải quyết tự động lỗi của tham số còn lại.

## 9. Transaction timeout và thời gian xử lý listener

Một transaction Kafka có thời gian tồn tại hữu hạn. Nếu listener gọi downstream rất lâu trong khi transaction mở, nó có thể vượt `transaction.timeout.ms`; Kafka coordinator có thể abort. Đồng thời, nếu consumer không quay lại `poll()` đủ sớm, nó có thể vượt `max.poll.interval.ms`, làm group rebalance.

Ví dụ một listener:

1. Poll record nguồn.
2. Bắt đầu Kafka transaction.
3. Gọi HTTP API với timeout hai phút.
4. Retry ba lần, mỗi lần chờ một phút.
5. Publish output và cố commit Kafka transaction.

Nếu transaction timeout và poll interval ngắn hơn tổng thời gian, việc commit có thể thất bại. Prefix đúng không giúp một transaction quá hạn trở nên hợp lệ.

Nên:

- Giới hạn timeout của HTTP/database và mỗi retry attempt.
- Giữ Kafka transaction ngắn, rõ ràng và đủ biên cho commit.
- Tránh `Thread.sleep` dài trong listener transactional.
- Dùng retry/rollback policy phù hợp với deadline poll và transaction.
- Với công việc cần chờ hàng phút/giờ, cân nhắc đưa vào workflow bền vững hoặc transactional outbox.

Kafka broker có thể giới hạn `transaction.timeout.ms` tối đa qua cấu hình broker, nên không được tăng timeout vô hạn.

### Retry và non-blocking retry

Với transactional listener container, lỗi thường rollback Kafka transaction và đi qua `AfterRollbackProcessor`/`DefaultAfterRollbackProcessor`. Không áp dụng mặc nhiên các quy tắc của `DefaultErrorHandler` non-transactional.

Tính năng non-blocking retry chuẩn qua `@RetryableTopic` **không kết hợp trực tiếp với Kafka container transactions** trong Spring Kafka. Nếu cần delay dài trong retry topic, phải thiết kế lại transaction boundary hoặc dùng mô hình khác; không chỉ thêm annotation để tạo \"exactly-once retry\".

## 10. Các cửa sổ lỗi và phạm vi bảo đảm

Kafka transaction phối hợp **những thao tác Kafka nằm trong cùng transaction**. Nó không tự bao trùm database transaction hoặc HTTP service.

| Tình huống | Kafka transaction hỗ trợ | Cần làm thêm |
|---|---|---|
| Publish nhiều output record trên Kafka | Commit/abort các record trong cùng Kafka transaction | Bảo đảm mọi send cùng tham gia transaction; downstream read committed. |
| Consume–transform–produce Kafka | Commit output và offset nguồn nguyên tử trong cùng transaction Kafka | Wiring đúng container/template/manager, xử lý abort. |
| Consumer cập nhật database | Không tự bao phủ database update | Inbox, unique event ID và database transaction. |
| Database update rồi gửi Kafka event | Không tự commit DB+Kafka atomically | Transactional outbox hoặc một giao thức phối hợp riêng. |
| Gửi HTTP trong listener | Abort Kafka không thu hồi HTTP request đã thành công | Idempotency key và kiểm tra kết quả không chắc chắn. |
| Publish DLT sau recovery | Phụ thuộc transaction/recoverer policy cụ thể | Xác nhận gửi DLT và offset commit; giữ khả năng replay. |

Ví dụ database đã commit nhưng process chết trước Kafka transaction commit: record nguồn có thể được đọc lại. Nếu không có idempotency, database có thể bị cập nhật hai lần. Vì vậy, ngay cả khi dùng Kafka transactional listener, consumer tác động ngoài Kafka vẫn cần chiến lược chống duplicate.

## 11. Những sự cố thường gặp

### Trùng prefix giữa các pod

**Triệu chứng:** `ProducerFencedException` lặp, transaction abort khi rollout, consumer lag tăng.

**Nguyên nhân:** nhiều producer factory cùng dùng prefix và sinh ra transactional ID giống nhau.

**Xử lý:** xác định prefix hiệu lực của từng replica/factory, sửa nguồn instance ID, kiểm tra rollout overlap và không tiếp tục tái sử dụng producer đã bị fenced.

### Prefix thay đổi theo từng message

**Triệu chứng:** rất nhiều transactional identities, metadata coordinator khó kiểm soát, khó tái sử dụng producer.

**Nguyên nhân:** code tự tạo producer factory/UUID transaction ID mới cho mỗi event.

**Xử lý:** cấu hình prefix theo instance, giữ producer factory có vòng đời quản lý và để Spring Kafka quản lý suffix/cache.

### Producer cache không đủ

**Triệu chứng:** với phiên bản có suffix pool hữu hạn, xuất hiện `NoProducerAvailableException` khi tải cao.

**Nguyên nhân:** concurrency cao hơn số producer/suffix có thể cấp.

**Xử lý:** kiểm tra producer pool, local transaction, listener concurrency và sizing; tăng cache phù hợp hoặc giới hạn transaction đồng thời.

### Fencing sau thời gian idle dài

**Triệu chứng:** transaction đầu tiên sau một khoảng không hoạt động bị lỗi dù transaction bình thường ổn định.

**Nguyên nhân có thể:** producer cached quá tuổi hoặc transactional ID broker hết hạn; cũng có thể do collision identity khác.

**Xử lý:** so sánh broker expiration, Spring Kafka `maxAge`, log error class và vòng đời factory; không kết luận nguyên nhân chỉ từ một exception.

### Có prefix nhưng offset không atomic với output

**Triệu chứng:** output đã ghi nhưng restart khiến record nguồn được xử lý lại, hoặc offset tiến ngoài transaction mong đợi.

**Nguyên nhân:** listener container chưa dùng đúng Kafka transaction manager, hoặc template gửi bên ngoài transaction của container.

**Xử lý:** kiểm tra container factory, template, producer factory và transaction manager; thử nghiệm crash trước commit để quan sát cả committed offsets và output với consumer read committed.

## 12. Observability cho transactionIdPrefix

Để chẩn đoán production, cần kết nối log transaction với instance và consumer assignment.

| Tín hiệu | Mục tiêu quan sát |
|---|---|
| Instance ID + prefix hiệu lực | Chứng minh mỗi replica có namespace không trùng. |
| Transaction begin/commit/abort | Phát hiện transaction không hoàn tất hoặc abort tăng bất thường. |
| `ProducerFencedException` / epoch errors | Phát hiện collision hoặc stale producer. |
| `NoProducerAvailableException` | Phát hiện suffix/cache không đủ trong phiên bản tương ứng. |
| Transaction duration p95/p99 | Phát hiện listener giữ transaction quá lâu. |
| Producer pool/cache size | Theo dõi số producer transactional đang sử dụng. |
| Consumer lag và rebalance | Liên hệ lỗi transaction với tiến độ offset. |
| Downstream read-committed output | Xác nhận Kafka output thành công có thể được đọc. |
| External DB idempotency outcome | Phát hiện duplicate vượt ngoài ranh giới Kafka. |

Log nên có service, environment, instance ID, group ID, listener ID, topic/partition/offset, transaction status và exception class. Chỉ ghi transactional ID/prefix khi cần chẩn đoán và đã kiểm soát cardinality; không đưa event ID vào metric label dễ gây bùng nổ series. Không ghi token, mật khẩu hoặc payload nhạy cảm.

## 13. Runbook khi xuất hiện ProducerFencedException

1. Xác định cluster, namespace, service, instance, producer factory và transactional ID đầy đủ nếu có.
2. Tìm tất cả pod/process có thể cùng tạo ID đó, kể cả process cũ chưa dừng khi rollout.
3. Kiểm tra nguồn `INSTANCE_ID`, default fallback, prefix theo environment và cách cấp suffix.
4. Phân biệt fencing producer cũ hợp lệ với hai instance đang hoạt động đụng identity ngoài ý muốn.
5. Khắc phục nguồn cấp prefix, dừng instance sai cấu hình theo quy trình deployment.
6. Khởi tạo producer mới đúng danh tính; không cố tái sử dụng producer đã bị fence.
7. Đối chiếu offset nguồn và output đã commit; kiểm tra idempotency khi record được giao lại.
8. Theo dõi abort/fencing và lag trong những lần rollout tiếp theo.

Không xử lý bằng cách tắt transaction trên toàn ứng dụng hoặc sinh prefix ngẫu nhiên mới cho từng message. Điều đó có thể loại bỏ triệu chứng nhưng làm mất bảo đảm thiết kế.

## 14. Runbook khi transaction abort hoặc timeout

1. Đọc exception gốc từ listener, template, transaction manager và Kafka broker.
2. Đo transaction duration và thời gian giữa poll; so sánh `transaction.timeout.ms` với `max.poll.interval.ms`.
3. Kiểm tra lời gọi I/O chặn, retry, backoff và kích thước batch.
4. Kiểm tra coordinator/broker, ACL, kết nối và transaction ID có xung đột không.
5. Xác nhận rollback/recovery/`DefaultAfterRollbackProcessor` theo phiên bản đang dùng.
6. Rút ngắn transaction hoặc thay đổi kiến trúc với công việc quá dài.
7. Kiểm tra offset commit, output đọc bằng `read_committed` và kết quả nghiệp vụ sau phục hồi.

## 15. Runbook khi scale nhiều replica

1. Liệt kê tất cả deployment và producer factory sử dụng transactional producer trên cùng cluster.
2. Thiết kế quy tắc prefix có environment, service và instance identity duy nhất.
3. Kiểm tra từng replica không dùng fallback trùng nhau.
4. Đo concurrency và sizing producer suffix/cache cho các transaction đồng thời.
5. Thử rolling restart, crash, process cũ chưa dừng và reconnect sau network partition.
6. Kiểm tra fencing, commit/abort, input offset và output read committed.
7. Theo dõi broker transaction coordinator, producer pool, group lag và lỗi transactional ID sau scale.

Nếu một JVM có nhiều producer factory độc lập nhưng dùng chung prefix, vẫn có nguy cơ trùng transactional ID. Uniqueness áp dụng cho các producer ID thực tế trong Kafka cluster, **không chỉ** cho số pod.

## 16. Bảng kiểm soát trước khi triển khai

| Điểm kiểm soát | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| Prefix configuration | Đã cấu hình `transactionIdPrefix` trên đúng producer factory chưa? | Effective Boot properties hoặc bean config. |
| Identity uniqueness | Replica/factory có tránh trùng transactional ID không? | Mapping instance → prefix, suffix strategy. |
| Container transaction | Listener có dùng Kafka transaction manager đúng không? | Container factory và logs begin/commit/abort. |
| Template participation | KafkaTemplate output có tham gia transaction listener không? | Producer factory wiring và fault injection. |
| Consumer visibility | Downstream cần đúng transactional semantics có dùng `read_committed` không? | Consumer effective config. |
| Producer cache | Pool/suffix đủ với transaction đồng thời không? | Concurrency, cache metrics, availability exception. |
| Expiration | Có quản lý producer lâu không sử dụng không? | Broker expiration, `maxAge` và lifecycle logs. |
| Timeout | Transaction và poll deadline phù hợp workload không? | Duration p99, timeout configs và retry policy. |
| Failure handling | Lỗi listener có rollback/retry/recover đúng không? | AfterRollbackProcessor và DLT outcome. |
| External consistency | DB/HTTP có chống duplicate ngoài Kafka transaction không? | Inbox/outbox, idempotency tests. |

**Kết luận:** `transactionIdPrefix` là cách Spring Kafka quản lý namespace của `transactional.id` cho transactional producer. Cấu hình đúng cần bảo đảm ID duy nhất giữa các instance/factory có thể hoạt động cùng lúc, dùng producer cache/suffix strategy phù hợp và quản lý timeout/expiration để tránh fencing. Sau đó mới cấu hình transaction manager, listener container và KafkaTemplate để đạt atomicity giữa Kafka output và input offset. Prefix đúng là điều kiện quan trọng của Kafka reliability, nhưng không tự tạo exactly-once cho database, HTTP hoặc các tác động ngoài Kafka.
