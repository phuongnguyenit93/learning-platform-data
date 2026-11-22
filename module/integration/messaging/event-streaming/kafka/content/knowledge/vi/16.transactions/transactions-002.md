# transactional.id, producer epoch và cơ chế fencing

## Mục tiêu bài học

Kafka transaction cho phép producer ghi nhiều record vào một hoặc nhiều partition theo một đơn vị nguyên tử. Để khôi phục transaction khi producer restart và ngăn một process cũ tiếp tục ghi sau khi quyền sở hữu đã chuyển sang process mới, Kafka dùng transactional ID, producer ID, producer epoch và cơ chế fencing.

Trọng tâm của bài học là cách Kafka nhận diện một logical producer qua transactional ID, cách transaction coordinator cấp hoặc khôi phục producer identity, cách epoch phân biệt producer hiện tại với producer cũ, và vì sao một producer bị fencing phải dừng hoạt động. Người học sẽ cấu hình KafkaProducer và Spring Kafka, triển khai transaction, xử lý ProducerFencedException và áp dụng đúng transactional ID khi chạy nhiều instance.

Sau bài học, người học có thể:

- Phân biệt transactional.id, producer ID, producer epoch và client.id.
- Giải thích vai trò của transaction coordinator và internal topic __transaction_state.
- Mô tả cách initTransactions đăng ký producer và tăng epoch.
- Giải thích fencing và vì sao producer cũ bị từ chối.
- Chọn transactional ID ổn định, duy nhất cho từng logical producer đang hoạt động.
- Phân biệt idempotent producer với transactional producer.
- Dùng KafkaProducer transaction để ghi nhiều record và commit/abort.
- Dùng transaction cho consume-transform-produce và commit input offset nguyên tử với output.
- Cấu hình transaction trong Spring Kafka và xử lý lỗi fencing.

## 1. Vấn đề mà producer fencing giải quyết

Hãy hình dung một ứng dụng xử lý đơn hàng có logical worker tên order-transformer-0. Worker này đang ghi kết quả vào Kafka. Process bị treo hoặc mất kết nối, hệ thống orchestration khởi động một process mới để tiếp quản cùng công việc. Process cũ có thể hồi phục sau một khoảng pause và tiếp tục gửi request.

Nếu Kafka không phân biệt được process cũ và process mới, cả hai có thể cùng ghi transaction cho một logical worker. Điều này có thể tạo output trùng, transaction chồng lấn hoặc làm sai thứ tự xử lý.

Kafka giải quyết bằng fencing:

1. Logical producer được định danh bằng transactional ID ổn định.
2. Khi producer mới khởi tạo với cùng transactional ID, transaction coordinator cấp producer epoch mới.
3. Producer cũ vẫn giữ epoch cũ.
4. Request từ producer cũ bị broker/coordinator từ chối vì epoch đã lỗi thời.
5. Chỉ producer sở hữu epoch mới tiếp tục điều khiển transaction của logical producer đó.

~~~mermaid
sequenceDiagram
    participant Old as Producer cũ
    participant TC as Transaction coordinator
    participant New as Producer mới
    Old->>TC: initTransactions(transactional.id)
    TC-->>Old: PID=700, epoch=4
    Note over Old: Process cũ bị treo/mất kết nối
    New->>TC: initTransactions(same transactional.id)
    TC->>TC: Tăng producer epoch
    TC-->>New: PID=700, epoch=5
    Old->>TC: Gửi request với epoch=4
    TC-->>Old: Producer fenced
    New->>TC: Gửi transaction với epoch=5
    TC-->>New: Request được chấp nhận
~~~

Fencing bảo vệ quyền sở hữu của một logical producer. Nó không phải cơ chế phân quyền người dùng và cũng không thay thế ACL/SASL/TLS. Một producer có credential hợp lệ vẫn có thể bị fencing nếu dùng transactional ID đã được producer mới tiếp quản.

## 2. Bốn khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Vòng đời |
|---|---|---|
| client.id | Tên client dùng cho log, metric và quan sát kết nối | Do ứng dụng cấu hình; không xác định quyền sở hữu transaction |
| transactional.id | Định danh ổn định của logical transactional producer | Được dùng để tìm transaction coordinator và khôi phục quyền sở hữu qua restart |
| producer ID (PID) | Định danh producer do Kafka cấp | Được dùng trong giao thức producer, idempotence và transaction |
| producer epoch | Thế hệ hiện tại của producer ID/transactional producer | Tăng khi producer mới tiếp quản cùng transactional ID để fencing epoch cũ |

Không dùng client.id thay cho transactional.id. Hai producer có thể dùng client ID giống nhau mà không có fencing theo transaction identity. Ngược lại, hai producer dùng cùng transactional ID sẽ cạnh tranh cùng một quyền sở hữu dù client.id khác nhau.

### 2.1. transactional.id

transactional.id là tên logical producer do ứng dụng chọn. Kafka dùng ID này để xác định transaction coordinator quản lý producer và transaction state tương ứng.

Các yêu cầu thiết kế:

- Ổn định qua lần restart của cùng một logical producer để Kafka nhận ra lần tiếp quản.
- Duy nhất giữa các logical producer đang hoạt động đồng thời trong cùng cluster.
- Có thể suy ra từ service, môi trường và shard/instance identity.
- Không tạo ngẫu nhiên một ID mới ở mỗi lần restart nếu muốn fencing producer cũ.
- Không để nhiều instance độc lập cùng dùng một ID nếu chúng phải hoạt động song song.

Ví dụ:

| Logical worker | transactional.id gợi ý |
|---|---|
| Worker 0 của order transformer production | prod-order-transformer-0 |
| Worker 1 của order transformer production | prod-order-transformer-1 |
| Worker 0 của môi trường staging | staging-order-transformer-0 |
| Worker 0 của billing projection | prod-billing-projection-0 |

Đưa môi trường vào ID giúp tránh hai ứng dụng staging và production vô tình dùng chung transactional ID khi cùng kết nối một Kafka cluster.

### 2.2. Producer ID

Producer ID là định danh số do Kafka cấp khi producer khởi tạo. Producer ID cùng sequence number giúp broker nhận diện các batch và retry từ cùng producer, hỗ trợ idempotence.

Ứng dụng không tự chọn PID và không nên lưu PID như một định danh nghiệp vụ. Khi dùng transactional ID, producer nhận PID/epoch từ transaction coordinator trong quá trình initTransactions.

### 2.3. Producer epoch

Epoch là số thế hệ của producer. Khi một producer mới khởi tạo với cùng transactional ID, coordinator tăng epoch để phân biệt producer mới với producer cũ. Các request mang epoch cũ không còn quyền thực hiện thao tác transaction.

Có thể xem epoch như một token về quyền sở hữu theo thời gian:

- Epoch mới hơn đại diện owner hiện tại.
- Epoch cũ đại diện process đã bị thay thế.
- Broker từ chối request của owner cũ sau khi epoch mới được đăng ký.

Epoch không phải timestamp và không biểu thị số lượng record đã gửi. Nó là một phần của giao thức để Kafka phát hiện producer stale.

## 3. Transaction coordinator và __transaction_state

Kafka có transaction coordinator để quản lý trạng thái transaction và producer identity gắn với transactional ID. Coordinator được xác định dựa trên partition của internal topic __transaction_state tương ứng với transactional ID.

Internal topic __transaction_state lưu metadata trạng thái transaction cần cho việc khôi phục sau lỗi coordinator hoặc producer restart. Topic này do Kafka quản lý bằng cơ chế lưu trạng thái nội bộ và compaction; ứng dụng không ghi record nghiệp vụ vào đây và không được sửa file log trực tiếp.

Quy trình khái quát:

1. Producer gửi InitProducerId thông qua initTransactions.
2. Kafka tìm transaction coordinator cho transactional ID.
3. Coordinator cấp hoặc khôi phục producer ID và epoch.
4. Coordinator quản lý trạng thái transaction, participant partition và kết quả commit/abort.
5. Khi producer restart với cùng transactional ID, coordinator tăng epoch và fencing owner cũ.

~~~mermaid
flowchart TB
    P[Transactional producer] -->|transactional.id| TC[Transaction coordinator]
    TC --> TS[__transaction_state partition]
    TS -->|Replicated metadata| R1[Replica broker 1]
    TS -->|Replicated metadata| R2[Replica broker 2]
    TC -->|PID and epoch| P
    P -->|Begin / Produce / Commit / Abort| TC
    TC -->|Prepare and marker coordination| B[Partition leaders]
~~~

Sơ đồ mô tả quan hệ logic. Trong cluster thực tế, nhiều transaction coordinator được phân bố trên các broker; mỗi transactional ID được ánh xạ tới một partition của __transaction_state.

### 3.1. Vì sao transaction state cần replication?

Nếu broker đang làm transaction coordinator dừng, Kafka cần có thể khôi phục trạng thái transaction từ internal topic đã replicate. Replication của __transaction_state giúp coordinator mới tiếp quản sau khi leader partition thay đổi.

Nếu internal transaction topic không có đủ replica hoặc gặp lỗi storage, producer có thể không khởi tạo/commit transaction thành công. Vì vậy, production cần thiết kế replication factor, min ISR và health của broker cho internal topic.

### 3.2. Quan sát internal topic

Có thể kiểm tra partition, leader, replica và ISR của internal topic:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic __transaction_state
~~~

Đây là thao tác quan sát metadata topic. Không dùng console producer/consumer để ghi trực tiếp vào __transaction_state và không tự sửa key/value nội bộ.

## 4. initTransactions và quy trình cấp epoch

Với KafkaProducer, khi cấu hình transactional.id, ứng dụng phải gọi initTransactions trước khi bắt đầu transaction. Lời gọi này đăng ký producer với transaction coordinator, lấy producer identity và hoàn tất việc xử lý trạng thái transaction còn lại từ instance trước theo giao thức Kafka.

Vòng đời cơ bản:

1. Tạo KafkaProducer với transactional.id.
2. Gọi initTransactions một lần trước transaction đầu tiên.
3. Gọi beginTransaction để bắt đầu transaction.
4. Gửi các record thuộc transaction.
5. Gọi commitTransaction nếu toàn bộ công việc thành công.
6. Gọi abortTransaction nếu cần hủy transaction.
7. Tiếp tục transaction tiếp theo trên producer đó.

~~~mermaid
flowchart TD
    A[Create KafkaProducer] --> B[initTransactions]
    B --> C[Nhận PID và epoch hiện tại]
    C --> D[beginTransaction]
    D --> E[Send records]
    E --> F{Xử lý thành công?}
    F -->|Có| G[commitTransaction]
    F -->|Không| H[abortTransaction]
    G --> I[Transaction tiếp theo]
    H --> I
    I --> D
~~~

Không gọi initTransactions trước mỗi transaction. Hàm này là bước khởi tạo/đăng ký producer instance; beginTransaction và commit/abort mới là các thao tác lặp theo từng transaction.

### 4.1. Điều gì xảy ra khi producer mới khởi động?

Giả sử producer cũ đang dùng:

~~~properties
transactional.id=prod-order-transformer-0
~~~

Process mới tiếp quản cùng logical worker và khởi tạo producer với cùng ID. Coordinator tăng epoch, xử lý trạng thái transaction trước đó theo quy tắc khôi phục, sau đó trả producer identity mới. Producer cũ không thể tiếp tục commit transaction bằng epoch cũ.

Điều này đặc biệt quan trọng khi process cũ không chết hẳn mà chỉ bị pause dài, mất network tạm thời hoặc bị tách khỏi hệ thống điều phối. Fencing ngăn zombie process tiếp tục ghi sau khi owner mới đã tiếp quản.

### 4.2. Init producer có thể phải chờ

initTransactions có thể cần liên lạc coordinator, khôi phục transaction state và hoàn tất xử lý transaction cũ. Do đó, không nên gọi nó trong request path cho từng record. Khởi tạo producer ở lifecycle của worker/service và xử lý lỗi startup rõ ràng.

## 5. Cơ chế fencing hoạt động ra sao?

Khi coordinator cấp epoch mới cho transactional ID, producer cũ trở thành stale producer. Broker và coordinator kiểm tra epoch trong các request liên quan. Request dùng epoch cũ bị từ chối.

Các tình huống điển hình:

- Process mới khởi động lại cùng transactional ID trong khi process cũ vẫn còn sống.
- Orchestrator chuyển logical shard sang node khác nhưng node cũ chưa dừng hoàn toàn.
- Hai process vô tình cấu hình cùng transactional ID.
- Một producer cũ tiếp tục gửi hoặc commit sau khi owner mới đã đăng ký.

### 5.1. ProducerFencedException

Java client có thể báo ProducerFencedException khi producer đã mất quyền sở hữu transactional ID. Đây là lỗi fatal đối với producer instance bị fencing.

Khi gặp fencing:

- Dừng sử dụng producer instance cũ.
- Không retry transaction bằng chính instance đã bị fencing.
- Đóng producer và kết thúc worker cũ.
- Kiểm tra cấu hình để tránh hai instance đồng thời dùng cùng ID ngoài chủ đích.
- Để logical owner hiện tại tiếp tục công việc.

Không bắt ProducerFencedException rồi lặp lại beginTransaction/commitTransaction trên cùng producer. Epoch của instance đó đã lỗi thời; retry không thể khôi phục quyền sở hữu.

### 5.2. Fencing khác lỗi network

| Tình huống | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Network timeout tạm thời | Chưa nhận được response; kết quả một request có thể chưa rõ | Để producer retry theo giao thức hoặc xử lý trạng thái transaction theo exception |
| Coordinator unavailable | Chưa liên lạc được coordinator hiện tại | Chờ coordinator phục hồi theo timeout/retry phù hợp |
| ProducerFencedException | Producer đã mất quyền sở hữu epoch/transactional ID | Dừng và đóng producer cũ |
| Transaction timeout | Transaction vượt giới hạn thời gian | Abort hoặc xử lý theo trạng thái producer/error semantics |
| Authorization failure | Principal không có quyền cần thiết | Sửa ACL/credential; không đổi transactional ID để né quyền |

Không phân loại mọi exception thành fencing. Chỉ kết luận producer bị fencing khi exception/response chỉ rõ quyền sở hữu đã bị thay thế.

## 6. Chọn transactional.id cho nhiều instance

Thiết kế transactional ID là quyết định vận hành quan trọng. Cần cân bằng hai yêu cầu:

- Cùng một logical worker phải dùng lại ID qua restart để producer mới fencing process cũ.
- Hai logical worker hoạt động song song phải dùng ID khác nhau để không fencing lẫn nhau.

Ví dụ deployment có ba shard:

~~~text
prod-inventory-projector-0
prod-inventory-projector-1
prod-inventory-projector-2
~~~

Mỗi shard giữ ID ổn định. Nếu shard 1 restart, instance mới của shard 1 dùng lại ID kết thúc bằng -1. Shard 0 và shard 2 không bị ảnh hưởng.

### 6.1. Những cách đặt ID dễ gây lỗi

| Cách đặt | Vấn đề |
|---|---|
| Tất cả pod dùng orders-producer | Pod mới fencing pod khác dù chúng cần chạy song song |
| Tạo UUID mới mỗi lần process start | Không nhận diện được logical producer cũ qua restart |
| Dùng hostname ngẫu nhiên của pod | Restart có thể tạo ID mới và không fencing đúng owner cũ |
| Dùng cùng ID cho staging và production trên cùng cluster | Hai môi trường có thể fencing lẫn nhau |
| Dùng ID cố định nhưng scale nhiều replica không phân biệt ordinal | Các replica tranh chấp cùng một transactional ID |

### 6.2. Quy tắc đặt ID

Một mẫu có thể dùng:

~~~text
<environment>-<service>-<logical-shard>
~~~

Ví dụ:

~~~text
prod-payment-projector-0
prod-payment-projector-1
staging-payment-projector-0
~~~

Với StatefulSet, ordinal có thể là một phần của logical shard. Với hệ thống partition workload động, cần một cơ chế cấp lease/ownership để đảm bảo một logical shard chỉ có một owner đang hoạt động; transactional ID là lớp fencing phía Kafka, không thay thế hoàn toàn cơ chế điều phối công việc.

## 7. Idempotent producer và transactional producer

Idempotence và transaction có liên quan nhưng không giống nhau.

| Đặc tính | Idempotent producer | Transactional producer |
|---|---|---|
| Mục tiêu | Tránh duplicate do retry của producer protocol | Ghi nhiều record/partition theo một transaction nguyên tử |
| Định danh | Producer ID và sequence number | transactional.id, producer ID và epoch |
| Phạm vi | Các batch của producer session | Nhiều record và partition trong transaction |
| Commit/abort | Không có transaction nghiệp vụ | Có commitTransaction/abortTransaction |
| Fencing logical producer qua restart | Không phải mục tiêu chính | Có qua transactional ID và epoch |
| Consume-transform-produce cùng offset | Không tự thực hiện | Có thể commit output và input offset trong cùng transaction |

Khi cấu hình transactional.id, Kafka bật các điều kiện idempotence cần thiết cho transactional producer. Có thể khai báo enable.idempotence=true tường minh để làm rõ ý định.

Idempotent producer giúp retry request an toàn trong phạm vi producer identity/sequence. Transaction giúp nhiều output được nhìn thấy cùng nhau hoặc không được nhìn thấy bởi consumer dùng read_committed. Cả hai vẫn không biến side effect bên ngoài Kafka thành transaction phân tán.

## 8. Cấu hình KafkaProducer với transactional.id

Ví dụ cấu hình Java:

~~~java
import java.util.Properties;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.serialization.StringSerializer;

public class TransactionalProducerFactory {

    public static KafkaProducer<String, String> create(String instanceId) {
        Properties props = new Properties();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName());
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName());

        // Ổn định qua restart của cùng logical worker, duy nhất giữa worker song song.
        props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG,
            "prod-order-transformer-" + instanceId);

        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.TRANSACTION_TIMEOUT_CONFIG, 60000);

        return new KafkaProducer<>(props);
    }
}
~~~

Trong ví dụ, instanceId phải là logical shard identity ổn định, không phải UUID ngẫu nhiên tạo mới mỗi lần restart. Hai worker song song phải có instanceId khác nhau.

### 8.1. transaction.timeout.ms

transaction.timeout.ms đặt giới hạn thời gian transaction có thể mở trước khi coordinator xem transaction quá hạn và xử lý abort. Giá trị client phải nằm trong giới hạn broker, thường được kiểm soát bởi transaction.max.timeout.ms.

Transaction timeout quá ngắn có thể làm transaction bị abort khi batch xử lý chậm. Timeout quá dài khiến transaction mở lâu, giữ Last Stable Offset (LSO) lùi lại và làm consumer read_committed bị chặn không đọc vượt qua transaction chưa kết thúc trên partition liên quan.

Hãy giữ transaction ngắn:

- Poll một batch vừa phải.
- Thực hiện xử lý nhanh và có giới hạn.
- Gửi output và offset trong cùng transaction.
- Commit hoặc abort ngay khi hoàn tất.
- Không chờ thao tác HTTP/database dài bên trong transaction Kafka nếu có thể thiết kế lại.

### 8.2. transaction.max.timeout.ms

transaction.max.timeout.ms là giới hạn broker cho transaction timeout mà client yêu cầu. Nếu client cấu hình transaction.timeout.ms vượt giới hạn broker, producer có thể bị từ chối khi khởi tạo transaction.

Không tăng timeout chỉ để che giấu transaction bị treo. Trước tiên hãy xác định thời gian xử lý batch, thời gian chờ downstream và nguyên nhân transaction kéo dài.

## 9. Ví dụ transaction cơ bản bằng KafkaProducer

Producer cần gọi initTransactions một lần, sau đó bao các record liên quan trong begin/commit hoặc abort:

~~~java
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.errors.ProducerFencedException;
import org.apache.kafka.common.KafkaException;

public class OrderTransactionExample {

    public static void publishOrder(
            KafkaProducer<String, String> producer,
            String orderId,
            String orderEvent,
            String auditEvent) {

        producer.beginTransaction();
        try {
            producer.send(new ProducerRecord<>("orders", orderId, orderEvent));
            producer.send(new ProducerRecord<>("orders-audit", orderId, auditEvent));
            producer.commitTransaction();
        } catch (ProducerFencedException ex) {
            // Producer đã mất ownership. Không tiếp tục dùng instance này.
            producer.close();
            throw ex;
        } catch (KafkaException ex) {
            // Hàm phân loại dưới đây là logic ứng dụng, dựa trên exception
            // semantics của phiên bản Kafka client đang sử dụng.
            if (isAbortableTransactionError(ex)) {
                producer.abortTransaction();
            } else {
                producer.close();
            }
            throw ex;
        }
    }
}
~~~

Khởi tạo:

~~~java
KafkaProducer<String, String> producer =
    TransactionalProducerFactory.create("0");

producer.initTransactions();

try {
    publishOrder(
        producer,
        "order-42",
        "{\"status\":\"PAID\"}",
        "{\"action\":\"ORDER_PAID\"}"
    );
} finally {
    producer.close();
}
~~~

Đây là skeleton minh họa; isAbortableTransactionError là helper do ứng dụng định nghĩa, không phải API Kafka. Trong ứng dụng production, cần phân loại lỗi abortable và fatal theo Kafka client version. Nếu abortTransaction cũng lỗi vì producer đã bị fencing hoặc gặp lỗi fatal, phải đóng producer và để logical owner hiện tại khởi tạo instance mới. Không gọi abort mù quáng sau mọi exception.

## 10. Consume-transform-produce và fencing

Một pattern phổ biến là consumer đọc record từ topic input, transform rồi producer ghi output. Nếu output được commit nhưng input offset chưa commit, consumer có thể đọc lại input và ghi output lần nữa. Kafka transaction cho phép commit output record và input offset trong cùng transaction.

Luồng:

1. Consumer poll input record.
2. Producer beginTransaction.
3. Producer gửi output record.
4. Producer gửi input offset vào transaction bằng sendOffsetsToTransaction.
5. Producer commitTransaction.
6. Consumer downstream dùng read_committed để chỉ nhìn thấy output đã commit.

~~~mermaid
sequenceDiagram
    participant C as Input consumer
    participant P as Transactional producer
    participant TC as Transaction coordinator
    participant K as Kafka partitions
    C->>K: Fetch input records
    P->>TC: beginTransaction
    P->>K: Produce output records
    P->>TC: sendOffsetsToTransaction
    TC->>K: Prepare/commit transaction markers
    TC-->>P: Commit result
    Note over K: Output và input offset cùng transaction
~~~

### 10.1. Cấu hình consumer input

~~~java
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.ISOLATION_LEVEL_CONFIG, "read_committed");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "order-transformer");
~~~

read_committed phù hợp khi input topic có thể chứa transactional records và ứng dụng chỉ muốn xử lý dữ liệu đã commit. Với input topic không dùng transaction, isolation level này vẫn hoạt động nhưng có thể có chi phí/giới hạn đọc theo LSO.

### 10.2. Gửi offset vào transaction

~~~java
producer.beginTransaction();
try {
    for (ConsumerRecord<String, String> record : records) {
        String transformed = transform(record.value());
        producer.send(new ProducerRecord<>(
            "orders-processed",
            record.key(),
            transformed
        ));
    }

    Map<TopicPartition, OffsetAndMetadata> offsets = currentNextOffsets(records);
    producer.sendOffsetsToTransaction(offsets, consumer.groupMetadata());
    producer.commitTransaction();
} catch (ProducerFencedException ex) {
    producer.close();
    throw ex;
} catch (KafkaException ex) {
    if (isAbortableTransactionError(ex)) {
        producer.abortTransaction();
    } else {
        producer.close();
    }
    throw ex;
}
~~~

isAbortableTransactionError cũng là helper ứng dụng; chỉ abort khi client còn cho phép tiếp tục sau khi hủy transaction. Với lỗi fatal hoặc fencing, đóng producer và dừng logical worker.

currentNextOffsets là hàm ứng dụng cần tính offset tiếp theo đã xử lý an toàn theo từng partition. Không lấy offset lớn nhất của batch một cách tùy tiện nếu xử lý song song hoặc có record thất bại ở giữa; chỉ commit qua phần liên tục đã xử lý thành công.

Trong mô hình này, consumer không commit offset độc lập bằng commitSync. Offset input được đưa vào Kafka transaction của producer.

## 11. Producer bị fencing thì xử lý thế nào?

Khi nhận ProducerFencedException, producer instance không còn là owner. Đây không phải lỗi transient để retry trên cùng object.

Quy trình:

1. Dừng nhận công việc mới trên worker bị fencing.
2. Đánh dấu producer instance không còn sử dụng được.
3. Đóng producer cũ.
4. Kiểm tra transactional ID có bị trùng giữa các instance không.
5. Chỉ logical owner hiện tại được phép khởi tạo producer mới với ID đó.
6. Nếu worker cũ vẫn được hệ thống điều phối xem là hoạt động, xử lý ownership/lease ở tầng ứng dụng trước khi khởi động lại.

Không tự động tạo một transactional ID ngẫu nhiên mới khi gặp fencing để né lỗi. Làm vậy có thể khiến hai logical producer cùng xử lý một công việc dưới hai ID khác nhau và làm mất ý nghĩa fencing.

### 11.1. Phân biệt producer fencing với consumer group fencing

Kafka có các cơ chế fencing khác nhau:

- Producer fencing dựa trên transactional ID và producer epoch.
- Static consumer membership có group.instance.id và có thể phát hiện member ID trùng/fenced.
- Consumer group generation/epoch bảo vệ quyền commit offset của member theo trạng thái group.

Các cơ chế này phục vụ đối tượng khác nhau. ProducerFencedException không phải lỗi group membership và không nên xử lý bằng cách đổi group ID.

## 12. Spring Kafka và transactional.id prefix

Spring Kafka hỗ trợ transaction thông qua DefaultKafkaProducerFactory, KafkaTemplate và KafkaTransactionManager. Khi cấu hình transaction ID prefix, producer factory tạo transactional ID cụ thể bằng cách ghép prefix với suffix do factory quản lý.

Ví dụ application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      transaction-id-prefix: prod-order-transformer-0-
      properties:
        transaction.timeout.ms: 60000
        enable.idempotence: true
    consumer:
      properties:
        isolation.level: read_committed
~~~

Prefix phải duy nhất giữa các application instance đang chạy đồng thời, đồng thời ổn định cho cùng logical instance qua restart để fencing có ý nghĩa. Ví dụ prod-order-transformer-0- dành cho shard 0; shard 1 cần prefix khác.

### 12.1. KafkaTemplate.executeInTransaction

Ví dụ gửi hai record trong cùng transaction:

~~~java
String result = kafkaTemplate.executeInTransaction(operations -> {
    operations.send("orders", orderId, orderEvent);
    operations.send("orders-audit", orderId, auditEvent);
    return "published";
});
~~~

Nếu callback hoàn tất bình thường, transaction được commit. Nếu callback ném exception, transaction được abort theo cơ chế của Spring Kafka. Ứng dụng cần xử lý exception ở tầng gọi và không coi việc gọi send() là bằng chứng transaction đã commit; kết quả cuối cùng phụ thuộc việc transaction hoàn tất.

### 12.2. KafkaTransactionManager

Có thể cấu hình KafkaTransactionManager từ ProducerFactory để tích hợp transaction với listener container hoặc Spring transaction infrastructure:

~~~java
@Bean
KafkaTransactionManager<String, String> kafkaTransactionManager(
        ProducerFactory<String, String> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Với listener container được cấu hình Kafka transaction manager, container có thể bắt đầu transaction trước khi gọi listener và commit khi listener thành công. Nếu listener ném exception, transaction được rollback/abort theo cấu hình error handler.

Spring transaction synchronization giữa Kafka và database không tự biến chúng thành một distributed atomic transaction. Nếu cần đồng bộ database và Kafka bền vững, dùng transactional outbox/inbox hoặc giải pháp phù hợp với hệ thống dữ liệu.

## 13. Theo dõi transaction và fencing

Các dấu hiệu nên giám sát:

- Số lần ProducerFencedException theo service/instance.
- Tỷ lệ transaction commit và abort.
- Thời gian transaction mở và thời gian commit.
- Transaction timeout và coordinator unavailable.
- Lỗi khi khởi tạo producer hoặc gọi initTransactions.
- Sức khỏe leader/ISR của __transaction_state.
- Producer restart, container restart và deployment overlap.
- Số lượng logical worker cùng tranh chấp một transactional ID.

Nếu fencing tăng đột biến sau deployment, kiểm tra transaction-id-prefix có bị dùng chung giữa các replica không. Nếu transaction timeout tăng, đo thời gian xử lý batch và downstream latency trước khi tăng timeout.

### 13.1. Kiểm tra internal topic và broker log

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic __transaction_state
~~~

Kiểm tra broker log để tìm transaction coordinator movement, transaction timeout, producer fencing và lỗi replication của internal topic. Không đọc hoặc ghi trực tiếp dữ liệu nhị phân trong __transaction_state để sửa transaction.

## 14. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| ProducerFencedException ngay sau startup | Một producer khác đang dùng cùng transactional.id | Tìm instance trùng ID, bảo đảm prefix/ID duy nhất |
| Producer cũ tiếp tục ghi rồi bị fencing | Instance mới đã tiếp quản logical producer | Dừng worker cũ, kiểm tra orchestrator/lease và lifecycle |
| initTransactions timeout | Coordinator unavailable, internal topic lỗi hoặc network | Kiểm tra coordinator, __transaction_state, broker và network |
| Transaction timeout | Transaction mở quá lâu hoặc batch xử lý chậm | Giảm batch, tối ưu xử lý, kiểm tra transaction.timeout.ms |
| Transaction bị abort liên tục | Exception trong xử lý, producer fencing hoặc timeout | Phân loại nguyên nhân, kiểm tra producer epoch và log coordinator |
| Consumer read_committed bị đứng ở một partition | Có transaction đang mở khiến LSO chưa tiến lên | Tìm producer transaction chưa commit/abort và transaction timeout |
| Spring Kafka các instance fencing lẫn nhau | transaction-id-prefix bị dùng chung | Tạo prefix duy nhất theo logical instance |
| Output xuất hiện thiếu một phần | Consumer dùng read_uncommitted hoặc transaction bị abort | Kiểm tra isolation.level và trạng thái transaction |
| Internal transaction topic thiếu ISR | Broker down hoặc replica lag | Khôi phục broker/replica và kiểm tra replication factor |

## 15. Bài tập thực hành

### Bài tập 1: Quan sát producer epoch và fencing

1. Tạo một producer với transactional.id ổn định lab-transformer-0.
2. Gọi initTransactions và gửi một transaction.
3. Khởi chạy producer thứ hai với cùng transactional.id trong một process khác.
4. Gọi initTransactions trên producer thứ hai.
5. Thử gửi/commit bằng producer cũ và quan sát ProducerFencedException.
6. Giải thích vì sao producer cũ không thể tiếp tục sử dụng instance hiện tại.

Chỉ thực hiện bài tập trên cluster lab. Không dùng transactional ID của ứng dụng production.

### Bài tập 2: Chọn transactional ID cho nhiều replica

Thiết kế transactional ID cho service có bốn logical shard. Yêu cầu:

- Mỗi shard có thể restart mà vẫn fencing process cũ.
- Các shard chạy song song không fencing lẫn nhau.
- Staging và production không đụng ID khi dùng chung cluster.

Viết quy tắc tạo ID và mô phỏng một lần rolling restart.

### Bài tập 3: Consume-transform-produce

1. Tạo input topic và output topic.
2. Cấu hình consumer tắt auto commit.
3. Cấu hình producer có transactional.id.
4. Poll một batch, transform record, gửi output và gửi input offset vào transaction.
5. Commit transaction.
6. Dùng consumer read_committed kiểm tra output.
7. Thử abort transaction và xác nhận output của transaction bị abort không được consumer read_committed nhìn thấy.

### Bài tập 4: Spring Kafka transaction

1. Cấu hình transaction-id-prefix duy nhất cho instance.
2. Dùng KafkaTemplate.executeInTransaction gửi hai record.
3. Ném exception giữa callback để quan sát abort.
4. Dùng consumer read_committed kiểm tra kết quả.
5. Khởi chạy hai instance dùng cùng prefix trong lab để quan sát fencing.

## 16. Câu hỏi tự kiểm tra

1. transactional.id khác client.id ở điểm nào?
2. Producer ID và producer epoch được Kafka dùng để làm gì?
3. Transaction coordinator lưu trạng thái transaction ở internal topic nào?
4. Vì sao producer mới dùng cùng transactional.id có thể fencing producer cũ?
5. Khi nào transactional.id cần ổn định qua restart?
6. Vì sao các replica chạy song song phải có transactional ID khác nhau?
7. ProducerFencedException có nên retry trên cùng producer instance không?
8. Idempotent producer khác transactional producer như thế nào?
9. transaction.timeout.ms và transaction.max.timeout.ms liên quan ra sao?
10. Vì sao consumer read_committed có thể bị chặn bởi transaction chưa kết thúc?
11. Kafka transaction có tự bảo đảm atomicity với database ngoài Kafka không?
12. Spring Kafka dùng transaction-id-prefix để tạo transactional ID cho producer như thế nào?

Khi thiết kế transactional ID đúng theo logical producer, Kafka có thể dùng producer epoch để loại bỏ process cũ, bảo vệ quyền điều khiển transaction và hỗ trợ khôi phục an toàn sau restart hoặc failover.
