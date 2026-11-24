# AMQP inbound channel adapter

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích đường đi của một AMQP message từ **RabbitMQ exchange/binding/queue** đến **MessageChannel** trong Spring Integration.
- Phân biệt **AMQP inbound channel adapter** một chiều với **AMQP inbound gateway** có hợp đồng request–reply.
- Hiểu vai trò của **listener container**, **ConnectionFactory**, **MessageConverter**, payload, headers và channel ở ranh giới nhận dữ liệu.
- Viết một luồng **Spring Integration Java DSL** tiếp nhận message từ RabbitMQ queue và chuyển cho handler nội bộ.
- Phân tích **acknowledgment, redelivery, requeue, dead-letter, retry, idempotency, prefetch, concurrency** và các trạng thái sau khi ứng dụng khởi động lại.
- Xây dựng bộ kiểm thử và chỉ số vận hành để nhận biết lỗi kết nối, lỗi dữ liệu, backlog và message bị xử lý lặp.

## 1. Vấn đề cần giải quyết

Một hệ thống thương mại điện tử phát sự kiện **OrderCreated** khi đơn hàng được tạo. Ứng dụng Spring Boot khác cần tiếp nhận sự kiện, kiểm tra dữ liệu, rồi kích hoạt nghiệp vụ của mình. Các ứng dụng không nhất thiết chạy cùng thời điểm hoặc cùng ngôn ngữ lập trình.

RabbitMQ có thể làm trung gian: producer xuất bản AMQP message, broker định tuyến đến queue, consumer lấy message khi sẵn sàng. Trong ứng dụng nhận, **AMQP inbound channel adapter** của Spring Integration nối cơ chế nhận message từ RabbitMQ với một **MessageChannel** nội bộ. Handler phía sau channel chỉ cần biết hợp đồng payload và headers, không phải trực tiếp lập trình nhận message bằng RabbitMQ client.

~~~mermaid
flowchart LR
    P["Producer<br/>OrderCreated"] --> X["RabbitMQ Exchange<br/>orders.events"]
    X -->|"Routing key + binding"| Q["Queue<br/>orders.created.q"]
    Q --> L["Spring AMQP<br/>Listener container"]
    L --> A["AMQP inbound<br/>channel adapter"]
    A --> M["Spring Message<br/>payload + headers"]
    M --> C["MessageChannel<br/>rabbitOrders"]
    C --> H["Validator / Transformer<br/>Service activator"]
~~~

**AMQP** là giao thức/message model; **RabbitMQ** là broker được sử dụng trong ví dụ. Spring Integration AMQP tích hợp với **Spring AMQP** để sử dụng connection factory, listener container và message converter. Chọn mô hình này khi ứng dụng cần nhận thông điệp một chiều từ broker và đưa vào integration flow.

Phạm vi của inbound adapter là **broker → ứng dụng**. Không nhầm với **AMQP outbound adapter** (ứng dụng → broker) hoặc **AMQP gateway** (có request và reply).

## 2. Các thành phần cần hiểu trước khi cấu hình

RabbitMQ không chuyển message từ producer trực tiếp vào một MessageChannel của Spring. Có hai hệ thống và một lớp chuyển đổi ở giữa:

| Thành phần | Vai trò | Điều cần lưu ý |
| --- | --- | --- |
| **Exchange** | Nhận bản tin producer publish, định tuyến theo loại exchange và bindings | Producer thường publish vào exchange; exchange không phải nơi consumer trực tiếp lấy dữ liệu |
| **Routing key** | Tham gia quy tắc định tuyến của exchange | Với direct exchange, thường được đối chiếu với binding key |
| **Binding** | Liên kết exchange với queue theo quy tắc | Cấu hình sai khiến message không đến queue mong muốn |
| **Queue** | Giữ các message chờ consumer nhận theo chính sách broker | Durable queue không tự bảo đảm mọi message sống sót nếu message không persistent hoặc broker không đáp ứng bảo đảm cần thiết |
| **ConnectionFactory** | Tạo và quản lý kết nối RabbitMQ cho ứng dụng | Cần cấu hình xác thực, TLS, host, virtual host và khả năng reconnect |
| **Listener container** | Tiêu thụ delivery từ queue; điều phối concurrency và acknowledgment | Thời điểm ACK, exception, requeue và các consumer đang hoạt động phụ thuộc container |
| **Inbound channel adapter** | Chuyển AMQP delivery thành Spring Integration Message và phát vào channel | Một chiều, không chờ reply nghiệp vụ |
| **MessageConverter** | Ánh xạ giữa AMQP body/properties và payload | Kiểu payload không tự giống kiểu domain |
| **MessageChannel** | Giao message cho endpoint phía sau | DirectChannel đồng bộ; ExecutorChannel/QueueChannel có ngữ nghĩa khác |

### 2.1. Exchange, queue và binding không thể dùng thay nhau

Trong ví dụ, producer publish đến direct exchange **orders.events** với routing key **orders.created**. Queue **orders.created.q** được bind vào exchange với binding key cùng giá trị. Nếu topology được khai báo đúng, delivery sẽ vào queue để listener container tiêu thụ.

~~~mermaid
flowchart TD
    PX["Publisher"] --> EX["Direct Exchange<br/>orders.events"]
    EX -->|"orders.created"| Q1["orders.created.q"]
    EX -. "Routing key khác,<br/>không có binding phù hợp" .-> NO["Không đến queue này"]
    Q1 --> C["Consumer của ứng dụng"]
~~~

Một queue có thể được nhiều consumer cùng tiêu thụ để chia tải; điều đó **khác** với việc có nhiều queue độc lập được bind vào cùng exchange để mỗi hệ thống nhận một bản sao. Nếu cần mỗi hệ thống có luồng xử lý riêng, hãy thiết kế queue/binding phù hợp, không mặc định rằng nhiều consumer trên cùng queue đều nhận được mỗi message.

### 2.2. Spring AMQP listener khác Spring Integration poller

Inbound AMQP theo mô hình **message-driven**: listener container nhận các delivery từ RabbitMQ qua client và gọi endpoint. Thông thường **không cần Spring Integration Poller** để quét queue như cách File/SFTP/JDBC inbound adapter dùng MessageSource.

Listener container có cơ chế I/O, nhận delivery, concurrency, prefetch và acknowledgment riêng. Một Flow dùng AMQP inbound adapter vẫn trao đổi dữ liệu thông qua MessageChannel, nhưng điểm kích hoạt nguồn là **listener**, không phải **poller định kỳ** của Integration DSL.

## 3. Một message đi vào Spring Integration như thế nào?

Quá trình nhận có thể chia thành bảy bước:

1. **Producer publish** một AMQP message với body, properties, exchange và routing key.
2. **Broker định tuyến** vào queue tương ứng với binding; nếu không có route thì hành vi phụ thuộc chính sách publish, mandatory/return và cấu hình broker.
3. **Listener container** nhận delivery, kèm thông tin delivery tag, redelivery, properties và nội dung body.
4. **MessageConverter** theo cấu hình chuyển nội dung từ biểu diễn AMQP thành payload phù hợp, chẳng hạn byte array, String hoặc DTO.
5. **Inbound adapter** tạo/chuyển tiếp Spring Integration Message, ánh xạ metadata thích hợp vào headers và gửi đến output channel.
6. **MessageChannel** chuyển message cho transformer, filter, router hoặc service activator tiếp theo.
7. **Listener container** xử lý acknowledgment hoặc lỗi theo mode/configuration. Không suy ra ACK luôn xảy ra cùng lúc với bước gửi vào channel.

~~~mermaid
sequenceDiagram
    participant B as RabbitMQ queue
    participant L as Listener container
    participant A as AMQP inbound adapter
    participant C as MessageChannel
    participant H as Handler nghiệp vụ
    B-->>L: AMQP delivery
    L->>A: Gọi listener
    A->>C: Message(payload, headers)
    C->>H: Giao message
    H-->>C: Hoàn tất hoặc exception
    C-->>A: Kết thúc xử lý đồng bộ
    A-->>L: Kết thúc listener callback
    L-->>B: ACK / NACK theo mode và kết quả
~~~

Sơ đồ mô tả tình huống **DirectChannel và handler đồng bộ**. Nếu đổi sang channel bất đồng bộ, handler có thể còn chạy sau khi listener callback kết thúc. Khi đó ACK ở listener có thể đến **trước khi nghiệp vụ thực sự hoàn tất** nếu không có cơ chế phối hợp tương ứng.

## 4. Inbound adapter hay inbound gateway?

AMQP có thể hỗ trợ giao tiếp một chiều và request–reply, nhưng hai hợp đồng cần endpoint khác nhau:

| Nhu cầu | Endpoint phù hợp | Hành vi |
| --- | --- | --- |
| Nhận event OrderCreated rồi xử lý nội bộ | **AMQP inbound channel adapter** | Nhận delivery, phát message vào channel; không phát reply nghiệp vụ |
| Producer gửi yêu cầu và đợi kết quả của hệ thống xử lý | **AMQP inbound gateway** | Nhận request, đưa vào flow, nhận response và gửi reply theo hợp đồng AMQP |
| Ứng dụng publish sự kiện sang queue/topic ngoài | **AMQP outbound channel adapter** | Gửi một chiều ra broker |
| Flow gửi AMQP request rồi cần dùng kết quả trả về | **AMQP outbound gateway** | Request–reply, cần timeout và correlation |

**ACK của broker không phải reply nghiệp vụ.** Inbound adapter có thể tham gia xác nhận delivery theo Spring AMQP, nhưng producer không tự nhận được đối tượng OrderResult như một cặp request–reply. Nếu producer cần biết đơn hàng đã được duyệt hay từ chối, hãy thiết kế gateway hoặc một quy trình phản hồi bất đồng bộ có correlation ID và nơi nhận reply.

## 5. Payload và headers: hợp đồng ở biên AMQP

Một message ở broker có **body** cùng **properties/headers** AMQP. Trong Spring Integration, handler nhận **Spring Message** với **payload** và **MessageHeaders**. Có thể hình dung:

~~~text
RabbitMQ delivery
├── body: byte[] theo wire format
├── contentType, contentEncoding
├── messageId, correlationId, timestamp (nếu producer cung cấp)
├── headers / routing metadata
└── delivery metadata
           |
           v
Spring AMQP MessageConverter + header mapper
           |
           v
Spring Message<?>
├── payload: byte[] / String / DTO / ...
└── headers: metadata đã được ánh xạ theo cấu hình
~~~

Không được mặc định AMQP inbound luôn phát **String** hoặc **DTO**. Kiểu payload tùy converter và content type:

- Với converter cơ bản, body kiểu **text/plain** có thể được giải mã thành String.
- Với **application/json**, muốn có DTO thường cần JSON converter hoặc transformer phù hợp; converter mặc định không thể tự đoán mọi cấu trúc domain.
- Với payload nhị phân, có thể giữ byte array và deserialize ở bước downstream.

### 5.1. Những metadata cần cân nhắc

| Metadata | Sử dụng điển hình | Cảnh báo |
| --- | --- | --- |
| **contentType/encoding** | Xác định serializer hoặc charset của body | Header khai báo đúng chưa chắc body hợp lệ |
| **correlationId** | Ghép request/reply hoặc truy vết | Không tự là khóa idempotency nghiệp vụ |
| **messageId** | Theo dõi thông điệp do producer đặt | Có thể thiếu, không đảm bảo duy nhất theo nghiệp vụ |
| **routing key / queue** | Biết message đến từ luồng nào | Metadata cụ thể do adapter ánh xạ, không phải payload |
| **redelivered** | Dấu hiệu broker đã giao lại | Không thể dùng một mình để kết luận message chưa được xử lý |
| **delivery tag/channel** | Hỗ trợ ACK ở cấp delivery khi dùng manual mode | Không chuyển bừa tham chiếu client sang hệ thống khác |
| **eventId/orderId** | Khóa domain cho chống trùng và đối soát | Nên được xác định rõ trong hợp đồng nghiệp vụ |

Đối với nhiều sự kiện dùng chung một queue, nên có **eventType** và **schemaVersion** rõ ràng để handler có thể phân loại và xác thực. Những thông tin nghiệp vụ quan trọng có thể đặt trong payload theo hợp đồng thay vì phụ thuộc vào metadata AMQP không được mọi consumer bảo toàn.

## 6. Ví dụ Java DSL: RabbitMQ → inbound adapter → DirectChannel

Ta xây dựng ví dụ tối giản để nhận một message chứa hai trường **orderId|totalVnd** từ RabbitMQ:

- Direct exchange: **orders.events**.
- Routing key: **orders.created**.
- Durable queue: **orders.created.q**.
- AMQP inbound adapter lấy delivery từ queue.
- MessageChannel nội bộ: **rabbitOrders**.
- Service handler parse String và ghi log kết quả nhận.

Đây là ví dụ **một chiều** để nhìn rõ ranh giới adapter. Handler chưa ghi database; không dùng nó làm minh chứng hoàn thành nghiệp vụ. Với Spring Boot, cần dependency **spring-boot-starter-amqp**, **spring-boot-starter-integration** và **spring-integration-amqp**, theo phiên bản được dependency management của Spring Boot kiểm soát.

### 6.1. Khai báo topology và IntegrationFlow

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
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
public class OrderAmqpInboundConfiguration {

    public static final String EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "orders.created";
    public static final String QUEUE = "orders.created.q";

    @Bean
    public DirectExchange orderExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue orderQueue() {
        return new Queue(QUEUE, true);
    }

    @Bean
    public Binding orderBinding(
            Queue orderQueue, DirectExchange orderExchange) {
        return BindingBuilder.bind(orderQueue)
            .to(orderExchange)
            .with(ROUTING_KEY);
    }

    @Bean
    public MessageChannel rabbitOrders() {
        return new DirectChannel();
    }

    // Broker delivery -> AMQP inbound adapter -> MessageChannel.
    @Bean
    public IntegrationFlow ordersInbound(ConnectionFactory connectionFactory) {
        return IntegrationFlow
            .from(Amqp.inboundAdapter(connectionFactory, QUEUE))
            .channel("rabbitOrders")
            .get();
    }

    // MessageChannel -> handler minh hoa.
    @Bean
    public IntegrationFlow inspectOrders() {
        return IntegrationFlow.from("rabbitOrders")
            .handle(String.class, (body, headers) -> {
                String[] fields = body.split("\\|", -1);
                if (fields.length != 2 || fields[0].isBlank()) {
                    throw new IllegalArgumentException(
                        "Message phai co dang orderId|totalVnd");
                }

                long totalVnd = Long.parseLong(fields[1]);
                if (totalVnd <= 0) {
                    throw new IllegalArgumentException(
                        "Tong tien phai lon hon 0");
                }

                System.out.println(
                    "Nhan don " + fields[0] + ", totalVnd=" + totalVnd);
                return null; // Endpoint mot chieu, khong co business reply.
            })
            .get();
    }
}
~~~

**Điều kiện của ví dụ:** một RabbitMQ broker phải hoạt động và ứng dụng đã cấu hình ConnectionFactory (host, port, virtual host, username/password hoặc TLS tùy môi trường). Các bean Exchange, Queue, Binding chỉ được broker khai báo tự động khi ứng dụng có **RabbitAdmin/AmqpAdmin** phù hợp, tài khoản có quyền khai báo và auto-declaration được bật. Nếu hạ tầng quản lý topology từ bên ngoài, thay đổi quy trình khai báo theo chính sách triển khai.

**Kiểu payload:** ví dụ dùng **String** vì ở bước gửi thử ta dùng RabbitTemplate.convertAndSend với payload String, được converter mặc định phát dưới dạng nội dung văn bản. Nếu producer ngoài gửi JSON hoặc bytes với content type khác, handler phải được thay bằng converter/transformer đúng hợp đồng; không cố ép mọi payload về String.

**Phạm vi production:** logger minh họa không thay thế logic idempotent, transaction hay ACK được kiểm chứng. Trong hệ thống thật, tách transformer để parse hợp đồng và service activator để xử lý nghiệp vụ; cân nhắc queue lỗi trước khi cho producer gửi dữ liệu thật.

### 6.2. Gửi message thử bằng RabbitTemplate

Từ một test tích hợp hoặc service có RabbitTemplate đã được Spring Boot cấu hình:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class OrderEventPublisher {
    private final RabbitTemplate rabbitTemplate;

    public OrderEventPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendExample() {
        rabbitTemplate.convertAndSend(
            "orders.events", "orders.created", "O-1001|150000");
    }
}
~~~

Nếu topology và converter khớp, message sẽ được định tuyến vào **orders.created.q**. Listener container chuyển delivery qua AMQP inbound adapter vào **rabbitOrders**; handler in thông tin đơn hàng.

Không nhầm hành động **convertAndSend** với việc application consumer đã hoàn thành nghiệp vụ. Nó chỉ gửi bản tin qua producer theo cơ chế của RabbitTemplate; xác nhận producer/broker phải được cấu hình và giám sát riêng nếu cần.

### 6.3. Trình tự thử nghiệm

1. Chuẩn bị RabbitMQ và cấu hình kết nối Spring AMQP bằng tài khoản có quyền phù hợp.
2. Khởi động ứng dụng; xác minh exchange, queue và binding đã có trên broker (do admin của ứng dụng hoặc công cụ triển khai tạo).
3. Gửi chuỗi **O-1001|150000** bằng phương thức sendExample.
4. Kiểm tra handler đã nhận và in dữ liệu sau khi listener nhận delivery.
5. Gửi **O-1002|90000** để xác minh một message khác cũng đến được channel.
6. Gửi dữ liệu sai như **bad-message** để quan sát đường lỗi. **Không thử liên tục trên production queue** khi chưa cấu hình retry/requeue/DLQ, vì bản lỗi có thể bị giao lại lặp.
7. Tạm dừng ứng dụng nhận rồi publish thêm message, sau đó khởi động lại. Quan sát backlog ở queue và chính sách tiêu thụ khi listener được bật lại.

## 7. Acknowledgment: thời điểm nào được coi là đã nhận?

Đây là quyết định quan trọng nhất của AMQP inbound. **Delivery được listener nhận** không đồng nghĩa **business transaction đã commit**. RabbitMQ dùng acknowledgment để biết một delivery đã được consumer xác nhận hay cần xử lý tiếp theo chính sách.

Trong Spring AMQP, thường gặp ba chế độ:

| AcknowledgeMode | Ý nghĩa | Rủi ro cần xét |
| --- | --- | --- |
| **AUTO** | Container ACK khi listener hoàn tất thành công, xử lý lỗi theo cơ chế container | Nếu listener trả về trước khi nghiệp vụ bất đồng bộ xong, ACK có thể xảy ra quá sớm |
| **MANUAL** | Ứng dụng chịu trách nhiệm ACK/NACK theo delivery tag và channel | Dễ rò rỉ unacked message nếu quên xác nhận; cần quản lý mọi nhánh lỗi |
| **NONE** | Broker tự coi message được xác nhận khi giao theo mode không yêu cầu ACK của consumer | Dễ mất cơ hội giao lại nếu consumer chết sau khi nhận mà chưa xử lý |

### 7.1. AUTO với DirectChannel đồng bộ

Ở ví dụ Java DSL, adapter gửi vào **DirectChannel** và handler được gọi ngay trong chuỗi xử lý listener. Nếu handler hoàn tất thành công, listener có thể trả về để container thực hiện ACK trong mode AUTO. Nếu handler ném lỗi và lỗi được để truyền tới container, container có thể reject/nack theo chính sách cấu hình.

Điều này **không tự bảo đảm một giao dịch nguyên tử** giữa RabbitMQ và database. Nếu handler ghi DB thành công nhưng mất kết nối trước ACK, message có thể được broker giao lại. Nên lưu khóa idempotency và có kiểm soát trùng ở lớp nghiệp vụ.

### 7.2. AUTO với ExecutorChannel bất đồng bộ

Giả sử đổi channel sau inbound adapter thành **ExecutorChannel**. Adapter có thể gửi việc cho executor rồi return ngay. Listener thấy quá trình gửi message vào channel hoàn tất, nhưng handler trên thread khác vẫn đang xử lý. Nếu container ACK tại thời điểm đó, nghiệp vụ phía sau thất bại **không còn được broker bảo đảm giao lại** thông qua ACK của delivery cũ.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant L as Listener
    participant E as ExecutorChannel
    participant H as Async handler
    B-->>L: AMQP delivery
    L->>E: send(message)
    E-->>L: Đã giao việc cho executor
    L-->>B: Có thể ACK khi callback thành công
    E->>H: Bắt đầu xử lý sau đó
    H--xE: Lỗi nghiệp vụ
    Note over B,H: ACK có thể đã xảy ra<br/>trước khi lỗi xuất hiện
~~~

Vì vậy, **đừng thay DirectChannel bằng channel bất đồng bộ chỉ để tăng throughput** nếu yêu cầu ACK gắn với kết quả xử lý nghiệp vụ. Khi cần bất đồng bộ, hãy thiết kế ranh giới lưu bền và điểm ACK riêng, hoặc dùng cơ chế manual acknowledgment được kiểm thử kỹ.

### 7.3. MANUAL: chỉ dùng khi đã kiểm soát mọi nhánh

Trong manual mode, consumer phải biết delivery tag và RabbitMQ channel phù hợp để ACK/NACK. Spring Integration/Spring AMQP có thể cung cấp metadata cần thiết qua headers khi được cấu hình; tên header và kiểu đối tượng phải đối chiếu với phiên bản thư viện thực tế. Không nên giả định handler tùy ý có thể ACK sau khi message đã tách khỏi vòng đời delivery hoặc channel đã bị đóng.

Manual ACK là công cụ cho yêu cầu đặc biệt, không phải phương án mặc định để “an toàn hơn”. Nếu quên ACK, message sẽ ở trạng thái unacked cho đến khi connection/channel đóng hoặc điều kiện khác xảy ra; throughput có thể bị giới hạn bởi prefetch.

## 8. Retry, requeue và dead-letter

Một AMQP message có thể lỗi vì nhiều lý do:

- **Lỗi tạm thời:** database timeout, dịch vụ downstream chậm, kết nối ngắt.
- **Lỗi dữ liệu:** JSON không hợp lệ, field thiếu, schema sai, business ID không hợp lệ.
- **Lỗi hạ tầng:** không đủ quyền truy cập, consumer không sẵn sàng hoặc cấu hình kết nối sai.
- **Trạng thái không rõ:** side effect đã diễn ra nhưng ACK chưa tới broker.

Không nên xử lý mọi lỗi bằng cách **requeue vô hạn**.

### 8.1. Phân biệt retry và requeue

| Cơ chế | Điều xảy ra | Khi phù hợp |
| --- | --- | --- |
| **Retry trong listener** | Thử lại xử lý cùng delivery theo policy/backoff | Lỗi tạm thời có thể hồi phục nhanh |
| **NACK/reject với requeue** | Broker đưa message về queue để giao lại theo chính sách | Khi có lý do kỳ vọng lần nhận sau sẽ thành công |
| **Reject không requeue** | Delivery bị từ chối; nếu có DLX phù hợp thì có thể đến dead-letter queue | Dữ liệu sai vĩnh viễn hoặc hết retry |
| **DLQ/DLX** | Hệ thống cô lập message thất bại để điều tra/xử lý sau | Tránh một poison message làm ảnh hưởng toàn bộ luồng |

Trong nhiều cấu hình Spring AMQP, exception từ listener ở mode AUTO có thể dẫn đến requeue mặc định. Nếu dữ liệu chắc chắn sai, broker có thể giao lại liên tục và chiếm tài nguyên. Hãy cấu hình **retry giới hạn**, cách **reject không requeue**, dead-letter exchange/queue và quy trình xử lý riêng.

**DLQ không phải tính năng tự xuất hiện chỉ vì ném exception.** Cần định nghĩa dead-letter routing, queue/binding phù hợp và chính sách reject của listener. Cũng cần kiểm tra TTL, giới hạn kích thước và vòng đời dữ liệu ở DLQ.

~~~mermaid
flowchart TD
    Q["orders.created.q"] --> L["AMQP inbound adapter"]
    L --> V{"Kiểm tra và xử lý"}
    V -->|"Thành công"| ACK["ACK theo cấu hình"]
    V -->|"Lỗi tạm thời"| R["Retry có giới hạn + backoff"]
    R --> V
    V -->|"Lỗi vĩnh viễn hoặc hết retry"| N["Reject/NACK không requeue"]
    N --> DX["Dead-letter exchange<br/>nếu được cấu hình"]
    DX --> DQ["orders.created.dlq"]
~~~

### 8.2. Idempotency là điều kiện bắt buộc khi có redelivery

Nếu consumer đã lưu đơn hàng O-1001 rồi tiến trình bị ngắt trước khi ACK, broker có thể giao lại cùng sự kiện. Consumer phải tránh tạo bản ghi trùng:

1. Tạo **eventId** hoặc dùng **partnerId + orderId** ổn định theo hợp đồng.
2. Dùng unique constraint/checkpoint hoặc inbox table phù hợp để đánh dấu đã xử lý.
3. Bao việc ghi nghiệp vụ và đánh dấu idempotency trong transaction dữ liệu khi có thể.
4. Chỉ ACK khi đạt được mức hoàn tất đã cam kết, theo mô hình đồng bộ hoặc cơ chế lưu bền được thiết kế.
5. Ghi nhận/đối soát những trường hợp không biết chắc đã xử lý hay chưa.

Header **redelivered = true** chỉ gợi ý broker đã giao lại; không nên dùng nó để quyết định bỏ qua xử lý. Một message trùng nghiệp vụ có thể đến dưới dạng một lần publish mới và không mang dấu redelivered.

## 9. Prefetch, concurrency và throughput

Khi lượng message tăng, có hai điều chỉnh thường được cân nhắc tại listener container:

- **Concurrent consumers:** số consumer xử lý song song. Có thể cải thiện throughput nếu downstream và broker đủ năng lực.
- **Prefetch count:** số delivery chưa ACK được broker cho phép đẩy trước theo phạm vi cấu hình. Prefetch lớn có thể giảm overhead nhưng tăng số message nằm trong tay consumer, tiêu tốn bộ nhớ và giảm độ công bằng giữa consumer.

| Triệu chứng | Kiểm tra trước khi tăng cấu hình |
| --- | --- |
| Queue depth tăng | Downstream latency, số consumer, tốc độ publish, DB/broker bottleneck |
| Nhiều unacked message | Handler chậm, prefetch, quên manual ACK, transaction treo |
| CPU cao, queue vẫn tăng | Parse/validation nặng hoặc concurrency quá lớn |
| Redelivery nhiều | Lỗi dữ liệu, rollback/requeue, mất connection trước ACK |
| Xử lý lệch thứ tự | Nhiều consumer/prefetch làm mất giả định thứ tự nghiệp vụ |
| Một consumer giữ quá nhiều delivery | Prefetch và thời gian xử lý phân bố không đều |

**Thứ tự:** RabbitMQ queue có khái niệm thứ tự, nhưng concurrency, requeue, priority và nhiều consumer có thể làm **thứ tự xử lý thực tế** không giống thứ tự publish. Nếu yêu cầu xử lý tuần tự cho cùng order ID, phải thiết kế khóa phân luồng/điều phối hoặc quy tắc version phù hợp, không chỉ dựa vào việc dùng một queue.

**Capacity:** nếu broker giao 500 message/giây còn database chỉ xử lý 100 message/giây, tăng consumers chưa chắc giúp ích. Một phương án đúng có thể cần giới hạn đầu vào, batch nghiệp vụ, mở rộng database, hoặc kiến trúc giữ backlog ở broker và xử lý theo năng lực thực tế.

## 10. Vòng đời adapter, listener container và kết nối

AMQP inbound channel adapter gắn với listener container và các tài nguyên RabbitMQ. Tình trạng chạy của endpoint và tình trạng sẵn sàng của broker **không phải một**.

### 10.1. Khi ứng dụng khởi động

Thông thường:

Ở mức Spring, nhiều endpoint và listener container tham gia cơ chế **Lifecycle/SmartLifecycle**. Tùy bean và cấu hình, **autoStartup**, **start()/stop()** và **phase** giúp kiểm soát thời điểm bắt đầu nhận message cũng như thứ tự dừng các thành phần. Không nên tự coi việc thay đổi một cờ lifecycle là cơ chế xác nhận message hoặc cách bảo đảm xử lý hết backlog.

1. Spring tạo bean ConnectionFactory, topology declarations và các endpoint liên quan.
2. RabbitAdmin/AmqpAdmin (nếu được cấu hình) có thể khai báo exchange, queue và binding trên broker theo chính sách.
3. Listener container bắt đầu nhận từ queue theo lifecycle và **autoStartup**.
4. Inbound adapter chuyển message nhận được vào MessageChannel.

Đừng suy ra **isRunning() = true** đồng nghĩa kết nối hoàn toàn khỏe. Một container có thể đang cố reconnect do broker không khả dụng hoặc user thiếu quyền. Cần quan sát cả kết nối, log và chỉ số tiêu thụ thực tế.

### 10.2. Khi dừng hoặc bảo trì

Khi dừng endpoint/listener, các delivery đang xử lý có thể cần hoàn tất, bị rollback hoặc được giao lại tùy cơ chế ACK, transaction và container. Không nên kỳ vọng **stop()** đồng nghĩa mọi tác vụ downstream đã drain xong, nhất là khi có ExecutorChannel hoặc các tác vụ bất đồng bộ.

Một trình tự vận hành thường hợp lý:

1. Ngừng nhận công việc mới hoặc tạm dừng listener theo cơ chế được hỗ trợ.
2. Theo dõi **in-flight/unacked**, active handlers, queue depth và các tác vụ đang chạy.
3. Chờ xử lý xong trong giới hạn vận hành hoặc chuẩn bị cơ chế redelivery an toàn.
4. Đóng tài nguyên và tiến trình theo vòng đời Spring.
5. Khi khởi động lại, kiểm tra message tồn trong broker, checkpoint và idempotency nghiệp vụ.

Các connection/session dùng chung không nên bị đóng tùy tiện chỉ vì muốn dừng một inbound adapter. Phải xét bean nào sở hữu tài nguyên và những endpoint khác có dùng chung hay không.

## 11. Quan sát và bảo mật khi vận hành

AMQP inbound adapter không phải “hộp đen”: cần theo dõi tình trạng nhận dữ liệu ở cả broker lẫn ứng dụng.

| Nhóm | Chỉ số hoặc thông tin cần quan sát |
| --- | --- |
| Broker | Ready messages, unacked messages, consumer count, publish/deliver/ack rates |
| Listener | Consumer concurrency, reconnect, lỗi khai báo queue, listener failure |
| Flow nội bộ | Số message vào channel, handler latency, failure rate, active processing |
| Retry | Số lần retry, số message bị requeue, số message đi DLQ, poison messages |
| Nghiệp vụ | Event ID đã xử lý, số đơn hàng được ghi, số bản trùng bị loại |
| Độ trễ | Thời gian từ publish đến xử lý, backlog age, thời gian ACK |
| Bảo mật | TLS, quyền virtual host/queue/exchange, credential rotation, log masking |

Khi cấu hình sản xuất:

- Dùng tài khoản RabbitMQ giới hạn quyền theo virtual host, exchange và queue.
- Bật TLS nếu môi trường cần mã hóa đường truyền và xác minh chứng chỉ đúng cách.
- Không ghi credential hoặc toàn bộ payload nhạy cảm vào log.
- Có chính sách TTL, retention hoặc hạn mức cho queue/DLQ để tránh tăng vô hạn.
- Đặt topology và policy (queue durability, dead-letter, message size, quorum/classic theo nhu cầu) cùng đội vận hành broker.
- Kiểm thử tình huống broker restart, network partition, consumer reconnect và credential hết hạn.

**Broker khỏe không đồng nghĩa nghiệp vụ khỏe.** Queue giảm nhưng message bị ACK quá sớm, handler bất đồng bộ thất bại hoặc lỗi bị đưa vào errorChannel không có xử lý phù hợp vẫn gây mất hiệu quả nghiệp vụ. Cần đối chiếu chỉ số broker với số bản ghi thực sự được xử lý.

## 12. Kịch bản tích hợp thực tế

### 12.1. Một queue cho nhóm worker xử lý đơn hàng

Nếu nhiều instance của cùng dịch vụ cùng consume **orders.created.q**, RabbitMQ phân phối delivery giữa các consumer theo cơ chế queue. Đây là mô hình **competing consumers** để chia tải. Mỗi message được giao cho một consumer tại một thời điểm theo broker, nhưng có thể bị giao lại khi chưa ACK.

Ứng dụng phải:

- Chịu được redelivery và không tạo đơn hàng trùng.
- Không dựa vào thứ tự xử lý tuyệt đối khi nhiều consumer chạy.
- Đặt prefetch và concurrency phù hợp với năng lực database.
- Quản lý graceful shutdown để tránh consumer đang làm việc mất trạng thái.

### 12.2. Nhiều hệ thống cần cùng một sự kiện

Hệ thống kho và hệ thống báo cáo đều cần OrderCreated. Nếu cả hai cùng tiêu thụ **một queue**, chúng thường **chia nhau** message thay vì mỗi bên nhận một bản sao. Cách thiết kế phù hợp là mỗi hệ thống có queue riêng, bind vào exchange theo điều kiện định tuyến cần thiết.

~~~mermaid
flowchart TD
    P["Order publisher"] --> X["orders.events exchange"]
    X --> Q1["warehouse.orders.q"]
    X --> Q2["analytics.orders.q"]
    Q1 --> W["Warehouse inbound adapter"]
    Q2 --> A["Analytics inbound adapter"]
~~~

Cần quyết định direct/topic/fanout exchange theo quy tắc routing, không mặc định rằng một routing key hoặc một queue phù hợp cho mọi subscriber.

### 12.3. Gửi sang AMQP rồi lưu database

Giả sử inbound adapter nhận OrderCreated, service activator ghi vào database, sau đó outbound adapter gửi biên nhận sang hệ thống khác. Không có transaction tự động bao trùm cả RabbitMQ, database và đích khác.

Nếu database commit thành công nhưng outbound publish thất bại, có thể cần outbox lưu trạng thái bản tin chưa gửi. Nếu broker giao lại sau khi database đã commit, cần idempotency ở consumer. **ACK phải gắn với ranh giới hoàn tất đã được thiết kế**, không chỉ với một lần parse payload thành công.

## 13. Kiểm thử: từ happy path đến tình huống lỗi

| Kịch bản | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Routing đúng | Publish với orders.events / orders.created | Message tới orders.created.q và vào rabbitOrders |
| Routing sai | Dùng key không có binding phù hợp | Không đến queue đích; kiểm tra return/mandatory nếu cần |
| Payload hợp lệ | Gửi O-1001|150000 dưới dạng text/plain | Handler nhận String, xử lý và hoàn tất |
| Sai định dạng | Gửi message thiếu trường hoặc sai số | Phát hiện lỗi; không requeue vô hạn; áp dụng retry/DLQ theo cấu hình |
| Consumer tạm dừng | Stop consumer rồi publish | Queue lưu message theo chính sách; resume sẽ có thể nhận backlog |
| Handler ném exception | Giả lập DB lỗi | Kiểm tra ACK/NACK/requeue và retry theo cấu hình |
| Connection đứt | Ngắt broker trong khi có delivery | Kiểm tra reconnect, in-flight và khả năng redelivery |
| Duplicate | Publish cùng eventId nhiều lần | Nghiệp vụ tạo kết quả một lần nhờ idempotency |
| Load cao | Publish burst và tăng backlog | Theo dõi queue ready/unacked, latency, prefetch, throughput |
| Scale out | Chạy hai consumer trên cùng queue | Competing-consumer đúng kỳ vọng, không mặc định broadcast |
| Restart | Dừng và khởi động lại ứng dụng | Các message chưa ACK được xử lý lại theo broker; nghiệp vụ không trùng |

### 13.1. Đừng chỉ kiểm tra log “đã nhận”

Nếu handler chỉ in **Nhan don O-1001**, ta mới biết payload đã đến service handler trong ví dụ. Để kết luận một đơn hàng được ghi an toàn, test thực tế cần kiểm tra database, trạng thái idempotency, ACK và hành vi sau khi khởi động lại.

Trong test tích hợp, có thể dùng RabbitMQ chạy riêng trong môi trường test hoặc container thử nghiệm được quản lý bởi hệ thống build. Tuy nhiên không biến demo thành bài test bảo đảm exactly-once chỉ bằng cách chạy một lượt gửi thành công.

## 14. Sai lầm thường gặp

**Nhầm AMQP queue với Spring MessageChannel.** Queue thuộc RabbitMQ và được broker quản lý; MessageChannel thuộc ứng dụng Spring Integration và có ngữ nghĩa giao tiếp nội bộ.

**Dùng Spring Integration poller cho mọi AMQP inbound endpoint.** Message-driven AMQP inbound adapter thường dùng listener container, không cần polling source định kỳ như File/SFTP.

**Coi một queue là nơi broadcast cho mọi ứng dụng.** Nhiều consumer trên cùng queue thường cạnh tranh nhận message; muốn mỗi hệ thống có bản sao thì thiết kế queue/binding riêng.

**Cho rằng AUTO ACK nghĩa là nghiệp vụ luôn hoàn tất trước khi ACK.** Điều này còn phụ thuộc channel và cách xử lý bất đồng bộ. Với ExecutorChannel, adapter có thể trả về trước khi handler hoàn thành.

**Để message sai dữ liệu bị requeue liên tục.** Poison message có thể gây vòng lặp delivery; cần retry có giới hạn và DLQ được cấu hình rõ.

**Dùng redelivered hoặc messageId thay khóa idempotency duy nhất.** Cần eventId/orderId ổn định và kiểm tra nghiệp vụ khi ghi trạng thái.

**Tăng prefetch hoặc consumer không giới hạn.** Có thể tăng unacked backlog, gây quá tải DB, tốn bộ nhớ và làm thứ tự xử lý khó kiểm soát.

**Nhầm ACK của consumer với reply nghiệp vụ.** Nếu producer phải biết kết quả, cần inbound/outbound gateway hoặc luồng phản hồi bất đồng bộ.

**Tin rằng durable queue đủ cho mọi tình huống mất dữ liệu.** Cần xét message persistence, chính sách broker, topology, ACK và xử lý sự cố.

**Chỉ giám sát isRunning.** Cần thêm kết nối RabbitMQ, ready/unacked, retry, DLQ, thời gian xử lý và kết quả nghiệp vụ.

## 15. Câu hỏi tự kiểm tra

1. RabbitMQ exchange, binding và queue khác nhau ở điểm nào? Vì sao inbound adapter thường tiêu thụ từ queue thay vì trực tiếp từ exchange?
2. Khi dùng AMQP inbound adapter, vì sao Spring Integration Poller thường không cần thiết?
3. AMQP inbound channel adapter khác inbound gateway như thế nào? ACK có phải business reply không?
4. Khi producer publish String, những điều kiện nào khiến inbound adapter nhận được String thay vì byte array?
5. Với DirectChannel đồng bộ và AUTO ACK, thời điểm listener return có quan hệ như thế nào với thời điểm handler xử lý xong?
6. Nếu đổi sang ExecutorChannel, vì sao ACK có thể xảy ra trước khi nghiệp vụ thất bại?
7. Một message chứa JSON sai schema liên tục gây exception. Cần thiết kế retry, requeue và DLQ như thế nào?
8. Nếu consumer ghi database xong nhưng tiến trình chết trước ACK, cơ chế nào giúp không tạo bản ghi trùng khi message được giao lại?
9. Prefetch cao và nhiều consumer ảnh hưởng thế nào tới unacked message, throughput và thứ tự xử lý?
10. Hai ứng dụng cùng cần OrderCreated. Vì sao không nên cho chúng cạnh tranh trên một queue nếu yêu cầu mỗi ứng dụng đều nhận đủ sự kiện?
11. Những chỉ số nào giúp phân biệt listener không kết nối được broker với listener khỏe nhưng queue không có message?
12. Vì sao queue durable không đồng nghĩa toàn bộ pipeline có bảo đảm exactly-once?

## Tổng kết

**AMQP inbound channel adapter** là cầu nối một chiều từ **RabbitMQ queue**, qua **Spring AMQP listener container** và **MessageConverter**, đến **MessageChannel** trong ứng dụng Spring Integration. Muốn dùng đúng endpoint này, cần hiểu **exchange–binding–queue**, kiểu payload và headers sau chuyển đổi, cũng như mối quan hệ giữa **ACK, exception, redelivery và kết quả nghiệp vụ**. DirectChannel đồng bộ giúp giữ đường xử lý rõ ràng; chuyển sang bất đồng bộ phải đánh giá lại điểm ACK. Một luồng tin cậy cần retry có giới hạn, DLQ, idempotency, kiểm soát prefetch/concurrency, bảo mật kết nối và chỉ số vận hành của cả RabbitMQ lẫn ứng dụng. Đây là nền tảng để kết nối AMQP với các adapter, gateway và service activator khác trong Spring Integration mà không nhầm giao nhận kỹ thuật với hoàn tất nghiệp vụ.
