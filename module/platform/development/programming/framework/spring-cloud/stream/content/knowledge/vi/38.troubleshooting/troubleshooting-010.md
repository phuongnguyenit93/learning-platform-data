# Giao dịch bị rollback, timeout hoặc producer fencing

Trong một ứng dụng **SPRING_CLOUD_STREAM** xử lý sự kiện bằng Supplier/Function/Consumer, Kafka transaction giúp liên kết việc ghi nhiều record và, với luồng consume-transform-produce được cấu hình đúng, commit offset đầu vào cùng các record đầu ra trong một transaction Kafka. Tuy nhiên, transaction có thể bị rollback vì exception nghiệp vụ, timeout trong quá trình xử lý, mất kết nối broker, rebalance hoặc một producer khác chiếm cùng **transactional.id**.

Ba triệu chứng dễ bị nhầm là:

- **Rollback:** transaction hiện tại không được commit; output record nằm trong transaction bị abort và offset có thể được xử lý lại.
- **Timeout:** một giới hạn thời gian bị vượt. Có thể là transaction deadline tại broker, thời gian chờ metadata/acknowledgment của client hoặc chu kỳ poll của consumer; mỗi loại có cách xử lý khác nhau.
- **Producer fencing:** broker vô hiệu hóa một producer đang dùng epoch cũ của cùng transactional.id, ngăn producer đó tiếp tục ghi/commit transaction. Không được tiếp tục sử dụng instance đã bị fence.

Bài học thuộc chương **Chẩn đoán sự cố**. Trọng tâm là Kafka message binder và Kafka Streams binder của Spring Cloud Stream; RabbitMQ/Pulsar có transaction hoặc acknowledgment semantics khác, không thể áp dụng nguyên xi nguyên nhân và tham số Kafka.

## 1. Mô hình giao dịch Kafka cần hiểu trước khi chẩn đoán

Kafka producer transaction cho phép nhóm các record được ghi vào nhiều partition/topic và một nhóm consumer offsets thành một đơn vị commit/abort ở Kafka. Khi producer dùng **transactional.id**, broker gán producer ID cùng epoch để nhận diện owner hợp lệ của transactional session.

Một chu kỳ giao dịch điển hình:

~~~mermaid
flowchart TD
    A[Tạo transactional producer] --> B[initTransactions]
    B --> C[beginTransaction]
    C --> D[Send output records]
    D --> E{Có lỗi trong xử lý/gửi?}
    E -->|Không| F[sendOffsetsToTransaction nếu consume-process-produce]
    F --> G[commitTransaction]
    G --> H[Records và offsets được commit trong Kafka]
    E -->|Có lỗi có thể abort| I[abortTransaction]
    I --> J[Aborted records không hiện với read_committed]
    J --> K[Input có thể được xử lý lại]
    E -->|Fatal/fenced| L[Đóng producer; thay instance]
~~~

Mô hình này mô tả transaction ở Kafka. Framework như Spring Kafka hoặc Spring Cloud Stream có thể tự gọi các bước, nên application code thông thường không cần gọi thủ công begin/commit.

Điều quan trọng: **Kafka transaction không bao trùm tự động database, HTTP API hoặc hệ thống broker khác**. Một transaction Kafka rollback không thể tự hoàn tác khoản thanh toán đã thực hiện hoặc database transaction đã commit.

## 2. Sơ đồ đường xử lý của Spring Cloud Stream Kafka binder

Ví dụ một processor:

~~~java
@Bean
public Function<OrderCreated, OrderValidated> validateOrder(
        OrderValidator validator) {
    return validator::validate;
}
~~~

Bindings:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: order-validation-service
        validateOrder-out-0:
          destination: orders.validated
~~~

Khi **Kafka binder transaction được bật**, một lượt xử lý imperative thông thường diễn ra:

1. Listener nhận record từ input topic.
2. Container bắt đầu transaction Kafka.
3. Function xử lý record trên consumer thread.
4. Message gửi qua output binding tham gia transaction đang active trên thread đó.
5. Container đưa offset của record input vào transaction.
6. Nếu handler hoàn tất thành công, container commit transaction; nếu có lỗi, transaction bị rollback.
7. Sau rollback, container áp dụng cơ chế seek/re-fetch/retry và recovery tương ứng.

Các điều kiện cần lưu ý:

- Đường gửi output cần thực sự dùng **transactional producer factory** của cùng binder/transaction context.
- Xử lý bất đồng bộ hoặc gửi trên thread khác không tự tham gia transaction của consumer thread.
- Consumer đọc output của producer transactional nên có **isolation.level=read_committed** nếu yêu cầu không thấy dữ liệu bị abort.
- Một transaction thành công ở Kafka không xác minh các side effects ngoài Kafka.

## 3. Rollback nghĩa là gì đối với record và offset?

Giả sử input topic chứa event E42, function tạo output V42, sau đó ném exception.

| Thành phần | Khi transaction commit | Khi transaction abort |
| --- | --- | --- |
| Record output transactional V42 | Consumer read_committed có thể đọc | Consumer read_committed không thấy |
| Input offset được gửi vào cùng transaction | Commit hợp lệ; group có thể tiến | Không được commit như một phần transaction đó |
| Lần xử lý tiếp theo | Thường chuyển sang record mới | E42 có thể được đọc lại theo container recovery |
| HTTP/database side effect | Không thuộc Kafka transaction | Không tự rollback |
| Consumer read_uncommitted | Có thể thấy record committed | Có thể thấy cả record đã abort |

Một lần rollback không đồng nghĩa broker đã xóa record vật lý. Kafka vẫn có transaction markers và offset trong log. Consumer ở chế độ read_committed lọc record thuộc transaction đã abort.

**Không suy ra mất dữ liệu chỉ vì log chứa rollback.** Trước tiên xác minh output topic bằng read_committed, input committed offset và số lần xử lý/replay.

## 4. Phân loại nguyên nhân rollback

Rollback có thể là hành vi mong đợi hoặc triệu chứng hạ tầng.

| Nhóm | Ví dụ exception | Hành động |
| --- | --- | --- |
| Lỗi nghiệp vụ vĩnh viễn | InvalidOrderException, validation failed | Không retry vô hạn; sau rollback chuyển DLT/quarantine phù hợp |
| Lỗi tạm thời | HTTP 503, timeout database, leader election | Retry có giới hạn và backoff sau rollback |
| Lỗi producer | SerializationException, timeout, authorization | Xác định fatal/abortable trước khi retry |
| Lỗi consumer/group | CommitFailedException, rebalance, quá max.poll.interval.ms | Điều tra session/assignment và thời gian xử lý |
| Transaction coordinator | Broker unreachable, coordinator unavailable, transaction timeout | Đo latency, transaction state và broker health |
| Producer fencing | ProducerFencedException, InvalidProducerEpochException | Đóng producer đã bị fence; sửa transactional.id hoặc lifecycle |

Trước khi hành động, cần biết exception phát sinh **trong business function**, **lúc gửi record**, **lúc gửi offset**, hay **lúc commitTransaction**. Stack trace ở tầng KafkaProducer thường chứa nhiều lớp wrapper; đọc **root cause** và mốc thời gian của transaction.

## 5. Ba kiểu timeout không được nhầm

Trong hệ thống Kafka có ít nhất ba timeout độc lập thường bị gọi chung là “transaction timeout”.

| Timeout | Phạm vi | Ý nghĩa |
| --- | --- | --- |
| **transaction.timeout.ms** | Kafka producer transaction | Transaction mở quá lâu thì transaction coordinator có thể abort |
| **max.block.ms** | Các lời gọi KafkaProducer có thể block | Giới hạn chờ metadata, buffer hoặc một số thao tác transaction |
| **delivery.timeout.ms** | Gửi một producer record | Giới hạn tổng thời gian để record được báo success/failure sau khi send |
| **request.timeout.ms** | Producer request tới broker | Giới hạn chờ phản hồi request |
| **max.poll.interval.ms** | Consumer group member | Quá lâu giữa các lần poll có thể làm consumer mất membership/rebalance |
| **transaction.max.timeout.ms** | Kafka broker | Giới hạn tối đa broker cho phép client yêu cầu transaction.timeout.ms |

Ví dụ một transaction có **transaction.timeout.ms=60000** ms nhưng handler gọi API ngoài mất 90 giây. Coordinator có thể abort transaction trước khi handler kết thúc, kể cả khi max.poll.interval.ms vẫn còn nhiều thời gian.

Ngược lại, **TimeoutException** ở một lời gọi commit/abort có thể do **max.block.ms** hoặc lỗi truyền thông; nó không tự chứng minh broker đã abort transaction. Kết quả commit khi mất acknowledgment có thể **chưa chắc chắn từ góc nhìn caller**. Không nên lập tức publish bản sao mà chưa có kế hoạch idempotency/reconciliation.

## 6. transaction.timeout.ms và transaction.max.timeout.ms

Apache Kafka producer định nghĩa:

- **transaction.timeout.ms:** transaction coordinator sẽ chủ động abort transaction kéo dài quá giới hạn; trong Kafka 4.2, thời điểm bắt đầu tính gắn với lúc partition đầu tiên được thêm vào transaction.
- **transaction.max.timeout.ms:** mức tối đa broker cho phép một client yêu cầu. Nếu producer yêu cầu vượt mức này, Kafka trả lỗi cấu hình như **InvalidTxnTimeoutException** khi khởi tạo transaction.

Giá trị mặc định trong Kafka 4.2 được tài liệu công bố:

| Thuộc tính | Mặc định tham khảo | Nơi đặt |
| --- | --- | --- |
| transaction.timeout.ms | 60000 ms (1 phút) | Producer |
| transaction.max.timeout.ms | 900000 ms (15 phút) | Broker |

Đây là default theo phiên bản Kafka 4.2, không phải giới hạn nên áp dụng cho mọi ứng dụng. Đừng nâng broker max chỉ để che giấu một handler bị treo.

**Quy tắc chọn timeout:** transaction.timeout.ms phải đủ lớn so với độ trễ xử lý P99/P99.9, retry/backoff, time to commit, độ trễ broker; nhưng không nên quá lớn vì transaction mở giữ **Last Stable Offset (LSO)** của consumer read_committed ở những partition liên quan.

## 7. Ví dụ timeout do xử lý quá lâu

Một function:

~~~java
@Bean
public Function<OrderCreated, OrderValidated> validateOrder(
        OrderValidator validator) {
    return order -> {
        validator.validateWithExternalApi(order); // có thể chờ 75 giây
        return new OrderValidated(order.orderId(), true);
    };
}
~~~

Nếu transaction timeout = 60 giây và HTTP call chờ 75 giây, transaction có thể bị abort trước khi function trả output. Khi framework cố gửi hoặc commit, lỗi phát sinh có thể xuất hiện ở tầng producer/transaction manager.

Giải pháp phải bắt đầu từ profiling:

1. Đo thời gian xử lý function, HTTP call và transaction commit theo percentile.
2. Đặt timeout HTTP nhỏ, retry có giới hạn, circuit breaker phù hợp.
3. Chuyển công việc dài sang một bước bất đồng bộ có event riêng/outbox nếu thích hợp.
4. Chỉ tăng transaction.timeout.ms nếu nghiệp vụ và Kafka coordinator thực sự cần transaction dài.
5. Kiểm tra transaction.timeout.ms không vượt broker transaction.max.timeout.ms.
6. Kiểm thử khi broker chậm, producer retry và consumer rebalance cùng xảy ra.

Không giữ transaction Kafka mở trong lúc chờ người dùng xác nhận, workflow hàng phút hoặc một batch ngoại hệ thống lớn; chia thành nhiều bước nhỏ có định danh/idempotency.

## 8. TimeoutException không luôn có nghĩa transaction đã rollback

Một số trường hợp thường gặp:

~~~text
org.apache.kafka.common.errors.TimeoutException:
  Timeout of ... expired before successful completion

org.apache.kafka.common.errors.TimeoutException:
  Expiring ... record(s) for ...

org.apache.kafka.common.errors.InvalidTxnTimeoutException:
  Transaction timeout ... exceeds broker maximum ...
~~~

Đây là ví dụ log mang tính minh họa, message text thực tế thay đổi theo Kafka client version.

Cách điều tra đúng:

- **Lỗi metadata/buffer:** kiểm tra bootstrap servers, advertised listeners, ACL, buffer.memory, broker latency và max.block.ms.
- **Lỗi delivery:** kiểm tra delivery.timeout.ms, request.timeout.ms, retries, ISR/acks và network.
- **Lỗi transaction deadline:** kiểm tra transaction.timeout.ms và thời gian transaction thực tế mở.
- **Lỗi vượt broker maximum:** sửa cấu hình producer/broker tương thích.
- **Lỗi commit response timeout:** không tự khẳng định transaction đã abort; dùng read_committed, idempotency key và trạng thái consumer offset để đối chiếu trước khi replay.

Nếu một producer transaction đã rơi vào trạng thái fatal hoặc fencing, đừng cố “cứu” nó bằng cách tăng timeout rồi dùng lại object.

## 9. Producer fencing là gì?

Kafka dùng **transactional.id** để liên kết nhiều producer sessions tới cùng một transactional identity và **producer epoch** để loại bỏ producer cũ (zombie).

Ví dụ:

1. Pod A khởi động producer có transactional.id là **orders-tx-0**, epoch e1.
2. A treo hoặc mất mạng nhưng process chưa chết.
3. Pod B dùng cùng transactional.id **orders-tx-0** và gọi initTransactions, nhận epoch mới e2.
4. Broker từ chối các transactional requests tiếp theo của producer A.
5. A nhận **ProducerFencedException** hoặc lỗi epoch liên quan; A phải đóng producer đó.

~~~mermaid
sequenceDiagram
    participant A as Producer A (epoch e1)
    participant K as Kafka transaction coordinator
    participant B as Producer B (epoch e2)
    A->>K: initTransactions(orders-tx-0)
    K-->>A: epoch e1
    A->>K: begin/send (transaction mở)
    B->>K: initTransactions(orders-tx-0)
    K-->>B: epoch e2; fence phiên cũ
    A->>K: send/commit (epoch e1)
    K-->>A: ProducerFencedException
    Note over A: Close producer cũ, không retry cùng instance
    B->>K: begin/send/commit (epoch e2)
~~~

Fencing là cơ chế **bảo vệ tính đúng đắn**: chỉ producer session hợp lệ mới có thể thực hiện transactional requests cho một transactional ID. Nếu bỏ qua fencing và tiếp tục dùng producer cũ, hệ thống không an toàn hơn; nó chỉ lặp fatal error.

## 10. Khi nào fencing là bình thường, khi nào là lỗi triển khai?

Producer A cũ bị fence sau failover có thể là hành vi Kafka mong muốn, vì producer B mới tiếp quản identity để chặn zombie.

Nhưng fencing liên tục trong khi hai pod đều đang chạy bình thường thường là dấu hiệu cấu hình sai:

| Dấu hiệu | Nguyên nhân nghi ngờ |
| --- | --- |
| Hai replica cùng transactional.id/prefix | Prefix không unique per live instance |
| Fencing sau rolling deployment | Pod mới dùng identity trùng pod cũ trong thời gian overlap |
| Fencing khi producer cache sống lâu nhưng không hoạt động | Transactional ID bị broker expire, producer tái sử dụng stale epoch |
| Fencing sau restart/kết nối gián đoạn | New session lấy epoch mới, process zombie cũ tiếp tục chạy |
| Kafka Streams báo task migrated/fenced | Task chuyển owner khi rebalance/failover; cần phân biệt với binder producer prefix collision |
| Exception liên quan consumer group instance | Có thể là static membership **FencedInstanceIdException**, không đồng nhất ProducerFencedException |

Việc dùng cùng **transactional.id** tại hai instance **đang hoạt động đồng thời** là sai. Trong một số mô hình failover, cố ý tái sử dụng identity để fence zombie là chủ đích, nhưng cần có fencing lifecycle và deployment contract rõ ràng. Với Spring Kafka **EOSMode.V2**, tài liệu yêu cầu **transactionIdPrefix khác nhau trên từng active application instance**.

## 11. ProducerFencedException là lỗi fatal với producer đó

Theo Kafka Producer API, **ProducerFencedException** cho biết producer khác có cùng transactional.id đã thay thế session cũ. Khi gặp lỗi này, phải **close producer instance**; không gọi lại send/commit/abort trên object đã bị fence như một retry nghiệp vụ.

Hướng xử lý thực tế:

1. Ghi nhận transactional.id (được rút gọn/redact nếu cần), pod ID, instance ID, timestamp, stack trace gốc.
2. Dừng dùng producer đã bị fence, để framework/container quản lý close và tạo phiên mới khi thích hợp.
3. So sánh prefix và thực tế transactional.id của tất cả replica hoạt động.
4. Kiểm tra pod rollout overlap, orphan process, duplicate deployment và producer cache.
5. Nếu đã hết collision, chỉ khởi tạo producer mới theo lifecycle chuẩn.
6. Xác minh input offset, read_committed output và duplicate side effects trước replay.

Không bắt ProducerFencedException trong business function rồi trả về thành công; làm vậy có thể khiến caller tưởng record đã được commit. Không đổi transactional.id ngẫu nhiên cho từng record để “né” fencing: cách đó phá vỡ ý nghĩa của transactional identity theo producer session và tăng số identity không cần thiết.

## 12. Trường hợp fencing không có replica mới: producer hết hạn

Spring Kafka ghi nhận tình huống transactional producer lâu không hoạt động: broker có thể hết hạn transactional.id theo **transactional.id.expiration.ms**; khi producer cũ trong cache hoạt động trở lại, nó có thể gặp fencing dù không có một rebalance hoặc pod mới rõ ràng.

**DefaultKafkaProducerFactory** hỗ trợ **maxAge** để loại bỏ producer cache đã quá tuổi và tạo producer mới trước khi transactional.id hết hạn. Chỉ dùng tính năng này khi:

- Đã xác nhận triệu chứng gắn với idle producer và ID expiration.
- Chọn maxAge nhỏ hơn broker expiration window với biên an toàn.
- Kiểm tra factory thực tế mà binder dùng, không cấu hình nhầm vào producer factory khác.
- Không thay thế việc chẩn đoán prefix collision bằng thay đổi maxAge.

Không tự tăng transactional.id.expiration.ms quá lớn khi nguyên nhân thật sự là hai active replicas dùng trùng ID.

## 13. Bật Kafka transactional binder trong Spring Cloud Stream

Cấu hình tối thiểu minh họa:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: validation-service
        validateOrder-out-0:
          destination: orders.validated
      kafka:
        binder:
          brokers: kafka:9092
          transaction:
            transaction-id-prefix: order-validation-instance-a-
~~~

**spring.cloud.stream.kafka.binder.transaction.transactionIdPrefix** với giá trị khác rỗng kích hoạt transactional binder. Ở ví dụ, giá trị **instance-a** chỉ hợp lệ cho một instance cụ thể; trong Kubernetes/scale-out phải cung cấp prefix riêng theo pod/instance.

Khi transaction được bật, binder sử dụng chung transactional producer factory cho các output bindings. Các producer properties riêng của binding có thể bị bỏ qua; thuộc tính producer dùng chung được đặt dưới:

~~~text
spring.cloud.stream.kafka.binder.transaction.producer.*
~~~

Vì vậy, một thay đổi ở **spring.cloud.stream.kafka.bindings.validateOrder-out-0.producer.configuration** có thể không tác động tới transactional producer thực tế như người vận hành kỳ vọng.

Đừng nhầm Kafka transactional binder với giao dịch cơ sở dữ liệu hoặc với transaction manager do Spring Boot tự cấu hình cho một KafkaTemplate độc lập.

## 14. Prefix unique per instance khi deploy nhiều pod

Sai:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: orders-tx-
~~~

Nếu cả ba pod dùng cùng giá trị orders-tx- và mỗi factory sinh ra hậu tố giống nhau, các transactional IDs thực tế có thể đụng nhau và liên tục fence nhau.

Đúng về mặt nguyên tắc:

~~~text
pod order-service-a -> order-tx-order-service-a-
pod order-service-b -> order-tx-order-service-b-
pod order-service-c -> order-tx-order-service-c-
~~~

Cách cấp prefix có thể là environment variable được orchestrator inject, dùng pod name hoặc một instance identity chắc chắn không trùng giữa các pod active.

Ví dụ Kubernetes truyền tên pod vào biến môi trường:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0
          env:
            - name: INSTANCE_ID
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
~~~

Ứng dụng cần tạo prefix theo INSTANCE_ID ở cấu hình Spring trước khi xây producer factory; pod name ở trên chỉ là **nguồn identity**, không tự biến thành transaction prefix khi chưa được gán vào thuộc tính Spring Cloud Stream.

Chú ý lifecycle: nếu hai process cùng sử dụng một logical instance identity trong lúc failover, phải có chiến lược zombie fencing và kiểm soát overlap. Nếu mục tiêu là chạy nhiều active replicas song song, prefix không được trùng.

## 15. Cấu hình timeout cho transactional producer

Spring Cloud Stream cung cấp namespace producer chung khi transactional binder được bật. Ví dụ dạng khai báo thường dùng:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: order-validation-instance-a-
            producer:
              configuration:
                transaction.timeout.ms: 120000
                delivery.timeout.ms: 120000
                request.timeout.ms: 30000
~~~

Đây là cấu hình minh họa, không phải bộ giá trị production cố định. **transaction.timeout.ms** nằm trong Kafka producer configuration; **transaction.max.timeout.ms** nằm ở broker, không đặt dưới binder producer.

Khi cấu hình timeout:

- Transaction deadline phải bao trùm thời gian xử lý và commit thực tế với dự phòng.
- Delivery timeout áp dụng từng send, không thay transaction deadline.
- Request timeout áp dụng request/ack, không đồng nghĩa total time của function.
- Max block time có thể ảnh hưởng một số lời gọi transaction khi coordinator/metadata chậm.
- Tránh đặt transaction timeout dài vượt quá broker maximum.
- Đo P99/P99.9 theo workload và làm test broker disruption trước khi thay default.

Kiểm tra phiên bản binder để xác nhận các property trong **transaction.producer.configuration** được chuyển đúng vào Kafka producer factory thực tế; đừng chỉ đọc application.yml rồi suy là broker đã nhận cấu hình đó.

## 16. Spring Cloud Stream transactions khác Spring Boot KafkaTemplate transactions

Có hai đường thường gặp:

**Đường A — Spring Cloud Stream Kafka binder:** transaction được bật bằng **spring.cloud.stream.kafka.binder.transaction.transactionIdPrefix**, container của binder quản lý transaction khi consume-process-produce.

**Đường B — Spring Kafka/Spring Boot:** cấu hình **spring.kafka.producer.transaction-id-prefix** có thể làm Spring Boot tự tạo KafkaTransactionManager cho producer factory của Boot; sử dụng KafkaTemplate, @Transactional hoặc TransactionTemplate.

Hai đường này không tự động cùng một producer factory/transaction context. Cần biết record được gửi qua **StreamBridge/output binding** hay qua **KafkaTemplate** nào, và transaction manager tương ứng. Nếu lẫn lộn, output có thể gửi ngoài transaction đang quản lý offset input.

**Không đặt cả hai prefix rồi mặc định chúng hợp thành một transaction.** Kiểm tra bean/producer factory, thread context và binder selection cụ thể.

## 17. Retry và DLT khi Kafka binder đang transactional

Trong chế độ transactional, Spring Cloud Stream Kafka binder **không dùng retry và dead-lettering thông thường bên trong transaction gốc** theo cùng cách với nontransactional binder.

Lý do: nếu handler thất bại và transaction bị rollback, output record gửi trong transaction đó cũng rollback. Do đó, cơ chế retry/recovery phải được xử lý **sau rollback**.

Tài liệu binder mô tả:

- Các thuộc tính retry của consumer được dùng để cấu hình **DefaultAfterRollbackProcessor** khi bật transaction.
- Processor có thể seek/re-fetch record thất bại ở lần poll kế tiếp và áp backoff/recovery theo cấu hình.
- Khi gửi record lỗi sang DLT, thao tác recover được thực hiện theo cơ chế container, không coi DLT record trong transaction đã rollback là đã được lưu thành công.
- Offset của record đã recover có thể được commit trong **transaction mới** cùng thao tác recovery theo tùy chọn của binder.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: validation-service
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
      kafka:
        bindings:
          validateOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.validation-service.dlt
~~~

Đây là cấu hình retry/DLT cho **regular Kafka message binder**. Hành vi recovery thực tế, transaction manager và offset commit phải được kiểm chứng theo phiên bản Spring Cloud Stream/Spring Kafka đang dùng. Một custom error handler có thể thay đổi hoàn toàn luồng recovery.

## 18. txCommitRecovered và offset của record đã đưa vào DLT

Kafka binder có thuộc tính consumer **txCommitRecovered** dành cho transactional recovery. Tài liệu mô tả giá trị mặc định **true**: khi một record được xử lý thành công bằng recoverer (ví dụ đã vào DLT), offset của nó được commit thông qua một transaction mới.

Điều này nhằm tránh hiện tượng:

1. Handler thất bại và transaction chính rollback.
2. Recoverer publish record lỗi vào DLT.
3. Nhưng offset gốc chưa được đánh dấu đã recover.
4. Consumer đọc lại record gốc, tiếp tục publish thêm bản DLT trùng.

Không đặt **txCommitRecovered=false** chỉ để “cho chắc” nếu không hiểu rõ kịch bản replay. Khi tắt commit recovered, record có thể được xử lý lại theo chiến lược container và tạo duplicate.

Các câu hỏi phải kiểm thử:

- DLT publish có được broker ack thành công không?
- Khi publish DLT thất bại, offset gốc có còn để retry không?
- Nếu DLT thành công nhưng commit offset bị lỗi, có xử lý duplicate qua event ID không?
- DLT consumer có đọc ở isolation phù hợp không?
- Custom error handler có thay thế DefaultAfterRollbackProcessor hoặc recoverer mặc định không?

## 19. DefaultAfterRollbackProcessor và poison message

Spring Kafka sử dụng **DefaultAfterRollbackProcessor** để xử lý record sau rollback. Với record listener, processor có thể seek về record lỗi và những record chưa xử lý. Với batch listener, phạm vi replay thường lớn hơn vì container khó xác định chính xác record lỗi nếu không có thông tin bổ sung; phiên bản mới có cơ chế hỗ trợ batch recovery riêng.

Hãy chọn chính sách rõ:

| Chính sách | Khi nào dùng |
| --- | --- |
| Retry có giới hạn + backoff | Timeout ngắn, broker hoặc API ngoài tạm lỗi |
| Non-retryable + DLT | Lỗi schema, dữ liệu sai, business invariant |
| Quarantine | Record cần can thiệp thủ công hoặc nhạy cảm |
| Parking lot sau N lần replay | Tránh vòng lặp DLT → topic chính → DLT |
| Tạm dừng consumer và cảnh báo | Lỗi cấu hình hoặc downstream hỏng diện rộng |

Hãy tránh retry vô hạn một poison message làm partition không tiến. Mặt khác, đừng bỏ qua record lỗi im lặng rồi commit offset nếu nghiệp vụ yêu cầu audit và khả năng replay.

## 20. KafkaTemplate.executeInTransaction dùng cho local producer transaction

Khi sử dụng Spring Kafka trực tiếp thay vì transactional binder, KafkaTemplate có API transaction cục bộ:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class AuditPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public AuditPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishBoth(String eventId, String payload) {
        kafkaTemplate.executeInTransaction(operations -> {
            operations.send("orders.events", eventId, payload);
            operations.send("orders.audit", eventId, "published");
            return null;
        });
    }
}
~~~

Đoạn code giả định KafkaTemplate dùng transactional producer factory. Nếu callback hoàn tất, template commit; nếu ném exception, transaction rollback.

Lưu ý quan trọng:

- executeInTransaction tạo **local transaction** mới, không tự sử dụng một KafkaTransactionManager transaction đang active.
- Với consumer-triggered exactly-once read-process-write, không thay binder transaction bằng local transaction độc lập rồi giả định offset input cùng commit.
- Nếu producer bị fence, đóng producer; framework quản lý cache/factory mới theo lifecycle.
- Timeout hoặc lỗi commit cần reconciliation vì kết quả bên broker có thể không được caller xác nhận rõ.

## 21. Consumer isolation.level=read_committed

Để consumer không thấy record thuộc transaction đã abort, cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        consumeValidated-in-0:
          destination: orders.validated
          group: downstream-service
      kafka:
        bindings:
          consumeValidated-in-0:
            consumer:
              configuration:
                isolation.level: read_committed
~~~

Đây là consumer của **regular Kafka message binder**. Nếu consumer dùng read_uncommitted (mặc định Kafka), nó có thể quan sát record transactional đã bị abort.

### Last Stable Offset (LSO)

Trong read_committed, consumer chỉ đọc đến **LSO** — ranh giới trước transaction đang mở đầu tiên tại partition liên quan. Một transaction mở quá lâu có thể làm consumer read_committed dừng tiến ở một offset, dù high watermark còn cao hơn.

Sau commit/abort, LSO có thể tiến. Consumer cũng có thể thấy **lỗ hổng offset** do transaction markers hoặc record đã abort bị lọc. Đây không tự động là mất dữ liệu.

~~~text
Partition:
  offset 101: record đã commit
  offset 102: record thuộc transaction đang mở
  offset 103: record của producer khác
  offset 104: record của producer khác

read_committed: chưa thể đọc vượt qua transaction mở ở 102
read_uncommitted: có thể đọc record transactional chưa commit
~~~

Nếu lag của read_committed tăng bất thường, hãy kiểm tra transaction mở quá lâu trước khi tăng consumer concurrency hoặc phân vùng.

## 22. Không nhầm transaction timeout với max.poll.interval.ms

**max.poll.interval.ms** là giới hạn thời gian giữa các lần gọi poll của consumer group. Handler chạy quá lâu hoặc retry/backoff chặn poll có thể khiến consumer mất quyền sở hữu partition. Hệ quả có thể là rebalance, lỗi commit offset hoặc fencing ở những trường hợp liên quan membership.

**transaction.timeout.ms** là thời gian tồn tại transaction ở broker. Hai giới hạn độc lập nhưng cùng ảnh hưởng luồng consume-process-produce:

- Transaction deadline ngắn hơn thời gian xử lý → coordinator abort.
- Poll interval bị vượt → group có thể rebalance và consumer không còn là owner khi gửi offset.
- Cả hai xảy ra gần nhau → log có thể chứa nested exceptions, gây nhầm nguyên nhân.

Phương án xử lý: đo thời gian handler, đặt giới hạn HTTP/database calls, giảm batch size, chuyển công việc dài thành workflow bất đồng bộ, và điều chỉnh timeout theo số liệu thật. Đừng chỉ tăng max.poll.interval.ms trong khi transaction vẫn timeout ở 60 giây.

## 23. Producer epoch, commit failure và consumer rebalance

Trong một pipeline exactly-once, producer transaction và consumer group phối hợp để commit input offsets. Nếu consumer mất assignment hoặc group membership thay đổi, thao tác gửi offsets/commit có thể thất bại.

Triệu chứng cần đối chiếu:

| Log/Exception | Câu hỏi |
| --- | --- |
| ProducerFencedException | Có active producer khác dùng cùng transactional.id không? |
| InvalidProducerEpochException | Producer đang dùng epoch cũ hoặc session đã invalid không? |
| CommitFailedException | Consumer có bị mất membership/rebalance trước khi commit không? |
| FencedInstanceIdException | Static group.instance.id có bị trùng không? |
| TimeoutException trong sendOffsetsToTransaction | Coordinator/group metadata có trả lời trong max.block.ms không? |
| InvalidTxnTimeoutException | Producer có yêu cầu transaction timeout vượt broker maximum không? |

Không gộp các loại fencing thành cùng một nguyên nhân. **group.instance.id** trùng ảnh hưởng static consumer membership, khác với **transactional.id** trùng gây producer fencing. Chúng có thể cùng xuất hiện trong sự cố rolling update nhưng cách sửa khác nhau.

## 24. Kafka Streams binder có đường transaction riêng

Kafka Streams binder được xây trên Kafka Streams API, không dùng hoàn toàn cùng cách xử lý transaction như imperative Kafka message binder.

Để bật exactly-once trong Kafka Streams, cấu hình processing guarantee theo Kafka Streams API và phiên bản Kafka đang dùng, ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              processing.guarantee: exactly_once_v2
~~~

Đây là namespace **spring.cloud.stream.kafka.streams.binder.configuration**, không phải transactionIdPrefix của regular Kafka message binder.

Trong Kafka Streams:

- Streams runtime quản lý producer, tasks, offsets và transaction theo topology.
- Transaction timeout có thể đi kèm task migration, rebalance, state restore, commit interval hoặc broker transaction coordinator.
- Producer/task fenced có thể là một phần của failover; nếu liên tục xảy ra, kiểm tra instance identity, assignment, group membership, resource starvation và producer configuration.
- Không lấy lỗi Kafka Streams rồi áp ngay tùy chọn DefaultAfterRollbackProcessor của Kafka message listener; đây là hai runtime khác nhau.

Cần đo stream thread state, rebalance/restore duration, transaction abort/error metrics, changelog lag và broker transaction coordinator health.

## 25. Tại sao rollback Kafka không rollback database?

Giả sử function làm các bước:

1. Đọc OrderCreated từ Kafka.
2. Ghi database trạng thái VALIDATED.
3. Gửi OrderValidated qua Kafka output binding.
4. Kafka commitTransaction thất bại và rollback.

Database có thể đã commit dù Kafka output/offset không commit. Khi input được xử lý lại, database side effect có thể xảy ra lần nữa.

~~~mermaid
flowchart LR
  I[(Kafka input)] --> F[Function]
  F --> DB[(Database transaction)]
  F --> KT[(Kafka transaction)]
  KT -->|Abort| R[Kafka output và offset rollback]
  DB -->|Đã commit| S[Database không tự rollback]
~~~

Không coi @Transactional của database kết hợp Kafka binder transaction là một giao dịch phân tán ACID tự động. Cần chọn pattern như **transactional outbox**, **idempotent consumer/inbox**, reconciliation, hoặc kiến trúc saga/compensation tùy bài toán. Transaction synchronization giữa Kafka và DB cũng có crash window và cần xác minh thứ tự commit; không nên quảng bá như hai-phase commit toàn phần.

## 26. Phân loại exception trước khi retry

Một hướng phân loại mang tính vận hành:

| Nhóm | Ví dụ | Retry với cùng producer? | Hành động |
| --- | --- | --- | --- |
| Business invalid data | Validation failed | Không | Abort và route DLT/quarantine |
| Transient Kafka/network | Coordinator load, retryable transport | Theo client/runtime policy | Backoff; rollback/reprocess nếu cần |
| Transaction abortable state | Transaction phải abort nhưng producer còn hợp lệ | Không tiếp tục transaction đó | Abort theo framework rồi bắt đầu transaction mới |
| Producer fenced/fatal | ProducerFencedException, nhiều lỗi epoch/authorization | **Không** | Close producer; thay instance sau khi điều tra |
| Commit outcome chưa chắc chắn | Timeout khi commit response | Không được replay mù | Reconcile output/offset/idempotency trước hành động |

Kafka producer lỗi có thể được phân loại fatal, abortable hoặc retriable theo API và client version. Tránh viết catch(Exception) → abort → retry bằng cùng object cho tất cả lỗi. Cách đó có thể làm hỏng transactional state machine và che dấu mất dữ liệu.

## 27. Cây quyết định chẩn đoán nhanh

~~~mermaid
flowchart TD
  A[Nhận lỗi transaction] --> B{Có ProducerFencedException / InvalidProducerEpoch?}
  B -->|Có| C[Đóng producer cũ, điều tra trùng ID / zombie / expiry]
  B -->|Không| D{Có InvalidTxnTimeoutException?}
  D -->|Có| E[So producer transaction.timeout và broker max]
  D -->|Không| F{Có TimeoutException?}
  F -->|Có| G[Xác định call site: metadata, send, offset, commit, abort]
  F -->|Không| H{Business function ném exception?}
  H -->|Có| I[Rollback → after-rollback retry/DLT]
  H -->|Không| J[Kiểm tra group rebalance, coordinator và ACL]
  G --> K[Kiểm tra deadline, network, metrics, transaction outcome]
  C --> L[Không dùng lại producer bị fenced]
  E --> M[Chỉnh cấu hình và kiểm thử]
  I --> N[Không coi DLT trong transaction rollback là đã commit]
~~~

Khi xác định được nguyên nhân, xử lý tại lớp liên quan: transaction ID collision, timeout budget, consumer processing time, recovery policy hoặc broker availability. Không giải quyết đồng loạt bằng tăng retries.

## 28. Runbook 10 bước khi production báo rollback/fencing

1. **Khoanh vùng:** xác định app, pod, deployment, consumer group, input/output topics, partition, event ID và transactional ID nếu có.
2. **Đọc root exception:** phân biệt transaction deadline, max.block timeout, send failure, rebalance và fencing.
3. **Ghi mốc thời gian:** lúc begin, các sends, external calls, offsets transaction, commit/abort, container restart.
4. **Kiểm tra rollout:** tìm các active pods sử dụng trùng transaction prefix; kiểm tra orphan process và zombie.
5. **Đọc cấu hình thực tế:** Spring Cloud Stream binder transaction prefix, transaction.producer.*, Kafka client timeouts, broker transaction.max.timeout.ms, isolation.level.
6. **Kiểm tra broker:** coordinator availability, authentication/ACL, ISR và network latency.
7. **Đối chiếu read_committed:** output record được commit hay đã abort, LSO có bị chặn không.
8. **Kiểm tra input offset:** consumer group commit tiến chưa, record có đang được re-fetch không.
9. **Xác minh DLT/recovery:** DLT record có tồn tại và offset recovered đã commit theo chính sách không.
10. **Khôi phục có kiểm soát:** sửa prefix/timeout/code, tạo producer mới khi cần, replay bằng event ID/idempotency; ghi kết quả runbook.

Nếu kết quả commit không chắc chắn, không phát lại message một cách thủ công trước khi kiểm tra trạng thái Kafka và dữ liệu nghiệp vụ. Việc restart hàng loạt pod cũng có thể tạo collision/rebalance mới.

## 29. Log và metric cần thu thập

Nên log theo cấu trúc, tránh in secret hoặc payload nhạy cảm:

- App instance/pod ID, transaction prefix (được rút gọn khi cần), group ID.
- Topic/partition/offset của input và output.
- Event ID, correlation ID, trace ID nếu có.
- Exception class, root cause và stack trace.
- Thời gian xử lý function, thời gian chờ downstream, transaction duration.
- Số lần rollback, abort, producer fencing, retry, DLT publish.
- Kafka producer error/commit/abort metrics theo client/producer factory.
- Consumer lag, rebalance count, poll interval và assignment.
- Broker transaction coordinator error rate, transaction timeout và replication health.
- Read_committed progress/LSO, nếu có công cụ hỗ trợ.

Không đưa **transactional.id** thành high-cardinality metric tag trên toàn bộ producer instances khi có thể dùng tag ổn định; lưu ID cụ thể trong logs/traces có kiểm soát. Tránh log toàn bộ transaction headers hoặc dữ liệu cá nhân.

## 30. Lệnh CLI kiểm tra consumer offset và visibility

Ví dụ xem group progress:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --group validation-service \
  --describe
~~~

Đọc output topic bằng consumer **read_committed**:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server kafka:9092 \
  --topic orders.validated \
  --from-beginning \
  --consumer-property isolation.level=read_committed
~~~

So sánh với một consumer **read_uncommitted** trong môi trường test:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server kafka:9092 \
  --topic orders.validated \
  --from-beginning \
  --consumer-property isolation.level=read_uncommitted
~~~

Nếu record xuất hiện với read_uncommitted nhưng không xuất hiện với read_committed, có thể liên quan transaction abort hoặc transaction còn mở. Đừng kết luận ngay mà chưa xem transaction lifecycle, offset và markers. Khi test ở production, giới hạn thời gian, số record đọc và quyền ACL; tránh dùng một lệnh console chạy vô hạn vào topic nhạy cảm.

## 31. Ma trận fault injection bắt buộc

| Kịch bản test | Điều quan sát | Kết quả mong đợi |
| --- | --- | --- |
| Function ném exception trước send | Retry/DLT, input offset | Transaction abort; input được retry hoặc recover theo policy |
| Function ném exception sau send nhưng trước commit | Output read_committed | Output trong transaction abort không xuất hiện |
| Handler chậm hơn transaction.timeout.ms | Broker abort, commit exception | Không commit transaction hết hạn; có đường recovery |
| Producer timeout vượt broker max | Startup/initTransactions | Nhận lỗi cấu hình rõ, không loop mù |
| Hai active pods dùng trùng prefix | Producer epoch/fenced logs | Producer cũ bị fence; sửa identity |
| Producer idle vượt expiration | Producer cache reuse | Xác minh maxAge/expiry hoặc tạo producer mới |
| Broker mất sau send trước commit response | Kết quả commit chưa chắc chắn | Không replay mù; reconciliation/idempotency |
| Consumer rebalance trong handler dài | Offset commit, group state | Failure/retry theo đúng listener semantics |
| DLT publish failure | Offset gốc, DLT records | Không âm thầm mất message |
| DB commit trước Kafka abort | DB + Kafka output | Duplicate khi replay được idempotency xử lý |
| Kafka Streams task migration | Stream state/assignment | EOS processing tiếp tục sau failover phù hợp |
| Output consumer read_uncommitted | Aborted output visibility | Phơi bày rủi ro đọc dữ liệu chưa commit |

Dùng Testcontainers hoặc broker test thật để kiểm tra transaction coordinator, producer epoch và read_committed. Test Binder của Spring Cloud Stream chỉ kiểm tra function/binding behavior, không thể chứng minh Kafka transaction thật sự commit/abort.

### Gợi ý một test tích hợp

1. Khởi động Kafka test broker và tạo hai topic input/output có cấu hình giao dịch phù hợp.
2. Bật transactional binder với prefix riêng của instance.
3. Gửi event E1 thành công, xác minh output read_committed thấy V1 và input offset tiến.
4. Với E2, cho function ném exception sau khi đã tạo output; xác minh V2 không hiện ở read_committed.
5. Tạm ngắt broker hoặc chặn commit response, quan sát exception và xác minh transaction outcome bằng một consumer độc lập.
6. Cho hai producer cùng transactional.id trong một test thấp tầng riêng; xác minh producer cũ bị fence và phải đóng.
7. Phục hồi broker, xác minh retry/DLT, offset và side effect không bị nhân bản.

Không dùng sleep cố định làm bằng chứng. Dùng Awaitility, bounded polling, timeout và assertion trên output/offset.

## 32. Các lỗi xử lý thường gặp

| Phản ứng sai | Vì sao nguy hiểm | Thay bằng |
| --- | --- | --- |
| Tăng mọi timeout lên 30 phút | Giữ transaction mở lâu, có thể chặn LSO/read_committed | Đo bottleneck và chọn deadline có ngân sách |
| Retry bằng producer đã bị fenced | Session đã bị broker vô hiệu hóa | Close producer và tạo session mới phù hợp |
| Dùng cùng transaction prefix cho mọi replica | Collision, fencing liên tục | Prefix unique per live instance |
| Retry/DLT ngay trong transaction sẽ rollback | DLT record cũng có thể bị abort | Recovery sau rollback, transaction mới khi cần |
| Đánh dấu input đã xử lý khi DLT publish thất bại | Mất khả năng phục hồi record | Kiểm tra recoverer + offset commit semantics |
| Đọc output bằng read_uncommitted | Có thể thấy aborted records | Dùng read_committed khi yêu cầu |
| @Transactional DB được hiểu là Kafka+DB atomic | Hai hệ thống commit độc lập | Outbox/inbox, reconciliation, idempotency |
| Trộn Boot KafkaTemplate transaction với binder transaction | Producer factories không cùng context | Xác nhận bean/manager/transaction boundary |
| Tăng max.poll.interval.ms để sửa mọi timeout | Không thay broker transaction deadline | Đo và sửa đúng timeout |
| Coi TimeoutException của commit là abort chắc chắn | Commit outcome có thể chưa rõ | Reconciliation, idempotency trước replay |
| Tạo transaction ID mới cho từng event | Tốn identity/resources, không giải quyết root cause | Prefix theo producer instance, suffix do factory quản lý |
| Dùng Kafka Streams settings cho message binder | Hai binder/runtime khác nhau | Cấu hình theo đúng loại binder |

## 33. Checklist production cho Kafka transactional workloads

- Xác định rõ transactional binder hay Kafka Streams EOS.
- Bật transaction trên đúng binder và producer factory.
- Cấp transaction ID prefix unique cho mỗi active instance.
- Theo dõi rolling deployment overlap, zombie và producer cache expiry.
- Cấu hình timeout dựa trên thời gian xử lý thực tế; kiểm tra broker maximum.
- Phân loại transaction timeout, max.block, delivery và max.poll riêng.
- Dùng read_committed cho consumer cần tránh aborted output.
- Cấu hình DefaultAfterRollbackProcessor/retry và DLT theo mode transactional.
- Kiểm tra txCommitRecovered trước khi chọn replay policy.
- Không swallow fatal fencing/epoch exceptions.
- Đảm bảo producer đã fenced được close, không dùng tiếp.
- Xác minh DLT publish, input offset và output visibility bằng broker integration test.
- Thiết kế idempotency cho database/HTTP side effect.
- Theo dõi transaction duration, abort/fence counts, lag và LSO.
- Có runbook xử lý commit outcome chưa chắc chắn trước khi replay.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.0 — Kafka Transactional Binder](https://docs.spring.io/spring-cloud-stream/reference/5.0/kafka/kafka-binder/transactional.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka — After Rollback Processor](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html#after-rollback-processor)
- [Apache Kafka 4.2 — Producer Configs](https://kafka.apache.org/42/configuration/producer-configs/)
- [Apache Kafka 4.2 — Broker Configs](https://kafka.apache.org/42/configuration/broker-configs/)
- [Apache Kafka 4.2 — KafkaConsumer read_committed](https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html)
- [Apache Kafka 4.2 — ProducerFencedException API](https://kafka.apache.org/42/javadoc/org/apache/kafka/common/errors/ProducerFencedException.html)
- [Apache Kafka 4.2 — KafkaProducer transaction API](https://kafka.apache.org/42/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html)
- [Spring Cloud Stream — Kafka Streams Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)

API, default và transactional error classification có thể thay đổi giữa các phiên bản Kafka client, Spring Kafka, Spring Cloud Stream và Kafka Streams. Hãy đối chiếu đúng release train/BOM và cấu hình broker đang chạy trước khi áp dụng quy trình recovery vào production.

## Kết luận

**Rollback** có thể là cách đúng để bảo vệ tính nhất quán của input offset và output Kafka record khi xử lý thất bại. **Timeout** cần xác định đúng loại: transaction deadline, producer blocking/delivery hoặc consumer poll. **Producer fencing** là cơ chế bảo vệ broker trước producer session cũ, không phải lỗi có thể retry bằng chính producer đã bị fence.

Trong Spring Cloud Stream Kafka transactional binder, offset input và output records có thể được commit cùng transaction khi xử lý đúng consumer thread/producer context; retry/DLT cần được tổ chức sau rollback. Với Kafka Streams, EOS được cấu hình ở runtime riêng. Chẩn đoán an toàn cần so sánh logs, transaction ID/prefix, producer epoch, timeout budget, read_committed visibility, DLT và input offsets, đồng thời thiết kế idempotency vì side effects ngoài Kafka không tự rollback cùng transaction.
