# Fencing token để từ chối thao tác từ tác nhân hết quyền

Một worker nhận quyền xử lý tác vụ xuất báo cáo, giữ một **distributed lock** có thời hạn 30 giây và bắt đầu ghi tệp kết quả. Sau đó worker bị dừng vì **GC pause**, máy ảo bị tạm ngưng hoặc mạng gián đoạn trong hơn 30 giây. Khóa hết hạn; worker khác nhận quyền và ghi kết quả mới. Worker cũ tỉnh lại, vẫn giữ biến trong bộ nhớ **“tôi đã lấy khóa”**, rồi tiếp tục ghi và ghi đè kết quả của worker mới.

Điểm nguy hiểm ở đây là **khóa hết hạn trong hệ điều phối không buộc tiến trình cũ ngừng chạy**. Không có cơ chế nào từ bên ngoài bảo đảm một worker đã mất quyền sẽ tự biết và dừng đúng trước tác động tiếp theo. Với nguồn dữ liệu quan trọng, cần một cơ chế khiến **nơi nhận thao tác** nhận biết và **từ chối tác nhân đã cũ**.

**Fencing token** giải quyết đúng vấn đề ấy: mỗi lần cấp quyền mới gắn với một **thế hệ/quyền phiên bản cao hơn**, và tài nguyên đích kiểm tra token khi chấp nhận thao tác. Khi tài nguyên đích đã công nhận thế hệ 42, thao tác từ thế hệ 41 sẽ bị từ chối, dù worker 41 vẫn đang chạy, kết nối mạng đã hồi phục và nó biết đầy đủ địa chỉ ghi.

Đây là bài học thuộc chương **Đồng thuận và quyền ghi** trong module **Database No SQL**. Nội dung sẽ đi từ lịch sử lỗi GC pause, quy tắc cấp token, điều kiện tại resource, phân biệt lease/CAS/version/idempotency, đến triển khai trong MongoDB, DynamoDB, Cassandra, Redis, etcd, ZooKeeper và các tài nguyên bên ngoài database. Các ví dụ cũng chỉ ra **giới hạn**: token tăng đơn điệu không phải bùa hộ mệnh nếu sink không thực thi kiểm tra hoặc chưa biết thế hệ mới.

## 1. Bài toán: worker đã mất khóa nhưng vẫn có thể ghi

Giả sử tác vụ **GenerateDailyReport** có một khóa phân tán:

~~~text
lock name: report:daily:2026-11-14
lease duration: 30 seconds
~~~

Timeline:

~~~text
t=00s  Worker A acquire lock -> SUCCESS
t=02s  A bắt đầu đọc dữ liệu và dựng báo cáo
t=05s  A bị GC pause / máy ảo suspend
t=30s  Lease A hết hạn
t=31s  Worker B acquire lock -> SUCCESS
t=34s  B ghi report mới, version B
t=40s  A hoạt động trở lại
t=41s  A ghi report cũ, version A
~~~

Nếu hệ đích chỉ cho phép:

~~~text
PUT /reports/daily/2026-11-14
body = nội dung báo cáo
~~~

thì thao tác của A ở t=41 có thể **ghi đè** báo cáo đúng hơn do B đã ghi ở t=34.

Những điều A có thể vẫn tin:

- “Tôi từng acquire lock thành công.”
- “Tôi không nhận được sự kiện lock bị thu hồi.”
- “Tôi đã kiểm tra lease trước khi bắt đầu tính toán.”
- “Tôi có connection hợp lệ đến database hoặc object storage.”

Không điều nào chứng minh **A còn quyền ghi vào thời điểm t=41**.

## 2. Vì sao TTL và distributed lock chưa đủ?

Một distributed lock/lease thường kiểm soát **việc cấp quyền tại hệ điều phối**:

~~~text
acquire(lockName) -> ownerId, expiresAt
renew(lockName, ownerId) -> success/fail
release(lockName, ownerId) -> success/fail
~~~

Khi TTL hết hạn, hệ điều phối có thể cấp lock cho người khác. Nhưng tiến trình A đã lấy lock:

- Có thể bị dừng ở điểm nằm **sau khi kiểm tra quyền**, trước khi ghi.
- Có thể đang chờ network call rất lâu.
- Có thể gửi request trước khi hết hạn nhưng request chỉ đến sink sau khi hết hạn.
- Có thể không nhận được thông báo về lease expiry.
- Có thể bỏ qua lỗi renew do bug hoặc đường xử lý ngoại lệ.
- Có thể giữ connection đến sink dù không còn quyền tại lock service.

Một ví dụ lỗi **time-of-check to time-of-use (TOCTOU)**:

~~~text
A: checkLease() -> still valid
A: dừng 40 giây
B: acquire lock mới và ghi
A: write() bằng kết quả checkLease cũ
~~~

Thêm một lệnh **checkLease trước write** chỉ rút ngắn cửa sổ race, **không xóa được race** nếu check quyền và effect nằm ở hai hệ độc lập.

**Fencing chuyển trách nhiệm kiểm tra từ lòng tin ở client sang một điều kiện bắt buộc tại tài nguyên đích**.

## 3. Fencing token là gì?

**Fencing token** là mã đại diện cho một **thế hệ quyền mới**. Trong mô hình điển hình, các lần cấp quyền liên tiếp cho cùng phạm vi nhận token tăng đơn điệu:

\[
f_1 < f_2 < f_3 < \dots
\]

Ví dụ:

~~~text
Worker A acquire lease -> fencing token 41
Worker B acquire lease -> fencing token 42
Worker C acquire lease -> fencing token 43
~~~

Mỗi lần gọi sink phải mang token:

~~~json
{
  "resourceId": "report:daily:2026-11-14",
  "fencingToken": 42,
  "operationId": "generate-report-2026-11-14-v42",
  "reportContent": "..."
}
~~~

Nơi nhận dữ liệu lưu **thế hệ cao nhất đã công nhận** hoặc kiểm tra **thế hệ đang có quyền** theo giao thức:

~~~text
sink đã chấp nhận token 42

request token 41 -> REJECT_STALE_OWNER
request token 42 -> xử lý theo điều kiện của cùng owner/operation
request token 43 -> chỉ chấp nhận nếu hợp đồng cấp quyền
                    và quy tắc ghi cho phép thế hệ mới
~~~

Token không nhất thiết là một số nguyên đơn lẻ. Nó có thể là **term + sequence, generation, revision hoặc một giá trị có thứ tự chắc chắn** theo giao thức. Điều thiết yếu là **không tái sử dụng thế hệ cũ và có quy tắc so sánh không mơ hồ trong phạm vi tài nguyên cần bảo vệ**.

## 4. Lịch sử có fencing: tác nhân cũ bị chặn

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant L as Lock/Lease Authority
    participant B as Worker B
    participant S as Fenced Resource
    A->>L: acquire(report)
    L-->>A: lease, token=41
    Note over A: GC pause lâu
    Note over L: Lease 41 hết hạn
    B->>L: acquire(report)
    L-->>B: lease, token=42
    B->>S: write(result B, token=42)
    S-->>B: ACCEPT, maxFence=42
    Note over A: A tỉnh lại
    A->>S: write(result A, token=41)
    S-->>A: REJECT_STALE_FENCE
~~~

Điểm cốt lõi: A có thể gửi lại request. **Không cần trông chờ A tự dừng**; sink chủ động từ chối token đã cũ theo trạng thái nó công nhận.

Một cách minh họa trạng thái của sink:

~~~text
Before:
  report = result A cũ
  highestFence = 40

B writes with token 42:
  report = result B
  highestFence = 42

A writes with token 41:
  rejected
  report vẫn = result B
  highestFence vẫn = 42
~~~

## 5. Quy tắc kiểm tra token cần được định nghĩa chính xác

Một policy thường gặp để **ngăn ghi từ thế hệ thấp hơn sau khi thế hệ cao hơn đã được công nhận**:

~~~text
if token < storedHighestFence:
    reject STALE_FENCE
else:
    atomically apply mutation and update storedHighestFence
~~~

Nếu cùng owner có thể thực hiện nhiều write, token bằng highestFence thường được phép **trong nhiệm kỳ đó**, nhưng vẫn cần xác định operation ID, trạng thái bản ghi, quyền và điều kiện nghiệp vụ.

Nếu mỗi token chỉ được phép dùng **một lần**, policy có thể yêu cầu:

~~~text
token > storedHighestFence
~~~

để lần dùng lại bị từ chối. Nhưng policy này không thích hợp nếu một lease hợp lệ phải cập nhật nhiều lần bằng cùng token.

| Policy | Phù hợp với | Nguy cơ nếu hiểu sai |
|---|---|---|
| **token >= highestSeen** | Nhiều thao tác cùng lease và chống các thế hệ thấp hơn | Retry trong cùng token vẫn có thể gây double effect |
| **token > highestSeen** | Một thao tác/transition duy nhất cho một thế hệ | Các thao tác tiếp theo của cùng owner bị từ chối |
| **token == activeEpoch** | Resource biết chính xác quyền đang hoạt động | Cần đồng bộ nguồn quyền và effect phù hợp |
| **token + operationId + state/version** | Nhiều thao tác nghiệp vụ trong cùng thế hệ | Metadata và kiểm tra phức tạp hơn |

Không có một dấu so sánh **<** hoặc **<=** áp dụng cho mọi bài toán. Hãy viết **sequential specification** của tài nguyên cần bảo vệ.

## 6. Giới hạn rất quan trọng: highestSeen chỉ chặn sau khi thấy token mới

Giả sử:

~~~text
Sink highestFence = 40

A sở hữu lease 41.
Lease A hết hạn.
B nhận lease 42.

B CHƯA gửi request đến sink.
A gửi write với token 41.
~~~

Nếu sink chỉ kiểm:

~~~text
incomingToken >= highestFence
~~~

thì **41 >= 40** và thao tác A có thể được chấp nhận, dù A đã hết lease.

Vậy chính xác hơn:

> So sánh **highestSeen fence tại sink** ngăn một tác nhân **thấp hơn thế hệ đã được sink công nhận** ghi đè sau thế hệ mới. Nó **không tự chứng minh sink biết ngay mọi lần lease expiry hoặc lần cấp token mới ở hệ điều phối**.

Muốn từ chối **mọi thao tác ngay khi quyền hết hạn**, cần thêm một hợp đồng mạnh hơn, chẳng hạn:

- Sink kiểm **active epoch/owner và lease validity** từ nguồn có thẩm quyền bằng cách có thứ tự nhất quán với effect.
- Authority và protected state cùng nằm trong **một phạm vi atomicity/transaction**.
- Protocol buộc **thế hệ mới được đăng ký/fenced ở sink** trước khi các tác nhân cũ có thể tiếp tục ghi theo yêu cầu.
- Hệ đích hỗ trợ **fencing/lease-aware writes** như một phần native protocol.

Nếu kiểm active epoch ở hệ ngoài rồi mới write ở sink khác, có thể xuất hiện **TOCTOU mới**. Hai bước đó không tự trở thành một điều kiện nguyên tử.

Đây là khác biệt giữa **fencing theo thứ tự các thế hệ đã quan sát** và **thu hồi quyền tức thời theo thời gian thực**. Mỗi triển khai cần tuyên bố đúng lời hứa mình bảo đảm.

## 7. Fencing token phải do nguồn có thẩm quyền cấp

Một token đúng cần ít nhất:

1. **Tăng đơn điệu** theo các lần cấp quyền hợp lệ cho cùng resource.
2. **Không tái sử dụng** sau restart, failover hoặc restore trong phạm vi bảo đảm.
3. **Gắn với quyền sở hữu/lease** được cấp qua một protocol có kiểm soát.
4. **So sánh được** bởi sink mà không dựa vào timestamp tùy ý của client.
5. Có cách **phát hiện token giả, scope sai hoặc bị replay**, tùy mô hình tin cậy.
6. Được sinh **nguyên tử cùng quyết định cấp quyền** hoặc theo một quy trình bảo đảm không tạo hai owner cạnh tranh hợp lệ.

Điểm thường được bỏ qua: **một counter tăng độc lập chưa tạo ra lock authority an toàn**. Nếu cả A lẫn B tự lấy số 41/42 nhưng không có quy tắc ai thực sự sở hữu tài nguyên, các token ấy chỉ là số thứ tự, chưa chắc là bằng chứng quyền.

## 8. Không tự dùng đồng hồ tường làm fencing token

Một thiết kế sai:

~~~text
fencingToken = currentTimeMillis()
~~~

Hai server có thể có đồng hồ lệch:

~~~text
Worker A thực hiện trước nhưng đồng hồ đi nhanh:
  token = 1000500

Worker B nhận quyền sau nhưng đồng hồ chậm:
  token = 1000100
~~~

Nếu sink so số lớn hơn, token cũ A vẫn có thể trông “mới” hơn B.

Ngoài ra:

- Clock có thể bị chỉnh bởi NTP.
- Hai request có thể cùng millisecond.
- Host mới có đồng hồ sai.
- Timestamp tăng không chứng minh quyền sở hữu đã được cấp.

**Fencing cần thứ tự do authority/giao thức xác lập**, không phải một timestamp client tự tuyên bố.

## 9. Counter tăng đơn điệu và consensus

Một cách xây dựng nguồn token là giữ **counter per resource** trong một kho có thao tác cập nhật nguyên tử và bảo đảm phù hợp:

~~~text
Acquire(resource K):
  transaction:
    nếu current lease không hợp lệ hoặc đã hết hạn:
      token := previousToken + 1
      owner := newWorkerId
      leaseId := newLeaseId
      expiresAt := ...
      return token, leaseId
    ngược lại:
      reject BUSY
~~~

Nếu hệ dùng **consensus** để quyết định thứ tự các lần acquire, các generation được cấp có thể gắn với **log index/term/revision** theo hợp đồng sản phẩm.

Những điều cần xác minh:

- Hai acquire cạnh tranh không cùng thành công cho cùng quyền độc quyền.
- Token không giảm khi leader failover.
- Counter đã công nhận không bị rollback sau restart/snapshot restore.
- Client timeout lúc acquire có thể xác minh **token nào, owner nào** thực sự được cấp.
- Một lease renewal **không tùy tiện tạo token mới** nếu contract coi nó là cùng một nhiệm kỳ.

**Consensus không có nghĩa mọi API trên cùng cluster đều linearizable**; phải xem đúng loại operation/read mode được dùng để cấp token.

## 10. Tách resource scope và phạm vi thứ tự

Một token có thể tăng **theo từng resource**:

~~~text
report:daily:2026-11-14
  41, 42, 43, ...

report:daily:2026-11-15
  12, 13, 14, ...
~~~

Hoặc dùng một generation toàn namespace nếu allocator hỗ trợ.

Điều quan trọng là sink so sánh token **đúng scope**:

~~~text
(resourceId, fencingToken)
~~~

Token 42 của report ngày 14 không có ý nghĩa lớn hơn token 13 của report ngày 15 nếu hệ chỉ bảo đảm thứ tự **trong từng resource**.

Key cần xác định rõ:

- tenantId.
- logical resourceId.
- operation type.
- ownership scope.
- topology/allocator epoch nếu có.

Thiếu tenant scope có thể gây **nhầm token giữa hai khách hàng**, còn dùng global counter không cần thiết có thể tạo hot key.

## 11. Fencing token khác lock ID, lease ID và UUID thế nào?

| Giá trị | Dùng để làm gì? | Có thứ tự tăng không? |
|---|---|---|
| **Lock name** | Chọn tài nguyên cần bảo vệ | Không |
| **Owner ID** | Định danh worker/tiến trình | Không nhất thiết |
| **Lease ID** | Theo dõi vòng đời lease | Không nhất thiết |
| **Random UUID** | Phân biệt hai lần acquire/operation | Không có thứ tự số học đáng tin |
| **Fencing token** | Xếp thứ tự thế hệ quyền và chặn thế hệ cũ | Phải có quan hệ thứ tự phù hợp |
| **Version của data record** | Optimistic concurrency trên dữ liệu | Có thể tăng nhưng không mặc nhiên là quyền sở hữu |
| **Operation ID** | Dedup retry của một ý định | Không nhất thiết |
| **Term/epoch** | Đánh dấu nhiệm kỳ/protocol generation | Có thể là thành phần fence |

Một **UUID ngẫu nhiên** đủ để xác thực “chính owner đã tạo lock thì mới được release lock”, nhưng **không đủ** để sink phân biệt owner A đã cũ hay B mới nếu không có nguồn active-owner đáng tin.

Fencing token và operation ID thường được dùng **cùng nhau**, vì chúng giải quyết hai bài toán khác.

## 12. Fencing khác optimistic locking/CAS

**Optimistic locking** thường bảo vệ một record khỏi ghi đè phiên bản dữ liệu mới:

~~~text
record.version = 7

UPDATE record
IF version == 7:
    set payload, version = 8
~~~

**Fencing** bảo vệ quyền của **tác nhân**:

~~~text
Worker A có generation 41.
Worker B có generation 42.

Sink đã công nhận generation 42.
Mọi mutation từ 41 phải bị từ chối.
~~~

Chúng thường kết hợp:

~~~text
Write accepted iff:
  token không cũ hơn generation được bảo vệ
  AND recordVersion khớp expectedVersion
  AND businessState cho phép transition
  AND operationId chưa áp dụng (nếu cần)
~~~

Một **CAS đúng trên chính record đích** có thể đã ngăn nhiều race mà fencing muốn ngăn. Nhưng trong workflow dài có lease, các thao tác trên **nhiều tài nguyên hoặc external side effects** vẫn cần xem tác nhân nào được phép làm gì, và nơi nào thực thi điều kiện đó.

## 13. Fencing khác idempotency

Hai request:

~~~text
A, token 41, operationId export-9001
B, token 42, operationId export-9002
~~~

**Fencing**: không cho A 41 ghi đè sau khi thế hệ B 42 đã được sink công nhận.

**Idempotency**: nếu B 42 gửi lại **export-9002** vì response timeout, sink không thực hiện hiệu ứng **export-9002** lần thứ hai.

Một token 42 hợp lệ có thể được dùng để:

~~~text
INCR counter +1
INCR counter +1   // retry cùng operation
~~~

Nếu chỉ kiểm token >= highestSeen, cả hai lệnh vẫn có thể tăng. Vì thế:

> **Fencing bảo vệ thứ tự quyền. Idempotency bảo vệ số lần áp dụng một ý định.**

Đối với payment, reserve stock hoặc gửi notification, không thể thay thế idempotency bằng fencing.

## 14. Fencing phải được thực thi tại nơi có effect

Giả sử:

~~~text
Lock service: etcd
Protected data: Object storage
Worker: Java service
~~~

Worker có token 42 từ etcd, nhưng ghi object storage bằng lệnh PUT không có điều kiện. Nếu object storage không kiểm token:

~~~text
A(token 41) PUT report
B(token 42) PUT report
A(token 41) PUT report lần nữa
~~~

thì object có thể bị ghi đè bởi A. **Gắn token vào log message nhưng sink bỏ qua token không có tác dụng bảo vệ**.

Các chiến lược:

1. **Native conditional write** nếu tài nguyên hỗ trợ predicate trên version/generation có thẩm quyền.
2. **Atomic fenced row/document update** nếu effect nằm trong cùng database.
3. **Fenced gateway** duy nhất nhận mutation rồi kiểm token và chuyển effect theo một protocol không tạo race mới.
4. **Immutable outputs + atomic pointer/version switch**: worker ghi artifact bất biến riêng, rồi chỉ cập nhật pointer “current” bằng CAS/fencing.
5. **Reconciliation và idempotency** cho hệ ngoài không hỗ trợ fencing/transaction chung.

Không nên nói “gateway có kiểm token trước khi PUT” là đủ nếu **check ở gateway** và **PUT bên ngoài** có thể bị đảo thứ tự sau khi gateway mất quyền.

## 15. Mẫu an toàn: immutable artifact và fenced pointer

Giả sử hai worker xuất báo cáo:

~~~text
Worker A (token 41):
  ghi reports/2026-11-14/run-41.json

Worker B (token 42):
  ghi reports/2026-11-14/run-42.json
~~~

Hai tệp là **immutable, có tên riêng**, nên A không thể ghi đè bytes của B nếu quyền ghi được giới hạn đúng đường dẫn.

Một record nhỏ quản lý bản hiện hành:

~~~json
{
  "reportId": "daily:2026-11-14",
  "currentObject": "reports/2026-11-14/run-42.json",
  "highestFence": 42
}
~~~

Sink cập nhật **currentObject + highestFence** bằng một mutation nguyên tử có điều kiện. Sau khi token 42 được công nhận, request token 41 không thể chuyển pointer về run-41.

Ưu điểm:

- Artifact cũ có thể vẫn tồn tại để audit nhưng không được xem là current.
- Không cần một transaction giữa ghi object bytes và cập nhật pointer nếu giao thức chấp nhận orphan artifacts.
- Xác nhận pointer chỉ sau khi artifact được ghi hoàn chỉnh và kiểm tra integrity.
- Cleanup orphan artifacts là công việc riêng, không được xóa artifact đang được trỏ tới.

**Tính đúng của thao tác publish nằm ở pointer có fencing**, không phải ở việc hai worker đều đã tạo một tệp.

## 16. Mẫu đơn giản của fenced write

Trạng thái:

~~~text
resource R:
  value = initial
  highestFence = 40
~~~

Pseudocode:

~~~text
function fencedWrite(resourceId, token, operationId, value):
    atomic transaction on protected resource:
        record = read(resourceId)

        if token < record.highestFence:
            return STALE_OWNER

        if operationId already applied:
            return PREVIOUS_RESULT

        verifyBusinessPrecondition(record, value)
        write value
        set highestFence = max(record.highestFence, token)
        record operationId and result

    return SUCCESS
~~~

**Yêu cầu thiết yếu:** kiểm token, áp dụng effect và cập nhật highestFence phải có **một ranh giới atomicity hoặc giao thức đồng bộ đủ mạnh**. Nếu đọc highestFence rồi ghi payload không điều kiện:

~~~text
check(token 41) -> pass
B(token 42) commits
A(token 41) writes payload
~~~

thì vẫn xảy ra race.

Một số hệ đích chỉ hỗ trợ optimistic CAS trên một record; khi CAS thất bại, ứng dụng phải đọc lại trạng thái và phân biệt **fence stale** với **business version conflict**.

## 17. MongoDB: fenced update trong một document

Nếu **protected state và highestFence cùng nằm trong một document MongoDB**, một conditional update có thể thực hiện phép kiểm tại nguồn.

Ví dụ document:

~~~javascript
{
  _id: "report:daily:2026-11-14",
  currentObject: "reports/old.json",
  highestFence: NumberLong(40),
  lastOperationId: "run-40"
}
~~~

Worker B với token 42:

~~~javascript
const token = NumberLong(42);

const result = db.reportPointers.updateOne(
  {
    _id: "report:daily:2026-11-14",
    highestFence: { $lte: token }
  },
  {
    $set: {
      currentObject: "reports/2026-11-14/run-42.json",
      highestFence: token,
      lastOperationId: "run-42"
    }
  },
  {
    writeConcern: { w: "majority" }
  }
);

printjson(result);
~~~

Sau khi thành công, A dùng token 41:

~~~javascript
db.reportPointers.updateOne(
  {
    _id: "report:daily:2026-11-14",
    highestFence: { $lte: NumberLong(41) }
  },
  {
    $set: {
      currentObject: "reports/2026-11-14/run-41.json",
      highestFence: NumberLong(41)
    }
  }
);
~~~

Nếu document đang có highestFence=42, filter của A không match và A không thể ghi đè bằng lệnh này.

### Giới hạn ví dụ

- Cần **khởi tạo document và field highestFence có type chuẩn**, không cho một đường upsert thiếu điều kiện tự tạo lại record thấp hơn.
- Update trên **một document** là atomic trong phạm vi MongoDB hỗ trợ; nếu pointer và highestFence nằm ở **hai documents** thì hai update riêng không còn tự nguyên tử.
- Token 42 có thể lặp lại; code trên **không phải idempotency đầy đủ** cho những thao tác nhiều effect.
- Majority write concern cần chọn theo durability/failover contract; không dùng một read stale từ secondary để quyết định owner.
- Token phải được cấp bởi **authority đáng tin**. Một client tự gửi token 999 không được mặc nhiên xem là owner có quyền.
- Cần kiểm tra **matchedCount/modifiedCount** và lỗi; write timeout có thể có outcome UNKNOWN.

## 18. MongoDB: cấp token và lease trong một record quyền

Giả sử collection **resourceLeases** có document:

~~~json
{
  "_id": "report:daily:2026-11-14",
  "generation": 41,
  "owner": "worker-A",
  "leaseId": "lease-41",
  "leaseExpiresAt": "2026-11-14T10:00:30Z"
}
~~~

Một thiết kế acquire cần thực hiện **kiểm tra lease hiện hành, tăng generation và ghi owner/leaseId** trong cùng một transaction hoặc atomic conditional operation phù hợp.

Pseudocode:

~~~text
ACQUIRE(resourceId, workerId):
  atomic conditional mutation on resourceLeases[resourceId]:
    condition:
      lease đang trống hoặc đã được authority xác định hết hạn
    effect:
      generation := generation + 1
      owner := workerId
      leaseId := freshLeaseId()
      leaseExpiresAt := newExpiry
    return generation, leaseId
~~~

Đừng biến **đồng hồ của client** thành nguồn phán quyết cuối về hết hạn. Nếu dùng timestamp trong MongoDB, phải hiểu nguồn thời gian, clock skew, consistency của predicate và cách hệ điều phối xử lý đồng thời. Một conditional update đúng predicate nhưng dựa trên thời gian sai vẫn có thể cấp quyền không đúng ý định.

Với resource thực nằm ở collection khác, **acquire và fenced write vẫn là hai thao tác tách rời**. Sink cần thực thi guard phù hợp; không suy rằng vì token được cấp trong MongoDB nên mọi external write tự an toàn.

## 19. DynamoDB: ConditionExpression làm guard tại item đích

DynamoDB cho phép conditional writes trên một item. Với một protected item:

~~~text
PK = RESOURCE#daily-report#2026-11-14
highestFence = 42
currentObject = "run-42.json"
~~~

Một UpdateItem mang token 41 có thể dùng:

~~~text
Key:
  PK = "RESOURCE#daily-report#2026-11-14"

ConditionExpression:
  attribute_not_exists(#fence) OR #fence <= :token

UpdateExpression:
  SET #fence = :token,
      #current = :object

ExpressionAttributeNames:
  #fence = "highestFence"
  #current = "currentObject"

ExpressionAttributeValues:
  :token = Number(41)
  :object = "run-41.json"
~~~

Khi highestFence=42, điều kiện sai và write bị từ chối bằng lỗi điều kiện theo API.

Các điểm phải thiết kế:

- Nếu item **chưa tồn tại**, điều kiện attribute_not_exists cho phép bootstrap; cần quyền và quy tắc khởi tạo chính xác.
- **Không cho token thấp tự reset resource** sau Delete/recreate nếu cần bảo toàn high-watermark.
- ConditionExpression và UpdateExpression của cùng item tạo điều kiện cập nhật nguyên tử trong phạm vi DynamoDB hỗ trợ.
- Có thể thêm **version/status predicate** và operationId để giữ invariant và chống retry.
- Với multi-item effects, cần xem **TransactWriteItems** và giới hạn cụ thể; UpdateItem một item không biến hệ ngoài thành transaction.
- Strongly consistent read và transaction đa Region có phạm vi/giới hạn riêng; GSI eventual không thay thế nguồn quyết định.

Nếu token allocator và sink là hai items riêng, việc đọc active token ở item allocator rồi UpdateItem trên sink có thể tạo TOCTOU. Cần transaction/condition hoặc protocol khác nếu hợp đồng đòi biết quyền đang hoạt động tại thời điểm mutation.

## 20. DynamoDB: cấp quyền và generation trong một item

Một item lease:

~~~text
PK = LEASE#daily-report#2026-11-14
generation = 41
owner = worker-A
leaseId = lease-41
expiresAt = ...
~~~

Acquire có thể được diễn đạt bằng **conditional update**:

~~~text
if lease is free or expired under a reliable policy:
  generation := generation + 1
  owner := newWorker
  leaseId := newLeaseId
  expiry := newExpiry
else:
  reject BUSY
~~~

Đây là logic khái niệm, không phải payload API có thể chạy ngay. Cần định nghĩa cách xác định **expired** sao cho không phụ thuộc một giả định sai về thời gian client và không có hai acquire cùng thành công.

**Atomic increment** của generation nên nằm trong cùng quyết định nhận quyền, không được thực hiện bởi client trước rồi mới kiểm xem nó có lock. Những generation bị bỏ qua thường không gây hại, nhưng một token được phát không có quyền và một worker tự tuyên bố thành công có thể phá security nếu sink chỉ so số lớn nhất.

## 21. Cassandra: LWT và CAS thay vì ghi đè theo timestamp

Trong Cassandra, ordinary write/read consistency như QUORUM **không tự biến hai lệnh SELECT rồi UPDATE thành một CAS**. Muốn bảo vệ condition trên một row/partition, có thể dùng **lightweight transactions (LWT)** trong phạm vi API.

Ví dụ schema:

~~~sql
CREATE TABLE report_pointer_by_id (
    report_id text PRIMARY KEY,
    highest_fence bigint,
    current_object text
);
~~~

Giả sử record có:

~~~text
report_id = "daily:2026-11-14"
highest_fence = 42
current_object = "run-42.json"
~~~

Một thao tác compare-and-set:

~~~sql
UPDATE report_pointer_by_id
SET highest_fence = 43,
    current_object = 'run-43.json'
WHERE report_id = 'daily:2026-11-14'
IF highest_fence = 42;
~~~

Ứng dụng phải kiểm tra **[applied]**. Nếu một worker khác đã thay đổi highest_fence, CAS thất bại.

### Vậy token 41 bị chặn thế nào?

Một worker không nên tự đọc current rồi blind write. Protocol cần:

1. Đọc highestFence/row state theo cách phù hợp.
2. Kiểm tra **incoming token không cũ hơn highestFence** và token thực sự được cấp.
3. Chỉ cập nhật bằng **LWT có điều kiện trên giá trị đã đọc**.
4. Nếu [applied]=false, đọc lại và quyết định reject/retry.

Nếu dùng ordinary UPDATE không điều kiện, Cassandra có semantics timestamp/conflict cho ordinary cells; một timestamp lớn từ tác nhân cũ có thể phá ý định fence. Để guard chắc chắn, phải sử dụng một cơ chế conditional/transaction và quyền cấp token phù hợp.

**LWT có phạm vi và chi phí riêng**, không tự tạo một transaction nguyên tử với S3, payment provider hoặc mọi partition khác.

## 22. Redis: SET NX PX không tự cung cấp fencing

Một khóa Redis phổ biến:

~~~redis
SET lock:daily-report lease-abc NX PX 30000
~~~

Nó giúp chỉ một client tạo lock key khi key chưa tồn tại trong phạm vi instance/protocol, nhưng giá trị **lease-abc** có thể chỉ là UUID dùng để release đúng owner.

Timeline:

~~~text
A SET NX -> OK.
A pause > TTL.
B SET NX -> OK.
B write protected resource.
A resume -> write protected resource.
~~~

TTL của Redis không tự khiến sink biết A đã mất quyền.

Một ý tưởng là cấp fencing generation bằng **INCR**:

~~~redis
INCR fence:daily-report
~~~

nhưng phải hết sức thận trọng:

- **INCR riêng và SET lock riêng** không tự là một quyết định cấp quyền nguyên tử.
- Redis replication có thể bất đồng bộ; failover/persistence config có thể không bảo vệ tính **monotonic không tái sử dụng** qua mọi lỗi.
- Dùng **WAIT** hoặc cơ chế replica acknowledgement khác không tự biến Redis thành consensus allocator với mọi guarantee mong muốn.
- Một lần lấy token cao không chứng minh client giữ lock hợp lệ.
- Sink vẫn phải kiểm và từ chối token cũ.

Có thể dùng Redis trong những hệ chấp nhận giới hạn rủi ro tương ứng, hoặc xây protocol và durability phù hợp. Nhưng **không được tuyên bố Redlock/SET NX PX tự cấp fencing token tăng đơn điệu**; token random phục vụ nhận diện owner là khái niệm khác.

## 23. Redis: release lock an toàn và giới hạn của nó

Một lỗi khác là A hết lease rồi gọi DELETE, vô tình xóa khóa mới của B:

~~~text
A lock value = lease-A
lease A hết hạn
B lock value = lease-B
A DEL lock
-> xóa khóa B
~~~

Do đó release phải là **compare owner ID rồi delete nguyên tử** trong phạm vi Redis hỗ trợ:

~~~lua
-- KEYS[1] = lock key
-- ARGV[1] = leaseId của caller
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
end
return 0
~~~

Đây là biện pháp **không xóa lock của người khác**. Nó vẫn **không từ chối các ghi của A vào một tài nguyên ngoài Redis** khi A đã mất quyền. Đừng lẫn:

- Correct release: không xóa lease của B.
- Lease expiry: cho phép B có thể acquire.
- Fencing at sink: từ chối mutation từ A khi A không còn hợp lệ theo contract.

Ba việc bổ sung cho nhau nhưng không thay thế nhau.

## 24. etcd: revision/lease và giao dịch có điều kiện

**etcd** là một ví dụ của KV store dùng consensus để điều phối metadata. Nó có:

- **Lease** với TTL và cơ chế keep-alive.
- **Transaction (Txn)** dùng compare-then-put/delete.
- **Revision metadata** trên keys để theo dõi thứ tự thay đổi.
- Các API lock/coordination theo protocol.

Một thiết kế lock có thể lưu key:

~~~text
/locks/reports/daily-2026-11-14/<owner-key>
~~~

với lease gắn vào key. Trong các triển khai lock dùng **creation revision** hoặc thứ tự tạo key để quyết định owner, revision liên quan có thể được dùng làm **fencing generation**, nếu đúng bảo đảm của protocol.

Ví dụ khái niệm:

~~~text
1. Worker đăng ký lock candidate dưới lease.
2. Chờ đến lượt sở hữu hợp lệ.
3. Lấy fencing token là revision/generation theo giao thức.
4. Gửi token trong mọi request đến protected sink.
5. Sink dùng atomic predicate để reject generation thấp.
~~~

### Các caveat

- **Không dùng một revision ngẫu nhiên của một thao tác không liên quan** như bằng chứng quyền sở hữu.
- Cần phân biệt **create revision, mod revision, lease ID** và quyền lock thực tế.
- Client mất kết nối không tự biết chắc lease còn sống; phải xử lý renew/uncertain state.
- Có một Txn trong etcd không tự tạo transaction với Redis, MongoDB hay object storage.
- Nếu token bị reset do restore/di chuyển coordination namespace, sink có thể giữ highestFence cao hơn và reject mọi token mới; cần kế hoạch epoch/restore nhất quán.

Khi toàn bộ protected state ở **chính etcd**, Txn compare current owner/revision và cập nhật protected key trong cùng transaction có thể mạnh hơn cách gửi token sang hệ ngoài.

## 25. ZooKeeper: ephemeral sequential nodes và thứ tự quyền

Trong ZooKeeper, một công thức distributed lock quen thuộc dùng **ephemeral sequential znodes**:

~~~text
/locks/report-77/lock-0000000041
/locks/report-77/lock-0000000042
/locks/report-77/lock-0000000043
~~~

Ứng viên có sequence phù hợp theo thuật toán chờ/quan sát predecessor được cấp lượt. **Session expiry** làm ephemeral znode biến mất, nhưng client cũ có thể vẫn chạy vì không kịp biết session đã hết.

Sequence/generation có thể cung cấp một thứ tự để fencing nếu:

- Token thuộc đúng namespace/lock scope.
- Chỉ worker thực sự đến lượt acquire được xem là owner.
- Thứ tự không bị tái sử dụng trong vòng đời cần bảo vệ.
- Parent znode/namespace không bị xóa rồi tạo lại khiến sequence được reset mà sink vẫn giữ history cũ.
- Sink nhận token và thực thi compare guard.

Một **sequence number của contender** không tự là giấy phép ghi trước khi contender trở thành owner; phải phân biệt **được cấp số thứ tự** và **đã giành quyền lock**.

## 26. Kafka consumer generation và các worker xử lý message

Một worker đọc một partition từ broker:

~~~text
Consumer A được gán partition 3.
A pause lâu.
Group rebalance.
Consumer B nhận partition 3.
A tỉnh lại, tiếp tục gửi update ra sink.
~~~

Đây là một biến thể của stale owner. Cơ chế **consumer group generation/member fencing** có thể chặn một số thao tác với broker theo protocol, nhưng **không tự chặn mọi external write** đã bị A gửi đến database.

Một thiết kế downstream:

~~~text
Sink key = (topic, partition, aggregateId)
OwnerGeneration = generation được broker/authority công nhận
Write:
  require generation phù hợp
  require event offset/operationId chưa được xử lý
  apply transition atomically
~~~

Không được mặc định **Kafka offset** chính là fencing token của quyền consumer:

- Offset mô tả vị trí event trong partition, không trực tiếp mô tả **nhiệm kỳ owner**.
- Group assignment generations và transaction producer epochs có ý nghĩa khác.
- Offset checkpoint, event dedup và owner fencing phải được thiết kế theo phạm vi đúng.

Khi xử lý events idempotent từ durable log, **version hoặc event sequence của aggregate** còn có thể quan trọng hơn quyền worker cho tính đúng của trạng thái nguồn.

## 27. Kubernetes Lease và resourceVersion

Một Kubernetes controller có thể tham gia leader election qua **Lease object**. Controller hết lease vẫn có thể đang chạy hoặc đang có request đến API/DB khác.

Một số hiểu nhầm:

- Lease renewal thành công không tạo atomic transaction với protected data bên ngoài.
- Kubernetes **metadata.resourceVersion** là token cho cơ chế concurrency/watch của API server theo hợp đồng của nó, **không nên tùy tiện parse/so sánh như một số fencing tăng đơn điệu toàn cục cho mọi object**.
- Tên pod, UID hoặc thời điểm pod khởi động không tự tạo thứ tự quyền.

Nếu controller cần bảo vệ mutation trên một record trong database, hãy dùng generation/term được cấp theo protocol phù hợp và **CAS/conditional update tại database**, hoặc dùng một nguồn sở hữu có transaction với resource được bảo vệ.

## 28. Token cần được lưu bền ở sink

Giả sử sink đã lưu:

~~~text
highestFence = 42
~~~

Sau crash, nếu sink khởi tạo trở lại:

~~~text
highestFence = 0
~~~

thì worker A với token 41 có thể được nhận lại.

Vì thế trạng thái fence phải:

- Được lưu theo durability cần thiết.
- Được sao chép theo guarantee phù hợp failover.
- Không bị xóa khi data record TTL hoặc cache eviction nếu vẫn cần bảo vệ resource.
- Không reset khi restore từ backup cũ mà không có kế hoạch epoch/authority.
- Được cập nhật **cùng effect** hoặc qua protocol an toàn.

Nếu một sink mới được tạo từ snapshot cũ, cần **bước bootstrap/rehydration** bảo đảm high-watermark không lùi sau các thế hệ đã công nhận.

### “Thay sink” cũng phải duy trì thế hệ

Nếu protected file chuyển từ storage A sang storage B, storage B không biết token 42. Một cách an toàn có thể là **chuyển cùng metadata fence** hoặc có authority kiểm tra active generation trước khi cho write, với cutover protocol không tạo khoảng nhận token cũ.

## 29. Token có thể bị giả hoặc sử dụng sai scope

Một request:

~~~json
{
  "resourceId": "report:daily:2026-11-14",
  "fencingToken": 999999,
  "payload": "malicious update"
}
~~~

Nếu sink chỉ kiểm “token lớn hơn highestFence” và client không được xác thực, bất kỳ ai cũng có thể gửi token lớn để chặn những owner hợp lệ khác (**fence poisoning**).

Phải có mô hình tin cậy:

- Chỉ dịch vụ đã xác thực được gọi sink.
- Sink biết token được cấp bởi authority đáng tin hoặc token được ký/xác minh theo giao thức.
- Owner, resource, tenant và token có scope gắn nhau.
- Không lộ quyền của tenant A sang tenant B.
- Không nhận token cao mà không có điều kiện cấp quyền/authorization cần thiết.
- Có giới hạn kiểu số và overflow; token quá lớn không được làm allocator tê liệt.

**Fencing token là metadata để enforce quyền**, không nên coi nó là một **secret bearer token** thay thế authn/authz.

## 30. Token tăng đơn điệu nhưng reset khi restore

Một lỗi vận hành nguy hiểm:

~~~text
Trước disaster:
  allocator đã cấp token 1000.
  sink đã lưu highestFence 1000.

Khôi phục allocator từ snapshot cũ:
  counter chỉ còn 900.

Worker mới nhận token 901.
Sink reject vì 901 < 1000.
~~~

Nếu bỏ điều kiện ở sink để “chạy lại cho được”, hệ mở đường cho tác nhân cũ.

Các hướng thiết kế:

- Restore coordination state và sink theo recovery protocol bảo vệ generation.
- Dùng **epoch mới được cấp bền vững**, token dạng **(allocatorEpoch, sequence)** theo thứ tự từ điển đúng giao thức.
- Khi rotate namespace/authority, có bước chuyển quyền với guard trên protected resources.
- Không tái cấp token bằng cách reset counter về 0.
- Có runbook xử lý “new token lower than sink high-watermark” thay vì tự ý hạ fence.

Lưu ý: tăng **epoch** cũng phải được cấp và lưu một cách không lùi. Chỉ cộng số vào hostname hoặc deployment version không chứng minh thế hệ mới có quyền.

## 31. Token không giải quyết mọi race giữa nhiều resource

Workflow:

~~~text
Worker B token 42:
  1. ghi object storage
  2. update database status
  3. publish event
~~~

Giả sử mỗi nơi tự lưu highestFence riêng. Thứ tự quan sát có thể khác:

~~~text
Object storage đã thấy token 42.
Database status mới chỉ thấy token 41.
Message consumer chưa thấy token 42.
~~~

Một fence trên object storage **không tự chặn** A ghi vào database status nếu database chưa enforce thế hệ mới.

Với side effects xuyên nhiều hệ:

1. Chọn **nguồn truth** của quyết định.
2. Tách **prepare immutable output** khỏi **commit/publish pointer**.
3. Bảo vệ điểm commit bằng CAS/fencing.
4. Dùng **outbox/inbox** để phát và tiêu thụ event idempotent.
5. Dùng Saga/reconciliation nếu provider ngoài không thể tham gia transaction.

Không được tuyên bố “đã có fencing” mà không chỉ ra **từng sink nào kiểm token**, guard nào atomic và những hiệu ứng nào vẫn có thể đi qua.

## 32. Pending write đến muộn: phải xem thời điểm commit

Một worker A còn lease khi **gửi** request, nhưng request bị network delay:

~~~text
t1: A token 41 gửi write, lease còn hiệu lực.
t2: Lease 41 hết hạn.
t3: B nhận token 42.
t4: B write thành công tại sink.
t5: Request cũ của A mới đến sink.
~~~

Nếu sink đã ghi highestFence=42 ở t4, request của A token 41 phải bị từ chối ở t5.

Điểm quan trọng: **thời điểm gửi không đồng nghĩa thời điểm effect được chấp nhận**. Sink phải thực thi guard tại chỗ, không tin một timestamp trong request:

~~~text
"sentAt": "trước khi lease hết hạn"
~~~

Một client có thể tự khai sentAt, còn mạng có thể trì hoãn request. Fencing dùng **thế hệ quyền đã được sink công nhận**, không suy từ thông tin này.

## 33. So sánh fencing với giết tiến trình cũ

Một thiết kế khác có thể cố dừng worker cũ:

~~~text
Lease hết hạn -> gửi kill/terminate tới worker A.
~~~

Vấn đề:

- Worker A có thể offline nên không nhận kill.
- OS có thể trì hoãn scheduling.
- Một HTTP request đã gửi từ A có thể còn in-flight.
- Side effect tới hệ ngoài có thể được retry bởi proxy/broker khác.
- Worker có thể ở vùng mạng bị chia cắt, không quan sát lệnh điều khiển.

**Killing old worker** có thể giảm công việc thừa, nhưng không cung cấp bằng chứng sink sẽ từ chối mọi request đã đến muộn.

Fencing đặt guard tại tài nguyên, giúp bảo vệ trước những tiến trình cũ không thể kiểm soát trực tiếp.

## 34. Fencing và distributed lock cho cron job

Giả sử cron **CloseMonthlyInvoices** chạy trên nhiều pods:

~~~text
Pod A lock -> token 57
Pod B chờ
A bị suspend
Lease A hết
B lock -> token 58
~~~

Thiết kế đơn giản nhưng sai:

~~~text
if (holdLock):
  for each invoice:
    closeInvoice()
~~~

Thiết kế tốt hơn:

~~~text
Acquire lease -> fencingToken
For each invoice:
  closeInvoice(
    expectedState=OPEN,
    expectedOwnerGeneration=fencingToken,
    operationId="close:" + invoiceId + ":" + period
  )
~~~

Đối với invoice, nguồn phải kiểm tra business state và dedup. Nếu invoice đã **CLOSED**, một lần chạy lại phải không phát hành charge hai lần.

Điều này còn giải thích vì sao một cron lock duy nhất không thể bảo vệ đầy đủ hàng nghìn external operations nếu mỗi operation không có conditional/idempotent semantics.

## 35. Fencing trong object storage: không phải mọi API hỗ trợ token tùy ý

Một object store có thể hỗ trợ **ETag/conditional PUT**, object versioning hoặc precondition khác, nhưng không nhất thiết có sẵn:

~~~text
PUT object IF fencingToken >= highestFence
~~~

Các lựa chọn:

- Nếu object version/ETag được dùng làm CAS, client phải lấy đúng expected version và xử lý precondition failure.
- Lưu **manifest/pointer record** trong database hỗ trợ conditional update và đưa các artifacts về đường dẫn immutable.
- Hạn chế write trực tiếp vào đường dẫn “current” từ các workers.
- Nếu protected resource đòi quyền active epoch, đưa guard cùng nơi commit hoặc protocol liên kết với authority.

**Ghi token vào metadata của object không tự khiến storage so token**. Cần kiểm tra tài liệu API thật sự hỗ trợ predicate nào, phạm vi atomicity và cách versioning/failover hoạt động.

## 36. Khi external API không hỗ trợ fencing

Ví dụ payment provider chỉ có:

~~~text
POST /capture(paymentIntentId)
~~~

nó không hiểu trường fencingToken.

Một worker A hết quyền có thể vẫn gọi capture. Không thể đảm bảo provider từ chối A chỉ vì bạn đã có token ở etcd.

Cách tiếp cận:

1. Đặt một **authoritative state machine** cho paymentIntent trong DB.
2. Chỉ một command với **idempotency key ổn định** được gửi cho một ý định capture.
3. Worker A/B phải tranh chấp một **conditional claim** trước khi điều phối command.
4. Dùng **outbox** để đảm bảo command không mất giữa commit và publish.
5. Đối soát provider khi outcome UNKNOWN.
6. Nếu cần cấm stale worker sau owner change, mọi đường gửi provider phải đi qua một gateway có guard thích hợp; cần hiểu giới hạn TOCTOU với provider ngoài.

**Fencing ở DB không thay cho idempotency và reconciliation ở payment provider**. Khi không có atomic transaction xuyên hệ, thiết kế phải mô tả các trạng thái đang chờ/không rõ kết quả.

## 37. Fencing với queue worker và kết quả tính toán

Một job tính toán nặng có thể kéo dài hàng phút:

~~~text
Job ID: embedding-index:tenant-A:v5
Worker A token 71 bắt đầu
Worker A bị pause
Worker B token 72 làm lại
Worker B hoàn tất
Worker A hoàn tất muộn
~~~

Không nhất thiết phải hủy toàn bộ tính toán của A, miễn:

- A ghi kết quả vào **artifact immutable riêng**.
- B cũng ghi artifact riêng.
- Chỉ một **publish pointer** được cập nhật bằng fenced compare.
- Artifact chưa publish có thể được dọn sau.

Thiết kế này thường dễ bảo vệ hơn việc cho cả hai worker cập nhật cùng một tập records **trong khi** xây index.

Nếu cần ghi từng phần vào data store chia sẻ, từng mutation hoặc batch phải mang token/expected generation, không chỉ kiểm quyền ở đầu job.

## 38. Fencing và heartbeat/renew lease

Worker thường renew:

~~~text
lease TTL = 30s
renew every 10s
~~~

Renew có thể thất bại do:

- Mạng chập chờn.
- Coordinator mất quorum.
- Process pause.
- Credential hết hạn.
- Lease đã thực sự bị cấp cho owner khác.

Khi renew trả kết quả **UNKNOWN**, worker không được mặc định mình vẫn có quyền vô hạn. Nhưng cũng không nên nghĩ việc dừng local worker lập tức **thu hồi mọi request đã gửi**.

Một thiết kế có thể:

- Đưa worker vào trạng thái **UNSAFE_TO_PUBLISH** nếu không xác nhận được lease.
- Ngừng tạo side effects mới khi không còn bằng chứng sở hữu.
- Cho phép tính toán local tiếp tục nếu không gây hại.
- Yêu cầu guard tại sink khi publish.
- Kiểm tra/cập nhật leaseId và token trước những bước quan trọng.

**Ngừng ở client và fencing tại sink là hai lớp bảo vệ bổ trợ**.

## 39. Dùng lease expiry ở sink có dễ không?

Nếu sink lưu:

~~~text
activeToken = 42
expiresAt = ...
~~~

có thể muốn:

~~~text
accept iff incomingToken == activeToken
           AND now < expiresAt
~~~

Điều kiện này mạnh hơn chỉ so highestSeen, nhưng đúng khi:

- Sink có **nguồn thời gian/phán quyết lease** được định nghĩa chắc chắn.
- Condition và mutation diễn ra **nguyên tử** trong phạm vi sink.
- Renew/cấp lease mới cập nhật state theo protocol không có race.
- Clock skew, failover và restart không làm expiry sai.
- Không có đường ghi bypass condition.

Nếu lease state ở etcd còn payload ở MongoDB, việc sink đọc etcd rồi update MongoDB có cửa sổ race. Muốn cam kết thu hồi tức thời, cần protocol hoặc ranh giới transaction có thể thực thi đồng thời điều kiện quyền và effect.

Không được suy rằng thêm trường **expiresAt** ở mọi record tự xóa mọi vấn đề phân tán.

## 40. Thứ tự token và nhiều lần ghi cùng owner

Ví dụ worker B token 42 cần:

~~~text
write chunk 1
write chunk 2
write chunk 3
publish complete
~~~

Nếu sink chỉ cho phép token **lớn hơn highestFence**, chunk 2 của chính B bị từ chối sau chunk 1 vì token 42 không lớn hơn 42.

Có hai cách:

**Cách A — Token là generation, operation ID riêng**

~~~text
generation 42
  chunk 1 operationId=op-1
  chunk 2 operationId=op-2
  chunk 3 operationId=op-3
~~~

Sink cho phép **token bằng active/highest generation** theo contract, nhưng mỗi op được dedup và kiểm state/version.

**Cách B — Mỗi commit có sequence riêng**

~~~text
token=(generation=42, sequence=1)
token=(generation=42, sequence=2)
token=(generation=42, sequence=3)
~~~

Sink so thứ tự cặp giá trị và xử lý out-of-order. Sequence nội bộ phải được bảo vệ; không để hai threads cùng claim một sequence nhưng ghi hiệu ứng khác nhau.

**Đừng để “token tăng” ngầm nghĩa mỗi lệnh của cùng owner đều cần xin lock mới**, trừ khi bài toán thật sự muốn thế.

## 41. Khi hai request cùng token đến sai thứ tự

Worker B token 42:

~~~text
Request 1: set state=PROCESSING
Request 2: set state=COMPLETED
~~~

Do network:

~~~text
Request 2 tới trước -> COMPLETED
Request 1 tới sau -> PROCESSING
~~~

Nếu sink chỉ so **token >= highestFence**, cả hai dùng token 42 và đều có thể được chấp nhận: state bị lùi.

Do đó trong cùng generation cần thêm:

- **Record version/sequence number**.
- **State machine transition predicates**.
- **Operation ID và causal order**.
- Hoặc một transaction/queue thứ tự phù hợp.

**Fencing phân biệt owner generations; nó không tự xếp thứ tự mọi operation bên trong một generation.**

## 42. Có cần token toàn cục hay token theo resource?

Một global allocator:

~~~text
fence:global -> 1000001, 1000002, ...
~~~

đơn giản về so sánh, nhưng có thể trở thành **hot key/coordination bottleneck** và cấp thứ tự mạnh hơn nhu cầu.

Một per-resource allocator:

~~~text
fence:report-77 -> 41,42,...
fence:report-78 -> 8,9,...
~~~

giảm contention nếu resources độc lập.

Tuy nhiên:

- Nếu một worker cần quyền trên **nhiều resources**, mỗi resource có thể có generation khác nhau.
- Một task xuyên nhiều resources cần transaction/coordination riêng để giữ invariant.
- Resource IDs phải được chuẩn hóa và không mơ hồ theo tenant.
- Nếu chuyển resource sang namespace khác, phải có kế hoạch giữ high-watermark.

**Chỉ cấp thứ tự mạnh trong phạm vi thật sự cần bảo vệ** giúp giảm chi phí.

## 43. Dùng term + sequence làm token có thứ tự

Trong một số hệ có leader và log, một generation có thể được biểu diễn:

~~~text
token = (term, sequence)
~~~

So sánh từ điển:

~~~text
(term=8, seq=100) < (term=9, seq=1)
~~~

vì term 9 mới hơn term 8 theo protocol.

Nhưng phải có những điều kiện:

- **Term tăng đơn điệu và không reset** sau failover/restore trong phạm vi được bảo vệ.
- Sequence có ý nghĩa theo term và không bị cấp trùng cho các thao tác mâu thuẫn.
- Các cặp token được phát bởi authority, không do client tự dựng.
- Sink lưu/so cả term và sequence, không bỏ term.
- Không trộn với term/index từ những clusters độc lập không có quan hệ thứ tự chung.

Nếu chỉ chọn **sequence tăng cục bộ trong từng leader** rồi bỏ term, một leader mới bắt đầu lại từ 1 có thể bị sink xem là cũ.

## 44. Từ chối stale write khác với kiểm soát data race

Xét các lỗi:

| Lỗi | Fencing có đủ không? | Cơ chế cần kết hợp |
|---|---|---|
| A token 41 ghi sau khi sink thấy B token 42 | **Có**, nếu guard atomic và không bypass | HighestFence compare |
| A token 41 ghi khi B đã được cấp 42 nhưng sink chưa biết | **Không chắc** với highestSeen đơn thuần | Active owner/epoch validation hoặc protocol |
| B token 42 retry INCR cùng operation | **Không** | Idempotency/event marker |
| B token 42 gửi COMPLETE rồi PROCESSING sai thứ tự | **Không** | Version/state transition |
| Hai keys cần giữ invariant xuyên key | **Không** | Transaction/coordination |
| Token 999 giả được gửi bởi attacker | **Không** | Authentication/authorization |
| Sink khôi phục high-watermark từ backup cũ | **Không** nếu fence lùi | Restore/epoch protocol |
| Old worker ghi vào external API bỏ qua token | **Không** | Sink/gateway guard, idempotent workflow |
| Sink chấp nhận token mới nhưng effect chưa bền | Tùy durability | Replication/commit/restore guarantee |

Một thiết kế đúng thường cần **fencing + conditional mutation + idempotency + durability**, tùy business invariant.

## 45. Diễn giải lỗi STALE_FENCE ở tầng API

Một API có thể phân biệt:

~~~text
SUCCESS
STALE_FENCE
NOT_OWNER
LEASE_EXPIRED
CONDITION_FAILED
DUPLICATE_OPERATION
UNKNOWN_TIMEOUT
RESOURCE_UNAVAILABLE
~~~

Các mã này không nhất thiết có sẵn trong driver; ứng dụng có thể ánh xạ từ lỗi engine phù hợp.

**STALE_FENCE** nghĩa là thế hệ đến thấp hơn thế hệ được tài nguyên công nhận; worker nên:

1. Dừng mọi kế hoạch publish tiếp bằng token cũ.
2. Không tự nâng token lên số cao hơn.
3. Không retry vô hạn cùng token.
4. Đưa trạng thái job vào **SUPERSEDED** hoặc tương đương.
5. Giữ audit log để điều tra nếu cần.

**UNKNOWN_TIMEOUT** khác: effect có thể đã commit, nên cần verify bằng operationId/result pointer trước khi thử lại.

## 46. Không release lock mới khi cleanup lock cũ

Worker A token 41 đã mất quyền, nhưng finally block vẫn chạy:

~~~text
finally:
    release("report:daily")
~~~

Nếu release chỉ xóa key theo tên, A có thể xóa lock của B. Một release an toàn cần:

~~~text
release iff:
  storedOwner == workerA
  AND storedLeaseId == lease41
  AND storedGeneration == 41
~~~

và thực hiện nguyên tử theo cơ chế lock store.

Cleanup artifact:

~~~text
A được phép xóa "run-41.json" do A sở hữu nếu không được publish.
A không được xóa "currentObject" hoặc "run-42.json" của B.
~~~

**Sở hữu dữ liệu tạm riêng** giúp cleanup an toàn; không dùng token cũ để dọn tài nguyên chung của thế hệ mới.

## 47. Kiểm thử bằng lịch sử thao tác

Một bài kiểm thử fencing phải tạo **stale owner thật sự**, không chỉ gọi hai acquire tuần tự:

~~~text
1. A acquire -> token 41.
2. A chuẩn bị payload nhưng bị chặn trước write.
3. Đợi lease A hết hạn theo test harness.
4. B acquire -> token 42.
5. B write vào sink -> SUCCESS.
6. Giải phóng A; A write token 41.
7. Kỳ vọng: A bị từ chối; sink vẫn giữ result B.
~~~

Nên ghi log:

~~~json
{
  "resourceId": "daily:2026-11-14",
  "operationId": "op-A-41",
  "workerId": "worker-A",
  "leaseId": "lease-41",
  "fencingToken": 41,
  "sinkHighestBefore": 42,
  "outcome": "STALE_FENCE",
  "sinkHighestAfter": 42
}
~~~

Đây là một test minh họa; trong test thực cần xác định invocation/response, thời điểm acquire/commit và loại lỗi.

## 48. Test quan trọng: A ghi trước khi B đăng ký thế hệ ở sink

Đừng chỉ thử tình huống dễ:

~~~text
B token 42 write thành công.
A token 41 write sau -> reject.
~~~

Cần thử thêm:

~~~text
A lease 41 expired.
B acquire 42 tại lock authority.
B chưa gửi write.
A gửi write với 41.
~~~

Nếu sink chỉ có **highestSeen=40**, A có thể được chấp nhận. Đây không nhất thiết là bug trong policy “chặn thế hệ thấp hơn đã seen”, nhưng có thể là **vi phạm yêu cầu mạnh hơn** “mọi thao tác từ owner hết lease phải bị từ chối ngay”.

Đội phải quyết định:

- Yêu cầu thật sự là **không ghi đè kết quả owner mới**?
- Hay cần **không chấp nhận bất kỳ thao tác nào sau expiry**?
- Active epoch được sink biết qua cách nào?
- Việc đăng ký thế hệ mới và effect được nguyên tử hóa tới đâu?

Viết câu trả lời vào API contract trước khi gắn nhãn giải pháp “fencing-safe”.

## 49. Fault injection với GC pause và network partition

Các lịch lỗi cần thử:

| Kịch bản | Nguy cơ | Bằng chứng cần xác minh |
|---|---|---|
| A pause vượt TTL, B publish | A ghi đè B | A token cũ bị sink reject |
| A request đến trễ qua mạng | Effect xảy ra sau quyền mới | Guard kiểm tại commit |
| A renew timeout | A tưởng vẫn còn lease | Worker dừng publish/verify |
| B acquire timeout sau commit | B acquire lại, có nhiều token | Authority biết owner/token thực |
| Sink crash rồi recover | HighestFence reset | Metadata fence không lùi |
| Allocator failover | Token bị cấp lặp | Monotonic/durable generation |
| A release sau khi B acquire | A xóa lock B | Owner+lease compare |
| Retry cùng token | Double increment/payment | Operation dedup |
| Hai writes cùng token đảo thứ tự | State rollback | Sequence/version/state machine |
| Token giả số rất lớn | Fence poisoning | Authz và token validation |
| External sink bỏ qua token | Old worker vẫn có effect | Guard tại sink/gateway |
| Multi-region replication lag | Region cũ ACK stale owner | Consistency/epoch theo region |

Fault injection cần được thực hiện trong môi trường được phép, không tùy ý gây partition hoặc kill node production.

## 50. Observability cho fencing

Theo dõi:

| Metric/log | Mục đích |
|---|---|
| Current owner/generation per resource | Biết thế hệ có thẩm quyền |
| Lease renewal failures | Phát hiện worker đang mất quyền |
| Acquire contention/timeouts | Thấy lock nóng hoặc authority lỗi |
| Stale fence rejection count | Đếm thao tác đến từ owner cũ |
| Highest fence update latency | Xem đăng ký thế hệ tại sink chậm |
| Unknown outcome count | Theo dõi commit nhưng mất response |
| Duplicate operation suppressed | Phân biệt dedup với fencing |
| Owner transitions/term changes | Truy vết failover |
| Fence rollback alarms | Phát hiện restore token thấp |
| Protected write p95/p99 | Đo chi phí guard/CAS/quorum |
| Invariant violations | Theo dõi kết quả nghiệp vụ cuối |

Không đưa resourceId hoặc tenantId có cardinality cực lớn vào mọi metric label. Trace/audit có thể giữ IDs với quyền truy cập và retention phù hợp.

Một log nên chứa:

~~~text
resourceId, tenantScope, operationId,
workerId, leaseId, fencingToken,
storedFenceBefore, storedFenceAfter,
predicateResult, commitResult, traceId
~~~

Khi sự cố xảy ra, những trường này giúp trả lời **request của worker cũ đã bị chặn ở đâu**, thay vì chỉ nhìn “lock expired”.

## 51. Quy trình chọn giải pháp theo loại tài nguyên

~~~mermaid
flowchart TD
    A["Có nhiều worker tranh quyền cùng resource?"] --> B{"Effect nằm ở đâu?"}
    B -->|"Một record/transaction hỗ trợ CAS"| C["Conditional write và generation guard cùng effect"]
    B -->|"External sink có conditional write"| D["Dùng native compare/version và scope token"]
    B -->|"External sink không có fencing"| E["Immutable outputs + fenced pointer / gateway + reconciliation"]
    C --> F["Xác định authority cấp token"]
    D --> F
    E --> F
    F --> G["Xác định lease semantics, monotonicity và durability"]
    G --> H["Định nghĩa equal-token, operationId, business state"]
    H --> I["Thiết kế retry UNKNOWN / release / cleanup"]
    I --> J["Test pause, failover, restore, late request, forged token"]
    J --> K["Metrics và runbook"]
~~~

Các bước áp dụng:

1. **Xác định tài nguyên cần bảo vệ**: key, report pointer, stock reservation, invoice, upload, leader job.
2. **Viết invariant**: output từ owner cũ không được ghi đè sau owner mới; hoặc yêu cầu mạnh hơn là không ghi sau lease expiry.
3. **Chọn authority** cấp quyền và generation theo cùng resource scope.
4. **Chứng minh token không lùi** qua các lần acquire/failover/restore.
5. **Định nghĩa guard tại sink**: highestSeen, activeEpoch, CAS, version và business predicates.
6. **Đảm bảo guard + effect nguyên tử** hoặc có protocol an toàn tương đương.
7. **Phân biệt retry cùng operation** bằng stable operation ID.
8. **Quy định behavior khi lease renew/acquire/write UNKNOWN**.
9. **Chặn release/cleanup cũ** can thiệp tài nguyên owner mới.
10. **Kiểm thử lịch lỗi**, đặc biệt GC pause và write in-flight.
11. **Giám sát và đối soát** resource generations, stale rejects, business invariants.
12. **Lập kế hoạch recovery** nếu coordinator/sink bị restore từ trạng thái cũ.

## 52. Những nhầm lẫn phổ biến

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| “Lock TTL hết hạn thì A không thể chạy nữa” | Process có thể pause rồi resume | Sink phải tự bảo vệ |
| “Kiểm lease trước write là đủ” | TOCTOU giữa check và effect | Atomic guard tại sink |
| “UUID lock là fencing token” | UUID không có thứ tự generation | Cần token so sánh được |
| “Timestamp client là token tăng” | Clock skew và rollback | Authority cấp thứ tự |
| “Chỉ cần token lớn hơn là được quyền” | Token có thể bị giả | Authz và proof of issuance |
| “Đã có highestSeen thì biết tức thời lease mới” | Sink chỉ biết thế hệ đã quan sát | Active epoch/protocol nếu cần |
| “INCR Redis luôn bền qua mọi failover” | Replication/persistence khác consensus | Xác minh guarantee thực |
| “SET NX PX tự fencing” | TTL lock không kiểm protected sink | Guard tại sink |
| “Redlock random value là token đơn điệu” | Giá trị nhận diện owner không có thứ tự | Thiết kế riêng generation |
| “etcd revision nào cũng là quyền lock” | Có thể là revision không liên quan | Dùng revision đúng protocol |
| “ZooKeeper sequence được cấp là đã sở hữu lock” | Contender còn phải chờ lượt | Chỉ cấp quyền khi acquire |
| “ResourceVersion Kubernetes là fence numeric toàn cục” | Opaque concurrency token theo API | Đúng scope và guarantee |
| “Fencing thay idempotency” | Cùng owner có thể retry double effect | Operation ID/dedup |
| “Token bằng nhau thì mọi write an toàn” | Cùng generation có thể out-of-order | State/version/sequence |
| “Một fenced DB update chặn mọi external side effects” | Hệ ngoài không tự kiểm token | Guard từng sink hoặc workflow |
| “Để token trong object metadata là đủ” | Storage có thể không so token | Native precondition/fenced pointer |
| “Restore counter về 0 chỉ ảnh hưởng hiệu năng” | Token mới thấp hơn old high-watermark | Restore/epoch protocol |
| “Một global counter luôn tốt hơn” | Hot allocator và cross-scope contention | Per-resource nếu phù hợp |
| “Failover đã xong thì không còn request cũ” | Request có thể in-flight | Sink reject stale generations |
| “Contention giải quyết bằng tăng lease TTL thật dài” | Stale owner vẫn có thể xảy ra | TTL tuning + fencing |
| “STALE_FENCE nên retry với token cộng một” | Client không có quyền tự cấp token | Acquire lại qua authority |
| “Một lần test pass chứng minh mọi lỗi an toàn” | Lịch lỗi khác có thể xảy ra | Fault histories và đặc tả |

## 53. Bài tập thực hành

### Bài tập 1 — Lịch sử GC pause

A acquire lock ở t=0, TTL 30 giây. A bị pause từ t=5 tới t=45. B acquire ở t=31 và ghi tại t=35. Hãy mô tả cách A có thể ghi đè B nếu không có fencing, dù hai lần acquire đều theo quy tắc TTL.

### Bài tập 2 — Fencing theo highestSeen

Sink highestFence=41. B ghi token 42, sau đó A gửi token 41. Viết predicate chặn A và giải thích vì sao thao tác kiểm token phải atomic với mutation.

### Bài tập 3 — Giới hạn khi sink chưa thấy token mới

Sink highestFence=40. A đã hết lease 41, B được cấp 42 nhưng chưa gửi gì tới sink. A gửi token 41. Nếu sink chỉ kiểm token >= highestFence, kết quả là gì? Đề xuất giao thức mạnh hơn nếu bắt buộc từ chối mọi tác nhân hết hạn.

### Bài tập 4 — TOCTOU

Worker A gọi checkLease() trả valid, rồi bị dừng 40 giây trước khi PUT object. B đã acquire và ghi. Hãy chứng minh lệnh checkLease không đủ và đề xuất nơi thực thi guard.

### Bài tập 5 — UUID vs token tăng

Hai lần acquire trả lease IDs UUID khác nhau. Vì sao sink không thể so UUID để biết generation mới? Hãy thiết kế ownerId, leaseId và fencingToken như ba trường riêng.

### Bài tập 6 — Đồng hồ lệch

Worker A được cấp quyền trước nhưng đồng hồ nhanh 500 ms; B được cấp quyền sau nhưng đồng hồ chậm 300 ms. Hãy tạo lịch sử cho thấy currentTimeMillis không phải fencing allocator đúng.

### Bài tập 7 — Token theo resource

Report A có generation 42; report B có generation 9. Vì sao không nên so 42 với 9 khi chúng thuộc hai namespace? Thiết kế key dùng tenantId và resourceId.

### Bài tập 8 — MongoDB

Tạo document report pointer có highestFence=42. Viết updateOne mang token 41 và filter từ chối thao tác cũ. Nêu những điều phải kiểm tra về atomicity, missing field, matchedCount và majority write concern.

### Bài tập 9 — MongoDB cấp token

Thiết kế resourceLeases record chứa generation, owner, leaseId, expiresAt. Mô tả conditional acquisition nguyên tử và cách xử lý hai worker acquire đồng thời. Giải thích giới hạn của expiresAt từ đồng hồ client.

### Bài tập 10 — DynamoDB UpdateItem

Viết ConditionExpression dựa trên highestFence và UpdateExpression lưu object pointer mới. Vì sao phải bảo vệ trường hợp item bị Delete/recreate và không cho client bất kỳ tự gửi token lớn?

### Bài tập 11 — DynamoDB và hai items

Lease item nằm ở PK=LEASE#R, protected state ở PK=RESOURCE#R. Worker đọc lease rồi ghi resource. Hãy chỉ ra TOCTOU và đề xuất TransactWriteItems/đổi data model hoặc protocol khác.

### Bài tập 12 — Cassandra LWT

Viết UPDATE ... IF highest_fence=42 cho một row và tăng thành 43. Giải thích vì sao ordinary UPDATE không điều kiện có thể làm hỏng fence khi writer cũ gửi timestamp mâu thuẫn.

### Bài tập 13 — Redis SET NX PX

A có lock lease-A, hết TTL; B có lease-B. A gọi DEL theo tên key. Hãy mô tả lỗi và viết Lua compare-owner-before-delete. Vì sao script release đúng vẫn không fencing được external resource?

### Bài tập 14 — Redis INCR và failover

Giả sử allocator Redis cấp 42 nhưng primary chết trước khi replica lưu đầy đủ thay đổi. Sau failover generation có thể thấp hơn. Hãy chỉ ra tác động và yêu cầu gì với allocator nếu muốn monotonic bền vững.

### Bài tập 15 — etcd

Thiết kế lock candidate dưới lease trong etcd và dùng creation revision/generation phù hợp làm fencing token. Trình bày vì sao phải phân biệt revision được cấp với việc contender đã thực sự giành quyền.

### Bài tập 16 — ZooKeeper

Hai ephemeral sequential nodes lần lượt có sequence 41 và 42. A giữ lock với 41, mất session; B được quyền 42. Sink cần lưu gì để chặn A sau B? Điều gì xảy ra nếu parent znode bị xóa rồi tạo lại?

### Bài tập 17 — Kafka worker

A đã nhận partition rồi bị pause, rebalance cho B. Hãy phân biệt broker consumer generation, message offset và external DB fence; viết một contract chống stale writes và duplicate events.

### Bài tập 18 — Kubernetes Lease

Hai controllers dùng Lease object để chọn leader. Vì sao không nên parse resourceVersion thành số fencing tổng quát? Đề xuất conditional update ở DB được bảo vệ.

### Bài tập 19 — Object storage

Worker A/B tạo báo cáo từ cùng source. Thiết kế **immutable artifacts + current pointer** được fenced CAS, cùng cleanup orphan artifacts an toàn.

### Bài tập 20 — Payment provider không hiểu token

Một payment API chỉ có capture(paymentIntentId). Trình bày vì sao việc có token 42 ở etcd không tự chặn A token 41 gọi provider. Đề xuất idempotency, authoritative state machine, outbox và đối soát UNKNOWN.

### Bài tập 21 — Nhiều writes cùng generation

B token 42 gửi PROCESSING và COMPLETED, nhưng COMPLETED đến trước PROCESSING. Tại sao predicate token >= highestFence không chặn state regression? Thiết kế version/state transition.

### Bài tập 22 — Retry cùng token

B token 42 gửi INCR +1, server commit nhưng response timeout. B retry cùng token. Fencing có chặn double increment không? Viết phương án operationId/marker có atomic effect.

### Bài tập 23 — Security

Một request lạ gửi token 999999 vào sink đang highestFence 42. Thiết kế authentication, resource scope, proof of grant và cách chống fence poisoning.

### Bài tập 24 — Restore

Allocator được restore về generation 900, trong khi sink highestFence=1000. Hãy giải thích vì sao không được hạ sink về 900, và đề xuất recovery với allocator epoch mới có thẩm quyền.

### Bài tập 25 — Multi-resource workflow

Một worker với token 42 phải cập nhật object storage, MongoDB và publish event. Hãy đánh dấu **điểm commit**, nơi cần guard, nơi cần idempotency và những hiệu ứng có thể phải reconcile.

### Bài tập 26 — Metrics và fault injection

Thiết kế test suite tiêm GC pause, network delay, owner change, failover và sink restore. Định nghĩa expected behavior đối với stale token, unknown outcome, retry, release và hệ thống giám sát cần quan sát.

### Bài tập 27 — Thiết kế hợp đồng API

Viết hợp đồng cho:

~~~text
POST /reports/{date}/publish
~~~

Bao gồm resource scope, authority cấp fencing token, lease semantics, điều kiện từ chối token cũ, rule token bằng nhau, operation ID, atomicity guard+effect, durability, behavior khi sink chưa thấy token mới, timeout/retry, authentication, recovery và observability.

### Bài tập 28 — Chứng minh giới hạn của giải pháp

Một đội tuyên bố: “Vì mọi request gửi kèm token, không worker nào đã hết lease có thể ghi vào bất cứ lúc nào.” Hãy dựng lịch sử phản ví dụ **B đã acquire token mới nhưng sink chưa biết**, rồi sửa phát biểu guarantee cho chính xác hoặc đề xuất protocol để đạt yêu cầu mạnh hơn.

---

**Kết luận:** Fencing token giải quyết lỗ hổng quan trọng của distributed lock: **tác nhân đã mất quyền vẫn có thể tiếp tục chạy và gửi thao tác**. Một authority đáng tin phải cấp **thế hệ quyền tăng đơn điệu**, còn tài nguyên đích phải **kiểm và cập nhật fence nguyên tử cùng hiệu ứng** để từ chối các thế hệ đã cũ. Không được nhầm **lease ID với token có thứ tự**, **token với idempotency**, hay **một lần kiểm lease ở client với guard tại sink**. Đặc biệt, policy chỉ so **highestSeen** bảo vệ chống ghi lùi **sau khi sink đã công nhận thế hệ mới**; muốn từ chối ngay mọi thao tác khi lease hết hạn cần thêm cơ chế đồng bộ/active-owner validation có ranh giới atomicity phù hợp. Với NoSQL, MongoDB conditional update, DynamoDB ConditionExpression, Cassandra LWT và các dịch vụ coordination như etcd/ZooKeeper có thể là thành phần của thiết kế; Redis TTL đơn thuần, token ngẫu nhiên và external API không kiểm token **không tự cung cấp fencing**. Hệ thống an toàn cần ghép **quyền ghi, CAS/state transition, idempotency, durability và reconciliation** theo đúng phạm vi tài nguyên, rồi thử nghiệm thực tế bằng GC pause, failover và request đến muộn.
