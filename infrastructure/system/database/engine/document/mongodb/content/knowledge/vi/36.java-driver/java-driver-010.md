# ClientSession, giao dịch và hành vi retry của MongoDB Java Driver

> **Module:** Database Engine Document MongoDB  
> **Chương:** Java Driver  
> **Bài học:** ClientSession, giao dịch và hành vi retry của driver

## 1. Bài toán: một thao tác thất bại thì điều gì đã xảy ra?

Một ứng dụng Java bán hàng xử lý yêu cầu đặt mua một sản phẩm. Trong một lần gọi API, service cần:

1. Kiểm tra và trừ số lượng còn trong kho.
2. Tạo document đơn hàng.
3. Ghi một sự kiện `OrderPlaced` cho hệ thống xử lý bất đồng bộ.
4. Trả mã đơn hàng cho client.

Nếu ghi tồn kho thành công nhưng ghi đơn hàng thất bại, dữ liệu không nhất quán. Nếu giao dịch commit thành công nhưng kết nối mất đúng lúc server trả lời, client có thể nhìn thấy **lỗi dù dữ liệu thực tế đã commit**. Nếu driver chạy lại toàn bộ callback mà callback đã gọi cổng thanh toán bên ngoài, người dùng có thể bị tính tiền hai lần.

Ba câu hỏi này đòi hỏi phân biệt:

- **Session:** Ngữ cảnh các thao tác giữa client và server, hỗ trợ causal consistency và transaction.
- **Transaction:** Nhóm database operations có một kết quả commit/abort.
- **Retry:** Cách driver thực hiện lại một thao tác hoặc toàn transaction khi gặp lỗi có thể hồi phục.
- **Idempotency:** Cách ứng dụng bảo đảm cùng một yêu cầu nghiệp vụ không tạo tác dụng không mong muốn khi gọi lại.
- **Unknown outcome:** Trạng thái mà client không biết commit đã thành công hay chưa.

```text
HTTP request: Place Order
        │
        ▼
MongoDB Java Sync Driver
        │
        ├── MongoClient (thread-safe, connection pools)
        │
        └── ClientSession (gắn với một client, dùng tuần tự)
                 │
                 ├── Transaction attempt 1
                 │      update inventory
                 │      insert order
                 │      insert outbox event
                 │      commit / abort
                 │
                 ├── Retry transaction body?
                 │      chỉ khi lỗi phù hợp
                 │
                 └── Retry commit?
                        nếu outcome chưa rõ
                        không đồng nghĩa chạy lại business logic
        │
        ▼
Application trả kết quả đã được xác minh
```

**Mục tiêu:** Viết code Java chính xác về transaction và retry, tránh nhầm driver retry với exactly-once business processing, hiểu điều kiện hỗ trợ, cách xử lý lỗi, giới hạn tài nguyên và kiểm thử failover.

---

## 2. Bản đồ khái niệm: session, transaction và retry

| Khái niệm | Vai trò | Không nên hiểu thành |
|---|---|---|
| `MongoClient` | Entry point, topology discovery, connection pooling | Một kết nối TCP duy nhất |
| `ClientSession` | Logical session và ngữ cảnh liên tiếp cho các operations | Một database transaction luôn chạy từ lúc session mở |
| Implicit session | Driver quản lý session cho những lệnh phù hợp | API có transaction nhiều lệnh mặc định |
| Explicit session | Ứng dụng tạo qua `startSession()` | Tự nhiên có ACID multi-document |
| Causal consistency | Duy trì thứ tự quan sát theo quan hệ nhân quả trong điều kiện phù hợp | Snapshot của mọi dữ liệu hoặc full linearizability |
| Snapshot session | Hỗ trợ nhiều snapshot reads nhất quán theo một mốc trong điều kiện hỗ trợ | Một transaction ghi |
| Multi-document transaction | Nhóm operations cùng commit/abort | Cơ chế atomic đối với payment/email bên ngoài MongoDB |
| Retryable write | Driver có thể retry một lệnh ghi đủ điều kiện | Retry mọi updateMany/deleteMany |
| Retryable read | Driver có thể retry một lệnh đọc đủ điều kiện | Retry cả cursor đã trả nhiều batches |
| `withTransaction()` | Callback API giúp retry transaction/commit theo error labels | Bảo đảm callback chạy đúng một lần |
| Idempotency key | Ràng buộc yêu cầu nghiệp vụ không tạo kết quả trùng | Chức năng driver tạo tự động |
| Outbox pattern | Ghi ý định phát sự kiện trong cùng transaction | Gửi event ra Kafka chính xác một lần tự động |

### 2.1. Một session không đồng nghĩa một transaction

~~~java
try (ClientSession session = client.startSession()) {
    // Các thao tác gắn session nhưng CHƯA ở transaction.
    collection.find(session).first();

    // Chỉ khi startTransaction được gọi mới bắt đầu transaction.
    session.startTransaction();

    // ...
}
~~~

Có thể dùng session để giữ ngữ cảnh causal consistency mà không cần transaction. Ngược lại, transaction luôn gắn với một client session.

### 2.2. Session không phải socket hoặc Java thread

Driver có thể sử dụng các kết nối vật lý khác nhau theo topology và pooling. Logical session có session ID, server lưu thông tin phù hợp. Không đồng nhất session với một TCP socket hoặc một thread dùng mãi mãi.

### 2.3. Transaction không phải giải pháp đầu tiên cho mọi thao tác

MongoDB bảo đảm **atomicity ở cấp một document**. Ví dụ tăng bộ đếm hoặc cập nhật hai trường trong **cùng một document** thường không cần multi-document transaction:

~~~javascript
db.inventory.updateOne(
  { _id: "SKU-100", available: { $gte: 2 } },
  { $inc: { available: -2 }, $set: { updatedBy: "checkout" } }
);
~~~

Một update trên một document có tính atomic. Dùng transaction nhiều document chỉ khi cần bất biến vượt document/collection.

---

## 3. Điều kiện tiên quyết để dùng transactions

### 3.1. Server topology

Multi-document transactions được hỗ trợ trên các topology và phiên bản MongoDB phù hợp:

- **Replica set:** hỗ trợ từ MongoDB 4.0.
- **Sharded cluster:** hỗ trợ distributed transactions từ MongoDB 4.2.
- **Standalone `mongod`:** không hỗ trợ multi-document transactions như replica set.

Một **single-node replica set** là cách thực hành transactions trong local lab; nó vẫn là replica set, không phải standalone.

### 3.2. Driver và server versions

Cần MongoDB Java Sync Driver và server tương thích với sessions/transactions. Phiên bản có thể ảnh hưởng:

- Transaction options.
- Snapshot session behavior.
- Retryable reads/writes.
- Error labels.
- Command monitoring fields.
- Timeouts và sharded transaction limitations.

Đừng chỉ thấy method `startTransaction()` trong driver rồi cho rằng mọi server MongoDB đều hỗ trợ.

### 3.3. Feature Compatibility Version

FCV ảnh hưởng việc bật các tính năng tùy MongoDB Server version. Với cluster nâng cấp/chuyển major versions, cần kiểm tra FCV, command support và transaction restrictions trong target release.

Không chỉnh FCV chỉ để “sửa một transaction lỗi” khi chưa có runbook nâng cấp.

### 3.4. Quyền truy cập

Application principal phải được cấp quyền đọc/ghi trên collections tương ứng. Session/transaction **không bỏ qua RBAC**.

Ví dụ tài khoản có role `readWrite` trên database nghiệp vụ vẫn không được cấp quyền trên một database khác nếu không có role phù hợp.

### 3.5. Data model và vận hành

Cần xét:

- Bất biến nghiệp vụ nào bắt buộc atomic xuyên nhiều documents?
- Số documents/collections/shards liên quan?
- Transaction kéo dài bao lâu?
- Tần suất write conflicts?
- Có external API call trong callback không?
- Có idempotency key/outbox không?
- Độ trễ p95/p99 và tải storage?
- Có đủ monitoring và rollback?

---

## 4. Cài MongoDB Java Sync Driver

Ví dụ Maven với dependency được quản lý theo phiên bản phù hợp với project:

~~~xml
<dependency>
  <groupId>org.mongodb</groupId>
  <artifactId>mongodb-driver-sync</artifactId>
  <version>5.5.0</version>
</dependency>
~~~

Số phiên bản trên là **ví dụ minh họa** chứ không phải khẳng định bản mới nhất ở mọi thời điểm. Nên dùng phiên bản được tổ chức hỗ trợ, đối chiếu release notes và bảng tương thích với MongoDB Server.

Gradle tương đương:

~~~groovy
dependencies {
    implementation "org.mongodb:mongodb-driver-sync:5.5.0"
}
~~~

Dùng dependency management của project thực tế; tránh để các thư viện BSON/driver-core khác major versions trong cùng classpath.

### 4.1. Các lớp chính

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import com.mongodb.TransactionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.ReadPreference;
import org.bson.Document;
~~~

### 4.2. Kết nối qua environment

~~~java
String uri = System.getenv("MONGODB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("Missing MONGODB_URI");
}

try (MongoClient client = MongoClients.create(uri)) {
    client.getDatabase("admin")
          .runCommand(new Document("ping", 1));
}
~~~

Ví dụ URI cho local single-node replica set:

~~~text
mongodb://127.0.0.1:27017/?replicaSet=rs0&retryWrites=true&retryReads=true
~~~

Trong production, cấu hình seed list/SRV, TLS, authSource, pool sizing và timeouts theo topology thật. Không hardcode username/password.

---

## 5. Vòng đời của ClientSession

### 5.1. Tạo session explicit

~~~java
try (MongoClient client = MongoClients.create(uri);
     ClientSession session = client.startSession()) {

    MongoDatabase db = client.getDatabase("commerce");
    MongoCollection<Document> orders =
            db.getCollection("orders");

    Document first = orders
            .find(session)
            .first();

    System.out.println(first);
}
~~~

Phương thức `startSession()` trả về một đối tượng session; `try-with-resources` bảo đảm `close()` khi thoát block.

### 5.2. Phải truyền session cho từng operation

Đây là lỗi rất phổ biến:

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    // SAI: không truyền session cho lệnh.
    orders.insertOne(new Document("_id", "O-1"));

    session.commitTransaction();
}
~~~

Lệnh `orders.insertOne(...)` ở trên có thể chạy **ngoài transaction**, vì API không nhận `session`.

Đúng:

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    orders.insertOne(
            session,
            new Document("_id", "O-1"));

    session.commitTransaction();
}
~~~

**Quy tắc:** Mọi lệnh MongoDB thuộc transaction phải nhận cùng `ClientSession`, bao gồm reads, writes và các commands được phép.

### 5.3. Explicit session có thể có nhiều transactions tuần tự

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();
    // Operations for transaction A.
    session.commitTransaction();

    session.startTransaction();
    // Operations for transaction B.
    session.abortTransaction();
}
~~~

Không được chạy hai transactions đồng thời trên cùng session. Một transaction đã commit/abort trước khi bắt đầu transaction khác.

### 5.4. Không chia sẻ ClientSession giữa threads

`MongoClient` được thiết kế thread-safe và nên tái sử dụng. Nhưng `ClientSession` **không thread-safe**; không dùng một session đồng thời từ hai Java threads.

Sai:

~~~java
ClientSession shared = client.startSession();

executor.submit(() -> collection.insertOne(
        shared, new Document("n", 1)));
executor.submit(() -> collection.insertOne(
        shared, new Document("n", 2)));
~~~

Hành vi không được bảo đảm, đặc biệt khi nằm trong một transaction.

Đúng hơn:

- Mỗi request/workflow sở hữu session riêng.
- Các lệnh trong transaction chạy tuần tự.
- Không dùng `parallelStream()` hoặc `CompletableFuture` trên cùng session.

### 5.5. Đóng session

Dùng:

~~~java
try (ClientSession session = client.startSession()) {
    // ...
}
~~~

Không giữ session trong singleton, cache user session vô hạn hoặc quên close. Long-lived sessions/transactions có thể gây resource pressure; session là tài nguyên cần quản lý vòng đời.

### 5.6. Session thuộc MongoClient tạo ra nó

Không truyền session từ `clientA.startSession()` cho collection lấy từ `clientB.getDatabase(...)`. Session gắn với client và topology context được tạo.

---

## 6. Implicit và explicit sessions

### 6.1. Implicit session

Trong nhiều thao tác bình thường:

~~~java
orders.find(eq("status", "PENDING")).first();
orders.insertOne(new Document("_id", "O-2"));
~~~

Driver có thể quản lý implicit sessions cần thiết cho retryable reads/writes và protocol features.

**Không cần gọi `startSession()` cho mọi CRUD** chỉ để driver dùng retryable operations.

### 6.2. Explicit session

Khi cần:

- Multi-document transaction.
- Causal consistency xuyên một chuỗi operations.
- Snapshot session theo tính năng được hỗ trợ.
- Kiểm soát transaction scope/options.

thì dùng explicit `ClientSession`.

### 6.3. Session ID và transaction number

Trong MongoDB wire protocol/diagnostics có các khái niệm:

- `lsid`: logical session identifier.
- `txnNumber`: transaction/retryable write numbering.
- `autocommit: false`: dấu hiệu operation thuộc multi-document transaction trên wire protocol.
- `startTransaction`: marker cho operation bắt đầu transaction trên server theo protocol.

Các fields này do driver/server quản lý. **Đừng tự đặt `lsid`/`txnNumber` trong Java application BSON commands** để tạo transaction hoặc retry cơ chế nội bộ.

---

## 7. Causal consistency: session không có transaction vẫn hữu ích

### 7.1. Bài toán

Một service vừa ghi user profile rồi lập tức đọc ở một secondary còn replication lag. Nếu các operations không ràng buộc quan hệ nhân quả và read concern thích hợp, read có thể nhìn thấy dữ liệu cũ.

### 7.2. Causal consistency làm gì?

Một causal-consistent session có thể dùng các cơ chế như operation time/cluster time để duy trì một số guarantee, ví dụ:

- Read your own writes.
- Monotonic reads.
- Monotonic writes.
- Writes follow reads.

Các guarantee phụ thuộc điều kiện server/topology và sự phối hợp read/write concern. Theo MongoDB docs, để có đầy đủ guarantees causal consistency cần dùng **majority read concern và majority write concern** trong bối cảnh phù hợp.

### 7.3. Cấu hình explicit causal consistency

~~~java
import com.mongodb.ClientSessionOptions;

ClientSessionOptions options =
        ClientSessionOptions.builder()
                .causallyConsistent(true)
                .build();

try (ClientSession session =
             client.startSession(options)) {

    collection.withWriteConcern(WriteConcern.MAJORITY)
              .insertOne(
                      session,
                      new Document("_id", "C-100")
                              .append("status", "ACTIVE"));

    Document doc = collection
            .withReadConcern(ReadConcern.MAJORITY)
            .find(session, eq("_id", "C-100"))
            .first();

    System.out.println(doc);
}
~~~

Ví dụ cần server/topology hỗ trợ. Không phải thao tác nào cũng yêu cầu transaction; đây là **hai operations trong cùng causal session**.

### 7.4. Causal session không atomic nhiều documents

Nếu code:

~~~java
inventory.updateOne(session, ...);
orders.insertOne(session, ...);
~~~

mà không gọi `session.startTransaction()`, hai lệnh **không tạo thành multi-document transaction**, dù session có causal consistency.

### 7.5. Snapshot session là khái niệm khác

Một số driver/server versions hỗ trợ snapshot sessions cho point-in-time reads ngoài transaction.

Ví dụ ý tưởng:

~~~java
ClientSessionOptions options =
        ClientSessionOptions.builder()
                .snapshot(true)
                .build();

try (ClientSession session =
             client.startSession(options)) {
    // Các snapshot reads được phép theo driver/server support.
}
~~~

Snapshot sessions và causal consistency có các ràng buộc riêng; không bật cả hai một cách tùy tiện. Snapshot session **không phải multi-document write transaction**.

---

## 8. ACID trong MongoDB transactions

### 8.1. Atomicity

Một transaction commit thành công thì các writes của transaction được commit cùng nhau theo guarantees của MongoDB. Nếu abort, những writes chưa commit trong transaction không trở thành committed changes.

### 8.2. Consistency

MongoDB giúp giữ atomicity/isolation, nhưng **business invariants vẫn do ứng dụng thiết kế**. Một transaction không tự ngăn nghiệp vụ bán hàng âm tồn kho nếu code bỏ qua điều kiện `available >= quantity`.

### 8.3. Isolation

MongoDB transactions dùng snapshot isolation với các ngữ nghĩa reads/writes phụ thuộc read concern và conflict detection. Không nên tuyên bố mọi transaction đều đáp ứng serializable isolation.

Hai transactions concurrent có thể gặp write conflict, snapshot stale reads hoặc một transaction bị abort.

### 8.4. Durability

Durability phụ thuộc write concern, replication và tình trạng deployment. Dùng `WriteConcern.MAJORITY` ở cấp transaction khi cần majority acknowledgment.

### 8.5. Phạm vi MongoDB

ACID transaction chỉ bao phủ những database operations tham gia cùng transaction. Nó không đưa:

- HTTP payment.
- Gửi email.
- Kafka publish ngoài DB.
- Ghi file vào object storage.
- Gọi hệ thống bên thứ ba.

vào cùng atomic commit của MongoDB.

Nếu nghiệp vụ cần phối hợp chúng, dùng outbox/saga/idempotency và quy trình reconciliation.

---

## 9. TransactionOptions: read concern, write concern và read preference

### 9.1. Cấu hình Java

~~~java
TransactionOptions txnOptions =
        TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();
~~~

### 9.2. Read concern

Các mức read concern liên quan:

- `local`.
- `majority`.
- `snapshot`, khi được hỗ trợ trong transaction.

`ReadConcern.SNAPSHOT` giúp đọc từ một snapshot nhất quán trong transaction theo semantics MongoDB. Các guarantee về snapshot đã majority-committed cần xem cùng write concern khi commit; không coi riêng chữ `snapshot` là bằng chứng dữ liệu an toàn tuyệt đối trước failover.

### 9.3. Write concern

Dùng `WriteConcern.MAJORITY` ở **transaction level**, không phải tùy tiện đặt write concern riêng cho mỗi operation trong transaction.

~~~java
TransactionOptions options =
        TransactionOptions.builder()
                .writeConcern(WriteConcern.MAJORITY)
                .build();
~~~

Write concern trên các writes *bên trong* transaction không nên được chỉ định riêng; write concern áp dụng trong quá trình commit theo quy tắc transaction.

### 9.4. Read preference

Các operations trong một multi-document transaction phải tuân theo yêu cầu routing đến **primary**. Cấu hình:

~~~java
.readPreference(ReadPreference.primary())
~~~

để rõ ràng. Không thiết kế transaction ghi đa document dựa vào read preference `secondaryPreferred`.

### 9.5. Các defaults

Nếu không truyền `TransactionOptions`, driver/server dùng defaults và có thể kế thừa từ client/session theo API. Vì vậy:

- Không giả định mọi transaction mặc định là majority + snapshot.
- Ghi rõ options cho workflow quan trọng.
- Đọc transaction options của driver version thực tế.
- Test behavior trong replica set với failover.

### 9.6. maxCommitTime

Nếu phiên bản Java Driver hỗ trợ:

~~~java
TransactionOptions options =
        TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .maxCommitTime(5, java.util.concurrent.TimeUnit.SECONDS)
                .build();
~~~

Đây là giới hạn liên quan commit operation. Nó **không đồng nghĩa transaction body sẽ tự kết thúc sau 5 giây** hoặc giải quyết mọi timeout end-to-end.

---

## 10. Chuẩn bị data model ví dụ: tồn kho, đơn hàng, outbox

Ba collections trong database `commerce_lab`:

```text
inventory
  _id: SKU-100
  available: 25
  reserved: 0

orders
  _id: order-...
  requestId: checkout-...
  sku: SKU-100
  quantity: 2
  status: CREATED

outbox
  _id: order-created:<orderId>
  type: OrderCreated
  payload: { orderId, sku, quantity }
  processed: false
~~~

### 10.1. Vì sao có requestId?

HTTP client có thể retry sau timeout. `requestId`/idempotency key giúp ứng dụng nhận biết cùng **một yêu cầu đặt hàng** thay vì tạo hai đơn.

### 10.2. Vì sao có outbox?

MongoDB transaction không commit trực tiếp message broker bên ngoài. Ta ghi **ý định phát event** trong cùng transaction với order/inventory. Một worker sau đó publish event, retry có kiểm soát và đánh dấu kết quả.

### 10.3. Khởi tạo dữ liệu trên lab

Trong `mongosh` kết nối tới một replica set lab:

~~~javascript
const lab = db.getSiblingDB("commerce_lab");

lab.inventory.insertOne({
  _id: "SKU-100",
  available: 25,
  reserved: 0,
  updatedAt: new Date()
});

lab.orders.createIndex(
  { requestId: 1 },
  { unique: true, name: "uq_order_request" }
);

lab.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_status_created" }
);

lab.outbox.createIndex(
  { processed: 1, createdAt: 1 },
  { name: "idx_outbox_pending" }
);

printjson(lab.inventory.findOne({ _id: "SKU-100" }));
~~~

Chỉ chạy khởi tạo trên **database lab trống**. Không dùng `dropDatabase()` trên production chỉ để làm lại bài.

### 10.4. Invariant nghiệp vụ

Nếu đặt quantity = 2:

- `inventory.available` phải giảm từ 25 xuống 23.
- Một document `orders` tương ứng được tạo.
- Một outbox event tương ứng được tạo.
- Nếu bất kỳ bước nào fail, toàn bộ transaction không được commit.

Kiểm soát tồn kho phải dùng conditional update để tránh bán âm khi nhiều transactions concurrent.

---

## 11. Manual transaction API: start, commit, abort

Cách viết tường minh để hiểu API:

~~~java
import com.mongodb.TransactionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.set;

public final class ManualTransactionDemo {

    static void markTwoDocuments(
            MongoClient client,
            MongoCollection<Document> orders,
            MongoCollection<Document> outbox) {

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();

        try (ClientSession session = client.startSession()) {
            session.startTransaction(options);

            try {
                orders.updateOne(
                        session,
                        eq("_id", "O-100"),
                        set("status", "CONFIRMED"));

                outbox.insertOne(
                        session,
                        new Document("_id", "confirmed:O-100")
                                .append("type", "OrderConfirmed"));
            } catch (RuntimeException bodyError) {
                try {
                    session.abortTransaction();
                } catch (RuntimeException abortError) {
                    bodyError.addSuppressed(abortError);
                }
                throw bodyError;
            }

            // Nếu commit gặp lỗi chưa rõ kết quả, KHÔNG
            // tự động kết luận dữ liệu đã rollback.
            session.commitTransaction();
        }
    }
}
~~~

### 11.1. Vì sao commit được tách khỏi catch của body?

Lỗi khi chạy transaction body thường cần abort (nếu transaction còn active). Nhưng lỗi **trên commit** có thể khiến client không biết commit đã thành công hay chưa.

Nếu catch mọi exception, gọi `abortTransaction()` và tuyên bố rollback thành công, ứng dụng có thể báo sai sau khi server đã commit.

### 11.2. Manual retry khó ở đâu?

Bạn phải phân biệt:

- Lỗi transient trước commit → có thể thử lại **toàn transaction**.
- Lỗi unknown commit outcome → thử lại **commit** với cùng transaction context, không lập tức chạy lại writes.
- Lỗi nghiệp vụ (hết hàng) → không nên retry vô hạn.
- Duplicate key → phải xem idempotency/business meaning.
- Lỗi không retryable → báo thất bại có thông tin phù hợp.

Viết đúng mọi nhánh tương đối phức tạp; vì vậy driver cung cấp `withTransaction()`.

---

## 12. withTransaction(): API nên ưu tiên cho phần lớn workflow

`ClientSession.withTransaction(...)` nhận một callback thực hiện transaction body và giúp áp dụng retry behavior được MongoDB driver hỗ trợ.

Ví dụ ngắn:

~~~java
try (ClientSession session = client.startSession()) {
    String orderId = session.withTransaction(() -> {
        orders.insertOne(
                session,
                new Document("_id", "O-101")
                        .append("status", "CREATED"));

        outbox.insertOne(
                session,
                new Document("_id", "created:O-101")
                        .append("type", "OrderCreated"));

        return "O-101";
    }, txnOptions);

    System.out.println("Committed order " + orderId);
}
~~~

### 12.1. Tại sao callback phải thuần về business side effects?

Driver **có thể chạy callback nhiều lần** nếu transaction nhận lỗi transient phù hợp.

Không đặt:

~~~java
session.withTransaction(() -> {
    chargeCreditCard();
    sendEmail();
    orders.insertOne(session, order);
    return orderId;
}, txnOptions);
~~~

Đó là anti-pattern nghiêm trọng. Payment/email không được rollback khi MongoDB transaction abort. Callback chạy lần hai có thể tính tiền hoặc gửi email hai lần.

### 12.2. Với transaction retry, điều gì được làm lại?

Khi driver retry toàn transaction do lỗi có label thích hợp:

- Transaction attempt cũ bị abort hoặc không commit.
- Callback có thể chạy lại từ đầu.
- Các writes của attempt đã abort không trở thành committed data.
- Side effects ngoài MongoDB **không tự rollback**.

### 12.3. Lỗi ở commit khác lỗi trong body

Nếu commit outcome không rõ, driver có thể **retry commit** cho cùng transaction theo error label, thay vì chạy lại callback ngay.

Tại sao? Vì transaction có thể đã commit trên server. Chạy lại callback có thể gây duplicate business operations hoặc conflict.

### 12.4. withTransaction không retry vô hạn

Driver có điều kiện và giới hạn thời gian retry. Khi retry không thể giải quyết hoặc lỗi không thuộc nhóm retryable, helper sẽ ném exception.

Ứng dụng phải có phương án xử lý lỗi cuối cùng, idempotency và reconciliation; không coi gọi `withTransaction()` là cam kết 100% success.

---

## 13. Ví dụ Java đầy đủ: đặt hàng và trừ tồn kho trong transaction

### 13.1. Mục tiêu

- Inventory chỉ giảm khi còn đủ hàng.
- Order và outbox event được ghi trong cùng transaction.
- Dùng một idempotency key cho mỗi yêu cầu.
- Không gửi HTTP/email/Kafka trong callback.
- Cho phép driver retry transaction theo cơ chế được hỗ trợ.

### 13.2. Service Java

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import java.time.Instant;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.inc;

public final class PlaceOrderService {

    private final MongoClient client;
    private final MongoCollection<Document> inventory;
    private final MongoCollection<Document> orders;
    private final MongoCollection<Document> outbox;

    private final TransactionOptions txnOptions =
            TransactionOptions.builder()
                    .readConcern(ReadConcern.SNAPSHOT)
                    .writeConcern(WriteConcern.MAJORITY)
                    .readPreference(ReadPreference.primary())
                    .build();

    public PlaceOrderService(MongoClient client) {
        this.client = client;
        MongoDatabase db = client.getDatabase("commerce_lab");
        this.inventory = db.getCollection("inventory");
        this.orders = db.getCollection("orders");
        this.outbox = db.getCollection("outbox");
    }

    public String placeOrder(
            String requestId,
            String sku,
            int quantity) {

        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("Missing requestId");
        }
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Invalid item");
        }

        // Deterministic identity for the same application request.
        final String orderId = "order:" + requestId;
        final String eventId = "event:" + requestId;

        try (ClientSession session = client.startSession()) {
            return session.withTransaction(() -> {
                UpdateResult reserved = inventory.updateOne(
                        session,
                        and(
                                eq("_id", sku),
                                gte("available", quantity)
                        ),
                        inc("available", -quantity)
                );

                if (reserved.getModifiedCount() != 1) {
                    throw new IllegalStateException(
                            "Insufficient inventory");
                }

                orders.insertOne(
                        session,
                        new Document("_id", orderId)
                                .append("requestId", requestId)
                                .append("sku", sku)
                                .append("quantity", quantity)
                                .append("status", "CREATED")
                                .append("createdAt",
                                        java.util.Date.from(
                                                Instant.now()))
                );

                outbox.insertOne(
                        session,
                        new Document("_id", eventId)
                                .append("type", "OrderCreated")
                                .append("orderId", orderId)
                                .append("processed", false)
                                .append("createdAt",
                                        java.util.Date.from(
                                                Instant.now()))
                );

                return orderId;
            }, txnOptions);
        }
    }
}
~~~

### 13.3. Ý nghĩa từng phần

1. `requestId` là idempotency identity được xác thực/gắn với đúng client/request ở tầng application.
2. `orderId` và `eventId` được tạo **ngoài callback** theo requestId; không sinh UUID mới trong mỗi attempt.
3. Conditional `updateOne` chỉ trừ hàng khi còn đủ tồn kho.
4. `modifiedCount==1` xác nhận có một inventory record được giảm; nếu không, ném lỗi nghiệp vụ.
5. Insert order và outbox đều truyền `session`.
6. `withTransaction` quyết định commit/abort/retry phù hợp theo driver semantics.
7. Không gọi external payment/email trong transaction callback.

### 13.4. Có vấn đề nào vẫn cần xử lý ở application?

Có. Một request có thể được gửi lại sau khi transaction đã commit:

- Lần thứ hai cố trừ tồn kho trước.
- Sau đó insert order trùng `_id` hoặc unique `requestId`.
- Transaction lần hai abort, nên tồn kho không bị trừ lần nữa nếu transaction abort đúng.
- Nhưng service sẽ trả duplicate key error thay vì trả lại order đã tồn tại.

Vì vậy production API cần **idempotency lookup/reconciliation**: trước khi bắt đầu có thể kiểm tra order theo requestId, xử lý các race bằng unique index và sau khi gặp lỗi trùng/unknown outcome phải query lại trạng thái đã commit.

Không coi ví dụ code là một idempotent HTTP endpoint hoàn chỉnh.

### 13.5. Đừng bắt mọi lỗi rồi trả success

Nếu `withTransaction()` ném exception, application phải đánh giá:

- Có phải business validation fail?
- Có phải duplicate request đã có order?
- Có thể transaction đã commit nhưng client không nhận response?
- Có nên trả HTTP 409/503/202 hoặc một trạng thái đang xác minh?

Không trả “order success” nếu chưa có bằng chứng phù hợp.

---

## 14. Đọc lại kết quả theo idempotency key

Một service có thể thiết kế trạng thái:

```text
requestId = checkout-2026-abc

Nếu order chưa tồn tại:
    thử transaction tạo order

Nếu order đã tồn tại:
    trả lại chính order đó (sau xác minh request payload)

Nếu commit outcome không rõ:
    query order theo requestId với consistency phù hợp
    quyết định success/pending/retry theo policy
~~~

### 14.1. Unique index

~~~javascript
db.getSiblingDB("commerce_lab").orders.createIndex(
  { requestId: 1 },
  { unique: true, name: "uq_request" }
);
~~~

Không tạo trùng index nếu đã có. Index unique là cơ chế database ngăn hai orders có cùng requestId.

### 14.2. Idempotency key cần gắn với payload

Không chỉ dùng một chuỗi tùy ý làm requestId. Nếu client gửi cùng key nhưng khác `sku` hoặc `quantity`, ứng dụng phải từ chối như conflicting request.

Ví dụ record có:

~~~javascript
{
  requestId: "checkout-2026-abc",
  requestHash: "HASH_OF_CANONICAL_BUSINESS_INPUT",
  orderId: "order:checkout-2026-abc",
  status: "CREATED"
}
~~~

Hash là minh họa; không gửi raw PII vào key/metrics/logs. Thiết kế TTL/retention của idempotency records theo yêu cầu nghiệp vụ.

### 14.3. Reconciliation query không phải blind retry

Khi commit outcome không rõ, một read phù hợp giúp kiểm tra đã có kết quả durable theo business invariant hay chưa. Nhưng:

- Read từ secondary lag có thể không thấy dữ liệu mới.
- Rollback/failover có thể ảnh hưởng kết quả nếu write concern không đủ.
- Trạng thái outbox/order/inventory cần xét cùng nhau.
- Nếu chưa xác định chắc chắn, trả pending và để background reconciliation thay vì tự động trừ tồn kho lần nữa.

---

## 15. Retry của transaction: hai nhánh quan trọng

MongoDB drivers sử dụng **error labels** để xác định hướng xử lý một số lỗi transaction.

### 15.1. TransientTransactionError

Label:

~~~text
TransientTransactionError
~~~

thường báo tình huống transaction không thể hoàn tất vì lỗi transient trong giai đoạn thực thi.

Ý tưởng xử lý:

```text
Transaction body attempt
      │
      ├── success → commit
      │
      └── error labeled TransientTransactionError
              │
              └── retry WHOLE transaction callback
                     với transaction attempt mới
~~~

Khi callback chạy lại, **không thực hiện side effects bên ngoài MongoDB**.

### 15.2. UnknownTransactionCommitResult

Label:

~~~text
UnknownTransactionCommitResult
~~~

nghĩa là client **không xác định được** kết quả commit trong tình huống cụ thể.

Ý tưởng:

```text
Transaction body completed
          │
          ▼
commitTransaction
          │
          ├── success → committed
          │
          └── UnknownTransactionCommitResult
                   │
                   └── retry COMMIT for same transaction
                       không tự chạy lại body
~~~

**Không đồng nghĩa transaction đã abort** và cũng không đồng nghĩa transaction đã commit; đó là trạng thái kết quả chưa rõ từ góc nhìn client.

### 15.3. Vì sao hai nhánh khác nhau?

Một transaction lỗi transient trước commit có thể phải làm lại các bước DB trong một attempt mới. Nhưng nếu server đã commit thành công rồi connection mất lúc trả lời, chạy lại body sẽ tạo thêm thao tác không cần thiết.

### 15.4. Các lỗi không thuộc hai nhãn

Không phải mọi lỗi đều retry:

- Validation error.
- Unauthorized.
- Duplicate key do business invariant.
- Illegal operation trong transaction.
- Unsupported server/topology.
- Quá giới hạn thời gian/tài nguyên.
- Lỗi ứng dụng như `IllegalStateException("Insufficient inventory")`.

Có lỗi có nhãn khác và hành vi phụ thuộc phiên bản; không tự thêm retry cho mọi exception.

---

## 16. Đọc error labels trong Java

MongoDB Java Driver cung cấp `MongoException.hasErrorLabel(...)`.

~~~java
import com.mongodb.MongoException;

try {
    doTransaction();
} catch (MongoException e) {
    boolean transientTxn =
            e.hasErrorLabel("TransientTransactionError");

    boolean unknownCommit =
            e.hasErrorLabel("UnknownTransactionCommitResult");

    System.err.println(
            "transientTxn=" + transientTxn +
            ", unknownCommit=" + unknownCommit +
            ", errorCode=" + e.getCode());

    throw e;
}
~~~

Ví dụ chỉ minh họa cách đọc labels. Không nên tự retry toàn bộ transaction trong `catch` nếu `doTransaction()` đã dùng `withTransaction()` và đã thực hiện retries theo spec.

### 16.1. Đừng suy từ error message string

Sai:

~~~java
if (e.getMessage().contains("not primary")) {
    retryEverything();
}
~~~

Message thay đổi theo server/driver versions, không phải API contract tốt để điều khiển retry.

Nên dùng:

- Error labels.
- Error codes/categories được hỗ trợ.
- Retry helpers của driver.
- Documented exception types.
- Business idempotency rules.

### 16.2. Error labels không thay business semantics

Ngay cả khi label báo retryable, callback có external side effects vẫn có rủi ro. Retry đúng ở driver layer **không tự tạo exactly-once end-to-end processing**.

---

## 17. Retryable writes: tự retry một lệnh ghi khi đủ điều kiện

### 17.1. Retryable writes là gì?

Khi `retryWrites=true` và topology/command đáp ứng điều kiện, MongoDB Java Driver có thể tự retry một số **single-statement write operations** sau lỗi network/failover có thể hồi phục.

Ví dụ:

~~~java
orders.insertOne(
        new Document("_id", "O-200")
                .append("status", "CREATED"));
~~~

Nếu response bị mất sau write, driver dùng session/transaction numbering protocol để tránh thực thi lại không đúng theo semantics được hỗ trợ.

### 17.2. Cấu hình URI

~~~text
mongodb://mongo1.example.internal:27017,mongo2.example.internal:27017,mongo3.example.internal:27017/?replicaSet=rs0&retryWrites=true
~~~

Trên các MongoDB Java Driver versions hiện đại, retryable writes thường **được bật mặc định** khi môi trường hỗ trợ. Tuy nhiên, kiểm tra connection string, driver version và provider thay vì suy đoán.

### 17.3. Các operation phù hợp phổ biến

Những ví dụ thường thuộc nhóm retryable write khi điều kiện được đáp ứng:

- `insertOne()`.
- `updateOne()`.
- `replaceOne()`.
- `deleteOne()`.
- `findOneAndUpdate()`.
- `findOneAndReplace()`.
- `findOneAndDelete()`.
- Một số bulk writes có những ràng buộc riêng, phụ thuộc statement types.

### 17.4. Những thao tác không được coi là retryable single-statement write

Ví dụ:

- `updateMany()`.
- `deleteMany()`.
- Những multi-write patterns không đáp ứng retryable write specification.
- Write concern `w:0`.
- Commands không nằm trong tập eligible.
- Những topology/server versions không hỗ trợ.

Không viết một wrapper “retryWrites=true nên mọi writes đều được retry an toàn”.

### 17.5. Bảng so sánh

| Java operation | Có thể retryable write? | Ghi chú |
|---|---|---|
| `insertOne` | Có khi đủ điều kiện | Dùng session/txn numbering |
| `updateOne` | Có khi đủ điều kiện | Một statement |
| `replaceOne` | Có khi đủ điều kiện | Một statement |
| `deleteOne` | Có khi đủ điều kiện | Một statement |
| `findOneAndUpdate` | Có khi đủ điều kiện | Read-modify-write một document |
| `updateMany` | Không theo cơ chế retryable write thông thường | Nhiều matches |
| `deleteMany` | Không theo cơ chế retryable write thông thường | Nhiều matches |
| `bulkWrite` | Phụ thuộc chứa single vs multi statements | Kiểm tra driver/server |
| Multi-document transaction | Retry qua transaction mechanism | Không đồng nghĩa từng statement retry riêng |

### 17.6. Retryable writes không giải quyết mọi duplicate request

Nếu một HTTP client gửi lại **cùng một request** sau khi lần trước đã thành công, đó là **application-level retry**, không phải driver nội bộ retry cùng lệnh.

Nếu code sinh `new ObjectId()` mỗi lần HTTP request chạy lại, driver không thể biết hai lần đó là cùng một business request.

Dùng idempotency key/unique index cho các yêu cầu có khả năng được gửi lại.

---

## 18. Retryable reads: tự retry một số thao tác đọc

### 18.1. Cấu hình

~~~text
mongodb://mongo1.example.internal:27017/?replicaSet=rs0&retryReads=true
~~~

Java Driver hiện đại thường bật retryable reads mặc định trong điều kiện được hỗ trợ.

### 18.2. Ví dụ đủ điều kiện phổ biến

- `find`.
- `aggregate` cho pipeline không có một số stages ghi dữ liệu bị loại trừ.
- `distinct`.
- Một số commands đọc metadata/cursor khởi tạo theo driver spec.

Không suy từ một phương thức “có vẻ đọc” là chắc chắn driver retry nó; xem operation eligibility trong docs.

### 18.3. getMore không retryable như find ban đầu

MongoDB cursor trả dữ liệu theo batches:

```text
find      → firstBatch
getMore   → secondBatch
getMore   → thirdBatch
~~~

Driver có thể retry `find` theo retryable reads spec. Nhưng `getMore` **không phải** một retryable read theo cùng cơ chế thông thường.

Nếu cursor bị lỗi sau khi đã trả một phần kết quả, ứng dụng không được mặc định “retryReads=true nên tự nhận phần còn lại đúng một lần”.

### 18.4. Đọc dữ liệu đang thay đổi

Ngay cả khi một `find` được retry thành công, application còn phải xem consistency. Hai lần đọc có thể gặp dữ liệu thay đổi do concurrent writes.

Retryable read không tự bảo đảm một snapshot nhất quán trên nhiều lệnh độc lập.

### 18.5. Aggregate có $out/$merge

Aggregation có stages ghi như `$out` hoặc `$merge` có semantics khác read-only aggregation, và không nên được coi là retryable read bình thường.

### 18.6. maxTimeMS và timeout

Dùng `maxTimeMS` hoặc client-side timeouts có thể giúp kiểm soát tài nguyên, nhưng timeout không biến một operation thành retryable và không đồng nghĩa “operation không xảy ra”.

---

## 19. Retryable reads/writes khác transaction retry

| Tiêu chí | Retryable read/write | Retry của transaction |
|---|---|---|
| Phạm vi | Một lệnh đủ điều kiện | Một transaction nhiều lệnh |
| Được bật từ | Connection settings/default | Session transaction API, withTransaction |
| Điều kiện | Operation/topology/error eligible | Error labels/transaction state |
| Lặp lại code business callback | Không theo nghĩa application callback | Có thể với withTransaction |
| Xử lý commit chưa rõ | Không phải commit transaction | Retry commit theo label |
| Bảo đảm nhiều document atomic | Không | Có trong MongoDB |
| Exactly-once external side effects | Không | Cũng không |
| Idempotency key nghiệp vụ | Vẫn cần | Vẫn cần |

### 19.1. retryWrites=true không tự retry toàn transaction body

Khi đang ở transaction, cần dùng transaction retry API/logic; không kỳ vọng `retryWrites=true` sẽ retry độc lập từng `updateOne(session,...)` như lệnh ngoài transaction.

### 19.2. withTransaction không tự retry mọi HTTP request

Driver chỉ kiểm soát transaction attempts bên trong một lời gọi. Nếu client mất HTTP response và gửi lại request, service nhận một **lời gọi mới**. Business idempotency key mới xử lý tình huống này.

### 19.3. Một database write có thể xảy ra hơn một lần ở tầng attempt

Nhờ transaction abort hoặc retryable writes protocol, MongoDB tránh các tác dụng không mong muốn trong phạm vi được bảo đảm. Nhưng metrics/logs có thể thấy nhiều attempts; không đồng nghĩa committed business records bị nhân đôi.

---

## 20. Các lỗi transaction thường gặp

### 20.1. WriteConflict

Hai transactions đồng thời cố sửa một document:

```text
Transaction A reads stock 10
Transaction B reads stock 10
A updates stock
B tries same document
→ một bên có thể gặp WriteConflict/transient abort
~~~

Giải pháp:

- Giữ transaction ngắn.
- Dùng conditional update.
- Dùng `withTransaction()` với retry behavior.
- Tối ưu contention/hot documents.
- Không tự đặt retry vô hạn.

### 20.2. Lock contention

Transactions dài có thể giữ hoặc chờ resources, ảnh hưởng latency và throughput.

Không dùng transaction để giữ một workflow đang đợi:

- Người dùng nhập OTP.
- Payment gateway gọi hàng chục giây.
- API ngoài chập chờn.
- Worker ngủ/backoff dài.

Đặt những operations đó **ngoài transaction** và phối hợp bằng saga/outbox.

### 20.3. TransactionLifetimeLimitSeconds

Trên nhiều MongoDB deployments, mặc định transaction lifetime limit khoảng **60 giây**, nhưng tham số/giá trị cụ thể có thể được quản trị cấu hình và khác theo version/provider.

Transaction chạy quá giới hạn có thể bị abort.

Không tăng giới hạn hàng giờ chỉ để transaction chứa external HTTP call; hãy giảm thời gian body.

### 20.4. DuplicateKey

Một `insertOne` bị duplicate key có thể là:

- HTTP requestId đã được xử lý.
- Concurrent request với cùng idempotency key.
- Data inconsistency.
- Logic sinh ID lỗi.
- Race giữa transactions.

Không retry vô hạn duplicate key. Kiểm tra document đã tồn tại và payload hash theo business policy.

### 20.5. Unauthorized

Thiếu quyền access collection hoặc command không được hỗ trợ trong transaction. Retry cùng credential/role thường không giúp.

### 20.6. TransactionTooLargeForCache

Một transaction quá lớn có thể vượt các giới hạn liên quan cache/resource và bị abort. Nên chia batch hoặc thiết kế lại workflow, không mặc định thêm RAM là cách giải quyết duy nhất.

### 20.7. Primary stepdown/network error

Khi primary thay đổi:

- Transaction có thể nhận transient error.
- Commit outcome có thể chưa rõ.
- Driver rediscover topology và có thể retry theo điều kiện.
- Application cần xử lý kết quả cuối cùng.

Không kết luận “network exception = transaction chắc chắn chưa commit”.

### 20.8. Write concern timeout

Nếu commit có write concern timeout, cần đọc error labels và behavior của server/driver. Một write concern error không phải lúc nào cũng tương đương dữ liệu chưa được ghi.

### 20.9. Inactive/expired session

Logical session có timeout và resource lifecycle do server/driver quản lý. Long-running operations hoặc giữ session không đúng cách có thể dẫn đến session-related errors.

Hãy mở/đóng session theo request/workflow, không giữ vô hạn.

---

## 21. Các thao tác hạn chế trong transaction

Multi-document transactions không hỗ trợ mọi lệnh MongoDB trong mọi phiên bản/topology.

Những điều cần kiểm tra:

- Một số DDL và collection/index management operations.
- Một số administrative commands.
- Aggregation stages `$out` hoặc `$merge`.
- Các ràng buộc với capped collections.
- Collection creation hoặc cross-shard behavior phụ thuộc version.
- Operation types không được driver/server cho phép trong transaction.
- Transaction time/resource limits.

Không lập luận “một lệnh chạy được ở ngoài transaction thì chắc chắn chạy được trong transaction”.

### 21.1. Không tạo index trong callback đặt hàng

Index nên được chuẩn bị trước khi traffic bắt đầu:

~~~javascript
db.getSiblingDB("commerce_lab").orders.createIndex(
  { requestId: 1 },
  { unique: true, name: "uq_request" }
);
~~~

Không để mỗi request tự chạy `createIndex` trong một transaction chỉ để tránh migration step.

### 21.2. Không sửa schema migration bên trong business transaction

Schema/index changes cần migration plan; không trộn với giao dịch đặt hàng nếu chưa có lý do và kiểm tra support.

### 21.3. Sharded transactions có chi phí cao hơn

Một transaction trải nhiều shards cần phối hợp distributed commit. Có thể làm tăng network, resource utilization và tail latency.

Ưu tiên data modeling để các writes thường cùng shard khi phù hợp, nhưng không đánh đổi correctness một cách mù quáng.

---

## 22. Transaction isolation và concurrent updates

### 22.1. Snapshot không có nghĩa không có conflict

Hai transactions có thể đọc từ snapshot riêng, nhưng khi cùng update một document, MongoDB cần xử lý xung đột.

Một transaction có thể bị abort với lỗi transient, để application/driver thử lại.

### 22.2. Conditional update là bạn đồng hành của transaction

Để trừ hàng:

~~~java
UpdateResult result = inventory.updateOne(
        session,
        and(
                eq("_id", sku),
                gte("available", quantity)
        ),
        inc("available", -quantity)
);

if (result.getModifiedCount() != 1) {
    throw new IllegalStateException("Out of stock");
}
~~~

Điều kiện `available >= quantity` thể hiện invariant rõ ràng. Đọc `available` rồi không điều kiện ghi theo một giá trị tính ở application dễ dẫn đến tranh chấp/logic sai nếu không có concurrency control phù hợp.

### 22.3. Business locks và MongoDB transactions

Nếu workflow cần khóa cấp nghiệp vụ lâu dài, MongoDB multi-document transaction không nên trở thành lock giữ hàng phút. Có thể dùng:

- Reservation documents có expiry rõ.
- State machines.
- Compare-and-set version fields.
- Outbox/saga.
- Application retry policies.

### 22.4. Snapshot stale reads

Một transaction có thể đang đọc snapshot không chứa thay đổi vừa xảy ra bên ngoài. Không mặc định mỗi read trong transaction luôn là “dữ liệu mới nhất trên primary”.

---

## 23. Transaction performance: càng ngắn càng tốt

### 23.1. Chi phí của transaction

Một transaction có thể tăng:

- Lock/resource holding.
- Write conflict probability.
- Oplog/replication work.
- WiredTiger cache pressure.
- Tail latency.
- Network round trips.
- Sharded coordination cost.
- Recovery complexity khi timeout.

### 23.2. Đừng lấy transaction làm “batch container” vô hạn

Sai:

~~~java
session.withTransaction(() -> {
    for (Order order : oneMillionOrders) {
        collection.insertOne(session, toDocument(order));
    }
    return null;
}, txnOptions);
~~~

Một transaction cực lớn không phải cách migrate hàng triệu documents an toàn. Hãy chia batches với consistency checkpoint riêng, idempotency và migration runbook.

### 23.3. Tránh business computation trong transaction

Không đặt CPU-heavy image processing, CSV parsing, encryption huge payload hoặc external API calls bên trong callback.

Thực hiện input validation và phần tính toán không cần database snapshot **trước** transaction.

### 23.4. Sắp thứ tự operations

Đọc/ghi chỉ những documents thật sự cần. Thiết kế indexes để điều kiện update/lookup nhanh, tránh giữ transaction mở khi scan lớn.

### 23.5. SLO và limits

Đặt:

- Operation timeout theo driver/server policy.
- Commit timeout khi API hỗ trợ.
- Circuit breaker/HTTP deadline.
- Retry budget.
- Backoff nếu application tự retry sau khi driver trả lỗi.

Không đặt retry budget vượt xa HTTP deadline mà không có asynchronous job/result reconciliation.

---

## 24. Retry policy ở application: điều cần làm và không được làm

### 24.1. Không “catch Exception rồi thử mãi”

Sai:

~~~java
while (true) {
    try {
        placeOrder();
        break;
    } catch (Exception ignored) {
        // Endless retry, hides permanent errors.
    }
}
~~~

Hậu quả:

- Infinite retry khi Unauthorized/validation fail.
- Tạo load storm.
- Không biết commit outcome.
- Hết connection pool/thread capacity.
- Business request bị xử lý lặp.

### 24.2. Chọn retry budget

Khi application có thêm layer retry ngoài driver, phải có:

- Giới hạn tổng số attempts hoặc elapsed time.
- Backoff có jitter.
- Chỉ retry những error categories phù hợp.
- Idempotency key ổn định.
- Telemetry theo attempt.
- Deadline propagation.
- Cơ chế reconcile unknown outcome.

### 24.3. Không retry callback trực tiếp từ web layer khi helper đã retry

Nếu `withTransaction` đã chạy vài attempts rồi throw, web layer không nên tự blindly gọi toàn bộ service method lại nếu không đánh giá business idempotency và error state.

### 24.4. Idempotency không phải miễn phí

Unique index và status-check logic cần thiết kế cẩn thận:

- TTL retention bao lâu?
- Payload hash chuẩn hóa thế nào?
- Nếu cùng key với input khác thì response nào?
- Nếu request đang IN_PROGRESS thì trả pending hay wait?
- Nếu kết quả commit chưa rõ, khi nào query lại?
- Nếu order tạo nhưng outbox chưa publish, worker xử lý ra sao?

---

## 25. Transaction và outbox pattern

### 25.1. Vấn đề dual write

Sai:

~~~text
1. Commit order vào MongoDB
2. Publish OrderCreated sang Kafka
~~~

Nếu bước 1 thành công, bước 2 fail, downstream không biết có order mới.

Đảo thứ tự cũng sai:

~~~text
1. Publish OrderCreated sang Kafka
2. Commit order vào MongoDB
~~~

Nếu publish thành công nhưng DB fail, downstream thấy event cho order chưa tồn tại.

### 25.2. Outbox giải quyết điều gì?

Trong một MongoDB transaction:

~~~text
update inventory
insert order
insert outbox event
COMMIT
~~~

Sau commit, worker:

~~~text
read pending outbox event
publish to broker
mark outbox processed
~~~

Nếu publish thành công nhưng worker crash trước đánh dấu processed, event có thể được publish lại. Vì vậy downstream consumer vẫn cần **idempotency/deduplication**.

### 25.3. Không hứa exactly-once giữa MongoDB và external broker

MongoDB transaction không atomically commit Kafka/SMTP/payment gateway. Outbox đạt consistency ở chỗ **business data và ý định phát event** được commit cùng nhau trong MongoDB, sau đó dùng at-least-once delivery + dedupe.

### 25.4. Outbox worker sample logic

~~~text
repeat:
  find one pending outbox record
  publish with eventId as dedupe key
  if broker ack:
      mark processed with conditional update
  else:
      backoff and retry
~~~

Worker cần xử lý:

- Multiple worker concurrency.
- Duplicate publishes.
- Retry/backoff.
- Poison messages.
- Dead-letter queue.
- Broker acknowledgments.
- Observability/retention.

### 25.5. Tại sao không publish trong withTransaction callback?

Callback có thể chạy lại, còn external broker không thể rollback cùng MongoDB. Outbox tách side effect khỏi callback trong khi vẫn giữ ý định phát event cùng transaction.

---

## 26. Causal reads, read concern và consistency sau commit

### 26.1. Tại sao sau commit vẫn cần quan tâm readConcern?

Nếu workflow viết với write concern yếu rồi failover, durability/visibility có thể khác mong muốn. Một read ngay sau commit từ secondary có thể gặp replication lag nếu không có causal/session controls phù hợp.

### 26.2. Majority write concern

Transaction commit với `WriteConcern.MAJORITY` giúp đợi acknowledgment theo replica set majority rules, giảm một số rủi ro rollback so với weaker acknowledgment trong topology phù hợp.

Nó không bảo đảm hệ thống không bao giờ xảy ra outage hoặc mất dữ liệu dưới mọi tình huống thiên tai/hạ tầng.

### 26.3. ReadConcern.SNAPSHOT

Trong transaction, snapshot read cung cấp cái nhìn nhất quán theo snapshot semantics. Khi kết hợp majority commit, có các guarantees về majority-committed snapshot theo MongoDB docs.

Không nhầm `ReadConcern.SNAPSHOT` với `ReadPreference.secondary()`.

### 26.4. Causal-consistent session

Nếu cần read-your-writes qua những thao tác tuần tự, một causal session với majority read/write concern có thể phù hợp mà không cần multi-document transaction.

### 26.5. Read ngoài transaction

Một read ở session khác, node khác hoặc thời điểm khác có consistency riêng. Transaction không tự tạo end-to-end “mọi nơi nhìn thấy ngay” khi replication/read preferences khác nhau.

---

## 27. Bảng chọn cơ chế phù hợp cho từng bài toán

| Nhu cầu | Nên cân nhắc |
|---|---|
| Cập nhật 2 trường trong 1 document | Single-document atomic update |
| Ghi một đơn hàng | `insertOne` và unique/business key |
| Retry lỗi mạng cho single write eligible | Driver retryable write |
| Retry `find` khi network lỗi eligible | Driver retryable read |
| Update inventory + insert order cùng commit | Multi-document transaction |
| Đảm bảo đọc sau ghi theo quan hệ nhân quả | Causal-consistent session và concerns phù hợp |
| Cần nhiều reads cùng snapshot, không ghi | Snapshot session khi supported |
| Ghi DB và gửi Kafka event | Transaction + outbox |
| Thanh toán bên thứ ba + DB state | Saga/idempotency/reconciliation, không giữ DB transaction xuyên HTTP |
| Bulk migration hàng triệu documents | Batching/checkpointing, không một transaction khổng lồ |
| Client gửi lại HTTP request | Application idempotency key |
| Commit result chưa rõ | Retry commit theo driver; reconcile trạng thái |
| Query read từ secondary | Read preference/causal consistency, không dùng write transaction secondary |
| Mọi query phải cực nhanh | Query modeling/indexing/profiling; transaction không giải quyết automatically |

---

## 28. Transaction trong Spring và các frameworks

Nhiều Java frameworks có transaction abstraction, chẳng hạn Spring Data MongoDB với `MongoTransactionManager`.

Ví dụ khái niệm:

~~~java
@Transactional
public void placeOrder(...) {
    inventoryRepository.reserve(...);
    orderRepository.save(...);
}
~~~

Nhưng **đừng suy từ annotation thành MongoDB transaction chắc chắn hoạt động** nếu:

- Chưa cấu hình transaction manager.
- Server là standalone.
- Code dùng raw MongoClient khác không tham gia session.
- Async tasks chạy ngoài transaction context.
- Service method self-invocation làm framework proxy không áp dụng.
- Transaction operations không được thực thi qua session tương ứng.
- Framework defaults về concerns/timeouts không phù hợp.

Bài này tập trung vào **Java Sync Driver API trực tiếp**; với framework, cần đọc docs phiên bản tương ứng và biết nó quản lý session binding/propagation thế nào.

### 28.1. Transaction boundary

Trong framework cũng phải đặt transaction boundary tại business service layer, không ở controller cho cả HTTP call ngoại vi kéo dài.

### 28.2. Retrying @Transactional không giống withTransaction

Framework có cơ chế retry riêng. Nếu dùng cả framework retry và driver retry cần kiểm soát thứ tự, idempotency và retry budget để tránh nhân số lần chạy ngoài dự kiến.

---

## 29. Command monitoring: quan sát retry mà không lộ dữ liệu

Java Driver cung cấp `CommandListener` để quan sát commands.

### 29.1. Ví dụ listener tối thiểu

~~~java
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.concurrent.TimeUnit;

public final class SafeCommandListener
        implements CommandListener {

    private static final Logger LOG =
            LoggerFactory.getLogger(SafeCommandListener.class);

    @Override
    public void commandStarted(CommandStartedEvent event) {
        LOG.debug(
                "mongo.start command={} database={} requestId={}",
                event.getCommandName(),
                event.getDatabaseName(),
                event.getRequestId());
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        LOG.debug(
                "mongo.success command={} requestId={} elapsedMs={}",
                event.getCommandName(),
                event.getRequestId(),
                event.getElapsedTime(TimeUnit.MILLISECONDS));
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        LOG.warn(
                "mongo.failed command={} requestId={} elapsedMs={} exceptionType={}",
                event.getCommandName(),
                event.getRequestId(),
                event.getElapsedTime(TimeUnit.MILLISECONDS),
                event.getThrowable().getClass().getSimpleName());
    }
}
~~~

**Không log `event.getCommand()` toàn bộ trong production**: command BSON có thể chứa PII, passwords hoặc dữ liệu nhạy cảm. Log mọi successful command ở INFO level cũng có thể tạo log storm.

### 29.2. Đăng ký listener

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

String uri = System.getenv("MONGODB_URI");

MongoClientSettings settings = MongoClientSettings.builder()
        .applyConnectionString(new ConnectionString(uri))
        .addCommandListener(new SafeCommandListener())
        .build();

try (MongoClient client = MongoClients.create(settings)) {
    // Application workload.
}
~~~

### 29.3. Quan sát transaction commands

Có thể thấy các command events liên quan:

- `insert`, `update`, `find`...
- `commitTransaction`.
- `abortTransaction`.

Khi retry xảy ra, command monitoring có thể thấy thêm attempts. Nhưng không nên chỉ đếm number of commandStarted events để suy ra number of committed orders.

### 29.4. Metrics cần theo dõi

- Transaction attempt count.
- Transaction commit/abort count.
- Error labels theo nhóm.
- Retry count theo command type.
- Transaction duration p50/p95/p99.
- WriteConflict rates.
- Unknown commit outcomes.
- Connection pool wait.
- Replica set election/stepdown.
- Server CPU/IO/cache.
- Outbox pending age/duplicate publish.
- Idempotency conflicts.

### 29.5. Monitoring không phải source of truth về commit

Driver callback có thể lỗi mạng ở commit, nhưng server đã commit. Mọi metric “commit failed” cần phân biệt **confirmed failure** và **unknown outcome**.

---

## 30. Thực hành local single-node replica set

### 30.1. Vì sao không dùng standalone?

MongoDB multi-document transaction cần topology hỗ trợ. Trên máy học tập, single-node replica set là lựa chọn đơn giản.

### 30.2. Khởi động mongod lab

Một ví dụ Linux/macOS, cần có MongoDB Server binary và directory phù hợp:

~~~bash
mkdir -p ./mongo-rs-lab
mongod --replSet rs0 --port 27017 --dbpath ./mongo-rs-lab --bind_ip 127.0.0.1
~~~

Đây là **một tiến trình lab**, không sử dụng port/dbPath đang có service MongoDB khác. Trên Windows, chọn directory hợp lệ và PowerShell path tương ứng.

### 30.3. Initiate replica set một node

Mở `mongosh`:

~~~javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "127.0.0.1:27017" }
  ]
});
~~~

Đợi node trở thành PRIMARY:

~~~javascript
rs.status();
db.adminCommand({ hello: 1 });
~~~

Chỉ làm trong môi trường lab. Không chạy `rs.initiate()` lại trên production replica set đã tồn tại.

### 30.4. Connection string

~~~text
mongodb://127.0.0.1:27017/?replicaSet=rs0&retryWrites=true&retryReads=true
~~~

Nếu server bật auth/TLS, thêm các options hợp lệ và dùng secret manager.

### 30.5. Test với transaction đơn giản

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    collection.insertOne(
            session,
            new Document("_id", "txn-lab-001"));

    session.commitTransaction();
}
~~~

Sau đó xem document đã có:

~~~javascript
db.getSiblingDB("commerce_lab")
  .getCollection("orders")
  .findOne({ _id: "txn-lab-001" });
~~~

---

## 31. Lab thử abort transaction

### 31.1. Tạo transaction và abort

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    orders.insertOne(
            session,
            new Document("_id", "abort-lab-001")
                    .append("status", "TEMPORARY"));

    session.abortTransaction();
}
~~~

### 31.2. Kiểm tra

~~~javascript
db.getSiblingDB("commerce_lab")
  .orders.findOne({ _id: "abort-lab-001" });
~~~

Kỳ vọng kết quả `null` trong lab nếu document chưa tồn tại trước đó, vì writes của transaction vừa bị abort.

### 31.3. Thử sai cách không truyền session

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    orders.insertOne(
            new Document("_id", "outside-txn-001"));

    session.abortTransaction();
}
~~~

Document `outside-txn-001` có thể đã được ghi vì lệnh không nhận session và chạy ngoài transaction.

Chỉ làm thí nghiệm này ở lab; đây là anti-pattern để nhận diện bug.

---

## 32. Lab thử lỗi nghiệp vụ trong transaction

### 32.1. Yêu cầu quantity lớn hơn available

Tồn kho `SKU-100` có 25, thử quantity = 100:

~~~java
service.placeOrder("request-out-of-stock", "SKU-100", 100);
~~~

Trong service:

~~~java
UpdateResult reserved = inventory.updateOne(
        session,
        and(
                eq("_id", "SKU-100"),
                gte("available", 100)),
        inc("available", -100));

if (reserved.getModifiedCount() != 1) {
    throw new IllegalStateException(
            "Insufficient inventory");
}
~~~

### 32.2. Kết quả mong đợi

- Transaction callback ném business exception.
- Không commit order/outbox.
- Inventory không giảm.
- Driver không nên retry mãi lỗi hết hàng.

### 32.3. Phân biệt retryable với business errors

Hết hàng không phải lỗi mạng transient. Retry không làm hàng xuất hiện trừ khi có một state change nghiệp vụ khác.

Phương án trả HTTP phù hợp có thể là 409 Conflict hoặc thông điệp cụ thể theo API contract, không phải 500 và retry vô hạn.

---

## 33. Lab concurrency: hai giao dịch tranh cùng inventory

### 33.1. Mô hình

Hai requests cùng mua sản phẩm còn ít tồn kho.

~~~text
Available = 1

Request A: quantity 1
Request B: quantity 1
~~~

### 33.2. Mong muốn

Chỉ một đơn được commit thành công, inventory không âm.

### 33.3. Cơ chế

- Conditional update `available >= quantity`.
- MongoDB transaction isolation/write conflicts.
- Driver retry transaction khi có lỗi transient.
- Sau retry, request thua có thể nhận business failure vì inventory đã hết.

### 33.4. Bài học

**Không đủ chỉ dùng transaction** nếu code không kiểm tra modifiedCount và không đặt business invariant. Đồng thời không cần khóa toàn collection thủ công để giải quyết một update có điều kiện.

### 33.5. Thực hành an toàn

Chạy thử concurrency trên lab nhỏ bằng executor riêng **mỗi task tạo session riêng**, không share một ClientSession giữa tasks.

---

## 34. Lab kiểm thử failover và retry

### 34.1. Vì sao cần replica set nhiều nodes?

Single-node replica set hỗ trợ transaction nhưng không mô phỏng failover có primary mới. Để kiểm tra driver retry qua primary stepdown, dùng replica set nhiều data-bearing members trong lab.

### 34.2. Những tình huống cần test

- Primary stepdown ngay trước write.
- Network timeout khi đang đọc.
- WriteConflict trong transaction body.
- Connection mất quanh commit.
- Retryable write operation trước khi response tới client.
- HTTP retry sau transaction commit thành công.

### 34.3. Không dùng failpoints tùy tiện trên production

MongoDB có testing failpoints như `failCommand` trên các deployment/version/privilege hỗ trợ. Chúng dùng để mô phỏng lỗi, **không phải công cụ production debugging mặc định**.

Chỉ bật trên isolated lab, có thời gian kết thúc và rollback rõ.

### 34.4. Kết quả cần xác minh

Đối với mỗi test:

1. Request có thể thất bại/cần retry theo policy.
2. Inventory không âm.
3. Không có hai orders cho cùng requestId.
4. Outbox có đúng event identity.
5. Không có charge/email phát sinh từ transaction callback.
6. Log có error labels được sanitize.
7. Driver không retry vô hạn.
8. Có cơ chế reconciliation cho unknown commit result.

---

## 35. Một state machine retry cho ứng dụng

Có thể mô hình hóa:

```text
NEW
 │
 ▼
RUNNING_TRANSACTION
 │
 ├── business failure ──> REJECTED
 │
 ├── transient txn error ──> RETRY_TRANSACTION
 │                           (bounded by driver/policy)
 │
 └── body completed ──> COMMITTING
                            │
                            ├── commit success ──> COMMITTED
                            │
                            └── unknown result ──> RETRY_COMMIT
                                                      │
                                                      ├── confirmed
                                                      │    └── COMMITTED
                                                      └── unresolved
                                                           └── RECONCILE
~~~

### 35.1. RECONCILE là gì?

Kiểm tra business record theo requestId và các invariants với read/write concerns thích hợp.

Nếu chưa có bằng chứng chắc chắn:

- Không tự trừ tồn kho lần nữa.
- Có thể trả pending/accepted và tiếp tục background verification.
- Theo dõi idempotency state.
- Có deadline/alert cho operation stuck.

### 35.2. Retry transaction không có nghĩa retry HTTP side effects

Mỗi layer chỉ retry phần nó có thể bảo đảm:

- Driver: commands/transaction attempts.
- Application: idempotent business request.
- Outbox worker: event delivery có dedupe.
- Payment adapter: provider idempotency key.

### 35.3. Backoff

Khi retry ngoài driver, dùng exponential backoff có jitter và bounded budget. Không busy-loop khi primary đang failover hoặc database unavailable.

---

## 36. Các anti-pattern thường gặp

| Anti-pattern | Tại sao sai | Cách tốt hơn |
|---|---|---|
| Dùng session nhưng không startTransaction | Không có multi-document atomicity | Dùng transaction API khi cần |
| Start transaction nhưng quên truyền session | Lệnh có thể chạy ngoài transaction | Pass session vào mọi DB operation |
| Chia sẻ session cho nhiều threads | Không thread-safe | Mỗi workflow sở hữu session |
| Không close session | Resource leak | Try-with-resources |
| Giữ MongoClient mới mỗi request | Tạo pool liên tục | Tái sử dụng MongoClient |
| Gửi email trong withTransaction callback | Callback có thể chạy lại | Outbox worker |
| Charge credit card trong callback | Có thể trùng thanh toán | External idempotency + saga |
| Retry mọi exception | Permanent errors bị lặp vô hạn | Error labels/typed policy |
| Lỗi commit = chắc chắn abort | Commit outcome có thể unknown | Retry commit/reconcile |
| Retry toàn body khi UnknownCommitResult | Có thể nhân business effects | Retry commit same transaction |
| Không có requestId | HTTP retry tạo order mới | Idempotency key + unique index |
| Sinh UUID mới trong mỗi transaction attempt | Dữ liệu không ổn định giữa retries | Precompute deterministic IDs |
| Không kiểm tra modifiedCount | Có thể coi out-of-stock là success | Conditional update + invariant |
| Transaction hàng phút chờ payment | Resource contention/lifetime abort | Tách external calls |
| Mọi thao tác dùng multi-document txn | Chi phí không cần thiết | Single-document atomicity |
| Dùng standalone cho transaction lab | Không supported | Single-node replica set |
| Dùng secondary read preference trong transaction | Không phù hợp transaction routing | Primary |
| Per-operation write concern trong txn | Không đúng transaction semantics | Set transaction write concern |
| retryWrites=true tự retry updateMany | Không đủ điều kiện | Idempotent app retry nếu cần |
| retryReads=true tự retry getMore | Không theo cơ chế đó | Xử lý cursor failure |
| Dùng profiler/log raw query có PII | Lộ dữ liệu | Safe metadata logging |
| Count command events = count committed transactions | Retries nhiều attempts | Đo commit/business result |
| Không test failover | Unknown outcome chỉ lộ trong sự cố | Replica set integration test |
| Dùng nhiều retry layers không ngân sách | Retry amplification | Bounded end-to-end budget |
| Retry DuplicateKey như network timeout | Sai business semantics | Check existing idempotency record |
| Transaction bảo đảm exactly-once Kafka publish | Không bao trùm broker | Outbox + consumer dedupe |
| Không xét sharded transaction cost | Tail latency cao | Data modeling & monitoring |

---

## 37. Runbook xử lý lỗi transaction ở production

### Bước 1 — Xác định phạm vi

- Endpoint/service nào?
- MongoDB cluster, replica set/shard nào?
- Thời điểm bắt đầu?
- Driver/server versions?
- Có primary stepdown hoặc deploy gần đây?
- Số attempts/retries theo request?

### Bước 2 — Phân biệt triệu chứng

- Body error trước commit?
- Unknown commit result?
- Business conflict?
- Unauthorized/validation?
- Network timeout?
- Server selection timeout?
- Transaction lifetime exceeded?

### Bước 3 — Kiểm tra error labels

- `TransientTransactionError`?
- `UnknownTransactionCommitResult`?
- `RetryableWriteError` với single eligible write?
- Error code và category?

Không chỉ grep substring message text.

### Bước 4 — Xem consistency options

- Read concern.
- Write concern (đặc biệt majority).
- Read preference primary.
- Transaction options.
- Client timeout/retry settings.
- Session lifecycle.

### Bước 5 — Xem data/business state

- Order theo requestId.
- Inventory balance.
- Outbox event.
- Payment provider status nếu có.
- Duplicate key records.

Không sửa tay dữ liệu trước khi xác định committed/unknown state.

### Bước 6 — Kiểm tra server health

- Primary availability.
- Elections/stepdowns.
- Replication lag.
- CPU/IO/cache.
- Write conflicts.
- Transaction lifetime/timeouts.
- Shard targeting/cross-shard transaction overhead.

### Bước 7 — Mitigation

- Giảm contention/hotspot.
- Điều chỉnh query/index.
- Rút ngắn transaction.
- Chỉnh backoff/retry budget.
- Cải thiện pool/timeouts.
- Chuyển external side effects sang outbox.
- Thiết kế idempotency/reconciliation.

### Bước 8 — Xác minh

- Không còn tồn kho âm.
- Không trùng orders theo requestId.
- Retry rate trở về nền.
- Commit unknown outcomes được reconcile.
- Outbox không stuck.
- p95/p99 không xấu đi.
- Không có transaction/resource leak.

### Bước 9 — Postmortem

Ghi causes và constraints, không chỉ “MongoDB tự retry”. Bảo vệ logs khỏi lộ credentials, PII và raw query payload.

---

## 38. Checklist code review cho ClientSession và transaction

### 38.1. Session lifecycle

- [ ] MongoClient được tái sử dụng, không tạo mỗi request.
- [ ] Session được tạo đúng client.
- [ ] Session không chia sẻ giữa threads.
- [ ] Try-with-resources hoặc close trong finally.
- [ ] Mỗi database operation thuộc transaction đều nhận session.
- [ ] Không chạy parallel operations trên cùng session.

### 38.2. Transaction correctness

- [ ] Server topology hỗ trợ transaction.
- [ ] Read preference là primary.
- [ ] ReadConcern/WriteConcern được chọn có chủ đích.
- [ ] Conditional updates giữ business invariant.
- [ ] Mọi writes cần atomic đều cùng session/transaction.
- [ ] Không gọi external API trong callback.
- [ ] Không giữ transaction mở qua user interaction.
- [ ] Transaction body ngắn và có indexes.
- [ ] Có xử lý business failures đúng nghĩa.

### 38.3. Retry semantics

- [ ] Biết khi nào dùng retryWrites/retryReads.
- [ ] Không coi updateMany/deleteMany là retryable single writes.
- [ ] Không coi getMore là retryable read.
- [ ] Dùng withTransaction hoặc manual retry đúng labels.
- [ ] Phân biệt TransientTransactionError và UnknownTransactionCommitResult.
- [ ] Không retry toàn callback khi commit result chưa rõ.
- [ ] Không retry vô hạn.
- [ ] Có idempotency key cho HTTP/API retries.
- [ ] Không sinh identity mới trong mỗi callback attempt.
- [ ] Có reconciliation khi unknown outcome.
- [ ] Có backoff/deadline cho application retries.

### 38.4. Security và observability

- [ ] Không hardcode passwords.
- [ ] Không log raw command/client session secrets.
- [ ] Metrics tách attempt/commit/business success.
- [ ] Có monitoring write conflicts, retries và unknown commits.
- [ ] Có integration tests với replica set/failover.
- [ ] Không chứa PII trong metrics labels.
- [ ] Outbox consumers có dedupe.

---

## 39. Câu hỏi và bài tập

### Bài A — Nhận diện transaction thật

Cho:

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();
    inventory.updateOne(session, filter, update);
    orders.insertOne(order);
    session.commitTransaction();
}
~~~

Hỏi:

1. Lệnh nào nằm trong transaction?
2. Nếu commit fail, `orders.insertOne(order)` có thể đã ghi hay chưa?
3. Sửa thế nào để cả hai cùng atomic?

### Bài B — Retry labels

Trình bày sự khác biệt:

- `TransientTransactionError`.
- `UnknownTransactionCommitResult`.
- `RetryableWriteError`.

Lỗi nào phù hợp retry toàn transaction? Lỗi nào cần retry commit?

### Bài C — Outbox

Thiết kế transaction:

1. Trừ tồn kho.
2. Tạo order.
3. Tạo outbox event.

Sau commit, worker gửi event. Nếu worker gửi thành công rồi crash trước khi đánh dấu, consumer cần làm gì?

### Bài D — Retryable operations

Phân loại:

- insertOne.
- updateOne.
- updateMany.
- deleteOne.
- deleteMany.
- find.
- aggregate với `$out`.
- getMore.
- findOneAndUpdate.

Giải thích điều kiện retryable và trường hợp không được hỗ trợ.

### Bài E — Causal consistency

Một user vừa cập nhật profile, ngay lập tức đọc từ secondary.

1. Khi nào session có causal consistency giúp?
2. Read/write concern cần điều kiện gì?
3. Vì sao causal session không làm hai writes thành một transaction?

### Bài F — Transaction và concurrent inventory

Hai requests đặt SKU có available=1. Mỗi request quantity=1.

1. Dùng conditional update.
2. Dự đoán kết quả khi concurrent.
3. Giải thích WriteConflict.
4. Vì sao một bên có thể retry rồi nhận hết hàng?
5. Kiểm tra không có tồn kho âm.

### Bài G — Unknown commit outcome

Client gọi commit, server có thể đã commit nhưng response mất.

1. Có nên abort rồi trả “không đặt hàng”?
2. Có nên chạy lại callback ngay?
3. Driver retry commit thế nào?
4. Khi retry không giải quyết được, làm reconciliation theo requestId ra sao?
5. Phương án HTTP response khi trạng thái chưa xác định là gì?

### Bài H — Java session concurrency

Một singleton giữ ClientSession và chia cho 20 request threads.

1. Sai ở đâu?
2. Session có thread-safe không?
3. Thiết kế lại vòng đời MongoClient/session.
4. Nếu một transaction đang active, có được chạy parallel operations không?

### Bài I — Đo hiệu năng

Một service tăng từ 10 ms lên 250 ms sau khi chuyển single document update sang transaction ba collections.

1. Dùng transaction thật sự cần thiết không?
2. Các writes có ở nhiều shards không?
3. Có write conflict/hotspot không?
4. Transaction kéo dài bao lâu?
5. Có outbox external API call trong callback không?
6. Đo attempt counts/commit latency thế nào?

### Bài J — Test failover

Lập test plan cho three-node replica set:

- Stepdown primary trước transaction.
- Stepdown trong transaction.
- Mất response quanh commit.
- HTTP client retry sau commit.
- Duplicate idempotency key.
- Outbox publish lặp.

Viết expected business invariants, không chỉ expected exceptions.

### Bài K — Spring @Transactional

Một Spring service dùng annotation nhưng raw MongoCollection thao tác qua client khác.

1. Operations đó có chắc tham gia transaction không?
2. Cần cấu hình MongoTransactionManager và session binding thế nào?
3. Có nên đặt payment HTTP call bên trong annotated method không?
4. Framework retry và driver retry phối hợp ra sao?

### Bài L — Đề xuất kiến trúc

Có workflow:

~~~text
Create order
Reserve inventory
Charge card
Send email
Publish Kafka event
~~~

Hãy phân tách:

- MongoDB atomic transaction scope.
- External payment idempotency.
- Outbox.
- Saga/compensation.
- Recovery/reconciliation.
- Monitoring.

Không tuyên bố toàn workflow có một MongoDB atomic transaction duy nhất.

---

## 40. Tài liệu tham khảo chính thức

Nên tra đúng phiên bản MongoDB Server và MongoDB Java Sync Driver đang sử dụng, vì APIs, retry behavior, error labels và topology restrictions có thể thay đổi qua releases.

- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Java Sync Driver — Client-Side Sessions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/#client-side-sessions)
- [MongoDB Java Sync Driver — Configure Connection Options](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/)
- [MongoDB Java Sync Driver — Retryable Reads and Writes](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/retryable-reads-and-writes/)
- [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/monitoring-and-logging/monitoring/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — Retryable Reads](https://www.mongodb.com/docs/manual/core/retryable-reads/)
- [MongoDB Manual — Causal Consistency and Read/Write Concerns](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/)
- [MongoDB Manual — Read Concern snapshot](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Transaction Error Handling](https://www.mongodb.com/docs/manual/core/transactions/#transactions-and-error-handling)
- [MongoDB Specifications — Transactions](https://github.com/mongodb/specifications/blob/master/source/transactions/transactions.md)
- [MongoDB Specifications — Retryable Writes](https://github.com/mongodb/specifications/blob/master/source/retryable-writes/retryable-writes.md)
- [MongoDB Specifications — Retryable Reads](https://github.com/mongodb/specifications/blob/master/source/retryable-reads/retryable-reads.md)

> **Lưu ý thực hành:** Hãy đối chiếu APIs với driver artifact đang dùng. Một số ví dụ rút gọn thể hiện flow tổng quát và cần được tích hợp với xử lý authentication, validation, logging và exception mapping của ứng dụng trước khi triển khai production. Các operation có quyền ghi/xóa chỉ nên chạy trong isolated lab.

---

## 41. Tổng kết

1. **`ClientSession` là ngữ cảnh logical session**, không mặc định là một transaction. Muốn nhiều operations atomic cần gọi transaction API và truyền cùng session cho **mọi DB operation** liên quan.
2. **Transactions cần topology được hỗ trợ**, thường là replica set hoặc sharded cluster. Standalone mongod không phải môi trường transaction multi-document.
3. **MongoClient dùng lại, session dùng tuần tự và close đúng vòng đời**. Không chia sẻ ClientSession giữa request threads.
4. **TransactionOptions** nên được chọn rõ về read concern, write concern và primary read preference; majority commit phù hợp với nhiều nghiệp vụ cần durability.
5. **`withTransaction()`** giúp retry transaction callback và commit theo nhãn lỗi, nhưng callback **có thể chạy nhiều lần**.
6. **`TransientTransactionError`** thường cho phép retry toàn transaction; **`UnknownTransactionCommitResult`** yêu cầu tập trung vào retry commit/reconciliation, không mù quáng chạy lại business body.
7. **Retryable writes/reads** có phạm vi operation-specific. `updateMany`/`deleteMany` và `getMore` không được coi là retryable giống `updateOne`/`find`.
8. **Driver retries không tạo exactly-once business execution**. HTTP retries cần idempotency keys và unique constraints; external side effects cần outbox, saga hoặc provider-side idempotency.
9. **Giữ transactions ngắn**, tránh external calls, kiểm soát contention, timeouts và limits; không dùng transaction để migrate hàng triệu records trong một attempt.
10. **Quan sát và kiểm thử failover** phải đo cả attempts, commit outcomes, business invariants và duplicate suppression, không chỉ đếm exceptions.

**Kết luận:** Sử dụng MongoDB Java Driver đúng nghĩa là chọn **transaction khi cần atomicity, session khi cần consistency context, retry khi operation/error đủ điều kiện, và idempotency khi nghiệp vụ có thể được gọi lại**. Sự kết hợp đúng của bốn lớp này mới giúp một workflow Java giữ được tính chính xác khi MongoDB gặp write conflict, mạng gián đoạn hoặc primary failover.
