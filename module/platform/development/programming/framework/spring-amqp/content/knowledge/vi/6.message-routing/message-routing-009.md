# Chọn exchange, routing key và quy tắc đặt tên theo miền nghiệp vụ

Trong chương **Định tuyến thông điệp** của **SPRING_AMQP**, quyết định quan trọng nhất không phải là gọi **RabbitTemplate.convertAndSend(...)** như thế nào, mà là xác định **message phải đến nhóm xử lý nào** và **hợp đồng định tuyến có ổn định khi hệ thống phát triển hay không**. RabbitMQ định tuyến dựa trên **exchange**, **routing key** và **binding**; phía nhận dùng **@RabbitListener** để tiêu thụ message từ queue.

Bài học xây dựng một quy tắc chọn exchange, thiết kế routing key và đặt tên tài nguyên theo **miền nghiệp vụ (domain/bounded context)**. Ví dụ xuyên suốt là hệ thống thương mại điện tử: sau khi đặt hàng, dịch vụ lập hóa đơn và dịch vụ phân tích cần nhận sự kiện độc lập. Những quyết định này tạo nền tảng để triển khai retry, dead-letter, xác nhận giao nhận và khả năng quan sát của một hệ thống bất đồng bộ đáng tin cậy.

## 1. Tư duy đúng về định tuyến message

~~~mermaid
flowchart LR
    P["Order Service<br/>RabbitTemplate"] -->|"routing key:<br/>order.placed.v1"| E{"Topic exchange<br/>commerce.orders.events"}
    E -->|"binding:<br/>order.placed.v1"| BQ[("billing.order-placed.q")]
    E -->|"binding:<br/>order.*.v1"| AQ[("analytics.orders.q")]
    BQ --> B["Billing Service<br/>@RabbitListener"]
    AQ --> A["Analytics Service<br/>@RabbitListener"]
~~~

Đọc sơ đồ từ trái qua phải:

1. **Producer** phát một message đến exchange **commerce.orders.events** cùng routing key **order.placed.v1**.
2. **Topic exchange** đối chiếu routing key với các binding.
3. Cả **order.placed.v1** và **order.*.v1** đều khớp, nên hai queue đều nhận message.
4. Mỗi nhóm dịch vụ tiêu thụ từ **queue riêng**. Nếu Billing chạy ba instance cùng nghe **billing.order-placed.q**, ba instance này **chia việc trên cùng queue**; chúng không nhận ba bản sao của cùng message.

**Exchange quyết định message được đưa đến queue nào; consumer lấy message từ queue.** Producer không trực tiếp chọn consumer, và routing key không phải tên một phương thức Java hay địa chỉ của một instance.

Một message có thể được **route đến nhiều queue** nếu nhiều binding khớp. Nếu cùng một queue có nhiều binding cùng khớp, RabbitMQ không tạo nhiều bản sao của message đó trong cùng queue chỉ vì có nhiều binding phù hợp.

## 2. Chọn loại exchange theo mục đích nghiệp vụ

RabbitMQ cung cấp bốn loại exchange AMQP 0-9-1 phổ biến, ngoài **default exchange** đặc biệt.

| Exchange | Cơ chế định tuyến | Khi phù hợp | Ví dụ |
|---|---|---|---|
| **Direct** | Routing key phải khớp chính xác binding key | Gửi công việc theo loại lệnh, nhóm xử lý đã xác định | **invoice.generate** |
| **Topic** | So khớp routing key theo các segment ngăn bởi dấu chấm và wildcard | Sự kiện theo miền, cần lọc nhiều nhóm sự kiện | **order.placed.v1**, **order.*.v1** |
| **Fanout** | Bỏ qua routing key, gửi đến mọi queue được bind | Thông báo broadcast, không cần lọc theo key | Thông báo làm mới cache |
| **Headers** | Dựa vào các header và điều kiện **x-match** | Lọc theo nhiều thuộc tính header | Loại tài liệu + vùng xử lý |
| **Default exchange** | Direct exchange tên rỗng **""**; queue mặc định được bind theo chính tên queue | Gửi trực tiếp vào queue đã biết | Routing key **jobs.work.q** |

### 2.1. Direct: lựa chọn rõ đích theo loại công việc

Ví dụ hệ thống Billing nhận lệnh tạo hóa đơn:

~~~text
Exchange: billing.commands            (direct)
Routing key: invoice.generate          (exact match)
Queue: billing.invoice-generate.q
Binding key: invoice.generate
~~~

Producer cần gửi **lệnh (command)** đến nhóm xử lý chức năng lập hóa đơn. Direct exchange đơn giản, chính xác, tránh việc nhiều service vô tình đăng ký các wildcard quá rộng.

**Direct exchange vẫn có thể route đến nhiều queue** khi các queue đó đều được bind bằng cùng routing key. Nếu nghiệp vụ cần *một công việc chỉ được một worker xử lý*, hãy đặt nhiều worker nghe **một queue chung**; không suy ra tính “một consumer” chỉ từ direct exchange.

### 2.2. Topic: lựa chọn phổ biến cho sự kiện nghiệp vụ

Ví dụ **commerce.orders.events** chứa các sự kiện thuộc miền đơn hàng:

~~~text
order.placed.v1
order.paid.v1
order.cancelled.v1
~~~

Các service khác nhau có thể đăng ký:

- Billing: **order.placed.v1** để lập hóa đơn sau khi có đơn.
- Analytics: **order.*.v1** để thống kê các sự kiện order có ba segment và phiên bản v1.
- Audit: **order.#** nếu thực sự cần mọi sự kiện có tiền tố order và chấp nhận thêm loại/phiên bản mới.

Topic exchange thích hợp khi **người phát không cần biết mọi nhóm nhận**, còn mỗi nhóm có thể quyết định quan tâm đến những loại sự kiện nào thông qua binding.

### 2.3. Fanout: broadcast không cần phân loại theo key

Ví dụ một message **catalog.cache-invalidated** cần gửi tới toàn bộ nhóm cache độc lập:

~~~mermaid
flowchart LR
    P["Publisher"] --> F{"Fanout exchange<br/>catalog.cache-broadcast"}
    F --> Q1[("web.cache-refresh.q")]
    F --> Q2[("mobile.cache-refresh.q")]
    F --> Q3[("search.cache-refresh.q")]
~~~

Fanout bỏ qua routing key do producer cung cấp. Nếu mỗi nhóm đều cần một bản sao, tạo queue riêng cho từng nhóm. Nếu chỉ cần các worker **chia tải cùng một việc**, dùng một queue với nhiều consumer thay cho nhiều queue.

### 2.4. Headers: chỉ dùng khi tiêu chí thật sự nằm ở headers

Headers exchange có thể so khớp nhiều trường như **documentType=invoice** và **region=apac**, với quy tắc **x-match=all** hoặc **x-match=any** trên binding. Đổi lại, mô hình quản trị khó nhìn bằng topic khi các nhãn nghiệp vụ đã có cấu trúc rõ ràng.

Trong đa số luồng event/command, hãy bắt đầu từ **direct** hoặc **topic**. Chỉ dùng headers khi việc định tuyến thật sự cần so khớp các header độc lập và không nên mã hóa thành routing key.

## 3. Hiểu chính xác wildcard của topic exchange

Topic routing key được chia thành các **từ (word)** bởi dấu chấm (**.**). Hai wildcard dành cho **binding key** là:

- **\***: khớp **đúng một** từ.
- **#**: khớp **không hoặc nhiều** từ.

Ví dụ các binding:

| Binding key | Khớp | Không khớp |
|---|---|---|
| **order.placed.v1** | **order.placed.v1** | **order.paid.v1** |
| **order.*.v1** | **order.placed.v1**, **order.paid.v1** | **order.placed.v2**, **order.placed.apac.v1** |
| **order.#** | **order.placed.v1**, **order.paid.v2**, **order** | **payment.paid.v1** |
| **#.v1** | **order.placed.v1**, **payment.paid.v1** | **order.placed.v2** |
| `order.placed.*` | **order.placed.v1**, **order.placed.v2** | **order.paid.v1**, **order.placed.apac.v1** |

Ví dụ, binding `order.placed.*` chấp nhận cả `order.placed.v1` và `order.placed.v2`, nhưng không khớp `order.placed.apac.v1`.

**Wildcard thuộc về binding của topic exchange.** Producer nên gửi routing key mang giá trị nghiệp vụ **cụ thể**, ví dụ **order.placed.v1**, không publish một key tổng quát có ký tự **#** hoặc **\*** để “gửi cho nhiều nơi”. Với direct exchange, các ký tự **\*** và **#** không mang ý nghĩa wildcard.

### 3.1. Cùng một key, các queue nhận message khác nhau

Giả sử có ba queue:

~~~text
billing.order-placed.q   <- order.placed.v1
analytics.orders.q       <- order.*.v1
audit.orders.q           <- order.#
~~~

| Routing key khi publish | Billing | Analytics | Audit |
|---|:---:|:---:|:---:|
| **order.placed.v1** | ✓ | ✓ | ✓ |
| **order.paid.v1** | — | ✓ | ✓ |
| **order.placed.v2** | — | — | ✓ |
| **order.cancelled.v1** | — | ✓ | ✓ |
| **order.placed.v1.priority** | — | — | ✓ |
| **payment.paid.v1** | — | — | — |

Vì vậy, binding **order.#** rất linh hoạt nhưng cũng rộng: queue sẽ nhận cả các loại message chưa từng được dự kiến khi thiết kế consumer. Hãy dùng wildcard có chủ đích, đánh giá khả năng xử lý schema mới trước khi mở rộng.

## 4. Đặt tên theo bounded context thay vì theo máy chủ

Trong hệ thống nhiều service, tên tài nguyên trở thành **hợp đồng giao tiếp** giữa producer, consumer, đội vận hành và pipeline triển khai. Một quy tắc nhất quán giúp đọc topology, phân quyền và truy tìm lỗi nhanh hơn.

### 4.1. Quy tắc đặt tên đề xuất

| Thành phần | Quy tắc gợi ý | Ví dụ | Lý do |
|---|---|---|---|
| **Exchange sự kiện** | **domain.aggregate.events** | **commerce.orders.events** | Producer công bố sự kiện của miền đơn hàng |
| **Exchange lệnh** | **domain.commands** hoặc **service.commands** | **billing.commands** | Phân biệt intent điều khiển với event |
| **Routing key event** | **entity.past-action.version** | **order.placed.v1** | Biểu đạt sự kiện đã xảy ra |
| **Routing key command** | **entity.verb** | **invoice.generate** | Biểu đạt yêu cầu cần thực hiện |
| **Queue của consumer** | **consumer.purpose.q** | **billing.order-placed.q** | Queue thuộc nhóm nhận, có thể đổi số worker |
| **Dead-letter exchange** | **consumer.dlx** | **billing.dlx** | Gắn ownership cho luồng xử lý lỗi |
| **Dead-letter queue** | **consumer.purpose.dlq** | **billing.order-placed.dlq** | Dễ tìm message lỗi theo consumer |

Đây là **quy ước thiết kế**, không phải cú pháp RabbitMQ bắt buộc. Khi tổ chức đã có quy ước khác, ưu tiên tính nhất quán hơn việc đổi tên đồng loạt.

Một số nguyên tắc quan trọng:

1. **Tên gắn với vai trò nghiệp vụ**, không gắn với tên pod, địa chỉ IP, số instance hay thread. Các instance cùng một nhóm xử lý phải nghe **cùng queue** nếu mục tiêu là chia việc.
2. **Queue thuộc consumer**: Billing và Analytics cần hai queue vì chúng có nhu cầu xử lý, tốc độ, retry và DLQ độc lập.
3. **Exchange thuộc domain phát**: Order Service có thể công bố sự kiện trên **commerce.orders.events** mà không cần biết những consumer nào sẽ xuất hiện trong tương lai.
4. **Không nhúng dữ liệu cá nhân, token, số thẻ hoặc mã bí mật** vào tên exchange/queue/routing key. Topology, metrics và log có thể hiển thị những tên này.
5. **Tránh ID biến thiên theo từng message trong routing key** nếu không cần phân vùng/định tuyến theo ID; ví dụ **order.placed.ord-123456** tạo nhiều key khó quản trị và không phù hợp binding ổn định.
6. **Phân biệt môi trường** bằng vhost/cluster, namespace hoặc quy tắc triển khai rõ ràng; không để ứng dụng local vô tình trỏ vào exchange production.

### 4.2. Đặt tên sự kiện từ góc nhìn “đã xảy ra”

Một event nêu **sự thật nghiệp vụ đã xảy ra**:

~~~text
order.placed.v1
payment.authorized.v1
shipment.dispatched.v1
~~~

Một command nêu **yêu cầu cần làm**:

~~~text
invoice.generate
shipment.schedule
payment.capture
~~~

Việc phân biệt này giúp consumer hiểu ranh giới trách nhiệm: với event, service phát không ra lệnh cho tất cả subscriber phải làm cùng một việc; với command, người gửi mong đợi một nhóm phụ trách thực hiện một hành động.

**Không nên đặt key quá chung** như **process**, **created**, **doWork**. Chúng dễ trùng giữa các miền và làm người vận hành khó biết message đại diện cho điều gì.

### 4.3. Có luôn cần đặt phiên bản trong routing key?

**Không.** Hai chiến lược đều hợp lệ:

| Chiến lược | Ví dụ | Nên chọn khi |
|---|---|---|
| Version trong routing key | **order.placed.v1**, **order.placed.v2** | Consumer cần chọn rõ phiên bản ở tầng routing |
| Key ổn định, version trong message | **order.placed** và header/payload **schemaVersion=2** | Các thay đổi tương thích, không muốn cập nhật binding mỗi lần đổi schema |

Nếu dùng version trong key, hãy tính đến wildcard **order.*.v1** và **order.#** khi ra mắt v2. Nếu dùng version trong payload, consumer vẫn phải kiểm tra schema. **Đổi tên routing key không thay thế được thiết kế tương thích dữ liệu**.

Với thay đổi phá vỡ tương thích, nên phối hợp hỗ trợ song song, triển khai consumer trước/sau theo kế hoạch và chỉ loại bỏ đường cũ khi đã xử lý hết message còn tồn.

## 5. Mẫu thiết kế sự kiện “một publisher, nhiều bounded context”

Giả sử Order Service phát **OrderPlaced**. Billing phải lập hóa đơn, Analytics phải ghi nhận dữ liệu, và sau này Search có thể cần đồng bộ tìm kiếm.

~~~mermaid
flowchart TB
    O["Order Service<br/>publish: order.placed.v1"] --> X{"commerce.orders.events<br/>topic"}
    X -->|"order.placed.v1"| BQ[("billing.order-placed.q")]
    X -->|"order.*.v1"| AQ[("analytics.orders.q")]
    X -->|"order.placed.v1"| SQ[("search.order-placed.q")]
    BQ --> BW["Billing workers"]
    AQ --> AW["Analytics workers"]
    SQ --> SW["Search workers"]
~~~

Khi thêm Search, chỉ cần tạo queue mới và binding thích hợp. **Producer không cần thêm lời gọi gửi riêng cho Search**, vì exchange định tuyến dựa trên binding của các queue.

Đây là khác biệt so với cách publisher gọi trực tiếp ba HTTP endpoint: producer có thể tách khỏi sự hiện diện tức thời của các consumer, trong khi mỗi consumer tự quản lý backlog, xác nhận giao nhận, retry và DLQ của mình.

Tuy nhiên, producer vẫn phải có hợp đồng rõ ràng về nội dung và schema event. RabbitMQ không tự bảo đảm một message luôn được tất cả consumer xử lý thành công; những điều đó còn phụ thuộc độ bền queue/message, publisher confirm, ACK và chính sách retry.

## 6. Ví dụ Spring Boot và Spring AMQP có thể thực hành

### 6.1. Dependency và kết nối RabbitMQ

Với ứng dụng Spring Boot dùng Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Ví dụ cấu hình local của RabbitMQ đã có vhost và tài khoản thích hợp:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    virtual-host: app_dev
    username: learn_amqp
    password: local-demo-only
~~~

Đổi các giá trị phù hợp với broker thực tế. Mật khẩu trong ví dụ chỉ minh họa; ứng dụng triển khai nên nhận secret qua biến môi trường hoặc secret manager.

### 6.2. Khai báo TopicExchange, Queue và Binding

~~~java
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableRabbit
public class OrderRoutingTopology {
    public static final String EVENTS = "commerce.orders.events";
    public static final String PLACED_KEY = "order.placed.v1";

    public static final String BILLING_QUEUE = "billing.order-placed.q";
    public static final String ANALYTICS_QUEUE = "analytics.orders.q";

    @Bean
    public Declarables orderRoutingDeclarables() {
        TopicExchange events = new TopicExchange(EVENTS, true, false);

        Queue billing = QueueBuilder.durable(BILLING_QUEUE).build();
        Queue analytics = QueueBuilder.durable(ANALYTICS_QUEUE).build();

        return new Declarables(
                events,
                billing,
                analytics,
                BindingBuilder.bind(billing)
                        .to(events)
                        .with(PLACED_KEY),
                BindingBuilder.bind(analytics)
                        .to(events)
                        .with("order.*.v1")
        );
    }
}
~~~

Ý nghĩa:

- **TopicExchange** cho phép routing key có cấu trúc dấu chấm và binding pattern.
- **durable=true** giúp exchange/queue tồn tại sau khi broker khởi động lại; để bảo vệ message khi broker gặp sự cố, còn phải cân nhắc persistent message, publisher confirm và chính sách an toàn dữ liệu.
- **billing.order-placed.q** chỉ nhận **order.placed.v1** theo binding trong ví dụ.
- **analytics.orders.q** có thể nhận mọi message dạng **order.<một-từ>.v1**, chẳng hạn **order.paid.v1**, nếu được publish trên cùng exchange.
- Trong cấu hình Spring Boot thông dụng, **RabbitAdmin** có thể khai báo các bean này trên RabbitMQ khi kết nối được thiết lập.

Trong môi trường thực, Billing và Analytics thường là **hai ứng dụng khác nhau**. Chúng có thể quản lý queue riêng và các binding tương ứng qua provisioning. Ví dụ gom topology vào một cấu hình để dễ học, không ép các microservice phải dùng chung một repository.

### 6.3. Publish bằng RabbitTemplate

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishOrderPlaced(String orderId) {
        rabbitTemplate.convertAndSend(
                OrderRoutingTopology.EVENTS,
                OrderRoutingTopology.PLACED_KEY,
                orderId
        );
    }
}
~~~

**convertAndSend(exchange, routingKey, payload)** dùng exchange và key để định tuyến. Payload ở đây là **String orderId** cho bài thực hành; trong hệ thống thật nên dùng event DTO/JSON có **eventId**, **orderId**, **occurredAt**, **schemaVersion**, các thuộc tính nghiệp vụ cần thiết và quy ước tuần tự hóa/giải tuần tự hóa thống nhất.

Ví dụ gọi thử bằng **ApplicationRunner**:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RoutingDemoRunner {
    @Bean
    ApplicationRunner publishDemo(OrderEventPublisher publisher) {
        return args -> publisher.publishOrderPlaced("ord-1001");
    }
}
~~~

### 6.4. Hai listener cùng nhận sự kiện qua hai queue

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class DemoOrderConsumers {
    @RabbitListener(queues = OrderRoutingTopology.BILLING_QUEUE)
    public void handleBilling(String orderId) {
        System.out.println("Billing received: " + orderId);
    }

    @RabbitListener(queues = OrderRoutingTopology.ANALYTICS_QUEUE)
    public void handleAnalytics(String orderId) {
        System.out.println("Analytics received: " + orderId);
    }
}
~~~

Sau khi khởi động ứng dụng, có thể thấy:

~~~text
Billing received: ord-1001
Analytics received: ord-1001
~~~

Hai dòng log đến từ **hai queue độc lập** nhận cùng một event. Thứ tự xuất hiện của hai dòng log không được bảo đảm. Nếu khởi chạy thêm instance cùng tiêu thụ **billing.order-placed.q**, các instance Billing sẽ **cạnh tranh xử lý từng delivery** của queue Billing.

### 6.5. Kiểm tra routing key khác

Thử thay lời gọi publish:

~~~java
rabbitTemplate.convertAndSend(
        OrderRoutingTopology.EVENTS,
        "order.paid.v1",
        "ord-1001"
);
~~~

Với những binding đã khai báo:

- **analytics.orders.q** nhận message.
- **billing.order-placed.q** không nhận message.
- Không cần thay Java listener để diễn đạt phân phối này; quy tắc nằm ở **routing key + binding**.

## 7. Điều gì xảy ra khi message không được route?

Một trong những lỗi khó phát hiện khi xây hệ thống bất đồng bộ là **exchange tồn tại, publish có vẻ thành công nhưng không queue nào nhận message**.

Giả sử producer gửi:

~~~java
rabbitTemplate.convertAndSend(
        "commerce.orders.events",
        "payment.completed.v1",
        "pay-1001"
);
~~~

Nếu không có binding tương ứng, topic exchange không tìm được queue đích. Với AMQP 0-9-1, một message **unroutable** thường bị loại bỏ nếu không có cấu hình xử lý khác, chẳng hạn mandatory return hoặc alternate exchange.

**Publisher confirm** và **publisher return** trả lời hai câu hỏi khác nhau:

| Cơ chế | Câu hỏi được trả lời | Giới hạn |
|---|---|---|
| **Publisher confirm** | Broker đã xử lý việc publish theo cơ chế confirm hay chưa? | ACK từ broker không chứng minh consumer đã nhận hoặc xử lý |
| **Mandatory return** | Message có được route vào ít nhất một queue không? | Chỉ hoạt động khi bật mandatory/return và xử lý callback phù hợp; có ngoại lệ nếu alternate exchange route được |
| **Consumer ACK** | Consumer đã xác nhận một delivery chưa? | Không thay thế publisher confirm/return |
| **Dead-letter exchange** | Message bị từ chối/expired/quá giới hạn có đi đến luồng xử lý lỗi không? | Không mặc định xử lý trường hợp initial publish không route được |

### 7.1. Bật confirm và return trong Spring Boot

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Ví dụ đăng ký callback theo **RabbitTemplate** đang sử dụng:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PublisherDiagnostics {
    @Bean
    SmartInitializingSingleton publisherCallbacks(RabbitTemplate template) {
        return () -> {
            template.setReturnsCallback(returned -> {
                System.err.printf(
                        "Unroutable message: exchange=%s, key=%s, reason=%s%n",
                        returned.getExchange(),
                        returned.getRoutingKey(),
                        returned.getReplyText()
                );
            });

            template.setConfirmCallback((correlation, ack, cause) -> {
                if (!ack) {
                    System.err.println("Publish not confirmed: " + cause);
                }
            });
        };
    }
}
~~~

Ví dụ chỉ minh họa cơ chế callback. Trong hệ thống thật cần dùng logger, correlation ID để liên kết confirm với message, cảnh báo, theo dõi và chiến lược xử lý lỗi. **RabbitTemplate chỉ có một callback mỗi loại**, nên cần tích hợp với callback đã có thay vì vô tình ghi đè trong ứng dụng lớn.

Nếu bật **alternate exchange (AE)** cho exchange chính, message không route được ở exchange ban đầu có thể được chuyển đến AE. Nếu AE route được vào queue, message không nhất thiết phát sinh mandatory return. Cần kiểm tra cả topology AE khi chẩn đoán.

**Nếu exchange hoàn toàn không tồn tại**, publish có thể gây lỗi đóng channel. Đây là nhóm lỗi khác với trường hợp exchange tồn tại nhưng không có binding phù hợp.

## 8. Cách thiết kế hợp đồng định tuyến giữa các đội

Một sự kiện được nhiều hệ thống sử dụng thường tồn tại lâu hơn phiên bản code phát ra nó. Vì vậy, cần ghi rõ **routing contract**.

Ví dụ hợp đồng tối thiểu:

| Thành phần | Giá trị đã thống nhất |
|---|---|
| Bounded context phát | **Commerce / Orders** |
| Event nghiệp vụ | **OrderPlaced** |
| Exchange | **commerce.orders.events** |
| Exchange type | **topic** |
| Routing key | **order.placed.v1** |
| Payload | Event JSON có **eventId**, **orderId**, **occurredAt**, **schemaVersion** |
| Queue Billing | **billing.order-placed.q** |
| Binding Billing | **order.placed.v1** |
| Queue Analytics | **analytics.orders.q** |
| Binding Analytics | **order.*.v1** |
| Yêu cầu độ tin cậy | Đánh giá confirms/returns, ACK, retry, DLQ, idempotency |

Khi có thay đổi, trả lời các câu hỏi:

1. **Đây là sự kiện mới, phiên bản schema mới hay chỉ đổi tên key?** Những thay đổi này có tác động khác nhau tới binding.
2. **Consumer cũ có đọc được payload mới không?** Nếu không, cần kế hoạch chuyển đổi hoặc route song song.
3. **Message chưa xử lý đang nằm trong queue nào?** Đổi exchange hoặc queue mà không tính backlog có thể làm lỡ nghiệp vụ.
4. **Ai sở hữu binding?** Nên có quy trình tạo/xóa nhất quán thay vì mỗi môi trường tự phát triển topology khác nhau.
5. **Ai nhận cảnh báo khi unroutable hoặc backlog tăng?** Tên tài nguyên và thông tin chẩn đoán phải rõ để xác định chủ sở hữu.

### 8.1. Không đổi type của exchange đã tồn tại bằng cách khai báo lại

Nếu **commerce.orders.events** đã được tạo dưới dạng **direct**, rồi ứng dụng khai báo cùng tên với **type=topic**, RabbitMQ thường từ chối vì thuộc tính exchange không tương đương (**406 PRECONDITION_FAILED**). Broker không âm thầm biến direct thành topic.

Khi cần thay đổi kiểu exchange, hãy tạo exchange mới với tên phân biệt, triển khai binding mới và di chuyển producer/consumer có kế hoạch. Đừng xóa exchange/queue đang dùng chỉ để tránh lỗi khi khởi động.

### 8.2. Không dùng routing key để thay thế phân quyền

Routing key là **thông tin định tuyến**, không phải cơ chế kiểm tra user có quyền xem dữ liệu hay không. Producer phải được cấp quyền publish, consumer cần quyền đối với queue và vhost; dữ liệu nhạy cảm còn có thể cần mã hóa hoặc kiểm soát riêng.

Nếu ứng dụng multi-tenant cần cô lập mạnh, xem xét vhost/cluster và quyền theo tenant tùy yêu cầu thay vì chỉ đặt **tenantId** vào routing key rồi tin rằng các bên sẽ không nhận nhầm.

## 9. Quan sát message đã đi đâu

Khi thấy “publish chạy nhưng consumer không nhận”, kiểm tra theo thứ tự:

~~~mermaid
flowchart TD
    A["Publisher gọi RabbitTemplate"] --> B{"Exchange có tồn tại?"}
    B -->|"Không"| C["Lỗi channel / khai báo topology"]
    B -->|"Có"| D{"Binding có khớp routing key?"}
    D -->|"Không"| E["Unroutable: return, AE hoặc bị loại bỏ"]
    D -->|"Có"| F{"Message vào queue?"}
    F -->|"Không"| G["Kiểm tra vhost, TTL, chính sách, quyền"]
    F -->|"Có"| H{"Có consumer đang hoạt động?"}
    H -->|"Không"| I["Message Ready có thể tăng"]
    H -->|"Có"| J["Kiểm tra Unacked, ACK, lỗi xử lý / retry"]
~~~

| Biểu hiện | Nơi kiểm tra đầu tiên |
|---|---|
| **404 NOT_FOUND** khi publish | Exchange có tên đúng trong vhost hiện tại không? |
| **406 PRECONDITION_FAILED** lúc khởi động | Exchange type/queue argument có mâu thuẫn với broker không? |
| Publisher confirm ACK nhưng Billing không có message | Routing key, binding, mandatory return, alternate exchange |
| Analytics nhận nhưng Billing không nhận | Billing đã bind đúng **order.placed.v1** chưa? |
| Message ở queue nhưng listener không chạy | Tên queue của @RabbitListener, consumer count, quyền read |
| Queue **Unacked** tăng | Listener đang xử lý hay bị kẹt, ACK và prefetch |
| Lặp message hoặc xử lý hai lần | Consumer redelivery, ACK sau commit, idempotency |
| DLQ tăng | Lỗi xử lý/TTL/reject; kiểm tra headers và quy tắc DLX |

Trong RabbitMQ Management UI, chọn **đúng virtual host**, mở exchange để xem **Bindings**, sau đó kiểm tra queue và các chỉ số **Ready**, **Unacked**, **Consumers**. Producer cũng nên log **exchange**, **routing key** và **message ID** để ghép với log consumer, nhưng tránh ghi payload nhạy cảm.

**Quan sát định tuyến chỉ là một phần của độ tin cậy.** Một message vào queue thành công vẫn có thể bị xử lý thất bại; cần ACK đúng thời điểm, retry hữu hạn, DLQ và nghiệp vụ idempotent.

## 10. Những lỗi thiết kế thường gặp

| Thiết kế có vấn đề | Hệ quả | Hướng cải thiện |
|---|---|---|
| Mọi event đi qua một key **events** | Consumer khó đăng ký chọn lọc | Key phản ánh loại event, chẳng hạn **order.placed.v1** |
| Mỗi consumer nhận trực tiếp bằng tên queue qua default exchange | Producer biết tên queue của từng service | Dùng domain exchange khi cần nhiều consumer độc lập |
| Dùng một queue chung cho Billing và Analytics | Chỉ một nhóm có thể nhận một message cụ thể | Mỗi nhóm xử lý độc lập dùng queue riêng |
| Dùng binding **#** cho mọi consumer | Nhận cả event ngoài hợp đồng, dễ lỗi schema | Giới hạn pattern theo nghiệp vụ thực sự hỗ trợ |
| Đặt queue theo tên pod/instance | Mỗi lần scale phát sinh queue mới, message phân tán | Đặt theo consumer group/purpose |
| Ghi ID người dùng hoặc secret vào key | Rò rỉ qua topology/log, key có nhiều giá trị | Đặt dữ liệu riêng trong payload/header phù hợp |
| Đổi routing key không thông báo consumer | Binding cũ không khớp, message unroutable | Quản lý contract và kế hoạch migration |
| Chỉ dựa vào publisher confirm | Không phát hiện đúng mọi tình huống không route | Bật mandatory return hoặc thiết kế AE và giám sát |
| Đổi exchange direct sang topic cùng tên | Lỗi thuộc tính không tương đương | Tạo exchange mới và chuyển đổi có kiểm soát |

## 11. Bài thực hành tự kiểm tra

### Bài 1 — Chọn exchange

Với ba tình huống sau, chọn loại exchange và giải thích:

1. Dịch vụ Billing nhận lệnh **invoice.generate**, chỉ một worker trong nhóm xử lý mỗi job.
2. Sau khi phát **order.placed.v1**, ba hệ thống Billing, Analytics và Search đều cần một bản sao sự kiện.
3. Một thông báo thay đổi cấu hình cache phải được gửi đến toàn bộ nhóm worker đã đăng ký.

Gợi ý: trường hợp 1 có thể dùng direct + **một queue** với nhiều consumer; trường hợp 2 phù hợp topic + **queue riêng theo nhóm**; trường hợp 3 có thể dùng fanout.

### Bài 2 — Dự đoán kết quả binding

Dùng topic exchange **commerce.orders.events**:

~~~text
Queue A <- order.placed.v1
Queue B <- order.*.v1
Queue C <- order.#
~~~

Thử gửi các key **order.placed.v1**, **order.paid.v1**, **order.placed.v2**, **order.cancelled.v1**, **payment.paid.v1**. Dự đoán queue nào nhận từng message trước khi kiểm tra bằng RabbitMQ Management UI.

### Bài 3 — Đổi naming convention

Giả sử dự án cũ có những tên:

~~~text
exchange: all
routing key: handle
queue: worker-7
~~~

Hãy thiết kế lại cho sự kiện **PaymentAuthorized** thuộc bounded context **Payments**, với consumer **Fraud** và **Accounting**. Đặt tên exchange, routing key, hai queue và binding phù hợp. Giải thích vì sao queue không nên mang tên instance **worker-7**.

### Bài 4 — Phát hiện unroutable

1. Bật **publisher-confirm-type=correlated**, **publisher-returns=true** và **template.mandatory=true**.
2. Gửi message vào **commerce.orders.events** với key không được binding nào nhận, ví dụ **payment.completed.v1**.
3. Quan sát publisher return và so sánh với publisher confirm.
4. Thêm binding phù hợp trên queue thử nghiệm rồi gửi lại.
5. Thảo luận tại sao sự kiện được route không có nghĩa nghiệp vụ consumer đã hoàn tất.

### Bài 5 — Thay đổi schema

Một event **order.placed.v1** được mở rộng bằng trường mới. Hãy đánh giá hai phương án: giữ routing key cũ và thay payload tương thích; hoặc phát **order.placed.v2** kèm binding mới. Trình bày các bước để Billing không bỏ sót message trong lúc chuyển đổi.

## 12. Tổng kết kiến thức cần nhớ

- **Exchange** xác định chiến lược định tuyến; **binding** diễn đạt điều kiện một queue nhận message; **routing key** do producer gửi để exchange so khớp.
- **Direct** phù hợp lựa chọn chính xác, **topic** phù hợp sự kiện có cấu trúc và nhiều subscriber, **fanout** phù hợp broadcast; **headers** dành cho định tuyến dựa vào tập thuộc tính.
- **Một queue với nhiều consumer** là chia việc; **nhiều queue nhận cùng event** là phát sự kiện độc lập cho nhiều nhóm.
- Routing key và tên tài nguyên nên thể hiện **bounded context, loại sự kiện/lệnh và ownership**, được quản lý như một hợp đồng liên service.
- **Topic wildcard** dùng trong binding: **\*** khớp một từ, **#** khớp không hoặc nhiều từ.
- **Publisher confirm** không thay thế **mandatory return**, và cả hai không thay thế **consumer ACK**.
- Việc đặt tên và định tuyến tốt tạo nền tảng để mở rộng **RabbitTemplate**, **@RabbitListener**, retry, DLQ, giao dịch và quan sát hệ thống bất đồng bộ bằng Spring AMQP.
