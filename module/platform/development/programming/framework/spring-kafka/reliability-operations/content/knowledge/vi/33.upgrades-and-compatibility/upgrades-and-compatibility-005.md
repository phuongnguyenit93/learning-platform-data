# Deprecation của transaction manager cũ trong Spring Kafka

## 1. Vì sao một thay đổi API lại liên quan đến độ tin cậy dữ liệu?

Một ứng dụng nhận event từ Kafka, cập nhật database rồi gửi event kết quả sang một topic khác. Ở phiên bản cũ, dự án có thể dùng `ChainedKafkaTransactionManager` để “gộp” transaction của Kafka và JDBC, sau đó gắn transaction manager này trực tiếp vào listener container. Khi nâng cấp Spring Kafka, IDE báo `@Deprecated` hoặc API `ContainerProperties.setTransactionManager(...)` bị đánh dấu for removal.

Phản ứng dễ mắc sai lầm là thay một class bằng class khác để hết warning mà không kiểm tra **thứ tự commit và khả năng phục hồi**. Việc này có thể khiến service hoạt động ở đường đi thành công, nhưng khi broker, database hoặc mạng lỗi đúng thời điểm commit, dữ liệu giữa hai hệ thống có thể lệch nhau.

Bài **Deprecation của transaction manager cũ** thuộc *Spring Kafka Reliability Operations → Nâng cấp và tương thích*. Mục tiêu không phải học mọi API transaction của Spring, mà là hiểu rõ vì sao transaction manager cũ bị deprecated, phương án thay thế được khuyến nghị và cách migration **không làm mất hoặc nhân đôi business side effect**.

Bạn sẽ học cách:

- Xác định đúng những API bị deprecated, phiên bản liên quan và API **vẫn còn được dùng**.
- Hiểu `ChainedKafkaTransactionManager` dựa trên `ChainedTransactionManager` và vì sao chaining không phải XA/two-phase commit.
- Thay bằng `KafkaTransactionManager` cho Kafka container và `@Transactional` với DB transaction manager tại service.
- Phân biệt **consumer-initiated** và **producer-initiated** transactions.
- Phân tích thứ tự commit DB-first/Kafka-first, những cửa sổ partial commit và cách idempotency xử lý redelivery.
- Cấu hình đúng `transactionIdPrefix`, producer factory, consumer isolation, listener container và nhiều bean transaction manager.
- Điều chỉnh error handler, rollback processor, DLT/retry và chiến lược kiểm thử khi container có transaction.
- Lập checklist triển khai, quan sát và rollback migration.

Ví dụ dựa trên **Java 17, Spring Boot 3.4.x, Spring Kafka 3.3.x và Spring Framework 6.x**. Ở Spring Boot 4/Spring Kafka 4, cấu trúc package auto-configuration có thay đổi; kiểm tra Javadoc của đúng bộ phiên bản. Các ví dụ là thiết kế minh họa, không khẳng định đã được build/chạy trong môi trường dự án cụ thể.

---

## 2. Chính xác cái gì đã bị deprecated?

Cụm “transaction manager cũ” trong Spring Kafka dễ gây nhầm lẫn bởi có **hai nhóm deprecation liên quan**, nhưng không đồng nhất.

| Thành phần | Tình trạng trong Spring Kafka 3.3.x | Thay bằng |
|---|---|---|
| `org.springframework.kafka.transaction.ChainedKafkaTransactionManager<K,V>` | Deprecated từ Spring Kafka **2.7** | Dùng `KafkaTransactionManager` ở container; khởi tạo DB transaction bằng `@Transactional` ở listener/service |
| `org.springframework.data.transaction.ChainedTransactionManager` | Deprecated từ Spring Data Commons **2.5** | Transaction synchronization hoặc điều phối riêng; với reliability cao, cân nhắc outbox/idempotency |
| `ContainerProperties.setTransactionManager(PlatformTransactionManager)` | Deprecated từ Spring Kafka **3.2**, đánh dấu for removal | `ContainerProperties.setKafkaAwareTransactionManager(KafkaAwareTransactionManager<?, ?>)` |
| `ContainerProperties.getTransactionManager()` | Deprecated từ Spring Kafka **3.2**, đánh dấu for removal | `getKafkaAwareTransactionManager()` |
| `KafkaAwareTransactionManager<K,V>` | Giao diện được hỗ trợ trong 3.3 | Sử dụng khi container cần transaction manager biết `ProducerFactory` |
| `KafkaTransactionManager<K,V>` | Được hỗ trợ, **không phải class bị deprecated ở đây** | Vẫn dùng cho transactional Kafka producer/container |

**Mốc thời gian:** tên `ChainedKafkaTransactionManager` từng có từ Spring Kafka 2.1.3; từ 2.7 tài liệu khuyến nghị không dùng cho thiết kế mới. Với 3.2, Spring Kafka còn thu hẹp type mà `ContainerProperties` chấp nhận, thay setter tổng quát nhận `PlatformTransactionManager` bằng setter nhận `KafkaAwareTransactionManager`. Điều này khiến các dự án nâng cấp từ 2.x qua 3.3 có thể gặp hai nhóm warning đồng thời.

“Deprecated” **không tự đồng nghĩa “class đã bị xóa”**. Ví dụ Javadoc Spring Kafka 3.3 và 4.0 vẫn liệt kê `ChainedKafkaTransactionManager` với annotation deprecated. Nhưng code tiếp tục dựa vào API for-removal sẽ làm chi phí nâng cấp tương lai tăng và giữ nguyên các rủi ro partial commit đã biết.

### 2.1. Cách nhận diện trong code cũ

Dấu hiệu 1:

```java
import org.springframework.kafka.transaction
        .ChainedKafkaTransactionManager;

@Bean
ChainedKafkaTransactionManager<String, String> chained(
        PlatformTransactionManager jdbcTx,
        KafkaTransactionManager<String, String> kafkaTx) {

    return new ChainedKafkaTransactionManager<>(
            jdbcTx, kafkaTx);
}
```

Dấu hiệu 2:

```java
factory.getContainerProperties()
        .setTransactionManager(chained);
```

Dấu hiệu 3: project không tự tạo chained manager nhưng vẫn gọi `setTransactionManager(kafkaTransactionManager)`. Trường hợp này chủ yếu là **migration API của container property**, không phải việc bỏ chaining.

Dấu hiệu 4: có nhiều bean `PlatformTransactionManager` và code `@Transactional` không chỉ rõ bean. Dù hết deprecation warning, transaction có thể khởi tạo sai manager hoặc startup báo ambiguity.

### 2.2. Vì sao deprecated không chỉ để “đẹp code”?

Một transaction manager chain không thể biến hai tài nguyên độc lập thành **một distributed atomic transaction**. Nếu một resource đã commit nhưng resource còn lại lỗi lúc commit, cả hệ thống ở trạng thái một bên thành công một bên thất bại. Class cũ có thể báo lỗi, nhưng không thể tự hoàn tác một commit đã hoàn thành ở nơi khác.

Do đó một migration tốt phải **thể hiện rõ ranh giới Kafka transaction, DB transaction và thứ tự commit**, rồi thiết kế replay/idempotency/reconciliation thay vì dựa vào tên “Chained” để giả định an toàn.

---

## 3. Transaction manager cũ thực sự hoạt động như thế nào?

### 3.1. ChainedTransactionManager bắt đầu và kết thúc theo thứ tự nào?

`ChainedKafkaTransactionManager` kế thừa Spring Data `ChainedTransactionManager`. Parent manager nhận một dãy `PlatformTransactionManager`. Về nguyên tắc:

- **Bắt đầu transaction** theo thứ tự được truyền vào.
- **Commit và rollback** theo thứ tự ngược lại.
- Nếu một resource commit thất bại, manager có thể rollback những resource còn chưa commit.
- Nhưng resource nào đã commit thành công thì **không thể bị rollback lại** chỉ bằng transaction manager.

Ví dụ:

```java
new ChainedKafkaTransactionManager<>(
        dbTransactionManager,
        kafkaTransactionManager);
```

Trong chain này, **Kafka commit trước DB** theo thứ tự ngược. Nếu Kafka đã commit thành công rồi DB commit thất bại, consumer ở phía Kafka có thể đọc event kết quả trong khi dữ liệu DB chưa ghi thành công.

Đảo thứ tự constructor:

```java
new ChainedKafkaTransactionManager<>(
        kafkaTransactionManager,
        dbTransactionManager);
```

làm **DB commit trước Kafka** trong cơ chế chain. Nếu DB đã commit nhưng Kafka commit lỗi, DB chứa thay đổi chưa có event tương ứng.

**Không chọn thứ tự chỉ bằng cảm giác.** Thứ tự commit là một quyết định nghiệp vụ và failure recovery. Cả hai thứ tự đều có cửa sổ partial commit.

### 3.2. HeuristicCompletionException

Javadoc `ChainedTransactionManager` cảnh báo về trạng thái **partially committed** và có thể ném `HeuristicCompletionException` khi commit một delegate thất bại sau khi delegate khác đã commit. Đây không phải cơ chế bù trừ tự động.

Giả lập:

```text
Begin DB transaction
Begin Kafka transaction
       │
       ▼
Process event
       │
       ▼
Commit Kafka ────────── SUCCESS
       │
       ▼
Commit DB ───────────── FAILURE
       │
       ▼
Partial commit:
  downstream thấy event Kafka
  database chưa ghi dữ liệu tương ứng
```

Hệ thống có thể phải chạy reconciliation, gửi compensating event, đánh dấu pending hoặc xử lý lại theo business key. Chaining không có commit coordinator kiểu XA bảo đảm hai bên cùng commit hoặc cùng rollback dưới mọi lỗi.

### 3.3. KafkaTransactionManager cũng không phải XA manager

`KafkaTransactionManager` quản lý giao dịch trên **Kafka ProducerFactory**. Nó có thể commit các Kafka messages và offsets theo transaction Kafka khi container được cấu hình phù hợp. Nó **không** enlist JDBC database vào cùng một XA transaction.

Spring Kafka transaction mang lại hiệu quả cao cho flow:

```text
Consume Kafka → transform → produce Kafka
                  │
                  ▼
      Kafka output + consumed offsets
           trong Kafka transaction
```

Nhưng khi có side effect JDBC/HTTP/email:

```text
Consume Kafka → update PostgreSQL → produce Kafka
                        │
               một transaction khác
```

Cần có thiết kế cho sự bất đồng giữa hai resource.

---

## 4. Ba tình huống transaction khác nhau cần chọn đúng

Đừng áp một mẫu migration cho mọi code sử dụng Kafka.

### 4.1. Kafka → Kafka (không dùng database)

Một listener đọc topic đầu vào, chuyển đổi message và publish topic đầu ra. Container bắt đầu Kafka transaction, `KafkaTemplate` cùng producer factory tham gia. Offset của input được gửi vào Kafka transaction khi container hoàn tất.

Trong phạm vi Kafka read-process-write, có thể đạt exactly-once semantics theo điều kiện cấu hình và `read_committed`, không cần DB transaction manager.

**Thiết kế:** một `KafkaTransactionManager` đủ, không cần `ChainedKafkaTransactionManager`.

### 4.2. Kafka → DB hoặc Kafka → DB + Kafka

Listener đọc Kafka, cập nhật database và có thể publish topic đầu ra. Mẫu migration được Spring Kafka khuyến nghị:

1. Container bắt đầu **Kafka transaction** bằng `KafkaTransactionManager`.
2. Phương thức service/listener được bảo vệ bằng `@Transactional("dbTransactionManager")` để mở **DB transaction** riêng.
3. DB transaction hoàn tất khi service method return.
4. Container sau đó commit Kafka transaction (bao gồm Kafka outputs và offset của input).

Trong tình huống bình thường, thứ tự là **DB-first, Kafka-second**. Nếu Kafka commit thất bại sau DB commit, input record có thể được giao lại. Do đó DB write phải **idempotent**.

### 4.3. DB → Kafka (producer-initiated, không có Kafka consumer container)

Một REST endpoint hoặc scheduled job cập nhật database và publish event. Thông thường `@Transactional("dbTransactionManager")` là transaction chính; khi dùng transactional `KafkaTemplate` đã cấu hình phù hợp, send có thể synchronize Kafka transaction với DB transaction.

Trong flow này, DB commit trước rồi Kafka commit. Nếu Kafka commit thất bại, DB có thể đã ghi. Với yêu cầu reliable publication, **transactional outbox** thường an toàn hơn chỉ dùng synchronization.

### 4.4. Ma trận lựa chọn

| Flow | Cách thường dùng | Vấn đề cần bảo vệ |
|---|---|---|
| Kafka → Kafka | Kafka container transaction | Producer factory, offsets, isolation, fencing |
| Kafka → DB | Kafka container transaction + DB `@Transactional` | DB redelivery/idempotency |
| Kafka → DB → Kafka | Kafka container transaction + DB `@Transactional` + `KafkaTemplate` | DB/Kafka partial commit |
| DB → Kafka | DB transaction + Kafka synchronization | DB commit trước Kafka, reconcile publish |
| DB → Kafka cần phát event không mất | Transactional outbox + dispatcher | Outbox delivery at-least-once và consumer idempotency |
| Kafka → HTTP/payment | Kafka transaction không bao trùm HTTP side effect | Idempotency key, unknown outcome, reconciliation |

---

## 5. Mẫu legacy: điều cần thay và điều không nên copy

Ví dụ cho dự án Spring Kafka cũ:

```java
// LEGACY, KHÔNG DÙNG CHO CODE MỚI.

@Bean("chainedTransactionManager")
ChainedKafkaTransactionManager<String, String> chainedTx(
        @Qualifier("dbTransactionManager")
                PlatformTransactionManager dbTx,
        KafkaTransactionManager<String, String> kafkaTx) {

    return new ChainedKafkaTransactionManager<>(
            dbTx, kafkaTx);
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, String>
legacyFactory(
        ConsumerFactory<String, String> consumers,
        ChainedKafkaTransactionManager<String, String> chainedTx) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory
                    <String, String>();

    factory.setConsumerFactory(consumers);
    factory.getContainerProperties()
            .setTransactionManager(chainedTx);

    return factory;
}
```

**Vấn đề 1:** `ChainedKafkaTransactionManager` deprecated từ 2.7. **Vấn đề 2:** `setTransactionManager(PlatformTransactionManager)` deprecated từ 3.2. **Vấn đề 3:** dù chạy thành công, không có atomicity DB + Kafka.

Giải pháp **không phải** đổi `ChainedKafkaTransactionManager` thành `KafkaTransactionManager` ở cùng một dòng và coi migration xong. Bạn còn phải quyết định transaction DB được mở ở đâu, mỗi service dùng manager nào, commit order mới và logic xử lý redelivery.

---

## 6. Chuẩn bị Kafka transaction trong Spring Boot 3.x

### 6.1. Bật transactional producer

Trong Spring Boot, cách phổ biến để bật Kafka transactions là khai báo:

```yaml
spring:
  kafka:
    bootstrap-servers: "${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}"
    producer:
      transaction-id-prefix: "orders-${POD_NAME:local}-tx-"
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
    consumer:
      group-id: "orders-worker"
      enable-auto-commit: false
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      properties:
        isolation.level: read_committed
    listener:
      type: single
      concurrency: 3
```

Trong môi trường một máy dev, giá trị fallback `local` chỉ để minh họa. **Production phải dùng prefix duy nhất cho mỗi instance/pod**, ví dụ lấy từ pod name/instance identity và không cho hai process cùng sống dùng chung prefix.

Khi có `spring.kafka.producer.transaction-id-prefix`, Spring Boot có thể tự cấu hình transactional producer factory, `KafkaTransactionManager` và nối manager vào listener container mặc định. Nếu application tự tạo factory hoặc có nhiều bean transaction manager, cần kiểm tra wiring cụ thể thay vì giả định Boot tự chọn đúng mọi bean.

### 6.2. Mỗi replica có transaction ID riêng

Kafka transactions nhận diện producer bằng `transactional.id`. Với Spring Kafka 3.x, producer factory thường tạo ID từ prefix + suffix. Nếu hai replica dùng cùng ID, Kafka có thể **fence** producer cũ và xuất hiện `ProducerFencedException`/transaction failures.

```text
Pod A:
  prefix = orders-pod-a-tx-
  transactional.id = orders-pod-a-tx-0 / 1 / ...

Pod B:
  prefix = orders-pod-b-tx-
  transactional.id = orders-pod-b-tx-0 / 1 / ...
```

Không hard-code một prefix giống nhau cho mọi pod của cùng Deployment. Khi pod restart với cùng identity, cần hiểu lifecycle producer cũ, transaction timeout và fencing; không dùng unique prefix như một cách vô hiệu hóa mọi lỗi mà bỏ qua resource management.

### 6.3. ProducerFactory và KafkaTemplate phải tương thích

Nếu tự khai báo:

```java
@Bean("kafkaTransactionManager")
KafkaTransactionManager<String, String> kafkaTransactionManager(
        ProducerFactory<String, String> producerFactory) {

    if (!producerFactory.transactionCapable()) {
        throw new IllegalStateException(
                "ProducerFactory must support transactions");
    }

    return new KafkaTransactionManager<>(producerFactory);
}
```

Đoạn code **chỉ áp dụng khi bạn chủ động quản lý bean**; đừng khai báo thêm một `KafkaTransactionManager` trùng với bean Boot đã tạo. Chọn một trong hai phương án: Boot auto-config hoặc custom configuration rõ ràng.

`KafkaTemplate` được dùng trong cùng transaction phải dùng **cùng ProducerFactory** với manager. Nếu template gửi thông qua producer factory khác hoặc cluster khác, nó không tự tham gia vào Kafka transaction đã mở.

### 6.4. EOSMode.V2 và isolation

Từ Spring Kafka 3.0, `EOSMode.V2` là chế độ EOS còn được hỗ trợ. Không cố giữ một switch EOS mode cũ chỉ để tránh thay đổi khi migrate.

Consumer đọc output từ producer transactional nên cân nhắc:

```yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
```

`read_committed` giúp consumer tránh đọc những record thuộc Kafka transaction đã abort. Nó **không** tạo consistency cho JDBC database hoặc remote HTTP.

### 6.5. Transaction ID cache và concurrency

Spring Kafka 3.2 có `TransactionIdSuffixStrategy` và `DefaultTransactionIdSuffixStrategy` để quản lý suffix của transactional ID. Khi producer factory dùng cache suffix hữu hạn, cần:

- Cache size **ít nhất tương ứng concurrency** của transactional listener containers dùng factory đó.
- Nếu có nested Kafka transactions hoặc nhiều listeners chia factory, chừa thêm capacity.
- Theo dõi `NoProducerAvailableException` khi không còn suffix/producer khả dụng.
- Kiểm tra số producer connections, memory và broker transaction state.
- Đánh giá `maxAge` của cached producers để tránh dùng producer idle quá lâu rồi bị fence vì transactional ID expiration ở broker.

Không tăng cache vô hạn để che thiếu tài nguyên; việc sizing phụ thuộc số transaction concurrent thực tế.

---

## 7. Migration cho consumer-initiated transaction: phương án được khuyến nghị

### 7.1. Thiết lập tường minh hai manager

Một ứng dụng vừa dùng JDBC vừa dùng Kafka có thể có hai transaction managers:

```text
dbTransactionManager
    └── JdbcTransactionManager(DataSource)
         chỉ quản lý JDBC connection/transaction

kafkaTransactionManager
    └── KafkaTransactionManager(ProducerFactory)
         chỉ quản lý Kafka producer transaction

@KafkaListener container
    └── Kafka transaction outer

OrderProcessingService.process()
    └── @Transactional("dbTransactionManager")
         DB transaction inner
```

Một bean JDBC manager ví dụ Spring Framework 6:

```java
package com.example.kafka.tx;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;

@Configuration(proxyBeanMethods = false)
public class DatabaseTxConfiguration {

    @Bean("dbTransactionManager")
    JdbcTransactionManager dbTransactionManager(
            DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

`JdbcTransactionManager` là một implementation thích hợp cho JDBC; cũng có thể dùng `DataSourceTransactionManager` hoặc `JpaTransactionManager` tùy persistence stack. Nếu dùng JPA, chọn manager đúng với `EntityManagerFactory`, không giả định JDBC manager tự quản lý đầy đủ JPA persistence context.

**Chú ý Spring Boot auto-config:** khi tự khai báo transaction manager, điều kiện tạo bean mặc định có thể thay đổi; kiểm tra bean names/type trong application context. Các ví dụ ở đây giả định app có đúng một bean Kafka manager và một bean DB manager phù hợp.

### 7.2. Listener factory mới với setter đúng

Với Spring Boot 3.4.x, `ConcurrentKafkaListenerContainerFactoryConfigurer` nằm trong `org.springframework.boot.autoconfigure.kafka`.

```java
package com.example.kafka.tx;

import org.springframework.boot.autoconfigure.kafka
        .ConcurrentKafkaListenerContainerFactoryConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.kafka.config
        .ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.transaction
        .KafkaTransactionManager;

@Configuration(proxyBeanMethods = false)
public class KafkaListenerTxConfiguration {

    @Bean("ordersTxListenerContainerFactory")
    ConcurrentKafkaListenerContainerFactory<Object, Object>
    ordersTxListenerContainerFactory(
            ConcurrentKafkaListenerContainerFactoryConfigurer configurer,
            ConsumerFactory<Object, Object> consumerFactory,
            KafkaTransactionManager<?, ?> kafkaTransactionManager) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory
                        <Object, Object>();

        // Lấy baseline từ spring.kafka.* đã được Boot bind.
        configurer.configure(factory, consumerFactory);

        // API được hỗ trợ từ Spring Kafka 3.2:
        factory.getContainerProperties()
                .setKafkaAwareTransactionManager(
                        kafkaTransactionManager);

        factory.setConcurrency(3);
        factory.setBatchListener(false);

        return factory;
    }
}
```

Điểm migration cốt lõi:

```java
// Cũ, deprecated từ 3.2:
containerProperties.setTransactionManager(oldManager);

// Mới:
containerProperties.setKafkaAwareTransactionManager(
        kafkaTransactionManager);
```

**Không** truyền một `JdbcTransactionManager` hay một `ChainedKafkaTransactionManager` vào setter mới. Interface `KafkaAwareTransactionManager` dành cho Kafka manager biết `ProducerFactory`.

Nếu dùng factory mặc định của Boot và chỉ cần tính năng chuẩn, có thể **không cần tạo custom factory**: cấu hình producer transaction ID prefix và kiểm tra Boot đã wire manager cho container. Factory riêng phù hợp khi cần đặt tên/behavior riêng hoặc tránh ambiguity giữa nhiều listener.

### 7.3. Listener khởi tạo Kafka transaction, service mở DB transaction

```java
package com.example.kafka.tx;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrdersEventListener {

    private final OrdersApplicationService service;

    public OrdersEventListener(
            OrdersApplicationService service) {
        this.service = service;
    }

    @KafkaListener(
            id = "orders-tx-v1",
            topics = "orders.events",
            groupId = "orders-worker",
            containerFactory =
                    "ordersTxListenerContainerFactory")
    public void onOrder(String payload) {

        service.applyEvent(payload);

        // Không nuốt exception:
        // nếu service thất bại, container phải rollback.
    }
}
```

Service:

```java
package com.example.kafka.tx;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrdersApplicationService {

    private final OrdersRepository orders;
    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrdersApplicationService(
            OrdersRepository orders,
            KafkaTemplate<String, String> kafkaTemplate) {

        this.orders = orders;
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("dbTransactionManager")
    public void applyEvent(String payload) {
        OrderEvent event = OrderEvent.parse(payload);

        // Repository phải có idempotency theo eventId.
        boolean firstProcessing =
                orders.claimEventId(event.eventId());

        if (!firstProcessing) {
            return; // Kafka redelivery của event đã xử lý.
        }

        orders.updateStatus(
                event.orderId(), event.status());

        kafkaTemplate.send(
                "orders.processed",
                event.orderId(),
                event.toProcessedJson());
    }
}
```

Các type `OrdersRepository` và `OrderEvent` là thành phần nghiệp vụ cần định nghĩa trong project; mục 10 có ví dụ database dedup. Logic minh họa **Kafka → DB + Kafka**. Chạy với transactional KafkaTemplate cùng producer factory mà container đã mở transaction.

### 7.4. Thứ tự commit trong flow này

```text
Kafka listener container
  ├── START Kafka transaction
  │       ├── receive input record
  │       └── call OrdersApplicationService
  │               ├── START DB transaction
  │               ├── INSERT dedup key
  │               ├── UPDATE business table
  │               ├── KafkaTemplate.send(...) in Kafka tx
  │               └── COMMIT DB transaction
  │
  ├── listener returns successfully
  ├── send consumed offsets to Kafka transaction
  └── COMMIT Kafka transaction
```

Khi mọi thứ thành công:

- Database chứa business effect.
- Topic `orders.processed` có output event đã commit.
- Consumed offset của `orders.events` được commit trong Kafka transaction tương ứng.

Khi DB commit thất bại, exception phải lan ra listener; Kafka transaction rollback và input chưa được đánh dấu xử lý thành công.

Khi **DB commit thành công nhưng Kafka commit thất bại**, input có thể được giao lại. Hãy dùng transaction DB idempotent, nếu không sẽ cập nhật business lần hai. **Mẫu mới không biến commit DB + Kafka thành 2PC**; nó làm ranh giới rõ để thiết kế recovery.

### 7.5. Vì sao đặt @Transactional ở service khác bean?

Spring Framework thông thường áp dụng `@Transactional` qua AOP proxy. Nếu method `this.applyEvent(...)` tự gọi trong cùng class, self-invocation có thể bỏ qua proxy và không mở DB transaction như kỳ vọng.

Để dễ hiểu và kiểm thử:

- Listener chỉ nhận/dẫn message.
- Service bean được Spring quản lý có `@Transactional("dbTransactionManager")`.
- Listener gọi qua bean proxy của service.
- Không dùng private method được annotation rồi hy vọng proxy áp dụng.
- Không bắt exception trong listener rồi return bình thường khi DB failed.

---

## 8. Khi nào chỉ cần đổi API setTransactionManager?

Nếu legacy code **đã sử dụng KafkaTransactionManager thuần**, ví dụ:

```java
factory.getContainerProperties()
        .setTransactionManager(kafkaTransactionManager);
```

thì migration chủ yếu là:

```java
factory.getContainerProperties()
        .setKafkaAwareTransactionManager(kafkaTransactionManager);
```

Trong trường hợp này không nhất thiết phải thay business transaction boundary; tuy nhiên vẫn nên kiểm tra transaction-enabled producer factory, offset commit, error handling và listener behavior trước khi deploy. Đừng gộp vấn đề này với việc thay `ChainedKafkaTransactionManager` — hai bước có mức độ rủi ro khác nhau.

Nếu code cũ truyền **non-Kafka** `PlatformTransactionManager` vào container, setter mới không nhận type đó. Thay vì ép cast, hãy đặt DB transaction ở tầng service/interceptor phù hợp như `@Transactional` và chỉ đưa Kafka transaction manager vào container khi cần Kafka transactional consumption.

---

## 9. Producer-initiated flow: DB-first synchronization

Trong flow không có Kafka listener container (REST/service/scheduler), Spring Kafka hỗ trợ synchronize KafkaTemplate transaction với transaction hiện có của Spring.

Ví dụ:

```java
@Service
public class BillingService {

    private final JdbcTemplate jdbc;
    private final KafkaTemplate<String, String> kafka;

    public BillingService(
            JdbcTemplate jdbc,
            KafkaTemplate<String, String> kafka) {
        this.jdbc = jdbc;
        this.kafka = kafka;
    }

    @Transactional("dbTransactionManager")
    public void createInvoice(
            String invoiceId, String payload) {

        jdbc.update(
                "INSERT INTO invoices (invoice_id) VALUES (?)",
                invoiceId);

        kafka.send("invoices.created", invoiceId, payload);
    }
}
```

Với transactional producer factory phù hợp và một **producer-initiated DB transaction**, KafkaTemplate có thể đồng bộ Kafka transaction theo DB transaction: **DB commit trước, Kafka commit sau**. Điều này khác listener container đã mở Kafka transaction ở ngoài cùng.

### 9.1. Cửa sổ lỗi DB-first

```text
DB transaction BEGIN
     │
     ├─ insert invoice
     ├─ KafkaTemplate.send
     │
DB COMMIT ──────────── SUCCESS
     │
Kafka COMMIT ───────── FAILURE
     │
     ▼
DB có invoice;
Kafka thiếu/không rõ event.
```

Trong các phiên bản Spring Kafka được tài liệu nhấn mạnh (2.5.17, 2.6.12, 2.7.9, 2.8.0 trở lên), lỗi commit của synchronized transaction sau primary commit được ném ra caller thay vì âm thầm bỏ qua. **Exception không có nghĩa DB đã rollback.** Caller phải có cách xác định và bù trừ trạng thái.

### 9.2. Không retry toàn method mù quáng

Nếu caller thấy exception do Kafka commit failed và retry `createInvoice(...)`, lệnh INSERT DB có thể gây duplicate key hoặc tạo invoice mới nếu ID khác. Cần dùng business ID ổn định và idempotency.

Một worker không thể suy ra từ exception ở Kafka rằng chưa có message được gửi, chưa có DB row hoặc chưa có transaction nào commit. Cần reconciliation với trạng thái bền vững.

### 9.3. @Transactional không tự chọn DB manager đúng

Khi có cả `dbTransactionManager` và `kafkaTransactionManager`:

```java
@Transactional("dbTransactionManager")
```

rõ ràng hơn:

```java
@Transactional
```

Bản không có qualifier có thể phụ thuộc bean name/default/primary của context, dẫn đến ambiguity hoặc dùng manager không mong muốn. Không giả định có nhiều manager thì Spring “tự chọn theo JDBC method gọi bên trong”.

---

## 10. Kafka-first bằng nested @Transactional: hiểu rõ hậu quả

Đôi khi nghiệp vụ muốn **Kafka commit trước** rồi mới DB commit. Spring Kafka hướng dẫn dùng nested transactional methods, với hai bean/proxy rõ ràng.

### 10.1. Ví dụ nested services

Bean Kafka writer:

```java
@Service
public class KafkaInvoicePublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public KafkaInvoicePublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @Transactional("kafkaTransactionManager")
    public void publish(String invoiceId, String body) {
        kafkaTemplate.send(
                "invoices.created", invoiceId, body);
    }
}
```

Bean DB orchestrator:

```java
@Service
public class InvoiceOrchestrator {

    private final JdbcTemplate jdbc;
    private final KafkaInvoicePublisher publisher;

    public InvoiceOrchestrator(
            JdbcTemplate jdbc,
            KafkaInvoicePublisher publisher) {
        this.jdbc = jdbc;
        this.publisher = publisher;
    }

    @Transactional("dbTransactionManager")
    public void execute(String invoiceId, String payload) {

        jdbc.update(
                "INSERT INTO invoices (invoice_id) VALUES (?)",
                invoiceId);

        // Proxy của bean khác mở/commit Kafka transaction.
        publisher.publish(invoiceId, payload);

        // Sau khi Kafka method return, DB outer TX commit.
    }
}
```

**Thứ tự:** mở DB outer transaction → mở Kafka inner transaction → Kafka inner commit → DB outer commit.

### 10.2. Cửa sổ lỗi Kafka-first

```text
DB transaction BEGIN
     │
Kafka transaction BEGIN
     │
Kafka COMMIT ──────────── SUCCESS
     │
DB COMMIT ─────────────── FAILURE
     │
     ▼
Consumer đã thấy invoice event;
database chưa có invoice tương ứng.
```

Không dùng phương án này nếu downstream bắt buộc đọc DB ngay khi nhận Kafka event mà không chấp nhận trạng thái “event có trước dữ liệu”. Đối với các hệ thống có eventual consistency, vẫn cần protocol trạng thái và reconciliation.

### 10.3. Chú ý nesting không phải XA

Nested `@Transactional` ở hai manager khác nhau chỉ tạo ra **hai local transactions** có thứ tự kết thúc do scope phương thức. Việc inner transaction commit không bị đảo ngược bởi rollback của outer transaction.

Vì vậy “Kafka-first” không phải giải pháp tổng quát an toàn hơn DB-first; chỉ thay đổi hướng mất nhất quán tiềm tàng.

---

## 11. Mô hình chính xác hơn về lỗi: ma trận partial commit

Phải phân tích cả trường hợp thành công và lỗi không thể rollback đồng thời.

| Flow | Lỗi xảy ra khi | Trạng thái có thể còn lại | Hành động |
|---|---|---|---|
| Consumer-initiated, DB-first | DB update lỗi trước commit | Kafka transaction rollback; input có thể redeliver | Fix DB, retry giới hạn |
| Consumer-initiated, DB-first | DB commit OK, Kafka commit lỗi | DB effect có, Kafka output/offset có thể chưa commit | DB dedup, redelivery và reconciliation |
| Producer-initiated, DB-first | DB commit OK, Kafka commit lỗi | DB row có, Kafka event thiếu/unknown | Outbox hoặc reconcile publish |
| Producer-initiated, Kafka-first | Kafka commit OK, DB commit lỗi | Event đã visible, DB row thiếu | Consumer chịu trạng thái pending, compensation |
| Kafka-only read-process-write | Kafka transaction abort | Kafka output và offset trong transaction không commit | Consumer redeliver |
| DB transaction lỗi business | Exception bị bắt/nuốt | App có thể return success dù DB không xử lý đúng | Không nuốt lỗi; đảm bảo rollback |
| HTTP side effect kèm Kafka | HTTP timeout sau server commit | Outcome remote unknown | Idempotency key, status lookup |
| DLT publish lỗi | Recoverer chưa lưu được record lỗi | Record chưa được khôi phục an toàn | Không coi là handled; alert/retry |

### 11.1. Tại sao DB idempotency là bắt buộc?

Giả sử consumer xử lý event `evt-123`:

1. DB commit đã ghi trạng thái order.
2. Kafka transaction commit lỗi, offset chưa được commit.
3. Khi consumer restart, Kafka gửi lại `evt-123`.
4. Nếu code cộng tiền thêm lần nữa, business effect bị nhân đôi.
5. Nếu DB có unique marker `evt-123` trong cùng transaction với update, lần hai biết đã xử lý và không tạo side effect mới.

Idempotency phải được thiết kế theo **event/business identity**, không chỉ theo việc code không throw exception.

### 11.2. Idempotency key từ đâu?

Các lựa chọn:

- `eventId` được producer tạo ổn định cho một business event.
- `businessTransactionId` hoặc `paymentId` nếu tương ứng đúng một side effect.
- `(topic, partition, offset)` để nhận diện redelivery của một Kafka record cụ thể.
- `aggregateId + version` nếu cần ngăn event version cũ ghi đè state mới.

Key `orderId` thường **không đủ** nếu một order có nhiều event legitimate (CREATED, PAID, SHIPPED). Ngược lại, offset không dedup được hai record khác offset nhưng cùng business event do producer publish trùng.

### 11.3. Ví dụ idempotent DB transaction bằng unique key

Schema PostgreSQL:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(120) NOT NULL,
    topic_name    VARCHAR(255) NOT NULL,
    partition_no  INTEGER NOT NULL,
    kafka_offset  BIGINT NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE order_state (
    order_id      VARCHAR(120) PRIMARY KEY,
    status        VARCHAR(40) NOT NULL
);
```

Repository service:

```java
@Service
public class OrdersRepository {

    private final JdbcTemplate jdbc;

    public OrdersRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean claimEventId(
            String eventId,
            String topic,
            int partition,
            long offset) {

        int count = jdbc.update("""
            INSERT INTO processed_events (
                consumer_name, event_id,
                topic_name, partition_no, kafka_offset
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """,
            "orders-worker", eventId, topic, partition, offset);

        return count == 1;
    }

    public void updateStatus(
            String orderId, String status) {
        jdbc.update("""
            INSERT INTO order_state (order_id, status)
            VALUES (?, ?)
            ON CONFLICT (order_id)
            DO UPDATE SET status = EXCLUDED.status
            """,
            orderId, status);
    }
}
```

Trong ví dụ này, `claimEventId` và `updateStatus` cần được gọi trong **cùng DB transaction** do `@Transactional("dbTransactionManager")` quản lý. Nếu marker “processed” commit trước rồi update business rollback, một lần redelivery sau có thể bị bỏ qua sai.

Nếu event có version/thứ tự nghiệp vụ, `ON CONFLICT DO UPDATE` cần kiểm tra version. Không để event cũ ghi đè state mới chỉ vì eventId của nó chưa xuất hiện trong bảng dedup.

---

## 12. Outbox: khi nào transaction synchronization chưa đủ?

Đối với flow **DB → Kafka** cần chắc chắn event cuối cùng được phát sau khi ghi business row, transactional outbox thường là giải pháp đáng cân nhắc.

### 12.1. Pattern

```text
HTTP request / Scheduled job
        │
        ▼
@Transaction DB
  ├── INSERT/UPDATE business rows
  └── INSERT outbox event
        │
        ▼
    DB COMMIT
        │
        ▼
Outbox dispatcher (polling/CDC)
        │
        ├── Kafka send success
        │        └── mark SENT / ack by CDC
        └── Kafka send failure
                 └── retry later
```

Business row và outbox event được ghi **trong cùng DB transaction**, giảm nguy cơ “DB đã commit nhưng event bị mất vì không có dấu vết phải gửi”.

### 12.2. Outbox không có nghĩa Kafka message gửi đúng một lần

Dispatcher có thể:

1. Publish event lên Kafka thành công.
2. Crash trước khi đánh dấu outbox row SENT.
3. Restart và publish lại event.

Do đó outbox thường bảo đảm **at-least-once delivery** tới Kafka; consumer phải dùng `eventId` và idempotency để xử lý duplicate. Không dùng outbox như một lời hứa exactly-once tuyệt đối ở mọi external system.

### 12.3. Khi nào dùng synchronization vẫn hợp lý?

- Side effect của event không quan trọng tới mức bắt buộc atomic với DB.
- Có thể reconcile bằng định kỳ quét trạng thái database.
- Hệ thống consumer có idempotency và chấp nhận eventual consistency.
- Độ phức tạp outbox/CDC lớn hơn lợi ích ở quy mô hiện tại.

Quyết định cần được business owner và nhóm vận hành thống nhất. Migration chỉ để xóa deprecation warning không tự bắt buộc xây outbox, nhưng **phải xác định chấp nhận cửa sổ partial commit nào**.

---

## 13. Transactional container: offset, rollback và error handler

### 13.1. Kafka transaction chứa offset như thế nào?

Khi listener container có `KafkaTransactionManager`, một vòng xử lý thành công có thể bao gồm:

- Record đã được consume.
- Những record mà `KafkaTemplate` gửi trong transaction.
- Offset được container gửi vào Kafka transaction.
- Kafka producer transaction commit.

Nếu transaction abort, output Kafka và offsets trong transaction đó không trở thành committed results. Consumer có thể đọc lại record sau restart/rebalance/seek theo chính sách.

Điều này khác container không transactional dùng `AckMode.RECORD/BATCH` để commit offsets ngoài producer transaction.

### 13.2. AckMode không phải công cụ chuyển đổi 2PC

Trong container transactional, offset send-to-transaction được container quản lý theo chế độ record/batch listener. Không dùng `MANUAL_IMMEDIATE` hoặc tự gọi `Acknowledgment.acknowledge()` như một cách làm Kafka + DB commit nguyên tử.

Nếu đổi AckMode trong quá trình migration, cần test behavior thật; offset semantics với Kafka container transaction có các quy tắc riêng và không giống non-transactional listener đơn thuần.

### 13.3. Error handling khi có container transaction

Với non-transactional listener, `DefaultErrorHandler` thường thực hiện retry/recover. Với **transactional container**, khi listener ném exception, Kafka transaction được rollback và `AfterRollbackProcessor` xử lý việc seek/replay/recovery theo configuration.

Mô hình:

```text
@KafkaListener throws
         │
         ▼
Kafka transaction ROLLBACK
         │
         ▼
AfterRollbackProcessor
         │
         ├── seek/reprocess với backoff
         ├── recover poison record theo policy
         └── quyết định bước tiếp theo
```

Không sao chép nguyên error handler của container non-transactional rồi giả định nó tương đương. Theo tài liệu Spring Kafka, nếu cấu hình một `CommonErrorHandler` làm **nuốt exception** trong container transactional, framework có thể coi xử lý thành công và commit thay vì rollback như mong muốn. Handler cho transactional flow phải giữ đúng error propagation và recovery contract.

### 13.4. DefaultAfterRollbackProcessor

Spring Kafka cung cấp `DefaultAfterRollbackProcessor` có thể retry và recover theo cấu hình. Với record sau nhiều lần thất bại, có thể dùng `DeadLetterPublishingRecoverer` làm recoverer. Khi cần publish DLT **và** commit recovered offset trong một Kafka transaction, phải cấu hình phiên bản/producer factory, `kafkaTemplate` và các tùy chọn như `commitRecovered`, `kafkaOperations` theo tài liệu.

Không triển khai ngay một đoạn code DLT “đã gửi thành công” khi chưa kiểm tra:

- DLT topic có đủ partitions/ACL.
- Serializer xử lý được raw payload khi lỗi deserialization.
- Producer DLT transaction tham gia transaction phù hợp.
- Recovered offset được commit đúng.
- Nếu DLT publish thất bại thì record nguồn không bị đánh dấu hoàn tất.
- Có replay/quarantine workflow ngoài listener.

### 13.5. Retry non-blocking và container transactions

Spring Kafka documentation nêu **non-blocking retries qua retry topics không kết hợp với container transactions** theo cách thông thường. Khi error path chuyển record sang retry topic, transaction/offset behavior có thể trái kỳ vọng của container transactional.

Nếu cần transactional listener và retry:

- Ưu tiên blocking retry/after-rollback recovery có giới hạn khi phù hợp.
- Với outage kéo dài, có thể dừng/pause consumer và điều phối reprocessing.
- Nếu cần non-blocking retry topics, thiết kế lại boundary và đánh giá chấp nhận ordering/transaction semantics.
- Không chỉ thêm `@RetryableTopic` lên method hiện hữu rồi cho rằng transaction vẫn nguyên vẹn.

### 13.6. KafkaTemplate.executeInTransaction không “join” transaction hiện tại như thường nghĩ

`KafkaTemplate.executeInTransaction(...)` mở một **local Kafka transaction riêng**. Tài liệu mô tả rằng kể cả khi đã có KafkaTransactionManager hoặc synchronized transaction, nó vẫn sử dụng một transaction lồng riêng chứ không tự động tham gia transaction bên ngoài.

Do đó:

```java
kafkaTemplate.executeInTransaction(ops -> {
    ops.send("topic", "value");
    return null;
});
```

không nên đưa vào service đã có Kafka container transaction chỉ với ý định “bảo đảm transaction chắc hơn”. Một inner transaction hoàn tất trước outer boundary có thể tạo cửa sổ không nhất quán khác; dùng khi thực sự chủ đích cần một transaction độc lập.

---

## 14. Migration từng bước trong một codebase thực

### 14.1. Bước 1 — Inventory

Tìm tất cả chỗ sử dụng:

```text
ChainedKafkaTransactionManager
ChainedTransactionManager
setTransactionManager(
getTransactionManager(
KafkaTransactionManager
KafkaAwareTransactionManager
@Transactional
KafkaTemplate.executeInTransaction
transaction-id-prefix
setTransactionIdPrefix
AfterRollbackProcessor
DefaultErrorHandler
@RetryableTopic
```

Không phải mọi `setTransactionManager` trong toàn dự án đều là API Spring Kafka; một số component JDBC/JPA khác vẫn có setter hợp lệ. Cần xác định class nhận phương thức trước khi thay.

Ghi lại:

- Mỗi listener ID, topics, group ID, concurrency.
- Factory bean nào listener đang dùng.
- ProducerFactory/KafkaTemplate nào tham gia transaction.
- DB transaction manager được chọn.
- Thứ tự commit hiện tại của chain.
- Cách retry/DLT hoạt động.
- Business side effect nào có thể replay.
- Có idempotency/outbox/reconciliation hay không.

### 14.2. Bước 2 — Vẽ sơ đồ resource boundary

Ví dụ trước migration:

```text
@KafkaListener
    │
    ▼
ChainedKafkaTransactionManager(DB, Kafka)
    ├── Kafka producer transaction
    └── DB transaction
          │
          ▼
Commit ngược order constructor
```

Sau migration:

```text
@KafkaListener container
    │
    ▼
KafkaTransactionManager (outer)
    │
    ▼
@Transaction("dbTransactionManager") (inner)
    │
    ▼
DB commit
    │
    ▼
Kafka commit + consumed offsets
```

So sánh hai sơ đồ **về thứ tự commit**. Nếu legacy chain đặt DB rồi Kafka, old commit order là Kafka-first; thiết kế mới DB-first có thể **đổi hành vi recovery**. Cần quyết định đó có phù hợp nghiệp vụ không, không coi migration thuần thay tên class.

### 14.3. Bước 3 — Chuẩn hóa bean names

Đặt tên rõ:

```text
dbTransactionManager
kafkaTransactionManager
ordersTxListenerContainerFactory
ordersApplicationService
ordersEventListener
```

Với `@Transactional` luôn chỉ định manager khi có nhiều resource:

```java
@Transactional(transactionManager = "dbTransactionManager")
```

Nếu cần Kafka-only service transaction:

```java
@Transactional(transactionManager = "kafkaTransactionManager")
```

Không dùng `@Primary` tùy tiện để che ambiguity khi hai nhóm method phải tham gia transaction khác nhau.

### 14.4. Bước 4 — Thay container property

Đổi:

```java
props.setTransactionManager(chainedKafkaTransactionManager);
```

thành:

```java
props.setKafkaAwareTransactionManager(
        kafkaTransactionManager);
```

và chuyển phần DB transaction vào một service được bảo vệ qua Spring transaction proxy. Xóa bean chained manager nếu không còn chỗ dùng, đồng thời xóa import/reference cũ.

### 14.5. Bước 5 — Giữ producer/config đồng nhất

Kiểm tra:

- `ProducerFactory.transactionCapable()`.
- `KafkaTemplate` dùng cùng ProducerFactory như Kafka TM.
- `transactionIdPrefix` đã được cấp riêng mỗi pod/instance.
- Consumer isolation level phù hợp với output transactional.
- Consumer `enable.auto.commit=false` khi dùng container-managed offsets.
- DLT/after-rollback policy được thiết kế cho transactional container.
- Transaction cache đủ capacity khi concurrency tăng.

### 14.6. Bước 6 — Thêm idempotency nếu chưa có

Trước khi deploy, xác định **ít nhất** cách tránh nhân đôi DB side effect khi Kafka commit fail sau DB commit. Ưu tiên unique business key + dedup table trong cùng DB transaction. Nếu dùng HTTP/email, cần idempotency key/outbox và reconciliation riêng.

### 14.7. Bước 7 — Kiểm thử fault injection

Không chỉ kiểm tra listener xử lý thành công. Bắt buộc test:

- DB commit thất bại.
- Kafka commit thất bại sau DB commit.
- Pod chết trước Kafka commit.
- Redelivery của cùng event ID.
- Producer bị fence.
- DLT/recovery failure.
- Transaction ID prefix collision giữa replicas.
- Retry sau broker outage.
- Sai transaction manager bean.
- Self-invocation làm thiếu DB transaction.

### 14.8. Bước 8 — Canary và rollback plan

Triển khai trước lên staging/canary với group/topic dữ liệu test độc lập; đo error rate, retries, rebalance và business duplicates. Nếu triển khai dần trong cùng group, xác nhận các versions đang xử lý được cùng schema và cùng idempotency contract.

Nếu cần rollback binary, đừng chỉ rollback code: kiểm tra messages đã publish, offsets đã commit và những DB side effects đã xảy ra. Chạy lại code cũ dùng chained manager có thể tạo hành vi recovery khác phiên bản mới; rollback cần có quy trình dữ liệu đi kèm.

---

## 15. Checklist API theo phiên bản

| Nhiệm vụ | Spring Kafka 2.6 trở về trước | 2.7–3.1 | 3.2–3.3 | Ghi chú |
|---|---|---|---|---|
| Chaining DB + Kafka | Có dự án dùng `ChainedKafkaTransactionManager` | Deprecated từ 2.7 | Vẫn deprecated | Không dùng mới |
| Container transaction setter | `setTransactionManager(...)` | Có API cũ | Deprecated từ 3.2 | Dùng setter narrow type |
| Kafka TM | `KafkaTransactionManager` | Hỗ trợ | Hỗ trợ | Manager chính cho Kafka transaction |
| Narrow transaction manager | `KafkaAwareTransactionManager` | Có | Có | Dùng ở container API mới |
| Kafka EOS mode | Có legacy mode tùy version | Chuyển đổi theo release | Chỉ EOS V2 từ 3.0 | Không hard-code mode cũ |
| Producer transaction-id prefix | Bắt buộc để producer transactional | Hỗ trợ | Hỗ trợ | Duy nhất theo instance |
| Transaction ID suffix cache | Producer cache từ trước | Có | API suffix strategy từ 3.2 | Sizing theo concurrency |

**Bảng chỉ định hướng migration**, không thay thế tài liệu release notes của phiên bản cụ thể. Một hệ Spring Boot 3.4/Spring Kafka 3.3 nên dùng nhóm API từ 3.2+; dự án Spring Boot 4 cần cập nhật namespace auto-configuration và có thể có thay đổi khác ngoài phạm vi transaction manager.

### 15.1. Không nhầm thay đổi package với deprecation transaction

Ví dụ Spring Boot 3.x:

```java
org.springframework.boot.autoconfigure.kafka
    .ConcurrentKafkaListenerContainerFactoryConfigurer
```

Spring Boot 4.x chuyển configurer sang namespace khác. Đây là **migration framework API/package**, không phải lý do dùng lại ChainedKafkaTransactionManager. Luôn xét version matrix toàn bộ Boot, Spring Kafka, Spring Framework, Spring Data và Kafka clients.

---

## 16. Tính nhất quán theo thứ tự: producer-only và consumer-initiated

Đây là một điểm dễ bị hiểu nhầm khi đọc tài liệu.

### 16.1. Producer-only transaction synchronization

```text
@Transactional("dbTransactionManager")
  update DB
  KafkaTemplate.send(...)
RETURN
  COMMIT DB
  COMMIT synchronized Kafka transaction
```

Có thể gọi là **DB-first**.

### 16.2. Consumer-initiated Kafka transaction

```text
Container starts Kafka transaction
  @Transactional("dbTransactionManager")
     update DB
     KafkaTemplate.send(...)
  COMMIT DB
  RETURN from listener
Container commits Kafka transaction (+ offset)
```

Cũng là **DB-first** trong mẫu được khuyến nghị.

### 16.3. Nested Kafka-first khi producer-only

```text
@Transactional("dbTransactionManager") outer
  update DB
  @Transactional("kafkaTransactionManager") inner
     KafkaTemplate.send(...)
  COMMIT Kafka
COMMIT DB
```

Đây là **Kafka-first**. Nó không áp dụng tự động khi Kafka listener container đã mở Kafka outer transaction; thứ tự scope khác.

### 16.4. Vì sao cần phân biệt?

Vì exception ở bước commit sau cùng có nghĩa khác nhau:

| Thứ tự | Bước đầu đã thành công | Bước sau lỗi | Hệ quả |
|---|---|---|---|
| DB-first | DB commit | Kafka commit | Có DB row nhưng Kafka event/offset có thể chưa được commit |
| Kafka-first | Kafka commit | DB commit | Có event Kafka nhưng DB row chưa có |
| Kafka-only | Kafka transaction abort | Không có DB transaction | Kafka output/offset trong transaction không commit |

Không có phương án nào với **hai local resources độc lập** cho atomic commit hoàn hảo dưới mọi network/power failure. Hệ thống phải có **business recovery**, không chỉ exception handling.

---

## 17. Kiểm thử migration với Embedded Kafka và database

### 17.1. Test dependencies

Ví dụ Gradle cho Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.kafka:spring-kafka'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.kafka:spring-kafka-test'
    testImplementation 'org.testcontainers:postgresql'
    testImplementation 'org.testcontainers:kafka'
}
```

Trong production, version Gradle/Spring Boot/Testcontainers cần được quản lý theo BOM tương thích. Ví dụ liệt kê các dependency thông dụng, không phải một build đã được chạy.

### 17.2. Integration test skeleton

Test cần broker thật/EmbeddedKafka và một DB test có transaction:

```java
@SpringBootTest
@EmbeddedKafka(
        partitions = 3,
        topics = {
                "orders.events",
                "orders.processed"
        },
        bootstrapServersProperty =
                "spring.kafka.bootstrap-servers")
class KafkaTxMigrationIT {

    @Autowired
    KafkaListenerEndpointRegistry registry;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void transactionalContainerIsRegistered() {
        var container =
                registry.getListenerContainer("orders-tx-v1");
        assertNotNull(container);
    }

    // Các test tiếp theo gửi event thật, đợi bằng
    // Awaitility/latch rồi assert DB + Kafka.
}
```

Imports tham khảo:

```java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.test.context.EmbeddedKafka;
```

Skeleton chỉ xác nhận Spring context đã đăng ký container. Nó **không tự chứng minh** transaction boundaries. Cần test broker + DB, faults và redelivery thực.

### 17.3. Test DB success rồi Kafka commit fail

Đây là failure case quan trọng nhất của mẫu consumer-initiated DB-first:

1. Gửi event `evt-123` vào `orders.events`.
2. Cho service JDBC ghi thành công và commit.
3. Tạo tình huống Kafka transaction commit thất bại có kiểm soát (ví dụ broker interruption/fault injection phù hợp môi trường).
4. Xác minh DB có business row nhưng consumed offset có thể chưa được commit.
5. Phục hồi broker, để record được giao lại.
6. Xác nhận dedup table ngăn business side effect bị lặp.
7. Xác nhận Kafka output cuối cùng ở trạng thái đúng theo recovery contract.

Test này có thể khó tạo xác suất lỗi đúng cửa sổ chỉ bằng `Thread.sleep`. Dùng fault-injection hook hoặc Testcontainers/proxy điều khiển network, và xác nhận bằng committed offsets, records và DB state. Không coi unit test Mockito của service là đủ.

### 17.4. Test Kafka producer fencing

Chạy hai instances cố tình dùng cùng `transactionIdPrefix` trong môi trường test:

- Quan sát `ProducerFencedException`/transaction failures.
- Xác nhận instance bị fence không tiếp tục publish như thành công.
- Đổi sang prefix unique theo instance và kiểm tra ổn định.
- Thử rolling restart và graceful shutdown.

Không làm bài test gây fencing lên producer ID production.

### 17.5. Test rollback do DB error

1. Gửi input record.
2. Tạo lỗi DB constraint/connection tại service.
3. Đảm bảo exception được truyền tới container.
4. Kafka transaction rollback, không có committed Kafka output cho attempt lỗi.
5. Khôi phục DB.
6. Record được xử lý lại thành công hoặc đi qua after-rollback recovery theo policy.
7. Không có duplicate DB effect.

### 17.6. Test transaction manager bean selection

Đặt hai bean:

```text
dbTransactionManager
kafkaTransactionManager
```

Rồi test một method `@Transactional("dbTransactionManager")` thực sự rollback JDBC insert khi ném exception. Điều này phát hiện annotation trên method không được Spring proxy áp dụng, bean qualification sai hoặc data source dùng transaction manager khác.

### 17.7. Test DLT với transactional container

- Poison message cố định.
- AfterRollbackProcessor thử đúng số attempts.
- Recovery publish DLT thành công theo transaction policy.
- Recovered offset được commit hoặc record nguồn tiếp tục redeliver theo contract đã chọn.
- Nếu DLT producer lỗi, không được mất record nguồn âm thầm.
- Replay DLT có idempotency và không tạo vòng lặp vô hạn.

### 17.8. Test Kafka-only EOS

- Input event tạo một output record.
- Inject exception trước commit để transaction abort.
- Consumer `read_committed` không nhìn thấy output từ transaction abort.
- Retry thành công dẫn tới một output kết quả hợp lệ theo EOS contract.
- Đo record offsets và transaction state, không chỉ log application.

---

## 18. Các cảnh báo và metric sau nâng cấp

### 18.1. Những chỉ số cần theo dõi

| Chỉ số | Tác dụng |
|---|---|
| Kafka transaction commit successes/failures | Phát hiện publish/offset không được commit |
| Producer fenced errors | Phát hiện duplicate transactional.id hoặc stale producer |
| Transaction abort/rollback count | Phát hiện lỗi nghiệp vụ hoặc dependency |
| Consumer lag/rebalance | Xem redelivery và khả năng catch-up |
| DB deadlocks/rollback/commit latency | Đánh giá DB transactional behavior |
| Kafka producer send latency/retries | Phát hiện broker/network problem |
| `NoProducerAvailableException` | Transaction ID suffix cache/producer capacity |
| DLT/recovery success/failure | Đảm bảo poison messages không mất |
| Business dedup hits | Đếm redelivery và producer duplicate theo eventId |
| Outbox pending age/count | Detect DB commit nhưng event chưa publish |
| Partial-commit incidents | Đối soát số event thiếu/không khớp DB |
| Processing latency p95/p99 | Cảnh báo transaction giữ quá lâu |

Không phải tất cả metric có sẵn với tên trên; một số cần custom Micrometer counters hoặc query DB/outbox. Khi cấu hình monitoring, dùng label có cardinality thấp như service, cluster, transaction outcome và error category; không gắn eventId mỗi record vào metric tags.

### 18.2. Log có cấu trúc

Ví dụ:

```json
{
  "event": "KAFKA_TX_COMMIT_FAILED",
  "listenerId": "orders-tx-v1",
  "groupId": "orders-worker",
  "topic": "orders.events",
  "partition": 1,
  "offset": 10998,
  "transactionalIdPrefix": "orders-pod-a-tx-",
  "dbOperation": "ORDER_STATUS_UPDATE",
  "dbOutcome": "COMMITTED",
  "kafkaOutcome": "UNKNOWN_OR_FAILED",
  "reconciliationRequired": true
}
```

Đây là **mẫu dữ liệu log**, không phải event thật. Quan trọng: nếu ứng dụng chưa biết DB commit có hoàn thành hay không, không ghi `dbOutcome=COMMITTED` bằng suy đoán. Trường hợp có sự cố mạng tại commit, outcome có thể unknown; cần xác minh ở hệ thống nguồn.

Không log credentials, producer config chứa SASL password, raw payload PII hoặc token. Transactional ID và business key có thể là metadata nhạy cảm tùy hệ thống; mask khi cần.

### 18.3. Cảnh báo đáng ưu tiên

- Producer fencing tăng sau rolling deployment.
- Consumer lag tăng liên tục kèm transaction abort.
- Kafka commit failure rate tăng.
- DB dedup hits tăng đột biến sau pod restarts.
- DLT producer/recoverer thất bại.
- Outbox pending quá SLA.
- Không có record processed thành công dù source có input.
- Transaction ID suffix cache cạn khi tăng concurrency.

Không coi việc consumer lag bằng 0 là bằng chứng DB và Kafka đã nhất quán: listener có thể nuốt exception hoặc recovery policy đã chuyển nhiều record sang DLT.

---

## 19. Runbook khi migration gặp sự cố

### 19.1. Bean startup error hoặc ambiguous transaction manager

1. Kiểm tra các bean tên `dbTransactionManager` và `kafkaTransactionManager` có tồn tại không.
2. Xem có đồng thời Boot auto-create và custom Kafka manager trùng mục đích không.
3. Kiểm tra các `@Transactional` đã chọn đúng transaction manager.
4. Kiểm tra `KafkaTemplate` và `KafkaTransactionManager` dùng cùng ProducerFactory.
5. Xác nhận `transactionIdPrefix` đã được cấu hình và ProducerFactory transaction-capable.
6. Không sửa bằng cách đặt đại một bean `@Primary` nếu chưa hiểu lời gọi nào cần DB/Kafka transaction.

### 19.2. ProducerFencedException sau deploy

1. So sánh transactional ID prefix của mọi pod đang sống.
2. Xác nhận mỗi pod/instance có prefix unique.
3. Xem hai deployment cũ/mới có chạy chồng lấn và dùng cùng prefix không.
4. Kiểm tra cache producer, maxAge và broker transaction ID expiration.
5. Đừng tái sử dụng producer bị fence như thể transaction còn hợp lệ.
6. Quan sát offset/DB dedup sau phục hồi, vì redelivery có thể xảy ra.

### 19.3. Kafka commit lỗi nhưng database đã ghi

1. Lấy topic/partition/offset/eventId và transaction outcome từ log.
2. Tra DB theo eventId; xác minh dedup marker và business row cùng transaction.
3. Kiểm tra Kafka committed offset/output event, tránh giả định từ exception message.
4. Nếu record được redeliver, xác nhận DB update idempotent.
5. Nếu output Kafka thiếu, dùng reconciliation/outbox/reprocess theo runbook.
6. Không sửa DB/Kafka offsets thủ công mà không xác định dữ liệu đã xử lý.

### 19.4. Message lỗi lặp không ngừng

1. Phân biệt deserialization, business validation, DB outage và Kafka commit error.
2. Xem listener có transactional container không.
3. Kiểm tra `AfterRollbackProcessor`, recovery attempts và DLT.
4. Tránh gắn handler non-transactional nuốt lỗi trong container transactional.
5. Nếu poison message cố định, dùng quarantine/DLT sau số attempt hữu hạn theo nghiệp vụ.
6. Với lỗi hạ tầng kéo dài, xem xét pause/stop để tránh retry storm.

### 19.5. Nhiều duplicate DB operations sau nâng cấp

1. Kiểm tra commit order đã thay từ Kafka-first sang DB-first không.
2. Xem pod restarts/rebalance/transaction abort.
3. Kiểm tra dedup uniqueness và marker được ghi cùng business transaction.
4. Tìm self-invocation làm DB `@Transactional` không được áp dụng.
5. Xác nhận producer events có eventId ổn định và không publish ID mới mỗi retry.
6. Nếu có duplicate không thể xóa tự động, triển khai reconciliation/compensation theo nghiệp vụ.

### 19.6. DLT không nhận record

1. Kiểm tra transactional path đang dùng `AfterRollbackProcessor` hay `DefaultErrorHandler`.
2. Xác nhận DLT producer, serializer, ACL, topic partition count và key.
3. Kiểm tra publish DLT có transactional hay không và đã thật sự commit chưa.
4. Nếu recoverer thất bại, nguồn phải còn có khả năng redelivery.
5. Nếu record bị commit offset mà không có DLT event, điều tra ngay nguy cơ mất dữ liệu.

---

## 20. Những sai lầm dễ gặp

| Sai lầm | Hậu quả | Hướng đúng |
|---|---|---|
| Nghĩ `KafkaTransactionManager` đã deprecated | Bỏ cơ chế được hỗ trợ | Phân biệt chính xác class/API |
| Thấy `ChainedKafkaTransactionManager` deprecated và thay class một-một | Mất DB transaction boundary | Chuyển DB `@Transactional` vào service |
| Dùng chain như XA transaction | Tin sai vào atomicity DB/Kafka | Partial commit design/idempotency |
| Không tính commit order cũ | Migration có behavior khác khi lỗi | Vẽ thứ tự trước/sau |
| Truyền DB manager vào `setKafkaAwareTransactionManager` | Không đúng type/semantics | Chỉ dùng KafkaAware manager |
| Dùng setter `setTransactionManager` deprecated từ 3.2 | Nợ kỹ thuật for-removal | Dùng setter mới |
| Không có `transaction-id-prefix` | Kafka producer không transactional đúng | Cấu hình producer factory rõ |
| Mọi pod dùng prefix giống nhau | Producer fencing | Prefix unique theo instance |
| Hai KafkaTemplates dùng producer factories khác nhau | Không cùng Kafka transaction | Thống nhất factory |
| `@Transactional` không qualifier khi có nhiều managers | Ambiguity hoặc mở sai transaction | Chỉ rõ bean name |
| Self-invocation qua `this.method()` | Có thể bỏ qua AOP proxy | Service bean riêng/proxy |
| Bắt exception rồi return success | Container commit dù business thất bại | Propagate exception đúng loại |
| Tin DB commit cũng gửi Kafka offset | Kafka offset nằm resource khác | Kafka transaction + redelivery policy |
| Tin DB rollback sẽ hủy Kafka commit đã xong | Không thể rollback resource đã commit | Reconcile/compensate |
| Coi `read_committed` là DB consistency | Chỉ ảnh hưởng đọc Kafka transactional records | DB transaction/idempotency riêng |
| `KafkaTemplate.executeInTransaction` để join outer tx | Có thể mở independent inner tx | Hiểu rõ scope của method |
| Dùng retry topics như non-tx listener | Ordering/transaction behavior thay đổi | Kiểm tra hỗ trợ transactional container |
| Dùng `DefaultErrorHandler` nuốt lỗi khi tx container | Có nguy cơ không rollback | AfterRollbackProcessor/propagate |
| Đổi Kafka group ID để “sửa offset” | Có thể replay/mất hàng loạt events | Quản lý offset có chủ đích |
| Tăng concurrency không tăng producer cache | Producer exhaustion | Capacity planning |
| Chỉ test happy path | Không thấy partial commit/redelivery | Fault injection integration tests |
| Rollback code nhưng không kiểm tra data | Có thể nhân đôi/mất business effect | Reconciliation trước/sau deploy |

---

## 21. Bài tập thực hành

### Bài 1 — Nhận diện deprecation

Đọc Javadoc của `ChainedKafkaTransactionManager`, `ChainedTransactionManager` và `ContainerProperties.setTransactionManager`. Ghi rõ phiên bản bắt đầu deprecated và replacement của từng API. Giải thích tại sao `KafkaTransactionManager` không thuộc nhóm phải bỏ.

### Bài 2 — Commit order legacy

Với chain `(dbTx, kafkaTx)`, xác định thứ tự begin/commit. Giả sử Kafka commit thành công rồi DB commit thất bại; vẽ trạng thái còn lại và kế hoạch reconciliation. Sau đó đảo thứ tự chain và làm lại.

### Bài 3 — Migration API

Chuyển một custom listener container factory từ `setTransactionManager(chainedTx)` sang `setKafkaAwareTransactionManager(kafkaTx)`, tách DB transaction vào service riêng có `@Transactional("dbTransactionManager")`. Xác nhận listener method vẫn ném exception khi service failed.

### Bài 4 — Kafka-only transaction

Tạo app đọc `orders.input` và gửi `orders.output` bằng container transactional. Kiểm tra record output trong transaction abort không xuất hiện ở consumer `read_committed` và input được redeliver.

### Bài 5 — DB-first failure

Tạo DB unique marker theo eventId. Giả lập DB commit thành công nhưng Kafka commit failed; redeliver event nhiều lần và chứng minh business side effect chỉ xảy ra một lần.

### Bài 6 — Producer-only DB + Kafka

Tạo method `@Transactional("dbTransactionManager")` ghi invoice rồi gửi Kafka. Mô tả trạng thái DB khi Kafka commit failed và triển khai outbox/reconciliation để xử lý.

### Bài 7 — Kafka-first nested transaction

Tách hai Spring beans, inner Kafka transaction và outer DB transaction. Giả lập DB commit failure sau Kafka commit thành công; giải thích vì sao event có thể visible khi DB chưa có invoice.

### Bài 8 — Self-invocation

Trong cùng service, gọi một method `@Transactional` bằng `this.method()` rồi làm một test rollback JDBC. Tách thành hai Spring beans/proxy và so sánh behavior.

### Bài 9 — Transaction ID per pod

Chạy hai instance dùng cùng `transactionIdPrefix` trong môi trường thử nghiệm, quan sát producer fencing. Sau đó cấp prefix unique và kiểm tra transactional publish ổn định.

### Bài 10 — AfterRollbackProcessor và DLT

Cấu hình transactional listener với poison message. Kiểm tra retry/recover và DLT publish thành công, rồi mô phỏng DLT failure. Chứng minh không âm thầm commit offset nguồn khi chưa lưu được record lỗi theo policy.

### Bài 11 — Sizing producer cache

Topic có sáu partitions, ba consumer threads và thêm nested producer transactions. Đề xuất cache size/suffix strategy dựa trên concurrency thực, kiểm thử exhaustion và alert `NoProducerAvailableException`.

### Bài 12 — ADR migration

Viết một Architecture Decision Record gồm: giao dịch hiện tại, lý do bỏ chained manager, commit order trước/sau, business idempotency, lựa chọn outbox, test partial commit, deployment/rollback plan và danh sách owner chịu trách nhiệm reconciliation.

---

## 22. Tài liệu tham khảo

- [Spring Kafka — Transactions (reference 3.3)](https://docs.spring.io/spring-kafka/reference/3.3/kafka/transactions.html): `KafkaTransactionManager`, transaction synchronization, consumer-initiated transactions và deprecation của chain.
- [Spring Kafka — ChainedKafkaTransactionManager Javadoc 3.3](https://docs.spring.io/spring-kafka/docs/3.3.x/api/org/springframework/kafka/transaction/ChainedKafkaTransactionManager.html): class deprecated và quan hệ kế thừa.
- [Spring Data — ChainedTransactionManager Javadoc](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/transaction/ChainedTransactionManager.html): begin/commit order, partial commit và `HeuristicCompletionException`.
- [Spring Kafka — ContainerProperties Javadoc 3.3](https://docs.spring.io/spring-kafka/docs/3.3.1/api/org/springframework/kafka/listener/ContainerProperties.html): setter cũ deprecated từ 3.2 và setter mới `setKafkaAwareTransactionManager`.
- [Spring Kafka — KafkaTransactionManager Javadoc 3.3](https://docs.spring.io/spring-kafka/docs/3.3.x/api/org/springframework/kafka/transaction/KafkaTransactionManager.html): transaction manager cho ProducerFactory.
- [Spring Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/3.3/kafka/exactly-once.html): scope EOS Kafka và container offset semantics.
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/3.3/kafka/annotation-error-handling.html): `AfterRollbackProcessor` và error recovery.
- [Spring Kafka — Tips, Tricks and Examples](https://docs.spring.io/spring-kafka/reference/3.3/tips.html): examples of transactions with other transaction managers.
- [Spring Kafka — Change History](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html): các mốc thay đổi như deprecation của chaining/container property.
- [Spring Boot 3.4 — Kafka Support](https://docs.spring.io/spring-boot/3.4/reference/messaging/kafka.html): `spring.kafka.*`, transactional producer và auto-configuration.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, proxy/self-invocation và transaction managers.
- [Apache Kafka — Transactions](https://kafka.apache.org/documentation/): transactional producer, `transactional.id`, consumer isolation và offset semantics.

## 23. Tổng kết

Deprecation của transaction manager cũ trong Spring Kafka không phải chỉ là một cảnh báo tên class. **`ChainedKafkaTransactionManager` (deprecated từ 2.7)** và **`ContainerProperties.setTransactionManager(...)` (deprecated từ 3.2)** đánh dấu hai thay đổi liên quan nhưng khác nhau: bỏ kiểu chaining tài nguyên dễ partial commit và dùng interface container transaction manager rõ Kafka-aware hơn.

Đối với consumer-initiated flow, thay thế được tài liệu Spring Kafka hướng dẫn là **KafkaTransactionManager ở listener container + `@Transactional` với DB transaction manager ở service**, không phải một chain giả định nguyên tử giữa Kafka và database. Với producer-only flow, transaction synchronization hoặc nested methods có thể chọn thứ tự commit, nhưng **DB-first lẫn Kafka-first đều có cửa sổ nhất quán cần xử lý**.

Một migration thành công vì thế phải chứng minh ba điều: **API không còn dùng deprecation cũ**, **commit/rollback/retry hoạt động đúng trên broker và database**, và **business side effects không bị nhân đôi hoặc mất khi có partial failure**. Các cơ chế cốt lõi là transaction ID duy nhất, idempotency/dedup, outbox khi cần, after-rollback recovery, observability và kiểm thử fault injection; không chỉ là code compile mà không còn warning.
