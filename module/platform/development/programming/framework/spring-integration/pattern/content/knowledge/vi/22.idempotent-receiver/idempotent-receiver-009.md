# Idempotency qua nhiều instance

> **Chương:** Idempotent receiver  
> **Module:** `SPRING_INTEGRATION_PATTERN` — học triển khai Enterprise Integration Patterns (EIP) với Spring Integration để xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng. Thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation, đồng thời kiểm thử, theo dõi các nhánh xử lý. Bài này tập trung vào **bảo đảm cùng một thao tác nghiệp vụ không tạo thêm tác dụng phụ khi message được giao lại hoặc được xử lý đồng thời trên nhiều instance**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **Idempotent Receiver** trong hệ thống message-driven và vì sao `@Transactional` hay `ConcurrentHashMap` đơn lẻ không bảo đảm idempotency khi có nhiều replica.
2. Phân biệt **delivery**, **processing attempt**, **business operation**, **correlation group**, **idempotency key** và **business result**.
3. Thiết kế khóa nghiệp vụ ổn định, có namespace cho tenant và phân biệt thao tác mới hợp lệ với lần giao lại của thao tác cũ.
4. Phân tích các cửa sổ lỗi: hai instance xử lý đồng thời, commit xong mất ACK, worker chết giữa chừng, lease hết hạn, redelivery/DLQ replay và timeout bên ngoài.
5. Chọn giữa **unique constraint + transaction**, **shared ConcurrentMetadataStore**, **Redis atomic operation**, **lease/fencing** và **idempotency tại API đích**; hiểu rõ mỗi cơ chế bảo vệ được ranh giới nào.
6. Viết ví dụ Java 17, SQL PostgreSQL và Spring Integration Java DSL cho một receiver có **trạng thái xử lý và kết quả bền vững**.
7. Thiết kế kiểm thử concurrent/multi-instance, restart, duplicate khác payload, idempotent reply và outbox để tránh gửi kết quả cuối hai lần.
8. Đo duplicate hits, conflicts, lock contention, retry/backpressure và bảo vệ khóa, dữ liệu qua các service boundaries.

## 2. Bối cảnh: ba instance cùng nhận một lệnh giữ hàng

Một ứng dụng Spring Integration chạy ba replica sau load balancer, cùng tiêu thụ request từ broker. Lệnh giữ hai quyển sách:

~~~json
{
  "tenantId": "shop-a",
  "commandId": "CMD-1001",
  "orderId": "ORD-981",
  "lineId": "LINE-02",
  "sku": "BOOK-42",
  "quantity": 2,
  "executionId": "RUN-01"
}
~~~

Lần giao đầu tới **instance A**. A ghi đã giữ hàng thành công vào database, nhưng chết trước khi ACK broker. Broker giao lại cùng command tới **instance B**. Đồng thời, producer đã retry và bản thứ hai có thể đến **instance C**.

~~~mermaid
sequenceDiagram
    participant Q as Broker
    participant A as Instance A
    participant B as Instance B
    participant C as Instance C
    participant DB as Shared DB
    Q->>A: CMD-1001 / delivery #1
    A->>DB: Atomic claim + reserve stock
    DB-->>A: COMMITTED
    A--xQ: Crash before ACK
    Q->>B: CMD-1001 / redelivery
    Q->>C: CMD-1001 / duplicate publish
    B->>DB: Same operation key
    C->>DB: Same operation key
    DB-->>B: Existing committed result
    DB-->>C: Existing committed result
    B-->>Q: ACK after safe processing
~~~

**Mục tiêu:** Dù có ba attempts và ba replica, tồn kho chỉ bị trừ **hai sản phẩm một lần**, không phải hai sản phẩm cho mỗi lần giao message.

**Không đủ** nếu A, B, C mỗi instance đều có một `Set<String> processedIds` trong RAM. Mỗi instance không nhìn thấy trạng thái của instance khác; sau restart, set cũng có thể mất.

### 2.1. “Đã thấy message” không đồng nghĩa “đã commit nghiệp vụ”

Một receiver có thể phát hiện duplicate ở ingress nhưng vẫn xảy ra lỗi:

~~~text
1. Instance A lưu key "đã xử lý" vào cache.
2. A crash TRƯỚC khi trừ tồn kho.
3. B nhận redelivery, thấy key đã tồn tại.
4. B bỏ qua.
5. Lệnh giữ hàng không bao giờ được thực hiện.
~~~

Ngược lại, nếu đánh dấu processed **sau** khi gọi API ngoài:

~~~text
1. A gọi API giữ hàng, API đã commit.
2. A crash TRƯỚC khi lưu key "đã xử lý".
3. B không thấy key và gọi lại API.
4. Tồn kho có thể bị giữ hai lần.
~~~

Hai cửa sổ này cho thấy **dedup ở một bước không nguyên tử với side effect chưa đủ** để tuyên bố “exactly once”.

## 3. Idempotent Receiver là gì?

EIP **Idempotent Receiver** bảo đảm khi một message đại diện cho **cùng thao tác nghiệp vụ** được gửi lặp, receiver không tạo ra những tác dụng phụ mới ngoài tác dụng của lần xử lý hợp lệ đầu tiên.

Với thao tác `reserveStock(commandId=CMD-1001)`:

~~~text
reserve(CMD-1001) lần 1 -> RESERVED, stock -2
reserve(CMD-1001) lần 2 -> trả RESERVED đã lưu, stock không đổi
reserve(CMD-1001) lần 3 -> trả RESERVED đã lưu, stock không đổi
~~~

Nhưng với `CMD-1002` là **thao tác mới được nghiệp vụ cho phép**:

~~~text
reserve(CMD-1002) -> có thể giữ thêm 2 sản phẩm,
                     tuân theo số lượng còn lại và policy.
~~~

Idempotency không có nghĩa **tất cả message giống về nội dung đều bị bỏ qua**. Nó có nghĩa những **attempts của cùng một business operation** có tác dụng tương đương thực thi một lần.

### 3.1. Ba tầng khác nhau

| Tầng | Câu hỏi | Bằng chứng phù hợp |
| --- | --- | --- |
| **Transport delivery** | Record đã được giao/ACK chưa? | Broker offset, delivery tag, ACK/transaction |
| **Receiver processing** | Operation đã được nhận/đang xử lý/chốt kết quả chưa? | Shared idempotency ledger/inbox |
| **Business effect** | Tồn kho/thanh toán/đơn hàng đã commit một lần chưa? | Unique business operation tại nơi mutation xảy ra |

Một hệ thống có thể nhận cùng record nhiều lần, chạy handler nhiều lần nhưng **chỉ commit business effect một lần**. Đó là mục tiêu thực tế thường khả thi hơn tuyên bố mọi thành phần toàn hệ thống đều chạy đúng một lần.

### 3.2. Idempotency không phải correlation

| Định danh | Mục đích | Có đổi khi retry/redelivery? |
| --- | --- | --- |
| `MessageHeaders.ID` | ID envelope message | Có thể đổi khi tái tạo message |
| Kafka topic/partition/offset | Vị trí record của transport | Có thể đổi khi republish |
| JMS/AMQP delivery metadata | Giao lần nào, có redeliver không | Có thể đổi |
| `businessCorrelationId` | Trace các bước của cùng đơn | Thường giữ, nhưng có thể quá rộng |
| `executionId` | Correlate các replies thuộc một lần workflow | Có thể đổi khi reprocess |
| **`operationId` / `commandId`** | Nhận diện một tác vụ có side effect | **Phải giữ nguyên** khi retry cùng task |
| `traceId`, `spanId` | Quan sát phân tán | Không thay idempotency key |

Một Aggregator có thể gom theo `executionId` trong khi Idempotent Receiver chặn trùng theo `commandId + lineId + operationType`. **Cần cả hai**, không gộp chúng thành một ID cho tiện.

## 4. Khóa idempotency có phạm vi chính xác

Ví dụ một đơn có ba dòng hàng, cùng `commandId` cho batch. Nếu chỉ dùng `commandId` để dedup, có thể vô tình bỏ hai dòng còn lại.

### 4.1. Khóa theo thao tác

~~~text
(tenantId, commandId, lineId, operationType)

(shop-a, CMD-1001, LINE-01, RESERVE_STOCK)
(shop-a, CMD-1001, LINE-02, RESERVE_STOCK)
(shop-a, CMD-1001, LINE-03, RESERVE_STOCK)
~~~

Mỗi dòng là một operation riêng. Lệnh `RELEASE_STOCK` cho cùng dòng có `operationType` khác, **không** bị chặn nhầm như lệnh giữ hàng.

### 4.2. Những trường không nên đưa vào khóa

- `retryCount`, `deliveryAttempt`, `JMSXDeliveryCount`: thay đổi theo số lần thử.
- Timestamp của lúc consumer **nhận lại** message.
- `MessageHeaders.ID`: có thể sinh lại ở mỗi envelope.
- `executionId` nếu business contract quy định reprocess cùng command **không** được commit thêm.
- `traceId`, `spanId`: dành cho observability.
- Payload hash thô chưa canonicalize: field order/serializer có thể làm cùng lệnh mang hash khác nhau.

### 4.3. Scope theo tenant và nguồn đáng tin

`commandId=CMD-1001` của `shop-a` và `shop-b` không phải một operation. Mặt khác, client không được tự khai `tenantId=shop-b` để xem cached result của tenant B.

Khóa cần được xây từ **identity đã xác thực** và contract của nghiệp vụ. Nếu consumer lấy dữ liệu từ header bên ngoài, phải kiểm tra chữ ký/ACL/mapping tenant trước khi dùng khóa.

### 4.4. Cùng key nhưng payload khác là conflict

Hai yêu cầu:

~~~text
Key: (shop-a,CMD-1001,LINE-02,RESERVE_STOCK)
Original: sku=BOOK-42, quantity=2
Duplicate: sku=BOOK-42, quantity=20
~~~

Không được:

1. Thực hiện thêm lần giữ hàng với 20 sản phẩm; hoặc
2. Trả `RESERVED` của lệnh hai sản phẩm và để client tưởng đã giữ 20.

Lưu **các trường bất biến có ảnh hưởng nghiệp vụ** hoặc một **request fingerprint đã canonicalize có version**; khi cùng key mà nội dung khác, trả `IDEMPOTENCY_CONFLICT` và lưu audit. Không tự sửa ledger theo yêu cầu cuối.

## 5. Định nghĩa tính đúng đắn khi nhiều replica

Một receiver phân tán cần tối thiểu những bất biến sau:

1. **At most one committed effect cho mỗi operation key** trong một phạm vi consistency được xác định.
2. **Mọi duplicate hợp lệ có cùng kết quả terminal** hoặc một response chỉ ra operation vẫn đang xử lý.
3. **Conflicting duplicate không được đổi effect** đã commit.
4. **Crash trước commit** cho phép xử lý lại an toàn; **crash sau commit** cho phép lấy kết quả cũ.
5. **Hai instance tranh cùng key** được giải quyết nguyên tử, không check-then-act trên cache riêng.
6. **Operation khác key** vẫn có thể xử lý đồng thời; không khóa toàn hệ thống vô lý.
7. Khi business effect ở **hệ thống ngoài** không nằm cùng transaction, phải có **idempotency ở đích hoặc reconciliation**; local lock không đủ.

### 5.1. Race condition của lối `contains → add`

~~~java
// KHÔNG AN TOÀN cho multi-instance, và còn race ngay trong một JVM
if (!processedIds.contains(key)) {
    reserveStock(command);
    processedIds.add(key);
}
~~~

Hai instances có thể đồng thời thấy “chưa có key” rồi cùng gọi `reserveStock`.

Ngay cả nếu dùng một map thread-safe, hai bước `contains` và `add` vẫn không atomic như một operation. Và nếu map chỉ nằm trong RAM của một instance, việc atomic ở cấp process **không** tạo atomic giữa các node.

### 5.2. Race bằng sơ đồ

~~~mermaid
sequenceDiagram
    participant A as Instance A
    participant B as Instance B
    participant DB as Shared database
    A->>DB: key exists?
    B->>DB: key exists?
    DB-->>A: no
    DB-->>B: no
    A->>DB: reserve stock
    B->>DB: reserve stock
    Note over A,B: Two business effects unless one atomic claim/commit prevents it
~~~

Giải pháp cần một **consistency boundary chung**: unique index/transaction ở DB sở hữu mutation, hoặc một backend idempotent nhận token và tự thực hiện mutation một lần.

## 6. Bảng so sánh chiến lược distributed idempotency

| Giải pháp | Bảo vệ tốt điều gì? | Không tự bảo đảm điều gì? |
| --- | --- | --- |
| **Unique constraint trong cùng DB transaction với mutation** | Chặn hai worker cùng commit một effect trong DB đó | API ngoài không cùng transaction, broker publish/ACK |
| **Idempotent endpoint ở hệ thống đích** | Receiver thật của side effect nhận cùng key và trả outcome đã lưu | Hệ thống gọi phải giữ key và phân biệt payload conflict |
| **Shared `ConcurrentMetadataStore`** | Atomic key claim/selection cho nhiều SI instances nếu backend hỗ trợ | Atomic commit với business DB/API; hoàn thành nghiệp vụ |
| **Redis `SET NX` + TTL** | Tranh quyền claim/lease có giới hạn giữa instances | Worker cũ có thể tiếp tục khi lease hết hạn; rollback/side effect |
| **Database inbox + outbox** | Durable input dedup và phát output có thể retry | External side effect ngoài consistency boundary |
| **Partition/order theo business key** | Giảm mức tranh chấp nếu một owner được gán | Failover/rebalance/redelivery vẫn có thể trùng |
| **Local `ConcurrentHashMap`** | Demo/test trong một JVM | Restart, replica khác, durable correctness |

**Lựa chọn ưu tiên:** Nếu thao tác và ledger cùng nằm trong một database có transaction/unique index đáng tin, hãy bắt đầu bằng **ràng buộc duy nhất + commit kết quả trong cùng transaction**. Nếu side effect là **HTTP API ngoài**, cần idempotency token được hỗ trợ bởi phía đích hoặc một quy trình reconcile rõ.

### 6.1. “Dùng Redis để lock” không phải một câu trả lời hoàn chỉnh

Redis có thể rất hữu ích để giảm tranh chấp và điều phối, nhưng chỉ một khóa với TTL **không đủ** để khẳng định effect chỉ xảy ra một lần. Cần xét lease expiry, stale workers, lock renewal, fencing, mất kết nối Redis và consistency của backend nơi mutation thật sự diễn ra.

### 6.2. “Kafka exactly once” không bảo vệ mọi side effect

Các cơ chế transaction/exactly-once của một messaging platform có phạm vi cụ thể, chẳng hạn một số luồng xử lý và ghi record trong broker. Chúng **không tự mở rộng** giao dịch nguyên tử tới database hoặc HTTP payment gateway tùy ý. Khi bài toán là “không trừ tiền hai lần”, kiểm tra ở **nơi trừ tiền** mới quyết định correctness.

## 7. Cách đáng tin cậy: cùng transaction cho ledger và mutation

Ví dụ dùng **PostgreSQL** và Spring JDBC để thực hiện giữ hàng. Cấu trúc dữ liệu:

~~~sql
CREATE TABLE inventory_stock (
    tenant_id       VARCHAR(80) NOT NULL,
    sku             VARCHAR(120) NOT NULL,
    available       BIGINT NOT NULL CHECK (available >= 0),
    PRIMARY KEY (tenant_id, sku)
);

CREATE TABLE reservation_operation (
    tenant_id       VARCHAR(80) NOT NULL,
    command_id      VARCHAR(120) NOT NULL,
    line_id         VARCHAR(120) NOT NULL,
    operation_type  VARCHAR(40) NOT NULL,
    sku             VARCHAR(120) NOT NULL,
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    state           VARCHAR(20) NOT NULL,
    outcome_code    VARCHAR(40),
    PRIMARY KEY (
        tenant_id, command_id, line_id, operation_type
    )
);
~~~

**Bất biến dữ liệu:**

- Primary key chính là **operation identity** được duyệt.
- `sku` và `quantity` lưu để xác minh duplicate không thay đổi nội dung yêu cầu.
- `state=PROCESSING` chỉ nằm trong **transaction chưa commit** của flow minh họa; khi transaction commit thì phải là `COMPLETED`. Không cố tình commit trạng thái PROCESSING rồi hy vọng worker tiếp theo đoán đã thành công hay chưa.
- `outcome_code` là kết quả nghiệp vụ đã chốt: `RESERVED` hoặc `OUT_OF_STOCK`.
- `executionId` không ở primary key, vì một retry/replay cùng command có thể chạy trong execution mới.

### 7.1. Tại sao `ON CONFLICT DO NOTHING` có ích?

Một unique constraint ở database là **bộ phân xử chung** cho hai instance. Trong PostgreSQL `READ COMMITTED`, khi hai transactions chèn cùng primary key, một transaction sẽ phải chờ hoặc va unique constraint theo ngữ nghĩa DB; không có trường hợp cả hai cùng commit hai ledger rows cho cùng key.

Điều quan trọng hơn: **mutation tồn kho và cập nhật kết quả operation phải commit trong cùng transaction**. Nếu process chết trước commit, DB rollback cả ledger lẫn mutation. Nếu chết sau commit, duplicate thấy kết quả đã lưu.

~~~mermaid
flowchart TD
    IN["Receive ReserveCommand"] --> TX["BEGIN transaction"]
    TX --> I["INSERT operation key ON CONFLICT DO NOTHING"]
    I --> L["SELECT row FOR UPDATE"]
    L --> C{"Existing state and request?"}
    C -->|"Same key, same request, completed"| R["Return recorded outcome"]
    C -->|"Same key, different request"| ERR["IDEMPOTENCY_CONFLICT / ROLLBACK"]
    C -->|"New operation"| U["UPDATE stock atomically"]
    U --> O["Write outcome to ledger"]
    O --> COM["COMMIT"]
    R --> END["Reply for current execution"]
    COM --> END
~~~

**Lưu ý transaction:** sơ đồ này bảo vệ **database nội bộ**. Nếu trong bước `UPDATE stock` thực chất là gọi HTTP bên ngoài, tính nguyên tử không còn như sơ đồ.

## 8. Java 17: command, receipt và service transacted

Những đoạn code sau tập trung vào logic chính, không có package/build/dependency khai báo. Chúng minh họa **PostgreSQL + Spring JDBC + Spring Transaction** với schema ở mục 7, và yêu cầu gọi qua bean Spring để `@Transactional` thực sự được áp dụng.

### 8.1. Java records

~~~java
record ReserveStockCommand(
    String tenantId,
    String commandId,
    String executionId,
    String orderId,
    String lineId,
    String sku,
    int quantity
) {
    ReserveStockCommand {
        require(tenantId, "TENANT");
        require(commandId, "COMMAND_ID");
        require(executionId, "EXECUTION_ID");
        require(orderId, "ORDER_ID");
        require(lineId, "LINE_ID");
        require(sku, "SKU");

        if (quantity <= 0) {
            throw new IllegalArgumentException("INVALID_QUANTITY");
        }
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + "_MISSING");
        }
    }
}

record ReservationReceipt(
    String executionId,
    String orderId,
    String lineId,
    String outcomeCode
) {}

record OperationRow(
    String sku,
    int quantity,
    String state,
    String outcomeCode
) {}

final class IdempotencyConflict extends RuntimeException {
    IdempotencyConflict() {
        super("IDEMPOTENCY_CONFLICT");
    }
}
~~~

`ReserveStockCommand` là dữ liệu đã được xác thực ở ingress của flow demo. **Không** lấy `tenantId` do client tự khai mà bỏ qua AuthN/AuthZ của tầng HTTP/broker.

### 8.2. Transactional service

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JdbcReservationService {
    private final JdbcTemplate jdbc;

    JdbcReservationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public ReservationReceipt reserve(ReserveStockCommand cmd) {
        String operation = "RESERVE_STOCK";

        // PostgreSQL: unique key là arbiter cho mọi replica.
        int inserted = jdbc.update("""
            INSERT INTO reservation_operation
              (tenant_id, command_id, line_id, operation_type,
               sku, quantity, state, outcome_code)
            VALUES (?, ?, ?, ?, ?, ?, 'PROCESSING', NULL)
            ON CONFLICT DO NOTHING
            """,
            cmd.tenantId(), cmd.commandId(), cmd.lineId(),
            operation, cmd.sku(), cmd.quantity());

        // SELECT sau INSERT và FOR UPDATE để giữ khóa dòng
        // trong transaction đến lúc hoàn tất business mutation.
        OperationRow row = jdbc.queryForObject("""
            SELECT sku, quantity, state, outcome_code
              FROM reservation_operation
             WHERE tenant_id = ? AND command_id = ?
               AND line_id = ? AND operation_type = ?
             FOR UPDATE
            """,
            (rs, index) -> new OperationRow(
                rs.getString("sku"),
                rs.getInt("quantity"),
                rs.getString("state"),
                rs.getString("outcome_code")),
            cmd.tenantId(), cmd.commandId(), cmd.lineId(), operation);

        if (row == null) {
            throw new IllegalStateException("OPERATION_ROW_MISSING");
        }

        // Cùng identity nhưng SKU/quantity khác: reject, không reuse.
        if (!cmd.sku().equals(row.sku())
                || cmd.quantity() != row.quantity()) {
            throw new IdempotencyConflict();
        }

        // Redelivery sau commit: trả lại outcome, không trừ kho lần nữa.
        if ("COMPLETED".equals(row.state())) {
            return new ReservationReceipt(
                cmd.executionId(), cmd.orderId(),
                cmd.lineId(), row.outcomeCode());
        }

        if (inserted != 1 || !"PROCESSING".equals(row.state())) {
            // Không tự chạy side effect cho một trạng thái kế thừa
            // không rõ provenance; cần reconciliation.
            throw new IllegalStateException(
                "OPERATION_STATE_REQUIRES_RECONCILIATION");
        }

        // Mutation có điều kiện, atomic, cùng database và transaction.
        int changed = jdbc.update("""
            UPDATE inventory_stock
               SET available = available - ?
             WHERE tenant_id = ? AND sku = ?
               AND available >= ?
            """,
            cmd.quantity(), cmd.tenantId(),
            cmd.sku(), cmd.quantity());

        String outcome = changed == 1
            ? "RESERVED"
            : "OUT_OF_STOCK";

        jdbc.update("""
            UPDATE reservation_operation
               SET state = 'COMPLETED', outcome_code = ?
             WHERE tenant_id = ? AND command_id = ?
               AND line_id = ? AND operation_type = ?
            """,
            outcome,
            cmd.tenantId(), cmd.commandId(), cmd.lineId(), operation);

        // Spring transaction proxy commit trước khi caller nhận kết quả.
        return new ReservationReceipt(
            cmd.executionId(), cmd.orderId(), cmd.lineId(), outcome);
    }
}
~~~

### 8.3. Tại sao phiên bản này chống trùng giữa nhiều instance?

Trong cùng một PostgreSQL database, với transaction `READ_COMMITTED` và unique primary key:

1. **A** chèn operation key, khóa row và cập nhật tồn kho.
2. **B** chèn cùng key phải chờ logic unique conflict/transaction của PostgreSQL.
3. Nếu **A commit**, **B** thấy row `COMPLETED` rồi trả kết quả cũ.
4. Nếu **A rollback** vì crash, B có thể trở thành worker thực hiện operation.
5. A commit rồi mất ACK: redelivery vẫn đọc outcome đã commit thay vì trừ thêm.

**Giới hạn của code:** minh họa một transaction trên **một** database. Nó chưa có retry cho SQL deadlock/connection failure, không phát outbox, không xử lý cross-region active-active database replication, không có API bên ngoài và chưa có schema migration/Gradle build. Mục tiêu là làm rõ **vị trí đặt ràng buộc nguyên tử**.

### 8.4. Đừng dùng `@Transactional` sai ranh giới

`@Transactional` ở Spring thường được áp qua proxy. Một lời gọi **tự gọi nội bộ** `this.reserve(...)` trong cùng class có thể bỏ qua proxy và transaction advice, tùy cấu hình. Với IntegrationFlow, nên inject bean service đã được Spring quản lý và gọi method qua endpoint/proxy phù hợp, rồi test transaction thật bằng database.

Nếu inventory nằm trong **database khác** hoặc được gọi qua HTTP, annotation này **không làm hai hệ thống cùng commit/rollback**.

### 8.5. `OUT_OF_STOCK` cũng là một kết quả cần nhớ

Giả sử command `CMD-1001` trả `OUT_OF_STOCK` ở thời điểm tồn kho thiếu. Một giờ sau kho được bổ sung hàng; cùng command bị redeliver. Idempotency đúng nghĩa với **terminal result** của ví dụ sẽ **trả lại OUT_OF_STOCK**, không tự thử giữ hàng lại vì tình hình đã thay đổi.

Nếu nghiệp vụ muốn **thử giữ hàng mới sau khi restock**, hãy phát hành **command mới** hoặc định nghĩa trạng thái retryable rõ — không bí mật đổi outcome của một command đã chốt.

## 9. Spring Integration Java DSL: handler idempotent trong flow

Trong thiết kế này, **nguồn bảo vệ chính** là `JdbcReservationService` với transaction chung ở mục 8. Spring Integration chịu trách nhiệm tiếp nhận, định tuyến, retry có kiểm soát, error channel và trả reply.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class IdempotentReservationFlowConfiguration {

    @Bean("reservations.commands.in")
    DirectChannel commandsIn() {
        return new DirectChannel();
    }

    @Bean("reservations.receipts.out")
    QueueChannel receiptsOut() {
        // Dùng để quan sát trong bài học/test.
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow reserveEachCommand(JdbcReservationService service) {
        return IntegrationFlow.from("reservations.commands.in")
            .handle(service, "reserve")
            .channel("reservations.receipts.out")
            .get();
    }
}
~~~

~~~text
Broker / HTTP / Gateway
  -> Validate principal, tenant, schema, business IDs
  -> reservations.commands.in
  -> JdbcReservationService.reserve (transaction + unique ledger)
  -> reservations.receipts.out
  -> Adapter / Aggregator / caller
~~~

Code trên giả định `JdbcReservationService` và các JDBC/transaction beans được cấu hình bởi Spring application, đồng thời inbound adapter tạo payload `ReserveStockCommand` đúng kiểu. **`QueueChannel` của demo là in-memory**, không thay broker bền vững hoặc chứng minh receipt đã được downstream xử lý.

### 9.1. Retry với cùng payload, không sinh command mới

Một endpoint có thể gắn `RequestHandlerRetryAdvice` để retry những lỗi transient của JDBC/transport theo policy. Nhưng:

- Lỗi `IDEMPOTENCY_CONFLICT`, schema sai hoặc thiếu quyền **không** nên retry.
- SQL timeout/connection reset có thể không biết transaction đã commit hay chưa; retry **cùng operation key** an toàn theo contract DB.
- Không sinh một `commandId` mới ở mỗi attempt.
- Dùng backoff và retry budget hữu hạn, tránh tất cả instances dồn tải khi DB yếu.

Cấu hình retry cụ thể cần kiểm tra theo Spring Integration/Spring Retry version; hãy test cả khi exception đến **sau commit trước response**.

### 9.2. Dùng metadata header cho observability, không làm nguồn correctness

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

ReserveStockCommand command = new ReserveStockCommand(
    "shop-a", "CMD-1001", "RUN-01",
    "ORD-981", "LINE-02", "BOOK-42", 2);

Message<ReserveStockCommand> message =
    MessageBuilder.withPayload(command)
        .setHeader("businessCorrelationId", "ORD-981")
        .setHeader("commandId", "CMD-1001")
        .setHeader("executionId", "RUN-01")
        .build();
~~~

Headers tiện cho Router/trace/correlation, nhưng **payload và identity đã được validate** mới là nguồn để tạo operation key. Khi qua Kafka/AMQP/JMS, header mapper có thể đổi kiểu/bỏ header; vì vậy cần contract kiểm thử round-trip.

## 10. IdempotentReceiverInterceptor và shared metadata store

Spring Integration có **Idempotent Receiver** hỗ trợ interceptor cho MessageHandler. Một triển khai thường dùng `IdempotentReceiverInterceptor` với một `MessageSelector`, chẳng hạn `MetadataStoreSelector`, để quyết định message đã gặp trước đó hay chưa.

Để nhiều instance cùng nhìn thấy state, cần một **shared backend** cung cấp atomic metadata operations, ví dụ một implementation `ConcurrentMetadataStore` trên Redis hoặc JDBC được cấu hình đúng. Một `SimpleMetadataStore` hoặc map của mỗi JVM **không** mang lại distributed dedup.

~~~text
Instance A ----\
                \      atomic claim / putIfAbsent
Instance B -------> Shared ConcurrentMetadataStore
                /              |
Instance C ----/               v
                          Key exists?
~~~

### 10.1. “Duplicate” có thể được đánh dấu chứ không bị drop

Trong Spring Integration, Idempotent Receiver interceptor có các semantics cấu hình về **đánh dấu duplicate trong header hoặc loại/định tuyến message**. Đừng chỉ gắn interceptor rồi giả định duplicate **luôn** bị bỏ qua và business handler không thể chạy.

Cần xác định và test:

- Key selector dùng **business identity nào**.
- Store là shared backend hay per-JVM.
- Duplicate được **mark**, **discard**, **throw** hay **route** theo cấu hình.
- Nếu duplicate là request–reply, caller có được **recorded result** hay chỉ timeout vì message bị drop.
- Nếu claim marker được ghi trước handler rồi handler thất bại, làm sao retry/khôi phục?
- Chính sách TTL và cleanup có bao phủ DLQ replay/delayed messages không?

### 10.2. Đánh dấu “đã thấy” trước business commit có nguy cơ mất tác vụ

Một `MetadataStoreSelector` có thể giúp chặn duplicate rất sớm, nhưng metadata claim được tạo **trước khi handler hoàn tất** thì việc receiver crash có thể để lại key mà không có business result. Nếu duplicate bị discard theo key đó, message được coi “đã xử lý” dù effect chưa xảy ra.

Do đó:

> **Dùng shared metadata selector như lớp sàng lọc/điều phối khi phù hợp; không thay thế transaction/idempotent operation ở nơi business effect được commit.**

Trong luồng yêu cầu dữ liệu đáng tin, thường nên để duplicate **đi vào service idempotent** để nhận kết quả đã lưu, hoặc thiết kế một state machine `IN_PROGRESS/COMPLETED` có expiry/reconciliation rõ.

### 10.3. Khi nào interceptor rất hữu ích?

- Chặn những thông báo **không có side effect** hoặc có thể bỏ duplicate theo business contract.
- Giảm work trùng trước handler tốn CPU, với điều kiện có đường retry/repair khi key đã claim mà handler lỗi.
- Kiểm tra message đã được xử lý tại cùng boundary mà shared metadata store hỗ trợ.
- Bổ sung observability cho duplicate hits, phát hiện producer/broker retries bất thường.

Không dùng một cờ interceptor để thay **idempotency ở payment gateway**, API giữ hàng hoặc DB sở hữu mutation.

## 11. Redis atomic claim, TTL, lease và fencing token

Một cách hay gặp:

~~~text
SET operation-key worker-A NX PX 30000
~~~

Lệnh Redis `SET NX PX` có thể giúp chỉ một worker giành claim cho một key còn tồn tại. Tuy nhiên, Redis key này là **lease/claim**, không phải bằng chứng operation đã commit.

### 11.1. Race khi lease hết hạn

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant R as Redis lease
    participant B as Worker B
    participant S as Storage/side-effect owner
    A->>R: Acquire lease, TTL=30s
    R-->>A: acquired
    Note over A: Pauses for 40s (GC/network)
    B->>R: Acquire after TTL expires
    R-->>B: acquired
    B->>S: Commit effect
    Note over A: Resumes after lease expiry
    A->>S: Also tries to commit effect
~~~

Worker A **không nhận được thông báo thần kỳ rằng lease đã hết hạn**. Nếu A tiếp tục gọi external API, hai workers có thể gây hai effects.

### 11.2. Fencing token để chặn worker cũ

Một kỹ thuật là cấp **fencing token tăng đơn điệu** cho mỗi lần chiếm quyền, và **đích thực hiện side effect** từ chối token cũ hơn token đã chấp nhận.

~~~text
A acquires token 41
A pauses
B acquires token 42
B commits at protected storage with token 42
A resumes; storage rejects token 41
~~~

Điều này chỉ an toàn nếu resource đích **thực sự kiểm tra fencing token một cách nguyên tử với mutation**. Nếu đích là API không biết token, việc có token trong Redis **chưa giúp chặn effect** của A.

### 11.3. Lease và processed result là hai loại state

| State | Ý nghĩa | TTL/retention |
| --- | --- | --- |
| `PROCESSING_LEASE` | Ai đang xử lý, còn quyền trong thời hạn nào | Ngắn, gia hạn/lease policy |
| `COMPLETED_RESULT` | Operation đã commit gì, outcome là gì | Theo retention/replay/compliance của nghiệp vụ |
| `FAILED_FINAL` | Operation đã có lỗi terminal nào | Theo contract |
| `UNKNOWN_RECONCILE` | Có thể đã commit ngoài nhưng chưa xác nhận | Không tự retry side effect mù quáng |

Không nên dùng **một Redis key TTL 30 giây** cho cả “worker ownership” lẫn “operation hoàn tất”. Sau 30 giây, key mất sẽ cho phép một duplicate cũ đi vào và tạo side effect mới.

## 12. Side effect ở external service: DB local không đủ

Giả sử `InventoryGateway` gọi HTTP tới kho ngoài. Worker lưu `operation_state=PROCESSING` ở DB nội bộ, gọi API, sau đó định lưu kết quả.

~~~text
A: INSERT local operation_state(PROCESSING)
A: HTTP reserve -> external inventory commits
A: network timeout / crash before local COMPLETED
B: redelivery -> sees PROCESSING/UNKNOWN
~~~

Nếu B chỉ dựa vào DB local mà gọi reserve mới, có thể giữ hàng hai lần. DB local **không cùng transaction** với kho ngoài.

### 12.1. Phương án ưu tiên: external API có idempotency key

~~~http
POST /inventory/reservations
Idempotency-Key: shop-a:CMD-1001:LINE-02:RESERVE_STOCK
Content-Type: application/json

{"sku":"BOOK-42","quantity":2}
~~~

Request/response này là **giao thức minh họa**; header, định dạng và semantics phụ thuộc API thực. Điều cần bảo đảm ở external service là:

1. Idempotency key được scope theo principal/tenant.
2. Cùng key và request phù hợp trả **same terminal result**.
3. Cùng key nhưng request khác trả conflict.
4. Việc ghi key/result **atomic với mutation**.
5. Key/result tồn tại ít nhất qua retry/replay window đã cam kết.

Khi caller timeout, nó có thể retry **cùng key**, không phát một key mới.

### 12.2. Nếu bên ngoài không hỗ trợ idempotency

Chọn một trong các chiến lược được nghiệp vụ cho phép:

- Tra cứu trạng thái giao dịch theo một request/reference ID có thể đối chiếu.
- Dùng một hệ thống reconciliation/settlement để xác nhận effect đã diễn ra.
- Tách yêu cầu thành prepare/confirm nếu external API hỗ trợ.
- Đưa vào manual review thay vì retry một khoản charge/giữ hàng có thể đã commit.

**Không thể** bảo đảm chỉ một effect cho external service bất kỳ chỉ bằng distributed lock ở hệ thống gọi. Cần khả năng phối hợp tại đích hoặc chấp nhận trường hợp outcome không chắc chắn có quy trình khắc phục.

### 12.3. “Exactly once” phải luôn nói rõ **ở đâu**

Phát biểu chính xác nên là:

> Với operation key K, database inventory thực hiện tối đa một mutation đã commit theo constraint và transaction X, còn message transport có thể giao lại nhiều lần.

Không nên nói chung “hệ thống xử lý exactly once” khi có thêm broker, DB, HTTP, nhiều DC và DLQ replay mà không xác định consistency boundary.

## 13. Outbox: business commit rồi publish event

Sau khi giữ hàng, service cần publish `StockReserved` cho Router/Aggregator downstream. Nếu commit tồn kho thành công nhưng publish fail, receiver sẽ có business effect nhưng không có event báo kết quả.

### 13.1. Transactional outbox trong cùng DB

~~~text
BEGIN TRANSACTION
  INSERT operation ledger (unique key)
  UPDATE inventory_stock
  MARK operation COMPLETED + recorded result
  INSERT outbox_event(eventId, operation key, payload)
COMMIT

Outbox publisher later:
  load unpublished event
  publish to broker
  retry if broker ACK lost
  mark published / reconcile
~~~

Nếu publisher crash sau broker nhận event nhưng trước đánh dấu published, event có thể được publish **lại**. Consumer của event cần idempotency theo **event ID hoặc business operation**, tùy contract. Outbox giúp **không mất thông báo**, nhưng không hứa broker nhận event đúng một lần.

### 13.2. Reply có thể được tạo lại

Trong trường hợp message redelivery sau business commit, receiver có thể:

- Trả `ReservationReceipt` đã lưu cho **executionId hiện tại**.
- Hoặc phát lại event/outcome idempotent theo một `eventId` ổn định.
- Không tạo thêm business mutation.

Nếu receipt mới mang execution ID mới, Aggregator có thể cần **gom reply vào group mới**, nhưng bản thân business effect vẫn như cũ. Một lần reprocess không đồng nghĩa một lần commit lại.

### 13.3. Đừng phát hai final outcomes

Nếu một Aggregator đã đóng group và duplicate result tới sau, group mới không được tự hình thành thành một “lần hoàn thành” khác. Dùng **closed-execution state/tombstone** và finalization CAS để chỉ một **final decision** cho mỗi execution, trừ khi business contract cho phép **versioned updates**.

## 14. Retry, redelivery và DLQ replay trên nhiều instance

Một command có thể được thử ở nhiều tầng:

~~~text
Producer publishes K
    |
Broker delivers to A
    |
A local retry: attempt #1,#2
    |
Broker redelivery to B
    |
B local retry: attempt #3,#4
    |
DLQ/replay to C later
    |
C attempts #5 ...
~~~

Không có gì bảo đảm local retry count, JMS delivery count, Kafka offset hoặc DLQ header **giữ nguyên qua mọi tầng**.

### 14.1. Identity bất biến phải đi qua transport

Các trường cần bảo toàn:

- `tenantId` đã xác minh.
- `commandId`/`operationId` bất biến.
- `lineId`/`subTaskId` nếu một command có nhiều effects.
- `operationType` để tách lệnh giữ và giải phóng.
- `schemaVersion` để đối chiếu đúng nội dung khi replay.
- `executionId` cho correlation của workflow.
- `originalEventId`/`replayOf` nếu cần điều tra.

Message envelope ID, timestamp xử lý, trace span, delivery attempt có thể thay đổi và chỉ dùng cho **diagnostic**.

### 14.2. Redelivery có thể chạy song song

Dù cùng một queue dùng consumer group, sự cố mạng, visibility timeout, rebalance hoặc retry topic có thể khiến cùng business operation **được thực hiện song song** trên hai workers trong những mô hình cụ thể.

Không dựa vào giả định “broker chỉ giao cho một consumer tại một thời điểm” làm bảo đảm correctness cuối cùng. Atomic ledger tại business owner phải chịu được contention.

### 14.3. DLQ replay giữ đúng ý định nghiệp vụ

Một replay của **cùng command** giữ nguyên operation key. Một **command mới hợp lệ** phải có identity mới do nghiệp vụ phát hành và được audit/authorize rõ. Nếu operator chỉ đổi `commandId` để “chạy lại cho qua dedup”, side effect có thể bị nhân đôi.

Nếu DLQ giữ message phiên bản cũ, cần versioned decoder và test migration trước khi replay, không tự diễn giải payload theo contract mới khác nghĩa.

## 15. Thời hạn lưu khóa idempotency và hậu quả của TTL ngắn

Giả sử:

~~~text
T0         CMD-1001 committed
T0 + 1 day Broker still has delayed retry
T0 + 2 day Ledger row deleted by short TTL
T0 + 3 day DLQ replay CMD-1001
~~~

Nếu không còn bằng chứng operation đã commit, receiver có thể xem `CMD-1001` như command mới và giữ hàng lần nữa.

### 15.1. Retention phải dựa trên thời gian replay lớn nhất

Tính tổng hoặc đánh giá:

- Thời gian message có thể nằm trên broker.
- Delay của các retry topics/queues.
- Thời gian DLQ được phép replay thủ công.
- Thời gian producer/partner có thể resend.
- Quy định về historical reconciliation/audit.
- TTL của external API idempotency key.
- Thời gian giữ tombstone khi đã xóa chi tiết kết quả.

Một TTL đồng nhất 24 giờ có thể không đủ nếu nghiệp vụ cho phép xử lý lại trong 30 ngày.

### 15.2. Xóa dữ liệu nhạy cảm nhưng vẫn cần chống trùng

Có thể cần xóa payload/PII vì quy định lưu trữ nhưng vẫn giữ **một tombstone tối thiểu** với opaque operation identity và trạng thái `COMPLETED`, nếu hợp pháp và phù hợp chính sách. Không tự giữ khóa chứa PII thô lâu hơn mức cần thiết. Phải quyết định cùng bộ phận security/compliance.

### 15.3. Key reuse

Nếu producer tái sử dụng `commandId` sau một thời gian, đó là **một lệnh mới hay lỗi protocol**? Contract tốt nên không tái sử dụng ID trong cửa sổ retention và có namespace/version rõ. Nếu reuse là hợp lệ, cần một epoch/operation version được quản lý thay vì âm thầm xóa ledger và hy vọng không redelivery cũ.

## 16. Kiểm thử unit: mô phỏng hai replica bằng một shared ledger

Trước khi dùng PostgreSQL thật, mô hình trong JVM cho phép kiểm tra nguyên tắc **chung một kho state**. Đây là fake chỉ dùng trong unit test, không thay kiểm thử DB multi-process.

### 16.1. Shared fake operation ledger

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

record Key(String tenant, String commandId, String lineId, String op) {}

record FakeStoredResult(String sku, int quantity, String outcome) {}

final class SharedFakeInventory {
    private final ConcurrentMap<Key, FakeStoredResult> completed =
        new ConcurrentHashMap<>();

    private final AtomicInteger commits = new AtomicInteger();

    ReservationReceipt reserve(ReserveStockCommand command) {
        Key key = new Key(
            command.tenantId(), command.commandId(),
            command.lineId(), "RESERVE_STOCK");

        FakeStoredResult result = completed.compute(key, (k, old) -> {
            if (old != null) {
                if (!old.sku().equals(command.sku())
                        || old.quantity() != command.quantity()) {
                    throw new IdempotencyConflict();
                }
                return old;
            }

            commits.incrementAndGet();
            return new FakeStoredResult(
                command.sku(), command.quantity(), "RESERVED");
        });

        return new ReservationReceipt(
            command.executionId(),
            command.orderId(),
            command.lineId(),
            result.outcome());
    }

    int committedOperations() {
        return commits.get();
    }
}
~~~

`ConcurrentHashMap.compute` làm thao tác với **một key trong cùng một JVM** có tính nguyên tử phù hợp cho fake. Hai Spring application processes khác nhau **không** dùng chung object này; production vẫn cần database/remote backend có guarantees đúng.

### 16.2. JUnit 5 concurrent test

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.Test;

class SharedFakeInventoryTest {

    private static ReserveStockCommand command(String execution) {
        return new ReserveStockCommand(
            "shop-a", "CMD-1001", execution,
            "ORD-981", "LINE-02", "BOOK-42", 2);
    }

    @Test
    void concurrentCallsForSameKeyHaveOneFakeCommit()
            throws Exception {
        SharedFakeInventory shared = new SharedFakeInventory();
        int workers = 20;
        CountDownLatch start = new CountDownLatch(1);

        ExecutorService executor = Executors.newFixedThreadPool(workers);
        try {
            List<Callable<ReservationReceipt>> jobs = new ArrayList<>();
            for (int i = 0; i < workers; i++) {
                String execution = "RUN-" + i;
                jobs.add(() -> {
                    start.await();
                    return shared.reserve(command(execution));
                });
            }

            List<Future<ReservationReceipt>> futures = new ArrayList<>();
            for (Callable<ReservationReceipt> job : jobs) {
                futures.add(executor.submit(job));
            }
            start.countDown();

            for (Future<ReservationReceipt> future : futures) {
                assertEquals("RESERVED", future.get().outcomeCode());
            }
            assertEquals(1, shared.committedOperations());
        } finally {
            executor.shutdownNow();
        }
    }

    @Test
    void sameKeyDifferentRequestIsAConflict() {
        SharedFakeInventory shared = new SharedFakeInventory();
        shared.reserve(command("RUN-1"));

        ReserveStockCommand changed = new ReserveStockCommand(
            "shop-a", "CMD-1001", "RUN-2",
            "ORD-981", "LINE-02", "BOOK-42", 20);

        assertThrows(IdempotencyConflict.class,
            () -> shared.reserve(changed));

        assertEquals(1, shared.committedOperations());
    }

    @Test
    void sameCommandInDifferentTenantsIsNotSameKey() {
        SharedFakeInventory shared = new SharedFakeInventory();
        shared.reserve(command("RUN-1"));
        shared.reserve(new ReserveStockCommand(
            "shop-b", "CMD-1001", "RUN-2",
            "ORD-981", "LINE-02", "BOOK-42", 2));

        assertEquals(2, shared.committedOperations());
    }
}
~~~

**Giới hạn:** test chứng minh fake map dùng chung chống tranh chấp giữa 20 threads **trong một process**. Nó không chứng minh isolation của PostgreSQL, network partition, transaction rollback, crash/restart hay tính nguyên tử với inventory database. Đó là phạm vi của integration tests.

## 17. Integration tests: hai Spring instances, một PostgreSQL

Đây là **bộ tình huống bắt buộc** nếu chuẩn bị triển khai nhiều replica. Test phải sử dụng **hai service beans/application contexts hoặc hai JVM/containers** kết nối **cùng một PostgreSQL**, thay vì hai maps trong RAM.

### 17.1. Race test 50 requests cùng một operation

~~~text
Given:
  inventory_stock(shop-a, BOOK-42).available = 100
  reservation_operation = empty
  2 independent application instances -> same PostgreSQL
  Same validated ReserveStockCommand sent 50 times concurrently

When:
  Start requests together using a barrier
  Wait for all requests or bounded errors/retries

Then:
  Exactly one ledger row for operation key
  Row state=COMPLETED, outcome_code=RESERVED
  Inventory available = 98, not 0 or -2
  All successful replies report same business outcome
  No cross-tenant data leak
~~~

### 17.2. Commit xong nhưng mất ACK

~~~text
1. Send command to A.
2. Allow DB transaction to COMMIT.
3. Simulate lost response / consumer crash before ACK.
4. Broker redelivers same command to B.
5. Assert stock is decremented only once.
6. Assert B reads existing result and can ACK safely.
~~~

Để test chính xác, cần **failure injection ở ranh giới sau commit**. Đừng chỉ ném exception **trước** repository commit, vì test đó không chứng minh cửa sổ lỗi khó nhất.

### 17.3. Crash trước commit

~~~text
1. A starts DB transaction and reserves operation row.
2. A fails before COMMIT; DB rolls back.
3. B receives same command.
4. B can perform the transaction.
5. Exactly one committed inventory mutation and ledger result.
~~~

### 17.4. Concurrency ở nhiều operation khác nhau

Kiểm tra `CMD-1001` và `CMD-1002` là **hai thao tác hợp lệ**, không bị khóa lẫn toàn hệ thống. Nếu chúng cùng cập nhật một SKU, database phải đảm bảo stock không âm qua conditional update. Một thiết kế chỉ lock toàn bộ table có thể đúng một số invariants nhưng throughput kém; đo **lock contention** và latency thực tế.

### 17.5. Contract conflict

Cùng operation key nhưng:

~~~text
Original: quantity=2, sku=BOOK-42
Replay:   quantity=20, sku=BOOK-42
~~~

Assert `IDEMPOTENCY_CONFLICT`, không commit thêm và không trả outcome cũ như thể request mới hợp lệ.

### 17.6. Restart/multi-instance

Sau khi A commit rồi **kill/restart** process, B vẫn phải lấy được result từ PostgreSQL. Nếu test chỉ restart một bean và vẫn giữ same Java fake ledger, kết quả **không có ý nghĩa** cho durability.

## 18. Kiểm thử Spring Integration flow và errors

Unit test của `JdbcReservationService` chưa chứng minh DSL routing đúng. Với `IdempotentReservationFlowConfiguration`, cần:

- Gửi message vào `reservations.commands.in`.
- Nhận đúng một `ReservationReceipt` ở `reservations.receipts.out` cho mỗi request demo.
- Assert `executionId`/`orderId`/`lineId` đúng.
- Gửi lại cùng command: handler có thể trả **một receipt mới cho request thứ hai**, nhưng DB effect vẫn chỉ một.
- Trường hợp conflicting duplicate: không có receipt giả `RESERVED`; lỗi đi qua đúng error/rejection contract.
- Nếu dùng `IdempotentReceiverInterceptor`, test **cấu hình duplicate handling thực** (mark/discard/throw) thay vì chỉ đếm database updates.
- Nếu chuyển sang Gateway request–reply, duplicate không bị drop khiến caller chờ timeout; nó cần nhận cached outcome hoặc một trạng thái rõ.

### 18.1. Retry được gắn ở đâu?

Trong Spring Integration, advice có thể chạy tại **message handler**. Điều này khác với retry của inbound adapter, consumer container hay outbox publisher. Test tổng số attempts ở các tầng để không rơi vào retry storm:

~~~text
2 broker deliveries
× 3 handler attempts per delivery
= up to 6 attempts for the same business key
~~~

Phép nhân là ví dụ minh họa, không phải default của framework. Dù có sáu attempts, chỉ **một business effect** được phép commit cho operation key.

### 18.2. Error channel không đồng nghĩa retry/dedup

`ErrorMessage` có thể xuất hiện theo cấu hình poller/executor/adapter. Nhưng gửi exception tới error channel **không tự xóa claim key** hoặc rollback external operation. Phải đặt error handling đúng theo state:

- `INVALID_REQUEST`/`UNAUTHORIZED`: terminal rejection.
- `IDEMPOTENCY_CONFLICT`: reject/quarantine + audit.
- `DATABASE_TEMPORARY_UNAVAILABLE`: retry hữu hạn/backoff.
- `ALREADY_COMPLETED`: trả persisted outcome.
- `IN_PROGRESS`: defer/wait/retry later, không chạy đồng thời side effect.
- `EXTERNAL_OUTCOME_UNKNOWN`: reconcile, không tự charge/commit lại với key mới.

## 19. Ma trận kiểm thử đầy đủ

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Một message mới | One operation row + one business effect |
| Local retry sau lỗi transient | Stable key, không commit lặp |
| A commit, ACK mất, B redeliver | B trả cached result, không trừ kho thêm |
| A rollback trước commit | B có thể thực hiện operation |
| Hai replicas gọi cùng key đồng thời | Unique row và một mutation |
| Hai replicas gọi hai keys khác | Hai commands hợp lệ được xử lý |
| Cùng key, quantity khác | Conflict và không cấp kết quả nhầm |
| Cùng commandId ở tenant khác | Không chặn nhầm hoặc lộ data |
| Restart cả hai replicas | Durable ledger còn hiệu lực |
| DB unavailable | Không ACK như thành công khi chưa chắc xử lý |
| DB deadlock/serialization failure | Retry cùng key, bounded budget |
| Broker duplicate publish | Không double effect |
| DLQ replay sau nhiều ngày | Retention đủ hoặc có reconciliation |
| Redis lease expires, worker A resumes | Fencing ở effect owner hoặc safe fallback |
| Redis/store bị network partition | Không tuyên bố exactly once thiếu guarantees |
| External API committed, local response lost | Target idempotency/status lookup |
| Outbox publish rồi ACK mất | Duplicate event downstream idempotent |
| Aggregator nhận duplicate reply | Không đếm thành hai unique item results |
| Late reply sau group closed | Không tạo final outcome thứ hai |
| Message headers mất qua broker | Stable key/correlation còn trong hợp đồng |
| Schema version upgrade | Command cũ được diễn giải đúng khi replay |
| TTL ledger hết quá sớm | Test phát hiện nguy cơ effect lặp |
| Request key bị giả mạo | AuthN/AuthZ tenant và conflict detection |
| 0 replies từ downstream | Deadline watcher xử lý, không đợi group không tồn tại |
| Load test 10k ops/s | Lock contention, queue depth, latency và DB hot keys |

**Đừng chỉ assert “API trả 200” hoặc “output có receipt”.** Chứng minh bằng **dữ liệu đã commit** và các hành vi không được phép như inventory decrement lần hai.

## 20. Observability cho idempotency nhiều instance

Các metric và trace nên tách **số lần giao**, **số lần handler chạy** và **số business operations thực sự commit**.

| Tín hiệu | Mục đích |
| --- | --- |
| `messages_received_total` | Đếm inbound deliveries/republishes |
| `handler_attempts_total` | Thấy local retries |
| `idempotency_claim_new_total` | Operation mới |
| `idempotency_hit_completed_total` | Duplicate được trả kết quả đã lưu |
| `idempotency_conflict_total` | Cùng key nhưng dữ liệu khác |
| `idempotency_inflight_total` | Operations còn xử lý/chờ |
| `business_effect_committed_total` | Effects thực sự được commit |
| `db_unique_conflict_total` | Tranh chấp concurrent |
| `db_transaction_retry_total` | Deadlock/serialization/network retries |
| `outbox_pending_age` | Event đã commit nhưng chưa phát |
| `external_outcome_unknown_total` | Thao tác phải reconciliation |
| `late_reply_total` | Replies sau execution đóng |
| `dlq_replay_total` | Phục hồi từ DLQ |
| `idempotency_ledger_age` | Giám sát retention/cleanup |

Một log cho một duplicate:

~~~json
{
  "event": "idempotency_reused",
  "tenant": "shop-a",
  "commandId": "CMD-1001",
  "lineId": "LINE-02",
  "operationType": "RESERVE_STOCK",
  "executionId": "RUN-02",
  "result": "RESERVED",
  "source": "broker_redelivery"
}
~~~

**Không** dùng `commandId`, `executionId`, `orderId` hoặc tenant tự do làm tag time-series metric cardinality cao. Với logs/traces, cần masking, phân quyền, retention phù hợp, không log dữ liệu thanh toán/PII hoặc token.

### 20.1. Cảnh báo vận hành

- Duplicate hit rate tăng bất thường → producer retry loop hoặc broker ACK lỗi.
- Operations `IN_PROGRESS` quá lâu → lease/recovery bị kẹt.
- Lock wait tăng → hot key, DB contention.
- Outbox age tăng → publisher/broker gặp vấn đề.
- Same key conflicting payload → lỗi producer contract hoặc hoạt động đáng ngờ.
- Hệ thống đích có nhiều outcome UNKNOWN → reconciliation cần ưu tiên.
- Số `business_effect_committed_total` vượt số unique operation keys → có nguy cơ duplicate effect.

### 20.2. Quan sát một request–reply chain

~~~text
HTTP/Message Gateway
  -> validated command
  -> idempotent handler (new/reused/conflict)
  -> DB commit / existing outcome
  -> reply with current executionId
  -> Aggregator if fan-in
  -> finalizer once per execution
~~~

Một duplicate receipt có thể là điều đúng nếu caller thật sự gửi lại request; điều cần tránh là **business effect mới** hoặc **final business result thứ hai không được version**.

## 21. Những anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách thay |
| --- | --- | --- |
| Mỗi instance có `HashSet` xử lý | Instance B không biết instance A đã commit | Shared durable ledger |
| `containsKey` rồi gọi external API | Race giữa hai workers | Atomic claim tại owner hoặc backend idempotent |
| Redis lock TTL là giải pháp exactly-once | Lease hết, stale worker vẫn chạy | Fencing/idempotent resource |
| Đánh dấu processed trước commit rồi drop duplicates | Crash có thể làm mất tác vụ | Same-transaction commit hoặc recoverable state |
| Đánh dấu processed sau external commit | Crash có thể double effect | External idempotency/reconciliation |
| Dùng `MessageHeaders.ID` làm business key | Envelope đổi khi redelivery | Stable operation ID |
| Dùng `orderId` duy nhất làm key | Các line/command hợp lệ bị drop | Scope theo line + command + operation |
| Cùng key nhưng quantity khác vẫn trả cached success | Che request conflict nghiêm trọng | Compare immutable request fields |
| Retry với command ID mới | Biến retry thành thao tác mới | Preserve key across attempts |
| `@Transactional` trên một HTTP call ngoài | DB rollback không rollback API | Target idempotency, saga/reconcile |
| Rely on Kafka exactly-once cho payment HTTP | Sai consistency boundary | Idempotency tại payment owner |
| Xóa ledger quá sớm | DLQ replay tạo effect mới | Retention theo replay window |
| Không lưu terminal failure | Redelivery làm kết quả đổi vô tình | Persist outcome theo contract |
| Drop duplicate mà không reply | Gateway chờ timeout | Return stored result or clear status |
| Outbox không có idempotent subscriber | Publisher retry phát event lặp | Stable event ID/dedup downstream |
| Group đã complete nhưng duplicate reply tạo group mới | Phát final output lần hai | Closed execution registry |
| Lock toàn hệ thống cho mọi operations | Throughput và latency kém | Per-key uniqueness/row locks |
| Dùng test một JVM để xác nhận multi-node | Bỏ sót distributed races/restart | 2 process/contexts cùng database |
| Không kiểm tra tenant principal | Cross-tenant result leak | AuthN/AuthZ trước dedup |
| Retry vô hạn khi DB quá tải | Retry storm | Bounded budget, jitter, monitoring |

## 22. Checklist trước triển khai production

- [ ] Khóa idempotency mô tả chính xác **một business operation**, không phải một delivery.
- [ ] Scope key theo tenant/principal/command/line/operation type khi cần.
- [ ] Identity được phát một lần và giữ nguyên qua retries, broker redelivery và DLQ replay.
- [ ] Cùng key với payload khác bị phát hiện và từ chối.
- [ ] State store dùng chung giữa mọi instance, có atomic uniqueness/compare-and-set phù hợp.
- [ ] Side effect và ledger cùng consistency boundary hoặc external API có idempotency/reconciliation.
- [ ] Không nhầm shared metadata selector với transaction nghiệp vụ.
- [ ] Redis lease có xử lý stale worker/fencing nếu được dùng làm quyền thao tác.
- [ ] Có phân biệt `IN_PROGRESS`, `COMPLETED`, `FAILED_FINAL` và `UNKNOWN`.
- [ ] Crash trước và sau commit có kết quả phục hồi đã được kiểm thử.
- [ ] Duplicate trả persisted result theo contract, không tự động drop khiến caller timeout.
- [ ] Transaction proxy/DB isolation/unique constraint được kiểm tra trên version đang dùng.
- [ ] Outbox/inbox và broker ACK order được thiết kế cho redelivery.
- [ ] DLQ replay giữ operation key, policy/schema version, có authorization.
- [ ] Retention ledger đủ dài so với cửa sổ delayed delivery/replay lớn nhất.
- [ ] Aggregator correlation theo execution và dedup theo item; có late-reply path.
- [ ] Retry budget hữu hạn, phân loại lỗi và có backoff/jitter.
- [ ] Có integration tests với **hai instance** trên cùng database, không chỉ fake in-memory.
- [ ] Metrics phân biệt delivery, attempts, dedup hits và committed effects.
- [ ] Security: không rò cached result cross-tenant, không để ID nhạy cảm trong metric tags.

## 23. Bài tập vận dụng

Một nền tảng bán vé chạy **5 replicas** của dịch vụ `TicketReservation`. Kafka gửi `ReserveSeatCommand` gồm:

~~~json
{
  "tenantId": "event-a",
  "commandId": "RSV-2026-55",
  "eventId": "EVT-123",
  "seatId": "A-07",
  "accountId": "ACC-88",
  "executionId": "RUN-1"
}
~~~

Nhiều bản cùng command có thể được giao qua retry topics và DLQ. Khi giữ ghế thành công, hệ thống phát `SeatReserved` để một Aggregator tổng hợp cùng kết quả thanh toán.

**Yêu cầu:**

1. Thiết kế idempotency key, chỉ ra tại sao `seatId` một mình không đủ để phân biệt retry và thao tác mới.
2. Vẽ race giữa replica A/B cùng nhận `RSV-2026-55`. Chọn consistency boundary để chỉ một reservation được commit.
3. Viết PostgreSQL schema có unique operation key và ràng buộc một ghế không thể được giữ cho hai chủ thể theo business lifecycle (cần constraint/schema riêng, **không chỉ idempotency key**).
4. Viết service Java `@Transactional` với atomic operation insert và update ghế, persist kết quả.
5. Mô tả xử lý cùng key nhưng khác `accountId` hoặc `seatId`.
6. Mô phỏng A commit seat rồi crash trước Kafka offset commit; chứng minh B redelivery trả kết quả cũ.
7. Nếu Payment Gateway bên ngoài bị timeout sau charge, giải thích vì sao DB ticket local không đủ bảo đảm charge một lần. Đề xuất target idempotency/reconciliation.
8. Thiết kế outbox cho `SeatReserved` và idempotent subscriber ở Aggregator.
9. Khi DLQ replay sau 15 ngày, ledger TTL nên được quyết định thế nào?
10. Thiết kế integration test dùng **ít nhất hai Spring processes/contexts** cùng PostgreSQL, đồng thời 100 copies một command.
11. Nếu dùng Redis lease để giảm contention, bổ sung fencing hoặc giải thích vì sao vẫn cần DB constraints.
12. Chỉ rõ metrics/alerts cho duplicate, conflict, retained operations, lock wait và replay.

**Gợi ý:** dùng business operation ID ổn định, database unique index + transaction trên tài nguyên ghế, outbox để phát event và **các ràng buộc nghiệp vụ của ghế độc lập với dedup**. Hãy phân biệt “mỗi command giữ ghế tối đa một lần” với “một ghế không được bán cho hai người”: đây là **hai invariants khác nhau**.

## 24. Tổng kết

**Idempotency qua nhiều instance** không đến từ việc kiểm tra một ID trong bộ nhớ cục bộ. Nó đòi hỏi **nhận diện business operation ổn định, một bộ phân xử nguyên tử dùng chung và bảo vệ chính nơi side effect được commit**. Khi multiple replicas, retries, broker redelivery, outbox và DLQ replay cùng tồn tại, số lần handler chạy có thể lớn hơn một nhưng **business mutation phải có contract rõ về at-most-once**.

Trong Spring Integration, `IdempotentReceiverInterceptor` và `ConcurrentMetadataStore` hỗ trợ nhận diện/điều phối duplicates, nhưng không tự làm một external API hoặc database mutation trở thành transaction chung. Với dữ liệu cùng DB, hãy ưu tiên **unique operation key, atomic transaction và persisted outcome**; với external services, cần **idempotency key ở đích hoặc reconciliation**, lease/fencing khi phù hợp. Kết hợp Router, Filter, Transformer, Gateway, retry/error channel, correlation, Aggregator, inbox/outbox, durable store và kiểm thử multi-instance để bảo đảm **retry không tạo thao tác mới, kết quả không lặp sai và hệ thống còn đúng sau crash/restart**.

**Tài liệu tham khảo:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Idempotent Receiver, Correlation Identifier, Guaranteed Delivery, Message Store); Spring Integration Reference về Idempotent Receiver, Message Selector, Metadata Stores, Java DSL, Message Channels, Error Handling và Testing; Spring Framework về Transaction Management và JDBC; PostgreSQL documentation về transactions, `ON CONFLICT` và row-level locking; tài liệu Java SE về records và concurrency.

