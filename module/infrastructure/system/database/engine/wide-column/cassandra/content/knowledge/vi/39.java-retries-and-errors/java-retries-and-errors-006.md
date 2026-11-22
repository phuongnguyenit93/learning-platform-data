# Default retry policy, điều kiện kích hoạt và các lỗi được xử lý riêng trong Cassandra Java Driver

> **Chương:** Retry và lỗi Java  
> **Đối tượng:** Lập trình viên Java và người vận hành Apache Cassandra muốn phân biệt lỗi server, lỗi mạng, timeout phía driver, phản hồi `UNAVAILABLE` và cơ chế thử lại. Nội dung tập trung Java Driver **4.x** (đặc biệt 4.17/4.18), sử dụng CQL/Java 17 và một số ví dụ lab. Các API callback hậu tố `Verdict` áp dụng từ driver **4.10**; bản cũ hơn có API khác. Mọi cấu hình/giả lập sự cố trong bài chỉ thực hiện trên **cluster lab hoặc staging được phê duyệt**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò của `DefaultRetryPolicy` trong chu trình `CqlSession.execute` và sự khác nhau giữa **một logical request** với nhiều **node attempts/messages**.
2. Nêu chính xác phản ứng mặc định trước `UNAVAILABLE`, `READ_TIMEOUT`, `WRITE_TIMEOUT`, mất kết nối trước response và các lỗi server khác.
3. Phân biệt các nhánh **không cần dấu idempotent** với các nhánh **chỉ thử lại khi statement idempotent**, tránh khẩu quyết sai “mọi retry đều yêu cầu idempotence=true”.
4. Hiểu `BATCH_LOG` trong `WriteTimeoutException`, tách nó khỏi `BATCH`, `UNLOGGED_BATCH`, `SIMPLE` và tính nguyên tử của batch.
5. Nhận biết các trường hợp driver **tự xử lý ngoài RetryPolicy**: chưa gửi network write, `UNPREPARED` cần reprepare, node bootstrapping.
6. Nêu các lỗi **không retry**: query validation, function failure, protocol error và các lỗi nghiệp vụ không thể giải quyết bằng cách gửi lại.
7. Phân biệt **server-side timeout** với **DriverTimeoutException**, Java deadline, cancellation, network ambiguity và unknown write outcome.
8. Dùng `basic.request.default-idempotence`, `Statement.setIdempotent`, `advanced.retry-policy.class`, execution profiles và driver metrics một cách có kiểm soát.
9. Viết Java xử lý exception đúng lớp, trả lỗi cho application hợp lý, áp dụng **bounded application retry/backoff** chỉ sau khi đánh giá idempotency và deadline.
10. Thực hiện lab CQL/Java quan sát thành công, validation error và lược đồ quyết định retry mô phỏng **không cần phá cluster**.

**Bối cảnh của `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`:** Cassandra là cơ sở dữ liệu wide-column phân tán; partition key xác định token/natural replicas, replication factor (RF) và consistency level (CL) xác định điều kiện read/write. Java Driver có retry để đối phó một số lỗi tạm thời, **không** tự sửa schema, partition hotspot, replication thiếu, compaction backlog hoặc lỗi thiết kế nghiệp vụ. Retry hợp lý phải tôn trọng **tính đúng dữ liệu** lẫn SLO.

## 2. Retry nằm ở đâu trong đường đi của request?

~~~text
Ứng dụng Java
    |
    |  session.execute(statement)
    v
    Logical CQL request  + deadline + profile + idempotence
    |
    v
Load balancing: query plan [node A, node B, node C, ...]
    |
    +--> Attempt #1: coordinator A
    |         |
    |         +-- Thành công -> ResultSet / ACK
    |         |
    |         +-- Lỗi có phản hồi từ A
    |         |       -> RetryPolicy nhận loại lỗi phù hợp
    |         |          -> retry SAME / retry NEXT / RETHROW / IGNORE
    |         |
    |         +-- Lỗi trước khi network write được thử
    |         |       -> driver tự chuyển tới next node
    |         |
    |         +-- UNPREPARED
    |                 -> driver tự reprepare và gửi lại
    |
    +--> Attempt #2 (chỉ nếu đủ điều kiện, còn deadline)
    |         |
    |         +--> node A hoặc node B
    |
    v
Ứng dụng thấy cuối cùng: success, server error hoặc client timeout
~~~

Một **request** trong metrics của session có thể tạo **nhiều messages/attempts** tới nodes vì retry hoặc speculative execution. Điều này ảnh hưởng latency, CPU, network và Cassandra coordinator. Không được đọc tỉ lệ “application success” tăng mà bỏ qua số attempts và áp lực lên cluster.

### 2.1. Ba tầng lỗi phải tách riêng

| Tầng | Ví dụ | Ai quyết định thử lại? |
|---|---|---|
| **Ứng dụng** | Input sai, status transition không hợp lệ, quota/tenant authorization | Code nghiệp vụ; thường **không retry** |
| **Driver transport/request** | Không mượn được connection, connection reset, query deadline | Một số nhánh hard-coded; RetryPolicy trong những nhánh đủ điều kiện; app có thể quyết định tiếp |
| **Coordinator/replicas** | `UNAVAILABLE`, `READ_TIMEOUT`, `WRITE_TIMEOUT`, `READ_FAILURE`, `OVERLOADED` | Coordinator trả server error; driver policy áp dụng theo loại; app nhận exception nếu rethrow |

**Quan trọng:** Một lỗi `WriteTimeoutException` chứng minh **CL write chưa được xác nhận đủ**, **không** chứng minh rằng mutation chưa chạm replica nào. Gửi lại có thể nhân đôi side effect nếu thao tác không idempotent.

### 2.2. Bốn quyết định của retry policy

| Verdict | Ý nghĩa | Rủi ro nếu dùng sai |
|---|---|---|
| `RETRY_SAME` | Gửi lại qua **cùng coordinator** | Lặp lại tải lên node đang chậm |
| `RETRY_NEXT` | Gửi qua node tiếp theo trong query plan | Có thể tăng áp lực nhiều coordinators; không bảo đảm còn node |
| `RETHROW` | Đưa lỗi tới code gọi/failed future | Ứng dụng cần phân loại, trả lỗi và có thể reconcile |
| `IGNORE` | Coi lỗi như thành công, trả empty result | **Che mất consistency guarantee/unknown outcome** |

`DefaultRetryPolicy` chủ yếu dùng `RETRY_SAME`, `RETRY_NEXT` và `RETHROW` trong những trường hợp cụ thể. **Đừng chọn `IGNORE` trong custom policy để “khỏi thấy lỗi”**: một empty result không chứng minh dữ liệu đã được ghi hoặc đọc đủ.

## 3. Cấu hình mặc định của Java Driver 4.x

Java Driver 4.x chọn `DefaultRetryPolicy` mặc định, không cần thay config để bật:

~~~hocon
datastax-java-driver {
  advanced.retry-policy {
    class = DefaultRetryPolicy
  }

  basic.request {
    timeout = 2 seconds
    default-idempotence = false
  }
}
~~~

Đây là **khung minh họa**: timeout cụ thể phải đọc trong effective config của phiên bản/ứng dụng, không lấy `2 seconds` làm ngưỡng production. Quan trọng hơn, `basic.request.default-idempotence=false` là default của driver 4.17, khiến nhiều callback retry dành cho lỗi **có thể đã thực thi mutation** bị chặn đối với statement chưa đánh dấu an toàn. Xem [Java Driver 4.18 — Retries](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/) và [Idempotence](https://apache.github.io/cassandra-java-driver/4.18.1/core/idempotence/).

### 3.1. Retry policy không phải reconnection policy

- **Retry policy** quyết định hành vi của một CQL request lỗi khi gửi tới coordinator.
- **Reconnection policy** quyết định cách driver thử mở lại connection đến node bị ngắt theo thời gian.
- **Load balancing policy** tạo query plan và chọn coordinator.
- **Speculative execution policy** có thể gửi request **song song** sang node khác vì chậm, không cần chờ lỗi; chỉ cho request có idempotence phù hợp.
- **Application retry/backoff** là một lần thực thi logic mới từ application, có thể xảy ra *sau khi* driver đã retry; phải tính budget tổng.

Một số nhóm lỗi được xử lý **hard-coded trước chính sách**, và một request retry ở driver có thể mang lại success mà ứng dụng không thấy exception. Đừng tự viết vòng lặp retry bên ngoài chỉ vì thấy request thỉnh thoảng chậm.

### 3.2. `retryCount` không phải số lần application gọi API

Trong callback `onXxxVerdict(..., retryCount)`, `retryCount=0` là lần policy xem xét đầu tiên đối với request; nó đếm những lần retry policy đã được gọi trước đó, không phải index của source event, số attempts toàn hệ thống hay số lần application đã re-invoke `session.execute`. `DefaultRetryPolicy` thường tối đa **một retry do policy** trên một logical request trong các nhánh được hỗ trợ.

**Không suy** rằng mọi request có tối đa hai network messages: các đường hard-coded reprepare/unsent, speculative executions và **outer application retries** có thể tạo thêm hoạt động. Deadline và query plan còn có thể chặn retry trước khi thực hiện.

## 4. Ma trận hành vi của DefaultRetryPolicy

| Loại lỗi / callback | Điều kiện chính | Quyết định mặc định | Có yêu cầu statement idempotent? |
|---|---|---|---|
| `UNAVAILABLE` / `onUnavailableVerdict` | First policy decision, coordinator báo thiếu live replicas | **RETRY_NEXT tối đa một lần**; sau đó RETHROW | **Không bắt buộc** cho callback này |
| `READ_TIMEOUT` / `onReadTimeoutVerdict` | First decision, `received >= blockFor`, **`dataPresent=false`** | **RETRY_SAME một lần**; ngoài điều kiện RETHROW | **Không bắt buộc** cho callback này |
| `WRITE_TIMEOUT` / `onWriteTimeoutVerdict` | First decision, `writeType=BATCH_LOG` | **RETRY_SAME một lần**; các write types khác RETHROW | **Có**, mới vào callback |
| Request aborted / `onRequestAbortedVerdict` | `ClosedConnectionException` hoặc `HeartbeatException` | **RETRY_NEXT** nếu kết nối bị đóng; lỗi decode bất thường thì RETHROW | **Có** |
| Other server error / `onErrorResponseVerdict` | `OverloadedException`, `ServerError`... | **RETRY_NEXT** cho loại mặc định coi thử node khác có ích; `ReadFailure`/`WriteFailure` RETHROW | **Có** |
| `QueryValidationException` và subclasses | CQL/schema/authorization/syntax sai | **RETHROW ngay**, ngoài policy | Không liên quan |
| `FunctionFailureException`, `ProtocolError` | Lỗi function/protocol | **RETHROW ngay**, ngoài policy | Không liên quan |
| Lỗi **chưa hề gửi request** | Pool/node hỏng trước network write | Driver tự thử node tiếp theo | Không cần policy/idempotence |
| `UNPREPARED` | Coordinator chưa biết prepared statement ID | Driver tự **reprepare và retry SAME** | Cơ chế riêng |
| Gửi tới node bootstrapping | Node chưa xử lý CQL request | Driver tự thử node tiếp theo | Cơ chế riêng |
| `DriverTimeoutException` | Deadline phía driver hết, không nhận final response trong hạn | **Không** phải callback `onReadTimeout/WriteTimeout` | Ứng dụng xử lý deadline/unknown outcome |

**Hai ngoại lệ idempotence quan trọng:** `onUnavailableVerdict` và `onReadTimeoutVerdict` là các nhánh không cần `isIdempotent=true` vì chúng mô tả tình huống chưa thực thi mutation thành công theo phản hồi tương ứng; các nhánh write timeout/aborted/other error thì cần. Phân biệt **policy callback** với việc code bên ngoài có thể tự retry sau exception. Xem tài liệu [DataStax — Retry policies](https://docs.datastax.com/en/astra-db-classic/drivers/retry-policies.html) và [Apache Java Driver — Retries](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/).

### 4.1. Không có “retry vô hạn vì vẫn còn node”

Ngay cả với RF=3 và query plan có nhiều nodes, `DefaultRetryPolicy` không bắt đầu vòng lặp bất tận qua mọi coordinator. Nó có **quy tắc giới hạn** và request timeout. Nếu ứng dụng bị lỗi lặp, phải đo node/replica availability, CL, timeout và request attempts thay vì thay policy thành vô hạn.

### 4.2. Retry không mặc định hạ consistency

`DefaultRetryPolicy` giữ **consistency level của request** khi thử lại. Nếu ban đầu `LOCAL_QUORUM` mà cluster không còn đủ replica, thử node khác chỉ giúp khi coordinator đầu có góc nhìn topology sai hoặc network-isolated; nó không tự hạ xuống `ONE`. Thay đổi CL là thay đổi **hợp đồng dữ liệu**, không phải phép chữa tạm an toàn trong mọi nghiệp vụ.

## 5. `UNAVAILABLE` — coordinator thấy không đủ replica

### 5.1. Tại sao phát sinh?

Coordinator đã nhận yêu cầu với CL cụ thể, nhưng tại thời điểm đánh giá nó **biết** không có đủ replicas đang sống để đáp ứng:

~~~text
Keyspace NetworkTopologyStrategy: dc1 RF=3
Read CL: LOCAL_QUORUM       => cần 2 full replicas ở dc1

  Replica A: UP          Replica B: DOWN     Replica C: DOWN
         \                      |                   /
          \------------------- coordinator ----------/
                             |
                     known live replicas=1
                     required responses=2
                             |
                      UNAVAILABLE
~~~

Khác `READ_TIMEOUT`: trong `UNAVAILABLE`, coordinator nhận ra **trước khi tiến hành** rằng không thể đạt CL với góc nhìn liveness hiện tại; với `READ_TIMEOUT`, ban đầu nó tưởng đủ replica nhưng các phản hồi không kịp.

### 5.2. Hành vi DefaultRetryPolicy

Theo [Apache Java Driver retries](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/):

- Nếu đây là callback retry đầu (`retryCount=0`), driver **thử node tiếp theo trong query plan** một lần.
- Lý do: coordinator A có thể bị **network partition/isolation** nên tưởng các replicas còn lại đều chết, trong khi coordinator B có góc nhìn tốt hơn.
- Nếu lần thử lại vẫn lỗi hoặc giới hạn đã dùng, policy **rethrow**. Nếu query plan không còn node hoặc deadline hết, request cũng thất bại.
- Callback này **không yêu cầu** statement phải `idempotent=true`; đây là khác biệt với write timeout/mất kết nối sau gửi.
- **Không hạ CL** khi thử lại.

### 5.3. Thông tin trong exception

~~~java
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;

try {
    session.execute(request);
} catch (UnavailableException ex) {
    System.err.printf(
        "UNAVAILABLE coordinator=%s cl=%s required=%d alive=%d%n",
        ex.getCoordinator(),
        ex.getConsistencyLevel(),
        ex.getRequired(),
        ex.getAlive());
    throw ex;
}
~~~

Code minh họa **khi exception tới trực tiếp ứng dụng**. Nếu driver đã thử nhiều coordinators, ứng dụng có thể nhận `AllNodesFailedException` bao các lỗi theo node; cần kiểm nguyên nhân bên trong. Không log raw bind values, credentials hoặc tenant IDs để debug.

### 5.4. Điều **không** làm

- Không tự động đổi `LOCAL_QUORUM` thành `ONE` chỉ để request “thành công”.
- Không gọi `session.execute` thêm 10 lần tức thời khi replicas vẫn DOWN.
- Không tăng `basic.request.timeout` để chữa thiếu replica rõ ràng.
- Không nhận định “node UP” trong một client đủ để chứng minh đủ **natural replicas** cho mọi token range.

**Hướng xử lý:** Kiểm `nodetool status`, RF/DC theo keyspace, network giữa nodes, gossip/liveness, node bootstrap/replace/repair và token ownership. Nếu nghiệp vụ có failover DC được thiết kế, chuyển traffic theo **runbook chủ động**, không giấu trong retry policy.

## 6. `READ_TIMEOUT` — đủ phản hồi nhưng thiếu data, hoặc không đủ phản hồi

### 6.1. Các biến của callback

~~~text
onReadTimeoutVerdict(
  request,
  cl,
  blockFor,
  received,
  dataPresent,
  retryCount
)
~~~

| Tham số | Ý nghĩa |
|---|---|
| `cl` | CL ban đầu như `LOCAL_QUORUM` |
| `blockFor` | Số replica responses cần để đáp ứng CL |
| `received` | Số replica responses đã về |
| `dataPresent` | Có **dữ liệu thực** trong các responses đã nhận hay chỉ digest/checksum |
| `retryCount` | Số lần policy được gọi trước callback này |

Cassandra tối ưu đọc bằng cách yêu cầu **full data** từ một số replica, còn các replica khác có thể chỉ trả **digest** để hòa giải. Bởi vậy, có tình huống `received >= blockFor` nhưng **không có full data response**. Tức đã đủ số lượng phản hồi để thỏa quorum trên giấy, nhưng chưa đủ dữ liệu để trả Row.

### 6.2. Decision tree của DefaultRetryPolicy

~~~text
READ_TIMEOUT từ coordinator
           |
   retryCount đã > 0? --- CÓ ---> RETHROW
           |
          KHÔNG
           |
   received >= blockFor?
         /      \
       KHÔNG     CÓ
        |        |
     RETHROW   dataPresent?
                  /       \
                 CÓ       KHÔNG
                 |           |
              RETHROW    RETRY_SAME
                           (một lần)
~~~

**Vì sao cùng coordinator?** Thường coordinator đã chọn replica không phản hồi cho data retrieval; tới lần sau gossip có thể đã nhận ra node lỗi và chọn replica khác có data. Thử coordinator khác không cần thiết nếu chính coordinator hiện tại đã đủ góc nhìn để sửa lựa chọn đó.

### 6.3. Bốn ví dụ để tự kiểm

| `blockFor` | `received` | `dataPresent` | `retryCount` | Default verdict |
|---:|---:|---|---:|---|
| 2 | 2 | false | 0 | **RETRY_SAME** |
| 2 | 1 | false | 0 | **RETHROW** |
| 2 | 2 | true | 0 | **RETHROW** |
| 2 | 2 | false | 1 | **RETHROW** |

Không được viết custom policy kiểu “cứ `READ_TIMEOUT` thì retry” bỏ qua dữ liệu có/không, số replica và retry count. Retry khi storage quá tải có thể kéo dài thời gian nghẽn.

### 6.4. Phân tích exception trong Java

~~~java
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;

try {
    session.execute(statement);
} catch (ReadTimeoutException ex) {
    System.err.printf(
        "READ_TIMEOUT cl=%s received=%d blockFor=%d dataPresent=%s%n",
        ex.getConsistencyLevel(),
        ex.getReceived(),
        ex.getBlockFor(),
        ex.wasDataPresent());
    throw ex;
}
~~~

`ReadTimeoutException` là **server-side timeout**. `DriverTimeoutException` là **client-side request deadline**, không có `getReceived()/wasDataPresent()` như exception này. Khi driver đã thử nhiều nodes, lỗi có thể được bọc trong `AllNodesFailedException`.

### 6.5. Tại sao không tự động bỏ CL?

Nếu ứng dụng cần `LOCAL_QUORUM` để đọc dữ liệu đủ mới, custom retry hạ xuống `LOCAL_ONE` có thể trả **stale data** đúng cú pháp, sai nghiệp vụ. Tối ưu nên bắt đầu từ read path: partition size, SSTables-per-read, tombstone scans, disk/GC, repair và replica liveness. CL chỉ đổi khi có quyết định nghiệp vụ được phê duyệt.

## 7. `WRITE_TIMEOUT` — vì sao mặc định chỉ thử lại `BATCH_LOG`

### 7.1. Một write timeout không phải rollback

~~~text
Client -> Coordinator A
              |
          RF=3, CL=QUORUM
         /      |      \
     Replica1 Replica2 Replica3
       ACK      slow      slow
         \       |        /
          \--- server timeout
                     |
             WRITE_TIMEOUT
                     |
Client KHÔNG BIẾT mutation có ở replica 2/3 hay chưa
~~~

Một replica đã ACK có thể lưu mutation. Replica khác có thể hoàn tất **sau** deadline. Nếu client retry thao tác tăng counter hoặc append list, trạng thái cuối có thể khác một lần thực hiện.

### 7.2. `WriteType` và quyết định mặc định

| `WriteType` | Ý nghĩa điển hình | DefaultRetryPolicy với first retry & idempotent |
|---|---|---|
| `SIMPLE` | Mutation thông thường | **RETHROW** |
| `BATCH` | Pha write của logged batch | **RETHROW** |
| `UNLOGGED_BATCH` | Unlogged batch | **RETHROW** |
| **`BATCH_LOG`** | Ghi distributed batchlog cho logged batch | **RETRY_SAME một lần** |
| `COUNTER` | Ghi counter | **RETHROW** |
| `CAS`/các loại khác | Conditional mutation/LWT | **RETHROW** |

**Vì sao `BATCH_LOG` đặc biệt?** Đó là lỗi khi coordinator đang cố ghi **batchlog** vào một nhóm node; việc thử lại trên cùng coordinator có cơ hội thành công hơn sau cập nhật liveness. Nó **không** nghĩa là driver có thể retry cả một logged batch đã ghi một phần dữ liệu vô điều kiện.

### 7.3. Điều kiện idempotence

`onWriteTimeoutVerdict` chỉ được gọi đối với request được đánh dấu **idempotent**. Nếu statement không idempotent, driver **không mời policy quyết định** và chuyển lỗi cho client. Đây là lớp bảo vệ ngoài chuyện policy xét `WriteType`.

~~~java
// Giả định "status = PAID" với PK cố định, không sinh TTL/ID mới,
// và nghiệp vụ cho phép replay mutation.
BoundStatement safeUpsert = prepared.bind(
        "tenant-a",
        java.util.UUID.fromString(
            "11111111-1111-1111-1111-111111111111"),
        "PAID")
    .setIdempotent(true);

// Không tự động đặt idempotent cho counter += 1,
// append/prepend list, timestamp/TTL phụ thuộc lúc retry...
~~~

Ngay cả khi statement được đánh dấu idempotent, `DefaultRetryPolicy` vẫn **không retry `SIMPLE` write timeout**. **Idempotent=true chỉ cho phép policy được cân nhắc**, không cam kết sẽ có retry.

### 7.4. Tách `BATCH_LOG`, `BATCH` và `UNLOGGED_BATCH`

~~~text
Logged batch:
  1. Coordinator ghi batchlog            -> lỗi BATCH_LOG
  2. Áp mutations vào natural replicas    -> có thể lỗi BATCH
  3. Dọn batchlog sau thành công

Unlogged batch:
  Không có distributed batchlog,
  nhưng vẫn phải gửi mutations tới replicas.
  Một phần mutations có thể đã áp dụng khi timeout.
~~~

**Không dùng logged batch nhiều partition làm bulk import accelerator**. Nó có coordination/batchlog overhead, không phải transaction SQL toàn cục. Khi cần exactly-once business event, dùng event ID/version/dedup/outbox thích hợp.

### 7.5. Khai thác `WriteTimeoutException`

~~~java
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

try {
    session.execute(writeStatement);
} catch (WriteTimeoutException ex) {
    System.err.printf(
        "WRITE_TIMEOUT cl=%s received=%d blockFor=%d writeType=%s%n",
        ex.getConsistencyLevel(),
        ex.getReceived(),
        ex.getBlockFor(),
        ex.getWriteType());

    // Không tự ghi lại ngay khi outcome chưa chắc chắn.
    // Reconcile theo eventId/version trong hệ thống nghiệp vụ.
    throw ex;
}
~~~

`getWriteType()` mô tả **pha của write** trong Cassandra, không chỉ tên loại CQL statement. Không suy từ tên batch ở source code rằng `WriteType` luôn bằng `BATCH_LOG`.

## 8. `onRequestAbortedVerdict` — bị ngắt kết nối **trước khi có response**

### 8.1. Hai nhóm nguyên nhân

| Nguyên nhân | Ví dụ | DefaultRetryPolicy |
|---|---|---|
| Connection đóng bất ngờ | `ClosedConnectionException` do mất mạng, `HeartbeatException` khi heartbeat lỗi | **RETRY_NEXT**, trong giới hạn policy |
| Phát hiện lỗi bất thường khi decode response | Bug/protocol decoding không hợp lệ | **RETHROW**, không giả định sẽ hết ở coordinator khác |

Callback này chỉ được cân nhắc khi request **idempotent**. Với request **không idempotent**, driver rethrow vì kết nối mất sau khi có thể đã gửi bytes; không ai biết chắc coordinator đã áp mutation hay chưa. Hành động “gửi sang node B” không tương đương bảo đảm node A chưa hoàn tất.

### 8.2. Dòng thời gian mơ hồ

~~~text
Java                   Network                   Coordinator A
 |                        |                            |
 |---- INSERT ------------|--------------------------->|
 |                        |                     xử lý mutation
 |                        X  connection dropped        |
 |<--- không có response -X                            |
 |                                                     |
 |  request idempotent?                                |
 |      YES -> policy có thể RETRY_NEXT                 |
 |      NO  -> rethrow                                 |
 |                                                     |
 |  Coordinator A CÓ THỂ đã ghi thành công              |
~~~

Chỉ ứng dụng biết mutation có side effect nào khác với Cassandra: ví dụ tạo một mã đơn hàng mới mỗi retry, tăng counter, gửi email sau write. **Đặt `setIdempotent(true)` không tự làm những side effect đó an toàn**.

### 8.3. Lỗi transport xảy ra **trước** network write là trường hợp khác

Nếu node được chọn DOWN ngay sau khi lấy từ query plan, pool không có connection hoặc request fail trước khi driver **thử gửi** message, driver biết coordinator **chưa nhận** request. Khi đó nó có thể tự thử node tiếp theo **không đi qua RetryPolicy**, kể cả statement không idempotent. Đây là trường hợp an toàn hơn mất kết nối **sau khi đã gửi bytes**.

Ví dụ:

~~~text
Request created
   |
Pool borrow fails BEFORE network write
   |
Driver knows "not sent"
   |
Try next node transparently
   |
No RetryPolicy.onRequestAbortedVerdict invocation
~~~

Không gộp metric `errors.request.unsent` và `errors.request.aborted` thành một nhóm “network error có thể retry an toàn” vì ý nghĩa outcome khác nhau.

## 9. `onErrorResponseVerdict` — lỗi server khác READ/WRITE_TIMEOUT/UNAVAILABLE

Các server responses được phân vào nhóm này gồm:

- `OverloadedException` — coordinator/server báo quá tải.
- `ServerError` — lỗi phía server.
- `TruncateException` — lỗi trong thao tác TRUNCATE.
- `ReadFailureException` — read bị lỗi replica (khác replica chậm).
- `WriteFailureException` — write bị lỗi replica (khác replica chậm).

### 9.1. Hành vi mặc định theo nhóm

| Nhóm | Default verdict trong nhánh policy hợp lệ | Tại sao? |
|---|---|---|
| `ReadFailureException` | **RETHROW** | Có lỗi phía replica/read path; thử lại ngay ít cơ hội sửa |
| `WriteFailureException` | **RETHROW** | Write side effect có thể đã xảy ra một phần |
| `OverloadedException`, `ServerError` và lỗi server khác thuộc nhóm callback | Thường **RETRY_NEXT** một lần | Coordinator khác có thể hoạt động bình thường |
| `TruncateException` | Thuộc nhóm server errors khác; **không** coi thao tác TRUNCATE là có thể replay từ ứng dụng | Thao tác phá dữ liệu, phải xem version/policy và runbook riêng |

**Nhánh này yêu cầu statement idempotent** để policy được gọi. Nếu statement không idempotent, driver đưa lỗi ra ngoài mà không nhờ policy retry. Không cố ép một `TRUNCATE` hoặc migration DDL thành idempotent để tận dụng retry.

**Phân biệt `ReadFailure`/`WriteFailure` với timeout:** Failure có thể chứa số replica báo lỗi, số phản hồi và reason; timeout thường mô tả phản hồi không về kịp. Hành động root-cause khác nhau: read/write failure có thể liên quan disk/corruption/exception trên node, không đơn thuần tăng timeout.

### 9.2. Overloaded không có nghĩa “hãy retry nhiều hơn”

Khi một node trả `OverloadedException`, thử coordinator tiếp theo một lần có thể thành công. Nhưng nếu nhiều replica dùng chung đĩa/network đã đầy:

~~~text
Request -> A overloaded
             |
           retry B
             |
             +--> B cũng overloaded
                       |
                       v
               Application retry liên tục
                       |
                  RETRY STORM
                       |
               Cluster càng nghẽn
~~~

Giải pháp vận hành là giảm concurrency, áp backpressure, sửa hot partitions, compaction/disk và cân bằng tải. Không tạo loop tức thời trong ứng dụng chỉ vì thấy exception “tạm thời”.

### 9.3. Vì sao `ReadFailureException` không nên ép retry NEXT?

Một replica có thể báo fail do lỗi đọc SSTable, corruption, tombstone/IO, hoặc lỗi trong coordinator. Nếu đổi coordinator liên tục mà cùng **natural replicas** vẫn đang lỗi, bạn chỉ tăng I/O và latency. Hãy kiểm Cassandra server logs, disk, compaction/repair, mismatch schema và token ownership trước khi quyết định nạp lại.

## 10. Các lỗi được driver xử lý riêng, **không** gọi RetryPolicy

### 10.1. Trước khi gửi message: retry vì chắc chắn chưa thực thi

Driver có một số hard-coded transitions an toàn khi biết request chưa gửi:

~~~text
Query plan A -> B -> C
    |
    A pool saturated / node unavailable BEFORE network write
    |
    driver skips to B
    |
    RetryPolicy callback không được gọi
~~~

**Điều kiện cốt lõi là “before a network write was attempted”**, không phải “không có ACK”. Nếu bytes đã gửi mà chưa nhận response, đó là tình huống outcome mơ hồ.

### 10.2. `UNPREPARED`: chuẩn bị lại, rồi gửi lại

Prepared statements được cache trên server theo ID; khi node restart, node mới join hoặc prepared cache bị mất, coordinator có thể trả `UNPREPARED`. Java Driver lưu query text/metadata để:

1. Phát hiện `UNPREPARED` của prepared ID.
2. Gửi `PREPARE` lại tới **cùng coordinator**.
3. Sau khi prepare thành công, gửi lại execute với prepared ID hợp lệ.

Đường này là **cơ chế riêng**, không phải `DefaultRetryPolicy.onErrorResponseVerdict`. Đừng xây “khi UNPREPARED thì prepare lại trong loop ứng dụng” nếu driver đã làm được. Nếu `UNPREPARED` xuất hiện dày đặc, xem node restart/churn, schema agreement, prepared-cache pressure và phiên bản driver.

~~~text
Java -> node B: EXECUTE prepared-id=abc
node B -> Java: UNPREPARED abc
Java -> node B: PREPARE "SELECT ... WHERE pk=?"
node B -> Java: prepared-id=abc
Java -> node B: EXECUTE abc (values)
node B -> Java: ResultSet
~~~

### 10.3. Node bootstrapping

Trong một edge case, nếu contact point chỉ tới node đang bootstrap và nó chưa xử lý CQL request, driver có thể chuyển node tiếp theo. Đây không phải một cách “làm bootstrap nhanh”: cluster topology phải được quan sát và driver policy nên tránh node chưa sẵn sàng.

### 10.4. Những lỗi **luôn rethrow** không nhờ RetryPolicy

| Lớp lỗi | Ví dụ | Hành động |
|---|---|---|
| `QueryValidationException` và subclasses | `InvalidQueryException`, `SyntaxError`, `UnauthorizedException`, `AlreadyExistsException` | Sửa query/schema/authorization, **không retry** |
| `FunctionFailureException` | UDF/function phía server lỗi | Sửa function/data, không retry mù |
| `ProtocolError` | Vấn đề protocol không tương thích/invalid | Kiểm version/network/config, không gửi lặp vô hạn |
| Java bind/codec errors | `IllegalArgumentException`, codec missing, sai marker/Java type | Sửa code/DTO trước khi `execute` |

Không coi lỗi validation là tạm thời ngay cả khi xuất hiện trong lúc rolling schema deployment: cần kiểm DDL, schema agreement và backward compatibility. Retry liên tục cùng một CQL lỗi `Unknown column` không sửa được schema.

### 10.5. `AllNodesFailedException` không phải một server error riêng

Khi driver thử nhiều nodes và chúng đều thất bại, application thường có thể nhận `AllNodesFailedException` chứa **mapping node → errors**. Đây là exception tổng hợp, không nói mọi node cùng lỗi. Có thể có:

~~~text
Node A -> UnavailableException
Node B -> ClosedConnectionException
Node C -> ReadTimeoutException
Application -> AllNodesFailedException
~~~

Muốn phân tích chính xác, phải đọc từng cause trong mapping; không chỉ bắt `AllNodesFailedException` rồi mặc định “toàn cluster chết”. `NoNodeAvailableException` là trường hợp đặc biệt khi **không coordinator nào được thử**, thường do không có node usable/connection phù hợp.

**Lưu ý API:** Cách lấy `getAllErrors()` phụ thuộc driver version, nên dùng Javadoc của 4.x cụ thể; tránh giả lập toàn bộ errors thành một `getCause()` rồi mất node context. [AllNodesFailedException Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/AllNodesFailedException.html).

## 11. Idempotence: cổng an toàn cho những retry có kết quả mơ hồ

### 11.1. Định nghĩa thực dụng

**Idempotent** nghĩa là thực thi cùng thao tác nhiều lần dẫn tới **cùng trạng thái cuối cùng** như thực thi một lần, trong các giả định ứng dụng đã nêu. Ví dụ:

~~~sql
-- Có thể idempotent nếu PK/values và timestamp/TTL policy ổn định:
UPDATE payments_by_id
SET status = 'PAID'
WHERE tenant_id = 'tenant-a'
  AND payment_id = 11111111-1111-1111-1111-111111111111;

-- Không idempotent:
UPDATE counters_by_key
SET processed = processed + 1
WHERE tenant_id = 'tenant-a';
~~~

Một `UPDATE status='PAID'` nhìn như idempotent nhưng nếu ứng dụng có **workflow side effect** như gửi email, phát sự kiện trùng, tạo write timestamp khác hoặc đặt TTL mới, toàn bộ business operation có thể **không idempotent**. Phải kiểm đủ các lớp, không chỉ CQL syntax.

### 11.2. Ma trận những thao tác dễ nhầm

| Thao tác | Đánh giá | Điều kiện |
|---|---|---|
| Point SELECT | Thường idempotent | Không có side effect ứng dụng đi kèm |
| INSERT với PK cố định và cùng values | Có điều kiện | Không thay timestamp/TTL/version logic giữa attempts |
| UPDATE set regular column thành literal cố định | Có điều kiện | Không vi phạm thứ tự event/newer writes |
| DELETE theo PK cố định | Có điều kiện | Tombstone timestamp/retention phải đúng |
| COUNTER UPDATE `x=x+1` | **Không** | Lặp làm tăng nhiều lần |
| LIST append/prepend `list = list + [...]` | **Không** | Lặp làm nhân đôi phần tử |
| INSERT dùng `UUID.randomUUID()` mỗi attempt | **Không** | Tạo nhiều primary keys |
| LWT `IF NOT EXISTS` | Cần quyết định theo nghiệp vụ | `[applied]=false` khi retry có thể nghĩa lần trước đã thành công |
| API ghi payment rồi gửi email | Không tự nhiên idempotent | Cần payment ID + outbox/dedup |

**Bảo vệ tốt hơn flag:** Giữ `event_id`/`payment_id` ổn định, version/sequence từ nguồn, schema đúng và quy tắc duplicate resolution; dùng outbox/idempotency store khi có side effects ngoài Cassandra.

### 11.3. Driver 4.x mặc định `default-idempotence=false`

~~~hocon
datastax-java-driver {
  basic.request.default-idempotence = false
}
~~~

Có thể đánh dấu theo statement:

~~~java
PreparedStatement select = session.prepare(
    "SELECT status FROM retry_lab.orders_by_id " +
    "WHERE tenant_id = ? AND order_id = ?");

BoundStatement safeRead = select.bind(
        "tenant-a",
        java.util.UUID.fromString(
            "11111111-1111-1111-1111-111111111111"))
    .setIdempotent(true);

// Đối với statement khác, không mặc định:
// BoundStatement updateCounter = ... .setIdempotent(true);
~~~

**Không bật true trên toàn bộ service mixed-read/write** nếu chưa audit tất cả statements. Flag chỉ **cung cấp thông tin cho driver** để xét retry/speculation, không phải cơ chế transaction/dedup.

### 11.4. Cổng idempotence theo từng callback

~~~text
onReadTimeoutVerdict / onUnavailableVerdict:
  -> có thể vào callback dù request chưa đánh dấu idempotent.

onWriteTimeoutVerdict:
onRequestAbortedVerdict:
onErrorResponseVerdict:
  -> cần idempotent=true; nếu false -> rethrow trực tiếp.

Hard-coded unsent/reprepare/bootstrap:
  -> không đi qua RetryPolicy; dựa trên bằng chứng chưa thực thi
     hoặc khả năng prepared recovery.
~~~

Đây là chi tiết dễ bị hiểu sai từ tóm tắt “retry policy chỉ chạy với idempotent queries”: **sự an toàn của hai nhánh `READ_TIMEOUT`/`UNAVAILABLE` được đánh giá riêng**. Với application retry, bạn vẫn cần xem **request có phải read-only hay không và outcome ra sao**; đừng biến exception name thành một quy tắc không cần suy nghĩ.

### 11.5. PreparedStatement và BoundStatement

Trong Java Driver 4.x, thuộc tính idempotence của `SimpleStatement` đưa vào lúc prepare có thể được truyền xuống `BoundStatement`, và có thể được override khi bind:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

PreparedStatement p = session.prepare(
    SimpleStatement.builder(
        "SELECT status FROM retry_lab.orders_by_id " +
        "WHERE tenant_id = ? AND order_id = ?")
        .setIdempotence(true)
        .build());

BoundStatement b = p.bind(
    "tenant-a",
    java.util.UUID.fromString(
        "11111111-1111-1111-1111-111111111111"));

System.out.println("idempotent=" + b.isIdempotent());
~~~

Lưu ý setter trên built-in statements **bất biến**, trả object mới. Nếu code gọi `b.setIdempotent(true);` mà không giữ giá trị trả về, `b` cũ vẫn có flag cũ.

## 12. `DriverTimeoutException`: hết deadline của client khác timeout của Cassandra

### 12.1. Hai đồng hồ

~~~text
                  JAVA DRIVER                        CASSANDRA
             request timeout budget             coordinator timeout
           (basic.request.timeout)            (cassandra.yaml ...)
                      |                                |
Client ---- request ---- network ---- coordinator ---- replicas
                      |                                |
             Có thể hết hạn trước          Có thể trả READ/WRITE_TIMEOUT
             khi server trả lỗi            nếu server timeout trước
                      |                                |
             DriverTimeoutException          ReadTimeoutException /
                                             WriteTimeoutException
~~~

**`DriverTimeoutException`** xảy ra khi deadline phía driver hết. Nó **không** phải `ReadTimeoutException`, `WriteTimeoutException`, không có những metadata `received/blockFor` và **không** được xử lý bởi callbacks tương ứng trong `DefaultRetryPolicy`. Xem [DriverTimeoutException Javadoc 4.17](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/DriverTimeoutException.html).

### 12.2. Vì sao timeout client còn nguy hiểm với write?

~~~text
T0: Java gửi INSERT payment_id=P, status=PAID
T1: Coordinator chuyển mutation tới replicas
T2: Client hết 2s, ném DriverTimeoutException
T3: Một số replica xử lý xong, ACK đến muộn
T4: App retry nghiệp vụ -> có thể duplicate side effects
~~~

**Không có bảo đảm rollback tự động ở T2.** Phân loại **UNKNOWN_OUTCOME**; đối chiếu nguồn nghiệp vụ và trạng thái Cassandra theo PK/event ID, không sinh ID mới để “tránh trùng” vì làm trùng nghiệp vụ nặng hơn.

### 12.3. Deadline của một request không phải deadline của cả workflow

Ví dụ API đọc 30 trang Cassandra liên tiếp hoặc chạy 3 statements theo nghiệp vụ:

~~~text
GET /orders/history
  -> page 1: timeout budget 2s
  -> page 2: timeout budget 2s
  -> ...
  -> page 30: timeout budget 2s

Không có nghĩa cả API bị giới hạn tuyệt đối trong 2s.
~~~

Cần có **end-to-end deadline** của request HTTP/job và max pages/rows. Retry ở application phải **nằm trong** deadline còn lại; không đặt 3 lần `session.execute` mỗi lần 5 giây khi API yêu cầu 3 giây.

### 12.4. Đọc config thực từ session

~~~java
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import java.time.Duration;

Duration requestTimeout = session.getContext().getConfig()
    .getDefaultProfile()
    .getDuration(DefaultDriverOption.REQUEST_TIMEOUT);

boolean defaultIdempotent = session.getContext().getConfig()
    .getDefaultProfile()
    .getBoolean(DefaultDriverOption.REQUEST_DEFAULT_IDEMPOTENCE);

System.out.printf("requestTimeout=%s defaultIdempotent=%s%n",
    requestTimeout, defaultIdempotent);
~~~

Đây là **giá trị effective trong default profile**, không nhất thiết là giá trị của mọi request: named/derived execution profile hay explicit `Statement.setTimeout()`/`setIdempotent()` có thể ghi đè. Khi debug retry, luôn ghi **profile đang dùng và statement options**.

## 13. Retry ở application: retry budget, backoff, jitter, circuit breaker

### 13.1. Khi nào cần lớp retry ngoài driver?

`DefaultRetryPolicy` chủ động bảo thủ; đôi khi ứng dụng cần **một lần workflow-level retry** sau khi hệ thống phục hồi. Ví dụ:

- Một readonly GET muốn retry sau vài chục mili-giây **vẫn trong deadline** nếu cluster vừa hồi network.
- Một batch job idempotent muốn checkpoint rồi retry **sau khi** cluster hết overload.
- Một payment service cần reconcile một write timeout trước khi quyết định trả trạng thái `PENDING_RECONCILIATION` cho caller.

Không nên implement:

~~~java
// SAI: vòng lặp vô hạn, retry mọi lỗi, không deadline/backoff.
while (true) {
    try { session.execute(statement); break; }
    catch (Exception ignored) { }
}
~~~

### 13.2. Ngân sách tổng hợp

~~~text
API deadline  = 1.5s
   |
   +-- Attempt 1: Java Driver (có thể có internal retry)
   |
   +-- Check time remaining
   |
   +-- Backoff có jitter (nếu read/idempotent & transient)
   |
   +-- Attempt 2: Java Driver (lại có thể có internal retry)
   |
   +-- Return result OR explicit timeout/failure
~~~

Nếu driver đã làm 1 retry nội bộ ở mỗi lần execute, **2 application attempts có thể thành nhiều hơn 2 network attempts**. Speculative execution còn làm tăng physical attempts. Vì vậy phải budget dựa **physical load và time budget**, không chỉ đếm vòng lặp ngoài.

### 13.3. Exponential backoff có jitter

Mẫu tính thời gian chờ cho retry ngoài driver:

\[
d_n = \min(d_{\max},\, d_0 \cdot 2^n),\qquad
\text{jitter}_n \sim U(0,d_n).
\]

Ví dụ `d0=50ms`, `dmax=400ms`, tối đa 2 application attempts; đây chỉ là **giá trị minh họa**, không phải tối ưu cho mọi SLO. Chỉ chờ nếu còn đủ ngân sách deadline, CL và cluster health. **Không gọi `Thread.sleep` trong callback `RetryPolicy`**: callback chạy trên I/O threads và sẽ chặn xử lý asynchronous của driver. App có thể dùng scheduler/nonblocking delay thích hợp ở tầng ngoài.

### 13.4. Circuit breaker và bulkhead

| Biện pháp | Mục đích | Hạn chế |
|---|---|---|
| Bounded retries | Không khuếch đại errors vô hạn | Cần phân loại lỗi và deadline |
| Exponential backoff + jitter | Giảm đồng bộ đợt retry | Không chữa node thiếu quorum |
| Circuit breaker | Tạm ngừng gọi dependency đang bệnh | Cần half-open probes phù hợp |
| Bulkhead/concurrency limit | Một query family không chiếm hết pool | Cần queue/backpressure và fairness |
| Adaptive rate limit | Giảm tải khi p99/error/GC xấu | Có thể tăng latency đầu vào nếu không thiết kế |
| Idempotency key/outbox | Chống duplicate business effects | Cần source-of-truth và dedup retention |
| Reconciliation | Giải quyết unknown write outcome | Có thể cần audit/event log đáng tin |

Không gán `RetryPolicy` vai trò của toàn bộ resilience architecture. Nó chỉ là **một bước** trong pipeline request Cassandra.

## 14. Cấu hình RetryPolicy và execution profiles bằng HOCON

### 14.1. Một `application.conf` tối thiểu cho lab

~~~hocon
datastax-java-driver {
  basic {
    contact-points = [ "127.0.0.1:9042" ]
    load-balancing-policy.local-datacenter = "datacenter1"
    request {
      timeout = 2 seconds
      consistency = ONE
      default-idempotence = false
      page-size = 500
    }
  }

  advanced.retry-policy.class = DefaultRetryPolicy

  profiles {
    read_only {
      basic.request.timeout = 1 second
      basic.request.consistency = ONE
      basic.request.default-idempotence = true
    }

    critical_write {
      basic.request.timeout = 3 seconds
      basic.request.consistency = ONE
      basic.request.default-idempotence = false
    }
  }
}
~~~

**Chỉ dùng cấu hình CL=ONE/DC=datacenter1 trên lab một node RF=1.** Production nhiều DC phải khai báo contact points, local DC, RF/CL và TLS/auth đúng topology; ví dụ RF3 tại local DC thường cần `LOCAL_QUORUM` khi nghiệp vụ yêu cầu. `read_only` chỉ an toàn với các statements **thực sự read-only**; đặt SELECT/LWT/UPDATE chung profile rồi bật true có thể sai.

### 14.2. Profile chọn chính sách mặc định, statement còn có thể override

~~~java
SimpleStatement read = SimpleStatement.builder(
        "SELECT release_version FROM system.local")
    .setExecutionProfileName("read_only")
    .setIdempotent(true)
    .build();
~~~

Nếu statement chọn `read_only`, nó nhận request timeout 1s và idempotence default=true **nếu không có explicit overrides**. `setIdempotent(false)` trên statement có thể ghi đè profile. Ngược lại, `advanced.retry-policy.class` có thể được định nghĩa riêng trong named profile; policy nào được gọi thuộc **profile thực tế của request**.

### 14.3. Dùng nhiều retry policies

~~~hocon
datastax-java-driver {
  advanced.retry-policy.class = DefaultRetryPolicy

  profiles {
    read_only {
      basic.request.default-idempotence = true
      # Nếu không khai báo advanced.retry-policy,
      # profile kế thừa policy của default.
    }

    operations {
      basic.request.default-idempotence = false
      # Ở đây có thể khai báo class custom đã kiểm thử.
      # advanced.retry-policy.class = my.package.MySafePolicy
    }
  }
}
~~~

Driver tái sử dụng policy instance khi cấu hình giống nhau giữa profiles; không mặc định tạo một policy độc lập cho từng request. Với custom policy có state, phải tính **thread safety**, lifecycle `close()` và việc chia sẻ instance.

### 14.4. Không invent option `max-retries` cho DefaultRetryPolicy

~~~hocon
# KHÔNG mặc định là option được hỗ trợ:
# datastax-java-driver.advanced.retry-policy.max-retries = 10
~~~

`DefaultRetryPolicy` có hành vi và giới hạn theo code built-in, không có một setting chuẩn “retry mọi exception N lần” chỉ bằng HOCON. Để thay logic cần custom `RetryPolicy` được kiểm chứng; với retry có backoff, logic đó thuộc **application scheduler** thay vì block I/O thread của policy.

## 15. Java Driver 4.x: bắt exception và phân loại kết quả đúng

### 15.1. Các exception classes thường gặp

| Class | Package tiêu biểu | Nội dung cần xem |
|---|---|---|
| `DriverTimeoutException` | `com.datastax.oss.driver.api.core` | Deadline client |
| `AllNodesFailedException` | `...api.core` | `getAllErrors(): Map<Node,List<Throwable>>` |
| `NoNodeAvailableException` | `...api.core` | Không coordinator nào có thể thử |
| `ReadTimeoutException` | `...api.core.servererrors` | `received, blockFor, dataPresent, CL` |
| `WriteTimeoutException` | `...api.core.servererrors` | `received, blockFor, writeType, CL` |
| `UnavailableException` | `...api.core.servererrors` | `alive, required, CL` |
| `ReadFailureException` | `...api.core.servererrors` | Số replica failure/reason map |
| `WriteFailureException` | `...api.core.servererrors` | Số replica failure/write type |
| `InvalidQueryException` | `...api.core.servererrors` | Query/schema sai |
| `UnauthorizedException` | `...api.core.servererrors` | Permission sai |
| `RequestThrottlingException` | `...api.core` | Client request throttler từ chối |

Một `AllNodesFailedException` là **wrapper** cho lỗi per-node, không nhất thiết là cùng một subclass với lỗi bên trong. Vì thế code bắt `ReadTimeoutException` ở top-level **không thay thế** kiểm trong `getAllErrors()`.

### 15.2. Java 17 — một helper đọc-only có xử lý lỗi

~~~java
package example;

import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.NoNodeAvailableException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.QueryValidationException;
import java.util.UUID;

public final class SafeOrderRead {
    private final CqlSession session;
    private final PreparedStatement lookup;

    public SafeOrderRead(CqlSession session) {
        this.session = session;
        this.lookup = session.prepare(
            "SELECT status FROM retry_lab.orders_by_id " +
            "WHERE tenant_id = ? AND order_id = ?");
    }

    public String findStatus(String tenantId, UUID orderId) {
        if (tenantId == null || tenantId.isBlank()
                || orderId == null) {
            throw new IllegalArgumentException("Invalid primary key");
        }

        BoundStatement statement = lookup.bind(tenantId, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE)
            .setIdempotent(true);

        try {
            Row row = session.execute(statement).one();
            return row == null ? null : row.getString("status");
        } catch (NoNodeAvailableException e) {
            System.err.println("No coordinator candidate available");
            throw e;
        } catch (AllNodesFailedException e) {
            // Có thể chứa nhiều errors ở mỗi node; không bỏ bối cảnh.
            e.getAllErrors().forEach((node, failures) -> {
                for (Throwable failure : failures) {
                    System.err.printf(
                        "node=%s errorType=%s%n",
                        node.getHostId(),
                        failure.getClass().getSimpleName());
                }
            });
            throw e;
        } catch (DriverTimeoutException e) {
            System.err.println("Client deadline expired");
            throw e;
        } catch (ReadTimeoutException e) {
            System.err.printf(
                "Read timed out: received=%d required=%d dataPresent=%s%n",
                e.getReceived(), e.getBlockFor(),
                e.wasDataPresent());
            throw e;
        } catch (WriteTimeoutException e) {
            // Về nguyên tắc SELECT không phát sinh write timeout;
            // giữ nhánh này chỉ để minh họa phân loại lỗi API.
            System.err.println(
                "Unexpected write timeout: " + e.getWriteType());
            throw e;
        } catch (UnavailableException e) {
            System.err.printf(
                "Unavailable: alive=%d required=%d cl=%s%n",
                e.getAlive(), e.getRequired(),
                e.getConsistencyLevel());
            throw e;
        } catch (QueryValidationException e) {
            System.err.println("Permanent query/permission/schema error");
            throw e;
        }
    }
}
~~~

**Đây là ví dụ học tập về phân loại exception**, không phải bộ retry hoàn chỉnh và không giả định mọi lỗi sẽ xuất hiện top-level. Trong ứng dụng production:

- Đừng bắt rồi gọi lại ngay lập tức trong từng `catch`.
- Đừng log raw CQL bind values/PII.
- Một số errors chỉ nằm trong `AllNodesFailedException.getAllErrors()`, vì vậy cần **phân loại các nested causes**.
- `NoNodeAvailableException` kế thừa `AllNodesFailedException` nên phải catch **trước**.
- Với read-only API có thể trả HTTP 503/504 và Retry-After phù hợp; với mutation kết quả không chắc chắn nên trả trạng thái **PENDING/UNKNOWN** hay cơ chế reconciliation, không khẳng định write thất bại.
- `ONE` được dùng vì lab RF1; production phải đặt CL theo hợp đồng nghiệp vụ.

### 15.3. Trong Java async — exception có thể được bọc

~~~java
import java.util.concurrent.CompletionException;

session.executeAsync(statement).whenComplete((result, error) -> {
    if (error == null) {
        System.out.println("CQL succeeded");
        return;
    }

    Throwable cause = error;
    while (cause instanceof CompletionException
            && cause.getCause() != null) {
        cause = cause.getCause();
    }
    System.err.println("CQL failed: " +
        cause.getClass().getSimpleName());
});
~~~

Trong `CompletionStage`, `join()` thường bọc lỗi trong `CompletionException`; `get()` thường bọc trong `ExecutionException`. Không chỉ kiểm text của `getMessage()` để quyết định retry. Giữ exception type, metrics và node context.

### 15.4. Lấy lỗi per-node từ AllNodesFailedException

~~~java
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.metadata.Node;
import java.util.List;
import java.util.Map;

static void inspect(AllNodesFailedException e) {
    for (Map.Entry<Node, List<Throwable>> entry :
            e.getAllErrors().entrySet()) {
        Node node = entry.getKey();
        for (Throwable failure : entry.getValue()) {
            System.err.printf("node=%s type=%s%n",
                node.getHostId(),
                failure.getClass().getSimpleName());
        }
    }
}
~~~

`getAllErrors()` là API của Driver 4.17. Nó cho nhiều errors mỗi node; không gọi API deprecated `getErrors()` chỉ lấy first error rồi tưởng đã đủ bối cảnh. [Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/AllNodesFailedException.html).

## 16. Custom RetryPolicy: khi nào được cân nhắc và bẫy triển khai

### 16.1. Bản chất interface

Từ driver 4.10 trở đi, callback ưu tiên API hậu tố `Verdict`:

~~~text
onUnavailableVerdict(Request, ConsistencyLevel, required, alive, retryCount)
onReadTimeoutVerdict(Request, ConsistencyLevel, blockFor, received,
                     dataPresent, retryCount)
onWriteTimeoutVerdict(Request, ConsistencyLevel, WriteType,
                      blockFor, received, retryCount)
onRequestAbortedVerdict(Request, Throwable, retryCount)
onErrorResponseVerdict(Request, CoordinatorException, retryCount)
~~~

Các methods cũ không có hậu tố `Verdict` đã bị deprecated từ **4.10**; một custom policy copy từ driver 3.x/4.4 có thể không phù hợp khi nâng cấp. Đọc [RetryPolicy API 4.18](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/retry/RetryPolicy.html) và đúng source/library version.

### 16.2. Quy tắc an toàn của custom policy

- **Không block Netty/I/O thread.** Callback chính sách chạy trên I/O threads; `Thread.sleep`, gọi REST, query DB bổ sung hoặc khóa chờ lâu trong callback có thể làm cả driver chậm.
- **Không giữ state mutable không bảo vệ.** Một policy instance có thể được dùng bởi nhiều requests/threads và nhiều execution profiles có cấu hình giống nhau.
- **Không tự hạ CL** khi nghiệp vụ đòi quorum.
- **Không trả IGNORE** chỉ vì đã nhận ≥1 ACK: điều đó có thể biến write chưa đạt CL thành “success” giả.
- **Không retry lỗi validation/auth**; nhóm đó đã được driver rethrow hard-coded.
- **Không cho retry vô hạn**; bound retryCount, request timeout, query plan và application budget.
- **Không retry write không idempotent** sau khi khả năng đã gửi network bytes.
- **Không sinh exceptions/logs quá lớn cho mỗi request**; giữ metrics theo loại lỗi, tránh PII.

### 16.3. Khi nào cần custom policy thật?

Chỉ khi:

1. Có lỗi/khả năng phục hồi **đã quan sát**, DefaultRetryPolicy không đáp ứng SLO có căn cứ.
2. Có bằng chứng mutations là idempotent theo business, đúng CL/replica semantics.
3. Có load test/failure injection trong staging để đo retries, write amplification, tail latency.
4. Có nguồn code + kiểm thử tương thích driver version, quan sát được quyết định policy.
5. Có rollout canary, rollback và owner hiểu Cassandra coordinator/replica.

Với đa số ứng dụng, **giữ `DefaultRetryPolicy` + bảo vệ idempotence + bounded application backoff** đơn giản và an toàn hơn.

### 16.4. So với `ConsistencyDowngradingRetryPolicy`

Driver có built-in `ConsistencyDowngradingRetryPolicy` nhưng **không khuyến nghị mặc định** cho nghiệp vụ cần consistency:

| Tình huống | Default | Consistency downgrading |
|---|---|---|
| `UNAVAILABLE` CL QUORUM, thiếu 1 replica | Thử coordinator khác **giữ nguyên CL** | Có thể thử CL thấp hơn ở cùng node |
| `READ_TIMEOUT` không đủ responses | RETHROW | Có thể giảm CL nếu đủ dữ liệu theo mức thấp hơn |
| `WRITE_TIMEOUT` có 1 ACK | RETHROW (trừ BATCH_LOG) | Có thể **IGNORE** error trong một số write types |
| Yêu cầu tính nhất quán | Không tự suy yếu | **Có thể suy yếu** và làm stale read/hidden failure |

Ví dụ hazard:

~~~text
Ghi payment ở QUORUM; downgrade write còn ONE;
ứng dụng nhận "success"; replica khác chưa theo kịp.

Đọc sau đó ở QUORUM từ luồng khác
  -> chưa chắc quan sát payment ngay.

Nghiệp vụ cần read-your-writes/quorum invariant bị phá.
~~~

**Không áp `ConsistencyDowngradingRetryPolicy` cho thanh toán, trạng thái giao dịch hoặc các invariants trọng yếu** chỉ để giảm thông báo lỗi. Nếu một use case được phép degrade, định nghĩa rõ mức đảm bảo mới, DC locality, audit và tín hiệu gửi cho client.

## 17. Observability: phân biệt lỗi, retries và speculative executions

### 17.1. Metrics của driver 4.x

Theo reference configuration, một số session/node metrics thường **tắt mặc định** và chỉ có tác dụng nếu registry/reporter được cấu hình đúng. Mẫu:

~~~hocon
datastax-java-driver {
  advanced.metrics {
    session.enabled = [
      connected-nodes,
      cql-requests,
      cql-client-timeouts
    ]

    node.enabled = [
      cql-messages,
      pool.in-flight,
      errors.request.unsent,
      errors.request.aborted,
      errors.request.read-timeouts,
      errors.request.write-timeouts,
      errors.request.unavailables,
      errors.request.others,
      retries.total,
      retries.read-timeout,
      retries.write-timeout,
      retries.unavailable,
      retries.aborted,
      retries.other,
      ignores.total,
      speculative-executions
    ]
  }
}
~~~

Các tên trên là **driver metric option names** trong HOCON. Tên metric **xuất ra** Prometheus/Dropwizard/Micrometer tùy integration; chỉ bật HOCON không tự thiết lập exporter hoặc dashboard. Không bật mọi metric mức cao cardinality trong production mà không kiểm chi phí.

### 17.2. Session vs node-level metrics

| Metric | Cấp | Ý nghĩa chính |
|---|---|---|
| `cql-requests` | Session | Latency/throughput **logical CQL requests** |
| `cql-client-timeouts` | Session | Request hết driver deadline |
| `cql-messages` | Node | Individual requests/messages tới **coordinator**; có thể nhiều hơn logical requests |
| `errors.request.unsent` | Node | Lỗi **trước** khi gửi network write |
| `errors.request.aborted` | Node | Request bị ngắt trước khi có response, có thể outcome unknown |
| `errors.request.read-timeouts` | Node | Server trả READ_TIMEOUT |
| `errors.request.write-timeouts` | Node | Server trả WRITE_TIMEOUT |
| `errors.request.unavailables` | Node | Server trả UNAVAILABLE |
| `retries.*` | Node | Những retry do **policy** quyết định, phân nhóm |
| `ignores.*` | Node | Những error bị policy IGNORE |
| `speculative-executions` | Node | Extra attempts do speculative policy |
| `pool.in-flight` | Node | Messages đang đợi response |

**Không cộng `retries.total` và `errors.request.unsent` rồi gọi đó là “số application retries”**: unsent được driver xử lý ngoài policy và application retry là một lớp khác. Một response có thể bị bỏ do request timeout trong khi server vẫn xử lý mutation.

### 17.3. Đo retry amplification

Đặt ký hiệu:

\[
A = \frac{\text{Tổng số CQL messages tới nodes}}
         {\text{Tổng số logical CQL requests từ application}}.
\]

`A≈1` khi hầu như không có retries/speculations; `A>1` có thể do retry, speculative execution, multiple page fetches hoặc cách metric được gom. Đây là **ước lượng theo phạm vi metrics**, không phải đẳng thức để suy số retries chính xác. Phải căn chỉnh cùng service/cluster/time window, hiểu các endpoints/pages và kiểm driver version.

Ví dụ đo 60 giây:

~~~text
logical CQL requests = 10,000
node cql-messages     = 11,200
nominal amplification = 1.12

Không khẳng định:
  "tất cả 1,200 messages là DefaultRetryPolicy retry".

Cần xem:
  retries.total
  errors.request.unsent
  speculative-executions
  pool.in-flight
~~~

Nếu errors/timeouts tăng cùng attempts và Cassandra CPU/disk chạm ngưỡng, tăng retry có thể là **nguyên nhân duy trì sự cố**, không phải cách chữa.

### 17.4. Metrics phía Cassandra tương ứng

~~~bash
nodetool status
nodetool tpstats
nodetool compactionstats
nodetool tablestats retry_lab.orders_by_id
nodetool netstats
~~~

| Triệu chứng client | Quan sát server | Hướng điều tra |
|---|---|---|
| `UNAVAILABLE` tăng | Node DOWN, wrong RF/DC, gossip/ring không ổn | Replica liveness/placement |
| `READ_TIMEOUT` tăng | Read latency, SSTables-per-read, tombstones | Query shape, compaction, repair |
| `WRITE_TIMEOUT` tăng | Commitlog/memtable flush, disk await, blocked writers | Write path, disk/GC |
| `OVERLOADED` nhiều nodes | CPU/GC/queue tăng | Admission control/backpressure |
| `ABORTED` tăng | Network drops, heartbeat/connection logs | Network, TLS, thread stalls |
| `UNPREPARED` lặp bất thường | Node restarts/rollouts, schema churn | Prepared cache/session lifecycle |
| Driver timeout nhưng ít server timeout | Network RTT, client pool, I/O loop, throttler | Client deadline vs server handling |

**Không lấy hiệu hai percentile** driver/server để tính chính xác network latency, vì hai histogram có thể không cùng tập requests. Dùng tracing/time-correlated events và network metrics khi cần root cause.

### 17.5. Log có ích và log nguy hiểm

Ghi **allowlisted labels**:

~~~text
query_family=orders.byId
profile=read_only
consistency=LOCAL_QUORUM
idempotent=true
exception_type=ReadTimeoutException
coordinator_dc=dc1
retry_verdict=RETHROW
latency_ms=...
~~~

Không đưa raw CQL bind values, password, token/PII, email, tên khách hàng vào metrics labels. Nếu logging toàn bộ request trên hot path làm tăng allocation/GC, nó còn có thể khiến timeouts nặng thêm. Thống kê aggregate đủ để chẩn đoán phần lớn vấn đề.

## 18. Lab A — CQL + Java: phân biệt thành công và lỗi validation

**Mục tiêu:** Dùng Java Driver 4.x với `DefaultRetryPolicy` mặc định, kiểm CQL read theo PK và phát hiện lỗi **không nên retry**. Lab không làm node DOWN, không mở firewall, không gây overload. Những nhánh `READ_TIMEOUT`/`WRITE_TIMEOUT` được học bằng **bảng quyết định mô phỏng** ở Lab B, tránh gây bất ổn.

### 18.1. Điều kiện

- Cassandra 4.1/5.0 **lab một node**, port 9042 accessible.
- `cqlsh` và Java 17 + driver 4.17 (hoặc phiên bản 4.x tương thích).
- Quyền CQL tạo keyspace/table hoặc keyspace lab đã được cấp.
- Nếu tên DC thật không phải `datacenter1`, thay `withLocalDatacenter(...)` tương ứng.
- Các lệnh trong lab chỉ tạo dữ liệu **giả**, không chạy trên production.

### 18.2. Chuẩn bị schema và dữ liệu mẫu

~~~sql
CREATE KEYSPACE IF NOT EXISTS retry_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS retry_lab.orders_by_id (
  tenant_id text,
  order_id uuid,
  status text,
  amount decimal,
  PRIMARY KEY ((tenant_id), order_id)
);

CONSISTENCY ONE;

INSERT INTO retry_lab.orders_by_id (
  tenant_id, order_id, status, amount
) VALUES (
  'tenant-a',
  11111111-1111-1111-1111-111111111111,
  'PAID',
  1200.50
);

SELECT order_id, status, amount
FROM retry_lab.orders_by_id
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Kỳ vọng read trả `PAID`/`1200.50`. `SimpleStrategy`/RF1 và `ONE` chỉ dùng để **hiểu exception handling**, không phải mô hình production nhiều DC.

### 18.3. Java 17: thành công và lỗi query cố ý

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import com.datastax.oss.driver.api.core.servererrors.QueryValidationException;
import java.net.InetSocketAddress;
import java.util.UUID;

public final class RetryLab {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(
                    "127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            // Thử statement read-only hợp lệ.
            PreparedStatement prepared = session.prepare(
                "SELECT status, amount FROM retry_lab.orders_by_id " +
                "WHERE tenant_id = ? AND order_id = ?");

            BoundStatement read = prepared.bind(
                    "tenant-a",
                    UUID.fromString(
                        "11111111-1111-1111-1111-111111111111"))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true);

            Row row = session.execute(read).one();
            if (row == null
                    || !"PAID".equals(row.getString("status"))) {
                throw new IllegalStateException(
                    "Business verification failed");
            }
            System.out.println("VALID_READ_PASS");

            // Sai column cố ý: server trả query validation error.
            SimpleStatement invalid = SimpleStatement.builder(
                    "SELECT non_existing_column " +
                    "FROM retry_lab.orders_by_id " +
                    "WHERE tenant_id = 'tenant-a'")
                .setIdempotent(true)
                .build();

            try {
                session.execute(invalid);
                throw new AssertionError(
                    "Expected a query validation failure");
            } catch (QueryValidationException expected) {
                System.out.println(
                    "VALIDATION_NOT_RETRIED=" +
                    expected.getClass().getSimpleName());
            }

        } catch (DriverException ex) {
            // Session/node không khỏe hoặc lỗi khác ngoài expectation.
            System.err.println("DRIVER_FAILURE=" +
                ex.getClass().getSimpleName());
            throw ex;
        }
    }
}
~~~

**Kỳ vọng:**

~~~text
VALID_READ_PASS
VALIDATION_NOT_RETRIED=InvalidQueryException
~~~

Đây là **expected form**, không phải output được chạy sẵn. Nếu Driver 4.x trả subclass QueryValidation khác theo version/query, kiểm **exception class hierarchy**, không match raw error message. Mục đích lab không phải kiểm retries thực bằng cách gọi lỗi cú pháp hàng nghìn lần.

### 18.4. Cách chứng minh lỗi không nên retry

Một query sai tên cột sẽ lỗi dù gửi tới coordinator A hay B: lỗi nằm trong **schema/query definition**, không nằm ở replica đang chậm. Vì thế driver **không gọi RetryPolicy** cho `QueryValidationException`. Nếu ứng dụng tự retry 10 lần, số logs và server parse load tăng 10 lần mà kết quả không đổi.

### 18.5. Tập câu hỏi sau lab

1. `setIdempotent(true)` có làm một query sai cột trở thành retryable không? — **Không.**
2. Nếu ứng dụng nhận `AllNodesFailedException` thay vì `QueryValidationException`, phải đọc đâu? — Mapping lỗi per node và cause.
3. Việc SELECT trả dữ liệu có chứng minh RF3/quorum production không? — **Không**, lab RF1/ONE.
4. Code gọi `session.execute(read)` có thể đã được driver retry nội bộ mà ứng dụng không biết không? — **Có**, nếu có failure/retry branch thích hợp; dùng metrics/tracing để biết.

## 19. Lab B — Mô phỏng deterministic DefaultRetryPolicy decision table

**Mục tiêu:** Học đúng điều kiện nhánh retry mà **không** cần ngắt Cassandra hay inject timeout gây hại. Đoạn code sau là **mô hình giáo dục** dựa trên tài liệu, **không phải implementation của driver**, không thay thế tests chính sách trên phiên bản binary dùng thật.

### 19.1. Hàm quyết định cho read/write/unavailable

~~~java
import java.util.Objects;

public final class RetryDecisionModel {
    enum Verdict { RETRY_SAME, RETRY_NEXT, RETHROW }
    enum WriteType { SIMPLE, BATCH, UNLOGGED_BATCH,
                     BATCH_LOG, COUNTER, CAS }

    static Verdict unavailable(int retryCount) {
        return retryCount == 0
            ? Verdict.RETRY_NEXT
            : Verdict.RETHROW;
    }

    static Verdict readTimeout(
            int blockFor, int received,
            boolean dataPresent, int retryCount) {
        if (retryCount == 0
                && received >= blockFor
                && !dataPresent) {
            return Verdict.RETRY_SAME;
        }
        return Verdict.RETHROW;
    }

    static Verdict writeTimeout(
            WriteType type, boolean idempotent, int retryCount) {
        if (!idempotent) {
            return Verdict.RETHROW;
        }
        if (retryCount == 0 && type == WriteType.BATCH_LOG) {
            return Verdict.RETRY_SAME;
        }
        return Verdict.RETHROW;
    }

    static void expect(Verdict actual, Verdict expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError(
                "expected=" + expected + ", actual=" + actual);
        }
    }

    public static void main(String[] args) {
        expect(unavailable(0), Verdict.RETRY_NEXT);
        expect(unavailable(1), Verdict.RETHROW);

        expect(readTimeout(2, 2, false, 0),
            Verdict.RETRY_SAME);
        expect(readTimeout(2, 1, false, 0),
            Verdict.RETHROW);
        expect(readTimeout(2, 2, true, 0),
            Verdict.RETHROW);
        expect(readTimeout(2, 2, false, 1),
            Verdict.RETHROW);

        expect(writeTimeout(WriteType.BATCH_LOG, true, 0),
            Verdict.RETRY_SAME);
        expect(writeTimeout(WriteType.BATCH_LOG, false, 0),
            Verdict.RETHROW);
        expect(writeTimeout(WriteType.SIMPLE, true, 0),
            Verdict.RETHROW);
        expect(writeTimeout(WriteType.UNLOGGED_BATCH, true, 0),
            Verdict.RETHROW);

        System.out.println("DECISION_MODEL_PASS");
    }
}
~~~

Đoạn này có thể chạy riêng bằng Java 17 **nếu** được người học tạo file lab và compile trong môi trường của họ; Worker STEP 4 không chạy Java/Gradle để thực hiện Content QA. Khi ứng dụng thực gặp failure, driver còn có idempotence gating, query plan, deadline, hooks/retry state và metadata server — mô hình này cố ý chỉ biểu diễn **một phần các quyết định**.

### 19.2. Bài luyện decision table

| Input | Hỏi trước khi kết luận | Kết quả |
|---|---|---|
| `UNAVAILABLE`, retryCount=0 | Coordinator khác có thể nhìn liveness tốt hơn? | RETRY_NEXT |
| `READ_TIMEOUT`, blockFor=2, received=2, dataPresent=false | Có full data? | RETRY_SAME |
| `READ_TIMEOUT`, blockFor=2, received=1 | Đủ responses? | RETHROW |
| `WRITE_TIMEOUT`, `BATCH_LOG`, idempotent=true | First decision? | RETRY_SAME |
| `WRITE_TIMEOUT`, `SIMPLE`, idempotent=true | Có phải BATCH_LOG? | RETHROW |
| `WRITE_TIMEOUT`, `BATCH_LOG`, idempotent=false | Policy được gọi không? | Không; rethrow |
| Connection closed sau gửi, idempotent=false | Outcome biết chắc chưa ghi không? | RETHROW |
| Invalid CQL column | Retry có đổi query/schema không? | RETHROW ngoài policy |

### 19.3. Lab không phá cluster không thể chứng minh mọi lỗi runtime

Muốn kiểm `READ_TIMEOUT`, `WRITE_TIMEOUT`, mất kết nối, overload trong thực tế cần **fault injection lab riêng** có môi trường phục hồi, quan sát metrics và test oracle. Không tự tắt nodes production, khóa network hoặc làm disk đầy để “chụp screenshot lỗi”. Lab này chứng minh **hiểu decision rules**, còn integration tests/failure drills thuộc vòng QA/staging chuyên sâu.

## 20. Tình huống thực tế — chọn retry hay điều tra nguyên nhân

### Ca 1 — RF3, LOCAL_QUORUM, hai replicas DOWN

**Tình huống:** Keyspace NTS ở `dc1` có RF3, request `LOCAL_QUORUM` cần 2 phản hồi; chỉ còn một natural replica UP. Coordinator trả `UNAVAILABLE`.

**Default:** Thử coordinator tiếp theo một lần, **vẫn LOCAL_QUORUM**. Nếu cluster thật sự thiếu replicas, request vẫn fail.

**Xử lý:** Khôi phục replica/rebuild/repair theo runbook, kiểm ring và token ownership. Đừng đổi `LOCAL_QUORUM` thành `ONE` ngay vì có thể vi phạm data consistency.

### Ca 2 — READ_TIMEOUT, blockFor=2, received=2, dataPresent=false

**Tình huống:** Hai digest/replica responses đã về nhưng full data response chưa có.

**Default:** `RETRY_SAME` một lần, nếu `retryCount=0`.

**Xử lý:** Nếu lỗi lặp, kiểm coordinator chọn replica full data, node disk/read latency, SSTables/tombstones và network. Không suy rằng tất cả data đều mất.

### Ca 3 — READ_TIMEOUT, blockFor=2, received=1

**Default:** `RETHROW`; không có đủ responses, retry ngay cùng node ít cơ hội.

**Xử lý:** Đo `ReadLatency`/replica liveness, tombstones, GC; tránh application retry storm.

### Ca 4 — WRITE_TIMEOUT sau một ACK

**Tình huống:** Ghi trạng thái order bằng `SIMPLE`, CL=`LOCAL_QUORUM`, received=1/blockFor=2.

**Default:** `RETHROW` kể cả đã đánh dấu idempotent=true (không phải `BATCH_LOG`).

**Xử lý:** Kết quả **UNKNOWN**; truy vấn lại bằng PK/event version khi đủ CL, đồng bộ với audit/outbox, không khẳng định “write không xảy ra”.

### Ca 5 — BATCH_LOG timeout trong logged batch

**Tình huống:** Coordinator không ghi batchlog đủ nhanh và trả `writeType=BATCH_LOG`.

**Default:** Nếu idempotent=true, lần callback đầu `RETRY_SAME`. Nếu không idempotent, không vào callback.

**Xử lý:** Kiểm batchlog hosts/availability, logged batch size, node disk/GC. Không coi đây là lý do gom hàng nghìn unrelated partitions thành một batch.

### Ca 6 — UNLOGGED_BATCH timeout

**Default:** `RETHROW`, không chuyển thành `BATCH_LOG` chỉ vì source code có từ `BATCH`.

**Xử lý:** Một phần mutations có thể đã áp; phân loại idempotency từng operation, reconcile theo PK/event ID. Không retry toàn batch mù nếu chứa increment/list append.

### Ca 7 — Mất kết nối sau khi gửi INSERT

**Tình huống:** Driver đã gửi bytes nhưng TCP connection reset trước response.

**Default:** Với idempotent request, có thể retry node kế; với non-idempotent, rethrow.

**Xử lý:** Kiểm network/heartbeat và unknown outcome. Nếu tạo UUID mới trong vòng catch, nguy cơ duplicate. Giữ business ID ổn định và đối chiếu.

### Ca 8 — Pool không có connection trước network write

**Default:** Driver tự thử node tiếp theo ngoài `RetryPolicy` vì chưa gửi message; metric `errors.request.unsent` có thể tăng.

**Xử lý:** Kiểm pool saturation/client throttling/node health, không coi mọi “no connection” là đã ghi nửa chừng.

### Ca 9 — `UNPREPARED` tăng sau rolling restart

**Default:** Driver tự PREPARE lại trên coordinator rồi EXECUTE lại.

**Xử lý:** Nếu reprepare chỉ tăng ngắn hạn sau restart, theo dõi. Nếu kéo dài, kiểm node churn, prepared cache pressure, schema agreement, prepared CQL text/driver version. Không tự viết retry loop liên tục trên `UNPREPARED`.

### Ca 10 — `InvalidQueryException` do sai column

**Default:** RETHROW ngay, không gọi RetryPolicy.

**Xử lý:** Sửa code/schema migration/column type, thêm CI contract test. Retry 100 lần làm tốn CPU mà không tự tạo column.

### Ca 11 — `UnauthorizedException` khi role thiếu SELECT

**Default:** RETHROW ngay vì là query validation/authorization.

**Xử lý:** Sửa role/grant theo least privilege. Không dùng alternate credentials hoặc downgrade auth trong retry.

### Ca 12 — `OverloadedException` do read hot partition

**Default:** Nếu statement idempotent, thử node kế theo policy; nếu không, rethrow.

**Xử lý:** Hot partition vẫn do **cùng natural replicas** phục vụ dù coordinator khác. Giảm concurrency, sửa model/bucket, kiểm disk/compaction thay vì tăng retry.

### Ca 13 — `ReadFailureException` vì replica báo lỗi

**Default:** RETHROW trong nhánh policy, không retry đổi coordinator bất tận.

**Xử lý:** Xem server logs, disk corruption/I/O, repair, schema/codec error, metrics per node. Khi fix xong mới cho workflow retry nếu cần.

### Ca 14 — `DriverTimeoutException` nhưng server không báo READ_TIMEOUT

**Default:** Đây là client deadline, không phải server READ_TIMEOUT callback.

**Xử lý:** Kiểm driver pool in-flight, request throttler, Netty event loop, network, application thread contention và timer. Tăng timeout có thể giảm error metric nhưng tăng API p99; phải đo end-to-end SLO.

### Ca 15 — Ứng dụng retry `COUNTER UPDATE` hai lần

**Rủi ro:** Increment có thể áp hai lần khi lần đầu đã thực hiện nhưng ACK mất.

**Xử lý:** Không đánh dấu idempotent=true; nếu cần exactly-once business counter, thiết kế event dedup/aggregation có ID ổn định hoặc tính lại từ source-of-truth. RetryPolicy không sửa semantics counter.

### Ca 16 — Read-only API dùng speculative execution và retry cùng lúc

**Tình huống:** Nhiều requests chậm vì một rack có network latency cao.

**Rủi ro:** Speculative attempts **đồng thời** và retries sau lỗi cộng dồn tăng messages/CPU/replica work, có thể gây overload thứ cấp.

**Xử lý:** Đo `cql-requests` vs `cql-messages`, `speculative-executions`, retry counters và p99. Chỉ bật speculation cho queries **thực sự idempotent** và có đủ replica/capacity.

### Ca 17 — Bắt AllNodesFailed nhưng log “Cassandra down” quá sớm

**Rủi ro:** Có thể node A trả `UNAVAILABLE`, B mất connection, C trả read failure; nguyên nhân phân tán không đồng nhất.

**Xử lý:** Log sanitized `getAllErrors()` theo node/type, phân tích RF/DC/ring, rồi mới kết luận outage. `NoNodeAvailableException` có nghĩa không coordinator nào được thử.

### Ca 18 — Sửa policy thành IGNORE khi write timeout

**Rủi ro:** API trả success nhưng mutation chưa đủ CL; ứng dụng thanh toán/đơn hàng tin vào trạng thái chưa xác nhận.

**Xử lý:** Rollback custom/downgrading policy, phát incident correctness, reconcile theo event ID và audit. Không gọi đó là “tối ưu availability” nếu làm yếu invariant.

## 21. Runbook GO/HOLD/STOP khi retries tăng

### 21.1. Baseline trước thay chính sách

~~~text
SERVICE/CLUSTER:
  service, build, driver version:
  local datacenter, keyspace RF:
  application SLO:
  default/named retry policy:
  request timeout:
  default/statement idempotence:
  speculative execution enabled?:

OBSERVABILITY:
  app success/error/p95/p99:
  cql-requests and cql-client-timeouts:
  node cql-messages:
  retries.total and retries by error type:
  unsent / aborted / read-timeouts / write-timeouts:
  node liveness, p99 read/write, GC/disk:
~~~

### 21.2. Quy trình

~~~text
             Phát hiện retry/error rate bất thường
                          |
                  Xác định lỗi nào?
                     /           \
                  Permanent     Transient/ambiguous
                     |                 |
                STOP retry       Đọc exception data
                fix query        + idempotence
                                      |
                       Dữ liệu write outcome unknown?
                          /                  \
                        YES                   NO
                         |                     |
                    Reconcile trước        Còn deadline?
                    khi gửi lại                |
                         |                 Có/Không
                         |                     |
                    Business source        Throttle/backoff
                    /version/outbox        hoặc trả lỗi
                          \                  /
                           \                /
                         Theo dõi cluster health
                                  |
                         GO / HOLD / STOP
~~~

### 21.3. Bảng điều kiện hành động

| Dấu hiệu | Hành động | Lý do |
|---|---|---|
| Query validation/auth lỗi | **STOP retry** và sửa config/code | Retry không đổi logic |
| RF/DC không đủ quorum | **STOP/HOLD**, khôi phục replicas | Retry node khác không tạo replica |
| Write timeout có unknown outcome | **HOLD mutation replay**, reconcile | Tránh duplicate side effects |
| Errors tăng đồng thời node CPU/disk/GC cao | **THROTTLE/HOLD**, không tăng retries | Tránh amplification |
| Một coordinator network-isolated, các node khác khỏe | **GO có kiểm soát** với policy default | Thử node khác có cơ hội |
| Client p99 quá SLO dù error rate giảm | **HOLD/ROLLBACK** thay timeout | Tránh che root cause bằng chờ lâu |
| Counter/LWT/outbox side effect không idempotent | **STOP auto retry** | Nguy cơ sai nghiệp vụ |
| Staging fault-injection có đủ metrics, retry an toàn | **GO canary** từng service/profile | Có bằng chứng trước rollout |

Không có ngưỡng chung kiểu “`retries.total > 20` thì stop” cho mọi cluster. Dùng **tỷ lệ theo QPS, baseline và SLO**, đặc biệt phân biệt session errors với node-level attempts.

### 21.4. Sau canary/rollback

- Xác minh **effective retry policy** và idempotence profile từ JVM hiện tại, không chỉ source `application.conf`.
- Kiểm cả driver logical success **và** Cassandra p99, pending compaction, disk/GC, replica liveness.
- Phân loại những writes với unknown outcome và lịch reconcile; không báo thành công nếu chưa kiểm.
- Ghi rollback owner, change ID, config version và mốc UTC. Nếu cần restart session, tránh khởi động đồng loạt gây connection storm.
- Khóa policy config được quản lý tập trung; không để một `-D`/programmatic override cũ tự áp lại setting lỗi khi redeploy.

## 22. Checklist phát triển và vận hành DefaultRetryPolicy

### 22.1. Thiết kế Java/CQL

- [ ] Biết rõ `CqlSession` dùng driver **4.x phiên bản nào** và metadata/options có hiệu lực.
- [ ] `DefaultRetryPolicy` được giữ mặc định nếu không có lý do thay đủ bằng chứng.
- [ ] CQL được chuẩn bị/bind đúng partition key, clustering key và query pattern.
- [ ] Đã xác định RF theo DC và CL cho từng query family.
- [ ] Không coi `LOCAL_ONE`/`ONE` là giải pháp chung cho timeout với dữ liệu quan trọng.
- [ ] Đã phân biệt READ_TIMEOUT, WRITE_TIMEOUT, UNAVAILABLE, driver deadline.
- [ ] Biết `onUnavailable`/`onReadTimeout` và các nhánh yêu cầu idempotence khác nhau.
- [ ] Có audit idempotency cho mọi request được đánh dấu `true`.
- [ ] Không gắn `true` bừa cho COUNTER, LIST append/prepend, tự sinh UUID, LWT hoặc side effect đa hệ thống.
- [ ] Retry từ app có giới hạn attempts, deadline còn lại, backoff+jitter và circuit-breaker/bulkhead khi cần.
- [ ] Không gọi `Thread.sleep` hoặc blocking network I/O trong custom retry policy.
- [ ] Không tự tạo retry loop xử lý query validation/auth/codec errors.
- [ ] Nếu cần data write exactly-once, có event ID/version/outbox/dedup hoặc thiết kế nghiệp vụ tương đương.
- [ ] Có cơ chế trả `UNKNOWN/PENDING_RECONCILIATION` khi write timeout/outcome chưa chắc chắn.
- [ ] Không dùng `IGNORE`/downgrade CL như cách che lỗi.
- [ ] Có contract tests cho statements, typed bound values và consistency/idempotence flags.

### 22.2. Kiểm tra fault handling

- [ ] Phân biệt **chưa network write** với **đã gửi nhưng mất response**.
- [ ] Không tự viết xử lý `UNPREPARED` nhiều lần khi driver đã reprepare.
- [ ] Lỗi trước network write/bootstrapping không bị nhầm là policy retry.
- [ ] Với `READ_TIMEOUT`, ghi `received`/`blockFor`/`dataPresent`.
- [ ] Với `WRITE_TIMEOUT`, ghi `writeType`/`received`/`blockFor` và business ID không nhạy cảm.
- [ ] Với `UNAVAILABLE`, ghi `required`/`alive`/`CL`, kiểm RF/ring.
- [ ] Với `AllNodesFailedException`, kiểm `getAllErrors()` thay vì chỉ top-level message.
- [ ] Kiểm loại `QueryValidationException`/`ProtocolError`/`FunctionFailureException` không retry.
- [ ] Không tăng concurrency/retry khi `OverloadedException`/disk/GC đang tăng.
- [ ] Có staging fault tests và rollback nếu custom policy thay behavior mặc định.
- [ ] Không sử dụng các thao tác phá hoại (DROP/TRUNCATE/node shutdown) ngoài môi trường được phép.

### 22.3. Quan sát production

- [ ] Dashboard phân biệt session `cql-requests`/`cql-client-timeouts` và node `cql-messages`.
- [ ] Có `errors.request.unsent`, `aborted`, `read/write-timeouts`, `unavailables`, `retries.*`.
- [ ] Speculative executions được tính vào physical load.
- [ ] Có metrics p95/p99 latency và error rate theo query family/profile/CL.
- [ ] Có metrics Cassandra node CPU/GC/disk/compaction/replica liveness.
- [ ] Logs/sampled traces không chứa raw bind values, credentials, PII hoặc high-cardinality IDs.
- [ ] Có ngưỡng GO/HOLD/STOP theo baseline/SLO, không một số tùy tiện.
- [ ] Có owner, runbook rollback, config commit và timeline.
- [ ] Sau incident, các unknown write outcomes được đối chiếu với nguồn nghiệp vụ.

## 23. Câu hỏi tự đánh giá và gợi ý trả lời

**Câu 1.** `DefaultRetryPolicy` có phải mặc định của Java Driver 4.x không?  
**Định hướng:** Có; không cần khai báo để kích hoạt, chỉ override khi có lý do rõ.

**Câu 2.** Một logical CQL request có thể tạo hơn một message tới Cassandra không?  
**Định hướng:** Có; retry, speculative execution và các nhánh xử lý riêng có thể tạo thêm attempts.

**Câu 3.** `RETRY_NEXT` là gửi tới replica tiếp theo hay coordinator trong query plan?  
**Định hướng:** **Coordinator tiếp theo** do load balancing plan chọn; natural replicas vẫn theo token/RF.

**Câu 4.** `RETRY_SAME` có đổi consistency level không?  
**Định hướng:** Không trong DefaultRetryPolicy; vẫn dùng coordinator và CL ban đầu.

**Câu 5.** `IGNORE` có an toàn để thay cho RETHROW nếu muốn API thành công cao hơn không?  
**Định hướng:** Không; nó có thể báo success/empty result dù chưa đạt CL hoặc chưa biết trạng thái.

**Câu 6.** `UNAVAILABLE` khác `READ_TIMEOUT` như thế nào?  
**Định hướng:** UNAVAILABLE: coordinator biết không đủ live replicas trước khi xử lý; READ_TIMEOUT: ban đầu tưởng đủ nhưng phản hồi không đến kịp.

**Câu 7.** Với `UNAVAILABLE` và retryCount=0, DefaultRetryPolicy quyết định gì?  
**Định hướng:** RETRY_NEXT một lần, giữ nguyên CL.

**Câu 8.** `UNAVAILABLE` có cần `idempotent=true` để policy xét không?  
**Định hướng:** Không bắt buộc đối với callback này.

**Câu 9.** `READ_TIMEOUT` có `received=2, blockFor=2, dataPresent=false`, retryCount=0. Điều gì xảy ra?  
**Định hướng:** RETRY_SAME một lần.

**Câu 10.** Vì sao `dataPresent=false` vẫn có `received >= blockFor`?  
**Định hướng:** Có thể chỉ nhận digest/checksum responses mà chưa có full data.

**Câu 11.** `READ_TIMEOUT` nhận 1/2 phản hồi, retryCount=0. Default verdict là gì?  
**Định hướng:** RETHROW, không đủ responses.

**Câu 12.** `READ_TIMEOUT` với 2/2 responses, `dataPresent=true`. Default có retry không?  
**Định hướng:** Không; RETHROW.

**Câu 13.** `WRITE_TIMEOUT` có phải chứng minh mutation chưa được ghi trên bất kỳ replica nào?  
**Định hướng:** Không; kết quả có thể không chắc chắn hoặc ghi một phần.

**Câu 14.** `WRITE_TIMEOUT` loại `SIMPLE` được đánh dấu idempotent=true. Default có retry không?  
**Định hướng:** Không; policy RETHROW.

**Câu 15.** `WRITE_TIMEOUT` loại `BATCH_LOG`, idempotent=true, first callback. Default làm gì?  
**Định hướng:** RETRY_SAME một lần.

**Câu 16.** `BATCH_LOG` có nghĩa mọi lỗi logged batch đều được retry an toàn không?  
**Định hướng:** Không; BATCH_LOG chỉ là pha ghi batchlog, khác BATCH/UNLOGGED_BATCH và mutation đã áp một phần.

**Câu 17.** Khi connection đã đóng trước khi có response, request non-idempotent có được DefaultRetryPolicy retry next không?  
**Định hướng:** Không qua onRequestAborted; rethrow vì outcome không chắc.

**Câu 18.** Khi request chưa được gửi một byte nào do pool borrow fail, có cần gọi RetryPolicy không?  
**Định hướng:** Không; driver xử lý hard-coded, thử coordinator khác nếu có.

**Câu 19.** `UNPREPARED` sau node restart được xử lý thế nào?  
**Định hướng:** Driver tự PREPARE lại trên coordinator và gửi lại EXECUTE.

**Câu 20.** `InvalidQueryException` do sai tên cột nên retry mấy lần?  
**Định hướng:** Không retry; sửa CQL/schema.

**Câu 21.** `OverloadedException` có thể khiến default thử node khác không?  
**Định hướng:** Có với request idempotent và policy allowance; nhưng phải tránh retry storm nếu cả cluster overload.

**Câu 22.** `ReadFailureException`/`WriteFailureException` khác `READ_TIMEOUT`/`WRITE_TIMEOUT` ra sao?  
**Định hướng:** Failure thường là replica báo lỗi, timeout là không đủ phản hồi đúng hạn; default rethrow read/write failures.

**Câu 23.** `DriverTimeoutException` có phải callback `onReadTimeoutVerdict` không?  
**Định hướng:** Không; đó là client-side request deadline.

**Câu 24.** Vì sao một write timeout phải được biểu diễn `UNKNOWN_OUTCOME`?  
**Định hướng:** Replica có thể đã ghi nhưng ACK chậm/mất, cần reconcile trước khi retry.

**Câu 25.** Tại sao bật `basic.request.default-idempotence=true` trên toàn bộ mixed workload nguy hiểm?  
**Định hướng:** Có COUNTER/list append/LWT/TTL/side effect không idempotent, driver có thể retry/speculate sai.

**Câu 26.** `setIdempotent(true)` có ép DefaultRetryPolicy retry mọi write timeout không?  
**Định hướng:** Không; chỉ cho phép policy xét, policy vẫn rethrow SIMPLE/BATCH/UNLOGGED_BATCH.

**Câu 27.** `ConsistencyDowngradingRetryPolicy` có điểm nguy hiểm gì?  
**Định hướng:** Có thể giảm CL hoặc ignore lỗi, phá invariants/read-your-writes/DC locality.

**Câu 28.** `retryCount=0` là số lần application đã gọi `session.execute` hay số lần policy xem xét trước đó?  
**Định hướng:** Số lần policy đã được gọi trước callback hiện tại.

**Câu 29.** Tại sao không gọi `Thread.sleep` trong `RetryPolicy`?  
**Định hướng:** Callback chạy trên driver I/O threads; blocking làm ảnh hưởng mọi requests khác.

**Câu 30.** Muốn tìm hiểu `AllNodesFailedException` phải xem gì?  
**Định hướng:** `getAllErrors(): Map<Node,List<Throwable>>`, không chỉ message top-level.

**Câu 31.** Driver metrics `cql-requests` khác `cql-messages` như thế nào?  
**Định hướng:** Logical requests ở session vs messages/attempts gửi từng node.

**Câu 32.** `errors.request.unsent` và `errors.request.aborted` có thể gộp thành một nghĩa “chưa ghi” không?  
**Định hướng:** Không; unsent chưa gửi, aborted có thể xảy ra sau gửi với outcome chưa chắc.

**Câu 33.** RetryPolicy có tự xử lý deadline của toàn API 30 trang không?  
**Định hướng:** Không; cần end-to-end deadline ở service và giới hạn pages/rows.

**Câu 34.** Nếu `LOCAL_QUORUM` không đủ replica, tăng timeout 2s lên 30s có chắc thành công không?  
**Định hướng:** Không; timeout không tạo lại replicas/quorum.

**Câu 35.** Giảm error rate bằng tăng timeout có luôn cải thiện trải nghiệm người dùng không?  
**Định hướng:** Không; p99 và request in-flight có thể tăng, cần đo SLO và resource.

**Câu 36.** Một sự cố khiến retry tăng cùng disk await và GC. Nên tăng max retry hay throttle?  
**Định hướng:** Ưu tiên giảm tải/điều tra capacity, không khuếch đại physical messages.

## 24. Tổng kết

~~~text
               JAVA DRIVER 4.x CQL REQUEST
                           |
                    Classify error
                           |
         +-----------------+-------------------+
         |                 |                   |
   UNSENT/UNPREPARED   Policy callbacks    PERMANENT ERROR
         |                 |                   |
   Driver handles      UNAVAILABLE           QueryValidation
   separately          READ_TIMEOUT          FunctionFailure
         |              WRITE_TIMEOUT         ProtocolError
         |              REQUEST_ABORTED           |
         |              ERROR_RESPONSE        RETHROW
         |                 |
         |           Is this branch gated
         |             by idempotence?
         |                 |
         |           Default decision
         |        SAME/NEXT/RETHROW
         |                 |
         +-----------------+-------------------+
                           |
                     Deadline remains?
                           |
                   Result or Exception
                           |
              Application decides based on:
          business idempotency / RPO / SLO / CL
                  |                   |
              Reconcile           Stop/backoff
              unknown writes      within budget
                  |                   |
                  +---------+---------+
                            |
                    Correct outcome
                   with useful metrics
~~~

Một quy tắc nhớ nhanh, nhưng phải dùng cùng ma trận ở mục 4:

- **UNAVAILABLE:** thử coordinator khác tối đa một lần, không hạ CL.
- **READ_TIMEOUT:** chỉ retry same khi đủ responses nhưng chưa có **full data**.
- **WRITE_TIMEOUT:** mặc định chỉ `BATCH_LOG`, và callback cần statement idempotent.
- **Mất connection sau gửi:** chỉ cân nhắc retry cho idempotent; **chưa gửi** là nhánh hard-coded an toàn hơn.
- **Server errors khác:** phân biệt overloaded/server error với read/write failures.
- **UNPREPARED:** driver tự reprepare; **query validation/function/protocol** không retry.
- **DriverTimeoutException:** deadline client, không suy “server không ghi”.
- **Application retry:** luôn budget attempts/deadline/backoff và reconcile unknown outcomes.

**Thông điệp quan trọng nhất:** `DefaultRetryPolicy` của Cassandra Java Driver 4.x là **chính sách bảo thủ, theo loại lỗi**, không phải “thử lại cho đến khi thành công”. Sự an toàn đến từ **điều kiện server đã trả, khả năng mutation được áp dụng, idempotence thực tế, RF/CL và giới hạn tải**. Đúng đắn nghiệp vụ phải được kiểm chứng **ngoài** RetryPolicy, nhất là khi lỗi ghi khiến client không biết chắc trạng thái trên replicas.

## Tài liệu tham khảo

- [Apache Cassandra Java Driver 4.18 — Retries](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/) — mặc định theo các callback, hard-coded paths, consistency downgrade và profiles.
- [Apache Cassandra Java Driver 4.18 — Idempotence](https://apache.github.io/cassandra-java-driver/4.18.1/core/idempotence/) — `setIdempotent`, default-idempotence, retries/speculation và unsafe mutations.
- [Apache Cassandra Java Driver — RetryPolicy Javadoc](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/retry/RetryPolicy.html) — `onXxxVerdict`, callback I/O thread, return verdicts.
- [DataStax Java Driver 4.17 — Retries](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/retries/) — manual đúng nhánh Java Driver 4.17.
- [DataStax Java Driver 4.17 — Reference configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/reference/) — `advanced.retry-policy.class`, request timeout, metrics và profile inheritance.
- [DataStax Java Driver 4.17 — AllNodesFailedException](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/AllNodesFailedException.html) — `getAllErrors()`/NoNodeAvailable.
- [DataStax Java Driver 4.17 — ReadTimeoutException](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/servererrors/ReadTimeoutException.html) — `received`, `blockFor`, `wasDataPresent()`.
- [DataStax Java Driver 4.17 — WriteTimeoutException](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/servererrors/WriteTimeoutException.html) — `getWriteType()`, semantics of timeout.
- [DataStax Java Driver 4.17 — DriverTimeoutException](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/DriverTimeoutException.html) — client-side timeout.
- [DataStax Java Driver 4.17 — DefaultDriverOption](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/config/DefaultDriverOption.html) — request timeout, idempotence và policy options.
- [DataStax Java Driver 4.17 — Metrics](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metrics/) — cql-requests, cql-messages, errors.request.*, retries.*, ignores.*.
- [DataStax Java Driver 4.17 — Speculative execution](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/speculative_execution/) — extra attempts và idempotency.
- [DataStax Java Driver 4.17 — Prepared statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/) — caching, UNPREPARED và reprepare.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — ring/token/replication/consistency/coordinator.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — server read/write latency, compaction, request failures.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — query-first schema, partition key và hot partition risks.

