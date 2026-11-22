# Transactional Channel và transaction boundary trong Spring Integration

## 1. Vấn đề cần giải quyết

Trong hệ thống tích hợp, một thông điệp thường đi qua nhiều **Enterprise Integration Patterns (EIP)**: Gateway tiếp nhận yêu cầu, Filter kiểm tra điều kiện, Transformer chuẩn hóa dữ liệu, Router chọn nhánh, rồi Service Activator ghi cơ sở dữ liệu hoặc gửi tới hệ thống khác. Câu hỏi quan trọng là: **khi một bước thất bại, những bước nào được hoàn tác và thông điệp nào có thể được xử lý lại?**

Ví dụ với đơn hàng:

1. Ứng dụng nhận lệnh đặt hàng và kiểm tra tính hợp lệ.
2. Lưu đơn vào cơ sở dữ liệu.
3. Phát sự kiện `OrderCreated` cho dịch vụ kho.
4. Dịch vụ kho cập nhật tồn kho, sau đó gửi kết quả về để tổng hợp.

Nếu bước 2 thành công nhưng bước 3 thất bại, có thể xuất hiện đơn hàng không có sự kiện tương ứng. Nếu bước 3 thành công nhưng ứng dụng sập trước khi ghi nhận đã gửi, lần gửi lại có thể tạo sự kiện trùng. **Transactional messaging** là việc thiết kế luồng sao cho ranh giới commit/rollback, xác nhận nhận thông điệp, retry và xử lý trùng lặp đều được xác định rõ.

Trong Spring Integration, **Transactional Channel** nên được hiểu như *một cách tổ chức việc gửi/nhận và xử lý thông điệp có phối hợp với giao dịch của tài nguyên*, chứ không phải thuộc tính tự động biến mọi `MessageChannel` thành giao dịch xuyên hệ thống. **Transaction boundary** là điểm bắt đầu và kết thúc một giao dịch cụ thể, thường gắn với một `PlatformTransactionManager` và một hoặc một nhóm tài nguyên được cấu hình tham gia.

Sau bài này, người học có thể:

- Xác định bước nào thực sự nằm trong cùng transaction khi luồng đi qua `DirectChannel`, `ExecutorChannel` hoặc kênh polling.
- Đặt transaction tại service gọi Gateway hoặc tại polling endpoint và dự đoán kết quả khi handler ném exception.
- Phân biệt rollback cơ sở dữ liệu với việc hoàn lại một thông điệp đã lấy khỏi queue hoặc đã xác nhận với broker.
- Thiết kế retry, error channel, idempotency và transactional outbox cho luồng đa hệ thống.
- Kiểm thử các tình huống commit, rollback, xử lý lặp và lỗi tại ranh giới giao dịch.

## 2. Transaction bao phủ tài nguyên nào?

Một transaction thông thường bảo đảm các thao tác **cùng tham gia giao dịch đó** có kết quả nhất quán: hoặc commit, hoặc rollback. Ví dụ, hai lệnh SQL dùng cùng `DataSource` và transaction manager thích hợp có thể commit/rollback cùng nhau. Việc gọi HTTP, gửi email hoặc publish thông điệp sang broker **không tự động** tham gia transaction JDBC chỉ vì các thao tác nằm trong cùng một phương thức Java.

Hãy tách ba khái niệm:

| Khái niệm | Ý nghĩa | Không bảo đảm điều gì? |
| --- | --- | --- |
| **Transaction boundary** | Phạm vi một giao dịch, có điểm bắt đầu, commit hoặc rollback và tài nguyên tham gia. | Không tự mở rộng qua thread, process hay broker. |
| **Message delivery boundary** | Điểm thông điệp được chuyển cho handler khác, hàng đợi hoặc hệ thống khác. | Việc `send()` thành công không nhất thiết có nghĩa nghiệp vụ downstream đã commit. |
| **Acknowledgement boundary** | Điểm nguồn/broker xác nhận đã tiêu thụ thông điệp. | ACK không đồng nghĩa với commit của một cơ sở dữ liệu khác nếu không có cơ chế phối hợp. |

Trong các luồng transaction dạng imperative phổ biến của Spring, trạng thái transaction được liên kết với **thread đang thực thi**. Metadata như `MessageHeaders.ID`, `correlationId` hoặc `sequenceNumber` giúp định danh và ghép thông điệp, nhưng **không mang theo một JDBC transaction** sang thread hay dịch vụ khác.

### Hai sơ đồ để nhận biết ranh giới

**Luồng đồng bộ: toàn bộ handler có thể cùng nằm trong một transaction JDBC.**

~~~mermaid
flowchart LR
  subgraph TX["TX-A: cùng thread, cùng JDBC transaction"]
    A["OrderService @Transactional"] --> B["Messaging Gateway"]
    B --> C["DirectChannel"]
    C --> D["Filter / Transformer"]
    D --> E["Service Activator"]
    E --> F[("Orders DB")]
  end
  E -. "Exception truyền ngược" .-> A
~~~

Nếu thao tác ghi DB ở `E` thất bại và exception truyền tới lời gọi `@Transactional`, transaction có thể rollback (theo rollback rules). `DirectChannel` không lưu lại thông điệp; sau rollback, **bên gọi hoặc nguồn phát phải quyết định retry**.

**Luồng bất đồng bộ: một lần giao thông điệp thường tạo ra ranh giới mới.**

~~~mermaid
flowchart LR
  subgraph TX1["TX-A: thread tiếp nhận"]
    A["Gateway"] --> B["Transformer"]
    B --> C["Gửi tới ExecutorChannel"]
  end
  C -. "handoff sang thread khác" .-> D["Worker nhận message"]
  subgraph TX2["TX-B nếu worker tự mở transaction"]
    D --> E["Service Activator"]
    E --> F[("Orders DB")]
  end
~~~

`TX-A` không tự đi vào worker. Nếu worker dùng `@Transactional` hoặc một transactional poller, đó là **transaction khác**. Kết thúc thành công của lời gọi gửi ở phía trước không phải bằng chứng rằng worker đã xử lý xong.

## 3. Hành vi giao dịch theo loại channel

| Thành phần trong Spring Integration | Cách xử lý | Hệ quả với transaction |
| --- | --- | --- |
| `DirectChannel` | Dispatcher gọi subscriber **đồng bộ** trên thread của người gửi. | Handler có thể dùng transaction đã mở bởi caller; exception thường truyền ngược ngay. |
| `PublishSubscribeChannel` **không** cấu hình executor | Phát tới subscriber trong luồng gọi đồng bộ. | Các handler có thể cùng transaction nếu sử dụng cùng tài nguyên; một nhánh thất bại chỉ dẫn tới rollback nếu lỗi được truyền ra và chính sách rollback áp dụng. |
| `ExecutorChannel` | Chuyển việc cho `TaskExecutor`, thường ở thread khác. | Transaction kiểu thread-bound của caller không tự được truyền sang handler; cần boundary riêng. |
| `QueueChannel` trong bộ nhớ | `send` đưa message vào queue; poller lấy ra sau. | Queue mặc định không bền vững và không tự tham gia JDBC transaction; rollback DB không đồng nghĩa với tự đưa message trở lại queue. |
| Polling endpoint | Định kỳ nhận message từ `PollableChannel` hoặc nguồn polling. | Có thể đặt transactional advice/poller bao quanh lần poll và xử lý downstream đồng bộ. Phải kiểm tra **nguồn** có tham gia transaction đó không. |
| Queue có persistent `MessageStore` phù hợp | Lưu thông điệp trong hệ lưu trữ có thể giao dịch. | Có thể phối hợp lấy message và ghi dữ liệu trong cùng transaction DB nếu store, business repository, datasource và transaction manager được cấu hình tương thích. |
| JMS/AMQP/Kafka adapter | Nhận hoặc gửi thông điệp qua broker với cơ chế ACK/transaction riêng. | Phụ thuộc adapter, container, chế độ ACK và transaction manager; transaction broker không mặc nhiên là transaction của DB. |

**Quy tắc thực hành:** xác định *nguồn phát*, *kiểu channel*, *thread thực thi*, *nguồn lưu message*, *transaction manager* và *điểm ACK*. Chỉ sau đó mới kết luận thất bại có làm hoàn tác hoặc phát lại message hay không.

### Kiểm tra nhanh một luồng

Giả sử `Gateway → DirectChannel → Filter → Transformer → Service Activator → JDBC`, với service gọi Gateway được đánh dấu `@Transactional`:

- Filter từ chối bằng cách trả về `null` hoặc loại message theo logic thông thường có thể kết thúc xử lý **thành công**, nên DB transaction có thể commit. "Message bị lọc" không nhất thiết là lỗi giao dịch.
- Transformer ném `RuntimeException` và lỗi truyền về service: giao dịch JDBC thường rollback.
- Service Activator bắt exception rồi chỉ ghi log mà không ném lại: transaction interceptor có thể coi lời gọi đã thành công và commit.
- Thêm `ExecutorChannel` trước handler JDBC: handler chạy ở thread khác; transaction của service gọi Gateway không bao phủ lệnh ghi bên worker.
- Router phát sang một service từ xa: phải thiết kế giao dịch của service nhận độc lập; cùng `correlationId` không tạo giao dịch phân tán.

## 4. Ví dụ 1 — một transaction bao phủ Gateway và DirectChannel

Ví dụ dùng Spring Boot, Spring Integration Java DSL và Spring JDBC. Giả sử ứng dụng đã cấu hình một `DataSource` cùng `PlatformTransactionManager` cho bảng sau:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL
);
~~~

Khai báo message, Gateway và integration flow đồng bộ:

~~~java
record OrderCommand(String orderId, BigDecimal amount) {}

@MessagingGateway(defaultRequestChannel = "ordersInput")
interface OrderGateway {
    void submit(OrderCommand command);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OrderIntegrationConfig {
    @Bean
    MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderFlow(OrderWriter writer) {
        return IntegrationFlow.from("ordersInput")
                .handle(writer, "insert")
                .get();
    }
}

@Component
class OrderWriter {
    private final JdbcTemplate jdbc;

    OrderWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(OrderCommand command) {
        jdbc.update(
                "INSERT INTO orders (order_id, amount) VALUES (?, ?)",
                command.orderId(), command.amount());
    }
}
~~~

`@MessagingGateway` tạo điểm vào có kiểu dữ liệu rõ ràng, `DirectChannel` giao message trên cùng thread và `.handle(writer, "insert")` gọi phương thức của Spring bean. Mở transaction ở **application service** gọi Gateway:

~~~java
@Service
class OrderFacade {
    private final OrderGateway gateway;

    OrderFacade(OrderGateway gateway) {
        this.gateway = gateway;
    }

    @Transactional
    public void submit(OrderCommand command) {
        gateway.submit(command);
    }

    // Dùng trong kiểm thử để chứng minh INSERT sẽ rollback.
    @Transactional
    public void submitThenFail(OrderCommand command) {
        gateway.submit(command);
        throw new IllegalStateException("Simulated failure");
    }
}
~~~

**Vòng đời một lời gọi `facade.submit(command)` từ bên ngoài Spring bean:**

1. Spring transaction interceptor bắt đầu transaction DB trước khi chạy `submit`.
2. Gateway gửi thông điệp vào `ordersInput`.
3. `DirectChannel` gọi handler cùng thread. `JdbcTemplate` dùng kết nối đã tham gia transaction.
4. Khi lời gọi trở về thành công, interceptor commit transaction; nếu lỗi phù hợp rollback rules thoát ra ngoài, interceptor rollback.

Với `submitThenFail`, bản ghi đã `INSERT` sẽ bị rollback dù câu lệnh SQL được thực thi *trước* khi exception xuất hiện. Ngược lại, khi dùng `ExecutorChannel` giữa Gateway và handler, `submitThenFail` có thể rollback transaction phía caller trong khi công việc ở worker đã hoặc sẽ commit ở transaction khác.

Lưu ý:

- `@Transactional` của Spring mặc định rollback cho `RuntimeException` và `Error`; checked exception cần cấu hình `rollbackFor` nếu muốn rollback. Quy tắc này phải được xét cùng các thiết lập transaction thực tế.
- Method `@Transactional` phải được gọi qua proxy/interceptor thích hợp. Lời gọi nội bộ kiểu `this.submit(...)` thường bỏ qua transaction advice của Spring proxy.
- Nếu có nhiều transaction manager, chỉ rõ manager tương ứng với `DataSource` cần dùng; nếu các bước JDBC dùng các datasource khác nhau thì không được suy rằng chúng cùng giao dịch.
- Một lần ghi DB thành công trong handler chưa phải là **commit**: commit diễn ra khi boundary của transaction kết thúc thành công.

### Khi nào cần transaction ở handler?

Nếu Gateway được gọi từ một nơi **không** có transaction và handler cần bảo vệ thao tác DB của riêng nó, có thể đặt `@Transactional` trên một Spring service chuyên xử lý. Khi `DirectChannel` đồng bộ, transaction sẽ mở tại service đó. Cần hiểu rằng transaction lúc này chỉ bao phủ đoạn xử lý bên trong handler; những bước trước đó đã hoàn thành ở ngoài boundary của handler.

## 5. Ví dụ 2 — transaction bắt đầu ở poller

Polling thường phù hợp khi lấy công việc từ hàng đợi hoặc message store. Có thể khai báo transactional poller như sau (đã lược bỏ import và cấu hình datasource):

~~~java
@Bean
QueueChannel workQueue() {
    return new QueueChannel(100);
}

@Bean
IntegrationFlow workerFlow(
        OrderWriter writer,
        PlatformTransactionManager transactionManager) {
    return IntegrationFlow.from(
                    "workQueue",
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(1000)
                                    .maxMessagesPerPoll(1)
                                    .transactional(transactionManager)))
            .handle(writer, "insert")
            .get();
}
~~~

Trong ví dụ này, transactional advice mở transaction cho tác vụ polling và xử lý downstream đồng bộ. Vì `maxMessagesPerPoll(1)`, mỗi lần poll xử lý tối đa một message, khiến phạm vi kiểm thử và phân tích lỗi dễ hiểu hơn. Nếu `OrderWriter.insert` ném exception, thao tác JDBC có thể rollback.

**Bẫy quan trọng:** `workQueue()` bên trên là `QueueChannel` **trong bộ nhớ**. Transaction JDBC không làm thao tác lấy phần tử từ bộ nhớ thành giao dịch. Sau lỗi, không được mặc định kỳ vọng message tự quay lại queue. Cũng không được dựa vào ví dụ này cho bảo đảm không mất message khi process sập.

Muốn có khả năng phục hồi, cần một nguồn thông điệp hỗ trợ cơ chế tương ứng:

- **JDBC-backed message store:** dùng persistent store có ngữ nghĩa giao dịch phù hợp và cấu hình lấy message/ghi nghiệp vụ cùng một `DataSource`/transaction manager khi cần atomicity trong *một* DB. Kiểm tra việc khóa, lấy và xóa message của loại store và channel cụ thể.
- **Broker:** dùng listener container/adapter và chế độ transaction/ACK được hỗ trợ để lỗi có thể kích hoạt redelivery từ broker. Kiểm tra các cài đặt như prefetch, requeue, redelivery và DLQ theo broker.
- **External API:** polling qua HTTP hoặc API không có rollback tự nhiên; thường phải dùng checkpoint, durable cursor, retry và idempotency.

`transactional(poller)` chỉ có ý nghĩa với **các tài nguyên thật sự tham gia transaction**. Nó không tự cung cấp tính bền vững cho queue in-memory, không đưa transaction sang thread khác và không làm một remote API có khả năng rollback.

## 6. Ranh giới giữa database và message broker

Giả sử handler cần vừa ghi `orders` vào PostgreSQL, vừa publish `OrderCreated` tới RabbitMQ/Kafka/JMS. Đây là bài toán **dual write**:

| Thứ tự thao tác | Điểm xảy ra lỗi | Trạng thái có thể xuất hiện |
| --- | --- | --- |
| Commit DB rồi publish event | Process sập sau commit, trước publish | Có đơn hàng nhưng thiếu sự kiện. |
| Publish event rồi commit DB | DB rollback sau khi broker đã nhận event | Có sự kiện cho đơn chưa được commit. |
| Publish, sau đó ghi "đã gửi" vào DB | Broker đã nhận nhưng process sập trước khi đánh dấu | Lần chạy lại có thể publish trùng. |

`@Transactional` của JDBC chỉ giải quyết phần JDBC. Một transaction phía broker (hoặc cơ chế ACK của consumer) chỉ giải quyết phần mà broker hỗ trợ. Muốn phối hợp **atomic commit thật sự giữa nhiều tài nguyên**, phải đánh giá khả năng của XA/JTA, adapter, driver và broker; chi phí và mức hỗ trợ phụ thuộc hạ tầng. Không nên mặc định Spring Integration làm các tài nguyên này cùng commit chỉ vì nằm trong một IntegrationFlow.

### Transactional outbox: lựa chọn thường dùng cho dual write

Để tránh tình huống **DB đã commit nhưng sự kiện bị bỏ quên**, ghi dữ liệu nghiệp vụ và bản ghi outbox trong **cùng một transaction DB**:

~~~mermaid
flowchart LR
  subgraph DBTX["Transaction DB: commit hoặc rollback cùng nhau"]
    A["Lưu Orders"] --> B["Lưu OutboxEvent"]
  end
  B --> C[("Outbox table")]
  C --> D["Outbox publisher / poller"]
  D --> E["Message broker"]
  E --> F["Consumer idempotent"]
~~~

~~~java
@Transactional
public void placeOrder(OrderCommand command) {
    ordersRepository.insert(command);
    outboxRepository.insert(
            command.orderId(),
            "OrderCreated",
            serializeEvent(command));
}
~~~

Phần publisher đọc các bản ghi outbox chưa gửi, publish sang broker rồi đánh dấu đã gửi theo chiến lược phù hợp. Nếu publisher sập sau khi broker nhận nhưng trước lúc đánh dấu, bản ghi có thể được publish lại. Do đó outbox thường hướng tới **at-least-once delivery** và cần consumer **idempotent** (ví dụ lưu `eventId` đã xử lý, có unique constraint, hoặc cập nhật theo trạng thái có kiểm tra).

Outbox tạo atomicity giữa **orders** và **outbox** trong cùng DB; nó **không** tạo một transaction phân tán bao phủ DB và broker. Đây là lý do cần cả khả năng phát lại lẫn chống xử lý trùng.

### Transaction của consumer và ACK

Một consumer có thể đi theo trình tự:

1. Nhận thông điệp từ broker, giữ thông tin delivery/offset.
2. Bắt đầu transaction DB và xử lý message (kiểm tra idempotency, cập nhật nghiệp vụ).
3. Commit DB.
4. ACK/commit offset theo cơ chế của broker và adapter.

Nếu consumer sập giữa bước 3 và bước 4, broker có thể gửi lại message dù DB đã commit. **Redelivery là một tình huống bình thường cần được kiểm thử**, không đồng nghĩa nghiệp vụ được phép thực thi hai lần. Với một số broker/adapter, ACK có thể được quản lý bởi listener container và thứ tự chính xác khác trình tự minh họa; phải đối chiếu cấu hình thực tế.

## 7. Error channel, retry và rollback

Spring Integration hỗ trợ error flow và các chiến lược retry, nhưng **cách lỗi được truyền đi** quyết định transaction có rollback hay không.

**Kênh đồng bộ:** exception từ handler của `DirectChannel` thường quay lại người gửi. Nếu lỗi thoát khỏi method `@Transactional` và thỏa rollback rules, DB transaction rollback.

**Kênh bất đồng bộ:** exception ở executor, poller hoặc listener không thể đơn giản truyền ngược qua lời gọi Gateway đã trả về. Tùy endpoint, lỗi có thể được đưa thành `ErrorMessage` tới `errorChannel`, đi qua retry advice, hoặc được listener container xử lý. Transaction và cơ chế ACK nằm ở **consumer boundary**.

**Đừng nhầm "đã đưa vào errorChannel" với "đã rollback":** nếu một error handler xử lý xong lỗi và flow trở về bình thường, có cấu hình sẽ coi công việc đã thành công. Ngược lại, ném lỗi từ error flow có thể khiến poller/listener rollback hoặc kích hoạt retry tùy endpoint. Cần xác định endpoint nào bắt exception và kết quả cuối cùng mà transaction interceptor nhìn thấy.

| Tình huống | Điều nên thiết kế/kiểm thử |
| --- | --- |
| Lỗi mạng hoặc database tạm thời | Retry hữu hạn với backoff, phân biệt lỗi tạm thời và lỗi nghiệp vụ. |
| Lỗi dữ liệu không hợp lệ | Reject/quarantine/DLQ có nguyên nhân rõ ràng, tránh retry vô hạn. |
| Handler đã làm side effect rồi timeout | Idempotency key và cách tra cứu kết quả trước khi thử lại. |
| Exception bị catch để ghi log | Quyết định rõ có ném lại để rollback hay chấp nhận commit; ghi log không tự làm transaction rollback. |
| Retry vượt quá số lần cho phép | Lưu thông tin lỗi và message gốc vào kho bền vững/DLQ có thể vận hành và phát lại. |
| Lỗi sau khi ACK hoặc commit nguồn | Xác định cơ chế bù trừ/reconciliation; không giả định nguồn sẽ tự gửi lại. |

### Retry nằm ở đâu?

Với thao tác đồng bộ trong transaction DB, một retry ngay trong transaction đã gặp lỗi có thể không phù hợp nếu transaction đã bị đánh dấu `rollback-only` hoặc kết nối bị lỗi. Thường cần đặt retry **bao ngoài một lần xử lý có transaction mới** khi muốn retry toàn bộ đơn vị công việc. Với consumer từ broker, retry/redelivery phải nhất quán với ACK và chính sách DLQ. Không sử dụng retry vô hạn để che lỗi dữ liệu hoặc lỗi lập trình.

Ví dụ mang tính minh họa:

~~~text
Receive message
  -> check idempotency key
  -> begin business transaction
  -> perform write / update
  -> commit transaction
  -> acknowledge delivery

Temporary failure -> retry / redelivery with backoff
Permanent failure -> durable error record or DLQ
Redelivery after prior commit -> detect duplicate and return safely
~~~

**Thứ tự retry và transaction interceptor có ý nghĩa**: "mỗi lần thử một transaction" và "nhiều lần thử trong một transaction" không tương đương. Cấu hình advice chain phải được xem xét theo thứ tự thực thi thực tế.

## 8. Khi kết hợp Router, Splitter, Aggregator và correlation

Transactional boundary dễ bị hiểu sai trong các flow nhiều nhánh:

~~~mermaid
flowchart LR
  A["Gateway"] --> B{"Router"}
  B --> C["Nhánh A: DirectChannel"]
  B --> D["Nhánh B: ExecutorChannel / broker"]
  C --> E["Handler A"]
  D --> F["Handler B"]
  E --> G["Aggregator"]
  F --> G
  G --> H["Kết quả tổng hợp"]
~~~

- **Router** chỉ quyết định đường đi của message. Nếu đi qua channel đồng bộ và vẫn dùng cùng thread, các bước tiếp theo *có thể* tiếp tục dùng transaction hiện tại; nếu route sang executor/broker, boundary thay đổi.
- **Filter** loại message theo quy tắc nghiệp vụ thường là kết thúc hợp lệ của nhánh đó; muốn rollback phải thiết kế tín hiệu lỗi tương ứng.
- **Transformer** có thể biến đổi payload và header; giữ `correlationId` giúp theo dõi nhưng không chia sẻ transaction.
- **Splitter** tạo nhiều message con. Nếu các message được xử lý trên nhiều thread hoặc process, không có một local transaction mặc định bao phủ mọi nhánh.
- **Aggregator** dùng `correlationId`, sequence/release strategy và một message store để nhóm kết quả. Tính bền vững và giao dịch của message store quyết định khả năng phục hồi trạng thái tổng hợp; không thể tự rollback mọi side effect trước đó chỉ bằng việc aggregator gặp lỗi.
- **Gateway** giúp client gọi flow dễ dàng, nhưng phương thức trả về đồng bộ chỉ có ý nghĩa về **những bước đã thực sự chạy xong trước khi trả về**. Một nhánh bất đồng bộ có thể tiếp tục xử lý sau đó.

Với xử lý phân tán, nên thiết kế mỗi nhánh là một đơn vị xử lý có idempotency, lưu tiến độ và cơ chế retry/bù trừ riêng. Nếu nghiệp vụ cần nhiều bước có thể phục hồi nhưng không thể giao dịch chung, cân nhắc **Saga/compensating actions**. Một "compensation" là hành động nghiệp vụ mới để khắc phục tác động đã commit, **không phải rollback JDBC từ xa**.

## 9. Chọn boundary theo mục tiêu nghiệp vụ

| Nhu cầu | Cách bố trí gợi ý | Bảo đảm cần kiểm tra |
| --- | --- | --- |
| Validate và ghi một DB trong lời gọi đồng bộ | `@Transactional` tại application service → Gateway → `DirectChannel` → handler JDBC. | Cùng datasource/transaction manager; exception truyền về; rollback rule. |
| Worker xử lý đơn hàng nền | Durable queue/broker → transactional consumer/poller → handler. | Transaction của source, ACK/redelivery, timeout, idempotency và DLQ. |
| Một DB vừa cập nhật nghiệp vụ vừa tạo sự kiện | Ghi business row + outbox row cùng DB transaction; publisher độc lập. | Outbox scan/publish, retry, event ID duy nhất và consumer idempotent. |
| Nhiều nhánh song song và cần hợp nhất | Splitter/Router → async branches → Aggregator persistent state. | Correlation, timeout, lưu trạng thái, kết quả đến trễ, duplicate và compensation. |
| Gọi HTTP API từ handler transaction | Giới hạn thời gian gọi và dùng idempotency/cơ chế bù trừ nếu cần. | Remote call không rollback cùng JDBC; tránh giữ lock DB lâu trên lời gọi mạng. |

Một transaction dài bao quanh nhiều lời gọi mạng dễ giữ kết nối/khóa DB quá lâu, tăng tranh chấp và làm lỗi khó phục hồi. Boundary thường hiệu quả hơn khi nhỏ, rõ nguồn dữ liệu, và có cơ chế xử lý việc tiếp tục sau commit.

## 10. Kiểm thử hành vi, không chỉ kiểm tra flow chạy thành công

### Kiểm thử rollback đồng bộ

Với cấu hình `OrderFacade` ở phần 4, có thể dùng kiểm thử tích hợp sau (giả định Spring Boot, JUnit Jupiter, `JdbcTemplate` và schema test đã sẵn sàng):

~~~java
@SpringBootTest
class OrderTransactionIT {
    @Autowired OrderFacade facade;
    @Autowired JdbcTemplate jdbc;

    @Test
    void rollbackWhenCallerFailsAfterInsert() {
        String id = UUID.randomUUID().toString();

        assertThrows(IllegalStateException.class,
                () -> facade.submitThenFail(
                        new OrderCommand(id, new BigDecimal("125.00"))));

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders WHERE order_id = ?",
                Integer.class, id);
        assertEquals(0, count);
    }

    @Test
    void commitWhenFlowCompletesNormally() {
        String id = UUID.randomUUID().toString();
        facade.submit(new OrderCommand(id, new BigDecimal("125.00")));

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders WHERE order_id = ?",
                Integer.class, id);
        assertEquals(1, count);
    }
}
~~~

Không gắn `@Transactional` lên chính test nếu điều đó làm kết quả bị ảnh hưởng bởi transaction bao ngoài test và che mất hành vi commit/rollback của application service. Kiểm thử cần gọi bean đã được Spring proxy, truy vấn trạng thái lưu trữ **sau** khi lời gọi trả về, và dùng ID riêng để tránh dữ liệu của test khác.

### Ma trận lỗi cần có trong bài thực hành

| Kịch bản | Quan sát mong đợi |
| --- | --- |
| Handler trong `DirectChannel` ghi SQL rồi ném lỗi | Không có bản ghi commit nếu cùng transaction và exception kích hoạt rollback. |
| Chuyển handler sang `ExecutorChannel` | Transaction phía caller không bao phủ worker; kiểm chứng bằng trạng thái DB và cách xử lý lỗi bên worker. |
| Poller lấy từ `QueueChannel` in-memory rồi handler lỗi | DB rollback có thể xảy ra, nhưng không mặc định message được đưa lại queue. |
| Broker giao message lại sau DB commit | Handler idempotent không gây ghi nhận nghiệp vụ hai lần. |
| Publish outbox thành công nhưng chưa đánh dấu đã gửi | Có thể phát lại; phía nhận xử lý duplicate an toàn. |
| Filter loại message và không ném lỗi | Flow kết thúc theo logic filter; không tự suy ra transaction rollback. |
| Splitter tạo nhiều nhánh; một nhánh thất bại | Kiểm tra trạng thái từng nhánh, aggregator timeout, retry và compensation. |

Để quan sát rõ, log `messageId`, `correlationId`, định danh nghiệp vụ (`orderId`), lần thử, channel/endpoint, thời điểm bắt đầu và kết quả xử lý, cùng sự kiện commit/rollback/ACK khi có thể. Không ghi thông tin nhạy cảm trong payload vào log. Dùng metric cho số lần retry, redelivery, DLQ và độ trễ xử lý, thay vì chỉ ghi “send success”.

## 11. Những lỗi thiết kế thường gặp

1. **Cho rằng `DirectChannel` tự tạo transaction.** Kênh đồng bộ chỉ giữ call stack/thread; phải có application service, handler, poller hoặc interceptor thật sự mở transaction.
2. **Cho rằng `@Transactional` đi theo message header.** Khi chuyển thread/process, hãy xác định consumer boundary riêng.
3. **Cho rằng rollback DB tương đương rollback queue.** Queue in-memory và external broker có cơ chế xử lý riêng; rollback chỉ tác động lên tài nguyên đã tham gia transaction.
4. **Cho rằng một lần `send()` thành công nghĩa là nghiệp vụ đã hoàn tất.** Với async processing, thành công có thể chỉ là đã nhận vào buffer hoặc đã giao cho executor.
5. **Nuốt lỗi rồi chờ transaction tự rollback.** Nếu method kết thúc bình thường và transaction không bị đánh dấu rollback-only, dữ liệu có thể commit.
6. **Dựa vào "exactly once" như bảo đảm tuyệt đối toàn hệ thống.** Phạm vi bảo đảm của từng broker/transaction cụ thể khác nhau; ở ranh giới DB–broker vẫn phải đánh giá duplicate, ACK và recovery.
7. **Dùng correlation như khóa giao dịch.** Correlation phục vụ nhóm message và theo dõi nghiệp vụ, còn transaction được quản lý bởi tài nguyên và transaction manager.

## 12. Bài tập vận dụng

**Bài 1 — Vẽ transaction boundary.** Với flow `Gateway → DirectChannel → Transformer → ExecutorChannel → JDBC Handler` và một method service gọi Gateway có `@Transactional`, hãy vẽ hai thread và chỉ ra chỗ transaction của caller kết thúc. Nếu worker ghi DB thành công rồi caller ném lỗi, những dữ liệu nào có thể vẫn tồn tại?

**Bài 2 — Xử lý lại an toàn.** Một consumer nhận `OrderCreated(eventId, orderId)` và cập nhật tồn kho. DB đã commit nhưng consumer sập trước ACK. Hãy đề xuất bảng lưu `eventId` đã xử lý và unique constraint để redelivery không trừ kho lần thứ hai. Kiểm thử cùng một message được nhận hai lần.

**Bài 3 — Outbox và Aggregator.** Thiết kế luồng phát sự kiện từ transaction tạo đơn; hai consumer bất đồng bộ xử lý kho và thanh toán; một aggregator tổng hợp trạng thái theo `orderId`. Xác định rõ nơi lưu outbox, nơi commit/ACK, thời gian chờ nhánh, khóa idempotency, phương án xử lý khi thanh toán thất bại sau khi đã giữ kho.

### Câu hỏi tự đánh giá

**1. Vì sao `DirectChannel` thường dễ dùng với `@Transactional`?** Vì handler chạy đồng bộ trên cùng thread, nhờ đó có thể tham gia transaction hiện có của caller nếu dùng tài nguyên tương thích; bản thân channel không mở transaction.

**2. Thêm `ExecutorChannel` có làm transaction của caller tự đi sang worker không?** Không. Worker cần transaction riêng và cơ chế báo lỗi/đảm bảo xử lý thích hợp.

**3. Đặt `Pollers...transactional(manager)` trên `QueueChannel` in-memory đã bảo đảm không mất message chưa?** Chưa. Nó bao transaction quanh các tài nguyên tham gia, nhưng queue trong bộ nhớ không có bảo đảm lưu bền hay rollback việc dequeue như một nguồn giao dịch.

**4. Vì sao outbox vẫn cần idempotency?** Publisher có thể gửi xong rồi sập trước khi đánh dấu đã gửi, dẫn đến publish lại cùng event.

**5. Khi nào phải nhìn vào error channel để xác định rollback?** Khi exception có thể bị chuyển thành `ErrorMessage` hoặc được handler xử lý; phải kiểm tra lỗi có thực sự truyền tới transaction boundary hay không.

## 13. Checklist trước khi đưa flow vào vận hành

- [ ] Xác định rõ ai mở transaction, khi nào commit/rollback, và transaction manager quản lý tài nguyên nào.
- [ ] Vẽ vị trí chuyển thread/process và nơi bắt đầu consumer transaction mới.
- [ ] Ghi rõ độ bền của message store/queue và cơ chế redelivery khi process sập.
- [ ] Quy định ACK/offset commit và phản ứng khi xử lý thành công, lỗi tạm thời hoặc lỗi vĩnh viễn.
- [ ] Chọn idempotency key và unique constraint hoặc trạng thái nghiệp vụ để chống xử lý trùng.
- [ ] Dùng outbox hoặc cơ chế phù hợp khi cần đồng bộ thay đổi DB với việc phát sự kiện.
- [ ] Cấu hình retry hữu hạn, backoff, DLQ và quy trình phát lại message lỗi.
- [ ] Kiểm thử lỗi trước/sau DB commit, trước/sau broker ACK, giữa các nhánh song song và khi khởi động lại service.
- [ ] Theo dõi correlation, số lần retry, duplicate, backlog và thời gian xử lý mà không giả định correlation là transaction.

**Ghi nhớ:** Spring Integration giúp ghép các bước theo EIP một cách ít phụ thuộc và dễ mở rộng, nhưng transaction chỉ bảo vệ những thao tác thực sự nằm trong boundary và tài nguyên tương ứng. Độ tin cậy của luồng còn phụ thuộc vào nơi lưu message, redelivery, xử lý lỗi và khả năng idempotent của nghiệp vụ.
