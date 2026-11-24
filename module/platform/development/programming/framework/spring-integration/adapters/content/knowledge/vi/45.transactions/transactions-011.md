# Tránh giữ transaction khi gọi dịch vụ chậm trong Spring Integration Adapters

## 1. Mục tiêu: transaction ngắn, kết quả đáng tin cậy

Trong hệ thống **Spring Integration Adapters**, một message có thể được nhận qua file/SFTP, HTTP, JMS, AMQP, Kafka hoặc database, đi qua `MessageChannel`, transformer, filter, gateway và cuối cùng tạo tác động ở một hệ thống khác. Bẫy thường gặp là mở **transaction cơ sở dữ liệu**, cập nhật một bản ghi, rồi **giữ nguyên transaction trong lúc chờ** HTTP API, SFTP server, broker hoặc dịch vụ bên thứ ba đáp ứng.

Cách triển khai này có thể chạy tốt ở môi trường phát triển nhưng khi dịch vụ ngoài chậm hoặc có timeout, hệ thống phải giữ kết nối, khóa và tài nguyên giao dịch lâu hơn nhiều so với thao tác database cần thiết. Hậu quả là contention, backlog, timeout dây chuyền, deadlock, pool exhaustion, ghi dữ liệu không nhất quán và những lần retry không an toàn.

**Nguyên tắc trung tâm:** chỉ giữ transaction bao quanh các thao tác thực sự cần tính nguyên tử trong **cùng phạm vi tài nguyên giao dịch**. Nếu phải gọi dịch vụ bên ngoài, hãy thiết kế điểm tách rõ: **commit trạng thái nội bộ trước**, thực hiện I/O ở ngoài transaction database, rồi ghi nhận kết quả bằng transaction ngắn khác; khi cần giao hàng đáng tin cậy, dùng **transactional outbox + dispatcher + idempotent consumer/partner** thay vì chỉ tách bằng một lệnh gọi bất đồng bộ.

Sau bài học, bạn cần có khả năng:

1. Giải thích vì sao một remote call chậm có thể làm tăng thời gian giữ JDBC connection, row lock, transaction log và mức tranh chấp.
2. Phân biệt **database transaction**, **JMS/Kafka/broker transaction**, **Spring transaction synchronization** và **tính nhất quán nghiệp vụ xuyên hệ thống**.
3. Nhận biết nơi transaction lan truyền qua `@Transactional`, `TransactionTemplate`, `DirectChannel`, poller, `ExecutorChannel` và gateway.
4. Thiết kế **short local transaction** không giữ tài nguyên DB khi chờ HTTP/SFTP/JMS/AMQP/Kafka.
5. Áp dụng outbox, retry/backoff, idempotency key, trạng thái trung gian, reconciliation và compensation theo rủi ro.
6. Viết test chứng minh **external call thực sự xảy ra ngoài transaction**, không chỉ nhận được message.
7. Biết khi nào chấp nhận trade-off của đồng bộ, khi nào dùng queue/outbox và cách vận hành khi đích chậm hoặc không sẵn sàng.

**Phạm vi:** kiến thức áp dụng cho Spring Boot + Spring Integration với inbound/outbound adapter, gateway, poller, MessageChannel và các luồng file, SFTP, HTTP, JMS, AMQP, Kafka, JDBC. Những API/annotation được minh họa theo các thế hệ Spring hiện đại; luôn kiểm tra version thực tế của dự án trước khi áp dụng.

## 2. Transaction là gì, và cái gì *không* nằm trong nó?

Một transaction database có các ranh giới như **begin → các thao tác JDBC/JPA → commit/rollback**. Trong một database có cấu hình phù hợp, các thao tác trong transaction có thể nguyên tử và tuân theo mức isolation. Nhưng khi thêm một HTTP POST hoặc SFTP upload giữa các thao tác đó, **local DB transaction không tự biến HTTP/SFTP thành thành viên của cùng giao dịch**.

~~~mermaid
sequenceDiagram
    participant I as Input / MessageChannel
    participant S as Spring service
    participant D as Database
    participant P as Partner HTTP/SFTP
    I->>S: Process command
    S->>D: BEGIN + UPDATE order
    D-->>S: Row locked / DB resource held
    S->>P: POST /shipments (slow)
    Note over S,P: 20 s latency / timeout
    P-->>S: 201 / error / response lost
    S->>D: COMMIT hoặc ROLLBACK
    S-->>I: Result / exception
~~~

Nếu remote call đã thực hiện side effect nhưng response bị mất, DB rollback **không hoàn tác được tác động bên phía đối tác**. Ngược lại, nếu DB commit trước khi gửi remote request mà process chết ngay sau commit, request có thể **chưa từng được gửi**. Đây là lý do phải giải quyết **reliability** riêng, thay vì kéo dài transaction để “bao trùm” một giao thức không tham gia giao dịch.

### 2.1. Bốn khái niệm rất dễ bị đánh đồng

| Cơ chế | Bảo đảm có thể cung cấp | Không được tự suy ra |
|---|---|---|
| **Local JDBC/JPA transaction** | Atomicity/isolation cho tài nguyên DB nằm trong phạm vi transaction | Không rollback được HTTP request hoặc upload SFTP |
| **JMS/AMQP transaction/ack** | Commit/ack/nack trong session hoặc delivery của broker theo cấu hình | Không tự atomic với DB hoặc REST API |
| **Kafka producer transaction** | Atomicity cho các thao tác Kafka thuộc transaction Kafka phù hợp | Không biến SQL/HTTP/SFTP thành cùng một Kafka transaction |
| **Business workflow/saga/outbox** | Phối hợp các local transactions bằng trạng thái, sự kiện, retry và bù trừ | Không mặc nhiên có exactly-once xuyên mọi tài nguyên |

**XA/2PC** có thể phối hợp một số **tài nguyên giao dịch có hỗ trợ** dưới hạ tầng transaction manager tương ứng, nhưng không phải một giải pháp tổng quát cho HTTP/SFTP, có chi phí lock/availability và các rủi ro vận hành riêng. Bài này tập trung vào thiết kế phổ biến hơn: **giao dịch cục bộ ngắn + giao tiếp bên ngoài đáng tin qua trạng thái và idempotency**.

### 2.2. “Giữ connection” có xảy ra từ lúc bắt đầu @Transactional không?

Không nên phát biểu tuyệt đối. Việc lấy connection thực tế phụ thuộc transaction manager, connection pool, JPA provider và cơ chế **lazy acquisition**. Tuy nhiên **sau khi transaction đã thao tác DB**, hệ thống có thể giữ JDBC connection và lock đến lúc hoàn tất. Remote call càng lâu, thời gian giữ tài nguyên đó càng lớn. Cần **đo bằng metric/tracing**, không suy đoán từ annotation.

## 3. Vì sao remote call chậm làm hệ thống sụp theo dây chuyền?

Giả sử một endpoint xử lý 60 message/giây, mỗi transaction thuần DB kéo dài 20 ms. Khi thêm remote HTTP call mất trung bình 3 giây **bên trong transaction**, thời gian giữ tài nguyên tăng hàng trăm lần. Nếu transaction cần một connection liên tục, áp lực lên pool tăng mạnh.

Một quy tắc ước lượng từ **Little's Law** (khi hệ thống ổn định):

\[
L \approx \lambda W
\]

Với \(\lambda\) là thông lượng (yêu cầu/giây) và \(W\) là thời gian trung bình yêu cầu giữ tài nguyên (giây), \(L\) là số yêu cầu đồng thời trung bình đang giữ tài nguyên. Chẳng hạn 40 yêu cầu/giây × 2 giây = **80 yêu cầu đồng thời**; pool 20 connection sẽ chịu tranh chấp nếu mỗi yêu cầu giữ một connection trong khoảng đó. Đây là **mô hình minh họa**, không phải đo đạc của một hệ thống cụ thể; truy vấn, lazy connection, batching và concurrency thực tế có thể thay đổi con số.

| Tác động | Biểu hiện thường thấy |
|---|---|
| **Connection pool exhaustion** | Thread chờ connection, Hikari timeout, latency tăng |
| **Lock contention** | Transaction khác chờ row/table lock, deadlock, timeouts |
| **Transaction dài** | Giữ nhiều state/undo/MVCC snapshot, áp lực vacuum/log tùy DB |
| **Backlog queue/poller** | Message chờ, consumer throughput giảm, retry dồn |
| **Timeout dây chuyền** | HTTP/client timeout → retry → load tăng → timeout nhiều hơn |
| **Không chắc về outcome** | Partner đã xử lý, caller timeout và rollback DB |
| **Gián đoạn shutdown** | Process dừng giữa giao dịch và remote call, chưa rõ kết quả |
| **Suy giảm tính khả dụng** | Dịch vụ ngoài chậm kéo cả database và các chức năng nội bộ chậm |

**Đây không chỉ là vấn đề hiệu năng.** Transaction dài có thể làm tăng xác suất retry và tính không chắc chắn của một side effect đã hoàn thành ở xa.

## 4. Anti-pattern cơ bản: gọi HTTP trong @Transactional

Ví dụ:

~~~java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final ShippingClient shipping;

    public OrderService(OrderRepository orders, ShippingClient shipping) {
        this.orders = orders;
        this.shipping = shipping;
    }

    @Transactional
    public void approveAndSend(String orderId) {
        Order order = orders.findForUpdate(orderId);
        order.markApproved();
        orders.save(order);

        // Sai ranh giới: HTTP có thể chậm nhiều giây hoặc timeout.
        ShipmentReceipt receipt = shipping.reserve(orderId);

        order.markSubmitted(receipt.shipmentId());
        orders.save(order);
    }
}
~~~

`OrderRepository`, `ShippingClient`, `Order` và `ShipmentReceipt` là các kiểu nghiệp vụ minh họa. `findForUpdate` giả định đọc với cơ chế khóa phù hợp; hành vi save/flush/lock cụ thể phụ thuộc JPA/JDBC provider.

**Vấn đề:**

1. Database transaction bắt đầu trước cuộc gọi `shipping.reserve(...)`.
2. Sau khi lấy lock và cập nhật, transaction vẫn mở trong thời gian chờ mạng.
3. Nếu HTTP timeout nhưng remote đã tạo shipment, rollback DB không hủy shipment.
4. Retry lại cả method có thể **tạo hai shipment** nếu partner không idempotent.
5. Pool exhaustion làm hỏng cả luồng không liên quan đến shipping.

**Một cách “sửa” chưa đủ:** thay `ShippingClient` bằng client async nhưng vẫn gọi `future.get()` / `join()` ngay bên trong `@Transactional`. Transaction vẫn chờ I/O. Tương tự, đặt `@Async` ở cùng method tự gọi qua `this` có thể không được áp dụng bởi proxy.

## 5. Nhìn transaction boundary trong Spring Integration

Spring Integration kết nối endpoint bằng channel; một số channel/handler chạy đồng bộ trên cùng thread, một số chuyển sang thread khác hoặc nhận message ở thời điểm khác.

~~~mermaid
flowchart LR
    A["@Transactional service"] --> D["DB write / locks"]
    D --> CH["DirectChannel"]
    CH --> H["HTTP outbound handler"]
    H --> R["Remote service - slow"]
    A -. "transaction scope vẫn mở" .-> R
~~~

### 5.1. DirectChannel: thông thường giữ call stack

`DirectChannel` thường dispatch message tới handler **trên thread của sender** và method `send()` chỉ trả về sau khi handler xử lý xong. Nếu sender đang ở trong một Spring-managed transaction, handler đồng bộ có thể thực thi **trong cùng transaction context** của thread, trừ khi chủ động tách bằng cấu hình transaction hoặc cơ chế khác.

Ví dụ:

~~~java
@Transactional
public void process(OrderEvent event) {
    orders.markAccepted(event.orderId()); // DB operation
    outboundChannel.send(
        MessageBuilder.withPayload(event).build()
    ); // Nếu là DirectChannel -> HTTP handler đồng bộ.
}
~~~

Ở đây `outboundChannel.send(...)` có thể làm transaction DB kéo dài theo HTTP latency. **Chỉ đổi tên channel thành "async" không làm nó bất đồng bộ.**

### 5.2. ExecutorChannel: có thể tách thread, không tự đảm bảo giao hàng

`ExecutorChannel` dispatch qua executor nên **transaction context gắn với thread cũ không tự truyền qua thread mới**. Đây là một ranh giới transaction thường gặp, nhưng có hai lưu ý:

- **Không có durable handoff tự động.** Nếu DB commit nhưng task trong executor chưa chạy và process chết, message có thể mất.
- Các thao tác ở thread worker có thể cần **transaction riêng**; không giả định sẽ dùng lại transaction của caller.

Dùng executor đúng khi sự kiện không cần durability mạnh hoặc đã có nguồn lưu bền/khả năng phục hồi. Với giao dịch nghiệp vụ cần giao hàng đáng tin cậy, **transactional outbox** thường phù hợp hơn.

### 5.3. QueueChannel và poller: tách thời điểm nhưng cần xác định nơi mở transaction

`QueueChannel` là `PollableChannel`; sender đưa message vào queue, consumer/poller lấy sau. Nếu là queue in-memory, nó **không bảo đảm durability qua crash**. Khi polling consumer được cấu hình transaction advice, transaction có thể bao quanh **polling và handler đồng bộ** bên trong poll, tùy cách cấu hình.

Nếu handler thực hiện remote call chậm **trong transaction của poller**, bạn vẫn giữ transaction dài dù channel là queue. Do đó cần **xem call chain và advice tại poller**, không chỉ nhìn tên channel.

### 5.4. Gateway request–reply có thể khiến caller phải chờ

Gateway cung cấp reply đồng bộ hoặc bất đồng bộ tùy kiểu gateway/cấu hình. Nếu một `@Transactional` method gọi gateway và chờ reply từ HTTP/JMS, transaction của caller có thể vẫn mở trong thời gian chờ, kể cả khi hoạt động từ xa diễn ra trên thread khác.

**Tách thread không đồng nghĩa tách thời gian giữ transaction của caller**, nếu caller vẫn chờ kết quả trước khi commit.

### 5.5. Bảng định hướng

| Topology | Ranh giới transaction tiềm năng | Bẫy |
|---|---|---|
| `@Transactional` → `DirectChannel` → HTTP handler | Có thể cùng thread, cùng transaction | DB lock giữ qua HTTP call |
| `@Transactional` → `ExecutorChannel` → handler | Worker không tự nhận thread-bound transaction | Message in-memory có thể mất sau commit |
| `@Transactional` → `QueueChannel` → poller | Producer/consumer tách thời điểm; tx poller cấu hình riêng | Poller có thể bao cả slow handler |
| JDBC polling với `TransactionInterceptor` → HTTP | Transaction poll bao gồm xử lý đồng bộ | Giữ DB tx dài |
| JMS listener transacted → HTTP → ack | Broker/session giao dịch có thể kéo dài đến handler return | Redelivery, duplicate và consumer stall |
| Kafka listener → handler → HTTP | Ack/offset tùy container, thường sau handler | Rebalance/timeout, duplicate; không phải DB tx mặc định |
| DB short tx → outbox → dispatcher → partner | DB tx kết thúc trước I/O ngoài | Cần outbox worker, retry/lease/idempotency |

## 6. Ba mốc thời gian phải đo riêng

Một bài tối ưu transaction cần phân biệt:

- **DB transaction duration**: thời gian transaction thực sự hoạt động, đặc biệt từ lock/write đến commit.
- **External call latency**: thời gian request/response ở HTTP/SFTP/broker/client.
- **Business workflow latency**: từ lúc nhận command đến lúc có kết quả cuối cùng, có thể dài hơn nhiều transaction.

~~~mermaid
gantt
    title Mô hình minh họa: transaction dài và tách ranh giới
    dateFormat  X
    axisFormat %s
    section Trước
    DB transaction giữ qua remote I/O :a1, 0, 10
    section Sau
    DB transaction (state + outbox) :a2, 0, 2
    Remote I/O (ngoài DB tx) :a3, 2, 8
    DB transaction cập nhật kết quả :a4, 8, 10
~~~

**Sơ đồ là minh họa tương đối**, không mô tả một số giây/latency đo được. Mục tiêu không nhất thiết giảm tổng thời gian business operation; mục tiêu là **không giữ tài nguyên giao dịch** trong giai đoạn chờ ngoài.

## 7. Chọn giải pháp theo độ tin cậy yêu cầu

| Bối cảnh | Mô hình ưu tiên | Trade-off |
|---|---|---|
| Đọc dữ liệu DB rồi gọi API không quan trọng, có thể tính lại | Read-only short tx → HTTP ngoài tx | Cần chấp nhận dữ liệu snapshot có thể thay đổi |
| HTTP request cần trả response đồng bộ ngay | Tx ngắn để đọc/đổi state, HTTP ngoài tx, tx ngắn ghi result | Outcome có thể không chắc khi timeout; cần idempotency |
| Đơn hàng/thanh toán/tích hợp quan trọng | Transactional outbox + worker + idempotent receiver | Eventual consistency, thêm state và vận hành |
| One-way telemetry có thể mất | Commit → executor/queue in-memory | Không bảo đảm giao hàng khi crash |
| JMS/AMQP/Kafka message cần xử lý DB | Listener/handler phối hợp DB tx và ack hợp lý, idempotent | Không tự atomic giữa broker và DB |
| SFTP upload xuất file nghiệp vụ | Staging/outbox → upload ngoài DB tx → verify/mark | Cần xử lý partial file và retry |
| Workflow nhiều remote services | Saga/choreography/orchestration với compensation | Không đạt ACID xuyên mọi hệ thống |
| Client không hỗ trợ idempotency và side effect không thể hoàn tác | Dùng reconciliation, operation tracking, manual review | Không thể tuyên bố exactly-once từ retry đơn giản |

**Đừng gọi một thiết kế là “an toàn” chỉ vì đã chuyển HTTP sang `@Async`.** Phải đánh giá **durable intent, trạng thái khi crash, idempotency, kết quả không chắc chắn và khả năng đối soát**.

## 8. Tách transaction ngắn trong service đồng bộ

Trường hợp chỉ cần gọi partner một lần với response ngay, có thể dùng **hai transaction cục bộ ngắn** và call HTTP ở giữa:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant S as Orchestration
    participant T as DB state service
    participant P as Partner
    C->>S: Submit order
    S->>T: markPending(orderId)
    T->>T: BEGIN → UPDATE PENDING → COMMIT
    S->>P: POST order (outside DB tx)
    P-->>S: result
    S->>T: markResult(orderId, result)
    T->>T: BEGIN → UPDATE result → COMMIT
    S-->>C: Result
~~~

Một **cách cụ thể** là dùng `TransactionTemplate`. Ví dụ logic:

~~~java
@Service
public class ShippingOrchestrator {
    private final TransactionTemplate transactionTemplate;
    private final OrderRepository orders;
    private final ShippingClient client;

    public ShippingOrchestrator(
            TransactionTemplate transactionTemplate,
            OrderRepository orders,
            ShippingClient client) {
        this.transactionTemplate = transactionTemplate;
        this.orders = orders;
        this.client = client;
    }

    public ShipmentReceipt submit(String orderId) {
        // Giao dịch ngắn đầu tiên.
        transactionTemplate.executeWithoutResult(status ->
                orders.markPending(orderId));

        // Không nằm trong TransactionTemplate của bước DB.
        ShipmentReceipt receipt = client.reserve(
                orderId, "shipment-" + orderId);

        // Giao dịch ngắn tiếp theo.
        transactionTemplate.executeWithoutResult(status ->
                orders.markSubmitted(orderId, receipt.shipmentId()));

        return receipt;
    }
}
~~~

`OrderRepository` và `ShippingClient` là interfaces nghiệp vụ minh họa; `TransactionTemplate` phải được cấu hình với transaction manager phù hợp. **Điều kiện bắt buộc:** phương thức `submit` này **không được gọi từ một transaction bao ngoài** nếu mục tiêu là remote call ở ngoài mọi DB transaction. Nếu caller đã mở transaction, cả hai khối `TransactionTemplate` mặc định có thể **tham gia transaction bao ngoài** với `PROPAGATION_REQUIRED`.

Do đó cần **xác định entry boundary** ở controller/message handler, không chỉ nhìn hai lệnh `executeWithoutResult(...)`. Có thể dùng service entry riêng không gắn `@Transactional`, gọi qua bean/proxy phù hợp, hoặc cấu hình propagation có chủ đích và test thực tế. **`REQUIRES_NEW` không tự giải quyết chuyện transaction bao ngoài**: nó chỉ suspend/khởi tạo transaction mới cho đoạn ngắn, rồi transaction bao ngoài có thể resume và vẫn mở khi gọi remote.

### 8.1. Thiếu độ tin cậy ở đâu?

Mẫu trên vẫn có lỗ hổng:

1. `markPending` đã commit.
2. Process chết **trước** `client.reserve` → order mãi PENDING trừ khi có recovery.
3. Partner xử lý thành công nhưng client timeout → không biết trạng thái thật.
4. Partner thành công rồi `markSubmitted` fail → retry có nguy cơ gửi lại.
5. Caller retry toàn bộ `submit` → cần idempotency để tránh duplicate.

**Đây chỉ là cách tách transaction**, chưa phải giao hàng đáng tin cậy. Với tác vụ quan trọng, hãy lưu **durable intent/outbox** trong cùng transaction với trạng thái business, rồi để worker gửi và phục hồi.

## 9. Transactional outbox: tách DB commit khỏi remote I/O nhưng không mất ý định gửi

**Transactional outbox** đặt một record cần phát gửi trong **cùng database transaction** với thay đổi nghiệp vụ. Sau commit, dispatcher lấy outbox record và gọi HTTP/SFTP/JMS/AMQP/Kafka **ngoài DB transaction**. Khi có kết quả, worker ghi trạng thái bằng một transaction ngắn khác.

~~~mermaid
flowchart LR
    REQ["Inbound command"] --> TX1["Short DB transaction"]
    TX1 --> BIZ["Orders / business rows"]
    TX1 --> OB["Outbox: PENDING"]
    OB --> WORKER["Dispatcher / poller"]
    WORKER --> REMOTE["HTTP / SFTP / broker"]
    REMOTE --> TX2["Short DB transaction: SENT / RETRY"]
    TX2 --> AUDIT["Outcome / audit"]
    WORKER -. "retry/idempotency" .-> REMOTE
~~~

**Bảo đảm quan trọng:** nếu transaction đầu tiên commit, intent gửi **được lưu bền** trong DB (theo durability của DB); nếu rollback, thay đổi nghiệp vụ và outbox **cùng rollback**. Dispatcher có thể xử lý sau, với retry và giám sát.

**Không bảo đảm exactly-once end-to-end.** Dispatcher có thể gửi thành công, rồi crash trước khi mark SENT. Khi chạy lại, nó gửi tiếp. Vì vậy cần **idempotency key tại đối tác/consumer, deduplication hoặc reconciliation**.

### 9.1. Những trạng thái cần quản lý

Một state machine đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> IN_FLIGHT: claim + lease
    IN_FLIGHT --> SENT: confirmed outcome
    IN_FLIGHT --> RETRY: transient error
    RETRY --> IN_FLIGHT: backoff expired
    IN_FLIGHT --> UNKNOWN: timeout / uncertain outcome
    UNKNOWN --> IN_FLIGHT: safe replay/reconcile
    UNKNOWN --> MANUAL_REVIEW: cannot determine
    IN_FLIGHT --> DEAD: permanent failure / policy exhausted
    SENT --> [*]
    DEAD --> MANUAL_REVIEW: operator decision
~~~

Các trạng thái là **mô hình tham khảo**, không có trong Spring Integration mặc định. Trong hệ thống thật có thể thêm `CANCELLED`, `COMPENSATING`, `FAILED_FINAL` hoặc version; phải xác định transition hợp lệ và actor có quyền thực hiện.

### 9.2. Idempotency key

Dùng một ID **ổn định theo nghiệp vụ**, ví dụ `shipment:order-42:v1`, lưu cùng outbox record và gửi tới remote API nếu remote hỗ trợ idempotency. Không sinh UUID mới cho cùng event ở mỗi lần retry; attempt ID có thể mới, nhưng **event/operation ID phải ổn định** để bên nhận nhận diện thao tác lặp.

## 10. Mô hình dữ liệu outbox có thể kiểm toán

Ví dụ DDL gần **PostgreSQL** cho bảng `integration_outbox`; tổ chức có thể điều chỉnh schema/index theo tải và DB đang dùng:

~~~sql
CREATE TABLE integration_outbox (
    id UUID PRIMARY KEY,
    aggregate_id VARCHAR(120) NOT NULL,
    destination VARCHAR(120) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload_json JSONB NOT NULL,
    idempotency_key VARCHAR(180) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    leased_until TIMESTAMPTZ,
    lease_token UUID,
    remote_receipt_id VARCHAR(180),
    last_error_code VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT outbox_status_check CHECK (
        status IN ('PENDING', 'IN_FLIGHT', 'RETRY',
                   'UNKNOWN', 'SENT', 'DEAD')
    )
);

CREATE INDEX outbox_ready_idx
    ON integration_outbox (status, next_attempt_at, created_at)
    WHERE status IN ('PENDING', 'RETRY', 'UNKNOWN');

CREATE INDEX outbox_expired_lease_idx
    ON integration_outbox (leased_until)
    WHERE status = 'IN_FLIGHT';
~~~

**Tùy chọn schema:** Có thể cần riêng tenant ID, owner, trace ID, created_by, event version, destination partition/key, lease owner và retention. Tránh lưu access token, password hoặc PII không cần thiết trong payload/outbox/error fields; cần mã hóa/kiểm soát truy cập dữ liệu nếu chứa thông tin nhạy cảm.

Một record outbox là **ý định làm việc**, không phải bằng chứng đã gửi. Chỉ cập nhật `SENT` khi có xác nhận có ý nghĩa theo giao thức và contract; một lời gọi `MessageChannel.send()` vào queue in-memory **không luôn đủ**.

## 11. Claim nhanh, commit ngay, rồi mới gửi: tránh khóa hàng trong lúc chờ mạng

**Sai lầm phổ biến khi dùng outbox:** worker mở transaction, `SELECT ... FOR UPDATE` một record, **giữ row lock**, gọi HTTP trong transaction rồi mới `UPDATE status=SENT` và commit. Như vậy bạn chỉ **di chuyển anti-pattern** từ transaction nghiệp vụ sang outbox dispatcher.

~~~text
SAI:
  BEGIN
  SELECT ... FOR UPDATE
  POST /remote       <- giữ khóa row trong lúc chờ
  UPDATE status=SENT
  COMMIT

ĐÚNG HƯỚNG:
  BEGIN
  CLAIM record + lease/fencing token
  COMMIT             <- thả khóa DB
  POST /remote       <- ở ngoài DB transaction
  BEGIN
  MARK_SENT nếu token vẫn hợp lệ
  COMMIT
~~~

### 11.1. Claim row không giữ lock qua remote call

Một chiến lược PostgreSQL với nhiều worker dùng `FOR UPDATE SKIP LOCKED` để tránh tranh cùng row. Đoạn SQL sau **phải chạy trong một transaction ngắn**:

~~~sql
WITH picked AS (
    SELECT id
    FROM integration_outbox
    WHERE status IN ('PENDING', 'RETRY')
      AND next_attempt_at <= CURRENT_TIMESTAMP
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE integration_outbox AS o
SET status = 'IN_FLIGHT',
    attempts = o.attempts + 1,
    leased_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds',
    lease_token = :new_lease_token,
    updated_at = CURRENT_TIMESTAMP
FROM picked
WHERE o.id = picked.id
RETURNING o.id, o.payload_json, o.destination,
          o.idempotency_key, o.lease_token, o.attempts;
~~~

Đây là **mẫu PostgreSQL định hướng**, không phải SQL portable cho mọi DB. `:new_lease_token` là UUID mới do dispatcher tạo cho lần claim, không phải bind được Spring JDBC tự động nếu chưa có named-parameter configuration. **Cố ý không tự claim `UNKNOWN` hoặc lease đã hết hạn để gửi lại ngay:** một attempt cũ có thể đã hoàn tất ở remote. Trước tiên cần đối soát outcome hoặc xác minh remote hỗ trợ idempotency rồi mới chuyển record sang `RETRY`. Trong thực tế còn cần giới hạn số row mỗi batch, hỗ trợ backoff, xử lý lease hết hạn riêng, tenant fairness và cảnh báo backlog.

Ví dụ chuyển lease hết hạn về trạng thái cần đối soát bằng một transaction ngắn riêng:

~~~sql
UPDATE integration_outbox
SET status = 'UNKNOWN',
    leased_until = NULL,
    lease_token = NULL,
    last_error_code = 'LEASE_EXPIRED_OUTCOME_UNCERTAIN',
    updated_at = CURRENT_TIMESTAMP
WHERE status = 'IN_FLIGHT'
  AND leased_until < CURRENT_TIMESTAMP
RETURNING id, idempotency_key;
~~~

Một reconciler có thể đưa `UNKNOWN` sang `SENT` khi remote xác nhận, hoặc `RETRY` khi việc gửi lại an toàn. Đừng biến việc lease hết hạn thành bằng chứng remote chắc chắn chưa nhận request.

**Không giữ connection/transaction** trong lúc HTTP/SFTP request đang chạy. Worker cần nhận thông tin record trong bộ nhớ và kết thúc transaction claim trước khi gọi client.

### 11.2. Mark outcome với fencing token

Khi một worker xử lý chậm hơn `leased_until`, worker khác có thể claim lại record. Để tránh worker cũ ghi đè trạng thái của worker mới, dùng **fencing/lease token** khi cập nhật:

~~~sql
UPDATE integration_outbox
SET status = 'SENT',
    leased_until = NULL,
    lease_token = NULL,
    remote_receipt_id = :remote_receipt_id,
    last_error_code = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND status = 'IN_FLIGHT'
  AND lease_token = :lease_token
  AND leased_until > CURRENT_TIMESTAMP;
~~~

Nếu `UPDATE 0 rows`, **không** tự coi là thành công; có thể worker đã mất quyền sở hữu lease. Phải đọc/truy xét trạng thái mới và thực hiện reconciliation nếu remote đã xử lý. Có thể cần chính sách riêng cho kết quả đến sau khi lease hết hạn (ví dụ ghi nhận đã xác minh outcome nhưng không ghi đè một attempt mới).

**Lease token không ngăn remote request trùng.** Nó chỉ ngăn **ghi state lỗi tại database**. Chống trùng side effect ở đích cần idempotency key/operation query hoặc cơ chế remote hỗ trợ.

### 11.3. Lease duration không phải HTTP timeout

Nếu timeout HTTP là 45 giây mà lease chỉ 30 giây, một worker khác có thể claim lại khi request đầu vẫn chạy. Có thể:

- Cấu hình **hard timeout cho remote call** nhỏ hơn lease với biên an toàn.
- Gia hạn lease theo heartbeat khi xử lý dài và có cơ chế giám sát.
- Dùng fencing token và chấp nhận at-least-once, kết hợp idempotency.
- Nếu remote operation không thể hủy hoặc có timeout không chắc chắn, dùng reconciliation trước retry.

Không đặt lease vô hạn vì khi worker chết record sẽ kẹt. Không coi lease còn hiệu lực là bằng chứng remote chưa xử lý.

## 12. Java: tách service ghi outbox khỏi dispatcher gọi remote

Một thiết kế dễ kiểm thử có ba vai trò:

1. **Command service:** trong transaction DB, đổi business state và thêm outbox.
2. **Claim/outcome service:** mỗi method thực hiện một transaction DB ngắn.
3. **Dispatcher:** không có transaction bao ngoài, gọi remote ở giữa các method.

Ví dụ skeleton:

~~~java
public record OutboxJob(
        UUID id,
        String destination,
        String payloadJson,
        String idempotencyKey,
        UUID leaseToken,
        int attempts
) {}

public interface PartnerClient {
    SendReceipt send(String destination,
                     String payloadJson,
                     String idempotencyKey);
}

public record SendReceipt(String remoteOperationId) {}

public interface OutboxRepository {
    void insert(UUID id, String orderId, String payloadJson,
                String idempotencyKey);

    OutboxJob claimNext(UUID leaseToken);

    int markSent(UUID id, UUID leaseToken, String remoteOperationId);

    int scheduleRetry(UUID id, UUID leaseToken,
                      String errorCode, Instant nextAttemptAt);

    int markUnknown(UUID id, UUID leaseToken,
                    String errorCode, Instant reviewAt);
}
~~~

Các interfaces/records do **ứng dụng tự định nghĩa**, không phải API Spring Integration có sẵn. `OutboxRepository` trong production phải hiện thực atomic SQL, lease/fencing, transaction và idempotency theo DB cụ thể.

### 12.1. Transaction tạo order và outbox là một

~~~java
@Service
public class OrderCommandService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderCommandService(OrderRepository orders,
                               OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public UUID approve(String orderId, String payloadJson) {
        orders.markApproved(orderId);

        UUID eventId = UUID.randomUUID();
        String idempotencyKey = "shipment:" + orderId + ":v1";

        outbox.insert(eventId, orderId, payloadJson, idempotencyKey);
        return eventId;
    }
}
~~~

**Yêu cầu production:** cùng `DataSource`/transaction manager và cùng transaction cho `orders.markApproved` lẫn `outbox.insert`; có constraint idempotency, xử lý trường hợp request lặp và cập nhật aggregate version khi phát sự kiện mới. Không dựa vào việc `UUID.randomUUID()` thay cho idempotency key: UUID mới ở mỗi retry sẽ tạo record khác. Mẫu này cho thấy ý tưởng, chưa định nghĩa `OrderRepository` và SQL implementation.

### 12.2. Các method DB ngắn ở bean riêng

~~~java
@Service
public class OutboxStateService {
    private final OutboxRepository outbox;

    public OutboxStateService(OutboxRepository outbox) {
        this.outbox = outbox;
    }

    @Transactional
    public OutboxJob claim() {
        return outbox.claimNext(UUID.randomUUID());
    }

    @Transactional
    public boolean complete(OutboxJob job, SendReceipt receipt) {
        return outbox.markSent(
                job.id(),
                job.leaseToken(),
                receipt.remoteOperationId()) == 1;
    }

    @Transactional
    public boolean retry(OutboxJob job, String errorCode,
                         Instant nextAttemptAt) {
        return outbox.scheduleRetry(
                job.id(), job.leaseToken(),
                errorCode, nextAttemptAt) == 1;
    }

    @Transactional
    public boolean uncertain(OutboxJob job, String errorCode,
                             Instant reviewAt) {
        return outbox.markUnknown(
                job.id(), job.leaseToken(),
                errorCode, reviewAt) == 1;
    }
}
~~~

**Lưu ý `@Transactional` proxy:** Các method này phải được gọi **qua bean Spring đã được proxy phù hợp**, không qua self-invocation từ cùng class, và method dispatcher bao ngoài không được giữ transaction đang hoạt động. Khi dùng Spring AOP, `this.claim()` nội bộ có thể bỏ qua interceptor. Việc dùng bean riêng giúp ranh giới dễ quan sát hơn.

### 12.3. Dispatcher gọi client *sau commit* và trước transaction mới

~~~java
@Component
public class OutboxDispatcher {
    private final OutboxStateService state;
    private final PartnerClient partner;

    public OutboxDispatcher(OutboxStateService state,
                            PartnerClient partner) {
        this.state = state;
        this.partner = partner;
    }

    public void dispatchOne() {
        OutboxJob job = state.claim();  // tx ngắn, đã commit khi return
        if (job == null) {
            return;
        }

        try {
            // Không có DB transaction bao ngoài method này.
            SendReceipt receipt = partner.send(
                    job.destination(),
                    job.payloadJson(),
                    job.idempotencyKey());

            boolean recorded = state.complete(job, receipt); // tx mới
            if (!recorded) {
                // Lease mất hiệu lực: đưa vào reconciliation/alert,
                // không đánh dấu success bằng cách ghi đè vô điều kiện.
                reportStaleLease(job.id());
            }
        }
        catch (UncertainOutcomeException ex) {
            // HTTP timeout sau khi có thể đã gửi: không tự POST lại.
            if (!state.uncertain(job, safeErrorCode(ex), Instant.now())) {
                reportStaleLease(job.id());
            }
        }
        catch (TransientPartnerException ex) {
            Instant next = backoffFrom(job.attempts());
            if (!state.retry(job, safeErrorCode(ex), next)) {
                reportStaleLease(job.id());
            }
        }
        catch (PermanentPartnerException ex) {
            // Cần transition DEAD/MANUAL_REVIEW có transaction,
            // được thực hiện bởi state service theo policy.
            markForReview(job, ex);
        }
    }
}
~~~

`reportStaleLease`, `backoffFrom`, `safeErrorCode`, `markForReview` và ba lớp exception là **helpers/interfaces cần hiện thực**, được cố ý mô tả chứ không giả làm mã chạy ngay. Đặc biệt phải **phân loại `UncertainOutcomeException` khác lỗi trước khi request được gửi**: một HTTP read timeout có thể nghĩa là remote đã tạo side effect, nên đưa vào `UNKNOWN` và reconcile thay vì tự retry. `markUnknown` và `scheduleRetry` cần triển khai conditional update có lease token/expected state; `reviewAt` là thời điểm dự kiến đối soát. Mẫu ở đây minh họa ý tưởng state transition, không chứng nhận một database/HTTP client đã được cấu hình chính xác.

**Điều kiện trọng yếu:** `dispatchOne()` không gắn `@Transactional` và không được gọi trong một transaction khác nếu muốn external call chắc chắn nằm ngoài transaction DB. Nếu một poller vô tình dùng advice mở transaction quanh toàn bộ `dispatchOne()`, mẫu trên **không còn giữ đúng ranh giới**.

### 12.4. Vì sao không dùng @Transactional(REQUIRES_NEW) cho toàn dispatcher?

Nếu gắn `REQUIRES_NEW` vào `dispatchOne()`, worker sẽ mở transaction mới bao cả `partner.send(...)` — lặp lại anti-pattern ban đầu. `REQUIRES_NEW` chỉ hữu ích khi dùng **có chủ đích cho một phần DB ngắn**, và phải hiểu transaction ngoài đang suspend/resume thế nào. Trong mô hình này, **dispatcher bản thân không có transaction**, còn state service nhận transaction riêng.

## 13. Spring Integration: thiết kế flow không giữ DB transaction qua HTTP/SFTP

### 13.1. Flow hướng outbox

~~~mermaid
flowchart TD
    CMD["Inbound Adapter / Gateway"] --> VALIDATE["Validate / map command"]
    VALIDATE --> TX["OrderCommandService @Transactional"]
    TX --> ORDER["Business row + outbox row cùng commit"]
    OUTBOX["DB outbox poller"] --> CLAIM["Claim service @Transactional (short)"]
    CLAIM --> SEND["HTTP/SFTP/JMS/AMQP/Kafka outbound (no DB tx)"]
    SEND --> COMPLETE["State service @Transactional (short)"]
    SEND -. "failure" .-> RETRY["Retry/reconcile/dead-letter state"]
    ORDER --> OUTBOX
~~~

Spring Integration có thể làm lớp orchestration cho dispatcher, nhưng phải chọn **đúng vị trí transaction advice**. Một inbound JDBC adapter đặt transaction advice vào poller rồi nối ngay tới HTTP handler đồng bộ có thể khiến DB transaction bao quanh cả remote call.

Cách tách rõ là để poller/handler **claim trong transaction ngắn và trả Job đã commit**, sau đó đưa Job đến handler remote **không thuộc transaction claim**. Nếu dùng một flow `DirectChannel` duy nhất với transaction advice ở polling endpoint bao trùm toàn bộ downstream handler, việc “tách method” chưa chắc đã tách transaction. Cần kiểm thực tế bằng transaction probe.

### 13.2. Ví dụ Java DSL cho điểm gửi ngoài transaction

~~~java
@Configuration
@EnableIntegration
class OutboxFlowConfig {

    @Bean
    MessageChannel dispatchChannel(TaskExecutor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean
    IntegrationFlow outboxDispatchFlow(
            OutboxDispatcher dispatcher) {
        return IntegrationFlow
                .from("dispatchChannel")
                .handle(message -> dispatcher.dispatchOne())
                .get();
    }
}
~~~

**Đây là skeleton orchestration**, không phải một flow outbox production hoàn chỉnh: cần một trigger có kiểm soát gửi tín hiệu vào `dispatchChannel` (ví dụ scheduled task/poller), bảo đảm capacity/backpressure, error handler và lifecycle. `ExecutorChannel` chỉ làm dispatch bất đồng bộ **trong bộ nhớ**, không làm task trở nên durable. **Tính bền vững nằm ở outbox DB**, còn worker phải có cơ chế quét/retry record khi khởi động lại.

Nếu không cần executor, có thể để scheduled worker gọi trực tiếp `OutboxDispatcher.dispatchOne()` và dùng một channel chỉ để thu event/metrics; đây thường là cách đơn giản, dễ xác minh ranh giới hơn.

### 13.3. Không nhầm @Async với outbox

~~~text
Commit order
  -> applicationEventPublisher.publishEvent(...)
  -> @Async listener gửi remote
~~~

Nếu event chỉ sống trong RAM, process chết sau commit nhưng trước listener chạy có thể làm **mất thao tác gửi**. `@TransactionalEventListener(phase = AFTER_COMMIT)` cũng không tự biến event thành durable: callback vẫn thuộc process hiện tại, có thể fail hoặc không chạy nếu process chết. Với delivery bắt buộc, thêm **outbox record** trong transaction và worker phục hồi.

### 13.4. @TransactionalEventListener(AFTER_COMMIT) có bẫy gì?

Một callback sau commit có thể vẫn quan sát transaction synchronization/resources của thread trong một số trường hợp; tài liệu Spring cảnh báo việc tương tác resource trong callback sau commit cần transaction mới nếu muốn **thực sự commit những DB writes mới**. Vì thế không dựa vào callback này để thay outbox, và nếu ghi result sau commit thì dùng transaction độc lập được xác minh.

## 14. Poller: transaction ở nguồn, consumer và handoff

Poller có thể kết hợp transaction advice để bảo vệ các thao tác nhận và cập nhật trạng thái nguồn. Cần phân biệt:

- **Transaction của source polling:** ví dụ đọc outbox row, claim lease, cập nhật trạng thái trong DB.
- **Transaction của downstream handler:** ví dụ ghi trạng thái kết quả sau remote call.
- **Network call:** HTTP/SFTP/broker publish ở khoảng **không có DB transaction**.

### 14.1. Anti-pattern do advice đặt quá rộng

~~~text
Polling endpoint:
  transactionAdvice: begin
  source.receive() -> read/lock outbox row
  downstream.handle() -> HTTP gateway call (slow)
  transactionAdvice: commit

=> Transaction có thể kéo dài qua cả receive + handle.
~~~

**Nguyên tắc chỉnh sửa:** giới hạn transaction bao quanh **claim/read-state**, hoặc tách handoff ra khỏi transaction của poller với boundary được kiểm chứng. Đừng chỉ thêm một `QueueChannel` mà mặc định transaction sẽ kết thúc đúng lúc; phụ thuộc việc poller được cấu hình vào phía nào của channel và handler nào vẫn ở cùng scope.

### 14.2. Khi dùng JDBC inbound adapter đọc nhiều row

Nếu source đọc batch 100 row rồi worker giữ transaction trong khi gọi 100 HTTP APIs, tổng thời gian lock có thể tăng theo tổng độ trễ. Tách **claim batch → commit** rồi xử lý từng job với concurrency giới hạn, không giữ row locks. Mỗi job có status/lease/idempotency độc lập để retry.

### 14.3. Tối ưu batching và backpressure

- `maxMessagesPerPoll` giới hạn số message mỗi poll, **không tự giới hạn** số xử lý đang chạy nếu có executor/multiple instances.
- Giới hạn concurrent remote calls để tránh làm quá tải partner và chính ứng dụng.
- Khi backlog tăng, dùng metric và scale workers trong capacity cho phép.
- Không tăng thread pool vô hạn để “giấu” HTTP latency.
- Nếu source queue/broker có backpressure, cần đảm bảo ack/offset/lease tương thích với công việc thực sự đã hoàn tất.

## 15. HTTP outbound: timeout, kết quả không chắc chắn và idempotency

HTTP outbound gateway/adapter là một nguồn remote latency điển hình. Tối thiểu cần:

| Timeout/chính sách | Mục đích |
|---|---|
| **Connection timeout** | Giới hạn thời gian thiết lập kết nối |
| **Read/response timeout** | Giới hạn chờ response |
| **Total/deadline** | Hạn tổng của operation, bao gồm retry nếu có |
| **Retry/backoff** | Giới hạn attempts và khoảng nghỉ có jitter |
| **Circuit breaker/bulkhead** (nếu cần) | Ngăn một partner chậm chiếm tài nguyên toàn ứng dụng |
| **Idempotency key** | Nhận biết thao tác lặp sau timeout |
| **Reconciliation/query status** | Xác minh outcome khi response bị mất |

**Không có cấu hình timeout mặc định nào phù hợp mọi dịch vụ.** Đặt theo SLA, server timeout, pool capacity và lease duration, có metrics thực tế. Deadline business không nhất thiết bằng HTTP socket timeout. Cấu hình timeout của test queue `receive(2000)` cũng **không chứng minh** HTTP read timeout đã được cấu hình.

### 15.1. HTTP timeout không khẳng định request thất bại ở server

~~~mermaid
sequenceDiagram
    participant W as Worker
    participant API as Partner API
    participant DB as Local DB
    W->>API: POST /shipments key=shipment:42
    API->>API: Create shipment sh-42
    Note over W,API: Response lost / client timeout
    W->>DB: mark UNKNOWN / retry scheduled
    W->>API: GET /operations/shipment:42
    API-->>W: Already completed: sh-42
    W->>DB: Mark SENT with remote receipt
~~~

Nếu API không cung cấp query/idempotency, phải chọn giữa retry có rủi ro duplicate, quy trình manual reconciliation hoặc compensation. **Không được tuyên bố exactly-once** chỉ vì có retry template.

### 15.2. Outbound gateway và transaction của caller

Nếu một API inbound request phải chờ outbound gateway reply, toàn bộ HTTP request có thể kéo dài, nhưng **DB transaction không cần kéo dài cùng nó**. Thiết kế trạng thái `PENDING/PROCESSING/SUBMITTED/FAILED` và các transaction ngắn trước/sau gateway. Khi cần low latency mà remote service chậm, cân nhắc response `202 Accepted` với operation ID và endpoint truy vấn trạng thái; đó là **thay đổi API contract**, không nên áp dụng âm thầm.

## 16. SFTP: không giữ database transaction suốt quá trình truyền file

Upload SFTP có thể mất nhiều giây hoặc phút, nhất là file lớn. Nếu transaction DB mở để đánh dấu “đang xuất file” rồi chờ upload, connection/lock dễ bị giữ quá lâu.

Thiết kế an toàn hơn:

1. Transaction ngắn ghi **export intent** với `exportId`, tên file, checksum/version, remote path đã được kiểm tra và status `PENDING`.
2. Worker claim job, commit DB.
3. Tạo payload/file staging **ngoài DB transaction**, với snapshot/version hoặc checksum để ổn định dữ liệu.
4. Upload tới **temporary remote path** (nếu server/contract hỗ trợ).
5. Xác minh upload hoàn tất; rename sang final path theo cơ chế server hỗ trợ.
6. Transaction ngắn ghi `SENT`/remote receipt; khi timeout xử lý `UNKNOWN` hoặc retry/reconcile.
7. Dọn staging và file tạm theo retention/recovery policy.

**Temporary upload + rename** có thể cải thiện khả năng consumer chỉ thấy file hoàn chỉnh, nhưng không tự bảo đảm atomicity trên mọi server/filesystem/kiến trúc SFTP. Phải xác nhận semantics của server, xử lý rename fail và đối soát file đã tồn tại.

### 16.1. Idempotency cho export file

Một key như `export:<business-id>:<version>` và remote filename deterministic giúp phát hiện lần gửi lặp. Tuy nhiên việc remote path đã tồn tại không luôn chứng minh nội dung đúng: cần kiểm size/checksum hoặc metadata tương ứng, đồng thời phân biệt file do một process khác tạo.

### 16.2. File inbound cũng có rủi ro tương tự

Nếu file inbound poller mở transaction DB cho toàn flow rồi parse file lớn/gọi HTTP chậm, transaction có thể kéo dài. Tách parse/validate ngoài tx nếu phù hợp, commit kết quả DB theo batch nhỏ và dùng durable idempotency key để tránh xử lý file trùng sau restart.

## 17. JMS và AMQP: transaction broker và slow HTTP handler

Một JMS/AMQP listener thường nhận message rồi chuyển vào Spring Integration message flow. Transaction/acknowledgment của broker là một ranh giới khác với local DB transaction.

### 17.1. Dòng xử lý dễ gây backlog

~~~text
Broker message received
  -> listener transaction / ack pending
  -> DB update @Transactional
  -> HTTP external call 30s
  -> local DB commit
  -> broker ack/commit (tùy cấu hình)
~~~

Khi handler chậm, consumer slot bị chiếm, broker thấy unacked/in-flight messages lâu, khả năng redelivery/requeue và timeout tăng. Nếu DB transaction mở cùng lúc, pool/locks cũng bị giữ.

### 17.2. Hướng thiết kế

- Consume message, thực hiện **DB mutation + outbox record** trong transaction DB ngắn.
- Chỉ ack/commit broker theo semantics và thứ tự xử lý đã định nghĩa; nếu crash giữa DB commit và broker ack, **message sẽ có thể redeliver**, nên cần deduplication/inbox/unique business key.
- Worker ngoài đường broker listener gửi remote HTTP/SFTP với retry/idempotency.
- Tách `INBOUND_ACCEPTED` khỏi `EXTERNAL_DELIVERED` trong audit/metrics.

**Điểm tinh tế:** “ack sau DB commit” chỉ là mô hình logic; với container/provider khác nhau cần xác minh ack mode, transaction manager và error handler. Spring transaction synchronization có thể phối hợp một phần, nhưng **không tự biến DB + JMS/AMQP thành một atomic transaction** nếu không có cơ chế giao dịch thích hợp.

### 17.3. Consumer không được giữ transaction trong khi chờ retry/backoff

Nếu retry advice thực hiện sleep/backoff ngay trong phạm vi DB transaction, nó có thể giữ resource trong suốt thời gian ngủ. Hãy đưa retry delay vào **scheduled next_attempt_at** hoặc broker retry/delay topology và **kết thúc transaction trước** khi chờ lượt sau.

## 18. Kafka: offset, producer transaction và DB khác ranh giới

Kafka có mô hình riêng: producer send, broker append/ack, consumer poll/commit offset và (tùy cấu hình) Kafka transactions. Chúng không đồng nghĩa DB transaction mở bởi `@Transactional`.

| Vấn đề | Điều cần nhớ |
|---|---|
| Producer `send()` async | Future có thể hoàn tất sau khi handler return; phải kiểm callback/result |
| Kafka producer transaction | Có thể bao nhóm thao tác Kafka tương ứng; không bao HTTP/SFTP/DB một cách tự động |
| Consumer offset | Commit offset là vị trí đọc, không phải xác nhận side effect remote |
| Redelivery | Crash trước commit offset có thể xử lý lại event |
| Long processing | Có thể ảnh hưởng consumer poll interval/rebalance và throughput |
| DB transaction | Nếu mở trước remote call, vẫn chịu lock/pool pressure |
| Exactly-once claims | Phải xác định **phạm vi** Kafka transactions/stream processing, không suy ra toàn hệ thống |

### 18.1. Dòng xử lý Kafka → DB → HTTP

Hướng đề xuất:

1. Consumer nhận record, xác minh schema và business event ID.
2. Trong transaction DB ngắn, upsert state/dedup và insert outbox intent. Nếu event đã tồn tại, áp dụng idempotent decision.
3. Commit DB.
4. Commit offset/ack theo container policy; nếu commit fail sẽ đọc lại, dedup vẫn ngăn insert trùng.
5. Worker outbox gửi HTTP và mark result với transaction ngắn.

**Cần kiểm crash windows thật** giữa DB commit và offset commit. Không có thứ tự nào loại bỏ mọi trường hợp duplicate khi hai tài nguyên không tham gia một giao dịch chung. Đảm bảo **reprocessing an toàn** thường thực tế hơn yêu cầu không bao giờ đọc lại.

### 18.2. Khi Kafka chính là đích outbox

Worker có thể publish outbox event lên Kafka. Chỉ mark `SENT` sau confirmation đáp ứng policy, không đánh dấu ngay khi enqueue producer future nếu ứng dụng cần broker ack. Worker có thể crash sau ack nhưng trước mark; consumer Kafka phải dedup theo `eventId` khi side effect không idempotent.

## 19. Chờ slow service không cần nằm trong database transaction — nhưng vẫn cần giới hạn tải

Sau khi tách DB transaction, remote calls vẫn chiếm thread/connection pool của HTTP/SFTP/broker client. Một ứng dụng xử lý 10.000 outbox jobs cùng lúc có thể gây nghẽn mới.

Các biện pháp vận hành:

- Giới hạn **concurrency theo destination** hoặc tenant, không chỉ global thread count.
- Đặt HTTP/SFTP client connection pool phù hợp và có timeout.
- Dùng bounded executor/queue; xác định chính sách reject/backpressure.
- Dùng retry jitter và circuit breaker hợp lý để tránh retry storm.
- Phân biệt permanent error với transient error; không retry mãi dữ liệu sai schema/auth.
- Đo queue age, oldest pending, IN_FLIGHT age, retry count, lease expiry.
- Đảm bảo scan/dispatch chịu được restart, duplicate và test song song.

**Tách transaction là điều kiện quan trọng nhưng chưa đủ.** Hệ thống cũng cần capacity planning, durability, idempotency và quan sát vận hành để không chuyển điểm nghẽn từ DB pool sang thread pool hoặc partner.

## 20. Spring @Transactional propagation: công cụ hữu ích nhưng không phải lối thoát thần kỳ

Spring transaction management hỗ trợ các kiểu propagation như `REQUIRED`, `REQUIRES_NEW`, `SUPPORTS`, `NOT_SUPPORTED`, `NESTED`, `MANDATORY` và `NEVER`. Bài toán **tránh giữ transaction khi gọi dịch vụ chậm** yêu cầu hiểu chính xác lúc nào một transaction cũ vẫn đang tồn tại.

| Propagation | Khi caller đã có DB transaction | Ứng dụng trong bài toán |
|---|---|---|
| `REQUIRED` | Tham gia transaction có sẵn | Mặc định nhiều service; dễ kéo dài tx khi gọi slow I/O |
| `REQUIRES_NEW` | Suspend transaction cũ, mở transaction mới cho method | Hữu ích cho DB write tách biệt, **không** tự thả lock của outer tx |
| `NOT_SUPPORTED` | Suspend transaction có sẵn, chạy method không transaction | Có thể tách call stack, **nhưng** outer tx vẫn đang mở/giữ resource |
| `SUPPORTS` | Tham gia nếu có, không tạo nếu chưa có | Không dùng để đảm bảo remote call ngoài tx |
| `NEVER` | Báo lỗi nếu được gọi trong transaction | Có thể dùng làm guardrail ở boundary remote gửi |
| `MANDATORY` | Yêu cầu transaction hiện hữu | Hữu ích để đảm bảo DB write được thực hiện trong tx |
| `NESTED` | Savepoint trong transaction hiện tại khi manager hỗ trợ | Không thay remote I/O thành giao dịch độc lập |

### 20.1. Bẫy NOT_SUPPORTED và REQUIRES_NEW

~~~java
@Transactional
public void outerProcess(String orderId) {
    orders.updateWithLock(orderId);     // DB transaction đang giữ lock
    remoteSender.sendOutsideTx(orderId); // @Transactional(NOT_SUPPORTED)
    orders.markReady(orderId);
}
~~~

`sendOutsideTx` chạy với transaction synchronization bị suspend theo cơ chế proxy nhưng **outer DB transaction chưa commit**. Nó có thể vẫn giữ row lock/connection bị suspend cho tới khi `outerProcess` hoàn tất. Vì vậy **NOT_SUPPORTED không sửa triệt để vấn đề** nếu transaction ngoài đã thực hiện các thao tác giữ tài nguyên.

**Giải pháp gốc:** đặt commit của phần DB **trước** khi vào orchestration remote, nghĩa là thay đổi **cấu trúc call graph và transaction entrypoint**, không chỉ thay annotation ở một helper.

### 20.2. Self-invocation

~~~java
@Service
class UnsafeService {

    public void handle(String orderId) {
        this.persistIntent(orderId); // self invocation
    }

    @Transactional
    public void persistIntent(String orderId) {
        // Trong cấu hình AOP proxy thông thường, lời gọi bằng this
        // có thể bỏ qua interceptor @Transactional.
    }
}
~~~

Ở Spring AOP proxy mode thông dụng, một lời gọi nội bộ `this.method()` không đi qua proxy nên annotation trên method đích có thể không được áp dụng. Đưa transaction boundary sang một **Spring bean khác**, gọi từ bên ngoài qua proxy, hoặc dùng `TransactionTemplate` một cách chủ động. Cần lưu ý hỗ trợ các kiểu weaving/proxy khác có thể thay behavior; luôn kiểm test trong cấu hình thật.

### 20.3. Không tạo transaction chỉ để bao sleep hoặc rate limit

Nếu một retry policy có backoff hoặc rate limiter chờ permit, thực hiện **trước khi mở DB transaction**. Đừng đặt `Thread.sleep`, chờ semaphore, chờ network response hoặc chờ executor hoàn tất bên trong transaction.

## 21. Optimistic concurrency: thay vì giữ khóa cho tới khi dịch vụ ngoài trả lời

Một lý do developer giữ transaction qua HTTP là muốn **đảm bảo order không đổi** trong lúc gọi partner. Giữ row lock nhiều giây thường không phải giải pháp phù hợp.

Một thay thế là **optimistic versioning và state machine**:

~~~text
T0: short tx
  read order version=7
  mark state=SUBMITTING, increment version to 8
  persist operationId=shipment:42:v7
  commit

T1: remote I/O without DB transaction
  call partner with operationId

T2: short tx
  UPDATE order
  SET state=SUBMITTED, version=9
  WHERE id=42 AND version=8 AND state=SUBMITTING
~~~

T0 đã **tăng version** từ 7 lên 8, vì vậy T2 phải so với **version sau khi T0 commit** (8), không phải 7 của snapshot cũ. Mô hình trên là mô tả ý tưởng version/state; implementation cần định nghĩa cụ thể state/version expected:

~~~sql
-- Minh họa bước finalization: expected_version được lưu từ
-- trạng thái đã commit ở T0, không dùng snapshot cũ không hợp lệ.
UPDATE orders
SET state = 'SUBMITTED',
    version = version + 1,
    remote_receipt = :receipt
WHERE id = :order_id
  AND version = :expected_version
  AND state = 'SUBMITTING'
  AND operation_id = :operation_id;
~~~

Nếu `UPDATE 0 rows`, không ghi đè bằng một update vô điều kiện; có thể order đã bị cancel, sửa bởi một worker khác hoặc operation đã được hoàn tất. Phải đọc state, đối soát remote và quyết định tiếp.

**Không để snapshot cũ trở thành nguyên nhân gửi nhầm:** nếu thông tin của order cần bất biến để gửi, snapshot payload/version đã được duyệt cần được lưu cùng outbox record. Consumer/partner nhận operation ID và version, không đọc “bản mới nhất” trong lúc remote call khi mục tiêu là gửi một snapshot nhất định.

## 22. Xây dựng state machine cho thao tác không đồng bộ

Không nên dùng một boolean `sent=true/false` để biểu diễn đầy đủ một request có thể timeout hoặc được gửi lại. State rõ ràng giúp phân biệt:

| State | Ý nghĩa | Hành động tiếp theo |
|---|---|---|
| `PENDING` | Ý định gửi đã commit, chưa claim | Worker claim nếu đến hạn |
| `IN_FLIGHT` | Worker đang sở hữu lease và thử gửi | Chờ result; giám sát lease/deadline |
| `SENT` | Có kết quả được xác minh theo contract | Không gửi lại trừ policy riêng |
| `RETRY` | Lỗi tạm; có thời điểm thử lại | Scheduler chờ `next_attempt_at` |
| `UNKNOWN` | Request có thể đã được remote xử lý | Query/reconcile trước khi retry nguy hiểm |
| `DEAD` | Không tự retry nữa do lỗi permanent/hết ngưỡng | Owner/manual handling/compensation |
| `CANCELLED` | Nghiệp vụ hủy intent trước khi hoàn tất | Ngăn dispatch mới; xử lý race với in-flight |
| `COMPENSATING` | Đang thực hiện bước bù trừ | Theo dõi receipt/độ trễ và failure của compensation |

Một transaction ngắn ghi state transition. Các chuyển trạng thái cần kiểm soát actor, operation ID, expected state/version, lease token và audit để tránh hai worker cùng đánh dấu thành công hoặc hủy sai.

### 22.1. Hủy order khi remote call đang chạy

Nếu order bị hủy lúc worker đã gửi request, “đặt CANCELLED trong DB” **không làm remote request biến mất**. Phải quyết định:

- Hủy trước khi claim: không dispatch.
- Hủy khi đang in-flight: chặn attempt mới, nhưng kết quả attempt cũ có thể đến.
- Remote đã tạo shipment: gọi API cancel/compensation khi được hỗ trợ.
- Remote không hỗ trợ cancel: manual review/đối soát trạng thái và rủi ro.

Tránh viết logic rollback DB coi như đã hủy remote operation trong mọi tình huống.

## 23. Các cửa sổ lỗi: commit, send, ack, crash

Kiểm transaction boundary cần liệt kê **crash windows**:

| Thời điểm crash/sự cố | Điều còn tồn tại | Cách hồi phục |
|---|---|---|
| Trước commit business + outbox | Cả hai rollback theo local DB transaction | Caller có thể retry command bằng business key |
| Sau commit, trước dispatcher claim | Outbox PENDING còn bền | Worker khác/restart sẽ claim |
| Sau claim, trước remote call | IN_FLIGHT có lease, chưa chắc đã gửi | Lease hết hạn → claim lại |
| Trong remote call | Side effect có thể đã xảy ra một phần | UNKNOWN/reconcile/idempotency |
| Remote thành công, trước mark SENT | Outbox vẫn in-flight | Retry có thể lặp, cần idempotent target |
| Mark SENT DB fail | Remote có thể thành công, DB chưa xác nhận | Reconcile, retry an toàn |
| Broker publish ack thất lạc | Producer không chắc broker đã nhận | Idempotency/dedup theo event ID |
| DB commit thành công, broker ack fail | Inbound event có thể redeliver | Inbox/dedup ở DB |
| Lease hết hạn trước worker return | Worker khác có thể đã claim | Fencing token, remote idempotency |
| Shutdown lúc đang upload SFTP | Remote có thể còn temporary file | Resume/cleanup/checksum policy |

**Một thiết kế đúng không nhất thiết ngăn được mọi lần chạy lặp; nó khiến việc chạy lặp an toàn và giải thích được.**

### 23.1. Chặn duplicate bằng unique business key

Một outbox có constraint `UNIQUE (idempotency_key)` giúp ngăn hai intent trùng khi cùng key được tạo trong DB. Nhưng duplicate cũng có thể xảy ra ở **remote** dù chỉ có một outbox row nếu worker retry; phải có idempotency ở đích hoặc logic query/compensation.

### 23.2. Tại sao không nên đánh dấu SENT trước khi gửi?

~~~text
BEGIN -> mark SENT -> COMMIT -> HTTP send
                               ^
                               process crashes here
~~~

Nếu crash sau khi mark SENT nhưng trước khi send, worker restart sẽ bỏ qua record → mất thao tác gửi. Với remote I/O, cần đánh dấu success **sau kết quả xác thực**; chấp nhận khả năng phải retry và thiết kế idempotency.

### 23.3. Không coi ACK là business completion

Một HTTP 202 Accepted, Kafka broker ack hoặc RabbitMQ publisher confirm thường nói về **mức tiếp nhận** tại hệ thống đích, không nhất thiết consumer đã xử lý nghiệp vụ. Có thể có các trạng thái tách biệt: `PUBLISHED` / `REMOTE_ACCEPTED` / `REMOTE_COMPLETED`. Chọn milestone theo contract và báo cáo chính xác.

## 24. Reconciliation: khi response biến mất hoặc trạng thái bị lệch

Reconciliation là cơ chế kiểm tra **desired state ở DB** với **actual state tại remote**, đặc biệt với operation ở trạng thái `UNKNOWN` hoặc hết lease.

Ví dụ:

~~~text
Local outbox:
  operationId = shipment:42:v1
  status      = UNKNOWN
  attempts    = 2

Partner:
  lookup operationId -> shipmentId=sh-42, state=CREATED

Action:
  short DB tx: mark SENT + store remote receipt
  no extra POST
~~~

Nếu remote trả “not found”, chỉ retry POST khi policy xác nhận **kết quả lookup có thẩm quyền và nhất quán**; một API có eventual consistency có thể tạm thời trả not found ngay sau khi tạo, nên retry có thể tạo duplicate nếu không có idempotency. Nếu remote không hỗ trợ lookup, cần xác định ngưỡng manual review và phạm vi compensation.

### 24.1. Đối soát không được giữ DB transaction mở trong khi query remote

Reconciler cũng là một remote client. Thiết kế:

1. Trong transaction ngắn, claim tập UNKNOWN và copy các keys cần kiểm.
2. Commit; gọi partner query API ngoài DB transaction.
3. Trong transaction ngắn, cập nhật outcome bằng expected state/version/lease.
4. Nếu state đã đổi, áp dụng fencing và không ghi đè vô điều kiện.

Không lặp lại anti-pattern bằng cách `SELECT ... FOR UPDATE` rồi query 100 remote operation trong cùng transaction.

## 25. Xử lý lỗi, retry và backoff theo phân loại

| Lỗi | Thường có thể retry? | Kiểm soát |
|---|---|---|
| Kết nối tạm thời mất / HTTP 503 | Có thể, nếu operation idempotent và policy cho phép | Bounded retry + exponential backoff + jitter |
| HTTP 429 | Theo retry-after/quota và policy | Rate limiting và tránh retry storm |
| HTTP 400/schema invalid | Thường không, cho tới khi dữ liệu được sửa | DEAD/reject có owner |
| HTTP 401/403 | Không retry vô hạn | Khắc phục credential/scope, alert |
| HTTP timeout sau khi body đã gửi | Outcome **không chắc chắn** | UNKNOWN, idempotency, query/reconciliation |
| SFTP transfer fail giữa chừng | Tùy partial file, temporary rename, checksum | Cleanup/resume có kiểm chứng |
| JMS/AMQP consumer nack/redelivery | Theo broker policy | Dedup, DLQ, không retry vô hạn |
| Kafka producer future fail | Tùy exception và broker config | Producer policy, record ID, ack handling |
| Database deadlock/serialization conflict | Có thể retry **local transaction** ngắn | Idempotent DB operation, backoff |
| Data integrity/unique violation | Tùy nghĩa nghiệp vụ; có thể là duplicate hợp lệ | Phân biệt dedup với lỗi thật |

Một nguyên tắc quan trọng: **không đặt backoff sleep bên trong DB transaction**, và không cấu hình retry không giới hạn ở handler giữ broker session, transaction hoặc một thread quan trọng.

### 25.1. Retry với jitter

Ví dụ biểu thức thời gian chờ:

\[
delay = \min(delay_{max}, delay_{base} \cdot 2^{attempt - 1}) + jitter
\]

Giá trị `jitter` cần bị giới hạn, tránh overflow ở số attempt lớn và tuân thủ server `Retry-After` khi áp dụng. Đây là công thức tham khảo, không phải policy Spring Integration mặc định. Lưu `next_attempt_at` trong DB để worker có thể phục hồi sau restart.

### 25.2. Dead-letter không phải “xóa lỗi”

Dead-letter record hoặc DLQ phải mang operation ID, error category, attempts, source/destination và owner đủ để điều tra **nhưng không lộ secret**. Có chính sách replay sau khi dữ liệu/permission được sửa, luôn kiểm idempotency và review trước khi chạy lại một operation tác động lớn.

## 26. Quan sát vận hành: đo transaction và dịch vụ chậm bằng metric đúng

Những chỉ số giúp xác định anti-pattern và hiệu quả cải tiến:

| Nhóm | Metric/đối tượng cần theo dõi |
|---|---|
| **DB transaction** | Duration p50/p95/p99, số transaction dài, lock wait, deadlock, timeout |
| **Connection pool** | Active/idle/pending connections, acquisition wait, pool exhaustion |
| **Remote I/O** | HTTP/SFTP/broker latency, error %, timeout %, retry attempts |
| **Outbox** | Backlog count, oldest pending age, IN_FLIGHT age, UNKNOWN count, lease expiry |
| **Delivery correctness** | Duplicate detected, idempotency hits, reconciliation outcomes |
| **Consumer health** | JMS/AMQP unacked, Kafka lag/rebalances, poller delay |
| **Business outcome** | Time to externally delivered/completed, manual-review backlog |
| **Security** | Failed auth/TLS/SSH, secret exposure risk, access controls on audit |

**Không đo mỗi thời gian HTTP** rồi kết luận transaction ngắn hơn. Cần instrument **điểm bắt đầu và kết thúc transaction thực tế**, pool/locks và thời gian gửi bên ngoài.

### 26.1. Trace và correlation

Dùng business `operationId`/`correlationId` xuyên các bước:

~~~text
trace/order:
  operationId=shipment:42:v1
  receive -> db.commitIntent -> outbox.claim -> http.send
          -> http.result -> db.markSent -> audit
~~~

Correlation ID phải ổn định qua retry để truy vết cùng nghiệp vụ, còn attempt ID dùng phân biệt lần gọi. Không đưa password, access token, private key hoặc PII không cần thiết vào headers/logs để tạo dấu vết.

### 26.2. Cảnh báo hữu ích

- Database connection pool gần chạm giới hạn và transaction duration p99 tăng.
- HTTP timeout tăng **đồng thời** outbox UNKNOWN tăng.
- Job IN_FLIGHT quá `leased_until` lâu bất thường.
- Outbox oldest pending age vượt mức cho phép của workflow.
- Duplicate/idempotency violation ở partner hoặc số compensation tăng.
- Kafka consumer lag tăng do handler chờ remote lâu.

## 27. Kiểm thử: remote client phải chạy ngoài transaction DB

Một bài test đúng **không chỉ kiểm kết quả cuối**. Nó phải kiểm **rõ ràng ranh giới transaction**.

### 27.1. Probe đơn giản tại điểm gọi remote

Trong một client fake/test double:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.transaction.support.TransactionSynchronizationManager;

final class RecordingPartnerClient implements PartnerClient {
    private final AtomicBoolean wasTransactional =
            new AtomicBoolean(true);

    @Override
    public SendReceipt send(String destination,
                            String payloadJson,
                            String idempotencyKey) {
        wasTransactional.set(
            TransactionSynchronizationManager
                    .isActualTransactionActive());
        return new SendReceipt("remote-op-42");
    }

    boolean observedActiveTransaction() {
        return wasTransactional.get();
    }
}
~~~

Trong Spring integration test có bean dispatcher/state service/DB đã cấu hình:

~~~java
// Fixture đã chuẩn bị outbox PENDING và inject dispatcher + recordingClient.
dispatcher.dispatchOne();

assertFalse(recordingClient.observedActiveTransaction(),
        "Remote call không được chạy trong DB transaction");

assertEquals("SENT", outboxRepository.findStatus(jobId));
~~~

**Điều kiện:** `dispatcher.dispatchOne()` phải chạy **qua topology thực** mà bạn muốn xác minh (poller advice, channel, proxy) chứ không chỉ gọi thẳng method theo cách bỏ qua transaction interceptor. `TransactionSynchronizationManager.isActualTransactionActive()` chứng minh thread hiện tại không có Spring actual transaction nhưng **không chứng minh** không có một outer transaction bị suspend vẫn giữ lock, hay không có transaction ở thread khác. Cần thêm integration test kiểm row lock/connection availability.

### 27.2. Test DB lock không bị giữ qua HTTP chậm

Một test thực chất hơn:

1. Tạo order/outbox trong DB test.
2. Dùng fake HTTP client có `CountDownLatch` để **chặn ngay tại remote call**.
3. Trong thread khác, thử cập nhật/đọc khóa row có liên quan ở DB với deadline ngắn đã xác định.
4. Xác minh update được hoàn tất trong khoảng remote fake vẫn đang chờ, theo isolation/locking policy của DB.
5. Thả latch, để worker hoàn tất rồi verify state.
6. Nếu test chỉ pass với H2 nhưng target PostgreSQL, chạy lại với DB loại production để xác minh lock behavior thực.

**Tránh kỳ vọng không lock mọi row:** một cơ chế claim có thể giữ resource trong **transaction ngắn trước** remote I/O; test nên đo rằng resource **đã được thả trước** khi remote call bị chặn.

### 27.3. Test anti-pattern để phát hiện regression

Giữ một bài test mô phỏng:

~~~text
Given:
  PartnerClient bị block trong 5 giây.
When:
  Input flow kích hoạt send.
Then:
  remoteClient sees transactionActive=false
  DB lock không chờ 5 giây
  connection pool không giữ connection do tx bao remote
  job được xử lý đúng sau release
~~~

Không nhất thiết assert vào con số 5 giây cứng trong CI. Sử dụng latch/await và deadline hữu hạn; tên test nên nêu **contract** chứ không chỉ nêu implementation.

### 27.4. Test commit business + outbox là atomic

- Giả lập lỗi khi insert outbox sau khi update business: cả hai phải rollback.
- Giả lập lỗi khi update business: outbox không xuất hiện.
- Khi commit thành công: cả business state và outbox intent đều tồn tại.
- Gửi lại cùng command/event: unique key ngăn tạo outbox trùng theo chính sách.
- Nếu event schema không hợp lệ: reject đúng boundary, không để một intent hỏng tồn tại mãi.

Không mock `@Transactional` rồi coi là đã test atomicity. Cần **database test** với transaction manager thật.

## 28. Kiểm thử lỗi và replay để bảo đảm reliability

Một test suite thực tế nên bao gồm:

| Case | Mô phỏng | Điều phải chứng minh |
|---|---|---|
| C1: Commit outbox lỗi | DB exception | Business row và outbox cùng rollback |
| C2: Crash sau commit trước send | Dừng/restart worker | Job PENDING được khôi phục |
| C3: Crash sau claim | Không gọi remote, lease hết hạn | Job được claim lại an toàn |
| C4: Remote 503 | Client trả transient | RETRY/backoff, không giữ DB tx |
| C5: Remote 400 | Client trả permanent | DEAD/reject, không retry vô hạn |
| C6: Timeout sau remote commit | Server fake ghi rồi mất response | UNKNOWN/reconcile hoặc idempotent retry |
| C7: Remote success, DB mark fail | Force DB error | Recovery không tạo side effect thứ hai |
| C8: Hai workers claim cùng lúc | Concurrent transactions | Chỉ một lease owner tại một thời điểm |
| C9: Worker cũ trả result sau lease expire | Delay > lease | Fencing token ngăn ghi đè |
| C10: Duplicate input broker | Redeliver cùng event ID | DB/inbox/outbox không nhân đôi |
| C11: Kafka producer future fail | CompletableFuture exceptionally | Không mark SENT giả |
| C12: SFTP upload dở | Disconnect mid-transfer | Không coi final file đã hoàn tất |
| C13: Shutdown | Stop in-flight worker | Lease/retry/audit phục hồi đúng |
| C14: API 202 Accepted | Async remote job | Không nhầm accepted với completed |
| C15: Cancel during send | Operation đổi state | Race/compensation xử lý đúng |
| C16: Backpressure | Partner chậm, nhiều jobs | Bounded concurrency, không nghẽn pool |
| C17: Secret in payload | Token/header nhạy cảm | Logs/outbox không rò dữ liệu |
| C18: HTTP reply no correlation | Sai mapping | Phát hiện/không gán nhầm kết quả |

**Không phải mọi test đều cần thực hiện trong một suite nhanh.** Dùng unit test cho state transitions, integration test cho DB/outbox/poller, mock HTTP/SFTP server cho remote outcomes, broker test cho ack/offset và staged test cho hạ tầng gần production.

## 29. Case study: JDBC inbound → HTTP shipping chậm

Giả sử hệ thống đơn hàng có JDBC inbound poller đọc `orders_to_ship`, rồi gọi HTTP shipping service mất 2–20 giây.

### 29.1. Thiết kế ban đầu

~~~mermaid
flowchart LR
    SQL["JDBC polling @Transactional"] --> CH["DirectChannel"]
    CH --> HTTP["HTTP outbound gateway (slow)"]
    HTTP --> UPDATE["Update order as SHIPPED"]
    UPDATE --> COMMIT["Commit transaction"]
~~~

**Hậu quả:** nếu transaction advice bao toàn bộ đồng bộ chain, DB row/connection có thể bị giữ nhiều giây; 20 consumer đồng thời có thể chiếm phần lớn pool, và HTTP timeout khiến rollback không hoàn tác shipment đã được tạo ở remote.

### 29.2. Thiết kế lại

~~~mermaid
flowchart LR
    CMD["DB/source events"] --> TX["Short transaction"]
    TX --> O["orders + outbox record"]
    O --> WORKER["Dispatcher claims lease, commits"]
    WORKER --> HTTP["HTTP shipping outside DB tx"]
    HTTP --> SUCCESS["Result short transaction"]
    HTTP -. "timeout" .-> UNKNOWN["UNKNOWN + reconciliation"]
    SUCCESS --> DONE["SUBMITTED"]
~~~

Quy trình:

1. Poller/handler kiểm message ID và cập nhật trạng thái đơn hàng **cùng outbox record trong một DB transaction ngắn**.
2. Commit trước khi remote call.
3. Worker nhận record, cấp lease token, commit.
4. Worker gọi HTTP với `operationId`/idempotency key ổn định và timeout hữu hạn.
5. Nếu 201 kèm receipt: transaction ngắn mark SENT; nếu 202: ghi nhận ACCEPTED và theo dõi completion.
6. Nếu 503: retry có backoff; nếu timeout uncertain: truy vấn partner/reconcile trước khi gửi lại nếu cần.
7. Nếu server đã tạo shipment nhưng DB không mark được: retry vẫn không tạo shipment thứ hai nhờ idempotency.
8. Đo transaction duration, pool occupancy, backlog và order completion time trước/sau.

### 29.3. Những trade-off phải nói rõ

- **Eventual consistency:** order có thể ở trạng thái PENDING/PROCESSING trước khi remote xử lý xong.
- **Thêm độ phức tạp vận hành:** outbox table, worker, lease, alert, cleanup.
- **Không phải exactly-once:** có thể gửi lặp; cần receiver idempotent và reconciliation.
- **Độ trễ nghiệp vụ:** tổng completion time chưa chắc nhỏ hơn, nhưng hệ thống ít giữ DB lock/connection hơn.
- **Giới hạn throughput:** vẫn bị giới hạn bởi partner API và capacity worker; cần backpressure.
- **Phân quyền:** worker và source cần quyền DB/API đúng mức, không dùng credential chung vô hạn.

## 30. Case study: Kafka/JMS inbound, DB write và remote notification

### 30.1. Câu chuyện

Một consumer nhận `OrderPaid` từ Kafka hoặc JMS. Business service cập nhật `orders.payment_status`, sau đó gửi thông báo qua HTTP webhook hoặc email provider. Nếu toàn bộ xử lý nằm trong một `@Transactional` method rồi chờ webhook/email chậm, database transaction bị kéo dài; consumer cũng có thể bị chặn, làm tăng lag/unacked.

### 30.2. Mô hình đề nghị

~~~text
Kafka/JMS inbound event
  -> Validate schema + eventId
  -> DB transaction:
       INSERT inbox(eventId) if absent
       UPDATE order payment state
       INSERT outbox(notificationIntent)
     COMMIT
  -> acknowledge/commit inbound theo container policy

Outbox dispatcher:
  claim + COMMIT
  remote webhook/email outside DB transaction
  mark result + COMMIT
~~~

**Inbox/dedup** ở đây là một bảng/unique constraint giúp xử lý an toàn khi broker redeliver cùng event ID. Nếu transaction DB commit nhưng broker ack/offset commit thất bại, event đến lần nữa: inbox phát hiện đã xử lý và tránh ghi business side effect lần hai. Hành vi ack thực tế phụ thuộc container/provider; cần test thay vì giả định Spring Integration làm điều này mặc định.

### 30.3. Những sai lầm dễ phát sinh

- Ack input **trước** khi durable DB intent được commit: crash có thể mất thông báo.
- Gửi webhook **trước** khi DB mutation commit: partner nhận event trong khi DB rollback.
- Dựa vào Kafka offset làm business event ID: offset có phạm vi topic/partition và không thay thế global operation ID.
- Gửi email bằng SMTP rồi rollback DB: email đã gửi không được hoàn tác.
- Giữ JMS transaction trong lúc sleep 60 giây để retry webhook: giữ consumer/session và gây backlog.
- Dùng volatile `ApplicationEventPublisher` không ghi outbox, rồi cho rằng AFTER_COMMIT tự tạo durable messaging.

### 30.4. Kiểm chứng mức hoàn tất

Với email provider, status HTTP `202` hoặc SMTP `250` có thể chỉ chứng minh provider đã **nhận** yêu cầu. “Email delivered” phụ thuộc báo cáo delivery của provider; không đồng nhất `ACCEPTED` với `DELIVERED`. Với webhook, HTTP 200 có thể là confirmation theo contract nhưng vẫn cần xác minh side effect khi nghiệp vụ đòi hỏi.

## 31. Anti-pattern và lý do chúng không giải quyết tận gốc

| Anti-pattern | Vì sao chưa đủ hoặc sai | Hướng sửa |
|---|---|---|
| Mở `@Transactional` rồi gọi HTTP/SFTP | Giữ DB transaction qua I/O, rollback không hoàn tác remote | Commit DB trước, gửi ngoài tx, ghi result bằng tx ngắn |
| Dùng `REQUIRES_NEW` ở helper gửi HTTP | Có thể mở transaction quanh network call; outer transaction vẫn giữ lock | Định lại entry boundary và call graph |
| Dùng `NOT_SUPPORTED` trong outer tx đang giữ lock | Outer transaction bị suspend nhưng chưa commit/release lock | Commit outer trước remote call |
| Dùng `ExecutorChannel` thay cho outbox | Queue in-memory có thể mất khi crash | Durable outbox/queue có ack phù hợp |
| `@Async` + `@TransactionalEventListener(AFTER_COMMIT)` | Không có durable handoff sau commit | Persist outbox trong transaction |
| Poller transaction advice bao cả HTTP handler | DB transaction kéo dài qua poll + downstream | Transaction claim riêng, handoff tách rõ |
| `SELECT FOR UPDATE` rồi POST trước commit | Row lock giữ qua slow partner | Claim + lease + commit, gửi sau |
| Mark SENT trước khi HTTP POST | Crash có thể làm mất thao tác | Mark sau confirmation có ý nghĩa |
| Mark SENT ngay sau enqueue producer future | Async publish có thể fail | Await/result callback/ack phù hợp |
| Retry HTTP timeout với UUID mới | Có thể tạo duplicate tại đích | Stable idempotency key, query/reconcile |
| Chỉ giảm read timeout | Không sửa lock/transaction boundary | Short tx + remote timeout + durable retry |
| Không phân biệt 400 và 503 | Retry dữ liệu sai không có điểm dừng | Classify errors, backoff, DEAD/MANUAL_REVIEW |
| Retry bằng sleep trong DB transaction | Giữ connection/lock trong lúc đợi | Schedule next attempt sau commit |
| Không dùng lease/fencing cho nhiều worker | Hai worker claim/mark state chồng nhau | SKIP LOCKED + lease token + conditional update |
| Lease quá ngắn so với HTTP timeout | Worker khác claim khi request cũ còn chạy | Deadline/heartbeat/fencing/idempotency |
| Lease vô hạn | Job kẹt nếu worker chết | Bounded lease + expiry/recovery |
| Mỗi retry tạo event ID mới | Receiver không dedup được | Business operation ID cố định |
| Coi broker ack = business success | Ack có thể chỉ là nhận ở broker | Tách PUBLISHED/ACCEPTED/COMPLETED |
| Gắn transaction vào mọi layer “cho chắc” | Khó biết actual scope, dễ tạo outer tx | Thiết kế transaction owner rõ, probe/test |
| Chỉ test output channel | Không test external side effect, lock, crash | DB/broker/mock server integration tests |
| Ghi token/PII đầy đủ vào outbox log | Rủi ro dữ liệu và audit | Giảm dữ liệu, mã hóa/quyền truy cập, redact |

## 32. Kế hoạch chuyển đổi từ transaction dài sang thiết kế ngắn

Một ứng dụng production đã chạy lâu năm không nên chuyển sang outbox trong một lần deploy thiếu kế hoạch.

### 32.1. Kiểm kê

Xác định mọi call chain:

~~~text
HTTP/JMS/Kafka/File/SFTP inbound
  -> @Transactional service?
  -> MessageChannel (Direct/Executor/Queue)?
  -> Poller/advice?
  -> Remote adapter/gateway?
  -> DB update?
  -> Retry/error handler?
~~~

Đối chiếu stack traces/tracing để thấy:
- Transaction thực bắt đầu/kết thúc ở method nào.
- Remote I/O xảy ra trước hay sau commit.
- Hệ thống nhận có hỗ trợ idempotency/query status/cancel hay không.
- Nguồn input được ack/mark consumed lúc nào.
- Dữ liệu quan trọng nào cần cùng commit (business row + outbox).

### 32.2. Thiết kế state, version và durable intent

Quy định business state, outbox schema, unique event IDs, retry/lease, owner, data retention, và đường xử lý `UNKNOWN`. **Đặt message contract trước khi viết dispatcher** để tránh phát các event không thể diễn giải khi có replay.

### 32.3. Triển khai song song có kiểm soát

Một cách migration:

1. Thêm outbox table và monitoring.
2. Trong business transaction hiện hữu, ghi outbox intent nhưng **chưa bật publisher mới** để đối soát số lượng.
3. Bật dispatcher cho một destination/tenant nhỏ; xác nhận idempotency và receipts.
4. Chuyển dần outbound call khỏi transaction cũ.
5. Theo dõi duplicate, unknown, pool/lock duration, retry và backlog.
6. Gỡ code gửi đồng bộ cũ khi đã xác nhận không phát song song hai đường.
7. Chuẩn bị rollback stateful, không làm mất outbox rows đã commit hoặc gửi hai lần không kiểm soát.

**Cẩn trọng dual-write:** trong giai đoạn migration, nếu vừa giữ HTTP send cũ vừa chạy outbox dispatcher cho cùng operation, bạn có thể nhân đôi side effect. Cần feature flag/quy tắc ownership rõ cho **một** đường gửi, và unique idempotency key.

### 32.4. Khi nào không cần outbox?

Outbox có thêm độ phức tạp. Với một request **read-only** gọi dịch vụ ngoài sau khi đọc data rồi không có nhu cầu durability, chỉ cần **kết thúc transaction trước khi gọi network** và đặt timeout/bulkhead có thể đủ. Với tác vụ nền tái tạo được từ nguồn đáng tin mà mất một attempt không gây hậu quả, in-memory queue có thể chấp nhận. Quyết định dựa **mức tổn thất nếu crash/lặp**, không vì muốn dùng pattern “hiện đại”.

## 33. Checklist review code và pull request

- [ ] Không có slow HTTP/SFTP/broker call hoặc `Future.get()/join()` trong DB transaction sau khi đã giữ locks.
- [ ] `@Transactional` boundary có owner rõ, không bị outer transaction bao ngoài ngoài ý muốn.
- [ ] Không dùng `REQUIRES_NEW`/`NOT_SUPPORTED` để che một outer transaction vẫn giữ resource.
- [ ] Nếu caller dùng gateway đồng bộ, xác định caller có giữ DB transaction khi chờ reply hay không.
- [ ] Nếu poller có transaction advice, kiểm tra advice có bao toàn bộ handler slow không.
- [ ] Nếu dùng executor/queue in-memory, rủi ro mất message khi crash đã được chấp nhận hoặc có durable source.
- [ ] Nếu cần reliable delivery, business state + outbox intent được commit nguyên tử trong cùng DB.
- [ ] Claim outbox có transaction ngắn, không giữ `SELECT FOR UPDATE` qua remote I/O.
- [ ] Có timeout/deadline cho client, phù hợp lease duration hoặc heartbeat.
- [ ] Worker có lease expiry, conditional state update và fencing token.
- [ ] Partner/consumer có idempotency key hoặc kế hoạch reconciliation khi outcome không chắc.
- [ ] `eventId/operationId` không đổi giữa retry, `attemptId` có thể đổi.
- [ ] Error classification phân biệt transient, permanent và ambiguous outcome.
- [ ] Retry có backoff/jitter/giới hạn, không sleep trong transaction.
- [ ] Không mark SENT trước khi có confirmation có ý nghĩa theo contract.
- [ ] Không nhầm broker ack, HTTP 202 hoặc output channel với nghiệp vụ hoàn tất.
- [ ] Có đường xử lý shutdown/restart, stale lease, duplicate và cancellation race.
- [ ] Dữ liệu outbox/audit không chứa secret hoặc PII ngoài mục đích cần thiết.
- [ ] Test probe xác nhận remote call không nằm trong DB transaction thực tế.
- [ ] Có test lock release với DB test khi cần chứng minh contention.
- [ ] Có test crash windows, remote response lost, DB mark failure và idempotent replay.
- [ ] Có metrics transaction duration, pool occupancy, backlog age, UNKNOWN và manual review.
- [ ] Có runbook reprocess/reconcile an toàn và phân quyền operator.

## 34. Câu hỏi tình huống có giải thích

### A. “Gọi HTTP trong @Transactional thì rollback HTTP được không?”

**Không.** Local database transaction rollback chỉ bao những thao tác/tài nguyên tham gia nó. HTTP POST có thể đã hoàn tất ở server. Cần API idempotency, status lookup, compensation hoặc workflow quản lý trạng thái.

### B. “Chuyển DirectChannel thành ExecutorChannel là xong?”

**Không chắc.** Thread-bound transaction thông thường không đi theo executor thread, nhưng caller có thể vẫn chờ gateway reply trong transaction hoặc message in-memory bị mất khi crash. Cần xét durable handoff, outer tx, exception handling và correctness.

### C. “Dùng @Transactional(NOT_SUPPORTED) cho client có được giải phóng row lock không?”

**Không nếu outer transaction chưa commit.** Outer tx có thể bị suspend nhưng vẫn giữ tài nguyên. Phải commit DB trước remote call theo đúng call graph, không chỉ đổi annotation của client.

### D. “Một worker lấy SELECT FOR UPDATE, gọi HTTP rồi commit. Đã có outbox nên chắc an toàn?”

**Không.** Row lock vẫn bị giữ qua I/O. Outbox dispatcher phải claim/lease và commit trước khi gửi; dùng fencing khi ghi kết quả.

### E. “Response HTTP timeout nghĩa là server chưa tạo shipment?”

**Không.** Server có thể đã commit nhưng response bị mất. Retry với idempotency key hoặc truy vấn outcome; khi không thể xác định, quản lý `UNKNOWN`/manual review.

### F. “Nếu worker crash sau commit order, trước gửi HTTP?”

**Transactional outbox** giữ ý định gửi trong DB để worker khác tiếp tục. Nếu chỉ `@Async` event trong RAM, thao tác có thể mất.

### G. “Nếu worker crash sau HTTP success nhưng trước mark SENT?”

Có thể gửi lại. Bên nhận phải idempotent hoặc có reconciliation/compensation; đừng công bố exactly-once end-to-end khi chưa có bảo đảm tương ứng.

### H. “mark SENT rồi mới send có giúp tránh duplicate?”

Có thể giảm một số retry nhưng **gây mất message** khi crash giữa hai bước. Mô hình reliable thường chấp nhận at-least-once và deduplication.

### I. “Lease token ngăn remote request bị gửi hai lần?”

**Không.** Token giúp fencing các DB state transitions. Remote có thể đã nhận request từ worker cũ; phải có remote idempotency và policy deadline.

### J. “JMS session transacted có tự atomic với SQL?”

**Không tự động.** Cần hiểu transaction manager và khả năng tài nguyên tham gia, nếu không vẫn có crash window giữa DB commit và broker ack. Dùng inbox/outbox/dedup theo kiến trúc.

### K. “Kafka transaction giải quyết mọi side effect HTTP?”

**Không.** Kafka transaction có phạm vi Kafka phù hợp; không rollback HTTP hoặc SFTP. Cần workflow/idempotency ngoài Kafka.

### L. “Có thể thêm sleep 30 giây trong @Transactional để chờ API hồi phục?”

**Không nên.** Sleep sẽ kéo dài transaction/lock và giảm throughput. Lưu `next_attempt_at`, commit rồi retry ở lần poll sau.

### M. “Một transaction probe báo false là đủ để chứng minh DB pool không bị giữ?”

**Chưa đủ.** Nó chứng minh không có actual transaction trên thread đó, nhưng outer tx bị suspend hoặc lock từ thread khác vẫn có thể tồn tại. Kiểm DB lock/connection dưới load/test topology thật.

### N. “Tại sao HTTP 202 không được mark REMOTE_COMPLETED?”

Vì `202 Accepted` thường chỉ xác nhận tiếp nhận một tác vụ chưa hoàn tất. Theo contract API, nên ghi `ACCEPTED`/`PUBLISHED` rồi theo dõi completion bằng callback/query/receipt.

### O. “Khi nào dùng saga/compensation?”

Khi workflow xuyên nhiều hệ thống có các bước local commit riêng và cần xử lý một bước sau thất bại. Compensation là **hành động nghiệp vụ bù**, có thể fail và cần theo dõi; nó **không phải rollback ACID** của remote side effect.

### P. “Chỉ đổi transaction boundary mà throughput không tăng, vì sao?”

Có thể đã bỏ DB lock bottleneck nhưng partner API vẫn là nút nghẽn, executor chưa giới hạn hợp lý, connection pool của HTTP bị bão hòa, hoặc retry storm. Cần metric từng tầng, không kết luận tách transaction không có giá trị chỉ vì tổng latency chưa giảm.

## 35. Bài thực hành tổng hợp

**Đề bài:** Xây một mini service Spring Boot + Spring Integration nhận yêu cầu tạo shipment, ghi DB rồi gửi HTTP tới đối tác. Hãy làm hai phiên bản để so sánh rủi ro.

### 35.1. Phiên bản A — anti-pattern

~~~text
@Transactional
  update orders
  HTTP POST shipping service (fake delay 2–5s)
  update orders with receipt
COMMIT
~~~

Dùng test DB và fake HTTP server có latch để kiểm: row lock/connection giữ lâu, timeout trong lúc đã có remote side effect, duplicate khi caller retry.

### 35.2. Phiên bản B — outbox

~~~text
TX #1:
  update orders + insert outbox PENDING
COMMIT

dispatcher:
  TX claim lease -> COMMIT
  HTTP POST idempotency-key outside DB tx
  TX mark SENT / RETRY / UNKNOWN -> COMMIT
~~~

Kiểm các tình huống: happy path, HTTP 503, timeout after commit, DB mark failure, stale lease, duplicate input, worker restart và cancellation race.

### 35.3. Tiêu chí nghiệm thu

| Tiêu chí | Bằng chứng |
|---|---|
| Transaction DB không chờ HTTP | Probe + lock/concurrency test |
| Business + outbox nguyên tử | Rollback test trên database thật |
| Remote call có giới hạn thời gian | Mock server timeout & retry policy |
| Side effect không nhân đôi | Stateful test với idempotency key |
| Worker restart không làm mất job | Durable PENDING/lease expiry test |
| Ghi trạng thái đúng owner | Fencing token/conditional update |
| Khi outcome không chắc chắn | UNKNOWN + reconciliation/manual review |
| Không tăng tải vô hạn | Bounded worker + backpressure metrics |
| Audit có thể truy vết | operationId, attemptId, trạng thái, receipt |
| Không lộ dữ liệu | Secret redaction và access control |

Kết quả phải được báo cáo **theo từng tầng**: DB transaction, remote I/O, business outcome và durability. Đừng chỉ so tổng thời gian end-to-end giữa A và B: phiên bản B có thể hoàn thành nghiệp vụ sau, nhưng không giữ DB resources qua remote latency và chịu lỗi tốt hơn.

## 36. Tài liệu tham khảo

Để kiểm tra API, transaction semantics và configuration theo version thực tế:

- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Integration — Transaction Support: https://docs.spring.io/spring-integration/reference/transactions.html
- Spring Integration — Poller: https://docs.spring.io/spring-integration/reference/endpoint.html
- Spring Integration — Message Channels: https://docs.spring.io/spring-integration/reference/channel.html
- Spring Integration — JDBC Support: https://docs.spring.io/spring-integration/reference/jdbc.html
- Spring Integration — HTTP Support: https://docs.spring.io/spring-integration/reference/http.html
- Spring for Apache Kafka Reference: https://docs.spring.io/spring-kafka/reference/
- Spring AMQP Reference: https://docs.spring.io/spring-amqp/reference/

**Lưu ý phiên bản:** Các dependency, callback và DSL overload có thể khác theo Spring Boot/Spring Integration/driver/client version. Mọi snippet được gọi rõ là *mã minh họa* nếu còn interface hoặc helper giả định; chúng không phải bằng chứng đã biên dịch/chạy trong module. Những SQL claim/lease là ví dụ cho PostgreSQL, cần thiết kế và test riêng khi dùng MySQL, Oracle hoặc database khác.

## Kết luận

**“Tránh giữ transaction khi gọi dịch vụ chậm”** không chỉ là một mẹo tăng tốc trong Spring Integration Adapters, mà là **nguyên tắc thiết kế ranh giới nhất quán**: database transaction chỉ nên bao các thao tác cần atomicity cục bộ, còn HTTP/SFTP/JMS/AMQP/Kafka hoặc các I/O bên ngoài phải được xử lý bằng cơ chế phù hợp với latency và failure độc lập của chúng. `DirectChannel`, gateway đồng bộ và poller transaction advice có thể vô tình kéo dài transaction; `ExecutorChannel` hoặc `@Async` có thể tách thread nhưng không bảo đảm durable delivery. Với dữ liệu quan trọng, giải pháp bền vững thường là **business state + transactional outbox trong một commit ngắn**, sau đó **claim/lease → commit → remote call ngoài transaction → commit kết quả**, kèm retry có giới hạn, stable idempotency key, fencing, reconciliation và observability. Khi đo được cả lock/connection duration lẫn outcome ở hệ thống đích, đội ngũ mới có thể chứng minh rằng giao dịch được giữ ngắn **mà không đánh đổi tính đúng đắn nghiệp vụ**.
