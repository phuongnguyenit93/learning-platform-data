# Đặt lớp truy cập dữ liệu và tránh rò rỉ ngữ nghĩa sản phẩm ngoài hợp đồng

Một dịch vụ Java lưu đơn hàng trong một cơ sở dữ liệu NoSQL dạng document. Ban đầu, business service gọi trực tiếp driver để tìm document, cập nhật trạng thái và xử lý exception. Khi cần chuyển một số tenant lớn sang cụm khác hoặc thay công nghệ lưu trữ, nhóm nhận ra code nghiệp vụ đã biết quá nhiều về BSON, tên collection, session, index, cursor và quy tắc retry của sản phẩm. Mỗi thay đổi hạ tầng kéo theo sửa hàng chục service.

Một giải pháp thường được đề xuất là tạo `Repository<T>` với `save()`, `findById()` và `delete()`, rồi giấu toàn bộ database ở phía sau. Nhưng một interface quá chung cũng có thể nguy hiểm: `save()` có phải atomic trên nhiều records? `findById()` có luôn đọc dữ liệu mới nhất? `delete()` có xóa ngay không? Một timeout có chứng minh write không commit không? Nếu caller tự tưởng tượng các bảo đảm mà backend không cung cấp, abstraction đã làm **rò rỉ ngữ nghĩa bằng cách che khuất những giới hạn quan trọng**.

Trong bài học thuộc chương **Tích hợp và kiến trúc** của **Database No SQL**, mục tiêu là thiết kế lớp truy cập dữ liệu có ý nghĩa đối với nghiệp vụ: **giấu chi tiết SDK không cần thiết nhưng công bố trung thực các bảo đảm về dữ liệu**. Chúng ta sẽ xây ports/adapters, repository và query contracts, biểu diễn transaction/conditional write/read consistency/unknown commit, so sánh cách triển khai trên nhiều NoSQL, kiểm thử contract và chuẩn bị cho migration.

> **Nguyên tắc cốt lõi:** Abstraction tốt không hứa rằng MongoDB, DynamoDB, Cassandra, Cosmos DB và Redis giống nhau. Nó **định nghĩa hành vi ứng dụng cần**, xác minh backend có thể đáp ứng, và từ chối hoặc thay đổi kiến trúc khi một sản phẩm không đáp ứng được hợp đồng.

## 1. “Rò rỉ ngữ nghĩa sản phẩm” là gì?

Một abstraction rò rỉ khi consumer buộc phải phụ thuộc chi tiết lẽ ra thuộc bên triển khai, hoặc khi interface không diễn đạt đủ sự khác biệt làm thay đổi kết quả ứng dụng.

### 1.1. Rò rỉ loại thứ nhất: SDK chảy vào domain

~~~java
public interface OrderRepository {
    org.bson.Document findOne(org.bson.Document filter);
    com.mongodb.client.result.UpdateResult update(
        com.mongodb.client.ClientSession session,
        org.bson.Document filter,
        org.bson.Document update
    );
}
~~~

Caller phải hiểu BSON, MongoDB session, update operators và `UpdateResult`. Đây gần như một wrapper đổi tên driver, chưa phải domain contract.

### 1.2. Rò rỉ loại thứ hai: che đi semantics bắt buộc

~~~java
public interface OrderRepository {
    void save(Order order);
}
~~~

Chữ ký đơn giản nhưng chưa nói:

- `save` ghi đè toàn document, patch hay upsert?
- Có `expectedVersion` để chống lost update không?
- Kết quả thành công là local ACK hay committed durable?
- Nếu timeout, thao tác có thể đã commit không?
- Có transaction cùng Inventory/Outbox không?
- Đường ghi chọn partition/shard/tenant bằng cách nào?

Nếu code nghiệp vụ mặc nhiên giả định transaction mạnh, port đã hứa ngầm điều sai. Đây là kiểu leakage **còn nguy hiểm hơn** việc lộ SDK type.

### 1.3. Phân loại thứ nên giấu và thứ phải nói rõ

| Nên nằm ở adapter/hạ tầng | Phải hiện diện trong contract hoặc capability policy |
|---|---|
Driver classes, BSON, AttributeValue | Ý định nghiệp vụ và điều kiện commit |
Tên collection/table, routing request | Logical identity/tenant scope |
Connection pool, endpoint discovery | Quyền ghi, availability, failover behavior |
Exception class và error label vendor | Known success, known reject, unknown outcome |
Wire-format continuation token | Thứ tự paging, giới hạn snapshot, token validity |
Serializer và mapping index | Kiểu dữ liệu, precision, version semantics |
Native retry/retry-after headers | Deadline, retry budget, idempotency |
Implementation của TTL/CDC | Expiry, retention, event ordering/delivery contract |

Giấu chi tiết **không có nghĩa làm biến mất giới hạn**. Nếu thông tin ảnh hưởng invariant, application cần biết hoặc được bảo vệ bằng hợp đồng phù hợp.

## 2. Xác định ranh giới qua Ports & Adapters

Một kiến trúc tham khảo:

~~~mermaid
flowchart TD
    API["HTTP / gRPC Endpoint"] --> APP["Application Use Case"]
    APP --> CMD["Command Port / Aggregate Repository"]
    APP --> QUERY["Query Port / Read Model"]
    CMD --> ADAPTER["NoSQL Command Adapter"]
    QUERY --> QADAPTER["Query Adapter"]
    ADAPTER --> SDK["Vendor Driver"]
    SDK --> DB["Authoritative Database"]
    QADAPTER --> READDB["Search / Projection / Cache"]
~~~

Application **định nghĩa những phép toán nó cần**. Infrastructure implements các contracts ấy. Một composition root chọn adapter phù hợp theo cấu hình triển khai.

### 2.1. Hướng phụ thuộc

~~~text
domain/application code
    defines port interfaces and domain types

infrastructure code
    imports ports and vendor SDKs

bootstrap/composition
    constructs adapters and wires dependencies
~~~

Không để `domain` import các package `com.mongodb`, `software.amazon.awssdk`, `com.azure.cosmos` hoặc `com.datastax` nếu mục đích là giữ domain độc lập.

### 2.2. Lớp truy cập dữ liệu không nhất thiết là thư viện khổng lồ

Trong một ứng dụng nhỏ, package chứa ports/adapters là đủ. Không cần tạo thêm network hop/microservice chỉ để chứng minh “clean architecture”. Ranh giới logic quan trọng hơn số module.

### 2.3. Repository không nhất thiết tương ứng một collection

`OrderRepository` thường đại diện **aggregate Order**: status, lines, totals, outbox intent cần thay đổi trong một consistency boundary. Physical storage có thể là một document, nhiều items cùng partition hoặc transaction trong scope được hỗ trợ.

### 2.4. Command và query có thể đi qua dữ liệu khác nhau

Lệnh xác nhận đơn phải dùng nguồn có thẩm quyền. Query tìm đơn theo tên khách hàng có thể dùng search index bất đồng bộ. Hai access paths có **semantics khác nhau**, nên tách port có ích hơn cố ép chúng vào một `find()` chung.

## 3. Thiết kế contract từ use case, không từ CRUD của driver

Hãy bắt đầu bằng yêu cầu:

~~~text
ConfirmOrder:
    only PENDING -> CONFIRMED
    no duplicate confirmation for same commandId
    durable confirmation and outbox intent
    explicit COMMITTED, REJECTED or PENDING outcome

ReserveStock:
    available stock never becomes negative
    one reservation per stable business command
    concurrent writers cannot both spend same stock

GetOrderForDecision:
    tenant authorization required
    read consistency sufficient for business decision

SearchOrders:
    eventual indexing accepted
    bounded query, pagination, documented lag
~~~

Sau đó mới chọn primitive MongoDB/DynamoDB/Cosmos/CQL/Redis phù hợp.

### 3.1. Hợp đồng gồm cả điều không được hứa

Ví dụ:

~~~text
SearchOrders guarantees:
    returns only data caller may view
    bounded pages with a documented sort order

SearchOrders does not guarantee:
    immediate visibility after ConfirmOrder
    existence proof from a missing search result
    transactional consistency with Inventory
~~~

Negative guarantees giúp ngăn service khác dùng read model sai mục đích.

### 3.2. Phân biệt business result với infrastructure result

`OUT_OF_STOCK` là từ chối nghiệp vụ. `PERMISSION_DENIED` là kiểm soát quyền. `RETRYABLE_UNAVAILABLE` là điều kiện tạm thời. `UNKNOWN_COMMIT` có nghĩa client chưa xác minh kết quả, **không** nghĩa server đã rollback.

### 3.3. Abstraction không tự tạo invariant

Một method `transferMoney()` không làm hai cập nhật Account trở thành atomic nếu backend chỉ hỗ trợ single-document writes. Adapter phải có primitive phù hợp hoặc application cần workflow/transaction architecture khác.

## 4. Ma trận các bảo đảm cần thống nhất trước khi viết interface

| Chiều hợp đồng | Câu hỏi bắt buộc |
|---|---|
| Identity | Entity ID có duy nhất theo tenant/partition không? |
| Authorization | Tenant scope lấy từ context đáng tin nào? |
| Atomicity | Một item, một document, logical partition hay nhiều shards? |
| Isolation | Snapshot, serializable hay chỉ conditional single-key? |
| Conditional update | CAS/version/ETag/predicate có kiểm tra tại commit không? |
| ACK/durability | Thành công đồng nghĩa đã bền qua lỗi nào? |
| Read consistency | Strong, session, eventual và phạm vi? |
| Idempotency | Stable commandId được lưu/kiểm tra ở đâu? |
| Ambiguous result | Timeout sau commit được xử lý như thế nào? |
| Secondary index | Index đồng bộ hay cập nhật trễ? |
| Pagination | Token có snapshot/cross-shard semantics gì? |
| Query access | Có cần partition key, fan-out có giới hạn không? |
| Expiry/delete | TTL xóa ngay hay nền; tombstones ra sao? |
| CDC/events | Thứ tự theo partition, at-least-once hay khả năng replay? |
| Multi-region | Một hay nhiều writers, conflict rule nào? |
| Schema evolution | Document phiên bản cũ được đọc thế nào? |
| Capacity | Hot key, rate limit, throttling và retry hint? |

### 4.1. Đừng dùng `supportsTransactions=true` không có scope

Tốt hơn:

~~~text
atomicity:
    scope = SINGLE_LOGICAL_PARTITION
    maxOperations = documented API limit
    crossRegionCommit = NOT_SUPPORTED
~~~

Những giá trị là ví dụ; phải lấy từ version, API và topology thật.

### 4.2. Capability phải gắn với use case

Một backend có thể hỗ trợ transaction của vài items nhưng không hỗ trợ phép merge mười triệu documents. Một hệ có mạnh single-key consistency nhưng secondary index eventual. Không suy từ nhãn “transactional database” rằng mọi query/operation cùng bảo đảm.

### 4.3. Fail fast khi backend không đáp ứng

Nếu `ConfirmOrder` bắt buộc ghi Order cùng Outbox atomically mà adapter chỉ gọi hai writes độc lập, hệ phải từ chối cấu hình/capability hoặc đổi data model. Không trả `COMMITTED` với lời hứa giả.

## 5. Một port theo ý định nghiệp vụ: giữ tồn kho

Mô hình Java 17+:

~~~java
public record ReserveStockCommand(
    String commandId,
    String tenantId,
    String sku,
    long quantity,
    String orderId
) {}

public record ReservationReceipt(
    String reservationId,
    String sku,
    long reservedQuantity,
    long inventoryVersion
) {}

public sealed interface ReserveStockResult
    permits ReserveStockResult.Committed,
            ReserveStockResult.Rejected,
            ReserveStockResult.Pending {

    record Committed(ReservationReceipt receipt)
        implements ReserveStockResult {}

    record Rejected(String businessCode)
        implements ReserveStockResult {}

    record Pending(String commandId)
        implements ReserveStockResult {}
}

public interface InventoryReservationPort {
    ReserveStockResult reserve(ReserveStockCommand command);

    ReserveStockResult resolveByCommandId(
        String tenantId, String commandId
    );
}
~~~

Đây là interface application-owned; không lộ native classes hay cách partitioner tạo key.

### 5.1. Viết semantic contract cạnh interface

~~~text
reserve(cmd):
    Preconditions:
      - caller is authorized for tenant
      - quantity > 0, valid sku/orderId

    Guarantees:
      - reservation cannot exceed available authority
      - same (tenantId, commandId) and same immutable payload
        cannot reserve stock twice
      - a COMMITTED receipt is durable according to deployment contract

    Outcomes:
      COMMITTED: reservation is confirmed
      REJECTED: command did not reserve under specified reason
      PENDING: system cannot yet confirm final outcome

    Reusing same commandId with different payload:
      reject as idempotency mismatch
~~~

### 5.2. `Pending` khác business rejection

Nếu server đã commit nhưng response mất, ứng dụng chưa biết kết quả. Trả `REJECTED` có thể làm user tạo lệnh mới và giữ hàng lần hai. `Pending` cho phép đối soát bằng stable commandId.

### 5.3. Idempotency không do tên field tạo ra

Adapter phải enforce `commandId` cùng mutation trong atomic boundary hoặc protocol tương đương. Nếu giảm stock rồi ghi một processed-command record tách rời, crash giữa hai bước vẫn gây double reserve.

### 5.4. Domain result không thay diagnostic data

`ReserveStockResult` đủ cho business flow; requestId, error labels, retries, partition ID vẫn nên được ghi vào structured telemetry của adapter, không nhét vào domain code.

## 6. Application service dựa vào port, không dựa SDK

~~~java
public final class ReserveStockService {
    private final InventoryReservationPort port;

    public ReserveStockService(InventoryReservationPort port) {
        this.port = port;
    }

    public ReserveStockResult execute(ReserveStockCommand command) {
        if (command.commandId() == null
                || command.commandId().isBlank()) {
            return new ReserveStockResult.Rejected("INVALID_COMMAND_ID");
        }
        if (command.quantity() <= 0) {
            return new ReserveStockResult.Rejected("INVALID_QUANTITY");
        }

        ReserveStockResult result = port.reserve(command);
        if (result instanceof ReserveStockResult.Pending) {
            return port.resolveByCommandId(
                command.tenantId(), command.commandId()
            );
        }
        return result;
    }
}
~~~

**Giới hạn của ví dụ:** Service chưa xác thực tenant/principal, chưa có end-to-end deadline, telemetry hoặc durable pending reconciliation. `resolveByCommandId` có thể tiếp tục trả Pending. Production cần kết nối với authorization và workflow bền, không coi một lần lookup là lời hứa giải quyết xong.

### 6.1. Không `get` rồi `decrement` ngoài atomic boundary

~~~text
Client A reads stock=2.
Client B reads stock=2.
A reserves 2.
B also reserves 2.
~~~

Nếu adapter chỉ làm read-then-write tách rời, cả hai có thể vượt kho. Nguồn có thẩm quyền phải thực hiện condition và mutation atomically hoặc có escrow/ownership protocol.

### 6.2. Cùng key nhưng payload khác

`commandId=C1, quantity=2` và `commandId=C1, quantity=5` không phải cùng một ý định. Dedupe store cần lưu fingerprint/canonical intent và từ chối mismatch.

## 7. Tránh `GenericRepository<T>` hứa quá nhiều

~~~java
interface GenericRepository<T> {
    T findById(String id);
    void save(T item);
    void delete(String id);
    java.util.List<T> findAll();
    void saveAll(java.util.List<T> items);
}
~~~

Chữ ký có vẻ portable, nhưng `findAll()` có thể quét toàn cluster; `saveAll()` có thể là bulk có partial success; `save()` có thể là upsert hoặc replace không có CAS; `delete()` có thể để lại tombstone/TTL.

### 7.1. Các câu hỏi interface không trả lời

- ID có partition/tenant scope nào?
- Ghi một bản ghi được ACK ở mốc durability nào?
- `saveAll` có all-or-nothing hay ghi từng item?
- Read có thể lấy từ follower lag không?
- Có lost-update guard và unique constraint không?
- Hai calls có được nằm trong cùng transaction manager?

### 7.2. Một abstraction xấu thường được “cứu” bằng nhiều flags

~~~java
save(entity, upsert, majority, requireFsync,
     transactional, ignoreConflict, strongRead);
~~~

Những flags tạo nhiều tổ hợp khó hiểu, một số không có nghĩa với backend. Tốt hơn là các use-case operations và capability-specific ports.

### 7.3. Port theo aggregate/intent thường chính xác hơn

~~~text
OrderCommandPort.confirmIfPending(command)
InventoryPort.reserve(command)
OrderQueryPort.search(criteria)
SessionStore.invalidate(sessionId)
~~~

Chúng mô tả behavior caller cần và cho adapter chọn primitives hợp lệ.

### 7.4. Khi generic CRUD đủ dùng

Với dữ liệu cấu hình nhỏ, use case đơn giản, single-owner hoặc read-only dataset có giới hạn rõ, generic repository vẫn hợp lý. Không cần xây framework phức tạp nếu không có invariant khó; chỉ tránh đem cùng abstraction ấy áp cho ledger, inventory và workflow nhiều shards.

## 8. Đặt boundary theo aggregate và transaction scope

Một Order có:

~~~text
Order header
Order lines
Status transitions
OrderOutboxIntent
~~~

Nếu status, lines và intent phải nhất quán, nên đặt cùng aggregate/transaction scope hoặc triển khai transaction đúng contract.

### 8.1. Repository không đồng nghĩa table

Một Order aggregate có thể nằm trong một document, một nhóm items cùng partition hoặc vài collections trong một transaction hỗ trợ. `OrderRepository` là domain boundary, không phải wrapper cho collection `orders`.

### 8.2. Multi-shard transaction là năng lực riêng

Nếu Inventory ở shard X và Order ở shard Y, hai commits độc lập không tự tạo atomic checkout. Dùng distributed transaction được sản phẩm hỗ trợ hoặc workflow/saga có states và compensation phù hợp.

### 8.3. `@Transactional` không phải câu thần chú

Framework annotation chỉ có hiệu lực theo transaction manager/driver/backend và propagation rules thực. Hai adapters thuộc hai databases khác nhau không tự tham gia cùng ACID transaction chỉ vì cùng nằm trong method.

### 8.4. Isolation khác durability

Majority durable ACK không tự ngăn write skew; snapshot isolation không tự serializable. Contract phải nói rõ invariant nào cần bảo vệ và primitive nào sẽ kiểm tra nó.

### 8.5. Không giấu transaction downgrade

Một adapter không hỗ trợ atomic Order+Outbox không được thay bằng hai independent writes rồi vẫn báo `COMMITTED` theo hợp đồng đã định.

## 9. Conditional write và optimistic concurrency

Một update đúng cần so version hoặc business predicate tại commit:

~~~text
IF Order.id=O-100
   AND tenantId=T1
   AND status=PENDING
   AND version=7
THEN
    status=CONFIRMED
    version=8
ELSE
    no mutation; report condition not met
~~~

### 9.1. Đừng tách read và write

~~~java
Order order = port.load(id);
if (order.status().equals("PENDING")) {
    port.save(order.withStatus("CONFIRMED"));
}
~~~

Hai requests có thể cùng đi qua `if`. Interface nên có `confirmIfPending`, `saveIfVersion` hoặc transaction có conflict protection.

### 9.2. Phân biệt các kết quả của CAS

Native update trả `matchedCount=0` có thể vì not-found, wrong tenant, stale version hoặc state predicate không còn phù hợp. Adapter không được đoán sai lý do; cần result chung hoặc authoritative read có permission phù hợp để phân loại.

### 9.3. Retry conflict không phải overwrite

Nếu expectedVersion 7 đã cũ, service có thể đọc 8, tính lại business decision và thử `expectedVersion=8` nếu hợp lệ. Không bỏ `If-Match`/version condition chỉ để thao tác thành công.

### 9.4. Entity version không phải causal ordering toàn cluster

Một scalar version tốt với single authority/OCC; hai regions độc lập có thể cùng tạo `version=8` khi partition. Nếu application cho phép multi-writer, contract phải nêu conflict resolution/causal semantics khác.

## 10. Adapter MongoDB: một ví dụ triển khai có điều kiện

Document:

~~~json
{
  "_id": "T1/SKU-A",
  "tenantId": "T1",
  "sku": "SKU-A",
  "available": 10,
  "version": 7
}
~~~

Atomic conditional mutation khái niệm:

~~~javascript
db.inventory.updateOne(
  {
    _id: "T1/SKU-A",
    tenantId: "T1",
    available: { $gte: 2 },
    version: 7
  },
  {
    $inc: { available: -2, version: 1 }
  }
);
~~~

### 10.1. Điều nó bảo vệ

Nếu MongoDB API đảm bảo condition + update nguyên tử trên một document, two concurrent requests dùng same expected version không cùng thành công như blind writes.

### 10.2. Điều nó chưa bảo vệ

Ví dụ chưa ghi processedCommandId cùng mutation, nên **chưa idempotent khi ACK bị mất và request được tái diễn**. Nếu port hứa idempotency, adapter phải dùng transaction cùng dedupe record hoặc document/protocol atomic tương ứng và đảm bảo retention.

### 10.3. Read concern và write concern

`w:1`/majority, journaling, read preferences và transaction commit concern là các knob sản phẩm cần ánh xạ vào contract đúng deployment. Adapter không được tuyên bố local ACK bảo vệ committed history qua mọi failover.

### 10.4. Mapping lỗi

Duplicate key, write conflict, network ambiguity và permission denial không nên thành một exception `DatabaseFailed` duy nhất. Phân loại cho phù hợp domain/infrastructure outcomes và lưu native details trong diagnostics.

## 11. Adapter DynamoDB: key-based access và điều kiện

Một item:

~~~text
PK=TENANT#T1
SK=INVENTORY#SKU-A
available=10
version=7
~~~

Một update expression khái niệm:

~~~text
SET available = available - :qty,
    version = version + :one
CONDITION available >= :qty AND version = :expected
~~~

Đây là pseudocode của intent, không phải request SDK đầy đủ; cần expression names, initialization và data types theo API thật.

### 11.1. Partition key không được “ẩn” tới mức không route được

Domain biết tenantId và SKU; adapter xây PK/SK. Nếu query không có access key cần thiết, port phải nêu hạn chế hoặc dùng read model khác, không tự fallback full-table scan.

### 11.2. Dedupe record và transaction

Với operation nằm trong scope API hỗ trợ, một transactional write có thể cập nhật Inventory và tạo `ProcessedCommand` conditionally. Cần test **atomicity, payload mismatch, retry và outcome unknown**, không chỉ happy path.

### 11.3. GSI có consistency riêng

Một read qua GSI cập nhật trễ không thích hợp để enforce business quota ngay lúc ghi. Nếu use case cần strong condition, dùng authoritative item/transaction path.

### 11.4. Cross-region semantics khác nhau

Regional success không tự là global linearizable commit. Nếu đổi deployment sang global tables/multi-writer, adapter cần đánh giá conflict/replication/transaction guarantees, không chỉ thay endpoint.

## 12. Cosmos DB, Cassandra/ScyllaDB và Redis

### 12.1. Cosmos DB for NoSQL

ETag + conditional `If-Match` giúp OCC theo item; transactional batch/stored procedures có logical partition scope theo API. Adapter không được hứa atomicity cho Order và Outbox ở hai full partition keys nếu không có primitive thật sự hỗ trợ.

### 12.2. Cassandra/ScyllaDB

Partition key/clustering quyết định access pattern và dữ liệu cùng partition. Normal writes có consistency levels khác LWT/conditional CQL. Port `saveIfVersion` phải dùng atomic conditional mechanism trong phạm vi phù hợp, không biến `SELECT` rồi `UPDATE` thành CAS giả.

### 12.3. Redis

Một số commands/scripts nguyên tử trên primary, nhưng primary–replica replication/promotion có durability/failover semantics riêng. Nếu abstraction hứa không mất confirmed reservation khi mất primary, phải kiểm chứng backend thực sự đáp ứng, không chỉ test script atomic lúc một node khỏe.

### 12.4. Cùng port không buộc mọi vendor giống nhau

Một Redis cache adapter có thể chỉ phù hợp `CachePort`; Cassandra phù hợp time-series access patterns; MongoDB phù hợp document aggregate; các hệ có thể kết hợp trong cùng kiến trúc theo role rõ ràng.

### 12.5. Không suy từ nhãn sản phẩm

“Document”, “wide-column”, “managed”, “quorum” và “supports transactions” là mô tả chưa đủ. Hợp đồng phải được kiểm chứng bằng API, version, configuration, topology và fault model cụ thể.

## 13. Read consistency: source of truth khác search và cache

Một hệ có:

~~~text
Order source database
    -> CDC/outbox
    -> Search index
    -> Cache
~~~

Sau khi ConfirmOrder committed, search có thể vẫn phản ánh `PENDING`.

### 13.1. Đặt hai read ports khác nhau

~~~java
public interface OrderAuthoritativeReadPort {
    OrderState getForDecision(
        String authorizedTenantId,
        String orderId
    );
}

public interface OrderSearchPort {
    OrderSearchPage search(OrderSearchCriteria criteria);
}
~~~

Port đầu dùng cho business decision/reconciliation; port thứ hai cho trải nghiệm tìm kiếm có độ trễ projection được công bố.

### 13.2. Đừng đặt mọi đường đọc vào `findById`

Một method chung khiến service không biết dữ liệu từ leader, follower, GSI, cache hoặc search. Đó là kiểu **giấu sai semantics**.

### 13.3. Session/read-your-writes

Nếu user vừa ghi và GET phải thấy chính write của mình, application có thể cần session context/causal token hoặc authoritative read mode được backend hỗ trợ. Không mặc định “cùng user” nghĩa tự được session consistency ở database.

### 13.4. Strong read không đồng nghĩa cross-shard transaction

Một linearizable point read có thể vẫn không tạo atomic snapshot giữa hai aggregates. Port phải nêu chính xác consistency và transaction scope.

### 13.5. Không dùng absence trong search làm bằng chứng

Nếu search chưa thấy Order, không tự tạo lại Order hoặc kết luận write nguồn thất bại. Đối soát ở source bằng appropriate read mode.

## 14. Query ports có giới hạn rõ: không expose query DSL vô hạn

Một contract:

~~~java
public record OrderSearchCriteria(
    String authorizedTenantId,
    String status,
    long fromEpochMillis,
    long toEpochMillis,
    int limit,
    String pageToken
) {}

public record OrderSummary(
    String orderId,
    String status,
    long createdAtEpochMillis
) {}

public record OrderSearchPage(
    java.util.List<OrderSummary> items,
    String nextPageToken,
    Long projectionAsOfEpochMillis
) {}

public interface OrderSearchPort {
    OrderSearchPage search(OrderSearchCriteria criteria);
}
~~~

### 14.1. Limit, sorting và access patterns

`limit` nên bị cap; time-range bounded; sort key cần tie-breaker (ví dụ createdAt + orderId). Nếu query thiếu partition/index key, adapter có thể phải scatter/gather toàn cluster; contract phải giới hạn workload hoặc đề xuất read model khác.

### 14.2. Opaque page token

Token có thể chứa native continuation token, shard positions, last sort key hoặc snapshot generation. Caller **không** parse/rebuild token; nó chỉ gửi lại trong đúng query scope.

### 14.3. Token phải ràng buộc identity

Không cho page token của tenant T1 dùng để tiếp tục query ở T2. Token cần gắn filters, sort, tenant, schema/routing epoch và expiration khi thích hợp.

### 14.4. Pagination consistency

Nếu trong lúc lấy nhiều pages có inserts/deletes, backend có thể cho snapshot consistency hoặc chỉ best-effort ordering. Không hứa snapshot hoàn hảo nếu adapter không có cơ chế tương ứng.

### 14.5. Fan-out và tail latency

Tenant whale có 64 buckets; LIST newest Orders có thể cần query 64 buckets và k-way merge. Adapter phải kiểm soát concurrent requests, deadline và cost. Tên method `search` không cho phép full scan không giới hạn.

## 15. Domain model, DTO và persistence document

Một anti-pattern:

~~~java
@Document("orders")
public class Order {
    @Id public String id;
    @Indexed public String tenantId;
    public String status;
}
~~~

Class vừa là API DTO, domain entity, persistence schema. Sau một thời gian, tất cả callers phụ thuộc annotations, field names và schema migration của database.

### 15.1. Các representation có trách nhiệm riêng

~~~text
HTTP Request DTO
    -> Application Command
    -> Domain Aggregate/Value Objects
    -> Persistence Document or Row
~~~

Không cần tạo quá nhiều classes cho data nhỏ, nhưng với core entities, tách mapping giúp kiểm soát invariants và giảm SDK coupling.

### 15.2. Persistence fields có thể chỉ phục vụ index

Document lưu `tenantBucket`, `ttlEpoch`, `sortKey`, `schemaVersion`, `searchTokens`. Domain Order không cần biết hashing/index strategy để quyết định chuyển trạng thái.

### 15.3. Conversion có thể làm sai dữ liệu

Decimal128, JSON numbers, DynamoDB number strings, CQL timestamps và binary types có giới hạn khác nhau. Tiền không nên tự đổi sang `double`; timestamp cần timezone/precision rõ; Unicode normalization và null/missing semantics cần được thống nhất.

### 15.4. Mapping failures không phải not-found

Nếu document tồn tại nhưng không decode được schema version mới, adapter phải phân loại lỗi schema/config và báo vận hành; không trả `Optional.empty()` rồi khiến service tạo entity trùng.

## 16. Quản lý schema evolution

Một record v1:

~~~json
{"schemaVersion":1,"orderId":"O-100","total":120000}
~~~

và record v2:

~~~json
{
  "schemaVersion":2,
  "orderId":"O-100",
  "totalMinor":120000,
  "currency":"VND"
}
~~~

### 16.1. Reader hỗ trợ nhiều bản hoặc migrate

Adapter có thể đọc v1 và map sang `Money`, **chỉ khi biết currency của v1 theo dữ liệu/hợp đồng**. Không tự đoán đồng tiền từ vùng hiện tại rồi giả vờ chính xác.

### 16.2. Rolling deployment

Vì nhiều service instances có thể viết schema cũ/mới đồng thời, cần expand–contract, compatibility tests và versioned mapping. Nếu old writer full replace document v2, fields mới có thể bị xóa.

### 16.3. Partial update và full replace khác nhau

`replaceOne` toàn document từ stale object có thể mất fields do writer khác thêm. `PATCH` có điều kiện và CAS/version thường an toàn hơn cho nhiều use cases, nhưng phải xét invariant chéo fields.

### 16.4. Thay Java interface không migrate data

Đổi repository implementation từ MongoDB sang DynamoDB không chuyển dữ liệu lịch sử, indexes, tombstones hoặc CDC checkpoints. Migration là một workflow riêng.

## 17. Identity, tenant isolation và routing

Trong multi-tenant:

~~~text
Entity identity = (tenantId, entityType, entityId)
~~~

`O-100` có thể tồn tại trong hai tenants. Repository phải không đọc/ghi chéo tenant chỉ vì lookup theo ID.

### 17.1. TenantId đến từ ngữ cảnh đã xác thực

User có thể gửi `/tenants/T1/orders/O-100`, nhưng service phải xác minh principal được phép truy cập T1. Không coi path/query string là authorization.

### 17.2. Port nên biểu diễn context cần thiết

~~~java
public record AuthorizedTenantContext(
    String tenantId,
    String principalId
) {}
~~~

Đây là type minh họa; **truyền type không tự enforce quyền**. Authorization phải được thực thi trên đường đọc/ghi và đúng resource scope.

### 17.3. Cache key không được bỏ tenant

`cache.get(orderId)` có thể lộ dữ liệu nếu hai tenants cùng dùng ID. Cache entries/token cần scope theo tenant, permission và serialization version khi thích hợp.

### 17.4. Tenant placement có thể thay đổi

Một whale tenant được chuyển từ shared cluster sang dedicated cluster. Adapter có thể dùng tenant directory trả cluster, region và routing epoch; domain chỉ biết tenant logical ID, nhưng hợp đồng về authority/residency vẫn phải rõ.

### 17.5. Fencing khi đổi owner

Router cache cũ có thể tiếp tục trỏ nguồn cũ. Data plane cần epoch/ownership validation để từ chối stale writer; TTL cache routing không phải cơ chế fencing đủ mạnh.

### 17.6. Data residency

Không tự failover sang region không được phép chỉ vì adapter che địa chỉ cluster. Region constraints cần nằm trong deployment/security policy và được test.

## 18. Lỗi phân tán: commit outcome phải được biểu diễn

Ví dụ:

~~~mermaid
sequenceDiagram
    participant APP as Application
    participant DB as NoSQL Authority
    APP->>DB: Reserve(commandId=C100)
    DB->>DB: Commit mutation + dedupe
    DB--xAPP: Success response lost
    Note over APP: Timeout, outcome unknown
    APP->>DB: ResolveByCommandId(C100)
    DB-->>APP: Previously committed receipt
~~~

Không có transport API nào cho client biết chắc response mất ở bước nào chỉ từ `SocketException`.

### 18.1. Biết commit khác không biết commit

~~~text
KNOWN_COMMITTED
KNOWN_REJECTED_OR_ABORTED
UNKNOWN_OUTCOME
~~~

Một `UNKNOWN` là **sự thiếu tri thức phía client**; database có thể đã commit từ lâu.

### 18.2. Retry an toàn phải giữ identity

`commandId` phải ổn định qua retry, và authority cần ghi/tra outcome theo ID ấy. Tạo UUID khác mỗi lần retry có thể khiến một ý định thành nhiều mutations.

### 18.3. Không dùng eventual index để xác minh absence

Read model chưa thấy `commandId` không chứng minh intent không commit. Dùng authoritative read theo consistency contract hoặc giữ trạng thái Pending cho workflow.

### 18.4. Timeout không tự hủy server operation

Client cancel HTTP sau deadline không chắc database transaction rollback. Nếu backend có thể tiếp tục, application phải lưu thông tin đủ để đối soát.

### 18.5. Retention của dedupe metadata

Nếu command registry bị TTL xóa sau 1 giờ nhưng client có thể retry sau 24 giờ, cùng commandId có thể được chấp nhận lại. Cần documented idempotency window, policy từ chối command quá cũ hoặc durable ledger.

## 19. Chuẩn hóa lỗi nhưng không xóa nguyên nhân

Một error taxonomy bên trong ứng dụng:

~~~java
public enum DataFailureKind {
    INVALID_INPUT,
    NOT_AUTHORIZED,
    BUSINESS_PRECONDITION,
    VERSION_CONFLICT,
    TRANSIENT_TOPOLOGY,
    THROTTLED,
    TRANSACTION_ABORTED,
    UNKNOWN_COMMIT,
    UNSUPPORTED_CAPABILITY,
    STORAGE_CONFIGURATION
}
~~~

### 19.1. Phân loại để quyết định hành động

| Failure | Thông thường nên làm |
|---|---|
| `INVALID_INPUT` | Sửa payload/schema |
| `NOT_AUTHORIZED` | Dừng, điều chỉnh quyền hợp lệ |
| `BUSINESS_PRECONDITION` | Trả rejection có ý nghĩa |
| `VERSION_CONFLICT` | Re-read/revalidate hoặc báo conflict |
| `TRANSIENT_TOPOLOGY` | Refresh route, retry có giới hạn khi an toàn |
| `THROTTLED` | Respect retry hints, backoff/jitter |
| `TRANSACTION_ABORTED` | Retry toàn transaction nếu protocol cho phép |
| `UNKNOWN_COMMIT` | Resolve commandId, không retry mù |
| `UNSUPPORTED_CAPABILITY` | Fail fast/configuration change |
| `STORAGE_CONFIGURATION` | Báo vận hành, không loop vô hạn |

### 19.2. Mã HTTP/gRPC/vendor chỉ là bằng chứng đầu vào

`409` có thể là duplicate, CAS conflict hay business rule. `429` là throttling nhưng có thể tồn tại rất lâu. `504` sau mutation có thể che commit thành công. Classifier không được hardcode `retry=true` chỉ theo một mã.

### 19.3. Transaction abort khác unknown commit

Nếu API xác nhận attempt đã abort, có thể chạy lại toàn **read–validate–write unit**. Nếu commit response mất, phải theo SDK commit retry/resolve protocol và đối soát, không mặc định abort.

### 19.4. Giữ native diagnostics trong hạ tầng

Error label, request ID, substatus, retry-after và topology version vẫn cần log/tracing. Domain chỉ dùng những distinctions có ý nghĩa nghiệp vụ; đừng bỏ thông tin debug khi map exception.

### 19.5. Không log secrets

Không đẩy access token, full document PII hoặc payment data vào exception messages chỉ để hỗ trợ retry. Chọn safe IDs và structured metadata.

## 20. Retry ownership và tổng ngân sách

Một request có các tầng:

~~~mermaid
flowchart TD
    C["Caller"] --> GW["Gateway"]
    GW --> SVC["Application Service"]
    SVC --> REPO["Adapter"]
    REPO --> SDK["SDK auto retry"]
    SDK --> DB["NoSQL"]
~~~

Nếu mỗi tầng retry tối đa ba lần, số attempts có thể **nhân lên** nếu tất cả lặp toàn chuỗi.

### 20.1. Quy định ai retry cái gì

- SDK xử lý topology/transport retries theo tài liệu.
- Adapter map vendor errors và optional infrastructure retries đúng safety.
- Service retry **whole transaction unit** khi known abort và re-read cần thiết.
- Workflow xử lý pending/unknown outcome lâu dài bằng durable queue.
- Gateway/API áp end-to-end deadline và trả status trung thực.

### 20.2. Backoff và jitter

Một mẫu:

\[
d_k = \min(d_{\max},d_0\cdot 2^{k-1})
\]

Kết hợp jitter ngẫu nhiên để nhiều clients không đồng thời retry khi cluster phục hồi. Respect server `Retry-After` nếu có và không sleep vượt deadline.

### 20.3. Circuit breaker và admission control

Nếu một shard mất quorum hoặc hot key bị throttle lâu, tăng retries chỉ làm quá tải. Dùng rate limits, concurrency caps, circuit breaker và retry budgets, nhất là trong multi-tenant SaaS.

### 20.4. Đừng retry external side effect trong transaction callback

Một số SDK có thể chạy lại callback transaction. Nếu callback gọi payment gateway hoặc gửi email, side effect có thể chạy nhiều lần. Ghi outbox/intent atomically rồi xử lý external effects idempotently.

## 21. TTL, delete và lifecycle không phải phép toán đồng nhất

`delete()` có thể là hard delete, logical tombstone, soft delete hoặc request xóa nền.

### 21.1. TTL cleanup khác expiry policy

Một token hết hạn lúc 12:00 vẫn có thể còn item vật lý lúc 12:05 vì TTL daemon chạy nền. Authentication phải kiểm tra `expiresAt` ở đường request, TTL chỉ dọn dữ liệu.

### 21.2. Tombstone chống resurrection

Trong replication, nếu record bị xóa ở một replica nhưng bản cũ ở replica offline, thiếu delete marker có thể làm record hồi sinh khi sync. Port phải có lifecycle semantics, không chỉ gọi native delete.

### 21.3. Privacy erasure

Xóa dữ liệu người dùng có thể cần xóa khỏi cache, search, backups, CDC/object storage và versions cũ theo retention/legal hold policy. Một `repository.deleteById` không tự chứng minh hoàn thành nghĩa vụ erasure.

### 21.4. Distinct domain operations

~~~text
DeactivateCustomer -> business state transition.
EraseCustomerData  -> compliance/lifecycle workflow.
DeleteCacheEntry   -> best-effort cache invalidation.
~~~

Đừng đặt cả ba dưới một semantic contract mơ hồ.

## 22. CachePort nên tách khỏi SourceOfTruthPort

Cache được dùng để giảm latency và cost, nhưng **cache miss** không đồng nghĩa entity không tồn tại.

### 22.1. Cache-aside

~~~text
read cache
    if hit and freshness acceptable: return
    if miss: read authoritative source
    populate cache according to TTL/invalidation policy
~~~

### 22.2. Negative caching

Lưu cache “not found” quá lâu có thể che một entity mới được tạo. Cần TTL/invalidation và phân biệt authoritative absence với projection lag.

### 22.3. Stale-while-revalidate có mục đích cụ thể

Catalog UI có thể chấp nhận stale data; Inventory reservation không được dựa trên stale `available` để báo `RESERVED`. Hai ports/consistency policies nên tách nhau.

### 22.4. Cache invalidation có thể fail

Source commit trước, CDC/event invalidation đến chậm. Nếu caller yêu cầu strong read, phải bypass/validate cache hoặc chọn authoritative path. Không thay guarantee âm thầm vì mục tiêu performance.

## 23. Outbox, events và CDC là những contracts riêng

Một nghiệp vụ:

~~~text
Update Order status=CONFIRMED.
Publish OrderConfirmed event.
~~~

Gọi database rồi broker nối tiếp có failure window: DB commit nhưng publish fail; hoặc event được gửi trước khi transaction hoàn thành.

### 23.1. Transactional outbox

Nếu Order + Outbox intent cùng supported atomic transaction scope, application có thể bảo đảm event intent không thất lạc so với Order state. Publisher thực hiện asynchronous delivery và consumers dedupe theo `eventId`.

### 23.2. Không tự gọi hai writes là atomic

Nếu backend không hỗ trợ transaction chung, phải thiết kế saga/durable intent/CDC mechanism khác. Gom hai lệnh trong `OrderRepository.confirm()` không thay semantics của storage.

### 23.3. Native CDC event không phải integration event schema

Không để downstream services import `MongoChangeStreamDocument` hoặc native DynamoDB stream type để hiểu Order. Adapter/integration layer chuyển thành **domain event** có schema version, stable eventId, aggregateId/version và documented meaning.

### 23.4. Ordering scope

CDC thường có thứ tự trong một partition/stream; không mặc nhiên globally ordered qua mọi shards. Consumer contract phải nói rõ thứ tự và replay/retry semantics.

### 23.5. At-least-once effects

Publisher có thể gửi lại sau ACK lost. Consumers cần idempotency, dedupe retention, checkpoint và reconciliation; don't assume exactly-once external side effects.

## 24. Bulk writes phải phân biệt partial success và transaction

Một API import 10.000 records có thể trả:

~~~json
{
  "batchId":"import-42",
  "items":[
    {"itemId":"r1","state":"COMMITTED"},
    {"itemId":"r2","state":"THROTTLED"},
    {"itemId":"r3","state":"INVALID_INPUT"},
    {"itemId":"r4","state":"UNKNOWN"}
  ]
}
~~~

### 24.1. `saveAll()` không nhất thiết all-or-nothing

Một số APIs hỗ trợ transactional batch trong phạm vi giới hạn; một số khác trả kết quả từng item. Port phải gọi đúng loại operation hoặc exposed per-item results.

### 24.2. Retry từng item theo trạng thái

`r1` không ghi lại; `r2` backoff có giới hạn; `r3` sửa input; `r4` đối soát theo stable ID. Retry cả batch tạo new IDs có thể nhân đôi dữ liệu.

### 24.3. Durable checkpoint

Import worker cần `importId`, item outcome, dedupe key và checkpoint để resume sau crash. Lớp adapter không nên tự giấu partial outcomes rồi chỉ trả boolean.

### 24.4. Ordering

Bulk API có thể chạy parallel/unordered. Nếu nhiều updates cùng aggregate, phải có version/sequence guard, không dựa vào vị trí của item trong danh sách đầu vào.

## 25. Schema và API evolution của port

Đổi:

~~~java
void save(Order order);
~~~

thành:

~~~java
SaveOrderResult saveIfVersion(
    Order order, long expectedVersion
);
~~~

là thay đổi semantics, không chỉ thêm tham số.

### 25.1. Clients cũ cần thích nghi

Caller phải xử lý `VERSION_CONFLICT`. Read model phải cung cấp version đúng scope. Existing documents chưa có version cần migration/default policy được kiểm chứng.

### 25.2. Rolling deployments

Old writers và new writers có thể chạy đồng thời. Nếu old writer vẫn blind replace, CAS ở new service không đủ bảo vệ data. Cần feature gates, write-path migration hoặc fail closed.

### 25.3. Upgrade SDK cũng có thể là breaking semantic change

Một driver đổi retry defaults, session behavior hoặc exception classifications có thể thay business outcomes dù interface Java không đổi. Run contract/integration tests trên version mới.

### 25.4. Contract version cần quản lý

Một port/endpoint thay từ eventual read sang strong read có thể tăng latency/unavailability; ngược lại thay strong bằng eventual là downgrade semantics. Review như thay đổi API, không chỉ infrastructure tuning.

## 26. Migration sản phẩm không phải chỉ đổi adapter bean

Ví dụ chuyển một số tenants từ MongoDB sang DynamoDB:

~~~mermaid
flowchart TD
    R["Xác định contract / capability"] --> M["Thiết kế data model đích"]
    M --> B["Backfill snapshot với checkpoint"]
    B --> C["CDC/catch-up thay đổi và tombstones"]
    C --> V["Đối soát key/version/command outcomes"]
    V --> F["Fence writer cũ, đổi routing epoch"]
    F --> T["Chạy contract/failover tests trên target"]
    T --> E["Retire source theo retention"]
~~~

### 26.1. Access patterns có thể phải thiết kế lại

MongoDB aggregation/filter linh hoạt không tự ánh xạ thành DynamoDB Query không có partition key. Cần index/read model mới; abstraction giảm coupling code nhưng không tạo khả năng truy vấn không tồn tại.

### 26.2. Một source authority trong migration

Ghi A thành công, ghi B timeout là partial dual-write. Nếu không có atomic distributed protocol, cần single authority + CDC/outbox hoặc workflow idempotent có trạng thái rõ.

### 26.3. Cutover phải có fencing

Directory chuyển `tenant T -> cluster B, epoch 18`; service giữ cache epoch 17 phải không tiếp tục ghi A. Ownership enforcement ở data plane là cần thiết.

### 26.4. Backfill bao gồm xóa

Nếu document đã bị xóa sau snapshot nhưng tombstone không được truyền, target có thể hồi sinh record cũ. CDC checkpoint/retention phải bảo đảm delete continuity.

### 26.5. Rollback cũng cần data movement

Sau cutover, target có writes mới. Quay routing về source cũ ngay có thể làm mất chúng. Cần reconciliation/catch-up ngược, owner fencing và data recovery plan.

### 26.6. Contract tests cả hai sides

Đối chiếu atomicity, ACK, unknown outcome, tenant isolation, pagination, schema evolution, index lag và transaction scope; **so JSON giống nhau ở một GET là chưa đủ**.

## 27. Capability-specific ports thay vì “native feature everywhere”

Không phải tính năng vendor nào cũng cần bị cấm. Redis sorted sets, MongoDB aggregation, DynamoDB streams hay Cassandra clustering có thể mang lại hiệu quả lớn.

### 27.1. Bọc theo use case

~~~java
public interface LeaderboardReadPort {
    LeaderboardPage topPlayers(
        String tenantId, String seasonId, int limit
    );
}
~~~

Redis adapter có thể dùng sorted set; adapter khác dùng materialized ranking. Caller biết leaderboard semantics, không cần `ZREVRANGE` và Redis key names.

### 27.2. Có thể tạo một infrastructure extension rõ chủ đích

Admin tooling hoặc analytics chuyên sâu đôi khi cần dùng native SDK trực tiếp trong module riêng, có giới hạn quyền, throughput và ownership. Đừng ép mọi trường hợp vào generic repository nếu khiến query cực tốn hoặc semantic giả.

### 27.3. Hợp đồng unsupported

Nếu adapter không hỗ trợ realtime leaderboards, nó nên báo capability unsupported hoặc dùng một projection được thiết kế. Không fallback sang `findAll()` + sort toàn database trên mọi request.

### 27.4. Port không làm portability tuyệt đối

Chọn NoSQL data model thường phụ thuộc access patterns và partition constraints. Port giảm **diện tích thay đổi** khi chuyển backend nhưng không xóa data migration, index strategy và performance implications.

## 28. Observability không nên làm nhiễm domain types

| Metric hoặc trace | Mục tiêu |
|---|---|
| Operation name | `reserveStock`, `searchOrders` |
| Domain final outcome | Committed/Rejected/Pending |
| Native error class/category | On-call phân tích vendor issues |
| Retry attempts/budget | Phát hiện retry amplification |
| Rate limit/throttle | Noisy neighbor, hot partition |
| p95/p99 latency | Theo dõi SLO thực |
| Routing epoch/stale route | Migration/failover |
| Version conflicts | OCC contention |
| Pending command backlog | Unknown commit reconciliation |
| CDC/outbox lag | Downstream projections |
| Read consistency mode | Phân biệt stale read với data loss |
| Tenant/region distribution | Compliance và capacity |

### 28.1. Business metrics và backend metrics khác nhau

`databaseUp=true` không bảo đảm Checkout thành công. Đo business final outcomes và p99 end-to-end, không chỉ request count của SDK.

### 28.2. Trace và command identity

Một commandId ổn định cho intent; mỗi HTTP attempt có thể có request/trace ID riêng. Telemetry cần liên kết chúng để tìm lần commit đầu khi ACK bị mất.

### 28.3. Bảo vệ dữ liệu nhạy cảm

Không log đầy đủ token, payment data, PII. Với hàng triệu tenants/entities, đừng dùng mọi ID làm metric labels cardinality vô hạn; dùng safe sampling/top-K/traces theo policy.

### 28.4. Giữ diagnostics qua mapping

Map SDK exception sang taxonomy không có nghĩa xóa native request IDs/substatus/retryAfter. Lưu chúng trong diagnostic envelope của infrastructure, tách khỏi public API response.

## 29. Kiểm thử hợp đồng thay vì chỉ mock data access

Một in-memory fake có thể giúp test application flow nhưng **không chứng minh** transaction, durability, consistency hoặc partition correctness trên NoSQL thực.

Hai tầng cần phân biệt:

1. **Application tests:** fake ports trả outcomes có kiểm soát, kiểm tra quyết định service.
2. **Adapter contract/integration tests:** cùng những yêu cầu chạy trên backend thực hoặc test deployment tương đương.

### 29.1. Ma trận test cho adapter

| Test | Điều phải xác minh |
|---|---|
Double submit stable commandId | Không double mutation |
Same ID khác payload | Idempotency mismatch |
Concurrent expectedVersion | Không lost update |
Unknown ACK sau commit | PENDING/resolve, không ghi lần hai |
Leader failover | Ghi đã ACK sống trong fault model |
Tenant A truy cập B | Bị từ chối, không lộ dữ liệu |
Stale projection | Source read vẫn đúng guarantee |
Query page token đổi tenant/filter | Từ chối/không leak |
Partial batch | Per-item outcomes |
TTL cleanup chậm | Expiry policy vẫn đúng |
Delete/CDC replay | Không resurrect document |
Schema v1/v2 | Map không mất precision/field |
Unsupported transaction scope | Fail closed |
Hot partition/throttling | Backoff và budget được tôn trọng |

### 29.2. JUnit contract test skeleton

~~~java
public interface ReservationFixture {
    InventoryReservationPort port();
    void reset(String tenantId, String sku, long available);
    long authoritativeAvailable(String tenantId, String sku);
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

abstract class InventoryPortContractTest {
    protected abstract ReservationFixture fixture();

    @Test
    void sameCommandDoesNotDecrementTwice() {
        var f = fixture();
        f.reset("T1", "SKU-A", 10);

        var cmd = new ReserveStockCommand(
            "cmd-1", "T1", "SKU-A", 2, "O-100"
        );
        assertInstanceOf(
            ReserveStockResult.Committed.class,
            f.port().reserve(cmd)
        );
        assertInstanceOf(
            ReserveStockResult.Committed.class,
            f.port().reserve(cmd)
        );
        assertEquals(8, f.authoritativeAvailable("T1", "SKU-A"));
    }

    @Test
    void differentIntentWithSameCommandIdIsRejected() {
        var f = fixture();
        f.reset("T1", "SKU-A", 10);
        f.port().reserve(new ReserveStockCommand(
            "cmd-1", "T1", "SKU-A", 2, "O-100"
        ));
        var conflicting = f.port().reserve(
            new ReserveStockCommand(
                "cmd-1", "T1", "SKU-A", 3, "O-100"
            )
        );
        assertInstanceOf(
            ReserveStockResult.Rejected.class,
            conflicting
        );
        assertEquals(8, f.authoritativeAvailable("T1", "SKU-A"));
    }
}
~~~

`ReservationFixture` là abstraction minh họa, chưa có implementation nên code không phải một suite chạy độc lập. Production cần integration tests cho race conditions, permission/tenant scope, unknown outcome và failover.

### 29.3. Test success path không chứng minh consistency

Hai sequential requests có thể pass trên bất kỳ database nào. Muốn chứng minh CAS, phải chạy **hai writers đồng thời từ cùng expectedVersion**, đối soát final state.

### 29.4. Fault injection và commit ambiguity

Cho DB commit rồi **cắt response**, không chỉ throw timeout trước gửi request. Kiểm tra port trả Pending/resolve và không double reserve.

### 29.5. Quorum/region fault model

Nếu port hứa durable ACK qua node failure, kiểm tra trên topology và write concern phù hợp. Process kill khác mất host/storage domain; một lần test pass không thay formal vendor guarantee.

## 30. Case study 1: Checkout phụ thuộc driver

Ban đầu:

~~~java
public final class CheckoutService {
    // Pseudocode: vendor-specific types leak into business service.
    private com.mongodb.client.MongoCollection<org.bson.Document> orders;

    public void confirm(String orderId) {
        org.bson.Document order = orders
            .find(new org.bson.Document("_id", orderId))
            .first();
        orders.updateOne(
            new org.bson.Document("_id", orderId),
            new org.bson.Document("$set",
                new org.bson.Document("status", "CONFIRMED"))
        );
    }
}
~~~

Vấn đề:

- Không xác minh tenant/permission.
- Read–then–write không atomic.
- Không kiểm tra trạng thái/expectedVersion.
- Không có idempotency cho command retry.
- Không có outbox intent hoặc transaction scope.
- Service import trực tiếp MongoDB classes.

### 30.1. Phương án thay

~~~text
CheckoutApplicationService
    receives authorized tenant and ConfirmOrder command
    calls OrderConfirmationPort.confirm(command)
    handles Committed, Rejected, Pending

MongoOrderConfirmationAdapter
    maps tenant/order identity to shard key
    issues atomic condition/transaction as needed
    enforces dedupe and outbox contract
    translates vendor errors and diagnostics
~~~

### 30.2. Lợi ích thực tế

Checkout use case độc lập tên collection và SDK. Khi một whale tenant dùng backend khác, service có thể giữ business contract, **nếu** adapter mới thực sự đáp ứng requirements.

### 30.3. Điều abstraction không làm

Nó không tự chuyển dữ liệu, sửa indexes hay tạo transaction capability cho backend mới. Migration và topology design vẫn là dự án kỹ thuật riêng.

## 31. Case study 2: tìm kiếm được dùng sai như authority

Source Order đã committed version 8 nhưng search index mới xử lý version 7. Một service gọi chung `repository.findById()`; implementation lặng lẽ đổi sang search để nhanh hơn. Nó không thấy Order mới, suy Order chưa tồn tại và tạo lại.

### 31.1. Lỗi hợp đồng

Port đã không phân biệt **authoritative read** với **eventual projection read**. Tối ưu hiệu năng vô tình thay đổi correctness guarantee.

### 31.2. Sửa kiến trúc

~~~text
OrderAuthoritativeReadPort:
    for decisions and command outcome reconciliation

OrderSearchPort:
    for UI discovery; eventual, with lag/asOf

OrderCommandPort:
    for versioned mutation/idempotency
~~~

### 31.3. Bằng chứng cần test

Giả lập projection lag; ConfirmOrder phải không dựa vào search absence. Search có thể trả stale đúng contract; authoritative decision path phải giữ invariant.

## 32. Case study 3: chuyển counter sang Redis làm đổi durability

Một ứng dụng có `CounterPort.increment()` trước đây được thực hiện bằng một DB có durable replicated ACK trong failure model đã định. Sau đó đổi Redis primary–replica adapter để tăng tốc mà không thay interface. Primary ACK local rồi chết trước replication, counter có thể bị mất sau promotion tùy cấu hình.

### 32.1. Cùng chữ ký không cùng bảo đảm

`long increment(String key)` không nói write sống qua crash/failover nào. Đây là một **semantic breaking change** dù Java code compile.

### 32.2. Phân vai theo domain

Nếu counter có thể replay từ durable event stream hoặc chỉ dùng telemetry, Redis có thể phù hợp. Nếu counter là balance hoặc quota không được vượt, phải dùng authoritative ledger/conditional operation và durability contract tương ứng.

### 32.3. Retry không tự giải quyết

Sau network timeout, retry INCR có thể tăng hai lần nếu lệnh đầu đã commit; nếu failover làm mất write, retry có thể tạo một lịch sử khác. Cần stable command identity, authoritative outcome và failure-model review.

## 33. Các anti-pattern hay gặp

### “Có interface nghĩa là backend-agnostic”

Không nếu interface expose native SDK types hoặc lời hứa ngầm không đúng.

### “Ẩn mọi consistency để domain đơn giản”

Nếu user code không biết read eventual, nó có thể dùng stale data cho quyết định quan trọng.

### “`saveAll()` mặc định atomic”

Sai ở nhiều bulk APIs; cần transaction scope hoặc per-item results.

### “`findAll()` có thể dùng cho mọi size”

Nguy cơ full scan, fan-out và chi phí không giới hạn.

### “`save()` mặc định upsert an toàn”

Upsert có thể tạo bản ghi ngoài ý muốn hoặc ghi đè state chưa đọc.

### “CAS conflict thì bỏ version rồi ghi lại”

Có thể mất cập nhật của writer khác và phá invariant.

### “`@Transactional` áp dụng cho mọi NoSQL”

Không nếu transaction manager/operation scope không hỗ trợ.

### “Timeout nghĩa là không ghi”

Server có thể đã commit và mất ACK.

### “CommandId có trong request là đủ idempotent”

Server phải ghi nhận/dedupe atomically cùng mutation hoặc protocol tương đương.

### “SDK retry là business exactly-once”

Không. Side effects ngoài DB và command semantics vẫn có thể trùng.

### “Cache miss nghĩa entity not found”

Không; phải phân biệt source vs cache/projection.

### “TTL là lịch xóa chính xác”

TTL cleanup có thể trễ; business expiry phải kiểm tra riêng.

### “Một native transaction luôn xuyên nhiều partitions”

Phạm vi tùy backend/API; không suy từ tên.

### “Cùng tenantId tức cùng shard/transaction”

Không. Tenant whale có thể chia nhiều buckets/partitions.

### “Chỉ cần đổi URL là chuyển database”

Không. Data model, indexes, backfill, CDC và cutover cần xử lý.

### “Dual-write hai databases là một transaction”

Không. Có thể partial success hoặc ambiguous outcome.

### “Versionless read model dùng để check uniqueness”

Một index eventual không thay authoritative uniqueness guard.

### “Domain event là raw change stream payload”

Điều đó khóa consumers vào vendor schema và có thể thiếu business meaning.

### “Một adapter pass unit tests nghĩa là đúng”

Không. Atomicity, concurrent writes, failover, stale reads và durability cần integration/fault tests.

### “Ẩn mọi native feature để portability tối đa”

Có thể làm mất lợi thế NoSQL và tạo full scan fallback nguy hiểm. Cần coupling có chủ đích ở extension layer.

## 34. Checklist thiết kế lớp truy cập dữ liệu

1. **Định nghĩa use case:** command/query nào cần interface?
2. **Ghi identity:** tenant, aggregate, commandId và version scope.
3. **Định nghĩa success:** ACK ở mốc nào, trong fault model nào?
4. **Định nghĩa known reject và unknown:** Không gộp hết thành `false`.
5. **Nêu atomicity:** document/item/partition/multi-shard/region.
6. **Nêu isolation:** serializable, snapshot, CAS hoặc domain guard.
7. **Chọn read guarantee:** authoritative/session/eventual.
8. **Nêu index/query shape:** partition key, max page, ordering, fan-out.
9. **Dedupe intent:** stable command ID, same-key-different-payload policy.
10. **Định nghĩa retry owner:** SDK, adapter, service, workflow.
11. **Giữ deadline/backoff:** tránh retry amplification.
12. **Tách DTO/domain/persistence mappings** khi có biến đổi schema.
13. **Phân quyền tenant ở mọi path:** read/write/cache/batch.
14. **Định nghĩa TTL/delete/retention:** Không xem physical cleanup là business state.
15. **Tách source với search/cache:** Projection lag không phá invariant.
16. **Outbox/events:** Thứ tự, delivery semantics, idempotent consumers.
17. **Capability validation:** Fail fast khi backend không hỗ trợ.
18. **Contract tests:** Concurrent CAS, ambiguous outcome, idempotency.
19. **Resilience tests:** Quorum loss, failover, throttling, stale routing.
20. **Migration runbook:** Backfill, CDC, fence, epoch, reconciliation.
21. **Observability:** Business outcome, version conflicts, native diagnostics.
22. **Ghi deliberate coupling:** Native features chỉ ở ranh giới sở hữu rõ.

### 34.1. Mẫu hợp đồng phục vụ review

~~~yaml
port: InventoryReservationPort
intent: "reserve quantity of SKU for an order"

identity:
  tenant: "authorized tenant scope"
  entity: "InventoryItem"
  commandId: "stable across retries"

correctness:
  businessGuard: "available >= requested quantity"
  atomicityScope: "<verified backend API scope>"
  isolation: "<required and supported isolation>"
  idempotency: "same tenant, commandId and immutable intent"
  mismatchedPayload: "reject"

success:
  response: "Committed with reservation receipt"
  durability: "<ACK and fault-model guarantee>"

failures:
  knownRejected: "no reservation applied"
  unknownCommit: "Pending, authoritative reconciliation"
  permissionDenied: "terminal until authorization changes"

reads:
  authoritative: "<guarantee and route>"
  search: "eventual; not for reservation decisions"

adapter:
  productVersion: "<verified vendor/version>"
  topology: "<regions, partitions, replicas>"
  capabilities: "<transaction, CAS, consistency>"

evidence:
  contractTests: "<run id>"
  failureTests: "<run id>"
  documentation: "<versioned reference>"
~~~

Mẫu chỉ định hướng review, không phải cấu hình production đã được xác minh. Mọi placeholder phải có bằng chứng từ deployment và API thực.

## 35. Bài tập thực hành

### Bài 1 — Phát hiện leakage

Một `OrderRepository` nhận `Bson` filter, `ClientSession` và trả `UpdateResult`. Chỉ ra những chi tiết driver bị rò rỉ, rồi thiết kế operation `confirmIfPending` trả result có nghĩa nghiệp vụ.

### Bài 2 — Generic repository

Giải thích vì sao `saveAll()`, `findAll()` và `save()` không thể có cùng semantics mặc định trên mọi NoSQL. Nêu rủi ro transaction, pagination, fan-out và blind overwrite.

### Bài 3 — Viết semantic contract

Thiết kế port `ReserveStock` có quantity guard, tenant scope, stable commandId, durable ACK, COMMITTED/REJECTED/PENDING và lookup kết quả.

### Bài 4 — CAS và concurrency

Hai writers cùng đọc Order version 7. Viết conditional update logic; giải thích vì sao `get()` rồi `save()` hai lệnh không đủ chống lost update.

### Bài 5 — Unknown commit

Database commit xong nhưng response mất do leader failover. Thiết kế state machine đối soát bằng commandId và trả API response trung thực.

### Bài 6 — MongoDB

Adapter nhận `matchedCount=0` từ conditional update. Khi nào là not-found, wrong tenant, version conflict hoặc business predicate failure? Làm sao không lộ dữ liệu tenant khác?

### Bài 7 — DynamoDB

Thiết kế conditional stock decrement cùng dedupe record trong transaction scope được hỗ trợ. Phân loại throttling, condition failure và timeout sau write.

### Bài 8 — Cosmos DB

Order và Outbox nằm trên hai full logical partition keys khác nhau. Có thể coi hai transactional batches là atomic chung không? Nếu không, cần thay kiến trúc thế nào?

### Bài 9 — Cassandra/ScyllaDB

Một service dùng `SELECT version` rồi `UPDATE` không điều kiện. Hãy phân tích race và thay bằng primitive conditional/LWT phù hợp, kèm chi phí coordination.

### Bài 10 — Redis

Một `CounterPort` được chuyển sang Redis primary–replica. Hãy lập bảng khác biệt ACK/durability/failover và quyết định domain nào chấp nhận được.

### Bài 11 — Đọc authoritative và eventual

Source Order ở version 8 nhưng search index ở version 7. Thiết kế hai read ports và chọn đúng port cho dashboard, checkout và hậu kiểm lệnh.

### Bài 12 — Query contract

Thiết kế `OrderSearchCriteria` với tenant, time range, status, limit, sort và opaque cursor. Nêu max fan-out, token scope, pagination consistency và index requirements.

### Bài 13 — Cache miss

Service coi `CachePort.get()` trả empty là entity không tồn tại và tạo record. Thiết kế cache-aside fallback, negative cache và strong read path.

### Bài 14 — Multi-tenant security

T1 và T2 có cùng OrderId. Thiết kế key, authorization context, cache key và test chống cross-tenant reads.

### Bài 15 — Idempotency collision

Hai requests có cùng `(tenantId, commandId)` nhưng quantity khác. Nêu cách canonicalize payload, lưu intent và từ chối reuse sai.

### Bài 16 — Transaction scope

Order ở shard X, Inventory ở shard Y. Vì sao cùng method repository không tạo atomic checkout? Đề xuất transaction coordinator hoặc saga/escrow.

### Bài 17 — Outbox

Database cập nhật Order thành công nhưng broker publish lỗi. Thiết kế atomic outbox intent, publisher retry và idempotent consumers.

### Bài 18 — TTL

Session hết hạn lúc 12:00 nhưng TTL dọn row lúc 12:05. Làm thế nào bảo đảm authorization ngừng đúng lúc mà vẫn dùng TTL cleanup?

### Bài 19 — Schema v1/v2

Document v1 dùng `total`, v2 dùng `totalMinor`+`currency`. Xây reader/writer mapping, rollback-safe deployment và policy không tự đoán currency.

### Bài 20 — Partial batch

Một import trả 2 committed, 1 throttled, 1 invalid, 1 unknown. Thiết kế result per-item, checkpoint và retry theo ID ổn định.

### Bài 21 — Capability registry

Một backend hỗ trợ single-item atomicity nhưng không cross-partition transaction. Thiết kế capability metadata và fail-fast logic khi một use case bắt buộc atomic Order+Outbox.

### Bài 22 — Adapter migration

Chuyển một tenant từ MongoDB sang DynamoDB. Lập kế hoạch backfill, CDC, tombstones, version checks, routing epoch, fencing, verification và failback.

### Bài 23 — Error taxonomy

Phân loại 412, 429, 403, timeout after write, duplicate command và known transaction abort thành business outcome/hạ tầng action đúng; đừng đơn giản `retry=true` cho tất cả.

### Bài 24 — Contract testing

Thiết kế test suite dùng chung cho hai adapters: double submit, same-key-different-payload, concurrent CAS, stale read, tenant isolation, ACK loss, partial batch và unsupported capability. Nêu giới hạn của in-memory fake.

### Bài 25 — Review kiến trúc

Một tài liệu viết: “Cứ dùng GenericRepository là không phụ thuộc database; `@Transactional` luôn bảo vệ mọi writes; cache miss nghĩa không tồn tại; timeout là rollback; chuyển database chỉ đổi connection string.” Hãy phản biện từng giả định và đưa ra design correction.

---

**Kết luận:** Lớp truy cập dữ liệu là **ranh giới hợp đồng**, không phải chỉ lớp đổi tên driver. Nó giúp domain tránh phụ thuộc BSON, AttributeValue, CQL, native cursors và mã lỗi sản phẩm, nhưng **không được giấu đi** tính nguyên tử, isolation, durability, read consistency, partition scope, idempotency, TTL và unknown commit. Các ports nên xuất phát từ **ý định nghiệp vụ và aggregate invariants**; adapters chỉ triển khai khi sản phẩm thực sự có năng lực đáp ứng. Query ports cần phân biệt source of truth với search/cache, và migrations phải có backfill, CDC, fencing, reconciliation cùng contract tests. Một interface giống nhau chỉ đáng tin khi **hai adapters cùng giữ đúng những bảo đảm đã công bố**, kể cả trong concurrency và failure scenarios.
