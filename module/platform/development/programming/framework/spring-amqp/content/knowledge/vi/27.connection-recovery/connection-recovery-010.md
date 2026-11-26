# Blocked connection do giới hạn bộ nhớ hoặc dung lượng đĩa

## 1. Vì sao một kết nối RabbitMQ còn mở nhưng không gửi được message?

Khi dùng **Spring AMQP** để xây hệ thống bất đồng bộ, `RabbitTemplate` publish message qua **exchange**, **binding** định tuyến đến **queue**, còn `@RabbitListener` lấy message để xử lý. Một hiểu lầm thường gặp là: “TCP connection còn mở thì publisher vẫn gửi bình thường”, hoặc “khi gửi bị treo thì cứ reconnect là hết”.

RabbitMQ có cơ chế **resource alarms** để tự bảo vệ khi tài nguyên trên node gần cạn:

- **Memory alarm:** bộ nhớ RabbitMQ sử dụng vượt ngưỡng `vm_memory_high_watermark` được cấu hình.
- **Disk alarm:** dung lượng đĩa trống giảm xuống dưới ngưỡng `disk_free_limit` được cấu hình.

Khi có alarm, broker **tạm ngừng đọc dữ liệu từ các kết nối đang publish message**, tạo backpressure. Kết nối có thể còn sống, nhưng thao tác publish chậm, có thể bị block rồi timeout hoặc gặp lỗi I/O. Khi alarm được giải tỏa, broker cho phép xử lý publish trở lại. Đây là **blocked connection**, khác với sự cố mất kết nối TCP.

**Chủ đề của bài:** cách nhận biết, phòng ngừa và xử lý blocked connection do giới hạn RAM/đĩa trong **RabbitMQ + Spring AMQP**, đồng thời phân biệt việc khôi phục kết nối với khôi phục **độ tin cậy giao message đầu cuối**.

Sau bài học, bạn có thể:

1. Giải thích các ngưỡng memory/disk alarm, cơ chế block/unblock và phạm vi ảnh hưởng trong cluster.
2. Đọc tín hiệu `connection.blocked`/`connection.unblocked` từ RabbitMQ và các sự kiện tương ứng của Spring AMQP.
3. Tổ chức kết nối riêng cho producer/consumer để tránh tình huống worker không thể giải phóng tài nguyên.
4. Chuẩn đoán bằng RabbitMQ Management, CLI, log và metric Spring Boot.
5. Xử lý publisher confirm, timeout, retry, outbox và phục hồi mà không làm mất hoặc nhân đôi hiệu ứng nghiệp vụ.

> Tài liệu trình bày cơ chế của **RabbitMQ AMQP 0-9-1** và **Spring AMQP 2.x/3.x**. Tên API/config và mức watermark mặc định có thể thay đổi theo phiên bản RabbitMQ, Spring Boot/Spring AMQP và môi trường container. Hãy đối chiếu với phiên bản đang dùng, không suy ra một ngưỡng mặc định cố định cho mọi hệ thống.

## 2. Cơ chế resource alarms ở broker

### 2.1. Memory alarm

RabbitMQ cần RAM cho queue state, connection/channel, consumer, bộ đệm, metadata và các thao tác nội bộ. Khi mức sử dụng đạt ngưỡng `vm_memory_high_watermark` mà node áp dụng, RabbitMQ phát **memory alarm** để hạn chế publisher tạo thêm dữ liệu.

Ngưỡng này có thể khai báo theo tỷ lệ của lượng RAM broker nhận diện hoặc theo dung lượng tuyệt đối. Trong container/Kubernetes, lượng RAM broker nhận diện và giới hạn bộ nhớ của container có thể không trùng với mong đợi của người vận hành; một số phiên bản/documentation khuyến nghị dùng ngưỡng tuyệt đối khi triển khai trong container. **Không tăng watermark lên gần toàn bộ RAM chỉ để tắt alarm:** hệ điều hành vẫn có thể dừng tiến trình RabbitMQ vì hết bộ nhớ.

### 2.2. Disk alarm

RabbitMQ cần dung lượng đĩa để lưu message, thông tin của queue và các tệp nội bộ. Nếu không gian trống xuống thấp hơn `disk_free_limit`, broker sẽ hạn chế publisher để tránh ghi thêm đến mức đĩa cạn.

Điểm quan trọng:

- **Disk alarm dựa trên dung lượng trống**, không trực tiếp dựa trên tổng số message trong queue.
- Queue durable, message persistent, quorum queue và các đặc tính lưu trữ có thể tạo nhu cầu đĩa khác nhau.
- Chỉ tăng dung lượng đĩa hoặc giảm dữ liệu hợp lệ mới xử lý nguyên nhân; việc giảm ngưỡng cảnh báo thiếu căn cứ có thể làm tình hình xấu hơn.
- Dung lượng thực dùng có thể chưa giảm ngay tức thì sau khi một số message được ACK; còn phụ thuộc cách RabbitMQ quản lý tệp/segment và cơ chế thu hồi.

### 2.3. Những ai bị chặn?

~~~text
                  RabbitMQ cluster
                 +------------------+
Node A ----------| MEMORY alarm     |
                 | hoặc DISK alarm  |
                 +------------------+
                          |
                 Alarm cluster-wide
                          |
      +-------------------+-------------------+
      |                                       |
      v                                       v
Producer connection                     Consumer-only connection
RabbitTemplate.publish                  @RabbitListener nhận/ACK
      |                                       |
      v                                       v
Broker tạm ngừng đọc publish             Tiếp tục tiêu thụ
      |                                  (nếu độc lập về connection)
      v                                       |
Pending confirm / timeout                    v
                                        Queue có cơ hội giảm tải
~~~

**Alarm trong cluster có tác động toàn cluster:** nếu **một node** bị memory/disk alarm, các node khác cũng áp dụng hạn chế đối với kết nối publish. Đổi DNS hoặc kết nối publisher sang node còn khỏe không nhất thiết giải quyết được tình trạng block.

RabbitMQ ưu tiên giữ đường tiêu thụ hoạt động để consumer có thể lấy và ACK message, qua đó giảm áp lực tài nguyên. Tuy nhiên, nếu **producer và consumer dùng chung một TCP connection**, producer bị chặn có thể khiến các hoạt động khác đi qua kết nối đó cũng bị treo. Đây là lý do Spring AMQP khuyến nghị có **đường kết nối publish riêng** khi phù hợp.

Trên RabbitMQ Management/CLI, một số connection có trạng thái:

| Trạng thái | Ý nghĩa liên quan đến alarm |
| --- | --- |
| `running` | Connection đang hoạt động bình thường. |
| `blocking` | Broker đang ở chế độ ngăn publish, nhưng connection này chưa cố gửi message theo cách làm nó bị dừng. |
| `blocked` | Connection đã cố publish và broker hiện đang tạm ngừng xử lý dữ liệu trên connection. |
| `flow` (nếu hiển thị theo phiên bản/giao diện) | Backpressure/flow control **tạm thời** do tốc độ gửi, khác với resource alarm kéo dài; cần xem thêm metric. |
| `closed` / connection mất | TCP/AMQP connection không còn hoạt động; đây là tình huống khôi phục khác. |

Không suy luận “alarm không còn” chỉ vì một connection chưa chuyển sang `blocked`: broker có thể đang ở trạng thái `blocking`, hoặc ứng dụng chưa publish thêm. Cần xem **alarm trên từng node** và trạng thái của cluster.

## 3. Diễn biến khi broker chặn publisher

Ví dụ service xử lý đơn hàng gửi message `order.created`:

~~~text
10:00:00  RabbitTemplate.convertAndSend("orders.x", "order.created", ...)
10:00:01  RabbitMQ node A vượt memory watermark.
10:00:01  Resource alarm có hiệu lực trong cluster.
10:00:01  Broker gửi thông báo connection.blocked (client hỗ trợ).
10:00:02  Các publish mới trên connection bị hạn chế.
10:00:05  Publisher confirm chậm hoặc future/caller bị timeout.
10:00:10  Consumers tiếp tục xử lý, giải phóng tài nguyên.
10:00:12  Alarm được gỡ trên tất cả các node liên quan.
10:00:12  Broker gửi connection.unblocked.
10:00:13  Publish có thể tiếp tục; ứng dụng rà soát message chưa rõ kết quả.
~~~

Trình tự là ví dụ **minh họa**, không phải mốc thời gian được RabbitMQ bảo đảm. Lưu ý:

- `connection.blocked` là **thông báo của broker**, không đồng nghĩa TCP connection bị đóng.
- Broker có thể chặn việc đọc dữ liệu từ client; các lệnh publish và publisher confirm có thể bị trễ hoặc thất bại.
- Nếu cả memory và disk alarm đang hoạt động, `connection.unblocked` chỉ xuất hiện **khi tất cả resource alarms liên quan đã được giải tỏa**; không có thông báo blocked mới cho từng alarm phát sinh thêm.
- Broker tạm ngừng kiểm tra heartbeat trên các connection đang bị chặn do resource alarm theo cơ chế của nó. Tuy nhiên, ứng dụng vẫn có thể gặp timeout ở socket, transaction, caller hoặc tầng HTTP; không mặc định mọi request sẽ chờ vô hạn và tự thành công.

**Tính chất quan trọng:** nếu `RabbitTemplate.convertAndSend()` đã chạy mà ứng dụng **chưa nhận publisher confirm**, chưa thể kết luận broker đã nhận hay chưa. Việc retry sau timeout có nguy cơ gửi trùng message vốn đã được broker nhận trước đó.

## 4. Phân biệt blocked connection, mất kết nối và publisher flow control

| Tình huống | Connection còn mở? | Dấu hiệu | Cách xử lý chính |
| --- | --- | --- | --- |
| **Memory/disk alarm** | Thường có | `connection.blocked`, state `blocking/blocked`, alarm ở RabbitMQ, confirm trễ. | Xử lý áp lực RAM/đĩa, tạm giảm tốc độ publish, giữ consumer hoạt động. |
| **Mạng đứt/broker restart** | Không hoặc không ổn định | Shutdown, IOException, reconnect/recovery, channel bị đóng. | Khôi phục connection/topology, xác minh publish chưa rõ kết quả. |
| **Flow control tạm thời** | Có | State `flow`, publish chậm khi đầu vào vượt khả năng xử lý. | Điều chỉnh tốc độ producer/consumer, quan sát throughput. |
| **Routing không đúng** | Có | Publisher return/unroutable (nếu mandatory bật), queue đích không nhận. | Sửa exchange, routing key, binding, queue; không tăng bộ nhớ/đĩa một cách vô ích. |
| **Consumer backlog** | Có | Queue depth tăng, consumer lag, latency xử lý cao; có thể dẫn tới alarm sau đó. | Tối ưu consumer, prefetch, concurrency và chính sách giữ message. |

**Blocked connection không được “chữa” bằng vòng lặp reconnect liên tục.** Broker vẫn đang chịu cùng điều kiện tài nguyên và có thể block connection mới; reconnect vô tội vạ làm tăng số connection, tiêu thụ thêm RAM và che giấu nguyên nhân.

## 5. Theo dõi blocked/unblocked trong Spring AMQP

RabbitMQ hỗ trợ extension AMQP 0-9-1:

- `connection.blocked`: broker thông báo connection bị block và có thể kèm lý do.
- `connection.unblocked`: broker thông báo block đã được giải tỏa.

RabbitMQ Java client hỗ trợ `com.rabbitmq.client.BlockedListener`. Từ **Spring AMQP 2.0**, abstraction connection hỗ trợ blocked listener; `AbstractConnectionFactory` phát **`ConnectionBlockedEvent`** và **`ConnectionUnblockedEvent`** vào Spring application event system.

Ví dụ giám sát sự kiện (Spring Boot + spring-boot-starter-amqp):

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.amqp.rabbit.connection.ConnectionBlockedEvent;
import org.springframework.amqp.rabbit.connection.ConnectionUnblockedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class RabbitConnectionAlarmObserver {
    // Ví dụ đơn giản cho luồng publish một connection.
    private final AtomicBoolean blocked = new AtomicBoolean(false);

    @EventListener
    public void onBlocked(ConnectionBlockedEvent event) {
        blocked.set(true);
        System.err.println("RabbitMQ connection blocked: " + event);
        // Production: cập nhật metric, incident status hoặc admission control.
    }

    @EventListener
    public void onUnblocked(ConnectionUnblockedEvent event) {
        blocked.set(false);
        System.out.println("RabbitMQ connection unblocked: " + event);
        // Production: phục hồi có giới hạn tốc độ; không phát bù ồ ạt.
    }

    public boolean isBlocked() {
        return blocked.get();
    }
}
~~~

**Lưu ý khi triển khai thực tế:** sự kiện có thể đến từ **nhiều connection** (kể cả publisher connection riêng). Biến `AtomicBoolean` đơn lẻ ở đây chỉ để minh họa quan sát; nếu ứng dụng có nhiều connection, phải theo dõi **trạng thái theo từng connection/instance** hoặc dùng metric broker kết hợp circuit breaker cho đúng publisher. Không dùng biến này làm nguồn sự thật duy nhất để quyết định message đã được gửi.

Với Spring AMQP **trước 2.0**, cơ chế event ở trên chưa được cung cấp tương đương. Nếu dự án cũ cần tín hiệu ở mức client, có thể nghiên cứu việc đăng ký `BlockedListener` trực tiếp trên connection của RabbitMQ Java client, kèm quản lý vòng đời; không áp dụng nguyên mã Spring event cho bản cũ.

### Không xử lý nặng trên callback sự kiện

Event handler chỉ nên đổi trạng thái, ghi log/metric và kích hoạt cơ chế kiểm soát tốc độ. **Không chạy truy vấn chậm, publish hàng loạt, ngủ dài hoặc gọi `RabbitTemplate` ngay trong callback `connection.blocked`**: callback có thể chạy trên thread liên quan đến xử lý sự kiện connection và làm tình hình xấu hơn.

## 6. Tách đường kết nối publisher và consumer

### 6.1. Vì sao cần tách?

Giả sử một `@RabbitListener` nhận message, sau đó publish thông báo bằng `RabbitTemplate` **trên cùng TCP connection**. Khi broker block connection vì memory/disk alarm, thao tác publish có thể chiếm/chặn hoạt động của connection, khiến consumer khó ACK và giải phóng message. Hệ thống có thể rơi vào trạng thái:

~~~text
Memory pressure -> block publisher trên connection chung
       ^                             |
       |                             v
       +-- không giải phóng RAM <- consumer/ACK cũng bị ảnh hưởng
~~~

Với Spring AMQP hỗ trợ, cấu hình `RabbitTemplate` dùng connection publish riêng:

~~~java
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitPublisherConnectionsConfig {
    @Bean
    RabbitTemplate rabbitTemplate(CachingConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setUsePublisherConnection(true);
        return template;
    }
}
~~~

Lúc này, với `CachingConnectionFactory` phù hợp, `RabbitTemplate` sử dụng một **publisher connection** riêng, còn listener container dùng connection tiêu thụ. `setUsePublisherConnection(true)` được Spring AMQP hỗ trợ từ **2.0.2**; khi dùng Spring Boot, lưu ý bean `RabbitTemplate` tự định nghĩa có thể thay thế template mặc định nên cần kiểm tra các thiết lập `MessageConverter`, mandatory, retry, confirms và callbacks đang dùng.

Đây là **tách TCP connection trong cùng môi trường broker/cluster**, không phải cách bỏ qua resource alarms. Khi RabbitMQ thiếu tài nguyên, publisher connection riêng vẫn bị block, nhưng consumer connection có cơ hội tiếp tục đọc và ACK để giảm áp lực.

**Ngoại lệ quan trọng:** nếu producer gửi trong **transaction được khởi tạo bởi listener container**, Spring AMQP có thể dùng chính channel của listener transaction, dù đã bật `usePublisherConnection`. Khi đó không được hứa bảo đảm cô lập tuyệt đối; cân nhắc tách publish ra khỏi listener transaction bằng outbox hoặc thiết kế giao tiếp khác.

### 6.2. Khi nào nên dùng hai CachingConnectionFactory?

Trong cấu hình phức tạp, có thể dùng hai `CachingConnectionFactory` rõ ràng với các giới hạn/kết nối khác nhau cho producer và consumer. Cần cấu hình đầy đủ credentials, SSL, heartbeat, publisher confirms, exception handling và bean `RabbitAdmin` đúng factory. Không nên vô tình khai báo **exclusive/anonymous queue** trên publisher connection rồi tiêu thụ bằng connection khác, vì queue đó có phạm vi gắn với connection sở hữu.

Với phần lớn ứng dụng Spring AMQP hiện đại, thử `setUsePublisherConnection(true)` trước khi xây hệ thống hai connection factory riêng.

## 7. Điều chỉnh publisher theo backpressure và khả năng chưa rõ kết quả

### 7.1. Khi thấy blocked, nên làm gì ở ứng dụng?

1. **Chuyển hệ thống publish sang chế độ giảm tải**: hạn chế tốc độ, giảm số request in-flight hoặc tạm ngừng lấy việc publish mới. Không cho request mới xếp hàng chờ trong RAM không giới hạn.
2. **Giữ công việc cần giao an toàn trong durable store** (transactional outbox, bảng job hoặc nhật ký sự kiện bền vững) trước khi publish.
3. **Không hứa đã giao message** chỉ vì `RabbitTemplate.convertAndSend()` đã trả về. Với blocked connection, cần phân biệt thao tác Java kết thúc và broker xử lý publish.
4. **Giới hạn thời gian chờ confirm**; khi timeout, ghi kết quả là **UNKNOWN** chứ không tự kết luận `NOT_PUBLISHED`.
5. **Khi unblocked**, phát lại theo tốc độ kiểm soát, giữ nguyên business event ID và kiểm tra publisher confirm; consumer phải idempotent.

### 7.2. Publisher confirms và returns

Trong Spring Boot, có thể bật publisher confirms/returns:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Một publisher gắn message ID ổn định cho từng lần thử:

~~~java
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class ReliableOrderEventPublisher {
    private final RabbitTemplate template;

    public ReliableOrderEventPublisher(RabbitTemplate template) {
        this.template = template;
    }

    public CorrelationData publishOrderEvent(String eventId,
                                             String payload) {
        CorrelationData cd = new CorrelationData(eventId);

        template.convertAndSend(
                "orders.events.x",
                "order.created",
                payload,
                message -> {
                    message.getMessageProperties().setMessageId(eventId);
                    return message;
                },
                cd
        );
        return cd;
    }
}
~~~

Caller hoặc dispatcher outbox cần theo dõi `cd.getFuture()` và `cd.getReturned()` trong cơ chế confirm/return của **đúng phiên bản Spring AMQP**:

~~~java
CorrelationData cd = publisher.publishOrderEvent(eventId, payload);

cd.getFuture().whenComplete((confirm, error) -> {
    if (error != null || confirm == null || !confirm.isAck()) {
        // Không có bằng chứng broker đã nhận thành công.
        // Ghi retry/UNKNOWN theo policy, giữ nguyên eventId.
        return;
    }

    if (cd.getReturned() != null) {
        // Broker có thể confirm ACK nhưng message unroutable.
        // Cần sửa topology/routing trước khi retry.
        return;
    }

    // Publish được broker xác nhận và không có returned message.
    // Chưa chứng minh consumer đã xử lý nghiệp vụ.
});
~~~

**Ví dụ giả định:**

- Exchange `orders.events.x` tồn tại, type/arguments đúng.
- Queue `orders.created.q` đã bind với routing key `order.created`.
- Publisher confirm type là `correlated`; mandatory/returns được bật.
- Kết quả callback được ghi lại bền vững; ví dụ code trên chỉ thể hiện **nhánh quyết định**, chưa có repository/outbox và chưa xử lý timeout.

Với `RabbitTemplate` custom ở mục 6, thuộc tính `spring.rabbitmq.template.mandatory` của Spring Boot có thể không được áp dụng như với auto-configured template. Hãy **đặt `template.setMandatory(true)`** nếu cần mandatory returns, đồng thời kiểm tra tính đồng bộ của cấu hình trên factory thật.

### 7.3. Unknown outcome và idempotency

Khi broker đã nhận một publish rồi nhưng publisher bị block hoặc mất kết nối trước khi nhận confirm, **retry** có thể gây giao message hai lần. Quy tắc an toàn:

~~~text
business operation ID = ORDER-123-CREATED
              |
              v
outbox(eventId = UUID cố định, state = PENDING)
              |
       publish attempt #1 ------> confirm timeout / UNKNOWN
              |
       retry attempt #2 với cùng eventId
              |
              v
Consumer inbox UNIQUE(eventId)
  lần đầu -> tạo tác vụ
  lần sau -> bỏ qua trùng
~~~

Không thay event ID sau mỗi timeout. Consumer cần idempotency ở lớp nghiệp vụ, chẳng hạn unique constraint trên `event_id` và ghi nhận kết quả cùng một transaction database. Đặc biệt khi message kích hoạt thanh toán, gửi email hay tạo vận đơn, không được dựa vào **exactly-once delivery** mặc định của broker.

## 8. Phân tích alarm bằng RabbitMQ Management và CLI

### 8.1. Các lệnh kiểm tra trên broker

Chạy **trên node RabbitMQ** có quyền truy cập CLI (hoặc trong container tương ứng). Các lệnh sau dùng để **quan sát**, không đổi ngưỡng:

~~~bash
# Liệt kê resource alarms đang hoạt động trong cluster.
rabbitmq-diagnostics alarms

# Health check: exit code khác 0 khi còn alarm.
rabbitmq-diagnostics check_alarms

# Trạng thái node (memory, disk, runtime).
rabbitmq-diagnostics status

# Phân tích sử dụng bộ nhớ theo nhóm.
rabbitmq-diagnostics memory_breakdown

# Xem kết nối publish/consumer, trạng thái blocking/blocked.
rabbitmqctl list_connections name state

# Kiểm tra queue và message chờ/đã giao chưa ACK.
rabbitmqctl list_queues name messages_ready messages_unacknowledged consumers
~~~

Với cluster, dùng `--node`/`-n` theo cú pháp CLI của phiên bản đang chạy để kiểm tra **từng node**, vì alarm có thể bắt nguồn từ node khác nơi ứng dụng kết nối. Nếu dùng nhiều virtual host, chọn đúng vhost khi xem queue.

### 8.2. Bảng điều tra nhanh

| Dấu hiệu | Kiểm tra đầu tiên | Ý nghĩa thực tế |
| --- | --- | --- |
| `connection.blocked` và memory alarm | `rabbitmq-diagnostics alarms`, `memory_breakdown`, queue backlog, số connection/channel. | Broker cần giảm RAM hoặc tăng dung lượng tài nguyên hợp lệ. |
| Disk alarm | `alarms`, `status`, filesystem/quota/PVC, log và queue storage. | Không gian trống thấp; xử lý tài nguyên lưu trữ. |
| Publish bị treo, không có event blocked | Xem trạng thái connection ở broker, confirm latency, I/O, version/client capabilities. | Có thể là flow control, nghẽn mạng, pool channel hoặc metric còn thiếu. |
| Consumer không giảm queue | Kiểm tra `messages_ready`, `messages_unacknowledged`, concurrency, prefetch và consumer lỗi. | Consumer không chạy/không ACK; tăng worker chỉ sau khi xác định nguyên nhân. |
| Broker báo alarm đã hết nhưng retry vẫn lỗi | Kiểm tra publisher connection, socket, confirm, topology và circuit breaker. | Unblock không bảo đảm tất cả publish đang chờ đã thành công. |

### 8.3. Metric và alert

Nên theo dõi cả broker lẫn ứng dụng:

| Nhóm | Metric/tín hiệu cần có | Gợi ý hành động |
| --- | --- | --- |
| Broker memory | RAM sử dụng, `vm_memory_high_watermark`, `memory_alarm`. | Cảnh báo **trước** ngưỡng, tìm queue/connection chiếm RAM. |
| Broker disk | Dung lượng đĩa trống, disk limit/alarm, tốc độ ghi. | Tăng năng lực lưu trữ hoặc dọn dữ liệu theo retention hợp lệ. |
| Broker connection | Số `blocked`/`blocking`, block duration, số connection, channel. | Phát hiện backpressure và chia sẻ connection sai. |
| Broker queue | Ready/unacked messages, oldest message age, consumer throughput. | Phát hiện backlog và nguyên nhân tăng tài nguyên. |
| Publisher | Publish attempts, confirm ACK/NACK/timeout, returned message, in-flight. | Phân biệt thành công, thất bại và trạng thái chưa rõ. |
| Business | Tuổi outbox, số event pending, số event đến consumer, lag end-to-end. | Biết xử lý nghiệp vụ có đang dừng hay không. |

Tránh dùng ID riêng của từng message làm label cho Prometheus/Micrometer metric vì cardinality rất cao. Event ID nên ở log/tracing và dữ liệu outbox/inbox.

## 9. Khôi phục đúng cách khi broker thiếu bộ nhớ hoặc đĩa

### 9.1. Quy trình xử lý memory alarm

1. Xác nhận node nào gây alarm và so với watermark/limit thực tế; xem `memory_breakdown`.
2. Kiểm tra queue backlog, nhiều message `unacked`, prefetch quá cao, consumer không hoạt động, connection/channel tăng đột biến và payload quá lớn.
3. Cho **consumer khỏe mạnh tiếp tục ACK** trên connection riêng; giảm tốc publish hoặc tạm dừng lấy thêm công việc mới ở producer.
4. Điều chỉnh nguyên nhân: scale consumer/giảm xử lý chậm, giới hạn backlog/payload, sửa leak hoặc tăng RAM phù hợp môi trường.
5. Khi alarm hết, xác minh `connection.unblocked`, confirm latency giảm, consumer còn hoạt động và outbox tiếp tục drain có giới hạn.

Không khuyên **purge queue** để giải phóng RAM nếu chưa xác định message nào có thể bỏ; purge có thể xóa dữ liệu nghiệp vụ chưa xử lý. Cũng không tăng `vm_memory_high_watermark` tùy tiện để che alarm.

### 9.2. Quy trình xử lý disk alarm

1. Kiểm tra filesystem/PVC có đang hết dung lượng, quota, log, tệp của RabbitMQ và vị trí data directory.
2. Xác định queue, lưu lượng persistent message, message tồn lâu, DLQ backlog và chính sách lưu trữ làm tăng dung lượng.
3. Tăng không gian lưu trữ hoặc xử lý retention đúng quy định, duy trì consumer có thể xử lý message còn tồn.
4. Tránh tự ý xóa tệp trong **RabbitMQ data directory** khi broker chạy; việc đó có thể phá hỏng trạng thái queue.
5. Chờ broker thực sự thấy dung lượng trống vượt ngưỡng, mọi alarm được xóa, sau đó xác minh publisher/consumer và tình trạng message.

Một hệ thống dùng quorum queues hoặc có data replication cần tính thêm dung lượng trên từng node và bản sao. Một node cạn disk có thể ảnh hưởng publisher trên cả cluster.

### 9.3. Vì sao không khôi phục bằng reconnect hàng loạt?

Khi resource alarm đang tồn tại, reconnect không sửa RAM/disk và có thể tạo thêm connection/channel, tăng chi phí bộ nhớ. Khi alarm được xóa, các connection còn hoạt động có thể nhận `connection.unblocked` và xử lý trở lại. Chỉ reconnect khi **connection thực sự hỏng**; dùng backoff/jitter và giới hạn attempt, không tự động quay vòng hàng nghìn kết nối.

## 10. Tình huống khó: consumer cũng publish phản hồi

Ví dụ listener xử lý `payment.completed`, sau đó publish `invoice.created` trước khi ACK. Nếu publisher và consumer cùng dùng connection, resource alarm có thể cản trở cả đường giải phóng queue. Tách connection như mục 6 giúp giảm rủi ro, nhưng còn các câu hỏi:

- Nếu **publish `invoice.created` chưa xác định được kết quả**, consumer có ACK `payment.completed` hay không?
- Nếu listener bị retry, có tạo hai hóa đơn không?
- Nếu publish nằm trong transaction consumer, có thực sự dùng publisher connection riêng không?

Một mô hình bền vững là **transactional outbox**:

~~~text
@RabbitListener nhận payment.completed
           |
           v
DB transaction:
  1. Lưu idempotency record của payment event
  2. Lưu/cập nhật trạng thái hóa đơn
  3. Tạo outbox event invoice.created
           |
           v
DB commit -> listener ACK
           |
           v
Dispatcher riêng publish outbox với confirm/return
           |
           v
Alarm -> giữ outbox, retry có backoff
Unblock -> tiếp tục phát, giữ eventId bất biến
~~~

Như vậy, consumer không cần **block chờ RabbitTemplate publish** để hoàn tất một xử lý nghiệp vụ trong khi broker đang thiếu tài nguyên. Outbox tránh mất sự kiện giữa DB commit và publish; inbox/idempotency tránh lỗi tạo tác dụng phụ trùng khi message được giao lại.

## 11. Bài thực hành kiểm chứng

**Bối cảnh:** Spring Boot service có một `RabbitTemplate` gửi `order.created`, một `@RabbitListener` tiêu thụ `orders.created.q`, RabbitMQ đang chạy trong môi trường **test riêng biệt**.

### 11.1. Chuẩn bị topology

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderQueueTopology {
    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange("orders.events.x", true, false);
    }

    @Bean
    Queue ordersQueue() {
        return QueueBuilder.durable("orders.created.q").build();
    }

    @Bean
    Binding ordersBinding(Queue ordersQueue,
                          DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
                .to(ordersExchange)
                .with("order.created");
    }
}
~~~

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {
    @RabbitListener(queues = "orders.created.q")
    public void handle(String eventId) {
        // Trong hệ thống thật, lưu eventId đã xử lý để chống trùng.
        System.out.println("Consumed order event: " + eventId);
    }
}
~~~

### 11.2. Các bước kiểm thử

1. Khởi động broker, producer và consumer. Đảm bảo binding `order.created` hoạt động; quan sát publish confirm và consumer ACK bình thường.
2. Bật quan sát `ConnectionBlockedEvent`/`ConnectionUnblockedEvent`; kiểm tra trạng thái connection trong Management UI.
3. **Chỉ trên môi trường test riêng**, nhờ quản trị viên mô phỏng memory hoặc disk alarm bằng cách điều chỉnh ngưỡng có kiểm soát. **Ghi nhận ngưỡng ban đầu và phục hồi đúng giá trị sau bài test.** Không cố làm đầy ổ đĩa thật, không thử nghiệm lên cluster dùng chung.
4. Khi alarm xuất hiện, publish một vài event ID cố định; ghi rõ thời điểm `convertAndSend` và thời điểm publisher confirm (nếu có). Quan sát `blocking/blocked`, timeout và hành vi consumer.
5. Tách publisher connection bằng `setUsePublisherConnection(true)` rồi so sánh việc consumer có thể tiếp tục nhận/ACK trong khi publisher bị block.
6. Khôi phục tài nguyên/ngưỡng; đợi `connection.unblocked` và `rabbitmq-diagnostics check_alarms` không còn báo lỗi. Kiểm tra producer drain dần backlog.
7. Chủ động tạo một lần publish **không có confirm rõ ràng**, rồi phát lại cùng event ID qua outbox. Kiểm tra consumer idempotent chỉ tạo một kết quả nghiệp vụ.
8. Thử trường hợp queue/routing key sai để phân biệt **publisher return** với **resource blocked**.

Mỗi lần thử ghi bảng:

| Thời điểm | Broker alarm | Connection state | Event ID | Publisher confirm/return | Consumer nhận | Kết luận |
| --- | --- | --- | --- | --- | --- | --- |
| Trước alarm | Không | `running` | `evt-01` | Confirm ACK | Có | Đường đi bình thường. |
| Trong alarm | Memory/disk | `blocked` | `evt-02` | Chưa có/timeout | Chưa rõ | **Không được kết luận message đã mất.** |
| Sau unblock | Không | `running` | `evt-02` | Kiểm tra lại | Có hoặc chưa | Đối soát theo eventId. |

### Câu hỏi tự kiểm tra

**Câu 1.** RabbitMQ phát `connection.blocked` nhưng Java application chưa mất TCP connection. Tự reconnect ngay có giải quyết memory alarm không?

**Đáp án:** Không. Resource alarm vẫn còn và có thể block connection mới. Cần giải quyết áp lực tài nguyên, giảm producer load, cho consumer xử lý/ACK rồi xác minh `unblocked`.

**Câu 2.** Producer publish bị timeout khi broker đang blocked. Có thể kết luận message chưa đến RabbitMQ không?

**Đáp án:** Không. Kết quả có thể không xác định; khi retry phải giữ eventId và có idempotency ở consumer để chống trùng.

**Câu 3.** Có thể kết nối sang node B để tránh alarm do node A hết disk trong cùng cluster không?

**Đáp án:** Không nên kỳ vọng điều đó. Resource alarms áp dụng **cluster-wide**, cần xử lý node gây alarm.

**Câu 4.** Đã bật `setUsePublisherConnection(true)`, liệu publish trong consumer transaction có luôn dùng connection riêng?

**Đáp án:** Không. Spring AMQP có thể dùng channel thuộc transaction của listener; cần kiểm tra cấu hình và cân nhắc outbox nếu muốn giảm phụ thuộc.

**Câu 5.** Có `ConnectionUnblockedEvent` nghĩa là tất cả publish trước đó đã được xử lý thành công?

**Đáp án:** Không. Event này chỉ báo broker đã giải tỏa block; các lệnh/confirm trước đó vẫn cần được kiểm tra, đối soát và retry an toàn nếu kết quả chưa rõ.

## 12. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| Xem blocked là connection down. | Reconnect liên tục và thêm áp lực broker. | Phân biệt alarm, blocked và lỗi socket. |
| Dùng chung connection publisher–consumer khi consumer cần giải phóng backlog. | Nguy cơ phụ thuộc vòng tròn, ACK trì trệ. | Cân nhắc publisher connection riêng; hiểu ngoại lệ transaction. |
| Bỏ qua publisher confirm/return. | Không biết publish được broker nhận và route chưa. | Bật correlated confirms, mandatory returns khi cần. |
| Retry message với event ID mới sau timeout. | Consumer có thể tạo hiệu ứng hai lần. | Giữ business event ID và idempotency. |
| Giữ message chưa gửi chỉ trong bộ đệm RAM. | Producer crash có thể làm mất công việc. | Transactional outbox hoặc durable job queue phía nguồn. |
| Tăng watermark hoặc hạ disk limit vô căn cứ. | Che vấn đề, tăng nguy cơ OOM/hết đĩa thật. | Dùng capacity planning, phân tích nguồn tiêu thụ tài nguyên. |
| Dựa vào queue depth duy nhất. | Bỏ sót message chưa được publish, in-flight confirm hoặc task sau ACK. | Theo dõi cả outbox, broker, consumer, hiệu ứng nghiệp vụ. |

## 13. Ghi nhớ

**Blocked connection** do **memory/disk resource alarm** là cơ chế RabbitMQ **tạm dừng nhận publish để tự bảo vệ**, có thể xảy ra khi TCP connection vẫn sống. Alarm có hiệu lực ở phạm vi cluster và chỉ được giải tỏa khi tài nguyên đáp ứng điều kiện; đổi node hoặc reconnect thường không sửa nguyên nhân. Trong **Spring AMQP**, theo dõi **ConnectionBlockedEvent/ConnectionUnblockedEvent**, tách publisher–consumer connection khi phù hợp (`RabbitTemplate.setUsePublisherConnection(true)`), kết hợp publisher confirm/return, backpressure, outbox, retry có giới hạn và idempotency để phục hồi tin cậy. Sau khi nhận `unblocked`, **vẫn phải đối soát những message có kết quả publish chưa rõ**.

### Tài liệu chính thức

- [RabbitMQ: Memory and Disk Alarms](https://www.rabbitmq.com/docs/alarms) — điều kiện alarm và phạm vi cluster.
- [RabbitMQ: Blocked Connection Notifications](https://www.rabbitmq.com/docs/connection-blocked) — `connection.blocked`, `connection.unblocked` và BlockedListener.
- [RabbitMQ: Memory Threshold](https://www.rabbitmq.com/docs/memory) — cách tính/cấu hình ngưỡng bộ nhớ.
- [RabbitMQ: Diagnostic CLI](https://www.rabbitmq.com/docs/man/rabbitmq-diagnostics.8) — `alarms`, `check_alarms`, `memory_breakdown`.
- [Spring AMQP: Connection and Resource Management](https://docs.spring.io/spring-amqp/reference/amqp/connections.html) — các Spring connection events và tách đường kết nối.
- [Spring AMQP: RabbitTemplate and Separate Publisher Connection](https://docs.spring.io/spring-amqp/reference/amqp/template.html) — `setUsePublisherConnection` và giới hạn trong transaction.
