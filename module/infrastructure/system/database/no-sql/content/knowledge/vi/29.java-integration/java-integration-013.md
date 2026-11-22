# Giao dịch và cập nhật có điều kiện từ lớp truy cập dữ liệu

Khi lập trình Java kết nối với **Database No SQL**, một phương thức trong Repository như `save()`, `updateOne()` hay `execute()` tưởng chừng chỉ là thao tác kỹ thuật. Nhưng chính nơi này thường quyết định một bất biến nghiệp vụ có được bảo vệ trước nhiều request đồng thời hay không. Nếu hai người cùng mua sản phẩm cuối cùng, hai nhân viên cùng phê duyệt một đơn, hoặc hai worker cùng nhận một job, lớp truy cập dữ liệu (**Data Access Layer – DAL**) phải thực hiện thao tác ghi với **điều kiện được kiểm tra nguyên tử tại database** khi tính đúng đắn đòi hỏi điều đó.

Một ví dụ:

~~~text
Inventory: available = 1

Request A đọc available=1
Request B đọc available=1
Request A muốn giảm 1
Request B muốn giảm 1
~~~

Nếu Java chỉ làm `read()` rồi `save(available - 1)` không có điều kiện, hai request có thể đều tin đã đặt hàng thành công. Cách an toàn hơn là để database thực hiện **conditional decrement**:

~~~text
UPDATE inventory
IF available >= 1
THEN available = available - 1
~~~

Với nghiệp vụ trải nhiều document hoặc nhiều nguồn, ta có thể cần transaction, saga, outbox hoặc một mô hình aggregate phù hợp. Bài học này thuộc chương **Kết nối Java** của **Database No SQL**, tập trung vào cách biểu diễn những bảo đảm đó trong Repository, Unit of Work, driver và service layer.

Các chủ đề chính gồm: atomic operation đơn document; optimistic concurrency với version/ETag; giao dịch nhiều document; isolation, snapshot và write skew; giao diện DAL không che mất semantics của engine; MongoDB Java driver và Spring Data MongoDB; DynamoDB SDK v2; Cassandra lightweight transactions; Redis transaction/Lua; lỗi retry, unknown commit, idempotency, outbox và kiểm thử concurrency.

> **Nguyên tắc trọng tâm:** Kiểm tra điều kiện nghiệp vụ bằng câu lệnh **được thực thi nguyên tử tại nguồn có thẩm quyền**, chứ không dựa vào kết quả đọc trong bộ nhớ Java đã có thể lỗi thời.

## 1. DAL nằm ở đâu trong kiến trúc Java?

Một hệ thống thường có các tầng:

~~~mermaid
flowchart TD
    API["Controller / API"] --> App["Application Service"]
    App --> Domain["Domain Policy / Aggregate"]
    App --> Repo["Repository / DAL"]
    Repo --> Driver["NoSQL Java Driver"]
    Driver --> DB["Authoritative NoSQL database"]
    App --> Out["Outbox / Event dispatcher"]
~~~

**Controller** tiếp nhận request và xác thực ngữ cảnh. **Application Service** điều phối use case và transaction scope. **Domain Policy** quyết định invariant. **DAL** ánh xạ những yêu cầu ấy thành điều kiện read/write có bảo đảm của driver và database.

Ví dụ `OrderService.placeOrder()` có thể gọi `inventoryRepository.reserveIfAvailable()` thay vì tự đọc `available` rồi gọi `inventoryRepository.save()`.

Một Repository tốt không chỉ có CRUD; nó có **những primitive sát với invariant**.

## 2. Ba cấp độ bảo đảm cần phân biệt

| Cấp độ | Phạm vi bảo đảm | Ví dụ |
|---|---|---|
| Atomic operation | Một thao tác database được thực hiện nguyên tử trong phạm vi được hỗ trợ | Conditional update trên một MongoDB document |
| Optimistic concurrency | Chỉ ghi nếu version/ETag hoặc điều kiện vẫn khớp | Compare-and-swap theo `version` |
| Multi-item transaction | Một nhóm read/write được commit hoặc abort theo contract của engine | MongoDB multi-document transaction; DynamoDB TransactWriteItems |
| Cross-service workflow | Nhiều nguồn độc lập, không có transaction nguyên tử chung mặc định | Order + Payment + Shipping với saga/outbox |

Một transaction SQL-style không thể được giả định có đầy đủ guarantees tương đương trong mọi NoSQL. Phải xác minh **phạm vi entity, isolation level, commit acknowledgment, limit và topology** của từng engine.

## 3. Một lệnh ghi nguyên tử khác read-then-write

Phương pháp dễ sai:

~~~java
Inventory inventory = repository.findBySku(sku);
if (inventory.available() >= quantity) {
    repository.save(
        inventory.withAvailable(inventory.available() - quantity)
    );
}
~~~

Hai luồng Java có thể cùng thấy số lượng 1 trước khi ghi. `synchronized` chỉ bảo vệ trong một JVM; nếu có nhiều replica API pods hoặc worker thì không giải quyết concurrency toàn hệ.

Thiết kế tốt hơn:

~~~java
ReservationResult result =
    inventoryRepository.reserveIfAvailable(tenantId, sku, quantity);
~~~

Bên dưới, Repository dùng một atomic conditional update trên nguồn dữ liệu có thẩm quyền.

## 4. Invariant phải được diễn đạt chính xác

Ví dụ tồn kho:

\[
available \ge 0
\]

Một reservation cho số lượng `q` cần giữ:

\[
available_{after}=available_{before}-q
\]

với điều kiện:

\[
q > 0 \quad \text{và} \quad available_{before}\ge q
\]

Điều kiện `q > 0` thường được validate tại service/DAL trước khi gửi. Điều kiện `available >= q` cần được **kiểm tra tại thời điểm ghi** nếu có thể có nhiều writer.

Đối với chuyển trạng thái Order:

~~~text
PENDING -> APPROVED
PENDING -> CANCELLED
APPROVED -> FULFILLED
~~~

Một command có thể yêu cầu `status == PENDING` và `version == expectedVersion`; nếu trạng thái đã đổi thành CANCELLED thì không được cứ retry để ép APPROVED.

## 5. CRUD generic thường không đủ

Một interface:

~~~java
interface GenericRepository<T> {
    T findById(String id);
    void save(T item);
}
~~~

không thể hiện rõ điều kiện, version, commit outcome hay số record được ghi.

Một DAL sát domain hơn:

~~~java
interface InventoryRepository {
    ReserveOutcome reserveIfAvailable(
        String tenantId,
        String sku,
        long quantity,
        String operationId
    );
}
~~~

Các kết quả nên được phân loại:

- `RESERVED`: đã cập nhật thành công.
- `INSUFFICIENT_STOCK`: điều kiện nghiệp vụ không đạt.
- `NOT_FOUND`: không có entity trong scope.
- `ALREADY_APPLIED`: cùng operation ID đã được thực hiện.
- `CONFLICT_RETRYABLE`: state đã đổi nhưng có thể thử lại.
- `UNAVAILABLE` hoặc `UNKNOWN_OUTCOME`: không thể khẳng định kết quả.

Không được dùng `boolean` cho mọi trường hợp nếu caller cần quyết định retry hay trả rejection.

## 6. Atomicity đơn document trong MongoDB

MongoDB bảo đảm atomicity cho các phép cập nhật trên **một document** trong phạm vi thích hợp. Ví dụ:

~~~javascript
db.inventory.updateOne(
  {
    _id: "tenant-17#sku-A",
    available: { $gte: 2 }
  },
  {
    $inc: { available: -2 }
  }
);
~~~

Nếu một request khác đã giảm `available` từ 2 xuống 1 trước khi lệnh chạy, filter `available >= 2` không match. Database không thực hiện phép trừ sai.

Đây là một cách tránh **time-of-check-to-time-of-use race** mà không cần một transaction nhiều document chỉ để thay một field.

## 7. Java MongoDB: conditional update

Ví dụ MongoDB Java Sync Driver:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

public final class MongoInventoryRepository {
    private final MongoCollection<Document> collection;

    public MongoInventoryRepository(
            MongoCollection<Document> collection) {
        this.collection = collection;
    }

    public boolean reserveIfAvailable(
            String tenantId, String sku, long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be > 0");
        }

        String key = tenantId + "#" + sku;
        UpdateResult result = collection.updateOne(
            and(
                eq("_id", key),
                gte("available", quantity)
            ),
            inc("available", -quantity)
        );

        return result.getMatchedCount() == 1;
    }
}
~~~

Đoạn code minh họa API driver, chưa có xử lý idempotency/tenant authorization, timeout và phân biệt `NOT_FOUND` với `INSUFFICIENT_STOCK`.

Điểm quan trọng là **filter và update được gửi thành một operation**. Trả `false` nghĩa điều kiện không match, **không phải mặc định lỗi mạng hoặc lỗi retryable**.

## 8. Vì sao matchedCount và modifiedCount khác nhau?

Các kết quả thường có:

- `matchedCount`: số document phù hợp filter.
- `modifiedCount`: số document thực sự bị thay đổi.

Ví dụ `$set: {status: "ACTIVE"}` lên document vốn đã ACTIVE có thể match nhưng không modify. Không nên chỉ xem `modifiedCount == 0` là conflict nếu operation được phép idempotent no-op.

Với conditional decrement có quantity dương, `matchedCount == 1` là tín hiệu filter đã match. Nhưng nếu write acknowledgment không được bảo đảm hoặc command lỗi trước khi có kết quả, không nên tự suy rằng update thất bại.

## 9. findOneAndUpdate và trạng thái sau ghi

Nếu cần trả về bản mới sau atomic update, MongoDB có `findOneAndUpdate` với lựa chọn trả document sau update.

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;
import org.bson.Document;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

public Document reserveAndReturn(
        MongoCollection<Document> inventory,
        String key,
        long quantity) {

    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be > 0");
    }

    return inventory.findOneAndUpdate(
        and(
            eq("_id", key),
            gte("available", quantity)
        ),
        inc("available", -quantity),
        new FindOneAndUpdateOptions()
            .returnDocument(ReturnDocument.AFTER)
    );
}
~~~

Nếu không có document phù hợp, kết quả có thể là `null`. Caller phải quyết định có cần đọc thêm để phân biệt missing với insufficient stock không; đó là một read khác và có thể thấy state thay đổi sau đó.

## 10. Optimistic locking với version

Document:

~~~json
{
  "_id": "order-100",
  "tenantId": "t-17",
  "status": "PENDING",
  "version": 7
}
~~~

Hai request đều đọc version 7. Cả hai muốn chuyển Order sang trạng thái khác. Chỉ một request có thể ghi thành công nếu DAL yêu cầu `version=7` trong filter và tăng version khi ghi.

~~~javascript
db.orders.updateOne(
  {
    _id: "order-100",
    tenantId: "t-17",
    status: "PENDING",
    version: 7
  },
  {
    $set: { status: "APPROVED" },
    $inc: { version: 1 }
  }
);
~~~

Request thứ hai với expectedVersion 7 không match sau khi request thứ nhất commit version 8.

**Version phải được tăng nguyên tử cùng mutation**; nếu cập nhật version ở hai câu lệnh riêng, concurrency guard có thể bị phá.

## 11. Java Repository có expectedVersion

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

public enum ApprovalOutcome {
    APPLIED, STATE_CHANGED
}

public ApprovalOutcome approve(
        MongoCollection<Document> orders,
        String tenantId,
        String orderId,
        long expectedVersion) {

    UpdateResult result = orders.updateOne(
        and(
            eq("_id", orderId),
            eq("tenantId", tenantId),
            eq("status", "PENDING"),
            eq("version", expectedVersion)
        ),
        combine(
            set("status", "APPROVED"),
            inc("version", 1)
        )
    );

    return result.getMatchedCount() == 1
        ? ApprovalOutcome.APPLIED
        : ApprovalOutcome.STATE_CHANGED;
}
~~~

Ví dụ cố ý gộp missing, unauthorized scope và đã đổi trạng thái thành `STATE_CHANGED` để tránh suy luận sai từ một lookup không match. Một API thực tế có thể bổ sung truy vấn/logic để trả code phù hợp mà không tiết lộ tài nguyên tenant khác.

## 12. Nếu update CAS thất bại thì sao?

Đừng tự thay expectedVersion 7 bằng 8 rồi chạy lại cùng giá trị đã tính. Version mới có thể đi kèm trạng thái mới, price mới hoặc quyền mới.

Quy trình:

~~~text
Read Order(version=7, status=PENDING)
Try approve if version=7
CAS fails
Read current Order(version=8, status=CANCELLED)
Re-evaluate business rule
Return ORDER_NOT_APPROVABLE
~~~

Nếu current Order vẫn PENDING nhưng một field không liên quan đổi, có thể policy cho phép retry; nhưng phải **đọc lại toàn bộ decision dependencies**, không chỉ con số version.

## 13. Một lần đọc trước không thay CAS tại commit

Giả sử Java gọi:

~~~java
Order order = repository.findById(id);
if ("PENDING".equals(order.status())) {
    repository.setStatus(id, "APPROVED");
}
~~~

Giữa hai lệnh, request khác có thể CANCEL Order. Đọc “thấy đúng” không bảo đảm vẫn đúng khi ghi.

Dùng filter `status=PENDING`/expectedVersion tại write-time. Với multi-document invariant, cần transaction hoặc mô hình khác có bảo đảm tương ứng.

## 14. Điều kiện không tồn tại

Bài toán một user chỉ được dùng coupon một lần:

~~~text
Key = tenantId#campaignId#customerId
~~~

Thay vì:

~~~text
Read if CouponUsage exists
If none -> Insert
~~~

hãy dùng **unique key** và conditional insert/unique constraint của database. Hai request có thể cùng đọc “none” trước khi một request ghi.

MongoDB ví dụ:

~~~javascript
db.couponUsages.createIndex(
  { tenantId: 1, campaignId: 1, customerId: 1 },
  { unique: true }
);
~~~

Trên sharded collection phải xét điều kiện unique index tương thích shard key của MongoDB phiên bản triển khai. Không tự khẳng định mọi index unique hoạt động global trong mọi shard design.

## 15. Duplicate key là business conflict hay retry?

Khi insert gặp duplicate:

- Nếu record thuộc **cùng idempotency key** đã commit, có thể trả lại outcome trước.
- Nếu key đã được người khác chiếm, ví dụ username, trả `USERNAME_TAKEN`.
- Nếu duplicate xuất hiện do retry một transaction outcome chưa rõ, phải **reconcile** trước.
- Không retry insert vô hạn với cùng unique key và mong nó tự trở nên trống.

Mã lỗi kỹ thuật cần được map vào outcome nghiệp vụ, không dùng một catch-all `DatabaseException` cho mọi trường hợp.

## 16. Transaction nhiều document cần được chọn có lý do

Ví dụ checkout cần:

~~~text
1. Reserve Inventory
2. Record CouponUsage
3. Create Order
4. Append OutboxEvent
~~~

Nếu invariant yêu cầu bốn thay đổi **cùng commit hoặc cùng abort** và database hỗ trợ transaction trên phạm vi ấy, application service có thể mở một transaction.

~~~mermaid
flowchart TD
    Start["Checkout command"] --> Tx["Begin transaction"]
    Tx --> Read["Read current dependencies"]
    Read --> Check{"Business conditions valid?"}
    Check -->|"No"| Abort["Abort / rejection"]
    Check -->|"Yes"| Writes["Reserve, Order, CouponUsage, Outbox"]
    Writes --> Commit["Commit according to DB protocol"]
    Commit --> End["Return outcome"]
~~~

Không dùng transaction cho những side effects không nằm trong database, như payment gateway, email hoặc hệ queue độc lập, trừ khi có một distributed protocol đặc biệt hỗ trợ đúng scope (thường không có ở lớp DAL đơn giản).

## 17. Transaction scope nên thuộc application service

Repository quản lý query/updates; service quản lý **một use case**.

~~~text
OrderService.checkout()
  -> begin transaction
  -> inventoryRepo.reserve(tx)
  -> couponRepo.consume(tx)
  -> orderRepo.insert(tx)
  -> outboxRepo.append(tx)
  -> commit
~~~

Nếu mỗi repository method tự mở/commit transaction riêng, tổng thể **không còn atomic**:

~~~text
inventoryRepo.reserve() commits
couponRepo.consume() commits
orderRepo.insert() fails
```

Khi đó stock và coupon đã bị trừ mà Order không tồn tại. Cần phối hợp transaction context hoặc chuyển thành workflow có compensation.

## 18. Unit of Work là một abstraction có giới hạn

Một DAL có thể dùng:

~~~java
interface UnitOfWork {
    <T> T inTransaction(TransactionalWork<T> work);
}

@FunctionalInterface
interface TransactionalWork<T> {
    T execute(TransactionContext context);
}
~~~

Ý nghĩa tùy implementation:

- MongoDB: `ClientSession` với transaction.
- Một engine khác: API transaction có limits khác.
- Redis standalone `MULTI` không tương đương snapshot-isolated multi-document transaction.
- Cassandra LWT chỉ cho conditional semantics được hỗ trợ trên scope cụ thể.
- Một service gọi hai databases độc lập **không thể** được cứu bởi một interface tên `UnitOfWork`.

**Abstraction phải mô tả guarantees thật**; không được che khác biệt isolation và commit.

## 19. Java MongoDB: multi-document transaction

Ví dụ MongoDB Sync Driver với `ClientSession` và callback `withTransaction`:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

public final class CheckoutStore {
    private final MongoClient client;
    private final MongoCollection<Document> inventory;
    private final MongoCollection<Document> orders;
    private final MongoCollection<Document> outbox;

    public CheckoutStore(
            MongoClient client,
            MongoCollection<Document> inventory,
            MongoCollection<Document> orders,
            MongoCollection<Document> outbox) {
        this.client = client;
        this.inventory = inventory;
        this.orders = orders;
        this.outbox = outbox;
    }

    public String checkout(
            String tenantId, String sku,
            String orderId, String operationId) {

        TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(WriteConcern.MAJORITY)
            .readPreference(ReadPreference.primary())
            .build();

        try (ClientSession session = client.startSession()) {
            return session.withTransaction(() -> {
                var reserve = inventory.updateOne(
                    session,
                    and(
                        eq("_id", tenantId + "#" + sku),
                        gte("available", 1)
                    ),
                    inc("available", -1)
                );

                if (reserve.getMatchedCount() != 1) {
                    throw new InsufficientStockException();
                }

                orders.insertOne(session, new Document()
                    .append("_id", orderId)
                    .append("tenantId", tenantId)
                    .append("sku", sku)
                    .append("operationId", operationId)
                    .append("status", "PENDING"));

                outbox.insertOne(session, new Document()
                    .append("_id", "event#" + operationId)
                    .append("eventType", "OrderCreated")
                    .append("orderId", orderId));

                return orderId;
            }, options);
        }
    }
}
~~~

`InsufficientStockException` là exception domain giả định, cần tự khai báo. Ví dụ chưa bao gồm mọi check nghiệp vụ, mapping error, unique indexes, read dependencies, timeout và driver version specifics. **Không dùng nó nguyên xi làm checkout production.**

Điểm quan trọng: cả update stock, insert Order và append Outbox đều nhận **cùng session đang có transaction**.

## 20. MongoDB transaction cần deployment hỗ trợ

Không được suy transaction nhiều document luôn khả dụng trên một server tùy ý. Cần deployment/phiên bản MongoDB hỗ trợ transaction (ví dụ replica set hoặc sharded cluster với điều kiện tương ứng).

Cần kiểm tra:

- Transaction support của server/driver.
- Thời gian sống transaction và giới hạn.
- Read/write concern.
- Read preference khi transaction.
- Index/unique constraints.
- Shard targeting và cross-shard transaction costs.
- Retryable error labels.
- Không chạy các operation song song trên cùng `ClientSession` nếu driver không hỗ trợ.
- Không giữ transaction mở trong lúc gọi external HTTP API.

## 21. withTransaction có thể chạy callback nhiều lần

Một driver helper có thể tự retry callback cho những transaction errors phù hợp. Vì vậy:

~~~java
session.withTransaction(() -> {
    updateInventory(session);
    paymentGateway.charge(card, amount);
    emailService.sendReceipt(email);
    return orderId;
});
~~~

là thiết kế nguy hiểm. Nếu transaction bị abort/retry, payment hoặc email có thể xảy ra nhiều lần, trong khi database chỉ commit một attempt.

Thay bằng:

~~~text
Transaction:
  validate
  reserve stock
  insert Order
  insert OutboxEvent
  commit

Worker after commit:
  dispatch OrderCreated
  process payment with stable idempotency key
  reconcile unknown external result
~~~

Outbox worker cũng phải xử lý duplicate message và crash giữa send/ack.

## 22. Read set phải nằm trong attempt cần retry

Sai:

~~~text
price = readPriceOutsideTransaction()
coupon = readCouponOutsideTransaction()

retryTransaction(() -> {
    stock = readStock()
    total = price - coupon
    insertOrder(total)
})
~~~

Nếu transaction abort và được chạy lại, price/coupon cũ vẫn được giữ. Khi quyết định cần mức giá/quota hiện hành, phải đọc lại những state mutable trong consistency scope phù hợp.

Tốt hơn:

~~~text
retryTransaction(() -> {
    price = readPriceFromAuthority()
    coupon = readCouponFromAuthority()
    stock = readStockFromAuthority()
    validateAndCalculate()
    reserveAndCreateOrder()
})
~~~

Nếu một price quote là immutable và còn hiệu lực theo hợp đồng, có thể dùng lại quote; nhưng cần xác minh điều kiện hiệu lực và version tại commit.

## 23. Transaction isolation không phải một nhãn tùy ý

Một transaction API cần nêu:

- Atomicity cho tập writes nào?
- Read được nhìn theo snapshot nào?
- Có ngăn dirty read/non-repeatable read không?
- Có bảo vệ predicate/phantom không?
- Có cho phép write skew không?
- Write conflict được phát hiện thế nào?
- Read/write đến những region nào?
- Khi commit response mất, recovery ra sao?

**Snapshot isolation không mặc nhiên bằng serializable isolation**. Phải xem guarantees của engine và tình huống cụ thể.

## 24. Write skew: đọc nhiều document nhưng ghi khác document

Quy tắc: ít nhất một bác sĩ phải trực.

~~~text
Doctor A: onCall=true
Doctor B: onCall=true

T1 reads A,B -> writes A=false
T2 reads A,B -> writes B=false
~~~

Nếu hai writes không đụng cùng document, một số hệ snapshot isolation có thể để cả hai commit và làm invariant bị phá.

Cách bảo vệ:

- Serializable isolation nếu engine hỗ trợ đúng phạm vi.
- Một owner/counter document được cập nhật có điều kiện.
- Mô hình aggregate gom invariant vào cùng document phù hợp.
- Coordination protocol khác đã được chứng minh.

**Transaction nhiều document không tự biến mọi predicate read thành serializable**.

## 25. Phantom và sự vắng mặt

Quy tắc: một phòng không có hai booking trùng khoảng.

~~~text
T1 queries overlapping bookings -> none
T2 queries overlapping bookings -> none
T1 inserts booking A
T2 inserts booking B
~~~

Nếu database không bảo vệ predicate, hai transactions có thể cùng commit. Chỉ đọc “none” bên trong transaction không đủ nếu isolation không ngăn write skew/phantom.

Có thể mô hình hóa room-time slots bằng unique owner keys, constraint được thực thi ở write-time, hoặc một cơ chế serialization phù hợp. Cần cân bằng độ lớn slot và khoảng thời gian.

## 26. Atomic conditional owner document

Ví dụ bác sĩ đang trực có một policy document:

~~~json
{
  "_id": "hospital-17#on-call",
  "onCallCount": 2,
  "version": 11
}
~~~

Khi bác sĩ off-call, transaction phải giảm `onCallCount` với điều kiện `onCallCount >= 2`, đồng thời ghi trạng thái bác sĩ nếu nằm ở document khác.

Cả hai transaction tranh cùng policy document để database nhận diện conflict. Tuy nhiên policy document có thể thành **hot spot**, cần đánh giá throughput/partitioning.

## 27. MongoDB @Version trong Spring Data

Spring Data MongoDB hỗ trợ optimistic locking bằng annotation `@Version` trong những trường hợp sử dụng phù hợp.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public class OrderDocument {
    @Id
    private String id;

    private String tenantId;
    private String status;

    @Version
    private Long version;

    // Constructors/getters/setters theo dự án.
}
~~~

Khi dùng những phương thức save được hỗ trợ, framework có thể đưa version hiện hành vào điều kiện cập nhật và tăng version. Nếu version không match, một exception optimistic locking có thể được phát ra.

Nhưng:

- Không phải mọi `MongoTemplate.update...` tùy biến tự tuân theo cùng một `@Version` contract.
- Acknowledged writes quan trọng để phát hiện mismatch theo semantics phù hợp.
- Phải biết cách entity mapping xử lý initial/null version.
- Không tự retry `save()` của object cũ mà chưa reload/re-evaluate.
- Không coi `@Version` thay thế business condition `status == PENDING`.

## 28. Spring @Transactional và MongoDB

Ví dụ minh họa service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderApplicationService(
            OrderRepository orders,
            InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void confirmOrder(String orderId) {
        OrderDocument order = orders.load(orderId);
        inventory.reserveFor(order);
        orders.markConfirmed(order);
    }
}
~~~

Đây là skeleton Java/Spring **không biên dịch nguyên xi** nếu chưa khai báo các Repository types và transaction manager.

Quan trọng hơn: `@Transactional` **chỉ có hiệu lực khi Spring transaction infrastructure được cấu hình đúng cho datastore**, ví dụ `MongoTransactionManager` khi dùng MongoDB với deployment hỗ trợ. Annotation tự nó không tạo một distributed transaction qua MongoDB, Redis và một payment API.

## 29. Spring transaction proxy và self-invocation

Trong cơ chế Spring proxy phổ biến:

~~~java
public void outer() {
    innerTransactionalMethod();
}

@Transactional
public void innerTransactionalMethod() {
    // ...
}
~~~

Nếu lời gọi là **self-invocation** trong cùng object, nó có thể không đi qua transaction proxy, khiến annotation không có hiệu lực như kỳ vọng. Cần hiểu Spring proxy/AOP, transaction manager, exception rollback rules và reactive transaction context.

Đừng suy “method có annotation” đồng nghĩa mọi operation bên trong đang nằm trong một transaction thật. Kiểm thử phải xác minh rollback/commit thực tế.

## 30. Transaction context truyền vào Repository

DAL có thể chọn:

1. **Explicit context:** Repository nhận `ClientSession`/transaction context và dùng trong mọi operation.
2. **Framework-bound context:** Repository/Template nhận session từ transaction manager/context đang active.
3. **Application-level Unit of Work:** wrapper điều phối nhưng phải map vào scope thật của engine.

Với explicit MongoDB session, rất dễ quên truyền session vào một query:

~~~java
orders.insertOne(session, order);
audit.insertOne(auditEvent); // Không truyền session.
~~~

Nếu audit write nằm ngoài transaction, commit/abort không bao trùm nó. Dùng API consistent và test rollback để phát hiện những operation thoát transaction scope.

## 31. Repository không được giấu non-atomic fallback

Một interface:

~~~java
interface WalletRepository {
    void transfer(String from, String to, long amount);
}
~~~

Nếu implementation:

~~~text
debit(from)
credit(to)
```

mà không có transaction/ledger protocol, interface tạo ấn tượng sai rằng chuyển tiền nguyên tử.

Tốt hơn:

- Nêu transaction scope được hỗ trợ.
- Thực hiện transfer trong engine transaction đúng phạm vi.
- Hoặc dùng ledger entries/booking workflow với state machine và recovery rõ.
- Trả outcome `PENDING` khi external/multi-source workflow chưa hoàn tất.

Tên phương thức không thay thế guarantee.

## 32. DynamoDB: conditional UpdateItem

DynamoDB có conditional writes. Một update có thể giảm stock khi version và available phù hợp.

~~~java
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.*;
import java.util.Map;

public boolean reserve(
        DynamoDbClient client,
        String pk,
        String sk,
        long quantity,
        long expectedVersion) {

    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be > 0");
    }

    UpdateItemRequest request = UpdateItemRequest.builder()
        .tableName("Inventory")
        .key(Map.of(
            "pk", AttributeValue.fromS(pk),
            "sk", AttributeValue.fromS(sk)
        ))
        .updateExpression(
            "SET available = available - :q, "
          + "version = version + :one"
        )
        .conditionExpression(
            "attribute_exists(pk) AND available >= :q "
          + "AND version = :v"
        )
        .expressionAttributeValues(Map.of(
            ":q", AttributeValue.fromN(Long.toString(quantity)),
            ":one", AttributeValue.fromN("1"),
            ":v", AttributeValue.fromN(Long.toString(expectedVersion))
        ))
        .build();

    try {
        client.updateItem(request);
        return true;
    } catch (ConditionalCheckFailedException ex) {
        return false;
    }
}
~~~

Đây là ví dụ AWS SDK for Java v2 trên table có key `pk` + `sk` và thuộc tính số đã được khởi tạo. Không dùng `false` để gộp cả network timeout; exception transport/throttling phải có phân loại khác.

## 33. ConditionExpression là phần bảo vệ bất biến

Một lần `GetItem` trước đó không đủ vì dữ liệu có thể đổi. ConditionExpression trên write kiểm tra điều kiện **nguyên tử theo semantics DynamoDB**.

Các thao tác hữu ích:

- `attribute_not_exists(pk)` để conditional create theo key.
- `version = :expected` để optimistic concurrency.
- `available >= :q` để chặn số âm.
- `status = :pending` để bảo vệ state transition.
- Kiểm tra timestamp/lease generation khi được mô hình hóa đúng.

Không đưa mọi điều kiện ngoài transaction rồi chỉ tin vào kết quả GET. Điều kiện nào quyết định tính đúng phải được bảo vệ ở write boundary.

## 34. DynamoDB: TransactWriteItems

Một use case nhiều items có thể dùng `TransactWriteItems` với các action Put/Update/Delete/ConditionCheck trong phạm vi API hỗ trợ.

~~~java
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.*;
import java.util.List;
import java.util.Map;

public void createOrderAtomically(
        DynamoDbClient client,
        String operationId,
        String orderPk,
        String orderSk) {

    Put orderPut = Put.builder()
        .tableName("Orders")
        .item(Map.of(
            "pk", AttributeValue.fromS(orderPk),
            "sk", AttributeValue.fromS(orderSk),
            "status", AttributeValue.fromS("PENDING")
        ))
        .conditionExpression("attribute_not_exists(pk)")
        .build();

    TransactWriteItemsRequest request =
        TransactWriteItemsRequest.builder()
            .clientRequestToken(operationId)
            .transactItems(
                TransactWriteItem.builder().put(orderPut).build()
            )
            .build();

    client.transactWriteItems(request);
}
~~~

Ví dụ chỉ có một Put để cho thấy hình dạng transaction API, **không phải checkout đa item hoàn chỉnh**. Thực tế cần thêm transactional Inventory/Coupon/Idempotency/Outbox actions phù hợp API limits, item ownership và key design.

**DynamoDB không cho hai actions trong cùng TransactWriteItems cùng tác động một item**; thiết kế phải tránh ghép `ConditionCheck` và `Update` riêng cho đúng item ấy. Hãy đưa condition vào action Update/Put tương ứng.

## 35. DynamoDB client request token không thay business idempotency

`clientRequestToken` giúp idempotency cho `TransactWriteItems` trong **thời hạn và semantics được dịch vụ công bố**. Không được xem nó là chứng chỉ exactly-once vô hạn thời gian.

Nếu cùng token nhưng payload thay đổi trong idempotency window, dịch vụ có thể trả lỗi mismatch theo API. Một idempotency key ở tầng nghiệp vụ nên:

- Ổn định cho một ý định.
- Được namespace theo tenant/operation.
- Có payload hash để phát hiện key reuse khác request.
- Có durable mapping từ key tới outcome.
- Có retention đủ cho retry/offline period mà nghiệp vụ yêu cầu.
- Không chứa thông tin nhạy cảm.

## 36. DynamoDB transaction cancellation cần phân loại

Một transaction có thể bị hủy vì:

- Transaction conflict.
- Condition không đạt.
- Validation/schema lỗi.
- Capacity/throttling.
- Giới hạn hoặc ràng buộc API.
- Khác biệt cấu hình region/table/index.

Không gộp `TransactionCanceledException` thành “retry mọi lúc”. Với condition `available >= 1` không đạt, đó có thể là **SOLD_OUT**, không phải transient error.

Tùy SDK và service, cancellation reasons có thể hỗ trợ điều tra; cần xử lý theo code/contract cụ thể, không parse chuỗi lỗi tự do.

## 37. DynamoDB read consistency và GSI

DynamoDB có lựa chọn strong/consistent reads trong một số API/scope được hỗ trợ, nhưng **GSI không hỗ trợ strongly consistent reads** như base table.

Nếu ứng dụng đọc GSI để tìm một item rồi cập nhật, GSI có thể stale. Phải dùng authoritative key và conditional write tại source khi invariant quan trọng.

Global Tables có replication/conflict semantics theo chế độ triển khai; một transaction trong region không tự là transaction tuyến tính xuyên mọi region.

## 38. Cassandra: LWT thay cho arbitrary transaction

Cassandra cung cấp Lightweight Transactions (LWT) với conditional operations như `IF version = ?` hoặc `IF NOT EXISTS` trong phạm vi được hỗ trợ.

Ví dụ CQL:

~~~sql
UPDATE inventory
SET available = ?, version = ?
WHERE tenant_id = ?
  AND sku = ?
IF version = ?;
~~~

Ở tầng Java:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.*;

public final class CassandraInventoryRepository {
    private final CqlSession session;
    private final PreparedStatement statement;

    public CassandraInventoryRepository(CqlSession session) {
        this.session = session;
        this.statement = session.prepare(
            "UPDATE inventory SET available=?, version=? "
          + "WHERE tenant_id=? AND sku=? IF version=?"
        );
    }

    public boolean compareAndSet(
            String tenantId,
            String sku,
            long newAvailable,
            long newVersion,
            long expectedVersion) {

        BoundStatement bound = statement.bind(
            newAvailable, newVersion,
            tenantId, sku, expectedVersion
        );

        ResultSet result = session.execute(bound);
        Row row = result.one();
        return row != null && row.getBoolean("[applied]");
    }
}
~~~

Đây là ví dụ driver 4.x-style: trước khi gọi cần đọc trạng thái và **tính toán điều kiện nghiệp vụ**, đồng thời mapping type/CQL column phải khớp schema. Một kết quả `[applied]=false` là **conditional check không đạt**, không tự là lỗi mạng.

## 39. Cassandra LWT có giới hạn phạm vi

Đừng suy từ một conditional update Cassandra rằng hệ có arbitrary serializable transaction qua nhiều partitions.

Cần nắm:

- Partition key và phạm vi Paxos/LWT.
- Consistency/serial consistency levels.
- Performance/latency của LWT so với write thường.
- Các giới hạn statement/batch.
- Retry behavior và duplicate command.
- Điều kiện một row/partition không bao trùm invariant trải nhiều entities.

Một transfer giữa hai account ở những partitions khác nhau cần mô hình ledger/workflow hay hạ tầng transaction được thiết kế đúng; không thể chỉ thêm `IF` ở một row rồi tự gọi nó atomic xuyên hai partitions.

## 40. Cassandra: điều kiện số dư không được suy từ giá trị cũ

Giả sử:

~~~text
Read credits=10, version=7
Want debit 8 -> proposed credits=2, version=8
LWT IF version=7 fails
~~~

Retry sai là giữ `credits=2` rồi thay expected version bằng 8. Một giao dịch khác có thể đã trừ 5, nên credits hiện tại chỉ còn 5.

Retry đúng:

1. Đọc current state.
2. Tính lại proposed value.
3. Kiểm tra `credits >= debit`.
4. Dùng conditional update theo version mới.
5. Dừng với business rejection nếu không đủ.

Với bất biến có thể được biểu diễn trong một primitive atomic phù hợp, ưu tiên để engine kiểm tra điều kiện tại ghi thay vì vòng read–modify–write dễ sai.

## 41. Redis MULTI/EXEC không phải transaction ACID chung

Redis `MULTI`/`EXEC` gom nhiều commands và thực thi tuần tự trong một lượt theo semantics Redis, nhưng **không cung cấp rollback theo kiểu transaction SQL khi một command có lỗi runtime**.

Không được cho rằng:

~~~text
MULTI
DECRBY wallet:A 100
INCRBY wallet:B 100
EXEC
```

có cùng guarantees về validations, durability, rollback và failover như một database có transaction ACID. Muốn bảo vệ invariant `wallet:A >= 100`, cần đưa điều kiện vào một atomic script/function/command phù hợp hoặc dùng một nguồn authoritative có transactional guarantees thích hợp.

Redis trong nhiều hệ là cache/queue helper; dùng làm nguồn sổ cái tài chính cần đánh giá durability/failover rất kỹ.

## 42. Redis WATCH/MULTI/EXEC là optimistic concurrency

Mẫu:

~~~text
WATCH inventoryKey
GET inventoryKey
if value < requested:
    UNWATCH
    return SOLD_OUT

MULTI
DECRBY inventoryKey requested
EXEC
~~~

Nếu key bị writer khác thay đổi trước `EXEC`, transaction có thể không được thực thi. Client cần **WATCH lại, đọc lại, tính lại** theo vòng retry giới hạn.

Một kết quả `EXEC` bị abort do WATCH khác với `EXEC` đã chạy command nhưng response mạng mất.

## 43. Redis với Lettuce trong Java

Pseudo-code synchronous Lettuce cho một connection **không chia sẻ đồng thời** giữa các luồng transaction:

~~~java
import io.lettuce.core.RedisClient;
import io.lettuce.core.TransactionResult;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.sync.RedisCommands;

public final class RedisReservation {
    public boolean reserve(
            RedisClient client, String key, long quantity) {

        if (quantity <= 0) {
            throw new IllegalArgumentException();
        }

        try (StatefulRedisConnection<String, String> conn =
                 client.connect()) {
            RedisCommands<String, String> commands = conn.sync();

            for (int attempt = 1; attempt <= 3; attempt++) {
                commands.watch(key);
                String raw = commands.get(key);

                if (raw == null || Long.parseLong(raw) < quantity) {
                    commands.unwatch();
                    return false;
                }

                commands.multi();
                commands.decrby(key, quantity);
                TransactionResult result = commands.exec();

                if (!result.wasDiscarded()) {
                    return true;
                }

                // Backoff theo deadline; lần sau WATCH/GET lại.
            }
            return false;
        }
    }
}
~~~

Ví dụ phục vụ giải thích WATCH semantics; cần xử lý parse errors, network unknown outcome, reconnect, Redis Cluster slot constraints, backoff, error classification và pooling đúng trước khi dùng thật. `false` cuối vòng lặp trong thiết kế production nên phân biệt `RETRY_EXHAUSTED` với `SOLD_OUT`.

Trong Redis Cluster, các multi-key operations thường phải thỏa quy tắc cùng hash slot; `WATCH/MULTI` không tự là distributed transaction giữa slots.

## 44. Redis Lua/Functions cho bất biến một key

Một atomic script:

~~~lua
local available = tonumber(redis.call('GET', KEYS[1]) or '0')
local qty = tonumber(ARGV[1])

if qty == nil or qty <= 0 then
  return redis.error_reply('INVALID_QUANTITY')
end

if available < qty then
  return 0
end

redis.call('DECRBY', KEYS[1], qty)
return 1
~~~

Script thực thi nguyên tử trong Redis server theo semantics tương ứng; tránh cửa sổ giữa GET và DECRBY.

Nhưng:

- Atomic execution không đồng nghĩa durable commit qua mọi failover.
- Redis Lua script có thể ảnh hưởng event loop nếu chạy lâu.
- Với Redis Cluster, keys phải tuân thủ slot constraints.
- External side effects vẫn nằm ngoài script.
- Retry sau network timeout cần idempotency vì script có thể đã chạy.

## 45. Điều kiện ở DAL phải dùng kiểu dữ liệu chuẩn

Nếu source lưu `available` là number nhưng Java filter gửi string `"5"`, điều kiện so sánh có thể không hoạt động như mong muốn.

Các vấn đề khác:

- BSON Long vs Integer vs Decimal128.
- DynamoDB Number dưới dạng chuỗi biểu diễn số.
- Cassandra bigint/decimal và Java type mapping.
- Currency `amountMinor` và currency code.
- Date/UTC, TTL và server-side time.
- Missing/null semantics.
- Case normalization cho username/email.
- Prefix tenant namespace.

Một conditional write chỉ đúng khi **schema, units, field types và normalization** cũng đúng.

## 46. Money không nên dùng floating point tùy tiện

Đối với thanh toán:

~~~text
priceMinor = 1290000
currency = VND
```

hoặc dùng kiểu decimal được engine/driver hỗ trợ và quy tắc rounding minh bạch. Không dùng `double` rồi so số tiền chính xác hoặc update balance bằng phép tính floating-point có thể gây sai lệch.

Java có thể dùng `BigDecimal` cho tính toán tiền, nhưng phải thống nhất scale/currency khi serialize sang BSON/NoSQL types. Conditional compare cần cùng đơn vị.

## 47. Version phải có lifecycle rõ

Một field `version` hữu ích khi:

- Tăng mỗi mutation liên quan.
- Được ghi nguyên tử cùng data.
- Không bị reset tùy tiện sau restore.
- Tách `entityVersion` với `schemaVersion`.
- Có `generation` nếu ID tái sử dụng.
- Không dùng timestamp từ client làm expectedVersion nếu clocks không đáng tin.
- Có semantics cho create/delete/tombstone.

Ví dụ một document bị xóa rồi tạo lại cùng ID, version cũ của entity trước không tự xác định thứ tự với version mới. Cần ID không tái sử dụng hoặc generation/epoch.

## 48. Predicate-level invariant đòi thiết kế khác CAS một document

Một quy tắc:

~~~text
Mỗi người chỉ được có tối đa năm booking ACTIVE.
```

Một `SELECT COUNT` rồi insert có thể race. Optimistic lock trên **booking mới** không ngăn hai requests tạo hai booking khác nhau vượt giới hạn.

Có thể cần:

- Counter/owner document điều phối quota.
- Unique/conditional token cho từng slot.
- Transaction có write conflict chung.
- Serializable predicate protection nếu engine hỗ trợ.
- Queue serialize theo customer/aggregate.
- Thiết kế quota reservation với TTL/fencing phù hợp.

Đây là vấn đề **mô hình invariant**, không thể giải quyết bằng cách thêm `@Version` lên mọi entity rồi hy vọng.

## 49. Unique constraint và sharding

Một unique index trong hệ sharded có thể bị giới hạn bởi shard-key prefix hoặc cách engine triển khai. Một key `email` được yêu cầu unique **toàn hệ** nhưng collection sharded theo `tenantId` đòi thiết kế rõ uniqueness scope:

- Unique email trong mỗi tenant.
- Unique email toàn hệ.
- Normalization email/username.
- Ownership của global directory.
- Race khi tạo entity và record uniqueness.

Đừng chỉ định một index và giả định database có thể enforce mọi global uniqueness trong mọi topology. Có thể cần authoritative registry/collection khác với shard key phù hợp.

## 50. Transaction hay saga?

So sánh:

| Trường hợp | Hướng thường phù hợp |
|---|---|
| Điều kiện trên một document | Atomic conditional update |
| CAS theo version một entity | Optimistic locking |
| Nhiều documents trong cùng database có transaction support | DB transaction |
| Nhiều partitions nhưng engine chỉ hỗ trợ conditional single partition | Redesign aggregate, ledger hoặc workflow |
| Ghi Order DB và charge Payment gateway | Saga/outbox/idempotency |
| Publish event sau Order commit | Transactional outbox |
| Ghi cache/search projection | Eventual projection + reconciliation |
| Workflow dài nhiều phút/giờ | Durable state machine, không giữ DB transaction mở |

**Không giữ transaction mở trong lúc chờ người dùng hoặc external API**. Transaction nên ngắn và giới hạn trong phạm vi database hỗ trợ.

## 51. Idempotency key là business contract

Client retry sau timeout có thể gửi cùng một ý định nhiều lần:

~~~text
POST /orders
Idempotency-Key: checkout-K100
```

Nếu lần đầu đã commit nhưng response mất, service không nên tạo Order thứ hai.

Một record idempotency có thể gồm:

~~~json
{
  "_id": "t-17#Checkout#checkout-K100",
  "requestHash": "canonical-request-digest",
  "status": "COMPLETED",
  "resourceId": "order-101",
  "resultCode": "CREATED"
}
~~~

Cần bảo vệ unique key trong cùng authoritative scope, phát hiện reuse khác payload, xác định retention và response recovery.

**Retry của driver khác retry của client/queue.** Idempotency cần được thiết kế end-to-end, không chỉ dựa vào một SDK retry flag.

## 52. Unknown commit result không phải transaction abort

Timeline:

~~~text
t0 Client gửi COMMIT
t1 Database commit thành công
t2 Network mất response
t3 Java nhận timeout
```

Java không biết transaction đã commit hay chưa. Nếu tự mở một transaction khác và thực thi lại body, có thể nhân đôi business effect.

Phải dùng khả năng retry commit của driver khi phù hợp, hoặc tra idempotency record/reconcile outcome. Trong MongoDB, lỗi có nhãn như `UnknownTransactionCommitResult` có semantics khác với lỗi cần retry **whole transaction**.

Không parse error text như `"timeout"` rồi mặc định “chưa ghi”.

## 53. Retryable transaction abort cần chạy lại decision

Ví dụ transaction đọc:

~~~text
Inventory v10
Price v5
Coupon v3
```

rồi bị write conflict do Inventory bị cập nhật. Retry đúng:

1. Đóng/abort attempt cũ theo driver.
2. Mở transaction/snapshot mới.
3. Đọc lại các **decision dependencies** có thể thay đổi.
4. Tính lại quantity, price, discount, quyền, quota.
5. Thực hiện conditional writes/transaction mới.
6. Commit.
7. Nếu conflict tiếp, backoff và thử trong deadline.

Không chỉ retry câu UPDATE cuối với price hoặc coupon từ attempt trước nếu nghiệp vụ yêu cầu state hiện hành.

## 54. Phân loại lỗi ở DAL

Một bộ categories:

~~~java
public sealed interface WriteOutcome
        permits Applied, BusinessRejected,
                RetryableConflict, UnknownOutcome,
                TemporarilyUnavailable {}

record Applied(String resourceId) implements WriteOutcome {}
record BusinessRejected(String reason) implements WriteOutcome {}
record RetryableConflict(String code) implements WriteOutcome {}
record UnknownOutcome(String operationId) implements WriteOutcome {}
record TemporarilyUnavailable(String code) implements WriteOutcome {}
~~~

Đây là Java 17+-style DTO minh họa. Cần implement mapping theo driver/version:

- MongoDB duplicate key, write conflict, transaction labels.
- DynamoDB conditional check failed, transaction canceled, throttling.
- Cassandra LWT `[applied]` và timeouts.
- Redis WATCH aborted, `EXEC` error và transport uncertainty.

Không che mất distinction giữa **business rejection** và **retryable transient error**.

## 55. Một transaction result có thể bị phân loại lại sau khi đọc

Ví dụ một CAS không match:

~~~text
Expected status=PENDING, version=7
matchedCount=0
```

Có thể vì:

- Order không tồn tại.
- Order đã APPROVED bởi cùng operation ID.
- Order đã CANCELLED bởi actor khác.
- Version tăng nhưng status vẫn PENDING.
- Tenant scope không khớp.
- Condition khác thay đổi.

Nếu API muốn trả outcome cụ thể, DAL/service có thể đọc lại authoritative state. Nhưng cần tránh **lộ sự tồn tại record của tenant khác** qua thông báo lỗi. Và trạng thái đọc sau đó vẫn có thể đổi tiếp; nó là tín hiệu giải thích, không thay atomic condition đã được thực thi.

## 56. Bounded retry và backoff

Retry một hot document ngay lập tức có thể tạo storm:

~~~text
Higher contention
  -> more transaction aborts
  -> more retries
  -> even higher contention
```

Có thể dùng exponential backoff with full jitter:

\[
delay_a = U(0,\min(maxDelay,baseDelay\cdot 2^{a-1}))
\]

Trong đó `a` là số attempt, `U` lấy một delay ngẫu nhiên trong khoảng. Giới hạn:

- `maxAttempts`.
- Deadline toàn request.
- Maximum backoff.
- Số attempts ở SDK và application layer.
- Cancellation.
- Transaction lifetimes.
- Quote/lease expiry.
- Operation priority.

Không chờ backoff **bên trong transaction đang mở**, vì giữ resource vô ích.

## 57. Nhiều tầng retry có thể nhân tải

Giả sử:

~~~text
HTTP gateway retries 3
Application service retries 3
Driver retries 3
```

Về mặt tổ hợp, cùng một business intent có thể phát sinh nhiều attempts ở backend, làm tăng rủi ro storm.

Cần một retry policy thống nhất theo deadline, idempotency và capabilities. Không tắt hoàn toàn driver retries khi không hiểu semantics, nhưng cũng không mặc định tất cả tầng đều nên retry mọi lỗi ba lần.

## 58. Transactional outbox

Một use case cần ghi Order và phát event:

~~~text
Database transaction:
  Create Order
  Insert OutboxEvent(OrderCreated, stable eventId)
  Commit

Background dispatcher:
  Read Outbox event
  Send to message broker
  Mark dispatched (idempotent/retriable)
~~~

Nếu dispatcher crash sau publish nhưng trước khi mark success, event có thể được gửi lại. Consumer cần dedupe/idempotency.

Không gửi event trực tiếp giữa transaction body mà không có recovery protocol: event có thể đi dù database transaction abort, hoặc commit thành công mà event không được gửi.

## 59. Saga cho side effect ngoài database

Ví dụ Order → Inventory → Payment:

~~~mermaid
flowchart TD
  A["Create Order PENDING"] --> B["Reserve inventory"]
  B --> C["Authorize payment"]
  C --> D{"Payment successful?"}
  D -->|"Yes"| E["Confirm Order"]
  D -->|"No"| F["Release reservation"]
  E --> G["Publish confirmed state"]
  F --> H["Mark failed / reconcile"]
~~~

Mỗi bước cần stable operation ID, durable state, retry policy và compensation khi applicable. Không giả định một `@Transactional` trên Java method bao trùm mọi remote API.

## 60. Conditional delete và soft delete

Một delete quan trọng cũng cần điều kiện:

~~~text
Delete Order only if status=DRAFT and version=7
```

Có thể dùng filter `status="DRAFT"` và `version=7` trong một delete/update. Soft delete với tombstone/version có thể cần thiết nếu event cũ có thể đến sau delete hoặc projections được duy trì bất đồng bộ.

Không thực hiện:

~~~text
Read Order as DRAFT
... time passes ...
deleteById(orderId)
```

vì Order có thể đã được APPROVED trước delete.

## 61. Conditional upsert và duplicate key

Một upsert vừa có filter vừa có unique key có thể bị race giữa hai writers. Nếu filter không match bản hiện tại do version khác, upsert có thể cố tạo document cùng `_id` và ném duplicate key.

Không biến mọi duplicate key thành “retry lại upsert” vô hạn. Với create-only, dùng insert-if-absent/unique constraints và xử lý duplicate như domain outcome; với update, dùng CAS và re-read.

## 62. Transaction context và tenant scope

Một Repository method cần gắn tenant identity từ authenticated context:

~~~java
Optional<Order> findByTenantAndId(
    String trustedTenantId,
    String orderId
);
~~~

Một conditional update phải giữ tenant predicate:

~~~text
WHERE tenantId = trustedTenant
AND orderId = requestedOrder
AND version = expectedVersion
```

Nếu không, một Order ID trùng giữa hai tenants có thể bị cập nhật nhầm. Cấu hình shard routing đúng không tự là authorization.

Idempotency key cũng nên được namespace theo tenant và operation type để hai khách khác không va chạm hoặc đọc outcome của nhau.

## 63. Read concern, read preference và write concern

Với MongoDB:

- **Read preference:** loại node có thể nhận read.
- **Read concern:** dữ liệu được đọc ở mức nào.
- **Write concern:** điều kiện acknowledgment của write/commit.
- **Session/transaction options:** liên hệ read/write trong một scope.
- **Retryable writes:** cơ chế retry driver được hỗ trợ, không thay business idempotency.

Với DynamoDB:

- Read consistency phụ thuộc API/table/index scope.
- Conditional writes thực thi theo semantics dịch vụ.
- Transaction APIs có hạn mức/phạm vi riêng.
- Global Tables có consistency/conflict semantics cần xét riêng.

Với Cassandra/Redis, các từ như consistency, transaction, atomicity lại có phạm vi khác.

**Không gọi một method `saveStronglyConsistent()` mà không định nghĩa nó tương đương setting nào của engine**.

## 64. Durability khác atomicity

Một operation có thể được thực thi atomic trên một node nhưng chưa được bảo đảm sống sót qua mọi failover theo acknowledgement/replication policy.

Ví dụ Redis atomic Lua script bảo vệ concurrent increments trên primary, nhưng phải xét persistence/replication; MongoDB local acknowledgment khác majority write concern; DynamoDB SDK success có semantics riêng.

Vì vậy mô tả một repository operation nên trả lời:

1. Có atomic đối với những field/items nào?
2. Có isolation nào?
3. Khi nào response success?
4. Có durability nào sau node crash?
5. Khi response timeout, biết outcome không?
6. Có idempotency và read-your-writes không?

## 65. Multi-region transactions có giới hạn

Nếu dữ liệu Order nằm region A và Payment/Inventory nằm region B, một transaction do Java mở vào một database cụ thể không tự commit xuyên các service/regions.

Cần xét:

- Source-of-truth region.
- Global Tables replication/conflict policy.
- Writes active-active hay single writer.
- Network partition behavior.
- Quorum/leader availability.
- Data residency.
- Saga/compensation.
- Idempotency xuyên region failover.

Không suy từ cùng tên table/collection ở hai regions thành một atomic transaction toàn cầu.

## 66. DAL dùng connection pool và client lifecycle đúng

Một nguyên tắc vận hành:

~~~text
Startup:
  create MongoClient / DynamoDbClient / CqlSession / Redis client
  initialize repositories

Per request:
  reuse client and pools
  create short-lived session/transaction as supported
  execute conditional operation
  classify outcome
  close session/resources

Shutdown:
  stop accepting requests
  drain work if possible
  close clients
~~~

Không tạo một client mới cho mỗi update; việc đó gây socket/TLS churn. Nhưng cũng không **chia sẻ một transaction session** giữa nhiều HTTP requests khi driver không hỗ trợ.

## 67. Async/reactive transaction context

Với asynchronous/reactive Java:

- Session/transaction context cần đi theo chain/future/reactive context, không mặc định theo thread-local như synchronous call.
- Không block event-loop threads bằng sleep/backoff.
- Cancellation có thể xảy ra giữa write và response; outcome có thể unknown.
- Publisher được subscribe hai lần có thể thực thi side effect hai lần nếu semantics không được thiết kế.
- Transaction operator/manager phải được cấu hình cho driver reactive thật.

Không chỉ đổi kiểu trả về `Mono<Void>` rồi giả định transaction context từ Spring imperative được truyền đúng.

## 68. Transaction timeout và pool saturation

Transaction dài gây:

- Giữ snapshot/locks/resources lâu.
- Tăng khả năng conflict.
- Tăng pool checkout wait.
- Kéo dài p95/p99 latency.
- Tăng retries khi failover.
- Gây áp lực lên database.

Giảm bằng cách:

- Đọc đúng fields/indexes.
- Không gọi external API trong transaction.
- Giảm số documents cần chạm.
- Sử dụng atomic single-document operations khi đủ.
- Dùng short, bounded transaction.
- Đưa heavy analytics ra read model.
- Giới hạn concurrency trên hot aggregate.

Không “giải quyết” bằng cách đặt transaction timeout vô hạn.

## 69. Một transaction không tự bảo vệ external lock

Nếu worker giữ Redis lease rồi ghi MongoDB, cần xem stale worker:

~~~text
Worker A nhận lease epoch 41
A pause quá TTL
Worker B nhận lease epoch 42
A tỉnh và gửi update
```

Nếu MongoDB update không có điều kiện owner/fencing generation hoặc version, A vẫn có thể ghi dù lease của nó hết. TTL chỉ làm lock hết hạn, **không dừng đoạn code đã chạy**.

Nếu dựa vào external lease, DAL cần kiểm tra token/epoch tại authoritative write theo cơ chế có thể chứng minh, hoặc chuyển sang một protocol khác bảo vệ invariant.

## 70. Data types và timezone trong conditional checks

Điều kiện `expiresAt > now` có thể sai nếu một bên lưu UTC và bên kia tạo local time không chuẩn, hoặc thời gian client không đáng tin.

Cần xác định:

- Nguồn thời gian được sử dụng.
- Precision của timestamp.
- `Date`/`Instant`/BSON Date/CQL timestamp mapping.
- `NumberLong` vs `Integer`/Decimal.
- Missing/null có nghĩa gì.
- Array/predicate được so như thế nào.
- Timezone và daylight-saving behavior.

Đừng dùng `LocalDateTime` không timezone cho thời điểm absolute mà không có quy tắc chuyển đổi.

## 71. Transaction tests phải kiểm concurrency

Một test chạy từng request tuần tự không thể chứng minh tránh overselling.

Ví dụ:

~~~text
Initial stock=1
Start request A and B concurrently
Both reserve quantity=1
Wait for outcomes

Assert:
  exactly one business reservation succeeds
  available never negative
  successful Order has one stock reservation
  loser receives SOLD_OUT/CONFLICT_BUSY
  no duplicate side effects
~~~

Cần test dưới concurrency nhiều lần, với scheduling random và fault injection phù hợp. Không chỉ kiểm một exception type.

## 72. Test rollback qua nhiều repositories

Một test quan trọng:

~~~text
Begin transaction
Reserve inventory
Insert Order
Intentionally fail before commit
Assert:
  Order not visible as committed
  Inventory reservation not committed
  Outbox event not committed
~~~

Nếu Inventory còn bị giảm sau rollback, một repository method có thể đã **thoát transaction scope**, hoặc engine không hỗ trợ transaction như abstraction tuyên bố.

## 73. Test write skew

Ban đầu hai bác sĩ đang trực. Hai transaction đồng thời tắt trạng thái của hai người khác nhau.

Assert invariant `onCallCount >= 1` luôn giữ. Nếu cả hai commit dù logic mỗi transaction có đọc đủ hai bác sĩ, đó là dấu hiệu cần **redesign invariant protection** hoặc isolation, không chỉ tăng retry attempts.

## 74. Test mất response sau commit

Kịch bản:

~~~text
Database commits CreateOrder(operationId=K)
Network drops commit response
Client retries same K
~~~

Assert:

- Không tạo hai Order.
- Không reserve stock hai lần.
- Idempotency lookup trả lại cùng Order ID.
- Outbox/consumer không tạo payment intent trùng.
- API xử lý `UNKNOWN_OUTCOME` hợp lệ.

Đây là test bổ sung cho optimistic conflict; transaction có thể đúng mà business vẫn trùng nếu idempotency thiếu.

## 75. Test conditional write dưới failover

Trong môi trường được phép:

1. Bắt đầu nhiều CAS attempts.
2. Thực hiện node failover/step-down hợp lệ.
3. Xác nhận các operation được phân loại success, retryable conflict, temporary unavailable hoặc unknown.
4. Kiểm tra invariant không bị phá.
5. Kiểm tra không có retry vô hạn.
6. Xác minh session/pool được giải phóng.
7. Kiểm tra audit/correlation IDs.

Không chạy chaos/kill primary trên production nếu không có kế hoạch và quyền cho phép.

## 76. Metrics cho DAL

| Metric | Ý nghĩa |
|---|---|
| `conditionalWriteSuccess` | Số cập nhật đủ điều kiện |
| `conditionalMismatch` | Số update không match |
| `businessRejectCount` | Từ chối vì invariant |
| `optimisticConflictCount` | Version mismatch |
| `transactionAbortCount` | Transaction abort |
| `retryableErrorRate` | Lỗi tạm có thể retry |
| `unknownCommitCount` | Outcome chưa xác định |
| `attemptsPerOperation` | Số lần thử một business intent |
| `idempotencyHitCount` | Request trùng được trả outcome |
| `outboxBacklog` | Event chưa được dispatch |
| `transactionDuration` | Thời gian transaction mở |
| `poolCheckoutWait` | Đợi connection |
| `operationP95/P99Latency` | Tail latency |
| `invariantViolationCount` | Sai sót correctness |
| `hotKeyConflictRate` | Độ tranh chấp theo aggregate |

Không chỉ đo throughput và số exception. Một hệ có conflict thấp vì **không kiểm concurrency** còn nguy hiểm hơn một hệ có conflict vừa phải và invariant luôn đúng.

## 77. Tracing và correlation

Một operation log có thể chứa:

~~~json
{
  "tenantClass": "small",
  "operationType": "ReserveInventory",
  "operationId": "checkout-K100",
  "attemptNo": 2,
  "expectedVersion": 11,
  "resultCategory": "RETRYABLE_CONFLICT",
  "durationMs": 35
}
~~~

Không log card data, credentials, raw PII hoặc bản ghi đầy đủ không cần thiết. Với tenantId cực nhiều, metrics label cần giới hạn cardinality; giữ ID chi tiết ở trace/log an toàn khi policy cho phép.

## 78. Những anti-pattern phổ biến

1. `findById` → tính lại → `save` không có CAS.
2. Bảo vệ concurrency bằng `synchronized` trong một JVM nhiều API pods.
3. Coi `matchedCount=0` luôn là transient database error.
4. Bắt `Exception` rồi retry vô hạn.
5. Retry full transaction khi commit outcome chưa rõ.
6. Gọi email/payment trong callback transaction có thể chạy lại.
7. Mọi Repository method tự commit một transaction riêng.
8. Gắn `@Transactional` nhưng không có transaction manager phù hợp.
9. Cho rằng snapshot isolation là serializable.
10. Dùng `@Version` nhưng vẫn update những paths bỏ qua version.
11. Kiểm tra quota bằng count query không có atomic constraint.
12. Dùng Redis MULTI làm transaction xuyên hai Redis Cluster slots.
13. Giả định Cassandra LWT bảo vệ arbitrary multi-partition workflow.
14. Dùng GSI eventual read làm authorization nguồn.
15. Dùng idempotency key mới mỗi lần retry cùng ý định.
16. Ghi version ở bước riêng so với data.
17. Dùng `double` cho số tiền chính xác.
18. Che mất error categories trong generic `boolean`.
19. Dựa vào lease TTL nhưng không fence stale owner.
20. Không test response mất sau commit.

## 79. Bài tập A — Tồn kho một đơn vị

Hai request Java cùng mua một item khi `available=1`.

**Hỏi:** điều kiện phải đặt ở đâu?

**Hướng giải:** tại write primitive của database, ví dụ filter `available >= 1` kết hợp atomic decrement. GET trước update không đủ.

## 80. Bài tập B — Version mismatch

Order v7 đang PENDING. Request A approve và tăng v8. Request B từ v7 muốn cancel.

**Hỏi:** B có nên tự đổi expectedVersion thành 8 để retry không?

**Hướng giải:** không. Phải reread trạng thái và kiểm lại transition rule; không giữ decision dựa trên v7.

## 81. Bài tập C — matchedCount=0

MongoDB conditional update trả matchedCount=0.

**Hỏi:** chắc chắn đây là lỗi mạng?

**Hướng giải:** không. Filter có thể không match do thiếu stock, missing entity, sai tenant hoặc state/version đổi. Network exception có đường xử lý khác.

## 82. Bài tập D — Multiple repository calls

OrderService gọi reserve(), insertOrder(), appendOutbox() và mỗi method tự commit.

**Hỏi:** có atomic toàn use case không?

**Hướng giải:** không. Cần một transaction context chung trong engine hỗ trợ hoặc workflow với compensation.

## 83. Bài tập E — Spring @Transactional

Một Spring service có annotation trên method nhưng không cấu hình MongoTransactionManager.

**Hỏi:** annotation tự tạo MongoDB transaction không?

**Hướng giải:** không. Cần transaction infrastructure thực và deployment hỗ trợ; self-invocation cũng là bẫy.

## 84. Bài tập F — DynamoDB condition failed

Inventory available=0, UpdateItem `available >= 1` trả ConditionalCheckFailed.

**Hỏi:** retry 100 lần ngay có hợp lý?

**Hướng giải:** không. Có thể là SOLD_OUT, cần business rejection; chỉ retry conflict/transient được phân loại.

## 85. Bài tập G — Cassandra LWT

Client đọc credits=10,v7 và muốn trừ 8. LWT v7 fail; state mới credits=5,v8.

**Hỏi:** có thể ghi credits=2 với expected v8 không?

**Hướng giải:** không. Phải tính lại; 5-8 âm nên từ chối.

## 86. Bài tập H — Redis WATCH

Java WATCH key, GET=2, MULTI DECRBY 1, EXEC bị abort do key thay đổi.

**Hỏi:** làm gì ở attempt tiếp?

**Hướng giải:** WATCH và GET lại, đánh giá lại điều kiện, tính mutation mới và retry trong budget.

## 87. Bài tập I — Redis MULTI và rollback

Một command trong MULTI bị lỗi runtime.

**Hỏi:** có thể mặc định mọi command trước đó được rollback như SQL transaction không?

**Hướng giải:** không. Cần hiểu Redis MULTI/EXEC semantics, chọn atomic script/command phù hợp.

## 88. Bài tập J — Transaction callback có payment

Callback bị retry vì write conflict nhưng đã gọi gateway charge.

**Hỏi:** nguy cơ và cách sửa?

**Hướng giải:** charge lặp; dùng outbox/saga và external idempotency, không đặt side effect ngoài DB trong callback có thể retry.

## 89. Bài tập K — Unknown commit

Java gửi COMMIT rồi timeout.

**Hỏi:** có chắc transaction abort không?

**Hướng giải:** không. Có thể đã commit; dùng driver commit retry/reconciliation và stable idempotency key.

## 90. Bài tập L — Write skew

Hai transactions đọc hai doctors đang trực nhưng ghi hai doctors khác nhau thành off.

**Hỏi:** vì sao cả hai có thể commit dưới một số snapshot isolation?

**Hướng giải:** không có write-write conflict chung; cần serializable protection hoặc owner/counter constraint.

## 91. Bài tập M — Tenant scope

Hai tenant cùng dùng `orderId=o100`. DAL update chỉ filter orderId.

**Hỏi:** lỗi gì?

**Hướng giải:** có nguy cơ sửa nhầm tenant. Cần tenant identity tin cậy trong key/filter và authorization độc lập shard routing.

## 92. Bài tập N — Idempotency TTL

Một DynamoDB clientRequestToken có idempotency window hữu hạn, nhưng khách có thể retry sau nhiều ngày.

**Hỏi:** dùng token SDK có đủ không?

**Hướng giải:** không. Cần idempotency business record với retention phù hợp.

## 93. Bài tập O — Quota predicate

Quy tắc tối đa 5 booking. Hai transactions đều đọc count=4 rồi insert hai documents mới.

**Hỏi:** @Version trên hai booking mới có ngăn vượt quota không?

**Hướng giải:** không. Cần authoritative shared constraint/counter hoặc serializable predicate protection.

## 94. Bài tập P — One document vs transaction

Chỉ cần giảm stock nếu available đủ.

**Hỏi:** multi-document transaction có luôn tốt hơn không?

**Hướng giải:** không. Atomic conditional single-document operation thường đơn giản và ít overhead hơn nếu toàn invariant nằm trong document.

## 95. Bài tập Q — Metadata write concern

Một write được acknowledge tại primary nhưng chưa đạt durability policy mong muốn.

**Hỏi:** atomicity của update có tự bảo đảm sống sót qua mọi failover?

**Hướng giải:** không. Atomicity, durability và acknowledgment là các guarantees khác nhau.

## 96. Checklist thiết kế DAL transaction/conditional write

1. Invariant nghiệp vụ nào phải giữ?
2. Invariant nằm trong một document/item hay nhiều?
3. Có thể dùng atomic condition thay read–modify–write không?
4. Đã validate quantity, currency, type và domain scope chưa?
5. Repository có interface phản ánh atomic operation không?
6. `matchedCount=0` được phân loại đúng chưa?
7. Version có tăng nguyên tử và không reset sai không?
8. ExpectedVersion được reread khi retry chưa?
9. Unique scope theo tenant/global được database enforce đúng chưa?
10. Có bảo vệ predicate/phantom/write skew không?
11. Transaction được mở ở use-case scope thay vì mỗi method không?
12. Mọi Repository calls có dùng cùng session/transaction context không?
13. `@Transactional` có transaction manager và proxy semantics đúng không?
14. Engine có hỗ trợ transaction trong deployment/topology hiện tại không?
15. Isolation level, read/write concerns có được xác định không?
16. Driver callback có thể chạy lại không?
17. Có external side effect trong transaction body không?
18. Có outbox và idempotent consumer không?
19. Unknown commit outcome có đường riêng không?
20. Idempotency key có ổn định cho một business intent không?
21. DynamoDB conditional/TransactWriteItems semantics có đúng scope không?
22. Cassandra LWT có bị áp quá phạm vi một partition không?
23. Redis WATCH/Lua/MULTI và Cluster slots có được hiểu đúng không?
24. Có retry budget/backoff/jitter và deadline không?
25. Có giới hạn contention trên hot aggregate không?
26. Có typed business outcomes thay catch-all exception không?
27. Có read consistency phù hợp khi reread after conflict không?
28. Tenant authorization và keys được áp ở mọi conditional write không?
29. Transaction/session/client lifecycle có tránh leak/pool exhaustion không?
30. Có test concurrency, rollback, phantom/write skew, failover và unknown commit không?
31. Có observability về conflicts, retries, idempotency và invariant violations không?

## 97. Mẫu tài liệu hợp đồng DAL

~~~yaml
useCase: Checkout
owner: OrderApplicationService
sourceOfTruth:
  inventory: InventoryCollection
  orders: OrdersCollection
  couponUsage: CouponUsageCollection
transaction:
  engine: MongoDB
  scope:
    - inventory
    - order
    - couponUsage
    - outbox
  requiresSupportedDeployment: true
  reads:
    - inventoryAvailable
    - currentPriceOrValidQuote
    - couponEligibility
    - customerState
    - idempotencyRecord
  writes:
    - conditionalInventoryReserve
    - uniqueCouponUsageInsert
    - idempotentOrderInsert
    - outboxAppend
  onRetryableAbort: newAttemptAndReread
  onUnknownCommit: retryCommitOrReconcile
conditionalWrites:
  inventory: "available >= requestedQuantity"
  orderCreate: "orderId does not exist"
  couponUsage: "unique tenant-campaign-customer"
  idempotency: "unique tenant-operation-requestId"
externalSideEffects:
  payment: idempotentSagaStep
  email: outboxConsumer
retry:
  attempts: bounded
  deadline: bounded
  backoff: exponentialWithJitter
observability:
  - conditionalMismatch
  - transactionAbort
  - unknownCommit
  - idempotencyHit
  - outboxBacklog
  - p99Latency
tests:
  - concurrentLastItemCheckout
  - abortRollsBackAllWrites
  - droppedCommitResponse
  - duplicateIdempotencyRequest
  - priceChangesDuringRetry
  - quotaWriteSkew
~~~

Đây là YAML **mô tả kiến trúc**, không phải file cấu hình có thể đưa trực tiếp cho Spring/MongoDB driver. Từng điều kiện phải được ánh xạ vào code DAL và API transaction của engine triển khai.

## 98. Kết luận

Trong kết nối Java với NoSQL, **DAL không chỉ chuyển object thành document**. Nó là nơi biến các yêu cầu concurrency và consistency của domain thành điều kiện được database thực thi.

- Một invariant trong một document nên ưu tiên **atomic conditional update**.
- Cập nhật dựa trên phiên bản cần **CAS/optimistic locking** và reread khi conflict.
- Những write phải cùng commit trong một database có thể dùng **multi-document transaction** nếu engine/topology hỗ trợ.
- **Snapshot isolation không tự ngăn mọi write skew/phantom**; cần mô hình constraint đúng.
- Transaction có thể retry callback, vì vậy không gọi payment/email trực tiếp trong callback.
- **Unknown commit outcome** khác confirmed abort: cần commit retry/reconciliation và idempotency.
- MongoDB, DynamoDB, Cassandra và Redis có những guarantees khác nhau; Repository phải thể hiện giới hạn thật.
- Đo conflict, unknown outcome, pool pressure và business invariant violations, không chỉ đo số request thành công.

> **Một thao tác cập nhật đúng là thao tác kiểm tra điều kiện tại chính điểm ghi có thẩm quyền. Một giao dịch đúng là giao dịch có phạm vi, isolation, commit và retry semantics được hiểu và kiểm chứng, không chỉ là method Java mang tên `transaction`.**

Khi thiết kế DAL quanh bất biến, version và outcome rõ ràng, ứng dụng Java có thể tận dụng các mô hình NoSQL linh hoạt mà vẫn chịu được nhiều writer đồng thời, failover và retry mà không âm thầm làm sai dữ liệu nghiệp vụ.
