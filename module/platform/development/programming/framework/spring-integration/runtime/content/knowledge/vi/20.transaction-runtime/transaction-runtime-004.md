# Commit khi handler và downstream thành công

Trong Spring Integration, một message có thể đi từ inbound adapter qua channel, consumer endpoint, handler rồi tiếp tục tới transformer, router, service activator, outbound gateway hoặc các consumer khác. Nhiều hệ thống mong muốn một cam kết rõ ràng: **chỉ commit dữ liệu khi handler hiện tại và tất cả bước downstream thuộc cùng đơn vị công việc đều thành công**.

Yêu cầu này không tự động có được chỉ vì một method được gắn <code>@Transactional</code>. Transaction của Spring được gắn với **thread và phạm vi lời gọi** đã mở transaction. Một bước downstream chạy sau khi method kết thúc, hoặc chạy trên executor/poller khác, có thể thất bại **sau khi** giao dịch ở handler đã commit.

Bài học thuộc chương **Transaction runtime** của module **SPRING_INTEGRATION_RUNTIME**. Ta sẽ xác định ranh giới transaction khi Spring Integration điều phối message flow qua channel, endpoint, consumer, poller và executor; sau đó thực hành cách cấu hình, kiểm chứng rollback/commit, xử lý retry, error channel, message store và correlation.

> **Nguyên tắc:** “Chỉ commit sau khi downstream thành công” chỉ có nghĩa khi **transaction bao trùm đoạn downstream cần bảo vệ**, exception còn được truyền về transaction interceptor và tài nguyên cần rollback thực sự tham gia transaction đó. Một transaction đơn lẻ không biến mọi API, broker và hệ thống ngoài thành thao tác nguyên tử.

## 1. “Handler thành công” không đồng nghĩa “Flow thành công”

Xét luồng đặt hàng:

~~~text
order.input
    → OrderService.save()
    → order.saved (DirectChannel)
    → AuditService.record()
    → reply
~~~

Ta muốn hai bản ghi <code>orders</code> và <code>order_audit</code> cùng thành công hoặc cùng rollback. Có ít nhất ba điểm cần tách biệt:

- **Handler thành công:** <code>OrderService.save()</code> đã trả về, nhưng audit có thể chưa được gọi.
- **Downstream thành công:** <code>AuditService.record()</code> đã hoàn tất bình thường, nhưng điều đó chưa chứng minh transaction đã commit thành công.
- **Commit thành công:** transaction manager đã hoàn tất commit với các tài nguyên transactional tham gia; vẫn có thể tồn tại side effect bên ngoài không được bảo vệ.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant TX as Transaction boundary
    participant H as Order handler
    participant D as Downstream audit
    participant DB as Transactional DB
    C->>TX: bắt đầu unit of work
    TX->>H: handle(order)
    H->>DB: INSERT orders
    H-->>TX: SavedOrder
    TX->>D: record audit
    D->>DB: INSERT order_audit
    D-->>TX: AuditReceipt
    TX->>DB: COMMIT
    TX-->>C: success
    Note over TX,DB: Commit chỉ diễn ra sau khi cả hai bước trả về thành công
~~~

Sơ đồ thể hiện một transaction được khởi tạo **bên ngoài cả hai bước** và toàn bộ lời gọi xử lý diễn ra đồng bộ trên cùng thread. Nếu audit ném exception trước commit, transaction interceptor có thể rollback cả hai thao tác database.

## 2. Quy tắc về transaction boundary trong message flow

Spring Integration chỉ chuyển message giữa các thành phần; nó **không tự mở một transaction rộng cho toàn bộ graph**. Chính transaction manager và điểm bắt đầu transaction quyết định phạm vi thực tế.

| Yếu tố | Tác động tới commit |
|---|---|
| <code>DirectChannel</code> | Consumer thường chạy trên thread của sender; transaction hiện tại có thể tiếp tục qua chuỗi đồng bộ |
| <code>PublishSubscribeChannel</code> **không có executor** | Subscriber được gọi đồng bộ; vẫn cần kiểm tra cách lỗi được lan truyền và xử lý |
| <code>ExecutorChannel</code> hoặc <code>PublishSubscribeChannel</code> có executor | Xử lý sau handoff chạy trên thread khác; transaction thread-bound của sender không được chuyển tự động |
| <code>QueueChannel</code> và polling consumer | Tạo ranh giới nhận/xử lý sau; transaction của sender không tự bao quanh consumer của poller |
| <code>@Transactional</code> tại handler | Thường chỉ bao quanh lời gọi method handler; downstream được dispatch sau khi method trả về có thể nằm ngoài phạm vi |
| <code>@Transactional</code> tại caller/gateway facade | Có thể bao quanh toàn bộ flow request–reply **đồng bộ**, khi mọi lời gọi downstream diễn ra trước khi facade trả về |
| Transaction advice của poller | Có thể mở transaction bao quanh một chu kỳ receive-and-handle và các downstream đồng bộ |
| <code>REQUIRES_NEW</code>, một transaction manager khác | Có thể tạo commit độc lập ngay cả khi đang có outer transaction |

<code>DirectChannel</code> **không tự khởi tạo transaction**. Nó chỉ giữ lời gọi cùng thread, tạo điều kiện cho transaction đã tồn tại được sử dụng tiếp. Ngược lại, <code>ExecutorChannel</code> có thể báo gửi thành công ngay khi task được chấp nhận, dù handler downstream chưa chạy hoặc sẽ thất bại sau đó.

### Hai cách đặt <code>@Transactional</code>, hai kết quả khác nhau

**Cách dễ gây lỗi:**

~~~java
@Service
public class OrderService {
    @Transactional
    public SavedOrder save(OrderCommand command) {
        // INSERT orders
        return new SavedOrder(command.orderId(), command.quantity());
    }
}

// Flow: .handle(orderService, "save").handle(auditService, "record")
~~~

Transaction của <code>save()</code> có thể **commit khi method kết thúc**, trước khi Spring Integration dispatch output cho <code>auditService.record()</code>. Nếu audit lỗi, bản ghi order đã commit không tự rollback theo lỗi đó.

**Cách phù hợp với mục tiêu của bài:** đặt transaction ở một entry point bên ngoài toàn bộ lời gọi message flow đồng bộ, chẳng hạn facade gọi messaging gateway. Hoặc, với polling consumer, cấu hình transaction advice ở poller để bao quanh receive và downstream đồng bộ. Hai cách được minh họa ở các phần tiếp theo.

## 3. Ví dụ đầy đủ: transaction bao quanh Gateway → Handler → Downstream

Ví dụ dùng Spring Integration Java DSL, Java 17+ và một database JDBC. Lệnh lưu đơn và ghi audit phải cùng giao dịch. Tất cả thành phần giả định nằm trong Spring context có Spring JDBC, Spring Transaction, Spring Integration và transaction manager quản lý cùng <code>DataSource</code>.

**Bước 1 — định nghĩa dữ liệu:**

~~~java
public record OrderCommand(String orderId, int quantity) {}
public record SavedOrder(String orderId, int quantity) {}
public record AuditReceipt(String orderId, String status) {}
~~~

Schema tối thiểu:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    quantity INTEGER NOT NULL
);

CREATE TABLE order_audit (
    order_id VARCHAR(64) PRIMARY KEY,
    event VARCHAR(40) NOT NULL
);
~~~

Ràng buộc khóa duy nhất giúp ngăn các lần ghi trùng khi upstream retry/redeliver. Cơ chế idempotency đầy đủ cần định nghĩa cách trả lại kết quả khi yêu cầu trùng khóa.

**Bước 2 — hai service dùng chung nguồn dữ liệu:**

~~~java
@Service
public class OrderService {
    private final JdbcTemplate jdbc;

    public OrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public SavedOrder save(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }
        jdbc.update("INSERT INTO orders(order_id, quantity) VALUES (?, ?)",
            command.orderId(), command.quantity());
        return new SavedOrder(command.orderId(), command.quantity());
    }
}

@Service
public class AuditService {
    private final JdbcTemplate jdbc;

    public AuditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public AuditReceipt record(SavedOrder order) {
        // Tạo một failure có chủ đích để kiểm tra rollback.
        if (order.orderId().equals("FAIL-AUDIT")) {
            throw new IllegalStateException("Audit không thành công");
        }
        jdbc.update(
            "INSERT INTO order_audit(order_id, event) VALUES (?, ?)",
            order.orderId(), "SAVED");
        return new AuditReceipt(order.orderId(), "RECORDED");
    }
}
~~~

Ở đây hai service chưa cần tự quản lý giao dịch. Các thao tác JDBC sẽ tham gia transaction đang được Spring bind vào thread khi facade bên ngoài mở giao dịch.

**Bước 3 — cấu hình các channel đồng bộ và IntegrationFlow:**

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class OrderFlowConfig {

    @Bean(name = "orders.input")
    MessageChannel inputChannel() {
        return new DirectChannel();
    }

    @Bean(name = "orders.saved")
    MessageChannel savedChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow ordersFlow(OrderService orders, AuditService audit) {
        return IntegrationFlow.from("orders.input")
            .handle(orders, "save")
            .channel("orders.saved")
            .handle(audit, "record")
            .get();
    }
}
~~~

Các import chính: <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.channel.DirectChannel</code>, <code>org.springframework.integration.config.EnableIntegration</code>, <code>org.springframework.integration.annotation.IntegrationComponentScan</code> và <code>org.springframework.messaging.MessageChannel</code>. Hai handler được dispatch đồng bộ trên thread đi vào <code>orders.input</code>; <code>orders.saved</code> cũng là <code>DirectChannel</code>.

**Bước 4 — messaging gateway và facade mở transaction phía ngoài flow:**

~~~java
@MessagingGateway(defaultRequestChannel = "orders.input")
public interface OrderGateway {
    AuditReceipt submit(OrderCommand command);
}

@Service
public class CheckoutFacade {
    private final OrderGateway gateway;

    public CheckoutFacade(OrderGateway gateway) {
        this.gateway = gateway;
    }

    @Transactional
    public AuditReceipt submit(OrderCommand command) {
        return gateway.submit(command);
    }
}
~~~

<code>@MessagingGateway</code> thuộc <code>org.springframework.integration.annotation</code>, <code>@Transactional</code> thuộc <code>org.springframework.transaction.annotation</code>. Ứng dụng phải gọi <code>CheckoutFacade.submit(...)</code> **qua Spring proxy**; lời gọi nội bộ <code>this.submit(...)</code> trong cùng bean không kích hoạt interceptor transaction trong chế độ proxy thông thường.

Khi gọi:

~~~java
AuditReceipt receipt =
    checkoutFacade.submit(new OrderCommand("O-204", 2));
// Sau khi submit() hoàn thành và commit thành công,
// orders và order_audit đều có bản ghi tương ứng.
~~~

Trình tự mong muốn:

1. Spring transaction interceptor mở transaction trước khi <code>CheckoutFacade.submit()</code> chạy.
2. Facade gọi gateway; gateway gửi message qua <code>orders.input</code> (đồng bộ).
3. <code>OrderService.save()</code> ghi bảng <code>orders</code>, trả <code>SavedOrder</code>.
4. Spring Integration gửi payload qua <code>orders.saved</code>; <code>AuditService.record()</code> ghi bảng <code>order_audit</code>.
5. Reply <code>AuditReceipt</code> quay về gateway, rồi facade trả về.
6. Chỉ lúc đó transaction interceptor của facade mới thực hiện commit.

Với <code>new OrderCommand("FAIL-AUDIT", 2)</code>, audit ném <code>IllegalStateException</code> (runtime exception). Exception truyền ngược theo các <code>DirectChannel</code>, quay tới facade transaction interceptor, nên **cả INSERT vào <code>orders</code> cũng được rollback**. Điều này giả định transaction manager đúng, không có advice nào nuốt exception, và không có bước <code>REQUIRES_NEW</code> hoặc nguồn dữ liệu thứ hai tự commit riêng.

### Giới hạn quan trọng của ví dụ

Giao dịch chỉ bao phủ những thao tác tham gia cùng transaction manager. Nếu <code>AuditService</code> đồng thời gửi email hoặc gọi HTTP API, database rollback **không thu hồi** email đã gửi hoặc yêu cầu HTTP đã hoàn thành. Nếu audit ghi sang một database khác dùng transaction manager độc lập, cam kết “cả hai cùng commit” cũng không còn tự động đúng.

## 4. Sơ đồ commit và rollback

### Trường hợp A — cả handler và downstream đều thành công

~~~mermaid
flowchart LR
    A["BEGIN TX"] --> B["Handler: ghi orders"]
    B --> C["DirectChannel"]
    C --> D["Downstream: ghi audit"]
    D --> E["Trả reply"]
    E --> F["COMMIT DB"]
    F --> G["Caller nhận kết quả"]
~~~

### Trường hợp B — downstream ném exception

~~~mermaid
flowchart LR
    A["BEGIN TX"] --> B["Handler: ghi orders"]
    B --> C["DirectChannel"]
    C --> D["Downstream: audit lỗi"]
    D -. "exception truyền ngược" .-> E["Transaction interceptor"]
    E --> F["ROLLBACK DB"]
    F --> G["Caller nhận exception"]
~~~

Trong cả hai sơ đồ, commit/rollback nằm **sau khi đoạn đồng bộ trong transaction kết thúc**. Nếu handler tự mở transaction riêng và commit trước khi output message được dispatch, sơ đồ thứ hai sẽ không còn đúng.

## 5. Với poller: transaction cần bao quanh receive và xử lý

Không phải flow nào cũng bắt đầu từ một synchronous gateway. Một polling consumer có thể lấy message từ <code>QueueChannel</code>, JDBC-backed message store, JMS hoặc nguồn dữ liệu polling khác. Poller có thể được gắn transaction advice để mở transaction trước <code>receive()</code> và chỉ hoàn tất sau khi chuỗi xử lý đồng bộ kết thúc.

Ví dụ XML cấu hình poller theo cơ chế Spring Integration:

~~~xml
<int:service-activator input-channel="orders.queue"
                       ref="orderProcessor"
                       method="process">
    <int:poller fixed-delay="1000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int:service-activator>
~~~

<code>orderProcessor.process(...)</code> có thể gửi tiếp qua một hoặc nhiều <code>DirectChannel</code>. Khi poller transaction bao quanh chu kỳ receive-and-process, các bước downstream đồng bộ có thể nằm trong cùng transaction cho đến khi poll task kết thúc. Cấu hình XML trên minh họa **transaction của polling endpoint**; cần bổ sung bean <code>orders.queue</code>, <code>orderProcessor</code> và <code>transactionManager</code> phù hợp với ứng dụng.

Tuy nhiên, kết quả rollback của **thao tác receive** phụ thuộc loại nguồn:

| Message source/channel | Rollback có thể làm gì? |
|---|---|
| <code>JdbcChannelMessageStore</code> qua transactional queue/channel, dùng cùng transaction manager | Thao tác lấy/xóa message có thể rollback cùng thay đổi DB theo cấu hình thực tế |
| JDBC polling adapter dùng cùng database transaction | Có thể rollback công việc đọc/đánh dấu trạng thái khi nguồn và thao tác tham gia cùng transaction |
| JMS channel hoặc inbound adapter | Redelivery/ACK phụ thuộc session, transaction mode và cấu hình container/broker |
| <code>QueueChannel</code> in-memory thông thường | Không tự trở thành hàng đợi bền vững hay transactional chỉ vì poller có <code>@Transactional</code> |
| File/FTP hoặc API ngoài | Không có rollback database thực sự cho thao tác trên file/server ngoài; cần transaction synchronization hoặc cơ chế bù riêng |

**Sai lầm phổ biến:** thấy rollback các bản ghi JDBC rồi kết luận message chắc chắn quay lại hàng đợi. Cần kiểm tra transaction của chính message source, cách message được remove/ack và khả năng replay sau crash.

### Transaction synchronization cho nguồn không đồng nhất

Spring Integration hỗ trợ <code>TransactionSynchronizationFactory</code> với các callback như <code>beforeCommit</code>, <code>afterCommit</code>, <code>afterRollback</code>. Ví dụ, sau khi xử lý file thành công và commit database, có thể chuyển file sang thư mục “processed” tại <code>afterCommit</code>; nếu rollback, chuyển sang thư mục “failed” khi thích hợp.

Điều quan trọng là:

- <code>beforeCommit</code> chạy trước commit; một lỗi được phát hiện và truyền ra ở giai đoạn này có thể khiến transaction rollback.
- <code>afterCommit</code> chạy khi transaction **đã commit**; thao tác sau đó thất bại không thể rollback giao dịch đã hoàn tất.
- <code>afterRollback</code> giúp kích hoạt hành động xử lý sau rollback; callback không tự làm nguồn ngoài trở thành tài nguyên transactional.

Nếu yêu cầu nghiêm ngặt “downstream phải xong rồi mới commit”, một downstream chạy **ở <code>afterCommit</code>** không đáp ứng điều kiện ấy. Nó là **tác vụ sau commit**, thích hợp cho thông báo hoặc công việc có thể retry độc lập, không phải phần bắt buộc của một commit nguyên tử.

## 6. Vượt qua ranh giới bất đồng bộ: thành công khi handoff có thể dẫn đến commit sớm

Giả sử flow đổi <code>orders.saved</code> từ <code>DirectChannel</code> sang <code>ExecutorChannel</code>:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant T as Transaction (thread A)
    participant H as Handler (thread A)
    participant X as ExecutorChannel
    participant D as Downstream (thread B)
    C->>T: begin
    T->>H: save()
    H-->>T: saved
    T->>X: gửi message
    X-->>T: task accepted
    T->>T: COMMIT DB của thread A
    X->>D: xử lý ở thread B
    D--xX: exception
    Note over T,D: Exception ở thread B không rollback được commit ở thread A
~~~

Sơ đồ mô tả một nguồn kích hoạt không cần chờ kết quả downstream và việc giao task thành công. Với **request–reply gateway**, caller cũng có thể đợi reply rồi timeout nếu downstream chậm; việc chờ reply **không chuyển transaction của caller sang worker thread**. Tùy timeout, wrapper/exception, transaction của caller có thể commit hoặc rollback, nhưng **không tạo ra atomicity xuyên thread**.

| Ranh giới | Vì sao commit không chờ tất cả downstream? | Cách thiết kế đáng cân nhắc |
|---|---|---|
| <code>ExecutorChannel</code> | Chuyển xử lý sang thread khác | Mở transaction mới ở consumer; dùng outbox/inbox hoặc bản tin bền vững cho workflow nhiều bước |
| <code>QueueChannel</code> + poller | Message nằm ở queue và được xử lý ở một chu kỳ khác | Transaction riêng cho poller; queue có transactional message store nếu cần |
| Broker (Kafka/JMS/AMQP) | Publish/ACK và xử lý consumer có protocol, thời điểm commit riêng | Theo transaction hỗ trợ của từng adapter; idempotency, outbox, DLQ, redelivery |
| <code>@Async</code> hoặc thread tự tạo | Không truyền tự động thread-bound transaction | Hợp đồng bất đồng bộ rõ ràng, transaction riêng ở worker |
| Reactor/flow reactive | Context và transaction semantics khác thread-bound imperative transaction | Dùng hỗ trợ reactive transaction phù hợp; không dựa vào giả định cùng thread |

**Không nên giữ một database transaction mở để chờ một loạt tác vụ bất đồng bộ kéo dài.** Thiết kế tốt hơn thường gồm một transaction ngắn để lưu trạng thái nghiệp vụ cùng outbox, sau đó worker xử lý các bước kế tiếp với retry và idempotency có kiểm soát.

## 7. Downstream gặp lỗi nhưng flow vẫn commit: các nguyên nhân thường gặp

| Triệu chứng | Vì sao có thể commit? | Kiểm tra/sửa |
|---|---|---|
| Handler ghi DB rồi audit lỗi, order vẫn còn | <code>@Transactional</code> chỉ bao quanh method của handler | Đưa transaction lên caller hoặc poller nếu flow đồng bộ |
| Audit lỗi nhưng caller nhận success | Advice/handler bắt exception rồi chỉ log hoặc trả giá trị thay thế | Chỉ recover khi có hợp đồng rõ; nếu yêu cầu rollback thì để exception lan ra |
| Handler kết thúc, downstream async lỗi sau đó | Transaction đã hoàn tất tại handoff thread | Dùng workflow nhiều transaction, outbox và compensating action khi cần |
| Exception là checked exception | Default <code>@Transactional</code> thường rollback với <code>RuntimeException</code>/<code>Error</code>, không tự rollback mọi checked exception | Dùng <code>rollbackFor</code> khi hợp đồng yêu cầu, hoặc chuyển exception phù hợp |
| Downstream dùng <code>REQUIRES_NEW</code> | Transaction độc lập có thể commit riêng | Rà soát propagation; xác định resource nào phải atomic |
| Hai thao tác qua transaction manager khác nhau | Chỉ một resource được transaction quản lý | Thiết kế ranh giới rõ; tránh suy luận về distributed atomicity |
| ErrorMessage được publish thành công | Error flow chỉ quan sát/công bố lỗi sau khi có exception | Phân biệt notification với rollback; xác định lỗi có còn lan tới transaction owner không |
| Audit đã gửi HTTP nhưng JDBC rollback | HTTP không tự tham gia JDBC transaction | Dùng outbox, idempotency phía nhận hoặc saga/bù nghiệp vụ |

Một tình huống dễ bỏ sót: handler ném exception sau khi đã ghi DB, nhưng advice retry thử lại rồi **nuốt exception cuối cùng**. Lớp ngoài chỉ thấy lời gọi hoàn thành, nên có thể commit. Cần thiết kế recovery theo nghĩa “thành công”, “thất bại cần rollback” và “đã chuyển sang hàng đợi xử lý lại” một cách tường minh.

## 8. Retry kết hợp transaction: commit ở lần nào?

Retry và transaction có thể được xếp theo hai thứ tự:

**A. Retry bao ngoài transaction riêng của mỗi attempt**

~~~text
Retry
  ├─ attempt #1: BEGIN → handler + downstream → lỗi → ROLLBACK
  ├─ attempt #2: BEGIN → handler + downstream → lỗi → ROLLBACK
  └─ attempt #3: BEGIN → handler + downstream → thành công → COMMIT
~~~

Đây là cách thường phù hợp khi cần retry một *đơn vị công việc* và mỗi lần thử phải bắt đầu với trạng thái transaction mới. Điều kiện là transaction advice thực sự được gọi mỗi attempt, hoặc service dùng propagation phù hợp, và không có transaction bên ngoài giữ tất cả attempts trong cùng một transaction.

**B. Transaction bao ngoài nhiều attempt**

~~~text
BEGIN TRANSACTION
  Retry
    attempt #1 → exception
    attempt #2 → exception
    attempt #3 → success
COMMIT? (có thể thất bại nếu transaction đã rollback-only)
~~~

Một lần thử trước có thể đánh dấu transaction rollback-only. Dù lần cuối handler trả về thành công, commit ngoài cùng vẫn có thể thất bại, ví dụ <code>UnexpectedRollbackException</code>. Vì vậy, phải xác định retry xảy ra **trong hay ngoài** transaction interceptor và lỗi nào đã đánh dấu rollback.

Retry cũng có thể tạo side effect trùng lặp nếu attempt trước gửi email, thanh toán hoặc publish event rồi mới ném exception. Idempotency key nghiệp vụ, unique constraint, inbox/outbox và giới hạn attempt/backoff là những thành phần đi kèm cần thiết.

## 9. Error channel và correlation không quyết định commit

Khi exception xảy ra ở consumer đồng bộ, nó có thể đi ngược về sender và transaction interceptor; ở consumer bất đồng bộ/poller, nó có thể được chuyển thành <code>ErrorMessage</code> trên error channel tương ứng. Tuy nhiên:

- <code>MessagePublishingErrorHandler</code> có nhiệm vụ phát lỗi khi được runtime sử dụng; **không tự thực hiện rollback cho một transaction đã kết thúc**.
- Header <code>errorChannel</code> xác định nơi nhận <code>ErrorMessage</code> trong các đường xử lý lỗi phù hợp; nó không phải lệnh “rollback”.
- <code>correlationId</code> giúp nối các bước processing, retry và lỗi qua thread; nó không đại diện cho transaction ID và không bảo đảm hai bước dùng chung transaction.
- <code>MessageHeaders.ID</code> là định danh một message; khi message được tạo lại hoặc redeliver, ID có thể khác. Không dùng riêng ID này để chống duplicate side effect.
- Với poller, error handler thường chạy ở ranh giới sau khi task ném exception; cần xem transaction đã rollback và message source sẽ redeliver hay chưa.

Ở môi trường production, nên log/trace tối thiểu <code>correlationId</code>, order ID hoặc idempotency key, tên endpoint, tên thread, transaction status khi cần chẩn đoán, loại exception và số lần retry. Không ghi toàn bộ payload nhạy cảm vào log.

## 10. Kiểm thử đúng câu “chỉ commit khi tất cả thành công”

Unit test mock service không chứng minh được database rollback. Với mục tiêu này, nên dùng **integration test với database và transaction manager thực**, ví dụ H2 hoặc Testcontainers, chạy flow Spring Integration và truy vấn dữ liệu sau khi transaction kết thúc.

| Kịch bản | Kỳ vọng ở DB | Điều xác minh thêm |
|---|---|---|
| Order + audit thành công | Có cả <code>orders</code> và <code>order_audit</code> | Gateway trả receipt sau commit thành công |
| Handler <code>save()</code> thất bại | Không có bản ghi mới ở cả hai bảng | Audit không được gọi |
| Handler thành công, audit ném runtime exception | **Không có** bản ghi mới ở cả hai bảng | Exception truyền về facade, transaction rollback |
| Audit ném checked exception (nếu ứng dụng cho phép) | Theo quy tắc rollback đã cấu hình | Kiểm tra <code>rollbackFor</code> nếu yêu cầu rollback |
| Audit bắt exception và trả success | Có thể commit | Test này chứng minh nguy cơ nuốt lỗi |
| Flow có <code>ExecutorChannel</code> | Giao dịch handler và worker tách biệt | Không kỳ vọng một rollback bao trùm cả hai |
| Poller + transactional message store | DB rollback và trạng thái message nhất quán theo cấu hình | Kiểm chứng nhận lại message sau lần lỗi |
| Retry rồi thành công | Không có dữ liệu trùng lặp | Unique key, số attempt, transaction cho từng attempt |

**Phác thảo integration test** (giả sử đã có <code>JdbcTemplate jdbc</code>, <code>CheckoutFacade checkoutFacade</code> và dữ liệu test được dọn trước mỗi case):

~~~java
@Test
void commitOnlyWhenDownstreamSucceeds() {
    AuditReceipt result =
        checkoutFacade.submit(new OrderCommand("O-OK", 2));

    assertEquals("RECORDED", result.status());
    assertEquals(1, jdbc.queryForObject(
        "SELECT COUNT(*) FROM orders WHERE order_id = ?",
        Integer.class, "O-OK"));
    assertEquals(1, jdbc.queryForObject(
        "SELECT COUNT(*) FROM order_audit WHERE order_id = ?",
        Integer.class, "O-OK"));
}

@Test
void rollbackWhenDownstreamFails() {
    assertThrows(RuntimeException.class, () ->
        checkoutFacade.submit(new OrderCommand("FAIL-AUDIT", 2)));

    assertEquals(0, jdbc.queryForObject(
        "SELECT COUNT(*) FROM orders WHERE order_id = ?",
        Integer.class, "FAIL-AUDIT"));
    assertEquals(0, jdbc.queryForObject(
        "SELECT COUNT(*) FROM order_audit WHERE order_id = ?",
        Integer.class, "FAIL-AUDIT"));
}
~~~

Các assertion thuộc JUnit 5. **Không nên đặt <code>@Transactional</code> trên chính test** nếu mục tiêu là kiểm tra transaction do facade commit/rollback độc lập: transaction bao ngoài của test có thể làm sai kết quả quan sát. Thử nghiệm phải xác nhận trạng thái database sau khi <code>checkoutFacade.submit(...)</code> kết thúc.

### Kiểm tra transaction active tại từng điểm

Trong lúc chẩn đoán, có thể tạm thêm:

~~~java
boolean active = TransactionSynchronizationManager
    .isActualTransactionActive();
log.debug("component={}, thread={}, txActive={}",
    "audit", Thread.currentThread().getName(), active);
~~~

<code>TransactionSynchronizationManager</code> thuộc <code>org.springframework.transaction.support</code>. Kết quả <code>txActive=true</code> cho biết thread đang có transaction theo Spring, **không** chứng minh tất cả resource cùng tham gia transaction đó. Kết hợp log thread ID, transaction manager, datasource và integration test rollback mới kết luận được phạm vi thực.

## 11. Checklist trước khi áp dụng

1. Xác định chính xác bước downstream nào **bắt buộc** phải thành công trước commit; tách các công việc sau commit như gửi email, notification hoặc indexing.
2. Đặt transaction ở entry point bao trùm **toàn bộ** đoạn đồng bộ cần atomic (gateway facade hoặc poller transaction), không mặc định đặt trên một handler là đủ.
3. Kiểm tra loại channel giữa các bước: <code>DirectChannel</code> giữ cùng thread; <code>QueueChannel</code>, executor hoặc async adapter tạo boundary mới.
4. Xác nhận các thao tác dữ liệu tham gia cùng transaction manager, cùng resource/connection theo cấu hình và không commit độc lập bằng <code>REQUIRES_NEW</code>.
5. Đảm bảo exception từ downstream được lan đến transaction interceptor; quy định rõ checked exception, rollback-only và các advice có recovery.
6. Với message source, xác định rollback làm gì với ACK, remove, visibility, message store và redelivery; thử nghiệm khi worker chết hoặc restart.
7. Xác định chiến lược retry và idempotency, đặc biệt nếu downstream có side effect ngoài database.
8. Kiểm thử cả nhánh thành công, handler lỗi, downstream lỗi, async boundary và sự cố ngay trước/sau commit.
9. Quan sát correlation, thread, endpoint, transaction lifecycle, retry và queue depth, nhưng giới hạn dữ liệu nhạy cảm trong logs.

**Kết luận:** Commit chỉ nên được hiểu là thành công của **một transaction xác định**, không phải thành công của mọi bước trong cả distributed message flow. Nếu handler và downstream chạy đồng bộ trong cùng transaction, một exception downstream có thể khiến tất cả thay đổi transactional rollback. Khi flow đổi sang poller, executor, broker hoặc hệ thống ngoài, phải thiết kế ranh giới commit mới cùng message store, retry, idempotency hoặc outbox để đạt cam kết nghiệp vụ mong muốn.

## Tài liệu tham khảo

- [Spring Integration — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration — Message Endpoints và poller transactions](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
