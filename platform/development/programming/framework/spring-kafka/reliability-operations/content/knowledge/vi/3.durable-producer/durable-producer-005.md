# retries và retry backoff

Producer Kafka gửi record qua mạng tới broker. Trong lúc gửi, kết nối có thể bị gián đoạn, broker có thể đang bầu leader mới, partition có thể tạm thời không có đủ replica trong ISR, hoặc request có thể hết thời gian chờ. Nếu mọi lỗi đều làm ứng dụng bỏ message ngay lập tức, hệ thống sẽ dễ mất khả năng phục hồi trước các sự cố ngắn. Retry cho phép producer thử lại các lỗi có thể phục hồi; retry backoff tạo khoảng chờ giữa các lần thử để tránh gây thêm tải lên broker và mạng đang gặp sự cố.

Trong Spring Kafka, việc gửi message thường đi qua `KafkaTemplate`, nhưng cơ chế retry ở tầng producer chủ yếu do Kafka Java client thực hiện. Spring Kafka cung cấp cấu hình, tích hợp với Spring và kết quả gửi bất đồng bộ để ứng dụng theo dõi thành công hoặc thất bại. Cần phân biệt retry nội bộ của Kafka producer với việc ứng dụng gọi `send()` lại, và với retry topic của consumer. Ba cơ chế này xử lý những tình huống khác nhau.

## 1. Retry ở producer giải quyết vấn đề gì?

Một lần gửi Kafka không phải lúc nào cũng hoàn tất ngay. Producer có thể gặp những lỗi tạm thời như:

- Broker leader của partition đang thay đổi sau khi node gặp sự cố.
- Kết nối TCP bị reset hoặc tạm thời không tới được broker.
- Request timeout trong khi broker bận hoặc mạng có độ trễ cao.
- Partition tạm thời không đáp ứng điều kiện ISR mà producer yêu cầu.
- Metadata của topic hoặc partition cần được làm mới sau thay đổi trong cluster.

Với lỗi có thể phục hồi, Kafka producer có thể gửi lại request. Khi request thành công, record được broker xác nhận theo cấu hình `acks`. Nếu mọi lần thử đều thất bại hoặc thời gian gửi vượt giới hạn, producer hoàn tất future/callback bằng lỗi để ứng dụng xử lý.

Retry không sửa được mọi lỗi. Một payload không serialize được, topic không tồn tại do cấu hình sai, hoặc producer không có quyền ghi thường cần sửa dữ liệu hay cấu hình. Thử lại liên tục những lỗi loại này chỉ làm tăng độ trễ và log nhiễu.

Mục tiêu của retry là vượt qua lỗi tạm thời trong một ngân sách thời gian hữu hạn. Nó không phải lời bảo đảm rằng message cuối cùng chắc chắn được ghi.

## 2. Ba lớp retry cần phân biệt

| Cơ chế | Ai thực hiện? | Phạm vi | Khi nào dùng? |
|---|---|---|---|
| Kafka producer retry | Kafka Java client bên trong producer | Gửi lại request cho broker trong vòng đời lần gửi | Lỗi request được client xác định là có thể retry |
| Application-level retry | Logic ứng dụng hoặc một tiến trình dispatcher | Gọi `send()` lại sau khi lần gửi trước thất bại | Cần chính sách nghiệp vụ, lưu bền yêu cầu gửi hoặc xử lý sau khi vượt ngân sách retry nội bộ |
| Consumer retry / retry topic | Spring Kafka listener container hoặc cơ chế retry của consumer | Xử lý lại record đã được consumer nhận | Logic xử lý ở phía consumer thất bại |

Với Spring Kafka, `KafkaTemplate.send()` sử dụng producer được cấu hình từ Kafka client. Các thuộc tính như `acks`, `enable.idempotence`, `delivery.timeout.ms` và `retry.backoff.ms` là cấu hình producer client.

`@RetryableTopic`, retry topic và dead-letter topic thường dùng cho lỗi xử lý trong listener consumer. Chúng không phải cách cấu hình retry cho một lời gọi `KafkaTemplate.send()` thất bại. Nếu producer không gửi được event, event chưa được consumer nhận; cần xử lý kết quả gửi ở phía producer hoặc dùng một cơ chế lưu bền như transactional outbox.

## 3. Kafka producer retry và retry backoff

### 3.1. Retry nội bộ

Kafka producer là thành phần bất đồng bộ. Sau khi ứng dụng gọi `send()`, producer thường đưa record vào buffer, gom batch theo partition rồi gửi request đến broker. Nếu request gặp lỗi có thể retry, producer có thể thử lại theo chính sách của Kafka client.

Việc retry nội bộ có một số đặc điểm:

- Ứng dụng không cần tự gọi `send()` lại cho mỗi lỗi mạng tạm thời.
- Producer quản lý việc gửi lại request và cập nhật metadata khi cần.
- Với idempotent producer được bật và cấu hình tương thích, client có thể chống trùng do các lần retry nội bộ.
- Lần gửi vẫn có thể thất bại nếu vượt quá giới hạn thời gian giao hoặc gặp lỗi không thể retry.

Trong các phiên bản Kafka client hiện đại, `delivery.timeout.ms` là giới hạn tổng thời gian producer chờ một record được gửi thành công hoặc kết thúc bằng lỗi. Số lần retry thực tế phụ thuộc lỗi, thời gian request, backoff, batching và ngân sách thời gian này. Vì vậy, chỉ đặt một giá trị `retries` lớn không có nghĩa producer sẽ thử vô hạn.

### 3.2. Retry backoff

Backoff là khoảng chờ trước khi thực hiện lần thử tiếp theo. Nếu producer gửi request liên tục trong lúc broker đang khởi động lại hoặc leader đang được bầu, nó có thể làm tăng tải đúng vào thời điểm cluster cần phục hồi.

Backoff giúp:

- Giảm tần suất request lặp lại khi lỗi còn tồn tại.
- Cho broker và mạng thời gian phục hồi.
- Tránh nhiều producer đồng loạt retry ngay lập tức.
- Phân bổ tải retry theo thời gian thay vì tạo một đợt request dồn dập.

Kafka client cung cấp các thuộc tính liên quan:

| Thuộc tính | Vai trò |
|---|---|
| `retry.backoff.ms` | Khoảng chờ cơ sở trước khi retry request thất bại |
| `retry.backoff.max.ms` | Mức trần backoff trong các phiên bản client hỗ trợ thuộc tính này |
| `request.timeout.ms` | Thời gian chờ phản hồi cho một request |
| `delivery.timeout.ms` | Ngân sách thời gian tối đa để một record được gửi thành công hoặc kết thúc bằng lỗi |
| `linger.ms` | Thời gian producer có thể chờ gom thêm record vào batch trước khi gửi |

Cách tính backoff và việc hỗ trợ từng thuộc tính phụ thuộc phiên bản Kafka client. Khi nâng cấp Spring Boot hoặc Spring Kafka, hãy kiểm tra phiên bản Kafka client thực tế được dependency management kéo vào và đối chiếu tài liệu đúng phiên bản.

### 3.3. Backoff cố định và backoff tăng dần

Backoff cố định chờ cùng một khoảng thời gian sau mỗi lần thất bại. Ví dụ, nếu khoảng chờ là 200 ms thì các lần thử tiếp theo đều chờ xấp xỉ 200 ms.

Backoff tăng dần (exponential backoff) tăng thời gian chờ sau mỗi lần thất bại, thường có giới hạn tối đa. Ví dụ minh họa với mức cơ sở 200 ms và trần 3.000 ms:

| Lần retry | Khoảng chờ minh họa |
|---|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 trở đi | Tối đa 3.000 ms |

Công thức minh họa:

```text
delay(n) = min(initialDelay * multiplier^(n - 1), maxDelay)
```

Một số chiến lược còn thêm jitter, tức một lượng biến thiên ngẫu nhiên vào thời gian chờ. Jitter giúp nhiều producer không cùng thức dậy và retry ở một thời điểm sau khi gặp chung một sự cố. Công thức trên chỉ minh họa cách thiết kế backoff; không nên giả định Kafka client ở mọi phiên bản sử dụng chính xác công thức này.

### 3.4. Backoff không thay thế timeout

Backoff quyết định thời điểm thử lại. Timeout quyết định thời gian chờ một request hoặc toàn bộ lần giao record. Hai khái niệm này phối hợp với nhau.

Ví dụ, nếu `request.timeout.ms` quá ngắn so với độ trễ mạng bình thường, producer có thể liên tục kết thúc request bằng timeout và tạo thêm retry. Nếu `delivery.timeout.ms` quá ngắn, record có thể hết ngân sách trước khi broker phục hồi. Ngược lại, đặt timeout quá dài có thể khiến ứng dụng phát hiện sự cố muộn và giữ các record trong buffer lâu hơn.

Khi cấu hình, cần xét đồng thời:

- Độ trễ mạng bình thường và khi tải cao.
- Thời gian broker cần để phục hồi hoặc bầu leader.
- Thời gian chờ gom batch qua `linger.ms`.
- Số lượng record đồng thời và dung lượng buffer.
- Mức trễ tối đa mà nghiệp vụ chấp nhận.
- Thời gian chờ của request gọi vào service gửi event.

Đừng đặt các giá trị timeout chỉ để làm cho log hết lỗi. Mỗi giá trị cần phản ánh ngân sách độ trễ của luồng nghiệp vụ.

## 4. Cấu hình producer trong Spring Boot

Một cấu hình khởi đầu cho event quan trọng có thể đặt trong `application.yml`:

```yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
        "[retry.backoff.ms]": 100
        "[retry.backoff.max.ms]": 1000
        "[max.in.flight.requests.per.connection]": 5
```

Đây là ví dụ minh họa, không phải bộ giá trị phù hợp cho mọi cluster. Cần xác nhận phiên bản Kafka client có hỗ trợ các thuộc tính đang dùng và các giới hạn cấu hình tương thích với nhau.

Ý nghĩa của cấu hình:

- `acks: all` yêu cầu broker xác nhận theo ISR hiện tại. Độ bền thực tế còn phụ thuộc replication factor và `min.insync.replicas` của topic/broker.
- `enable.idempotence: true` bật cơ chế producer idempotent để chống ghi trùng do retry nội bộ trong một producer session.
- `delivery.timeout.ms` giới hạn tổng thời gian chờ giao record.
- `request.timeout.ms` giới hạn thời gian chờ phản hồi của từng request.
- `retry.backoff.ms` và `retry.backoff.max.ms` điều chỉnh khoảng chờ retry ở các Kafka client hỗ trợ chúng.
- `max.in.flight.requests.per.connection` giới hạn số request chưa nhận phản hồi trên một kết nối. Khi bật idempotence, cần giữ cấu hình tương thích với yêu cầu của Kafka client.

Nếu dùng `application.properties`, có thể biểu diễn cùng cấu hình như sau:

```properties
spring.kafka.producer.acks=all
spring.kafka.producer.properties[enable.idempotence]=true
spring.kafka.producer.properties[delivery.timeout.ms]=120000
spring.kafka.producer.properties[request.timeout.ms]=30000
spring.kafka.producer.properties[retry.backoff.ms]=100
spring.kafka.producer.properties[retry.backoff.max.ms]=1000
spring.kafka.producer.properties[max.in.flight.requests.per.connection]=5
```

Không nên sao chép nguyên các con số vào production mà không đo độ trễ và kiểm tra chính sách cluster. Đặc biệt, `acks=all` chỉ có ý nghĩa trong mối liên hệ với ISR và `min.insync.replicas`; nếu topic chỉ có một replica, mức bảo vệ khi broker mất dữ liệu vẫn hạn chế.

## 5. Idempotent producer và nguy cơ gửi trùng

Retry có thể tạo ra một tình huống khó nhận biết: broker đã ghi record nhưng phản hồi xác nhận bị mất trên đường về producer. Producer không biết chắc broker đã ghi hay chưa và có thể gửi lại request.

Kafka idempotent producer sử dụng producer ID và sequence number để broker nhận biết các lần gửi lại do retry nội bộ, từ đó tránh ghi trùng trong phạm vi producer session theo cơ chế của Kafka.

Bật idempotence là lựa chọn quan trọng với producer cần độ tin cậy cao, nhưng cần hiểu giới hạn:

- Nó xử lý duplicate phát sinh từ retry nội bộ của producer.
- Nó không tự loại bỏ hai lần ứng dụng chủ động gọi `send()` cho cùng một event nghiệp vụ.
- Nó không thay thế idempotency ở consumer khi cùng event được phát lại từ outbox hoặc một tiến trình khác.
- Nó không tạo transaction nguyên tử giữa Kafka và database bên ngoài.
- Nó không bảo đảm event không bị mất nếu ứng dụng bỏ qua lỗi gửi và không lưu lại event để thử lại.

Với event nghiệp vụ, nên có định danh ổn định như `eventId` hoặc `orderId + eventVersion`. Consumer có thể dùng định danh đó để phát hiện event đã xử lý. Định danh này cũng giúp điều tra việc publish lặp và đối chiếu dữ liệu.

Cần phân biệt idempotent producer với idempotent business operation. Producer bảo vệ việc ghi ở tầng Kafka theo cơ chế retry của client; nghiệp vụ vẫn cần xử lý an toàn khi event được phát lại từ một lần chạy ứng dụng khác.

## 6. Theo dõi kết quả gửi bằng KafkaTemplate

`KafkaTemplate.send()` trả về một kết quả bất đồng bộ. Ở các phiên bản Spring Kafka hiện đại, kiểu trả về là `CompletableFuture<SendResult<K, V>>`. Ứng dụng nên quan sát future để biết record được broker xác nhận hay gửi thất bại.

Ví dụ:

```java
@Service
public class OrderEventPublisher {

    private static final Logger log =
        LoggerFactory.getLogger(OrderEventPublisher.class);

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event
            )
            .whenComplete((result, exception) -> {
                if (exception != null) {
                    log.error(
                        "Không gửi được order event, eventId={}",
                        event.eventId(),
                        exception
                    );
                    // Chuyển sang cơ chế xử lý lỗi bền vững
                    // theo chính sách của ứng dụng.
                    return;
                }

                RecordMetadata metadata =
                    result.getRecordMetadata();

                log.info(
                    "Đã gửi order event, eventId={}, topic={}, partition={}, offset={}",
                    event.eventId(),
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
                );
            });
    }
}
```

Đây là ví dụ theo API CompletableFuture của các phiên bản Spring Kafka hiện đại. Nếu dự án dùng phiên bản cũ, kiểu future và API callback có thể khác; hãy dùng API của phiên bản dependency đang cài.

Callback giúp ghi nhận kết quả mà không chặn thread gọi `publish()`. Tuy nhiên, chỉ ghi log khi gửi thất bại là chưa đủ đối với event không được phép mất. Ứng dụng cần một nơi lưu bền event chưa gửi được, một quy trình retry có giới hạn hoặc một cơ chế cảnh báo và xử lý thủ công phù hợp.

Không nên coi việc gọi `kafkaTemplate.send()` là bằng chứng record đã được broker xác nhận. Việc gửi thường bất đồng bộ; chỉ kết quả hoàn tất thành công mới cung cấp metadata xác nhận từ broker theo cấu hình producer.

## 7. Khi nào cần application-level retry?

Nếu Kafka client đã tự retry trong ngân sách `delivery.timeout.ms`, đa số ứng dụng không cần bọc mỗi lần `send()` trong một vòng lặp retry riêng. Application-level retry chỉ nên được thêm khi có yêu cầu rõ ràng, ví dụ:

- Cần thử lại sau khi producer đã kết thúc lần gửi bằng lỗi.
- Cần giữ event qua thời gian Kafka cluster không khả dụng lâu hơn ngân sách gửi nội bộ.
- Cần lịch retry riêng theo loại nghiệp vụ.
- Cần đưa event lỗi vào hàng đợi bền vững để dispatcher xử lý sau.
- Cần giới hạn số lần thử và chuyển sang trạng thái chờ can thiệp khi hết retry.

### 7.1. Phân loại lỗi trước khi retry

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời | Mất kết nối ngắn, leader election, request timeout | Để producer retry nội bộ; sau khi thất bại mới cân nhắc retry ở ứng dụng |
| Lỗi có thể phục hồi sau thay đổi trạng thái | Topic vừa được tạo, cluster đang phục hồi | Retry có giới hạn sau khi xác minh điều kiện phục hồi |
| Lỗi cấu hình hoặc quyền | Sai bootstrap server, authentication/authorization thất bại | Dừng retry tự động kéo dài; cảnh báo và sửa cấu hình/quyền |
| Lỗi dữ liệu | Serialization exception, schema hoặc payload không hợp lệ | Sửa dữ liệu hoặc đưa vào luồng xử lý lỗi; retry cùng payload thường không giúp |
| Lỗi không rõ kết quả giao | Timeout hoặc mất kết nối ở thời điểm broker có thể đã ghi | Kiểm tra khả năng gửi trùng; dùng event ID và xử lý idempotent trước khi gửi lại |

Việc phân loại cụ thể phụ thuộc exception và phiên bản Kafka client. Không nên chỉ kiểm tra chuỗi thông báo lỗi. Hãy xem exception type, nguyên nhân gốc và trạng thái của producer.

### 7.2. Dùng retry có giới hạn

Một chính sách application-level retry cần xác định trước:

1. Những lỗi nào được phép retry.
2. Số lần retry tối đa.
3. Backoff cơ sở, hệ số tăng và thời gian chờ tối đa.
4. Tổng thời gian nghiệp vụ cho phép chờ.
5. Hành động khi hết retry: lưu trạng thái pending, đưa vào hàng đợi lỗi, cảnh báo hoặc chuyển sang xử lý thủ công.
6. Cách tránh tạo tác dụng phụ trùng khi gửi lại.

Ví dụ, một chính sách có thể thử lại tối đa bốn lần với backoff tăng dần và jitter, nhưng các con số phải dựa trên SLO và khả năng phục hồi của hệ thống. Khi hết retry, event phải còn ở trạng thái có thể khôi phục; không được chỉ xóa khỏi bộ nhớ rồi bỏ qua.

Tránh dùng `Thread.sleep()` trực tiếp trong request thread hoặc listener thread để chờ retry. Cách này chiếm thread trong lúc không làm việc, có thể làm cạn thread pool và kéo theo lỗi dây chuyền. Nếu cần retry ở tầng ứng dụng, hãy dùng scheduler hoặc một dispatcher riêng có giới hạn concurrency và hàng đợi bền vững.

### 7.3. Vì sao transactional outbox thường phù hợp hơn vòng lặp retry trong RAM?

Một vòng lặp retry trong RAM mất trạng thái khi tiến trình bị restart hoặc crash. Nếu event được tạo từ một transaction database, transactional outbox giúp ghi thay đổi nghiệp vụ và bản ghi cần publish trong cùng transaction database.

Luồng điển hình:

1. Service cập nhật dữ liệu nghiệp vụ và thêm một outbox record trong cùng transaction.
2. Dispatcher đọc các outbox record chưa gửi.
3. Dispatcher gửi event đến Kafka và chờ kết quả gửi.
4. Khi nhận xác nhận thành công, dispatcher đánh dấu outbox record đã gửi.
5. Nếu gửi thất bại, record vẫn còn để dispatcher thử lại theo backoff và chính sách đã định.

Có một khoảng trống cần xử lý: broker có thể đã ghi event nhưng dispatcher crash trước khi đánh dấu outbox record đã gửi. Khi chạy lại, dispatcher có thể gửi event lần nữa. Vì vậy, outbox thường cung cấp khả năng publish ít nhất một lần; consumer cần idempotent theo event ID để xử lý duplicate an toàn.

Outbox giải quyết việc giữ lại ý định publish qua restart và sự cố kéo dài. Nó không tự tạo exactly-once end-to-end.

## 8. Những lỗi thiết kế retry thường gặp

**Retry vô hạn ở tầng ứng dụng.** Khi cluster mất khả năng ghi, vô hạn request retry làm tăng tải, giữ tài nguyên và che khuất sự cố. Hãy đặt giới hạn thời gian, giới hạn số lần thử và đường xử lý khi hết retry.

**Retry lỗi không thể phục hồi.** Sai quyền, sai cấu hình hoặc payload không serialize được thường không thể giải quyết bằng chờ thêm. Phân loại exception và đưa lỗi cần can thiệp đến đúng nơi.

**Đặt timeout không nhất quán.** Nếu request timeout, delivery timeout và ngân sách request nghiệp vụ không được tính cùng nhau, ứng dụng có thể kết thúc request trước khi producer hoàn tất hoặc chờ lâu hơn SLA cho phép.

**Tự gửi lại ngay sau mọi future thất bại.** Một lần gửi thất bại ở phía ứng dụng có thể có kết quả giao không rõ ràng. Gửi lại như một record mới có thể tạo duplicate. Dùng event ID ổn định và idempotency ở consumer.

**Cho rằng idempotent producer bảo vệ mọi duplicate.** Cơ chế này bảo vệ retry nội bộ của Kafka producer trong phạm vi được Kafka hỗ trợ. Nó không thay thế deduplication cho lần publish độc lập do ứng dụng hoặc dispatcher tạo ra.

**Chỉ log lỗi mà không lưu event.** Nếu message quan trọng bị lỗi sau khi hết retry nội bộ, log không phải hàng đợi khôi phục. Cần outbox hoặc cơ chế lưu bền tương đương.

**Không theo dõi retry và thời gian giao.** Producer có thể gửi thành công nhưng độ trễ tăng cao do retry. Chỉ đếm số message thành công sẽ bỏ qua dấu hiệu suy giảm. Cần theo dõi cả latency, error, timeout và backlog.

## 9. Vận hành và quan sát retry

Để biết producer có đang phục hồi tốt hay đang bị mắc trong vòng retry, cần quan sát các tín hiệu ở cả ứng dụng và Kafka client.

| Tín hiệu | Điều cần quan sát | Ý nghĩa vận hành |
|---|---|---|
| Send success/failure | Số record gửi thành công và thất bại | Phân biệt lỗi gửi thực tế với log nghiệp vụ |
| Send latency | Thời gian từ lúc gửi đến khi future hoàn tất | Retry có thể làm tăng độ trễ dù cuối cùng gửi thành công |
| Request latency và timeout | Thời gian phản hồi broker, số request timeout | Phát hiện mạng hoặc broker suy giảm |
| Retry/error rate | Tỷ lệ lỗi retry được và lỗi cuối cùng | Phát hiện cluster thường xuyên cần retry |
| Buffer availability | Mức sử dụng producer buffer và thời gian chờ buffer | Phát hiện producer bị nghẽn khi broker chậm |
| Outbox backlog | Số record chưa gửi và tuổi của record cũ nhất | Đo khả năng phục hồi sau sự cố kéo dài |
| DLT hoặc failed-event queue | Số event chờ điều tra | Phát hiện lỗi không thể tự phục hồi |

Tên metric cụ thể phụ thuộc Kafka client, Spring Kafka, Micrometer và cấu hình instrumentation. Không nên giả định mọi metric đều được bật sẵn. Hãy kiểm tra metric thực tế được export trong môi trường chạy.

Các cảnh báo hữu ích gồm:

- Tỷ lệ send failure vượt ngưỡng trong một khoảng thời gian.
- p95/p99 send latency tăng kéo dài.
- Producer buffer gần cạn hoặc thread gửi bị chặn do buffer.
- Outbox backlog tăng liên tục hoặc tuổi record cũ nhất vượt SLA.
- Có lỗi authentication, authorization hoặc serialization kéo dài.
- Event chuyển sang hàng đợi lỗi nhưng không được xử lý.

Khi điều tra, đối chiếu timestamp của ứng dụng với broker log, thay đổi leader/ISR, trạng thái network và metric của producer. Một spike retry có thể là dấu hiệu cluster vừa phục hồi sau sự cố; retry rate tăng kéo dài thường cho thấy một vấn đề chưa được giải quyết.

## 10. Quy trình thiết kế retry cho producer mới

Khi xây dựng producer trong một service Spring, có thể đi theo trình tự sau:

1. Xác định yêu cầu độ bền: event nào có thể mất, event nào phải được lưu cho đến khi publish thành công.
2. Chọn cấu hình xác nhận ghi: `acks`, replication factor và `min.insync.replicas`.
3. Bật idempotent producer với cấu hình tương thích để giảm duplicate do retry nội bộ.
4. Xác định ngân sách thời gian: `request.timeout.ms`, `delivery.timeout.ms`, `linger.ms` và thời gian nghiệp vụ cho phép.
5. Cấu hình retry backoff phù hợp với thời gian phục hồi của cluster và phiên bản Kafka client.
6. Theo dõi future từ `KafkaTemplate.send()` để ghi nhận kết quả gửi.
7. Chỉ thêm application-level retry khi có chính sách rõ ràng; dùng backoff có giới hạn và tránh chặn thread.
8. Dùng transactional outbox hoặc cơ chế lưu bền tương đương nếu event phải tồn tại qua restart và sự cố dài.
9. Dùng event ID ổn định và idempotent consumer để xử lý an toàn trường hợp publish lại.
10. Kiểm thử khi broker tạm ngừng, leader thay đổi, mất kết nối, timeout, lỗi quyền và lỗi serialization; xác minh cả khả năng phục hồi lẫn hành vi duplicate.

## 11. Kiểm thử các tình huống retry

Một producer đáng tin cậy cần được kiểm thử trong các tình huống lỗi, không chỉ kiểm thử đường gửi thành công.

| Tình huống | Kết quả mong đợi cần xác minh |
|---|---|
| Broker tạm thời không truy cập được | Producer retry trong ngân sách cấu hình; ứng dụng nhận kết quả cuối cùng |
| Leader partition thay đổi | Metadata được cập nhật và record có thể được gửi lại |
| Broker không đáp ứng trước delivery timeout | Future kết thúc bằng lỗi; event được giữ hoặc xử lý theo chính sách ứng dụng |
| Authentication hoặc authorization sai | Hệ thống phát hiện lỗi cấu hình và cảnh báo, không retry vô hạn |
| Payload serialization lỗi | Lỗi được phát hiện ở phía producer và không bị retry như lỗi mạng |
| Ứng dụng restart khi outbox còn pending | Dispatcher tiếp tục xử lý record chưa gửi |
| Dispatcher restart sau khi Kafka đã ghi nhưng trước khi đánh dấu outbox | Duplicate có thể xuất hiện và consumer xử lý idempotent |
| Tải tăng làm producer buffer đầy | Backpressure, timeout và cảnh báo thể hiện đúng tình trạng |

Khi kiểm thử, ghi nhận event ID, topic, partition, offset, thời gian gửi và số lần xử lý ở consumer. Điều này giúp phân biệt một record được Kafka client retry nội bộ với một event được ứng dụng publish lại thành record mới.

## 12. Nguyên tắc lựa chọn

Đối với producer Spring Kafka thông thường, hãy bắt đầu bằng retry nội bộ của Kafka client, idempotent producer, timeout và backoff được cấu hình có chủ đích. Theo dõi kết quả bất đồng bộ của `KafkaTemplate` để ứng dụng biết lần gửi đã thành công hay thất bại.

Chỉ bổ sung retry ở tầng ứng dụng khi cần một chính sách vượt ra ngoài ngân sách gửi nội bộ. Với event quan trọng, hãy lưu ý định publish một cách bền vững, thường bằng transactional outbox, rồi retry theo lịch có giới hạn. Thiết kế consumer idempotent để chịu được trường hợp event được publish lại.

Retry giúp hệ thống vượt qua lỗi tạm thời. Backoff giúp quá trình phục hồi không làm sự cố nặng thêm. Timeout giới hạn thời gian chờ, idempotence giảm duplicate do retry nội bộ, còn outbox và idempotent consumer giúp bảo vệ luồng nghiệp vụ qua restart và các lần publish lại. Các thành phần này cần được thiết kế cùng nhau để producer vận hành đáng tin cậy.

