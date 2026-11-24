# AMQP inbound gateway

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích hợp đồng **request–reply** của AMQP inbound gateway và phân biệt nó với AMQP inbound channel adapter một chiều.
- Mô tả đường đi **RabbitMQ request queue → listener container → inbound gateway → MessageChannel → service activator → AMQP reply**.
- Hiểu cách sử dụng **reply-to**, **correlation ID**, request/reply conversion, message headers và reply timeout khi gọi qua RabbitTemplate.
- Tạo một ví dụ **Spring Integration Java DSL** phục vụ yêu cầu báo giá qua RabbitMQ, có exchange, binding, request queue, handler và client thử nghiệm.
- Phân tích lỗi xử lý, ACK/NACK, retry/requeue, timeout, reply đến muộn, message trùng và ảnh hưởng của channel bất đồng bộ.
- Thiết kế kiểm thử, bảo mật, concurrency, observability và trình tự vận hành cho gateway request–reply.

## 1. Bài toán: consumer phải trả lời cho bên gửi

Trong kiến trúc event-driven, một hệ thống thường phát sự kiện **OrderCreated** và không đợi consumer xử lý xong. Khi đó **AMQP inbound channel adapter** phù hợp: nhận message từ RabbitMQ queue, đưa vào MessageChannel và kết thúc trách nhiệm ở luồng inbound một chiều.

Nhưng có những tác vụ yêu cầu **kết quả ngay cho mỗi request**. Ví dụ, ứng dụng bán hàng gửi thông tin sản phẩm và số lượng tới dịch vụ báo giá qua RabbitMQ, rồi phải nhận tổng tiền để hoàn tất bước tiếp theo. Một bản tin đã được broker xác nhận hoặc consumer ACK **không chứa kết quả báo giá**. Cần một luồng **request–reply** thật sự.

**AMQP inbound gateway** là endpoint phục vụ yêu cầu đó ở **phía nhận**. Nó tiêu thụ request từ một AMQP queue, chuyển request thành Spring Message, gửi vào flow, chờ hoặc nhận reply theo hợp đồng, rồi phát reply trở lại địa chỉ được bên gọi khai báo.

~~~mermaid
flowchart LR
    C["Caller<br/>RabbitTemplate"] --> X["RabbitMQ exchange"]
    X --> Q["Request queue<br/>quotes.request.q"]
    Q --> L["Spring AMQP<br/>listener container"]
    L --> G["AMQP inbound gateway"]
    G --> MC["MessageChannel<br/>quoteRequests"]
    MC --> H["Service activator<br/>QuoteService"]
    H -->|"Spring reply message"| G
    G -->|"AMQP reply-to + correlation"| R["Reply destination"]
    R --> C
~~~

Trong ví dụ này, **inbound** được tính từ góc nhìn của dịch vụ báo giá: request đi từ bên ngoài vào ứng dụng. Dù có phát một bản reply ra RabbitMQ, endpoint vẫn được gọi là **inbound gateway** vì nó cung cấp một dịch vụ request–reply cho các caller bên ngoài.

## 2. Phân biệt inbound adapter với inbound gateway

| Tiêu chí | AMQP inbound channel adapter | AMQP inbound gateway |
| --- | --- | --- |
| Hợp đồng ứng dụng | **One-way**: tiêu thụ message | **Request–reply**: request cần kết quả |
| Nguồn dữ liệu | RabbitMQ queue | RabbitMQ request queue |
| Đầu vào cho Spring Integration | Spring Message qua channel | Spring request Message qua channel |
| Phản hồi nghiệp vụ | Không tự gửi reply nghiệp vụ | Lấy reply từ flow rồi gửi AMQP reply |
| Reply destination | Không bắt buộc cho trao đổi một chiều | Thường cần **reply-to** hoặc đích reply được cấu hình |
| Correlation | Chủ yếu phục vụ tracing nếu cần | Cần ghép đúng response với request khi nhiều lượt gọi |
| Khi service activator trả null | Thường không cần reply | Có nguy cơ không hoàn thành request–reply |
| Ví dụ | Nhận sự kiện OrderCreated | Nhận yêu cầu QuoteRequest, trả QuoteResponse |

**AMQP outbound gateway** là góc nhìn từ phía *ứng dụng chủ động gửi request đi* rồi đợi reply. Một kiến trúc có thể có outbound gateway ở ứng dụng A và inbound gateway ở ứng dụng B; bên gọi cũng có thể dùng trực tiếp **RabbitTemplate.convertSendAndReceive(...)** mà không xây một outbound IntegrationFlow.

Không nên chọn inbound gateway chỉ để “được RabbitMQ ACK”. Broker acknowledgment và reply nghiệp vụ là hai cơ chế có mục đích, thời điểm và điều kiện thành công khác nhau.

## 3. Giao thức request–reply: request queue, reply-to, correlation

Một AMQP request thông thường mang:

- **Body:** payload yêu cầu, ví dụ JSON hoặc String được converter hỗ trợ.
- **reply-to:** địa chỉ mà caller muốn nhận phản hồi.
- **correlation ID:** giúp caller ghép reply với request tương ứng.
- **Message properties/headers:** content type, encoding, message ID, trace ID hoặc metadata nghiệp vụ.

Ở phía dịch vụ:

1. Caller publish request đến exchange với routing key để request tới queue.
2. RabbitMQ listener container nhận delivery từ request queue.
3. Inbound gateway chuyển AMQP message thành Spring Message, đưa vào request channel.
4. Handler tạo ra **một reply**; Spring Integration định tuyến reply trở lại gateway.
5. Gateway chuyển reply thành AMQP message và gửi đến reply destination.
6. Caller dùng correlation để nhận đúng kết quả, hoặc timeout nếu không có reply đúng hạn.

~~~mermaid
sequenceDiagram
    participant C as Caller / RabbitTemplate
    participant X as RabbitMQ
    participant G as AMQP inbound gateway
    participant H as QuoteService
    C->>X: Publish request, reply-to, correlation
    X->>G: Request delivery
    G->>H: Spring Message trên quoteRequests
    H-->>G: Spring reply message
    G->>X: Publish reply theo reply-to
    X-->>C: AMQP reply (correlation tương ứng)
    C->>C: Chuyển reply thành kết quả cho caller
~~~

**Correlation ID khác idempotency key.** Correlation ghép request với reply của một lượt trao đổi; **requestId nghiệp vụ** nhận diện cùng một yêu cầu nếu bị retry hoặc gửi lại. Có thể trùng nhau theo thiết kế cụ thể, nhưng không được mặc định rằng mọi thư viện giữ nguyên correlation ID qua các lần retry.

### 3.1. Những cơ chế reply destination

| Cách trả reply | Đặc điểm | Khi cần lưu ý |
| --- | --- | --- |
| **RabbitMQ direct reply-to** | Tối ưu request–reply khi client và broker hỗ trợ, dùng pseudo-queue reply-to | Không phải một durable queue lưu backlog reply cho caller ngoại tuyến |
| **Temporary/exclusive reply queue** | Caller có thể tạo queue riêng cho reply | Quản lý vòng đời queue/consumer và connection |
| **Fixed reply queue** | Một queue reply xác định trước | Cần consumer phù hợp, correlation, concurrency và cấu hình tránh nhầm reply |

Khi dùng RabbitTemplate.convertSendAndReceive với cấu hình mặc định phù hợp, Spring AMQP có thể sử dụng cơ chế direct reply-to. Điều đó không có nghĩa mọi RabbitMQ deployment và mọi cấu hình sẽ tự áp dụng cùng một cơ chế. Nếu dùng fixed reply queue, phải thiết kế queue, listener container, định tuyến, timeout và correlation rõ ràng.

### 3.2. Nếu request không có reply-to?

Một request gửi bằng cơ chế publish một chiều có thể **không có địa chỉ trả lời**. Khi đó inbound gateway không có thông tin đủ để trả kết quả qua kênh reply thông thường, trừ khi endpoint được cấu hình một **reply destination mặc định** thích hợp. Không nên hứa một response sẽ tự đến caller nếu không có reply-to/correlation hoặc hợp đồng khác.

### 3.3. MessageHeaders trong flow không phải AMQP properties

Spring Message có payload và headers như **replyChannel**, **errorChannel**, correlation hoặc metadata tùy cấu hình. Inbound gateway có thể dùng một reply channel tạm hoặc đường reply tương đương để nhận kết quả từ flow; sau đó message converter/header mapper chuyển những trường phù hợp thành AMQP reply.

Không serialize trực tiếp một đối tượng Spring MessageChannel ra RabbitMQ. **AMQP reply-to** là thông tin giao thức ngoài, còn **Spring replyChannel** là cơ chế định tuyến reply *nội bộ flow*.

## 4. RabbitMQ topology và listener container

Request–reply qua AMQP không làm mất các khái niệm RabbitMQ cơ bản:

| Thành phần | Vai trò trong inbound gateway |
| --- | --- |
| **Exchange** | Nhận request do caller publish |
| **Routing key/binding** | Chuyển request vào đúng request queue |
| **Request queue** | Chứa request chờ gateway xử lý |
| **ConnectionFactory** | Cung cấp kết nối RabbitMQ cho client và listener |
| **Listener container** | Tiêu thụ request delivery, quản lý ACK/NACK, concurrency, prefetch |
| **MessageConverter** | Chuyển AMQP body/properties thành payload/headers, và chuyển reply ngược lại |
| **AMQP inbound gateway** | Kết nối giao thức request–reply với messaging flow |
| **MessageChannel** | Chuyển request đến service activator hoặc endpoint xử lý |

Với AMQP inbound gateway dạng listener, nguồn nhận là **message-driven**, không phải File/SFTP poller theo lịch. Spring AMQP listener container có vòng đời start/stop và cơ chế nhận riêng. Không thêm một Spring Integration poller chỉ vì request xuất phát từ queue.

**Request queue durable** giúp topology của queue tồn tại theo chính sách broker; nó không tự khiến request/reply có exactly-once, không bảo đảm reply tồn tại khi caller đã timeout, và không thay thế idempotency.

## 5. Thiết kế hợp đồng request và reply

Trong ví dụ học tập, caller gửi chuỗi:

~~~text
requestId|productId|quantity
~~~

Ví dụ:

~~~text
req-1001|SKU-42|2
~~~

Gateway chuyển request cho QuoteService; service trả:

~~~text
OK|req-1001|100000
~~~

Trong đó đơn giá giả lập là **50.000 VND/sản phẩm**. Nếu dữ liệu sai, demo trả kết quả có cấu trúc đơn giản:

~~~text
ERROR|INVALID_REQUEST
~~~

Đây là định dạng tối giản để nhìn rõ đường request–reply. Trong production nên dùng JSON/Avro/Protobuf có schemaVersion, trường bắt buộc, mã lỗi và quy tắc tương thích:

~~~json
{
  "requestId": "req-1001",
  "productId": "SKU-42",
  "quantity": 2
}
~~~

Một reply có thể có các trường:

~~~json
{
  "requestId": "req-1001",
  "status": "OK",
  "totalVnd": 100000,
  "schemaVersion": 1
}
~~~

**Business error** như INVALID_REQUEST có thể là một *reply hợp lệ* để caller biết yêu cầu bị từ chối. **Technical error** như broker mất kết nối, database timeout hoặc converter lỗi thường cần đường xử lý lỗi khác. Không trả cùng một nội dung lỗi cho mọi loại sự cố vì caller sẽ không biết có an toàn để retry hay không.

## 6. Ví dụ Spring Integration Java DSL: AMQP inbound gateway

Ta xây dựng dịch vụ báo giá:

- Direct exchange: **quotes.requests**.
- Routing key: **quote.calculate**.
- Durable request queue: **quotes.request.q**.
- Inbound gateway lắng nghe request queue.
- MessageChannel nội bộ: **quoteRequests** (DirectChannel).
- Service activator gọi QuoteService và trả một String reply.
- Caller sử dụng RabbitTemplate.convertSendAndReceive(...) để nhận kết quả.

### 6.1. Dependencies và kết nối

Với Spring Boot, sử dụng các dependency được quản lý phiên bản đồng bộ với Spring Boot BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-amqp</artifactId>
    </dependency>
</dependencies>
~~~

Trong môi trường phát triển, ứng dụng cần RabbitMQ broker hoạt động và ConnectionFactory có host, port, virtual host, credential phù hợp. Dùng secret manager/biến môi trường và TLS trong môi trường cần bảo vệ kết nối; **không hardcode credential thật** trong source.

### 6.2. Tạo exchange, queue, binding và gateway flow

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
public class QuoteAmqpGatewayConfiguration {

    public static final String EXCHANGE = "quotes.requests";
    public static final String ROUTING_KEY = "quote.calculate";
    public static final String REQUEST_QUEUE = "quotes.request.q";

    @Bean
    public DirectExchange quotesExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue quotesRequestQueue() {
        return new Queue(REQUEST_QUEUE, true);
    }

    @Bean
    public Binding quotesBinding(
            Queue quotesRequestQueue,
            DirectExchange quotesExchange) {
        return BindingBuilder.bind(quotesRequestQueue)
            .to(quotesExchange)
            .with(ROUTING_KEY);
    }

    @Bean
    public MessageChannel quoteRequests() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow quoteInboundGatewayFlow(
            ConnectionFactory connectionFactory,
            QuoteService quoteService) {
        return IntegrationFlow
            .from(Amqp.inboundGateway(
                connectionFactory, REQUEST_QUEUE))
            .channel("quoteRequests")
            .handle(String.class, (request, headers) ->
                quoteService.calculate(request))
            .get();
    }
}
~~~

**Giải thích:**

1. **quotesExchange**, **quotesRequestQueue** và **quotesBinding** mô tả topology để caller publish vào exchange với routing key cố định.
2. **Amqp.inboundGateway(connectionFactory, REQUEST_QUEUE)** đăng ký endpoint nhận request qua Spring AMQP listener container.
3. **quoteRequests** là DirectChannel nội bộ. Message đi qua channel đến handler mà không cần viết RabbitMQ consumer thủ công.
4. **handle(String.class, ...)** kích hoạt QuoteService. Giá trị String trả về được framework sử dụng làm reply message cho gateway.
5. Gateway đọc thông tin reply destination/correlation từ AMQP request và gửi reply qua AMQP theo cơ chế đã cấu hình.

Các bean khai báo topology **chỉ thực sự được tạo trên broker** khi có AmqpAdmin/RabbitAdmin hoặc hệ thống triển khai tương đương và tài khoản đủ quyền. Không giả định khai báo bean đồng nghĩa queue/exchange đã hiện hữu ở RabbitMQ. Nếu tổ chức quản lý topology riêng, hãy provision bên ngoài ứng dụng.

### 6.3. Service xử lý request

~~~java
import org.springframework.stereotype.Service;

@Service
public class QuoteService {

    public String calculate(String body) {
        String[] fields = body.split("\\|", -1);

        if (fields.length != 3) {
            return "ERROR|INVALID_REQUEST";
        }

        String requestId = fields[0];
        String productId = fields[1];

        if (!requestId.matches("[A-Za-z0-9_-]{1,64}")
                || !productId.matches("[A-Za-z0-9_-]{1,64}")) {
            return "ERROR|INVALID_REQUEST";
        }

        int quantity;
        try {
            quantity = Integer.parseInt(fields[2]);
        } catch (NumberFormatException ex) {
            return "ERROR|INVALID_QUANTITY";
        }

        if (quantity <= 0 || quantity > 100) {
            return "ERROR|INVALID_QUANTITY";
        }

        // Quy tắc giá giả lập: 50.000 VND cho mỗi sản phẩm.
        long totalVnd = quantity * 50_000L;
        return "OK|" + requestId + "|" + totalVnd;
    }
}
~~~

**Vì sao trả String thay vì null?** Một gateway yêu cầu reply để hoàn tất tương tác. Khi service trả một String hợp lệ, framework có kết quả để chuyển về gateway. Nếu handler **trả null/void**, flow có thể không tạo reply, khiến caller chờ đến timeout hoặc xảy ra hành vi lỗi tùy cấu hình.

Ví dụ này chỉ tính giá trong bộ nhớ, **không tạo side effect** và không lưu trạng thái. Nếu xử lý thực tế tạo hóa đơn, trừ tồn kho hoặc ghi database, cần validation, transaction, authorization và idempotency phù hợp.

### 6.4. Caller sử dụng RabbitTemplate

Ứng dụng gửi request có thể dùng Spring AMQP trực tiếp:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class QuoteClient {

    private final RabbitTemplate rabbitTemplate;

    public QuoteClient(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public String askQuote(
            String requestId, String productId, int quantity) {

        String request = requestId + "|"
            + productId + "|" + quantity;

        Object reply = rabbitTemplate.convertSendAndReceive(
            "quotes.requests", "quote.calculate", request);

        if (!(reply instanceof String text)) {
            throw new IllegalStateException(
                "Khong nhan duoc reply hop le / timeout");
        }
        return text;
    }
}
~~~

Khi gọi:

~~~java
quoteClient.askQuote("req-1001", "SKU-42", 2);
~~~

Kết quả thành công mong đợi:

~~~text
OK|req-1001|100000
~~~

**RabbitTemplate.convertSendAndReceive(...)** thiết lập cơ chế request–reply phù hợp với cấu hình client, gửi message, chờ một reply tương ứng và convert kết quả. Khi hết thời hạn chờ mà không có reply, phương thức có thể trả về null; ví dụ coi null hoặc sai kiểu là lỗi. Đừng dùng việc caller nhận String như bằng chứng mọi transaction bên ngoài đã commit nếu dịch vụ thực tế còn những bước bất đồng bộ.

Trong ví dụ, converter mặc định của Spring AMQP thường xử lý String dưới dạng nội dung text. Nếu producer dùng JSON/binary hoặc converter tùy chỉnh, phải kiểm tra body/contentType và kiểu payload thực tế ở cả request và reply.

### 6.5. Timeout ở phía caller

Một cấu hình Spring Boot thường dùng:

~~~yaml
spring:
  rabbitmq:
    template:
      reply-timeout: 5s
~~~

**reply-timeout** giới hạn khoảng thời gian caller chờ reply theo RabbitTemplate, không phải thời gian xử lý tối đa của nghiệp vụ tại server. Nếu handler đang thực hiện I/O hoặc đợi downstream, phải đặt timeout riêng cho các bước đó. Thời gian chờ quá ngắn có thể làm caller timeout dù gateway vẫn đang xử lý và gửi response đến muộn.

## 7. Phân biệt bốn kiểu thông tin xác nhận

AMQP request–reply có nhiều tín hiệu dễ gây nhầm:

| Tín hiệu | Hướng | Nó nói điều gì? | Nó không nói điều gì? |
| --- | --- | --- | --- |
| **Publisher confirm** | Broker → publisher request/reply | Broker đã xác nhận publish theo cơ chế confirm | Handler nghiệp vụ đã thực hiện thành công |
| **Consumer ACK/NACK** | Consumer/gateway → broker | Trạng thái xác nhận delivery request | Caller đã nhận business reply |
| **AMQP reply message** | Gateway → caller | Kết quả nghiệp vụ theo hợp đồng reply | Mọi side effect bên ngoài khác đã hoàn tất |
| **Reply timeout** | Caller tự xác định | Không nhận được reply đúng hạn | Yêu cầu chắc chắn chưa được server xử lý |

Đặc biệt, một request có thể đã được service xử lý thành công và reply đã gửi nhưng caller mất kết nối hoặc timeout trước khi đọc reply. Khi caller retry, hệ thống có thể nhận **hai request cho cùng một nghiệp vụ**.

## 8. ACK, exception, requeue và lỗi nghiệp vụ

Inbound gateway dựa trên Spring AMQP listener container; container thường quản lý ACK theo cấu hình. Không nên suy ra rằng gateway tự tạo transaction nguyên tử giữa RabbitMQ, service handler và database.

### 8.1. Với DirectChannel và AUTO ACK

Trong ví dụ, request được chuyển qua DirectChannel đến QuoteService **đồng bộ**. Khi handler trả String reply, gateway có thể tiếp tục công việc gửi AMQP reply; listener container xử lý ACK theo cơ chế AUTO và kết quả của callback. Nếu exception lan đến listener/container, việc reject, NACK hoặc requeue phụ thuộc cấu hình và loại lỗi.

Lưu ý: thứ tự chính xác giữa publish reply, consumer acknowledgment, transaction và callback phụ thuộc implementation/configuration. **ACK không chứng minh caller đã đọc reply.**

### 8.2. Lỗi business nên có reply có cấu trúc

Yêu cầu báo giá sai số lượng không nhất thiết là sự cố hạ tầng. Trong ví dụ, QuoteService trả **ERROR|INVALID_QUANTITY** như một reply hợp lệ để caller biết cần sửa input. Điều này tránh biến mọi lỗi dữ liệu thành requeue vô hạn.

Một hệ thống thật nên dùng mã lỗi, thông điệp an toàn, requestId và schemaVersion; không đẩy stack trace hoặc exception nội bộ nguyên văn về client.

### 8.3. Lỗi kỹ thuật cần chính sách riêng

Ví dụ: database timeout, RabbitMQ reply publish lỗi, service downstream tạm ngừng, converter không thể parse request. Nếu ném exception:

- Container có thể dùng ACK/NACK/requeue hoặc error handling tùy cấu hình.
- Client có thể chỉ quan sát **timeout** nếu không có AMQP reply được gửi.
- Requeue không giới hạn có thể tạo **poison message loop**, đặc biệt với dữ liệu không hợp lệ.
- Nếu request đã tạo side effect trước exception, redelivery/retry có nguy cơ tạo trùng.

Cần chọn chính sách tường minh: retry hữu hạn với backoff cho lỗi tạm thời; cách ly/DLQ hoặc reply lỗi cho lỗi cố định; ghi trạng thái và đối soát khi kết quả không rõ.

### 8.4. DLQ không tự phát reply cho caller

Dead-letter exchange/queue có thể nhận những message request bị reject không requeue, hết TTL hoặc theo broker policy. Nhưng **đưa request vào DLQ không tương đương gửi một business reply**. Caller có thể đã timeout từ trước; hệ thống cần một cách riêng để báo trạng thái cho người dùng hoặc hệ thống gọi.

~~~mermaid
flowchart TD
    REQ["AMQP request"] --> V{"Kiểm tra request"}
    V -- "Business input sai" --> BR["Trả reply lỗi có cấu trúc"]
    V -- "Hợp lệ" --> H["Xử lý nghiệp vụ"]
    H --> R{"Kết quả"}
    R -- "Thành công" --> OK["Trả reply kết quả"]
    R -- "Lỗi tạm thời" --> RET["Retry có giới hạn / backoff"]
    R -- "Lỗi cố định / hết retry" --> ERR["Lưu lỗi, DLQ hoặc phản hồi theo policy"]
    RET --> H
~~~

Không nên có một cơ chế duy nhất “cứ ném lỗi là retry mãi” cho cả invalid request lẫn lỗi network.

## 9. Timeout và reply đến muộn

Gateway request–reply tạo quan hệ thời gian giữa caller và handler. Một chuỗi thời gian có thể như sau:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant B as RabbitMQ
    participant G as Inbound gateway
    participant S as QuoteService
    C->>B: Request req-1001
    B->>G: Delivery
    G->>S: Xử lý request
    Note over C: Reply timeout xảy ra
    C--xC: Không có reply đúng hạn
    S-->>G: Kết quả đến muộn
    G->>B: Gửi reply theo reply-to
    Note over B,C: Caller có thể không còn chờ reply
~~~

**Timeout của caller không hủy công việc bên server một cách tự động.** Tùy cách cài đặt, server vẫn đang xử lý, có thể ghi database và gửi reply sau khi caller đã ngừng chờ. Vì vậy:

1. Đặt timeout theo SLA thực tế của nghiệp vụ và thời gian chờ downstream.
2. Gắn **requestId nghiệp vụ** ổn định vào nội dung request.
3. Nếu request có side effect, áp dụng idempotency và tra cứu trạng thái trước khi retry.
4. Không tạo reply quá lớn; kiểm soát kích thước và thời gian serialize.
5. Nếu tác vụ kéo dài hàng phút, cân nhắc **gửi yêu cầu bất đồng bộ + job ID + sự kiện/callback trạng thái**, thay vì giữ request–reply đồng bộ trong thời gian dài.

### 9.1. Reply đến không đúng correlation

Khi nhiều request đồng thời dùng chung cơ chế reply, caller phải ghép response theo correlation. Nếu tùy biến reply queue/converter/header mapper và làm mất correlation ID, hệ thống có thể timeout dù broker đã có reply. Cần kiểm thử song song nhiều request, requestId và correlation để phát hiện sai lệch.

### 9.2. Direct reply-to và độ bền

Direct reply-to của RabbitMQ tối ưu đường trả lời cho RPC ngắn, nhưng không nên xem đó là một hàng đợi reply durable để lưu kết quả cho caller đã offline. Nếu yêu cầu phản hồi được lưu nhiều giờ, API trạng thái có thể phù hợp hơn một RPC qua direct reply-to.

## 10. Concurrency, prefetch và MessageChannel

AMQP inbound gateway có thể phục vụ nhiều request thông qua listener container. Số consumer, prefetch và loại channel quyết định năng lực xử lý đồng thời và thời gian chờ.

| Thành phần | Tác động | Nguy cơ |
| --- | --- | --- |
| **Listener concurrency** | Số request có thể được tiếp nhận/xử lý song song | Quá nhiều consumer có thể làm nghẽn DB hoặc downstream |
| **Prefetch** | Số delivery được đưa tới consumer trước ACK theo phạm vi cấu hình | Request bị giữ ở consumer lâu, tăng unacked backlog |
| **DirectChannel** | Handler chạy theo chuỗi gọi đồng bộ | Request chậm giữ listener thread |
| **ExecutorChannel** | Chuyển handler sang executor | Gateway phải đợi reply bất đồng bộ, cần kiểm soát timeout, correlation và capacity |
| **QueueChannel** | Đệm request cho polling consumer | Cần poller, reply có thể đến muộn, durability/timeout phải thiết kế |

### 10.1. DirectChannel là lựa chọn dễ hiểu cho demo

Trong ví dụ, gateway gọi handler qua DirectChannel rồi nhận reply trong cùng tương tác logic. Điều này giúp giới hạn số request đang thực thi theo listener concurrency và làm đường exception dễ theo dõi. Nhưng một handler chậm có thể giữ listener lâu; cần đặt timeout thực tế và bảo vệ downstream.

### 10.2. Khi chuyển sang ExecutorChannel

Không nên chỉ thay DirectChannel bằng ExecutorChannel để tăng throughput. Gateway có thể tiếp tục chờ reply qua channel tạm trong khi handler thực thi trên worker thread, và cần cấu hình thời gian chờ. Khi executor queue đầy hoặc reply đến sau timeout, caller có thể không nhận kết quả.

Khác với inbound adapter một chiều, **gateway có hợp đồng chờ reply** nên cách ACK và kết thúc listener callback cần được kiểm chứng với cấu hình thực tế; không được giả định ACK tự động xảy ra ngay sau khi executor nhận tác vụ hoặc chắc chắn đợi tới khi mọi side effect xong.

### 10.3. Backpressure

Giả sử hệ thống nhận 500 quote request/giây nhưng service chỉ tính và trả được 80 request/giây. Nếu tiếp tục tăng số listener hoặc executor không có giới hạn, thời gian chờ và backlog sẽ tăng, khiến caller timeout nhiều hơn.

Giải pháp có thể gồm:

- Giới hạn listener concurrency theo năng lực thực.
- Đặt timeout cho cả RPC và các dịch vụ downstream.
- Giới hạn queue capacity; có chính sách từ chối hoặc làm chậm producer.
- Quan sát số request đang chờ, unacked deliveries, latency p95/p99 và retry.
- Tách tác vụ dài sang quy trình bất đồng bộ có trạng thái.

## 11. Idempotency khi request có side effect

Demo QuoteService chỉ tính toán nên dễ chạy lại. Nhưng hãy xét một **PaymentGatewayService** tạo giao dịch thanh toán:

1. Caller gửi requestId **pay-1001**.
2. Inbound gateway nhận request; service ghi giao dịch thành công.
3. Kết nối mất trước khi reply đến caller.
4. Caller timeout rồi gửi lại requestId pay-1001.

Không có idempotency, hai lần gọi có thể tạo hai giao dịch. Hãy:

- Dùng **requestId** hoặc **idempotencyKey** ổn định giữa các lần retry.
- Kiểm tra khóa ở nơi thực hiện side effect, tốt nhất có unique constraint và transaction thích hợp.
- Lưu kết quả nghiệp vụ của lần xử lý thành công để có thể trả lại cho request trùng.
- Phân biệt request trùng cùng payload với **requestId bị tái sử dụng nhưng payload khác**.
- Có cơ chế phục hồi khi process chết sau khi commit nhưng trước khi trả reply.

**Correlation ID không mặc nhiên là idempotency key**. Thư viện có thể tạo correlation riêng cho mỗi lượt RPC; business identity phải được cam kết trong hợp đồng request.

### 11.1. ACK và transaction không đủ cho exactly-once

Một transaction database không tự bao phủ acknowledgment request và publish reply qua RabbitMQ. Nếu database commit nhưng consumer ACK chưa đến broker, request có thể bị redeliver. Nếu reply đã publish nhưng ACK mất, caller có thể thấy hai replies hoặc một reply đến muộn. Idempotency ở tầng nghiệp vụ vẫn cần thiết.

## 12. ErrorMessage, errorChannel và replyChannel

Trong Spring Integration:

- **replyChannel** chỉ đường trả lời của một Spring Message bên trong flow.
- **errorChannel** là nơi ErrorMessage có thể được chuyển đến trong những cấu hình xử lý lỗi phù hợp.
- **AMQP reply-to** chỉ destination ở giao thức RabbitMQ để gateway publish reply về caller.

Ba khái niệm này không được dùng thay nhau.

Nếu một handler ném exception, cách lỗi được lan ngược, chuyển thành ErrorMessage, làm listener reject/requeue hoặc chuyển thành reply lỗi **phụ thuộc endpoint và cấu hình**. Một bản ErrorMessage không mặc nhiên là body AMQP reply mà caller hiểu được.

Muốn client luôn nhận mã lỗi nghiệp vụ, nên định nghĩa rõ cách biến **các lỗi có thể dự báo** thành reply hợp lệ. Với lỗi hạ tầng, ghi log, metrics, retry, alert và dead-letter theo chính sách; nếu gửi reply lỗi kỹ thuật, không được tiết lộ stack trace, nội bộ database hoặc credential.

## 13. Vòng đời, kết nối và bảo mật

Inbound gateway phụ thuộc listener container, RabbitMQ ConnectionFactory, converter và scheduler/thread pool của ứng dụng. Nhiều endpoint tham gia **Lifecycle/SmartLifecycle** với **start(), stop(), isRunning(), autoStartup** và **phase**.

| Hạng mục | Điểm vận hành |
| --- | --- |
| **Khởi động** | RabbitMQ đã có exchange/queue/binding; listener container có quyền consume |
| **Kết nối** | Host, TLS, virtual host, credential và reconnect |
| **Dừng** | Ngừng nhận request mới, quản lý request in-flight và reply chưa gửi |
| **Quá tải** | Listener concurrency, prefetch, downstream latency và queue depth |
| **Bảo mật** | Tài khoản tối thiểu quyền, không log payload nhạy cảm, auth/authorization nghiệp vụ |
| **Theo dõi** | Requests nhận, replies gửi, timeouts, errors, redelivery, business outcomes |

**isRunning() = true không chứng minh broker và đường reply đang khỏe.** Cần theo dõi connection, queue ready/unacked, số consumer, các lỗi listener và tỷ lệ RPC hoàn tất.

### 13.1. Dừng và khởi động lại

Khi graceful shutdown:

1. Ngừng tiếp nhận request mới hoặc tạm dừng listener theo cơ chế hỗ trợ.
2. Cho request đang xử lý hoàn tất trong giới hạn thời gian đã cam kết, hoặc dựa vào idempotency/redelivery để xử lý tiếp.
3. Theo dõi in-flight/unacked, reply publish thất bại và timeout.
4. Đóng tài nguyên theo lifecycle của Spring, không đóng ConnectionFactory dùng chung tùy tiện.
5. Sau restart, kiểm tra backlog trên request queue và việc xử lý lại theo chính sách ACK.

Không nên cho rằng **stop() sẽ tự gửi lỗi cho mọi caller đang chờ**. Nếu caller timeout trong lúc bảo trì, họ cần biết quy tắc retry/idempotency hoặc cách tra cứu trạng thái.

## 14. Bộ kiểm thử cần có

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Request hợp lệ | req-1001/SKU-42/2 trả OK và tổng tiền 100000 |
| Payload sai | Handler trả reply lỗi có mã rõ ràng, không tạo poison loop |
| Routing không đến queue | Caller timeout hoặc nhận lỗi theo policy, có metrics/alert |
| Reply-to thiếu/sai | Gateway không hứa trả reply thành công; lỗi được quan sát |
| Hai request song song | Correlation không trả nhầm kết quả giữa hai caller |
| Service chậm hơn timeout | Caller hết thời hạn chờ; xử lý reply đến muộn |
| Broker restart | Consumer reconnect, request chưa ACK có thể redeliver |
| Handler exception | Requeue/DLQ hoặc reply lỗi theo đúng chính sách |
| Duplicate requestId | Side effect không thực hiện hai lần |
| Mất kết nối sau side effect | Retry của caller không tạo kết quả nghiệp vụ trùng |
| Tải đỉnh | Latency, unacked, ready backlog, số consumer và timeout |
| Graceful shutdown | Request in-flight được xử lý hoặc phục hồi có kiểm soát |

### 14.1. Các bước thử ví dụ

1. Khởi động RabbitMQ test và dịch vụ có QuoteAmqpGatewayConfiguration.
2. Xác minh **quotes.requests** exchange và **quotes.request.q** có binding **quote.calculate**.
3. Gọi QuoteClient.askQuote với requestId **req-1001**, productId **SKU-42**, quantity **2**; kiểm tra reply **OK|req-1001|100000**.
4. Gửi quantity bằng 0; kiểm tra reply **ERROR|INVALID_QUANTITY**.
5. Tạm dừng listener hoặc dừng dịch vụ và gọi client; kiểm tra reply timeout thay vì giả định broker publish thất bại.
6. Gửi hai requestId khác nhau đồng thời để kiểm tra reply đúng correlation.
7. Thử exception ở handler trong môi trường test có kiểm soát; quan sát retry/requeue và tránh lặp vô hạn.

Nếu ứng dụng đang chạy trong cùng process với client test, điều đó chỉ minh họa API RabbitTemplate; triển khai thực tế nên kiểm tra qua hai tiến trình độc lập để phát hiện lỗi topology, mạng, xác thực và đóng/mở kết nối.

## 15. Sai lầm thường gặp

**Chọn inbound adapter một chiều rồi chờ business reply.** Adapter không tự thực hiện request–reply; phải dùng gateway hoặc xây cơ chế phản hồi riêng.

**Nhầm RabbitMQ ACK với AMQP reply.** ACK có ý nghĩa delivery; reply là dữ liệu nghiệp vụ được gửi qua reply destination.

**Bỏ qua reply-to và correlation.** Một request không có nơi nhận reply hoặc reply bị mất correlation có thể khiến client timeout.

**Xem direct reply-to như queue bền vững.** Nó tối ưu RPC ngắn, không phải kho lưu kết quả cho client offline.

**Dùng timeout để suy ra server chưa thực hiện.** Server có thể đã commit rồi reply bị mất; retry phải idempotent.

**Trả null từ service activator trong flow request–reply.** Gateway có thể không nhận được một message reply hoàn chỉnh.

**Retry vô hạn cho request sai dữ liệu.** Hãy trả business error hoặc cách ly, không tạo vòng requeue.

**Nhét lỗi kỹ thuật vào reply mà không có hợp đồng.** Client cần mã lỗi ổn định, không phải stack trace hoặc exception tùy ý.

**Tăng listener concurrency không đo năng lực downstream.** Có thể chỉ tăng số request in-flight và timeout.

**Dùng correlation ID làm khóa chống trùng duy nhất.** Cần requestId/idempotencyKey nghiệp vụ ổn định giữa các lần retry.

**Cho rằng gateway và database nằm trong một transaction.** Không có bảo đảm nguyên tử xuyên database, request ACK và reply publish nếu không có thiết kế riêng.

## 16. Câu hỏi tự kiểm tra

1. Tại sao AMQP inbound gateway khác inbound channel adapter dù đều tiêu thụ request từ RabbitMQ queue?
2. Caller phải gửi những metadata nào để gateway có thể trả đúng reply?
3. AMQP reply-to khác Spring replyChannel như thế nào?
4. RabbitTemplate.convertSendAndReceive giải quyết điều gì mà convertAndSend một chiều không làm?
5. Nếu service trả null, caller có thể quan sát điều gì?
6. Producer confirm, consumer ACK và business reply khác nhau ở các điểm nào?
7. Khi reply đến sau khi caller timeout, phía caller và phía server phải xử lý những rủi ro nào?
8. Vì sao cần requestId/idempotencyKey ổn định ngay cả khi đã có correlation ID?
9. Khi handler ném exception, vì sao không thể mặc định caller nhận một reply lỗi hợp lệ?
10. Khi nào nên dùng fixed reply queue thay vì direct reply-to? Cần đánh giá những gì?
11. Vì sao tăng ExecutorChannel concurrency có thể làm tình trạng timeout tệ hơn?
12. Khi ứng dụng chết sau database commit nhưng trước khi gửi reply, request redelivery có thể gây vấn đề gì?
13. Những chỉ số nào cho biết gateway đang chạy nhưng reply path không hoạt động?
14. Trong trường hợp xử lý hàng phút, tại sao một workflow bất đồng bộ có job ID có thể phù hợp hơn AMQP RPC?

## Tổng kết

**AMQP inbound gateway** nhận yêu cầu từ **RabbitMQ request queue**, ánh xạ delivery thành **Spring Message**, chuyển request qua **MessageChannel** để xử lý, rồi đưa **reply nghiệp vụ** về AMQP reply destination. Để luồng hoạt động đúng, cần xác định payload/converter, reply-to, correlation, request/reply timeout và đường lỗi. **Publisher confirm, consumer ACK và business reply** là ba loại tín hiệu khác nhau. Một gateway tin cậy phải quản lý timeout, reply đến muộn, redelivery, idempotency khi có side effect, concurrency, bảo mật và lifecycle của listener. Những nguyên tắc này giúp dùng AMQP request–reply đúng chỗ trong một hệ thống Spring Integration có file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, thay vì đồng nhất mọi lần nhận message với một giao dịch nghiệp vụ đã hoàn tất.
