# Message mất, trùng hoặc sai thứ tự do hiểu sai acknowledge và commit

## 1. Tình huống: đã nhận message nhưng dữ liệu vẫn sai

Một ứng dụng Spring Boot nhận sự kiện `OrderPaid` từ Kafka, cập nhật PostgreSQL rồi phát thông báo sang RabbitMQ. Sau khi nâng cấp thư viện hoặc tăng số consumer, đội vận hành gặp ba triệu chứng:

- **Mất:** log báo consumer đã nhận sự kiện nhưng database không có bản ghi tương ứng.
- **Trùng:** cùng một sự kiện cập nhật số dư hoặc gửi email hai lần.
- **Sai thứ tự:** trạng thái `PAID` bị ghi đè thành `CREATED` bởi sự kiện cũ đến muộn.

Ba hiện tượng thường xuất phát từ hiểu nhầm giữa **đã nhận message**, **xử lý nghiệp vụ thành công**, **commit transaction**, **acknowledge/commit tiến độ đọc** và **bảo đảm thứ tự**. Những mốc này không tự động là một thao tác nguyên tử.

Trong Spring Boot Integration, cùng một luồng có thể đi qua HTTP client, database, cache và broker; từng thành phần có cơ chế xác nhận riêng. Bài học này giải thích cách tìm nguyên nhân, xác định thứ tự thực hiện đúng, cấu hình Spring Kafka/Spring AMQP, xử lý JMS và thử nghiệm tình huống lỗi sau khi nâng cấp.

## 2. Phân biệt các loại xác nhận

### Acknowledge không đồng nghĩa commit nghiệp vụ

**Acknowledge (ack)** nói rằng phía nhận đã xác nhận một message với hệ thống gửi hoặc broker theo giao thức tương ứng. Ý nghĩa cụ thể phụ thuộc hệ thống:

| Khái niệm | Ai xác nhận với ai? | Điều được bảo đảm | Điều **không** được bảo đảm |
| --- | --- | --- | --- |
| Kafka producer `acks=all` | Broker xác nhận cho producer | Bản ghi được chấp nhận theo chính sách replica/ISR | Consumer đã đọc, database đã cập nhật |
| Kafka consumer offset commit | Consumer group lưu vị trí tiếp tục đọc | Những offset **trước vị trí commit** thường không được phát lại khi resume bình thường | Tác dụng phụ trong DB/HTTP đã commit |
| RabbitMQ publisher confirm | Broker xác nhận cho publisher | Broker đã nhận/xử lý publish theo các điều kiện về routing và lưu trữ | Consumer đã xử lý thành công |
| RabbitMQ consumer `basicAck` | Consumer xác nhận delivery với broker | Broker có thể xóa delivery khỏi danh sách chưa ack | Transaction DB hoặc HTTP của consumer đã thành công |
| JMS `Session.commit()` | Session giao dịch xác nhận/commit trong phạm vi JMS | Các thao tác JMS tham gia session được commit | Transaction database ngoài JMS tự động commit theo |
| HTTP `2xx` | Server trả phản hồi cho client | Request được ứng dụng chấp nhận/xử lý theo hợp đồng HTTP cụ thể | Mọi tác vụ bất đồng bộ phía sau đã bền vững |

**Kafka offset commit không phải database commit.** Kafka lưu offset theo **consumer group và topic-partition**. Ví dụ commit offset `105` nghĩa là sau khi consumer tiếp tục bình thường, nó đọc từ offset `105`; các bản ghi `0..104` được coi đã qua. Không nên hiểu rằng “message offset 105 vừa được xử lý xong”.

**RabbitMQ delivery acknowledgment không phải producer confirm.** Hai cơ chế phục vụ hai chiều khác nhau của luồng. Publisher confirm có thể thành công dù ứng dụng tiêu thụ sau đó lỗi; consumer ack có thể xảy ra trước khi database ghi xong nếu mã gọi sai chỗ.

### Thứ tự các mốc

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer Spring Boot
    participant D as Database
    B->>C: Deliver event E
    C->>D: BEGIN + xử lý nghiệp vụ
    D-->>C: COMMIT DB thành công
    C->>B: Ack / commit offset
    Note over C,B: Nếu crash trước ack, E có thể được phát lại
    Note over C,D: Nếu ack trước COMMIT DB, có nguy cơ mất cập nhật
~~~

Thứ tự thường an toàn hơn khi có tác dụng phụ lưu tại DB là **xử lý và commit DB trước, ack/commit tiến độ sau**, kèm **idempotency** để chịu được việc broker giao lại khi consumer crash giữa hai bước.

Đó là một nguyên tắc xử lý *at-least-once* thực dụng, không có nghĩa DB và broker tạo thành một transaction nguyên tử. Nếu ack thành công nhưng ghi database xảy ra sau, vùng lỗi gây mất message xuất hiện. Nếu DB commit xong nhưng ack không tới broker, vùng lỗi gây trùng message xuất hiện. Không thể loại bỏ cả hai chỉ bằng việc đổi vị trí của `ack()`.

## 3. Ma trận lỗi: tại sao message mất hoặc trùng?

| Thời điểm crash/lỗi | DB đã commit? | Tiến độ broker đã ack/commit? | Hệ quả thường thấy |
| --- | --- | --- | --- |
| Trước khi xử lý | Chưa | Chưa | Broker có thể giao lại; cần retry |
| **Ack sớm, rồi xử lý thất bại** | **Chưa** | **Đã** | **Mất hiệu ứng nghiệp vụ:** tiến độ đã vượt qua message |
| **Commit DB rồi crash trước ack** | **Đã** | **Chưa** | **Phát lại:** nếu xử lý không idempotent sẽ tạo tác dụng phụ trùng |
| DB commit và ack đều hoàn tất | Đã | Đã | Hoàn thành ở hai phía trong điều kiện vận hành bình thường |
| Timeout khi gửi ack/commit | Có thể đã | **Không rõ** | Không được đoán trạng thái; có thể phát lại và cần đối chiếu |
| Hệ thống nhận ack nhưng lời gọi HTTP bên ngoài thất bại | Có thể đã | Đã | DB và hệ thống ngoài có thể bất nhất; cần outbox/bù trừ |

“Message mất” đôi khi chỉ có nghĩa **không còn được giao lại cho consumer group**, chứ broker chưa chắc đã xóa vật lý message. Kafka vẫn giữ record theo retention; một offset đã commit có thể làm ứng dụng **bỏ qua** record còn trên topic. Với RabbitMQ, delivery được ack thành công thường bị loại khỏi queue, do đó hậu quả khác về khả năng phát lại.

**Một lỗi phổ biến:** listener gọi service `@Async`, nhận về ngay rồi ack, trong khi việc ghi DB chạy sau. Lúc này ack chỉ chứng minh công việc đã được *xếp lịch*, không chứng minh đã commit. Cần chờ kết quả xử lý hoặc thiết kế inbox bền vững trước khi ack.

### At-most-once, at-least-once và exactly-once trong phạm vi nào?

- **At-most-once:** có thể mất tác vụ nếu tiến độ đọc được xác nhận trước xử lý, nhưng không phát lại bởi chính cơ chế đó.
- **At-least-once:** message có thể được giao lại; nghiệp vụ phải chịu trùng. Thực tế thường đạt bằng việc commit/ack sau xử lý.
- **Exactly-once:** chỉ có ý nghĩa khi nêu rõ **phạm vi**. Kafka hỗ trợ cơ chế transactional read–process–write trong Kafka khi cấu hình producer/consumer/transaction đúng; điều đó **không tự biến** cập nhật PostgreSQL, gọi REST hoặc gửi email thành tác dụng phụ exactly-once.

Với hệ tích hợp nhiều hệ thống, cách khả thi thường là **at-least-once delivery + idempotent effect** (giao ít nhất một lần, hiệu ứng nghiệp vụ không lặp), kết hợp outbox/inbox cho các đường đi cần đảm bảo.

## 4. Kafka: offset commit, acknowledge, retry và thứ tự

### Offset thuộc partition, không thuộc toàn topic

~~~text
Topic order-status, group order-projector
  partition 0: ... [offset 40] [41] [42] [43]
  partition 1: ... [offset 80] [81] [82] [83]

Nếu group đã commit:
  partition 0 -> 43 : lần tiếp theo thường bắt đầu tại 43
  partition 1 -> 82 : lần tiếp theo thường bắt đầu tại 82
~~~

Không có “offset toàn topic” để bảo đảm thứ tự toàn cục. Kafka chỉ có thứ tự append trong **một partition**. Nếu sự kiện của một đơn hàng nằm ở nhiều partition (vì key không ổn định), consumer có thể quan sát `PAID` trước `CREATED`.

Với consumer group, một partition thường chỉ được gán cho một thành viên group tại một thời điểm, nhưng **xử lý bất đồng bộ**, rebalance, retry, thay đổi partition count hoặc việc dùng nhiều pipeline có thể làm hiệu ứng nghiệp vụ xuất hiện khác thứ tự đọc. Tăng concurrency không tự bảo đảm mọi cập nhật tới cùng entity sẽ tuần tự.

### Các cơ chế commit cần phân biệt

| Cơ chế | Ý nghĩa thực tế | Rủi ro cần kiểm tra |
| --- | --- | --- |
| Kafka client `enable.auto.commit=true` | Client định kỳ commit vị trí consumer đã poll theo cơ chế của nó | Tiến độ có thể vượt việc xử lý nếu ứng dụng xử lý chậm/bất đồng bộ |
| Spring Kafka container `AckMode.BATCH` | Container commit sau khi xử lý các record trong batch poll theo cấu hình | Một record lỗi ảnh hưởng tiến độ cả batch, tùy error handler |
| `AckMode.RECORD` | Container commit sau mỗi record được listener xử lý thành công | Thông lượng/chi phí commit và cách handler xử lý lỗi |
| `AckMode.MANUAL` | Listener báo đã xử lý; container thực hiện commit theo cơ chế tương tự batch | `acknowledge()` không đồng nghĩa commit tức thời tại dòng code |
| `AckMode.MANUAL_IMMEDIATE` | Listener ack trên consumer thread để yêu cầu commit ngay | Vẫn phải xử lý lỗi commit, rebalance và chế độ sync/async |

Tên và hành vi có thể thay đổi theo phiên bản Spring Kafka, listener type, transactional container, `asyncAcks` và error handler. Khi nâng cấp, **kiểm tra listener container factory và log condition/config thực tế** thay vì suy đoán từ một thuộc tính cấu hình.

### Ví dụ Spring Boot: commit tiến độ sau khi transaction DB hoàn tất

~~~yaml
# application.yml (Spring Boot + Spring for Apache Kafka)
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      ack-mode: manual_immediate
~~~

`auto-offset-reset: earliest` chỉ có tác dụng khi **không có offset hợp lệ đã lưu** cho partition/group; nó không “phát lại từ đầu” nếu group đã commit tiến độ.

Giả sử event có cấu trúc:

~~~json
{
  "eventId": "partner-a:evt-8192",
  "orderId": "ORD-1024",
  "version": 7,
  "status": "PAID"
}
~~~

Lưu dấu xử lý ở **cùng transaction PostgreSQL** với dữ liệu projection:

~~~sql
CREATE TABLE consumed_event (
    event_id TEXT PRIMARY KEY,
    consumed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_projection (
    order_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    last_version BIGINT NOT NULL
);
~~~

~~~java
// OrderEvent.java
public record OrderEvent(
        String eventId, String orderId, long version, String status) {}
~~~

~~~java
// OrderProjectionService.java: minh họa PostgreSQL + Spring JDBC
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {

    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void apply(OrderEvent event) {
        int inserted = jdbc.update("""
            INSERT INTO consumed_event(event_id)
            VALUES (?)
            ON CONFLICT (event_id) DO NOTHING
            """, event.eventId());
        if (inserted == 0) {
            return; // cùng eventId đã được xử lý và commit
        }

        jdbc.update("""
            INSERT INTO order_projection(order_id, status, last_version)
            VALUES (?, ?, ?)
            ON CONFLICT (order_id) DO UPDATE SET
                status = EXCLUDED.status,
                last_version = EXCLUDED.last_version
            WHERE order_projection.last_version < EXCLUDED.last_version
            """, event.orderId(), event.status(), event.version());
    }
}
~~~

Ví dụ trên giả định mỗi sự kiện mang **trạng thái đầy đủ** và `version` tăng đơn điệu cho mỗi `orderId`. Điều kiện cập nhật chỉ áp dụng phiên bản mới hơn; event cũ tới muộn không ghi đè state. Nếu sự kiện là delta (ví dụ “cộng 100 vào số dư”) hoặc đòi hỏi xử lý từng version liên tiếp, bỏ qua gap không an toàn: phải giữ hàng đợi theo khóa, phát hiện version thiếu và replay/đối soát.

Không dùng query “kiểm tra ID tồn tại rồi mới INSERT” tách rời transaction để chống trùng, vì hai consumer có thể cùng kiểm tra trước khi ghi. Unique constraint trên `consumed_event.event_id` là rào chắn cạnh tranh chính; phần INSERT và cập nhật projection phải dùng **cùng database transaction manager**. `@Transactional` có hiệu lực khi phương thức được gọi qua Spring proxy, không phải tự gọi nội bộ cùng instance.

Listener Kafka:

~~~java
// OrderKafkaListener.java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class OrderKafkaListener {

    private final ObjectMapper json;
    private final OrderProjectionService projection;

    public OrderKafkaListener(
            ObjectMapper json, OrderProjectionService projection) {
        this.json = json;
        this.projection = projection;
    }

    @KafkaListener(
        topics = "partner.order-status",
        groupId = "order-projector")
    public void consume(
            ConsumerRecord<String, String> record,
            Acknowledgment acknowledgment) throws JsonProcessingException {
        OrderEvent event = json.readValue(record.value(), OrderEvent.class);
        projection.apply(event);       // DB transaction commit khi trả về
        acknowledgment.acknowledge(); // sau đó mới báo xử lý xong
    }
}
~~~

Đây là luồng đồng bộ có chủ đích. Nếu `projection.apply` ném exception, listener không đến `acknowledge()`; retry và DLT tùy `DefaultErrorHandler`/container được cấu hình. Nếu transaction DB đã commit nhưng consumer crash trước khi commit offset, broker có thể phát lại, nhưng `consumed_event` giúp nhận biết event trùng.

**Không tự động coi mọi exception là retry vô hạn.** JSON sai schema, field bắt buộc thiếu hoặc event không hợp lệ thường cần đường lưu sự kiện lỗi (DLT/quarantine), cảnh báo và quyết định rõ khi nào được đánh dấu đã xử lý. Với lỗi mạng/DB tạm thời nên retry có giới hạn, backoff, quan sát và khả năng replay.

### Những nhầm lẫn Kafka cần tránh

1. **Producer `acks=all` không quyết định consumer offset.** Message được Kafka xác nhận vẫn có thể chưa được ứng dụng xử lý.
2. **`acknowledge()` khác với database commit.** Chỉ ack sau khi phương thức chứa transaction nghiệp vụ đã trả về thành công; nếu xử lý bất đồng bộ phải chờ đủ.
3. **Manual ack không tự giải quyết lỗi trong batch.** Nếu commit vượt offset của record chưa xử lý, record đó có thể bị bỏ qua. Khi sử dụng `asyncAcks` hay xử lý song song, phải hiểu cách container giữ các ack chưa liên tục và hành vi khi crash.
4. **Rebalance có thể gây phát lại.** Consumer bị mất partition do vượt `max.poll.interval.ms` hoặc thay đổi group có thể thất bại khi commit; record đã ghi DB vẫn xuất hiện lại.
5. **DLT recovery cũng ảnh hưởng offset.** Error handler có thể đánh dấu record đã recover và cho container tiến độ đi tiếp; cần xác nhận DLT publish đã thành công và chính sách commit recovery theo phiên bản.
6. **Kafka transaction không bao trùm database.** Trong read-process-write giữa các topic Kafka, dùng transactional producer và việc gửi offset vào transaction tương ứng. Nếu cùng lúc cập nhật PostgreSQL, vẫn cần mô hình phục hồi/idempotency qua ranh giới DB–Kafka.

## 5. RabbitMQ: delivery ack, requeue và thứ tự nhận lại

Với RabbitMQ, broker gửi delivery kèm **delivery tag** trên một channel. Trong chế độ manual acknowledgement:

- `basicAck(deliveryTag, false)` xác nhận đúng delivery đó; nếu broker nhận thành công, delivery rời trạng thái unacked.
- `basicNack(deliveryTag, false, true)` từ chối và yêu cầu **requeue**; đây không phải retry có giới hạn thời gian.
- `basicReject(deliveryTag, false)` từ chối **không requeue**; message được định tuyến đến dead-letter exchange nếu queue có cấu hình, hoặc có thể bị loại bỏ.
- `basicAck(deliveryTag, true)` xác nhận **nhiều delivery chưa ack** đến tag đó trên **cùng channel**. Dùng `multiple=true` nhầm có thể xác nhận cả message chưa xử lý.

Delivery tag chỉ có ý nghĩa trong channel phát delivery; không lưu tag để xác nhận trên channel khác hoặc sau khi channel đóng.

### Spring AMQP: phân biệt AUTO với RabbitMQ auto-ack

Spring AMQP `AcknowledgeMode.AUTO` (chế độ mặc định phổ biến của listener container) thường có nghĩa **container tự xác nhận sau khi listener xử lý thành công**, hoặc reject/nack theo policy khi lỗi. Nó **khác** với RabbitMQ `autoAck=true` ở cấp protocol (không chờ consumer manual acknowledgment).

Spring AMQP `AcknowledgeMode.MANUAL` đòi hỏi ứng dụng chủ động ack/nack. `AcknowledgeMode.NONE` tương ứng broker không đòi manual ack, do đó không phù hợp với luồng cần xử lý bền vững trước khi xác nhận.

Ví dụ:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        acknowledge-mode: manual
        prefetch: 10
~~~

~~~java
// OrderRabbitListener.java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.core.AmqpHeaders;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class OrderRabbitListener {

    private final ObjectMapper json;
    private final OrderProjectionService projection;

    public OrderRabbitListener(
            ObjectMapper json, OrderProjectionService projection) {
        this.json = json;
        this.projection = projection;
    }

    @RabbitListener(queues = "partner.order-status")
    public void consume(
            String body, Channel channel,
            @Header(AmqpHeaders.DELIVERY_TAG) long tag) throws IOException {
        try {
            OrderEvent event = json.readValue(body, OrderEvent.class);
            projection.apply(event);       // DB transaction đã kết thúc
            channel.basicAck(tag, false); // xác nhận đúng delivery
        } catch (JsonProcessingException invalidJson) {
            channel.basicReject(tag, false); // cần DLX để không mất dữ liệu lỗi
        } catch (Exception failure) {
            channel.basicNack(tag, false, false); // chuyển tới DLX nếu đã cấu hình
        }
    }
}
~~~

Đây là minh họa cho queue đã có **dead-letter exchange** và bộ xử lý retry/quarantine được cấu hình riêng. `basicNack(..., requeue=false)` không tự tạo retry queue; nếu chưa cấu hình DLX, message có thể bị loại bỏ. Trong hệ thống thật, phân loại lỗi tạm thời, retry theo số lần với delay/backoff, giới hạn poison message và cảnh báo để tránh tạo vòng lặp.

Không thay nhánh lỗi bằng `basicNack(tag, false, true)` vô hạn: message lỗi có thể được giao lại tức thì, tiêu thụ CPU, gây nghẽn queue và làm thay đổi thứ tự thực tế. Nếu channel/connection đóng trước ack, các delivery chưa ack có thể được requeue và gửi lại. Đây là lý do idempotency vẫn cần ngay cả khi luôn ack sau DB.

### Vì sao RabbitMQ không bảo đảm thứ tự hiệu ứng nghiệp vụ?

Queue có thứ tự enqueuing nhất định, nhưng thực tế có nhiều consumer, `prefetch > 1`, xử lý song song, requeue, nack, retry queue, DLX và redelivery. Một event cũ có thể quay lại sau event mới, thậm chí khi ban đầu queue nhận đúng thứ tự. `redelivered` là tín hiệu hỗ trợ chẩn đoán, **không phải unique event ID** dùng để chống trùng.

Publisher confirm là câu chuyện khác: publisher nên dùng confirm để biết broker đã chấp nhận publish; nếu message unroutable cần xử lý publisher returns/`mandatory` hoặc topology phù hợp. Publisher confirm thành công không chứng minh event đã đến đúng consumer hoặc đã commit vào DB.

## 6. JMS và các hệ thống khác: ý nghĩa ack phụ thuộc session

Với JMS, lựa chọn acknowledgement mode và transaction của **Session** ảnh hưởng khả năng giao lại:

| JMS mode | Đặc điểm | Rủi ro hiểu sai |
| --- | --- | --- |
| `AUTO_ACKNOWLEDGE` | Session/container xác nhận theo vòng đời nhận/đọc callback | Thành công của callback không nhất thiết tương đương các tác vụ `@Async` đã xong |
| `CLIENT_ACKNOWLEDGE` | Ứng dụng gọi `message.acknowledge()` | Acknowledge thường có tác dụng lên **các message đã nhận trong cùng Session**, không chỉ một message riêng lẻ |
| `DUPS_OK_ACKNOWLEDGE` | Cho phép xác nhận lười và có thể giao trùng | Cần idempotency |
| `SESSION_TRANSACTED` | `Session.commit()`/`rollback()` quản lý transaction JMS | Không mặc nhiên là transaction nguyên tử với PostgreSQL |

Spring JMS listener container có chế độ session transacted và transaction manager; cách commit/rollback cụ thể phụ thuộc cấu hình container và nhà cung cấp JMS. Tránh trộn nhận thức giữa **JMS local transaction**, **database transaction** và **XA/JTA distributed transaction**. Nếu muốn atomic cross-resource thật, phải có cơ chế phối hợp giao dịch tương ứng và đánh đổi hiệu năng/độ phức tạp; trong nhiều luồng tích hợp, inbox/outbox đơn giản và đáng kiểm soát hơn.

Với Apache Pulsar hoặc các broker hỗ trợ subscription acknowledgment, cũng cần tách **ack của consumer** khỏi commit dữ liệu ngoài broker; hành vi ack tích lũy, negative acknowledgment, redelivery và thứ tự tùy subscription type, batching và phiên bản client. Không áp dụng cơ học kết luận “ack một record = commit một offset Kafka” cho mọi nền tảng.

## 7. Sai thứ tự: phân biệt thứ tự broker với thứ tự nghiệp vụ

**Ordered delivery** là broker giao message theo một quy tắc nào đó. **Ordered processing** là listener xử lý tuần tự. **Ordered effects** là trạng thái cuối trong hệ thống phản ánh đúng thứ tự nghiệp vụ. Ba điều này khác nhau.

Ví dụ:

~~~text
orderId = ORD-1024
event version 5: CREATED
event version 6: CONFIRMED
event version 7: PAID

Consumer A nhận version 7; ghi DB nhanh.
Consumer B retry version 5; ghi DB muộn.
Nếu UPDATE không có điều kiện version, DB trở lại CREATED.
~~~

Ba biện pháp thường kết hợp:

1. **Định tuyến theo khóa ổn định.** Với Kafka, chọn message key là `orderId` để các sự kiện của một đơn hàng vào cùng partition (với topology/partition count phù hợp); không dùng event ID ngẫu nhiên làm key khi cần tuần tự theo entity.
2. **Hạn chế xử lý song song trên cùng entity.** Dùng consumer/partition assignment phù hợp, kiểm soát executor, retry và rebalance; không giả định một queue có nhiều consumer vẫn giữ thứ tự hiệu ứng.
3. **Kiểm soát phiên bản nghiệp vụ.** Dùng `version`, sequence number hoặc CAS/optimistic locking trong DB để từ chối update cũ. Với event là delta bắt buộc đủ bước, cần phát hiện gap, đợi/replay hoặc đưa vào vùng cách ly.

**Idempotency chỉ giải quyết trùng**, chưa giải quyết out-of-order. Một event ID chưa từng thấy vẫn có thể **cũ hơn** trạng thái hiện có. Ngược lại, kiểm tra version đơn thuần chưa đủ chống việc phát email trùng hoặc debit trùng khi retry.

Đặc biệt trong luồng HTTP → broker → DB → cache: nếu ghi cache trước khi commit database hoặc không gắn version/invalidation phù hợp, cache có thể phản ánh trạng thái mới rồi bị callback cũ ghi đè. Từng adapter phải định rõ ai là nguồn chân lý và thời điểm cập nhật cache.

## 8. Quy trình điều tra sự cố mất, trùng, sai thứ tự

### Bước 1 — Lấy một event làm mẫu và dựng timeline

Chọn event có `eventId`, `businessKey` (ví dụ `orderId`), `version` và `traceId` rõ ràng. Kết hợp log producer, broker, consumer và database theo thời gian:

~~~text
10:00:00.001 producer publish eventId=evt-8192
10:00:00.013 broker append (topic, partition=2, offset=351)
10:00:00.021 consumer receive (group=order-projector)
10:00:00.030 DB BEGIN
10:00:00.044 DB COMMIT success
10:00:00.045 consumer ack/commit attempt
10:00:00.047 commit result: timeout/unknown
10:00:02.100 consumer receive again (same eventId)
10:00:02.103 duplicate key -> skip safely
~~~

Không ghi toàn bộ payload có thông tin nhạy cảm ra log. Các trường hữu ích: `eventId`, `orderId`, `version`, `topic`, `partition`, `offset`, `consumerGroup`, `deliveryTag` (RabbitMQ), `redelivered`, `attempt`, `transactionId`, thời gian bắt đầu/kết thúc và kết quả commit.

### Bước 2 — Trả lời bốn câu hỏi ở đúng ranh giới

1. **Broker thật sự đã nhận và lưu/routе message chưa?** Xem Kafka producer acks/error, RabbitMQ publisher confirm/returns, quyền và topology.
2. **Consumer có nhận message không?** Xem group assignment, committed offset vs current position/lag; với RabbitMQ xem ready/unacked, số consumer, redelivery và DLQ.
3. **DB hoặc hệ đích đã commit gì?** Đối chiếu transaction log/record nghiệp vụ, bảng inbox/idempotency, outbox; không dùng duy nhất log “process success”.
4. **Ack/offset commit xảy ra lúc nào?** Xác định ack mode thật, thread thực thi, error handler, retry/DLT recovery và điều kiện commit trong container.

### Bước 3 — Đối chiếu dấu hiệu với nguyên nhân

| Dấu hiệu quan sát | Nghi vấn chính | Hành động xác minh |
| --- | --- | --- |
| Committed offset đã vượt event, DB không có thay đổi | Auto-commit hoặc ack trước DB commit; handler coi lỗi là thành công | Đối chiếu timeline, transaction và vị trí gọi ack |
| DB có thay đổi hai lần, event ID giống nhau | Redelivery sau DB commit nhưng trước ack; thiếu idempotency | Kiểm tra unique key/inbox, offset/ack error và crash |
| Kafka vẫn còn record nhưng group không đọc lại | Offset đã commit; reset policy không áp dụng vì group có offset | Kiểm tra committed offset và kế hoạch replay có kiểm soát |
| RabbitMQ queue có nhiều unacked kéo dài | Manual ack bị bỏ sót, xử lý treo, prefetch quá lớn | Xem channel, delivery tag, thread và timeout |
| RabbitMQ ready/requeued tăng nhanh | Requeue vô hạn trên poison message | Cấu hình giới hạn retry, backoff, DLQ, kiểm tra lỗi payload |
| Trạng thái mới bị đè bởi trạng thái cũ | Partition key không ổn định, retry hoặc concurrency, thiếu version check | Kiểm tra key, version và đường xử lý song song |
| Sau nâng cấp mới mất message vào DLT | Error handler/ackAfterHandle/recoverer thay đổi hành vi | Xem release notes phiên bản, cấu hình recovery và DLT publish |
| DLT có message nhưng consumer group tiếp tục | Framework đã coi record được recover | Xem quy định replay từ DLT, giám sát và SLA |

### Bước 4 — Sửa đường đi dữ liệu, không chỉ tăng retry

- Chuyển ack/offset commit sang sau khi transaction nghiệp vụ hoàn tất; với bất đồng bộ cần chờ kết quả bền vững hoặc ghi inbox trước.
- Đưa `eventId` hoặc business idempotency key vào unique constraint/atomic insert; không dựa vào một cache kiểm tra tồn tại không có tính nguyên tử.
- Thêm version check, quy tắc xử lý gap và key routing cho entity cần đúng thứ tự.
- Chuẩn hóa retry có giới hạn, backoff, phân loại lỗi, DLT/quarantine và quy trình replay; khi khôi phục phải giữ cùng idempotency key.
- Nếu publish sang broker khác sau khi ghi DB, cân nhắc **transactional outbox**: ghi dữ liệu nghiệp vụ + outbox trong một DB transaction, worker publish rồi đánh dấu đã gửi; consumer downstream vẫn phải idempotent vì publish có thể lặp.

## 9. Sau khi nâng cấp Spring Boot, Spring Kafka hoặc Spring AMQP

Nâng cấp có thể thay default, bean configuration, error handler, transaction integration và cách hoàn thành listener. Không nên mặc định mọi vấn đề sau nâng cấp do broker giữ sai dữ liệu.

### Danh sách cần đối chiếu theo phiên bản

| Thành phần | Điều phải kiểm tra | Ảnh hưởng nếu sai |
| --- | --- | --- |
| Spring Kafka `AckMode` và `enable.auto.commit` | Container factory đang dùng, bean custom, config override | Offset commit sai thời điểm |
| Kafka error handler / recoverer / DLT | Retry/backoff, `ackAfterHandle`, commit recovered offset | Bỏ qua record lỗi hoặc lặp mãi |
| Kafka transactions | Transaction manager, producer ID, isolation level, offset gửi vào transaction | Đọc record abort hoặc cam kết sai phạm vi |
| Kafka concurrency / polling | `max.poll.interval.ms`, `max.poll.records`, executor, partition reassignment | Rebalance, duplicate và thứ tự hiệu ứng |
| Spring AMQP listener ack mode | `AUTO`/`MANUAL`/`NONE`, loại listener container, error handler | Ack sớm hoặc delivery treo |
| RabbitMQ retry/DLX/prefetch | `defaultRequeueRejected`, DLX, `prefetch`, policy | Poison loop hoặc message bị loại bỏ |
| JMS session transaction | Acknowledgment mode, `sessionTransacted` và transaction manager | Xác nhận không nhất quán với DB |
| DB transaction và async | Proxy `@Transactional`, propagation, `@Async`/Reactor subscribe | Ack trước khi commit thực |

**Chiến lược nâng cấp an toàn:** ghim phiên bản dependency phù hợp BOM của Spring Boot, đọc release notes cho thành phần bị thay đổi, chụp lại cấu hình listener container thực tế, so sánh hành vi trước–sau với cùng bộ sự kiện, rồi bật metric/cảnh báo sau rollout. Nếu thay listener từ đồng bộ sang reactive/asynchronous, phải quyết định ai chờ completion và ai gọi ack; một `Mono`/`CompletableFuture` vừa được tạo chưa có nghĩa side effect đã hoàn tất.

Không thể đảm bảo mọi lỗi bằng cách chỉ tăng retention, thêm replica hoặc đổi retry count. Cần xác định **mốc commit nghiệp vụ** và **mốc broker ghi nhận tiến độ** trước.

## 10. Kịch bản kiểm thử lỗi thực tế

Trong môi trường tích hợp riêng với broker thật (có thể dùng Testcontainers) và database test, mỗi ca phải kiểm chứng **record nghiệp vụ, inbox/idempotency, offset/ack, số lần tác dụng phụ, DLT và thứ tự phiên bản**:

| Ca thử | Cách tạo tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Crash trước DB commit | Ném exception khi transaction chưa hoàn tất | Không có cập nhật DB; record còn cơ hội được xử lý lại |
| Crash sau DB commit trước ack | Chèn điểm lỗi ngay sau khi service trả về | Event được phát lại nhưng unique event ID ngăn hiệu ứng trùng |
| Timeout khi ack/commit offset | Mô phỏng mất mạng hoặc rebalance tại commit | Xử lý trạng thái không rõ; redelivery vẫn an toàn |
| JSON sai hợp đồng | Gửi payload thiếu field hoặc sai kiểu | Được quarantine/DLT theo policy, có cảnh báo, không vòng lặp vô hạn |
| Sự kiện trùng | Gửi hai record cùng `eventId` | Một hiệu ứng nghiệp vụ |
| Sự kiện ngược thứ tự | Gửi version 7 rồi version 5 cho cùng `orderId` | Trạng thái cuối vẫn version 7 |
| Xử lý bất đồng bộ | Tạo task chạy chậm hoặc thất bại sau callback | Không ack khi chưa có commit bền vững |
| Rebalance | Dừng một consumer khi đang xử lý; thêm consumer mới | Không bỏ sót message, duplicate được xử lý idempotent |
| RabbitMQ poison retry | Một message gây lỗi lặp đi lặp lại | Retry có giới hạn rồi vào DLQ, không nghẽn consumer |
| Publish qua broker thứ hai | DB commit xong nhưng lần publish đầu thất bại | Outbox được retry; downstream không tạo tác dụng phụ trùng |

Nếu hệ thống có người dùng hoặc tác vụ đối tác nhạy cảm, chỉ làm thử nghiệm crash/replay trong môi trường kiểm thử có dữ liệu giả. Khi cần replay production, khoanh vùng consumer group, thời gian và batch message; dự báo tác dụng phụ, không reset offset hàng loạt nếu chưa kiểm tra idempotency.

## 11. Bài tập chẩn đoán và câu hỏi tự kiểm tra

**Tình huống A — “Kafka nuốt mất đơn hàng”.** Listener poll offset 201, gọi `acknowledge()` rồi khởi chạy `@Async` ghi database. Process crash; offset 202 đã commit, DB chưa có đơn. Gốc lỗi là **xác nhận tiến độ sớm hơn kết quả bền vững**. Sửa bằng xử lý đồng bộ/đợi completion, hoặc ghi một inbox bền vững rồi ack; bổ sung kiểm tra idempotency để chịu redelivery.

**Tình huống B — “Một webhook được xử lý hai lần”.** DB commit, nhưng `basicAck` RabbitMQ chưa đến broker do mất connection. Message được giao lại. Không thể kết luận broker vi phạm; trường hợp này phù hợp **at-least-once**. Dùng event ID ổn định và unique constraint ở cùng transaction với cập nhật nghiệp vụ.

**Tình huống C — “Đơn đã trả tiền trở về trạng thái mới tạo”.** Event `version=7` xử lý trước `version=5` do retry và concurrency; cả hai ID đều khác nhau, nên inbox chống trùng vẫn cho qua. Sửa bằng version check hoặc xử lý đúng thứ tự/gap theo hợp đồng sự kiện.

**Tự kiểm tra:**

1. **Kafka producer `acks=all` có nghĩa consumer đã ghi database chưa?** Chưa; đó là xác nhận publish theo chính sách của Kafka.
2. **Commit offset `58` có nghĩa xử lý record offset 58 xong chưa?** Không; nó chỉ lưu vị trí đọc tiếp là 58.
3. **Tại sao ack sau DB commit vẫn có thể nhận lại message?** Vì crash hoặc timeout giữa DB commit và ack khiến broker không biết chắc tiến độ.
4. **Spring AMQP `AUTO` có đồng nghĩa RabbitMQ `autoAck=true` không?** Không; AUTO của container thường ack sau listener thành công.
5. **Idempotency key có tự giữ đúng thứ tự không?** Không; cần thêm ordering key, version check hoặc gap handling.
6. **Kafka transaction có bảo đảm gửi email exactly-once không?** Không; phạm vi transaction Kafka không tự bao gồm hệ thống email.

Khi gỡ lỗi, hãy lập timeline có bằng chứng cho **publish → deliver → xử lý → DB commit → broker ack/offset commit**. Khi thiết kế luồng mới, chọn **ack sau commit nghiệp vụ**, bổ sung **idempotency** để an toàn với phát lại và **version/ordering policy** để giữ đúng trạng thái. Ba quyết định này giúp xác định được cơ chế mất, trùng và sai thứ tự ở từng ranh giới tích hợp thay vì chỉ dựa vào log “đã nhận message”.
