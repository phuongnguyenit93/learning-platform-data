# Transaction-aware MessageStore trong Spring Integration Adapters

## 1. Bài toán: đã nhận message nhưng tiến trình chết trước khi xử lý xong

Giả sử một ứng dụng Spring Integration nhận sự kiện đơn hàng qua HTTP inbound gateway rồi đẩy message vào `QueueChannel` để xử lý bất đồng bộ. Handler sẽ cập nhật database và gọi HTTP outbound gateway tới một đối tác. Nếu ứng dụng sử dụng queue trong bộ nhớ, JVM chết sau khi đã trả `202 Accepted` nhưng trước khi handler nhận message, sự kiện có thể biến mất. Nếu dùng **persistent MessageStore**, message có thể tồn tại qua restart, nhưng lại nảy sinh các câu hỏi khó hơn:

- Khi nào message thực sự **được commit vào kho bền vững**?
- Một poller lấy message ra rồi handler ném lỗi: message có **quay về queue** hay đã bị xóa vĩnh viễn?
- Có thể ghi **business state và dequeue** trong cùng một database transaction không?
- Nếu đã commit database nhưng broker ACK thất bại, có thể nhận lại message không?
- Nếu outbound HTTP timeout sau khi phía đối tác đã commit, một transaction local có cứu được tình huống không?
- Với aggregator, dữ liệu từng message con và trạng thái group có thực sự bền vững, nhất quán khi nhiều worker cùng xử lý không?
- Nếu store gặp lỗi schema, serialization, connection hoặc cleanup, nghiệp vụ phải dừng, retry hay chuyển sang DLQ?

**Transaction-aware MessageStore** là cách tổ chức lưu trữ message hoặc message group sao cho **các thao tác đọc/ghi/xóa liên quan đến message tham gia đúng một transaction được quản lý**, khi implementation và transaction boundary hỗ trợ. Mục đích là tránh trạng thái “message biến mất khỏi queue nhưng business effect chưa commit”, hoặc “group được đánh dấu hoàn tất dù kết quả chưa được giao an toàn”.

Trong chương **Transactions** của module **SPRING_INTEGRATION_ADAPTERS**, bài học liên hệ trực tiếp với inbound/outbound adapter, gateway, poller, `MessageChannel` và luồng qua **File, SFTP, HTTP, JMS, AMQP, Kafka, database**; đồng thời xét hợp đồng message, lỗi, retry và vòng đời kết nối.

> **Điểm mấu chốt:** lưu message trong database **không tự tạo exactly-once end-to-end**. Điều có thể bảo đảm nguyên tử trước hết là **những thay đổi nằm trong cùng transaction và cùng resource manager**. Network calls, file systems, broker ACK và remote APIs thường nằm ngoài phạm vi đó.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt `MessageStore`, `ChannelMessageStore`, `MessageGroupStore` và store của aggregator.
2. Chỉ rõ transaction **bắt đầu ở đâu, bao phủ những lệnh nào, commit/rollback khi nào**.
3. Thiết kế persistent `QueueChannel`/polling consumer với JDBC store và transaction manager phù hợp.
4. Xử lý failure giữa `receive`, handler, business DB commit và external acknowledgment.
5. Thiết kế message group state, timeout, reaper và multi-instance concurrency.
6. Áp dụng transaction-aware storage cho File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC theo semantics riêng.
7. Kiểm thử crash/restart, rollback, duplicate, ordering, schema migration và bảo mật dữ liệu trong store.

## 2. Từ vựng và các mức “đã xử lý”

| Thuật ngữ | Ý nghĩa | Lưu ý |
|---|---|---|
| **Message** | Payload cùng headers theo Spring Messaging | ID/header có thể thay khi tạo message mới |
| **MessageStore** | Abstraction lưu và truy xuất message | Không phải tất cả store đều là queue |
| **ChannelMessageStore** | Store dành cho channel cần lưu message theo group/queue semantics | Kiểm tra implementation/version |
| **MessageGroupStore** | Abstraction lưu/tương tác với nhóm message | Phù hợp aggregator, resequencer, group state |
| **QueueChannel** | Pollable channel giữ message để consumer nhận sau | Mặc định in-memory không phải durable |
| **Persistent channel** | Channel dựa trên store bền vững | Độ bền phụ thuộc DB/commit/config |
| **Transaction boundary** | Những operations tham gia một transaction | Phải xác định thread, manager và resource |
| **ACK/offset commit** | Ghi nhận ở broker/transport rằng delivery đã được xử lý | Không tự đồng nhất DB commit |
| **Redelivery** | Message được giao lại sau rollback/lost ACK | Receiver cần idempotency |
| **In-flight** | Message đã được nhận nhưng chưa hoàn tất theo mốc đặt ra | Không nhất thiết còn hiển thị trong queue |
| **Outbox** | Durable intent để gửi ra hệ thống khác | Bổ trợ chứ không thay receiver idempotency |

### 2.1. Năm mốc dễ bị nhầm

~~~text
SOURCE_OBSERVED
    -> MESSAGE_CREATED
    -> STORED_AND_COMMITTED
    -> DEQUEUED_AND_PROCESSED
    -> BUSINESS_EFFECT_COMMITTED
    -> REMOTE_OUTCOME_CONFIRMED
~~~

Danh sách chỉ thể hiện một hành trình **minh họa**, không có nghĩa mỗi adapter có đủ các mốc hoặc mọi mốc nằm trong một transaction. Thí dụ, HTTP gateway có thể trả response trước khi business effect hoàn tất; Kafka producer ACK không chứng minh consumer đã ghi database.

### 2.2. Durable storage và transactional processing khác nhau

Một `JdbcChannelMessageStore` có thể lưu message bền vững, song nếu handler nhận message **ngoài transaction** hoặc handler thao tác DB bằng **transaction manager khác**, message vẫn có thể bị mất logic hoặc xử lý lặp. Muốn biết thiết kế an toàn đến đâu phải kiểm tra **transaction được mở trước hay sau lúc receive** và những resources nào thực sự tham gia.

## 3. Tổng quan các loại store liên quan

Spring Integration có các abstraction để quản lý messages, groups và channels. Cách sử dụng và loại store được hỗ trợ phụ thuộc **phiên bản Spring Integration**.

| Thành phần | Nhu cầu chính | Ví dụ triển khai/ý tưởng |
|---|---|---|
| `MessageStore` | Lưu/lấy/xóa message theo ID | Persistent message repository |
| `MessageGroupStore` | Thêm/lấy/xóa messages trong một group | Aggregator, resequencer |
| `ChannelMessageStore` | Quản lý messages của persistent channel | JDBC-backed queue/channel |
| `JdbcMessageStore` | JDBC storage cho message/group theo API được hỗ trợ | Aggregator/resequencer persistence |
| `JdbcChannelMessageStore` | JDBC-backed persistence cho pollable channel | Durable QueueChannel |
| Metadata store | Lưu checkpoint/file filter/dedup metadata | Không mặc nhiên lưu full messages |
| Dead-letter queue | Lưu lỗi cuối theo transport | Không tự là transaction-aware MessageStore |
| Transactional outbox | Lưu outbound intent cạnh domain state | Đảm bảo không mất ý định gửi sau DB commit |

**Không hoán đổi tùy tiện:** `JdbcMessageStore` phục vụ bài toán message/group và `JdbcChannelMessageStore` phục vụ channel semantics theo thiết kế cụ thể. Chúng có thể dùng schema/query/provider khác nhau. Đọc contract/API của phiên bản dự án trước khi thay một bean store vào một channel.

### 3.1. Store bền vững không chỉ có JDBC

Spring Integration có các implementation dựa trên công nghệ lưu trữ khác tùy module/version, như Redis hoặc MongoDB cho một số nhu cầu. Tuy nhiên **transaction semantics, atomicity, locking, TTL và consistency của từng backend khác nhau**. Không thể thay một JDBC store bằng Redis store rồi suy nguyên vẹn rollback của transaction SQL cũng được bảo đảm.

## 4. Kiến trúc tổng thể: transactional local queue với remote target

~~~mermaid
flowchart LR
    EXT[HTTP / File / SFTP / Broker / DB] --> IN[Inbound Adapter / Gateway]
    IN --> CH[Persistent QueueChannel]
    CH <--> STORE[(Transactional Message Store)]
    CH --> POLLER[Transactional Polling Consumer]
    POLLER --> HANDLER[Business Handler]
    HANDLER --> DB[(Business Tables)]
    HANDLER --> OUTBOX[(Outbox Intent)]
    OUTBOX --> DISPATCH[Dispatcher + Retry]
    DISPATCH --> TARGET[HTTP / JMS / AMQP / Kafka / SFTP]
    TARGET --> VERIFY[ACK / Status / Reconciliation]
    STORE -. local DB transaction .-> DB
    DB -. local DB transaction .-> OUTBOX
~~~

Đường chấm chỉ ý nghĩa **các cập nhật có thể cùng tham gia local database transaction** nếu store, business tables, outbox thực sự dùng **cùng DataSource/transaction manager và cùng transaction context**. Nó **không** có nghĩa `QueueChannel`, handler, outbox dispatcher, broker và target đều nằm trong một distributed transaction.

### 4.1. Hai transaction thường khác nhau

**Transaction A — ingress/storing:** adapter hoặc handler đưa message vào persistent channel; commit được xem là điểm message đã durable. Với HTTP 202, cần bảo đảm commit trước khi báo “accepted” nếu hợp đồng nghĩa là “đã nhận bền vững”.

**Transaction B — consuming/processing:** poller bắt đầu transaction, lấy message từ store, cập nhật business state/outbox và commit; nếu rollback, việc lấy/xóa message **có thể được rollback cùng các thay đổi DB**.

Việc hai transaction tách rời là bình thường. Mấu chốt là thiết kế rõ **commit points, ownership, error propagation và replay policy**.

## 5. ACID và ranh giới thực tế của Transaction-aware Store

### 5.1. Atomicity

Thao tác store và thay đổi domain trong cùng transaction **cùng resource** có thể commit hoặc rollback cùng nhau. Nếu gửi HTTP/Kafka/file từ bên trong code đó, remote không tự rollback theo transaction local.

### 5.2. Consistency

Unique constraints, foreign keys, business invariants và quy tắc message lifecycle giữ dữ liệu đúng. Transaction manager không thay validation, idempotency và trạng thái nghiệp vụ.

### 5.3. Isolation

Hai polling consumers có thể tranh cùng message/group. Database locking/isolation, store implementation, message group locks và transaction duration ảnh hưởng việc cùng một message có được giao cho hai workers đồng thời không.

### 5.4. Durability

Sau DB commit, message/marker tồn tại theo durability guarantee của database và cấu hình replication/backup. Không xem một write chưa commit hoặc một cache in-memory là durable.

### 5.5. Những gì ACID không bao phủ

- Network transmission tới HTTP API ngoài transaction local.
- Thao tác upload/rename ở SFTP server.
- ACK và offset commit của JMS/AMQP/Kafka nếu không có cơ chế coordination phù hợp.
- Chỉnh sửa file system hoặc side effect tới người dùng.
- Operation ở một database khác không dùng cùng transaction manager.
- Một lời gọi async được schedule sau transaction nhưng chưa được phát.

## 6. MessageStore và MessageGroupStore: không cùng lifecycle

### 6.1. MessageStore

Một message store tổng quát có thể lưu message độc lập để tra lại theo ID. Việc nó có transaction-aware hay không phụ thuộc implementation. **Không suy ra có FIFO dequeue** chỉ vì store cung cấp `addMessage(...)` hoặc `removeMessage(...)`.

### 6.2. MessageGroupStore

Group store có trách nhiệm quản lý nhóm message: group ID, messages, trạng thái hoàn tất, release/expire/cleanup theo các API của implementation. Khi aggregator nhận nhiều parts, chính sách **correlation, release và message group completion** quyết định khi nào kết quả được tạo.

### 6.3. ChannelMessageStore

Store dành cho pollable channel thường bổ sung queue semantics, group/channel identity và cách lấy message tiếp theo. Để xử lý an toàn, cần kiểm tra:

- Channel nào được ánh xạ tới cùng group/key/store?
- Thứ tự dequeue/FIFO/priority có được bảo đảm trong cấu hình đó không?
- Có transaction mở trước `receive` không?
- Có consumer concurrent hay polling task executor không?
- Lúc rollback, message được trả về trạng thái chờ ra sao?
- Khi restart, metadata nào còn và message nào chưa commit?

### 6.4. Không nhầm với metadata store

`MetadataStore` dùng cho file accept-once filter, checkpoint hoặc idempotency selector có thể chỉ giữ key/value, **không lưu payload message**. Dù metadata store bền vững, business flow vẫn có thể mất message giữa lúc source được đánh dấu “đã nhìn thấy” và lúc message được ghi thành công tới queue.

## 7. QueueChannel mặc định và persistent QueueChannel

### 7.1. Queue trong bộ nhớ

`QueueChannel` không có persistent store thường giữ message trong JVM. Ưu điểm: đơn giản, chi phí I/O thấp; nhược điểm: mất nội dung khi process crash/restart, khó scale nhiều replicas như một queue chung.

### 7.2. Queue có durable store

~~~mermaid
sequenceDiagram
    participant I as Inbound Handler
    participant C as QueueChannel
    participant S as JDBC Channel Store
    participant P as Poller
    participant B as Business Database
    I->>C: send(message)
    C->>S: persist message
    S-->>C: write (transaction commit tùy boundary)
    C-->>I: send result
    Note over I,S: Chỉ coi accepted bền vững khi transaction đã commit
    P->>S: begin TX + receive/dequeue
    S-->>P: Message
    P->>B: business update trong cùng TX nếu cấu hình đúng
    alt Handler hoàn tất
        P->>S: commit TX
    else Exception buộc rollback
        P->>S: rollback TX
        Note over P,S: Dequeue được rollback nếu cùng resource/transaction
    end
~~~

Sơ đồ là **mô hình transaction kỳ vọng**, không phải hành vi mặc định chỉ nhờ khai báo JDBC store. Nếu một handler bất đồng bộ vượt sang executor khác hoặc tham gia transaction manager khác, mối liên kết transaction có thể bị cắt.

### 7.3. Nguồn và đích có thể vẫn lặp

Sau khi message đã commit ở persistent queue, upstream có thể nhận ACK thất bại và gửi lại cùng event. Bên cạnh transaction-aware queue cần **idempotent receiver** hoặc business unique key. Durability giải quyết **mất message**, không tự giải quyết **duplicate source deliveries**.

## 8. Transaction manager, thread-bound context và propagation

Trong Spring, local JDBC transaction thường do `PlatformTransactionManager` như `DataSourceTransactionManager` quản lý. Spring Integration poller có thể cấu hình **transaction advice**, hoặc service có thể dùng `@Transactional`; hai lựa chọn này không tương đương về phạm vi.

### 8.1. Ba trường hợp quan trọng

| Cấu hình | Dequeue có trong transaction? | Business update có trong transaction? | Hệ quả |
|---|---|---|---|
| Không có transaction | Không bảo đảm | Không bảo đảm | Nhận rồi crash có thể mất message |
| Chỉ `@Transactional` trên handler | Có thể **không**, vì receive xảy ra trước lúc vào handler | Có nếu proxy hoạt động | Message removal và domain update có thể tách |
| Poller advice bắt đầu TX trước `receive` | Có, nếu store tham gia cùng manager/resource | Có nếu handler chạy trong cùng TX/thread | Rollback có thể đưa message lại cùng domain state |

### 8.2. Thread boundary

Local Spring transaction thường gắn với thread/context quản lý. Khi `ExecutorChannel` hoặc một custom async task chuyển xử lý sang thread khác:

- Transaction của poller **không tự đi theo thread**.
- Handler ở thread mới có thể chạy một transaction khác hoặc không có transaction.
- Poller có thể commit dequeue trước khi business effect hoàn tất.
- Cần thay thiết kế: xử lý đồng bộ trong poller transaction, hoặc tạo **durable handoff/outbox** sang bước async trước khi commit.

### 8.3. Proxy và self-invocation

`@Transactional` chỉ hiệu lực khi được áp dụng đúng qua Spring AOP proxy/transaction infrastructure. Gọi một method transactional từ một method khác trong **cùng bean** có thể bypass proxy trong cấu hình proxy thường gặp. Đừng suy transaction tồn tại chỉ nhờ nhìn thấy annotation; test commit/rollback với DB thật.

## 9. Cấu hình transaction-aware poller bằng XML minh họa

Một ví dụ cấu hình **mang tính chỉ dẫn theo Spring Integration XML namespace**:

~~~xml
<int:channel id="durableOrders">
    <int:queue message-store="ordersChannelStore"/>
</int:channel>

<bean id="ordersChannelStore"
      class="org.springframework.integration.jdbc.store.JdbcChannelMessageStore">
    <constructor-arg ref="dataSource"/>
</bean>

<int:service-activator input-channel="durableOrders"
                       ref="ordersHandler"
                       method="handle">
    <int:poller fixed-delay="1000">
        <int:transactional transaction-manager="transactionManager"/>
    </int:poller>
</int:service-activator>
~~~

**Đây là fragment**, không phải file XML hoàn chỉnh: còn cần khai báo namespaces `int`, beans `dataSource`, `transactionManager`, `ordersHandler`, schema SQL và cấu hình dialect/query provider tương thích. Kiểm tra thuộc tính/constructor của phiên bản Spring Integration trước khi áp dụng.

### 9.1. Ý nghĩa fragment

1. `durableOrders` là pollable channel có backing store.
2. `ordersChannelStore` lưu messages qua JDBC thay vì queue RAM.
3. Poller kích hoạt consumer có transaction advice được cấu hình.
4. Khi `receive` và synchronous handler cập nhật **cùng JDBC resource**, exception làm rollback TX có thể giữ message và business state chưa commit.
5. Nếu handler đã gọi HTTP remote trước khi ném exception, **HTTP side effect không rollback**.

### 9.2. Các mục phải được kiểm tra trong project thật

- Có đúng database DDL/permission/SQL dialect cho JDBC channel store?
- DataSource mà store dùng có đúng manager mà poller advice dùng không?
- Handler có xử lý đồng bộ, không chuyển sang thread khác trước commit không?
- Error handler/retry advice có **nuốt exception** khiến transaction commit ngoài ý muốn không?
- Backend có nhiều consumers/instances và row lock semantics nào?
- Đã kiểm thử rollback của dequeue bằng một DB integration test chưa?

## 10. Ví dụ Java: JDBC transaction manager và persistent store

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class MessageStoreInfrastructure {
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    JdbcChannelMessageStore ordersChannelStore(DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);
        // Cấu hình query provider/schema/dialect nếu bản đang dùng cần.
        return store;
    }
}
~~~

Mã nhằm làm rõ **store và local transaction manager dùng cùng DataSource**. Chưa đủ để biến toàn flow thành transactional: phải nối store với channel, mở transaction trong consumer poller và triển khai business handler đúng boundary. `JdbcChannelMessageStore` và constructor/API cần kiểm tra theo version; không xem đoạn này là một project đã build/test.

### 10.1. Vì sao “cùng DataSource” quan trọng?

Nếu store dùng DataSource A, còn handler cập nhật DB B bằng transaction manager khác, `@Transactional` trên handler không tự bảo đảm rollback dequeue ở A. Ngay cả khi hai DataSources cùng trỏ vào một server database, **hai physical connections được quản lý bởi hai transaction contexts độc lập** có thể vẫn commit/rollback riêng.

### 10.2. Không mở transaction quá dài

Giữ transaction trong thời gian gọi HTTP/SFTP chậm khiến database locks/connections bị giữ lâu, giảm throughput và tăng deadlocks. Nên cân nhắc **domain update + outbox intent trong một transaction ngắn**, rồi external dispatcher gửi ngoài transaction đó với idempotency/retry.

## 11. Ghi nhận ingress trước khi trả lời client

### 11.1. HTTP inbound gateway trả `202 Accepted`

Nếu hợp đồng HTTP nói “đã nhận bền vững để xử lý sau”, thì **lưu persistent message hoặc inbox/outbox intent phải commit trước khi phản hồi**. Nếu mới đưa vào một in-memory queue hoặc transaction chưa commit, trả 202 có thể làm client ngừng retry dù work bị mất khi JVM crash.

### 11.2. Trạng thái đề xuất

| Trạng thái | Nghĩa | Response/ACK |
|---|---|---|
| `RECEIVED_NOT_COMMITTED` | Đã thấy request, chưa durable | Không khẳng định đã accepted bền vững |
| `STORED_COMMITTED` | Work item bền vững | Có thể trả 202 theo API contract |
| `PROCESSING` | Worker đang chạy | Status API có thể hiển thị đang xử lý |
| `COMPLETED` | Business effect đạt mốc xác nhận | Trả status/result theo contract |
| `FAILED_RETRYABLE` | Sẽ retry theo policy | Không coi hoàn tất |
| `UNKNOWN_OUTCOME` | Đích có thể đã commit | Reconciliation trước retry nguy hiểm |

### 11.3. Không nhầm ACK của ingress với completion của egress

Trả HTTP 202 cho ingress có thể đúng nếu message đã durable, nhưng không chứng minh outbound JMS/Kafka/SFTP đã gửi xong. Thiết kế status endpoint hoặc callback khi caller cần biết kết quả nghiệp vụ cuối.

## 12. Dequeue và handler: transaction phải bao phủ cả hai

Một sequence đáng mong đợi:

~~~text
BEGIN local JDBC transaction
  RECEIVE message from persistent queue
  VALIDATE payload / idempotency key
  APPLY business DB changes
  RECORD outbox intent (nếu cần outbound)
COMMIT local JDBC transaction

ACK/REPLY tới upstream theo hợp đồng và boundary riêng
~~~

Nếu handler ném exception **trước COMMIT**, các thao tác JDBC cùng transaction được rollback. Message được bảo toàn để xử lý lại **nếu thao tác dequeue của store cũng tham gia transaction đó**. Nếu handler gọi external API giữa BEGIN/COMMIT, remote call đã xảy ra không thể bị rollback bởi local JDBC transaction.

### 12.1. Ví dụ service cập nhật domain trong transaction sẵn có

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderDatabaseHandler {
    private final JdbcTemplate jdbc;

    public OrderDatabaseHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void handle(OrderEvent event) {
        int updated = jdbc.update(
                """
                UPDATE orders
                   SET state = ?
                 WHERE order_id = ?
                """,
                event.newState(), event.orderRef());

        if (updated != 1) {
            throw new IllegalStateException("ORDER_ROW_NOT_FOUND");
        }
    }
}
~~~

Ở đây `OrderEvent` là DTO nghiệp vụ do dự án tự định nghĩa. Handler **không tự mở transaction**; mục tiêu minh họa là nó được gọi **đồng bộ bên trong transaction do poller mở**, bằng `JdbcTemplate` sử dụng cùng DataSource. Với domain có thể nhận trùng event, phải bổ sung **idempotent receiver/unique business marker** chứ không chỉ update một row.

### 12.2. Vì sao handler phải để lỗi rollback lan ra?

Nếu code:

~~~java
try {
    orderHandler.handle(event);
} catch (Exception ex) {
    log.warn("Failed but ignored");
}
~~~

thì transaction interceptor có thể thấy method kết thúc **bình thường** và commit dequeue. Muốn retry/rollback, lỗi phải được **propagate** hoặc transaction được chủ động đánh dấu rollback-only theo policy; đồng thời cần error handling, retry budget và DLQ tránh poison message chạy mãi.

## 13. Các ranh giới thời gian và điểm crash

### 13.1. Ma trận local queue + database

| Điểm crash | Message ở store | Business DB | Hướng khôi phục |
|---|---|---|---|
| Trước ingress commit | Không chắc được lưu | Chưa đổi | Upstream retry hoặc nguồn còn giữ |
| Sau ingress commit, trước poll | Đã bền vững | Chưa đổi | Poller nhận sau restart |
| Sau dequeue, trước handler, TX chưa commit | Dequeue chưa commit | Chưa đổi | Rollback và redelivery nếu cùng TX |
| Handler update xong, trước TX commit | Dequeue/update chưa commit | Chưa commit | Rollback cả hai nếu cùng DB TX |
| Sau TX commit, trước ACK nguồn | Đã lấy khỏi queue | Đã commit | Upstream có thể giao lại; cần idempotency |
| Sau outbound HTTP commit, trước TX commit | Có thể rollback dequeue | Remote có thể đã đổi | Reconciliation/remote idempotency |

### 13.2. Từ “rollback” luôn phải có đối tượng

Hỏi chính xác: rollback **message dequeue**, **business update**, **outbox row**, **broker offset**, hay **remote API**? Chỉ những operations đã tham gia transaction manager tương ứng mới rollback cùng nhau.

## 14. Khi message được nhận nhưng transaction bị rollback

Một retry policy cần phân biệt:

1. **Transient error:** deadlock, temporary DB connection, rate limit; retry với backoff.
2. **Permanent error:** schema invalid, unsupported message, missing domain prerequisite không thể tự khôi phục.
3. **Unknown outcome:** remote timeout sau request đã gửi; không retry mù.
4. **Store failure:** không biết dequeue/commit đã xảy ra hay chưa; cần đọc DB state.
5. **Poison message:** bản ghi liên tục lỗi khiến queue không tiến triển.

### 14.1. Lặp rollback vô hạn

Nếu poller cứ lấy cùng message, handler ném cùng một exception và transaction rollback, message có thể xuất hiện lại liên tục, chiếm worker và chặn những message sau. Cần **bounded retries, delay/backoff, parking lot/DLQ** và state transition có transaction/ack phù hợp.

### 14.2. DLQ không tự là một phần của JDBC transaction

Nếu xử lý lỗi bằng cách publish sang DLQ ở broker rồi commit DB dequeue, hai thao tác không tự nguyên tử. Có thể mất message trong khoảng giữa chúng, hoặc publish DLQ trùng sau crash. Giải pháp thường là **ghi durable failure/outbox intent trong cùng transaction DB**, rồi chuyển message ra DLQ bất đồng bộ có idempotency.

## 15. MessageGroupStore trong aggregator và resequencer

Không phải mọi persistent message store dùng để làm queue. **Aggregator** cần lưu **message group state** để chờ đủ parts; **resequencer** cần giữ các messages chưa đủ điều kiện phát đúng thứ tự. Khi có restart, store bền vững giúp các messages đã ghi không mất, nhưng release và cleanup phải được thiết kế nguyên tử theo phạm vi phù hợp.

### 15.1. Ví dụ luồng batch

~~~mermaid
flowchart LR
    IN[File / Kafka / JMS Input] --> SPLIT[Splitter]
    SPLIT --> A[Part A]
    SPLIT --> B[Part B]
    SPLIT --> C[Part C]
    A --> AGG[Aggregator]
    B --> AGG
    C --> AGG
    AGG <--> GROUP[(Persistent MessageGroupStore)]
    AGG --> RESULT[Aggregate Result]
    RESULT --> QUEUE[Durable Outbound Queue]
    QUEUE --> TARGET[Remote Target]
~~~

### 15.2. Những state cần quan sát

| State | Nghĩa | Failure mode |
|---|---|---|
| **Group created** | Có part đầu tiên | Chưa chắc batch đầy đủ |
| **Part added** | Message part đã được lưu | Duplicate part có thể xuất hiện |
| **Group complete** | Release strategy thỏa điều kiện | Chưa chắc kết quả đã tới target |
| **Result released** | Output message được tạo/dispatch | Crash sau release có thể mất output nếu không durable |
| **Group expired** | Timeout/cleanup theo policy | Có thể là batch thiếu parts |
| **Group removed** | Store đã cleanup | Có thể mất dấu vết nhận diện late arrivals nếu policy không giữ |

### 15.3. Key group không phải idempotency của item

`correlationId` phục vụ gom nhóm; còn idempotency có thể cần **group ID + stable item ID + operation**. Nếu chỉ dùng group ID làm dedup key tại part handler, part đầu có thể khiến các part còn lại bị xem là trùng. Nếu không có idempotency, một part redeliver có thể làm group có duplicate và phát kết quả không đúng.

## 16. Transaction-aware Aggregator: kết quả release phải được giao an toàn

Một thiết kế thiếu là: group đã `complete` trong persistent store, aggregator tạo kết quả, sau đó gửi qua output channel chỉ nằm trong RAM; JVM chết trước khi outbound xử lý. Khi restart, group có thể đã được đánh dấu hoàn tất nên **không phát kết quả lại**.

### 16.1. Phân tích ranh giới

~~~text
Persist part
   -> Mark group complete
   -> Release aggregated result
   -> Send output
   -> External target ACK
~~~

Các bước này **không mặc nhiên nằm trong một transaction**. Dù `MessageGroupStore` dùng JDBC, việc phát ra `MessageChannel` hoặc remote HTTP/Kafka có thể diễn ra ngoài DB transaction.

### 16.2. Những chiến lược đáng cân nhắc

1. **Transactional group update + durable output intent:** cùng DB transaction ghi group completion và outbox row; dispatcher gửi sau.
2. **Durable output channel:** output được lưu bền vững trước khi coi quá trình release hoàn tất, với transaction synchronization theo khả năng.
3. **Idempotent result consumer:** nếu release xảy ra hai lần sau recovery, receiver ở đích nhận ra cùng `aggregate_result_id`.
4. **Completed-group retention:** giữ thông tin đã hoàn tất đủ lâu để nhận diện late/duplicate parts.
5. **Recovery scanner:** tìm group/intent đang kẹt và đối soát theo state machine.

### 16.3. Sự kiện đến muộn

Một message đến sau khi group đã được release đặt ra policy: bỏ qua, tạo group mới, sửa kết quả hoặc gửi correction event. Tùy framework/configuration, aggregator có thể có behavior khác. **Định nghĩa nghiệp vụ phải rõ**, không suy từ việc database table đã dọn group.

### 16.4. Transaction không thay release strategy

Ngay cả khi phần ghi group atomic, release strategy sai vẫn làm phát sớm hoặc không bao giờ phát. Kiểm tra correlation, sequence number/sequence size, missing parts, duplicate items, group timeout và restart với dữ liệu thật đại diện.

## 17. MessageGroupStoreReaper, expiration và cleanup

Một số flow dùng cơ chế reaper/expiry để xóa hoặc xử lý các message groups không hoàn tất trong thời hạn quy định. Spring Integration có hỗ trợ kiểu **`MessageGroupStoreReaper`** và các chiến lược timeout/expiration tùy version.

### 17.1. Cần chọn chính sách trước khi bật cleanup

| Câu hỏi | Vì sao quan trọng |
|---|---|
| Group nào được coi là stale? | Có batch vốn chỉ đến một lần/ngày? |
| Timeout tính từ mốc nào? | Group creation, last update hay event time? |
| Có phát partial result không? | Có thể vi phạm hợp đồng dữ liệu |
| Expired group có vào error/parking state? | Tránh mất dấu vết |
| Cleanup có transactional không? | Tránh xóa sau khi message chưa giao xong |
| Late part được xử lý ra sao? | Tránh group ma hoặc kết quả trùng |
| Ai chịu trách nhiệm retry/reconciliation? | Không để expiry thành silent data loss |

### 17.2. Không dùng expiry để sửa sự cố tồn đọng

Xóa hết groups cũ để giảm số rows có thể làm mất nghiệp vụ chưa hoàn tất. Trước khi chạy cleanup hàng loạt, phân loại **completed, abandoned, awaiting parts, unknown outcome**; có approval và rollback/evidence theo policy.

## 18. JDBC MessageStore: schema, dialect và migrations

Persistent JDBC store cần **tables/indexes/constraints/SQL phù hợp phiên bản thư viện và database dialect**. Không tự tạo bảng bằng cách đoán tên dựa trên một tutorial khác.

### 18.1. Checklist database nền tảng

1. Dùng **DDL/schema scripts chính thức tương ứng đúng version** của Spring Integration JDBC.
2. Kiểm tra **dialect/query provider** tương thích PostgreSQL, MySQL, Oracle, SQL Server hoặc loại DB đang dùng.
3. Đảm bảo unique/index và cơ chế ordering/locking mà implementation cần.
4. Tách database schema/user permission cho ứng dụng khi có yêu cầu.
5. Kiểm tra migration khi nâng Spring Integration: dữ liệu message cũ còn đọc được không?
6. Đánh giá payload serializer/headers converter compatibility khi thay đổi Java class/schema.
7. Thiết kế backup/restore, HA, retention, purge và giám sát disk.
8. Có migration rollback phù hợp nhưng **không xóa message pending** chỉ để rollback release.

### 18.2. Index và capacity

Store tăng theo **ingress − committed processing**. Khi downstream chậm, rows pending và transaction contention có thể tăng mạnh. Cần đo:

- Message count/pending age và rate add/remove.
- Query duration, DB connection wait, lock wait/deadlock.
- Storage bytes, index bloat, write amplification và checkpoint/backup.
- Số pollers/concurrent consumers, batch size và throughput thực.
- Phân bố message size, chi phí serialize/deserialize và lỗi mapping.

### 18.3. Đổi version ứng dụng

Nếu queue chứa message serialized từ class Java phiên bản A, sau deploy B có thể không deserialize được. Cần **backward-compatible message contract**, converter phù hợp hoặc chiến lược drain/migrate an toàn. Không chỉ dựa vào Java default serialization khi cần giữ message qua nhiều deployments mà chưa thử tương thích.

## 19. Serialization: message lưu bền vững không giống object trong RAM

Một Spring `Message<?>` có payload và headers; những thành phần này có thể chứa:

- DTO Java, record, map, byte[], XML/JSON, file reference.
- `replyChannel`/`errorChannel` là object runtime không thích hợp serialize.
- InputStream hoặc resource chưa materialize, không thể lưu trực tiếp tùy store/converter.
- Trace baggage, metadata nhạy cảm, application headers.
- Class schema thay đổi qua deployments.

### 19.1. Quy tắc thiết kế payload

1. Ưu tiên **data contract ổn định** (JSON/Avro/Protobuf/DTO có version) thay vì lưu object gắn chặt classpath nếu store cần sống lâu.
2. Chỉ lưu headers cần thiết, có thể serialize và đã được phê duyệt.
3. Không giữ raw password/token, session object hay file stream trong persistent store.
4. Khi payload quá lớn, cân nhắc lưu **reference tới object store có ACL**, còn message chỉ giữ metadata và content hash/version nếu phù hợp.
5. Kiểm tra converter failure trước/sau commit; không mark message completed khi không đọc được.
6. Review rủi ro deserialize object từ nguồn không tin cậy; dùng allowlist type và thư viện cập nhật.

### 19.2. Chú ý “serialized successfully” không bằng xử lý được

Message ghi thành công ở version A vẫn có thể vướng class/schema incompatibility ở version B. Hãy có **compatibility test dùng dữ liệu persisted từ version trước**, không chỉ unit test tạo/đọc cùng một JVM.

### 19.3. Dữ liệu nhạy cảm tồn tại trong store

Persistent store có thể chứa **toàn bộ payload và một số headers**, khác hẳn queue RAM. Vì vậy cần phân loại dữ liệu, encryption at rest, TLS tới DB, RBAC, audit truy cập, retention và quy trình purge/backup. MessageStore **không phải nơi an toàn mặc định cho secrets**.

## 20. Concurrency và transaction isolation khi nhiều consumers

Một persistent queue có thể được poll bởi nhiều threads hoặc instances. Muốn an toàn cần biết implementation bảo vệ **atomic take/dequeue** thế nào.

### 20.1. Các race condition

- Hai pollers cùng thử lấy một message.
- Worker A đã receive trong transaction dài; worker B bị lock hoặc skip record.
- Worker A rollback, message lại có thể được nhận.
- Worker B commit kết quả trước A theo lịch xử lý, làm thay đổi ordering.
- Database deadlock do khóa message/group và business tables theo thứ tự khác nhau.
- Poller timeout/cancellation khiến connection bị đóng giữa lúc commit.

### 20.2. Isolation không đồng nghĩa ordering tuyệt đối

Một implementation có thể dùng row locks, paging, group keys hoặc khác; thứ tự “first stored, first completed” không được bảo đảm khi có nhiều workers. Nếu nghiệp vụ cần ordering theo entity, phải có **partition/group key, version/sequence guard hoặc tuần tự hóa thích hợp**.

### 20.3. Transaction kéo dài làm nghẽn queue

Nếu một poller mở JDBC transaction rồi gọi API chậm hàng chục giây:

- Row locks/DB connections bị giữ lâu.
- Other consumers giảm throughput hoặc bị contention.
- Deadlocks/timeouts tăng.
- Queue depth và oldest age tiếp tục tăng.

Thiết kế tốt thường giới hạn transaction ở **local DB effects + durable outbound intent**, tách external I/O sang một bước có retry/idempotency.

## 21. Transaction synchronization và thao tác sau commit

Một số flow cần làm việc **sau khi** local transaction đã commit, ví dụ phát sự kiện hoặc kích hoạt dispatcher. Spring có cơ chế transaction synchronization; Spring Integration cũng có các khả năng tích hợp transaction synchronization theo phiên bản.

### 21.1. Một sai lầm phổ biến

~~~text
BEGIN TX
  UPDATE business DB
  SEND remote API
ROLLBACK business DB due to later error
~~~

Remote API có thể đã xử lý, nên rollback local DB **không hủy remote effect**.

### 21.2. After-commit callback có tác dụng gì?

Đẩy remote call sang **after-commit** tránh gọi khi local transaction chắc chắn rollback; tuy nhiên **process có thể chết sau commit trước khi callback chạy**. Callback trong RAM không đủ làm durable outbound handoff.

### 21.3. Khi nào dùng outbox?

Nếu yêu cầu không mất sự kiện gửi đi, ghi một **outbox row trong cùng local transaction** với business update. Sau commit, dispatcher đọc row đó, gửi tới đích và cập nhật trạng thái. `afterCommit` có thể dùng để **đánh thức dispatcher**, nhưng outbox row mới là bằng chứng bền vững.

## 22. File adapter: filesystem không tự rollback cùng JDBC store

Một File inbound adapter có thể đọc file và gửi message vào persistent queue. Nếu database transaction rollback, file đã rename/move/delete ở filesystem **không tự khôi phục**.

### 22.1. Ranh giới thực tế

| Hành động | Thuộc local JDBC TX? | Ghi chú |
|---|---|---|
| Insert queue message vào JDBC store | Có thể, nếu manager/store cùng context | Kiểm chứng commit |
| Update business table cùng DB | Có thể | Cùng transaction |
| Move/rename file | Không | File system không tự rollback |
| Mark accept-once metadata ở external store | Phụ thuộc implementation | Có thể khác transaction |
| Gửi HTTP/Kafka | Không tự | Cần target idempotency/outbox |

### 22.2. Cách tổ chức an toàn

1. Đảm bảo file đã **sẵn sàng/ổn định** trước khi đọc, không parse file đang được ghi.
2. Thiết kế file identity/manifest và **idempotency** cho một logical file/batch.
3. Chỉ chuyển file sang trạng thái “đã xử lý” khi durable processing đạt checkpoint hợp đồng.
4. Nếu phải move trước processing, giữ nguồn phục hồi hoặc một persistent queue đủ tin cậy và recovery plan.
5. Với file nhiều records, có thể cần completion ledger theo item thay vì chỉ một cờ file.
6. Không log raw file path hoặc payload nhạy cảm khi điều tra lỗi.

## 23. SFTP adapter: remote session và local transaction độc lập

SFTP inbound/outbound có session/connection lifecycle, remote listing, transfer, rename và metadata filter. **Remote SFTP operations không tham gia JDBC transaction** chỉ vì message được lưu vào `JdbcChannelMessageStore`.

### 23.1. Các điểm có thể thất bại

~~~text
REMOTE_FILE_DISCOVERED
  -> DOWNLOAD_ATTEMPTED
  -> LOCAL_FILE_READY
  -> MESSAGE_STORED_AND_COMMITTED
  -> BUSINESS_PROCESSED_AND_COMMITTED
  -> REMOTE_ARCHIVE_OR_ACKNOWLEDGED
~~~

Nếu crash sau download nhưng trước queue commit, file cần có đường retry. Nếu crash sau local DB commit nhưng trước remote archive, source có thể gửi lại file; receiver phải dedup business event. Nếu outbound SFTP timeout, target có thể đang giữ **partial file**.

### 23.2. Quy tắc thiết kế

- Định nghĩa remote file generation ID, không dựa riêng filename/mtime.
- Dùng temporary name + atomic rename/handoff khi remote contract hỗ trợ.
- Phân biệt **downloaded**, **queued**, **processed**, **uploaded**, **confirmed**.
- Cẩn trọng khi nhiều replicas cùng poll remote source; phối hợp filter/lock.
- Kiểm tra remote status/size/checksum theo policy trước retry upload.
- Không để database transaction bao trùm transfer dài.

## 24. HTTP inbound/outbound gateway: response và transaction khác nhau

### 24.1. HTTP inbound

HTTP client retry khi timeout hoặc connection reset. Một persistent message store giúp **sau khi commit** work item có thể tồn tại qua restart; nhưng nếu phản hồi trước commit, client có thể nghĩ request đã được nhận khi thực ra chưa durable.

Khi nhận request có tác dụng phụ:

1. Authenticate, authorize và validate request.
2. Kiểm tra idempotency key theo tenant/operation.
3. Commit durable work item/inbox marker trước `202` nếu hợp đồng yêu cầu.
4. Trả opaque reference/status URL theo policy.
5. Worker xử lý sau, lưu business completion và cung cấp status/callback.

### 24.2. HTTP outbound

Đặt remote HTTP call trong một JDBC transaction **không** đưa remote server vào transaction đó. Nếu timeout sau remote commit:

- Local transaction có thể rollback, message được nhận lại.
- Retry có thể gọi remote lần hai.
- Phải dùng **remote idempotency key**, readback/reconciliation hoặc compensating workflow.

### 24.3. Response 200/202 không tự nói business done

HTTP 200 có thể chứa mã lỗi nghiệp vụ; 202 thường chỉ accepted async. SLI và completion marker phải theo **hợp đồng đích**, không chỉ status class.

## 25. JMS: local message store và broker ACK là hai resource

JMS consumer có thể nhận một message, đưa vào local persistent MessageStore rồi ACK broker. Muốn tránh mất message, **local store commit phải hoàn tất trước broker ACK** theo thiết kế. Nếu store commit xong mà ACK broker thất bại, JMS có thể redeliver → local receiver cần idempotent key.

### 25.1. Hai chiến lược dễ nhầm

| Chiến lược | Lợi ích | Rủi ro |
|---|---|---|
| ACK JMS trước khi DB store commit | Ít redelivery | DB fail sau ACK có thể làm mất message |
| Commit DB store trước ACK JMS | Không mất durable work item vì ACK sớm | ACK fail gây duplicate, cần dedup |
| Coordinate transaction bằng cơ chế phù hợp | Có thể giảm cửa sổ sai lệch | Cấu hình phức tạp; phải kiểm thử guarantees |

### 25.2. Trường hợp handler có business DB update

Nếu JMS consumer gọi domain service trong cùng một local DB transaction và sau đó ACK, phải xem **container transaction/ack mode, exception handling và synchronization**. `@Transactional` không tự đảm bảo JMS ACK và JDBC transaction nguyên tử. Một consumer được giao lại nên có **unique business event marker** để tránh side effect trùng.

### 25.3. Redelivery và DLQ

JMS redelivery không nên bị đếm thành nhiều business events. Thiết kế retry budget, backoff và DLQ theo provider; nếu DB store đã nhận message rồi broker redeliver, idempotent ingress ngăn chèn duplicate work item không cần thiết.

## 26. AMQP/RabbitMQ: publisher confirm khác consumer ACK

Với AMQP, cần phân biệt:

- **Publish attempt** tại outbound adapter.
- **Publisher confirm** theo broker protocol.
- **Consumer delivery** và prefetch.
- **ACK/NACK/requeue** từ consumer.
- **Business transaction commit** trong database.

Một Spring Integration persistent message store chỉ bảo vệ phần **message trong local DB**. Broker ACK/NACK không tự tham gia local SQL transaction. Nếu DB commit rồi consumer crash trước ACK, RabbitMQ có thể redeliver; nên giữ **business idempotency key**.

### 26.1. Poison-message loop

Nếu lỗi schema khiến handler luôn rollback, cùng message có thể bị requeue vô hạn. Cần **bounded retry, DLQ và error classification**, không chỉ tăng số consumers. Đừng đưa raw body vào log; error message có thể chứa dữ liệu nhạy cảm.

### 26.2. Outbound transactional handoff

Ghi outbox row trong cùng DB transaction với business effect, dispatcher publish AMQP với stable outbound command ID, theo dõi confirm/return. Khi dispatcher crash sau confirm nhưng trước update outbox status, publisher có thể gửi lại; consumer đích cần idempotent receiver.

## 27. Kafka: offset commit không tự đồng bộ với JDBC MessageStore

Kafka consumer có thể nhận record, lưu vào local message store, commit offset. Cửa sổ crash:

| Thời điểm | Kết quả có thể xảy ra |
|---|---|
| Trước store commit | Record chưa durable ở local, chưa nên coi đã nhận xong |
| Store commit, chưa offset commit | Kafka có thể redeliver, gây duplicate enqueue |
| Offset commit, store commit chưa chắc | Có nguy cơ mất work item nếu store fail |
| Worker hoàn tất DB nhưng chưa commit local dequeue | Redelivery từ local queue, cần idempotency |
| Outbound Kafka publish success nhưng DB/outbox status chưa cập nhật | Có thể publish trùng khi retry |

### 27.1. Kafka transaction không thay database transaction

Kafka transactions/idempotent producer có những guarantee trong phạm vi Kafka và cấu hình consumer/producer tương ứng. **Local JDBC transaction của MessageStore không tự là một transaction Kafka**. Nếu có coordination/synchronization riêng, phải test failure windows thay vì suy “exactly once” từ tên tính năng.

### 27.2. Thiết kế thực tế

- Dùng stable business event ID ở inbound khi producer có thể gửi lại.
- Commit durable inbox/store trước offset ACK theo policy.
- Áp idempotent receiver tại handler và target.
- Với consume–DB update–produce, cân nhắc **transactional inbox/outbox**.
- Theo dõi Kafka topic/partition/offset, lag, rebalance và DLQ riêng với local queue metrics.
- Không dùng trace ID hoặc Spring Message ID làm dedup key của logical event.

## 28. JDBC inbound/outbound: nơi thuận lợi nhất để ghép transaction

Nếu nguồn JDBC, message store và business tables ở **cùng database và cùng transaction manager**, việc cập nhật source status/marker, durable message storage và domain state có thể nằm trong một transaction.

### 28.1. Ví dụ thiết kế polling

~~~text
BEGIN TX
  SELECT eligible rows with claim/lock strategy
  INSERT durable work item / inbox if not processed
  UPDATE source row as enqueued
COMMIT

Later:
BEGIN TX
  DEQUEUE durable work item
  APPLY domain operation idempotently
  INSERT outbox intent if needed
COMMIT
~~~

Ví dụ là **logical transaction sketch**, không phải SQL/API cụ thể. Cơ chế select-for-update/skip-locked và transaction scheduling tùy database; kiểm tra race giữa nhiều pollers.

### 28.2. Nếu JDBC source ở database khác

Không mặc định transaction manager của business DB bao phủ JDBC source khác. Có thể cần reliable polling with idempotency, inbox/ledger và reconciliation; **XA/JTA** nếu thật sự bắt buộc và tất cả resources hỗ trợ, nhưng chi phí/độ phức tạp cần được đánh giá.

### 28.3. Watermark không thay completed marker

`last_processed_id` hoặc `updated_at` hỗ trợ quét nguồn; nhưng khi event đến muộn, transaction rollback hoặc rows đổi thứ tự, watermark có thể bỏ sót/đọc lại. **Store transaction + idempotency + versioning** giải quyết các yêu cầu khác nhau.

## 29. Transactional Inbox/Outbox kết hợp MessageStore

Một **Transaction-aware MessageStore** giải quyết phần lưu và nhận message bền vững trong ứng dụng, nhưng khi nghiệp vụ cần “đã nhận event thì chắc chắn phát một command khác”, mô hình **Inbox/Transactional Outbox** thường đơn giản để kiểm chứng hơn việc giữ transaction mở xuyên network.

### 29.1. Thiết kế local transaction

~~~mermaid
flowchart TD
    IN[Inbound Delivery] --> KEY[Validate business event key]
    KEY --> TX[Begin local DB TX]
    TX --> INBOX[Insert unique inbox marker]
    INBOX --> DOMAIN[Update domain state]
    DOMAIN --> OUTBOX[Insert outbound intent]
    OUTBOX --> COMMIT[Commit DB TX]
    COMMIT --> ACK[ACK ingress or return accepted]
    COMMIT --> D[Outbox Dispatcher]
    D --> REMOTE[External Target]
    REMOTE --> CONFIRM[ACK / Status / Reconcile]
    CONFIRM --> DONE[Mark outbound outcome]
~~~

### 29.2. PostgreSQL schema minh họa

~~~sql
CREATE TABLE integration_inbox (
    tenant_ref     varchar(80)  NOT NULL,
    event_id       varchar(160) NOT NULL,
    operation      varchar(80)  NOT NULL,
    processed_at   timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_ref, event_id, operation)
);

CREATE TABLE integration_outbox (
    command_id     varchar(160) PRIMARY KEY,
    event_ref      varchar(160) NOT NULL,
    target_alias   varchar(80)  NOT NULL,
    payload_json   jsonb        NOT NULL,
    state          varchar(32)  NOT NULL,
    attempt_count  integer      NOT NULL DEFAULT 0,
    created_at     timestamptz  NOT NULL DEFAULT now()
);
~~~

Đây là **schema ứng dụng riêng**, không phải bảng nội bộ của Spring Integration JDBC. `payload_json` có thể chứa PII nên cần encryption/ACL/retention phù hợp; production cần indexes, version, lease/retry, audit, uniqueness theo business semantics và schema migration được kiểm thử.

### 29.3. Pseudocode transaction

~~~text
processInbound(event):
    validateAuthSchemaBusinessKey(event)
    BEGIN local DB transaction
        if not insertUniqueInboxKey(event.key):
            return ALREADY_COMMITTED
        applyBusinessChange(event)
        insertOutboxCommand(stableCommandId, approvedPayload)
    COMMIT
    acknowledgeInboundAccordingToTransport()

dispatchOutbox(command):
    claimPendingCommandWithLease(command.id)
    sendToRemoteUsingStableIdempotencyKey(command.id)
    if remoteConfirmed:
        markConfirmed()
    else if timeoutAndUnknown:
        markUnknownAndReconcile()
    else:
        retryWithBoundedBackoff()
~~~

### 29.4. Điểm cần hiểu đúng

- Inbox marker chặn **domain update trùng** trong cùng transaction.
- Outbox row bảo vệ **ý định gửi**, kể cả JVM chết sau commit.
- Dispatcher có thể gửi **hơn một lần** nếu crash sau remote ACK nhưng trước lúc cập nhật outbox.
- Remote cần idempotency key/correlation hoặc reconciliation để tránh **external duplicate effect**.
- Với persistent `QueueChannel`, có thể dùng nó làm lớp durable handoff, nhưng phải tránh **ghi hai nơi không cùng transaction** mà không rõ nguồn nào là authority.

## 30. XA/JTA, local transactions và transaction synchronization

Đôi khi hệ thống cần một transaction trải qua nhiều resource managers. **XA/JTA** có thể điều phối các tài nguyên có hỗ trợ đúng chuẩn, nhưng không phải mọi adapter/broker/API đều hỗ trợ. Việc triển khai distributed transaction cần đánh giá throughput, recovery log, timeout, failure-in-doubt và vận hành.

### 30.1. Bảng lựa chọn

| Mô hình | Atomic trong phạm vi nào? | Khi phù hợp |
|---|---|---|
| **Local JDBC TX** | Cùng JDBC resource/manager được enlist | DB-backed queue + domain tables |
| **Local TX + Outbox** | Domain state + durable send intent | Gửi event/HTTP/broker an toàn sau commit |
| **Remote idempotency + reconciliation** | Tác dụng phụ tại remote theo contract | Payment API, file handoff, create resource |
| **XA/JTA** | Các XA resources tham gia transaction | Yêu cầu đặc thù, đã kiểm thử failure recovery |
| **Saga/compensation** | Nhiều local transactions với bước bù | Workflow phân tán dài hoặc không hỗ trợ XA |
| **Best-effort sync** | Thứ tự hành động, không có atomicity toàn cục | Chỉ khi chấp nhận và xử lý được rủi ro |

### 30.2. Chọn đơn giản nhất đáp ứng yêu cầu

Nếu yêu cầu chỉ là “không mất message khi JVM restart”, persistent queue có thể đủ. Nếu yêu cầu “không trừ tiền hai lần dù HTTP timeout”, cần **remote idempotency/domain ledger**. Nếu yêu cầu “DB update và event publish không mất”, có thể dùng outbox. Không mặc định bật XA/JTA cho mọi connector chỉ vì tên bài có chữ transaction.

## 31. Định nghĩa hợp đồng lỗi và state cho persistent work item

Để vận hành an toàn, một message/persistent work item nên được giải thích bằng trạng thái có ý nghĩa:

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> STORED: Commit ingress
    STORED --> PROCESSING: Poll/claim
    PROCESSING --> COMPLETED: Local effect commit
    PROCESSING --> STORED: Transaction rollback, retry
    PROCESSING --> UNKNOWN: External timeout
    UNKNOWN --> COMPLETED: Target confirms
    UNKNOWN --> STORED: Reconciled safe to retry
    PROCESSING --> FAILED_TERMINAL: Permanent error after policy
    FAILED_TERMINAL --> REPLAY_PENDING: Approved replay
    REPLAY_PENDING --> STORED: New controlled attempt
~~~

**Đây là state machine ứng dụng minh họa**, không phải các state được `JdbcChannelMessageStore` tạo mặc định. Store có thể quản lý rows/transaction mà không lưu đủ `UNKNOWN`, `FAILED_TERMINAL` hoặc remote receipt; các trạng thái này cần một business ledger/side table riêng khi cần.

### 31.1. Không coi mất row queue là hoàn tất

Row biến mất khỏi persistent queue sau dequeue commit chưa chứng minh:

- Handler đã gửi thành công HTTP.
- Kafka consumer downstream đã lưu database.
- File/SFTP output đã được đối tác nhận.
- DLQ publish đã thành công.
- Business operation không bị duplicate.

Hoàn tất phải có **completion marker** ở nơi giữ authority cho hợp đồng được định nghĩa.

## 32. Performance và capacity planning cho MessageStore

Persistent store tăng độ bền nhưng đổi lấy disk I/O, serialization, connection usage và transaction contention. Đây là **trade-off** cần đo bằng workload thật.

### 32.1. Các chỉ số quan trọng

| Chỉ số | Câu hỏi |
|---|---|
| **Ingress committed/s** | Tốc độ message được ghi bền vững |
| **Committed dequeue/s** | Tốc độ message được nhận/xử lý hoàn tất |
| **Pending message count** | Có bao nhiêu work item đang đợi |
| **Oldest pending age** | Sự kiện cũ nhất bị trễ bao lâu |
| **Transaction duration p95/p99** | Có TX đang giữ lock quá lâu |
| **DB pool wait/active** | Connection pool có bão hòa |
| **Deadlock/lock timeout rate** | Có contention giữa consumers/groups |
| **Serialization failures** | Message có thể lưu/đọc giữa versions |
| **Store error rate** | SQL/schema/permission/network issues |
| **Outbox unknown outcomes** | Remote may-have-committed chưa được đối soát |
| **Duplicate/retry attempts** | Transport hoặc business đang giao lại |
| **Cleanup/retention lag** | Rows/messages quá hạn chưa được dọn đúng policy |

### 32.2. Backpressure đúng chỗ

Nếu ingress tăng nhanh hơn dequeue:

~~~text
pending_next ≈ pending_current + stored_committed - processed_committed
~~~

Biểu thức là **xấp xỉ**, cần tính thêm retries, poison messages, re-enqueue, expiry, group release và các luồng khác. Không tăng poller concurrency vô hạn: có thể làm database lock contention, remote rate limit hoặc executor saturation trầm trọng hơn.

### 32.3. Tối ưu an toàn

1. Giữ transaction ngắn; tránh gọi remote I/O trong local DB lock.
2. Dùng chỉ số backlog age thay vì chỉ queue depth.
3. Chọn schema/index và query provider phù hợp database.
4. Giới hạn message size; cân nhắc lưu payload lớn ở object store có ACL.
5. Đo retry storm, deadlocks và connection pool trước khi tăng consumers.
6. Dùng pagination/batch/retention policy tương thích store.
7. Có quota/capacity alert trước khi disk hoặc DB pool cạn.
8. Thiết kế cleanup chỉ cho **state đã an toàn**, không xóa pending để “giảm disk”.

## 33. Bảo mật dữ liệu trong store và quyền quản trị

Khác với một queue RAM, persistent MessageStore có thể lưu đầy đủ message trong database và được đưa vào backup, replication, SQL debug, audit và support export.

### 33.1. Các nguy cơ chính

- Payload/headers chứa PII, thông tin thanh toán, tokens hoặc nội dung file nhạy cảm.
- `replyChannel`, `errorChannel` hoặc runtime object không phù hợp serializer.
- SQL log bật bind-parameters khiến payload bị nhân bản sang hệ logs.
- Quản trị viên thao tác xóa/purge các rows chưa xử lý.
- Store account được cấp quyền schema rộng hơn cần thiết.
- Snapshot/backup tồn tại quá thời hạn dữ liệu nghiệp vụ.
- ErrorMessage/DLQ chứa original payload nhạy cảm.
- Một message đến từ nguồn không đáng tin kích hoạt unsafe deserialization.

### 33.2. Kiểm soát khuyến nghị

1. Phân loại payload/headers **trước khi lưu**.
2. Dùng serializer/converter có schema/version và type validation.
3. Encryption in transit/at rest, DB credentials trong secret manager.
4. Áp RBAC/least privilege cho ứng dụng, DBA, backup và monitoring.
5. Giữ retention theo business/compliance; xóa dữ liệu an toàn sau khi đủ điều kiện.
6. Log metadata như flow, opaque correlation, attempt, error class, **không dump raw message**.
7. Bảo vệ DLQ, outbox và group store cùng mức với nguồn message.
8. Mọi thao tác purge/replay/repair trên production cần owner, audit và approval phù hợp.

## 34. Testing: phải kiểm tra failure boundaries, không chỉ happy path

Một bài test có persistent store không đủ nếu chỉ gửi một message rồi nhận một message. Cần kiểm chứng **commit, rollback, restart, multi-instance, schema và external side effect**.

### 34.1. Ma trận kiểm thử

| Test case | Thao tác/sự cố | Kết quả cần xác minh |
|---|---|---|
| **Store commit** | Gửi một message rồi commit | Sau tạo context mới vẫn đọc được |
| **Ingress rollback** | Transaction ghi store ném lỗi trước commit | Không có durable work item giả |
| **Dequeue rollback** | Poller TX nhận message, handler ném exception | Message còn/được đưa lại đúng theo store TX |
| **Dequeue commit** | Handler local DB thành công | Message được remove đúng một lần tại boundary |
| **Different DataSources** | Store và domain DB dùng managers khác | Chứng minh rollback **không** nguyên tử, test phát hiện |
| **Self-invocation** | Transaction annotation không qua proxy | Test transaction thực sự được mở |
| **Async boundary** | ExecutorChannel tách handler ra thread khác | Không giả định poller TX còn bao phủ |
| **DB deadlock** | Hai consumers tranh lock | Retry/backoff, message không mất |
| **Process crash** | Kill JVM trước/sau commit | Tồn tại hoặc redelivery theo ma trận |
| **Restart with old DTO** | Đọc message serialized ở release trước | Migration/compatibility thành công hoặc xử lý có kiểm soát |
| **Group timeout** | Aggregator thiếu parts | Expiration/partial result theo policy |
| **Group release crash** | Crash giữa complete và outbound | Output không mất hoặc có replay bền vững |
| **JMS redelivery** | ACK fail sau DB commit | Không áp side effect trùng |
| **AMQP NACK** | Consumer rollback/requeue | Retry/DLQ đúng policy |
| **Kafka rebalance** | Offset chưa commit | Business idempotency hoạt động |
| **HTTP timeout after commit** | Remote đã commit nhưng client không thấy | Reconcile/idempotency, không double effect |
| **SFTP interrupted upload** | Remote giữ partial file | Recovery/handoff không tạo final file lỗi |
| **Store unavailable** | DB lỗi kết nối | Không ACK thành công trước durable commit |
| **Multi-pod** | Hai instances cùng poll/claim | Không double commit hoặc mất ordering contract |
| **Retention cleanup** | Message/marker cũ được dọn | Không xóa pending/unknown quan trọng |

### 34.2. Chọn đúng loại test

- **Unit tests:** business key, release strategy, error classification.
- **Integration tests:** JDBC store/schema, poller transaction advice, rollback với database thật.
- **Failure tests:** kill process, network partition, crash ở checkpoint và restart.
- **Protocol tests:** broker ACK/commit, HTTP timeout, SFTP transfer, DB transaction.
- **Compatibility tests:** messages được viết bằng version trước đọc trên version mới.
- **Security tests:** payload/headers nhạy cảm không rò vào logs/metrics/export và ACL đúng.

`SimpleMetadataStore` hoặc in-memory `QueueChannel` không thể thay bài test persistence/JDBC rollback khi mục tiêu là transaction-aware storage.

## 35. Ví dụ kiểm thử transaction rollback ở mức hợp đồng

### 35.1. Test specification

~~~text
Given:
  - JDBC-backed QueueChannel và polling consumer đã cấu hình
  - Store, business table dùng cùng DataSource + transaction manager
  - Một message hợp lệ đã được ghi và committed trong queue
  - Handler đồng bộ, sẽ throw RuntimeException sau khi update business table

When:
  - Poller nhận message và chạy handler trong transaction

Then:
  - Business update KHÔNG được commit
  - Transactional dequeue KHÔNG biến message thành mất vĩnh viễn
  - Retry có thể thấy lại message theo queue/store semantics
  - Error logs không dump raw payload

When:
  - Sửa điều kiện lỗi và cho poller xử lý lại

Then:
  - Business update committed đúng một lần theo idempotency policy
  - Queue state phản ánh message đã được xử lý
~~~

Đây là **đặc tả kiểm thử**, chưa phải JUnit đã chạy. Cần xác định cách quan sát queue bằng API/counters thích hợp và tránh test dựa trên race timing mong manh. Nếu retry có backoff hoặc poller async, dùng synchronization/eventual assertions thay vì `Thread.sleep` cố định.

### 35.2. Ví dụ kiểm tra local transaction bằng Spring JDBC

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LocalStoreAndDomainWriter {
    private final JdbcTemplate jdbc;

    public LocalStoreAndDomainWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void writeTwoDomainRowsThenFail() {
        jdbc.update("INSERT INTO demo_a(id) VALUES (?)", 901);
        jdbc.update("INSERT INTO demo_b(id) VALUES (?)", 901);
        throw new IllegalStateException("INTENTIONAL_TEST_FAILURE");
    }
}
~~~

Ví dụ chỉ minh họa **rollback của hai JDBC updates trong cùng transaction** nếu bean được gọi qua Spring proxy và test dùng đúng transaction manager. Nó **không kiểm thử QueueChannel**. Với MessageStore, hãy kết hợp store add/dequeue thực tế vào cùng integration test mới có thể chứng minh store tham gia transaction tương ứng.

### 35.3. Test “remote đã commit, local rollback”

Cho fake HTTP server lưu một command ID rồi cố ý **không trả response**. Local handler timeout, local DB transaction rollback và message được giao lại. Test kỳ vọng:

1. Receiver ghi `UNKNOWN_OUTCOME` và không coi chắc remote fail.
2. Retry giữ **cùng remote idempotency key**, hoặc readback trước khi gọi lại.
3. Remote chỉ áp một business effect dù có nhiều attempts.
4. Log/Micrometer tách attempt count và unique completed count.

## 36. Runbook TXSTORE-01 — Message biến mất sau khi handler lỗi

**Trigger:** một inbound event đã accepted nhưng không còn trong queue và business DB/target không có kết quả.

1. Tìm **opaque correlation/event reference**, xác nhận nguồn, instance và khoảng thời gian.
2. Phân biệt ingress chỉ được nhận trong RAM, đã gọi `send()` hay **đã commit JDBC store**.
3. Kiểm tra store schema/query/provider, SQL exceptions, connection pool, transaction logs và rows pending.
4. Xem consumer poller có **transaction advice bắt đầu trước receive** hay chỉ handler có `@Transactional`.
5. Xem store và domain updates có cùng DataSource/manager/thread không.
6. Tìm exception bị nuốt bởi error handler hoặc retry advice làm commit ngoài ý muốn.
7. Kiểm tra async handoff sang executor/queue khác có bẻ transaction boundary không.
8. Xác định message đã được chuyển DLQ, parking lot, expired group hay outbox chưa.
9. Đối chiếu broker ACK/offset, file/SFTP state và external target outcome trước khi replay.
10. Không tự xóa/purge DB rows hoặc thêm message trùng; tạo recovery plan có approval nếu chưa biết side effect.
11. Sửa boundary/config và thêm crash/rollback integration test đúng lỗi tái hiện.
12. Đóng incident khi có evidence **durable recovery + business completion**, không chỉ state queue bằng 0.

### 36.1. Các nguyên nhân phổ biến

| Triệu chứng | Nghi vấn |
|---|---|
| Queue in-memory trống sau restart | Không có persistent store |
| DB đã remove message nhưng domain rollback | Receive ngoài TX hoặc resource managers khác |
| Handler exception mà message bị commit remove | Exception bị catch/nuốt, rollback-only không set |
| Có state trong store nhưng không deserialize được | DTO/schema/serializer incompatibility |
| Aggregator complete mà không thấy output | Group release và output send không durable cùng boundary |
| Source JMS/Kafka ACK rồi store không có row | Ingress ACK xảy ra trước durable commit |

## 37. Runbook TXSTORE-02 — Backlog và DB locks tăng mạnh

**Trigger:** pending rows/queue age tăng, DB pool bão hòa, deadlock hoặc poller timeouts.

1. Đo ingress committed/s, dequeue committed/s, oldest pending age, retry/error rate.
2. Xác định store query duration, lock wait, deadlocks và connection pool saturation.
3. Kiểm tra handler có giữ transaction trong lúc gọi HTTP/SFTP/Kafka chậm không.
4. Xem concurrency/poller batch size vượt capacity DB hay remote target.
5. Phân loại poison messages và retry loops; đưa sang parked/DLQ theo policy nếu cần.
6. Kiểm tra indexes/query plan và schema version của JDBC store.
7. Nếu cần throttle ingress, đánh giá HTTP response/ACK và nguồn backlog; không âm thầm nhận rồi mất work.
8. Không tăng consumer threads hay truncate queue tables mù quáng.
9. Áp bounded concurrency, transaction ngắn, outbox dispatcher, backoff và capacity review.
10. Theo dõi backlog age, error rate, remote confirmed events và unique completions sau remediation.

## 38. Mười hai tình huống thực hành

### Tình huống A — HTTP đã trả 202 nhưng JVM chết

HTTP inbound gateway trả 202 ngay sau khi đưa message vào QueueChannel RAM; JVM crash trước khi consumer nhận.

**Phân tích:** 202 đã đưa lời hứa xử lý bền vững mà queue không đáp ứng. Cần commit persistent store/inbox trước accepted response hoặc đổi contract; xác minh lại request bằng opaque reference và idempotency, không suy còn message sau restart.

### Tình huống B — Persistent QueueChannel nhưng dequeue ngoài TX

Handler có `@Transactional`, nhận message rồi cập nhật DB và ném exception. DB rollback, queue message không trở lại.

**Phân tích:** transaction của handler mở **sau khi receive**. Cần poller transaction advice trước dequeue, cùng DataSource/manager và integration test rollback; tránh async boundary phá transaction.

### Tình huống C — JMS redelivery sau local DB commit

Consumer đã commit domain state, nhưng mất ACK JMS nên broker gửi lại message.

**Phân tích:** local transaction không bảo đảm JMS ACK; idempotent receiver/unique event marker khiến lần hai không áp effect trùng, rồi ACK an toàn.

### Tình huống D — Kafka offset commit trước durable enqueue

Consumer commit offset trong khi SQL insert tới message store chưa commit; DB mất kết nối.

**Phân tích:** record có nguy cơ bị bỏ qua dù local queue chưa giữ durable copy. Đổi thứ tự/coordination phù hợp, test crash window và điều tra broker retention trước recovery.

### Tình huống E — SFTP file đã move trước khi store commit

File inbound được chuyển sang archive, sau đó JDBC store fail và rollback.

**Phân tích:** file move không rollback theo JDBC TX. Cần restore/requeue từ archive theo policy, thiết kế checkpoint/handoff rõ và tránh xóa file nguồn quá sớm.

### Tình huống F — HTTP outbound timeout sau remote commit

Message được lấy từ persistent queue trong JDBC TX, gọi remote API và timeout. TX rollback nên message được nhận lại.

**Phân tích:** remote có thể đã commit. Cần stable remote idempotency key và reconciliation; không coi rollback local là đảo ngược remote payment.

### Tình huống G — Aggregator complete nhưng mất result

Group state được ghi `complete`; aggregator dispatch kết quả vào channel RAM rồi process crash.

**Phân tích:** group persistence không bảo đảm output durable. Cần transactional outbox/durable result handoff và result idempotency, kiểm thử crash đúng khoảng trống.

### Tình huống H — Hai replicas xử lý một group cùng lúc

Hai JVM dùng group store nhưng không kiểm soát concurrency/release; cả hai phát aggregate result.

**Phân tích:** xem LockRegistry/DB isolation/claim và release semantics, cùng result ID + idempotent downstream; phải thử race trên nhiều instances.

### Tình huống I — Message cũ không deserialize sau deploy

Queue lưu serialized Java object của phiên bản A. Sau deploy B thay class structure, worker không đọc được.

**Phân tích:** cần version-aware serializer/schema migration, backward compatibility hoặc planned drain; không xóa pending rows để “sửa nhanh”.

### Tình huống J — Poller database giữ khóa quá lâu

Polling consumer mở transaction rồi gọi remote SFTP upload chậm 45 giây; các consumers khác bị lock timeout.

**Phân tích:** chuyển external I/O ra khỏi local DB transaction bằng outbox và dispatcher, giới hạn concurrency, đo lock wait và queue age.

### Tình huống K — DLQ publish thành công nhưng dequeue rollback

Handler publish vào AMQP DLQ rồi một SQL statement ném lỗi; local transaction rollback. Lần sau message lại được gửi DLQ.

**Phân tích:** DLQ send không cùng JDBC transaction. Cần durable failure intent/outbox và DLQ consumer idempotency; không cho rằng message chỉ xuất hiện một lần vì error handler được gọi một lần.

### Tình huống L — File batch bị xóa bởi group reaper

Aggregator chờ đủ 20 parts; chỉ có 18 parts đến, reaper cleanup group và mất khả năng phân tích.

**Phân tích:** định nghĩa timeout/expiry, retention, partial-failure policy, DLQ/parking, audit và recovery. Không coi expiration = business success.

## 39. Checklist triển khai Transaction-aware MessageStore

### 39.1. Hợp đồng message và store

- [ ] Đã xác định mục tiêu: durable queue, message group, inbox hay outbound intent?
- [ ] `MessageStore`, `ChannelMessageStore`, `MessageGroupStore` có được dùng đúng phạm vi?
- [ ] Có schema/dialect/query provider tương thích Spring Integration version?
- [ ] Payload/headers có serializer an toàn, versioned và được phép lưu?
- [ ] Message size, retention, encryption, ACL và backup được quy định?
- [ ] Có idempotent business key và distinction giữa delivery/processing attempts?

### 39.2. Transaction/ACK

- [ ] Transaction được mở **trước lúc receive/dequeue** khi cần rollback message?
- [ ] Store và business DB thực sự dùng cùng DataSource/manager/transaction?
- [ ] Handler xử lý đồng bộ trong boundary hay có async thread break?
- [ ] Exception khiến rollback đúng policy, không bị nuốt?
- [ ] Ingress response/ACK chỉ được emit sau durable commit theo contract?
- [ ] JMS/AMQP ACK và Kafka offset được kiểm tra độc lập DB transaction?
- [ ] Không gọi remote API dài trong DB lock nếu có thể dùng outbox?
- [ ] Timeout có `UNKNOWN_OUTCOME` và reconciliation trước retry?

### 39.3. Aggregation và concurrency

- [ ] Group ID, release strategy, duplicate parts và late arrivals có policy?
- [ ] Completed group và output release có durable handoff?
- [ ] Có locking/transaction strategy cho nhiều pollers/instances?
- [ ] Reaper/expiry không xóa pending hoặc unknown business state sai?
- [ ] Queue ordering/priority có được hiểu đúng, không suy FIFO tuyệt đối?

### 39.4. Kiểm thử và vận hành

- [ ] Có test ingress commit, rollback dequeue, handler failure và crash/restart?
- [ ] Có test DB manager khác nhau, async handoff và self-invocation?
- [ ] Có test broker redelivery, HTTP timeout sau remote commit, SFTP partial transfer?
- [ ] Có test schema migration và serialized message từ release trước?
- [ ] Có test multi-instance race và aggregation release failure?
- [ ] Có dashboard pending count/age, DB locks/pool, retries/DLQ và remote outcome?
- [ ] Có runbook cho mất message, kẹt backlog, unknown outcome?
- [ ] Không purge/delete records để xử lý sự cố khi chưa có audit/approval?

## 40. Tổng kết

**Transaction-aware MessageStore** là nền tảng giúp Spring Integration xử lý message bền vững và nhất quán trong **phạm vi transaction có thể kiểm chứng**. Với `QueueChannel` hoặc aggregator dùng JDBC store, câu hỏi quan trọng không phải chỉ là “có lưu xuống database không”, mà là **store operation, receive/dequeue, business update, group state và completion marker có commit/rollback đúng ranh giới hay không**.

Trong các luồng **File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC**, mỗi adapter có cơ chế ACK, transaction, retry và connection lifecycle riêng. **Local JDBC rollback không kéo theo remote HTTP/file/broker rollback**. Vì vậy cần kết hợp **persistent store, transaction-aware poller/handler, stable idempotency key, Inbox/Transactional Outbox, target confirmation/reconciliation, monitoring backlog và failure-injection tests**.

Một hệ thống đúng không chỉ “không mất queue row”, mà phải chứng minh rõ **message đã được nhận bền vững, side effect nào đã commit, lần giao lại nào an toàn và ai chịu trách nhiệm cho những kết quả chưa biết**. Đó là cách dùng Transaction-aware MessageStore để xây dựng các integration flows có thể phục hồi, kiểm toán và mở rộng mà không tuyên bố sai về exactly-once end-to-end.


