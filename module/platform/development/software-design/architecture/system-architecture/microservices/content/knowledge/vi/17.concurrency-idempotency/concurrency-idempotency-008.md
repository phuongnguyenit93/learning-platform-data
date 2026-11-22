# Khóa phân tán, thời hạn thuê và vai trò của fencing token

## 1. Bối cảnh: một khóa có thực sự ngăn được hai worker ghi dữ liệu?

Một hệ thống microservices thường có nhiều replica cùng đọc job, điều khiển một shard hoặc tái tạo dữ liệu chung. Một mutex nằm trong JVM chỉ đồng bộ các thread của tiến trình ấy; nó không kiểm soát Pod khác. Vì vậy nhóm phát triển có thể đặt khóa trong Redis, database hoặc hệ thống coordination để chỉ một worker nhận quyền xử lý một tài nguyên.

Ví dụ:

~~~text
                  Scheduler / Queue
                         |
         +---------------+---------------+
         |               |               |
      Worker A        Worker B        Worker C
         |               |               |
         +---------------+---------------+
                         |
                   Shared Storage
~~~

Điều khó nằm ở trường hợp tiến trình cũ **mất quyền nhưng vẫn chạy**:

1. Worker A lấy khóa cho report-42 và bắt đầu tạo báo cáo.
2. A bị tạm dừng lâu do GC, máy ảo bị suspend, CPU starvation hoặc mạng chậm.
3. Khóa hết hạn nên coordinator cấp quyền cho B.
4. B ghi kết quả báo cáo phiên mới.
5. A tiếp tục chạy và ghi bản báo cáo cũ, có thể ghi đè kết quả B.

Không nhất thiết coordinator cấp hai khóa hợp lệ cùng lúc; lỗi là **lệnh ghi của holder đã hết quyền vẫn được nơi lưu dữ liệu chấp nhận**.

Để thiết kế đúng cần phân biệt:

- **Distributed lock:** ai được bộ điều phối xem là owner.
- **Lease:** quyền ấy tồn tại trong thời hạn bao lâu và được gia hạn thế nào.
- **Owner token:** nhận diện đúng holder khi renew hoặc release.
- **Fencing token:** số thế hệ quyền sở hữu, giúp sink phát hiện lệnh từ holder cũ.
- **Idempotency/version/invariant:** các cơ chế bổ sung để bảo vệ dữ liệu và hiệu ứng nghiệp vụ.

Mục tiêu của bài học là biết **khi nào cần khóa phân tán, khóa không bảo đảm điều gì, và phải đặt cơ chế bảo vệ tại đâu** thay vì chỉ triển khai một đoạn SET NX rồi tin rằng hệ thống đã an toàn.

## 2. Bảng khái niệm

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Local mutex | Khóa trong một process | synchronized hoặc ReentrantLock trong Java |
| Distributed lock | Cơ chế phối hợp quyền giữa nhiều tiến trình | Chọn một leader xử lý một shard |
| Lease | Quyền tạm thời có hạn hoặc gắn với phiên | Lease 15 giây, renew định kỳ |
| Owner/session ID | Định danh duy nhất của một lần giữ quyền | UUID của holder |
| Fencing token / epoch | Số thế hệ tăng đơn điệu khi cấp quyền mới | 105, 106, 107 |
| Stale worker | Worker không còn quyền nhưng vẫn gửi lệnh | A thức dậy sau GC pause |
| Lock coordinator | Nguồn quyết định cấp quyền | PostgreSQL, etcd, ZooKeeper hoặc lock service |
| Sink / protected resource | Nơi cuối cùng chấp nhận thay đổi | Database, file store, service ghi dữ liệu |
| CAS/version guard | Ghi có điều kiện dựa trên state/version | UPDATE WHERE version = 8 |
| Idempotency key | Nhận diện thao tác logic để retry không lặp hiệu ứng | paymentAttemptId |
| Cancellation | Tín hiệu yêu cầu worker dừng công việc | Context canceled |
| Linearizability | Các thao tác có một thứ tự quan sát nhất quán theo contract | Atomic acquire dựa trên compare-and-set |

**Owner UUID không phải fencing token.** UUID giúp biết khóa đang thuộc ai nhưng không nói holder nào mới hơn. Fencing token có thứ tự tăng, nhưng token cũng vô ích nếu resource đích không thực thi kiểm tra.

## 3. Khi nào nên sử dụng distributed lock?

Các tình huống có thể hưởng lợi:

- Chọn một worker chạy job định kỳ cho mỗi tenant.
- Chọn leader điều phối một shard hoặc một batch có nhiều bước.
- Ngăn nhiều process đồng thời thực hiện migration hoặc rebuild cùng một index.
- Giới hạn số coordinator cùng sở hữu một thiết bị hay một external integration.
- Điều khiển chuyển giao trách nhiệm từ worker lỗi sang worker mới.
- Tránh lặp thao tác tốn kém dù lặp đôi không gây sai dữ liệu.

Nhưng phân tán không có nghĩa mọi bài toán cần distributed lock. Nhiều trường hợp phù hợp hơn với các cơ chế sẵn có ở nguồn dữ liệu:

| Yêu cầu | Phương án thường đơn giản hơn |
|---|---|
| Không tạo hai Order cùng business key | UNIQUE constraint / idempotency key |
| Cập nhật một row an toàn | Local transaction, atomic UPDATE, optimistic version |
| Không bán vượt tồn kho | Reservation và invariant tại Inventory owner |
| Chống xử lý trùng event | Inbox/ledger và business identity |
| Chạy nhiều job độc lập trên queue | Consumer group + idempotent handler |
| Cộng điểm hay số dư | Ledger append-only + atomic invariant |
| Cập nhật document theo version | Compare-and-swap / If-Match |
| Một cron chạy cùng cluster | Job controller có election/lease, đồng thời vẫn bảo vệ side effect |

Ví dụ Inventory có thể dùng câu UPDATE kèm WHERE quantity >= requested thay vì đặt một khóa Redis cho mỗi SKU. Distributed lock thêm network hop và tình huống lỗi mới; invariant database vẫn cần được bảo vệ.

## 4. Safety và liveness: đánh đổi nền tảng

**Safety:** không xảy ra kết quả bị cấm, chẳng hạn stale writer ghi đè state mới hoặc hai leader cùng commit thao tác mâu thuẫn.

**Liveness:** hệ thống vẫn có thể tiếp tục sau khi worker chết, coordinator phục hồi hoặc lease hết hạn.

Một khóa không bao giờ hết hạn có thể giữ quyền quá lâu khi owner chết, làm hệ thống không tiến triển. Lease cho phép cấp lại quyền, cải thiện liveness. Nhưng lease hết hạn **không tiêu diệt tiến trình cũ**, tạo yêu cầu safety mới.

~~~text
Lock vĩnh viễn:
  + ít nguy cơ chuyển quyền khi owner chậm
  - nguy cơ kẹt vĩnh viễn nếu holder crash

Lease có TTL:
  + holder chết -> quyền có thể chuyển
  - holder pause -> thức dậy sau khi mất quyền
  => cần bảo vệ hiệu ứng ở nơi ghi
~~~

Không có một TTL vừa bảo đảm mọi worker chậm không mất quyền vừa bảo đảm failover cực nhanh. Tính đúng đắn không được dựa trên giả định “GC chắc chắn ngắn hơn 5 giây”.

## 5. Timeline stale worker

Giả sử quyền dành cho resource report-42 có TTL 10 giây:

~~~text
t=0   A acquire thành công, lease epoch=41
t=2   A bắt đầu tính toán
t=3   A bị GC pause 15 giây
t=10  Lease của A hết hạn ở coordinator
t=11  B acquire mới, epoch=42
t=13  B ghi kết quả mới
t=18  A thức dậy, vẫn giữ object LeaseGrant(epoch=41)
t=19  A gửi WRITE kết quả cũ
~~~

Nếu Storage chỉ nhận PUT không có điều kiện, kết quả B bị ghi đè. Điều này không phủ nhận coordinator đã quản lý lease đúng; nó cho thấy **quyền không tự được thực thi ở sink**.

Những nơi có thể gây pause không chỉ là GC: process bị suspend, container bị thiếu CPU, network partition, queue chờ, I/O block, client retry sau timeout, TCP packet đến trễ hay job chạy quá lâu.

**Check lease trước khi write không đủ**: worker có thể kiểm tra đúng ở t=2 rồi pause đến t=18. Đây là race giữa lúc kiểm tra và lúc sử dụng quyền (TOCTOU). Để đạt safety cao, cần kiểm tra tại điểm commit trong một protocol có thứ tự đáng tin.

## 6. Lease: quyền tạm thời

Lease thường có vòng đời:

~~~text
NOT_OWNED
   |
   | acquire success
   v
OWNED (ownerId + epoch + expiry)
   |         |
   |         +---- renew success -> tiếp tục OWNED
   |
   +---- release ----------> NOT_OWNED
   |
   +---- expiry ----------- > NOT_OWNED
   |
   +---- renew uncertain --> UNKNOWN -> hành động bảo thủ
~~~

Một worker có thể mất quyền mà không nhận được thông báo ngay. Vì vậy trạng thái phía client “tôi đã acquire” chỉ đúng tại thời điểm đã được cấp; không phải đặc quyền vĩnh viễn.

### 6.1. Acquire

- Dùng khóa tài nguyên ổn định: tenant:42:report:daily hoặc shard:7.
- Acquire phải là thao tác atomic; không tự SELECT rồi INSERT bằng hai bước tách rời.
- Không cho hai tiến trình cùng lấy được quyền hợp lệ dưới failure model đã cam kết.
- Trả owner/session ID mới cho mỗi lần cấp quyền.
- Nếu dùng fencing, trả epoch **tăng đơn điệu** gắn với lần acquire thành công.
- Có giới hạn thời gian chờ, retry/backoff và quan sát contention.

### 6.2. Renew

- Chỉ holder có **đúng owner ID và đúng epoch hiện hành** được renew.
- Holder đã hết hạn không được gia hạn quyền cũ sau khi bên khác có thể acquire.
- Khi renew timeout, kết quả có thể UNKNOWN: coordinator đã gia hạn nhưng response mất, hoặc chưa gia hạn.
- Worker nên ngừng tạo side effect mới nếu không còn bằng chứng quyền hợp lệ.
- Renewal interval phải được chọn theo số liệu network, GC, coordinator latency và TTL.

### 6.3. Release

- Release cần so khớp owner/session và epoch; không xóa lock chỉ bằng tên key.
- Nếu A hết hạn rồi B giữ quyền, release của A không được xóa quyền B.
- Release là best effort; process crash vẫn phải được phục hồi bằng expiry/session cleanup.
- Không tự coi release failure là quyền vẫn thuộc mình.

## 7. Owner token khác fencing token ở đâu?

### 7.1. Owner token ngẫu nhiên

Ví dụ key Redis:

~~~text
key   = lock:report:42
value = 4f6a-...-9d8b (random UUID)
TTL   = 15000 ms
~~~

Giá trị owner giúp script release xác minh:

~~~text
Nếu Redis value vẫn là UUID của A:
    A có thể xóa key
Nếu value đã là UUID của B:
    A không được xóa key
~~~

Nhưng UUID không biểu diễn thế hệ mới/cũ. Không thể hỏi một storage service “UUID 4f6a và UUID 81bc, cái nào phải có quyền ghi trước?” mà có đáp án dựa trên thứ tự.

### 7.2. Fencing token tăng đơn điệu

Coordinator cấp một số thế hệ:

~~~text
Grant A -> token 41
Grant B -> token 42
Grant C -> token 43
~~~

Mỗi lệnh nguy hiểm mang token:

~~~text
A -------- PUT(token=41) --------> Storage
B -------- PUT(token=42) --------> Storage
A -------- PUT(token=41) --------> Storage (stale)
~~~

Storage phải có quy tắc **chỉ chấp nhận thế hệ hợp lệ**. Nếu đã quan sát thế hệ 42 và đang bảo vệ state bằng 42, nó có thể từ chối 41. Token nên được cấp bởi nguồn đáng tin có tính chất thứ tự trong phạm vi resource, không tự tăng theo RAM mỗi worker.

### 7.3. Quan trọng: max-token-seen không đồng nghĩa current-owner

Nếu Storage lưu **token cao nhất từng nhận**, token 41 sẽ bị từ chối **sau khi** Storage đã nhận token 42. Nhưng nếu B vừa acquire 42 **chưa gửi bất kỳ write nào tới Storage**, A gửi token 41 trước, Storage vẫn có thể thấy token cao nhất là 40 và chấp nhận 41.

Vì vậy phải phân biệt hai contract:

- **Monotonic fencing theo token đã quan sát:** lệnh cũ không thể ghi đè trạng thái đã được bảo vệ bởi thế hệ mới hơn mà sink đã thấy.
- **Strict current lease authorization:** mọi ghi phải chứng minh token trùng quyền hiện hành ngay tại thời điểm quyết định ghi, kể cả khi holder mới chưa từng ghi.

Contract thứ hai cần sink kiểm tra **authoritative current epoch** trong một ranh giới atomic phù hợp, hoặc protocol chuyển quyền khiến sink biết epoch mới trước khi cho phép tác động. Đừng hứa strict exclusivity nếu chỉ lưu max-seen token.

## 8. Fencing enforcement trong database

Ví dụ một bảng kết quả báo cáo:

~~~sql
CREATE TABLE report_results (
    report_id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    last_fencing_token BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
~~~

Một cách kiểm tra token đã thấy:

~~~sql
UPDATE report_results
SET payload = :new_payload,
    last_fencing_token = :token,
    updated_at = NOW()
WHERE report_id = :report_id
  AND :token >= last_fencing_token;
~~~

Phải kiểm tra **affected rows**:

- 1 row: điều kiện token được đáp ứng, nhưng vẫn phải xét invariant/idempotency.
- 0 row: có thể do token cũ hoặc record không tồn tại; cần xử lý lỗi rõ.

### 8.1. Dùng dấu > hay >=?

Nếu mỗi epoch chỉ có **một lần commit kết quả cuối**, có thể dùng token > last_token để chặn lặp. Nếu một epoch phải ghi nhiều bước, dùng >= có thể cần thiết, nhưng điều này **không ngăn lặp một thao tác** trong cùng epoch.

Ví dụ hai lệnh trừ tồn cùng token 42 vẫn có thể trừ hai lần nếu retry sau timeout. Vì vậy:

- **Fencing** trả lời “holder/phiên nào mới hơn?”
- **Idempotency** trả lời “thao tác này đã được áp dụng chưa?”
- **Version/CAS** trả lời “state nền tôi dựa vào còn mới không?”
- **Domain invariant** trả lời “trạng thái này có hợp lệ không?”

Các cơ chế bổ sung nhau.

### 8.2. Sink phải thực thi, không chỉ nhận header

Một header X-Fencing-Token là vô ích nếu handler chỉ log giá trị rồi UPDATE không điều kiện. Cần bảo vệ tại bước thay đổi state, tốt nhất là trong một transaction có ràng buộc phiên/epoch.

Nếu một batch script hoặc admin console bỏ qua check, bảo đảm safety bị phá. Rà soát **mọi đường ghi** tới cùng tài nguyên.

## 9. Redis SET NX PX: có ích nhưng chưa phải fencing

Ví dụ mẫu lock:

~~~redis
SET lock:tenant-42:daily-report <random-owner-id> NX PX 15000
~~~

- NX chỉ set nếu key chưa tồn tại.
- PX 15000 đặt TTL 15 giây.
- Owner ID ngẫu nhiên giúp release đúng holder.
- SET thành công chứng minh acquire theo semantics của Redis instance/tập triển khai đang dùng.

### 9.1. Release an toàn bằng Lua

~~~lua
-- KEYS[1]: lock key
-- ARGV[1]: expected owner ID
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
~~~

So sánh và xóa atomically tại Redis. Nếu lock đã chuyển chủ, A không xóa được key B.

### 9.2. Renew an toàn bằng Lua

~~~lua
-- KEYS[1]: lock key
-- ARGV[1]: expected owner ID
-- ARGV[2]: TTL in milliseconds
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("PEXPIRE", KEYS[1], ARGV[2])
end
return 0
~~~

Renew phải được xác nhận. Nếu RPC timeout, không biết chắc thao tác đã thành công hay chưa.

### 9.3. Giới hạn cần ghi rõ

Mẫu Redis trên:

- **Không cung cấp fencing epoch tăng đơn điệu.**
- Không tự chặn worker cũ ghi database sau TTL.
- Không bao phủ transaction ở PostgreSQL hoặc external HTTP API.
- Có rủi ro liên quan replication/failover nếu trạng thái lock chưa được sao chép bền vững trước khi primary chuyển.
- Không tự bảo đảm exclusivity trong mọi network partition.
- Không thay thế idempotency nghiệp vụ.

Nó có thể phù hợp với cache refresh hoặc job có thể chạy lại an toàn. Với thanh toán, số dư hoặc điều khiển thiết bị có hậu quả lớn, cần cơ chế mạnh hơn hoặc bảo vệ từ nguồn dữ liệu.

### 9.4. Tại sao gọi INCR rồi SET NX chưa đủ?

Một ý tưởng là gọi Redis INCR để lấy token rồi thực hiện acquire. Nhưng nếu token được cấp **trước** khi lock thật sự thành công, worker thua cuộc vẫn có token cao hơn holder hiện hành. Nếu counter bị reset khi failover hoặc restore, token có thể giảm. Nếu sink không kiểm, con số cũng chẳng bảo vệ gì.

Muốn token dùng như fencing, cần chứng minh:

1. Token gắn với **lần cấp quyền thành công**.
2. Thứ tự cấp token có tính nhất quán phù hợp.
3. Không tái sử dụng token sau crash, restore hoặc xóa/recreate resource.
4. Sink dùng token trong thao tác ghi.
5. Failure model của coordinator thực sự đáp ứng yêu cầu.

Đừng coi UUID, timestamp local hay counter RAM là fencing token đủ an toàn chỉ vì chúng “thường không trùng”.

## 10. PostgreSQL lease row và epoch tăng nguyên tử

Nếu domain state và lock metadata cùng PostgreSQL, một database transaction có thể là công cụ tốt hơn một distributed lock tách riêng.

### 10.1. Bảng lease

~~~sql
CREATE TABLE resource_leases (
    resource_key TEXT PRIMARY KEY,
    owner_id UUID NOT NULL,
    lease_epoch BIGINT NOT NULL CHECK (lease_epoch >= 1),
    expires_at TIMESTAMPTZ NOT NULL
);
~~~

### 10.2. Acquire bằng UPSERT có điều kiện

~~~sql
INSERT INTO resource_leases (
    resource_key, owner_id, lease_epoch, expires_at
)
VALUES (
    :resource_key,
    :owner_id,
    1,
    clock_timestamp() + INTERVAL '15 seconds'
)
ON CONFLICT (resource_key) DO UPDATE
SET owner_id = EXCLUDED.owner_id,
    lease_epoch = resource_leases.lease_epoch + 1,
    expires_at = clock_timestamp() + INTERVAL '15 seconds'
WHERE resource_leases.expires_at <= clock_timestamp()
RETURNING resource_key, owner_id, lease_epoch, expires_at;
~~~

- Có row RETURNING: acquire thành công và đã nhận epoch.
- Không có row RETURNING: resource vẫn có lease hiệu lực; phải bỏ qua hoặc retry.
- Nhờ unique key/row lock, quyết định cấp quyền và tăng epoch diễn ra theo transaction tại DB.
- **Không xóa rồi recreate row** tùy tiện, vì sẽ reset epoch về 1.
- Không đọc từ replica stale để quyết định owner.
- PostgreSQL dùng clock_timestamp() là wall clock phía server: cần theo dõi clock drift/failover và giới hạn của TTL. Không nhầm với monotonic clock.

### 10.3. Renew đúng owner/epoch

~~~sql
UPDATE resource_leases
SET expires_at = clock_timestamp() + INTERVAL '15 seconds'
WHERE resource_key = :resource_key
  AND owner_id = :owner_id
  AND lease_epoch = :lease_epoch
  AND expires_at > clock_timestamp()
RETURNING lease_epoch, expires_at;
~~~

Không có row trả về nghĩa là caller không xác minh được mình còn quyền. Không renew chỉ dựa vào resource_key.

### 10.4. Release đúng owner/epoch

~~~sql
UPDATE resource_leases
SET expires_at = clock_timestamp()
WHERE resource_key = :resource_key
  AND owner_id = :owner_id
  AND lease_epoch = :lease_epoch;
~~~

Release của A không thể thay đổi lease do B nắm nếu epoch/owner đã đổi.

### 10.5. Khi database failover

Cơ chế này phụ thuộc vào durability và topology PostgreSQL. Nếu failover làm mất một transaction acquire được trả success nhưng chưa replicate bền vững theo cấu hình, thứ tự quyền có thể không đạt contract bạn kỳ vọng. Hãy kiểm chứng sync replication, backup/restore, failover và cách xử lý in-flight requests trong hạ tầng thật.

## 11. Xác minh quyền ngay trong transaction ghi

Nếu resource_leases và business state cùng database, có thể giữ lease row lock trong transaction rất ngắn để kiểm **current owner**, rồi commit hiệu ứng.

~~~sql
BEGIN;

SELECT lease_epoch
FROM resource_leases
WHERE resource_key = :resource_key
  AND owner_id = :owner_id
  AND lease_epoch = :lease_epoch
  AND expires_at > clock_timestamp()
FOR UPDATE;

-- Application phải xác minh SELECT trả đúng một row.
-- Nếu không: ROLLBACK và từ chối STALE/LEASE_LOST.

UPDATE report_results
SET payload = :payload,
    last_fencing_token = :lease_epoch,
    updated_at = NOW()
WHERE report_id = :resource_key
  AND last_fencing_token <= :lease_epoch;

-- Kiểm tra affected rows, business constraints và version.
COMMIT;
~~~

Điều quan trọng:

- Acquire/renew/release trên cùng lease row sẽ phải tôn trọng row lock. Quyền không thể lặng lẽ chuyển giữa check và update nếu mọi bên dùng cùng protocol.
- Không tính báo cáo 10 phút hoặc gọi HTTP bên ngoài khi đang giữ SELECT FOR UPDATE.
- Ghi trong transaction ngắn, sau khi đã tính toán.
- Nếu transaction chạy quá lâu, có thể qua expiry theo wall clock; cần giới hạn thời gian transaction và điều kiện nghiệp vụ. Row lock giúp serialize chuyển quyền, không tự hứa side effect hoàn tất trước một mốc wall-clock tuyệt đối.
- Nếu nơi ghi là database khác hoặc cloud API, transaction tại DB điều phối **không atomic với side effect** đó.

Khi mọi state cùng một DB, đôi khi SELECT FOR UPDATE/optimistic version trực tiếp trên business row còn đơn giản hơn tạo resource_leases.

## 12. Sink ở hệ thống khác: cấp epoch chưa đủ

Giả sử etcd cấp epoch nhưng worker ghi sang Object Storage hoặc một service khác:

~~~text
Lease Authority                   Worker                   Storage
     |                               |                         |
     +--- epoch 100 ---------------->|                         |
     |                               +--- write token 100 ---->|
     |                               |                         |
     +--- epoch 101 --> Worker B     |                         |
     |                               |      B write token 101 ->|
     |                               |                         |
     |                 Worker A ------+--- write token 100 ---->|
     |                                           reject stale   |
~~~

Các câu hỏi bắt buộc:

1. Storage kiểm token bằng logic nào?
2. Storage có cập nhật token và dữ liệu **atomically** không?
3. Có một authoritative current epoch hoặc chỉ max token từng thấy?
4. Có thể có stale request đến **sau acquire mới nhưng trước write mới** không?
5. Nếu Storage có nhiều replica, các replica thống nhất về epoch thế nào?
6. Có đường ghi trực tiếp nào bỏ qua token?
7. Token có được ràng buộc resource identity và service authorization?
8. Thao tác có thể được lặp trong cùng epoch không, và idempotency key ở đâu?

Nếu sink chỉ nhớ max-seen epoch, cần thừa nhận cửa sổ đã nêu. Nếu yêu cầu nghiêm ngặt, hãy dùng current-epoch check/protocol chuyển quyền có thứ tự và phối hợp với sink, hoặc serialize writes tại service owner.

### 12.1. Header truyền token qua API

~~~http
PUT /internal/reports/report-42
X-Lease-Resource: report-42
X-Fencing-Epoch: 1024
Idempotency-Key: report-run-2026-11-12
Authorization: Bearer <service-token>
Content-Type: application/json

{ "version": 19, "result": "ready" }
~~~

X-Lease-Resource và X-Fencing-Epoch là ví dụ **header tự định nghĩa**. Service nhận phải xác thực caller, kiểm epoch thuộc resource đúng và kiểm business idempotency. Header do client bên ngoài tự gửi không được coi là giấy phép thực hiện ghi.

## 13. etcd và ZooKeeper: coordination source

### 13.1. etcd

etcd cung cấp key-value, transaction/compare và revision với semantics nhất quán phù hợp cho nhiều bài toán điều phối. Thiết kế phải phân biệt:

- **Lease ID:** định danh cơ chế TTL/session của etcd.
- **Revision:** số thứ tự thay đổi trong store theo semantics của etcd.
- **Fencing epoch:** giá trị chọn theo một acquisition thành công, mang đến sink.

Không mặc nhiên dùng lease ID như token tăng đơn điệu. Nếu chọn revision từ transaction acquire, cần bảo đảm token gắn chính xác với **grant thực sự**, không với một thao tác khác.

Pseudocode khái niệm:

~~~text
grant lease
txn:
  IF lock-key currently absent:
       PUT lock-key = ownerID attached to lease
       receive successful revision / epoch under contract
  ELSE:
       fail acquire

worker uses epoch in protected writes
~~~

Code thật phụ thuộc thư viện/version và cách xác định revision. Cần kiểm tra consistency của read/txn, cách xử lý session expiry và failover.

### 13.2. ZooKeeper

ZooKeeper hỗ trợ ephemeral sequential nodes thường được dùng cho election/lock recipes. Sequence trong phạm vi parent có thể biểu diễn thứ tự thế hệ; ephemeral node mất khi session hết hạn.

- Phải xử lý session expiration: worker cũ có thể vẫn đang chạy.
- Không coi watch notification là bằng chứng đồng hồ worker đã dừng.
- Không xóa/recreate namespace khiến số thứ tự mất tính đơn điệu nếu sink còn giữ epoch cũ.
- Sử dụng recipe/library có xử lý lost watches, connection state và herd effects.
- Đưa sequence/epoch tới nơi thực thi effect và kiểm tra ở đó.

Một coordination system trưởng thành giúp cấp quyền đáng tin hơn, nhưng không tự bảo vệ database khác nếu database bỏ qua token.

## 14. Đồng hồ, TTL và gia hạn

### 14.1. Ai đo thời gian?

Mỗi máy có thể lệch wall clock. Worker không nên tự quyết định lease còn sống chỉ vì giờ local nhỏ hơn timestamp do nó lưu. Coordinator/authority phải là nơi quyết định quyền có còn hiệu lực.

Trong tiến trình dùng System.nanoTime() để đo elapsed có thể phù hợp, nhưng nó không thay thế trạng thái lease ở coordinator.

### 14.2. Đặt TTL và renew interval

Một ví dụ minh họa:

~~~text
TTL:              15 giây
Renew interval:    5 giây
Work unit:         chia thành chunk nhỏ có checkpoint
Network p99:       vài trăm mili giây
~~~

Không lấy ví dụ làm default production. Cần đo:

- GC pause và CPU starvation p99/p99.9.
- Coordinator latency, failover và thời gian unavailable.
- Network jitter, packet loss.
- Thời gian phát hiện lease lost và dừng worker.
- Chi phí failover khi TTL dài.
- Tải renew khi hàng nghìn lease.
- Lock hold duration và business operation latency.

**TTL dài hơn giảm false expiry nhưng khiến recovery chậm; TTL ngắn hơn tăng liveness nhưng nhạy với pause.** Dù chọn TTL nào, cơ chế sink-side safety vẫn quan trọng.

### 14.3. Renew trả timeout/UNKNOWN

Nếu worker gửi renew nhưng không nhận response, nó không biết chắc coordinator đã renew hay chưa. Chính sách bảo thủ:

1. Không bắt đầu side effect mới.
2. Thử xác minh ownership qua API đáng tin trong giới hạn.
3. Nếu chưa xác nhận được, coi lease bị mất từ phía client.
4. Ngừng việc mới/cancel công việc hợp tác.
5. Để sink thực thi kiểm tra quyền ở bước commit.
6. Cho hệ thống recovery tiếp nhận job qua checkpoint và idempotency.

## 15. Java: mô hình LeaseGrant và ProtectedSink

Ví dụ các interface tách cấp quyền và nơi thực hiện ghi:

~~~java
import java.time.Duration;
import java.util.UUID;

public record LeaseGrant(
    String resourceKey,
    UUID ownerId,
    long fencingEpoch
) {}

public interface LeaseCoordinator {
    LeaseGrant tryAcquire(String key, Duration ttl);
    boolean renew(LeaseGrant grant, Duration ttl);
    boolean release(LeaseGrant grant);
}

public interface ProtectedSink {
    boolean writeIfAuthorized(
        String resourceKey,
        long epoch,
        String operationId,
        byte[] result
    );
}
~~~

Ví dụ worker:

~~~java
public final class ReportWorker {
    private final LeaseCoordinator coordinator;
    private final ProtectedSink sink;

    public ReportWorker(
            LeaseCoordinator coordinator, ProtectedSink sink) {
        this.coordinator = coordinator;
        this.sink = sink;
    }

    public void run(String reportId, String jobRunId) {
        LeaseGrant lease = coordinator.tryAcquire(
            reportId, Duration.ofSeconds(15)
        );
        if (lease == null) {
            return;
        }

        try {
            byte[] result = computeReport(reportId);

            boolean accepted = sink.writeIfAuthorized(
                reportId,
                lease.fencingEpoch(),
                jobRunId,
                result
            );
            if (!accepted) {
                throw new IllegalStateException(
                    "Lease lost or write conflict"
                );
            }
        } finally {
            coordinator.release(lease);
        }
    }

    private byte[] computeReport(String reportId) {
        return new byte[0]; // Placeholder.
    }
}
~~~

Ví dụ chỉ thể hiện **contract cần có**:

- Chưa triển khai heartbeat/renewal cho job dài.
- computeReport là placeholder, không tạo báo cáo thật.
- writeIfAuthorized **phải kiểm epoch và operation ID tại sink**; nếu chỉ ghi không điều kiện thì không an toàn.
- Release phải so owner/epoch; lỗi release không đồng nghĩa có quyền tiếp tục.
- Nếu cần strict current-owner checking, sink phải tham gia protocol phù hợp chứ không chỉ nhận epoch.
- Retry cùng jobRunId cần business idempotency và trạng thái job bền vững.

Không nên đặt các lời gọi HTTP chậm trong một DB transaction giữ row lock; tính toán trước, chỉ commit trạng thái ngắn sau khi đã xác minh quyền.

## 16. Leader election và zombie leader

Một hệ thống dùng lock để chọn leader xử lý shard:

~~~text
Shard 7:
  Leader A (epoch 200)
       |
       | mất session
       v
  Leader B (epoch 201)
       |
       | worker A thức dậy
       v
  A cố cập nhật checkpoint cũ
~~~

Quy trình đúng:

1. B được coordinator cấp quyền mới theo một authority đáng tin.
2. B nhận epoch 201 và đọc checkpoint business bền vững.
3. B xác định phần việc đã commit; phần chưa chắc chắn phải đối soát.
4. Mọi commit lên shard mang epoch/operationId.
5. Sink chặn stale requests của A theo semantics đã công bố.
6. A ngừng tạo việc mới khi phát hiện session/renew failure.
7. Một callback cũ từ A không được tự vượt qua phiên ownership mới.

Nếu checkpoint chỉ nằm trong RAM A, B không biết phần nào đã hoàn thành. Cần business record/checkpoint và idempotency để takeover không nhân đôi side effect.

## 17. Fencing và message queue

Consumer group trong Kafka có thể chỉ gán một partition cho một member tại một thời điểm theo group assignment, nhưng một member **cũ** sau rebalance vẫn có thể tiếp tục chạy handler đang dang dở. Broker có thể redeliver khi chưa ACK/commit offset.

Vì vậy:

- Partition assignment không thay thế business idempotency.
- Offset commit không atomic với database write theo mặc định.
- Khi consumer mất assignment, dừng task mới và cancel task cũ khi có thể.
- Nếu một partition owner điều khiển shared state, có thể cần generation/epoch tại sink.
- Bảo vệ message processing bằng Inbox/ledger, unique key, transaction rồi ACK.
- Với event cùng aggregate, đảm bảo ordering/version guard; fencing không tự giải quyết out-of-order deltas.

Không thêm distributed lock cho mỗi message nếu broker + database unique constraint đã giải quyết bài toán. Mỗi lock thêm tải, latency và failure mode.

## 18. External API không hiểu token

Giả sử worker cần charge qua một payment provider chỉ hỗ trợ POST /charge và không biết fencing epoch. A đã hết lease vẫn có thể gửi charge sau khi B takeover.

Thêm một header X-Fencing-Epoch chỉ hữu ích khi **provider hoặc một adapter có thẩm quyền thật sự kiểm tra nó**. Một adapter đơn giản check lease rồi gọi provider vẫn có race nếu quyền đổi giữa check và side effect.

Cần thiết kế:

- Một business operation ID ổn định cho charge.
- Provider idempotency key khi được hỗ trợ.
- API tra cứu kết quả khi request timeout nhưng provider đã commit.
- Payment Service owner nắm ledger/trạng thái và serialize command phù hợp.
- Reconciliation và compensation/void/refund theo nghiệp vụ.
- Không retry với ID mới khi kết quả cũ đang UNKNOWN.
- Kiểm tra quyền tại nơi chịu trách nhiệm ghi side effect hoặc một protocol serialization thật sự.

**Lease không phải transaction với provider.** Nếu không thể đảm bảo không lặp và không thể đối soát, cần đánh giá lại khả năng của provider hoặc quy tắc nghiệp vụ.

## 19. Khóa nhiều tài nguyên và deadlock

Ví dụ:

~~~text
Worker A:
  acquire lock:order
  wait for lock:inventory

Worker B:
  acquire lock:inventory
  wait for lock:order
~~~

Đây là một tình huống deadlock có thể xảy ra khi giữ hai distributed locks. Biện pháp:

1. Giảm số khóa cần giữ cùng lúc.
2. Áp thứ tự acquire cố định trên toàn hệ thống.
3. Giới hạn wait time và total request deadline.
4. Release đúng owner, kể cả khi một bước thất bại.
5. Backoff có jitter, tránh contender đập liên tục.
6. Không giữ lock khi gọi API bên ngoài chậm.
7. Cân nhắc gom invariant về một domain owner/local transaction.

Fencing chỉ xử lý stale ownership ở sink, không giải quyết deadlock do thứ tự acquire sai.

## 20. Lock key: global, tenant, shard hay entity?

Phạm vi lock quyết định throughput và rủi ro:

| Phạm vi | Ưu điểm | Nhược điểm |
|---|---|---|
| Global | Dễ hiểu, chỉ một công việc toàn hệ thống | Bottleneck và blast radius rộng |
| Per tenant | Tenant độc lập có thể chạy song song | Cần định nghĩa tenant context đáng tin |
| Per shard | Phù hợp leader/partition assignment | Cần di chuyển shard và epoch đúng |
| Per entity | Độ song song lớn | Rất nhiều lock, contention coordinator |
| Per job run | Chống hai worker chạy một đợt | Không nhất thiết bảo vệ cùng tài nguyên giữa nhiều đợt |

Chọn theo **invariant**, không theo sơ đồ class. Ví dụ hai đơn hàng cùng tiêu hạn mức tín dụng của một khách thì lock per-order không bảo vệ giới hạn tổng khách hàng. Có thể cần một nguồn dữ liệu chính có atomic constraint thay vì lock trên từng order.

## 21. Retention của epoch và vòng đời resource

Fencing yêu cầu số thế hệ không bị tái sử dụng trong phạm vi tài nguyên còn tồn tại lệnh cũ.

Nếu xóa resource_leases rồi tạo lại key cùng tên với epoch 1, một worker cũ giữ token 500 có thể bị đánh giá sai (hoặc người mới bị từ chối) nếu sink vẫn giữ metadata thế hệ cũ.

Cần xác định:

- Resource ID có được tái sử dụng hay không?
- Epoch có cần tồn tại sau khi job hoàn thành?
- Restore từ backup có làm quay ngược counter không?
- Chuyển region/shard có đổi namespace epoch không?
- Cần kết hợp epoch với một **incarnation ID** được quản lý bền vững không?
- Sink lưu watermark/epoch bao lâu?
- Lệnh đã enqueue trong broker/DLQ có thể xuất hiện lại sau nhiều tháng không?
- Khi migrate coordinator, làm sao chứng minh thứ tự quyền mới nối tiếp quyền cũ?

Không chỉ xem TTL của lock key; hãy xem **vòng đời của command đang bay trong mạng, broker, retry queue và workflow**.

## 22. Split-brain và network partition

Split-brain xảy ra khi hai bên cùng hoạt động như owner hợp lệ do hệ thống điều phối không thống nhất về quyền.

~~~text
Region A                 Region B
Coordinator A            Coordinator B
   |                         |
Grant epoch=100          Grant epoch=100
   |                         |
Worker A                 Worker B
   |                         |
             Storage
~~~

Nếu hai coordinator độc lập cấp cùng epoch 100, sink không thể phân biệt bằng fencing. Điều kiện quan trọng:

- Một nguồn thẩm quyền logic cho thứ tự epoch.
- Atomic grant và dữ liệu durable phù hợp.
- Quorum/consensus khi thiết kế yêu cầu safety dưới partition.
- Không đọc replica stale để cấp quyền.
- Không tự khởi động counter mới sau failover/restore.
- Quy tắc fail-closed khi không thể xác nhận quyền.
- Kiểm tra authority ở cả đường ghi dữ liệu lẫn admin/batch paths.

Không có hệ thống distributed lock nào nên được tuyên bố tuyệt đối an toàn trong mọi fault model mà không nêu giả định. Đổi lấy availability, hệ thống có thể phải ngừng cấp quyền mới khi mất quorum.

## 23. Thundering herd và fairness

Khi lease hết hạn, nhiều contender cùng xin quyền có thể gây:

- Thundering herd: hàng trăm worker wake cùng lúc.
- Hot key: một resource bị tranh chấp liên tục.
- Lock convoy: holder chậm khiến cả hàng đợi chờ.
- Starvation: một worker không bao giờ acquire thành công.
- Coordinator saturation do renew/poll dày đặc.
- Livelock khi mọi worker retry đồng nhịp.

Giải pháp:

- Backoff có jitter.
- Watch/notification thay polling nếu hệ thống hỗ trợ.
- Giới hạn số contender và concurrency.
- Chia theo tenant/shard nếu invariant cho phép.
- Short critical sections.
- Đặt deadline cho acquire attempts.
- Quan sát lock_wait_duration, success rate và số lần retries.
- Chọn fairness policy nếu nghiệp vụ yêu cầu.

Không nên giảm TTL đến mức làm quá tải coordinator chỉ để trông như “failover nhanh hơn”.

## 24. Quan sát và cảnh báo

| Metric | Mục đích |
|---|---|
| lock_acquire_success/failure | Theo dõi khả năng cấp quyền |
| lock_wait_duration p95/p99 | Đánh giá contention |
| lease_renew_failure | Phát hiện mất quyền hoặc network lỗi |
| lease_expired_count | Theo dõi holder không renew kịp |
| lease_remaining_at_commit | Nguy cơ commit sát expiry |
| coordinator_unavailable_duration | Availability của authority |
| fencing_stale_rejected_count | Số write cũ đã bị chặn |
| stale_write_accepted_incidents | Vi phạm safety nghiêm trọng |
| epoch_reuse/regression | Phát hiện token giảm hoặc trùng |
| in_flight_work_after_loss | Zombie tasks vẫn chạy |
| job_takeover_duration | Thời gian phục hồi sau holder chết |
| business_duplicate_count | Kiểm chứng idempotency |
| DB lock_wait/deadlocks | Tác động của row locks |
| hot_resource_keys | Tìm resource bị tranh chấp lớn |
| external_unknown_outcomes | Side effect cần đối soát |

Các tên là ví dụ instrumentation nội bộ. Trong trace/log nên nối **resourceKey, owner/session ID, epoch, operationId, coordinator revision, write result và trace ID** với quyền truy cập hợp lệ. Không dùng raw customer ID, secret hoặc resource key có PII làm metric labels cardinality cao.

Cần phân biệt **stale write bị từ chối** (cơ chế phòng vệ hoạt động) với **stale write được chấp nhận** (sự cố an toàn).

## 25. Ma trận kiểm thử

| Kịch bản | Cách dựng | Kỳ vọng |
|---|---|---|
| Hai worker acquire đồng thời | Barrier trước acquire | Chỉ một grant hợp lệ theo authority |
| Holder crash | Kill A sau acquire | Lease hết, B tiếp nhận |
| Pause dài hơn TTL | Pause A, B acquire và ghi | A không ghi đè trạng thái B |
| Unlock trễ | A release sau khi B nắm quyền | Lock B không bị xóa |
| Renew trễ | A renew sau expiry | Renew bị từ chối |
| Renew response mất | Chặn response | Worker xử lý UNKNOWN bảo thủ |
| Coordinator restart | Restart sau grant | Epoch không giảm/reuse |
| Coordinator failover | Mô phỏng primary failover | Không cấp hai grant vi phạm contract |
| Clock skew | Dịch clock test | Quan sát giới hạn, tránh worker tự quyết |
| Reordered writes | Token 42 đến trước 41 | 41 bị từ chối sau 42 theo max-seen rule |
| Grant mới chưa ghi | B acquire 42, A gửi 41 trước B ghi | Đánh giá strict current-epoch check |
| Duplicate operation | Gửi cùng operationId hai lần | Chỉ một business effect |
| Hai epoch cùng operation | Retry sau takeover | Business unique constraint chặn lặp |
| Worker lease lost | Chặn renew giữa job | Dừng việc mới, checkpoint/recovery đúng |
| DB commit rồi crash trước ACK | Redelivery message | Inbox/idempotency chặn duplicate |
| External API timeout | Provider commit nhưng mất response | Đối soát, không gửi operation ID mới |
| Bypass writer | Admin trực tiếp UPDATE | Quyền/enforcement chặn hoặc audit |
| Multi-resource locks | A/B acquire đảo thứ tự | Timeout/backoff, không deadlock vô hạn |
| High contention | Nhiều contender trên một key | Backoff, không overload authority |

Không chạy fault injection nguy hiểm trên production nếu không có kế hoạch bảo vệ. Với hệ thống chứa dữ liệu quan trọng, kiểm thử cả coordinator và **sink enforcement**, không chỉ hàm acquire thành công.

## 26. Bài tập thực hành

### Bài 1: stale worker

Lease TTL là 12 giây:

~~~text
t=0   A acquire epoch=7
t=4   A pause trong 20 giây
t=12  Lease A hết
t=13  B acquire epoch=8
t=15  B ghi result token=8
t=24  A thức dậy, gửi ghi token=7
~~~

Hãy giải thích:

1. Coordinator đã cấp hai lease hợp lệ cùng lúc chưa?
2. Nếu Storage không kiểm token, điều gì có thể sai?
3. Nếu Storage đã lưu maxToken=8, request token=7 phải ra sao?
4. Nếu A release Redis key bằng DEL không kiểm owner thì rủi ro gì?
5. Nếu A gửi request **sau t=13 nhưng trước write đầu của B**, một max-seen-token check có chắc từ chối không?
6. Cần thiết kế bổ sung nào để có strict current owner authorization?

### Bài 2: Redis vs database

Một công ty dùng Redis SET NX PX để chặn hai cron cùng chạy, nhưng kết quả ghi vào PostgreSQL. Hãy:

- Viết Lua compare-and-delete.
- Đề xuất cách cấp fencing epoch phù hợp và không reset.
- Giải thích tại sao owner UUID không phải fencing epoch.
- Thiết kế điều kiện ghi phía database.
- Nêu failure modes nếu Redis primary mất lock chưa replicated.
- Đề xuất phương án chỉ dùng PostgreSQL row lock/CAS thay distributed lock.
- So sánh chi phí mạng, isolation, vận hành và recovery.

### Bài 3: job dài

Có tám replica cùng chạy daily export cho nhiều tenant; mỗi job mất tám phút. Thiết kế:

1. Resource key và jobRunId.
2. TTL và renewal theo số liệu.
3. Checkpoint và takeover từ worker mới.
4. Fencing cho manifest/object output.
5. Idempotency khi upload/export và gửi notification.
6. Hành vi khi renew timeout.
7. Ba metrics và hai điều kiện dừng.
8. Cách tránh mỗi tenant bị chặn bởi global lock không cần thiết.

### Bài 4: tìm lỗi

Pseudocode:

~~~java
if (redis.setNx("lock", "locked", 15000)) {
    try {
        paymentProvider.charge(customer, amount);
    } finally {
        redis.del("lock");
    }
}
~~~

Hãy tìm ít nhất sáu vấn đề: thiếu owner identity, release nhầm, không fencing, provider không tham gia transaction, charge có thể trùng sau timeout, không có operation ID, không đối soát, và Redis failover có thể làm mất trạng thái lock.

### Bài 5: bảo vệ write bằng transaction

Thiết kế transaction PostgreSQL kiểm tra resource_leases với SELECT FOR UPDATE, xác minh owner/epoch/expiry, rồi cập nhật report_results có business version guard và commit. Giải thích vì sao một lần GET lease ngoài transaction rồi UPDATE không điều kiện không đủ.

## 27. Mẫu hợp đồng lease/fencing

~~~markdown
# Distributed Lease Contract: <resource>

## Phạm vi
- Resource và business invariant:
- Vì sao không dùng local transaction/CAS:
- Những side effects cần bảo vệ:
- Tenant/shard/job key:

## Coordinator
- Công nghệ và deployment:
- Failure model và consensus/replication:
- Atomic acquire semantics:
- Owner/session identity:
- Cơ chế cấp fencing epoch:
- Durability sau failover/restore:
- Current owner lookup consistency:

## Lease
- TTL và renew interval:
- Hành vi khi renew UNKNOWN:
- Quy tắc conditional release:
- Local cancellation:
- Backoff và contention policy:

## Sink
- Database/service/object store:
- Kiểm max-seen hay current epoch:
- Atomic enforcement ở đâu:
- Cửa sổ stale write có thể còn:
- Business CAS/idempotency:
- Bypass writer và phân quyền:

## Recovery
- Checkpoint bền vững:
- Job operationId:
- Quy trình tiếp nhận bởi owner mới:
- Unknown external outcomes:
- Đối soát sau crash:
- Owner, incident runbook:

## Validation
- Test pause, network, failover:
- Test delayed/reordered writes:
- Metrics và alert:
- Ngưỡng guardrail:
- Ngày xem lại:
~~~

## 28. Checklist trước production

- [ ] Có invariant thật cần quyền xử lý độc quyền.
- [ ] Đã cân nhắc UNIQUE, CAS/version, local DB transaction và idempotency trước.
- [ ] Resource key đúng độ hạt và ổn định.
- [ ] Acquire atomic với nguồn quyền tin cậy.
- [ ] Owner ID riêng cho mỗi lần cấp lease.
- [ ] Renew/release kiểm đúng owner và epoch.
- [ ] Lease TTL có căn cứ đo tải/GC/network, không chọn tùy ý.
- [ ] Worker dừng việc mới khi mất hoặc không chắc về lease.
- [ ] Đã xử lý pause vượt TTL, zombie worker và network partition.
- [ ] Fencing token tăng đơn điệu theo lần acquire thành công.
- [ ] Epoch không reset khi restart, restore hoặc resource recreate.
- [ ] Sink thực thi token tại bước commit.
- [ ] Đã phân biệt max-token-seen với strict current-epoch authorization.
- [ ] Không có bypass write path không được kiểm soát.
- [ ] Các command có idempotency/operation ID.
- [ ] Invariant nghiệp vụ vẫn được bảo vệ tại nơi sở hữu dữ liệu.
- [ ] External APIs có status lookup hoặc reconciliation.
- [ ] Job dài có checkpoint và takeover policy.
- [ ] Đã test lease expiry, renew timeout, release trễ và reordered write.
- [ ] Đã test coordinator failover và DB/object storage failover.
- [ ] Có metric, trace và runbook cho stale writer/split-brain.
- [ ] Có owner chịu trách nhiệm review protocol và thay đổi TTL.

## 29. Ghi nhớ

**Distributed lock** phối hợp quyền giữa nhiều process. **Lease** cho phép quyền tự hết khi holder chết, giúp hệ thống còn tiến triển; nhưng không buộc worker cũ dừng ngay. Một worker bị pause có thể thức dậy sau khi đã mất quyền và gửi lệnh đến tài nguyên.

**Fencing token** là thế hệ quyền tăng đơn điệu, được truyền tới sink để từ chối lệnh thuộc thế hệ cũ. Token phải được cấp theo một thứ tự đáng tin, không giảm sau failover và được **thực thi tại nơi ghi**. Kiểm max-token-seen bảo vệ chống lệnh cũ đến sau khi sink đã biết thế hệ mới, nhưng không tự bảo đảm mọi stale write đều bị cấm ngay từ giây phút quyền mới được cấp.

Trong nghiệp vụ quan trọng, kết hợp lease/fencing với **idempotency, version/CAS, local transactions, checkpoint, quan sát và đối soát**. Mục tiêu không phải khiến worker không bao giờ chạy trùng; mục tiêu là để pause, retry hoặc chuyển quyền **không gây sai dữ liệu và tác dụng phụ không thể kiểm soát**.
