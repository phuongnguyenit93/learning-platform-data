# Phân loại lỗi có thể thử lại, phải hủy hoặc phải đóng producer

Kafka transactional producer có thể gặp lỗi khi khởi tạo transaction, gửi record, gửi offset consumer hoặc hoàn tất transaction. Cách xử lý phụ thuộc vào **loại exception và thao tác đang thực hiện**. Có lỗi chỉ cần thử lại đúng thao tác; có lỗi khiến transaction hiện tại không thể commit và phải abort; cũng có lỗi làm producer rơi vào trạng thái fatal, buộc phải đóng producer.

Nếu phân loại sai, ứng dụng có thể commit một transaction không còn hợp lệ, abort một transaction mà commit đang hoàn tất, hoặc tiếp tục dùng producer đã bị fencing. Bài này xây dựng cách nhận diện ba nhóm lỗi, giải thích vòng đời transactional producer và đưa ra mẫu xử lý bằng Kafka Java client và Spring Kafka.

## 1. Transactional producer có những trạng thái nào?

Khi cấu hình **transactional.id**, Kafka producer sử dụng idempotence và cơ chế transaction. Một producer có thể mở tối đa một transaction tại một thời điểm.

transactional.id nên ổn định cho cùng một logical producer qua các lần restart và duy nhất giữa các producer đang hoạt động đồng thời. initTransactions() khôi phục trạng thái transaction của phiên trước dùng cùng ID: transaction còn mở của phiên đã chết sẽ được abort, còn transaction đang trong giai đoạn hoàn tất sẽ được chờ giải quyết. Hàm này cũng lấy producer ID và epoch cho phiên hiện tại.

Vòng đời cơ bản:

1. Tạo producer với transactional.id.
2. Gọi initTransactions() đúng một lần trước các thao tác transaction.
3. Gọi beginTransaction() để bắt đầu một transaction.
4. Gửi các record; Kafka client tự retry các request có thể retry trong giới hạn cấu hình.
5. Nếu xử lý consume-transform-produce, gửi offset đầu vào bằng sendOffsetsToTransaction().
6. Gọi commitTransaction() để commit toàn bộ hoặc abortTransaction() để hủy toàn bộ.

~~~mermaid
flowchart TD
    A["Tạo producer<br/>transactional.id"] --> B["initTransactions()"]
    B --> C["beginTransaction()"]
    C --> D["send records / offsets"]
    D --> E{"Kết quả và trạng thái lỗi"}
    E -->|"Có thể retry"| F["Thử lại đúng thao tác"]
    F --> D
    E -->|"Transaction abortable"| G["abortTransaction()"]
    G --> H["Bắt đầu transaction mới"]
    E -->|"Lỗi fatal / bị fencing"| I["close producer"]
    E -->|"Mọi thao tác thành công"| J["commitTransaction()"]
    J --> K["Transaction committed"]
~~~

Kafka có transaction coordinator để quản lý trạng thái transaction. Coordinator ghi nhận producer ID/epoch, các partition tham gia và quyết định commit hoặc abort. Khi hoàn tất, Kafka ghi transaction marker vào các partition liên quan. Consumer dùng isolation.level=read_committed chỉ đọc dữ liệu thuộc transaction đã commit; dữ liệu của transaction bị abort không được trả cho consumer này.

## 2. Ba nhóm hành động cần phân biệt

| Nhóm | Trạng thái | Hành động đúng |
|---|---|---|
| Retryable | Thao tác có thể hoàn tất nếu thử lại; producer vẫn có thể tiếp tục theo API contract | Retry đúng thao tác đang dở |
| Abortable | Transaction hiện tại không thể commit, nhưng producer có thể dùng cho transaction mới sau khi abort | Gọi abortTransaction(), sau đó mới bắt đầu transaction khác |
| Fatal | Producer đã bị fencing hoặc ở trạng thái không thể phục hồi | Đóng producer; tạo instance mới sau khi xử lý nguyên nhân |

Không phân loại chỉ dựa trên tên lớp cha KafkaException. Lớp này có thể bao bọc lỗi fatal, abortable hoặc lỗi ngoài dự kiến. Cần xét exception cụ thể, nguyên nhân gốc và API vừa gọi.

## 3. Lỗi có thể thử lại

Lỗi retryable thường do coordinator tạm thời không sẵn sàng, network timeout hoặc request chưa nhận được phản hồi. Khi API cho phép retry, hãy thử lại **chính thao tác đã thất bại**.

Ví dụ:

- Kafka client tự retry các lỗi request có thể retry trong lúc gửi record.
- Ở tầng request, các lỗi như NetworkException, NotCoordinatorException hoặc CoordinatorNotAvailableException thường có thể hồi phục sau khi client kết nối lại hoặc refresh coordinator metadata.
- initTransactions() có thể được gọi lại nếu lần khởi tạo bị timeout hoặc thread bị interrupt trước khi khởi tạo thành công.
- commitTransaction() có thể được thử lại khi nhận TimeoutException hoặc InterruptException.
- abortTransaction() cũng có thể được thử lại nếu bị timeout hoặc interrupt.

### Điểm đặc biệt của commitTransaction()

Nếu commitTransaction() timeout, producer không thể biết chắc coordinator đã nhận và hoàn tất yêu cầu commit hay chưa. Request có thể đã đến broker nhưng response không về kịp. Vì vậy:

- Có thể retry commitTransaction() để nhận kết quả cuối.
- Không gọi abortTransaction() trong lúc commit có thể đang hoàn tất.
- Không bắt đầu transaction mới trên cùng producer khi kết quả commit chưa được giải quyết.
- Nếu ứng dụng quyết định không retry, hãy đóng producer.

Đây là quy tắc quan trọng: **commit timeout không đồng nghĩa transaction đã abort**.

### Timeout khi abortTransaction()

abortTransaction() cũng có thể timeout sau khi yêu cầu đã đến broker. Nếu muốn tiếp tục dùng producer, retry chính abortTransaction() để hoàn tất thao tác abort. Không chuyển sang commitTransaction() vì abort có thể đang hoàn tất ở coordinator. Nếu không retry, đóng producer.

### Retry ở đâu?

| Thao tác | Lỗi thường gặp | Hành động |
|---|---|---|
| initTransactions() | TimeoutException, InterruptException | Retry khởi tạo; sau khi đã khởi tạo thành công thì không gọi lại trong vòng đời producer đó |
| Gửi record | Lỗi network/request tạm thời | Kafka client tự retry; nếu send cuối cùng thất bại không thể phục hồi trong transaction, xử lý theo nhóm abort/fatal |
| sendOffsetsToTransaction() | Timeout khi resolve metadata/gửi offset | Xử lý theo contract của API và trạng thái transaction; không tự commit offset riêng |
| commitTransaction() | TimeoutException, InterruptException | Retry cùng commit; không abort hoặc bắt đầu transaction mới |
| abortTransaction() | TimeoutException, InterruptException | Retry cùng abort; không chuyển sang commit |

Không tạo vòng lặp retry vô hạn cho mọi exception. Retry phải có deadline và logging. Nếu thao tác không thể được xác nhận trong giới hạn vận hành, đóng producer theo contract của API rồi khôi phục bằng một producer mới có cùng transactional.id khi phù hợp.

## 4. Lỗi buộc phải abort transaction

Abortable error làm transaction hiện tại không thể commit, nhưng producer chưa rơi vào trạng thái fatal. Ứng dụng phải hủy transaction đang mở trước khi bắt đầu transaction khác.

Các trường hợp thường gặp:

- Một lần send() trong transaction kết thúc với lỗi không thể phục hồi; commitTransaction() sẽ báo lỗi của lần gửi thất bại và không commit transaction.
- sendOffsetsToTransaction() ném CommitFailedException, ví dụ consumer đã bị loại khỏi group trước khi offset được thêm vào transaction.
- Nghiệp vụ phát hiện dữ liệu không hợp lệ hoặc điều kiện business không đạt, và toàn bộ batch hiện tại phải được hủy để không phát một phần output.
- Kafka client báo transaction đang ở trạng thái abortable.

Khi abort thành công:

- Các record đã ghi trong transaction được đánh dấu aborted.
- Consumer read_committed không nhìn thấy các record thuộc transaction đó.
- Offset gửi trong transaction cũng không được commit.
- Ứng dụng có thể bắt đầu transaction mới trên producer còn hợp lệ.

Với transactional producer, KafkaProducer không bắt buộc ứng dụng phải gắn callback hoặc gọi get() trên Future chỉ để phát hiện lỗi send. Nếu một send trong transaction thất bại với lỗi không thể phục hồi, commitTransaction() sẽ báo lỗi đó và transaction không được commit. Callback vẫn hữu ích cho telemetry, nhưng exception ném ra từ callback không làm transaction tự abort.

### Ví dụ: một record trong batch gửi thất bại

Giả sử transaction gửi ba record A, B, C. A và B đã được broker append nhưng C gặp lỗi không thể phục hồi. Khi commit, producer báo transaction không thể commit. Ứng dụng cần abort để A và B cũng không trở thành output đã commit. Nếu chỉ bỏ qua C rồi tiếp tục transaction, downstream có thể nhìn thấy một phần batch và vi phạm tính nguyên tử.

### Abort rồi retry transaction mới

Sau khi abort thành công, có thể chạy lại toàn bộ đơn vị nghiệp vụ nếu:

- Dữ liệu đầu vào vẫn còn và có thể đọc lại.
- Side effect ngoài Kafka chưa xảy ra hoặc đã được bảo vệ bằng idempotency.
- Nguyên nhân lỗi có khả năng hồi phục.
- Retry có giới hạn và backoff.

Không tự động retry vô hạn lỗi schema, authorization, record quá lớn hoặc lỗi logic. Những lỗi này cần sửa dữ liệu/cấu hình hoặc đưa sự kiện vào quy trình xử lý riêng.

## 5. Lỗi fatal: phải đóng producer

Fatal error khiến transactional producer không thể tiếp tục hoạt động. Gọi abortTransaction() cũng không khôi phục được producer nếu nó đã bị fencing hoặc ở trạng thái fatal.

Các exception điển hình:

| Exception | Ý nghĩa | Hành động |
|---|---|---|
| ProducerFencedException | Một producer khác dùng cùng transactional.id đã chiếm quyền; instance hiện tại là zombie | Đóng producer hiện tại |
| InvalidProducerEpochException | Producer gửi với epoch cũ | Đóng producer |
| OutOfOrderSequenceException | Sequence number không còn hợp lệ theo trạng thái producer/broker | Đóng producer |
| UnsupportedVersionException | Broker không hỗ trợ API/protocol transaction cần dùng | Đóng producer và xử lý tương thích phiên bản |
| AuthorizationException trong thao tác transaction | Principal không có quyền transactional ID hoặc quyền cần thiết | Đóng producer; sửa ACL trước khi tạo lại |
| FencedInstanceIdException khi gửi offset kèm group metadata | Consumer instance bị fencing do định danh group/member không hợp lệ hoặc trùng | Đóng producer/luồng hiện tại và sửa membership |

Khi producer fatal, các lần gọi API tiếp theo có thể tiếp tục ném KafkaException bọc cùng lỗi gốc. Không dùng lại instance này.

### Producer fencing và transactional.id

transactional.id cần:

- Ổn định cho cùng một logical producer qua các lần restart để Kafka có thể khôi phục transaction cũ.
- Duy nhất giữa các producer đang hoạt động đồng thời.
- Không được chia sẻ vô tình giữa nhiều replica độc lập.

Khi instance mới khởi động với cùng transactional.id, initTransactions() lấy producer ID/epoch mới và fence instance cũ. Đây là cơ chế ngăn zombie producer tiếp tục ghi dữ liệu.

Nếu hai replica cùng dùng một ID và liên tục khởi động, chúng có thể fence lẫn nhau, gây lỗi ProducerFencedException lặp lại. Cần sửa cách cấp ID; không giải quyết bằng cách tăng retries.

## 6. Lỗi dữ liệu và lỗi trạng thái ứng dụng

Không phải exception nào cũng thuộc ba nhóm lỗi broker:

| Lỗi | Nguyên nhân | Hướng xử lý |
|---|---|---|
| SerializationException | Object không serialize được hoặc serializer/schema sai | Sửa payload/serializer; nếu transaction đã gửi record khác và cần atomicity, abort transaction |
| RecordTooLargeException | Record vượt giới hạn cấu hình | Giảm payload hoặc điều chỉnh giới hạn có kiểm soát; không retry nguyên trạng |
| IllegalStateException | Gọi API sai vòng đời, ví dụ commit khi chưa begin hoặc begin khi transaction trước chưa kết thúc | Sửa logic ứng dụng; không retry mù |
| CommitFailedException | Consumer không còn quyền commit offset cho group, thường do rebalance/fencing | Abort transaction chứa output và xử lý lại input theo group state |
| TimeoutException ở commit/abort | Không nhận được xác nhận đúng hạn; thao tác có thể đã đến broker | Retry đúng thao tác hiện tại; không đổi commit thành abort hoặc ngược lại |

KafkaException là lớp tổng quát. Hãy kiểm tra cause chain và trạng thái producer; đừng coi mọi KafkaException là lỗi abortable. Fatal exceptions phải được bắt riêng trước khi xử lý nhóm abortable.

## 7. Trình tự quyết định khi gặp exception

~~~mermaid
flowchart TD
    A["Exception từ producer API"] --> B{"Fatal exception?"}
    B -->|"Có"| C["close producer<br/>Không tái sử dụng"]
    B -->|"Không"| D{"API cho phép retry cùng thao tác?"}
    D -->|"Có"| E["Retry chính thao tác đó<br/>theo deadline"]
    E --> F{"Đã có kết quả?"}
    F -->|"Có"| G["Tiếp tục theo kết quả"]
    F -->|"Không"| H["Đóng producer<br/>và khôi phục có kiểm soát"]
    D -->|"Không"| I{"Transaction abortable?"}
    I -->|"Có"| J["abortTransaction()"]
    J --> K["Chỉ sau abort thành công<br/>mới begin transaction mới"]
    I -->|"Không / chưa rõ"| L["Dừng luồng, phân tích<br/>exception và API contract"]
~~~

Thứ tự kiểm tra:

1. Kiểm tra exception cụ thể có thuộc nhóm fatal không.
2. Xác định exception phát sinh từ initTransactions, send, sendOffsetsToTransaction, commitTransaction hay abortTransaction.
3. Nếu API quy định có thể retry, retry đúng thao tác đó.
4. Nếu transaction ở trạng thái abortable, abort và chỉ bắt đầu transaction mới sau khi abort được xác nhận.
5. Nếu fatal hoặc kết quả không thể giải quyết an toàn, đóng producer và khôi phục theo transactional.id.

## 8. Ví dụ Java Kafka Producer

Ví dụ dưới đây minh họa cấu hình producer và phân nhánh lỗi. Phần retry thao tác commit/abort được tách riêng vì timeout ở hai thao tác này không cho phép đổi sang thao tác đối nghịch.

~~~java
import java.time.Duration;
import java.util.Properties;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.errors.AuthorizationException;
import org.apache.kafka.common.errors.FencedInstanceIdException;
import org.apache.kafka.common.errors.InvalidProducerEpochException;
import org.apache.kafka.common.errors.OutOfOrderSequenceException;
import org.apache.kafka.common.errors.ProducerFencedException;
import org.apache.kafka.common.errors.UnsupportedVersionException;
import org.apache.kafka.common.KafkaException;
import org.apache.kafka.common.errors.InterruptException;
import org.apache.kafka.common.errors.TimeoutException;

Properties properties = new Properties();
properties.put("bootstrap.servers", "localhost:9092");
properties.put("transactional.id", "orders-writer-shard-0");
properties.put("key.serializer",
    "org.apache.kafka.common.serialization.StringSerializer");
properties.put("value.serializer",
    "org.apache.kafka.common.serialization.StringSerializer");
properties.put("transaction.timeout.ms", 60_000);

KafkaProducer<String, String> producer =
    new KafkaProducer<>(properties);

try {
    producer.initTransactions();

    producer.beginTransaction();
    try {
        producer.send(new ProducerRecord<>(
            "orders.events", "order-42", "OrderCreated"
        ));
        producer.send(new ProducerRecord<>(
            "orders.audit", "order-42", "Created"
        ));
    } catch (
        ProducerFencedException
        | InvalidProducerEpochException
        | OutOfOrderSequenceException
        | UnsupportedVersionException
        | AuthorizationException fatal
    ) {
        // Producer không thể phục hồi; finally sẽ đóng producer.
        throw fatal;
    } catch (KafkaException abortableOrUnexpected) {
        // KafkaException có thể bọc cả lỗi fatal; phải phân loại cause/state.
        if (!isAbortableTransactionError(abortableOrUnexpected)) {
            throw abortableOrUnexpected;
        }
        producer.abortTransaction();
        throw abortableOrUnexpected;
    }

    try {
        commitWithRetry(producer, 3);
    } catch (TimeoutException | InterruptException unresolved) {
        // Commit chưa được xác nhận sau số lần retry cho phép.
        // finally sẽ đóng producer; tuyệt đối không abort transaction ở đây.
        throw unresolved;
    } catch (
        ProducerFencedException
        | InvalidProducerEpochException
        | OutOfOrderSequenceException
        | UnsupportedVersionException
        | AuthorizationException
        | FencedInstanceIdException fatal
    ) {
        throw fatal;
    } catch (KafkaException abortable) {
        if (!isAbortableTransactionError(abortable)) {
            throw abortable;
        }
        producer.abortTransaction();
        throw abortable;
    }
} finally {
    producer.close(Duration.ofSeconds(10));
}
~~~

Trong mẫu này, isAbortableTransactionError là hàm phân loại do ứng dụng triển khai theo exception cause và trạng thái transaction của phiên bản Kafka client. Lỗi fatal được truyền ra và producer được đóng ở finally. Timeout sau retry commit được xử lý riêng, không đi vào nhánh abort. Nếu lỗi không thuộc nhóm abortable hoặc fatal, cần kiểm tra cause chain và API contract trước khi chọn hành động.

### Mẫu xử lý timeout của commit

~~~java
void commitWithRetry(
    KafkaProducer<String, String> producer,
    int maxAttempts
) {
    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            producer.commitTransaction();
            return;
        } catch (TimeoutException | InterruptException retryable) {
            // Retry chính commitTransaction().
            // Không gọi abortTransaction() hoặc beginTransaction() tại đây.
            if (attempt == maxAttempts) {
                // Kết quả commit chưa được xác nhận: caller phải đóng producer.
                throw retryable;
            }
            backoffBeforeRetry(attempt);
        }
    }
}
~~~

backoffBeforeRetry là hàm hỗ trợ do ứng dụng cung cấp. Nếu hết số lần thử mà vẫn chưa nhận được kết quả, caller phải đóng producer; không abort transaction hoặc bắt đầu transaction khác. Với abortTransaction(), áp dụng cùng nguyên tắc nhưng retry chính abortTransaction().

## 9. Consume-transform-produce và lỗi khi gửi offset

Trong luồng consumer đọc input rồi producer ghi output, offset input phải được gửi vào cùng transaction:

~~~java
try {
    producer.beginTransaction();
    for (var record : records) {
        producer.send(new ProducerRecord<>(
            "orders.enriched",
            record.key(),
            enrich(record.value())
        ));
    }

    producer.sendOffsetsToTransaction(
        offsetsAfter(records),
        consumer.groupMetadata()
    );

    producer.commitTransaction();
} catch (org.apache.kafka.clients.consumer.CommitFailedException
         groupCommitFailed) {
    // Consumer đã mất quyền commit offset (ví dụ bị rebalance).
    // Phải abort output của transaction hiện tại.
    producer.abortTransaction();
    throw groupCommitFailed;
} catch (
    org.apache.kafka.common.errors.ProducerFencedException
    | org.apache.kafka.common.errors.InvalidProducerEpochException
    | org.apache.kafka.common.errors.FencedInstanceIdException
    | org.apache.kafka.common.errors.UnsupportedVersionException
    | org.apache.kafka.common.errors.AuthorizationException fatal
) {
    // Đây là lỗi fatal: đóng producer, không gọi abort để phục hồi.
    producer.close();
    throw fatal;
}
~~~

offsetsAfter(records) phải chứa offset tiếp theo N+1 theo từng partition và chỉ bao gồm tiến độ đã xử lý liên tục. Consumer cần enable.auto.commit=false và không tự commit offset bằng commitSync()/commitAsync() trong mô hình này.

Nếu consumer đã bị kick khỏi group, CommitFailedException cho biết offset không thể được commit. Abort transaction để output chưa trở thành dữ liệu committed; sau đó để consumer group/rebalance điều phối việc đọc lại.

Nếu sendOffsetsToTransaction() ném TimeoutException, không được tự commit offset bằng consumer.commitSync(). Hãy xử lý theo API contract của phiên bản client, giữ nguyên transaction context cho đến khi xác định được kết quả; nếu không thể giải quyết an toàn, đóng producer và để group/transaction recovery xử lý lần khởi động tiếp theo.

## 10. Cấu hình transactional.id và transaction timeout

Ví dụ cấu hình:

~~~properties
bootstrap.servers=localhost:9092
transactional.id=orders-writer-shard-0
transaction.timeout.ms=60000
acks=all
enable.idempotence=true
~~~

Khi cấu hình transactional.id, idempotence được bật tự động cùng các cấu hình phụ thuộc. transaction.timeout.ms giới hạn thời gian broker cho phép transaction chưa hoàn tất. Broker có transaction.max.timeout.ms để giới hạn giá trị tối đa client có thể yêu cầu.

Không tăng transaction timeout chỉ để che giấu transaction bị treo. Transaction mở quá lâu giữ trạng thái pending và có thể làm consumer read_committed phải chờ last stable offset tiến lên.

Độ bền của topic tham gia transaction cũng quan trọng. Nên chọn replication factor và min.insync.replicas phù hợp với yêu cầu durability, đồng thời cấu hình producer acks=all.

## 11. Cấu hình Spring Boot và Spring Kafka

Spring Kafka hỗ trợ transaction thông qua DefaultKafkaProducerFactory, KafkaTransactionManager, transactional listener container và KafkaTemplate.

Với Spring Boot:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: ${INSTANCE_ID}-orders-tx-
      acks: all
      properties:
        transaction.timeout.ms: 60000
    consumer:
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

INSTANCE_ID phải khác nhau giữa các application instance đang chạy đồng thời. Producer factory tạo transactional producer từ prefix và suffix; prefix trùng giữa các replica có thể gây fencing.

Spring Boot có thể tự cấu hình KafkaTransactionManager khi có spring.kafka.producer.transaction-id-prefix. Với cấu hình thủ công, KafkaTransactionManager và KafkaTemplate phải dùng cùng một ProducerFactory có hỗ trợ transaction.

### Transaction cục bộ với KafkaTemplate

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publishOrder(String orderId) {
        kafkaTemplate.executeInTransaction(operations -> {
            operations.send("orders.events", orderId, "OrderCreated");
            operations.send("orders.audit", orderId, "Created");
            return true;
        });
    }
}
~~~

Nếu callback kết thúc bình thường, Spring commit transaction. Nếu exception thoát khỏi callback, transaction bị rollback. Không bắt exception rồi trả về bình thường nếu nghiệp vụ yêu cầu abort; việc đó có thể khiến framework coi callback đã thành công và commit.

### Transaction trong listener container

Khi listener container được cấu hình với KafkaTransactionManager, container bắt đầu transaction trước khi gọi listener. Nếu listener xử lý thành công, container gửi offset vào transaction rồi commit. Nếu listener ném exception, transaction rollback và record được đưa lại theo cơ chế của container/AfterRollbackProcessor.

Ví dụ:

~~~java
@KafkaListener(
    topics = "orders.events",
    groupId = "order-projection"
)
public void onOrder(String event) {
    kafkaTemplate.send("orders.processed", event);
}
~~~

Để đoạn listener tham gia Kafka transaction, listener container phải được cấu hình dùng KafkaTransactionManager và KafkaTemplate phải dùng cùng transactional producer factory tương ứng. Chỉ thêm @KafkaListener không tự bật transaction.

## 12. Transaction Kafka và transaction database

Kafka transaction chỉ nguyên tử trong phạm vi Kafka. Nếu ứng dụng đồng thời cập nhật database, hai transaction không tự trở thành một distributed transaction.

Spring có thể đồng bộ transaction manager Kafka với transaction manager database, nhưng commit của hai hệ thống vẫn có thứ tự và có thể gặp lỗi ở transaction thứ hai sau khi transaction thứ nhất đã commit. Ví dụ database commit xong nhưng Kafka commit thất bại; ứng dụng cần chiến lược bù hoặc outbox/inbox để khôi phục.

Nếu cần bảo đảm nghiệp vụ database không lặp khi Kafka giao lại record, dùng inbox/idempotent write trong cùng database transaction. Nếu cần phát sự kiện Kafka cùng thay đổi database, cân nhắc Transactional Outbox. Không coi @Transactional kết hợp nhiều transaction manager là bằng chứng hai hệ thống commit nguyên tử tuyệt đối.

## 13. Theo dõi và chẩn đoán

Nên theo dõi:

- Số transaction bắt đầu, commit và abort.
- Tỷ lệ transaction abort và nguyên nhân.
- Số lỗi producer fencing, invalid epoch, out-of-order sequence.
- Lỗi coordinator, request timeout và thời gian commit/abort.
- Transaction mở quá lâu hoặc vượt transaction.timeout.ms.
- transactional.id trùng giữa các instance.
- Consumer lag và last stable offset khi dùng read_committed.
- ACL đối với transactional ID, topic và consumer group.

Khi thấy ProducerFencedException, kiểm tra trước tiên có hai producer đang chạy cùng transactional.id hay không. Khi thấy CommitFailedException trong sendOffsetsToTransaction, kiểm tra rebalance và quyền sở hữu partition. Khi thấy timeout ở commit/abort, xác định chính xác thao tác đang dở trước khi quyết định retry hoặc đóng producer.

## 14. Bài tập tự kiểm tra

1. Một commitTransaction() ném TimeoutException. Vì sao không được lập tức gọi abortTransaction()?
2. Một sendOffsetsToTransaction() ném CommitFailedException vì consumer bị kick khỏi group. Cần làm gì với transaction hiện tại?
3. Vì sao ProducerFencedException yêu cầu đóng producer?
4. Hai replica dùng cùng transactional.id có thể gây ra hiện tượng gì?
5. Sau khi abortTransaction() timeout, thao tác nào có thể được thử lại?
6. Vì sao KafkaException không đủ để kết luận lỗi thuộc nhóm abortable?
7. Spring Boot dùng transaction-id-prefix như thế nào để tạo transactional producer cho nhiều instance?

## Kết luận

Lỗi transactional producer phải được xử lý theo exception cụ thể và thao tác đang thực hiện. Retryable error yêu cầu thử lại đúng API call; abortable error yêu cầu abort transaction hiện tại trước khi bắt đầu transaction mới; fatal error như producer fencing, invalid epoch, out-of-order sequence, unsupported version hoặc authorization phải đóng producer.

Đặc biệt, timeout ở commitTransaction() hoặc abortTransaction() có thể xảy ra sau khi request đã đến broker. Hãy retry cùng thao tác; không chuyển commit thành abort hoặc ngược lại. Thiết kế transactional.id ổn định nhưng duy nhất, cấu hình transaction timeout hợp lý và theo dõi coordinator/fencing giúp producer phục hồi an toàn khi cluster hoặc ứng dụng gặp lỗi.

## Tài liệu tham khảo

- [Apache Kafka 4.4 – KafkaProducer Java API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html)
- [Spring for Apache Kafka – Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
