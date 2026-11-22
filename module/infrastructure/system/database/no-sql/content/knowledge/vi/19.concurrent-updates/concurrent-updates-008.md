# Khóa bi quan hoặc cơ chế tương đương theo từng hệ

## 1. Bài toán cập nhật đồng thời và câu hỏi “ai được ghi trước?”

Trong ứng dụng NoSQL, nhiều tiến trình có thể đọc và ghi cùng một đối tượng:

- Hai khách cùng đặt chiếc vé cuối cùng.
- Hai worker cùng lấy một công việc khỏi hàng chờ.
- Người dùng và tác vụ nền cùng sửa trạng thái đơn hàng.
- Một job đồng bộ chạy đồng thời trên hai máy sau khi hệ thống tự động mở rộng.
- Hai node cùng cố cập nhật cấu hình quan trọng.
- Một quy trình thanh toán kéo dài qua nhiều bước và không được thực hiện hai lần.

Nếu mỗi tiến trình tự đọc trạng thái, kiểm tra điều kiện rồi ghi, hai tiến trình có thể đều nhìn thấy cùng trạng thái cũ và ra quyết định mâu thuẫn.

Ví dụ một job:

~~~text
jobId=J100
status=READY

Worker A                           Worker B
--------                           --------
Đọc status=READY
                                   Đọc status=READY
Bắt đầu xử lý
                                   Bắt đầu xử lý
Gửi thông báo
                                   Gửi thông báo
Đánh dấu DONE
                                   Đánh dấu DONE
~~~

Database cuối cùng chỉ có `status=DONE`, nhưng người dùng nhận **hai thông báo**.

Một hướng giải quyết là **khóa bi quan (pessimistic locking)**: khi một tiến trình chuẩn bị thao tác trên tài nguyên, nó giữ quyền truy cập độc quyền hoặc chia sẻ theo một giao thức nhất định; tiến trình khác phải đợi hoặc bị từ chối trước khi thực hiện thao tác xung đột.

Nhưng NoSQL không đồng nhất:

- Một số sản phẩm có cơ chế khóa document trực tiếp.
- Một số có khóa do transaction engine quản lý mà ứng dụng không thao tác rõ như SQL `SELECT ... FOR UPDATE`.
- Một số chủ yếu cung cấp **conditional write, CAS hoặc optimistic concurrency control (OCC)**.
- Nhiều hệ ứng dụng xây **distributed lease** trên item/key và kiểm tra phiên bản hoặc fencing token.
- Một số workload phù hợp hơn với **single-writer queue**, không cần khóa dài hạn.

Mục tiêu bài này là nhận biết **khóa nào thật sự tồn tại, nó bảo vệ phạm vi nào, điều gì xảy ra khi tiến trình chết và khi nào cần chọn cơ chế tương đương thay vì cố mô phỏng SQL row lock**.

## 2. Khóa bi quan là gì?

**Pessimistic concurrency control** giả định xung đột đủ quan trọng hoặc đủ thường xuyên để ngăn thao tác cạnh tranh từ trước. Một tiến trình phải nắm quyền trên tài nguyên trước khi sửa, hoặc transaction engine tự giữ khóa tương ứng.

Sơ đồ:

~~~text
                 Resource R
                     |
            +--------+--------+
            |                 |
            v                 v
        Worker A          Worker B
        acquire(R)        acquire(R)
            |                 |
            v                 v
        GRANTED            WAIT / FAIL
            |
        read-modify-write
            |
        release(R)
                              |
                              v
                           GRANTED
                              |
                          update(R)
~~~

Với khóa độc quyền đúng nghĩa, hai tác vụ không cùng giữ quyền sửa cùng một tài nguyên tại một thời điểm logic theo cơ chế được hệ cung cấp.

### 2.1. Từ “bi quan” không có nghĩa hiệu năng kém

Nó mô tả cách xử lý xung đột:

- **Bi quan:** chặn/đợi hoặc từ chối thao tác xung đột trước khi cho nó tiến vào phần được bảo vệ.
- **Lạc quan:** cho các tiến trình chuẩn bị song song rồi kiểm tra phiên bản/điều kiện tại lúc commit; nếu xung đột, một bên thất bại và có thể retry.

Khóa bi quan có thể rất hiệu quả khi giao dịch ngắn, xung đột cao và hệ hỗ trợ khóa phù hợp. Ngược lại, một lock giữ lâu trong mạng phân tán có thể gây tắc nghẽn, deadlock hoặc rủi ro stale owner.

### 2.2. Shared lock và exclusive lock

Trong hệ có khóa đọc/ghi:

| Loại | Mục đích | Có thể cùng tồn tại? |
|---|---|---|
| Shared/read lock | Cho phép nhiều tác vụ đọc nhưng bảo vệ khỏi thay đổi xung đột theo semantics hệ | Nhiều shared lock thường có thể cùng giữ |
| Exclusive/write lock | Chỉ một chủ thể được sửa tài nguyên trong phạm vi khóa | Thường không cùng tồn tại với lock xung đột |
| Intent locks | Báo ý định khóa cấp dưới trong hệ phân cấp | Phụ thuộc ma trận tương thích |
| Advisory lock | Ứng dụng tự tuân thủ giao thức khóa, không bắt buộc mọi thao tác DB đều bị chặn | Chỉ an toàn nếu mọi writer hợp tác |

Không phải database NoSQL nào cũng phơi bày đủ các loại trên. Đặc biệt, một **key Redis đặt bằng `SET NX`** không tự động làm một thao tác UPDATE trên MongoDB bị chặn. Đó là **khóa tư vấn ở tầng ứng dụng**, không phải một physical row lock được MongoDB cưỡng chế.

### 2.3. Khóa có phạm vi và thời gian sống

Một khóa có thể gắn với:

- Key;
- Document/item;
- Row;
- Partition;
- Collection/table;
- Transaction;
- Một tài nguyên ngoài DB: file, job, máy in, thiết bị, API bên thứ ba.

Thời gian sống có thể là:

- Đến khi transaction commit/rollback;
- Đến khi caller gọi unlock;
- Đến khi session/connection chết;
- Đến khi **lease hết hạn**;
- Đến khi một coordinator thu hồi quyền.

Một lock chỉ đáng tin cậy khi biết **chủ sở hữu, đối tượng được bảo vệ, điều kiện hết hiệu lực và hành vi khi hệ thống lỗi**.

## 3. So sánh khóa bi quan, OCC và điều phối một writer

| Tiêu chí | Pessimistic lock | Optimistic CAS/OCC | Single-writer queue |
|---|---|---|---|
| Cách hoạt động | Giữ quyền trước khi sửa | So điều kiện/version tại ghi | Chuyển yêu cầu cùng key tới một luồng thực thi |
| Khi có xung đột | Đợi/từ chối khóa | Một request conflict/retry | Xếp hàng |
| Phù hợp | Critical section ngắn, rủi ro race cao | Xung đột thấp/trung bình, update ngắn | Hot key, xử lý theo thứ tự |
| Chi phí chính | Chờ, giữ lock, deadlock/lease | Retry, đọc lại, CAS contention | Độ trễ hàng đợi, vận hành coordinator |
| Nếu worker chết | DB/session/lease phải giải phóng | Mutation chưa commit hoặc commit theo API | Broker/consumer cần retry và ownership |
| Phạm vi bảo vệ | Theo phạm vi engine hoặc giao thức lock | Theo phạm vi conditional mutation | Chỉ khi routing và failover giữ một owner đúng |
| Đường sang hệ khác | Cần lock thực thi/fencing ở đích | Cần transaction/workflow khác | Cần idempotency/fencing |
| Có tự tạo exactly-once? | Không | Không | Không |

**Quy tắc:** nếu invariant đã nằm trọn trong một item/document và database hỗ trợ **atomic conditional update**, thường nên đánh giá nó **trước** khi tự tạo distributed lock. Giảm một tầng coordination có thể đơn giản hơn, nhanh hơn và ít tình huống lỗi hơn.

## 4. Điều gì cần bảo vệ: thao tác, bất biến hay side effect?

Xem ba bài toán:

### 4.1. Chỉ trừ tồn kho nếu còn đủ

~~~text
Inventory(P100) = {available: 1}
~~~

Nếu chỉ cần đảm bảo `available >= 0`, có thể dùng:

~~~text
ATOMIC:
  IF available >= 1:
    available := available - 1
~~~

Một **conditional update một item** thường đủ; không nhất thiết tạo lock rồi đọc rồi trừ.

### 4.2. Chỉ một worker xử lý job

~~~text
Job(J100) = {state: READY}
~~~

Nếu worker chỉ cần claim job rồi xử lý bên ngoài database, một cập nhật:

~~~text
IF state = READY:
  state := PROCESSING
  owner := workerA
~~~

có thể ngăn hai worker cùng claim **ở thời điểm đó**. Nhưng nếu worker A chết, job phải được giao lại: cần lease/deadline, retry và idempotency.

### 4.3. Chỉ một lần gọi API thanh toán

Dù chỉ một worker nắm lock J100, việc gọi API thanh toán có thể:

1. Thành công ở cổng thanh toán;
2. Worker timeout trước khi ghi kết quả;
3. Lease hết hạn;
4. Worker khác xử lý lại.

Một lock **không thể tự cam kết** rằng hai hệ độc lập đã thực hiện giao dịch một lần duy nhất. Cần idempotency key tại payment provider, log trạng thái bền vững, đối soát và quy trình recover.

**Đừng chọn khóa trước khi viết rõ invariant cần bảo vệ và các hệ chịu tác động.**

## 5. Atomicity và isolation không phải lúc nào cũng là “có khóa”

Một thao tác database có thể nguyên tử mà không cung cấp API lock dài hạn cho ứng dụng.

### 5.1. Atomic conditional update

Một mutation có điều kiện được engine xét và ghi như một đơn vị:

~~~text
UPDATE product
IF available >= quantity
SET available = available - quantity
~~~

Nếu engine cam kết atomicity trong phạm vi item, hai lệnh cạnh tranh không cùng dựa vào trạng thái chưa cập nhật để được áp dụng.

Đây là **hiệu quả tương đương việc tuần tự hóa một bước check-and-write**, nhưng không có nghĩa caller đang giữ lock để làm thêm ba round-trip khác.

### 5.2. Transaction-managed locking

Một transaction có thể đọc, ghi và giữ các khóa nội bộ cho đến commit/rollback. Cách engine triển khai (pessimistic, optimistic, MVCC, conflict detection) tùy sản phẩm, SDK, isolation level và mode.

Người dùng không nên suy rằng cứ có giao dịch là tương đương SQL `SELECT FOR UPDATE` hoặc rằng mọi bản đọc bị khóa.

### 5.3. Linearizability, serializability và durability

- **Atomicity:** mutation trong phạm vi cam kết không thực hiện nửa vời.
- **Isolation:** giao dịch đồng thời thấy/tranh chấp trạng thái theo quy tắc nào.
- **Linearizability:** có thể coi mỗi operation xảy ra tại một điểm, tôn trọng thứ tự thời gian thực của operation hoàn tất.
- **Serializability:** kết quả nhiều transaction tương đương một thứ tự tuần tự hợp lệ.
- **Durability:** sau commit, dữ liệu được giữ ra sao khi xảy ra lỗi.

Có **CAS** không tự nghĩa mọi thao tác trên toàn cluster có serializable isolation. Có **lock** không tự nghĩa đã có durability qua failover. Có **strong read** không tự nghĩa hai ghi độc lập là một transaction.

## 6. Khóa ứng dụng khác khóa do storage engine quản lý

### 6.1. Khóa engine cưỡng chế

Ví dụ một database có API `getAndLock` document: khi một client nắm lock theo hợp đồng sản phẩm, những thao tác cập nhật cạnh tranh vào document bị engine kiểm soát.

Ưu điểm: mọi client đi qua engine chịu cơ chế đó, không chỉ những client “tự giác đọc lock key”.

Giới hạn: lock duration/size/transaction semantics, chi phí và ràng buộc phiên bản cụ thể.

### 6.2. Khóa tư vấn do ứng dụng tạo

Ví dụ:

~~~text
redis key "lock:report:2026-11-14" = "worker-A"
~~~

Ứng dụng quy ước:

> Chỉ writer nào giữ lock Redis mới được cập nhật report.

Nhưng nếu một tiến trình bỏ qua Redis và ghi thẳng report vào MongoDB, MongoDB sẽ không tự kiểm tra lock Redis. Muốn bảo vệ được tài nguyên đích, tất cả writer phải tuân thủ giao thức hoặc **tài nguyên đích phải cưỡng chế phiên bản/fencing token**.

### 6.3. Khi nào phải nghi ngờ cơ chế khóa?

Hãy hỏi:

1. Chủ thể nào cấp lock?
2. Hai client tại hai region có thể cùng được cấp không?
3. Lock có bị mất khi failover không?
4. Mọi write vào tài nguyên có bắt buộc kiểm tra lock không?
5. Nếu chủ sở hữu bị pause rồi thức dậy sau khi mất lock, điều gì chặn nó?
6. Ghi vào database khác có bị bảo vệ không?
7. Timeout có nghĩa lock chưa được cấp hay chưa chắc?
8. Lock tồn tại lâu bao nhiêu và được gia hạn thế nào?

Nếu chưa trả lời, đừng gọi giải pháp đó là “độc quyền tuyệt đối”.

## 7. Lease: quyền sở hữu có thời hạn

Trong distributed systems, một **lease** thường thực tế hơn một lock giữ vô hạn.

Ví dụ record điều phối:

~~~json
{
  "jobId": "J100",
  "ownerId": "worker-A",
  "leaseUntil": "2026-11-14T08:05:00Z",
  "fencingToken": 41,
  "state": "PROCESSING"
}
~~~

Các trường có vai trò khác nhau:

- `ownerId`: ai đang giữ quyền.
- `leaseUntil`: mốc mà quyền hết hạn theo giao thức.
- `fencingToken`: số thế hệ tăng đơn điệu dùng để chặn chủ sở hữu cũ.
- `state`: trạng thái nghiệp vụ của job.

### 7.1. Vòng đời lease

~~~text
READY
  |
  | acquire thành công
  v
LEASED(owner=A, token=41, until=T1)
  |
  +---- heartbeat/renew ----> until=T2
  |
  +---- hoàn tất đúng owner ----> DONE
  |
  +---- lease hết hạn ---------> đủ điều kiện acquire bởi B
                                    |
                                    v
                          LEASED(owner=B, token=42)
~~~

**“Lease hết hạn” không đồng nghĩa worker A đã ngừng chạy.** Nó chỉ nghĩa A không còn quyền theo giao thức và tài nguyên phải từ chối hành động của A nếu hành động đó cần bảo vệ.

### 7.2. Bảo đảm safety và liveness

Một thiết kế cần cả hai:

- **Safety:** không có hai chủ sở hữu cùng được công nhận có quyền thao tác xung đột tại tài nguyên cần bảo vệ.
- **Liveness:** nếu một worker chết, công việc cuối cùng có thể được tiếp tục bởi worker khác.

Lock không bao giờ hết hạn có thể đảm bảo một phần safety khi hệ khỏe nhưng không có liveness nếu owner chết. Lease cải thiện liveness nhưng cần **fencing/owner verification** để tránh stale owner làm hỏng safety.

## 8. Redis: SET NX PX là distributed lease cơ bản

Redis được dùng nhiều làm cache, session và nơi điều phối lock ngắn hạn. Một mẫu phổ biến:

~~~redis
SET lock:job:J100 96d682ce-f01c-4810-8e26-uniqueowner NX PX 30000
~~~

Ý nghĩa:

- `NX`: chỉ đặt giá trị nếu key chưa tồn tại;
- `PX 30000`: expire key sau 30.000 ms;
- Giá trị là **owner token ngẫu nhiên đủ khó đoán**, duy nhất cho mỗi lần acquire.

Trên một Redis instance theo semantics của command, hai client đồng thời `SET NX` cùng key không cùng nhận thành công cho key đang tồn tại.

### 8.1. Vì sao không GET rồi SET?

Cách sai:

~~~text
A GET lock -> nil
B GET lock -> nil
A SET lock=A
B SET lock=B
~~~

Hai client đều nghĩ mình giữ lock. `SET ... NX` đưa phép kiểm tra tồn tại và ghi vào một command nguyên tử.

### 8.2. Vì sao phải có TTL?

Nếu owner crash mà lock không có TTL, key có thể tồn tại vô thời hạn và job không được xử lý lại. TTL giúp hệ có cơ hội tiến lên sau lỗi.

Nhưng TTL cũng mang rủi ro: worker đang xử lý lâu hơn lease mà không gia hạn có thể mất quyền giữa chừng.

### 8.3. Giải phóng lock phải kiểm tra owner

Cách sai:

~~~redis
DEL lock:job:J100
~~~

Giả sử:

~~~text
T0: A lấy lock 30 giây
T1: A pause 60 giây
T2: lock A hết hạn
T3: B lấy lock mới
T4: A chạy lại và DEL key -> xóa lock của B
~~~

Một script kiểm tra chủ sở hữu rồi xóa nguyên tử:

~~~lua
-- KEYS[1] = lock key
-- ARGV[1] = owner token của lần acquire này

if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
~~~

Script trên bảo vệ thao tác **release** trong Redis. Nó không bảo vệ những ghi vào database khác đã được worker A gửi khi lease hết hạn.

### 8.4. Gia hạn lease cũng phải kiểm tra owner

Một script:

~~~lua
-- KEYS[1] = lock key
-- ARGV[1] = owner token
-- ARGV[2] = TTL mới tính bằng mili giây

if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("PEXPIRE", KEYS[1], ARGV[2])
else
    return 0
end
~~~

Worker cần:

- Gia hạn **trước** deadline với biên an toàn;
- Theo dõi thời gian response và lỗi mạng;
- Ngừng/cancel công việc nếu mất quyền;
- Không tự diễn giải timeout là renew thành công;
- Tránh chạy critical section dài vượt quá thời gian lock.

### 8.5. Redis Cluster và multi-key Lua

Nếu một script động chạm nhiều key trong Redis Cluster, các key có thể phải thuộc cùng hash slot theo quy tắc của Redis. Không thể mặc định một Lua script sẽ điều phối nguyên tử tùy ý mọi key nằm trên nhiều shard.

Với khóa bảo vệ nhiều tài nguyên, cần thiết kế key scope, orchestration và atomicity cụ thể.

### 8.6. Redis lock không tự là giao dịch bền vững nhiều hệ

Redis có replication/failover với những bảo đảm riêng. Một lock vừa ghi vào primary nhưng chưa được replica thấy có thể gặp tình huống mất trạng thái khi failover, tùy triển khai.

Do đó, đừng dùng một `SET NX PX` đơn giản làm lời hứa **duy nhất toàn cụm qua mọi partition mạng và crash**, nhất là để bảo vệ tiền hoặc tài nguyên bên ngoài mà không có fencing/idempotency.

## 9. Redlock và giới hạn của giải pháp đa Redis node

Một số kiến trúc dùng **Redlock**, trong đó client thử acquire cùng lock trên nhiều Redis node độc lập và quyết định thành công theo ngưỡng và thời gian.

Điểm cần hiểu:

- Nó là **thuật toán lock/lease ứng dụng**, không phải row lock native của database nguồn.
- Các giả định về thời gian, độ trễ mạng, clock, crash/restart và tài nguyên ảnh hưởng bảo đảm.
- Một worker bị pause quá lease vẫn có thể gửi lệnh cũ đến hệ ngoài Redis.
- Có tranh luận và đánh giá kỹ thuật khác nhau về tính phù hợp của Redlock cho các yêu cầu safety mạnh.

Vì vậy, nếu bảo vệ tài nguyên không thể cho hai writer hành động, nên đánh giá **fencing token được tài nguyên đích kiểm tra**, và/hoặc dùng một coordination service có bảo đảm thích hợp. Không nên kết luận “nhiều Redis node nên lock chắc chắn an toàn tuyệt đối”.

Khi dữ liệu chỉ là cache có thể tạo lại, tính chất lock đơn giản có thể đủ. Khi dữ liệu có hậu quả không thể bù, phải chứng minh đầy đủ hơn.

## 10. Fencing token: cách chặn chủ sở hữu đã hết hạn

### 10.1. Tình huống stale worker

~~~text
T0: A nhận lease, token=41
T1: A bị dừng bởi GC/pause 60 giây
T2: Lease A hết hạn
T3: B nhận lease mới, token=42
T4: B ghi dữ liệu thành công
T5: A chạy tiếp và cũng ghi dữ liệu
~~~

Nếu tài nguyên đích chỉ tin rằng A từng sở hữu lock, nó có thể chấp nhận ghi cũ của A.

### 10.2. Fencing tại nơi thực sự ghi

Tài nguyên lưu `maxAcceptedToken`:

~~~text
WRITE(token=42, value="new")
    maxAcceptedToken = 42
    ACCEPT

WRITE(token=41, value="old")
    41 < 42
    REJECT
~~~

Điều kiện token phải được kiểm tra **nguyên tử cùng mutation trên tài nguyên đích**.

Ví dụ MongoDB ở sink:

~~~javascript
db.outputs.updateOne(
  {
    _id: "job:J100",
    lastFence: { $lt: 42 }
  },
  {
    $set: {
      result: "new-result",
      lastFence: 42
    }
  }
);
~~~

Ví dụ này chỉ minh họa đối tượng đã có `lastFence` và fence tăng. Khi tạo lần đầu hoặc khi dùng upsert cần thiết kế thêm condition/unique key để không tạo trùng.

### 10.3. Owner token khác fencing token

| Token | Vai trò | Yêu cầu |
|---|---|---|
| Owner token ngẫu nhiên | Chứng minh caller là người đã acquire key/lease đó khi release/renew | Không bị tái sử dụng hoặc đoán dễ |
| Fencing token tăng đơn điệu | Cho tài nguyên đích biết writer nào thuộc thế hệ mới hơn | Phải tăng theo những lần cấp quyền và được đích kiểm tra |
| Business version | Trạng thái thực thể nguồn thay đổi thế nào | Có phạm vi/version semantics phù hợp |
| Idempotency key | Một ý định nghiệp vụ có bị thực hiện lặp không | Ổn định cho cùng request |

Một UUID owner ngẫu nhiên không có thứ tự, nên không tự thay thế fencing token.

### 10.4. Cấp fencing token phải đủ tin cậy

Không nên mặc định `INCR fenceCounter` trên một Redis triển khai có thể mất write khi failover là một **sequence bền vững, tuyệt đối tăng đơn điệu** cho mọi tình huống. Tính chất phải được đảm bảo bởi authority cấp token theo mô hình lỗi yêu cầu.

Khi một tài nguyên không hỗ trợ kiểm tra token (ví dụ API bên thứ ba không có precondition), fencing ở nơi khác **không tự chặn** request đã được worker cũ gửi đi. Cần idempotency, một gateway kiểm soát quyền, hoặc thay đổi quy trình để giảm rủi ro.

## 11. DynamoDB: không có SQL row lock, dùng conditional claim/lease

DynamoDB không cung cấp một cú pháp SQL `SELECT ... FOR UPDATE` cho một item để ứng dụng giữ khóa dài hạn theo session. Thay vào đó thường dùng:

- `ConditionExpression` trên PutItem/UpdateItem/DeleteItem;
- `TransactWriteItems` cho phạm vi giao dịch được hỗ trợ;
- Một lock item/lease do ứng dụng hoặc thư viện điều phối quản lý;
- Một luồng xử lý tuần tự theo business key khi phù hợp.

### 11.1. Thiết kế lock item

Ví dụ bảng `JobLocks` dùng `PK`:

~~~json
{
  "PK": "JOB#J100",
  "ownerId": "worker-A",
  "leaseUntilEpoch": 1794643500,
  "fence": 41,
  "state": "PROCESSING"
}
~~~

Các số epoch chỉ minh họa format; thời gian thực tế phải tính từ clock/deadline nhất quán với thiết kế.

### 11.2. Atomic acquire khi lock hết hạn

Ý tưởng một `UpdateItem`:

~~~text
KEY PK = "JOB#J100"

CONDITION:
  attribute_exists(PK)
  AND (
       attribute_not_exists(leaseUntilEpoch)
       OR leaseUntilEpoch < :now
  )

UPDATE:
  SET ownerId = :owner,
      leaseUntilEpoch = :newDeadline
  ADD fence :one
~~~

Nếu item `JobLocks` được tạo trước với khóa rõ ràng, một request acquire áp dụng thành công sẽ tăng `fence` và cấp owner mới trong cùng thao tác nguyên tử.

Tùy lựa chọn schema, có thể cho conditional create khi key chưa tồn tại; khi đó phải xử lý đúng các trường absent và không được vô tình tạo lock duplicate. Ví dụ trên là **mẫu điều kiện**, không phải payload JSON API đầy đủ.

### 11.3. Lưu ý clock và lease expiration

DynamoDB không tự thay `:now` bằng “thời gian của server” trong `ConditionExpression`. Nếu client tự truyền `now` và hai worker lệch đồng hồ nhiều, một worker có thể nghĩ lease đã hết trước khi nó thực sự hết theo hệ khác.

Cần:

- Đồng bộ clock và quy tắc timeout/lease;
- Chọn biên an toàn;
- Dùng fencing tại sink khi rủi ro stale write đáng kể;
- Không lấy một field TTL của DynamoDB làm tín hiệu xóa/giải phóng đúng giây: TTL deletion là bất đồng bộ.

### 11.4. Renew và release có điều kiện

Gia hạn:

~~~text
UPDATE lock
IF ownerId = :owner
   AND fence = :fence
   AND leaseUntilEpoch > :now
SET leaseUntilEpoch = :later
~~~

Kết thúc:

~~~text
UPDATE lock
IF ownerId = :owner AND fence = :fence
SET state = "DONE"
REMOVE ownerId, leaseUntilEpoch
~~~

Nếu worker A cũ mang `fence=41` còn worker B đang giữ `42`, thao tác của A phải bị từ chối.

### 11.5. Lock client library

Có các thư viện/client lock dựa trên DynamoDB dùng lease, heartbeat, record version number hoặc những phương pháp tương đương. Dùng thư viện có kiểm chứng thường tốt hơn tự tạo giao thức vài dòng, nhưng vẫn phải kiểm tra:

- Hành vi khi owner process chết;
- Khi network partition và timeout;
- Khi ghi renew thành công nhưng phản hồi mất;
- Khi lease hết và owner cũ còn chạy;
- Khi region/failover thay đổi;
- Khi cần fencing tại tài nguyên đích.

**Lock library không tự biến mọi side effect ngoài DynamoDB thành giao dịch nguyên tử.**

### 11.6. Conditional writes trực tiếp thường đơn giản hơn lock item

Nếu yêu cầu chỉ là:

> Trừ 2 tồn kho khi `available >= 2`.

Hãy ưu tiên:

~~~text
UpdateItem Inventory(P100)
  ConditionExpression: available >= 2
  UpdateExpression: available = available - 2
~~~

Không cần tạo `JobLocks(P100)`, acquire, đọc inventory, trừ, rồi release. Giao thức lock nhiều bước có thể tạo thêm crash windows và latency.

## 12. MongoDB: update nguyên tử, transaction và lease document

MongoDB có cơ chế đồng thời bên trong storage engine, hỗ trợ thao tác nguyên tử trên **một document** và multi-document transactions theo topology/phạm vi được hỗ trợ. MongoDB không phơi bày một lệnh `SELECT FOR UPDATE` thông dụng như SQL để client giữ explicit row lock lâu trong khi thao tác tự do.

### 12.1. Claim job bằng findOneAndUpdate

Giả sử collection `jobs` có:

~~~json
{
  "_id": "J100",
  "state": "READY",
  "leaseUntil": null,
  "ownerId": null,
  "fence": 0,
  "payload": {"taskType": "EXPORT"}
}
~~~

Một worker có thể cố claim job đã sẵn sàng:

~~~javascript
const now = new Date();
const leaseUntil = new Date(now.getTime() + 30_000);
const workerId = "worker-A";

const claimed = db.jobs.findOneAndUpdate(
  {
    _id: "J100",
    state: "READY",
    $or: [
      { leaseUntil: null },
      { leaseUntil: { $lte: now } }
    ]
  },
  {
    $set: {
      state: "PROCESSING",
      ownerId: workerId,
      leaseUntil: leaseUntil
    },
    $inc: { fence: 1 }
  },
  {
    returnDocument: "after"
  }
);
~~~

Ở đây có một **điều kiện filter và mutation trên cùng document**, nên hai worker không được cùng claim cùng trạng thái ban đầu theo bảo đảm atomic document update.

Tuy nhiên, mẫu `state:"READY"` trên chỉ cho claim từ READY. Nếu cần reclaim job PROCESSING sau lease hết hạn, điều kiện state và việc tính số lần retry phải được thiết kế rõ.

### 12.2. Claim job tiếp theo từ một hàng chờ

Với nhiều document:

~~~javascript
const now = new Date();

const job = db.jobs.findOneAndUpdate(
  {
    state: "READY",
    $or: [
      { leaseUntil: null },
      { leaseUntil: { $lte: now } }
    ]
  },
  {
    $set: {
      state: "PROCESSING",
      ownerId: "worker-A",
      leaseUntil: new Date(now.getTime() + 30_000)
    },
    $inc: { fence: 1 }
  },
  {
    sort: { priority: -1, createdAt: 1, _id: 1 },
    returnDocument: "after"
  }
);
~~~

Điều kiện update một document được áp dụng nguyên tử, nhưng “tất cả worker luôn lấy job đúng thứ tự toàn cục” là một yêu cầu mạnh hơn và còn phụ thuộc concurrent inserts, sort, index và semantics cụ thể. Nên dùng index phù hợp cho các trường tìm job.

### 12.3. Heartbeat chỉ khi còn owner

~~~javascript
db.jobs.updateOne(
  {
    _id: "J100",
    state: "PROCESSING",
    ownerId: "worker-A",
    fence: 41,
    leaseUntil: { $gt: new Date() }
  },
  {
    $set: {
      leaseUntil: new Date(Date.now() + 30_000)
    }
  }
);
~~~

Nếu không match, worker không nên tiếp tục tự nhận mình còn quyền. Trong production, cần giải quyết sai khác clock và xử lý khi cập nhật heartbeat timeout/unknown.

### 12.4. Mark done chỉ khi còn owner

~~~javascript
db.jobs.updateOne(
  {
    _id: "J100",
    ownerId: "worker-A",
    fence: 41,
    state: "PROCESSING",
    leaseUntil: { $gt: new Date() }
  },
  {
    $set: {
      state: "DONE",
      finishedAt: new Date()
    },
    $unset: {
      ownerId: "",
      leaseUntil: ""
    }
  }
);
~~~

Đoạn này bảo vệ **document job**. Nếu worker đã gọi API ngoài rồi mới mark DONE, vẫn cần idempotency/outbox để tránh gọi lặp khi timeout.

### 12.5. MongoDB transaction không phải khóa ứng dụng dài hạn

Trong transaction, engine quản lý xung đột, snapshot và commit theo semantics sản phẩm. Một transaction đọc nhiều document không phải giấy phép để giữ tài nguyên kinh doanh trong nhiều phút, chờ người dùng thao tác hoặc gọi dịch vụ bên ngoài.

Không nên mở transaction MongoDB rồi đợi thanh toán/truyền file trong thời gian dài. Transaction dài có thể gây chi phí lock/snapshot/resource và gặp giới hạn thời gian.

Nếu cần giữ quyền trong một workflow dài, dùng **trạng thái reservation/lease bền vững**, không cố biến transaction ngắn thành lock kinh doanh dài.

## 13. Cassandra: LWT là cơ chế tương đương CAS, không phải row lock dài hạn

Apache Cassandra không dùng SQL `SELECT FOR UPDATE` để client giữ row lock trong lúc thao tác nhiều request. Khi cần conditional update, Cassandra có **Lightweight Transaction (LWT)** với các điều kiện CQL như `IF NOT EXISTS` hoặc `IF version = ...`.

### 13.1. Claim một job bằng LWT

Ví dụ:

~~~sql
CREATE TABLE jobs_by_id (
    job_id text PRIMARY KEY,
    state text,
    owner_id text,
    lease_until timestamp,
    generation bigint
);
~~~

Giả sử job J100 ở trạng thái READY:

~~~sql
UPDATE jobs_by_id
SET state = 'PROCESSING',
    owner_id = 'worker-A',
    generation = 41
WHERE job_id = 'J100'
IF state = 'READY';
~~~

CQL trả cột `[applied]` để báo điều kiện có được áp dụng hay không. Trong ví dụ, giá trị generation 41 do ứng dụng đã xác định; **không được suy rằng LWT tự sinh fencing token tăng dần chỉ vì có trường generation**.

Để cấp generation an toàn, cần giao thức được bảo vệ phù hợp. Ví dụ ứng dụng có thể đọc generation hiện tại rồi gửi LWT so sánh đúng giá trị cũ, đồng thời ghi generation mới trong một statement; với xung đột phải đọc và thử lại.

### 13.2. LWT dùng giao thức đồng thuận

LWT có chi phí phối hợp giữa replica theo cơ chế Paxos của Cassandra. Nó cung cấp check-and-write có bảo vệ trong phạm vi được hỗ trợ, nhưng không phải một lock mà caller giữ suốt cả workflow bên ngoài.

Không nên hiểu:

~~~text
IF state = READY thành công
    |
    +--> client đang nắm row lock trong 10 phút
~~~

Thay vào đó, statement đã thực hiện transition. Nếu cần xử lý 10 phút và có thể failover, phải xây **lease owner/generation và retry** ở tầng dữ liệu/ứng dụng.

### 13.3. Contention và hot partition

Hàng nghìn worker chạy LWT trên cùng một partition có thể làm tăng độ trễ và giảm throughput. Cần theo dõi serial consistency, trạng thái replica, timeout, latency và conflict.

Không thể lấy tốc độ của normal insert để suy tốc độ của LWT. Nếu một key quá nóng, cân nhắc queue theo key hoặc cấu trúc dữ liệu khác.

### 13.4. LWT trên một bảng không khóa mọi bảng phi chuẩn hóa

Giả sử:

~~~text
jobs_by_id[J100]          -> PROCESSING
jobs_by_owner[worker-A]   -> chưa có
jobs_by_state[READY]      -> vẫn còn J100
~~~

LWT trên `jobs_by_id` không biến những cập nhật `jobs_by_owner`, `jobs_by_state` thành một transaction ACID nhiều bảng. Nếu dùng event/outbox hoặc read model, cần đồng bộ và đối soát.

### 13.5. Đừng gọi Cassandra BATCH là pessimistic locking

Cassandra batch có semantics riêng, không phải một session transaction với row lock như DB quan hệ. Một batch nhiều partition không tự bảo đảm invariant phức hợp kiểm tra–ghi xuyên mọi bảng.

Nếu invariant trải nhiều object, có thể cần thay đổi mô hình aggregate, đưa authority về một partition hoặc dùng workflow khác.

## 14. Firestore: transaction mode khác nhau theo SDK và cấu hình

Cloud Firestore là trường hợp đáng chú ý vì tên “transaction” có thể che các cơ chế đồng thời khác nhau.

### 14.1. Server transactions

Các SDK server của Firestore dùng transaction do backend điều phối. Với cấu hình **pessimistic concurrency** ở môi trường hỗ trợ, transaction đọc document có thể giữ lock trên document liên quan, khiến các transaction/write cạnh tranh phải chờ hoặc thất bại theo semantics của dịch vụ.

Đây là một ví dụ cơ chế khóa bi quan được **database quản lý**, không phải một Redis advisory lock.

Nhưng mode concurrency có thể phụ thuộc **edition và cấu hình database**. Một số môi trường dùng optimistic concurrency. Không nên chỉ nhìn code `runTransaction()` rồi kết luận chắc chắn dùng pessimistic lock.

### 14.2. Mobile/web transactions

Các SDK mobile/web có cơ chế mô phỏng optimistic concurrency dựa trên document version/preconditions, bất kể chế độ concurrency của database trong những ngữ cảnh được tài liệu mô tả. Chúng không nên được mô tả là có cùng hành vi giữ document lock như server transaction.

### 14.3. Ví dụ giao dịch trừ tồn kho

Giả sử biến `db` là Firestore server SDK đã khởi tạo:

~~~javascript
const productRef = db.collection("inventory").doc("P100");

const reserved = await db.runTransaction(async (tx) => {
  const snapshot = await tx.get(productRef);

  if (!snapshot.exists) {
    return false;
  }

  const available = snapshot.get("available");

  if (typeof available !== "number" || available < 2) {
    return false;
  }

  tx.update(productRef, {
    available: available - 2
  });

  return true;
});
~~~

Dù backend ở chế độ pessimistic hay optimistic theo cấu hình, ứng dụng phải coi **transaction commit** là điểm quyết định kết quả. Nếu transaction abort vì contention, SDK có thể retry callback.

### 14.4. Cẩn thận side effect trong transaction callback

Sai thiết kế:

~~~javascript
await db.runTransaction(async (tx) => {
  const snapshot = await tx.get(orderRef);

  await chargePayment(); // Side effect ngoài Firestore.

  tx.update(orderRef, {
    status: "PAID"
  });
});
~~~

Nếu callback được chạy lại hoặc transaction thất bại, `chargePayment()` có thể bị gọi nhiều lần hoặc gọi thành công dù DB chưa commit.

Một hướng an toàn hơn là commit trạng thái + một dấu sự kiện bền vững trong phạm vi giao dịch được hỗ trợ, rồi worker idempotent thực hiện side effect.

### 14.5. Transaction không nên chờ người dùng

Không giữ Firestore transaction mở trong lúc chờ một người bấm nút “Xác nhận” vài phút. Với tác vụ dài, lưu trạng thái reservation/lease có deadline rồi dùng transaction ngắn cho từng bước.

## 15. Couchbase: getAndLock là ví dụ explicit document lock

Couchbase là một trong những NoSQL có cơ chế **explicit document locking** thông qua các API như `getAndLock` và `unlock` trong SDK phù hợp.

### 15.1. Ý tưởng

~~~text
Client A                           Couchbase
--------                           ---------
getAndLock(K, lockTime) --------->
                <--------------- Document + CAS token

Client B: replace(K) ------------>
                <--------------- Locked / conflict

Client A: replace/unlock với
CAS phù hợp --------------------->
                <--------------- Success / release
~~~

Lock được giới hạn thời gian theo sản phẩm; không phải một khóa vô hạn. Trong những phiên bản Couchbase phổ biến, thời gian lock explicit thường bị giới hạn ở **một số giây đến khoảng 30 giây**, và default/giới hạn cụ thể phải kiểm tra ở phiên bản SDK/server dùng thật.

### 15.2. Giả mã

~~~text
locked = collection.getAndLock("order::O100", lockTime=10s)

try:
    newDoc = transform(locked.content)
    collection.replace(
        "order::O100",
        newDoc,
        cas=locked.cas
    )
finally:
    if stillOwnsLock:
        collection.unlock("order::O100", locked.cas)
~~~

Đây là **giả mã**, không phải API nguyên văn của mọi Couchbase SDK. Sau khi replace thành công, lock có thể được giải phóng theo semantics của API; vì vậy không được gọi unlock mù quáng với một CAS token cũ và mong luôn thành công.

### 15.3. Vì sao có CAS token khi đã lock?

CAS giúp xác định đúng phiên bản tài liệu và tránh tác vụ của caller cũ tương tác sai với tài liệu đã đổi. Cách lock/unlock khi document bị thay đổi trong thời gian giữ lock phải dựa vào hợp đồng SDK.

### 15.4. Giới hạn

- Lock duration ngắn và có giới hạn.
- Không giữ lock qua workflow nhiều phút.
- Có thể tăng contention trên hot documents.
- Không bảo vệ một API ở hệ ngoài Couchbase.
- Không tự bảo đảm transaction nhiều document.
- Cần xử lý failover/timeout và khả năng lock hết hạn trước khi client hoàn tất.

Couchbase explicit document lock phù hợp cho một critical section **ngắn trên document**, không phải distributed workflow lock tổng quát.

## 16. Azure Cosmos DB for NoSQL: ETag, batch và lease ở tầng ứng dụng

Azure Cosmos DB for NoSQL chủ yếu cung cấp cơ chế kiểm soát đồng thời qua **ETag/If-Match** và giao dịch trong phạm vi được hỗ trợ, không phải một SQL row lock dài hạn cho client.

### 16.1. OCC với ETag

Một item:

~~~json
{
  "id": "O100",
  "tenantId": "T1",
  "status": "PAID",
  "_etag": "\"etag-7\""
}
~~~

Client đọc ETag, gửi update/replace với precondition `If-Match`. Nếu item đã đổi ETag, request có thể bị từ chối, thường với mã `412 Precondition Failed` theo API tương ứng.

Đây là **optimistic concurrency**. Nó không giữ khóa trong lúc user đọc và chuẩn bị sửa.

### 16.2. Transactional batch

Nếu nhiều item chia sẻ cùng logical partition key, `TransactionalBatch` của Cosmos DB for NoSQL có thể giúp cập nhật nguyên tử theo các giới hạn của dịch vụ.

Nhưng nếu invariant chạy qua hai logical partitions, một batch thông thường không tự bao phủ cả hai. Khi đó cần thiết kế lại partition key/aggregate hoặc workflow có thể phục hồi.

### 16.3. Lease documents

Ứng dụng có thể tự tạo document điều phối:

~~~json
{
  "id": "lease:J100",
  "tenantId": "T1",
  "ownerId": "worker-A",
  "leaseUntil": "2026-11-14T08:05:00Z",
  "generation": 41
}
~~~

Sau đó dùng ETag/precondition hoặc stored procedure/transaction theo phạm vi được hỗ trợ để acquire và renew an toàn.

**Lưu một document có trường `ownerId` chưa đủ tạo lock.** Mọi transition phải được bảo vệ bởi điều kiện nguyên tử. Nếu hai client cùng đọc “lease hết hạn” và cả hai replace không precondition, cả hai có thể nghĩ mình là chủ.

### 16.4. Change feed processor lease không phải lock nghiệp vụ tổng quát

Một số SDK/dịch vụ Cosmos DB dùng **lease container** để điều phối những worker đọc change feed. Lease đó phục vụ phân chia tiến độ của change feed processor, không nên tự suy là khóa độc quyền cho mọi business resource trong ứng dụng.

Cần tách công cụ điều phối stream với cơ chế bảo vệ invariant của đơn hàng/tồn kho.

## 17. HBase: row-level atomic mutation thay cho khóa dài hạn của client

Apache HBase hỗ trợ các thao tác nguyên tử theo **row** trong phạm vi được engine cung cấp, như `CheckAndMutate`, cùng các cơ chế nội bộ để tuần tự hóa mutation cạnh tranh.

### 17.1. Ví dụ ý tưởng

~~~text
RowKey = INVENTORY#P100

IF column stock:available >= 1
THEN decrement stock:available by 1
~~~

Cú pháp thực tế và các loại predicate hỗ trợ phụ thuộc HBase API/version; đây là **mô hình yêu cầu**, không phải statement HBase chạy trực tiếp.

### 17.2. Không suy ra multi-row transaction

Một row mutation nguyên tử **không** biến:

~~~text
Row INVENTORY#P100
Row ORDER#O100
Row AUDIT#A100
~~~

thành một giao dịch ACID nhiều row. Cần xem các khả năng transaction/hệ bao ngoài nếu có, hoặc thay mô hình.

### 17.3. Row lock nội bộ không phải lock người dùng giữ mãi

Database có thể dùng row locks nội bộ để thực thi row mutation, nhưng việc đó khác với việc SDK cung cấp lock để caller giữ vài phút qua nhiều request.

Bài học kiến trúc: **có nguyên tử theo row không đồng nghĩa có API khóa bi quan dài hạn**.

## 18. Elasticsearch/OpenSearch: optimistic concurrency không phải lock giao dịch

Elasticsearch có thể dùng những thông tin như `_seq_no` và `_primary_term` cho optimistic concurrency của một document:

~~~text
GET document
  _seq_no=42
  _primary_term=3

UPDATE if_seq_no=42&if_primary_term=3
~~~

Nếu tài liệu đã đổi, request sẽ conflict thay vì ghi đè vô điều kiện.

Đây là một kỹ thuật rất hữu ích khi update search document, nhưng:

- Nó không làm Elasticsearch trở thành nguồn transaction của mọi nghiệp vụ.
- Không giữ khóa trong lúc gọi service bên ngoài.
- Không thay thế idempotency của event projector.
- Search index có độ trễ visibility/refresh theo semantics engine.
- Bản sao search thường được dựng từ nguồn authoritative.

Nếu nghiệp vụ cần đảm bảo chỉ một worker thanh toán đơn hàng, đặt lock trên search document là lựa chọn không đúng ranh giới bảo vệ.

## 19. ZooKeeper, etcd và Consul: coordinator cho distributed locks

Khi nhiều dịch vụ hoặc nhiều database cần một authority điều phối, có thể dùng một dịch vụ coordination chuyên dụng.

Các hệ như Apache ZooKeeper, etcd hoặc Consul cung cấp những cơ chế như:

- Key/value có đồng thuận;
- Session hoặc lease;
- Watch/notification;
- Revision/sequence;
- Conditional transaction;
- Leader election;
- Ephemeral keys/nodes.

Khả năng cụ thể phụ thuộc sản phẩm. Không nên coi mọi dịch vụ là hoán đổi được, đặc biệt về thứ tự, session expiration và failure semantics.

### 19.1. ZooKeeper ephemeral sequential nodes

Một “recipe” lock phổ biến dùng những node tạm thời có số thứ tự:

~~~text
/locks/report/lock-00000101  (worker A)
/locks/report/lock-00000102  (worker B)
/locks/report/lock-00000103  (worker C)
~~~

Worker có số nhỏ nhất giữ lock. Worker khác **theo dõi node ngay trước mình**; khi node trước biến mất, nó kiểm tra lại thứ tự.

Cách watch predecessor giúp tránh việc mọi worker cùng bị đánh thức mỗi khi một holder rời đi, so với việc tất cả cùng watch node nhỏ nhất.

Node ephemeral gắn với session. Nếu session hết hạn, node có thể được xóa và worker khác được cấp quyền; **worker cũ vẫn có thể đang chạy** nếu nó không nhận biết session loss kịp thời.

### 19.2. etcd lease và revision

etcd hỗ trợ lease, transaction so sánh–ghi và các thư viện/concurrency primitive. Một worker có thể giữ key dưới lease; khi lease hết, key có thể được thu hồi.

Một số trường revision/index có tính đơn điệu theo cơ chế etcd, có thể phục vụ thiết kế fencing khi được dùng đúng với phạm vi và lịch sử cluster. Nhưng phải đảm bảo tài nguyên đích kiểm tra token mới hơn; chỉ có một số revision trong log chưa đủ.

### 19.3. Leader election không đồng nghĩa stale leader đã ngừng

Một leader bị mất session nhưng đang pause có thể chưa biết quyền đã hết. Leader mới được bầu, trong khi leader cũ thức dậy và gửi write cũ.

Do đó, **leader election cần fencing hoặc điều kiện ghi ở sink** nếu việc có hai leader cùng thực thi side effect gây hại.

### 19.4. Chi phí của coordinator

Một coordinator mạnh giúp quản lý quyền sở hữu nhưng cũng tạo:

- Hạ tầng cần vận hành;
- Mạng round-trip;
- Latency acquire;
- Giới hạn throughput của một lock nóng;
- Session renewal;
- Failure modes khi quorum mất;
- Nhu cầu phân quyền và audit.

Không nên đưa mọi lần tăng một counter nhẹ qua coordinator nếu atomic increment tại nơi lưu trữ đã đáp ứng invariant.

## 20. Single writer per key: cơ chế thay khóa đáng cân nhắc

Một mẫu khác là **tuần tự hóa các command thuộc cùng business key**.

~~~text
Commands:
  UpdateOrder(O100, ...)
  CancelOrder(O100, ...)
  ShipOrder(O100, ...)

          |
          v
Partition by orderId
          |
          v
One active consumer for O100
          |
          v
Apply state transitions in order
~~~

Nếu broker/consumer-group đảm bảo một partition có một active owner theo mô hình cần thiết, các command cùng key có thể được thực thi tuần tự trong một luồng.

### 20.1. Ưu điểm

- Giảm contention CAS trên hot keys.
- Dễ giữ thứ tự command theo key.
- Không cần giữ lock dài cho mỗi request.
- Hợp lý với state machine, ledger theo entity, job queues.

### 20.2. Giới hạn

- Khi rebalance/failover, một consumer cũ có thể còn chạy hoặc commit muộn.
- Broker delivery thường cần idempotency.
- Không tự bảo vệ hai command thuộc **hai partition** khác nhau.
- Nếu có writer ghi thẳng database bỏ qua queue, invariant có thể vỡ.
- Side effect bên ngoài vẫn cần idempotency/fencing.
- Consumer có thể crash sau commit DB nhưng trước ACK -> xử lý lại.

Single-writer là một **cấu trúc thực thi**, không phải phép màu exactly-once.

## 21. Deadlock: hai khóa, hai worker chờ nhau

Giả sử A cần cập nhật Order rồi Inventory, B cập nhật Inventory rồi Order.

~~~text
Worker A                              Worker B
--------                              --------
lock(Order)                           lock(Inventory)
lock(Inventory) -> WAIT               lock(Order) -> WAIT

        A chờ B; B chờ A
             DEADLOCK
~~~

Một số database transaction engine có deadlock detection và abort một transaction. Với **advisory distributed locks**, ứng dụng thường phải tự đặt timeout, thứ tự khóa và chiến lược recovery.

### 21.1. Khóa theo thứ tự toàn cục

Định nghĩa một thứ tự cố định:

~~~text
ORDER locks trước
INVENTORY locks sau
~~~

Mọi worker lấy theo cùng thứ tự để giảm nguy cơ vòng chờ. Với nhiều ID, có thể sắp xếp khóa theo chuỗi canonical trước khi acquire.

### 21.2. Try-lock và timeout

Một worker có thể:

1. Thử acquire trong giới hạn thời gian.
2. Nếu thất bại, release tất cả lock đã giữ.
3. Backoff với jitter.
4. Retry có giới hạn hoặc chuyển vào queue.

Không nên giữ một khóa rồi retry vô hạn khóa còn lại, vì dễ gây deadlock/starvation.

### 21.3. Phạm vi lock càng lớn càng nhiều contention

Một khóa global `lock:all-orders` đơn giản nhưng làm mọi đơn hàng phải chờ nhau. Khóa theo `orderId` tăng song song, nhưng cũng làm khó bảo vệ invariant liên quan nhiều order.

Chọn granularity đúng quan trọng hơn “càng khóa nhiều càng an toàn”.

## 22. Starvation, fairness và priority inversion

### 22.1. Starvation

Một worker liên tục thất bại khi acquire vì có nhiều worker khác lấy khóa trước. Nó có thể không bao giờ tiến lên dù hệ vẫn xử lý request đều đặn.

Redis `SET NX` hoặc conditional item writes thường **không hứa hàng đợi FIFO công bằng**. Nếu fairness quan trọng, cần queue/lock manager với thứ tự rõ ràng.

### 22.2. Priority inversion

Tác vụ ưu tiên cao chờ lock do tác vụ ưu tiên thấp giữ, trong khi tác vụ thấp bị trì hoãn bởi công việc khác.

Với lease dài hoặc critical section có external I/O, vấn đề có thể nghiêm trọng. Một nguyên tắc là:

> **Giữ critical section ngắn và tránh các thao tác không dự đoán được trong lúc giữ lock.**

### 22.3. Thundering herd

Khi lock hết hạn, hàng nghìn worker cùng thử acquire. Có thể gây bão request vào Redis/DynamoDB/Cassandra.

Biện pháp:

- Backoff có jitter;
- Giới hạn số contender;
- Queue theo key;
- Event/watch để đánh thức có chọn lọc;
- Chia tài nguyên thành nhiều key khi invariant cho phép;
- Giới hạn thời gian và số lần thử.

Đừng giải quyết thundering herd bằng cách bỏ điều kiện bảo vệ; như vậy chỉ chuyển bottleneck thành race condition.

## 23. Ranh giới transaction và tác vụ dài

### 23.1. Transaction ngắn

Một transaction phù hợp thường có dạng:

~~~text
BEGIN
  read/check
  update related records
COMMIT
~~~

Thời gian hoạt động ngắn, không chờ UI hay một API ngoài không kiểm soát.

### 23.2. Business workflow dài

Một luồng như:

~~~text
Đặt vé -> Chờ thanh toán 10 phút -> Xuất vé -> Gửi email
~~~

không nên cố giữ một transaction/row lock 10 phút. Cần trạng thái:

~~~text
AVAILABLE
   |
   v
RESERVED(expiresAt, owner, generation)
   |
   +--> PAID -> ISSUED
   |
   +--> EXPIRED -> AVAILABLE
~~~

Mỗi bước được commit bằng **transition có điều kiện**. Tác vụ hết hạn phải kiểm tra trạng thái hiện tại thay vì giải phóng vé vô điều kiện.

### 23.3. TTL không tự hoàn tác side effect

Nếu reservation record biến mất do TTL:

- Vé có thể vẫn bị trừ khỏi counter;
- Cổng thanh toán có thể đã nhận tiền;
- Một event có thể còn ở queue.

TTL giúp dọn dữ liệu, không thay quy trình hoàn tác/bù hoặc ledger.

## 24. Lỗi mạng và kết quả acquire không chắc chắn

Một worker gửi:

~~~text
SET lock:job:J100 tokenA NX PX 30000
~~~

Server có thể cấp lock nhưng phản hồi bị mất. Client thấy timeout:

~~~text
Client --> lock server: acquire
Server: lock đã được tạo
Server --> Client: response bị mất
Client: timeout, không biết mình có lock không
~~~

Nếu client tự thử acquire lại với owner token khác, nó có thể tự gặp lock đang tồn tại hoặc tạo trạng thái không rõ.

Một giao thức cần:

- Dùng owner token **ổn định cho một attempt**;
- Định nghĩa cách truy vấn lại quyền sở hữu nếu an toàn;
- Phân biệt result=granted, denied và unknown;
- Không thực hiện critical side effect khi chưa có bằng chứng quyền còn hiệu lực;
- Không xoá key vô điều kiện để “dọn lỗi”;
- Gắn timeout của request với deadline lease thực tế.

Tương tự với DynamoDB conditional write: timeout không có nghĩa condition fail và không chứng minh lock chưa cấp.

## 25. Crash sau side effect: vì sao lock không tạo exactly-once

Một timeline:

~~~text
T0: A acquire lock J100
T1: A gửi email thành công
T2: A crash trước khi ghi DONE
T3: Lease hết hạn
T4: B acquire lock J100
T5: B gửi email lần hai
~~~

Khóa đã làm việc theo hợp đồng: chỉ một owner hợp lệ tại một thời điểm. Nhưng tác động email vẫn bị lặp.

### 25.1. Idempotency của business action

Có thể tạo một `operationId` ổn định:

~~~json
{
  "jobId": "J100",
  "operationId": "SEND_EMAIL#J100",
  "recipientId": "U42",
  "state": "PENDING"
}
~~~

Worker chỉ xử lý cùng `operationId`, nơi nhận side effect nếu hỗ trợ idempotency sẽ từ chối thực hiện lần hai.

Nếu bên thứ ba không hỗ trợ idempotency, cần thiết kế audit/reconciliation và đôi khi chấp nhận/giảm rủi ro duplicate theo đặc thù nghiệp vụ. Không thể dùng lock nội bộ để đạt exactly-once end-to-end qua một hệ không phối hợp.

### 25.2. Outbox

Khi state transition và outbox record nằm trong một transaction phù hợp:

~~~text
BEGIN
  J100 -> DONE
  INSERT outbox event SEND_NOTIFICATION
COMMIT
~~~

relay có thể phát event ít nhất một lần, consumer idempotent xử lý. Outbox giúp thu hẹp khoảng mất event giữa cập nhật nguồn và publish, nhưng vẫn không tự đảm bảo external side effect exactly-once.

## 26. Bất biến nhiều bản ghi và write skew

Một khóa trên từng document riêng biệt có thể vẫn không bảo vệ invariant toàn tập.

Giả sử:

~~~text
doctor D1: onCall=true
doctor D2: onCall=true

Invariant: luôn có ít nhất một bác sĩ trực.
~~~

D1 đọc D2 còn trực và tự tắt trạng thái D1. D2 đọc D1 còn trực và tự tắt D2. Nếu mỗi người chỉ CAS/lock **document của chính mình**, cả hai mutation có thể thành công:

~~~text
D1=false
D2=false

Invariant bị vi phạm.
~~~

Đây là dạng **write skew**.

### 26.1. Chọn đúng phạm vi

Các cách:

- Một aggregate `ShiftOnCall` chứa tập bác sĩ và được cập nhật nguyên tử;
- Transaction với isolation đủ mạnh cho invariant;
- Một “slot” on-call duy nhất để quản lý ownership;
- Một coordinator/serial command processor theo shift;
- Điều kiện/khóa chung mà mọi transition phải sử dụng.

Khóa hai document độc lập chỉ hữu ích nếu mọi mutation tham gia vào một giao thức thực sự bảo vệ invariant chung.

### 26.2. Không nhầm locking với constraint

Một cơ chế lock có thể chặn hai writer cạnh tranh, nhưng business rule như “không bao giờ có hơn 3 đơn ACTIVE trên một khách” vẫn cần được **biểu diễn trong dữ liệu và kiểm tra đúng**.

Nếu không biết cần khóa gì, có thể khóa đúng kỹ thuật nhưng sai ngữ nghĩa.

## 27. Hot key: khi lock làm hệ nghẽn

Giả sử 10.000 request/s cùng dùng lock:

~~~text
lock:global-inventory
~~~

Nếu mỗi critical section mất 10 ms, một lock độc quyền được giữ lần lượt không thể xử lý vô hạn request đồng thời. Về mặt trực giác, throughput bị giới hạn bởi thời gian giữ lock và overhead điều phối:

\[
throughput_{max}\ \lesssim\ \frac{1}{holdTime}
\]

Đây là ước lượng cực đơn giản cho **một chuỗi thực thi độc quyền**, không phải SLA của mọi database.

### 27.1. Giảm phạm vi

Thay `lock:global-inventory` bằng `lock:inventory:P100` khi invariant chỉ thuộc một product. Những product khác có thể tiến hành song song.

### 27.2. Giảm thời gian giữ

Không giữ lock trong lúc:

- Gọi API thanh toán;
- Chờ email;
- Đọc file lớn;
- Render báo cáo;
- Chờ người dùng;
- Sleep/retry I/O dài.

Chỉ giữ khóa khi thực sự cần bảo vệ trạng thái chung, và chuẩn bị dữ liệu trước/sau critical section khi an toàn.

### 27.3. Thay lock bằng atomic operation

Nếu chỉ tăng view count, dùng `INCR` hoặc atomic increment trong DB thay vì acquire lock, read, add, write, release.

Nếu chỉ claim một job, dùng conditional state transition một item. Nếu có hàng nghìn contender trên cùng một key, cân nhắc partitioned queue.

## 28. Java: giao diện LeaseManager minh họa

Một ứng dụng có thể thiết kế abstraction để tránh trộn logic nghiệp vụ với Redis/DynamoDB/MongoDB cụ thể:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

public interface LeaseManager {

    record Lease(
            String resourceId,
            String ownerId,
            long fencingToken,
            Instant expiresAt
    ) {}

    Optional<Lease> tryAcquire(
            String resourceId,
            String ownerId,
            Duration leaseDuration
    );

    boolean renew(Lease lease, Duration leaseDuration);

    boolean release(Lease lease);
}
~~~

Đây là **interface khái niệm**, không phải implementation bảo đảm an toàn. Các method cần được thực thi trên một authority với điều kiện nguyên tử; `Lease` chỉ chứa dữ liệu, không làm lock trở nên đáng tin cậy.

### 28.1. Cách dùng an toàn hơn

~~~java
import java.time.Duration;
import java.util.Optional;
import java.util.UUID;

public final class JobRunner {
    private final LeaseManager leases;
    private final JobService jobs;

    public JobRunner(LeaseManager leases, JobService jobs) {
        this.leases = leases;
        this.jobs = jobs;
    }

    public void tryRun(String jobId) {
        String owner = UUID.randomUUID().toString();

        Optional<LeaseManager.Lease> acquired =
                leases.tryAcquire(
                        jobId,
                        owner,
                        Duration.ofSeconds(30)
                );

        if (acquired.isEmpty()) {
            return;
        }

        LeaseManager.Lease lease = acquired.get();

        try {
            // jobs.process cần kiểm tra fencing token
            // tại tài nguyên đích và xử lý idempotency.
            jobs.process(jobId, lease.fencingToken());
        } finally {
            // Release chỉ khi vẫn đúng owner/generation.
            leases.release(lease);
        }
    }

    public interface JobService {
        void process(String jobId, long fencingToken);
    }
}
~~~

Đoạn code **chưa có heartbeat/renew/cancellation**. Nó không nên được copy vào production rồi giả định job chạy hơn 30 giây vẫn an toàn. Mục đích là cho thấy API cần mang owner và fencing token vào việc xử lý.

### 28.2. Với job dài cần gì thêm?

- Heartbeat/renew chạy theo lịch có kiểm soát;
- Deadline và cancellation token;
- Nếu renew thất bại hoặc không rõ kết quả, dừng/không commit phần việc có thể hủy;
- Sink kiểm tra fencing token;
- Idempotency key cho side effect;
- Xử lý crash và resume;
- Log lease acquisition/release;
- Giới hạn retry;
- Chạy bù khi hoàn tất một phần.

Đừng tự triển khai heartbeat bằng một thread không kiểm soát mà không hiểu GC pauses, network partitions và hệ quả khi callback tiếp tục sau lease expiry.

## 29. So sánh cơ chế theo từng hệ

| Hệ | Có explicit pessimistic lock cho client? | Cơ chế được dùng phổ biến | Phạm vi & giới hạn cần nhớ |
|---|---|---|---|
| Redis | Không phải row lock DB nghiệp vụ; advisory lock qua key | `SET NX PX`, Lua compare-release/renew, `WATCH` | Key/slot, TTL, replication/failover, stale owner |
| DynamoDB | Không có `SELECT FOR UPDATE` | `ConditionExpression`, `TransactWriteItems`, lease item | Item/giao dịch theo giới hạn, clock và region |
| MongoDB | Không có SQL-style row lock công khai dài hạn | Atomic document update, transaction, lease doc | Một document hoặc transaction có giới hạn, write conflict |
| Cassandra | Không có row lock phiên ứng dụng | `IF` / LWT (Paxos), state + owner | Chi phí đồng thuận, hot partition, không khóa bảng dẫn xuất |
| Firestore | Server transaction có thể pessimistic theo mode | Transaction, preconditions | SDK/mobile khác server; retry callback; giới hạn transaction |
| Couchbase | Có `getAndLock` document theo API hỗ trợ | Explicit document lock + CAS token | Lock duration ngắn, một document |
| Cosmos DB for NoSQL | Không có SQL-style row lock dài hạn | ETag/If-Match, transactional batch, lease doc | Item và cùng logical partition cho batch |
| HBase | Có cơ chế row serialization nội bộ | CheckAndMutate/row mutation | Một row, không phải multi-row transaction tự động |
| Elasticsearch/OpenSearch | Không dùng làm business row lock | Sequence/version optimistic concurrency | Document index, refresh/visibility |
| ZooKeeper/etcd/Consul | Coordination primitive chuyên dụng | Lease, ephemeral nodes, watch, revision | Cần resource-side fencing, session failure, vận hành quorum |
| Partitioned queue | Không phải database lock | Single active consumer per key | Rebalance, retry, idempotency, không tự atomic across partitions |

Bảng này là **định hướng thiết kế**, không phải một hợp đồng API dùng nguyên xi cho mọi phiên bản/edition. Khi triển khai, phải tra điều kiện hỗ trợ theo đúng SDK và cấu hình production.

## 30. Cách chọn khóa cho từng use case

### 30.1. Tồn kho một sản phẩm

**Ưu tiên:** conditional decrement ở item/document authoritative.

Lý do: invariant nằm trên một bản ghi, thời gian thao tác ngắn. Thêm distributed lock bên ngoài thường tạo overhead mà không tăng bảo đảm cần thiết.

### 30.2. Hai người cùng sửa hồ sơ

**Ưu tiên:** OCC bằng version/ETag/CAS token; trả conflict khi snapshot cũ.

Lý do: chỉnh sửa form có thời gian chờ người dùng dài, không thể giữ lock suốt khi người dùng suy nghĩ. Khi conflict, người dùng có thể cần merge có ý nghĩa.

### 30.3. Job xử lý video mất 20 phút

**Ưu tiên:** lease + heartbeat + fencing/idempotency + checkpoint; có thể dựa trên queue.

Lý do: quá dài để giữ transaction hay getAndLock document. Worker có thể chết hoặc bị pause.

### 30.4. Singleton scheduler chạy mỗi giờ

Có thể dùng leader election/lease nếu chỉ cần một coordinator; vẫn phải có **idempotency theo kỳ chạy** để chống việc job cũ và mới cùng thực hiện side effect khi lease thay đổi.

Ví dụ business key:

~~~text
REPORT#2026-11-14T09:00Z
~~~

Conditional create kết quả theo kỳ và process idempotent thường quan trọng hơn chỉ một leader.

### 30.5. Chuyển tiền giữa hai tài khoản

**Không ưu tiên một Redis lock đơn giản như bảo đảm duy nhất.** Cần ledger/transaction/giao thức bảo vệ invariant nhiều bản ghi, idempotency và audit.

### 30.6. Cập nhật cache có thể tính lại

`SET NX PX` có thể đủ để giảm nhiều client tính cùng một dữ liệu. Nếu lock mất và hai worker cùng tính, hệ chỉ lãng phí CPU chứ không làm sai trạng thái nghiệp vụ, có thể chấp nhận.

### 30.7. Đặt ghế/vé có deadline

Dùng reservation state có version/lease, transition theo điều kiện và nguồn authoritative. Nếu một vị trí đã được cấp lại, callback thanh toán cũ phải bị từ chối/bù theo quy tắc nghiệp vụ.

## 31. Kiểm thử khóa và lease dưới lỗi phân tán

Kiểm thử tuần tự:

~~~text
A acquire -> success
B acquire -> fail
A release
B acquire -> success
~~~

là cần thiết nhưng chưa đủ.

### 31.1. Hai caller đồng thời

- Đặt barrier cho 100 caller cùng acquire một resource.
- Xác nhận chỉ một caller được công nhận trong một generation.
- Kiểm tra những caller thất bại không thực hiện side effect.
- Ghi nhận thời gian chờ và số attempt.

### 31.2. Owner crash không release

- A acquire rồi crash.
- Quan sát lease hết hạn theo hợp đồng.
- B có thể tiếp tục.
- Đảm bảo kết quả A chưa commit không bị coi là đã thành công.

### 31.3. Pause lâu hơn lease

- A acquire token 41.
- Đóng băng A lâu hơn lease.
- B acquire token 42 và ghi sink.
- A thức dậy và cố ghi sink.
- Sink phải từ chối token 41 nếu yêu cầu fencing.

Đây là test quan trọng nhất để phân biệt **“lock key hợp lệ”** với **“stale worker không thể gây hại”**.

### 31.4. Mất phản hồi sau acquire

- Server cấp lock nhưng response bị chặn.
- Client không được tự coi đã/không có quyền theo cách gây duplicate.
- Kiểm tra recovery của attempt và owner token.

### 31.5. Renew timeout

- A gửi renew; response mất.
- A không được kéo dài lease chỉ bằng niềm tin chủ quan.
- B có thể acquire nếu deadline thực sự qua.
- Fencing bảo vệ sink nếu cả hai cùng chạy.

### 31.6. Failover và network partition

- Đánh giá trạng thái lock khi Redis primary/replica chuyển vai trò;
- DynamoDB region/replication semantics;
- ZooKeeper/etcd mất quorum;
- Node clock lệch;
- Rebalance consumer.

Thử nghiệm phải dựa trên mô hình lỗi của hệ đang dùng; không chạy chaos test gây rủi ro trên production khi chưa có quy trình.

### 31.7. Deadlock và starvation

- A lấy R1 rồi đợi R2, B lấy R2 rồi đợi R1.
- Quan sát timeout/recovery.
- Kiểm tra có worker đợi mãi do không công bằng không.

### 31.8. Side effect đúng một lần theo business key

- A gửi payment/email thành công rồi crash.
- B tiếp tục job.
- Xác nhận idempotency ngăn duplicate trong giới hạn mà hệ ngoài hỗ trợ.

## 32. Monitoring và SLO của cơ chế khóa

| Nhóm | Metric cần đo | Vì sao quan trọng |
|---|---|---|
| Acquire | Success/denied/timeout/unknown | Phân biệt xung đột và lỗi hạ tầng |
| Waiting | p50/p95/p99 wait-to-acquire | Phát hiện lock trở thành bottleneck |
| Hold | Thời gian giữ lock/lease | Phát hiện critical section quá dài |
| Renewal | Renew success/failure/late | Phát hiện owner có nguy cơ mất quyền |
| Contentions | Attempt per key, retry/backoff | Phát hiện hot key, thundering herd |
| Fencing | Stale write rejected | Chứng minh sink chặn owner cũ |
| Crash recovery | Job reclaimed, time-to-recovery | Đánh giá liveness |
| Correctness | Duplicate jobs, oversell, lost update | Kiểm tra invariant thực sự |
| Distributed | Session expire, quorum loss, region failover | Theo dõi cơ chế coordination |
| Cost | RU/RCU/WCU, CPU, network, storage | Hiểu chi phí của lock và retry |

Một SLO tốt cần gắn với mục tiêu nghiệp vụ, ví dụ:

> Mỗi job xuất báo cáo theo kỳ chỉ được công bố một kết quả cuối cùng; mọi write từ generation cũ phải bị từ chối tại nơi lưu kết quả.

SLO về độ trễ:

> p95 thời gian đợi acquire dưới ngưỡng đã xác định ở mức tải đại diện.

**Không đánh giá cơ chế chỉ bằng tốc độ acquire.** Một lock rất nhanh nhưng thỉnh thoảng cho stale worker ghi sai là không phù hợp với nghiệp vụ có yêu cầu safety cao.

## 33. Những sai lầm phổ biến

**“NoSQL nào cũng có SELECT FOR UPDATE.”** Không. Nhiều hệ chỉ có atomic conditional write hoặc transaction theo phạm vi hạn chế.

**“CAS là pessimistic lock.”** Không. CAS là conditional operation/OCC; có thể tạo hiệu quả loại trừ cho một transition nhưng không giữ lock dài hạn.

**“Đã có document `locked=true` thì tài nguyên được khóa.”** Không nếu check và write không nguyên tử, hoặc writer khác bỏ qua field đó.

**“Redis SET NX là khóa bền vững qua mọi failover.”** Không tự động. Cần hiểu replication, crash và mô hình lỗi.

**“Có TTL thì worker cũ sẽ dừng.”** Không. Lease hết hạn không kết thúc process/thread đang pause.

**“So token khi release đủ để bảo vệ mọi side effect.”** Không. Sink cần fencing/idempotency khi worker cũ có thể còn gửi write.

**“UUID owner token cũng là fencing token.”** Không. UUID ngẫu nhiên không mang thứ tự generation.

**“Cấp fencing token từ counter nào cũng an toàn.”** Không nếu counter có thể rollback hoặc không có bảo đảm đơn điệu trong mô hình failover.

**“DynamoDB TTL tự giải phóng lease đúng giây.”** Không. TTL deletion là bất đồng bộ; logic lease phải dùng điều kiện deadline.

**“MongoDB transaction có thể mở suốt khi người dùng thanh toán.”** Không nên. Transaction dài gây giới hạn và contention; dùng trạng thái reservation.

**“Cassandra LWT có thể giữ row lock sau khi statement kết thúc.”** Không. Nó là conditional transaction theo giao thức của Cassandra, không phải khóa session dài hạn.

**“Firestore mọi SDK đều dùng pessimistic document locks.”** Không. Mode và SDK ảnh hưởng semantics.

**“Couchbase getAndLock bảo vệ toàn bộ workflow nhiều phút.”** Không. Lock document có thời gian giới hạn và không chặn hệ ngoài.

**“Hai khóa riêng lẻ luôn bảo vệ invariant toàn tập.”** Không; write skew vẫn có thể xảy ra.

**“Lock đảm bảo exactly-once.”** Không. Crash sau side effect tạo khoảng không chắc chắn; cần idempotency và recovery.

**“Timeout acquire nghĩa là chắc chắn không có khóa.”** Không. Phản hồi có thể mất sau khi server cấp quyền.

**“Khi conflict cứ retry liên tục.”** Có thể tạo thundering herd/starvation; cần backoff và giới hạn.

**“Global lock cho mọi tài nguyên là an toàn nhất.”** Có thể làm toàn hệ nối đuôi và tạo single point of contention. Chọn scope vừa đủ bảo vệ invariant.

**“Coordinator bầu leader rồi mọi ghi từ leader đều hợp lệ.”** Stale leader có thể tiếp tục; cần fencing tại tài nguyên.

## 34. Bài tập tự vận dụng

### Bài tập 1 — Nhận diện khóa thật và khóa tư vấn

Ứng dụng có Redis key `lock:order:O100`. Một service khác sửa trực tiếp MongoDB order O100 mà không kiểm tra Redis.

**Câu hỏi:** Redis key có tự chặn lệnh MongoDB không?

**Gợi ý:** Không. Đây là advisory lock trừ khi mọi writer tuân thủ hoặc MongoDB sink kiểm tra fencing/owner.

### Bài tập 2 — CAS hay lock?

Tồn kho P100 còn 1 và hai client cùng đặt. Database hỗ trợ atomic update với điều kiện `available >= 1`.

**Câu hỏi:** Có cần tạo distributed lock riêng không?

**Gợi ý:** Thường không. Conditional decrement trong cùng item bảo vệ invariant này trực tiếp và đơn giản hơn.

### Bài tập 3 — Lease hết hạn

A có lease 30 giây, bị pause 45 giây. B acquire được lease mới khi A chưa thức dậy.

**Câu hỏi:** Vì sao A vẫn nguy hiểm?

**Gợi ý:** A có thể tiếp tục side effect sau khi quyền đã hết. Cần fencing/authorization tại sink.

### Bài tập 4 — Token nào dùng để release?

Redis lock value là một owner UUID ngẫu nhiên. Worker A muốn release.

**Câu hỏi:** Nên chạy `DEL lockKey` hay compare token rồi delete nguyên tử?

**Gợi ý:** Compare-and-delete nguyên tử; tránh xóa lock mới của B.

### Bài tập 5 — Fencing

A nhận token 41, B nhận 42 và đã ghi sink. A gửi write kèm 41.

**Câu hỏi:** Sink cần làm gì?

**Gợi ý:** Từ chối stale token 41 bằng điều kiện nguyên tử khi sink đã chấp nhận 42.

### Bài tập 6 — DynamoDB lock item

Hai worker đọc `leaseUntilEpoch=1000` và cùng thấy `now=1100`. Cả hai gọi update vô điều kiện.

**Câu hỏi:** Có bảo đảm chỉ một owner không?

**Gợi ý:** Không. Đưa `leaseUntilEpoch < :now` vào `ConditionExpression` của cùng UpdateItem.

### Bài tập 7 — Đồng hồ lệch

A tính `now` bằng đồng hồ chạy nhanh hơn 60 giây, B dùng đồng hồ đúng.

**Câu hỏi:** Điều gì có thể sai trong lease dùng client-supplied now?

**Gợi ý:** A có thể coi lease chưa hết là đã hết. Cần clock discipline, biên an toàn và fencing khi hậu quả lớn.

### Bài tập 8 — MongoDB claim job

Hai worker gọi `findOneAndUpdate` với filter `state="READY"`, mutation `state="PROCESSING", ownerId=...` trên cùng document.

**Câu hỏi:** Điều gì ngăn cả hai claim trạng thái READY?

**Gợi ý:** Filter và update được thực hiện nguyên tử trên document theo semantics của MongoDB.

### Bài tập 9 — Cassandra LWT

Client thực hiện CQL `UPDATE ... IF state='READY'`, nhận `[applied]=true` rồi chạy job 20 phút.

**Câu hỏi:** Có đang giữ Cassandra row lock trong toàn bộ 20 phút không?

**Gợi ý:** Không. LWT chỉ thực hiện conditional transition. Muốn reclaim an toàn cần lease/generation và bảo vệ side effect.

### Bài tập 10 — Firestore callback

Transaction callback của Firestore gửi email rồi update document. SDK retry callback hai lần.

**Câu hỏi:** Có thể có mấy email?

**Gợi ý:** Có nguy cơ nhiều email. Tách side effect khỏi callback và dùng idempotent outbox/workflow.

### Bài tập 11 — Couchbase getAndLock

Một worker khóa document trong 10 giây nhưng xử lý 40 giây.

**Câu hỏi:** Có thể tin lock bảo vệ toàn bộ 40 giây không?

**Gợi ý:** Không. Lock duration hữu hạn; cần thiết kế critical section ngắn hoặc cơ chế khác.

### Bài tập 12 — Khóa hai tài nguyên

A khóa Order rồi Inventory; B khóa Inventory rồi Order.

**Câu hỏi:** Tình trạng nào có thể xảy ra và cách giảm?

**Gợi ý:** Deadlock. Áp cùng thứ tự khóa, timeout, release và retry có jitter.

### Bài tập 13 — Write skew

Hai bác sĩ cùng kiểm tra người còn lại đang trực rồi tự tắt `onCall` của document mình bằng CAS.

**Câu hỏi:** Vì sao cả hai CAS thành công mà invariant sai?

**Gợi ý:** Invariant thuộc hai documents, không được bảo vệ bằng CAS riêng lẻ. Cần aggregate/transaction/authority chung.

### Bài tập 14 — Singleton scheduler

Hai pod cùng chạy báo cáo ngày hôm qua. Cả hai tranh leader lease và một pod cũ có thể chạy lại sau timeout.

**Câu hỏi:** Ngoài leader election cần gì?

**Gợi ý:** Idempotency theo ngày báo cáo, fencing/conditional publish và xử lý stale leader.

### Bài tập 15 — Side effect sau crash

Worker A có lock, gọi payment thành công rồi crash trước khi ghi DONE. B lấy lock và gọi payment lại.

**Câu hỏi:** Lock đã ngăn duplicate payment chưa?

**Gợi ý:** Chưa. Cần idempotency key ở payment provider, record bền vững và reconciliation.

### Bài tập 16 — Fairness

100 worker liên tục tranh một Redis lock, vài worker không bao giờ acquire.

**Câu hỏi:** Có vi phạm đặc tính FIFO đã được Redis SET NX hứa không?

**Gợi ý:** SET NX không mặc định hứa FIFO fairness. Nếu cần fairness, dùng queue/lock manager với giao thức thứ tự thích hợp.

### Bài tập 17 — Multi-region

Hai region ghi độc lập cùng acquire một “global lock” lưu bằng điều kiện cục bộ, trước khi dữ liệu replicate.

**Câu hỏi:** Có bảo đảm chỉ một global owner không?

**Gợi ý:** Không mặc định. Cần authority có điều phối toàn cục hoặc mô hình conflict/tài nguyên phù hợp.

### Bài tập 18 — Stale owner và Redis renew

A đã hết lease, B lấy lock với token khác. A gửi lệnh `PEXPIRE` vô điều kiện.

**Câu hỏi:** Rủi ro gì?

**Gợi ý:** A có thể kéo dài lock của B theo cách sai quy tắc. Renew phải so owner token nguyên tử.

### Bài tập 19 — Chọn kiến trúc

Có ba bài toán:

1. Tăng cache counter mỗi request;
2. Người dùng chỉnh hồ sơ trong 5 phút;
3. Worker xuất video mất 30 phút.

**Câu hỏi:** Chọn atomic increment, OCC, lock dài hạn hay lease?

**Gợi ý:** (1) Atomic increment; (2) OCC/version; (3) Lease + heartbeat + idempotency/fencing, không giữ DB transaction 30 phút.

### Bài tập 20 — Thiết kế thử nghiệm

Một nhóm tuyên bố “distributed lock của chúng tôi an toàn vì hai worker không bao giờ lấy được lock cùng lúc trong test”.

**Câu hỏi:** Còn thiếu test nào?

**Gợi ý:** Pause dài hơn TTL, network partition, renew timeout, failover, unknown acquire, stale write, fencing, crash sau side effect và idempotency.

## 35. Checklist trước khi chọn cơ chế khóa cho production

- [ ] Invariant cần bảo vệ đã được mô tả rõ và có thể kiểm thử.
- [ ] Đã xác định key/document/partition hay tài nguyên nào là authority.
- [ ] Đã kiểm tra liệu một atomic conditional write có đủ hay không.
- [ ] Nếu cần transaction, đã xác định phạm vi và isolation thực tế.
- [ ] Nếu dùng advisory lock, mọi writer có tuân thủ hay sink có cưỡng chế?
- [ ] Lease có owner token duy nhất cho mỗi lần acquire.
- [ ] Acquire được bảo vệ bằng một check-and-write nguyên tử.
- [ ] Renew/release kiểm tra owner và generation.
- [ ] Có deadline, clock-skew policy và không dựa vào TTL cleanup tức thì.
- [ ] Khi owner mất quyền, worker có thể dừng hoặc sink từ chối stale writes.
- [ ] Fencing token thực sự đơn điệu và được sink kiểm tra nguyên tử khi cần.
- [ ] Có timeout/backoff/jitter, giới hạn retry và xử lý unknown outcome.
- [ ] Có thiết kế tránh deadlock và starvation nếu lấy nhiều lock.
- [ ] Critical section ngắn, không chờ người dùng hoặc external API dài.
- [ ] Side effect ngoài DB có idempotency hoặc quy trình đối soát.
- [ ] Có workflow recover khi worker chết hoặc lease hết.
- [ ] Đã xét multi-region, failover và replication consistency.
- [ ] Có metric contention, wait time, renewal, stale-writer rejection.
- [ ] Đã kiểm thử pause, timeout sau commit, failover và duplicate business action.
- [ ] Không tuyên bố “exactly-once” chỉ vì có lock.

## 36. Tổng kết

**Khóa bi quan** là một lựa chọn để ngăn các thao tác xung đột trước khi chúng sửa trạng thái. Trong hệ NoSQL, cơ chế tương đương có thể tồn tại ở nhiều lớp: **explicit document lock** của Couchbase, **transaction-managed locks** trong những chế độ Firestore hỗ trợ, **conditional update/CAS** của MongoDB, DynamoDB, Cassandra và Cosmos DB, hay **lease** được xây trên Redis, database item hoặc một coordinator như ZooKeeper/etcd.

Điểm khác biệt quan trọng là **một CAS nguyên tử không phải khóa dài hạn**, và **một khóa tư vấn trong Redis không tự cưỡng chế các write tới database khác**. Khi công việc kéo dài qua nhiều giây/phút, cần xác định chuyện gì xảy ra nếu worker pause, lease hết hạn, failover hoặc response bị mất. **Fencing token được tài nguyên đích kiểm tra**, cùng owner/generation và idempotency, là những công cụ giúp tránh stale worker và duplicate business action.

Để chọn giải pháp đúng, hãy bắt đầu bằng **bất biến cần bảo vệ và phạm vi dữ liệu của nó**, rồi chọn cơ chế đơn giản nhất đạt yêu cầu: atomic conditional write cho một item, OCC cho form dài, transaction cho cập nhật nhiều object trong phạm vi hỗ trợ, single-writer queue cho hot key, hay lease/coordinator cho công việc phân tán lâu. Đồng thời phải tính đến contention, deadlock, clock, retry, phục hồi và giám sát.

**Nguyên tắc cốt lõi:** một cơ chế khóa chỉ đáng tin cậy khi nó được cấp phát nguyên tử, có phạm vi và thời hạn rõ ràng, và **mọi thao tác gây tác động quan trọng đều được kiểm tra quyền sở hữu hiện hành tại nơi thực sự ghi**. Còn phần nghiệp vụ trải nhiều hệ vẫn cần transaction, idempotency hoặc workflow phục hồi riêng, không thể phó mặc cho một lock key.

