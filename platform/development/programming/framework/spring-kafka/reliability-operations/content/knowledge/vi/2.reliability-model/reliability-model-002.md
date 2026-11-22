# Delivery guarantee của producer

Trong Spring Kafka, delivery guarantee của producer mô tả mức độ chắc chắn mà ứng dụng có thể đạt được khi gửi một record đến Kafka: record có thể bị mất hay không, có thể xuất hiện nhiều lần hay không, và thứ tự của các record có được giữ hay không. Những bảo đảm này được hình thành từ nhiều lớp phối hợp với nhau: cách producer gửi và retry, cấu hình xác nhận của broker, replication của topic, cơ chế idempotence và transaction, cùng cách ứng dụng xử lý kết quả gửi.

Một lời gọi gửi thành công từ ứng dụng không đồng nghĩa với việc consumer đã xử lý record. Nó chỉ cho biết producer đã nhận được xác nhận theo chính sách cấu hình của nó. Muốn bảo đảm toàn bộ luồng nghiệp vụ, cần xem xét cả consumer, database và các hệ thống bên ngoài Kafka.

## 1. Luồng gửi record và ý nghĩa của acknowledgement

Khi ứng dụng gọi KafkaTemplate.send(), Spring Kafka tạo ProducerRecord và chuyển nó đến Kafka producer của Apache Kafka. Producer serialize key/value, xác định partition, gom record vào batch, rồi gửi request đến broker đang giữ vai trò leader của partition đó.

Luồng khái quát:

~~~text
Ứng dụng
   |
   | KafkaTemplate.send(record)
   v
Spring Kafka / KafkaProducer
   |
   | serialize, partition, batch
   v
Broker leader của partition
   |
   | append record vào log
   | replicate đến các replica trong ISR
   v
Acknowledgement theo cấu hình acks
   |
   v
CompletableFuture hoàn tất / callback được gọi
~~~

Producer thường gửi bất đồng bộ. Lệnh send có thể trả về trước khi broker xác nhận; kết quả cuối cùng được thể hiện qua future hoặc callback. Vì vậy, cần phân biệt ba thời điểm:

1. Ứng dụng đã gọi send: record được chuyển cho producer để xử lý.
2. Broker đã xác nhận: producer nhận được acknowledgement đáp ứng cấu hình acks.
3. Consumer đã xử lý: một consumer đọc record và hoàn tất nghiệp vụ của nó.

Delivery guarantee của producer chủ yếu điều khiển hai thời điểm đầu. Nó không tự bảo đảm thời điểm thứ ba.

### Các giá trị acks

Thuộc tính acks xác định producer cần bao nhiêu xác nhận từ broker trước khi coi một lần gửi là thành công.

| Giá trị | Điều producer chờ | Độ bền và rủi ro |
|---|---|---|
| 0 | Không chờ broker acknowledgement | Độ trễ thấp, nhưng producer không biết broker có nhận record hay không. Record có thể mất mà ứng dụng không nhận được lỗi tương ứng. |
| 1 | Chờ leader ghi record vào log cục bộ và xác nhận | Nếu leader lỗi trước khi record được replicate sang replica khác, record có thể mất khi một replica mới được bầu làm leader. |
| all hoặc -1 | Chờ tất cả replica hiện thuộc ISR xác nhận | Bảo đảm mạnh hơn khi kết hợp replication factor và min.insync.replicas phù hợp. Đây là lựa chọn thường dùng cho dữ liệu quan trọng. |

all không có nghĩa là chờ mọi broker trong cluster. Nó có nghĩa là chờ các replica đang nằm trong In-Sync Replicas (ISR) của partition tại thời điểm ghi. ISR là tập replica được xem là theo kịp leader theo các tiêu chí replication của Kafka.

Ví dụ, một topic có replication factor bằng 3 và min.insync.replicas bằng 2. Nếu cả ba replica đang ở ISR, producer dùng acks=all sẽ chờ cả ba replica trong ISR xác nhận. Nếu chỉ còn hai replica trong ISR, việc ghi vẫn có thể thành công khi cả hai xác nhận. Nếu ISR giảm xuống dưới hai, broker từ chối yêu cầu ghi để tránh chấp nhận một lần ghi với mức replication thấp hơn chính sách tối thiểu.

Do đó, acks=all cần được cấu hình cùng min.insync.replicas. Chỉ đặt acks=all mà topic có replication factor thấp hoặc min.insync.replicas không phù hợp thì chưa tạo ra mức độ bền mong muốn.

## 2. Ba kiểu delivery guarantee

Ba cách gọi at-most-once, at-least-once và exactly-once mô tả các trade-off về mất record và record trùng. Chúng không phải ba giá trị cấu hình đơn lẻ. Bảo đảm thực tế phụ thuộc vào producer, broker, ứng dụng và phạm vi nghiệp vụ.

| Kiểu bảo đảm | Có thể mất record? | Có thể có record trùng? | Trường hợp thường gặp |
|---|---|---|---|
| At-most-once | Có | Không do retry của producer | Ưu tiên tránh xử lý lặp, chấp nhận mất một số sự kiện |
| At-least-once | Hạn chế mất khi retry và replication được cấu hình đúng | Có thể | Ưu tiên không bỏ sót sự kiện, chấp nhận xử lý trùng có kiểm soát |
| Exactly-once | Trong phạm vi transaction Kafka được commit, record được công bố một cách nguyên tử | Không do retry producer trong phạm vi idempotence/transaction | Cần ghi nhiều record hoặc kết hợp xử lý consume-transform-produce một cách nguyên tử trong Kafka |

### 2.1. At-most-once

At-most-once có nghĩa một record được gửi tối đa một lần theo logic của ứng dụng. Nếu lần gửi thất bại hoặc kết quả không rõ ràng, ứng dụng không gửi lại. Cách này tránh việc retry tạo thêm bản sao, nhưng đổi lại có thể mất record.

Một cấu hình không chờ acknowledgement như acks=0 có thể làm giảm thời gian chờ, nhưng producer cũng không có thông tin đáng tin cậy để xác nhận record đã được broker ghi. At-most-once ở cấp ứng dụng thường đến từ chính sách không retry sau một lần gửi, chứ không phải một cờ cấu hình duy nhất.

Ví dụ, ứng dụng gửi một sự kiện telemetry có giá trị thấp. Nếu mạng bị gián đoạn đúng lúc gửi, ứng dụng bỏ qua sự kiện đó và tiếp tục xử lý. Hệ thống tránh gửi lặp nhưng chấp nhận thiếu một mẫu dữ liệu.

At-most-once phù hợp khi:

- Dữ liệu có thể mất mà không gây sai lệch nghiệp vụ nghiêm trọng.
- Tốc độ và độ trễ quan trọng hơn độ đầy đủ.
- Một record lặp gây hậu quả lớn hơn việc bỏ sót record.

Không nên chọn cách này cho thanh toán, tạo đơn hàng, thay đổi số dư hoặc các sự kiện cần kiểm toán.

### 2.2. At-least-once

At-least-once hướng đến việc record được ghi thành công ít nhất một lần. Producer retry các lỗi có thể phục hồi, và broker xác nhận theo chính sách acks. Nếu broker đã ghi record nhưng acknowledgement bị mất trên đường về producer, producer có thể không biết lần ghi trước đã thành công hay chưa. Khi gửi lại, broker có thể lưu thêm một bản sao nếu idempotence không được bật.

Ví dụ:

1. Producer gửi sự kiện OrderCreated.
2. Leader ghi record và replica trong ISR cũng nhận record.
3. Broker gửi acknowledgement, nhưng kết nối bị ngắt trước khi producer nhận được.
4. Producer xem lần gửi là chưa thành công và retry.
5. Nếu producer không có cơ chế idempotence, cùng sự kiện nghiệp vụ có thể xuất hiện hai lần trong log.

At-least-once là lựa chọn thực tế cho nhiều hệ thống nghiệp vụ vì nó ưu tiên không bỏ sót sự kiện. Để kiểm soát bản sao, ứng dụng nên có event ID ổn định và consumer nên xử lý idempotent. Ví dụ, consumer lưu event ID đã xử lý trong cùng transaction với thay đổi dữ liệu nghiệp vụ; nếu nhận lại event ID đó, consumer không áp dụng thay đổi lần thứ hai.

Producer retries giúp phục hồi lỗi tạm thời, nhưng không thể biến một lần gửi thất bại vĩnh viễn thành thành công. Khi hết thời gian giao record hoặc gặp lỗi không thể retry, ứng dụng vẫn cần ghi nhận lỗi và quyết định cách xử lý tiếp theo.

### 2.3. Exactly-once

Exactly-once cần được diễn giải theo phạm vi cụ thể. Kafka hỗ trợ hai cơ chế liên quan:

- Idempotent producer: ngăn bản sao phát sinh do producer retry cùng một lần gửi trong một phiên producer.
- Transactional producer: ghi một nhóm record theo transaction; các record được commit cùng nhau hoặc bị abort cùng nhau. Transaction cũng có thể bao gồm offset của consumer trong luồng consume-transform-produce.

Idempotence và transaction không tự ngăn ứng dụng gọi send hai lần cho cùng một sự kiện nghiệp vụ. Nếu ứng dụng nhận một yêu cầu HTTP hai lần và chủ động tạo hai ProducerRecord mới, Kafka xem đó là hai lần gửi khác nhau. Muốn chống lặp ở cấp nghiệp vụ, vẫn cần event ID, idempotency key hoặc kiểm soát ở tầng ứng dụng.

Exactly-once processing trong Kafka thường có nghĩa là kết quả xử lý được công bố đúng một lần trong phạm vi các topic và offset tham gia cùng một transaction Kafka. Bảo đảm này không tự mở rộng sang database, email, API thanh toán hoặc hệ thống ngoài Kafka.

## 3. Idempotent producer

Khi bật idempotence, Kafka gán producer ID và sequence number cho các batch theo từng partition. Broker dùng các thông tin này để nhận diện và loại bỏ bản gửi lặp do retry của cùng producer. Cơ chế này xử lý tình huống acknowledgement bị mất và producer phải gửi lại batch.

Với Kafka client hiện đại, idempotence được hỗ trợ trực tiếp. Nên đặt enable.idempotence=true một cách tường minh để cấu hình thể hiện rõ yêu cầu độ tin cậy và tránh vô tình tắt tính năng khi các tham số khác thay đổi.

Các điều kiện cấu hình cần lưu ý:

- acks phải là all.
- retries phải lớn hơn 0; trong cấu hình thực tế thường cho phép producer retry trong toàn bộ delivery timeout.
- max.in.flight.requests.per.connection không vượt quá 5 với idempotence.
- Không đặt các giá trị xung đột khiến Kafka client vô hiệu hóa idempotence.

Kafka client 3.x mặc định bật idempotence trong nhiều cấu hình thông thường, nhưng khai báo tường minh vẫn giúp người đọc nhận ra đây là yêu cầu reliability chứ không phải một giá trị ngẫu nhiên.

Idempotence bảo vệ retry bên trong Kafka producer. Nó không bảo vệ các trường hợp sau:

- Ứng dụng khởi động lại và gửi lại cùng sự kiện nghiệp vụ như một ProducerRecord mới.
- Một request từ client được xử lý hai lần.
- Ứng dụng tự retry bằng cách gọi KafkaTemplate.send() lần nữa sau khi future báo lỗi.
- Hai service instance độc lập cùng phát một sự kiện.
- Consumer áp dụng side effect hai lần sau khi đọc lại record.

Với các trường hợp đó, hãy tạo event ID ổn định ở ranh giới nghiệp vụ và thiết kế consumer có thể nhận cùng event nhiều lần mà không làm sai dữ liệu.

## 4. Retry, timeout và thứ tự record

Retry là cơ chế phục hồi lỗi tạm thời, chẳng hạn broker leader đang được bầu lại hoặc kết nối mạng bị gián đoạn ngắn. Producer không retry vô hạn trong mọi điều kiện: record có thời hạn giao và có các lỗi không thể khắc phục bằng retry, ví dụ lỗi serialize hoặc cấu hình không hợp lệ.

Một số cấu hình có liên quan:

| Thuộc tính | Vai trò |
|---|---|
| retries | Số lần producer thử lại với lỗi có thể retry. |
| request.timeout.ms | Thời gian chờ một request phản hồi từ broker. |
| delivery.timeout.ms | Giới hạn tổng thời gian producer cố gắng giao record, bao gồm chờ batch, request và retry. |
| max.in.flight.requests.per.connection | Số request chưa nhận phản hồi mà producer có thể gửi trên một kết nối. |
| linger.ms | Thời gian producer chờ thêm record để gom batch, có thể cải thiện throughput với một phần độ trễ bổ sung. |

delivery.timeout.ms phải đủ lớn so với request.timeout.ms và linger.ms. Nếu thời hạn giao quá ngắn, record có thể hết hạn trước khi producer phục hồi được một sự cố broker ngắn. Nếu đặt quá dài, ứng dụng phải chấp nhận việc phát hiện lỗi chậm hơn.

Thứ tự được bảo đảm trong một partition. Kafka không cung cấp thứ tự toàn cục giữa các partition. Nếu các sự kiện của cùng một đơn hàng phải theo thứ tự, hãy dùng order ID làm key để chúng được định tuyến vào cùng partition.

Khi idempotence tắt, nhiều request đang bay cùng lúc kết hợp với retry có thể khiến thứ tự record bị thay đổi trong một số tình huống lỗi. Bật idempotence và giữ max.in.flight.requests.per.connection trong giới hạn được hỗ trợ giúp producer giữ thứ tự trong partition ngay cả khi retry.

Không nên đặt max.in.flight bằng 1 theo thói quen nếu idempotence đã bật và client hỗ trợ giá trị đến 5. Giá trị 1 có thể làm giảm throughput; hãy chọn dựa trên yêu cầu thứ tự và kết quả đo tải.

## 5. Cấu hình producer trong Spring Boot và Spring Kafka

Ví dụ dưới đây thể hiện cấu hình producer ưu tiên độ bền, bật idempotence và cho phép retry trong khoảng thời gian giao record. Các giá trị timeout cần được điều chỉnh theo latency, thời gian phục hồi broker và SLO của hệ thống.

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 2147483647
      properties:
        enable.idempotence: true
        max.in.flight.requests.per.connection: 5
        request.timeout.ms: 30000
        delivery.timeout.ms: 120000
        linger.ms: 5
~~~

Trong ví dụ này:

- acks=all yêu cầu xác nhận từ các replica hiện thuộc ISR.
- enable.idempotence=true chống bản sao phát sinh từ retry của cùng producer.
- retries cho phép client tiếp tục thử lại lỗi có thể phục hồi; delivery.timeout.ms vẫn giới hạn tổng thời gian giao.
- max.in.flight.requests.per.connection=5 cho phép nhiều request đồng thời trong giới hạn tương thích với idempotence.
- request.timeout.ms giới hạn thời gian chờ một request; delivery.timeout.ms đặt giới hạn tổng thể.
- linger.ms cho producer một khoảng ngắn để gom batch. Có thể đặt 0 nếu ưu tiên độ trễ và không muốn chờ gom batch.

Tên property có thể được khai báo qua application.yml hoặc application.properties. Nếu dùng application.properties, các property tương ứng có dạng spring.kafka.producer.acks=all và spring.kafka.producer.properties.enable.idempotence=true.

### Cấu hình phía broker và topic

Để acks=all có ý nghĩa về độ bền, topic cần replication factor đủ lớn và min.insync.replicas được đặt theo số replica tối thiểu mà hệ thống muốn duy trì.

Ví dụ tạo topic với ba replica và yêu cầu ít nhất hai replica trong ISR:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --create \
  --topic orders \
  --partitions 12 \
  --replication-factor 3 \
  --config min.insync.replicas=2
~~~

Với cấu hình trên, producer dùng acks=all có thể ghi khi ít nhất hai replica còn trong ISR. Nếu ISR chỉ còn một replica, broker từ chối ghi cho đến khi replication phục hồi hoặc chính sách được thay đổi có chủ đích.

Các điểm vận hành cần xem xét:

- Replication factor xác định số bản sao của partition. RF=3 thường là điểm khởi đầu phổ biến cho dữ liệu quan trọng, nhưng cần xét topology và ngân sách tài nguyên.
- min.insync.replicas đặt mức ISR tối thiểu cho phép ghi khi producer dùng acks=all.
- Theo dõi under-replicated partitions và ISR shrink để phát hiện nguy cơ giảm khả năng chịu lỗi.
- Cân nhắc tắt unclean leader election cho topic cần độ bền cao. Bầu một replica không nằm trong ISR có thể làm mất record đã được xác nhận trước đó.
- Replication trong cùng cluster không thay thế backup, disaster recovery hoặc bản sao ở vùng địa lý khác.

Nếu topic đã tồn tại, cần kiểm tra cấu hình thực tế của topic thay vì chỉ dựa vào giá trị mặc định của broker.

## 6. Gửi record và xử lý kết quả với KafkaTemplate

Trong Spring Kafka 3.x, KafkaTemplate.send() trả về CompletableFuture<SendResult<K, V>>. Ứng dụng nên quan sát future để biết kết quả gửi, ghi nhận lỗi và lấy metadata khi thành công.

~~~java
@Service
public class OrderEventPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(OrderEventPublisher.class);

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreated>> publish(
            OrderCreated event) {

        return kafkaTemplate
                .send("orders", event.orderId(), event)
                .whenComplete((result, exception) -> {
                    if (exception != null) {
                        log.error(
                                "Cannot publish OrderCreated, eventId={}",
                                event.eventId(),
                                exception);
                        return;
                    }

                    RecordMetadata metadata = result.getRecordMetadata();
                    log.info(
                            "Published eventId={} topic={} partition={} offset={}",
                            event.eventId(),
                            metadata.topic(),
                            metadata.partition(),
                            metadata.offset());
                });
    }
}
~~~

Khi future hoàn tất thành công, producer đã nhận acknowledgement theo cấu hình acks. RecordMetadata cung cấp topic, partition, offset và timestamp liên quan đến record. Offset giúp truy vết vị trí record trong partition, nhưng không chứng minh consumer đã xử lý nó.

Khi future hoàn tất exceptionally, cần ghi nhận lỗi cùng event ID và ngữ cảnh nghiệp vụ đủ để điều tra. Không nên nuốt exception hoặc chỉ ghi một thông báo chung chung vì khi broker có sự cố, hệ thống sẽ khó phân biệt lỗi tạm thời, lỗi cấu hình và lỗi dữ liệu.

Callback nên ngắn gọn. Tránh thực hiện thao tác blocking hoặc gọi API chậm ngay trong callback vì callback có thể chạy trên luồng hoàn tất của producer. Nếu cần xử lý tiếp, hãy chuyển công việc sang executor hoặc một hàng đợi nội bộ phù hợp.

Không cần gọi flush sau mỗi lần send. Việc flush liên tục làm giảm khả năng gom batch và throughput. Hãy để producer quản lý batch bình thường; khi ứng dụng shutdown, cần cho producer được đóng một cách graceful để các record đang chờ có cơ hội hoàn tất trong giới hạn thời gian shutdown.

Với Spring Kafka 2.x, send thường trả về ListenableFuture thay vì CompletableFuture. Cần dùng API callback phù hợp với phiên bản Spring Kafka đang chạy; không sao chép ví dụ CompletableFuture vào dự án phiên bản cũ mà không kiểm tra chữ ký API.

### Khi nào cần chờ đồng bộ?

Trong một số luồng đặc biệt, ứng dụng cần chỉ tiếp tục khi broker đã xác nhận record. Có thể chờ future với timeout, nhưng thao tác này giữ luồng gọi và làm tăng latency:

~~~java
SendResult<String, OrderCreated> result =
        kafkaTemplate.send("orders", event.orderId(), event)
                .get(5, TimeUnit.SECONDS);
~~~

Phải xử lý InterruptedException, ExecutionException và TimeoutException. Nếu ứng dụng timeout khi chờ, kết quả ở broker có thể chưa rõ ràng: record có thể chưa được ghi, hoặc broker đã ghi nhưng phản hồi không đến kịp. Gửi lại một record mới ngay lập tức có thể tạo bản sao nghiệp vụ. Nếu cần retry ở tầng ứng dụng, hãy dùng event ID ổn định và cơ chế idempotency.

## 7. Transactional producer trong Spring Kafka

Idempotence xử lý retry của từng producer. Transaction mở rộng bảo đảm đến một nhóm thao tác gửi: các record thuộc transaction được commit cùng nhau hoặc không được hiển thị cho consumer đọc theo read_committed.

Transaction hữu ích khi một thao tác nghiệp vụ phải công bố nhiều record liên quan. Ví dụ, khi tạo đơn hàng, ứng dụng cần ghi OrderCreated vào topic orders và OrderAuditCreated vào topic order-audit. Nếu hai record phải cùng xuất hiện hoặc cùng không xuất hiện, hãy gửi chúng trong một transaction Kafka.

Để bật transaction cho producer của Spring Kafka, cấu hình transaction ID prefix. Mỗi instance ứng dụng chạy đồng thời phải có prefix riêng để tránh tranh chấp transactional ID:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-node-a-
      acks: all
      properties:
        enable.idempotence: true
~~~

Ví dụ prefix orders-node-a- chỉ minh họa một instance. Trong môi trường nhiều replica, hãy tạo prefix từ định danh instance duy nhất và ổn định trong thời gian instance đó hoạt động. Spring Kafka dùng prefix để tạo transactional ID cho producer.

Có thể dùng KafkaTemplate.executeInTransaction() để gom các lệnh gửi vào một transaction:

~~~java
kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders", event.orderId(), event);
    operations.send("order-audit", event.orderId(), auditEvent);
    return null;
});
~~~

Khi callback hoàn tất bình thường, transaction được commit. Nếu callback ném exception, transaction bị abort. Consumer muốn chỉ nhìn thấy các record đã commit cần đặt isolation.level=read_committed. Consumer dùng read_uncommitted có thể đọc cả record thuộc transaction chưa commit hoặc đã abort.

### Consume-transform-produce

Một trường hợp quan trọng là consumer đọc record, xử lý, gửi record kết quả sang topic khác rồi commit offset. Nếu offset được commit riêng trước khi output được ghi, ứng dụng có thể mất kết quả khi crash. Nếu output được ghi trước nhưng offset chưa commit, record đầu vào có thể được xử lý lại và tạo output trùng.

Spring Kafka hỗ trợ Kafka transaction cho luồng consume-transform-produce. Khi listener container được cấu hình dùng transaction manager Kafka, container có thể điều phối việc gửi output và offset đầu vào trong cùng transaction. Consumer chỉ đọc output đã commit bằng isolation.level=read_committed. Cấu hình cụ thể cần khớp với phiên bản Spring Kafka và cách ứng dụng quản lý transaction.

Transaction Kafka chỉ bao phủ dữ liệu và offset trong Kafka. Nếu listener còn cập nhật database hoặc gọi một hệ thống ngoài, transaction Kafka không tự commit hoặc rollback side effect đó. Không nên gọi một API thanh toán rồi giả định thao tác đó sẽ rollback khi transaction Kafka abort.

### Transaction với database: transactional outbox

Một nghiệp vụ thường vừa ghi database vừa phát event Kafka. Hai hệ thống này không chia sẻ một transaction ACID mặc định. Nếu ghi database thành công nhưng gửi Kafka thất bại, trạng thái database và event bị lệch. Nếu gửi Kafka thành công nhưng database rollback, consumer nhận một event cho thay đổi chưa tồn tại.

Transactional outbox giải quyết bài toán dual-write theo cách sau:

1. Trong một transaction database, cập nhật dữ liệu nghiệp vụ và thêm một bản ghi vào bảng outbox.
2. Một publisher hoặc CDC connector đọc các bản ghi outbox và phát chúng lên Kafka.
3. Theo dõi trạng thái đã phát và dùng event ID để xử lý việc phát lại an toàn.
4. Consumer xử lý idempotent để chịu được trường hợp event được chuyển tiếp nhiều lần.

Outbox tạo tính nguyên tử giữa thay đổi nghiệp vụ và ý định phát event trong database. Việc chuyển outbox sang Kafka vẫn cần retry và cơ chế chống trùng phù hợp.

## 8. Phân biệt retry của producer và retry của ứng dụng

Hai lớp retry thường bị nhầm lẫn:

| Loại retry | Ai thực hiện? | Đặc điểm |
|---|---|---|
| Producer retry | Kafka producer | Retry request khi gặp lỗi có thể retry, sử dụng cùng cơ chế producer ID và sequence number nếu idempotence bật. |
| Application retry | Code nghiệp vụ hoặc tầng xử lý lỗi | Gọi send lại, thường tạo một lần gửi mới; có thể tạo record trùng nếu lần gửi trước thực tế đã được broker ghi. |

Không nên viết callback tự động gọi KafkaTemplate.send() vô hạn mỗi khi future báo lỗi. Cách đó có thể tạo vòng lặp không kiểm soát, làm tăng tải broker và phát nhiều bản sao của cùng event.

Một chính sách xử lý lỗi nên phân loại:

- Lỗi tạm thời: broker unavailable, leader election hoặc lỗi mạng. Trước tiên để producer retry trong delivery timeout.
- Lỗi dữ liệu: serialization hoặc record không hợp lệ. Sửa dữ liệu hoặc đưa vào luồng xử lý lỗi; retry cùng dữ liệu thường không giúp ích.
- Lỗi xác thực hoặc phân quyền: kiểm tra credential và ACL; retry liên tục không khắc phục được cấu hình sai.
- Hết delivery timeout: ghi nhận event chưa được xác nhận và chuyển sang quy trình phục hồi có kiểm soát. Cần xem xét khả năng kết quả ở broker chưa rõ ràng.

Nếu phải retry ở tầng ứng dụng, hãy lưu event ID và payload cần gửi trong một nơi bền vững, dùng backoff có giới hạn, đặt giới hạn số lần thử, và có quy trình xử lý các event không thể gửi. Thiết kế consumer để nhận cùng event ID nhiều lần mà không áp dụng nghiệp vụ lặp.

## 9. Chọn cấu hình theo yêu cầu nghiệp vụ

Không phải mọi topic đều cần cùng một mức bảo đảm. Có thể chọn cấu hình theo hậu quả khi mất hoặc trùng dữ liệu:

| Loại dữ liệu | Hướng cấu hình | Lưu ý |
|---|---|---|
| Telemetry hoặc metric có thể lấy mẫu | Có thể chấp nhận acks thấp hơn hoặc bỏ một số record | Chỉ áp dụng khi mất dữ liệu đã được chấp nhận rõ ràng. |
| Log sự kiện nghiệp vụ | acks=all, replication phù hợp, idempotence bật | Consumer cần xử lý event ID để chịu được phát lại ở tầng ứng dụng. |
| Đơn hàng, thanh toán, số dư | acks=all, min.insync.replicas phù hợp, idempotence; transaction nếu cần atomicity giữa nhiều record Kafka | Thiết kế thêm idempotency key, outbox và kiểm soát side effect ngoài Kafka. |
| Luồng consume-transform-produce | Transaction Kafka bao gồm output và offset | Consumer downstream dùng read_committed. |

Độ tin cậy cũng có chi phí. acks=all và replication tăng số lần truyền dữ liệu giữa broker; transaction thêm bước commit; timeout lớn có thể kéo dài thời gian phát hiện lỗi. Hãy đo throughput, p95/p99 latency, tỷ lệ retry và thời gian phục hồi broker trong môi trường gần với production.

## 10. Quan sát và vận hành

Producer có thể vẫn trả về lỗi dù broker hoạt động, ví dụ do serialization, buffer đầy, ACL hoặc metadata không cập nhật. Ngược lại, một tỷ lệ gửi thành công cao không đủ chứng minh dữ liệu đã được consumer xử lý. Cần theo dõi cả producer, broker và consumer.

Các chỉ số hữu ích ở phía producer:

- Record send rate và byte rate: tốc độ gửi record và dung lượng.
- Record error rate: tỷ lệ gửi thất bại.
- Record retry rate: tần suất producer phải retry.
- Request latency: thời gian broker phản hồi request.
- Record queue time: thời gian record nằm trong producer trước khi gửi.
- Buffer pool wait time: thời gian chờ buffer khi producer chịu áp lực.
- Batch size và compression rate: mức độ gom batch và hiệu quả nén.

Ở phía broker và topic, theo dõi under-replicated partitions, offline partitions, ISR shrink, request handler saturation và dung lượng đĩa. Khi ISR thường xuyên co lại, acks=all có thể làm tăng lỗi ghi vì broker từ chối yêu cầu khi số replica trong ISR thấp hơn min.insync.replicas.

Log ứng dụng nên chứa event ID, topic, key, partition và offset khi gửi thành công. Khi thất bại, ghi loại exception, số lần retry nếu có và thông tin correlation cần thiết. Tránh log toàn bộ payload nhạy cảm.

Khi shutdown, cần đặt thời gian graceful shutdown đủ để producer đóng và xử lý các record còn trong buffer. Không nên kết thúc tiến trình ngay sau khi gọi send bất đồng bộ nếu ứng dụng chưa có cơ chế đảm bảo các lệnh gửi đang chờ được hoàn tất hoặc được lưu lại để phục hồi.

## 11. Những hiểu nhầm thường gặp

**acks=all đồng nghĩa với mọi broker đều có bản sao.** Không đúng. Producer chờ các replica trong ISR, không phải tất cả broker trong cluster. Replication factor và min.insync.replicas quyết định cấu trúc bản sao và mức ISR tối thiểu.

**enable.idempotence=true ngăn mọi event trùng.** Không đúng. Nó loại bỏ bản sao do retry của cùng producer. Hai lần gọi send độc lập cho cùng một event vẫn có thể tạo hai record.

**KafkaTemplate.send() trả về nghĩa là record đã được lưu.** Không đúng. send trả về future trước khi kết quả cuối cùng được biết. Phải quan sát future hoặc callback.

**Future thành công nghĩa là consumer đã xử lý xong.** Không đúng. Future phản ánh acknowledgement từ broker theo acks. Consumer có thể chưa chạy, đang lỗi hoặc xử lý chậm.

**Transaction Kafka làm database rollback cùng Kafka.** Không đúng. Kafka transaction chỉ quản lý các thao tác nằm trong transaction Kafka. Dùng transactional outbox hoặc một thiết kế phối hợp phù hợp khi có database.

**Retry càng nhiều thì hệ thống càng đáng tin cậy.** Không đúng. Retry không sửa được lỗi dữ liệu, ACL hoặc cấu hình. Retry thiếu giới hạn và backoff có thể làm sự cố nặng hơn. Producer retry cũng không thay thế quy trình phục hồi bền vững ở tầng ứng dụng.

**Kafka bảo đảm thứ tự giữa mọi partition.** Không đúng. Thứ tự được giữ trong từng partition. Chọn key phù hợp để các record cần thứ tự đi cùng partition.

## 12. Hướng dẫn thiết kế

Khi thiết kế producer cho một topic mới, hãy xác định trước hậu quả của mất record và record trùng. Từ đó chọn kiểu delivery guarantee và cấu hình broker phù hợp.

Một cấu hình khởi đầu thường dùng cho sự kiện nghiệp vụ là:

1. Topic có replication factor phù hợp với topology, thường bắt đầu xem xét RF=3.
2. min.insync.replicas được đặt theo mức replica tối thiểu mà nghiệp vụ chấp nhận.
3. Producer dùng acks=all và enable.idempotence=true.
4. delivery.timeout.ms và request.timeout.ms phù hợp với SLO và thời gian phục hồi.
5. Record có key ổn định để giữ thứ tự trong cùng thực thể nghiệp vụ.
6. Ứng dụng quan sát kết quả KafkaTemplate.send() và ghi log theo event ID.
7. Consumer có xử lý idempotent để chịu được việc phát lại.
8. Nếu cần commit nhiều record Kafka hoặc kết hợp output với offset, dùng transaction Kafka.
9. Nếu cần ghi database và phát event, dùng transactional outbox hoặc một giải pháp dual-write có bảo đảm tương đương.
10. Theo dõi retry, lỗi gửi, ISR và trạng thái replication trong production.

Delivery guarantee tốt là kết quả của cấu hình nhất quán từ ứng dụng đến broker và cách xử lý nghiệp vụ sau khi record được nhận. Hãy mô tả rõ phạm vi bảo đảm trong tài liệu hệ thống: producer bảo đảm điều gì, consumer phải chống trùng ra sao, transaction bao phủ những thao tác nào, và trường hợp nào cần quy trình phục hồi. Cách diễn đạt chính xác này giúp tránh hiểu nhầm rằng một tham số producer đơn lẻ có thể bảo đảm toàn bộ quy trình nghiệp vụ.
