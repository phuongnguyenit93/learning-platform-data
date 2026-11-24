# isolation.level và đọc dữ liệu đã commit

Kafka producer có thể gửi nhiều record trong một transaction. Consumer cần xác định có được nhìn thấy record thuộc transaction chưa hoàn tất hay chỉ nhìn thấy dữ liệu đã commit. Thuộc tính `isolation.level` của Kafka consumer điều khiển hành vi này.

Hai giá trị quan trọng là `read_uncommitted` và `read_committed`. `read_uncommitted` cho phép consumer đọc record transactional trước khi transaction kết thúc, kể cả record thuộc transaction sau đó bị abort. `read_committed` chỉ trả về record không transactional và record thuộc transaction đã commit; record của transaction đang mở hoặc đã abort không được trả về cho ứng dụng.

Trong Spring Cloud Stream Kafka binder, có thể đặt `isolation.level` cho consumer binding. Nếu dịch vụ chỉ được xử lý các sự kiện đã được producer xác nhận commit, hãy cấu hình `read_committed` và hiểu tác động của Last Stable Offset (LSO), transaction kéo dài, consumer lag và thời gian chờ dữ liệu.

## 1. Transactional record và trạng thái transaction

Kafka hỗ trợ producer transaction để ghi nhiều record một cách nguyên tử trong phạm vi Kafka. Producer bắt đầu transaction, gửi record tới một hoặc nhiều partition, sau đó commit hoặc abort transaction.

Một transaction có thể trải qua các trạng thái khái quát:

1. **Bắt đầu:** producer mở transaction và gửi các record.
2. **Đang diễn ra:** record được ghi vào partition log nhưng transaction chưa có kết quả cuối cùng.
3. **Commit:** transaction coordinator ghi nhận transaction thành công; các record của transaction trở thành dữ liệu đã commit.
4. **Abort:** transaction coordinator ghi nhận transaction thất bại; các record của transaction bị đánh dấu aborted và không được consumer `read_committed` trả về.

Record transactional có thể đã nằm trong log trước khi transaction được commit. Việc record đã được ghi vào log không đồng nghĩa mọi consumer đều được phép nhìn thấy nó. `isolation.level` xác định consumer có đọc qua ranh giới transaction hay không.

Kafka cũng ghi các control marker nội bộ để thể hiện kết quả transaction. Các marker này phục vụ broker và consumer protocol; ứng dụng không nhận chúng như payload nghiệp vụ thông thường.

## 2. Hai giá trị của isolation.level

Kafka consumer hỗ trợ hai giá trị:

| Giá trị | Hành vi | Trường hợp phù hợp |
| --- | --- | --- |
| `read_uncommitted` | Đọc record không transactional và cả record transactional chưa commit hoặc cuối cùng bị abort | Cần đọc tối đa dữ liệu đang có và ứng dụng tự chấp nhận xử lý record có thể bị abort |
| `read_committed` | Chỉ trả về record không transactional và record thuộc transaction đã commit | Cần tránh xử lý dữ liệu từ transaction chưa hoàn tất hoặc đã abort |

Giá trị mặc định của Kafka consumer là `read_uncommitted`. Nếu ứng dụng cần đọc dữ liệu transactional một cách nhất quán, phải cấu hình rõ `read_committed`; không nên giả định consumer tự chuyển sang chế độ này chỉ vì producer có bật transaction.

`isolation.level` là thuộc tính của consumer. Nó không tự bật transaction cho producer, không làm một producer thông thường trở thành transactional và cũng không biến transaction database thành Kafka transaction.

## 3. read_uncommitted: nhìn thấy record trước khi transaction kết thúc

Với `read_uncommitted`, consumer đọc record ngay khi chúng có thể được fetch từ log, không chờ transaction chứa record được commit.

Ví dụ producer gửi hai sự kiện trong cùng transaction:

```text
beginTransaction()
  send(OrderCreated)
  send(InventoryReserved)
commitTransaction()
```

Consumer `read_uncommitted` có thể nhận `OrderCreated` và `InventoryReserved` trước khi producer gọi `commitTransaction()`. Nếu producer sau đó abort, consumer có thể đã xử lý hai record này rồi. Kafka không thể thu hồi side effect mà ứng dụng đã thực hiện.

Điều đó có nghĩa `read_uncommitted` có thể quan sát một trạng thái trung gian của transaction. Nếu producer ghi nhiều record để biểu diễn một thay đổi logic duy nhất, consumer có thể nhìn thấy một phần record trước khi transaction kết thúc.

### Ví dụ transaction bị abort

```text
Producer                         Consumer read_uncommitted
--------                         -------------------------
beginTransaction()
send(OrderCreated)       ----->  nhận OrderCreated
send(InventoryReserved)  ----->  nhận InventoryReserved
abortTransaction()
```

Consumer đã nhận record dù transaction kết thúc bằng abort. Với consumer nghiệp vụ không thể hoàn tác side effect, đây thường không phải hành vi mong muốn.

## 4. read_committed: chỉ đọc dữ liệu đã commit

Với `read_committed`, Kafka consumer chỉ trả về:

- Record không transactional.
- Record thuộc transaction đã commit.

Consumer không trả về record thuộc transaction đang mở và record thuộc transaction đã abort. Nếu producer commit transaction, các record của transaction trở thành có thể đọc được theo thứ tự log. Nếu producer abort, chúng bị ẩn khỏi consumer `read_committed`.

```text
Producer                         Consumer read_committed
--------                         -----------------------
beginTransaction()
send(OrderCreated)       ----->  chưa nhận record
send(InventoryReserved)  ----->  chưa nhận record
commitTransaction()
                               nhận OrderCreated
                               nhận InventoryReserved
```

Nếu transaction abort, hai record trên sẽ không được trả về cho consumer `read_committed`.

`read_committed` giúp consumer tránh thực hiện side effect dựa trên record transactional chưa được commit. Đây là điều kiện quan trọng khi xây dựng pipeline Kafka consume-process-produce có transaction.

## 5. Last Stable Offset (LSO) và ranh giới dữ liệu được phép đọc

Khác biệt cốt lõi giữa hai isolation level nằm ở giới hạn offset mà consumer có thể đọc.

- High Watermark (HW) biểu thị ranh giới dữ liệu đã được replicate đủ theo điều kiện của partition và có thể được đọc theo semantics thông thường.
- Last Stable Offset (LSO) là ranh giới ổn định đối với transaction và được hiểu là mốc loại trừ. Với `read_committed`, consumer chỉ nhận record có offset nhỏ hơn LSO của partition.

LSO được xác định theo transaction chưa hoàn tất sớm nhất trong partition. Nếu transaction đang mở đầu tiên có record tại offset 101, LSO có thể dừng ở 101; consumer `read_committed` đọc các record có offset nhỏ hơn 101. Các record ở offset 101 trở đi có thể đã được ghi và replicate nhưng vẫn chưa được trả về cho consumer.

Ví dụ log của một partition:

```text
Offset:  100   101   102   103   104   105   106
Record:   A    Tx-1  Tx-1    B     C    Tx-2   D
State:  plain  open  open   plain plain  open plain
```

Nếu `Tx-1` chưa kết thúc, LSO dừng trước transaction đó. Consumer `read_committed` có thể đọc record trước ranh giới nhưng phải chờ transaction hoàn tất trước khi tiến tới các record phía sau. Khi `Tx-1` commit hoặc abort, LSO có thể tiến lên, trừ khi còn transaction mở khác tiếp tục chặn.

Đây là lý do một consumer `read_committed` đôi khi có vẻ chậm dù broker đã nhận record mới. Record có thể đã tồn tại trong log nhưng chưa nằm trong vùng ổn định mà consumer được phép đọc.

## 6. Transaction kéo dài có thể làm consumer chờ

Một transaction mở quá lâu có thể chặn LSO và làm tăng độ trễ của consumer `read_committed` trên partition liên quan.

Các nguyên nhân phổ biến:

- Producer bắt đầu transaction rồi chờ một API hoặc database bên ngoài quá lâu trước khi commit.
- Một nhánh xử lý bị treo và không commit/abort transaction.
- Producer bị lỗi trước khi đóng transaction, trong khi broker chưa hoàn tất việc xử lý timeout hoặc fencing.
- Transaction bao trùm quá nhiều công việc hoặc quá nhiều record.

Ví dụ:

```text
Partition 2:
  offset 40: CustomerUpdated (non-transactional)
  offset 41: Tx-77 / OrderCreated (transaction open)
  offset 42: CustomerBalanceChanged (non-transactional)
  offset 43: NotificationRequested (non-transactional)
```

Consumer `read_committed` có thể đọc record ở offset 40 nhưng phải chờ kết quả `Tx-77` trước khi nhận các record sau nó. Các record non-transactional phía sau cũng bị chặn bởi ranh giới LSO, dù bản thân chúng không thuộc transaction.

Vì vậy, transaction nên ngắn và giới hạn trong thao tác Kafka cần tính nguyên tử. Tránh giữ Kafka transaction mở trong lúc gọi hệ thống bên ngoài hoặc chờ người dùng.

## 7. Offset có thể có khoảng trống

Consumer `read_committed` không nhất thiết nhìn thấy các offset liên tiếp. Record thuộc transaction bị abort vẫn chiếm offset trong log nhưng bị ẩn khỏi ứng dụng. Control record cũng chiếm vị trí trong log mà ứng dụng không nhận như payload thông thường.

Ví dụ:

```text
Offset 20: OrderCreated             (committed, visible)
Offset 21: PaymentAttempted         (aborted, hidden)
Offset 22: PaymentReservation       (aborted, hidden)
Offset 23: InventoryReserved        (committed, visible)
```

Consumer `read_committed` có thể nhận offset 20 rồi offset 23. Đây không phải mất message hoặc lỗi phân phối; offset 21 và 22 bị ẩn vì transaction đã abort.

Không viết logic giả định offset kế tiếp luôn bằng offset hiện tại cộng một. Offset là vị trí trong log, không phải số thứ tự liên tục của những record mà một consumer nhìn thấy.

## 8. Cấu hình isolation.level trong Spring Cloud Stream Kafka binder

Với Spring Cloud Stream Kafka binder, có thể đặt Kafka consumer property ở cấp binding. Ví dụ input binding `processOrders-in-0` cần chỉ đọc dữ liệu đã commit:

```yaml
spring:
  cloud:
    function:
      definition: processOrders
    stream:
      bindings:
        processOrders-in-0:
          destination: orders.events
          group: order-service
          content-type: application/json
      kafka:
        bindings:
          processOrders-in-0:
            consumer:
              configuration:
                "isolation.level": read_committed
```

Trong ví dụ, `configuration` truyền thuộc tính Kafka consumer tới consumer do binder tạo. Tên property Kafka là `isolation.level`, dùng dấu chấm. Đặt trong binding-specific consumer configuration giúp giới hạn phạm vi cho input binding này.

Nếu muốn áp dụng cho mọi consumer do Kafka binder quản lý, có thể cấu hình ở phạm vi binder phù hợp với phiên bản đang sử dụng. Tuy nhiên, cấu hình binding cụ thể giúp dễ nhận biết luồng nào yêu cầu đọc committed data.

Không nhầm property này với `spring.kafka.consumer.properties.isolation.level` của Spring Boot Kafka auto-configuration. Khi ứng dụng sử dụng Spring Cloud Stream binder, binder tạo và cấu hình consumer riêng; hãy dùng namespace Kafka binder được tài liệu phiên bản hỗ trợ thay vì giả định cấu hình `KafkaProperties` của một `KafkaListenerContainerFactory` khác sẽ tự áp dụng.

## 9. Cấu hình producer transaction không thay thế isolation.level

Producer transaction và consumer isolation là hai phần cấu hình khác nhau:

| Thành phần | Trách nhiệm | Ví dụ cấu hình/khái niệm |
| --- | --- | --- |
| Producer transaction | Ghi một nhóm record rồi commit hoặc abort cùng nhau | Transactional producer, `transactional.id`, transaction manager hoặc transaction support của Kafka binder |
| Consumer isolation | Quyết định consumer có đọc record transactional chưa commit/đã abort hay không | `isolation.level=read_committed` |
| Consumer group offset | Lưu vị trí đọc của group | Offset commit, hoặc gửi offset vào cùng Kafka transaction trong consume-process-produce |

Chỉ bật producer transaction không làm mọi consumer tự động dùng `read_committed`. Một consumer giữ mặc định `read_uncommitted` vẫn có thể đọc record trước khi transaction kết thúc. Ngược lại, đặt `read_committed` trên consumer không tự tạo transaction cho producer; nó chỉ lọc dữ liệu theo trạng thái transaction mà broker ghi nhận.

Trong pipeline có producer transactional và consumer downstream cần chỉ xử lý kết quả đã commit, hãy cấu hình consumer isolation rõ ràng. Nếu pipeline còn cần bảo đảm offset input và record output được commit nguyên tử, phải dùng cơ chế consume-transform-produce transaction phù hợp của Kafka/Spring Kafka hoặc binder; `read_committed` một mình không bảo đảm điều đó.

## 10. Ví dụ producer commit và abort

Một producer Kafka được cấu hình transactional có thể gửi nhiều record trong cùng transaction. Ví dụ dưới đây minh họa API `KafkaTemplate` của Spring Kafka; cần một `ProducerFactory` hỗ trợ transaction và cấu hình transactional ID prefix trong ứng dụng:

```java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventProducer {

    private final KafkaTemplate<String, Object> kafkaTemplate;

    public OrderEventProducer(KafkaTemplate<String, Object> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishOrder(OrderCreated order, InventoryReserved inventory) {
        kafkaTemplate.executeInTransaction(operations -> {
            operations.send("orders.created", order.orderId(), order);
            operations.send("inventory.reserved", order.orderId(), inventory);
            return null;
        });
    }
}
```

Khi callback hoàn tất bình thường, transaction được commit. Nếu callback ném exception, transaction bị abort theo semantics của `executeInTransaction`. Đoạn mã chỉ minh họa transaction trong Kafka; nó không bao trùm một transaction JPA ở relational database.

Consumer downstream cần `read_committed` để không xử lý `OrderCreated` hoặc `InventoryReserved` khi transaction chưa commit hoặc đã abort.

## 11. Ví dụ kiểm chứng hai isolation level

Có thể kiểm chứng hành vi bằng integration test với Kafka thật hoặc Testcontainers:

1. Tạo một topic thử nghiệm.
2. Tạo transactional producer.
3. Mở transaction và gửi một record.
4. Trước khi commit, dùng consumer `read_uncommitted` để kiểm tra record có thể được đọc.
5. Dùng consumer `read_committed` để xác nhận record chưa được trả về.
6. Commit transaction và xác nhận consumer `read_committed` nhận record.
7. Lặp lại với transaction bị abort; consumer `read_committed` không nhận record đã abort.

Với test abort, `read_uncommitted` có thể đã đọc record trước khi abort. Nếu test chỉ bắt đầu consumer sau khi abort hoàn tất, record vẫn có thể được đọc theo isolation `read_uncommitted`, vì log giữ record aborted và consumer không lọc chúng.

Pseudo-code kiểm tra consumer config:

```java
Map<String, Object> consumerProps = new HashMap<>();
consumerProps.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
consumerProps.put(ConsumerConfig.GROUP_ID_CONFIG, "isolation-test");
consumerProps.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class);
consumerProps.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class);
consumerProps.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
```

Đây là cấu hình Kafka client trực tiếp để minh họa thuộc tính. Khi kiểm thử Spring Cloud Stream binder, hãy đặt cùng property trong binding-specific `consumer.configuration` như ví dụ trước và khởi chạy đúng binder.

## 12. Tác động đến consumer lag và quan sát hệ thống

Consumer `read_committed` có thể có độ trễ nhìn thấy cao hơn consumer `read_uncommitted` vì nó phải chờ transaction hoàn tất. Khi đo lag, cần phân biệt:

- Vị trí consumer đã xử lý/commit.
- High Watermark của partition.
- Last Stable Offset mà consumer `read_committed` có thể đọc.

Một số dashboard tính lag dựa trên high watermark hoặc end offset, trong khi consumer `read_committed` chỉ đọc tới LSO. Vì vậy, lag hiển thị có thể bao gồm cả record đang bị chặn bởi transaction mở. Cần hiểu cách exporter và công cụ monitoring tính lag trước khi kết luận consumer xử lý chậm.

Các chỉ số nên quan sát:

- Consumer lag theo group và partition.
- LSO so với high watermark, nếu công cụ broker/exporter cung cấp.
- Thời lượng transaction producer.
- Số transaction đang mở hoặc bị abort.
- Thời gian từ lúc producer gửi record đến lúc consumer `read_committed` nhận được.
- Số lần producer timeout, fencing hoặc transaction abort.
- Rebalance và processing latency ở consumer.

Nếu consumer lag tăng nhưng CPU và thời gian xử lý thấp, hãy kiểm tra transaction kéo dài hoặc transaction coordinator trước khi tăng consumer concurrency.

## 13. Isolation level không phải cơ chế bảo đảm exactly-once toàn hệ thống

`read_committed` giúp consumer không nhìn thấy record thuộc transaction Kafka chưa commit hoặc đã abort. Nó không bảo đảm:

- Database và Kafka cùng commit hoặc rollback nguyên tử.
- Consumer chỉ xử lý một lần nếu crash sau side effect nhưng trước khi commit offset.
- API HTTP hoặc hệ thống bên ngoài được gọi đúng một lần.
- Hai topic hoặc hai broker độc lập có chung một transaction nếu không có cơ chế phối hợp tương ứng.

Để xây dựng pipeline đáng tin cậy, cần kết hợp transaction Kafka với idempotent consumer, event ID, retry/DLQ, outbox hoặc cơ chế lưu trạng thái phù hợp. Nếu consumer ghi database, hãy cân nhắc inbox/deduplication hoặc transactional outbox cho chiều phát tiếp theo.

## 14. Khi nào nên dùng read_committed?

Nên chọn `read_committed` khi:

- Producer upstream dùng Kafka transaction để phát một nhóm record nguyên tử.
- Consumer không được phép thực hiện side effect dựa trên record có thể bị abort.
- Pipeline consume-process-produce cần đọc đầu vào transactional đã commit.
- Kết quả báo cáo hoặc xử lý downstream phải phản ánh trạng thái transaction cuối cùng.

`read_uncommitted` có thể phù hợp khi:

- Topic không dùng transaction và yêu cầu latency/throughput ưu tiên hơn việc lọc transaction state.
- Consumer chỉ dùng dữ liệu tạm thời hoặc có khả năng xử lý bù khi transaction upstream abort.
- Ứng dụng cần quan sát dữ liệu trong log theo semantics không chờ transaction commit.

Với dữ liệu nghiệp vụ quan trọng, `read_committed` thường là lựa chọn an toàn hơn khi upstream sử dụng transaction. Tuy nhiên, cần đánh giá độ trễ do transaction mở và không bật theo phong trào nếu producer không dùng transaction và ứng dụng không có yêu cầu tương ứng.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Consumer thấy record trước khi producer commit | Consumer đang dùng `read_uncommitted` | Đặt `isolation.level=read_committed` cho đúng input binding. |
| Consumer không thấy record dù broker đã ghi | Transaction chưa commit hoặc LSO chưa vượt qua offset | Kiểm tra trạng thái transaction, producer timeout và LSO. |
| Consumer không thấy record của transaction bị abort | Đây là hành vi đúng của `read_committed` | Nếu cần điều tra, dùng log/metrics producer hoặc consumer thử nghiệm `read_uncommitted`, không đưa dữ liệu abort vào nghiệp vụ. |
| Offset consumer có khoảng trống | Record aborted/control marker bị ẩn khỏi ứng dụng | Không giả định offset liên tiếp; dùng event ID và offset như vị trí log. |
| Lag tăng dù consumer xử lý nhanh | LSO bị chặn bởi transaction mở hoặc metric tính tới HW | Kiểm tra transaction duration và cách exporter tính lag. |
| Producer transaction bật nhưng consumer vẫn thấy dữ liệu chưa commit | Consumer giữ mặc định `read_uncommitted` | Cấu hình consumer isolation riêng; producer transaction không tự đổi consumer. |
| Cấu hình `spring.kafka.consumer.properties.isolation.level` không có tác dụng | Binder tạo consumer riêng, không dùng auto-config consumer dự kiến | Dùng namespace Kafka binder `bindings.<binding>.consumer.configuration`. |
| Tăng concurrency không giảm lag | Partition đang bị LSO chặn hoặc downstream không phải bottleneck | Kiểm tra transaction state, partition assignment và nguồn lag trước khi scale. |

## 16. Checklist triển khai

Trước khi đưa consumer đọc transactional data vào production:

1. Xác định producer upstream có dùng Kafka transaction hay không.
2. Xác định consumer có cần loại bỏ record chưa commit/đã abort không.
3. Cấu hình `isolation.level=read_committed` cho đúng binding.
4. Xác minh property thực sự được truyền tới Kafka consumer của binder.
5. Kiểm thử cả transaction commit và abort.
6. Kiểm tra consumer không giả định offset liên tiếp.
7. Theo dõi LSO, high watermark, transaction duration và consumer lag.
8. Đặt timeout và giới hạn thời lượng transaction hợp lý ở producer.
9. Thiết kế idempotency cho side effect của consumer.
10. Kiểm thử crash, rebalance và retry trong pipeline consume-process-produce.

## Tài liệu tham khảo

- [Apache Kafka — Consumer Configs: `isolation.level`](https://kafka.apache.org/documentation/#consumerconfigs_isolation.level)
- [Apache Kafka — Design: Message Delivery Semantics and Transactions](https://kafka.apache.org/documentation/#semantics)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)

Hãy đối chiếu tài liệu của phiên bản Kafka broker, Kafka client và Spring Cloud Stream Kafka binder đang sử dụng. Tên property binder, cấu hình transaction và metric LSO có thể khác nhau theo phiên bản và công cụ vận hành.

## Kết luận

`isolation.level` quyết định Kafka consumer có nhìn thấy record transactional chưa commit hoặc đã abort hay không. `read_uncommitted` có thể trả về cả những record cuối cùng bị abort; `read_committed` chỉ trả về record không transactional và record thuộc transaction đã commit. Consumer `read_committed` đọc tới Last Stable Offset, vì vậy transaction mở lâu có thể chặn cả những record phía sau và làm tăng độ trễ quan sát. Trong Spring Cloud Stream Kafka binder, hãy cấu hình thuộc tính này ở consumer binding, kiểm thử cả commit/abort và kết hợp với idempotency cùng chiến lược retry để xây dựng pipeline đáng tin cậy.
