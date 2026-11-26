# Thời hạn xác nhận của consumer và thời gian xử lý kéo dài

## 1. Một consumer vẫn chạy nhưng RabbitMQ đã giao lại công việc

Với **Spring AMQP**, producer có thể gửi thông điệp bằng `RabbitTemplate.convertAndSend(...)`; RabbitMQ định tuyến qua **exchange**, **routing key** và **binding** vào **queue**; consumer sử dụng `@RabbitListener` để xử lý và gửi xác nhận (ACK). Nếu phương thức listener mất nhiều phút, người học thường cho rằng RabbitMQ sẽ đợi vô hạn miễn là chương trình Java vẫn hoạt động. Điều đó **không luôn đúng**.

RabbitMQ có cơ chế **consumer delivery acknowledgement timeout** (thường được gọi ngắn là **consumer timeout** hoặc **ACK timeout**). Khi một delivery cần ACK bị giữ quá thời hạn do broker quy định, broker có thể đóng channel với lỗi **`PRECONDITION_FAILED`**. Các delivery chưa ACK gắn với channel đó có thể được đưa trở lại để giao cho consumer khác. Trong khi ấy, luồng Java đang xử lý nghiệp vụ có thể vẫn đang chạy hoặc đang cố commit database.

Ví dụ giả định:

~~~text
09:00  RabbitMQ giao event evt-1001 cho Consumer A.
09:00  Spring @RabbitListener bắt đầu tạo báo cáo lớn.
09:30  Delivery vẫn chưa ACK, ngưỡng timeout của broker bị vượt.
09:31  Broker kiểm tra timeout, đóng channel của A.
09:31  Message chưa ACK có thể được requeue/redeliver tới Consumer B.
09:32  A hoàn tất ghi dữ liệu, nhưng ACK qua channel cũ không còn hợp lệ.
09:33  B có thể đang thực hiện lại cùng evt-1001.
~~~

Các mốc thời gian chỉ minh họa. Thời điểm kiểm tra timeout có thể lệch so với ngưỡng cấu hình vì broker thực hiện kiểm tra định kỳ. Vấn đề thật sự là **một event có thể đang được xử lý đồng thời hoặc tuần tự nhiều lần sau lỗi channel**, không phải chỉ đơn giản “listener chậm nên phải tăng timeout”.

**Điểm cần nhớ:**

> ACK timeout là **chính sách bảo vệ consumer ở phía RabbitMQ**, không phải giới hạn thời gian chạy Java method do Spring tự đặt. Khi quá hạn, broker có thể đóng channel và giao lại **những delivery chưa được xác nhận**. Do đó cần phối hợp timeout, prefetch, transaction, idempotency và mô hình xử lý công việc dài.

Bài thuộc chương **Xác nhận tiêu thụ** của module **Spring AMQP**; tập trung vào cơ chế timeout khi nhận message, cách xử lý job kéo dài, cấu hình RabbitMQ/Spring, các lựa chọn kiến trúc đáng tin cậy và cách quan sát lỗi.

## 2. Phân biệt bốn loại “timeout” thường gặp

Không phải timeout nào cũng liên quan đến ACK của consumer:

| Cơ chế | Bên đặt/giám sát | Điều gì được giới hạn? | Khi quá hạn có thể xảy ra gì? |
| --- | --- | --- | --- |
| **Consumer delivery acknowledgement timeout** | RabbitMQ broker | Thời gian một delivery còn chờ ACK theo chính sách broker. | Broker đóng channel, requeue các delivery chưa ACK tùy tình trạng queue/channel. |
| **AMQP heartbeat timeout** | Client và broker | Phát hiện connection không còn trao đổi heartbeat/network phù hợp. | Connection bị xem là không còn sống và đóng. |
| **Connection timeout** | RabbitMQ client / Spring configuration | Thời gian cố thiết lập TCP/AMQP connection. | Producer/consumer không mở được connection đúng hạn. |
| **Business/DB/API timeout** | Ứng dụng và dịch vụ phụ thuộc | Giới hạn thời gian query, HTTP call hoặc transaction. | Exception trong listener, rollback/retry theo code. |
| **Publisher confirm timeout** | Ứng dụng producer, nếu có deadline riêng | Thời gian chờ broker xác nhận một lần publish. | Producer chưa biết kết quả publish, phải đối soát/retry an toàn. |
| **Message TTL** | RabbitMQ queue/message policy | Thời gian message đủ điều kiện tồn tại trong queue trước khi expire. | Có thể expire/dead-letter; **không phải** consumer ACK deadline. |

**Ví dụ dễ nhầm:** Một consumer chạy job 40 phút nhưng connection luôn có heartbeat đều đặn. Heartbeat chỉ cho thấy connection còn trao đổi tín hiệu, **không làm mới thời hạn ACK** của một delivery đã nhận. Nếu consumer timeout là 30 phút, channel vẫn có thể bị đóng dù heartbeat bình thường.

Ngược lại, một listener xử lý nhanh có thể chưa gửi ACK nếu code dùng **manual ACK**, batch ACK, giữ transaction lâu hoặc quên xác nhận. Broker không biết logic Java “đã xong”; nó chỉ biết **ACK frame thực sự tới channel hay chưa**.

## 3. Ready, Unacknowledged, ACK và Redelivery

### 3.1. Vòng đời message theo cơ chế có ACK

~~~mermaid
flowchart TD
    P["RabbitTemplate publish"]
    X["Exchange + binding"]
    Q["Queue: READY"]
    U["Delivery: UNACKNOWLEDGED"]
    L["@RabbitListener xử lý"]
    DB["Database / side effect"]
    ACK["Consumer ACK"]
    TIME{"Vượt consumer ACK timeout?"}
    CLOSE["Broker đóng channel<br/>PRECONDITION_FAILED"]
    RE["Requeue / redelivery<br/>delivery chưa ACK"]
    DL["Reject / dead-letter<br/>theo policy"]
    P --> X --> Q --> U --> L --> DB --> ACK
    U --> TIME
    TIME -- "Có" --> CLOSE --> RE --> Q
    L -. "Reject không requeue" .-> DL
~~~

Sơ đồ khái niệm, không phải lịch trình frame chính xác của tất cả biến thể listener. ACK và timeout có thể **đua nhau**: nếu ACK chưa được broker xử lý trước lúc channel bị đóng, phía client không nên mặc định message đã được xác nhận.

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Messages Ready** | Message sẵn sàng giao trong queue. |
| **Messages Unacknowledged** | Delivery đã giao nhưng broker chưa nhận ACK/NACK kết thúc phù hợp. |
| **Consumer ACK** | Consumer xác nhận một hoặc nhiều delivery trên channel. |
| **Consumer NACK/Reject** | Consumer từ chối delivery, có thể yêu cầu requeue hoặc dead-letter tùy cấu hình. |
| **Redelivery** | RabbitMQ có thể giao lại message chưa ACK sau connection/channel mất hoặc requeue. |
| **Delivery tag** | Số nhận diện delivery **theo channel** để ACK/NACK, không phải logical event ID. |

**Ready giảm không có nghĩa job hoàn thành.** Với `prefetch=20`, broker có thể đã chuyển 20 delivery tới consumer dù listener xử lý tuần tự; tất cả đang tính thời gian chờ ACK theo cơ chế broker liên quan, kể cả delivery chưa bắt đầu được method xử lý thực sự.

### 3.2. Channel bị đóng tác động cả những delivery khác

Khi broker đóng một channel do lỗi acknowledgement timeout, hậu quả không chỉ nhất thiết giới hạn ở **message đầu tiên bị chậm**. **Những delivery còn unacknowledged trên channel đó** có thể phải được đưa trở lại để giao lại, làm tăng lượng công việc và khả năng duplicate. Nếu consumer dùng chung channel với nhiều delivery, phạm vi ảnh hưởng có thể lớn hơn một job.

Đây là lý do phải tính **prefetch** cùng thời gian xử lý, thay vì chỉ xem thời gian của job riêng lẻ.

## 4. RabbitMQ consumer acknowledgement timeout hoạt động thế nào?

### 4.1. Broker kiểm tra delivery đã chờ ACK quá lâu

Trong RabbitMQ, cơ chế này bảo vệ broker khỏi việc consumer nhận message nhưng **không xác nhận quá lâu**, đặc biệt khi có những delivery giữ tài nguyên queue hoặc ảnh hưởng tiến độ. Broker kiểm tra timeout theo chu kỳ; các tài liệu RabbitMQ hiện đại mô tả việc kiểm tra định kỳ khoảng **mỗi phút**, vì vậy việc đóng channel có thể xảy ra **sau** mốc timeout danh nghĩa, không đúng từng millisecond.

Khi vượt ngưỡng, một lỗi thường gặp trong broker log có dạng:

~~~text
PRECONDITION_FAILED - delivery acknowledgement on channel ... timed out.
Timeout value used: 1800000 ms.
~~~

Chuỗi chi tiết thay đổi theo phiên bản và ngữ cảnh. Broker có thể ghi consumer/channel, delivery tag và thời gian đã chờ; client Spring AMQP có thể báo `ShutdownSignalException`, channel shutdown hoặc các exception liên quan. **Hãy đọc nguyên nhân từ RabbitMQ broker log và client log cùng thời điểm**, không chỉ kết luận từ exception bao ngoài.

### 4.2. Giá trị mặc định và phạm vi cấu hình

Trong nhiều bản RabbitMQ gần đây, ngưỡng mặc định thường được công bố là **30 phút (1.800.000 ms)** nếu không được cấu hình khác. Tuy nhiên, **mặc định, nơi có thể override và loại queue được hỗ trợ có thể thay đổi theo phiên bản RabbitMQ**. Hãy kiểm tra cấu hình broker đang chạy trước khi đưa ra giới hạn cho production.

Ví dụ cấu hình **toàn broker** trong `rabbitmq.conf`:

~~~ini
# RabbitMQ broker configuration; đơn vị: milliseconds.
consumer_timeout = 1800000
~~~

Ví dụ ngưỡng **5 phút** cho bài lab (chỉ nên dùng nơi được phép điều chỉnh):

~~~ini
consumer_timeout = 300000
~~~

**Không đặt giá trị 10 giây rồi kỳ vọng broker luôn đóng channel đúng 10 giây.** RabbitMQ kiểm tra định kỳ, các giá trị cực thấp không phù hợp/không được hỗ trợ ở nhiều phiên bản; tài liệu khuyến nghị không dùng nhỏ hơn vài phút. Đồng thời, ngưỡng quá cao che giấu consumer bị treo và có thể khiến unacked tồn tại lâu.

Một số phiên bản hỗ trợ cấu hình timeout **theo queue** thông qua policy `consumer-timeout` hoặc queue argument `x-consumer-timeout`. Cú pháp áp dụng và mức hỗ trợ theo **classic/quorum queue** phụ thuộc phiên bản RabbitMQ; không giả định mọi môi trường RabbitMQ đều có cùng hành vi.

### 4.3. Không có “ACK heartbeat” để gia hạn delivery

Trong AMQP 0-9-1, message ACK là thao tác **xác nhận đã xử lý delivery**, không phải tín hiệu “tôi vẫn đang làm, cho tôi thêm 5 phút”. **AMQP connection heartbeat**, log tiến độ, hoặc ghi `lastProgressAt` vào DB **không gia hạn tự động consumer acknowledgement timeout**.

Không nên gọi `basicAck` trước khi công việc hoàn thành chỉ để tránh timeout, trừ khi đã thiết kế **bàn giao công việc bền vững** sang một hệ thống khác và việc ACK lúc đó mang đúng ý nghĩa đã nhận trách nhiệm.

## 5. Thời hạn ACK bắt đầu trước khi method listener chạy xong

Một ngộ nhận là timeout bắt đầu khi code gọi `processOrder()`. Trên thực tế, RabbitMQ giám sát **delivery chưa được xác nhận**, tức thời gian chờ có thể bao gồm:

- Thời gian broker đã giao message nhưng nó đang chờ trong client/container do prefetch.
- Thời gian method `@RabbitListener` đang chạy.
- Thời gian retry đồng bộ ngay trong method/advice.
- Thời gian chờ database commit, outbound HTTP call hoặc lock.
- Thời gian ACK bị trì hoãn bởi batch acknowledgement.

### 5.1. Ví dụ prefetch khiến message chưa chạy đã gần timeout

Giả sử:

~~~text
RabbitMQ consumer timeout: 30 phút
prefetch: 4
consumer concurrency: 1
mỗi message mất 10 phút xử lý
container xử lý các delivery theo thứ tự:

T0: broker giao m1, m2, m3, m4 (đều unacked).
T0–T10: xử lý m1 -> ACK.
T10–T20: xử lý m2 -> ACK.
T20–T30: xử lý m3 -> ACK.
T30+: m4 mới bắt đầu hoặc sắp bắt đầu xử lý.
~~~

**m4 đã được giao khoảng 30 phút dù method cho m4 hầu như chưa chạy**. Mức độ và thời điểm broker đóng channel phụ thuộc phiên bản/chu kỳ kiểm tra/ACK timing, nhưng ví dụ cho thấy vì sao `prefetch=4` có thể không phù hợp với job kéo dài 10 phút mỗi cái.

Nếu giảm `prefetch=1`, consumer không giữ trước ba message nữa; broker chỉ giao job mới khi job trước được ACK. Điều đó **giảm số delivery đang đếm thời gian chờ**, nhưng vẫn **không cứu được job đơn lẻ dài hơn timeout**.

### 5.2. Ước lượng để lập ngân sách

Một phép tính sơ bộ cho consumer xử lý tuần tự:

\[
\text{Thời gian chờ của delivery thứ }k
\approx \sum_{i=1}^{k-1} t_i + t_k + t_{\text{ACK}}
\]

Trong đó `t_i` là thời gian xử lý từng delivery trước đó và `t_ACK` là phần trễ để broker nhận ACK. Nếu prefetch đủ lớn để cấp `k` delivery từ sớm, số hạng **chờ các job đứng trước** cũng đáng kể.

Đây chỉ là **mô hình ước lượng**: thời điểm RabbitMQ gửi từng delivery, concurrency, client buffering, prefetch policy, ACK batching và queue type thay đổi kết quả thực. Không lấy tổng đó làm cam kết broker sẽ đóng channel chính xác lúc nào.

## 6. Spring AUTO, MANUAL và NONE: ACK thực sự được gửi khi nào?

### 6.1. So sánh chế độ

| `AcknowledgeMode` | Khi nào gửi ACK? | Quan hệ với consumer timeout |
| --- | --- | --- |
| **AUTO** | Spring listener container thường ACK sau khi method hoàn thành **thành công**, theo cấu hình batching/transaction liên quan. | Method hoặc transaction quá lâu có thể vượt broker ACK timeout. |
| **MANUAL** | Code hoặc thành phần được ủy quyền gọi `basicAck/basicNack/basicReject`. | Quên ACK, ACK muộn hoặc xử lý nền không ACK khiến delivery giữ unacked. |
| **NONE** | Broker nhận tiêu thụ kiểu auto-ack; không chờ ACK thủ công sau xử lý. | Không cùng cơ chế unacked/timeout ACK như AUTO/MANUAL, nhưng có nguy cơ mất message khi xử lý thất bại. |

`spring.rabbitmq.listener.simple.acknowledge-mode: auto` là **Spring container AUTO**, không phải `autoAck=true` của AMQP. Với AUTO, nếu method ném exception thì container quyết định reject/requeue theo error handling; với NONE, broker có thể coi delivery đã được chấp nhận ngay khi giao, không chờ method xử lý thành công.

### 6.2. Vì sao MANUAL có rủi ro lớn hơn khi xử lý dài?

Khi bật MANUAL, một lệnh `basicAck` bị quên có thể giữ delivery unacked dù nghiệp vụ đã hoàn tất. Khi tổng unacked chạm prefetch, broker ngừng cấp thêm; đến khi consumer timeout, broker có thể đóng channel. Các trường hợp thường gây lỗi:

- Có nhánh `return` bỏ qua ACK/NACK.
- Bắt exception rồi chỉ log, không phản hồi broker.
- Đưa job vào `CompletableFuture.runAsync(...)`, method trả về nhưng không có ai quản lý ACK.
- Dùng raw `Channel` sau khi thread/channel đã bị đóng.
- ACK nhiều lần hoặc ACK delivery tag không thuộc channel tương ứng.

Manual ACK hữu ích khi cần kiểm soát phức tạp, nhưng nếu không có yêu cầu cụ thể, **AUTO với transaction boundary rõ ràng** thường đơn giản và an toàn vận hành hơn.

### 6.3. Async listener không tự giải quyết thời hạn

Spring AMQP hỗ trợ một số kiểu **asynchronous return types** cho `@RabbitListener` với cơ chế ACK phù hợp theo phiên bản. Nếu dùng `CompletableFuture`, `Mono` hoặc API bất đồng bộ khác, cần đọc contract phiên bản Spring AMQP và xác minh **ACK diễn ra khi tác vụ thật sự hoàn tất**. Không giả định method “return một future ngay” đồng nghĩa broker đã nhận ACK.

Nếu future chạy 45 phút trong khi broker timeout là 30 phút, rủi ro timeout vẫn còn. Chuyển sang async API chỉ thay thread chờ, **không tự gia hạn ACK deadline**.

## 7. Cấu hình Spring Boot để điều tiết thời gian giữ delivery

Ví dụ **Spring Boot 3.x / Spring AMQP 3.x**, Java 17+, RabbitMQ AMQP 0-9-1:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
}
~~~

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
    requested-heartbeat: 30s
    listener:
      type: simple
      simple:
        acknowledge-mode: auto
        prefetch: 1
        concurrency: 2
        max-concurrency: 4
~~~

Ở đây:

- `prefetch=1` giảm lượng message một consumer giữ trước khi ACK, phù hợp để **thử nghiệm** tác vụ dài.
- `concurrency=2` tạo hai consumer lúc khởi đầu; `max-concurrency=4` cho phép Simple container mở rộng theo tải, nếu các điều kiện scale được đáp ứng.
- `acknowledge-mode=auto` giúp container gửi ACK sau khi listener xử lý thành công.
- `requested-heartbeat=30s` chỉ điều chỉnh **AMQP heartbeat**, không gia hạn thời hạn ACK.

**Không có thuộc tính Spring Boot `spring.rabbitmq.listener.simple.consumer-timeout` phổ quát để thay đổi RabbitMQ broker ACK timeout.** Ngưỡng acknowledgement timeout được broker kiểm soát; đặt ở `rabbitmq.conf` hoặc cơ chế policy/queue argument được hỗ trợ ở phiên bản RabbitMQ thực tế.

Tài khoản `guest/guest` chỉ dành cho RabbitMQ demo cục bộ; ở production dùng user/vhost riêng, quyền phù hợp, TLS và bảo vệ secrets.

### 7.1. Simple và Direct listener container

Spring AMQP có `SimpleMessageListenerContainer` và `DirectMessageListenerContainer`. Chúng khác nhau ở mô hình luồng, cách quản lý consumer và cấu hình concurrency.

Trong Spring Boot, Direct container có ví dụ:

~~~yaml
spring:
  rabbitmq:
    listener:
      type: direct
      direct:
        acknowledge-mode: auto
        prefetch: 1
        consumers-per-queue: 2
~~~

Đây là **cấu hình thay thế** cho block Simple ở trên, không gộp cả hai vào một ý nghĩa. Dù chọn Simple hay Direct, nếu consumer ACK quá muộn so với chính sách broker thì channel vẫn có thể bị đóng. Chuyển loại container không tự giải quyết job quá dài.

### 7.2. Tăng concurrency có giải quyết timeout không?

Nếu nhiều message đang chờ ở queue và từng job tương đối độc lập, tăng số consumer có thể giảm thời gian message chờ **trước khi được giao**. Tuy nhiên:

- Nó không rút ngắn một job riêng lẻ 40 phút xuống dưới timeout 30 phút.
- Nó tăng tải database, CPU, downstream và số message có thể đang unacked.
- Nếu prefetch lớn, mỗi consumer vẫn có thể giữ nhiều delivery chờ ACK.
- Với job cần xử lý theo thứ tự, tăng concurrency có thể làm thứ tự hoàn tất khác thứ tự publish.

Nên tuning **prefetch, concurrency và xử lý nghiệp vụ** như ba biến riêng biệt, dựa trên metrics thay vì tăng tất cả cùng lúc.

## 8. Khai báo exchange, queue và consumer thử nghiệm

### 8.1. Topology tối giản

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LongJobTopology {
    public static final String EXCHANGE = "jobs.events";
    public static final String QUEUE = "jobs.requested.q";
    public static final String ROUTING_KEY = "job.requested";

    @Bean
    DirectExchange jobsExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue jobsQueue() {
        return QueueBuilder.durable(QUEUE).build();
    }

    @Bean
    Binding jobsBinding(Queue jobsQueue, DirectExchange jobsExchange) {
        return BindingBuilder.bind(jobsQueue)
                .to(jobsExchange)
                .with(ROUTING_KEY);
    }
}
~~~

Khi `RabbitAdmin` được cấu hình phù hợp, Spring có thể khai báo queue, exchange, binding. Một queue durable chỉ bảo đảm **định nghĩa queue** có thể tồn tại qua restart theo điều kiện hỗ trợ; sự bền vững của message còn phụ thuộc delivery mode, confirms, queue type, replication và sự cố thực tế.

### 8.2. Producer gửi job ID ổn định

~~~java
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class LongJobPublisher {
    private final RabbitTemplate rabbitTemplate;

    public LongJobPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(String jobId) {
        rabbitTemplate.convertAndSend(
                LongJobTopology.EXCHANGE,
                LongJobTopology.ROUTING_KEY,
                jobId,
                message -> {
                    message.getMessageProperties().setMessageId(jobId);
                    message.getMessageProperties()
                            .setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                    return message;
                }
        );
    }
}
~~~

Giữ **`jobId` không đổi** khi retry cùng logical job. Nếu cần biết broker đã nhận và định tuyến thành công, kết hợp **publisher confirms** và **mandatory returns**; lời gọi `convertAndSend` không ném exception chưa đủ chứng minh consumer đã xử lý.

### 8.3. Listener chậm minh họa

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class SlowJobListener {

    @RabbitListener(queues = LongJobTopology.QUEUE)
    public void handle(String jobId) throws InterruptedException {
        // CHỈ DÙNG TRONG LAB: giả lập tác vụ lâu.
        Thread.sleep(6 * 60 * 1_000L);
        System.out.println("Finished job " + jobId);
    }
}
~~~

Nếu broker/queue timeout được cấu hình khoảng 5 phút trong một môi trường thử nghiệm có hỗ trợ, listener ngủ 6 phút có thể khiến broker đóng channel **trước khi container ACK thành công**. Nhưng thời điểm broker phát hiện timeout không chính xác từng giây, vì vậy kết quả phải kiểm chứng qua **broker logs, channel status và redelivery**, không chỉ nhìn một exception.

**Không dùng `Thread.sleep` để xử lý job thật**; ví dụ chỉ phục vụ mô phỏng. Khi cần xử lý lâu, thiết kế theo các hướng ở mục 10–11.

## 9. Cấu hình timeout theo queue: chỉ khi phiên bản hỗ trợ

Một số bản RabbitMQ hỗ trợ queue argument `x-consumer-timeout`. Ví dụ minh họa bằng Spring:

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;

// Chỉ dùng thay thế jobsQueue() ở mục 8 trong lab tương thích.
@Bean
Queue jobsQueueWithTimeout() {
    return QueueBuilder.durable(LongJobTopology.QUEUE)
            .withArgument("x-consumer-timeout", 300_000)
            .build();
}
~~~

**Đừng đăng ký cùng lúc hai bean queue có cùng tên nhưng arguments khác nhau.** Đây là **phương án thay thế** cho định nghĩa queue ở mục 8 và chỉ phù hợp khi RabbitMQ version/queue type hỗ trợ argument. Một số môi trường hỗ trợ cấu hình timeout qua policy, thường thuận tiện hơn cho việc quản lý nhiều queue. Có phiên bản giới hạn chính sách theo queue type.

Nếu queue đã tồn tại với arguments khác, khai báo lại một queue không tương đương có thể dẫn đến **`406 PRECONDITION_FAILED`**. Không xóa queue production chỉ để đổi timeout khi queue đang có message; hãy đánh giá policy/migration và sao lưu kế hoạch thay đổi.

Ví dụ dưới đây là cấu hình broker global, **không đặt vào `application.yml` của Spring Boot**:

~~~ini
# rabbitmq.conf - thay đổi theo chính sách vận hành broker
consumer_timeout = 300000
~~~

**Nguyên tắc:** Thay đổi timeout ở **đúng nơi RabbitMQ thực sự đọc** và xác minh bằng broker logs/config hiệu lực; không giả định sửa YAML phía Java sẽ đổi được ngưỡng broker.

## 10. Ba cách xử lý tác vụ kéo dài

### 10.1. Cách A: tối ưu job để hoàn tất và ACK trong ngưỡng

Nếu công việc thông thường chỉ mất vài giây nhưng đôi lúc thành vài phút:

- Tìm bottleneck ở DB, HTTP downstream, lock contention, file I/O.
- Đặt timeout cho từng dependency để tránh chờ vô hạn.
- Giảm prefetch để hạn chế message bị giữ trước khi xử lý.
- Cân nhắc tăng concurrency khi CPU/DB còn sức và công việc độc lập.
- Chia job quá lớn thành các bước nhỏ có event/ID riêng nếu phù hợp nghiệp vụ.

Ưu điểm: giữ được contract đơn giản “listener xử lý xong mới ACK”. Nhược điểm: nếu job bản chất dài hơn giới hạn an toàn, việc tuning nhỏ lẻ không giải quyết được.

### 10.2. Cách B: tăng consumer timeout có kiểm soát

Tăng timeout có thể phù hợp nếu:

- Job thật sự cần giữ message unacked trong khi xử lý.
- Thời gian xử lý tối đa được biết/giới hạn.
- Broker, queue type và cluster chấp nhận thời gian unacked kéo dài.
- Có giám sát job bị treo, memory và tình huống consumer crash.

Nhưng **tăng timeout không làm job chạy nhanh hơn**, không tránh redelivery khi connection mất và có thể khiến message bị giữ lâu khi consumer thực sự treo. Đừng dùng giá trị cực lớn hoặc tắt cơ chế bảo vệ mà không có hệ thống theo dõi và recovery tương đương.

Nếu phải tăng thời hạn, đặt nó dựa trên **thời gian delivery-to-ACK**, bao gồm chờ prefetch, retry, DB commit và khoảng dự phòng; không chỉ dựa trên thời gian chạy method trung bình.

### 10.3. Cách C: ACK sau khi bàn giao công việc bền vững

Với job thật sự kéo dài hàng chục phút hoặc hàng giờ, một kiến trúc thường tốt hơn là **listener chỉ nhận yêu cầu rồi ghi vào một inbox/job table bền vững**. Sau khi transaction DB commit thành công, listener được phép hoàn thành để container ACK; một worker riêng thực hiện công việc dài và cập nhật trạng thái.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as RabbitTemplate Producer
    participant Q as RabbitMQ Queue
    participant L as @RabbitListener tiếp nhận
    participant DB as Job Inbox DB
    participant W as Background Job Worker
    P->>Q: publish jobId
    Q->>L: deliver jobId
    L->>DB: transaction insert-if-absent(jobId, PENDING)
    DB-->>L: COMMIT
    L-->>Q: Consumer ACK qua Spring AUTO
    W->>DB: Claim job PENDING
    W->>W: Xử lý lâu, cập nhật checkpoint
    W->>DB: DONE / RETRYABLE / FAILED
~~~

Điểm cốt lõi: **ACK ở đây có nghĩa “đã tiếp nhận trách nhiệm vào kho việc bền vững”**, **không** có nghĩa “đã hoàn tất nghiệp vụ cuối cùng”. Điều này chỉ an toàn nếu:

1. Database/queue nội bộ thực sự ghi **bền vững** trước khi listener trả thành công.
2. Job worker có cơ chế khôi phục các job `PENDING/RUNNING` sau crash, chẳng hạn lease và timeout ở job table.
3. `jobId` duy nhất, phép insert idempotent, nhiều lần giao message không tạo hai logical job.
4. Job worker tự có retry/backoff, trạng thái thất bại cuối cùng và cảnh báo.
5. Người dùng/API phân biệt **ACCEPTED** với **COMPLETED**.

**Không thay bằng việc chỉ gọi `executor.submit(...)` rồi ACK ngay**. Thread pool/queue trong RAM có thể mất toàn bộ job khi JVM chết, trong khi RabbitMQ đã nhận ACK và xóa delivery.

## 11. Ví dụ Spring: lưu job vào inbox rồi mới ACK

### 11.1. Listener giữ thời gian giao nhận ngắn

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class JobIntakeListener {
    private final JobInboxService jobInbox;

    public JobIntakeListener(JobInboxService jobInbox) {
        this.jobInbox = jobInbox;
    }

    @RabbitListener(queues = LongJobTopology.QUEUE)
    public void accept(String jobId) {
        // Phải COMMIT bền vững trước khi method trả thành công.
        jobInbox.persistIfAbsent(jobId);
        // Với Spring container AUTO, ACK diễn ra sau thành công.
    }
}
~~~

### 11.2. Transaction và khóa chống trùng

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JobInboxService {
    private final JobRepository repository;

    public JobInboxService(JobRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void persistIfAbsent(String jobId) {
        // Repository phải triển khai INSERT ... ON CONFLICT DO NOTHING
        // hoặc một cơ chế unique constraint/atomic tương đương.
        repository.insertPendingIfAbsent(jobId);
    }
}
~~~

`JobRepository` là abstraction của tầng database, chưa được triển khai trong bài vì SQL/ORM cụ thể phụ thuộc dự án. Dưới đây là ví dụ cấu trúc PostgreSQL:

~~~sql
CREATE TABLE jobs (
    job_id       VARCHAR(100) PRIMARY KEY,
    status       VARCHAR(30) NOT NULL,
    attempts     INTEGER NOT NULL DEFAULT 0,
    lease_until  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Pseudocode SQL do repository dùng trong transaction:
INSERT INTO jobs(job_id, status)
VALUES (:job_id, 'PENDING')
ON CONFLICT (job_id) DO NOTHING;
~~~

Sau khi ghi job với `job_id` duy nhất thành công (hoặc xác định job đã tồn tại), `JobIntakeListener` trả về; container AUTO có thể ACK. Nếu database thất bại trước commit, method ném exception, container **không nên ACK như thành công**.

Để tránh mất việc, worker riêng phải đọc các job `PENDING`, claim bằng transaction/lease, xử lý và đánh dấu `DONE`. Phải có quá trình phục hồi `RUNNING` khi worker chết, không giữ việc duy nhất trong executor RAM.

**Lưu ý:** không đồng thời kích hoạt `SlowJobListener` và `JobIntakeListener` trên cùng queue trong lab nếu muốn đánh giá riêng mô hình; cả hai sẽ cạnh tranh tiêu thụ message.

### 11.3. Thời gian ACK ngắn hơn nhưng thời gian nghiệp vụ vẫn dài

Với thiết kế inbox:

~~~text
RabbitMQ delivery -> DB insert/commit -> ACK (thường ngắn)
                               |
                               v
                     Job worker xử lý lâu
                               |
                           DONE/FAILED
~~~

Đây là cách **thay đổi ranh giới trách nhiệm**, không phải “lách” broker timeout. Hệ thống cần một hợp đồng rõ ràng rằng đã ACK tức là yêu cầu đã được lưu để hoàn tất sau. Nếu cần response đồng bộ báo “xử lý hoàn tất”, caller phải theo dõi trạng thái job thay vì suy từ consumer ACK.

## 12. Manual ACK: xác nhận sau commit, không xác nhận hai lần

Khi cần kiểm soát trực tiếp, tạo một `SimpleRabbitListenerContainerFactory` với `AcknowledgeMode.MANUAL`:

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ManualAckConfig {
    @Bean
    SimpleRabbitListenerContainerFactory jobsManualAckFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);
        factory.setPrefetchCount(1);
        factory.setConcurrentConsumers(1);
        return factory;
    }
}
~~~

Một ví dụ chỉ dùng trong lab:

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class ManualJobIntakeListener {
    private final JobInboxService jobInbox;

    public ManualJobIntakeListener(JobInboxService jobInbox) {
        this.jobInbox = jobInbox;
    }

    @RabbitListener(
            queues = LongJobTopology.QUEUE,
            containerFactory = "jobsManualAckFactory")
    public void accept(
            String jobId,
            Channel channel,
            @Header(AmqpHeaders.DELIVERY_TAG) long deliveryTag)
            throws IOException {

        try {
            jobInbox.persistIfAbsent(jobId); // Transaction đã COMMIT khi return.
        } catch (RuntimeException dbFailure) {
            // Chỉ là lựa chọn lab. Production cần retry/backoff,
            // không requeue vô hạn nếu lỗi vĩnh viễn.
            channel.basicNack(deliveryTag, false, true);
            return;
        }

        channel.basicAck(deliveryTag, false);
    }
}
~~~

**Không bật đồng thời các listener mẫu** cho cùng một queue khi muốn thử riêng mỗi chế độ ACK. Trong mã trên, nếu `basicAck` thất bại do channel đã đóng, method không nên gửi ACK lại bằng một channel khác với delivery tag cũ.

Các nguyên tắc cần tuân thủ:

- `deliveryTag` chỉ có ý nghĩa **trên channel hiện tại**; khác `jobId/messageId`.
- `basicAck(deliveryTag, false)` ACK một delivery, `multiple=true` có thể ACK nhiều delivery và cần hết sức cẩn thận nếu xử lý bất đồng bộ.
- Không ACK và NACK **hai lần** một delivery; broker có thể trả `PRECONDITION_FAILED - unknown delivery tag` và đóng channel.
- Nếu ACK bị mất do connection đứt, message có thể được giao lại. `JobInboxService.persistIfAbsent` phải idempotent.
- Một transaction database không tự gộp nguyên tử với ACK RabbitMQ; thứ tự commit rồi ACK vẫn có cửa sổ redelivery.

Nếu không có yêu cầu manual đặc biệt, **AUTO với service transaction rõ ràng** thường ít rủi ro hơn.

## 13. Vì sao tăng prefetch và batch ACK có thể làm timeout xuất hiện sớm?

### 13.1. Prefetch giữ nhiều delivery đồng thời

Nếu prefetch lớn, broker có thể gửi nhiều message trước khi method xử lý từng cái. Các message đang đợi trong client/container cũng có thể đang đếm thời gian chưa ACK. Vì thế một job chưa được bắt đầu có thể vẫn liên quan đến lỗi timeout của channel.

Giảm prefetch là cách **giảm số lượng delivery nằm ngoài queue nhưng chưa xử lý** và giới hạn phạm vi requeue nếu một channel bị đóng. Tuy nhiên, prefetch 1 không đủ nếu một job đơn lẻ đã vượt timeout.

### 13.2. Batch acknowledgement trì hoãn ACK

Với một số container, `batchSize` hoặc `messagesPerAck` cho phép gom nhiều ACK:

~~~text
Method xử lý m1 thành công.
Container chờ thêm message để ACK theo batch.
m1 vẫn Unacknowledged cho tới khi broker nhận ACK.
~~~

Nếu job dài hoặc listener ít traffic, việc trì hoãn ACK cần được xem cùng consumer timeout. Đừng nhầm **batch ACK** với xử lý batch payload; hai cơ chế có thể có ngữ nghĩa khác nhau. Trong Spring AMQP, các cấu hình batch có thể khiến framework điều chỉnh prefetch để đủ số lượng xử lý/ACK; hãy kiểm tra factory đang chạy thay vì chỉ nhìn YAML.

### 13.3. Retry ngay trong listener kéo dài cùng một delivery

Ví dụ một DB query timeout sau 4 phút, listener retry ba lần với backoff ngay trong cùng delivery. Tổng thời gian giữ delivery có thể vượt 12 phút dù một lượt thực thi thường dưới 5 phút.

| Retry kiểu nào? | Delivery nguồn còn unacked? | Hệ quả |
| --- | --- | --- |
| Retry đồng bộ trong method/advice | Thường **có**, cho đến khi listener kết thúc/ACK/NACK. | Tăng thời gian giữ unacked, có thể chạm timeout. |
| NACK `requeue=true` | Delivery cũ kết thúc, broker có thể giao lại. | Dễ thành vòng lặp nóng nếu lỗi vĩnh viễn. |
| Reject không requeue với DLX | Delivery cũ kết thúc; message có thể đi DLQ/retry topology. | Cần cấu hình DLX/binding và theo dõi. |
| Bàn giao bền vững sang job table rồi ACK | Delivery được ACK sau commit inbox. | Job worker cần tự timeout/retry/checkpoint và idempotency. |

**Không dùng RabbitMQ requeue ngay vô hạn như giải pháp thay thế timeout**. Consumer có thể bị quá tải bởi cùng poison message và liên tục tạo lỗi channel.

## 14. Khi channel đóng: lỗi tác động tới Spring thế nào?

### 14.1. Không đồng nhất lỗi broker và exception trong listener

Nếu RabbitMQ phát hiện timeout và đóng channel:

- Broker log có thể ghi `PRECONDITION_FAILED` với nguyên nhân **delivery acknowledgement timed out**.
- Java client nhận channel shutdown; listener container có thể log warning, recovery/cancellation và tái tạo consumer/channel tùy tình trạng kết nối/cấu hình.
- Delivery chưa ACK thuộc channel có thể được requeue/redeliver.
- Method Java đang làm việc có thể không lập tức bị ngắt. Nếu nó hoàn tất sau đó, ACK trên channel cũ có thể thất bại.

**Không mặc định chỉ vì Spring tự tạo consumer mới thì message cũ đã xử lý chính xác một lần.** Cần idempotency và quan sát DB.

### 14.2. Hai lỗi PRECONDITION_FAILED không giống nhau

| Broker error | Nguyên nhân |
| --- | --- |
| `PRECONDITION_FAILED - delivery acknowledgement ... timed out` | Một delivery chưa ACK vượt timeout của consumer. |
| `PRECONDITION_FAILED - unknown delivery tag` | Ứng dụng ACK/NACK delivery tag không hợp lệ trên channel, có thể do double ACK hoặc nhầm channel. |
| `PRECONDITION_FAILED - inequivalent arg ...` | Ứng dụng khai báo lại queue/exchange với properties/arguments không tương đương. |

Tất cả có thể làm đóng channel nhưng cần **cách sửa khác nhau**. Không tăng consumer timeout để chữa lỗi double ACK hoặc khai báo queue sai.

### 14.3. Có nên tăng network heartbeat không?

**Không** nếu nguyên nhân là consumer acknowledgement timeout. Heartbeat và ACK thuộc hai tầng khác nhau. Heartbeat giúp phát hiện connection còn sống; nó không cho broker bằng chứng rằng message đã hoàn tất nghiệp vụ.

Nếu network bị đứt thì heartbeat/connection recovery lại là chủ đề đúng; nhưng việc tăng heartbeat timeout quá cao có thể khiến lỗi connection được phát hiện muộn. Cần xác định **lỗi thật trong broker log** trước khi thay đổi cấu hình.

## 15. Quan sát và cảnh báo trong production

### 15.1. Metric cần xem

| Chỉ số | Câu hỏi |
| --- | --- |
| `messages_ready` | Bao nhiêu message còn sẵn sàng giao? |
| `messages_unacknowledged` | Bao nhiêu delivery đang chờ consumer ACK? |
| Consumer count | Bao nhiêu consumer đang hoạt động; có liên tục mất và reconnect không? |
| Delivery/ACK rate | Delivery có được xác nhận đều không? |
| Redelivery rate | Message có bị giao lại do lỗi hoặc consumer restart không? |
| `listener_processing_duration` p50/p95/p99 | Thời gian xử lý method có tiến gần timeout không? |
| **Delivery-to-ACK latency** (nếu có instrumentation) | Bao gồm thời gian giữ trước xử lý, retry, commit và ACK. |
| Channel shutdown reason | Có `PRECONDITION_FAILED` do ACK timeout không? |
| DLQ depth | Có poison message hay job không thể hoàn tất cần điều tra không? |
| Job inbox pending/running age | Trong mô hình bàn giao, job có bị treo sau khi RabbitMQ đã ACK không? |
| DB pool, CPU, heap/GC, downstream latency | Nguồn gây tác vụ kéo dài nằm ở đâu? |

**Lưu ý:** `listener_processing_duration` chỉ đo thời gian chạy method; broker có thể tính thời gian từ **lúc delivery**, đặc biệt khi prefetch lớn. Đừng coi method duration luôn bằng delivery-to-ACK latency. Nếu muốn cảnh báo sát ngưỡng, cần tự instrument nhận/giao và ACK theo khả năng của container, đồng thời đối chiếu broker metrics.

### 15.2. RabbitMQ Management UI và CLI

Trong Management UI, xem queue **Ready**, **Unacked**, **Total**, consumers và rates. Kiểm tra connections/channels để phát hiện consumer liên tục reconnect. Ví dụ lệnh quản trị:

~~~bash
# Queue có bao nhiêu message sẵn sàng/chưa ACK?
rabbitmqctl list_queues -p / name messages_ready messages_unacknowledged consumers

# Xem thông tin consumers và các tham số QoS theo phiên bản broker.
rabbitmqctl list_consumers -p /

# Xem trạng thái kết nối và số channel.
rabbitmqctl list_connections -p / name state channels
~~~

Những lệnh này chỉ chạy ở nơi có quyền quản trị RabbitMQ. Cú pháp field và thông tin hiển thị có thể khác theo phiên bản; dùng `rabbitmqctl help <command>` và log broker để xác định chính xác ACK timeout. Không dùng CLI chạy liên tục từ mỗi Java instance như hệ thống telemetry production; thường tích hợp Management API/Prometheus và Micrometer tốt hơn.

### 15.3. Phân loại tình huống qua dấu hiệu

| Triệu chứng | Nghi vấn | Hướng xử lý |
| --- | --- | --- |
| Unacked cao, ACK rate thấp | Listener chậm, retry, quên manual ACK hoặc batch ACK. | Đo processing/DB latency, kiểm tra ACK path và prefetch. |
| Broker log có acknowledgement timed out | Delivery giữ quá thời hạn broker. | Kiểm tra timeout hiệu lực, thời gian delivery-to-ACK, số message prefetch. |
| Consumer reconnect liên tục, job duplicate | Channel bị đóng, unacked bị requeue. | Xác định shutdown reason, kiểm tra idempotency. |
| Job xử lý lâu hơn timeout dù prefetch 1 | Tác vụ đơn lẻ vượt ngưỡng. | Chia job, bàn giao vào inbox bền vững hoặc tăng timeout có kiểm soát. |
| Đổi heartbeat nhưng vẫn lỗi ACK timeout | Cấu hình sai tầng. | Sửa job/ACK policy hoặc broker consumer timeout. |
| Method hoàn thành nhưng Unacked không giảm | Batch/manual ACK chưa gửi, channel đã mất hoặc lỗi ACK. | Đối chiếu container mode, ACK logs, channel shutdown. |
| Ready thấp, Unacked rất cao | Nhiều delivery đã được giao trước, chưa xử lý. | Giảm prefetch, đo backlog thật và tốc độ hoàn thành. |
| Inbox đã ACK nhưng job ở RUNNING quá lâu | Worker nội bộ bị kẹt; RabbitMQ không còn quản lý job đó. | Lease/recovery/checkpoint và cảnh báo ở job table. |

## 16. Bài thực hành có thể kiểm chứng

Làm trên RabbitMQ cục bộ hoặc môi trường test chuyên dụng, không thay timeout/kill consumer ở production.

| Bước | Thao tác | Kỳ vọng quan sát |
| --- | --- | --- |
| 1 | Khai báo topology `jobs.events`, `jobs.requested.q` và binding; chạy consumer AUTO. | Queue/consumer tồn tại; message được xử lý và ACK bình thường nếu ngắn. |
| 2 | Ghi nhận consumer timeout đang có hiệu lực ở broker. | Biết ngưỡng áp dụng và nơi được cấu hình; không đoán từ Spring YAML. |
| 3 | Đặt lab timeout khoảng 5 phút bằng cơ chế RabbitMQ version hỗ trợ. | Broker log/cấu hình xác nhận ngưỡng; không dùng giá trị vài giây để thử. |
| 4 | Dùng listener chậm ở mục 8 và gửi một job. | Nếu delivery vượt ngưỡng, có thể thấy channel shutdown với `PRECONDITION_FAILED` và redelivery. |
| 5 | So sánh `prefetch=1` và `prefetch=4` với vài job dài. | Lượng Unacked và thời gian chờ của các delivery phía sau khác nhau. |
| 6 | Bật manual ACK trong một listener thay thế; cố ý không ACK một message test. | Unacked còn giữ, consumer có thể dừng nhận thêm khi hết prefetch, rồi broker đóng channel nếu vượt deadline. |
| 7 | Quan sát RabbitMQ logs và Spring logs cùng timestamp. | Phân biệt ACK timeout với `unknown delivery tag` và lỗi connection heartbeat. |
| 8 | Triển khai inbox pattern `JobIntakeListener` + transaction DB + worker độc lập. | RabbitMQ ACK sau commit inbox, job dài tiếp tục được quản lý trong DB. |
| 9 | Kill job worker sau khi listener đã ACK. | Job PENDING/RUNNING được recovery từ DB lease; không mất chỉ vì RAM bị xóa. |
| 10 | Publish lại cùng jobId và cho consumer nhận trùng. | Unique jobId giúp idempotent; không tạo hai logical jobs. |
| 11 | Thử DB timeout trước commit inbox. | Listener không ACK như thành công; delivery được xử lý theo retry/requeue/DLQ policy. |

### Mẫu ghi nhận kết quả

~~~text
Spring Boot / Spring AMQP version:
RabbitMQ version / queue type:
Broker consumer_timeout thực tế:
Queue-level timeout/policy có được hỗ trợ?:
Listener container: SIMPLE / DIRECT
ACK mode: AUTO / MANUAL / NONE
Configured prefetch / active consumers:
Job processing time p50/p95/p99:
Delivery-to-ACK latency (nếu đo được):
Messages Ready / Unacknowledged:
Channel shutdown reason:
Redelivery count / rate:
DB transaction status:
Event/job ID preserved across retry?:
Idempotency outcome:
Inbox persisted before ACK?:
Job recovery after worker crash?:
DLQ depth:
~~~

**Điều phải ghi nhận:** broker kiểm tra timeout định kỳ, vì vậy một bài test với job vừa vượt ngưỡng không bắt buộc đóng channel ngay lập tức. Hãy dựa vào broker log, mức timeout hiệu lực, quá trình ACK và trạng thái redelivery để xác minh thay vì suy luận từ thời điểm method kết thúc.

## 17. Những hiểu nhầm thường gặp

**“Kết nối vẫn có heartbeat nghĩa là delivery không thể bị timeout.”** Không. Heartbeat và acknowledgement timeout là hai cơ chế khác nhau.

**“Spring AUTO ACK ngay khi @RabbitListener bắt đầu.”** Không. Container thường ACK sau khi method hoàn tất thành công và theo cấu hình ACK liên quan.

**“Prefetch=1 bảo đảm không bị ACK timeout.”** Không. Một job đơn lẻ dài hơn timeout vẫn có nguy cơ.

**“Prefetch=10 nghĩa là chỉ một delivery có thời hạn ACK.”** Không. Nhiều delivery có thể đã được giao và chưa ACK, kể cả delivery đang chờ xử lý trong client.

**“Chỉ message bị timeout mới chịu ảnh hưởng khi channel đóng.”** Không. Những delivery khác còn unacked trên channel đó cũng có thể phải được giao lại.

**“Tăng consumer timeout là cách duy nhất để chạy job hàng giờ.”** Không. Có thể chia job hoặc bàn giao bền vững vào inbox/job table rồi ACK; worker riêng quản lý thời gian và recovery.

**“ACK ngay sau executor.submit bảo đảm job không mất.”** Không. Executor trong RAM có thể biến mất khi process crash; chỉ ACK sớm sau một **handoff bền vững**.

**“Consumer timeout hoạt động giống TTL.”** Không. TTL và ACK timeout giải quyết các trạng thái/thời điểm khác nhau của message.

**“ACK trước rồi xử lý DB vẫn exactly once.”** Không. ACK trước DB commit có thể khiến message bị mất khỏi queue dù DB thất bại; commit trước ACK có nguy cơ redelivery, cần idempotency.

**“Publisher confirms xác nhận consumer đã ACK.”** Không. Publisher confirm chỉ liên quan broker xử lý publish, không nói consumer đã hoàn tất.

**“Thấy PRECONDITION_FAILED thì luôn do consumer timeout.”** Không. Unknown delivery tag hoặc redeclare queue arguments không tương đương cũng có thể gây PRECONDITION_FAILED.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Consumer thực hiện một job 40 phút, broker consumer timeout 30 phút. Heartbeat đều đặn có ngăn channel bị đóng không?

**Trả lời:** Không. Heartbeat kiểm tra connection, còn consumer ACK timeout theo dõi delivery chưa xác nhận.

**Câu 2.** Vì sao prefetch 4 có thể khiến message thứ tư bị ảnh hưởng dù method của nó chưa thực thi?

**Trả lời:** Broker có thể đã giao sớm cả bốn delivery; message thứ tư đã ở trạng thái unacked và chờ các job trước, nên thời gian delivery-to-ACK bao gồm cả thời gian chờ.

**Câu 3.** Khi channel bị đóng vì ACK timeout, có thể chỉ ACK lại delivery cũ trên channel mới bằng delivery tag cũ không?

**Trả lời:** Không. Delivery tag có phạm vi **channel**. Consumer phải xử lý delivery được broker giao lại với tag mới và có idempotency.

**Câu 4.** Vì sao tăng `spring.rabbitmq.requested-heartbeat` không sửa được lỗi consumer ACK timeout?

**Trả lời:** Vì heartbeat timeout và acknowledgement timeout thuộc các cơ chế riêng. Cần sửa thời gian giữ delivery, mô hình xử lý hoặc cấu hình broker.

**Câu 5.** Nếu inbox đã commit job rồi listener ACK, trong khi worker xử lý job 2 giờ, thiết kế có hợp lệ không?

**Trả lời:** Có thể hợp lệ, **nếu** ACK biểu thị đã bàn giao bền vững, job worker có lease/recovery và xử lý trùng theo job ID. Không thể chỉ dùng executor RAM.

**Câu 6.** Spring `AcknowledgeMode.NONE` có phải cách an toàn để tránh consumer timeout không?

**Trả lời:** Không. Broker không chờ ACK nhưng message có thể bị coi là đã tiêu thụ trước khi xử lý xong, tăng nguy cơ mất việc khi lỗi.

**Câu 7.** Broker log báo `PRECONDITION_FAILED - unknown delivery tag`. Có nên tăng timeout ngay không?

**Trả lời:** Không. Kiểm tra double ACK, dùng nhầm channel hoặc delivery tag sai. Đây không phải lỗi acknowledgement timed out.

**Câu 8.** Consumer đã commit DB nhưng ACK bị mất; RabbitMQ redeliver cùng event. Cần cơ chế gì?

**Trả lời:** Logical event ID ổn định, transaction cùng dấu đã xử lý/unique constraint, và listener idempotent; chỉ thay prefetch/timeout không tạo exactly-once side effect.

## 19. Tài liệu tham khảo

- [RabbitMQ — Consumers / Delivery Acknowledgement Timeout](https://www.rabbitmq.com/docs/consumers#acknowledgement-timeout): cơ chế timeout, lỗi channel, cấu hình và những lưu ý theo phiên bản.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): consumer ACK/NACK, delivery tags, khác biệt với publisher confirms.
- [RabbitMQ — Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch): `basic.qos`, giới hạn per-consumer và tác động tới Unacked.
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx): khi nào message bị dead-letter và các chính sách DLX/DLQ.
- [Spring AMQP — Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-consumer.html): Simple/Direct containers, prefetch, batching và ack modes.
- [Spring AMQP — Annotation-driven Listener](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven.html): `@RabbitListener`, method invocation và khả năng xử lý bất đồng bộ.
- [Spring AMQP — Exception Handling](https://docs.spring.io/spring-amqp/reference/amqp/exception-handling.html): xử lý lỗi, reject/requeue và lựa chọn retry.
- [Spring AMQP — Transactions](https://docs.spring.io/spring-amqp/reference/amqp/transactions.html): transaction boundary và tương tác với acknowledgements.

**Ghi nhớ:** RabbitMQ có thể áp dụng **consumer delivery acknowledgement timeout** để đóng channel khi delivery còn chờ ACK quá lâu; message chưa ACK có thể được **redeliver**, thậm chí khi tác vụ Java cũ vẫn chạy. Phải phân biệt timeout này với **heartbeat, connection timeout, TTL và publisher confirms**. Với **Spring AMQP**, hãy chọn `AUTO/MANUAL` ACK hợp lý, giảm prefetch khi job lâu, đo delivery-to-ACK, tránh retry nóng và giữ **idempotency**. Đối với công việc thực sự kéo dài, ưu tiên **bàn giao bền vững vào inbox/job table trước khi ACK**, rồi để worker có lease/recovery tiếp tục; hoặc tăng broker timeout có kiểm soát sau khi đánh giá rủi ro. Kết hợp exchange/queue/binding, publisher confirms, retry/dead-letter, transaction và giám sát để tạo hệ thống xử lý bất đồng bộ đáng tin cậy.
