# Gửi đồng bộ, gửi bất đồng bộ và timeout

Khi ứng dụng Spring Cloud Stream phát message đến Kafka, lời gọi gửi có thể hoàn tất trước khi producer nhận được kết quả xác nhận từ broker. Đây là khác biệt quan trọng giữa gửi bất đồng bộ và gửi đồng bộ. Gửi bất đồng bộ giúp luồng ứng dụng không phải chờ mỗi lần broker xác nhận; gửi đồng bộ cho phép caller chờ kết quả gửi và xử lý lỗi ngay tại điểm gọi, đổi lại làm tăng độ trễ và giữ thread lâu hơn.

Trong Kafka Binder, producer gửi bất đồng bộ là hành vi mặc định của Kafka client. Kafka Binder cung cấp thuộc tính `sync` cho từng output binding để yêu cầu chờ kết quả gửi. Dù chọn cách nào, timeout vẫn cần được thiết kế cùng với `acks`, retry, `delivery.timeout.ms`, `request.timeout.ms` và giới hạn chờ lấy metadata/buffer. Một lời gọi trả về thành công ở tầng ứng dụng không phải lúc nào cũng đồng nghĩa broker đã lưu message bền vững.

Bài thuộc chương **Phát tới Kafka** của module `SPRING_CLOUD_STREAM`. Ta sẽ dùng `StreamBridge` và output binding để giải thích luồng gửi, phân biệt xác nhận của channel với xác nhận của broker, cấu hình đồng bộ/bất đồng bộ, thiết kế timeout, xử lý lỗi và kiểm thử trong môi trường có tải.

## 1. Luồng gửi message qua Kafka Binder

Một ứng dụng có thể phát message từ function output hoặc từ thành phần imperative bằng `StreamBridge`. Trong cả hai trường hợp, Kafka Binder kết nối output binding với Kafka producer.

```text
Ứng dụng
   |
   | StreamBridge.send(...) hoặc function output
   v
Output binding / MessageChannel
   |
   v
Kafka Binder
   |
   v
Kafka Producer
   |
   | gửi record qua network
   v
Kafka broker
   |
   | ghi log và trả kết quả theo acks
   v
Producer callback / send result
```

Các bước có thể hoàn tất ở những thời điểm khác nhau:

1. Ứng dụng chuyển message vào output binding.
2. Binder gọi Kafka producer để gửi record.
3. Kafka producer đưa record vào buffer và gửi qua network.
4. Broker nhận record, ghi theo cấu hình replication và trả acknowledgement.
5. Producer nhận kết quả thành công hoặc lỗi.

Gửi bất đồng bộ thường cho phép bước 1 và bước 2 hoàn tất trước bước 5. Gửi đồng bộ làm cho caller chờ kết quả producer theo cấu hình binder. Vì vậy, cần hiểu rõ caller đang chờ điều gì trước khi quyết định dùng chế độ nào.

## 2. Gửi bất đồng bộ là gì?

Kafka Java producer có API `send()` bất đồng bộ: phương thức đưa record vào luồng gửi và trả về một `Future`/kết quả bất đồng bộ. Producer có thể gom batch, gửi nhiều record song song và nhận acknowledgement sau đó. Kafka Binder thông thường sử dụng cách gửi này mặc định để tận dụng khả năng batching và network I/O của producer.

Với `StreamBridge`, code imperative có thể gửi message như sau:

```java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

record OrderPlaced(String eventId, String orderId, long total) {}

@Service
class OrderEventPublisher {

    private final StreamBridge streamBridge;

    OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderPlaced event) {
        return streamBridge.send("orders-out-0", event);
    }
}
```

`StreamBridge.send` trả về `boolean` cho biết message đã được chấp nhận bởi output channel theo cơ chế gửi của Spring hay chưa. Khi Kafka producer chạy bất đồng bộ, giá trị `true` không tự chứng minh broker đã xác nhận record. Lỗi phát sinh sau khi producer gửi record cần được quan sát qua cơ chế callback/error handling của binder và Kafka client.

### Ưu điểm

- Caller không phải chờ broker xác nhận cho từng record.
- Producer có thể gom batch và tận dụng `linger.ms`, `batch.size`.
- Throughput thường tốt hơn khi gửi nhiều message.
- Thread xử lý request hoặc nghiệp vụ có thể tiếp tục công việc khác sớm hơn.

### Hạn chế

- Lỗi broker có thể xuất hiện sau khi phương thức gửi đã trả về.
- Caller không có một kết quả xác nhận broker trực tiếp chỉ từ boolean của `StreamBridge.send`.
- Nếu ứng dụng shutdown quá sớm, cần bảo đảm producer được flush/close đúng cách để xử lý các record đang chờ.
- Cần cơ chế quan sát và xử lý lỗi bất đồng bộ rõ ràng.

Gửi bất đồng bộ phù hợp với luồng có thể xử lý lỗi bằng retry/outbox hoặc theo dõi trạng thái phát sau đó. Không dùng kết quả `true` của `StreamBridge.send` làm bằng chứng một giao dịch nghiệp vụ đã được broker lưu bền vững.

## 3. Gửi đồng bộ là gì?

Kafka Binder hỗ trợ thuộc tính producer `sync`. Khi bật `sync: true`, binder chờ kết quả gửi từ Kafka producer trước khi hoàn tất lời gọi gửi theo cơ chế đồng bộ của binder. Nếu producer gặp lỗi hoặc hết thời gian chờ, lỗi được chuyển về caller theo cơ chế của framework.

Ví dụ cấu hình output binding:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          content-type: application/json
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              sync: true
```

`sync` là thuộc tính riêng của Kafka binder, nằm dưới `spring.cloud.stream.kafka.bindings.<bindingName>.producer`. Nó không phải thuộc tính generic áp dụng giống nhau cho mọi binder. Với RabbitMQ hoặc Pulsar, semantics xác nhận gửi và cấu hình đồng bộ được quyết định bởi binder tương ứng.

Khi `sync: true`, một lần gửi có thể chờ broker phản hồi. Điều này giúp phát hiện lỗi publish tại điểm gọi, nhưng làm thread caller bị giữ trong suốt thời gian chờ. Nếu broker chậm, nhiều thread có thể cùng bị giữ và làm cạn thread pool của web server hoặc worker.

## 4. So sánh hai chế độ

| Tiêu chí | Bất đồng bộ (`sync: false`, mặc định) | Đồng bộ (`sync: true`) |
|---|---|---|
| Thời điểm caller tiếp tục | Sau khi message được đưa vào luồng gửi của binder/producer | Sau khi kết quả gửi được xác định hoặc timeout/lỗi |
| Xác nhận broker | Đến sau qua callback/error handling | Caller chờ kết quả theo cấu hình producer |
| Độ trễ của lời gọi | Thường thấp hơn | Phụ thuộc network, broker và replication |
| Throughput | Thuận lợi cho batching và gửi nhiều record | Có thể thấp hơn nếu chờ từng record |
| Xử lý lỗi | Cần quan sát lỗi bất đồng bộ | Có thể bắt lỗi tại điểm gọi |
| Tài nguyên thread | Ít giữ thread caller hơn | Giữ thread trong thời gian chờ |
| Trường hợp phù hợp | Event stream, telemetry, outbox relay có theo dõi kết quả | Luồng cần biết kết quả publish trước khi tiếp tục |

Không có chế độ nào tự động bảo đảm exactly-once. Chất lượng xác nhận còn phụ thuộc `acks`, replication factor, `min.insync.replicas`, idempotent producer và transaction.

## 5. `StreamBridge.send` trả về điều gì?

Khi dùng Spring Cloud Stream, cần phân biệt ba kết quả:

- **Channel accepted:** output channel chấp nhận message để chuyển tiếp.
- **Broker acknowledged:** Kafka producer nhận acknowledgement theo cấu hình `acks`.
- **Consumer processed:** consumer đã nhận và hoàn tất tác động nghiệp vụ.

Ba mốc này không đồng nhất.

```text
StreamBridge.send(...) == true
          |
          v
Message được nhận vào output channel
          |
          v
Kafka producer gửi record
          |
          v
Broker ack theo acks
          |
          v
Consumer nhận và xử lý
```

Nếu cần chờ broker xác nhận từ `StreamBridge`, bật `sync: true` cho Kafka output binding. Dù vậy, broker acknowledgement vẫn không chứng minh consumer đã xử lý. Nếu nghiệp vụ cần biết consumer hoàn tất, cần một acknowledgement nghiệp vụ, reply message hoặc trạng thái được lưu ở hệ thống đích.

Nếu `send` trả về `false`, ứng dụng cần xem đó là tín hiệu message không được chấp nhận theo cơ chế channel và quyết định retry hoặc trả lỗi. Nếu `send` trả về `true` trong chế độ bất đồng bộ, vẫn cần theo dõi kết quả publish sau đó.

## 6. Kafka `acks` quyết định mức xác nhận

Chế độ đồng bộ chỉ quyết định caller có chờ kết quả producer hay không. Thuộc tính Kafka `acks` quyết định broker cần xác nhận ở mức nào:

| `acks` | Ý nghĩa | Đánh đổi |
|---|---|---|
| `0` | Producer không chờ broker acknowledgement | Độ trễ thấp nhưng không có xác nhận broker; có thể mất record mà producer không biết |
| `1` | Leader partition xác nhận sau khi ghi record vào log của leader | Có thể mất dữ liệu nếu leader lỗi trước khi follower bắt kịp |
| `all` hoặc `-1` | Leader chờ các replica trong ISR xác nhận theo cấu hình Kafka | Bền vững hơn, nhưng phụ thuộc ISR và `min.insync.replicas` |

Với message nghiệp vụ quan trọng, thường cân nhắc `acks: all` cùng replication factor và `min.insync.replicas` phù hợp. Nếu chỉ đặt `sync: true` nhưng `acks: 0`, caller không nhận được xác nhận broker về việc record đã được ghi. Đồng bộ không thể tạo ra mức bảo đảm cao hơn cấu hình Kafka.

Ví dụ cấu hình theo binding:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.events
      kafka:
        bindings:
          orders-out-0:
            producer:
              sync: true
              configuration:
                acks: all
                enable.idempotence: true
```

`enable.idempotence` giúp Kafka producer tránh một số bản ghi trùng do retry nội bộ của producer trong phạm vi session/producer identity. Nó không thay thế event ID và idempotency ở consumer khi ứng dụng gửi lại cùng sự kiện qua một lần gọi mới hoặc sau restart.

## 7. Các loại timeout trong quá trình gửi

Không có một timeout duy nhất điều khiển toàn bộ quá trình. Một số timeout liên quan đến các giai đoạn khác nhau:

| Timeout | Phạm vi | Khi hết thời gian |
|---|---|---|
| `max.block.ms` | Thời gian producer có thể bị block khi chờ metadata hoặc chờ chỗ trong buffer | Producer có thể ném lỗi nếu không lấy được metadata/buffer trong giới hạn |
| `request.timeout.ms` | Thời gian chờ phản hồi cho một request gửi đến broker | Request có thể bị xem là thất bại và được retry nếu chính sách cho phép |
| `delivery.timeout.ms` | Tổng thời gian tối đa để một record được gửi thành công hoặc thất bại, tính cả batching, request và retry | Producer hoàn tất record với lỗi timeout nếu không giao được trong giới hạn |
| Timeout chờ đồng bộ của binder | Thời gian caller chờ kết quả producer khi `sync` bật | Caller nhận lỗi timeout theo cơ chế binder |
| Timeout của HTTP/request nghiệp vụ | Thời gian hệ thống gọi bên ngoài chờ ứng dụng phản hồi | Client có thể timeout dù producer hoặc broker vẫn đang xử lý |

Các thuộc tính Kafka client có thể được cấu hình trong binder configuration hoặc producer configuration. Tên, vị trí và khả năng override theo binding cần đối chiếu với phiên bản Spring Cloud Stream Kafka binder đang dùng.

`delivery.timeout.ms` là giới hạn giao record ở phía Kafka producer; nó không phải timeout của HTTP request. `max.block.ms` thường liên quan đến lúc producer cần metadata hoặc buffer, trước khi request được gửi. `request.timeout.ms` áp dụng cho một request broker. Khi kết hợp, cần tránh đặt timeout caller ngắn hơn nhiều so với thời gian producer có thể tiếp tục gửi ở background mà không có cơ chế đối soát.

## 8. Ví dụ cấu hình timeout cho Kafka producer

Ví dụ sau minh họa cấu hình producer ở mức binder:

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: kafka-1:9092,kafka-2:9092
          configuration:
            acks: all
            enable.idempotence: true
            request.timeout.ms: 30000
            delivery.timeout.ms: 120000
            max.block.ms: 60000
```

Đây là các giá trị minh họa, không phải bộ timeout tối ưu cho mọi hệ thống. `delivery.timeout.ms` phải lớn hơn hoặc bằng các giới hạn request/batching liên quan theo yêu cầu Kafka client. Khi thay đổi `request.timeout.ms`, hãy xem xét lại `delivery.timeout.ms` và tổng thời gian retry. Khi dùng nhiều binding có SLA khác nhau, có thể cấu hình producer properties riêng cho binding nếu binder hỗ trợ.

Không đặt timeout ngắn chỉ để làm request trả về nhanh nếu ứng dụng không có cách biết message đã được broker nhận hay chưa. Timeout ở caller có thể xảy ra trong khi producer vẫn đang chờ hoặc broker đã nhận record nhưng phản hồi bị trễ. Đây là nguồn gốc phổ biến của publish retry và duplicate.

## 9. Xử lý timeout không có nghĩa chắc chắn message chưa được gửi

Giả sử producer gửi record đến Kafka. Broker ghi record và gửi acknowledgement, nhưng mạng bị gián đoạn trước khi acknowledgement đến producer. Producer có thể thấy timeout trong khi record đã nằm trong log.

```text
Producer                         Kafka broker
   |                                  |
   |---------- record ---------------->
   |                                  | ghi record
   |<--------- acknowledgement -------|
   X network timeout trước khi nhận ack
```

Khi caller thấy timeout, kết quả có thể là **không xác định**: record có thể chưa đến broker, đã đến nhưng chưa được ghi theo mức yêu cầu, hoặc đã được ghi nhưng acknowledgement bị mất. Nếu ứng dụng tạo event ID mới rồi gửi lại, consumer có thể coi đó là một sự kiện mới.

Với message nghiệp vụ, hãy tạo event ID ổn định trước lần publish đầu tiên và giữ nguyên ID qua các lần retry. Consumer dùng idempotency/inbox để chống tác động lặp. Với producer cần phục hồi sau restart, lưu event và trạng thái publish trong outbox thay vì chỉ giữ trong bộ nhớ.

## 10. Retry của producer và retry của ứng dụng

Kafka producer có retry nội bộ cho những lỗi có thể phục hồi. Producer giữ record trong buffer và thử gửi lại theo cấu hình client cho đến khi thành công hoặc vượt `delivery.timeout.ms`. Đây là retry ở tầng client cho cùng một lần gửi logic.

Retry của ứng dụng là một lần gọi gửi mới, ví dụ service bắt timeout rồi gọi `StreamBridge.send` lần nữa. Nếu lần gửi đầu đã được broker ghi nhưng acknowledgement bị mất, lần gửi mới có thể tạo record thứ hai. Producer idempotence xử lý một số retry nội bộ của producer, nhưng không thay thế idempotency cho lần gọi mới từ ứng dụng.

| Tầng retry | Phạm vi | Lưu ý |
|---|---|---|
| Kafka producer retry | Một record trong một producer send operation | Phối hợp với `delivery.timeout.ms` và idempotence |
| Binder/application retry | Gọi lại thao tác publish từ ứng dụng hoặc framework | Có thể tạo một send operation mới |
| Outbox relay retry | Đọc lại cùng bản ghi outbox chưa được đánh dấu gửi xong | Phải giữ nguyên event ID để consumer deduplicate |
| Consumer retry/redelivery | Xử lý lại message sau khi nhận | Consumer cần idempotent |

Không lồng retry ở nhiều tầng mà không tính tổng số lần gửi. Ví dụ producer tự retry nhiều lần, ứng dụng retry thêm ba lần và outbox relay lại chạy sau restart có thể làm số bản ghi tăng nếu không giữ event ID và dedup.

## 11. Chọn đồng bộ hay bất đồng bộ theo nghiệp vụ

### Gửi đồng bộ phù hợp khi

- Một request cần biết ngay việc publish đã được broker xác nhận theo `acks` hay chưa.
- Luồng xử lý không thể tiếp tục nếu publish thất bại.
- Tần suất gửi vừa phải và latency budget cho phép chờ broker.
- Caller có cơ chế xử lý timeout và kết quả không xác định.

Ví dụ một thao tác quản trị cần ghi audit event và trả trạng thái gửi cho người gọi. Nếu yêu cầu thực sự là “broker đã xác nhận”, cần bật synchronous producer và chọn `acks` phù hợp.

### Gửi bất đồng bộ phù hợp khi

- Throughput và batching quan trọng hơn việc chờ từng acknowledgement.
- Caller không cần kết quả broker ngay lập tức.
- Hệ thống có outbox, retry hoặc cơ chế theo dõi lỗi publish.
- Message có thể được xử lý độc lập sau khi request nghiệp vụ hoàn tất.

Ví dụ telemetry hoặc sự kiện theo dõi có thể được gửi bất đồng bộ, miễn là hệ thống có metric, error handling và chính sách mất dữ liệu phù hợp.

Không chọn async chỉ vì muốn nhanh nếu dữ liệu không được phép mất và không có cơ chế bền vững. Cũng không chọn sync cho mọi message vì việc chờ broker trên mỗi lần gửi có thể làm giảm throughput và gây nghẽn thread pool.

## 12. Tránh giữ thread HTTP quá lâu

Nếu một REST request gọi `StreamBridge.send` đồng bộ, thread xử lý HTTP sẽ chờ kết quả producer. Khi Kafka chậm hoặc mất kết nối, nhiều request có thể cùng giữ thread. Điều này làm tăng latency, cạn thread pool và gây hiệu ứng dây chuyền.

Các biện pháp:

- Đặt timeout hợp lý cho producer và request nghiệp vụ.
- Giới hạn số request đồng thời có thể chờ Kafka.
- Không thực hiện synchronous send trong critical path nếu SLA không cho phép.
- Dùng outbox để ghi sự kiện cùng transaction nghiệp vụ, sau đó relay gửi bất đồng bộ.
- Theo dõi thời gian chờ producer, số request đang chờ và thread pool saturation.
- Trả trạng thái `ACCEPTED` khi sự kiện đã được lưu bền vững vào outbox; không diễn giải thành broker đã nhận nếu relay chưa gửi xong.

Mẫu outbox thường phù hợp khi request cần commit nghiệp vụ nhanh nhưng sự kiện phải được phát bền vững. REST request ghi dữ liệu và outbox record trong cùng database transaction; worker riêng gửi outbox đến Kafka và cập nhật trạng thái. Worker có thể gửi lặp, nên consumer vẫn cần event ID ổn định.

## 13. Gửi bất đồng bộ nhưng vẫn theo dõi kết quả

Khi dùng Kafka Binder với `sync: false`, không nên bỏ qua lỗi publish sau khi `StreamBridge.send` trả về. Cần cấu hình và quan sát error handling theo khả năng binder, log lỗi gửi, metric producer và trạng thái outbox nếu có.

Nếu ứng dụng cần một `Future`/`CompletableFuture` cụ thể cho từng record để liên kết kết quả publish với một workflow, `StreamBridge.send` không cung cấp trực tiếp future Kafka record metadata trong API boolean của nó. Có thể dùng API Spring Kafka như `KafkaTemplate.send(...)` ở một thành phần producer chuyên biệt, nơi cần callback/metadata cụ thể; đổi lại thành phần đó đang sử dụng Spring Kafka trực tiếp thay vì chỉ dựa vào output binding của Spring Cloud Stream.

Ví dụ với Spring Kafka để minh họa việc chờ kết quả có giới hạn:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;
import org.springframework.stereotype.Service;

@Service
class DirectKafkaPublisher {

    private final KafkaTemplate<String, OrderPlaced> kafkaTemplate;

    DirectKafkaPublisher(KafkaTemplate<String, OrderPlaced> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderPlaced>> publish(
            OrderPlaced event) {
        return kafkaTemplate.send("orders.events", event.orderId(), event);
    }

    public SendResult<String, OrderPlaced> publishAndWait(OrderPlaced event)
            throws Exception {
        return publish(event).get(5, TimeUnit.SECONDS);
    }
}
```

Trong Spring Kafka hiện đại, `KafkaTemplate.send` trả về `CompletableFuture<SendResult<...>>`. `get(5, SECONDS)` chờ tối đa năm giây ở caller. Nếu hết thời gian, future có thể hoàn tất sau đó; timeout của `get` không tự hủy record đã gửi. Cần xử lý trạng thái không xác định và tránh gửi lại với event ID mới.

Ví dụ này là lựa chọn khi cần API future và `RecordMetadata` chi tiết. Trong ứng dụng dùng Kafka Binder, hãy cân nhắc giữ một đường gửi thống nhất qua binding nếu không cần các khả năng thấp tầng này.

## 14. Shutdown và flush producer

Producer bất đồng bộ có thể còn record trong buffer khi ứng dụng bắt đầu shutdown. Kafka producer cần được đóng đúng cách để flush dữ liệu đang chờ trong giới hạn cấu hình. Spring container và binder quản lý lifecycle producer; không tự đóng producer do framework quản lý.

Trong ứng dụng có outbox relay, khi shutdown nên:

1. Ngừng nhận công việc mới hoặc dừng lịch poll.
2. Chờ tác vụ đang xử lý hoàn tất trong giới hạn shutdown timeout.
3. Để producer flush/close theo lifecycle của binder/client.
4. Không đánh dấu outbox record đã gửi nếu chưa có kết quả xác nhận phù hợp.
5. Khi khởi động lại, tiếp tục các record chưa được đánh dấu hoàn tất bằng cùng event ID.

Nếu shutdown timeout quá ngắn, relay có thể bị dừng khi đang gửi. Điều đó không nhất thiết làm mất message nếu outbox còn giữ record, nhưng có thể gây publish lặp. Idempotency ở consumer là lớp bảo vệ cần thiết.

## 15. Quan sát độ trễ và timeout

Các chỉ số nên theo dõi:

- Thời gian từ lúc ứng dụng gọi send đến lúc channel chấp nhận message.
- Thời gian producer chờ broker acknowledgement khi dùng sync.
- Số lần timeout theo `max.block.ms`, request và delivery.
- Số record gửi thất bại hoặc retry ở producer.
- Producer buffer availability, batch size, request latency và record error rate.
- Số outbox record đang chờ, tuổi record cũ nhất và số lần publish lại.
- Thread pool saturation nếu gửi đồng bộ từ request handler.

Log nên có `eventId`, destination, partition key nếu có, binding name và loại lỗi. Không ghi toàn bộ payload nhạy cảm. Metric label nên giới hạn theo binding/destination đã chuẩn hóa, không dùng event ID làm nhãn có cardinality cao.

Khi timeout tăng, phân biệt lỗi metadata/buffer, lỗi network request, broker không đáp ứng `acks`, hoặc caller hết timeout trước producer. Các nguyên nhân này cần cách xử lý khác nhau.

## 16. Kiểm thử đồng bộ, bất đồng bộ và timeout

Một bộ kiểm thử nên bao gồm:

| Kịch bản | Cách kiểm thử | Điều cần xác minh |
|---|---|---|
| Async send bình thường | Gửi message với `sync: false` | Channel chấp nhận message và broker nhận record; lỗi async được quan sát |
| Sync send thành công | Bật `sync: true`, broker hoạt động | Caller chỉ hoàn tất sau kết quả producer theo cấu hình |
| Broker không khả dụng | Dừng broker hoặc chặn network | Lỗi được quan sát; thời gian chờ tuân theo timeout đã đặt |
| `acks: 0` | Gửi với acks 0 | Không diễn giải hoàn tất send là broker đã xác nhận |
| `acks: all` | Dùng topic có replication phù hợp | Xác minh broker ack theo ISR và `min.insync.replicas` |
| Buffer/metadata chưa sẵn sàng | Khởi động khi broker chưa sẵn sàng hoặc làm cạn buffer trong test tải | Xác minh giới hạn `max.block.ms` |
| Request timeout | Giả lập broker phản hồi chậm | Xác minh `request.timeout.ms` và retry |
| Delivery timeout | Giữ broker không thể nhận record trong thời gian dài | Xác minh producer kết thúc record trong ngân sách `delivery.timeout.ms` |
| Caller timeout | Đặt timeout HTTP ngắn hơn producer | Xác minh caller timeout không làm giả định record chưa được gửi |
| Shutdown khi còn record | Dừng ứng dụng trong lúc publish | Xác minh lifecycle flush và khả năng phục hồi outbox |
| Retry publish | Giả lập mất acknowledgement sau khi broker ghi | Consumer dedup theo event ID ổn định |

Test binder hữu ích để kiểm tra output binding và luồng message của Spring Cloud Stream, nhưng không mô phỏng đầy đủ Kafka producer buffer, acknowledgement, replication, timeout và network failure. Các tình huống timeout/acks cần integration test với Kafka phù hợp hoặc môi trường test có thể điều khiển broker.

## 17. Quy trình lựa chọn chế độ gửi

Khi thiết kế producer Kafka:

1. Xác định caller có cần biết broker đã xác nhận record trước khi tiếp tục hay không.
2. Nếu không cần chờ, giữ producer async và xây dựng cơ chế theo dõi lỗi gửi.
3. Nếu cần chờ, bật `sync: true` trên đúng Kafka output binding.
4. Chọn `acks` theo yêu cầu bền vững; không nhầm sync với durability.
5. Bật idempotent producer khi phù hợp và cấu hình replication/ISR ở broker.
6. Đặt `request.timeout.ms`, `delivery.timeout.ms` và `max.block.ms` nhất quán.
7. Tính tổng thời gian chờ cùng timeout HTTP, shutdown và SLA nghiệp vụ.
8. Giữ event ID ổn định qua mọi lần retry; dùng outbox nếu cần phục hồi sau restart.
9. Theo dõi lỗi bất đồng bộ, timeout, producer metrics và backlog outbox.
10. Kiểm thử broker chậm, broker mất kết nối, mất acknowledgement và shutdown.

## 18. Tự kiểm tra

- [ ] Giải thích được sự khác nhau giữa gửi bất đồng bộ và đồng bộ.
- [ ] Biết `sync` là thuộc tính producer của Kafka binder và mặc định là bất đồng bộ.
- [ ] Phân biệt giá trị boolean của `StreamBridge.send` với broker acknowledgement.
- [ ] Giải thích được vai trò của `acks: 0`, `acks: 1` và `acks: all`.
- [ ] Phân biệt `max.block.ms`, `request.timeout.ms` và `delivery.timeout.ms`.
- [ ] Hiểu timeout của caller không chứng minh record chưa được ghi vào Kafka.
- [ ] Phân biệt retry nội bộ của Kafka producer với retry của ứng dụng/outbox.
- [ ] Biết vì sao sync send có thể làm cạn thread pool.
- [ ] Thiết kế được event ID ổn định và idempotency khi publish lại.
- [ ] Kiểm thử được sync/async, acknowledgement, timeout, broker failure và shutdown.

## Kết luận

Kafka Binder gửi bất đồng bộ theo mặc định để tận dụng batching và giảm thời gian giữ thread caller. Bật `sync: true` trên output binding khi ứng dụng cần chờ kết quả gửi từ Kafka producer; tuy nhiên, mức xác nhận thực tế vẫn phụ thuộc `acks` và cấu hình replication. `StreamBridge.send` trả về boolean về việc message được chấp nhận ở output channel, không phải bằng chứng consumer đã xử lý hoặc broker đã lưu bền vững trong mọi chế độ. Hãy phân biệt `max.block.ms`, `request.timeout.ms`, `delivery.timeout.ms` và timeout nghiệp vụ; xử lý kết quả timeout như trạng thái có thể chưa xác định, giữ event ID qua retry và dùng outbox/idempotency khi cần bảo đảm giao nhận.
