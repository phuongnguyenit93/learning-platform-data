# Transaction bị abort hoặc fence

## 1. Hiện tượng và tác động

Kafka transaction giúp producer ghi nhiều record và commit chúng như một đơn vị. Nếu một transaction bị abort, consumer dùng `read_committed` sẽ không nhận các record thuộc transaction đó. Nếu producer bị fence, producer cũ mất quyền sử dụng transactional ID và không thể tiếp tục transaction.

Các dấu hiệu thường gặp:

- Log có `ProducerFencedException`, `InvalidProducerEpochException` hoặc thông báo producer bị từ chối vì epoch cũ.
- `KafkaTemplate` gửi được record nhưng `commitTransaction()` thất bại.
- Listener transaction rollback và record được giao lại.
- Consumer `read_committed` không nhìn thấy record mà producer đã gửi trước đó.
- Ứng dụng liên tục tạo producer mới hoặc transaction bị abort sau mỗi lần rollout.
- Broker log có lỗi transaction coordinator, transactional ID authorization hoặc transaction timeout.

Abort có thể là kết quả đúng khi xử lý nghiệp vụ thất bại. Fencing thường cho biết có producer khác đang sở hữu cùng transactional ID, hoặc producer hiện tại đã trở nên stale. Cần phân biệt hai trường hợp trước khi thay đổi cấu hình.

## 2. Transaction, producer ID và epoch

Kafka cấp cho transactional producer một `transactional.id`. Khi producer khởi tạo transaction (`initTransactions()`), broker gán producer ID và epoch cho danh tính đó. Epoch là số thế hệ dùng để phân biệt producer hiện tại với producer cũ.

Nếu một producer mới khởi tạo với cùng `transactional.id`, Kafka tăng epoch. Producer cũ với epoch thấp hơn bị fence; các request tiếp theo từ producer cũ bị từ chối.

```text
transactional.id = orders-producer-1

Producer A khởi tạo
  producerId = 700
  epoch      = 3
       |
       | Producer A bắt đầu transaction
       v
Kafka transaction coordinator
       ^
       | Producer B khởi tạo lại cùng transactional.id
       |
Producer B
  producerId = 700
  epoch      = 4

Producer A (epoch 3) ---- request tiếp theo ----> bị fence
Producer B (epoch 4) ---- request tiếp theo ----> hợp lệ
```

Fencing bảo vệ dữ liệu khỏi một producer cũ tiếp tục ghi sau khi một producer mới đã tiếp quản cùng transactional ID. Nó không phải lỗi ngẫu nhiên có thể khắc phục bằng cách retry cùng producer.

## 3. Phân biệt abort, fence và các lỗi liên quan

| Exception / dấu hiệu | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `ProducerFencedException` | Producer bị một producer khác có epoch mới hơn thay thế | Không dùng lại producer cũ; tìm transactional ID bị trùng hoặc producer stale |
| `InvalidProducerEpochException` | Request dùng producer epoch không còn hợp lệ | Kiểm tra producer lifecycle, fencing và transaction state |
| `OutOfOrderSequenceException` | Sequence của producer không hợp lệ; có thể là lỗi nghiêm trọng với producer idempotent/transactional | Kiểm tra retry, producer lifecycle và broker; producer cũ có thể phải bị loại bỏ |
| `InvalidTxnStateException` | Thao tác không hợp lệ với trạng thái transaction hiện tại | Kiểm tra begin/send/commit/abort và việc dùng chung producer |
| `TimeoutException` | Một thao tác transaction không hoàn tất trong thời hạn | Phân biệt timeout khi gửi, commit, coordinator hoặc transaction đang mở quá lâu |
| `TransactionalIdAuthorizationException` | Principal không có quyền dùng transactional ID | Cấp ACL `TransactionalId` phù hợp |
| `NotCoordinatorException` / coordinator unavailable | Client chưa liên lạc được transaction coordinator hiện tại | Kiểm tra broker/coordinator; để Kafka client xử lý lỗi retriable theo cấu hình |
| `FencedInstanceIdException` | Consumer static member bị một consumer khác dùng cùng `group.instance.id` thay thế | Sửa consumer instance ID; đây không phải producer transaction fencing |
| `CommitFailedException` | Consumer không thể commit offset, thường do đã mất assignment hoặc group rebalance | Điều tra consumer group, poll interval và offset commit |

`ProducerFencedException` và `FencedInstanceIdException` là hai lỗi khác nhau. Lỗi đầu liên quan transactional producer ID; lỗi sau liên quan static consumer membership.

## 4. Các nguyên nhân phổ biến khiến producer bị fence

### 4.1. Hai application instance dùng cùng transactional ID

Đây là nguyên nhân cần kiểm tra đầu tiên khi lỗi xuất hiện sau khi scale hoặc deploy nhiều replica. Hai JVM cùng khởi tạo một transactional ID sẽ thay epoch của nhau. Mỗi lần instance mới khởi động, producer cũ có thể bị fence.

Ví dụ cấu hình sai:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-tx-
```

Nếu mọi pod dùng cùng prefix và mỗi pod có producer factory riêng, các suffix được cấp trong từng factory có thể trùng nhau. Prefix phải phân biệt giữa các application instance đang chạy đồng thời.

### 4.2. Producer cũ vẫn còn hoạt động sau restart hoặc network partition

Một process có thể bị mất kết nối tạm thời nhưng chưa dừng hẳn. Process mới khởi tạo cùng transactional ID và tăng epoch. Khi process cũ kết nối lại, request của nó bị fence.

### 4.3. Nhiều producer dùng chung factory nhưng vòng đời bị quản lý sai

Spring Kafka `DefaultKafkaProducerFactory` quản lý transactional producer và suffix cho producer. Nếu ứng dụng tự tạo nhiều factory với cùng prefix, hoặc tự giữ producer cũ bên ngoài factory, có thể tạo xung đột ngoài dự kiến.

### 4.4. Static identity của deployment không duy nhất

Kubernetes Deployment có nhiều replica nhưng cùng dùng một environment variable cố định làm prefix. Khi scale, mọi replica cùng dùng một danh tính. Mỗi pod cần một ID duy nhất và ổn định trong vòng đời của pod.

## 5. Cấu hình transactional ID đúng trong Spring Kafka

Spring Kafka sử dụng `transactionIdPrefix` trên `DefaultKafkaProducerFactory`. Factory thêm suffix để tạo transactional ID riêng cho mỗi producer được cấp từ factory.

Ví dụ Spring Boot:

```yaml
spring:
  kafka:
    bootstrap-servers: broker1:9092,broker2:9092
    producer:
      transaction-id-prefix: ${HOSTNAME:local}-orders-tx-
```

Trong Kubernetes, `HOSTNAME` thường là pod name. Hãy xác minh biến này thật sự khác nhau giữa các replica và không bị override thành một giá trị chung.

Giá trị fallback `local` chỉ phù hợp cho môi trường phát triển một instance. Ở production, nên yêu cầu `HOSTNAME` hoặc `APP_INSTANCE_ID` bắt buộc có giá trị; nếu biến bị thiếu, ứng dụng nên fail fast thay vì để nhiều replica vô tình dùng cùng prefix.

Nếu tự tạo factory:

```java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;

@Bean
DefaultKafkaProducerFactory<String, String> orderProducerFactory(
        @Value("${spring.kafka.bootstrap-servers}") String bootstrapServers,
        @Value("${app.instance-id}") String instanceId) {

    Map<String, Object> properties = new HashMap<>();
    properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
    properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);

    DefaultKafkaProducerFactory<String, String> factory =
            new DefaultKafkaProducerFactory<>(properties);

    factory.setTransactionIdPrefix(instanceId + "-orders-tx-");
    return factory;
}
```

`instanceId` phải duy nhất giữa các process chạy đồng thời. Trong ví dụ này, mỗi factory tự quản lý suffix nội bộ để các producer do chính factory cấp không đụng transactional ID với nhau.

Không đặt cùng một `transactional.id` tĩnh trực tiếp cho mọi producer. Khi dùng Spring Kafka, cấu hình prefix ở factory để factory quản lý producer lifecycle và suffix.

## 6. Kiểm tra transactional ID thực tế

Không chỉ nhìn prefix trong YAML. Hãy kiểm tra transactional ID mà producer thực sự sử dụng trong log và cấu hình runtime.

Các bước:

1. Ghi log `HOSTNAME`, pod name, application instance ID và transaction ID prefix lúc startup.
2. So sánh các instance trong cùng môi trường và cùng cluster.
3. Kiểm tra có nhiều `DefaultKafkaProducerFactory` bean dùng chung prefix không.
4. Kiểm tra producer factory có bị tạo thủ công nhiều lần ngoài Spring context không.
5. Kiểm tra process cũ còn sống sau rollout, graceful shutdown hoặc node partition không.
6. Đối chiếu thời điểm `ProducerFencedException` với startup của instance khác.

Không log credential, JAAS config hoặc dữ liệu nhạy cảm khi debug transaction ID.

## 7. Transactional ID phải duy nhất giữa instance, nhưng ổn định trong instance

Có hai yêu cầu cần cân bằng:

- Các instance chạy đồng thời phải dùng transactional ID khác nhau để không fence lẫn nhau.
- Producer được khởi tạo lại cho cùng một logical instance có thể dùng lại prefix/ID theo thiết kế để Kafka fence producer cũ và bảo đảm chỉ producer mới sở hữu transaction.

Ví dụ với Kubernetes StatefulSet:

```yaml
env:
  - name: APP_INSTANCE_ID
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
```

Ứng dụng dùng `APP_INSTANCE_ID` để tạo prefix. StatefulSet ordinal ổn định khi pod được tạo lại, trong khi mỗi ordinal khác nhau giữa các replica.

Với Deployment, pod name thường thay đổi khi tạo pod mới. Đây là lựa chọn an toàn để tránh xung đột giữa các pod cùng chạy, nhưng cần hiểu rằng transactional ID mới có thể tạo state mới trong transaction coordinator. Theo dõi số transactional ID và thời gian cleanup; không sinh prefix ngẫu nhiên mới cho từng producer trong cùng một factory.

Không dùng hostname của node nếu nhiều pod trên cùng node có thể chạy cùng service và chia sẻ hostname.

## 8. Producer bị fence thì phải làm gì?

Khi producer nhận `ProducerFencedException`, producer cũ không còn quyền ghi transaction. Không retry lệnh `send()` hoặc `commitTransaction()` trên cùng producer như thể lỗi mạng tạm thời.

Quy trình xử lý:

1. Dừng sử dụng producer đã bị fence.
2. Để Spring Kafka/producer factory loại bỏ producer lỗi theo lifecycle của factory; không giữ reference cũ để tái sử dụng.
3. Tìm instance khác đang dùng cùng transactional ID hoặc prefix.
4. Sửa instance ID/prefix để mỗi application instance có danh tính riêng.
5. Đảm bảo instance cũ đã shutdown hoặc không còn tiếp tục ghi.
6. Khởi tạo producer mới thông qua factory và bắt đầu transaction mới.
7. Kiểm tra các record thuộc transaction cũ ở consumer `read_committed` để xác nhận chúng không được nhìn thấy nếu transaction đã abort.

Không bắt `ProducerFencedException` rồi bỏ qua để listener tiếp tục chạy. Producer cũ không thể khôi phục quyền sở hữu transaction chỉ bằng retry.

## 9. Vì sao transaction bị abort?

Transaction có thể bị abort vì:

- Listener hoặc service ném exception trước khi commit.
- Ứng dụng chủ động gọi `abortTransaction()`.
- Producer bị fence bởi producer khác.
- Transaction vượt `transaction.timeout.ms`.
- Broker transaction coordinator gặp lỗi hoặc không sẵn sàng đủ lâu.
- Commit không thể hoàn tất trước timeout.
- Ứng dụng gửi offset hoặc record ngoài trạng thái transaction hợp lệ.
- Principal không có quyền ghi topic hoặc transactional ID.

Abort là kết quả của transaction rollback. Record đã được gửi trong transaction nhưng chưa commit sẽ không hiển thị cho consumer có `isolation.level=read_committed`.

Với consumer `read_uncommitted` (mặc định Kafka client), record thuộc transaction đã abort vẫn có thể được đọc. Vì vậy khi kiểm thử transaction, phải cấu hình consumer `read_committed` nếu muốn xác minh atomic visibility.

## 10. Phân biệt transaction timeout và poll timeout

Các timeout sau điều khiển những hoạt động khác nhau:

| Cấu hình | Ý nghĩa | Dấu hiệu khi vượt |
|---|---|---|
| `transaction.timeout.ms` | Thời gian tối đa broker cho phép một transaction mở | Broker có thể abort transaction quá hạn |
| `transaction.max.timeout.ms` | Giới hạn tối đa broker chấp nhận cho client transaction timeout | Producer config lớn hơn giới hạn bị từ chối khi khởi tạo |
| `max.poll.interval.ms` | Thời gian tối đa giữa hai lần consumer poll trong classic protocol | Consumer có thể rời group; offset commit có thể thất bại |
| `request.timeout.ms` | Thời gian client chờ response cho một request | Request timeout, nhưng không nhất thiết transaction đã abort ngay |
| `delivery.timeout.ms` | Giới hạn thời gian producer giao một record thành công hoặc báo lỗi | Send future hoàn tất lỗi do delivery timeout |

Không tăng tất cả timeout cùng lúc. Hãy xác định thao tác nào bị timeout và thời gian thực tế transaction/listener giữ tài nguyên.

Ví dụ cấu hình producer:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${HOSTNAME:local}-orders-tx-
      properties:
        "[transaction.timeout.ms]": 60000
        "[request.timeout.ms]": 30000
        "[delivery.timeout.ms]": 120000
```

Giá trị trên chỉ minh họa. `transaction.timeout.ms` phải nhỏ hơn hoặc bằng `transaction.max.timeout.ms` của broker. Không đặt transaction timeout dài hơn nhu cầu nghiệp vụ vì transaction mở lâu giữ transaction coordinator state và có thể làm tăng thời gian xử lý downstream `read_committed`.

## 11. Kiểm tra transaction coordinator và broker

Kafka transaction coordinator quản lý transactional ID, producer epoch và trạng thái transaction. Nếu coordinator unavailable hoặc đang chuyển quyền, producer có thể thấy lỗi như `NotCoordinatorException`, `CoordinatorNotAvailableException` hoặc `CoordinatorLoadInProgressException`.

Kiểm tra:

- Broker nào đang làm coordinator cho transactional ID.
- Broker log có transaction state log error, disk error hoặc ISR shrink không.
- Cluster có đủ broker để đáp ứng replication factor của transaction state log không.
- `transaction.state.log.replication.factor` và `transaction.state.log.min.isr` có phù hợp với số broker và độ bền mong muốn không.
- Broker restart, leader election hoặc network partition có trùng thời điểm lỗi không.
- Producer có retry coordinator metadata theo Kafka client hay ứng dụng đang tự retry quá mức.

Trong production nhiều broker, transaction state log cần replication phù hợp để transaction metadata không trở thành điểm yếu của cluster. Không hạ replication factor/min ISR chỉ để làm transaction hoạt động trên cluster thiếu broker mà không đánh giá rủi ro.

Nếu nhiều producer với nhiều transactional ID cùng lỗi coordinator, nghi ngờ broker/cluster. Nếu chỉ một ID liên tục bị fence trong khi coordinator ổn định, ưu tiên điều tra ID collision và producer lifecycle.

## 12. Transactional ID authorization và Kafka ACL

Khi dùng SASL/SSL hoặc cơ chế xác thực khác, producer cần quyền trên các resource liên quan. Thiếu quyền transactional ID có thể gây `TransactionalIdAuthorizationException` khi khởi tạo transaction hoặc gửi request transaction.

Kiểm tra các quyền:

| Resource | Operation thường cần | Mục đích |
|---|---|---|
| `TransactionalId` | `Write`, `Describe` theo thao tác/phiên bản | Khởi tạo và sử dụng transactional ID |
| Topic nguồn/đích | `Write`, `Describe` | Ghi record trong transaction |
| Consumer Group | `Read` | Consumer tham gia group và gửi offset vào transaction |

ACL chính xác phụ thuộc broker authorizer, principal mapping và operation thực tế. Cấp quyền tối thiểu cho prefix transactional ID của service; tránh cấp quyền rộng cho mọi transactional ID.

Nếu lỗi là authorization, thay đổi `transactionIdPrefix` không giải quyết được quyền thiếu. Kiểm tra principal mà broker nhìn thấy và ACL resource đúng loại.

## 13. Cấu hình KafkaTransactionManager trong Spring Kafka

Để dùng `@Transactional` với Kafka, producer factory phải có transaction ID prefix và ứng dụng khai báo `KafkaTransactionManager`.

```java
@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
            ProducerFactory<String, OrderEvent> producerFactory) {

        return new KafkaTransactionManager<>(producerFactory);
    }
}
```

Service có thể tham gia transaction bằng cách chỉ định đúng transaction manager:

```java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, OrderEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(OrderEvent event) {
        kafkaTemplate.send("orders", event.orderId(), event);
        kafkaTemplate.send("orders.audit", event.orderId(), event);
    }
}
```

Các lệnh gửi được thực hiện trong cùng Kafka transaction được Spring bind vào thread. Khi method hoàn tất bình thường, transaction manager commit; nếu method ném exception phù hợp, transaction rollback/abort.

`KafkaTemplate` trong service phải dùng đúng `ProducerFactory` mà `KafkaTransactionManager` quản lý. Nếu template và transaction manager trỏ đến hai factory khác nhau, lệnh gửi có thể không tham gia transaction mà bạn mong đợi.

Đảm bảo method được gọi qua Spring proxy. Self-invocation trong cùng bean có thể bỏ qua `@Transactional`; khi đó Kafka transaction không được mở như mong đợi. Nếu method gọi từ thread khác hoặc `@Async`, transaction thread-bound cũng không tự truyền sang thread mới.

## 14. Transactional listener container và offset

Với listener container transactional, Spring Kafka bắt đầu Kafka transaction cho việc xử lý record. Khi listener thành công, container gửi offset đã xử lý vào transaction và commit. Nếu listener ném exception, transaction abort; record có thể được giao lại theo error handler và offset commit policy.

Ví dụ cấu hình factory với transaction manager:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent> orderListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
            .setKafkaAwareTransactionManager(kafkaTransactionManager);
    return factory;
}
```

`ConsumerFactory` của listener container tạo consumer và phải trỏ đến đúng cluster/cấu hình bảo mật. `KafkaTransactionManager` quản lý producer transaction; `KafkaTemplate` phát output trong transaction phải dùng cùng `ProducerFactory` với transaction manager.

Listener:

```java
@KafkaListener(
        topics = "orders",
        groupId = "order-projection",
        containerFactory = "orderListenerFactory")
public void onOrder(OrderEvent event) {
    projectionService.apply(event);
}
```

Nếu listener ném exception, container rollback transaction. `AfterRollbackProcessor` xử lý record được giao lại hoặc recovery sau số lần thử; `DefaultAfterRollbackProcessor` là implementation mặc định trong luồng transactional listener. Không bắt exception rồi chỉ log nếu muốn transaction rollback; nếu exception bị nuốt, container có thể coi listener thành công và commit offset.

API cấu hình transaction manager của listener container thay đổi theo dòng Spring Kafka. Với Spring Kafka hiện hành, dùng `setKafkaAwareTransactionManager`; dự án cũ có thể gặp API `setTransactionManager` đã deprecated. Hãy dùng API tương ứng với version đang quản lý.

## 15. Kiểm tra `isolation.level=read_committed`

Consumer mặc định dùng `read_uncommitted`. Khi muốn chỉ nhận record thuộc transaction đã commit, cấu hình:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

Consumer `read_committed` chỉ trả về record đến Last Stable Offset (LSO), tức vị trí trước transaction đang mở sớm nhất trong partition. Một transaction mở lâu có thể khiến record phía sau bị chặn khỏi consumer dù record đó đã được ghi.

Khi kiểm tra record “mất”, cần xác minh:

- Producer đã commit hay abort transaction?
- Consumer có đang dùng `read_committed` hay `read_uncommitted`?
- Partition có transaction mở lâu làm LSO chưa tiến không?
- Consumer có đọc đúng topic, partition và offset không?
- Transaction marker đã được broker ghi và replication chưa?

Nếu record thuộc transaction abort, consumer `read_committed` không nhìn thấy nó theo thiết kế. Điều đó không có nghĩa Kafka xóa record ngoài transaction.

## 16. Transaction timeout và transaction mở quá lâu

Transaction nên bao quanh một đơn vị công việc có thời gian hữu hạn. Nếu ứng dụng mở transaction rồi gọi HTTP chậm, chờ người dùng hoặc xử lý batch quá lớn, transaction có thể vượt `transaction.timeout.ms`.

Các thực hành tốt:

- Không thực hiện tác vụ ngoài Kafka chậm trong Kafka transaction nếu không cần thiết.
- Đặt timeout cho database/HTTP call.
- Giữ batch transaction đủ nhỏ.
- Không mở transaction rồi giữ producer lâu giữa các bước tương tác.
- Theo dõi transaction duration và abort rate.
- Chọn `transaction.timeout.ms` theo p99 processing duration và giới hạn broker.

Transaction timeout là giới hạn bảo vệ broker khỏi transaction bị bỏ quên. Tăng timeout chỉ hợp lý khi nghiệp vụ thực sự cần thời gian dài và cluster đã được đánh giá tác động.

## 17. Producer factory cache và producer lifecycle

Spring Kafka `DefaultKafkaProducerFactory` quản lý producer được tạo từ factory. Với transactional producer, factory tạo transactional ID từ prefix và suffix; các producer có thể được cache rồi tái sử dụng theo lifecycle.

Kiểm tra:

- Có bao nhiêu producer factory được tạo trong application context?
- Các factory có dùng cùng prefix không?
- Có nhiều thread/concurrent transaction hơn số producer cache cho phép không?
- Ứng dụng có giữ producer ngoài factory hoặc gọi `close()` sai cách không?
- Có producer cũ sống quá lâu sau khi pod được thay thế không?
- Có cấu hình `maxAge` để producer được refresh trước khi transactional ID hết hạn không?

Spring Kafka cung cấp `setMaxAge(Duration)` trên producer factory để giới hạn tuổi producer được cache. Điều này hữu ích khi broker có `transactional.id.expiration.ms`; producer cache quá lâu có thể dùng transactional ID đã hết hạn và gặp lỗi khi khởi tạo transaction mới. Chọn max age nhỏ hơn thời gian expiration của broker với biên an toàn.

`setMaxAge()` có từ Spring Kafka 2.5.8, 2.6.4 và 2.7.0 trên các nhánh tương ứng. Nếu dự án dùng bản cũ hơn, kiểm tra API trước khi cấu hình. Không áp dụng một giá trị max age chung mà không đối chiếu broker `transactional.id.expiration.ms`.

Ví dụ:

```java
factory.setMaxAge(Duration.ofHours(6));
```

Giá trị 6 giờ chỉ là minh họa. Đối chiếu với `transactional.id.expiration.ms` của broker và thời gian producer thực sự được sử dụng.

## 18. Nested transaction và `executeInTransaction`

`KafkaTemplate.executeInTransaction()` cho phép tạo transaction cục bộ quanh một callback gửi record:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders", orderId, orderEvent);
    operations.send("orders.audit", orderId, auditEvent);
    return null;
});
```

Nếu callback ném exception, transaction được abort; nếu hoàn tất bình thường, template commit transaction. API này hữu ích khi muốn transaction chỉ bao quanh một đoạn code rõ ràng.

`executeInTransaction()` quản lý transaction cục bộ của callback; không giả định nó tự tham gia transaction đang được `KafkaTransactionManager` bind. Khi phối hợp với `@Transactional`, hãy kiểm tra semantics của phiên bản đang dùng và tránh vô tình tạo hai transaction riêng trong khi nghĩ rằng chúng là một.

Không lồng nhiều transaction với cùng producer một cách tùy tiện. Nếu dùng `@Transactional`, `KafkaTransactionManager` và `executeInTransaction()` cùng lúc, hãy xác định transaction nào đang sở hữu producer và transaction nào là độc lập. Kiểm tra semantics propagation của version Spring Kafka đang dùng trước khi tạo nested transaction.

Nếu một transaction đã bị fence, không gọi `executeInTransaction()` lại trên producer cũ. Hãy sửa nguyên nhân transactional ID và để factory cấp producer hợp lệ mới.

## 19. Phân biệt Kafka transaction với transaction database

Kafka transaction chỉ atomic trong phạm vi Kafka: ghi nhiều Kafka record và gửi consumer offsets vào cùng transaction. Nó không tự tạo distributed transaction atomic với database.

Ví dụ `@Transactional("kafkaTransactionManager")` chỉ quản lý Kafka transaction. Nếu method cũng ghi database qua JDBC/JPA, transaction database và Kafka có thể commit ở hai thời điểm khác nhau tùy transaction manager và synchronization.

Không kết luận rằng cả database và Kafka cùng rollback chỉ vì method có annotation `@Transactional`. Nếu cần bảo đảm phát event sau khi database commit, cân nhắc Transactional Outbox và CDC relay; nếu consumer cập nhật database, dùng Inbox/idempotency để chống xử lý trùng.

## 20. Kiểm tra producer transaction bằng CLI và log

Kafka không cung cấp một CLI đơn giản để liệt kê mọi transaction đang mở theo transactional ID trong mọi phiên bản. Khi điều tra, kết hợp producer log, broker log, consumer visibility và metrics.

Kiểm tra producer:

- Ghi nhận application instance ID, transactional ID prefix, producer client ID và thời điểm startup.
- Tìm `ProducerFencedException`, `InvalidProducerEpochException`, `TimeoutException` và `TransactionalIdAuthorizationException`.
- Xác định exception xảy ra ở `initTransactions`, `beginTransaction`, `send`, `sendOffsetsToTransaction`, `commitTransaction` hay `abortTransaction`.
- Ghi transaction duration và số transaction commit/abort.

Kiểm tra broker:

- Transaction coordinator và broker log.
- Transaction state log replication/ISR.
- Coordinator movement, broker restart và network.
- ACL cho transactional ID và topic.

Kiểm tra consumer:

- `isolation.level` đang dùng.
- Consumer lag và Last Stable Offset nếu có metric phù hợp.
- Record có thuộc transaction abort hay transaction còn mở không.
- Offset commit có nằm trong cùng transaction khi dùng consume-transform-produce không.

Không bật debug log toàn bộ Kafka protocol lâu dài trong production. Chỉ bật log chi tiết có giới hạn thời gian và kiểm soát dữ liệu nhạy cảm.

## 21. Bảng lỗi và hướng xử lý

| Lỗi | Nguyên nhân thường gặp | Hành động |
|---|---|---|
| `ProducerFencedException` | Nhiều producer dùng cùng transactional ID; producer cũ còn sống | Tạo prefix duy nhất theo instance; dừng producer cũ; không retry producer bị fence |
| `InvalidProducerEpochException` | Producer epoch stale hoặc transaction state không còn hợp lệ | Kiểm tra transactional ID collision và lifecycle |
| `OutOfOrderSequenceException` | Sequence/epoch không khớp do lỗi producer state hoặc retry | Loại producer lỗi, kiểm tra client/broker và không tái sử dụng instance cũ |
| `InvalidTxnStateException` | Gọi commit/abort/send sai trạng thái hoặc dùng producer đồng thời không đúng | Kiểm tra transaction lifecycle và ownership producer |
| `TransactionalIdAuthorizationException` | Thiếu ACL cho transactional ID | Cấp quyền `TransactionalId` cho principal đúng |
| `TimeoutException` khi commit | Coordinator chậm, transaction mở lâu hoặc request không hoàn tất | Kiểm tra coordinator, timeout và transaction duration; xác định kết quả commit trước khi retry nghiệp vụ |
| `CoordinatorNotAvailableException` | Transaction coordinator đang unavailable | Kiểm tra broker/coordinator và network; để client xử lý lỗi retriable |
| `CommitFailedException` ở listener | Consumer mất assignment hoặc group rebalance | Kiểm tra poll interval, listener duration và group membership |
| Consumer không thấy record | Transaction abort hoặc consumer dùng `read_committed` trong khi transaction chưa commit | Kiểm tra transaction outcome, LSO và isolation level |
| Abort tăng khi downstream chậm | Transaction giữ mở trong lúc chờ dependency | Rút ngắn transaction, đặt dependency timeout hoặc tách workflow |
| Fencing sau scale deployment | Prefix giống nhau giữa các replica | Gắn prefix với pod/instance ID duy nhất |
| Producer cũ bị fence sau restart | Producer cũ chưa dừng hoặc cùng ID được tái sử dụng | Kiểm tra shutdown, rollout và ownership ID |

Nếu `commitTransaction()` timeout, client có thể không biết chắc broker đã commit hay chưa vì response có thể bị mất trên đường về. Không kết luận transaction đã abort chỉ từ timeout phía client. Dùng consumer `read_committed`, event ID/idempotency và log coordinator để đối soát trước khi phát lại side effect nghiệp vụ.

## 22. Kiểm thử transaction abort và fencing

Nên có integration test với broker hỗ trợ transaction, không chỉ mock `KafkaTemplate`.

### Test abort không làm lộ record cho read_committed

1. Tạo transactional producer.
2. Bắt đầu transaction và gửi record.
3. Gọi `abortTransaction()`.
4. Dùng consumer `read_committed` đọc topic.
5. Xác nhận record trong transaction đã abort không được trả về.

### Test commit làm record hiển thị

1. Bắt đầu transaction.
2. Gửi một hoặc nhiều record.
3. Gọi `commitTransaction()`.
4. Consumer `read_committed` nhận đủ record.
5. Xác nhận metadata/offset và payload.

### Test fencing

1. Tạo producer A với transactional ID `orders-test-1`.
2. Gọi `initTransactions()` và bắt đầu transaction.
3. Tạo producer B với cùng transactional ID và gọi `initTransactions()`.
4. Xác nhận producer A bị fence khi tiếp tục thao tác transaction.
5. Xác nhận producer B có thể tiếp tục với epoch mới.

Test này phải chạy tuần tự và đóng cả hai producer. Không chạy đồng thời nhiều test dùng cùng transactional ID.

### Test Spring factory prefix

- Khởi tạo hai application instance với hai prefix khác nhau và xác nhận không fence nhau.
- Khởi tạo hai factory cùng prefix và xác nhận test phát hiện xung đột.
- Kiểm tra `maxAge` và producer refresh theo cấu hình broker test.
- Kiểm tra transaction rollback khi listener ném exception.
- Kiểm tra offset và output record được commit cùng transaction trong consume-transform-produce.

## 23. Quy trình điều tra nhanh

1. **Phân loại lỗi:** xác định là abort, producer fence, authorization, coordinator timeout hay consumer static member fence.
2. **Xác định thao tác:** exception xuất hiện ở init, begin, send, send offsets, commit hay abort.
3. **Ghi nhận danh tính:** lấy transactional ID/prefix, application instance ID, pod name và producer client ID.
4. **So sánh instance:** tìm hai process dùng cùng prefix/transactional ID trong cùng thời điểm.
5. **Kiểm tra lifecycle:** xem producer cũ, pod cũ, graceful shutdown và network partition.
6. **Kiểm tra timeout:** đối chiếu transaction duration với `transaction.timeout.ms` và broker max timeout.
7. **Kiểm tra coordinator:** broker log, coordinator movement, transaction state log và network.
8. **Kiểm tra ACL:** principal có quyền trên transactional ID, topic và consumer group không.
9. **Kiểm tra consumer visibility:** `read_committed` hay `read_uncommitted`, transaction đã commit chưa, LSO có bị chặn không.
10. **Sửa một nguyên nhân:** thường bắt đầu từ prefix uniqueness hoặc transaction duration.
11. **Khởi tạo producer mới:** chỉ sau khi loại bỏ producer stale/fenced và xác nhận ID đúng.
12. **Kiểm thử lại:** commit, abort, fencing, restart và multi-instance rollout.

## 24. Checklist phòng ngừa

- [ ] Mỗi application instance có `transactionIdPrefix` duy nhất.
- [ ] Producer trong cùng factory được quản lý bởi `DefaultKafkaProducerFactory`.
- [ ] Không giữ hoặc tái sử dụng producer đã bị fence.
- [ ] Transaction có thời gian hữu hạn và nhỏ hơn broker max timeout.
- [ ] Dependency timeout không làm transaction mở quá lâu.
- [ ] Consumer dùng `read_committed` nếu nghiệp vụ cần ẩn record thuộc transaction abort.
- [ ] Kafka ACL cấp đúng quyền cho transactional ID, topic và consumer group.
- [ ] Transaction coordinator và transaction state log có replication/ISR phù hợp.
- [ ] Producer factory `maxAge` phù hợp với `transactional.id.expiration.ms`.
- [ ] Shutdown/rollout không để producer cũ tiếp tục chạy ngoài kiểm soát.
- [ ] Có metrics commit, abort, duration, fencing và coordinator error.
- [ ] Có integration test cho commit, abort, fencing và nhiều instance.

## 25. Tổng kết

- Transaction abort là rollback của một đơn vị Kafka transaction; record chưa commit không hiển thị với consumer `read_committed`.
- `ProducerFencedException` xảy ra khi producer dùng epoch cũ vì transactional ID đã được producer khác tiếp quản.
- `transactionIdPrefix` của Spring Kafka phải duy nhất giữa các application instance; factory quản lý suffix cho producer của chính nó.
- Producer bị fence không thể tiếp tục bằng retry trên cùng instance; phải loại bỏ producer cũ và sửa nguyên nhân ID collision/lifecycle.
- `transaction.timeout.ms` khác `max.poll.interval.ms`, `request.timeout.ms` và `delivery.timeout.ms`.
- Transaction coordinator, transaction state log, ACL `TransactionalId` và network đều có thể gây lỗi transaction.
- `KafkaTransactionManager` và transactional listener container giúp Spring quản lý transaction; exception bị nuốt có thể khiến container commit ngoài ý muốn.
- `read_committed` là cấu hình quan trọng khi kiểm tra tính atomic visibility của transaction.
- Kafka transaction không tự atomic với database; dùng Outbox/Inbox khi cần phối hợp DB và Kafka.
- Theo dõi transaction ID, producer epoch, duration, abort rate, coordinator và consumer visibility để chẩn đoán có căn cứ.

Khi transactional ID được quản lý riêng cho từng instance và transaction có thời gian sống rõ ràng, producer tránh được fencing do xung đột danh tính. Khi transaction thực sự abort, consumer và error handler có thể xử lý theo đúng semantics commit/rollback thay vì retry mù quáng.

## Tài liệu tham khảo

- [Apache Kafka — Transactional Messaging](https://kafka.apache.org/documentation/#semantics)
- [Apache Kafka — Producer Configs](https://kafka.apache.org/41/configuration/producer-configs/)
- [Apache Kafka — Broker Configs](https://kafka.apache.org/41/configuration/broker-configs/)
- [Apache Kafka — Authorization and ACLs](https://kafka.apache.org/documentation/#security_authz)
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [Spring Kafka — Producer Factory](https://docs.spring.io/spring-kafka/reference/kafka/producer-factory.html)
- [Spring Kafka — Container Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html#container-transaction)
