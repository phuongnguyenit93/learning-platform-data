# Khai báo thụ động, tài nguyên chưa tồn tại và lỗi không khớp thuộc tính

Trong chương **Khai báo tài nguyên** của **SPRING_AMQP**, việc kết nối được RabbitMQ mới là bước đầu. Ứng dụng còn phải bảo đảm các **exchange**, **queue** và **binding** thực sự tồn tại, đồng thời có các thuộc tính phù hợp với điều mà producer và consumer mong đợi.

Spring AMQP giúp khai báo topology qua **Queue**, **Exchange**, **Binding** và **RabbitAdmin**. Tuy nhiên, khi ứng dụng khởi động hoặc khôi phục kết nối, RabbitMQ có thể trả về lỗi nếu tài nguyên chưa được tạo hoặc đã tồn tại với cấu hình khác. Hiểu **khai báo thụ động (passive declaration)**, **khai báo chủ động (active declaration)** và cơ chế kiểm tra thuộc tính là điều cần thiết để vận hành hệ thống gửi bằng **RabbitTemplate**, nhận bằng **@RabbitListener** với hành vi có thể dự đoán.

## 1. Khai báo thụ động và chủ động khác nhau ở đâu?

Trong AMQP 0-9-1, thao tác **queue.declare** và **exchange.declare** có thể được thực hiện với chế độ **passive** hoặc **active**.

| Tiêu chí | Active declaration | Passive declaration |
|---|---|---|
| Ý định | Đảm bảo tài nguyên có cấu hình được khai báo | Kiểm tra tài nguyên đã tồn tại hay chưa |
| Khi tài nguyên chưa tồn tại | Thường tạo mới nếu có quyền | Trả lỗi **404 NOT_FOUND** và đóng channel |
| Khi tài nguyên đã tồn tại | Broker kiểm tra tính tương đương của các thuộc tính bắt buộc | Không sửa tài nguyên; thông thường chỉ kiểm tra sự tồn tại |
| Khi thuộc tính không tương đương | Có thể trả **406 PRECONDITION_FAILED** | Không dùng để xác nhận toàn bộ cấu hình |
| Trường hợp sử dụng | Tự chuẩn bị topology lúc khởi động, khai báo lần đầu | Kiểm tra hệ thống đã được provisioning; kiểm tra vận hành |

**Passive không có nghĩa là “khai báo nhưng bỏ qua lỗi”**. Nó là một phép kiểm tra tồn tại gửi đến broker. Nếu queue hoặc exchange không tồn tại, phép kiểm tra thất bại và broker đóng **channel** thực hiện phép kiểm tra.

Ngược lại, **active cũng không có nghĩa là “ghi đè cấu hình tài nguyên cũ”**. Broker không tùy ý đổi một queue durable thành non-durable, hay đổi loại exchange direct thành topic chỉ vì ứng dụng khai báo lại cùng tên.

### 1.1. Vị trí của exchange, queue và binding

~~~mermaid
flowchart LR
    P["Producer<br/>RabbitTemplate"] --> E["Exchange<br/>jobs.exchange"]
    E -->|"Binding: jobs.work"| Q["Queue<br/>jobs.work.q"]
    Q --> C["Consumer<br/>@RabbitListener"]
    A["RabbitAdmin / AMQP client"] -. "active declare" .-> E
    A -. "active declare" .-> Q
    V["Topology verifier"] -. "passive check" .-> E
    V -. "passive check" .-> Q
~~~

Exchange và queue là hai loại tài nguyên có thao tác passive declare tương ứng. **Binding không có thao tác passive declare riêng trong API AMQP 0-9-1 thông thường**. Muốn kiểm tra binding, có thể xem topology qua RabbitMQ Management UI/API hoặc công cụ quản trị; muốn kiểm tra đường đi thực tế thì thử publish và consume trên một luồng kiểm soát.

Việc **exchange tồn tại** và **queue tồn tại** chưa tự chứng minh có binding đúng routing key giữa hai tài nguyên.

## 2. Vì sao RabbitMQ đóng channel khi khai báo lỗi?

AMQP tổ chức hoạt động theo lớp kết nối và channel:

- **Connection**: kết nối TCP/AMQP giữa ứng dụng và RabbitMQ.
- **Channel**: luồng giao thức logic nằm trong connection; publish, consume và declare thường chạy trên channel.
- **Protocol exception**: broker báo vi phạm điều kiện của thao tác, thường bằng lỗi đóng channel.

~~~mermaid
flowchart TD
    A["Ứng dụng gửi declare"] --> B{"Tài nguyên tồn tại?"}
    B -->|"Không; passive=true"| C["404 NOT_FOUND<br/>Đóng channel"]
    B -->|"Không; active"| D["Tạo mới nếu có quyền"]
    B -->|"Có; passive=true"| E["Xác nhận tồn tại<br/>Không sửa cấu hình"]
    B -->|"Có; active"| F{"Thuộc tính tương đương?"}
    F -->|"Có"| G["Khai báo lại thành công"]
    F -->|"Không"| H["406 PRECONDITION_FAILED<br/>Đóng channel"]
~~~

Hai lỗi cốt lõi của bài:

| Mã AMQP | Tên lỗi | Nguyên nhân điển hình |
|---|---|---|
| **404** | **NOT_FOUND** | Passive declare queue/exchange chưa tồn tại trong vhost đang kết nối |
| **406** | **PRECONDITION_FAILED** | Active declare một tài nguyên cùng tên nhưng khác thuộc tính không được phép thay đổi |

Ngoài ra còn có lỗi **ACCESS_REFUSED** nếu tài khoản thiếu quyền thao tác, và **RESOURCE_LOCKED** khi truy cập queue exclusive thuộc connection khác. Không nên quy mọi lỗi declare về 404 hoặc 406.

**Một channel bị đóng không nhất thiết kéo theo connection hoặc cả broker bị dừng.** Tuy nhiên, channel đã đóng không thể được dùng tiếp. Spring AMQP có thể cấp channel mới cho hoạt động tiếp theo, nhưng việc thử lại cùng khai báo sai sẽ lặp lại lỗi. Nếu nhiều container cùng cố khởi động, log có thể dày đặc dù RabbitMQ vẫn đang hoạt động.

## 3. Bối cảnh thực hành: topology do hệ thống quản lý

Giả sử dịch vụ xử lý công việc dùng topology sau:

| Thành phần | Tên | Thuộc tính dự kiến |
|---|---|---|
| Direct exchange | **jobs.exchange** | durable = true, autoDelete = false |
| Queue | **jobs.work.q** | durable = true, exclusive = false, autoDelete = false |
| Binding | **jobs.exchange → jobs.work.q** | routing key = **jobs.work** |
| Virtual host | **app_dev** | Tất cả tài nguyên nằm trong cùng vhost |

Để tập trung vào khai báo tài nguyên, giả định RabbitMQ đã chạy, và Spring Boot đã kết nối được với host/port, vhost **app_dev** cùng tài khoản có quyền phù hợp.

Ví dụ thuộc tính kết nối:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    virtual-host: app_dev
    username: learn_amqp
    password: dev_only_123
~~~

Mật khẩu ở đây chỉ để minh họa môi trường local. Trong ứng dụng triển khai thực tế, cung cấp mật khẩu bằng biến môi trường hoặc secret manager.

Để sử dụng Spring AMQP trong dự án Spring Boot, cần starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

## 4. Active declaration với Queue, Exchange, Binding và RabbitAdmin

Khi ứng dụng **chịu trách nhiệm tạo topology**, cách thường dùng là khai báo các bean Spring AMQP.

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JobsTopologyConfig {
    public static final String EXCHANGE = "jobs.exchange";
    public static final String QUEUE = "jobs.work.q";
    public static final String ROUTING_KEY = "jobs.work";

    @Bean
    public Declarables jobsTopology() {
        DirectExchange exchange =
                new DirectExchange(EXCHANGE, true, false);

        Queue queue = QueueBuilder.durable(QUEUE).build();

        Binding binding = BindingBuilder.bind(queue)
                .to(exchange)
                .with(ROUTING_KEY);

        return new Declarables(exchange, queue, binding);
    }
}
~~~

**RabbitAdmin** có thể tự gửi các active declaration tương ứng khi kết nối được tạo, nếu tính năng auto-declaration đang được bật. Trong cấu hình Spring Boot thông dụng, cơ chế này được bật theo mặc định thông qua bean **AmqpAdmin/RabbitAdmin** mà Boot tạo, khi **spring.rabbitmq.dynamic** được bật.

Kết quả kỳ vọng lần đầu:

1. Exchange **jobs.exchange** chưa có → được tạo với type **direct**, durable **true**.
2. Queue **jobs.work.q** chưa có → được tạo với durable **true**.
3. Binding với routing key **jobs.work** được khai báo.
4. Producer publish qua **RabbitTemplate** và consumer nhận qua **@RabbitListener** có thể dùng cùng topology.

Trong những lần khởi động sau, **khai báo lại cùng thuộc tính** thường thành công. Đây là tính chất hữu ích của việc active declare có cấu hình tương đương.

**Lưu ý:** việc ứng dụng khai báo bean **không tự bảo đảm** RabbitAdmin đã thực sự chạy, có quyền tạo tài nguyên hoặc không xảy ra lỗi trên channel. Hãy quan sát log khởi động và trạng thái broker.

### 4.1. Đừng nhầm active declaration với publish

~~~java
rabbitTemplate.convertAndSend(
        "jobs.exchange",
        "jobs.work",
        "job-123"
);
~~~

Lệnh trên **publish message**; nó **không tự khai báo** exchange, queue hoặc binding. Nếu exchange không tồn tại, broker có thể đóng channel với lỗi **404 NOT_FOUND**. Nếu exchange tồn tại nhưng không có binding phù hợp, message có thể không được route đến queue; khi đó cần xem cơ chế mandatory return và publisher confirm, không kết luận từ việc publish không ném lỗi.

## 5. Passive declaration: kiểm tra mà không tạo tài nguyên

Khi đội vận hành hoặc hệ thống provisioning quản lý topology, ứng dụng có thể cần kiểm tra trước rằng những tài nguyên cần thiết **đã có sẵn**.

Java client của RabbitMQ có các phương thức:

- **Channel.queueDeclarePassive(queueName)**
- **Channel.exchangeDeclarePassive(exchangeName)**

Spring AMQP cho phép sử dụng các phương thức đó qua **RabbitTemplate.execute(ChannelCallback)**.

~~~java
import com.rabbitmq.client.AMQP;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class JobsTopologyProbe {
    private final RabbitTemplate rabbitTemplate;

    public JobsTopologyProbe(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void requireExchange() {
        rabbitTemplate.execute(channel -> {
            channel.exchangeDeclarePassive("jobs.exchange");
            return null;
        });
    }

    public QueueSnapshot requireQueue() {
        return rabbitTemplate.execute(channel -> {
            AMQP.Queue.DeclareOk result =
                    channel.queueDeclarePassive("jobs.work.q");
            return new QueueSnapshot(
                    result.getMessageCount(),
                    result.getConsumerCount()
            );
        });
    }

    public record QueueSnapshot(
            int readyMessages,
            int consumerCount
    ) {}
}
~~~

Trong ví dụ này:

- **exchangeDeclarePassive** xác nhận tên exchange hiện có; nó **không trả về** type, durable hay các argument để so sánh.
- **queueDeclarePassive** trả về thông tin **số message sẵn sàng giao** và **số consumer** tại thời điểm kiểm tra. Các con số này là một ảnh chụp tức thời, không thay thế metrics giám sát.
- Hai phép kiểm tra được gọi qua **hai lần RabbitTemplate.execute riêng biệt**. Nếu phép thứ nhất gặp 404 và channel bị đóng, chương trình sẽ báo lỗi thay vì cố dùng lại channel hỏng.
- Nếu queue hoặc exchange không tồn tại, Spring AMQP ném lỗi liên quan đến thao tác RabbitMQ. Mã 404 cụ thể có thể nằm trong nguyên nhân gốc hoặc log, tùy phiên bản thư viện và đường đi exception.

Có thể gọi bộ kiểm tra trong quá trình khởi động để phát hiện sai topology sớm:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JobsTopologyPreflight {
    @Bean
    ApplicationRunner verifyRequiredTopology(
            JobsTopologyProbe probe
    ) {
        return args -> {
            probe.requireExchange();
            JobsTopologyProbe.QueueSnapshot snapshot =
                    probe.requireQueue();

            System.out.printf(
                    "Queue exists: ready=%d, consumers=%d%n",
                    snapshot.readyMessages(),
                    snapshot.consumerCount()
            );
        };
    }
}
~~~

**Điểm mấu chốt của thử nghiệm:** nếu **RabbitAdmin** đang tự tạo exchange và queue trong cùng ứng dụng, topology có thể đã được tạo **trước khi passive probe chạy**. Khi đó probe không còn chứng minh “tài nguyên được provisioning sẵn”.

Để kiểm tra tồn tại một cách độc lập, dùng một ứng dụng/profile **chỉ có JobsTopologyProbe và JobsTopologyPreflight**, **không đăng ký JobsTopologyConfig**, đồng thời tắt việc tạo RabbitAdmin tự động của Spring Boot:

~~~yaml
spring:
  rabbitmq:
    dynamic: false
~~~

Thuộc tính **spring.rabbitmq.dynamic=false** ngăn Spring Boot tự tạo bean AmqpAdmin. Nếu dự án tự tạo RabbitAdmin hoặc listener có cơ chế khai báo/khôi phục riêng, cũng cần kiểm tra chúng để tránh việc topology bị tạo ngoài ý muốn.

**Không dùng passive declaration để xác thực durable, autoDelete, queue type, DLX hoặc đầy đủ binding.** Để bảo đảm những thuộc tính đó, cần so sánh qua API quản trị/topology thực tế hoặc quản lý chủ động một định nghĩa được kiểm soát phiên bản.

## 6. Lỗi 404 NOT_FOUND: tài nguyên chưa tồn tại

Giả sử ứng dụng gọi:

~~~java
rabbitTemplate.execute(channel -> {
    channel.queueDeclarePassive("jobs.work.q");
    return null;
});
~~~

Nhưng **jobs.work.q** chưa được tạo trong vhost **app_dev**. Một thông báo lỗi minh họa của RabbitMQ:

~~~text
channel.close:
  reply-code=404
  reply-text=NOT_FOUND - no queue 'jobs.work.q' in vhost 'app_dev'
~~~

Tình huống tương tự xảy ra với **exchangeDeclarePassive** khi exchange chưa tồn tại.

Các nguyên nhân phổ biến:

- Đội provisioning chưa tạo tài nguyên.
- Ứng dụng nối **sai virtual host**. Tài nguyên cùng tên trong **/** không đồng nghĩa tồn tại trong **app_dev**.
- Tên queue/exchange bị sai chính tả, khác hoa/thường hoặc thay đổi theo profile.
- Queue auto-delete/exclusive đã biến mất sau khi consumer/connection trước đó kết thúc, tùy điều kiện lifecycle.
- Tài nguyên đã bị xóa trong quá trình vận hành hoặc triển khai.

### Cách xử lý

1. Xác nhận **host, port, vhost và username** thực sự được Spring Boot sử dụng.
2. Kiểm tra danh sách exchange/queue trong **đúng vhost** qua Management UI hoặc RabbitMQ CLI.
3. Xác định ai chịu trách nhiệm tạo topology: ứng dụng, hạ tầng hoặc quy trình migration.
4. Nếu ứng dụng sở hữu topology, active declare với cấu hình chuẩn và quyền thích hợp.
5. Nếu hạ tầng sở hữu topology, sửa bước provisioning và chỉ khởi động consumer khi tài nguyên đã sẵn sàng.

**Không mặc định chuyển mọi passive declare sang active chỉ để 404 biến mất.** Nếu thiếu queue là lỗi triển khai, tự tạo queue mới với cấu hình thiếu DLX, TTL hoặc queue type có thể khiến dữ liệu được định tuyến vào một tài nguyên sai hợp đồng.

### 6.1. Khi @RabbitListener gặp queue không tồn tại

~~~java
@RabbitListener(queues = "jobs.work.q")
public void receive(String jobId) {
    // Xử lý công việc
}
~~~

Listener container phải có một queue phù hợp để bắt đầu nhận message. Khi queue chưa tồn tại, Spring AMQP có thể thử khai báo/khôi phục hoặc lặp lại việc kết nối và consume tùy loại container, cấu hình **missingQueuesFatal**, RabbitAdmin và cơ chế recovery. Không nên suy đoán nguyên nhân chỉ từ việc listener không nhận message.

Kiểm tra log khởi động, vhost, tên queue, tình trạng RabbitAdmin và tài nguyên trên broker. Nếu tổ chức yêu cầu queue tồn tại từ trước, nên kiểm tra riêng ở giai đoạn deployment/preflight và bảo đảm quá trình khai báo không tình cờ tạo mới queue.

## 7. Lỗi 406 PRECONDITION_FAILED: cùng tên, khác thuộc tính

Ví dụ: RabbitMQ đang có queue **jobs.work.q** với **durable=true**. Một phiên bản ứng dụng khác lại active declare cùng queue với **durable=false**:

~~~java
@Bean
public Queue incompatibleQueue() {
    return new Queue("jobs.work.q", false);
}
~~~

Lệnh khai báo sẽ bị từ chối. Một thông báo minh họa:

~~~text
channel.close:
  reply-code=406
  reply-text=PRECONDITION_FAILED -
    inequivalent arg 'durable' for queue 'jobs.work.q' in vhost 'app_dev':
    received 'false' but current is 'true'
~~~

Điểm cần hiểu:

- **Tên queue đã tồn tại**, nhưng active declaration mới không tương đương với định nghĩa hiện có.
- RabbitMQ **không âm thầm chuyển** queue durable thành non-durable.
- Channel thực hiện declare bị đóng; RabbitAdmin hoặc listener container có thể báo lỗi khi khởi động.
- **Passive check có thể vẫn thành công**, vì nó chỉ kiểm tra queue tồn tại, không so sánh durable.

### 7.1. Những thuộc tính dễ xung đột

| Tài nguyên | Thuộc tính có thể gây lỗi khi khai báo lại | Ví dụ |
|---|---|---|
| Queue | **durable** | Broker true, code false |
| Queue | **autoDelete** | Broker false, code true |
| Queue | **exclusive** | Khai báo khác cách truy cập/tính sở hữu queue |
| Queue | **x-queue-type** | Code muốn **quorum**, queue đang là **classic** |
| Queue | **x-max-priority**, một số **x-arguments** | Khai báo có cấu hình khác hiện tại |
| Exchange | **type** | Broker **direct**, code **topic** |
| Exchange | **durable**, **autoDelete**, một số argument | Broker và code khai báo không tương đương |

Quy tắc kiểm tra tính tương đương có các chi tiết theo phiên bản RabbitMQ, queue type, chính sách và loại argument. Vì vậy, khi thấy **406**, phải đọc chính **reply-text** và so với cấu hình hiện tại, không suy ra toàn bộ khác biệt chỉ từ mã lỗi.

Một số argument được cấu hình qua **policy** hoặc **operator policy** và có quy tắc ưu tiên riêng. Việc thay đổi policy có thể làm thay đổi hành vi áp dụng mà không yêu cầu ứng dụng khai báo lại queue với argument khác; nhưng không phải thuộc tính nào cũng có thể đổi bằng policy.

### 7.2. Exchange cũng có thể gặp 406

RabbitMQ đã có **jobs.exchange** là direct exchange. Ứng dụng đổi mã thành:

~~~java
@Bean
public TopicExchange wrongExchangeType() {
    return new TopicExchange("jobs.exchange", true, false);
}
~~~

Active declare với **type=topic** đụng tài nguyên **type=direct** sẽ bị từ chối. Không thể chuyển kiểu exchange chỉ bằng cách khởi động lại Spring Boot.

### 7.3. Binding khác routing key có phải 406?

Không nhất thiết. Với nhiều loại binding thông thường, khai báo thêm một binding khác routing key sẽ **tạo thêm quan hệ định tuyến**, không tự thay thế binding cũ. Ví dụ, vẫn có thể còn binding **jobs.work** trong khi ứng dụng mới thêm binding **jobs.updated**. Hệ quả là các message được route theo cả hai quy tắc nếu chúng khớp.

Vì vậy, ngoài việc xác nhận exchange và queue tồn tại, phải kiểm tra danh sách binding để tránh định tuyến thiếu hoặc định tuyến thừa.

## 8. Chẩn đoán từng bước trên RabbitMQ và Spring AMQP

### 8.1. Tra cứu topology trong đúng vhost

Trong RabbitMQ Management UI, chọn vhost **app_dev**, mở danh sách **Exchanges**, **Queues and Streams** và kiểm tra tên, type, durable, autoDelete, arguments và bindings.

Nếu có quyền dùng RabbitMQ CLI trên node broker, những lệnh sau giúp đọc cấu hình:

~~~bash
rabbitmqctl list_vhosts
rabbitmqctl list_queues -p app_dev name durable auto_delete arguments
rabbitmqctl list_exchanges -p app_dev name type durable auto_delete arguments
rabbitmqctl list_bindings -p app_dev source_name destination_name routing_key
~~~

Đây là các lệnh **đọc thông tin**, không khai báo mới và không xóa tài nguyên. Tùy môi trường, quản trị viên có thể dùng giao diện quản trị hoặc HTTP API thay cho CLI.

### 8.2. Đối chiếu định nghĩa từ hai phía

Ví dụ bảng kiểm khi gặp lỗi 406:

| Thuộc tính | Trên broker | Trong ứng dụng | Kết quả |
|---|---|---|---|
| Queue name | jobs.work.q | jobs.work.q | Trùng |
| Virtual host | app_dev | app_dev | Trùng |
| Durable | true | false | **Không tương đương** |
| Auto-delete | false | false | Trùng |
| Queue type | classic | classic | Trùng |

Nếu queue thực tế là durable, thay lại code thành **QueueBuilder.durable("jobs.work.q")** có thể giải quyết sai khác, miễn các thuộc tính khác cũng tương đương. Ngược lại, nếu ứng dụng thực sự cần queue mới với ngữ nghĩa khác, cần **kế hoạch migration** thay vì ép broker sửa thuộc tính của queue cũ.

### 8.3. Phân biệt các nhóm sự cố

| Hiện tượng | Kiểm tra trước |
|---|---|
| **404 khi passive queue declare** | Queue có trong đúng vhost không? |
| **404 khi passive exchange declare** | Exchange có trong đúng vhost không? |
| **404 khi publish vào exchange** | Exchange có tồn tại, tên exchange có đúng không? |
| **406 khi active queue declare** | Durable, autoDelete, x-arguments, queue type |
| **406 khi active exchange declare** | Exchange type, durable, autoDelete, arguments |
| **ACCESS_REFUSED** | Quyền configure/read/write của user trên vhost |
| **RESOURCE_LOCKED** | Queue exclusive thuộc connection nào? |
| **Không nhận message dù queue tồn tại** | Binding, routing key, consumer, ACK, quyền đọc queue |

Lỗi **404/406** ở mức khai báo khác với việc listener xử lý message rồi **NACK**, **retry** hoặc đưa message vào **dead-letter queue**. Những cơ chế đó liên quan tới delivery và xử lý nghiệp vụ; chúng không sửa được một topology sai ngay từ đầu.

## 9. Điều chỉnh topology an toàn khi queue đang có dữ liệu

Một queue có thể đang chứa message **Ready** và **Unacked**, đồng thời được nhiều consumer sử dụng. Xóa queue để tạo lại đúng thuộc tính có nguy cơ **mất message**, gián đoạn worker và thay đổi định tuyến.

Quy trình thận trọng khi cần thay thuộc tính không thể cập nhật trực tiếp:

1. **Chụp hiện trạng**: tên vhost, queue/exchange, arguments, bindings, số message và consumer đang hoạt động.
2. **Xác định hợp đồng mong muốn**: queue type, durability, TTL, DLX, retry, quyền và routing key nào là chính thức.
3. **Phân loại thay đổi**: thay đổi có thể quản lý bằng policy hay buộc phải tạo tài nguyên mới?
4. **Nếu cần tài nguyên mới**, tạo queue phiên bản mới (ví dụ **jobs.work.v2.q**) với cấu hình đúng và binding phù hợp.
5. **Chuyển lưu lượng có kiểm soát**: điều chỉnh producer/binding và consumer theo kế hoạch, xử lý message còn lại trong queue cũ; xác định xử lý trùng và thứ tự khi có hai queue chạy song song.
6. **Kiểm chứng và dọn dẹp sau cùng**: chỉ gỡ queue/binding cũ khi đã xác nhận không còn message cần giữ và có phương án rollback thích hợp.

### 9.1. Khi nào dùng policy?

Các thiết lập vận hành như dead-letter exchange và một số giới hạn/TTL có thể được quản trị qua **RabbitMQ policy** tùy loại queue và phiên bản RabbitMQ. Điều này giúp đội vận hành điều chỉnh quy tắc mà không phải sửa từng ứng dụng đang khai báo queue.

Không nên hiểu policy là cách “đổi mọi thuộc tính” của queue. Ví dụ, chuyển **classic queue** đã tồn tại thành **quorum queue** không đơn giản là đặt policy rồi declare lại cùng tên.

### 9.2. Có nên bỏ qua lỗi khai báo của RabbitAdmin?

Spring AMQP hỗ trợ các tùy chọn như **ignoreDeclarationExceptions** trong RabbitAdmin/Declarable để tiếp tục xử lý một số tình huống khai báo lỗi.

Tùy chọn này **không làm queue sai thuộc tính trở thành đúng**, cũng không bảo đảm listener sẽ chạy an toàn. Nếu ứng dụng tiếp tục khi topology không khớp, producer có thể gửi sai đường hoặc consumer không đọc được queue. Chỉ dùng cơ chế bỏ qua khi đã hiểu rõ tài nguyên nào có thể thất bại và vì sao sự thất bại đó chấp nhận được.

## 10. Thực hành đối chiếu passive và active

Đây là bài thực hành có thể làm trên một RabbitMQ **dành riêng cho phát triển**, không dùng queue chứa dữ liệu quan trọng.

### Bài A: Kiểm tra một queue chưa tồn tại

1. Dùng profile kiểm tra thụ động ở mục 5, không đăng ký bean khai báo topology tự động.
2. Chọn tên queue chưa có, ví dụ **jobs.missing.check.q**.
3. Gọi **queueDeclarePassive** với tên queue này.
4. Quan sát **404 NOT_FOUND** và việc channel bị đóng.
5. Kiểm tra lại trên broker để xác nhận queue **không bị tạo mới**.

### Bài B: Tạo rồi kiểm tra thụ động

1. Kích hoạt **JobsTopologyConfig** ở mục 4 để active declare exchange, queue và binding.
2. Kiểm tra ba tài nguyên trong vhost **app_dev**.
3. Chạy lại profile passive-only của mục 5.
4. Xác nhận **exchangeDeclarePassive** và **queueDeclarePassive** thành công.
5. Quan sát số message và consumer mà **Queue.DeclareOk** trả về; giải thích vì sao các giá trị này có thể thay đổi giữa hai lần gọi.

### Bài C: Gây lỗi 406 trong môi trường thử nghiệm

1. Giữ **jobs.work.q** ở trạng thái **durable=true**.
2. Chạy một cấu hình thử nghiệm active declare cùng tên với **durable=false**.
3. Quan sát **406 PRECONDITION_FAILED**, tìm chuỗi **inequivalent arg** trong log.
4. Kiểm tra queue trên broker: queue cũ vẫn có thuộc tính durable ban đầu.
5. Sửa lại định nghĩa thành **durable=true**, khởi động lại và kiểm tra declare thành công.

**Không xóa queue để làm mất lỗi trong bước 3.** Điều cần học là RabbitMQ bảo vệ tính nhất quán của thuộc tính; ứng dụng phải khai báo đúng hợp đồng đã chọn.

### Bài D: Phân biệt tồn tại và định tuyến

1. Giữ nguyên exchange và queue đã khai báo.
2. Dùng RabbitTemplate publish đến **jobs.exchange** với routing key **jobs.unknown** khi không có binding tương ứng.
3. Xem kết quả và kiểm tra binding thực tế trên broker.
4. Bổ sung binding thích hợp và thử lại; nếu cần phát hiện unroutable message, sử dụng **mandatory return** theo cấu hình publisher.

Qua bài D, bạn sẽ thấy **passive declare thành công không chứng minh message đến được queue**.

## 11. Câu hỏi tự đánh giá

1. Passive queue declare kiểm tra được điều gì? Nó có kiểm chứng được **durable** và **x-dead-letter-exchange** không?
2. Vì sao passive declare trên queue chưa tồn tại có thể đóng **channel**, trong khi cả RabbitMQ broker và connection vẫn còn hoạt động?
3. Đã có queue durable cùng tên, ứng dụng khai báo lại non-durable. RabbitMQ trả lỗi nào? Bạn nên kiểm tra thông tin gì trước khi sửa?
4. Hai vhost khác nhau có thể cùng có queue tên **jobs.work.q** không? Passive declare trong vhost nào sẽ nhìn thấy queue đó?
5. Nếu ứng dụng vừa bật RabbitAdmin tự tạo queue vừa chạy passive preflight, kết quả preflight có chứng minh queue đã được provisioning từ trước không?
6. Khi yêu cầu đổi từ classic sang quorum queue nhưng queue cũ có nhiều message, vì sao cần thiết kế migration?
7. Khi exchange và queue đều tồn tại nhưng RabbitTemplate gửi message không tới consumer, bạn kiểm tra thêm thành phần nào?

## 12. Những điều cần nhớ

- **Passive declaration** xác nhận queue/exchange tồn tại; không tạo mới và không bảo đảm các thuộc tính trùng với cấu hình mong muốn.
- **Active declaration** có thể tạo tài nguyên còn thiếu; với tài nguyên đã tồn tại, broker kiểm tra tính tương đương thay vì ghi đè tùy ý.
- **404 NOT_FOUND** thường chỉ ra tài nguyên bị thiếu trong phép kiểm tra thụ động; **406 PRECONDITION_FAILED** thường chỉ ra khai báo lại không khớp thuộc tính.
- Lỗi giao thức có thể đóng **channel**. Không thử dùng lại channel hỏng hoặc retry vô hạn một khai báo sai.
- **RabbitAdmin** có thể tự khai báo topology trước khi ứng dụng kiểm tra. Phải xác định rõ hệ thống nào sở hữu việc provisioning.
- Khi topology đang mang dữ liệu, **kiểm tra và migration có kiểm soát** an toàn hơn việc xóa queue rồi tạo lại.
- Topology đúng là nền tảng cho **RabbitTemplate**, **@RabbitListener**, ACK, retry, dead-letter và khả năng quan sát hệ thống Spring AMQP đáng tin cậy.
