# Chống trùng đồng thời giữa nhiều consumer hoặc bản sao ứng dụng

Một ứng dụng Spring Boot tích hợp HTTP API, cơ sở dữ liệu và message broker thường được triển khai nhiều replica để tăng thông lượng. Nhưng khi broker giao lại message, consumer bị rebalance, HTTP client retry hoặc hai pod cùng nhận một lệnh, **nhiều tiến trình có thể cố thực hiện cùng một tác động nghiệp vụ tại cùng thời điểm**.

Ví dụ: sự kiện `OrderStatusChanged` có `eventId=E42` được gửi tới consumer cập nhật trạng thái đơn hàng. Pod A commit thay đổi vào database nhưng chết trước khi gửi acknowledgment (ack). Broker giao lại message cho pod B. Nếu logic không chống trùng, B có thể cập nhật lại, phát event thêm lần nữa hoặc gọi API thanh toán/hóa đơn lần hai.

Trong phạm vi tích hợp hệ thống của Spring Boot, ta cần phối hợp **khóa nhận diện ổn định, transaction, ràng buộc dữ liệu, ack/retry, idempotency và quan sát**. Bài này chỉ rõ cơ chế bảo vệ khi nhiều consumer hoặc replica chạy đồng thời, đặc biệt là những giới hạn của khóa Redis hay bảo đảm giao message từ broker.

## 1. Phân biệt duplicate message và duplicate effect

| Hiện tượng | Nguyên nhân điển hình | Rủi ro |
| --- | --- | --- |
| Broker redelivery | Consumer commit DB nhưng ack mất, hoặc broker rebalance | Xử lý cùng event thêm lần nữa |
| Consumer chạy song song | Nhiều subscription/group, deployment hoặc replay | Hai worker cùng áp dụng một sự kiện |
| HTTP retry | Client không biết request trước đã hoàn tất chưa | Lệnh tạo đơn hoặc charge tiền bị lặp |
| Publisher retry | Broker đã nhận message nhưng producer mất ack | Cùng ý nghĩa nghiệp vụ xuất hiện nhiều message |
| Check-then-act race | Hai pod cùng đọc “chưa xử lý” rồi cùng ghi | Cả hai vượt qua kiểm tra |
| Backfill/replay | Đọc lại sự kiện lịch sử hoặc publish sang topic mới | Event cũ ghi đè trạng thái mới |

**Trùng message không đồng nghĩa trùng hiệu ứng.** Một event được giao ba lần nhưng handler chỉ ghi một lần là xử lý trùng an toàn. Ngược lại, hai message có `eventId` khác nhau vẫn có thể đại diện cho **cùng một lệnh thanh toán** và tạo tác động trùng nếu chỉ dedupe theo event ID.

### 1.1. Hiểu đúng delivery semantics

- `At-most-once` có thể bỏ mất message khi lỗi; không thể dùng làm bảo đảm xử lý cho mọi nghiệp vụ.
- `At-least-once` cho phép nhận lại message khi hệ thống không chắc việc xử lý đã hoàn tất; consumer cần idempotent.
- `Exactly-once` chỉ có ý nghĩa trong phạm vi được định nghĩa. Ví dụ transaction của một broker có thể bao trùm các thao tác trong broker đó, nhưng không mặc nhiên bao trùm cập nhật PostgreSQL, gọi REST API, gửi email hoặc tác vụ ở hệ thống khác.

Mục tiêu thực tế của nhiều luồng HTTP → DB → broker → consumer là **at-least-once delivery kết hợp idempotent effects**. Phải xác định rõ bảo đảm áp dụng cho hệ thống nào, bước nào và nguồn sự thật nào.

## 2. Vì sao “kiểm tra rồi ghi” không an toàn?

Một cách triển khai dễ mắc lỗi:

~~~java
if (!processedEventRepository.existsByEventId(event.eventId())) {
    applyBusinessUpdate(event);
    processedEventRepository.save(new ProcessedEvent(event.eventId()));
}
~~~

Nếu hai transaction đọc `exists=false` cùng lúc, cả hai đều có thể gọi `applyBusinessUpdate`. Việc đặt `@Transactional` quanh đoạn mã không tự biến chuỗi SELECT → UPDATE thành thao tác nguyên tử với isolation mặc định.

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant B as Consumer B
    participant D as Database
    A->>D: SELECT marker(E42) → chưa có
    B->>D: SELECT marker(E42) → chưa có
    A->>D: Business UPDATE
    B->>D: Business UPDATE lần nữa
    A->>D: INSERT marker(E42)
    B->>D: INSERT marker(E42) → unique error?
    Note over A,B: Hiệu ứng có thể đã xảy ra trước khi phát hiện trùng
~~~

Ngay cả khi bảng marker có unique constraint, nó không hoàn tác được các **HTTP side effects** đã thực hiện bên ngoài transaction. Giải pháp phải đặt quyền xử lý và thay đổi bền vững vào đúng **ranh giới nguyên tử**, chứ không dừng ở một phép kiểm tra trong application memory.

## 3. Chọn khóa idempotency theo nghiệp vụ

Một khóa chống trùng nên ổn định qua mọi retry và chứa đủ thông tin về phạm vi xử lý:

~~~text
Deduplication identity
  = security/tenant scope
  + logical handler hoặc operation
  + stable event ID / command ID
~~~

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| `tenant_id` | `shop-a` | Tách biệt cùng ID ở hai tenant |
| `handler_name` | `order-projection-v1` | Mỗi handler độc lập có quyền xử lý cùng event |
| `event_id` | UUID do producer tạo một lần | Nhận ra duplicate qua redelivery/replay |
| Business operation ID | `payment-capture-123` | Chống cùng thao tác nghiệp vụ có hai event ID |
| Aggregate version | `order-42, version 10` | Xác định thứ tự/cập nhật hợp lệ |

Không lấy tên pod, thời điểm nhận, Kafka offset hay Pulsar message ID làm **khóa nghiệp vụ chung** nếu message có thể được publish lại. Các ID hạ tầng có thể đổi dù tác động kinh doanh không đổi.

Ví dụ client retry `capture-payment-123` khiến producer tạo `E1` và `E2` là hai event khác ID. Dedupe theo `eventId` sẽ cho cả hai đi qua. Hệ thống thanh toán cần thêm ràng buộc riêng như unique `(tenant_id, payment_command_id)` hoặc `Idempotency-Key` do cổng thanh toán xử lý.

Nếu upstream chưa cấp event ID ổn định, cần thiết kế định danh ở ranh giới producer hoặc dùng khóa nghiệp vụ đã được chuẩn hóa, chẳng hạn `tenantId + orderId + transitionVersion`. Không mặc định hash toàn payload làm khóa: timestamp, thứ tự trường và serialization có thể đổi giữa hai lần gửi.

Nếu cùng `eventId` nhưng nội dung khác nhau, đó là **xung đột hợp đồng dữ liệu**. Khi có rủi ro này, lưu thêm `payload_hash` đã chuẩn hóa và cảnh báo nếu duplicate có hash khác; đừng âm thầm bỏ qua payload có thể gây sai nghiệp vụ.

## 4. Mẫu nền tảng: transactional inbox + unique constraint

Khi receipt chống trùng và thay đổi nghiệp vụ cùng nằm trong **một database có transaction**, dùng quy trình:

1. Bắt đầu DB transaction.
2. `INSERT` vào bảng `consumer_inbox` có `PRIMARY KEY (tenant_id, handler_name, event_id)`.
3. **Chỉ** nếu insert mới thành công, cập nhật business state và ghi outbox record cần thiết.
4. Commit tất cả trong **cùng DB transaction**.
5. **Sau commit** mới ack message ở broker.

~~~mermaid
sequenceDiagram
    participant A as Consumer A
    participant B as Consumer B
    participant D as Shared database
    participant M as Broker
    M-->>A: Event E42
    M-->>B: Event E42 (duplicate)
    A->>D: BEGIN; INSERT inbox(E42)
    B->>D: BEGIN; INSERT inbox(E42)
    Note over D: Unique index điều phối concurrency
    A->>D: UPDATE business; INSERT outbox
    A->>D: COMMIT
    D-->>B: Duplicate key → không xử lý business
    B->>D: COMMIT hoặc rollback no-op
    A->>M: Ack sau commit
    B->>M: Ack duplicate đã xác nhận
~~~

Hai worker cạnh tranh cùng unique key phải được database phân xử. Nếu transaction A **commit**, B sẽ không ghi thêm một business effect; nếu A **rollback**, marker cũng rollback, nên B có thể được quyền xử lý. Không cần và không nên dựa vào `existsBy...` trước bước insert.

### 4.1. PostgreSQL schema minh họa

~~~sql
CREATE TABLE consumer_inbox (
    tenant_id      varchar(80)  NOT NULL,
    handler_name   varchar(120) NOT NULL,
    event_id       uuid         NOT NULL,
    received_at    timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, handler_name, event_id)
);

CREATE TABLE order_projection (
    tenant_id      varchar(80)  NOT NULL,
    order_id       uuid         NOT NULL,
    state          varchar(40)  NOT NULL,
    source_version bigint       NOT NULL,
    updated_at     timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE integration_outbox (
    outbox_id      uuid         PRIMARY KEY,
    tenant_id      varchar(80)  NOT NULL,
    event_id       uuid         NOT NULL,
    event_type     varchar(120) NOT NULL,
    payload        jsonb        NOT NULL,
    published_at   timestamptz,
    UNIQUE (tenant_id, event_id, event_type)
);
~~~

`consumer_inbox` là receipt, `order_projection` là dữ liệu đích. `integration_outbox` chỉ cần khi handler phải phát lệnh hoặc event tiếp theo. Schema dùng PostgreSQL; các DB khác có cú pháp upsert, khóa và lỗi unique khác nhau. Dữ liệu đã được đánh dấu xử lý có thể cần giữ đủ lâu cho phép redelivery hoặc replay.

### 4.2. Spring Boot: cùng transaction và insert-first

Ví dụ dùng `JdbcTemplate`, `TransactionTemplate` trên cùng datasource PostgreSQL. Giả định `OrderStatusEvent` là record của ứng dụng chứa `eventId`, `tenantId`, `orderId`, `version` và `state`.

~~~java
import java.util.Objects;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class OrderProjectionHandler {
    private static final String HANDLER = "order-projection-v1";

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;

    public OrderProjectionHandler(JdbcTemplate jdbc,
                                  TransactionTemplate transactions) {
        this.jdbc = jdbc;
        this.transactions = transactions;
    }

    public Result handle(OrderStatusEvent event) {
        validate(event); // Kiểm tra schema, tenant, ID, version, state.

        return Objects.requireNonNull(transactions.execute(tx -> {
            int claimed = jdbc.update("""
                INSERT INTO consumer_inbox
                    (tenant_id, handler_name, event_id)
                VALUES (?, ?, ?)
                ON CONFLICT (tenant_id, handler_name, event_id)
                DO NOTHING
                """,
                event.tenantId(), HANDLER, event.eventId());

            if (claimed == 0) {
                return Result.DUPLICATE;
            }

            jdbc.update("""
                INSERT INTO order_projection
                    (tenant_id, order_id, state, source_version)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (tenant_id, order_id)
                DO UPDATE SET
                    state = EXCLUDED.state,
                    source_version = EXCLUDED.source_version,
                    updated_at = now()
                WHERE order_projection.source_version
                      < EXCLUDED.source_version
                """,
                event.tenantId(), event.orderId(),
                event.state(), event.version());

            // Nếu cần gửi event ra hệ thống khác,
            // INSERT integration_outbox tại đây, cùng transaction.
            return Result.PROCESSED;
        }));
    }

    private void validate(OrderStatusEvent event) {
        Objects.requireNonNull(event);
        Objects.requireNonNull(event.eventId());
        Objects.requireNonNull(event.tenantId());
        Objects.requireNonNull(event.orderId());
        Objects.requireNonNull(event.state());
        if (event.version() < 1) {
            throw new IllegalArgumentException("version must be positive");
        }
    }

    public enum Result { PROCESSED, DUPLICATE }
}
~~~

Đoạn code cố ý không gọi HTTP hoặc publish broker trực tiếp bên trong DB transaction. Java text block yêu cầu Java 15+. `validate` phải được hoàn thiện theo hợp đồng ứng dụng, nhất là xác thực tenant từ nguồn tin cậy, dữ liệu hợp lệ và quyền xử lý.

**Lý do chống race:** PostgreSQL giải quyết cạnh tranh khi hai transaction `INSERT` cùng unique key. B có thể chờ A commit hoặc rollback; sau commit của A thì `ON CONFLICT DO NOTHING` trả số row insert là 0, trong khi rollback của A cho phép một worker khác claim lại. Cần giới hạn thời gian transaction để tránh lock kéo dài và kiểm soát deadlock/timeout.

**Vì sao thêm version:** hai event **khác ID** có thể đến sai thứ tự. Điều kiện `source_version < EXCLUDED.source_version` ngăn bản cũ ghi đè bản mới đối với projection cho phép nhận latest state. Nhưng nếu yêu cầu xử lý **mọi bước chuyển** đúng thứ tự, phải kiểm tra `expectedVersion = currentVersion + 1` và có cách giữ lại event đến sớm, không chỉ bỏ qua phiên bản cũ.

**Không coi mọi lỗi là duplicate:** database timeout, deadlock, mất kết nối, lỗi foreign key hoặc mismatch payload cần rollback và retry/quarantine theo nguyên nhân. Chỉ kết quả `claimed == 0` từ đúng unique key mới có nghĩa event đã có receipt tương ứng. Với MySQL, không thể copy `ON CONFLICT`; nên dùng cú pháp tương ứng và bắt đúng duplicate key thay vì mặc định `INSERT IGNORE` là an toàn cho mọi loại lỗi.

### 4.3. Giới hạn về transaction

- Nếu có nhiều datasource, `TransactionTemplate` phải dùng đúng `PlatformTransactionManager` quản lý `JdbcTemplate`; không tự suy ra có transaction chung giữa hai database.
- Inbox và business update được commit nguyên tử **chỉ trong database**. Một HTTP call, message publish hay email không tự rollback theo transaction đó.
- Nếu business operation thất bại, phải rollback cả marker; nếu commit marker riêng trước rồi fail business update, retry sẽ bị skip nhầm.
- Không đưa raw payload hoặc credential vào bảng inbox nếu không có nhu cầu và kiểm soát dữ liệu rõ ràng.

## 5. Ack broker sau khi transaction đã commit

Ở mọi broker, cần phân biệt **đã nhận message** và **đã hoàn tất tác động bền vững**:

~~~text
Đúng:
receive → begin DB tx → claim → business update → commit → ack

Sai:
receive → ack → begin DB tx → crash
           └─ broker không còn nghĩa vụ redeliver

Nếu thiếu inbox:
receive → update DB → commit → crash trước ack
          └─ redelivery → update DB lần nữa
~~~

Ví dụ Spring Kafka dùng manual acknowledgment, giả định listener container đã thực sự được cấu hình `AckMode.MANUAL` hoặc `MANUAL_IMMEDIATE` và có converter phù hợp cho `OrderStatusEvent`:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
class OrderProjectionListener {
    private final OrderProjectionHandler handler;

    OrderProjectionListener(OrderProjectionHandler handler) {
        this.handler = handler;
    }

    @KafkaListener(
        topics = "orders.status.changed",
        groupId = "order-projection")
    void onMessage(OrderStatusEvent event, Acknowledgment ack) {
        // handle() commit database trước khi trả kết quả.
        // Nếu handler ném lỗi, không ack ở nhánh này.
        handler.handle(event);
        ack.acknowledge();
    }
}
~~~

`groupId` không tự bật manual ack. Container factory, deserializer, error handler, retry và DLT phải được cấu hình tương ứng với phiên bản Spring Kafka và nghiệp vụ. Không bắt mọi exception rồi gọi `ack.acknowledge()` trong `finally`.

Với Pulsar, RabbitMQ hoặc Spring Integration inbound adapter, dùng cơ chế ack/nack, requeue hay transaction tương ứng. API khác nhau nhưng quy tắc giống nhau: **chỉ xác nhận sau khi trạng thái đã xử lý được lưu bền vững**, hoặc sau khi một yêu cầu xử lý tiếp theo đã được ghi nhận bền vững theo hợp đồng.

Một duplicate đã có receipt thành công có thể ack như một lần nhận thành công. Nếu database không sẵn sàng, không được đoán đó là duplicate từ cache local.

## 6. Cạnh tranh giữa nhiều pod: những trường hợp phải phân biệt

| Kịch bản | Pod A | Pod B | Kết quả |
| --- | --- | --- | --- |
| Hai transaction cùng key | Insert marker nhưng chưa commit | Insert marker, có thể chờ unique lock | DB chọn một commit hợp lệ |
| A commit | Commit marker + business | `claimed=0` | B không làm business effect |
| A rollback | Rollback marker + business | Có thể insert và xử lý | Không mất sự kiện |
| A commit rồi mất ack | Side effect đã commit | Broker giao lại cho B | B nhận diện duplicate và ack |
| A update business ngoài DB rồi chết | HTTP đích đã chạy | B retry cùng key | Cần idempotency tại đích |

Unique constraint là **điểm phân xử bền vững** cho event ID. Nhưng nó không cấm hai event khác ID cùng sửa một aggregate, và không giải quyết được các HTTP side effect ngoài DB.

Với PostgreSQL, `READ COMMITTED` và unique key đủ cho mẫu insert-first thông thường. Không cần nâng mọi transaction lên `SERIALIZABLE` chỉ để chặn trùng cùng event ID. Nếu domain có nhiều invariant phụ thuộc tập row hoặc bảng khác, cần bổ sung row lock, optimistic locking, unique business constraints hay isolation phù hợp.

## 7. Chống trùng event chưa đủ để giữ đúng thứ tự trạng thái

Xét hai event khác ID:

~~~text
E1: order-42, version=10, state=PAID
E2: order-42, version=11, state=SHIPPED
~~~

Nếu E2 đến trước E1, chỉ đánh dấu hai event ID là “đã thấy” không ngăn E1 ghi đè trạng thái về `PAID`. Vì thế cần tách **deduplication** khỏi **ordering/concurrency theo aggregate**:

- `Optimistic versioning`: cập nhật nếu version mới lớn hơn (projection latest-state) hoặc bằng `currentVersion + 1` (workflow cần xử lý từng bước).
- `SELECT ... FOR UPDATE` hoặc điều kiện `UPDATE ... WHERE version=?` để bảo vệ read–check–write trong cùng DB transaction.
- Broker key/partition theo `tenant + aggregateId` để giảm reorder theo cam kết cụ thể của broker.
- Business state machine và DB constraints để chặn chuyển trạng thái không hợp lệ.
- Giới hạn concurrency/rate ở nguồn downstream khi nhiều aggregate cập nhật cùng hệ thống.

Một Kafka partition được một consumer trong **cùng group** sở hữu tại một thời điểm, nhưng rebalance/replay và group khác vẫn có thể gây xử lý lại. Pulsar `Shared` và `Key_Shared` có đặc tính routing/ordering khác nhau; `Key_Shared` còn phụ thuộc producer batching đúng cách. RabbitMQ prefetch/ack có thể redeliver. Cấu hình broker giúp phân phối tải, **không thay thế kiểm soát trạng thái nghiệp vụ bền vững**.

## 8. Side effect ngoài database: inbox một mình chưa đủ

Giả sử consumer nhận `PaymentCaptured` rồi phải gọi HTTP sang dịch vụ phát hành hóa đơn:

~~~text
DB INSERT inbox(E1) + COMMIT
HTTP POST /invoices
~~~

Nếu pod chết sau commit inbox nhưng trước HTTP call, broker giao lại E1 và handler thấy duplicate, dẫn tới **không bao giờ tạo hóa đơn**. Ngược lại, nếu HTTP call được thực hiện trước khi ghi marker, một crash sau khi API đích xử lý thành công nhưng trước khi commit marker có thể tạo **hai hóa đơn** khi retry.

Ba hướng xử lý thường gặp:

| Mẫu | Khi nào phù hợp | Điều kiện then chốt |
| --- | --- | --- |
| **Inbox + transactional outbox** | Sau DB commit cần gửi event/lệnh bất đồng bộ | Receipt và ý định gửi được commit cùng transaction |
| **Idempotency key của API đích** | Hệ thống HTTP cung cấp cơ chế dedupe | Mọi retry dùng cùng key, cùng payload hợp lệ |
| **Saga/workflow bền vững** | Nhiều dịch vụ và bước có bồi hoàn | State machine, timeout, retry, reconciliation và compensation |

### 8.1. Transactional outbox

~~~mermaid
flowchart LR
    A[Nhận event E1] --> B[DB transaction]
    B --> C[Insert inbox E1]
    C --> D[Update business]
    D --> E[Insert outbox operationId]
    E --> F[Commit]
    F --> G[Ack input broker]
    F --> H[Outbox publisher]
    H --> I[HTTP hoặc output broker]
    I --> J[Đánh dấu outbox đã gửi]
~~~

Nếu pod chết **trước khi commit**, không có receipt cũng không có outbox. Nếu pod chết **sau khi commit nhưng trước publish**, một publisher khác vẫn có thể gửi. Nếu publisher gửi thành công nhưng chết **trước khi đánh dấu đã gửi**, nó có thể gửi thêm lần nữa. Outbox bảo vệ **khả năng phục hồi ý định gửi**, không tự tạo exactly-once ở hệ thống đích.

Cần truyền `operationId`/`eventId` ổn định cho consumer đích và dùng idempotency ở đó. Nếu nhiều publisher đọc outbox cùng lúc, có thể claim row qua transaction/lease hoặc khóa hàng thích hợp; phải xử lý cả publisher chết và hết lease.

### 8.2. HTTP Idempotency-Key

Một API bên ngoài hỗ trợ idempotency có thể nhận:

~~~http
POST /invoices HTTP/1.1
Idempotency-Key: tenant-a:invoice:create:order-42
Content-Type: application/json

{"orderId":"order-42","amount":125000}
~~~

Header và cú pháp ở trên chỉ là ví dụ; mỗi provider có hợp đồng riêng về tên header, thời hạn key, payload hash và cách trả response cho lệnh lặp. Giá trị `Idempotency-Key` phải giữ nguyên qua mọi retry của **cùng business operation** và được lưu trong outbox/workflow. Không tạo random UUID mới mỗi lần retry. Một HTTP timeout không chứng minh rằng API đích chưa hoàn tất thao tác, vì response có thể bị mất sau khi đích commit.

Nếu API đích không hỗ trợ idempotency, cần cân nhắc endpoint tra cứu trạng thái, khóa nghiệp vụ ở hệ thống đích, reconciliation hoặc bồi hoàn. Không thể dùng một lock cục bộ để bảo đảm exactly-once cho side effect ở dịch vụ khác.

## 9. Lease, PROCESSING và fencing cho tác vụ dài

Đối với công việc kéo dài nhiều giây/phút hoặc cần gọi external HTTP, giữ transaction DB mở để khóa event là bất lợi. Có thể thiết kế **bảng trạng thái xử lý**:

~~~text
NEW
  └─ claim → PROCESSING(ownerToken, leaseUntil, attempt)
                 ├─ success → COMPLETED
                 ├─ transient failure → RETRYABLE
                 └─ permanent failure → FAILED / DEAD_LETTER
~~~

Worker claim bằng một thao tác nguyên tử và ghi `owner_token`, `lease_until`. Worker khác chỉ takeover khi điều kiện lease cho phép, có thể tăng `attempt`, áp dụng giới hạn retry. Khi hoàn tất, một lệnh có điều kiện như `UPDATE ... WHERE owner_token=? AND status='PROCESSING'` giúp một worker đã mất quyền không ghi đè trạng thái local.

**Cạm bẫy lease:** lease hết hạn **không** có nghĩa worker cũ đã ngừng thực thi. Pod A có thể bị GC pause, lease hết và pod B claim rồi gọi HTTP. Pod A tỉnh lại cũng có thể gọi HTTP. So sánh owner token khi hoàn thành chỉ bảo vệ **bảng điều phối local**, không chặn side effect trên HTTP server.

Khi cần bảo vệ tài nguyên đích trước worker cũ, dùng **fencing token đơn điệu** (epoch/version cao hơn chiến thắng) được **chính hệ thống đích** kiểm tra; hoặc đích phải hỗ trợ idempotency key. Random owner token chỉ giúp nhận diện chủ lease, **không phải fencing token**. Nếu đích không hỗ trợ cả fencing lẫn idempotency, hãy mô tả rõ giới hạn bảo đảm và dùng reconciliation/compensation phù hợp.

### 9.1. Redis lock có thay được unique constraint không?

Khóa `SET lock:key token NX PX leaseMs` có ích để giảm số worker cùng cố tải một resource. Tuy nhiên:

- Lease có thể hết khi worker vẫn chạy; hai worker cùng thực hiện tác động.
- Network partition, Redis failover, timeout hoặc sai cấu hình làm việc điều phối phải được phân tích.
- Crash sau external side effect nhưng trước trạng thái bền vững tạo retry và khả năng lặp.
- Release khóa phải kiểm tra token rồi xóa **nguyên tử**; không dùng cặp `GET` và `DEL` riêng rẽ.

Redis lock có thể giúp giảm tải hoặc tránh stampede, nhưng không nên được dùng như **bằng chứng cuối cùng** rằng đã trừ tiền đúng một lần, phát hành đúng một hóa đơn hoặc xử lý xong một business operation. Với dữ liệu nằm trên một relational database, unique constraint và transaction thường là nền tảng chắc chắn hơn.

## 10. Lưu marker bao lâu và xử lý replay có chủ đích

`consumer_inbox` sẽ tăng theo số event. Xóa marker quá sớm có thể khiến message cũ xuất hiện lại và đi qua như một sự kiện mới.

~~~text
Dedup retention cần bao phủ cửa sổ có thể có duplicate:
  broker retention/replay
  + retry, DLQ, outbox resend
  + khoảng backfill và khôi phục được hỗ trợ
~~~

Đây là cách phân tích các **nguồn phát lại**, không phải phép cộng số học bắt buộc: cửa sổ bảo vệ thực tế phải dài hơn **độ tuổi tối đa** mà sự kiện cũ vẫn có thể quay lại, xét cả các quy trình vận hành thủ công. Nếu hệ thống có thể replay sau sáu tháng, marker chỉ giữ bảy ngày không còn chặn được replay sau thời gian đó.

Các chiến lược có thể cân nhắc: partition và archive inbox; lưu tombstone chứa khóa tối thiểu; giữ business operation ID có unique constraint lâu hơn; không dùng raw PII trong marker. Chính sách xóa phải phù hợp yêu cầu tuân thủ dữ liệu và vòng đời thực tế của event.

Phân biệt bốn trường hợp:

1. **Retry cùng yêu cầu:** giữ nguyên event/operation ID, phải được chặn nếu đã thành công.
2. **Replay để phục hồi projection:** có thể cần một handler version hoặc projection table mới, nhưng không được tái phát side effect không mong muốn.
3. **Reprocess có thay đổi input:** chỉ tạo revision mới khi có chủ đích, được kiểm soát và có quy tắc thay thế kết quả cũ.
4. **Backfill lịch sử:** đảm bảo tenant/aggregate version, thứ tự và trạng thái hiện tại không bị event cũ ghi đè.

Việc đổi tên `handler_name` mỗi lần deploy sẽ khiến toàn bộ receipt cũ không còn chặn duplicate cho tên handler mới. Chỉ thay namespace của handler khi thực sự có kế hoạch reprocess và biết hệ quả.

## 11. Phân loại lỗi, retry và poison message

Không phải lỗi nào cũng nên retry; cũng không phải mọi exception đều có nghĩa “đã xử lý”.

| Tình huống | Xử lý phù hợp |
| --- | --- |
| Duplicate đã commit cùng khóa | Skip business effect, ack thành công, tăng metric duplicate |
| Transaction khác đang claim | Đợi có giới hạn; lock timeout thì retry với backoff |
| Database deadlock hoặc mất kết nối | Rollback, không ack success; retry giới hạn với jitter |
| Payload/schema sai vĩnh viễn | Reject/DLQ/quarantine theo hợp đồng; không loop vô hạn |
| Thiếu prerequisite có thể bổ sung sau | Retry trì hoãn hoặc đợi version/quan hệ phụ thuộc |
| HTTP 429/503 | Retry có backoff và concurrency limit, cùng idempotency key |
| HTTP timeout, không rõ kết quả | Tra cứu trạng thái nếu hỗ trợ, rồi retry cùng operation ID |
| Event ID trùng nhưng payload khác | Báo xung đột hợp đồng, không âm thầm bỏ qua |
| Không thể kiểm tra inbox vì DB lỗi | Không coi đó là duplicate; xử lý theo luồng lỗi |

Cần chọn **một nơi chịu trách nhiệm chính** cho retry của từng giai đoạn: Spring Kafka error handler/DLT, Pulsar retry/DLQ, RabbitMQ requeue/DLX, Spring Integration error channel hay workflow trong DB. Nếu adapter, broker và ứng dụng đều retry vô hạn, hệ thống có thể gây retry storm và làm nguồn dữ liệu sập.

Đặt tổng số lần retry hoặc deadline, backoff có jitter, DLQ có kiểm soát và quy tắc re-drive. Poison message không nên chặn toàn bộ subscription, nhưng việc bỏ qua nó cũng phải tôn trọng invariant ordering: event version 11 có thể không hợp lệ nếu version 10 chưa được áp dụng.

## 12. Quan sát duplicate rate và tác động nghiệp vụ

Chỉ đo số message nhận và ack là chưa đủ. Cần đối chiếu dữ liệu bền vững và nguồn downstream để biết chống trùng có thực sự hiệu quả.

| Nhóm | Metric hoặc tín hiệu | Ý nghĩa |
| --- | --- | --- |
| Inbox | Claim thành công, duplicate skip, payload conflict | Nhận diện retry và lỗi upstream |
| DB concurrency | Unique conflict, thời gian chờ lock, deadlock, transaction timeout | Phát hiện nhiều replica cạnh tranh cùng key |
| Broker | Redelivery, consumer lag/backlog, nack, DLQ, rebalance | Liên hệ duplicate với hạ tầng message |
| Outbox | Pending age, resend, publish timeout, failure rate | Phát hiện mất tiến độ hoặc retry quá nhiều |
| HTTP downstream | Idempotency hit, timeout, external response không chắc chắn | Xác minh hệ thống đích chống trùng |
| Nghiệp vụ | Business operation count, invariant violations, double-charge detection | Đo **tính đúng**, không chỉ throughput |

Micrometer/Actuator và tracing có thể nối receive → claim inbox → DB commit → ack → publish outbox → xử lý ở đích. Không dùng raw `eventId`, `orderId`, `userId` hoặc `tenantId` có cardinality cao làm metric tag; log/trace có thể giữ correlation ID với kiểm soát truy cập và lọc dữ liệu nhạy cảm. Tránh ghi token, credential và raw payload không cần thiết.

Cảnh báo nên dựa trên baseline: duplicate rate tăng mạnh sau rebalance, contention tăng theo số pod, pending outbox quá SLA, lease hết hạn nhưng worker còn gọi downstream, số record đã xử lý thực tế vượt số business command hợp lệ.

## 13. Kiểm thử race condition và các cửa sổ crash

Unit test gọi handler hai lần tuần tự chỉ xác nhận nhánh duplicate cơ bản. Cần **kiểm thử đồng thời với database thật tương ứng production**, ví dụ PostgreSQL qua Testcontainers, rồi tạo fault injection tại các ranh giới quan trọng.

| Kịch bản | Cách tạo | Kỳ vọng |
| --- | --- | --- |
| Hai worker cùng event ID | Hai transaction riêng bắt đầu tại barrier | Một receipt, một business effect commit |
| Winner rollback | A insert nhưng rollback, B chờ cùng key | B xử lý được; không mất event |
| Commit rồi mất ack | DB commit, kill process trước broker ack | Redelivery nhận diện duplicate, không nhân effect |
| Crash trước commit | Ngắt worker khi transaction chưa commit | Marker/business đều rollback; retry thành công |
| Event khác topic cùng ID | Replay/re-publish cùng event ID tới cùng logical handler | Vẫn dedupe nếu business identity không đổi |
| Cùng event ID, khác payload | Đổi một trường với same key | Được phát hiện là xung đột contract |
| Hai event khác version | Giao 11 trước 10 | Không ghi đè trạng thái mới bằng event cũ |
| Outbox đã gửi, chưa đánh dấu | Kill publisher sau send success | Downstream chống trùng bằng operation ID |
| HTTP đích xử lý nhưng timeout | Mock remote commit rồi drop response | Retry cùng Idempotency-Key không tạo effect thứ hai |
| Lease hết khi worker A còn chạy | A pause, B takeover, A tỉnh lại | Fencing/idempotency ở đích chặn stale effect |
| DB không sẵn sàng | Connection timeout/deadlock | Không ack success, retry giới hạn |
| Retry/DLQ hàng loạt | Rebalance/replay dưới tải | Không cạn connection pool, không tạo side effect trùng |

Cách làm race test hiệu quả:

1. Dùng hai instance service hoặc hai transaction/connection độc lập nhưng cùng PostgreSQL; đồng bộ điểm bắt đầu với `CountDownLatch` hoặc barrier.
2. Giữ transaction A chưa commit để B thật sự va vào unique index. Test riêng cả nhánh A commit và A rollback.
3. Kiểm tra **số row đã commit** trong inbox, bảng nghiệp vụ và outbox; đếm số lần method được gọi là chưa đủ.
4. Giả lập crash ngay **trước/sau commit** và **trước/sau ack**. Đây là các cửa sổ có nguy cơ mất hoặc trùng việc.
5. Với HTTP, dùng mock service giữ lịch sử `Idempotency-Key` và mô phỏng response bị mất sau commit.
6. Test giới hạn concurrent jobs/consumers, timeout, lock contention và redelivery trên nhiều replica.
7. Không viết assertion rằng worker A luôn thắng; hành vi đúng cần được giữ dù bất kỳ worker nào thắng.

Nếu chỉ có unit test in-memory, ta chưa kiểm chứng được unique index của database, transaction isolation, network fault và hành vi container message thật.

## 14. Chọn cơ chế theo phạm vi nhất quán

| Nguồn và đích | Điểm nguyên tử đáng tin cậy | Cơ chế nên dùng |
| --- | --- | --- |
| Broker consumer → **một relational DB** | Transaction + unique index | Inbox receipt + business update + ack sau commit |
| HTTP retry → **một relational DB** | Unique business key + transaction | Stable idempotency key, lưu kết quả để trả lại |
| Broker/HTTP → DB → phát broker khác | Không có transaction tự động xuyên hai hệ thống | Inbox + transactional outbox + consumer đích idempotent |
| Consumer → external payment/invoice API | API đích nắm side effect | Stable Idempotency-Key, durable workflow và reconciliation |
| Tác vụ dài có nhiều worker | Lease điều phối chỉ có hiệu lực tạm thời | Durable state + lease + fencing/idempotency ở đích |
| Nhiều event khác ID cùng aggregate | Unique event ID không giải quyết ordering | Version check, row lock, keyed partitioning, domain invariant |
| Replay/backfill dài hạn | Marker TTL có thể ngắn hơn replay window | Retention chính sách hoặc business invariant lâu dài |

Trước khi triển khai, trả lời bảy câu hỏi:

1. **Cùng tác động nghĩa là gì?** Một message, một command, một khoản thanh toán hay một lần chuyển trạng thái?
2. **Khóa ổn định qua retry là gì?** Event ID, command ID, tenant, handler và version do ai cấp?
3. **Nguồn sự thật là gì?** Một database, nhiều database hay API bên ngoài? Transaction nào bao phủ được bước nào?
4. **Ai có thể chạy đồng thời?** Consumer group, subscription, HTTP retry, scheduler, nhiều replica, publisher replay?
5. **Nếu crash trước/sau commit và ack thì sao?** Có mất việc hoặc trùng side effect không?
6. **Dữ liệu cũ xử lý thế nào?** Ordering, revision, replay retention và DLQ có làm sống lại event không?
7. **Kiểm chứng bằng gì?** Unique conflict, duplicate skip, outbox age, reconciliation và race test nào?

**Nguyên tắc cốt lõi:** chống trùng đồng thời không thể chỉ dựa vào `existsById()`, một cache cục bộ hoặc distributed lock có lease. Hãy dùng **business identity ổn định**, cơ chế phân xử **nguyên tử và bền vững** (thường là unique constraint trong transaction DB), **ack sau commit**, và **idempotency/fencing ở hệ thống chịu side effect ngoài transaction**. Khi đó scale-out, retry, rebalance và crash không khiến một yêu cầu hợp lệ biến thành nhiều thay đổi nghiệp vụ.

### Tài liệu tham khảo

- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): ranh giới transaction, rollback, propagation và transaction manager.
- [Spring for Apache Kafka — Message Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): acknowledgment, container và message listener.
- [Spring for Apache Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): phạm vi đảm bảo của Kafka transaction và các tác động ngoài Kafka.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): xử lý tranh chấp unique key và `DO NOTHING`.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): chờ lock và deadlock trong PostgreSQL.
- [Apache Kafka — Documentation](https://kafka.apache.org/documentation/): consumer groups, delivery semantics và producer/consumer behavior.

Ví dụ minh họa sử dụng PostgreSQL, Spring JdbcTemplate/TransactionTemplate, Spring Kafka và Java text blocks. Khi vận dụng phải xác minh đúng phiên bản Spring Boot, broker, driver, isolation level và hợp đồng idempotency của API đích; chỉ những thay đổi trong **cùng transaction DB** mới được commit/rollback nguyên tử theo mẫu trên.


