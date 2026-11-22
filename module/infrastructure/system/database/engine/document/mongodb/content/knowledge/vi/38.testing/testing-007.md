# Kiểm thử commit, rollback và gửi lại giao dịch trên replica set trong MongoDB

## 1. Bài toán: chuyển tiền hai tài khoản nhưng mạng bị ngắt ngay sau commit

Giả sử ứng dụng ví điện tử chuyển **150.000 VND** từ tài khoản A sang tài khoản B. Dữ liệu nằm trong hai MongoDB documents:

~~~javascript
// wallet.accounts
{
  _id: "A",
  ownerId: "customer-101",
  balanceCents: NumberLong("50000000")
}
{
  _id: "B",
  ownerId: "customer-202",
  balanceCents: NumberLong("30000000")
}
~~~

Ở ví dụ này, **balanceCents** là số nguyên ở đơn vị nhỏ do hệ thống tự định nghĩa; để minh họa chuyển 150.000 VND, ứng dụng sử dụng một số nguyên tương đương theo contract của ví, không tự suy số chữ số thập phân của mọi loại tiền tệ. Trong mã ví dụ về sau, giá trị sẽ được đặt tên **amountUnits** để tránh nhập nhằng. Đây là bài thử kỹ thuật về transaction; hệ thống tài chính production cần nhiều ràng buộc kế toán, đối soát và an toàn bổ sung.

Một request chuyển tiền cần ba thao tác:

1. Trừ số dư A.
2. Cộng số dư B.
3. Lưu bản ghi chuyển tiền với **transferId** để phục vụ truy vết và chống xử lý trùng.

Nếu xử lý độc lập:

~~~text
Update A: success
Update B: network timeout
Insert transfer record: not executed
~~~

Hệ thống có thể mất tính nhất quán. Cần **multi-document transaction** để các thay đổi thuộc cùng nghiệp vụ commit hoặc rollback như một đơn vị.

Nhưng một tình huống khó hơn:

~~~text
Application                     MongoDB replica set
     |                                  |
     | begin transaction                |
     | update A, update B, insert T     |
     |--------------------------------->|
     |                                  |
     | commitTransaction                |
     |--------------------------------->|
     |                                  | commit may succeed
     |            network breaks        |
     X<---------------------------------X
     |
     | "Did commit succeed?"
     | "Should I retry the transaction?"
~~~

Nếu ứng dụng gửi lại **toàn bộ transfer** mà không có idempotency, một giao dịch chuyển tiền có thể bị áp dụng **hai lần**. Nếu bỏ qua retry, kết quả thực tế có thể đã commit nhưng ứng dụng báo thất bại.

Bài học này giải quyết ba lớp câu hỏi:

- **Commit:** Khi nào các thay đổi thật sự trở thành một giao dịch đã cam kết?
- **Rollback/abort:** Khi lỗi trước commit, hệ thống có bảo đảm không để lại cập nhật nửa vời?
- **Retry:** Phải gửi lại **toàn transaction** hay chỉ **commitTransaction**, và làm thế nào chống thực thi nghiệp vụ trùng?

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Tạo và kiểm tra một **replica set** MongoDB trong môi trường test.
2. Phân biệt atomicity của một document với **multi-document transactions**.
3. Mô tả vòng đời **startTransaction → operations → commitTransaction / abortTransaction**.
4. Hiểu vai trò của **ClientSession**, **transaction options**, **readConcern**, **writeConcern**, **readPreference**.
5. Viết test chứng minh **commit đầy đủ**, **rollback đúng** và **isolation/concurrency**.
6. Phân biệt nhãn lỗi **TransientTransactionError** và **UnknownTransactionCommitResult**.
7. Gửi lại đúng phạm vi khi gặp lỗi mạng, write conflict hoặc primary failover.
8. Sử dụng **ClientSession.withTransaction()** trong Java Sync Driver và Spring transaction management phù hợp.
9. Thiết kế **idempotency key, unique index và ledger record** chống business request trùng.
10. Thực hành fault injection trong lab mà không phá dữ liệu production.
11. Kiểm thử timeout, commit retries, failover, concurrent transfers và quan sát kết quả sau lỗi.
12. Biết giới hạn của transactions đối với tác động bên ngoài MongoDB và trách nhiệm vận hành.

**Điểm cốt lõi:** *Retry một lần commit chưa biết kết quả không giống thực thi lại nghiệp vụ. MongoDB transaction atomicity không tự tạo exactly-once semantics cho HTTP requests, email, Kafka hoặc lệnh thanh toán ngoài database.*

## 2. Replica set là tiền đề của bài kiểm thử

### 2.1. Replica set là gì?

Một **replica set** là nhóm các tiến trình **mongod** cùng duy trì bản sao dữ liệu và bầu **primary**. Writes được gửi tới primary và được sao chép sang secondaries theo cơ chế replication.

~~~text
                    Java application
                           |
                    MongoDB driver
                           |
          +----------------+----------------+
          |                |                |
     +----v----+      +----v----+      +----v----+
     | node01  |      | node02  |      | node03  |
     | PRIMARY |----->|SECONDARY|----->|SECONDARY|
     +---------+      +---------+      +---------+
         \________ Replica set "rsLab" ________/
~~~

Hình chỉ minh họa topology. Replication topology và source of oplog sync của một secondary có thể khác hình mũi tên.

MongoDB multi-document transactions hỗ trợ trên **replica sets và sharded clusters** theo phiên bản MongoDB phù hợp. Bài này tập trung **replica set**. Một mongod chạy ở **standalone mode** không tương đương một single-node replica set: thường không hỗ trợ transaction như replica set.

### 2.2. Single-node replica set và ba-member replica set

Hai môi trường test phục vụ mục đích khác nhau:

| Môi trường | Kiểm thử được | Không kiểm thử thực tế được |
|---|---|---|
| Single-node replica set | API transaction, commit/abort, rollback logic, idempotency. | Primary election giữa nhiều nodes, majority availability thực, replication lag. |
| Ba data-bearing members | Transaction và primary failover, replication/majority behavior. | Không tự đại diện chính xác production hardware/network/traffic. |

Không cần ba máy vật lý để học transaction: có thể dùng ba mongod containers/processes trong một test host, miễn kiểm soát URI, ports, persistent storage và replica-set setup.

### 2.3. Kiểm tra bạn đang kết nối tới replica set

Trong mongosh:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

Trên một mongod thành viên replica set, output có thể chứa **setName**, thông tin primary/secondary và hosts. Trong môi trường thử nghiệm:

~~~javascript
rs.status();
~~~

Kết quả cho biết replica set members/state, nhưng command này chỉ phù hợp khi kết nối trực tiếp với member và có quyền tương ứng; **không** chạy rs.status() trên mongos rồi coi output đó là trạng thái của một shard replica set.

### 2.4. MongoDB URI cho replica set

Ví dụ:

~~~text
mongodb://node01:27017,node02:27017,node03:27017/wallet
  ?replicaSet=rsLab
  &retryWrites=true
  &w=majority
~~~

Đây là một URI minh họa, không nên chép line breaks vào config thật. **replicaSet=rsLab** cho phép driver biết topology và bầu chọn primary/secondary; hosts phải được client resolve/truy cập được. Các production deployments cần authentication, TLS và secrets management.

**retryWrites=true không thay thế retry logic cho multi-document transaction.** Nó là một cơ chế liên quan đến các retryable write operations theo semantics được MongoDB hỗ trợ; transaction cần xử lý lỗi theo transaction labels và commit rules.

### 2.5. Majority và tính bền vững

Trong một replica set ba data-bearing voting members, **majority** thường cần acknowledgments từ đa số thành viên phù hợp cấu hình. Với transaction dùng **writeConcern: majority** ở commit, ứng dụng yêu cầu commit acknowledgment theo độ bền majority của replica set.

Không suy rằng:

~~~text
Primary replied OK to one write
  => any later primary failover always retains it.
~~~

Đặc biệt khi dùng weaker write concern, một số writes chưa được majority committed có thể bị rollback khi primary cũ mất vị trí. Cần thiết kế **transaction commit write concern** theo consistency/durability SLO.

### 2.6. Không nhầm hai nghĩa của rollback

Từ **rollback** trong MongoDB có thể chỉ:

1. **Transaction abort/rollback:** hủy các thay đổi chưa commit của một multi-document transaction.
2. **Replication rollback:** một node primary cũ quay lại replica set và loại bỏ những writes chưa được đưa vào lịch sử majority-committed, tùy tình huống failover.

Trong bài này, các test rollback nghiệp vụ chủ yếu nói về **abortTransaction** và transaction atomicity. Phần failover sẽ phân biệt thêm replication durability.

## 3. Atomicity: một document khác với nhiều documents

MongoDB bảo đảm atomicity của write operation ở cấp **một document**, kể cả khi write cập nhật nhiều fields trong document đó.

~~~javascript
db.accounts.updateOne(
  { _id: "A" },
  {
    $inc: { balanceUnits: -150000 },
    $set: { lastUpdatedBy: "transfer-service" }
  }
);
~~~

Hai thay đổi trong cùng document thuộc một atomic document update. Nhưng:

~~~javascript
db.accounts.updateOne({ _id: "A" }, { $inc: { balanceUnits: -150000 } });
db.accounts.updateOne({ _id: "B" }, { $inc: { balanceUnits: 150000 } });
db.transfers.insertOne({ _id: "transfer-101", state: "COMMITTED" });
~~~

**Không phải một đơn vị atomic** nếu thực hiện thành ba commands độc lập, dù chúng chạy nối tiếp và có retryable writes.

### 3.1. Multi-document transaction làm gì?

Một transaction có thể chứa nhiều reads/writes đối với các documents/collections được hỗ trợ:

~~~text
Transaction starts
  |
  +--> debit Account A
  +--> credit Account B
  +--> insert Transfer T
  |
  +--> commit
  |      all changes become committed
  |
  +--> OR abort
         no transaction writes become committed
~~~

MongoDB hỗ trợ **atomicity** của các writes nằm trong transaction: kết quả không phải “chỉ debit A nhưng chưa credit B” sau khi transaction bị abort.

### 3.2. Transactions không thay thế business validation

Một transaction không tự bảo đảm:

- Account A có đủ tiền.
- Account B tồn tại.
- Hai tài khoản thuộc cùng currency.
- Transfer chưa từng được thực hiện.
- User có quyền thao tác.
- Không gửi email/HTTP payment request hai lần.

Các điều kiện đó phải được thể hiện bằng **validation, predicates, indexes, business logic và idempotency**.

### 3.3. Giá trị tiền dùng integer units để thử atomicity

Ví dụ sau dùng **balanceUnits: NumberLong**:

~~~javascript
{
  _id: "A",
  currency: "VND",
  balanceUnits: NumberLong("500000")
}
{
  _id: "B",
  currency: "VND",
  balanceUnits: NumberLong("300000")
}
~~~

Sau chuyển **150000 units**:

~~~text
A = 350000
B = 450000
A + B = 800000 (unchanged)
~~~

Giá trị ví dụ phục vụ kiểm tra invariant, không xác nhận hệ thống thanh toán thực tế nên sử dụng đơn vị nhỏ nào. Với tiền tệ, nên định nghĩa rõ currency, denomination, rounding, overflow và các luật kế toán.

## 4. Vòng đời transaction trên ClientSession

Mỗi transaction được điều khiển qua một **ClientSession** của MongoDB driver.

~~~text
SESSION OPEN
    |
    v
startTransaction()
    |
    v
READ/WRITE OPERATIONS USING THAT SESSION
    |
    +-------------+
    |             |
    v             v
commitTransaction()    abortTransaction()
    |             |
    v             v
COMMITTED       ABORTED
    |             |
    +------v------+
           |
        close session
~~~

### 4.1. startSession không tự bắt đầu transaction

Trong Java:

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();
    // Operations MUST receive the same session.
}
~~~

**startSession()** tạo logical session. **startTransaction()** bắt đầu một transaction trong session; các collection operations cần được truyền **session** thì mới tham gia transaction.

### 4.2. Mọi operation phải dùng cùng session

Đúng:

~~~java
accounts.updateOne(
        session,
        Filters.eq("_id", "A"),
        Updates.inc("balanceUnits", -150000L)
);
~~~

Sai về ý định transactional:

~~~java
session.startTransaction();

// Missing session argument: this write is OUTSIDE the transaction.
accounts.updateOne(
        Filters.eq("_id", "A"),
        Updates.inc("balanceUnits", -150000L)
);

session.abortTransaction();
~~~

Trong ví dụ sai, abort transaction **không rollback** write chạy bên ngoài session.

### 4.3. Không chạy song song các operations trên cùng session/transaction

MongoDB Java Driver không hỗ trợ vận hành nhiều transaction operations song song trên cùng một ClientSession. Tránh:

~~~java
// Unsafe design:
CompletableFuture.runAsync(() -> accounts.updateOne(session, ...));
CompletableFuture.runAsync(() -> transfers.insertOne(session, ...));
~~~

Một logical transaction nên thực hiện operations theo luồng tuần tự đã thiết kế trong callback hoặc synchronous service. Nếu cần xử lý parallel workload, tách transaction/session và kiểm soát invariants/concurrency ở business layer.

### 4.4. Read concern, write concern và read preference

Các transaction options phổ biến:

~~~java
TransactionOptions options = TransactionOptions.builder()
        .readPreference(ReadPreference.primary())
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(WriteConcern.MAJORITY)
        .build();
~~~

- **readPreference.primary()**: transaction reads/writes gửi tới primary trong replica set.
- **ReadConcern.SNAPSHOT**: yêu cầu semantics đọc snapshot trong transaction; các bảo đảm chính xác phụ thuộc commit write concern và topology.
- **WriteConcern.MAJORITY**: yêu cầu mức xác nhận commit theo majority.

Tùy phiên bản MongoDB, readConcern được phép có thể bao gồm **local, majority, snapshot** với những semantics riêng. Không suy rằng một transaction dùng snapshot tự động có mọi bảo đảm durability mạnh nếu commit không được majority acknowledged.

**Chỉ đặt write concern cho transaction ở transaction-level, không gán tùy ý cho từng write trong transaction**.

### 4.5. Transaction options không sửa lỗi nghiệp vụ

Nếu logic không kiểm tra số dư, một transaction có thể **commit cả ba thao tác sai về nghiệp vụ**. Atomicity chỉ nói “tất cả hoặc không gì”, không nói “tất cả luôn đúng”.

Ví dụ debit cần một predicate điều kiện:

~~~javascript
{
  _id: "A",
  currency: "VND",
  balanceUnits: { $gte: NumberLong("150000") }
}
~~~

Sau đó ứng dụng phải kiểm tra **matchedCount/modifiedCount**. Nếu tài khoản không tồn tại hoặc không đủ số dư, transaction phải abort thay vì thực hiện credit B.

### 4.6. Không lạm dụng transaction dài

Multi-document transaction có chi phí:

- Giữ snapshot/resources và gây áp lực cache.
- Có thể gặp write conflict với transactions hoặc writes cạnh tranh.
- Có **transaction lifetime limit** và timeout/lock constraints tùy cấu hình.
- Có thể tiêu tốn thêm oplog, replication và recovery resources.
- Có thể bị abort khi node lỗi hoặc có những giới hạn về transactions.

Không gói **đọc 100.000 records, gọi HTTP API, chờ người dùng nhập OTP rồi ghi MongoDB** vào một transaction sống nhiều phút. Tách external work, giảm số operations và giữ transaction ngắn.

## 5. Chuẩn bị dữ liệu kiểm thử trên replica set

Các script sau dành riêng cho database **wallet_txn_lab**, không được dùng cho production. Chạy mongosh kết nối replica set có quyền được cấp trong môi trường test.

### 5.1. Tạo collections trước transaction

~~~javascript
const lab = db.getSiblingDB("wallet_txn_lab");

lab.createCollection("accounts");
lab.createCollection("transfers");

lab.accounts.createIndex({ ownerId: 1 });
lab.transfers.createIndex({ sourceId: 1, createdAt: -1 });
~~~

Tạo collection/index trước giúp tránh trộn vấn đề DDL/implicit collection creation với bài học transaction. Nếu môi trường test tái sử dụng, cần kiểm tra collections đã tồn tại trước khi gọi createCollection, hoặc dùng database mới dành riêng cho test.

### 5.2. Dữ liệu seed minh họa

~~~javascript
lab.accounts.insertMany([
  {
    _id: "A",
    ownerId: "customer-101",
    currency: "VND",
    balanceUnits: NumberLong("500000")
  },
  {
    _id: "B",
    ownerId: "customer-202",
    currency: "VND",
    balanceUnits: NumberLong("300000")
  }
]);
~~~

Đây là thao tác seed thực hiện **ngoài transaction** cho lab trống. Trong các lần chạy test lặp lại, dùng fixtures cô lập hoặc một prefix ID duy nhất; **không dùng deleteMany({}) trên một database chia sẻ**.

### 5.3. Unique transfer ID làm idempotency key

Collection transfers dùng **_id** duy nhất:

~~~javascript
{
  _id: "request-1001",
  sourceId: "A",
  destinationId: "B",
  amountUnits: NumberLong("150000"),
  currency: "VND",
  state: "COMMITTED",
  createdAt: ISODate("2026-11-14T00:00:00Z")
}
~~~

MongoDB tạo unique index trên **_id** theo semantics collection. Cùng một **transferId** không thể có hai transfer documents bình thường trong cùng collection, nhưng chỉ index unique thôi **chưa bảo đảm** mọi code paths đã chống double debit: nghiệp vụ phải kiểm tra transaction state và transfer parameters.

### 5.4. Invariants của test

Sau thành công:

~~~text
Before:
  A = 500000
  B = 300000
  Total = 800000

After transfer of 150000:
  A = 350000
  B = 450000
  Total = 800000
  Exactly one transfer record with _id=request-1001
~~~

Sau abort:

~~~text
A = 500000
B = 300000
No committed transfer record for aborted request
~~~

Một test không được xác nhận “rollback thành công” chỉ bằng việc exception được ném: phải **đọc lại trạng thái đã commit** và kiểm tra dữ liệu thực tế.

### 5.5. Đo theo cùng nhất quán đọc

Nếu test đọc từ secondary ngay sau commit, replication lag có thể khiến nó thấy giá trị cũ. Để kiểm tra thành công transaction:

- Đọc từ **primary** hoặc sử dụng read concern phù hợp.
- Với yêu cầu durability, dùng **majority commit**.
- Nếu cần read-your-writes/causal ordering, quản lý session và causal consistency phù hợp.
- Không kết luận rollback chỉ vì một secondary chưa kịp thấy thay đổi đã commit.

## 6. Ví dụ transaction thành công bằng mongosh

### 6.1. Bắt đầu session

~~~javascript
const session = db.getMongo().startSession();
const sessionDb = session.getDatabase("wallet_txn_lab");

const accounts = sessionDb.accounts;
const transfers = sessionDb.transfers;
~~~

**Không dùng lab.accounts trực tiếp** trong các thao tác của transaction này nếu đó là collection handle lấy ngoài session. Sử dụng **sessionDb** bảo đảm commands được gắn vào session mongosh phù hợp.

### 6.2. Start, debit, credit, insert và commit

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" },
  readPreference: { mode: "primary" }
});

try {
  const amount = NumberLong("150000");

  const debit = accounts.updateOne(
    {
      _id: "A",
      currency: "VND",
      balanceUnits: { $gte: amount }
    },
    { $inc: { balanceUnits: NumberLong("-150000") } }
  );

  if (debit.matchedCount !== 1) {
    throw new Error("Account A missing or insufficient balance");
  }

  const credit = accounts.updateOne(
    { _id: "B", currency: "VND" },
    { $inc: { balanceUnits: amount } }
  );

  if (credit.matchedCount !== 1) {
    throw new Error("Account B missing or currency mismatch");
  }

  transfers.insertOne({
    _id: "request-1001",
    sourceId: "A",
    destinationId: "B",
    amountUnits: amount,
    currency: "VND",
    state: "COMMITTED",
    createdAt: new Date()
  });

  session.commitTransaction();
  print("Transaction committed");
} catch (error) {
  // A simple lab example. In production, do not treat
  // a commit network error as proof the commit failed.
  try {
    session.abortTransaction();
  } catch (abortError) {
    print("Abort may be unnecessary or unsuccessful: " + abortError);
  }
  throw error;
} finally {
  session.endSession();
}
~~~

**Giới hạn quan trọng:** đây là luồng **happy path và abort trước commit** để học API. Nếu **commitTransaction() trả lỗi kết quả không xác định**, handler ở trên chưa xử lý retry theo error labels. **Không dùng nguyên mẫu này cho production payment**. Phần Java với **withTransaction** và mục retry sẽ giải thích cách xử lý chuẩn.

### 6.3. Quan sát kết quả

~~~javascript
lab.accounts.find(
  { _id: { $in: ["A", "B"] } },
  { _id: 1, balanceUnits: 1, currency: 1 }
);

lab.transfers.findOne({ _id: "request-1001" });
~~~

Kỳ vọng A=350000, B=450000 và đúng một transfer record.

### 6.4. Vì sao test cần record thứ ba?

Nếu chỉ kiểm tra debit và credit, bạn có thể bỏ sót trường hợp:

~~~text
Balances committed, transfer receipt missing
~~~

Đặt transfer record **trong cùng transaction** buộc ba thao tác cùng commit/abort. Trong hệ thống thật, bản ghi này còn hỗ trợ audit, idempotency và reconciliation.

### 6.5. Commit không tương đương gửi HTTP 200

Ví dụ:

~~~text
MongoDB transaction committed
       |
       v
HTTP connection breaks
       |
       v
Client retries POST /transfer
~~~

Response bị mất **không rollback** database. Business endpoint phải dùng stable idempotency key và trả kết quả đã ghi nhận khi client gửi lại.

## 7. Ví dụ rollback/abort bằng mongosh

Mục tiêu: thử lỗi **giữa transaction** và chứng minh không có “nửa bản ghi”.

### 7.1. Chủ động tạo lỗi sau debit

Chuẩn bị một transferId mới **request-abort-01** và dùng accounts đã seed (hoặc fixture riêng). Trong mongosh:

~~~javascript
const s2 = db.getMongo().startSession();
const db2 = s2.getDatabase("wallet_txn_lab");

s2.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});

try {
  db2.accounts.updateOne(
    {
      _id: "A",
      balanceUnits: { $gte: NumberLong("10000") }
    },
    {
      $inc: { balanceUnits: NumberLong("-10000") }
    }
  );

  // Test-only failure before credit and insert receipt.
  throw new Error("Injected application failure");

  // Unreachable:
  // db2.accounts.updateOne(... credit B ...);
  // db2.transfers.insertOne(...);
  // s2.commitTransaction();
} catch (err) {
  s2.abortTransaction();
  print("Transaction aborted: " + err.message);
} finally {
  s2.endSession();
}
~~~

### 7.2. Kiểm tra rollback

~~~javascript
lab.accounts.find(
  { _id: { $in: ["A", "B"] } },
  { balanceUnits: 1 }
);

lab.transfers.countDocuments({
  _id: "request-abort-01"
});
~~~

Kỳ vọng số dư A/B **không đổi so với trước test abort** và không có record của transfer ID đó.

### 7.3. Abort vì insufficient funds

Nếu debit predicate không match:

~~~javascript
{
  _id: "A",
  balanceUnits: { $gte: NumberLong("999999999") }
}
~~~

thì **matchedCount=0**; business logic phải abort. MongoDB không tự suy rằng matchedCount=0 là exception hoặc lỗi transaction. **Một update không match có thể là thao tác hợp lệ** trừ khi ứng dụng kiểm tra và chủ động từ chối.

### 7.4. Abort vì recipient không tồn tại

Nếu debit A đã được thực hiện trong transaction, nhưng credit B không match hoặc B bị xóa cạnh tranh, logic phải throw và abort. Sau đó kiểm tra A không bị trừ.

### 7.5. Abort vì unique constraint

Nếu insert transfer record có cùng **_id** với một record đã tồn tại, MongoDB báo duplicate key trong trường hợp điều kiện phù hợp. Transaction lỗi và cần xử lý đúng:

- Không retry không giới hạn một duplicate key mang tính business conflict.
- Kiểm tra **record hiện tại có cùng request parameters** hay không.
- Nếu cùng idempotency key nhưng parameters khác, trả **conflict**.
- Nếu đã hoàn tất đúng request, trả kết quả cũ theo API contract.

Không “giải quyết” duplicate key bằng cách đổi sang transferId mới và debit lại.

### 7.6. Abort sau commit là bất khả thi về ý nghĩa

~~~text
startTransaction
  -> debit/credit
commit succeeded
  -> client later wants to undo
~~~

Khi commit thành công, **abortTransaction() không đảo ngược transaction đã commit**. Nếu cần hoàn tiền, nghiệp vụ phải tạo một **compensating transaction** mới, có audit/reference tương ứng. Đây là business reversal chứ không phải rollback của transaction trước.

## 8. Phân biệt lỗi trước commit, lỗi transient và kết quả commit chưa biết

Không phải mọi exception có cùng cách retry. Cần phân biệt **giai đoạn xảy ra lỗi**, **lỗi có nhãn gì** và **transaction đã có thể commit hay chưa**.

### 8.1. Lỗi nghiệp vụ trước commit

Ví dụ:

- Insufficient balance.
- Destination account không tồn tại.
- Currency mismatch.
- Idempotency key được sử dụng với parameters khác.

~~~text
Start transaction
  -> business predicate fails
  -> abort
  -> return a business failure
~~~

Không retry mù quáng nếu request vẫn thiếu tiền hoặc dữ liệu không hợp lệ.

### 8.2. TransientTransactionError — retry toàn transaction

MongoDB driver/server có thể đánh nhãn **TransientTransactionError** cho những lỗi tạm thời trong transaction, như một số write conflicts, primary failover hoặc sự cố kết nối theo semantics phiên bản.

~~~text
Error labeled TransientTransactionError
       |
       v
Discard unsuccessful attempt
       |
       v
Start a NEW transaction attempt
       |
       v
Rerun all reads and writes with current conditions
~~~

**Retry toàn transaction** nghĩa là đọc và ghi lại trong một attempt mới. Không tiếp tục một transaction đã abort và không lặp một write riêng lẻ mà bỏ những thao tác còn lại.

### 8.3. UnknownTransactionCommitResult — retry commit

Nếu client gửi **commitTransaction** nhưng bị ngắt kết nối hoặc không nhận được kết quả có ý nghĩa xác định, một số lỗi có nhãn **UnknownTransactionCommitResult**:

~~~text
Transaction body completed
        |
        v
commitTransaction sent
        |
        X response lost
        |
        v
UnknownTransactionCommitResult
        |
        v
Retry commitTransaction
for SAME transaction/session
~~~

**Đây không phải tín hiệu retry lại body ngay.** Giao dịch đầu tiên có thể đã commit, nên chạy lại debit/credit trong một transaction mới có nguy cơ double transfer nếu không có idempotency.

### 8.4. Duplicate key và lỗi không transient

Một duplicate transfer ID không tự động là transient. Xử lý:

1. Đọc transfer record của ID đó.
2. So toàn bộ immutable request parameters.
3. Nếu cùng request và đã commit, trả kết quả đã lưu.
4. Nếu cùng ID nhưng khác parameters, trả conflict.
5. Nếu outcome chưa rõ, reconcile/retry theo policy giới hạn.

Không đổi transferId tùy tiện để vượt unique constraint.

### 8.5. Bảng quyết định

| Lỗi / tình huống | Hành động |
|---|---|
| Validation fail trước commit | Abort và trả business error. |
| **TransientTransactionError** trong body | Retry **toàn transaction** trên attempt mới. |
| **UnknownTransactionCommitResult** khi commit | Retry **commit cùng transaction**. |
| Duplicate transfer ID | Reconcile existing record, verify parameters. |
| HTTP response mất sau khi commit | Client resend với cùng idempotency key; server trả kết quả cũ. |
| Primary down kéo dài | Bounded retry/backoff, thông báo chưa xác định khi cần, reconciliation. |
| Code/schema/permission error | Khắc phục lỗi, không blind retry. |

### 8.6. Kiểm tra error labels trong Java

~~~java
if (exception.hasErrorLabel("TransientTransactionError")) {
    // Retry transaction body in a new attempt.
}

if (exception.hasErrorLabel("UnknownTransactionCommitResult")) {
    // Retry commit, not the entire body immediately.
}
~~~

Đoạn code chỉ minh họa **cách phân loại**. Không tự viết vòng lặp transaction đơn giản dựa trên hai câu if mà bỏ qua trạng thái session/commit hoặc giới hạn thời gian.

### 8.7. Retryable writes khác transaction retries

| Cơ chế | Phạm vi |
|---|---|
| **Retryable write** | Một số write operations được hỗ trợ, thường ngoài multi-document transaction. |
| **Transaction body retry** | Chạy lại nhóm reads/writes sau lỗi transient. |
| **Commit retry** | Gửi lại commit của cùng transaction khi outcome chưa rõ. |
| **HTTP retry** | Một business request mới có thể tới service; phải có idempotency key. |
| **Message redelivery** | Consumer có thể thấy event cũ lần nữa; phải deduplicate. |

**retryWrites=true** không tự tạo exactly-once semantics cho HTTP requests nhiều bước.

## 9. Java Sync Driver: transaction callback với withTransaction

MongoDB Java Sync Driver hỗ trợ **ClientSession.withTransaction(...)**. Driver thực hiện vòng đời transaction và xử lý các error labels cần retry theo hành vi được hỗ trợ, giúp giảm rủi ro của retry loops tự viết.

### 9.1. Transaction options

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;

TransactionOptions txOptions = TransactionOptions.builder()
        .readPreference(ReadPreference.primary())
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(WriteConcern.MAJORITY)
        .build();
~~~

Trước khi chạy: driver/server tương thích, replica set URI, collections/indexes đã tạo, đủ quyền và có timeout policy của ứng dụng.

### 9.2. Domain request có idempotency key

~~~java
package com.example.wallet;

public record TransferRequest(
        String transferId,
        String sourceId,
        String destinationId,
        String currency,
        long amountUnits) {

    public TransferRequest {
        if (transferId == null || transferId.isBlank()
                || sourceId == null || sourceId.isBlank()
                || destinationId == null || destinationId.isBlank()) {
            throw new IllegalArgumentException(
                    "Transfer and account IDs are required");
        }
        if (sourceId.equals(destinationId)) {
            throw new IllegalArgumentException(
                    "Source and destination must differ");
        }
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException(
                    "Currency is required");
        }
        if (amountUnits <= 0) {
            throw new IllegalArgumentException(
                    "Transfer amount must be positive");
        }
    }
}
~~~

Các validations về owner, quyền truy cập, currency normalization và business transaction limits phải được bổ sung trong hệ thống thật.

### 9.3. Dùng cùng ClientSession cho mọi lệnh

~~~java
package com.example.wallet;

import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import java.util.Date;
import java.util.Objects;

public final class TransferService {

    private static final TransactionOptions TX_OPTIONS =
            TransactionOptions.builder()
                    .readPreference(ReadPreference.primary())
                    .readConcern(ReadConcern.SNAPSHOT)
                    .writeConcern(WriteConcern.MAJORITY)
                    .build();

    private final MongoClient client;
    private final MongoCollection<Document> accounts;
    private final MongoCollection<Document> transfers;

    public TransferService(MongoClient client) {
        this.client = Objects.requireNonNull(client);
        var database = client.getDatabase("wallet_txn_lab");
        accounts = database.getCollection("accounts");
        transfers = database.getCollection("transfers");
    }

    public Document transfer(TransferRequest request) {
        Objects.requireNonNull(request);

        try (ClientSession session = client.startSession()) {
            return session.withTransaction(() -> {
                Document existing = transfers.find(
                        session,
                        Filters.eq("_id", request.transferId())
                ).first();

                if (existing != null) {
                    verifySameRequest(existing, request);
                    return existing;
                }

                UpdateResult debit = accounts.updateOne(
                        session,
                        Filters.and(
                                Filters.eq("_id", request.sourceId()),
                                Filters.eq("currency", request.currency()),
                                Filters.gte(
                                        "balanceUnits",
                                        request.amountUnits())
                        ),
                        Updates.inc(
                                "balanceUnits",
                                -request.amountUnits())
                );

                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                            "Source missing, wrong currency, "
                                    + "or insufficient funds");
                }

                UpdateResult credit = accounts.updateOne(
                        session,
                        Filters.and(
                                Filters.eq("_id", request.destinationId()),
                                Filters.eq("currency", request.currency())
                        ),
                        Updates.inc(
                                "balanceUnits",
                                request.amountUnits())
                );

                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                            "Destination missing or wrong currency");
                }

                Document receipt = new Document(
                        "_id",
                        request.transferId()
                ).append("sourceId", request.sourceId())
                 .append("destinationId", request.destinationId())
                 .append("amountUnits", request.amountUnits())
                 .append("currency", request.currency())
                 .append("state", "COMMITTED")
                 .append("createdAt", new Date());

                transfers.insertOne(session, receipt);
                return receipt;
            }, TX_OPTIONS);
        }
    }

    private static void verifySameRequest(
            Document existing,
            TransferRequest request) {

        Object amount = existing.get("amountUnits");
        boolean same = request.sourceId().equals(
                existing.getString("sourceId"))
                && request.destinationId().equals(
                        existing.getString("destinationId"))
                && request.currency().equals(
                        existing.getString("currency"))
                && amount instanceof Number
                && request.amountUnits()
                        == ((Number) amount).longValue();

        if (!same) {
            throw new IllegalStateException(
                    "Idempotency key reused with different parameters");
        }
    }
}
~~~

### 9.4. withTransaction có thể gọi body nhiều lần

Driver có thể retry callback trên một transaction attempt mới sau lỗi transient. Do đó, **body phải an toàn khi chạy lặp**:

- Không gửi email bên trong callback.
- Không gọi payment REST API ngoài MongoDB trong callback.
- Không publish Kafka event ngay trong callback.
- Không tạo transferId mới cho mỗi attempt.
- Không phát event từ log side effect mà không có deduplication.

**transferId phải ổn định xuyên attempts và xuyên HTTP retries**. Trong ví dụ, createdAt dùng new Date() nên có thể khác giữa những attempt đã abort; nếu business yêu cầu request-time cố định, sinh timestamp trước callback và lưu cùng TransferRequest.

### 9.5. withTransaction không thay thế business idempotency

Transaction callback có thể retry nội bộ, nhưng một HTTP POST mới có thể tạo **ClientSession mới và transaction mới**:

~~~text
POST /transfers, transferId=abc
    -> MongoDB transaction commits
    -> HTTP response lost

POST /transfers, transferId=abc again
    -> must return previous result
    -> must NOT debit again
~~~

Query transferId trước khi debit và unique **_id** trên receipt giúp thực hiện idempotency ở database, kết hợp với business parameter checks.

### 9.6. Đồng thời hai requests cùng ID

Hai requests có thể cùng đọc “transfer chưa tồn tại” trước khi một trong hai commit. **Unique _id** sẽ ngăn hai receipt records cùng ID, còn transaction đảm bảo attempt thất bại không để lại nửa debit/credit.

Tuy nhiên, request thua race có thể nhận **duplicate key/write conflict**. Lớp API cần:

1. Phân loại lỗi sau driver retries.
2. Re-read transferId bằng read consistency phù hợp.
3. Xác minh sourceId/destinationId/currency/amount đúng.
4. Trả existing result khi đó là cùng business request.
5. Trả conflict nếu key trùng nhưng parameters khác.
6. Nếu kết quả vẫn chưa rõ, dùng **bounded reconciliation** thay vì debit lại mù quáng.

### 9.7. Giới hạn retries

Mọi retry cần **deadline, số lần hoặc khoảng thời gian hữu hạn, backoff/jitter khi phù hợp và quan sát errors**. Driver withTransaction xử lý các lỗi có labels được hỗ trợ nhưng không bảo đảm giao dịch mãi mãi sẽ thành công nếu cluster unavailable.

## 10. Mô hình retry thủ công: phạm vi nào được lặp lại?

Khi không dùng **withTransaction**, ứng dụng phải tự triển khai vòng đời transaction và các nhánh lỗi. Học mô hình này giúp hiểu semantics, nhưng **không nên tự chép một vòng lặp ngắn thành transaction manager production**.

### 10.1. Hai vòng lặp khác nhau

~~~text
OUTER LOOP: transaction attempt
  |
  v
startTransaction
  |
  v
execute body
  |
  +-- TransientTransactionError? --> abort attempt, retry OUTER
  |
  v
INNER LOOP: commit of THIS attempt
  |
  v
commitTransaction
  |
  +-- UnknownTransactionCommitResult? --> retry INNER
  |
  +-- known success --> return success
  |
  +-- known non-retryable failure --> stop/reconcile
~~~

**Tuyệt đối không** biến UnknownTransactionCommitResult thành lệnh tự động debit/credit một lần nữa.

### 10.2. Pseudocode có deadline

~~~text
deadline = now + configuredRetryBudget

while timeRemaining(deadline):
    start a new transaction attempt

    try:
        execute transaction reads/writes
    catch error:
        bestEffortAbort()

        if error has TransientTransactionError:
            backoffAndRetryWholeAttempt()
            continue

        throw error

    while timeRemaining(deadline):
        try:
            commit SAME transaction
            return COMMITTED
        catch error:
            if error has UnknownTransactionCommitResult:
                backoffAndRetryCommitOnly()
                continue
            throw error

    return UNKNOWN_NEEDS_RECONCILIATION

return RETRY_BUDGET_EXHAUSTED
~~~

Mã giả nêu rõ hai retry scopes; triển khai thực tế phải tuân theo driver transaction specifications, bao gồm **session state, commit errors, server selection, cancellation, retry budgets và exception labels**. Khi deadline hết mà kết quả commit chưa rõ, không tự khẳng định transaction đã abort.

### 10.3. Gửi lại commit sử dụng cùng transaction identity

Để commit retry có ý nghĩa, client phải giữ đúng **logical session/transaction identity** (ví dụ thông tin session và transaction number do driver quản lý). Không tự phát một transaction mới rồi gọi đó là “retry commit”.

Đừng sửa hoặc giả mạo **lsid/txnNumber** bằng BSON trong application code. Dùng **ClientSession API** của driver.

### 10.4. Một lỗi không được tự động retry

Nếu server phản hồi rằng update không match:

~~~text
matchedCount=0
reason=insufficient funds
~~~

đó là kết quả nghiệp vụ cần xử lý, không nhất thiết có error label. Retry 100 lần khi không có ai nạp thêm tiền chỉ tăng tải DB và làm API chậm.

### 10.5. Bounded retry, backoff và overload

Trên một cluster đang election hoặc quá tải:

~~~text
100 application instances
  x 500 requests
  x immediate retry loop
  = retry storm
~~~

Áp dụng:

- Retry budget/deadline ở request level.
- Backoff và jitter nếu phù hợp.
- Circuit breaker/admission control khi hệ thống down.
- Metrics về attempts, transient errors và unknown outcomes.
- Idempotency/reconciliation cho request bị timeout.

Driver có policy retry riêng. Tránh bọc **withTransaction** bằng nhiều lớp retry vô hạn ở controller, service và message consumer.

## 11. Thiết kế ma trận kiểm thử transaction

Một bài kiểm thử tốt không chỉ hỏi “commit không lỗi?” mà kiểm tra **trạng thái sau sự cố**, **retry scope**, **độ bền** và **business idempotency**.

### 11.1. Ma trận chính

| Kịch bản | Lỗi/điều kiện | Kỳ vọng sau test |
|---|---|---|
| Happy commit | Không lỗi, account đủ tiền | A giảm, B tăng, đúng một receipt, tổng bảo toàn. |
| Explicit abort | Throw sau debit | Không thay đổi số dư đã commit, không receipt. |
| Missing recipient | B không tồn tại | Debit A rollback, không receipt. |
| Insufficient funds | Debit predicate không match | Không thay đổi dữ liệu, trả business error. |
| Currency mismatch | Currency B khác | Không debit/credit/receipt nào commit. |
| Duplicate ID, same parameters | Gửi lại request sau commit | Trả kết quả cũ, không debit lần hai. |
| Duplicate ID, different parameters | Gửi lại key với số tiền khác | Conflict, không debit lần hai. |
| Transient error before commit | Write conflict hoặc failover | Driver retry toàn body; cuối cùng commit một lần hoặc fail có kiểm soát. |
| Unknown commit outcome | Response commit bị mất | Retry commit/resolve; không chạy lại business body mù quáng. |
| Primary stepdown | Failover trong attempt | Recovery/transaction retry theo labels, invariants giữ đúng. |
| Parallel distinct transfer IDs | Hai requests cùng source balance | Không bị âm ngoài policy; totals và receipts nhất quán. |
| Read from secondary | Replication lag | Không nhầm stale read với abort; assert theo read concern. |
| Retry budget exhausted | DB unavailable dài | API báo failure/unknown phù hợp; reconciliation xác định outcome. |
| External side effect | Callback bị replay | Không gửi email/publish trùng không kiểm soát. |

### 11.2. Kiểm thử commit không chỉ nhìn return value

~~~text
Given:
  A = 500000, B = 300000

When:
  commit transfer 150000 with ID=req-1

Then:
  A = 350000
  B = 450000
  sum(A,B) = 800000
  exactly 1 transfer record _id=req-1
  receipt parameters match request
~~~

Kiểm thử **business invariants** bền hơn kiểm tra một field status đơn lẻ.

### 11.3. Kiểm thử rollback cần đọc sau abort

~~~text
Given:
  A = 500000, B = 300000

When:
  debit A inside transaction
  inject failure before credit
  abort

Then:
  A = 500000
  B = 300000
  no receipt from aborted transaction
~~~

Không coi việc exception được ném là bằng chứng rollback. Nếu debit vô tình chạy ngoài session, abort vẫn được gọi nhưng dữ liệu đã thay đổi!

### 11.4. Kiểm thử không nhìn thấy partial writes

Trong transaction chưa commit, chính session có thể đọc những writes vừa thực hiện (read-your-own-writes). Một reader ngoài transaction với read semantics phù hợp **không được coi partial transactional writes chưa commit là một trạng thái hợp lệ đã công bố**.

Thiết kế test:

1. T1 bắt đầu và debit A, chưa commit.
2. T2 thực hiện một read độc lập theo mức consistency đã chọn.
3. T1 abort.
4. T2/new reader xác nhận không có partial committed state.

Không dùng một reader trên secondary đang lag để kết luận về visibility của dữ liệu mới.

### 11.5. Kiểm thử concurrent updates

Hai transfers cùng nguồn:

~~~text
A balance = 200 units

T1: A -> B, 150 units, ID=req-1
T2: A -> C, 150 units, ID=req-2
~~~

Nếu business cấm overdraft, **không được cả hai debit thành công** với tổng 300 units. Predicate **balanceUnits >= amount** và transaction/write-conflict behavior giúp enforce constraint. Một attempt có thể phải retry trên snapshot mới và sau đó thấy không đủ tiền.

Điều kiện xác nhận:

~~~text
A >= 0
sum(A,B,C) unchanged
at most one 150-unit transfer committed
each committed receipt corresponds to one debit/credit
~~~

### 11.6. Test không được phụ thuộc chỉ vào sleep

Không viết:

~~~text
sleep(100)
assert failover completed
~~~

Election, connection recovery và replication mất thời gian biến thiên. Dùng **polling có deadline** cho observable condition (new primary elected, committed record visible, replica healthy), và fail test khi vượt deadline kèm diagnostics.

### 11.7. Không che kết quả UNKNOWN thành FAIL

Một commit outcome chưa rõ khác với kết quả chắc chắn abort:

~~~text
ABORTED:
  transaction was not committed

COMMITTED:
  transaction committed and known

UNKNOWN:
  client cannot determine final commit outcome yet
~~~

API/reconciliation phải có cách quản lý trạng thái UNKNOWN. Không gửi lệnh bù tiền tự động chỉ vì response commit timeout: nếu transaction đầu tiên cuối cùng commit, compensation có thể tạo lỗi mới.

## 12. Kiểm thử với một single-node replica set

Single-node replica set phù hợp cho **smoke tests commit/abort và converter/session wiring**. Nó không tạo được thử nghiệm failover majority thực tế.

### 12.1. Khởi động một mongod trong lab

Ví dụ **chỉ trên máy lab** đã có mongod, một data directory riêng:

~~~bash
mkdir -p /tmp/mongodb-txn-lab
mongod \
  --replSet rsLab \
  --bind_ip localhost \
  --port 27017 \
  --dbpath /tmp/mongodb-txn-lab
~~~

Đối với Windows, Docker hoặc Kubernetes, cách tạo directory/process sẽ khác; ví dụ shell này dành cho môi trường Unix-like test. Không dùng cổng hoặc dbpath đã có MongoDB quan trọng.

Trong một mongosh riêng:

~~~javascript
rs.initiate({
  _id: "rsLab",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
});
~~~

Sau đó kiểm tra:

~~~javascript
rs.status();
db.adminCommand({ hello: 1 });
~~~

Chờ node thành **PRIMARY** rồi mới thực hiện transaction tests.

### 12.2. Vì sao single-node là đủ cho bước đầu?

Một node replica set vẫn cho phép chạy session transactions ở server/version hỗ trợ. Nó giúp kiểm tra:

- Ứng dụng có tạo ClientSession đúng không?
- Các writes có đi qua cùng session không?
- Commit/abort có tác dụng không?
- Unique transfer ID có được thực thi không?
- Domain/business predicates có đúng không?

Không dùng single-node để kết luận khả năng chịu mất primary, ghi majority trong nhiều nodes hay hành vi secondary reads.

### 12.3. Khi nào cần ba members?

Các kịch bản cần **ít nhất một multi-node replica set test**:

- Election và primary stepdown.
- Majority write concern khi một node không available.
- Replication lag.
- Secondary reads sau commit.
- Node partition/reconnect.
- Durable commit sau failover.

Trong production, cấu hình members, votes, priorities, disk và network topology phải theo thiết kế HA; lab ba containers trên một host **không chứng minh** availability trước mất toàn host.

## 13. Fault injection: chủ động kiểm thử lỗi mà không gây sự cố production

Các test retry có ý nghĩa chỉ khi có thể tái hiện những khoảng thời gian khó:

- Mất kết nối trong transaction body.
- Ghi bị write conflict.
- Primary election khi transaction chưa commit.
- Kết nối bị đóng khi commit result chưa tới client.
- Secondary lag/replication availability.

**Tất cả thí nghiệm gây lỗi phải chạy trên lab replica set cô lập**, dùng test data và account được cấp quyền. Không gọi failpoint, stepdown, kill process hoặc network proxy phá kết nối trên production/shared environments khi chưa có quy trình change/incident riêng.

### 13.1. Ba mức fault injection

| Mức | Cách thực hiện | Tính quyết định |
|---|---|---|
| Application-level | Throw exception sau debit, trước credit. | Cao; thử abort logic, không thử server/network. |
| Server command-level | Supported test failpoints như **failCommand**. | Có thể tái tạo command failures; behavior/version phụ thuộc cấu hình. |
| Infrastructure/network | Proxy đóng kết nối, node stepdown, partition. | Thử network/election thực tế, nhưng thời điểm có thể khó đồng bộ. |

Nên bắt đầu với lỗi **application-level**, sau đó mới thử fault injection sâu hơn.

### 13.2. FailCommand failpoint chỉ dành cho môi trường test

MongoDB có một số **failpoints** dùng cho kiểm thử lỗi theo command, được hỗ trợ/bật theo server build và cấu hình. Một ví dụ minh họa test-only:

~~~javascript
db.adminCommand({
  configureFailPoint: "failCommand",
  mode: { times: 1 },
  data: {
    failCommands: ["commitTransaction"],
    closeConnection: true
  }
});
~~~

Thao tác này cố tình gây lỗi đường kết nối cho command commit trong trường hợp server/test version hỗ trợ. **Không bảo đảm commit đã thực sự thực thi trước khi kết nối bị cắt**: failpoint có thể hoạt động trước lúc command được xử lý.

Vì vậy bài test phải chấp nhận hai nhánh thực tế và kiểm tra:

1. Client/driver có phân loại exception và error labels đúng không?
2. Driver có retry commit hoặc trả trạng thái unknown theo hợp đồng không?
3. Sau khi hệ thống ổn định, database có **0 hoặc 1 lần commit** đối với transferId, không bao giờ có double debit.
4. Business request được reconcile bằng idempotency key.

**Không** sử dụng failCommand rồi khẳng định đã tái hiện chính xác “server commit thành công nhưng client mất response” nếu không có thêm phương pháp đồng bộ timing.

### 13.3. Tắt failpoint sau test

Trong môi trường thử nghiệm và trên node đã cấu hình:

~~~javascript
db.adminCommand({
  configureFailPoint: "failCommand",
  mode: "off"
});
~~~

Các failpoints có thể cần quyền/cấu hình test đặc biệt và không có trên mọi managed deployment. Nếu command bị từ chối, sử dụng network proxy/test harness được hỗ trợ; **không nới quyền production** chỉ để chạy một bài thực hành.

### 13.4. Tái hiện unknown outcome bằng network proxy

Một cách nâng cao là đặt test proxy giữa client và replica set, cho phép script kiểm soát hướng client→server và server→client trong lab.

~~~text
Java test client
      |
      v
Network fault proxy
      |
      v
Replica set primary
~~~

Mục tiêu của tình huống:

1. Transaction body hoàn tất.
2. Commit được gửi.
3. Kênh phản hồi server→client bị gián đoạn.
4. Driver xử lý outcome chưa rõ.
5. Test đọc lại receipt và balances sau khi mạng phục hồi.

Việc điều khiển chính xác **sau commit, trước response** có thể đòi hỏi test harness/protocol proxy chuyên dụng. Nếu không khống chế timing, chỉ báo “injected network error near commit” và xác nhận invariants, không gán một kết quả giả.

### 13.5. Primary stepdown trong replica set nhiều nodes

Trên **test primary** của replica set có secondaries khỏe:

~~~javascript
rs.stepDown(15);
~~~

Lệnh làm primary từ chức trong một khoảng thời gian theo semantics được hỗ trợ. Election và driver topology discovery sẽ diễn ra; một transaction in-flight có thể thất bại và cần retry.

Điểm cần đo:

- Driver nhận lỗi/labels nào?
- Mất bao lâu chọn được primary mới?
- Có transaction nào bị abort?
- Có request nào báo commit unknown?
- Số dư và receipt sau phục hồi có thỏa invariants không?
- Majority-acknowledged commit có được bảo toàn không?

Không chạy stepdown tùy tiện nếu replica set chỉ có một primary và không đủ secondaries để bầu lại.

### 13.6. Khi nào nên inject lỗi?

Tạo các test points riêng:

~~~text
F1: before startTransaction
F2: after first debit
F3: after second credit
F4: after receipt insert, before commit
F5: during commit request/response
F6: after confirmed commit, before HTTP response
~~~

Mỗi điểm trả lời câu hỏi khác:

- F2–F4: rollback atomicity nếu transaction abort.
- F5: commit result ambiguity và commit retry.
- F6: **application-level idempotency** sau khi DB đã commit.

Một bộ test chỉ inject ở F2 không chứng minh đã xử lý F5 hoặc F6.

### 13.7. Không chạy nhiều loại fault cùng lúc ở bài đầu

Nếu vừa stepdown primary, vừa throttle disk, vừa chặn network, lại vừa có write conflicts, kết quả khó diễn giải. Bắt đầu một fault với expected result rõ, sau đó mới chạy chaos scenarios tổng hợp.

## 14. Kiểm thử transaction khi primary failover

### 14.1. Các mốc thời gian quan trọng

~~~text
T0: start transaction on primary P1
T1: debit and credit
T2: commit attempt
T3: P1 steps down / network interrupted
T4: P2 becomes primary
T5: client reconnects and resolves/retries
T6: verify balances + transfer receipt
~~~

Để thực hiện tốt, log **attempt ID, transfer ID, error labels, cluster time/session context đã lọc nhạy cảm** và thời điểm các events.

### 14.2. Lỗi trước commit

Nếu primary failover xảy ra trước khi transaction commit, attempt thường không thể tiếp tục như cũ và driver có thể thông báo transient error. Retry cần:

1. Một transaction attempt mới.
2. Reread account balances.
3. Re-evaluate funds/currency/idempotency.
4. Commit trên primary mới theo transaction options.

Không reuse những document snapshots cũ làm cơ sở cho một debit không có predicate.

### 14.3. Lỗi quanh commit

Nếu network break xảy ra quanh commit, ứng dụng có thể không biết kết quả. **Không suy từ việc primary cũ biến mất rằng transaction chắc chắn abort**.

Commit retry theo driver rules hoặc reconciliation bằng **transferId** mới xác định business outcome một cách có kiểm soát.

### 14.4. Majority write concern

Test durability cần phân biệt:

~~~text
Commit acknowledged with majority
    vs
Commit acknowledged under weaker concern
~~~

Việc một primary vừa trả kết quả chưa đủ để kiểm thử majority durability nếu transaction options dùng write concern không phù hợp. Trong replica set ba members, nếu đa số không available, majority writes có thể chờ/thất bại theo timeout/config, và application cần chịu được trạng thái bất định.

### 14.5. Secondary reads sau failover

Sau khi transaction đã commit, một secondary có thể chưa apply hết thay đổi:

~~~text
Read from primary: new balance
Read from lagging secondary: old balance
~~~

Không diễn giải sự chênh tạm thời này là partial transaction commit. Khi test invariant cần xác định **read preference/read concern/session causal guarantees** để tránh nhầm replication lag với rollback.

### 14.6. Không suy “exactly once” từ majority

Majority commit tăng bảo đảm durability của database. Nó **không** ngăn một HTTP client gửi lại toàn bộ business request sau khi response mất. Phần **exactly-once business effect** cần idempotency key, unique constraints và reconciliation.

## 15. Spring Data MongoDB: MongoTransactionManager

Trong ứng dụng Spring, bạn có thể dùng **MongoTransactionManager** để tích hợp MongoDB transactions với **@Transactional**.

### 15.1. Cấu hình transaction manager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTxConfiguration {

    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory databaseFactory) {
        return new MongoTransactionManager(databaseFactory);
    }
}
~~~

Các configuration APIs và transaction defaults có thể thay đổi theo Spring Data MongoDB version. Khi cần **snapshot/majority** cụ thể, định nghĩa transaction options và đảm bảo MongoTransactionManager được cấu hình đúng, không giả định defaults giống ví dụ Java Driver.

### 15.2. Dùng @Transactional

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WalletApplicationService {

    private final MongoTemplate template;

    public WalletApplicationService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void transferOnce(
            String transferId,
            String sourceId,
            String destinationId,
            long amountUnits) {

        Query debitQuery = Query.query(
                Criteria.where("_id").is(sourceId)
                        .and("balanceUnits").gte(amountUnits)
        );

        var debit = template.updateFirst(
                debitQuery,
                new Update().inc("balanceUnits", -amountUnits),
                "accounts"
        );

        if (debit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Source missing or insufficient funds");
        }

        Query creditQuery = Query.query(
                Criteria.where("_id").is(destinationId)
        );

        var credit = template.updateFirst(
                creditQuery,
                new Update().inc("balanceUnits", amountUnits),
                "accounts"
        );

        if (credit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Destination missing");
        }

        template.insert(
                new org.bson.Document("_id", transferId)
                        .append("sourceId", sourceId)
                        .append("destinationId", destinationId)
                        .append("amountUnits", amountUnits)
                        .append("state", "COMMITTED"),
                "transfers"
        );
    }
}
~~~

Đây là minh họa **transaction demarcation**, chưa phải transfer service hoàn chỉnh: cần kiểm tra currency, permissions, idempotency lookup và xử lý duplicate concurrency giống ví dụ Java Driver. Phương thức transactional chỉ hoạt động nếu Spring thực sự áp dụng **transaction interceptor**.

### 15.3. Spring session binding

Khi gọi MongoTemplate/MongoRepository bên trong một method giao dịch được quản lý đúng, Spring Data liên kết session vào transaction context theo cơ chế framework.

Không tự tạo MongoClient mới bên trong method rồi gọi raw driver không kèm session, vì nó có thể nằm ngoài Spring-managed transaction.

### 15.4. Rollback rules của @Transactional

Mặc định Spring **rollback với unchecked exceptions** như RuntimeException và Error, còn checked exception có thể cần rule rõ như **rollbackFor**. Nếu method bắt exception rồi return success:

~~~java
@Transactional
public void badExample() {
    try {
        // debit...
        // credit fails...
    } catch (Exception ex) {
        // Swallows exception; transaction manager may commit.
    }
}
~~~

thì không thể giả định transaction tự abort. Nên rethrow exception hoặc đánh dấu rollback theo supported Spring API và policy.

### 15.5. Self-invocation và proxy

Nếu một method của cùng object gọi trực tiếp method gắn **@Transactional** bằng **this.transferOnce(...)**, Spring proxy-based transaction interception có thể **không được áp dụng**.

Kiểm thử integration phải chứng minh transaction thực sự hoạt động khi gọi qua service bean/proxy bình thường. Không tin annotation xuất hiện trong source code là bằng chứng transactions được kích hoạt.

### 15.6. @Transactional không tự giải quyết retries

**MongoTransactionManager/@Transactional chủ yếu quản lý start/commit/rollback**. Nó không đồng nghĩa với Java Driver **withTransaction callback retry** trong mọi phiên bản/trường hợp.

Nếu cần retry transient, xây chính sách ở **outer orchestration layer**, bảo đảm lần retry gọi lại **một invocation transactional mới qua proxy**, không loop bên trong cùng transaction đã lỗi.

Đối với **UnknownTransactionCommitResult**, không được đơn giản retry toàn @Transactional method mà không có business idempotency/reconciliation; Spring transaction completion và driver commit handling phải được hiểu theo version.

### 15.7. Không trộn transaction managers thiếu chủ đích

Một ứng dụng có cả **DataSourceTransactionManager/JpaTransactionManager** và **MongoTransactionManager** cần chỉ định đúng manager. Một @Transactional mặc định có thể chạy transaction của SQL nhưng Mongo operations không nằm trong cùng atomic unit.

MongoDB transaction **không tự tạo distributed transaction với SQL, Kafka hoặc một HTTP service**. Để phối hợp với hệ ngoài, cần outbox, saga hoặc mô hình khác có guarantees rõ ràng.

## 16. Unit test và integration test cho commit/abort bằng Java

Đối với MongoDB transaction, **unit test với mock repository không đủ** để xác nhận server atomicity. Cần ít nhất một bộ **integration tests kết nối replica set thật** và assertions trên dữ liệu đã lưu.

### 16.1. Mỗi tầng test chứng minh điều gì?

| Tầng | Kiểm tra được | Không tự chứng minh |
|---|---|---|
| Unit test domain | Input validation, amount, parameter mismatch. | Server commit/rollback. |
| Mock transaction service | Thứ tự calls, exception propagation. | Dữ liệu server thực sự rollback. |
| Single-node replica set integration | Session wiring, commit/abort, unique index/idempotency. | Multi-node failover, majority availability. |
| Three-node replica set integration | Election, majority commit, retry behavior, secondary lag. | Tất cả production failure modes. |
| End-to-end/API test | HTTP timeout/retry, response và business idempotency. | Các boundary ngoài nếu không mô phỏng broker/gateway. |

### 16.2. Test happy path

Ví dụ với JUnit 5, dùng **MONGODB_TEST_URI** chỉ vào test replica set và fixture IDs duy nhất:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.UUID;

public class TransferIntegrationTest {

    @Test
    void commitUpdatesBothAccountsAndReceipt() {
        String uri = System.getenv("MONGODB_TEST_URI");
        assertNotNull(uri, "Use a dedicated test replica set");

        try (MongoClient client = MongoClients.create(uri)) {
            var database = client.getDatabase("wallet_txn_lab");
            MongoCollection<Document> accounts =
                    database.getCollection("accounts");
            MongoCollection<Document> transfers =
                    database.getCollection("transfers");

            String prefix = "it-" + UUID.randomUUID();
            String sourceId = prefix + "-source";
            String destinationId = prefix + "-destination";
            String transferId = prefix + "-transfer";

            accounts.insertMany(List.of(
                    new Document("_id", sourceId)
                            .append("currency", "VND")
                            .append("balanceUnits", 500000L),
                    new Document("_id", destinationId)
                            .append("currency", "VND")
                            .append("balanceUnits", 300000L)
            ));

            var service = new TransferService(client);
            var receipt = service.transfer(
                    new TransferRequest(
                            transferId,
                            sourceId,
                            destinationId,
                            "VND",
                            150000L
                    )
            );

            Document source = accounts.find(
                    new Document("_id", sourceId)
            ).first();
            Document destination = accounts.find(
                    new Document("_id", destinationId)
            ).first();

            assertNotNull(source);
            assertNotNull(destination);
            assertEquals(350000L,
                    source.getLong("balanceUnits"));
            assertEquals(450000L,
                    destination.getLong("balanceUnits"));
            assertEquals(800000L,
                    source.getLong("balanceUnits")
                            + destination.getLong("balanceUnits"));

            assertEquals(transferId, receipt.getString("_id"));
            assertEquals(1L, transfers.countDocuments(
                    new Document("_id", transferId)
            ));
        }
    }
}
~~~

Đây là test pattern cho lab, chưa có cleanup tự động. Trong test suite thật, **cô lập database/collections hoặc chỉ dọn prefix IDs do test sở hữu**, tránh xóa cả collection chia sẻ. Các assertions về majority durability cần dùng đúng read preference/concern.

### 16.3. Test abort sau debit

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction(txOptions);

    try {
        accounts.updateOne(
                session,
                Filters.eq("_id", sourceId),
                Updates.inc("balanceUnits", -10000L)
        );

        throw new IllegalStateException(
                "Simulated failure after debit");
    } catch (IllegalStateException ex) {
        session.abortTransaction();
    }
}

Document source = accounts.find(
        Filters.eq("_id", sourceId)
).first();
assertEquals(originalBalance,
        source.getLong("balanceUnits"));
~~~

Giả sử các biến fixture được khởi tạo trong test. Đây là test **transaction abort**, không phải test network fault hoặc ambiguous commit.

### 16.4. Test thiếu session — anti-pattern

~~~java
session.startTransaction();
accounts.updateOne(Filters.eq("_id", sourceId), update);
session.abortTransaction();
~~~

Vì updateOne thiếu session argument, write có thể commit độc lập và **abort không đảo ngược nó**. Có thể dùng tình huống này làm negative diagnostic trong một fixture cô lập; không dùng trong application code.

### 16.5. Test idempotent resend

1. Gọi service.transfer lần đầu với ID ổn định.
2. Đọc balances và receipt.
3. Gọi lại service.transfer với cùng ID/parameters.
4. Xác nhận balances không đổi thêm và receipt count vẫn 1.
5. Xác nhận response lần hai diễn giải là cùng business result.

### 16.6. Test cùng ID nhưng khác parameters

~~~text
First:  ID=req-100, amount=150000
Second: ID=req-100, amount=200000
~~~

Kỳ vọng conflict và không debit lần hai. Chỉ kiểm tra ID tồn tại rồi trả success mà không so payload là sai semantics idempotency.

### 16.7. Test write conflict

Hai sessions và hai threads:

~~~text
A balance = 200 units
T1 reads A=200, wants debit 150
T2 reads A=200, wants debit 150
~~~

Một attempt có thể gặp conflict và phải retry với snapshot mới, lúc đó có thể thấy không đủ tiền.

Expected invariants:

~~~text
A >= 0
sum(A,B,C) unchanged
at most one 150-unit transfer committed
each receipt corresponds to matching debit/credit
~~~

Sử dụng **CountDownLatch/CyclicBarrier** trong test harness để đồng bộ thời điểm race; không phụ thuộc một sleep cố định.

### 16.8. Test concurrent duplicate request

Hai threads gửi cùng transferId. Một attempt có thể thành công, attempt còn lại gặp duplicate key hoặc conflict cần reconciliation. Sau cùng:

~~~text
receipt count = 1
debit happened once
credit happened once
sum balance invariant holds
~~~

Không bắt buộc cả hai API calls đều trả 200 nếu chưa có lớp reconcile; nhưng **không được hai business effects**.

### 16.9. Test failover không giống test lỗi trong code

Throw IllegalStateException sau debit chỉ chứng minh abort, không kiểm tra election. Test failover cần nhiều nodes và fault injector có kiểm soát. Báo cáo rõ lỗi đã gây ra và error labels quan sát được.

### 16.10. Testcontainers và test replica set

Một số phiên bản **Testcontainers MongoDB module** hỗ trợ chạy MongoDB container dưới dạng replica set và lấy URI kết nối tương ứng. Workflow:

~~~text
JUnit lifecycle:
  start isolated replica set container(s)
  wait for PRIMARY
  create collections and indexes
  seed fixture documents
  execute transaction test
  inspect committed state
  stop/dispose test deployment
~~~

Kiểm tra APIs theo Testcontainers version. Một container replica set phù hợp commit/abort, nhưng **không thể chứng minh multi-node primary failover**.

## 17. HTTP idempotency và business-level resend

Client có thể retry request vì timeout ngay cả khi MongoDB đã commit.

### 17.1. Đặt idempotency key ở API boundary

Ví dụ:

~~~http
POST /transfers HTTP/1.1
Idempotency-Key: transfer-req-1001
Content-Type: application/json

{
  "sourceId": "A",
  "destinationId": "B",
  "amountUnits": 150000,
  "currency": "VND"
}
~~~

Mỗi **logical business request** sử dụng key ổn định. Retry sau timeout phải giữ **cùng key**; một transfer mới phải có key mới.

### 17.2. Key trùng phải so payload

~~~text
Idempotency-Key = k-1

Request A: A -> B, 150000 VND
Request B: A -> C, 150000 VND
~~~

Không trả thành công của A cho B âm thầm. Key phải gắn với một business action rõ, so immutable fields hoặc canonical request fingerprint (và chú ý cách chuẩn hóa).

### 17.3. Khi outcome vẫn UNKNOWN

~~~text
Client receives timeout / pending / status unknown
                |
                v
GET /transfers/{transferId}
                |
                v
Server checks persisted receipt and reconciles
                |
                v
COMMITTED / definitively FAILED / still UNKNOWN
~~~

API contract có thể chọn status endpoint, retry cùng key hoặc workflow pending. Không tự quy UNKNOWN thành abort để gửi một business request mới với ID khác.

### 17.4. Unique index và retention

Unique **_id** tạo persistent deduplication boundary nhưng vẫn cần:

- Dùng cùng stable ID trên mọi code paths.
- Debit/credit/receipt trong một transaction.
- Xử lý race và parameter mismatch.
- Chính sách lưu receipt/idempotency key đủ dài.

Nếu receipt được xóa sau 24 giờ nhưng client có thể retry cùng key sau 30 ngày, cơ chế chống double debit mất tác dụng sau khi xóa. Retention phải phù hợp replay horizon, business audit và quy định dữ liệu.

### 17.5. Replay message broker

Một consumer nhận:

~~~text
TransferRequested(eventId=e-101, transferId=t-101)
~~~

Broker có thể redeliver event khi consumer crash trước ACK. Consumer nên dùng **transferId/eventId có uniqueness và durable deduplication** trong phạm vi xử lý, thay vì mỗi lần nhận sinh một transferId mới.

### 17.6. Exactly-once phải chỉ rõ phạm vi

MongoDB transaction bảo đảm atomicity của MongoDB writes trong phạm vi đã định nghĩa. Nó không tự bảo đảm một lệnh gửi tới **payment gateway** hoặc **email server** được gọi đúng một lần.

Không tự tuyên bố exactly-once end-to-end nếu chưa có cơ chế idempotency và recovery cho tất cả boundaries.

## 18. Transactional outbox cho side effects sau commit

Ứng dụng có thể muốn publish một event khi transfer đã commit. Nếu publish ngay trong callback:

~~~text
Transaction attempt 1:
  debit/credit
  send Kafka event
  transaction aborts after write conflict

Transaction attempt 2:
  debit/credit
  send Kafka event again
  commit
~~~

Broker đã nhận event từ attempt abort. Transaction MongoDB **không rollback được event broker**.

### 18.1. Lưu outbox trong cùng transaction

Một giải pháp là thêm một record vào **wallet.outbox** trong cùng transaction với debit/credit/transfer:

~~~javascript
{
  _id: "outbox-transfer-req-1001",
  eventType: "TransferCommitted",
  aggregateId: "request-1001",
  payload: {
    sourceId: "A",
    destinationId: "B",
    amountUnits: NumberLong("150000")
  },
  state: "PENDING",
  createdAt: ISODate("2026-11-14T00:00:00Z")
}
~~~

Trước transaction, collection/index cần được tạo. Trong callback:

~~~text
debit A
credit B
insert transfer receipt
insert outbox event
commit
~~~

Nếu transaction abort, outbox event cũng không được commit; dispatcher không thấy event từ transaction đã abort.

### 18.2. Dispatcher chạy sau commit

~~~text
MongoDB transaction COMMITTED
           |
           v
Outbox record PENDING
           |
           v
Background dispatcher
           |
           v
Publish to broker
           |
           v
Mark outbox record SENT
~~~

Nếu dispatcher publish thành công rồi crash trước khi đánh dấu SENT, event có thể được publish **lại**. Vì vậy outbox thường cung cấp **at-least-once delivery**; consumer vẫn cần deduplication/idempotency theo eventId.

### 18.3. Outbox không phải distributed ACID transaction

MongoDB commit và broker ACK không tạo một ACID transaction xuyên hai hệ. Outbox giúp đảm bảo ý định publish được lưu bền cùng business data và có thể retry sau crash.

### 18.4. Compensating transaction

Nếu một external payment service đã xử lý tiền nhưng bước khác thất bại, có thể cần **saga/compensating action**:

~~~text
Original transaction COMMITTED
   |
   v
New business action reverses effect
   |
   v
New transaction/ledger entry with reference
~~~

Compensation phải có ID, authorization và audit riêng. Không gọi **abortTransaction()** để đảo ngược một commit đã thành công.

### 18.5. Kiểm thử outbox

Các test quan trọng:

1. Transfer commit → outbox event có đúng một record.
2. Transfer abort → không có outbox event committed.
3. Dispatcher crash trước publish → retry được.
4. Dispatcher crash sau publish trước ACK/markSent → consumer dedup được.
5. Replay cùng transferId → không tạo outbox event nghiệp vụ trùng.

## 19. Transaction isolation không có nghĩa mọi invariant đều tự an toàn

Một transaction có snapshot đọc nhất quán và atomic writes, nhưng không được xem là công cụ tự động enforce mọi **cross-document constraint** theo serializable semantics.

### 19.1. Concurrent transactions trên cùng account

Nếu hai transactions cùng update document nguồn A, write conflict hoặc conditional update có thể khiến một transaction phải retry. Với predicate kiểm tra số dư, attempt mới có thể phát hiện không còn đủ funds.

### 19.2. Write skew khi ghi hai documents khác nhau

Giả sử hệ thống có quy tắc luôn phải có **ít nhất một bác sĩ trực ca**:

~~~text
Doctor A: onCall=true
Doctor B: onCall=true
~~~

Hai transactions đồng thời cùng đọc snapshot có hai bác sĩ trực:

~~~text
T1 reads A,B; sets A.onCall=false
T2 reads A,B; sets B.onCall=false
~~~

Nếu hai transactions chỉ ghi hai documents khác nhau và không có ràng buộc write conflict/guard chung, một kiểu **write skew** có thể làm trạng thái cuối cùng không còn ai trực.

Đây là lý do **snapshot isolation không nên bị diễn giải là serializable business invariants tự động**.

### 19.3. Cách enforce invariant

Tùy domain:

- Ghi vào một **guard/coordination document** chung.
- Dùng conditional updates trên document đại diện invariant.
- Dùng unique indexes/schema constraints khi có thể biểu diễn được.
- Thiết kế lại data model để constraint quan trọng nằm trong một document atomic.
- Xử lý serialization/retries theo architecture review.

Không chỉ thêm **readConcern: snapshot** và bỏ validation.

### 19.4. Kiểm thử concurrency có chủ đích

Test đồng thời phải cố tình tạo race có thể xảy ra bằng synchronization barriers, không chỉ spawn threads và hy vọng tranh chấp xuất hiện.

Kỳ vọng của test phải ghi rõ:

~~~text
Correctness invariant
Conflicting read/write sets
Expected committed or aborted attempts
Retry conditions
Final persisted state
~~~

Nếu constraint được bảo đảm bằng **unique index**, kiểm thử cả duplicate races và error handling.

## 20. Quan sát transaction và retry trong môi trường test

Một transaction test thất bại cần đủ dữ liệu để phân biệt lỗi nghiệp vụ, lỗi mapping/session, transient write conflict, primary election, kết quả commit unknown và retry exhaustion.

### 20.1. Các metrics nên thu thập

| Metric ý tưởng | Ý nghĩa | Nhãn có kiểm soát |
|---|---|---|
| **txn.started** | Số transaction attempts. | service, operation, environment. |
| **txn.committed** | Số attempts xác nhận commit. | service, operation. |
| **txn.aborted** | Số attempts abort. | service, reason category. |
| **txn.body.retry** | Số lần retry toàn body. | operation, error category. |
| **txn.commit.retry** | Số lần retry commit. | service, operation. |
| **txn.commit.unknown** | Số outcomes chưa xác định. | operation, error category. |
| **txn.duration** | Thời gian body + commit. | operation. |
| **txn.write.conflict** | Write-conflict errors. | operation. |
| **txn.idempotent.hit** | Trả kết quả từ receipt cũ. | operation. |
| **txn.idempotent.conflict** | Key trùng nhưng payload khác. | operation. |
| **txn.reconciliation.pending** | Outcomes chưa giải quyết. | service. |

Tên metrics ở bảng **do ứng dụng tự định nghĩa**, không phải tất cả đều do MongoDB export tự động.

### 20.2. ServerStatus

Trên mongod member với quyền thích hợp:

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });
printjson(s.transactions);
~~~

Server versions có thể cung cấp các gauges/counters về transactions đang mở, active, committed và aborted. Fields như **currentOpen**, **currentActive**, **totalCommitted**, **totalAborted** có thể khác nhau theo version và topology.

Với cumulative counters:

~~~text
totalCommitted(t0) = 12300
totalCommitted(t1) = 12420
elapsed = 60 seconds

committedRate = (12420 - 12300) / 60 = 2/s
~~~

Không vẽ raw counter như QPS; xử lý process restart/counter reset.

### 20.3. Logs, profiler và current operations

Logs/profiler có thể chứa lỗi transaction, write conflicts, elections, slow operations và metadata nhạy cảm. Không bật profiling mức cao không kiểm soát trên production chỉ để làm bài test.

Các công cụ **currentOp/$currentOp** theo server version có thể giúp điều tra transactions đang chạy. Nhưng snapshot có thể rất ngắn, output lớn và chứa thông tin hạ tầng/query; ưu tiên monitoring chính thức và sampling có giới hạn.

### 20.4. Client-side tracing

Một logical request có thể tạo nhiều attempts:

~~~text
traceId=abc
transferId=request-1001
  attempt=1 -> TransientTransactionError
  attempt=2 -> commit returned UnknownTransactionCommitResult
  attempt=2 -> commit retry succeeded
~~~

Nên ghi **attempt number**, phase (**body/commit**) và error label/category, không log raw balances, token, tài khoản hay toàn bộ documents.

### 20.5. Không đếm attempts thành transfers

~~~text
Logical business transfers: 1
Transaction body attempts:  3
Commit calls:               possibly >3
Committed receipts:         1
~~~

Nếu dashboard cộng mọi attempts và gọi là “số tiền đã chuyển”, business metrics sẽ sai. Nên tính kết quả nghiệp vụ từ durable receipt/ledger và invariants.

### 20.6. Alerts có ngữ cảnh

~~~text
High TransientTransactionError + primary elections
  -> investigate replica set health

UnknownTransactionCommitResult + network errors
  -> investigate transport and unresolved commit outcomes

Transaction p95 rising + write conflicts
  -> investigate contention and transaction duration

Reconciliation queue growing
  -> protect business SLA and replay semantics
~~~

Không alert chỉ vì **txn.aborted > 0**: các business abort hợp lệ, chẳng hạn insufficient funds, không đồng nghĩa cluster có sự cố.

## 21. Giới hạn và chi phí của multi-document transactions

### 21.1. Transaction không miễn phí

Multi-document transaction có thể làm tăng cache/snapshot pressure, lock waits/write conflicts, replication work, latency và retry overhead. Nếu invariant nằm trong một document, một atomic single-document update có thể đơn giản và rẻ hơn.

### 21.2. Transaction lifetime

MongoDB có **transaction lifetime limit** và các timeout/resource constraints theo server version/configuration. Transaction quá lâu có thể bị abort.

Không viết:

~~~text
startTransaction
  -> scan huge collection
  -> call external payment API
  -> wait for customer OTP
  -> update three accounts
  -> commit
~~~

Giữ transaction ngắn, đưa external I/O và user interactions ra khỏi transaction.

### 21.3. Transaction rất lớn

Một batch hàng triệu documents trong cùng transaction có thể giữ nhiều resources, dễ conflict, gây chậm replication và khó retry. Khi business cho phép, chia thành nhiều batches có checkpoints/idempotency; không gói tất cả vào một ACID transaction chỉ vì cảm giác an toàn.

### 21.4. Collection/index creation

MongoDB hỗ trợ một số DDL trong transaction theo version/điều kiện nhưng có giới hạn. Với test commit/abort nghiệp vụ, **tạo collections/indexes trước** để tránh DDL che khuất mục tiêu của test.

### 21.5. Sharded transactions

Transactions cũng có thể chạy trên sharded cluster hỗ trợ, nhưng multi-shard coordination làm latency/failure modes phức tạp hơn. Kết quả thử trên single-node replica set không chứng minh performance của distributed transaction chạm nhiều shards.

### 21.6. Snapshot không phải serializable

ReadConcern.SNAPSHOT không tự enforce tất cả cross-document constraints; write skew vẫn là rủi ro nếu transactions ghi các documents khác nhau dựa trên cùng điều kiện đọc. Dùng guard document, conditional writes, unique indexes hoặc data-model changes khi cần.

### 21.7. Long transaction và primary failover

Một transaction đang mở có thể bị abort khi election. Giảm thời gian callback, dùng indexes đúng, không chờ I/O ngoài DB và đo **p95/p99 duration** lẫn transient errors.

### 21.8. Retry storm

Nếu hàng trăm ứng dụng retry không backoff khi primary vừa được bầu, cluster có thể quá tải lần nữa. Cần deadlines, backoff/jitter và circuit breakers theo architecture.

### 21.9. Retry budget phụ thuộc business SLO

API realtime có deadline 2 giây có thể không chờ election 10 giây. Nó cần trả **pending/unknown** và có reconciliation. Batch worker có thể chờ lâu hơn. Không một vòng lặp vô hạn phục vụ tốt cả hai.

## 22. Runbook chẩn đoán khi transaction thất bại

### 22.1. Case A — Abort nhưng account vẫn bị trừ

~~~text
Application says transaction aborted.
Account A balance decreased anyway.
~~~

Điều tra:

1. Debit có gọi collection method kèm **ClientSession** không?
2. Các thao tác dùng cùng client/session context?
3. Spring @Transactional có thực sự dùng MongoTransactionManager và proxy?
4. Có raw driver write nằm ngoài session không?
5. Có đang đọc nhầm test fixture hoặc secondary stale data?

Nếu write chạy ngoài transaction, abort **không undo** nó. Sửa session propagation và thêm integration assertion.

### 22.2. Case B — Commit response timeout

~~~text
commitTransaction sent
network timeout
result unknown
~~~

Không tạo transfer ID mới. Khi còn cùng transaction/session, xử lý retry commit theo driver rules. Nếu HTTP request đã kết thúc, dùng durable transferId để reconcile và trả trạng thái appropriate.

### 22.3. Case C — Hai receipts cho một nghiệp vụ

Kiểm tra:

- Retry có sinh transferId mới không?
- Hai services có dùng hai key spaces?
- Có path không dùng idempotency?
- Records cũ đã bị xóa bởi TTL/retention?
- Có writes tới collections khác không?

Unique _id ngăn **cùng ID** trong cùng collection, không tự biết hai IDs khác nhau đại diện cùng nghiệp vụ.

### 22.4. Case D — Transient errors tăng sau deploy

Kiểm tra transaction duration, query plans, scans, hot documents, concurrent updates, primary election và network/disk/cache metrics. Không chỉ tăng số retries khi root cause là contention hoặc query nặng.

### 22.5. Case E — Callback gửi email hai lần

Callback được retry sau lỗi transient; external email đã gửi từ attempt abort. Dùng outbox trong transaction và dispatcher sau commit, có deduplication.

### 22.6. Case F — Spring @Transactional không có tác dụng

Checklist:

- MongoTransactionManager đã đăng ký đúng?
- Annotation chỉ định đúng manager?
- Method được gọi qua proxy, không self-invocation?
- Exception có bị swallow?
- Repositories/templates dùng cùng transaction context?
- Server có là replica set không?

Một annotation tồn tại không phải bằng chứng transaction đã được mở.

### 22.7. Case G — Duplicate key ở receipt

So existing record với business input. Nếu trùng parameters và record đã COMMITTED, trả kết quả cũ. Nếu khác, trả conflict. Không chuyển duplicate key thành success vô điều kiện.

### 22.8. Case H — Hai transfers đều muốn rút 150 từ 200

Kiểm tra:

1. Debit dùng conditional predicate balanceUnits >= amount.
2. Cả hai attempts cập nhật cùng source document.
3. Write conflict được xử lý bằng attempt mới.
4. Mỗi attempt reread tài khoản và reevaluate funds.
5. Không có overdraft hoặc double receipt.

Nếu code đọc balance ngoài transaction, sau đó update không điều kiện, có thể gây overdraft.

### 22.9. Case I — Majority commit không thể hoàn tất

Kiểm tra replica set members, majority availability, replication lag, write concern timeout, disk/network pressure. Đừng giảm write concern chỉ để ngừng báo lỗi khi chưa đánh giá durability và business risk.

### 22.10. Case J — Đọc số dư cũ sau commit

Nếu đọc secondary, có thể do replication lag. Chọn primary/read concern/causal consistency phù hợp khi verify. Nếu primary không thấy data sau confirmed commit, kiểm tra namespace, receipt, transaction/session và error handling.

### 22.11. Case K — API trả timeout nhưng receipt đã COMMITTED

Response bị mất sau commit. Retry cùng idempotency key phải trả existing result, không debit lần hai.

### 22.12. Case L — Cần hoàn tiền sau commit

Tạo **compensating/reversal transaction** có transferId và audit trail riêng, tham chiếu transaction ban đầu. AbortTransaction không đảo ngược commit đã hoàn tất.

### 22.13. Quy trình xử lý UNKNOWN

~~~text
1. Identify original transferId and immutable parameters
2. Check driver error phase and labels
3. If same session still active and label allows:
     retry same commit, bounded by deadline
4. Otherwise query durable receipt by original ID
5. If receipt COMMITTED with matching parameters:
     return existing business result
6. If receipt absent but outcome still uncertain:
     move to pending reconciliation, do not blindly replay
7. When outcome is conclusively resolved:
     update client status/audit record
~~~

Một **missing receipt tại một thời điểm** không luôn chứng minh transaction chắc chắn abort, nhất là khi commit outcome còn unknown hoặc đang đọc secondary lag. Có thể cần đợi/retry theo consistent observation policy.

## 23. Checklist kiểm thử trước khi phát hành

### 23.1. Môi trường và cấu hình

- [ ] MongoDB chạy replica set, không chỉ standalone.
- [ ] Phiên bản MongoDB/driver/Spring Data phù hợp transaction support.
- [ ] Client URI khai báo replica set và hosts reachable.
- [ ] Collections/indexes/fixtures tồn tại trước transaction.
- [ ] Tài khoản test có quyền phù hợp, không dùng production credentials.
- [ ] Data riêng test; cleanup chỉ dữ liệu test sở hữu.
- [ ] Transaction options được chọn có giải thích read concern, write concern và read preference.
- [ ] Có single-node test và multi-node test cho failover cần thiết.

### 23.2. Commit

- [ ] Debit A, credit B và insert receipt nằm trong một transaction.
- [ ] Mọi operations dùng cùng session/transaction manager.
- [ ] Khi commit thành công, số dư A/B đúng.
- [ ] Tổng số dư bảo toàn theo invariants của fixture.
- [ ] Transfer receipt count bằng 1 với stable key.
- [ ] Cùng currency và parameters theo business contract.
- [ ] Đọc trạng thái bằng consistent read không nhầm secondary lag.

### 23.3. Abort/rollback

- [ ] Throw lỗi sau debit → không thay đổi A/B sau abort.
- [ ] Recipient không tồn tại → rollback debit.
- [ ] Insufficient balance → transaction abort/không commit.
- [ ] Currency mismatch → không có partial debit.
- [ ] Duplicate key không để lại partial state.
- [ ] Không có external side effect từ aborted callback.
- [ ] Không nuốt exception trong Spring method rồi commit.

### 23.4. Retry và unknown commit

- [ ] TransientTransactionError được retry đúng **toàn transaction**.
- [ ] UnknownTransactionCommitResult được retry đúng **commit cùng transaction**.
- [ ] Retry có giới hạn và backoff policy.
- [ ] Body callback không gọi external service sinh side effects.
- [ ] Mỗi logical request có stable idempotency key.
- [ ] HTTP retry sau commit không debit lần hai.
- [ ] Same key/different parameters trả conflict.
- [ ] Two concurrent same-key requests không tạo hai business effects.
- [ ] Unknown sau deadline có pending/reconciliation mechanism.
- [ ] Log/metrics phân biệt body retry và commit retry.

### 23.5. Replica set failover

- [ ] Multi-node test có primary election thực.
- [ ] Majority write concern được kiểm tra.
- [ ] Node unavailability không làm API retry vô hạn.
- [ ] Election recovery có deadline/polling thay vì sleep ngắn cố định.
- [ ] Sau failover, invariant và receipt được kiểm tra.
- [ ] Replication lag được phân biệt với rollback.
- [ ] Failpoints/stepdown chỉ chạy trên lab và được cleanup.

### 23.6. Spring Data

- [ ] MongoTransactionManager bean đăng ký đúng.
- [ ] @Transactional chỉ định đúng transaction manager.
- [ ] Method gọi qua Spring proxy.
- [ ] Checked/unchecked exception rollback rules rõ.
- [ ] Không tạo client/raw driver write ngoài transaction.
- [ ] Retry outer layer tạo attempt mới đúng cách.
- [ ] Không gọi MongoDB transaction bên trong SQL @Transactional rồi kỳ vọng distributed ACID.

### 23.7. Vận hành và bảo mật

- [ ] Có metrics duration, aborts, retries và unknown outcomes.
- [ ] Có bounded reconciliation queue/ownership.
- [ ] Logs không chứa raw balances/PII/secrets.
- [ ] Transaction body ngắn, dùng indexes phù hợp.
- [ ] Cảnh báo phân biệt business abort với cluster errors.
- [ ] Backup/recovery plan và audit cho receipt/outbox.
- [ ] Có quy trình compensation nếu business reversal sau commit.

## 24. Bài thực hành

Các bài tập phải chạy trên **database thử nghiệm được phép**, không chạy commands phá kết nối hay bước down primary trên production. Với những bài fault injection, người học có thể viết test plan/pseudocode nếu không có multi-node lab.

### Bài 1 — Sơ đồ replica set

Vẽ sơ đồ một primary và hai secondaries, đường kết nối từ Java Driver và luồng writes/replication. Giải thích vì sao ba members không có nghĩa ba shards.

### Bài 2 — Standalone và single-node replica set

Phân biệt mongod standalone với một single-node replica set có cùng một mongod process. Môi trường nào có thể thực hành multi-document transaction theo supported versions?

### Bài 3 — Tạo lab replica set

Thiết lập một replica set lab và chạy **hello**, **rs.status**. Giải thích khi nào node sẵn sàng nhận transaction và vì sao phải đợi PRIMARY.

### Bài 4 — Lập fixtures

Tạo hai accounts A=500000 và B=300000, cùng VND, và một transfers collection. Sử dụng IDs dành riêng cho lab, không xóa records của người khác.

### Bài 5 — Atomic một document

Viết updateOne thay đổi hai fields trong Account A. Vì sao operation này đã atomic cấp document mà không cần multi-document transaction?

### Bài 6 — Ba operations không transaction

Mô tả những trạng thái nửa vời có thể xảy ra khi debit A, credit B, insert receipt được chạy thành ba commands độc lập. Vì sao retryWrites không biến chúng thành một ACID transaction?

### Bài 7 — Commit bằng mongosh

Tạo ClientSession, startTransaction, debit A, credit B, insert receipt, commit. Kiểm tra cả balances và receipt sau commit.

### Bài 8 — Abort sau debit

Inject một application exception sau khi debit A nhưng trước khi credit B. Gọi abortTransaction. Đọc lại balances và chứng minh không có write nửa vời.

### Bài 9 — Operation thiếu session

Viết một test âm tính: startTransaction rồi vô tình gọi updateOne không có session argument. Giải thích vì sao abort không undo write độc lập. Chỉ thực hiện trên fixture lab.

### Bài 10 — Insufficient balance

Cho A=100, yêu cầu transfer 150. Viết debit predicate **balanceUnits >= amount** và kiểm tra matchedCount. Khi matchedCount=0, ứng dụng nên làm gì?

### Bài 11 — Destination missing

Debit A trong transaction, rồi thử credit một account B không tồn tại. Xác nhận throw/abort giữ nguyên số dư A.

### Bài 12 — Currency mismatch

Cho A=VND và B=USD. Viết predicates bảo vệ currency cho cả debit/credit. Khi B không match, transaction phải có trạng thái gì?

### Bài 13 — Commit receipt

Lưu transfer record có ID duy nhất trong cùng transaction với balances. Vì sao receipt không được ghi trong một command bên ngoài transaction sau commit?

### Bài 14 — Invariant tổng số dư

Trong fixture không có phí, chuyển 150000 units từ A sang B. Viết assertions:

~~~text
A_after = A_before - 150000
B_after = B_before + 150000
A_after + B_after = A_before + B_before
~~~

### Bài 15 — ReadConcern SNAPSHOT

Giải thích tại sao transaction reads dùng snapshot và write concern majority ở commit có mục đích khác nhau. Có phải snapshot tự làm tất cả business invariants serializable không?

### Bài 16 — Retry toàn transaction

Vẽ flow khi một write trong body trả lỗi gắn **TransientTransactionError**. Attempt nào phải bị bỏ và operations nào cần chạy lại?

### Bài 17 — Retry commit

Vẽ flow khi commitTransaction trả lỗi gắn **UnknownTransactionCommitResult**. Tại sao phải retry commit của cùng transaction thay vì chạy lại debit?

### Bài 18 — Lỗi không transient

Input thiếu currency, destination không tồn tại hoặc duplicate-key conflict được phân loại như thế nào? Khi nào retry toàn body có thể vô ích?

### Bài 19 — withTransaction Java

Viết Java Sync Driver code tạo ClientSession và gọi withTransaction với TransactionOptions gồm primary, snapshot và majority. Tất cả MongoDB operations phải nhận cùng session.

### Bài 20 — Callback không có external side effects

Liệt kê bốn hành động không nên đặt trong callback có thể retry: email, HTTP payment, publish Kafka, cập nhật hệ thống bên ngoài. Giải thích trường hợp callback chạy hai lần.

### Bài 21 — HTTP resend sau commit

MongoDB đã commit request ID=T1 nhưng API response bị mất. Client gửi lại POST cùng ID. Thiết kế logic lookup receipt và trả kết quả cũ mà không debit lại.

### Bài 22 — Same key, changed amount

Hai POST cùng ID nhưng lần hai đổi amount từ 100 sang 200. Server phải xử lý thế nào? Vì sao trả success không kiểm tra payload là sai?

### Bài 23 — Duplicate race

Hai threads đồng thời gửi cùng transferId. Thiết kế test với barrier, unique receipt ID và assertions để chứng minh không double debit.

### Bài 24 — Concurrent insufficient funds

A=200, T1 và T2 đều muốn chuyển 150 sang hai recipients khác nhau. Tạo test conflict/retry và xác nhận A không âm; chỉ một transfer có thể commit với số dư này.

### Bài 25 — Write skew

Hai doctors A/B cùng on-call. Hai transactions đọc snapshot và mỗi transaction off-duty một doctor khác nhau. Giải thích tại sao snapshot isolation không tự enforce “ít nhất một doctor on-call” và đề xuất guard document.

### Bài 26 — Single-node limitation

Những test nào single-node replica set làm được? Vì sao không thể đánh giá majority election durability hoặc secondary lag bằng một member?

### Bài 27 — Primary stepdown

Lập test plan sử dụng **rs.stepDown** chỉ trên replica set lab ba members. Xác định điểm inject, các metrics cần quan sát và final invariants.

### Bài 28 — Commit network fault

Thiết kế test mà client mất response quanh commit. Tại sao chỉ dùng failCommand đóng kết nối không chắc đã mô phỏng “commit thành công rồi mất ACK”?

### Bài 29 — Retry budgets

Ứng dụng có API deadline 2 giây nhưng replica set election mất 10 giây. Bạn sẽ trả response gì và dùng reconciliation nào thay vì retry vô hạn?

### Bài 30 — Secondary stale read

Sau commit majority, một test đọc secondary cũ và thấy balance trước đó. Vì sao chưa thể kết luận rollback? Hãy thay test observation strategy.

### Bài 31 — Spring MongoTransactionManager

Viết @Configuration bean cho MongoTransactionManager và method Spring service có @Transactional đúng manager. Tạo integration test chứng minh abort khi runtime exception.

### Bài 32 — Self-invocation

Một service gọi this.transferOnce() từ method khác trong cùng bean. Vì sao proxy-based transaction có thể không chạy? Đề xuất thiết kế invocation đúng.

### Bài 33 — Exception bị nuốt

Một @Transactional method bắt Exception rồi return success. Vì sao dữ liệu có thể được commit dù business step đã lỗi? Thiết kế propagation/rollback rules.

### Bài 34 — Checked exception

So mặc định rollback với RuntimeException và checked exception trong Spring. Khi nào cần rollbackFor?

### Bài 35 — Outbox trong transaction

Thêm outbox event vào cùng transaction transfer. Test commit có event; abort không có event. Vì sao dispatcher vẫn phải hỗ trợ publish lại và consumer dedup?

### Bài 36 — Callback tạo timestamp

Callback dùng new Date() mỗi lần retry. Điều này có thể ảnh hưởng receipt consistency thế nào? Khi business cần timestamp cố định, nên tạo nó ở đâu?

### Bài 37 — Reconciliation unknown outcome

Viết thuật toán có deadline, lookup transferId, so immutable parameters, trả COMMITTED/CONFLICT/PENDING đúng. Vì sao receipt absent một lần không phải bằng chứng chắc chắn abort?

### Bài 38 — Logs và metrics

Đề xuất metrics phân biệt transaction attempts, body retries, commit retries, unknown outcomes, idempotency hits và committed business transfers. Tại sao không đếm attempts thành transactions thành công?

### Bài 39 — Kiểm thử majority durability

Trong ba-member replica set lab, đề xuất thử failover sau confirmed majority commit. Phải quan sát điều gì để không nhầm secondary lag hoặc read concern với lost writes?

### Bài 40 — Transaction và SQL

Một Spring service ghi MongoDB và PostgreSQL trong method gắn @Transactional nhưng chỉ cấu hình MongoTransactionManager. Có bảo đảm hai database commit/rollback cùng nhau không? Thiết kế saga/outbox khi cần.

### Bài 41 — Transaction lifetime

Một transaction mở 90 giây để đọc hàng triệu records rồi gọi HTTP. Liệt kê resource/timeout risks và cách giảm thời gian transaction.

### Bài 42 — Retry storm

50 service instances, mỗi instance có 100 pending transfers, tất cả retry tức thì sau primary election. Mô tả tải nhân lên và cách dùng backoff, budget, circuit breaker.

### Bài 43 — Reversal sau commit

Transaction chuyển tiền đã commit; người dùng yêu cầu hoàn tiền. Vì sao abortTransaction không giúp? Phác thảo compensating transaction và audit link.

### Bài 44 — Phân biệt errors

Phân loại những trường hợp: insufficient funds, write conflict, lost commit response, invalid schema, duplicate transferId và replica set unavailable. Trường hợp nào retry body, retry commit hoặc không retry?

### Bài 45 — End-to-end test plan

Thiết kế một test suite cho transfer API có:

~~~text
Setup:
  isolated replica set + accounts + unique transfer IDs

Cases:
  commit / abort / duplicate / conflict / failover / timeout

Assertions:
  balance invariants
  exactly one receipt per business request
  no partial committed state
  no uncontrolled external side effects

Observability:
  attempt counts, error labels, duration, reconciliation

Cleanup:
  only dedicated test data
~~~

Đừng chỉ assert HTTP status; phải xác nhận trạng thái bền trong MongoDB.

## 25. Câu hỏi ôn tập

1. Replica set gồm những vai trò chính nào?
2. Multi-document transaction cần điều kiện topology gì?
3. Single-node replica set khác mongod standalone ở điểm nào?
4. MongoDB bảo đảm atomicity sẵn có ở cấp document ra sao?
5. Vì sao ba updates trên ba documents không thành một transaction nếu không dùng session?
6. ClientSession có phải transaction không? Cần gọi method nào để bắt đầu?
7. Vì sao tất cả MongoDB operations trong transaction phải nhận cùng session?
8. Một write không truyền session có bị rollback khi abortTransaction không?
9. ReadConcern.SNAPSHOT có mục đích gì?
10. WriteConcern.MAJORITY ở commit có mục đích gì?
11. Vì sao transaction reads/writes trên replica set thường dùng primary?
12. Transaction có tự kiểm tra đủ số dư không?
13. Vì sao matchedCount=0 cần được application phân loại?
14. Commit thành công có thể bị client nhìn thấy là timeout không?
15. Khi commit result chưa rõ, có được kết luận transaction chắc chắn abort không?
16. Nhãn TransientTransactionError thường dẫn đến kiểu retry nào?
17. Nhãn UnknownTransactionCommitResult thường dẫn đến kiểu retry nào?
18. Vì sao retry commit không giống retry toàn business body?
19. Retryable writes ngoài transaction có giải quyết multi-document atomicity không?
20. Vì sao không dùng một vòng lặp retry vô hạn?
21. Driver withTransaction có thể chạy callback nhiều lần không?
22. Vì sao không gửi email trong callback?
23. TransferId phải được tạo khi nào để ổn định giữa attempts?
24. Idempotency key giải quyết rủi ro nào của HTTP retry?
25. Unique _id trên receipt đã đủ chống double transfer ở mọi code paths chưa?
26. Khi cùng key nhưng amount khác, API nên xử lý thế nào?
27. Hai requests đồng thời có thể cùng đọc “receipt chưa tồn tại” không?
28. Duplicate key error có nhất thiết nghĩa request trước đã commit đúng parameters không?
29. Vì sao phải kiểm tra balances và receipt sau abort?
30. Primary failover khác application exception trước commit như thế nào?
31. Vì sao single-node replica set không đủ kiểm thử election?
32. Majority commit khác commit với weaker write concern về durability ra sao?
33. Vì sao đọc secondary lag có thể gây kết luận sai về rollback?
34. MongoTransactionManager quản lý những phần nào?
35. @Transactional có tự triển khai đầy đủ withTransaction retry semantics không?
36. Vì sao self-invocation có thể làm @Transactional không có tác dụng?
37. Checked exception và RuntimeException khác nhau trong mặc định rollback của Spring thế nào?
38. Vì sao MongoTransactionManager không tạo ACID transaction với SQL database?
39. Transactional outbox là gì?
40. Outbox dispatcher có thể publish trùng trong tình huống nào?
41. Vì sao consumer broker cần dedup dù outbox record chỉ được insert một lần?
42. Transaction atomicity có tương đương exactly-once delivery end-to-end không?
43. Snapshot isolation có luôn serializable với cross-document constraints không?
44. Write skew xảy ra như thế nào trong ví dụ bác sĩ trực ca?
45. Có những cách nào enforce invariant với guard document/unique index?
46. Long transaction tạo những rủi ro cache/timeout/conflict nào?
47. Vì sao test dùng failCommand closeConnection không tự chứng minh commit đã thành công trước khi lỗi?
48. Những metrics nào giúp phân biệt body retry và commit retry?
49. UNKNOWN outcome cần được reconcile bằng những dữ liệu bền nào?
50. Compensation sau commit khác abort trước commit ở điểm nào?

## 26. Tổng kết: test transaction phải xác nhận dữ liệu, không chỉ exceptions

Một quy trình transaction đáng tin cậy nên có sơ đồ tư duy:

~~~text
                BUSINESS REQUEST
             stable transferId + payload
                        |
                        v
                 Input validation
                        |
                        v
              Start MongoDB transaction
                        |
                        v
              Check existing receipt ID
                        |
                +-------+--------+
                |                |
          Existing record    No existing record
                |                |
                v                v
           Verify payload    Conditional debit
                |                |
                |                v
                |            Credit receiver
                |                |
                |                v
                |           Insert receipt
                |                |
                +-------+--------+
                        |
                        v
               Commit transaction
                        |
               +--------+---------+
               |                  |
               v                  v
         Known success       Error/uncertainty
               |                  |
               |          +-------+------------------+
               |          |                          |
               |          v                          v
               |   Transient error?           Unknown commit?
               |          |                          |
               |          v                          v
               |    Retry whole body             Retry same commit
               |          |                          |
               +----------+--------------------------+
                        |
                        v
              Business result/reconciliation
                        |
                        v
             Validate durable invariants
~~~

### 26.1. Năm bất biến quan trọng

**Bất biến 1 — Atomicity**

~~~text
Either:
  debit A + credit B + receipt all committed
Or:
  none of these transaction writes committed
~~~

**Bất biến 2 — Số dư hợp lệ**

~~~text
If overdraft is disallowed:
  balanceUnits(source) >= 0

For a transfer without fees:
  sum(balanceUnits of involved accounts)
  remains unchanged
~~~

**Bất biến 3 — Idempotency**

~~~text
Same logical transferId + same immutable request parameters:
  at most one business transfer effect
  repeat requests return the existing result
~~~

**Bất biến 4 — Không giả kết quả**

~~~text
Confirmed COMMITTED != confirmed ABORTED != UNKNOWN
~~~

Khi unknown, ứng dụng phải retry/reconcile theo protocol, không tự khẳng định abort hoặc phát transfer mới.

**Bất biến 5 — Side effects ngoài DB được quản lý riêng**

~~~text
MongoDB transaction cannot atomically undo:
  email sent
  Kafka event published
  payment gateway request accepted
~~~

Với side effects, dùng outbox/idempotency/saga phù hợp business contract.

### 26.2. Những nguyên tắc thực hành

1. **Sử dụng replica set** để test multi-document transactions; standalone mongod không tương đương.
2. **Mọi operations phải dùng đúng ClientSession**, hoặc Spring transaction context thực sự được áp dụng.
3. **Commit/abort cần assertions trên persisted data** sau khi thao tác hoàn tất.
4. **MatchedCount=0 phải được xử lý bằng business logic**; MongoDB không tự báo lỗi thiếu tiền.
5. **ReadConcern.SNAPSHOT** và **WriteConcern.MAJORITY** giải quyết các khía cạnh khác nhau; lựa chọn theo SLO và topology.
6. **TransientTransactionError → retry toàn transaction** trên attempt mới.
7. **UnknownTransactionCommitResult → retry commit cùng transaction** khi protocol cho phép.
8. **Không retry vô hạn**, không chạy external side effects trong body có thể được replay.
9. **Idempotency key ổn định** chống resend business request sau khi HTTP response mất.
10. **Unique index không thay validation/reconciliation** khi requests concurrent hoặc payload trùng key nhưng khác nhau.
11. **Primary failover và network fault** cần test riêng, không thay bằng application exception rồi coi như đủ.
12. **Secondary lag không chứng minh rollback**; dùng read observation policy phù hợp.
13. **Spring @Transactional cần MongoTransactionManager và invocation qua proxy**, với rollback rules rõ.
14. **Outbox/compensation** quản lý những effects ở hệ ngoài MongoDB.
15. **Kiểm thử concurrency**, vì atomic transactions không tự enforce mọi constraint kiểu write skew.
16. **Metrics phải phân biệt attempts, commit retries, business effects và unknown outcomes**.
17. **Transactions ngắn và được index tốt** sẽ giảm conflicts/resource pressure.
18. **Kết quả test phải có khả năng tái tạo**, fault injections chỉ trên lab và cleanup đúng scope.

### 26.3. Tài liệu tham khảo chính thức

- [MongoDB Transactions — Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — giới hạn/tài nguyên/triển khai transactions.
- [MongoDB Transactions — Core Concepts](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document atomicity và transaction semantics.
- [MongoDB Transactions — Retries](https://www.mongodb.com/docs/manual/core/transactions-in-applications/) — transaction APIs, error handling và retries.
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — mức xác nhận/durability.
- [MongoDB Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — local/majority/snapshot semantics.
- [MongoDB Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — routing reads trên replica sets.
- [MongoDB Replica Sets](https://www.mongodb.com/docs/manual/replication/) — primary/secondary, elections và replication.
- [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — phân biệt retryable writes với transaction retries.
- [MongoDB Transactions in Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — ClientSession, withTransaction và commit/abort.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — driver overview và API integration.
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — MongoTransactionManager, @Transactional và session binding.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — proxy, @Transactional và rollback rules.
- [MongoDB Configure Fail Point](https://www.mongodb.com/docs/manual/reference/command/configureFailPoint/) — test failpoints khi môi trường/version hỗ trợ.
- [MongoDB serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — transactions metrics và node diagnostics.

Các transaction behaviors, error labels, driver callback retries, server commands và failpoints có thể thay đổi theo **MongoDB server version, MongoDB Java Driver version, Spring Data MongoDB version** và deployment (Atlas/self-managed). Đối chiếu tài liệu phiên bản đang dùng trước khi triển khai production hoặc xây fault-injection harness.

**Kết luận:** Một bài kiểm thử commit, rollback và gửi lại giao dịch trên replica set chỉ thực sự có giá trị khi nó chứng minh được **không có partial committed state, không double business effect khi request bị gửi lại, và không đoán sai kết quả của commit đang bất định**. Hãy kết hợp MongoDB transactions, idempotency records, retries theo error labels, fault injection có kiểm soát và kiểm tra dữ liệu bền sau mỗi trường hợp để xây một hệ thống có thể phục hồi đúng sau sự cố.










