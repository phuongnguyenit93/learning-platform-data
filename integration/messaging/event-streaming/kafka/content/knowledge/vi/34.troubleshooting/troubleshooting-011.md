# Giao dịch treo, fencing và consumer read_committed bị chặn

Kafka transaction giúp ghi nhiều record và offset consumer theo một đơn vị nguyên tử. Tuy nhiên, transaction phải được kết thúc bằng commit hoặc abort. Nếu producer giữ transaction quá lâu, broker có thể hết hạn và abort transaction; producer cũ có thể bị fencing khi một producer khác khởi tạo cùng `transactional.id`; consumer dùng `read_committed` có thể tạm thời không đọc được các record nằm sau transaction chưa kết thúc trên cùng partition.

Ba hiện tượng này thường xuất hiện cùng nhau nhưng cần chẩn đoán theo đúng lớp. Transaction treo liên quan đến vòng đời producer và transaction coordinator. Fencing liên quan đến epoch và quyền sở hữu `transactional.id`. Consumer bị chặn liên quan đến last stable offset (LSO) của partition. Tăng timeout consumer hoặc chuyển sang `read_uncommitted` không giải quyết được nguyên nhân transaction chưa kết thúc.

## 1. Hiểu transaction và LSO

### 1.1. Vòng đời transaction

Producer giao dịch dùng `transactional.id` ổn định để broker nhận diện một logical producer qua các lần khởi động. Producer gọi `initTransactions()`, bắt đầu transaction, ghi một hoặc nhiều record, rồi kết thúc bằng `commitTransaction()` hoặc `abortTransaction()`.

```java
producer.initTransactions();

try {
    producer.beginTransaction();
    producer.send(new ProducerRecord<>("orders", "order-42", "created"));
    producer.send(new ProducerRecord<>("order-audit", "order-42", "created"));
    producer.commitTransaction();
} catch (Exception ex) {
    // Xử lý theo loại exception và trạng thái producer.
    throw ex;
}
```

Đây là phác thảo luồng; phần xử lý lỗi phải phân biệt exception có thể phục hồi với lỗi fatal như fencing. Với transaction, không để nhánh code thoát khỏi xử lý mà producer vẫn giữ transaction mở. Mọi đường đi phải có kết quả rõ ràng: commit, abort hoặc đóng producer để coordinator xử lý việc thu hồi transaction theo timeout.

Broker có transaction coordinator quản lý trạng thái transaction và producer epoch. Trạng thái giao dịch được lưu trong internal topic `__transaction_state`. Coordinator ghi nhận các partition tham gia transaction, sau đó phát transaction marker commit hoặc abort để consumer phân biệt record đã commit với record đã hủy.

### 1.2. Vì sao read_committed có thể không trả record mới

Mỗi partition có high watermark (HW), thể hiện ranh giới dữ liệu đã được replicate đủ theo điều kiện của partition. Consumer `read_committed` còn bị giới hạn bởi last stable offset (LSO). LSO là ranh giới an toàn để trả record đã biết kết quả transaction; transaction đang mở đầu tiên trên partition có thể giữ LSO ở phía trước các record mới hơn.

Ví dụ partition có thứ tự offset như sau:

```text
Offset:   100       101        102        103        104
          |         |          |          |          |
          A         B          C          D          E
                    \__________/
                     transaction T1

T1 đang mở; record 102 chưa có commit/abort marker.
LSO có thể dừng ở 101 dù HW đã tiến đến 105.
```

Trong ví dụ, consumer `read_committed` có thể đọc các record trước LSO nhưng chưa được trả record nằm sau transaction chưa kết thúc. Khi T1 commit hoặc abort và marker được ghi nhận, LSO có thể tiến lên, cho phép consumer đọc tiếp. Việc chờ này mang tính partition: một partition có transaction mở có thể bị chặn trong khi các partition khác của cùng topic vẫn tiến triển.

`read_uncommitted` có thể đọc record chưa commit hoặc đã abort, vì vậy hữu ích trong một số bước chẩn đoán. Nó không phải cách sửa hệ thống production nếu hợp đồng nghiệp vụ yêu cầu chỉ xử lý dữ liệu đã commit. Đọc một record chưa commit có thể khiến ứng dụng tạo side effect cho dữ liệu cuối cùng bị abort.

## 2. Nhận diện transaction treo

Transaction có thể bị giữ mở bởi nhiều nguyên nhân:

- Ứng dụng gọi `beginTransaction()` nhưng có nhánh code không gọi commit hoặc abort.
- Xử lý nghiệp vụ, gọi database hoặc HTTP nằm bên trong transaction và bị chậm/treo.
- Retry hoặc backoff diễn ra trong transaction, khiến thời gian mở vượt `transaction.timeout.ms`.
- Producer bị crash, mất kết nối hoặc dừng trước khi kết thúc transaction.
- Transaction coordinator hoặc leader của partition trong `__transaction_state` không sẵn sàng.
- Broker không đủ replica/ISR cho internal transaction state topic hoặc transaction marker.
- Một producer cũ còn hoạt động sau failover/restart và tiếp tục gửi lệnh với epoch đã lỗi thời.

### 2.1. Đo thời gian mở transaction

Ghi nhận ít nhất các mốc sau cho mỗi transaction:

| Mốc | Thông tin cần ghi |
|---|---|
| Bắt đầu | `transactional.id`, producer instance, thời điểm `beginTransaction()` |
| Ghi record | Topic/partition, số record, thời gian send và kết quả callback |
| Kết thúc | Thời điểm commit/abort bắt đầu và kết quả cuối cùng |
| Lỗi | Exception class, message, producer epoch nếu có, coordinator/broker liên quan |
| Tác động | Partition bị ảnh hưởng, consumer lag và thời gian LSO không tiến |

Không ghi payload nhạy cảm vào log chỉ để chẩn đoán transaction. Dùng correlation ID hoặc transaction business ID để nối log producer, coordinator và consumer.

So sánh thời gian mở transaction với `transaction.timeout.ms` của producer. Giá trị này phải nằm trong giới hạn `transaction.max.timeout.ms` của broker. Khi producer vượt transaction timeout, coordinator có thể abort transaction; transaction marker và replication vẫn cần thời gian để hoàn tất, vì vậy LSO không nhất thiết tiến ngay tại đúng thời điểm timeout.

### 2.2. Kiểm tra transaction coordinator và internal topic

Nếu nhiều `transactional.id` cùng lỗi hoặc transaction không thể commit/abort, kiểm tra broker đang làm coordinator và trạng thái internal topic `__transaction_state`:

- Partition của `__transaction_state` có leader hay không.
- ISR có đáp ứng `transaction.state.log.min.isr` không.
- Broker có đủ replica theo `transaction.state.log.replication.factor` không.
- Log broker có lỗi coordinator load, state log, timeout, leader election hoặc transaction marker không.
- Cluster có đang under-replicated hoặc mất broker đồng thời không.

Trong cluster nhỏ dùng cho local development, các giá trị replication mặc định dành cho cluster nhiều broker có thể không phù hợp. Điều chỉnh replication factor/min ISR cho môi trường thử nghiệm phải được thực hiện có chủ đích; không hạ yêu cầu durability của production chỉ để làm transaction hoạt động trở lại.

Transaction coordinator là một broker được chọn cho partition tương ứng của `__transaction_state`. Vì vậy, không chỉ kiểm tra broker nhận request từ producer; hãy kiểm tra broker đang giữ leader của partition state liên quan và tình trạng metadata/leader election toàn cluster.

## 3. Fencing và producer epoch

### 3.1. Fencing bảo vệ khỏi zombie producer

Kafka tăng producer epoch khi một producer mới khởi tạo cùng `transactional.id`. Producer cũ dùng epoch thấp hơn bị fencing. Cơ chế này ngăn một instance cũ tiếp tục ghi dữ liệu sau khi ứng dụng đã chuyển quyền sở hữu logical producer sang instance mới.

Fencing thường xảy ra khi:

- Hai instance chạy đồng thời với cùng `transactional.id`.
- Nhiều pod dùng chung một `transactional.id` tĩnh.
- Một lần deploy tạo producer mới trong khi producer cũ chưa dừng.
- Producer cũ bị treo hoặc network partition, rồi tiếp tục hoạt động sau khi instance thay thế đã khởi tạo.
- Ứng dụng tái sử dụng transactional ID giữa các logical producer độc lập.

`ProducerFencedException` là lỗi fatal đối với producer bị fencing. Producer đó không thể tiếp tục transaction bằng cách retry cùng lệnh. Hãy dừng/đóng producer cũ, xử lý vòng đời instance và để producer mới sở hữu transactional ID theo đúng thiết kế. Không bắt exception rồi bỏ qua để tiếp tục gửi.

### 3.2. Quy tắc đặt transactional.id

`transactional.id` cần ổn định qua lần restart của cùng một logical producer để Kafka có thể nhận diện và fencing phiên cũ. Đồng thời, nó phải duy nhất giữa các logical producer đang hoạt động.

| Thiết kế | Đánh giá |
|---|---|
| Mỗi pod có ID riêng, ổn định qua restart của chính pod đó | Phù hợp khi định danh instance được quản lý bền vững |
| Mọi pod cùng dùng `orders-producer` | Sai khi chạy đồng thời; các pod fencing lẫn nhau |
| Mỗi lần khởi động tạo ID ngẫu nhiên hoàn toàn mới | Tránh trùng đồng thời nhưng mất khả năng fencing/recovery theo logical producer cũ và có thể để lại transaction cần chờ timeout |
| Một ID cho từng shard/worker độc lập, được phân công độc quyền | Phù hợp nếu hệ thống bảo đảm một owner hoạt động tại một thời điểm |

Trong môi trường orchestrator, cần quyết định identity dựa trên mô hình chạy: StatefulSet ordinal, shard assignment hoặc một cơ chế cấp quyền sở hữu có kiểm soát. Không chỉ ghép hostname ngẫu nhiên nếu mục tiêu là nhận diện cùng logical producer qua restart.

### 3.3. Spring Kafka transaction ID prefix

Spring Kafka dùng `transactionIdPrefix` để tạo transactional ID cho các producer được cache bởi producer factory. Prefix phải duy nhất giữa các application instance. Ví dụ:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${INSTANCE_ID}-orders-tx-
```

`INSTANCE_ID` phải được cấp riêng cho từng instance đang chạy và ổn định theo chính sách restart mà hệ thống mong muốn. Không để tất cả replica nhận cùng một giá trị mặc định như `local` trong production. Nếu nhiều producer transaction được tạo đồng thời trong một instance, Spring Kafka quản lý suffix để tạo ID riêng trong phạm vi prefix.

Khi dùng transaction trong Spring Kafka, có thể khai báo `KafkaTransactionManager` và dùng `KafkaTemplate`/listener container theo cơ chế transaction của framework. Không tự tạo một producer ngoài producer factory rồi dùng chung transactional ID với container.

## 4. Xử lý lỗi producer đúng cách

### 4.1. Phân biệt lỗi fatal và lỗi có thể abort

Không phải exception nào trong transaction cũng có cách phục hồi giống nhau.

| Loại lỗi | Hành động |
|---|---|
| `ProducerFencedException` hoặc lỗi epoch fatal | Producer đã mất quyền sở hữu; đóng producer và khởi tạo instance hợp lệ mới |
| Lỗi serialization hoặc validation trước khi gửi | Sửa dữ liệu/contract; quyết định abort transaction hiện tại |
| Lỗi tạm thời khi gửi hoặc broker timeout | Đánh giá trạng thái producer và transaction; chỉ retry theo API/state hợp lệ |
| `commitTransaction()` timeout | Không giả định transaction đã commit; theo hướng dẫn API của client, abort nếu producer còn ở trạng thái cho phép và xử lý kết quả không chắc chắn bằng idempotency |
| Coordinator unavailable | Kiểm tra coordinator/state topic; retry có giới hạn theo cơ chế client, theo dõi transaction timeout |

Kafka producer có thể chuyển sang trạng thái fatal sau một số lỗi. Khi gặp lỗi fatal, gọi `close()` và tạo producer mới với identity hợp lệ; không gọi `beginTransaction()` lần nữa trên producer đã lỗi.

### 4.2. Ví dụ xử lý transaction với KafkaProducer

Đoạn code dưới đây minh họa cấu trúc xử lý. Trong ứng dụng thực tế, cần phân loại exception theo Kafka client version và bảo đảm `close()` chạy khi producer không còn sử dụng được:

```java
KafkaProducer<String, String> producer = createTransactionalProducer();
producer.initTransactions();

try {
    producer.beginTransaction();
    producer.send(new ProducerRecord<>("orders", "order-42", "created"));
    producer.commitTransaction();
} catch (ProducerFencedException | InvalidProducerEpochException fatal) {
    // Producer này không còn quyền sở hữu transactional.id.
    producer.close();
    throw fatal;
} catch (KafkaException recoverableOrFatal) {
    try {
        producer.abortTransaction();
    } catch (ProducerFencedException | InvalidProducerEpochException fenced) {
        producer.close();
        throw fenced;
    }
    throw recoverableOrFatal;
}
```

Đây là khung để thảo luận, không phải một policy tổng quát cho mọi exception. `KafkaException` có thể đại diện lỗi fatal hoặc lỗi không thể abort; trước khi gọi `abortTransaction()`, phải xác định producer còn hợp lệ và đang ở trạng thái cho phép abort. Một số exception như fencing/epoch invalid là fatal và không được đi qua nhánh abort thông thường. Nếu `commitTransaction()` timeout, kết quả cần được xử lý theo hợp đồng của Kafka client; ứng dụng không được phát lại side effect bên ngoài một cách mù quáng.

Trong production, nên đóng producer trong `finally`/resource lifecycle phù hợp và không giữ producer sau khi đã fencing. Tránh khởi tạo producer mới ngay lập tức bằng cùng transactional ID từ nhiều thread hoặc nhiều instance chưa có cơ chế single owner.

## 5. Cấu hình transaction timeout hợp lý

Producer dùng `transaction.timeout.ms` để giới hạn thời gian coordinator chờ transaction kết thúc. Broker giới hạn giá trị tối đa bằng `transaction.max.timeout.ms`. Chọn timeout dựa trên thời gian xử lý transaction p99, thời gian retry cần thiết và yêu cầu phục hồi; không tăng vô hạn để che lỗi code path bị treo.

```java
props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG, transactionalId);
props.put(ProducerConfig.TRANSACTION_TIMEOUT_CONFIG, 120_000);
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
props.put(ProducerConfig.ACKS_CONFIG, "all");
```

Ví dụ 120 giây chỉ là giá trị minh họa. Broker phải cho phép timeout này; nếu vượt `transaction.max.timeout.ms`, broker từ chối cấu hình hoặc khởi tạo transaction. Trong Spring Boot, các thuộc tính producer có thể truyền qua `spring.kafka.producer.properties` theo phiên bản Spring Boot đang sử dụng.

Các nguyên tắc:

- Giữ transaction ngắn; không gọi dịch vụ ngoài chậm nếu không cần thiết trong transaction.
- Đặt timeout cho từng dependency và tổng thời gian xử lý.
- Không retry nhiều phút bên trong một transaction đang mở.
- Chọn `transaction.timeout.ms` đủ cho trường hợp hợp lệ nhưng vẫn cho phép broker thu hồi transaction bị treo trong thời gian chấp nhận được.
- Theo dõi transaction timeout và số transaction đang mở sau mỗi lần deploy.

Nếu cần xử lý lâu, chia công việc thành nhiều transaction nhỏ với checkpoint/idempotency hoặc dùng workflow/outbox phù hợp. Một transaction Kafka dài không phải cơ chế khóa công việc dài hạn.

## 6. Chẩn đoán consumer read_committed bị chặn

### 6.1. Phân biệt partition bị chặn với consumer không poll

Khi consumer `read_committed` liên tục poll nhưng không nhận record mới, hãy kiểm tra:

1. Consumer đã được assign partition và không bị rebalance liên tục chưa.
2. Log end offset/HW có tăng trong khi committed offset và records consumed đứng yên không.
3. Có producer transaction đang mở trên partition đó không.
4. LSO có bị giữ ở offset của transaction chưa kết thúc không.
5. Coordinator có hoàn tất commit/abort marker và replication của marker không.

Consumer `read_committed` có thể trả về batch rỗng dù phía sau vẫn có record đã được producer gửi. Điều đó không nhất thiết có nghĩa topic hết dữ liệu. Nếu một partition bị chặn bởi LSO, các partition khác vẫn có thể đọc bình thường.

### 6.2. So sánh isolation level có kiểm soát

Trong môi trường chẩn đoán riêng, có thể chạy hai consumer group độc lập:

```java
readCommittedProps.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
readUncommittedProps.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_uncommitted");
```

Nếu consumer `read_uncommitted` thấy record mới nhưng `read_committed` không thấy, đây là dấu hiệu cần kiểm tra transaction đang mở/LSO. Tuy nhiên, phép so sánh này không chứng minh transaction nào đang treo; cần đối chiếu producer `transactional.id`, coordinator log và trạng thái partition. Consumer `read_uncommitted` chỉ dùng để chẩn đoán, không dùng làm workaround cho luồng nghiệp vụ yêu cầu dữ liệu committed.

Hai consumer cần group ID riêng để offset của chúng độc lập. Cả hai phải subscribe/assign đúng partition, chờ assignment hoàn tất và poll có timeout. Đảm bảo không có record cũ hoặc transaction khác làm sai kết luận.

### 6.3. Đọc log broker và metric

Tìm log theo `transactional.id`, producer ID, coordinator broker và partition của `__transaction_state`. Các sự kiện hữu ích gồm:

- Transaction bắt đầu, commit hoặc abort.
- Transaction timeout và coordinator chủ động abort.
- Producer epoch tăng hoặc producer bị fenced.
- Coordinator load/reload transaction state.
- Lỗi ghi transaction state hoặc transaction marker.
- Partition state topic mất leader, ISR thấp hoặc request timeout.

Tên metric và MBean thay đổi theo Kafka version và hệ thống giám sát. Theo dõi các nhóm metric transaction coordinator, số transactional ID đang hoạt động, transaction start/end/timeout, request latency, request error, under-replicated partitions và ISR. Kiểm tra metric catalog/JMX của phiên bản đang chạy thay vì giả định tên metric giống nhau ở mọi bản.

Để khoanh vùng, nối ba nguồn dữ liệu theo thời gian:

| Nguồn | Câu hỏi |
|---|---|
| Producer application log | Transaction nào bắt đầu nhưng chưa kết thúc? Instance nào đang sở hữu ID? |
| Broker/coordinator log | Coordinator đã nhận begin/commit/abort chưa? Có timeout, fencing hay state log error không? |
| Consumer log/metric | Partition nào không tiến? Consumer có poll đều và vẫn giữ assignment không? |

## 7. Khôi phục transaction treo và fencing an toàn

Thực hiện theo trình tự sau:

1. **Xác định phạm vi:** lấy topic/partition bị chặn, `transactional.id`, producer instance, consumer group và thời điểm LSO ngừng tiến.
2. **Xác định owner:** tìm tất cả instance có thể dùng transactional ID đó. Xác nhận có nhiều owner đồng thời hay instance cũ còn chạy.
3. **Kiểm tra coordinator:** xác định broker coordinator và trạng thái partition tương ứng của `__transaction_state`; xử lý lỗi broker/ISR trước khi thao tác producer.
4. **Dừng zombie producer:** nếu một instance đã bị thay thế, dừng instance cũ để tránh nó tiếp tục gửi và tạo thêm fencing.
5. **Khởi tạo owner hợp lệ:** producer mới gọi `initTransactions()` với transactional ID đúng logical owner; thao tác này fencing producer cũ và cho phép coordinator xử lý transaction trước đó.
6. **Chờ kết thúc transaction:** xác nhận commit/abort marker được ghi và LSO tiến qua vùng bị chặn.
7. **Kiểm tra consumer:** xác nhận `read_committed` đọc tiếp được, offset và lag tiến triển bình thường.
8. **Đối soát nghiệp vụ:** kiểm tra event ID/side effect để phát hiện xử lý lặp hoặc trạng thái ngoài Kafka không đồng nhất.

Không xóa thủ công `__transaction_state`, không chỉnh sửa log segment để bỏ transaction marker và không thay isolation level production để che tình trạng treo. Các thao tác đó có thể làm hỏng trạng thái transaction hoặc khiến ứng dụng đọc dữ liệu chưa commit.

Nếu coordinator không sẵn sàng, khôi phục leader/ISR của internal state topic trước. Nếu chỉ một producer bị treo, khôi phục owner và fencing đúng transactional ID. Không restart toàn bộ cluster theo phản xạ khi chưa biết broker/coordinator nào bị ảnh hưởng.

## 8. Spring Kafka: quản lý transaction lifecycle

### 8.1. Cấu hình transaction manager

Spring Kafka có thể cấu hình producer transaction thông qua `transaction-id-prefix`. Khi dùng listener container, container có thể quản lý transaction cho quá trình consume-process-produce. Ví dụ cấu hình prefix:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${INSTANCE_ID}-orders-tx-
    consumer:
      properties:
        isolation.level: read_committed
```

Prefix phải riêng cho từng application instance. Consumer `read_committed` chỉ phù hợp khi luồng cần chỉ nhìn thấy transaction đã commit; nếu một transaction mở quá lâu trên partition, độ trễ nhìn thấy record sẽ tăng theo LSO.

### 8.2. Dùng KafkaTemplate trong transaction

```java
@Service
public class OrderPublisher {
    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate.executeInTransaction(operations -> {
            operations.send("orders", event.orderId(), toJson(event));
            operations.send("order-audit", event.orderId(), toAuditJson(event));
            return null;
        });
    }
}
```

`executeInTransaction` tạo transaction cho các thao tác Kafka trong callback và commit khi callback hoàn tất; exception làm transaction bị abort theo cơ chế framework. Giữ callback ngắn và không thực hiện lời gọi network/database kéo dài bên trong nếu không cần thiết.

Nếu ứng dụng cần phối hợp database và Kafka, `@Transactional` với hai transaction manager không tự tạo một distributed atomic transaction. Chọn outbox/inbox hoặc một mô hình phối hợp có thể phục hồi. Kafka transaction bảo đảm tính nguyên tử giữa các thao tác Kafka được enlist trong transaction đó, bao gồm offset khi dùng consume-transform-produce theo cấu hình hỗ trợ.

## 9. Ma trận triệu chứng và hướng xử lý

| Triệu chứng | Nguyên nhân có khả năng | Hành động ưu tiên |
|---|---|---|
| `read_committed` không thấy record mới nhưng `read_uncommitted` thấy | LSO bị giữ bởi transaction mở/chưa có marker | Tìm `transactional.id`, coordinator và transaction chưa kết thúc |
| `ProducerFencedException` khi gửi hoặc commit | Có producer khác đã claim cùng transactional ID | Dừng zombie, bảo đảm một owner cho mỗi ID, tạo producer mới hợp lệ |
| `initTransactions()` chờ lâu | Coordinator phải recover transaction cũ hoặc state topic/coordinator không sẵn sàng | Kiểm tra coordinator, `__transaction_state`, ISR và broker log |
| Transaction bị abort sau thời gian xử lý dài | Vượt `transaction.timeout.ms` hoặc coordinator abort | Rút ngắn transaction, chuyển retry ra ngoài, cấu hình timeout có căn cứ |
| Nhiều transactional ID cùng timeout | Coordinator/broker hoặc internal state topic có vấn đề | Kiểm tra leader, ISR, replication và coordinator metrics |
| Một partition đứng nhưng partition khác vẫn đọc | Transaction mở giữ LSO ở partition cụ thể | Xác định producer đã ghi vào partition đó và hoàn tất transaction |
| Consumer đọc được dữ liệu nhưng nghiệp vụ sai sau khi đổi sang read_uncommitted | Ứng dụng xử lý record chưa commit/đã abort | Khôi phục read_committed và xử lý transaction producer gốc |

## 10. Tiêu chí xác nhận đã khắc phục

- [ ] Mỗi logical producer có `transactional.id` riêng và không có hai owner hoạt động đồng thời.
- [ ] Mọi transaction được commit hoặc abort trong thời gian nằm trong timeout đã chọn.
- [ ] Không còn producer cũ tiếp tục gửi sau khi instance mới đã nhận quyền sở hữu.
- [ ] Transaction coordinator và partition của `__transaction_state` ổn định, ISR đáp ứng yêu cầu.
- [ ] LSO tiến qua offset bị chặn sau khi transaction kết thúc.
- [ ] Consumer `read_committed` tiếp tục đọc record đã commit mà không cần hạ isolation level.
- [ ] Ứng dụng đối soát được side effect và chịu được replay sau abort/restart.
- [ ] Log và metric cho phép nối producer, coordinator, partition và consumer theo cùng transaction/correlation ID.

Transaction treo, fencing và consumer bị chặn là các biểu hiện liên quan đến vòng đời giao dịch. Khi định danh producer được quản lý đúng, transaction có giới hạn thời gian và coordinator hoàn tất marker, consumer `read_committed` có thể tiếp tục đọc dữ liệu đã commit mà vẫn giữ được bảo đảm nguyên tử của Kafka.
