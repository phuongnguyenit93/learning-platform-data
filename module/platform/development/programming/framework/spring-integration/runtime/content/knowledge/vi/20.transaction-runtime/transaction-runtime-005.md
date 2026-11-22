# Rollback khi handler throw exception trong Spring Integration runtime

## 1. Vấn đề cần giải quyết

Trong **SPRING_INTEGRATION_RUNTIME**, một message đi qua `MessageChannel`, consumer endpoint, message handler và có thể gọi database, broker, HTTP hoặc những flow khác. Khi handler ném exception giữa chừng, câu hỏi không chỉ là *có lỗi hay không* mà còn là:

- Có **transaction đang hoạt động** ở thời điểm handler ném lỗi không?
- Transaction đó do **ai mở**: method `@Transactional`, handler advice, poller hay inbound listener?
- Exception có **thoát đến transaction boundary** không, và rollback rule đánh giá nó như thế nào?
- **Tài nguyên nào tham gia** transaction, và message nguồn có thể nhận lại sau rollback hay không?
- Flow đã qua `ExecutorChannel`, `QueueChannel` hoặc ranh giới thread khác chưa?
- Retry, recovery callback và error flow có vô tình đổi lỗi thành “xử lý thành công” không?

Đề bài **Transaction runtime → Rollback khi handler throw exception** là hiểu chính xác chuỗi quyết định đó và kiểm chứng bằng một thí nghiệm JDBC.

Ví dụ: message `CreateOrder("O-42")` đến service activator; handler ghi đơn vào database, sau đó ném `IllegalStateException`. Nếu đoạn ghi database chạy trong Spring transaction và lỗi thoát ra khỏi boundary, transaction có thể rollback bản ghi. Nếu không có transaction, lệnh ghi có thể đã được commit dù handler báo lỗi. Ngay cả khi JDBC rollback, **message đầu vào không tự động được gửi lại** nếu nguồn message không có cơ chế redelivery phù hợp.

~~~mermaid
flowchart TD
    A["Message vào endpoint"] --> B{"Có transaction đang bao\nthao tác tài nguyên?"}
    B -->|Không| N["Handler ghi DB / gọi dịch vụ"]
    N --> U["Exception: thao tác đã commit trước đó\nkhông tự được hoàn tác"]
    B -->|Có| C["Handler thực thi trong transaction"]
    C --> D{"Exception thoát khỏi\ntransaction boundary?"}
    D -->|Không, bị catch/trap| E["Boundary có thể commit\ntrừ khi đã mark rollback-only"]
    D -->|Có| F{"Rollback rules\ncó khớp exception?"}
    F -->|Có| R["Rollback tài nguyên tham gia"]
    F -->|Không| K["Boundary có thể commit\ndù exception truyền ra ngoài"]
    R --> X["Redelivery? phụ thuộc adapter,\nmessage store và ack"]
~~~

**Quy tắc trung tâm:** `throw` chỉ là tín hiệu lỗi. Rollback cần **transaction thật**, **boundary bao đúng thao tác**, **exception được transaction infrastructure quan sát**, **quy tắc rollback phù hợp** và **tài nguyên tham gia giao dịch**.

## 2. Bốn lớp cần phân biệt ở runtime

| Lớp | Thành phần điển hình | Vai trò | Sai lầm thường gặp |
| --- | --- | --- | --- |
| **Message delivery** | `DirectChannel`, `QueueChannel`, `ExecutorChannel`, broker adapter | Chuyển message đến consumer, quyết định thread và handoff | Nghĩ channel nào cũng có transaction mặc định |
| **Transaction boundary** | `@Transactional`, `TransactionInterceptor`, poller transactional advice | Mở/join/commit/rollback một giao dịch | Nghĩ mọi handler `throw` đều tự tạo transaction |
| **Transactional resources** | JDBC/JPA connection, JMS session hoặc message store hỗ trợ transaction | Thực hiện commit/rollback dữ liệu đang được quản lý | Nghĩ rollback JDBC cũng hoàn tác HTTP call |
| **Failure/recovery** | `errorChannel`, retry advice, recoverer, DLQ, broker ack/nack | Quyết định quan sát, retry, lưu lỗi, redelivery | Nghĩ nhận `ErrorMessage` đồng nghĩa rollback nguồn |

Một transaction gắn với resource manager cụ thể. Ví dụ `DataSourceTransactionManager` quản lý JDBC connection của một `DataSource`; nó không thể hoàn tác một HTTP request đã gửi thành công. Nếu JMS và JDBC phải cùng commit như một đơn vị, có thể cần transaction manager thích hợp với mô hình giao dịch của cả hai tài nguyên, hoặc dùng outbox/inbox thay vì giả định chúng tự đồng bộ.

**Ví dụ thực tế:** flow nhận đơn từ broker, ghi row trong DB rồi gửi HTTP tạo vận đơn. Nếu DB và broker tham gia vào transaction phù hợp thì rollback có thể ảnh hưởng DB và việc nhận message; request HTTP đã thực hiện thường **không rollback**. Để xử lý trùng khi redelivery, endpoint HTTP cần idempotency key hoặc cơ chế đối soát trạng thái.

## 3. Khi nào một exception làm Spring rollback?

Với **Spring declarative transaction** thông thường, quy tắc mặc định là:

| Hành vi tại transaction boundary | Kết quả mặc định |
| --- | --- |
| Handler ném `RuntimeException` và exception đi qua interceptor | Transaction bị đánh rollback |
| Handler ném `Error` và đi qua interceptor | Transaction bị đánh rollback |
| Handler ném checked `Exception` (ví dụ `IOException`) | Mặc định **không rollback**, trừ khi cấu hình rule phù hợp |
| Handler tự `catch` lỗi rồi trả về bình thường | Interceptor có thể **commit** nếu transaction chưa đánh `rollback-only` |
| Handler trả `false`/`null` như kết quả bình thường | Không tự gây rollback chỉ vì giá trị trả về |
| Handler gọi `setRollbackOnly()` | Transaction bị rollback dù code sau đó trả về bình thường |
| Transaction trước đó đã bị đánh `rollback-only` bởi một scope khác | Attempt commit ngoài cùng có thể ném `UnexpectedRollbackException` |

Có thể định nghĩa rõ rule trên Spring service:

~~~java
@Transactional(rollbackFor = BusinessCheckedException.class)
public void createOrder(OrderCommand command)
        throws BusinessCheckedException {
    repository.insert(command);
    if (hasPermanentIssue(command)) {
        throw new BusinessCheckedException("Business failure");
    }
}
~~~

Đây là **đoạn minh họa**, cần cung cấp các kiểu phụ thuộc `BusinessCheckedException`, `OrderCommand`, `repository` và `hasPermanentIssue`. `rollbackFor` dùng **class type** thay vì tên pattern để tránh match ngoài ý muốn. `noRollbackFor` có thể dùng khi exception thực sự là kết quả nghiệp vụ cho phép commit, nhưng cần kiểm tra trường hợp tài nguyên đã đánh rollback-only trước đó.

Trong Spring Framework 6.2+ còn có khả năng cấu hình **quy tắc mặc định toàn cục** (ví dụ rollback với mọi exception). Do đó bảng trên mô tả hành vi thông thường khi **chưa tùy chỉnh** rollback policy. Khi chẩn đoán một ứng dụng, luôn xem cấu hình thực tế của transaction interceptor và `@EnableTransactionManagement`.

### Exception wrapper của Spring Integration

Một method handler có thể ném `IllegalStateException`, nhưng tầng endpoint có thể bọc nó trong `MessageHandlingException` hoặc một `MessagingException` khác. Điều cần quan sát là **exception thật sự đi qua transaction advice**. Mặc định các wrapper này thường là runtime exception nên vẫn gây rollback, nhưng nếu dùng `rollbackFor`/`noRollbackFor` theo class, hãy kiểm tra actual type, cause chain và policy cụ thể.

Không nên biến mọi lỗi thành checked exception mà quên cập nhật rule, cũng không nên nuốt lỗi trong handler chỉ để giảm số log.

## 4. Ranh giới theo thread: điều quyết định rollback có lan ngược hay không

Transaction thông thường của Spring dựa vào context gắn với thread. Với chuỗi `DirectChannel` đồng bộ, các handler downstream chạy cùng thread gửi, nên có thể dùng cùng transaction nếu scope giao dịch bao đoạn này.

~~~mermaid
flowchart LR
    A["Caller mở TX"] --> B["DirectChannel"]
    B --> C["@ServiceActivator A"]
    C --> D["DirectChannel"]
    D --> E["@ServiceActivator B throws"]
    E -->|Exception cùng call stack| A
~~~

Nếu A, B cùng làm việc trên JDBC connection tham gia transaction do caller mở và B ném một unchecked exception không bị catch, boundary ở caller có thể rollback cả các thay đổi trước đó.

Ngược lại, một handoff qua `ExecutorChannel` hoặc pollable channel tạo ranh giới mới:

~~~mermaid
flowchart LR
    A["Thread 1\nTX-A"] --> B["ExecutorChannel"]
    B --> C["Thread 2\nHandler ném lỗi"]
    C --> D["Error flow của worker"]
    B --> E["Thread 1 handoff OK\nTX-A có thể commit"]
~~~

Nếu việc bàn giao message thành công, transaction của thread gửi có thể commit **trước khi** worker xử lý thất bại. Lỗi ở worker không tự quay lại transaction đã kết thúc.

| Channel/consumer | Thread và failure propagation | Tác động rollback |
| --- | --- | --- |
| `DirectChannel` | Handler thường chạy trong thread của `send()` | Exception đồng bộ có thể đi ngược tới transaction ngoài cùng |
| `ExecutorChannel` | Dispatch sang `TaskExecutor` | Transaction context ở thread cũ không tự truyền; worker cần boundary riêng |
| `QueueChannel` + poller | `send()` enqueue; consumer poll sau | Transaction lúc enqueue và lúc poll tách biệt; cần hiểu store và poller |
| `PublishSubscribeChannel` đồng bộ | Nhiều subscriber chạy trên caller thread | Lỗi có thể tác động transaction gọi, tùy error handling và order |
| `PublishSubscribeChannel` có executor | Gọi subscriber bất đồng bộ | Cần transaction và error flow theo từng worker |
| JMS/AMQP/Kafka inbound | Listener container có ack, redelivery và transaction policy riêng | Rollback hoặc nack phải theo đúng adapter/broker configuration |

**Thử nghiệm tư duy:** B ghi DB và throw sau khi nhận từ `ExecutorChannel`. Caller A bao `send()` trong `@Transactional`, nhưng `send()` trả về sau khi handoff thành công. A commit; B sau đó mới thất bại. Để kết hợp atomic handoff và xử lý, cần thiết kế durable channel, outbox hoặc transaction trên cả hai phía phù hợp, chứ không kéo dài transaction của một thread qua executor.

## 5. Ví dụ tự chứa: handler ghi JDBC rồi ném exception

Ví dụ dùng **Java 17+**, Spring Boot với Spring Integration, Spring JDBC và H2 in-memory. Dependency cần có starter Spring Integration, starter JDBC và H2 runtime tương thích phiên bản Boot. Đặt nội dung dưới đây vào **một file** `RollbackDemoApplication.java` trong package `demo.integration`; chạy ứng dụng với package được component scan.

Mục đích: gửi hai message, một thành công và một gây lỗi **sau khi INSERT**, rồi kiểm tra database còn những dòng nào.

~~~java
package demo.integration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@SpringBootApplication
@EnableIntegration
public class RollbackDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(RollbackDemoApplication.class, args);
    }

    @Bean("orderCommands")
    MessageChannel orderCommands() {
        return new DirectChannel();
    }

    @Bean
    ApplicationRunner demo(
            @Qualifier("orderCommands") MessageChannel input,
            JdbcTemplate jdbc) {

        return args -> {
            jdbc.execute("""
                CREATE TABLE IF NOT EXISTS demo_orders (
                    order_id VARCHAR(50) PRIMARY KEY,
                    status VARCHAR(20) NOT NULL
                )
                """);

            sendAndReport(input, "O-SUCCESS", false);
            sendAndReport(input, "O-FAIL", true);

            Integer ok = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM demo_orders WHERE order_id = ?",
                    Integer.class, "O-SUCCESS");
            Integer failed = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM demo_orders WHERE order_id = ?",
                    Integer.class, "O-FAIL");

            System.out.printf("DB O-SUCCESS=%d, O-FAIL=%d%n", ok, failed);
        };
    }

    private static void sendAndReport(
            MessageChannel input, String id, boolean shouldFail) {

        try {
            input.send(MessageBuilder
                    .withPayload(new OrderCommand(id, shouldFail))
                    .setHeader("traceId", "trace-" + id)
                    .build());
            System.out.println("SEND_OK " + id);
        }
        catch (RuntimeException ex) {
            System.out.println("SEND_FAILED " + id + ": "
                    + ex.getClass().getSimpleName());
        }
    }
}

record OrderCommand(String orderId, boolean shouldFail) {}

@MessageEndpoint
class OrderCommandHandler {

    private final OrderTransactionService service;

    OrderCommandHandler(OrderTransactionService service) {
        this.service = service;
    }

    @ServiceActivator(inputChannel = "orderCommands")
    public void handle(OrderCommand command) {
        service.saveOrder(command); // gọi qua bean khác -> transaction proxy
    }
}

@Service
class OrderTransactionService {

    private final JdbcTemplate jdbc;

    OrderTransactionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void saveOrder(OrderCommand command) {
        System.out.println("TX_ACTIVE="
                + TransactionSynchronizationManager
                        .isActualTransactionActive());

        jdbc.update(
            "INSERT INTO demo_orders (order_id, status) VALUES (?, ?)",
            command.orderId(), "CREATED");

        if (command.shouldFail()) {
            throw new IllegalStateException(
                    "Simulated failure after database INSERT");
        }
    }
}
~~~

**Kết quả dự kiến** (bỏ qua log khởi động):

~~~text
TX_ACTIVE=true
SEND_OK O-SUCCESS
TX_ACTIVE=true
SEND_FAILED O-FAIL: ...
DB O-SUCCESS=1, O-FAIL=0
~~~

Tên exception in ở `SEND_FAILED` có thể là wrapper do Spring Integration tạo. Kết quả quan trọng là **DB có O-SUCCESS và không có O-FAIL**.

### Vì sao ví dụ rollback đúng?

1. `ApplicationRunner` gửi `Message<OrderCommand>` vào `DirectChannel`.
2. `@ServiceActivator` nhận message và gọi `OrderTransactionService.saveOrder(...)` qua **Spring bean proxy**.
3. `@Transactional` mở transaction (hoặc tham gia transaction sẵn có); `JdbcTemplate` lấy connection tham gia `DataSourceTransactionManager` do Boot cấu hình từ `DataSource`.
4. Code INSERT bản ghi. Nếu `shouldFail` là true, `IllegalStateException` thoát khỏi `saveOrder()`.
5. Transaction interceptor nhận runtime exception và rollback INSERT. Sau đó exception tiếp tục về `send()` trên cùng thread; caller catch để log.
6. Message thành công được commit; message lỗi không để lại bản ghi trong bảng.

**Không nhầm lẫn:** ở ví dụ này, transaction nằm **trong service**, bao quanh mỗi lời gọi `saveOrder()`. `DirectChannel` cho phép exception đi ngược nhưng không làm nguyên cả `ApplicationRunner` tự động trở thành một transaction. Việc `SEND_FAILED` được catch sau đó **không đảo ngược rollback đã thực hiện** bên trong service proxy.

Ví dụ không có broker hay queue bền vững, nên sau lỗi `O-FAIL` **không tự xuất hiện lại**. Muốn retry/redelivery phải bổ sung chính sách và nguồn có hỗ trợ.

### Đổi một điều để quan sát kết quả khác

Nếu bỏ `@Transactional` trên `saveOrder()` và không có transaction ngoài đang mở, mỗi `jdbc.update()` thường được commit độc lập (tùy autocommit/DataSource); khi method ném lỗi, bản ghi `O-FAIL` **có thể vẫn tồn tại**. Đây là bài kiểm chứng khác biệt giữa “handler ném exception” và “tài nguyên được rollback”.

Nếu đổi `IllegalStateException` thành checked exception, cần khai báo `throws` phù hợp ở method/caller và cấu hình `rollbackFor` khi muốn rollback theo quy tắc mong muốn.

## 6. @Transactional có hiệu lực khi nào?

`@Transactional` thường hoạt động qua proxy (Spring AOP). Có annotation trên source code chưa đủ chứng minh transaction thực sự được mở.

| Tình huống | Hành vi thường gặp | Hướng xử lý |
| --- | --- | --- |
| Handler gọi một `@Service` khác qua bean Spring được inject | Lời gọi đi qua proxy | Phù hợp; kiểm tra `TX_ACTIVE` |
| Một method trong cùng object gọi `this.saveOrder()` đã annotate | Self-invocation bỏ qua proxy trong proxy mode | Tách sang bean khác hoặc dùng boundary phù hợp |
| Method không phải Spring-managed bean | Không được Spring transaction proxy bọc | Đăng ký bean và bật transaction management đúng cách |
| Method private/final, đối tượng proxy không intercept được | Transaction có thể không áp như kỳ vọng | Dùng public/proxy-interceptable method theo cấu hình |
| Hai transaction managers hoặc nhiều DataSource | Có thể chọn nhầm manager, resource không join | Chỉ rõ `@Transactional(transactionManager = "...")` |
| Transaction tồn tại nhưng dùng JDBC connection ngoài manager | Resource không chắc tham gia transaction | Dùng `JdbcTemplate`/Spring-managed connection hoặc infrastructure tương thích |

Trong ứng dụng Spring Boot có JDBC/JPA starter và transaction manager phù hợp, transaction management thường được auto-configure. Ở Spring Framework thuần cần cấu hình manager và kích hoạt management rõ ràng. Việc ghi `TX_ACTIVE=true` giúp xác nhận có transaction context, nhưng **chưa đủ** để chứng minh mọi external resource cùng tham gia; vẫn cần kiểm tra loại manager và log/DB thực tế.

### Khi nguồn đã mở transaction

Một inbound listener hoặc poller có thể đã mở transaction trước khi gọi handler. Với `Propagation.REQUIRED` (mặc định), `@Transactional` ở service thường **join transaction hiện tại**. Transaction không commit ngay lúc service trả về; nó chỉ commit/rollback ở **boundary ngoài cùng** tương ứng.

Giả sử service insert rồi một handler downstream cùng thread ném exception. Nếu transaction scope ngoài cùng bao cả downstream, toàn bộ thay đổi tham gia transaction có thể rollback. Nếu không có transaction ngoài và service đã commit, lỗi downstream **không hồi tố rollback** bản ghi service đã commit.

## 7. Transactional poller: rollback của handler có requeue message không?

Poller là thành phần đặc biệt: nó chủ động gọi `receive()` từ nguồn message rồi đưa message vào flow. Spring Integration hỗ trợ đặt transaction quanh **receive-and-forward**. Với XML namespace, cú pháp khái niệm:

~~~xml
<int:service-activator input-channel="workQueue"
                       ref="workHandler"
                       method="process">
    <int:poller fixed-delay="1000" max-messages-per-poll="1">
        <int:transactional transaction-manager="transactionManager"
                           propagation="REQUIRED"/>
    </int:poller>
</int:service-activator>
~~~

Đây là **đoạn cấu hình XML**: cần khai báo namespace `int`, bean `workQueue` loại `PollableChannel`, bean `workHandler` và bean `transactionManager`, cùng phần cấu hình context. Tùy loại inbound adapter, poller cũng có thể được khai báo ở đầu nguồn tương ứng.

Khi handler ném runtime exception **đồng bộ** trong lần poll và không bị nuốt lỗi:

1. Transaction advice quanh poll bắt lỗi.
2. Giao dịch của các tài nguyên tham gia (ví dụ JDBC cùng manager) được rollback.
3. Poller/error handler có thể ghi nhận lỗi rồi tiếp tục chu kỳ polling tiếp theo.
4. **Việc message có trở lại hàng đợi hay không tùy thuộc message source/queue store.**

| Nguồn message | Sau rollback cần kỳ vọng gì? |
| --- | --- |
| `QueueChannel` thuần **in-memory** | Không mặc định đảm bảo một message đã dequeue sẽ được put lại khi database rollback. |
| Queue/message store **hỗ trợ giao dịch** trên cùng resource và dùng manager phù hợp | Thao tác lấy/xóa khỏi store có thể rollback cùng transaction, cho phép message xuất hiện lại. |
| JMS session được transacted hoặc transaction manager phù hợp | Broker có thể redeliver theo transaction và broker policy. |
| AMQP/Kafka hoặc adapter khác | Hành vi phụ thuộc acknowledge, nack, rollback và cấu hình container của adapter cụ thể. |
| File inbound adapter | Đọc file không phải một transaction filesystem; có thể dùng synchronization để di chuyển file theo commit/rollback. |

**Không suy diễn:** đặt `<int:transactional>` trên poller không biến mọi `QueueChannel` trong bộ nhớ thành durable transactional queue. Cũng không biến nhiều resource manager độc lập thành một transaction phân tán.

### Message store và transaction synchronization

Với JDBC-backed store, cần chọn transaction manager cho cùng `DataSource` và kiểm tra câu lệnh receive/delete/save có tham gia transaction hay không. Cơ chế `TransactionSynchronizationFactory` cho phép thực hiện logic **beforeCommit**, **afterCommit** hoặc **afterRollback** với message poll được, chẳng hạn di chuyển file nguồn đến thư mục thành công/thất bại hoặc phát message audit theo kết quả.

~~~text
Poller transaction bắt đầu
    receive message
    xử lý flow đồng bộ
    handler throw RuntimeException
Transaction rollback
    afterRollback synchronization được gọi nếu cấu hình
    adapter/broker quyết định có redeliver hay không
~~~

Transaction synchronization chỉ đồng bộ hóa thời điểm thực hiện hành động; **không làm file, HTTP hoặc một resource phi transaction trở nên có thể rollback**. `PseudoTransactionManager` chỉ cung cấp lifecycle callback commit/rollback giả lập, không thực sự rollback dữ liệu.

## 8. Handler advice và phạm vi rollback

Ngoài `@Transactional` trên Spring service, Spring Integration có thể gắn `TransactionInterceptor` vào advice chain của endpoint.

Với **reply-producing handler** như transformer hoặc outbound gateway, một request-handler advice thông thường thường chỉ bao quanh `handleRequestMessage()`. Bước gửi reply tới channel downstream có thể nằm **ngoài** scope đó. Vì vậy:

~~~text
input -> @Transformer(tx request-handler advice) -> DirectChannel -> failing handler
               | transaction chỉ bao logic transform |
                                                         X throw
~~~

Nếu transaction của transformer đã commit trước khi gửi reply, exception ở downstream không làm rollback transaction đó. Khi cần bao cả `handleMessage()` và phần downstream đồng bộ, Spring Integration cung cấp **`TransactionHandleMessageAdvice`** (dạng `HandleMessageAdvice`), và `TransactionInterceptorBuilder(true)` có thể xây dựng advice tương ứng theo API của framework.

Ví dụ cách khai báo builder (đoạn độc lập, cần bean transaction manager và import phù hợp):

~~~java
@Bean("transactionAdvice")
TransactionInterceptor transactionAdvice(
        PlatformTransactionManager transactionManager) {

    return new TransactionInterceptorBuilder(true)
            .transactionManager(transactionManager)
            .build();
}
~~~

Trong đoạn này, `TransactionInterceptorBuilder` nằm trong `org.springframework.integration.transaction`; cấu hình advice cho endpoint bằng `adviceChain = "transactionAdvice"` ở annotation hỗ trợ. Cần kiểm tra phiên bản API thực tế khi nhập và cấu hình kiểu `TransactionManager`/`PlatformTransactionManager`. `true` chọn `TransactionHandleMessageAdvice` thay vì request-handler transaction interceptor thông thường.

**Ranh giới thread vẫn giữ nguyên:** `TransactionHandleMessageAdvice` có thể bao phần downstream đồng bộ qua `DirectChannel`, nhưng không truyền transaction qua `ExecutorChannel` hoặc poller thread khác. Đừng xem nó là cơ chế transaction xuyên broker hay xuyên service.

### Thứ tự retry và transaction advice

Giả sử advice chain khai báo tuần tự từ ngoài vào trong:

~~~text
[retryAdvice, transactionAdvice]
  retry attempt #1 -> transaction -> handler throw -> rollback
  retry attempt #2 -> transaction -> handler success -> commit

[transactionAdvice, retryAdvice]
  transaction -> retry attempt #1 throw
              -> retry attempt #2 success
              -> commit? có thể vướng rollback-only
~~~

Với thứ tự **retry ngoài, transaction trong**, mỗi attempt *có thể* tạo transaction riêng **nếu** không tồn tại transaction ngoài và propagation/manager phù hợp. Với transaction ngoài, nhiều attempt cùng một transaction có thể khiến trạng thái rollback-only bị đánh dấu. Recovery callback hoặc `trapException` cũng có thể nuốt exception làm lớp ngoài quyết định commit.

Trong luồng có poller transaction, việc handler advice tự tạo transaction `REQUIRES_NEW` có thể dẫn tới commit riêng trước khi poller rollback: đây là hành vi có thể đúng khi làm audit lỗi, nhưng không phù hợp nếu bạn cần atomicity của business data với nguồn message.

## 9. Caught exception, rollback-only và UnexpectedRollbackException

Một số lỗi khó tìm vì **handler có throw nhưng transaction vẫn commit**, hoặc **handler đã catch lỗi nhưng commit sau cùng lại thất bại**.

### Tình huống A: lỗi bị nuốt trước transaction interceptor

~~~java
@Transactional
public void saveOrder(OrderCommand command) {
    jdbc.update("INSERT INTO ...", ...);
    try {
        callExternalApi();
    }
    catch (RuntimeException ex) {
        logger.warn("API error", ex);
    }
    // Trả bình thường: interceptor có thể commit JDBC.
}
~~~

Ví dụ này minh họa ý tưởng; các hàm phụ thuộc chưa được khai báo. Nếu yêu cầu rollback, **ném lại exception** hoặc đánh dấu rollback-only có chủ đích. Chỉ ghi log không gây rollback.

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

// Chỉ dùng khi biết chắc đang ở declarative transaction có hiệu lực.
TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
~~~

Tuy nhiên, `setRollbackOnly()` tạo logic transaction ẩn trong nghiệp vụ; khi có thể, hãy để exception và rollback rule thể hiện ý định rõ ràng hơn.

### Tình huống B: inner REQUIRED đánh rollback-only, outer vẫn commit

~~~text
outer @Transactional REQUIRED
    inner @Transactional REQUIRED
        DB change
        throw RuntimeException
    outer catch(RuntimeException) rồi tiếp tục
outer return bình thường
outer commit -> UnexpectedRollbackException
~~~

Khi inner method qua **proxy** và join cùng transaction, interceptor của inner có thể đánh transaction đang chia sẻ là rollback-only. Outer catch không xóa được cờ đó; khi commit, transaction manager báo commit không thể hoàn tất. Đây là tín hiệu quan trọng để tránh "commit thành công giả".

### Tình huống C: Checked exception

Nếu method ném `IOException` mà không có `rollbackFor` và không có rule khác, transaction interceptor có thể **commit** rồi chuyển exception ra caller. Việc xuất hiện stack trace không chứng minh DB đã rollback. Test nên kiểm tra cả dữ liệu còn lại, không chỉ kiểm tra có exception.

### Tình huống D: Filter trả false hoặc recovery thành công

`@Filter` trả `false` thường là kết quả điều kiện nghiệp vụ, không phải exception. Tương tự, retry advice có `RecoveryCallback` có thể phát `ErrorMessage` rồi trả về bình thường sau khi đã lưu lỗi. Tùy scope và transaction manager, transaction bên ngoài **có thể commit**. Khi yêu cầu broker redeliver, đừng sử dụng recoverer nuốt exception trừ khi recovery đã bảo đảm lưu bền vững và nghiệp vụ chủ đích coi công việc gốc đã kết thúc.

## 10. Sự kiện lỗi, errorChannel, retry, ack và correlation

Thời điểm xảy ra exception ảnh hưởng nơi quan sát lỗi:

| Trạng thái khi handler lỗi | Nơi lỗi thường xuất hiện | Điều cần kiểm chứng |
| --- | --- | --- |
| `DirectChannel` sync, không trap | Exception thường về caller `send()`/gateway | Caller có transaction ngoài không? |
| Endpoint polling | Poller error handler và/hoặc `ErrorMessage` | Poller có transaction quanh receive và handler không? |
| `ExecutorChannel` | Worker thread, error flow phù hợp | Transaction của worker có riêng không? |
| Broker listener | Container error handler, rollback/nack/requeue | Ack mode, retry count, DLQ/redelivery policy |
| Retry advice với recovery callback | Recovery channel/handler | Recovery đã lưu được lỗi trước khi coi message hoàn thành chưa? |

**`errorChannel` không phải transaction manager.** Việc gửi `ErrorMessage` không tự gọi rollback, cũng không bảo đảm message nguồn đã được requeue. Nó là đường điều phối lỗi; lỗi gốc phải tiếp cận transaction boundary trong thời điểm phù hợp để ảnh hưởng commit.

Trong Spring Integration, lỗi có thể chứa `MessagingException.failedMessage`; với poller có synchronization thích hợp, message gốc cũng có thể được gắn vào lỗi phát qua error channel để điều tra. Hãy ghi `traceId`, `correlationId`, `eventId`/idempotency key, channel/endpoint và class lỗi. Không đưa payload nhạy cảm nguyên văn vào production logs.

Retry có thể gây **nhiều lần thực thi cùng handler**, dù chỉ có một logical message:

- Khi rollback khiến broker redeliver, cùng command có thể trở lại.
- Khi `RequestHandlerRetryAdvice` retry trong một invocation, service có thể được gọi nhiều lần mà broker không redeliver.
- Khi nhiều retry layer chồng nhau, số invocation có thể tăng nhanh, dễ duplicate side effect.

Vì vậy handler nên idempotent theo khóa nghiệp vụ và có ranh giới transaction rõ. Nếu đã gọi external API rồi mới ném lỗi, rollback JDBC không hoàn tác API; cần idempotency key, outbox và quy trình đối soát.

## 11. Chẩn đoán rollback không như mong đợi

| Triệu chứng | Khả năng gây ra | Cách xác minh |
| --- | --- | --- |
| Handler ném `RuntimeException` nhưng row DB vẫn tồn tại | Thiếu transaction, sai transaction manager, resource không join, hoặc transaction đã commit trước lỗi | Log `TX_ACTIVE`, kiểm tra manager/DataSource và thời điểm commit |
| `TX_ACTIVE=false` trong method `@Transactional` | Self-invocation, bean không qua proxy, transaction management chưa bật | Tách method sang bean khác, xác minh proxy và context |
| `TX_ACTIVE=true` nhưng queue không redeliver | Queue in-memory, nguồn không transacted, adapter ack đã hoàn tất | Kiểm tra loại channel/store, session transaction và ack mode |
| Đã catch lỗi mà cuối cùng `UnexpectedRollbackException` | Inner REQUIRED mark rollback-only | Xác định transaction propagation, các tầng interceptor |
| Checked exception truyền ra ngoài nhưng DB vẫn commit | Rule mặc định không rollback checked exception | Thêm `rollbackFor` đúng type và viết test |
| Downstream throw nhưng transaction của transformer vẫn commit | Request-handler advice chỉ bao `handleRequestMessage()` | Kiểm tra scope `TransactionHandleMessageAdvice` |
| Một số bước rollback, nhưng HTTP side effect còn | External service không tham gia transaction | Dùng idempotency/compensation/outbox |
| Thay `DirectChannel` bằng executor làm thay đổi kết quả | Exception không trở lại original transaction thread | Vẽ lại boundary, đặt manager tại worker |
| Retry báo success nhưng sau đó dữ liệu không nhất quán | Retry/recovery nuốt lỗi hoặc thiếu idempotency | Kiểm tra advice order, callback, ack và commit |
| Poller lỗi nhưng message không còn | Receive operation không rollback được hoặc bị đánh handled | Xem message store và error handler của poller |

### Quy trình debug theo bằng chứng

1. **Tìm boundary:** method `@Transactional`, transaction advice, poller hoặc listener nào mở transaction? Transaction manager của tài nguyên nào?
2. **Ghi timeline:** tại từng handler, log thread name, endpoint name, `TransactionSynchronizationManager.isActualTransactionActive()`, message `traceId` và thời điểm exception.
3. **Kiểm tra propagation:** `REQUIRED`, `REQUIRES_NEW`, `NESTED` (khi resource hỗ trợ savepoint), nơi bắt đầu/commit của outer transaction; đừng suy luận từ annotation đơn lẻ.
4. **Kiểm tra exception thực tế:** class ở boundary, nguyên nhân gốc, đã bị catch/rethrow/trap hay chưa, rollback policy có match?
5. **Kiểm tra durable effect:** row DB trước/sau, message source acknowledgement, queue/broker backlog, recovery store và external side effects.
6. **Fault injection:** gây lỗi *trước INSERT*, *sau INSERT*, *sau commit* và *sau async handoff* để phân biệt ranh giới.
7. **Tối ưu khi đã đúng semantics:** theo dõi transaction duration, số connection chờ, lock wait/deadlock, queue depth, executor saturation và retry storm.

Có thể bật log DEBUG có kiểm soát cho các gói Spring transaction như `org.springframework.transaction.interceptor` và transaction manager tương ứng. Không bật log SQL/payload nhạy cảm tràn lan trên production.

## 12. Bài thực hành và câu hỏi kiểm chứng

1. Chạy ví dụ `RollbackDemoApplication`, xác nhận đúng `O-SUCCESS=1` và `O-FAIL=0`. Kiểm tra `TX_ACTIVE` ở service.
2. Bỏ `@Transactional`, chạy lại với database H2 mới để không bị dữ liệu cũ ảnh hưởng; so sánh DB sau khi throw.
3. Viết `BusinessCheckedException extends Exception`, đổi handler cho ném checked exception và cấu hình `rollbackFor`. So sánh trước/sau rule.
4. Chuyển logic `saveOrder()` vào cùng class rồi gọi qua `this`; quan sát proxy/self-invocation có khiến transaction không được mở không.
5. Đặt một `@ServiceActivator` khác ở downstream cùng `DirectChannel` và cho nó throw **sau** khi service trước đã commit; giải thích vì sao transaction riêng của service trước không rollback ngược.
6. Dùng `ExecutorChannel` có executor giới hạn giữa hai handler, log thread và transaction active ở hai phía; quan sát lỗi phía worker.
7. Đổi nguồn sang `QueueChannel` với poller transactional. So sánh queue in-memory với một nguồn/store hỗ trợ giao dịch; **không giả định** message đã dequeue sẽ quay lại.
8. Thử retry advice theo hai thứ tự `[retry, tx]` và `[tx, retry]`; kiểm tra rollback-only, thời gian giữ thread và số lần invocation.
9. Thêm một consumer recovery tạo record lỗi có `eventId`; xác minh duplicate/restart không tạo hai thao tác nghiệp vụ.
10. Dùng một adapter/broker thử nghiệm có redelivery: gây lỗi handler, theo dõi broker ack/nack, DLQ và điều kiện dừng retry trước khi kết luận rollback đảm bảo xử lý lại.

## 13. Những kết luận phải tự chứng minh trong một flow

- `throw RuntimeException` **không** đủ để chứng minh rollback; phải có transaction bao đúng thao tác và resource tham gia.
- `DirectChannel` giữ call stack đồng bộ; `ExecutorChannel`/pollable channel tạo ranh giới thread khiến transaction ban đầu không tự đi tiếp.
- `@Transactional` thông qua Spring proxy, nên self-invocation và chọn sai transaction manager là nguyên nhân rất phổ biến của rollback không hoạt động.
- Rollback database và **redelivery message** là hai cơ chế khác nhau. Poller transacted + message source hỗ trợ giao dịch mới có thể làm việc nhận message được rollback theo thiết kế.
- Checked exception mặc định không gây rollback; `rollbackFor`, `noRollbackFor` và custom policy quyết định semantics cuối.
- Recovery/trap exception, retry và transaction advice order có thể làm thay đổi việc commit và số lần thực thi handler.
- HTTP call, file operation và các hệ thống ngoài transaction manager cần idempotency, outbox/compensation hoặc transaction coordination thích hợp.
- **Kiểm chứng bằng trạng thái tài nguyên sau lỗi** (row DB, broker ack, DLQ), không chỉ bằng log có exception.

## 14. Tài liệu tham khảo chính thức

- [Spring Integration — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html): poller transactions, transaction boundaries theo thread, synchronization và pseudo-transactions.
- [Spring Integration — Polling and Transactions](https://docs.spring.io/spring-integration/reference/polling-consumer.html): transactional polling và receive-and-forward.
- [Spring Integration — TransactionHandleMessageAdvice](https://docs.spring.io/spring-integration/reference/handler-advice/tx-handle-message.html): phạm vi `handleMessage()` so với `handleRequestMessage()`.
- [Spring Integration — Advice Chain Order](https://docs.spring.io/spring-integration/reference/handler-advice/order.html): thứ tự transaction/retry và advice wrapping.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): default rollback rules, checked exception và custom rollback.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): propagation, manager, proxy, rollback semantics.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED` và rollback-only.
