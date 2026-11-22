# Producer transaction cache

Trong Spring Kafka, khi producer sử dụng Kafka transaction, mỗi transaction cần một producer có **`transactional.id`** hợp lệ và đã được khởi tạo với broker. Việc liên tục tạo một `KafkaProducer` mới, gọi `initTransactions()`, thực hiện transaction rồi đóng hẳn producer thường tốn tài nguyên và tăng độ trễ. **Producer transaction cache** của `DefaultKafkaProducerFactory` giúp tái sử dụng các producer giao dịch đã khởi tạo khi transaction trước đã kết thúc.

Cache này nằm **trong tiến trình ứng dụng Spring Kafka**, không phải trong Kafka broker, và không phải một bộ nhớ lưu record. Nó quản lý vòng đời các transactional producer để ứng dụng có thể liên tục bắt đầu transaction mà không phải thiết lập producer từ đầu mỗi lần.

Trong vận hành thực tế, producer transaction cache liên quan trực tiếp đến độ trễ xử lý, số transaction chạy đồng thời, giới hạn producer, lỗi `NoProducerAvailableException`, hiện tượng **producer fencing**, cách đặt transaction ID khi scale nhiều pod và khả năng xử lý khi broker hết hạn trạng thái transactional ID.

## 1. Vì sao transactional producer cần được quản lý riêng?

Một Kafka producer không giao dịch có thể gửi nhiều record mà không cần `beginTransaction()`. Transactional producer phải có `transactional.id`; khi dùng giao dịch, producer thực hiện quy trình đại ý:

```text
Tạo KafkaProducer có transactional.id
          |
          v
      initTransactions()
          |
          v
      beginTransaction()
          |
          v
  send(record A), send(record B)
          |
          v
  commitTransaction() hoặc abortTransaction()
          |
          v
Producer có thể phục vụ transaction tiếp theo
```

`initTransactions()` tương tác với transaction coordinator của Kafka để khởi tạo hoặc tiếp quản trạng thái producer theo `transactional.id`. Đây không phải thao tác miễn phí; nếu tạo producer mới mỗi transaction, ứng dụng có thể chịu thêm chi phí kết nối, metadata, tài nguyên thread/buffer và transaction initialization.

Spring Kafka giải quyết bằng cách để `DefaultKafkaProducerFactory` **giữ lại producer đã kết thúc transaction**. Khi code gọi `close()` trên producer do factory cung cấp, factory có thể trả producer về cache thay vì đóng client vật lý ngay lập tức. Transaction kế tiếp mượn producer phù hợp và tái sử dụng nó.

Điều kiện quan trọng là producer chỉ được tái sử dụng **sau khi transaction trước đã kết thúc**. Không thể sử dụng cùng một transactional producer cho hai transaction đồng thời.

## 2. Producer transaction cache hoạt động thế nào?

Luồng đơn giản khi ứng dụng có `KafkaTransactionManager`:

```text
                       Spring application
                               |
                               v
                   Bắt đầu Spring transaction
                               |
                               v
                    DefaultKafkaProducerFactory
                               |
                       mượn producer
                       /             \
                  cache hit         cache miss
                     |                 |
                     |          Tạo transactional producer
                     |          và initTransactions()
                     \                 /
                      \               /
                       v             v
                    beginTransaction()
                               |
                               v
                       KafkaTemplate.send()
                               |
                               v
                    commit / abort transaction
                               |
                               v
                   Trả producer lại cho factory
                               |
                 +-------------+-------------+
                 |                           |
        Còn sử dụng được               Không còn hợp lệ
                 |                           |
                 v                           v
           Cache producer              Đóng/loại producer
```

Không phải mọi transaction đều có cache hit. Lúc khởi động, cache chưa có producer; producer được tạo theo nhu cầu. Khi có nhiều transaction cùng chạy, mỗi transaction cần một producer riêng, nên factory có thể phải tạo thêm producer. Nếu producer gặp lỗi nghiêm trọng, bị fencing hoặc đã quá tuổi theo chính sách factory, nó có thể bị đóng và thay thế.

Cache thường được quản lý **theo từng `ProducerFactory` trong mỗi JVM**. Nếu có ba pod, mỗi pod có factory riêng và cache riêng; không có một bộ cache chia sẻ tự động giữa các pod. Hai ứng dụng dùng chung cluster Kafka cũng không chia sẻ cache Java với nhau.

### Cache không đồng nghĩa số transaction được phép đồng thời vô hạn

Một producer có thể chạy nhiều transaction **tuần tự**, nhưng không thể đồng thời chạy nhiều transaction độc lập. Nếu tại thời điểm cao điểm có 10 transaction song song, ứng dụng cần đủ transactional producer hoặc sẽ phải chờ/thất bại theo chính sách cấp phát của factory.

Điều này giải thích vì sao việc tính cache dựa trên **concurrency** và số transaction cùng hoạt động quan trọng hơn chỉ nhìn số message mỗi giây.

## 3. transactional.id và transaction ID prefix

Kafka dùng `transactional.id` để nhận diện một chuỗi phiên giao dịch. Broker quản lý producer ID và epoch gắn với ID này; producer mới dùng cùng `transactional.id` có thể **fence** producer cũ để tránh hai producer khác nhau cùng chiếm quyền ghi giao dịch dưới một định danh.

Spring Kafka cho phép cấu hình `transactionIdPrefix` trên `DefaultKafkaProducerFactory`. Factory dùng prefix cùng **suffix** để tạo các ID cụ thể:

```text
transactionIdPrefix = order-tx-pod-a-

Producer 1 -> transactional.id = order-tx-pod-a-0
Producer 2 -> transactional.id = order-tx-pod-a-1
Producer 3 -> transactional.id = order-tx-pod-a-2
```

Các hậu tố chỉ mang tính minh họa; cách sinh và tái sử dụng suffix phụ thuộc `TransactionIdSuffixStrategy` và phiên bản Spring Kafka.

### Quy tắc khi triển khai nhiều instance

**Transaction ID prefix phải tránh trùng giữa những ứng dụng hoặc pod có producer giao dịch đang hoạt động đồng thời.** Nếu hai pod cùng dùng prefix giống hệt và nhận cùng suffix, chúng có thể tạo cùng `transactional.id`. Producer khởi tạo sau có thể fence producer trước, khiến transaction đang chạy thất bại.

Ví dụ không phù hợp khi nhiều pod chạy đồng thời:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: order-tx-
```

Nếu tất cả pod đều dùng đúng prefix này với cùng chiến lược suffix, có nguy cơ đụng ID. Một cách an toàn hơn là để mỗi pod nhận một prefix riêng.

Trong Kubernetes, có thể đưa tên pod vào environment variable bằng Downward API:

```yaml
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: SPRING_KAFKA_PRODUCER_TRANSACTION_ID_PREFIX
    value: "order-tx-$(POD_NAME)-"
```

Kubernetes hỗ trợ tham chiếu giá trị environment variable đã khai báo trước bằng cú pháp `$(POD_NAME)`. Cách này tạo prefix khác nhau cho các pod đang chạy đồng thời. Nếu ứng dụng quản lý transaction factory theo Java config, có thể xây dựng prefix từ metadata instance theo cơ chế cấu hình tương đương.

Một prefix **duy nhất theo instance đang hoạt động** là điều cần bảo đảm; việc chọn định danh ổn định qua restart hay thay đổi theo pod mới phải cân nhắc thêm vòng đời deployment, trạng thái giao dịch và cách dọn dẹp transactional ID ở broker.

## 4. Cấu hình transaction bằng Spring Boot

Một cấu hình tối thiểu thường gồm producer serializer, transaction ID prefix và các tham số bảo đảm gửi tin phù hợp:

```yaml
spring:
  kafka:
    bootstrap-servers: kafka:9092
    producer:
      transaction-id-prefix: "orders-tx-instance-1-"
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
      acks: all
      properties:
        "[enable.idempotence]": true
    consumer:
      enable-auto-commit: false
      properties:
        "[isolation.level]": read_committed
```

Ở môi trường nhiều instance, không hard-code cùng một giá trị `orders-tx-instance-1-` cho mọi replica; hãy cung cấp prefix riêng qua biến môi trường hoặc cơ chế cấu hình deployment.

Với cấu hình Spring Boot thích hợp, transaction ID prefix cho phép Boot tạo các bean transaction liên quan, trong đó có `KafkaTransactionManager`, theo auto-configuration của phiên bản Boot đang sử dụng. Nếu ứng dụng có custom `ProducerFactory` hoặc nhiều template, phải xác nhận transaction manager và template đang dùng **cùng factory transactional** cần thiết.

`isolation.level=read_committed` là cấu hình **consumer** để không giao các record thuộc transaction chưa commit hoặc đã abort cho listener. Nó không điều khiển producer cache. `enable.auto.commit=false` giúp container kiểm soát offset khi áp dụng consumer-initiated Kafka transactions; riêng producer-initiated transactions không mặc nhiên đòi mọi consumer trong hệ thống phải có cấu hình giống nhau.

## 5. Cấu hình trực tiếp DefaultKafkaProducerFactory

Khi cần điều khiển tuổi producer và số suffix, có thể tạo factory bằng Java. Ví dụ dưới đây dùng các API dành cho **Spring Kafka 3.2 trở lên**:

```java
@Configuration
public class KafkaTransactionConfiguration {

    @Bean
    public ProducerFactory<String, String> transactionalProducerFactory() {
        Map<String, Object> props = new HashMap<>();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "kafka:9092");
        props.put(
                ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(
                ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
                StringSerializer.class);
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);

        DefaultKafkaProducerFactory<String, String> factory =
                new DefaultKafkaProducerFactory<>(props);

        factory.setTransactionIdPrefix("orders-tx-instance-a-");
        factory.setMaxAge(Duration.ofMinutes(30));
        factory.setTransactionIdSuffixStrategy(
                new DefaultTransactionIdSuffixStrategy(8));

        return factory;
    }

    @Bean
    public KafkaTransactionManager<String, String> kafkaTransactionManager(
            ProducerFactory<String, String> transactionalProducerFactory) {
        return new KafkaTransactionManager<>(transactionalProducerFactory);
    }

    @Bean
    public KafkaTemplate<String, String> kafkaTemplate(
            ProducerFactory<String, String> transactionalProducerFactory) {
        return new KafkaTemplate<>(transactionalProducerFactory);
    }
}
```

Các import chính:

```java
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.DefaultKafkaProducerFactory;
import org.springframework.kafka.core.DefaultTransactionIdSuffixStrategy;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.ProducerFactory;
import org.springframework.kafka.transaction.KafkaTransactionManager;
```

Giá trị `8` trong `DefaultTransactionIdSuffixStrategy(8)` ở đây là giới hạn **số suffix có thể được cấp** cho factory theo chiến lược suffix có giới hạn; không nên hiểu nó là số partition Kafka. Giới hạn phù hợp phải được chọn theo concurrency và nhu cầu transaction lồng nhau.

**Lưu ý theo phiên bản:** `TransactionIdSuffixStrategy` và `DefaultTransactionIdSuffixStrategy` được giới thiệu ở Spring Kafka 3.2. Với phiên bản thấp hơn, cách cấp và quản lý suffix có thể khác. Không sao chép đoạn cấu hình này vào một phiên bản cũ mà không kiểm tra API. Cũng không khai báo thêm một bean factory tùy chỉnh nếu dự án đã có một factory Boot tự cấu hình mà không có chủ đích thay thế; tránh tạo các factory cùng hoặc khác prefix mà template/manager dùng sai.

## 6. Khi nào producer được mượn và trả về cache?

Với transaction được điều phối bởi `KafkaTransactionManager` hoặc `KafkaTemplate.executeInTransaction(...)`, vòng đời nhìn từ ứng dụng thường là:

1. Transaction bắt đầu; Spring Kafka lấy transactional producer từ factory.
2. Producer được gắn với ngữ cảnh transaction để các lệnh gửi liên quan dùng đúng producer.
3. Ứng dụng gửi record qua `KafkaTemplate`.
4. Transaction được commit hoặc abort.
5. Producer được giải phóng về factory; nếu còn hợp lệ, nó có thể được cache để dùng tiếp.

Ví dụ transaction do `KafkaTemplate` điều phối:

```java
public void publishOrder(String orderId, String payload) {
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders", orderId, payload);
        operations.send("order-audit", orderId, "created");
        return null;
    });
}
```

Trong ví dụ, hai send nằm trong **cùng Kafka transaction**. Factory có thể dùng lại producer đó cho một transaction kế tiếp sau khi transaction hiện tại đã hoàn tất. Không dùng `KafkaTemplate.executeInTransaction` chỉ để “kích hoạt cache”; điểm chính của lời gọi là tạo ranh giới Kafka transaction.

### Vì sao code ứng dụng không nên tự close producer tùy ý?

Với transactional producer được Spring Kafka cấp, vòng đời producer gắn với transaction và cách factory quản lý cache. Nếu code tự lấy raw Kafka producer rồi gọi `close()`, `beginTransaction()` hoặc `commitTransaction()` ngoài cơ chế quản lý đã chọn, có thể phá vỡ vòng đời transaction và tái sử dụng.

Hãy ưu tiên các API được hỗ trợ như `KafkaTemplate` và `KafkaTransactionManager`. Nếu cần xử lý producer trực tiếp, phải hiểu hợp đồng của `ProducerFactory` và cách Spring giải phóng producer sau transaction. **Không chia sẻ cùng một producer đang có transaction cho nhiều thread độc lập.**

## 7. Kích thước cache và concurrency

Một lỗi vận hành thường gặp là cấu hình cache quá nhỏ so với số transaction có thể chạy đồng thời.

Ví dụ một pod chạy listener container với `concurrency=4`, mỗi child consumer xử lý trong một Kafka transaction:

```text
Pod A
  listener-0 -> transaction T0 -> producer P0
  listener-1 -> transaction T1 -> producer P1
  listener-2 -> transaction T2 -> producer P2
  listener-3 -> transaction T3 -> producer P3

Số producer transaction cần đồng thời: tối thiểu 4
```

Nếu dùng strategy suffix bị giới hạn, hãy đặt dung lượng ít nhất đủ cho số transaction đồng thời. Khi có transaction lồng nhau hoặc các luồng producer độc lập cùng dùng factory, nhu cầu thực tế có thể cao hơn concurrency của listener.

| Kịch bản trong một JVM | Listener concurrency | Transaction độc lập khác | Số producer cần đồng thời có thể đạt |
|---|---:|---:|---:|
| Một listener, một transaction cho mỗi child consumer | 2 | 0 | 2 |
| Một listener, một transaction cho mỗi child consumer | 4 | 0 | 4 |
| Listener và một tác vụ publish chạy đồng thời | 4 | 1 | 5 |
| Listener với transaction Kafka lồng nhau | 4 | Phụ thuộc số transaction lồng | Có thể lớn hơn 4 |
Những con số trên là ước lượng năng lực đồng thời; không phải cam kết mỗi child container luôn giữ producer suốt vòng đời của nó. Producer được mượn khi transaction cần chạy và có thể được trả về cache sau khi kết thúc.

Trong các phiên bản hỗ trợ `DefaultTransactionIdSuffixStrategy(maxCache)`, một `maxCache` dương giới hạn tập suffix mà strategy cấp. Nếu tất cả suffix đã được sử dụng và không còn producer có thể mượn hợp lệ, Spring Kafka có thể ném `NoProducerAvailableException`. Với strategy mặc định không giới hạn suffix, factory có thể tạo thêm transactional ID khi nhu cầu tăng, đổi lại việc giới hạn tài nguyên không còn rõ như cấu hình bounded.

**Không lấy số replica nhân concurrency để đặt maxCache cho một factory trong một pod.** Mỗi pod có factory và cache riêng. Nếu bốn pod cùng chạy concurrency=3, nhóm có thể tạo 12 consumer, nhưng từng pod thường cần tối thiểu ba transactional producer cho workload tương ứng, chưa tính transaction độc lập khác.

## 8. NoProducerAvailableException khi hết producer trong cache

`NoProducerAvailableException` có thể xuất hiện khi strategy cấp transaction ID suffix có giới hạn và toàn bộ suffix cần thiết đang bị chiếm. Đây là lỗi **thiếu transactional producer có thể cấp phát** trong factory của ứng dụng, không đồng nghĩa Kafka broker hết partition hoặc topic bị hỏng.

Ví dụ:

```text
maxCache = 2

Transaction A -> suffix 0 (đang dùng)
Transaction B -> suffix 1 (đang dùng)
Transaction C -> yêu cầu producer thứ ba
               -> không còn suffix
               -> NoProducerAvailableException
```

Các hướng xử lý:

- Xác định số transaction thực sự đồng thời trên **cùng factory** và so với `maxCache`.
- Kiểm tra listener concurrency, transaction lồng nhau, code producer chạy từ scheduler và request thread.
- Giảm transaction chạy đồng thời, hoặc tăng `maxCache` theo nhu cầu đã đo.
- Nếu cần retry việc mượn producer, dùng chính sách backoff có giới hạn; không retry vòng lặp gấp khiến thread và CPU bị nghẽn.
- Xem log bắt đầu/kết thúc transaction; một transaction chạy quá lâu có thể giữ producer và suffix lâu hơn dự kiến.

Đừng khắc phục bằng cách đặt lại `transactional.id` ngẫu nhiên trong từng lần gửi. Cách đó tránh đụng suffix nhưng làm mất lợi ích cache và tạo nhiều transactional ID không cần thiết ở broker.

## 9. Cache có thể bị ảnh hưởng bởi transactional.id expiration

Kafka broker có cấu hình `transactional.id.expiration.ms` để quản lý thời gian hết hạn trạng thái transactional ID không hoạt động. Nếu một transactional producer nằm idle trong cache quá lâu, broker có thể hết hạn trạng thái liên quan đến transactional ID của producer đó. Khi được tái sử dụng, producer có thể gặp lỗi transaction hoặc bị broker fencing tùy hoàn cảnh.

Spring Kafka cung cấp `DefaultKafkaProducerFactory.setMaxAge(Duration)` (có từ các phiên bản Spring Kafka 2.5.x) để tránh tái sử dụng producer đã quá tuổi. Khi factory kiểm tra một producer đã vượt tuổi cho phép, nó có thể loại producer đó và tạo producer mới thay vì tái sử dụng mãi.

Ví dụ:

```java
DefaultKafkaProducerFactory<String, String> factory =
        new DefaultKafkaProducerFactory<>(producerConfigs);

factory.setTransactionIdPrefix("orders-tx-pod-a-");
factory.setMaxAge(Duration.ofMinutes(30));
```

Chọn `maxAge` **nhỏ hơn** khoảng expiration phù hợp của broker, có dư địa cho độ trễ, restart và các biến động vận hành. Không phải mọi cluster đều giữ giá trị mặc định của `transactional.id.expiration.ms`; hãy tra cấu hình thật của cluster trước khi quyết định.

`maxAge` là chính sách vòng đời của producer trong factory, **không phải thời gian timeout của một Kafka transaction**. Nó cũng không đảm bảo một timer nền sẽ ngay lập tức xóa mọi producer đúng thời điểm maxAge; điểm quan trọng là factory tránh trả về producer quá tuổi khi cần sử dụng lại.

Phân biệt:

| Cấu hình | Mục đích |
|---|---|
| `DefaultKafkaProducerFactory.setMaxAge(...)` | Giới hạn tuổi của producer được cache trước khi tái sử dụng. |
| Broker `transactional.id.expiration.ms` | Quy định thời gian hết hạn metadata transactional ID không hoạt động. |
| Producer `transaction.timeout.ms` | Giới hạn thời gian một transaction được phép tồn tại trên broker. |
| Producer `request.timeout.ms` | Timeout cho yêu cầu client/broker; không phải timeout toàn transaction. |

Nếu listener giữ transaction quá lâu, cần kiểm tra transaction timeout và thời gian xử lý; tăng `maxAge` không chữa được transaction đang bị timeout.

## 10. Producer fencing và transaction ID trùng

**Producer fencing** bảo vệ Kafka khỏi hai producer cùng cố sử dụng một `transactional.id` để chạy transaction. Broker dùng epoch để vô hiệu producer cũ khi producer mới với cùng ID được khởi tạo.

Tình huống phổ biến khi rolling deployment:

```text
Pod old: transactional.id = orders-tx-0
  |
  +-- transaction đang chạy

Pod new: transactional.id = orders-tx-0
  |
  +-- initTransactions() với cùng ID
  |
  v
Pod old có thể nhận ProducerFencedException
```

Nếu deploy nhiều pod với một prefix dùng chung và suffix bị trùng, fencing có thể xảy ra ngay cả khi cả hai pod đều healthy. Trong mô hình multi-instance, cấu hình `transactionIdPrefix` duy nhất theo instance là biện pháp cơ bản.

Một số thông điệp hoặc exception cần phân biệt:

- `ProducerFencedException`: producer đã bị fence vì có phiên producer mới hơn dùng transactional ID liên quan.
- `InvalidProducerEpochException` hoặc lỗi epoch liên quan: epoch của producer không hợp lệ trong ngữ cảnh giao dịch.
- Transaction coordinator timeout hoặc unavailable: liên quan broker/network/coordinator, không nhất thiết do cache quá nhỏ.
- `NoProducerAvailableException`: factory phía ứng dụng không cấp được producer khi giới hạn suffix bị sử dụng hết.

Sau lỗi fencing hoặc lỗi giao dịch không thể phục hồi, đừng cố dùng tiếp cùng raw producer. Hãy để Spring Kafka và factory quản lý việc loại bỏ producer không còn hợp lệ, đồng thời điều tra nguyên nhân ID trùng hoặc vòng đời transaction bất thường.

## 11. Transaction cache và Kafka-to-Kafka exactly-once

Producer transaction cache giúp **tái sử dụng producer**, không tự tạo exactly-once semantics. Exactly-once cho luồng đọc Kafka rồi ghi Kafka cần phối hợp consumer offset với việc publish output trong cùng Kafka transaction.

Ví dụ luồng xử lý:

```text
orders topic -> consumer trong group order-service
                     |
                     v
                xử lý record
                     |
                     v
          producer gửi normalized-orders
                     |
                     v
    sendOffsetsToTransaction(group metadata)
                     |
                     v
          Kafka transaction commit
                     |
                     v
        consumer tiến đến offset kế tiếp
```

Trong Spring Kafka, mô hình này có thể được điều phối bằng listener container transaction manager và `KafkaTemplate` dùng cùng transactional producer factory. Các output record cùng offset consumer được commit theo cơ chế transaction của Kafka. Nếu transaction abort, `read_committed` consumer sẽ không thấy output record đã abort; offset của transaction không được hoàn tất theo nhánh commit.

Các điểm cần kiểm tra:

- Listener container thật sự dùng `KafkaTransactionManager` hoặc cơ chế transaction phù hợp với phiên bản.
- Producer factory có `transactionIdPrefix` và transaction ID không đụng giữa các instance.
- Consumer sử dụng `enable.auto.commit=false` để offset không bị commit ngoài ranh giới transaction.
- Downstream consumers muốn bỏ qua aborted records dùng `isolation.level=read_committed`.
- Xử lý exception và rollback không nuốt lỗi theo cách làm transaction bị commit khi nghiệp vụ chưa hoàn tất.

Một Kafka transaction **không làm cho giao dịch database ngoài Kafka tự động nguyên tử** với Kafka. Nếu listener vừa update database vừa publish event, phải đánh giá thứ tự commit, idempotency hoặc outbox/inbox thay vì coi việc producer được cache là bảo đảm dữ liệu không bị lặp/mất.

## 12. Producer cache và transaction lồng nhau

Khi ứng dụng mở một Kafka transaction mới trong khi một transaction Kafka khác đang hoạt động, có thể cần thêm producer. Không nên coi một transaction manager hoặc một `KafkaTemplate` tương đương “chỉ cần một producer”.

Ví dụ một consumer thread đã dùng producer cho Kafka transaction A, sau đó đi vào một đoạn code cố tình mở Kafka transaction B độc lập. Tùy API và ranh giới giao dịch, factory có thể cần producer thứ hai để tránh hai transaction cùng sử dụng một producer.

Nếu cache được cấu hình quá nhỏ, luồng có thể hết suffix dù listener concurrency bằng một. Vì vậy:

1. Xác định transaction nào thực sự lồng nhau và có dùng cùng factory không.
2. Kiểm tra transaction propagation tại Spring service và việc dùng `executeInTransaction(...)`.
3. Tính số producer đồng thời tối đa trên mỗi JVM, gồm listener, scheduler và request thread.
4. Tăng `maxCache` có chủ đích hoặc đơn giản hóa cấu trúc transaction.

Không khuyến khích mở Kafka transaction lồng nhau tùy tiện. Nó làm tăng độ phức tạp commit/rollback và có thể khiến người đọc hiểu sai rằng hai transaction tách biệt có atomicity chung.

## 13. Theo dõi cache và transaction trong production

Không nên chỉ quan sát số message được publish. Một ứng dụng có producer cache vận hành bất thường có thể vẫn gửi được message nhưng có độ trễ cao vì liên tục tạo producer mới, gặp lỗi fencing, hoặc không cấp được producer khi concurrency tăng.

Những tín hiệu nên thu thập:

| Tín hiệu | Ý nghĩa |
|---|---|
| Số Kafka transaction bắt đầu/commit/abort | Phản ánh tải và tỷ lệ giao dịch thất bại. |
| Transaction latency | Phát hiện transaction coordinator chậm, timeout hoặc dependency kéo dài transaction. |
| Số producer được tạo mới/đóng | Tăng bất thường có thể cho thấy cache churn, producer bị fence hoặc maxAge quá ngắn. |
| Số `NoProducerAvailableException` | Có thể cho thấy bounded suffix strategy quá nhỏ hoặc transaction giữ producer quá lâu. |
| `ProducerFencedException` và lỗi epoch | Nghi ngờ transaction ID trùng, producer cũ bị thay thế hoặc vòng đời client bất thường. |
| Producer send error, retry, request latency | Đánh giá broker/network/serialization, không nhầm mọi lỗi thành lỗi cache. |
| Kafka consumer lag và rebalance | Thấy tác động gián tiếp của transaction chậm hoặc thất bại lên tiến độ xử lý. |

Kafka producer cung cấp metric qua JMX/Kafka client metrics. Spring Kafka/Micrometer có thể cung cấp quan sát listener và KafkaTemplate tùy cấu hình, nhưng **không mặc định có một metric ổn định tên “transaction-cache-hit-ratio”** trên mọi phiên bản. Nếu cần metric cache cụ thể, kiểm tra API producer factory/listener và triển khai instrumentation phù hợp, tránh gán tên metric không tồn tại.

Khi log lỗi giao dịch, ưu tiên ghi:

```text
event=kafka_transaction_error
application=order-service
instance=order-service-7c9f6d8-p9x5m
transaction_id_prefix=orders-tx-order-service-7c9f6d8-p9x5m-
error_type=NoProducerAvailableException
listener_id=order-listener
consumer_group=order-service
```

Ví dụ là log có cấu trúc tự thiết kế, không phải log mặc định của Spring Kafka. Tránh ghi raw payload, secret, authorization header hoặc toàn bộ object producer vào log. Với `transactional.id`, việc ghi một định danh kỹ thuật thường có ích khi điều tra fencing nhưng cần tuân thủ chính sách log của tổ chức.

## 14. Một số cấu hình dễ nhầm

| Cấu hình / khái niệm | Không nên hiểu là |
|---|---|
| `transaction-id-prefix` | Group ID của consumer. |
| `maxCache` trong suffix strategy | Số partition của topic hoặc số replica toàn cluster. |
| `maxAge` của producer factory | Timeout cho một transaction đang chạy. |
| `enable.idempotence=true` | Thay thế cho `transactional.id` và commit/abort transaction. |
| `acks=all` | Bằng chứng tất cả bước nghiệp vụ và offset đều đã commit nguyên tử. |
| `read_committed` | Cấu hình producer cache; đây là isolation level của consumer. |
| Producer được trả về cache | Record được giữ trong cache; cache giữ client, không giữ message nghiệp vụ. |

Ví dụ `transaction.timeout.ms` thường phải nhỏ hơn hoặc bằng giới hạn mà broker chấp nhận. Nếu một transaction bị timeout trên broker, nâng `maxCache` hay đổi `maxAge` không giúp transaction đó thành công. Tương tự, khi producer không cấp được vì suffix giới hạn, tăng số partition Kafka không làm suffix tự xuất hiện.

## 15. Runbook: lỗi NoProducerAvailableException

Giả sử sau khi tăng `concurrency` từ 3 lên 8, listener log:

```text
org.springframework.kafka.core.NoProducerAvailableException:
No producer available
```

Một cách điều tra:

**Bước 1 — Xác nhận scope.** Xem lỗi đến từ instance nào, producer factory nào và có bao nhiêu listener/template đang dùng factory đó.

**Bước 2 — Kiểm tra strategy.** Xác nhận phiên bản Spring Kafka, `DefaultTransactionIdSuffixStrategy(maxCache)` và giá trị giới hạn thực tế.

**Bước 3 — So sánh concurrency.** Tính số transaction Kafka đồng thời trong pod; cộng cả publisher từ scheduler, request thread và transaction lồng nhau nếu có.

**Bước 4 — Kiểm tra transaction kéo dài.** Xem có lời gọi network/database nằm trong Kafka transaction, timeout quá cao hay thread bị block khiến producer được trả về cache chậm không.

**Bước 5 — Điều chỉnh có kiểm soát.** Tăng giới hạn đủ cho tải đã đo, giảm đồng thời hoặc áp dụng retry mượn producer với backoff và giới hạn. Không chuyển thành retry vô hạn.

**Bước 6 — Xác nhận sau thay đổi.** Theo dõi exception giảm, transaction commit rate hồi phục, producer count và consumer lag ổn định.

Điều quan trọng: **không gọi `reset()` producer factory liên tục mỗi khi hết producer**. Reset không tự giải quyết giới hạn concurrency; có thể tạo thêm churn, mất lợi ích cache và ảnh hưởng transaction đang hoạt động.

## 16. Runbook: ProducerFencedException sau rollout

Một deployment nhiều pod có thể xuất hiện lỗi fencing đồng loạt ngay sau khi phiên bản mới tham gia cluster.

```text
Old pod: orders-tx-0
New pod: orders-tx-0
Kafka broker: producer mới thay thế producer cũ
Old pod: transaction thất bại
```

Kiểm tra theo thứ tự:

1. Xác định pod cũ và mới có đang chạy đồng thời hay không, đặc biệt khi rolling update dùng `maxSurge`.
2. So sánh `transactionIdPrefix` thực tế ở từng pod, không chỉ file cấu hình trong repository.
3. Kiểm tra có nhiều producer factory/template cùng xây dựng `transactional.id` trùng nhau hay không.
4. Xem lỗi fencing xảy ra thường xuyên hay chỉ một lần trong quá trình chuyển giao quyền sở hữu mong đợi.
5. Gán prefix riêng cho từng instance đang chạy đồng thời, sau đó deploy có kiểm soát.
6. Xác minh không còn lỗi epoch/fencing và consumer group có thể tiến offset bình thường.

Tránh xử lý bằng cách nuốt `ProducerFencedException` rồi cố commit transaction đang lỗi. Sau khi bị fence, producer cũ không nên tiếp tục được dùng như một producer khỏe.

## 17. Chọn maxCache và maxAge trong thực tế

Giả sử một service chạy ba replica, mỗi replica có listener concurrency bằng 4 và thêm tối đa hai transaction độc lập từ một background job.

```text
Số replica: 3
Listener concurrency / replica: 4
Background transaction đồng thời / replica: 2

Mức cao điểm dự kiến / replica = 4 + 2 = 6
Tổng consumer trên cả deployment = 3 × 4 = 12
```

Với bounded suffix strategy, có thể bắt đầu sizing **ít nhất sáu suffix cho mỗi replica**, rồi bổ sung headroom theo tải thực tế và tình huống transaction lồng nhau. Không nhất thiết đặt 18 suffix trong mỗi pod chỉ vì deployment có ba replica.

Khi chọn `maxAge`:

- Kiểm tra `transactional.id.expiration.ms` thật trên broker.
- Chọn tuổi cache thấp hơn thời gian expiration với khoảng an toàn phù hợp.
- Tránh đặt quá ngắn, khiến producer khởi tạo lại liên tục và mất lợi ích cache.
- Tránh đặt quá dài, khiến producer idle lâu bị broker expire trước khi được dùng lại.
- Quan sát tỷ lệ producer bị tạo mới, thời gian init transaction và lỗi liên quan epoch/fencing.

Không có một giá trị maxCache hoặc maxAge tối ưu cho mọi hệ thống. Các tham số phải phản ánh listener concurrency, mô hình transaction, tần suất idle và chính sách Kafka broker.

## 18. Checklist khi triển khai transactional producer cache

Trước khi đưa một service Spring Kafka có transaction lên production, hãy xác nhận:

1. **Factory đúng:** `KafkaTemplate` và transaction manager sử dụng transactional `ProducerFactory` được cấu hình như dự kiến.
2. **Prefix duy nhất:** mỗi instance đang chạy đồng thời dùng `transactionIdPrefix` không chồng lấp với instance khác.
3. **Concurrency phù hợp:** nếu dùng bounded suffix strategy, `maxCache` đủ cho số transaction đồng thời trên mỗi JVM, kể cả job nền và nested transactions.
4. **Tuổi producer hợp lý:** `maxAge` tránh tái sử dụng producer đã idle quá lâu so với expiration policy của broker.
5. **Timeout đồng bộ:** xem lại transaction timeout, request timeout và thời gian listener xử lý, không chỉ kích thước cache.
6. **Delivery semantics rõ ràng:** xác nhận offset và output record được commit trong Kafka transaction khi cần Kafka-to-Kafka EOS, và consumer downstream dùng `read_committed` khi phù hợp.
7. **Idempotency:** các hiệu ứng ngoài Kafka có thiết kế chống trùng hoặc transaction/outbox phù hợp.
8. **Observability:** có log/metric cho commit, abort, producer creation, fencing, `NoProducerAvailableException`, send errors và consumer lag.
9. **Rollback an toàn:** biết cách xử lý khi deploy mới dùng prefix trùng, khi broker fencing hoặc khi cache cạn trong thời điểm tải cao.
10. **Kiểm thử vận hành:** mô phỏng nhiều transaction đồng thời, producer lỗi, pod restart/rollout và Registry/Network failure liên quan serialization hoặc publish.

Producer transaction cache của Spring Kafka là một cơ chế **tái sử dụng transactional producer** giúp giảm chi phí khởi tạo và hỗ trợ nhiều giao dịch nối tiếp. Để dùng an toàn, cần hiểu rằng cache thuộc từng `DefaultKafkaProducerFactory`, transaction ID phải duy nhất giữa các instance cùng hoạt động, giới hạn suffix phải phù hợp concurrency, và producer quá tuổi hoặc bị fence phải được thay thế. Cache tối ưu tài nguyên; tính nhất quán và độ tin cậy vẫn đến từ cách ứng dụng tổ chức transaction, offset, exception handling và idempotency.
