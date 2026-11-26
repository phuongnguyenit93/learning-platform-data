# Phân biệt lưu thông điệp trong queue với sao chép tới nhiều queue

Trong RabbitMQ, **queue** là nơi thông điệp chờ được tiêu thụ; **exchange** quyết định thông điệp được đưa vào queue nào. Hai cơ chế thường bị nhầm lẫn là:

- **Một queue có nhiều consumer:** nhiều tiến trình cùng lấy việc từ một hàng đợi. Với mỗi lần giao nhận thành công, một thông điệp được xử lý bởi **một** consumer trong nhóm đó.
- **Một thông điệp được định tuyến đến nhiều queue:** exchange đưa một bản sao **về mặt logic** của thông điệp vào **mỗi queue khớp binding**. Mỗi queue có vòng đời giao nhận và xác nhận riêng.

Đây là sự khác nhau giữa mô hình **chia việc (competing consumers)** và **phân phối sự kiện đến nhiều nhóm xử lý (publish/subscribe qua nhiều queue)**. Trong Spring AMQP, ta thường dùng **RabbitTemplate** để publish, **exchange/queue/binding** để thiết kế đường đi và **@RabbitListener** để tiêu thụ.

## 1. Message đi qua những thành phần nào?

Khi ứng dụng publish theo AMQP 0-9-1, luồng phổ biến là:

1. **Publisher** gửi thông điệp đến một **exchange**, kèm **routing key**.
2. Exchange xét loại exchange và các **binding** để tìm những queue đích.
3. Mỗi queue đích giữ một bản sao logic của thông điệp theo chính sách của queue đó.
4. Consumer nhận thông điệp từ queue; broker theo dõi trạng thái chưa xác nhận (**unacked**) và xử lý **ack/nack**.

~~~mermaid
flowchart LR
    P["Ứng dụng đặt hàng<br/>RabbitTemplate"] -->|"publish: order.created"| E{"Exchange<br/>demo.order.events"}
    E -->|"binding"| Q1[("Queue<br/>demo.billing.order-events")]
    E -->|"binding"| Q2[("Queue<br/>demo.analytics.order-events")]
    Q1 --> L1["Billing<br/>@RabbitListener"]
    Q2 --> L2["Analytics<br/>@RabbitListener"]
~~~

Trong sơ đồ, một sự kiện tạo đơn hàng có thể đến **cả Billing lẫn Analytics** vì mỗi chức năng có queue riêng. Điều đó không có nghĩa exchange lưu một bản sự kiện để tất cả listener cùng đọc; exchange **định tuyến tại thời điểm publish**, còn queue giữ thông điệp cho consumer của mình.

**Các thuật ngữ cần phân biệt:**

| Thành phần | Vai trò | Điều không nên hiểu nhầm |
| --- | --- | --- |
| Exchange | Quyết định các queue nhận thông điệp qua binding | Không phải kho lưu lịch sử sự kiện để consumer đọc lại tùy ý |
| Binding | Quy tắc nối exchange với queue; có thể dựa trên routing key | Không phải kết nối trực tiếp từ publisher tới consumer |
| Queue | Giữ thông điệp đang chờ hoặc đang được giao cho consumer | Không tự sao chép thông điệp cho mọi consumer cùng queue |
| Consumer | Nhận và xử lý thông điệp từ queue | Mỗi consumer không mặc nhiên nhận mọi thông điệp |
| Ack | Xác nhận một lần giao nhận đã được xử lý để broker có thể loại thông điệp khỏi queue | Không phải xác nhận rằng tất cả queue khác cũng đã xử lý xong |

## 2. Một queue, nhiều consumer: chia nhau xử lý

Giả sử có một queue **payment.jobs** chứa ba thông điệp M1, M2, M3 và ba instance xử lý thanh toán A, B, C đều subscribe queue ấy.

~~~text
Publisher -> Exchange -> [ payment.jobs: M1, M2, M3 ]
                              |       |       |
                         Consumer A   B       C
                    (cùng cạnh tranh nhận việc)
~~~

Broker có thể giao M1 cho A, M2 cho B và M3 cho C. Nếu có thêm M4, một trong ba consumer sẽ nhận M4 tùy thời điểm sẵn sàng, **prefetch**, số thông điệp chưa ack và cách broker phân phối. Không được giả định chia đều tuyệt đối hoặc round-robin trong mọi điều kiện.

Điều quan trọng:

- **Mỗi thông điệp trong queue thường chỉ được giao cho một consumer tại một thời điểm.** Tăng số listener/replica trên cùng queue chủ yếu giúp tăng năng lực xử lý.
- Nếu consumer xác nhận thành công (**ack**), thông điệp tương ứng được loại khỏi queue. Nếu consumer mất kết nối trước khi ack, broker có thể giao lại; lỗi, nack, requeue và dead-letter phụ thuộc cấu hình.
- **At-least-once** có thể dẫn đến xử lý lại cùng một thông điệp. Vì thế thao tác ghi cơ sở dữ liệu, trừ tiền hoặc gọi API cần thiết kế **idempotent** khi có khả năng redelivery.
- Một queue vẫn có thể chứa nhiều thông điệp **ready** khi chưa có consumer; các thông điệp đã được giao nhưng chưa ack nằm ở trạng thái **unacked**. Chính sách TTL, giới hạn độ dài và lỗi cũng có thể làm thông điệp rời queue.

**Ví dụ:** chạy ba bản sao của dịch vụ tạo thumbnail cùng lắng nghe queue **image.resize**. Mỗi ảnh chỉ cần một worker xử lý, vì vậy một queue chung là phù hợp. Tạo ba consumer **không** làm cùng một ảnh được resize ba lần theo chủ đích.

## 3. Một sự kiện, nhiều queue: mỗi nhóm nhận phần của mình

Giả sử một đơn hàng vừa được tạo, hai nhóm độc lập đều cần biết:

- **Billing** tạo yêu cầu thanh toán.
- **Analytics** ghi nhận số liệu bán hàng.

Ta khai báo hai queue, mỗi queue gắn vào exchange sự kiện. Khi publisher gửi **order.created:O-1001**, broker định tuyến tới hai queue:

~~~text
                         +--> [billing.order-events: O-1001] --> Billing
Publisher --> Exchange --|
                         +--> [analytics.order-events: O-1001] --> Analytics
~~~

Kết quả là có **hai bản sao logic trong hai queue**. Billing xử lý xong và ack **không làm mất** bản sao ở queue Analytics. Nếu Analytics tạm dừng, bản sao của nó có thể nằm chờ trong queue riêng, theo chính sách lưu trữ đã cấu hình.

Mỗi queue có thể có:

- Số consumer và tốc độ xử lý khác nhau.
- Lượng thông điệp tồn đọng, thời điểm ack và redelivery khác nhau.
- Retry, dead-letter exchange/dead-letter queue, TTL, giới hạn dung lượng và chính sách vận hành riêng.

**Không cần publisher tự gọi publish hai lần.** Publisher gửi một lần đến exchange; topology của broker quyết định có bao nhiêu queue nhận được.

### Bảng so sánh nhanh

| Tiêu chí | Một queue, nhiều consumer | Nhiều queue cùng nhận một sự kiện |
| --- | --- | --- |
| Mục tiêu | Chia tải một loại công việc | Cho nhiều nhóm chức năng cùng nhận sự kiện |
| Số bản sao logic sau định tuyến | Một bản sao trong queue đó | Một bản sao cho mỗi queue khớp |
| Ai xử lý một message? | Một consumer trong nhóm, khi xử lý thành công | Một consumer **trong mỗi queue** đích |
| Khi một consumer dừng | Consumer khác cùng queue có thể tiếp tục | Queue của nhóm đó vẫn có thể giữ message, các queue khác hoạt động độc lập |
| Tăng số consumer | Tăng mức song song của cùng nhóm công việc | Không tạo thêm subscriber độc lập nếu vẫn dùng queue cũ |
| Tăng số queue và binding | Tạo nhóm nhận mới | Thêm một luồng xử lý riêng; tăng chi phí lưu trữ/vận hành |
| Phù hợp | Task queue, worker pool, gửi email theo lô | Domain events, tích hợp Billing/Analytics/Notification |

**Quy tắc thiết kế:** muốn **nhiều instance cùng chia việc**, dùng chung queue; muốn **nhiều chức năng độc lập đều nhận một sự kiện**, mỗi chức năng dùng queue riêng và binding phù hợp.

## 4. Exchange nào có thể đưa message tới nhiều queue?

Không chỉ **fanout exchange** mới định tuyến một message đến nhiều queue. Cần phân biệt loại exchange với số lượng binding khớp:

| Loại exchange | Cách chọn queue | Ví dụ |
| --- | --- | --- |
| **Fanout** | Gửi tới mọi queue đang bind vào exchange; bỏ qua routing key | Một sự kiện cần gửi đến Billing và Analytics |
| **Direct** | Gửi tới mọi queue có binding key **bằng chính xác** routing key | Hai queue cùng bind key **order.created** thì cả hai đều nhận |
| **Topic** | Gửi tới mọi queue có mẫu binding khớp routing key; dấu **\*** khớp một từ và **#** khớp không hoặc nhiều từ, phân tách bởi dấu chấm | **order.created** khớp **order.\*** và **order.#** |
| **Default exchange** | Một direct exchange có tên rỗng; mỗi queue được bind ngầm theo tên queue | Gửi với routing key **billing.order-events** sẽ đến queue có tên đó |

Ví dụ đối với **direct exchange**, nếu hai queue có binding key **order.created**, một lệnh publish với routing key **order.created** vẫn có thể đưa thông điệp vào cả hai queue. Ngược lại, nếu chỉ một queue có binding khớp, chỉ queue ấy nhận.

RabbitMQ không tạo thêm nhiều bản sao logic **trong cùng một queue** chỉ vì queue đó có nhiều binding cùng khớp một message từ cùng exchange. Tuy nhiên, redelivery và publisher gửi lặp vẫn có thể khiến ứng dụng quan sát các lần xử lý trùng.

Nếu **không có queue nào khớp**, thông điệp có thể không được giữ lại và có thể bị loại bỏ, trừ khi sử dụng cơ chế như **alternate exchange** hoặc xử lý trả về thông điệp không được route (**publisher returns** với mandatory). Việc exchange tồn tại **không** đồng nghĩa mọi thông điệp publish đều được lưu lại.

## 5. Thực hành với Spring AMQP: một lần publish, hai queue

Ví dụ dùng một ứng dụng Spring Boot đã thêm dependency **spring-boot-starter-amqp** và RabbitMQ đang chạy. Toàn bộ mã bên dưới dùng chuỗi để làm payload, nhờ đó có thể tập trung vào **routing và queue** mà chưa cần cấu hình JSON converter.

Với Gradle, khai báo dependency trong ứng dụng Spring Boot:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-amqp")
}
~~~

Kết nối đến RabbitMQ cục bộ trong **application.yml**:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
~~~

Tài khoản **guest** thường chỉ được RabbitMQ cho phép kết nối từ localhost. Với môi trường khác, cung cấp user/password phù hợp thay vì dùng thông tin mẫu.

### Bước 1: Khai báo exchange, hai queue và hai binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.FanoutExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class AmqpTopology {
    public static final String EVENTS_EXCHANGE = "demo.order.events";
    public static final String BILLING_QUEUE = "demo.billing.order-events";
    public static final String ANALYTICS_QUEUE = "demo.analytics.order-events";

    @Bean
    public FanoutExchange orderEventsExchange() {
        return new FanoutExchange(EVENTS_EXCHANGE, true, false);
    }

    @Bean("billingQueue")
    public Queue billingQueue() {
        return QueueBuilder.durable(BILLING_QUEUE).build();
    }

    @Bean("analyticsQueue")
    public Queue analyticsQueue() {
        return QueueBuilder.durable(ANALYTICS_QUEUE).build();
    }

    @Bean
    public Binding billingBinding(
            @Qualifier("billingQueue") Queue queue,
            FanoutExchange orderEventsExchange) {
        return BindingBuilder.bind(queue).to(orderEventsExchange);
    }

    @Bean
    public Binding analyticsBinding(
            @Qualifier("analyticsQueue") Queue queue,
            FanoutExchange orderEventsExchange) {
        return BindingBuilder.bind(queue).to(orderEventsExchange);
    }
}
~~~

Ở đây:

- **demo.order.events** là fanout exchange. Tham số **durable=true** cho phép khai báo exchange bền qua broker restart; **autoDelete=false** không tự xóa khi không còn binding.
- **demo.billing.order-events** và **demo.analytics.order-events** là hai queue riêng biệt, được khai báo durable.
- Hai bean **Binding** nối cả hai queue vào cùng exchange. Mỗi queue có thể nhận thông điệp sau một lần publish.

Tên exchange/queue là hợp đồng giữa producer và các consumer. Trong hệ thống nhiều ứng dụng, mỗi dịch vụ có thể khai báo hoặc quản lý topology tương ứng thay vì đặt mọi listener trong cùng một ứng dụng.

### Bước 2: Publisher chỉ gửi một lần qua RabbitTemplate

~~~java
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishOrderCreated(String orderId) {
        String event = "order.created:" + orderId;

        rabbitTemplate.convertAndSend(
                AmqpTopology.EVENTS_EXCHANGE,
                "",
                event,
                message -> {
                    message.getMessageProperties()
                           .setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                    return message;
                }
        );
    }
}
~~~

Phương thức **convertAndSend(exchange, routingKey, payload, postProcessor)** gửi **một lần** đến **demo.order.events**. Routing key để chuỗi rỗng vì fanout không dùng nó để chọn queue. **PERSISTENT** yêu cầu broker lưu message theo chế độ persistent khi queue hỗ trợ; độ bền thực tế còn phụ thuộc kiểu queue, cấu hình và xác nhận từ broker.

### Bước 3: Hai listener tiêu thụ hai queue khác nhau

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class BillingOrderListener {
    @RabbitListener(queues = AmqpTopology.BILLING_QUEUE)
    public void onOrderCreated(String event) {
        System.out.println("[billing] " + event);
        // Ví dụ: tạo yêu cầu thanh toán, có chống xử lý trùng.
    }
}
~~~

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class AnalyticsOrderListener {
    @RabbitListener(queues = AmqpTopology.ANALYTICS_QUEUE)
    public void onOrderCreated(String event) {
        System.out.println("[analytics] " + event);
        // Ví dụ: cập nhật số liệu, có chống xử lý trùng.
    }
}
~~~

Để thử ngay khi ứng dụng khởi động, thêm một **CommandLineRunner** vào lớp khởi động Spring Boot:

~~~java
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    public CommandLineRunner publishExample(OrderEventPublisher publisher) {
        return args -> publisher.publishOrderCreated("O-1001");
    }
}
~~~

Khi RabbitMQ sẵn sàng, topology được khai báo và ứng dụng publish thành công, sẽ có hai dòng log tương tự (thứ tự **không được đảm bảo**):

~~~text
[billing] order.created:O-1001
[analytics] order.created:O-1001
~~~

Đó là **hai queue xử lý cùng một sự kiện**. Đừng nhầm với hai listener trên **cùng một queue**: ở trường hợp sau, thông điệp sẽ được giao cho một trong các consumer cạnh tranh của queue đó.

### Bước 4: Kiểm chứng sự khác biệt

1. **Giữ hai queue:** publish sự kiện **O-1002**. Mỗi queue nhận một bản sao logic, do đó Billing và Analytics đều có thể xử lý.
2. **Thêm một instance Analytics dùng cùng tên queue:** publish nhiều sự kiện. Hai instance Analytics chia nhau các thông điệp của **demo.analytics.order-events**; mỗi sự kiện không mặc nhiên chạy ở cả hai instance.
3. **Dừng riêng consumer Billing nhưng giữ queue và binding:** tiếp tục publish. Những message hợp lệ vẫn có thể đợi ở queue Billing; Analytics tiếp tục xử lý ở queue riêng. Khi Billing chạy lại, nó xử lý phần đang chờ, trừ các message đã hết TTL hoặc bị loại bỏ bởi chính sách khác.
4. **Bỏ binding Analytics:** các lần publish **mới** sẽ không còn được fanout exchange định tuyến đến queue Analytics. Điều này không tự xóa thông điệp cũ đang có trong queue.

Trên giao diện RabbitMQ Management, quan sát từng queue qua các chỉ số **Ready**, **Unacked** và **Total**, cùng phần **Bindings** để xem exchange nào đang route đến queue nào. Độ dài queue và số message unacked có thể thay đổi nhanh trong lúc consumer xử lý.

## 6. Xác nhận, lưu trữ và retry diễn ra ở cấp nào?

Phân phối tới nhiều queue chỉ giải quyết câu hỏi **ai có cơ hội nhận sự kiện**. Nó không tự bảo đảm sự kiện được xử lý thành công đúng một lần.

| Cơ chế | Phạm vi | Ý nghĩa |
| --- | --- | --- |
| **Publisher confirm** | Publisher ↔ broker | Broker xác nhận đã xử lý publish theo cơ chế confirm; không chứng minh mọi consumer hoàn thành công việc |
| **Publisher return** (mandatory) | Publisher ↔ exchange/routing | Cho phép phát hiện thông điệp không được route tới queue trong trường hợp áp dụng |
| **Consumer ack/nack** | Từng lần giao nhận từ một queue | Broker biết consumer đã xử lý thành công hay cần xử lý lại/loại bỏ/dead-letter theo chính sách |
| **Durable queue + persistent message** | Lưu trữ tại broker | Cấu hình nền tảng cho việc tồn tại qua restart; vẫn cần xem xét kiểu queue, mức an toàn dữ liệu và xác nhận publish |
| **Retry / dead-letter** | Theo consumer/queue và policy | Giải quyết lỗi xử lý của từng nhóm độc lập; không tự retry các nhóm khác đã ack |
| **Idempotency** | Logic nghiệp vụ ở consumer | Chống tác dụng phụ khi một sự kiện được giao lại hoặc publish trùng |

Trong chế độ **AUTO acknowledge** thường dùng với Spring AMQP listener container, khi phương thức listener trả về thành công thì container thực hiện ack; khi ném ngoại lệ, hành vi requeue/reject, retry hay dead-letter phụ thuộc cấu hình và loại ngoại lệ. **AUTO** ở đây khác với chế độ AMQP **autoAck/no-ack**: Spring vẫn điều phối xác nhận sau khi listener xử lý.

Ví dụ: Billing xử lý thành công rồi ack, còn Analytics gặp lỗi và được redelivery. Sự kiện có thể được xử lý **nhiều lần tại Analytics** nhưng Billing **không tự nhận lại** chỉ vì Analytics lỗi. Hai queue có trạng thái độc lập. Dù mỗi queue nhận một bản sao, chúng không tạo thành giao dịch nguyên tử xuyên các hệ thống đích.

**Lưu ý về thứ tự và lịch sử:** hai queue có thể xử lý cùng một sự kiện ở các thời điểm khác nhau; không nên suy luận có thứ tự hoàn tất toàn cục. Queue thông thường cũng không đóng vai trò event log cho subscriber mới: một queue được tạo/bind **sau khi** thông điệp đã publish sẽ không tự nhận lại các thông điệp lịch sử.

## 7. Các nhầm lẫn thường gặp

**“Tôi khai báo hai @RabbitListener cùng nghe queue X, sao mỗi listener không thấy đủ mọi message?”** Vì hai listener thuộc cùng nhóm consumer cạnh tranh trên queue X. Nếu hai tính năng cần xử lý độc lập, dùng hai queue khác nhau cùng được route từ exchange.

**“Tôi chỉ dùng direct exchange, vậy không thể gửi tới nhiều queue?”** Có thể. Nếu nhiều queue cùng có binding key khớp routing key, direct exchange đưa message vào tất cả queue đó. Fanout chỉ giúp bỏ qua điều kiện routing key.

**“Tôi gửi vào queue rồi, exchange có lưu bản dự phòng không?”** Với exchange AMQP thông thường, exchange thực hiện routing; chính queue mới giữ message. Muốn lưu bền cần thiết kế queue và message delivery mode phù hợp, kết hợp publisher confirms và giám sát.

**“Thêm queue mới hôm nay có nhận lại sự kiện ngày hôm qua?”** Không theo mặc định. Binding có hiệu lực cho các lần publish được route khi binding tồn tại, không phải cơ chế replay lịch sử.

**“Publisher confirm thành công có nghĩa cả Billing và Analytics xử lý xong?”** Không. Xử lý phía consumer cần có ack, idempotency và cơ chế theo dõi kết quả nghiệp vụ riêng.

**“Tại sao cùng một message ID xuất hiện hai lần ở cùng consumer?”** Có thể do redelivery sau mất kết nối/chưa ack hoặc do publisher gửi lại. Đừng lấy giả định “một queue chỉ có một bản sao tại thời điểm route” làm bảo đảm **exactly once** cho xử lý nghiệp vụ.

## 8. Chọn mô hình qua tình huống thực tế

| Yêu cầu | Topology phù hợp | Lý do |
| --- | --- | --- |
| 20 worker cùng xử lý danh sách email cần gửi | Một queue email.jobs, nhiều consumer | Mỗi email chỉ cần một worker nhận việc |
| Khi tạo đơn hàng, Billing, Analytics và Notification đều phải biết | Một exchange sự kiện, ba queue độc lập | Mỗi chức năng cần bản sao logic và vòng đời xử lý riêng |
| Billing cần chạy nhanh hơn khi tăng tải | Tăng số consumer của queue Billing | Tăng song song mà không tạo sự kiện bổ sung cho Billing |
| Chỉ một số nhóm nhận các sự kiện order.created, order.cancelled | Direct/topic exchange với binding thích hợp | Chọn tập queue nhận theo routing key |
| Notification có thể dừng nhưng Analytics vẫn phải chạy | Queue Notification và Analytics tách biệt | Tồn đọng/lỗi của nhóm này không buộc nhóm kia chờ |

Khi thiết kế tích hợp bất đồng bộ với **Spring AMQP và RabbitMQ**, hãy trả lời theo thứ tự: **Những nghiệp vụ nào cần nhận sự kiện?** → tạo **queue riêng cho mỗi nhóm xử lý độc lập**. **Mỗi nhóm cần bao nhiêu worker?** → tăng **consumer trên queue của nhóm đó**. Sau cùng, cấu hình exchange/binding, publisher confirms, ack, retry/dead-letter và giám sát theo mức tin cậy mà nghiệp vụ yêu cầu.

### Tự kiểm tra

1. Một exchange fanout nối với ba queue, mỗi queue có bốn consumer. Với **một lần publish**, có tối đa bao nhiêu queue nhận bản sao logic? Có bao nhiêu consumer xử lý thành công bản sao đó trên **mỗi queue** trong điều kiện không redelivery?
2. Hai queue cùng binding key **order.created** trên direct exchange. Publisher gửi routing key **order.created** một lần: queue nào nhận?
3. Nếu listener Analytics xử lý lỗi nhưng Billing đã ack, Billing có tự chạy lại hay không? Vì sao?

**Đáp án:** (1) Ba queue; thông thường một consumer trên mỗi queue xử lý thành công một bản sao. (2) Cả hai queue. (3) Không; ack và redelivery được quản lý độc lập cho từng queue.
