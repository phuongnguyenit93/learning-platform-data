# Transaction id duy nhất theo instance

## 1. Vì sao transaction ID phải duy nhất theo instance?

Kafka hỗ trợ producer transaction để nhóm nhiều bản ghi gửi vào Kafka và, trong luồng consume–process–produce, phối hợp cả offset consumer với output record trong cùng một giao dịch. Thành phần nhận diện một **transactional producer logic** với Kafka broker là `transactional.id`.

Khi triển khai ứng dụng Spring Kafka trên nhiều JVM, container hoặc Kubernetes pod, mỗi instance có thể tạo các producer transaction riêng. **Những producer hoạt động đồng thời và độc lập không được vô tình sử dụng trùng `transactional.id`.** Nếu chúng trùng ID, Kafka sẽ coi producer đến sau là thế hệ mới của producer logic đó; producer cũ có thể bị *fence* (tước quyền thực hiện giao dịch), gây lỗi gửi hoặc commit.

Đối với Spring Kafka, cách cấu hình quen thuộc là cấp **`transactionIdPrefix` duy nhất cho mỗi instance**. `DefaultKafkaProducerFactory` sử dụng prefix này để tạo các `transactional.id` cụ thể, với suffix được factory quản lý cho các producer trong instance.

~~~text
Ứng dụng billing, chạy 3 instance

Instance A (prefix: billing-tx-a-)
  Producer 1 -> transactional.id: billing-tx-a-0
  Producer 2 -> transactional.id: billing-tx-a-1

Instance B (prefix: billing-tx-b-)
  Producer 1 -> transactional.id: billing-tx-b-0
  Producer 2 -> transactional.id: billing-tx-b-1

Instance C (prefix: billing-tx-c-)
  Producer 1 -> transactional.id: billing-tx-c-0

Không trùng ID giữa các producer đang hoạt động.
~~~

Suffix trong sơ đồ là ví dụ minh họa; thuật toán và cách cấp suffix phụ thuộc phiên bản Spring Kafka, producer factory và cấu hình `TransactionIdSuffixStrategy`. Điều quan trọng là **toàn bộ ID tạo ra cho các instance đồng thời phải không xung đột**.

### 1.1. Mục tiêu của bài học

Trong vận hành Exactly once với Spring Kafka, cần hiểu:

- `transactional.id` khác gì với `client.id`, `group.id` và business event ID.
- Vì sao Kafka producer fencing là cơ chế an toàn có chủ đích nhưng cũng là dấu hiệu lỗi cấu hình khi hai instance tranh cùng ID.
- Cách cấp `transaction-id-prefix` cho mỗi instance qua Spring Boot và Kubernetes.
- Cách bảo đảm uniqueness khi tăng replica, rolling update, restart và scale down/up.
- Cách nhận biết fencing và điều tra các lỗi transaction.
- Vì sao unique ID là **điều kiện cần** của transactional producer, không phải lời hứa exactly once cho side effect ngoài Kafka.

## 2. Transactional producer được định danh thế nào?

### 2.1. transactional.id là danh tính logic

Kafka client cấu hình `transactional.id` để bật giao thức transactional producer. Khi một producer khởi tạo giao dịch, broker transaction coordinator theo dõi danh tính logic này và cấp thông tin producer ID/epoch phù hợp.

Một ứng dụng có thể lần lượt mở nhiều Kafka transactions với cùng một transactional producer, nhưng không được mở những giao dịch chồng lấn tùy ý trên cùng producer. Kafka transaction API có lifecycle:

~~~text
initTransactions
      |
      v
beginTransaction
      |
      +---- send(record A)
      +---- send(record B)
      |
      v
commitTransaction
      |
      v
beginTransaction (giao dịch kế tiếp)
~~~

Hoặc, khi xảy ra lỗi có thể rollback:

~~~text
beginTransaction
      |
      +---- send(record A)
      +---- xử lý lỗi
      |
      v
abortTransaction
~~~

`transactional.id` được dùng xuyên các lần transaction của cùng producer logic, không đổi theo từng event hoặc mỗi lời gọi send.

### 2.2. Producer ID và epoch

Broker sử dụng producer ID và epoch để phân biệt các thế hệ producer. Khi một producer mới khởi tạo với cùng `transactional.id`, coordinator có thể nâng epoch và làm producer cũ mất quyền sử dụng danh tính đó.

~~~mermaid
sequenceDiagram
    participant A as Producer A
    participant K as Kafka coordinator
    participant B as Producer B

    A->>K: initTransactions với ID billing-tx-7
    K-->>A: Cấp PID / epoch n
    A->>K: beginTransaction + send
    B->>K: initTransactions cùng ID billing-tx-7
    K-->>B: Cấp epoch mới theo protocol
    A->>K: commitTransaction bằng epoch cũ
    K-->>A: Producer fenced / invalid epoch
    B->>K: Giao dịch bằng epoch mới
~~~

Đây là **producer fencing**. Kafka dùng nó để ngăn hai thế hệ producer cùng tuyên bố quyền sở hữu một transactional ID và tạo kết quả không nhất quán.

Fencing không phải một cơ chế phân tải. Kafka không chia một transactional ID chung cho nhiều instance để tăng concurrency. Mỗi transactional producer đang hoạt động cần danh tính hợp lệ riêng.

## 3. Vì sao trùng ID thường xuất hiện khi scale?

Giả sử dịch vụ `orders-worker` chạy ba pod với cùng cấu hình:

~~~properties
spring.kafka.producer.transaction-id-prefix=orders-tx-
~~~

Nếu mỗi pod tạo producer factory riêng, các factory có thể sinh những suffix trùng nhau, chẳng hạn producer đầu tiên của cả ba pod cùng dùng một ID kết thúc bằng `0`.

~~~text
Pod A -> orders-tx-0
Pod B -> orders-tx-0
Pod C -> orders-tx-0

Tất cả cùng initTransactions...
=> Producer cũ có thể liên tục bị fencing.
=> Listener transaction rollback, lag tăng, ứng dụng không ổn định.
~~~

Cấu hình này có thể **chạy bình thường khi chỉ có một instance**, nhưng lỗi xuất hiện sau khi:

- Tăng replica từ 1 lên 2.
- Rolling deployment chạy đồng thời pod cũ và pod mới.
- Một process cũ chưa dừng hoàn toàn nhưng replacement đã khởi động.
- Hai môi trường hoặc hai ứng dụng dùng chung Kafka cluster và trùng prefix.
- Một số container factory độc lập dùng chung prefix mà không có cơ chế cấp suffix tránh va chạm.

Do vậy, uniqueness phải được đánh giá ở **phạm vi Kafka cluster và các transactional producers có thể hoạt động đồng thời**, không chỉ trong một JVM.

## 4. Prefix và suffix trong Spring Kafka

### 4.1. transactionIdPrefix

Trong Spring Kafka, `DefaultKafkaProducerFactory` có thể được cấu hình bằng `setTransactionIdPrefix(...)`. Khi có prefix, factory tạo transactional producers và quản lý việc sử dụng chúng cho Kafka transactions.

Ví dụ:

~~~java
@Bean
public ProducerFactory<String, OrderEvent> orderProducerFactory(
    KafkaProperties kafkaProperties
) {
    Map<String, Object> configs =
        kafkaProperties.buildProducerProperties();

    DefaultKafkaProducerFactory<String, OrderEvent> factory =
        new DefaultKafkaProducerFactory<>(configs);

    factory.setTransactionIdPrefix("orders-tx-instance-a-");

    return factory;
}
~~~

Ví dụ hướng đến một producer factory quản lý transactional producers cho instance A. Nếu dùng Spring Boot, có thể để auto-configuration làm việc thay vì tự tạo factory, miễn là cấu hình prefix đã được truyền đúng.

### 4.2. Suffix không phải ID độc lập giữa các pod

Factory quản lý suffix giúp nhiều producer trong **cùng factory** có thể hoạt động mà không trùng transactional ID. Nhưng cơ chế suffix của JVM A không tự phối hợp với JVM B.

Vì vậy, không dựa vào việc factory tự thêm `-0`, `-1` để cho rằng mọi pod đã có ID duy nhất.

~~~text
prefix riêng từng instance + suffix do factory quản lý
                    |
                    v
         transactional.id duy nhất
~~~

Trong các phiên bản Spring Kafka mới, cơ chế cấp suffix có thể cấu hình với `TransactionIdSuffixStrategy` và cache; cần tham khảo API tương ứng của phiên bản đang dùng. Nếu tự xây dựng suffix strategy, phải bảo đảm thread safety, không cấp trùng ID cho producer đang active và không bỏ qua giới hạn producer cache.

### 4.3. Không tự thay transaction ID theo từng event

Một lỗi thiết kế khác là ghép event ID hoặc offset vào transactional ID cho mỗi event:

~~~text
Không nên tạo producer mới cho từng event:
  orders-tx-event-10001
  orders-tx-event-10002
  orders-tx-event-10003
  ...
~~~

`transactional.id` định danh producer logic, không phải record. Tạo producer mới và ID mới cho mỗi record gây chi phí init transaction, metadata và lifecycle lớn, đồng thời làm khó quản lý timeout, cache và fencing.

Dùng event ID trong payload/header để hỗ trợ business idempotency; dùng transaction ID prefix phù hợp để quản lý producer transaction.

## 5. Cấu hình Spring Boot theo instance

### 5.1. application.yml

Một cấu hình mẫu:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: "orders-tx-instance-a-"
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      enable-auto-commit: false
      isolation-level: read_committed
~~~

Giá trị `orders-tx-instance-a-` phải được thay bằng danh tính instance thực tế ở deployment. Không commit một giá trị cố định như vậy vào cấu hình chung rồi scale nhiều bản sao mà không override nó.

`spring.kafka.consumer.isolation-level` chỉ ảnh hưởng các consumer được cấu hình bằng property đó, không tự thay đổi tất cả consumer của hệ thống. Các dịch vụ downstream muốn tránh nhìn thấy aborted records cũng cần dùng `read_committed`.

### 5.2. Inject prefix qua biến môi trường

Spring Boot có thể nhận property từ environment variable tương ứng:

~~~text
SPRING_KAFKA_PRODUCER_TRANSACTION_ID_PREFIX=orders-tx-instance-a-
~~~

Ở môi trường khác hoặc instance khác:

~~~text
Instance B:
SPRING_KAFKA_PRODUCER_TRANSACTION_ID_PREFIX=orders-tx-instance-b-

Instance C:
SPRING_KAFKA_PRODUCER_TRANSACTION_ID_PREFIX=orders-tx-instance-c-
~~~

Cách này giúp dùng cùng một artifact nhưng cấp danh tính phù hợp khi triển khai. Nên xác nhận giá trị hiệu lực bằng startup logs có kiểm soát hoặc công cụ kiểm tra cấu hình, không ghi secret hay toàn bộ Kafka properties vào log.

### 5.3. Dùng identity nào?

Có nhiều lựa chọn, mỗi lựa chọn có đánh đổi:

| Identity | Ưu điểm | Điểm cần chú ý |
|---|---|---|
| Pod UID | Duy nhất cho vòng đời pod | Pod replacement có UID khác; không tự fence producer cũ bằng cùng ID |
| Pod name | Dễ theo dõi trong log | Phải kiểm tra uniqueness và rolling overlap |
| StatefulSet ordinal | Ổn định qua restart của slot | Cần bảo đảm không có hai process cùng sở hữu slot đồng thời |
| Instance ID do orchestrator cấp | Có thể kiểm soát và truy vết | Cần service cấp ID không va chạm |
| Random UUID khi start | Dễ tạo uniqueness | Không duy trì cùng logical ID qua restart và không fence zombie bằng ID cũ |

**Quy tắc bắt buộc là không va chạm giữa các producer độc lập đang chạy đồng thời.** Việc ổn định ID giữa các lần restart còn phụ thuộc kiến trúc failover, mục tiêu fencing và cách Spring Kafka/Kafka client quản lý state.

Không nên khẳng định “UUID ngẫu nhiên là đủ cho mọi exactly once use case”: ID thay đổi mỗi lần khởi động không cung cấp fencing cho producer cũ bằng cùng danh tính logic. Với worker xử lý partition cố định hoặc dùng cơ chế ownership riêng, cần đánh giá cả danh tính logical owner và producer fencing.

## 6. Ví dụ Kubernetes: cấp prefix từ Pod UID

Trong Kubernetes, có thể dùng Downward API đưa `metadata.uid` vào environment variable và dùng nó trong prefix.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-consumer
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-consumer
  template:
    metadata:
      labels:
        app: orders-consumer
    spec:
      containers:
        - name: app
          image: example/orders-consumer:1.0.0
          env:
            - name: POD_UID
              valueFrom:
                fieldRef:
                  fieldPath: metadata.uid
            - name: SPRING_KAFKA_PRODUCER_TRANSACTION_ID_PREFIX
              value: "orders-tx-$(POD_UID)-"
~~~

Kubernetes hỗ trợ tham chiếu env đã khai báo bằng cú pháp `$(POD_UID)` trong giá trị của env phía sau. Pod UID là định danh duy nhất cho vòng đời pod; mỗi pod trong Deployment sẽ có prefix khác nhau.

Ví dụ:

~~~text
Pod A UID: 2f8a...
  prefix: orders-tx-2f8a...-

Pod B UID: 7b1c...
  prefix: orders-tx-7b1c...-

Pod C UID: d64e...
  prefix: orders-tx-d64e...-
~~~

Lưu ý: ví dụ đảm bảo **unique ID giữa các pod hiện tại**, nhưng vì pod thay thế nhận UID mới nên nó **không cố ý tái sử dụng transactional ID của pod cũ để fence producer cũ**. Đối với luồng cần zombie fencing qua một logical owner ổn định, phải xem thêm strategy định danh theo owner, consumer group generation và EOS của phiên bản Kafka/Spring Kafka đang chạy.

Nếu ứng dụng dùng Kubernetes Deployment với rollout overlap, phải tính cả pod cũ và pod mới cùng tồn tại trong giai đoạn cập nhật. Đảm bảo giá trị prefix không bị rút ngắn gây va chạm và không có middleware override cùng một biến môi trường cho mọi pod.

## 7. Unique per instance khác với stable across restart

Đây là hai yêu cầu liên quan nhưng không đồng nhất.

### 7.1. Unique giữa các instance đang hoạt động

Bất kỳ hai transactional producers độc lập **đang chạy đồng thời** đều cần tránh cùng một transactional ID. Việc này ngăn chúng tranh epoch và fence nhau không mong muốn.

Một prefix chứa Pod UID thường giải quyết tốt yêu cầu uniqueness cho deployment thông thường.

### 7.2. Stable cho cùng logical owner khi cần fencing

Nếu một logical worker bị crash rồi một worker khác tiếp quản đúng vai trò đó, việc tái sử dụng cùng transactional ID logic có thể giúp Kafka fence producer cũ nếu producer cũ vẫn còn hoạt động. Đây là lợi ích quan trọng của transactional ID ổn định trong các thiết kế ownership/failover.

~~~text
Logical worker slot 7

Old process (zombie):
  transactional.id = job-slot-7

New process tiếp quản slot 7:
  transactional.id = job-slot-7
  -> khởi tạo epoch mới
  -> producer cũ bị fenced
~~~

Nhưng nếu hai process có ý định hoạt động độc lập cùng lúc, chúng **không nên** cùng sử dụng ID đó. Không thể dùng một ID đồng thời cho hai ownership độc lập rồi xem các lỗi fencing là bình thường.

### 7.3. Cách lựa chọn thực tế

- Dịch vụ có nhiều pod xử lý các assignment linh hoạt: cần uniqueness giữa các pod và phù hợp consumer group/EOS version.
- Worker slot cố định cần fence zombie khi failover: thiết kế ID ổn định theo logical owner, cùng cơ chế leader/ownership an toàn.
- Rolling deployment có overlap: phải xác định rõ bản mới đang thay thế cùng owner hay là instance độc lập.
- Không dùng `client.id` hoặc `group.instance.id` như một cơ chế thay thế cho transactional ID.

Các chi tiết fencing của consume–process–produce hiện đại còn phụ thuộc Kafka consumer group metadata và EOS mode, không chỉ phụ thuộc chuỗi prefix. Kiểm tra tài liệu đúng phiên bản khi thiết kế failover đặc thù.

## 8. Phân biệt các định danh thường bị nhầm

| Thuộc tính | Phạm vi | Mục đích |
|---|---|---|
| `transactional.id` | Transactional producer | Fencing và quản lý transaction state |
| `transactionIdPrefix` | Spring Kafka ProducerFactory | Sinh ra các transactional IDs cho producer do factory quản lý |
| `client.id` | Kafka client | Định danh client trong log, metrics và requests |
| `group.id` | Consumer group | Phân phối partition và lưu committed offsets |
| `group.instance.id` | Static consumer membership | Định danh member ổn định trong group |
| Producer ID/epoch | Kafka protocol | Nhận diện producer generation và fencing |
| Business event ID | Event nghiệp vụ | Deduplication/idempotency của side effect |

Ví dụ:

~~~text
client.id        = orders-consumer-pod-a-0
group.id         = orders-service
group.instance.id= orders-slot-a (nếu dùng static membership)
transactional.id = orders-tx-pod-a-0
event.id         = evt-408219
~~~

Các giá trị có thể chứa một phần identity chung để dễ truy vết, nhưng **không cùng chức năng**. Đổi group ID làm thay đổi consumer offset namespace; nó không tự giải quyết producer fencing. Ngược lại, đổi transactional ID prefix không phải thao tác reset consumer offsets.

## 9. Transactional listener và exactly-once Kafka-to-Kafka

Trong Spring Kafka, transactional listener container có thể mở Kafka transaction quanh quá trình tiêu thụ và xử lý record. Output record qua KafkaTemplate và offset consumer đã xử lý có thể tham gia cùng transaction.

~~~mermaid
flowchart TD
    A[Input record tại topic nguồn] --> B[Transactional listener container]
    B --> C[Business transform]
    C --> D[KafkaTemplate gửi output]
    D --> E[Thêm source offset vào transaction]
    E --> F{Commit Kafka transaction?}
    F -->|Thành công| G[Output và source offset cùng được commit]
    F -->|Abort| H[Output bị abort và source offset không được commit]
    H --> I[Record nguồn có thể được giao lại]
~~~

Khi áp dụng đúng Kafka transactions và consumer `read_committed`, luồng Kafka-to-Kafka có thể đạt exactly-once semantics ở phạm vi Kafka. Nhưng **uniqueness của transactional ID chỉ là một điều kiện** trong thiết kế đó.

Còn cần:

- Transactional ProducerFactory và KafkaTemplate dùng đúng factory.
- Listener container được cấu hình Kafka transaction manager đúng phiên bản.
- Source offsets được gửi vào transaction trong consume–process–produce.
- Consumer downstream chọn `read_committed` nếu cần tránh aborted output.
- Retry/rollback xử lý exception đúng semantics.
- Không có side effect ngoài Kafka không được bảo vệ idempotency.

### 9.1. KafkaTransactionManager

Một bean minh họa:

~~~java
@Bean
public KafkaTransactionManager<String, OrderResult>
        kafkaTransactionManager(
            ProducerFactory<String, OrderResult> producerFactory
        ) {
    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Đây là manager cho producer factory transactional. Nếu ứng dụng có nhiều KafkaTemplate/ProducerFactory, cần bảo đảm manager dùng cùng factory với template phát output.

### 9.2. Gắn transaction manager vào listener container

Trong Spring Kafka version hỗ trợ API Kafka-aware:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCommand>
        transactionalListenerContainerFactory(
            ConsumerFactory<String, OrderCommand> consumerFactory,
            KafkaTransactionManager<String, OrderResult> kafkaTxManager
        ) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCommand>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
        .setKafkaAwareTransactionManager(kafkaTxManager);

    return factory;
}
~~~

API và kiểu transaction manager của container thay đổi theo phiên bản Spring Kafka. Phiên bản cũ có thể dùng setter khác. Đối chiếu Javadoc đúng version và xác nhận listener sử dụng factory này.

Với Spring Kafka 3.x, EOS V2 là cơ chế exactly-once được hỗ trợ; ở những phiên bản cũ hơn có thể gặp tài liệu nói về EOS V1. Đừng áp dụng nguyên xi chiến lược ID gắn theo topic-partition của một phiên bản cũ cho deployment hiện tại.

## 10. Vì sao transaction ID không được chia sẻ giữa các producer độc lập?

Giả sử cả Pod A và Pod B dùng ID `orders-tx-0`:

~~~text
Time T1:
  A initTransactions -> epoch 1
  A begin transaction, gửi event A

Time T2:
  B initTransactions -> epoch 2
  B bắt đầu transaction với cùng transactional.id

Time T3:
  A commit -> broker từ chối vì epoch cũ
  A nhận producer fencing / invalid epoch

Time T4:
  B vẫn tiếp tục theo epoch mới
~~~

Hệ quả vận hành có thể là:

1. Transaction của A abort hoặc không commit thành công.
2. Listener A gặp exception và phải rollback/redeliver input.
3. Lag tăng vì các giao dịch không hoàn tất.
4. A restart, tạo producer mới cùng ID, lại fence B.
5. Hai pod rơi vào vòng lặp fencing lẫn nhau.

Lỗi này không giải quyết bằng việc đặt `acks=all`, tăng retry count hoặc tăng `transaction.timeout.ms`. Phải sửa nguồn tạo transactional ID hoặc cơ chế ownership.

Trong một số kiến trúc failover, việc instance mới cố ý sử dụng cùng ID để fence instance cũ là hợp lệ. Điểm quyết định là **chỉ một owner hợp lệ được phép tiếp tục**; không phải hai pod hoạt động đồng thời như các worker độc lập.

## 11. Producer fencing không phải consumer rebalance

Producer fencing và consumer rebalance liên quan đến độ tin cậy nhưng thuộc hai cơ chế khác nhau:

- **Rebalance** thay đổi partition assignment giữa các consumer member trong một group.
- **Fencing** từ chối producer generation cũ khi transactional identity bị thay thế.

Một consumer bị revoke partition có thể vẫn đang thực thi code bất đồng bộ nếu ứng dụng tự tạo thread nền. Kafka group assignment không tự dừng side effect ngoài Kafka của thread đó. Transactional producer fencing cũng không tự rollback database transaction đã commit.

Đối với xử lý song song:

- Theo dõi công việc theo `TopicPartition`.
- Dừng hoặc hủy task của partition đã revoke theo deadline.
- Để transaction của owner cũ kết thúc đúng protocol.
- Không giao external side effect cho thread nền rồi commit source offset trước khi task bền vững.
- Dùng event ID, inbox hoặc idempotent operations để bảo vệ side effect.

Trong EOS V2, Kafka dùng thông tin consumer group metadata phù hợp khi gửi offsets vào transaction. Transaction ID uniqueness vẫn quan trọng, nhưng fencing còn liên quan đến generation/ownership của consumer group.

## 12. Lỗi xảy ra khi rollout Kubernetes

### 12.1. RollingUpdate

RollingUpdate thường tạo pod mới trước khi pod cũ hoàn toàn dừng. Nếu cả hai dùng prefix cố định, chúng có thể đồng thời khởi tạo producer trùng transactional ID.

~~~text
T0: Pod old đang chạy, prefix orders-tx-
T1: Pod new khởi động, prefix orders-tx-
T2: Cả hai tạo orders-tx-0
T3: Fencing lỗi trong thời gian overlap
~~~

Dùng prefix unique theo instance giải quyết va chạm không mong muốn này. Nếu thiết kế cần kế thừa logical identity để fence old owner, phải kiểm soát readiness, shutdown và ownership, không chỉ dựa vào suffix tự sinh.

### 12.2. CrashLoopBackOff

Nếu một pod liên tục gặp ProducerFencedException rồi restart, mỗi lần restart nó có thể tiếp tục dùng ID trùng với pod khác. CrashLoop sẽ không tự chữa được cấu hình uniqueness.

Cần xác định:

- Pod nào đang dùng cùng prefix.
- Factory nào tạo transactional producer.
- Prefix có được inject đúng vào pod không.
- Có container factory hoặc bean tùy chỉnh ghi đè property không.
- Có ứng dụng khác kết nối cùng Kafka cluster và prefix trùng không.

### 12.3. HPA autoscaling

Khi HPA tăng replica, mỗi replica tạo thêm consumer threads và transactional producers. Prefix unique bảo vệ ID, nhưng số producer giao dịch đồng thời cũng tăng.

Đừng chỉ đặt prefix khác nhau rồi quên tài nguyên broker. Cần theo dõi transaction coordinator latency, producer cache, consumer lag và error rate.

### 12.4. StatefulSet

StatefulSet ordinal ổn định giúp tạo danh tính theo slot, chẳng hạn `orders-tx-slot-0-` và `orders-tx-slot-1-`. Cách này có thể phù hợp nếu mỗi slot chỉ có một owner hợp lệ tại một thời điểm.

Cần đánh giá tình huống split-brain hoặc process cũ chưa dừng trên node lỗi. ID ổn định có thể giúp fence producer cũ khi producer mới nhận đúng slot, nhưng không thay thế cơ chế fencing/leader election cho database hoặc service ngoài Kafka.

## 13. Timeout, transactional ID expiration và producer cache

Không phải mọi lỗi transaction đều do hai pod trùng ID. Có những tình huống producer không còn khả dụng dù prefix được cấp đúng.

### 13.1. transaction.timeout.ms

`transaction.timeout.ms` giới hạn thời gian một Kafka transaction được phép mở. Nếu ứng dụng giữ transaction quá lâu qua HTTP/database call, broker có thể abort transaction và commit sau đó thất bại.

Đây là timeout của **transaction đang chạy**, không phải thời hạn tồn tại vĩnh viễn của transactional ID.

### 13.2. transactional.id.expiration.ms

Broker có cấu hình `transactional.id.expiration.ms` để quản lý thời gian giữ metadata của transactional IDs không được sử dụng trong thời gian dài. Một producer được giữ trong cache quá lâu mà không hoạt động có thể gặp vấn đề khi quay lại dùng sau khi metadata/identity không còn hợp lệ theo lifecycle.

Spring Kafka cung cấp cấu hình `maxAge` trên `DefaultKafkaProducerFactory` để refresh producer trong cache trước khi producer trở nên quá cũ. Cần điều chỉnh phù hợp broker expiration và workload ít phát event.

Không nên nhầm expiration này với duplicate transactional ID giữa hai pod; chúng có triệu chứng có thể gần giống ở mức lỗi producer nhưng nguyên nhân và cách khắc phục khác nhau.

### 13.3. Kafka broker authorization

Transactional producer thường cần quyền phù hợp trên transactional ID và topic đích. Nếu ACL từ chối, có thể gặp lỗi authorization ngay cả khi ID không trùng.

Với Kafka ACL, cần kiểm tra principal, transactional ID resource, topic WRITE và các quyền khác theo mode triển khai. Không đổi prefix tùy tiện để “né” ACL nếu cấu hình authorization đang sai.

## 14. Các lỗi thường gặp khi transaction ID không phù hợp

| Triệu chứng | Khả năng nguyên nhân | Hướng kiểm tra |
|---|---|---|
| `ProducerFencedException` trong nhiều pod | Trùng transactional ID hoặc producer cũ mất ownership | So sánh prefix/suffix, rollout overlap |
| `InvalidProducerEpochException` | Producer epoch cũ hoặc transaction state không còn hợp lệ | Kiểm tra fencing và transaction lifecycle |
| `OutOfOrderSequenceException` | Sequence/order producer không hợp lệ | Kiểm tra trạng thái producer và lỗi trước đó |
| `InvalidTxnStateException` | API transaction gọi không đúng trạng thái | Begin/send/commit/abort |
| `TimeoutException` khi commit | Broker/network chậm hoặc transaction hết hạn | Transaction duration và coordinator |
| Authorization error | Thiếu ACL trên transactional ID/topic | Principal, resource và permissions |
| Restart liên tục sau khi scale | Prefix chung cho nhiều replicas | Cấu hình env per-instance |
| Lỗi chỉ sau thời gian idle | Producer cache / transactional ID expiration | Factory maxAge và broker expiration |
| Transaction rollback nhiều nhưng không fencing | Listener exception hoặc downstream fail | Listener log và after-rollback processor |

Khi gặp producer fencing, **không retry vô hạn trên cùng producer đã bị fence**. Đây thường là lỗi fatal của producer generation. Framework cần đóng/loại bỏ producer không hợp lệ, và ứng dụng phải xác định nguồn xung đột identity nếu có.

## 15. Logging và observability

Mục tiêu là xác định nhanh instance nào tạo ID nào, transaction bị lỗi ở giai đoạn nào và điều đó có ảnh hưởng đến consumer offsets hay không.

Những thông tin nên ghi nhận:

- Application/service name và deployment environment.
- Instance/pod identity và transaction ID prefix.
- Consumer group ID và client ID (nếu listener).
- Tên Kafka cluster hoặc bootstrap server alias đã cấu hình.
- Transaction begin/commit/abort outcomes.
- Kafka exception class, đặc biệt fencing/epoch/authorization.
- Listener container ID, topic-partition và offset khi lỗi.
- Producer cache lifecycle và transaction duration nếu có instrumentation.

Không cần log secret, full payload hoặc thông tin authentication. Có thể log prefix và một phần transactional ID để điều tra trùng identity, miễn là tuân thủ chính sách bảo mật.

Các metrics đáng theo dõi:

| Metric / tín hiệu | Ý nghĩa |
|---|---|
| Transaction commit success/error | Tỷ lệ transaction hoàn tất |
| Transaction abort count | Lỗi nghiệp vụ hoặc hạ tầng làm abort |
| Producer fenced count | Xung đột producer generation |
| Transaction duration | Phát hiện transaction mở lâu |
| Transaction coordinator latency | Phát hiện broker bottleneck |
| Producer send errors | Lỗi publish trong transaction |
| Consumer lag theo partition | Tác động rollback/redelivery |
| Rebalance count/duration | Đánh giá group stability |
| Pod restarts | Nhận diện crash loop vì fencing |
| Producer cache activity | Phân tích churn và resource usage |

Nếu fencing tăng ngay sau deployment hoặc autoscaling, hãy so sánh instance identities đang chạy. Nếu lỗi chỉ xuất hiện sau idle lâu, xem lại producer cache và broker transaction ID expiration.

## 16. Quy trình điều tra ProducerFencedException

Khi nhận log fencing trong một service sử dụng KafkaTransactionManager:

1. Ghi nhận thời điểm lỗi, tên pod/JVM, môi trường và Kafka cluster.
2. Xác định transactional ID thực tế hoặc prefix đang được dùng.
3. Liệt kê các **instance đang hoạt động** thuộc dịch vụ đó trong cùng cluster.
4. Kiểm tra prefix có khác nhau giữa các instance không.
5. Kiểm tra có rollout overlap, HPA scale-up hoặc process cũ còn sống không.
6. Xác định có nhiều ProducerFactory trong cùng JVM tạo các ID trùng nhau không.
7. Xác nhận Spring Boot environment override không bị ghi đè bởi bean Java tùy chỉnh.
8. Đối chiếu commit/abort logs và Kafka coordinator errors.
9. Không cố tiếp tục dùng producer đã fenced; khắc phục ownership/identity.
10. Chạy lại trên môi trường thử nghiệm với nhiều replica để chứng minh không còn xung đột.

Nếu tất cả prefix đều unique mà vẫn có fencing, không lập tức kết luận Kafka broker lỗi. Cần kiểm tra client lifecycle, broker expiration, lỗi transaction trước đó và những producer khác có thể sử dụng cùng ID.

## 17. Kiểm thử prefix duy nhất trước production

### 17.1. Một instance

1. Cấu hình transactional producer với prefix thử nghiệm.
2. Mở transaction, gửi hai records, commit.
3. Xác nhận `read_committed` consumer nhìn thấy hai records.
4. Gửi transaction khác và xác nhận producer có thể tiếp tục.

### 17.2. Hai instance với prefix trùng (chỉ môi trường test)

1. Khởi chạy hai instance cùng prefix cố định.
2. Cho cả hai init transactions gần thời điểm nhau.
3. Quan sát producer epoch thay đổi và hành vi fencing.
4. Ghi log transactional IDs để chứng minh nguồn va chạm.
5. Không chạy thử nghiệm này trên production cluster/topic.

### 17.3. Hai instance với prefix riêng

1. Chạy hai instance cùng ứng dụng nhưng prefix khác nhau.
2. Mỗi instance gửi records trong transaction riêng.
3. Xác nhận không có lỗi fencing do trùng ID.
4. Đọc bằng `read_committed` để xác minh committed records hiển thị.

### 17.4. Rolling deployment

1. Chạy phiên bản cũ với một số replica.
2. Triển khai phiên bản mới theo RollingUpdate.
3. Ghi nhận identity/prefix của cả pod cũ và mới trong khoảng overlap.
4. Xác nhận không có accidental collision.
5. Theo dõi transaction commit/error, consumer lag và rebalance.

### 17.5. Crash và restart

1. Cho một transactional listener xử lý input rồi dừng process trước transaction commit.
2. Khởi động lại theo chiến lược identity đã chọn.
3. Xác nhận record input chưa được commit có thể được giao lại.
4. Xác nhận output từ aborted transaction không hiển thị với `read_committed`.
5. Xác nhận side effect bên ngoài Kafka được bảo vệ idempotency.
6. Nếu dùng identity ổn định theo slot, kiểm tra owner cũ không còn quyền commit sau khi owner mới tiếp quản.

Kiểm thử không chỉ dựa vào một exception message. Hãy xác minh trạng thái output topic, source consumer offset và transaction outcomes.

## 18. Exactly once không đồng nghĩa với một lần gọi listener

Một transactional listener có thể được gọi lại sau transaction abort hoặc process restart. Kafka exactly-once processing trong phạm vi Kafka bảo vệ việc output và offset được commit cùng nhau, không hứa listener method chạy đúng một lần theo nghĩa CPU/business invocation.

Ví dụ:

~~~text
Input event E
  -> Listener xử lý E, transaction T1
  -> T1 abort
  -> Listener nhận lại E, transaction T2
  -> T2 commit

Listener đã chạy 2 lần.
Kafka output committed có thể chỉ phản ánh T2.
~~~

Nếu listener thực hiện SQL update hoặc HTTP call giữa hai lần, side effect đó vẫn có thể lặp. Unique transaction ID không tự giải quyết. Cần:

- Business event ID ổn định.
- Inbox table hoặc unique constraint ở database.
- Idempotent update hoặc upsert.
- Transactional outbox khi đồng bộ database và Kafka.
- Recovery và DLT có thể xử lý record trùng.

## 19. Checklist quyết định theo kiểu triển khai

| Mô hình | Chiến lược identity cần xem |
|---|---|
| Một JVM producer-only | Prefix cố định riêng cho ứng dụng, factory quản lý suffix |
| Nhiều JVM/pod producer-only | Prefix khác nhau giữa những instance chạy đồng thời |
| Kubernetes Deployment | Pod UID hoặc instance ID unique; đánh giá thêm failover semantics |
| Kubernetes StatefulSet | Identity theo slot có thể ổn định, cần ownership/fencing đúng |
| Listener consume–process–produce | Prefix unique + transactional listener + source offsets in transaction |
| Nhiều ProducerFactory | Phối hợp không gian ID giữa factory, không tạo trùng |
| Nhiều namespace chung Kafka cluster | Đặt prefix có app/environment/instance scope để tránh va chạm |
| Rolling update | Tính cả pod cũ và mới đồng thời |
| Transactional service có database side effect | Unique ID không đủ; cần outbox/inbox/idempotency |

Một cấu trúc prefix dễ quản lý:

~~~text
<environment>-<service>-<instance-identity>-
~~~

Ví dụ:

~~~text
prod-orders-worker-pod-72a9-
staging-orders-worker-pod-b814-
prod-payments-worker-slot-03-
~~~

Đây không phải format bắt buộc của Kafka. Giá trị quan trọng là uniqueness, tính dễ truy vết và tính phù hợp với ownership model. Tránh các tên prefix quá chung như `tx-`, `producer-` hoặc `orders-` trên một cluster chứa nhiều dịch vụ.

## 20. Các lỗi thiết kế thường gặp

**Dùng cùng một transaction-id-prefix cho mọi pod:** factory ở các pod có thể tạo suffix trùng, gây fencing.

**Cho rằng factory tự thêm suffix đủ bảo đảm uniqueness toàn cluster:** suffix được quản lý trong phạm vi factory, không có một bộ cấp suffix chung cho các JVM.

**Dùng `client.id` thay cho `transactional.id`:** client ID phục vụ observability và không phải cơ chế fencing transaction.

**Dùng `group.id` làm transactional ID:** consumer group và producer transaction có semantics khác nhau; cần identity riêng.

**Dùng random ID rồi giả định tự fence zombie:** random ID mới không tự thay thế epoch của producer có ID cũ.

**Dùng identity ổn định nhưng chạy hai owner độc lập cùng lúc:** một producer có thể liên tục fence producer kia.

**Tạo transactional ID theo từng message:** tăng producer overhead và không phục vụ business deduplication.

**Chỉ sửa prefix khi thấy fencing nhưng bỏ qua factory wiring:** bean tùy chỉnh có thể tiếp tục dùng prefix cũ hoặc tạo producer khác.

**Nuốt ProducerFencedException rồi tiếp tục commit:** producer đã mất ownership không nên được xem là recoverable bằng retry cùng instance.

**Coi unique prefix là exactly-once end-to-end:** còn cần Kafka transaction boundary, consumer isolation, offset coordination và idempotency của external side effect.

**Không kiểm tra Kafka cluster scope:** staging và production có thể cùng một cluster; các prefix giống nhau vẫn có khả năng va chạm.

**Không theo dõi transaction expiration:** producer idle trong cache có thể gặp lỗi không xuất phát từ collision.

## 21. Nguyên tắc vận hành production

- Xem `transactional.id` là danh tính logic của producer transaction, không phải event ID.
- Dùng `transaction-id-prefix` khác nhau giữa các instance độc lập đang hoạt động.
- Để factory quản lý suffix; không dựa vào suffix để ngăn va chạm giữa các JVM.
- Với Kubernetes, cấp prefix bằng Pod UID/identity hoặc cơ chế cấp ID đáng tin cậy.
- Phân biệt yêu cầu uniqueness giữa pod với yêu cầu identity ổn định để fence owner cũ sau failover.
- Kiểm tra rolling overlap, HPA và StatefulSet ownership.
- Giám sát `ProducerFencedException`, invalid epoch, transaction commit/abort và latency.
- Không tiếp tục dùng producer đã bị fence.
- Đồng bộ transaction ID strategy với Kafka EOS version và listener container.
- Cấu hình consumer `read_committed` khi muốn không thấy aborted Kafka records.
- Không coi KafkaTransactionManager là distributed transaction với database.
- Bảo vệ side effect nghiệp vụ bằng event ID, inbox/outbox và idempotency.

**Kết luận:** Trong Spring Kafka, transaction ID duy nhất theo instance giúp các transactional producers độc lập không vô tình fence lẫn nhau khi ứng dụng chạy nhiều replica. `transactionIdPrefix` phải được cấp đúng phạm vi và kết hợp với suffix của producer factory. Đối với hệ thống cần exactly-once Kafka-to-Kafka, còn phải bảo đảm transaction boundary, consumer offsets, isolation và xử lý rollback chính xác. Với failover hoặc external side effect, uniqueness đơn thuần không thay thế ownership fencing và idempotency nghiệp vụ.
