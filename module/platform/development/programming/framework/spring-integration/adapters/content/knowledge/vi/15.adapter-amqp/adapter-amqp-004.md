# AMQP outbound gateway

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Xác định khi nào dùng **AMQP outbound gateway** thay vì **AMQP outbound channel adapter** trong Spring Integration.
- Giải thích đường đi **MessageChannel → outbound gateway → RabbitMQ request queue → AMQP reply → MessageChannel/caller**, bao gồm exchange, routing key, reply-to và correlation.
- Phân biệt **business reply**, **publisher confirm**, **publisher return** và **consumer acknowledgment**.
- Xây dựng hai ứng dụng minh họa: bên gọi dùng **@MessagingGateway + Amqp.outboundGateway(...)** và bên cung cấp dịch vụ dùng **Amqp.inboundGateway(...)**.
- Thiết kế timeout, converter, headers, xử lý lỗi, redelivery, idempotency và giới hạn tài nguyên cho request–reply.
- Kiểm thử reply đúng request khi có đồng thời, reply đến muộn và trường hợp hệ thống đích thực hiện thành công nhưng caller không nhận được phản hồi.

## 1. Bài toán: flow cần kết quả từ một dịch vụ qua RabbitMQ

Giả sử ứng dụng bán hàng phải tính phí giao hàng trước khi xác nhận đơn. Phần tính phí là một dịch vụ riêng, tiếp nhận các request từ RabbitMQ. Sau khi gửi dữ liệu sản phẩm và số lượng, ứng dụng bán hàng **cần nhận số tiền trả về** để tiếp tục.

Nếu chỉ dùng **AMQP outbound channel adapter**, flow sẽ publish thông điệp một chiều đến RabbitMQ; nó không tự cung cấp một message reply nghiệp vụ cho bước tính tổng tiền. Muốn request và nhận đúng response trong cùng một tương tác logic, ta dùng **AMQP outbound gateway**.

~~~mermaid
flowchart LR
    A["Mã Java / IntegrationFlow"] --> Q["MessageChannel<br/>quoteRpcRequests"]
    Q --> G["AMQP outbound gateway"]
    G --> T["RabbitTemplate<br/>convert / send / receive"]
    T --> EX["RabbitMQ exchange<br/>quotes.rpc"]
    EX --> RQ["Request queue<br/>quotes.request.q"]
    RQ --> S["Dịch vụ báo giá"]
    S --> RP["AMQP reply destination"]
    RP --> T
    T -->|"Spring reply Message"| G
    G -->|"Reply cho flow / caller"| A
~~~

**Outbound** được xác định theo hướng request: ứng dụng đang chạy flow **chủ động gửi yêu cầu ra** hệ thống bên ngoài. Reply đi ngược trở lại, nhưng endpoint vẫn là outbound gateway. Ở phía dịch vụ nhận, một **AMQP inbound gateway** có thể đóng vai trò đối ứng.

AMQP outbound gateway là một endpoint **request–reply**; **không phải** một cơ chế bảo đảm exactly-once hay một giao dịch nguyên tử xuyên hai ứng dụng.

## 2. Outbound gateway khác outbound adapter ở đâu?

| Tiêu chí | AMQP outbound channel adapter | AMQP outbound gateway |
| --- | --- | --- |
| Hợp đồng trao đổi | **One-way**: phát message | **Request–reply**: phát request, cần reply |
| Nguồn request | Spring MessageChannel | Spring MessageChannel |
| Đích gửi | Exchange + routing key | Exchange + routing key |
| Reply nghiệp vụ | Không tự phát lại vào flow | Nhận reply và tạo Spring reply Message |
| Reply-to/correlation | Không cần cho event một chiều | Cần cơ chế định tuyến và ghép reply đúng request |
| Timeout trả lời | Không phải hợp đồng chính | Phải đặt giới hạn thời gian chờ |
| Caller cần phản hồi ngay? | Không phù hợp nếu phải dùng reply | Thường phù hợp với RPC ngắn, bounded latency |
| Ví dụ | Publish OrderCreated | Gửi QuoteRequest, nhận QuoteResponse |

### 2.1. Bốn endpoint AMQP khi nhìn từ ứng dụng Spring

| Endpoint | Hướng giao tiếp | Ví dụ |
| --- | --- | --- |
| **Inbound channel adapter** | RabbitMQ → Spring MessageChannel, một chiều | Nhận sự kiện OrderCreated |
| **Outbound channel adapter** | Spring MessageChannel → RabbitMQ, một chiều | Phát sự kiện OrderCreated |
| **Inbound gateway** | RabbitMQ request → flow → RabbitMQ reply | Dịch vụ nhận request tính giá |
| **Outbound gateway** | Flow → RabbitMQ request → reply về flow | Bên bán hàng gọi dịch vụ tính giá |

**Messaging gateway (@MessagingGateway)** là một khái niệm nữa: nó cung cấp **giao diện phương thức Java** để ứng dụng gọi IntegrationFlow. Trong ví dụ bên dưới, @MessagingGateway đưa request vào channel nội bộ; **AMQP outbound gateway** là endpoint ở cuối channel thực sự làm việc với broker. Hai gateway không đồng nghĩa nhưng thường được dùng cùng nhau.

### 2.2. Khi nào không nên chọn request–reply?

Nếu nghiệp vụ chỉ cần thông báo OrderCreated cho các hệ thống xử lý sau, outbound adapter một chiều đơn giản hơn. Nếu một tác vụ cần nhiều phút hoặc bên đích có thể offline dài hạn, giữ hàng nghìn request đồng bộ chờ reply có thể làm cạn tài nguyên. Khi đó có thể chọn:

- Publish command/event một chiều, trả **job ID** ngay cho ứng dụng phía trước.
- Lưu trạng thái xử lý và công bố kết quả qua message riêng, callback hoặc API tra cứu.
- Dùng correlation/request ID để liên kết kết quả bất đồng bộ với công việc ban đầu.

**Có reply** không bắt buộc phải là một kết nối mạng song công duy nhất; nhưng nó yêu cầu một **hợp đồng kết quả**, cách tương quan và giới hạn thời gian rõ ràng.

## 3. Hiểu topology RabbitMQ trước khi gọi gateway

Outbound gateway dùng RabbitMQ như một hệ thống bên ngoài, nên vẫn cần:

1. **Exchange** để nhận request publish.
2. **Routing key** để exchange định tuyến.
3. **Binding** liên kết exchange với **request queue** phù hợp.
4. **Consumer/gateway phía nhận** để xử lý request.
5. **Reply destination** để bên nhận gửi response về phía caller.

~~~mermaid
flowchart TD
    CALL["Sales service<br/>AMQP outbound gateway"] --> EX["Direct exchange<br/>quotes.rpc"]
    EX -->|"quote.calculate"| Q["quotes.request.q"]
    Q --> SERVER["Pricing service<br/>AMQP inbound gateway"]
    SERVER -->|"Reply theo reply-to"| REPLY["Direct reply-to / reply queue"]
    REPLY --> CALL
~~~

**Direct exchange** định tuyến theo binding key; **topic exchange** theo pattern; **fanout exchange** gửi đến các queue được bind phù hợp. Bài này dùng direct exchange để dễ truy vết. Không nên gọi request queue là một Spring MessageChannel: queue thuộc RabbitMQ; MessageChannel thuộc ứng dụng.

### 3.1. Request queue durable không có nghĩa reply durable

Một queue bền vững chỉ giải quyết một phần trạng thái lưu trữ yêu cầu. Reply thường dùng **direct reply-to** hoặc reply queue do caller quản lý; reply có thể bị mất khi caller timeout hoặc ngắt kết nối. Việc queue giữ request không giúp caller tự động tìm lại một reply đã hết hạn.

Nếu cần lấy kết quả sau vài giờ, thiết kế **tra cứu trạng thái theo requestId** thường phù hợp hơn việc dựa vào một RPC reply đang chờ trong bộ nhớ.

## 4. Hợp đồng AMQP request–reply gồm những gì?

Trong Spring Integration, một request là **Message<?>** với **payload** và **headers**. Khi outbound gateway gửi request qua RabbitTemplate, một số thông tin được chuyển thành AMQP body/properties. Phía nhận có thể trả lại AMQP reply, rồi converter/header mapper biến nó thành Spring reply Message.

~~~text
Spring Message<QuoteRequest>
  payload: dữ liệu request
  headers: tracing / requestId / replyChannel nội bộ
                |
                v
AMQP outbound gateway + MessageConverter
                |
                v
AMQP request
  body: byte[] theo wire format
  properties: contentType, correlationId,
              replyTo và metadata được mapping
                |
                v
RabbitMQ request queue -> consumer
                |
                v
AMQP reply -> Spring reply Message -> caller
~~~

| Thông tin | Vai trò | Điều cần tránh |
| --- | --- | --- |
| **Body/payload** | Chứa dữ liệu QuoteRequest/QuoteResponse | Producer và consumer dùng wire format không tương thích |
| **contentType/encoding** | Chỉ cách diễn giải body | Khai JSON nhưng nội dung không hợp lệ |
| **reply-to** | Chỉ nơi bên nhận gửi AMQP reply | Nhầm với replyChannel nội bộ |
| **correlation ID** | Ghép AMQP reply với một request đang chờ | Dùng làm khóa idempotency mà không có hợp đồng |
| **requestId** | Định danh nghiệp vụ ổn định qua retry | Sinh requestId mới mỗi lần gửi lại cùng thao tác |
| **replyChannel** | Spring Integration định tuyến reply tới caller/flow | Serialize trực tiếp đối tượng MessageChannel lên RabbitMQ |
| **errorChannel** | Kênh xử lý ErrorMessage khi cấu hình phù hợp | Coi ErrorMessage tự động là reply nghiệp vụ |

**Correlation ID** được RabbitTemplate/endpoint sử dụng để ghép reply đúng request khi nhiều RPC cùng diễn ra. **RequestId hoặc idempotency key** phục vụ chống thực hiện nghiệp vụ hai lần. Hai trường có thể cùng giá trị theo thiết kế nhưng không nên mặc định rằng framework luôn tạo và duy trì cùng một ID cho chúng.

### 4.1. Reply-to là địa chỉ ở broker; replyChannel là đường nội bộ

AMQP **reply-to** nằm trong message properties, cho phía nhận biết cần publish phản hồi về đâu. Spring **replyChannel** thường là tham chiếu trong MessageHeaders cho endpoint nội bộ gửi kết quả về gateway. Chúng không cùng kiểu dữ liệu, không cùng phạm vi và không được copy thô qua lại.

### 4.2. Direct reply-to, temporary queue và fixed reply queue

| Cơ chế | Đặc điểm | Cần đánh giá |
| --- | --- | --- |
| **RabbitMQ direct reply-to** | Tối ưu RPC ngắn với pseudo-queue reply-to | Không phải durable queue cho caller offline |
| **Temporary/exclusive reply queue** | Reply queue riêng được tạo/phân bổ theo client | Vòng đời queue, connection và listener |
| **Fixed reply queue** | Caller nghe một reply queue xác định | Correlation, consumer cạnh tranh, quyền và cấu hình container |

Spring AMQP RabbitTemplate có thể sử dụng direct reply-to theo cấu hình và khả năng broker. Không nên tự khẳng định mọi môi trường luôn dùng cách này hoặc mọi lần request–reply đều được lưu bền.

## 5. Chọn kiểu payload và converter cho RPC

Ví dụ học tập sẽ dùng **String** theo hợp đồng:

~~~text
Request: requestId|productId|quantity
Reply:   OK|requestId|totalVnd
Error:   ERROR|requestId|errorCode
~~~

Với request:

~~~text
req-1001|SKU-42|2
~~~

Phía báo giá tính đơn giá giả lập 50.000 VND và trả:

~~~text
OK|req-1001|100000
~~~

Trong hệ thống thực tế, nên định nghĩa JSON, Avro hoặc Protobuf theo schema có version. Ví dụ:

~~~json
{
  "requestId": "req-1001",
  "productId": "SKU-42",
  "quantity": 2,
  "schemaVersion": 1
}
~~~

Reply có thể là:

~~~json
{
  "requestId": "req-1001",
  "status": "OK",
  "totalVnd": 100000,
  "schemaVersion": 1
}
~~~

**MessageConverter** chuyển payload String/DTO sang AMQP body và chuyển body reply ngược lại. **Transformer** trong flow chuẩn hóa dữ liệu nghiệp vụ giữa các endpoint. Nếu cả transformer lẫn converter đều serialize JSON, rất dễ xảy ra double-encoding. Hãy xác định một nơi chịu trách nhiệm cho mỗi phép chuyển đổi.

## 6. Ví dụ Java DSL: hai ứng dụng gọi và phục vụ báo giá

Ví dụ tách thành hai tiến trình:

- **Ứng dụng A (requester):** phương thức Java gọi @MessagingGateway; message đi tới **quoteRpcRequests**, rồi **AMQP outbound gateway** publish vào RabbitMQ và nhận reply.
- **Ứng dụng B (provider):** **AMQP inbound gateway** lắng nghe **quotes.request.q**, gọi QuoteCalculator và trả String reply.

Để minh họa Spring Integration Java DSL, ví dụ dùng Spring Boot, Java 17+ và các dependency Spring Integration/Spring AMQP tương thích do Spring Boot quản lý.

### 6.1. Dependencies cho hai ứng dụng

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

Mỗi ứng dụng cần RabbitMQ ConnectionFactory/RabbitTemplate với host, port, virtual host, credential và TLS phù hợp môi trường. Không đưa mật khẩu thật vào source control; dùng secret manager hoặc biến môi trường.

### 6.2. Ứng dụng B: topology và inbound gateway

Phía cung cấp báo giá thường được triển khai trước để request queue/exchange/binding đã sẵn sàng.

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class QuoteProviderConfiguration {

    public static final String EXCHANGE = "quotes.rpc";
    public static final String ROUTING_KEY = "quote.calculate";
    public static final String REQUEST_QUEUE = "quotes.request.q";

    @Bean
    public DirectExchange quoteExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue quoteRequestQueue() {
        return new Queue(REQUEST_QUEUE, true);
    }

    @Bean
    public Binding quoteBinding(
            Queue quoteRequestQueue,
            DirectExchange quoteExchange) {
        return BindingBuilder.bind(quoteRequestQueue)
            .to(quoteExchange)
            .with(ROUTING_KEY);
    }

    @Bean
    public IntegrationFlow quoteProviderFlow(
            ConnectionFactory connectionFactory,
            QuoteCalculator quoteCalculator) {
        return IntegrationFlow
            .from(Amqp.inboundGateway(
                connectionFactory, REQUEST_QUEUE))
            .handle(String.class, (request, headers) ->
                quoteCalculator.calculate(request))
            .get();
    }
}
~~~

**Giải thích:** RabbitMQ direct exchange **quotes.rpc** định tuyến request có routing key **quote.calculate** tới **quotes.request.q**. AMQP inbound gateway nhận AMQP delivery qua listener, chuyển request vào integration flow. Handler tạo reply, gateway gửi về địa chỉ reply-to theo hợp đồng.

Các bean topology chỉ được khai báo trên RabbitMQ khi ứng dụng có **RabbitAdmin/AmqpAdmin** phù hợp với quyền khai báo hoặc hạ tầng bên ngoài đã provision exchange/queue/binding. Không nên giả định cứ có @Bean thì topology broker chắc chắn tồn tại.

### 6.3. Ứng dụng B: handler trả kết quả nghiệp vụ

~~~java
import org.springframework.stereotype.Service;

@Service
public class QuoteCalculator {

    public String calculate(String body) {
        String[] fields = body.split("\\|", -1);
        if (fields.length != 3) {
            return "ERROR|UNKNOWN|INVALID_FORMAT";
        }

        String requestId = fields[0];
        String productId = fields[1];
        if (!requestId.matches("[A-Za-z0-9_-]{1,64}")
                || !productId.matches("[A-Za-z0-9_-]{1,64}")) {
            return "ERROR|UNKNOWN|INVALID_ID";
        }

        int quantity;
        try {
            quantity = Integer.parseInt(fields[2]);
        } catch (NumberFormatException ex) {
            return "ERROR|" + requestId + "|INVALID_QUANTITY";
        }

        if (quantity <= 0 || quantity > 100) {
            return "ERROR|" + requestId + "|INVALID_QUANTITY";
        }

        long totalVnd = 50_000L * quantity;
        return "OK|" + requestId + "|" + totalVnd;
    }
}
~~~

Handler dùng ví dụ giá cố định, **không ghi database** và không có side effect. Các request sai cấu trúc được trả về **business error** có mã để caller phân biệt với timeout hoặc mất kết nối. Trong nghiệp vụ thật, mã lỗi, validation, authorization, schemaVersion và giá trị tiền tệ phải được thiết kế chính thức.

### 6.4. Ứng dụng A: AMQP outbound gateway flow

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class QuoteRequesterConfiguration {

    @Bean
    public IntegrationFlow quoteOutboundFlow(
            RabbitTemplate rabbitTemplate) {
        return IntegrationFlow.from("quoteRpcRequests")
            .handle(Amqp.outboundGateway(rabbitTemplate)
                .exchangeName("quotes.rpc")
                .routingKey("quote.calculate"))
            .get();
    }
}
~~~

Trong flow này, **quoteRpcRequests** là request channel nội bộ, được tạo/resolve theo DSL và cấu hình liên quan. Outbound gateway sẽ publish request qua RabbitTemplate và chuyển reply AMQP thành Spring reply message để flow hoặc caller tiếp tục.

**Khác outbound adapter:** nếu thay outboundGateway bằng outboundAdapter, flow không còn lời hứa nhận String reply từ dịch vụ tính giá. Do đó phương thức Java đang cần kết quả sẽ không có hợp đồng request–reply tương ứng.

### 6.5. Ứng dụng A: giao diện Java gọi flow

~~~java
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
    defaultRequestChannel = "quoteRpcRequests",
    defaultReplyTimeout = "6500")
public interface QuoteRpcGateway {
    String requestQuote(String requestBody);
}
~~~

Ứng dụng khác có thể inject QuoteRpcGateway và gọi:

~~~java
String reply = quoteRpcGateway.requestQuote(
    "req-1001|SKU-42|2");

// Kết quả thành công mong đợi:
// OK|req-1001|100000
~~~

**@MessagingGateway** cung cấp giao diện Java, đẩy payload vào channel và nhận reply của flow. **Amqp.outboundGateway(...)** mới là bước giao tiếp AMQP ra RabbitMQ. Đặt hai thành phần trong cùng ứng dụng giúp business code không phải gọi trực tiếp RabbitTemplate.

### 6.6. Đặt timeout cho cả hai lớp chờ

Có thể cấu hình thời hạn chờ reply của RabbitTemplate:

~~~yaml
spring:
  rabbitmq:
    template:
      reply-timeout: 5s
~~~

Trong ví dụ, RabbitTemplate chờ tối đa khoảng **5 giây**, còn @MessagingGateway được khai báo **defaultReplyTimeout = 6500 ms**. Cách đặt này tránh việc outer gateway hết hạn sớm hơn reply timeout nội bộ một cách không chủ đích. Đây chỉ là giá trị minh họa: tổng độ trễ còn gồm thời gian gửi request vào channel, network, chờ queue, xử lý server và convert reply.

Khi RabbitTemplate không nhận reply đúng hạn, hành vi trả về **null, exception hoặc đường lỗi tiếp theo** phụ thuộc endpoint và API/configuration cụ thể. Caller phải xử lý cả việc không có kết quả lẫn lỗi chuyển đổi; **không** mặc định timeout nào cũng trả một String như ERROR|TIMEOUT.

### 6.7. Trình tự chạy thử

1. Chuẩn bị RabbitMQ; ứng dụng A và B dùng đúng virtual host, exchange/routing key và converter tương thích.
2. Khởi động ứng dụng B; xác minh exchange **quotes.rpc**, queue **quotes.request.q** và binding **quote.calculate** đã có trên broker.
3. Khởi động ứng dụng A và gọi **requestQuote("req-1001|SKU-42|2")**.
4. Kiểm tra reply **OK|req-1001|100000** được trả về từ QuoteRpcGateway.
5. Gọi với quantity 0; kiểm tra reply có mã **INVALID_QUANTITY**.
6. Tạm dừng ứng dụng B hoặc tạo xử lý chậm trong test để kiểm tra timeout của phía caller.
7. Gửi hai request khác requestId đồng thời và xác nhận mỗi caller nhận đúng kết quả tương ứng.

Ví dụ dùng hai tiến trình để quan sát rõ request queue, reply destination và các sự cố mạng. Nếu chạy cả requester lẫn provider trong một JVM để demo, không nên suy ra các tình huống consumer disconnect và broker reconnect đã được kiểm chứng.

## 7. Điều gì xảy ra khi không có reply?

Đối với outbound gateway, **nhận được business reply** là mục tiêu của một lượt trao đổi. Cần xem xét nhiều loại lỗi hơn là chỉ “broker có kết nối không”.

~~~mermaid
sequenceDiagram
    participant A as Caller
    participant G as Outbound gateway
    participant B as RabbitMQ
    participant S as Provider
    A->>G: QuoteRequest req-1001
    G->>B: Publish AMQP request
    B->>S: Request delivery
    S->>S: Xử lý chậm / tắc downstream
    Note over G: Hết hạn chờ reply
    G-->>A: Timeout / không có kết quả
    S-->>B: Reply req-1001 đến muộn
    B-->>G: Reply đến sau thời hạn
    Note over G,B: Cần chính sách xử lý reply muộn
~~~

**Timeout không chứng minh provider chưa thực hiện nghiệp vụ.** Request có thể đã được broker nhận và provider đã ghi database, nhưng reply mất hoặc đến trễ. Đây là lý do nhiều API tích hợp cần cả idempotency lẫn khả năng tra cứu trạng thái.

### 7.1. Các thời hạn chờ khác nhau

| Timeout/giới hạn | Điểm áp dụng | Hệ quả nếu vượt |
| --- | --- | --- |
| **Gửi request vào channel** | @MessagingGateway hoặc request channel | Không gửi được request vào flow theo thời hạn mong đợi |
| **Kết nối/publish AMQP** | RabbitTemplate/ConnectionFactory và RabbitMQ client | Có thể thất bại hoặc trạng thái publish chưa chắc chắn |
| **RabbitTemplate reply timeout** | Đợi AMQP reply tương quan | Caller phía outbound gateway không nhận được reply đúng hạn |
| **Spring gateway reply timeout** | Phương thức Java đợi Spring reply Message | Phương thức Java có thể không nhận được kết quả |
| **Downstream timeout** | Service bên provider gọi HTTP/JDBC/SFTP hoặc hệ thống khác | Provider không tạo reply kịp hoặc phát sinh lỗi |

Không nên đặt cùng một timeout cho mọi lớp theo thói quen. Ví dụ, nếu provider có API HTTP downstream với timeout 10 giây trong khi caller chỉ đợi AMQP reply 3 giây, hầu hết request chậm sẽ thành reply đến muộn. Cần thiết kế **ngân sách thời gian** từ tổng SLA của người dùng.

### 7.2. Trả lời đến muộn hoặc đến nhầm request

Khi một caller gửi nhiều request đồng thời, AMQP RPC phải ghép reply bằng correlation phù hợp. RabbitTemplate và gateway quản lý phần này theo cấu hình tương ứng; nếu tự thay đổi message properties hoặc dùng custom reply queue, cần kiểm tra:

- Correlation ID của reply có khớp request đang chờ hay không.
- Sau timeout, một reply đến muộn được ghi log/đếm metric và bỏ qua hay đối soát ra sao.
- Caller không vô tình lấy reply của request cũ cho request mới.
- Fixed reply queue có đủ quyền, consumer và cơ chế điều phối khi nhiều instance dùng chung không.
- RequestId trong **payload nghiệp vụ** có được trả lại để kiểm chứng nội dung không.

Không nên tự chuyển toàn bộ properties của message khác vào reply và hy vọng framework luôn tương quan đúng. Những trường AMQP dành cho hạ tầng RPC cần được mapping bằng converter/header mapper hoặc cơ chế được API hỗ trợ.

## 8. Bốn tín hiệu xác nhận không được đánh đồng

Một hệ thống RabbitMQ request–reply có thể sử dụng nhiều tín hiệu:

| Tín hiệu | Bên phát ra | Nó chứng minh điều gì? | Điều chưa được chứng minh |
| --- | --- | --- | --- |
| **Publisher confirm** | RabbitMQ → publisher request/reply | Broker xác nhận publish theo cơ chế publisher confirms | Provider đã xử lý request |
| **Publisher return** | RabbitMQ → publisher | Request không route được trong điều kiện mandatory/returns phù hợp | Provider đã chạy hoặc đã thất bại |
| **Consumer ACK/NACK** | Listener/provider → RabbitMQ | Kết quả xác nhận delivery request theo mode | Caller đã nhận và đọc business reply |
| **Business reply** | Provider → caller qua AMQP | Một kết quả theo hợp đồng ứng dụng đã được gửi/nhận | Mọi side effect liên hệ đều có tính nguyên tử xuyên hệ thống |

### 8.1. Publisher confirm không phải business reply

RabbitMQ có thể ACK publish ở exchange trong khi request còn nằm trong queue, provider chưa chạy. Bên gọi cần **QuoteResponse**, nên publisher confirm không thể thay thế một AMQP reply Message.

### 8.2. Trường hợp unroutable

Nếu exchange tồn tại nhưng routing key không trùng binding, request có thể **không đến bất kỳ queue nào**. Cơ chế publisher returns cần bật **mandatory** và cấu hình return handling phù hợp để quan sát trường hợp này.

Ví dụ cấu hình Spring Boot cho publisher trong trường hợp cần theo dõi xác nhận:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
      reply-timeout: 5s
~~~

**Lưu ý:** Bật các cờ trên **không tự đảm bảo AMQP outbound gateway biến mọi confirm/return thành business reply**. Nếu cần theo dõi kỹ publish ở mức RabbitTemplate, hãy thiết kế callback/CorrelationData và chính sách đánh giá kết quả phù hợp. Mỗi trường hợp RPC timeout cần được phân tích theo cả routing, consumer và reply destination.

### 8.3. ACK của consumer là sự kiện phía nhận

Inbound gateway của provider dùng listener container. Với **AcknowledgeMode.AUTO**, container thường ACK khi listener callback hoàn tất theo quy tắc thành công/lỗi. Nhưng ACK không chứng minh caller thực sự đọc được reply.

Nếu dùng **MANUAL**, ứng dụng/provider phải chịu trách nhiệm ACK/NACK delivery theo cấu hình. Không chọn manual ACK chỉ vì muốn “RPC an toàn hơn”: nếu quên ACK, request có thể tồn ở trạng thái unacked, giảm throughput và bị giao lại khi connection đóng.

## 9. Lỗi nghiệp vụ, lỗi kỹ thuật và đường xử lý lỗi

AMQP RPC cần định nghĩa **hai kiểu kết quả**:

- **Kết quả nghiệp vụ hợp lệ**: OK, INVALID_QUANTITY, PRODUCT_NOT_FOUND, LIMIT_EXCEEDED... dưới schema reply mà caller hiểu.
- **Lỗi kỹ thuật**: mất broker, permission denied, không route được, converter lỗi, provider crash, timeout, downstream database/HTTP không sẵn sàng.

Không nên biến mọi exception thành chuỗi lỗi nghiệp vụ giả định; làm vậy caller có thể nhầm sự cố hạ tầng với yêu cầu bị từ chối đúng quy tắc.

### 9.1. Ma trận lỗi theo vị trí

| Vị trí lỗi | Ví dụ | Cách ứng xử hợp lý |
| --- | --- | --- |
| **Trước khi gửi** | Payload không hợp lệ, serialize lỗi | Trả lỗi validate cho caller, không publish request |
| **Exchange/routing** | Exchange thiếu, binding sai, unroutable | Cảnh báo cấu hình, returns/timeout, đối soát |
| **Listener/provider** | Consumer dừng hoặc broker không giao được | Request chờ ở queue theo policy; caller có thể timeout |
| **Business handler** | Số lượng không hợp lệ | Tạo business reply có mã lỗi ổn định |
| **Downstream của provider** | JDBC/HTTP timeout | Retry có giới hạn, lỗi kỹ thuật/đối soát; cân nhắc trả reply lỗi |
| **Reply publish** | Provider xử lý xong nhưng gửi reply thất bại | Caller timeout; server cần theo dõi trạng thái thực |
| **Correlation/reply queue** | Reply không ghép được hoặc đến muộn | Đếm orphan/late reply, kiểm tra cấu hình |

### 9.2. replyChannel và errorChannel

Trong Spring Integration:

- **replyChannel** xác định nơi message phản hồi đi tới ở **hệ thống nội bộ**.
- **errorChannel** là nơi ErrorMessage có thể được gửi khi điểm xử lý và channel được cấu hình theo đường lỗi tương ứng.
- **AMQP reply-to** xác định địa chỉ ở **RabbitMQ** mà provider trả reply về caller.

Một handler ném exception **không bảo đảm** caller nhận ngay một AMQP reply kiểu ERROR. Tùy DirectChannel/ExecutorChannel, listener container và error handler, exception có thể được truyền ngược, chuyển thành ErrorMessage, tạo NACK/requeue hoặc khiến caller đợi đến timeout.

Với lỗi có thể dự báo trong nghiệp vụ, hãy tạo **reply lỗi theo schema**. Với lỗi kỹ thuật, đừng tiết lộ stack trace, credential hoặc thông tin database trong payload phản hồi.

### 9.3. Đường lỗi đồng bộ và bất đồng bộ khác nhau

Ở **DirectChannel**, request handler thường chạy ngay trên chuỗi gọi, exception có thể lan đến gateway/listener. Ở **ExecutorChannel**, request được giao cho worker khác; lỗi có thể phát sinh sau khi bước gửi message vào channel thành công. Gateway đang chờ reply cần được cấu hình timeout/error flow rõ ràng.

Do đó chỉ thay DirectChannel bằng ExecutorChannel để tăng throughput **có thể thay đổi thời điểm quan sát lỗi**, không chỉ hiệu năng.

## 10. Retry, redelivery và idempotency

Retry có thể xảy ra ở ít nhất ba tầng:

1. **Caller retry** vì không nhận reply trong thời hạn.
2. **Broker redeliver** request do consumer không ACK trước khi connection bị đóng hoặc xử lý lỗi.
3. **Provider retry downstream** vì một thao tác database/HTTP thất bại tạm thời.

Nếu request tạo side effect, ba cơ chế này có thể chồng lên nhau và tạo **nhiều lần thực thi**.

### 10.1. Ví dụ thanh toán thay vì báo giá

Giả sử ứng dụng gửi requestId **pay-1001** đến dịch vụ thanh toán:

1. Provider ghi giao dịch thành công trong database.
2. Provider mất kết nối trước khi reply đến caller.
3. Caller timeout và gửi lại **pay-1001**.
4. Broker cũng có thể redeliver request cũ chưa được ACK.

**Nếu không có idempotency, hai lời gọi có thể tạo hai giao dịch.** Việc có correlation ID, publisher confirms hoặc durable queue không giải quyết trọn vẹn điều này.

### 10.2. Thiết kế xử lý trùng tại nơi sinh side effect

Một provider có side effect cần:

- **requestId/idempotencyKey** ổn định giữa mọi lần retry của cùng thao tác.
- Kiểm tra requestId có tồn tại trong bảng xử lý hay chưa; dùng **unique constraint** hoặc cơ chế tương đương để bảo vệ khi nhiều consumer chạy đồng thời.
- Nếu requestId đã xử lý thành công, **trả lại kết quả đã lưu**, không chạy side effect lại.
- Nếu requestId giống nhưng payload khác, trả lỗi hợp đồng thay vì âm thầm tái sử dụng kết quả.
- Khi có thể, ghi business effect và trạng thái idempotency trong **cùng database transaction**.
- Thiết kế đối soát khi transaction commit thành công nhưng reply gửi thất bại.

### 10.3. Poison message và DLQ

Nếu payload sai schema mà listener ném exception rồi broker requeue vô hạn, request lỗi có thể được giao lại liên tục. Cần phân biệt:

| Loại lỗi | Chính sách gợi ý |
| --- | --- |
| Business input không hợp lệ | Trả một business reply lỗi có cấu trúc |
| Lỗi tạm thời có thể hồi phục | Retry hữu hạn với backoff |
| Sai schema, không thể parse | Cách ly/đưa vào DLQ theo chính sách, ghi nhận để xử lý thủ công |
| Kết quả side effect không rõ | Đối soát qua idempotencyKey/trạng thái nghiệp vụ |

**Đưa request vào DLQ không tự gửi reply cho caller**. Caller có thể đã timeout từ trước, nên những workflow cần kết quả bền vững phải có cơ chế tra cứu trạng thái riêng.

## 11. Threading, concurrency và backpressure

AMQP outbound gateway phải chờ một kết quả từ xa. So với outbound adapter một chiều, nó tạo thêm áp lực lên **số request đang chờ**, **reply correlation state** và **thời gian sống của lời gọi**.

| Thành phần | Điều cần kiểm soát |
| --- | --- |
| **DirectChannel** | Giữ đường gọi đồng bộ; remote reply chậm có thể giữ thread caller |
| **ExecutorChannel** | Queue/executor capacity, lỗi bất đồng bộ, replyChannel và timeout |
| **QueueChannel** | Poller, độ bền message, request bị chậm trước khi thực sự publish |
| **RabbitTemplate** | Reply timeout, số RPC đang chờ, kết nối và reply destination |
| **Provider listener** | Concurrency/prefetch, ACK, request xử lý dài, downstream latency |
| **RabbitMQ queue** | Ready/unacked backlog và chính sách giao nhận |

### 11.1. Khả năng chịu tải không tăng theo số thread vô hạn

Giả sử provider xử lý được **80 request/giây**, nhưng caller gửi **500 request/giây** liên tục. Nếu mỗi request phải chờ reply, backlog và số request in-flight sẽ tăng; sớm hay muộn timeout hoặc cạn tài nguyên.

Tăng số listener hoặc ExecutorChannel có thể giúp khi CPU/connection còn dư, nhưng không thể giải quyết giới hạn cứng của database hoặc dịch vụ downstream. Cần đo request latency, p95/p99, số reply timeout, backlog, connection usage và số request đang chờ.

### 11.2. Khi QueueChannel nằm trước outbound gateway

QueueChannel có thể tách producer khỏi polling consumer, nhưng tạo thêm thời gian chờ ở **hàng đợi nội bộ** trước khi request ra RabbitMQ. Nếu caller vẫn cần reply đồng bộ trong một khoảng ngắn, hàng đợi này có thể làm RPC timeout trước khi provider được gọi.

QueueChannel mặc định **không phải storage bền vững**; nếu cần khôi phục request sau crash, phải thiết kế MessageStore bền vững, broker hoặc outbox theo yêu cầu.

### 11.3. Đặt ngân sách timeout theo tải thực tế

Ví dụ có SLA 3 giây cho kết quả báo giá, nên xác định ngân sách cho:

~~~text
Tổng SLA = xếp hàng nội bộ
         + publish/route qua RabbitMQ
         + chờ provider
         + xử lý nghiệp vụ/downstream
         + publish và nhận reply
         + convert kết quả
~~~

Đặt một reply timeout lớn hơn SLA không tự giúp người dùng có kết quả sớm. Nếu request thường chậm hơn SLA, cần tối ưu downstream hoặc đổi sang mô hình bất đồng bộ có trạng thái.

## 12. Bảo mật, vòng đời kết nối và quan sát

AMQP outbound gateway phụ thuộc RabbitTemplate, ConnectionFactory, broker topology, listener reply và messaging flow. Các tài nguyên này có vòng đời riêng.

### 12.1. Vòng đời và graceful shutdown

Nhiều endpoint Spring Integration tham gia **Lifecycle/SmartLifecycle** với start(), stop(), isRunning(), autoStartup và phase. Tuy nhiên **isRunning() = true không chứng minh broker đang khỏe hoặc reply path còn khả dụng**.

Một quy trình shutdown phù hợp có thể gồm:

1. Ngừng nhận hoặc sinh thêm request mới ở lớp API/business.
2. Theo dõi số RPC đang chờ và deadline của chúng.
3. Cho các request ngắn hoàn tất trong giới hạn thời gian, hoặc ghi trạng thái có thể phục hồi.
4. Đóng consumer/endpoint và các connection dùng chung theo lifecycle của Spring.
5. Khi restart, dùng requestId/idempotency để giải quyết các thao tác đã thực hiện nhưng chưa được caller xác nhận.

**stop() không tự gửi reply lỗi cho tất cả caller đang chờ**, không tự hủy side effect phía provider và không bảo đảm mọi message trong channel đã xử lý xong.

### 12.2. Bảo mật đường request và reply

- Dùng TLS nếu môi trường yêu cầu mã hóa và xác thực máy chủ.
- Tài khoản RabbitMQ được giới hạn quyền publish/consume/declare theo virtual host, exchange và queue.
- Phân quyền nghiệp vụ phải diễn ra ở provider; quyền publish vào queue **không thay thế** authorization của API tính giá/thanh toán.
- Không ghi credential, token hoặc payload nhạy cảm nguyên văn vào log, reply hoặc header không được kiểm soát.
- Giới hạn kích thước request/reply, schema và định dạng để tránh payload bất thường gây cạn bộ nhớ.
- Kiểm soát requestId/correlationId có thể từ nguồn không tin cậy, không dùng chúng trực tiếp như đường dẫn file hoặc câu SQL.

### 12.3. Các metric nên theo dõi

| Vị trí | Metric/log quan trọng |
| --- | --- |
| **Caller Java/messaging gateway** | Request count, reply count, timeout, exception, latency |
| **AMQP outbound gateway** | Publish attempts, reply conversion errors, late replies, correlation failures |
| **RabbitTemplate** | Connection failures, confirms/returns nếu cấu hình, reply timeout |
| **RabbitMQ** | Request queue ready/unacked, consumer count, publish/deliver rate |
| **Provider** | Active requests, processing latency, success/business error/technical error |
| **Nghiệp vụ** | requestId đã xử lý, idempotency hit, side effect thành công, kết quả đối soát |

Một dashboard chỉ hiển thị queue depth không đủ. Queue request có thể trống vì provider đã lấy message nhưng đang xử lý chậm; số **unacked**, số RPC đang chờ và latency phải được xem cùng nhau.

## 13. Bộ kiểm thử theo hợp đồng request–reply

| Tình huống | Thao tác | Kết quả cần kiểm chứng |
| --- | --- | --- |
| Happy path | Gửi req-1001/SKU-42/2 | Nhận OK|req-1001|100000 |
| Input không hợp lệ | Quantity = 0 | Nhận business reply INVALID_QUANTITY |
| Provider chưa chạy | Gửi khi request queue có nhưng consumer dừng | Caller có thể timeout; backlog tăng theo policy |
| Sai exchange/routing key | Cố tình publish vào route không tồn tại | Error/return/timeout theo cấu hình, không báo business success |
| Hai request đồng thời | Gửi hai requestId khác nhau | Không trả nhầm reply giữa các caller |
| Handler xử lý chậm | Tạo delay vượt reply timeout | Caller hết hạn chờ; reply đến muộn được xử lý rõ |
| Reply destination sai | Tạo cấu hình reply không hợp lệ trong test | Có metric và lỗi, không treo vô hạn |
| Converter sai | Request JSON nhưng provider đòi String theo hợp đồng khác | Lỗi chuyển đổi được phát hiện và phân loại |
| Provider exception | Downstream giả lập lỗi kỹ thuật | Quan sát ACK/requeue/error handling/timeout |
| Request redelivery | Consumer chết trước ACK | Xử lý lại theo policy; side effect idempotent |
| Caller retry | Gửi lại cùng requestId sau timeout | Không thực hiện nghiệp vụ trùng |
| Broker restart | Ngắt kết nối giữa request/reply | Quan sát reconnect, trạng thái không rõ và timeout |
| Tải cao | Tạo burst concurrent RPC | Không vượt capacity; đo p95/p99 và số request đang chờ |
| Graceful shutdown | Dừng requester/provider khi có RPC | Không giả định tất cả reply đã đến; khôi phục theo hợp đồng |

### 13.1. Kiểm thử đồng thời và correlation

Khi có nhiều request, không chỉ xác minh mỗi reply có nội dung hợp lệ. Hãy tạo requestId riêng cho mỗi lần gọi, gửi song song, rồi xác nhận **reply.requestId khớp requestId đã gửi**. Nếu ứng dụng dùng custom reply queue hoặc custom headers, cần kiểm tra cả AMQP correlation mapping và khóa nghiệp vụ.

### 13.2. Kiểm thử mất reply sau khi đã thực hiện

Với handler có side effect, tạo tình huống provider đã ghi database nhưng reply không đến caller. Sau khi caller timeout, gửi lại cùng requestId. Kết quả đúng là **không tạo side effect thứ hai** và có thể trả lại kết quả đã xử lý hoặc cho phép tra cứu trạng thái.

### 13.3. Kiểm thử hiệu năng và timeout

Đo riêng thời gian publish request, chờ queue, xử lý provider và nhận reply. Một reply timeout không giải thích được phần nào chậm nếu thiếu log/trace. Dùng metric theo endpoint, correlation ID và requestId để liên kết sự cố xuyên hai ứng dụng.

## 14. Khi nào nên chuyển từ RPC sang workflow bất đồng bộ?

AMQP outbound gateway phù hợp nhất khi caller thực sự cần kết quả, thời gian xử lý có giới hạn dự đoán được và bên cung cấp có thể đáp ứng SLA.

| Đặc điểm | RPC qua AMQP outbound gateway | Workflow bất đồng bộ |
| --- | --- | --- |
| Caller cần kết quả ngay | Phù hợp nếu latency ngắn và ổn định | Cần API trạng thái/callback |
| Tác vụ chạy nhiều phút | Dễ gây timeout và in-flight backlog | Thường phù hợp hơn |
| Provider tạm offline | Request có thể nằm ở queue nhưng caller vẫn timeout | Có thể chấp nhận công việc và xử lý sau |
| Khôi phục sau restart | Cần idempotency và đối soát | Cần durable job/event state |
| Kết quả đến sau lâu | Late reply có thể không còn caller chờ | Lưu trạng thái đến khi được tra cứu |

Ví dụ, một yêu cầu **xuất báo cáo qua SFTP** mất 20 phút không nên mặc định được thiết kế như RPC đợi response trực tiếp. Có thể nhận lệnh tạo báo cáo, trả job ID, phát trạng thái hoàn thành qua AMQP/JMS/Kafka hoặc cho phép tra cứu HTTP. Nếu phải đồng bộ, hãy giới hạn công việc theo thời gian cho phép của gateway.

## 15. Sai lầm thường gặp

**Chọn outbound adapter nhưng lại đòi reply nghiệp vụ.** Channel adapter là one-way; gateway mới có hợp đồng request–reply.

**Nhầm @MessagingGateway với AMQP outbound gateway.** Một bên nối interface Java với integration flow, bên kia nối integration flow với giao thức AMQP.

**Coi publisher confirm ACK là QuoteResponse.** Confirm chỉ là xác nhận publish ở broker, không phải kết quả của QuoteCalculator.

**Nhầm Spring replyChannel với AMQP reply-to.** Một cái nằm trong MessageHeaders nội bộ, cái kia định tuyến phản hồi tại broker.

**Cho rằng request queue durable thì reply cũng được lưu bền.** Reply destination có chính sách riêng; direct reply-to không phải durable job-result store.

**Tưởng caller timeout nghĩa provider chưa xử lý.** Provider có thể đã commit, reply bị chậm hoặc mất. Hãy dùng idempotency/đối soát.

**Tự thay correlation mà không kiểm tra tương quan.** Điều này có thể gây reply đến nhưng không tới caller đang chờ.

**Trả null trong flow đang đợi reply.** Gateway có thể không nhận được response hợp lệ và caller timeout.

**Biến mọi exception thành business reply không có schema.** Caller không phân biệt được dữ liệu sai, lỗi hệ thống hoặc trạng thái kết quả không chắc chắn.

**Retry vô hạn cho request không hợp lệ.** Dữ liệu sai cần trả lỗi hoặc cách ly; không nên tạo poison-message loop.

**Dùng correlation ID làm khóa chống trùng duy nhất.** Correlation là định danh một tương tác; requestId/idempotencyKey phải ổn định theo nghiệp vụ.

**Tăng concurrency khi downstream đã quá tải.** Có thể làm nhiều caller timeout hơn và tiêu tốn connection/thread.

**Chỉ kiểm tra isRunning.** Gateway có thể báo đang chạy nhưng broker, reply route hoặc converter đang lỗi.

## 16. Câu hỏi tự kiểm tra

1. Vì sao AMQP outbound gateway phù hợp khi flow cần kết quả báo giá mà outbound channel adapter không đáp ứng?
2. Ứng dụng A và B trong ví dụ có những gateway nào? Vai trò của @MessagingGateway khác AMQP outbound gateway ở đâu?
3. Request queue, exchange, binding và reply destination có nhiệm vụ khác nhau thế nào?
4. AMQP reply-to và Spring Integration replyChannel khác nhau ở phạm vi và kiểu dữ liệu nào?
5. Vì sao cần correlation ID khi có nhiều request–reply đang thực hiện đồng thời?
6. Correlation ID và requestId/idempotencyKey có thể dùng thay nhau một cách mặc định không?
7. Publisher confirm, publisher return, consumer ACK và business reply khác nhau ở điểm nào?
8. Nếu provider dừng nhưng request queue vẫn tồn tại, caller có thể gặp hiện tượng gì?
9. Nếu handler xử lý thành công nhưng reply đến sau timeout, caller nên làm gì trước khi retry?
10. Trả null từ service activator trong flow request–reply có thể gây hậu quả gì?
11. Vì sao không nên sử dụng một reply timeout rất dài để xử lý công việc kéo dài hàng chục phút?
12. Khi đổi từ DirectChannel sang ExecutorChannel, phải kiểm tra thêm những rủi ro nào?
13. Làm sao kiểm thử rằng reply của hai request song song không bị trả nhầm?
14. Trường hợp thanh toán đã commit nhưng reply mất, cách nào giúp hạn chế thanh toán trùng?
15. Những metric nào nên quan sát để phát hiện chậm ở request queue, provider hoặc reply path?

## Tổng kết

**AMQP outbound gateway** nối một **MessageChannel** nội bộ với RabbitMQ theo hợp đồng **request–reply**: publish request tới exchange/queue, chờ AMQP reply theo reply-to/correlation, rồi đưa kết quả trở lại flow hoặc caller. Khác với outbound adapter một chiều, gateway phải quản lý **timeout, ghép reply, lỗi và reply đến muộn**. Publisher confirm, returned message, consumer ACK và business reply là các tín hiệu độc lập, không thể thay thế nhau. Trong một hệ thống Spring Integration kết nối File, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, hãy chọn RPC chỉ khi cần kết quả đúng hạn; khi request có side effect, bắt buộc thiết kế idempotency và đối soát, đồng thời kiểm soát thread, connection, bảo mật và khả năng phục hồi sau sự cố.
