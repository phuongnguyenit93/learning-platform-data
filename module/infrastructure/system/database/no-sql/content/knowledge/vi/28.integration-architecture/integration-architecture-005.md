# Giao dịch trong một hệ và phối hợp nghiệp vụ qua nhiều dịch vụ

## 1. Vấn đề: một lần “Đặt hàng” nhưng nhiều hệ phải thay đổi

Một ứng dụng thương mại điện tử có các dịch vụ:

```text
                         Client
                           |
                           v
                     Order Service
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
   Inventory Service  Payment Service  Notification Service
          |                |                |
          v                v                v
     Inventory DB      Payment DB       Message Provider
```

Người dùng nhấn **Đặt hàng**. Về nghiệp vụ, hệ cần:

1. Tạo đơn hàng.
2. Giữ đủ số lượng sản phẩm.
3. Xử lý hoặc ủy quyền thanh toán.
4. Xác nhận đơn hàng.
5. Gửi thông báo.
6. Giải phóng phần tài nguyên đã giữ nếu một bước không thành công.

Mỗi dịch vụ có thể dùng một cơ sở dữ liệu NoSQL riêng và có quyền thay đổi dữ liệu của mình. Khi có sự cố, những bước này **không nhất thiết cùng thành công hoặc cùng thất bại**.

Ví dụ:

```text
T0: Order DB tạo O100 -> thành công
T1: Inventory DB giữ 1 sản phẩm -> thành công
T2: Payment provider thu tiền -> thành công
T3: Order Service mất kết nối trước khi ghi CONFIRMED
T4: Client timeout, bấm "Đặt hàng" thêm lần nữa
```

Nếu xử lý thiếu kiểm soát, hệ có thể giữ hàng hai lần, thu tiền hai lần, hoặc đơn hàng còn `PENDING` dù provider đã thanh toán thành công.

Ở đây có **hai cấp độ cần phân biệt**:

- **Giao dịch trong một hệ (local/database transaction):** database bảo đảm một tập thao tác được thực hiện nguyên tử theo phạm vi transaction mà API hỗ trợ.
- **Phối hợp nghiệp vụ nhiều dịch vụ (distributed business workflow):** nhiều bước local, sự kiện và external effects cần được điều phối để đi đến trạng thái nghiệp vụ đúng, có thể có trạng thái trung gian và hành động bù.

Bài học thuộc chương **Tích hợp và kiến trúc**, tập trung vào cách kết hợp đúng hai cấp độ trên trong NoSQL: atomic update, conditional write, transaction API, outbox/inbox, Saga, TCC, idempotency và đối soát.

> **Nguyên tắc trung tâm:** transaction của một database không tự mở rộng qua HTTP request, message broker, database của dịch vụ khác hoặc cổng thanh toán. Muốn nghiệp vụ xuyên nhiều hệ đúng, phải thiết kế giao thức phối hợp và phục hồi bên ngoài ranh giới transaction cục bộ.

## 2. Ba câu hỏi phải trả lời trước khi chọn kiến trúc

### 2.1. Bất biến nghiệp vụ là gì?

Một số ví dụ:

- Không được xác nhận hai khách giữ cùng một ghế.
- Tồn kho không được âm.
- Một `paymentIntentId` không bị charge hai lần cho cùng mục đích.
- Tổng bút toán sổ cái cân đối theo quy tắc kế toán.
- Không gửi hàng nếu đơn chưa được xác nhận thanh toán theo chính sách.
- Không chuyển quyền sở hữu khi chưa thỏa điều kiện.

Viết chúng thành mệnh đề rõ ràng, thay vì chỉ nói “cần strong consistency”.

### 2.2. Bất biến nằm ở đâu?

Ví dụ `available >= 0` có thể kiểm tra trên một item Inventory. Nhưng “Order đã CONFIRMED thì Inventory đã RESERVED và Payment đã AUTHORIZED” trải qua **ba dịch vụ**.

Một local transaction trên Order DB có thể giữ điều kiện của Order; nó không tự sửa Inventory/Payment.

### 2.3. Khi lỗi giữa các bước, kết quả nào được chấp nhận?

- Dừng ngay và trả `REJECTED`?
- Giữ `PENDING`, tiếp tục xử lý sau?
- Hủy reservation bằng compensation?
- Chờ cổng thanh toán xác nhận trạng thái?
- Hoàn tiền nếu tiền đã bị capture?
- Chuyển sang xử lý thủ công?

Đây là **chính sách nghiệp vụ**, không chỉ lựa chọn library.

## 3. Transaction là gì?

Một **transaction** là nhóm thao tác được xử lý theo một hợp đồng xác định về atomicity, consistency, isolation và durability.

### 3.1. Atomicity

Các thay đổi thuộc phạm vi transaction được commit cùng nhau hoặc rollback cùng nhau theo semantics API.

Ví dụ:

```text
Trong cùng transaction:
  Put Order O100
  Decrement Inventory P100
  Put Outbox Event E100

Commit -> cả ba thay đổi tồn tại
Abort  -> không công bố thay đổi một phần
```

Nhưng chỉ đúng nếu **database thật sự hỗ trợ transaction bao trùm ba items đó** và thao tác được gọi đúng API.

### 3.2. Consistency

Transaction giúp chuyển trạng thái từ một cấu hình thỏa các ràng buộc được kiểm tra sang cấu hình hợp lệ.

Quan trọng: chữ **C** trong ACID không có nghĩa database tự hiểu quy tắc “không bán trùng ghế”. Ứng dụng và database phải biểu diễn invariant bằng điều kiện, constraint hoặc một command nguyên tử.

### 3.3. Isolation

Isolation quy định các transactions đồng thời có thể quan sát và ảnh hưởng nhau thế nào.

Không nên mặc định mọi NoSQL transaction đều **serializable**. Tùy sản phẩm có thể có snapshot isolation, serializable transaction, optimistic retries hoặc những giới hạn riêng.

### 3.4. Durability

Sau khi commit được xác nhận, dữ liệu sống sót trước những loại lỗi được sản phẩm và cấu hình hứa.

Durability phụ thuộc cả replication, write concern, disk persistence và failover semantics. Nó **khác** việc một read replica đã hiển thị dữ liệu.

## 4. Một hệ không nhất thiết là một node hay một partition

Từ “local transaction” rất dễ gây nhầm.

**Local ở đây có nghĩa:** transaction được quản lý bởi **một database system/transaction authority** theo API hỗ trợ. Nó có thể tác động nhiều documents, tables hoặc shards nếu database hỗ trợ.

Ví dụ:

- Một atomic item update trên DynamoDB là thao tác trong một bảng tại một phạm vi được hỗ trợ.
- `TransactWriteItems` có thể tác động nhiều items/tables trong cùng phạm vi transaction của DynamoDB.
- MongoDB có multi-document transactions, kể cả trên sharded clusters khi topology hỗ trợ.
- Một transactional batch Cosmos DB for NoSQL có phạm vi **cùng logical partition key**.
- Firestore có transactions cho nhiều documents trong phạm vi giới hạn sản phẩm.

Ngược lại, **hai dịch vụ dùng cùng một loại database** chưa đủ để một `@Transactional` ở Order Service bao phủ thao tác riêng tại Payment Service.

### 4.1. Transaction boundary phải được ghi rõ

| Phạm vi | Ví dụ | Có thể atomic bằng cách nào? |
|---|---|---|
| Một field/item | Trừ inventory từ 5 xuống 4 | Atomic update có điều kiện |
| Một document | Đổi trạng thái và version cùng lúc | Atomic document mutation |
| Một logical partition | Ghi Order cùng các rows phụ trợ | Transaction/batch nếu engine hỗ trợ |
| Nhiều items trong một database | Order + Inventory + Outbox | Native multi-item transaction nếu hỗ trợ và cùng scope |
| Nhiều database systems | Order DB + Inventory DB | Không tự có; cần distributed transaction hoặc workflow |
| Database và HTTP payment | Update Order + gọi provider | Không có atomicity mặc định; cần idempotent workflow |
| Database và message broker | Save Order + publish event | Transactional outbox hoặc cơ chế tích hợp đặc biệt |
| Database và email | Commit Order + gửi mail | Side effect phải xử lý riêng, thường eventual/idempotent |

**Đơn vị transaction do hệ lưu trữ cam kết, không phải do code tổ chức trong một hàm Java.**

## 5. Atomic operation một item: nền tảng của NoSQL

Nhiều NoSQL ưu tiên một access pattern trong đó một aggregate nghiệp vụ được lưu đủ gần để cập nhật nguyên tử.

Ví dụ item Inventory:

```json
{
  "productId": "P100",
  "available": 5,
  "reserved": 2,
  "version": 17
}
```

Khi giữ 1 đơn vị, không nên làm:

```text
GET available=5
Nếu available > 0:
    PUT available=4
```

Hai clients có thể cùng đọc 5 rồi ghi 4, dẫn đến **lost update** và xác nhận quá nhiều reservations.

Cần dùng một atomic conditional update:

```text
UPDATE Inventory(P100):
    IF available >= 1
    SET available = available - 1,
        reserved = reserved + 1,
        version = version + 1
```

Đối với operation được database thực thi nguyên tử, một lượt khác không thể đồng thời vượt qua điều kiện trên cùng trạng thái cũ theo semantics tương ứng.

### 5.1. Đơn vị gốc của invariant

Nếu `available >= 0` gói gọn trong một item, một conditional item update thường đủ để giữ invariant, tránh transaction nhiều items không cần thiết.

### 5.2. Điều kiện phải nằm tại database

Kiểm tra `if (available > 0)` chỉ ở Java trước khi gọi một `PUT` vô điều kiện không chống được race.

### 5.3. Atomic update không bảo vệ hệ khác

Một Inventory decrement nguyên tử vẫn không tự tạo Order hoặc charge payment. Cần thêm workflow.

## 6. Aggregate và đặt invariant đúng ranh giới

Trong thiết kế domain-driven, **aggregate** là một nhóm dữ liệu có invariant cần được bảo vệ tại một ranh giới nhất quán.

Ví dụ Reservation có thể chứa:

```json
{
  "reservationId": "R100",
  "seatId": "SEAT-100",
  "ownerId": "U42",
  "status": "HELD",
  "expiresAt": "2026-11-14T12:00:00Z",
  "version": 3
}
```

Một mutation có điều kiện:

```text
IF seat chưa được claim hoặc hold đã hết hạn hợp lệ:
    tạo/đổi reservation theo authority
ELSE:
    từ chối
```

Cần cẩn thận: nếu mỗi reservation của cùng một ghế nằm ở một item khác nhau mà không có **seat authority**, hai requests có thể tạo hai reservations và đều nghĩ mình thành công.

### 6.1. Đặt dữ liệu cạnh nhau có lợi

Khi state và điều kiện ở một item/document/partition, thao tác thường đơn giản hơn, latency thấp hơn và ít coordination hơn.

### 6.2. Không ép mọi dữ liệu vào một document khổng lồ

Đặt tất cả Orders của một tenant trong một document chỉ để có atomicity có thể chạm giới hạn kích thước, tạo hot key và làm read/write contention.

### 6.3. Thiết kế hai ranh giới

- **Consistency boundary:** nơi điều kiện bắt buộc phải đúng ngay lúc commit.
- **Workflow boundary:** tập các services cần cuối cùng đạt một kết quả nghiệp vụ.

Một quy trình có thể có nhiều consistency boundaries cục bộ và một workflow điều phối bên ngoài.

## 7. Optimistic concurrency control (OCC)

**OCC** dùng một version/ETag để phát hiện mutation dựa trên dữ liệu cũ.

```json
{
  "orderId": "O100",
  "status": "PENDING",
  "version": 7
}
```

Client muốn chuyển sang `CONFIRMED`:

```text
UPDATE Order O100
IF version=7 AND status=PENDING
SET status=CONFIRMED, version=8
```

Nếu một worker khác đã chuyển Order sang `CANCELLED`, mutation bị từ chối. Worker phải reload và đánh giá trạng thái mới, không retry vô điều kiện.

### 7.1. OCC khác LWW

- **Last-write-wins:** chọn một winner sau những mutations cạnh tranh, có thể âm thầm bỏ một update.
- **OCC/CAS:** phát hiện trạng thái đã đổi và từ chối một mutation stale.

Với financial/inventory/order-state transition, OCC thường phù hợp hơn việc blind overwrite.

### 7.2. Version khác timestamp

`updatedAt` không chắc đơn điệu khi clock lệch; `version` tăng qua authority có thể rõ ràng hơn cho CAS và event ordering.

### 7.3. Conflict không phải lỗi hạ tầng

CAS trả condition-failed có thể là một outcome nghiệp vụ bình thường: seat đã được giữ bởi người khác. Không retry vô hạn làm tăng contention.

## 8. DynamoDB: transaction nhiều items trong cùng phạm vi dịch vụ

DynamoDB có:

- Conditional writes trên item bằng `ConditionExpression`;
- `TransactWriteItems` cho nhiều thao tác ghi có tính giao dịch trong những giới hạn và phạm vi được tài liệu hỗ trợ;
- `TransactGetItems` cho transactional reads.

Một giao dịch checkout **nếu Order, Inventory và Outbox đều nằm trong DynamoDB cùng account/Region và thỏa giới hạn API** có thể được thiết kế:

```text
TransactWriteItems:
  1. UPDATE Inventory(P100)
       SET available = available - 1
       IF available >= 1

  2. PUT Order(O100, status=PENDING)
       IF attribute_not_exists(orderId)

  3. PUT Outbox(E100, type=OrderCreated)
       IF attribute_not_exists(eventId)
```

Nếu một điều kiện thất bại, cả transaction không được commit theo contract.

### 8.1. Không thực hiện hai actions trên cùng item

Trong `TransactWriteItems`, không đặt nhiều actions khác nhau lên **cùng một item** như vừa ConditionCheck vừa Update cho cùng key; gộp condition vào Update phù hợp.

### 8.2. Idempotency của transaction API có giới hạn

Một số SDK/API hỗ trợ client request token để deduplicate requests theo phạm vi/cửa sổ xác định. Điều này hữu ích nhưng **không thay một business idempotency record dài hạn** nếu user có thể retry sau nhiều giờ.

### 8.3. Transaction region không tự thành global transaction

Với global tables, replication multi-region và concurrent writes có semantics tùy mode. Một transaction trong Region A không được giả định là một global atomic transaction đồng bộ trên mọi Region.

### 8.4. Chi phí

Multi-item transactions có capacity/latency/contension và size limits. Khi thiết kế, giảm số item/partition tham gia và phân biệt invariant thật sự cần atomic với read models có thể cập nhật sau.

## 9. MongoDB: multi-document transaction trong một MongoDB system

MongoDB hỗ trợ transactions cho nhiều documents và, trong topology phù hợp, có thể qua nhiều collections/shards.

Ví dụ cùng MongoDB system:

```text
Transaction T100:
  Insert Order O100
  Update Inventory P100 if available >= 1
  Insert Outbox E100

COMMIT hoặc ABORT như một transaction
```

### 9.1. Java MongoDB Driver minh họa

Ví dụ dưới đây giả định đã có kết nối tới cluster hỗ trợ transactions, các collections dùng cùng MongoDB deployment, unique indexes cần thiết đã được cấu hình và các options read/write concern được chọn đúng production policy.

```java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

public final class LocalCheckoutTransaction {
    private final MongoClient mongoClient;
    private final MongoCollection<Document> inventory;
    private final MongoCollection<Document> orders;
    private final MongoCollection<Document> outbox;

    public LocalCheckoutTransaction(
            MongoClient mongoClient,
            MongoCollection<Document> inventory,
            MongoCollection<Document> orders,
            MongoCollection<Document> outbox
    ) {
        this.mongoClient = mongoClient;
        this.inventory = inventory;
        this.orders = orders;
        this.outbox = outbox;
    }

    public void createPendingOrder(
            String orderId,
            String productId,
            String operationId
    ) {
        try (ClientSession session = mongoClient.startSession()) {
            session.withTransaction(() -> {
                var updated = inventory.updateOne(
                        session,
                        and(
                                eq("_id", productId),
                                gte("available", 1)
                        ),
                        combine(
                                inc("available", -1),
                                inc("reserved", 1)
                        )
                );

                if (updated.getModifiedCount() != 1) {
                    throw new IllegalStateException(
                            "OUT_OF_STOCK"
                    );
                }

                orders.insertOne(
                        session,
                        new Document("_id", orderId)
                                .append("operationId", operationId)
                                .append("productId", productId)
                                .append("status", "PENDING")
                                .append("version", 1L)
                );

                outbox.insertOne(
                        session,
                        new Document("_id", "evt:" + orderId)
                                .append("aggregateId", orderId)
                                .append("type", "OrderCreated")
                                .append("published", false)
                );

                return null;
            });
        }
    }
}
```

**Phạm vi và giới hạn của ví dụ:**

- Cả ba collections phải thuộc **cùng MongoDB transaction context**; ở ví dụ này session được truyền vào từng operation.
- Phải có unique constraint/index tương ứng để xử lý duplicate `operationId`, không chỉ dùng `find` trước `insert`.
- Transaction có thể được driver retry theo các lỗi được gắn nhãn phù hợp; **callback không được gọi payment provider hoặc gửi email**.
- Transaction abort khi một bước fail, nhưng side effect đã xảy ra ngoài database **không được rollback**.
- Lỗi khi commit có thể tạo **unknown transaction outcome**; client phải dùng idempotency/status lookup.
- Tùy topology/version, cần cấu hình transaction options, write concern và timeout phù hợp.
- Không nên giữ transaction lâu để gọi mạng hoặc chờ con người; chi phí lock/snapshot/retention có thể tăng.

### 9.2. Một transaction không thay mô hình aggregate

Nếu mọi write nhỏ đều mở multi-document transaction dù chỉ sửa một document, throughput/latency có thể tệ hơn. Hãy ưu tiên atomicity đơn giản nhất đủ bảo vệ invariant.

## 10. Cassandra: regular writes, LWT và giới hạn batch

Cassandra có replication/write consistency levels cùng các cơ chế conditional mutation như **Lightweight Transactions (LWT)**.

### 10.1. Regular writes

```sql
UPDATE orders_by_id
SET status = 'PENDING'
WHERE order_id = 'O100';
```

Write `QUORUM` hay `LOCAL_QUORUM` nói về số/phạm vi replica responses, không tự biến mọi update nhiều partitions thành một transaction ACID.

### 10.2. LWT

Ví dụ claim một reservation:

```sql
INSERT INTO reservations_by_seat (
    seat_id, reservation_id, owner_id
)
VALUES ('SEAT-100', 'R100', 'U42')
IF NOT EXISTS;
```

LWT có conditional/serial consistency semantics trong phạm vi được phiên bản Cassandra hỗ trợ. Client phải đọc kết quả `[applied]`.

### 10.3. Logged batch không phải cross-partition ACID transaction

```sql
BEGIN BATCH
    INSERT INTO orders_by_id (...) VALUES (...);
    UPDATE inventory_by_id SET ... WHERE ...;
APPLY BATCH;
```

Đây là **cú pháp minh họa ý định**, không phải lệnh thực thi hoàn chỉnh. Cassandra logged batch chủ yếu có semantics phân phối/batchlog và không nên được suy như một transaction serializable qua nhiều partition keys.

Nếu cần invariant xuyên partitions, phải thiết kế workflow hoặc sử dụng khả năng transaction được **phiên bản cụ thể** cam kết, thay vì suy chung từ chữ `BATCH`.

### 10.4. NoSQL phải được đánh giá theo phiên bản

Các database có thể bổ sung transactional features theo thời gian. Hợp đồng lựa chọn đúng phải bám release/edition/API đang vận hành, không dùng một kết luận cũ cho mọi phiên bản.

## 11. Cosmos DB, Firestore, Redis và các hệ khác

### 11.1. Azure Cosmos DB for NoSQL

`TransactionalBatch` có transaction scope gắn với **cùng logical partition key**. Nếu Order và Outbox cần được commit cùng nhau, đặt chúng trong một logical partition khi mô hình phù hợp; không suy transaction này tự trải nhiều partition keys hoặc sang một payment provider.

### 11.2. Firestore

Firestore hỗ trợ transactions qua nhiều documents theo giới hạn/quy tắc sản phẩm. Transaction function có thể **được chạy lại** khi có concurrent modifications, nên không chứa side effect ngoài database như charge payment hay gửi email.

Write batch và transaction có semantics khác nhau, đặc biệt khi cần đọc rồi quyết định có điều kiện; phải chọn theo invariant.

### 11.3. Redis

`MULTI`/`EXEC` và Lua scripts có thể cung cấp cách thực thi tập lệnh nguyên tử trên một Redis server trong phạm vi hỗ trợ. Nhưng:

- Redis transactions không có rollback kiểu relational transaction cho mọi lỗi runtime.
- Durability/failover còn tùy persistence và replication mode.
- Redis Cluster có hạn chế về keys/hash slots khi thực hiện multi-key operations.
- Không có atomicity mặc định với một database ngoài Redis.

### 11.4. Elasticsearch/OpenSearch

Một bulk API có thể trả **thành công một phần**. Không nên coi một bulk request ghi nhiều documents là transaction atomic all-or-nothing. Đọc response theo từng item và dùng idempotent projection/retry.

### 11.5. Neo4j và graph databases

Một số graph databases cung cấp ACID transactions trong phạm vi graph/database của chúng. Chữ “NoSQL” không tự có nghĩa “không có transaction”; cần xem scope và isolation của từng hệ.

## 12. Isolation: atomic không tự là serializable

Giả sử hai bác sĩ A, B cùng trực; invariant là **ít nhất một bác sĩ trực**.

```text
Initial:
  Doctor A onCall=true
  Doctor B onCall=true
```

Hai transactions cùng đọc snapshot ban đầu:

```text
Transaction T1:
  đọc A=true, B=true
  ghi A=false

Transaction T2:
  đọc A=true, B=true
  ghi B=false
```

Nếu isolation cho phép **write skew**, cả hai commit và cuối cùng:

```text
A=false, B=false
```

Mỗi transaction atomic trên một record, nhưng invariant liên hai records bị phá.

### 12.1. Cần phân biệt các bảo đảm

- Atomicity một item;
- Snapshot isolation;
- Serializable transaction;
- Conditional write;
- Unique constraint;
- Predicate conflict detection;
- Compare-and-set;
- Linearizable read/update;
- Quorum replication.

Chúng không đồng nghĩa nhau.

### 12.2. Phương án bảo vệ

Có thể gom invariant vào một aggregate như `OnCallDuty(shiftId, doctorsOnDutyCount)` rồi kiểm tra điều kiện nguyên tử, hoặc dùng transaction serializable/constraint được database hỗ trợ.

### 12.3. Không nâng consistency level rồi hy vọng hết race

`QUORUM` replica ACK không tự tạo atomic read-modify-write. Cần đúng primitive bảo vệ điều kiện.

## 13. Durability, read visibility và transaction outcome

Một write có thể ở nhiều trạng thái khác nhau:

| Trạng thái | Ý nghĩa |
|---|---|
| Accepted | Server nhận request |
| Locally written | Một node đã ghi |
| Replicated | Nhiều replicas đã nhận |
| Committed | Transaction/authority đã quyết định |
| Applied | State machine/local storage đã áp dụng |
| Visible | Read path đang quan sát được |
| Durable | Sống sót trước những loại lỗi được cam kết |
| Published | Event tới message broker |
| Processed | Consumer đã xử lý side effect |

**Committed Order** không nghĩa **Payment đã charge**. **Outbox event persisted** không nghĩa **consumer đã nhận**. **Payment provider success** không nghĩa **Order DB đã chuyển CONFIRMED**.

Thiết kế API phải thể hiện đúng mốc đã đạt khi trả `200`, `201`, `202` hay một trạng thái `PENDING`.

## 14. Vì sao `@Transactional` không bao phủ ba microservices?

Xét:

```java
@Transactional
public void checkout() {
    orderRepository.save(order);
    inventoryClient.reserve(productId);
    paymentClient.charge(paymentIntentId);
}
```

Annotation transaction manager có thể quản lý các thao tác database mà nó tham gia. Nó **không tự enlist** một HTTP request tới Inventory Service hoặc Payment Service vào cùng local transaction.

Kịch bản:

```text
T0: Order local transaction bắt đầu
T1: inventoryClient.reserve() -> Inventory commit
T2: paymentClient.charge() -> Provider charge thành công
T3: Order local transaction rollback vì lỗi database
```

Order bị rollback nhưng Inventory/Payment vẫn đã có side effect.

### 14.1. Vấn đề khác: local lock giữ quá lâu

Nếu để DB transaction mở trong lúc chờ HTTP provider vài giây:

- Snapshot/locks/transaction resources bị giữ lâu.
- Network timeout tăng nguy cơ contention.
- Callback bị retry có thể gọi provider lần nữa.
- Thời gian phục hồi và throughput giảm.

### 14.2. Ranh giới phù hợp

Local transaction nên giữ **thay đổi dữ liệu và intent event trong cùng database**. Workflow khác dịch vụ được xử lý qua events/commands và state machine sau commit.

### 14.3. Một service có hai data sources

Ngay trong một JVM, nếu có hai transaction managers cho hai databases khác nhau, `@Transactional` theo một manager **không tự cung cấp atomic commit** cho cả hai. Cần xác định rõ transaction resource participation.

## 15. Dual write: lỗi nguy hiểm nhất của tích hợp

**Dual write** là khi code cố ghi vào database và message broker (hoặc hai databases) như hai bước độc lập.

### 15.1. Database trước, publish sau

```text
1. Commit Order O100
2. Publish OrderCreated(O100)
```

Nếu process crash giữa hai bước:

```text
Order tồn tại
Event không bao giờ được publish
```

Inventory Service không biết cần giữ hàng.

### 15.2. Publish trước, database sau

```text
1. Publish OrderCreated(O100)
2. Commit Order O100
```

Nếu commit thất bại:

```text
Consumer đã nhận event
Order O100 không tồn tại
```

### 15.3. Gọi hai nơi trong try/catch chưa sửa được

```java
try {
    db.save(order);
    broker.publish(event);
} catch (Exception e) {
    // rollback?
}
```

Một `catch` không thể hoàn tác transaction đã commit hoặc message đã đến consumer.

### 15.4. Kiến trúc cần giải quyết

- Làm sao atomically ghi state và **ý định phát event**?
- Làm sao publish sau lỗi?
- Làm sao consumer xử lý event trùng?
- Làm sao bảo toàn thứ tự theo aggregate?
- Làm sao đối soát giữa nguồn và projection?

Đây là lý do transactional outbox được sử dụng nhiều.

## 16. Transactional outbox: ghi state và intent cùng transaction

**Transactional outbox** đặt một event record ngay trong database nguồn, thuộc cùng local transaction với thay đổi aggregate.

```text
Order Service
      |
      v
Local DB Transaction
   +-- Update Order O100
   +-- Insert Outbox E100
      |
      v
    COMMIT
      |
      v
Outbox Relay/CDC ---> Message Broker ---> Consumers
```

Nếu transaction abort, không có Order change cũng không có outbox event. Nếu commit thành công, event intent đã được lưu bền trong cùng scope.

### 16.1. Outbox schema minh họa

```json
{
  "eventId": "E100",
  "aggregateType": "Order",
  "aggregateId": "O100",
  "aggregateVersion": 3,
  "type": "OrderCreated",
  "payload": {
    "orderId": "O100",
    "userId": "U42"
  },
  "createdAt": "2026-11-14T10:00:00Z",
  "publishStatus": "PENDING"
}
```

### 16.2. Ba điều kiện bắt buộc

1. Aggregate write và outbox insert **thật sự nằm trong cùng local transaction scope**.
2. Relay có cơ chế đọc/retry để event chưa publish không bị bỏ quên.
3. Consumer xử lý duplicate/idempotency vì relay có thể publish lại.

### 16.3. Nếu NoSQL không có transaction hai items?

Có thể cân nhắc:

- Lưu pending event trong cùng một atomic aggregate document/item.
- Sử dụng native transaction API nếu hỗ trợ.
- CDC từ thay đổi chính đã được commit làm source event.
- Đổi model để Order và Outbox có thể cùng logical partition với batch atomic.
- Dùng một durable local state machine khác.

Không được lưu Order ở partition A và outbox ở partition B bằng hai `PUT` vô điều kiện rồi gọi đó là transactional outbox.

### 16.4. Outbox giải quyết điều gì?

Outbox giải quyết **khoảng trống atomicity giữa source DB state và source event intent**. Nó **không** tự làm consumer cập nhật Inventory/Payment ngay lập tức hoặc không bao giờ nhận trùng.

## 17. Outbox relay: publish thành công nhưng chưa đánh dấu DONE

Một relay đọc outbox và gửi event:

```text
T0: Relay đọc E100 PENDING
T1: Broker nhận và xác nhận E100
T2: Relay crash trước khi ghi E100 PUBLISHED
T3: Relay restart, đọc E100 PENDING
T4: Publish lại E100
```

Consumer có thể nhận E100 **hai lần**.

Nếu relay đảo thứ tự:

```text
T1: Mark E100 PUBLISHED
T2: Publish E100
```

crash giữa hai bước có thể làm event **mất vĩnh viễn** khỏi đường publish.

### 17.1. Chấp nhận at-least-once và chống trùng

Một thiết kế phổ biến ưu tiên khả năng publish lại, rồi consumer dùng idempotency để xử lý nhiều lần mà không tạo business effect trùng.

### 17.2. Relay polling hoặc CDC

Có hai hướng:

- **Polling:** đọc pending events theo lịch/lease, publish, cập nhật trạng thái.
- **CDC/log tailing:** đọc commit log/change stream từ database để đẩy sự kiện.

Mỗi cách cần checkpoint, retry, backpressure, retention và quan sát lag.

### 17.3. Không dùng flag PUBLISHED như nguồn sự thật duy nhất về consumer

Event được broker ACK không chứng minh tất cả consumers đã xử lý thành công. Cần consumer offsets/inbox/processing status riêng.

## 18. Java + MongoDB: outbox cùng một transaction

Giả định collections `orders` và `outbox` nằm trong cùng MongoDB deployment có transaction support, session được truyền cho mọi thao tác.

```java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public final class OrderWriter {
    private final MongoClient client;
    private final MongoCollection<Document> orders;
    private final MongoCollection<Document> outbox;

    public OrderWriter(
            MongoClient client,
            MongoCollection<Document> orders,
            MongoCollection<Document> outbox
    ) {
        this.client = client;
        this.orders = orders;
        this.outbox = outbox;
    }

    public void create(String orderId, String operationId) {
        try (ClientSession session = client.startSession()) {
            session.withTransaction(() -> {
                orders.insertOne(
                        session,
                        new Document("_id", orderId)
                                .append("operationId", operationId)
                                .append("status", "PENDING")
                                .append("version", 1L)
                );

                outbox.insertOne(
                        session,
                        new Document("_id", "evt:" + orderId + ":v1")
                                .append("aggregateId", orderId)
                                .append("aggregateVersion", 1L)
                                .append("type", "OrderCreated")
                                .append("publishStatus", "PENDING")
                );

                return null;
            });
        }

        // Không gửi payment hoặc broker message
        // bên trong callback có thể bị retry.
    }
}
```

Cần có unique index phù hợp cho `operationId` và xử lý duplicate-key/retry bằng cách đọc outcome đã ghi. Ví dụ không mô tả đủ transaction options, server version, write concern, schema và production error handling.

### 18.1. Vì sao không publish trong callback?

Driver có thể retry transaction body khi gặp transient error. Nếu callback gọi payment provider, một lần retry có thể **charge hai lần** dù transaction DB chỉ commit một lần.

### 18.2. Tại sao eventId ổn định?

Relay publish E100 nhiều lần thì consumer vẫn nhận diện đó là **cùng một event**, không tạo event mới với UUID khác trong mỗi lần publish.

### 18.3. Nếu commit outcome unknown?

Không tạo Order mới với id mới ngay; tra `operationId`/`orderId` trước và retry theo semantics transaction API.

## 19. Transactional inbox: consumer xử lý event nhiều lần vẫn an toàn

**Inbox/deduplication record** giúp consumer nhận biết một event đã được xử lý.

```text
Message Broker
      |
      v
Inventory Consumer
      |
      v
Local Transaction
  +-- Insert Inbox(eventId=E100) if absent
  +-- Reserve Inventory
  +-- Insert Outbox(InventoryReserved)
      |
      v
COMMIT
      |
      v
ACK message
```

Nếu consumer crash sau local commit nhưng trước broker ACK, message được giao lại. Khi xử lý lại, `Inbox(E100)` đã tồn tại nên không thực hiện reserve lần nữa.

### 19.1. Dedupe marker và business write phải atomic

Nếu viết Inbox trước rồi Inventory update sau, crash giữa hai bước khiến event bị đánh dấu xử lý nhưng không giữ hàng.

Nếu Inventory update trước rồi ghi Inbox sau, crash có thể giữ hàng hai lần.

### 19.2. Khi NoSQL chỉ atomic một item

Có thể tích hợp `lastProcessedEventIds` hoặc aggregate version vào item cần mutate, nếu capacity và retention cho phép, hoặc dùng native multi-item transaction. Không dùng một marker lưu riêng ngoài transaction rồi tuyên bố exactly-once processing.

### 19.3. Inbox chỉ chống trùng trong phạm vi được thiết kế

Nếu eventId bị tái sử dụng cho event khác, hoặc dedupe TTL hết trước retry window, duplicate có thể được xử lý lại. Phải chọn retention và identity theo yêu cầu nghiệp vụ.

### 19.4. External side effect vẫn cần idempotency riêng

Inbox trong Order DB không tự ngăn payment provider charge hai lần nếu process crash giữa provider response và local Inbox commit. Cần payment idempotency ở provider.

## 20. Vì sao “exactly once” thường là khẩu hiệu nguy hiểm?

Một hệ thống có thể cung cấp exactly-once trong **một phạm vi cụ thể**, chẳng hạn transaction log + state store của một framework hoặc một database transaction.

Nhưng **end-to-end exactly-once** qua:

```text
Client -> API -> DB -> Broker -> Consumer -> Payment Provider
```

không tự có chỉ vì broker có exactly-once mode.

### 20.1. Các điểm phát sinh duplicate

- HTTP client retry;
- Load balancer retry;
- Producer publish lại;
- Broker redelivery;
- Consumer crash sau commit;
- Worker lease hết rồi chạy lại;
- Webhook provider gửi lại;
- Timeout không biết external effect đã thành công.

### 20.2. Cách đạt “effectively once” theo nghiệp vụ

- Idempotency key ổn định theo operation.
- Atomic state transition tại authority.
- Unique constraint/conditional create.
- Inbox/outbox và durable retry.
- Version guard ở projections.
- Provider-side idempotency.
- Reconciliation và audit.

Hợp đồng nên nói rõ **business effect nào không được lặp**, thay vì dùng một nhãn exactly-once không có phạm vi.

## 21. Saga: một giao dịch nghiệp vụ gồm nhiều local transactions

**Saga** là một chuỗi local transactions được điều phối bằng commands/events; khi có lỗi, hệ dùng **compensating actions** và state machine để đưa workflow về trạng thái nghiệp vụ chấp nhận được.

Ví dụ checkout:

```text
Order Service         Inventory Service        Payment Service
     |                       |                        |
     |-- Create PENDING ---->|                        |
     |                       |                        |
     |---- Reserve --------->|                        |
     |<--- Reserved ---------|                        |
     |                                                |
     |---------------- Authorize Payment ------------>|
     |<--------------- Authorized --------------------|
     |                                                |
     |-- Confirm Order                                |
     |-- Publish OrderConfirmed                       |
```

Mỗi mũi tên có thể kéo dài, timeout, duplicate hoặc out-of-order. Không được coi sơ đồ là một call stack có atomic rollback.

### 21.1. Saga không phải transaction ACID toàn cục

Một saga có thể đi qua:

```text
PENDING -> RESERVED -> PAYMENT_AUTHORIZED -> CONFIRMED
```

Trong thời gian đó, các services có thể nhìn các trạng thái trung gian hợp lệ.

### 21.2. Quy tắc về trạng thái trung gian

Một Order `PENDING_PAYMENT` không được bị giao hàng như `CONFIRMED`. Một inventory hold cần thời hạn hoặc điều kiện release. Một payment `UNKNOWN` không được tự coi là `FAILED`.

### 21.3. Đảm bảo từng bước

Mỗi local step cần:

- Idempotency;
- Atomic local mutation;
- Một message/response bền vững;
- Timeout/retry policy;
- Expected state/version check;
- Audit trail;
- Compensation/recovery path.

## 22. Saga choreography: các dịch vụ phản ứng theo events

Trong **choreography**, không có một service trung tâm trực tiếp điều khiển toàn bộ; mỗi service phản ứng với events.

```text
OrderCreated
     |
     v
Inventory Service
     |
     +-- InventoryReserved
                  |
                  v
             Payment Service
                  |
                  +-- PaymentAuthorized
                              |
                              v
                         Order Service
                              |
                              +-- OrderConfirmed
```

Nếu hết hàng:

```text
InventoryRejected -> Order Service -> OrderCancelled
```

### 22.1. Ưu điểm

- Services tương đối độc lập;
- Dễ thêm read models/subscribers;
- Event-driven phù hợp với nhiều workflows đơn giản;
- Không cần synchronous call chain dài.

### 22.2. Nhược điểm

- Workflow phân tán khó nhìn tổng thể.
- Dễ tạo event loops.
- Business logic bị trải khắp services.
- Thay đổi trạng thái cần phối hợp nhiều teams.
- Debug timeline, retries và compensation phức tạp.
- Có nguy cơ một event không có consumer chịu trách nhiệm.

### 22.3. Khi phù hợp?

Một workflow ít bước, trách nhiệm rõ, events ổn định, ít nhánh và ít compensation có thể phù hợp choreography.

Không nên dùng choreography chỉ vì muốn “mọi thứ là microservices events”, bất kể domain complexity.

## 23. Saga orchestration: coordinator quản lý tiến độ

Trong **orchestration**, một saga orchestrator giữ trạng thái workflow và gửi commands đến services.

```text
                   Saga Orchestrator
                         |
         +---------------+----------------+
         |               |                |
         v               v                v
  Reserve Inventory  Authorize Payment  Confirm Order
         |               |                |
      Reply           Reply            Reply
         \               |                /
          +--------------+---------------+
```

Ví dụ state:

```json
{
  "sagaId": "checkout:O100",
  "orderId": "O100",
  "state": "PAYMENT_AUTHORIZATION_PENDING",
  "stepVersion": 4,
  "inventoryReservationId": "R100",
  "paymentIntentId": "PI100",
  "retryCount": 1,
  "deadlineAt": "2026-11-14T10:10:00Z"
}
```

### 23.1. Ưu điểm

- Có một nơi mô tả workflow.
- Dễ nhìn trạng thái, deadline và compensation.
- Phù hợp với nhánh phức tạp.
- Có thể kiểm thử state machine rõ ràng.
- Dễ theo dõi retries và audit.

### 23.2. Đánh đổi

- Orchestrator là thành phần quan trọng cần HA và durable state.
- Dễ thành coupling trung tâm nếu chứa business logic của mọi service.
- Commands/replies cần idempotent.
- Không được cho phép hai orchestrator instances cùng điều khiển saga sai thứ tự.

### 23.3. Orchestrator không phải distributed transaction manager

Một coordinator gửi commands theo state machine không làm Order/Inventory/Payment cùng commit atomically. Nó giúp **duy trì tiến độ và phục hồi** của quy trình nhiều local commits.

## 24. Thiết kế trạng thái Saga checkout

Một state machine minh họa:

```text
NEW
  |
  v
INVENTORY_PENDING
  |                \
  | RESERVED        \ REJECTED
  v                  v
PAYMENT_PENDING     CANCELLING
  |      \              |
  |       \ UNKNOWN      v
  |        v           CANCELLED
  |    PAYMENT_UNKNOWN
  |        |
  |    reconcile provider
  |        |
  | AUTHORIZED
  v
CONFIRMING
  |
  v
CONFIRMED
```

Một số transitions cần compensation:

```text
PAYMENT_DECLINED
      |
      v
RELEASE_INVENTORY_PENDING
      |
      v
CANCELLED
```

### 24.1. Trạng thái phải mang nghĩa nghiệp vụ

- `PENDING`: đang xử lý, chưa hứa kết quả cuối.
- `RESERVED`: đã giữ tài nguyên theo một hold có identifier/expiration.
- `AUTHORIZED`: provider đã chấp nhận authorization theo contract.
- `CAPTURED`: tiền đã thực sự được capture theo contract.
- `CONFIRMED`: đủ điều kiện nghiệp vụ để xác nhận.
- `CANCELLED`: không thực hiện tiếp và các bước bù đã được quản lý.
- `PAYMENT_UNKNOWN`: không biết provider đã xử lý hay chưa.
- `MANUAL_REVIEW`: cần con người vì tự động không thể xác minh.

### 24.2. Không dùng một boolean duy nhất

`success=true/false` không đủ biểu diễn một saga có thể bị chặn ở bước bù, payment unknown hoặc inventory hold sắp hết hạn.

### 24.3. Version cho state transitions

Mỗi transition nên kiểm tra `(sagaId, expectedState, expectedVersion)` tại authority để duplicate/stale handlers không chuyển saga lùi trạng thái.

## 25. Saga checkout từng bước có idempotency

Một thiết kế có thể dùng các bước:

### Bước 1 — Tạo Order intent

Order Service ghi Order `PENDING` và outbox `OrderCreated` trong cùng local transaction. Có unique `checkoutOperationId`.

### Bước 2 — Giữ tồn kho

Inventory Service nhận `ReserveInventory` với `reservationId=R100`:

```text
IF reservationId đã xử lý:
    RETURN recorded result
ELSE IF available >= quantity:
    decrement available
    create hold R100 with expiresAt
    emit InventoryReserved
ELSE:
    emit InventoryRejected
```

Mutation Inventory, hold record và outbox/inbox phải atomic trong scope hỗ trợ.

### Bước 3 — Payment authorize

Payment Service gọi provider với **idempotency key ổn định** như `payment:O100:authorize:v1`.

Nếu provider trả timeout, giữ `PAYMENT_UNKNOWN`, truy vấn provider/webhook trước khi retry hoặc bù.

### Bước 4 — Xác nhận Order

Khi đã biết hold hợp lệ và payment authorization thành công, Order chuyển `CONFIRMED` theo CAS và ghi outbox `OrderConfirmed`.

### Bước 5 — Capture payment theo chính sách

Một số hệ capture sau khi xác nhận/giao hàng; một số capture ngay. Cần định nghĩa rõ khi nào tiền thực được giữ và khi nào có thể void/refund.

### Bước 6 — Hủy khi cần

Khi hết hàng hoặc payment declined, orchestrator gửi `ReleaseInventory(R100)`, `VoidAuthorization(PI100)` nếu cần và chuyển Order về trạng thái hủy khi các bước bù được xác minh.

### 25.1. Một hold phải có deadline

Nếu saga crash sau InventoryReserved, reservation không nên giữ hàng vô hạn. Hold expiry/sweeper hoặc recovery worker phải biết deadline và kiểm tra trạng thái trước khi release.

### 25.2. Một release phải idempotent

Gửi `ReleaseInventory(R100)` hai lần không được cộng `available` hai lần. Authority nên lưu reservation state:

```text
R100:
  HELD -> RELEASED
  RELEASED -> RELEASED (duplicate/no-op)
```

### 25.3. Late success phải được xử lý

Payment authorization success có thể đến sau khi saga bắt đầu hủy. Không được tự chuyển Order đã CANCELLED thành CONFIRMED chỉ vì event success tới muộn; cần state guard và void/refund nếu cần.

## 26. Compensation không phải rollback vật lý

Trong local transaction, rollback có thể khiến mutations chưa commit không được công bố.

Trong Saga, **compensation** là một business operation mới để sửa tác động của một bước đã commit.

Ví dụ:

- `ReserveInventory` → `ReleaseInventory`.
- `AuthorizePayment` → `VoidAuthorization` nếu provider hỗ trợ và authorization chưa capture.
- `CapturePayment` → `RefundPayment`; đây là một nghiệp vụ mới, không xóa charge lịch sử.
- `BookShipment` → `CancelShipment` nếu chưa bàn giao; sau khi hàng đã gửi có thể phải tạo return workflow.
- `SendEmail` → không thể “unsend”; có thể gửi email đính chính.

### 26.1. Compensation có thể thất bại

Một bước bù có thể timeout, provider bị lỗi hoặc tài nguyên đã thay đổi. Saga phải có `COMPENSATION_PENDING`, retries, alert và manual resolution.

### 26.2. Không giả định thao tác bù là phép nghịch đảo toán học

Nếu reservation được giữ rồi TTL đã giải phóng, một `Release` đến muộn không được cộng tồn kho thêm lần nữa.

### 26.3. Compensation cần version/identity

Đừng chỉ làm `available += 1` khi thấy event `OrderCancelled`. Phải release **đúng reservationId** nếu reservation còn HELD.

### 26.4. Irreversible steps nên đặt cuối khi có thể

Email công khai, vận chuyển hàng, capture không thể void, chuyển quyền sở hữu pháp lý... thường nên xảy ra sau những bước dễ hủy, hoặc có quy trình bù nghiệp vụ rõ.

## 27. TCC: Try–Confirm–Cancel

**Try–Confirm–Cancel (TCC)** là một mẫu phối hợp với ba thao tác nghiệp vụ:

1. **Try:** đặt trước/giữ tài nguyên.
2. **Confirm:** chốt quyền sử dụng.
3. **Cancel:** giải phóng phần giữ nếu không chốt.

Ví dụ:

```text
Try Inventory R100    -> Hold 1 item
Try Payment PI100     -> Authorize amount
Confirm Inventory     -> Convert hold to allocated
Confirm Payment       -> Capture if policy requires
```

Nếu workflow không thể tiến hành:

```text
Cancel Inventory R100
Cancel Payment PI100 (void authorization)
```

### 27.1. Vì sao TCC giúp hơn blind steps?

Bởi các bước Try tạo **reservation có thể hủy**, giảm nguy cơ đã thực hiện tác động không thể đảo ngược trước khi biết các điều kiện còn lại.

### 27.2. TCC không tự bảo vệ giao dịch toàn cục

Các services vẫn thực thi local state transitions riêng. Try/Confirm/Cancel phải idempotent, chịu timeout, có expiration/fencing và recovery.

### 27.3. Confirm sau hold hết hạn

Nếu hold R100 hết hạn lúc 10:05 mà Confirm đến 10:06, Inventory phải kiểm tra trạng thái/deadline. Không được confirm dựa vào một event cũ trong cache.

### 27.4. TCC và Saga

TCC là một cách cấu trúc các bước với reservation semantics; nó có thể được sử dụng **bên trong một Saga** hoặc một workflow điều phối tương tự.

## 28. 2PC: tại sao không mặc định dùng để nối mọi microservices?

**Two-Phase Commit (2PC)** là một giao thức atomic commit gồm:

1. **Prepare:** coordinator yêu cầu các participants chuẩn bị commit, giữ trạng thái cần thiết và bỏ phiếu.
2. **Commit/Abort:** coordinator đưa ra quyết định cuối và thông báo tới participants.

Sơ đồ:

```text
             Coordinator
             /          \
            v            v
         DB A           DB B
        PREPARE        PREPARE
           |              |
          YES            YES
            \            /
             v          v
              COMMIT decision
             /          \
            v            v
         COMMIT          COMMIT
```

### 28.1. Khác Saga

- 2PC hướng tới **atomic commit** của các participants hỗ trợ giao thức.
- Saga chấp nhận **nhiều local commits** và dùng compensation/recovery để đạt trạng thái nghiệp vụ phù hợp.

### 28.2. Những trở ngại thực tế

- Các participants phải hỗ trợ protocol/transaction enlistment.
- HTTP payment provider thường không tham gia XA/2PC.
- Có thể giữ locks/resources trong thời gian prepare.
- Một số triển khai 2PC có tính blocking khi coordinator lỗi.
- Network partitions làm availability và latency xấu đi.
- Multi-region coordination có thể tốn kém.

### 28.3. 2PC không phải consensus

2PC giải quyết atomic commit theo một mô hình coordinator/participants; consensus quyết định giá trị/log với mô hình lỗi khác. Có hệ kết hợp replicated transaction coordinator với consensus để nâng khả năng phục hồi.

### 28.4. Khi nào 2PC có thể thích hợp?

Một hệ kiểm soát cả participants, có hỗ trợ transactions phân tán chính thức, nghiệp vụ cần atomicity mạnh và chấp nhận chi phí coordination có thể cân nhắc. **Không tự thay thế mọi workflow bằng 2PC**, cũng không loại trừ nó theo khẩu hiệu.

## 29. Bảng chọn local transaction, Saga, TCC và 2PC

| Trường hợp | Hướng thường hợp lý | Lưu ý |
|---|---|---|
| Một item Inventory cần giảm nếu còn hàng | Atomic conditional update | Thử concurrency và stale version |
| Order + Outbox cùng một database hỗ trợ transaction | Local transaction | Relay/consumer vẫn at-least-once |
| Nhiều rows cùng logical partition Cosmos DB | Transactional batch | Không mở rộng sang partition khác |
| MongoDB nhiều documents trong một deployment | Native transaction | Đừng gọi API ngoài trong callback |
| Cassandra một claim với `IF NOT EXISTS` | LWT/conditional operation | Đừng dùng logged batch thay CAS |
| Order–Inventory–Payment qua ba services | Saga/orchestrated workflow | Trạng thái trung gian/compensation |
| Tài nguyên có thể hold trước commit | TCC/reservation | Expiration và idempotent cancel |
| Các database participants hỗ trợ atomic commit protocol | Có thể xét distributed transaction/2PC | Latency/blocking/coordination |
| Cập nhật search từ source DB | Outbox/CDC + projector | Version guard và reconciliation |
| Gửi email sau commit Order | Async notification qua outbox | Email không rollback được |
| Payment kết quả unknown | Status query/reconciliation + idempotency | Không tự chuyển unknown thành failed |

Không có một pattern phù hợp toàn bộ domain; thường dùng **local ACID bên trong service, Saga hoặc TCC giữa services, outbox/inbox tại biên tích hợp**.

## 30. Idempotency từ HTTP tới database và provider

Một request idempotent theo nghiệp vụ là request lặp lại với **cùng ý định** không tạo thêm business effect.

### 30.1. HTTP request idempotency key

```http
POST /checkout
Idempotency-Key: checkout-user42-cart9-v1
Content-Type: application/json

{
  "cartId": "C9",
  "shippingAddressId": "A7"
}
```

Backend lưu identity:

```json
{
  "operationId": "checkout-user42-cart9-v1",
  "requestHash": "sha256:...",
  "status": "PROCESSING",
  "orderId": "O100",
  "resultCode": null
}
```

### 30.2. Phải có unique/conditional create

Hai concurrent requests với cùng key:

```text
Request A: if not exists -> create operation
Request B: if not exists -> condition fails/read existing
```

Nếu cả hai chỉ `find` rồi `insert` không có unique guard, có race.

### 30.3. Cùng key, khác payload

Nếu client tái sử dụng idempotency key cho hai giỏ hàng khác nhau, backend không được im lặng trả kết quả của request cũ hoặc tạo hai orders. So payload fingerprint và trả lỗi phù hợp.

### 30.4. Response replay

Sau khi operation đã hoàn thành, retry cùng key nên trả **kết quả cũ** hoặc đường dẫn tới resource đã tạo, tùy API contract.

### 30.5. Window và retention

Provider idempotency keys, API tokens và Inbox markers có thể có TTL khác nhau. Cần chọn retention phù hợp thời gian retry, webhook delay và chính sách dispute; không để một key hết hạn quá sớm rồi tạo tác động trùng.

### 30.6. Dedupe event khác idempotency business

`eventId` nhận diện một message; `operationId` nhận diện một ý định nghiệp vụ; `paymentIntentId` nhận diện giao dịch tại provider. Một business operation có thể sinh nhiều events, nên không được trộn mọi identity thành một UUID không rõ scope.

## 31. Retry policy: khi nào nên thử lại?

Mọi hệ phân tán đều có transient failures, nhưng retry vô điều kiện có thể làm lỗi nặng hơn.

### 31.1. Retry nên có

- Exponential backoff;
- Jitter;
- Retry budget;
- Deadline;
- Idempotency;
- Phân loại lỗi transient/permanent;
- Circuit breaker hoặc admission control khi cần;
- Logging/tracing cùng operation ID.

### 31.2. Không retry lỗi nghiệp vụ như lỗi mạng

Ví dụ:

| Kết quả | Hướng xử lý |
|---|---|
| Inventory condition failed vì hết hàng | Trả `OUT_OF_STOCK`; không retry vô hạn |
| Order version mismatch | Reload và đánh giá state; conflict |
| Network timeout tới provider | Truy vấn/reconcile theo payment intent |
| Broker tạm unavailable | Giữ outbox, retry có backoff |
| Payload schema invalid | Dead letter/quarantine, sửa producer/consumer |
| Rate limited | Retry-After/backoff nếu phù hợp |
| Duplicate operation ID | Trả kết quả đã có, không thực hiện lại |
| Unauthorized | Không retry với cùng quyền sai |

### 31.3. Retry storm

```text
Database chậm
  -> requests timeout
  -> clients retry x3
  -> queue tăng
  -> database càng chậm
```

Idempotency giữ tính đúng nhưng **không tự giới hạn tải**. Cần backpressure, bounded queues và rate limits.

## 32. Unknown outcome: timeout không chứng minh giao dịch thất bại

Một payment flow:

```text
T0: Payment Service gọi provider Authorize(PI100)
T1: Provider authorize thành công
T2: HTTP response bị mất
T3: Payment Service nhận timeout
```

Tại T3, trạng thái là **UNKNOWN**, không phải chắc chắn DECLINED.

### 32.1. Vì sao retry bằng request mới nguy hiểm?

Nếu tạo payment intent mới rồi charge tiếp, khách có thể bị charge hai lần.

### 32.2. Quy trình phù hợp

1. Lưu `paymentIntentId`/idempotency key bền vững trước khi gọi.
2. Dùng cùng key khi retry theo hợp đồng provider.
3. Nếu timeout, query provider status hoặc chờ webhook có chữ ký.
4. Ghi trạng thái kết quả bằng local transaction.
5. Nếu vẫn không xác minh được, giữ `MANUAL_REVIEW`/`UNKNOWN`.
6. Không confirm hoặc refund một cách đoán mò.

### 32.3. Unknown commit của database

Tương tự, transaction commit có thể thành công nhưng ACK bị mất. Dùng operation ID và query state trước khi tạo transaction mới.

## 33. Ordering: không cần một total order cho toàn hệ

Trong event-driven architecture, thường cần **thứ tự theo aggregate** hơn là thứ tự global cho mọi dữ liệu.

```text
Order O100:
  v1 OrderCreated
  v2 InventoryReserved
  v3 PaymentAuthorized
  v4 OrderConfirmed

Order O101:
  v1 OrderCreated
  v2 InventoryRejected
```

Không cần so O100:v4 với O101:v2 để quyết định cái nào “mới hơn toàn hệ”.

### 33.1. Out-of-order delivery

Consumer nhận O100:v4 trước v3:

- Có thể buffer chờ v3;
- Có thể query authoritative latest state;
- Có thể bỏ qua event cũ khi projection chỉ cần snapshot mới nhất;
- Có thể yêu cầu replay missing sequence.

Lựa chọn phụ thuộc event semantics.

### 33.2. Version guard

Một projection lưu `(aggregateId, lastAppliedVersion)`. Khi nhận event cũ, không ghi đè state mới.

```text
current v4
incoming v3
-> ignore as stale
```

Nếu event là **delta** cần tính lần lượt, nhận v4 trước v3 có thể cần chờ gap chứ không đơn giản áp v4.

### 33.3. Broker key theo aggregate

Có thể route events cùng `aggregateId` vào cùng partition/ordering lane nếu broker hỗ trợ. Nhưng scale, re-partition, retry và multiple producers vẫn cần contract về thứ tự.

### 33.4. Tombstone projection

Nếu event `OrderDeleted:v6` được áp dụng, event `OrderUpdated:v5` đến muộn không được tái tạo document. Giữ marker/version theo retention policy.

## 34. Domain event khác integration command

**Command:** yêu cầu một service thực hiện một việc, ví dụ `ReserveInventory(R100)`.

**Event:** thông báo một sự thật đã được commit tại authority, ví dụ `InventoryReserved(R100)`.

Không nên publish `InventoryReserved` **trước khi Inventory thật sự commit**.

### 34.1. Commands có thể bị từ chối

`ReserveInventory` có thể trả `InventoryRejected`; command không phải lời cam kết nó sẽ thành công.

### 34.2. Events nên biểu diễn trạng thái nguồn đã được xác nhận

Một event có thể là:

```json
{
  "eventId": "inventory-R100-v3",
  "type": "InventoryReserved",
  "aggregateId": "P100",
  "aggregateVersion": 3,
  "reservationId": "R100",
  "orderId": "O100"
}
```

### 34.3. Hợp đồng schema

Cần versioned schema, backward compatibility và phân biệt `null`, missing fields, default values. Consumer cũ không được biến event mới thành business mutation sai.

### 34.4. Không nhồi toàn bộ database schema vào event

Integration events nên mang những dữ liệu cần cho các consumers, có version và ownership rõ, tránh coupling bất biến giữa microservices.

## 35. CDC và event sourcing có vai trò khác

### 35.1. Change Data Capture

**CDC** đọc thay đổi đã commit ở nguồn qua change stream/log để đẩy sang hệ khác. Nó có thể giảm dual write, nhưng cần:

- Checkpoint;
- Replay;
- Ordering;
- Snapshot/backfill;
- Deduplication;
- Retention của change log;
- Recovery khi connector downtime lâu.

### 35.2. Transactional outbox với CDC

Có thể lưu outbox records trong DB, rồi dùng CDC để publish. Khi đó **source mutation và intent nằm trong cùng local transaction**, CDC chuyển intent ra broker.

### 35.3. Event sourcing

Trong event sourcing, **event log là nguồn state authoritative**, còn aggregate state/projections được dựng lại từ events.

Event sourcing không đồng nghĩa transactional outbox. Một hệ outbox thông thường vẫn có state documents/tables là nguồn chính và outbox chỉ là integration intent.

### 35.4. Event sourcing cũng có concurrency

Append event cần expected stream version hoặc authority để tránh hai commands cùng viết dựa trên một aggregate version. Replay cần deterministic state transitions; external side effects không chạy lại mù quáng khi rebuild projections.

## 36. Data ownership: không cho các services ghi chéo database tùy ý

Một kiến trúc microservices nên xác định owner của từng aggregate.

```text
Order Service      owns Order DB
Inventory Service  owns Inventory DB
Payment Service    owns Payment DB
```

Order Service không nên tự sửa trực tiếp `inventory.available` trong database của Inventory Service chỉ để “làm nhanh”, vì:

- Bỏ qua invariant mà Inventory Service kiểm soát.
- Schema thay đổi gây coupling.
- Mất audit và version guard.
- Khó theo dõi quyền truy cập.
- Không biết khi nào Inventory đã xử lý events/compensations.
- Có thể phá local transaction của service chủ sở hữu.

### 36.1. API/command boundary

Order gửi command với `reservationId`, Inventory thực thi điều kiện nguyên tử tại DB nó sở hữu và trả event/result.

### 36.2. Read models không phải nguồn ghi

Order có thể có projection sản phẩm/giá để hiển thị, nhưng không dùng bản copy eventual ấy để xác nhận inventory cuối cùng.

### 36.3. Một shared database chưa chắc sai, nhưng phải rõ ownership

Nếu nhiều services chia sẻ cùng database và cùng một transaction manager, cần quản lý schema, locking và contract. Đừng gọi đó là microservices độc lập chỉ vì có nhiều HTTP endpoints.

## 37. Eventual consistency: cần hợp đồng UX, không chỉ cấu hình

Sau khi checkout tạo Order PENDING, Inventory/Payment có thể chưa hoàn tất trong vài giây.

UI nên thể hiện:

```json
{
  "orderId": "O100",
  "status": "PROCESSING",
  "nextAction": "POLL_OR_SUBSCRIBE",
  "retryAfterSeconds": 2
}
```

Chỉ khi Order đã đạt business commit `CONFIRMED` mới trả thông báo xác nhận cuối.

### 37.1. Đọc từ đâu?

- Order detail từ authoritative Order Service.
- Search/order history từ projection có thể lag.
- Payment status từ Payment Service/provider.
- Inventory count từ Inventory authority ở checkout.

Không nên dùng Search index để quyết định order được giao hay chưa.

### 37.2. Read-your-writes

Client có thể cần thấy một Order PENDING vừa tạo ngay cả khi global search chưa index. Đường GET theo ID nên route tới authority hoặc dùng session token/freshness guarantee phù hợp.

### 37.3. Freshness watermark

Một projection có thể hiển thị:

```text
Dữ liệu cập nhật đến event offset 81042
Delay dự kiến: vài giây
```

Các chỉ số phải đo thực tế; không hứa “real time” khi pipeline chưa có SLO.

### 37.4. Thất bại kéo dài

Sau một deadline, hệ cần chuyển `PROCESSING` sang `MANUAL_REVIEW` hoặc trạng thái lỗi có thể phục hồi, không để UI quay spinner vô hạn.

## 38. Timeouts và deadlines phải là một phần của state

Một saga đang chờ InventoryReserved có thể bị treo nếu message bị mất hoặc consumer down.

Không thể chỉ dùng sleep hoặc timeout của một HTTP thread.

### 38.1. Deadline bền vững

```json
{
  "sagaId": "checkout:O100",
  "state": "INVENTORY_PENDING",
  "deadlineAt": "2026-11-14T10:05:00Z"
}
```

Một scheduled recovery worker có thể quét những saga đã quá hạn và kiểm tra state.

### 38.2. Kiểm tra trước khi hủy

Nếu reply `InventoryReserved` đến chậm, timeout không chứng minh reservation chưa được tạo. Recovery phải hỏi Inventory theo `reservationId`, hoặc gửi một idempotent cancel có semantics rõ.

### 38.3. Không xóa dữ liệu chỉ vì request timeout

Một Order chưa có response nhưng payment đã thành công cần được reconcile. Blind delete Order có thể làm mất audit trail để xử lý refund.

### 38.4. Cleanup cũng phải idempotent

Nhiều workers có thể cùng phát hiện một expired hold. Conditional transition `HELD -> EXPIRED` một lần tại authority giúp tránh cộng tồn kho nhiều lần.

## 39. Observability: một transaction nghiệp vụ có nhiều transaction IDs

Những identifiers nên giữ xuyên dịch vụ:

```text
checkoutOperationId = C100
orderId             = O100
sagaId              = S100
reservationId       = R100
paymentIntentId     = PI100
eventId             = E100, E101, ...
traceId             = T100
```

Chúng phục vụ mục đích khác nhau, không phải tất cả cùng một transaction ID.

### 39.1. Metrics cần quan sát

| Nhóm | Metric gợi ý | Câu hỏi |
|---|---|---|
| Saga progression | Số saga theo state và tuổi state | Workflow kẹt ở đâu? |
| End-to-end latency | p50/p95/p99 thời gian từ intent tới CONFIRMED | User chờ bao lâu? |
| Outbox | Pending count, oldest age, publish failures | Có event chưa gửi? |
| Inbox | Duplicates skipped, processing retries | Consumers có redelivery nhiều? |
| Inventory | Active holds, expired holds, double-release prevention | Có giữ hàng thất lạc? |
| Payment | UNKNOWN count, reconciliation lag, duplicate attempts | Có rủi ro charge trùng? |
| Compensation | Pending/failed compensation | Có resource chưa được giải phóng? |
| Broker | Lag, DLQ age, retry rate | Pipeline có tắc? |
| DB | Conditional failures, transaction aborts, lock/conflict | Authority có contention? |
| Business | Oversell, orphan payment, confirmed-without-reservation | Invariant có sai? |
| Read model | Projection lag, version gaps | UI/search có stale? |
| Recovery | Age of unresolved operations | Có trường hợp cần xử lý thủ công? |

### 39.2. Alert theo hậu quả

Alert có ích khi chỉ rõ **việc cần làm**:

- Saga PAYMENT_UNKNOWN vượt deadline;
- Outbox oldest event vượt SLO;
- Inventory hold quá hạn nhưng chưa release;
- Payment captured mà Order không CONFIRMED;
- Đơn CONFIRMED không có reservation hợp lệ;
- DLQ chứa event schema không thể xử lý;
- Compensation failure kéo dài.

### 39.3. Log an toàn

Không log full card PAN, tokens, PII hoặc secrets. Log IDs, versions, state transitions và sanitized error codes để điều tra.

## 40. Một ma trận lỗi phải được diễn tập

| Điểm lỗi | Trạng thái khả dĩ | Hướng phục hồi |
|---|---|---|
| Crash trước local transaction commit | Không có mutation/outbox | Client retry cùng operation ID |
| Crash sau commit, trước HTTP response | Operation có thể đã commit | Query theo idempotency key |
| Crash sau DB commit, trước broker publish | Outbox còn PENDING | Relay retry |
| Crash sau broker ACK, trước mark published | Event có thể tới hai lần | Consumer Inbox/dedupe |
| Consumer crash sau local commit, trước broker ACK | Redelivery | Local Inbox + aggregate mutation atomic |
| Payment timeout sau provider charge | PAYMENT_UNKNOWN | Provider query/webhook/reconciliation |
| Inventory reserve success, reply mất | Reservation có thể tồn tại | Query/cancel bằng reservationId |
| Compensation release gửi hai lần | Tồn kho có nguy cơ cộng đôi | Conditional HELD -> RELEASED |
| Cancel đến trước late success | State có thể xung đột | Version/state guard và void/refund |
| Outbox event v12 đến sau v13 | Projection có thể rollback | Source version guard/gap handling |
| Orchestrator crash | Saga còn dở | Durable state + worker recovery |
| Một service down nhiều giờ | Backlog, holds hết hạn | Retry budget, deadline, sweeper |
| Region partition | Không thể đạt authority | Không confirm trái invariant; PENDING/fail closed |
| Restore snapshot cũ | State/version cũ cạnh tranh event mới | Reconcile source version, replay events |

Một hệ chưa kiểm thử những tình huống này chưa thể tuyên bố workflow đáng tin chỉ vì happy path chạy thành công.

## 41. Kiểm thử tự động với failure injection

### 41.1. Concurrent inventory reservation

Tạo `available=1`, cho 100 clients đồng thời reserve. Kết quả tối đa một reservation thành công theo authority, không có `available < 0`.

### 41.2. Duplicate checkout HTTP

Gửi 20 requests cùng `Idempotency-Key`. Phải có một Order/business intent, những requests khác trả cùng outcome hoặc PROCESSING nhất quán.

### 41.3. Outbox crash point

Cho Order local transaction commit, kill relay trước publish. Khởi động lại và xác minh event được publish.

### 41.4. Publish–mark crash point

Kill relay sau broker ACK nhưng trước mark PUBLISHED. Consumer phải xử lý event lặp mà không reserve hai lần.

### 41.5. Consumer crash point

Cho Inbox và Inventory transaction commit rồi kill consumer trước ACK. Broker giao lại; không thay đổi tồn kho lần hai.

### 41.6. Payment unknown

Mô phỏng provider trả success nhưng HTTP response mất. Recovery phải tra lại cùng `paymentIntentId`, không tạo charge mới.

### 41.7. Late event

Order đã CANCELLED, sau đó nhận `PaymentAuthorized` muộn. Order không được tự CONFIRMED; compensation/reconciliation chạy theo rule.

### 41.8. Hold expiry

Cho hold hết hạn cùng lúc Confirm đến. Database phải có một điều kiện nguyên tử để một transition hợp lệ thắng, không vừa release vừa confirm.

### 41.9. Out-of-order events

Gửi projection v13 trước v12, đảm bảo không rollback sang v12 hoặc xử lý gap theo policy.

### 41.10. Multi-region failover

Mất region chứa authority, xác minh hệ không bán vượt quota hoặc xác nhận hai owners. Với workflow cho phép degraded mode, API trả trạng thái rõ.

### 41.11. Data restore/replay

Rebuild search từ snapshot cũ trong lúc live CDC tiếp tục chạy; source version guard phải giữ winner hợp lệ.

### 41.12. Không chaos tùy tiện trên production

Network partition, kill majority hay restore snapshot là test phá hủy có thể ảnh hưởng dữ liệu thật. Thực hiện trong môi trường cách ly hoặc theo kế hoạch được phê duyệt.

## 42. Những ngộ nhận phổ biến

**“NoSQL không có transaction.”** Sai. Nhiều NoSQL hỗ trợ atomic item/document mutations hoặc transactions theo phạm vi riêng.

**“Có transaction là mọi document trong toàn cluster đều atomic.”** Không mặc định. Cần xem đúng transaction API và scope.

**“MongoDB `@Transactional` tự rollback cổng thanh toán.”** Sai; provider không tham gia local DB transaction.

**“QUORUM của Cassandra tương đương serializable transaction.”** Không. Quorum replica ACK khác CAS/LWT.

**“Cassandra logged batch là ACID xuyên nhiều partition.”** Không nên suy như vậy.

**“Một DynamoDB transaction ở Region A nghĩa global tables commit đồng bộ mọi region.”** Không mặc định; tùy replication mode.

**“Outbox làm messages exactly-once.”** Không. Relay có thể publish trùng.

**“Dùng broker exactly-once thì không cần idempotency ở provider.”** Sai. External HTTP side effect nằm ngoài transaction của broker.

**“Mark event processed trước xử lý là đủ.”** Sai. Crash có thể khiến event bị bỏ quên vĩnh viễn.

**“Consumer ACK trước commit cũng được.”** Nguy hiểm vì crash có thể mất business mutation.

**“Saga là transaction ACID phân tán.”** Sai. Saga gồm nhiều local commits và compensations.

**“Compensation là rollback byte-for-byte.”** Sai. Refund không xóa charge lịch sử; email không thể unsend.

**“Timeout nghĩa payment thất bại.”** Sai. Outcome có thể unknown.

**“Retry không giới hạn vì operations idempotent.”** Sai. Dù không trùng dữ liệu, retry storm vẫn gây quá tải.

**“Order PENDING nghĩa có thể bỏ qua không cần recovery.”** Sai. Cần deadline/sweeper/reconciliation.

**“Version của Order so được với version Inventory.”** Không nếu chúng có scope độc lập.

**“Event nhận sau là mới hơn.”** Không. Delivery có thể out-of-order.

**“Two-phase commit giống Saga.”** Sai. Khác commit model và failure handling.

**“Thêm microservice có nghĩa mỗi dịch vụ được sửa DB của dịch vụ khác.”** Không, làm vậy thường phá ownership/invariants.

**“Replication là backup.”** Sai. Delete nhầm/corruption có thể lan qua mọi replica.

**“Tất cả happy-path tests chạy xanh là workflow đã an toàn.”** Chưa. Cần crash, duplicates, lost ACK và concurrent contention tests.

## 43. Case study: ứng dụng đặt phòng theo chỗ trống hữu hạn

Một marketplace cho phép một host có một phòng trong một khoảng thời gian.

### 43.1. Invariant

Không có hai bookings cùng `CONFIRMED` cho cùng `roomId` với khoảng thời gian chồng lấn.

### 43.2. Nếu chỉ lưu mỗi Booking một document?

Hai bookings khác `bookingId` có thể được tạo đồng thời. Atomic insert trên mỗi Booking **không bảo vệ** overlap.

### 43.3. Authority cho slot

Có thể:

- Dùng database transaction serializable có predicate/constraint phù hợp;
- Dùng một aggregate availability theo room/time bucket và conditional reservation;
- Dùng slot allocation và reservation tokens;
- Dùng một booking authority điều phối mọi claims cho cùng resource.

### 43.4. Các service khác

Sau khi hold slot:

```text
Booking Service -> Reservation HELD
Payment Service -> Authorization
Booking Service -> CONFIRMED
Notification Service -> Email
```

Những bước sau là Saga/TCC và outbox, không cần nhét email vào một database transaction.

### 43.5. Hủy booking

- Giải phóng đúng reservation ID nếu còn HELD.
- Void/cancel payment authorization nếu chưa capture.
- Nếu đã capture, tạo refund workflow.
- Đảm bảo cancelled booking không bị late payment success chuyển lại CONFIRMED vô điều kiện.

## 44. Case study: chuyển tiền và sổ cái

Một hệ tài chính không được chỉ cập nhật hai `balance` fields rồi hy vọng Saga compensation luôn đủ.

### 44.1. Invariant

Các bút toán phải hợp lệ và tổng giá trị theo nguyên tắc kế toán được bảo vệ trong **ledger authority**.

### 44.2. Thiết kế thường an toàn hơn

- Lưu append-only journal entries với unique operation ID.
- Posting transaction trong phạm vi authority hỗ trợ.
- Đọc balance từ ledger/materialized aggregate với reconciliation.
- Không dùng LWW cập nhật balance snapshots độc lập.
- Phân biệt pending transfer, committed ledger posting và external settlement.

### 44.3. External bank transfer

Một bank API không nằm trong local DB transaction. Cần idempotent payment instruction, trạng thái PENDING/UNKNOWN, callbacks/webhooks và reconciliation với settlement reports.

### 44.4. Compensation phải là bút toán mới

Nếu cần hoàn một giao dịch đã post, tạo reversal/refund entries, giữ audit trail; không xóa lịch sử để giả vờ transaction chưa từng xảy ra.

## 45. Lộ trình triển khai an toàn

### Bước 1 — Vẽ bản đồ ownership và invariant

Liệt kê aggregate, DB owner, commands/events, constraints và các ngoại tác.

### Bước 2 — Chọn local atomic primitives

Single-item conditional update trước khi mở multi-item transaction; nếu cần nhiều records, chọn transaction API đúng scope.

### Bước 3 — Chọn workflow boundary

Số services, bước có thể hủy, thời hạn, tác động irreversible, business outcomes.

### Bước 4 — Chọn choreography hoặc orchestration

Chọn dựa trên độ phức tạp, số nhánh và nhu cầu nhìn toàn bộ tiến độ.

### Bước 5 — Thêm outbox/inbox và source version

Không dual write DB/broker không có cơ chế phục hồi.

### Bước 6 — Đặt idempotency ở mọi ranh giới

HTTP, consumer, provider, compensation, scheduled workers.

### Bước 7 — Thiết kế timeout/UNKNOWN

Lưu trạng thái trung gian bền vững, có deadline và phương án đối soát.

### Bước 8 — Bổ sung metrics và runbook

Theo dõi saga stuck, pending outbox, payment unknown, orphan holds, DLQ và business anomalies.

### Bước 9 — Failure injection

Đánh vào từng khoảng giữa commit, publish, ACK, provider reply và compensation.

### Bước 10 — Rollout có kiểm soát

Dùng canary/feature flags, replay-safe migration, monitor, reconciliation và rollback route. Không chuyển workflow cũ sang mới bằng dual-write thiếu idempotency.

## 46. Bài tập thực hành

### Bài tập 1 — Atomic boundary

Inventory decrement và Order insert ở cùng MongoDB deployment với session transaction.

**Câu hỏi:** Có thể đặt trong cùng local transaction không?

**Gợi ý:** Có trong topology hỗ trợ, nếu mọi operations tham gia đúng transaction/session và thỏa giới hạn.

### Bài tập 2 — HTTP ngoài local transaction

Order Service dùng `@Transactional`, bên trong gọi Payment Service HTTP.

**Câu hỏi:** Order DB rollback có rollback được charge không?

**Gợi ý:** Không. Payment là external effect.

### Bài tập 3 — Check-then-write race

Hai requests cùng đọc `available=1` rồi ghi `available=0`.

**Câu hỏi:** Vì sao có thể bán hai lần?

**Gợi ý:** Điều kiện không được kiểm tra nguyên tử.

### Bài tập 4 — DynamoDB transactions

Order + Inventory + Outbox là ba items trong cùng account/Region được phép dùng `TransactWriteItems`.

**Câu hỏi:** Nên gộp điều kiện `available>=1` vào operation nào?

**Gợi ý:** Vào Update Inventory, tránh hai actions trên cùng item.

### Bài tập 5 — Cosmos DB

Order và Outbox ở hai logical partition keys khác nhau.

**Câu hỏi:** Có thể dùng một transactional batch cùng partition để bảo vệ cả hai không?

**Gợi ý:** Không; cần điều chỉnh placement hoặc chiến lược khác.

### Bài tập 6 — Cassandra

Team dùng logged BATCH qua Order và Inventory partitions rồi tuyên bố serializable.

**Câu hỏi:** Nhầm lẫn ở đâu?

**Gợi ý:** Batchlog/batch semantics không tự tạo cross-partition ACID serializable transaction.

### Bài tập 7 — OCC

Order version=7, hai workers đều muốn chuyển trạng thái.

**Câu hỏi:** CAS trên version giúp gì?

**Gợi ý:** Chỉ một transition hợp lệ theo expected version, worker stale phải reload.

### Bài tập 8 — Isolation write skew

Hai transactions cùng đọc hai bác sĩ onCall rồi tắt mỗi người một field/document.

**Câu hỏi:** Vì sao atomic mỗi document chưa đủ?

**Gợi ý:** Invariant trải hai records; isolation có thể cho write skew.

### Bài tập 9 — Dual write DB trước broker

Order commit, process crash trước publish.

**Câu hỏi:** Sửa bằng pattern gì?

**Gợi ý:** Transactional outbox/CDC với reliable relay.

### Bài tập 10 — Dual write broker trước DB

Event đến consumer nhưng Order transaction fail.

**Câu hỏi:** Hậu quả?

**Gợi ý:** Consumer thấy một sự kiện về state chưa commit; cần commit source + event intent atomically.

### Bài tập 11 — Outbox duplicate

Broker ACK event, relay crash trước mark published.

**Câu hỏi:** Consumer nhận lại cần làm gì?

**Gợi ý:** Inbox/idempotent handler.

### Bài tập 12 — Inbox sai thứ tự

Consumer ghi Inbox marker rồi crash trước Inventory reserve.

**Câu hỏi:** Lỗi gì?

**Gợi ý:** Event bị coi đã xử lý dù business mutation chưa xảy ra; cần atomic cùng transaction.

### Bài tập 13 — Saga hay transaction?

Order DB, Inventory DB và Payment provider là ba authorities khác nhau.

**Câu hỏi:** Một local transaction có đủ không?

**Gợi ý:** Không. Cần workflow phân tán như Saga/TCC hoặc cơ chế phân tán được các participants thực sự hỗ trợ.

### Bài tập 14 — Choreography

Một event handler lặp và dẫn tới vòng lặp vô hạn events.

**Câu hỏi:** Nhóm cần kiểm soát gì?

**Gợi ý:** State guards, event contracts, correlation IDs và flow ownership; cân nhắc orchestration.

### Bài tập 15 — Orchestration

Orchestrator crash sau khi Inventory reserve xong.

**Câu hỏi:** Điều gì giúp tiếp tục?

**Gợi ý:** Durable saga state, idempotent command/reply và recovery worker.

### Bài tập 16 — Compensation

ReleaseInventory(R100) được gửi hai lần.

**Câu hỏi:** Làm sao không cộng tồn kho hai lần?

**Gợi ý:** Conditional reservation transition HELD -> RELEASED và dedupe theo reservationId.

### Bài tập 17 — Payment UNKNOWN

Provider charge success, HTTP timeout.

**Câu hỏi:** Có thể lập tức gửi charge mới với ID khác không?

**Gợi ý:** Không. Query/reconcile cùng payment intent và provider idempotency key.

### Bài tập 18 — Late success

Order đã CANCELLED, một event PaymentAuthorized đến muộn.

**Câu hỏi:** Có tự chuyển CONFIRMED không?

**Gợi ý:** Không. State guard và void/refund workflow theo outcome thật.

### Bài tập 19 — Out-of-order events

Projection có Order v12, event v11 đến sau.

**Câu hỏi:** Xử lý thế nào?

**Gợi ý:** Version guard; nếu delta events thì còn cần xử lý gaps.

### Bài tập 20 — Idempotency TTL

HTTP retry sau 48 giờ nhưng idempotency record chỉ giữ 5 phút.

**Câu hỏi:** Rủi ro gì?

**Gợi ý:** Tạo business operation thứ hai; retention phải phù hợp retry/dispute window.

### Bài tập 21 — TCC hold expiry

Inventory hold hết hạn, Confirm đến sau.

**Câu hỏi:** Inventory cần làm gì?

**Gợi ý:** Atomic check hold state/deadline; không confirm từ event cũ.

### Bài tập 22 — 2PC

Payment provider chỉ hỗ trợ HTTP charge, không hỗ trợ prepare/commit XA.

**Câu hỏi:** Có thể 2PC atomically commit database và provider bằng cách gọi hai HTTP endpoints không?

**Gợi ý:** Không; cần provider idempotency và workflow khác.

### Bài tập 23 — Email compensation

Email xác nhận đã gửi rồi Order bị hủy.

**Câu hỏi:** Có rollback email không?

**Gợi ý:** Không; có thể gửi đính chính và lưu audit.

### Bài tập 24 — Business correctness

Dashboard outbox lag=0 nhưng có 10 PaymentCaptured không có OrderConfirmed.

**Câu hỏi:** Có thể tuyên bố hệ đã đúng chưa?

**Gợi ý:** Không; cần reconciliation và business invariant metrics.

### Bài tập 25 — Thiết kế hoàn chỉnh

Một nền tảng đặt phòng cần giữ slot, charge tiền, tạo booking, gửi email và cập nhật search.

**Yêu cầu:** Vẽ transaction boundaries, Saga state machine, outbox/inbox, idempotency keys, compensation, timeout handling và projection freshness.

**Gợi ý:** Slot authority dùng atomic reservation; Booking service giữ state/outbox; Payment dùng idempotent provider intent; Saga quản lý Confirm/Cancel/Refund; search/email là downstream eventual consumers.

## 47. Checklist triển khai thực tế

- [ ] Đã viết invariant nghiệp vụ thành điều kiện có thể kiểm tra.
- [ ] Đã chỉ rõ transaction boundary và database owner cho mỗi aggregate.
- [ ] Không nhầm NoSQL với “không có transaction”.
- [ ] Không suy atomic multi-item từ một API chỉ hỗ trợ một item/partition.
- [ ] Đã chọn đúng conditional update, CAS, transaction/isolation.
- [ ] Đã xác định durability/write concern/read visibility.
- [ ] Không gọi payment/email trong transaction callback có thể retry.
- [ ] Không coi `@Transactional` tự bao phủ HTTP hoặc broker.
- [ ] Không dual write DB và broker không có recovery.
- [ ] Outbox được ghi atomically với source state.
- [ ] Relay có retry, checkpoint, backpressure và giám sát lag.
- [ ] Consumer có Inbox/dedupe cùng local mutation theo atomic scope.
- [ ] Đã xác định eventId, aggregateVersion, operationId và paymentIntentId.
- [ ] Có idempotency cho retries HTTP, broker và external provider.
- [ ] Có state machine với PENDING/UNKNOWN/COMPENSATING rõ ràng.
- [ ] Mỗi compensation có identity, state guard và retry.
- [ ] Reservation/hold có deadline và recovery.
- [ ] Có policy xử lý late replies và out-of-order messages.
- [ ] Có version guard ở search/read-model projections.
- [ ] Đã phân biệt Saga với transaction ACID/2PC.
- [ ] Có audit/ledger và không xóa nhầm lịch sử financial effect.
- [ ] Có graceful degradation khi một authority unavailable.
- [ ] Có observability xuyên services bằng correlation IDs.
- [ ] Có reconciliation jobs cho orphan payments/reservations.
- [ ] Đã thử crash trước/sau commit, publish, ACK, provider response.
- [ ] Đã thử duplicate, concurrency, timeout và failover.
- [ ] Không gọi kết quả là “exactly once” nếu chưa nêu phạm vi.
- [ ] User-facing status không khẳng định CONFIRMED trước business commit.

## 48. Tổng kết

Trong NoSQL, **giao dịch trong một hệ** có thể rất mạnh nhưng luôn có **phạm vi**: một item, document, logical partition, nhiều records trong một database transaction hoặc một nhóm dữ liệu do một authority bảo vệ. Chọn conditional update, OCC, transaction và isolation đúng phạm vi giúp giữ invariant cục bộ mà không cần coordination dư thừa.

Khi nghiệp vụ cần nhiều **dịch vụ hoặc external providers**, local ACID không tự trải qua HTTP, broker và database khác. Thay vì coi toàn workflow là một hàm có thể rollback, hãy mô hình hóa:

1. **Mỗi bước local** commit dữ liệu và intent event một cách bền vững.
2. **Outbox/CDC** chuyển ý định sang broker mà không bỏ sót source commit.
3. **Inbox/idempotency** khiến retry/redelivery không nhân đôi business effect.
4. **Saga/TCC** quản lý những bước, trạng thái trung gian, deadlines và compensations.
5. **Reconciliation** xử lý timeout có kết quả không rõ, side effect ngoài hệ và workflow kẹt.
6. **Business invariants** được kiểm tra tại authority phù hợp thay vì hy vọng eventual consistency sửa lỗi đã công bố cho khách.

**Một database transaction bảo đảm điều gì xảy ra cùng nhau trong ranh giới của nó. Một quy trình nghiệp vụ phân tán phải quy định điều gì được xác nhận, điều gì có thể tạm chờ, điều gì cần bù và cách phát hiện/sửa mọi trường hợp thất bại giữa các ranh giới ấy.**

