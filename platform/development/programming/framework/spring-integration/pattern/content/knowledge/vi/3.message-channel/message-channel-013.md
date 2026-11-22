# Chọn channel theo semantics cần bảo đảm

## 1. Vì sao phải chọn channel từ yêu cầu xử lý?

Trong module **SPRING_INTEGRATION_PATTERN**, chúng ta triển khai các **Enterprise Integration Patterns** bằng Spring Integration nhằm tạo các luồng thông điệp ít phụ thuộc, dễ mở rộng và dễ kiểm thử. Router, Filter, Transformer, Splitter, Aggregator và Gateway xử lý **logic** của flow; **MessageChannel** quyết định **cách một message được chuyển giữa các thành phần**. Khi thêm retry, error channel, correlation và quan sát từng nhánh, lựa chọn channel còn ảnh hưởng đến thread, độ trễ, thứ tự, transaction và khả năng khôi phục sau lỗi.

Xét hai yêu cầu có vẻ giống nhau:

- **Kiểm tra đơn hàng rồi tính tổng tiền ngay trước khi trả HTTP response:** caller phải biết kết quả; một chuỗi xử lý đồng bộ có thể phù hợp.
- **Đã nhận đơn hàng, gửi email xác nhận và cập nhật hệ thống phân tích ở phía sau:** các công việc có thể diễn ra độc lập; cần xác định có phải tất cả consumer đều nhận sự kiện, có cần lưu bền và xử lý lại khi gặp lỗi không.

Chọn cùng một channel cho hai yêu cầu trên có thể dẫn đến sai hợp đồng. Ví dụ, **DirectChannel** chuyển một message đến một handler được chọn và chạy đồng bộ; nó **không** tự phát sự kiện cho mọi subscriber và **không** tạo hàng đợi bền vững.

**Mục tiêu bài học**

1. Định nghĩa chính xác các semantics cần bảo đảm trước khi chọn channel.
2. Phân biệt unicast, broadcast, đồng bộ, bất đồng bộ, buffering và rendezvous.
3. Chọn giữa DirectChannel, ExecutorChannel, QueueChannel, PriorityChannel, PublishSubscribeChannel và những loại đặc thù.
4. Hiểu giới hạn của channel với ordering, durability, delivery guarantee, backpressure, error handling và transaction.
5. Viết kiểm thử xác nhận các thuộc tính đã chọn thay vì chỉ kiểm tra message có được gửi hay không.

## 2. Các chiều semantics phải trả lời trước

**Semantics** ở đây là những hành vi mà người gửi và người nhận được phép trông đợi khi truyền một message. Một quyết định chính xác thường cần nhiều chiều cùng lúc:

| Câu hỏi thiết kế | Hai hoặc nhiều lựa chọn | Tác động chính |
| --- | --- | --- |
| Ai nhận message? | Một consumer / tất cả consumer | Unicast hay broadcast |
| Caller chờ đến đâu? | Chờ handler hoàn tất / chỉ chờ nhận việc | Đồng bộ hay bất đồng bộ |
| Có vùng đệm không? | Chuyển ngay / lưu trong queue | Khả năng hấp thụ tải và tách thời gian |
| Có cần giữ thứ tự? | Theo một nguồn / theo khóa / toàn cục | Giới hạn concurrency và cơ chế sắp xếp |
| Cần tồn tại sau restart? | In-memory / persistent store hoặc broker | Độ bền dữ liệu và khôi phục |
| Khi lỗi thì sao? | Trả lỗi cho caller / phát ErrorMessage / retry / DLQ | Ranh giới xử lý lỗi |
| Cần chung transaction? | Cùng thread/transaction / bước async độc lập | Phạm vi rollback, cam kết dữ liệu |
| Consumer chậm có sao không? | Caller chờ / queue đầy / từ chối / điều tiết | Backpressure và năng lực hệ thống |
| Có cần liên kết các message? | Không / correlationId, sequence, group | Splitter/Aggregator và truy vết |

Đây là các chiều **độc lập một phần**. Chẳng hạn, **ExecutorChannel** tạo ranh giới bất đồng bộ nhưng không mặc nhiên tạo lưu trữ bền. **QueueChannel** tạo vùng đệm, song queue trong bộ nhớ vẫn có thể mất dữ liệu khi tiến trình dừng. **PublishSubscribeChannel** broadcast đến subscriber, song mặc định cũng không đảm bảo phát sự kiện lại sau restart.

### Unicast và broadcast

~~~mermaid
flowchart LR
    P1["Producer"] --> U["Unicast channel"]
    U -->|"Chọn một"| H1["Handler A hoặc B"]
    P2["Producer"] --> B["Broadcast channel"]
    B --> H2["Handler A"]
    B --> H3["Handler B"]
    B --> H4["Handler C"]
~~~

- **Unicast (point-to-point):** một lần dispatch hướng đến một receiver được chọn. Nếu có nhiều subscriber, cơ chế phân phối tải và failover quyết định receiver nào được gọi; **không phải chuỗi A → B → C**.
- **Broadcast (publish-subscribe):** một lần gửi hướng đến nhiều subscriber. Mỗi subscriber có trách nhiệm riêng; cần xác định cách xử lý trường hợp một subscriber thất bại.

Một flow gồm **validate → transform → persist** có thể sử dụng nhiều DirectChannel nối tiếp dù mỗi lần gửi vẫn là unicast. Ngược lại, yêu cầu **persist và audit và notify** cần fan-out hoặc một cơ chế phát sự kiện tương đương nếu cả ba việc đều phải được thực hiện.

### Đồng bộ, bất đồng bộ và chấp nhận công việc

**Đồng bộ** nghĩa là trong một call stack, sender gọi handler và chờ handler trả về. **Bất đồng bộ** nghĩa là bên gửi và bên nhận chạy tách thời điểm hoặc thread. Điều này ảnh hưởng cách xử lý lỗi:

- Với chuỗi **DirectChannel** đồng bộ, lỗi handler thường có thể đi ngược theo call stack tới người gửi.
- Với **ExecutorChannel**, send() thường hoàn tất sau khi executor nhận nhiệm vụ; lỗi phát sinh trong handler chạy về sau thường **không** quay lại trực tiếp với caller ban đầu.
- Với **QueueChannel**, send() biểu thị hành động đưa message vào queue, **không chứng minh** consumer đã xử lý thành công.

Không đồng nhất “**send() trả true**” với “**nghiệp vụ thành công**”. Một flow có Filter có thể loại message hợp lệ về mặt giao thức, một executor có thể nhận task trước khi task chạy, hoặc downstream có thể lỗi sau khi đã ghi một phần dữ liệu.

## 3. Bản đồ các channel thường dùng

| Loại channel | Người nhận | Thread, thời điểm | Buffer | Khi nào phù hợp |
| --- | --- | --- | --- | --- |
| **DirectChannel** | Một handler được chọn | Đồng bộ trên thread sender | Không | Chuỗi xử lý nhanh cần kết quả ngay hoặc chung transaction |
| **FixedSubscriberChannel** | Một subscriber cố định | Đồng bộ | Không | Đường xử lý ổn định, yêu cầu overhead thấp, không thay subscriber |
| **ExecutorChannel** | Một handler được chọn | Executor điều phối task; thường khác thread | Queue/tài nguyên do executor quyết định, không phải MessageStore của channel | Tách việc nặng ra khỏi thread caller |
| **QueueChannel** | Một consumer lấy message cho mỗi lần receive() | Producer send, consumer poll độc lập | Có queue | Làm phẳng đỉnh tải, chủ động kiểm soát poll/consumer |
| **PriorityChannel** | Một consumer lấy mỗi lần receive() | Polling | Queue có ưu tiên | Xử lý message ưu tiên cao trước khi cùng chờ |
| **RendezvousChannel** | Một sender ghép với một receiver | Send/receive đồng bộ tại điểm gặp | Không lưu queue thông thường | Muốn hai phía trao message khi cả hai đều sẵn sàng |
| **PublishSubscribeChannel** | Nhiều subscriber | Đồng bộ theo mặc định; có thể cấu hình Executor | Không có queue bền mặc định | Phát event cho nhiều nhánh độc lập |
| **NullChannel** | Không có consumer xử lý | Nhận rồi loại bỏ | Không | Chủ động kết thúc một nhánh, discard có chủ ý |

**Ghi nhớ:** tên channel mô tả **cơ chế giao nhận**, còn các bảo đảm mạnh hơn như “không mất dữ liệu sau restart”, “xử lý đúng một lần” hoặc “giữ thứ tự trên toàn cụm” đòi hỏi kiến trúc bổ sung và phải được kiểm thử trong môi trường thực.

### DirectChannel: gọi ngay, cùng thread

DirectChannel phù hợp với một pipeline như **Filter → Transformer → Service Activator**, khi các endpoint được nối đúng thứ tự bằng channel hoặc **IntegrationFlow**. Nó thường giữ được **thread-bound context** (ví dụ transaction do Spring quản lý) trên cùng thread.

Điều **không** được bảo đảm: một DirectChannel có nhiều subscriber sẽ gọi lần lượt tất cả; thứ tự toàn cục giữa nhiều thread producer; khôi phục message sau restart.

### ExecutorChannel: tách thread xử lý

ExecutorChannel chuyển việc dispatch qua một **Executor**. Các đặc tính như queue task, số worker, chiến lược từ chối khi quá tải và shutdown phụ thuộc executor được cấu hình. Task có thể chạy rất sớm, thậm chí caller chạy inline nếu cấu hình rejection policy như CallerRunsPolicy; vì thế nói chính xác hơn là “có **ranh giới scheduling**”, không hứa mọi tình huống đều chạy khác thread.

Transaction gắn với thread sender **không tự chuyển** sang thread xử lý. Cần chuẩn bị cơ chế báo lỗi async, giới hạn concurrency và kế hoạch retry/idempotency.

### QueueChannel: tách thời gian producer/consumer

QueueChannel là **PollableChannel**. Producer đưa message vào queue; consumer nhận bằng receive() hoặc poller. Có thể giới hạn capacity để tránh chiếm quá nhiều bộ nhớ và dùng timeout ở send/receive để giới hạn thời gian chờ.

**QueueChannel mặc định là in-memory**; nó **không phải** persistent queue chỉ vì có tên “queue”. Khi cần phục hồi sau restart, phải cấu hình MessageStore có khả năng lưu bền phù hợp, phối hợp transaction, hoặc dùng broker có cơ chế durability tương ứng. Kể cả khi lưu bền, còn cần thiết kế xác nhận xử lý, retry và duplicate handling.

### PriorityChannel: thứ tự ưu tiên khác FIFO

PriorityChannel lấy message theo độ ưu tiên, thường dựa trên header priority hoặc comparator đã cấu hình. Message đến sau nhưng có độ ưu tiên cao có thể được nhận trước. Điều này **không** bảo đảm FIFO toàn cục; khi nhiều message có cùng độ ưu tiên, không nên dựa vào thứ tự nếu chưa có hợp đồng cụ thể.

Rủi ro: luồng message ưu tiên thấp có thể chờ rất lâu nếu liên tục xuất hiện message ưu tiên cao. Khi nghiệp vụ cần fairness, phải thiết kế chính sách phân phối phù hợp.

### PublishSubscribeChannel: một sự kiện cho nhiều nhánh

PublishSubscribeChannel dispatch tới các subscriber. **Mặc định dispatch đồng bộ**; có thể cấu hình Executor để đưa các handler sang xử lý bất đồng bộ. Vì vậy **broadcast và async không phải là một**.

Ứng dụng: khi **order.paid** cần đồng thời kích hoạt analytics, notification và audit. Nếu thất bại ở một subscriber là không được phép làm mất nhánh còn lại, cần thiết kế ranh giới lỗi, retry và độ bền **cho từng nhánh**. Gửi vào PublishSubscribeChannel nội bộ không tạo ra một event bus phân tán bền vững.

### RendezvousChannel, FixedSubscriberChannel và NullChannel

- **RendezvousChannel** trao message khi phía gửi và phía nhận gặp nhau; lời gọi có thể block chờ bên kia. Hữu ích cho phối hợp hai phía, nhưng nguy hiểm nếu một bên không bao giờ đến và không cấu hình timeout.
- **FixedSubscriberChannel** tối ưu cho một subscriber cố định. Không chọn nó khi topology cần thay handler động hoặc cần fan-out.
- **NullChannel** nhận rồi bỏ message theo chủ đích, chẳng hạn nhánh bỏ qua được thiết kế rõ; cần có metric hoặc ghi nhận trước khi loại nếu việc bỏ message phải kiểm toán.

## 4. Cây quyết định chọn channel

~~~mermaid
flowchart TD
    A["Một message cần tới nhiều consumer?"] -->|Có| B["PublishSubscribeChannel"]
    A -->|Không| C["Caller phải chờ handler xong?"]
    C -->|Có| D["DirectChannel"]
    D --> E["Chỉ một subscriber cố định, muốn tối ưu?"]
    E -->|Có| F["FixedSubscriberChannel"]
    E -->|Không| G["Duy trì DirectChannel"]
    C -->|Không| H["Cần tách thời gian bằng queue/poller?"]
    H -->|Có| I["QueueChannel"]
    I --> J["Cần xử lý theo độ ưu tiên?"]
    J -->|Có| K["PriorityChannel"]
    J -->|Không| L["Giữ QueueChannel"]
    H -->|Không| M["ExecutorChannel"]
~~~

Cây này là điểm khởi đầu **chọn cơ chế giao nhận cục bộ**. Trước khi quyết định cuối cùng, tiếp tục hỏi:

1. **Có phải sống qua restart?** Nếu có, bổ sung persistent store/broker và chính sách transaction.
2. **Có cần bảo toàn thứ tự?** Nếu có, xác định thứ tự **theo khóa** hay **toàn cục**, số consumer và concurrency.
3. **Có thể gửi lặp?** Nếu có, consumer phải có cơ chế idempotent hoặc deduplication.
4. **Nếu backlog đầy thì sao?** Bắt buộc định nghĩa timeout, từ chối, cảnh báo và giới hạn tài nguyên.
5. **Lỗi đi đâu?** Xác định cơ chế trả lỗi cho caller, error channel, retry và đường xử lý cuối cùng.

## 5. Ví dụ 1 — Pipeline đồng bộ với DirectChannel

Một API nhận lệnh thanh toán, cần kiểm tra dữ liệu và trả lỗi ngay nếu không hợp lệ. Các bước validate → transform → service chạy nối tiếp, không có việc nặng kéo dài.

~~~mermaid
flowchart LR
    P["HTTP / Gateway"] --> C["paymentInput<br/>DirectChannel"]
    C --> V["Filter: hợp lệ?"]
    V --> T["Transformer"]
    T --> S["Payment service"]
    S --> R["Kết quả trong cùng call stack"]
~~~

Ví dụ cấu hình Spring Integration Java DSL (Java 17+, Spring Integration có Java DSL):

~~~java
import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

record PaymentRequest(String orderId, BigDecimal amount) {}
record PaymentCommand(String orderId, BigDecimal amount) {}

interface PaymentService {
    void execute(PaymentCommand command);
}

@Configuration
@EnableIntegration
class PaymentFlowConfig {

    @Bean
    MessageChannel paymentInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow paymentFlow(PaymentService paymentService) {
        return IntegrationFlow.from("paymentInput")
                .filter(PaymentRequest.class, req ->
                        req.orderId() != null && !req.orderId().isBlank()
                        && req.amount() != null
                        && req.amount().signum() > 0,
                        filter -> filter.throwExceptionOnRejection(true))
                .transform(PaymentRequest.class, req ->
                        new PaymentCommand(req.orderId(), req.amount()))
                .handle(PaymentCommand.class, (command, headers) -> {
                    paymentService.execute(command);
                    return null;
                })
                .get();
    }
}
~~~

**Tại sao DirectChannel?** Caller muốn biết ngay dữ liệu có hợp lệ hay không; các bước trong ví dụ có thể xử lý trên cùng thread và lỗi có đường quay về caller. Đây là một flow **đồng bộ**; không nên mặc nhiên suy ra PaymentService đã giao dịch thành công với hệ thống ngoài nếu service chỉ gửi request từ xa.

**Điều cần kiểm tra:** chính sách từ chối của Filter, thời gian xử lý, transaction thực tế và side effect khi có retry. Mặc dù flow gọi theo chuỗi, một lần gửi vào DirectChannel vẫn dispatch cho **một endpoint được chọn**; thứ tự đến từ cách **IntegrationFlow** nối các endpoint.

## 6. Ví dụ 2 — Tách tác vụ chậm bằng ExecutorChannel

Khi nhận event cập nhật dữ liệu, xử lý ảnh hoặc đồng bộ dữ liệu sang hệ thống khác có thể mất nhiều giây, API không nên phải giữ thread chờ toàn bộ việc đó.

~~~mermaid
sequenceDiagram
    participant P as API producer
    participant E as ExecutorChannel
    participant W as Worker thread
    P->>E: send(message)
    E-->>P: Đã lập lịch xử lý
    E->>W: Dispatch khi executor sẵn sàng
    W->>W: Chạy handler
    Note over P,W: Lỗi sau lúc send trở về không tự quay lại caller
~~~

Ví dụ cấu hình một executor có giới hạn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class AsyncChannelConfig {

    @Bean
    ThreadPoolTaskExecutor integrationWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("integration-worker-");
        executor.initialize();
        return executor;
    }

    @Bean
    MessageChannel asyncProcessingChannel(
            ThreadPoolTaskExecutor integrationWorkerExecutor) {
        return new ExecutorChannel(integrationWorkerExecutor);
    }
}
~~~

**Semantics thật sự:** channel chuyển việc cho executor; nếu executor không thể nhận task, send() có thể lỗi hoặc bị ảnh hưởng bởi rejection policy. Queue capacity ở ví dụ thuộc **ThreadPoolTaskExecutor**, **không** biến ExecutorChannel thành message store bền vững.

Nếu nghiệp vụ có câu “đã nhận rồi thì chắc chắn phải xử lý, kể cả server restart”, chỉ sử dụng ExecutorChannel là **chưa đủ**. Cần chiến lược persist trước khi báo thành công (ví dụ transactional outbox hoặc broker), consumer idempotent, retry và theo dõi backlog.

## 7. Ví dụ 3 — Bounded QueueChannel và backpressure

Giả sử một producer tạo thông điệp nhanh hơn consumer xử lý. QueueChannel có capacity giúp làm phẳng lượng việc trong thời gian ngắn, đồng thời cho một **tín hiệu quá tải** rõ ràng khi queue đầy.

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

QueueChannel commands = new QueueChannel(2);

Message<String> first = MessageBuilder.withPayload("CMD-001").build();
Message<String> second = MessageBuilder.withPayload("CMD-002").build();
Message<String> third = MessageBuilder.withPayload("CMD-003").build();

boolean accepted1 = commands.send(first, 0);  // true
boolean accepted2 = commands.send(second, 0); // true
boolean accepted3 = commands.send(third, 0);  // false: queue đã đầy

Message<?> consumed = commands.receive(0);   // lấy CMD-001
~~~

Một **QueueChannel** là PollableChannel: consumer cần **receive()** hoặc một endpoint được cấu hình **poller**. Nếu không có consumer, message có thể tồn tại trong queue (tới khi đầy) nhưng không được xử lý.

Nên giới hạn ba yếu tố:

| Điều kiện | Quyết định cần có |
| --- | --- |
| Queue đầy | Trả lỗi/429, chờ có timeout, giảm tốc producer hoặc chuyển sang nơi lưu bền |
| Consumer xử lý chậm | Thêm worker phù hợp, đo queue depth/age, tối ưu điểm nghẽn |
| Tiến trình restart | Chấp nhận mất message trong RAM hoặc triển khai persistent store/broker |

**Quan trọng:** đưa message vào queue thành công không đồng nghĩa một consumer đã hoàn tất xử lý. Nếu consumer nhận rồi crash, mức độ mất/khôi phục message còn phụ thuộc message store, transaction và cơ chế xác nhận xử lý. Không nên gọi QueueChannel in-memory là “at-least-once” hoặc “exactly-once”.

### Khi nào cần PriorityChannel?

Ví dụ nghiệp vụ xử lý cảnh báo bảo mật trước yêu cầu tổng hợp thông thường. PriorityChannel có thể lấy message theo header priority:

~~~java
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.integration.support.MessageBuilder;

PriorityChannel alerts = new PriorityChannel();

alerts.send(MessageBuilder.withPayload("daily-summary")
        .setPriority(1)
        .build());
alerts.send(MessageBuilder.withPayload("security-alert")
        .setPriority(10)
        .build());

// Consumer poll sau cả hai lần send: thông điệp ưu tiên cao
// có thể được lấy trước thông điệp đã được gửi từ sớm hơn.
~~~

Trong thực tế, các message chỉ được so sánh về priority khi **cùng đang chờ** trong queue. PriorityChannel không làm gián đoạn một handler đang xử lý message ưu tiên thấp, và không đảm bảo thời gian hoàn thành của cảnh báo.

## 8. Ví dụ 4 — PublishSubscribeChannel cho fan-out

Sau khi thanh toán thành công, cần ba nhánh **audit**, **notification**, **analytics** nhận cùng một sự kiện:

~~~mermaid
flowchart LR
    E["payment.completed"] --> PS["PublishSubscribeChannel"]
    PS --> A["Audit subscriber"]
    PS --> N["Notification subscriber"]
    PS --> M["Analytics subscriber"]
~~~

Ví dụ Java thuần:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

PublishSubscribeChannel events = new PublishSubscribeChannel();
List<String> observed = new ArrayList<>();

events.subscribe(message -> observed.add("audit"));
events.subscribe(message -> observed.add("notification"));
events.subscribe(message -> observed.add("analytics"));

events.send(MessageBuilder.withPayload("PAYMENT-42")
        .setHeader("eventType", "payment.completed")
        .build());

// Theo cấu hình mặc định đồng bộ, cả ba subscriber được gọi.
// Không suy ra từ ví dụ rằng mọi subscriber có cơ chế retry bền vững.
~~~

Nếu một nhánh có thể lỗi hoặc chậm, không nên để sự thành công của thao tác thanh toán phụ thuộc ngoài ý muốn vào việc gửi thông báo. Các lựa chọn cần cân nhắc:

1. Dispatch đồng bộ nhưng định nghĩa rõ cách xử lý lỗi từng subscriber.
2. Cấu hình executor để tách thread, kết hợp error handling riêng.
3. Ghi sự kiện bền qua outbox/broker khi mỗi nhánh phải nhận được event sau restart.

Nhiều subscriber trên **DirectChannel** là **cạnh tranh nhận một message**; nhiều subscriber trên **PublishSubscribeChannel** là **cùng nhận message**. Đây là khác biệt quyết định khi chọn channel.

## 9. Ordering: “đúng thứ tự” nghĩa là thứ tự nào?

Yêu cầu “giữ thứ tự” phải nói rõ **phạm vi**:

| Yêu cầu thứ tự | Ví dụ | Điều kiện thiết kế |
| --- | --- | --- |
| Theo một send() | Validate → Transform → Persist | Flow đồng bộ nối tiếp bằng DirectChannel |
| Theo một producer tuần tự | A gửi trước B | Không thay đổi thread hoặc chỗ queue/consumer làm đảo thứ tự |
| Theo khóa nghiệp vụ | Các event của cùng orderId phải theo trình tự | Partition/serialize theo orderId; tránh xử lý song song tùy tiện |
| Toàn cục | Tất cả message của mọi producer theo một tổng thứ tự | Cần một điểm xếp thứ tự chung và giới hạn concurrency; thường tốn thông lượng |
| Theo độ ưu tiên | Cảnh báo cao xử lý trước việc nền | PriorityChannel; không phải FIFO toàn cục |

**DirectChannel không bảo đảm thứ tự toàn cục**: hai thread producer có thể đồng thời gọi handler. Với **ExecutorChannel**, executor đa thread có thể đảo thứ tự bắt đầu/kết thúc. Với **QueueChannel**, queue có thể giữ một thứ tự lấy ra nhưng nhiều consumer xử lý đồng thời vẫn có thể **hoàn tất khác thứ tự**. Với **PublishSubscribeChannel**, mỗi nhánh có thể trải nghiệm thứ tự khác nhau nếu dùng các executor khác nhau.

Khi cần correlation trong Splitter/Aggregator, các header như **correlationId**, **sequenceNumber**, **sequenceSize** giúp nhóm message đúng. Chúng **không tự làm mọi consumer xử lý tuần tự** và không tạo một cam kết thứ tự toàn cục.

### Ví dụ: cùng một orderId phải tuần tự

Một hệ thống phát **order.created → order.paid → order.shipped**. Nếu ba message có thể đến ba worker độc lập, kết quả có thể đảo thứ tự khi xử lý. Có thể chia partition theo orderId, tiêu thụ tuần tự trong mỗi partition, kèm số phiên bản/số thứ tự và kiểm tra trạng thái hợp lệ. Lựa chọn message channel cục bộ là **một phần** trong thiết kế này, không thay thế hợp đồng giữa producer và consumer.

## 10. Delivery guarantee, durability và retry

Đây là phần dễ bị hiểu sai nhất khi chọn channel. Các khái niệm cần tách rời:

- **Accepted / dispatched:** message đã được channel chấp nhận hoặc chuyển đến dispatcher.
- **Handled:** handler đã chạy xong theo tiêu chí của handler.
- **Persisted:** message hoặc trạng thái nghiệp vụ đã được ghi vào một nơi có khả năng khôi phục.
- **Acknowledged:** hệ thống có một cam kết xác nhận cụ thể, ví dụ broker ack hay trạng thái commit.
- **Exactly-once effect:** cùng một tác động nghiệp vụ không được thực hiện trùng lặp, ngay cả khi việc giao message có thể lặp.

Không một channel in-memory nào **một mình** tạo ra exactly-once processing xuyên nhiều hệ thống. Một giao thức giao nhận có thể phát lại message sau crash, và một handler có thể hoàn thành side effect trước khi ghi nhận ack.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as Queue/Broker
    participant C as Consumer
    participant DB as Database
    P->>Q: Gửi event E
    Q->>C: Giao E
    C->>DB: Ghi tác động của E
    DB-->>C: Commit thành công
    Note over C,Q: Consumer crash trước ack
    Q->>C: Giao lại E
    C->>DB: Nếu không idempotent, có thể ghi lặp
~~~

Để thỏa yêu cầu nghiệp vụ:

| Mục tiêu | Cơ chế thường cần thêm |
| --- | --- |
| Không mất thông điệp khi tiến trình restart | MessageStore bền hoặc broker durable; ghi/commit đúng ranh giới |
| Tối đa hóa khả năng xử lý thành công | Retry có giới hạn, backoff, quan sát lỗi, xử lý poison message |
| Không thực hiện tác động nghiệp vụ trùng | Idempotency key, unique constraint, deduplication hoặc giao dịch phù hợp |
| Producer trả thành công sau khi sự kiện được lưu | Transactional outbox hoặc cơ chế commit/publish đáng tin |
| Không giữ message lỗi vô hạn | Dead-letter channel/queue hoặc khu vực cách ly có chính sách vận hành |

**Mối quan hệ với Spring Integration:** MessageStore, poller, advice, error channel, retry và gateway là những cơ chế có thể phối hợp với channel để tạo hợp đồng lớn hơn. Mỗi adapter có semantics riêng; không nên suy ra khả năng lưu bền hoặc ack từ tên một channel.

## 11. Error channel và ranh giới transaction

### Xử lý lỗi đồng bộ

Trong DirectChannel, exception từ handler có thể truyền về caller theo call stack. Nếu producer đang trong một transaction Spring và handler đồng bộ dùng cùng transaction manager, handler có thể cùng tham gia transaction đó. Nhưng việc một HTTP request hay email đã gửi ra bên ngoài **không** tự rollback theo database transaction.

### Xử lý lỗi bất đồng bộ

Sau khi chuyển qua ExecutorChannel hoặc poller của QueueChannel, lỗi thường xảy ra ở một thread/bước độc lập. Việc phát **ErrorMessage** đến một **errorChannel** tùy cấu hình endpoint, message header, error handler và loại inbound adapter/gateway. Cần kiểm tra đường lỗi thực tế thay vì giả định mọi exception sẽ tự quay về producer.

**Retry** cần xác định rõ “retry từ bước nào”. Retry toàn bộ flow có thể gửi email hai lần sau khi một bước ghi DB thành công nhưng bước sau thất bại. Áp dụng retry cục bộ, idempotent consumer và chính sách DLQ để giảm tác động ngoài ý muốn.

| Channel / ranh giới | Khi handler lỗi | Transaction của producer |
| --- | --- | --- |
| DirectChannel đồng bộ | Thường có thể lan về sender | Có thể tiếp tục trong cùng thread |
| ExecutorChannel | Handler lỗi về sau; phải có cơ chế async error handling | Không tự truyền sang worker thread |
| QueueChannel + poller | Lỗi xảy ra lúc poll/handle, tách khỏi send trước đó | Consumer có transaction riêng nếu cấu hình |
| PublishSubscribeChannel mặc định đồng bộ | Lỗi một subscriber có thể ảnh hưởng send và các nhánh khác; tùy cấu hình | Có thể cùng call stack cho các subscriber đồng bộ |
| PublishSubscribeChannel với Executor | Lỗi được xử lý ở phía async | Không tự chia sẻ transaction của publisher |

## 12. Backpressure, timeout và tài nguyên

Backpressure là cách hệ thống phản ứng khi producer nhanh hơn consumer. Những channel khác nhau tạo tín hiệu khác nhau:

| Lựa chọn | Dấu hiệu quá tải | Hướng xử lý |
| --- | --- | --- |
| DirectChannel | Caller bị chậm, thread request bị giữ lâu | Đo latency, tối ưu handler, đặt timeout thích hợp ở I/O |
| ExecutorChannel | Executor queue đầy hoặc từ chối task | Bounded queue, rejection policy rõ ràng, metrics |
| QueueChannel có capacity | send() chờ hoặc trả false/timeout khi queue đầy | Giới hạn chờ, từ chối có kiểm soát, throttle producer |
| QueueChannel không giới hạn phù hợp | Bộ nhớ tăng liên tục khi consumer chậm | Đặt giới hạn hoặc chuyển backlog đến hệ thống chuyên biệt |
| RendezvousChannel | Sender/receiver có thể chờ nhau | Timeout và cơ chế hủy khi phía kia không hoạt động |
| PublishSubscribeChannel đồng bộ | Một subscriber chậm giữ publisher | Tách nhánh chậm và đặt chính sách lỗi/timeout |

Đừng tăng số worker vô điều kiện. Khi bottleneck là DB, thêm thread có thể làm tăng contention. Giám sát queue depth, thời gian chờ, throughput, lỗi và thời gian xử lý theo endpoint để điều chỉnh phù hợp.

## 13. Kiểm thử semantics thay vì chỉ kiểm thử API

Các ví dụ sau dùng **JUnit 5** để xác nhận những hành vi cốt lõi của channel. Chúng có thể dùng làm nền cho bài test tích hợp trong dự án Spring Integration; tên package và dependency cần khớp với phiên bản sử dụng.

### 13.1. DirectChannel gọi handler trên thread sender

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.support.MessageBuilder;

class DirectSemanticsTest {
    @Test
    void directHandlerRunsOnTheSenderThread() {
        DirectChannel channel = new DirectChannel();
        AtomicReference<Thread> actualThread = new AtomicReference<>();
        channel.subscribe(message -> actualThread.set(Thread.currentThread()));

        Thread senderThread = Thread.currentThread();
        assertTrue(channel.send(MessageBuilder.withPayload("payload").build()));
        assertSame(senderThread, actualThread.get());
    }
}
~~~

Test này xác nhận **thread trong một lần gửi** khi handler đồng bộ, nhưng không kiểm chứng thứ tự toàn cục giữa nhiều producer.

### 13.2. PublishSubscribeChannel gửi đến tất cả subscriber

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.messaging.support.MessageBuilder;

class PublishSubscribeSemanticsTest {
    @Test
    void eventIsDeliveredToBothSubscribers() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        AtomicInteger audit = new AtomicInteger();
        AtomicInteger notification = new AtomicInteger();

        channel.subscribe(message -> audit.incrementAndGet());
        channel.subscribe(message -> notification.incrementAndGet());

        channel.send(MessageBuilder.withPayload("payment.completed").build());

        assertEquals(1, audit.get());
        assertEquals(1, notification.get());
    }
}
~~~

### 13.3. Bounded QueueChannel báo khi đầy

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class QueueSemanticsTest {
    @Test
    void boundedQueueProvidesAFullSignal() {
        QueueChannel channel = new QueueChannel(1);
        Message<String> a = MessageBuilder.withPayload("A").build();
        Message<String> b = MessageBuilder.withPayload("B").build();

        assertTrue(channel.send(a, 0));
        assertFalse(channel.send(b, 0));

        Message<?> received = channel.receive(0);
        assertNotNull(received);
        assertEquals("A", received.getPayload());
    }
}
~~~

### 13.4. ExecutorChannel phân phối qua executor

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.support.MessageBuilder;

class ExecutorSemanticsTest {
    @Test
    void handlerCanRunOnAWorkerThread() throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            ExecutorChannel channel = new ExecutorChannel(executor);
            CountDownLatch handled = new CountDownLatch(1);
            AtomicReference<Thread> worker = new AtomicReference<>();
            Thread sender = Thread.currentThread();

            channel.subscribe(message -> {
                worker.set(Thread.currentThread());
                handled.countDown();
            });

            assertTrue(channel.send(MessageBuilder
                    .withPayload("background-job").build()));
            assertTrue(handled.await(2, TimeUnit.SECONDS));
            assertNotSame(sender, worker.get());
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Với executor một thread do test tạo ra, kiểm tra được sự chuyển thread. Khi sử dụng executor thực tế, cần thêm test về queue đầy, rejection và shutdown; không chỉ dựa vào việc một lần gửi thành công.

## 14. Những lỗi thiết kế thường gặp

| Cách làm sai | Hệ quả | Cách sửa |
| --- | --- | --- |
| Đặt nhiều handler trên DirectChannel rồi kỳ vọng mọi handler chạy | Chỉ một subscriber được chọn trong mỗi dispatch | Dùng PublishSubscribeChannel hoặc nối chuỗi channel |
| Chọn ExecutorChannel vì nghĩ rằng “async = durable” | Message có thể mất khi tiến trình chết | Thêm persistent store, outbox hoặc broker |
| Xem QueueChannel là bảo đảm xử lý đúng một lần | Crash/retry có thể mất hoặc lặp tác động | Thiết kế commit, idempotency và ack |
| Giả định send() true nghĩa là consumer đã hoàn thành | Consumer có thể chưa chạy hoặc đã reject ở Filter | Tách accepted/handled/committed trong hợp đồng |
| Chạy nhiều consumer để tăng tốc nhưng vẫn đòi FIFO toàn cục | Thứ tự hoàn tất có thể đảo | Quy định scope ordering, partition hoặc serialize |
| Không giới hạn queue | Out-of-memory khi consumer chậm | Bounded queue và overload policy |
| Gắn errorChannel mà không xác minh endpoint async | Lỗi đi sai nơi hoặc bị bỏ sót | Test lỗi theo đúng điểm phát sinh |
| Retry toàn flow gồm side effect không idempotent | Tạo đơn, gửi email hoặc tính tiền trùng | Retry theo bước và deduplicate |
| Broadcast nội bộ được coi là event bus bền | Một nhánh lỗi/restart có thể bỏ lỡ event | Thiết kế delivery cho từng nhánh, dùng storage/broker khi cần |
| Đưa dữ liệu nhạy cảm vào header/log | Lộ thông tin xuyên các điểm quan sát | Giới hạn metadata và lọc thông tin log |

## 15. Bài thực hành chọn channel theo yêu cầu

Một hệ thống thương mại điện tử xử lý các sự kiện sau:

| Luồng | Yêu cầu | Lựa chọn khởi đầu |
| --- | --- | --- |
| Checkout validation | HTTP caller cần biết kết quả kiểm tra ngay | DirectChannel và flow đồng bộ |
| Tạo bản thumbnail | Tác vụ tương đối chậm; có thể xử lý nền, chưa yêu cầu sống qua restart | ExecutorChannel với bounded executor |
| Đơn hàng chờ hệ thống kho | Producer nhanh hơn consumer trong thời gian ngắn, cần theo dõi backlog | QueueChannel bounded và poller |
| Payment completed | Audit, notification và analytics đều cần nhận event | PublishSubscribeChannel; đánh giá độ bền từng nhánh |
| Cảnh báo an ninh | Công việc khẩn được ưu tiên khi tồn đọng | PriorityChannel với policy ngăn starvation |
| Giao tiếp hai worker phải hẹn nhau | Sender/receiver cùng sẵn sàng mới trao được message | RendezvousChannel với timeout |

**Bài tập chính**

1. Với mỗi luồng, ghi rõ **consumer cardinality, sync/async, buffering, ordering scope, durability, backpressure và error path**.
2. Tạo một IntegrationFlow gồm Filter, Transformer và Service Activator sử dụng DirectChannel; kiểm thử rằng Filter từ chối sẽ ngăn các bước còn lại.
3. Tách bước tạo thumbnail qua ExecutorChannel; mô phỏng handler ném exception và chứng minh caller không thể dựa vào try/catch quanh send() để thu mọi lỗi xảy ra sau đó.
4. Chuyển sang QueueChannel capacity=2; thử gửi ba message với timeout=0 và kiểm chứng tín hiệu khi đầy.
5. Tạo sự kiện payment.completed có correlationId để cả audit và analytics nhận, xác nhận fan-out bằng test.
6. Viết một phương án nâng cấp khi yêu cầu thay thành: “không mất payment.completed sau restart và không ghi audit trùng khi nhận lại”.

**Định hướng lời giải cho câu 6:** thêm nơi lưu bền và cơ chế phát sự kiện đáng tin (ví dụ transactional outbox/broker), một khóa idempotency ổn định, unique constraint hoặc bảng processed_event ở audit consumer, retry/backoff và tuyến xử lý message không thể xử lý. PublishSubscribeChannel đơn thuần chưa đạt yêu cầu này.

### Câu hỏi tự kiểm tra

1. Vì sao ExecutorChannel không đồng nghĩa một message đã được lưu bền?
2. Cần dùng DirectChannel hay PublishSubscribeChannel khi tất cả subscriber phải nhận sự kiện?
3. Send thành công trong QueueChannel chứng minh điều gì, và chưa chứng minh điều gì?
4. QueueChannel với một consumer có chắc giữ được thứ tự hoàn tất khi handler tự khởi tạo các task song song không?
5. Tại sao PriorityChannel có thể làm message ưu tiên thấp chờ lâu?
6. Những điểm nào cần kiểm thử sau khi đổi một ranh giới DirectChannel sang ExecutorChannel?
7. Vì sao một hệ thống có retry thường cần idempotent consumer?

## 16. Checklist trước khi chốt thiết kế channel

- **Cardinality:** xác nhận một consumer hay mọi subscriber đều phải nhận.
- **Completion:** định nghĩa rõ caller chờ tới đâu và trả success theo sự kiện nào.
- **Concurrency:** ghi rõ thread/executor, ranh giới async và giới hạn worker.
- **Ordering:** xác định thứ tự theo một send(), một khóa hay toàn hệ thống.
- **Buffering:** xác định capacity, poller, timeout và chiến lược khi đầy.
- **Durability:** kiểm chứng dữ liệu phải sống qua restart hay có thể mất.
- **Failure:** mô tả exception, retry, error channel, DLQ và quan sát lỗi.
- **Transaction:** xác định phạm vi commit và các side effect không thể rollback.
- **Idempotency:** chuẩn bị cho trường hợp duplicate delivery nếu có retry/redelivery.
- **Verification:** kiểm thử trên flow thực, gồm lỗi và quá tải, ngoài ví dụ happy path.

Một quyết định chọn channel tốt bắt đầu bằng **hợp đồng cần bảo đảm** rồi mới chọn implementation. Khi hiểu rõ consumer cardinality, đồng bộ/bất đồng bộ, thứ tự, độ bền và xử lý lỗi, các thành phần Router, Filter, Transformer, Splitter, Aggregator và Gateway sẽ kết nối với nhau theo cách có thể dự đoán, kiểm thử và vận hành.

## Tài liệu tham khảo

- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): phân loại channel và hành vi dispatch.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): cấu hình flow, channel và endpoint.
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): các lựa chọn lưu trữ message, kiểm soát độ bền.
- [Spring Integration API — DirectChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/DirectChannel.html): hợp đồng và các tùy chọn dispatch.
