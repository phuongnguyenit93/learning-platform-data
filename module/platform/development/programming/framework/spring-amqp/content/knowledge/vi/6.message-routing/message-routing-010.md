# Đối chiếu định tuyến đúng, không định tuyến được và exchange không tồn tại

Trong một ứng dụng tích hợp RabbitMQ bằng **Spring AMQP**, việc gọi `RabbitTemplate.convertAndSend(...)` không tự chứng minh message đã tới đúng queue, càng không có nghĩa `@RabbitListener` đã xử lý thành công. Message có thể được **định tuyến đúng**, được publish vào exchange **nhưng không có queue nào khớp**, hoặc được gửi đến **exchange không tồn tại**. Ba trường hợp này có cơ chế và tín hiệu lỗi rất khác nhau.

Bài học thuộc chương **Định tuyến thông điệp** của module **SPRING_AMQP**. Việc phân biệt chính xác ba kết quả publish là nền tảng để thiết kế exchange, queue, binding, `RabbitTemplate`, `@RabbitListener`, publisher confirms/returns, retry, dead-letter, giao dịch và giám sát hệ thống bất đồng bộ đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **publish**, **route**, **enqueue**, **deliver**, **acknowledge** và **hoàn tất xử lý nghiệp vụ**.
- Dự đoán kết quả khi exchange tồn tại có hoặc không có binding khớp, và khi exchange không tồn tại.
- Hiểu ý nghĩa của `mandatory`, `basic.return`, publisher confirm (`basic.ack`/`basic.nack`) và lỗi `404 NOT_FOUND` đóng channel.
- Bật và quan sát publisher confirms/returns trong Spring AMQP; không kết luận sai từ callback `ack=true`.
- Thiết kế phép thử và quy trình chẩn đoán lỗi routing, bao gồm alternate exchange, default exchange và dead-letter.

## 2. Đường đi của một message

~~~mermaid
flowchart LR
    P["Producer<br/>RabbitTemplate"] -->|"basic.publish<br/>exchange + routing key"| E["Exchange"]
    E -->|"Có binding khớp"| Q["Queue"]
    Q -->|"Delivery"| C["Consumer<br/>@RabbitListener"]
    E -->|"Không có đường đến queue"| U["Unroutable"]
    P -.->|"Exchange không tồn tại"| X["Channel error<br/>404 NOT_FOUND"]
~~~

Khi gọi:

~~~java
rabbitTemplate.convertAndSend(
        "orders.events",
        "order.created",
        "{\"orderId\":\"O-1001\"}"
);
~~~

hai chuỗi đầu tiên có vai trò riêng:

| Tham số | Giá trị ví dụ | Broker dùng để làm gì? |
|---|---|---|
| **Exchange** | `orders.events` | Tìm exchange đích trong đúng virtual host |
| **Routing key** | `order.created` | So khớp binding theo loại exchange |
| **Message body** | JSON chứa `orderId` | Dữ liệu được chuyển vào queue; broker không tự phân tích JSON để route bằng direct/topic exchange |

Một exchange phải tồn tại trước khi broker có thể định tuyến thông qua nó. Nếu exchange tồn tại, routing phụ thuộc **loại exchange, các binding và routing key/headers**. Nếu route khớp, message được đưa tới queue; sau đó mới có bước broker giao message cho consumer.

Các trạng thái cần tách biệt:

1. **Published:** producer đã thực hiện thao tác gửi trên kết nối/client; có thể chưa biết broker xử lý ra sao.
2. **Accepted/confirmed:** publisher nhận kết quả xử lý publish từ broker qua confirm (nếu bật).
3. **Routed/enqueued:** ít nhất một queue đã được chọn làm đích và broker xử lý việc enqueue theo đặc tính queue.
4. **Delivered:** broker chuyển một delivery cho consumer.
5. **Consumer acknowledged:** consumer/container gửi acknowledgement đối với delivery.
6. **Business completed:** logic nghiệp vụ thật sự đã hoàn tất theo hợp đồng của ứng dụng, có thể còn gồm commit database hoặc gọi hệ thống ngoài.

Các bước này **không tương đương**. Ví dụ, một message được route vào queue nhưng chưa có consumer vẫn thuộc trường hợp định tuyến đúng; một callback publisher confirm `ack=true` cũng không chứng minh nghiệp vụ đã chạy.

## 3. Bảng đối chiếu ba trường hợp bắt buộc

Giả sử broker không cấu hình alternate exchange cho exchange đang thử, và queue không áp dụng chính sách loại bỏ tức thời. Với `mandatory` và publisher confirms được cấu hình đúng:

| Tình huống publish | Broker nhìn thấy gì? | `basic.return` khi `mandatory=true` | Publisher confirm | Kết quả về queue |
|---|---|---|---|---|
| **A. Exchange tồn tại, routing khớp** | Exchange tìm được ít nhất một queue theo binding | Không trả về do thiếu route | Thường `ack` khi broker đã xử lý publish | Message được định tuyến tới queue phù hợp |
| **B. Exchange tồn tại, không có route** | Không tìm được queue đích | `basic.return`, thường mã `312 NO_ROUTE` | Vẫn có thể `ack` vì exchange đã xử lý publish | Không queue nào nhận message theo route đó |
| **C. Exchange không tồn tại** | Không tìm thấy exchange được chỉ định | **Không** phải trường hợp `NO_ROUTE`; không có return thông thường | Không dựa vào confirm bình thường để nhận dạng; channel bị lỗi/đóng | Message không được định tuyến bởi exchange đó |

Hai biến thể quan trọng của **B**:

- **`mandatory=false` (thường là mặc định khi chưa cấu hình):** broker có thể bỏ message không có route mà **không gửi basic.return**; nếu có publisher confirms, publish đó vẫn có thể được `ack`.
- **`mandatory=true`:** nếu cuối cùng không có queue phù hợp, broker có thể gửi `basic.return` để trả message về publisher. Để Spring AMQP quan sát được return, cần bật publisher returns và đăng ký callback hoặc dùng cơ chế trả kết quả tương ứng.

**C không phải là “unroutable do binding sai”.** Publish tới exchange không tồn tại là lỗi giao thức cấp **channel**; RabbitMQ thường phản hồi `channel.close` với mã `404 NOT_FOUND`. Đây không phải tín hiệu `basic.return` với `312 NO_ROUTE`.

> **Quy tắc xử lý:** `ack=true` của publisher confirm không đồng nghĩa message đã đến queue mục tiêu. Muốn phát hiện không định tuyến được, cần xem **publisher return**; muốn phát hiện exchange không tồn tại, cần xem **lỗi channel/exception/log** và trạng thái publisher confirm liên quan.

## 4. Trường hợp A — Định tuyến đúng

Định nghĩa topology:

~~~text
Exchange: orders.events
Type:     direct
Queue:    orders.created.q
Binding:  orders.events --[order.created]--> orders.created.q

Publish:
  exchange   = orders.events
  routingKey = order.created
  body       = {"orderId":"O-1001"}
~~~

Với **direct exchange**, binding key `order.created` khớp chính xác routing key `order.created`. Exchange có thể route message đến `orders.created.q`. Nếu có nhiều queue cùng binding key, broker có thể định tuyến một bản đến **mỗi queue phù hợp**. Nếu một queue có nhiều binding cùng khớp một message, queue đó không vì thế nhận nhiều bản của cùng một publish chỉ do các binding trùng.

~~~mermaid
flowchart TD
    P["basic.publish<br/>orders.events / order.created"] --> E["Direct exchange<br/>orders.events"]
    E -->|"Binding order.created"| Q1["orders.created.q"]
    E -->|"Nếu có binding trùng key<br/>trên queue khác"| Q2["orders.audit.q"]
~~~

Điều kiện “định tuyến đúng” là **exchange có đường đến queue đích phù hợp**, không phải ngay lập tức `@RabbitListener` chạy. Có thể xảy ra:

- Listener chưa khởi động nên message nằm trong queue.
- Listener đang bận, có prefetch hoặc consumer chưa xác nhận message.
- Queue áp dụng TTL, maximum length hoặc overflow policy khiến message bị hết hạn/loại bỏ về sau; routing ban đầu vẫn có thể đúng.
- Consumer nhận message rồi exception, requeue hoặc dead-letter. Lúc này vấn đề thuộc **xử lý delivery**, không phải tìm binding.

**Tín hiệu quan sát:** không có `basic.return` do `NO_ROUTE`; publisher confirm thường `ack=true` nếu broker xử lý publish thành công. Để xác minh đích cụ thể, kiểm tra binding và queue hoặc gắn message ID/correlation ID rồi đối chiếu nhận thực tế.

## 5. Trường hợp B — Exchange tồn tại nhưng không định tuyến được

Giả sử queue vẫn chỉ có binding key `order.created`, nhưng producer publish:

~~~java
rabbitTemplate.convertAndSend(
        "orders.events",
        "order.cancelled",
        "{\"orderId\":\"O-1001\"}"
);
~~~

Routing key `order.cancelled` **không khớp** binding `order.created` của direct exchange. Khi không có queue nào khác khớp và không có alternate exchange route được message, đây là tình huống **unroutable**.

### 5.1. mandatory=false

Với `mandatory=false`, RabbitMQ có thể loại message không định tuyến được mà không trả payload về publisher. Producer gọi `send` xong không có exception đồng bộ rõ ràng, và publisher confirm có thể vẫn `ack=true`. Vì vậy một hệ thống chỉ kiểm tra exception hoặc chỉ log confirm `ack=true` **có thể bỏ sót mất message do sai routing key**.

### 5.2. mandatory=true

Với `mandatory=true` và publisher returns được cấu hình, broker trả lại message bằng `basic.return`. Tín hiệu thường thấy:

~~~text
Reply code: 312
Reply text: NO_ROUTE
Exchange:   orders.events
Routing key: order.cancelled
Returned body: {"orderId":"O-1001"}
~~~

Code `312 NO_ROUTE` nói rằng broker không tìm được route phù hợp; không chứng minh exchange bị thiếu. Cần ghi cả exchange, routing key, message ID/correlation ID và thông tin retry để chẩn đoán.

Với publisher confirms, `basic.return` và `basic.ack` có thể xuất hiện cho **cùng một publish**: broker trả lại vì không route được nhưng vẫn `ack` việc đã xử lý publish. Do đó, **return và confirm mang hai ý nghĩa độc lập**. RabbitMQ phát tín hiệu return trước publisher confirm tương ứng; phía ứng dụng nên tương quan hai kết quả theo message/correlation ID thay vì xem callback theo thứ tự thời gian là đủ.

### 5.3. Vì sao không tự retry liên tục cùng routing key?

Nếu message thất bại vì typo `order.cancelled` hoặc thiếu binding, gửi lại với **cùng exchange và routing key, trên cùng topology** sẽ tiếp tục thất bại. Hãy xử lý nguyên nhân:

1. Xác nhận exchange, virtual host và loại exchange.
2. Kiểm tra binding key/arguments thực tế.
3. Quyết định cần sửa routing key, tạo binding đúng hay chuyển message sang kênh xử lý sự cố.
4. Chỉ retry sau khi đã có bằng chứng điều kiện định tuyến thay đổi hoặc có chiến lược retry có giới hạn.

**Quan trọng:** Dead-letter exchange (DLX) của **queue** không tự thu gom message chưa từng được route vào queue. Nếu message bị loại ngay tại exchange vì thiếu route, nó không trải qua cơ chế dead-letter của queue.

## 6. Trường hợp C — Publish đến exchange không tồn tại

Giả sử broker **không có** exchange `orders.missing` trong virtual host của kết nối:

~~~java
rabbitTemplate.convertAndSend(
        "orders.missing",
        "order.created",
        "{\"orderId\":\"O-1001\"}"
);
~~~

RabbitMQ không thể áp dụng direct/topic/fanout/header routing vì tên exchange **không trỏ tới tài nguyên có thật**. Với AMQP 0-9-1, publish vào exchange không tồn tại gây lỗi cấp channel, thường mang nội dung tương tự:

~~~text
reply-code=404
reply-text=NOT_FOUND - no exchange 'orders.missing' in vhost '/'
class-id=60, method-id=40
~~~

`class-id=60, method-id=40` tương ứng thao tác `basic.publish` của AMQP 0-9-1. Dòng lỗi minh họa có thể thay đổi theo bản RabbitMQ/client và virtual host thực tế.

Tác động:

- Broker đóng **channel** phát sinh lỗi; kết nối TCP không nhất thiết bị đóng theo.
- Thao tác publish có thể sinh exception trong ứng dụng hoặc lỗi được quan sát qua callback/log do phản hồi đóng channel đến **bất đồng bộ**. Không giả định mọi lần `convertAndSend` đều ném exception đồng bộ ngay tại dòng gọi.
- Channel đã bị đóng không còn dùng được; client/framework có thể tạo channel mới cho lần gửi tiếp theo, nhưng việc khôi phục channel **không sửa** tên exchange sai.
- Message publish đó không được route; đừng diễn giải sự kiện thành `312 NO_ROUTE`.

Nếu có publisher confirms, lỗi channel có thể ảnh hưởng các confirm còn chờ. Cần xử lý **trạng thái publish thất bại/không chắc chắn**, lỗi channel và khả năng gửi lại có kiểm soát; đừng coi việc không thấy return là bằng chứng thành công.

### So sánh hai mã hay bị nhầm

| Mã | Điều kiện điển hình | Phạm vi lỗi | Ý nghĩa xử lý |
|---|---|---|---|
| **312 NO_ROUTE** | Exchange có thật, message không đến queue nào, `mandatory=true` | `basic.return` của publish | Kiểm tra binding/routing key và đường đi thay thế |
| **404 NOT_FOUND** | Publish tới exchange không tồn tại trong virtual host | Lỗi giao thức dẫn đến đóng channel | Kiểm tra khai báo exchange, virtual host, thứ tự khởi tạo và quyền/configuration |

Mã 404 cũng có thể xuất hiện ở những thao tác AMQP khác khi tài nguyên không tồn tại; luôn đọc **operation và log cụ thể** trước khi kết luận lỗi xuất phát từ `basic.publish`.

## 7. Thực hành Spring AMQP: khai báo topology tối thiểu

Ví dụ sau sử dụng **Spring Boot với spring-boot-starter-amqp**, broker RabbitMQ hoạt động và cấu hình kết nối phù hợp. Ta tạo một direct exchange, một durable queue và một binding để chủ động tạo cả ba tình huống.

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RoutingTopology {

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange("orders.events", true, false);
    }

    @Bean
    Queue ordersCreatedQueue() {
        return QueueBuilder.durable("orders.created.q").build();
    }

    @Bean
    Binding ordersCreatedBinding(DirectExchange ordersExchange,
                                 Queue ordersCreatedQueue) {
        return BindingBuilder.bind(ordersCreatedQueue)
                .to(ordersExchange)
                .with("order.created");
    }
}
~~~

Một `RabbitAdmin` được cấu hình phù hợp có thể khai báo các bean exchange, queue và binding khi ứng dụng kết nối RabbitMQ. Spring Boot thường hỗ trợ auto-configuration cho trường hợp cơ bản, nhưng cần xác minh có `AmqpAdmin` và quyền khai báo trên đúng virtual host.

Để phép thử C hợp lệ, **không** khai báo `orders.missing` ở bất cứ đâu trong môi trường test. Các tên trong ví dụ chỉ dành cho môi trường thực hành, tránh vô tình dùng tên trùng tài nguyên production.

### 7.1. Bật publisher confirms và publisher returns

Với các phiên bản Spring Boot hỗ trợ những property dưới đây, cấu hình ví dụ:

~~~properties
spring.rabbitmq.publisher-confirm-type=correlated
spring.rabbitmq.publisher-returns=true
spring.rabbitmq.template.mandatory=true
~~~

- `publisher-confirm-type=correlated`: cho phép theo dõi confirm của publish thông qua correlation data/callback khi connection factory được cấu hình tương ứng.
- `publisher-returns=true`: bật nhận các message trả về từ broker.
- `template.mandatory=true`: yêu cầu return message nếu không được định tuyến đến queue theo điều kiện AMQP; có ý nghĩa khi kiểm tra trường hợp B.

Tên property và khả năng hỗ trợ phụ thuộc **phiên bản Spring Boot** đang dùng. Hãy đọc cấu hình được hỗ trợ bởi đúng phiên bản ứng dụng. Nếu tự tạo `ConnectionFactory` hoặc `RabbitTemplate`, cần đảm bảo các tùy chọn tương ứng thực sự được áp dụng, tránh tưởng đã bật theo properties nhưng bean tùy chỉnh không nhận cấu hình.

### 7.2. Cấu hình callbacks tập trung cho RabbitTemplate

Ví dụ dưới đây tạo một template riêng với `mandatory=true` và callbacks cho publisher; connection factory do Spring Boot cung cấp phải được bật publisher confirms/returns như mục 7.1.

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RoutingPublisherConfiguration {

    @Bean
    RabbitTemplate rabbitTemplate(ConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMandatory(true);

        template.setReturnsCallback(returned -> {
            String body = new String(
                    returned.getMessage().getBody(),
                    StandardCharsets.UTF_8
            );
            System.err.printf(
                    "RETURN code=%d reason=%s exchange=%s key=%s body=%s%n",
                    returned.getReplyCode(),
                    returned.getReplyText(),
                    returned.getExchange(),
                    returned.getRoutingKey(),
                    body
            );
        });

        template.setConfirmCallback((correlationData, ack, cause) -> {
            String id = correlationData == null
                    ? "unknown" : correlationData.getId();
            System.out.printf(
                    "CONFIRM id=%s ack=%s cause=%s%n",
                    id, ack, cause
            );
        });

        return template;
    }
}
~~~

Trong ví dụ:

- `ReturnsCallback` nhận thông tin do `basic.return` cung cấp. Đó là nguồn chứng cứ cho trường hợp message không có route khi `mandatory=true`.
- `ConfirmCallback` xử lý publisher confirm; `ack` phản ánh việc broker xác nhận publish theo cơ chế confirm, **không** phản ánh việc consumer xử lý thành công hay chắc chắn có queue nhận message.
- `RabbitTemplate` chỉ hỗ trợ một returns callback và một confirm callback chính cho template; hãy tổ chức đăng ký callbacks tại chỗ quản lý template để tránh component khác ghi đè.
- In body ra log chỉ nhằm quan sát ở ví dụ thực hành; ứng dụng thực tế nên giới hạn thông tin nhạy cảm, kích thước payload và gắn các ID phù hợp.

Khi tự khai báo `RabbitTemplate` bean, bạn đang tự chịu trách nhiệm các cấu hình template tùy chỉnh như converter, retry template và message post-processors nếu ứng dụng cần chúng. Các lựa chọn liên quan publisher confirms/returns vẫn phải được áp dụng trên connection factory. Không dùng bean thứ hai có cùng mục đích mà không xác định template nào producer thực sự sử dụng.

### 7.3. Gửi ba message có correlation ID

~~~java
import java.util.UUID;

import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class RoutingPublisher {
    private final RabbitTemplate rabbitTemplate;

    public RoutingPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public String publish(String exchange, String routingKey, String body) {
        String id = UUID.randomUUID().toString();
        CorrelationData correlation = new CorrelationData(id);
        rabbitTemplate.convertAndSend(
                exchange, routingKey, body, correlation
        );
        return id;
    }
}
~~~

Gọi lần lượt ba phép thử trên môi trường test:

~~~java
// A: Exchange có thật, routing khớp một queue.
String routedId = publisher.publish(
        "orders.events", "order.created", "OrderCreated:O-1001"
);

// B: Exchange có thật nhưng không có binding nào khớp.
String unroutableId = publisher.publish(
        "orders.events", "order.cancelled", "OrderCancelled:O-1001"
);

// C: Exchange chưa hề được khai báo.
String missingExchangeId = publisher.publish(
        "orders.missing", "order.created", "OrderCreated:O-1001"
);
~~~

Ba lời gọi minh họa các tình huống độc lập. Trong thực tế, cuộc gọi C có thể ném exception hoặc xuất hiện lỗi channel bất đồng bộ; **không** để phép thử C làm mất khả năng quan sát của A/B. Chạy riêng từng phép thử nếu cần và quan sát logs/callbacks tương ứng.

Để phân tích ở cấp từng message trong chương trình thực tế, thay vì chỉ in logs theo thời điểm, có thể dùng `CorrelationData` và cơ chế chờ confirm/returned result được Spring AMQP hỗ trợ ở phiên bản đang dùng. Cần thiết kế timeout, trạng thái không rõ kết quả và xử lý lỗi một cách tường minh.

## 8. Dự đoán và xác minh kết quả của từng phép thử

Giả sử `orders.events` là direct exchange, **chỉ** có một binding `order.created` tới `orders.created.q`, không có alternate exchange và các cấu hình đã được áp dụng:

| Phép thử | ReturnsCallback | ConfirmCallback | Broker/queue |
|---|---|---|---|
| **A. `orders.events` + `order.created`** | Không có `NO_ROUTE` | Thường `ack=true` | Queue nhận message, trừ các yếu tố lưu trữ/chính sách khác |
| **B. `orders.events` + `order.cancelled`** | `312 NO_ROUTE` với mandatory | Có thể `ack=true` | Không queue nào được route bởi exchange đó |
| **C. `orders.missing` + `order.created`** | Không có `312 NO_ROUTE` thông thường | Không được giả định có confirm thành công | Log/exception báo `404 NOT_FOUND`; channel đóng |

**Cách thử tái lập:** chỉ khai báo topology của mục 7, tạm dừng mọi listener đọc `orders.created.q` hoặc tạo một queue riêng để kiểm tra; ghi lại lượng message trước và sau publish A. Với B, quan sát return của publisher. Với C, xem log client/channel error của chính thao tác publish. Nếu listener đang chạy, queue depth có thể về 0 ngay do consumer đã nhận message, nên queue rỗng **không đủ chứng minh** routing thất bại.

Trong RabbitMQ Management UI, kiểm tra đúng virtual host và các tab **Exchanges**, **Queues**, **Bindings**. Khi kiểm tra từ ứng dụng, gắn correlation ID ở publisher và message ID/header quan sát để so sánh các bước publish, enqueue, delivery và business log.

### Khi muốn kết luận “consumer đã xử lý”

Callback publisher không đủ. Cần quan sát listener nhận message, kết quả xử lý nghiệp vụ và acknowledgement theo cơ chế cấu hình. Đối với hệ thống cập nhật database, bằng chứng hữu ích có thể là transaction đã commit và idempotency key đã lưu. Nếu consumer nhận rồi lỗi, redelivery hoặc DLQ có thể xảy ra sau khi routing ban đầu đã thành công.

## 9. Mandatory, publisher returns, confirms và consumer ack

Đây là bốn cơ chế khác nhau:

| Cơ chế | Bên nào phát tín hiệu? | Trả lời câu hỏi nào? | Không chứng minh được |
|---|---|---|---|
| **mandatory flag** | Producer đặt trong lệnh publish | “Nếu cuối cùng không route được thì broker có cần trả message lại không?” | Message đã route thành công |
| **basic.return** | Broker gửi về publisher | “Message không có queue nhận theo điều kiện mandatory” | Exchange không tồn tại hoặc consumer lỗi |
| **Publisher confirm ack/nack** | Broker gửi về publisher trên confirm channel | “Broker xử lý publish theo cơ chế confirm ra sao?” | Có consumer nhận và xử lý nghiệp vụ thành công |
| **Consumer basic.ack/nack/reject** | Consumer gửi về broker | “Delivery này được xử lý/xác nhận hay yêu cầu xử lý tiếp ra sao?” | Producer đã biết kết quả nghiệp vụ |

Publisher confirm `nack` thường chỉ xuất hiện trong tình huống broker không thể xử lý publish vì lý do nội bộ. **Không dùng `nack` làm tín hiệu chuẩn cho NO_ROUTE**; một message được trả bằng `basic.return` vẫn có thể có publisher confirm `ack`.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant E as RabbitMQ Exchange
    participant Q as Queue
    P->>E: basic.publish (mandatory=true)
    alt Route khớp
        E->>Q: Enqueue message
        E-->>P: Publisher confirm ack (khi xử lý thành công)
    else Không có route
        E-->>P: basic.return (312 NO_ROUTE)
        E-->>P: Publisher confirm ack có thể vẫn xảy ra
    else Exchange không tồn tại
        E-->>P: channel.close (404 NOT_FOUND)
    end
~~~

Các callback xảy ra bất đồng bộ, vì vậy log từ nhiều lần publish có thể xen kẽ. Với publish số lượng lớn, cần nhận diện chính xác message/correlation data để không nhầm return của message B với confirm của message A.

## 10. Các biến thể ảnh hưởng kết luận

### 10.1. Alternate exchange có thể cứu một message không khớp binding chính

RabbitMQ hỗ trợ **alternate exchange (AE)**: nếu exchange chính không route được message, broker có thể chuyển message sang alternate exchange được cấu hình cho nó. Ví dụ:

~~~text
orders.events (direct)
  binding: order.created -> orders.created.q
  alternate-exchange: unrouted.events

unrouted.events (fanout)
  binding -> orders.unrouted.q
~~~

Khi publish `order.cancelled` vào `orders.events`, binding chính không khớp nhưng alternate exchange có thể chuyển message tới `orders.unrouted.q`. Nếu cuối cùng có queue nhận, đây **không còn là tình huống không được định tuyến đến bất kỳ queue nào**. Tùy tuyến AE và cấu hình, publisher có thể **không** nhận return, dù message không đến queue nghiệp vụ ban đầu.

Vì vậy, `không có basic.return` không chứng minh message tới **queue dự kiến**; nó chỉ cho biết broker không thông báo một trường hợp return theo cấu hình quan sát. Luôn kiểm tra alternate exchange nếu message biến mất khỏi queue mong đợi.

Nếu alternate exchange cũng không route được đến queue nào và message được publish với `mandatory=true`, cần xem chính sách và đường routing cuối cùng để hiểu kết quả return. Khi có AE, không nên dùng ma trận A/B giản lược để kết luận mà không biết topology.

### 10.2. Default exchange luôn có sẵn trong virtual host

RabbitMQ có **default exchange** tên rỗng `""`, là một direct exchange đặc biệt. Queue thường có binding tự động với default exchange bằng đúng **tên queue**. Ví dụ:

~~~java
rabbitTemplate.convertAndSend(
        "",                    // Default exchange.
        "orders.created.q",    // Routing key = tên queue.
        "OrderCreated:O-1001"
);
~~~

Nếu queue `orders.created.q` tồn tại, message có thể được route qua default exchange. Nếu tên queue sai hoặc queue chưa tồn tại, trường hợp này là **unroutable qua một exchange có thật**, không phải “exchange không tồn tại”. Khi dùng `mandatory=true`, có thể nhận `NO_ROUTE`.

### 10.3. Loại exchange thay đổi quy tắc so khớp

| Exchange | Điều kiện định tuyến cơ bản | Lỗi thường gặp |
|---|---|---|
| **direct** | Routing key khớp binding key | Gửi key `order.created.v2` khi binding chỉ `order.created` |
| **topic** | Binding pattern dùng `*` và `#` trên routing key | Nhầm `order.*` có thể khớp `order.eu.created` |
| **fanout** | Phát đến các queue đã binding, không dựa vào routing key | Exchange không có binding nhưng nghĩ rằng key đúng sẽ giúp route |
| **headers** | So khớp header theo binding arguments, ví dụ `x-match` | Đặt routing key đúng nhưng thiếu header bắt buộc |

Với topic exchange, `*` khớp **đúng một** segment; `#` khớp **không hoặc nhiều** segment. Với headers exchange, kiểu dữ liệu và giá trị header phải được tính đến. Không lấy một binding key của direct exchange để suy diễn quy tắc cho tất cả exchange.

### 10.4. Sai virtual host giống “không tìm thấy tài nguyên”

Hai virtual host có thể đều có queue tên `orders.created.q` nhưng khác exchange/binding. Nếu ứng dụng kết nối vhost `/test` trong khi topology chỉ tồn tại tại vhost `/production`, broker **không tìm thấy exchange trong vhost hiện tại** và có thể đóng channel với 404. Kiểm tra connection URI/virtual host, quyền và môi trường trước khi tạo thêm topology.

### 10.5. Exchange có thật nhưng topology bị lỗi khai báo

Nếu ứng dụng khai báo exchange cùng tên nhưng **khác type/durability/arguments** so với exchange đã tồn tại, broker có thể phản hồi `PRECONDITION_FAILED` (thường mã `406`) trong lệnh declare. Đây là lỗi **khai báo tài nguyên**, không phải tín hiệu return `NO_ROUTE` của một message.

Một ứng dụng bị lỗi khai báo không thể suy ra publish đã đi qua topology mới. Cần xử lý migration topology có kiểm soát.

## 11. Đừng nhầm unroutable với retry và dead-letter

Một ví dụ đối chiếu ba tầng lỗi:

~~~mermaid
flowchart TD
    P["Publish message"] --> EX{"Exchange tồn tại?"}
    EX -->|Không| X["404 NOT_FOUND<br/>channel error"]
    EX -->|Có| RT{"Có queue đích?"}
    RT -->|Không| NR["Unroutable<br/>return nếu mandatory"]
    RT -->|Có| Q["Enqueue tới queue"]
    Q --> C["Consumer xử lý"]
    C --> OK{"Xử lý thành công?"}
    OK -->|Có| ACK["Ack delivery"]
    OK -->|Không| RETRY["Nack/reject, retry/requeue/DLX<br/>tùy cấu hình"]
~~~

**Dead-letter** thường áp dụng khi một message **đã nằm trong queue** và sau đó bị reject/nack không requeue, hết TTL, vượt giới hạn queue hoặc gặp điều kiện được hỗ trợ khác. Một publish không route được vì thiếu binding chưa vào queue nên queue DLX không tự tiếp nhận nó.

Nếu hệ thống cần xử lý các publish không có route, hãy cân nhắc:

- **Publisher returns + lưu sự kiện lỗi** để sửa routing hoặc gửi lại có kiểm soát.
- **Alternate exchange** cho một tuyến xử lý các message không khớp trên exchange chính.
- **Outbox/retry có trạng thái** khi tính bền vững đầu cuối là yêu cầu nghiệp vụ.

Nếu message đã route nhưng consumer xử lý lỗi, dùng cơ chế retry/requeue/DLX với giới hạn và idempotency. Không dùng vòng retry của producer để sửa lỗi của một consumer đã nhận message, vì publish lại có thể tạo thêm bản sao.

## 12. Thiết kế giám sát và phản ứng phù hợp từng tình huống

| Tín hiệu quan sát | Cách hiểu | Hành động trước tiên |
|---|---|---|
| Confirm `ack=true`, không return | Broker đã xác nhận publish; chưa chứng minh tới queue dự kiến | Đối chiếu topology, queue và consumer nếu nghiệp vụ chưa chạy |
| Return `312 NO_ROUTE` | Broker không route được và trả message theo mandatory | Kiểm tra exchange type, binding, routing key, AE và vhost |
| Lỗi `404 NOT_FOUND` khi publish | Không có exchange chỉ định ở vhost của channel | Kiểm tra tên exchange, quyền/khai báo, thứ tự khởi tạo và cấu hình connection |
| Lỗi `406 PRECONDITION_FAILED` khi declare | Định nghĩa tài nguyên không tương thích với broker | So sánh topology hiện có và lập kế hoạch migration |
| Message tăng trong queue, consumer không xử lý | Routing có thể đúng, nhưng delivery/consumer bị nghẽn | Kiểm tra consumer count, unacked count, listener errors, prefetch |
| DLQ tăng | Message đã vào queue rồi rơi vào luồng dead-letter | Điều tra exception, reject/nack, TTL, queue policy, vòng retry |

Những thông tin hữu ích cho log/metrics:

1. **publishId/messageId hoặc correlationId** ổn định để đối chiếu publisher với listener.
2. **Exchange, routing key, virtual host, loại exchange** và tài nguyên đích dự kiến.
3. **Publisher confirm status**, return code/reason và lỗi channel được ghi tách biệt.
4. **Queue depth, consumer count, unacked count, DLQ depth**, cùng tỷ lệ lỗi ứng dụng.
5. **Thời điểm và version cấu hình topology**, đặc biệt khi rolling deploy nhiều replica.

Tránh log toàn bộ body hay headers nhạy cảm. Dùng ID, schema version và dữ liệu đã hạn chế để truy vết, đồng thời xử lý an toàn các kết quả publish **không chắc chắn** (ví dụ mất kết nối khi đang đợi confirm): retry có thể phát sinh bản sao, nên consumer cần idempotency.

## 13. Thực hành kiểm thử theo kịch bản

Các kiểm thử sau nên chạy trên RabbitMQ test có thể quan sát topology. Để tách kết quả, thực hiện **mỗi phép thử trên một lượt**, dùng correlation ID riêng và ghi logs/callbacks.

| Kịch bản | Chuẩn bị | Publish | Kết quả mong đợi |
|---|---|---|---|
| **A1. Direct route đúng** | Direct exchange + queue + binding `order.created` | Key `order.created` | Message vào queue; không return `NO_ROUTE` |
| **A2. Nhiều queue cùng key** | Thêm queue audit với binding `order.created` | Key `order.created` | Mỗi queue được route một bản |
| **B1. Unroutable, mandatory=true** | Không có binding cho `order.cancelled` | Key `order.cancelled` | Return `312 NO_ROUTE`; confirm vẫn có thể ack |
| **B2. Unroutable, mandatory=false** | Giữ topology B1, tắt mandatory | Key `order.cancelled` | Không có return do mandatory; confirm có thể ack |
| **C1. Exchange không tồn tại** | Xác nhận `orders.missing` không có trong vhost | Exchange `orders.missing` | Lỗi channel `404 NOT_FOUND`, không nhận `312 NO_ROUTE` |
| **D1. Default exchange, queue có thật** | Queue `orders.created.q` tồn tại | Exchange rỗng; key bằng tên queue | Message vào queue |
| **D2. Alternate exchange** | Đặt AE cho exchange chính, binding AE tới queue dự phòng | Key không khớp binding chính | Message có thể vào queue dự phòng; không mặc nhiên có return |

### Quy trình quan sát A/B/C

1. Tạo và xác nhận topology của mục 7 trong RabbitMQ Management UI.
2. Tạm dừng listener để việc message vào queue không bị consumer lấy ngay, hoặc dùng queue test riêng.
3. Bật confirms, returns và mandatory; bảo đảm callback được đăng ký vào **đúng RabbitTemplate** được producer gọi.
4. Gửi A, quan sát queue nhận message và publisher confirm.
5. Gửi B, quan sát callback return `312 NO_ROUTE`, đối chiếu confirm cùng correlation ID.
6. Gửi C riêng, quan sát exception/log/channel closure, sau đó kiểm tra kết nối/channel mới nếu tiếp tục publish.
7. Nếu kết quả khác dự đoán, kiểm tra alternate exchange, các bindings khác, vhost, policy và các listener đang chạy trước khi kết luận RabbitMQ hoạt động sai.

### Bài tập 1 — Confirm ack nhưng không có message

Producer publish `order.cancelled` tới direct exchange chỉ có binding `order.created`. Publisher confirm báo `ack=true`, không có message trong queue. Giải thích vì sao và đề xuất cấu hình để phát hiện.

**Đáp án gợi ý:** broker có thể ack một publish không route được. Bật `mandatory=true`, publisher returns và `ReturnsCallback`/cơ chế tương đương để quan sát `NO_ROUTE`; sửa binding/routing key hoặc thiết kế AE.

### Bài tập 2 — Phân biệt NO_ROUTE và NOT_FOUND

Publisher gửi `orders.events` với key sai nhận `312 NO_ROUTE`; lần tiếp theo gửi `orders.evnts` nhận lỗi đóng channel `404 NOT_FOUND`.

**Đáp án gợi ý:** trường hợp đầu exchange tồn tại, route không khớp; trường hợp sau exchange sai tên hoặc không tồn tại trong virtual host. Không giải quyết lỗi 404 bằng cách thay binding key mà không kiểm tra exchange.

### Bài tập 3 — Default exchange

Queue `reports.q` tồn tại nhưng exchange `reports.direct` không tồn tại. Publish tới `""` với routing key `reports.q` và publish tới `reports.direct` với cùng routing key có kết quả giống nhau không?

**Đáp án gợi ý:** không. Default exchange là exchange có thật và thường route được bằng tên queue; `reports.direct` chưa tồn tại gây lỗi channel nếu publish đến nó.

### Bài tập 4 — Vì sao không có return dù sai binding chính?

Direct exchange có alternate exchange dạng fanout trỏ đến `orders.unrouted.q`. Producer dùng routing key không khớp binding chính nhưng không thấy `NO_ROUTE`.

**Đáp án gợi ý:** alternate exchange có thể đã route message tới queue dự phòng. Kiểm tra queue AE, không coi sự vắng mặt của return là bằng chứng đến queue chính.

### Bài tập 5 — Phân định publish và consume failure

Message đã vào `orders.created.q`, listener ném exception và message xuất hiện trong DLQ. Publisher có cần gửi lại từ đầu không?

**Đáp án gợi ý:** routing ban đầu đã thành công; đây là lỗi xử lý delivery và chính sách retry/DLX của consumer. Publisher gửi lại tùy yêu cầu nghiệp vụ và trạng thái hệ thống, nhưng làm vậy tùy tiện có thể tạo message trùng.

## 14. Checklist trước khi triển khai producer

- [ ] Xác định đúng **exchange name**, exchange type, virtual host và thời điểm resource được khai báo.
- [ ] Kiểm tra queue/binding hoặc headers/alternate exchange thực tế; không suy chỉ từ code.
- [ ] Bật publisher confirms khi cần bằng chứng broker xử lý publish.
- [ ] Bật mandatory + publisher returns khi cần phát hiện message không route được.
- [ ] Xử lý `312 NO_ROUTE` như lỗi routing, phân biệt với `404 NOT_FOUND` đóng channel do thiếu exchange.
- [ ] Không coi `ack=true` của publisher confirm là ack từ consumer hoặc bằng chứng message vào queue dự kiến.
- [ ] Với nhiều message đồng thời, dùng correlation data/ID để ghép return, confirm, exception và trạng thái nghiệp vụ.
- [ ] Chọn retry hợp lý; lỗi routing cố định cần sửa topology hoặc routing key trước khi gửi lại.
- [ ] Phân biệt unroutable với queue DLX, consumer exception và message expiration.
- [ ] Kiểm thử A/B/C trên RabbitMQ test đúng version/configuration; theo dõi logs, queue, returns và confirms.

**Ghi nhớ:** **Định tuyến đúng** nghĩa exchange tìm được queue phù hợp; **không định tuyến được** nghĩa exchange tồn tại nhưng không có đường đến queue, có thể phát `basic.return` khi `mandatory=true`; **exchange không tồn tại** gây lỗi channel, thường là `404 NOT_FOUND`. Ba kết quả cần cơ chế quan sát và xử lý khác nhau. Nắm vững điểm này giúp hệ thống Spring AMQP tránh làm mất message một cách âm thầm, chẩn đoán lỗi topology nhanh và xây luồng xử lý bất đồng bộ có thể kiểm chứng.
