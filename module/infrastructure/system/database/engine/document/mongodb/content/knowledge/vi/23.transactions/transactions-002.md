# Điều kiện triển khai giao dịch trên replica set và sharded cluster trong MongoDB

## 1. Giao dịch nhiều document giải quyết vấn đề gì?

MongoDB bảo đảm **atomicity ở cấp một document** cho một thao tác ghi đơn lẻ. Nếu thông tin có thể nằm cùng một document, cập nhật bằng `$set`, `$inc`, `$push` hoặc một update pipeline thường đã đủ để giữ những field liên quan nhất quán.

Tuy nhiên, một số quy trình nghiệp vụ cần thay đổi **nhiều document, collection, database hoặc shard** theo nguyên tắc **cùng thành công hoặc cùng thất bại**:

- Chuyển tiền: trừ tài khoản A, cộng tài khoản B, ghi lịch sử chuyển tiền.
- Đặt hàng: tạo order, giữ tồn kho, lưu bản ghi trạng thái thanh toán nội bộ.
- Chuyển quyền sở hữu: cập nhật hai đối tượng và một bản ghi audit.
- Thay đổi nhiều aggregate có quan hệ ràng buộc, không được để dữ liệu ở trạng thái nửa chừng.

**Multi-document transaction** cho phép nhóm các thao tác phù hợp thành một đơn vị ACID. Nếu commit thành công, các thay đổi của transaction được chấp nhận như một tập; nếu abort, các thay đổi thuộc transaction không được giữ lại.

```text
Trước giao dịch
  Account A: 1000
  Account B:  500

Transaction chuyển 200
  1. A -= 200
  2. B += 200
  3. Insert transfer log

Commit thành công:
  A = 800, B = 700, có log

Abort:
  A = 1000, B = 500, không có log
```

Nhưng không thể chỉ viết `session.startTransaction()` rồi kỳ vọng giao dịch hoạt động trên mọi MongoDB server. **Loại deployment**, phiên bản và feature compatibility, topology, session, read/write concern, những operation được phép và giới hạn runtime đều quyết định khả năng triển khai.

> **Ý chính:** Giao dịch nhiều document của MongoDB chạy trên **replica set hoặc sharded cluster được cấu hình hợp lệ**, không phải một `mongod` standalone. Với sharded cluster, giao dịch có thể trải qua nhiều shard, nhưng chi phí và các ràng buộc lớn hơn.

Bài này tập trung vào **điều kiện triển khai** và cách kiểm tra các điều kiện ấy trong hệ thống thật, thay vì chỉ trình bày cú pháp start/commit.

---

## 2. Ma trận hỗ trợ theo kiến trúc

| Môi trường | Giao dịch nhiều document | Điều cần lưu ý |
| --- | --- | --- |
| Một `mongod` **standalone** | **Không hỗ trợ** | Dù mọi collection trên cùng server, vẫn không phải replica set. |
| **Replica set một node** dành cho development | **Có thể dùng để thử nghiệm** | Không có tính sẵn sàng cao; không đại diện hành vi failover production. |
| Replica set nhiều node | **Hỗ trợ** | Phải có topology, session, read/write concern và runtime phù hợp. |
| Sharded cluster với các shard hợp lệ | **Hỗ trợ** | Truy cập qua `mongos`; có thể chạy trên một hoặc nhiều shard. |
| Một shard replica set nằm trong sharded cluster | Có khả năng tham gia transaction | Client ứng dụng phải dùng router/topology sharded thích hợp. |
| Replica set có arbiter | Một số transaction có thể chạy | Có giới hạn đặc biệt với transaction chạm nhiều shard hoặc đổi shard key. |
| Sharded cluster có shard với `writeConcernMajorityJournalDefault: false` | **Không hỗ trợ transactions** | Cấu hình lưu bền/majority của shard không đáp ứng điều kiện. |
| MongoDB Atlas hoặc managed MongoDB | Phụ thuộc loại cluster/tier và server | Kiểm tra dịch vụ, topology, version và quyền thao tác thay vì tự `rs.initiate()`. |

**Một-node replica set** là phương pháp hữu ích để local development có transaction, nhưng không nên gọi nó là “môi trường production tương đương replica set ba node”. Nó không có majority độc lập, không có failover thực và không mô phỏng được commit phân tán giữa nhiều shard.

### 2.1. Các mốc hỗ trợ lịch sử

| Hình thức | MongoDB version xuất hiện | FCV tối thiểu được tài liệu nêu |
| --- | --- | --- |
| Multi-document transaction trên replica set | **4.0** | **4.0** |
| Multi-document transaction trên sharded cluster | **4.2** | **4.2** |

FCV viết tắt của **featureCompatibilityVersion**. Nó kiểm soát việc kích hoạt các hành vi/tính năng tương thích của deployment, đặc biệt có ý nghĩa trong quá trình rolling upgrade.

Trên các phiên bản MongoDB đang được hỗ trợ, transaction là tính năng chuẩn, nhưng **môi trường thực tế vẫn phải cấu hình đúng**. Đừng chỉ xem `mongod --version` rồi bỏ qua FCV và topology.

---

## 3. Kiểm tra server version và FCV

Trước khi cấu hình application transaction, kiểm tra:

```javascript
db.version();
```

Để xem FCV nếu tài khoản có quyền:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Với replica set hoặc sharded cluster đang nâng cấp theo giai đoạn, phải xác nhận **toàn deployment** tương thích, không chỉ một node tình cờ được kết nối.

### 3.1. Vì sao FCV quan trọng?

Ví dụ, một replica set đã được nâng binary nhưng FCV vẫn ở mức cũ để bảo đảm khả năng rollback upgrade. Nếu application bật một tính năng đòi FCV cao hơn, lỗi có thể xuất hiện dù binary server nhìn có vẻ đủ mới.

Trong tài liệu transaction, ngưỡng tối thiểu lịch sử là:

```text
Replica set     : FCV >= 4.0
Sharded cluster : FCV >= 4.2
```

Khi vận hành MongoDB hiện đại, kiểm tra **compatibility matrix theo bản server đang dùng**; không tự đặt FCV về 4.0/4.2. Mục tiêu của bảng là hiểu điều kiện tối thiểu lịch sử, không phải khuyến nghị hạ version.

### 3.2. FCV không phải điều kiện duy nhất

Ngay cả khi version/FCV thỏa:

- Server có thể vẫn là **standalone**.
- Sharded cluster có thể chứa shard với cấu hình journaling/majority không được hỗ trợ.
- Client có thể kết nối **trực tiếp shard** thay vì `mongos`.
- Application có thể dùng sai session hoặc read preference.
- Transaction có thể bị abort do thời gian, lock, DDL hoặc write conflicts.

Đó là lý do cần một checklist triển khai toàn diện.

---

## 4. Vì sao standalone `mongod` không chạy transaction nhiều document?

Một server được khởi động không có replica set topology là standalone:

```text
Application
    |
    v
mongod standalone
    |
    +-- collection A
    +-- collection B
```

Nó có thể thực hiện nhiều thao tác ghi, nhưng **không nhận transaction nhiều document theo session như replica set**. Lỗi thường được thấy khi dùng driver transaction trên standalone liên quan tới `Transaction numbers are only allowed on a replica set member or mongos`.

**Không được lẫn lộn hai khái niệm:**

1. `updateOne` trên một document của standalone có atomicity ở cấp document.
2. `startTransaction` rồi cập nhật nhiều document là multi-document transaction và cần deployment hỗ trợ.

### 4.1. Phát hiện môi trường standalone

Kết nối bằng `mongosh`:

```javascript
db.hello();
```

Với replica set, response có thông tin về set name/role của member. Với standalone, không có topology replica set tương ứng.

Có thể xem thông tin cấu hình replica set trong môi trường được quản lý:

```javascript
rs.status();
rs.conf();
```

Trên standalone, các lệnh replica set này không hoạt động như trên member của replica set; đây là tín hiệu deployment cần được thiết lập lại.

### 4.2. Local development: dùng replica set một node

Ví dụ khái niệm với một `mongod` local **không phải production**:

```shell
mongod --replSet rsDev --dbpath /data/mongodb/rsDev --port 27017 --bind_ip 127.0.0.1
```

Sau khi server chạy, kết nối qua `mongosh` và khởi tạo:

```javascript
rs.initiate({
  _id: "rsDev",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
});
```

Chờ member trở thành primary:

```javascript
db.hello();
rs.status();
```

Application:

```text
mongodb://localhost:27017/?replicaSet=rsDev
```

Nếu môi trường dùng Docker/network nhiều namespace, hostname trong `rs.initiate()` phải **phân giải được từ client và các member liên quan**. Dùng `localhost` trong một container không mặc định trỏ tới MongoDB ở container khác.

**Ví dụ trên không cấu hình security production.** Ở môi trường thật cần authentication, authorization, TLS, internal authentication, hostname phù hợp và quy trình quản lý secrets. Đừng khởi tạo public-facing replica set chỉ để tránh lỗi transaction.

---

## 5. Replica set production cần những thành phần nào?

Một topology đơn giản có ba data-bearing members:

```text
             Replica set rsOrders

            +---------------------+
            | PRIMARY   db1       |
            | SECONDARY db2       |
            | SECONDARY db3       |
            +---------------------+
                      ^
                      |
              MongoDB Driver
                      |
                Application
```

Thông thường, application kết nối bằng URI liệt kê các host và set name:

```text
mongodb://db1.example.net:27017,db2.example.net:27017,db3.example.net:27017/
  ?replicaSet=rsOrders
```

URI được chia dòng để dễ đọc; URI thật phải là một chuỗi liên tục. Hãy thêm TLS/auth theo môi trường.

### 5.1. Những điều kiện vận hành cần xác nhận

1. Replica set đã khởi tạo và có **primary** hợp lệ.
2. Các member có connectivity, replication health và config thống nhất.
3. Version/FCV đủ để chạy transaction.
4. Server hỗ trợ sessions và các storage engine/replication behavior cần thiết.
5. Write concern được chọn có khả năng nhận acknowledgment trong topology.
6. Tài khoản có quyền CRUD cần thiết trên các collection thuộc transaction.
7. Application dùng MongoDB driver hỗ trợ sessions/transactions.
8. Thời gian transaction, tài nguyên, locking và oplog window được giám sát.
9. Các collection/index được chuẩn bị trước để tránh DDL trong transaction.
10. Team có phương án xử lý failover và retry an toàn.

### 5.2. Replica set không làm transaction miễn phí

Mọi transaction thường có chi phí lớn hơn một update nguyên tử trên một document:

- Server giữ snapshot/trạng thái transaction.
- Nhiều document có thể bị khóa ở mức thích hợp hoặc tạo write conflicts.
- Commit phải đạt điều kiện write concern.
- Những transaction lâu có thể giữ pinned snapshot và tăng áp lực cache/history.
- Khi primary step down hoặc connection đổi, application phải xử lý lỗi transient.

Mục tiêu không phải “bật transaction cho mọi lệnh ghi” mà là bảo vệ những **bất biến liên-document thật sự cần atomicity**.

---

## 6. Kiến trúc sharded cluster và vị trí chạy transaction

Một sharded cluster thường có:

- **`mongos`:** router nhận command từ ứng dụng và định tuyến tới shard.
- **Config server replica set (CSRS):** giữ metadata của sharded cluster.
- **Các shard:** mỗi shard thường là một **replica set** lưu dữ liệu của một phần collection.
- **Shard key:** xác định cách phân phối/định tuyến document giữa các shard.

```text
                         Application
                              |
                              v
                            mongos
                         /    |    \
                        /     |     \
              Shard 1 RS   Shard 2 RS   Shard 3 RS
               P + S + S    P + S + S    P + S + S
                        \      |      /
                         Config Server RS
```

**Ứng dụng kết nối tới `mongos`, không trực tiếp một `mongod` của shard để chạy transaction toàn cluster.** Router biết metadata phân bố và điều phối các thao tác tới shard có liên quan.

### 6.1. Single-shard transaction

Một transaction chạm dữ liệu chỉ trên **một shard**:

```text
Client -> mongos -> Shard 1 RS
                       |
                     Commit
```

Chi phí thường gần với transaction trên replica set tương ứng, cộng phần định tuyến qua mongos.

Ví dụ một collection `orders` được shard theo `tenantId`. Nếu toàn bộ thao tác trong transaction đều filter cùng `tenantId` và dữ liệu cần chạm nằm cùng shard, transaction có thể chỉ cần một shard.

Điều này **không tự xảy ra** chỉ vì bạn dùng cùng database. Cần biết shard key của từng collection và dữ liệu đang được phân phối thế nào.

### 6.2. Multi-shard transaction

Một transaction chạm dữ liệu trên **nhiều shard**:

```text
                    mongos
                   /     \
                  v       v
             Shard 1   Shard 2
                 \       /
                  \     /
          Transaction coordination
                  |
                  v
          Commit/abort nhất quán
```

Giao dịch nhiều shard có thêm bước **điều phối commit phân tán**, sử dụng cơ chế phối hợp theo kiểu **two-phase commit** để đảm bảo các shard tham gia đạt cùng quyết định commit/abort.

Hệ quả:

- Có thêm network round trips giữa router, coordinator và shards.
- Commit có thể chậm hơn so với single-shard transaction.
- Thời gian commit chịu ảnh hưởng của shard chậm hoặc lỗi mạng.
- Retry/unknown commit result cần được xử lý đúng.
- Không thể coi các shard như các MongoDB standalone độc lập rồi tự commit tuần tự từ client.

Theo tài liệu MongoDB, **transaction chỉ target một shard có thể đạt hiệu năng tương tự replica-set transaction**, còn transaction ảnh hưởng nhiều shard có overhead cao hơn.

---

## 7. Điều kiện đặc biệt với sharded cluster

Để triển khai giao dịch nhiều document trên sharded cluster, kiểm tra ít nhất các điều kiện sau:

| Điều kiện | Vì sao cần |
| --- | --- |
| MongoDB/FCV đáp ứng transaction sharded | Hỗ trợ bắt đầu từ MongoDB/FCV 4.2 trong lịch sử. |
| Ứng dụng đi qua `mongos` | Router có metadata và điều phối transaction xuyên shard. |
| Các shard có replica set hợp lệ | Ghi/đồng bộ/commit phải dựa trên thành viên đủ khả năng. |
| `writeConcernMajorityJournalDefault` không bị đặt `false` ở shard | Cluster không thể chạy transaction nếu có shard không hỗ trợ điều kiện này. |
| Multi-shard transaction không chạm shard có arbiter | Transaction có write trải nhiều shard sẽ lỗi/abort nếu operation chạm shard replica set có arbiter. |
| Shard key/index đáp ứng CRUD và uniqueness | Targeting và global uniqueness có các giới hạn riêng trong sharding. |
| Những collection cần ghi đã được chuẩn bị | Không được tạo collection mới trong cross-shard write transaction. |
| Monitoring và retry/timeout phù hợp | Chunk migration, DDL, lock conflict và failover có thể abort transaction. |

### 7.1. `writeConcernMajorityJournalDefault`

Một hạn chế đặc biệt: MongoDB **không cho chạy transaction trên sharded cluster có shard mà `writeConcernMajorityJournalDefault` là `false`**.

Ví dụ tài liệu nêu tình huống một shard có voting member dùng **in-memory storage engine**, khiến setting đó không đáp ứng yêu cầu.

Không nên suy ra “mọi replica set bắt buộc tất cả member phải dùng WiredTiger” từ giới hạn này. Điều kiện cần xét là **cấu hình thực tế của deployment**, nhất là journaling/majority commit behavior của từng shard.

Một số phần trong commit của sharded transaction sử dụng `{w: "majority", j: true}` ngay cả khi transaction-level write concern được khai báo khác. Đây là lý do hạ write concern về `w: 1` **không xóa được mọi yêu cầu bền vững khi commit xuyên shard**.

### 7.2. Arbiter là ràng buộc đặc biệt

Arbiter chỉ bỏ phiếu, không lưu dữ liệu. Theo MongoDB:

- Transaction đổi **shard key** không được dùng nếu replica set có arbiter.
- **Transaction có thao tác ghi trải nhiều shard** sẽ error và abort nếu bất kỳ operation trong transaction đọc/ghi tới shard có arbiter.

Không nên thiết kế một multi-shard transaction rồi hy vọng arbiter “cũng có thể xác nhận phần dữ liệu”, vì arbiter không có bản sao data cần thiết.

### 7.3. Tài nguyên từng shard vẫn quan trọng

Dù đã có cấu hình hợp lệ, shard chậm, thiếu disk IOPS hoặc replication lag lớn vẫn có thể làm transaction mất nhiều thời gian, timeout hoặc bị abort. Phải quan sát cả router và những shards thực sự tham gia giao dịch.

---

## 8. Session là bắt buộc

MongoDB multi-document transaction gắn với một **logical session**. Driver quản lý thông tin session và transaction, ví dụ `lsid`/transaction number ở protocol.

Trong Java:

```java
try (ClientSession session = mongoClient.startSession()) {
    session.startTransaction();

    collectionA.insertOne(session, documentA);
    collectionB.updateOne(
        session,
        Filters.eq("_id", someId),
        Updates.set("status", "PAID")
    );

    session.commitTransaction();
}
```

Đây chỉ là khung minh họa; phần xử lý lỗi/abort/timeout được trình bày chi tiết hơn ở các mục sau.

### 8.1. Mọi operation phải nhận đúng session

Sai:

```java
session.startTransaction();

orders.insertOne(session, order);
inventory.updateOne(
    Filters.eq("_id", sku),
    Updates.inc("available", -1)
); // Không truyền session: có thể chạy ngoài transaction.

session.commitTransaction();
```

Đúng:

```java
session.startTransaction();

orders.insertOne(session, order);
inventory.updateOne(
    session,
    Filters.eq("_id", sku),
    Updates.inc("available", -1)
);

session.commitTransaction();
```

Nếu một operation không dùng session tương ứng, nó **không thuộc transaction**. Kết quả có thể là trạng thái không nhất quán dù `commitTransaction()` báo thành công.

### 8.2. Mỗi session chỉ có một transaction đang mở

Không mở hai transaction đồng thời trên cùng một `ClientSession`. Driver session còn gắn với đúng `MongoClient` đã tạo ra nó; không dùng session của client A với collection được lấy từ client B.

### 8.3. Không chạy song song operation trong cùng transaction

Java driver không hỗ trợ thao tác song song trong một transaction. Không truyền cùng session vào hai `CompletableFuture` hoặc nhiều thread chạy đồng thời để “tăng tốc”.

```text
Đúng:
  read -> update A -> update B -> insert audit -> commit

Không phù hợp:
  session -> async update A
          -> async update B (cùng lúc)
          -> commit không đợi đúng trật tự
```

Nếu cần xử lý song song workload không yêu cầu transaction chung, phải thiết kế độc lập phù hợp, không chia sẻ cùng một session.

---

## 9. Vòng đời transaction

```text
startSession()
      |
      v
startTransaction()
      |
      v
CRUD operation 1
      |
      v
CRUD operation 2
      |
      v
Kiểm tra invariant
      |
      +-----------------+
      |                 |
   Thành công         Có lỗi / timeout
      |                 |
      v                 v
commitTransaction()  abortTransaction()
      |                 |
      v                 v
   COMMITTED           ABORTED
      |
      v
close session
```

Transaction có ba kết quả thực tế quan trọng:

1. **Commit xác nhận thành công:** caller được thông báo transaction đã được commit theo write concern.
2. **Abort:** những thay đổi thuộc transaction không có hiệu lực lâu dài.
3. **Commit result không rõ (`UnknownTransactionCommitResult`):** client không biết chắc commit đã thành công hay chưa. **Không được mặc định transaction đã abort**.

Trạng thái thứ ba đặc biệt quan trọng khi network bị mất đúng thời điểm commit. Driver có thể cần retry **commit operation**, thay vì chạy lại toàn bộ nghiệp vụ.

---

## 10. Read preference trong transaction

MongoDB yêu cầu **transaction có thao tác đọc** dùng read preference **`primary`**. Các operation của một transaction phải được định tuyến tới member phù hợp của replica set.

Ví dụ cấu hình rõ:

```java
TransactionOptions options = TransactionOptions.builder()
    .readPreference(ReadPreference.primary())
    .build();
```

**Không đặt `secondaryPreferred()` chỉ vì các query read-only khác trong ứng dụng thường đọc secondary.** Trong transaction có đọc dữ liệu để quyết định cập nhật, cần read preference đúng.

### 10.1. Read preference đặt ở đâu?

MongoDB driver có thể kế thừa read preference từ:

1. Transaction options.
2. Session.
3. MongoClient settings.

Để tránh tình huống client toàn cục đang dùng `secondaryPreferred()` rồi transaction vô tình kế thừa không phù hợp, nên **đặt `ReadPreference.primary()` ngay trong transaction options**.

### 10.2. Không dùng `readPreference=secondary` để “giảm tải primary”

Đọc transaction trên secondary không phải mẹo tăng hiệu năng được hỗ trợ cho transaction chứa read operations. Nếu một báo cáo chỉ cần eventual consistency, có thể chạy query ngoài transaction trên secondary, không nhất thiết phải ép nó vào ACID transaction.

---

## 11. Read concern cho transaction

MongoDB hỗ trợ các mức read concern chính cho transaction: `"local"`, `"majority"` và `"snapshot"`.

| Read concern | Ý nghĩa cần chú ý | Đặc biệt với sharded cluster |
| --- | --- | --- |
| `"local"` | Đọc dữ liệu theo góc nhìn local, có khả năng rollback nếu chưa majority-committed. | Không bảo đảm snapshot thống nhất trên nhiều shard. |
| `"majority"` | Gắn với dữ liệu majority-committed khi commit được thực hiện với majority theo các điều kiện MongoDB quy định. | Không bảo đảm cùng một snapshot giữa các shard. |
| `"snapshot"` | Đọc từ snapshot nhất quán theo contract, và với commit majority có bảo đảm majority-committed. | **Là mức cần dùng nếu yêu cầu snapshot đồng bộ giữa nhiều shard.** |

### 11.1. Vì sao `"snapshot"` thường được lựa chọn?

Trong nghiệp vụ chuyển tiền, không muốn đọc account A ở một mốc và account B ở mốc không nhất quán khi dữ liệu có thể trải các shard khác nhau.

Cấu hình ứng viên:

```java
TransactionOptions options = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .readPreference(ReadPreference.primary())
    .build();
```

`ReadConcern.SNAPSHOT` trong transaction trên sharded cluster cung cấp một snapshot dữ liệu được đồng bộ giữa các shard. `"majority"` read concern **không đồng nghĩa** với một snapshot đồng bộ như vậy.

### 11.2. Snapshot và majority write concern có quan hệ

Tài liệu MongoDB nói rõ: bảo đảm snapshot của **majority-committed data** phụ thuộc vào transaction **commit với write concern `"majority"`**.

Nếu commit với `w: 1`, read concern `"snapshot"` **không bảo đảm** những document đọc được đều là majority-committed theo semantics tương ứng.

Vì vậy, không nên trình bày chỉ cần viết `readConcern: "snapshot"` là đã có đầy đủ mọi bảo đảm durability cho bất kỳ cấu hình commit nào.

### 11.3. Dữ liệu không phải lúc nào cũng là “mới nhất tại thời điểm hiện tại”

Snapshot isolation ổn định góc nhìn đọc trong transaction, nhưng một snapshot có thể **không phản ánh update mới hơn từ bên ngoài**. Cần tách:

- **Snapshot consistency:** các thao tác đọc trong transaction nhìn dữ liệu theo một góc nhìn nhất quán.
- **Freshness:** nhìn được cập nhật mới nhất ở thời điểm yêu cầu hay không.

Với nghiệp vụ cần ngăn một concurrent update làm thay đổi quyết định, phải kết hợp thao tác ghi có điều kiện, unique constraints, và xử lý write conflicts; không dựa vào đọc snapshot đơn thuần như một khóa toàn hệ thống.

---

## 12. Write concern phải đặt ở transaction level

Transaction sử dụng **transaction-level write concern khi commit**. Những operation ghi bên trong transaction **không được chỉ định write concern riêng**.

Sai:

```javascript
// Không đặt per-operation write concern bên trong transaction.
orders.insertOne(
  { _id: "O100", status: "NEW" },
  { writeConcern: { w: 1 } }
);
```

Ví dụ shell ở trên chỉ để minh họa cấu hình sai khi đặt trong transaction; tùy API driver/shell cần truyền đúng session để gắn lệnh vào transaction.

Đúng về mặt ý tưởng:

```javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" },
  readPreference: "primary"
});

// Thực hiện các CRUD bằng session; không chỉ định
// write concern riêng cho từng CRUD.
```

### 12.1. `w: 1` và `"majority"` khác nhau

| Commit write concern | Điều được chờ | Cần chú ý |
| --- | --- | --- |
| `w: 1` | Primary acknowledgment theo ngữ nghĩa w=1. | Transaction có thể bị rollback khi failover trong những điều kiện MongoDB quy định. |
| `w: "majority"` | Majority acknowledgment ở các voting data-bearing members phù hợp. | Độ bền cao hơn, có thể tăng latency, phụ thuộc replication health. |

**Không được suy ra `commitTransaction()` trả success với `w: 1` đồng nghĩa dữ liệu đã tồn tại ở đa số replica set.**

### 12.2. Default write concern phụ thuộc phiên bản và topology

Trên MongoDB hiện đại, các default được MongoDB quy định theo version, và cấu hình có arbiter có thể làm implicit default khác. Để giảm mơ hồ, các nghiệp vụ tài chính hoặc dữ liệu quan trọng nên **đặt write concern tường minh** theo yêu cầu hệ thống.

Không mặc định mọi cluster đều có `"majority"` chỉ vì code không khai báo `w`.

### 12.3. Commit trên sharded cluster có những bước majority/journal riêng

Với transaction có nhiều shard, một số phần của commit phối hợp sử dụng `{w: "majority", j: true}` bất kể transaction-level write concern. Điều này giải thích vì sao commit phân tán không thể được rút gọn thành hai lệnh ghi đơn giản cộng lại.

---

## 13. Cấu hình transaction options trong `mongosh`

Ví dụ transfer được minh họa trên collection `accounts` đã tồn tại, hai tài khoản có số dư theo **minor currency units**:

```javascript
// Chuẩn bị dữ liệu ngoài transaction, trên database thử nghiệm:
db.accounts.insertMany([
  { _id: "A", balanceMinor: NumberLong("100000") },
  { _id: "B", balanceMinor: NumberLong("50000") }
]);
```

Giao dịch:

```javascript
const session = db.getMongo().startSession();

try {
  const txnDb = session.getDatabase(db.getName());
  const accounts = txnDb.getCollection("accounts");
  const transfers = txnDb.getCollection("transfers");

  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" },
    readPreference: "primary"
  });

  const debit = accounts.updateOne(
    {
      _id: "A",
      balanceMinor: { $gte: NumberLong("20000") }
    },
    {
      $inc: { balanceMinor: NumberLong("-20000") }
    }
  );

  if (debit.matchedCount !== 1) {
    throw new Error("Không đủ số dư hoặc thiếu tài khoản A");
  }

  const credit = accounts.updateOne(
    { _id: "B" },
    { $inc: { balanceMinor: NumberLong("20000") } }
  );

  if (credit.matchedCount !== 1) {
    throw new Error("Tài khoản B không tồn tại");
  }

  transfers.insertOne({
    _id: "TRANSFER-EXAMPLE-1",
    from: "A",
    to: "B",
    amountMinor: NumberLong("20000")
  });

  session.commitTransaction();
} catch (err) {
  if (session.inTransaction()) {
    session.abortTransaction();
  }
  throw err;
} finally {
  session.endSession();
}
```

**Điều kiện để ví dụ chạy đúng:**

- Đã kết nối tới replica set hoặc `mongos`, không phải standalone.
- Hai collection `accounts`, `transfers` được tạo trước, nhất là nếu transaction có thể chạm nhiều shard.
- Mọi operation dùng các collection lấy từ `session.getDatabase()`.
- Tài khoản A/B đã tồn tại, số dư có kiểu tương thích.
- Chưa chạy cùng `_id` transfer trước đó; insert `_id` trùng sẽ gây lỗi.
- Không dùng script minh họa này như cổng thanh toán production; còn thiếu idempotency API, bảo vệ giá trị đầu vào, audit policy và xử lý unknown commit result ở caller.

Trong một ứng dụng thật, dùng **callback API** hoặc vòng retry có kiểm soát thay vì tự giả định một lần start/commit luôn thành công. Mục Java bên dưới đưa ra cách quản lý transaction được MongoDB driver hỗ trợ.

### 13.1. Kiểm tra sau commit

```javascript
db.accounts.find(
  { _id: { $in: ["A", "B"] } }
).sort({ _id: 1 });

db.transfers.findOne({
  _id: "TRANSFER-EXAMPLE-1"
});
```

Không cố “kiểm thử atomicity” bằng cách ngắt kết nối/xóa database production. Hãy dùng bộ test integration riêng có cả ca abort, conflict và failover.

---

## 14. Chuẩn bị collection và index: hạn chế DDL trong transaction

MongoDB cho phép một số thao tác tạo collection/index **bên trong transaction** theo điều kiện giới hạn, nhưng việc này không có nghĩa mọi DDL đều được hỗ trợ.

### 14.1. Những thao tác được phép có điều kiện

Có thể tạo collection hoặc index trong transaction nếu **không phải cross-shard write transaction**.

Với thao tác tạo index:

- Chỉ cho phép tạo index trên **collection chưa tồn tại** (collection có thể được tạo trong transaction) hoặc **collection mới, trống, được tạo trước đó trong cùng transaction**.
- Những lệnh tạo index trên existing index có thể được chấp nhận như một thao tác kiểm tra tồn tại theo quy tắc API.
- **Explicit create collection/index yêu cầu transaction read concern `"local"`**.

Điều đó không tương thích với việc chọn `"snapshot"` cho mọi trường hợp nếu transaction còn cần thực hiện explicit DDL.

### 14.2. Không được tạo collection mới trong cross-shard write transaction

Ví dụ:

```text
Shard A:
  write vào collection orders đã tồn tại.

Shard B:
  insert tới collection auditLogs chưa tồn tại,
  khiến collection được tạo ngầm.

Cả hai nằm trong cùng một transaction.
```

MongoDB **không cho phép** kiểu tạo collection trong cross-shard write transaction như vậy. Transaction có thể fail.

**Khuyến nghị triển khai:** thực hiện **schema migration/index creation trước khi ứng dụng bắt đầu transaction**, xác nhận collection/index đã có và metadata sharded phù hợp.

### 14.3. DDL chạy song song có thể làm transaction abort

Một transaction đang giữ tài nguyên collection; người vận hành chạy `createIndex`/`renameCollection`/`drop` cùng lúc. DDL có thể phải chờ transaction, và các transaction mới có thể bị block bởi DDL pending rồi hết lock timeout.

Với sharded cluster, chunk migration/DDL còn có giai đoạn critical section. Tùy thứ tự đan xen, transaction có thể **abort khi commit** vì metadata phân vùng đổi.

Không nên bắt tất cả lỗi DDL/migration rồi retry vô hạn. Cần kế hoạch change window, retry budget và quan sát lock wait.

---

## 15. Các operation bị hạn chế hoặc không được phép

Không phải mọi MongoDB command có thể chạy trong transaction.

| Operation/nhóm | Điều kiện hoặc giới hạn |
| --- | --- |
| CRUD thường trên collection hỗ trợ | Dùng được khi đủ session/quyền/concern. |
| `createCollection`, `createIndex` | Chỉ trong những trường hợp tạo collection/index được hỗ trợ, và explicit DDL cần `readConcern: "local"`. |
| Tạo collection trong cross-shard write transaction | **Không cho phép**. |
| `listCollections`, `listIndexes` | Không được dùng trong transaction. |
| `getParameter`, `createUser` và nhiều command quản trị | Không được phép trong transaction. |
| `explain()` | Không được dùng như một operation trong transaction. |
| `$out`, `$merge` trong aggregation | Không dùng trong transaction. |
| Ghi vào **capped collection** | Không cho phép. |
| Đọc capped collection bằng snapshot read concern | Bị hạn chế theo version, MongoDB 5.0+ không hỗ trợ trường hợp này. |
| Đọc/ghi vào collection thuộc `config`, `admin`, `local` database | Không được dùng trong transaction. |
| Ghi vào `system.*` collection | Không được dùng trong transaction. |
| `getMore` trên cursor tạo ngoài transaction, hoặc ngược lại | Không được làm lẫn ranh giới transaction. |
| `$graphLookup` target một sharded collection | Bị hạn chế trong transaction. |
| Parallel operations dùng cùng một session/transaction | Driver không hỗ trợ. |

### 15.1. Lệnh `count` và `distinct`

Một số helper/command cũ có thể bị hạn chế trong transaction. Khi cần đếm theo điều kiện, có thể dùng aggregation như:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $count: "total" }
]);
```

Để lấy giá trị duy nhất, có thể dùng `$group` + `$addToSet` theo ngữ nghĩa phù hợp. Phải gắn session và tránh các stage không được hỗ trợ nếu chạy trong transaction.

### 15.2. Nên làm migration trước giao dịch

Nếu cần unique index bảo vệ `transferId` hay business key, tạo nó **trước khi xử lý transaction production**. Không đợi đến request đầu tiên rồi thực hiện DDL trong transaction, vì dễ gặp lock contention, incompatibility read concern và những giới hạn cross-shard.

---

## 16. Shard key và cách tránh transaction chạm nhiều shard

Transaction trải nhiều shard có thể cần thiết, nhưng nên tránh nếu một thiết kế dữ liệu hợp lý cho phép gom những thao tác liên quan vào **cùng shard**.

Ví dụ collection được shard theo:

```javascript
sh.shardCollection(
  "shop.orders",
  { tenantId: 1, orderId: 1 }
);
```

Đây là ví dụ cấu hình để hiểu key. Việc chọn shard key thực tế còn đòi phân tích cardinality, phân phối dữ liệu, targeting và index. Không chạy `sh.shardCollection` mà chưa chuẩn bị collection/index/topology.

### 16.1. Query có shard key thường target tốt hơn

```javascript
db.orders.findOne({
  tenantId: "T100",
  orderId: "O900"
});
```

Khi chứa shard key phù hợp, `mongos` có cơ sở định tuyến thao tác tới shard liên quan, thay vì broadcast rộng.

Nếu filter chỉ có:

```javascript
db.orders.findOne({
  status: "PENDING"
});
```

router có thể phải gửi operation tới nhiều shard, làm tăng số participant và chi phí transaction.

### 16.2. Shard key chỉ là một phần của thiết kế transaction

Nếu collection A shard theo `tenantId`, collection B shard theo `customerId`, cùng một quy trình cập nhật A và B **không bảo đảm** nằm cùng shard. Để có single-shard transaction, cần xác nhận vị trí dữ liệu của tất cả collection được chạm, không chỉ một filter có `tenantId`.

### 16.3. Unique index trong sharded collection

MongoDB có giới hạn uniqueness xuyên shard. Nói chung, unique index cho sharded collection phải chứa **đầy đủ shard key làm tiền tố** theo các điều kiện được hỗ trợ.

Ví dụ:

```javascript
// Nếu collection sharded theo tenantId:
db.transfers.createIndex(
  { tenantId: 1, transferId: 1 },
  { unique: true }
);
```

Ràng buộc này bảo đảm uniqueness trên cặp `(tenantId, transferId)` theo mô hình. Nó **không bảo đảm transferId duy nhất toàn hệ thống** nếu các tenant khác nhau có cùng transferId.

Trước khi đưa idempotency key vào sharded collection, xác định phạm vi uniqueness yêu cầu: toàn hệ thống, theo tenant, theo customer hay theo yêu cầu API. Transaction **không tự bổ sung global unique constraint** trên một field ngoài shard key.

---

## 17. Transaction có thể thay đổi shard key không?

Trên các phiên bản MongoDB hỗ trợ, việc cập nhật shard key có các điều kiện riêng và thường được thực hiện qua những thao tác định danh document thích hợp, trong transaction hoặc retryable write tùy trường hợp.

Điểm cần phân biệt:

- **Update field bình thường** của sharded document không giống **thay đổi shard key** làm document có thể chuyển shard.
- Thay đổi shard key có yêu cầu routing, filter và atomicity riêng.
- **Không được thay đổi shard key trong transaction nếu replica set liên quan có arbiter** theo hạn chế MongoDB.
- Nếu mutation dẫn đến chuyển shard, chi phí và khả năng gặp lỗi/retry có thể tăng.

Không nên xem việc sửa shard key là update thông thường rồi tùy tiện dùng `$set`. Với nghiệp vụ đổi tenant/partition hoặc di chuyển dữ liệu, cần thiết kế lại route và kiểm tra tài liệu đúng phiên bản trước.

---

## 18. Thời gian sống của transaction

Theo tài liệu MongoDB, **mặc định transaction phải hoàn thành trong dưới một phút**. Tham số server:

```text
transactionLifetimeLimitSeconds
```

điều khiển giới hạn thời gian. Transaction vượt giới hạn được coi là hết hạn và có thể bị abort bởi quá trình cleanup định kỳ.

### 18.1. Tại sao transaction dài gây hại?

Một transaction giữ snapshot và trạng thái liên quan càng lâu thì càng có thể:

- Tăng bộ nhớ/cache pressure.
- Giữ lịch sử dữ liệu cần thiết cho snapshot.
- Giữ lock/resource trong những thời đoạn phù hợp.
- Tăng xung đột với write hoặc DDL khác.
- Làm chậm chunk migration trong sharded cluster.
- Tăng nguy cơ hết timeout/abort khi có failover.

Không đưa thao tác gọi HTTP service bên ngoài, chờ người dùng bấm xác nhận, gửi email hoặc xử lý file lớn **vào giữa** transaction nếu chúng khiến transaction mở lâu.

### 18.2. Thay đổi lifetime trong sharded cluster

Nếu cần thay `transactionLifetimeLimitSeconds` trong sharded cluster, MongoDB yêu cầu cấu hình trên **tất cả thành viên của các shard replica set** tương ứng theo hướng dẫn.

Tăng timeout không làm transaction tự nhanh hơn hoặc an toàn hơn. Ưu tiên giảm phạm vi transaction, tối ưu index, tránh network call và chia công việc nghiệp vụ có thể tách được.

### 18.3. `maxTimeMS`, `wtimeout` và transaction lifetime khác nhau

- **Transaction lifetime:** giới hạn thời gian transaction sống; hết hạn có thể bị abort.
- **`maxTimeMS` trên `commitTransaction`:** giới hạn thời gian commit theo hành vi server; trong sharded cluster phải cân nhắc transaction lifetime.
- **Write concern timeout (`wtimeout`)**: giới hạn đợi acknowledgment của write concern; **timeout không mặc định chứng minh dữ liệu đã rollback**.

Đừng coi mọi lỗi timeout là “chưa ghi gì”. Đặc biệt lúc commit, trạng thái có thể không rõ và cần xử lý theo error label.

---

## 19. Lock wait, write conflict và tài nguyên transaction

### 19.1. Lock request timeout mặc định

Theo MongoDB, transaction mặc định **chờ khoảng 5 ms** để lấy những lock cần thiết. Nếu không lấy được trong ngưỡng, transaction có thể bị abort.

Tham số liên quan:

```text
maxTransactionLockRequestTimeoutMillis
```

Không nên tăng ngưỡng tùy tiện lên vài phút để “hết lỗi”. Nó có thể chỉ chuyển một abort sớm thành nhiều request đang chờ, làm tình trạng contention khó quan sát hơn.

### 19.2. Write conflicts

Hai transaction cùng sửa một document, hoặc một transaction gặp write ngoài transaction cạnh tranh, có thể dẫn tới **write conflict**. MongoDB có thể abort một transaction để bảo vệ consistency.

```text
Transaction T1: đọc account A
Transaction T2: cập nhật account A và commit
Transaction T1: cố ghi account A
        |
        +--> Có thể gặp write conflict/abort
```

Ứng dụng cần cơ chế **retry toàn bộ transaction đối với lỗi transient phù hợp**; không chỉ retry riêng lệnh cuối khi transaction đã bị abort.

### 19.3. Transaction quá lớn và áp lực cache

Một transaction sửa rất nhiều document, trả cursor lớn hoặc lưu quá nhiều trạng thái trung gian có thể làm tăng cache/history pressure và nhận lỗi tài nguyên.

Không áp một giới hạn 16 MiB cho **toàn bộ transaction** chỉ vì BSON document riêng có giới hạn kích thước. Giới hạn BSON document và các giới hạn của transaction/oplog/cache là những quy tắc khác nhau. Quy tắc/giới hạn có thể thay đổi theo phiên bản MongoDB.

Đặc biệt, từ MongoDB 6.2, lỗi `TransactionTooLargeForCache` không được server retry như lỗi transient thông thường. Cần **giảm transaction scope**, không lặp vô hạn cùng thao tác quá lớn.

### 19.4. DDL và chunk migration

DDL có thể chờ transaction kết thúc; transaction mới có thể chờ DDL pending rồi hết thời gian. Trong sharded cluster, chunk migration có critical section; nếu migration thay đổi placement đúng lúc transaction, transaction có thể fail ở commit.

Những lỗi này thường đòi retry phù hợp, điều phối deployment và giảm transaction duration. Không nên tắt balancer toàn hệ thống vô thời hạn chỉ để tránh mọi conflict.

---

## 20. Hai-phase commit trong multi-shard transaction

Khi một transaction có write trên nhiều shard, MongoDB sử dụng cơ chế điều phối phân tán để đưa các participant về quyết định commit/abort nhất quán.

Sơ đồ khái niệm:

```text
App
 |
 v
mongos / coordinator
 |
 +--> Shard A: thay đổi document A
 |
 +--> Shard B: thay đổi document B
 |
 +--> Chuẩn bị quyết định commit
 |          |
 |          +--> participant A
 |          +--> participant B
 |
 +--> Quyết định commit được ghi nhận/điều phối
 |
 +--> Các shard hoàn thành commit
 |
 v
Kết quả về client
```

Không nên hiểu đây là một tập các transaction độc lập mà ứng dụng có thể tự commit tuần tự:

```text
commit Shard A thành công
commit Shard B lỗi
```

Nếu tự làm như vậy ở client, bạn không còn đảm bảo multi-shard atomicity. MongoDB coordinator xử lý commit như một distributed transaction.

### 20.1. Khi client mất kết nối lúc commit

Giả sử coordinator đã nhận quyết định commit nhưng network giữa client và router đứt. Client có thể thấy lỗi `UnknownTransactionCommitResult`.

**Không được tự chạy lại toàn bộ chuyển tiền ngay lập tức rồi coi transaction cũ thất bại.** Nếu transaction cũ đã commit, việc chạy lại có thể phát sinh giao dịch nghiệp vụ lần hai.

Driver callback API có logic retry commit theo label phù hợp; tầng nghiệp vụ vẫn cần idempotency key và cách reconcile kết quả chưa rõ.

### 20.2. Quan sát từ transaction khác trong lúc commit

MongoDB có quy tắc visibility trong quá trình commit cross-shard:

- Một số outside reads dùng read concern `"snapshot"`/`"linearizable"` có thể phải **chờ** để thấy trạng thái commit nhất quán.
- Outside reads với mức concern khác có thể nhìn **trạng thái trước transaction** trong thời gian commit.
- Không nên suy ra mọi read ở mọi concern nhìn thấy mọi shard cùng một thời điểm mà không có điều kiện.

Nếu ứng dụng yêu cầu đọc một snapshot nhất quán xuyên shard, hãy chọn read concern thích hợp và kiểm tra semantics cụ thể của transaction.

---

## 21. Java Sync Driver: một ví dụ transaction đầy đủ

Ví dụ chuyển tiền nội bộ bằng `MongoDB Java Sync Driver`. Mọi số dư lưu bằng **minor units** (ví dụ cent) dưới dạng Int64 để phép cộng/trừ integer rõ ràng.

Dữ liệu được tạo **ngoài transaction** trên collection đã được chuẩn bị:

```javascript
db.accounts.insertMany([
  {
    _id: "ACC-A",
    balanceMinor: NumberLong("150000")
  },
  {
    _id: "ACC-B",
    balanceMinor: NumberLong("75000")
  }
]);
```

Collection `transfers` cũng cần tồn tại, nhất là khi code có thể chạy trên sharded cluster và tạo cross-shard write transaction.

### 21.1. Code sử dụng `withTransaction()`

```java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import org.bson.Document;

public final class TransferService {

    private final MongoClient client;
    private final MongoCollection<Document> accounts;
    private final MongoCollection<Document> transfers;

    public TransferService(MongoClient client) {
        this.client = client;

        MongoDatabase database =
            client.getDatabase("bank_demo");

        this.accounts = database.getCollection("accounts");
        this.transfers = database.getCollection("transfers");
    }

    public void transfer(
            String transferId,
            String fromAccount,
            String toAccount,
            long amountMinor
    ) {
        if (amountMinor <= 0 || fromAccount.equals(toAccount)) {
            throw new IllegalArgumentException(
                "Invalid transfer arguments"
            );
        }

        TransactionOptions options =
            TransactionOptions.builder()
                .readPreference(ReadPreference.primary())
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .build();

        try (ClientSession session = client.startSession()) {
            session.withTransaction(() -> {

                UpdateResult debited = accounts.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", fromAccount),
                        Filters.gte("balanceMinor", amountMinor)
                    ),
                    Updates.inc("balanceMinor", -amountMinor)
                );

                if (debited.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Account not found or insufficient funds"
                    );
                }

                UpdateResult credited = accounts.updateOne(
                    session,
                    Filters.eq("_id", toAccount),
                    Updates.inc("balanceMinor", amountMinor)
                );

                if (credited.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Destination account not found"
                    );
                }

                transfers.insertOne(
                    session,
                    new Document("_id", transferId)
                        .append("from", fromAccount)
                        .append("to", toAccount)
                        .append("amountMinor", amountMinor)
                );

                return null;
            }, options);
        }
    }
}
```

**Điểm đúng về mặt transaction:**

- `ClientSession` lấy từ **chính MongoClient** sở hữu collection.
- Cả hai `updateOne` và `insertOne` đều được truyền cùng `session`.
- Thao tác diễn ra **tuần tự**, không async parallel.
- Transaction options gồm `readPreference.primary`, `readConcern.snapshot`, `writeConcern.majority`.
- Lọc debit có điều kiện `balanceMinor >= amountMinor`, giúp ngăn âm số dư khi update phù hợp.
- `transferId` được dùng làm `_id` của audit document, tạo một ràng buộc uniqueness khi collection phù hợp.
- Nếu một thao tác trong callback thất bại, driver xử lý abort theo behavior `withTransaction()`; commit chỉ được thực hiện khi callback hoàn thành.

### 21.2. Điều kiện nghiệp vụ chưa được giải quyết bởi ví dụ

Đây là minh họa transaction, **không phải hệ ngân hàng hoàn chỉnh**. Production còn phải xử lý:

- Idempotency của một HTTP transfer request bị gửi lại.
- Hạn mức chuyển tiền, loại tiền, kiểm tra ownership/permissions.
- Kiểm soát overflow khi cộng/trừ Long.
- Audit và reconciliation giữa ledger và balance.
- Chặn tài khoản bị khóa, account status không hợp lệ.
- Retry budget và tình huống unknown commit.
- Hạn chế uniqueness của `_id`/business key nếu `transfers` là sharded collection.
- Ghi log an toàn, không lộ account/PII.
- Trường hợp transaction đã commit nhưng client không nhận response.

Nếu ứng dụng dùng nhiều loại currency, `balanceMinor` phải có currency đi kèm và công thức không được trộn hai currency.

### 21.3. Vì sao dùng callback API?

`ClientSession.withTransaction()` giúp tự quản lý vòng đời start/commit/abort và có logic retry theo các error label được MongoDB định nghĩa. Nó là lựa chọn tiện lợi cho transaction CRUD điển hình.

Tuy nhiên, **callback có thể chạy lại** khi gặp lỗi transient. Không đưa tác dụng bên ngoài database vào callback:

```java
// Không nên:
session.withTransaction(() -> {
    sendEmailToCustomer(); // Có thể bị gửi nhiều lần khi callback retry.
    accounts.updateOne(session, filter, update);
    return null;
}, options);
```

Nếu cần gửi email/event, cân nhắc **transactional outbox**: ghi một outbox document trong cùng transaction, sau commit có worker gửi ra hệ thống ngoài với idempotency.

---

## 22. `UnknownTransactionCommitResult` và `TransientTransactionError`

Đây là hai tình huống cần phân biệt rõ.

### 22.1. `TransientTransactionError`

Trong transaction có thể gặp lỗi transient như write conflict, stepdown hoặc sự kiện topology. Nếu lỗi mang label:

```text
TransientTransactionError
```

hướng xử lý thường là **retry toàn bộ transaction** từ đầu bằng một session/transaction hợp lệ, theo giới hạn retries/backoff.

Không chỉ chạy lại một lệnh `updateOne` khi transaction hiện tại đã abort.

### 22.2. `UnknownTransactionCommitResult`

Nếu lỗi xảy ra trong lúc commit và được đánh dấu:

```text
UnknownTransactionCommitResult
```

application chưa biết chắc server đã commit hay chưa. Cách xử lý transaction-level thường là **retry commit operation** theo semantics driver, không mặc định transaction đã fail.

Một request nghiệp vụ bị người dùng retry sau khi không nhận response vẫn cần **idempotency key** để tránh tạo chuyển tiền/đơn hàng hai lần.

### 22.3. Callback API so với Core API

| Đặc điểm | Callback API `withTransaction()` | Core API `startTransaction`/`commitTransaction` |
| --- | --- | --- |
| Start/commit/abort | Driver tổ chức | Application tự điều phối. |
| Retry transaction transient | Có logic tích hợp theo driver spec | Phải viết logic riêng. |
| Retry commit unknown result | Có logic tích hợp theo driver spec | Phải viết logic riêng. |
| Kiểm soát flow | Dễ dùng cho CRUD tuần tự | Linh hoạt hơn nhưng dễ sai. |
| Side effects ngoài DB | Vẫn phải tự kiểm soát idempotency | Vẫn phải tự kiểm soát idempotency. |

Dù callback giúp retry, **không được gọi là đảm bảo exactly-once cho toàn bộ HTTP request**. Cần một business idempotency contract bền vững khi client gửi lại.

---

## 23. Idempotency và retry trong sharded environment

Giả sử API:

```text
POST /transfers
Idempotency-Key: 1d9f...
```

Một request chuyển tiền được thực hiện và commit, nhưng mạng mất kết nối trước khi app trả response. Client retry request với cùng key.

Nếu server xử lý lần hai như giao dịch mới, tài khoản có thể bị trừ thêm lần nữa. Giao dịch MongoDB bảo vệ **atomicity của từng lần thực thi**, không tự nhận biết hai HTTP request mô tả cùng một giao dịch nghiệp vụ.

Một thiết kế an toàn hơn:

1. Mỗi request nghiệp vụ có `transferId` ổn định.
2. Lưu `transferId` trong transaction cùng các thay đổi balance/ledger.
3. Đặt unique constraint phù hợp với shard key và phạm vi business.
4. Khi retry bị duplicate, kiểm tra record cũ và so khớp amount/from/to/trạng thái trước khi trả kết quả.
5. Không tự coi mọi lỗi duplicate là thành công: duplicate có thể là một request khác dùng lại key không hợp lệ.
6. Với `UnknownTransactionCommitResult`, dùng strategy reconcile theo domain và driver retry.

### 23.1. Cẩn thận với uniqueness trong sharded collection

Giả sử `transfers` được shard theo `tenantId`. Một unique index chỉ trên `transferId` có thể không hợp lệ hoặc không có guarantee toàn cục như mong đợi.

Nên cân nhắc:

```javascript
db.transfers.createIndex(
  {
    tenantId: 1,
    transferId: 1
  },
  {
    unique: true
  }
);
```

Kết quả là uniqueness **theo tenant**. Nếu business yêu cầu uniqueness toàn hệ thống, phải thiết kế key/collection phù hợp; không giả định transaction phân tán tự tạo một global unique index.

---

## 24. Transaction không bao gồm hành động của hệ thống ngoài MongoDB

Ví dụ luồng đặt hàng:

```text
1. Tạo order trong MongoDB.
2. Trừ inventory trong MongoDB.
3. Gọi payment gateway.
4. Gửi email xác nhận.
```

Một MongoDB transaction có thể atomic các ghi **MongoDB được gắn cùng session**. Nó **không thể tự rollback** một khoản thanh toán đã được payment gateway chấp nhận, hoặc “thu hồi” email đã gửi.

Không làm:

```text
startTransaction
  - update inventory
  - HTTP gọi payment provider (chờ 2 giây)
  - insert order
commit
```

rồi xem toàn bộ quy trình là một ACID transaction xuyên MongoDB và payment provider.

Hướng kiến trúc phù hợp hơn có thể gồm:

- Saga/compensating actions.
- Transactional outbox.
- Idempotent payment operations.
- State machine rõ `PENDING`, `AUTHORIZED`, `CONFIRMED`, `FAILED`.
- Retry và reconciliation định kỳ.

Điều này cũng giúp **giảm thời gian mở transaction**, tránh vượt timeout và giữ tài nguyên lâu.

---

## 25. Cách thiết kế transaction để thường chỉ chạm một shard

Một ứng dụng nhiều tenant có collection:

```javascript
{
  tenantId: "T1",
  accountId: "A",
  balanceMinor: NumberLong("5000")
}
```

Nếu shard key phù hợp để các document của một tenant thường được xử lý trên cùng shard, nhiều giao dịch nội bộ tenant có thể giảm số shard tham gia.

Tuy nhiên:

- Shard key không được chọn chỉ dựa trên transaction: còn phân phối tải, hot shard và khả năng scale.
- Một tenant cực lớn có thể cần phân phối qua nhiều shard.
- Collection khác shard theo key khác có thể làm transaction cross-shard.
- Thay shard key hoặc di chuyển chunk là thay đổi kiến trúc lớn.

### 25.1. Có luôn cần co-locate mọi document không?

Không. Một số nghiệp vụ phải chuyển tiền giữa hai tenant hoặc cập nhật hai shard khác nhau. Khi đó cross-shard transaction là công cụ hợp lệ, nhưng nên:

- Giảm số document và shard tham gia.
- Target shard bằng filter tốt nhất có thể.
- Dùng index cho những query bên trong transaction.
- Tránh scan toàn cluster.
- Tránh DDL và external network calls.
- Đặt timeout/retry budget và đo p95/p99 commit.

**Đừng hy sinh tính đúng đắn để né distributed transaction bằng nhiều update độc lập**, trừ khi domain chấp nhận eventual consistency và có saga/recovery rõ ràng.

---

## 26. Monitoring transaction trên server

Có thể xem số liệu transaction theo môi trường và quyền truy cập.

### 26.1. `serverStatus`

```javascript
db.serverStatus().transactions;
```

Các trường có thể bao gồm số transaction active/inactive, committed, aborted và những thống kê khác tùy phiên bản/edition.

Không hardcode dashboard dựa vào một tập metric bất biến; kiểm tra output của server thực tế.

### 26.2. `$currentOp`

```javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      idleSessions: true
    }
  }
]);
```

Tùy quyền và phiên bản, `$currentOp` có thể đưa ra thông tin transaction hiện tại, session đang giữ resources và phần liên quan tới distributed coordinator.

Các thao tác này là **quan sát quản trị**, không phải operation nên đưa vào transaction nghiệp vụ.

### 26.3. Sharded transaction coordinator

Với write transaction chạm nhiều shard, một số metric/trạng thái của two-phase commit coordinator được cung cấp qua các công cụ server như `$currentOp` và server status.

Nếu p99 commit tăng, không chỉ xem application logs. Cần quan sát:

- Shard participant nào chậm.
- Majority replication lag.
- Lock wait và write conflict.
- Chunk migration/DDL critical section.
- Network latency giữa router/shard.
- Số transaction active/aborted.
- Transaction lifetime và cache pressure.

### 26.4. Driver-side telemetry

Ở Java, thêm command monitoring/tracing để thấy `startTransaction` (theo wire protocol là metadata trên command), CRUD, `commitTransaction` và `abortTransaction`, độ trễ command và error labels.

Không log đầy đủ document hay secrets chỉ để debug transaction. Dùng request ID/transaction business ID đã được xử lý PII thích hợp.

---

## 27. Kiểm tra transaction trên replica set và sharded cluster

### 27.1. Kiểm tra replica set

Trong `mongosh`:

```javascript
rs.status();
db.hello();
db.version();
```

Kiểm tra FCV nếu có quyền:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Các điều kiện cần được xác nhận:

- `db.hello()` đang kết nối tới member của replica set.
- Có primary đủ điều kiện.
- Các members chủ chốt healthy.
- Replica set có write concern phù hợp.
- App dùng đúng URI/set name và không cấu hình sai read preference.

### 27.2. Kiểm tra sharded cluster

Kết nối qua `mongos`:

```javascript
db.hello();
sh.status();
```

Response từ `hello` trên router có đặc điểm của `mongos`, ví dụ thông tin `msg: "isdbgrid"` theo phiên bản. `sh.status()` cho biết thông tin về shards và phân phối dữ liệu.

Đừng chạy `sh.status()` vào một `mongod` standalone rồi kết luận sharding bị lỗi: phải kết nối đúng router.

### 27.3. Smoke test transaction an toàn

Dùng database thử nghiệm có những collection được tạo sẵn:

1. Insert hai document test.
2. Start transaction.
3. Update hai document bằng cùng session.
4. Chủ động abort và xác nhận **cả hai vẫn ở trạng thái cũ**.
5. Start transaction khác.
6. Update hai document, commit majority và xác nhận **cả hai thay đổi**.
7. Thử lỗi do unique key để kiểm tra toàn bộ transaction abort.
8. Với sharded cluster, thử riêng **single-shard** và **multi-shard** trên dữ liệu đã phân bố đúng, có quan sát metrics.

Không cố tình gây primary failover hoặc network partition trong giờ production chỉ để kiểm tra “transaction có chịu được lỗi không”. Những bài test này thuộc môi trường staging/chaos được kiểm soát.

---

## 28. Những lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Transaction numbers are only allowed on a replica set member or mongos` | Kết nối standalone. | Dùng replica set/`mongos`, kiểm tra URI. |
| Giao dịch trên sharded cluster bị từ chối dù server mới | FCV/topology/shard restrictions không đạt. | Kiểm tra tất cả shard, FCV, arbiter, majority journaling. |
| Transaction báo lỗi read preference | Transaction đọc nhưng kế thừa secondary read preference. | Đặt `ReadPreference.primary()` ở transaction options. |
| Update A rollback nhưng update B đã được giữ | Operation B không dùng session. | Bảo đảm tất cả CRUD nhận cùng `ClientSession`. |
| `NoSuchTransaction` hoặc lỗi transaction state | Session/transaction bị abort, hết hạn hoặc dùng sai lifecycle. | Đọc error label, kiểm tra timeout và session use. |
| `WriteConflict` | Nhiều writer tranh cùng document. | Retry transaction theo transient label, giảm phạm vi cạnh tranh. |
| `LockTimeout`/abort khi có `createIndex` | DDL pending chặn lock. | Điều phối migration và transaction window. |
| Transaction vượt một phút rồi abort | Lifetime limit mặc định hoặc workload quá dài. | Giảm số operation, tối ưu query, tránh network call. |
| `UnknownTransactionCommitResult` | Mất kết nối/timeout khi commit. | Retry commit theo driver và reconcile idempotency; không mặc định abort. |
| Giao dịch multi-shard chậm hơn replica set | Distributed coordinator, network và majority. | Giảm số shard tham gia, đo participant/commit. |
| Tạo collection mới trong multi-shard write txn lỗi | DDL/implicit create không được hỗ trợ. | Tạo collection/index trước transaction. |
| `explain()` bị từ chối trong transaction | Operation không được hỗ trợ. | Chạy explain ở ngoài transaction với query tương đương. |
| Transaction chạm shard có arbiter lỗi | Multi-shard write restriction. | Thiết kế lại topology hoặc transaction scope đúng hướng dẫn. |
| Client retry tạo hai giao dịch nghiệp vụ | Không có idempotency. | Dùng business key/unique constraint và reconcile. |
| Thời gian commit cao khi majority | Replication lag hoặc shard coordinator. | Kiểm tra shard health, network, write concern. |
| `count`/`distinct` bị từ chối | Command/helper không phù hợp trong txn. | Dùng aggregation tương ứng khi được hỗ trợ. |
| Transaction đọc dữ liệu khác shard không nhất quán | Read concern `"local"`/`"majority"` thay vì `"snapshot"`. | Dùng snapshot nếu cần view đồng bộ xuyên shard. |

---

## 29. Bài tập vận dụng

### Bài 1 — Standalone và replica set

Local MongoDB chỉ chạy `mongod --dbpath ...`, không có `--replSet`. Java gọi `startTransaction()` rồi update hai collection và báo lỗi.

**Câu hỏi:** Vì sao? Làm thế nào để thử transaction local?

**Gợi ý:** Standalone không hỗ trợ multi-document transaction. Chuyển local deployment thành **single-node replica set** hoặc dùng test MongoDB replica set đã cấu hình.

### Bài 2 — Version và FCV

Môi trường A: replica set FCV 4.0. Môi trường B: sharded cluster FCV 4.0.

**Câu hỏi:** Ngưỡng tối thiểu lịch sử có cho phép transactions?

**Gợi ý:** Replica set từ 4.0; sharded cluster từ 4.2. Cần kiểm tra version/FCV phù hợp cho cả deployment; không dựa vào một `mongos` riêng lẻ.

### Bài 3 — Operation ngoài session

```java
session.startTransaction();

orders.insertOne(session, order);
inventory.updateOne(filter, update);

session.commitTransaction();
```

**Câu hỏi:** Vì sao transaction không đảm bảo hai thao tác cùng atomic?

**Gợi ý:** `inventory.updateOne` không có tham số session, nên không thuộc transaction.

### Bài 4 — Read preference

MongoClient đang có `ReadPreference.secondaryPreferred()`, nhưng transaction đọc số dư trước khi ghi.

**Câu hỏi:** Cần thay đổi gì?

**Gợi ý:** Đặt transaction `ReadPreference.primary()`. Không sử dụng secondary reads trong transaction có thao tác đọc.

### Bài 5 — Snapshot xuyên shard

Transaction đọc account A ở shard 1 và account B ở shard 2. Team đặt read concern `"majority"` và tin đây là cùng snapshot.

**Câu hỏi:** Kết luận đúng không?

**Gợi ý:** `"majority"` không bảo đảm đồng bộ snapshot giữa các shard. Nếu cần điều đó, dùng `"snapshot"` và commit `"majority"` cho các bảo đảm tương ứng.

### Bài 6 — Arbiter

Transaction có write trên hai shard, một shard là replica set có arbiter.

**Câu hỏi:** Có được hỗ trợ không?

**Đáp án:** MongoDB có hạn chế và transaction multi-shard write sẽ error/abort nếu một operation chạm shard chứa arbiter.

### Bài 7 — DDL

Transaction trên shard A cập nhật `orders` và trên shard B insert vào collection `auditLogs` chưa tồn tại.

**Câu hỏi:** Có thể làm trong một cross-shard write transaction không?

**Đáp án:** Không. Tạo collection trước ngoài transaction.

### Bài 8 — Transaction lifetime

Ứng dụng mở transaction, gọi payment gateway mất 90 giây, rồi commit.

**Câu hỏi:** Những rủi ro nào?

**Gợi ý:** Vượt lifetime mặc định 60 giây, giữ resources lâu, tăng write conflicts, commit có thể fail. Đưa call ngoài transaction và dùng saga/outbox.

### Bài 9 — Retry commit

MongoDB đã commit nhưng response bị mất. Client nhận `UnknownTransactionCommitResult`.

**Câu hỏi:** Có được coi là abort rồi chạy lại chuyển tiền không?

**Gợi ý:** Không. Retry commit theo driver API và đối soát bằng business idempotency key.

### Bài 10 — Thiết kế shard key

`accounts` sharded theo `tenantId`, nhưng query transaction chỉ có `accountId`.

**Câu hỏi:** Rủi ro gì?

**Gợi ý:** Router có thể phải broadcast, tăng số participant/chi phí. Xem shard key và filter để targeted operation khi có thể.

### Bài 11 — Unique index

Collection `transfers` sharded theo `tenantId`, team tạo unique index chỉ trên `transferId` để đảm bảo mỗi request toàn hệ thống một lần.

**Câu hỏi:** Điều gì chưa được giải quyết?

**Gợi ý:** Global uniqueness trong sharded collection có giới hạn; unique key phải tương thích shard key, và transaction không tự đảm bảo uniqueness cho mọi field.

### Bài 12 — Transaction và external call

Một transaction cập nhật hai collection rồi gửi email trong callback `withTransaction`.

**Câu hỏi:** Vì sao có thể gửi hai email dù MongoDB chỉ commit một lần?

**Gợi ý:** Callback có thể retry trên lỗi transient. Dùng outbox/idempotent event delivery.

---

## 30. Checklist production cho giao dịch trên replica set

1. Replica set đã được khởi tạo, có primary và member khỏe.
2. Version/FCV hỗ trợ transaction; không phải standalone.
3. Driver hỗ trợ session, mọi CRUD dùng cùng session.
4. Transaction có tối đa một active transaction trên session; không chia sẻ session giữa thread.
5. Read preference phù hợp, đặc biệt transaction đọc phải là primary.
6. Chọn read concern đúng yêu cầu consistency, thường snapshot khi cần.
7. Chọn write concern rõ ở transaction level; cân nhắc majority.
8. Không đặt write concern riêng cho từng CRUD trong transaction.
9. Bảo vệ invariant bằng điều kiện update/unique index.
10. Collection và index chuẩn bị sẵn bằng migration.
11. Transaction ngắn, tránh network call, xử lý dữ liệu lớn và chờ người dùng.
12. Có retry đúng theo transient/unknown commit labels.
13. Có idempotency cho HTTP request nghiệp vụ và side effects.
14. Theo dõi abort rate, duration, lock waits, cache và replication lag.
15. Đã test abort, conflict, failover và unknown commit ở môi trường kiểm soát.

## 31. Checklist bổ sung cho sharded cluster

Ngoài checklist replica set:

1. Client ứng dụng kết nối **qua `mongos`**.
2. Version/FCV toàn cluster hỗ trợ sharded transactions.
3. Các shard có topology hợp lệ và journaling majority phù hợp.
4. Không có shard `writeConcernMajorityJournalDefault: false`.
5. Xem arbiter restrictions trước khi dùng cross-shard write transaction.
6. Các collection cần ghi được tạo/index trước, không tạo mới trong cross-shard write transaction.
7. Shard keys/filters giúp target shard và hạn chế scatter-gather.
8. Nếu cần snapshot đồng bộ xuyên shard, dùng read concern `"snapshot"`.
9. Hiểu two-phase commit và chi phí thêm của coordinator.
10. Giảm số shard tham gia khi domain cho phép.
11. Có chiến lược với chunk migration và DDL trong giờ chạy transaction.
12. Transaction lifetime được quản lý trên các shard replica set members.
13. Đã đánh giá uniqueness/idempotency với shard key.
14. Theo dõi participant/coordinator metrics, network và majority replication.
15. Có benchmark riêng single-shard vs multi-shard với p95/p99 dưới tải.

Sơ đồ quyết định:

```text
Nhu cầu cập nhật nhiều giá trị
             |
             v
Có thể đưa vào một document?
        |            |
       Có          Không
        |            |
   Single-doc     Cần cùng thành công/thất bại?
   atomic update        |             |
                       Không          Có
                        |             |
                  Eventual/      Transaction
                  saga có chủ đích     |
                                      v
                              Deployment là gì?
                               /      |       \
                          Standalone ReplicaSet Sharded
                             |        |        |
                           Không     Được     Được nếu
                           hỗ trợ   nếu hợp  đủ điều
                                   lệ        kiện
                                               |
                                               v
                                   Single-shard hay cross-shard?
                                     |               |
                                  Single          Cross
                                   shard           shard
                                     |               |
                                 Chi phí thấp    2PC, arbiter,
                                  hơn thường     DDL, FCV và
                                                 majority rules
```

---

## 32. Tài liệu MongoDB chính thức

- [Transactions — MongoDB Manual](https://www.mongodb.com/docs/manual/core/transactions/): ACID, sessions, concerns, read preference và behavior tổng quan.
- [Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/): hỗ trợ standalone/replica set, FCV, lifetime, locks, DDL, cache.
- [Production Considerations — Sharded Clusters](https://www.mongodb.com/docs/manual/core/transactions-sharded-clusters/): chi phí, shard restrictions, time limit, snapshot và commit.
- [Transactions and Operations](https://www.mongodb.com/docs/manual/core/transactions-operations/): các operation được hỗ trợ/cấm và điều kiện tạo collection/index.
- [Handle Transactions in Applications with the Drivers API](https://www.mongodb.com/docs/manual/core/transactions-in-applications/): callback/core API và xử lý retry labels.
- [Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/): `ClientSession`, `withTransaction`, transaction options và example Java.
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/): khác biệt local, majority, snapshot.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): acknowledgment và majority rules.
- [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/): routing đọc và yêu cầu primary cho transactions có đọc.
- [Sharded Cluster Requirements](https://www.mongodb.com/docs/manual/core/sharded-cluster-requirements/): shard key, unique indexes và các ràng buộc vận hành.
- [Sharded Cluster Query Router](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/): vai trò của `mongos` và target/broadcast routing.

Khi vận hành production, luôn đối chiếu **version MongoDB server, FCV, driver, deployment type và managed service**. Một số giới hạn và cơ chế thu thập metrics có thể thay đổi giữa các phiên bản.

## 33. Kết luận

MongoDB multi-document transaction chỉ có thể triển khai khi **kiến trúc máy chủ** đáp ứng yêu cầu: **replica set hoặc sharded cluster hợp lệ**, không phải standalone. Version/FCV là điều kiện đầu tiên, nhưng chưa đủ; **session đúng, read preference, read concern, write concern và operation set được hỗ trợ** quyết định transaction có hoạt động đúng nghĩa hay không.

Trên replica set, một transaction thường có overhead hơn một single-document update nhưng có thể bảo vệ các bất biến liên-document. Trên sharded cluster, ứng dụng phải dùng `mongos`; transaction chạm nhiều shard cần phối hợp commit phân tán, chịu thêm ràng buộc về **arbiter, journaling majority, DDL, shard key và chunk migrations**.

Trong cả hai, hãy **giữ transaction ngắn**, chuẩn bị collection/index trước, không trộn network calls hoặc tác dụng ngoài MongoDB vào callback có thể retry, và thiết kế **idempotency + error handling** cho kết quả commit không rõ. Đo cả hiệu năng và tính đúng đắn ở môi trường sát production.

**Điều kiện kỹ thuật giúp transaction chạy được; thiết kế nhất quán và retry đúng mới giúp nó an toàn trong hệ thống thật.**
