# Queue exchange binding và routing key

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích chính xác vai trò của **queue**, **exchange**, **binding** và **routing key** trong RabbitMQ/AMQP 0-9-1.
- Phân biệt các kiểu exchange **direct**, **topic**, **fanout**, **headers** và **default exchange**; dự đoán queue nào nhận một bản publish.
- Thiết kế topology cho trường hợp nhiều hệ thống cần cùng một sự kiện hoặc nhiều worker chia việc trên một queue.
- Khai báo exchange, queue và binding qua **Spring AMQP**, sau đó kết nối chúng với **Spring Integration AMQP inbound/outbound adapter** và **MessageChannel**.
- Phân tích trường hợp **unroutable**, publisher confirms/returns, mandatory, alternate exchange, dead-letter exchange và consumer acknowledgment.
- Xem xét độ bền, bảo mật, quyền truy cập, vòng đời kết nối, retry, idempotency và quan sát khi triển khai production.

## 1. Tại sao cần hiểu topology trước khi dùng AMQP adapter?

Giả sử hệ thống đặt hàng phát sự kiện **OrderCreated**. Dịch vụ kho cần cập nhật tồn kho; dịch vụ phân tích cần ghi nhận thống kê; trong khi nhóm worker xử lý thanh toán có một queue công việc riêng. Nếu producer chỉ biết tên một queue và không hiểu exchange/binding, rất dễ cấu hình nhầm thành **các consumer cạnh tranh cùng một queue** thay vì **mỗi dịch vụ nhận một bản sao**.

RabbitMQ sử dụng mô hình định tuyến:

~~~mermaid
flowchart LR
    P["Producer / RabbitTemplate"] -->|"basic.publish<br/>exchange + routing key"| X["RabbitMQ exchange"]
    X -->|"Binding A"| Q1["Queue: warehouse"]
    X -->|"Binding B"| Q2["Queue: analytics"]
    Q1 --> C1["Warehouse consumer"]
    Q2 --> C2["Analytics consumer"]
~~~

Trong ứng dụng Spring Integration, luồng thường đi như sau:

~~~text
Service activator / Transformer
  -> Spring MessageChannel
  -> AMQP outbound channel adapter
  -> RabbitTemplate / ConnectionFactory
  -> RabbitMQ exchange
  -> binding phù hợp
  -> RabbitMQ queue
  -> Spring AMQP listener container
  -> AMQP inbound channel adapter
  -> Spring MessageChannel phía nhận
~~~

Điểm cần phân biệt:

- **MessageChannel** là kênh chuyển giao message **bên trong ứng dụng Spring**.
- **RabbitMQ queue** là tài nguyên **trên broker**, giữ các message đã được định tuyến tới nó.
- **Exchange** quyết định định tuyến, không phải nơi consumer thông thường lấy message.
- **Binding** mô tả quan hệ giữa exchange và queue.
- **Routing key** là giá trị publisher gắn với từng lần publish để exchange áp dụng quy tắc định tuyến.

Một luồng có thể sử dụng HTTP, SFTP, JMS, Kafka, file hoặc database ở những biên khác; tuy nhiên khi đi qua AMQP, các quy tắc RabbitMQ về exchange, queue và routing key vẫn phải được tuân thủ.

## 2. Bốn khái niệm cốt lõi

| Khái niệm | Nằm ở đâu? | Vai trò chính | Điều nó **không** tự làm |
| --- | --- | --- | --- |
| **Queue** | RabbitMQ broker | Chứa những message đã được route, chờ delivery cho consumer | Tự copy mọi message cho mọi consumer |
| **Exchange** | RabbitMQ broker | Nhận publish và chọn đích theo loại exchange cùng bindings | Mặc nhiên lưu message như một queue |
| **Binding** | RabbitMQ broker | Kết nối exchange với queue theo điều kiện | Tạo business ACK hay transaction |
| **Routing key** | Thuộc tính của thao tác publish | Cung cấp giá trị để exchange xét route | Tự tạo queue hoặc thay business event ID |

### 2.1. Producer gửi vào exchange

Trong AMQP 0-9-1, producer thực hiện publish với các thông tin quan trọng:

~~~text
basic.publish(
  exchange = "commerce.events",
  routingKey = "orders.created",
  properties = ...,
  body = bytes
)
~~~

**Exchange name** là tên tài nguyên trên broker; **routing key** là chuỗi được dùng khi định tuyến. **Body** và **message properties** có hợp đồng serialize riêng, ví dụ contentType, correlationId và messageId.

Khi dùng Spring AMQP:

~~~java
rabbitTemplate.convertAndSend(
    "commerce.events",
    "orders.created",
    "evt-1001|O-1001|150000");
~~~

RabbitTemplate chuyển payload thành AMQP message theo MessageConverter rồi publish tới exchange được nêu. Lệnh này không mặc nhiên chứng minh bản tin đến một queue nào đó hoặc consumer đã xử lý.

### 2.2. Queue là nơi consumer nhận delivery

Consumer thường đăng ký đọc **queue**, không đọc trực tiếp từ exchange. Nếu nhiều consumer cùng tiêu thụ một queue, chúng thường **chia nhau các delivery**; broker có thể giao lại message chưa ACK khi consumer gặp sự cố.

Nếu hai hệ thống độc lập đều cần OrderCreated, hãy đặt **hai queue** và bind cả hai vào exchange. Nếu một hệ thống muốn chạy nhiều instance worker để chia tải, có thể đặt **nhiều consumer trên cùng một queue**.

### 2.3. Một exchange có thể định tuyến đến nhiều queue

Một lần publish có thể khớp nhiều bindings và đến nhiều queue khác nhau. Đối với một queue có nhiều binding cùng khớp, RabbitMQ không có nghĩa phải tạo nhiều bản sao message cho cùng queue chỉ vì có nhiều binding trùng điều kiện.

Quan hệ exchange–queue **không nhất thiết là 1–1**:

- Một exchange có thể bind tới nhiều queue.
- Một queue có thể bind với nhiều exchange.
- Một exchange có thể có nhiều bindings với các binding key khác nhau.
- Khi xóa một binding, không đồng nghĩa xóa queue; khi xóa queue, các binding liên quan cũng không thể tiếp tục route tới queue đó.

## 3. Các kiểu exchange và quy tắc định tuyến

RabbitMQ hỗ trợ các kiểu exchange phổ biến sau:

| Loại exchange | Cách quyết định route | Ví dụ phù hợp |
| --- | --- | --- |
| **Direct** | Routing key phải khớp chính xác binding key | Chuyển lệnh theo loại hoặc tên hàng đợi logic |
| **Topic** | Routing key được so với pattern binding, tách các từ bởi dấu chấm | Event theo miền: orders.created, orders.cancelled |
| **Fanout** | Phân phối tới những queue được bind, bỏ qua routing key | Phát thông báo đến nhiều nhóm nhận |
| **Headers** | Dựa trên message headers và điều kiện binding, không phải pattern routing key | Định tuyến theo thuộc tính metadata |
| **Default exchange** | Direct exchange dựng sẵn tên rỗng, queue tự có binding theo tên queue | Gửi đơn giản tới một queue theo tên |

### 3.1. Direct exchange: khớp chính xác

Giả sử direct exchange **operations.direct** có hai bindings:

~~~text
operations.direct -- key = "payments.charge" --> payments.charge.q
operations.direct -- key = "payments.refund" --> payments.refund.q
~~~

Publish với routing key **payments.charge** đến queue charge; **payments.refund** đến queue refund. Routing key **payments.charge.priority** không khớp binding **payments.charge**, vì direct exchange không hiểu ký tự đại diện kiểu topic.

~~~mermaid
flowchart LR
    P["Publisher"] --> X["Direct exchange<br/>operations.direct"]
    X -->|"payments.charge"| A["payments.charge.q"]
    X -->|"payments.refund"| B["payments.refund.q"]
~~~

Nếu hai queue cùng bind vào direct exchange với **cùng binding key**, một publish khớp có thể được route tới cả hai queue. Direct exchange **không có nghĩa** chỉ được có một queue nhận.

### 3.2. Topic exchange: định tuyến bằng pattern

Topic exchange hữu ích với event có nhiều loại. **Routing key** thường gồm những từ được ngăn cách bằng dấu chấm:

~~~text
orders.created
orders.cancelled
orders.created.priority
payments.refunded
~~~

Trong **binding key của topic exchange**:

- **\*** khớp **đúng một từ**.
- **#** khớp **không hoặc nhiều từ**.
- Dấu **.** phân tách các từ.

Ví dụ:

| Binding key | orders.created | orders.cancelled | orders.created.priority | payments.refunded |
| --- | :---: | :---: | :---: | :---: |
| **orders.created** | Có | Không | Không | Không |
| **orders.\*** | Có | Có | Không | Không |
| **orders.#** | Có | Có | Có | Không |
| **#.created** | Có | Không | Không | Không |
| **payments.#** | Không | Không | Không | Có |
| **#** | Có | Có | Có | Có |

Chú ý: binding **orders.\*** không khớp **orders.created.priority** vì có ba từ. Ngược lại **orders.#** khớp cả **orders.created** lẫn **orders.created.priority**.

Ví dụ kiến trúc:

~~~mermaid
flowchart TD
    P["Publisher"] --> X["Topic exchange<br/>commerce.events"]
    X -->|"orders.created"| W["warehouse.orders.q"]
    X -->|"orders.#"| A["analytics.orders.q"]
    X -->|"payments.#"| F["finance.payments.q"]
~~~

Một sự kiện **orders.created** đến cả warehouse và analytics. **orders.cancelled** chỉ tới analytics theo ba bindings trên; **payments.refunded** chỉ tới finance.

**\*** và **#** có ý nghĩa đặc biệt ở **binding pattern của topic exchange**, không phải biểu thức cần nhét vào routing key của producer. Với direct exchange, các ký tự này không tạo hành vi wildcard tương tự.

### 3.3. Fanout exchange: bỏ qua routing key

Fanout exchange chuyển bản publish đến các queue được bind, bất kể routing key:

~~~mermaid
flowchart TD
    P["Publisher"] --> X["Fanout exchange<br/>system.notifications"]
    X --> Q1["email.notifications.q"]
    X --> Q2["mobile.notifications.q"]
    X --> Q3["audit.notifications.q"]
~~~

Phù hợp khi **mọi hệ thống đã đăng ký** cần nhận cùng một loại thông báo. Không đồng nghĩa mọi user hoặc mọi consumer đang chạy sẽ nhận được cùng một bản tin: message vẫn đến **queue**, sau đó các consumer cùng một queue có thể chia delivery.

### 3.4. Headers exchange: định tuyến theo properties

Headers exchange xem xét một tập message headers và điều kiện bindings, thường có lựa chọn tương đương **x-match = all** hoặc **x-match = any**:

- **all:** yêu cầu các điều kiện header chỉ định đều khớp.
- **any:** chỉ cần ít nhất một điều kiện header chỉ định khớp.

Ví dụ minh họa: queue xử lý hóa đơn được bind theo **documentType=invoice** và **region=apac**. Để dùng đúng, phải xác định cách producer chuyển headers thành AMQP properties, kiểu dữ liệu header và quyền truy cập. Không nên chọn headers exchange chỉ vì Spring Message có nhiều headers: đa số header nội bộ không tự đi ra broker.

### 3.5. Default exchange: trường hợp đặc biệt

RabbitMQ có **default direct exchange**, tên exchange là **chuỗi rỗng**. Mỗi queue thông thường được RabbitMQ tự bind vào default exchange bằng routing key đúng bằng **tên queue**.

~~~java
rabbitTemplate.convertAndSend(
    "", "orders.created.q", "evt-1001|O-1001");
~~~

Lời gọi trên gửi qua default exchange và định tuyến theo tên queue. Đây là lý do đôi khi nhìn code chỉ có queue name nhưng publish vẫn thành công. Tuy nhiên:

- Đây vẫn là **publish đến exchange** (tên rỗng), không phải API gửi trực tiếp vào Queue object.
- Không đem mô hình default exchange áp dụng cho exchange có tên khác.
- Khi cần routing nhiều đích, thường nên dùng named direct/topic/fanout exchange với bindings rõ ràng.
- Đừng cố thay đổi các binding mặc định bằng cách coi default exchange là exchange ứng dụng sở hữu như những exchange có tên.

## 4. Queue properties và độ bền topology

Việc tạo queue quyết định nhiều đặc điểm của đường nhận message:

| Thuộc tính | Ý nghĩa | Điểm cần cân nhắc |
| --- | --- | --- |
| **name** | Định danh queue trong virtual host | Tên ổn định, không nhầm với routing key |
| **durable** | Queue tiếp tục tồn tại qua broker restart theo cơ chế hỗ trợ | Chưa bảo đảm từng message đã persistent |
| **exclusive** | Queue gắn với connection sở hữu, không cho connection khác dùng theo quy tắc broker | Hữu ích cho queue tạm của client, không phù hợp queue dùng chung |
| **autoDelete** | Queue bị xóa khi điều kiện auto-delete của broker thỏa | Không dùng bừa cho queue cần giữ backlog lâu |
| **arguments/policy** | TTL, DLX, max length, queue type và hành vi đặc biệt | Cần phối hợp với đội vận hành |
| **queue type** | Classic/quorum hoặc loại được broker hỗ trợ | Ảnh hưởng tính sẵn sàng, độ bền và chi phí |

**Durable queue không tự làm message persistent**. Độ tin cậy còn phụ thuộc delivery mode của message, kiểu queue, policy broker, publisher confirms, consumer acknowledgment và cách xử lý trùng ở tầng nghiệp vụ.

### 4.1. Quorum queue hay classic queue?

RabbitMQ có nhiều loại queue với các bảo đảm, hiệu năng và hạn chế khác nhau. **Quorum queue** dùng thiết kế replication dựa trên quorum, thường được cân nhắc khi cần mức chịu lỗi node phù hợp; classic queue có đặc tính quản lý và tải khác. Chọn theo hạ tầng, kích thước cụm, SLA, retention, throughput và khuyến nghị phiên bản RabbitMQ triển khai thực tế. Không suy diễn “quorum queue thì không bao giờ mất dữ liệu” hoặc “mọi classic queue đều không an toàn”.

### 4.2. Queue durable, exchange durable và message persistent

Xét ba lựa chọn độc lập:

1. **Durable exchange**: cấu hình tồn tại của tài nguyên định tuyến.
2. **Durable queue**: cấu hình tồn tại của tài nguyên chứa message.
3. **Persistent delivery mode**: thuộc tính bản tin hỗ trợ lưu bền theo chính sách broker/loại queue.

Ngay cả khi cả ba đều được cấu hình, vẫn cần publisher confirms và chiến lược phục hồi trước các tình huống network timeout, publisher crash và consumer side effect trùng. Không hứa **exactly-once end-to-end** dựa trên một thuộc tính queue.

## 5. Binding, topology và nhiều nhóm nhận

### 5.1. Competing consumers trên một queue

~~~text
orders.created.q
  ├── warehouse-worker-1
  └── warehouse-worker-2
~~~

Hai worker thường chia tải: mỗi delivery được giao cho một consumer tại một thời điểm theo giao thức và có thể được giao lại khi chưa ACK. Điều này phù hợp để **scale out cùng một nhóm xử lý**, không thích hợp nếu mỗi worker đại diện một hệ thống phải nhận mọi sự kiện.

### 5.2. Mỗi hệ thống một queue

~~~text
commerce.events (topic)
  ├── key orders.# --> analytics.orders.q --> Analytics
  └── key orders.created --> warehouse.orders.q --> Warehouse
~~~

Một OrderCreated được broker định tuyến vào **cả hai queue**. Mỗi queue có backlog, consumer count, retry và chính sách ACK riêng. Khi warehouse ngừng hoạt động, analytics vẫn có thể tiếp tục nhận và xử lý message thuộc queue của nó.

### 5.3. Một queue có thể nhận từ nhiều exchange

Queue có thể bind với exchange của nhiều nguồn event. Nếu thiết kế kiểu này, cần chuẩn hóa payload/schemaVersion và metadata để consumer biết message đến từ loại sự kiện nào. Đừng trộn nhiều định dạng không tương thích rồi giả định một handler có thể parse tất cả.

### 5.4. Đặt tên và ownership

Nên có quy ước thống nhất:

- Exchange name phản ánh miền hoặc nhóm routing, ví dụ **commerce.events**.
- Routing key phản ánh loại sự kiện, ví dụ **orders.created**.
- Queue name phản ánh **consumer/nhóm nhận**, ví dụ **warehouse.orders.q**.
- Dead-letter queue phản ánh nguồn và chính sách, ví dụ **warehouse.orders.dlq**.

Đây là cách đặt tên gợi ý, không phải luật RabbitMQ. Điều quan trọng là ownership rõ ràng, tránh việc producer tự ý xóa/đổi queue do dịch vụ khác sở hữu.

## 6. Hành trình một message và bốn loại kết quả

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant X as RabbitMQ exchange
    participant Q as Queue
    participant C as Consumer
    P->>X: publish(exchange, routing key, body)
    alt Binding khớp
      X->>Q: Route message
    else Không có route phù hợp
      X-->>P: Return nếu mandatory và điều kiện phù hợp
    end
    X-->>P: Publisher confirm ACK/NACK nếu bật
    Q-->>C: Delivery khi consumer nhận
    C-->>Q: Consumer ACK/NACK tùy mode
~~~

| Tín hiệu | Bên phát | Nó nói được điều gì? | Không thể kết luận |
| --- | --- | --- | --- |
| **Publisher confirm** | Broker → publisher | Broker xác nhận trạng thái publish theo cơ chế confirms | Consumer đã xử lý nghiệp vụ |
| **Publisher return** | Broker → publisher | Bản tin không route được khi mandatory/returns có hiệu lực | Handler consumer bị lỗi |
| **Consumer ACK/NACK** | Consumer → broker | Kết quả xác nhận một delivery | Caller nhận business reply |
| **Business reply/event** | Ứng dụng nhận → ứng dụng gọi | Kết quả nghiệp vụ theo hợp đồng riêng | Broker không bao giờ redeliver |

**Publish không route được** có thể vẫn nhận publisher confirm ACK vì broker đã xử lý publish, dù không có queue nào phù hợp. Muốn phát hiện trường hợp này, cần **mandatory** và **publisher returns**, hoặc cơ chế thay thế phù hợp như alternate exchange theo thiết kế.

### 6.1. Exchange không tồn tại khác không có binding

- **Exchange không tồn tại:** publish đến tên exchange không tồn tại có thể gây lỗi protocol/channel hoặc exception; không nhất thiết là một returned message.
- **Exchange có tồn tại nhưng không có route:** message có thể là **unroutable**; dùng mandatory/returns hoặc alternate exchange để không âm thầm bỏ qua.
- **Queue có tồn tại nhưng listener chưa chạy:** message có thể tiếp tục chờ trong queue; không phải lỗi định tuyến.
- **Listener chạy nhưng handler lỗi:** đó là lỗi phía consumer sau delivery, cần ACK/NACK/retry/DLQ, khác lỗi publish của producer.

### 6.2. Routing key không phải khóa idempotency

**orders.created** định nghĩa hướng xử lý sự kiện; hàng nghìn bản tin có thể cùng routing key. Để chống xử lý trùng, cần **eventId** hoặc business key ổn định. Không dùng routing key, delivery tag, Kafka offset (ở hệ khác) hay Spring MessageHeaders.ID thay khóa nghiệp vụ.

## 7. Tình huống xuyên hệ thống: OrderCreated, OrderCancelled và PaymentRefunded

Yêu cầu:

- Warehouse chỉ nhận **orders.created**.
- Analytics nhận **mọi sự kiện thuộc miền orders**.
- Finance nhận **mọi sự kiện thuộc miền payments**.
- Hệ thống có thể scale out worker của từng queue nhưng không làm mất tính độc lập giữa các nhóm.

Chọn một topic exchange **commerce.events** với bindings:

| Queue | Binding pattern | Thông điệp sẽ nhận |
| --- | --- | --- |
| warehouse.orders.q | orders.created | Chỉ orders.created |
| analytics.orders.q | orders.# | orders.created, orders.cancelled, orders.created.priority, ... |
| finance.payments.q | payments.# | payments.received, payments.refunded, ... |

**Ma trận route mong đợi:**

| Routing key publish | Warehouse | Analytics | Finance |
| --- | :---: | :---: | :---: |
| orders.created | Có | Có | Không |
| orders.cancelled | Không | Có | Không |
| orders.created.priority | Không | Có | Không |
| payments.refunded | Không | Không | Có |
| customers.created | Không | Không | Không |

Với **customers.created**, nếu không có binding khác và không có alternate exchange, message sẽ **unroutable**; nếu mandatory không bật, publisher có thể không nhận một returned message cho trường hợp này.

## 8. Khai báo topology bằng Spring AMQP

Với Spring Boot, phần AMQP thường dùng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-amqp</artifactId>
    </dependency>
</dependencies>
~~~

Nên dùng các phiên bản do **Spring Boot dependency management/BOM** tương thích quản lý, không tự trộn phiên bản Spring Integration và Spring AMQP tùy ý.

### 8.1. Java configuration: topic exchange và ba queue

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CommerceAmqpTopology {

    public static final String EXCHANGE = "commerce.events";
    public static final String WAREHOUSE = "warehouse.orders.q";
    public static final String ANALYTICS = "analytics.orders.q";
    public static final String FINANCE = "finance.payments.q";

    @Bean
    public TopicExchange commerceExchange() {
        return new TopicExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue warehouseOrdersQueue() {
        return QueueBuilder.durable(WAREHOUSE).build();
    }

    @Bean
    public Queue analyticsOrdersQueue() {
        return QueueBuilder.durable(ANALYTICS).build();
    }

    @Bean
    public Queue financePaymentsQueue() {
        return QueueBuilder.durable(FINANCE).build();
    }

    @Bean
    public Binding warehouseBinding(
            Queue warehouseOrdersQueue,
            TopicExchange commerceExchange) {
        return BindingBuilder.bind(warehouseOrdersQueue)
            .to(commerceExchange)
            .with("orders.created");
    }

    @Bean
    public Binding analyticsBinding(
            Queue analyticsOrdersQueue,
            TopicExchange commerceExchange) {
        return BindingBuilder.bind(analyticsOrdersQueue)
            .to(commerceExchange)
            .with("orders.#");
    }

    @Bean
    public Binding financeBinding(
            Queue financePaymentsQueue,
            TopicExchange commerceExchange) {
        return BindingBuilder.bind(financePaymentsQueue)
            .to(commerceExchange)
            .with("payments.#");
    }
}
~~~

Code tạo **Spring bean mô tả topology**. Việc khai báo tương ứng trên RabbitMQ broker phụ thuộc **RabbitAdmin/AmqpAdmin**, connection, quyền và auto-declaration, hoặc được hệ thống vận hành provision từ trước.

### 8.2. Exchange, queue và binding có được tạo tự động không?

Với Spring Boot/Spring AMQP, **RabbitAdmin** có thể khai báo bean exchange/queue/binding trên broker nếu cơ chế đó được bật và tài khoản có đủ quyền. Nhưng:

- Việc tạo Spring bean **không bảo đảm** topology đã tồn tại trên broker.
- Ứng dụng có thể không có quyền configure vì topology do hạ tầng quản lý.
- Nếu broker có queue/exchange cùng tên nhưng thuộc tính không tương thích, RabbitMQ có thể từ chối khai báo (ví dụ lỗi **PRECONDITION_FAILED**, channel bị đóng).
- Đổi durable, type, arguments của queue đang có không nên được xem là thay đổi đơn giản chỉ cần restart ứng dụng; có thể cần migration.
- Khai báo binding không thay thế cấu hình exchange và queue ở cùng **virtual host**; topology thuộc phạm vi virtual host.

Trong môi trường production, cần chọn rõ **ai sở hữu topology**: ứng dụng tự khai báo khi được phép hay nhóm platform quản lý bằng IaC/script. Tránh cả hai bên vô tình sửa cấu hình trái nhau.

### 8.3. Vì sao cần kiểm tra topology thực?

Test đúng không chỉ kiểm tra các bean đã được tạo. Cần xác minh ở broker:

1. Exchange có tên **commerce.events**, kiểu **topic**, durable theo hợp đồng.
2. Ba queue tồn tại với properties mong muốn.
3. Ba bindings có pattern chính xác.
4. User producer có quyền publish vào exchange.
5. User consumer có quyền đọc queue tương ứng.
6. Tất cả tài nguyên nằm trong virtual host mà application thực sự kết nối.

## 9. Publish bằng RabbitTemplate: routing key được chọn ở đâu?

**RabbitTemplate** cung cấp thao tác publish qua Spring AMQP. Trong ví dụ này, một producer có thể phát các loại sự kiện khác nhau cùng vào topic exchange:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class CommerceEventPublisher {

    private final RabbitTemplate rabbitTemplate;

    public CommerceEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void orderCreated(String eventId, String orderId) {
        String payload = eventId + "|" + orderId + "|CREATED";
        rabbitTemplate.convertAndSend(
            CommerceAmqpTopology.EXCHANGE,
            "orders.created",
            payload);
    }

    public void orderCancelled(String eventId, String orderId) {
        String payload = eventId + "|" + orderId + "|CANCELLED";
        rabbitTemplate.convertAndSend(
            CommerceAmqpTopology.EXCHANGE,
            "orders.cancelled",
            payload);
    }

    public void paymentRefunded(String eventId, String paymentId) {
        String payload = eventId + "|" + paymentId + "|REFUNDED";
        rabbitTemplate.convertAndSend(
            CommerceAmqpTopology.EXCHANGE,
            "payments.refunded",
            payload);
    }
}
~~~

**Dự đoán route:**

- **orderCreated:** warehouse và analytics.
- **orderCancelled:** analytics.
- **paymentRefunded:** finance.

Trong ví dụ, payload là chuỗi đơn giản để tập trung vào routing. Production cần định nghĩa schema riêng cho OrderCreated, OrderCancelled và PaymentRefunded. Không nên gửi dữ liệu nhạy cảm hoặc dùng chuỗi tự ghép bằng dấu phân cách khi có nguy cơ dữ liệu chứa ký tự đặc biệt.

### 9.1. Routing key ở header hay ở cấu hình?

RabbitTemplate cho phép truyền routing key trực tiếp qua lời gọi **convertAndSend(exchange, routingKey, payload)**. Với Spring Integration outbound adapter, có thể cấu hình routing key **tĩnh** hoặc điều khiển theo message bằng những tùy chọn routing expression/header mà phiên bản DSL hỗ trợ.

Chọn **routing tĩnh** nếu flow phục vụ một loại event cố định. Nếu cần **routing động**:

1. Chuẩn hóa **eventType → routing key** bằng bảng ánh xạ được kiểm soát.
2. Không chấp nhận một chuỗi routing key tùy ý trực tiếp từ dữ liệu client bên ngoài.
3. Xác thực rằng các key được phép có bindings và consumer tương ứng.
4. Gắn event ID/schema version vào hợp đồng dữ liệu, không dùng routing key làm định danh sự kiện.
5. Kiểm thử trường hợp routing key bị thiếu hoặc không còn binding phù hợp.

### 9.2. MessageConverter không quyết định route

MessageConverter quyết định cách chuyển payload thành AMQP body/properties. Exchange và routing key quyết định **đi đâu**. Ví dụ cùng một JSON body có thể được publish với key **orders.created** hoặc **orders.cancelled** và đến những queue khác nhau. Consumer cần kiểm tra cả nội dung và ngữ nghĩa sự kiện, không tin mỗi routing key để bỏ qua validation.

## 10. Kết nối topology vào Spring Integration Java DSL

Một integration flow tốt tách **tạo dữ liệu nghiệp vụ** khỏi **đích AMQP**. MessageChannel chuyển message nội bộ, AMQP outbound adapter dùng RabbitTemplate publish. Ở phía nhận, AMQP inbound adapter dùng listener container nhận từ queue và đưa message vào MessageChannel.

~~~mermaid
flowchart LR
    P["OrderCreated producer"] --> OC["ordersToAmqp<br/>DirectChannel"]
    OC --> OA["AMQP outbound adapter"]
    OA --> EX["Topic exchange<br/>commerce.events"]
    EX --> WQ["warehouse.orders.q"]
    WQ --> IA["AMQP inbound adapter"]
    IA --> IC["warehouseOrders<br/>MessageChannel"]
    IC --> S["Warehouse service activator"]
~~~

### 10.1. Outbound adapter với routing key tĩnh

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class CommerceAmqpOutboundFlow {

    @Bean
    public MessageChannel ordersToAmqp() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow publishOrderCreated(RabbitTemplate rabbitTemplate) {
        return IntegrationFlow.from("ordersToAmqp")
            .handle(Amqp.outboundAdapter(rabbitTemplate)
                .exchangeName(CommerceAmqpTopology.EXCHANGE)
                .routingKey("orders.created"))
            .get();
    }
}
~~~

Ở đây, **ordersToAmqp** là tên MessageChannel, không phải tên queue. **Amqp.outboundAdapter(...)** nhận message và publish vào exchange với key orders.created. RabbitMQ mới là nơi quyết định message đến warehouse và analytics theo hai bindings đã cấu hình.

### 10.2. Producer nội bộ chỉ cần gửi Spring Message

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrderCreatedFlowPublisher {

    private final MessageChannel ordersToAmqp;

    public OrderCreatedFlowPublisher(
            @Qualifier("ordersToAmqp") MessageChannel ordersToAmqp) {
        this.ordersToAmqp = ordersToAmqp;
    }

    public void publish(String eventId, String orderId) {
        if (eventId == null
                || !eventId.matches("[A-Za-z0-9_-]{1,80}")
                || orderId == null
                || !orderId.matches("[A-Za-z0-9_-]{1,80}")) {
            throw new IllegalArgumentException(
                "EventId hoac orderId khong hop le");
        }

        String payload = eventId + "|" + orderId + "|CREATED";
        boolean sent = ordersToAmqp.send(
            MessageBuilder.withPayload(payload)
                .setHeader("businessEventId", eventId)
                .build());

        if (!sent) {
            throw new IllegalStateException(
                "Khong chuyen duoc message vao channel");
        }
    }
}
~~~

Chỉ dùng **một con đường publish** cho một sự kiện: hoặc CommerceEventPublisher gọi RabbitTemplate trực tiếp, hoặc OrderCreatedFlowPublisher gửi vào Spring Integration outbound flow. **Không gọi cả hai** cho cùng event nếu không muốn publish trùng.

Ở ví dụ này, **businessEventId** nằm trong Spring header nhằm minh họa; không giả định nó được chuyển sang AMQP properties khi chưa cấu hình header mapper. ID nghiệp vụ cũng có trong payload để bên nhận nhận diện ổn định.

**DirectChannel.send() trả về thành công không bảo đảm broker đã route tới mọi queue**, không đồng nghĩa đã nhận publisher confirm và càng không phải business ACK. Đây là điều cần xử lý bằng tracking producer, confirms/returns và đối soát nếu sự kiện quan trọng.

### 10.3. Inbound adapter ở phía Warehouse

Khi hệ thống Warehouse có AMQP inbound adapter, nó tiêu thụ **warehouse.orders.q**, không nhận trực tiếp từ topic exchange:

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class WarehouseAmqpInboundFlow {

    @Bean
    public MessageChannel warehouseOrders() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow warehouseInbound(ConnectionFactory connectionFactory) {
        return IntegrationFlow
            .from(Amqp.inboundAdapter(
                connectionFactory, CommerceAmqpTopology.WAREHOUSE))
            .channel("warehouseOrders")
            .get();
    }

    @Bean
    public IntegrationFlow inspectWarehouseOrders() {
        return IntegrationFlow.from("warehouseOrders")
            .handle(String.class, (payload, headers) -> {
                System.out.println("Warehouse received: " + payload);
                return null;
            })
            .get();
    }
}
~~~

**Hai đoạn cấu hình outbound/inbound có thể thuộc hai ứng dụng riêng**. Đây là cách trình bày hợp đồng giữa các hệ thống, không bắt buộc chúng chạy chung một JVM. Nếu đang kiểm tra số message nằm trong queue bằng công cụ pull, không khởi động consumer inbound đọc cùng queue cùng lúc; consumer có thể lấy dữ liệu trước bước kiểm tra.

Code inbound giả định converter cho payload kiểu **String** vì producer minh họa gửi String. Với JSON/bytes từ producer khác, phải kiểm tra MessageConverter và hợp đồng body thực tế trước khi ép handler nhận String.

### 10.4. Khi nào dùng gateway?

Các flow trên là một chiều. Nếu producer phải biết kết quả tính toán của dịch vụ nhận để tiếp tục trong cùng một tương tác, cần **AMQP outbound gateway** ở phía gọi và **AMQP inbound gateway** ở phía cung cấp dịch vụ, hoặc quy trình request/reply được xây riêng.

**Routing key** vẫn xác định đường đi của AMQP request, còn **reply-to/correlation** định nghĩa cách đưa response về caller. Producer confirm chỉ xác nhận ở cấp broker; không thể thay response nghiệp vụ của gateway.

## 11. Kiểm tra routing trên RabbitMQ

Để chứng minh routing hoạt động, không chỉ quan sát log “đã gửi”. Nên test với RabbitMQ trong môi trường test, kiểm tra topology thực tế, publish theo từng routing key rồi xem các queue tương ứng.

### 11.1. Ma trận test đề xuất

| Test | Exchange/routing key | Queue kỳ vọng |
| --- | --- | --- |
| OrderCreated | commerce.events / orders.created | warehouse.orders.q, analytics.orders.q |
| OrderCancelled | commerce.events / orders.cancelled | analytics.orders.q |
| Urgent OrderCreated | commerce.events / orders.created.priority | analytics.orders.q |
| PaymentRefunded | commerce.events / payments.refunded | finance.payments.q |
| Unknown event | commerce.events / customers.created | Không queue nào trong ba queue; kiểm tra unroutable |
| Exchange sai tên | commerce.missing / orders.created | Lỗi exchange không tồn tại theo cơ chế broker/client |
| Binding bị xóa | commerce.events / orders.created | Chỉ queue còn binding phù hợp nhận message |

### 11.2. Một phép kiểm tra bằng RabbitTemplate trong môi trường cô lập

Sau khi topology được provision, có thể dùng RabbitTemplate để publish rồi pull từ queue trong **một integration test không có listener đang tiêu thụ cùng queue**:

~~~java
// Test minh hoa; can rabbitTemplate duoc inject va broker test.
rabbitTemplate.convertAndSend(
    "commerce.events", "orders.created", "evt-1001|O-1001|CREATED");

Object warehouse = rabbitTemplate.receiveAndConvert(
    "warehouse.orders.q", 2000L);
Object analytics = rabbitTemplate.receiveAndConvert(
    "analytics.orders.q", 2000L);
Object finance = rabbitTemplate.receiveAndConvert(
    "finance.payments.q", 100L);

// warehouse va analytics mong doi chuoi su kien.
// finance mong doi null neu queue truoc test rong.
~~~

**receiveAndConvert** thực sự **lấy message khỏi queue** theo cơ chế RabbitTemplate; nó không phải API peek không tiêu thụ. Chỉ chạy kiểm tra này với queue test riêng, dữ liệu đã cô lập hoặc test topology được tạo/đặt tên riêng. Trong production, dùng quản trị/metrics và consumer test đúng quyền thay vì đọc mất message nghiệp vụ chỉ để kiểm tra.

### 11.3. Test nhiều consumer trên cùng queue

Nếu hai warehouse worker cùng consume **warehouse.orders.q**, mỗi worker sẽ nhận một phần delivery theo competing-consumer semantics, có thể redelivery nếu một worker không ACK. Không nên viết test yêu cầu **cả hai worker đều nhận mỗi message**.

Ngược lại, nếu muốn Analytics và Warehouse đều nhận mỗi OrderCreated, test phải gửi một event rồi kiểm chứng nội dung xuất hiện ở **hai queue riêng**, không kiểm tra hai consumer cùng queue.

### 11.4. Các lỗi cấu hình nên mô phỏng

1. **Sai routing key**: publisher không thấy route; bật returns/mandatory để quan sát rõ.
2. **Sai loại exchange**: bean topic nhưng broker đã có direct cùng tên; kiểm tra lỗi declare/precondition.
3. **Sai virtual host**: topology tồn tại ở vhost A nhưng ứng dụng kết nối vhost B.
4. **Không có quyền configure/write/read**: RabbitAdmin hoặc producer/consumer thất bại tương ứng.
5. **Mất binding giữa lúc gửi**: publish vẫn có thể được broker xử lý nhưng không tới queue đã kỳ vọng.
6. **Consumer đang dừng**: queue còn message ready, không được nhầm với lỗi routing.

## 12. Unroutable, mandatory, alternate exchange và dead-letter exchange

Ba cơ chế này dễ bị dùng lẫn, dù giải quyết các thời điểm khác nhau:

| Cơ chế | Áp dụng khi | Tác dụng chính |
| --- | --- | --- |
| **mandatory + publisher returns** | Một publish không được route tới queue phù hợp trong điều kiện return có hiệu lực | Báo cho producer rằng message không route được |
| **Alternate exchange (AE)** | Exchange gốc không route được và được cấu hình alternate exchange | Định tuyến lại bản publish chưa có route |
| **Dead-letter exchange (DLX)** | Message đã nằm trong queue và được dead-letter theo chính sách broker | Chuyển message từ queue sang đường lỗi/khác |

### 12.1. Mandatory và publisher returns

Ví dụ Spring Boot cho ứng dụng publisher:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Với cấu hình phù hợp, RabbitTemplate có thể xử lý returned message qua **ReturnsCallback** hoặc cơ chế đã tích hợp; confirms qua callback/future của **CorrelationData** nếu đang dùng correlated confirms.

Không chỉ bắt exception đồng bộ của convertAndSend rồi coi là đủ: **unroutable return và publisher confirm có thể đến bất đồng bộ**. Nên có trạng thái theo dõi publish và kiểm tra cả kết quả confirm, return và timeout.

**Đặc biệt:** publisher confirm ACK có thể được phát ngay cả khi message unroutable. ACK đó có nghĩa broker đã xử lý publish theo cơ chế confirms, không phải chứng nhận queue đích đã nhận.

### 12.2. Alternate exchange

Một **alternate exchange** được cấu hình cho exchange chính có thể nhận message mà exchange chính không thể route. Ví dụ:

~~~text
commerce.events  -- không có binding phù hợp -->
commerce.unrouted (alternate exchange)
                         |
                         v
                commerce.unrouted.q
~~~

Để thiết kế này hữu ích:

- Alternate exchange phải tồn tại và có bindings phù hợp tới queue dự phòng.
- Producer và operator phải biết message được chuyển đến đâu; không được đánh đồng việc alternate queue nhận với delivery thành công đến consumer đích dự kiến.
- Nếu alternate exchange cũng không route được, vẫn cần chính sách phù hợp cho trường hợp kết quả không rõ/không đến được queue.
- Cấu hình AE bằng exchange arguments/policy theo quy định broker; không thêm nhầm vào từng message như business field.

Nếu dùng alternate exchange, cần hiểu ảnh hưởng của nó lên quyết định báo **unroutable** cho publisher. Không mặc định một trường hợp được chuyển thành công sang alternate queue vẫn trả về mandatory return giống trường hợp broker không route được ở đâu.

### 12.3. Dead-letter exchange thuộc vòng đời message trong queue

DLX được dùng khi message trong queue bị dead-letter, ví dụ:

- Consumer reject/NACK với **requeue=false**.
- Message hết TTL theo chính sách.
- Queue vượt giới hạn độ dài theo cơ chế broker.
- Một số tình huống liên quan delivery limit của quorum queue theo cấu hình.

~~~mermaid
flowchart LR
    P["Publisher"] --> X["commerce.events"]
    X --> Q["warehouse.orders.q"]
    Q --> C["Warehouse consumer"]
    C -->|"Reject / NACK<br/>không requeue"| D["warehouse.dlx"]
    D --> DQ["warehouse.orders.dlq"]
~~~

**DLX không phải nơi tự nhận mọi bản publish thất bại từ producer.** Nếu publisher không thể kết nối, exchange không tồn tại hoặc message chưa vào queue, queue DLX của consumer không tự cứu bản publish đó. Với lỗi producer, cần outbox/retry/alert riêng.

### 12.4. Minh họa cấu hình DLX cho một queue

Ví dụ sau là **phương án thay thế** định nghĩa queue Warehouse với DLX; không thêm đồng thời hai bean Queue cùng tên/thuộc tính xung đột vào ứng dụng:

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;

// Vi du khai bao cho moi truong test / queue moi.
Queue warehouseWithDlx = QueueBuilder.durable("warehouse.orders.q")
    .deadLetterExchange("warehouse.dlx")
    .deadLetterRoutingKey("warehouse.failed")
    .build();
~~~

Phải khai báo **warehouse.dlx**, **warehouse.orders.dlq**, binding với key **warehouse.failed** và quyền tương ứng. Với topology production đã tồn tại, RabbitMQ policies thường linh hoạt hơn việc hardcode x-arguments không thể sửa tại chỗ; cần bàn kế hoạch thay đổi với đội vận hành.

Tránh **dead-letter cycle**: một message lỗi bị đưa về đúng queue ban đầu mà không có điều kiện kết thúc có thể tuần hoàn, gây tải và khó đối soát.

## 13. Độ tin cậy: routing đúng không đủ để xử lý đúng

Giả sử producer publish OrderCreated đến hai queue. Warehouse xử lý thành công, Analytics timeout rồi redeliver. Cả hai queue nhận đúng message nhưng **kết quả nghiệp vụ không giống nhau** tại một thời điểm.

Phân biệt:

1. **Routing success:** broker đưa message đến queue phù hợp.
2. **Transport acknowledgment:** publish confirm hoặc consumer ACK theo giao thức.
3. **Business completion:** service đã commit dữ liệu/hoàn thành tác vụ.
4. **End-to-end outcome:** các hệ thống liên quan đạt trạng thái nghiệp vụ mong muốn.

### 13.1. Idempotency khi consumer nhận lại

Consumer có thể nhận trùng do:

- Broker redelivery sau khi ACK chưa được gửi/ghi nhận.
- Producer retry sau khi mất publisher confirm.
- Cùng một event được phát lại từ outbox.
- Đối tác chủ động publish lại cùng sự kiện.

Vì thế nên gắn **eventId** ổn định (ví dụ **evt-1001**) và xử lý idempotent bằng unique constraint/inbox table hoặc cơ chế phù hợp. **Routing key orders.created** có thể giống nhau cho hàng triệu sự kiện, không có khả năng định danh duy nhất một nghiệp vụ.

### 13.2. Transactional outbox

Khi ghi Order vào database và publish AMQP, hai tài nguyên thường không nằm trong một transaction nguyên tử. Nếu database commit rồi tiến trình chết trước publish, event có thể mất. Nếu publish xong nhưng chưa đánh dấu đã gửi, event có thể phát lại.

Một mẫu **transactional outbox**:

~~~mermaid
flowchart LR
    S["OrderService"] --> TX["Database transaction"]
    TX --> O["Orders"]
    TX --> OB["OutboxEvent(eventId, routingKey)"]
    OB --> W["Outbox publisher worker"]
    W --> RT["RabbitTemplate / outbound adapter"]
    RT --> EX["commerce.events"]
    EX --> Q["Queue đích theo binding"]
    Q --> ID["Idempotent consumer"]
~~~

Trong transaction database, ghi cả Order và OutboxEvent. Worker publish sự kiện theo exchange/routing key đã chốt, theo dõi confirm/return/timeout và cập nhật trạng thái đã gửi khi đạt mốc xác nhận thiết kế. Consumer vẫn phải idempotent. **Outbox không tự tạo exactly-once end-to-end**; nó tăng khả năng khôi phục khi các bước sử dụng tài nguyên độc lập.

### 13.3. Bảo toàn thứ tự

RabbitMQ queue có những quy tắc về thứ tự delivery, nhưng concurrency, prefetch, nhiều consumer, retry, priority và requeue có thể làm thứ tự **xử lý nghiệp vụ** khác thứ tự publish. Nếu OrderCreated phải đến trước OrderCancelled theo từng order ID, cần kiểm tra phiên bản hoặc sequence của domain event và điều phối consumer, không chỉ giả định một topic exchange sẽ bảo toàn mọi thứ tự.

## 14. Vận hành: bảo mật, lifecycle, tải và quan sát

### 14.1. Quyền RabbitMQ theo virtual host

RabbitMQ quản lý tài nguyên trong **virtual host**. Exchange hoặc queue trùng tên ở hai vhost khác nhau không phải cùng tài nguyên.

Các quyền thường cần phân biệt:

- **Configure:** khai báo/thay đổi exchange hoặc queue và các thao tác cấu hình liên quan.
- **Write:** publish vào exchange hoặc thực hiện thao tác tương ứng.
- **Read:** consume từ queue theo quyền.

Hãy cấp quyền tối thiểu cho producer, consumer và tài khoản quản trị topology. Dùng TLS và xác minh chứng chỉ trong môi trường cần bảo mật; không đặt password vào code, log hoặc thông điệp sự kiện.

### 14.2. ConnectionFactory và vòng đời endpoint

Spring AMQP dùng **ConnectionFactory**, thường là **CachingConnectionFactory** trong ứng dụng Spring Boot, để cấp connection/channel. RabbitTemplate dùng nó để publish; inbound adapter dùng listener container để tiêu thụ queue.

- **Outbound adapter** có thể dừng nhưng RabbitTemplate/ConnectionFactory còn được các flow khác sử dụng.
- **Inbound adapter** thường message-driven, không dùng Spring Integration Poller giống File/SFTP.
- Nhiều endpoint dùng **Lifecycle/SmartLifecycle**; **isRunning()** không đồng nghĩa broker khỏe hoặc mọi message đã xử lý.
- Khi shutdown, ngừng nhận việc mới, xử lý/lưu bền công việc in-flight, sau đó đóng connection và tài nguyên theo lifecycle.

### 14.3. Tải và backlog

| Triệu chứng | Điều nên kiểm tra |
| --- | --- |
| Queue ready tăng | Consumer throughput thấp hơn publish rate, consumer down |
| Queue unacked tăng | Handler chậm, prefetch lớn, manual ACK chưa hoàn tất |
| Publish xác nhận chậm | Broker/network quá tải, connection/channel contention |
| Unroutable tăng | Routing key/binding/topology sai hoặc đích bị thay đổi |
| Requeue/redelivery cao | Poison message, transient error, crash trước ACK |
| DLQ tăng | Lỗi dữ liệu, hết retry, TTL/delivery-limit hoặc chính sách broker |
| Hai queue nhận số message khác nhau | Binding khác nhau, DLX/TTL, consumer đã xử lý, test chưa cô lập |

Không dùng **queue depth = 0** như bằng chứng rằng producer không gửi: consumer có thể đã lấy hết rất nhanh. Cũng không coi **queue depth > 0** là lỗi routing nếu có backlog do consumer chậm.

### 14.4. Bộ metric nên theo dõi

- **Publisher:** số lần publish, confirm ACK/NACK, return, timeout/UNKNOWN.
- **Broker:** connection/channel count, exchange publish/route rates, ready/unacked, consumer count.
- **Consumer:** delivery rate, ACK/NACK/requeue, thời gian xử lý và business error.
- **Nghiệp vụ:** eventId đã xử lý, event còn trong outbox, số bản trùng bị loại, trạng thái cuối của Warehouse/Analytics.
- **Bảo mật:** authentication/authorization failure, TLS errors và quyền bất thường.

Log nên có exchange, routing key, queue thuộc hợp đồng, eventId/correlation và loại lỗi; tránh in credentials hoặc payload nhạy cảm.

## 15. Những nhầm lẫn thường gặp

**“Producer publish vào queue.”** Trong AMQP 0-9-1, thao tác publish đi qua exchange; default exchange chỉ là một trường hợp đặc biệt có routing key bằng tên queue.

**“Direct exchange chỉ có thể gửi đến một queue.”** Nhiều queue có thể bind cùng một key; một publish phù hợp có thể đến nhiều queue.

**“Topic exchange dùng dấu sao trong routing key để chọn queue.”** Wildcard nằm trong **binding pattern**, không phải producer tự khai báo một routing key có ý nghĩa wildcard cho broker.

**“orders.* khớp orders.created.priority.”** Sai: dấu sao chỉ khớp đúng một từ; **orders.#** khớp nhiều cấp.

**“Một queue có nhiều consumer nghĩa là broadcast.”** Competing consumers thường chia delivery. Fan-out giữa các hệ thống cần các queue khác nhau.

**“Exchange durable thì mọi message đều an toàn.”** Phải xét queue, delivery mode, loại queue, confirms và consumer ACK/idempotency.

**“Publisher confirm ACK nghĩa là consumer đã xử lý.”** Confirm thuộc phía broker/publisher; consumer có ACK và business outcome riêng.

**“Message không có queue nhận chắc chắn làm convertAndSend ném exception.”** Unroutable có thể không tạo exception trực tiếp; cần mandatory/returns hoặc alternate exchange đúng cấu hình.

**“DLX dùng cho mọi lỗi producer.”** DLX chủ yếu xử lý message đã nằm trong queue và bị dead-letter theo chính sách; lỗi producer cần retry/outbox/alert riêng.

**“Routing key là event ID.”** Routing key là thông tin định tuyến; eventId dùng để chống trùng và truy vết nghiệp vụ.

**“Khai báo Queue bean là broker tự có queue.”** Cần RabbitAdmin/AmqpAdmin được bật, đủ quyền hoặc provision ngoài ứng dụng.

**“QueueChannel và RabbitMQ queue có cùng mức lưu bền.”** QueueChannel nội bộ mặc định thường ở bộ nhớ; RabbitMQ queue có các bảo đảm theo cấu hình broker và loại queue.

**“Dừng consumer xóa các message chưa xử lý.”** Message ready vẫn có thể chờ; in-flight/unacked phụ thuộc ACK, connection và chính sách khôi phục.

## 16. Câu hỏi tự kiểm tra

1. Queue, exchange, binding và routing key nằm ở đâu trong kiến trúc AMQP và khác nhau thế nào?
2. Tại sao producer có thể publish thành công tới exchange nhưng không có queue nhận message?
3. Khi nào direct exchange có thể đưa một publish vào hai queue?
4. Topic binding **orders.\*** có khớp **orders.created.priority** không? Còn **orders.#** thì sao?
5. Default exchange có tên là gì? Vì sao routing key có thể là tên queue?
6. Fanout exchange xử lý routing key như thế nào? Có cần mỗi consumer một queue để broadcast cho nhiều hệ thống không?
7. Headers exchange sử dụng thông tin nào để route? Vì sao không nên nhầm AMQP header với mọi Spring MessageHeader?
8. Vì sao durable queue không đủ để tuyên bố mọi message đều persistent và exactly-once?
9. Trong ví dụ CommerceAmqpTopology, sự kiện **orders.created** tới những queue nào? **orders.cancelled** thì sao?
10. Nếu ứng dụng có bean Queue nhưng RabbitMQ báo queue không tồn tại, cần kiểm tra những gì?
11. Publisher confirm, publisher return, consumer ACK và business reply khác nhau ở đâu?
12. Khi nào sử dụng alternate exchange, khi nào dùng dead-letter exchange?
13. Tại sao retry một event cần giữ nguyên eventId, thay vì dùng một routing key khác hoặc tạo ID mới?
14. Nếu cả Warehouse và Analytics phải nhận mọi OrderCreated, tại sao một queue dùng chung không đáp ứng yêu cầu?
15. Những metric nào giúp phân biệt lỗi routing, backlog do consumer chậm và poison message loop?
16. Khi đổi MessageChannel từ DirectChannel sang QueueChannel, điều gì thay đổi về poller, lưu bền và thời điểm báo thành công?
17. Nếu exchange được khai báo là direct trên broker nhưng code thay thành topic cùng tên, điều gì có thể xảy ra?
18. Làm thế nào bảo đảm dữ liệu Order trong database không bị mất event nếu tiến trình chết trước khi publish?

## Tổng kết

**Queue, exchange, binding và routing key** là bốn phần cốt lõi của đường định tuyến RabbitMQ. Producer publish **vào exchange**; exchange dựa trên **loại exchange và bindings** để xác định **queue** nhận message; consumer đọc từ queue. Direct exchange khớp chính xác, topic exchange dùng wildcard trong binding pattern, fanout bỏ qua routing key và headers exchange xét metadata. **Default exchange** cho phép định tuyến theo tên queue nhưng vẫn tuân theo mô hình publish tới exchange.

Trong Spring Integration, **AMQP outbound adapter/RabbitTemplate** nối MessageChannel với exchange; **AMQP inbound adapter/listener container** đưa delivery từ queue trở lại MessageChannel. Để hệ thống vận hành đúng, không chỉ kiểm tra routing mà còn phải quản lý **topology thực tế, quyền, message converter, publisher confirms/returns, ACK/retry/DLX, idempotency, transaction/outbox và lifecycle kết nối**. Một thiết kế topology rõ ràng giúp hệ thống kho, phân tích và những dịch vụ khác nhận đúng sự kiện, độc lập trong xử lý và phục hồi khi gặp lỗi.
