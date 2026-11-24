# Rollback khi handler downstream thất bại trong Spring Integration Adapters

## 1. Bài toán: handler trước thành công, handler sau ném exception

Trong module **SPRING_INTEGRATION_ADAPTERS**, Spring Integration kết nối các hệ thống ngoài bằng **inbound/outbound adapter**, **gateway**, **poller** và **MessageChannel**. Một message có thể đi qua nhiều transformer, filter, service activator, JDBC handler, HTTP outbound gateway hoặc broker adapter. Khi handler phía sau (*downstream*) thất bại, câu hỏi đầu tiên không phải là “đã có ErrorMessage chưa?” mà là:

**Những thao tác nào nằm trong cùng một transaction chưa commit, và exception có thực sự đi ngược qua ranh giới transaction đó không?**

Ví dụ, một file CSV chứa đơn hàng được nhận rồi xử lý:

~~~text
File inbound poller
    -> validate
    -> JDBC handler: INSERT orders
    -> HTTP outbound gateway: create shipment
    -> downstream handler: publish confirmation
~~~

Giả sử handler cuối ném exception. Có ít nhất bốn khả năng:

| Tình huống | Có thể rollback cái gì? | Điều không được suy ra |
|---|---|---|
| JDBC INSERT và handler lỗi nằm trong **một transaction DB chưa commit** | INSERT có thể rollback | Không có nghĩa file đã được đặt lại trạng thái |
| JDBC INSERT đã commit **trước** handler lỗi | Giao dịch đó không còn rollback bằng exception mới | Không thể “undo” bằng cách chỉ throw exception |
| HTTP create shipment đã được phía ngoài chấp nhận | Không thể rollback HTTP bằng transaction DB | Cần idempotency, tra cứu hoặc compensation |
| Downstream chạy qua ExecutorChannel/async callback | Exception có thể nằm ở thread khác, ngoài transaction của sender | Không thể giả định lỗi sẽ lan về poller/gateway ban đầu |

**Rollback** là cơ chế hoàn tác các thay đổi *chưa commit* trong phạm vi một transaction manager quản lý. Nó khác với **retry** (thử lại thao tác), **compensation** (tạo hành động nghiệp vụ bù cho side effect đã xảy ra), và **reconciliation** (đối soát khi kết quả chưa rõ).

### Mục tiêu học tập

Sau bài, người học có thể:

1. Xác định transaction boundary, điểm commit và nơi exception phải được propagate để kích hoạt rollback.
2. Phân biệt đường xử lý **DirectChannel đồng bộ**, **QueueChannel/poller** và **ExecutorChannel/bất đồng bộ**.
3. Dùng **@Transactional**, **transactional poller/advice** và transaction manager cho phạm vi thích hợp.
4. Giải thích vì sao **errorChannel/ErrorMessage** không đồng nghĩa với rollback, cũng không đồng nghĩa không rollback.
5. Phân biệt local JDBC transaction với semantics của File, SFTP, HTTP, JMS, AMQP và Kafka.
6. Thiết kế retry, acknowledgment, idempotency, inbox/outbox, compensation và trạng thái kết quả chưa xác định.
7. Kiểm thử failure injection tại từng vị trí trước/sau commit, trước/sau ack và ở các ranh giới thread.

## 2. Những khái niệm nền tảng cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Transaction boundary | Phạm vi mà transaction manager điều phối | Một transaction JDBC bao nhiều câu SQL |
| Commit | Chấp nhận thay đổi của transaction | DB ghi order + outbox cùng nhau |
| Rollback | Hủy thay đổi chưa commit thuộc transaction đó | INSERT không xuất hiện sau exception |
| Propagation | Cách lời gọi tham gia/khởi tạo transaction | REQUIRED, REQUIRES_NEW trong Spring |
| Exception propagation | Ngoại lệ lan ngược tới phía kiểm soát transaction | DirectChannel handler throw về caller |
| Error publishing | Biến Throwable thành ErrorMessage gửi channel lỗi | Poller error handler publish lỗi |
| Retry | Chạy lại một thao tác theo policy | Retry kết nối DB với backoff |
| Acknowledgment | Nguồn/broker ghi nhận message được tiếp nhận/xử lý | JMS ack, AMQP ack, Kafka offset |
| Compensation | Một tác vụ mới xử lý side effect đã hoàn tất | Cancel shipment, release reservation |
| Idempotency | Lặp lại cùng yêu cầu không gây tác động nghiệp vụ thêm | Một orderId chỉ tạo một shipment |

Điều quan trọng: **transaction của cơ sở dữ liệu**, **transaction/ack của message broker** và **vòng đời kết nối** có thể là những cơ chế riêng. Cùng nằm trong một IntegrationFlow không biến chúng thành một global transaction.

### 2.1. Transaction manager quản lý tài nguyên nào?

Một **DataSourceTransactionManager/JdbcTransactionManager** điều phối JDBC connections của DataSource phù hợp. Một **JmsTransactionManager** quản lý transaction của JMS Session tương ứng. Các hệ thống ngoài như SFTP filesystem, HTTP server hoặc Kafka producer không tự động tham gia local JDBC transaction.

Muốn phối hợp atomicity giữa nhiều tài nguyên đôi khi có thể dùng XA/JTA khi tất cả tài nguyên và hạ tầng hỗ trợ đúng, nhưng đổi lại là độ phức tạp và rủi ro vận hành. **Không xem XA là giải pháp mặc định cho HTTP/SFTP/Kafka**; dùng outbox/inbox hoặc saga khi phù hợp.

### 2.2. “Handler downstream” là vị trí tương đối

Trong flow:

~~~text
M0 -> transformer T -> handler H1 -> channel C -> handler H2
~~~

H2 là downstream của H1. Nếu H1 và H2 được gọi đồng bộ trong cùng thread, exception từ H2 **có thể** quay về H1/caller. Nếu C là boundary async, H1 có thể hoàn tất trước khi H2 bắt đầu; transaction tại H1 có thể đã commit.

### 2.3. Transaction không bắt đầu chỉ vì có MessageChannel

DirectChannel là một cơ chế dispatch đồng bộ, **không tự tạo database transaction**. QueueChannel cũng không mặc nhiên gắn message với transaction database. Một transaction cần được mở bởi @Transactional proxy, TransactionTemplate, transaction advice trên polling endpoint hoặc cơ chế tương ứng do ứng dụng cấu hình.

## 3. Bốn câu hỏi quyết định rollback

Khi nhận báo cáo “handler cuối thất bại nhưng DB vẫn có dữ liệu”, hãy đi theo thứ tự:

1. **Transaction có thật sự được mở không?** Kiểm tra @Transactional có được Spring AOP proxy áp dụng, có đúng manager và thread không.
2. **Thao tác DB có thực sự tham gia transaction ấy không?** Kiểm tra DataSource/EntityManager, propagation và transaction manager.
3. **Handler downstream có chạy trước khi transaction commit không?** Phân biệt DirectChannel và async, job queue, remote side effects.
4. **Exception có được quy tắc rollback nhận diện và lan ra đúng ranh giới không?** Có bị catch, recovery callback, error handler hoặc exception translation thay đổi không?

Nếu một câu trả lời là “không”, rollback kết quả đó **không được bảo đảm**. Nếu cả bốn là “có”, kiểm thử vẫn cần xác minh DB state và tác động ngoài.

### 3.1. Những điểm dễ tưởng tượng nhầm

- **Đã log exception** không có nghĩa transaction đã rollback.
- **Đã publish ErrorMessage** không chứng minh transaction commit hay rollback.
- **Đã @Transactional trên một method** không chứng minh lời gọi đi qua proxy.
- **Cùng một flow** không chứng minh cùng một thread hoặc transaction.
- **Message được redeliver** không có nghĩa mọi side effect trước đó đã bị hoàn tác.
- **HTTP timeout** không khẳng định server đích chưa tạo đơn hàng.

## 4. DirectChannel đồng bộ: trường hợp dễ đạt rollback nhất

### 4.1. Call stack và transaction

Giả sử một service có @Transactional gửi Message tới DirectChannel, H1 ghi JDBC, H2 ném RuntimeException, và toàn bộ hoạt động diễn ra đồng bộ trên thread của caller:

~~~mermaid
sequenceDiagram
    participant Caller as Transactional service
    participant TX as JDBC TransactionManager
    participant D as DirectChannel
    participant H1 as H1 - JDBC INSERT
    participant H2 as H2 - downstream
    Caller->>TX: begin transaction
    Caller->>D: send message
    D->>H1: handle
    H1->>TX: INSERT order (chưa commit)
    H1->>H2: dispatch tiếp trên thread đồng bộ
    H2--xH1: RuntimeException
    H1--xD: propagate exception
    D--xCaller: propagate exception
    Caller->>TX: rollback
    TX-->>Caller: INSERT không được commit
~~~

Sơ đồ giả định exception không bị nuốt, H1 thực sự tham gia transaction và không có thao tác ngoài DB đã commit. H2 là “handler downstream” theo thứ tự xử lý, không nhất thiết gọi trực tiếp H1 bằng code Java: Spring Integration có thể dùng các endpoint nối qua DirectChannel.

### 4.2. Vì sao DirectChannel giúp giữ boundary?

DirectChannel chuyển lời gọi tới subscriber đồng bộ. Handler cuối có thể ném exception trong **cùng call stack**; exception quay lại sender trước khi method @Transactional kết thúc. Transaction interceptor nhìn thấy lỗi và quyết định rollback theo rules.

Điều này khác với:

~~~text
Transactional sender
   -> ExecutorChannel.send(M)
      -> returns after dispatch/acceptance
   -> transaction commits

Executor thread (later)
   -> downstream handler fails
   -> exception cannot travel backward in time
      to undo transaction already committed
~~~

### 4.3. Ranh giới ở cuối method chứ không ở tên channel

Ngay cả DirectChannel cũng không giúp rollback nếu:

- Caller không có transaction;
- H1 tạo **REQUIRES_NEW** và commit trước lỗi H2;
- H1 dùng một DataSource không được manager hiện tại quản lý;
- H1 đã gọi HTTP bên ngoài, không nằm trong DB transaction;
- Exception được bắt và xử lý như thành công trong scope transaction;
- Flow chuyển thread sau H1 và lỗi chỉ xuất hiện sau khi caller return.

## 5. Mẫu Java: @Transactional bao đường gửi DirectChannel

### 5.1. Giả định dự án

Ứng dụng dùng Spring Boot/Spring Integration, Spring JDBC, DataSource và transaction manager cho cùng database. Một bảng kiểm thử:

~~~sql
CREATE TABLE integration_orders (
    order_id VARCHAR(80) PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);
~~~

### 5.2. Flow hai handler nối đồng bộ

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.MessageChannel;

record OrderCommand(String orderId) {}

@Configuration
@EnableIntegration
class OrderRollbackFlowConfiguration {

    @Bean
    MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderRollbackFlow(JdbcTemplate jdbcTemplate) {
        return IntegrationFlow.from("ordersInput")
                .handle((payload, headers) -> {
                    OrderCommand command = (OrderCommand) payload;
                    jdbcTemplate.update(
                            "INSERT INTO integration_orders(order_id, status) " +
                            "VALUES (?, ?)",
                            command.orderId(), "RECEIVED");
                    return command; // Forward tới handler tiếp theo.
                })
                .handle((payload, headers) -> {
                    throw new IllegalStateException(
                            "Simulated downstream failure");
                })
                .get();
    }
}
~~~

Trong Java DSL, handler đầu phải **trả Message hoặc payload** để chain có thể chuyển tiếp tới handler sau. Một one-way MessageHandler chỉ xử lý input và không gửi reply có thể kết thúc flow tại chỗ. Ví dụ dùng GenericHandler có trả payload để biểu diễn đường đi đồng bộ.

### 5.3. Transaction entrypoint

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderSubmissionService {

    private final MessageChannel ordersInput;

    OrderSubmissionService(MessageChannel ordersInput) {
        this.ordersInput = ordersInput;
    }

    @Transactional
    public void submit(OrderCommand command) {
        boolean accepted = ordersInput.send(
                MessageBuilder.withPayload(command).build());
        if (!accepted) {
            throw new IllegalStateException("Message was not accepted");
        }
    }
}
~~~

Spring transaction interceptor mở transaction khi phương thức công khai này được gọi **qua Spring-managed proxy**. JDBC handler sử dụng JdbcTemplate/DataSource phù hợp; H2 ném RuntimeException trước khi submit trả về, khiến DB rollback theo default rollback rules.

### 5.4. Điều kiện để ví dụ hoạt động đúng

- Phải có DataSource/transaction manager thực sự; @Transactional không tạo “transaction phép màu”.
- OrderSubmissionService được lấy từ Spring context và gọi từ bean khác, không self-invoke bypass proxy.
- Channel là DirectChannel và không có asynchronous boundary giữa các handler.
- Handler JDBC dùng **cùng DataSource được transaction manager quản lý**.
- Không có logic catch rồi return bình thường cho exception.
- Bảng dữ liệu được tạo trước khi test; ví dụ ở đây chỉ minh họa logic.
- Nếu có nhiều beans MessageChannel, inject bằng qualifier để tránh nhầm channel.

### 5.5. Ngoại lệ được bọc

Spring Integration có thể bọc một Throwable trong MessagingException/MessageHandlingException. Điều quan trọng là transaction interceptor nhìn thấy **exception thuộc rollback rule**. RuntimeException thường kích hoạt rollback mặc định; checked exception thì cần xét cấu hình. Không nên phụ thuộc tuyệt đối vào loại wrapper khi business logic có exception translation.

## 6. Poller transactional: rollback khi lỗi trong polling task

### 6.1. Transaction boundary của poller

File/SFTP/JDBC inbound adapter và polling consumer có thể được cấu hình để scheduler kích hoạt một transaction quanh **đoạn công việc thuộc poll task**. Spring Integration Java DSL cung cấp PollerSpec và khả năng gắn transaction advice/transaction manager theo API phiên bản.

~~~mermaid
flowchart TD
    S["Scheduler tick"] --> TX["Begin transaction advice"]
    TX --> POLL["Poll MessageSource / PollableChannel"]
    POLL --> H1["H1: JDBC insert/update"]
    H1 --> H2["H2: downstream synchronous handler"]
    H2 --> D{"Throw exception?"}
    D -->|"No"| COMMIT["Commit transaction"]
    D -->|"Yes, propagated"| ROLLBACK["Rollback transaction"]
    ROLLBACK --> ERR["Error handling/reporting, theo cấu hình"]
~~~

Sơ đồ trình bày ý tưởng: **thứ tự advice, cấu hình error handler và ranh giới thread** quyết định exception được rollback trước hay sau publish lỗi. Không mặc định mọi exception đều đến global errorChannel.

### 6.2. Java DSL cấu hình poller có transaction

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.Message;
import org.springframework.integration.core.MessageSource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class TransactionalPollingFlow {

    @Bean
    IntegrationFlow transactionalImport(
            MessageSource<?> source,
            JdbcTemplate jdbc,
            PlatformTransactionManager dbTransactionManager) {

        return IntegrationFlow.from(
                        source,
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(2))
                                        .maxMessagesPerPoll(1)
                                        .transactional(dbTransactionManager)))
                .handle((payload, headers) -> {
                    jdbc.update(
                            "INSERT INTO integration_orders(order_id, status) " +
                            "VALUES (?, ?)",
                            String.valueOf(payload), "IMPORTED");
                    return payload;
                })
                .handle((payload, headers) -> {
                    throw new IllegalStateException(
                            "Downstream validation failed");
                })
                .get();
    }
}
~~~

Đây là **mẫu cấu hình**, cần source bean tương thích và dữ liệu payload phù hợp; không phải một ứng dụng độc lập có thể chạy ngay. Với production, không dùng String.valueOf(payload) làm business key nếu MessageSource trả File hoặc object phức tạp. Cần lưu business key thật và bảo đảm idempotency.

**Ý chính:** transaction advice trên poller có thể bao JDBC handler đồng bộ trong cùng task. Nhưng **không tự rollback File/SFTP state hoặc QueueChannel in-memory** chỉ vì SQL đã rollback.

### 6.3. Khi error handler nằm ngoài transaction advice

Nếu exception từ poller đi qua một transaction interceptor và interceptor rollback **trước khi** error publisher bắt Throwable, ErrorMessage có thể được publish *sau khi DB rollback đã xảy ra*. Điều đó là hợp lệ.

Ngược lại, nếu một error handler hoặc recovery callback **bắt exception trong phần còn đang chịu trách nhiệm transaction** và return như success, transaction có thể commit nếu không bị đánh dấu rollback-only. Không thể kết luận chỉ từ việc nhìn thấy ErrorMessage. Cần biết thứ tự interceptor, handler và actual transaction state.

### 6.4. Điều khiển dữ liệu nguồn

Với JDBC polling source, transaction có thể hỗ trợ query/claim/update row phù hợp. Với File/SFTP, filesystem và SSH server không tự tham gia JDBC transaction. Với QueueChannel, semantics của receive khác nhau tùy in-memory hay persistent MessageStore. **Rollback DB không đồng nghĩa message tự trở lại source**.

## 7. Ranh giới bất đồng bộ: nơi rollback thường bị hiểu sai

### 7.1. ExecutorChannel thay đổi thread và thời điểm thất bại

Một flow có thể chạy H1 đồng bộ rồi bàn giao tiếp qua ExecutorChannel:

~~~mermaid
sequenceDiagram
    participant C as Caller + JDBC transaction
    participant H1 as H1 - DB write
    participant E as ExecutorChannel
    participant W as Worker thread
    participant H2 as H2 - downstream
    C->>H1: Insert order
    H1->>E: Send message
    E-->>H1: Accepted for asynchronous dispatch
    H1-->>C: Return
    C->>C: Commit JDBC transaction
    E->>W: Execute later
    W->>H2: Handle
    H2--xW: Exception
    Note over W: Exception không rollback được commit của C
~~~

Khi executor thread nhận message, nó **không mặc định thừa hưởng ThreadLocal transaction context** của caller. Transaction ở caller thường đã kết thúc; một exception xảy ra trong worker chỉ ảnh hưởng transaction riêng nếu worker có một transaction được cấu hình.

**Cảnh báo:** ExecutorChannel có thể bị cấu hình với rejection policy khiến task thực thi ngay trong caller thread hoặc fail tại lúc dispatch. Khi đó behavior có thể khác; không thiết kế transaction dựa trên giả định cố định mà không kiểm tra executor/rejection behavior.

### 7.2. Các ranh giới tương tự

| Ranh giới | Điều thay đổi | Cách bảo đảm nhất quán |
|---|---|---|
| QueueChannel | Message được lưu/chờ receive khác thời điểm | Durable queue/inbox, consumer transaction |
| ExecutorChannel | Thread xử lý khác | Transaction riêng ở worker, idempotent command |
| PublishSubscribeChannel với executor | Subscriber có thể chạy đồng thời | Không dựa vào global order hoặc một transaction chung |
| Reactive/Flux pipeline | Publisher và subscriber có scheduler khác | Transaction model tương ứng và explicit completion |
| HTTP async request/callback | Remote xử lý ngoài call stack | Request ID, idempotency, reconciliation |
| Kafka producer callback | Acknowledgment xuất hiện sau lời gọi | Outbox, retry/producer error strategy |
| JMS/AMQP listener | Broker/container quản lý message lifecycle | Transaction/ack, inbox/dedupe |

### 7.3. Không kéo dài transaction JDBC qua network call nếu không cần

Giữ transaction DB mở trong khi HTTP chờ nhiều giây có thể giữ connection/lock, tăng contention, pool exhaustion và nguy cơ deadlock. Nếu remote call là bước quan trọng, thường an toàn hơn khi:

1. Commit local state và **outbox command** trong cùng DB transaction;
2. Worker đọc outbox và gọi remote API;
3. Ghi kết quả có idempotency;
4. Retry hoặc compensate theo quy tắc nghiệp vụ.

Đây không phải bảo đảm atomic giữa DB và HTTP; đó là mô hình **eventual consistency có trạng thái phục hồi**.

### 7.4. Cơ chế rollback không “lan” qua message envelope

Spring Message có payload và headers; nó không tự mang một distributed transaction context có thể commit/rollback trên mọi hệ thống. Cố gắng truyền một transaction ID trong header **không làm HTTP/SFTP downstream tham gia transaction**.

## 8. Exception propagation, rollback rules và propagation behavior

### 8.1. Quy tắc rollback mặc định

Với @Transactional của Spring, cấu hình mặc định phổ biến rollback khi **RuntimeException hoặc Error** thoát ra khỏi method và không tự rollback đối với checked exception nếu không cấu hình thêm. Vì vậy cần xác định exception thật mà transaction interceptor nhìn thấy.

~~~java
import java.io.IOException;
import org.springframework.transaction.annotation.Transactional;

class OrderProcessingService {

    @Transactional
    public void processWithUncheckedFailure() {
        writeDatabase();
        throw new IllegalStateException("Downstream failure");
        // RuntimeException: rollback theo default rules.
    }

    @Transactional(rollbackFor = IOException.class)
    public void processWithCheckedFailure() throws IOException {
        writeDatabase();
        throw new IOException("External dependency failed");
        // Checked exception: rollback do rollbackFor được chỉ định.
    }

    private void writeDatabase() {
        // Cần triển khai dùng đúng transaction-managed DataSource.
    }
}
~~~

Đoạn code minh họa rollback rules, không phải một integration flow chạy độc lập; service phải được Spring quản lý/proxy và writeDatabase() thực sự thao tác trên resource thuộc transaction manager.

### 8.2. Bắt exception nhưng không ném lại

~~~java
@Transactional
public void process() {
    repository.insertOrder(...);
    try {
        downstreamCall();
    } catch (RuntimeException failure) {
        logger.warn("Failed: {}", failure.getClass().getSimpleName());
        // Không rethrow và không mark rollback-only.
    }
}
~~~

Nếu không có trạng thái rollback-only được thiết lập bởi thành phần khác, interceptor có thể coi method hoàn tất thành công và commit. **Logging failure không phải tín hiệu rollback**.

Nếu exception được bắt để chuyển thành business result, hãy quyết định rõ:

- Có cần rollback toàn bộ DB transaction không?
- Có cần đánh dấu transaction rollback-only không?
- Có thể return một outcome nghiệp vụ và commit một phần hợp lệ không?
- Có cần tạo recovery task trong transaction riêng không?

Không tùy tiện gọi setRollbackOnly chỉ để “bắt lỗi”: nó có thể dẫn đến UnexpectedRollbackException ở outer method nếu caller nghĩ rằng sẽ commit. Nên đưa policy rollback vào thiết kế transaction và báo cho caller biết kết quả.

### 8.3. REQUIRES_NEW không rollback theo outer transaction

Giả sử:

~~~text
Outer transaction T1
   -> H1 calls auditService in REQUIRES_NEW transaction T2
      -> T2 commits audit record
   -> H2 throws
   -> T1 rolls back
~~~

Record audit đã commit ở T2 **không tự bị rollback** khi T1 rollback, vì T2 độc lập. Điều đó có thể là chủ ý (ghi audit ngay cả khi nghiệp vụ thất bại), nhưng không được nhầm với một transaction toàn cục.

### 8.4. Self-invocation bypass Spring AOP proxy

Nếu bean gọi một method @Transactional khác **trong chính instance** qua this.process(), lời gọi có thể không đi qua Spring proxy; transaction mong muốn không được mở. Cách khắc phục thường là tách transactional entrypoint sang một Spring bean khác hoặc dùng TransactionTemplate/AspectJ theo kiến trúc được hỗ trợ.

### 8.5. Nested transaction/savepoint

Propagation NESTED (nếu transaction manager/tài nguyên hỗ trợ) có thể tạo savepoint trong transaction ngoài. Điều đó giúp rollback một phần DB changes theo ranh giới hỗ trợ, **không hoàn tác HTTP hay message đã publish**. Không mặc định NESTED giống REQUIRES_NEW.

### 8.6. @TransactionalEventListener và callback sau commit

Một listener hoặc callback được cấu hình chạy **after commit** có thể ném exception sau khi DB đã commit. Lúc đó không thể rollback transaction đã kết thúc. Nên dùng outbox nếu cần bảo đảm durable processing hoặc retry sau commit.

## 9. ErrorMessage, errorChannel và rollback: quan hệ đúng

### 9.1. ErrorMessage là báo lỗi, không phải lệnh rollback

Spring Integration có **ErrorMessage** mang Throwable payload. Một polling task, executor hoặc endpoint có error publisher phù hợp có thể gửi ErrorMessage tới kênh lỗi. Tuy nhiên, điều này không tự động điều khiển transaction manager.

| Vị trí lỗi | Exception đi đâu? | Rollback phụ thuộc vào |
|---|---|---|
| DirectChannel đồng bộ | Thường ném về sender/caller | Transaction bao sender và rollback rules |
| Polling endpoint | Error handler có thể publish ErrorMessage | Thứ tự poller transaction advice và error handling |
| ExecutorChannel | Error strategy của worker/executor | Transaction của worker và error handling |
| HTTP inbound gateway | Có thể được ánh xạ thành error response/error flow | Transaction scope của endpoint/caller |
| JMS/AMQP listener | Container/error handler có thể nhận exception | Ack/transacted session và propagation |
| Kafka listener | Container error handler/recovery tùy config | Offset/transaction/ack policy |

**Không có ErrorMessage không chứng minh không rollback**: exception đồng bộ có thể đã kích hoạt rollback rồi được ném cho caller. **Có ErrorMessage không chứng minh rollback đã xảy ra**: error publisher có thể đang thông báo một lỗi ngoài transaction hoặc sau commit.

### 9.2. Exception bị “nuốt” ở đâu?

Một callback recovery có thể:

1. Bắt Throwable từ H2;
2. Gửi ErrorMessage hoặc lưu lỗi;
3. Return mà không rethrow.

Nếu callback chạy **trong transaction boundary** và transaction chưa bị đánh dấu rollback, outer logic có thể commit. Nhưng nếu transaction interceptor đã xử lý exception và rollback **trước** callback bên ngoài bắt lỗi, việc publish ErrorMessage không làm transaction commit lại. Cần xem **thứ tự advice và nơi catch**.

### 9.3. Quy tắc quan sát

Không đo rollback bằng số ErrorMessage. Hãy dùng:

- Log transaction begin/commit/rollback ở môi trường kiểm thử phù hợp;
- Trạng thái DB thực sau khi method/poller kết thúc;
- Broker acknowledgment/offset và source state;
- Business key và event ID để đối soát;
- Failure category, stage, correlation, retry attempt để tra sự cố.

### 9.4. Logging không được làm lộ business payload

ErrorMessage payload có thể là MessagingException với failedMessage chứa HTTP headers, file contents, token hoặc PII. Error subscriber cần lọc dữ liệu; không log toàn bộ Message.toString() một cách mặc định trong production.

### 9.5. Header errorChannel không bắt exception

MessageHeaders.ERROR_CHANNEL chỉ định một destination cho error publisher có hỗ trợ header đó. Chỉ gắn header vào input Message **không tự tạo transaction, rollback, bắt exception hoặc retry**. Cần cấu hình đúng poller/gateway/async error handler và kiểm thử hướng lỗi.

## 10. JDBC transaction: những thao tác nào thực sự quay lại?

### 10.1. Nhiều JDBC handler cùng một transaction

Nếu H1 insert order và H2 cập nhật inventory cùng **DataSource/transaction manager**, chạy đồng bộ và xảy ra RuntimeException trước commit, cả hai SQL changes có thể rollback.

~~~text
BEGIN
    INSERT order-274
    UPDATE inventory reserved += 1
    H3: validate shipment policy -> throws
ROLLBACK

SELECT order-274 -> không tồn tại
SELECT inventory -> giữ giá trị trước transaction
~~~

Ngược lại, nếu H1 tự commit hoặc dùng transaction REQUIRES_NEW, order record có thể vẫn tồn tại sau outer rollback.

### 10.2. Đảm bảo datasource đúng

Một flow có thể kết nối database A và database B bằng hai DataSources. Transaction manager của database A **không tự quản lý** connection ở database B. Khi H2 ném exception, có thể A rollback còn B đã commit.

Phải phân biệt local transaction và distributed consistency. Nếu không dùng XA/JTA có hỗ trợ, cân nhắc outbox/saga và trạng thái đối soát.

### 10.3. TransactionTemplate cho biên giới rõ ràng

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;

class OrderDatabaseUnit {
    private final TransactionTemplate tx;
    private final JdbcTemplate jdbc;

    OrderDatabaseUnit(TransactionTemplate tx, JdbcTemplate jdbc) {
        this.tx = tx;
        this.jdbc = jdbc;
    }

    void saveOrderAndOutbox(String orderId) {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                    "INSERT INTO integration_orders(order_id, status) VALUES (?, ?)",
                    orderId, "PENDING");
            jdbc.update(
                    "INSERT INTO integration_outbox(event_id, order_id) VALUES (?, ?)",
                    "event-" + orderId, orderId);
        });
    }
}
~~~

Đoạn code giả định bảng outbox có schema phù hợp, hai JDBC operations dùng cùng transaction-managed DataSource và có unique constraints để chống trùng. **Chỉ atomic đối với DB**; việc gửi event lên Kafka/AMQP sau đó do worker đảm nhiệm.

### 10.4. Transaction kết thúc ở đâu?

Nếu method @Transactional gọi gateway, và gateway chỉ gửi task async rồi trả về, transaction có thể commit **trước** khi downstream task chạy. Nếu method gọi DirectChannel và handler cuối ném exception trong cùng stack, transaction interceptor còn cơ hội rollback.

### 10.5. Isolation level và race

Rollback đúng không thay thế isolation/concurrency control. Hai workers có thể cùng đọc inventory rồi cập nhật sai nếu logic read-modify-write không khóa/atomic/versioned. Kiểm thử rollback phải thêm các ca concurrency, unique constraint, optimistic locking và deadlock.

## 11. File/SFTP: transaction DB không quay ngược thao tác tệp

### 11.1. File inbound poller

FileReadingMessageSource có thể tìm File và kết hợp filters (ví dụ accept-once/persistent metadata). Sau khi file đã được chọn, H1 ghi DB, H2 lỗi và DB rollback. **Filter có thể đã đánh dấu file được nhận**; file có thể không tự xuất hiện ở lượt poll kế tiếp.

~~~text
File invoice-274.csv selected
    -> filter state says accepted
    -> JDBC INSERT within transaction
    -> downstream handler throws
    -> JDBC ROLLBACK
    -> file state remains as defined by filter/move policy
~~~

Nếu không có durable file state/replay strategy, ứng dụng có thể ghi nhận lỗi mà không xử lý lại được file. Ngược lại, reset filter tùy tiện có thể tạo duplicate khi DB thực sự đã commit trong một trường hợp khác.

### 11.2. SFTP remote side effect

SFTP có thể tải file, đổi tên remote file, xóa remote file hoặc upload file trước khi handler phía sau thất bại. **SSH/SFTP server không tự tham gia transaction JDBC**. Để phục hồi:

- Ghi rõ remote path/identity/version và local file reference;
- Không chuyển file thành “processed” trước khi dữ liệu có bằng chứng commit phù hợp;
- Có quarantine/retry/compensation nếu file bị move/delete;
- Đối soát trạng thái remote khi transfer timeout;
- Dùng business key và idempotency để tránh xử lý lại cùng record.

### 11.3. Transaction synchronization không phải file rollback thực sự

Spring Integration hỗ trợ cơ chế **transaction synchronization** trên polling endpoint để thực hiện callbacks theo completion status. Một số thiết kế dùng **PseudoTransactionManager** để có synchronization callbacks cho resource không hỗ trợ transaction; nó **không cung cấp rollback thật cho filesystem**.

Ví dụ logic:

~~~text
On transaction commit:
    move local file to processed/ (theo policy)

On transaction rollback:
    move file to retry/ hoặc failed/ (theo policy)

Những file operations này là callback có thể thất bại riêng.
Không coi chúng atomic với database transaction.
~~~

Nếu ứng dụng gọi một remote SFTP API trong afterCommit callback rồi nó thất bại, DB đã commit; phải có durable recovery reference hoặc outbox thay vì suy rằng callback failure sẽ rollback DB.

### 11.4. Khi file chứa nhiều record

Xác định đơn vị transaction: một record, một file hay một batch. Nếu commit từng record, handler downstream lỗi ở record thứ 40 **không rollback 39 record đã commit trước**. Cần checkpoint, idempotent upsert, quarantine record và logic replay phần còn lại.

### 11.5. Điều cần kiểm thử

| Injection point | Trạng thái phải kiểm tra |
|---|---|
| Lỗi trước khi File Message được tạo | Chưa có failedMessage; filter/source không mất file |
| Lỗi sau receive trước JDBC commit | DB rollback; file có thể được replay/quarantine |
| Lỗi sau remote rename | DB rollback không tự đảo remote rename |
| Lỗi trong transaction synchronization callback | Có alert/recovery cho callback lỗi |
| Crash sau commit trước archive | Replay không tạo duplicate side effect |
| Hai pollers cùng file | Claim/metadata store ngăn xử lý trùng theo policy |

## 12. HTTP outbound gateway: JDBC rollback không hủy API call

### 12.1. Hai trường hợp phải tách

Giả sử H1 ghi JDBC và H2 gọi HTTP POST CreateShipment.

**Trường hợp A — HTTP thất bại rõ ràng trước khi phía đích xử lý:** H2 ném exception trong transaction đồng bộ; JDBC có thể rollback. Nhưng muốn retry an toàn vẫn cần phân loại lỗi và bảo vệ các side effect khác.

**Trường hợp B — HTTP đã thành công tại phía đích, nhưng caller nhận timeout:** H2 ném exception, JDBC có thể rollback; shipment ở đối tác **vẫn có thể tồn tại**. Khi retry H1/H2 không có idempotency, hệ thống có nguy cơ tạo shipment thứ hai.

~~~mermaid
sequenceDiagram
    participant TX as Local DB transaction
    participant H as HTTP outbound gateway
    participant P as Partner API
    TX->>TX: INSERT pending order
    TX->>H: CreateShipment(orderId)
    H->>P: POST /shipments (requestId=R274)
    P->>P: Commit shipment S274
    Note over P,H: Response lost / network timeout
    H--xTX: Timeout exception
    TX->>TX: ROLLBACK order insert
    Note over TX,P: Local rollback không xóa shipment S274
~~~

### 12.2. HTTP status và exception phụ thuộc client

Không mặc định mọi 4xx/5xx sẽ ném MessageHandlingException. Tùy HTTP client, error handler và Spring Integration gateway configuration, status có thể được chuyển thành exception hoặc reply. Test rollback cần cố tình làm handler **ném exception phù hợp**, và kiểm tra business outcome trên server giả.

### 12.3. Idempotency và trạng thái unknown

Đối với endpoint tạo tài nguyên:

- Dùng một **request ID/idempotency key ổn định** theo ý định nghiệp vụ nếu API hỗ trợ.
- Lưu correlation và target ID thật khi nhận kết quả.
- Với timeout mà kết quả chưa biết, đánh dấu RESULT_UNKNOWN và **tra cứu đối tác** trước khi thử lại.
- Nếu đã tạo resource nhưng nghiệp vụ phải hủy, dùng **compensation** như CancelShipment; không gọi đó là rollback JDBC.
- Có retry budget và backoff; đừng nhân retry ở client, handler advice, poller và worker không kiểm soát.

### 12.4. HTTP inbound gateway và exception response

Một HTTP inbound gateway đồng bộ có thể nhận exception từ downstream DirectChannel và ánh xạ thành response 4xx/5xx theo contract. Nhưng HTTP status trả lỗi **không chứng minh DB rollback**: transaction có thể đã commit trước khi response được tạo hoặc dữ liệu nằm ngoài transaction.

Nếu API xử lý bất đồng bộ và trả 202 Accepted, lỗi về sau cần tra cứu trạng thái/callback/event; không thể “trả một HTTP 500” trên request đã kết thúc.

### 12.5. Best practice về transaction scope

Tránh giữ JDBC transaction dài xuyên nhiều remote HTTP calls. Nếu external action phải được thực hiện đáng tin, lưu intent vào outbox, commit DB, rồi worker gọi HTTP theo idempotent protocol; chấp nhận eventual consistency với theo dõi trạng thái rõ ràng.

## 13. JMS: transaction listener, acknowledgment và downstream failure

### 13.1. JMS message-driven inbound khác polling consumer

JMS inbound adapter/gateway thường có listener container quản lý việc nhận message; lỗi handler có thể propagate tới container. Khi container dùng **transacted JMS Session** hoặc transaction được cấu hình, rollback của phiên nhận có thể khiến broker **redeliver** message. Hành vi cụ thể phụ thuộc provider, container, acknowledgment/transaction mode và exception handling.

Không gắn nhãn “Spring Integration transaction” lên JMS message rồi mặc định nó cùng atomic với JDBC. Một local JMS transaction và một local DB transaction là hai tài nguyên riêng nếu không có cơ chế điều phối được hỗ trợ.

### 13.2. Hai transaction cùng tồn tại

~~~mermaid
flowchart TD
    BROKER["JMS broker: order-274"] --> LISTENER["JMS listener"]
    LISTENER --> H1["JDBC write (DB TX)"]
    H1 --> H2["Downstream handler"]
    H2 --> DEC{"Exception propagated?"}
    DEC -->|"Yes"| DBRB["DB TX rollback nếu còn mở"]
    DEC -->|"Yes"| JMSRB["JMS session rollback nếu container transacted và policy yêu cầu"]
    DEC -->|"No, handled"| MAY["Container có thể coi xử lý thành công"]
    JMSRB --> REDELIVERY["Broker redelivery theo provider policy"]
    DBRB --> VERIFY["Kiểm tra DB và side effects"]
~~~

**Điểm mấu chốt:** cần kiểm tra **cả DB transaction và JMS delivery state**. Nếu dùng resource-manager-specific hoặc XA/JTA transaction, thiết kế có thể khác; không coi sơ đồ trên là một transaction hai pha mặc định.

### 13.3. Khi error handler swallow exception

Giả sử JDBC ghi order thất bại. Handler bắt lỗi, gửi ErrorMessage, rồi trả về mà không propagate. Với cấu hình container coi lời gọi hoàn tất là thành công, JMS message **có thể được acknowledge/commit** và không được giao lại, trong khi DB chưa có order.

Nếu mục tiêu là redelivery từ broker, cần policy rõ về **throw/rollback**. Nếu mục tiêu là **ack source sau khi ghi recovery task bền vững**, phải xác minh recovery task đã lưu an toàn rồi mới ack; không chỉ có một ErrorMessage trong bộ nhớ.

### 13.4. Bài test cần có

| Tình huống | Kiểm tra |
|---|---|
| Handler ném exception trước DB commit | DB rollback, broker redelivery đúng policy |
| Handler ném exception sau một transaction DB riêng đã commit | Redelivery không làm ghi trùng DB |
| Error handler bắt lỗi không rethrow | Kiểm tra ack/rollback thực tế; không suy đoán |
| Retry vượt ngưỡng | DLQ/redelivery policy và sự tồn tại của bản ghi nghiệp vụ |
| Broker failover trong transaction | Không mất message ngoài hợp đồng |
| Listener restart sau credential rotation | In-flight message được phục hồi, idempotency hoạt động |

### 13.5. Thứ tự và poison message

JMS rollback/redelivery có thể ảnh hưởng ordering và throughput, nhất là nhiều consumers. Một poison message không nên được redeliver vô hạn; nhưng đưa nó vào DLQ cũng có thể tạo **gap nghiệp vụ**. Cần quyết định điều gì xảy ra với những message sau cùng business key.

## 14. AMQP/RabbitMQ: ack, nack, requeue và DB rollback

### 14.1. AMQP listener container kiểm soát delivery

AMQP inbound adapter thường dựa trên Spring AMQP listener container. Nếu handler downstream ném exception, container và configured advice/error handler quyết định message bị ack, nack, reject, requeue hay dead-letter. Điều này **không tự đồng bộ với transaction JDBC**.

Ví dụ:

~~~text
RabbitMQ queue: OrderCreated(E274)
    -> Listener receives
    -> JDBC inserts order, commits
    -> HTTP handler fails
    -> Rabbit listener requeues message
    -> Redelivery inserts order again -> duplicate key / duplicate effect
~~~

Giải pháp không chỉ là chỉnh requeue: phải xác định **idempotent consumer**, transaction boundary và xử lý external side effects.

### 14.2. AMQP transaction không đồng nhất với JDBC transaction

RabbitMQ channel transaction/publisher confirms/consumer acknowledgment có cơ chế riêng. Nếu backend DB commit và broker ack diễn ra theo hai bước, crash ở giữa có thể sinh duplicate delivery. Không thể khẳng định exactly-once business processing chỉ bằng việc bật AMQP transaction.

### 14.3. Error channel không thay cho broker DLQ

Một Spring ErrorMessage gửi tới errorChannel không tự khiến RabbitMQ route original delivery vào DLQ. DLX/DLQ, nack/requeue và poison handling phải được cấu hình ở broker/container; cần kiểm tra redelivery metadata và final disposition.

### 14.4. Khi nào giữ DB transaction ngắn?

Nếu handler phải gửi message AMQP outbound sau JDBC update, dùng **transactional outbox** khi cần bảo đảm phát thông điệp sau commit. Nếu message có thể gửi thành công rồi DB rollback, downstream đã thấy event nhưng DB không có dữ liệu tương ứng; outbox tránh được kiểu inconsistency này khi triển khai đúng.

### 14.5. Test quan trọng

- DB rollback nhưng consumer không ack/được redeliver theo policy;
- DB commit rồi process crash trước ack;
- Nack/requeue làm message có thể nhận lại nhiều lần;
- Broker exchange/queue permissions và network fail trước/sau publish;
- Pub/sub downstream tạo side effect rồi thất bại;
- Outbox publisher crash sau broker accept nhưng trước mark-sent;
- DLQ có record cần reconciliation, không tự coi là đã giải quyết.

## 15. Kafka: transaction, offset và handler downstream bất đồng bộ

### 15.1. Kafka listener không tự tham gia JDBC transaction

Spring Integration Kafka adapter sử dụng Spring for Apache Kafka container/producer. Kafka có transaction hỗ trợ các thao tác Kafka producer và offset trong mô hình được hỗ trợ, nhưng **Kafka transaction không mặc định bao DB hoặc HTTP**.

Một downstream handler thất bại có thể:

- Được ném lên listener container, kích hoạt error handler/retry;
- Được recover/DLT theo policy và có quyết định commit offset riêng;
- Xảy ra sau khi flow đã tách qua ExecutorChannel, khi listener có thể đã hoàn tất;
- Xảy ra sau DB commit hoặc HTTP call, lúc đó rollback Kafka không hoàn tác tác động bên ngoài.

### 15.2. Offset commit là trạng thái khác DB state

~~~text
Kafka partition P0 offset 100
    -> listener receives
    -> DB INSERT order-274 commits
    -> application crashes before offset commit
    -> consumer restarts
    -> offset 100 may be redelivered
~~~

Nếu không idempotent, đơn có thể được ghi hai lần. Ngược lại, nếu offset được commit trước khi work async được lưu an toàn, handler lỗi về sau có thể dẫn tới **message mất ở mức nghiệp vụ**.

### 15.3. Kafka transaction rollback không xóa record đã consumer khác thấy

Kafka transaction có isolation/read_committed semantics cho transactional records trong điều kiện phù hợp. Nhưng một HTTP request đã gửi hay JDBC transaction đã commit **không được Kafka transaction rollback**. Cần tách rõ Kafka-only atomicity và end-to-end business processing.

### 15.4. Producer callback lỗi sau transaction DB

Nếu JDBC H1 commit rồi Kafka outbound producer gửi bất đồng bộ, callback sau đó báo lỗi. Exception không thể đi ngược thời gian vào JDBC transaction đã commit. Nên thiết kế outbox và worker publisher có retry, final disposition, tracing và idempotent consumers.

### 15.5. Error handler/DLT không phải rollback SQL

Spring for Apache Kafka có các container error handlers (ví dụ DefaultErrorHandler theo phiên bản). DLT là đường cách ly record đã xử lý lỗi theo policy; **đưa record vào DLT không tự rollback DB trước đó**. Phải test fault injection tại commit và offset boundary.

### 15.6. Partition ordering

Kafka lưu record theo thứ tự offset trong từng partition, không global order giữa partitions. Nếu một listener chuyển record sang executor bất đồng bộ hoặc retry record riêng, commit order nghiệp vụ có thể khác offset order. Kiểm thử **per-key version, retry gaps và late callbacks** bên cạnh transaction rollback.

## 16. Retry advice: có thể làm transaction khác đi

### 16.1. Retry trước khi rollback hay rollback rồi retry?

Hai cấu hình về mặt logic:

~~~text
Option A:
Retry advice
    -> Transaction advice
        -> Handler
    Each attempt opens/rolls back its own TX if configured that way.

Option B:
Transaction advice
    -> Retry advice
        -> Handler
    Multiple attempts may execute within a TX scope.
~~~

**Thứ tự advice/interceptor có ý nghĩa.** Với lỗi DB đánh dấu transaction rollback-only, retry trong cùng transaction có thể vô ích hoặc dẫn tới UnexpectedRollbackException. Một retry bên ngoài transaction thường giúp mỗi attempt dùng transaction mới, nhưng phải biết tác động trước retry và idempotency.

### 16.2. Retry là phương tiện phục hồi, không thay rollback

| Loại lỗi | Hướng xử lý |
|---|---|
| DB connection transient trước commit | Rollback rồi retry transaction có backoff |
| Deadlock JDBC | Retry transaction mới có giới hạn |
| Data validation permanent | Rollback/quarantine, không retry vô hạn |
| Duplicate eventId | Dedupe, có thể coi đã xử lý nếu invariant đúng |
| HTTP timeout outcome unknown | Reconcile/idempotent retry, không chỉ rollback DB |
| Permission/authentication denied | Sửa credential/ACL, hạn chế retry |
| Kafka producer callback fail sau DB commit | Outbox retry, không giả rollback SQL |

### 16.3. Recovery callback và rollback

Nếu retry advice có recovery callback tự publish ErrorMessage rồi trả về như một kết quả bình thường, exception cuối có thể không đến transaction interceptor bên ngoài theo cách bạn dự kiến. Ngược lại, transaction advice trong từng attempt có thể đã rollback trước khi recovery callback được gọi. Phải kiểm tra **rollback rules thực tế, thứ tự advice và recovery policy** bằng integration test.

### 16.4. Tổng retry budget

Giả sử HTTP client retry 3 lần, Spring Retry advice retry 4 lần và message broker redelivery 5 lần. Số lời gọi remote có thể tăng lên nhiều lần và gây side effect trùng. Cần một **business attempt budget** hoặc rõ ràng ai sở hữu retry tại từng stage.

### 16.5. Sau retry exhausted

Không chỉ log. Hãy định nghĩa:

- RETRY_EXHAUSTED với error category;
- Quarantine/DLQ/DLT theo adapter (DLT cho Kafka);
- Durable recovery reference và owner;
- Deadline/SLA cần xử lý;
- Bằng chứng DB transaction đã rollback hay commit;
- Side effects ngoài transaction cần reconcile/compensate.

## 17. Outbox, inbox và compensation: khi local rollback không đủ

### 17.1. Vấn đề dual-write

Một handler vừa ghi database, vừa gửi message sang broker:

~~~text
BEGIN DB TX
    INSERT order
    Publish OrderCreated to Kafka
COMMIT DB TX
~~~

Có thể xảy ra:

1. Kafka publish thành công, DB commit thất bại → consumer đã thấy event nhưng DB không có order.
2. DB commit thành công, Kafka publish thất bại → order tồn tại nhưng không có event.
3. DB commit thành công, producer nhận timeout dù broker đã lưu event → retry có thể gửi trùng.

Một local transaction không loại bỏ ba khả năng này.

### 17.2. Transactional outbox

Ghi **business state và outbox intent** trong một DB transaction:

~~~mermaid
flowchart LR
    IN["Inbound event"] --> TX["Local DB transaction"]
    TX --> ORD["Order row"]
    TX --> OUT["Outbox row"]
    ORD --> C["DB commit / rollback cùng OUT"]
    OUT --> C
    C --> WORK["Publisher worker"]
    WORK --> MSG["Kafka / AMQP / HTTP"]
    MSG --> ACK["Confirm and mark sent / retry"]
~~~

Outbox đảm bảo không bị trạng thái **DB đã commit nhưng không lưu ý định phát** nếu schema/transaction triển khai đúng. Nhưng worker có thể crash **sau khi publish, trước khi mark sent**, nên vẫn cần idempotent receiver hoặc deduplication.

### 17.3. Transactional inbox/idempotent consumer

Khi nhận message JMS/AMQP/Kafka, lưu **event ID đã xử lý và business state** atomically trong DB nếu cùng DataSource. Khi broker redeliver, consumer kiểm tra eventId và không thực hiện side effect DB lần hai.

Ví dụ pseudocode:

~~~text
transaction:
    if inbox.contains(eventId):
        return ALREADY_PROCESSED
    validate expectedVersion
    apply business state change
    insert inbox(eventId, outcome)
    commit

ack source according to broker/container policy
~~~

Vẫn có cửa sổ DB commit trước broker ack, nhưng redelivery được dedupe. Nếu side effect là HTTP bên ngoài, chỉ inbox DB chưa đủ — cần remote idempotency/reconciliation.

### 17.4. Compensation cho side effect đã commit

Một đơn đã được shipment service tạo, sau đó downstream billing handler thất bại. Không thể dùng ROLLBACK JDBC để hủy shipment. Tạo **compensation command**:

~~~json
{
  "commandId": "cancel-shipment-order-274",
  "sagaId": "saga-274",
  "operation": "CANCEL_SHIPMENT",
  "targetReference": "shipment-S274",
  "idempotencyKey": "saga-274-cancel-shipment-v1",
  "status": "PENDING",
  "reason": "BILLING_STEP_FAILED"
}
~~~

Đây là schema nghiệp vụ minh họa, không phải Spring Integration DTO có sẵn. Bước bù phải kiểm tra resource thuộc saga, quyền, thời hạn hủy và kết quả thực tế. HTTP 202 có thể chỉ là “đã tiếp nhận”, chưa chứng minh đã hủy.

### 17.5. Không phải mọi lỗi downstream đều cần compensation

Nếu event broker tạm unavailable nhưng business goal còn hợp lệ, có thể retry outbox thay vì lập tức hủy đơn. Nếu input validation fail trước mọi side effect, không cần bù. Nếu timeout có kết quả unknown, **reconciliation trước** để tránh bù sai.

### 17.6. Quyết định bằng trạng thái nghiệp vụ

| State | Hành động |
|---|---|
| DB_TX_ROLLED_BACK | Input cần replay/abort theo policy nguồn |
| DB_COMMITTED_OUTBOX_PENDING | Publisher retry, không chạy lại DB transaction mù |
| REMOTE_OUTCOME_UNKNOWN | Tra cứu trạng thái, không tạo request ID mới tùy ý |
| COMPENSATION_REQUIRED | Tạo command bù bền vững |
| COMPENSATING | Worker thực thi từng bù, giữ retry/owner |
| COMPENSATED | Đã xác minh bù thực tế |
| MANUAL_REVIEW | Thiếu căn cứ để retry/bù tự động an toàn |

Các tên state do ứng dụng đặt, **không phải enum mặc định của Spring Integration**.

## 18. Transaction synchronization và trạng thái source

### 18.1. Transaction completion không trùng nguồn message completion

Khi poller đọc File/SFTP/JDBC hoặc QueueChannel, “lấy được một Message” là một sự kiện khác với “DB đã commit” và khác với “source đánh dấu đã xử lý”. Ứng dụng cần định nghĩa khi nào thay đổi source state:

- File: move từ inbox sang processed/failed sau business outcome có bằng chứng;
- SFTP: remote rename/delete hoặc archive sau khi có xác nhận;
- JDBC: chuyển row PENDING → PROCESSING → PROCESSED/RETRY;
- QueueChannel: lưu durable command/ack logic thay vì chỉ remove khỏi memory;
- Broker listener: ack/offset theo đúng transaction/recovery contract.

### 18.2. Callback sau commit và sau rollback

Spring transaction synchronization có thể chạy callbacks theo trạng thái commit/rollback. Điều đó giúp điều phối file movement hoặc cleanup **nhưng callbacks không tham gia cùng transaction filesystem/HTTP**.

Nếu một callback sau commit thất bại, thay đổi JDBC đã được commit. Nếu callback sau rollback lỗi, file có thể còn tại vị trí trung gian. Cần metadata, durable recovery reference và cảnh báo.

### 18.3. PseudoTransactionManager là gì?

Với nguồn không hỗ trợ transaction thật (File/SFTP), một số giải pháp Spring Integration sử dụng **PseudoTransactionManager** để tạo bối cảnh transaction synchronization cho callback afterCommit/afterRollback. Nhưng **không có resource manager thật nào bị rollback bởi pseudo transaction**.

Không dùng PseudoTransactionManager để tuyên bố “file download, SFTP rename và JDBC insert đều atomic”. Nếu muốn rollback JDBC, dùng manager thực quản lý JDBC và thiết kế state tệp riêng.

### 18.4. Đơn vị nghiệp vụ quyết định rollback

Một file có 1.000 records:

- Nếu cần all-or-nothing, có thể xử lý DB trong transaction phù hợp khi kích thước/tài nguyên cho phép; vẫn phải bảo vệ file source.
- Nếu xử lý theo batch nhỏ, mỗi batch đã commit là một checkpoint; downstream failure ở batch sau **không rollback batch trước**.
- Nếu mỗi record có idempotent business key, có thể replay file nhưng skip/verify records đã commit.

Không giữ một transaction DB quá dài chỉ để “trông giống atomic file import” nếu nó gây lock, pool exhaustion hoặc timeout.

## 19. Kiểm thử rollback với một JDBC database thật trong Spring context

### 19.1. Mục tiêu test

Bài test trọng tâm cần chứng minh:

1. H1 thực sự thực hiện INSERT khi transaction đang active.
2. H2 ném exception **trước commit** trên cùng call stack.
3. Exception đến entrypoint @Transactional.
4. Transaction manager rollback.
5. Sau khi hoàn tất, truy vấn từ transaction khác **không thấy** bản ghi.

Kiểm tra “có exception” mà không kiểm tra DB sau đó **chưa chứng minh rollback**.

### 19.2. JUnit 5 kiểm tra exception và dữ liệu

Ví dụ sau dùng các beans **OrderSubmissionService**, **OrderRollbackFlowConfiguration** và bảng integration_orders ở phần 5, một test context với Spring JDBC transaction manager:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        OrderRollbackFlowConfiguration.class,
        OrderRollbackTestInfrastructure.class
})
class OrderRollbackIntegrationTest {

    @Autowired
    OrderSubmissionService submission;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void clearRows() {
        jdbc.update("DELETE FROM integration_orders");
    }

    @Test
    void downstreamFailureRollsBackJdbcInsert() {
        RuntimeException thrown = assertThrows(RuntimeException.class,
                () -> submission.submit(new OrderCommand("order-274")));
        Throwable root = thrown;
        for (int i = 0; i < 32 && root.getCause() != null; i++) {
            if (root.getCause() == root) {
                break;
            }
            root = root.getCause();
        }
        assertInstanceOf(IllegalStateException.class, root);

        Integer remaining = jdbc.queryForObject(
                "SELECT COUNT(*) FROM integration_orders WHERE order_id = ?",
                Integer.class, "order-274");
        assertEquals(0, remaining);
    }
}
~~~

Đây là mẫu test thành phần: OrderRollbackTestInfrastructure cần cung cấp DataSource, JdbcTemplate, transaction manager, @EnableTransactionManagement và bean OrderSubmissionService cho phép Spring áp dụng proxy. Hạ tầng H2 in-memory minh họa có thể được tạo như sau:

~~~java
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.messaging.MessageChannel;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
class OrderRollbackTestInfrastructure {

    @Bean
    DataSource testDataSource() {
        return new EmbeddedDatabaseBuilder()
                .setType(EmbeddedDatabaseType.H2)
                .build();
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource testDataSource) {
        JdbcTemplate jdbc = new JdbcTemplate(testDataSource);
        jdbc.execute(
                "CREATE TABLE integration_orders (" +
                "order_id VARCHAR(80) PRIMARY KEY, " +
                "status VARCHAR(30) NOT NULL)");
        return jdbc;
    }

    @Bean
    PlatformTransactionManager transactionManager(
            DataSource testDataSource) {
        return new JdbcTransactionManager(testDataSource);
    }

    @Bean
    OrderSubmissionService orderSubmissionService(
            @Qualifier("ordersInput") MessageChannel input) {
        return new OrderSubmissionService(input);
    }
}
~~~

Đây là **fixture H2 cho học tập**: cần dependency Spring Integration, Spring Test, JUnit Jupiter, Spring JDBC và H2 phù hợp phiên bản. Trong một dự án thật có thể dùng Testcontainers để kiểm tra DB đích; đồng thời không đăng ký trùng DataSource/TransactionManager. Nếu transaction manager có nhiều beans, cần chỉ rõ qualifier và manager được @Transactional sử dụng. Test kiểm tra **root cause** thay vì giả định exception gốc luôn được ném trực tiếp, bởi Spring Integration có thể bọc nó bằng một MessagingException.

### 19.3. Không đặt @Transactional trên test này một cách vô thức

Nếu test method tự chạy trong một transaction với rollback mặc định của Spring Test, kết quả COUNT=0 có thể đến từ **rollback của test framework**, không phải rollback tại business entrypoint. Để chứng minh đường ứng dụng, nên chạy test method **không có @Transactional ở mức test** hoặc sử dụng TransactionTemplate/chủ động tách giao dịch kiểm tra.

### 19.4. Test đối chứng

Một test hữu ích nữa:

1. Tạo cấu hình H2 không ném exception;
2. Gửi một OrderCommand khác;
3. Xác minh INSERT được commit;
4. Sau đó bật fault injection ở H2;
5. Xác minh cùng DB transaction rollback khi lỗi.

Điều này giúp tránh false positive do handler JDBC chưa bao giờ thực thi hoặc SQL INSERT luôn fail trước H2.

### 19.5. Assert rollback state, không dựa vào log

Tăng logs transaction có thể giúp debug nhưng assertions nên quan sát DB từ connection khác sau khi transaction kết thúc. Với multi-database/resource, truy vấn từng resource; nếu một resource nằm ngoài manager, test phải làm lộ sự không atomic.

### 19.6. Test với DB engine production

H2 in-memory thuận tiện cho unit/integration test cơ bản, nhưng deadlock, isolation level, lock wait và retry có thể khác PostgreSQL/MySQL/Oracle. Cần có một lớp integration tests trên engine thực hoặc môi trường tương đương để kiểm tra concurrency, rollback và retry.

## 20. Ma trận fault injection theo transaction boundary

| Case | Điểm cố tình gây lỗi | Điều cần xác minh |
|---|---|---|
| T01 | Trước transaction begin | Không có DB side effect; source state rõ |
| T02 | Sau INSERT H1, trước H2 | JDBC rollback khi exception được propagate |
| T03 | H2 DirectChannel ném RuntimeException | Exception tới caller, DB row không commit |
| T04 | H2 ném checked exception chưa cấu hình rollbackFor | Quan sát commit/rollback thực tế theo rules |
| T05 | H2 exception được catch và return bình thường | DB có thể commit; phát hiện policy sai |
| T06 | H1 REQUIRES_NEW commit, H2 throw | Transaction mới không tự rollback |
| T07 | H2 sau ExecutorChannel | Tx upstream có thể đã commit; worker lỗi riêng |
| T08 | Poller receive File, JDBC rollback | Filter/file source được giữ/replay/quarantine đúng |
| T09 | SFTP remote rename trước DB error | Remote không tự undo; recovery xác định |
| T10 | HTTP POST remote commit rồi response mất | DB rollback nhưng shipment có thể tồn tại |
| T11 | JMS listener lỗi và rollback transacted session | Redelivery/ack và DB state theo policy |
| T12 | AMQP listener catches error rồi returns | Ack/nack/DB state không bị suy sai |
| T13 | Kafka offset đã commit trước async handler fail | Có durable recovery, không mất nghiệp vụ |
| T14 | DB commit rồi Kafka publish fail | Outbox giữ event pending |
| T15 | Publisher crash sau Kafka accept trước mark sent | Consumer dedupe; không thêm side effect |
| T16 | Retry inner/outer transaction advice đảo thứ tự | Số attempts, transaction count và final state |
| T17 | Error handler tự thất bại | Có fallback, không mất recovery reference |
| T18 | App restart giữa rollback và source retry | Input còn truy hồi, không bị duplicate vô kiểm soát |
| T19 | Hai workers cùng một business key | Optimistic lock/idempotency ngăn lost update |
| T20 | Credential/TLS hết hạn lúc retry | Lỗi được phân loại, không retry storm |

**Lưu ý:** fault injection phải có cơ chế dọn dữ liệu, namespace/topic riêng và không gọi API production thật bằng test command. Dùng fake server/broker hoặc môi trường integration test được phép.

### 20.1. Bốn điểm crash không thể bỏ qua

~~~text
P1  Before external send
P2  After external send but before response
P3  After DB commit but before broker acknowledgment
P4  After broker acknowledgment but before downstream async completion
~~~

Với P2, kết quả remote có thể unknown; với P3, nguồn có thể redeliver; với P4, message có thể mất nếu async work chưa durable. **Không một rollback JDBC nào tự giải quyết cả bốn cửa sổ**.

### 20.2. Kiểm thử execution order

Với ExecutorChannel hoặc nhiều consumers, dùng CountDownLatch/barrier để buộc H2 ném exception sau khi H1 đã return/commit. Điều này thể hiện ranh giới transaction. Kiểm tra event version, committed state và retry outcomes, không chỉ thứ tự log.

## 21. Case study: nhập đơn SFTP, ghi JDBC, gọi HTTP, phát Kafka

### 21.1. Bối cảnh nghiệp vụ

Nền tảng A nhận file đơn hàng từ nhà cung cấp B qua SFTP. Spring Integration đọc file mỗi phút, kiểm tra dữ liệu, lưu order vào JDBC, tạo vận đơn qua HTTPS của đối tác C, rồi phát OrderAccepted lên Kafka để billing và analytics xử lý.

Yêu cầu:

- Mỗi orderId chỉ có một bản ghi đơn và một vận đơn tương ứng;
- Không mất đơn khi file đã được tải nhưng DB chưa commit;
- Downstream billing fail không làm hệ thống coi đơn đã hoàn tất;
- Kafka unavailable tạm thời không nhất thiết làm hủy order đã hợp lệ;
- Có thể đối soát những HTTP request đã gửi nhưng không nhận response;
- Có bằng chứng xử lý khi rollback, retry, bù hoặc manual review.

### 21.2. Phiên bản sai: tưởng một transaction JDBC bao toàn flow

~~~mermaid
flowchart LR
    S["SFTP poller"] --> P["Parse CSV"]
    P --> DB["JDBC INSERT"]
    DB --> H["HTTP CreateShipment"]
    H --> K["Kafka send"]
    K --> END["Complete"]
    H -. "Failure" .-> ERR["Error flow"]
    K -. "Failure" .-> ERR
    ERR --> RB["Assume ROLLBACK ALL (sai)"]
~~~

Nếu DB transaction rollback sau HTTP thành công, shipment vẫn có thể tồn tại. Nếu Kafka publish đã đến broker, một rollback JDBC sau đó không xóa Kafka record đã phát. Nếu lỗi Kafka callback đến muộn, DB có thể đã commit trước khi callback được gọi.

### 21.3. Phương án 1 — DB transaction ngắn + outbox

Chia thành các bước:

1. **SFTP input:** tải file an toàn, giữ durable file reference/batch ID; chưa đánh dấu đã xử lý.
2. **Local DB transaction:** validate, INSERT/UPSERT order và INSERT outbox command CreateShipment trong một transaction.
3. **Sau DB commit:** worker đọc outbox và gọi HTTPS C dùng requestId/idempotency key.
4. **Sau khi xác minh shipment:** ghi trạng thái shipment và outbox intent OrderAccepted trong local transaction.
5. **Kafka worker:** publish OrderAccepted, retry an toàn và mark sent sau xác nhận phù hợp.
6. **File state:** archive theo policy khi các điều kiện nghiệp vụ được thỏa, không chỉ khi nhận ErrorMessage.

Nếu H1 JDBC thất bại, rollback chỉ làm mất **local writes chưa commit**; file vẫn được quản lý qua state. Nếu HTTP C thất bại, order đã tồn tại với trạng thái pending shipment, worker sẽ retry/reconcile. Nếu Kafka lỗi, outbox giữ intent.

### 21.4. Trạng thái đề xuất

| Thành phần | Trạng thái | Ý nghĩa |
|---|---|---|
| Import file | DETECTED, CLAIMED, IMPORTED, QUARANTINED | Theo dõi nguồn SFTP |
| Order | PENDING_SHIPMENT, SHIPMENT_CONFIRMED, COMPLETED, CANCELLED | Theo dõi nghiệp vụ |
| Outbox | PENDING, IN_FLIGHT, SENT, RETRY, FAILED | Theo dõi lệnh outbound |
| Remote shipment | UNKNOWN, CREATED, CANCELLED | Đối soát phía đối tác C |
| Saga | RUNNING, COMPENSATING, COMPLETED, MANUAL_REVIEW | Điều phối các side effects |

Các state là thiết kế minh họa, không được Spring Integration tự tạo. Các transitions cần version check và audit, nhất là khi nhiều workers cùng xử lý một order.

### 21.5. Sự cố A — Downstream validation ném exception trong DB transaction

~~~text
Begin TX
  -> Insert order-274
  -> Validate duplicate policy
  -> RuntimeException
Rollback TX
  -> order-274 không có trong DB
  -> source file vẫn được quản lý bằng file state
~~~

Kiểm thử cần:

- Assert exception hợp lệ;
- SELECT xác nhận DB không có order-274;
- Kiểm tra không có outbox event đã commit;
- File còn có thể replay hoặc đã được quarantine đúng policy;
- Không có HTTP CreateShipment đã gửi nếu validation nằm trước outbound.

### 21.6. Sự cố B — HTTP C tạo shipment nhưng response bị mất

DB order có thể ở PENDING_SHIPMENT; C đã tạo shipment S274. Worker nhận timeout, không biết outcome. Coordinator giữ RESULT_UNKNOWN, truy vấn C bằng requestId hoặc idempotency key, ghi resource ID thật, rồi quyết định tiếp tục hay compensate.

**Đừng rollback/DELETE order và gửi lại HTTP bằng request ID mới một cách mù quáng.** Một shipment chưa được lưu trong DB của A vẫn có thể tồn tại ở C.

### 21.7. Sự cố C — Kafka unavailable sau HTTP success

Outbox OrderAccepted vẫn PENDING/RETRY. Worker Kafka retry với backoff, đảm bảo event ID ổn định. Nếu lỗi kéo dài quá business deadline, phối hợp owner quyết định hủy/compensate hoặc manual review. Không kích hoạt CancelShipment chỉ vì một Kafka producer callback lỗi tạm thời nếu policy cho phép tiếp tục.

### 21.8. Sự cố D — Worker crash sau publish

Kafka broker đã nhận event, nhưng worker crash trước khi update outbox SENT. Khi restart, worker có thể publish lại. Consumer billing phải dedupe theo eventId/business key. Đây là **at-least-once delivery với idempotent effects**, không phải “exactly-once” được suy từ DB rollback.

### 21.9. Sự cố E — SFTP file đã được filter accepted nhưng JDBC rollback

Error channel nhận MessageHandlingException; ứng dụng ghi log và quay về poll. Nếu filter đã đánh dấu file accepted, file có thể không được đọc lại. Cần persistent import state/retry reference và cơ chế replay có kiểm soát, không chỉ gắn transaction JDBC vào File poller.

### 21.10. Các invariant cần assert

| Invariant | Cách xác minh |
|---|---|
| Một orderId không tạo hai order rows | Unique key + DB query |
| Một orderId không tạo hai shipments | Stable idempotency key + remote query |
| Không có outbox SENT nếu chưa xác minh publish | Outbox state + broker evidence |
| Khi handler DB downstream lỗi, local writes chưa commit rollback | Transactional integration test |
| File không bị mất sau rollback | File state/filter/replay test |
| Kafka duplicate không tạo billing hai lần | Consumer inbox/idempotency test |
| Có failure owner khi outcome unknown | Saga state + audit |
| Hệ thống phục hồi sau restart | Fault injection + retry backlog verification |

## 22. Observability: đo rollback, transaction và message lifecycle

### 22.1. Các tín hiệu cần có

| Metric đề xuất | Ý nghĩa |
|---|---|
| db_transaction_rollback_total | Số transaction DB rollback theo stage/category |
| db_transaction_commit_total | Số transaction DB commit |
| downstream_handler_failures_total | Lỗi handler downstream |
| integration_error_messages_total | Số ErrorMessage được publish theo flow |
| retry_attempts_total | Số lần retry |
| retry_exhausted_total | Lỗi đã hết retry |
| outbox_pending_count | Lệnh/event chờ phát |
| inbox_deduplicated_total | Message trùng đã được chặn |
| source_replay_pending_count | File/row/queue message cần replay |
| kafka_consumer_lag | Lag của consumer group |
| amqp_unacked_count | Message đang unacked nếu có provider metric |
| jms_redelivery_total | Message redelivery theo integration/provider metric |
| external_result_unknown_count | HTTP hoặc remote side effect chưa rõ |

Những tên trên là **gợi ý instrument**, không phải tất cả được Spring Integration tự xuất. Cần xác định nguồn đo và đừng suy transaction outcome từ số ErrorMessage.

### 22.2. Log theo business correlation

~~~text
flow=orders-sftp-import
businessKey=order-274
messageId=M274
transactionScope=jdbc-orders
stage=DOWNSTREAM_HANDLER
exceptionCategory=TRANSIENT
dbOutcome=ROLLED_BACK
sourceDisposition=RETRY_PENDING
remoteOutcome=UNKNOWN
attempt=2
~~~

**dbOutcome=ROLLED_BACK** chỉ được ghi khi có căn cứ từ transaction completion hoặc kiểm tra state, không chỉ vì handler ném exception. Một message có thể có nhiều transaction scopes, cần định danh đúng.

### 22.3. Không log secret và dữ liệu nhạy cảm

MessagingException.failedMessage có thể chứa File, HTTP Authorization, Kafka headers hoặc nội dung dữ liệu khách hàng. Error handlers cần log metadata tối thiểu: flow/stage/exception class/correlation, che token và PII, kiểm soát retention của error events. Không in toàn bộ Message hoặc Throwable stacktrace lên dashboard công khai.

### 22.4. Cảnh báo theo tác động

- Rollback rate tăng cao bất thường;
- SFTP/JDBC poller dừng hoặc không có last-successful-poll;
- Outbox pending lâu, Kafka lag tăng;
- Message redelivery/DLQ nhiều;
- HTTP remoteOutcome UNKNOWN vượt SLA;
- File được nhận nhưng chưa có trạng thái xử lý cuối;
- Transaction commit success nhưng downstream business confirmation thiếu;
- Error handler thất bại hoặc recovery queue không tiến triển.

**Không có ErrorMessage mới không chứng minh flow khỏe mạnh**: poller có thể không được schedule hoặc broker listener đã dừng.

## 23. Runbook: downstream thất bại, rollback có thực sự xảy ra?

### Bước 1 — Xác định phạm vi

Ghi chính xác:

- Source adapter (File/SFTP/JDBC/JMS/AMQP/Kafka/HTTP);
- Flow ID, endpoint IDs và MessageChannel giữa H1/H2;
- Transaction manager và resource đang được quản lý;
- Thread/executor và điểm chuyển bất đồng bộ;
- Business key/correlation ID, thời điểm và lỗi được quan sát.

### Bước 2 — Vẽ transaction timeline

~~~text
t0  Input received
t1  Transaction begin?
t2  JDBC operation H1
t3  Any remote side effect?
t4  H2 fails or async work dispatched?
t5  Transaction commit/rollback?
t6  Source ack/filter/offset updated?
t7  ErrorMessage published / recovery scheduled?
~~~

Nếu t5 xảy ra **trước t4**, H2 không thể làm rollback transaction đã hoàn tất. Nếu t4 xảy ra trước t5 nhưng exception bị swallow, transaction có thể commit trừ khi rollback-only đã được đặt.

### Bước 3 — Đọc exception đúng cách

Nếu có ErrorMessage:

1. Lấy payload kiểu Throwable;
2. Nếu payload thuộc MessagingException, đọc failedMessage nếu có;
3. Kiểm tra originalMessage nhưng hiểu rằng nó có thể null;
4. Xác định cause root và stage;
5. Không nhầm ErrorMessage headers với input Message headers;
6. Không log payload/secret nguyên văn.

Nếu không có ErrorMessage, kiểm tra caller synchronous exception hoặc adapter/container error handler trước khi kết luận không có lỗi.

### Bước 4 — Xác minh trạng thái tài nguyên

| Tài nguyên | Cần xác minh |
|---|---|
| JDBC DB | Row thực còn không, version gì, transaction đã commit/rollback? |
| File | Filter accepted chưa, file moved/deleted/quarantined chưa? |
| SFTP | Remote file đã rename/delete/download/processed chưa? |
| HTTP | API ngoài đã tạo resource chưa, requestId nào? |
| JMS | Message ack/rollback/redelivery theo provider? |
| AMQP | Ack/nack/requeue/DLQ và side effect consumer? |
| Kafka | Offset/transaction/DLT, producer publish result? |
| Outbox/inbox | Event intent và dedupe record có tồn tại không? |

### Bước 5 — Chọn recovery

- **Chưa commit, DB rollback thành công:** retry input nếu còn hợp lệ và an toàn.
- **DB commit rồi callback/downstream lỗi:** outbox retry, compensation hoặc reconciliation theo contract.
- **HTTP outcome unknown:** query external state trước retry.
- **Broker redelivery:** dedupe theo eventId/business key.
- **File filter giữ file dù DB rollback:** controlled replay/quarantine.
- **Không đủ context:** MANUAL_REVIEW có owner, không tự bịa resource ID.

### Bước 6 — Phòng lỗi lặp lại

Tăng test bao bốn điểm crash, bổ sung correlation/idempotency, review transaction advice order, xác minh listener ack policy và giám sát trạng thái nguồn. Không sửa bằng cách mở một transaction toàn cục quá dài hoặc tắt error handling.

### Bước 7 — Đóng sự cố

Chỉ đóng khi có bằng chứng state nghiệp vụ cuối, message source đã có disposition, các side effects ngoài đã được xử lý/đối soát và không còn retry/compensation pending không có owner. Tất cả dữ liệu điều tra phải được bảo vệ theo phân loại.

## 24. Các anti-pattern thường gặp

| Anti-pattern | Hậu quả | Biện pháp |
|---|---|---|
| Cho rằng cùng IntegrationFlow là cùng DB transaction | Một số handler commit trước lỗi downstream | Vẽ transaction scope và thread boundary |
| Gắn @Transactional nhưng gọi self-invocation | Interceptor không mở transaction như mong đợi | Dùng proxy entrypoint hoặc TransactionTemplate |
| DirectChannel không có transaction nhưng gọi là transactional flow | JDBC auto-commit từng thao tác | Cấu hình manager và kiểm thử rollback |
| Tưởng ExecutorChannel truyền transaction qua thread | Upstream commit trước khi worker lỗi | Durable work và transaction ở worker |
| Ghi DB bằng một DataSource khác manager | Một DB commit, DB khác rollback | Quản lý resource rõ, saga/XA khi phù hợp |
| Dùng REQUIRES_NEW mà nghĩ outer rollback hủy nó | Record ngoài còn lại | Hiểu propagation và commit độc lập |
| Catch exception rồi log/return success | Transaction có thể commit khi nghiệp vụ sai | Propagate, mark rollback-only có chủ đích hoặc recovery bền vững |
| Coi ErrorMessage đồng nghĩa rollback đã xảy ra | Không điều tra commit state | Quan sát transaction completion và DB |
| Coi không có ErrorMessage nghĩa là không rollback | Bỏ sót synchronous exception | Kiểm tra call stack và transaction interceptor |
| Gắn errorChannel header rồi chờ transaction tự rollback | Không có tác dụng | Cấu hình đúng transaction và error publisher |
| Đặt retry advice sai thứ tự | Retry trên transaction rollback-only | Test advice ordering, separate attempts |
| Retry mọi exception vô hạn | Poison loop, lockout, overload | Phân loại, backoff, budget, quarantine |
| Bật transaction trên File/SFTP và cho rằng file rollback | Mất hoặc trùng file sau lỗi | Durable file state, sync callbacks, replay policy |
| Dùng PseudoTransactionManager như DB manager thật | Không có rollback tài nguyên thật | Chỉ dùng cho synchronization callbacks khi phù hợp |
| Gửi HTTP POST trong DB transaction rồi tin DB rollback xóa request | Remote side effect tồn tại | Idempotency/reconciliation/compensation |
| Dùng HTTP 500 để suy DB rollback | Dữ liệu có thể đã commit trước response | Test database/transaction outcome |
| Ack JMS/AMQP trước khi phục hồi được lưu | Mất message nghiệp vụ | Durable inbox/recovery và ack policy |
| Requeue message sau DB commit không có dedupe | Duplicate rows và side effects | Idempotent consumer |
| Coi DLQ/DLT là rollback | Record được cách ly nhưng DB không đổi | Business reconciliation |
| Kafka offset commit trước khi async work durable | Message có thể mất sau crash | Commit/ack theo durable completion |
| Kafka rollback được HTTP/JDBC | Inconsistency xuyên hệ thống | Outbox/inbox/saga |
| DB commit rồi publish trực tiếp không outbox | Dual-write gap | Transactional outbox |
| Outbox publisher không idempotent | Phát event nhiều lần sau restart | Stable eventId và consumer dedupe |
| Chỉ assert exception trong test | Không chứng minh rollback | Query committed DB state và source |
| Đặt @Transactional lên test và đọc state trong test transaction | False positive | Tách transaction test và operation |
| Chỉ test H2 khi production dùng DB khác | Không phát hiện lock/isolation khác | Integration tests DB thực |
| Log toàn bộ failedMessage hoặc Throwable | Lộ token, SQL params hoặc PII | Structured safe metadata |
| Đóng incident sau khi thấy ErrorMessage | Recovery chưa xong | Verify business state và owner |

## 25. Checklist thiết kế transaction và rollback cho IntegrationFlow

### A. Contract nghiệp vụ

- [ ] Xác định đơn vị nghiệp vụ cần atomic: record, batch, file, order hay workflow.
- [ ] Liệt kê tất cả side effects theo thứ tự: DB, File, SFTP, HTTP, JMS, AMQP, Kafka.
- [ ] Định nghĩa khi nào được coi là COMPLETED, FAILED, RETRY_PENDING hoặc MANUAL_REVIEW.
- [ ] Có business key, eventId, correlation ID và idempotency policy.
- [ ] Phân loại lỗi permanent, transient và outcome unknown.

### B. Transaction scope

- [ ] Biết transaction manager thực tế quản lý DataSource/JMS/Kafka resource nào.
- [ ] Xác định transaction được mở qua @Transactional, TransactionTemplate hoặc poller advice.
- [ ] @Transactional entrypoint được gọi qua Spring proxy, không self-invoke.
- [ ] Các JDBC handlers dùng cùng transaction-managed DataSource khi cần atomicity.
- [ ] Không có REQUIRES_NEW làm commit ngoài dự kiến.
- [ ] Đã xác minh exception rollback rules (RuntimeException/checked/rollbackFor).
- [ ] Không nuốt exception trước interceptor nếu nghiệp vụ yêu cầu rollback.
- [ ] Không nhầm transaction synchronization callback với transaction thật của File/SFTP.

### C. Topology và thread

- [ ] Vẽ DirectChannel, QueueChannel, ExecutorChannel và asynchronous endpoints.
- [ ] Xác định H2 chạy trước hay sau transaction commit.
- [ ] Với poller, biết transaction advice bao receive/handler đến đâu.
- [ ] Với taskExecutor, callback hoặc Flux, có transaction/recovery riêng ở worker.
- [ ] ErrorMessage/errorChannel được cấu hình ở đúng endpoint và không bị hiểu là rollback API.
- [ ] Có test khi error handler hoặc retry recovery callback swallow exception.

### D. Adapter-specific semantics

- [ ] File filter và SFTP remote state được quản lý khi JDBC rollback.
- [ ] HTTP outbound có idempotency hoặc API đối soát outcome unknown.
- [ ] JMS listener có ack/transaction/redelivery policy phù hợp.
- [ ] AMQP có ack/nack/requeue/DLQ và test lỗi downstream.
- [ ] Kafka offset/producer transaction/DLT được kiểm tra cùng async boundary.
- [ ] JDBC transaction, isolation, concurrency, unique constraints và retry đã test.
- [ ] Có outbox/inbox khi cần khắc phục dual-write và duplicate delivery.
- [ ] Không đòi rollback external side effect vốn đã commit; có compensation khi cần.

### E. Kiểm thử

- [ ] Unit test rollback rule và state machine.
- [ ] Integration test DirectChannel H1 write → H2 throw → DB row absent.
- [ ] Positive test H1/H2 thành công → DB row committed.
- [ ] Test lỗi before/after commit, before/after ack, before/after remote request.
- [ ] Test exception bị catch/rethrow khác nhau.
- [ ] Test asynchronous downstream failure không rollback DB commit trước đó.
- [ ] Test poller source state khi DB rollback.
- [ ] Test JMS/AMQP/Kafka redelivery và duplicate business key.
- [ ] Test restart/outbox/inbox, retry exhausted và compensation failure.
- [ ] Test cùng DB engine và transaction config production ở mức trọng yếu.

### F. Operations

- [ ] Metrics commit/rollback, retry, source backlog và outbox lag có định nghĩa.
- [ ] Không lưu secret/PII trong ErrorMessage hoặc logs không kiểm soát.
- [ ] Có runbook xác minh DB state, HTTP outcome, broker ack/offset và file state.
- [ ] Có owner/deadline cho unresolved recovery.
- [ ] Có bằng chứng sau sự cố, không chỉ dựa vào log message lỗi.

## 26. Câu hỏi tự kiểm tra

**Câu 1.** H1 INSERT JDBC, H2 ném RuntimeException trên cùng DirectChannel, nhưng không có @Transactional hay transaction advice. Có thể chắc INSERT rollback không?

**Đáp án:** Không. DirectChannel đồng bộ không tự tạo transaction. JDBC có thể auto-commit; cần transaction manager và boundary bao cả hai handler.

**Câu 2.** Có @Transactional trên method gọi DirectChannel, H2 throw trước method return. Điều kiện cần để rollback JDBC?

**Đáp án:** Transaction phải thật sự mở qua proxy, H1 tham gia cùng resource/manager, exception thuộc rollback rules và propagate về interceptor trước commit.

**Câu 3.** Exception ở ExecutorChannel worker xảy ra sau khi sender commit DB. Nó có rollback commit cũ được không?

**Đáp án:** Không. Worker ở ranh giới async/transaction riêng; cần durable command, transaction tại worker, retry hoặc compensation.

**Câu 4.** H1 ghi JDBC, H2 ném checked IOException. Có rollback mặc định không?

**Đáp án:** Theo default Spring rules truyền thống, checked exception thường không kích hoạt rollback nếu không khai báo rollbackFor hoặc quy tắc tương đương. Cần xem wrapper và cấu hình version thực.

**Câu 5.** Handler catch RuntimeException, log rồi return bình thường. Tại sao DB có thể commit?

**Đáp án:** Transaction interceptor thấy method hoàn tất thành công nếu transaction chưa bị đánh dấu rollback-only; log không phải tín hiệu rollback.

**Câu 6.** H1 thực thi trong REQUIRES_NEW rồi commit, H2 lỗi ở transaction ngoài. H1 có bị rollback không?

**Đáp án:** Không tự động. Transaction mới độc lập đã commit. Cần thiết kế propagation đúng mong muốn.

**Câu 7.** @Transactional method tự gọi method @Transactional khác bằng this.method(). Có đáng tin rằng transaction thứ hai mở không?

**Đáp án:** Không với proxy-based AOP thông thường. Self-invocation bypass proxy, cần entrypoint bean riêng hoặc cơ chế khác.

**Câu 8.** Một ErrorMessage xuất hiện ở global errorChannel. Có chứng minh DB đã rollback không?

**Đáp án:** Không. ErrorMessage chỉ mang Throwable được publish. Phải kiểm tra transaction completion hoặc committed DB state.

**Câu 9.** Không có ErrorMessage nhưng caller nhận MessagingException. Có thể DB đã rollback không?

**Đáp án:** Có. Lỗi đồng bộ có thể lan về @Transactional caller, kích hoạt rollback mà không có error publisher.

**Câu 10.** File poller đã chọn một file rồi DB rollback. File có chắc được poll lại không?

**Đáp án:** Không. File filter/metadata có thể đã đánh dấu accepted, phải có file state/replay policy riêng.

**Câu 11.** Dùng PseudoTransactionManager trên SFTP có tự undo remote rename không?

**Đáp án:** Không. Pseudo transaction có thể hỗ trợ callback synchronization nhưng không biến remote filesystem thành transactional resource.

**Câu 12.** HTTP CreateShipment trả timeout, sau đó DB rollback. Shipment có chắc không tồn tại?

**Đáp án:** Không. Server có thể đã tạo shipment. Cần idempotency key và đối soát trạng thái trước retry/compensation.

**Câu 13.** JMS listener ném exception nhưng error handler swallow. Message có chắc redeliver không?

**Đáp án:** Không. Ack/redelivery phụ thuộc container/transaction/error policy; nếu container thấy success, message có thể được acknowledge.

**Câu 14.** AMQP message được nack/requeue sau khi DB commit. Redelivery có thể gây gì?

**Đáp án:** Dễ tạo duplicate DB rows/side effects nếu consumer không idempotent. Cần inbox/unique key và state.

**Câu 15.** Kafka transactional producer có bảo đảm rollback HTTP request trước đó không?

**Đáp án:** Không. Kafka transaction chỉ có phạm vi Kafka tương ứng, không tự quản lý remote HTTP hoặc local JDBC ngoài cơ chế phối hợp thích hợp.

**Câu 16.** Kafka offset đã commit, H2 async thất bại sau đó. Còn source record để xử lý lại không?

**Đáp án:** Không được mặc định. Cần durable work/recovery store trước khi commit offset nếu việc xử lý tiếp theo chưa hoàn tất.

**Câu 17.** Tại sao transactional outbox cần consumer idempotency?

**Đáp án:** Publisher có thể crash sau khi broker nhận event nhưng trước khi đánh dấu SENT, rồi gửi lại. Stable eventId và dedupe chống side effect trùng.

**Câu 18.** Dedupe inbox record có nên ghi transaction khác với business update không?

**Đáp án:** Nếu hai thao tác cùng DB và cùng mục tiêu nghiệp vụ, nên commit atomically để tránh cửa sổ đã update nhưng chưa dedupe hoặc ngược lại.

**Câu 19.** Retry advice nằm ngoài transaction advice khác gì khi retry nằm trong?

**Đáp án:** Ngoài transaction có thể tạo transaction mới cho mỗi attempt; bên trong có thể retry trên transaction đã bị đánh dấu rollback-only. Cần test advice order và policy thật.

**Câu 20.** Có nên giữ JDBC transaction mở trong khi HTTP API phản hồi chậm?

**Đáp án:** Thường nên tránh vì giữ connection/lock và không tạo atomicity xuyên HTTP. Xem outbox và idempotent worker.

**Câu 21.** Một integration test có assertThrows và COUNT=0 nhưng chính test method được đánh dấu @Transactional, tự rollback cuối test. Đã đủ chứng minh rollback ứng dụng chưa?

**Đáp án:** Chưa. Có thể là rollback của Spring Test. Cần thiết kế test không bị bao trong transaction không mong muốn và truy vấn sau khi business transaction kết thúc.

**Câu 22.** Sau khi H2 lỗi, DB không còn order, nhưng Kafka có OrderCreated. Cần làm gì?

**Đáp án:** Đối soát dual-write và downstream consumers, xử lý compensating event nếu cần; sửa thiết kế bằng outbox hoặc cơ chế consistency phù hợp.

**Câu 23.** Một record vào Kafka DLT hoặc RabbitMQ DLQ có nghĩa DB được rollback không?

**Đáp án:** Không. DLQ/DLT là cơ chế định tuyến/kho lỗi message, transaction DB có trạng thái riêng.

**Câu 24.** Vì sao cần test crash sau DB commit trước broker ack?

**Đáp án:** Broker có thể redeliver message sau restart, gây duplicate nếu không có idempotency. Đây là một cửa sổ hỏng phổ biến.

**Câu 25.** Bằng chứng đáng tin nhất để kết luận rollback khi handler downstream thất bại?

**Đáp án:** Có transaction boundary xác định, exception thuộc rollback policy, committed DB state không chứa thay đổi chưa được phép; đồng thời source/remote/broker states được xác minh độc lập theo contract.

## 27. Kết luận và tài liệu tham khảo

### 27.1. Kết luận trọng tâm

Rollback khi handler downstream thất bại **không phụ thuộc vào vị trí handler trong sơ đồ flow**, mà phụ thuộc **transaction manager quản lý tài nguyên nào, khi nào commit, handler có chạy trong cùng boundary và exception có đi qua rollback rule hay không**.

Trong Spring Integration:

1. **DirectChannel + transaction đồng bộ** cho phép exception ở downstream kích hoạt rollback JDBC upstream khi toàn bộ lời gọi thuộc cùng transaction chưa commit.
2. **Transactional poller** có thể bao phần xử lý đồng bộ trong polling task, nhưng rollback database không tự đưa File/SFTP message về trạng thái ban đầu.
3. **ExecutorChannel, QueueChannel, async HTTP/Kafka callbacks** tạo ranh giới thời gian/thread; exception về sau không thể rollback commit đã hoàn tất ở sender.
4. **JMS/AMQP/Kafka delivery state** có transaction/ack/error handler riêng, cần kiểm thử với broker/container configuration thực tế.
5. **HTTP/SFTP side effects đã xảy ra** cần idempotency, reconciliation hoặc compensation; không thể hứa rollback xuyên tất cả adapters bằng một annotation.
6. **ErrorMessage/errorChannel** là cơ chế thông báo lỗi; không phải bằng chứng commit/rollback và không thay thế durable retry workflow.
7. **Outbox/inbox, unique constraints, transaction-aware retries, state machine và fault injection** giúp đạt tính đúng đắn nghiệp vụ khi không có một global transaction.

Điều quan trọng nhất khi vận hành là **kiểm chứng trạng thái ở điểm commit của từng tài nguyên**. Một dòng log báo exception hoặc một ErrorMessage được publish không đủ để tuyên bố đã rollback đúng, nhất là khi có remote side effects, broker redelivery hoặc xử lý bất đồng bộ.

### 27.2. Nguồn đọc tiếp

- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html): transaction support, poller advice và transaction synchronization.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): synchronous/async exception, ErrorMessage và errorChannel.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, QueueChannel, ExecutorChannel và dispatch semantics.
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): @Transactional, AOP proxies, rollback rules và propagation.
- [Spring Framework Reference — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): TransactionTemplate và explicit boundaries.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/): container error handling, offset, transactions, retries và DLT.
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/): listener acknowledgment, transaction và DLQ.

**Ghi chú về phiên bản:** Các code block và sơ đồ là ví dụ giáo dục cho Spring Integration Adapters. Kiểu API Java DSL, poller transaction specification, callback ordering, adapter/container behavior và JDBC transaction manager có thể khác theo phiên bản Spring Boot/Spring Integration/JDK/driver. Trước khi đưa vào production, đối chiếu API thực tế và chạy integration tests trên tài nguyên tương ứng. Bài này hoàn thành phạm vi viết tài liệu, không thay cho Content QA chuyên môn của quy trình tiếp theo.
