# Not primary, write conflict và lỗi tạm thời của giao dịch trong MongoDB

## 1. Khi ứng dụng đang ghi thì primary đổi: lỗi có nghĩa gì?

Một ứng dụng đặt hàng dùng MongoDB replica set để lưu **orders**, **inventory** và **payment intents**. Request đang tạo đơn thì MongoDB driver nhận thông báo:

~~~text
MongoCommandException: Command failed with error 10107
(NotWritablePrimary): not primary
~~~

Một request khác đang thực thi transaction bị lỗi:

~~~text
WriteConflict (code 112)
Write conflict during plan execution and yielding is disabled.
Please retry your operation or multi-document transaction.
~~~

Ở thời điểm commit, một request khác lại gặp:

~~~text
MongoException
errorLabels: ["UnknownTransactionCommitResult"]
~~~

Cả ba đều có thể xuất hiện khi hệ thống MongoDB đang bị cạnh tranh tài nguyên hoặc thay đổi topology, nhưng **không được xử lý chúng như cùng một loại lỗi**.

- **Not primary / NotWritablePrimary** thường liên quan tới topology hoặc đường đi của write: node nhận command không còn là primary có khả năng nhận write tại thời điểm đó.
- **WriteConflict** thường liên quan tới cạnh tranh giữa những thao tác cùng sửa dữ liệu, nhất là trong transaction.
- **Lỗi tạm thời của giao dịch** được driver/server đánh dấu qua **error labels** và yêu cầu retry đúng phạm vi: transaction body hay chỉ commit.

Mục tiêu xử lý sự cố không phải “cứ retry cho đến khi hết lỗi”. Mục tiêu là **khôi phục dịch vụ mà không ghi dữ liệu hai lần, không làm mất bản ghi và không báo kết quả commit sai**.

### 1.1. Một timeline điển hình

~~~text
Application                Driver               Replica set
     |                        |                        |
     | insert/order           |                        |
     |----------------------->|                        |
     |                        |---- write to P1 ------>|
     |                        |                P1 steps down
     |                        |<-- NotWritablePrimary -|
     |                        |                        |
     |                        | topology refresh       |
     |                        | discover P2 primary    |
     |                        |                        |
     |                        |---- retry if allowed ->|
     |                        |                        |
     |<--- response ----------|                        |
~~~

Nếu lệnh nằm trong **multi-document transaction**, không thể chỉ lấy logic retry của một write độc lập rồi áp vào mọi bước: transaction có trạng thái và số transaction riêng.

### 1.2. Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Phân loại thông báo **NotWritablePrimary/not primary**, các lỗi server selection và lỗi network liên quan.
2. Hiểu primary election, stepdown, client topology discovery và khoảng gián đoạn khi failover.
3. Xác định nguyên nhân phổ biến của **WriteConflict** và cách giảm contention.
4. Phân biệt lỗi trong transaction body với lỗi khi **commitTransaction**.
5. Hiểu ý nghĩa **TransientTransactionError** và **UnknownTransactionCommitResult**.
6. Chọn đúng retry scope, backoff, retry budget và timeout.
7. Không biến temporary failure thành **double business effect** khi client/HTTP retry.
8. Kiểm tra **MongoClient URI**, read/write concern, replica set health và driver version.
9. Viết xử lý lỗi bằng Java Sync Driver và Spring Data MongoDB.
10. Thiết kế fault-injection tests và runbooks không gây ảnh hưởng production.
11. Giám sát write conflicts, elections, retry attempts, p95/p99, replication lag và pending reconciliations.
12. Phân biệt lỗi thực sự tạm thời với lỗi schema, quyền, input và business conflicts không nên retry.

## 2. Nền tảng cần biết: primary, replication và driver

### 2.1. Replica set và write routing

MongoDB replica set có **primary** và các **secondary**. Các write operations thông thường phải đi tới primary của replica set.

~~~text
                         Java service
                              |
                       MongoDB driver
                              |
           +------------------+------------------+
           |                  |                  |
         node01             node02             node03
         PRIMARY           SECONDARY          SECONDARY
           |                  ^                  ^
           +------ oplog ---->+------ sync ------+
~~~

Hình chỉ minh họa; một secondary có thể đồng bộ từ primary hoặc sync source phù hợp. Trong quá trình failover:

~~~text
T0: node01 = primary
T1: node01 steps down or becomes unavailable
T2: election / temporary no-primary window
T3: node02 = new primary
T4: driver detects and routes writes to node02
~~~

Trong **T1–T4**, writes có thể thất bại, chờ server selection hoặc được retry theo quy tắc hỗ trợ.

### 2.2. Không có primary là tình huống khác với client nhắm sai node

Hai trường hợp có thông điệp tương tự nhưng nguyên nhân khác:

**Trường hợp A — primary election hợp lệ:**

- Driver biết replica set.
- Primary cũ step down.
- Driver cập nhật topology và tìm primary mới.

**Trường hợp B — ứng dụng kết nối sai:**

- URI chỉ vào một secondary và ép **directConnection=true**.
- Application dùng một hard-coded host thay vì replica set URI.
- Một reverse proxy/DNS mapping làm driver thấy node sai.
- Client topology metadata sai do hostname không thể resolve.

Retry cùng một secondary mãi mãi **không thể biến nó thành primary** nếu cấu hình kết nối vẫn sai.

### 2.3. Ví dụ URI replica set

~~~text
mongodb://mongo1.example.test:27017,mongo2.example.test:27017,mongo3.example.test:27017/orders?replicaSet=rsOrders&retryWrites=true&w=majority
~~~

Đây là URI minh họa cho lab. Khi production cần bổ sung TLS, authentication và secrets theo chính sách. Các member hostnames trong **rs.conf()** phải có thể được client resolve và truy cập phù hợp network topology.

**Không đặt directConnection=true** cho application replica set bình thường nếu muốn driver tự chọn primary và failover. Direct connection phù hợp một số tình huống công cụ/quản trị có chủ đích, không phải giải pháp chữa lỗi write routing.

### 2.4. Server selection không đồng nghĩa server write error

Driver có thể không tìm được primary trước khi gửi command:

~~~text
MongoTimeoutException:
  Timed out while waiting for a server
  that matches WritableServerSelector
~~~

Hoặc command đã tới một node, node trả:

~~~text
NotWritablePrimary (10107)
~~~

Khác biệt:

| Nhóm | Vị trí lỗi | Hướng điều tra |
|---|---|---|
| **Server selection timeout** | Driver chưa tìm được server phù hợp để gửi command. | Replica set topology, DNS, ports, elections, connect/server-selection settings. |
| **NotWritablePrimary** | Node đã nhận command nhưng không thể nhận write như primary. | Stepdown, stale topology, directConnection, routing. |
| **Network/socket timeout** | Kết nối bị ngắt hoặc chờ quá lâu. | Network, node liveness, pool, TLS, load balancer/proxy. |
| **WriteConflict** | Storage/concurrency conflict khi thực thi. | Contended documents, transaction duration, retry strategy. |
| **Write concern failure** | Không đạt mức acknowledgment được yêu cầu. | Majority availability, replication lag, disk/network. |

Một thông điệp network timeout cũng có thể khiến **kết quả write/commit chưa rõ**, tùy command và giai đoạn xử lý. Không mặc định mọi timeout có nghĩa server chưa thực thi gì.

## 3. Not primary và các thông báo liên quan

### 3.1. NotWritablePrimary

Một mã lỗi thường gặp:

~~~text
Code 10107: NotWritablePrimary
Legacy text: "not primary" / "not master"
~~~

Ý nghĩa thực tế: node nhận command **không phải primary có khả năng nhận write** ở thời điểm command được đánh giá.

Những thông báo cũ có thể sử dụng thuật ngữ **not master**, trong khi các phiên bản MongoDB mới dùng **primary**. Không phụ thuộc hoàn toàn vào một chuỗi lỗi khi phân loại.

### 3.2. Những mã lỗi liên quan

Một số mã/tên thường gặp trong những phiên bản MongoDB:

| Code hoặc tên | Bối cảnh thường gặp |
|---|---|
| **NotWritablePrimary (10107)** | Write gửi đến node không thể nhận write của primary. |
| **NotPrimaryNoSecondaryOk (13435)** | Lệnh đọc hoặc operation yêu cầu primary trong khi server không đáp ứng điều kiện. |
| **PrimarySteppedDown (189)** | Primary vừa step down hoặc chuyển trạng thái. |
| **InterruptedDueToReplStateChange (11602)** | Operation bị gián đoạn vì thay đổi trạng thái replication. |
| **ShutdownInProgress (91)** | Server đang shutdown. |
| **HostUnreachable (6)**, **NetworkTimeout (89)** | Network/host reachability failures. |
| **WriteConflict (112)** | Cạnh tranh ghi hoặc transaction write conflict. |
| **NoSuchTransaction (251)** | Server không còn nhận diện transaction number/state theo command. |

**Không coi bảng code là exhaustive hoặc bất biến giữa mọi MongoDB server/driver versions.** Driver exception types và error labels mới là nguồn quan trọng cho quyết định retry của ứng dụng.

### 3.3. Những tình huống tạo NotWritablePrimary

1. **Election:** primary cũ không còn giữ vai trò.
2. **Stepdown do bảo trì:** người vận hành chuyển primary.
3. **Node mất kết nối majority:** không thể tiếp tục primary hợp lệ.
4. **Client kết nối trực tiếp secondary:** URI/hard-coded address sai.
5. **Application dùng cached/stale topology:** driver chưa phát hiện primary mới.
6. **Network partition hoặc proxy routing không đúng:** request tới node không phù hợp.
7. **Transaction kéo dài xuyên failover:** primary không còn thực thi được attempt cũ.

Lỗi này **không luôn là dữ liệu bị hỏng**, và cũng không nên tự chữa bằng cách restart tất cả nodes.

### 3.4. Một request thất bại có nghĩa cluster down không?

Không nhất thiết:

~~~text
Request 1 at T1 -> NotWritablePrimary
Election completes at T3
Request 2 at T4 -> success
~~~

Nhưng nếu lỗi kéo dài hàng phút, cần kiểm tra:

- Có primary được bầu không?
- Driver có kết nối được member hostnames không?
- Replica set member states và majority votes?
- DNS/TLS/authentication?
- Server selection/connection pool saturation?
- Có dùng directConnection hoặc stale client configuration?

### 3.5. Kiểm tra read-only bằng mongosh

Trên connection tới replica set phù hợp:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

Khi kết nối trực tiếp một member và có quyền phù hợp:

~~~javascript
rs.status();
~~~

Nếu cần xem cấu hình topology trong môi trường được phép:

~~~javascript
rs.conf();
~~~

Không chỉnh **rs.conf()**, votes, priorities hoặc gọi **rs.stepDown()** trên production chỉ vì xuất hiện NotWritablePrimary mà chưa có quy trình đã duyệt.

### 3.6. Những field cần quan sát

Trong **hello** hoặc monitoring topology:

- **setName:** replica set identifier.
- **isWritablePrimary:** server có đang là primary ghi được không.
- **secondary:** server có đang ở secondary state không.
- **primary:** địa chỉ primary được nhận biết theo topology.
- **hosts/passives/arbiters** khi có.
- **topologyVersion** hoặc thông tin tương đương theo version.

Đừng suy trạng thái toàn cluster chỉ từ một output cũ chụp trước election.

### 3.7. Tại sao cần dùng driver mới phù hợp?

MongoDB drivers có cơ chế **SDAM (Server Discovery and Monitoring)** để theo dõi servers/topology và chọn primary phù hợp. Driver cũ, URI cấu hình sai hoặc network không cho phép discover member hostnames sẽ làm failover kém tin cậy.

Sửa lệnh retry ở business service **không thay thế** việc cập nhật driver và cấu hình connectivity đúng.

## 4. WriteConflict là gì?

**WriteConflict** thể hiện một xung đột trong quá trình storage engine và transaction thực hiện writes cạnh tranh; MongoDB có thể yêu cầu thao tác hoặc transaction attempt được retry.

~~~text
Session T1              Session T2
   |                       |
startTransaction       startTransaction
   |                       |
read account A         read account A
   |                       |
update A               update A
   |                       |
success?               write conflict?
   |                       |
commit                 abort/retry
~~~

Trường hợp hai transactions cùng sửa một document là ví dụ phổ biến, nhưng write conflict không chỉ xảy ra duy nhất khi hai users cố tình sửa cùng account: concurrency, page-level/storage state, index updates và transaction snapshots có thể góp phần tùy operation.

### 4.1. Một ví dụ tài khoản đơn giản

Fixture:

~~~javascript
{
  _id: "wallet-A",
  currency: "VND",
  balanceUnits: NumberLong("200")
}
~~~

T1 và T2 cùng muốn trừ **150 units**. Nếu cả hai chỉ đọc **200** rồi update không điều kiện, ứng dụng có thể có race về nghiệp vụ. MongoDB transaction/write-conflict handling có thể abort một attempt; attempt được retry phải **đọc lại** số dư.

Điều kiện debit nên đặt ngay trong write:

~~~javascript
db.accounts.updateOne(
  {
    _id: "wallet-A",
    currency: "VND",
    balanceUnits: { $gte: NumberLong("150") }
  },
  { $inc: { balanceUnits: NumberLong("-150") } }
);
~~~

Trong transaction, kiểm tra **matchedCount**. Khi attempt mới thấy số dư chỉ còn 50, retry không được tiếp tục debit 150.

### 4.2. WriteConflict khác DuplicateKey

| WriteConflict | DuplicateKey |
|---|---|
| Concurrency/storage conflict; thường có cơ hội retry attempt. | Unique constraint bị vi phạm; có thể là business/data conflict bền. |
| Trong transaction có thể đi kèm **TransientTransactionError**. | Không tự mặc định retryable, nhất là khi key thực sự trùng. |
| Retry attempt phải đọc lại snapshot/điều kiện. | Nên kiểm tra record đang tồn tại và business idempotency. |
| Giảm contention và transaction duration có ích. | Sửa duplicate data/unique-key policy; không đổi key vô tội vạ. |

Một duplicate ID do client gửi lại cùng request có thể được **resolve** bằng receipt lookup; một duplicate ID do hai nghiệp vụ khác nhau là **409 Conflict**, không phải lỗi tạm thời cần retry vô hạn.

### 4.3. WriteConflict khác LockTimeout

**WriteConflict** phản ánh xung đột về concurrent writes/transaction state; **LockTimeout** thường liên quan tới operation không lấy được lock trong thời gian cho phép.

Hai nhóm có thể cùng tăng khi transaction quá dài hoặc load tăng, nhưng **không được gộp mọi lock timeout thành TransientTransactionError** trừ khi driver/server xác định nhãn phù hợp.

### 4.4. MongoDB có thể tự retry một số conflicts

Một số single-document operations ngoài transaction có thể được MongoDB storage/query engine tự xử lý conflicts nội bộ. Khi application thấy WriteConflict, không suy rằng mọi operation đều chưa được thực thi hoặc luôn an toàn khi gửi lại.

**Quy tắc ứng dụng là phân loại theo command, transaction phase, error label và idempotency contract**, không chỉ nhìn chữ “conflict”.

### 4.5. WriteConflict có thể tăng khi nào?

- Nhiều transactions cùng update một **hot document**.
- Transaction giữ snapshot lâu và data thay đổi nhanh.
- Workflow đọc nhiều records rồi mới ghi.
- Batch updates tranh chấp một tập IDs hẹp.
- Tần suất retry quá lớn gây thêm contention.
- Tạo indexes hoặc thao tác liên quan storage cạnh tranh tài nguyên.

Không kết luận “MongoDB không hỗ trợ concurrency” khi có một số conflicts: giải pháp có thể là giảm contention và cập nhật lại mô hình dữ liệu.

## 5. Tại sao giao dịch có lỗi tạm thời?

MongoDB multi-document transaction có **trạng thái** và nhiều commands phải được commit/abort như một đơn vị. Trong quá trình transaction:

~~~text
startTransaction
       |
       v
read/update/insert
       |
       +--> transient error?
       |        |
       |        v
       |     abort/stop attempt
       |        |
       |        v
       |     retry whole transaction
       |
       v
commitTransaction
       |
       +--> unknown commit result?
       |        |
       |        v
       |     retry same commit
       |
       v
confirmed committed
~~~

**Lỗi tạm thời không có nghĩa an toàn để gửi lại bất kỳ command nào theo cách tùy ý.** Nó chỉ ra một cơ chế retry đã được quy định và phải được áp dụng đúng giai đoạn.

### 5.1. Error codes, error labels và exception classes

Trong MongoDB ecosystem:

- **Error code** cho biết loại lỗi server, ví dụ WriteConflict, NotWritablePrimary.
- **Error labels** là metadata định hướng cách xử lý, ví dụ TransientTransactionError hoặc UnknownTransactionCommitResult.
- **Driver exception type** cho biết lỗi là command error, timeout, network failure hoặc transaction exception.
- **Operation phase** xác định khi lỗi xảy ra: trước transaction, trong body, commit, hay sau khi commit.

Ứng dụng nên dùng **label-aware retry policy** của driver khi có thể, thay vì parse câu chữ trong exception message.

### 5.2. TransientTransactionError

Error label **TransientTransactionError** thường được sử dụng cho một lỗi tạm thời khi thực thi transaction, khiến attempt hiện tại không tiếp tục bình thường.

Ví dụ có thể bao gồm:

- WriteConflict trong transaction.
- Primary stepdown khi transaction đang chạy.
- Một số network errors trong body.
- Một số server interruptions theo transaction spec.

Chi tiết label gắn cho lỗi nào phụ thuộc **server/driver version, command và phase**. Không suy mọi NotWritablePrimary luôn có label này.

Hành động về ý tưởng:

~~~text
TransientTransactionError during body
         |
         v
discard/abort current attempt if applicable
         |
         v
start a new transaction attempt
         |
         v
rerun reads/writes with current state
~~~

Retry body trên attempt mới giúp điều kiện nghiệp vụ được đánh giá lại với data mới.

### 5.3. UnknownTransactionCommitResult

Error label **UnknownTransactionCommitResult** đặc biệt quan trọng khi một lần commit đã được gửi nhưng client chưa thể xác định kết quả.

~~~text
Client                         MongoDB
  |                               |
  | commitTransaction             |
  |------------------------------>|
  |                               | commit may happen
  |          response lost        |
  X<------------------------------X
  |
  | commit outcome UNKNOWN
~~~

Hành động đúng khi còn trong cùng session/transaction context và error semantics cho phép:

~~~text
Retry commitTransaction
for the SAME transaction
~~~

**Không chạy lại transaction body ngay**; attempt ban đầu có thể đã commit.

### 5.4. NoSuchTransaction

Lỗi **NoSuchTransaction** có thể xuất hiện khi server không nhận diện transaction theo session/number trong hoàn cảnh đó. Nguyên nhân có thể gồm transaction đã bị abort, số transaction không còn hợp lệ hoặc client/server state thay đổi.

Không suy một cách đơn giản:

~~~text
NoSuchTransaction => definitely safe to debit again
~~~

Phải xem phase, error labels, driver behavior và business idempotency. Trường hợp commit outcome không rõ có thể cần reconciliation ngay cả khi một retry attempt báo lỗi khác.

### 5.5. TransactionTooLargeForCache và các lỗi không nên retry mù quáng

Ở các phiên bản MongoDB có transaction lớn vượt giới hạn tài nguyên, lỗi liên quan **transaction size/cache** có thể không được xử lý như lỗi transient có thể tự giải quyết bằng việc chạy lại y nguyên. Cần giảm kích thước/thời gian transaction hoặc thiết kế batch khác.

Không áp dụng cùng một vòng lặp retry cho:

~~~text
WriteConflict under contention
    vs
Invalid schema
    vs
Out-of-memory/transaction too large
    vs
Unauthorized
~~~

### 5.6. Tóm tắt ý nghĩa ba trạng thái

| Trạng thái ứng dụng biết | Có thể làm gì |
|---|---|
| **Definitely aborted / not committed** | Retry toàn transaction nếu lỗi transient và request còn hợp lệ. |
| **Definitely committed** | Trả success, không debit/credit lần nữa. |
| **Unknown commit outcome** | Retry commit cùng transaction khi có thể; nếu hết context thì reconcile bằng business key. |

Đây là **tri-state model** quan trọng nhất của nghiệp vụ khi có lỗi quanh commit.

## 6. Chọn đúng retry scope

### 6.1. Retry request độc lập

Với một command đơn lẻ được hỗ trợ bởi retryable writes:

~~~text
Application issues one write
  -> driver may retry according to retryable write protocol
  -> application receives result/error
~~~

Cơ chế có thể tận dụng session/statement identity để hạn chế double execution theo quy tắc server, nhưng nó **không giống** tự viết:

~~~java
while (true) {
    collection.updateOne(...);
}
~~~

Nếu update là **$inc**, một vòng lặp do ứng dụng tự gửi commands mới có thể tăng số dư nhiều lần nếu lần trước đã thực thi nhưng response bị mất.

### 6.2. Retry toàn transaction

Khi lỗi trong transaction body được gắn **TransientTransactionError**:

~~~text
Attempt #1:
  read A
  debit A
  credit B -> WriteConflict
  attempt aborted

Attempt #2:
  read A again
  recheck balance
  debit A
  credit B
  commit
~~~

Không dùng kết quả đọc của attempt #1 làm authority cho attempt #2. Data đã có thể thay đổi.

### 6.3. Retry commit

Khi commit result chưa rõ:

~~~text
Attempt #2 body already completed
  |
  v
commit call #1 -> network timeout
  |
  v
commit call #2 FOR SAME transaction
  |
  v
known committed / still unknown / other error
~~~

Commit retry không phát ra debit/credit commands mới. Driver quản lý session identity/transaction number; ứng dụng không tự viết lsid/txnNumber.

### 6.4. Retry toàn HTTP request

Một HTTP client có thể gửi lại:

~~~http
POST /wallet/transfers
Idempotency-Key: trx-2026-001
~~~

Khi service nhận lần hai, đây có thể là **business invocation mới** với session khác. MongoDB driver không tự biết đây là “cùng một lần chuyển tiền” nếu ứng dụng không dùng persistent idempotency key.

### 6.5. Bảng quyết định

| Tình huống | Phạm vi retry | Điều kiện |
|---|---|---|
| Retryable single write error | Driver-managed write retry | Command được hỗ trợ, retryWrites/config phù hợp. |
| TransientTransactionError trong body | Whole transaction attempt | Có retry budget, body an toàn khi replay. |
| UnknownTransactionCommitResult ở commit | Same transaction commit | Còn session/context, driver cho phép. |
| HTTP response mất sau commit | Same logical business request | Stable idempotency key, persistent receipt. |
| DuplicateKey với same request | Không blind retry; lookup | Xác minh immutable request fields. |
| DuplicateKey với khác request | No retry | Trả conflict và audit. |
| Data validation fail | No retry | Sửa request/dữ liệu. |
| Authentication/authorization error | No retry | Sửa identity/configuration. |
| Server selection tạm thời | Bounded retry/circuit breaker | Kiểm tra replica availability/topology. |
| Consistent WriteConflict trên hot key | Retry có giới hạn + redesign | Giảm contention, không retry storm. |

### 6.6. Đừng dùng error message string matching

Anti-pattern:

~~~java
if (ex.getMessage().contains("not primary")) {
    retry();
}
~~~

Thông báo có thể đổi theo version, bị wrap bởi framework hoặc khác ngôn ngữ. Dùng error codes, labels, exception types và driver APIs; vẫn cần business-level context.

### 6.7. Retry budget là giới hạn an toàn

Một retry policy có:

~~~text
maxAttempts or deadline
backoff with jitter
read/write timeout
idempotency/reconciliation
metrics and logging
~~~

Không đặt retries ở cả driver, repository wrapper, service, controller và gateway mà không xét tổng số lần:

~~~text
3 gateway retries
 x 3 service retries
 x 3 driver attempts
 = up to 27 attempts in an unlucky path
~~~

Các lớp retry phải có **một budget chung hoặc giới hạn phối hợp** để không nhân tải gây outage.

## 7. Java Sync Driver: cấu hình client trước khi sửa retry logic

Một **MongoClient** được tái sử dụng, thread-safe và quản lý connection pool/server discovery. Không tạo MongoClient mới cho mỗi request để cố chữa lỗi NotWritablePrimary.

### 7.1. Khởi tạo client bằng URI replica set

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoClientProvider {
    private final MongoClient client;

    public MongoClientProvider(String uri) {
        // URI from environment/secret manager, not hardcoded credentials.
        this.client = MongoClients.create(uri);
    }

    public MongoClient client() {
        return client;
    }

    public void close() {
        client.close();
    }
}
~~~

Ví dụ URI:

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/app?replicaSet=rsApp&retryWrites=true&w=majority
~~~

### 7.2. Connection string không phải phương án thay thế cho monitoring

Các thông số như:

- **serverSelectionTimeoutMS**
- **connectTimeoutMS**
- **socketTimeoutMS**
- **maxPoolSize / minPoolSize**
- **retryWrites**
- **w / journal**, theo write concern

có mục đích riêng. Ví dụ tăng **serverSelectionTimeoutMS** có thể cho election thêm thời gian, nhưng **không sửa** một replica set không có majority hoặc DNS sai.

Một timeout quá dài có thể vượt HTTP SLO; quá ngắn có thể tạo lỗi trong những failover hợp lệ. Đặt theo application deadline và high-availability requirements.

### 7.3. Chỉ định primary cho transaction

~~~java
TransactionOptions options = TransactionOptions.builder()
    .readPreference(ReadPreference.primary())
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .build();
~~~

Không cố ép transaction write đi secondary bằng một readPreference khác. Transaction options và write concern cần phù hợp driver/server version.

### 7.4. Truy vấn read-only để kiểm tra kết nối

Trong mongosh trên replica set:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

Trong Java:

~~~java
Document hello = client
    .getDatabase("admin")
    .runCommand(new Document("hello", 1));

System.out.println(
    "setName=" + hello.getString("setName")
);
System.out.println(
    "isWritablePrimary=" + hello.getBoolean("isWritablePrimary")
);
~~~

Một application client có thể gửi admin command tới server mà driver chọn theo semantics của operation; output là **một quan sát ở thời điểm đó**, không phải danh sách health của toàn bộ replica set. Dùng monitoring SDAM và các commands phù hợp để xem topology.

### 7.5. Không pin primary cố định

Anti-pattern:

~~~text
mongodb://node01:27017/?directConnection=true
~~~

Khi node01 stepdown, code không tự có khả năng chuyển sang primary mới chỉ vì retry. Dùng host seed list/replicaSet parameter hoặc connection string do managed service cung cấp.

## 8. Java Sync Driver: xử lý transaction với withTransaction

API **ClientSession.withTransaction(...)** của MongoDB Java Sync Driver điều phối start, commit và các retry được hỗ trợ theo transaction specification. Với nhiều workflow, đây là lựa chọn an toàn hơn tự xây hai vòng lặp body/commit.

### 8.1. Bài toán chuyển điểm giữa hai tài khoản

Fixtures:

~~~javascript
// app_test.accounts
{ _id: "A", balanceUnits: NumberLong("1000") }
{ _id: "B", balanceUnits: NumberLong("300") }
~~~

Một giao dịch muốn:

1. Trừ 200 units ở A nếu đủ.
2. Cộng 200 units vào B nếu B tồn tại.
3. Insert receipt có **_id** bằng stable requestId.

### 8.2. Code Java Sync Driver

~~~java
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
    private final MongoCollection<Document> receipts;

    public TransferService(MongoClient client) {
        this.client = Objects.requireNonNull(client);
        var database = client.getDatabase("app_test");
        accounts = database.getCollection("accounts");
        receipts = database.getCollection("transfer_receipts");
    }

    public Document transfer(
            String requestId,
            String fromId,
            String toId,
            long amountUnits) {

        if (requestId == null || requestId.isBlank()
                || fromId == null || fromId.isBlank()
                || toId == null || toId.isBlank()
                || fromId.equals(toId) || amountUnits <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        try (ClientSession session = client.startSession()) {
            return session.withTransaction(() -> {
                Document existing = receipts.find(
                        session,
                        Filters.eq("_id", requestId)
                ).first();

                if (existing != null) {
                    assertSameRequest(
                            existing, fromId, toId, amountUnits);
                    return existing;
                }

                UpdateResult debit = accounts.updateOne(
                        session,
                        Filters.and(
                                Filters.eq("_id", fromId),
                                Filters.gte("balanceUnits", amountUnits)
                        ),
                        Updates.inc("balanceUnits", -amountUnits)
                );

                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                            "Account missing or insufficient balance");
                }

                UpdateResult credit = accounts.updateOne(
                        session,
                        Filters.eq("_id", toId),
                        Updates.inc("balanceUnits", amountUnits)
                );

                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                            "Destination account missing");
                }

                Document receipt = new Document("_id", requestId)
                        .append("fromId", fromId)
                        .append("toId", toId)
                        .append("amountUnits", amountUnits)
                        .append("state", "COMMITTED")
                        .append("createdAt", new Date());

                receipts.insertOne(session, receipt);
                return receipt;
            }, TX_OPTIONS);
        }
    }

    private static void assertSameRequest(
            Document receipt,
            String fromId,
            String toId,
            long amountUnits) {

        Object value = receipt.get("amountUnits");
        boolean same = fromId.equals(receipt.getString("fromId"))
                && toId.equals(receipt.getString("toId"))
                && value instanceof Number
                && amountUnits == ((Number) value).longValue();

        if (!same) {
            throw new IllegalStateException(
                    "Idempotency key reused with another request");
        }
    }
}
~~~

**Giới hạn:** code là ví dụ transaction/idempotency, chưa phải hệ thống tiền tệ production. Nghiệp vụ thực cần currency, overflow checks, account ownership/authorization, ledger, audits và reconciliation.

### 8.3. Phải truyền cùng ClientSession

Tất cả operations:

~~~java
receipts.find(session, ...);
accounts.updateOne(session, ...);
accounts.updateOne(session, ...);
receipts.insertOne(session, ...);
~~~

đều tham gia transaction. Nếu một update dùng:

~~~java
accounts.updateOne(filter, update);
~~~

**không có session argument**, nó nằm ngoài transaction và có thể commit độc lập; abort transaction không undo nó.

### 8.4. Vì sao kiểm tra matchedCount?

Predicate:

~~~java
Filters.gte("balanceUnits", amountUnits)
~~~

ngăn debit khi balance không đủ. Nhưng updateOne không match **không tự ném exception**; nếu bỏ qua matchedCount, code có thể credit B dù không debit A.

### 8.5. Callback có thể chạy lại

~~~text
Attempt #1:
  debit A
  credit B -> write conflict
  transaction aborts

Attempt #2:
  check receipt again
  debit A with current balance
  credit B
  insert receipt
  commit
~~~

Không gửi email, HTTP payment request, Kafka event hoặc external side effect trong callback. **requestId phải ổn định** xuyên transaction attempts và HTTP retries.

### 8.6. withTransaction không tạo idempotency cho HTTP

~~~text
Transaction with requestId=T1 committed
            |
            v
HTTP response lost
            |
            v
Client retries POST /transfers with T1
~~~

Lần gọi HTTP mới tạo session/transaction mới. Lookup receipt bằng stable requestId và unique **_id** giúp không debit lần hai.

### 8.7. Đồng thời cùng một ID

Hai requests có thể cùng thấy receipt chưa tồn tại. Unique ID bảo vệ không ghi trùng receipt; transaction thất bại không được để lại debit/credit nửa vời. Tuy nhiên, request thua race có thể nhận duplicate key/write conflict, nên service cần đọc lại receipt và **so immutable request parameters** thay vì trả success vô điều kiện.

### 8.8. Khi cả cluster unavailable

withTransaction có retry rules nhưng không bảo đảm request sẽ thành công nếu primary mất majority. Application cần deadline, backoff/overload protection và trạng thái **unknown/pending reconciliation** khi kết quả commit vẫn chưa rõ.

## 9. Java: đọc error codes và labels đúng cách

### 9.1. MongoException và error labels

~~~java
import com.mongodb.MongoException;

public final class MongoFailureReporter {

    public static void report(MongoException exception) {
        int code = exception.getCode();

        boolean transientTransaction =
                exception.hasErrorLabel(
                        "TransientTransactionError");

        boolean unknownCommitResult =
                exception.hasErrorLabel(
                        "UnknownTransactionCommitResult");

        System.out.println("mongodb.error.code=" + code);
        System.out.println("mongodb.error.transientTx="
                + transientTransaction);
        System.out.println("mongodb.error.unknownCommit="
                + unknownCommitResult);
    }
}
~~~

Đây là minh họa phân loại, không phải khuyến nghị log mọi exception/payload trên production. Dùng error category, trace ID và redaction theo chính sách.

### 9.2. Error code chỉ là một phần ngữ cảnh

Ví dụ:

~~~text
Code: NotWritablePrimary
Phase: single retryable write
  -> driver topology selection / retryable-write rules

Code: NotWritablePrimary
Phase: transaction body
Label: TransientTransactionError
  -> retry whole transaction

Phase: commit
Label: UnknownTransactionCommitResult
  -> retry same transaction commit
~~~

**Đây là các nhánh minh họa, không phải cam kết rằng mọi NotWritablePrimary luôn gắn nhãn tương ứng.** Labels có thể khác theo server/driver version và command.

### 9.3. Không retry bằng message string

Anti-pattern:

~~~java
if (exception.getMessage().contains("not primary")) {
    while (true) {
        retry();
    }
}
~~~

Vấn đề:

- Message text có thể đổi.
- Exception bị wrap bởi Spring/framework.
- Một số lỗi là configuration issue dai dẳng.
- Retry storm làm cluster failover chậm phục hồi.
- Cơ chế này không phân biệt commit unknown.

### 9.4. Pseudocode hai vòng retry

~~~text
deadline = now + retryBudget

OUTER: while before deadline:
    start new transaction attempt

    try:
        execute all reads and writes
    catch error:
        abort attempt when appropriate

        if TransientTransactionError:
            backoff and continue OUTER

        throw error

    INNER: while before deadline:
        try:
            commit SAME transaction
            return COMMITTED
        catch error:
            if UnknownTransactionCommitResult:
                retry commit in INNER
                continue INNER

            handle known failure / reconcile

    return UNKNOWN_NEEDS_RECONCILIATION

return RETRY_BUDGET_EXHAUSTED
~~~

**Đây là mô hình tư duy**, không phải implementation được kiểm chứng. Trong code thật phải hiểu session state, driver-specific retry semantics, cancellation, transaction number và error labels. Ưu tiên **withTransaction** khi phù hợp.

### 9.5. Không tự chỉnh lsid hoặc txnNumber

Commit retry của **cùng transaction** phải giữ transaction identity do driver quản lý. Không dựng commands thủ công với lsid/txnNumber hoặc mở một session mới rồi gọi đó là retry commit.

### 9.6. Không bù tiền ngay khi outcome chưa rõ

Nếu một commit call timeout, transaction ban đầu **có thể đã được commit**. Việc phát ngay một transfer đảo chiều hoặc lệnh debit mới có thể gây sai số dư. Cần resolve durable receipt và business state trước khi hành động.

## 10. Spring Data MongoDB: @Transactional và lỗi transaction

Spring Data MongoDB có **MongoTransactionManager** để điều phối transaction trong các service methods được đánh dấu **@Transactional**.

### 10.1. Cấu hình transaction manager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfiguration {

    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

Với một số Spring Boot/Spring Data versions, auto-configuration hoặc APIs có thể khác. Cần kiểm tra transaction manager thực sự được đưa vào application context.

### 10.2. Spring transaction boundary

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final MongoTemplate template;

    public InventoryService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void reserve(String itemId, long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be > 0");
        }

        Query query = Query.query(
                Criteria.where("_id").is(itemId)
                        .and("available").gte(quantity)
        );

        var result = template.updateFirst(
                query,
                new Update().inc("available", -quantity),
                "inventory"
        );

        if (result.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Inventory item unavailable");
        }

        // Further MongoDB writes here can join this transaction.
    }
}
~~~

Ví dụ này minh họa **session binding và conditional update**. Một service thực phải định nghĩa thêm order ID/idempotency, reservation receipts, expiry và các thao tác khác trong transaction nếu cần atomicity.

### 10.3. @Transactional không tự retry mọi lỗi

MongoTransactionManager chủ yếu quản lý **begin, commit, rollback** của Spring transaction. Không mặc định annotation này cho semantics giống hệt **Java Sync Driver withTransaction** trong mọi version.

Một RetryTemplate hoặc **@Retryable** đặt sai chỗ có thể retry **bên trong transaction đã lỗi** hoặc chạy lại một **@Transactional method sau commit unknown** mà không có idempotency.

### 10.4. Đặt retry ngoài transaction boundary

Ý tưởng:

~~~text
Outer orchestration service:
  classify exception
  enforce retry budget/idempotency
  call transactional service through Spring proxy

Transactional service:
  one attempt
  MongoDB writes
  commit/rollback
~~~

Khi retry toàn body, mỗi attempt phải dùng một **Spring transaction mới**, không reuse transaction context đã thất bại.

Nếu commit outcome chưa xác định, **không tự retry toàn @Transactional method** mà không có transaction-aware handling và business reconciliation.

### 10.5. Spring proxy/self-invocation

~~~java
@Service
class BadService {
    public void call() {
        this.saveInTransaction(); // Bypasses proxy interception.
    }

    @Transactional
    public void saveInTransaction() {
        // May not run in a transaction when self-invoked.
    }
}
~~~

Trong cấu hình proxy-based thông thường, gọi một method cùng bean qua **this** không đi qua Spring proxy nên transaction advice có thể không được áp dụng.

Sửa thiết kế bằng cách gọi transactional method qua một **Spring-managed bean/proxy** phù hợp và xác minh bằng integration test.

### 10.6. Exception bị nuốt

~~~java
@Transactional
public void badTransfer() {
    try {
        debit();
        credit();
    } catch (RuntimeException ex) {
        // Dangerous: method exits without propagating failure.
    }
}
~~~

Nếu exception bị swallow, Spring transaction manager có thể cố commit. Để rollback, propagate unchecked exception hoặc dùng transaction rollback policy rõ ràng. Với checked exceptions, mặc định Spring rules có thể khác; khi cần cấu hình **rollbackFor**.

### 10.7. Không trộn MongoDB và SQL transaction managers

Một @Transactional gắn **JpaTransactionManager** không tự làm MongoDB writes atomic chung với PostgreSQL; ngược lại **MongoTransactionManager** không tự commit Kafka/HTTP gateway.

Đối với nhiều hệ thống, cân nhắc **outbox, saga và compensation** với ranh giới đảm bảo rõ.

### 10.8. Khi Spring bọc MongoDB error

Spring Data có thể dịch MongoDB exceptions sang nhóm **DataAccessException** theo Spring exception translation, tùy version và API. Đừng đặt logic business retry dựa độc nhất vào exception message, cũng đừng assume mọi DataAccessException đều transient.

Thiết kế adapter có thể:

1. Bảo tồn root cause và MongoDB error labels khi còn.
2. Phân loại retryable transaction attempts.
3. Xác định commit phase/unknown outcome.
4. Áp dụng idempotency và retry budgets.
5. Log sanitized error category.

### 10.9. Reactive transaction

ReactiveMongoTemplate/ReactiveMongoRepository có transaction APIs/ReactiveMongoTransactionManager riêng. Không copy thẳng synchronous retry/ThreadLocal assumptions vào Reactor pipeline.

Trong reactive code, chú ý:

- Session/transaction context qua Reactor context.
- Backpressure và cancellation.
- Retry operator có thể resubscribe toàn pipeline.
- External side effects trong pipeline được subscribe lại.
- Không block event-loop để backoff hoặc gọi network phụ.

**Một resubscription sai chỗ có thể thực thi lại body sau commit unknown**. Thiết kế recovery cần bám transaction protocol của reactive driver/framework.

## 11. Idempotency: không cho retry biến thành double write

### 11.1. Một write riêng lẻ với $inc

Ví dụ:

~~~javascript
db.counters.updateOne(
  { _id: "checkout" },
  { $inc: { count: 1 } }
);
~~~

Nếu response bị mất sau server execution, một lệnh $inc mới được application phát lại **có thể làm count tăng thêm**. Retryable writes protocol có những bảo đảm riêng, nhưng một custom retry loop không tự tái sử dụng đúng statement identity.

### 11.2. Stable idempotency key

Một HTTP request:

~~~http
POST /orders HTTP/1.1
Idempotency-Key: order-create-c4a7
Content-Type: application/json

{
  "customerId": "C-17",
  "items": [{"sku": "SKU-1", "quantity": 2}]
}
~~~

Ứng dụng nên lưu business order/receipt với một khóa ổn định ứng với request. Khi client gửi lại do timeout, server đọc trạng thái đã commit thay vì tạo order khác.

### 11.3. Unique index là bảo vệ ở DB

Ví dụ:

~~~javascript
db.orders.createIndex(
  { clientRequestId: 1 },
  { unique: true }
);
~~~

Khi đồng thời có hai requests cùng key, chỉ một record cùng key có thể tồn tại bình thường. Nhưng cần:

- Query/validation so immutable request inputs.
- Cùng transaction cho các updates liên quan.
- Đọc lại sau duplicate-key race.
- Phân biệt record đã commit và request đang pending.

Không đổi clientRequestId ngẫu nhiên khi gặp duplicate key để “giúp retry thành công”.

### 11.4. Key trùng nhưng payload khác

~~~text
Key = k-100
First request: quantity=2
Second request: quantity=100
~~~

Đừng trả success của request đầu cho request thứ hai mà không phát hiện mismatch. Gắn key với **canonicalized request fingerprint/immutable parameters** và trả conflict theo API contract.

### 11.5. Read after unknown commit

Nếu retry budget hết:

~~~text
Business request may have committed
       |
       v
Lookup durable receipt by original key
       |
       +--> COMMITTED + matching params: return recorded result
       |
       +--> CONFLICT: reject different request
       |
       +--> No record yet / uncertain: pending reconciliation
~~~

**Không thấy receipt trong một read từ secondary lag không chứng minh abort**. Dùng read preference/read concern phù hợp và poll có deadline.

### 11.6. Idempotency retention

Nếu TTL xóa idempotency records sau 24 giờ nhưng client có thể replay event sau 7 ngày, request cũ có thể được xử lý lần hai.

Retention của business dedup records cần phù hợp **replay horizon, audit requirements và khả năng tạo lại side effects**.

### 11.7. Transactional outbox cho Kafka/email

Một transaction MongoDB không thể rollback email đã gửi hay HTTP request đã tới payment gateway.

~~~text
MongoDB transaction:
  create order
  reserve inventory
  insert outbox event
  commit

Background dispatcher:
  read outbox
  send event
  mark dispatched
~~~

Dispatcher có thể publish event nhiều lần nếu crash sau send nhưng trước mark, nên consumer cần event ID và deduplication. **Outbox thường hướng tới at-least-once delivery, không tự tạo exactly-once ở mọi boundary**.

## 12. Runbook 1 — Xử lý NotWritablePrimary trên replica set

### 12.1. Định nghĩa hiện tượng

~~~text
2026-11-14T11:00:00Z checkout-api
  MongoCommandException: NotWritablePrimary, code=10107

2026-11-14T11:00:02Z checkout-api
  MongoTimeoutException: Timed out while selecting primary
~~~

Hai lỗi gần nhau có thể liên quan cùng một primary election, nhưng phải quan sát topology và logs để kết luận.

### 12.2. Thu dữ liệu trước khi thay đổi cluster

Ghi lại:

1. Timestamps cùng timezone.
2. Namespace/operation và driver exception class.
3. Error code, labels, transaction phase.
4. MongoDB driver/server versions.
5. Connection URI topology parameters đã che credentials.
6. Replica set members, primary/election events.
7. Application timeouts, retry và pool config.
8. Duration/frequency của lỗi.
9. Requests thành công, error rate, p95/p99.

Restart thành công tạm thời có thể che root cause network/DNS mãi chưa được sửa.

### 12.3. Kiểm tra primary

Trong mongosh:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

Trên replica set member có quyền:

~~~javascript
rs.status();
~~~

Cần biết có PRIMARY hay không, member nào healthy, election gần đây, hosts có reachable và majority có khả dụng không. Không chỉnh replica set config ở bước chẩn đoán read-only.

### 12.4. Kiểm tra connection string

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/orders?replicaSet=rsOrders
~~~

Cần sửa nếu:

- Chỉ trỏ secondary qua directConnection.
- Sai replicaSet name.
- Member quảng bá hostname client không resolve được.
- Port/TLS/SRV configuration sai.
- DNS/network policy không cho kết nối tới hosts trong rs.conf().

Nếu dùng managed deployment, ưu tiên URI chính thức của provider.

### 12.5. Server-selection timeout

Ví dụ:

~~~text
serverSelectionTimeoutMS = 1000
primary election/discovery takes several seconds
~~~

Application có thể timeout trước khi driver tìm primary. Tăng timeout có thể phù hợp một số SLO, nhưng **không sửa được** trường hợp cluster mất majority, DNS sai hoặc firewall chặn nodes. Phối hợp với HTTP deadline, circuit breaker và request retry budget.

### 12.6. Connection pool

Nếu primary khỏe nhưng application vẫn timeout, kiểm tra pool checkout wait, connection creation sau failover, socket exhaustion, thread starvation và số MongoClient instances.

Đừng tăng maxPoolSize rất lớn nếu chưa đo pool wait và server headroom.

### 12.7. Lỗi chỉ xảy ra khi maintenance

~~~text
02:00:00 maintenance begins
02:00:03 primary election
02:00:04 NotWritablePrimary spike
02:00:08 new primary discovered
02:00:09 traffic recovered
~~~

Một đợt lỗi ngắn có thể là failover bình thường. Tuy nhiên nếu SLO không cho phép request errors, cần xem retry/buffering/idempotency; không bỏ qua user impact.

### 12.8. Không làm những điều này trước khi biết nguyên nhân

- Restart mọi mongod cùng lúc.
- Gọi stepDown liên tục trên production.
- Thay priorities/votes để ép primary.
- Dùng directConnection tới một node cố định.
- Chuyển writes sang secondary.
- Giảm write concern bất chấp durability requirements.
- Mở infinite retry loop.

### 12.9. Ví dụ báo cáo sự cố

~~~text
Symptom: NotWritablePrimary spike 7 seconds
Scope: checkout-api writes to replica set rsOrders
Evidence: election T1, new primary T2
Impact: 0.8% request errors, p99 doubled
Mitigation: bounded retry and idempotency
Follow-up: verify member reachability and election rate
~~~

## 13. Runbook 2 — WriteConflict tăng đột biến

### 13.1. Pattern nhận diện

~~~text
MongoCommandException: WriteConflict (112)
errorLabels: ["TransientTransactionError"]
~~~

Nếu xảy ra trong transaction body và có TransientTransactionError, driver có thể retry attempt. Nhưng conflicts lặp dày đặc là dấu hiệu capacity/contention cần xử lý.

### 13.2. Các câu hỏi điều tra

1. Bao nhiêu transaction attempts thất bại?
2. Bao nhiêu logical business operations thành công?
3. Có hot document như global counter/stock record không?
4. Transaction durations có tăng?
5. Có scans/aggregation thiếu index trong callback?
6. Concurrency và peak traffic mới?
7. Có batch jobs cập nhật cùng documents?
8. Retry storm có làm thêm contention?
9. Lỗi trong body hay commit?
10. Invariants sau retries có đúng?

### 13.3. Hot document

~~~javascript
db.globalCounters.updateOne(
  { _id: "all-orders" },
  { $inc: { count: 1 } }
);
~~~

Nếu mọi request tranh cập nhật một document, nó là hotspot. Cân nhắc sharded/distributed counter khi semantics cho phép, analytics bất đồng bộ, hoặc conditional atomic update với throughput limit phù hợp.

Sharding collection không tự phân tán một hot key nếu mọi writes vẫn rơi vào cùng document/range.

### 13.4. Transaction quá dài

~~~text
T1 begins
  -> find 1M documents
  -> CPU-heavy aggregation
  -> wait for REST API
  -> update hot inventory document
  -> commit
~~~

Giảm thời gian transaction:

- Dùng targeted indexed predicates.
- Đưa external I/O ra ngoài callback.
- Chỉ đọc fields cần.
- Giảm số documents trong attempt.
- Tách reports/batch khỏi hot path.
- Sử dụng conditional writes để enforce invariants.

### 13.5. Cạnh tranh một inventory document

~~~text
SKU-X available=100
100 concurrent transactions each reserves one unit
~~~

Đo throughput/latency theo concurrency và so:

- Một atomic update per document nếu chỉ cần sửa một document.
- Transaction ngắn cho order + reservation khi cần atomicity.
- Inventory partition theo location/batch nếu business cho phép.
- Queue/serialize theo hot SKU khi thích hợp.

Không giảm consistency để né conflicts nếu sẽ gây oversell.

### 13.6. Optimistic concurrency bằng version

~~~javascript
db.products.updateOne(
  { _id: "SKU-X", version: 9 },
  {
    $set: { priceCents: NumberLong("12000") },
    $inc: { version: 1 }
  }
);
~~~

Nếu matchedCount=0, version đã đổi hoặc record không tồn tại; application reread và quyết định retry/conflict. Version predicate hỗ trợ optimistic concurrency nhưng không thay transaction khi nhiều documents cần atomicity.

### 13.7. Có nên tăng retry attempts?

Theo dõi:

~~~text
successful business operations/second
body attempts per successful operation
transaction p95/p99
CPU/cache/disk pressure
failure rate after bounded retries
~~~

Nếu attempts/s tăng mà successful throughput không tăng, tối ưu contention thay vì retry nhiều hơn.

### 13.8. Technical conflict khác business conflict

Business conflict:

~~~text
matchedCount=0 because balance is insufficient
~~~

không nhất thiết có server error code. Application phải trả business rejection. WriteConflict là technical error có thể retry theo label/protocol. Đặt metrics và alert riêng cho hai nhóm.

## 14. Runbook 3 — UnknownTransactionCommitResult

### 14.1. Tình huống rủi ro

~~~text
Transfer T-1001:
  debit source
  credit destination
  insert receipt
  send commitTransaction
  socket timeout
~~~

Ở đây không thể chỉ nhìn exception rồi xác định **commit đã thất bại**. Server có thể đã commit nhưng response chưa tới client.

### 14.2. Khi còn cùng session

Nếu Java Driver vẫn quản lý **ClientSession/transaction** và lỗi có **UnknownTransactionCommitResult**, áp dụng retry commit theo driver rules:

~~~text
Same session
Same transaction identity
Retry commitTransaction
Do not rerun debit/credit body
~~~

Ưu tiên **withTransaction** để driver thực hiện protocol thay vì tự phát lệnh.

### 14.3. Khi HTTP request/session đã đóng

Ví dụ server process crash sau khi gửi commit. Không thể tùy tiện mở một session mới rồi tiếp tục commit của session cũ.

Dùng **durable business receipt/idempotency key**:

1. Lấy transfer ID từ original request.
2. Đọc receipt từ primary theo consistency phù hợp.
3. So immutable payload: amount, currency, source và destination.
4. Nếu COMMITTED và match, trả kết quả cũ.
5. Nếu conflict, trả idempotency key misuse.
6. Nếu chưa có record mà outcome chưa rõ, đưa vào pending reconciliation có deadline/backoff.
7. Không tạo transfer ID khác để debit lại ngay.

### 14.4. Không thấy receipt một lần chưa đủ

Một lần đọc secondary lag hoặc một query trong lúc election không chứng minh transaction chắc chắn abort. Thiết kế **bounded polling, majority/primary read consistency và reconciliation policy**; khi không giải quyết được, giữ trạng thái UNKNOWN.

### 14.5. Ví dụ status API

~~~http
GET /transfers/T-1001
~~~

Kết quả có thể:

~~~json
{
  "transferId": "T-1001",
  "state": "COMMITTED",
  "amountUnits": 150000
}
~~~

hoặc:

~~~json
{
  "transferId": "T-1001",
  "state": "PENDING_RECONCILIATION"
}
~~~

Không map “chưa thấy commit” và “đã xác nhận thất bại” thành cùng một state FAILED nếu business cần phân biệt.

### 14.6. Không compensate chỉ vì timeout

Compensating/reversal transaction cần dựa trên **business state đã xác nhận**, authorization và audit. Nếu chuyển tiền ban đầu không commit mà hệ thống bù tiền ngay, nó có thể tạo nghiệp vụ sai.

### 14.7. Sau khi giải quyết

Kiểm tra:

~~~text
Exactly one transfer receipt
Source balance changed once
Destination balance changed once
No unexpected compensating transfer
No unowned pending reconciliation
~~~

## 15. Runbook 4 — Server selection timeout, network timeout và write concern

### 15.1. Server selection timeout

~~~text
MongoTimeoutException:
  Timed out while selecting a server
  matching WritableServerSelector
~~~

Driver chưa tìm được primary phù hợp. Điều tra:

- Replica set có PRIMARY?
- Driver topology snapshot có stale?
- Member hosts trong rs.conf() có reachable?
- DNS/TLS/authentication hoặc firewall?
- Network partition, proxy behavior?
- Timeout/pool configuration?

Không giảm durability hoặc retry $inc vô hạn.

### 15.2. Network timeout sau khi write được gửi

~~~text
Client sent write
Network lost before response
~~~

Outcome của write có thể chưa rõ. Với retryable write được driver hỗ trợ, driver thực hiện retry theo protocol. HTTP/gateway có thể resend cả logical business operation, vì vậy vẫn cần idempotency.

### 15.3. Write concern timeout

Ghi với **w: majority** có thể không nhận acknowledgment trong giới hạn thời gian do replication lag/availability. **Write concern timeout không chứng minh primary chưa áp dụng write.**

Trong transaction, xem commit result và error labels; không phát một business transaction mới ngay sau write concern timeout.

### 15.4. Không đạt majority

Nếu replica set ba voting members nhưng chỉ một node accessible, election/majority writes có thể không tiến triển.

Kiểm tra member states/connectivity, replication lag, disk/network, write concern errors và thực hiện recovery theo runbook đã duyệt. Không tự hạ **w: majority** xuống w:1 nếu nghiệp vụ cần majority durability.

### 15.5. Phân biệt client failure và server failure

Nếu một application service lỗi server selection còn service khác vẫn khỏe, có thể do app-specific DNS, network segment, driver version, URI/pool hoặc proxy/TLS khác.

Không kết luận toàn cluster down chỉ từ một instance.

## 16. Read-only diagnostics trong mongosh

Các commands sau yêu cầu quyền phù hợp. Output tùy MongoDB version và có thể chứa hostnames/metadata hạ tầng, vì vậy cần che thông tin nhạy cảm khi chia sẻ.

### 16.1. hello

~~~javascript
const hello = db.adminCommand({ hello: 1 });

printjson({
  setName: hello.setName,
  isWritablePrimary: hello.isWritablePrimary,
  secondary: hello.secondary,
  primary: hello.primary,
  hosts: hello.hosts
});
~~~

hello cho snapshot server state tại thời điểm gọi, không thay monitoring toàn replica set.

### 16.2. rs.status()

~~~javascript
const status = rs.status();

printjson({
  set: status.set,
  myState: status.myState,
  members: status.members && status.members.map(member => ({
    name: member.name,
    stateStr: member.stateStr,
    health: member.health,
    optimeDate: member.optimeDate
  }))
});
~~~

Fields có thể khác/thiếu theo version. Không suy commit outcome từ optime của một member đơn lẻ mà không hiểu replication consistency.

### 16.3. serverStatus()

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson({
  uptime: s.uptime,
  connections: s.connections,
  opcounters: s.opcounters,
  transactions: s.transactions,
  wiredTigerCache: s.wiredTiger
    ? s.wiredTiger.cache
    : undefined
});
~~~

ServerStatus có counters/gauges về transaction và WiredTiger cache tùy version/storage engine. Không giả định mọi field luôn tồn tại.

### 16.4. Current operations và profiler

Các công cụ **currentOp/$currentOp** giúp điều tra operations đang chạy theo server version. Nhưng:

- Output là snapshot ngắn hạn.
- Có thể chứa query text/namespace nhạy cảm.
- Tránh scan toàn bộ không giới hạn trong dashboard có scrape interval rất ngắn.
- Profiler có overhead và phải được bật theo change/monitoring policy.

Ưu tiên logs/traces/query shape metrics được sampling phù hợp.

### 16.5. Java Driver command monitoring

Java Sync Driver hỗ trợ **CommandListener** và connection/server monitoring. Dùng events theo APIs tương ứng để phân biệt:

~~~text
Command: update
Command: insert
Command: commitTransaction
Command: abortTransaction
~~~

Không log raw commands vì có thể chứa PII, tokens hoặc số dư. Chỉ log command name, duration, sanitized request trace ID, error class/code/labels.

### 16.6. Rates thay vì cumulative counters

Một counter minh họa:

~~~text
writeConflicts(t0) = 1000
writeConflicts(t1) = 1120
elapsed = 60 seconds
rate = (1120 - 1000) / 60 = 2 conflicts/s
~~~

Counter có thể reset khi mongod restart; collector phải phát hiện reset và đối chiếu timestamps/source node. Tên metric cụ thể lấy từ dashboard/provider/server version.

### 16.7. Attempts khác business successes

~~~text
One logical checkout:
  attempt 1 = aborted
  attempt 2 = aborted
  attempt 3 = committed

Transaction attempts = 3
Business orders created = 1
~~~

Không gọi retries hoặc transaction attempts là số orders đã tạo trong business reports.

## 17. Metrics và cảnh báo cho lỗi tạm thời

### 17.1. Metrics ứng dụng

| Metric ý tưởng | Ý nghĩa | Labels giới hạn |
|---|---|---|
| **mongo.tx.attempts** | Số transaction body attempts. | service, operation. |
| **mongo.tx.committed** | Số attempts xác nhận commit. | operation. |
| **mongo.tx.aborted** | Số aborts. | operation, error category. |
| **mongo.tx.body.retries** | Số body retries. | operation, error category. |
| **mongo.tx.commit.retries** | Số commit retries. | operation. |
| **mongo.tx.unknown.outcomes** | Số commit unknown outcomes. | operation. |
| **mongo.write.conflicts** | Technical write conflicts được quan sát. | collection/operation khi hợp lý. |
| **mongo.server.selection.timeouts** | Chờ writable server thất bại. | service, cluster. |
| **mongo.not.primary** | NotWritablePrimary occurrences. | service, cluster. |
| **mongo.tx.duration** | Transaction p50/p95/p99. | operation. |
| **business.idempotency.hits** | Replay trả record cũ. | operation. |
| **business.reconcile.pending** | Requests outcome unknown chưa giải quyết. | service. |

Đây là **metrics do ứng dụng tự đặt tên**, không phải các field MongoDB mặc định. Không dùng transferId/customerId làm labels có hàng triệu values; chúng gây cardinality explosion và có thể lộ dữ liệu.

### 17.2. Theo dõi số attempts trên mỗi successful business operation

~~~text
bodyAttempts = 10000
successes = 8000
averageAttemptsPerSuccess = 1.25
~~~

Chỉ số cần diễn giải cẩn thận khi có failed business requests; có thể tính theo trace/request IDs thay vì chia tổng counters mù quáng. Nếu attempts/s tăng mà successful throughput không tăng, retry đang làm hệ thống thêm bận.

### 17.3. Alert theo xu hướng thay vì một lỗi đơn lẻ

~~~text
NotWritablePrimary short spike
  + election
  + fast automatic recovery
  -> operational event; assess SLO impact

NotWritablePrimary persistent
  + no primary observed
  -> high-severity availability investigation

WriteConflict sustained increase
  + transaction p99 increase
  -> contention/root-cause investigation

UnknownTransactionCommitResult
  + reconciliation pending increasing
  -> protect business consistency and expedite resolution
~~~

Không alert Critical chỉ vì một transaction abort hợp lệ do business rule.

### 17.4. Dashboard các lớp

~~~text
Application SLO:
  successful requests/sec, errors, p95/p99

MongoDB Driver:
  server-selection, pool waits, network failures

Replica Set:
  elections, primary health, replication lag

Transaction:
  duration, commit/abort, retries, unknown outcomes

Data Correctness:
  unique receipts, idempotency, reconciliation backlog
~~~

Một dashboard chỉ có CPU và disk không đủ chẩn đoán lỗi commit unknown.

### 17.5. Correlation IDs và logs

Nên ghi:

~~~text
traceId=trace-123
operation=reserveInventory
phase=transaction-body
attempt=2
errorCode=112
errorLabel=TransientTransactionError
outcome=RETRYING
~~~

Tách **transaction attempt number**, **commit attempt number** và **logical request ID** ở instrumentation. Không dùng raw lsid/transaction number từ MongoDB làm business idempotency key.

### 17.6. Guardrails về privacy

Các logs/error reports không nên có:

- Passwords/connection strings nguyên vẹn.
- JWT/access tokens.
- Full BSON documents có PII.
- Full account balances nếu policy cấm.
- Raw merchant/customer IDs làm metrics labels.

Tối thiểu hóa dữ liệu và giữ diagnostic fields cần thiết: error category/code/label, service, operation, latency và anonymized trace ID.

## 18. Thiết kế môi trường lab tái hiện lỗi

Để chứng minh ứng dụng xử lý lỗi đúng, cần tests trên **replica set thật**, không chỉ mocks ném Exception.

### 18.1. Mức test theo khả năng

| Môi trường | Kiểm thử tốt | Giới hạn |
|---|---|---|
| Unit test/mock | Phân loại error labels, backoff, idempotency decision. | Không chứng minh MongoDB transaction atomicity/election. |
| Single-node replica set | Commit/abort, session wiring, write conflicts ở mức ứng dụng. | Không có primary failover sang node khác. |
| Three-member replica set | Election, majority availability, secondary lag, connection recovery. | Một host chạy ba containers không mô phỏng mất cả datacenter. |
| Network proxy/fault injector lab | Drop/delay connections, partial network failure. | Timing của commit/ACK có thể khó tái hiện chính xác. |

Test fixtures nên có database riêng, indexes tạo trước, request IDs unique, timeouts rõ và cleanup chỉ tài nguyên lab.

### 18.2. Thiết lập single-node replica set thử nghiệm

Ví dụ trên máy Unix-like **cô lập**, có mongod:

~~~bash
mkdir -p /tmp/mongodb-errors-lab

mongod \
  --replSet rsErrorLab \
  --bind_ip localhost \
  --port 27018 \
  --dbpath /tmp/mongodb-errors-lab
~~~

Trong mongosh kết nối port 27018:

~~~javascript
rs.initiate({
  _id: "rsErrorLab",
  members: [{ _id: 0, host: "localhost:27018" }]
});
~~~

Đợi PRIMARY bằng polling/rs.status. Không dùng dbpath/cổng của MongoDB đang chứa dữ liệu thật. Trong Docker/Kubernetes, hostnames phải resolve được từ **process chạy driver**, không chỉ trong container.

### 18.3. Seed test accounts và receipt collection

~~~javascript
const lab = db.getSiblingDB("app_test");

lab.createCollection("accounts");
lab.createCollection("transfer_receipts");

lab.accounts.insertMany([
  { _id: "A", balanceUnits: NumberLong("1000") },
  { _id: "B", balanceUnits: NumberLong("300") }
]);
~~~

Chỉ seed vào collection/database trống do lab sở hữu. Nếu chạy lại, dùng IDs/prefix mới hoặc fixtures cô lập; không xóa toàn bộ database chia sẻ.

### 18.4. Test application-level abort

Trong mongosh:

~~~javascript
const session = db.getMongo().startSession();
const sdb = session.getDatabase("app_test");

session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});

try {
  sdb.accounts.updateOne(
    { _id: "A" },
    { $inc: { balanceUnits: NumberLong("-200") } }
  );

  throw new Error("Injected lab failure before credit");

} catch (error) {
  session.abortTransaction();
} finally {
  session.endSession();
}
~~~

Sau abort, đọc primary và xác nhận A vẫn 1000, B vẫn 300. Đây là test atomic abort, **không phải test NotWritablePrimary hoặc server WriteConflict**.

### 18.5. Test WriteConflict hai sessions

Thiết kế test:

~~~text
T1 startTransaction
T2 startTransaction
T1 read account A
T2 read account A
T1 update A
T2 try update A
Observe conflict/abort/retry behavior
~~~

Lưu ý: một write đang chờ/transaction snapshot có thể tạo timing khác theo version/driver. Để test có tính quyết định, dùng **barriers/latches** và **deadlines**, không chỉ sleep ngẫu nhiên.

Sau test, xác nhận **số dư đúng và không có double effect**. Error label có thể khác theo tình huống; ghi thực tế.

### 18.6. Fault injection bằng failCommand

MongoDB có **configureFailPoint / failCommand** cho môi trường test ở những builds/deployments hỗ trợ.

Ví dụ **chỉ trên lab**:

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

Thí nghiệm này gây lỗi đường kết nối cho commit command khi failpoint được áp dụng. **Không có nghĩa nó chắc chắn làm server commit thành công rồi đánh rơi response**; failpoint có thể can thiệp trước command execution.

Test cần kiểm tra:

- Driver exception/labels.
- Retry behavior.
- Durability/invariants sau khi recovery.
- Idempotency của business request.

Không gắn một kết quả “server committed before failure” nếu chưa khống chế timing và quan sát được.

### 18.7. Tắt failpoint sau test

~~~javascript
db.adminCommand({
  configureFailPoint: "failCommand",
  mode: "off"
});
~~~

Nếu failpoint không được hỗ trợ hoặc managed provider từ chối, dùng test harness/network proxy tương ứng. **Không cấp quyền rộng cho production** chỉ để bật failpoint.

### 18.8. Primary stepdown trong multi-node lab

Khi có primary và secondaries khỏe:

~~~javascript
rs.stepDown(15);
~~~

Thao tác này làm primary từ chức theo supported behavior, có thể tạo election. Chỉ thực hiện khi **lab cô lập**, có thể mất kết nối thử nghiệm và có quyền phù hợp.

Kiểm tra:

1. Client thấy NotWritablePrimary/server-selection errors ở thời điểm nào?
2. Có primary mới được bầu không?
3. Driver reconnect mất bao lâu?
4. Transaction đang chạy bị abort/retry hay unknown commit?
5. Sau recovery, persisted state và receipt có đúng không?

Không chạy stepDown trên production/shared replica set để luyện tập.

### 18.9. Network proxy để kiểm tra retry

~~~text
Java test app
     |
     v
Fault injection proxy
     |
     v
Replica set
~~~

Proxy có thể tạo packet loss, delayed response hoặc close connection theo kịch bản. Tuy nhiên việc “drop response sau khi commit hoàn tất” đòi hỏi điểm đồng bộ đủ chính xác. Nếu không có điều kiện chứng minh, chỉ báo **network fault near commit**.

### 18.10. Không trộn ba faults cùng lúc

Một test mới nên inject đúng một loại fault:

~~~text
Test A: application exception after debit
Test B: write conflict during transaction
Test C: primary stepdown during body
Test D: connection interruption around commit
~~~

Sau khi hiểu từng lỗi, mới chạy chaos/soak test tổng hợp. Ghi timeout và preconditions để test có thể tái lập.

## 19. Test matrix: lỗi, kỳ vọng và cách xác nhận

| Test | Cách tạo lỗi | Kỳ vọng |
|---|---|---|
| Happy path | Không inject | Account A trừ, B cộng, receipt đúng một. |
| Business reject | Insufficient funds | No commit, không retry vô hạn. |
| Explicit abort | Throw sau debit | Debit rollback, không receipt. |
| Missing session | Viết ngoài session | Negative test chỉ ra write không được rollback. |
| WriteConflict | Hai transactions sửa cùng doc | Retry attempt theo label, không double update. |
| NotWritablePrimary | Stepdown trên lab | Driver phục hồi topology, retry đúng scope. |
| Server selection timeout | Không có writable primary trong lab | Bounded failure, không loop vô hạn. |
| Unknown commit result | Network fault near commit | Retry commit khi có thể; durable outcome reconciliation. |
| Duplicate business key | Cùng request gửi hai lần | Không debit hai lần, trả existing result. |
| Key reused with different payload | Giữ key, đổi amount | Conflict, không commit request mới. |
| Two concurrent same-key requests | Barrier + unique receipt | Một business effect; race được reconcile. |
| Write concern timeout | Majority không đáp ứng trong lab | Không coi response timeout là proof abort. |
| Secondary stale read | Đọc secondary lag | Không kết luận commit rollback do data cũ. |
| Pool exhaustion | Load generator controlled | Bounded wait/timeout, có metrics. |
| External side effect | Callback retries | Không publish trùng ngoài transaction; outbox/dedup. |

### 19.1. Assertion phải dựa trên trạng thái đã commit

~~~text
Before:
  A = 1000
  B = 300
  Sum = 1300

After committed transfer of 200:
  A = 800
  B = 500
  Sum = 1300
  ReceiptCount(requestId) = 1
~~~

Sau abort:

~~~text
  A = 1000
  B = 300
  ReceiptCount(requestId) = 0
~~~

**Exception được ném không phải bằng chứng rollback** nếu một update vô tình chạy ngoài session. Đọc lại persisted data với read semantics phù hợp.

### 19.2. Kiểm tra retry ở hai cấp

- **Internal driver retry:** body/commit logic theo error label.
- **External business retry:** HTTP/message replay với stable idempotency key.

Một test chỉ xác nhận internal retry vẫn chưa chứng minh endpoint an toàn khi HTTP response bị mất sau commit.

### 19.3. Kỳ vọng có thể là UNKNOWN hợp lệ

Nếu lab mất network dài hơn request deadline, ứng dụng có thể không thể xác định commit outcome ngay. Một API trả **pending/unknown** với reconciliation là hành vi đúng hơn trả chắc chắn failed rồi làm business effect lần nữa.

### 19.4. Dùng polling có deadline

Không viết:

~~~text
sleep(100 milliseconds)
assert election completed
~~~

Election và network recovery mất thời gian biến thiên. Poll đến khi condition quan sát được hoặc hết deadline, ghi diagnostics khi timeout.

### 19.5. Quan sát đúng primary

Nếu test đọc từ một secondary có lag, trạng thái có thể cũ. Xác định read preference/read concern cho assertions; với durability test, dùng consistent observation policy phù hợp majority commit.

## 20. Những lỗi triển khai thường gặp

### 20.1. Retry mọi MongoException

~~~java
catch (MongoException ex) {
    return retryEverything();
}
~~~

Sai vì MongoException có thể là DuplicateKey, Unauthorized, invalid schema, WriteConflict, server-selection timeout hoặc unknown commit. Các loại có retry scopes khác nhau.

### 20.2. Retry $inc bằng một command mới

~~~text
First $inc executed, response lost
Application sends independent $inc again
Counter increases twice
~~~

Retryable-write protocol của driver khác với một loop phát commands mới. Dùng driver-managed retry hoặc business idempotency.

### 20.3. Bỏ qua TransientTransactionError

Nếu một transaction body thất bại vì WriteConflict có nhãn transient, không tiếp tục attempt cũ như không có chuyện gì. Retry **toàn transaction** trên attempt mới, đọc lại conditions.

### 20.4. Retry body khi commit unknown

~~~text
commitTransaction -> response lost
application immediately reruns debit and credit
~~~

Transaction đầu có thể đã commit. Retry **commit cùng transaction** hoặc reconcile receipt; không debit một lần nữa.

### 20.5. Tạo idempotency key trong callback

~~~java
session.withTransaction(() -> {
    String requestId = UUID.randomUUID().toString();
    // ...
});
~~~

Callback được replay có thể tạo ID mới, làm dedup thất bại. Sinh stable business key trước callback và dùng lại qua HTTP retries.

### 20.6. Catch exception rồi Spring commit

~~~java
@Transactional
public void badOperation() {
    try {
        updateOne();
        updateTwo();
    } catch (Exception ex) {
        // Swallowed: transaction manager may commit.
    }
}
~~~

Propagate exception hoặc đánh dấu rollback theo Spring transaction policy. Checked/unchecked exceptions có rules khác theo mặc định.

### 20.7. Trộn clients/sessions

~~~text
ClientSession created from client A
Repository/driver operation uses client B without that session
~~~

Các operations phải tham gia đúng context. Tạo MongoClient mới trong transactional method có thể dẫn đến write ngoài transaction.

### 20.8. Hard-code primary

URI directConnection chỉ tới node01 có thể chạy lâu rồi liên tục NotWritablePrimary khi node01 stepdown. Dùng replica set URI và driver SDAM.

### 20.9. Tăng timeout nhưng không sửa DNS

Nếu driver không resolve được member hosts, tăng serverSelectionTimeoutMS chỉ làm user chờ lâu hơn. Sửa URI/network.

### 20.10. Giảm write concern tùy tiện

Thay majority bằng w:1 làm thay đổi durability/failover semantics. Phải qua phân tích business risk, không dùng workaround mặc định.

### 20.11. Chỉ đo retry attempts, không đo successful throughput

~~~text
Retries/sec: 1000
Successful orders/sec: 50
~~~

Retry tăng không đồng nghĩa thành công nghiệp vụ tăng. Đo p95/p99, successful QPS và error budget.

### 20.12. Kiểm thử election bằng sleep ngắn

Election timing biến thiên. Dùng polling điều kiện PRIMARY/recovery có deadline và diagnostics.

### 20.13. Đọc secondary stale rồi kết luận rollback

Secondary lag có thể trả state cũ dù primary đã commit. Chọn read consistency phù hợp.

### 20.14. Không kiểm tra matchedCount

Transaction có thể commit dù update không match. Với đủ tiền hoặc inventory reservation, matchedCount=0 cần business rejection và abort.

### 20.15. DuplicateKey bị coi là transient

Đọc existing record, so immutable parameters; cùng request có thể trả result cũ, khác request là conflict.

### 20.16. Unique key nhưng mỗi retry lại đổi ID

Nếu mỗi HTTP retry tạo request ID mới, unique index không thể phát hiện cùng nghiệp vụ.

### 20.17. Publish message trong callback

Callback có thể retry sau WriteConflict; Kafka/email không rollback theo MongoDB. Dùng outbox và consumer deduplication.

### 20.18. Long transaction

Transaction dài có thể làm tăng snapshot/cache pressure, timeouts và conflicts. Giữ callback ngắn, indexed, không chờ external I/O.

### 20.19. Retry storm

~~~text
100 service replicas
x 500 in-flight requests
x 5 immediate retries
= up to 250000 operation attempts
~~~

Đây chỉ là phép tính minh họa upper bound cho workload; số thực tế tùy control. Dùng deadlines, jitter, backpressure và circuit breaker.

### 20.20. Chuyển writes sang secondary

Secondary không phải nơi nhận ordinary application writes của replica set. Sửa topology/driver/election thay vì bypass primary.

### 20.21. Bỏ write concern failure vì “đã thấy document”

Write concern timeout không chứng minh durability majority đã đạt, dù primary có thể đã áp dụng write. Reconcile và kiểm tra durability theo contract.

### 20.22. Gộp UNKNOWN vào FAILED

Nếu API chỉ có SUCCESS/FAILED và timeout luôn thành FAILED, caller có thể gửi lại bằng ID mới. Cần status pending/unknown cùng reconciliation.

### 20.23. Không giới hạn failpoint test

FailCommand, network proxy và rs.stepDown có thể ảnh hưởng availability. Chỉ dùng trên lab cô lập và cleanup failpoint sau test.

### 20.24. Không lưu thông tin điều tra

Elections có thể chỉ kéo dài vài giây. Log error code, labels, phase, driver version và timestamps có redaction để phân tích lại.

## 21. Sơ đồ quyết định xử lý lỗi

~~~text
MongoDB operation failed
           |
           v
Is it inside a transaction?
       |
   +---+----+
   |        |
  NO       YES
   |        |
   v        v
Check     Which phase?
retryable    |
write     +--+-------+
protocol  |          |
          v          v
        Body       Commit
          |          |
          v          v
    TransientTx?  UnknownCommit?
       |             |
    +--+--+       +--+---+
    |     |       |      |
   YES    NO     YES     NO
    |     |       |      |
    v     v       v      v
   Retry Classify Retry   Classify
   whole business same   failure/
   body  /config  commit reconcile
         issue

Always:
  stable business key
  bounded retry/deadline
  observable outcomes
  persisted correctness checks
~~~

**COMMITTED:** return result, không debit lại.

**ABORTED:** retry toàn transaction nếu transient và request còn hợp lệ.

**UNKNOWN:** retry commit cùng transaction nếu còn context, hoặc reconcile bằng durable business receipt.

### 21.1. Lỗi tạm thời vẫn có thể gây sự cố lớn

~~~text
Without retry: p95 30 ms
With 3 attempts: p95 400 ms
~~~

Retry thành công về mặt kỹ thuật vẫn có thể vi phạm SLO. Retry là recovery mechanism, **không thay thế điều tra root cause**.

## 22. Checklist điều tra và phòng ngừa

### 22.1. Triaging một sự cố

- [ ] Ghi timestamp, time zone, service name, operation, environment.
- [ ] Thu exception class, error code, labels và transaction phase.
- [ ] Phân biệt server-selection error với server command error.
- [ ] Kiểm tra có primary hay đang election.
- [ ] Kiểm tra member hostnames/DNS/TLS/network accessibility.
- [ ] Kiểm tra replica set name và driver connection URI.
- [ ] Kiểm tra majority availability/replication lag.
- [ ] Kiểm tra driver/server versions và supported retry behaviors.
- [ ] Thu error/timeout/p95/p99 và successful QPS ở app layer.
- [ ] Không sửa topology mù quáng trước khi có evidence.

### 22.2. Điều tra WriteConflict

- [ ] Đo conflict rate, total attempts và business successes.
- [ ] Xác định hot documents/keys và top query shapes.
- [ ] Đo transaction p50/p95/p99 duration.
- [ ] Kiểm tra indexes cho reads/updates trong transaction.
- [ ] Kiểm tra long-running transactions và batch jobs.
- [ ] Tách business validation fail khỏi technical conflict.
- [ ] Test concurrent updates có barriers/deadlines.
- [ ] Xác nhận conditional predicates và matchedCount checks.
- [ ] Đặt bounded retries/backoff, không tăng vô hạn.
- [ ] Cân nhắc schema/partition/queue nếu conflicts kéo dài.

### 22.3. Điều tra transaction retry

- [ ] Phân biệt TransientTransactionError với UnknownTransactionCommitResult.
- [ ] Body transient được retry trong một attempt mới.
- [ ] Commit unknown được retry cùng transaction khi còn context.
- [ ] Callback không gọi external side effects.
- [ ] Request ID được giữ ổn định giữa attempts và HTTP retries.
- [ ] Unique receipt key có cơ chế compare parameters.
- [ ] Xử lý concurrent same-key race.
- [ ] Có outcome UNKNOWN/pending khi hết deadline.
- [ ] Có reconciliation worker/status endpoint.
- [ ] Không chuyển unknown trực tiếp thành definitely aborted.

### 22.4. Spring Data

- [ ] MongoTransactionManager được đăng ký đúng.
- [ ] @Transactional chỉ định đúng manager khi có nhiều managers.
- [ ] Invocation đi qua Spring proxy, không self-invocation.
- [ ] Exception propagation/rollbackFor rules rõ.
- [ ] MongoTemplate/Repository dùng đúng session-bound operations.
- [ ] Không tạo raw MongoClient khác trong transaction rồi tưởng cùng scope.
- [ ] Outer retries tạo transaction attempt mới khi phù hợp.
- [ ] Không blindly retry toàn @Transactional method sau unknown commit.
- [ ] Reactive code không tự subscribe lại side-effect pipeline ngoài ý muốn.

### 22.5. Test và vận hành

- [ ] Có test commit/abort trên replica set thật.
- [ ] Có test WriteConflict và duplicate race.
- [ ] Có test failover trên multi-node lab khi cần.
- [ ] Fault injection không chạy trên production.
- [ ] Failpoints/proxy faults được cleanup.
- [ ] Readback persisted state theo read consistency đã xác định.
- [ ] Không assert recovery bằng sleep cố định.
- [ ] Logs redacted, metrics cardinality thấp.
- [ ] Alert theo tỷ lệ lỗi + SLO impact + reconciliation backlog.
- [ ] Có runbook và người sở hữu pending outcomes.

## 23. Bài thực hành

Các bài thực hành dùng replica set lab riêng. Khi không có môi trường ba members, có thể làm phần mô hình/test design thay vì tự gây primary stepdown.

### Bài 1 — Phân loại ba lỗi

Cho:

~~~text
NotWritablePrimary (10107)
WriteConflict (112)
UnknownTransactionCommitResult
~~~

Hãy mô tả nguồn gốc, retry scope và dữ liệu cần kiểm tra của từng trường hợp.

### Bài 2 — Vòng đời election

Vẽ timeline P1 primary → P1 stepdown → no-primary window → P2 primary → driver discovers P2. Tại sao một request có thể thất bại ở khoảng chuyển tiếp?

### Bài 3 — Direct connection

Một application URI chỉ trỏ một secondary với directConnection=true. Vì sao retry cùng URI không sửa được NotWritablePrimary?

### Bài 4 — Replica set URI

Viết URI với ba seed hosts và replicaSet=rsApp; nêu các điều kiện DNS/TLS/ports cần đúng.

### Bài 5 — Server selection timeout

Mô tả trường hợp driver không tìm thấy writable primary trước khi command được gửi. Vì sao đây khác một mongod trả NotWritablePrimary?

### Bài 6 — hello

Viết read-only mongosh command lấy isWritablePrimary, setName, secondary và primary. Vì sao dữ liệu đó chỉ là snapshot?

### Bài 7 — rs.status

Trên lab replica set, dùng rs.status() để xác định member states. Những dấu hiệu nào cho biết cluster chưa có writable primary?

### Bài 8 — NotPrimaryNoSecondaryOk

Giải thích vì sao lỗi liên quan read eligibility không nhất thiết cùng nguyên nhân với NotWritablePrimary trên write path.

### Bài 9 — WriteConflict cùng document

Tạo hai sessions, mỗi session transaction cập nhật cùng Account A. Phác thảo test harness đồng bộ bằng barrier, ghi nhận exception label và final persisted balance.

### Bài 10 — Business conflict

Account A có 100 units, request muốn trừ 150. Viết conditional update với balance >= amount. matchedCount=0 phải được xử lý thế nào?

### Bài 11 — Hot counter

1.000 concurrent checkout requests đều update document _id=all-orders. Vì sao có thể tăng contention? So hai phương án: một atomic counter và distributed counter/event aggregation.

### Bài 12 — Long transaction

Một callback scan 1 triệu documents, gọi REST service rồi update inventory. Liệt kê bốn nguyên nhân tăng conflicts và cách rút ngắn.

### Bài 13 — Thêm index

Transaction update order theo tenantId, status, createdAt. Nếu query quét 500.000 documents, chỉ ra cách dùng explain/index design để giảm thời gian transaction.

### Bài 14 — Optimistic version

Viết updateOne dùng version=7, $set price và $inc version. Khi matchedCount=0 có được retry không điều kiện mà không reread không?

### Bài 15 — Error label

Trong Java, viết code kiểm tra exception.hasErrorLabel("TransientTransactionError"). Khi label xuất hiện trong body, thao tác retry đúng là gì?

### Bài 16 — Unknown commit label

Viết code phân loại UnknownTransactionCommitResult. Vì sao lặp lại body ngay có thể double debit?

### Bài 17 — Hai vòng retry

Vẽ OUTER loop cho body và INNER loop cho commit. Chỉ rõ mỗi loop được kích hoạt bởi error label nào.

### Bài 18 — RetryWrites

Phân biệt retryWrites=true cho command được hỗ trợ với một custom while loop phát độc lập cùng $inc.

### Bài 19 — Timeout không chứng minh thất bại

Một insert/update gửi thành công tới server nhưng response bị mất. Những thông tin nào cần biết trước khi gửi lại một business request?

### Bài 20 — Write concern timeout

Replica set majority không trả acknowledgment trong timeout. Có thể kết luận document chưa từng được primary áp dụng không? Vì sao?

### Bài 21 — Java withTransaction

Viết Java Sync Driver code mở ClientSession, dùng withTransaction, ReadConcern.SNAPSHOT, WriteConcern.MAJORITY và readPreference primary.

### Bài 22 — Missing session argument

Trong transaction body, một updateOne không nhận ClientSession. Khi abort, điều gì có thể xảy ra? Thiết kế negative integration test riêng.

### Bài 23 — Duplicate business key

Hai transfers có cùng requestId nhưng khác amount. Server nên trả existing result hay conflict? Giải thích.

### Bài 24 — Same request resend

Transfer T1 đã commit, HTTP response bị mất. Client gửi lại cùng idempotency key. Hãy xác định kết quả database và response đúng.

### Bài 25 — Concurrent same-key race

Hai clients cùng requestId bắt đầu đồng thời, đều chưa thấy receipt. Unique _id và transaction giúp điều gì? Application còn cần reconcile bước nào?

### Bài 26 — Callback side effect

Vì sao gửi Kafka event bên trong withTransaction callback có nguy cơ duplicate/out-of-sync? Đề xuất transactional outbox.

### Bài 27 — Event dedup

Outbox dispatcher publish thành công rồi crash trước khi mark SENT. Consumer có thể nhận event bao nhiêu lần? Thiết kế dedup bằng eventId.

### Bài 28 — Spring transaction manager

Viết @Bean MongoTransactionManager và @Transactional service. Nêu điều kiện để Spring proxy áp dụng transaction.

### Bài 29 — Self-invocation

Một method gọi this.reserve() trên cùng bean; reserve() có @Transactional. Vì sao có thể không mở transaction?

### Bài 30 — Swallowed exception

Một @Transactional method catch RuntimeException và return. Vì sao dữ liệu có nguy cơ commit? Sửa cách propagate hoặc rollback marking.

### Bài 31 — Retryable vs permanent Spring exception

Spring wrap MongoDB exception thành DataAccessException. Làm sao bảo tồn root cause/code/labels mà không retry mọi DataAccessException?

### Bài 32 — Reactive retry

Một reactive transaction pipeline có retry() trên toàn stream. Những side effects nào có thể chạy lại? Vì sao cần context/session đúng?

### Bài 33 — Request deadline

API deadline 2 giây, primary election mất 8 giây. Thiết kế bounded failure/pending status và reconciliation thay vì infinite retry.

### Bài 34 — Retry storm

50 instances, mỗi instance có 200 requests và mỗi request retry 5 lần. Tính số attempts tối đa nếu tất cả chạy; đề xuất backpressure/budget.

### Bài 35 — Three-node failover

Lập lab test có primary stepdown giữa transaction body. Quan sát topology recovery và final data invariants như thế nào?

### Bài 36 — Commit fault injection

Mô tả vì sao failCommand closeConnection trên commit không chắc chắn tái tạo “server đã commit rồi mất response”. Kỳ vọng nào vẫn kiểm tra được?

### Bài 37 — Cleanup failpoint

Viết command mode:"off" cho failCommand và giải thích vì sao phải cleanup ngay sau lab test.

### Bài 38 — Secondary lag

Sau confirmed commit, một secondary đọc trạng thái cũ. Vì sao chưa thể kết luận transaction rollback? Đề xuất read observation phù hợp.

### Bài 39 — Counter rate

Một MongoDB counter tăng từ 3000 lên 3180 trong 60 giây. Tính rate. Điều gì cần làm nếu process restart giữa hai samples?

### Bài 40 — App dashboard

Đề xuất dashboard phân biệt NotWritablePrimary/sec, WriteConflict/sec, body retries, commit retries, p99 latency, successful orders/sec và pending reconciliation.

### Bài 41 — DNS vs database

Chỉ một application chạy trong subnet X không resolve được member hostnames. App khác khỏe. Hướng điều tra nào ưu tiên?

### Bài 42 — Majority durability

Một người đề xuất giảm writeConcern từ majority xuống w:1 để xử lý timeout. Những rủi ro durability/business cần phân tích?

### Bài 43 — Retry vs schema

Transaction liên tục lỗi vì missing required field/invalid BSON. Vì sao không nên gắn infinite retry?

### Bài 44 — Abort vs compensation

Một transfer đã commit nhưng business muốn hoàn tiền. Tại sao abortTransaction không làm được? Đề xuất compensating transaction.

### Bài 45 — Incident review

Một sự cố:

~~~text
NotWritablePrimary spike: 20 seconds
WriteConflict rate: 100/s
HTTP p99: 4 seconds
Unknown commit outcomes: 120
Reconciliation backlog: 80
~~~

Viết thứ tự điều tra và mitigation: replica set health, driver/URI, contention, retry policy, idempotency và reconciliation. Không đề xuất restart đồng loạt hoặc sửa metadata replica set trực tiếp.

## 24. Câu hỏi ôn tập

1. NotWritablePrimary có ý nghĩa gì trong replica set?
2. Vì sao NotWritablePrimary có thể xuất hiện tạm thời khi election?
3. Driver SDAM có nhiệm vụ gì?
4. URI directConnection tới secondary gây khó khăn gì cho writes?
5. Server selection timeout khác MongoDB server trả NotWritablePrimary thế nào?
6. Những yếu tố DNS/network nào có thể khiến driver không tìm được primary?
7. Vì sao tăng serverSelectionTimeoutMS không sửa được replica set mất majority?
8. Việc có một PRIMARY trong rs.status có chứng minh mọi application đã route đúng không?
9. MongoDB WriteConflict code phổ biến là bao nhiêu?
10. Tại sao WriteConflict có thể xảy ra khi hai transactions cùng update document?
11. Transaction dài làm tăng contention/write-conflict risks thế nào?
12. Một hot counter document có thể giới hạn throughput ra sao?
13. Việc thêm shard có tự giải quyết hot document không?
14. Optimistic concurrency bằng version predicate hoạt động thế nào?
15. WriteConflict khác DuplicateKey ở retry semantics nào?
16. WriteConflict khác business predicate matchedCount=0 thế nào?
17. LockTimeout và WriteConflict có nên được gộp thành một exception type không?
18. MongoDB có thể tự retry những loại write conflicts nào ở storage/operation level?
19. Error code, error label và driver exception type khác nhau ra sao?
20. TransientTransactionError thường có ý nghĩa gì?
21. Khi gặp TransientTransactionError trong body, có nên tiếp tục attempt cũ không?
22. Vì sao retry transaction phải thực hiện lại reads và business checks?
23. UnknownTransactionCommitResult có nghĩa chắc chắn commit thất bại không?
24. Khi commit result unknown, nên retry body hay retry commit?
25. Vì sao commit retry phải dùng cùng transaction identity?
26. NoSuchTransaction có phải bằng chứng tuyệt đối để debit lại không?
27. retryWrites=true khác business request retry ở điểm nào?
28. Một ứng dụng tự gửi lại $inc sau timeout có rủi ro gì?
29. Vì sao cần ổn định idempotency key xuyên HTTP requests?
30. Unique index có tự so payload của hai requests cùng key không?
31. Khi cùng key nhưng payload khác, ứng dụng nên xử lý ra sao?
32. Khi concurrent duplicate requests, vì sao một call có thể nhận DuplicateKey dù cùng business request?
33. Một receipt không thấy trên lagging secondary chứng minh điều gì?
34. Vì sao cần ba trạng thái COMMITTED/ABORTED/UNKNOWN?
35. Java ClientSession.withTransaction có thể gọi callback nhiều lần không?
36. Vì sao không gửi email/Kafka event trong transaction callback?
37. Một callback thiếu session argument có hậu quả gì?
38. matchedCount có vai trò gì trong conditional debit?
39. MongoTransactionManager quản lý những giai đoạn nào?
40. Spring @Transactional có tự bảo đảm retry commit đúng như withTransaction không?
41. Vì sao self-invocation có thể khiến Spring @Transactional không hoạt động?
42. Khi nào checked exception cần rollbackFor trong Spring?
43. Spring DataAccount transaction có commit được SQL/Kafka atomically không?
44. Transactional outbox giải quyết vấn đề gì và còn rủi ro nào?
45. Khi nào nên dùng failCommand hoặc rs.stepDown để kiểm thử?
46. Vì sao failCommand closeConnection không chứng minh commit đã xảy ra trước lúc network drop?
47. Những metrics nào giúp phân biệt server health với business idempotency?
48. Retry storm làm một cluster vừa failover khó phục hồi hơn thế nào?
49. Vì sao phải đo p95/p99 và successful throughput bên cạnh lỗi retry?
50. Một runbook tốt cần những evidence và giới hạn an toàn nào trước khi thay đổi production?

## 25. Tổng kết và nguyên tắc xử lý an toàn

### 25.1. Cùng một sự cố có thể tạo nhiều loại exception

~~~text
Primary election
     |
     +--> Old primary rejects writes
     |       -> NotWritablePrimary
     |
     +--> Driver cannot find writable server
     |       -> Server selection timeout
     |
     +--> In-flight transaction interrupted
     |       -> TransientTransactionError on eligible errors
     |
     +--> Commit response lost
     |       -> UnknownTransactionCommitResult when labeled
     |
     +--> Applications aggressively retry
             -> Increased contention / WriteConflict
~~~

Đây là **một chuỗi nguyên nhân có thể xảy ra**, không phải thứ tự mặc định cho mọi election. Điều tra bằng timestamps, topology changes, error labels và metrics thực tế.

### 25.2. Bốn hướng xử lý chính

| Vấn đề | Hướng xử lý |
|---|---|
| **NotWritablePrimary** | Kiểm tra election/replica set health/URI/SDAM; driver chọn primary mới, retries có giới hạn. |
| **WriteConflict** | Retry whole transaction khi label cho phép; giảm hot documents, transaction duration và concurrency contention. |
| **TransientTransactionError** | Thực thi lại toàn transaction trên attempt mới; reread và revalidate điều kiện nghiệp vụ. |
| **UnknownTransactionCommitResult** | Retry same commit khi còn session/protocol cho phép; nếu không, durable receipt lookup/reconciliation. |

### 25.3. Bảo vệ ứng dụng khỏi double business effect

~~~text
Every business request:
  stable idempotency key
  immutable request payload
  unique database constraint
  transaction boundaries
  correct retry semantics
  persistent outcome record
  bounded reconciliation
~~~

Chỉ có retry tự động của driver là **chưa đủ** cho business-level resend từ HTTP gateway, queue hoặc user.

### 25.4. Năm câu hỏi trước khi retry

1. **Command đã gửi tới server hay chưa?**
2. **Đây là single write, body của transaction hay commit?**
3. **Error code, label và driver exception nói gì?**
4. **Kết quả là definitely failed/aborted, confirmed committed hay unknown?**
5. **Nếu phải chạy lại, business idempotency bảo vệ ra sao?**

Không trả lời được các câu này thì **đừng viết infinite retry loop**.

### 25.5. Một quy trình điều tra ngắn

~~~text
Capture symptoms and time window
      |
      v
Identify operation phase and error labels
      |
      v
Check replica set topology and application URI
      |
      v
Check write conflicts/transaction duration/pool/network
      |
      v
Choose retry/reconciliation by protocol
      |
      v
Validate persisted business invariants
      |
      v
Improve alerts, budgets, idempotency and root-cause fix
~~~

### 25.6. Tài liệu chính thức

- [MongoDB Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/) — election và primary failover.
- [MongoDB Replication](https://www.mongodb.com/docs/manual/replication/) — kiến trúc replica set, primary/secondary.
- [MongoDB Error Codes](https://www.mongodb.com/docs/manual/reference/error-codes/) — tên/mã lỗi server.
- [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — điều kiện và semantics của retryable writes.
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document atomicity.
- [MongoDB Transactions in Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/) — transaction APIs/retry guidance.
- [MongoDB Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — resource limits và vận hành.
- [MongoDB Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — consistency của reads.
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — acknowledgment và durability.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — MongoClient, error handling và server discovery.
- [MongoDB Java Sync Driver Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — ClientSession.withTransaction, commit/abort.
- [Spring Data MongoDB Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — MongoTransactionManager và transactional workflows.
- [Spring Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — @Transactional/proxy/rollback.
- [MongoDB hello Command](https://www.mongodb.com/docs/manual/reference/command/hello/) — thông tin member/topology.
- [MongoDB replSetGetStatus Command](https://www.mongodb.com/docs/manual/reference/command/replSetGetStatus/) — replica set status.
- [MongoDB serverStatus Command](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — node/transaction statistics.
- [MongoDB configureFailPoint Command](https://www.mongodb.com/docs/manual/reference/command/configureFailPoint/) — fault injection trong môi trường được hỗ trợ.

**Lưu ý phiên bản:** Error codes/labels, automatic retry policies, transaction limitations, driver behavior và Spring Data integration có thể thay đổi theo MongoDB server/driver/framework versions. Trước khi dùng trong production, đối chiếu tài liệu đúng phiên bản và thử trên môi trường phù hợp. Những ví dụ fault injection ở đây chỉ dành cho lab được cấp quyền.

**Kết luận:** Not primary, write conflict và lỗi tạm thời của giao dịch không chỉ là những exception cần catch. Chúng là tín hiệu về **topology, concurrency và transaction outcome**. Muốn xử lý an toàn, hãy xác định đúng giai đoạn lỗi, để driver quản lý topology/retry protocol khi thích hợp, giới hạn retry để không gây bão tải, duy trì idempotency ở business boundary và xác minh trạng thái đã commit trước khi báo kết quả hoặc thực thi bù. Hệ thống có khả năng phục hồi tốt không chỉ ít lỗi hơn, mà còn **không tạo tác động nghiệp vụ trùng hoặc sai khi lỗi xảy ra**.










