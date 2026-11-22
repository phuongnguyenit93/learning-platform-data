# Giao dịch nhiều bản ghi và giới hạn cấu hình/triển khai theo từng hệ

Trong thiết kế NoSQL, câu hỏi “database có hỗ trợ transaction không?” thường chưa đủ để chọn cách triển khai. Điều cần hỏi là: **transaction bảo vệ chính xác những bản ghi nào, trong phạm vi partition/cluster/region nào, với mức isolation và durability nào, và có giới hạn gì về thời gian, kích thước, số thao tác hay hiệu năng?**

Một hệ document có thể bảo đảm thao tác nguyên tử trên một document và còn cung cấp transaction nhiều document. Một dịch vụ key–value có thể hỗ trợ transaction nhiều item nhưng không cho phép giao dịch trải qua nhiều region. Một hệ wide-column có thể cung cấp conditional write mạnh cho một partition, trong khi batch ghi nhiều partition không có semantics tương đương một transaction SQL. Một graph database hoặc một distributed key–value khác lại có các bảo đảm khác nữa.

Sự khác biệt không nằm ở nhãn “NoSQL” mà ở **giao thức ghi, mô hình phân vùng, phạm vi commit, isolation, cấu hình triển khai và hành vi khi lỗi**.

Ví dụ, khi đặt hàng, ứng dụng có thể cần cập nhật:

~~~text
Order O-100:
    status = CONFIRMED

Inventory SKU-A:
    available = available - 2

Outbox:
    append OrderConfirmed event
~~~

Nếu chỉ thay đổi Order mà không trừ Inventory, hệ có thể nhận đơn vượt tồn. Nếu Order và Inventory đã commit nhưng Outbox bị bỏ sót, downstream không nhận được sự kiện. Tuy nhiên, việc cố gom cả thanh toán qua một cổng bên ngoài vào transaction database có thể làm transaction kéo dài hoặc không thể bảo đảm atomicity thực sự.

Bài học này giúp xác định **khi nào nên dùng giao dịch nhiều bản ghi, khi nào phải thay đổi data model, khi nào nên dùng saga/outbox**, cùng cách kiểm tra giới hạn của từng hệ và xử lý các sự cố phân tán.

> **Phạm vi và lưu ý:** Các sản phẩm, API và tính năng dưới đây được giới thiệu theo nguyên lý. Giới hạn định lượng, hành vi transaction, edition, SDK, kiểu replication và cấu hình có thể thay đổi theo phiên bản hoặc chế độ dịch vụ. Không dùng một con số hay phát biểu tổng quát trong bài để thay thế tài liệu chính thức của sản phẩm/cụm đang triển khai.

## 1. Giao dịch nhiều bản ghi là gì?

**Giao dịch nhiều bản ghi (multi-record transaction)** là một đơn vị công việc có thể gồm nhiều thao tác đọc/ghi, trong đó hệ quản trị cung cấp một số bảo đảm về việc **commit hoặc rollback cả nhóm** và về cách nhóm tương tác với các transaction đồng thời.

Các bản ghi có thể ở cùng collection, khác collection, cùng partition hoặc nhiều partition. Không phải hệ NoSQL nào cũng hỗ trợ tất cả các phạm vi ấy.

Ví dụ một transaction chuyển tiền giữa hai tài khoản:

~~~text
Account A: 200
Account B: 100

Transaction T:
    deduct 50 from A
    add 50 to B

Mong muốn sau commit:
    A = 150
    B = 150

Nếu T không commit:
    A = 200
    B = 100
~~~

Nếu chỉ cập nhật A thành công rồi tiến trình chết trước khi cộng B, kết quả trung gian không đáp ứng quy tắc nghiệp vụ.

### 1.1. Transaction khác batch

Một **batch** có thể chỉ là cách gửi nhiều lệnh trong một request để giảm round-trip. Nó không tự bảo đảm:

- Tất cả lệnh cùng commit hoặc cùng rollback.
- Reader không nhìn thấy trạng thái trung gian.
- Các lệnh được cách ly khỏi writer khác.
- Những điều kiện xuyên nhiều bản ghi được bảo vệ nguyên tử.

Một số hệ có **transactional batch** thật sự, số khác có **logged batch** nhằm bảo đảm một khía cạnh của atomicity hoặc khả năng hoàn tất khi lỗi nhưng không cung cấp isolation như transaction SQL. Phải đọc hợp đồng cụ thể.

### 1.2. Atomic item khác atomic transaction

Nếu một document chứa các dòng Order và tổng tiền, cập nhật nguyên tử **một document** có thể đủ để giữ bất biến `total` khớp `items`. Khi chuyển `Order` và `Inventory` sang hai document độc lập, muốn commit đồng thời cần transaction hỗ trợ cả hai hoặc một giao thức nghiệp vụ khác.

### 1.3. Một transaction không đồng nghĩa một HTTP request

Một request HTTP có thể gọi ba database và một gateway. Nó vẫn **không phải transaction nguyên tử toàn bộ** nếu các hệ không cùng tham gia giao thức commit đáng tin.

~~~mermaid
flowchart TD
    API["Checkout HTTP request"] --> O["Order storage"]
    API --> I["Inventory storage"]
    API --> P["Payment gateway"]
    O -. "Không tự có atomicity chung" .- I
    I -. "Không tự có atomicity chung" .- P
~~~

Điều cần xác định là transaction **được điều phối bởi hệ nào** và **có thể rollback những gì**.

## 2. ACID phải được đọc theo phạm vi

Bốn chữ **ACID** là một ngôn ngữ hữu ích, nhưng cần gắn từng thuộc tính với **phạm vi, mức isolation và cấu hình độ bền cụ thể**.

| Thuộc tính | Ý nghĩa cốt lõi | Cần xác minh trong NoSQL |
|---|---|---|
| **Atomicity** | Nhóm thay đổi commit toàn bộ hoặc không commit | Một document, nhiều item cùng partition hay xuyên partition? |
| **Consistency** | Transaction hợp lệ giữ invariant đã được biểu diễn và bảo vệ | Constraint nào do DB thực thi, constraint nào do ứng dụng? |
| **Isolation** | Transaction đồng thời quan sát/ảnh hưởng nhau thế nào | Snapshot isolation, serializable hay cơ chế khác? |
| **Durability** | Sau ACK/commit, kết quả được giữ theo fault model đã cam kết | Local journal/fsync, majority/quorum, region failure? |

### 2.1. Consistency trong ACID khác consistency khi đọc replica

“C” của ACID đề cập đến việc giữ các quy tắc dữ liệu ở ranh giới transaction. “Strong/eventual consistency” trong hệ phân tán thường nói về việc **các replica và reader thấy phiên bản nào**.

Một database có transaction nhiều document nhưng cho phép đọc từ replica trễ. Ngược lại, một key–value service có strong read cho một item nhưng không có transaction tùy ý qua nhiều item. Hai chiều này phải được xem riêng.

### 2.2. Atomicity không tự chứng minh isolation

Giả sử mỗi document được cập nhật nguyên tử:

~~~text
T1: update Account A
T2: update Account B
~~~

Nếu không có transaction chung, reader có thể thấy A đã đổi còn B chưa đổi. Ngay cả khi có atomicity của một batch, cần xác minh reader có thể quan sát kết quả trung gian hoặc transaction đồng thời có gây bất thường không.

### 2.3. Durability không tự đến từ lệnh commit

Một hệ có thể commit và ACK sau khi ghi vào buffer local, sau journal sync, hoặc khi replica quorum xác nhận. Mức bền khi node mất điện hoặc khi leader mất vĩnh viễn sẽ khác nhau. Transaction đúng về atomicity nhưng cấu hình write concern yếu vẫn có thể không đáp ứng RPO của nghiệp vụ.

## 3. Isolation: không phải mọi transaction mạnh như nhau

Các anomaly cần hiểu:

| Hiện tượng | Ví dụ | Hậu quả |
|---|---|---|
| **Dirty read** | Đọc thay đổi chưa commit rồi transaction kia rollback | Dùng dữ liệu chưa hợp lệ |
| **Non-repeatable read** | Hai lần đọc cùng item cho kết quả khác trong một transaction | Logic đọc không ổn định |
| **Phantom** | Truy vấn một tập bản ghi lần hai có thêm/bớt kết quả | Quy tắc dựa trên tập bản ghi có thể sai |
| **Lost update** | Hai writer ghi từ cùng state cũ | Mất thay đổi đã thực hiện |
| **Write skew** | Hai transaction sửa hai record riêng sau khi đọc cùng điều kiện | Vi phạm invariant xuyên record |
| **Serialization failure** | DB phát hiện transaction không thể đồng thời theo model yêu cầu | Ứng dụng phải retry/giải quyết |

### 3.1. Snapshot isolation có thể không đủ cho một số invariant

Ví dụ có hai bác sĩ A, B và quy tắc “ít nhất một bác sĩ đang trực”:

~~~text
Ban đầu:
    A.onCall = true
    B.onCall = true

T1 đọc A=true, B=true; cập nhật A=false.
T2 đọc A=true, B=true; cập nhật B=false.

Nếu hai transaction ghi hai record khác nhau
và engine cho phép cả hai commit:
    A=false, B=false
~~~

Đây là **write skew**. Một số hình thức snapshot isolation không ngăn được tình huống này. Cần transaction serializable, cơ chế predicate/constraint phù hợp hoặc thay đổi mô hình để mọi lệnh cùng cạnh tranh trên một record có thẩm quyền.

### 3.2. Serializable không đồng nghĩa không bao giờ cần retry

Ở mức isolation mạnh, engine có thể **từ chối/abort một transaction** khi phát hiện xung đột để bảo vệ kết quả như một thứ tự tuần tự. Ứng dụng phải xử lý retry thích hợp, không coi transaction abort là lỗi dữ liệu.

### 3.3. Kiểm tra isolation bằng bất biến, không chỉ tên mức cách ly

Nếu nghiệp vụ yêu cầu không oversell, không âm số dư hoặc username unique, cần mô phỏng **nhiều writer cạnh tranh và đọc lại state cuối**. Tên “transaction” không thay thế bài kiểm thử invariant.

## 4. Phạm vi giao dịch: bản ghi, partition, cluster, region

Một sơ đồ phân loại:

~~~mermaid
flowchart TD
    ITEM["Một item / một document"] --> PART["Nhiều item cùng logical partition"]
    PART --> NODE["Nhiều partition / shard trong cluster"]
    NODE --> REGION["Nhiều region"]
    REGION --> SERVICE["Nhiều database hoặc external service"]
~~~

Đi từ trên xuống dưới, khả năng phối hợp thường phức tạp hơn. Một hệ hỗ trợ mức trên **không mặc định hỗ trợ các mức dưới**.

### 4.1. Một document

Đa số document/key–value engine có thao tác ghi nguyên tử tại một đơn vị lưu trữ nhất định. Đây là phạm vi thường dễ đạt độ trễ thấp, ít phối hợp và phù hợp với aggregate nhỏ.

### 4.2. Cùng logical partition

Một số hệ, đặc biệt các dịch vụ partitioned document, hỗ trợ transaction nhiều item khi **cùng partition key**. Điều này có thể đủ nếu một aggregate hoặc một nhóm ràng buộc được lưu cùng partition.

Nhưng không nên nhồi toàn bộ dữ liệu của tenant vào một partition chỉ để dùng transaction, vì tenant lớn có thể tạo **hot partition, giới hạn kích thước và tranh chấp ghi**.

### 4.3. Xuyên partition/shard

Transaction cần điều phối nhiều thành phần. Một số DB hỗ trợ, nhưng thường có thêm round-trip, coordinator state, lock/conflict hoặc log/commit protocol; giới hạn số mục và thời gian có thể chặt hơn thao tác một item.

### 4.4. Xuyên region

Một transaction trong region A không tự bảo đảm cùng tính nguyên tử/serializability với writer ở region B. Một topology multi-writer có thể hòa giải xung đột bằng last-write-wins hoặc cơ chế ứng dụng, làm mất ý nghĩa invariant nếu cả hai region cho phép cập nhật nguồn có thẩm quyền một cách độc lập.

### 4.5. Xuyên service và bên thứ ba

HTTP call tới payment gateway, gửi email hoặc upload object storage **không tự gia nhập transaction của một NoSQL database**. Nếu hệ ngoài không tham gia một giao thức commit đáng tin với phạm vi phù hợp, phải dùng workflow bền, idempotency, saga, outbox và đối soát.

## 5. Ma trận so sánh các hướng giao dịch NoSQL

| Hệ / họ công nghệ | Phạm vi đáng chú ý | Cơ chế điển hình | Cần kiểm tra trước triển khai |
|---|---|---|---|
| **MongoDB** | Transaction nhiều document, có thể liên quan nhiều collection/shard trong deployment hỗ trợ | Session transaction | Topology, read/write concern, isolation, retry, kích thước/thời gian |
| **DynamoDB** | Transaction nhiều item qua API transaction trong phạm vi tài khoản/region được hỗ trợ | TransactWriteItems, TransactGetItems, condition | Giới hạn item/action, capacity, hot key, retry, global tables |
| **Cloud Firestore** | Transaction nhiều document theo phạm vi dịch vụ | Read–modify–write trong transaction callback | Retry callback, thời gian/size, contention, read-before-write |
| **Azure Cosmos DB for NoSQL** | Transaction nhiều item trong **một logical partition key** | Transactional batch, stored procedure | Partition key, batch size/time, ETag, multi-region |
| **Couchbase** | Transaction nhiều document qua SDK/cluster hỗ trợ | Distributed ACID transactions | SDK, deployment, staged mutation, cleanup, durability |
| **Cassandra/ScyllaDB** | Conditional transaction/LWT trong phạm vi được hỗ trợ; batch không tương đương transaction SQL tùy ý | IF/LWT, batch | Partition scope, isolation, Paxos/LWT cost, cross-partition invariant |
| **Redis** | Atomic command/script, MULTI/EXEC và WATCH trong phạm vi instance/cluster phù hợp | WATCH, MULTI/EXEC, Lua | Không rollback toàn bộ do command runtime error, durability, cluster key slots |
| **FoundationDB và một số KV transactional** | Transaction nhiều key/range theo mô hình riêng | MVCC và optimistic conflict detection | Thời gian, kích thước, phạm vi conflict, cluster availability |

Bảng nhằm so sánh **hướng thiết kế**, không phải bảng cam kết giới hạn chính xác. Với một sản phẩm cụ thể, **phiên bản, edition/plan, chế độ triển khai, vùng và SDK** là một phần của câu trả lời.

## 6. MongoDB: multi-document transactions

MongoDB có transaction nhiều document trong những topology được hỗ trợ, dùng **session** để nhóm các thao tác. Điều này hữu ích khi các bản ghi cần commit cùng nhau mà không thể nằm trong một document hợp lý.

Một thao tác gồm:

~~~text
BEGIN transaction in session S
  update Inventory SKU-A (chỉ khi đủ tồn)
  insert Order O-100
  insert OutboxEvent E-100
COMMIT transaction S
~~~

### 6.1. Ví dụ Java (mang tính minh họa)

~~~java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public final class MongoCheckout {
    private final MongoClient mongoClient;
    private final MongoCollection<Document> inventory;
    private final MongoCollection<Document> orders;
    private final MongoCollection<Document> outbox;

    public MongoCheckout(MongoClient client) {
        this.mongoClient = client;
        MongoDatabase db = client.getDatabase("commerce");
        this.inventory = db.getCollection("inventory");
        this.orders = db.getCollection("orders");
        this.outbox = db.getCollection("outbox");
    }

    public void checkout(String orderId, String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        try (ClientSession session = mongoClient.startSession()) {
            session.withTransaction(() -> {
                UpdateResult reserved = inventory.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", sku),
                        Filters.gte("available", quantity)
                    ),
                    Updates.inc("available", -quantity)
                );

                if (reserved.getMatchedCount() != 1) {
                    throw new IllegalStateException("Insufficient stock");
                }

                orders.insertOne(
                    session,
                    new Document("_id", orderId)
                        .append("sku", sku)
                        .append("quantity", quantity)
                        .append("status", "CONFIRMED")
                );
                outbox.insertOne(
                    session,
                    new Document("_id", "order-confirmed:" + orderId)
                        .append("type", "OrderConfirmed")
                        .append("orderId", orderId)
                );
                return null;
            });
        }
    }
}
~~~

Đoạn mã minh họa các lệnh **đều dùng cùng ClientSession**. Nó chưa là quy trình checkout production: cần tenant, số tiền, idempotency, unique indexes, quyền truy cập, định nghĩa retry, write concern/durability, validation và đối soát gateway. Trong một số trường hợp driver có thể chạy lại callback transaction sau lỗi tạm thời; vì vậy **không đưa cuộc gọi thu tiền hoặc gửi email vào callback**.

### 6.2. Cấu hình/topology cần kiểm tra

- Transaction có được hỗ trợ ở deployment hiện tại (replica set/sharded cluster) không?
- Các collection, index và shard key có tương thích đường ghi không?
- Read concern, write concern, read preference và mức isolation của transaction như thế nào?
- Mức ACK có đáp ứng khả năng chịu lỗi node được yêu cầu không?
- Transaction lifetime/lock contention/oplog/journal liên quan có giới hạn nào?
- Driver nhận biết lỗi transaction tạm thời và kết quả commit không xác định ra sao?

Không nên giả định một MongoDB standalone đơn giản có cùng tính năng và bảo đảm với replica set/sharded deployment.

### 6.3. Transaction có thể bị abort khi contention

Nhiều writer cùng sửa Inventory SKU-A có thể gây xung đột. Transaction bị abort không có nghĩa data đã sai; ứng dụng cần chiến lược retry hợp lệ với bounded attempts. Với hotspot lớn, gộp Order và Inventory trong transaction có thể khiến độ trễ tăng mạnh.

### 6.4. Không bỏ qua kết quả commit không xác định

Network timeout đúng lúc commit có thể làm client không biết transaction đã commit chưa. Dùng orderId/commandId ổn định, unique constraints và kiểm tra kết quả trước khi phát lại ý định, không thực hiện payment hai lần.

## 7. DynamoDB: transaction nhiều item với API chuyên dụng

Amazon DynamoDB có những thao tác transaction như **TransactWriteItems** và **TransactGetItems**, cho phép nhóm nhiều hành động trong phạm vi API hỗ trợ.

Một transaction ghi có thể gồm:

~~~text
TransactWriteItems:
  Update Inventory(SKU-A)
    condition available >= 2
    set available = available - 2

  Put Order(O-100)
    condition order does not exist

  Put OutboxEvent(E-100)
    condition event does not exist
~~~

Nếu transaction không đáp ứng điều kiện và không được commit, không nên coi chỉ một phần các hành động đã thành công. Nhưng phải phân biệt **transaction cancellation có nguyên nhân nghiệp vụ** với **timeout không rõ kết quả** ở phía client.

### 7.1. Các action có phạm vi và giới hạn

Trong API cụ thể, có các loại hành động như Put, Update, Delete và ConditionCheck. Cần kiểm tra:

- Giới hạn số action, kích thước tổng request và kích thước từng item.
- Quy tắc có được nhiều action cùng nhắm một item trong cùng transaction không.
- Capacity/throughput và chi phí transaction so với ghi thường.
- Cách xác định conflict và cancellation reasons.
- Có hỗ trợ condition trên item đã được chọn hay không.
- Những thao tác nào không thể tham gia cùng transaction.

Không nên “tách một transaction quá lớn thành hai request TransactWriteItems” rồi mặc định atomicity vẫn giữ nguyên.

### 7.2. Idempotency của transaction request

Một số transaction write API có cơ chế **client request token** với quy tắc idempotency riêng. Khi dùng, phải tuân thủ phạm vi hiệu lực, thời gian và điều kiện cùng payload được định nghĩa trong tài liệu sản phẩm; không được tự suy rằng token đó bảo vệ mọi lần gửi lặp vô hạn.

Với nghiệp vụ cần kết quả bền lâu, thường vẫn nên có một **business commandId** hoặc orderId duy nhất trong dữ liệu, giúp đối soát qua những lần retry, phiên bản client và workflow khác.

### 7.3. Không phải giao dịch multi-region toàn cầu

Transaction trong một region không mặc nhiên bảo đảm các write cùng nghiệp vụ tới global tables ở region khác được điều phối như một transaction serializable xuyên region. Khi có nhiều writer địa lý, phải kiểm tra chế độ replication/conflict resolution và quyết định nơi sở hữu invariant.

### 7.4. Dữ liệu dẫn xuất và GSI

Index hoặc stream có thể cập nhật theo cơ chế riêng. Không suy rằng mọi reader trên mọi index/replica luôn thấy nguyên một snapshot của transaction đúng thời điểm. Nếu ứng dụng yêu cầu kiểm tra trạng thái commit mới nhất, dùng đường đọc/consistency được API bảo đảm.

## 8. Cloud Firestore: transaction callback có thể chạy lại

Cloud Firestore hỗ trợ transaction đọc–ghi nhiều document theo phạm vi và giới hạn dịch vụ. Mẫu quen thuộc là đọc các document cần thiết trong transaction, kiểm tra rồi ghi.

Ví dụ conceptual theo JavaScript SDK:

~~~javascript
await runTransaction(db, async (tx) => {
  const stockSnap = await tx.get(stockRef);

  if (!stockSnap.exists()) {
    throw new Error("Stock record missing");
  }

  const available = stockSnap.data().available;
  if (available < 2) {
    throw new Error("Insufficient stock");
  }

  tx.update(stockRef, { available: available - 2 });
  tx.set(orderRef, {
    orderId: "O-100",
    sku: "SKU-A",
    quantity: 2,
    status: "CONFIRMED"
  });
});
~~~

Đây là ví dụ nhấn mạnh cơ chế transaction; production còn cần unique ID/idempotency, validation, auth, outbox và cấu hình SDK.

### 8.1. Transaction callback có thể chạy nhiều lần

Khi state đã bị writer khác thay đổi, SDK có thể retry transaction theo chính sách của nó. Vì vậy callback cần tránh side effect không thể rollback như:

~~~text
Gọi Payment gateway.
Gửi email.
Ghi log nghiệp vụ vào hệ khác mà không có idempotency.
Upload một file lớn.
~~~

Chỉ nên thực hiện logic tính toán và các thao tác DB nằm trong transaction, hoặc dùng mô hình outbox/workflow sau commit.

### 8.2. Thứ tự read–write

Trong Firestore transaction, cần tuân thủ quy tắc đọc trước khi ghi theo API và SDK được dùng. Đừng giả định cứ gọi `tx.get` sau `tx.update` sẽ trả state mới chưa commit; phải hiểu semantics transaction.

### 8.3. Giới hạn và contention

Cần xác minh giới hạn thời gian, số thao tác/kích thước, cách tính index updates, contention trên document hot và hành vi khi offline. Với transaction do client chạy, còn cần kiểm tra security rules và việc một client chưa đáng tin có được phép ghi tất cả field trong nghiệp vụ hay không.

### 8.4. Transaction khác batched writes

Batch ghi nhiều document có thể phục vụ một nhóm write nguyên tử nhưng **không giống** transaction callback có bước đọc, kiểm tra điều kiện dựa trên snapshot và retry. Chọn đúng API theo nhu cầu.

## 9. Azure Cosmos DB for NoSQL: ranh giới logical partition

Với Cosmos DB for NoSQL, một phạm vi transaction quan trọng là **các item cùng logical partition key**. Transactional batch và stored procedure là hai cơ chế cần nghiên cứu trong phạm vi được hỗ trợ.

Ví dụ:

~~~text
Partition key = (tenantId, orderId) theo mô hình triển khai

Trong cùng logical partition:
    Item Order: O-100
    Item OrderLine: O-100/I-1
    Item OrderLine: O-100/I-2

Transactional batch:
    update Order
    insert OrderLine I-2
    update Order total/version
~~~

Sơ đồ chỉ minh họa mô hình item; khóa phân vùng thực tế phải đáp ứng kiểu path/hierarchical partition key đã cấu hình. Khi các item thuộc **khác logical partition**, không thể mặc nhiên gom chúng vào cùng một batch transaction của Cosmos DB.

### 9.1. Partition key là quyết định correctness

Nếu Inventory SKU-A thuộc một partition còn Order O-100 thuộc partition khác, không thể chỉ gọi transactional batch rồi kỳ vọng transaction xuyên hai partition. Có thể:

- Đặt dữ liệu phải đổi nguyên tử cùng một logical partition nếu đúng mô hình nghiệp vụ và tải.
- Tách các aggregate, dùng conditional write từng nơi và một saga.
- Chuyển yêu cầu thiết kế tới hệ có transaction xuyên phạm vi cần thiết.

Không chọn partition key chỉ để có transaction mà bỏ qua growth/hot partition.

### 9.2. ETag và conditional update

Cosmos DB hỗ trợ revision/ETag cho những thao tác được hỗ trợ. Khi bảo vệ một item, dùng If-Match/condition theo API cụ thể, không tách kiểm tra version ở ứng dụng khỏi lệnh ghi.

### 9.3. Stored procedure và batch không thay thế toàn bộ saga

Stored procedure có thể chạy trong ranh giới partition được hỗ trợ. Nó không tự tham gia transaction với payment gateway hay object storage. Nếu workflow lớn hơn phạm vi ấy, vẫn cần trạng thái bền và bù trừ.

### 9.4. Multi-region và consistency

Chế độ ghi nhiều region hoặc consistency level làm thay đổi cách client thấy state và cách resolve conflict. Transaction cục bộ theo logical partition không đủ để suy ra một invariant toàn cầu mạnh giữa nhiều region.

## 10. Couchbase: transaction nhiều document qua SDK

Couchbase cung cấp các cơ chế transaction nhiều document qua SDK/trong topology được hỗ trợ, nhưng triển khai có các chi tiết riêng về staging, commit, cleanup và durability.

Mô hình khái niệm:

~~~text
runTransaction(ctx):
    stock = ctx.get(Inventory/SKU-A)
    require stock.available >= 2
    ctx.replace(stock, available - 2)
    ctx.insert(Order/O-100, orderPayload)
commit
~~~

Một số SDK cung cấp callback/lambda và có thể retry attempt nếu lỗi tạm thời hoặc conflict. Không được gọi API bên ngoài có side effect trực tiếp trong callback khi nó có thể chạy lại.

### 10.1. Ranh giới triển khai

Cần kiểm tra:

- SDK/version/topology hỗ trợ transaction nào?
- Các collection/bucket/scope nào có thể tham gia?
- Transaction metadata, staging và cleanup chạy ở đâu?
- Mức durability cần cấu hình thế nào?
- Khi node failover hoặc timeout commit, ứng dụng biết outcome ra sao?
- Query trong transaction có visibility và index semantics thế nào?

Không nên bê nguyên code transaction từ MongoDB hoặc DynamoDB sang Couchbase; cơ chế phối hợp khác nhau.

### 10.2. Transaction lớn và hot key

Một transaction dài giữ nhiều document có thể tăng xung đột, retry và chi phí mạng. Nếu nhiều đơn cùng giảm Inventory SKU-A, item inventory vẫn là điểm tranh chấp, dù transaction API cho phép sửa nhiều document.

## 11. Cassandra và ScyllaDB: batch không phải transaction tùy ý

Trong họ Cassandra/ScyllaDB, cần phân biệt:

- Ghi thường vào một row/partition theo consistency/durability phù hợp.
- Conditional write kiểu **IF** và lightweight transaction (LWT) trong phạm vi được sản phẩm hỗ trợ.
- **Batch** để nhóm mutation, với logged/unlogged batch và semantics riêng.

### 11.1. Conditional write/LWT

Ví dụ CQL:

~~~sql
UPDATE inventory
SET available = 3,
    version = 8
WHERE warehouse_id = 'W-1'
  AND sku = 'SKU-A'
IF version = 7;
~~~

Lệnh IF chỉ thành công nếu version theo condition còn phù hợp ở phạm vi hỗ trợ. Trong các hệ như Cassandra, cơ chế LWT/Paxos có chi phí và ràng buộc về phạm vi khác ghi thông thường.

### 11.2. Logged batch không phải SQL transaction

Một logged batch có thể hỗ trợ bảo đảm liên quan việc các mutation cuối cùng được áp dụng theo protocol, nhưng **không nên coi nó là transaction serializable tùy ý xuyên nhiều partition**. Reader và writer đồng thời có thể có semantics khác ACID transaction; các constraint xuyên record vẫn có thể sai nếu không có cơ chế bổ sung.

Ví dụ không nên dựa vào batch thông thường để tự tin triển khai “trừ tài khoản A, cộng tài khoản B, không bao giờ ai thấy trạng thái giữa chừng và mọi lần ghi đồng thời serializable”.

### 11.3. Conditional batch có ràng buộc

Các batch điều kiện có giới hạn và quy tắc partition/statement cụ thể. Cần xác minh trong tài liệu phiên bản trước khi thiết kế một aggregate nhiều row dựa vào chúng; không suy từ sự tồn tại của IF rằng nhiều partition đều có ACID transaction.

### 11.4. Thiết kế lại data model hoặc dùng saga

Nếu invariant chặt thuộc một aggregate có thể ánh xạ vào một partition/row và bảo vệ có điều kiện, đó có thể là hướng phù hợp. Nếu nghiệp vụ trải nhiều partition, cần đánh giá transaction ở hệ khác, single-writer/quota hoặc saga/ledger với đối soát.

## 12. Redis: transaction và atomic script có giới hạn riêng

Redis có **MULTI/EXEC**, **WATCH** và script/Function để tạo thao tác nguyên tử trong phạm vi instance/cluster thích hợp.

### 12.1. MULTI/EXEC

~~~text
MULTI
DECRBY inventory:SKU-A 2
HSET order:O-100 status CONFIRMED
EXEC
~~~

Các command được thực thi theo cơ chế transaction của Redis, không bị command từ client khác chen vào giữa trong phạm vi được hỗ trợ. Nhưng **Redis MULTI/EXEC không cung cấp rollback như database ACID trong mọi trường hợp**: nếu một command gặp lỗi lúc thực thi, những command khác có thể vẫn được thực hiện. Vì vậy không được coi đây là transaction có thể rollback bất kỳ side effect giống RDBMS.

### 12.2. WATCH để bảo vệ điều kiện

~~~text
WATCH inventory:SKU-A
available = GET inventory:SKU-A

if available < 2:
    UNWATCH
    return INSUFFICIENT

MULTI
DECRBY inventory:SKU-A 2
EXEC
~~~

Nếu key thay đổi trước EXEC, transaction có thể bị hủy. Client cần xử lý conflict và retry giới hạn. Đó là mẫu OCC, không phải một phép kiểm tra ở ứng dụng được phép tách khỏi commit tùy ý.

### 12.3. Lua/script

Một script có thể kiểm tra và giảm tồn trong một thao tác nguyên tử theo semantics Redis. Tuy nhiên vẫn cần idempotency commandId để retry sau timeout không trừ hai lần.

### 12.4. Cluster và durability

Trong Redis Cluster, thao tác nhiều key có ràng buộc về key slot/hashing; cần kiểm tra khả năng chạy các lệnh trên key thuộc cùng slot theo API thực. Persistence AOF/RDB, replication và failover có bảo đảm khác một transaction logic. Không được suy “EXEC thành công” có nghĩa mọi byte đã durable trên quorum theo fault model bất kỳ.

## 13. Không phải mọi NoSQL đều thiếu transaction xuyên key

Một số transactional key–value store, như FoundationDB, được thiết kế quanh giao dịch nhiều key với optimistic conflict detection và các giới hạn vận hành riêng. Đây là phản ví dụ cho kết luận “NoSQL luôn chỉ có atomicity một record”.

Tuy vậy, ngay cả khi một hệ hỗ trợ transaction xuyên nhiều key, vẫn cần xem:

- Thời gian/số bytes và read/write set tối đa.
- Phân vùng dữ liệu và xung đột theo key/range.
- Hành vi khi transaction conflict hoặc timeout.
- Durability/replication/fault tolerance.
- Phạm vi transaction so với external service.

**Có transaction không đồng nghĩa transaction nên bao trùm mọi bước nghiệp vụ**.

## 14. Hướng thiết kế ưu tiên: tìm aggregate trước transaction

Một cách giảm nhu cầu transaction xuyên nhiều record là **đặt những dữ liệu thực sự cần thay đổi nguyên tử vào một aggregate có kích thước hợp lý**.

Ví dụ:

~~~text
Order Aggregate
├── Order status/version
├── OrderItem I-1
├── OrderItem I-2
└── Total
~~~

Nếu số dòng hàng hữu hạn và luôn được cập nhật qua Order root, một document Order có thể bảo vệ:

~~~text
total == sum(item.quantity * capturedUnitPrice) - discounts
~~~

trong một atomic update. Nếu OrderItem được tách thành các document khác, có thể phải dùng transaction nhiều item để bảo vệ cùng invariant.

### 14.1. Đừng nhúng mọi thứ cho tiện atomicity

Không nên nhúng toàn bộ Order của Customer, toàn bộ Comment của Post hoặc mọi reservation của SKU vào một document lớn vô hạn. Rủi ro gồm:

- Giới hạn kích thước item/document.
- Hot key và conflict cao.
- Ghi amplification khi thay đổi một phần nhỏ.
- Vòng đời retention khác nhau.
- Phân trang và index khó tối ưu.

### 14.2. Một quan hệ dữ liệu không đủ chứng minh transaction boundary

Product và Order có liên hệ nhưng catalog có vòng đời riêng; giá đã chốt nên được lưu thành **snapshot** trong Order. Customer và Orders có liên hệ nhưng mỗi đơn có thể là aggregate riêng. Invariant **không bán vượt tồn** phải được bảo vệ ở Inventory source of truth, không bằng cách tin bản sao tồn kho trong Order.

### 14.3. Nguyên tắc thực hành

Giữ aggregate **đủ nhỏ để tránh contention và dữ liệu vô hạn**, nhưng **đủ lớn để những bất biến cần commit cùng nhau không bị tách thành workflow dễ sai**.

## 15. Ma trận lựa chọn theo nhu cầu

| Nhu cầu | Cơ chế ứng viên | Lý do/điều kiện |
|---|---|---|
| Sửa total cùng items nhỏ, bounded | Atomic document update | Một aggregate trong một document |
| Trừ tồn nếu đủ | Conditional update/CAS trên Inventory item | Bất biến cục bộ theo SKU/kho |
| Tạo Order và Outbox cùng nguồn | Transaction nhiều item được hỗ trợ | Tránh commit Order mà mất ý định phát event |
| Tạo nhiều document cùng logical partition | Transactional batch nếu DB hỗ trợ | Phạm vi batch thật sự bao hết records |
| Chuyển tiền qua hai account trong một DB transactional | Transaction/isolation phù hợp hoặc ledger transaction | Cần atomicity và kiểm soát concurrent debits |
| Order + Inventory khác hệ | Saga, quota hoặc thay đổi ranh giới | Không có transaction chung mặc nhiên |
| Payment gateway + Order | Idempotent workflow và đối soát | External API không tự tham gia DB transaction |
| Truy vấn lịch sử theo Customer | Read model/projection | Đường đọc không phải nguồn bảo vệ invariant |
| Tạo username duy nhất | Unique index/conditional create | Không dùng query-then-insert |
| Event append lớn, có nguồn replay | Idempotent ingest + durability contract | Không nhất thiết transaction mỗi event |

Quyết định phải dựa trên **invariant, read/write pattern và khả năng sản phẩm đang triển khai**; không thể chọn từ nhãn “document” hay “wide-column” một cách máy móc.

## 16. Case study: xác nhận đơn hàng và giữ tồn kho

Giả sử đơn O-100 muốn giữ 2 sản phẩm SKU-A. Inventory có available=3.

Một yêu cầu:

~~~text
Create Order O-100
Reserve 2 units of SKU-A
Commit Order status
Emit OrderConfirmed event
~~~

### 16.1. Nếu các bản ghi ở cùng một hệ transactional

Có thể thử dùng transaction:

~~~text
Transaction:
    check Inventory.available >= 2
    decrease Inventory.available by 2
    create Order O-100 if not exists
    create Outbox E-100 if not exists
Commit
~~~

Để đúng khi cạnh tranh, thao tác kiểm tra số tồn phải được bảo vệ ở commit, bằng conditional update hoặc isolation phù hợp. Hai transaction cùng đọc available=3 không được đồng thời chấp nhận giữ tổng 4.

Nếu transaction span nhiều partition, phải xác minh DB hỗ trợ, chi phí và thời gian. Nếu không hỗ trợ, không thể đơn giản tách thành ba write rồi đặt tên function là `transactionalCheckout`.

### 16.2. Nếu Order và Inventory ở hai hệ

Một workflow có thể là:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> RESERVING: Request inventory
    RESERVING --> RESERVED: Reservation accepted
    RESERVING --> CANCELING: Not enough stock
    RESERVED --> CONFIRMING: Finalize order
    CONFIRMING --> CONFIRMED: Commit + outbox
    CONFIRMING --> CANCELING: Failure requiring compensation
    CANCELING --> CANCELED: Release reservation
    CONFIRMED --> [*]
    CANCELED --> [*]
~~~

Inventory phải có **reservationId** và bảo vệ số tồn nguyên tử. Order dùng version/state transition để không xác nhận sau khi bị hủy. Workflow lưu trạng thái bền để có thể tiếp tục sau crash; release phải idempotent.

### 16.3. Timeout ở bước reserve

Client timeout không đồng nghĩa reserve thất bại. Có thể đã commit reservation nhưng ACK mất. Nếu retry tạo một reservationId mới và trừ tiếp, hệ sẽ giữ hàng hai lần. Cần dùng cùng reservationId và API tra cứu outcome.

### 16.4. TTL không thay thế bù trừ

Một reservation hết TTL không tự cộng tồn lại theo đúng business rule nếu dữ liệu đã bị xóa trước khi worker biết cần release. Cần deadline, trạng thái bền, retry/idempotency và đối soát.

## 17. Case study: chuyển tiền giữa hai tài khoản

Đây là ví dụ điển hình không nên thay transaction bằng hai update độc lập.

~~~text
Account A = 200
Account B = 100
Transfer T-100: 50 from A to B
~~~

### 17.1. Mô hình sai

~~~text
if A.balance >= 50:
    A.balance -= 50
    B.balance += 50
~~~

Hai transaction cùng trừ A có thể khiến A âm nếu check-then-act không được bảo vệ. Nếu crash sau khi trừ A, B chưa được cộng.

### 17.2. Transaction đúng phạm vi

Khi DB hỗ trợ transaction nhiều item phù hợp:

~~~text
Transaction T-100:
    ASSERT transferId not processed
    ASSERT A.balance >= 50
    UPDATE A.balance -= 50
    UPDATE B.balance += 50
    INSERT TransferLedger(T-100, 50, A, B)
COMMIT
~~~

Ngoài atomicity, cần isolation tránh write skew/lost update, và cần idempotency theo transferId. Nếu transactional isolation không bảo vệ ràng buộc balance, nên dùng atomic predicate trên A hoặc chiến lược khác có thể chứng minh đúng.

### 17.3. Ledger và kiểm toán

Một thiết kế tài chính nghiêm túc có thể dùng **ledger entries không sửa tùy tiện** và xác định số dư qua posting/balance projection, với transaction hoặc giao thức bền phù hợp. Số tiền phải dùng decimal/integer minor units theo contract, không dùng floating-point tùy tiện.

### 17.4. Hai hệ độc lập

Nếu A và B thuộc hai dịch vụ/tổ chức khác nhau, hai lệnh CAS độc lập không tạo transfer nguyên tử. Cần protocol chuyển tiền phù hợp, có trạng thái, reservation, settlement và đối soát; không thể coi việc trả HTTP 200 từ hai API là một transaction phân tán đáng tin.

## 18. Transactional outbox: cầu nối tới event-driven

Một bài toán:

~~~text
1. Ghi Order CONFIRMED thành công.
2. Worker chết trước khi publish OrderConfirmed.
3. Search/index, email và analytics không biết đơn đã xác nhận.
~~~

Nếu database hỗ trợ transaction chứa Order và Outbox:

~~~text
BEGIN
    UPDATE Order status=CONFIRMED
    INSERT Outbox(eventId=E-100, type=OrderConfirmed)
COMMIT

Publisher:
    đọc Outbox đã commit
    phát event

Consumer:
    cập nhật projection idempotently
~~~

### 18.1. Outbox phải cùng phạm vi nguyên tử

Nếu Order ở partition A còn Outbox ở partition B mà hệ chỉ hỗ trợ transaction một partition, hai thao tác chưa được bảo vệ. Cần thiết kế outbox item cùng partition nếu phù hợp, dùng transaction xuyên partition có hỗ trợ, hoặc chọn cơ chế CDC/dual-write safety khác có bằng chứng rõ.

### 18.2. Publisher có thể phát trùng

Publisher phát xong nhưng chết trước khi đánh dấu event đã gửi. Sau restart nó phát lại. **Outbox không mặc nhiên cung cấp exactly-once processing trên mọi consumer**. Consumer cần dedupe theo eventId hoặc thao tác idempotent.

### 18.3. Thứ tự event

Nếu Order chuyển version 7 -> 8 -> 9, projection phải xử lý thứ tự hoặc so sánh version. Event v8 đến sau v9 không được ghi đè state mới hơn. Transaction nguồn giúp event được ghi cùng state, nhưng consumer vẫn cần giao thức ordering/idempotency.

## 19. Retry và “commit outcome không xác định”

Trong giao dịch phân tán, có một tình huống khó:

~~~text
Client gửi COMMIT.
Database đã commit.
Network mất kết nối trước response.
Client nhận timeout.
~~~

Client không thể kết luận **commit thành công** hoặc **commit thất bại** chỉ dựa trên timeout.

### 19.1. Các outcome cần phân biệt

| Kết quả | Ý nghĩa | Xử lý |
|---|---|---|
| **Committed** | Giao dịch được xác nhận commit theo protocol | Trả kết quả bền, tiếp tục workflow |
| **Aborted/Conflict** | DB không cho transaction commit | Đánh giá retry từ state mới |
| **Business precondition failed** | Không đủ kho, không đúng trạng thái | Không retry mù |
| **Transient failure** | Lỗi tạm thời có thể thử lại | Retry theo quy tắc SDK/DB |
| **Unknown commit outcome** | Không biết đã commit chưa | Tra cứu theo commandId hoặc protocol retry commit thích hợp |

### 19.2. Idempotency ở tầng nghiệp vụ

Một transaction có thể retry trong thời gian driver cho phép, nhưng người dùng vẫn có thể gửi cùng request vài phút sau. Dùng **business commandId** được lưu trong cùng transaction nếu có thể.

~~~json
{
  "commandId": "checkout-7281",
  "orderId": "O-100",
  "result": "CONFIRMED",
  "createdAt": "2026-11-14T09:00:00Z"
}
~~~

Khi cùng commandId tới lần nữa, API tra lại kết quả đã xử lý; không tạo đơn mới hoặc thu tiền thêm.

### 19.3. Không đưa side effect ngoài DB vào callback retry

Sai:

~~~text
runTransaction(() -> {
    deductInventory()
    callPaymentGateway()  // có thể thực hiện hơn một lần!
    insertOrder()
})
~~~

Nếu transaction callback được SDK chạy lại sau conflict, gateway có thể bị gọi nhiều lần. Nên tách payment theo idempotent workflow trước/sau commit thích hợp, lưu trạng thái và đối soát.

### 19.4. Retry có thể gây bão tải

Khi nhiều client cùng sửa Inventory SKU-A, transaction conflict liên tiếp có thể tạo **retry storm**. Dùng bounded retries, exponential backoff có jitter, rate limiting, queue per key hoặc quota được phân bổ có kiểm soát. Thêm retry vô hạn thường khiến p99 xấu đi.

## 20. Isolation của transaction và đọc từ replica

Một transaction commit ở primary không nhất thiết lập tức xuất hiện trên mọi read replica hoặc search index.

### 20.1. Read-your-writes

Sau khi trả lời “Đơn đã xác nhận”, nếu UI đọc lại từ một replica trễ, nó có thể thấy PENDING. Cần cấu hình read concern/consistency phù hợp, session/casual consistency nếu hệ hỗ trợ, hoặc đọc từ nguồn có thẩm quyền để đáp ứng UX.

### 20.2. Query index không phải transaction snapshot mặc định

Một secondary/global index hoặc search projection có thể có lag và semantics riêng. Không suy rằng mọi query trên index luôn thấy một snapshot đồng thời với transaction nguồn.

### 20.3. Transaction commit và event đến consumer

Order và Outbox có thể cùng commit, nhưng email/search/analytics cập nhật về sau. Đây là **eventual consistency của hệ dẫn xuất**, không phải bằng chứng transaction nguồn không nguyên tử.

### 20.4. Multi-region write skew

Hai region có thể cùng chấp nhận reservation trên cùng SKU bằng local condition rồi đồng bộ sau. Nếu conflict resolution chỉ chọn một phiên bản thắng, một khách có thể đã được hứa hàng mà state thắng cuối không ghi nhận reservation đó. Cần một nguồn quyết định toàn cầu hoặc quota/coordination tương ứng với invariant.

## 21. Giới hạn cấu hình và triển khai phải được kiểm tra cụ thể

Khi chọn tính năng transaction, lập checklist cho **phiên bản production** thay vì chỉ thử trên local development.

| Chiều giới hạn | Câu hỏi cần tra trong tài liệu và đo |
|---|---|
| **Version/edition/plan** | Transaction đã được hỗ trợ ở phiên bản và gói sử dụng hiện tại chưa? |
| **Topology** | Standalone, replica set, cluster, sharded, serverless có khác nhau không? |
| **Partition scope** | Một logical partition hay nhiều partition? |
| **Region scope** | Transaction chỉ trong một region hay có bảo đảm xuyên region? |
| **Cross-container/table** | Có thể giao dịch nhiều collection/table/bucket không? |
| **Action count** | Tối đa bao nhiêu thao tác hoặc item? |
| **Request/document size** | Tổng bytes và kích thước từng record có giới hạn nào? |
| **Transaction duration** | Có timeout, lifetime hoặc idle timeout không? |
| **Read/write sets** | Có hạn chế số read, write, query, index access không? |
| **Isolation** | Snapshot, serializable hay bảo đảm cụ thể nào? |
| **Durability/write concern** | ACK sau local journal, quorum hay mốc khác? |
| **Conflict handling** | Driver auto retry, abort code, commit uncertainty thế nào? |
| **Capacity/cost** | Transaction tốn read/write units, throughput hay network overhead bao nhiêu? |
| **SDK limitations** | Thứ tự read/write, callback retry, session binding và async behavior? |
| **Security rules** | Tất cả item có cùng quyền và tenant context không? |
| **Data model/index** | Secondary index, TTL, CDC, change stream tham gia ra sao? |

### 21.1. Không gắn cứng các ngưỡng số vào kiến trúc

Giới hạn số item, bytes và thời gian có thể khác giữa dịch vụ hoặc thay đổi theo phiên bản. Nếu một transaction gần sát giới hạn hiện tại, hệ khó phát triển khi số line item, metadata hoặc index tăng.

Thiết kế cần có **headroom**, công cụ đo kích thước thật, và một hướng xử lý khi transaction vượt phạm vi. Không chỉ bắt lỗi sau khi hệ đã lên production.

### 21.2. Dev cluster khác production

Local emulator có thể thiếu một số giới hạn hoặc hành vi conflict/replication. Một đơn lẻ chạy tốt ở local chưa chứng minh sharded cluster, multi-region topology hay serverless tier có cùng mốc ACK và latency.

### 21.3. Transaction scope có thể ảnh hưởng partition key

Chọn cùng partition có thể giúp transaction, nhưng nếu partition chứa toàn bộ activity của một tenant lớn, nó có thể thành hot partition. Phải cân bằng **điều kiện nguyên tử** với **phân phối tải và kích thước dữ liệu**.

## 22. Chi phí của transaction nhiều bản ghi

Một transaction cần điều phối nhiều item có thể:

- Tăng số round-trip giữa coordinator và storage node.
- Tăng write-ahead/intent/commit metadata.
- Giữ snapshot, lock hoặc conflict tracking lâu hơn.
- Khiến các retry tiêu tốn thêm capacity.
- Tạo hotspot ở item chung như Inventory.
- Làm tăng p95/p99 latency khi transaction dài.
- Làm giảm availability trong một số tình huống partition mạng.

### 22.1. Tránh transaction dài

Không nên mở transaction rồi:

~~~text
BEGIN
    đọc Order
    gọi API tính thuế qua Internet
    chờ khách xác nhận thanh toán
    upload PDF lớn
    cập nhật Inventory
COMMIT
~~~

Thời gian chờ network và con người không được che bằng transaction. Nên chuẩn bị dữ liệu trước, chỉ giữ phần **đọc/ghi cần nguyên tử** trong transaction ngắn, còn bước bên ngoài theo workflow.

### 22.2. Transaction nhỏ vẫn có thể nghẽn

Nếu 50.000 checkout/s cùng trừ SKU flash sale, một item Inventory có thể bị tranh chấp. Giảm số document trong transaction chưa chắc giải quyết hot key; cần quota, queue hoặc thiết kế phân phối trách nhiệm.

### 22.3. Đo chi phí theo percentiles

Không chỉ đo trung bình. Cần throughput, p95/p99 transaction duration, abort/conflict rate, retry count, lock/intent wait, capacity throttling, hot partition và tail latency khi failover.

## 23. Khi nào nên dùng saga thay transaction lớn?

**Saga** là một workflow gồm nhiều transaction cục bộ, mỗi bước có trạng thái bền và khi cần thì có **hành động bù (compensation)**. Nó phù hợp khi không có transaction ACID chung hoặc khi transaction quá lớn/đắt.

Ví dụ checkout:

~~~mermaid
flowchart TD
    O["Create Order PENDING"] --> R["Reserve Inventory"]
    R --> A{"Reserved?"}
    A -->|Có| P["Authorize Payment"]
    A -->|Không| C["Cancel Order"]
    P --> B{"Payment accepted?"}
    B -->|Có| F["Confirm Order"]
    B -->|Không| REL["Release Inventory"]
    REL --> C
~~~

### 23.1. Compensation không phải rollback thực sự

Nếu đã gửi email cho khách rồi phải hủy đơn, không thể “unsend” email như rollback một row. Có thể gửi email đính chính, refund, giải phóng reservation hoặc cập nhật trạng thái.

Những hành động bù thường:

- Có thể thất bại và cần retry.
- Cần idempotency để không hoàn tiền hai lần.
- Có thể để tồn tại trạng thái trung gian hợp lệ.
- Cần job đối soát hoặc xử lý thủ công khi bị kẹt.

### 23.2. Saga không cho phép phá invariant cục bộ

Inventory vẫn phải bảo vệ số tồn tại lúc reserve. Payment vẫn phải bảo vệ capture/refund theo paymentId. Saga điều phối **các bước**, không thay thế atomic predicate trong từng aggregate.

### 23.3. Transaction hay saga?

| Tiêu chí | Transaction nhiều bản ghi | Saga/workflow |
|---|---|---|
| Cùng một DB có bảo đảm đủ mạnh | Thường đơn giản hơn | Có thể không cần thiết |
| Nhiều service/gateway ngoài | Thường không bao phủ toàn bộ | Thường phù hợp hơn |
| Bất biến cần đúng ở mọi thời điểm commit | Dùng nếu transaction hỗ trợ đúng phạm vi | Phải thiết kế invariant cục bộ thật chặt |
| Trạng thái trung gian có chấp nhận được không? | Ít bộc lộ hơn | Phải định nghĩa rõ |
| Tải cực lớn/hot key | Có thể contention cao | Có thể cần queue/quota |
| Recovery sau crash | DB hỗ trợ rollback/recovery nội bộ | App phải lưu workflow và bù trừ |
| Độ phức tạp nghiệp vụ | Đơn giản nếu phạm vi nhỏ | Phức tạp hơn do state/retry/đối soát |

## 24. Hai-phase commit (2PC) và lý do không nên tự dựng tùy tiện

Một số hệ distributed transaction dùng mô hình **prepare → commit/abort** với coordinator và participants. Ý tưởng là tất cả participants chuẩn bị trước, sau đó cùng nhận quyết định.

~~~mermaid
sequenceDiagram
    participant C as Coordinator
    participant A as Participant A
    participant B as Participant B
    C->>A: PREPARE
    C->>B: PREPARE
    A-->>C: READY
    B-->>C: READY
    C->>A: COMMIT
    C->>B: COMMIT
    A-->>C: ACK
    B-->>C: ACK
~~~

Trong thực tế, coordinator và participants phải ghi trạng thái bền, giải quyết crash đúng thời điểm, phục hồi quyết định commit và xử lý timeout. 2PC truyền thống có thể gặp **blocking** khi coordinator lỗi ở giai đoạn nhất định nếu không có cơ chế phục hồi phù hợp.

Không nên tự mô phỏng 2PC bằng vài HTTP request `prepare` và `commit` rồi tuyên bố ACID. Khi cần giao dịch phân tán mạnh, ưu tiên một database/protocol đã được chứng minh và kiểm tra fault model. Với nhiều dịch vụ nghiệp vụ, saga thường có chi phí triển khai và semantics khác, nhưng phù hợp hơn nếu không thể rollback các side effect.

## 25. Những sai lầm phổ biến

### “NoSQL không có giao dịch nhiều bản ghi”

Sai. Nhiều sản phẩm hỗ trợ transaction nhiều item/document, nhưng phạm vi và giới hạn khác nhau.

### “Có API transaction nghĩa là ACID trên mọi cluster, region và service”

Sai. Phải kiểm tra topology, partition boundary, isolation, durability và phạm vi external API.

### “Batch gửi cùng request là transaction”

Không mặc nhiên. Batch có thể chỉ giảm round-trip hoặc bảo đảm một phần, không có serializable isolation.

### “Atomic write trên hai document riêng đủ cho bất biến chung”

Không. Hai lệnh nguyên tử riêng vẫn có thể để lại trạng thái giữa chừng hoặc write skew.

### “Snapshot isolation loại bỏ mọi anomaly”

Không. Một số mô hình snapshot isolation vẫn cho phép write skew khi transaction ghi các record khác nhau.

### “Transaction commit rồi thì mọi read replica/search index đã có dữ liệu”

Không mặc nhiên. Replication/read concern/index propagation có semantics riêng.

### “Cứ thêm transaction là không cần CAS”

Không phải lúc nào. Business predicate như đủ tồn, đúng status hoặc unique key vẫn phải được bảo vệ theo isolation/constraint thực tế.

### “Firestore callback transaction chạy đúng một lần”

Không nên giả định. Một số SDK có thể retry callback, nên không đưa side effect không idempotent vào đó.

### “Redis MULTI/EXEC rollback toàn bộ nếu một command gặp runtime error”

Không. Semantics của Redis khác database transaction rollback kiểu SQL.

### “Logged batch Cassandra tương đương transaction serializable xuyên mọi partition”

Không. Batch có ý nghĩa riêng và không tự bảo vệ invariant tùy ý.

### “Cosmos DB transactional batch đi qua mọi partition”

Không. Phạm vi logical partition là một ranh giới quan trọng.

### “DynamoDB transaction tự bảo vệ global tables đa region”

Không thể suy ra bảo đảm đó; cần xác minh replication và conflict resolution.

### “Nếu transaction timeout thì chắc chắn rollback”

Không. Client có thể không nhận ACK dù commit thành công. Cần xác định unknown outcome.

### “Retry transaction bằng cách lặp cả payment gateway”

Nguy hiểm. Gateway có thể thu tiền nhiều lần nếu callback/retry lặp.

### “Có transaction thì không cần idempotency”

Transaction xử lý atomicity trong phạm vi commit, còn idempotency xử lý cùng nghiệp vụ bị gửi lại.

### “Gom mọi dữ liệu liên quan vào một partition là tốt nhất”

Có thể tạo hot partition, dữ liệu vô hạn, index phình to và làm giảm khả năng mở rộng.

### “Saga là rollback”

Saga là chuỗi bước bù có thể thất bại, trễ và không xóa được mọi hiệu ứng đã quan sát.

## 26. Quy trình chọn transaction cho một tính năng mới

1. **Liệt kê command nghiệp vụ:** CreateOrder, ReserveStock, CapturePayment, Refund.
2. **Viết bất biến:** điều gì phải đúng ngay sau commit, điều gì có thể hoàn thành về sau?
3. **Xác định aggregate/root:** bản ghi nào sở hữu quy tắc?
4. **Vẽ phạm vi lưu trữ:** item, logical partition, table, shard, region, service.
5. **Thử mô hình một item:** có thể nhúng dữ liệu bounded và cập nhật nguyên tử không?
6. **Kiểm tra transaction API:** có bao hết record cần thiết không, isolation ra sao?
7. **Tra giới hạn production:** version, edition, capacity, kích thước, thời gian, retry.
8. **Bảo vệ concurrency:** predicate, CAS, unique key, serialization failure.
9. **Thiết kế idempotency:** commandId và cách đối soát unknown outcome.
10. **Tách external side effects:** outbox, event consumer, saga, payment gateway.
11. **Đo hiệu năng:** conflict rate, p99, capacity, hot partition, failover.
12. **Kiểm thử sự cố:** crash giữa commit, retry, rollback, replication lag.
13. **Ghi quyết định:** tại sao transaction hoặc saga đáp ứng invariant và SLO.

Một bản ghi quyết định mẫu:

~~~text
Feature: Create Order with inventory reservation
Invariant: do not reserve more stock than available

Source of truth:
    Order aggregate in Orders
    Inventory aggregate by (warehouseId, sku)

Transaction scope:
    multi-item within deployment if supported
    else use reservation saga with local atomic predicates

Concurrency:
    inventory available >= requested
    unique orderId and reservationId

Durability:
    configured DB commit/write concern verified
    external Payment API not in DB transaction

Idempotency:
    checkout commandId stored with outcome
    retry after unknown commit does not duplicate order

Events:
    Order and Outbox in same atomic boundary if possible
    consumer idempotent by eventId

Operational limits:
    item count, bytes, transaction lifetime, p99, hot SKU
    topology/version/region restrictions documented

Testing:
    two concurrent reservations
    network loss at commit
    worker crash and duplicate event
    region failover
~~~

## 27. Kiểm thử tính đúng đắn và giới hạn triển khai

Một test “transaction commit thành công khi không có tranh chấp” chỉ chứng minh happy path. Cần kiểm tra các trường hợp sau.

### 27.1. Concurrent stock reservation

Inventory available=5, hai request đồng thời giữ 4 và 3. Kỳ vọng chỉ một reservation được chấp nhận nếu không có quota khác; tổng số giữ không vượt 5.

### 27.2. Write skew

Hai bác sĩ đang trực, mỗi transaction tắt lịch của một người sau khi đọc người kia. Nếu bất biến yêu cầu ít nhất một người trực, hệ phải từ chối hoặc tuần tự hóa một transaction, hoặc mô hình phải buộc hai lệnh cạnh tranh trên cùng một nguồn.

### 27.3. Crash giữa transaction

Kill worker sau update đầu nhưng trước commit. Sau recovery không được tồn tại trạng thái nửa chừng đối với transaction đã có bảo đảm atomicity.

### 27.4. Timeout ngay lúc commit

Giả lập commit đã thành công nhưng ACK mất. Client retry cùng commandId không tạo Order hay Payment thứ hai.

### 27.5. Transaction callback chạy lại

Buộc một transaction xung đột khiến SDK retry callback. Kiểm tra không có email, webhook hoặc payment bị gọi nhiều lần vì callback chứa side effect.

### 27.6. Gần giới hạn kích thước/thời gian

Tạo Order có nhiều dòng, metadata lớn và index updates. Kiểm tra giới hạn transaction của sản phẩm và hành vi khi vượt; không để hệ crash hoặc commit một phần.

### 27.7. Hot partition

Cho nhiều nghìn checkout cùng tranh SKU flash sale. Đo transaction abort, p95/p99, throughput, throttling, retry load và áp dụng backpressure.

### 27.8. Replica lag và failover

Đọc sau commit ở các consistency mode khác nhau; mô phỏng leader failover và kiểm tra cam kết durability. Đừng chỉ xem API trả 200.

### 27.9. Multi-region concurrency

Nếu cho phép ghi từ hai region, gửi cùng lúc request tác động cùng invariant. Kiểm tra kết quả sau replication convergence, không chỉ kết quả tại từng region.

### 27.10. Saga compensation

Reserve SKU-A thành công, reserve SKU-B thất bại, worker chết trước khi release A. Sau restart phải tiếp tục/bù trừ idempotently và không để reservation kẹt mãi.

## 28. Monitoring và vận hành

| Chỉ số | Ý nghĩa |
|---|---|
| Transaction success/abort rate | Mức thành công và lỗi chung |
| Conflict/serialization failure rate | Concurrency có vượt khả năng không |
| Transaction duration p95/p99 | Giao dịch có quá dài không |
| Items/bytes per transaction | Có gần giới hạn API không |
| Lock/intent/snapshot wait | Phát hiện transaction dài gây nghẽn |
| Capacity units/throttling | Tải và chi phí transaction |
| Retry count và jitter effectiveness | Có retry storm không |
| Unknown commit outcomes | Số command cần đối soát |
| Hot partition/aggregate | Key nào tạo tranh chấp |
| Replication/read lag | Reader có thấy commit mới không |
| Outbox lag | Event downstream chậm bao lâu |
| Stuck saga/compensation | Workflow chưa hoàn tất |
| Invariant violations | Số dư sai, oversell, duplicate |

### 28.1. Phân loại lỗi thay vì gom một mã

Một failure `INSUFFICIENT_STOCK` là kết quả nghiệp vụ bình thường. `VERSION_CONFLICT` gợi ý nhiều writer hoặc read cũ. `TRANSACTION_TOO_LARGE` là lỗi thiết kế phạm vi. `THROTTLED` là giới hạn capacity. `UNKNOWN_COMMIT` cần đối soát. Mỗi loại có hướng xử lý khác, không nên retry tất cả cùng một chính sách.

### 28.2. Transaction lâu không chỉ ảnh hưởng chính nó

Một transaction giữ snapshot hoặc xung đột lâu có thể làm tăng latency của các transaction khác, giữ tài nguyên, làm chậm garbage collection hoặc tạo pressure lên log/replication tùy hệ. Theo dõi **oldest active transaction** và backlog tương ứng khi sản phẩm cung cấp metric.

## 29. Bài tập thực hành

### Bài 1 — Atomic document hay transaction?

Order gồm 12 item, total và coupon, mỗi lần cập nhật quantity phải tính lại total ngay. Đề xuất lưu cùng document hoặc tách item và giải thích khi nào cần transaction nhiều bản ghi.

### Bài 2 — Phạm vi partition

Một dịch vụ có Order và Inventory với hai partition key khác nhau; hệ chỉ hỗ trợ transaction trong một logical partition. Đề xuất ba hướng: đổi mô hình dữ liệu, đổi công nghệ transactional hoặc saga. Nêu tradeoff.

### Bài 3 — Write skew

Hai bác sĩ A/B cùng đang trực, quy tắc không được để cả hai nghỉ. Hai transaction cùng đọc snapshot ban đầu rồi sửa record riêng. Hãy chỉ ra lỗi và đề xuất serializable, shared invariant item hoặc cơ chế phù hợp.

### Bài 4 — DynamoDB

Thiết kế một transaction gồm update Inventory với condition, put Order nếu chưa tồn tại và put Outbox event. Liệt kê giới hạn thực tế cần tra trong version dịch vụ đang sử dụng, và cách xử lý ClientRequestToken.

### Bài 5 — MongoDB

Viết pseudo/Java sử dụng ClientSession để cập nhật hai collection trong transaction. Khi driver retry callback, vì sao không được gửi payment trong callback?

### Bài 6 — Firestore

Một transaction đọc Stock rồi tạo Order. Client có thể chạy lại callback. Hãy phân biệt logic tính toán thuần, read-before-write, và side effect cần đặt ngoài transaction.

### Bài 7 — Cosmos DB

Thiết kế Order và OrderLine cùng logical partition để dùng transactional batch. Nếu Inventory thuộc partition khác, cách nào bảo vệ không oversell? Vì sao không thể coi batch là transaction cross-partition?

### Bài 8 — Cassandra

So sánh LWT trên một partition với logged batch trải nhiều partition. Một chuyển tiền từ A sang B có thể dùng batch như transaction serializable được không? Nêu lý do và phương án thay thế.

### Bài 9 — Redis

Giải thích khác biệt giữa WATCH/MULTI/EXEC và transaction rollback của SQL. Một command trong EXEC gặp lỗi runtime thì điều gì cần được kiểm tra? Thiết kế idempotent reservation khi Redis có thể failover.

### Bài 10 — Unknown outcome

Client gửi COMMIT và timeout, nhưng transaction có thể đã commit. Thiết kế commandId, cách tra kết quả, unique key và quy trình retry không tạo duplicate.

### Bài 11 — Outbox

Order đã commit nhưng event chưa publish. Thiết kế outbox chung transaction nguồn và consumer idempotent. Nếu Outbox không nằm cùng partition mà DB chỉ hỗ trợ single-partition transaction, xử lý thế nào?

### Bài 12 — Benchmark hot key

10.000 checkout cùng giữ một SKU còn 100 sản phẩm. Hãy đo conflict rate, p99, capacity, retry attempts và so sánh transaction trực tiếp với queue/quota phân bổ.

### Bài 13 — Multi-region

Hai region có thể cùng ghi Inventory bằng condition local trong lúc replication trễ. Hãy phân tích vì sao kết quả sau convergence có thể không bảo vệ invariant và thiết kế single-writer/quota vùng.

### Bài 14 — Saga

Reserve Inventory thành công, Payment thất bại, worker chết trước khi release. Xây state machine, timeout, idempotent release, đối soát và tiêu chí nào để Order được xem CANCELED hoàn tất.

### Bài 15 — Hợp đồng sản phẩm

Nhóm đang chọn NoSQL cho tính năng chuyển tiền. Lập bảng hỏi nhà cung cấp/đội hạ tầng về topology, transaction scope, isolation, durability, size/time limits, failover, billing, SDK retry và công cụ kiểm thử. Không được kết luận chỉ từ câu “có ACID”.

---

**Kết luận:** Giao dịch nhiều bản ghi không phải một tính năng có/không đơn giản của “NoSQL”. Cần hỏi **transaction bao phủ những dữ liệu nào, có bảo vệ đúng bất biến và isolation cần thiết không, commit bền tới đâu, và những giới hạn về partition, region, kích thước, thời gian, contention và SDK là gì**. MongoDB, DynamoDB, Firestore, Cosmos DB, Couchbase, Cassandra/ScyllaDB, Redis và các transactional key–value store cung cấp những cơ chế khác nhau; không thể suy bảo đảm của hệ này cho hệ kia. Hãy ưu tiên **aggregate và atomic operation đúng ranh giới**, dùng transaction khi phạm vi phù hợp, và dùng **idempotency, outbox, saga, compensation và đối soát** khi quy trình vượt ra ngoài một transaction duy nhất. Sự đúng đắn phải được chứng minh bằng **kiểm thử cạnh tranh, lỗi commit, failover và đo đạc trên topology production tương ứng**, không chỉ bằng một ví dụ giao dịch thành công ở local.
