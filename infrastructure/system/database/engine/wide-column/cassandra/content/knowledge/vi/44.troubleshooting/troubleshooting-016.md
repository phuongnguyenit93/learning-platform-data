# LWT contention, xung đột và thao tác có kết quả chưa biết trong Apache Cassandra

> **Chương:** Xử lý sự cố  
> **Phạm vi:** Apache Cassandra 4.1/5.x, CQL, replication/consistency levels, Java Driver 4.x và cách chẩn đoán **lightweight transactions (LWT)** dựa trên Paxos. Ví dụ dùng dữ liệu giả và môi trường lab riêng. Không gây contention, tắt node, đổi timeout hoặc chạy sửa dữ liệu trên production khi chưa có quyền và runbook.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích lý do cần LWT khi nhiều client cạnh tranh cập nhật **cùng thực thể logic/partition**, thay vì dựa trên read-then-write thường.
2. Phân biệt **normal write**, **conditional insert/update/delete** và **transaction đọc có serial consistency**.
3. Mô tả Paxos ở mức khái niệm: prepare/promise, proposal/accept, commit/learn; hiểu vì sao các vòng thông điệp làm latency tăng.
4. Đặt và diễn giải đúng **normal consistency level** cùng **serial consistency level** của một conditional write.
5. Hiểu ý nghĩa `[applied]=true`, `[applied]=false` và tại sao false là **xung đột điều kiện**, không mặc nhiên là sự cố Cassandra.
6. Chẩn đoán **LWT contention** do hotspot partition, nhiều writers, CAS retry loops, timeout budgets, client concurrency và môi trường replica/GC/network.
7. Nhận ra các trạng thái **KNOWN_APPLIED**, **KNOWN_NOT_APPLIED**, **UNKNOWN_OUTCOME** và phân biệt chúng với read/write availability.
8. Biết vì sao `CASWriteUnknownException`, `WriteTimeoutException` hoặc `DriverTimeoutException` **không cho phép kết luận** thao tác đã/không được áp dụng.
9. Thiết kế **idempotency key, operation ID, revision fencing và đối soát trạng thái** để tránh tạo hai đơn hàng/trừ tiền hai lần khi client retry.
10. Viết CQL và Java Driver 4.x với `INSERT ... IF NOT EXISTS`, `UPDATE ... IF revision=?`, `ResultSet.wasApplied()`, normal/serial CL và log kết quả theo outcome.
11. Sử dụng metrics `CASRead`/`CASWrite`, `ConditionNotMet`, `ContentionHistogram`, `UnfinishedCommit`, timeout, GC, disk và driver retries để tìm nguyên nhân.
12. Xây dựng runbook điều tra sự cố và kiểm thử đối chứng, đặt guardrails cho workload có LWT, xác định khi nào retry, dừng hoặc cần đối soát thủ công.

**Bối cảnh module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`:** Cassandra phân tán dữ liệu bằng partition key/token, áp replication factor (RF) và consistency level (CL) để quyết định cách đọc/ghi trên các natural replicas. LWT bổ sung một giao thức đồng thuận cho **conditional state transitions** trong phạm vi hỗ trợ, nhưng không biến Cassandra thành một hệ giao dịch SQL ACID toàn cục. Người viết Java cần kết hợp đúng CQL, Paxos, Java Driver, thiết kế bảng theo truy vấn, lỗi mạng và vận hành replica/repair để bảo vệ tính đúng dữ liệu.

## 2. Bài toán: hai client cùng kiểm tra rồi ghi

Giả sử một tài khoản có `status=PENDING` và chỉ một client được chuyển sang `CONFIRMED`:

~~~text
Thời điểm        Client A                 Client B
----------------------------------------------------------------
T0               SELECT status=PENDING   SELECT status=PENDING
T1               Quyết định được ghi     Quyết định được ghi
T2               UPDATE CONFIRMED        UPDATE CANCELLED
T3               ACK                     ACK

Kết quả cuối phụ thuộc timestamp/last-write-wins, không phải
một "người thắng theo điều kiện" đã được xác nhận nguyên tử.
~~~

Hai phép đọc thường và hai phép ghi thường **không** tạo thành compare-and-set (CAS) nguyên tử. Cassandra normal writes áp timestamp và quy tắc giải quyết xung đột giữa replica; ngay cả khi cả hai client đọc ở `QUORUM` rồi ghi `QUORUM`, bước **read → kiểm tra ở Java → write** vẫn có khoảng đua (*time-of-check/time-of-use*, TOCTOU).

Giải pháp khi nghiệp vụ thực sự cần **chỉ cập nhật nếu điều kiện hiện tại còn đúng** là dùng conditional CQL:

~~~sql
UPDATE lwt_lab.account_state
SET status = 'CONFIRMED', revision = 2
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF revision = 1;
~~~

Cassandra thực hiện điều kiện trong LWT/Paxos để cạnh tranh được phân xử. Một client có thể nhận `[applied]=true` và client kia nhận `[applied]=false` — nhưng nếu client **timeout trước khi có phản hồi**, kết quả chưa thể kết luận ngay. Đây là vấn đề trung tâm của bài học.

### 2.1. Khi nào nên dùng LWT?

| Nhu cầu | LWT có phù hợp? | Giới hạn cần biết |
|---|---|---|
| Đặt trước một username duy nhất trong bảng lookup được thiết kế đúng | Thường có | Unique chỉ theo key/scope đã được mô hình hóa |
| Chuyển state với `IF revision = n` | Có | Cạnh tranh cao trên một partition làm latency tăng |
| Chỉ tạo record mới nếu key chưa tồn tại | `INSERT ... IF NOT EXISTS` | Retry sau timeout cần operation ID |
| Thay state khi `IF status = 'PENDING'` | Có | Điều kiện cần giới hạn đúng row/partition |
| Update event log append-only, không cạnh tranh | Thường không cần | Normal writes nhanh hơn và ít round trips |
| Transaction ngân hàng qua hai partitions/2 microservices | **Không đủ** | Không có ACID transaction chung cho mọi partition/hệ khác |
| Cấp số thứ tự toàn cluster bằng một partition tăng mãi | Có thể nhưng thường là hotspot nguy hiểm | Throughput bị serialization/contended Paxos |
| Exactly-once cho Kafka + Cassandra + HTTP API | LWT riêng **không đủ** | Cần idempotency/inbox/outbox/saga và reconciliation |

**Quy tắc:** LWT là công cụ bảo vệ một **invariant cụ thể**, không phải cờ “bật consistency mạnh hơn cho tất cả INSERT”.

## 3. LWT hoạt động ở mức khái niệm như thế nào?

### 3.1. Consensus chứ không chỉ quorum write

Một mutation thường ở `LOCAL_QUORUM` được gửi tới các replicas và chờ đủ ACK. Nhưng nó không thực hiện một cuộc bỏ phiếu độc lập để bảo đảm điều kiện **“giá trị vẫn bằng n trước khi ghi”**.

LWT bổ sung **Paxos**. Mô hình trừu tượng:

~~~text
                  Client A: UPDATE IF revision=1
                                |
                           Coordinator
                                |
           1. PREPARE / PROMISE (ballot, existing state)
                           /    |    \
                         R1    R2    R3
                           \    |    /
                                |
              2. Evaluate condition / choose proposal
                                |
              3. PROPOSE / ACCEPT (agreed value)
                           /    |    \
                         R1    R2    R3
                           \    |    /
                                |
              4. COMMIT / LEARN (ordinary CL phase)
                                |
                          [applied] result
~~~

Đây là **mô hình học thuật**, không phải trace chính xác tất cả thông điệp của mọi phiên bản. Cassandra 4.1 cải tiến Paxos so với các bản cũ, nên số network round trips/fast-path thay đổi theo phiên bản, contention và recovery path. Không hardcode “LWT luôn đúng bốn round trips” khi đánh giá latency. Xem tài liệu [Cassandra guarantees](https://cassandra.apache.org/doc/stable/cassandra/architecture/guarantees.html) và thông tin [Cassandra 4.1 Paxos improvements](https://cassandra.apache.org/_/blog/Cassandra-4.1-is-here.html).

### 3.2. Paxos ballot và proposal không giống Cassandra cell timestamp

- **Ballot/proposal**: giúp nhiều proposers cạnh tranh để các replicas thống nhất một giá trị/operation cho vòng consensus.
- **CQL cell timestamp**: liên quan quy tắc giải quyết các normal mutations (last-write-wins) và storage semantics.
- **Application revision/version**: số hoặc token do nghiệp vụ dùng để kiểm điều kiện CAS và biết ai đã thay đổi trạng thái.
- **Operation ID**: định danh **một ý định nghiệp vụ** để đối soát sau timeout.

Không lấy timestamp trong Java làm “ballot ID”, và không coi một `USING TIMESTAMP` tự cấp quyền thắng cuộc trong LWT. CQL áp những hạn chế riêng với conditional mutations; hãy dùng contract CQL thực của phiên bản thay vì trộn custom timestamps vào LWT.

### 3.3. Linearizability nằm trong phạm vi được hỗ trợ

LWT được thiết kế để có tính chất **linearizable compare-and-set** đối với các thao tác tham gia đúng giao thức và phạm vi partition/replica tương ứng. Điều đó **không** có nghĩa:

- Một ứng dụng được quyền ghi normal UPDATE cùng row rồi vẫn đòi mọi thao tác có serial semantics như LWT.
- LWT trên partition A và partition B là một giao dịch nguyên tử chung.
- Đã đạt Paxos thì mọi read ở `ONE` ngay sau đó luôn quan sát commit bất kể **normal CL** sử dụng.
- Cassandra đã cung cấp transaction end-to-end qua message broker, cache, search index hoặc dịch vụ thanh toán.

**Điều kiện tiên quyết khi thiết kế:** mọi actor thay state chịu cùng invariant nên dùng **cùng quy tắc LWT/versioning** và một bảng/partition model phù hợp. Nếu một writer bỏ qua CAS, invariant có thể bị phá ngay cả khi những writers khác đều dùng LWT.

## 4. Những câu CQL nào kích hoạt LWT?

| CQL | Ý nghĩa | Có LWT? |
|---|---|---|
| `INSERT INTO ... VALUES (...)` | Upsert thường | Không |
| `INSERT INTO ... VALUES (...) IF NOT EXISTS` | Chỉ tạo khi key chưa tồn tại | Có |
| `UPDATE ... SET ... WHERE PK=...` | Upsert thường | Không |
| `UPDATE ... SET ... WHERE PK=... IF revision=...` | CAS theo giá trị điều kiện | Có |
| `UPDATE ... SET ... WHERE PK=... IF EXISTS` | Chỉ sửa row nếu tồn tại | Có |
| `DELETE FROM ... WHERE PK=...` | Xóa thường | Không |
| `DELETE ... WHERE PK=... IF status=...` | Xóa có điều kiện | Có |
| `BEGIN BATCH ... APPLY BATCH` | Batch thường, semantics riêng | Không mặc nhiên có Paxos |
| Conditional batch được CQL hỗ trợ trên cùng partition | Nhiều mutations có điều kiện | Có, nhưng bị giới hạn và tốn chi phí |

**Phải chỉ rõ primary key trong WHERE** theo yêu cầu của conditional DML. Không thể dùng LWT như `UPDATE table SET ... WHERE arbitrary_secondary_index=... IF ...` để khóa mọi rows của một tenant. Đây là database wide-column thiết kế theo truy vấn, không phải row-lock SQL engine.

### 4.1. `INSERT IF NOT EXISTS` và bất biến “tạo đúng một lần”

~~~sql
INSERT INTO lwt_lab.account_state
  (account_id, status, revision, last_op_id)
VALUES (
  11111111-1111-1111-1111-111111111111,
  'PENDING', 1,
  22222222-2222-2222-2222-222222222222
)
IF NOT EXISTS;
~~~

Nếu row đã tồn tại, Cassandra trả về **conditional result** `[applied]=false` (kèm dữ liệu hiện có tùy câu lệnh/phiên bản). Đây có thể là một **business conflict bình thường**, không có nghĩa node DOWN hay disk lỗi.

### 4.2. `UPDATE IF revision = n` và optimistic concurrency

~~~sql
UPDATE lwt_lab.account_state
SET status = 'CONFIRMED',
    revision = 2,
    last_op_id = 33333333-3333-3333-3333-333333333333
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF revision = 1;
~~~

Nếu một writer khác đã cập nhật revision lên 2:

~~~text
[applied] | revision | ...
----------+----------+-----
    False |        2 | ...
~~~

Những cột trả về trong result của conditional failure **phụ thuộc statement/server version**. Không viết logic dựa vào giả định mọi cột sẽ luôn xuất hiện; nếu cần state đầy đủ để phân loại conflict, thực hiện **SELECT theo primary key** tại CL phù hợp và kiểm version/op ID.

### 4.3. `IF EXISTS` không phải một distributed mutex dài hạn

~~~sql
UPDATE lwt_lab.account_state
SET status = 'SUSPENDED'
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF EXISTS;
~~~

Lệnh chỉ kiểm **row còn tồn tại tại điểm CAS**, không khóa row cho code Java làm việc thêm 5 phút. Nếu sau khi nhận ACK rồi Java gửi HTTP tới một hệ khác, LWT không giữ lock liên dịch vụ trong thời gian ấy.

### 4.4. Conditional batch: giới hạn rất quan trọng

Một conditional batch có thể giúp bảo vệ những cập nhật **trong cùng partition** theo khả năng CQL; không suy rằng `BEGIN BATCH` biến nhiều partitions thành ACID transaction toàn cục. Khi cần tạo uniqueness lookup và write record trong **hai partitions khác nhau**, phải thiết kế protocol/saga, owner, rollback/reconciliation riêng.

## 5. Hai consistency levels của LWT: serial và normal

Một conditional write không chỉ có một CL. Ta phải phân biệt:

- **Serial consistency level (SCL)**: phạm vi đồng thuận Paxos để quyết định giá trị/điều kiện. Thường chọn `SERIAL` hoặc `LOCAL_SERIAL`.
- **Normal consistency level (NCL/WCL)**: mức ACK của **learn/commit phase** và điều kiện quan sát kết quả qua những normal reads sau đó. Thường `QUORUM` hoặc `LOCAL_QUORUM` khi nghiệp vụ cần khả năng quan sát phù hợp.

Trong `cqlsh` có hai lệnh tách biệt:

~~~text
cqlsh> CONSISTENCY LOCAL_QUORUM;
cqlsh> SERIAL CONSISTENCY LOCAL_SERIAL;
~~~

Lệnh thứ nhất không tự đặt mức serial, và lệnh thứ hai không tự thay normal consistency. Trong Java Driver 4.x cũng cần thiết lập **hai properties** của statement.

### 5.1. Chọn mức CL dựa vào RF/DC

Giả sử `NetworkTopologyStrategy` có RF3 tại dc1 và RF3 tại dc2:

| Mục đích | Ví dụ serial CL | Ví dụ normal CL | Điều cần lưu ý |
|---|---|---|---|
| Chỉ cần serialization trong DC cục bộ theo hợp đồng | `LOCAL_SERIAL` | `LOCAL_QUORUM` | Phạm vi DC cục bộ, không tự cam kết global serial order |
| Cần serialization xuyên các DC tham gia | `SERIAL` | `QUORUM` (tùy read contract) | WAN latency/availability, số replicas và phạm vi giao |
| Đọc giá trị nhất quán với transaction trước đó | Serial read khi thực sự cần | Read CL phải phù hợp commit visibility | Không mặc định mọi `ONE` read đều thấy LWT mới |
| Lab một node RF1 | `SERIAL` | `ONE` | Để học CQL, không chứng minh quorum đa node |

**Nguy cơ lớn:** Hai vùng dc1/dc2 cùng ghi một khóa logic bằng `LOCAL_SERIAL` ở hai local DC khác nhau **không nên được quảng bá là global linearizability**. Nếu invariant cần một thứ tự toàn cục, thống nhất toàn bộ writers theo một lựa chọn serial scope và topology được kiểm thử; cân nhắc coordinator locality, global serial level, failover và WAN partition.

### 5.2. Normal CL quyết định read visibility sau conditional write

Lời giải thích của `cqlsh` phân tách serial phase và learn/commit phase. Chẳng hạn một conditional write thành công ở NCL=`QUORUM` tạo cơ sở để một read `QUORUM` phù hợp nhìn thấy commit đó. Nếu normal CL quá yếu (đặc biệt `ANY` trong những tình huống được hỗ trợ), không thể tự khẳng định một normal read mạnh hơn lập tức thấy update; **serial read** có thể phải hoàn tất pending Paxos state.

Không lấy công thức `W+R>RF` của ordinary quorum writes rồi suy rằng mọi pha của Paxos đều giống normal writes. Ghi **cả SCL và NCL** trong trace và runbook.

### 5.3. Hình dung CL theo pha

~~~text
Conditional UPDATE IF revision=7
      |
      +-- SERIAL / LOCAL_SERIAL
      |     Paxos PREPARE + PROPOSE
      |     Chọn proposal/kiểm expected state
      |
      +-- QUORUM / LOCAL_QUORUM / other NCL
            Commit/Learn + ACK visibility
      |
      +-- [applied] true/false
            (chỉ khi client đã nhận được kết quả)
~~~

Trong Cassandra 4.1+, tối ưu fast path có thể thay đổi những round trips thực; sơ đồ chỉ có mục đích **phân trách nhiệm các mức consistency**, không phải chứng minh lịch trình wire protocol chi tiết.

### 5.4. `SERIAL` read khác normal `SELECT`

Một read ở serial consistency có thể làm việc để **học/hoàn tất một Paxos commit đang dở**, thay vì chỉ đọc normal replica values. Điều này có chi phí. Không nên chuyển mọi SELECT sang `SERIAL` chỉ để giảm độ bất định; sử dụng cho **reconciliation/contract cần tính chất đó**, với timeout/throughput/overhead được đánh giá.

### 5.5. LWT và transient replication

Nếu cluster dùng transient replication hoặc mixed versions, yêu cầu full replica/consensus và feature support có sắc thái phiên bản; không lấy bảng RF3 “toàn full replicas” làm phép tính chung. Khi cần bảo đảm semantics, kiểm tài liệu của đúng Cassandra release, feature flags và topology, đồng thời thử trên môi trường phản ánh production.

## 6. Ý nghĩa `[applied]`: logic nghiệp vụ, không phải HTTP status

### 6.1. Ba kết quả khác nhau

~~~text
CQL result:
    [applied] = true
=> Conditional statement was applied

CQL result:
    [applied] = false
=> Condition for THAT attempt was not satisfied;
   current values may be returned

No definitive CQL result because timeout/network/CAS unknown
=> UNKNOWN_OUTCOME
   statement may have applied, may not have applied,
   or may still be completing.
~~~

**Không có trạng thái `[applied]=null` do server gửi để biểu diễn unknown** trong giao thức thành công: khi client không nhận được definitive response, phải phân loại exception/timeout và xử lý tại application.

### 6.2. `[applied]=false` vẫn là một lời đáp thành công ở tầng transport

Ví dụ:

~~~sql
UPDATE lwt_lab.account_state
SET status = 'CANCELLED', revision = 3
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF revision = 1;
~~~

Nếu current revision là 2, Cassandra có thể trả:

~~~text
 [applied] | revision
-----------+----------
     False |        2
~~~

Request đã **được xử lý có kết quả rõ ràng**; không nên ghi vào `server_errors` như timeout/hạ tầng. Với HTTP API, có thể ánh xạ nó sang **409 Conflict**, **412 Precondition Failed** hoặc outcome nghiệp vụ tương ứng. Đây là **lựa chọn API contract**, không phải HTTP mapping mặc định của Cassandra.

### 6.3. `[applied]=false` sau retry có thể là dấu vết một thành công cũ

~~~text
Client A sends INSERT IF NOT EXISTS, operation_id=OP-7
  |
Server decides/applies INSERT
  |
Response lost before client receives
  |
Client retries same conditional INSERT
  |
Server sees row exists -> [applied]=false
~~~

Nếu chỉ thấy `[applied]=false` ở attempt 2 rồi ghi “operation OP-7 thất bại”, ứng dụng có thể **đánh sai giao dịch đã hoàn tất**. Phải đọc lại row, kiểm `last_op_id`/request ID và expected version, phân biệt “đã được áp dụng ở attempt trước” với “một actor khác tạo row”.

### 6.4. `ResultSet.wasApplied()` trong Java Driver

~~~java
ResultSet result = session.execute(conditionalStatement);
if (result.wasApplied()) {
    // CAS was applied for this server-confirmed attempt.
} else {
    // Condition was not satisfied.
    // Check expected current state / business conflict.
}
~~~

Theo Java Driver Javadoc, `wasApplied()` đọc cột `[applied]` cho CQL conditional DML. Nó **trả true với non-conditional queries và DDL IF NOT EXISTS** vì các lệnh này không trả cột `[applied]`; **tuyệt đối không** gọi `wasApplied()` trên ordinary INSERT hay CREATE TABLE rồi tuyên bố LWT đã thành công. [Driver ResultSet API](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/cql/ResultSet.html).

### 6.5. Kết quả rõ ràng ở attempt khác kết quả cuối của logical operation

| Attempt A | Attempt B | Dữ liệu sau đối soát | Kết luận logical operation |
|---|---|---|---|
| `[applied]=true` | Không cần | `last_op_id=A` | Đã áp dụng ở A, sau đó có thể có write mới |
| Timeout | `[applied]=false` | `last_op_id=A`, expected revision | Có bằng chứng A đã áp dụng; B thấy row tồn tại/đã thay |
| Timeout | `[applied]=false` | `last_op_id=B` | Một thao tác khác thắng; A chưa thể mặc nhiên “failed” nếu lịch sử chưa rõ |
| Timeout | Không retry | Row vẫn old revision | Chưa chứng minh chắc A không còn in flight |
| Timeout | Timeout | State không đủ metadata | **UNKNOWN**, cần điều tra hoặc reconciliation |

**Không coi một snapshot hiện tại là lịch sử đầy đủ.** Nếu sau OP-A có OP-B hợp lệ thay state, `last_op_id=B` không chứng minh OP-A *chưa từng được áp dụng*. Muốn chứng minh “đã từng xảy ra” trong chuỗi nhiều updates, cần **audit/inbox event history** có thiết kế phù hợp.

## 7. Các dạng xung đột cần phân biệt

### 7.1. Business conflict: điều kiện không còn đúng

~~~text
Writer A expects revision=8
Writer B expects revision=8

A CAS: [applied]=true -> revision=9
B CAS: [applied]=false -> observed revision=9

=> Conflict expected under optimistic concurrency.
~~~

Ứng dụng nên trả conflict rõ hoặc **đọc lại state rồi xét rule nghiệp vụ**, không retry không giới hạn cùng expected revision. Nếu stale client “bump expected revision” sau mỗi conflict mà không tái xét invariant, nó biến LWT thành last-writer-wins trá hình.

### 7.2. Paxos contention: nhiều proposals chồng lên nhau

~~~text
Writer A PREPARE ballot A1
Writer B PREPARE ballot B1
Writer C PREPARE ballot C1
                         |
   Promises/accepted values can supersede proposals
                         |
   Some proposers need retry/learn/abort
                         |
   Latency + contention counters rise
~~~

Nhiều proposals cùng key/partition làm Paxos retry hơn, tăng response time, đôi khi hết `cas_contention_timeout`. Đây là **giao thức phải phân xử cạnh tranh**, không nhất thiết là data corruption.

### 7.3. Replica/network conflict: thiếu ACK và commit không rõ

Một proposer có thể nhận đủ agreement nhưng client mất response ở commit phase. Khi đó **server vẫn có thể áp mutation**, dù ứng dụng chỉ thấy timeout/unknown. Quorum/serial semantics **không xóa** vấn đề distributed systems kinh điển: **client không nhận được ACK không có nghĩa server chưa commit**.

### 7.4. Last-write-wins conflict do normal writer xen vào

Nếu một code path dùng LWT, một code path khác cập nhật **cùng state** bằng ordinary UPDATE và timestamp tự do, bảo đảm CAS không còn áp dụng cho toàn bộ business protocol. Đây là **vi phạm thiết kế**, không thể sửa bằng tăng `SERIAL` hay `QUORUM` cho riêng LWT.

### 7.5. Cross-partition conflict: LWT bảo vệ sai key

~~~text
Uniqueness rule: one active subscription per customer

Incorrect model:
  subscriptions_by_random_id(subscription_id PRIMARY KEY)
  INSERT ... IF NOT EXISTS

Two clients use two different subscription IDs.
Both CAS operations succeed — on different partitions!
~~~

Nếu invariant đặt theo `customer_id`, phải có một **unique guard/lookup key** được mô hình hóa theo customer, với quy trình dữ liệu giữa guard và record được kiểm soát. LWT không tự biết hai partitions có ý nghĩa nghiệp vụ liên quan.

## 8. Vì sao thao tác có kết quả chưa biết?

### 8.1. Dòng thời gian của một lost acknowledgment

~~~text
Client            Coordinator             Replicas A/B/C
  |                    |                       |
  |---- CAS request -->|                       |
  |                    |---- PREPARE/PROPOSE -->|
  |                    |<--- Paxos accepted ----|
  |                    |----- COMMIT/LEARN ---->|
  |                    |<------- ACK -----------|
  |      X network / response timeout           |
  |<---- no definitive result                   |
  |                    |                       |
  | "unknown"          | mutation may exist    |
~~~

Nếu client không biết commit đã được học/ACK tới đâu, **timeout không đồng nghĩa rollback**. Cassandra không thể luôn chuyển kết quả bị mất thành một quyết định chắc chắn ở phía Java. Cũng không thể mặc định mọi timeout đều đã commit; có thể request thất bại trước bất kỳ accept/commit.

### 8.2. Ba điểm timeout khác nhau

| Thời điểm | Dấu hiệu Java có thể thấy | Diễn giải an toàn |
|---|---|---|
| Trước khi request tới server | Connection failure/driver deadline | **Chưa biết chắc** có coordinator nào nhận request trong một attempt đa node |
| Trong prepare/propose | Write timeout/CAS contention error | Consensus có thể chưa hoàn tất hoặc đã tiến xa; xem exception cụ thể |
| Sau khi quyết định và trong commit/learn/response | `CASWriteUnknownException`/timeout/network | Có thể đã áp dụng; **phải reconcile** |
| Sau khi server gửi `[applied]` nhưng response mất | Client timeout | Server có definitive result nhưng client không nhận |
| Server trả `[applied]=false` và Java nhận đủ | Conditional result | Attempt được giải quyết: điều kiện không thỏa |

**Đối với whole logical operation**, nếu một request từng được retry hoặc gửi qua nhiều coordinators, một lỗi ở attempt cuối **không** chứng minh những attempts trước đều chưa thực thi. Phải giữ request/operation ID xuyên các attempts và xác minh dữ liệu/ledger.

### 8.3. Chẩn đoán cụ thể các Java Driver exceptions

| Exception (Driver 4.x) | Bản chất | Hành động |
|---|---|---|
| `CASWriteUnknownException` | Server phản hồi CAS result ở trạng thái **unknown** | Mark UNKNOWN; đối soát theo operation ID |
| `WriteTimeoutException` | Server-side write thiếu ACK trước deadline; có `WriteType` | Không tự giả định rollback; kiểm type/replica/CL |
| `DriverTimeoutException` | Deadline phía driver hết, kể cả network/pool/queue | UNKNOWN nếu request có thể đã được gửi |
| `WriteFailureException` | Server phản hồi lỗi xử lý từ replica/coordinator | Phân loại write outcome theo chứng cứ, không replay mù |
| `UnavailableException` | Coordinator xác định không đủ live replicas cho CL | Chẩn đoán RF/CL/DC; nhớ các attempts trước có thể khác |
| `AllNodesFailedException` | Nhiều coordinator attempts thất bại | Đọc `getAllErrors()` per-node/per-attempt |
| `NoNodeAvailableException` | Không có coordinator usable để thử | Driver topology/contact points, khác result CAS |
| `InvalidQueryException` | Syntax/PK/IF/permission or schema constraint | Fail-fast; sửa CQL, không retry như contention |
| `UnauthorizedException` | Role/permissions thiếu | Sửa RBAC, không giảm CL |

Trong Java Driver 4.18.1 có class `com.datastax.oss.driver.api.core.servererrors.CASWriteUnknownException` mô tả trực tiếp trạng thái CAS không xác định. Xem [Javadoc CASWriteUnknownException](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/servererrors/CASWriteUnknownException.html) và [Retry policies](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/).

### 8.4. `WriteTimeoutException.getWriteType()` có giá trị gì?

Theo kiểu write được Cassandra báo, kỹ sư có thể phân biệt ordinary write, CAS-related write path hoặc các loại batch/counter, tùy version. Tuy nhiên kiểu đó chỉ cho biết **loại thao tác/cơ chế**, không phải chứng cứ state đã/không commit.

~~~java
catch (WriteTimeoutException e) {
    System.err.println("writeType=" + e.getWriteType());
    System.err.println("received=" + e.getReceived());
    System.err.println("blockFor=" + e.getBlockFor());
    // KHÔNG tự kết luận rollback.
}
~~~

`received/blockFor` là số replies so với yêu cầu ở pha lỗi; **không** phải số rows được tạo hay business transactions đã commit. Tránh suy “received=1/2 nghĩa chỉ 50% transaction đã ghi”.

### 8.5. Tại sao HTTP 504 không thể là “thất bại chắc chắn”?

Ứng dụng có thể trả 504 khi deadline hết, nhưng Cassandra đã commit. Nếu client thanh toán thấy 504 rồi gọi “Thanh toán” lần nữa với **ID mới**, hệ thống có thể tạo giao dịch thứ hai. API phải quy định:

- Giữ **idempotency key** cho cùng một ý định.
- Trả trạng thái `PENDING_VERIFICATION` hoặc lỗi có **request ID để tra cứu** khi chưa biết kết quả.
- Không trả “Đã thất bại, cứ bấm lại” nếu không có bằng chứng.
- Có kênh truy vấn **outcome status** hoặc reconciliation worker.

### 8.6. Đừng lấy read ngắn ngay sau timeout làm bằng chứng vĩnh viễn

~~~text
CAS timeout at T0
Read ONE at T0+10ms -> old revision
Server finishes pending commit at T0+20ms
Read LOCAL_QUORUM at T0+50ms -> new revision
~~~

Kết quả ở `ONE` ngay sau timeout có thể stale, và ngay cả read mạnh tại một thời điểm vẫn là **snapshot**, không chứng minh một attempt in-flight không thể hoàn tất sau đó. Một reconciliation design tốt kết hợp **serial read/appropriate CL, stable op ID, deadline, ownership và audit history**, không chỉ `Thread.sleep(100)`.

## 9. Một state machine kết quả ứng dụng đáng tin

### 9.1. Outcome khác transport status

~~~text
                  CAS request
                      |
            +---------+---------+
            |                   |
     Definitive result      No definitive result
            |                   |
     +------+-------+           v
     |              |    UNKNOWN_OUTCOME
 [applied]=true  [applied]=false   |
     |              |             v
 APPLIED       CONDITION_NOT_MET  RECONCILE
     |              |              |
     |        Re-evaluate rule     +--> Proof operation_id matches?
     |                             |      YES -> VERIFIED_APPLIED
     |                             |
     |                             +--> Different winner/version?
     |                             |      Need business/audit decision
     |                             |
     |                             +--> Insufficient evidence?
     |                                    MANUAL_REVIEW / retry policy
     v
Persist status/emit external effects according to business protocol
~~~

**Không có transition hợp lệ** `UNKNOWN_OUTCOME → FAILED` chỉ vì một read ở `ONE` chưa thấy row.

### 9.2. Đề xuất enum cho Java

~~~java
enum CasOutcome {
    APPLIED,               // Definitive server result: true
    CONDITION_NOT_MET,     // Definitive server result: false
    UNKNOWN_OUTCOME,       // No definitive result
    VERIFIED_APPLIED,      // Reconciled using op ID/version
    VERIFIED_CONFLICT,     // Another outcome established
    MANUAL_REVIEW          // Evidence still insufficient
}
~~~

`VERIFIED_CONFLICT` chỉ được dùng khi business protocol và lịch sử cho phép kết luận request hiện tại không thắng/không cần thực thi thêm; không suy từ một snapshot đã thay đổi sau đó nếu LWT cũ vẫn có thể từng applied.

### 9.3. Hợp đồng đầu vào một logical operation

~~~text
logical_operation_id = stable UUID
entity_id            = stable partition key
expected_revision    = n
target_revision      = n + 1
target_state         = CONFIRMED
deadline             = business end-to-end budget
normal_cl            = LOCAL_QUORUM
serial_cl            = LOCAL_SERIAL (nếu phạm vi local là đủ)
attempt_id           = unique per network attempt
~~~

Các giá trị `entity_id`, `expected_revision` và `target_state` phải **không đổi giữa các retries của cùng ý định**. Nếu sau conflict logic nghiệp vụ đổi expected revision, đó là **một quyết định nghiệp vụ mới**, không phải đơn thuần retry cùng request.

### 9.4. Outbox/idempotency và side effect

Khi LWT bảo vệ trạng thái `order=PAID` nhưng Java còn gọi dịch vụ gửi email, Kafka hoặc thanh toán:

~~~text
CAS order PAID at Cassandra
     |
     +--- ACK lost / app crash
     |
Email/payment message not delivered (or delivered twice)
~~~

LWT không bảo đảm atomic commit cho Cassandra và hệ thống bên ngoài. Cần thiết kế **outbox/inbox, idempotent consumer, saga/compensation, reconciliation** tương thích dữ liệu và khả năng event delivery. Không tuyên bố `INSERT IF NOT EXISTS` bảo đảm “exactly once” toàn hệ.

## 10. Thiết kế khóa và revision để tránh contention vô ích

### 10.1. Chọn đúng partition đại diện invariant

~~~sql
CREATE TABLE lwt_lab.account_state (
  account_id uuid PRIMARY KEY,
  status text,
  revision int,
  last_op_id uuid
);
~~~

Ở đây mỗi `account_id` là một partition đơn giản, nên hai writers của **cùng account** cạnh tranh một Paxos instance. Nếu invariant nằm ở “mỗi customer chỉ được một voucher còn hiệu lực”, phải bảo vệ một key **đại diện customer/voucher scope**, không phải một random event ID riêng cho mỗi attempt.

### 10.2. Optimistic revision fencing

~~~sql
UPDATE lwt_lab.account_state
SET status = 'CONFIRMED', revision = 12,
    last_op_id = 99999999-9999-9999-9999-999999999999
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF revision = 11;
~~~

Nguyên tắc:

- Chỉ chuyển `n → n+1` khi trạng thái hiện tại đúng điều kiện.
- Record `last_op_id` được ghi **cùng conditional mutation**.
- Nếu request timeout, dùng revision+op ID để đối soát.
- Nếu có nhiều writer, không tự động tăng expected revision sau khi `[applied]=false` mà chưa xét business rule.

`revision int` chỉ là ví dụ; hệ thống thật cần xử lý overflow, concurrent version governance và initial state. Một số nghiệp vụ dùng immutable UUID/ULID state token thay vì số đếm; tính duy nhất và chống ABA là trọng tâm.

### 10.3. ABA problem: giá trị quay lại như cũ

~~~text
T0 status = AVAILABLE, revision=10
T1 status = RESERVED,  revision=11
T2 status = AVAILABLE, revision=12

Client A đọc ở T0 và đợi lâu.
Đến T2, IF status='AVAILABLE' vẫn true,
nhưng thực thể đã trải qua một vòng RESERVE/RELEASE.
~~~

Nếu invariant quan tâm **lịch sử**, chỉ kiểm status có thể cho phép thao tác cũ hợp lệ nhầm. Thêm `revision`/state token và bắt mọi writer tăng version để ngăn ABA. Đây là lý do `IF revision = n` thường an toàn hơn `IF status = 'AVAILABLE'` đơn độc cho business transitions phức tạp.

### 10.4. Hot partition và contention throughput

~~~text
10,000 clients -> CAS on same account_id=GLOBAL_COUNTER
                   |
               Same Paxos scope
                   |
             Repeated conflicts
                   |
          High contention/latency
~~~

Sharding theo random key có thể giảm hotspot, **nhưng chỉ khi invariant được phân rã hợp lệ**. Nếu uniqueness phải toàn cục, sharding guard thành nhiều keys **sẽ đánh mất bảo đảm duy nhất** trừ khi có protocol phối hợp mới.

### 10.5. Tách “read model” khỏi “guard model” cẩn thận

~~~text
Guard table keyed by username:
  username -> owning_user_id (CAS IF NOT EXISTS)

Profile table keyed by user_id:
  user_id -> profile attributes (ordinary writes)
~~~

Hai tables/partitions có thể bất đồng nếu app crash giữa guard CAS và profile write. Cần trạng thái `RESERVED/CONFIRMED`, operation IDs, TTL/lease rules đã review và background reconciliation. Không biến guard table thành orphan reservation vĩnh viễn hoặc tự xoá guard mù khi thấy profile missing.

## 11. Retry policy: khi nào được phép thử lại?

### 11.1. Bảng quyết định cơ bản

| Kết quả | Retry ngay? | Hành động ưu tiên |
|---|---|---|
| `[applied]=true` | **Không** | Ghi nhận APPLIED và thực hiện bước nghiệp vụ tiếp |
| `[applied]=false`, expected revision stale | Không retry cùng điều kiện vô hạn | Trả conflict hoặc read+re-evaluate |
| `CASWriteUnknownException` | **Không blind retry** | Reconcile operation ID + version |
| `WriteTimeoutException`/`DriverTimeoutException` sau CAS | Không mặc nhiên | UNKNOWN, reconcile theo deadline |
| `UnavailableException` trước khi thực thi (attempt đơn) | Có thể sau khi cluster hồi phục, nhưng xét attempts trước | Kiểm RF/CL/topology |
| `InvalidQueryException` | **Không** | Sửa statement/schema/PK |
| `UnauthorizedException` | **Không** | Sửa RBAC |
| Transient network issue, operation có idempotency proof | Có giới hạn | Retry **cùng logical ID** + backoff + audit |
| Unknown sau hết ngân sách đối soát | Không chạy vô hạn | Escalate/manual review, bảo toàn evidence |

### 11.2. Vì sao `setIdempotent(true)` không phải thuốc thần?

Java Driver có retry policies và speculative execution dựa vào cờ idempotence. Một **conditional mutation** lặp lại có thể:

- Lần đầu `[applied]=true`, lần hai `[applied]=false`.
- Có side effects trong application dù mutation ở Cassandra giống nhau.
- Vấp race với actor khác và cho outcome khác theo thời điểm.

**Đừng đặt `setIdempotent(true)` cho mọi LWT một cách máy móc**. Chỉ bật khi đã chứng minh request, các thao tác sau kết quả, operation IDs và downstream effects đều an toàn để retry/duplicate. Mặc định bài học dùng `setIdempotent(false)` cho conditional writes và tự quản lý reconciliation.

### 11.3. Speculative execution tăng cạnh tranh

Nếu driver gửi **cùng LWT** tới coordinator khác khi request đầu chậm, có thể tạo **proposals chồng nhau** và làm contention cao hơn. Không bật speculative execution cho non-idempotent LWT. Ngay cả khi idempotency được chứng minh, cần đo `CASWrite.ContentionHistogram`, attempts và total cost trước khi áp dụng.

### 11.4. Backoff và jitter chỉ có ích khi có điều kiện

Ví dụ backoff cho **logical operation** đã được reconcile và biết có thể retry:

~~~text
attempt 1: 0ms
attempt 2: randomized 25-75ms
attempt 3: randomized 75-225ms
attempt 4: randomized 150-450ms
hard stop: 3 retries OR total budget 2s, whichever first
~~~

Các ngưỡng minh họa, không phải default Cassandra. Nếu condition đã false do actor khác thắng, backoff không đổi kết quả trừ khi business rule thực sự chờ state change; **không dùng retry để giành lại state trái invariant**.

### 11.5. Server timeout và client deadline

Những budget thường có:

- `cas_contention_timeout` trên Cassandra: giới hạn thời gian coordinator cố giải quyết contention.
- `write_request_timeout`/các server request timeouts: giới hạn chờ các pha/response.
- `basic.request.timeout`/statement `setTimeout` trong Java Driver: deadline phía client.
- API gateway/HTTP timeout: có thể ngắn hơn server/driver.
- Business operation deadline: thời hạn cuối cần trả kết quả hoặc đưa vào reconciliation.

Nếu HTTP timeout 800ms, Java driver timeout 3s và server vẫn xử lý, client có thể đã bỏ request trong khi CAS tiếp tục. **Tăng tất cả timeout không làm mất contention**, chỉ khiến queue/in-flight và latency tệ hơn khi bottleneck vẫn còn. Dùng một **deadline model** có phân pha cho response/reconciliation.

Trong Cassandra 4.1+, option được viết `cas_contention_timeout` (ví dụ `1000ms` ở cấu hình tham khảo), các bản cũ có `cas_contention_timeout_in_ms`. Đọc **effective config của đúng release**, không copy tên option cũ và giả định được chấp nhận. [Configuration reference](https://cassandra.apache.org/doc/4.1/cassandra/configuration/cass_yaml_file.html).

## 12. Metrics đặc thù cho LWT và cách đọc chúng

Cassandra có nhóm client request metrics `CASRead` và `CASWrite` trong `org.apache.cassandra.metrics.ClientRequest`; đây là nguồn quan trọng hơn việc chỉ nhìn read/write QPS tổng. Tham khảo [Apache Cassandra Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html).

### 12.1. Ma trận metric

| Scope | Metric | Ý nghĩa | Cảnh báo về diễn giải |
|---|---|---|---|
| `CASWrite` | `Latency` | Độ trễ các conditional writes ở coordinator | Không trực tiếp bằng HTTP p99 |
| `CASWrite` | `ContentionHistogram` | Histogram lượng contention trên các CAS writes | Phụ thuộc sample count và phiên bản |
| `CASWrite` | `ConditionNotMet` | Điều kiện CAS không thỏa | Thường **business conflict**, không phải server outage |
| `CASWrite` | `UnfinishedCommit` | Commit từ transaction còn dở được hoàn tất trên CAS write | Có thể gợi ý contention/recovery |
| `CASWrite` | `Timeouts` | CAS write timeouts | Có thể có unknown outcomes |
| `CASWrite` | `Failures` | Transaction write failures | Xem node logs/cause, không gộp với false |
| `CASWrite` | `Unavailables` | Không đủ replicas ở consistency liên quan | Phụ thuộc RF/DC/SCL/NCL |
| `CASRead` | `Latency` | Transactional reads | Khác normal `ReadLatency` |
| `CASRead` | `ContentionHistogram` | Contended serial reads | Có thể tăng do unfinished Paxos |
| `CASRead` | `UnfinishedCommit` | Unfinished commit được hoàn tất khi đọc | Không mặc định data corruption |
| Table | `CasPrepare`/`CasPropose` | Server latency của các pha Paxos | Tên/exposition tùy release |
| Driver node | `cql-messages`, errors, retries | Attempts và pressure lên node | Một logical request có thể tạo nhiều attempts |
| OS/JVM | GC, CPU, disk await, internode RTT | Nguồn latency ngoài contention | Metrics Paxos một mình chưa đủ |

Không phải mọi exporter đều tự động xuất tất cả series với đúng tên bảng này. `JMX MBean`, metric registry, alias Prometheus/Micrometer và scope có thể khác; **kiểm endpoint thật** trước khi viết alert.

### 12.2. `ConditionNotMet` cao có phải bug không?

Ví dụ API cấp username:

~~~text
30 writers cùng tranh "john"
1 writer [applied]=true
29 writers [applied]=false

High ConditionNotMet count,
but business invariant still protected.
~~~

Đếm 29 cases là **conflict** chứ không phải 29 Cassandra internal errors. Tuy nhiên nếu một request path lặp lại CAS cùng expected revision 1.000 lần/s sau một false, đây là **retry storm** do code ứng dụng. Cần theo dõi ratio `condition_not_met / total_cas_writes` theo query family, sample window và business intent.

### 12.3. Lấy tỷ lệ và phân bố theo thời gian

~~~text
cas_requests_per_sec = delta(CASWrite requests) / seconds
condition_false_rate = delta(ConditionNotMet) / CAS attempts
timeout_rate         = delta(CASWrite Timeouts) / CAS attempts
contention_p95       = percentile of ContentionHistogram (if exposed)
unknown_outcomes     = application-classified timeout/unknown count
~~~

Đây là **định nghĩa metric logic**, không phải PromQL chạy ngay: loại counter/timer và labels thực tế phụ thuộc reporter. Nếu Cassandra server counter reset sau restart, dùng `rate`/`increase` xử lý reset và ghi uptime; không lấy raw totals hai node khác uptime để suy node nào có workload cao hơn.

### 12.4. Những chỉ số ngoài Paxos không được bỏ qua

~~~text
Logical LWT calls/s
  -> driver request attempts, pool.in-flight, retries
  -> coordinator CASWrite latency, ConditionNotMet, contention
  -> per-node GC/CPU, disk/commitlog, network RTT
  -> table read/write latency and compaction backlog
  -> business outcomes + downstream duplicate detections
~~~

Nếu `CASWrite.Latency` tăng nhưng `ContentionHistogram` không đổi, xem disk/GC/network/throttling hoặc đang thay phân phối keys/CL. Nếu contention tăng trên một partition nhưng cluster CPU bình thường, global CPU graph có thể che **hot-key serialization**.

### 12.5. Dòng thời gian có event markers

~~~text
10:00 baseline (2 CAS/s per key; false rate 2%)
10:05 rollout app version V2
10:06 contenders/key rises to 50
10:07 contention histogram shifts upward
10:08 client p99 rises, CASWrite timeouts increase
10:09 API 504 + reconciliation backlog grows
10:10 HOLD rollout and throttle writes on hot key
~~~

Đây là **dữ liệu giả minh họa**, không phải kết quả của một cluster thật. Cần đồng bộ mốc UTC giữa app, driver, coordinator và máy host khi làm incident report.

## 13. Những giả thuyết gây contention cần kiểm lần lượt

### 13.1. Một partition quá nóng

Một account hoặc order ID được nhiều clients thử cập nhật cùng lúc, đặc biệt nếu tất cả writers lặp CAS không có jitter. Xác minh bằng **key grouping an toàn** (hash/opaque bucket IDs, không log PII), sample per-key contender counts, `ConditionNotMet` và contention histogram.

### 13.2. Quá nhiều distinct operations nhưng bị dồn vào một guard key

Ví dụ service toàn cầu có một `global_sequence` partition để cấp ID tăng dần. Cả hàng nghìn writers tranh một Paxos instance; tăng số nodes không tự nhân throughput của **một partition**. Giải pháp có thể là cấp dải ID/segment, partition theo nghiệp vụ hoặc sử dụng ID phân tán, nhưng chỉ khi uniqueness/order requirements cho phép.

### 13.3. Client timeout ngắn hơn thực tế WAN

LWT gồm nhiều pha; `SERIAL` toàn cluster nhiều DC có thể có round-trip latency lớn hơn `LOCAL_SERIAL`. Nếu HTTP deadline nhỏ hơn thời gian xử lý hợp lệ, unknown outcomes tăng mà Cassandra chưa chắc có lỗi. Phải xét **SCL/NCL, DC, network RTT** và business deadline cùng nhau.

### 13.4. Quorum liveness giảm hoặc một replica chậm

Gossip `UN` không đảm bảo replica trả PREPARE/PROPOSE đúng hạn. Disk await, GC pause, internode queue và băng thông WAN có thể làm một quorum không kịp thời gian dù nodes đều UP. Một số lỗi là `CASWriteUnknownException`/timeout chứ không phải `ConditionNotMet`.

### 13.5. Driver retries/speculation vô tình nhân Paxos proposals

Nếu ứng dụng đánh dấu mọi conditional statement idempotent và bật aggressive retry/speculative execution, một logical request có thể tạo nhiều CAS attempts gây contention mới. So `client logical requests/s` với `node cql-messages/s` và driver retries/speculation; không chỉ nhìn QPS từ HTTP.

### 13.6. Workload generator giả lập sai

Benchmark LWT chỉ 100 hot keys có thể báo contention rất cao trong khi production có hàng triệu independent accounts. Ngược lại, generator tạo UUID mới cho mọi request sẽ báo contention gần 0 dù production thường có bursts trên cùng order ID. Benchmark phải có **distribution keys, contenders/key, DC routing và SCL/NCL** như production.

### 13.7. Hot condition bị false liên tục nhưng không tranh ballot

Nếu 10 nghìn requests kiểm `IF revision=1` trên row đang ở revision=50, chúng có thể trả false thường xuyên. `ConditionNotMet` rất cao **không tự chứng minh Paxos proposals thật sự đang va chạm mạnh**; phải xem `ContentionHistogram` và latency.

## 14. Bộ lệnh quan sát an toàn trước khi thay cấu hình

### 14.1. Kiểm trạng thái ring

~~~bash
nodetool status
nodetool describecluster
nodetool tpstats
nodetool netstats
nodetool compactionstats
nodetool tablestats lwt_lab.account_state
~~~

Các lệnh `nodetool` cần JMX permissions, và command availability/output khác nhau theo Cassandra version. Chúng chủ yếu là **read-only diagnostics**; không dùng `stop`/`compact`/`flush`/`repair` như “fix Paxos contention” tự động.

### 14.2. Kiểm replication và topology bằng CQL

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'lwt_lab';

SELECT cluster_name, data_center, host_id,
       release_version
FROM system.local;
~~~

Lab `SimpleStrategy RF1` không đủ kiểm hành vi SERIAL/LOCAL_SERIAL đa node. Production nhiều DC dùng `NetworkTopologyStrategy` với RF map theo DC; cần xác minh **actual natural replicas** cho partition đang contention (token/ring/DC/rack) để tránh đo nhầm node.

### 14.3. Read/write oracle không thay metrics

~~~sql
SELECT status, revision, last_op_id
FROM lwt_lab.account_state
WHERE account_id = 11111111-1111-1111-1111-111111111111;
~~~

Một SELECT trên đúng row giúp thấy state hiện tại, nhưng **không** cung cấp lịch sử mọi CAS attempts. Để phân xử unknown, cần expected op ID, revision, CL, thời điểm, actor và ledger/audit khi nghiệp vụ có intermediate transitions.

### 14.4. Đừng sửa trực tiếp Paxos internals

Cassandra có dữ liệu hệ thống phục vụ Paxos (tùy phiên bản gồm `system.paxos` hoặc cơ chế mới). Những bảng/internal states này **không phải API để DBA cập nhật thủ công**. Không truncate/delete/sửa ballot, không copy system tables giữa nodes và không áp “reset Paxos” từ một blog không khớp phiên bản. Nếu nghi corrupt/incomplete Paxos state, bảo toàn logs và escalates cho DBA theo vendor/release-specific recovery procedure.

## 15. So sánh LWT với một số cơ chế khác

| Cơ chế | Đúng cho vấn đề | Không giải quyết |
|---|---|---|
| Normal write at `LOCAL_QUORUM` | Ghi nhiều replicas với mức ACK phù hợp | Atomic compare-and-set khi concurrent writers |
| LWT `IF revision=n` | Optimistic atomic conditional transition trong scope hỗ trợ | Cross-system exactly once |
| `INSERT IF NOT EXISTS` | Chống tạo hai rows trên **cùng key** | Unique condition trải nhiều unrelated partitions |
| Kafka partition ordering | Thứ tự tiêu thụ trong một Kafka partition | CAS nếu writers trực tiếp vào DB bỏ qua Kafka |
| Actor/single-writer per entity | Giảm contention, rõ ownership | Crash/rebalance/out-of-order vẫn cần fencing |
| Idempotency key + ledger | Đối soát duplicate attempts | Không tự bảo vệ state transition nếu thiếu CAS/atomicity |
| Outbox/inbox + saga | Liên kết side effects bất đồng bộ | Một ACID transaction chung cho mọi hệ |
| SQL transaction/row lock (khác DB) | Các yêu cầu transactional đặc thù | Không tự suy áp dụng sang Cassandra CQL |

**Không có một giải pháp đơn lẻ** thay cho thiết kế invariant/end-to-end retry. Chọn LWT khi việc bảo đảm điều kiện đồng thời là thiết yếu, và đặt câu hỏi: “có thể giảm các writers cùng tranh một partition mà vẫn giữ invariant không?”

## 16. Lab A — CQL: `IF NOT EXISTS`, CAS revision và `[applied]`

### 16.1. Môi trường và giới hạn

- Cassandra 4.1 hoặc 5.0 **một node lab**, `cqlsh` đã kết nối.
- Chỉ dùng namespace `lwt_lab` mới, không chạy `DROP`/`TRUNCATE` trên keyspace thuộc người khác.
- `SimpleStrategy` RF1 và `CONSISTENCY ONE` phù hợp một node, **không** chứng minh Paxos availability khi một node trong RF3 DOWN.
- Trình tự đơn thread cho kết quả có thể tái hiện; thí nghiệm hai writers ở mục 17 đòi concurrent clients riêng.
- Thực hành **không gây lỗi mạng nhân tạo**; UNKNOWN_OUTCOME sẽ được giải thích và mô phỏng ở tầng application state, không làm hỏng Cassandra host.

### 16.2. Tạo table theo entity key

~~~sql
CREATE KEYSPACE IF NOT EXISTS lwt_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS lwt_lab.account_state (
  account_id uuid PRIMARY KEY,
  status text,
  revision int,
  last_op_id uuid
);

CONSISTENCY ONE;
SERIAL CONSISTENCY SERIAL;
~~~

**Cần kiểm schema thực** nếu chạy lại lab: `IF NOT EXISTS` không xác nhận table hiện hữu có đúng columns/types. Với multi-node production phải dùng NTS RF và CL đúng scope, không dùng keyspace RF1 để đo quorum.

### 16.3. Tạo entity lần đầu

~~~sql
INSERT INTO lwt_lab.account_state
  (account_id, status, revision, last_op_id)
VALUES (
  11111111-1111-1111-1111-111111111111,
  'PENDING',
  1,
  22222222-2222-2222-2222-222222222222
)
IF NOT EXISTS;
~~~

Nếu entity/PK chưa tồn tại:

~~~text
 [applied]
-----------
      True
~~~

Nếu chạy lại cùng lệnh khi row đã tồn tại:

~~~text
 [applied] | ... current values ...
-----------
     False
~~~

**False lúc chạy lại không đồng nghĩa lỗi hệ thống.** Nếu lần đầu client đã timeout nhưng row có `last_op_id=2222...` cùng revision/state, đó là evidence operation tạo row đã thành công. Nếu row thuộc actor/ID khác, cần xử lý conflict hoặc đối soát history.

### 16.4. Đọc trạng thái và điều kiện đã thiết lập

~~~sql
SELECT status, revision, last_op_id
FROM lwt_lab.account_state
WHERE account_id = 11111111-1111-1111-1111-111111111111;
~~~

Kỳ vọng ban đầu: `PENDING`, revision `1` và operation ID tạo row. Không dùng `SELECT COUNT(*)` toàn bảng hoặc `ALLOW FILTERING` để chẩn đoán một account — biết primary key là điều kiện quan trọng.

### 16.5. Client A chuyển từ revision 1 sang 2

~~~sql
UPDATE lwt_lab.account_state
SET status = 'CONFIRMED',
    revision = 2,
    last_op_id = 33333333-3333-3333-3333-333333333333
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF revision = 1;
~~~

Kỳ vọng `[applied]=true` nếu chưa có actor nào đã cập nhật row. Sau đó:

~~~sql
SELECT status, revision, last_op_id
FROM lwt_lab.account_state
WHERE account_id = 11111111-1111-1111-1111-111111111111;
~~~

Kỳ vọng `CONFIRMED`, `2`, `3333...`. Đây là **successful CAS transition**, không phải normal blind upsert.

### 16.6. Client B với expected revision cũ

~~~sql
UPDATE lwt_lab.account_state
SET status = 'CANCELLED',
    revision = 2,
    last_op_id = 44444444-4444-4444-4444-444444444444
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF revision = 1;
~~~

Kỳ vọng `[applied]=false`; **không** ghi đè state của client A. Đây là bản chất của optimistic concurrency:

~~~text
A: expected rev 1 -> applied true -> current rev 2
B: expected rev 1 -> applied false (stale expectation)
~~~

Nếu app nhận false, client B **không được tự động đổi expected revision thành 2 và ghi CANCELLED** nếu business rule không cho phép đảo CONFIRMED → CANCELLED.

### 16.7. CAS với nhiều conditions

~~~sql
UPDATE lwt_lab.account_state
SET status = 'FULFILLED',
    revision = 3,
    last_op_id = 55555555-5555-5555-5555-555555555555
WHERE account_id = 11111111-1111-1111-1111-111111111111
IF revision = 2 AND status = 'CONFIRMED';
~~~

Kỳ vọng true khi state còn như bước trước; nếu một actor khác đã chuyển state hoặc tăng revision, false là đúng. Luôn dùng **full partition/primary key** theo yêu cầu CQL.

### 16.8. Không dùng normal UPDATE trộn vào protocol

~~~sql
-- Đây là lệnh bình thường, KHÔNG dùng trong bài test invariant:
-- UPDATE lwt_lab.account_state
-- SET status = 'PENDING', revision = 1
-- WHERE account_id = 11111111-1111-1111-1111-111111111111;
~~~

Nếu một writer bỏ qua LWT, regression test phải phát hiện **vi phạm protocol**, không kết luận Cassandra “Paxos bị lỗi”. Mọi writer cần dùng cùng revision fencing hoặc actor/serialization được review.

### 16.9. Thực hành “không thấy ACK”

Không cần làm mất mạng để học logic unknown. Hãy tưởng tượng câu `UPDATE ... IF revision=1` của client A đã được server xử lý nhưng ứng dụng **không nhận được response**. Sau đó chạy query đọc trạng thái:

~~~sql
SELECT status, revision, last_op_id
FROM lwt_lab.account_state
WHERE account_id = 11111111-1111-1111-1111-111111111111;
~~~

Nếu `last_op_id` là của A và revision/state đúng, có chứng cứ A đã applied **ở một thời điểm**, miễn là các actor không được phép sửa `last_op_id` tùy ý. Nếu row đã chuyển tiếp sang op khác, một snapshot **không đủ** tái dựng lịch sử. Cần audit ledger/historical events hoặc manual investigation.

**Đây là bài tập suy luận, không phải fault-injection test đã chạy.**

## 17. Lab B — Hai client cạnh tranh: kiểm `[applied]` đúng cách

### 17.1. Dùng hai cửa sổ cqlsh riêng

Trên **một cluster lab**, chạy đồng thời hai `cqlsh` sessions với `CONSISTENCY ONE` và `SERIAL CONSISTENCY SERIAL`. Dùng cùng `account_id` và cùng `expected_revision=10` nhưng `target_status` và `last_op_id` khác nhau.

Seed một row lab riêng:

~~~sql
INSERT INTO lwt_lab.account_state
  (account_id, status, revision, last_op_id)
VALUES (
  aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa,
  'READY', 10,
  00000000-0000-0000-0000-000000000010
)
IF NOT EXISTS;
~~~

Nếu row đã tồn tại từ test cũ, dùng `account_id` mới do test sở hữu. **Không** reset bằng `TRUNCATE` hoặc normal overwrite mà bỏ qua LWT state.

### 17.2. Writer A (terminal 1)

~~~sql
UPDATE lwt_lab.account_state
SET status='OWNED_BY_A',
    revision=11,
    last_op_id=aaaaaaaa-0000-0000-0000-000000000001
WHERE account_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
IF revision=10;
~~~

### 17.3. Writer B (terminal 2)

~~~sql
UPDATE lwt_lab.account_state
SET status='OWNED_BY_B',
    revision=11,
    last_op_id=bbbbbbbb-0000-0000-0000-000000000002
WHERE account_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
IF revision=10;
~~~

Nếu cả hai truy vấn thật sự chạy và hoàn tất bình thường, **chỉ một** có thể applied=true trong mô hình đã thống nhất điều kiện; truy vấn còn lại có thể trả false. Nếu chúng xen vào nhau phức tạp và deadline quá thấp, một trong hai có thể trả **timeout/unknown**, nên không được assert “luôn có đúng một true và một false” trong test fault-injection chưa kiểm control.

### 17.4. Xác minh kết quả

~~~sql
SELECT status, revision, last_op_id
FROM lwt_lab.account_state
WHERE account_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa;
~~~

Kỳ vọng `revision=11` và status/op ID của một trong hai actor **trong test chỉ có hai writers**, không có background writes. Nếu cả hai clients nhận true cho hai CAS khác nhau cùng expected revision 10, đây là kết quả bất thường phải kiểm exact request IDs, schema, primary key, SCL/normal CL, scope nhiều DC, writers bỏ qua LWT và node versions trước khi tuyên bố data corruption.

### 17.5. Contention thật và sequential conflict khác nhau

Nếu bạn chạy A xong rồi mới chạy B, thấy false ở B chỉ là **stale revision/business conflict**, chưa chứng minh có Paxos contention (proposals cùng lúc). Muốn đo contention histogram cần **đồng thời** gửi nhiều proposals tới **cùng key** trong staging có giám sát, không chạy một script nối tuần tự rồi đọc `ConditionNotMet` làm bằng chứng contention giao thức.

### 17.6. Không dựng “lost ACK” trên production

Không ngắt mạng/iptables, kill coordinator hoặc giảm timeout production để ép UNKNOWN_OUTCOME. Khi học logic, dùng mock fault ở application/client/test harness. Khi cần kiểm lỗi hạ tầng thật, thực hiện ở dedicated staging với RF/CL và monitor/recovery plan rõ ràng.

## 18. Lab C — Java Driver 4.x: ghi LWT và đọc `wasApplied()`

### 18.1. Điều kiện chạy

- Java 17 và Apache Java Driver 4.x, Cassandra single-node lab RF1 ở `127.0.0.1:9042`.
- `datacenter1` trong code **phải thay bằng DC thực** từ `system.local.data_center` nếu khác.
- Chương trình tự tạo `lwt_lab`/`account_state` với `IF NOT EXISTS`; chỉ chạy trên **lab disposable** và xác nhận table schema không bị một test khác thay đổi.
- Dùng operation ID mới mỗi logical operation; **không** tạo operation ID mới khi chỉ retry cùng ý định sau timeout.
- Không bật speculative execution/retry tự động cho LWT trong ví dụ.

Gradle Kotlin DSL minh họa:

~~~kotlin
dependencies {
    implementation("org.apache.cassandra:java-driver-core:4.18.1")
}
~~~

Đây là hướng dẫn dependency, **không phải yêu cầu sửa Gradle repository**. Code bên dưới minh họa các API của driver 4.18.x; nên pin driver/JDK/Cassandra versions của môi trường thực và thử compile trong vòng QA riêng.

### 18.2. Chương trình Java 17 độc lập

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.AllNodesFailedException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.CASWriteUnknownException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;
import java.net.InetSocketAddress;
import java.time.Duration;
import java.util.UUID;

public final class LwtOutcomeLab {
    private LwtOutcomeLab() {}

    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            session.execute(
                "CREATE KEYSPACE IF NOT EXISTS lwt_lab " +
                "WITH replication = {'class':'SimpleStrategy', " +
                "'replication_factor':1}");

            session.execute(
                "CREATE TABLE IF NOT EXISTS lwt_lab.account_state (" +
                "account_id uuid PRIMARY KEY, status text, " +
                "revision int, last_op_id uuid)");

            if (!session.checkSchemaAgreement()) {
                throw new IllegalStateException(
                    "Schema agreement required in lab");
            }

            // Một account mới cho lần chạy này.
            UUID accountId = UUID.randomUUID();
            UUID createOpId = UUID.randomUUID();
            UUID confirmOpId = UUID.randomUUID();

            PreparedStatement insert = session.prepare(
                "INSERT INTO lwt_lab.account_state " +
                "(account_id, status, revision, last_op_id) " +
                "VALUES (?, ?, ?, ?) IF NOT EXISTS");

            PreparedStatement casUpdate = session.prepare(
                "UPDATE lwt_lab.account_state " +
                "SET status=?, revision=?, last_op_id=? " +
                "WHERE account_id=? IF revision=?");

            PreparedStatement read = session.prepare(
                "SELECT status, revision, last_op_id " +
                "FROM lwt_lab.account_state WHERE account_id=?");

            BoundStatement create = insert.bind(
                    accountId, "PENDING", 1, createOpId)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setSerialConsistencyLevel(DefaultConsistencyLevel.SERIAL)
                .setIdempotent(false)
                .setTimeout(Duration.ofSeconds(3));

            ResultSet created = session.execute(create);
            if (!created.wasApplied()) {
                throw new IllegalStateException(
                    "Unexpected conflict on fresh lab account");
            }

            BoundStatement transition = casUpdate.bind(
                    "CONFIRMED", 2, confirmOpId, accountId, 1)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setSerialConsistencyLevel(DefaultConsistencyLevel.SERIAL)
                .setIdempotent(false)
                .setTimeout(Duration.ofSeconds(3));

            try {
                ResultSet outcome = session.execute(transition);
                if (outcome.wasApplied()) {
                    System.out.println("APPLIED");
                } else {
                    System.out.println("CONDITION_NOT_MET");
                }
            } catch (CASWriteUnknownException
                   | WriteTimeoutException
                   | DriverTimeoutException e) {
                // Không retry với operation ID mới.
                System.err.println(
                    "UNKNOWN_OUTCOME type=" +
                    e.getClass().getSimpleName());
                // Trong một hệ thật: ghi status UNKNOWN vào
                // durable operation ledger và chạy reconciliation.
                return;
            } catch (AllNodesFailedException e) {
                System.err.println(
                    "COORDINATOR_FAILURES; outcome needs classification");
                e.getAllErrors().forEach((node, errors) -> {
                    for (Throwable failure : errors) {
                        System.err.printf(
                            "node=%s cause=%s%n",
                            node.getHostId(),
                            failure.getClass().getSimpleName());
                    }
                });
                // Có thể một attempt đã gửi/commit trước khi lỗi;
                // không tự replay.
                return;
            }

            BoundStatement readBack = read.bind(accountId)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true)
                .setTimeout(Duration.ofSeconds(3));

            Row row = session.execute(readBack).one();
            if (row == null
                    || !"CONFIRMED".equals(row.getString("status"))
                    || row.getInt("revision") != 2
                    || !confirmOpId.equals(row.getUuid("last_op_id"))) {
                throw new AssertionError(
                    "LWT applied response/data oracle mismatch");
            }

            System.out.println("DATA_ORACLE_PASS");

            // Chỉ để minh họa một lần gọi CAS lặp lại khi
            // lần đầu đã được xác nhận áp dụng.
            ResultSet repeated = session.execute(transition);
            if (repeated.wasApplied()) {
                throw new AssertionError(
                    "Old revision must no longer match");
            }
            System.out.println("REPEAT_CONDITION_NOT_MET");
        }
    }
}
~~~

### 18.3. Đọc output chính xác

~~~text
APPLIED
DATA_ORACLE_PASS
REPEAT_CONDITION_NOT_MET
~~~

Kết quả này là **kỳ vọng khi lab khỏe và chỉ một writer**. Nếu có timeout:

~~~text
UNKNOWN_OUTCOME type=CASWriteUnknownException
~~~

hoặc timeout/aggregate error tương ứng. Chương trình chỉ **phân loại và dừng**, chưa triển khai durable operation ledger; đó là phạm vi của mục 19. Không được đọc log `UNKNOWN_OUTCOME` rồi tự động gửi một CAS mới ở client HTTP với UUID khác.

### 18.4. Một hạn chế có chủ đích

`readBack` dùng `ONE` vì đây là lab **một node RF1** và đã có ACK applied; không được suy diễn rằng một read `ONE` đủ đối soát unknown outcome của cluster RF3 nhiều DC. Trong production, reconciliation read phải tuân theo hợp đồng normal/serial CL, data model và giới hạn read visibility của commit phase.

### 18.5. Không sinh ID trong vòng retry

**Sai:**

~~~java
for (int attempt = 0; attempt < 5; attempt++) {
    UUID opId = UUID.randomUUID(); // Mỗi lần là một ý định khác!
    // send CAS; catch timeout; retry blindly
}
~~~

**Đúng về mặt định danh:**

~~~java
UUID opId = UUID.randomUUID(); // Một lần cho logical operation.
for (int attempt = 0; attempt < maxAttempts; attempt++) {
    // Nếu policy cho phép retry, dùng LẠI opId và expected revision.
    // Sau unknown phải reconcile trước; không loop tự phát.
}
~~~

Đây chỉ là **skeleton giải thích ownership của ID**, chưa phải retry implementation. Với một CAS đã timeout, ứng dụng cần thực hiện reconciliation; không lấy skeleton này làm bằng chứng retry an toàn.

## 19. Đối soát UNKNOWN_OUTCOME: thuật toán và giới hạn

### 19.1. Kết quả đối soát tối thiểu

Một reconciler phải nhận `entityId`, `logicalOperationId`, `expectedRevision`, `targetRevision`, `expectedState`, serial/normal CL và deadline. Nó chỉ có thể chuyển UNKNOWN thành VERIFIED_APPLIED khi có **evidence đáng tin**, ví dụ current row có `last_op_id` đúng và `revision`/state đúng, trong một protocol không cho phép actor sửa op ID tùy tiện.

### 19.2. Read ở serial consistency khi cần

Trong `cqlsh`, có thể dùng:

~~~text
cqlsh> CONSISTENCY SERIAL;
~~~

Sau đó:

~~~sql
SELECT status, revision, last_op_id
FROM lwt_lab.account_state
WHERE account_id = 11111111-1111-1111-1111-111111111111;
~~~

Serial read có thể cần thiết để hoàn tất pending Paxos commit và quan sát transactional state theo phạm vi serial consistency. Nó **không** tự tái hiện lịch sử sau khi một writer khác đã thay state. Chỉ chạy có kiểm soát, vì serial read đắt hơn normal read. [Cassandra cqlsh SERIAL consistency](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html).

### 19.3. Java helper đọc để đối chiếu

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.util.UUID;

static CasOutcome checkOperation(
        CqlSession session,
        PreparedStatement readPrepared,
        UUID entityId,
        UUID expectedOpId,
        int targetRevision,
        String targetStatus) {

    BoundStatement serialRead = readPrepared.bind(entityId)
        .setConsistencyLevel(DefaultConsistencyLevel.SERIAL)
        .setTimeout(Duration.ofSeconds(3))
        .setIdempotent(true);

    Row row = session.execute(serialRead).one();
    if (row != null
            && expectedOpId.equals(row.getUuid("last_op_id"))
            && row.getInt("revision") == targetRevision
            && targetStatus.equals(row.getString("status"))) {
        return CasOutcome.VERIFIED_APPLIED;
    }

    // Không đủ evidence để kết luận "definitely not applied".
    return CasOutcome.UNKNOWN_OUTCOME;
}
~~~

Đoạn helper **phụ thuộc** `CasOutcome` enum trong mục 9 và `CqlSession` import từ Lab C; là minh họa logic đối soát, không phải toàn bộ recovery service. Với multi-DC nên chọn serial read scope theo **hợp đồng toàn hệ**, không dùng `LOCAL_SERIAL` rồi công bố global result. Nếu đọc lỗi/timeout, kết luận vẫn UNKNOWN và thu root cause.

### 19.4. Vì sao cần audit ledger nếu row có thể chuyển tiếp?

~~~text
T0 op A: PENDING -> CONFIRMED, revision=2, last_op=A
T1 op B: CONFIRMED -> FULFILLED, revision=3, last_op=B
T2 reconciler của A đọc:
      status=FULFILLED, rev=3, last_op=B
~~~

Reconciler **không thể** kết luận A chưa từng chạy: A có thể đã thành công, sau đó B thực hiện bước tiếp. Nếu nghiệp vụ đòi kết luận chính xác cả khi có multiple sequential transitions, duy trì một **operation-status ledger/audit trail** hoặc event history đã thiết kế consistency/idempotency. Có thể lưu outcome trong bảng theo operation ID, nhưng cập nhật giữa account state và ledger ở **hai partitions** không tự atomic — cần protocol phù hợp để tránh hai nguồn chứng cứ mâu thuẫn.

### 19.5. Reconciliation có deadline và outcome rõ

~~~text
UNKNOWN
  |
  | read/serial read within bounded budget
  v
Entity state matches op ID and expected version?
  | YES                 | NO
  v                     v
VERIFIED_APPLIED    Check operation ledger/history
                       |
                +------+-------+
                |              |
             Proof          Not enough proof
                |              |
       VERIFIED_CONFLICT   MANUAL_REVIEW /
       or APPLIED          PENDING_VERIFICATION
~~~

Nếu system có concurrent writes sau unknown, proof thường đòi audit trail, không chỉ current row. Đặt **max attempts/total deadline**, giới hạn query rate và giữ tracing để reconciler không tạo workload storm đúng lúc cluster đang yếu.

### 19.6. Exactly-once business outcome không đến từ DB một mình

Cho dù Cassandra đã xác nhận CAS APPLIED, HTTP response có thể mất. Cho dù ledger đã ghi SUCCESS, Kafka consumer có thể nhận event hai lần. Hợp đồng hệ thống nên ghi rõ:

1. Idempotency key được **client giữ nguyên** khi retry cùng ý định.
2. Operation ID và expected revision được ghi cùng CAS state khi khả thi.
3. Có endpoint/worker query outcome.
4. Downstream side effects có deduplication/inbox/outbox.
5. Lịch sử và trạng thái pending được retain đủ lâu để đối soát.
6. Có thủ tục manual review cho trường hợp outcome không thể chứng minh.

**Không** tự tạo một `INSERT INTO operation_log` sau CAS rồi gọi hai statements ở hai partitions là một atomic transaction.

## 20. Thiết kế integration test và fault test cho LWT

### 20.1. Ma trận test cần có

| Test | Fixture | Kết quả mong đợi | Chứng minh |
|---|---|---|---|
| Insert new key `IF NOT EXISTS` | RF1 lab | `[applied]=true` | Conditional insert thực thi |
| Duplicate insert same key | RF1 lab | `[applied]=false` | Không tạo row thứ hai cùng PK |
| Two writers expected revision n | Multi-thread lab | Tối đa một definitive applied=true | Optimistic CAS bảo vệ state |
| CAS with stale revision | RF1 lab | False + current revision | Business conflict, không phải timeout |
| Lost ACK after commit | Mock fault trong app | UNKNOWN → verified bằng op ID | Không đánh false là failed |
| Timeout before commit | Mock fault trong app | UNKNOWN, không auto replay | Cần reconciliation |
| Old writer returns after new revision | Lab concurrency | Không áp stale mutation | Revision fencing |
| Two writers dùng random keys khác nhau | Lab | Cả hai có thể true | Invariant phải cùng guard key |
| Normal writer bỏ qua CAS | Dedicated lab | Protocol có thể bị vi phạm | Phải enforce toàn bộ actors |
| RF3 + `LOCAL_QUORUM`/`LOCAL_SERIAL` | Multi-node real cluster | Correct result at declared CL | Replica/quorum semantics |
| One replica slow/partitioned | Dedicated fault staging | Timeout/unknown/recovery phân loại | Availability và RTO |
| Multi-DC LOCAL_SERIAL vs SERIAL | Real multi-DC lab | Scope đúng contract | Không suy global order từ local |

**Không bắt mọi pull request chạy chaos cluster 6 nodes** nếu CI không hỗ trợ; nhưng test RF1 đơn node chỉ chứng minh **logic cú pháp/conditional semantics**, không chứng minh khả năng chịu lỗi/quorum/replica race trong production.

### 20.2. JUnit 5: kiểm logic lost ACK bằng fake store

Ví dụ pure Java này **không giả lập Paxos**. Nó chỉ kiểm ứng dụng **không đánh một thao tác đã được áp dụng thành failed** khi kết quả bị mất.

~~~java
import java.util.UUID;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

final class UnknownOutcomeStateMachineTest {
    static final class ResponseLost extends RuntimeException {}

    static final class FakeAccount {
        int revision = 1;
        UUID lastOpId;

        // Chỉ là fake CAS atomic trên một đối tượng Java.
        synchronized boolean compareAndSet(
                int expected, int target, UUID operationId) {
            if (revision != expected) {
                return false;
            }
            revision = target;
            lastOpId = operationId;
            return true;
        }
    }

    @Test
    void lostReplyCannotBeTreatedAsDefiniteFailure() {
        FakeAccount store = new FakeAccount();
        UUID opId = UUID.randomUUID();

        assertThrows(ResponseLost.class, () -> {
            boolean applied = store.compareAndSet(1, 2, opId);
            assertTrue(applied);
            throw new ResponseLost(); // ACK bị mất sau commit
        });

        // Một retry với expected=1 sẽ thấy false, vì
        // attempt trước ĐÃ cập nhật revision=2.
        assertFalse(store.compareAndSet(1, 2, opId));

        // Reconciliation dựa trên operation ID, không
        // dựa vào kết quả false của attempt thứ hai.
        assertEquals(2, store.revision);
        assertEquals(opId, store.lastOpId);
    }

    @Test
    void twoDistinctWritersCannotBothWinOneRevision() {
        FakeAccount store = new FakeAccount();
        UUID opA = UUID.randomUUID();
        UUID opB = UUID.randomUUID();

        boolean a = store.compareAndSet(1, 2, opA);
        boolean b = store.compareAndSet(1, 2, opB);

        assertTrue(a);
        assertFalse(b);
    }
}
~~~

**Giới hạn:** Đây là deterministic fake store với `synchronized`; không test consistency của Cassandra, driver retry hay mạng. Giá trị của nó là đưa **reconciliation logic** vào unit test để một developer không vô tình đổi `UNKNOWN_OUTCOME` thành `FAILED`.

### 20.3. Integration test trên Cassandra thật

Khi có dedicated Cassandra lab:

1. Tạo một entity ID mới trong table lab.
2. Seed revision n bằng LWT, xác nhận `[applied]=true`.
3. Cho hai client threads gọi cùng conditional update `IF revision=n`, mỗi thread dùng op ID khác.
4. Dùng barrier/latch để bắt đầu gần đồng thời; mỗi thread log response/exception riêng.
5. Nếu hai clients đều nhận **definitive response**, assert **không quá một** `wasApplied=true`.
6. Đọc state với CL phù hợp, assert revision n+1 và op ID của actor thắng.
7. Nếu có timeout/unknown, **không** assert “một true một false” mù; lưu unknown, thực hiện reconciliation, kiểm invariant.
8. Sau test, quan sát CAS contention/timeout counters và node GC/disk/network.

Trên RF3, chọn đúng serial scope; các client không được **tự động** switch SCL từ `SERIAL` sang `LOCAL_SERIAL` giữa các attempts. Hãy ghi test coverage theo DC/token/RF và idempotency mode.

### 20.4. Nguồn gây flakiness trong tests

| Hiện tượng | Nguyên nhân | Cách chống |
|---|---|---|
| Row từ test cũ còn tồn tại | ID cố định qua CI runs | Per-run entity IDs, op IDs |
| Test nghĩ contention nhưng calls tuần tự | Barrier/start timing không đồng thời | Executor/latch + metrics |
| Lab RF1 PASS, RF3 staging timeout | Network/replica phases khác | Multi-node test riêng |
| Java Driver automatic retry | `setIdempotent(true)`/retry profile | Disable/record attempts cho test |
| Assertion chỉ có `row != null` | Không kiểm revision/op ID | Assert business oracle |
| Fault test dừng node không thuộc replica set | Token assignment không biết | Chọn key/replica đúng |
| Timeout giả do CI container CPU throttling | Shared resources | Dedicated workload/fault environment |
| Test false nhiều nhưng không thấy contention | Các requests chạy tuần tự | Dùng `ContentionHistogram` cùng `ConditionNotMet` |

### 20.5. Chaos với lost ACK có kiểm soát

Nếu tổ chức có tool fault injection trên **test-only network proxy**, có thể đặt fault *chỉ trên response path* sau khi server đã áp CAS, rồi xác minh:

~~~text
1. Baseline and known data
2. CAS with stable op ID
3. Proxy drops only matching response (lab)
4. Client marks UNKNOWN_OUTCOME
5. Reconciler performs serial/read + checks op ID/version
6. Result VERIFIED_APPLIED or still UNKNOWN
7. No duplicate downstream side effect
8. Restore network and collect metrics
~~~

**Không bảo đảm** một network proxy có thể biết chính xác commit đã xảy ra nếu không có server/trace evidence. Test harness phải quan sát/mô phỏng boundary rõ ràng; đừng gọi “lost ACK after commit” khi thực tế fault chặn request ngay từ đầu.

### 20.6. Test sau restore/repair và rolling restart

Trong một cluster trải qua snapshot restore, repair hoặc rolling restart:

- Kiểm schema/table/PK, RF/CL, node states và data oracle trước.
- Dùng các **historical operation IDs** từ audit manifest để đối soát, không chỉ CAS một entity mới.
- Kiểm pending Paxos transactions/`UnfinishedCommit` và resource load khi node join/recover.
- Không làm destructive fault injection trong cùng đợt restore thật.
- Nếu node đang DOWN, agreement của các UP nodes không nói node sẽ trở về với cùng trạng thái; cần rejoin gate.

## 21. Hai mươi hai ca chẩn đoán thực tế

### Ca 1 — `[applied]=false` bị báo thành “database timeout”

**Dấu hiệu:** HTTP 500/error-rate tăng, nhưng Cassandra `ConditionNotMet` tăng, timeout không tăng.

**Phân tích:** Application coi business conflict là server failure. **Sửa:** Ánh xạ false sang 409/412 hoặc rule nghiệp vụ, ghi conflict metrics riêng; không tăng server timeout.

### Ca 2 — Hai API requests cùng tạo username

**Dấu hiệu:** Một request true, một false trên `INSERT IF NOT EXISTS` cùng username guard key.

**Phân tích:** Đây là hành vi bảo vệ uniqueness được mong đợi. **Sửa:** Trả “username unavailable” cho loser; không retry với random guard key để “vượt” duplicate.

### Ca 3 — Lost ACK làm khách hàng thanh toán lại

**Dấu hiệu:** API 504, client retry với new order ID, tạo hai business intents.

**Phân tích:** Server có thể đã áp CAS trước khi response mất. **Sửa:** Stable idempotency key + transaction status lookup, reconciliation ledger, dedupe side effects.

### Ca 4 — Retry `INSERT IF NOT EXISTS` trả false dù lần đầu đã thành công

**Dấu hiệu:** Attempt 1 timeout; attempt 2 false; row chứa `last_op_id` của attempt 1.

**Phân tích:** False của retry không phủ định success trước đó. **Sửa:** Đối soát operation ID và revision, đánh VERIFIED_APPLIED.

### Ca 5 — Revision race thông thường bị gọi là Paxos bug

**Dấu hiệu:** A true, B false cùng expected revision 12.

**Phân tích:** CAS đã ngăn lost update. **Sửa:** Xử lý optimistic concurrency conflict, không tăng retries vô hạn.

### Ca 6 — Contention tăng do client “chạy lại cho đến khi true”

**Dấu hiệu:** `ConditionNotMet` và CAS QPS tăng sau deploy, cùng một key lặp quá nhiều attempts.

**Phân tích:** App retry sai policy; false là definitive condition failure. **Sửa:** Throttle, fail-fast conflict, backoff sau **business re-evaluation** khi được phép.

### Ca 7 — CAS p99 tăng nhưng Cassandra không thiếu CPU toàn cluster

**Dấu hiệu:** Một hot partition có nhiều concurrent writers; cluster CPU trung bình thấp.

**Phân tích:** Serialization/ballot competition tập trung trên natural replicas của key. **Sửa:** Per-key concurrency cap/single-writer pattern hoặc thiết kế lại invariant/partition.

### Ca 8 — Hai writers không tranh nhau vì dùng hai random partition keys

**Dấu hiệu:** Cả hai `INSERT IF NOT EXISTS` true, dù business rule chỉ cho phép một active subscription/customer.

**Phân tích:** LWT bảo vệ **mỗi key riêng**, invariant đặt trên customer chứ không phải subscription ID. **Sửa:** Unique guard keyed by customer/scope, protocol multi-table có reconciliation.

### Ca 9 — `CASWriteUnknownException` bị chuyển thành `FAILED`

**Dấu hiệu:** Java exception mapper trả “chắc chắn thất bại” ngay, không lưu operation ID.

**Phân tích:** Exception nói **unknown state**, không có bằng chứng rollback. **Sửa:** UNKNOWN/PENDING_VERIFICATION, durable operation record và reconciliation.

### Ca 10 — Driver timeout ngắn hơn server Paxos xử lý

**Dấu hiệu:** Client timeout 500ms, server logs cho thấy CAS completes sau 800ms.

**Phân tích:** Client deadline không chặn sự kiện server commit đã xảy ra. **Sửa:** Align deadline budgets, response status lookup, tránh duplicate retries.

### Ca 11 — Tăng `cas_contention_timeout` khiến queue nặng hơn

**Dấu hiệu:** Timeout có vẻ giảm, nhưng p99/in-flight/memory tăng, throughput không tăng.

**Phân tích:** Chỉ kéo dài thời gian coordinator tranh ballot, không giải quyết hotspot. **Sửa:** Giảm contenders/key, app backpressure, đo CAS contention và latency.

### Ca 12 — LWT bị speculative execution nhân đôi

**Dấu hiệu:** Một logical operation tạo nhiều coordinator attempts, contention histogram tăng.

**Phân tích:** Speculation trên non-idempotent LWT. **Sửa:** Không speculate, set idempotence đúng, đo physical attempts.

### Ca 13 — App A dùng `SERIAL`, app B dùng `LOCAL_SERIAL` ở DC khác

**Dấu hiệu:** Team kỳ vọng global order nhưng SCL config không nhất quán.

**Phân tích:** Scope không đồng nhất; LOCAL_SERIAL chỉ local. **Sửa:** Review invariants, thống nhất global SCL policy/driver profiles và thử multi-DC.

### Ca 14 — Row hiện tại là op B, reconciler kết luận op A chưa từng áp

**Dấu hiệu:** A timeout, B tiếp tục workflow, current `last_op_id=B`.

**Phân tích:** Current row không chứa lịch sử đầy đủ. **Sửa:** Audit ledger/events hoặc state transition history; giữ UNKNOWN nếu không có proof.

### Ca 15 — Normal UPDATE xen vào LWT

**Dấu hiệu:** Revision có thể quay lùi hoặc status thay bất thường dù CAS tests pass.

**Phân tích:** Một writer không dùng CAS/fencing. **Sửa:** Audit mọi write paths/DAO/background jobs, enforce protocol, xem timestamp/LWW.

### Ca 16 — Quorum thiếu một replica làm CAS timeout

**Dấu hiệu:** Một natural replica `DN`/network isolated, CAS timeout; normal ONE reads vẫn pass.

**Phân tích:** Serial/normal quorum của LWT đòi replicas/ACK khác ordinary ONE. **Sửa:** Kiểm RF/CL/DC/natural replica sets, phục hồi node, không giảm CL mù.

### Ca 17 — Replica đều `UN` nhưng prepare/propose chậm

**Dấu hiệu:** Cassandra gossip UP, p99 CAS cao, GC pauses/disk await/internode RTT tăng.

**Phân tích:** UP không bảo đảm phản hồi kịp deadline; contention có thể không phải yếu tố duy nhất. **Sửa:** Thu `CasPrepare`/`CasPropose`/host metrics, điều tra bottleneck.

### Ca 18 — Reconciliation chỉ SELECT `ONE` rồi báo failed

**Dấu hiệu:** Client CAS timeout; read ONE ngay sau đó trả revision cũ.

**Phân tích:** Normal read có thể stale/in-flight Paxos. **Sửa:** Dùng serial read/appropriate CL theo contract, bounded polling và audit; không biến old snapshot thành “rollback chắc chắn”.

### Ca 19 — Sau failover node UP nhưng CAS p99 chưa trở lại

**Dấu hiệu:** Node `UN`, transaction read/write vẫn có unfinished commit/GC/disk/repair load.

**Phân tích:** Functional recovery khác performance recovery. **Sửa:** Monitor CAS metrics, error/retry p99 và reconciliation backlog qua nhiều windows.

### Ca 20 — Benchmark LWT chạy một key cho 10 nghìn clients

**Dấu hiệu:** Throughput cực thấp, contention rất cao; team kết luận Cassandra không scale.

**Phân tích:** Thí nghiệm đo hotspot serialization, không phải independent CAS trên nhiều partitions. **Sửa:** Tách hotspot-test và representative key distribution, vẫn giữ invariant thật.

### Ca 21 — Conditional batch được dùng như cross-partition ACID

**Dấu hiệu:** App kỳ vọng bảo toàn order row, username guard, Kafka event và inventory ở nhiều partitions từ một batch.

**Phân tích:** Cassandra conditional batch không cung cấp transaction toàn cục xuyên các partitions/hệ thống. **Sửa:** Thiết kế saga/inbox/outbox, idempotency/reconciliation và compensating actions.

### Ca 22 — Duplicate downstream email dù CAS chỉ true một lần

**Dấu hiệu:** DB state chỉ transition một lần, nhưng service crash/retry gửi email hai lần.

**Phân tích:** LWT bảo vệ Cassandra mutation, không bảo vệ việc gửi email sau ACK. **Sửa:** Outbox/inbox/idempotent consumer/unique message ID và status ledger.

## 22. Runbook GO / HOLD / STOP khi LWT gặp xung đột hoặc timeout

### 22.1. Quy trình từ cảnh báo tới quyết định

~~~text
ALERT: CAS p99 high / condition_false surge /
       CASWriteUnknown / client 504 / duplicate side effects
                         |
             1. Identify contract
        keyspace/table/PK/RF/DC/SCL/NCL/query family
                         |
             2. Preserve evidence
        logical_op_id, attempt IDs, timeline, errors
                         |
          +--------------+--------------+
          |                             |
   Definitive result               No definitive result
          |                             |
   [applied] true/false             UNKNOWN_OUTCOME
          |                             |
   Business state path              Quarantine/reconcile
          |                             |
          +--------------+--------------+
                         |
               3. Observe cluster
     CASRead/CASWrite, replicas, GC/disk, driver retries
                         |
               4. Identify cause
   contention? normal vs serial CL? hotspot? network?
                         |
               5. Mitigate safely
      throttle per-key, hold rollout, restore replicas,
      fix retry policy or data-model protocol
                         |
                6. Verify outcome
     data oracle + op ledger + SLO + no duplicate effects
                         |
                    GO / HOLD / STOP
~~~

**Không** mở rộng traffic chỉ vì timeout từ Java đã hết; cần quan sát **Cassandra CAS metrics và unknown-outcome reconciliation backlog**. Một hệ thống có p99 tốt nhưng hàng nghìn giao dịch chưa biết kết quả không đạt readiness.

### 22.2. Preflight trước xử lý production

1. **Xác nhận scope:** app release, keyspace/table, query family, entity ID theo opaque/hash, thời điểm UTC, local DC.
2. **Chốt CL:** normal CL/serial CL thực tế của statement, execution profile, RF per DC, có transient replica hay không.
3. **Ghi outcome:** `[applied]` true/false hay exception/unknown? Có retry/speculation đã xảy ra không?
4. **Dừng thay đổi gây nhiễu:** Hold rollout mới, tạm dừng migration hoặc traffic burst của feature đang gây contention theo quyền quản trị.
5. **Giữ dữ liệu:** Không truncate table, không chỉnh Paxos system state/ballots, không ép repair/compact như workaround.
6. **Thu baseline:** `CASWrite.Latency`, `ConditionNotMet`, contention, timeout/unknown, GC/disk/network, driver pool/retries.
7. **Bảo vệ business:** Idempotency keys, ledger, status pending; không tự replay external side effects.
8. **Đặt owner:** API owner, Cassandra SRE/DBA, reconciliation/ledger owner và người quyết định rollout.

### 22.3. Thu thập bằng chứng đọc-only

~~~bash
nodetool status
nodetool describecluster
nodetool tpstats
nodetool netstats
nodetool compactionstats
nodetool tablestats <keyspace>.<table>
~~~

`<keyspace>.<table>` trong đoạn trên là **placeholder** để operator thay bằng bảng được phép kiểm; không phải cú pháp dấu góc cần gõ nguyên văn. Trong shell thực phải xác minh option/định dạng `tablestats` của Cassandra version.

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'lwt_lab';

SELECT status, revision, last_op_id
FROM lwt_lab.account_state
WHERE account_id = 11111111-1111-1111-1111-111111111111;
~~~

Với production, dùng **known-key của chính operation đang điều tra** và CL/permission được phê duyệt, không thay thế bằng account ID trong lab. Không đưa dữ liệu nhạy cảm vào log. Một read thường chỉ cho biết current state và có thể không đủ phân định lịch sử.

### 22.4. Triage theo triệu chứng

| Quan sát | Phân loại | Hành động đầu tiên |
|---|---|---|
| Nhiều false, ít timeout, CAS latency ổn | Business conflicts | Audit expected revisions, API contract |
| False nhiều, client retry cùng expected revision | Retry bug | Disable loop, backoff/business re-evaluate |
| Contention histogram và p99 cùng tăng | Paxos hotspot | Per-key rate limit/ownership, giảm writers |
| CAS timeout tăng + nodes DN/replica RTT cao | Replica/network | Hold, phục hồi quorum, không giảm CL |
| `CASWriteUnknownException` xuất hiện | Unknown outcome | Lưu op IDs, reconciliation/ledger |
| App timeout ngắn hơn server | Deadline mismatch | Align budgets, không tự replay |
| Write p99 bình thường nhưng duplicate emails | Cross-system side effect | Inbox/outbox dedupe, không sửa Cassandra CAS |
| CAS failures sau mixed-version upgrade | Version/feature compatibility | Hold upgrade, check version-specific Paxos behavior |
| Normal UPDATE xen vào CAS | Protocol breach | Audit all writers, protect invariant |
| Cluster quorum khỏe nhưng CAS p99 cao | Contention or capacity | Read metrics at CAS phases, per-key distribution |

### 22.5. Điều kiện GO/HOLD/STOP

| Gate | GO | HOLD | STOP/ESCALATE |
|---|---|---|---|
| **Correctness** | Current/audit state và op IDs chứng minh invariant | Unknowns đang reconcile trong budget | Wrong state/duplicate irreversible side effect |
| **CAS availability** | Đủ replicas cho SCL/NCL, error rate trong SLO | Replica phục hồi, quorum margin thấp | Mất CL tại keyspace/DC nghiệp vụ |
| **Contention** | False/contention có ý nghĩa business, p99 ổn | Contention tăng, chưa bão hòa | Retry storm làm cluster quá tải |
| **Unknown outcomes** | Backlog ổn, đúng RTO và có ownership | Tồn tại pending với deadline | Không có ID/ledger, không thể bảo đảm không duplicate |
| **Latency** | CAS p95/p99 và timeout đạt SLO | P99 drift hoặc retries tăng | SLO vượt guardrail nghiêm trọng |
| **Topology/repair** | Node states, disk/GC/streaming trong phạm vi cho phép | Rejoin/catch-up chưa hoàn tất | Rủi ro data loss hoặc disk full |

**GO** luôn là **GO có phạm vi**, ví dụ “cho phép feature orders.confirm ở dc1 với RF3, LOCAL_SERIAL/LOCAL_QUORUM, 500 req/s, p99 trong 150ms, unknown-outcome backlog xử lý trong 5 phút”. Những con số ở đây **minh họa**, phải lấy từ SLO thật; không dùng như thresholds mặc định.

### 22.6. Cảnh báo cần dừng test/rollout ngay

- Có bằng chứng vi phạm uniqueness hoặc state machine invariant.
- Một operation ID được dùng cho **hai ý định khác nhau**, hoặc retries tạo external side effect hai lần.
- Không đủ natural replicas để đạt CL nghiệp vụ ở phần lớn token ranges cần phục vụ.
- CAS timeouts/driver timeouts vượt error budget, backlog UNKNOWN tăng không kiểm soát.
- Disk/commitlog/GC/compaction errors khiến rủi ro mất dữ liệu.
- Một operator đề xuất chỉnh `system.paxos`, ép `DROP`/`TRUNCATE` hoặc tắt đồng loạt nodes mà không có runbook.
- Fault test nhắm sai cluster/namespace so với allowlist.

### 22.7. Khôi phục sau fault khác hoàn thành business transaction

~~~text
Node C UP again                    -> topology recovered
CAS LOCAL_QUORUM starts succeeding -> functional CL recovered
CAS p99 returns to SLO             -> performance recovered
Old UNKNOWN operations reconciled  -> business outcomes recovered
Duplicate effects resolved         -> end-to-end workflow recovered
~~~

Đây là **năm gate khác nhau**. Không đóng incident chỉ vì `nodetool status` hiển thị `UN` cho tất cả nodes hoặc HTTP error rate tạm về 0 khi vẫn còn hàng nghìn thanh toán `UNKNOWN`.

### 22.8. Mẫu báo cáo sự cố

~~~text
INCIDENT_ID:
UTC_FIRST_ERROR / UTC_RECOVERY:
SERVICE / RELEASE / QUERY FAMILY:
CASSANDRA VERSION / JAVA DRIVER VERSION:
KEYSPACE / TABLE / PARTITION MODEL:
RF PER DC / LOCAL_DC:
NORMAL_CL / SERIAL_CL:
OPERATION_ID (sanitized), ATTEMPT_IDS:
EXPECTED_REVISION / TARGET_REVISION / BUSINESS INVARIANT:
APPLIED_TRUE / CONDITION_FALSE / UNKNOWN COUNTS:
CASWrite CONTENTION / LATENCY / UNFINISHED_COMMIT:
CASRead METRICS / SERVER GC / DISK / NETWORK:
DRIVER RETRIES / SPECULATION / POOL-INFLIGHT:
RECONCILIATION BACKLOG / VERIFIED / MANUAL_REVIEW:
DATA ORACLE / DOWNSTREAM EFFECTS CHECK:
MITIGATION / ROLLBACK:
GO / HOLD / STOP AND OWNER:
OPEN RISKS / NEXT REVIEW UTC:
~~~

Không ghi nguyên tài khoản khách hàng, thẻ thanh toán, bí mật, session token hoặc `BoundStatement` values vào log. Khi cần correlation, giữ opaque op ID trong hệ thống nội bộ có phân quyền.

### 22.9. Các hành động **không** thay thế diagnosis

**Không**:

- Tăng `cas_contention_timeout`/`write_request_timeout` vô hạn.
- Giảm từ `LOCAL_QUORUM` xuống `ONE` để làm dashboard xanh mà không review consistency contract.
- Chuyển từ `SERIAL` sang `LOCAL_SERIAL` chỉ vì WAN chậm nếu invariant đòi global order.
- Bật mọi driver retries/speculative execution.
- Chạy major compaction/repair hoặc invalidate caches không liên quan.
- Thay op ID mỗi lần retry để vượt `[applied]=false`.
- Xóa row/ledger khi client báo 504 dù outcome còn unknown.

Mỗi hành động trên có thể làm **mất bằng chứng hoặc tăng độ bất định**. Thay vào đó, giữ nguyên operation identity, định lượng contention, làm giảm concurrent writers, phục hồi replicas và đối soát có deadline.

## 23. Checklist nghiệm thu một luồng LWT

### 23.1. Thiết kế dữ liệu và invariant

- [ ] Invariant nghiệp vụ mô tả chính xác (uniqueness, state transition, ownership).
- [ ] Guard key/partition key đại diện đúng scope của invariant.
- [ ] Không giả định CAS trên hai random partitions bảo vệ uniqueness toàn cục.
- [ ] Mọi actor cập nhật state đều dùng cùng LWT/fencing protocol.
- [ ] Có revision/token để tránh stale writer và ABA.
- [ ] Operation ID được tạo **một lần cho một logical intent**.
- [ ] Last-op marker được ghi cùng conditional mutation khi khả thi.
- [ ] Có audit/ledger nếu cần biết toàn bộ lịch sử sau nhiều state transitions.
- [ ] Cross-partition/cross-system effects có saga/outbox/inbox/compensation.
- [ ] Không dùng LWT trên global counter/hot key mà không có throughput plan.

### 23.2. CQL/driver contract

- [ ] `INSERT IF NOT EXISTS`/`UPDATE IF`/`DELETE IF` đúng primary key và condition.
- [ ] Có phân biệt ordinary write và LWT, không chỉ dựa vào tên method Java.
- [ ] Cả normal CL và serial CL được đặt tường minh.
- [ ] Local vs global serial scope được review trên topology multi-DC.
- [ ] `ResultSet.wasApplied()` chỉ dùng với conditional DML.
- [ ] `[applied]=false` được xử lý như condition conflict.
- [ ] `CASWriteUnknownException` và write/client timeouts không bị map thành failure chắc chắn.
- [ ] Driver `setIdempotent` chỉ bật với proof, không do convention chung.
- [ ] Speculative execution không nhân LWT proposals ngoài policy.
- [ ] Retry budget, backoff/jitter, max in-flight và deadline thống nhất.

### 23.3. Reconciliation

- [ ] Có một durable record/tracking cho operation PENDING/UNKNOWN.
- [ ] Current row + op ID + revision kiểm được trên primary key.
- [ ] Khi cần, dùng serial read/CL phù hợp để xử lý pending Paxos.
- [ ] Không suy “not applied” từ một old snapshot ở `ONE`.
- [ ] Ledger/history có mặt khi last_op_id có thể bị op kế tiếp thay thế.
- [ ] Unknown write outcome không gây double charge/email/emit.
- [ ] Retry cùng stable op ID và expected revision sau bước reconciliation được phép.
- [ ] Có manual review/escalation khi không đủ evidence.
- [ ] Reconciler có bounded budget và rate limit.
- [ ] Retention của operation records đủ cho thời gian khách hàng retry.

### 23.4. Monitoring và capacity

- [ ] Thu CASRead/CASWrite Latency riêng, không trộn normal Read/Write.
- [ ] Thu ConditionNotMet và phân biệt với server errors.
- [ ] Thu ContentionHistogram, UnfinishedCommit, timeouts, failures.
- [ ] Có breakdown theo query family, DC, CL, time window.
- [ ] Thu driver logical requests/physical attempts/retries/speculation.
- [ ] Thu per-node GC, disk, internode latency, queue/backpressure.
- [ ] Theo dõi hot-key skew an toàn, không log PII/high-cardinality IDs.
- [ ] Benchmark dùng representative contenders/key và key distribution.
- [ ] CL/data correctness và client p95/p99/error budget được cùng quan sát.
- [ ] Có SLO cho reconciliation backlog/age, không chỉ request latency.

### 23.5. An toàn và vận hành

- [ ] Fault tests chỉ chạy trên cluster lab/staging cho phép.
- [ ] Không sửa Paxos internals/`system.paxos`/system tables.
- [ ] Không tắt nodes hoặc thay RF/CL trên production để mô phỏng contention.
- [ ] Không dùng DROP/TRUNCATE như “reset conflict” khi có data thật.
- [ ] Có release gate GO/HOLD/STOP và rollback owner.
- [ ] Phân biệt functional CL recovery với business-outcome recovery.
- [ ] Không đóng incident khi còn unknown unresolved không có owner.
- [ ] Mọi việc sửa retry/CL/SCL đều có integration regression test.
- [ ] Biết giới hạn của RF1 lab so với RF3/multi-DC.
- [ ] STEP 4 chỉ soạn tài liệu; compile/QA/fault execution thuộc vòng chuyên môn sau.

## 24. Câu hỏi tự đánh giá và gợi ý đáp án

**Câu 1.** Vì sao `SELECT` rồi `UPDATE` ở `QUORUM` không thay CAS?  
**Đáp án:** Có khoảng race giữa check ở Java và write; các writes thường không kiểm điều kiện nguyên tử.

**Câu 2.** CQL nào tạo row chỉ khi chưa tồn tại?  
**Đáp án:** `INSERT ... IF NOT EXISTS`.

**Câu 3.** CQL nào kiểm state revision trước khi cập nhật?  
**Đáp án:** `UPDATE ... SET ... WHERE full_primary_key ... IF revision = n`.

**Câu 4.** `[applied]=true` nói điều gì?  
**Đáp án:** Conditional statement của attempt có definitive response đã được áp dụng.

**Câu 5.** `[applied]=false` có phải là Cassandra timeout không?  
**Đáp án:** Không; điều kiện không thỏa, thường là business conflict.

**Câu 6.** Nếu LWT timeout và không có result, có thể trả “definitely rolled back” không?  
**Đáp án:** Không; commit có thể đã xảy ra hoặc vẫn tiến hành.

**Câu 7.** Java Driver method nào đọc cột `[applied]`?  
**Đáp án:** `ResultSet.wasApplied()` với CQL conditional DML.

**Câu 8.** `wasApplied()` của ordinary INSERT trả gì?  
**Đáp án:** True theo API convention; **không** chứng minh ordinary INSERT là LWT.

**Câu 9.** Vì sao retry `INSERT IF NOT EXISTS` sau lost ACK có thể trả false?  
**Đáp án:** Row đã được tạo ở lần trước, nên điều kiện “not exists” không còn đúng.

**Câu 10.** `[applied]=false` ở attempt thứ hai có chứng minh logical operation thất bại không?  
**Đáp án:** Không; lần đầu có thể đã applied.

**Câu 11.** LWT dùng giao thức đồng thuận nào?  
**Đáp án:** Paxos.

**Câu 12.** Vì sao không hardcode “mọi LWT có đúng bốn network round trips”?  
**Đáp án:** Paxos implementation/fast-path Cassandra 4.1+ khác theo phiên bản, contention và recoveries.

**Câu 13.** Serial consistency level định nghĩa gì?  
**Đáp án:** Phạm vi consensus/Paxos của conditional phase.

**Câu 14.** Normal CL của conditional write định nghĩa gì?  
**Đáp án:** Commit/learn phase ACK và liên hệ tới visibility của normal reads.

**Câu 15.** `SERIAL` và `LOCAL_SERIAL` có phạm vi giống nhau không?  
**Đáp án:** Không; LOCAL_SERIAL có scope local DC, không tự bảo đảm global order.

**Câu 16.** Trong multi-DC, hai writers dùng `LOCAL_SERIAL` ở hai DC có tự bảo đảm invariant global không?  
**Đáp án:** Không nên giả định; cần global serialization policy/contract và kiểm thử.

**Câu 17.** Một read `ONE` sau conditional write timeout không thấy state mới, có chứng minh request chưa applied không?  
**Đáp án:** Không; stale replica hoặc pending Paxos commit có thể tồn tại.

**Câu 18.** `CONSISTENCY LOCAL_QUORUM` có tự thay `SERIAL CONSISTENCY` trong cqlsh không?  
**Đáp án:** Không, chúng là hai settings khác nhau.

**Câu 19.** Một serial read có thể làm gì ngoài đọc bình thường?  
**Đáp án:** Giúp hoàn tất/đọc pending Paxos state theo giao thức; có chi phí.

**Câu 20.** `CASWriteUnknownException` cho biết điều gì?  
**Đáp án:** Kết quả CAS đang không xác định; cần reconciliation, không khẳng định rollback.

**Câu 21.** `WriteTimeoutException.getReceived()` có phải số business writes đã commit không?  
**Đáp án:** Không; đó là số responses/ACK trong pha lỗi so với `blockFor`.

**Câu 22.** `DriverTimeoutException` có bảo đảm request chưa tới server không?  
**Đáp án:** Không; driver deadline có thể hết sau khi server đã xử lý.

**Câu 23.** Vì sao cần giữ operation ID cố định xuyên retries?  
**Đáp án:** Để nhận diện cùng logical intent và tránh tạo duplicate effects/records.

**Câu 24.** Nên sinh attempt ID và operation ID thế nào?  
**Đáp án:** Attempt ID mới cho mỗi network attempt; **cùng operation ID** cho tất cả attempts của một ý định.

**Câu 25.** `last_op_id` trong row có chứng minh mọi thao tác từng xảy ra không?  
**Đáp án:** Không; op mới có thể ghi đè marker cũ, cần ledger/history nếu cần cả lịch sử.

**Câu 26.** Vì sao current revision=10 không chứng minh operation cũ chưa từng chạy?  
**Đáp án:** Có thể đã có transitions khác giữa lúc op cũ applied và thời điểm đọc; current state không phải toàn bộ event history.

**Câu 27.** ABA problem là gì?  
**Đáp án:** State từ A→B→A làm check chỉ theo status thấy “A” nhưng bỏ qua lịch sử; cần revision/fencing.

**Câu 28.** Tại sao không đánh dấu mọi LWT `setIdempotent(true)`?  
**Đáp án:** Auto retry/speculation có thể đổi applied outcome và gây duplicate downstream side effects.

**Câu 29.** Speculative execution có thể làm LWT contention xấu hơn thế nào?  
**Đáp án:** Một logical request tạo nhiều CAS proposals/coordinator attempts cạnh tranh cùng key.

**Câu 30.** `ConditionNotMet` cao có luôn nghĩa database bị hỏng không?  
**Đáp án:** Không; có thể rất nhiều business conflicts bình thường.

**Câu 31.** Metric nào đặc biệt giúp đo contention Paxos?  
**Đáp án:** `CASWrite.ContentionHistogram` và `CASRead.ContentionHistogram`.

**Câu 32.** `UnfinishedCommit` có ý nghĩa gì?  
**Đáp án:** Đếm trường hợp transaction commit còn dở được hoàn tất trong CAS read/write path.

**Câu 33.** `CASWrite.Latency` khác ordinary `WriteLatency` không?  
**Đáp án:** Có; CAS là request type riêng và có các pha consensus.

**Câu 34.** Vì sao nhìn CPU trung bình toàn cluster có thể che hotspot?  
**Đáp án:** Một partition/natural replica set bị tranh Paxos trong khi nodes khác nhàn rỗi.

**Câu 35.** Tăng nodes có tự nhân throughput của một hot partition không?  
**Đáp án:** Không; cùng invariant/key cần serialization, thêm nodes không loại bỏ tranh chấp đó.

**Câu 36.** Có thể shard guard key của uniqueness tùy ý để tăng tốc không?  
**Đáp án:** Không nếu làm mất invariant toàn cục; cần protocol mới được chứng minh.

**Câu 37.** `cas_contention_timeout` làm gì?  
**Đáp án:** Giới hạn thời gian coordinator cố giải quyết CAS contention, không chữa hotspot.

**Câu 38.** Tăng server timeout vô hạn có bảo đảm throughput tăng không?  
**Đáp án:** Không; có thể chỉ tăng in-flight/queue/backlog và unknown outcomes.

**Câu 39.** `UnavailableException` trên LWT khác `[applied]=false` thế nào?  
**Đáp án:** Một lỗi availability/quorum; một là kết quả điều kiện không đúng được server xác nhận.

**Câu 40.** Vì sao `AllNodesFailedException` phải kiểm `getAllErrors()`?  
**Đáp án:** Nhiều coordinators có causes khác nhau, cần xem timeout/unknown/routing cụ thể.

**Câu 41.** Khi operation ID đã applied ở Cassandra nhưng email vẫn gửi trùng, sai ở đâu?  
**Đáp án:** Side effect bên ngoài thiếu outbox/inbox/idempotent consumer; LWT không cho cross-system exactly-once.

**Câu 42.** Một CAS trên subscription_id random có bảo đảm chỉ một subscription/customer không?  
**Đáp án:** Không; hai subscription IDs là hai keys độc lập, cần guard theo customer/scope.

**Câu 43.** Vì sao fault injection phải biết natural replicas của test key?  
**Đáp án:** Dừng node không thuộc replica set có thể không ảnh hưởng CAS; kết luận availability sai.

**Câu 44.** Lab một node RF1 chứng minh được điều gì?  
**Đáp án:** CQL conditional behavior/coding basics, không chứng minh multi-node quorum contention/recovery.

**Câu 45.** Khi node đã `UN` sau restart, có thể đóng incident unknown operations chưa đối soát không?  
**Đáp án:** Không; topology recovery khác business outcome recovery.

**Câu 46.** Reconciliation sau UNKNOWN nên ưu tiên bằng chứng nào?  
**Đáp án:** Stable op ID, expected version/state, serial/appropriate CL read và audit history khi cần.

**Câu 47.** Nếu không còn đủ evidence sau bounded retries, nên làm gì?  
**Đáp án:** Giữ PENDING_VERIFICATION/MANUAL_REVIEW với owner; không tự declare failed rồi replay.

**Câu 48.** Khi nào có thể mở rộng traffic LWT sau incident?  
**Đáp án:** Khi SCL/NCL/replica đủ, invariants và data oracle đúng, contention/p99/errors đạt SLO, unknown backlog được kiểm soát và downstream effects không trùng.

## 25. Tổng kết: LWT bảo vệ điều kiện, không bảo đảm client luôn biết kết quả

~~~text
                   BUSINESS INTENT
             entity_id + stable operation_id
             expected_revision + target_state
                           |
                           v
                    CQL UPDATE ... IF
              SERIAL/LOCAL_SERIAL + normal CL
                           |
              +------------+-------------+
              |                          |
        Client gets result         Client no definitive result
              |                          |
       +------+-------+             UNKNOWN_OUTCOME
       |              |                   |
  applied=true    applied=false          v
       |              |             RECONCILE / AUDIT
  APPLIED       CONDITION_NOT_MET          |
       |              |              +----+----+
       |      Business re-evaluate    |         |
       |                              |         |
       |                         PROOF       NO PROOF
       |                              |         |
       |                    VERIFIED OUTCOME  PENDING/
       |                                      MANUAL REVIEW
       +----------------------+------------------+
                              |
                   End-to-end side effects
               outbox/inbox/idempotent handlers
                              |
                  GO / HOLD / STOP gate
~~~

### 25.1. Bảy nguyên tắc cần ghi nhớ

1. **Xung đột điều kiện không phải lỗi hạ tầng:** `[applied]=false` có thể là một kết quả đúng theo nghiệp vụ. Đừng retry/alert như server timeout.
2. **Contention là chi phí thực:** Nhiều writers tranh một Paxos scope khiến latency, ballot retries và timeout tăng. Đo `CASWrite` metrics, per-key hotspots và physical attempts.
3. **Hai CL có nhiệm vụ khác nhau:** `SERIAL`/`LOCAL_SERIAL` cho serial phase; normal `QUORUM`/`LOCAL_QUORUM`/... cho commit/learn visibility. Scope phải phù hợp RF/DC và invariant.
4. **Không thấy ACK ≠ thất bại chắc chắn:** `CASWriteUnknownException`, write/client timeout hoặc mất mạng có thể xảy ra sau commit. Giữ UNKNOWN cho tới khi có evidence.
5. **Logical operation khác network attempt:** Giữ **operation ID cố định**, revision fencing, không sinh business ID mới khi retry cùng ý định.
6. **Snapshot không phải lịch sử:** `last_op_id` của row hiện tại có thể bị op sau ghi đè; muốn phân xử toàn bộ chuỗi phải có ledger/audit semantics.
7. **LWT không làm mọi hệ thống exactly-once:** Cross-partition và external side effects vẫn cần state machine, outbox/inbox, deduplication, saga và reconciliation.

### 25.2. Chẩn đoán nhanh theo tín hiệu

| Tín hiệu | Câu hỏi ưu tiên | Hướng xử lý |
|---|---|---|
| `[applied]=false` | Expected revision/condition có stale? | Business conflict và re-evaluate |
| `ContentionHistogram` tăng | Có quá nhiều writers cùng entity? | Throttle, serialize per key, tối ưu invariant |
| `CASWrite.Timeouts` tăng | Replica/GC/network hay contention? | Scope RF/SCL/NCL, metrics per node |
| `CASWriteUnknownException` | Có operation ID/durable ledger chưa? | UNKNOWN → reconciliation |
| `DriverTimeoutException` | Request đã rời driver chưa, server có thể commit? | Không replay mù; giữ trace/unknown |
| `ConditionNotMet` tăng nhưng p99 ổn | Business conflict bình thường hay retry bug? | Phân tích query family/attempt ratio |
| Duplicate email/payment | Side effect có idempotency? | Outbox/inbox/compensation |
| Node `UN` nhưng unknown vẫn tồn đọng | Outcome đã được đối soát chưa? | Business recovery, không chỉ topology |

**Kết luận thực hành:** Không nên đánh giá “Cassandra LWT hoạt động đúng” chỉ vì một câu `INSERT IF NOT EXISTS` trả true. Một luồng production đáng tin phải chứng minh **đúng invariant/partition key, đúng serial và normal CL, phân biệt false vs unknown, giữ operation identity, giám sát contention, và có quy trình đối soát cả khi phản hồi bị mất**.

### 25.3. Giới hạn của bài lab và bước đánh giá tiếp theo

Các lab CQL/Java một node chỉ thể hiện conditional semantics và cách viết Java Driver. Chúng không phải bằng chứng đã thử WAN Paxos, replica failure, repair/compaction pressure hay giao dịch xuyên dịch vụ. Fault tests thực phải được thực hiện ở dedicated staging đủ RF/DC và có stop/recovery plan. Theo workflow học liệu, **STEP 4 viết Markdown**, không chạy Gradle, không inject fault và không làm STEP 6 Content QA; chuyên gia sẽ kiểm chứng phiên bản, khả năng compile và case studies ở bước sau.

## Tài liệu tham khảo

- [Apache Cassandra — Guarantees, lightweight transactions and linearizability](https://cassandra.apache.org/doc/stable/cassandra/architecture/guarantees.html) — cơ sở Paxos/CAS và phạm vi tính nhất quán.
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — `INSERT IF NOT EXISTS`, `UPDATE IF`, `DELETE IF`, partition/row semantics.
- [Apache Cassandra — cqlsh and serial consistency](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html) — tách `CONSISTENCY` và `SERIAL CONSISTENCY`, commit visibility.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — `CASRead`/`CASWrite`, `ConditionNotMet`, `ContentionHistogram`, `UnfinishedCommit`, `CasPrepare` và `CasPropose`.
- [Apache Cassandra — Cassandra 4.1 improvements](https://cassandra.apache.org/_/blog/Cassandra-4.1-is-here.html) — Paxos optimization và khác biệt latency/round trips với phiên bản trước.
- [Apache Cassandra — cassandra.yaml 4.1](https://cassandra.apache.org/doc/4.1/cassandra/configuration/cass_yaml_file.html) — `cas_contention_timeout`, `write_request_timeout` và các request budgets.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — token, replicas, RF/CL và read/write consistency nền tảng.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — data replica repair, không phải cơ chế xoá contention/Paxos.
- [Apache Java Driver 4.18.1 — ResultSet.wasApplied Javadoc](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/cql/ResultSet.html) — cách đọc `[applied]` và giới hạn trên nonconditional queries.
- [Apache Java Driver 4.18.1 — CASWriteUnknownException Javadoc](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/servererrors/CASWriteUnknownException.html) — CAS outcome không xác định.
- [Apache Java Driver 4.18.1 — WriteTimeoutException Javadoc](https://apache.github.io/cassandra-java-driver/4.18.1/api/com/datastax/oss/driver/api/core/servererrors/WriteTimeoutException.html) — `WriteType`, `received` và `blockFor`.
- [Apache Java Driver 4.18.1 — Retry policies](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/) — logic retry/idempotence và các timeout verdict.
- [Apache Java Driver 4.18.1 — Prepared statements](https://apache.github.io/cassandra-java-driver/4.18.1/core/statements/prepared/) — prepared/bound statements và cách tái sử dụng CQL.
- [Apache Java Driver 4.18.1 — Request throttling](https://apache.github.io/cassandra-java-driver/4.18.1/core/throttling/) — driver backpressure, queue và request budgets.
- [JUnit 5 User Guide](https://docs.junit.org/current/user-guide/) — assertions, lifecycle và test concurrency/integration.

