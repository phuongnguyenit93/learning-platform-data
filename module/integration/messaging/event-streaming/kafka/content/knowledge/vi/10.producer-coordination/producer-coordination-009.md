# enable.idempotence, producer ID và sequence number

Kafka producer có thể phải gửi lại một Produce request khi broker đã ghi record nhưng acknowledgement bị mất trên đường truyền. Nếu lần gửi lại được xem như một yêu cầu mới, cùng một record có thể được append lần thứ hai. Idempotent producer giải quyết tình huống retry này bằng cách gắn định danh producer và sequence number vào các record batch để broker nhận diện lần gửi trùng.

Ba thành phần cần hiểu là:

- **enable.idempotence:** bật cơ chế gửi idempotent ở producer.
- **Producer ID (PID) và producer epoch:** nhận diện producer session và thế hệ producer.
- **Sequence number:** đánh số record theo từng producer và từng partition để broker phát hiện duplicate hoặc request sai thứ tự.

Cơ chế này tăng độ tin cậy của việc gửi khi gặp retry. Nó không tự bảo đảm một event nghiệp vụ chỉ xuất hiện một lần qua nhiều lần ứng dụng khởi động, nhiều producer độc lập hoặc nhiều hệ thống bên ngoài Kafka.

## 1. Vấn đề duplicate khi producer retry

Giả sử ứng dụng gửi event `OrderPaid` đến topic `orders`:

1. Producer gửi Produce request đến partition leader.
2. Broker append record vào partition log.
3. Broker gửi acknowledgement về producer.
4. Kết nối mạng bị đứt trước khi producer nhận được acknowledgement.
5. Producer không biết broker đã ghi thành công hay chưa và phải retry.

Nếu broker append request retry như một record mới, log có thể chứa hai bản ghi giống nhau. Ứng dụng nhìn thấy lỗi timeout nhưng thực tế record đầu tiên có thể đã được ghi.

~~~mermaid
sequenceDiagram
    participant P as Idempotent producer
    participant B as Partition leader

    P->>B: Produce batch (PID, epoch, sequence)
    B->>B: Append batch
    B--xP: Acknowledgement bị mất
    P->>B: Retry cùng batch, cùng sequence
    B->>B: Kiểm tra producer state
    B-->>P: Nhận diện duplicate, trả kết quả phù hợp
~~~

Nếu producer gửi lại cùng batch với cùng định danh và sequence, broker có thể nhận diện request đó là retry của dữ liệu đã append. Broker không append thêm một bản sao mới cho cùng sequence đã được chấp nhận.

Đây là vấn đề mà idempotent producer xử lý. Nó không dựa vào việc so sánh nội dung key/value để đoán hai record có giống nhau hay không.

## 2. Idempotence là gì?

Một thao tác idempotent có thể được thực hiện lại mà không làm thay đổi kết quả đã đạt được sau lần thực hiện đầu tiên. Trong Kafka producer, điều đó có nghĩa retry nội bộ của cùng một lần gửi không tạo thêm bản ghi trùng trong partition log.

Producer thực hiện điều này bằng cách gắn metadata giao thức vào record batch:

- PID xác định producer.
- Epoch xác định thế hệ của producer.
- Sequence number xác định vị trí batch/record trong chuỗi gửi của producer đến một partition.

Broker dùng metadata đó để kiểm tra request trước khi append. Nếu sequence đã được ghi nhận, broker biết đây là duplicate; nếu sequence không đúng thứ tự, broker có thể từ chối request.

Idempotence được áp dụng riêng cho từng producer và partition. Hai producer độc lập gửi cùng một JSON với cùng key vẫn là hai nguồn gửi khác nhau và có thể tạo hai record. Kafka không tự hiểu rằng hai payload đó là cùng một giao dịch nghiệp vụ.

## 3. Producer ID (PID) và producer epoch

### 3.1. Producer ID được cấp như thế nào?

Producer ID là định danh nội bộ do Kafka cấp cho producer. Khi cần khởi tạo trạng thái idempotent, producer trao đổi với broker bằng giao thức khởi tạo producer ID (InitProducerId). Broker cấp PID để nhận diện producer trong quá trình gửi.

PID không phải:

- `client.id` mà người vận hành đặt trong cấu hình.
- `group.id` của consumer.
- Key của record.
- Event ID của nghiệp vụ.
- Offset của partition.

PID được client Kafka quản lý nội bộ. Ứng dụng thông thường không tự tạo PID hoặc gắn PID vào payload.

### 3.2. Epoch biểu thị thế hệ producer

Producer epoch là số thế hệ gắn với PID. Nó giúp broker nhận biết một producer generation cũ đã bị thay thế hoặc không còn quyền ghi trong một số tình huống điều phối producer.

Điều này đặc biệt quan trọng với transactional producer. Khi một producer mới khởi tạo với cùng `transactional.id`, broker có thể tăng epoch và fence producer cũ đang dùng cùng định danh logic. Producer cũ sau đó không còn được phép tiếp tục ghi như chủ thể hiện hành.

Có thể hình dung:

| Thành phần | Vai trò |
|---|---|
| Producer ID | Nhận diện producer ở tầng giao thức |
| Producer epoch | Phân biệt thế hệ của producer |
| `transactional.id` | Định danh logic ổn định do ứng dụng cấu hình cho transactional producer |
| `client.id` | Nhãn phục vụ log, metric và quan sát |

Không cần cấu hình `transactional.id` chỉ để bật idempotence. Producer idempotent thông thường vẫn dùng PID do broker cấp, nhưng không có cơ chế giao dịch nhiều partition và fencing theo transactional ID như transactional producer.

### 3.3. Điều gì xảy ra khi producer khởi động lại?

Với producer idempotent không có `transactional.id`, một instance mới thường nhận PID mới. Sequence number bắt đầu một chuỗi mới theo PID mới. Nếu ứng dụng tự gửi lại cùng một event nghiệp vụ sau khi khởi động lại, broker có thể xem đó là lần gửi mới vì PID/sequence đã khác.

Transactional producer dùng `transactional.id` ổn định có thể khôi phục định danh logic và tăng epoch để fence instance cũ. Tuy nhiên, fencing không tự khử một event mà ứng dụng chủ động gửi lại trong transaction mới. Vẫn cần event ID hoặc cơ chế idempotency ở tầng nghiệp vụ nếu phải chống trùng qua restart.

## 4. Sequence number được dùng như thế nào?

Sequence number là số thứ tự nội bộ mà producer gắn cho record khi gửi đến một partition. Chuỗi sequence được quản lý theo tổ hợp producer identity và partition, không phải một bộ đếm toàn cục cho toàn topic hoặc toàn cluster.

Ví dụ một producer có PID 7001 gửi vào hai partition:

| Partition | Sequence number minh họa |
|---|---|
| orders-0 | 0, 1, 2, 3, 4 |
| orders-1 | 0, 1, 2 |
| payments-0 | 0, 1 |

Mỗi partition có chuỗi riêng. Việc sequence ở `orders-0` là 4 không có nghĩa sequence ở `orders-1` phải là 5.

Producer gửi batch chứa sequence tương ứng. Broker giữ trạng thái producer theo partition để xác định sequence tiếp theo hợp lệ và nhận diện batch đã được ghi trước đó.

### 4.1. Retry dùng lại sequence

Giả sử producer gửi batch đến `orders-0`:

| Lần gửi | PID | Epoch | Sequence của batch | Kết quả |
|---|---:|---:|---:|---|
| Gửi đầu | 7001 | 0 | 10–12 | Broker append |
| Retry do mất acknowledgement | 7001 | 0 | 10–12 | Broker nhận diện batch đã ghi |
| Batch tiếp theo | 7001 | 0 | 13–14 | Broker append record mới |

Điểm quan trọng là retry của cùng batch giữ nguyên sequence. Nếu producer đánh số lại batch retry thành sequence mới, broker sẽ không thể nhận diện nó là cùng lần gửi trước.

### 4.2. Sequence không phải offset

Sequence number và offset có ý nghĩa khác nhau:

| Tiêu chí | Sequence number | Partition offset |
|---|---|---|
| Được dùng để | Nhận diện thứ tự gửi của một producer | Định vị record trong partition log |
| Phạm vi | Một PID/epoch trên một partition | Một partition |
| Ai quản lý | Producer tạo và broker xác thực | Broker gán khi append |
| Có dùng chung giữa nhiều producer? | Không | Có, mọi record trong partition dùng cùng không gian offset |
| Ứng dụng thường sử dụng trực tiếp? | Thường không | Có, consumer đọc và commit offset |

Nếu hai producer khác nhau ghi vào cùng partition, mỗi producer có sequence riêng nhưng record của cả hai vẫn nhận offset trong cùng partition log.

## 5. Broker phát hiện duplicate và sai thứ tự ra sao?

Broker kiểm tra PID, epoch và sequence của batch trước khi append. Với mỗi partition, broker duy trì trạng thái producer cần thiết để biết sequence đã nhận gần nhất và xác thực request tiếp theo.

Có ba trường hợp cơ bản:

1. **Sequence mới hợp lệ:** batch tiếp theo đúng chuỗi, broker có thể append.
2. **Sequence đã được chấp nhận trước đó:** broker nhận diện retry/duplicate và không append thêm bản sao.
3. **Sequence không hợp lệ hoặc sai thứ tự:** broker trả lỗi giao thức phù hợp, ví dụ out-of-order sequence hoặc producer epoch không còn hợp lệ.

Broker không deduplicate bằng cách đọc và so sánh toàn bộ JSON. Nếu ứng dụng gọi `send()` hai lần cho cùng event nhưng hai lần gửi có sequence khác nhau, broker sẽ xem đó là hai record mới.

Điều này giải thích vì sao idempotence bảo vệ retry do producer client quản lý, còn duplicate do logic ứng dụng cần được xử lý riêng.

## 6. Cấu hình enable.idempotence

Ví dụ cấu hình rõ ràng cho Kafka Java producer:

~~~properties
bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092
key.serializer=org.apache.kafka.common.serialization.StringSerializer
value.serializer=org.apache.kafka.common.serialization.StringSerializer
client.id=orders-producer
enable.idempotence=true
acks=all
retries=10
max.in.flight.requests.per.connection=5
~~~

Các thuộc tính liên quan:

| Thuộc tính | Vai trò | Điều kiện khi bật idempotence |
|---|---|---|
| `enable.idempotence` | Bật cơ chế PID/sequence và dedup retry | Đặt `true` |
| `acks` | Mức acknowledgement | Phải là `all` |
| `retries` | Số lần producer thử lại lỗi có thể retry | Phải lớn hơn 0 |
| `max.in.flight.requests.per.connection` | Số request chưa nhận response trên một kết nối | Không lớn hơn 5 |

Với Kafka client hiện đại, idempotence được bật mặc định khi các cấu hình liên quan tương thích; các phiên bản cũ có thể có mặc định khác. Khai báo tường minh giúp cấu hình và ý định của ứng dụng dễ kiểm tra.

Nếu bật idempotence nhưng đồng thời đặt `acks` không phải `all`, `retries=0` hoặc `max.in.flight.requests.per.connection` lớn hơn giới hạn, producer có thể từ chối cấu hình khi khởi tạo. Hãy kiểm tra tài liệu của phiên bản `kafka-clients` đang sử dụng.

### 6.1. Vì sao max.in.flight.requests.per.connection bị giới hạn?

Producer có thể gửi nhiều request mà chưa chờ response của request trước. Điều đó giúp tăng throughput. Tuy nhiên, nếu request trước lỗi và cần retry trong khi request sau đã thành công, thứ tự có thể trở nên phức tạp.

Idempotent producer dùng sequence number và cơ chế kiểm tra ở broker để giữ tính đúng đắn trong giới hạn được Kafka hỗ trợ. Với các client hiện đại, tối đa 5 request chưa hoàn tất trên mỗi kết nối được hỗ trợ khi idempotence bật.

Không nên tăng giá trị này vượt giới hạn chỉ để ép throughput. Hãy đo batching, linger, compression, partition distribution và network trước khi thay đổi cấu hình.

## 7. Ví dụ Java producer bật idempotence

Ví dụ sau dùng `StringSerializer`, `acks=all` và idempotence. Ứng dụng tạo một producer và tái sử dụng nó thay vì tạo mới cho từng record.

~~~java
import java.util.Properties;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

public class IdempotentOrderProducer {

    public static void main(String[] args) {
        Properties props = new Properties();

        props.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        props.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        props.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );

        props.put(ProducerConfig.CLIENT_ID_CONFIG, "orders-producer");
        props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        props.put(ProducerConfig.ACKS_CONFIG, "all");
        props.put(ProducerConfig.RETRIES_CONFIG, 10);
        props.put(
            ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
            5
        );

        try (KafkaProducer<String, String> producer =
                 new KafkaProducer<>(props)) {

            ProducerRecord<String, String> record =
                new ProducerRecord<>(
                    "orders",
                    "order-123",
                    """
                    {
                      "eventId": "evt-1001",
                      "eventType": "OrderPaid",
                      "orderId": "order-123"
                    }
                    """
                );

            producer.send(record, (metadata, exception) -> {
                if (exception != null) {
                    System.err.println(
                        "Send failed: " + exception.getMessage()
                    );
                    return;
                }

                System.out.printf(
                    "topic=%s partition=%d offset=%d%n",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
                );
            });

            producer.flush();
        }
    }
}
~~~

Các điểm cần chú ý:

- `eventId` trong JSON là định danh nghiệp vụ do ứng dụng tạo; nó khác PID và sequence number nội bộ của Kafka.
- Producer giữ cùng PID/sequence cho các lần retry nội bộ theo protocol.
- `flush()` chờ các lần gửi đang chờ hoàn tất trước khi đóng trong ví dụ ngắn.
- Trong service chạy lâu dài, tạo producer ở lifecycle ứng dụng và tái sử dụng; không flush sau từng record.
- `retries=10` là giá trị minh họa. Tổng thời gian giao record vẫn chịu giới hạn `delivery.timeout.ms`.

## 8. Idempotence khác gì transactional producer?

Idempotent producer và transactional producer có liên quan nhưng giải quyết các phạm vi khác nhau.

| Cơ chế | Bảo đảm chính | Cần cấu hình |
|---|---|---|
| Idempotent producer | Retry nội bộ không tạo duplicate do cùng batch được gửi lại | `enable.idempotence=true` |
| Transactional producer | Nhóm nhiều thao tác Kafka có thể commit hoặc abort như một transaction; hỗ trợ fencing producer generation | `transactional.id`, `initTransactions()`, begin/commit/abort |
| Idempotent consumer/nghiệp vụ | Cùng một event nghiệp vụ được xử lý lặp mà không tạo side effect lặp | Event ID, unique constraint hoặc idempotency key |

Chỉ bật idempotence không cần khai báo `transactional.id`. Nếu cần ghi atomically vào nhiều partition hoặc kết hợp việc đọc offset với ghi output trong Kafka, hãy xem xét Kafka transactions.

Ví dụ khởi tạo transactional producer:

~~~java
props.put(
    ProducerConfig.TRANSACTIONAL_ID_CONFIG,
    "orders-publisher-instance-1"
);

KafkaProducer<String, String> producer =
    new KafkaProducer<>(props);

producer.initTransactions();

try {
    producer.beginTransaction();

    producer.send(orderRecord);
    producer.send(auditRecord);

    producer.commitTransaction();
} catch (Exception exception) {
    producer.abortTransaction();
    throw exception;
}
~~~

Đây là ví dụ minh họa rút gọn; ứng dụng thực tế cần xử lý các exception transaction, timeout, fencing và lifecycle producer theo đúng phiên bản client.

Transactional ID phải được quản lý có chủ đích:

- Các instance chạy đồng thời cần transactional ID riêng nếu chúng là các logical producer độc lập.
- Khi một instance khởi động lại để thay thế cùng logical producer, dùng lại ID đó có thể fence instance cũ thông qua epoch mới.
- Hai instance độc lập không được vô tình dùng chung transactional ID, vì instance mới có thể làm instance cũ mất quyền gửi.
- Consumer muốn chỉ đọc dữ liệu transaction đã commit cần dùng `isolation.level=read_committed`.

Transaction Kafka không tự bao gồm transaction database hoặc HTTP service. Nếu ghi database và gửi Kafka phải nguyên tử với nhau, cần thiết kế outbox hoặc cơ chế phối hợp tương ứng.

## 9. Những gì idempotent producer bảo đảm và không bảo đảm

| Tình huống | Idempotence xử lý? | Giải thích |
|---|---|---|
| Broker đã append batch nhưng response bị mất, producer retry cùng batch | Có | Cùng PID/epoch/sequence giúp broker nhận diện duplicate |
| Request retry do lỗi mạng trong cùng producer session | Có, trong phạm vi cơ chế retry được hỗ trợ | Client giữ metadata gửi phù hợp |
| Ứng dụng gọi send() hai lần cho cùng payload | Không | Hai lần gọi là hai record với sequence khác nhau |
| Ứng dụng khởi động lại và tự gửi lại event cũ với PID mới | Không tự động | PID mới bắt đầu chuỗi sequence mới |
| Hai service độc lập gửi cùng event | Không | Mỗi producer có định danh và chuỗi riêng |
| Consumer thực hiện side effect hai lần | Không | Cần idempotent consumer hoặc event ID |
| Ghi nhiều partition phải commit nguyên tử | Không chỉ bằng idempotence | Cần transactional producer |
| Ghi Kafka và database trong cùng transaction | Không | Kafka transaction không bao trùm transaction database thông thường |

Vì vậy, một hệ thống nghiệp vụ thường kết hợp nhiều lớp:

1. Producer idempotence để xử lý retry giao thức.
2. Event ID ổn định để nhận diện event nghiệp vụ.
3. Transactional outbox để không mất event giữa database commit và publish.
4. Consumer idempotency để bảo vệ side effect khi record được phát lại.
5. Kafka transaction khi cần atomicity giữa các thao tác bên trong Kafka.

## 10. Ordering và nhiều partition

Sequence number được quản lý riêng theo producer và partition. Nó không tạo thứ tự toàn cục giữa các partition.

Nếu producer gửi event cùng `orderId` vào cùng partition, Kafka có thể duy trì thứ tự append của các event đó trong partition. Idempotence giúp retry không làm đảo thứ tự trong các điều kiện cấu hình hỗ trợ.

Nếu record được phân phối sang các partition khác nhau, sequence của partition này không so sánh trực tiếp với sequence của partition kia. Nếu nghiệp vụ cần thứ tự theo đơn hàng, dùng `orderId` làm key và bảo đảm các producer dùng cùng quy tắc partitioning.

Khi có nhiều producer độc lập cùng ghi một key, idempotence không sắp xếp thứ tự nghiệp vụ giữa các producer. Cần một nguồn phát có thẩm quyền, sequence nghiệp vụ hoặc cơ chế điều phối riêng.

## 11. Theo dõi và xử lý lỗi sequence

Một số dấu hiệu có thể xuất hiện khi producer gặp vấn đề về PID, epoch hoặc sequence:

| Dấu hiệu | Ý nghĩa có thể | Hướng xử lý |
|---|---|---|
| Retry rate tăng | Producer gặp lỗi tạm thời hoặc broker/network chậm | Kiểm tra request latency, broker và network |
| Out-of-order sequence | Broker nhận sequence không đúng trạng thái kỳ vọng | Kiểm tra producer lifecycle, cấu hình in-flight và lỗi trước đó |
| Invalid producer epoch | Epoch không còn hợp lệ với trạng thái broker | Kiểm tra transaction ID, fencing và instance trùng định danh |
| Producer fenced | Một producer khác đã tiếp quản cùng transactional ID | Kiểm tra transactional ID và quản lý instance |
| Delivery timeout | Producer không giao được record trong giới hạn thời gian | Kiểm tra broker, ISR, timeout và retry policy |

Không nên bắt mọi lỗi sequence rồi tạo producer mới ngay lập tức. Một số lỗi là fatal đối với producer hiện tại hoặc cần khôi phục transaction theo đúng quy trình. Hãy phân loại exception theo loại và hướng dẫn của phiên bản Kafka client.

Các metric hữu ích để theo dõi:

- `record-retry-rate`: tỷ lệ record phải retry.
- `record-error-rate`: tỷ lệ record gửi lỗi.
- Request latency và số request đang chờ.
- Tỷ lệ send thành công.
- Producer fencing/transaction errors nếu dùng transactional producer.
- Broker request errors và trạng thái ISR của partition.

## 12. Kiểm thử idempotent producer

Có thể xây dựng bài kiểm thử trong môi trường staging:

1. Tạo topic thử nghiệm với partition và replication phù hợp.
2. Khởi tạo producer với idempotence bật, `acks=all` và cấu hình in-flight hợp lệ.
3. Gửi một chuỗi event có event ID riêng, ghi lại metadata partition/offset.
4. Tạo lỗi mạng tạm thời trong lúc producer đang gửi để kích hoạt retry.
5. Khôi phục mạng và chờ producer hoàn tất hoặc trả lỗi cuối cùng.
6. Đọc topic từ đầu và kiểm tra các event ID, partition và offset.
7. So sánh với số event ứng dụng đã gửi, đồng thời phân biệt retry nội bộ với việc ứng dụng gọi send() lần thứ hai.
8. Khởi động lại producer và thử gửi lại event ID cũ để xác minh rằng event ID nghiệp vụ cần cơ chế chống trùng riêng.
9. Nếu dùng transactional ID, chạy thử hai instance cùng ID để quan sát fencing và xác minh instance cũ không tiếp tục ghi.

Không nên dựa vào việc gửi hai lần cùng payload để chứng minh idempotence. Hai lần gọi send() là hai thao tác mới; bài test phải tạo retry của cùng một lần gửi hoặc mô phỏng lỗi response sau khi broker đã nhận request.

## 13. Checklist cấu hình producer idempotent

- [ ] `enable.idempotence=true` được bật rõ ràng hoặc xác nhận mặc định của client.
- [ ] `acks=all`.
- [ ] `retries` lớn hơn 0 và delivery timeout phù hợp.
- [ ] `max.in.flight.requests.per.connection` không vượt 5.
- [ ] Producer được tái sử dụng đúng lifecycle.
- [ ] Không nhầm PID với client ID, transactional ID hoặc event ID.
- [ ] Hiểu sequence number được quản lý riêng theo producer và partition.
- [ ] Phân biệt retry nội bộ với việc ứng dụng gửi lại event.
- [ ] Có event ID và consumer idempotency cho nghiệp vụ cần chống trùng qua restart.
- [ ] Chỉ dùng transactional ID khi cần transaction/fencing và quản lý ID theo logical producer.
- [ ] Theo dõi retry, error, latency và lỗi sequence/fencing.
- [ ] Đã kiểm thử retry khi có lỗi mạng và kiểm tra record thực tế trong topic.

Idempotent producer giúp Kafka nhận diện retry của cùng một lần gửi thông qua PID, epoch và sequence number. Producer tạo sequence riêng cho từng partition; broker xác thực chuỗi này để tránh append trùng khi acknowledgement bị mất. Cơ chế chỉ bảo vệ retry trong phạm vi producer protocol. Muốn chống trùng qua restart, nhiều producer hoặc side effect bên ngoài Kafka, hệ thống vẫn cần event ID, outbox, idempotent consumer hoặc transaction phù hợp.
