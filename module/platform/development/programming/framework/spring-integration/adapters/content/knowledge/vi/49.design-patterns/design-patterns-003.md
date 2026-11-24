# Gateway Request–Reply Pattern trong Spring Integration Adapters

> **Chương:** Design patterns  
> **Chủ đề:** Gateway request-reply pattern  
> **Bối cảnh module:** SPRING_INTEGRATION_ADAPTERS — kết nối hệ thống ngoài qua inbound/outbound adapter, gateway, poller và MessageChannel; luồng trao đổi file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; thiết kế hợp đồng message, xử lý lỗi và vòng đời kết nối.

## 1. Bài toán: ứng dụng gửi yêu cầu và cần kết quả

Trong hệ thống tích hợp, không phải mọi message đều là sự kiện phát một chiều. Một dịch vụ tính giá có thể cần hỏi hệ thống định giá: “Giá cuối cùng của sản phẩm A cho khách hàng B là bao nhiêu?”. Một cổng HTTP có thể nhận yêu cầu kiểm tra đơn hàng rồi cần trả phản hồi cho client. Một ứng dụng Java cũng muốn **gọi một phương thức bình thường**, trong khi phía sau là nhiều bước message-based.

**Gateway Request–Reply Pattern** giải quyết khoảng cách đó: bên gửi đưa một **request message** vào flow và nhận lại một **reply message** tương ứng, hoặc một kết quả lỗi/timeout theo hợp đồng. Gateway che giấu phần lớn chi tiết message/channel trước code gọi, nhưng không tự bảo đảm thành công của các hệ thống bên ngoài.

Ví dụ ở mức khái niệm:

~~~text
REST Controller / Java Service
      gọi pricingGateway.quote(request)
              |
              v
      Message<PriceRequest>
              |
              v
         requestChannel
              |
         Pricing handler
              |
              v
      Message<PriceReply>
              |
              v
      pricingGateway.quote(...) trả kết quả
~~~

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Trình bày mô hình **Request–Reply** và vai trò gateway trong Enterprise Integration Patterns (EIP).
2. Phân biệt **Messaging Gateway**, **Inbound Gateway**, **Outbound Gateway** và **Channel Adapter** trong Spring Integration.
3. Hiểu các thành phần **requestChannel, replyChannel, reply-to, correlation ID, timeout, Message headers**.
4. Viết một giao diện **@MessagingGateway** và một service activator xử lý request trong Java.
5. Tạo luồng tích hợp HTTP hoặc message broker có request/reply, không giả định mọi broker hỗ trợ reply giống HTTP.
6. Thiết kế reply mapping, validation, business error, transport error và late reply.
7. Lựa chọn **DirectChannel, ExecutorChannel, QueueChannel** theo cách dispatch, độ trễ, lỗi và transaction.
8. Phòng tránh duplicate request, timeout retry, lỗi commit và nhầm lẫn giữa phản hồi thành công với tác động end-to-end.
9. Xây kịch bản kiểm thử, theo dõi metrics và một runbook đủ để vận hành gateway.

### 1.2. Kết quả cần chứng minh

Một thiết kế đạt yêu cầu khi bạn trả lời được:

- **Ai gửi request?** Danh tính hoặc workload đã được xác thực và được phép gọi nghiệp vụ?
- **Gửi tới đâu?** Request đi vào channel/endpoint nào, payload/header có hợp đồng gì?
- **Ai xử lý?** Handler, service, HTTP server hay broker consumer nào chịu trách nhiệm?
- **Reply đi về đâu?** Làm sao không đưa kết quả của request A sang người gọi B?
- **Chờ đến khi nào?** Timeout và điều kiện nhận kết quả cuối được định nghĩa thế nào?
- **Khi lỗi thì sao?** Lỗi nghiệp vụ khác lỗi kết nối hay mất phản hồi ra sao?
- **Nếu client retry?** Có tạo cùng side effect hai lần không?

## 2. Request–Reply trong Enterprise Integration Patterns

Ở mô hình một chiều (*one-way / fire-and-forget*), producer phát message rồi không chờ kết quả nghiệp vụ trực tiếp. Với **Request–Reply**, producer gửi yêu cầu và mong đợi một kết quả liên hệ được với yêu cầu đó.

### 2.1. Hai nửa của một cuộc trao đổi

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Requester** | Khởi tạo yêu cầu và chờ/nhận phản hồi | PricingService gọi quote |
| **Gateway** | Chuyển lời gọi hoặc giao thức thành message request/reply | Spring Messaging Gateway |
| **Request channel** | Chuyển request tới handler/adapter | pricingRequests |
| **Request handler** | Thực thi nghiệp vụ hoặc gọi hệ ngoài | PriceQuoteHandler |
| **Reply** | Kết quả hoặc thông tin từ chối hợp lệ | QuoteAccepted / QuoteRejected |
| **Reply channel / reply destination** | Đường phản hồi về requester | Message replyChannel hoặc JMSReplyTo |
| **Correlation** | Nối reply với request ban đầu | Correlation ID hoặc cơ chế reply routing |
| **Deadline / timeout** | Giới hạn thời gian người gọi chờ | 3 giây trong lab |

**Mấu chốt:** request và reply có thể đi trên hai channel hoặc hai queue/topic khác nhau; vì vậy phải có cách liên hệ đúng cặp, không chỉ dựa vào thứ tự đến.

### 2.2. Đồng bộ về API không đồng nghĩa đồng bộ trên mạng

~~~mermaid
sequenceDiagram
    participant CALL as Java caller
    participant GW as Messaging Gateway
    participant REQ as RequestChannel
    participant H as Handler
    participant REP as ReplyChannel
    CALL->>GW: quote(PriceRequest)
    GW->>REQ: Message<PriceRequest>
    REQ->>H: handle(request)
    H-->>REP: Message<PriceReply>
    REP-->>GW: Reply cho request đúng
    GW-->>CALL: PriceReply
~~~

Caller có thể thấy một lời gọi đồng bộ đơn giản, nhưng flow phía sau có thể đi qua executor, TCP, HTTP hoặc broker và trở lại. Chọn kiến trúc dựa trên **độ trễ, cách xử lý lỗi và điều kiện nghiệp vụ**, không chỉ trên việc method có kiểu trả về.

### 2.3. Các biến thể của Request–Reply

| Biến thể | Cách hoàn tất | Khi sử dụng |
| --- | --- | --- |
| **In-process synchronous** | Handler trả lời ngay trong cùng call stack | Lookup nhanh, validate hoặc business function tại JVM |
| **Remote synchronous** | Gửi request HTTP/JMS và đợi phản hồi từ hệ đích | Query service ngoài với SLA ngắn |
| **Asynchronous Request–Reply** | Request và reply đi qua các kênh/broker khác nhau | Hệ thống tách rời, thời gian xử lý biến động |
| **Request accepted + callback/status** | Phản hồi ngay bằng job ID, kết quả đến sau | Batch lâu, export dữ liệu, xử lý kéo dài |
| **Scatter–Gather** | Một request gửi nhiều recipient và tổng hợp replies | Cần nhiều báo giá hoặc dữ liệu từ nhiều nguồn |

Không nên dùng gateway đồng bộ để chờ công việc có thể kéo dài hàng giờ. Khi đó phù hợp hơn là **trả mã công việc**, lưu trạng thái bền vững rồi cho client truy vấn hoặc nhận callback/event khi hoàn tất.

## 3. Gateway khác adapter, handler và poller ở điểm nào?

Spring Integration có nhiều endpoint cùng làm việc với MessageChannel, nhưng **hợp đồng giữa bên gọi và bên được gọi** rất khác nhau.

| Thành phần | Chiều giao tiếp | Bên gọi chờ reply? | Ví dụ |
| --- | --- | --- | --- |
| **Inbound channel adapter** | Bên ngoài → channel | Thường không có request-reply tại flow | File inbound adapter, message-driven listener |
| **Outbound channel adapter** | Channel → bên ngoài | Không mặc nhiên có reply message | Gửi file, publish notification |
| **Inbound gateway** | Yêu cầu từ ngoài → flow → phản hồi ra ngoài | Có, theo protocol/contract | HTTP inbound gateway, JMS inbound gateway |
| **Outbound gateway** | Flow → yêu cầu tới hệ ngoài → reply vào flow | Có | HTTP outbound gateway, JMS outbound gateway |
| **Messaging Gateway** | Method invocation → message → reply → return value | Có nếu method yêu cầu reply | Java interface @MessagingGateway |
| **Service activator** | MessageChannel → business handler | Trả result nếu handler/method có reply | validateQuote, calculatePrice |
| **Poller** | Theo lịch nhận từ MessageSource/PollableChannel | Không phải là một gateway | File/SFTP polling, QueueChannel consumer |

### 3.1. Inbound gateway và outbound gateway

**Inbound gateway** là điểm **người ngoài gọi vào** một integration flow của ta. Với HTTP, nó nhận request và có thể gửi HTTP response sau khi flow trả reply.

**Outbound gateway** là điểm integration flow của ta **gọi ra ngoài**, chẳng hạn một HTTP GET tới service tỷ giá, rồi đưa HTTP response trở lại flow như một reply message.

~~~mermaid
flowchart LR
    EXT["External HTTP client"] --> IG["HTTP Inbound Gateway"]
    IG --> CH["MessageChannel"]
    CH --> H["Service handler"]
    H --> OG["HTTP Outbound Gateway"]
    OG --> REM["Remote price API"]
    REM --> OG
    OG --> H
    H --> IG
    IG --> EXT
~~~

Đường mũi tên phản hồi ở sơ đồ là **logic request/reply**, không hứa rằng cùng object hoặc cùng thread đi xuyên tất cả thành phần. Khi flow có router, transform hay broker, cần bảo toàn các thông tin định tuyến reply thích hợp.

### 3.2. Messaging Gateway không nhất thiết là một HTTP gateway

Messaging Gateway là **proxy Java** cho một message flow. Nó có thể gọi handler trong JVM, gửi qua JMS/AMQP hoặc kích hoạt HTTP outbound gateway. **Không có HTTP bắt buộc** trong định nghĩa.

### 3.3. Polling Consumer và Gateway có thể cùng hiện diện

Một luồng có thể dùng **SFTP inbound poller** lấy file, gọi **outbound HTTP gateway** để kiểm tra dữ liệu rồi chuyển kết quả tới adapter ghi DB. Poller quyết định khi nào lấy file; gateway quyết định request/reply khi gọi API. Không nên nhầm hai trách nhiệm đó.

## 4. Các message và headers quyết định đường reply

Spring Integration dùng Spring **Message** gồm **payload** và **headers**. Với request/reply, ngoài metadata như message ID và timestamp, các header như **replyChannel** và **errorChannel** là đặc biệt quan trọng trong cơ chế định tuyến nội bộ.

### 4.1. Hợp đồng cơ bản

~~~text
Request Message:
  payload      = PriceRequest(sku, quantity, customerTier)
  headers:
    messageId        = ID thông điệp kỹ thuật
    replyChannel     = kênh/địa chỉ reply nội bộ
    errorChannel     = kênh xử lý lỗi nếu cấu hình phù hợp
    correlationId    = khóa liên hệ với request (khi cần)
    traceId          = khóa tracing (nếu hệ tích hợp bổ sung)

Reply Message:
  payload      = PriceReply(sku, currency, total)
  headers:
    correlationId    = cùng khóa liên hệ theo contract
    traceId          = dùng để nối log/traces
~~~

Đây là một ví dụ **khái niệm**. Không phải mọi Gateway tự bổ sung tất cả các header kể trên, cũng không có bảo đảm rằng cùng một trường correlation mang ý nghĩa như nhau qua HTTP, JMS và Kafka. Phải phân biệt **header nội bộ Spring Messaging** với **header của giao thức vận chuyển**.

### 4.2. replyChannel và Reply-To

- Với gateway nội bộ, framework có thể thiết lập một **kênh nhận reply tạm thời** để kết quả quay về đúng lời gọi đang chờ.
- Handler có reply có thể trả một payload hoặc Message; framework sử dụng thông tin reply route để đưa kết quả trở lại.
- Với JMS có thể dùng **JMSReplyTo** hoặc destination reply được cấu hình; kết quả cần được nối bằng correlation.
- Với AMQP và Kafka, cơ chế reply-to/correlation khác JMS; phải cấu hình theo adapter, container và các topic/queue thực tế.
- Với HTTP inbound gateway, reply cuối được ánh xạ thành một **HTTP response** gắn với request/connection, không phải một thông điệp được broker lưu mặc định.

**Không xóa replyChannel hoặc correlation metadata tùy tiện** khi tạo một Message mới giữa flow; nếu làm mất khả năng định tuyến, gateway có thể timeout dù handler đã tạo ra một kết quả hợp lệ.

### 4.3. Correlation ID và Business ID khác nhau

| ID | Dùng để làm gì | Ví dụ |
| --- | --- | --- |
| **messageId** | Định danh một Spring Message kỹ thuật | Một UUID mới mỗi lần tạo message |
| **requestId** | Định danh một yêu cầu nghiệp vụ | PRICE-REQ-0198 |
| **correlationId** | Liên kết reply với request đúng | CORR-7C2A |
| **traceId** | Nối các span/log xuyên hệ thống | TRACE-9021 |
| **idempotencyKey** | Ngăn tác động nghiệp vụ bị lặp khi retry | customer + order + operation |

Chúng có thể trùng giá trị nếu hợp đồng cố ý thiết kế như vậy, nhưng **không có quy tắc chung rằng chúng luôn giống nhau**. Với retry, messageId có thể thay đổi trong khi requestId/idempotencyKey vẫn giữ nguyên.

### 4.4. Một luồng có hàng trăm request đồng thời

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant GW as Gateway
    participant H as Remote Service
    A->>GW: Request A (corr=A1)
    B->>GW: Request B (corr=B1)
    GW->>H: A1
    GW->>H: B1
    H-->>GW: Reply B1 (đến trước)
    GW-->>B: Kết quả B1
    H-->>GW: Reply A1
    GW-->>A: Kết quả A1
~~~

Nếu định tuyến reply bằng **thứ tự xuất hiện** thay vì correlation đúng, caller có thể nhận dữ liệu của người khác. Đây vừa là lỗi đúng sai nghiệp vụ, vừa là nguy cơ rò rỉ dữ liệu giữa tenant/customer.

## 5. Trạng thái Request–Reply và những điều một reply không chứng minh

Một gateway cần phân biệt nhiều giai đoạn:

| Mốc | Đã biết điều gì? | Chưa chắc điều gì? |
| --- | --- | --- |
| **SUBMITTED** | Caller tạo yêu cầu hợp lệ ở phía mình | Chưa chắc channel/broker nhận |
| **SENT/ACCEPTED** | Endpoint nhận request theo hợp đồng | Handler phía sau có commit hay chưa |
| **PROCESSING** | Consumer đang xử lý | Sẽ có reply đúng hạn hay không |
| **REPLIED** | Gateway nhận và ánh xạ reply | Hệ ngoài có side effect bổ sung chưa hoàn thành hay không |
| **TIMED_OUT** | Caller đã hết thời gian chờ | Request có thể vẫn đang chạy hoặc đã commit |
| **FAILED** | Một bước lỗi đã được phát hiện | Khả năng rollback/khôi phục còn tùy hệ |
| **COMMITTED** | Một đơn vị nghiệp vụ đã ghi kết quả bền vững theo contract | Các bước ngoài transaction có hoàn tất chưa |

**Nguy cơ quan trọng:** caller timeout **không đồng nghĩa** hệ đích chưa xử lý. Nếu gọi lại không có idempotency, có thể tạo hai đơn hàng, thanh toán hai lần hoặc cấp quyền hai lần.

### 5.1. Cách lựa chọn reply contract

- **Query thuần:** trả dữ liệu hoặc lỗi, thường dễ retry nếu không có side effect.
- **Command có side effect:** kèm requestId/idempotencyKey, làm rõ trạng thái accepted/committed.
- **Tác vụ dài:** trả 202/jobId hoặc thông báo trạng thái, không treo gateway vô hạn.
- **Business rejection:** trả một kết quả nghiệp vụ có cấu trúc (ví dụ QUOTE_NOT_AVAILABLE), không đánh đồng với lỗi TCP.
- **Transport timeout:** báo trạng thái **chưa rõ kết quả thực tế**, có đường truy vấn/đối soát nếu lệnh có side effect.

### 5.2. Khi nào trả lỗi thay vì reply bình thường?

Một giá bán không tồn tại có thể là **kết quả nghiệp vụ hợp lệ** (PriceUnavailable). Một JSON hỏng, service bị ngắt kết nối hoặc vi phạm security là lỗi khác. Hợp đồng API/message phải quyết định lỗi nào là kết quả domain, lỗi nào được xử lý qua exception/error channel.

Không nên chỉ trả chuỗi trống hoặc null cho mọi trường hợp: caller cần phân biệt **không có giá**, **hết thời gian chờ** và **server không hợp lệ**.

## 6. Java 17: tạo một Messaging Gateway thực tế trong JVM

Ví dụ sử dụng **Spring Integration 6.x**, Spring context và Java 17. Ta định nghĩa một **Java interface** làm gateway, một DirectChannel để chuyển request và một service activator tính giá. Đây là mô hình request/reply **nội bộ**: chưa kết nối HTTP hay broker, giúp cô lập các khái niệm trước khi thêm I/O.

### 6.1. DTO yêu cầu và phản hồi

Tạo hai record đại diện cho hợp đồng nghiệp vụ:

~~~java
// QuoteRequest.java
public record QuoteRequest(
        String requestId,
        String sku,
        int quantity,
        String customerTier
) {}
~~~

~~~java
// QuoteReply.java
import java.math.BigDecimal;

public record QuoteReply(
        String requestId,
        String sku,
        String currency,
        BigDecimal unitPrice,
        BigDecimal total
) {}
~~~

Request có **requestId** để theo dõi nghiệp vụ; trong ví dụ này nó chưa phải khóa idempotency cho một thao tác có side effect. Price lookup thuần có thể được gọi lại, nhưng nếu thay handler bằng “tạo đơn hàng” thì phải thêm idempotency bền vững.

### 6.2. Khai báo giao diện gateway

~~~java
// QuoteGateway.java
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
        defaultRequestChannel = "pricingRequests",
        defaultRequestTimeout = "1000",
        defaultReplyTimeout = "3000"
)
public interface QuoteGateway {
    QuoteReply quote(QuoteRequest request);
}
~~~

**Ý nghĩa:**

- **@MessagingGateway** yêu cầu Spring Integration tạo **proxy** để chuyển lời gọi method thành Message.
- **defaultRequestChannel** định tuyến request vào channel tên pricingRequests.
- **defaultRequestTimeout** giới hạn thời gian chờ khi **gửi** request tới channel trong những trường hợp hỗ trợ blocking send.
- **defaultReplyTimeout** giới hạn thời gian chờ reply cho lời gọi đồng bộ.
- Kiểu trả về **QuoteReply** được gateway ánh xạ từ reply nhận được.

Không coi request timeout là **HTTP connect timeout** hay reply timeout là **thời gian tối đa remote transaction có thể tồn tại**. Khi gọi mạng bên ngoài, connector có timeout riêng.

### 6.3. Tạo channel và kích hoạt gateway scanning

~~~java
// GatewayConfiguration.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class GatewayConfiguration {

    @Bean
    public MessageChannel pricingRequests() {
        return new DirectChannel();
    }
}
~~~

**@IntegrationComponentScan** phát hiện interface gateway trong những package nằm trong phạm vi quét được cấu hình. Với Spring Boot, phải bảo đảm cấu trúc package hoặc cấu hình scan bao phủ gateway và handler. Không tạo thủ công một instance của interface.

### 6.4. Service activator trả lời yêu cầu

~~~java
// PricingHandler.java
import java.math.BigDecimal;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class PricingHandler {

    @ServiceActivator(inputChannel = "pricingRequests")
    public QuoteReply calculate(QuoteRequest request) {
        if (request == null
                || request.requestId() == null
                || request.requestId().isBlank()
                || request.sku() == null
                || request.sku().isBlank()
                || request.quantity() <= 0) {
            throw new IllegalArgumentException("Invalid quote request");
        }

        BigDecimal unitPrice = new BigDecimal("125000");
        BigDecimal total = unitPrice.multiply(
                BigDecimal.valueOf(request.quantity())
        );
        return new QuoteReply(
                request.requestId(),
                request.sku(),
                "VND",
                unitPrice,
                total
        );
    }
}
~~~

Khi method trả **QuoteReply**, service activator chuyển kết quả thành reply theo cơ chế request/reply của Spring Integration. Với flow request/reply thông thường này, gateway có thể nhận lại reply mà handler **không phải tự gửi vào một hàng đợi được đặt tên**.

**Hạn chế rõ ràng:** unitPrice đang cố định để dễ học, chưa có catalog, customer-tier policy, authorization, deadline hoặc truy vấn DB thực. Không triển khai thành một pricing service sản xuất từ ví dụ này.

### 6.5. Caller nhìn thấy một interface Java

~~~java
// Một Spring @Service hoặc @Component
import org.springframework.stereotype.Service;

@Service
public class QuoteApplicationService {
    private final QuoteGateway quoteGateway;

    public QuoteApplicationService(QuoteGateway quoteGateway) {
        this.quoteGateway = quoteGateway;
    }

    public QuoteReply getQuote() {
        return quoteGateway.quote(new QuoteRequest(
                "PRICE-LAB-001",
                "SKU-LAB-A",
                2,
                "STANDARD"
        ));
    }
}
~~~

Kết quả minh họa:

~~~json
{
  "requestId": "PRICE-LAB-001",
  "sku": "SKU-LAB-A",
  "currency": "VND",
  "unitPrice": 125000,
  "total": 250000
}
~~~

**Luồng đi:** lời gọi quote → proxy gateway tạo Message → DirectChannel chuyển tới PricingHandler → handler trả QuoteReply → reply được định tuyến về gateway → method Java trả dữ liệu.

### 6.6. Đọc mã theo ba ranh giới

1. **Ranh giới lời gọi Java:** QuoteGateway có interface giống method thông thường.
2. **Ranh giới message:** channel và headers định tuyến message; handler không cần biết ai là caller.
3. **Ranh giới nghiệp vụ:** PricingHandler quyết định cách tính và tính hợp lệ của input.

Nếu thêm một outbound HTTP gateway sau bước transformation, ranh giới thứ tư xuất hiện: **kết nối bên ngoài** và rủi ro timeout/mất reply.

## 7. Request–Reply qua các channel đồng bộ và bất đồng bộ

### 7.1. DirectChannel: đơn giản và có call stack đồng bộ

Với ví dụ ở phần 6, DirectChannel thường dispatch handler trên thread của sender. Nếu handler tính toán trong 50 ms, caller có thể nhận reply sau thời gian xử lý và overhead phù hợp. Nếu handler chặn 30 giây vì một API treo, caller cũng có thể bị chặn.

**Đặc biệt:** reply timeout không phải một cơ chế ngắt cứng được mọi thao tác đồng bộ tuân theo. Nếu sender vẫn đang mắc kẹt trong call stack xử lý trên DirectChannel, thời gian chờ tổng của lời gọi còn phụ thuộc chính handler và các timeout mà nó dùng. Cần cấu hình timeout ở từng lớp I/O thay vì chỉ đặt defaultReplyTimeout.

### 7.2. ExecutorChannel: tách thread, thêm trách nhiệm lỗi

Khi đổi request channel thành ExecutorChannel, send có thể trả sau khi executor nhận task, còn handler xử lý ở thread khác. Gateway vẫn có thể chờ reply, nhưng lúc này:

- Task có thể bị **từ chối** nếu executor queue đầy.
- Transaction context trên thread gửi không tự lan sang handler.
- Một reply đến sau deadline có thể không còn người chờ.
- Lỗi của handler cần được đưa qua error flow và gateway theo contract; không thể giả định exception trực tiếp đi qua thread cũ.
- Retry từ caller có thể đến khi request đầu **vẫn đang thực thi**.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant GW as Gateway
    participant EX as ExecutorChannel
    participant H as Handler
    C->>GW: quote(Q1)
    GW->>EX: send(Q1)
    EX-->>GW: accepted by executor
    EX->>H: handle(Q1) thread khác
    Note over GW: Caller chờ reply tới deadline
    H-->>GW: reply hoặc error routing
    GW-->>C: result / timeout theo contract
~~~

**Sai lầm:** nhìn thấy ExecutorChannel nhận message rồi ghi “request đã xử lý thành công”. Điều đó mới nói rằng một bước dispatch diễn ra, chưa chứng minh handler commit và trả reply.

### 7.3. QueueChannel: phải có consumer kéo message

QueueChannel là **PollableChannel**. Nếu đưa request vào QueueChannel thì cần **PollingConsumer** hoặc một thành phần thực sự gọi receive() ở phía sau. Nếu thiếu consumer, gateway sẽ chờ reply cho đến timeout; chỉ gửi request vào QueueChannel không tự gọi handler.

Ngoài ra, một QueueChannel trong bộ nhớ **không mặc định bền vững qua crash**. Nếu request quan trọng cần tồn tại khi JVM dừng, hãy chọn broker/MessageStore hoặc giải pháp bền vững phù hợp.

### 7.4. PublishSubscribeChannel và nhiều kết quả

Gateway thông thường mong đợi **một reply** cho một request. Nếu broadcast request tới nhiều handler, có thể có nhiều reply hoặc không biết reply nào hợp lệ. Để lấy tất cả kết quả, dùng **Scatter–Gather/Aggregator** có correlation và completion strategy được định nghĩa rõ; không đơn giản nối ba reply vào một temporary reply channel rồi mong framework tự biết phải tổng hợp.

## 8. Request–Reply qua HTTP inbound và outbound gateway

### 8.1. HTTP inbound gateway: client gọi vào ta

Giả sử hệ thống nhận HTTP POST để tính báo giá:

~~~http
POST /api/prices/quote HTTP/1.1
Content-Type: application/json

{
  "requestId": "PRICE-LAB-001",
  "sku": "SKU-LAB-A",
  "quantity": 2,
  "customerTier": "STANDARD"
}
~~~

**HTTP inbound gateway** nhận request, tạo Spring Message, gửi vào flow, đợi một reply nếu contract yêu cầu rồi ánh xạ thành HTTP response. Cần cấu hình mapping và converter phù hợp cho JSON DTO, cùng authentication/authorization, validation, kích thước payload và timeout.

~~~mermaid
flowchart LR
    CLIENT["HTTP Client"] --> HTTP["HTTP Inbound Gateway"]
    HTTP --> CHANNEL["pricingRequests"]
    CHANNEL --> HANDLER["PricingHandler"]
    HANDLER --> CHANNEL
    CHANNEL --> HTTP
    HTTP --> CLIENT
~~~

Mũi tên trả về đi qua **reply route**, không nhất thiết quay ngược trên cùng requestChannel. Sơ đồ rút gọn để người học thấy hợp đồng request/reply.

Một dạng cấu hình Java DSL **tham khảo**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.http.dsl.Http;

@Configuration
public class HttpQuoteGatewayConfiguration {

    @Bean
    public IntegrationFlow inboundQuoteFlow() {
        return IntegrationFlow.from(
                    Http.inboundGateway("/api/prices/quote")
                        .requestMapping(m -> m.methods(HttpMethod.POST))
                        .requestPayloadType(QuoteRequest.class)
                )
                .channel("pricingRequests")
                .get();
    }
}
~~~

Ví dụ thể hiện **hướng cấu hình** trong Spring Integration 6.x, không phải dự án hoàn chỉnh. Trong project thật, cần dependency Spring Integration HTTP, Jackson/message converters phù hợp, xử lý JSON, HTTP response status, bảo mật, exception mapping và kiểm chứng các overload theo phiên bản thư viện đang dùng.

### 8.2. HTTP outbound gateway: flow gọi API khác

Một flow có thể nhận message từ broker, rồi gọi dịch vụ pricing bên ngoài qua **HTTP outbound gateway** và tiếp tục xử lý HTTP response như reply:

~~~text
OrderCreated message
  → transformer tạo PriceRequest
  → HTTP outbound gateway gọi pricing service
  ← HTTP response / PriceReply
  → validate reply
  → handler cập nhật order với kết quả
~~~

Trước khi gửi, phải xác định method GET/POST, URL, path/query variables, auth header, content type, expected response type, connect/read timeout và xử lý status 4xx/5xx. **HTTP 200** không tự có nghĩa dữ liệu trả về phù hợp schema hay giá đã được chốt theo hợp đồng nghiệp vụ.

### 8.3. HTTP status và kết quả domain

| Trạng thái | Ý nghĩa thông thường | Hướng xử lý trong gateway |
| --- | --- | --- |
| **200/201** | Yêu cầu trả kết quả thành công theo HTTP contract | Parse/validate reply, kiểm tra business status |
| **202** | Request đã được tiếp nhận để xử lý sau | Trả jobId/status URI; không báo hoàn thành ngay |
| **400/422** | Request không hợp lệ hoặc không đáp ứng ràng buộc nghiệp vụ | Trả lỗi có mã, không retry mù |
| **401/403** | Thiếu xác thực hoặc không đủ quyền | Không tự bypass, log kiểm soát |
| **404** | Tài nguyên không tồn tại theo endpoint | Có thể là kết quả domain hoặc lỗi mapping; cần contract |
| **409** | Xung đột trạng thái/phiên bản | Truy vấn hoặc xử lý concurrency, không retry vô hạn |
| **429** | Rate limit | Tôn trọng Retry-After nếu có và backoff |
| **500/502/503/504** | Lỗi phía server hoặc gateway | Retry có giới hạn, đặc biệt cẩn trọng với side effect |

Mã HTTP chỉ là **tín hiệu transport**. Không dùng ngoại lệ mạng làm bằng chứng request chưa commit.

### 8.4. Khi không nên giữ HTTP request đang mở

Nếu xuất báo cáo cần 20 phút, HTTP inbound gateway chờ đồng bộ là lựa chọn yếu: client/proxy có thể timeout, restart làm mất trạng thái và người dùng khó biết request có tiếp tục không. Mẫu phù hợp hơn:

~~~text
POST /exports → validate + persist job → 202 Accepted + jobId
Worker xử lý async qua broker
GET /exports/{jobId} → tiến độ và kết quả
Event/callback khi job hoàn tất (nếu được hỗ trợ)
~~~

Request/reply ở bước **tạo job** vẫn tồn tại, nhưng không buộc mọi khâu xử lý kéo dài phải diễn ra trong một lời gọi gateway.

## 9. Gateway request–reply qua JMS, AMQP và Kafka

Message broker cho phép tách requester và responder thành các service riêng, nhưng **không phải broker nào cũng có request/reply mặc định giống lời gọi HTTP**. Thường cần định nghĩa destination reply, correlation, cách xử lý reply muộn, timeout và ownership của các request đang chờ.

### 9.1. JMS: request destination, reply destination và correlation

Một luồng JMS request/reply thường có:

1. Requester gửi message đến **request queue**.
2. Message mang thông tin **reply destination** (ví dụ JMSReplyTo) và cơ chế correlation.
3. Responder nhận, xử lý và gửi reply đến destination tương ứng.
4. Requester nhận reply và ghép với request đang chờ bằng ID/correlation.
5. Khi hết deadline, requester dọn pending state theo chính sách; response muộn cần được xử lý.

~~~mermaid
sequenceDiagram
    participant A as Requester
    participant GW as JMS Outbound Gateway
    participant Q as JMS Request Queue
    participant RESP as Responder
    participant RQ as JMS Reply Destination
    A->>GW: Request Quote Q17
    GW->>Q: JMS request + reply destination
    Q->>RESP: Deliver request
    RESP->>RQ: Reply + correlation
    RQ-->>GW: Match Q17
    GW-->>A: QuoteReply
~~~

**JMSReplyTo** là thông tin định tuyến; **JMSCorrelationID** và JMSMessageID có những vai trò liên quan nhưng không phải lúc nào giống nhau. Một giải pháp có thể đặt correlation từ request ID, một giải pháp khác dùng ID message phát sinh để liên kết. Thiết kế phải theo gateway/client/broker cụ thể, không cố gán một công thức cố định cho mọi sản phẩm.

**Checklist JMS:**

- [ ] Queue reply là temporary, shared hay một destination được đặt tên? Ai tạo/xóa?
- [ ] Nếu nhiều instance request đồng thời, có cơ chế phân phối/matching reply chính xác?
- [ ] Có timeout khi gửi, khi chờ reply và khi broker không kết nối?
- [ ] Responder có transaction/ack đúng lúc không? Nếu nó xử lý lại, có trả reply trùng?
- [ ] Nếu requester chết, reply sẽ đi đâu? TTL/quota và cleanup như thế nào?
- [ ] Nếu reply đến sau deadline, nó được bỏ qua, lưu đối soát hay ảnh hưởng request khác?

### 9.2. AMQP/RabbitMQ: request queue và reply-to

RabbitMQ hỗ trợ nhiều cách tổ chức request/reply, chẳng hạn reply queue hoặc các cơ chế **direct reply-to** được client/library hỗ trợ. Một outbound gateway AMQP sẽ cần biết queue/exchange routing và cách broker/client liên kết reply với request.

~~~text
Integration Flow
    -> AMQP outbound gateway
    -> exchange/routing key
    -> request queue
    -> responder
    -> reply-to destination / direct reply-to
    -> AMQP gateway nhận và ghép reply
    -> Integration Flow tiếp tục
~~~

**Điều phải phân biệt:** message được broker nhận, message được responder acknowledge, responder đã commit nghiệp vụ, responder phát reply và requester đã nhận reply là **những mốc khác nhau**.

Với queue reply tạm thời, requester restart có thể làm reply cũ không còn người chờ. Với shared reply queue, phải có correlation và consumer coordination. Request đã được xử lý ở responder nhưng reply bị mất là tình huống quan trọng cho idempotent retry.

### 9.3. Kafka: reply topic không tự biến stream thành RPC

Kafka được tối ưu cho event log phân partition và consumer group. **Request/reply vẫn có thể thiết kế** bằng request topic, reply topic, correlation ID và một client/coordinator quản lý pending requests. Hệ sinh thái Spring Kafka có khả năng request/reply ở các API phù hợp; khi phối hợp với Spring Integration, cần xác minh adapter/gateway và phiên bản hỗ trợ cụ thể.

~~~mermaid
flowchart LR
    REQ["Request Producer/Gateway"] --> QT["quotes.requests topic"]
    QT --> WORK["Quote responder"]
    WORK --> RT["quotes.replies topic"]
    RT --> MATCH["Reply listener + correlation registry"]
    MATCH --> REQ
~~~

**Các vấn đề cần giải quyết thêm so với method call:**

- Reply tới **partition/topic** nào để requester tương ứng có thể nhận?
- Multiple requesters dùng **consumer group** thế nào để reply không bị service khác nhận nhầm?
- Correlation registry sống trong memory hay bền vững? Timeout xóa pending thế nào?
- Nếu requester restart, reply cũ được giữ/đọc lại ra sao?
- Khi responder rebalance/retry, hai reply cho cùng request sẽ được xử lý thế nào?
- Offset commit và transaction của responder có liên quan tới business commit/record reply không?

Không nên dùng Kafka RPC cho mọi tương tác đơn giản chỉ vì đã có Kafka. Với lookup nhanh cần response tức thời, HTTP/gRPC có thể ít phức tạp hơn. Với workflow nhiều phút, nên dùng event bất đồng bộ và state machine thay vì giữ hàng nghìn promise/future chờ reply.

### 9.4. So sánh transport cho request/reply

| Khía cạnh | HTTP | JMS | AMQP/RabbitMQ | Kafka |
| --- | --- | --- | --- | --- |
| Reply route | HTTP response gắn request/connection | Reply destination + correlation | Reply queue/direct reply-to + correlation | Reply topic + correlation/partition strategy |
| Ai quản lý pending | HTTP client/server/proxy theo kết nối | Gateway/client | Gateway/client | Reply coordinator/client |
| Timeout | Connect/read/request/proxy | Send + receive reply + broker | Broker/client/reply timeout | Produce/fetch/reply deadline |
| Khi requester chết | HTTP connection mất | Reply có thể còn/không còn theo destination | Tùy reply queue/expiry | Reply record có thể vẫn tồn tại trong topic |
| Duplicate | Client retry | Redelivery/reply trùng | Redelivery/reply trùng | At-least-once/replay/rebalance |
| Ordering | Theo request/connection, không tổng thể | Theo destination/consumer | Theo queue/consumer | Trong partition theo contract |
| Điểm dùng hợp lý | Query ngắn, web API | Enterprise messaging có request/reply | RabbitMQ workflows và RPC được quản trị | Dùng khi cần tích hợp stream và reply được thiết kế rõ |

**Không có lựa chọn nào tự đem tới exactly-once xuyên HTTP, broker và database**. Độ tin cậy đến từ hợp đồng xử lý, idempotency, transaction, timeout và reconciliation.

## 10. Gateway và các adapter File, SFTP, Database

File/SFTP/DB thường đóng vai trò **nguồn dữ liệu** hoặc **đích side effect**, không phải cặp request/reply theo thời gian thực như HTTP. Gateway có thể được gọi **giữa flow** để hỏi một thông tin khác hoặc gửi command.

### 10.1. File inbound → outbound HTTP gateway

Ví dụ mỗi file CSV cần được kiểm tra với hệ thống khách hàng trước khi nhập DB:

~~~mermaid
flowchart LR
    FILE["File/SFTP inbound poller"] --> PARSE["Parse + Validate"]
    PARSE --> REQ["Tạo CustomerLookupRequest"]
    REQ --> GW["HTTP Outbound Gateway"]
    GW --> API["Customer Service"]
    API --> GW
    GW --> DECIDE["Kiểm tra reply"]
    DECIDE --> DB["Commit dữ liệu hợp lệ"]
    DECIDE --> ERR["Quarantine / Retry"]
~~~

Ở đây **poller** làm nhiệm vụ phát hiện file mới; gateway làm nhiệm vụ request/reply với Customer Service. Nếu HTTP timeout sau khi Customer Service đã thực hiện một update, phải phân biệt query an toàn để retry với command có side effect.

### 10.2. SFTP command/reply không giống RPC tùy ý

Một adapter gửi/nhận file có thể xác nhận một thao tác protocol, nhưng không có nghĩa đối tác **đã xử lý nội dung file**. Ví dụ upload file lên SFTP thành công chỉ chứng minh server đã nhận file theo contract truyền tải; nếu cần xác nhận nghiệp vụ, cần **ack file, status API, broker event hoặc quy trình đối soát** riêng.

Không tạo một request/reply gateway chỉ bằng cách “đợi file biến mất” nếu không có hợp đồng rõ: file có thể được di chuyển bởi tác vụ khác hoặc bị xóa do lỗi.

### 10.3. Database as request/reply target

Một **JDBC outbound gateway** hoặc một service handler gọi repository có thể lấy dữ liệu rồi trả reply. Nhưng khi tác động tới DB:

- Query thuần có thể dùng read timeout và retry phù hợp.
- Write command cần transaction, constraint và idempotency.
- Đọc reply sau ghi phải được xác định theo isolation level và source of truth.
- Không coi transaction JDBC bao trùm cả SFTP transfer hay HTTP request khác.
- Nếu phải phát event sau commit, xem xét transactional outbox.

### 10.4. Gateway và message store

Trong một flow qua **QueueChannel/MessageStore**, gateway có thể chờ kết quả từ consumer ở phía sau. Nhưng nếu chờ reply qua crash/restart, phải quản lý pending requests, correlation state và reply destination **bền vững**. Lưu request bền vững mà chỉ giữ temporary reply channel trong RAM không tự đảm bảo caller còn nhận reply sau restart.

## 11. Timeout: ba đồng hồ và một reply đến muộn

Timeout là phần dễ gây lỗi nghiêm trọng nhất trong request/reply khi hệ đích chậm hoặc gặp sự cố.

### 11.1. Phân biệt các timeout

| Timeout | Đo điều gì? | Ví dụ lỗi |
| --- | --- | --- |
| **Request send timeout** | Chờ gửi message vào channel/destination khi đường gửi có blocking | Queue/MessageChannel đầy |
| **Gateway reply timeout** | Chờ reply được chuyển về gateway | Handler hoặc responder quá chậm |
| **Connect timeout** | Chờ thiết lập kết nối HTTP/TCP/broker | Service không reachable |
| **Read/response timeout** | Chờ đọc dữ liệu từ remote connection | Server đã nhận nhưng không phản hồi đúng hạn |
| **Business deadline** | Mốc nghiệp vụ mà kết quả còn hữu ích | Báo giá đã hết hiệu lực |
| **Broker message TTL** | Thời hạn message được giữ/nhận theo broker | Request/reply hết hạn ở queue/topic |

Không phải mọi timeout đều được tính từ cùng mốc hoặc được cấu hình bằng cùng annotation. Một gateway timeout không thay thế được HTTP socket timeout, transaction timeout hoặc deadline ở ứng dụng remote.

### 11.2. Timeline: timeout rồi retry

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant GW as Gateway
    participant H as Responder
    participant DB as Database
    C->>GW: CreateOrder(requestId=R1)
    GW->>H: Message R1
    H->>DB: Commit order R1
    DB-->>H: OK
    Note over GW,C: Reply timeout, caller chưa biết trạng thái
    GW-->>C: TIMEOUT / UNKNOWN
    C->>GW: Retry R1 cùng idempotency key
    GW->>H: Message R1
    H->>DB: Kiểm tra requestId R1 đã hoàn thành
    DB-->>H: Trả kết quả cũ, không tạo order thứ hai
    H-->>GW: Reply R1
    GW-->>C: Result of R1
~~~

**Nếu R1 đã commit, retry phải trả cùng kết quả hoặc trạng thái có thể truy vấn**. Nếu gọi retry bằng một requestId mới mà không có cơ chế deduplication, dễ tạo side effect thứ hai.

### 11.3. Reply muộn nên làm gì?

Reply đến sau deadline thường không còn caller đang chờ. Tùy kiến trúc:

1. **Drop có kiểm soát** và metric late replies nếu request là query vô trạng thái.
2. **Lưu kết quả theo requestId** và cho caller truy vấn lại nếu là command dài/quan trọng.
3. **Dọn pending correlation** theo TTL để không tăng memory vô hạn.
4. **Không ghép nhầm reply** muộn của request A với request B đang sử dụng cùng connection/queue.
5. **Không tự phát lại side effect** chỉ vì reply đến muộn.

### 11.4. Timeouts và retry storm

Nếu 1.000 caller đồng loạt timeout rồi retry không giới hạn, một service đã chậm càng quá tải. Hãy dùng **retry budget, exponential backoff, jitter, rate limiting, bulkhead và circuit breaker** theo rủi ro. Với lệnh ghi, cần idempotency và state query trước khi retry không chắc chắn.

### 11.5. Deadline propagation

Với chuỗi API A → gateway B → HTTP gateway C, nếu caller A chỉ còn 500 ms cho request, B không nên tiếp tục chờ C thêm 30 giây mà không có căn cứ. Có thể truyền **business deadline** hoặc remaining budget qua các lớp nội bộ được tin cậy. Không nhận deadline do client tự gửi để bỏ qua validation hoặc nâng đặc quyền.

## 12. Error channel và phản hồi lỗi

### 12.1. Ba loại outcome cần tách

| Outcome | Ví dụ | Cách biểu diễn |
| --- | --- | --- |
| **Business success** | Báo giá được tính | QuoteReply hợp lệ |
| **Business rejection** | SKU không bán, khách hàng không đủ điều kiện | Domain reply có code/reason, không lẫn transport failure |
| **Technical failure** | DB timeout, broker mất kết nối, JSON hỏng | Exception/ErrorMessage/error flow và mapping tới caller |

**Lỗi nghiệp vụ không nhất thiết là exception:** “Sản phẩm đã hết hàng” có thể là một reply hoàn toàn hợp lệ. Trái lại, việc parse ra một response không hợp schema cần được xem là thất bại kỹ thuật.

### 12.2. Lỗi đồng bộ và bất đồng bộ

**DirectChannel đồng bộ:** exception từ handler có thể lan về gateway trong cùng call stack, rồi được framework wrap/translate theo cơ chế Spring Messaging. Phương thức Java gọi gateway cần xử lý được ngoại lệ phù hợp.

**ExecutorChannel hoặc broker:** exception ở responder không tự chạy qua cùng call stack với requester; nó có thể đi qua error channel, DLT hoặc một reply báo lỗi có correlation. Thiết kế cần đảm bảo caller biết **timeout/technical failure/business rejection** khác nhau.

### 12.3. ErrorMessage và errorChannel

Spring Integration dùng **ErrorMessage** và error channel cho nhiều lỗi của flow. Tuy nhiên nơi phát ErrorMessage, việc lỗi có được đưa tới gateway hay không và cơ chế fallback phụ thuộc kiểu endpoint, synchronous/asynchronous boundary và error handler được cấu hình.

- [ ] Xác định lỗi phát sinh **trước khi gửi request**, **khi gửi**, **khi xử lý**, **khi gửi reply** hay **sau reply**.
- [ ] Với lỗi đồng bộ, không nuốt exception rồi giả reply thành công.
- [ ] Với lỗi async, có error flow hoặc reply lỗi được định tuyến theo correlation.
- [ ] Với lỗi trong adapter remote, giữ source requestId, target, attempt và exception type.
- [ ] Không lộ stack trace, secret, raw token hoặc dữ liệu cá nhân nhạy cảm ra external reply.
- [ ] Nếu caller đã timeout, xử lý error muộn theo runbook thay vì cố gửi vào reply channel không còn người chờ.
- [ ] Nếu cấu hình errorChannel, test thực tế callback nào nhận lỗi trong phiên bản thư viện đang dùng.

### 12.4. Ví dụ phản hồi lỗi có cấu trúc

~~~json
{
  "requestId": "PRICE-LAB-001",
  "status": "REJECTED",
  "code": "SKU_UNAVAILABLE",
  "message": "Sản phẩm không khả dụng tại thời điểm yêu cầu",
  "retryable": false
}
~~~

Đây là **domain reply** minh họa. Trong HTTP, có thể ánh xạ thành 4xx phù hợp hợp đồng; trong JMS/AMQP, có thể là message reply có status/code. Không cần dùng exception Java ở producer để biểu diễn mọi từ chối nghiệp vụ.

## 13. Idempotency và giao dịch khi gateway tạo side effect

Gateway không làm một thao tác trở nên **exactly-once end-to-end** chỉ vì cùng một method call có request và reply. Khi flow tạo đơn, thanh toán, gửi thông báo hoặc thay đổi trạng thái, cần xử lý khả năng **gửi trùng và phản hồi thất lạc**.

### 13.1. Năm điểm có thể gây lặp

1. Caller không nhận được reply nên tự gửi lại request.
2. HTTP reverse proxy hoặc client retry khi mạng lỗi.
3. JMS/AMQP responder bị redelivery request vì chưa ack/transaction chưa commit.
4. Kafka record được đọc lại sau rebalance hoặc offset chưa commit.
5. Gateway/adapter có retry advice tự động và side effect ở đích thực tế đã thành công.

### 13.2. Idempotency key phải là business key bền vững

Ví dụ tạo đơn hàng:

~~~json
{
  "requestId": "CREATE-ORDER-LAB-0098",
  "idempotencyKey": "TENANT-LAB-01/CHECKOUT-0098",
  "tenantId": "TENANT-LAB-01",
  "customerId": "CUST-LAB-03",
  "items": [
    {"sku": "SKU-A", "quantity": 2}
  ]
}
~~~

Khi retry, caller **giữ cùng idempotencyKey**. Responder:

~~~text
processCreateOrder(request):
  validateRequesterAndScope(request)
  validateBusinessPayload(request)
  checkKeyNotReusedForDifferentPayload(request.idempotencyKey)

  with databaseTransaction:
      existing = findOrderByIdempotencyKeyForUpdate(key)
      if existing:
          return persistedResult(existing)

      order = createOrder(request)
      persistIdempotencyRecord(key, hashOfSignificantRequestFields, order.id)
      commit

  return persistedResult(order)
~~~

Đây là **giả mã**. Chỉ một câu SELECT rồi INSERT không đủ chống race giữa hai request đồng thời; cần ràng buộc unique, transaction/locking phù hợp và cách giải quyết conflict. Không lưu trạng thái idempotency “thành công” trước khi nghiệp vụ commit theo contract.

### 13.3. Nếu responder còn gọi một API khác?

Giả sử CreateOrder handler vừa lưu DB vừa gọi Payment API. Một transaction JDBC thông thường **không rollback được lệnh thanh toán HTTP**. Cần thiết kế thêm:

- API thanh toán nhận idempotency key riêng hoặc có cách tra cứu giao dịch theo business reference.
- Dùng outbox hoặc saga/process manager cho các bước bất đồng bộ.
- Có compensation khi business cho phép; không coi mọi side effect đều rollback được.
- Trả trạng thái **PENDING/UNKNOWN** nếu timeout nhưng chưa xác minh external effect.
- Theo dõi attempt, operation ID và kết quả thực tế của từng bước.

### 13.4. Gateway query khác gateway command

| Đặc tính | Gateway query | Gateway command |
| --- | --- | --- |
| Side effect | Không mong đợi thay đổi dữ liệu | Có thể thay đổi trạng thái |
| Retry sau timeout | Thường đơn giản hơn nếu query thuần | Cần kiểm chứng/idempotency |
| Cần business key | Hữu ích cho tracing/cache | Thiết yếu khi có nguy cơ duplicate |
| Reply | Snapshot dữ liệu | Accepted/Committed/Rejected/Unknown |
| Bảo toàn | Độ mới, schema, phân quyền | Transaction, concurrency, quyền, reconciliation |

### 13.5. Sự kiện phát sau khi gateway trả reply

Một service có thể nhận CreateOrder, commit DB và trả reply cho HTTP caller, sau đó mới phát OrderCreated event. Nếu phát event thất bại, caller vẫn thấy đơn đã tạo nhưng consumer downstream không nhận event. Dùng **transactional outbox** để lưu order và outbox event trong cùng DB transaction, sau đó relay phát có retry. Người nhận event vẫn cần idempotency vì relay có thể phát lặp.

## 14. Correlation, routing, aggregation và reply ownership

### 14.1. Một request qua nhiều handler

Một luồng có router quyết định nhà cung cấp dịch vụ:

~~~mermaid
flowchart TD
    GW["Quote Gateway"] --> ROUTER{"Route by currency / region"}
    ROUTER -->|VN| VN["VN Price Service"]
    ROUTER -->|EU| EU["EU Price Service"]
    ROUTER -->|Other| FALL["Unsupported region reply"]
    VN --> REPLY["Reply route"]
    EU --> REPLY
    FALL --> REPLY
    REPLY --> GW
~~~

Router phải có tuyến fallback hoặc lỗi rõ ràng; nếu message bị loại bỏ im lặng, gateway thường chỉ biết **reply timeout**. Một flow cần reply không nên dùng filter âm thầm bỏ mọi request không hợp lệ mà không tạo kết quả lỗi/throw đúng contract.

### 14.2. Aggregator và Scatter–Gather

Giả sử một yêu cầu cần **giá từ ba nhà cung cấp** để chọn phương án:

~~~mermaid
flowchart LR
    REQ["GetBestQuote(request)"] --> SCATTER["Scatter to 3 providers"]
    SCATTER --> P1["Provider A"]
    SCATTER --> P2["Provider B"]
    SCATTER --> P3["Provider C"]
    P1 --> AGG["Aggregator"]
    P2 --> AGG
    P3 --> AGG
    AGG --> REP["One CombinedQuote reply"]
~~~

Aggregator cần **correlation key** để không trộn reply của hai request khác nhau, cùng **completion condition**: đợi đủ ba, chờ tối đa thời gian quy định, hay trả kết quả khi có hai giá hợp lệ? Khi một nhà cung cấp không phản hồi, phải biết partial result có được chấp nhận không.

### 14.3. Bảng thiết kế aggregation

| Quyết định | Câu hỏi |
| --- | --- |
| Correlation | Lấy khóa nào để nhóm replies cùng request? |
| Sequence | Cần biết trước expected count hay dùng dynamic recipients? |
| Completion | Đủ N reply, hết deadline, quorum hay kết quả sớm? |
| Missing result | Trả partial, retry, fallback hay lỗi tổng? |
| Duplicate reply | Có nhận lại cùng provider response không? |
| Late reply | Bỏ qua, lưu audit hay cập nhật kết quả đã trả? |
| State store | Aggregator có cần persistence qua restart không? |
| Resource bound | Có TTL và giới hạn pending group để tránh memory leak? |

**Không nên** dùng một list tĩnh lưu replies toàn cục cho nhiều request chạy song song; dễ trộn dữ liệu và vi phạm quyền tenant. Correlation và state phải tách đúng theo request/tenant được xác thực.

### 14.4. Header propagation

Khi dùng transformer hoặc handler tạo Message mới, nên:

- Giữ **requestId/correlationId/traceId** trong phạm vi cần thiết.
- Để Spring Integration quản lý các reply/error headers nội bộ khi có thể, tránh tự tạo vòng định tuyến không kiểm soát.
- Không forward toàn bộ headers từ HTTP client qua broker hoặc hệ thống nội bộ mà không lọc; có thể mang dữ liệu giả mạo, credential hoặc nội dung không phù hợp.
- Chuyển đổi header giữa JMS/AMQP/Kafka/HTTP theo **bản đồ có kiểm thử**.
- Đảm bảo mỗi reply ánh xạ đúng requester/tenant và không bị trộn giữa những request đồng thời.

## 15. Backpressure, thread pool và giới hạn số request đang chờ

Request/reply thường **giữ trạng thái pending trong thời gian đợi reply**. Tăng số request đồng thời mà không giới hạn có thể làm cạn thread, connection, heap hoặc các slot correlation.

### 15.1. Bài toán dung lượng đơn giản

Giả sử hệ thống nhận **100 request/giây** và mỗi request mất trung bình **2 giây** để hoàn tất, số request đồng thời đang chờ trong điều kiện ổn định xấp xỉ:

~~~text
concurrent in-flight requests ≈ arrivalRate × averageResponseTime
                             ≈ 100 × 2
                             ≈ 200
~~~

Đây chỉ là **ước lượng trung bình** theo trực giác của Little's Law trong điều kiện ổn định, không thay thế load test. P95/P99 response time, burst traffic, retry và timeout có thể làm số request đang chờ cao hơn nhiều.

### 15.2. Nơi có thể bị nghẽn

| Thành phần | Triệu chứng | Biện pháp cân nhắc |
| --- | --- | --- |
| HTTP ingress | Thread/connection đang chờ nhiều, 5xx/timeout | Rate limit, deadline, async accepted job |
| DirectChannel handler | Caller bị chặn theo độ trễ I/O | Giới hạn timeout ở remote call, tối ưu handler |
| ExecutorChannel | Queue đầy, task bị reject | Bounded queue, bulkhead, durable handoff khi cần |
| JMS/AMQP reply queue | Backlog reply, không khớp correlation | Consumer health, cleanup, reply TTL |
| Kafka reply topic | Lag reply, partition không assigned | Reply consumer group/partition configuration |
| Connection pool | Hết kết nối HTTP/DB/broker | Bounded pool, timeout, tuning theo tải |
| Aggregator | Pending groups tăng không dọn | Group timeout, expiry, release/cleanup |

### 15.3. Bulkhead và circuit breaker

Nếu dịch vụ pricing bên ngoài chậm, không để **mọi thread xử lý đơn hàng** bị chiếm chỉ vì giá chưa có:

1. Đặt timeout thực tế theo SLA.
2. Giới hạn số request đồng thời tới pricing bằng bulkhead/rate limiter.
3. Dùng circuit breaker khi nguồn lỗi lặp lại, có chính sách thử phục hồi.
4. Retry có giới hạn với jitter, tránh thác retry từ nhiều lớp.
5. Với query có thể dùng cache/fallback **nếu nghiệp vụ cho phép**; không trả giá giả hay dữ liệu sai để làm đẹp tỷ lệ success.

### 15.4. Tốc độ reply ảnh hưởng trải nghiệm caller

Một reply sau deadline có thể vẫn là kết quả đúng của hệ đích nhưng **không còn hữu ích** cho caller. Với báo giá có thời hạn, reply nên mang giá trị validity hoặc quote expiry; đừng cache một giá đã hết hiệu lực chỉ vì lần trước nhận được status thành công.

## 16. Bảo mật giao tiếp và dữ liệu reply

Gateway là một **ranh giới tin cậy**: nó có thể chuyển dữ liệu và danh tính người gọi sang một hệ thống khác. Nếu định tuyến sai hoặc bỏ kiểm soát, một request từ tenant A có thể nhận reply chứa dữ liệu tenant B.

### 16.1. Checklist bảo mật

- [ ] Caller được xác thực theo nguồn phù hợp (IdP/SSO, service principal, mTLS hoặc cơ chế khác được duyệt).
- [ ] Authorization áp dụng cho **người gọi, hành động và tài nguyên**, không chỉ đăng nhập thành công.
- [ ] Payload và headers được validate; không tin userId/tenantId do bên ngoài tự khai khi không có xác minh.
- [ ] Reply được định tuyến theo correlation chính xác, không rò sang caller khác.
- [ ] Outbound gateway có TLS, xác minh server và quản lý credential theo chính sách.
- [ ] Service credential của gateway có **least privilege**, không dùng shared admin account nếu không cần.
- [ ] Không log access token, refresh token, password, private key hoặc PII ngoài mục đích cần thiết.
- [ ] Giới hạn kích thước request/reply, số in-flight, timeout và tần suất gọi để chống quá tải.
- [ ] Xử lý JSON/XML/schema theo thư viện an toàn và cấu hình parser phù hợp.
- [ ] Không chuyển nội dung exception nội bộ/stack trace nguyên văn ra HTTP response công khai.
- [ ] Có chính sách retry/idempotency để caller độc hại không dễ tạo side effect lặp.
- [ ] Có audit requestId, người gọi, target, decision/outcome nhưng hạn chế metadata nhạy cảm.

### 16.2. Bảo vệ correlation metadata

Correlation ID thường giúp định tuyến đúng reply, nhưng **không phải bằng chứng authorization**. Người ngoài biết requestId của người khác không có nghĩa được xem kết quả của họ. Nếu API cho phép GET /jobs/{requestId}, phải kiểm tra **requester ownership/tenant** phía server.

### 16.3. Gateway tạo lỗ hổng confused deputy

Một gateway sở hữu credential mạnh để gọi Finance API có thể bị lợi dụng nếu nó nhận tùy ý accountId từ client và thực hiện giao dịch không kiểm tra quyền. Vì vậy cần:

~~~text
Caller được xác thực
   → policy kiểm tra quyền trên account/resource cụ thể
   → chỉ giữ các trường request hợp lệ
   → gateway gọi Finance API bằng credential hạn chế
   → validate reply và scope
   → trả dữ liệu đã được phép
~~~

Không dựa vào việc **gateway là service nội bộ** để bỏ qua kiểm tra quyền nghiệp vụ.

## 17. Vòng đời gateway, kết nối, failover và graceful shutdown

Gateway request/reply phải có chiến lược vận hành khi **application khởi động**, **broker hoặc API bên ngoài không sẵn sàng**, **deploy rolling** và **shutdown có request đang chờ**.

### 17.1. Startup

- [ ] Channel, handler, gateway proxy và adapter liên quan được đăng ký đúng trong Spring ApplicationContext.
- [ ] Định nghĩa startup order khi gateway phụ thuộc kết nối broker, MessageStore hoặc schema registry.
- [ ] Kiểm tra remote endpoint/destination, credential, quyền publish/consume và health.
- [ ] Không chỉ kiểm tra app HTTP trả 200; đường reply thực sự phải hoạt động.
- [ ] Với broker reply queue/topic, xác minh listener đã nhận/subscribe đúng trước khi bắt đầu gửi request cần reply.
- [ ] Khởi tạo idempotency store, correlation registry và giới hạn số pending request.
- [ ] Có cách từ chối nhanh/fallback có kiểm soát nếu downstream chưa sẵn sàng.

### 17.2. Shutdown và rolling deployment

- [ ] Ngừng nhận request mới hoặc báo trạng thái không sẵn sàng theo lifecycle.
- [ ] Cho request đang xử lý hoàn tất đến deadline phù hợp, không giữ vô hạn.
- [ ] Với broker, xác định reply đang chờ có được lưu/bỏ qua/chuyển sang instance khác không.
- [ ] Dọn pending correlation và temporary reply destination có thể được dọn an toàn.
- [ ] Không ack/commit request message trước business commit nếu contract yêu cầu.
- [ ] Retry hoặc resume có bảo vệ idempotency khi caller gửi lại sau deploy.
- [ ] Không làm rò thông tin của request A sang request B khi registry được tạo lại.

Gateway **đồng bộ trong JVM** thường mất trạng thái chờ khi process chết. Một reply đến sau restart không thể tự tìm về method call cũ vốn đã biến mất. Nếu bài toán cần **phục hồi xuyên restart**, hãy chuyển sang durable job/request state và kết quả truy vấn/callback, hoặc thiết kế coordinator bền vững chuyên biệt.

### 17.3. Kết nối remote

| Hệ thống ngoài | Tài nguyên/vòng đời cần quản lý | Triệu chứng |
| --- | --- | --- |
| HTTP API | Connection pool, TLS, DNS, timeout, credential rotation | Socket timeout, 429/503, pool exhausted |
| JMS | ConnectionFactory, session, listener, reply destination | Broker restart, temporary reply mất, redelivery |
| RabbitMQ | TCP/channel, exchange/queue, direct-reply-to listener | Reply queue disconnected, unknown correlation |
| Kafka | Producer, reply consumer, assignment, offset, topic | Rebalance, lag, pending reply tăng |
| JDBC | Connection pool, transaction, query timeout | Deadlock, lock wait, pool starvation |
| SFTP/File bridge | Remote session, directory, metadata processing | File chưa hoàn tất, transport timeout |

**Không coi reconnect tự động là đủ.** Phải kiểm tra request vừa gửi trước khi mất kết nối đã được đích xử lý chưa và cách caller xác minh kết quả sau timeout.

### 17.4. Nhiều instance của requester

Nếu ba instance gateway cùng gửi vào một request queue và cùng dùng một reply queue, phải bảo đảm **mỗi reply tới đúng instance sở hữu pending request**, hoặc có một lớp xử lý state phân tán được thiết kế. Không thể mặc nhiên dùng cạnh tranh consumer trên reply queue rồi mong tất cả reply đều về đúng JVM.

Với HTTP request/reply, connection thường gắn caller với instance nhận request. Nếu instance chết, client có thể retry ở instance khác; **idempotency store phải chia sẻ/bền vững** nếu side effect cần chống lặp giữa instance.

### 17.5. Reconfiguration và version compatibility

Khi thay schema PriceRequest/PriceReply, responder cũ và requester mới có thể chạy song song trong rolling deploy. Cần:

- Version contract hoặc cơ chế backward compatibility.
- Kiểm tra field mới tùy chọn và trường bắt buộc.
- Không thay ý nghĩa một field mà giữ schemaVersion không đổi.
- Triển khai consumer hỗ trợ version mới trước khi producer bắt buộc gửi version mới khi phù hợp.
- Có test canary/rollback cho luồng hai chiều, không chỉ chiều request.

## 18. Observability và runbook cho Request–Reply

Mọi gateway cần đo cả **tốc độ nhận/gửi request** và **khả năng nhận reply đúng hạn**. Một service có thể xử lý thành công rất nhiều request nhưng client vẫn timeout do reply routing lỗi.

### 18.1. Các chỉ số quan trọng

| Metric | Mục đích | Dấu hiệu cần điều tra |
| --- | --- | --- |
| **request sent / accepted** | Thông lượng gửi vào channel/destination | Giảm bất thường hoặc tăng đột ngột |
| **reply received** | Số reply gateway nhận | Chênh với sent ngoài dự kiến |
| **reply success / business reject** | Phân loại outcome nghiệp vụ | Từ chối tăng bất thường |
| **gateway reply timeout** | Caller không nhận reply trong deadline | Broker/handler chậm hoặc mất correlation |
| **late / unmatched reply** | Reply đến sau timeout hoặc không khớp | Pending cleanup, topology reply queue |
| **request/reply latency P50/P95/P99** | Trải nghiệm caller và khả năng đáp ứng | Tail latency tăng dù median ổn |
| **in-flight requests** | Số cuộc trao đổi đang chờ | Gần giới hạn/không giảm |
| **executor queue/rejection** | Backpressure tại xử lý bất đồng bộ | Queue đầy, message bị từ chối |
| **HTTP connect/read failures** | Vấn đề mạng và hệ ngoài | Tăng cùng lúc nhiều request |
| **retry / duplicate detected** | Tải và rủi ro side effect lặp | Retry storm hoặc idempotency conflict |
| **broker reply queue depth / lag** | Phản hồi tích đọng | Reply listener không hoạt động |
| **correlation registry size** | Dùng bộ nhớ để chờ reply | Tăng không giảm do thiếu cleanup |
| **last successful end-to-end reply** | Tiến triển theo contract | Quá lâu dù sent vẫn tăng |

Mọi metric nên được chia theo **endpoint, target, operation, environment**, không đính eventId/requestId làm label cardinality vô hạn. Chi tiết requestId nên đi trong tracing/log có phân quyền truy cập.

### 18.2. Mẫu audit an toàn

~~~json
{
  "requestId": "PRICE-LAB-001",
  "correlationId": "CORR-LAB-019",
  "operation": "price.quote",
  "requesterType": "service",
  "target": "pricing-api-lab",
  "schemaVersion": 1,
  "requestSentAt": "2026-11-23T10:00:00+07:00",
  "replyReceivedAt": "2026-11-23T10:00:00.170+07:00",
  "outcome": "SUCCESS",
  "latencyMs": 170,
  "retryAttempt": 0,
  "traceId": "TRACE-LAB-020"
}
~~~

Đây là log **minh họa**, không phải format mặc định của Spring Integration. Không ghi raw API token, password, private key, thông tin khách hàng không cần thiết hoặc toàn bộ response nhạy cảm.

### 18.3. Runbook A — Gateway timeout hàng loạt

1. Xem request sent, reply received, timeout rate và latency theo endpoint.
2. Kiểm tra remote API/broker, listener reply, destination, partition assignment và connection pool.
3. Tìm trường hợp **request đã được đích commit nhưng reply không quay về**.
4. Xác định lỗi correlation/header mapping hay chỉ là handler chậm.
5. Kích hoạt containment hợp lệ: rate limit, circuit breaker, giảm concurrency hoặc chuyển sang queue bền vững nếu cần.
6. Không bật retry vô hạn. Với command có side effect, tra trạng thái theo requestId trước retry.
7. Ghi root cause, phạm vi request UNKNOWN và kế hoạch reconciliation.

### 18.4. Runbook B — Reply đến sai người gọi

Đây là lỗi nghiêm trọng về dữ liệu và phân quyền. Dừng đường trả dữ liệu bị ảnh hưởng theo quy trình, kiểm tra routing/correlation/tenant boundary, bảo vệ log, đánh giá phạm vi rò rỉ, sửa mapping và thêm test hai request đồng thời trả reply đảo thứ tự. Không che lỗi bằng cách sắp xếp lại callback theo thời gian tới.

### 18.5. Runbook C — Caller retry tạo side effect trùng

Kiểm tra requestId/idempotencyKey của hai lần gửi, ACK/reply timeline, transaction và unique constraint bên responder. Khắc phục dữ liệu bị nhân đôi theo nghiệp vụ có thẩm quyền; thêm idempotency ở **điểm commit** thay vì chỉ làm dedupe trong memory ở gateway.

### 18.6. Runbook D — Một responder gửi hai reply

Nếu responder redelivery request hoặc logic bị retry sau commit, có thể phát hai reply có cùng correlation. Gateway phải xử lý kết quả thứ hai theo contract, không gửi thêm một reply không mong muốn vào request khác. Theo dõi duplicate/late replies; sửa responder idempotency và cleanup registry.

## 19. Bài thực hành tổng hợp: Quote Gateway và remote Price Service

Mục tiêu của lab là xây một gateway **dễ gọi từ Java**, kết nối được với handler local, rồi mô phỏng remote API/broker có timeout, lỗi và reply đảo thứ tự. Dùng toàn bộ **dữ liệu giả, endpoint thử nghiệm hoặc mock được phép**.

### 19.1. Kiến trúc hai chặng

**Chặng A — In-process:** QuoteApplicationService → QuoteGateway → DirectChannel → PricingHandler → QuoteReply. Chỉ kiểm tra mapping Java–Message–Reply.

**Chặng B — Remote:** HTTP inbound gateway nhận yêu cầu từ client; flow gọi HTTP outbound gateway tới mock Price API và trả reply. Sau đó tùy chọn thay remote bằng JMS/AMQP với queue request/reply.

~~~mermaid
flowchart TD
    CLIENT["HTTP Client"] --> IG["HTTP Inbound Gateway"]
    JAVA["Java Application Service"] --> MG["@MessagingGateway"]
    IG --> REQ["Quote request channel"]
    MG --> REQ
    REQ --> VALIDATE["Validate + authorize"]
    VALIDATE --> ROUTE{"Local or remote?"}
    ROUTE -->|Local| LOCAL["PricingHandler"]
    ROUTE -->|Remote| OUT["HTTP/JMS Outbound Gateway"]
    OUT --> REMOTE["Mock Price Service"]
    REMOTE --> OUT
    LOCAL --> REP["Reply mapping"]
    OUT --> REP
    REP --> IG
    REP --> MG
~~~

Đường reply trên sơ đồ là logic; thực tế gateway và framework định tuyến nhờ reply channel/correlation của **từng** request. Khi làm lab hãy thử **hai lời gọi đồng thời** có requestId khác nhau để chứng minh kết quả không bị trộn.

### 19.2. Fixture đầu vào

| Request | SKU | Số lượng | Kết quả mẫu |
| --- | --- | --- | --- |
| **PRICE-LAB-001** | SKU-LAB-A | 2 | 250.000 VND |
| **PRICE-LAB-002** | SKU-LAB-A | 1 | 125.000 VND |
| **PRICE-LAB-003** | SKU-NOT-FOUND | 1 | Domain reply SKU_UNAVAILABLE |
| **PRICE-LAB-004** | SKU-LAB-A | 0 | Validation error |
| **PRICE-LAB-005** | SKU-LAB-A | 5 | Giả lập remote timeout |

Đây chỉ là fixture; hệ pricing thật có currency, discount, customer tier, pricing version và thời hạn hiệu lực riêng. Phải validate đầy đủ khi thay mock.

### 19.3. Các bước thực hiện

**Bước 1 — Dựng core flow.** Tạo QuoteRequest, QuoteReply, QuoteGateway, GatewayConfiguration, PricingHandler theo phần 6. Khởi động Spring context và gọi quote từ một service.

**Bước 2 — Kiểm tra mapping.** Với request hợp lệ, QuoteReply phải giữ requestId, SKU, currency và giá đúng theo fixture. Với quantity=0, phải có đường lỗi hợp lệ thay vì trả giá 0 như một báo giá thành công.

**Bước 3 — Thử DirectChannel.** Tạo một handler chủ động ghi log start/end để thấy caller và handler trong cùng call stack nếu không thêm async boundary. Không cần poller.

**Bước 4 — Thử ExecutorChannel.** Đổi requestChannel sang executor có queue giới hạn. Quan sát reply đến sau khi handler kết thúc, kiểm tra timeout và cách nhận lỗi từ thread khác.

**Bước 5 — Tạo remote mock.** Thay handler local bằng HTTP outbound gateway hoặc một mock responder gửi reply qua message channel. Thêm connect/read timeout thực tế trong mock.

**Bước 6 — Đảo thứ tự reply.** Gửi Q1, Q2 gần như đồng thời; giữ Q1 trong 300 ms và trả Q2 sau 50 ms. Cả hai caller phải nhận đúng requestId và giá tương ứng.

**Bước 7 — Mô phỏng mất reply.** Responder thực thi xong nhưng không gửi reply. Caller timeout; log phải ghi UNKNOWN/TIMED_OUT rõ ràng. Nếu đây là command có side effect, không retry tùy tiện.

**Bước 8 — Idempotency.** Thêm command CreateOrder với idempotencyKey và một kho kết quả bền vững thử nghiệm. Gửi cùng request hai lần; hiệu ứng tạo đơn chỉ xảy ra một lần, trả kết quả nhất quán.

**Bước 9 — Thử lỗi và bảo mật.** Cho user tenant A đổi tenantId thành tenant B; backend phải từ chối. Cho remote trả 429/503, schema sai và reply muộn; phân loại lỗi và retry tương ứng.

**Bước 10 — Vận hành.** Đo sent/replied/timedOut, late reply, in-flight và latency; viết runbook cho reply queue chết, HTTP timeout và correlation mismatch.

### 19.4. JUnit test cho chặng A

Ví dụ trong project Spring Boot đã bật Spring Integration, Spring Boot Test và JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class QuoteGatewayTest {

    @Autowired
    private QuoteGateway quoteGateway;

    @Test
    void shouldReturnCorrelatedQuote() {
        QuoteReply result = quoteGateway.quote(
                new QuoteRequest("REQ-001", "SKU-LAB-A", 2, "STANDARD")
        );

        assertEquals("REQ-001", result.requestId());
        assertEquals("SKU-LAB-A", result.sku());
        assertEquals("VND", result.currency());
        assertEquals(new BigDecimal("250000"), result.total());
    }

    @Test
    void shouldRejectInvalidQuantity() {
        assertThrows(RuntimeException.class, () ->
                quoteGateway.quote(
                        new QuoteRequest("REQ-002", "SKU-LAB-A", 0, "STANDARD")
                )
        );
    }
}
~~~

Đoạn test ở trên là **ví dụ để người học chạy**, không phải báo cáo đã chạy trong repository này. Test nên bổ sung kiểm tra **loại lỗi và mã business** thay vì chỉ RuntimeException; exception có thể được gateway wrap. Khi viết integration test timeout, dùng eventual assertion có deadline và test double có kiểm soát thay vì Thread.sleep dài tùy ý.

### 19.5. Một thí nghiệm để hiểu replyChannel

Nếu bạn tự gửi một message vào channel mà **không dùng gateway proxy**, một handler có kết quả trả về cần biết gửi reply đi đâu. Có thể thiết kế đường trả riêng hoặc gắn reply channel hợp lệ vào message:

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

// Minh họa trong một Spring component/test có pricingRequests được inject.
QueueChannel privateReply = new QueueChannel(1);

Message<QuoteRequest> message = MessageBuilder.withPayload(
        new QuoteRequest("REQ-MANUAL", "SKU-LAB-A", 2, "STANDARD")
    )
    .setReplyChannel(privateReply)
    .build();

boolean sent = pricingRequests.send(message);
if (!sent) {
    throw new IllegalStateException("Cannot send request");
}

Message<?> reply = privateReply.receive(3000);
if (reply == null) {
    throw new IllegalStateException("Reply timeout");
}

QuoteReply result = (QuoteReply) reply.getPayload();
~~~

Đây là đoạn code **minh họa trong một method/test**, với biến pricingRequests phải có sẵn dưới dạng MessageChannel đã inject và handler trả reply theo cơ chế của framework. Nó cho thấy gateway thực chất **quản lý giúp việc gửi request và nhận reply**, không tạo ra một loại message hoàn toàn khác.

Không nhúng kênh reply trong bộ nhớ qua ranh giới JVM/broker bằng cách serialize trực tiếp object channel. Khi đi qua mạng, cần **reply destination** và các header correlation phù hợp giao thức.

### 19.6. Phần mở rộng

1. Thêm @Gateway ở một method riêng để ghi đè requestChannel hoặc replyTimeout trên gateway interface theo chính sách và phiên bản annotation đang dùng.
2. Tạo hai handler với một router và response code cho SKU không khả dụng.
3. Dùng Scatter–Gather lấy giá từ ba mock providers, trả partial nếu hai provider hợp lệ trước deadline.
4. Thêm bộ đo inflight request; test 100 request đồng thời để phát hiện lẫn correlation.
5. Thêm JMS/AMQP request/reply ở broker test, quan sát temporary reply queue và requester restart.
6. Mô phỏng Kafka reply topic với correlation registry, reply muộn và rebalance; so độ phức tạp với HTTP.
7. Thêm outbox cho CreateOrder và inbox cho responder để chống duplicate xuyên restart.
8. Kiểm tra tenant isolation khi hai caller đồng thời cùng có SKU nhưng khác giá/chính sách.

## 20. Ma trận kiểm thử Request–Reply Gateway

Các ca này mô tả **điều kiện mong đợi**, không phải kết quả tự động đã chạy. Với từng ca, ghi Input, Expected, Actual, PASS/FAIL/UNKNOWN và Evidence.

| ID | Tình huống | Điều kiện PASS |
| --- | --- | --- |
| **GW-01** | QuoteGateway gọi DirectChannel và handler trả reply | Caller nhận đúng QuoteReply |
| **GW-02** | Handler trả payload khác kiểu khai báo | Lỗi mapping được phát hiện, không trả dữ liệu sai |
| **GW-03** | Request thiếu SKU hoặc quantity=0 | Validation từ chối, không thành công giả |
| **GW-04** | Reply giữ đúng requestId của caller | Không bị trộn giữa các request |
| **GW-05** | Hai request đồng thời reply đảo thứ tự | Mỗi caller nhận đúng reply |
| **GW-06** | Router nhận vùng không hỗ trợ | Domain rejection hoặc lỗi rõ, không treo chờ vô hạn |
| **GW-07** | Handler đồng bộ ném exception | Gateway nhận lỗi phù hợp thay vì thành công |
| **GW-08** | ExecutorChannel dispatch xử lý ở thread khác | Không coi send accepted là business committed |
| **GW-09** | Executor queue đầy | Rejection/backpressure được ghi nhận |
| **GW-10** | QueueChannel có request nhưng không có consumer | Gateway timeout/cảnh báo, không giả reply |
| **GW-11** | HTTP inbound gateway nhận JSON đúng schema | Trả kết quả và HTTP status đúng contract |
| **GW-12** | HTTP caller gửi tenantId ngoài quyền | Backend từ chối, không rò reply |
| **GW-13** | Outbound HTTP API trả 429 | Backoff/tôn trọng rate limit, không retry storm |
| **GW-14** | Outbound HTTP API trả 503 | Phân loại lỗi transient, retry có giới hạn |
| **GW-15** | Remote đã commit nhưng reply mất | Không tạo side effect thứ hai khi retry |
| **GW-16** | Reply đến sau defaultReplyTimeout | Late reply được xử lý, pending state được dọn |
| **GW-17** | Reply có correlation ID không tồn tại | Không giao nhầm dữ liệu cho caller khác |
| **GW-18** | Responder phát reply hai lần | Không gửi hai result hoặc trộn vào request khác |
| **GW-19** | RequestId cũ với payload khác | Idempotency key reuse bị phát hiện |
| **GW-20** | JMS responder nhận request và trả JMSReplyTo hợp lệ | Correlation đúng, không lạc reply |
| **GW-21** | JMS broker restart lúc requester chờ | Không báo success giả; trạng thái timeout rõ |
| **GW-22** | AMQP reply queue/direct reply-to bị ngắt | Gateway timeout/error, không mất dấu theo policy |
| **GW-23** | Kafka request/reply qua hai topic | Request/reply được nối đúng theo chiến lược correlation |
| **GW-24** | Kafka reply consumer rebalance | Late/duplicate reply được xử lý an toàn |
| **GW-25** | SFTP file được poll rồi gọi HTTP gateway | Phân biệt polling source và request/reply downstream |
| **GW-26** | JDBC query gateway timeout | Phân biệt connect/query timeout với business error |
| **GW-27** | Scatter–Gather thiếu một provider | Completion strategy xử lý deadline/partial đúng |
| **GW-28** | Một caller mất kết nối HTTP sau khi tạo job | Có cách tra cứu theo jobId, không tạo duplicate |
| **GW-29** | 100 request đồng thời, reply đảo thứ tự | Correlation và tenant isolation không bị sai |
| **GW-30** | Consumer dùng credential vượt quyền | Authorization ngăn hành động không hợp lệ |
| **GW-31** | Audit chứa raw token/password | Test kiểm tra credential bị loại bỏ/redact |
| **GW-32** | Deploy rolling khi còn pending reply | Không rò rỉ reply, có timeout/resume strategy |

### 20.1. Mẫu báo cáo một ca kiểm thử

~~~yaml
testCase: GW-15
requestId: CREATE-ORDER-LAB-0098
scenario: "Business commit succeeds but the reply is lost"
expected: "Caller sees UNKNOWN; retry with same idempotency key does not duplicate"
actual: "Fill with observed result when the lab runs"
result: PENDING
evidenceRef: "lab://tests/GW-15"
owner: gateway-lab
verifiedAt: null
~~~

Không chuyển **PENDING** sang PASS chỉ vì mã triển khai có idempotency trên giấy. Phải kiểm tra trạng thái đích thực tế và log sau khi mô phỏng mất reply/crash.

### 20.2. Phân loại lỗi kiểm thử

- **Contract tests:** request/reply mapping, schema, validation, status codes, correlation.
- **Integration tests:** HTTP/JMS/AMQP/Kafka adapter và remote responder trong môi trường thử.
- **Failure injection:** mất reply, remote timeout, broker restart, schema mismatch, duplicated request.
- **Concurrency tests:** nhiều caller, reply đảo thứ tự, giới hạn inflight và executor queue.
- **Security tests:** authorization theo subject/resource/tenant, credential redaction.
- **Recovery tests:** restart requester/responder, retry idempotent, cleanup pending correlation.

## 21. Anti-patterns và checklist production

### 21.1. Những lỗi thiết kế hay gặp

| Anti-pattern | Vì sao sai | Cách làm phù hợp hơn |
| --- | --- | --- |
| **Xem Messaging Gateway như HTTP gateway** | Gateway Java không cần HTTP | Phân biệt gateway proxy với HTTP/JMS/AMQP endpoint |
| **Dùng outbound channel adapter rồi đợi reply** | Adapter một chiều không tự tạo request/reply contract | Dùng outbound gateway và reply handling |
| **Xóa replyChannel/correlation khi transform** | Reply không quay về caller đúng | Bảo toàn metadata định tuyến cần thiết |
| **Trả reply theo thứ tự đến** | Reply đảo thứ tự gây lộ dữ liệu | Matching theo correlation chính xác |
| **Đặt reply timeout như biện pháp hủy remote transaction** | Timeout không chứng minh side effect chưa chạy | Deadline, cancellation hợp lệ, idempotency, reconciliation |
| **Retry command sau timeout bằng requestId mới** | Tạo side effect lặp | Giữ idempotencyKey, tra cứu kết quả |
| **Giữ HTTP connection mở hàng giờ** | Proxy/client timeout, restart mất state | Async accepted job + status/callback |
| **Đặt QueueChannel nhưng không tạo consumer** | Message không được xử lý, gateway timeout | PollingConsumer hoặc thiết kế channel khác |
| **Đẩy request vào ExecutorChannel rồi báo success** | Handler chưa commit, crash có thể mất work | Durable handoff hoặc ack đúng điểm |
| **Dùng PublishSubscribeChannel mong một reply tự động** | Nhiều reply, không có completion strategy | Scatter–Gather/Aggregator có correlation |
| **Chỉ đo HTTP 200** | Bỏ sót pending, late reply, business reject | Đo gửi–reply–commit–timeout |
| **Dùng reply queue chung không có isolation** | Instance khác nhận reply, correlation bị lạc | Routing/consumer setup phù hợp |
| **Coi Kafka là RPC miễn phí** | Reply topic, offset, group và state phức tạp | Chọn giao thức theo SLA và tính chất nghiệp vụ |
| **Dùng role nội bộ của gateway thay caller authorization** | Confused deputy, vượt tenant | Kiểm tra quyền từng tài nguyên và least privilege |
| **Log full payload/header** | Rò credential và PII | Redaction, data minimization và RBAC audit |

### 21.2. Checklist thiết kế

- [ ] Đã xác định gateway là Java messaging, inbound hay outbound và có nhu cầu reply thật.
- [ ] Đã phân biệt request/reply với fire-and-forget adapter và polling source.
- [ ] Message request và reply có schema, version, validation, error contract.
- [ ] Có requestId, correlation strategy và business idempotencyKey khi có side effect.
- [ ] Không nhận dữ liệu quyền/tenant từ nguồn ngoài khi chưa xác minh.
- [ ] Có cấu hình request send timeout, reply timeout và I/O timeout độc lập.
- [ ] Biết caller sẽ thấy gì khi business reject, technical failure, timeout và UNKNOWN.
- [ ] Có cách xử lý reply muộn, duplicate reply và unknown correlation.
- [ ] Đã hiểu threading của DirectChannel/ExecutorChannel/QueueChannel.
- [ ] Không giữ transaction giả xuyên HTTP/broker/DB khi các thành phần không cùng cơ chế atomic.
- [ ] Nếu command có side effect, retry phải dựa trên idempotency và trạng thái thật.
- [ ] HTTP gateway có rate limit, authn/authz, content type, schema và response mapping.
- [ ] Broker gateway có reply destination/topic, listener, ack/offset và cleanup được kiểm tra.
- [ ] Multi-instance routing không đưa reply của requester A sang requester B.
- [ ] Khi request chạy lâu, có cơ chế job status/callback thay vì chờ vô hạn.
- [ ] Bounded concurrency, in-flight limit, circuit breaker/backpressure phù hợp tải.
- [ ] Logs/metrics/tracing nối được request tới handler và reply mà không rò secret.
- [ ] Đã thử remote failure, retry, duplicate, slow reply, restart, schema mismatch.
- [ ] Có runbook cho timeout, reply mismatch, duplicate side effect và shutdown.

## 22. Tổng kết: Gateway là ranh giới giữa lời gọi và message

**Gateway Request–Reply Pattern** cho phép code gọi một interface hoặc endpoint như một tương tác có kết quả, trong khi Spring Integration tổ chức xử lý bằng **MessageChannel, handler và adapter**.

Những điểm quan trọng nhất:

1. **Messaging Gateway** chuyển lời gọi Java thành request message và ánh xạ reply về giá trị trả về.
2. **Inbound Gateway** nhận yêu cầu từ hệ ngoài và trả kết quả; **Outbound Gateway** gọi hệ ngoài rồi đưa reply vào flow.
3. **replyChannel/correlation** giúp trả đúng kết quả cho đúng request, đặc biệt khi nhiều request đồng thời và reply đảo thứ tự.
4. **DirectChannel, ExecutorChannel, QueueChannel** quyết định cách dispatch, độ trễ, điều kiện lỗi và ranh giới transaction; một send thành công không phải lúc nào cũng là business commit.
5. **HTTP, JMS, AMQP, Kafka** có semantics reply khác nhau; không thể dùng một công thức ack/offset/timeout cho tất cả.
6. **Timeout không có nghĩa hệ đích chưa xử lý**. Với command có side effect, cần idempotency, kiểm tra trạng thái và phục hồi.
7. **File, SFTP và DB** có thể dùng poller ở đầu vào, rồi gọi gateway request/reply ở giữa flow; hai pattern bổ sung chứ không loại trừ.
8. **Observability và security** phải theo sát requestId, correlation, tenant, deadline, reply status và kết quả nghiệp vụ thực tế.

### 22.1. Câu hỏi cuối bài

1. Vì sao một Java interface @MessagingGateway không nhất thiết tạo HTTP request?
2. Nếu handler nhận request nhưng không trả reply, gateway sẽ biểu hiện thế nào?
3. Vì sao replyChannel và correlation ID không phải lúc nào cũng cùng một khái niệm?
4. Nếu dùng ExecutorChannel, lời gọi send thành công có đồng nghĩa remote business đã commit không?
5. Một HTTP request POST timeout sau khi đã tạo đơn, client phải làm gì để tránh đơn trùng?
6. Khi nào nên trả 202 + jobId thay vì giữ gateway chờ reply?
7. Vì sao một shared reply queue giữa nhiều requester instance có thể gây lạc reply?
8. Cần bổ sung gì khi Scatter–Gather nhận thiếu một trong ba reply?
9. Làm sao chứng minh response không rò sang tenant khác khi replies đảo thứ tự?
10. Metric nào giúp phân biệt remote service chậm với correlation registry không còn hoạt động?

**Gợi ý:** (1) gateway ánh xạ method sang message flow bất kỳ; (2) timeout hoặc error theo contract; (3) một bên là đường trả, một bên là khóa ghép; (4) không; (5) giữ idempotencyKey/tra trạng thái; (6) công việc kéo dài; (7) reply consumer không nhận đúng instance; (8) correlation, deadline, completion/partial policy; (9) chạy test concurrency có check requester/tenant; (10) remote latency, reply received/late/unmatched và pending registry size.

**Ghi nhớ cuối cùng:** *Một gateway tốt không chỉ gửi được request và nhận được reply; nó chứng minh được reply thuộc đúng người gọi, đúng nghiệp vụ, đúng thời hạn, đồng thời xử lý an toàn mọi khoảng trống giữa gửi yêu cầu, commit ở hệ đích và nhận phản hồi.*
