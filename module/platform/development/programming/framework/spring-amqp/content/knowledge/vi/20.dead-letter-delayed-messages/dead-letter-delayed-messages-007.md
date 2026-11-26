# Giới hạn số lần quay lại và queue cách ly cuối cùng

Trong hệ thống bất đồng bộ dùng **RabbitMQ và Spring AMQP**, một message xử lý thất bại không nên được đưa trở lại queue vô hạn. Lỗi tạm thời như API đối tác quá tải có thể hết sau một khoảng chờ; ngược lại, message sai định dạng hoặc vi phạm quy tắc nghiệp vụ sẽ tiếp tục thất bại dù xử lý bao nhiêu lần. Bài này xây dựng cơ chế **retry hữu hạn, có độ trễ, rồi chuyển message thất bại sang queue cách ly cuối cùng** (thường gọi là *parking-lot queue* hoặc *quarantine queue*).

Đây là bước tiếp theo trong chủ đề **Dead-letter và trì hoãn**: dùng exchange, queue, binding, TTL, RabbitTemplate và @RabbitListener của Spring AMQP để kiểm soát đường đi của message, xác nhận giao nhận và quan sát các trường hợp lỗi.

## 1. Vì sao cần giới hạn retry?

Xét consumer nhận sự kiện `OrderCreated` và gọi dịch vụ thanh toán:

- Dịch vụ thanh toán trả HTTP 503: **lỗi tạm thời**, có thể thử lại sau 30 giây.
- `orderId` không tồn tại hoặc dữ liệu không hợp lệ: **lỗi vĩnh viễn**, cần cách ly để điều tra.
- Consumer luôn gọi `basicNack(tag, false, true)` khi lỗi: message lập tức được trả lại queue, có thể tạo vòng lặp rất nhanh, chiếm CPU và che khuất các message hợp lệ.

Một thiết kế an toàn cần trả lời rõ bốn câu hỏi: **được xử lý tối đa bao nhiêu lần**, **chờ bao lâu giữa các lần**, **sau khi hết lượt sẽ đi đâu**, và **ai quyết định phát lại message cách ly**.

Trong bài này, quy ước `MAX_BUSINESS_ATTEMPTS = 4` nghĩa là **tối đa bốn lần thực sự gọi mã xử lý nghiệp vụ**, bao gồm lần nhận đầu tiên; đó không phải là bốn lần thử lại *sau* lần đầu.

| Khái niệm | Ý nghĩa | Có làm tăng `x-death` không? |
|---|---|---|
| Lần xử lý nghiệp vụ | Consumer gọi hàm xử lý một message | Không nhất thiết |
| Retry trong cùng một lần nhận (Spring Retry) | Hàm xử lý được gọi lại ngay trong tiến trình consumer | Không, nếu chưa dead-letter |
| `basicNack(tag, false, true)` | Yêu cầu broker requeue trực tiếp | Không phải một sự kiện dead-letter |
| `basicReject(tag, false)` | Từ chối và **không** requeue; broker dùng DLX nếu cấu hình | Có, với reason `rejected` |
| Message hết TTL trong retry queue | Broker dead-letter vì hết hạn | Có, với reason `expired` |

**Phân biệt quan trọng:** bit `redelivered` chỉ cho biết broker đánh dấu giao lại, không phải bộ đếm chính xác. Không dùng bit này để xác định số lần retry.

## 2. Mô hình: work queue → retry queue → work queue hoặc quarantine

Ta dùng ba queue và ba exchange (đều khai báo durable):

| Thành phần | Vai trò | Quy tắc |
|---|---|---|
| `orders.work.x` + `orders.work.q` | Nhận và xử lý đơn hàng | Khi bị reject với `requeue=false`, dead-letter đến `orders.retry.x` |
| `orders.retry.x` + `orders.retry.q` | Giữ message trong 30 giây | Hết TTL thì dead-letter về `orders.work.x` |
| `orders.parking.x` + `orders.parking.q` | Cách ly message không xử lý được | Không tự động chuyển về work queue, không có consumer retry tự động |

~~~mermaid
flowchart TD
    P["Publisher"] --> WX["orders.work.x"]
    WX --> WQ["orders.work.q"]
    WQ --> C{"@RabbitListener xử lý"}
    C -->|Thành công| A["basicAck"]
    C -->|"Lỗi tạm thời, còn lượt"| N["basicReject(requeue=false)"]
    N --> RX["orders.retry.x"]
    RX --> RQ["orders.retry.q — TTL 30 giây"]
    RQ -->|Hết TTL, dead-letter| WX
    C -->|"Lỗi vĩnh viễn / hết lượt"| PX["RabbitTemplate publish + publisher confirm"]
    PX --> PQ["orders.parking.x → orders.parking.q"]
    PQ -->|Có confirm và route thành công| PA["Ack message gốc"]
    PX -->|Không xác nhận được| N
    PQ -.-> OPS["Điều tra, sửa lỗi, phát lại thủ công"]
~~~

Luồng bình thường là: lần đầu nhận ở work queue → xử lý thất bại → broker dead-letter sang retry queue → chờ TTL → broker chuyển lại work queue. **Consumer chỉ chuyển sang quarantine khi lỗi vĩnh viễn hoặc đã dùng hết số lượt**. Một message được cách ly không còn nằm trên vòng retry tự động.

Sử dụng TTL ở **retry queue** giúp consumer không phải gọi `Thread.sleep` và không giữ message ở trạng thái *unacked* trong lúc chờ. TTL 30 giây là thời gian chờ dự kiến, không phải bảo đảm chính xác đến mili giây khi broker chịu tải.

## 3. Đếm số lần quay lại bằng `x-death`

RabbitMQ bổ sung header `x-death` mỗi khi một message được dead-letter. Đây là danh sách lịch sử theo cặp **queue + reason**, gồm số lần `count` và các thông tin như exchange, thời điểm; broker có thể gộp nhiều lần dead-letter cùng một cặp vào một bản ghi.

Ví dụ khi message đã quay lại work queue hai lần, header có thể chứa thông tin tương đương:

~~~yaml
x-death:
  - queue: orders.work.q
    reason: rejected
    count: 2
  - queue: orders.retry.q
    reason: expired
    count: 2
~~~

Để biết message đã **thất bại tại consumer chính** bao nhiêu lần, chỉ đọc bản ghi có `queue = orders.work.q` và `reason = rejected`. Không cộng tất cả các dòng `x-death` vì mỗi chu kỳ retry còn tạo thêm một dòng `expired` ở retry queue; cộng cả hai sẽ đếm gấp đôi.

Khi message vừa tới work queue:

**Số thứ tự lần xử lý hiện tại = 1 + số lần `rejected` trước đó tại `orders.work.q`.**

| Lần vào work queue | `x-death` cho work/rejected trước khi xử lý | Kết quả nếu tiếp tục lỗi tạm thời |
|---:|---:|---|
| 1 | 0 | Reject → retry 30 giây |
| 2 | 1 | Reject → retry 30 giây |
| 3 | 2 | Reject → retry 30 giây |
| 4 | 3 | Đủ 4 lượt → chuyển quarantine, ack bản gốc |
| 5 (chỉ khi quarantine đang lỗi) | 4 | **Không xử lý nghiệp vụ thêm**, chỉ tìm cách chuyển quarantine |

Lưu ý: `x-death` phản ánh lịch sử **dead-letter**, không tự động tính các lần retry bằng Spring Retry, requeue trực tiếp hoặc trường hợp publisher gửi một message mới. Nếu thiết kế chuyển sang *republish* để retry, cần cơ chế đếm khác (ví dụ header ứng dụng `retryCount` có kiểm soát) và quy định rõ số lần được phép.

## 4. Khai báo topology bằng Spring AMQP

Ví dụ dưới dùng Spring Boot và `spring-boot-starter-amqp`. Các tên exchange, routing key và queue được cố định trong một class để tránh lệch cấu hình giữa publisher và consumer.

~~~java
import org.springframework.amqp.core.*;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitTopology {
    public static final String WORK_EXCHANGE = "orders.work.x";
    public static final String WORK_QUEUE = "orders.work.q";
    public static final String WORK_KEY = "orders.work";

    public static final String RETRY_EXCHANGE = "orders.retry.x";
    public static final String RETRY_QUEUE = "orders.retry.q";
    public static final String RETRY_KEY = "orders.retry";

    public static final String PARKING_EXCHANGE = "orders.parking.x";
    public static final String PARKING_QUEUE = "orders.parking.q";
    public static final String PARKING_KEY = "orders.parking";

    @Bean
    DirectExchange workExchange() {
        return new DirectExchange(WORK_EXCHANGE, true, false);
    }

    @Bean
    DirectExchange retryExchange() {
        return new DirectExchange(RETRY_EXCHANGE, true, false);
    }

    @Bean
    DirectExchange parkingExchange() {
        return new DirectExchange(PARKING_EXCHANGE, true, false);
    }

    @Bean
    Queue workQueue() {
        return QueueBuilder.durable(WORK_QUEUE)
                .deadLetterExchange(RETRY_EXCHANGE)
                .deadLetterRoutingKey(RETRY_KEY)
                .build();
    }

    @Bean
    Queue retryQueue() {
        return QueueBuilder.durable(RETRY_QUEUE)
                .ttl(30_000)
                .deadLetterExchange(WORK_EXCHANGE)
                .deadLetterRoutingKey(WORK_KEY)
                .build();
    }

    @Bean
    Queue parkingQueue() {
        return QueueBuilder.durable(PARKING_QUEUE).build();
    }

    @Bean
    Binding workBinding(
            @Qualifier("workQueue") Queue queue,
            @Qualifier("workExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue).to(exchange).with(WORK_KEY);
    }

    @Bean
    Binding retryBinding(
            @Qualifier("retryQueue") Queue queue,
            @Qualifier("retryExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue).to(exchange).with(RETRY_KEY);
    }

    @Bean
    Binding parkingBinding(
            @Qualifier("parkingQueue") Queue queue,
            @Qualifier("parkingExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue).to(exchange).with(PARKING_KEY);
    }
}
~~~

Trong ví dụ, `orders.work.q` có dead-letter exchange là `orders.retry.x`. Vì vậy, gọi `basicReject(tag, false)` từ consumer khiến RabbitMQ tự định tuyến message vào retry queue. Retry queue thiết lập `x-message-ttl = 30000` và DLX trỏ về work exchange. Queue cách ly được bind riêng, không đặt TTL/DLX quay về work queue.

Spring Boot có thể dùng `RabbitAdmin` để khai báo các bean topology lúc khởi động. Trong hệ thống thực tế, nên quản lý DLX, TTL và binding bằng cấu hình triển khai hoặc **RabbitMQ policy** nếu cần điều chỉnh mà không thay đổi tham số của queue đang tồn tại. RabbitMQ có thể từ chối khai báo lại một queue cùng tên nhưng khác arguments.

## 5. Consumer giới hạn số lượt, xác nhận được việc chuyển quarantine

Để tránh ack bản gốc trước khi bản sao đã đến queue cách ly, cấu hình **publisher confirms và returns**:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

`publisher-confirm-type: correlated` cho phép chờ broker xác nhận publish; `publisher-returns` cùng `mandatory: true` giúp nhận biết message không được định tuyến tới queue nào. Chỉ khi publish được xác nhận **và không bị return** mới ack message gốc. Đây là hai thao tác khác nhau nên vẫn có khả năng tạo bản sao nếu kết nối đứt sau khi publish thành công nhưng trước lúc ack; xử lý downstream cần **idempotent**.

Ví dụ sau dùng `@RabbitListener` với manual acknowledgment. Giả định đã có `OrderProcessor.process(byte[])` thực hiện nghiệp vụ và `PermanentOrderException` đánh dấu lỗi không thể sửa bằng retry (chẳng hạn dữ liệu không hợp lệ).

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderListener {
    private static final long MAX_BUSINESS_ATTEMPTS = 4;

    private final OrderProcessor processor;
    private final RabbitTemplate rabbitTemplate;

    public OrderListener(OrderProcessor processor, RabbitTemplate rabbitTemplate) {
        this.processor = processor;
        this.rabbitTemplate = rabbitTemplate;
    }

    @RabbitListener(queues = RabbitTopology.WORK_QUEUE, ackMode = "MANUAL")
    public void consume(Message message, Channel channel) throws IOException {
        long tag = message.getMessageProperties().getDeliveryTag();
        long attempt = 1 + priorRejections(message);

        // Quarantine có thể đã lỗi ở lần trước: không gọi nghiệp vụ lần thứ 5.
        if (attempt > MAX_BUSINESS_ATTEMPTS) {
            parkOrRetry(message, channel, tag, attempt, "parking_unavailable");
            return;
        }

        try {
            processor.process(message.getBody());
        } catch (PermanentOrderException ex) {
            parkOrRetry(message, channel, tag, attempt, "permanent_error");
            return;
        } catch (Exception ex) {
            if (attempt < MAX_BUSINESS_ATTEMPTS) {
                channel.basicReject(tag, false); // DLX → retry queue
            } else {
                parkOrRetry(message, channel, tag, attempt, "attempts_exhausted");
            }
            return;
        }

        channel.basicAck(tag, false); // Chỉ ack sau khi xử lý thành công.
    }

    private long priorRejections(Message message) {
        Object raw = message.getMessageProperties().getHeaders().get("x-death");
        if (!(raw instanceof List<?> deaths)) {
            return 0;
        }
        for (Object item : deaths) {
            if (!(item instanceof Map<?, ?> death)) {
                continue;
            }
            boolean fromWork = RabbitTopology.WORK_QUEUE.equals(
                    String.valueOf(death.get("queue")));
            boolean rejected = "rejected".equals(
                    String.valueOf(death.get("reason")));
            Object count = death.get("count");
            if (fromWork && rejected && count instanceof Number number) {
                return number.longValue();
            }
        }
        return 0;
    }

    private void parkOrRetry(
            Message source, Channel channel, long tag,
            long attempt, String failureType) throws IOException {

        MessageProperties props = new MessageProperties();
        props.setContentType(source.getMessageProperties().getContentType());
        props.setContentEncoding(source.getMessageProperties().getContentEncoding());
        props.setCorrelationId(source.getMessageProperties().getCorrelationId());
        props.setMessageId(UUID.randomUUID().toString());
        props.setHeader("originalMessageId",
                source.getMessageProperties().getMessageId());
        props.setHeader("businessAttempts", attempt);
        props.setHeader("failureType", failureType);
        Message parked = new Message(source.getBody(), props);

        boolean published = false;
        try {
            CorrelationData correlation =
                    new CorrelationData(UUID.randomUUID().toString());
            rabbitTemplate.send(
                    RabbitTopology.PARKING_EXCHANGE,
                    RabbitTopology.PARKING_KEY,
                    parked,
                    correlation);
            CorrelationData.Confirm confirm =
                    correlation.getFuture().get(5, TimeUnit.SECONDS);
            published = confirm.isAck() && correlation.getReturned() == null;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            // Ghi log/cảnh báo trong ứng dụng thực tế.
        } catch (Exception ex) {
            // Ghi log/cảnh báo: không thể xác nhận publish quarantine.
        }

        if (published) {
            channel.basicAck(tag, false);
        } else {
            // Không mất message gốc; đi lại retry queue qua DLX,
            // rồi chỉ thử chuyển quarantine (không chạy lại nghiệp vụ).
            channel.basicReject(tag, false);
        }
    }
}
~~~

Các điểm quyết định trong đoạn mã:

1. **Chỉ đếm `x-death` của work queue với reason `rejected`.** Với một message mới, số lần xử lý là 1; sau ba lần dead-letter từ work queue, lần kế tiếp là lần thứ 4.
2. **Lỗi vĩnh viễn** được gửi thẳng tới quarantine. **Lỗi tạm thời** dùng vòng DLX/TTL khi còn lượt.
3. **Lỗi sau lượt thứ 4** được chuyển quarantine và ack message gốc *sau* khi xác nhận publish.
4. **Không xác nhận được quarantine** thì reject bản gốc để broker đưa qua retry queue. Khi nhận lại, guard `attempt > MAX_BUSINESS_ATTEMPTS` ngăn việc chạy nghiệp vụ thêm. Cần phát cảnh báo vì quarantine có thể đang lỗi.
5. Header trên message mới ghi lại message ID ban đầu, nguyên nhân và số lượt. Không tự tạo hoặc sửa `x-death`: đây là thông tin lịch sử do broker quản lý.

Trong sản phẩm thực, cần sao chép có chọn lọc các header nghiệp vụ/trace cần cho việc điều tra (như schema version hoặc correlation ID), thay vì mặc định sao chép mọi header từ broker. Mã mẫu bỏ qua phần ghi log, metric và quy tắc phân loại exception chi tiết để tập trung vào điều kiện dừng retry.

## 6. Quarantine là điểm dừng để điều tra, không phải retry queue tiếp theo

Message tại `orders.parking.q` nên được giữ nguyên cho đội vận hành hoặc một luồng quản trị có kiểm soát. Mỗi bản ghi cách ly nên cho phép truy vết:

- Message ID và correlation ID gốc; thời điểm nhận, exchange/queue nguồn.
- Payload và phiên bản schema cần để tái hiện lỗi; che thông tin nhạy cảm trong log.
- Số lượt xử lý, mã lỗi, loại lỗi (tạm thời/vĩnh viễn), phiên bản consumer.
- Trạng thái xử lý: chưa điều tra, đã xác định nguyên nhân, đã phát lại, hoặc đã loại bỏ có chủ đích.

**Quy trình phát lại thủ công**: sửa nguyên nhân → kiểm tra message còn hợp lệ → tạo một lần publish có kiểm soát về `orders.work.x` → chờ publisher confirm → sau đó mới xác nhận/xóa message ở quarantine. Trước khi phát lại, đặt lại bộ đếm retry *theo quy ước của ứng dụng* và giữ liên kết tới message gốc để audit; đừng phát tán nguyên header `x-death` như một bộ đếm tùy biến. Một message được replay có thể tạo hiệu ứng nghiệp vụ trùng lặp, nên consumer cần khóa idempotency theo business key (ví dụ `orderId` + loại sự kiện).

Queue cách ly không nên có binding tự động quay về work queue, không đặt lịch retry vô hạn và không có consumer chỉ việc `basicNack(requeue=true)`. Có thể đặt retention và quyền truy cập phù hợp để quản lý dung lượng, nhưng thời hạn xóa phải gắn với nhu cầu điều tra và chính sách dữ liệu của hệ thống.

## 7. Phân biệt với giới hạn giao lại của quorum queue

RabbitMQ còn hỗ trợ giới hạn số lần giao lại (*delivery limit*) cho **quorum queue**, dùng khi message liên tục bị trả về cùng queue với `requeue=true`. Khi vượt ngưỡng, broker có thể dead-letter message tới DLX/quarantine đã cấu hình.

Ví dụ một mô hình **khác**, không dùng vòng work → retry TTL như phía trên:

~~~java
@Bean
Queue quorumWorkQueue() {
    return QueueBuilder.durable("orders.quorum.work.q")
            .withArgument("x-queue-type", "quorum")
            .withArgument("x-delivery-limit", 5)
            .deadLetterExchange("orders.parking.x")
            .deadLetterRoutingKey("orders.parking")
            .build();
}
~~~

Ở mô hình này, broker quản lý giới hạn giao lại tại quorum queue; consumer cần chọn cách requeue phù hợp. Header `x-delivery-count` phản ánh số lần giao lại mà quorum queue ghi nhận, với ngữ nghĩa khác `x-death`. **Không lấy `x-delivery-limit` của quorum queue làm bộ đếm thay thế** cho chu kỳ chuyển qua retry queue bằng TTL và DLX: đây là hai cơ chế khác nhau, với các mốc đếm khác nhau. Muốn có backoff trong mô hình quorum requeue phải thiết kế thêm, vì requeue trực tiếp có thể chạy rất nhanh.

Với Spring Retry ở phía consumer, `maxAttempts(3)` cũng chỉ điều khiển **ba lần gọi tại phía ứng dụng**, không tự đồng nghĩa với ba lượt dead-letter trên RabbitMQ. Khi kết hợp Spring Retry với vòng broker, cần xác định rõ tổng số lần xử lý thực tế có thể bằng tích của hai giới hạn.

## 8. Kiểm thử luồng thất bại và quan sát vận hành

Trước khi triển khai, thử ít nhất các kịch bản:

| Tình huống | Kết quả mong đợi |
|---|---|
| Xử lý thành công lần đầu | Một lần nghiệp vụ, ack; retry và quarantine rỗng |
| Lỗi tạm thời hai lần rồi thành công | Ba lần xử lý, hai lần qua retry TTL, không có quarantine |
| Lỗi vĩnh viễn ngay lần đầu | Chuyển quarantine với `businessAttempts = 1`, không chờ các lượt còn lại |
| Message lỗi tạm thời mãi | Đúng bốn lần xử lý nghiệp vụ, sau đó quarantine |
| Parking exchange không có binding | Publisher return; không ack bản gốc; retry theo TTL và cảnh báo |
| Broker mất kết nối sau khi publish quarantine | Có thể xuất hiện bản sao khi nhận lại; truy vết và khử trùng lặp theo message/business key |
| Khôi phục message từ quarantine | Chỉ phát lại khi đã sửa lỗi, xác nhận publish trước khi xóa bản cách ly |

Các tín hiệu cần giám sát gồm độ sâu và tuổi của `orders.retry.q`/`orders.parking.q`, tốc độ reject/dead-letter, số message vượt giới hạn, lỗi publish/confirm/return, tỷ lệ thành công sau retry và số message cần xử lý thủ công. Nếu quarantine tăng liên tục, đây là một sự cố cần điều tra, không phải dấu hiệu hệ thống đã tự phục hồi.

Một số lỗi triển khai thường gặp:

- **`basicReject(false)` nhưng không khai báo DLX/binding hợp lệ:** message có nguy cơ bị loại bỏ. Kiểm tra cả queue arguments, exchange tồn tại và routing key/binding.
- **Đếm tổng mọi dòng `x-death`:** một vòng work/retry tạo cả `rejected` và `expired`, khiến hệ thống dừng sớm.
- **Ack trước khi publish quarantine được xác nhận:** xảy ra rủi ro mất message nếu publish thất bại hoặc không định tuyến được.
- **Giả định publisher confirm + consumer ack là một giao dịch nguyên tử:** hai thao tác có thể bị tách bởi sự cố kết nối; phải chuẩn bị cho *at-least-once delivery* và duplicate.
- **Quarantine được tự động replay:** poison message có thể tái tạo vòng lặp vô hạn ngoài giới hạn retry dự tính.
- **Gọi `Thread.sleep` trong listener:** giữ consumer và message unacked, làm giảm throughput; với chờ dài nên dùng retry queue TTL hoặc cơ chế scheduling/delay phù hợp.

## 9. Nguyên tắc thiết kế cần nhớ

Giới hạn retry phải tính theo một đơn vị rõ ràng: số lần xử lý nghiệp vụ, số lượt dead-letter hoặc số lần broker giao lại. Với luồng **Spring AMQP + RabbitMQ DLX/TTL**, hãy lọc `x-death` theo **work queue + reason rejected**, tính lần xử lý đầu tiên là 1, và kết thúc tại một **parking-lot queue** độc lập. Chỉ ack message gốc khi xử lý thành công hoặc khi đã xác nhận chuyển vào quarantine; đo lường thất bại chuyển quarantine, giữ idempotency và yêu cầu con người kiểm soát việc phát lại.
