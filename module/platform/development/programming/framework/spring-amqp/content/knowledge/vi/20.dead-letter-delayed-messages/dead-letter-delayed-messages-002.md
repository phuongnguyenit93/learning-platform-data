# Các nguyên nhân dead-letter: reject, hết hạn, giới hạn và delivery limit

Trong **Spring AMQP**, một message được gửi bằng **RabbitTemplate** qua exchange và binding vào queue, rồi được **@RabbitListener** tiêu thụ. Tuy nhiên, không phải message nào cũng được xử lý thành công. Có message bị consumer từ chối; có message chờ quá lâu rồi hết TTL; có queue đã đầy; và có message liên tục được giao lại trên **quorum queue** đến mức vượt giới hạn xử lý lỗi. RabbitMQ gọi thao tác chuyển những message đó sang một **dead-letter exchange (DLX)** là *dead-lettering*.

Bài thuộc chương **Dead-letter và trì hoãn** của module **SPRING_AMQP**. Mục tiêu là phân biệt **bốn nguyên nhân chính xác** dẫn đến dead-letter, biết cách cấu hình topology RabbitMQ và Spring AMQP, đọc metadata nguyên nhân, tránh thất lạc message, và chọn chính sách retry/dead-letter phù hợp.

**Bốn nguyên nhân cần nhớ:** **rejected**, **expired**, **maxlen** và **delivery_limit**. Đây là các giá trị của trường **reason** trong metadata **x-death** của AMQP 0-9-1; tên nguyên nhân cần giữ nguyên khi đọc log, không tự đổi thành tên nghiệp vụ.

Sau bài này, bạn sẽ:

1. Giải thích **DLX khác DLQ** và diễn tả dòng chuyển message giữa các queue.
2. Chủ động tạo từng nguyên nhân **rejected**, **expired**, **maxlen**, **delivery_limit** trong môi trường lab.
3. Phân biệt **basic.reject/basic.nack** và **requeue=true/false**, cùng cách Spring listener container tác động đến kết quả.
4. Hiểu **message TTL**, **queue expiry**, **max-length/overflow**, **quorum queue delivery-limit** và những khác biệt theo phiên bản RabbitMQ.
5. Đọc **x-death** và kiểm tra bằng RabbitMQ Management/CLI; thiết kế retry, idempotency, bảo vệ dữ liệu và giám sát DLQ.

## 1. Dead-lettering là gì, và cần cấu hình những gì?

**Dead-letter exchange (DLX)** chỉ là một exchange RabbitMQ bình thường được chọn làm đích để broker **republish** message rời khỏi một queue vì lý do dead-letter. Một **dead-letter queue (DLQ)** là queue được bind vào DLX để chứa message phục vụ kiểm tra, retry, đối soát hoặc xử lý thủ công.

~~~mermaid
flowchart LR
    P["RabbitTemplate<br/>Publisher"] --> E{"Exchange nghiệp vụ"}
    E -->|"Binding hợp lệ"| Q[("Queue chính")]
    Q -->|"Reject / TTL / max length<br/>/ quorum delivery limit"| D{"Dead-letter exchange<br/>DLX"}
    D -->|"Dead-letter routing key"| DLQ[("Dead-letter queue<br/>DLQ")]
    Q -->|"Deliver bình thường"| C["@RabbitListener"]
    C -->|"ACK thành công"| END["Message kết thúc"]
~~~

Trong topology này, DLQ không phải “khu vực bí mật tự động xuất hiện”. Cần đủ các phần:

1. **Queue nguồn** có cấu hình trỏ tới DLX bằng **x-dead-letter-exchange** hoặc policy **dead-letter-exchange**.
2. **DLX** tồn tại trong **cùng virtual host** với queue nguồn.
3. **Binding** từ DLX đến queue đích khớp routing key dùng khi dead-letter.
4. Publisher/consumer và người dùng RabbitMQ có quyền phù hợp; cấu hình sai có thể khiến message không đến DLQ.
5. Ứng dụng có quy trình **quan sát, phân loại và xử lý message trong DLQ**; đưa vào DLQ chưa đồng nghĩa đã giải quyết lỗi nghiệp vụ.

**Dead-letter ≠ requeue.** Requeue trả message về queue để tiếp tục được giao lại. Dead-letter chuyển message khỏi queue nguồn để broker publish sang DLX; DLX lại định tuyến theo binding đến queue khác, nếu có.

### DLX và DLQ không tự bảo đảm exactly-once

Ở nhiều cấu hình, việc republish dead-letter **không mặc nhiên có bảo đảm an toàn end-to-end**. Nếu DLX bị thiếu, binding không khớp, queue đích không chấp nhận hoặc node lỗi, message có thể không đến DLQ như kỳ vọng. Quorum queue có tùy chọn **at-least-once dead-lettering**, nhưng phải bật đúng các điều kiện; mặc định không nên coi mọi DLX là durable handoff.

## 2. Bảng tổng hợp bốn nguyên nhân chính

| Reason trong x-death | Sự kiện gây ra | Cơ chế/cấu hình | Áp dụng |
| --- | --- | --- | --- |
| **rejected** | Consumer gửi **basic.reject** hoặc **basic.nack** với **requeue=false** | Manual ACK, container error handler hoặc reject policy | Classic và quorum queue |
| **expired** | Message ở trong queue vượt **message TTL** | **x-message-ttl**, policy **message-ttl** hoặc property **expiration** | Queue có hỗ trợ TTL cho message |
| **maxlen** | Queue loại message vì vượt **max length / max length bytes** theo overflow strategy | **x-max-length**, **x-max-length-bytes**, policy tương ứng và **overflow** | Classic và quorum với những khác biệt về overflow |
| **delivery_limit** | Message trên **quorum queue** vượt giới hạn các lần giao thất bại được tính | **delivery-limit** policy hoặc **x-delivery-limit** | **Chỉ quorum queue** |

**Bốn trường hợp trên đều xảy ra sau khi message đã có mặt ở một queue nguồn.** Một message publisher gửi sai routing key và không được exchange định tuyến tới queue **không phải** là một dead-letter ở queue; muốn biết trường hợp unroutable từ publisher phải dùng **mandatory/publisher returns** và publisher confirms theo đúng ngữ nghĩa.

### Những sự kiện KHÔNG phải nguyên nhân dead-letter

| Sự kiện | Có tự phát sinh x-death không? | Giải thích |
| --- | --- | --- |
| Consumer **basic.ack** | **Không** | Message đã được xác nhận xử lý |
| Consumer **basic.nack(requeue=true)** | **Không ngay lập tức** | Message được trả về queue; có thể dẫn đến **delivery_limit** trong điều kiện nhất định |
| Publisher gửi tới exchange không có binding | **Không** | Message chưa từng vào queue nguồn; phụ thuộc mandatory/returns |
| Toàn bộ queue hết hạn do **x-expires** | **Không** | Queue bị xóa khi đủ điều kiện; **các message trong queue không được dead-letter** |
| Queue bị **delete/purge** | **Không** | Xóa/purge không phải quy trình dead-letter message |
| Consumer không hoạt động | **Không tự động** | Message có thể vẫn Ready, cho tới khi chạm TTL/maxlen hoặc cơ chế khác |
| Message nằm Unacked quá lâu | **Không mặc định chỉ vì thời gian chờ** | Broker có thể đóng channel do ACK timeout, sau đó redelivery; với quorum có thể ảnh hưởng bộ đếm giao thất bại |

## 3. Nguyên nhân 1 — rejected: consumer chủ động từ chối

Consumer đang giữ một delivery có thể:

- **ACK** khi đã xử lý xong: broker xóa delivery khỏi queue, không dead-letter.
- **basic.reject(tag, false)**: từ chối **không requeue** → message trở thành dead-letter với reason **rejected** nếu DLX đã được cấu hình.
- **basic.nack(tag, false, false)**: từ chối không requeue → cũng có thể dead-letter với reason **rejected**.
- **basic.reject(tag, true)** hoặc **basic.nack(tag, false, true)**: trả message để có thể redeliver; **không có x-death rejected tại thời điểm đó**.

Trong các lệnh trên, **tag** là **deliveryTag trên channel nhận message**, không phải eventId. Tham số cuối là **requeue**; với **basic.nack**, tham số boolean thứ hai là **multiple**.

~~~mermaid
flowchart TD
    Q[("Queue")] --> C{"Consumer xử lý"}
    C -->|"Thành công"| A["basic.ack"]
    C -->|"Lỗi có thể retry"| R["requeue=true"]
    C -->|"Lỗi không thể sửa"| N["basic.reject(tag,false)<br/>hoặc basic.nack(tag,false,false)"]
    R --> Q
    N --> D{"DLX"} --> X[("DLQ<br/>x-death reason=rejected")]
~~~

### 3.1. Trong Spring AMQP, throw exception chưa chắc vào DLQ

Một **@RabbitListener** có container chế độ **AUTO** thường được container ACK khi handler thành công. Khi handler ném exception:

- Cấu hình **defaultRequeueRejected=true** (thường là mặc định) khiến lỗi thông thường được reject/nack **có requeue**.
- **AmqpRejectAndDontRequeueException** khiến message bị từ chối **không requeue**, bất kể mặc định.
- **defaultRequeueRejected=false** có thể khiến lỗi thông thường không requeue; cần DLX để dead-letter.
- Lỗi convert/validation trước khi handler được gọi có thể được **ErrorHandler** phân loại là fatal theo chính sách riêng; đừng mặc định mọi lỗi đều có một cách requeue giống nhau.

Ví dụ khi payload có vấn đề vĩnh viễn:

~~~java
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class InvalidOrderRejectListener {

    @RabbitListener(queues = "lab.dead.reject")
    public void onOrder(String payload) {
        if (!payload.startsWith("order.created:")) {
            throw new AmqpRejectAndDontRequeueException(
                    "Unsupported order event payload");
        }

        // Chỉ hoàn tất khi công việc nghiệp vụ thật sự hoàn tất.
        System.out.println("Processed: " + payload);
    }
}
~~~

Đây là một ví dụ **AUTO acknowledge**. Với payload không hợp lệ, exception yêu cầu container không requeue, nên nếu queue có DLX hợp lệ sẽ được dead-letter với reason **rejected**. Không cần tự gọi **Channel.basicReject** trong listener AUTO; làm đồng thời có thể ACK/NACK trùng.

### 3.2. Manual ACK/NACK cho cùng mục tiêu

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class ManualRejectListener {

    @RabbitListener(
            queues = "lab.dead.reject",
            ackMode = "MANUAL")
    public void onMessage(
            String payload,
            Channel channel,
            @Header(AmqpHeaders.DELIVERY_TAG) long deliveryTag)
            throws IOException {

        if (!payload.startsWith("order.created:")) {
            channel.basicReject(deliveryTag, false);
            return;
        }

        // Giả định business transaction đã commit thành công.
        channel.basicAck(deliveryTag, false);
    }
}
~~~

Hai listener trong phần 3.1 và 3.2 là **lựa chọn thay thế** cho cùng queue. Không bật cả hai khi làm lab, vì RabbitMQ sẽ phân phối delivery cho các consumer cạnh tranh và phép thử thiếu tính dự đoán.

**Cảnh báo:** **requeue=true không phải delayed retry**. Broker có thể giao lại rất nhanh, tạo *hot loop*. Với lỗi tạm thời cần retry có giới hạn và backoff; với lỗi dữ liệu vĩnh viễn cần dead-letter hoặc cơ chế cách ly phù hợp.

## 4. Nguyên nhân 2 — expired: message hết thời gian sống

**Message TTL (time to live)** giới hạn thời gian message được giữ ở một queue. Nếu message **chưa được giao thành công** khi thời gian tồn tại trong queue vượt TTL áp dụng, broker có thể loại bỏ nó và đưa tới DLX với reason **expired**.

### 4.1. Hai cách đặt message TTL

| Vị trí | Tên cấu hình | Ý nghĩa |
| --- | --- | --- |
| Trên **queue** | Policy **message-ttl** hoặc argument **x-message-ttl** | Thời gian sống của message trong queue đó, đơn vị **mili-giây** |
| Trên **message do publisher gửi** | AMQP **expiration** property | TTL riêng của message; biểu diễn bằng **chuỗi số mili-giây** theo AMQP 0-9-1 |

Ví dụ Spring AMQP đặt TTL mặc định của message trong một queue:

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;

Queue queue = QueueBuilder.durable("lab.dead.ttl")
        .ttl(2000)
        .deadLetterExchange("lab.dead.dlx")
        .deadLetterRoutingKey("dead.any")
        .build();
~~~

Message ở queue **lab.dead.ttl** quá khoảng **2.000 ms** có thể được dead-letter nếu vẫn chờ trong queue, còn topology DLX đích hoạt động. **TTL không phải lịch hẹn xử lý đúng thời điểm với độ chính xác tuyệt đối**: broker có thể thu hồi message hết hạn khi chúng tới đầu queue hoặc tại các sự kiện xử lý nhất định.

Ví dụ TTL riêng của một lần publish:

~~~java
rabbitTemplate.convertAndSend(
        "lab.dead.work",
        "case.ttl",
        "expires-after-1500-ms",
        message -> {
            message.getMessageProperties().setExpiration("1500");
            return message;
        }
);
~~~

Nếu **cả queue TTL và message TTL** được áp dụng, giới hạn hiệu lực cho message là giới hạn chặt hơn. Trong bài lab, tránh đặt cả hai đồng thời khi chưa hiểu kết quả để dễ quan sát nguyên nhân.

### 4.2. Vì sao message không dead-letter đúng từng mili-giây?

Trong **classic queue**, expired messages thường được dead-letter khi chúng tới **đầu queue**, hoặc khi có thay đổi policy ảnh hưởng queue. Vì thế một message có TTL ngắn có thể đứng phía sau message khác có TTL dài; nó đã hết TTL nhưng vẫn chưa được loại vật lý ngay và có thể còn được tính vào thông số queue. Quorum queue cũng xử lý expired message khi đến đầu queue theo cơ chế riêng.

~~~text
Thời điểm t=0:
  Queue: [M1 TTL=60s] [M2 TTL=2s]

Thời điểm t=3s:
  M2 đã vượt TTL nhưng có thể chưa được dead-letter
  vì M1 đang nằm ở đầu queue.

Khi M2 đến đầu queue:
  broker không giao M2 cho consumer,
  mà hết hạn/đưa sang DLX nếu đủ điều kiện.
~~~

Không nên dùng TTL làm một bộ lập lịch nhiệm vụ có độ chính xác đến mili-giây. Với delayed retry, cần chấp nhận sai số và đặc điểm queue; hệ thống cần lịch chính xác nên cân nhắc scheduler hoặc cơ chế delayed delivery phù hợp.

### 4.3. TTL được áp dụng theo queue, không phải một “số tuổi chung” của event

Nếu cùng một event được exchange fanout tới **queue A** (TTL 2 giây) và **queue B** (không TTL), bản message ở A có thể **expired** trong khi bản ở B vẫn được xử lý bình thường. X-death ghi **queue nguồn bị dead-letter**, không có nghĩa event ở mọi queue đều đã hết hạn.

### 4.4. Queue TTL x-expires là trường hợp khác

| Cấu hình | Đối tượng bị hết hạn | Dead-letter message khi hết hạn? |
| --- | --- | --- |
| **x-message-ttl**, **message-ttl** | **Message** trong queue | **Có thể**, reason **expired** nếu DLX hợp lệ |
| AMQP **expiration** | **Message** cụ thể | **Có thể**, reason **expired** |
| **x-expires**, policy **expires** | **Bản thân queue** sau thời gian không được sử dụng | **Không**; khi queue bị xóa, các message trong đó không được dead-letter chỉ vì queue hết hạn |

Đây là một lỗi nhận thức thường gặp: cấu hình **QueueBuilder.expires(...)** không tương đương **QueueBuilder.ttl(...)**. Nếu bạn định dùng queue chờ để chuyển tiếp message sau một khoảng trì hoãn, cấu hình **message TTL**, không phải **queue expiration**.

### 4.5. Dead-lettering và expiration property

RabbitMQ có thể ghi **original-expiration** trong **x-death** để giữ thông tin TTL gốc của message, đồng thời loại bỏ property **expiration** khi republish qua DLX để tránh message hết hạn lại ngay lập tức ở queue đích chỉ vì TTL cũ. Do đó khi điều tra cần xem **x-death** thay vì chỉ xem expiration còn lại trên message trong DLQ.

## 5. Nguyên nhân 3 — maxlen: queue vượt giới hạn độ dài

RabbitMQ cho phép giới hạn số message trong queue bằng **max-length**, hoặc tổng số bytes body bằng **max-length-bytes**. Khi đạt giới hạn và có message mới, **overflow strategy** quyết định message nào bị loại hoặc bị từ chối.

### 5.1. Giới hạn ở queue hoặc policy

| Cấu hình | Mục đích | Lưu ý |
| --- | --- | --- |
| **x-max-length** / policy **max-length** | Số message tối đa theo điều kiện queue | Classic queue tính message Ready; quorum có những khoản mục khác ngoài Ready |
| **x-max-length-bytes** / policy **max-length-bytes** | Giới hạn tổng bytes của message body | Không bao gồm mọi overhead/properties |
| **x-overflow** / policy **overflow** | Cách broker xử lý khi đầy | **drop-head**, **reject-publish**, hoặc **reject-publish-dlx** tùy loại queue |

Ví dụ một **classic queue** giới hạn hai message, cho phép broker loại message ở đầu queue khi message thứ ba vào:

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;

Queue limited = QueueBuilder.durable("lab.dead.maxlen")
        .withArgument("x-max-length", 2)
        .withArgument("x-overflow", "drop-head")
        .deadLetterExchange("lab.dead.dlx")
        .deadLetterRoutingKey("dead.any")
        .build();
~~~

Nếu không có consumer đang lấy message và queue rỗng ban đầu:

~~~text
Publish M1 -> queue: [M1]
Publish M2 -> queue: [M1, M2]
Publish M3 -> queue: [M2, M3]

M1 bị đẩy khỏi đầu queue.
M1 được republish tới DLX (nếu cấu hình hợp lệ).
x-death reason = maxlen
~~~

**Nhớ phân biệt:** trong kịch bản này, **M1** bị dead-letter do queue đầy, **không phải M3**. Điều này ảnh hưởng trực tiếp đến cách bạn điều tra eventId trong DLQ.

### 5.2. Overflow strategy thay đổi kết quả

| Overflow | Message nào chịu tác động? | Publisher confirm / DLX |
| --- | --- | --- |
| **drop-head** (thường mặc định) | Message **cũ nhất ở đầu queue** bị đẩy ra khi cần | Message cũ có thể dead-letter reason **maxlen** nếu DLX hợp lệ |
| **reject-publish** | **Message mới** bị queue từ chối khi đã đầy | Nếu bật publisher confirms, broker có thể trả **basic.nack** cho publish bị từ chối; không tự dead-letter bản mới |
| **reject-publish-dlx** | Message mới bị từ chối và được đưa qua DLX | Hỗ trợ theo loại queue/phiên bản; **không được dùng với quorum queue hiện đại** |

**Cảnh báo theo loại queue:** theo tài liệu RabbitMQ hiện hành, quorum queue hỗ trợ queue length limit nhưng **không hỗ trợ overflow reject-publish-dlx**. Nếu cần quorum dead-letter an toàn, hãy thiết kế overflow policy phù hợp (thường là **reject-publish** cho at-least-once dead-lettering).

### 5.3. Không nhầm giới hạn queue với số message chưa ACK

Trong **classic queue**, chỉ message **Ready** được tính cho giới hạn độ dài; **Unacked** không được tính. Quorum queue còn tính thêm các nhóm message liên quan đến delayed retry hoặc at-least-once dead-lettering; **Unacked** cũng không được tính như Ready.

Vì vậy, một queue có thể có **2 Ready, 20 Unacked** dù max-length=2. Đừng dùng max-length để thay cho việc đặt **prefetch**, số consumer hoặc bảo vệ tài nguyên ứng dụng.

### 5.4. Max length không phải retry count

Reason **maxlen** nói rằng queue vượt **giới hạn dung lượng**, không nói message đã xử lý thất bại bao nhiêu lần. Một message có thể chưa từng được consumer nhìn thấy mà vẫn bị dead-letter vì maxlen.

Nếu backlog thường xuyên chạm maxlen, cần điều tra tốc độ publish, throughput consumer, prefetch, CPU, DB/API và chính sách lưu trữ. DLQ chỉ **di chuyển lượng backlog bị đẩy ra**, không tự giải quyết nút thắt.

## 6. Nguyên nhân 4 — delivery_limit: quorum queue vượt ngưỡng giao thất bại

**Quorum queue** dùng bộ đếm để phát hiện message bị xử lý thất bại và giao lại quá nhiều lần (poison message). Khi số lần thất bại được tính vượt **delivery limit**, broker có thể **loại message** hoặc **dead-letter** nó với reason **delivery_limit** nếu đã cấu hình DLX.

**Chỉ quorum queue có nguyên nhân này.** Classic queue không có cùng cơ chế delivery-limit tích hợp và không tạo x-death reason delivery_limit chỉ vì một message được reject/requeue nhiều lần.

### 6.1. Cấu hình giới hạn

Trong RabbitMQ **4.0 trở lên**, quorum queue có **delivery limit mặc định 20**. Có thể điều chỉnh bằng policy **delivery-limit** hoặc queue argument **x-delivery-limit**. Ví dụ Spring AMQP:

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;

Queue quorumSource = QueueBuilder.durable("lab.dead.quorum")
        .quorum()
        .deliveryLimit(3)
        .deadLetterExchange("lab.dead.dlx")
        .deadLetterRoutingKey("dead.any")
        .build();
~~~

**deliveryLimit(3)** dùng ngưỡng thấp để làm lab; môi trường production cần chọn dựa trên số liệu và policy. Đặt **-1** sẽ tắt delivery limit trong một số cấu hình nhưng **không được khuyến nghị**, vì message lỗi có thể quay vòng vô hạn.

Đặc biệt, policy **delivery-limit** có thể thay đổi hiệu lực trên quorum queue đang tồn tại theo phiên bản; tham số queue argument cố định yêu cầu quản lý khai báo cẩn thận. Ưu tiên **policy** khi vận hành hạ tầng lâu dài.

### 6.2. RabbitMQ 4.3 thay đổi cách đếm thất bại

Đây là điểm rất quan trọng khi tích hợp Spring AMQP:

| Hành động trên message của quorum queue | RabbitMQ 4.2 trở về trước | RabbitMQ 4.3+ |
| --- | --- | --- |
| **basic.nack(tag, false, true)** | Có thể tăng bộ đếm dẫn đến delivery limit | **Không** tăng bộ đếm **delivery-count** dùng cho limit |
| **basic.reject(tag, true)** | Giao lại và có thể tính vào limit | **Có**, được tính là lần giao thất bại |
| **Consumer crash/connection đóng khi còn Unacked** | Có thể làm tăng bộ đếm | **Có** |
| **basic.reject(tag, false)** | Dead-letter ngay với reason **rejected** nếu có DLX | **Vẫn là rejected**, không cần chờ delivery limit |
| **basic.ack(tag, false)** | Thành công; kết thúc delivery | Thành công; không vào DLX |

RabbitMQ 4.3 tách **x-acquired-count** (số lần message được cấp cho consumer) khỏi **x-delivery-count** (số lần giao thất bại được tính). Ở 4.3+, **basic.nack(requeue=true)** có thể requeue liên tục mà **không đi đến delivery_limit**. Vì vậy **không dựa độc nhất vào delivery limit để chặn hot loop** khi sử dụng Spring listener hoặc custom Channel code gửi NACK.

> Cần đối chiếu **đúng phiên bản RabbitMQ của môi trường chạy**: thay đổi này ảnh hưởng trực tiếp kịch bản kiểm thử poison message, cảnh báo và chính sách xử lý lỗi khi nâng cấp từ RabbitMQ 4.2 lên 4.3+.

### 6.3. Thử nghiệm an toàn với basic.reject(tag, true)

Ví dụ một listener **MANUAL** cố ý reject và requeue message trên quorum queue, để quan sát delivery limit ở RabbitMQ hiện đại:

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
public class QuorumDeliveryLimitLabListener {

    @RabbitListener(
            queues = "lab.dead.quorum",
            ackMode = "MANUAL")
    public void failIntentionally(
            String payload,
            Channel channel,
            @Header(AmqpHeaders.DELIVERY_TAG) long deliveryTag)
            throws IOException {
        // CHỈ DÙNG TRONG LAB: coi mọi lần delivery đều thất bại.
        channel.basicReject(deliveryTag, true);
    }
}
~~~

Với queue **quorum** và limit thấp như 3, sau các lần giao thất bại được broker tính, message được chuyển sang DLX với **x-death reason=delivery_limit**. Kết quả có thể phụ thuộc phiên bản và những lần giao/requeue cụ thể; tránh khẳng định số lần chính xác từ log method thay vì quan sát counter của broker.

**Không dùng listener này trong production:** nó cố tình tạo vòng giao lại rất nhanh. Hãy thử ở broker lab riêng, có DLQ, limit thấp và dừng consumer sau khi xác nhận kết quả. Với lỗi tạm thời thực tế, dùng **retry có backoff và giới hạn** ở application hoặc cơ chế delayed retry phù hợp.

### 6.4. Quan sát x-delivery-count và x-acquired-count

Khi broker gửi lại một message qua quorum queue, có thể có các header:

- **x-delivery-count**: các lần giao được tính là thất bại; ngữ nghĩa phụ thuộc phiên bản (đặc biệt từ 4.3).
- **x-acquired-count**: thông tin số lần message được cấp cho consumer, có từ RabbitMQ 4.3, **không nhất thiết chứng minh handler đã chạy**.

Những header này **khác x-death**:

- **x-delivery-count** giúp quan sát vòng **redelivery trong quorum queue**.
- **x-death** xuất hiện khi message **thật sự được dead-letter** ra khỏi queue.
- Bộ đếm **x-death.count** là số lần dead-letter cho cặp **(queue, reason)**, không phải số lần handler đã thử.

Nếu một message chạm delivery limit nhưng **không có DLX**, nó có thể bị loại khỏi queue; không được giả định sẽ có DLQ để truy vết.

## 7. Thực hành Spring AMQP: một DLX cho bốn nguyên nhân

Ta sẽ tạo **bốn queue nguồn riêng** để tránh một cấu hình ảnh hưởng phép thử khác, nhưng cùng route dead-letter về **một DLQ**:

~~~mermaid
flowchart LR
    PUB["RabbitTemplate"] --> W{"lab.dead.work<br/>Direct exchange"}
    W -->|"case.reject"| RJ[("lab.dead.reject")]
    W -->|"case.ttl"| TTL[("lab.dead.ttl<br/>message TTL=2s")]
    W -->|"case.maxlen"| ML[("lab.dead.maxlen<br/>max-length=2")]
    W -->|"case.quorum"| QQ[("lab.dead.quorum<br/>quorum, delivery-limit=3")]
    RJ -->|"rejected"| D{"lab.dead.dlx"}
    TTL -->|"expired"| D
    ML -->|"maxlen"| D
    QQ -->|"delivery_limit"| D
    D -->|"dead.any"| DLQ[("lab.dead.audit")]
~~~

**Các ví dụ được thiết kế cho Java 17, Spring Boot 3.x và Spring AMQP 3.x**. RabbitMQ 4.x (đặc biệt 4.3+) được dùng để giải thích delivery limit. Nếu dự án chạy Boot 4.x hoặc RabbitMQ đời khác, cần xem API và ngữ nghĩa đúng phiên bản trước khi dùng làm hướng dẫn triển khai.

### 7.1. Dependency và kết nối

Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-amqp")
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Địa chỉ broker trong **application.yml**:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: app
    password: local_dev_password
    virtual-host: /
    listener:
      simple:
        acknowledge-mode: auto
        prefetch: 1

lab:
  case: none
  reject-listener: false
  quorum-listener: false
  dlq-listener: false
~~~

Các thông tin kết nối chỉ là **giá trị mẫu trong môi trường lab**, không phải credential có sẵn trên mọi broker. Production nên lấy secret từ môi trường an toàn và chỉ cấp quyền cần thiết.

Giá trị **lab.case** xác định thử nghiệm sẽ publish lúc khởi động; giá trị mặc định **none** bảo đảm ứng dụng không tự tạo message lỗi ngoài ý muốn. Các cờ **lab.*-listener** bật/tắt consumer thí nghiệm tương ứng.

### 7.2. Khai báo topology đầy đủ

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableRabbit
public class DeadLetterCausesTopology {
    public static final String EXCHANGE = "lab.dead.work";
    public static final String DLX = "lab.dead.dlx";
    public static final String DEAD_KEY = "dead.any";
    public static final String AUDIT_QUEUE = "lab.dead.audit";

    public static final String REJECT_QUEUE = "lab.dead.reject";
    public static final String TTL_QUEUE = "lab.dead.ttl";
    public static final String MAXLEN_QUEUE = "lab.dead.maxlen";
    public static final String QUORUM_QUEUE = "lab.dead.quorum";

    @Bean
    DirectExchange workExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    DirectExchange deadExchange() {
        return new DirectExchange(DLX, true, false);
    }

    @Bean("rejectQueue")
    Queue rejectQueue() {
        return QueueBuilder.durable(REJECT_QUEUE)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DEAD_KEY)
                .build();
    }

    @Bean("ttlQueue")
    Queue ttlQueue() {
        return QueueBuilder.durable(TTL_QUEUE)
                .ttl(2000)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DEAD_KEY)
                .build();
    }

    @Bean("maxlenQueue")
    Queue maxlenQueue() {
        return QueueBuilder.durable(MAXLEN_QUEUE)
                .withArgument("x-max-length", 2)
                .withArgument("x-overflow", "drop-head")
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DEAD_KEY)
                .build();
    }

    @Bean("quorumQueue")
    Queue quorumQueue() {
        return QueueBuilder.durable(QUORUM_QUEUE)
                .quorum()
                .deliveryLimit(3)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DEAD_KEY)
                .build();
    }

    @Bean("auditQueue")
    Queue auditQueue() {
        return QueueBuilder.durable(AUDIT_QUEUE).build();
    }

    @Bean
    Binding rejectBinding(
            @Qualifier("rejectQueue") Queue queue,
            @Qualifier("workExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange).with("case.reject");
    }

    @Bean
    Binding ttlBinding(
            @Qualifier("ttlQueue") Queue queue,
            @Qualifier("workExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange).with("case.ttl");
    }

    @Bean
    Binding maxlenBinding(
            @Qualifier("maxlenQueue") Queue queue,
            @Qualifier("workExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange).with("case.maxlen");
    }

    @Bean
    Binding quorumBinding(
            @Qualifier("quorumQueue") Queue queue,
            @Qualifier("workExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange).with("case.quorum");
    }

    @Bean
    Binding deadBinding(
            @Qualifier("auditQueue") Queue queue,
            @Qualifier("deadExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue)
                .to(exchange).with(DEAD_KEY);
    }
}
~~~

Đây là **topology dành cho thí nghiệm**, nên dùng **queue names riêng biệt trên broker lab**. Trong production, RabbitMQ khuyến nghị cấu hình DLX/TTL/max-length/delivery-limit bằng **policy** khi có thể, thay vì hardcode x-arguments. Đổi argument của queue đã tồn tại thường gây **PRECONDITION_FAILED** nếu khai báo lại không tương đương; muốn đổi loại queue **classic → quorum** không thể đơn giản sửa một chuỗi trong @Bean khi queue cũ còn dữ liệu.

Với Spring Boot bật RabbitAdmin auto-configuration mặc định và tài khoản đủ quyền, các bean Queue/Exchange/Binding có thể được khai báo khi ứng dụng kết nối. Nếu tài nguyên được hạ tầng quản lý, phải kiểm tra topology đã tồn tại và tắt/tùy chỉnh auto-declare một cách có chủ đích.

### 7.3. Hai listener lỗi được bật bằng cờ lab

Listener tạo **rejected** ở queue classic. Tại đây dùng exception của Spring để tránh thao tác Channel thủ công:

~~~java
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        prefix = "lab",
        name = "reject-listener",
        havingValue = "true")
public class LabRejectListener {

    @RabbitListener(queues = DeadLetterCausesTopology.REJECT_QUEUE)
    public void reject(String payload) {
        throw new AmqpRejectAndDontRequeueException(
                "Lab: permanent failure -> rejected");
    }
}
~~~

Listener thử **quorum delivery limit** dùng **basic.reject(tag,true)** với manual ack:

~~~java
import com.rabbitmq.client.Channel;
import java.io.IOException;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        prefix = "lab",
        name = "quorum-listener",
        havingValue = "true")
public class LabQuorumFailureListener {

    @RabbitListener(
            queues = DeadLetterCausesTopology.QUORUM_QUEUE,
            ackMode = "MANUAL")
    public void rejectAndRequeue(
            String payload,
            Channel channel,
            @Header(AmqpHeaders.DELIVERY_TAG) long deliveryTag)
            throws IOException {
        // Chỉ thử với quorum queue nhỏ và giới hạn thấp ở broker lab.
        channel.basicReject(deliveryTag, true);
    }
}
~~~

**Chỉ bật consumer đúng với thí nghiệm đang chạy.** Với TTL và maxlen, **không khai báo @RabbitListener** cho hai queue đó: nếu chúng bị tiêu thụ ngay, message có thể không chờ đủ lâu để hết TTL hoặc không tồn tại đủ nhiều để chạm max-length.

### 7.4. Publisher chọn test case theo cấu hình

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class LabDeadLetterSender {

    @Bean
    ApplicationRunner sendTestMessages(
            RabbitTemplate template,
            Environment env) {
        return args -> {
            String testCase =
                    env.getProperty("lab.case", "none");

            switch (testCase) {
                case "reject" -> template.convertAndSend(
                        DeadLetterCausesTopology.EXCHANGE,
                        "case.reject",
                        "bad-order-event");

                case "ttl" -> template.convertAndSend(
                        DeadLetterCausesTopology.EXCHANGE,
                        "case.ttl",
                        "event-waiting-too-long");

                case "maxlen" -> {
                    for (int i = 1; i <= 3; i++) {
                        template.convertAndSend(
                                DeadLetterCausesTopology.EXCHANGE,
                                "case.maxlen",
                                "maxlen-" + i);
                    }
                }

                case "quorum" -> template.convertAndSend(
                        DeadLetterCausesTopology.EXCHANGE,
                        "case.quorum",
                        "poison-quorum-message");

                case "none" -> { /* Không tự publish */ }
                default -> throw new IllegalArgumentException(
                        "Unknown lab.case: " + testCase);
            }
        };
    }
}
~~~

Để tránh biến một buổi lab thành một đợt publish trùng vô tình, sau mỗi lần chạy hãy trả **lab.case: none**. Runner chỉ phát message; nó không tự bảo đảm publisher confirm, do đó khi cần kết quả chắc chắn hơn phải bật **publisher-confirm-type: correlated**, publisher returns/mandatory và theo dõi xác nhận tại lớp gửi.

### 7.5. Xem reason trong message thuộc DLQ

Có thể bật consumer kiểm tra DLQ khi sẵn sàng lấy message khỏi queue. Consumer này **mặc định tắt** để bạn còn xem Ready và properties trên RabbitMQ Management:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
        prefix = "lab",
        name = "dlq-listener",
        havingValue = "true")
public class LabDeadLetterInspector {

    @RabbitListener(queues = DeadLetterCausesTopology.AUDIT_QUEUE)
    public void inspect(Message message) {
        var properties = message.getMessageProperties();
        List<Map<String, ?>> history =
                properties.getXDeathHeader();

        System.out.println(
                "body=" + new String(
                        message.getBody(), StandardCharsets.UTF_8));
        System.out.println("messageId=" + properties.getMessageId());

        if (history == null || history.isEmpty()) {
            System.out.println("No x-death history");
            return;
        }

        Map<String, ?> mostRecent = history.get(0);
        System.out.println("deadFromQueue=" + mostRecent.get("queue"));
        System.out.println("reason=" + mostRecent.get("reason"));
        System.out.println("deathCount=" + mostRecent.get("count"));
    }
}
~~~

**getXDeathHeader()** là API của Spring AMQP **MessageProperties** trong dòng framework minh họa. Với nhiều lần dead-letter, danh sách có thể chứa nhiều bản ghi; ví dụ chỉ đọc **bản ghi gần đây nhất**. Trong AUTO ACK, inspector sẽ xác nhận message sau khi method thành công, vì vậy kiểm tra queue trong Management **trước khi** bật inspector nếu muốn giữ message để quan sát thủ công.

Ở production, không log toàn bộ body, token hoặc dữ liệu cá nhân chỉ vì message nằm trong DLQ. Đọc metadata ở mức cần thiết, lưu audit an toàn, và tách quyền truy cập vào dead-letter payload.

## 8. Cấu hình bằng policy thay vì hardcode queue arguments

Các ví dụ **QueueBuilder** ở phần 7 cố tình ghi trực tiếp arguments để một bài lab tự chứa, dễ dựng và dễ kiểm chứng. Tuy nhiên, với RabbitMQ vận hành dài hạn, **policy** thường phù hợp hơn:

- Policy có thể áp dụng **nhiều queue theo tên pattern**.
- Có thể cập nhật **DLX, message TTL, max length, overflow** (và một số quorum delivery-limit settings) mà không sửa code khai báo mọi queue.
- Giúp vận hành chuẩn hóa việc quản lý số lượng queue lớn và giảm rủi ro hardcode topology ở nhiều service.

Một bộ định nghĩa policy minh họa:

~~~json
{
  "name": "orders-source-dlx",
  "pattern": "^orders\\.(normal|priority)$",
  "apply-to": "queues",
  "priority": 5,
  "definition": {
    "dead-letter-exchange": "orders.dead.exchange",
    "dead-letter-routing-key": "orders.failed"
  }
}
~~~

Đây là **payload tham khảo** cho một policy qua Management HTTP API/CLI, không phải file cấu hình ứng dụng Spring Boot. Cần tạo **orders.dead.exchange** và binding đến dead-letter queue riêng trên **cùng vhost**. Pattern chỉ nên trúng **queue nguồn muốn quản lý**, tránh áp policy DLX lên cả queue DLQ ngoài ý định.

### Policy và x-arguments ưu tiên theo cách nào?

Nếu cả policy và arguments khai báo từ client đều đặt cùng một thuộc tính DLX, **x-argument từ client có ưu tiên** hơn policy. Với **message TTL** và **max-length**, cơ chế lấy giá trị hiệu lực còn phụ thuộc nhóm setting/policy/operator policy (thường giới hạn chặt hơn được áp dụng). Không nên đưa ra quy tắc “mọi key luôn do policy thắng” cho toàn bộ RabbitMQ.

Trước khi thử policy, hãy **không** khai báo những argument tương ứng hardcode trên queue lab đã tồn tại, hoặc tạo queue thử riêng được quản lý hoàn toàn bằng policy. Kiểm tra **effective policy + arguments** trong RabbitMQ Management → Queues.

### Lưu ý quyền và trạng thái queue

Khai báo DLX cần exchange có tên đúng trong cùng vhost, người dùng có quyền phù hợp với queue nguồn và DLX. **Tên DLX có trong x-arguments không chứng minh exchange đã tồn tại**; nếu đến thời điểm dead-letter mà exchange không tồn tại, message có thể bị mất theo chiến lược dead-lettering.

Khi queue đã tồn tại và có message, **không xóa queue** chỉ để thay đổi x-arguments mà chưa có kế hoạch bảo toàn dữ liệu. Với queue quan trọng, ưu tiên policy có thể đổi động và quy trình migration đã thử trên staging.

## 9. Đọc x-death: vì sao message thực sự rời queue?

Khi RabbitMQ dead-letter một message trong AMQP 0-9-1, broker bổ sung/cập nhật header **x-death**. Mỗi entry ghi thông tin về lần dead-letter tương ứng và được gộp theo **cặp queue + reason** để không tăng kích thước vô hạn.

Một giá trị x-death minh họa về mặt ý nghĩa:

~~~json
[
  {
    "queue": "lab.dead.reject",
    "reason": "rejected",
    "count": 1,
    "exchange": "lab.dead.work",
    "routing-keys": ["case.reject"]
  }
]
~~~

**Lưu ý:** JSON trên **chỉ minh họa cách đọc**, không phải cấu trúc JSON chính xác do AMQP Java client trả về. Trong thực tế, x-death là một **AMQP field-array** chứa bảng, timestamp và các kiểu dữ liệu của AMQP; trong Spring AMQP nó có thể được ánh xạ thành **List<Map<String, ?>>**. Đừng copy định dạng JSON này rồi giả định broker lưu JSON.

| Trường | Ý nghĩa | Lưu ý khi phân tích |
| --- | --- | --- |
| **queue** | Queue nguồn đã dead-letter message | Không phải queue đích hiện tại |
| **reason** | **rejected, expired, maxlen, delivery_limit** | Dùng để phân loại nguyên nhân thật |
| **count** | Số lần dead-letter theo cặp **queue + reason** | **Không** đồng nghĩa số lần consumer retry |
| **time** | Thời điểm lần đầu ghi nhận cặp queue/reason ở AMQP 0-9-1 theo tài liệu hiện hành | Không phải lúc publisher tạo event |
| **exchange** | Exchange message từng được publish vào trước khi dead-letter tại queue đó | Không nhất thiết là DLX đích |
| **routing-keys** | Các routing key trước lần dead-letter tương ứng | Có thể khác routing key broker dùng để vào DLQ |
| **original-expiration** | TTL message gốc nếu có | Có thể xuất hiện do broker bỏ expiration property khi dead-letter |

Broker còn cung cấp những metadata như **x-first-death-queue**, **x-first-death-reason**, **x-last-death-queue**, **x-last-death-reason** trong các phiên bản hiện hành để giúp xác định sự kiện dead-letter đầu tiên/gần nhất.

### Một message có thể có nhiều x-death reasons

Ví dụ một flow retry bằng TTL:

~~~text
1) main.queue:
     handler reject requeue=false
     -> x-death(reason=rejected, queue=main.queue)

2) retry.wait.queue:
     message sống quá TTL
     -> x-death(reason=expired, queue=retry.wait.queue)

3) main.queue:
     handler vẫn lỗi và reject lần nữa
     -> tăng count cho (main.queue, rejected)
~~~

Lúc này message có thể có nhiều entry x-death; phần tử **gần đây nhất** thường đứng đầu, nhưng **count** của từng entry là tổng số lần dead-letter theo cặp tương ứng, **không phải toàn bộ số lần message được deliver**.

**Đừng đọc x-death như một biến đếm retry vô hạn do ứng dụng tùy ý sửa.** Broker quản lý metadata này, có thể gộp/sắp xếp lại theo đặc tả; nếu cần retry policy chính xác cho nghiệp vụ, lưu **eventId ổn định** và trạng thái/counter rõ ràng của ứng dụng. Spring AMQP cũng có các cơ chế retry interceptor và recoverer phù hợp.

## 10. Kịch bản thực hành cho từng reason

Trước khi chạy, xác nhận ứng dụng kết nối được broker lab, RabbitAdmin đã khai báo đủ các tài nguyên và DLQ **lab.dead.audit** đang trống hoặc bạn đã ghi nhận trạng thái ban đầu.

### 10.1. Thử rejected

Đặt:

~~~yaml
lab:
  case: reject
  reject-listener: true
  quorum-listener: false
  dlq-listener: false
~~~

Khởi động một instance ứng dụng. Runner gửi **bad-order-event** vào queue reject. Listener **LabRejectListener** ném **AmqpRejectAndDontRequeueException**, yêu cầu container không requeue.

Kết quả mong đợi:

~~~text
Queue nguồn: lab.dead.reject
DLX:        lab.dead.dlx
DLQ:        lab.dead.audit
x-death:
  queue  = lab.dead.reject
  reason = rejected
~~~

Nếu muốn thử phiên bản manual, tắt **LabRejectListener** và dùng **ManualRejectListener** phần 3.2 thay thế; phải bảo đảm chỉ một consumer tham gia phép thử. Không nên chạy đồng thời hai lựa chọn trên queue này.

### 10.2. Thử expired

Đặt:

~~~yaml
lab:
  case: ttl
  reject-listener: false
  quorum-listener: false
  dlq-listener: false
~~~

Runner gửi **event-waiting-too-long** vào **lab.dead.ttl**. **Không có consumer** trên queue TTL. Sau khoảng TTL 2 giây và khi broker thực thi việc loại expired message, message sẽ đi tới DLX.

Kết quả mong đợi:

~~~text
Queue nguồn: lab.dead.ttl
TTL:        2000 ms
DLQ:        lab.dead.audit
x-death:
  queue  = lab.dead.ttl
  reason = expired
~~~

**Không kiểm tra bằng đồng hồ tuyệt đối 2.000 ms.** RabbitMQ có thể xử lý hết hạn khi message ở đầu queue hoặc tại thời điểm nội bộ phù hợp. Nếu chạy lại lab mà queue đã chứa backlog cũ, kết quả có thể bị ảnh hưởng; hãy dùng queue riêng sạch hoặc quan sát messageId để xác định message bạn vừa gửi.

### 10.3. Thử maxlen

Đặt:

~~~yaml
lab:
  case: maxlen
  reject-listener: false
  quorum-listener: false
  dlq-listener: false
~~~

Runner gửi lần lượt **maxlen-1, maxlen-2, maxlen-3** vào queue classic giới hạn **2 Ready messages** với overflow **drop-head**; không có consumer queue nguồn.

Kết quả khi queue ban đầu rỗng:

~~~text
lab.dead.maxlen:
  Ready: maxlen-2, maxlen-3

lab.dead.audit:
  Message: maxlen-1
  x-death queue  = lab.dead.maxlen
  x-death reason = maxlen
~~~

Đây là phép thử đáng chú ý vì **message cũ** bị dead-letter, không phải message mới nhất. Nếu trong lab có consumer lấy message hoặc broker đã có các message cũ, số lượng/định danh sẽ khác. Kiểm tra cả **Queue Arguments → x-overflow** trước khi kết luận.

### 10.4. Thử delivery_limit

Đặt:

~~~yaml
lab:
  case: quorum
  reject-listener: false
  quorum-listener: true
  dlq-listener: false
~~~

Runner gửi **poison-quorum-message** vào quorum queue. **LabQuorumFailureListener** dùng **basicReject(tag,true)** để broker có cơ sở ghi nhận những lần giao thất bại. Sau khi vượt ngưỡng được định nghĩa cho quorum queue, message được dead-letter:

~~~text
Queue nguồn: lab.dead.quorum
Queue type:  quorum
Limit:       3 (lab)
DLQ:         lab.dead.audit
x-death:
  queue  = lab.dead.quorum
  reason = delivery_limit
~~~

**Nhất thiết kiểm tra phiên bản RabbitMQ.** Với RabbitMQ 4.3+, dùng **basic.nack(requeue=true)** thay thế có thể làm message quay vòng **mà không tăng x-delivery-count**, dẫn đến phép thử không đạt delivery_limit. **Không dùng cách này để thử trên cluster production** hoặc queue dùng chung, vì vòng requeue tạo tải nóng.

### 10.5. Đọc kết quả an toàn

Ban đầu hãy giữ **lab.dlq-listener=false**. Trong RabbitMQ Management:

1. Mở **Queues → lab.dead.audit**.
2. Xem **Messages Ready** sau mỗi thí nghiệm.
3. Chọn thao tác **Get messages** với chế độ cho phép **requeue** nếu muốn kiểm tra mà không xóa message; hiểu rõ thao tác này cũng là một lần giao message.
4. Đọc **message properties và x-death header** để xác minh **reason** và **queue**.
5. Khi đã sẵn sàng xử lý/lấy message khỏi DLQ, bật **lab.dlq-listener=true** để dùng **LabDeadLetterInspector**. Sau khi listener ACK, message sẽ không còn ở DLQ.

**Không để cùng lúc bốn case được publish không kiểm soát** rồi dựa vào vị trí dòng đầu trong queue để đoán loại lỗi. Dùng eventId/messageId riêng hoặc payload có prefix test rõ ràng để truy vết.

## 11. Dead-lettering có an toàn khi broker hoặc DLQ lỗi không?

**Một message đã rời queue nguồn không đồng nghĩa nó đã tồn tại bền vững trong DLQ.** RabbitMQ phải republish nó vào DLX và các queue đích. Trong một số chiến lược dead-lettering mặc định, thao tác chuyển này có thể **không dùng publisher confirms** để đảm bảo đích chấp nhận.

### 11.1. At-most-once là rủi ro cần nhìn thấy

Một số tình huống cần kiểm thử trên staging:

- DLX chưa tồn tại hoặc bị xóa.
- DLX tồn tại nhưng không có binding khớp routing key của dead-letter.
- Queue đích bị xóa hoặc đang không sẵn sàng.
- Queue đích đầy và cấu hình overflow từ chối publish.
- Node RabbitMQ hoặc kết nối giữa các node gặp sự cố trong lúc dead-letter.

Nếu nguồn sử dụng cơ chế **at-most-once dead-lettering**, có thể không có bản message an toàn tại đích. Vì vậy **DLX không phải một giao dịch nguyên tử bảo toàn message trong mọi trường hợp**.

### 11.2. Quorum queue và at-least-once dead-lettering

Quorum queue có khả năng bật **at-least-once dead-lettering** để nâng độ an toàn khi chuyển message sang đích. Cơ chế nội bộ giữ message nguồn cho tới khi những queue đích xác nhận theo logic của nó. Tuy nhiên điều đó đòi hỏi **chính sách thích hợp**, không chỉ có DLX.

Theo tài liệu RabbitMQ, những điều kiện cần lưu ý gồm:

1. **dead-letter-strategy=at-least-once**.
2. **overflow=reject-publish**, không phải drop-head.
3. **dead-letter-exchange** phải được cấu hình.
4. Đáp ứng các yêu cầu feature flag/phiên bản RabbitMQ đang chạy nếu có.
5. Cân nhắc giới hạn độ dài queue nguồn và giám sát tình trạng message dead-letter đang chờ đích.

**At-least-once có thể gây duplicate ở DLQ** nếu một lần chuyển được thử lại sau trạng thái chưa rõ. Vì vậy inspector hoặc consumer xử lý DLQ vẫn cần idempotency theo **eventId** và đối soát trạng thái nghiệp vụ.

Một lỗi cấu hình nguy hiểm là bật chiến lược at-least-once nhưng dùng **drop-head** ở source quorum: các điều kiện đảm bảo có thể không còn được đáp ứng và cơ chế có thể quay về at-most-once. Đọc **effective policy** thay vì chỉ nhìn tham số khai báo queue.

### 11.3. Dead-letter cycle

Khi DLX/binding của một queue lại route message về chính queue ban đầu hoặc qua một vòng các queue, có thể tạo **dead-letter cycle**:

~~~mermaid
flowchart LR
    A[("source.queue")] -->|"expired / rejected"| E{"DLX"}
    E --> B[("retry.queue")]
    B -->|"TTL expired"| RE{"retry exchange"}
    RE --> A
~~~

Đôi khi chu trình này là **thiết kế retry có delay**. Nhưng nếu không có điều kiện dừng, message có thể quay vòng không giới hạn, tăng tải và x-death count. RabbitMQ có cơ chế phát hiện một số chu trình dead-letter và loại message trong trường hợp thích hợp (chẳng hạn vòng không có consumer rejection), nhưng **không nên dựa vào cơ chế đó thay cho giới hạn retry của ứng dụng**.

## 12. DLX, TTL và delayed retry: liên quan nhưng không giống nhau

Bài học thuộc chương **Dead-letter và trì hoãn**, nên cần phân biệt:

| Cơ chế | Được kích hoạt bằng | Mục đích điển hình |
| --- | --- | --- |
| **Reject → DLX** | Consumer quyết định không requeue | Cách ly message lỗi |
| **Message TTL → DLX** | Hết thời gian lưu trong queue | Hết hạn message hoặc chờ rồi chuyển queue |
| **Max length → DLX** | Queue đạt giới hạn | Bảo vệ dung lượng và xử lý message bị đẩy ra |
| **Quorum delivery limit → DLX** | Quá nhiều lần giao thất bại được tính | Chặn một số poison-message loop |
| **Retry queue TTL + DLX quay về queue chính** | Logic chủ động đưa message vào queue chờ, hết TTL rồi republish | Retry có trì hoãn bằng topology |
| **Delayed message mechanism khác** | Plugin hoặc cơ chế delayed retry theo phiên bản broker | Trì hoãn giao nhận theo kế hoạch |

### 12.1. Ví dụ retry queue bằng TTL

~~~mermaid
flowchart LR
    MAIN[("orders.main")] -->|"Consumer xử lý thất bại<br/>quyết định retry"| WAIT[("orders.retry.wait<br/>TTL=30s")]
    WAIT -->|"expired"| DLX{"retry.return.exchange"}
    DLX -->|"routing key tới main"| MAIN
    MAIN -->|"Hết số lần thử"| PARK[("orders.parking.dlq")]
~~~

**Điểm cần phân biệt:** trong sơ đồ này, **TTL của retry queue** tạo dead-letter reason **expired** khi message quay về main. Nhưng **lý do nghiệp vụ ban đầu** vẫn là consumer gặp lỗi tạm thời. Nếu cần biết toàn bộ lịch sử, phải đọc x-death/metadata và lưu retry policy ở ứng dụng.

Một topology TTL queue có giới hạn:

- Queue **orders.retry.wait** có **message-ttl=30000** và DLX trở về main exchange/routing key.
- Consumer xử lý lỗi đưa message từ main sang retry queue theo cách có kiểm soát; không đơn giản **basic.nack(requeue=true)** rồi mong có delay.
- Sau khi message vào retry queue và hết TTL, broker republish qua DLX về main.
- Khi số lần thử vượt ngưỡng hoặc lỗi vĩnh viễn, route tới **parking DLQ** để điều tra thay vì quay lại vô tận.

**Lưu ý:** TTL không bảo đảm lịch chính xác từng mili-giây, và message có thể bị chặn sau các message có TTL khác. Với RabbitMQ hiện đại, quorum queue còn có cơ chế delayed retry riêng; cần chọn thiết kế theo phiên bản, yêu cầu ordering và SLA. Không gộp tất cả các mô hình thành một “delay queue” duy nhất mà không kiểm chứng.

### 12.2. Không dùng x-death.count làm bằng chứng đã chạy business N lần

Trong chu trình retry qua queue TTL, **x-death.reason=expired** ở retry queue ghi số lần hết TTL của message tại **queue đó**. Nó không nhất thiết bằng số lần method business xử lý, ví dụ nếu message đã bị crash sau delivery hoặc được đưa vào queue chờ mà chưa chạy handler thật.

Để ra quyết định nghiệp vụ đáng tin cậy, có thể dùng:

- **eventId** ổn định để nhận diện cùng một sự kiện.
- Một **attempt counter** do ứng dụng kiểm soát hoặc một trạng thái retry lưu bền.
- Cơ chế retry bounded/backoff với số lần tối đa rõ ràng.
- DLQ/parking queue cho message cần can thiệp thủ công.
- Idempotency trong consumer và hệ thống đích để tránh tác dụng phụ lặp.

## 13. Theo dõi reason và sức khỏe DLQ

**RabbitMQ Management** giúp xem tình trạng queue, bindings, policies và một số message metadata. Khi nhiều queue nguồn cùng chia sẻ DLQ, đừng chỉ theo dõi một con số tổng; phải phân biệt lý do và queue phát sinh.

| Chỉ số/câu hỏi | Đọc ở đâu? | Ý nghĩa |
| --- | --- | --- |
| Queue nguồn **Ready/Unacked** | Queues/CLI | Có backlog hoặc tác vụ đang xử lý chưa ACK? |
| DLQ **Ready** | Queue DLQ | Có bao nhiêu message đang chờ xử lý lỗi? |
| **x-death.reason** | Header message trong DLQ | Bị rejected, expired, maxlen hay delivery_limit? |
| **x-death.queue** | Header message | Queue nào chịu trách nhiệm dead-letter? |
| **x-death.count** | Header message | Số lần dead-letter theo queue/reason; không phải số business retry |
| **x-delivery-count** của quorum | Header message ở lần giao lại | Số lần thất bại broker tính, phụ thuộc RabbitMQ version |
| **Policy/Arguments** | Queue detail, policy view | DLX, TTL, max-length, overflow, delivery-limit hiệu lực ra sao? |
| **Consumer count, ACK/redelivery rate** | Management/metrics | Consumer có đang xử lý/lặp lỗi liên tục không? |
| **Publisher confirm/return** | Spring RabbitTemplate và broker metrics | Có message bị mất trước khi vào queue nguồn vì routing không? |

Nếu RabbitMQ chạy qua Docker Compose với service tên **rabbitmq**, có thể đọc:

~~~bash
docker compose exec rabbitmq rabbitmqctl list_queues -p / name type arguments policy messages_ready messages_unacknowledged consumers
docker compose exec rabbitmq rabbitmqctl list_exchanges -p / name type
docker compose exec rabbitmq rabbitmqctl list_bindings -p /
~~~

Tên cột/định dạng có thể khác giữa các bản RabbitMQ; khi CLI không nhận một cột, kiểm tra **rabbitmqctl help list_queues** rồi điều chỉnh. Với người dùng Windows, các lệnh trên chạy qua **docker compose exec** trong container broker; không phụ thuộc cú pháp quote JSON của PowerShell.

### Một sự cố DLQ cần báo động thế nào?

Ví dụ nhóm metric:

- **DLQ backlog** tăng bất thường ở một service.
- Tần suất **x-death.reason=rejected** tăng: nghi ngờ schema/validation hoặc nghiệp vụ không đáp ứng.
- Tần suất **expired** tăng: TTL quá thấp, consumer chậm hoặc retry wait queue hoạt động nhiều.
- Tần suất **maxlen** tăng: queue chạm giới hạn, backlog nặng hoặc overflow policy không phù hợp.
- Tần suất **delivery_limit** tăng: quorum queue có poison message, consumer crash/reject nhiều hoặc chính sách retry sai.

Đừng tạo metric label là **eventId duy nhất của từng message**; điều đó gây cardinality lớn. Nên dùng **queue, reason, service, eventType** làm dimension hữu hạn. EventId dùng trong log/tracing có kiểm soát dữ liệu.

## 14. Khắc phục lỗi và những ngộ nhận

| Triệu chứng | Vì sao xảy ra | Cách xử lý |
| --- | --- | --- |
| Consumer ném exception nhưng message cứ quay lại | Container mặc định requeue lỗi thường | Dùng AmqpRejectAndDontRequeueException hoặc policy defaultRequeueRejected có chủ đích; DLX |
| Gọi basicNack(requeue=true) mà không thấy DLQ | Requeue chưa phải dead-letter | Dùng reject không requeue cho lỗi permanent, retry bounded cho lỗi transient |
| DLQ không có message dù queue nguồn đã hết TTL | DLX thiếu, binding sai, message chưa được xử lý expiration vật lý | Kiểm tra policy/arguments, DLX và thời điểm tới đầu queue |
| Message hết TTL nhưng vẫn thấy trong thống kê queue | Head-of-line blocking của TTL hoặc sự kiện xử lý chưa đến | Kiểm tra loại queue và thời điểm expiry; không xem TTL như cron |
| Xóa queue có x-expires nhưng không thấy x-death | Queue expiration không dead-letter các message bên trong | Dùng message TTL khi cần expiry → DLX |
| Max-length=2, message thứ ba không nằm trong DLQ | drop-head loại **message cũ nhất**, không phải message mới | Kiểm tra overflow strategy; xem M1 thay vì M3 |
| Queue đầy, publisher nhận NACK | Overflow reject-publish từ chối message mới | Đọc publisher confirms, tăng throughput hoặc điều chỉnh policy |
| Delivery limit trên classic queue không kích hoạt | Chỉ quorum hỗ trợ lý do delivery_limit | Dùng quorum hoặc retry/limit ở application |
| RabbitMQ 4.3+, basic.nack(true) lặp mãi không tới limit | NACK requeue không tăng delivery-count dùng cho limit | Hiểu 4.3, dùng retry có giới hạn; với lab thử basic.reject(true) |
| Quorum bị vượt limit mà không thấy DLQ | Chưa cấu hình DLX hoặc DLX/đích lỗi | Cấu hình DLX, kiểm tra policy/permissions và dead-letter strategy |
| x-death.count khác số lần handler chạy | Count là các lần dead-letter theo queue/reason | Theo dõi attempt ở ứng dụng và x-delivery-count phù hợp |
| x-death có nhiều lý do khác nhau | Message đã qua nhiều queue/chu kỳ dead-letter | Đọc toàn bộ danh sách và first/last death metadata |
| Xóa và khai báo lại queue bị PRECONDITION_FAILED | Arguments/type không tương đương với queue đang tồn tại | Kiểm tra migration/policy; không xóa message vô tình |
| Một message tự quay lại queue gốc rất nhiều lần | Dead-letter cycle hoặc retry wait queue không có giới hạn | Thêm retry budget, parking queue và giám sát |
| DLQ có message trùng | Retry/dead-lettering at-least-once, publisher gửi lại hoặc replay | Idempotent DLQ processor, eventId bền |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Nêu bốn giá trị **x-death.reason** chính của RabbitMQ AMQP 0-9-1 và sự kiện kích hoạt từng giá trị.

**Câu 2.** Listener Spring AMQP đang AUTO ACK, phát sinh IllegalArgumentException thông thường và defaultRequeueRejected=true. Message có chắc chắn vào DLQ không?

**Câu 3.** Khác biệt giữa **basicReject(tag,false)** và **basicReject(tag,true)** là gì? Trường hợp nào tạo reason rejected?

**Câu 4.** Một queue có **x-message-ttl=2000** và **x-expires=60000**. Message vượt 2 giây có thể trở thành reason gì? Khi cả queue tự hết hạn vì không dùng, message trong queue có được dead-letter không?

**Câu 5.** Classic queue giới hạn **max-length=2**, overflow drop-head, chưa có consumer. Gửi M1, M2, M3. Message nào vào DLQ?

**Câu 6.** Nếu overflow đổi thành **reject-publish**, có thể dựa vào việc M1 luôn vào DLQ với reason maxlen nữa không?

**Câu 7.** Delivery limit hoạt động trên **classic** hay **quorum** queue? Giá trị mặc định được giới thiệu từ RabbitMQ 4.0 là bao nhiêu?

**Câu 8.** Tại sao khi nâng RabbitMQ từ 4.2 lên 4.3, consumer dùng **basic.nack(requeue=true)** có thể không còn chạm delivery limit?

**Câu 9.** Trong một retry queue TTL, message có x-death reason expired. Điều đó chứng minh handler đã chạy và thất bại đúng một lần không?

**Câu 10.** Bật at-least-once dead-lettering của quorum queue có đồng nghĩa hoàn toàn không tạo duplicate ở DLQ không? Cần thêm điều kiện gì cho overflow?

**Đáp án:**

1. **rejected** khi reject/nack không requeue; **expired** khi message TTL hết; **maxlen** khi queue vượt giới hạn độ dài và message bị loại; **delivery_limit** khi quorum vượt ngưỡng giao thất bại được tính.
2. **Không.** Lỗi thông thường có thể bị requeue; cần điều khiển exception/error policy và có DLX hợp lệ.
3. **false**: reject không requeue, có thể dead-letter reason **rejected**. **true**: trả message vào queue để giao lại, không có rejected ngay.
4. Message có thể dead-letter reason **expired**. Queue tự bị xóa do x-expires **không** dead-letter các message trong nó.
5. **M1** bị loại từ đầu queue và có thể vào DLQ với reason **maxlen**.
6. **Không.** reject-publish từ chối message **mới**, khác drop-head; có thể tạo publisher NACK.
7. **Quorum queue**, mặc định **20** từ RabbitMQ 4.0.
8. Từ 4.3, NACK requeue không làm tăng **delivery-count** dùng cho delivery limit.
9. **Không.** Expired chỉ mô tả thời gian message ở queue chờ; count không phải số handler attempt.
10. **Không.** At-least-once có thể tạo duplicate khi retry chuyển DLQ; cần policy **overflow=reject-publish** và các điều kiện dead-lettering khác.

## 16. Checklist trước khi đưa DLX vào production

1. **Xác định nguyên nhân**: message bị rejected, expired, maxlen hay delivery_limit? Không gọi mọi lỗi là “retry exceeded”.
2. **Đặt đúng topology**: queue nguồn → DLX → binding → DLQ trên cùng vhost; kiểm tra quyền và trạng thái broker.
3. **Chọn policy thay vì hardcode** khi cần cập nhật runtime; đối chiếu precedence với queue arguments.
4. **Phân loại lỗi consumer**: lỗi vĩnh viễn đi DLQ; lỗi tạm thời dùng retry có giới hạn và backoff.
5. **Phân biệt TTL**: message TTL khác x-expires của queue; đừng coi TTL là timer chính xác tuyệt đối.
6. **Kiểm soát overflow**: drop-head loại cũ, reject-publish từ chối mới; đánh giá nguy cơ mất dữ liệu và publisher NACK.
7. **Xem phiên bản RabbitMQ** khi dùng quorum delivery limit, đặc biệt thay đổi cách đếm basic.nack từ 4.3.
8. **Chọn chiến lược an toàn** nếu dead-letter là dữ liệu không được phép mất; kiểm tra điều kiện at-least-once của quorum.
9. **Không tạo dead-letter cycle vô hạn** hoặc hot-loop requeue; dùng parking queue và retry budget rõ ràng.
10. **Giữ eventId ổn định**, dùng idempotency ở consumer và lúc replay DLQ.
11. **Quan sát x-death.queue/reason/count** nhưng không nhầm count với số lần nghiệp vụ retry.
12. **Đo Ready/Unacked, redelivery và DLQ backlog**, đặt cảnh báo theo queue/reason và làm sạch message sau điều tra có kiểm soát.
13. **Thử nghiệm lỗi thật trên staging**: sai schema, hết TTL, queue đầy, quorum vượt limit, DLX không tồn tại, restart consumer.
14. **Phân quyền và bảo mật**: DLQ có thể giữ message chứa dữ liệu nhạy cảm; kiểm soát retention, logging, quyền đọc và quy trình replay.

**Kết luận:** RabbitMQ có bốn nguyên nhân dead-letter rõ ràng: **rejected, expired, maxlen, delivery_limit**. Hai nguyên nhân đầu liên quan đến **quyết định từ chối của consumer** và **tuổi message**, hai nguyên nhân còn lại liên quan đến **sức chứa queue** và **giới hạn giao thất bại trên quorum queue**. Với Spring AMQP, hãy phối hợp **RabbitTemplate, @RabbitListener, ACK/NACK, queue/exchange/binding, DLX/DLQ, TTL, overflow, retry có giới hạn, idempotency và giám sát**. Khi biết chính xác *vì sao* message dead-letter, bạn mới có thể chọn cách sửa lỗi thay vì chỉ chuyển backlog sang một queue khác.

### Tài liệu tham khảo

- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)
- [RabbitMQ — Time-To-Live and Expiration](https://www.rabbitmq.com/docs/ttl)
- [RabbitMQ — Queue Length Limit](https://www.rabbitmq.com/docs/maxlength)
- [RabbitMQ — Quorum Queues và Delivery Limit](https://www.rabbitmq.com/docs/quorum-queues)
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [Spring AMQP — Error Handling and Broker Failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html)
- [Spring AMQP — QueueBuilder API](https://docs.spring.io/spring-amqp/docs/3.1.x/api/org/springframework/amqp/core/QueueBuilder.html)
- [Spring AMQP — MessageProperties API](https://docs.spring.io/spring-amqp/docs/3.1.x/api/org/springframework/amqp/core/MessageProperties.html)
