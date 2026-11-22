# Các bảo đảm cốt lõi của Kafka

Kafka được thiết kế để truyền và lưu trữ luồng sự kiện trên một cụm broker phân tán. Khi nói Kafka “đảm bảo” một thông điệp được gửi, lưu, đọc hoặc xử lý, cần tách các thuộc tính khác nhau: thứ tự của bản ghi, độ bền khi broker gặp sự cố, và ngữ nghĩa giao nhận khi producer hoặc consumer lỗi giữa chừng.

Trong ứng dụng Spring Kafka, các thuộc tính này được thể hiện qua `KafkaTemplate`, `@KafkaListener`, cấu hình producer/consumer, commit offset và transaction. Hiểu đúng ranh giới của từng bảo đảm giúp thiết kế luồng messaging tin cậy mà không mặc định rằng một cấu hình đơn lẻ có thể loại bỏ mọi lỗi.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích thứ tự của Kafka được đảm bảo ở cấp partition và vì sao topic không có một thứ tự toàn cục.
- Chọn `acks`, replication factor và `min.insync.replicas` để cân bằng độ bền với khả năng ghi.
- Phân biệt at-most-once, at-least-once và exactly-once; mô tả thời điểm commit offset ảnh hưởng đến từng ngữ nghĩa.
- Giải thích producer idempotence khác gì Kafka transaction và vì sao transaction không bao phủ mặc định cơ sở dữ liệu hoặc HTTP API.
- Áp dụng các bảo đảm trên khi xây dựng producer, consumer và luồng consume-transform-produce bằng Spring Kafka.

## 1. Mô hình cần nhớ

Một record Kafka thường có key, value, timestamp và headers. Record được ghi vào một partition của topic. Mỗi partition là một log có thứ tự: broker gán cho record một offset tăng dần trong partition đó.

Một topic có thể có nhiều partition và được sao chép trên nhiều broker:

- **Leader replica** nhận yêu cầu đọc/ghi cho partition.
- **Follower replica** sao chép dữ liệu từ leader.
- **ISR (in-sync replicas)** là tập các replica đang theo kịp leader theo tiêu chí đồng bộ của Kafka.
- **Consumer group** chia các partition giữa các consumer member. Trong một thời điểm ổn định, một partition được giao cho tối đa một member trong cùng group.
- **Consumer offset** ghi nhận vị trí tiếp theo mà group sẽ đọc trong một partition.

Ba câu hỏi khác nhau cần được trả lời riêng:

| Câu hỏi | Cơ chế chính | Phạm vi |
|---|---|---|
| Record được nhìn thấy theo thứ tự nào? | Partition và offset | Một partition |
| Record còn tồn tại khi broker lỗi không? | Replication, ISR và producer acknowledgement | Một partition và cụm broker |
| Record có thể bị mất hoặc xử lý lặp không? | Producer retry, consumer offset và transaction | Producer/consumer hoặc pipeline |

Kafka không tự tạo ra một thứ tự toàn cục giữa các partition. Một consumer group cũng không tự đảm bảo side effect trong hệ thống bên ngoài chỉ xảy ra một lần.

## 2. Bảo đảm thứ tự: chỉ trong một partition

Kafka lưu record trong mỗi partition theo thứ tự append. Nếu consumer đọc tuần tự một partition, consumer nhận các record theo thứ tự offset tăng dần. Ví dụ, các sự kiện của một đơn hàng có thể được gửi với cùng key:

```text
topic: order-events
key: order-42

partition 2:
offset 100 -> OrderCreated
offset 101 -> PaymentAuthorized
offset 102 -> OrderPacked
offset 103 -> OrderShipped
```

Để các sự kiện cùng một thực thể đi vào cùng partition, producer thường dùng định danh thực thể làm key:

```java
kafkaTemplate.send("order-events", orderId, event);
```

Với partitioner mặc định, cùng key thường được ánh xạ vào cùng partition khi cấu hình partition không đổi. Vì vậy, `orderId` là key hợp lý nếu yêu cầu nghiệp vụ là giữ thứ tự sự kiện của từng đơn hàng.

Có một số giới hạn quan trọng:

1. Hai record ở hai partition khác nhau không có quan hệ thứ tự tổng thể. Timestamp giống nhau cũng không tạo ra thứ tự xử lý.
2. Nếu tăng số partition, phép ánh xạ key sang partition có thể thay đổi. Các record cũ của một key có thể nằm ở partition cũ trong khi record mới đi vào partition khác; cần cân nhắc việc mở rộng partition khi thứ tự theo key là yêu cầu bắt buộc.
3. Nếu ứng dụng chuyển việc xử lý sang các tác vụ bất đồng bộ hoặc xử lý song song sau khi nhận record, thứ tự hoàn tất side effect có thể khác thứ tự Kafka đã giao.
4. Nhiều producer cùng ghi một key vẫn được sắp thứ tự theo thứ tự broker nhận và append record; Kafka không biết thứ tự nghiệp vụ mà các producer mong muốn.

Trong Spring Kafka, thuộc tính `concurrency` có thể tạo nhiều consumer thread để xử lý các partition khác nhau. Hãy tránh tự đưa các record của cùng partition vào một hàng đợi xử lý song song nếu nghiệp vụ cần giữ thứ tự.

**Quy tắc thiết kế:** chọn key theo đơn vị cần giữ thứ tự, chẳng hạn `orderId`, `accountId` hoặc `customerId`. Đừng chọn key ngẫu nhiên nếu các sự kiện liên quan phải được xử lý tuần tự.

## 3. Bảo đảm độ bền: replication và acknowledgement

Replication giúp partition tiếp tục tồn tại khi một broker gặp sự cố. Với replication factor bằng 3, một partition có một leader và tối đa hai follower. Tuy nhiên, replication factor tự nó chưa nói producer cần chờ bao nhiêu replica trước khi coi một lần ghi là thành công.

Producer kiểm soát mức chờ thông qua `acks`:

| Giá trị | Điều producer chờ | Hệ quả chính |
|---|---|---|
| `0` | Không chờ broker xác nhận | Độ trễ thấp, producer không biết broker đã nhận record hay chưa; nguy cơ mất dữ liệu cao hơn |
| `1` | Leader xác nhận sau khi nhận record | Có thể mất record nếu leader lỗi trước khi follower sao chép |
| `all` hoặc `-1` | Các replica hiện thuộc ISR xác nhận | Độ bền tốt hơn; yêu cầu ghi có thể thất bại nếu ISR không đạt ngưỡng tối thiểu |

Hai cấu hình cần được xem cùng nhau:

- `replication.factor` xác định số bản sao mục tiêu của partition.
- `min.insync.replicas` xác định số replica tối thiểu phải còn trong ISR để broker chấp nhận một lần ghi có `acks=all`.

Ví dụ, topic có replication factor là 3 và `min.insync.replicas=2`. Khi leader và ít nhất một follower còn trong ISR, broker có thể chấp nhận ghi với `acks=all` sau khi các replica thuộc ISR xác nhận. Nếu ISR chỉ còn một replica, broker từ chối ghi thay vì âm thầm hạ mức bảo đảm.

Cấu hình này tạo ra một đánh đổi có chủ đích: khi cụm mất quá nhiều replica, ứng dụng có thể tạm thời không ghi được. Đó là hành vi bảo vệ độ bền dữ liệu; hệ thống cần retry có giới hạn, cảnh báo và quy trình khôi phục phù hợp.

Ví dụ cấu hình producer trong Spring Kafka:

```java
Map<String, Object> producerProps = new HashMap<>();

producerProps.put(ProducerConfig.ACKS_CONFIG, "all");
producerProps.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
producerProps.put(ProducerConfig.RETRIES_CONFIG, Integer.MAX_VALUE);
producerProps.put(
    ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
    5
);

// Đưa producerProps vào ProducerFactory cùng bootstrap servers
// và serializer phù hợp với kiểu key/value của ứng dụng.
```

Ví dụ trên minh họa các thuộc tính liên quan đến acknowledgement và retry. Cấu hình topic/broker vẫn phải đặt replication factor và `min.insync.replicas` phù hợp. Chỉ đặt `acks=all` ở producer không thể thay thế cấu hình replication.

Một số giới hạn cần ghi nhớ:

- `acks=all` có nghĩa là chờ tất cả replica hiện thuộc ISR, không nhất thiết là mọi replica được khai báo trong replication factor.
- Acknowledgement xác nhận broker đã chấp nhận lần ghi theo cơ chế replication; nó không có nghĩa consumer đã đọc hoặc xử lý record.
- Retention vẫn áp dụng. Record có thể hết hạn theo `retention.ms`/`retention.bytes`, hoặc bị thay thế theo chính sách log compaction. Replication không có nghĩa dữ liệu được giữ vĩnh viễn.
- Nếu cho phép bầu leader từ replica ngoài ISR, có thể đánh đổi độ sẵn sàng lấy nguy cơ mất các record chưa được replica đó nhận. Hãy hiểu rõ cấu hình bầu leader không sạch trước khi thay đổi.

## 4. Ngữ nghĩa giao nhận: at-most-once và at-least-once

Consumer đọc record theo offset nhưng việc xử lý record và việc commit offset là hai hành động riêng. Lỗi có thể xảy ra giữa hai hành động đó. Thứ tự thực hiện quyết định record có thể bị mất hay được xử lý lặp.

### At-most-once

Consumer commit offset trước khi hoàn tất xử lý record.

```text
đọc record -> commit offset -> xử lý nghiệp vụ
                         |
                         +-- tiến trình lỗi ở đây: record có thể bị bỏ qua
```

Cách này tránh xử lý lại record đã commit, nhưng có nguy cơ mất xử lý nếu tiến trình dừng sau commit và trước khi side effect hoàn tất. Chỉ phù hợp khi bỏ sót một số record có thể chấp nhận được.

### At-least-once

Consumer xử lý thành công trước, sau đó mới commit offset.

```text
đọc record -> xử lý nghiệp vụ -> commit offset
                     |
                     +-- lỗi trước commit: record sẽ được đọc lại
```

Cách này ưu tiên không bỏ qua record, nhưng có thể xử lý lặp. Ví dụ, dịch vụ đã ghi khoản thanh toán vào database thành công rồi bị dừng trước khi commit offset. Khi consumer khởi động lại, record được đọc lại và thao tác ghi có thể chạy lần thứ hai.

At-least-once thường là lựa chọn thực tế cho consumer nghiệp vụ, với điều kiện handler có tính idempotent.

### Vì sao offset phải được commit đúng thời điểm?

Offset đã commit của một consumer group là vị trí tiếp theo cần đọc trong partition. Giả sử consumer xử lý thành công record offset 25; vị trí tiếp theo cần commit là 26.

Nếu commit quá sớm, có thể mất xử lý. Nếu commit quá muộn hoặc tiến trình lỗi trước commit, record có thể được giao lại. Tắt auto-commit và để listener container quản lý acknowledgement thường giúp ứng dụng gắn việc commit với kết quả xử lý rõ ràng hơn.

Ví dụ listener xử lý trước rồi mới acknowledge trong chế độ manual:

```java
@KafkaListener(topics = "order-events", groupId = "billing")
public void handle(
        OrderCreated event,
        Acknowledgment acknowledgment) {

    // Hàm này cần idempotent, ví dụ dùng eventId có unique constraint.
    billingService.applyIfNotProcessed(event.eventId(), event);

    // Chỉ acknowledge sau khi side effect đã hoàn tất.
    acknowledgment.acknowledge();
}
```

Listener trên cần được cấu hình container với acknowledgement mode tương ứng, chẳng hạn `MANUAL`, và consumer không bật auto-commit. Việc acknowledge sau khi ghi database vẫn để lại một cửa sổ lỗi: database có thể đã commit nhưng tiến trình dừng trước khi offset được commit. Unique constraint hoặc bảng inbox theo `eventId` giúp lần giao lại không tạo side effect lần thứ hai.

### Idempotent consumer

Một thao tác idempotent có thể được thực hiện nhiều lần với cùng một đầu vào mà kết quả nghiệp vụ cuối cùng vẫn như một lần thực hiện.

Các cách triển khai thường dùng:

- Mỗi event có `eventId` duy nhất; consumer lưu `eventId` đã xử lý với unique constraint.
- Cập nhật trạng thái theo điều kiện, ví dụ chỉ chuyển đơn hàng từ `PAID` sang `PACKED` nếu trạng thái hiện tại là `PAID`.
- Dùng upsert hoặc khóa nghiệp vụ để một lần giao lại không tạo thêm bản ghi.
- Ghi dấu đã xử lý và cập nhật dữ liệu nghiệp vụ trong cùng transaction của database.

Không nên chỉ kiểm tra event đã tồn tại rồi ghi dữ liệu ở hai transaction riêng biệt: hai consumer hoặc hai lần xử lý đồng thời vẫn có thể vượt qua bước kiểm tra cùng lúc. Ràng buộc duy nhất ở database là hàng rào cuối cùng đáng tin cậy.

## 5. Producer idempotence và exactly-once

Hai tính năng này liên quan đến nhau nhưng giải quyết các vấn đề khác nhau.

### Producer idempotence

Khi producer gửi record nhưng không nhận được acknowledgement do timeout, producer không biết broker đã ghi record hay chưa. Nếu gửi lại một cách thông thường, broker có thể ghi hai bản sao.

Producer idempotence dùng producer ID và sequence number để broker nhận diện retry của cùng một producer session, từ đó tránh ghi trùng do retry ở tầng producer. Trong các phiên bản Kafka hiện đại, producer idempotence được hỗ trợ trực tiếp; vẫn nên cấu hình rõ khi yêu cầu độ tin cậy là quan trọng.

Idempotence của producer **không** tự loại bỏ bản ghi trùng do ứng dụng chủ động gọi `send()` hai lần, do hai producer độc lập gửi cùng một event, hoặc do consumer xử lý lại một record.

### Kafka transaction

Kafka transaction cho phép ghi nhiều record, kể cả trên nhiều partition/topic, theo một đơn vị nguyên tử. Với luồng consume-transform-produce, transaction còn có thể đưa offset của record đầu vào vào cùng transaction với các record đầu ra.

Luồng xử lý thành công có thể được hiểu như sau:

```text
consume input ở offset N
        |
transform
        |
begin transaction
        |
produce output record(s)
        |
đưa offset tiếp theo N+1 vào transaction
        |
commit transaction
        |
output và offset cùng được commit
```

Nếu transaction bị abort, output thuộc transaction đó không được consumer ở chế độ `read_committed` nhìn thấy và offset đầu vào chưa được commit trong transaction. Consumer có thể đọc lại input để thử lại toàn bộ đơn vị công việc.

Để có ngữ nghĩa exactly-once cho pipeline Kafka-to-Kafka, cần phối hợp:

1. Producer được cấu hình transactional và sử dụng transactional ID phù hợp.
2. Offset đầu vào được gửi vào cùng transaction với output.
3. Consumer đọc output sử dụng `isolation.level=read_committed` để bỏ qua record thuộc transaction đã abort hoặc chưa commit.
4. Ứng dụng xử lý lỗi transaction và retry theo cơ chế phù hợp.

### Exactly-once không có nghĩa mọi side effect chỉ chạy một lần

Kafka transaction có thể nguyên tử hóa việc ghi record Kafka và commit offset Kafka. Nó không tự đưa một lệnh SQL, một lần gửi email hay một HTTP request vào cùng transaction phân tán.

Ví dụ, listener gọi dịch vụ thanh toán bên ngoài rồi transaction Kafka bị abort. Khi input được đọc lại, dịch vụ thanh toán có thể nhận cùng yêu cầu lần nữa. Để bảo vệ nghiệp vụ, API bên ngoài cần idempotency key hoặc ứng dụng cần một mẫu tích hợp như inbox/outbox, CDC hay saga.

Vì vậy, khi nói exactly-once, luôn xác định rõ phạm vi: exactly-once ở pipeline Kafka, hay hiệu ứng nghiệp vụ cuối cùng trong toàn hệ thống.

## 6. Áp dụng transaction trong Spring Kafka

Spring Kafka hỗ trợ transaction thông qua transactional producer factory, `KafkaTransactionManager` và listener container. Producer factory cần có transaction ID prefix; mỗi instance ứng dụng chạy đồng thời phải có prefix đủ duy nhất để tránh các producer fencing lẫn nhau.

Ví dụ khởi tạo transaction manager khi producer factory đã được cấu hình transactional:

```java
@Bean
KafkaTransactionManager<String, OrderEvent> kafkaTransactionManager(
        ProducerFactory<String, OrderEvent> producerFactory) {

    return new KafkaTransactionManager<>(producerFactory);
}
```

Với một thao tác chỉ phát nhiều record Kafka, `KafkaTemplate.executeInTransaction(...)` có thể gom các lần gửi vào một transaction:

```java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("order-events", orderId, createdEvent);
    operations.send("audit-events", orderId, auditEvent);
    return null;
});
```

Đối với luồng consume-transform-produce, cần cấu hình listener container tham gia Kafka transaction để offset của record đầu vào được gửi vào transaction cùng các record đầu ra. Chỉ mở transaction quanh lệnh `send()` mà không đưa offset đầu vào vào transaction thì chưa tạo ra exactly-once cho toàn bộ luồng.

Consumer đọc các topic đầu ra transactional cần dùng:

```java
consumerProps.put(
    ConsumerConfig.ISOLATION_LEVEL_CONFIG,
    "read_committed"
);
```

Một số lưu ý khi vận hành transaction:

- Transactional ID prefix phải ổn định trong vòng đời producer nhưng không trùng giữa các instance hoạt động đồng thời.
- Transaction cần kết thúc trong thời gian phù hợp với `transaction.timeout.ms`; xử lý bên ngoài quá lâu có thể khiến transaction timeout.
- Transaction làm tăng chi phí điều phối và có thể ảnh hưởng throughput. Chỉ bật khi cần tính nguyên tử của Kafka output và offset.
- Với database hoặc dịch vụ bên ngoài, vẫn cần idempotency hoặc một mẫu phối hợp riêng.

## 7. Retry, dead-letter và tác động đến bảo đảm

Retry giúp xử lý lỗi tạm thời như timeout hoặc dịch vụ phụ thuộc chưa sẵn sàng. Tuy nhiên, retry làm tăng khả năng một event được thực thi nhiều lần; handler nên idempotent ngay cả khi producer đã bật idempotence.

Dead-letter topic (DLT) giúp đưa record không thể xử lý sau các lần thử vào một nơi riêng để điều tra hoặc xử lý lại. DLT không tự chứng minh record đã được xử lý thành công về mặt nghiệp vụ. Cần theo dõi số lượng record, tuổi record lâu nhất, nguyên nhân lỗi và quy trình replay.

Cách retry cũng ảnh hưởng thứ tự:

- Retry chặn trên cùng luồng xử lý có thể giữ thứ tự của partition nhưng làm các record phía sau phải chờ.
- Retry bất đồng bộ hoặc chuyển record lỗi sang luồng khác có thể cho phép record phía sau hoàn tất trước record lỗi.
- Replay DLT có thể đưa sự kiện cũ vào sau các sự kiện mới; cần kiểm tra version/trạng thái nghiệp vụ trước khi áp dụng.

Nếu thứ tự là yêu cầu nghiệp vụ, hãy thiết kế retry và replay theo cùng đơn vị key/partition, đồng thời xác định cách xử lý sự kiện đến muộn.

## 8. Chọn bảo đảm theo yêu cầu

| Yêu cầu | Hướng thiết kế thường dùng | Điều cần chấp nhận |
|---|---|---|
| Không cần giữ mọi record, ưu tiên độ trễ | Có thể cân nhắc `acks=0` hoặc `acks=1` | Rủi ro mất dữ liệu cao hơn |
| Cần tăng độ bền khi broker lỗi | Replication factor phù hợp, `acks=all`, `min.insync.replicas` | Ghi có thể bị từ chối khi ISR thấp |
| Không muốn mất xử lý consumer | Xử lý xong mới commit offset; idempotent handler | Có thể giao lại và xử lý lặp |
| Cần giữ thứ tự theo thực thể | Dùng business key để phân partition; xử lý tuần tự theo partition | Không có thứ tự toàn cục; tăng partition cần được cân nhắc |
| Consume-transform-produce cần nguyên tử trong Kafka | Kafka transaction, đưa offset vào transaction, consumer `read_committed` | Chỉ bao phủ dữ liệu và offset Kafka |
| Side effect database không được nhân đôi | Inbox/idempotency key và transaction database | Cần thiết kế ở tầng nghiệp vụ |

Không có một cấu hình “exactly once” duy nhất giải quyết đồng thời mọi hàng đợi, database và API. Hãy xác định điều gì được phép mất, điều gì được phép lặp, thứ tự cần giữ ở cấp nào và ranh giới transaction nằm ở đâu.

## 9. Các tình huống lỗi cần dự đoán

| Tình huống | Kết quả có thể xảy ra | Cách giảm rủi ro |
|---|---|---|
| Producer timeout sau khi broker đã ghi record | Retry có thể tạo bản ghi trùng nếu không có idempotence | Bật producer idempotence; xử lý event trùng ở consumer |
| Leader lỗi trước khi follower sao chép record đã được xác nhận bằng `acks=1` | Record có thể mất khi leader mới được chọn | Dùng `acks=all` và `min.insync.replicas` phù hợp |
| Consumer lỗi trước khi xử lý xong và chưa commit | Record được giao lại | Retry có kiểm soát; handler idempotent |
| Consumer đã ghi database nhưng lỗi trước khi commit offset | Record được giao lại, side effect có thể lặp | Inbox/unique constraint và transaction database |
| Consumer commit offset trước khi ghi database | Record có thể bị bỏ qua sau khi tiến trình lỗi | Chỉ commit sau khi xử lý thành công |
| Kafka transaction abort | Output transaction không được consumer `read_committed` nhìn thấy; input có thể được đọc lại | Retry cả đơn vị transaction; side effect ngoài Kafka phải idempotent |
| ISR thấp hơn `min.insync.replicas` | Broker từ chối ghi với `acks=all` | Khôi phục replica, kiểm tra broker/network và theo dõi ISR |

Các tình huống này nên được chuyển thành kịch bản kiểm thử. Ví dụ: làm listener ném exception để xác nhận offset chưa tiến lên; gửi lại cùng `eventId` để xác nhận database không tạo bản ghi nghiệp vụ thứ hai; kiểm tra consumer `read_committed` không nhìn thấy output từ transaction đã abort.

## 10. Kiểm thử và quan sát

Kiểm thử đơn vị có thể xác nhận logic idempotent và cách handler phản ứng với lỗi. Kiểm thử tích hợp với Kafka thật hoặc Testcontainers phù hợp hơn để kiểm tra partition, offset, retry, transaction và hành vi consumer group.

Một số kiểm tra có giá trị:

- Gửi nhiều event cùng key và xác nhận chúng nằm trong cùng partition, có offset tăng dần.
- Gửi event với cùng `eventId` nhiều lần và xác nhận side effect chỉ được ghi nhận một lần.
- Làm handler thất bại trước acknowledgement, sau đó phục hồi và xác nhận record được giao lại.
- Abort một transaction có output rồi xác nhận consumer `read_committed` không đọc được output đó.
- Kiểm tra hành vi khi consumer group rebalance và khi một instance dừng đột ngột.

Trong môi trường chạy thật, nên theo dõi producer send failure/retry, request latency, ISR và under-replicated partitions, consumer lag, số lần rebalance, retry/DLT rate và tuổi của record chưa xử lý. Một consumer lag thấp không chứng minh side effect nghiệp vụ đã hoàn tất; cần quan sát thêm kết quả ở hệ thống đích.

## Checklist thiết kế

Trước khi phát hành một luồng Spring Kafka, hãy trả lời được các câu hỏi sau:

- [ ] Key nào xác định thứ tự nghiệp vụ cần giữ?
- [ ] Topic có replication factor và `min.insync.replicas` phù hợp với yêu cầu độ bền không?
- [ ] Producer có dùng acknowledgement và idempotence phù hợp không?
- [ ] Offset được commit sau thời điểm nào trong vòng đời xử lý?
- [ ] Consumer có chịu được việc cùng event được giao nhiều lần không?
- [ ] Nếu cần exactly-once, offset và output đã nằm trong cùng Kafka transaction chưa?
- [ ] Các side effect ngoài Kafka có idempotency key, inbox/outbox hoặc cơ chế tương đương chưa?
- [ ] Retry, DLT, replay và rebalance có thể làm thay đổi thứ tự ra sao?
- [ ] Các tình huống lỗi quan trọng đã được kiểm thử và có metric/cảnh báo chưa?

## Kết luận

Kafka cung cấp thứ tự trong từng partition, replication để tăng độ bền và cơ chế offset/transaction để kiểm soát việc giao nhận. Ứng dụng Spring Kafka đạt được hành vi tin cậy khi chọn key đúng, cấu hình producer và broker phù hợp, commit offset đúng thời điểm, đồng thời làm cho xử lý nghiệp vụ chịu được retry. Exactly-once có ý nghĩa rõ ràng nhất khi xác định đúng ranh giới Kafka transaction và bổ sung cơ chế idempotency cho mọi side effect nằm ngoài ranh giới đó.

