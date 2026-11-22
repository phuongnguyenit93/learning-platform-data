# Transaction timeout

Trong Kafka, **transaction timeout** là giới hạn do transaction coordinator áp dụng để một transaction không thể giữ trạng thái mở mãi khi producer không còn tiến triển. Nếu transaction tồn tại quá lâu mà coordinator không nhận được cập nhật trạng thái phù hợp, broker có thể chủ động **abort** transaction. Điều này đặc biệt quan trọng với ứng dụng Spring Kafka xử lý kiểu consume–transform–produce: listener vừa tiêu thụ record, vừa ghi output và đưa offset nguồn vào cùng Kafka transaction.

Timeout có hai mặt. Giới hạn quá thấp khiến một transaction hợp lệ bị abort khi listener xử lý chậm, broker chậm hoặc network gián đoạn. Giới hạn quá cao khiến transaction bị bỏ dở giữ trạng thái mở lâu, làm read_committed consumer chờ dữ liệu ổn định, tăng thời gian phục hồi và che khuất các lỗi ứng dụng.

Hiểu transaction timeout cần phân biệt **producer transaction timeout**, **giới hạn do broker cho phép**, **timeout của lời gọi network/producer**, **timeout của Spring transaction** và **max.poll.interval.ms** của consumer. Các giới hạn này không thay thế lẫn nhau.

## 1. Một Kafka transaction dùng để làm gì?

Kafka transaction cho phép nhóm nhiều thao tác ghi Kafka và, trong mô hình phù hợp, **commit offset consumer** thành một đơn vị nguyên tử ở cấp Kafka.

Giả sử dịch vụ nhận OrderPlaced từ topic orders và phát OrderValidated vào topic validated-orders:

~~~text
orders (input)
      |
      v
@KafkaListener
      |
      +-- Xử lý OrderPlaced
      |
      +-- KafkaTemplate.send("validated-orders", result)
      |
      +-- Container đưa consumed offsets vào transaction
      |
      v
Commit Kafka transaction
      |
      +-- Thành công: output hiển thị với read_committed,
      |               offset input được ghi nhận
      |
      +-- Abort: output transactional bị loại khỏi dữ liệu
                   read_committed nhìn thấy,
                   offset input không được commit cùng transaction
~~~

Nếu transaction abort, consumer có thể đọc lại record nguồn từ committed offset trước đó. Nhờ đó, tiến độ tiêu thụ input và output Kafka có thể được đồng bộ theo transaction boundary.

**Giới hạn:** Kafka transaction không tự gom database, REST API, email hoặc hệ thống thanh toán bên ngoài Kafka vào cùng một đơn vị nguyên tử. Những side effect đó cần idempotency, outbox/inbox hoặc workflow phối hợp riêng.

## 2. transaction.timeout.ms là gì?

Kafka producer có thuộc tính **transaction.timeout.ms**. Thuộc tính này mô tả khoảng thời gian tối đa mà transaction coordinator chấp nhận chờ các cập nhật trạng thái transaction từ producer trước khi có thể chủ động abort transaction đang mở.

Ví dụ:

~~~properties
transaction.timeout.ms=120000
~~~

Giá trị 120000 ms tương đương 2 phút. Đây là tham số thuộc **Kafka producer**, được broker transaction coordinator sử dụng; nó không phải một timeout của HTTP client hay @KafkaListener.

Theo mặc định của nhiều phiên bản Apache Kafka, transaction.timeout.ms là **60000 ms (60 giây)**. Khi vận hành, phải kiểm tra phiên bản Kafka client và cấu hình thực tế vì giá trị có thể được thay đổi bởi ứng dụng hoặc platform.

Transaction coordinator theo dõi trạng thái transaction, bao gồm producer identity, epoch, transaction state và các partition tham gia. Nếu một transaction không được hoàn tất theo thời gian coordinator cho phép, broker có thể abort để giải phóng trạng thái và mở đường cho dữ liệu ổn định.

Không nên hiểu transaction.timeout.ms như đồng hồ đếm chính xác từ khi listener bắt đầu đến lúc xử lý xong. Kafka quản lý transaction thông qua protocol và cập nhật trạng thái của producer; thời gian người dùng đo trong ứng dụng còn bao gồm poll, listener, producer request, commit và những khoảng trễ bên ngoài.

## 3. Broker giới hạn transaction timeout ra sao?

Kafka broker có cấu hình **transaction.max.timeout.ms**: giá trị timeout lớn nhất broker chấp nhận từ một transactional producer.

Ví dụ:

~~~properties
# Broker configuration, chỉ minh họa
transaction.max.timeout.ms=900000
~~~

Ở nhiều bản phân phối Apache Kafka, mặc định của giới hạn này là **900000 ms (15 phút)**. Giá trị trong cluster thực tế có thể khác, đặc biệt với Kafka managed service.

Nếu producer yêu cầu transaction.timeout.ms vượt transaction.max.timeout.ms của broker, quá trình **khởi tạo transactional producer** có thể thất bại, thay vì broker âm thầm cho phép transaction dài hơn. Khi đó cần sửa producer configuration hoặc thay đổi giới hạn cluster theo quy trình quản trị.

Không nên tự tăng broker limit chỉ vì một listener hiện tại đang chậm. Trước hết hãy kiểm tra thời gian xử lý, transaction scope, dependency và khả năng chia nhỏ công việc.

### 3.1. Phân biệt hai cấu hình

| Cấu hình | Nằm ở đâu | Mục đích |
|---|---|---|
| transaction.timeout.ms | Kafka producer | Đặt timeout transaction mà producer yêu cầu |
| transaction.max.timeout.ms | Kafka broker | Giới hạn trên broker cho phép |
| transactional.id | Kafka producer | Định danh transactional producer để coordinator quản lý epoch và fencing |
| isolation.level=read_committed | Kafka consumer | Chỉ đọc dữ liệu transactional đã commit và dữ liệu không transactional phù hợp |

transactional.id không phải timeout, nhưng là thành phần quan trọng của transaction state và producer fencing. Không chia sẻ cùng transactional.id đồng thời giữa các producer độc lập.

## 4. Vòng đời một transaction và điểm có thể timeout

Một producer transactional đi qua các bước khái quát:

~~~text
initTransactions()
      |
      v
beginTransaction()
      |
      +-- send() record tới output partitions
      |
      +-- sendOffsetsToTransaction() nếu xử lý input consumer
      |
      v
commitTransaction()
      |
      +-- Commit thành công
      |
      +-- Timeout / broker abort / fencing / lỗi khác
                |
                v
        Xử lý trạng thái transaction,
        rollback/recovery theo framework
~~~

Nếu producer bắt đầu transaction nhưng không commit hoặc abort trong thời gian coordinator cho phép, transaction có thể bị broker abort. Điều này có thể xảy ra dù Java process vẫn đang chạy, chẳng hạn thread bị kẹt do database lock hoặc HTTP request không có timeout.

### 4.1. Transactional producer không phải một database session

Kafka không tự rollback thay đổi ở database khi transaction Kafka abort. Ví dụ listener cập nhật bảng orders, sau đó Kafka transaction timeout:

~~~text
Database update: COMMITTED
Kafka transaction: ABORTED
Input offset trong Kafka transaction: NOT COMMITTED
      |
      v
Record đầu vào được đọc lại
      |
      v
Database update có thể thực hiện lần nữa
~~~

Đây là lý do giao dịch Kafka không thay thế thiết kế **idempotent consumer** hoặc **transactional outbox** khi có tài nguyên ngoài Kafka.

## 5. Cấu hình transaction timeout trong Spring Boot

Một ứng dụng Spring Boot có thể bật Kafka transaction bằng transaction ID prefix và truyền producer property:

~~~yaml
spring:
  kafka:
    bootstrap-servers: broker1:9092,broker2:9092
    producer:
      transaction-id-prefix: orders-tx-
      properties:
        transaction.timeout.ms: 120000
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Ý nghĩa:

- **transaction-id-prefix** giúp producer factory tạo transactional producers với transactional.id riêng.
- **transaction.timeout.ms** yêu cầu transaction timeout 2 phút cho Kafka producer.
- **enable-auto-commit=false** cho phép listener container quản lý offset thay vì Kafka consumer tự commit định kỳ.
- **read_committed** dành cho consumer cần ẩn output transactional chưa commit hoặc đã abort.

Prefix cần **duy nhất giữa các application instances chạy đồng thời** khi dùng transactional producer pooling của Spring Kafka. Ví dụ có thể thêm instance ID, pod name hoặc một định danh triển khai ổn định theo chính sách platform. Nếu hai instance vô tình dùng trùng transactional.id, chúng có thể fence lẫn nhau.

Các property Spring Boot và việc tự tạo KafkaTransactionManager có thể khác giữa phiên bản. Hãy xác định version, producer factory thực tế và transaction manager được listener container sử dụng.

### 5.1. Cấu hình bằng Java

Khi tự tạo DefaultKafkaProducerFactory:

~~~java
@Bean
ProducerFactory<String, String> producerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> config =
        new HashMap<>(kafkaProperties.buildProducerProperties());

    config.put(
        ProducerConfig.TRANSACTION_TIMEOUT_CONFIG,
        120_000
    );

    DefaultKafkaProducerFactory<String, String> factory =
        new DefaultKafkaProducerFactory<>(config);

    factory.setTransactionIdPrefix("orders-service-instance-1-tx-");
    return factory;
}
~~~

Ví dụ minh họa cách đặt producer property; chữ ký buildProducerProperties và cách truyền SSL bundles có thể thay đổi theo Spring Boot version. Nếu Boot đã tự cấu hình ProducerFactory và KafkaTransactionManager, không nhất thiết phải tự tạo lại các bean.

## 6. Transaction trong KafkaTemplate

Với producer factory có transaction ID prefix, KafkaTemplate có thể thực hiện một nhóm send trong transaction:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishTwoEvents(String orderId) {
        kafkaTemplate.executeInTransaction(operations -> {
            operations.send(
                "orders-validated",
                orderId,
                "VALIDATED"
            );
            operations.send(
                "orders-audit",
                orderId,
                "VALIDATED"
            );
            return null;
        });
    }
}
~~~

Trong ví dụ, hai send là phần của Kafka transaction do KafkaTemplate quản lý. Nếu transaction commit thành công, read_committed consumers có thể nhìn thấy output đã commit. Nếu transaction abort, các output transactional của transaction đó bị ẩn với read_committed consumers.

Một vấn đề có thể xuất hiện nếu đoạn code trong executeInTransaction làm công việc ngoài Kafka quá lâu, ví dụ gọi HTTP API không giới hạn timeout. Transaction mở trong khi đợi HTTP và có nguy cơ bị coordinator abort.

Do đó, **giữ transaction scope nhỏ nhất có thể**. Thực hiện công việc chuẩn bị thuần CPU hoặc truy vấn lâu trước khi bắt đầu transaction khi không cần chúng thuộc transaction boundary. Nếu side effect ngoài Kafka phải phối hợp, thiết kế outbox/inbox hoặc protocol phục hồi phù hợp.

## 7. Container transaction trong Spring Kafka

Khi listener container được cấu hình Kafka transaction manager, container quản lý Kafka transaction quanh quá trình xử lý record hoặc batch. Nó có thể gửi offset tiêu thụ vào cùng transaction với output của listener.

Một cấu hình khái quát:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        KafkaTransactionManager<String, OrderEvent> transactionManager) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties()
           .setKafkaAwareTransactionManager(transactionManager);

    return factory;
}
~~~

Đoạn code mang tính minh họa; transaction manager generic cần phù hợp ProducerFactory đang dùng để gửi output. API setter và cách Boot tự wiring transaction manager cần xác nhận với phiên bản Spring Kafka thực tế.

Với transactional container:

1. Container poll record.
2. Container bắt đầu Kafka transaction cho đơn vị xử lý.
3. Listener xử lý và gửi Kafka output qua template tương thích.
4. Container đưa offset đã xử lý vào transaction.
5. Producer commit transaction.
6. Nếu commit thành công, output và offset được ghi nhận cùng transaction; nếu abort, output và offset transactional không được commit.

Timeout có thể xảy ra nếu listener hoặc thao tác commit bị kẹt quá lâu. Chỉnh transaction.timeout.ms chỉ là một phần; cần đo cả thời gian listener, producer requests và commit transaction.

## 8. Transaction timeout khác Spring @Transactional timeout

Trong ứng dụng Spring, có thể gặp nhiều khái niệm “transaction timeout”:

~~~java
@Transactional(timeout = 30)
public void updateOrder(...) {
    // ...
}
~~~

Giá trị **timeout=30** ở annotation thuộc Spring transaction abstraction; behavior thực tế do **PlatformTransactionManager** và tài nguyên mà nó quản lý quyết định. Với database transaction manager, timeout có thể ảnh hưởng các resource operations theo implementation.

Nó **không tự đồng nghĩa** với Kafka producer property transaction.timeout.ms. Không nên giả định chỉ thêm @Transactional(timeout=30) là broker sẽ abort Kafka transaction sau đúng 30 giây.

Tương tự, Kafka transaction.timeout.ms không giới hạn mỗi câu SQL hoặc HTTP call. Nếu HTTP client treo, transaction có thể bị broker abort trong lúc thread vẫn đang chờ lời gọi HTTP.

### 8.1. So sánh các timeout dễ nhầm

| Timeout | Component | Giới hạn gì? |
|---|---|---|
| transaction.timeout.ms | Kafka transactional producer/coordinator | Transaction coordinator có thể abort transaction mở khi quá hạn |
| transaction.max.timeout.ms | Kafka broker | Giá trị transaction timeout lớn nhất broker chấp nhận |
| @Transactional(timeout=...) | Spring transaction abstraction | Timeout do transaction manager tương ứng thực thi |
| max.poll.interval.ms | Kafka consumer | Khoảng thời gian tối đa giữa các lần poll hợp lệ trước khi group đánh giá consumer không tiến triển |
| delivery.timeout.ms | Kafka producer | Thời gian tối đa cho việc giao một producer record theo retry/delivery policy |
| request.timeout.ms | Kafka client | Thời gian chờ phản hồi một request |
| max.block.ms | Kafka producer | Giới hạn blocking ở một số producer API khi đợi metadata hoặc buffer |
| HTTP connect/read timeout | HTTP client | Giới hạn thiết lập kết nối và chờ response từ dependency |
| Database statement/lock timeout | Database/driver | Giới hạn thao tác SQL, lock wait theo cơ chế DB |

Không có một timeout duy nhất bao phủ tất cả các lớp. Một thiết kế production cần đảm bảo timeout dependency và ngân sách xử lý phù hợp với thời gian mở transaction mong muốn.

## 9. Ví dụ transaction timeout trong consume–transform–produce

Giả sử:

- transaction.timeout.ms: 60 giây.
- Listener đọc record OrderPlaced.
- Listener gọi dịch vụ pricing mất 75 giây.
- Sau đó listener gửi record OrderPriced và container thử commit Kafka transaction.

Diễn biến khái quát:

~~~text
t=0s   Container bắt đầu Kafka transaction
       |
t=1s   Listener bắt đầu gọi pricing service
       |
t=60s  Transaction coordinator có thể xác định
       |      transaction đã quá thời hạn
       |      và chủ động abort
       |
t=76s  Listener hoàn thành, gửi output/commit
       |
       v
       Transaction không còn ở trạng thái
       cho phép commit theo dự kiến
       |
       v
       Exception -> rollback/error handling
       |
       v
       Input offset chưa được commit
       cùng Kafka transaction
~~~

Mốc t=60 chỉ là biểu diễn trực quan, không phải một cam kết broker abort chính xác ở mili giây thứ 60000 kể từ lúc listener bắt đầu. Transaction coordinator thực thi cơ chế timeout theo protocol và lịch xử lý của broker.

Khi transaction đã abort, Kafka output trong transaction đó không hiển thị với read_committed consumers. Record đầu vào có thể được redeliver. Nếu pricing service đã có side effect, nó có thể được gọi lại.

Khắc phục tốt nhất thường là giảm thời gian transaction mở, đặt timeout dependency và thiết kế idempotency, thay vì ngay lập tức nâng transaction.timeout.ms lên giá trị rất lớn.

## 10. Transaction timeout có thể biểu hiện bằng những exception nào?

Không có một exception duy nhất cho mọi trường hợp transaction hết hạn. Tùy thời điểm phát sinh lỗi, phiên bản Kafka client và trạng thái producer, ứng dụng có thể gặp KafkaException, TimeoutException, InvalidTxnStateException, producer fencing hoặc exception từ Spring transaction framework.

Các nhóm cần phân biệt:

### 10.1. Timeout khi producer request

Producer có thể timeout khi gửi record, lấy metadata, thêm partition vào transaction hoặc commit transaction. Một request timeout không tự chứng minh broker đã abort transaction. Cần xem producer state và exception gốc.

### 10.2. Coordinator đã abort transaction

Nếu transaction coordinator chủ động abort vì timeout, producer có thể không còn được phép commit transaction đó. Lỗi thường được quan sát khi producer tiếp tục gửi/commit hoặc khi framework hoàn tất transaction.

### 10.3. Producer fencing

Khi một producer khác sử dụng cùng transactional.id với epoch mới, producer cũ có thể bị **fence**. ProducerFencedException hoặc các lỗi liên quan đến producer epoch cho biết instance hiện tại không còn quyền dùng transactional identity như trước.

Đây không đơn thuần là một lỗi timeout có thể retry trên cùng producer bị fence. Cần đóng/loại bỏ producer cũ và xác minh transactional.id uniqueness, instance lifecycle và việc restart.

### 10.4. Spring transaction completion failure

Listener có thể xử lý thành công nhưng lỗi chỉ xuất hiện trong giai đoạn container commit Kafka transaction. Khi đó stack trace liên quan Spring Kafka listener container và transaction manager, không nhất thiết trỏ về dòng business logic gây chậm trước đó.

Điều tra bằng timeline bao gồm thời điểm bắt đầu transaction, listener latency, các Kafka send, commit và exception root cause. Tránh chỉ tăng retry listener dựa trên exception bao ngoài.

## 11. Timeout, retry và trạng thái producer

Một điểm quan trọng: sau lỗi transaction, không phải mọi trạng thái producer đều có thể tiếp tục dùng an toàn.

Tùy loại lỗi, client Kafka có thể yêu cầu:

- Abort transaction hiện tại nếu còn hợp lệ và có thể abort.
- Đóng transactional producer vì lỗi fatal hoặc fencing.
- Khởi tạo producer mới với transaction identity/epoch phù hợp.
- Để Spring Kafka transaction manager/container quản lý rollback và redelivery.

Không viết vòng lặp chung:

~~~java
while (true) {
    try {
        producer.commitTransaction();
        break;
    } catch (Exception ex) {
        // Sai: retry mọi exception trên producer cũ vô hạn
    }
}
~~~

Mã này có thể giữ producer ở trạng thái lỗi vĩnh viễn, làm chậm recovery và che mất nguyên nhân. Một transaction đã bị broker abort hoặc producer đã bị fence không thể được “cứu” bằng cách commit lại mãi.

Hãy phân loại error theo Kafka client contract, ghi nhận transaction state và để container/transaction manager quản lý lifecycle theo phiên bản.

## 12. Ảnh hưởng đến consumer read_committed và LSO

Với **isolation.level=read_committed**, consumer không được thấy output của transaction chưa commit hoặc đã abort. Kafka sử dụng **Last Stable Offset (LSO)** để giới hạn vùng log có thể đọc ở isolation này.

Nếu một partition chứa transaction còn mở, các record phía sau ranh giới của transaction đó có thể chưa được read_committed consumer nhìn thấy, dù log end offset tiếp tục tăng.

~~~text
Partition log:
offset 100  committed data
offset 101  transaction T bắt đầu (đang mở)
offset 102  record của T
offset 103  record khác đến sau
offset 104  record khác đến sau

LSO ----> vùng giới hạn đọc read_committed
LEO ----------------------------> cuối log
~~~

Ví dụ trên mô tả tác động khái niệm; Kafka lưu transaction markers và áp dụng LSO theo protocol chứ không nhất thiết có một record “begin” hiển thị như dữ liệu nghiệp vụ.

Nếu transaction T bị treo lâu, read_committed consumer có thể ngừng tiến triển ở partition đó. Khi transaction commit hoặc abort, LSO có thể tiến lên và consumer tiếp tục đọc dữ liệu đã ổn định.

Transaction timeout quá lớn có thể khiến một transaction bỏ dở giữ LSO phía sau lâu hơn, gây độ trễ cho downstream. Transaction timeout quá nhỏ lại tăng số abort không cần thiết. Vì vậy, tuning phải xét cả **producer reliability** và **read_committed consumption latency**.

## 13. Lag có thể gây hiểu nhầm khi transaction mở lâu

Một dashboard lag thường tính:

~~~text
consumer_group_lag = log_end_offset - committed_offset
~~~

Với read_committed consumer, một phần dữ liệu gần log end có thể chưa được đọc vì LSO chưa tiến tới. Khi đó lag tăng không nhất thiết do consumer xử lý chậm.

Ví dụ:

- Producer liên tục ghi record.
- Một transaction mở trên partition trong thời gian dài.
- LEO tăng nhưng LSO bị giữ bởi transaction đang mở.
- read_committed consumer không thể đọc record phía sau LSO.
- Lag tính theo LEO tăng.

Nếu chỉ tăng concurrency consumer, vấn đề không được giải quyết: giới hạn là transaction chưa ổn định, không phải số thread xử lý record.

Khi điều tra, xem cả producer transaction metrics, thời gian transaction mở, broker coordinator health, consumer isolation level và các lag metrics theo definition của exporter.

## 14. Transaction timeout và max.poll.interval.ms

Hai cấu hình này thường bị nhầm:

**transaction.timeout.ms** thuộc Kafka producer/coordinator. Nó giới hạn transaction còn mở theo quy tắc broker.

**max.poll.interval.ms** thuộc Kafka consumer. Nó giới hạn thời gian consumer được phép không thực hiện poll tiếp theo trước khi group coi consumer không còn tiến triển.

Một listener xử lý chậm có thể vi phạm **cả hai**, nhưng hậu quả khác nhau:

~~~text
Listener xử lý lâu
      |
      +--> transaction timeout
      |         |
      |         v
      |      Broker abort transaction,
      |      output và offsets transactional
      |      không commit như dự kiến
      |
      +--> max.poll.interval.ms vượt ngưỡng
                |
                v
             Consumer mất tiến độ group,
             rebalance, partition có thể bị thu hồi
~~~

Nếu consumer đã mất quyền sở hữu partition, việc gửi offset vào transaction hoặc commit theo generation cũ có thể gặp lỗi khác. Cần đo từng trục timeout và xác định nguyên nhân nào xảy ra trước.

### 14.1. Ngân sách thời gian poll và transaction

Ví dụ listener có các bước:

| Bước | Thời gian p99 |
|---|---:|
| Deserialize/chuyển đổi | 0,2 giây |
| Database read | 1,5 giây |
| External API | 8 giây |
| Business compute | 0,5 giây |
| Kafka sends và flush theo transaction | 2 giây |
| Commit transaction | 1 giây |
| Dự phòng GC/network | 3 giây |
| **Tổng xấp xỉ** | **16,2 giây** |

Nếu transaction timeout là 10 giây, budget không phù hợp cho p99. Tuy nhiên, không nên chọn 60 giây chỉ vì tổng này là 16,2 giây: còn phải đánh giá batch size, tình huống lỗi/retry, SLO và coordinator behavior.

Nếu listener xử lý cả một poll batch, nhân thời gian mỗi record với số record thực tế và mức độ song song để ước lượng worst-case. Bài toán thường cần giảm công việc trong transaction thay vì tăng timeout.

## 15. Đặt timeout như thế nào cho hợp lý?

Một cách thiết kế:

1. Xác định **transaction boundary**: bắt đầu trước thao tác nào và kết thúc khi nào.
2. Đo p50/p95/p99 và worst-case của listener cùng Kafka send/commit.
3. Đặt timeout cho database, HTTP và mọi dependency.
4. Tính tổng thời gian nhiều bước có thể giữ transaction mở.
5. Chọn transaction.timeout.ms có dư địa hợp lý so với thời gian transaction thực tế, nhưng vẫn đủ ngắn để broker abort transaction bị bỏ dở.
6. Xác nhận giá trị không vượt broker transaction.max.timeout.ms.
7. Kiểm tra max.poll.interval.ms và batch size độc lập.
8. Thử nghiệm failure injection để xem rollback/recovery khi timeout.

### 15.1. Bài toán chọn 30, 60 hay 180 giây

Giả sử hầu hết transaction hoàn tất trong 2 giây, p99 khoảng 6 giây, nhưng một endpoint ngoài Kafka thỉnh thoảng treo 90 giây.

Không nhất thiết phải nâng timeout lên 180 giây để “hỗ trợ” endpoint đó. Có thể:

- Đặt HTTP timeout hữu hạn, ví dụ phù hợp với SLO 5–10 giây.
- Chuyển phần xử lý chậm sang workflow riêng.
- Bắt đầu Kafka transaction sau bước chuẩn bị dài khi semantics cho phép.
- Dùng outbox nếu cần phối hợp database và Kafka.
- Đặt retry cho lỗi transient bên ngoài transaction đang mở.

Tăng transaction timeout chỉ nên làm khi transaction hợp lệ thực sự cần thời gian dài và downstream chấp nhận tác động của open transaction lên LSO.

## 16. Vì sao không nên mở transaction qua lời gọi ngoài Kafka kéo dài?

Giả sử listener vừa mở Kafka transaction vừa gọi Payment API. Payment API phản hồi sau 70 giây hoặc không phản hồi.

Trong thời gian đó:

- Kafka transaction vẫn mở, dù chưa hoàn tất logic.
- Broker có thể abort vì transaction timeout.
- Consumer thread có thể đang bị giữ bởi HTTP call.
- Nếu payment đã được thực hiện nhưng response mất, kết quả API chưa rõ.
- Record đầu vào có thể redeliver và thanh toán bị gọi lại.

Đây là vấn đề **transaction scope + side effect** chứ không chỉ là timeout property.

Thiết kế thay thế:

- Dùng idempotency key ổn định cho Payment API.
- Dùng outbox để ghi business state và intent gửi event trong cùng database transaction.
- Có worker riêng publish outbox sang Kafka.
- Tách thời gian chờ bên ngoài khỏi Kafka transaction nếu business consistency cho phép.
- Theo dõi trạng thái bất định và đối soát thay vì retry lệnh thanh toán như một lệnh mới.

Kafka transaction không thể rollback một khoản thanh toán đã thành công ở hệ thống khác.

## 17. Hành vi khi transaction timeout và rollback

Với transactional listener container, exception trong listener hoặc khi commit có thể khiến transaction abort/rollback. Sau rollback, framework cần quyết định cách redeliver input records.

Spring Kafka cung cấp **DefaultAfterRollbackProcessor** cho các kịch bản xử lý sau rollback. Nó có thể seek lại các partition/record cần xử lý theo policy và hỗ trợ recovery với số lần thử phù hợp.

Một ví dụ khái niệm:

~~~text
Consumer nhận record ở offset 220
       |
       v
Kafka transaction mở
       |
       v
Listener gửi output transactional
       |
       v
Timeout/commit transaction thất bại
       |
       v
Transaction abort hoặc không commit
       |
       v
Offset 221 không được commit cùng transaction
       |
       v
Record 220 có thể được redeliver
~~~

Khi recovery đưa record lỗi sang DLT, cần xác định việc publish DLT và commit recovered offset có nằm trong transaction recovery thích hợp hay không. Các API như commitRecovered hoặc kafkaTemplate của AfterRollbackProcessor có semantics tùy cấu hình và phiên bản.

Không nên đặt một DefaultErrorHandler non-transactional rồi giả định nó là bộ điều khiển duy nhất cho rollback của container transactional.

## 18. Retry không phải cách cứu một transaction đã timeout

Hai loại retry khác nhau:

1. **Retry một thao tác bên trong transaction còn hợp lệ**: Kafka client có thể retry producer requests theo protocol và delivery timeout.
2. **Retry toàn bộ xử lý record sau khi transaction abort**: Spring Kafka container/rollback processor có thể redeliver input để thực hiện lại với transaction mới.

Nếu Kafka transaction đã bị abort, không thể đơn giản gọi commitTransaction lần nữa trên chính transaction cũ để biến nó thành committed. Hãy để framework đóng/khôi phục producer state theo contract và thực hiện lại công việc trong transaction mới khi an toàn.

Quan trọng: retry toàn bộ listener có thể lặp side effect database/HTTP đã thành công trước đó. Do đó, transaction timeout càng cần event ID/idempotency.

## 19. Producer fencing và transaction ID uniqueness

Kafka dùng **transactional.id** và producer epoch để bảo vệ khỏi zombie producer, ví dụ producer cũ tưởng mình vẫn sở hữu transaction sau khi instance mới đã tiếp quản.

Nếu hai service instances vô tình dùng cùng transactional.id:

~~~text
Instance A: transactional.id=orders-tx-0
        |
        v
Transaction đang mở

Instance B: transactional.id=orders-tx-0
        |
        v
Khởi tạo producer mới với cùng identity
        |
        v
Producer cũ có thể bị fence
~~~

Khi xuất hiện ProducerFencedException, điều tra:

- transaction-id-prefix có duy nhất giữa các instances không?
- Có deploy rolling update đồng thời hai pod dùng cùng prefix không?
- Có producer pool tái sử dụng identity sai không?
- Có instance cũ chưa đóng mà instance mới đã hoạt động không?

Fencing khác với transaction timeout, dù cả hai có thể xảy ra quanh một lần restart hoặc commit chậm. Không tăng timeout để giải quyết transactional.id collision.

## 20. Transaction timeout và read_uncommitted

Consumer dùng isolation.level=read_uncommitted có thể nhìn thấy cả những record thuộc transaction đã abort, vì nó không lọc theo commit status như read_committed.

Vì vậy, nếu output Kafka dựa vào transaction để tránh downstream thấy kết quả chưa commit, consumer downstream cần **read_committed**. Nếu để read_uncommitted, các record output của transaction cuối cùng bị abort vẫn có thể được đọc và gây side effect.

Một hệ thống sử dụng Kafka EOS ở producer nhưng downstream không cấu hình read_committed có thể không nhận được semantics kỳ vọng.

Kiểm tra consumer properties tại **mọi downstream group cần bảo đảm này**, không chỉ producer đầu tiên.

## 21. Transaction timeout trong cluster không ổn định

Broker failover, coordinator migration và network partition có thể làm các request transaction chậm hoặc thất bại. Nếu transaction gần timeout, khoảng trễ này có thể làm tăng xác suất abort.

Để chẩn đoán:

- Xem lỗi coordinator, transaction markers và broker log.
- Kiểm tra leader/ISR của output partitions và internal transaction state topic.
- Đo producer request latency, retry rate và delivery timeout.
- Xác định sự kiện broker restart hoặc network disconnect cùng thời điểm.
- Kiểm tra transaction timeout và broker max.
- So sánh số lượng abort trước/sau hạ tầng thay đổi.

Kafka có các topic nội bộ cho transaction state và consumer offsets; vận hành cluster cần bảo đảm replication, ISR và availability của chúng. Một hạ tầng coordinator yếu có thể ảnh hưởng nhiều transactional producers dù business listener xử lý nhanh.

Không dùng việc tăng transaction.timeout.ms như biện pháp duy nhất để khắc phục broker/controller/coordinator outage dài hạn.

## 22. Monitoring: cần theo dõi metric nào?

Một dashboard tốt cho transactional producer không chỉ có send rate và consumer lag. Nó phải cho thấy transaction có đang hoàn thành trong thời gian dự kiến hay không.

| Tín hiệu | Ý nghĩa vận hành |
|---|---|
| Transaction duration p50/p95/p99 | Transaction thực sự mở bao lâu |
| Transaction commit rate | Số transaction hoàn tất thành công |
| Transaction abort rate | Số transaction bị abort |
| Transaction start/commit error rate | Broker/coordinator hoặc producer đang lỗi |
| Producer fencing/errors | Collision ID, epoch hoặc lifecycle issue |
| Producer request latency/retry | Kafka IO có kéo dài transaction không |
| Listener processing latency | Business logic hoặc dependency có chậm không |
| max.poll.interval và rebalance | Consumer có giữ được nhịp poll không |
| Read_committed consumer lag | Downstream có bị chặn bởi LSO không |
| LSO/HW/LEO nếu hạ tầng có metric | Khoảng cách do transaction mở hay replication |
| External dependency timeout rate | HTTP/database có làm transaction kéo dài không |

Tên metric cụ thể và khả năng xuất qua Micrometer, Kafka client JMX hoặc exporter khác nhau theo phiên bản. Một số chỉ số phải đo ở ứng dụng, ví dụ duration từ lúc begin đến khi commit/abort.

Đặt alert không chỉ trên lỗi transaction timeout đã xảy ra, mà cả xu hướng transaction duration tiến gần ngưỡng, abort rate tăng, read_committed lag tăng và producer fencing bất thường.

## 23. Log và tracing khi transaction timeout

Một log hữu ích cần hỗ trợ dựng timeline:

- Application instance, transactional.id hoặc prefix phù hợp.
- Consumer group, topic, partition và offset nguồn.
- Thời điểm listener bắt đầu/kết thúc.
- Thời điểm transaction begin, commit/abort nếu có.
- Thời gian database/HTTP dependency.
- Thời điểm Kafka send và kết quả producer future.
- Exception class gốc, nested cause và transaction manager exception.
- Transaction timeout config, broker max nếu truy cập được.
- Correlation ID/event ID ổn định.

Không nên log toàn bộ payload nhạy cảm hoặc credential. Khi dùng tracing, phân biệt span Kafka transaction với span HTTP/database, để xác định thời gian transaction đang mở có bị tiêu tốn bởi dependency nào.

Một exception commit xảy ra ở cuối listener có thể do sự cố cách đó hàng chục giây. Timeline giúp tìm nguyên nhân chính xác hơn stack trace cuối cùng.

## 24. Kiểm thử transaction timeout

Kiểm thử cần bao gồm cả tình huống transaction hợp lệ và transaction bị abort.

### 24.1. Giao dịch ngắn thành công

Tạo một input record, listener gửi output trong transaction và commit. Xác nhận:

- Output hiển thị với read_committed consumer.
- Offset nguồn được commit theo container transaction.
- Không có duplicate side effect trong điều kiện bình thường.

### 24.2. Listener chậm vượt transaction timeout

Trong môi trường thử nghiệm có kiểm soát, cấu hình timeout ngắn và tạo một bước xử lý kéo dài hơn ngưỡng. Xác nhận transaction không được commit, downstream read_committed không thấy output abort và input có thể redeliver theo rollback policy.

Không dùng sleep cực dài như một cách kiểm thử production; thời gian thực tế còn bị ảnh hưởng bởi coordinator và các timeout khác.

### 24.3. Transaction ID collision

Khởi tạo hai producer transactional cùng identity trong môi trường test. Quan sát fencing và xác nhận ứng dụng không retry vô hạn trên producer đã bị fence.

### 24.4. Broker coordinator không sẵn sàng

Giả lập lỗi kết nối/coordinator theo cơ chế test harness. Xác nhận error classification, transaction abort/recovery và metric alert.

### 24.5. External side effect thành công rồi Kafka abort

Đây là ca kiểm thử quan trọng nhất với dịch vụ có database/API:

1. Thực hiện side effect với event ID.
2. Ép transaction Kafka abort.
3. Redeliver input.
4. Xác nhận side effect không xảy ra hai lần.

### 24.6. Read_committed bị giữ bởi transaction mở

Tạo một transaction mở trong test cluster rồi ghi tiếp dữ liệu vào cùng partition. Quan sát sự khác biệt giữa read_committed và read_uncommitted khi transaction chưa kết thúc; xác nhận consumer đọc được dữ liệu ổn định sau khi commit/abort.

## 25. Runbook khi thấy lỗi transaction timeout

### Bước 1: Xác định timeout ở lớp nào

Lấy exception gốc và log xung quanh. Xác nhận đây là transaction timeout của Kafka producer/coordinator, request timeout, @Transactional database timeout hay max.poll.interval.ms.

### Bước 2: Xác định producer và transaction scope

Tìm transactional.id, application instance, listener/container factory và producer factory. Xem transaction bắt đầu ở đâu, kết thúc khi nào, có lời gọi dependency dài hay không.

### Bước 3: Kiểm tra cấu hình

- transaction.timeout.ms thực tế của producer là bao nhiêu?
- Broker transaction.max.timeout.ms là bao nhiêu?
- transactional.id prefix có unique trên các instance không?
- Downstream consumer có dùng read_committed không?
- max.poll.interval.ms và timeout của dependency có phù hợp không?

### Bước 4: Xác định nguyên nhân thời gian kéo dài

Đo p99 listener, HTTP/database timeout, Kafka send/commit latency, broker health và GC pause. Nếu listener xử lý một batch lớn, xem số record và công việc tuần tự trong transaction.

### Bước 5: Phân loại mức độ phục hồi

- Nếu timeout do một dependency transient: giảm scope và retry toàn bộ record trong transaction mới theo policy.
- Nếu producer đã bị fence: khôi phục producer lifecycle, sửa transactional.id uniqueness.
- Nếu broker abort do quá hạn: không cố commit lại transaction cũ.
- Nếu có side effect ngoài Kafka: đối soát trạng thái và idempotency trước khi replay.

### Bước 6: Khôi phục và xác nhận

Sau thay đổi, quan sát tỷ lệ commit/abort, transaction duration, listener throughput, read_committed lag, rebalance và duplicate side effects. Xác nhận input offsets và output Kafka tiến triển đúng cùng transaction.

## 26. Các lỗi thiết kế thường gặp

| Sai lầm | Rủi ro | Hướng điều chỉnh |
|---|---|---|
| Tăng transaction.timeout.ms để chữa mọi lỗi | Che listener chậm, giữ open transaction và LSO lâu | Đo transaction scope, dependency và coordinator |
| Đặt producer timeout vượt broker max | Init transactional producer có thể bị từ chối | Xem transaction.max.timeout.ms |
| Nhầm @Transactional timeout với Kafka producer timeout | Không có giới hạn như kỳ vọng | Cấu hình riêng theo manager và Kafka producer |
| Mở transaction qua HTTP không timeout | Broker abort trong khi request vẫn chạy | Đặt timeout, giảm scope, dùng idempotency/outbox |
| Retry commitTransaction vô hạn trên transaction đã abort | Không phục hồi được và có thể giữ producer lỗi | Retry toàn bộ xử lý bằng transaction mới nếu an toàn |
| Dùng cùng transactional.id cho hai instances | Producer fencing | Prefix duy nhất theo instance/lifecycle |
| Downstream để read_uncommitted | Có thể thấy output từ aborted transaction | Dùng read_committed khi cần transactional visibility |
| Xem consumer lag cao là consumer chậm | LSO có thể bị open transaction giữ lại | Kiểm tra LSO và transaction state |
| Retry listener mà không bảo vệ DB/HTTP side effects | Duplicate nghiệp vụ | Inbox/outbox/idempotency key |
| Chỉ xem exception ở commit cuối | Không thấy nguyên nhân listener đã chậm trước đó | Ghi timeline và đo dependency latency |
| Quên max.poll.interval.ms | Có thể đồng thời timeout transaction và rebalance | Tính riêng poll budget |
| Nhầm producer send retry với transaction retry | Retry sai scope hoặc sau fatal error | Phân biệt producer request và transaction lifecycle |

## 27. Checklist trước khi đưa Kafka transaction vào production

1. transaction.timeout.ms đã được cấu hình rõ cho transactional producer chưa?
2. Giá trị có phù hợp broker transaction.max.timeout.ms không?
3. transactional.id prefix có unique giữa các application instances và producer pools không?
4. Đã xác định chính xác transaction bắt đầu/kết thúc tại đâu chưa?
5. Listener có HTTP/database calls kéo dài trong transaction không?
6. Mọi dependency đều có timeout hữu hạn và policy retry hợp lý không?
7. Thời gian transaction p95/p99 có khoảng dự phòng phù hợp với timeout không?
8. max.poll.interval.ms có được đánh giá độc lập với transaction.timeout.ms không?
9. Output consumer có dùng isolation.level=read_committed khi cần không?
10. Có monitoring transaction duration, abort, commit failure, fencing và LSO/lag không?
11. Nếu transaction abort sau side effect ngoài Kafka, có idempotency hoặc đối soát không?
12. Transactional listener có rollback/recovery processor phù hợp không?
13. Có test khi transaction timeout, restart, coordinator outage và duplicate không?
14. Có runbook cho fencing, request timeout và broker abort riêng không?
15. Có cân nhắc outbox/inbox khi yêu cầu consistency vượt phạm vi Kafka không?

**Kết luận:** Transaction timeout không chỉ là một số mili giây trong producer properties. Nó là cơ chế để broker dọn dẹp transaction không hoàn tất, đồng thời có ảnh hưởng trực tiếp đến khả năng commit output/offset của Spring Kafka và độ trễ của read_committed consumers. Cách dùng bền vững là giữ transaction scope ngắn, đặt timeout cho dependency, tách bạch các lớp timeout, bảo đảm transactional.id độc lập, đo transaction duration và thiết kế idempotency cho mọi side effect ngoài Kafka.
