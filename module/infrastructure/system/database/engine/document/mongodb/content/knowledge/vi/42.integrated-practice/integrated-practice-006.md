# Thử nghiệm cạnh tranh khi cập nhật tồn kho và tạo đơn hàng trong MongoDB

Giả sử một cửa hàng trực tuyến còn **5 sản phẩm** cuối cùng. Đúng lúc chương trình khuyến mãi bắt đầu, 20 khách hàng cùng nhấn nút Đặt hàng. Nếu mỗi request đọc tồn kho rồi tự trừ trong Java và ghi lại, hệ thống có thể tạo 20 đơn hàng thành công nhưng số tồn kho chỉ giảm từ 5 xuống 4, hoặc thậm chí trở thành số âm. Khi thêm việc ghi document đơn hàng vào collection khác, còn xuất hiện tình huống **tồn kho đã bị trừ nhưng đơn hàng không được tạo**, hoặc **đơn hàng đã tạo nhưng stock chưa được trừ**.

Bài **“Thử nghiệm cạnh tranh khi cập nhật tồn kho và tạo đơn hàng”** nằm trong chương **Thực hành tổng hợp** của module **Database Engine Document MongoDB**. Bài này tổ chức một lab có thể kiểm chứng bằng code, nhiều clients/threads và các bất biến nghiệp vụ. Chúng ta sẽ lần lượt dựng một cách làm sai có chủ đích, sửa bằng **single-document atomic conditional update**, bổ sung **multi-document transaction**, thiết kế **idempotency key**, rồi kiểm thử khi có xung đột, retry, lỗi giữa chừng và kết quả commit không rõ.

Sau khi hoàn thành, bạn có thể:

1. Mô tả và tái hiện **lost update**/overselling khi nhiều khách cùng đặt hàng.
2. Viết bộ lọc **`available >= quantity`** kết hợp `$inc` trong **một lệnh MongoDB** để không cho tồn kho âm.
3. Phân biệt **tính nguyên tử trên một document** với **atomicity giữa document tồn kho và document đơn hàng**.
4. Dùng **MongoDB multi-document transaction** và MongoDB Java Sync Driver để tạo đơn + trừ tồn kho nhất quán.
5. Áp dụng unique business key `(tenantId, requestId)` để chống tạo đơn trùng khi client retry.
6. Phân biệt **hết hàng, yêu cầu trùng, yêu cầu trùng khác nội dung, write conflict, timeout và lỗi không rõ kết quả**.
7. Viết JUnit integration tests cho 20–100 requests đồng thời bằng `ExecutorService` và `CountDownLatch`.
8. Kiểm tra đúng invariant: tồn kho không âm, không có đơn duplicate, số lượng đã giữ khớp lượng tồn bị trừ.
9. Biết khi nào nên dùng transaction, atomic update, single-document embedding hoặc reservation/saga workflow.

> **Phạm vi an toàn:** toàn bộ dữ liệu, SKU, request ID và lệnh setup chỉ dùng trên **MongoDB lab disposable**. Không đưa test cạnh tranh lên cluster production đang phục vụ khách hàng. Những ví dụ transaction cần **replica set hoặc sharded cluster có hỗ trợ transactions**; một standalone `mongod` đơn lẻ thường không đáp ứng yêu cầu này. Các snippets được trình bày để học cơ chế; hãy cấu hình dependency, authentication, network, URI và cleanup đúng môi trường thực.

## 1. Thiết lập bất biến trước khi viết code

Trong một bài thực hành cạnh tranh, điều quan trọng nhất không phải “cả 20 threads đều không báo lỗi”. Đúng hơn, chúng ta định nghĩa **invariant** — quy tắc luôn phải giữ sau mọi kết quả được chấp nhận.

Với một SKU chỉ có một loại hàng và không nhập kho trong khi kiểm thử:

```text
initialAvailable = 5
quantity mỗi đơn = 1

0 <= inventory.available <= 5

Số lượng đã đặt thành công <= 5

inventory.available
  + SUM(quantity của các order trạng thái RESERVED)
  = initialAvailable

Không có hai orders cùng (tenantId, requestId)
```

Trong bài lab, mọi đơn thành công được tạo với trạng thái **RESERVED** và chưa có bước huỷ/trả hàng; nhờ vậy phương trình trên đúng theo mô hình cố định.

Nếu có nhập kho, huỷ đơn, trả hàng, fulfillment, expiration hoặc hàng giữ chỗ, mô hình cần mở rộng thành sổ giao dịch/định nghĩa `onHand`, `reserved`, `available` nhất quán. **Không lấy công thức đơn giản của lab áp thẳng vào một hệ thống kho phức tạp.**

### Những kết quả được phép

Cho 20 requests khác nhau, mỗi request đặt một sản phẩm khi tồn kho ban đầu là 5:

| Kết quả | Số lượng kỳ vọng |
| --- | ---: |
| Request được chấp nhận và có order RESERVED | 5 |
| Request bị từ chối vì hết hàng | 15 |
| Tồn kho cuối | 0 |
| Tồn kho âm | Không được phép |
| Hai đơn cùng idempotency key | Không được phép |
| Tồn kho bị trừ nhưng không có đơn | Không được phép trong cách dùng transaction |

Ai trong 20 khách thắng không quan trọng. Invariant nghiệp vụ mới là thứ test cần assert.

## 2. Mô hình dữ liệu tối thiểu

Chúng ta dùng hai collections:

```text
inventory
  _id           -> SKU, unique theo _id
  available     -> số lượng còn có thể đặt
  initialStock  -> số lượng ban đầu của fixture

orders
  _id           -> ID đơn hàng
  tenantId      -> scope ứng dụng
  requestId     -> idempotency key
  sku           -> SKU được đặt
  quantity      -> số lượng nguyên dương
  status        -> RESERVED trong bài lab
  createdAt     -> thời điểm tạo
```

Một document tồn kho:

```javascript
{
  _id: "SKU-BOOK-001",
  available: 5,
  initialStock: 5
}
```

Một document đơn hàng:

```javascript
{
  _id: "order-001",
  tenantId: "tenant-demo",
  requestId: "request-001",
  sku: "SKU-BOOK-001",
  quantity: 1,
  status: "RESERVED",
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
```

### Tại sao cần `requestId`?

Một người dùng có thể nhấn Đặt hàng hai lần hoặc client không nhận được phản hồi do timeout rồi retry. Hai lần gọi API có thể đại diện cho **cùng một ý định đặt hàng**. Nếu tạo ID mới mỗi lần mà không có unique business key, bạn có thể trừ tồn kho hai lần.

Trong lab, `requestId` là **idempotency key**: cùng tenant + cùng requestId + cùng payload nghiệp vụ chỉ nên đại diện cho **một đơn**.

## 3. Chuẩn bị database lab trong `mongosh`

Chạy trong môi trường có quyền với database thử nghiệm:

```javascript
use mongo_order_concurrency_lab

// Chỉ xóa collections trong database lab disposable.
db.inventory.drop();
db.orders.drop();

db.inventory.insertOne({
  _id: "SKU-BOOK-001",
  available: 5,
  initialStock: 5
});

db.orders.createIndex(
  { tenantId: 1, requestId: 1 },
  {
    unique: true,
    name: "uk_tenant_request"
  }
);

db.inventory.findOne({ _id: "SKU-BOOK-001" });
db.orders.getIndexes();
```

Các lệnh `drop()` ở đây **chỉ được dùng trong lab riêng**; chúng xóa toàn bộ documents và indexes. Với integration tests chạy song song, nên dùng **SKU/tenant/testRunId duy nhất cho mỗi test** thay vì drop collections dùng chung.

Unique index `{tenantId:1, requestId:1}` phải được tạo thành công **trước khi chạy concurrency test**. Việc có một field tên requestId không tự tạo uniqueness.

## 4. Xác nhận topology hỗ trợ transaction

Từ `mongosh`:

```javascript
db.adminCommand({ hello: 1 });
```

Kiểm tra deployment:

- Nếu là replica set, response có thông tin replica set như `setName` và member state phù hợp.
- Nếu qua `mongos`, response phản ánh sharded router.
- Với standalone `mongod`, multi-document transactions không có support như trong replica set/sharded cluster.

Trong replica set:

```javascript
rs.status();
```

Không phải mọi client được cấp quyền xem đầy đủ trạng thái replica; tài khoản vận hành cần role phù hợp.

### Chọn topology cho lab

Để test atomicity giữa hai collections, sử dụng replica set MongoDB thử nghiệm hoặc một môi trường Testcontainers được khởi tạo replica set đúng cách. **Không “sửa” lỗi transaction không hỗ trợ bằng cách bỏ transaction** rồi vẫn gắn nhãn test atomicity là PASS.

Lỗi thường gặp:

```text
Transaction numbers are only allowed on a replica set member
or mongos
```

Nếu gặp, trước hết kiểm tra topology/URI. Chạy MongoDB trong Docker **không mặc nhiên nghĩa là đã có replica set**.

## 5. Cách làm sai số 1: đọc rồi ghi giá trị mới

Một service ngây thơ:

```javascript
const stock = db.inventory.findOne({
  _id: "SKU-BOOK-001"
});

if (stock.available >= 1) {
  db.inventory.updateOne(
    { _id: "SKU-BOOK-001" },
    { $set: { available: stock.available - 1 } }
  );
}
```

Nhìn trên một client đơn lẻ, code có vẻ đúng. Nhưng hai clients có thể cùng đọc `available = 5` trước khi ai ghi.

```text
Client A                               Client B
   |                                      |
   | findOne -> available=5               | findOne -> available=5
   |                                      |
   | tính 5 - 1 = 4                      | tính 5 - 1 = 4
   |                                      |
   | update $set available=4              |
   |                                      | update $set available=4
   v                                      v

Tồn kho cuối = 4
Nhưng đã có HAI request được chấp nhận.
Theo nghiệp vụ đáng ra còn 3.
```

**Lost update** xuất hiện vì lệnh `updateOne()` chỉ lọc theo `_id` và ghi đè một giá trị đã tính từ dữ liệu cũ. Từng update vẫn nguyên tử ở cấp document; thứ bị thiếu là **điều kiện cạnh tranh trong cùng operation**.

## 6. Cách làm sai số 2: check tồn kho ở Java rồi insert order

Ví dụ mã giả:

```java
Inventory inventory = inventoryRepo.findById(sku)
    .orElseThrow();

if (inventory.getAvailable() >= quantity) {
    inventory.setAvailable(
        inventory.getAvailable() - quantity);
    inventoryRepo.save(inventory);
    ordersRepo.insert(newOrder);
}
```

Có ít nhất hai vấn đề:

1. **Cạnh tranh:** nhiều threads cùng đọc một số tồn kho cũ rồi cùng `save()`.
2. **Hai writes độc lập:** giảm kho thành công nhưng insert order có thể thất bại vì duplicate key, network, process crash hoặc validation.

Thêm `@Version`/optimistic locking vào inventory có thể giảm lỗi lost update cho đường `save()` được framework quản lý, nhưng **không tự tạo atomicity** giữa hai collections. Trừ kho và tạo order vẫn có thể thành công riêng lẻ nếu không có transaction/workflow bù trừ.

## 7. Sửa lỗi overselling bằng atomic conditional `$inc`

Một lệnh:

```javascript
db.inventory.updateOne(
  {
    _id: "SKU-BOOK-001",
    available: { $gte: 1 }
  },
  {
    $inc: { available: -1 }
  }
);
```

MongoDB kiểm tra điều kiện `available >= 1` và thực hiện decrement **trong cùng một write atomic trên một document**.

Nếu tồn kho còn 0, điều kiện không match; operation không trừ thành -1.

### Tại sao `$inc` an toàn hơn `$set` theo giá trị đã đọc?

```text
Sai:
  read available = N
  set available = N - 1

Đúng cho một inventory record:
  update where available >= 1
  inc available by -1
```

Hai requests không phải tự tính số mới dựa trên snapshot cũ; server thực hiện phép tăng/giảm atomically.

**Lưu ý:** update trên một document vẫn phải chạy với write concern có acknowledgment để ứng dụng biết matched count. Nó không thay thế transaction khi còn phải tạo order document.

## 8. Phân biệt `matchedCount` và `modifiedCount`

Lệnh `updateOne()` trả:

```javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 1
}
```

hoặc khi không đủ hàng:

```javascript
{
  acknowledged: true,
  matchedCount: 0,
  modifiedCount: 0
}
```

Đối với conditional decrement, `matchedCount == 1` có nghĩa điều kiện của operation match document. `matchedCount == 0` có thể là **SKU không tồn tại** hoặc **tồn kho không đủ**.

Không diễn giải mọi `matchedCount=0` thành lỗi mạng, và không tự tạo order khi decrement không match. Trong một phép cập nhật $set có giá trị không đổi, `modifiedCount=0` có thể xảy ra dù matchedCount=1; vì thế việc kiểm tra **matchedCount** quan trọng với CAS/conditional update.

## 9. Thử thủ công hai phiên `mongosh`

Mở hai kết nối tới **cùng database lab**, cùng collection inventory:

**Phiên A:**

```javascript
db.inventory.updateOne(
  { _id: "SKU-BOOK-001", available: { $gte: 1 } },
  { $inc: { available: -1 } }
);
```

**Phiên B:** chạy cùng lệnh.

Lặp lại với nhiều request nếu cần. Khi available đạt 0, các lệnh sau trả `matchedCount=0`.

Kiểm tra:

```javascript
db.inventory.findOne({ _id: "SKU-BOOK-001" });
```

Kết quả không được âm nếu **mọi writer dùng đúng điều kiện** và không có script khác `$set` tồn kho tùy tiện.

### Giới hạn của thử bằng tay

Hai câu lệnh gõ riêng thường không chạy thật sự đồng thời. Phần JUnit phía sau dùng barrier để tạo race có chủ đích. Kiểm thử manual hữu ích để hiểu filter và matched count, không đủ để chứng minh cơ chế chịu được nhiều requests.

## 10. Atomic decrement vẫn có lỗ hổng khi tạo order

Sau khi sửa overselling:

```text
1. update inventory WHERE available >= 1, $inc -1
2. insert order
```

Kịch bản lỗi:

```text
available: 5
   |
   v
UPDATE inventory -> available: 4, ACK
   |
   v
Process crash / duplicate key / network error
   |
   X
Không INSERT được order

Kết quả:
  Tồn kho đã trừ 1
  Không có order tương ứng
```

Nếu đổi thứ tự:

```text
1. insert order
2. decrement inventory
```

thì khi decrement thất bại, bạn lại có **order không có hàng để giữ**.

**Đúng ở từng bước không đồng nghĩa đúng cho cả hai bước.** Đây chính là lý do cần transaction hoặc workflow có trạng thái và bù trừ được thiết kế rõ ràng.

## 11. Ba phương án kiến trúc

| Phương án | Tránh overselling | Tránh lệch tồn kho/đơn hàng | Khi nên cân nhắc |
| --- | --- | --- | --- |
| Atomic `$inc` có điều kiện, rồi insert order | Có, cho một SKU document | **Không tự động** | Bài toán chấp nhận xử lý bù hoặc chưa cần order atomic |
| Multi-document transaction | Có khi filter đúng | Có, cho các writes trong transaction | Đơn giản nhất khi cần hai collections commit cùng nhau |
| Reservation ledger / saga / outbox | Phải thiết kế invariant và claims | Eventual consistency với reconciliation | Workflow phân tán, rất nhiều writes, external services |

Một phương án nữa là **embed order/reservation summary vào cùng inventory document**, nhưng có thể khiến document lớn, contention cao hoặc vượt giới hạn BSON; cũng không thích hợp nếu một order gồm nhiều SKUs. Chọn aggregate boundary theo nghiệp vụ và workload, không chỉ vì muốn tránh transaction.

## 12. MongoDB transaction làm gì trong bài lab?

Transaction bảo vệ nhóm writes:

```text
BEGIN TRANSACTION
    |
    +-- INSERT orders(orderId, requestId, sku, quantity)
    |
    +-- UPDATE inventory
          WHERE sku = X AND available >= quantity
          $inc available = -quantity
    |
    +-- Nếu đủ hàng và không lỗi -> COMMIT
    |
    +-- Nếu thiếu hàng, duplicate key, lỗi -> ABORT
```

Khi commit thành công theo durability/transaction semantics phù hợp, **không có kết quả bình thường kiểu chỉ một nửa hai writes được commit**.

Nếu không đủ hàng, phải **ném exception** hoặc abort transaction theo API để rollback insert order đã thực hiện trong transaction. Không return success sau khi update stock có matchedCount=0.

### Transaction không bảo đảm mọi business rule

Nếu filter tồn kho bỏ điều kiện `available >= quantity`, transaction vẫn có thể commit một phép decrement làm số âm. Nếu hai requests cùng idempotency key nhưng không có unique index, transaction **không tự bảo đảm** chỉ tạo một đơn theo khóa nghiệp vụ. Cần kết hợp transaction với **filter đúng, unique constraints và business validation**.

## 13. Multi-document transactions: điều kiện và giới hạn

Cần chú ý:

- MongoDB replica set hoặc sharded cluster hỗ trợ transactions theo version.
- Driver hỗ trợ sessions và transactions.
- Read/write concern, read preference và topology được cấu hình phù hợp.
- Bất kỳ MongoDB operations muốn tham gia transaction phải dùng **cùng session**.
- Transaction nên **ngắn**, không chứa thời gian người dùng đang mở form.
- Có khả năng `WriteConflict`/transient errors, cần retry theo semantics được hỗ trợ.
- Không gọi payment gateway/email bên trong transaction callback có thể được retry.

MongoDB transactions có overhead trên server và các giới hạn về thời gian/tài nguyên, đặc biệt khi chạm nhiều documents/shards. Không thay mọi thao tác `$inc` đơn giản thành multi-document transaction nếu invariant có thể bảo vệ ngay trong một document.

## 14. Định nghĩa idempotency cho đặt hàng

Đề bài có hai kiểu cạnh tranh:

**A. Hai người khác nhau đặt cùng SKU.**

```text
tenant-demo / request-A / SKU-BOOK-001 / qty=1
tenant-demo / request-B / SKU-BOOK-001 / qty=1
```

Đây là **hai intent độc lập**, đều được phép cạnh tranh số hàng còn lại.

**B. Một người retry đúng request.**

```text
tenant-demo / request-A / SKU-BOOK-001 / qty=1
tenant-demo / request-A / SKU-BOOK-001 / qty=1
```

Đây là **cùng intent** và không được trừ tồn kho hai lần.

**C. Client dùng lại key nhưng đổi payload.**

```text
tenant-demo / request-A / SKU-BOOK-001 / qty=1
tenant-demo / request-A / SKU-BOOK-001 / qty=5
```

Đây là **lỗi hợp đồng idempotency**. Không nên âm thầm coi request qty=5 là cùng một yêu cầu qty=1.

Trong lab, business identity là `(tenantId, requestId)` và payload được kiểm tra bằng `sku` cùng `quantity`. Production có thể cần thêm currency, price, address, user identity, discounts hoặc canonical fingerprint.

## 15. Unique index cho idempotency key

```javascript
db.orders.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uk_tenant_request" }
);
```

Ràng buộc này bảo đảm **không tồn tại hai documents khác nhau cùng cặp tenantId/requestId** theo unique key semantics.

Không dựa vào:

```java
if (!orders.existsByTenantAndRequest(...)) {
    orders.insert(...);
}
```

vì hai threads có thể cùng đọc “chưa tồn tại”. Unique index vẫn là chốt chặn cuối cùng.

### Vì sao không dùng unique SKU?

Một SKU cần có thể xuất hiện trong **nhiều đơn hàng khác nhau**. Unique `orders.sku` sẽ cấm mọi khách đặt một sản phẩm đã có trong đơn của người khác. Chỉ `inventory._id` unique theo SKU, còn `orders` unique theo idempotency key.

## 16. Quy ước status trong lab

Để đối soát đơn giản:

```text
RESERVED -> giữ hàng thành công, tồn kho đã giảm
REJECTED_OUT_OF_STOCK -> không tạo order trong collection orders
```

Bài lab chưa triển khai hủy, giao hàng, hoàn trả hoặc thanh toán. Khi ứng dụng thật có lifecycle:

```text
NEW -> RESERVED -> PAID -> SHIPPED
             \
              -> CANCELLED -> RELEASED
```

thì mỗi state transition cần quy tắc atomic/idempotent riêng. Không dùng cùng một transaction đặt hàng để giữ lock database qua quá trình chờ gateway thanh toán trong nhiều giây hoặc phút.

## 17. Java Sync Driver: dependencies và kết nối

Trong project Java 17+, thêm dependency `org.mongodb:mongodb-driver-sync` theo version tương thích. Ví dụ Gradle:

```groovy
dependencies {
    implementation("org.mongodb:mongodb-driver-sync:5.x.y")
    testImplementation("org.junit.jupiter:junit-jupiter:5.x.y")
}
```

**`5.x.y` là placeholder**, không phải version có thể resolve từ repository. Dùng version cụ thể đã được dependency management của dự án chốt. Ứng dụng cần URI tới replica set/sharded cluster lab và credential phù hợp.

Một kết nối tối thiểu:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;

String uri = System.getenv("MONGO_LAB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("Thiếu MONGO_LAB_URI");
}

try (MongoClient client = MongoClients.create(uri)) {
    MongoDatabase db =
        client.getDatabase("mongo_order_concurrency_lab");
    System.out.println(db.getName());
}
```

Đừng lưu MongoDB URI có password trong source hoặc output test. `MongoClient` là đối tượng thích hợp để dùng chung theo lifecycle ứng dụng; không tạo một client mới cho từng order nếu không có lý do.

## 18. DTO đầu vào và đầu ra

Ví dụ:

```java
public record CreateOrder(
    String tenantId,
    String requestId,
    String sku,
    int quantity
) {}

public record OrderReceipt(
    String orderId,
    String status,
    boolean newlyCreated
) {}
```

Trước khi bắt đầu transaction phải kiểm tra:

- `tenantId` lấy từ authenticated principal hoặc đã được authorization theo contract.
- `requestId` không rỗng và có giới hạn độ dài.
- `sku` hợp lệ, đã canonicalize theo schema.
- `quantity > 0` và không vượt giới hạn cho một request.
- User có quyền đặt hàng cho tenant/SKU này.

Ở đây `tenantId` được đưa vào record để ngắn gọn trong lab; **production không được tin tenantId tùy ý lấy từ request body**.

## 19. Exception riêng cho thiếu hàng

```java
public final class InsufficientStockException
        extends RuntimeException {

    public InsufficientStockException(String sku) {
        super("Không đủ tồn kho cho SKU: " + sku);
    }
}
```

Ta dùng exception để **abort transaction** nếu decrement không match. Trong sản phẩm thật, có thể trả HTTP 409 Conflict hoặc status khác theo API contract; không trả raw stack trace về client.

Tách lỗi business thiếu hàng khỏi:

- `MongoWriteException` duplicate key.
- `MongoException` do transient transaction errors.
- Timeout/network không rõ kết quả.
- Validation/authorization errors.

Không bắt mọi `MongoException` rồi trả “hết hàng”.

## 20. Java service: transaction tạo order và giảm tồn kho

Đây là ví dụ trung tâm của bài. Giả định `orders` đã có unique index `{tenantId:1, requestId:1}` và `inventory` có document SKU với `available` numeric.

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.MongoWriteException;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import java.util.Date;
import java.util.Objects;
import java.util.UUID;

public final class OrderService {

    private final MongoClient client;
    private final MongoCollection<Document> inventory;
    private final MongoCollection<Document> orders;

    public OrderService(MongoClient client, MongoDatabase db) {
        this.client = client;
        this.inventory = db.getCollection("inventory");
        this.orders = db.getCollection("orders");
    }

    public OrderReceipt place(CreateOrder request) {
        validate(request);

        // Sinh một lần cho invocation, không sinh lại trong
        // callback vì driver có thể retry transaction.
        String orderId = UUID.randomUUID().toString();

        TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(WriteConcern.MAJORITY)
            .readPreference(ReadPreference.primary())
            .build();

        try (ClientSession session = client.startSession()) {
            try {
                return session.withTransaction(() -> {
                    // Bước 1: tạo order trong transaction.
                    Document order = new Document("_id", orderId)
                        .append("tenantId", request.tenantId())
                        .append("requestId", request.requestId())
                        .append("sku", request.sku())
                        .append("quantity", request.quantity())
                        .append("status", "RESERVED")
                        .append("createdAt", new Date());

                    orders.insertOne(session, order);

                    // Bước 2: chỉ giảm kho nếu còn đủ.
                    UpdateResult stockResult = inventory.updateOne(
                        session,
                        Filters.and(
                            Filters.eq("_id", request.sku()),
                            Filters.gte("available",
                                request.quantity())
                        ),
                        Updates.inc("available",
                            -request.quantity())
                    );

                    if (stockResult.getMatchedCount() != 1) {
                        throw new InsufficientStockException(
                            request.sku());
                    }

                    // Hai writes chỉ có hiệu lực cùng nhau
                    // sau khi transaction commit thành công.
                    return new OrderReceipt(
                        orderId, "RESERVED", true);
                }, options);
            } catch (MongoWriteException ex) {
                if (ex.getError().getCode() != 11000) {
                    throw ex;
                }

                // Duplicate request key là một khả năng.
                // Không coi mọi E11000 là idempotent success.
                Document existing = orders.find(
                    Filters.and(
                        Filters.eq("tenantId",
                            request.tenantId()),
                        Filters.eq("requestId",
                            request.requestId())
                    )
                ).first();

                if (existing == null) {
                    throw ex;
                }

                if (!Objects.equals(
                        existing.getString("sku"),
                        request.sku())
                    || existing.getInteger("quantity")
                        != request.quantity()) {
                    throw new IllegalArgumentException(
                        "Idempotency key đã được dùng "
                        + "cho nội dung đơn hàng khác");
                }

                return new OrderReceipt(
                    existing.getString("_id"),
                    existing.getString("status"),
                    false
                );
            }
        }
    }

    private static void validate(CreateOrder r) {
        if (r.tenantId() == null
                || r.tenantId().isBlank()
                || r.requestId() == null
                || r.requestId().isBlank()
                || r.sku() == null
                || r.sku().isBlank()
                || r.quantity() <= 0) {
            throw new IllegalArgumentException(
                "Request không hợp lệ");
        }
    }
}
```

**Điểm cần hiểu:**

- `orders.insertOne(session, ...)` và `inventory.updateOne(session, ...)` sử dụng **cùng session**.
- `withTransaction` quản lý bắt đầu/commit/abort và xử lý retry các loại transaction errors nhất định theo driver semantics.
- `ReadConcern.SNAPSHOT` và `WriteConcern.MAJORITY` biểu thị lựa chọn consistency/durability của transaction; phải xem topology và contract thực tế.
- Unique index chống tạo hai orders cùng `(tenantId,requestId)`.
- Điều kiện `available >= quantity` chống bán vượt stock.
- Nếu hết hàng, `InsufficientStockException` khiến transaction không commit; order insert bên trong transaction phải được rollback.
- Nếu insert báo E11000, service không trừ kho trong transaction đó; ta chỉ coi request trùng hợp lệ sau khi đọc được order và so payload.
- Nếu gặp timeout/unknown commit result mà không xác định được thành công hay thất bại, **không mặc định đổi thành lỗi hết hàng hoặc retry với requestId mới**.

### Giới hạn của ví dụ

Đây là **sample cho bài lab**, không phải service production hoàn chỉnh. Production cần xử lý duplicate errors có thể bị wrap khác nhau, read concern/read preference khi đối soát, các trạng thái order khác, policy idempotency retention, giới hạn thời gian retry và trường hợp hệ thống tạm mất kết nối. Với các trường dữ liệu phức tạp, dùng canonical payload hash thay so `sku` và `quantity` đơn lẻ.

## 21. Vì sao tạo order trước rồi mới trừ kho?

Trong transaction, cả hai cách **đều có thể an toàn** nếu có điều kiện/abort đúng:

```text
Option A:
  INSERT order
  UPDATE stock
  COMMIT

Option B:
  UPDATE stock
  INSERT order
  COMMIT
```

Ta chọn A vì unique request key có thể từ chối sớm một yêu cầu trùng trước khi chạm vào hot inventory document. Nhưng:

- Khi stock thiếu, order insert vẫn xảy ra **bên trong transaction** rồi được abort.
- Không gửi email/ship order ngay sau `insertOne()` bên trong callback; transaction chưa commit.
- Không cho client thấy “order đã được tạo” trước khi xác nhận commit.

Không có thứ tự nào thay thế được transaction khi invariant cần commit cả hai writes.

## 22. Khi hai transactions cùng giảm một SKU

Ví dụ tồn kho 1 và hai requests khác nhau:

```text
Initial:
  inventory.available = 1

Transaction A            Transaction B
   |                        |
   | begin                  | begin
   | insert order-A         | insert order-B
   | update SKU -1          | update SKU -1
   |                        |
   | commit?                | conflict / retry?
   v                        v
  Một transaction được commit giữ hàng.
  Transaction còn lại phải kiểm tra lại
  state và cuối cùng bị từ chối nếu stock=0.
```

Đặc biệt với transaction snapshot isolation, hai transactions cạnh tranh cùng document có thể gặp **write conflict/transient error**, không đơn thuần là một lệnh update trả matchedCount=0. Driver hoặc application cần retry transaction theo đúng semantics để đánh giá lại stock trên snapshot mới.

Kết quả nghiệp vụ mong muốn:

```text
inventory.available = 0
count(orders RESERVED for SKU) = 1
Không có order-B được commit nếu nó không có hàng.
```

**Không bảo đảm transaction B luôn là người thua.** Test chỉ kiểm tra invariant, không phụ thuộc scheduling.

## 23. `withTransaction` và retry

MongoDB transactions có thể trả errors với labels liên quan retry:

- `TransientTransactionError`: có thể cần retry **toàn transaction**.
- `UnknownTransactionCommitResult`: client không chắc kết quả commit và có thể cần retry **commit** theo guidance của driver.

Convenient transaction API `withTransaction` trong Java Sync Driver hỗ trợ xử lý retry theo những semantics phù hợp. Nhưng có những giới hạn:

- Không mọi lỗi đều transient.
- Không retry vô hạn bằng outer loop không có deadline.
- Không bắt `InsufficientStockException` rồi retry như lỗi network.
- Không coi `E11000` đồng nghĩa với transient write conflict.
- Nếu callback được gọi lại, mọi code trong callback phải có thể **thực thi lại an toàn**.

### Khi callback được gọi lại

```text
withTransaction(callback)
       |
       +--> callback lần 1
       |      write conflict -> abort
       |
       +--> callback lần 2 (nếu driver retry)
              read/update ở transaction mới
              commit
```

Vì vậy code ví dụ sinh `orderId` **trước callback**, và không gọi cổng thanh toán/đẩy notification trong callback. Object order có thể được tạo lại khi retry nhưng chưa có write từ transaction thất bại được commit.

## 24. Không gọi side effect bên ngoài trong transaction callback

Anti-pattern:

```java
session.withTransaction(() -> {
    orders.insertOne(session, order);
    paymentGateway.charge(card, amount); // Nguy hiểm
    inventory.updateOne(session, filter, update);
    return orderId;
});
```

Vấn đề:

1. Payment gateway **không nằm trong MongoDB transaction**.
2. Nếu transaction abort, payment bên ngoài có thể đã thực hiện.
3. Driver có thể retry callback, khiến payment được gọi thêm lần nữa.
4. Nếu commit không rõ kết quả, có nguy cơ retry sai.

Một luồng tốt hơn:

```text
Transaction:
  reserve inventory
  create order RESERVED
  create outbox event (nếu cùng database/transaction)
Commit
  |
  v
Worker đọc outbox
  |
  v
Payment/fulfillment với idempotency key
  |
  v
Conditional status transition + audit
```

Even với outbox, event delivery thường có thể **at-least-once**, vì thế downstream phải idempotent. MongoDB transaction không tự tạo exactly-once side effects trên mọi hệ thống ngoài database.

## 25. E11000 khi nhiều requests cùng idempotency key

Kịch bản:

```text
T1: tenant-a / request-X / SKU-BOOK-001 / qty 1
T2: tenant-a / request-X / SKU-BOOK-001 / qty 1
```

Unique index đảm bảo không thể commit hai orders với cùng cặp `(tenantId, requestId)`.

Một request có thể:

- Insert và commit order trước.
- Gặp duplicate key sau khi request khác đã tạo.
- Gặp write conflict rồi driver retry, sau đó nhìn thấy duplicate.
- Gặp kết quả không rõ nếu network timeout ở commit.

Khi duplicate:

1. Xác định **index/key gây lỗi**, không assume mọi E11000 đều là idempotency index.
2. Đọc order theo unique business key.
3. So immutable payload/fingerprint.
4. Với payload giống: trả existing order/result theo contract.
5. Với payload khác: trả conflict.
6. Nếu chưa đọc được existing hoặc state không rõ: retry/reconcile có giới hạn, **không trả success giả**.

### Vì sao duplicate không tương đương lỗi mất dữ liệu?

Unique constraint đang **bảo vệ** hệ thống. Nhưng bắt E11000 rồi trả HTTP 200 không kiểm tra payload sẽ che lỗi tái sử dụng idempotency key sai mục đích.

## 26. Duplicate key không nên trừ tồn kho lần thứ hai

Invariant của idempotency:

```text
Same tenantId + requestId + payload:
  lần đầu -> order RESERVED + stock -quantity
  lần sau -> trả existing order
               + stock không đổi
```

Thử bằng:

```text
Initial available = 5
Call place(requestId="dup-01", quantity=2)
Call place(requestId="dup-01", quantity=2)

Expected:
  orders unique key count = 1
  available = 3
  hai responses cùng logical order ID
```

Nếu sau hai lần available = 1, service đã trừ hai lần dù chỉ có một order — lỗi nghiêm trọng. Transaction + unique index giúp chặn, nhưng error handling/retries vẫn phải được test.

## 27. Same key nhưng payload khác phải bị từ chối

Ví dụ:

```text
tenant-a / req-123 / SKU-BOOK-001 / qty=1
tenant-a / req-123 / SKU-BOOK-001 / qty=4
```

Chỉ vì `requestId` giống nhau không có nghĩa hai requests tương đương. API nên trả một **idempotency conflict** rõ nghĩa, không dùng upsert `$set` cập nhật quantity của order hiện hữu.

Nếu cần normalize payload:

- Currency, price snapshot, discount, shipping address, user identity.
- Canonicalization của số tiền/Unicode/optional fields.
- Hash version và schema version.
- Không log raw PII vào duplicate-key error message.

Trong bài lab chỉ so `sku` + `quantity`, vì các thành phần khác chưa được mô hình hóa.

## 28. Cập nhật tồn kho khi order có nhiều SKUs

Nếu một order chứa:

```json
{
  "items": [
    { "sku": "SKU-A", "quantity": 2 },
    { "sku": "SKU-B", "quantity": 1 }
  ]
}
```

cần giảm tồn kho ở **hai documents inventory**. Chỉ dùng atomic update riêng cho mỗi SKU mà không transaction có thể để lại:

```text
SKU-A giảm thành công
SKU-B hết hàng
Order không được chấp nhận
Nhưng SKU-A đã giảm
```

Trong transaction:

1. Tạo order ở trạng thái phù hợp.
2. Với từng item, update inventory với `available >= quantity`.
3. Nếu bất kỳ item không đủ, throw/abort transaction.
4. Nếu tất cả đều hợp lệ, commit.

### Tránh deadlock/thrashing theo workload

Khi nhiều requests cập nhật cùng nhiều SKUs, có thể tăng contention/write conflicts. Có thể áp một **thứ tự SKU nhất quán** khi update để giảm sự phức tạp của tương tác, giữ transaction ngắn và giới hạn số items per order. MongoDB xử lý concurrency khác hệ cơ sở dữ liệu khóa truyền thống, nên không coi thứ tự này là cam kết loại bỏ mọi write conflict.

## 29. Không dùng upsert để “tự tạo inventory” khi hết SKU

Anti-pattern:

```javascript
db.inventory.updateOne(
  { _id: "SKU-BOOK-001", available: { $gte: 2 } },
  { $inc: { available: -2 } },
  { upsert: true }
);
```

Nếu không có document match vì **available < 2**, lệnh upsert có thể cố insert một document mới với cùng `_id` và gây E11000. Nếu SKU không tồn tại, lệnh có thể tạo record không hợp lệ với available âm.

Để giữ hàng, luôn dùng **`upsert:false`**. Một SKU chưa tồn tại hay không còn đủ số lượng là điều kiện không chấp nhận đặt hàng, không phải lời mời tạo inventory document.

## 30. Phân biệt reserve, release và cancel

Trong nghiệp vụ thật, huỷ order có thể yêu cầu hoàn tồn kho:

```text
Order status RESERVED
       |
       v
Conditional transition to CANCELLED
       |
       v
Increment available by quantity
```

Không viết:

```java
orders.updateOne(eq("_id", orderId),
    Updates.set("status", "CANCELLED"));
inventory.updateOne(eq("_id", sku),
    Updates.inc("available", quantity));
```

như hai lệnh độc lập nếu policy yêu cầu chúng cùng atomic. Nếu request cancel được gửi hai lần, stock có thể được cộng lại hai lần.

### Quy tắc huỷ idempotent

Trong transaction:

1. Update order với filter `{_id:orderId,status:"RESERVED"}` sang CANCELLED.
2. Chỉ nếu matchedCount=1 mới `$inc inventory.available` thêm quantity.
3. Commit cả hai writes.
4. Nếu order đã CANCELLED, không increment lại.

Nếu order SHIPPED hay PAYMENT_CAPTURED, huỷ có thể cần nghiệp vụ hoàn trả khác, không chỉ `$inc`.

## 31. Ví dụ huỷ đơn với transaction

Đoạn mã ngắn mô tả invariant:

```java
session.withTransaction(() -> {
    Document order = orders.find(
        session,
        Filters.eq("_id", orderId)
    ).first();

    if (order == null) {
        throw new IllegalArgumentException(
            "Order không tồn tại");
    }

    UpdateResult changed = orders.updateOne(
        session,
        Filters.and(
            Filters.eq("_id", orderId),
            Filters.eq("status", "RESERVED")
        ),
        Updates.set("status", "CANCELLED")
    );

    if (changed.getMatchedCount() == 0) {
        // Đã xử lý hoặc trạng thái không cho phép huỷ.
        return false;
    }

    inventory.updateOne(
        session,
        Filters.eq("_id", order.getString("sku")),
        Updates.inc("available",
            order.getInteger("quantity"))
    );

    return true;
}, options);
```

Biến `orders`, `inventory`, `session`, `options` và `orderId` được tạo trong service context như các ví dụ trước. Đây là **đoạn minh họa transaction**, không phải method độc lập có thể paste vào bất kỳ file Java nào.

Trong production cần kiểm tra kết quả increment của inventory, tenant scope, quyền huỷ và khả năng sku bị xóa. Đồng thời không nên đọc order rồi cho phép một update ngoài transaction làm thay đổi status mà không đồng bộ stock.

## 32. Java test harness: tạo concurrency thật

Để kiểm thử 40 requests đặt cùng SKU tồn kho 10, dùng:

- `ExecutorService` để tạo nhiều workers.
- `CountDownLatch` để các workers bắt đầu gần cùng thời điểm.
- `Future` để thu outcome và propagate exceptions.
- MongoDB thật với unique index và transaction support.
- Fixtures có SKU và tenant ID duy nhất mỗi test.

Chạy với **một `MongoClient` dùng chung**, vì Java driver được thiết kế để hỗ trợ concurrent operations; mỗi transaction phải có **session riêng**, không chia cùng `ClientSession` cho nhiều threads.

### Mã test JUnit: khung chạy đồng thời

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

class OrderConcurrencyIntegrationTest {

    // Được inject/khởi tạo trong test setup thật.
    private MongoClient client;
    private MongoDatabase db;
    private OrderService service;

    @Test
    void fortyRequestsMustNotOversellTenUnits() throws Exception {
        String tenantId = "test-" + UUID.randomUUID();
        String sku = "SKU-" + UUID.randomUUID();

        MongoCollection<Document> inventory =
            db.getCollection("inventory");
        MongoCollection<Document> orders =
            db.getCollection("orders");

        inventory.insertOne(
            new Document("_id", sku)
                .append("available", 10)
                .append("initialStock", 10)
        );

        int attempts = 40;
        ExecutorService pool = Executors.newFixedThreadPool(20);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<String>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < attempts; i++) {
                final int index = i;

                Callable<String> task = () -> {
                    start.await();
                    try {
                        service.place(new CreateOrder(
                            tenantId,
                            "req-" + index,
                            sku,
                            1
                        ));
                        return "SUCCESS";
                    } catch (InsufficientStockException ex) {
                        return "OUT_OF_STOCK";
                    }
                };

                futures.add(pool.submit(task));
            }

            start.countDown();

            long success = 0;
            long outOfStock = 0;

            for (Future<String> future : futures) {
                String outcome = future.get(
                    90, TimeUnit.SECONDS);

                if ("SUCCESS".equals(outcome)) {
                    success++;
                } else if ("OUT_OF_STOCK".equals(outcome)) {
                    outOfStock++;
                } else {
                    fail("Outcome không dự kiến: " + outcome);
                }
            }

            Document finalStock = inventory.find(
                Filters.eq("_id", sku)).first();

            assertNotNull(finalStock);
            assertEquals(0, finalStock.getInteger("available"));

            long reservedOrders = orders.countDocuments(
                Filters.and(
                    Filters.eq("tenantId", tenantId),
                    Filters.eq("sku", sku),
                    Filters.eq("status", "RESERVED")
                )
            );

            assertEquals(10L, success);
            assertEquals(30L, outOfStock);
            assertEquals(10L, reservedOrders);
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

**Lưu ý về khung test:**

- Phải cấu hình `client`, `db`, `service` và unique index thật trước khi chạy. Trong Spring/JUnit dùng injection/test setup phù hợp.
- `get(90, TimeUnit.SECONDS)` là **deadline minh họa**, không phải SLA universal. Môi trường CI chậm có thể cần policy timeout khác.
- Unexpected transaction/network/driver errors phải làm test **fail**, không đổi thành OUT_OF_STOCK.
- Kết quả 10 thành công, 30 hết hàng là kỳ vọng **khi tất cả attempts hoàn tất theo policy**, không có người viết khác vào cùng SKU.
- Nếu quá nhiều write conflicts vượt retry budget, test phải báo **infrastructure/contention issue**, không tính như đơn hết hàng.
- Không chạy stress test này trên production. Sử dụng test SKU/tenant riêng và cleanup có kiểm soát.

## 33. Vì sao kết quả 10 thành công là hợp lý?

Trong lab:

```text
Initial stock = 10
40 requests riêng biệt
Each qty = 1
No restock / no cancellation
Successful reservation là transaction commit
```

Với điều kiện transaction và retry hoạt động chính xác:

```text
10 order transactions commit:
  10 * decrement(1) = 10

30 requests còn lại:
  stock không đủ -> không commit order

Final available = 0
Reserved orders = 10
```

Đừng dùng kiểm tra “`available >= 0`” làm invariant duy nhất: hệ thống có thể **trừ stock đúng** nhưng tạo **0 orders** nếu lệnh insert luôn thất bại ngoài transaction. Phải kiểm tra **đồng thời** available, order count, summed quantity và uniqueness.

## 34. Test duplicate request đồng thời

Một test khác dùng cùng requestId:

```text
Initial stock = 5

Task A -> tenant=test-X / requestId=dup-01 / qty=2
Task B -> tenant=test-X / requestId=dup-01 / qty=2

Expected after settle:
  exactly one order for (tenant, requestId)
  order quantity = 2
  stock = 3
  không có external side effect lặp
```

Có thể hai calls đều nhận cùng order ID nếu application xử lý duplicate idempotently; hoặc một call phải chờ reconciliation nếu commit còn chưa rõ. **Không được xem stock=1 là hợp lệ** chỉ vì unique index vẫn giữ một order: đó là dấu hiệu stock bị trừ hai lần.

### Test same key/different payload

```text
Task A: requestId=dup-02, qty=1
Task B: requestId=dup-02, qty=3
```

Kỳ vọng:

- Chỉ một request hợp lệ được chấp nhận theo first-writer policy.
- Existing order giữ payload của request thắng.
- Request còn lại nhận conflict, không overwrite order.
- Tồn kho giảm **đúng quantity của order được commit**.

Khi chạy concurrent, không ép Task A chắc chắn thắng.

## 35. Test lỗi sau khi insert order nhưng trước khi giảm stock

Transaction cho phép mô phỏng lỗi có chủ đích:

```java
try (ClientSession session = client.startSession()) {
    session.withTransaction(() -> {
        orders.insertOne(
            session,
            new Document("_id", "fault-order-001")
                .append("sku", "SKU-BOOK-001")
                .append("quantity", 1)
        );

        throw new IllegalStateException(
            "Injected fault before decrement");
    }, options);
}
```

Trong test setup cô lập, sau exception:

```text
Order fault-order-001 không được commit
Inventory không bị trừ
```

Đây là lỗi business/runtime được ném trước commit; convenient transaction API phải abort theo cơ chế của driver. Đừng làm tương tự bằng cách **kill thật mongod hoặc pod** trên một cluster dùng chung chỉ để chứng minh rollback.

### Test lỗi sau khi giảm stock

Nếu thứ tự là decrement rồi insert, chèn exception sau decrement nhưng trước insert. Vì cả hai operations thuộc cùng transaction, thay đổi inventory chưa commit phải được abort.

## 36. Test lỗi ở commit và kết quả không rõ

Một tình huống khó hơn:

```text
Transaction writes đều thành công
      |
      v
Client gửi commitTransaction
      |
      v
Network disconnect
      |
      v
Client chưa biết commit đã được áp dụng chưa
```

Không thể xử lý bằng cách **tạo requestId mới và lặp lại toàn bộ order**. Có thể dẫn đến hai đơn hàng nếu transaction đầu đã commit.

Hướng xử lý:

1. Để driver xử lý các retry conditions được hỗ trợ, đặc biệt đối với commit.
2. Nếu vẫn không rõ, lưu correlation/idempotency key và báo kết quả đang xác nhận theo API contract.
3. Đối soát bằng stable `(tenantId, requestId)` với read concern/route phù hợp.
4. Khi existing order đã commit, so payload và trả kết quả.
5. Nếu chưa thấy và connectivity chưa hồi phục, **không khẳng định chắc là thất bại**.
6. Không thực hiện external payment/email lặp nếu outcome chưa rõ.

Đây là lý do idempotency và unique index vẫn cần **ngay cả khi đã có transaction**.

## 37. Những lỗi cần phân loại riêng

| Tín hiệu | Ý nghĩa có thể | Hướng xử lý |
| --- | --- | --- |
| `matchedCount=0` khi decrement | SKU missing hoặc không đủ stock | Business reject, abort |
| E11000 trên `uk_tenant_request` | Same request key đã có | Đọc lại, so payload, idempotency/conflict |
| E11000 trên index khác | Constraint business khác | Không coi là replay thành công |
| `TransientTransactionError` | Transaction cần retry theo driver contract | Retry bounded toàn transaction |
| `UnknownTransactionCommitResult` | Không chắc commit | Retry commit/reconcile |
| `WriteConflict` | Concurrent writes cùng documents | Theo transient semantics, tránh retry storm |
| `MongoTimeoutException` | Không chọn được server hoặc connection issue | Kiểm tra topology/network, bounded retry |
| `MongoSocketTimeoutException` | I/O timeout | Outcome có thể không rõ; reconcile |
| Write concern timeout | Không đạt acknowledgment policy | Không mặc định chưa ghi |
| Unauthorized | Service thiếu DB privilege | Sửa RBAC, không retry liên tục |
| Validation error | Dữ liệu/schema không hợp lệ | Trả input/domain error |

Một exception có thể được wrapper bởi Spring Data hoặc driver API khác. Hãy phân loại theo structured error code/labels và context, không chỉ match text `"timeout"` hay `"duplicate"` trong error message.

## 38. Spring Data MongoDB: cấu hình transaction manager

Nếu ứng dụng dùng Spring Boot/Spring Data MongoDB, có thể sử dụng `MongoTransactionManager`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {

    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
```

Với topology MongoDB hỗ trợ, Spring sẽ quản lý session/transaction cho những Spring Data operations tham gia transaction scope.

**Không có nghĩa chỉ thêm `@Transactional` lên method là đủ trong mọi project**. Cần xem transaction manager bean, session binding, driver URI, MongoDB topology và version.

## 39. Spring Data: service giữ hàng và tạo đơn

Ví dụ rút gọn:

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SpringOrderService {

    private final MongoTemplate template;

    public SpringOrderService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional
    public String place(CreateOrder r) {
        String id = java.util.UUID.randomUUID().toString();

        OrderEntity order = new OrderEntity(
            id, r.tenantId(), r.requestId(),
            r.sku(), r.quantity(), "RESERVED");

        template.insert(order, "orders");

        Query filter = Query.query(
            Criteria.where("_id").is(r.sku())
                .and("available").gte(r.quantity())
        );

        Update decrement = new Update()
            .inc("available", -r.quantity());

        UpdateResult result = template.updateFirst(
            filter, decrement, "inventory");

        if (result.getMatchedCount() != 1) {
            throw new InsufficientStockException(r.sku());
        }

        return id;
    }
}
```

`OrderEntity` trong ví dụ là domain class/constructor do project tự định nghĩa. Khác với khung Java Sync Driver, ví dụ này dựa trên **Spring transactional proxy**: method phải được gọi qua Spring-managed proxy, không phải self-invocation nội bộ làm mất transaction advice.

### Cảnh báo khi retry Spring transactions

Nếu cần retry cả transaction, hãy đặt retry boundary **bên ngoài** transaction boundary có thể tạo **transaction mới cho mỗi attempt**. Không thêm `@Retryable` rồi giả định mọi thứ tự annotation/proxy và mọi exception đều được retry đúng; phải kiểm tra actual AOP order và điều kiện lỗi của Spring Data/driver.

Tuyệt đối không biến `InsufficientStockException` thành lỗi retry vô hạn.

## 40. Spring Data `@Version` có thay transaction không?

Không. Với một entity inventory:

```java
@Version
private Long version;
```

Spring Data có thể dùng optimistic locking khi `save()` trên entity có version. Điều đó giúp chống lost update giữa những entity saves được hỗ trợ.

Nhưng:

```text
Update inventory version N -> N+1
Insert order -> fail
```

vẫn là hai operations độc lập nếu không có transaction. `@Version` không tự roll back stock khi order insert thất bại.

Khi dùng raw `MongoTemplate.updateFirst()` hoặc Java driver, cần hiểu ai quản lý version field và filter. Tăng version mà không có expected-version predicate **không tự tạo optimistic CAS**. Nếu bài toán chỉ là atomic decrement, filter `available >= quantity` thường là điều kiện nghiệp vụ trực tiếp.

## 41. Dùng `findOneAndUpdate` để trả tồn kho mới

Không phải mọi endpoint đặt hàng đều cần trả document stock. Nhưng nếu muốn lấy kết quả sau conditional decrement trong một operation:

```java
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;

Document updated = inventory.findOneAndUpdate(
    Filters.and(
        Filters.eq("_id", sku),
        Filters.gte("available", quantity)
    ),
    Updates.inc("available", -quantity),
    new FindOneAndUpdateOptions()
        .returnDocument(ReturnDocument.AFTER)
);

if (updated == null) {
    throw new InsufficientStockException(sku);
}
```

Đây là một **atomic update trên inventory document**. Nó **không** tự gắn với insert order ở collection khác. Muốn cùng transaction phải truyền `ClientSession` cho cả operation hoặc dùng Spring transaction scope phù hợp.

### Vì sao không đọc `available` rồi trả lại như kết quả cuối?

Sau khi request của bạn commit, request khác có thể tiếp tục đặt hàng và giảm stock. Con số `available` trả về chỉ đại diện cho **thời điểm update của bạn**, không phải lượng tồn “bất biến” tới khi frontend render.

## 42. Tính đúng đắn của test: phải xem cả các trạng thái

Một test không đủ tốt:

```java
assertTrue(inventory.available >= 0);
```

Giả sử một service không bao giờ trừ stock nhưng vẫn tạo orders:

```text
initial=10, finalAvailable=10
orders RESERVED=100
available>=0 -> PASS giả
```

Một test mạnh hơn khi tất cả requests đã settle:

```text
finalAvailable >= 0
SUM(reservedOrder.quantity) <= initialStock
finalAvailable + SUM(reservedOrder.quantity) == initialStock
COUNT_DISTINCT(tenantId,requestId) == COUNT(orders)
Không có committed order cho failed reservation
Không có stock decrement cho aborted transaction
```

### Aggregate để đối soát

Trên database lab:

```javascript
db.orders.aggregate([
  {
    $match: {
      sku: "SKU-BOOK-001",
      tenantId: "tenant-demo",
      status: "RESERVED"
    }
  },
  {
    $group: {
      _id: "$sku",
      reservedQuantity: { $sum: "$quantity" },
      orderCount: { $sum: 1 }
    }
  }
]);
```

Nếu nhiều tenants cùng dùng SKU trong một kho chung, để kiểm tra invariant tổng kho phải cộng **mọi order được reserve trên SKU đó**, không chỉ tenant-demo. Trong lab đang tách fixture, có thể dùng tenant filter để đối chiếu đúng test scope.

## 43. Test uniqueness theo business key

Đếm orders trùng `(tenantId, requestId)`:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        requestId: "$requestId"
      },
      count: { $sum: 1 },
      orderIds: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } }
]);
```

Kỳ vọng **không trả nhóm duplicate**. Tuy vậy, pipeline này không thay được việc xác minh unique index đã thực sự tồn tại. Với dữ liệu production rất lớn, `$push` mọi IDs gây memory pressure; chọn giới hạn/batch và index status phù hợp.

### Đừng xem aggregation count là giải pháp cạnh tranh

Đọc count rồi quyết định insert vẫn có race. Aggregation ở đây là **đối soát sau test**, trong khi unique index là **ràng buộc thực thi ngay lúc write**.

## 44. Kiểm thử batch có áp lực cao

Nếu muốn tăng số lần thử:

```text
initial=100
parallelism=8, 16, 32, 64
total requests=1_000
qty=1
```

Đo:

- Success rate và số từ chối do hết hàng.
- Transient write conflicts / transaction retry count.
- Thời gian p50/p95/p99.
- Throughput commits/giây.
- Connection pool wait.
- Disk I/O và WiredTiger cache pressure.
- CPU và memory.
- Tỷ lệ duplicate idempotent requests.
- Mất kết nối, timeouts và unknown outcomes.

### Không chỉ tăng threads cho đến khi server gục

Mục tiêu học là **kiểm tra invariant**, không phải gây denial-of-service. Dùng replica set lab có resource budget, ramp-up, timeouts và cleanup. Số threads cao có thể làm transaction retries tăng mạnh, nhưng điều đó không có nghĩa database “sai atomicity”.

## 45. Test có retry storm

Một tình huống thực tế:

```text
50 original requests
Mỗi client timeout rồi retry 3 lần
=> có thể thành 200 API calls
```

Với cùng idempotency keys:

- Có tối đa 50 **logical orders**, không phải 200.
- Một số retries nên trả existing result.
- Không trừ stock nhiều lần theo một requestId.
- Không gửi payment/email nhiều lần.

Một test có thể tạo 50 distinct requestIds rồi submit mỗi requestId lặp bốn lần. Sau khi mọi calls settle, assert:

```text
orders count <= 50
unique(tenantId, requestId) count == orders count
total stock decremented == SUM(reserved quantities)
```

Không mặc định tất cả 50 orders sẽ được tạo khi stock không đủ. Kỳ vọng số thành công phải căn cứ `initialStock` và quantity.

## 46. Test cancellation và stock release cạnh tranh

Hai requests cùng huỷ một order RESERVED:

```text
Order status RESERVED, qty=2
Stock available=3

Cancel A -------------------\
                             --> cùng nhìn RESERVED
Cancel B -------------------/

Expected:
  Order chuyển sang CANCELLED một lần
  Stock tăng từ 3 lên 5 một lần
```

Không được có stock available=7. Để đạt điều này, conditional status update và stock increment phải **cùng transaction**, hoặc dùng một workflow idempotent có invariant tương đương.

### Test đặt hàng và huỷ cạnh tranh

Trong hệ thống thật, có thể xảy ra:

```text
Reserve new order / release old order / restock
```

Các operations đều cập nhật cùng inventory document, có thể tăng write contention. Kiểm tra invariant qua nhiều state transitions, không chỉ bài toán “20 đặt hàng, 5 món”.

## 47. Có thể dùng một document để tránh transaction?

Một mô hình:

```javascript
{
  _id: "SKU-BOOK-001",
  available: 5,
  reservations: [
    { requestId: "REQ-1", quantity: 1 }
  ]
}
```

Nếu mọi thứ cần giữ chung nằm trong một document, một update pipeline/conditional update có thể sửa stock và reservation list **nguyên tử**.

Nhưng:

- Array reservations có thể tăng không giới hạn.
- Một SKU quá “hot” gây contention.
- BSON document có giới hạn kích thước.
- Order còn cần địa chỉ, thanh toán, fulfillment, audit ở scope khác.
- Dữ liệu phân tán trên nhiều SKUs không còn cùng một document.

Thiết kế này phù hợp một số bài toán nhỏ nhưng **không thay thế mọi mô hình orders collection**.

## 48. Reservation ledger hoặc saga: khi nào phù hợp?

Một hệ thống rất lớn có thể tách:

```text
Order intent / idempotency record
       |
       v
Reservation command
       |
       v
Atomic stock claim + reservation ledger
       |
       v
Payment / fulfillment events
       |
       v
Final state / compensation
```

Đây có thể là **eventually consistent workflow** với:

- Idempotency keys.
- Per-SKU conditional updates.
- State machine cho NEW/RESERVED/FAILED/RELEASED.
- Outbox và at-least-once delivery.
- Bounded retry/dead-letter handling.
- Reconciliation giữa ledger và materialized stock.

Khi ấy invariant “stock.available + SUM(active reservations) = initial + restocks” vẫn cần được kiểm soát, nhưng các bước có thể không cùng commit tức thời; hệ thống phải định nghĩa **trạng thái trung gian hợp lệ** và quy trình bù trừ.

## 49. Viết consistency contract cho API

Ví dụ:

```http
POST /api/orders
Idempotency-Key: req-1001
Content-Type: application/json

{
  "sku": "SKU-BOOK-001",
  "quantity": 1
}
```

Server lấy tenant từ authenticated principal; không tin tenant do client tùy ý gửi.

Kết quả mẫu:

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "orderId": "order-1001",
  "status": "RESERVED"
}
```

Nếu retry đúng key/payload, API có thể trả existing order/result theo contract, ví dụ 200 OK hoặc cùng status code đã lưu. Nếu stock hết, trả business error nhất quán (409/422 tùy API). Nếu cùng key khác payload, trả conflict. Nếu kết quả commit chưa rõ, không tuyên bố đơn thất bại hoặc thành công khi chưa thể đối soát.

### API thành công sau điều kiện nào?

Chỉ trả `RESERVED` thành công khi transaction commit đã được xác nhận theo durability contract. Không trả “đã giữ hàng” ngay sau khi gọi `insertOne()` trong callback chưa commit.

## 50. Read concern và write concern trong bài thực hành

Một transaction có thể chọn:

```java
TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .readPreference(ReadPreference.primary())
    .build();
```

Ý nghĩa:

- `SNAPSHOT` giúp reads trong transaction nhìn thấy snapshot nhất quán theo semantics.
- `MAJORITY` là mức xác nhận commit được lựa chọn cho replication durability.
- `primary` là read preference phù hợp với transaction có writes.

Không coi việc chọn `SNAPSHOT` là tự động ngăn overselling: **filter `available >= quantity`** mới trực tiếp bảo vệ số lượng. Không coi `MAJORITY` là bảo đảm mọi lỗi mạng sẽ biến mất; UnknownCommit vẫn có thể cần retry/reconcile.

### Đối soát sau test

Khi mọi futures đã hoàn tất và không còn writer của fixture, đọc final state qua primary với read/write concern phù hợp. Không assert invariant toàn hệ thống từ hai `find()` riêng rẽ giữa lúc rất nhiều writers vẫn đang commit, vì snapshot thời điểm có thể khác nhau.

## 51. Sharded cluster và giao dịch xuyên shard

Nếu collection `inventory` và `orders` được sharded:

- Transactions có thể trải qua nhiều shards theo điều kiện/topology.
- Overhead/latency của cross-shard transaction có thể cao hơn.
- Router `mongos`, shard key và unique index rules phải được xem xét.
- Unique idempotency key trên sharded collection phải đáp ứng **quy tắc unique index/shard key** của MongoDB version.
- Truy vấn theo tenant/requestId nên hỗ trợ routing/targeting phù hợp.

Không tự tạo unique index `{tenantId:1,requestId:1}` trên một sharded collection với shard key không tương thích rồi nghĩ MongoDB chắc chắn enforce global uniqueness. Cần kiểm tra actual index constraints và topology.

Trong bài lab, nên bắt đầu với **replica set không shard** để quan sát concurrency rõ, sau đó mới mở rộng sang nhiều shards.

## 52. Kiểm thử bằng mock khác integration test thật

Một mock repository có thể trả kết quả:

```text
findStock -> 5
updateStock -> success
insertOrder -> success
```

nhưng **không mô phỏng đúng**:

- Two concurrent clients cùng thấy snapshot cũ.
- Write conflicts giữa transactions.
- Unique index enforcement thật.
- Replica set sessions/transaction commit.
- Network/unknown commit result.
- Durability/majority behavior.

Vì vậy:

| Test cấp độ | Mục tiêu |
| --- | --- |
| Unit test | Validate quantity, idempotency payload, API mapping |
| MongoDB integration | Atomic `$inc`, unique index, transaction rollback |
| Concurrency integration | 20–100 writers cùng SKU và same-key retries |
| Fault injection | Exception giữa transaction, không tạo partial state |
| Load/stress | Throughput, retries, contention, operational stability |
| E2E API | Status codes, tenant auth, idempotency header, no oversell |

Mock tests hữu ích nhưng không được dùng làm bằng chứng duy nhất rằng MongoDB transaction hoạt động đúng.

## 53. Bài thực hành đối chứng: cố tình tạo lost update

Trong lab riêng, có thể viết:

```java
Document stock = inventory.find(
    Filters.eq("_id", sku)).first();

int current = stock.getInteger("available");

// Đồng bộ threads tại đây để cả hai cùng đọc số cũ.
readBarrier.await();

inventory.updateOne(
    Filters.eq("_id", sku),
    Updates.set("available", current - 1)
);
```

Với 2 tasks cùng đọc `available=2`, cả hai có thể set về 1. Sau đó chạy bản dùng `$inc` và filter để so sánh:

```java
inventory.updateOne(
    Filters.and(
        Filters.eq("_id", sku),
        Filters.gte("available", 1)
    ),
    Updates.inc("available", -1)
);
```

Kỳ vọng:

- Bản read–modify–write có thể mất một decrement.
- Bản conditional `$inc` từ 2 đơn độc lập có thể giảm tới 0 nếu cả hai được chấp nhận.

**Thực hành này chỉ để tái hiện bug trên dữ liệu giả**, không đưa implementation cố tình sai vào ứng dụng production.

## 54. Bài thực hành đối chứng: không transaction

Tạo một service có chủ đích:

```text
update stock via conditional $inc -> success
raise injected exception
insert order -> không chạy
```

Kết quả mong đợi của bản **không transaction**:

```text
stock giảm
không có order
invariant fail
```

Sau đó dùng transaction để thực thi cùng fault injection:

```text
BEGIN
update stock
raise injected exception
ABORT

stock không giảm
không có order
invariant giữ đúng
```

Hai test đối chứng giúp hiểu transaction giải quyết vấn đề gì: **atomicity xuyên documents**, không chỉ tránh hai clients cùng đọc một con số cũ.

## 55. Ma trận kiểm thử tổng hợp

| Mã | Tình huống | Invariant/điều kiện pass |
| --- | --- | --- |
| CONC-01 | 1 request qty=1 khi stock=5 | 1 order, available=4 |
| CONC-02 | 1 request qty=6 khi stock=5 | Không order, available=5 |
| CONC-03 | 20 requests khác key, stock=5 | 5 orders, available=0 |
| CONC-04 | 2 requests khác key, stock=1 | 1 order, available=0 |
| CONC-05 | 2 requests cùng key/payload | 1 order, trừ stock một lần |
| CONC-06 | Same key, different quantity | Chỉ một payload được chấp nhận |
| CONC-07 | SKU không tồn tại | Không order và không tạo inventory mới |
| CONC-08 | Quantity=0/âm | Reject trước transaction |
| CONC-09 | Fault sau order insert | Không commit order/stock |
| CONC-10 | Fault sau stock decrement | Không commit order/stock |
| CONC-11 | Retry transient write conflict | Kết quả cuối không oversell |
| CONC-12 | Commit outcome unknown | Reconcile theo stable request key |
| CONC-13 | 40 requests, stock=10 | 10 order, available=0 |
| CONC-14 | 100 duplicate API retries | Không tạo 100 orders cho một request |
| CONC-15 | Cancel hai lần | Stock được release một lần |
| CONC-16 | Place and cancel concurrently | Consistency theo state machine |
| CONC-17 | Một order gồm hai SKUs | Hoặc đủ cả hai, hoặc không reserve SKU nào |
| CONC-18 | Bulk test có unexpected timeout | Test fail/unknown, không ngụy trang thành OOS |
| CONC-19 | Chưa tạo unique request index | Test setup fail, không claim idempotency |
| CONC-20 | Raw writer sửa stock ngoài contract | Test phát hiện invariant sai |
| CONC-21 | App restart sau commit | Retry không tạo double order |
| CONC-22 | Replica set failover trong lab | Kiểm tra outcome/retry và consistency |
| CONC-23 | Order read từ lagging secondary | Không kết luận thất bại ngay vì chưa thấy |
| CONC-24 | Multi-tenant same requestId | Scope uniqueness đúng tenant |

**Không cần ép mọi concurrency case vào một JUnit test khổng lồ.** Mỗi case nên có fixture riêng, timeouts, cleanup, expected business outcomes và error classification để dễ khoanh vùng lỗi.

## 56. Quan sát throughput và contention

Những metric nên thu:

| Metric | Ý nghĩa |
| --- | --- |
| Successful reservations/s | Throughput nghiệp vụ |
| Out-of-stock rejections/s | Mức độ thiếu hàng hợp lệ |
| Duplicate idempotent requests/s | Tỷ lệ client retries |
| Same-key different-payload conflicts | Dấu hiệu misuse API |
| Transaction retries/s | Contention hoặc transient errors |
| Write conflict errors/s | Các writes cùng documents |
| Unknown commit results | Sự cố mạng/replication cần đối soát |
| p50/p95/p99 latency | Trải nghiệm khách hàng |
| MongoDB pool checkout wait | Pool bottleneck |
| CPU, memory, disk IOPS | Giới hạn resource |
| Orders with no matching stock reservation | Sai invariant cần điều tra |
| Available below zero | Vi phạm nghiêm trọng |

### Một hot SKU là điểm contention tự nhiên

Một inventory document cho SKU được hàng chục nghìn người mua cùng lúc trở thành **điểm tuần tự hóa logic** cho các decrements. Atomicity đảm bảo không oversell nhưng không bảo đảm throughput vô hạn.

Hướng tối ưu có thể là:

- Admission control/rate limit ở API.
- Queue đặt hàng có idempotency.
- Quota/token phân vùng có reconciliation rõ ràng.
- Reservation service chuyên biệt.
- Giảm transaction duration và số documents mỗi transaction.
- Không tăng number of threads vô hạn.

Những kỹ thuật này có thể đổi consistency/availability trade-off, nên phải giữ invariant bằng tests và audit.

## 57. Quyền truy cập và tenant scope trong bài thực hành

Một lệnh:

```javascript
db.orders.findOne({ requestId: "req-001" });
```

có thể tìm nhầm order của tenant khác nếu requestId chỉ unique **trong tenant**. Để đối soát:

```javascript
db.orders.findOne({
  tenantId: "tenant-demo",
  requestId: "req-001"
});
```

Trong API, `tenantId` phải lấy từ principal đã xác thực hoặc context đã được authorization, không phải giá trị client có thể đổi tùy ý.

### Database account không biết HTTP user

Java service thường kết nối MongoDB bằng một service credential có quyền trên collections. MongoDB RBAC giới hạn quyền service đó, **không tự kiểm tra ai trong các HTTP users sở hữu từng order**. Authorization theo tenant/owner phải có trong application queries/commands.

### Test cross-tenant

Hai tenants có thể cùng `requestId="req-1"` nếu unique key chứa tenantId. Nhưng user A không được đọc/cancel order của B; kiểm thử riêng cho GET/PATCH/DELETE và error responses.

## 58. Thiết kế cleanup an toàn cho concurrency tests

Một JUnit test chạy lỗi giữa chừng có thể để lại fixtures. Không nên gọi:

```javascript
db.dropDatabase();
```

trong một môi trường lab chia sẻ giữa nhiều CI jobs.

Thay vào đó:

1. Mỗi test tạo `tenantId` và `sku` unique.
2. Sau khi futures kết thúc, cleanup `orders` theo tenantId/testRunId.
3. Cleanup inventory theo SKU test.
4. Không xóa documents bên ngoài scope.
5. Nếu test failure cần giữ evidence, lưu các IDs và kết quả đã sanitize.
6. Dùng một fixture-admin identity đủ quyền nhưng **khác** service account dùng trong test quyền nghiệp vụ.

Nếu cleanup có thể diễn ra khi một thread vẫn ghi, test có thể tạo ra kết quả rất khó hiểu. Bảo đảm workers đã kết thúc/được hủy có kiểm soát trước cleanup.

## 59. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách đúng hơn |
| --- | --- | --- |
| Đọc tồn rồi `$set(available-1)` | Lost update | Conditional `$inc` |
| `$inc(-qty)` nhưng thiếu `available >= qty` | Stock âm | Query có điều kiện |
| Decrement rồi insert order ngoài transaction | Stock giảm nhưng không có order | Transaction hoặc bù trừ |
| Insert order rồi decrement ngoài transaction | Order không có hàng | Transaction hoặc state machine |
| Tạo `requestId` mới khi retry cùng intent | Double order | Stable idempotency key |
| Có requestId nhưng thiếu unique index | Duplicate orders | Unique constraint |
| Catch mọi duplicate rồi trả success | Cùng key khác payload bị che | Read + compare payload |
| Bật `upsert:true` trên inventory decrement | Có thể tạo stock sai/duplicate | `upsert:false` |
| Retry cả transaction kèm payment call | Charge trùng | External idempotency/outbox |
| Đổi mọi lỗi thành out-of-stock | Ẩn lỗi kết nối/transaction | Phân loại exceptions |
| Dùng `@Version` thay transaction hai collections | Partial writes | Multi-doc transaction |
| Assert chỉ `available>=0` | Bỏ sót order/stock mismatch | Check sum invariant |
| Chạy 100 threads với một `ClientSession` | Sai session concurrency contract | Session per transaction |
| Test standalone rồi bỏ transaction | Không test atomicity | Replica set/sharded lab |
| Read lagging secondary để kết luận order chưa tạo | False negative | Reconcile theo consistency policy |
| Gọi `dropDatabase` trong CI shared env | Xóa dữ liệu test khác | Test IDs riêng, scoped cleanup |
| Đếm cả đơn CANCELLED trong reservation total | Đối soát sai | Sum theo active reservation statuses |
| Chỉ kiểm tra count orders | Có thể quantity sai hoặc stock sai | Count + quantities + stock |
| Tự gửi tenantId chưa xác thực | Cross-tenant access | Scope từ principal |
| Transaction dài chờ thanh toán | Tăng contention/timeout | Commit reservation rồi workflow riêng |

## 60. Runbook khi phát hiện overselling hoặc lệch đơn/tồn

### Bước 1 — Phân loại triệu chứng

```text
inventory.available < 0?
SUM(active reservations) vượt initial + restocks?
Có orders duplicate (tenantId,requestId)?
Có orders RESERVED nhưng không trừ kho?
Có stock đã trừ nhưng không có orders?
```

### Bước 2 — Giảm tác hại

- Tạm dừng hoặc giới hạn đặt hàng SKU bị ảnh hưởng theo incident policy.
- Không chạy update tăng stock hàng loạt khi chưa đối soát.
- Giữ request IDs, correlation IDs, timing/driver errors đã sanitize.
- Kiểm tra retries, message redelivery, version mới deploy.

### Bước 3 — Xác minh đường ghi

- Mọi writers có dùng conditional `available >= qty` không?
- Có còn read–modify–write qua repository.save không?
- Order insert và stock decrement có dùng **cùng session/transaction** không?
- Unique index idempotency tồn tại thật không?
- Bất kỳ code path nào bật `upsert:true` không phù hợp?
- Có timeout/unknown commit result bị retry với ID mới không?

### Bước 4 — Đối soát dữ liệu

- Chọn snapshot/điểm dừng writes thích hợp để so invariant.
- Nhóm orders theo SKU/tenant/status.
- Kiểm tra event/stock movements/returns/restocks.
- Phân biệt pending transaction/CDC lag với dữ liệu đã commit.
- Xác nhận downstream payment/fulfillment trước khi bù stock.

### Bước 5 — Khôi phục an toàn

- Chỉ tạo **compensating records/adjustments** đã được nghiệp vụ phê duyệt.
- Không xóa đơn đã thanh toán chỉ để “số lượng khớp”.
- Dùng transaction và idempotency cho bước bù trừ.
- Thêm integration tests tái hiện bug trước rollout.
- Theo dõi invariant violations và alert sau deploy.

## 61. Bài tập và đáp án

### Bài 1. Lost update

Tồn kho 3. Hai threads cùng đọc 3 rồi cùng `$set:{available:2}`. Bao nhiêu hàng thực sự được phản ánh là đã trừ?

**Đáp án:** Có thể chỉ trừ 1 trên document, dù cả hai threads tưởng đã bán 1. Đây là lost update.

### Bài 2. Atomic update

Viết lệnh MongoDB giảm 2 đơn vị chỉ khi còn ít nhất 2.

**Đáp án:**

```javascript
db.inventory.updateOne(
  { _id: "SKU-A", available: { $gte: 2 } },
  { $inc: { available: -2 } }
);
```

### Bài 3. Hết hàng

`matchedCount=0` với filter `{_id:sku,available:{$gte:qty}}` nghĩa chắc chắn SKU không tồn tại?

**Đáp án:** Không. Có thể SKU có tồn tại nhưng thiếu hàng. Cần xử lý theo business policy.

### Bài 4. Giảm kho rồi tạo order

Tồn kho giảm thành công, nhưng insert order lỗi. Invariant nào sai?

**Đáp án:** Tồn kho giảm mà không có reservation/order tương ứng. Cần multi-document transaction hoặc workflow bù trừ có kiểm soát.

### Bài 5. Tạo order rồi giảm kho

Insert order thành công, decrement kho thất bại. Có thể trả 201 Created bình thường không?

**Đáp án:** Không nếu trạng thái đơn yêu cầu đã được giữ hàng. Phải abort/đổi trạng thái theo business workflow, không trả thành công sai.

### Bài 6. 20 requests

Stock=5, 20 requests khác nhau, qty=1. Với transaction + unique index đúng, cuối cùng kỳ vọng?

**Đáp án:** 5 đơn RESERVED, 15 yêu cầu hết hàng và stock=0, nếu tất cả attempts được xử lý/settle theo policy.

### Bài 7. Unique SKU

Có nên tạo unique index `orders.sku`?

**Đáp án:** Không, một SKU có thể nằm trong nhiều orders. Unique idempotency key phù hợp hơn.

### Bài 8. Idempotency

Hai HTTP calls cùng tenant/requestId/sku/quantity. Sau hai calls stock bị trừ hai lần. Đây là đúng?

**Đáp án:** Không. Cùng logical request phải tạo tối đa một order và trừ stock một lần.

### Bài 9. Payload khác

Cùng requestId nhưng lần sau quantity=10 thay vì 1. Nên upsert ghi đè quantity?

**Đáp án:** Không. Trả idempotency conflict theo contract.

### Bài 10. Unique index

Ứng dụng chạy `existsByRequestId` rồi insert, chưa có unique index. Nhiều clients có thể tạo duplicate không?

**Đáp án:** Có vì race giữa check và insert. Cần database unique constraint.

### Bài 11. Session

Trong transaction, insert order dùng `session`, nhưng update inventory bỏ session. Có bảo đảm atomicity không?

**Đáp án:** Không. Operation không dùng session phù hợp có thể nằm ngoài transaction.

### Bài 12. Transaction bị lỗi giữa chừng

Insert order thành công trong transaction, sau đó throw exception trước update stock. Order có được commit không?

**Đáp án:** Không, nếu transaction được abort đúng. Test xác nhận order không tồn tại trong committed state.

### Bài 13. Write conflict

Hai transactions cùng update một inventory document. Một transaction nhận transient write conflict. Có nghĩa đã oversell chưa?

**Đáp án:** Không. Đó là tín hiệu concurrency cần retry/abort theo semantics; invariant cuối mới quyết định đúng sai.

### Bài 14. Retry side effect

Code gọi payment gateway trong `withTransaction` callback. Có rủi ro gì?

**Đáp án:** Callback có thể chạy lại do retry, trong khi payment không rollback theo MongoDB transaction. Có thể charge trùng.

### Bài 15. Unknown commit

Client mất kết nối ngay sau gửi commit. Có nên tạo requestId mới và gọi lại?

**Đáp án:** Không. Transaction có thể đã commit; dùng stable idempotency key và reconcile.

### Bài 16. Out-of-stock exception

Khi stock update matchedCount=0, service bắt exception và vẫn return order ID từ transaction. Có đúng?

**Đáp án:** Không. Phải abort transaction/không commit order nếu nó được trả thành RESERVED.

### Bài 17. Quantity âm

Request quantity=-2 được gửi tới `$inc:{available: -quantity}`. Điều gì sai?

**Đáp án:** Trừ một số âm có thể tăng stock và phá invariant. Validate `quantity > 0` trước thao tác.

### Bài 18. Upsert inventory

Vì sao không bật `upsert:true` cho conditional decrement?

**Đáp án:** Không match có thể nghĩa thiếu hàng; upsert sẽ cố tạo inventory record, có thể gây duplicate key hoặc giá trị sai.

### Bài 19. Transaction vs `@Version`

`@Version` trên inventory có tự rollback order insert trong collection khác không?

**Đáp án:** Không. Nó quản lý optimistic locking theo entity save paths, không thay multi-document transaction.

### Bài 20. Multi-SKU

Order gồm SKU-A qty1 và SKU-B qty2. A đủ hàng, B thiếu. Với transaction đúng, stock A có giảm không?

**Đáp án:** Không có thay đổi được commit cho cả hai; toàn transaction phải abort.

### Bài 21. Cancellation

Hai requests cùng cancel order qty2. Tồn kho được cộng 4. Bug gì?

**Đáp án:** Release không idempotent. Cần conditional status transition và stock increment cùng transaction, cộng đúng một lần.

### Bài 22. Test concurrency

JUnit tạo hai entity copies nhưng không dùng MongoDB thật. Đã chứng minh unique index và transaction behavior chưa?

**Đáp án:** Chưa. Cần integration test trên MongoDB replica set/sharded deployment hỗ trợ transaction.

### Bài 23. Barrier

Tại sao dùng `CountDownLatch` khi test 40 requests?

**Đáp án:** Cho workers bắt đầu gần cùng thời điểm, làm tăng khả năng tạo race và contention để quan sát invariant.

### Bài 24. Assertions

Test chỉ assert stock không âm. Có đủ không?

**Đáp án:** Không. Cần count/orders sum, uniqueness và quan hệ stock–orders.

### Bài 25. Reconciliation

Stock ban đầu 10, final 4, có ba orders RESERVED qty2 mỗi đơn. Invariant đúng?

**Đáp án:** Đúng trong lab không có nhập/huỷ: `4 + 3*2 = 10`.

### Bài 26. Reconciliation sai

Stock ban đầu 10, final 2, có ba orders RESERVED qty2. Vấn đề?

**Đáp án:** `2 + 6 = 8`, thiếu 2 đơn vị không được giải thích. Cần xem stock mutations, order states, failed writes/compensation.

### Bài 27. Một hot SKU

Tăng threads gấp 10 khiến write conflict và latency tăng. Có nghĩa MongoDB đã làm sai atomicity không?

**Đáp án:** Không. Có thể là contention trên cùng inventory document. Cần kiểm tra final invariant, throughput và thiết kế backpressure.

### Bài 28. Tenant scope

Hai tenants dùng cùng requestId. Unique index chỉ trên requestId có phù hợp mọi mô hình?

**Đáp án:** Không nếu key chỉ cần unique trong tenant. Dùng compound unique theo `tenantId,requestId` và kiểm tra tenant authorization.

### Bài 29. Replica set

Test transaction trên standalone bị lỗi “transaction numbers only allowed ...”. Có thể bỏ transaction rồi tiếp tục assert cross-document atomicity?

**Đáp án:** Không. Cần môi trường transaction-capable.

### Bài 30. Cleanup

CI có nhiều jobs cùng dùng database lab. Có nên `db.dropDatabase()` sau mỗi test?

**Đáp án:** Không. Dùng tenant/SKU/testRunId riêng và cleanup đúng scope sau khi threads hoàn tất.

## 62. Checklist triển khai bài thực hành

### Môi trường

- [ ] MongoDB lab là replica set/sharded deployment có hỗ trợ transaction.
- [ ] Client dùng URI và quyền đúng, không log credentials.
- [ ] Orders có unique index trên scope idempotency đã duyệt.
- [ ] Inventory có numeric `available` và SKU identity nhất quán.
- [ ] Fixture tách biệt production, mỗi test có SKU/tenant riêng.

### Đúng đắn dữ liệu

- [ ] Quantity được validate là số nguyên dương.
- [ ] Decrement dùng atomic `$inc` với `available >= quantity`.
- [ ] Không dùng read–modify–write thiếu CAS.
- [ ] Inventory decrement không dùng `upsert:true`.
- [ ] Insert order và decrement inventory cùng session/transaction.
- [ ] MatchedCount=0 làm abort, không commit order RESERVED.
- [ ] Unique request ID chống duplicate order.
- [ ] Same key/different payload được báo conflict.
- [ ] Cancel/release stock chỉ thực hiện một lần.

### Retry và giao dịch

- [ ] Transaction callback ngắn và không chứa external side effects.
- [ ] Driver retry semantics/labels được hiểu và có budget.
- [ ] Unknown commit không được mặc định là thất bại chắc chắn.
- [ ] Retry giữ nguyên idempotency key.
- [ ] Outbox/downstream có idempotency nếu phát event/payment.
- [ ] Write concern/read concern đáp ứng business RPO/consistency.

### Kiểm thử

- [ ] Có baseline single-request và hết hàng.
- [ ] Có test lost update cố tình sai trên lab để đối chứng.
- [ ] Có test concurrency requests khác nhau khi stock hạn chế.
- [ ] Có test duplicate requestId và payload khác nhau.
- [ ] Có fault injection sau từng write trong transaction.
- [ ] Có test order nhiều SKUs và cancellation.
- [ ] Có assert final stock + summed reservations = initial.
- [ ] Unexpected MongoDB errors làm test fail/unknown, không gán thành OOS.
- [ ] Test cleanup không xóa dữ liệu của jobs khác.

### Quan sát và vận hành

- [ ] Theo dõi conflicts, duplicate keys, transaction retry và p99.
- [ ] Có dashboard stock anomalies và reconciliation jobs.
- [ ] Biết giới hạn hot-document throughput và load shedding.
- [ ] Có runbook xử lý overselling, timeout và unknown outcomes.
- [ ] Không thực hiện compensation khi chưa đối soát payment/fulfillment.

## 63. Tổng kết

Thử nghiệm cạnh tranh khi **cập nhật tồn kho và tạo đơn hàng** là một cách thực hành nhiều khái niệm cốt lõi của MongoDB cùng lúc: atomic write trên một document, filter có điều kiện, unique index, multi-document transactions, session, retryable errors và idempotency.

Nếu ứng dụng đọc số tồn kho rồi `$set` kết quả tính toán từ Java, các requests đồng thời có thể gây **lost update**. Thay bằng **`updateOne({_id,available:{$gte:qty}},{$inc:{available:-qty}})`** giúp tránh overselling trên một inventory document. Nhưng khi còn phải **tạo order ở collection khác**, hai writes riêng lẻ vẫn có thể tạo trạng thái dở dang. Multi-document transaction giúp hai thao tác **cùng commit hoặc cùng abort**, miễn cả hai sử dụng cùng session và business conditions được kiểm tra.

Transaction **không thay thế** unique idempotency key: cùng request được retry phải tạo tối đa một order và trừ tồn kho một lần. Transaction cũng không thay thế backpressure, domain validation hay bảo vệ external payment/email khỏi chạy lặp. Khi nhiều transactions tranh cùng SKU, write conflicts và retries là tình huống cần xử lý, không tự động là dấu hiệu MongoDB làm sai atomicity.

Tiêu chí hoàn thành lab không phải “40 calls đều không ném exception”. Tiêu chí là **sau khi các operations hoàn tất, không có stock âm, không có duplicate business orders, số tồn kho giảm khớp lượng active reservations, và không có partial commit giữa order và inventory**. Từ đó, đội phát triển có thể áp dụng cùng phương pháp kiểm thử cho ví điện tử, giới hạn vé, quota, giữ phòng, phân bổ tài nguyên và nhiều workflow cạnh tranh khác.

### Tài liệu tham khảo chính thức

- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Manual — updateOne](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/)
- [MongoDB Manual — $inc](https://www.mongodb.com/docs/manual/reference/operator/update/inc/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — findAndModify](https://www.mongodb.com/docs/manual/reference/method/db.collection.findAndModify/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [Spring Data MongoDB Reference — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
