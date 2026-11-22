# Điều kiện để transaction hoạt động đúng

Kafka transaction cho phép producer ghi nhiều record và commit hoặc abort chúng như một đơn vị. Với Spring Kafka, chỉ gọi `KafkaTemplate.executeInTransaction()` hoặc gắn `@Transactional` là chưa đủ để hệ thống hoạt động đúng. Producer factory phải hỗ trợ transaction, broker phải lưu được trạng thái transaction, định danh producer phải được quản lý đúng, topic và ACL phải cho phép thao tác, còn consumer cần chọn isolation level phù hợp.

Một transaction có thể được tạo thành công trong môi trường local nhưng thất bại khi triển khai nhiều broker hoặc nhiều replica nếu các điều kiện này không được cấu hình đồng bộ. Bài viết này tập trung vào các điều kiện hạ tầng và cấu hình cần kiểm tra trước khi bật Kafka transaction trong ứng dụng Spring Kafka.

## 1. Bức tranh tổng thể: những điều kiện phải cùng đúng

Để transaction hoạt động ổn định, cần kiểm tra các lớp sau:

| Lớp | Điều kiện chính |
|---|---|
| Kafka cluster | Broker hỗ trợ transaction, transaction coordinator hoạt động và internal transaction state log có đủ replica/ISR |
| Producer | Producer được khởi tạo ở chế độ transactional, có `transactional.id` hợp lệ và idempotence |
| Spring Kafka | `ProducerFactory`, `KafkaTemplate` và transaction manager được nối đúng với nhau |
| Topic | Topic đích tồn tại, có replication phù hợp và producer có quyền ghi |
| Consumer | Dùng `read_committed` nếu chỉ muốn nhìn thấy record đã commit |
| Security | ACL cho phép producer ID, topic, consumer group và thao tác offset cần thiết |
| Thời gian | `transaction.timeout.ms` không vượt giới hạn broker và transaction không mở quá lâu |
| Triển khai | Transaction ID không bị trùng giữa các producer đang hoạt động đồng thời |

```text
Spring application
  KafkaTemplate / KafkaTransactionManager
                 |
                 v
       Transactional Producer
                 |
                 v
          Kafka Broker
       +-------------------+
       | Transaction       |
       | Coordinator       |
       +-------------------+
                 |
                 v
       __transaction_state
                 |
                 v
       Output topic partitions
                 |
                 v
       Consumer read_committed
```

Transaction chỉ bao phủ các thao tác Kafka thuộc cùng transaction và cùng Kafka cluster. Nó không tự biến database, HTTP service hoặc hai Kafka cluster độc lập thành một transaction phân tán.

## 2. Kafka cluster phải hỗ trợ transaction

Kafka hỗ trợ producer transaction từ Kafka 0.11.0. Các broker trong cluster cần chạy phiên bản tương thích và hoạt động ổn định để producer có thể đăng ký transaction, gửi dữ liệu, commit hoặc abort.

Khi producer bắt đầu transaction, Kafka chọn transaction coordinator để quản lý trạng thái cho `transactional.id`. Coordinator ghi trạng thái vào internal topic `__transaction_state`, sau đó phối hợp commit/abort và ghi transaction markers vào các partition liên quan.

Điều đó có nghĩa transaction phụ thuộc vào cả broker nhận record lẫn broker đang làm transaction coordinator. Nếu coordinator hoặc internal transaction state log không sẵn sàng, producer có thể gặp lỗi khi khởi tạo transaction, gửi record hoặc commit.

Không cần tự tạo `__transaction_state`. Kafka quản lý topic nội bộ này. Quản trị viên cần cấu hình broker để topic có replication và ISR phù hợp.

## 3. Cấu hình replication cho transaction state log

Hai broker configuration quan trọng là:

| Broker property | Ý nghĩa |
|---|---|
| `transaction.state.log.replication.factor` | Replication factor của internal topic lưu transaction state |
| `transaction.state.log.min.isr` | Số replica tối thiểu phải ở trạng thái in-sync để ghi transaction state |

Ví dụ cấu hình production thường cần nhiều broker để duy trì replication factor 3 và min ISR 2:

```properties
transaction.state.log.replication.factor=3
transaction.state.log.min.isr=2
```

Các giá trị cụ thể phải phù hợp với số broker và chính sách chịu lỗi của cluster. Nếu cluster chỉ có một broker nhưng internal topic yêu cầu replication factor 3, Kafka không thể tạo đủ replica và transaction có thể không hoạt động.

Với môi trường local chỉ có một broker, có thể giảm hai giá trị xuống 1:

```properties
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
```

Đây chỉ là cấu hình phục vụ học tập hoặc kiểm thử local. Không hạ replication factor và min ISR của production xuống 1 chỉ để làm transaction khởi động được; điều đó làm giảm khả năng chịu lỗi khi broker dừng.

`transaction.state.log.replication.factor` là cấu hình của internal transaction topic. Nó khác replication factor của topic nghiệp vụ như `orders.events` hoặc `payments.events`; cần cấu hình cả hai lớp phù hợp.

## 4. Topic nghiệp vụ cũng cần replication và ISR phù hợp

Transaction state log khỏe không có nghĩa dữ liệu nghiệp vụ đã có độ bền phù hợp. Các topic nhận record transactional vẫn cần replication factor và `min.insync.replicas` phù hợp với yêu cầu dữ liệu.

Ví dụ tạo topic với ba replica:

```bash
kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --create --topic orders.events \
  --partitions 6 --replication-factor 3
```

Sau khi tạo topic, có thể đặt topic config yêu cầu ít nhất hai replica trong ISR:

```bash
kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --entity-type topics --entity-name orders.events \
  --alter --add-config min.insync.replicas=2
```

`replication.factor` là tham số tạo topic; `min.insync.replicas` là topic configuration. Producer transactional thường dùng xác nhận `acks=all`; với Spring Kafka, không nên ghi đè các producer properties theo cách làm mất các điều kiện tương thích với idempotence và transaction. Khi ISR thấp hơn `min.insync.replicas`, producer có thể nhận lỗi thay vì ghi một bản sao không đạt mức độ bền đã yêu cầu.

Trước khi bật transaction, kiểm tra:

- Topic đích đã tồn tại hoặc cơ chế provisioning có quyền tạo topic.
- Partition count phù hợp với khả năng song song và key distribution.
- Replication factor không vượt quá số broker có thể nhận replica.
- `min.insync.replicas` phù hợp với replication factor.
- Producer có quyền ghi vào tất cả topic đích trong transaction.

Một transaction có thể ghi vào nhiều topic và partition trong cùng cluster, nhưng tất cả topic đích phải có thể nhận record và transaction marker.

## 5. Producer phải có transactional.id

Kafka producer thông thường có thể gửi record mà không mở transaction. Producer transactional được nhận diện bằng `transactional.id`. Khi khởi tạo transaction, producer gọi cơ chế khởi tạo transaction để nhận `producerId` và epoch từ coordinator.

`transactional.id` có hai mục đích quan trọng:

1. Nhận diện producer logic giữa các phiên hoạt động để broker quản lý transaction.
2. Cho phép broker fencing producer cũ khi một producer mới khởi tạo với cùng ID, tránh hai producer cùng ghi như một logical producer.

Trong Spring Kafka, ứng dụng thường không tự đặt từng `transactional.id`. `DefaultKafkaProducerFactory` nhận `transactionIdPrefix` rồi tạo ID cụ thể cho các producer mà factory quản lý.

```text
transactionIdPrefix = orders-pod-a-

Producer instance 1 -> orders-pod-a-0
Producer instance 2 -> orders-pod-a-1
Producer instance 3 -> orders-pod-a-2
```

Suffix giúp các producer được tạo từ cùng factory có transactional ID riêng. Prefix phải được chọn cẩn thận để không trùng với prefix của instance khác đang hoạt động trong cluster.

## 6. transaction-id-prefix phải duy nhất giữa các instance

Với Spring Boot, cấu hình prefix bằng `spring.kafka.producer.transaction-id-prefix`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${POD_NAME:orders-local}-tx-
```

Trong môi trường Kubernetes, `POD_NAME` có thể được inject từ metadata pod. Nếu chạy nhiều replica, mỗi pod cần prefix khác nhau. Không dùng một chuỗi cố định giống nhau cho tất cả instance.

Ví dụ:

```text
orders-service-pod-a-tx-
orders-service-pod-b-tx-
orders-service-pod-c-tx-
```

Prefix nên ổn định trong vòng đời của một instance logic để lần khởi động mới có thể fencing producer cũ cùng danh tính. Đồng thời, hai instance hoạt động song song không được dùng cùng prefix. Khi scale hoặc thay pod, cần bảo đảm tên instance được phân biệt.

Nếu hai ứng dụng dùng chung prefix và sinh ra cùng transactional ID, broker có thể trả `ProducerFencedException` cho producer cũ. Lỗi này thường là dấu hiệu có producer khác đã khởi tạo cùng transactional ID hoặc producer cũ đã mất quyền sở hữu epoch.

## 7. Spring Boot cần cấu hình producer transactional

Một cấu hình ứng dụng mẫu:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${POD_NAME:orders-local}-orders-tx-
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        "[transaction.timeout.ms]": 60000
    consumer:
      group-id: order-projection
      enable-auto-commit: false
      properties:
        "[isolation.level]": read_committed
```

Khi có `transaction-id-prefix`, Spring Boot có thể cấu hình transactional `ProducerFactory` và các thành phần transaction liên quan theo phiên bản Boot. Nếu ứng dụng tự khai báo producer factory, template hoặc transaction manager, cần kiểm tra các bean đó có dùng cùng factory và prefix đúng hay không.

Không cấu hình `transaction-id-prefix` là chuỗi rỗng hoặc bỏ trống trong khi gọi `executeInTransaction()`. `KafkaTemplate` phải lấy transactional producer từ `ProducerFactory`; nếu factory không hỗ trợ transaction, template không thể mở transaction và sẽ ném lỗi khi thực thi.

## 8. ProducerFactory, KafkaTemplate và transaction manager phải khớp nhau

Khi tự cấu hình bằng Java, `DefaultKafkaProducerFactory` phải nhận transaction ID prefix. `KafkaTemplate` và `KafkaTransactionManager` phải được tạo từ đúng `ProducerFactory` mà ứng dụng muốn dùng cho transaction.

```java
import java.util.HashMap;
import java.util.Map;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;

@Configuration
class TransactionalKafkaConfiguration {

    @Bean
    ProducerFactory<String, String> transactionalProducerFactory() {
        Map<String, Object> properties = new HashMap<>();
        properties.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        properties.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
        properties.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class);

        var factory = new DefaultKafkaProducerFactory<String, String>(properties);
        factory.setTransactionIdPrefix("orders-local-tx-");
        return factory;
    }

    @Bean
    KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> transactionalProducerFactory) {
        return new KafkaTemplate<>(transactionalProducerFactory);
    }

    @Bean
    KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> transactionalProducerFactory) {
        return new KafkaTransactionManager<>(transactionalProducerFactory);
    }
}
```

Ví dụ trên dùng chung một factory cho template và transaction manager. Nếu template gửi bằng factory A nhưng transaction manager quản lý factory B, lệnh gửi có thể không tham gia transaction mà ứng dụng mong đợi.

Trong production, prefix trong ví dụ Java phải được lấy từ cấu hình riêng của instance thay vì hard-code cùng một giá trị cho mọi replica.

Nếu ứng dụng có nhiều `ProducerFactory` transactional độc lập trong cùng một instance, mỗi factory cũng cần prefix riêng để các producer không tạo ra transactional ID trùng nhau.

## 9. Producer transaction timeout phải nằm trong giới hạn broker

Producer property `transaction.timeout.ms` xác định thời gian tối đa producer yêu cầu cho một transaction. Broker có giới hạn `transaction.max.timeout.ms`; giá trị producer yêu cầu không được vượt giới hạn broker.

Ví dụ:

```yaml
spring:
  kafka:
    producer:
      properties:
        "[transaction.timeout.ms]": 60000
```

Nếu broker cho phép tối đa 900000 ms thì yêu cầu 60000 ms nằm trong giới hạn. Các con số chỉ là ví dụ; hãy đọc cấu hình thực tế của cluster và chọn timeout theo thời gian xử lý dự kiến.

Transaction timeout phải đủ cho các thao tác Kafka trong transaction, bao gồm gửi record và commit. Nhưng timeout quá dài cũng có chi phí: transaction lỗi có thể giữ trạng thái mở lâu hơn, khiến consumer `read_committed` chờ ở Last Stable Offset.

Không giữ transaction mở trong khi chờ người dùng, gọi HTTP service chậm hoặc thực hiện công việc không liên quan. Hãy chuẩn bị dữ liệu trước, sau đó mở transaction và thực hiện nhóm thao tác Kafka ngắn gọn.

## 10. Producer transaction cần idempotence

Kafka transaction dựa trên producer ID và epoch để quản lý thứ tự, retry và fencing. Producer transactional được cấu hình với idempotence; không tắt idempotence hoặc ghi đè các producer property theo cách xung đột với yêu cầu transaction.

Idempotence giúp tránh duplicate do retry request của producer trong phạm vi bảo đảm của Kafka. Transaction bổ sung ranh giới commit/abort cho nhiều record. Hai tính năng liên quan nhưng không đồng nghĩa:

| Cơ chế | Bảo đảm chính |
|---|---|
| Idempotent producer | Hạn chế duplicate do retry của cùng producer session/sequence |
| Kafka transaction | Commit hoặc abort nhóm record thuộc transaction và có thể phối hợp offset consumer |
| Consumer idempotency | Bảo vệ side effect nghiệp vụ khi ứng dụng xử lý lại record |

Idempotent producer không làm cho database update, email hoặc HTTP request bên ngoài Kafka trở thành exactly-once. Consumer vẫn cần idempotency nếu nghiệp vụ có side effect ngoài Kafka hoặc có thể replay record.

## 11. Consumer phải dùng read_committed khi cần ẩn record bị abort

Producer transaction có thể gửi record trước khi commit. Consumer dùng `read_uncommitted` có thể nhìn thấy record transactional chưa được commit, kể cả record sau đó bị abort.

Nếu downstream chỉ được xử lý dữ liệu đã commit, cấu hình consumer:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[isolation.level]": read_committed
```

`read_committed` khiến consumer chỉ trả về record thuộc transaction đã commit và dừng ở Last Stable Offset (LSO) khi còn transaction chưa hoàn tất ở đầu log của partition. Vì vậy, transaction mở quá lâu có thể làm consumer tưởng như không có dữ liệu mới dù log end offset đã tăng.

Không phải mọi consumer đều bắt buộc dùng `read_committed`. Hãy chọn theo yêu cầu nhất quán. Với consumer phục vụ dữ liệu nghiệp vụ cần phản ánh đúng commit/abort, `read_committed` thường là lựa chọn phù hợp.

## 12. Consume-transform-produce cần phối hợp offset trong transaction

Nếu ứng dụng chỉ gửi nhiều record, `KafkaTemplate.executeInTransaction()` có thể đủ. Nhưng nếu consumer đọc record đầu vào, xử lý rồi gửi record đầu ra và muốn output cùng tiến độ input được commit nguyên tử, cần dùng mô hình transactional listener container hoặc API Kafka transaction gửi offset vào transaction.

Với Spring Kafka, `KafkaTransactionManager` có thể được gắn vào listener container. Container điều phối việc gửi offset của record đã xử lý vào transaction cùng các output record. Khi transaction commit, output record và input offset cùng được xác nhận; nếu abort, consumer có thể đọc lại input và phát lại output trong transaction mới.

Điều kiện cần kiểm tra:

- Consumer group có quyền đọc input topic và quản lý offset.
- Producer transactional có quyền ghi output topic.
- Transaction manager và listener container dùng đúng producer factory.
- Container quản lý offset commit theo transaction; không để auto-commit độc lập phá vỡ ranh giới này.
- Consumer downstream dùng `read_committed` nếu cần bỏ qua output bị abort.

`executeInTransaction()` đơn thuần không tự biết offset của record mà một listener đang xử lý. Không giả định callback producer-only tự động commit consumer offset.

## 13. ACL phải cho phép transaction và topic operations

Khi cluster bật authorization, producer cần các quyền tương ứng với transactional ID và topic. Với luồng consume-transform-produce, consumer group cũng cần quyền để gửi offset vào transaction.

| Resource | Quyền thường cần | Dùng cho |
|---|---|---|
| Transactional ID | `WRITE` | Khởi tạo và thực hiện transaction với transactional ID |
| Output topic | `WRITE` | Ghi record vào topic đích |
| Input topic | `READ` | Consumer đọc record nguồn |
| Consumer group | `READ` | Join group và gửi offset vào transaction theo cơ chế Kafka |
| Topic/cluster metadata | Quyền mô tả phù hợp với authorizer | Lấy metadata và vận hành client |

Quyền cụ thể có thể phụ thuộc thao tác, phiên bản Kafka và authorizer. Hãy cấp quyền tối thiểu theo transactional ID, topic và group mà ứng dụng thực sự dùng. Không cấp wildcard toàn cluster chỉ để tránh lỗi authorization.

Các lỗi thường gặp khi ACL thiếu quyền:

- `TransactionalIdAuthorizationException`: principal không được phép thao tác với transactional ID.
- `TopicAuthorizationException`: producer không được phép ghi topic đích hoặc consumer không được phép đọc topic nguồn.
- `GroupAuthorizationException`: consumer không được phép sử dụng group hoặc thao tác offset tương ứng.

Kiểm tra principal mà Spring Kafka thực sự sử dụng, nhất là khi ứng dụng chạy bằng SASL/OAUTH hoặc mTLS và các môi trường có principal mapping khác nhau.

## 14. Broker và producer phải thống nhất về transaction timeout

Có hai phía timeout cần phân biệt:

| Cấu hình | Nơi cấu hình | Ý nghĩa |
|---|---|---|
| `transaction.timeout.ms` | Producer | Timeout mà producer yêu cầu cho transaction |
| `transaction.max.timeout.ms` | Broker | Giới hạn lớn nhất broker chấp nhận từ producer |
| `transaction.state.log.replication.factor` | Broker | Replication factor của internal transaction state topic |
| `transaction.state.log.min.isr` | Broker | Số replica in-sync tối thiểu cho internal transaction state topic |

Nếu producer yêu cầu timeout lớn hơn broker cho phép, broker từ chối cấu hình/khởi tạo transaction. Nếu timeout quá ngắn, transaction hợp lệ nhưng xử lý hơi chậm cũng có thể bị timeout. Hãy đo thời gian gửi và commit dưới tải thật để chọn giá trị hợp lý.

## 15. Theo dõi transaction coordinator và producer fencing

Trong production, cần giám sát các dấu hiệu cho biết transaction không thể bắt đầu hoặc kết thúc:

| Dấu hiệu | Nguyên nhân cần kiểm tra |
|---|---|
| `ProducerFencedException` | Có producer khác dùng cùng transactional ID hoặc epoch cũ đã bị fence |
| `TransactionalIdAuthorizationException` | ACL trên transactional ID không đủ |
| `CoordinatorNotAvailableException` | Transaction coordinator chưa sẵn sàng hoặc đang chuyển trạng thái |
| `NotCoordinatorException` | Coordinator thay đổi; client cần refresh metadata/retry theo cơ chế Kafka |
| `TimeoutException` khi commit | Broker/network chậm, transaction quá dài hoặc kết quả commit chưa rõ với caller |
| `InvalidTxnStateException` | Producer gọi thao tác không hợp lệ trong trạng thái transaction hiện tại |
| Consumer lag tăng nhưng log end offset tăng | Transaction mở lâu có thể giữ LSO, hoặc consumer chưa đọc được dữ liệu đã commit |

Nên theo dõi transaction duration, commit/abort rate, producer error rate, coordinator availability, consumer lag và tuổi transaction chưa hoàn tất. Tên metric cụ thể tùy phiên bản Kafka client và hệ thống metrics.

Nếu producer bị fencing, đừng chỉ tăng retry hoặc timeout. Hãy kiểm tra transactional ID prefix có bị trùng giữa pod, có hai tiến trình cùng chạy một logical producer hay có producer cũ chưa dừng đúng cách hay không.

Broker còn quản lý thời gian lưu trạng thái cho transactional ID không hoạt động thông qua `transactional.id.expiration.ms`. Với ứng dụng giữ producer transactional trong pool lâu ngày, có thể cấu hình tuổi tối đa producer (`maxAge`) của `DefaultKafkaProducerFactory` ngắn hơn thời gian broker hết hạn ID nếu phiên bản Spring Kafka đang dùng hỗ trợ thuộc tính này. Cách đó giúp factory thay producer cũ trước khi transactional ID bị broker loại bỏ.

## 16. Môi trường local và production khác nhau ở đâu?

| Hạng mục | Local single broker | Production cluster |
|---|---|---|
| Transaction state log RF | Có thể đặt 1 để học/test | Thường dùng nhiều replica, ví dụ 3 |
| Transaction state log min ISR | Có thể đặt 1 | Ví dụ 2 khi RF=3 |
| Topic replication | 1 có thể chấp nhận cho local | Chọn theo yêu cầu chịu lỗi |
| Transaction ID prefix | `orders-local-tx-` | Unique theo pod/instance |
| ACL | Có thể tắt trong sandbox | Cấp quyền tối thiểu cho transaction/topic/group |
| Monitoring | Log và metrics cơ bản | Theo dõi coordinator, fencing, timeout, commit/abort và lag |
| Consumer isolation | Kiểm thử cả hai chế độ | `read_committed` cho consumer cần chỉ thấy dữ liệu đã commit |

Không lấy cấu hình local làm cấu hình production. Local thường chỉ có một broker nên phải giảm replication để internal topic có thể được tạo; production cần thiết kế replication và ISR để chịu lỗi.

## 17. Checklist trước khi bật transaction

Trước khi triển khai, xác nhận lần lượt:

1. Kafka cluster chạy phiên bản hỗ trợ transaction và các broker hoạt động ổn định.
2. Internal `__transaction_state` có replication factor và min ISR phù hợp với số broker.
3. Topic nghiệp vụ đã tồn tại, có partition và replication phù hợp.
4. Producer factory được cấu hình transaction ID prefix.
5. Prefix khác nhau giữa các instance hoạt động đồng thời.
6. `KafkaTemplate` và `KafkaTransactionManager` dùng cùng `ProducerFactory` khi cần cùng transaction context.
7. `transaction.timeout.ms` không vượt `transaction.max.timeout.ms` của broker.
8. Producer không bị cấu hình xung đột với idempotence/transaction.
9. ACL cho phép transactional ID, output topic, input topic và consumer group.
10. Consumer cần dữ liệu đã commit được cấu hình `read_committed`.
11. Luồng consume-transform-produce dùng container/offset coordination đúng cách.
12. Transaction không bao trùm các thao tác blocking hoặc HTTP/database dài ngoài ranh giới Kafka.
13. Có cảnh báo cho fencing, coordinator errors, transaction timeout, abort rate và consumer lag.
14. Integration test xác minh commit, abort, `read_committed`, ACL và nhiều instance.

## 18. Những nhầm lẫn thường gặp

1. **Chỉ cấu hình `transaction-id-prefix` là đủ.** Broker vẫn cần transaction coordinator và internal transaction state log có thể ghi được.
2. **Dùng replication factor 3 trên cluster một broker.** Internal topic không thể tạo đủ replica; local cần cấu hình riêng.
3. **Dùng cùng prefix cho mọi pod.** Các producer có thể fencing lẫn nhau do transactional ID trùng.
4. **Nhầm transaction state log với topic nghiệp vụ.** Đây là internal topic của broker, có replication settings riêng.
5. **Cho rằng mọi consumer tự động ẩn record abort.** Chỉ consumer `read_committed` mới lọc record transactional chưa commit/đã abort.
6. **Đặt transaction timeout lớn tùy ý.** Producer không thể vượt giới hạn broker; timeout dài còn làm transaction mở lâu và giữ LSO.
7. **Dùng hai ProducerFactory khác nhau cho template và transaction manager.** Lệnh gửi có thể không tham gia transaction được quản lý.
8. **Bỏ qua ACL transactional ID.** Có quyền ghi topic chưa chắc đã đủ quyền khởi tạo transaction.
9. **Cho rằng Kafka transaction bao gồm database.** Transaction Kafka chỉ bao phủ tài nguyên Kafka được tham gia đúng cách.
10. **Chỉ kiểm thử bằng mock.** Mock không xác minh coordinator, commit marker, abort marker, fencing và isolation behavior của broker.

Transaction hoạt động đúng khi broker, producer, Spring Kafka, topic, ACL và consumer cùng đáp ứng các điều kiện tương thích. Hãy kiểm tra transaction state log và coordinator ở cluster, cấp transactional ID prefix riêng cho từng instance, nối `KafkaTemplate` với đúng `ProducerFactory`, giới hạn timeout theo broker và dùng `read_committed` ở consumer cần dữ liệu đã commit. Khi các điều kiện này được xác minh bằng integration test và monitoring, transaction mới trở thành cơ chế tin cậy cho luồng messaging production.
