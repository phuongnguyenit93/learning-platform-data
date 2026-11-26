# Durable, exclusive và auto-delete: ba thuộc tính khác nhau

## 1. Bài toán: queue còn tồn tại đến khi nào?

Khi tích hợp **RabbitMQ với Spring AMQP**, ứng dụng thường khai báo exchange, queue và binding bằng các bean Spring; sau đó gửi thông điệp qua `RabbitTemplate` và xử lý bằng `@RabbitListener`. Một quyết định rất quan trọng ở thời điểm **khai báo tài nguyên** là: tài nguyên đó phải tồn tại qua lần khởi động lại broker, chỉ thuộc về một kết nối hay tự biến mất khi không còn được sử dụng?

RabbitMQ có ba thuộc tính thường xuất hiện cạnh nhau:

- **`durable`**: tài nguyên có được lưu để tồn tại qua **lần khởi động lại RabbitMQ** hay không?
- **`exclusive`**: queue có chỉ dành cho **connection đã khai báo nó**, đồng thời bị xóa khi connection này mất, hay không?
- **`auto-delete`**: tài nguyên có tự xóa khi điều kiện **không còn được sử dụng** tương ứng đã xảy ra hay không?

Ba thuộc tính trả lời **ba câu hỏi khác nhau**. Chúng không thay thế nhau: một queue có thể `durable=true` nhưng vẫn bị xóa vì `autoDelete=true`; một queue `exclusive=true` có thể bị xóa ngay sau khi connection đóng, ngay cả khi không bật `autoDelete`.

Ví dụ thực tế:

| Nhu cầu | Cấu hình phù hợp | Lý do |
| --- | --- | --- |
| Queue xử lý đơn hàng, phải tiếp tục sau khi ứng dụng consumer khởi động lại | `durable=true, exclusive=false, autoDelete=false` | Queue độc lập với vòng đời consumer và không tự xóa khi consumer dừng. |
| Queue tạm để nhận phản hồi chỉ cho một ứng dụng đang kết nối | `durable=false, exclusive=true, autoDelete=true` | Queue gắn với connection, được dọn khi connection kết thúc; cần tên riêng cho mỗi instance. |
| Queue dùng chung ngắn hạn, chỉ cần trong thời gian có consumer | `durable=false, exclusive=false, autoDelete=true` | Sau khi đã có consumer, queue tự xóa khi consumer cuối cùng rời đi. |

**Nguyên tắc:** cấu hình vòng đời của queue dựa trên nghiệp vụ, không dựa trên suy đoán rằng queue “lưu tin nhắn” thì mặc nhiên phải có cả ba cờ.

## 2. Nhìn nhanh trên RabbitMQ và Spring AMQP

### 2.1. Trên queue

| Thuộc tính | Đối tượng áp dụng | Sự kiện cần xét | Hệ quả trực tiếp |
| --- | --- | --- | --- |
| `durable` | Queue | Broker khởi động lại | Queue bền vững được broker lưu định nghĩa và có thể khôi phục; queue không durable thường biến mất. |
| `exclusive` | **Queue** | Connection đã **khai báo** queue đóng hoặc bị broker nhận diện là mất | RabbitMQ xóa queue; connection khác không được sử dụng queue đó như queue chung. |
| `autoDelete` | Queue | **Consumer cuối cùng** bị hủy/ngắt **sau khi queue từng có ít nhất một consumer** | RabbitMQ xóa queue ngay cả khi connection khai báo queue còn tồn tại. |

### 2.2. Trên exchange

Exchange có `durable` và `autoDelete`, nhưng **không có thuộc tính `exclusive` như queue**:

| Thuộc tính | Ý nghĩa với exchange |
| --- | --- |
| `durable=true` | Định nghĩa exchange còn tồn tại qua broker restart, trừ khi bị xóa bởi hành động/chính sách khác. |
| `autoDelete=true` | Exchange có thể tự bị xóa khi không còn binding sử dụng nó; điển hình là khi **binding cuối cùng bị gỡ**. |
| `exclusive` | **Không áp dụng** như một flag khai báo exchange. |

Đối với **queue**, auto-delete phụ thuộc **consumer**; đối với **exchange**, auto-delete phụ thuộc **binding**. Không được dùng chung một mô tả “xóa khi không còn ai dùng” mà bỏ qua hai điều kiện khác nhau này.

~~~mermaid
flowchart TD
    Q["Queue được khai báo"]
    D{"Broker restart?"}
    E{"durable = true?"}
    X{"exclusive = true và declaring connection mất?"}
    A{"autoDelete = true và consumer cuối rời đi sau khi đã có consumer?"}
    KEEP["Queue còn tồn tại"]
    DROP["Queue bị xóa"]
    Q --> X
    X -- Có --> DROP
    X -- Không --> A
    A -- Có --> DROP
    A -- Không --> D
    D -- Không --> KEEP
    D -- Có --> E
    E -- Có --> KEEP
    E -- Không --> DROP
~~~

Sơ đồ đơn giản hóa ba cờ để thấy điểm xóa **có thể xảy ra**. Để bảo đảm xử lý thông điệp qua sự cố còn phải tính đến message persistence, loại queue, cơ chế xác nhận publish, replication và chính sách broker.

## 3. Durable: tồn tại qua lần khởi động lại broker

### 3.1. `durable=true` thực sự bảo vệ điều gì?

Một queue durable được RabbitMQ lưu định nghĩa để khôi phục sau khi broker khởi động lại. Ví dụ:

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;

@Bean
Queue orderQueue() {
    return new Queue("orders.created.q", true);
}
~~~

Constructor hai tham số đặt tên queue và `durable=true`. Với `Queue` của Spring AMQP, các thuộc tính còn lại mặc định là **`exclusive=false`** và **`autoDelete=false`** trong trường hợp khai báo này.

Một queue durable **không tự biến mất** chỉ vì consumer tạm dừng. Điều đó phù hợp với xử lý bất đồng bộ: ứng dụng nhận có thể triển khai lại mà queue vẫn tồn tại để chờ consumer.

Tuy nhiên, **durable queue khác durable message**. Phải phân biệt:

1. **Độ bền của định nghĩa queue:** `durable=true`.
2. **Độ bền của thông điệp:** message được publish với delivery mode phù hợp, chẳng hạn `PERSISTENT` cho classic queue, và broker đã xử lý ghi nhận theo cơ chế của loại queue.
3. **Mức độ tin cậy khi publish:** publisher confirms giúp producer biết broker có xác nhận việc publish hay chưa.
4. **Mức độ tin cậy khi consume:** consumer ack chỉ được gửi sau khi đã hoàn thành những bước nghiệp vụ cần thiết; xử lý trùng lặp bằng idempotency.

Nếu queue durable mà producer gửi transient messages, không được suy ra các thông điệp đó chắc chắn sống sót sau broker restart. Ngược lại, message mang delivery mode persistent **không cứu được** queue không durable khi chính queue biến mất.

### 3.2. Durable không phải là miễn nhiễm với mọi kiểu xóa

`durable=true` **không ngăn** queue bị xóa bởi:

- Lệnh xóa queue từ API/UI hoặc bởi người vận hành.
- Chính sách hết hạn queue như `x-expires` khi queue đủ điều kiện “unused”.
- `autoDelete=true` khi consumer cuối cùng rời đi.
- `exclusive=true` khi connection sở hữu queue mất.
- Hỏng hóc dữ liệu hoặc mất hạ tầng vượt ngoài mức bảo đảm của cấu hình broker.

Với hệ thống quan trọng, hãy chọn loại queue và mô hình triển khai tương ứng. Chẳng hạn, **quorum queue** cung cấp replication và cơ chế xác nhận phù hợp nhưng có những giới hạn riêng: không dùng mô hình exclusive/auto-delete để tạo queue quorum tạm thời. Không suy ra “durable=true” tương đương “đã có replication”.

## 4. Exclusive: quyền sử dụng và vòng đời theo connection

### 4.1. Exclusive queue thuộc về connection khai báo

Khi một connection khai báo queue với `exclusive=true`, RabbitMQ gắn queue đó với chính **connection** ấy. Các connection khác không thể sử dụng queue như một queue chung; thao tác truy cập hoặc redeclare trái với tính độc quyền có thể nhận lỗi `RESOURCE_LOCKED`.

Điểm quan trọng là **connection, không phải consumer**:

- Một connection có thể có nhiều channel và nhiều consumer; queue vẫn thuộc cùng connection đã khai báo.
- Nếu listener bị hủy nhưng connection khai báo vẫn còn sống, cờ `exclusive` **tự nó chưa gây xóa**.
- Khi connection khai báo bị đóng, mất mạng rồi được broker xác định đã chết, hoặc broker restart làm connection mất, **exclusive queue bị xóa**.

Ví dụ queue dành cho một kết nối:

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;

@Bean
Queue connectionScopedQueue() {
    return QueueBuilder.nonDurable("reply.instance.a.q")
            .exclusive()
            .autoDelete()
            .build();
}
~~~

Tên `reply.instance.a.q` chỉ để minh họa. Trong hệ thống chạy nhiều instance, **không nên dùng cùng một tên tĩnh** cho các exclusive queue của những connection khác nhau: instance thứ hai có thể va chạm tài nguyên của instance thứ nhất.

Để tạo queue riêng cho từng instance, Spring AMQP cung cấp `AnonymousQueue` với tên ngẫu nhiên và cấu hình tạm thời:

~~~java
import org.springframework.amqp.core.AnonymousQueue;
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;

@Bean
Queue temporaryReplyQueue() {
    return new AnonymousQueue();
}
~~~

`AnonymousQueue` của Spring AMQP thường là **non-durable, exclusive, auto-delete** và sinh **tên riêng ở phía Spring**, thuận tiện cho queue phản hồi hoặc queue event riêng từng instance. Tên này không có nghĩa là queue hoàn toàn vô danh trên broker; nó có một tên cụ thể và sẽ được khai báo qua cơ chế Spring AMQP.

### 4.2. Exclusive queue không phải exclusive consumer

RabbitMQ cũng có khái niệm **exclusive consumer**: một consumer được cấp quyền tiêu thụ độc quyền từ một queue nhất định. Đây là cơ chế khác:

| Khái niệm | Phạm vi độc quyền | Khi kết nối mất |
| --- | --- | --- |
| **Exclusive queue** | Queue dành cho connection khai báo | Queue bị xóa. |
| **Exclusive consumer** | Giới hạn consumer đối với một queue | Consumer mất; queue có thể vẫn tồn tại nếu khai báo không gắn queue với connection. |
| **Single active consumer** | Broker chỉ cho một consumer hoạt động tại một thời điểm, có thể chuyển consumer active khi failover | Queue thường vẫn tồn tại, consumer khác có thể được kích hoạt theo chính sách. |

Đừng chọn exclusive queue chỉ vì muốn **một consumer xử lý tại một thời điểm**. Nếu muốn chia sẻ một queue bền vững giữa nhiều application instance nhưng chỉ có một consumer active, hãy đánh giá cơ chế **single active consumer** hoặc cấu hình số consumer phù hợp.

Exclusive không thay thế cho **user permission, virtual host và TLS**. Nó là quy tắc ownership của queue theo connection.

## 5. Auto-delete: xóa khi điều kiện sử dụng kết thúc

### 5.1. Auto-delete trên queue

Với queue `autoDelete=true`, RabbitMQ tự xóa queue **khi consumer cuối cùng đã rời đi**, với điều kiện queue **đã từng có ít nhất một consumer**. Đây là chi tiết đặc biệt quan trọng:

~~~text
Tạo queue auto-delete, chưa có consumer
    -> queue chưa bị xóa chỉ vì đang có 0 consumer.

Consumer A bắt đầu nhận
    -> queue có 1 consumer.

Consumer B cũng bắt đầu nhận
    -> queue có 2 consumer.

Consumer A rời đi
    -> queue vẫn tồn tại vì còn B.

Consumer B rời đi
    -> queue bị auto-delete.
~~~

Đăng ký consumer, sau đó dừng listener container có thể kích hoạt auto-delete ngay cả khi **publisher đang hoạt động** và queue **vẫn còn message ready**. Bởi vậy, không nên dùng auto-delete cho queue công việc quan trọng chỉ vì có thể tự khai báo lại lúc ứng dụng khởi động.

Nếu queue chưa từng có consumer thì cờ auto-delete chưa đủ để xóa nó; nếu muốn queue tự hết hạn khi không được dùng, hãy tìm hiểu **`x-expires`** (queue TTL) như một chính sách khác.

### 5.2. Auto-delete trên exchange

Exchange `autoDelete=true` được broker tự dọn khi **binding cuối cùng bị gỡ** sau khi exchange đã được sử dụng. Nó không quan tâm queue còn consumer hay không. Chẳng hạn:

~~~text
Exchange E (auto-delete=true)
       |
       +-- binding --> Queue Q1
       |
       +-- binding --> Queue Q2

Xóa binding Q1: E còn binding Q2 -> E còn.
Xóa binding Q2: E không còn binding -> E có thể bị auto-delete.
~~~

Vì thế có thể tạo exchange durable nhưng auto-delete; hai cờ này không mâu thuẫn về cú pháp, nhưng thường **không phù hợp** nếu exchange là thành phần hạ tầng lâu dài cho nhiều ứng dụng.

### 5.3. Auto-delete khác queue TTL và message TTL

| Cơ chế | Điều kiện | Đối tượng bị tác động |
| --- | --- | --- |
| Queue `autoDelete=true` | Consumer cuối cùng rời đi sau khi từng có consumer | **Cả queue**, kèm những message chưa được xử lý trong đó. |
| Exchange `autoDelete=true` | Binding cuối cùng không còn | **Exchange**, không đồng nghĩa xóa các queue trước đó. |
| Queue `x-expires` | Queue đạt thời gian **không được sử dụng** theo quy tắc broker | **Cả queue**. |
| Message `x-message-ttl` hoặc TTL riêng của message | Message hết thời gian sống | **Message**, không mặc nhiên xóa queue. |
| `x-max-length` / giới hạn độ dài | Queue vượt giới hạn cấu hình | Message có thể bị loại bỏ hoặc publish bị từ chối theo policy. |

Khi kết hợp dead-letter exchange (DLX), message bị reject, hết TTL hoặc bị loại bỏ trong những điều kiện được hỗ trợ có thể được dead-letter theo cấu hình. **Xóa cả queue** do auto-delete không được hiểu là từng message trong queue sẽ tự động chuyển sang DLQ.

## 6. Chọn tổ hợp cờ theo mục đích

Các cờ về mặt khái niệm độc lập, nhưng không phải tổ hợp nào cũng hợp lý trong vận hành hoặc được hỗ trợ bởi mọi loại queue.

| Durable | Exclusive | Auto-delete | Cách hiểu và tình huống |
| :---: | :---: | :---: | --- |
| `true` | `false` | `false` | **Queue nghiệp vụ ổn định**, độc lập vòng đời connection/consumer. |
| `false` | `true` | `true` | **Queue tạm từng instance**; xóa khi connection mất hoặc consumer cuối rời đi. |
| `false` | `false` | `true` | **Queue chia sẻ nhưng ngắn hạn**; hết consumer thì xóa. |
| `false` | `false` | `false` | Queue không tự xóa khi consumer dừng nhưng **không giữ qua broker restart**. |
| `true` | `false` | `true` | Queue có định nghĩa bền vững nhưng **sẽ bị auto-delete sau vòng đời consumer**; dễ bất ngờ nếu xem durable như bảo đảm giữ queue mãi. |
| `false` | `true` | `false` | Exclusive queue vẫn **bị xóa khi connection mất**, dù tắt auto-delete. |
| `true` | `true` | `false/true` | Không phù hợp cho queue durable có vòng đời dài; exclusive queue vẫn gắn chặt với connection và bị xóa khi connection mất. Tránh thiết kế này. |

### Ba câu hỏi trước khi khai báo

1. **Nếu RabbitMQ restart, tôi có cần queue này còn tồn tại?** Nếu có, cân nhắc queue durable và chính sách lưu/replication tương ứng.
2. **Nếu ứng dụng đang khai báo queue bị mất connection, ứng dụng khác có cần tiếp tục sử dụng queue không?** Nếu có, không dùng exclusive.
3. **Nếu tất cả consumer tạm dừng vài phút để triển khai lại, message có phải được giữ chờ không?** Nếu có, **không dùng auto-delete**.

Đối với queue nhận đơn hàng, ba câu hỏi thường dẫn tới `true / false / false`. Đối với queue phản hồi ngắn hạn cho một connection, thường là `false / true / true`.

## 7. Khai báo thực tế bằng Spring AMQP

### 7.1. Queue nghiệp vụ ổn định: durable=true, exclusive=false, autoDelete=false

Ví dụ Spring Boot dùng `spring-boot-starter-amqp` và RabbitMQ AMQP 0.9.1. Cấu hình exchange, queue và binding:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderRabbitTopology {
    public static final String EXCHANGE = "orders.events";
    public static final String QUEUE = "orders.created.q";
    public static final String ROUTING_KEY = "order.created";

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue ordersQueue() {
        return QueueBuilder.durable(QUEUE).build();
        // Tương đương new Queue(QUEUE, true, false, false).
    }

    @Bean
    Binding ordersBinding(Queue ordersQueue, DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
                .to(ordersExchange)
                .with(ROUTING_KEY);
    }
}
~~~

`DirectExchange(EXCHANGE, true, false)` nghĩa là exchange **durable**, **không auto-delete**. `QueueBuilder.durable(QUEUE)` tạo queue **durable**, **không exclusive**, **không auto-delete**. Binding định tuyến message có routing key `order.created` đến queue.

Khi `RabbitAdmin` hoạt động, Spring AMQP có thể tự khai báo các bean exchange, queue và binding lúc thiết lập kết nối. Nó **không bảo đảm sửa được cờ của queue đã tồn tại**: broker kiểm tra tính tương đương của các tham số khai báo.

Producer và consumer:

~~~java
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {
    private final RabbitTemplate template;

    OrderPublisher(RabbitTemplate template) {
        this.template = template;
    }

    void publish(String orderId) {
        template.convertAndSend(
                OrderRabbitTopology.EXCHANGE,
                OrderRabbitTopology.ROUTING_KEY,
                orderId,
                message -> {
                    message.getMessageProperties()
                            .setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                    return message;
                });
    }
}

@Component
class OrderCreatedConsumer {
    @RabbitListener(queues = OrderRabbitTopology.QUEUE)
    void handle(String orderId) {
        // Ví dụ: xử lý có kiểm soát lỗi và idempotency.
        System.out.println("Xu ly don hang: " + orderId);
    }
}
~~~

Trong ví dụ, delivery mode `PERSISTENT` minh họa thiết lập lưu message cho classic queue. Để đạt độ tin cậy thực tế còn cần **publisher confirms**, consumer acknowledgment thích hợp, retry có giới hạn và xử lý trùng theo event ID. Queue durable **không đảm bảo** người nhận xử lý đúng một lần.

### 7.2. Queue tạm, riêng từng application instance

Giả sử một ứng dụng muốn tự nhận sự kiện `order.created` trong lúc nó còn sống, nhưng không muốn giữ queue sau khi instance dừng:

~~~java
import org.springframework.amqp.core.AnonymousQueue;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TemporaryEventsTopology {

    @Bean("instanceEventsQueue")
    Queue instanceEventsQueue() {
        return new AnonymousQueue();
    }

    @Bean
    Binding instanceEventsBinding(
            @Qualifier("instanceEventsQueue") Queue temporaryQueue,
            DirectExchange ordersExchange) {
        return BindingBuilder.bind(temporaryQueue)
                .to(ordersExchange)
                .with("order.created");
    }
}
~~~

Listener sử dụng tên queue đã được sinh:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
class InstanceEventsListener {
    @RabbitListener(queues = "#{instanceEventsQueue.name}")
    void onEvent(String orderId) {
        System.out.println("Su kien cua instance hien tai: " + orderId);
    }
}
~~~

Ví dụ này giả định bean `ordersExchange` từ mục 7.1 vẫn tồn tại. Tại runtime, queue tạm sẽ có tên riêng do Spring AMQP sinh và có binding tới exchange; khi connection khai báo queue mất hoặc sau khi listener cuối cùng ngừng, queue được xóa theo cờ tương ứng.

**Không dùng queue tạm này làm queue công việc** nếu sự kiện phải chờ xử lý trong thời gian không có consumer. Với nhiều instance, mỗi instance có queue riêng có thể nhận **một bản** của sự kiện qua binding chung, phù hợp broadcast/fan-out có điều kiện; khác với nhiều instance cùng tiêu thụ **một queue nghiệp vụ** để chia tải.

### 7.3. Đọc trực tiếp tất cả cờ trong một constructor

Trong `org.springframework.amqp.core.Queue`:

~~~java
new Queue("demo.q", true, false, false);
//                    |     |      |
//                  durable exclusive autoDelete
~~~

Khi đọc code, hãy xác nhận thứ tự **`name, durable, exclusive, autoDelete`**. Đảo cờ thường gây lỗi tinh vi, chẳng hạn tưởng đã tạo queue durable nhưng thực tế lại tạo queue non-durable exclusive.

Thay vì bốn tham số boolean dễ đọc nhầm, `QueueBuilder` thường thể hiện ý đồ tốt hơn:

~~~java
Queue stable = QueueBuilder.durable("stable.q").build();
Queue temporary = QueueBuilder.nonDurable("temporary.q")
        .exclusive()
        .autoDelete()
        .build();
~~~

## 8. Những điều xảy ra khi restart, reconnect và redeclare

### 8.1. Vòng đời của queue trong bốn tình huống

| Tình huống | Durable, shared, không auto-delete | Non-durable exclusive auto-delete | Non-durable shared auto-delete |
| --- | --- | --- | --- |
| Consumer cuối cùng dừng, declaring connection còn | Queue **còn** | Queue bị xóa vì auto-delete sau khi từng có consumer | Queue bị xóa vì auto-delete sau khi từng có consumer |
| Declaring connection đóng, vẫn có broker | Queue **còn** | Queue bị xóa vì exclusive | Queue có thể còn **nếu chưa kích hoạt điều kiện auto-delete**; nếu consumer cuối đã rời đi thì bị xóa |
| Broker restart | Định nghĩa queue được khôi phục | Queue bị xóa vì không durable/exclusive | Queue không durable không được khôi phục |
| Spring reconnect, khai báo lại bean | Có thể sử dụng lại queue cũ nếu tham số khớp | Queue mới được khai báo lại; dữ liệu queue cũ đã mất | Queue có thể được tạo lại; dữ liệu queue cũ đã mất |

**Spring tự khai báo lại queue không phải là “khôi phục message”.** Một queue vừa bị xóa rồi tạo lại có thể có **cùng tên** nhưng không còn những thông điệp trước đó. Với các queue tạm, đây có thể là điều mong muốn. Với queue xử lý đơn hàng, đó có thể là mất dữ liệu nghiệp vụ.

### 8.2. Khi đổi cờ của queue đã tồn tại

Giả sử RabbitMQ đang có queue:

~~~text
name: orders.created.q
durable: true
exclusive: false
auto-delete: false
~~~

Sau đó code đổi thành:

~~~java
new Queue("orders.created.q", false, false, true);
~~~

Khi Spring AMQP khai báo lại queue với **cùng tên** nhưng thuộc tính khác, RabbitMQ có thể trả lỗi **`PRECONDITION_FAILED`** (các tham số khai báo không tương đương), và channel khai báo bị đóng. Việc chỉnh mã Java **không tự biến đổi** queue đang tồn tại trên broker.

Đối với production, cần lên kế hoạch thay đổi topology có kiểm soát, chẳng hạn:

1. Xác định queue hiện tại, producer/consumer đang sử dụng và số message chưa xử lý.
2. Nếu cần thay thuộc tính không tương thích, tạo queue **tên mới** với cấu hình mới và binding tương ứng.
3. Chuyển traffic và theo dõi consumer của queue mới; đối soát message/ack và trạng thái nghiệp vụ.
4. Chờ queue cũ được xử lý hết hoặc di chuyển dữ liệu có kiểm soát, rồi mới gỡ queue cũ.

Không xóa queue production chỉ để vượt qua lỗi `PRECONDITION_FAILED` khi chưa kiểm tra dữ liệu đang tồn đọng.

### 8.3. Exclusive queue và reconnect

Một exclusive queue đang được sử dụng có thể gặp **race condition** khi connection cũ chưa được broker nhận diện là mất mà connection mới cố khai báo lại cùng tên. Broker có thể tạm trả `RESOURCE_LOCKED`; vì thế nên dùng tên queue riêng cho mỗi instance và cấu hình recovery/retry phù hợp. Không dùng exclusive queue cố định để phối hợp nhiều node.

## 9. Những cờ này không thay thế cơ chế giao nhận đáng tin cậy

Chọn đúng vòng đời của queue chỉ giải quyết việc **queue có tồn tại hay không**. Một hệ thống Spring AMQP cần thêm các lớp bảo đảm:

| Yêu cầu | Thành phần/cơ chế cần kiểm tra |
| --- | --- |
| Message được định tuyến đúng | Exchange type, routing key, binding, mandatory returns khi cần. |
| Message đã được broker tiếp nhận | Publisher confirms, correlation ID, xử lý timeout và trạng thái chưa rõ. |
| Message chờ khi consumer tạm ngừng | Durable non-exclusive non-auto-delete queue, message persistence và chính sách broker phù hợp. |
| Delivery được xử lý trước khi xóa khỏi trạng thái unacked | `@RabbitListener` và consumer acknowledgment; xử lý exception thích hợp. |
| Thử lại khi lỗi tạm thời | Retry có backoff và giới hạn; không requeue nóng vô hạn. |
| Lỗi không khắc phục được | Dead-letter exchange/queue (DLX/DLQ), quan sát nguyên nhân và quy trình xử lý. |
| Có thể nhận lại cùng một message | Event ID, idempotent consumer, giao dịch database phù hợp. |
| Ghi DB và phát event nhất quán | Xem xét **transactional outbox** nếu hai hành động cần cam kết cùng nghiệp vụ. |

Ví dụ, một queue `durable=true` vẫn có thể mất message nếu ứng dụng publish sai routing key, nếu message không có mức độ bền phù hợp, hoặc nếu consumer ack trước khi ghi dữ liệu nghiệp vụ rồi gặp lỗi. Ngược lại, dùng `exclusive=true` không khiến một lần giao message trở thành “exactly once”.

## 10. Kiểm tra trong RabbitMQ Management và thực hành

RabbitMQ Management UI cho phép xem chi tiết queue/exchange đang có: tên, trạng thái, các flags như durable/auto-delete, số consumer, messages ready và unacknowledged. Có thể kiểm tra các kết quả sau trong môi trường phát triển (không thử xóa trên queue production):

| Thí nghiệm | Các bước | Kết quả dự kiến |
| --- | --- | --- |
| **A. Durable queue** | Khai báo `orders.created.q` như mục 7.1; tắt consumer, giữ broker chạy. | Queue vẫn tồn tại; message gửi đúng route có thể chờ ở `ready`. |
| **B. Durable qua broker restart** | Dùng queue mục 7.1, gửi message persistent; bảo đảm broker xử lý publish rồi restart broker. | Định nghĩa queue được khôi phục; khả năng khôi phục message phụ thuộc queue type, persistence và trạng thái broker đã xác nhận. |
| **C. Exclusive queue** | Tạo `instanceEventsQueue`, thử truy cập từ connection khác, sau đó đóng connection khai báo. | Connection khác có thể gặp `RESOURCE_LOCKED`; khi connection sở hữu bị đóng, queue bị xóa. |
| **D. Auto-delete queue** | Khai báo queue auto-delete, đăng ký consumer rồi hủy consumer cuối. | Queue bị xóa, bất kể cờ durable. |
| **E. Queue auto-delete chưa có consumer** | Tạo queue auto-delete nhưng chưa từng đăng ký consumer. | Queue chưa bị xóa chỉ vì hiện tại consumer count bằng 0. |
| **F. Sai thuộc tính khi redeclare** | Khai báo `demo.q` durable rồi cố khai báo lại cùng tên với `durable=false`. | RabbitMQ trả lỗi khai báo không tương đương, thường là `PRECONDITION_FAILED`. |

Gợi ý quan sát lỗi và kiểm tra:

- Nếu không thấy queue sau một lần reconnect, kiểm tra queue có `exclusive=true` hay bị auto-delete sau khi listener cuối dừng không.
- Nếu nhiều instance dùng chung queue bị `RESOURCE_LOCKED`, kiểm tra có khai báo exclusive queue tên tĩnh không.
- Nếu consumer vừa khởi động lại mà queue có tên cũ nhưng dữ liệu biến mất, kiểm tra queue đã bị xóa rồi Spring khai báo lại chưa.
- Nếu application log báo `PRECONDITION_FAILED`, so sánh chính xác flags/arguments của queue trên broker với bean Spring, thay vì chỉ nhìn tên queue.
- Nếu queue còn tồn tại nhưng thông điệp bị mất/không được xử lý, kiểm tra publisher confirms, message persistence, routing, consumer ack, retry và DLQ.

## 11. Tự kiểm tra

**Câu 1.** Một queue khai báo `durable=true, exclusive=false, autoDelete=true`. Consumer cuối đã rời đi. Queue còn không?

**Trả lời:** Không, nếu queue đã từng có consumer. `autoDelete=true` có thể xóa queue dù `durable=true`.

**Câu 2.** Một queue khai báo `durable=false, exclusive=true, autoDelete=false`. Connection khai báo bị đóng. Queue còn không?

**Trả lời:** Không. Exclusive queue bị xóa khi connection sở hữu mất, không phụ thuộc auto-delete.

**Câu 3.** Queue `autoDelete=true` chưa từng có consumer; hiện consumer count = 0. Nó tự xóa ngay không?

**Trả lời:** Không chỉ vì consumer count bằng 0; điều kiện queue auto-delete phát sinh sau khi đã có ít nhất một consumer và consumer cuối bị hủy.

**Câu 4.** Một exchange `durable=true, autoDelete=true` có bị xóa khi binding cuối cùng không còn?

**Trả lời:** Có thể. Durable xử lý khả năng tồn tại qua restart; auto-delete xử lý điều kiện exchange không còn binding sử dụng.

**Câu 5.** Vì sao cấu hình queue bền vững vẫn phải kết hợp publisher confirm, consumer ack và idempotency?

**Trả lời:** Vì tồn tại queue không chứng minh message được publish thành công, listener đã hoàn thành nghiệp vụ hay side effect chỉ xảy ra một lần.

## 12. Tài liệu tham khảo

- [RabbitMQ — Queues](https://www.rabbitmq.com/docs/queues): định nghĩa queue, durability, exclusive ownership, auto-delete và queue TTL.
- [RabbitMQ — Exchanges](https://www.rabbitmq.com/docs/exchanges): exchange durability, auto-delete, bindings và routing.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): tín hiệu xác nhận ở hai đầu publish/consume.
- [RabbitMQ — Time-To-Live and Expiration](https://www.rabbitmq.com/docs/ttl): sự khác biệt giữa TTL của message và queue.
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/): `Queue`, `QueueBuilder`, `AnonymousQueue`, `RabbitAdmin`, `RabbitTemplate` và `@RabbitListener`.

Trong thiết kế hệ thống bất đồng bộ bằng **Spring AMQP**, hãy nhớ ba ý độc lập: **durable** liên quan đến *broker restart*; **exclusive** liên quan đến *connection khai báo queue*; **auto-delete** liên quan đến *consumer cuối rời queue* hoặc *binding cuối rời exchange*. Khi lựa chọn đúng cờ và kết hợp với routing, ack, retry, dead-letter, giao dịch cùng quan sát hệ thống, vòng đời tài nguyên sẽ khớp hơn với yêu cầu tin cậy của nghiệp vụ.
