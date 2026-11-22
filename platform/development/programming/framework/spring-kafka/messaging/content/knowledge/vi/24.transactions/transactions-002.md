# `transactional.id` và `transactionIdPrefix`

Kafka transaction cho phép producer ghi nhiều record như một đơn vị nguyên tử: consumer dùng chế độ đọc phù hợp sẽ thấy toàn bộ transaction đã commit hoặc không thấy các record thuộc transaction bị abort. Để quản lý trạng thái transaction và nhận biết producer cũ đã bị thay thế, Kafka gắn một định danh cho producer là `transactional.id`.

Khi dùng Spring Kafka, ứng dụng thường cấu hình `transactionIdPrefix` trên producer factory. Spring Kafka ghép prefix này với hậu tố do factory quản lý để tạo `transactional.id` thực tế cho từng producer transactional. Vì vậy, prefix phải được thiết kế theo instance ứng dụng đang chạy; nếu nhiều instance dùng chung một prefix, producer có thể fencing lẫn nhau và làm transaction thất bại.

## 1. Phân biệt hai khái niệm

Hai tên gần giống nhau nhưng thuộc hai lớp khác nhau:

| Khái niệm | Nơi sử dụng | Vai trò |
|---|---|---|
| `transactional.id` | Kafka producer configuration | Định danh của một producer transactional trong Kafka. Kafka dùng nó để theo dõi transaction, khôi phục trạng thái và fencing producer cũ khi một producer mới sở hữu cùng ID. |
| `transactionIdPrefix` | Spring Kafka `DefaultKafkaProducerFactory` và cấu hình Spring Boot | Tiền tố để Spring Kafka tạo các `transactional.id` riêng cho những producer mà factory quản lý. |

Ví dụ, ứng dụng đặt prefix là `orders-pod-a-`. Spring Kafka có thể tạo các ID như `orders-pod-a-0`, `orders-pod-a-1` cho các producer transactional được factory cấp. Suffix cụ thể do factory quản lý; ứng dụng không nên tự gắn một suffix cố định rồi dùng chung cho nhiều producer đang hoạt động.

Trong cấu hình Kafka thuần, thuộc tính đúng là `transactional.id` (có chữ *al* ở cuối `transactional`). Spring Kafka cung cấp `transactionIdPrefix` để quản lý dải ID này. Không nhầm với `transaction.id`, vì đó không phải tên cấu hình producer Kafka.

## 2. Kafka dùng `transactional.id` để làm gì?

Kafka transaction có thể bao gồm nhiều record, kể cả record gửi tới nhiều partition hoặc topic trong cùng cluster. Producer bắt đầu transaction, gửi các record, rồi commit hoặc abort. Consumer cấu hình `isolation.level=read_committed` chỉ đọc các record thuộc transaction đã commit; các record thuộc transaction chưa hoàn tất hoặc đã abort không được trả như dữ liệu đã commit.

`transactional.id` giúp broker nhận diện một producer logic qua các phiên làm việc. Khi producer mới khởi tạo với cùng ID, broker tăng producer epoch và fencing producer cũ. Producer cũ không còn quyền tiếp tục ghi transaction với ID đó. Cơ chế này ngăn hai producer cùng sở hữu một định danh transactional và giúp khôi phục trạng thái transaction sau khi producer khởi động lại.

`transactional.id` cũng bật các bảo đảm cần thiết cho producer transaction và kéo theo idempotence. Tuy nhiên, cần phân biệt:

- **Idempotent producer** hạn chế record trùng do producer retry gửi trong một phiên producer.
- **Transaction** cho phép commit hoặc abort một nhóm record như một đơn vị và có thể phối hợp offset consumer trong cùng transaction Kafka.
- **Exactly-once processing trong Kafka** cần phối hợp transaction producer, offset consumer và consumer đọc `read_committed` theo đúng mô hình. Nó không tự biến cập nhật database hay lời gọi HTTP thành thao tác exactly-once.

`transactional.id` là định danh phục vụ quản lý producer transaction, không phải event ID, consumer group ID hay tên transaction nghiệp vụ.

## 3. Spring Kafka tạo `transactional.id` từ prefix

`DefaultKafkaProducerFactory` có thể quản lý các producer transactional và tạo suffix riêng cho từng producer. Ứng dụng cấu hình prefix trên factory; factory chịu trách nhiệm cấp producer với ID hoàn chỉnh và tái sử dụng producer theo cơ chế cache của nó.

Trong Spring Boot, có thể bật transaction bằng thuộc tính `spring.kafka.producer.transaction-id-prefix`:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      transaction-id-prefix: ${KAFKA_INSTANCE_ID:local}-orders-
```

`KAFKA_INSTANCE_ID` phải đại diện cho instance đang chạy. Ví dụ, mỗi pod Kubernetes có thể dùng tên pod làm giá trị. Khi chạy nhiều tiến trình local, hãy cấp giá trị khác nhau cho từng tiến trình; mặc định `local` chỉ phù hợp khi chỉ có một instance dùng prefix đó.

Nếu tự tạo `DefaultKafkaProducerFactory`, cấu hình prefix bằng Java:

```java
@Bean
public ProducerFactory<String, OrderEvent> orderProducerFactory(
        @Value("${app.kafka.instance-id}") String instanceId) {

    Map<String, Object> props = new HashMap<>();
    props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
    props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class);
    props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, JsonSerializer.class);

    DefaultKafkaProducerFactory<String, OrderEvent> factory =
            new DefaultKafkaProducerFactory<>(props);
    factory.setTransactionIdPrefix("orders-" + instanceId + "-");
    return factory;
}
```

Đây là ví dụ cấu hình tối thiểu; ứng dụng thực tế cần lấy bootstrap server, serializer, security và các producer property từ cấu hình môi trường. Khi Spring Kafka quản lý transactional ID bằng prefix, không đặt thêm một `transactional.id` tĩnh trong map producer properties vì factory cần tự tạo ID có suffix.

Nếu dùng cấu hình Spring Boot tự động, hãy đặt prefix ở `spring.kafka.producer.transaction-id-prefix`. Nếu tự tạo producer factory, gọi `setTransactionIdPrefix(...)`. Chọn một nơi cấu hình rõ ràng để tránh việc producer factory tùy biến vô tình bỏ qua prefix đã khai báo trong Boot properties.

## 4. Prefix phải duy nhất giữa các instance đang hoạt động

Đây là quy tắc vận hành quan trọng nhất: các instance ứng dụng cùng chạy và cùng tạo transactional producer phải có prefix riêng. Không dùng một prefix cố định chỉ dựa trên tên service cho mọi replica.

Giả sử có ba replica `order-service`:

| Instance | Prefix phù hợp | Ví dụ transactional ID |
|---|---|---|
| Pod A | `orders-pod-a-` | `orders-pod-a-0`, `orders-pod-a-1` |
| Pod B | `orders-pod-b-` | `orders-pod-b-0`, `orders-pod-b-1` |
| Pod C | `orders-pod-c-` | `orders-pod-c-0`, `orders-pod-c-1` |

Nếu cả ba pod đều dùng `orders-`, các factory có thể tạo ra cùng dải ID, chẳng hạn `orders-0`. Khi một producer khởi tạo với ID đang được producer khác sử dụng, Kafka fencing producer cũ. Hậu quả có thể là `ProducerFencedException`, transaction bị abort, thao tác gửi thất bại hoặc listener container phải phục hồi theo cơ chế lỗi.

Ví dụ cấu hình dễ gây xung đột:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-
```

Prefix trên chỉ an toàn nếu đúng một instance sử dụng nó trong cùng phạm vi Kafka. Khi scale nhiều replica, hãy đưa ID instance vào prefix:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${HOSTNAME}-orders-
```

Trong Kubernetes, `HOSTNAME` thường là tên pod và khác nhau giữa các pod. Ở môi trường khác, dùng instance ID do nền tảng cấp. Không dùng một biến môi trường chung giống nhau trên tất cả replica.

Prefix cần duy nhất giữa các producer factory có thể tạo cùng ID trong cùng cluster. Nếu một ứng dụng có nhiều producer factory transactional độc lập, hãy phân biệt cả service, instance và vai trò factory, ví dụ `orders-pod-a-outbound-` và `orders-pod-a-audit-`.

## 5. Duy nhất và ổn định: chọn instance ID thế nào?

Prefix phải phân biệt các instance đang hoạt động đồng thời. Đồng thời, định danh ổn định cho cùng một logical instance có thể giúp Kafka fencing tiến trình cũ khi tiến trình mới thay thế nó.

| Nguồn tạo instance ID | Đặc điểm | Lưu ý |
|---|---|---|
| Tên pod hoặc task | Thường duy nhất giữa các replica đang chạy và ổn định trong vòng đời pod/task | Phù hợp với môi trường orchestration; rolling deployment cần bảo đảm pod cũ và mới có tên khác nhau khi cùng hoạt động. |
| Hostname kết hợp service | Dễ vận hành trên VM hoặc máy chủ | Nếu nhiều tiến trình cùng service chạy trên một host, cần thêm process slot hoặc instance ID riêng. |
| UUID tạo lúc khởi động | Dễ tạo giá trị khác nhau cho từng tiến trình | Giảm khả năng đụng ID nhưng không tự fencing được tiến trình cũ nếu nó còn sống với UUID trước đó. |
| Tên service cố định | Dễ cấu hình | Không phù hợp cho nhiều replica vì tất cả có thể tạo cùng dải transactional ID. |

Trong triển khai có rolling update, mỗi instance mới phải có prefix riêng với instance cũ đang còn hoạt động. Khi cùng một logical instance khởi động lại và dùng lại định danh, producer mới có thể fencing producer cũ có cùng ID. Đây là hành vi hữu ích để ngăn hai tiến trình cùng sở hữu một producer identity, nhưng cũng có nghĩa hai tiến trình không được chia sẻ prefix.

Không nên chọn một giá trị ngẫu nhiên mới cho mọi lần khởi động nếu hệ thống cần nhận diện và fencing producer cũ của cùng một logical instance. UUID có thể bảo đảm uniqueness đồng thời, nhưng một định danh ổn định theo instance thường dễ quản lý vòng đời và sự cố split-brain hơn.

## 6. Prefix không tự bật transaction cho mọi thao tác

Khai báo `transactionIdPrefix` giúp Spring Kafka tạo transactional producer. Để một nhóm thao tác thực sự nằm trong transaction, ứng dụng còn phải chạy chúng trong transaction boundary, ví dụ qua `KafkaTemplate.executeInTransaction(...)` hoặc `KafkaTransactionManager`.

Ví dụ dùng `executeInTransaction`:

```java
public void publishOrderEvents(OrderCreated created, OrderAudited audited) {
    kafkaTemplate.executeInTransaction(operations -> {
        operations.send("orders", created.orderId(), created);
        operations.send("order-audit", audited.orderId(), audited);
        return null;
    });
}
```

Hai record được gửi trong cùng transaction do `executeInTransaction` mở. Nếu callback hoàn tất bình thường, transaction được commit; nếu exception thoát khỏi callback, transaction được abort. Các topic phải thuộc cùng Kafka cluster và producer factory của `KafkaTemplate` phải được cấu hình transactional.

Có thể dùng `KafkaTransactionManager` khi muốn tích hợp transaction vào Spring transaction abstraction:

```java
@Bean
public KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
        ProducerFactory<String, OrderEvent> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
```

Sau đó một phương thức Spring có thể dùng `@Transactional("kafkaTransactionManager")` để gửi record qua `KafkaTemplate` trong transaction. Phương thức phải được gọi qua Spring proxy; self-invocation trong cùng bean không kích hoạt proxy transaction như mong đợi. Nếu phối hợp Kafka với transaction database, cần hiểu rõ transaction manager nào quản lý tài nguyên nào và thứ tự commit; hai hệ thống không tự trở thành một distributed atomic transaction chỉ vì cùng dùng `@Transactional`.

Với `@KafkaListener`, có thể cấu hình listener container dùng `KafkaTransactionManager` để xử lý consume-transform-produce trong transaction. Khi đó, offset của record đã tiêu thụ và các record được publish có thể được commit trong cùng Kafka transaction. API cấu hình container manager có thể khác theo phiên bản Spring Kafka; hãy dùng API tương ứng phiên bản dự án đang chạy.

## 7. Producer fencing và các lỗi thường gặp

`ProducerFencedException` thường là dấu hiệu một producer khác đã chiếm cùng transactional ID hoặc producer hiện tại không còn epoch hợp lệ. Khi gặp lỗi này, không nên chỉ tăng timeout hoặc retry vô hạn; hãy kiểm tra nguồn cấp prefix và vòng đời instance.

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `ProducerFencedException` | Hai producer cùng dùng transactional ID; producer cũ bị producer mới fencing | Kiểm tra `transactionIdPrefix`, instance ID, số replica và các producer factory. |
| Transaction liên tục abort khi deploy | Instance mới và cũ dùng chung prefix trong rolling update | Bảo đảm mỗi instance đang chạy có prefix khác nhau. |
| Transaction không được bật | Producer factory chưa nhận prefix hoặc `KafkaTemplate` dùng factory khác | Kiểm tra bean wiring và cấu hình Boot/custom factory. |
| Không đọc được record chưa commit | Consumer đang dùng `read_committed` và producer chưa commit hoặc đã abort transaction | Kiểm tra trạng thái transaction, producer log và transaction timeout. |
| Transaction timeout | Công việc trong transaction kéo dài hoặc cấu hình timeout không phù hợp | Rút ngắn transaction, kiểm tra `transaction.timeout.ms` và giới hạn broker. |
| Producer factory hết producer transactional khả dụng | Nhu cầu producer đồng thời vượt khả năng cache/suffix được cấu hình | Kiểm tra concurrency, cache capacity và vòng đời producer theo phiên bản Spring Kafka. |

Kafka có thể fencing producer cũ khi cùng ID được khởi tạo lại. Producer đã bị fencing không thể tiếp tục transaction với ID đó; ứng dụng cần để producer factory/container tạo hoặc lấy producer hợp lệ theo cơ chế của Spring Kafka. Không tự bắt `ProducerFencedException` rồi tiếp tục coi transaction cũ là thành công.

## 8. Các cấu hình liên quan nhưng không thay thế prefix

Một số thuộc tính thường xuất hiện cùng transaction nhưng giải quyết vấn đề khác nhau:

| Thuộc tính | Ý nghĩa | Quan hệ với `transactionIdPrefix` |
|---|---|---|
| `transaction.timeout.ms` | Thời gian tối đa broker cho phép transaction mở trước khi timeout | Không tạo ID; điều chỉnh giới hạn thời gian của transaction. |
| `transaction.max.timeout.ms` | Giới hạn timeout tối đa mà broker chấp nhận từ producer | Giới hạn cho `transaction.timeout.ms`, không phải prefix. |
| `isolation.level` | Consumer chọn đọc `read_uncommitted` hay `read_committed` | Quyết định consumer có thấy record chưa commit/đã abort hay không. |
| `enable.idempotence` | Bảo đảm producer gửi retry không tạo duplicate trong phạm vi hỗ trợ của producer | Transactional producer bật các bảo đảm idempotence cần thiết; thuộc tính này không thay thế ID duy nhất. |
| `group.id` | Định danh consumer group | Không dùng làm transactional ID; nhiều producer có thể không liên quan tới group đó. |

Broker cluster cũng cần cấu hình transaction state log đủ độ bền cho môi trường vận hành. Trong production, kiểm tra replication factor và min ISR phù hợp với số broker, quyền truy cập topic và giới hạn transaction timeout. `transactionIdPrefix` đúng không thể bù cho broker transaction state log thiếu khả năng chịu lỗi.

## 9. Quy trình kiểm tra cấu hình trong môi trường thật

Trước khi triển khai transaction producer, hãy kiểm tra theo từng bước:

1. **Xác định phạm vi producer.** Liệt kê service, instance, producer factory và vai trò của từng factory đang tạo transactional producer.
2. **Thiết kế prefix.** Kết hợp tên service, instance ID và vai trò factory. Xác nhận không có hai instance đồng thời dùng cùng prefix trong cùng cluster.
3. **Kiểm tra cách tạo ID.** Nếu dùng Spring Boot, xác nhận `spring.kafka.producer.transaction-id-prefix` được bind. Nếu tự tạo factory, xác nhận đã gọi `setTransactionIdPrefix(...)` trên đúng factory được `KafkaTemplate` sử dụng.
4. **Kiểm tra transaction boundary.** Xác nhận gửi record nằm trong `executeInTransaction`, `@Transactional` với `KafkaTransactionManager` hoặc listener container transaction phù hợp.
5. **Kiểm tra consumer visibility.** Với luồng cần chỉ đọc dữ liệu đã commit, đặt `isolation.level=read_committed` cho consumer tương ứng.
6. **Thử chạy nhiều instance.** Khởi động ít nhất hai instance đồng thời, kiểm tra transactional ID sinh ra khác nhau và không xuất hiện fencing ngoài dự kiến.
7. **Thử restart và rolling update.** Xác minh instance mới không đụng prefix với instance khác đang chạy; xác minh logical instance thay thế có thể fencing tiến trình cũ đúng cách.
8. **Thử commit và abort.** Gửi nhiều record trong một transaction, xác minh consumer `read_committed` chỉ thấy nhóm commit và không thấy record đã abort.
9. **Theo dõi production.** Thu thập số transaction commit/abort, timeout, producer fencing, lỗi gửi và thời gian transaction. Cảnh báo khi fencing xuất hiện bất thường.

Trong log vận hành, nên ghi tên service, instance ID, vai trò producer factory và transaction outcome. Prefix không phải secret, nhưng vẫn nên tránh log quá nhiều chi tiết cấu hình không cần thiết. Khi sự cố fencing xảy ra, những thông tin này giúp xác định hai instance nào đang tranh chấp cùng ID.

`transactional.id` là định danh Kafka dùng để quản lý một producer transactional; `transactionIdPrefix` là cách Spring Kafka tạo các định danh đó một cách có hệ thống. Khi mỗi instance có prefix riêng, producer factory quản lý suffix và transaction boundary được cấu hình rõ ràng, ứng dụng có thể dùng Kafka transaction an toàn hơn trong môi trường nhiều replica và khi triển khai rolling update.
