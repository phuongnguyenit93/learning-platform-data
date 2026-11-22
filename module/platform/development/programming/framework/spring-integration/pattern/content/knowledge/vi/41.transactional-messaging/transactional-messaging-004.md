# Transaction Synchronization trong flow với Spring Integration

## 1. Vì sao cần đồng bộ hành động với vòng đời transaction?

Một **IntegrationFlow** có thể tiếp nhận yêu cầu qua Gateway, dùng Transformer chuẩn hóa dữ liệu, Filter loại thông điệp không hợp lệ, Router chuyển hướng và Service Activator ghi cơ sở dữ liệu. Bên cạnh các bước nghiệp vụ, hệ thống thường cần thực hiện hành động **đúng thời điểm giao dịch kết thúc**, chẳng hạn:

- Chỉ phát một thông báo khi transaction tạo đơn hàng đã **commit**.
- Ghi nhận hoặc dọn dẹp tài nguyên khi transaction **rollback**.
- Cập nhật trạng thái một file sau khi việc ghi database hoàn tất.
- Theo dõi kết quả giao dịch ở nhánh xử lý đồng bộ, poller hoặc listener.

**Transaction Synchronization** là cơ chế đăng ký các callback gắn với **vòng đời một transaction đang hoạt động**. Thay vì tự phỏng đoán xem một lệnh SQL có thực sự commit hay chưa, callback nhận được tín hiệu từ transaction manager tại những pha xác định.

Tuy nhiên, **callback không mở rộng phạm vi atomicity**. Chạy một lệnh gửi đến broker trong `afterCommit` có nghĩa lệnh gửi được thực hiện *sau* khi DB commit, chứ không làm broker cùng tham gia transaction DB. Nếu ứng dụng sập giữa DB commit và lúc gửi, event vẫn có thể bị mất.

Bài học này thuộc chương **Transactional messaging** trong module `SPRING_INTEGRATION_PATTERN`, với mục tiêu thiết kế Enterprise Integration Patterns ít phụ thuộc, dễ mở rộng, có thể theo dõi đường đi message và xử lý lỗi một cách rõ ràng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt transaction, transaction boundary và synchronization callback.
2. Hiểu thứ tự và ý nghĩa của `beforeCommit`, `beforeCompletion`, `afterCommit`, `afterCompletion`.
3. Đăng ký callback từ handler trong Spring Integration flow khi có transaction thật sự.
4. Hiểu cách transaction synchronization liên hệ tới polling endpoint, message store và các nhánh bất đồng bộ.
5. Dự đoán kết quả khi callback thất bại, transaction rollback hoặc process sập sau commit.
6. Chọn giữa callback sau commit, `@TransactionalEventListener` và transactional outbox; kiểm thử bằng failure injection.

## 2. Phân biệt transaction và transaction synchronization

| Khái niệm | Trách nhiệm | Điều không được tự suy ra |
| --- | --- | --- |
| **Transaction** | Gom các thao tác trên tài nguyên có tham gia để commit hoặc rollback theo cấu hình. | Mọi thao tác HTTP, broker, email đều nằm trong giao dịch JDBC. |
| **Transaction manager** | Bắt đầu, kết thúc giao dịch và điều phối tài nguyên thuộc phạm vi quản lý. | Một transaction manager cục bộ tự điều phối mọi database và broker. |
| **Transaction boundary** | Điểm bắt đầu và kết thúc transaction. | Boundary tự đi qua thread, channel bất đồng bộ hoặc service khác. |
| **Transaction synchronization** | Cho phép chạy callback tại các pha commit/rollback/completion của transaction. | Callback tự tạo transaction mới hoặc bảo đảm sẽ được chạy sau khi process sập. |
| **Acknowledgement (ACK)** | Xác nhận đã nhận/xử lý message theo hợp đồng nguồn/broker. | DB commit thì ACK chắc chắn cũng commit nguyên tử. |

Trong mô hình transaction imperative của Spring, thông tin transaction thường được gắn với **thread hiện tại**. Vì vậy:

- Handler chạy qua `DirectChannel` trên cùng thread có thể nhìn thấy transaction của caller.
- Handler chạy trên `ExecutorChannel` thường ở thread khác và không tự kế thừa transaction/synchronization.
- Message header như `correlationId` hoặc `sequenceNumber` không mang transaction sang downstream.
- Với broker hoặc remote service, mỗi bên phải xác định transaction và cơ chế ACK riêng.

Khi cần hành động "sau khi đơn hàng đã commit", transaction synchronization giúp chọn thời điểm; khi cần "event **không bị bỏ quên** nếu process sập", phải có cơ chế lưu bền vững như outbox.

## 3. Vòng đời callback chuẩn của Spring

Spring Framework cung cấp `TransactionSynchronization` và `TransactionSynchronizationManager`. Một synchronization thường được đăng ký trong **transaction đang hoạt động**; transaction manager sẽ gọi những phương thức tương ứng với trạng thái hoàn tất.

~~~mermaid
flowchart TD
    A["Bắt đầu transaction"] --> B["Flow thực hiện nghiệp vụ"]
    B --> C{"Kết thúc bằng commit?"}
    C -->|"Có"| D["beforeCommit(readOnly)"]
    D --> E["beforeCompletion()"]
    E --> F{"Commit tài nguyên thành công?"}
    F -->|"Có"| G["afterCommit()"]
    G --> H["afterCompletion(COMMITTED)"]
    F -->|"Không / kết quả không rõ"| U["afterCompletion(ROLLED_BACK hoặc UNKNOWN, tùy kết quả)"]
    C -->|"Rollback"| R["beforeCompletion()"]
    R --> S["Rollback tài nguyên"]
    S --> T["afterCompletion(ROLLED_BACK)"]
~~~

Sơ đồ mô tả ý nghĩa chính của từng pha. Chi tiết khi lỗi xảy ra hoặc transaction manager không biết chắc kết quả commit phụ thuộc tài nguyên và transaction manager cụ thể.

| Callback | Thời điểm | Ứng dụng hợp lý | Lưu ý |
| --- | --- | --- | --- |
| `beforeCommit(boolean readOnly)` | Trước khi transaction manager tiến hành commit. | Kiểm tra cuối cùng, đồng bộ state nội bộ khi phù hợp. | **Commit vẫn có thể thất bại** sau callback; exception có thể ngăn commit/đưa đến rollback. |
| `beforeCompletion()` | Trước khi kết thúc transaction, kể cả khi sắp rollback. | Dọn dẹp tài nguyên trong pha chuẩn bị hoàn tất. | Không thích hợp để phát sự kiện "đã commit"; exception ở đây thường được log theo xử lý của framework. |
| `afterCommit()` | Sau khi transaction đã commit thành công. | Gửi tín hiệu best-effort, xóa cache, kích hoạt công việc phụ. | Không thể rollback commit đã xảy ra; callback chưa chắc chạy được nếu process sập. |
| `afterCompletion(int status)` | Khi transaction kết thúc, với trạng thái commit/rollback/unknown. | Log/tracing, cleanup, release tài nguyên; phân biệt nhánh thành công/thất bại. | Không phải một transaction mới; ngoại lệ callback không biến commit thành rollback. |

Các hằng trạng thái thông dụng:

~~~java
TransactionSynchronization.STATUS_COMMITTED
TransactionSynchronization.STATUS_ROLLED_BACK
TransactionSynchronization.STATUS_UNKNOWN
~~~

**Không có phương thức `afterRollback()` trong interface `TransactionSynchronization` chuẩn.** Để xử lý riêng rollback, kiểm tra `status == STATUS_ROLLED_BACK` bên trong `afterCompletion(status)`. Một số abstraction của Spring Integration có khái niệm hook/expression "after rollback"; không được nhầm chúng với chữ ký của interface Spring Framework.

### Ba hiểu nhầm cần tránh

1. **`beforeCommit` không bảo đảm sau đó sẽ commit.** Lỗi commit, rollback-only hoặc sự cố tài nguyên có thể vẫn khiến transaction không thành công.
2. **`afterCommit` không nằm trong một transaction JDBC mới.** Tài nguyên có thể còn được bind trong giai đoạn callback; nếu cần một lần ghi DB có commit riêng, gọi một service thực sự mở **`REQUIRES_NEW`** qua Spring proxy.
3. **`afterCompletion(COMMITTED)` không có nghĩa broker đã nhận message.** Nó chỉ mô tả trạng thái transaction mà synchronization tham gia.

## 4. Vị trí transaction synchronization trong IntegrationFlow

Xét luồng xử lý đơn hàng:

~~~mermaid
flowchart LR
    A["CheckoutService @Transactional"] --> B["Messaging Gateway"]
    B --> C["DirectChannel"]
    C --> D["Filter / Transformer"]
    D --> E["Service Activator: lưu đơn"]
    E --> F["Register synchronization"]
    F --> G[("Orders DB")]
    G --> H{"Transaction hoàn tất"}
    H -->|"Commit"| I["afterCommit: send event"]
    H -->|"Rollback"| J["afterCompletion: cleanup"]
~~~

Đối với **DirectChannel**, handler được gọi đồng bộ trên thread của sender. Nếu application service đã mở transaction, handler có thể đăng ký synchronization vào **chính transaction đó**.

Ngược lại, nếu input chạy qua `ExecutorChannel` hoặc broker trước handler, transaction ban đầu **không tự đi cùng** message. Handler phải được gọi bên trong transaction mới do consumer, service hoặc polling endpoint mở.

Một synchronization đăng ký trong handler không nhất thiết chạy lúc handler trả về: nếu transaction do **outer service** quản lý, callback chỉ chạy **khi outer transaction thực sự hoàn tất**.

## 5. Ví dụ Java: gửi event sau khi DB commit

Giả sử bài thực hành dùng Spring Boot, Spring Integration Java DSL, Spring JDBC và một `DataSourceTransactionManager`/`JdbcTransactionManager` thích hợp. Bảng dữ liệu:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL,
    state VARCHAR(24) NOT NULL
);
~~~

Định nghĩa payload:

~~~java
record CreateOrder(String orderId, BigDecimal amount) {}
record OrderCreated(String eventId, String orderId) {}
~~~

Tạo Gateway và hai flow. `outboundEvents` được cấu hình thành `DirectChannel` trong ví dụ để minh họa thời điểm handler bên ngoài được gọi; việc publish tới broker thực tế do `OrderEventPublisher` triển khai:

~~~java
@MessagingGateway(defaultRequestChannel = "orderCommands")
interface OrderGateway {
    void create(CreateOrder command);
}

interface OrderEventPublisher {
    void publish(OrderCreated event);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OrderFlowConfig {
    @Bean("orderCommands")
    MessageChannel orderCommands() {
        return new DirectChannel();
    }

    @Bean("outboundEvents")
    MessageChannel outboundEvents() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow createOrderFlow(OrderWriter writer) {
        return IntegrationFlow.from("orderCommands")
                .handle(writer, "writeAndRegister")
                .get();
    }

    @Bean
    IntegrationFlow eventPublishFlow(OrderEventPublisher publisher) {
        return IntegrationFlow.from("outboundEvents")
                .handle(message -> publisher.publish(
                        (OrderCreated) message.getPayload()))
                .get();
    }
}
~~~

Application service sở hữu transaction:

~~~java
@Service
class CheckoutService {
    private final OrderGateway gateway;

    CheckoutService(OrderGateway gateway) {
        this.gateway = gateway;
    }

    @Transactional
    public void place(CreateOrder command) {
        gateway.create(command);
    }

    @Transactional
    public void placeThenFail(CreateOrder command) {
        gateway.create(command);
        throw new IllegalStateException("Simulated failure");
    }
}
~~~

Handler ghi DB, kiểm tra transaction rồi đăng ký synchronization:

~~~java
@Component
class OrderWriter {
    private final JdbcTemplate jdbc;
    private final MessageChannel outboundEvents;

    OrderWriter(
            JdbcTemplate jdbc,
            @Qualifier("outboundEvents") MessageChannel outboundEvents) {
        this.jdbc = jdbc;
        this.outboundEvents = outboundEvents;
    }

    public void writeAndRegister(CreateOrder command) {
        if (!TransactionSynchronizationManager.isActualTransactionActive()
                || !TransactionSynchronizationManager.isSynchronizationActive()) {
            throw new IllegalStateException(
                    "A real transaction with synchronization is required");
        }

        jdbc.update("""
                INSERT INTO orders(order_id, amount, state)
                VALUES (?, ?, ?)
                """,
                command.orderId(), command.amount(), "CREATED");

        // Sinh ID một lần cho sự kiện; không tạo ID mới mỗi lần retry publish.
        OrderCreated event = new OrderCreated(
                UUID.randomUUID().toString(), command.orderId());

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        boolean accepted = outboundEvents.send(
                                MessageBuilder.withPayload(event).build());
                        if (!accepted) {
                            throw new IllegalStateException(
                                    "outboundEvents rejected the event");
                        }
                    }

                    @Override
                    public void afterCompletion(int status) {
                        if (status ==
                                TransactionSynchronization.STATUS_ROLLED_BACK) {
                            // Có thể cleanup state nội bộ hoặc ghi metric.
                            // KHÔNG suy ra rằng mọi side effect bên ngoài
                            // đã được hoàn tác.
                        }
                    }
                });
    }
}
~~~

**Đường đi khi thành công:**

1. `CheckoutService.place()` được gọi qua Spring proxy và mở transaction.
2. Gateway gửi `CreateOrder` qua `DirectChannel` tới `OrderWriter` trên cùng thread.
3. Handler ghi `orders`, sau đó đăng ký synchronization vào transaction hiện hành.
4. Lời gọi handler và Gateway trở về; transaction của `place()` được commit.
5. Spring gọi `afterCommit()`. Khi ấy `outboundEvents.send()` mới chạy.
6. Spring hoàn tất lifecycle và gọi `afterCompletion(STATUS_COMMITTED)`.

Khi `placeThenFail()` ném exception phù hợp rollback rules, transaction DB rollback; callback `afterCommit()` **không được gọi**. Tuy nhiên, `afterCompletion(STATUS_ROLLED_BACK)` có thể được dùng cho cleanup hoặc quan sát.

### Điều kiện để ví dụ chạy đúng

- `@Transactional` cần thực sự được áp dụng qua Spring transaction interceptor, không gọi `this.place(...)` rồi kỳ vọng proxy có hiệu lực.
- `DirectChannel` cần còn đồng bộ; thay bằng executor có thể làm handler chạy ngoài transaction của `CheckoutService`.
- `JdbcTemplate` phải dùng datasource tham gia transaction manager.
- `OrderEventPublisher` là bean do ứng dụng cung cấp, được implement phù hợp broker/API thực tế.
- Ví dụ minh họa **best-effort send sau commit**; chưa đảm bảo event không thất lạc khi crash.

### Nếu không có transaction đang hoạt động?

`TransactionSynchronizationManager.isSynchronizationActive()` kiểm tra framework đang cho phép đăng ký synchronization, còn `isActualTransactionActive()` phản ánh một transaction thực sự đang hoạt động. Có những cấu hình propagation như `SUPPORTS` mà synchronization có thể active nhưng không có actual transaction; do đó ví dụ cố ý kiểm tra **cả hai** khi mục tiêu là callback sau **DB commit thật**.

Nếu một handler có thể được gọi trong cả hai trường hợp, phải chọn **chính sách có chủ đích**:

- Bắt buộc có transaction: từ chối như ví dụ; gọi qua application service hoặc handler có boundary phù hợp.
- Chấp nhận không có transaction: quyết định xử lý riêng cho nhánh không giao dịch, chẳng hạn gửi trực tiếp hoặc ghi outbox; không giả vờ đã đăng ký after-commit callback.

Không đăng ký callback khi transaction synchronization không hoạt động vì `registerSynchronization()` sẽ thất bại.

## 6. Callback thất bại thì DB có rollback không?

Lấy ví dụ `afterCommit()` gọi broker và broker trả lỗi mạng:

~~~text
INSERT order trong transaction   -> thành công
COMMIT DB                      -> thành công
afterCommit -> publish broker  -> thất bại
~~~

**Đơn hàng vẫn tồn tại trong database.** Exception từ `afterCommit()` có thể được truyền ra ngoài lời gọi giao dịch tùy callback và transaction manager, khiến caller tưởng `place()` thất bại dù dữ liệu đã commit. Nếu caller retry toàn bộ `place()`, có thể gặp duplicate key hoặc làm nghiệp vụ chạy lặp.

Vì vậy:

- Không coi exception xuất hiện sau commit là bằng chứng có thể rollback lại dữ liệu.
- Nếu retry ở sender, cần xác định kết quả commit trước đó hoặc thiết kế operation idempotent.
- Với sự kiện quan trọng, **ghi outbox trong cùng transaction** để có điểm phục hồi bền vững.
- Với tác vụ best-effort (ví dụ xóa cache, metric), callback có thể bắt và ghi nhận lỗi theo chính sách nghiệp vụ; không nuốt lỗi quan trọng một cách âm thầm.

### `beforeCommit()` có cứu được tính nguyên tử giữa DB và broker không?

Không. Nếu thực hiện external publish trong `beforeCommit()`, broker có thể đã nhận message nhưng database vẫn rollback do lỗi commit sau đó. Cả hai trường hợp đều tồn tại "khoảng hở":

| Thời điểm gửi tới broker | Nguy cơ chính |
| --- | --- |
| `beforeCommit()` | Message đã được gửi, nhưng database chưa commit và có thể rollback. |
| `afterCommit()` | Database đã commit, nhưng process có thể sập trước khi gửi. |
| `afterCompletion(COMMITTED)` | Cũng là hành động sau commit; không bảo đảm chạy được khi process sập. |
| **Outbox trong cùng DB transaction** | Ý định gửi được lưu cùng business data; có thể phát lại sau restart, nhưng publisher có thể gửi trùng. |

Vì vậy **transaction synchronization là công cụ điều phối thời điểm**, không phải cơ chế bảo đảm giao tin nguyên tử giữa các tài nguyên độc lập.

## 7. `afterCompletion` khi rollback và trạng thái không rõ

Một số logic chỉ cần thực hiện khi giao dịch thất bại:

~~~java
TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCompletion(int status) {
                if (status ==
                        TransactionSynchronization.STATUS_ROLLED_BACK) {
                    // Cleanup state tạm trong memory, ghi metric rollback.
                } else if (status ==
                        TransactionSynchronization.STATUS_COMMITTED) {
                    // Ghi metric commit hoặc release tài nguyên.
                } else {
                    // STATUS_UNKNOWN: chưa biết chắc trạng thái cuối.
                    // Cần reconcile bằng trạng thái lưu bền vững.
                }
            }
        });
~~~

**Rollback callback không phải transaction bù trừ.** Nếu handler đã gọi API đặt hàng bên ngoài trước rollback, after-completion không khiến lệnh gọi đó bị hoàn tác. Nếu cần compensation thực sự, phải lưu trạng thái và có cơ chế thực thi lại hành động bù trừ (thường là Saga hoặc job độc lập).

Khi trạng thái cuối là `STATUS_UNKNOWN`, không nên mặc định đã commit hay rollback. Có thể cần truy vấn database, kiểm tra transaction log hoặc dùng mã yêu cầu nghiệp vụ để reconcile; phụ thuộc cơ chế của resource manager.

### Ghi database trong `afterCommit` hoặc `afterCompletion`

Trong thời điểm gọi synchronization, một số resource có thể còn được Spring giữ/bind trên thread. Vì vậy việc dùng lại repository hoặc `JdbcTemplate` **không có nghĩa sẽ có một commit mới**. Nếu cần ghi log nghiệp vụ có transaction độc lập, gọi một **Spring bean khác** với propagation mới:

~~~java
@Service
class AuditRecordingService {
    private final JdbcTemplate jdbc;

    AuditRecordingService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String orderId, String result) {
        jdbc.update(
                "INSERT INTO order_tx_audit(order_id, result) VALUES (?, ?)",
                orderId, result);
    }
}
~~~

Lệnh `record(...)` là ví dụ giả định có bảng `order_tx_audit`. Bean đăng ký synchronization phải gọi **qua proxy** của `AuditRecordingService`. Việc dùng `this.record(...)` trong cùng bean có thể bỏ qua `@Transactional`. Dẫu vậy, audit ghi bằng transaction mới sau commit vẫn có rủi ro mất khi process chết; dùng outbox/audit trong transaction gốc nếu audit là dữ liệu bắt buộc.

## 8. Transaction synchronization tại polling endpoint

Trong Spring Integration, polling endpoint có thể được cấu hình để transaction bao quanh tác vụ polling và xử lý downstream **đồng bộ**:

~~~java
@Bean
IntegrationFlow workerFlow(
        PlatformTransactionManager transactionManager,
        OrderWriter writer) {
    return IntegrationFlow.from(
                    "workQueue",
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(1_000)
                                    .maxMessagesPerPoll(1)
                                    .transactional(transactionManager)))
            .handle(writer, "writeAndRegister")
            .get();
}
~~~

Đoạn code minh họa **boundary**; cần cấu hình `workQueue` và payload đầu vào tương thích với handler, và handler mẫu `writeAndRegister` yêu cầu payload `CreateOrder`. Với transactional poller:

1. Poller mở transaction theo advice cấu hình.
2. Poller nhận message từ `PollableChannel` hoặc source.
3. Handler downstream đồng bộ thực thi và có thể đăng ký synchronization.
4. Khi toàn bộ tác vụ trong boundary hoàn tất, Spring commit/rollback và gọi callback.

**Lưu ý nguồn message:** nếu `workQueue` là `QueueChannel` trong bộ nhớ, JDBC rollback không tự làm việc dequeue thành transactional. Callback `afterRollback` không tự trả phần tử về queue. Để phục hồi message sau crash, cần source có persistence/ack/redelivery phù hợp.

### Spring Integration có abstraction riêng cho synchronization

Ngoài `TransactionSynchronization` của Spring Framework, Spring Integration cung cấp các abstraction như `TransactionSynchronizationFactory`, `DefaultTransactionSynchronizationFactory` và `ExpressionEvaluatingTransactionSynchronizationProcessor` để đăng ký các xử lý theo pha trong một số kịch bản polling/adapter được hỗ trợ.

Ý tưởng thường là: **khi poll một tài nguyên**, giữ ngữ cảnh của dữ liệu vừa nhận rồi chạy biểu thức hoặc gửi đến channel tương ứng sau commit hoặc rollback. Điều này hữu ích với nguồn file hoặc những message source mà bạn muốn đánh dấu đã xử lý, đổi vị trí file hoặc thông báo lỗi theo kết quả giao dịch.

Ví dụ nghiệp vụ:

~~~text
Poll file import/orders-17.csv
    -> begin transaction
    -> parse/filter/transform rows
    -> insert orders into database
    -> commit DB transaction
    -> afterCommit: chuyển file sang processed/

Nếu rollback:
    -> afterCompletion(ROLLED_BACK) / hook rollback:
       giữ hoặc chuyển file sang khu vực retry/quarantine
       theo chính sách đã cấu hình
~~~

Trong cấu hình thực tế, phải xem API của phiên bản Spring Integration, cách adapter quản lý resource/message, các biểu thức post-commit, cùng transaction manager được dùng. Việc **move file** trên filesystem thông thường không thuộc JDBC transaction; callback có thể chạy thất bại sau khi DB đã commit. Thiết kế phải chịu được việc xử lý lặp khi file còn trong thư mục nguồn.

### Poller transaction và callback không thay thế ACK

Giả sử nhận message từ JMS hoặc Kafka:

- **Transaction của poller/handler** có thể rollback cập nhật database nếu handler thất bại.
- **Transaction hoặc acknowledgement của nguồn** quyết định message có được giao lại/offset có bị commit hay không.
- **Transaction synchronization** chạy callback theo lifecycle transaction đã đăng ký; nó không tự thay đổi chính sách redelivery của broker.

Đặc biệt, lỗi ở nhánh `ExecutorChannel` có thể xuất hiện **sau khi poller/listener kết thúc**. Callback của transaction trước đó không chờ công việc bất đồng bộ hoàn thành nếu không có cơ chế phối hợp riêng.

## 9. So sánh `@TransactionalEventListener` với synchronization trực tiếp

Spring Framework cũng hỗ trợ event listener gắn với transaction:

~~~java
@Service
class OrderService {
    private final ApplicationEventPublisher events;
    private final JdbcTemplate jdbc;

    OrderService(ApplicationEventPublisher events, JdbcTemplate jdbc) {
        this.events = events;
        this.jdbc = jdbc;
    }

    @Transactional
    public void create(String orderId) {
        jdbc.update(
                "INSERT INTO orders(order_id, amount, state) VALUES (?, ?, ?)",
                orderId, new BigDecimal("100.00"), "CREATED");

        events.publishEvent(new OrderCreated(
                UUID.randomUUID().toString(), orderId));
    }
}

@Component
class AfterCommitEventHandler {
    private final MessageChannel outboundEvents;

    AfterCommitEventHandler(
            @Qualifier("outboundEvents") MessageChannel outboundEvents) {
        this.outboundEvents = outboundEvents;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void publishAfterCommit(OrderCreated event) {
        outboundEvents.send(
                MessageBuilder.withPayload(event).build());
    }
}
~~~

Ở đây Spring application event được phát **trong** transaction; listener chạy theo pha được chỉ định khi transaction hoàn tất thành công. Theo mặc định, một `@TransactionalEventListener` không chạy nếu event được phát **ngoài** transaction, trừ khi cấu hình `fallbackExecution`. Nó không tự lưu event vào kho bền vững.

| Tiêu chí | `TransactionSynchronization` trực tiếp | `@TransactionalEventListener` |
| --- | --- | --- |
| Cách đăng ký | Gọi `TransactionSynchronizationManager.registerSynchronization(...)` trong code. | Publish application event và khai báo listener theo `TransactionPhase`. |
| Mục đích | Điều khiển trực tiếp callback, cleanup và status commit/rollback. | Tách code phát event với listener phản ứng theo pha giao dịch. |
| Quan sát rollback | `afterCompletion(status)`, kiểm tra hằng trạng thái. | Chọn `AFTER_ROLLBACK` hoặc `AFTER_COMPLETION` phù hợp. |
| Yêu cầu transaction | Phải có synchronization active; thường cần actual transaction cho ý nghĩa commit thật. | Thông thường listener chạy theo transaction gắn với event; có `fallbackExecution`. |
| Bảo đảm không mất event khi crash | Không. | Không. |
| Trường hợp phù hợp | Hook kỹ thuật, cleanup hoặc điều phối trong luồng. | Event nghiệp vụ tách lớp, hành động best-effort sau commit. |

**Không dùng đồng thời hai cơ chế chỉ để "chắc chắn hơn"**: nếu chúng cùng gửi một event, hệ thống có thể phát trùng từ chính code ứng dụng. Chọn một cơ chế nhất quán cho mỗi trách nhiệm.

## 10. Transactional outbox khi yêu cầu phát sự kiện bền vững

Với nghiệp vụ quan trọng, ta cần một cam kết mạnh hơn “nếu process còn sống sau commit thì cố gửi”. Giải pháp thường dùng là **transactional outbox**:

~~~mermaid
sequenceDiagram
    participant App as Order Service
    participant DB as Business DB + Outbox
    participant Relay as Outbox Publisher
    participant Broker as Broker
    participant Consumer as Consumer
    App->>DB: BEGIN
    App->>DB: INSERT orders
    App->>DB: INSERT outbox_events
    App->>DB: COMMIT cả hai
    Note over DB: Event pending đã bền vững
    Relay->>DB: Poll/claim PENDING
    Relay->>Broker: Publish eventId
    Broker-->>Relay: Publish confirmation
    Relay->>DB: Mark SENT
    Broker->>Consumer: Deliver eventId
    Consumer->>Consumer: Deduplicate eventId
~~~

Schema minh họa:

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(64) PRIMARY KEY,
    aggregate_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    payload_json TEXT NOT NULL,
    delivery_status VARCHAR(16) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Trong một `@Transactional` service, ghi business data **và** outbox row bằng cùng datasource:

~~~java
@Transactional
public void createOrder(CreateOrder command) {
    String eventId = UUID.randomUUID().toString();
    jdbc.update(
            "INSERT INTO orders(order_id, amount, state) VALUES (?, ?, ?)",
            command.orderId(), command.amount(), "CREATED");

    jdbc.update("""
            INSERT INTO outbox_events
              (event_id, aggregate_id, event_type,
               payload_json, delivery_status)
            VALUES (?, ?, ?, ?, ?)
            """,
            eventId,
            command.orderId(),
            "OrderCreated",
            serializeOrderCreated(eventId, command.orderId()),
            "PENDING");
}
~~~

Ví dụ giả định có hàm `serializeOrderCreated(...)` và bean `jdbc` trong service. Khi transaction rollback, cả order và outbox đều không commit; khi commit, outbox còn đó để relay gửi sau khi app khởi động lại.

**Outbox vẫn có thể publish trùng**: broker có thể nhận sự kiện thành công nhưng relay sập trước khi đánh dấu `SENT`. Vì thế phải có định danh sự kiện cố định (`eventId`) và consumer **idempotent**, ví dụ bảng `processed_events` có unique constraint và cập nhật nghiệp vụ cùng transaction.

Trong kiến trúc này, transaction synchronization có thể dùng làm **tín hiệu đánh thức relay sau commit** để giảm độ trễ; nhưng **outbox record mới là nguồn sự thật** để khôi phục nếu tín hiệu callback bị mất. Relay vẫn phải có lịch polling độc lập hoặc cơ chế khôi phục tương đương.

## 11. Error channel, retry và các nhánh bất đồng bộ

Các pattern làm flow dễ đọc nhưng cũng tạo nhiều điểm thay đổi boundary:

~~~mermaid
flowchart LR
    A["Gateway"] --> B["DirectChannel"]
    B --> C["Filter / Transformer"]
    C --> D{"Router"}
    D --> E["JDBC handler + callback"]
    D --> F["ExecutorChannel"]
    F --> G["Async worker"]
    E --> H["Transaction hoàn tất"]
    G --> I["Transaction riêng ở worker"]
    I --> J["Aggregator / error channel"]
~~~

### Lỗi được bắt ở đâu?

- **DirectChannel:** handler thường chạy đồng bộ. Nếu exception đi ngược lên `@Transactional` service, transaction có thể rollback; callback `afterCommit` sẽ không chạy.
- **ExecutorChannel:** handler có thể lỗi khi caller đã trả về. Callback của transaction trên thread caller không tự biết kết quả worker.
- **Error channel:** `ErrorMessage` có thể đến một error flow riêng. Việc một handler tiêu thụ lỗi rồi return bình thường **có thể làm transaction/container coi tác vụ thành công**. Cần kiểm tra exception nào thực sự thoát khỏi boundary.
- **Retry advice:** nếu retry được đặt bên ngoài boundary transaction, mỗi lần thử có thể mở transaction mới; nếu retry nằm *bên trong* một transaction đã `rollback-only`, retry cùng connection có thể không thành công. Kiểm tra thứ tự advice.
- **Splitter/Aggregator:** correlation giúp ghép kết quả, nhưng không làm nhiều transaction ở các nhánh thành một giao dịch nguyên tử; aggregator phải xử lý timeout, duplicate và state bền vững khi cần.

### Trường hợp callback đăng ký rồi retry

Giả sử handler ghi DB, đăng ký `afterCommit` và sau đó gặp lỗi:

1. Nếu transaction **rollback**, callback `afterCommit` của lần thử đó không chạy.
2. Lần retry mở **transaction mới** có thể đăng ký callback mới.
3. Nếu nhiều message hoặc handler cùng đăng ký callback trong một transaction, có thể có **nhiều callback** lúc commit; phải kiểm soát theo event ID và tránh phát trùng.
4. Nếu commit thành công nhưng callback send lỗi, retry toàn bộ đơn hàng có thể lặp business action; cần outbox hoặc cơ chế idempotency.

Không tạo ID mới mỗi lần retry publish của **cùng một event**. `messageId` của Spring Integration, `correlationId` nhóm công việc, và `eventId` để dedupe có mục đích khác nhau.

## 12. Kiểm thử transaction synchronization

Kiểm thử có ích nhất là kiểm chứng **thời điểm callback chạy** và **dữ liệu thực sự đã commit/rollback**.

### Kiểm thử bằng bộ ghi sự kiện giả

Giả sử `OrderEventPublisher` được thay bằng bean giả lưu các `eventId` nhận được vào bộ nhớ, và service/flow giống phần 5:

~~~java
@SpringBootTest
class OrderSynchronizationIT {
    @Autowired CheckoutService checkout;
    @Autowired JdbcTemplate jdbc;
    @Autowired RecordingPublisher publisher;

    @Test
    void sendsOnlyAfterSuccessfulCommit() {
        String orderId = UUID.randomUUID().toString();

        checkout.place(new CreateOrder(
                orderId, new BigDecimal("125.00")));

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders WHERE order_id = ?",
                Integer.class, orderId);
        assertEquals(1, rows);
        assertTrue(publisher.containsOrder(orderId));
    }

    @Test
    void skipsAfterCommitOnRollback() {
        String orderId = UUID.randomUUID().toString();

        assertThrows(IllegalStateException.class,
                () -> checkout.placeThenFail(new CreateOrder(
                        orderId, new BigDecimal("125.00"))));

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders WHERE order_id = ?",
                Integer.class, orderId);
        assertEquals(0, rows);
        assertFalse(publisher.containsOrder(orderId));
    }
}
~~~

`RecordingPublisher` là test double của `OrderEventPublisher`, do bài thực hành cài đặt và đăng ký qua Spring test configuration. Test giả định có schema database phù hợp và state của publisher được cô lập giữa các test. Không nên đặt `@Transactional` trên **chính test** nếu việc này bao trùm transaction của service và che đi thời điểm commit thực tế.

Để kiểm thử **thứ tự**, có thể dùng fake publisher truy vấn `orders` ngay khi nhận event: khi nhận tại `afterCommit`, nó phải nhìn thấy bản ghi đã commit trên một connection/transaction kiểm thử độc lập, phù hợp isolation. Tránh cho fake thực thi chung transaction chưa commit của caller vì sẽ tạo kết luận sai.

### Ma trận failure injection

| Kịch bản | Quan sát cần kiểm tra | Kết luận |
| --- | --- | --- |
| `@Transactional` service ghi DB rồi rollback | `afterCommit` không gửi; `afterCompletion` có status rollback. | Callback gắn với transaction thật. |
| `beforeCommit` ném runtime exception | DB không commit theo rollback rules và xử lý của manager. | before-commit có thể ngăn commit; không có event "committed". |
| DB commit xong, `afterCommit` gọi broker thất bại | DB vẫn có row; caller có thể quan sát lỗi. | Error sau commit không hoàn tác DB. |
| App sập ngay sau DB commit trước callback | Event từ callback có thể không gửi. | Cần durable outbox nếu yêu cầu không thất lạc. |
| Flow chuyển sang `ExecutorChannel` | Callback phía sender có thể chạy trước handler worker. | Cần transaction và tracking riêng ở worker. |
| Transactional poller đọc queue in-memory rồi lỗi | DB rollback nhưng message không mặc định được requeue. | Synchronization không thay thế source transaction. |
| Outbox relay gửi rồi crash trước đánh dấu `SENT` | Có thể gửi lại event sau restart. | Consumer phải idempotent. |
| Một transaction đăng ký hai callback publish cùng event | Có thể nhận trùng. | Cần chính sách đăng ký một lần/deduplication. |

Với broker thật, bổ sung kiểm thử ACK/redelivery, DLQ, backoff và lỗi bất đồng bộ. Trong telemetry, nên phân biệt timestamp `message_received`, `db_commit`, `after_commit_hook`, `send_accepted`, `broker_confirmed`, `consumer_processed`.

## 13. Hướng dẫn chọn cơ chế

| Yêu cầu | Cách giải quyết | Bảo đảm và giới hạn |
| --- | --- | --- |
| Cleanup bộ nhớ hay giải phóng tài nguyên khi transaction kết thúc | `afterCompletion(status)` | Phù hợp với công việc kỹ thuật cục bộ; không bền vững trước crash. |
| Chỉ xóa cache khi dữ liệu đã commit | `afterCommit` hoặc event listener `AFTER_COMMIT` | Cache invalidation có thể bị bỏ lỡ nếu app sập; cân nhắc TTL/reconciliation. |
| Phát notification không bắt buộc sau commit | `@TransactionalEventListener(AFTER_COMMIT)` hoặc callback. | Best-effort, cần rõ cách log/metric khi send fail. |
| Phát event nghiệp vụ quan trọng không được bỏ quên | Transactional outbox + relay + idempotent consumer. | Có thể publish lặp; phải quản lý retry, backlog và dead-letter. |
| Di chuyển file sau khi poll và ghi DB | Transaction synchronization của poller/adapter nếu được hỗ trợ. | Filesystem move không tự rollback cùng DB; cần replay an toàn. |
| Nhận từ broker và ghi DB | Consumer transaction + ACK/redelivery phù hợp; idempotent inbox. | Broker transaction và DB transaction không tự nguyên tử với nhau. |
| Router/Splitter xử lý nhiều nhánh async | Transaction riêng cho từng worker + correlation + durable state. | Callback ở nhánh này không phản ánh kết quả commit của nhánh khác. |

### Quy tắc đặt callback

**Callback phải được đăng ký trong transaction sở hữu dữ liệu mà callback đang quan tâm.** Đăng ký quá sớm ở một transaction không liên quan hoặc quá muộn sau khi transaction đã hoàn tất khiến callback không còn đúng về mặt nghiệp vụ.

Đối với `REQUIRES_NEW`, callback đăng ký bên trong transaction con sẽ chạy khi **transaction con** hoàn tất; điều đó không đồng nghĩa transaction bao ngoài sẽ commit. Hãy xác định rõ có muốn đồng bộ với **inner transaction** hay **outer business transaction**.

Nếu một callback chỉ nên chạy một lần cho toàn bộ giao dịch, cần bảo đảm code không đăng ký trùng khi flow có nhiều handler/route. Khi nhiều synchronization cùng chạy, có thể cân nhắc thứ tự thực thi theo contract `Ordered` nếu thực sự có phụ thuộc, nhưng tránh thiết kế nghiệp vụ yêu cầu thứ tự callback phức tạp khó kiểm thử.

## 14. Bài tập vận dụng

**Bài 1 — Truy dấu thời điểm callback.** Vẽ timeline `CheckoutService @Transactional → Gateway → DirectChannel → JDBC handler → commit → afterCommit`. Thêm một Filter bỏ message hợp lệ, một Transformer ném `RuntimeException` và một handler bắt exception rồi return; dự đoán khi nào commit/rollback.

**Bài 2 — Đổi sang ExecutorChannel.** Thay `DirectChannel` bằng `ExecutorChannel`. Kiểm tra transaction active trong worker, thứ tự caller commit và worker xử lý, và cách xử lý lỗi khi worker thất bại sau khi callback phía caller đã hoàn tất.

**Bài 3 — Gửi sau commit không bảo đảm durable.** Dùng fake publisher gây exception trong `afterCommit`. Quan sát DB đã commit nhưng caller thấy lỗi. Đề xuất cách tránh retry tạo đơn trùng, rồi thay gửi trực tiếp bằng outbox.

**Bài 4 — Poll file và chuyển thư mục.** Cấu hình polling flow đọc file, ghi DB, và chỉ sau commit mới chuyển file sang thư mục `processed`. Giả lập lỗi move file ngay sau DB commit; dùng business ID/idempotency để lần poll tiếp theo không tạo dữ liệu trùng.

**Bài 5 — Phân nhánh và Aggregator.** Dùng Router/Splitter gửi hai tác vụ bất đồng bộ có cùng `correlationId`. Mỗi nhánh lưu kết quả bằng transaction riêng, aggregator chờ đủ kết quả. Xác định điều gì xảy ra nếu một nhánh rollback và kết quả nhánh kia đã commit.

### Câu hỏi tự đánh giá

**1. `afterCommit()` thất bại có làm JDBC transaction rollback không?** Không. Giai đoạn commit đã hoàn thành; lỗi callback không quay ngược được kết quả commit.

**2. Vì sao `beforeCommit()` chưa đủ để bảo đảm message hợp lệ sau commit?** Vì commit DB vẫn có thể thất bại sau callback; external message gửi trước đó có thể đã được nhận.

**3. Có thể dùng `afterRollback()` trực tiếp trên `TransactionSynchronization` không?** Không. Dùng `afterCompletion(status)` và kiểm tra `STATUS_ROLLED_BACK`; các abstraction riêng có thể cung cấp hook rollback khác.

**4. Trong flow có `ExecutorChannel`, callback đăng ký ở caller có chờ worker hoàn tất không?** Không mặc định. Transaction kiểu thread-bound không truyền tự động sang worker.

**5. Khi nào dùng outbox thay vì after-commit callback?** Khi event nghiệp vụ phải có khả năng khôi phục và phát lại sau process crash, cần ghi ý định gửi vào cùng transaction với dữ liệu nguồn.

## 15. Checklist trước khi vận hành

- [ ] Vẽ rõ transaction boundary và xác định ai sở hữu commit/rollback.
- [ ] Phân biệt `isSynchronizationActive()` với `isActualTransactionActive()` khi cần DB transaction thật.
- [ ] Chỉ đăng ký synchronization vào transaction liên quan, tránh đăng ký trùng.
- [ ] Biết callback nào chạy ở commit, rollback và trạng thái không chắc chắn.
- [ ] Không coi `beforeCommit` là bằng chứng DB sẽ commit.
- [ ] Không dùng `afterCommit` làm cam kết event chắc chắn được giao tới broker.
- [ ] Nếu ghi thêm DB ở callback, dùng transaction mới thực sự khi cần và xác định cách phục hồi sau crash.
- [ ] Kiểm tra các điểm chuyển thread qua `ExecutorChannel`, queue, broker và transaction của consumer.
- [ ] Với polling flow, xác định resource/source có tham gia transaction và hỗ trợ redelivery hay không.
- [ ] Cấu hình retry, error channel, DLQ, idempotency và theo dõi event ID/correlation ID.
- [ ] Với event quan trọng, có outbox, relay có thể restart, unique event ID và consumer idempotent.
- [ ] Kiểm thử failure injection trước commit, sau commit trước callback, trong callback và ở từng nhánh async.

**Ghi nhớ:** **Transaction synchronization quyết định *khi nào* một hook được gọi**, còn transaction manager và tài nguyên quyết định **cái gì có thể commit/rollback cùng nhau**. Trong Spring Integration, sự kết hợp của các pattern giúp flow dễ mở rộng nhưng mỗi điểm polling, executor và broker đều có thể tạo một ranh giới mới; hãy chọn callback, transaction và chiến lược redelivery tương ứng với yêu cầu độ tin cậy thật sự.
