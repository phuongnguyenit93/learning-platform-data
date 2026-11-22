# Quy trình xử lý sự cố, ghi nhận thay đổi và kiểm chứng sau bảo trì trong MongoDB

## 1. Bối cảnh và mục tiêu

Một hệ thống MongoDB có thể đang hoạt động tốt trước khi bảo trì nhưng gặp lỗi sau khi nâng cấp driver, thay cấu hình TLS, rolling restart hoặc tạo index mới. Những lỗi đó không luôn xuất hiện tức thì: replica set có thể có primary khỏe nhưng một secondary tụt oplog, API có thể trả lời `ping` nhưng một query trọng yếu chậm gấp mười lần, hoặc ứng dụng Java chỉ lỗi khi pool phải tạo connection mới.

Vì vậy, công việc vận hành MongoDB không kết thúc ở thông báo **“lệnh đã chạy thành công”**. Cần có ba kỷ luật liên kết:

1. **Xử lý sự cố (incident response):** nhận biết ảnh hưởng, điều tra, giảm thiệt hại, phục hồi rồi tìm nguyên nhân gốc.
2. **Ghi nhận và kiểm soát thay đổi (change management):** biết ai thay điều gì, tại sao, khi nào, với phương án quay lui và chứng cứ phê duyệt.
3. **Kiểm chứng sau bảo trì (post-maintenance verification):** xác minh topology, dữ liệu, hiệu năng, bảo mật và chức năng ứng dụng vẫn đáp ứng các mục tiêu đã thống nhất.

Bài thuộc module **Database Engine Document MongoDB**, chương **Vận hành và nâng cấp**, với đề bài **Quy trình xử lý sự cố, ghi nhận thay đổi và kiểm chứng sau bảo trì**.

### 1.1. Kết quả học tập

Sau bài này, bạn có thể:

- Phân biệt incident, alert, problem, change và maintenance window.
- Xác định severity theo tác động người dùng, dữ liệu và RPO/RTO.
- Thiết lập vai trò incident commander, MongoDB operator, app owner, security và scribe.
- Thu thập bằng chứng MongoDB/driver trước khi can thiệp.
- Xây timeline điều tra có tách quan sát, giả thuyết và kết luận.
- Thiết kế change request có preconditions, checkpoints, blast radius và rollback.
- Áp dụng quy trình rolling maintenance an toàn cho replica set.
- Nhận biết rủi ro khác nhau của Atlas-managed và self-managed clusters.
- Kiểm tra version/FCV, replication, oplog, sharding, indexes, client connectivity và transactions sau bảo trì.
- Định nghĩa tiêu chí go/no-go và một cửa sổ theo dõi sau change.
- Ghi change log có cấu trúc, đầy đủ nguồn chứng cứ nhưng không lộ secrets.
- Viết runbook, smoke tests, bài tập và checklist thực thi.

**Nguyên tắc xuyên suốt:** Đừng coi bảo trì thành công khi MongoDB process đã khởi động. Thành công nghĩa dịch vụ thực sự phục vụ đúng dữ liệu, đúng quyền và đúng SLO, với bằng chứng kiểm tra có thể truy vết.

## 2. Những thuật ngữ cần tách rõ

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| Alert | Tín hiệu một điều kiện giám sát bị vi phạm | Secondary lag vượt 30 giây |
| Incident | Sự cố đang hoặc có khả năng ảnh hưởng dịch vụ | 30% writes timeout |
| Problem | Nguyên nhân nền có thể gây một hoặc nhiều incidents | Index/query regression lặp lại |
| Change | Thao tác có kiểm soát làm đổi hệ thống | Nâng MongoDB binary |
| Maintenance window | Khoảng thời gian đã phê duyệt để thay đổi | 01:00–03:00 UTC |
| Release | Phiên bản code/config ứng dụng | App v3.8.1 |
| Runbook | Hướng dẫn thực thi và xử lý ngoại lệ | Rolling restart replica set |
| Rollback | Quay lại trạng thái an toàn được hỗ trợ | Trả ứng dụng về release cũ |
| Forward fix | Sửa tiếp để đưa hệ thống về trạng thái mong muốn | Sửa cấu hình thiếu CA |
| Postmortem/RCA | Phân tích sau incident và biện pháp ngăn lặp | Vì sao smoke test không bắt được lỗi? |

### 2.1. Maintenance không miễn trừ incident response

Một đợt bảo trì có kế hoạch vẫn có thể trở thành incident nếu mất write availability ngoài dự kiến, mất dữ liệu hoặc vượt ngưỡng SLO. Khi đó phải chuyển sang incident mode, ghi timeline và yêu cầu phê duyệt theo severity.

### 2.2. Thay đổi không nhất thiết gây sự cố ngay

Ví dụ một index vừa bị drop không làm API lỗi khi traffic thấp. Nhưng 20 phút sau batch report chạy, disk I/O và p99 tăng mạnh. Change history cần đủ chi tiết để liên kết hai sự kiện.

## 3. Một mô hình vận hành end-to-end

~~~text
        Proposed Change                 Monitoring Alert
               |                              |
               v                              v
        Risk & Approval                 Impact Triage
               |                              |
               v                              v
      Preflight & Baseline             Incident Response
               |                              |
               +-----------+------------------+
                           |
                           v
                 Controlled Action
                           |
                           v
                 Verification Gates
                           |
              +------------+------------+
              |                         |
              v                         v
          PASS / CLOSE              FAIL / MITIGATE
              |                         |
              v                         v
       Change Log + Evidence       Rollback / Forward Fix
              |                         |
              +------------+------------+
                           |
                           v
                  Review / RCA / Actions
~~~

Không yêu cầu mọi thay đổi phải phức tạp như một nâng cấp major version. Nhưng ngay cả thao tác nhỏ cũng cần biết **có thể ảnh hưởng gì** và **xác minh thế nào**.

## 4. Đặt mục tiêu phục hồi trước khi xảy ra sự cố

### 4.1. Các mục tiêu thường dùng

- **SLI:** chỉ số đo mức phục vụ, ví dụ tỷ lệ request đọc đơn hàng thành công.
- **SLO:** mục tiêu SLI, ví dụ 99,9% request thành công trong 200 ms.
- **RPO:** mức dữ liệu có thể mất theo thời gian, ví dụ tối đa 5 phút.
- **RTO:** thời gian khôi phục tối đa có thể chấp nhận, ví dụ 1 giờ.
- **MTTD:** thời gian trung bình từ lúc lỗi xuất hiện đến khi phát hiện.
- **MTTA:** thời gian trung bình để tiếp nhận cảnh báo.
- **MTTR:** thời gian phục hồi theo định nghĩa của tổ chức.

**RPO và RTO không phải con số MongoDB tự cam kết.** Chúng là yêu cầu của hệ thống, được đáp ứng bằng topology, backup, runbook, năng lực vận hành và diễn tập.

### 4.2. Ví dụ mục tiêu theo hệ thống

| Workload | RPO ví dụ | RTO ví dụ | Điều phải kiểm chứng |
|---|---:|---:|---|
| Đặt hàng | 5 phút | 60 phút | Majority writes, PIT restore, đối soát |
| API nội dung | 30 phút | 2 giờ | Read availability, backup, cache |
| Báo cáo có thể tái tạo | 24 giờ | 24 giờ | Jobs và nguồn dữ liệu |
| Môi trường lab | Có thể làm lại | Theo nhu cầu | Automation tái tạo |

Những con số chỉ minh họa; chính sách phải theo chủ sở hữu nghiệp vụ.

## 5. Phân loại mức độ sự cố theo ảnh hưởng

| Severity | Dấu hiệu điển hình | Hành động |
|---|---|---|
| SEV-1 / Critical | Mất ghi diện rộng, nguy cơ mất dữ liệu, cluster không có majority, data corruption | Page ngay, incident commander, tập trung phục hồi |
| SEV-2 / High | Một dịch vụ quan trọng suy giảm, p99 tăng mạnh, secondary staleness ảnh hưởng người dùng | On-call ứng dụng + DBA, mitigation có thời hạn |
| SEV-3 / Medium | Một workload ít người dùng chậm, capacity có rủi ro trong vài ngày | Ticket/điều tra có owner |
| SEV-4 / Low | Cảnh báo mang tính phòng ngừa, chưa tác động SLO | Theo dõi và xử lý trong kế hoạch |

### 5.1. Severity phải dựa vào impact

Một đợt primary election vài giây có thể không gây ảnh hưởng nếu driver retry thành công. Ngược lại, một TLS misconfiguration có thể làm 100% new connections thất bại dù CPU rất thấp.

### 5.2. Nâng mức khi có tín hiệu an toàn dữ liệu

Không chỉ xem lỗi 5xx: dấu hiệu missing writes, backup không thể giải mã, dữ liệu bị sửa ngoài ý muốn hoặc thao tác đổi quyền trái phép cần escalation ngay theo security/data incident policy.

## 6. Ai làm gì trong một incident MongoDB?

| Vai trò | Trách nhiệm |
|---|---|
| Incident Commander (IC) | Quyết định ưu tiên, phạm vi, phê duyệt phương án, điều phối |
| MongoDB/Platform Operator | Kiểm tra topology, storage, replication, config và chạy thao tác được duyệt |
| Application Owner | Xác định user impact, driver/connection pools, rollback app |
| Security | Tham gia khi có authentication/TLS/credential/data exposure |
| Communications | Cập nhật stakeholders và người dùng theo policy |
| Scribe | Ghi timeline, giả thuyết, evidence, quyết định, kết quả |
| Change Owner | Đảm bảo thay đổi có preflight, gates và rollback |

Nhân sự có thể kiêm nhiệm ở sự cố nhỏ; không được bỏ qua việc xác định **ai có quyền ra quyết định**.

### 6.1. Incident bridge và single source of truth

Mọi quyết định quan trọng nên được ghi vào một incident record có timestamp UTC. Tránh nhiều nhóm tự thay config/scale/restart cùng lúc mà không biết nhau.

### 6.2. Break-glass

Quyền cao như `root`, Atlas Project Owner, KMS Decrypt hoặc quyền restore production chỉ nên dùng theo cơ chế khẩn cấp có ghi nhận, MFA/JIT/approval và thu hồi sau sự cố.

## 7. Quy trình xử lý sự cố: 8 bước

### Bước 1 — Detect

Nguồn tín hiệu:

- API SLO và error-budget burn.
- Atlas Alerts/Monitoring.
- Logs của `mongod`/`mongos`.
- Java driver command failures và pool checkout timeouts.
- Replica set elections và lag.
- Backup/PIT freshness.
- User reports.

### Bước 2 — Acknowledge

On-call tiếp nhận, xác nhận người phụ trách và mở incident nếu mức ảnh hưởng phù hợp. Không để alert quan trọng chỉ có email mà không có ACK/escalation.

### Bước 3 — Assess impact

Ghi:

- Bắt đầu lúc nào?
- Endpoint/service/tenants/regions nào bị ảnh hưởng?
- Bao nhiêu requests/transactions fail?
- Read, write hay cả hai?
- Có data loss/incorrect data không?
- Có yêu cầu dừng phát hành, khóa ghi hoặc chuyển traffic không?

### Bước 4 — Preserve evidence

Thu metrics/logs/traces, config versions, topology, query plans và change history **trước khi restart** khi có thể và an toàn. Không để việc thu bằng chứng trì hoãn mitigation cần thiết để bảo vệ dữ liệu.

### Bước 5 — Hypothesize

Lập danh sách giả thuyết có thứ tự và phép kiểm chứng, thay vì áp mọi runbook cùng lúc.

### Bước 6 — Mitigate

Giảm tác động: tạm ngừng batch, rollback release, giảm concurrency, scale hoặc cô lập node lỗi theo runbook. Tránh những thay đổi dễ làm mất dữ liệu hay quorum.

### Bước 7 — Verify recovery

Xác nhận SLO, error rate, correctness, primary/secondary health, lag và traffic trở lại bình thường trong khoảng quan sát tối thiểu.

### Bước 8 — Review

Viết postmortem, cập nhật runbook, ngưỡng cảnh báo, tests, rollback procedure và ownership.

## 8. Điều tra bằng giả thuyết có thể bác bỏ

Ví dụ incident: API latency tăng sau deployment.

| Giả thuyết | Dự đoán nếu đúng | Kiểm tra |
|---|---|---|
| Query shape mới bỏ index | Docs examined tăng, plan khác | `explain` và Query Profiler |
| Pool thiếu connections | Pool wait tăng, command time có thể bình thường | Driver metrics |
| Replica lag | Secondary lag và majority commit chậm | `rs.status()`, lag metrics |
| Disk I/O chậm | Read/write latency và iowait tăng | OS/Atlas metrics |
| TLS/secret rotation lỗi | New connection/auth errors tăng | Driver/TLS logs và change history |

Một kết luận tốt nêu rõ **observed facts**, **hypothesis**, **test evidence** và **remaining uncertainty**. Tương quan thời gian với deployment không tự chứng minh causal relationship.

### 8.1. Tránh “chữa theo trực giác”

Không tăng pool vì thấy timeout khi chưa biết bottleneck; pool lớn hơn có thể làm server bão hòa hơn. Không tạo index mới chỉ vì planner dùng `COLLSCAN` trên một collection rất nhỏ. Không thay writeConcern để che majority write latency nếu chưa hiểu durability trade-off.

## 9. Timeline sự cố bằng UTC

Một ví dụ:

~~~text
2026-11-14T10:02:00Z  orders-api v3.2 deploy 10%
2026-11-14T10:04:10Z  API p95 tăng từ 85ms lên 600ms
2026-11-14T10:05:30Z  docsExamined/returned tăng 100 lần
2026-11-14T10:06:00Z  Alert SEV-2 kích hoạt
2026-11-14T10:07:15Z  On-call ACK, mở incident
2026-11-14T10:10:20Z  Explain cho thấy query plan không phù hợp
2026-11-14T10:12:00Z  Rollback canary release
2026-11-14T10:15:00Z  API p95 và error rate trở lại baseline
2026-11-14T10:35:00Z  Bắt đầu monitoring hậu sự cố
~~~

Đồng hồ và timezone phải nhất quán. Có thể hiển thị giờ Việt Nam cho người vận hành nhưng lưu timestamp gốc UTC/offset rõ ràng.

### 9.1. Không chỉ ghi lệnh

Change/incident record nên ghi **tại sao chọn hành động** và kết quả sau đó:

~~~text
Decision: rollback canary v3.2
Reason: query plan regression có bằng chứng, rollback rủi ro thấp
Approved by: IC + App Owner
Observed outcome: p95 giảm, không xuất hiện lỗi ghi dữ liệu
~~~

## 10. Thu thập dữ liệu MongoDB ít tác động

Các lệnh dưới đây là ví dụ read-only/diagnostic. Chúng vẫn cần privileges phù hợp và có thể có overhead; tránh gọi dồn dập trên cluster đang quá tải.

### 10.1. Kiểm tra kết nối cơ bản

~~~javascript
db.adminCommand({ ping: 1 });
~~~

`ping` trả lời thành công **không chứng minh** nghiệp vụ đọc/ghi hoặc majority writes đang khỏe.

### 10.2. Xem phiên bản và build

~~~javascript
db.version();

db.adminCommand({ buildInfo: 1 });
~~~

Thông tin version/build phải được ghi theo từng member/process nếu bảo trì rolling; một kết nối qua load balancer/`mongos` không chứng minh toàn deployment đã đồng phiên bản.

### 10.3. Lấy role của node

~~~javascript
db.hello();
~~~

Output trên mongod có thể có `isWritablePrimary`, `secondary`, `setName` và `hosts`. Với `mongos`, response có các dấu hiệu router như `msg:"isdbgrid"`. Trường output phụ thuộc topology/version.

### 10.4. Thống kê server

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson({
  host: s.host,
  uptime: s.uptime,
  connections: s.connections,
  opcounters: s.opcounters,
  network: s.network
});
~~~

Counters tích lũy phải chuyển thành rates và xét reset sau restart; không so số tuyệt đối từ hai nodes có uptime khác nhau.

### 10.5. Replica status

~~~javascript
rs.status();
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
~~~

Những helpers dùng trong ngữ cảnh replica set phù hợp và cần quyền monitoring. Chúng không thay việc giám sát qua thời gian.

## 11. Thu thập thông tin replication cẩn thận

Các trường cần quan sát:

- Primary có khỏe không?
- Các members expected đều có trạng thái mong muốn?
- Secondary lag có giảm sau khi bảo trì?
- Optime của secondaries có tiến lên?
- Oplog window có đủ cho thời gian downtime?
- Có heartbeat failures, elections không theo lịch?
- Majority read/write có phục hồi?

~~~text
PRIMARY
   |
   +--> SECONDARY A: lag 0.8s
   |
   +--> SECONDARY B: lag 48s
~~~

Cluster không thể được gọi là “hoàn toàn khỏe” chỉ vì một secondary đang bắt kịp tốt; secondary B cần được giải thích.

### 11.1. Oplog window và thời gian maintenance

Nếu oplog window khoảng 8 giờ nhưng một secondary có thể ngừng 12 giờ, secondary có rủi ro không bắt kịp và phải initial sync. Rút ngắn maintenance hoặc điều chỉnh sizing/backup plan trước khi thực hiện.

### 11.2. Không dùng replication lag ngưỡng chung cho mọi workload

Secondary phục vụ user reads có yêu cầu freshness khác secondary dành cho báo cáo. Severity phải theo user impact, không chỉ con số giây.

## 12. Query troubleshooting bằng explain

Ví dụ trong database lab:

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "OPEN"
}).sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Quan sát:

- Winning plan và `IXSCAN`/`COLLSCAN`.
- `totalDocsExamined`.
- `totalKeysExamined`.
- `nReturned`.
- `executionTimeMillis`.
- Có blocking sort không.
- Index name và bounds.

### 12.1. Query có IXSCAN vẫn có thể chậm

Nếu quét một triệu index entries chỉ để trả 10 documents, truy vấn chưa hiệu quả dù planner đã dùng index.

### 12.2. COLLSCAN không luôn là lỗi

Với collection vài documents, collection scan có thể hợp lý. Đánh giá trong ngữ cảnh dataset lớn/representative.

### 12.3. Explain không thay production p99

Một lần explain trên một connection không đại diện đầy đủ concurrency, cache misses, driver pool wait hay workload biến động.

## 13. Current operations và profiler

### 13.1. Xem operations đang chạy

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      localOps: true
    }
  },
  {
    $match: {
      active: true,
      secs_running: { $gte: 5 }
    }
  },
  {
    $project: {
      opid: 1,
      ns: 1,
      desc: 1,
      secs_running: 1,
      waitingForLock: 1
    }
  },
  { $limit: 20 }
]);
~~~

`$currentOp` phải đứng đầu pipeline; xem hoạt động của mọi users có thể yêu cầu action `inprog`. Output chỉ là snapshot operations còn chạy.

### 13.2. Database profiler

Profiler trên `mongod` có các mức:

| Level | Ý nghĩa |
|---|---|
| 0 | Không ghi profiler operations |
| 1 | Ghi slow operations theo ngưỡng/filter |
| 2 | Ghi mọi operations |

Không bật level 2 thường trực trên production: có performance overhead và nguy cơ thu metadata/query values nhạy cảm.

Trên **lab self-managed**, nếu được phép:

~~~javascript
use operations_lab

db.getProfilingStatus();

db.setProfilingLevel(1, {
  slowms: 200,
  sampleRate: 0.1
});
~~~

Ghi lại cấu hình trước, kiểm tra docs đúng version, rồi khôi phục sau cửa sổ điều tra:

~~~javascript
db.setProfilingLevel(0);
~~~

Chú ý `slowms`/`sampleRate` có thể có ảnh hưởng process-wide với diagnostic logs; `setProfilingLevel(0)` không tự khôi phục mọi giá trị trước đó.

### 13.3. Không log query chứa PII

Trong incident, chia sẻ query shape, plan summary, duration và trace ID; không đưa toàn bộ predicates chứa email, tokens hoặc customer data lên ticket.

## 14. Phân biệt lỗi ứng dụng, driver và MongoDB server

Các nguồn latency:

~~~text
API request
   |
   v
Application queue
   |
   v
MongoClient connection checkout
   |
   v
Server selection / TLS / network
   |
   v
MongoDB command execution
   |
   v
Response deserialize / business logic
~~~

Nếu MongoDB command duration bình thường nhưng API p99 cao, kiểm tra pool checkout, DNS, TLS, network, retries và downstream dependencies trước khi thay MongoDB index.

### 14.1. Các lỗi Java Driver đáng phân loại

- Connection checkout timeout.
- Server selection timeout.
- Socket/network timeout.
- TLS certificate/hostname failure.
- AuthenticationFailed (code 18).
- Authorization failure (đã xác thực nhưng thiếu role).
- NotPrimary/server topology change.
- WriteConcern error.
- Transaction retry/TransientTransactionError labels.
- Application-level validation/duplicate key.

Những lỗi này **không có một remediation chung**. Chẳng hạn `AuthenticationFailed` không phải chứng cứ phải reset password ngay; có thể là sai `authSource` hoặc secret version.

## 15. Kiểm tra hoạt động sharded cluster

Trong sharded deployment phải kiểm tra:

- Các shards và config server replica set.
- `mongos` endpoints.
- Trạng thái balancer/chunk migrations nếu có tác động.
- Phân bố reads/writes per shard.
- Scatter-gather queries ngoài dự kiến.
- Độ nhất quán index trên từng shard.
- Độ trễ và lỗi của ứng dụng xuyên shards.
- Backup/restore plan phải xét global consistency.

### 15.1. Lệnh xem trạng thái có thể rất dài

~~~javascript
sh.status();
~~~

Chạy từ `mongos` trong ngữ cảnh sharded cluster với quyền thích hợp, không coi output của một router là đã kiểm chứng mọi member.

### 15.2. Hot shard và average

~~~text
Shard A: CPU 95%, p99 1.6s
Shard B: CPU 25%, p99 70ms
Cluster average CPU: 60%
~~~

Đánh giá theo từng shard. Không vội đổi shard key/reshard trong incident khi chưa đo đúng nguồn bất cân bằng.

## 16. Chẩn đoán storage và WiredTiger

Các tín hiệu:

- Disk free bytes và time-to-full.
- Disk read/write latency và IOPS.
- Memory pressure/swap.
- WiredTiger cache, eviction, dirty bytes.
- Checkpoint/journal stalls.
- Host error logs.
- Index build hoặc backup làm tăng I/O.

Ví dụ các fields tùy phiên bản:

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });
const cache = s.wiredTiger && s.wiredTiger.cache;

if (cache) {
  printjson({
    bytesInCache: cache["bytes currently in the cache"],
    maxBytes: cache["maximum bytes configured"],
    dirtyBytes: cache["tracked dirty bytes in the cache"]
  });
}
~~~

Một cache usage cao không đủ kết luận thiếu RAM: cần đối chiếu eviction/disk latency và user-facing SLO.

### 16.1. Những điều không làm

Không xóa trực tiếp WiredTiger data files hoặc journal nhằm “giải phóng dung lượng”. Không reboot nhiều members cùng lúc chỉ vì disk I/O tăng mà chưa xem majority/quorum.

## 17. Phân biệt planned maintenance và emergency change

| Hạng thay đổi | Đặc trưng | Kiểm soát |
|---|---|---|
| Standard/pre-approved | Lặp lại, ít rủi ro, đã có runbook và kiểm thử | Change record ngắn + evidence |
| Normal | Nâng version, index changes, TLS rotation, scale | Risk review, approval, preflight, rollback |
| Emergency | Sửa lỗi bảo mật/availability đang gây impact | Incident commander approval, ghi quyết định và review sau |

Emergency change không có nghĩa không ghi chép hoặc miễn trừ hậu kiểm. Có thể rút ngắn trình tự phê duyệt nhưng vẫn phải lưu risk, outcome và accountability.

### 17.1. Một maintenance có nhiều change units

Ví dụ nâng MongoDB rồi nâng Java Driver cùng lúc làm khó xác định nguyên nhân khi xảy ra lỗi. Nếu có thể, tách các changes đủ nhỏ và có checkpoint giữa chúng.

## 18. Một Change Request (CR) cần có những trường nào?

| Trường | Ví dụ |
|---|---|
| Change ID | CHG-2026-0142 |
| Title | Rolling MongoDB patch upgrade |
| Owner / executor | Platform team |
| Business owner | Orders service |
| Environment / topology | Production, replica set 3 nodes |
| Objective | Sửa security bug |
| Scope | mongod binaries, từng member |
| Before state | Version/build, FCV, config hash |
| Desired after state | Version mục tiêu được hỗ trợ |
| Impact/risk | Có election, kết nối ngắn bị gián đoạn |
| RPO/RTO/SLO | Theo service policy |
| Prerequisites | Backup, healthy majority, oplog headroom |
| Approval | DBA + service owner |
| Window | UTC start/end |
| Steps | Runbook versioned |
| Validation gates | Replication, app smoke, SLO |
| Rollback/forward fix | Phương án hỗ trợ theo phiên bản |
| Communications | Trước/trong/sau |
| Evidence links | Metrics, logs, execution record |

### 18.1. Scope và blast radius

Một index trên một collection có thể ảnh hưởng writes và storage. Một CA rotation có thể làm toàn bộ app clients mất kết nối. Một thay đổi shard topology có thể ảnh hưởng nhiều tenants.

Phải ghi rõ **đơn vị nhỏ nhất có thể dừng/quay lui** và các phụ thuộc cần kiểm tra.

## 19. Mẫu change record dạng YAML

Đây là **schema quản trị minh họa**, không phải file cấu hình trực tiếp của MongoDB.

~~~yaml
changeId: CHG-2026-0142
title: Rolling MongoDB patch upgrade
environment: production
deployment: orders-rs0
changeType: normal
risk: medium
owner: platform-oncall
approvers:
  - database-lead
  - orders-service-owner
window:
  startUtc: 2026-11-15T01:00:00Z
  endUtc: 2026-11-15T03:00:00Z
before:
  mongodbVersion: recorded-per-member
  featureCompatibilityVersion: recorded
  topology: 1-primary-2-secondaries
  backupStatus: verified
planned:
  stepsRef: runbook-mongodb-rolling-upgrade-v3
  rollbackRef: runbook-mongodb-recovery-v2
gates:
  - majority-healthy
  - secondary-caught-up
  - service-smoke-pass
  - error-budget-within-policy
results:
  status: pending
  evidenceRef: null
~~~

Các values về version/FCV thực tế phải được ghi từ deployment; không điền “đã kiểm tra” trước khi đo.

### 19.1. Change log không chứa secrets

Không ghi MongoDB URI có password, PEM private key, KMS key material hoặc plaintext database backup vào change record.

### 19.2. Khả năng tìm kiếm lịch sử

Nên liên kết change ID với:

- Deployment/release pipeline run.
- Source commit/infra plan.
- Incident ID nếu có.
- Baseline metrics.
- Approval.
- Postflight report.
- Rollback decision.
- Postmortem.

## 20. Preflight trước mọi maintenance có tác động

Preflight là điều kiện **go/no-go**, không phải phần điền hình thức.

1. Xác nhận scope, owner, approval và runbook version.
2. Xác nhận maintenance window/communication.
3. Kiểm tra SLO, current alerts và incident đang mở.
4. Kiểm tra topology và majority quorum.
5. Xem replication lag, oplog window, member health.
6. Xác minh backups/snapshots/PIT restore windows.
7. Kiểm tra disk/memory/CPU headroom.
8. Kiểm tra indexes/migrations jobs hiện tại.
9. Xác định active transactions và batch jobs.
10. Kiểm tra compatibility binary, driver, FCV, app.
11. Đảm bảo secrets/TLS/KMS còn hợp lệ trong thời gian maintenance.
12. Xác định rollback và ai có quyền thực hiện.
13. Thu baseline để so trước/sau.
14. Đặt alert routing và status communication phù hợp.

### 20.1. Dừng nếu một secondary đã không khỏe

Nếu replica set 3 members đang có một secondary unavailable, restart primary/secondary thứ hai có thể làm mất majority. Không bắt đầu rolling maintenance cho đến khi topology đạt điều kiện theo runbook.

### 20.2. Backup chỉ có giá trị khi khôi phục được

“Last backup succeeded” không thay backup integrity/restore readiness. Với changes rủi ro cao, cần recovery point hợp lệ, key giải mã và quy trình restore được thử.

### 20.3. Thời gian oplog phải đủ

Nếu secondary cần offline một khoảng dài hơn oplog window, node có thể phải initial sync. Đây là rủi ro đáng kể về RTO.

## 21. Baseline trước bảo trì: đo cái gì?

Tạo một baseline có timestamp UTC và môi trường:

| Tín hiệu | Trước change (ví dụ) | Mức chấp nhận sau change |
|---|---:|---|
| API read p95 | 70 ms | Không vượt SLO |
| API error rate | 0.05% | Không vượt error budget |
| DB command p95 | 20 ms | Không regression quá mức phê duyệt |
| Primary status | Healthy | Đúng một PRIMARY khi topology yêu cầu |
| Secondary lag max | 1.5 s | Quay về baseline trong recovery window |
| Disk free | 300 GB | Không giảm ngoài dự đoán |
| Available connections | Dư headroom | Không có rejected connection spikes |
| Backup point | Verified gần đây | Recovery point vẫn hợp lệ |

Các con số **minh họa**, không phải SLO MongoDB mặc định.

### 21.1. Cần lưu loại phiên bản và cấu hình

Trước thay đổi, ghi:

- MongoDB binary versions per member.
- `featureCompatibilityVersion` (FCV), khi deployment hỗ trợ/được phép đọc.
- Driver versions và release ứng dụng.
- Config revision/hash.
- TLS certificate expiry/CA trust.
- Feature flags/cluster parameters liên quan.
- Index specifications quan trọng.
- Shard/replica topology.

### 21.2. Chọn khoảng baseline đủ đại diện

Một 5 phút im ắng trước bảo trì lúc 02:00 không đại diện peak traffic 09:00. Nếu có thể, so với lịch sử cùng giờ/ngày và dự kiến workload sau change.

## 22. Ghi bằng chứng trạng thái trước thay đổi bằng mongosh

### 22.1. Ping/hello/build

~~~javascript
printjson(db.adminCommand({ ping: 1 }));

printjson(db.hello());

printjson(db.adminCommand({ buildInfo: 1 }));
~~~

Không đưa nguyên output nhạy cảm lên ticket công khai. Giới hạn những fields cần thiết.

### 22.2. Feature compatibility version

Trên phiên bản và môi trường cho phép:

~~~javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

FCV không luôn tự đổi theo binary version. Việc thay FCV có compatibility và rollback implications; không tự chạy `setFeatureCompatibilityVersion` như bước “cho đủ” ngoài quy trình nâng cấp chính thức.

### 22.3. Replica set status

~~~javascript
rs.status();
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
~~~

Nên có bản tóm tắt health theo từng member, không chỉ ảnh chụp phần đầu output.

### 22.4. Thống kê tài nguyên

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson({
  host: s.host,
  uptimeSeconds: s.uptime,
  connections: s.connections,
  opcounters: s.opcounters,
  network: s.network
});
~~~

Các counters tích lũy reset sau process restart; postflight phải so **rates** và normalized metrics, không so tổng counters như số tuyệt đối.

## 23. Rolling maintenance trên replica set: tư duy an toàn

Ví dụ topology:

~~~text
       PRIMARY A
          |
     +----+----+
     |         |
SECONDARY B  SECONDARY C
~~~

Đối với những công việc cho phép rolling restart, nguyên tắc thường là:

1. Xác minh cả ba members khỏe và backup có sẵn.
2. Chọn một secondary.
3. Bảo trì/restart **một member**.
4. Chờ member quay lại healthy SECONDARY và bắt kịp.
5. Kiểm tra replication lag, logs, resource usage.
6. Chỉ khi gate đạt mới chuyển secondary tiếp theo.
7. Sau khi secondaries đã được xử lý, lên kế hoạch thay primary/stepdown.
8. Xác nhận election/majority và kết nối ứng dụng.
9. Bảo trì primary cũ, đợi nó trở lại SECONDARY.
10. Kiểm tra topology, data và SLO toàn hệ thống.

Đây là **mô hình quy trình**, không phải hướng dẫn thay thế runbook theo từng MongoDB version/OS/clusterAuth/driver.

### 23.1. Vì sao không restart đồng thời?

Replica set phải có majority để duy trì primary/write availability. Restart nhiều voting members có thể gây mất quorum và outage.

### 23.2. Primary stepdown tạo thay đổi client-visible

Có thể có khoảng ngắn không có primary, in-flight operations fail hoặc phải retry. Application driver cần topology discovery và retry configuration phù hợp; không hứa zero interruption tuyệt đối.

### 23.3. Không bỏ qua election events

Ghi thời điểm election, new primary, driver errors và recovery. Nếu election lặp, dừng rollout và điều tra.

### 23.4. Arbiter không giữ dữ liệu

Replica set có arbiter cần hiểu số voting members và khả năng failover; arbiter không thay secondary data copy hoặc backup.

## 24. MongoDB version upgrade: binary và FCV khác nhau

Trong một lần nâng cấp MongoDB, cần phân biệt:

- **Binary version:** phiên bản mongod/mongos đang chạy.
- **Feature Compatibility Version (FCV):** điều khiển tập tính năng/định dạng tương thích theo release.
- **Driver compatibility:** ứng dụng Java/Node/Python có hỗ trợ server mới không.
- **Application schema/index compatibility:** query shapes, aggregation và index behavior có đổi không.

### 24.1. Thứ tự upgrade theo tài liệu phiên bản

MongoDB yêu cầu quy trình nâng cấp cụ thể, có thể đòi nâng theo từng major version, kiểm tra FCV trước, nâng binary theo topology rồi mới hoàn tất bước FCV khi đáp ứng điều kiện.

**Không** đưa một lệnh cụ thể như `setFeatureCompatibilityVersion("x.y")` vào runbook chung mà chưa đọc tài liệu upgrade chính thức của *source version → target version*.

### 24.2. FCV có ý nghĩa đối với rollback

Khi bật FCV mới, một số tính năng/định dạng có thể làm việc quay về binary cũ không còn đơn giản. Cần xác nhận downgrade support, backup restore plan và rollback cutoff trước khi đổi FCV.

### 24.3. Version skew trong quá trình rolling

Có giai đoạn cluster có các members chạy khác binary versions theo quy trình được hỗ trợ. Không coi mixed versions tạm thời là lỗi nếu upgrade guide cho phép, nhưng phải có cửa sổ chuyển tiếp và gate về trạng thái nhất quán.

### 24.4. Không thay MongoDB và driver đồng thời nếu có thể tách

Đổi server, driver, auth mechanism, TLS certificates và query indexes trong cùng một change tăng số giả thuyết khi incident xảy ra. Nên tách thành các changes có checkpoint riêng khi chính sách cho phép.

## 25. Atlas-managed maintenance khác self-managed

Với MongoDB Atlas, platform quản lý một phần lớn quy trình patch/upgrade, failover và hạ tầng. Người vận hành ứng dụng vẫn cần:

- Đọc maintenance/upgrade notifications.
- Chọn/configure maintenance window phù hợp khi được hỗ trợ.
- Kiểm tra cluster tier/version constraints.
- Chuẩn bị driver retry/transaction behavior.
- Đo SLO trước/sau.
- Xem project activity/event logs.
- Xác minh backups/PIT.
- Kiểm tra API/worker functionality sau change.

### 25.1. Không tự chạy thao tác self-managed trên Atlas

Không giả định có quyền restart `mongod` trực tiếp hoặc thay OS service khi dùng Atlas managed cluster. Sử dụng Atlas UI/CLI/API, các workflow được hỗ trợ và MongoDB Support khi cần.

### 25.2. Sự cố xảy ra trong Atlas maintenance

Dùng Atlas Events/Metrics/Alerts để đối chiếu timeline, phối hợp Support nếu cần, nhưng vẫn phải ghi incident record nội bộ và xác định ảnh hưởng tới người dùng.

### 25.3. Atlas alerts không thay postflight

Một cluster hiện status xanh trên UI không chứng minh một nghiệp vụ thanh toán dùng majority writes thành công hoặc một Java app vẫn trust CA.

## 26. Self-managed maintenance: những phụ thuộc phải kiểm tra

Ngoài mongod version và topology, kiểm tra:

- OS packages/service manager.
- Disk filesystem/volume health.
- DNS/network firewall.
- TLS CA, certificate validity và clusterAuth.
- Shared keyfile/internal X.509.
- KMS/KMIP nếu có encryption at rest.
- Monitoring agents/exporters.
- Backup/restore tools versions.
- System limits và file descriptors.
- Clock synchronization.
- Host resource limits/cgroups.
- Persistent volumes và mount paths.

### 26.1. Không thay nhiều loại secret cùng lúc khi không cần

Certificate rotation và keyfile rotation có trình tự riêng. Nếu vừa thay binary vừa thay CA/internal authentication, khó phân biệt lỗi handshake do đâu.

### 26.2. Bảo vệ cấu hình và secret

Change log có thể lưu config hash/diff đã redacted, nhưng không đưa private key, passwords hay KMS key material vào artifact công khai.

## 27. Verification gates: điều kiện qua từng bước

**Gate** là điều kiện bắt buộc trước khi sang bước tiếp theo.

| Gate | Mục tiêu | Nếu không đạt |
|---|---|---|
| G0 Preflight | Health, backup, approvals | Hoãn change |
| G1 Single member | Node trở lại healthy, lag ổn | Dừng rollout |
| G2 Majority | Primary/quorum ổn, app writes phục hồi | Incident/rollback |
| G3 Feature/FCV | Phiên bản và FCV hợp lệ | Không bật tính năng mới |
| G4 Data | Counts/invariants/transactions ổn | Chặn tiếp nhận traffic rộng |
| G5 Security | Auth/TLS/roles hoạt động | Mitigate và điều tra |
| G6 Application | Smoke tests và API SLO pass | Rollback/forward fix |
| G7 Observation | Không có regression kéo dài | Tiếp tục theo dõi, không đóng change |

### 27.1. No-go là trạng thái hợp lệ

Một secondary lag không trở lại baseline, hoặc pool new connections liên tục fail, là lý do dừng. Không cố hoàn thành maintenance window bằng mọi giá.

### 27.2. Ai xác nhận?

Platform/DBA xác nhận node/topology; application owner xác nhận smoke/SLO; security xác nhận auth/TLS nếu có thay đổi; change owner thu evidence và đóng change.

## 28. Postflight lớp 1: cluster topology

Đối với replica set:

~~~javascript
rs.status();
db.hello();
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
~~~

Kiểm tra:

- Đúng số members expected.
- Đúng một PRIMARY trong view healthy khi phù hợp topology.
- Mọi secondaries intended đều SECONDARY, bắt kịp trong giới hạn.
- Không member nào stuck RECOVERING/STARTUP2 không theo kế hoạch.
- Không mất votes/majority.
- Không heartbeat errors kéo dài.
- Election count/timeline hợp lý với thao tác đã thực hiện.
- Oplog window còn đủ.
- Không có initial sync ngoài dự kiến.

### 28.1. Không chỉ kiểm tra ngay sau restart

Một secondary có thể vào SECONDARY trước khi lag hoàn toàn giảm. Quan sát theo một khoảng để phát hiện lag tăng trở lại khi traffic bình thường.

### 28.2. Một câu lệnh không thay kiểm tra per-member

Kết nối qua một router hoặc primary không có nghĩa đã đọc đủ health của mọi node. Collector/monitoring phải có đủ per-member metrics.

## 29. Postflight lớp 2: phiên bản và cấu hình

- MongoDB binary/build version per member.
- FCV đúng giai đoạn đã được duyệt.
- Driver version và app release.
- Storage engine và required settings.
- Authentication/authorization còn bật.
- TLS chain/hostname validation pass.
- Backup/exporter agents vẫn hoạt động.
- Index definitions cần thiết còn nguyên.
- Configuration diff khớp với thay đổi được duyệt.
- Không có config drift ngoài phạm vi.

### 29.1. Binary upgrade thành công nhưng FCV chưa đổi?

Đây có thể là trạng thái **chủ đích** trước gate cuối. Đừng tự đổi FCV vì thấy không khớp binary. Theo upgrade plan của phiên bản và quyết định rollback.

### 29.2. Đừng dựa vào một output buildInfo

Trong rolling upgrade, từng member có thể khác version. Ghi version theo node, không chỉ `db.version()` qua một connection ngẫu nhiên.

## 30. Postflight lớp 3: dữ liệu và tính đúng đắn

Một cluster chạy khỏe về mặt topology nhưng dữ liệu có thể sai sau migration, restore hoặc thay index/schema.

Kiểm tra theo yêu cầu nghiệp vụ:

1. Các databases/collections expected còn tồn tại.
2. Counts/volumes không giảm bất thường.
3. Sample documents có khóa và schema đúng.
4. Referential/business invariants hợp lệ.
5. Các indexes cần thiết còn sẵn sàng.
6. Collation/unique constraints đúng.
7. Transactions/readConcern/writeConcern hoạt động theo thiết kế.
8. Change stream resume behavior nếu ứng dụng dùng.
9. TTL indexes và background jobs không xóa dữ liệu ngoài dự kiến.
10. Multi-tenant ACL vẫn đúng.

### 30.1. Count và sample chưa đủ để chứng minh data integrity

`countDocuments()` trên mẫu hoặc so total count không phát hiện mọi lỗi. Cần consistency/invariant checks phù hợp domain, nhất là sau restore/migration dữ liệu.

### 30.2. Không chạy kiểm tra nặng giữa sự cố

Một query full collection scan để đối chiếu mọi documents có thể làm cluster đang yếu tệ hơn. Dùng bounded samples, async validation hoặc restore target riêng khi thích hợp.

### 30.3. Dữ liệu đã xóa có thể tái xuất hiện sau restore

Nếu restore backup cũ, phải xét các business updates/deletions từ sau recovery point và có reconciliation plan trước khi mở lại traffic.

## 31. Postflight lớp 4: ứng dụng và driver

Một smoke test ít tác động nên bao gồm:

- Tạo **new MongoClient/new TLS connection** thành công.
- Authenticate với đúng principal và authSource.
- Đọc một document hợp lệ trong test namespace/tenant.
- Ghi một document test/transaction theo cơ chế cho phép.
- Đọc lại, xác nhận invariants.
- Dọn test data an toàn nếu policy cho phép.
- Query nghiệp vụ quan trọng dùng index dự kiến.
- Change streams/worker/ETL hoạt động lại.
- Không có connection checkout/server selection errors.
- Metrics p95/p99 và 5xx về baseline.

### 31.1. Ping chỉ là một bước

~~~javascript
db.adminCommand({ ping: 1 });
~~~

`ping` thành công không bảo đảm app có role, query index, transactions, majority write hoặc TLS trust trên mọi client.

### 31.2. Read-only smoke test bằng mongosh

~~~javascript
const appDb = db.getSiblingDB("operations_lab");

printjson(appDb.orders.findOne(
  { _id: "smoke-reference" },
  { _id: 1, status: 1, updatedAt: 1 }
));
~~~

Nếu document không tồn tại thì phép thử chưa có mẫu tốt; cần fixture/test data được thiết kế trước. Không dùng arbitrary customer document để thử trên production.

### 31.3. Write test phải có idempotency

Một smoke-write có thể tạo tài liệu với ID riêng và TTL/cleanup policy, nhưng cần tránh dữ liệu giả chảy vào báo cáo, billing hoặc change streams của nghiệp vụ. Nên dùng namespace test riêng với policy rõ.

## 32. Postflight lớp 5: hiệu năng, tài nguyên và SLO

So với baseline trước change:

| Chỉ số | Thực hành |
|---|---|
| API p95/p99 | So theo endpoint và khung giờ |
| Error rate | So với SLO/error budget |
| DB command duration | Xem percentiles và query shapes |
| Docs/keys examined | Phát hiện query plan regression |
| Connections | Current, available, rejected nếu hỗ trợ |
| Disk | Free space, latency, IOPS |
| WiredTiger | Cache/eviction/checkpoints |
| Replication | Lag, oplog, flow control |
| Host | CPU, memory, network |
| Backup | Freshness và agents vẫn hoạt động |

### 32.1. Counter reset sau restart

`opcounters`, `network.bytesIn` và `connections.totalCreated` có thể reset khi node restart. Không lấy giá trị absolute sau trừ trước để kết luận traffic giảm hàng triệu operations.

### 32.2. SLO thời điểm vắng khách không phản ánh peak

Maintenance lúc 02:00 có thể kết thúc khi traffic thấp. Cần một **observation window** đủ lâu, đôi khi kéo dài đến đợt peak đầu tiên theo policy, trước khi kết luận không có regression.

### 32.3. So query shapes thay vì full query values

Dùng query shapes từ Atlas Query Profiler/slow logs và sampled explain. Không tạo metric label theo email hoặc user ID; tăng cardinality và lộ dữ liệu.

## 33. Postflight lớp 6: an toàn và bảo mật

Kiểm tra:

- SCRAM/X.509/OIDC authentication vẫn hoạt động.
- Users/roles không thay ngoài phạm vi.
- TLS CA/SAN/expiry hợp lệ trên **new connections**.
- Internal member authentication không lỗi.
- KMS/at-rest encryption có quyền giải mã cần thiết.
- Audit logging/monitoring vẫn gửi dữ liệu.
- API keys/secrets vừa rotate đã được consumers nhận.
- Network ACL/private endpoints đúng.
- Backup keys còn truy cập để restore historical backups.
- Không có authentication failures tăng bất thường.
- Incident artifacts không chứa password/PEM.

### 33.1. Đổi TLS certificate cần thử kết nối mới

Một TLS session đã mở trước rotation có thể còn hoạt động. Chỉ kiểm tra pool cũ không chứng minh certificate mới được client trust.

### 33.2. Không tắt xác minh TLS

Không bật `tlsInsecure`, `tlsAllowInvalidHostnames` hoặc bypass hostname verification như cách xử lý lâu dài khi cert sai. Sửa CA/trust/SAN và triển khai lại theo runbook.

## 34. Postflight lớp 7: backup và khả năng phục hồi

Đặc biệt quan trọng sau upgrade, storage migration, backup agent change hoặc KMS rotation.

Câu hỏi:

- Lịch backup vẫn chạy?
- Snapshot/PIT mới có xuất hiện và đạt policy?
- Retention có bị giảm?
- Restore target/permissions còn khả dụng?
- KMS key cũ còn cần cho historical backups?
- Oplog window sau bảo trì có đủ?
- Bài restore drill gần nhất có thành công?
- Encryption/backup agents có lỗi không?

**Không coi backup verified chỉ vì object tồn tại.** Cần restore test theo lịch và kiểm tra khả năng decrypt.

## 35. Tiêu chí để tuyên bố bảo trì thành công

Một mẫu quyết định:

~~~text
[PASS] Topology đạt trạng thái mong muốn
[PASS] Binary/config/FCV khớp plan
[PASS] Secondary lag giảm về ngưỡng
[PASS] Queries trọng yếu hoạt động
[PASS] New driver/TLS connections thành công
[PASS] Không có auth/authorization regression
[PASS] SLO và error rate ổn
[PASS] Disk/cache/queue không suy giảm ngoài dự tính
[PASS] Backup/monitoring tiếp tục hoạt động
[PASS] Evidence và change log đủ
~~~

Chỉ đổi trạng thái change thành **COMPLETED** khi các gates đã được xác nhận hoặc có exception đã phê duyệt rõ. Nếu một gate chưa được kiểm tra, ghi `PENDING` chứ không điền `PASS` giả định.

### 35.1. Kết thúc maintenance khác đóng change record

Maintenance có thể kết thúc lúc 03:00, nhưng change chỉ đóng sau 30–60 phút hoặc qua peak monitoring theo chính sách. Khi chưa có đủ dữ kiện, giữ trạng thái `MONITORING`.

### 35.2. Partial completion

Nếu một secondary chưa upgrade nhưng cluster vẫn phục vụ tốt, phải ghi partial state và kế hoạch còn lại, không báo “mọi nodes đã upgrade”.

## 36. Rollback và forward-fix decision

| Điều kiện | Ưu tiên có thể phù hợp |
|---|---|
| App release mới gây regression rõ | Rollback app |
| Config/cert mới lỗi nhưng cũ còn an toàn | Khôi phục config/cert theo runbook |
| Upgrade binary vừa đổi, FCV chưa đổi | Xem downgrade support theo version |
| FCV đã đổi và dùng tính năng mới | Có thể cần forward fix/restore; không tự downgrade |
| Migration dữ liệu đã commit không thể đảo | Forward fix hoặc restore/reconciliation |
| Secret cũ bị compromise | Không rollback về secret cũ |
| Replica set thiếu majority | Phục hồi quorum trước, theo runbook khẩn cấp |

### 36.1. Rollback phải được kiểm thử trước

“Có backup” không phải rollback plan đủ. Cần biết RTO, data replay/reconcile, thao tác thay đổi endpoint và recovery permissions.

### 36.2. Đừng rollback tự động khi không còn tương thích

MongoDB major upgrade có thể có giới hạn downgrade theo binary/FCV và feature usage. Luôn kiểm tra **tài liệu chính thức cho đúng cặp source/target versions**.

### 36.3. Stop-the-line conditions

Dừng rollout ngay khi:

- Mất majority hoặc primary unavailable kéo dài.
- Dấu hiệu data corruption/missing writes.
- Authentication/TLS errors lan rộng.
- Secondary không bắt kịp và oplog window co nguy hiểm.
- Latency/error budget vi phạm rõ.
- Backup/recovery path không còn an toàn.
- Có change ngoài scope hoặc operator không xác định.

## 37. Nhật ký thao tác (execution log)

Một execution log cần ghi **ý định, người thực hiện, kết quả**, không chỉ console transcript.

Ví dụ:

| UTC | Actor | Hành động | Expected | Observed | Gate |
|---|---|---|---|---|---|
| 01:00 | DBA | Preflight | 3 members healthy | PASS | G0 |
| 01:10 | DBA | Restart secondary B | B về SECONDARY | PASS sau 4 phút | G1 |
| 01:20 | DBA | Restart secondary C | C về SECONDARY | PASS | G1 |
| 01:35 | DBA | Planned stepdown | New PRIMARY | PASS, retries nhẹ | G2 |
| 01:50 | App | Smoke read/write | Thành công | PASS | G6 |
| 02:15 | Platform | SLO compare | Trong baseline | PASS | G7 |

Dữ liệu này là ví dụ, không phải timeline bắt buộc của một deployment.

### 37.1. Thêm reference tới bằng chứng

Nếu metrics/console output lưu ở hệ thống khác, ghi link/reference có access control. Không paste full diagnostic logs chứa PII.

### 37.2. Người phê duyệt và người thao tác

Tách actor/approver khi thay đổi rủi ro cao. Automation nên có service identity riêng và signed pipeline run metadata.

## 38. Mẫu báo cáo sau bảo trì

~~~markdown
# Maintenance Report — CHG-2026-0142

- Deployment: orders-rs0 / production
- Scope: rolling MongoDB patch upgrade
- Planned window: 01:00–03:00 UTC
- Actual window: 01:08–02:20 UTC
- Owner: Platform
- Approval: CHG-2026-0142

## Before
- Members healthy: 3/3
- Primary: one expected
- Backup: verified
- Application SLO: within target
- MongoDB/FCV versions: recorded in evidence

## Actions
- Secondary B and C upgraded individually
- Planned primary stepdown
- Previous primary upgraded
- Indexes and configuration checked

## After
- Healthy members: 3/3
- Secondary lag: within baseline
- Primary stable: yes
- New TLS/MongoClient connection: pass
- App read/write smoke test: pass
- SLO/error rate: pass
- Backup agent: operational

## Deviations
- None / or list with incident ID

## Decision
- Status: MONITORING / COMPLETED
- Evidence: internal controlled links
- Approved by: DB lead + service owner
~~~

Đây là mẫu báo cáo, không phải output công cụ. Mọi dấu `pass` trong báo cáo thật phải được chứng minh.

## 39. Ghi nhận rủi ro và exceptions

Không phải mọi hệ thống đều đạt toàn bộ gates trong cửa sổ maintenance. Nếu chấp nhận ngoại lệ, ghi:

- Gate không đạt là gì?
- Lý do và phạm vi ảnh hưởng.
- Mức rủi ro còn lại.
- Người chấp nhận rủi ro.
- Hạn chót xử lý.
- Điều kiện giám sát bổ sung.
- Phương án nếu tình hình xấu đi.

Ví dụ:

~~~text
Exception:
Secondary C lag 12s, trên baseline 2s,
nhưng đang giảm đều và không phục vụ user reads.
Owner: DBA
Review in: 30 minutes
Escalate if lag increases or oplog headroom shrinks.
~~~

Không biến exception thành “PASS” để đóng thay đổi cho tiện.

## 40. Change history và nguồn gốc quyết định

Một hệ thống audit tốt liên kết:

~~~text
Change Request
     |
     +--> Approval
     +--> Runbook version
     +--> Source diff / IaC plan
     +--> Preflight evidence
     +--> Execution timeline
     +--> Postflight verification
     +--> Incident reference (nếu có)
     +--> Follow-up actions
~~~

### 40.1. Infrastructure as Code và config drift

Nếu dùng Terraform/Ansible/Kubernetes operators, version control chỉ là một phần. Kiểm tra **state thực tế** sau deploy và drift so với config định nghĩa.

### 40.2. Không lưu secrets vào diff

Config diffs phải redact SCRAM passwords, TLS private keys, KMS key material, API tokens và MongoDB URIs có credentials.

### 40.3. Rollout automation cần idempotency

Nếu pipeline retry một bước, nó không được thực hiện lại thao tác không idempotent gây ảnh hưởng như xóa dữ liệu, thay FCV hay thay primary mà không kiểm tra trạng thái trước.

## 41. Khi nào một maintenance thành incident?

Ví dụ:

~~~text
01:00  Planned rolling restart bắt đầu
01:15  Bảo trì secondary đầu tiên thành công
01:25  Bảo trì node tiếp theo
01:26  App error rate tăng đến 20%
01:27  Majority writes bị ảnh hưởng
~~~

Tại 01:26:

1. **Dừng rollout**.
2. **Mở incident**, nâng severity theo impact.
3. **Ghi nhận timeline** và người phụ trách.
4. **Giảm tác động**, theo runbook/approval.
5. **Không** tiếp tục các bước để “hoàn thành đúng lịch”.
6. Sau recovery, đánh giá rollback/forward fix.
7. Gắn incident ID vào change record.

Maintenance window không cho phép tự động bỏ qua tiêu chí availability.

## 42. Case study A — Query regression sau schema/index change

### Triệu chứng

- API p95 tăng từ 80 ms lên 800 ms.
- `docsExamined / nReturned` tăng mạnh.
- Primary/quorum vẫn bình thường.
- Incident xuất hiện sau release query mới.

### Điều tra

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "OPEN"
}).sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Kiểm tra query shape, index specifications, plan summary và deployment diff.

### Mitigation

Rollback query/release nếu chứng cứ phù hợp, hoặc áp index change được review nếu không thể rollback. Kiểm tra write amplification và disk headroom trước khi tạo index production.

### Hậu kiểm

Bổ sung representative data/performance tests và change checklist bắt buộc query plan review cho endpoints trọng yếu.

## 43. Case study B — Replica set election kéo dài sau maintenance

### Triệu chứng

- App server selection timeouts tăng.
- Primary unavailable lâu hơn dự kiến.
- Một secondary không healthy.
- Node vừa restart và có heartbeat errors.

### Điều tra

~~~javascript
rs.status();
db.hello();
~~~

Đối chiếu host logs, network, TLS, quorum, member state, FCV/binary compatibility và planned stepdown timeline.

### Mitigation

Dừng rollout, ưu tiên khôi phục member/quorum theo runbook; không restart node cuối còn healthy.

### Hậu kiểm

Thêm gate secondary-caught-up và verify member TLS trước bước đổi primary.

## 44. Case study C — TLS certificate được thay nhưng Java app lỗi

### Triệu chứng

- Existing pooled connections có thể còn chạy.
- New client/TLS handshakes thất bại.
- Logs có certificate chain/SAN mismatch.

### Giả thuyết

Server cert mới được ký bởi CA chưa nằm trong Java truststore, hoặc SAN không khớp hostname.

### Kiểm chứng

- Đọc issuer/SAN/validity của cert mới bằng công cụ PKI.
- Kiểm tra Java truststore/SSLContext cấu hình.
- Tạo **new connection** trên canary với TLS verification đầy đủ.
- Xem TLS handshake errors và auth outcomes.

### Mitigation

Khôi phục trust/cert theo runbook được phê duyệt; không bật `tlsInsecure`. Nếu CA rollover, dùng giai đoạn trust overlap khi phù hợp.

### Hậu kiểm

Bổ sung new-connection smoke test và inventory mọi clients.

## 45. Case study D — Disk pressure sau index build

### Triệu chứng

- Disk free giảm nhanh.
- Disk latency/p99 tăng.
- Index build vừa khởi chạy.
- Secondary replication lag tăng.

### Điều tra

- Disk growth và time-to-full.
- Current operations/index build state.
- WiredTiger cache/eviction.
- Host storage limits.
- Write throughput và replication.
- Change timeline.

### Mitigation

Dừng rollout tiếp theo, giới hạn batch tải, scale storage hoặc xử lý index build theo runbook. Không xóa file dữ liệu/journal trực tiếp.

### Hậu kiểm

Thêm capacity forecast và index build resource estimates vào preflight.

## 46. Case study E — Restore hoàn tất nhưng nghiệp vụ sai

### Triệu chứng

- Restore job báo completed.
- Cluster có primary và API kết nối được.
- Một số orders thiếu line items hoặc payment reconciliation lỗi.

### Bài học

Process/cluster health không chứng minh business correctness. Recovery cần:

- Mốc RPO cụ thể.
- Collections và indexes expected.
- Invariant tests cross-collection.
- Reapply các writes hợp lệ sau recovery point nếu cần.
- Kiểm tra dữ liệu đã xóa theo privacy policy.
- Thẩm định trước khi mở traffic rộng.

Không tuyên bố sự cố khép lại chỉ từ `ping` và số lượng documents tổng.

## 47. Java Sync Driver: ví dụ smoke test và instrumentation

### 47.1. Ping và read-only smoke test

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class MongoPostMaintenanceSmoke {
    public static boolean run(MongoClient client) {
        MongoDatabase admin = client.getDatabase("admin");
        Document ping = admin.runCommand(new Document("ping", 1));

        Number ok = (Number) ping.get("ok");
        if (ok == null || ok.doubleValue() != 1.0) {
            return false;
        }

        MongoCollection<Document> collection =
            client.getDatabase("operations_lab")
                  .getCollection("smokeReference");

        Document item = collection.find(
            new Document("_id", "known-readonly-fixture")
        ).first();

        return item != null && "ACTIVE".equals(item.getString("status"));
    }
}
~~~

Chỉ thành công khi test fixture đã được tạo từ trước và application credential đủ quyền. Không dùng production customer data ngẫu nhiên làm smoke fixture.

### 47.2. Cần test MongoClient mới

Một MongoClient tồn tại từ trước maintenance có thể giữ pooled connections. Tạo một client mới bằng credentials/TLS chính thức để verify new handshake, server selection và authentication.

### 47.3. Lắng nghe command failures

~~~java
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;

import java.util.concurrent.TimeUnit;

class SafeMongoListener implements CommandListener {
    @Override
    public void commandStarted(CommandStartedEvent event) {
        // Không log event.getCommand(): có thể chứa PII.
        System.out.println("Started " + event.getCommandName());
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        System.out.println(
            event.getCommandName() + " succeeded in " +
            event.getElapsedTime(TimeUnit.MILLISECONDS) + "ms"
        );
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        System.out.println(
            event.getCommandName() + " failed in " +
            event.getElapsedTime(TimeUnit.MILLISECONDS) + "ms"
        );
    }
}
~~~

Production nên chuyển sang metrics/tracing với cardinality/sampling controls, không in raw commands/URI/exception data có thể chứa secrets.

### 47.4. Read-only smoke không thay write/transaction test

Nếu hệ thống cần transactions và majority writeConcern, tạo **test case nghiệp vụ được kiểm soát** ở environment/namespace phù hợp. Không tự động ghi dữ liệu giả vào collection thanh toán production.

## 48. Diễn tập: mẫu dữ liệu lab

Các ví dụ chỉ dùng **MongoDB lab**:

~~~javascript
use operations_lab

db.orders.insertMany([
  {
    _id: "lab-001",
    tenantId: "tenant-A",
    status: "OPEN",
    amount: 100,
    createdAt: ISODate("2026-11-01T08:00:00Z")
  },
  {
    _id: "lab-002",
    tenantId: "tenant-A",
    status: "CLOSED",
    amount: 200,
    createdAt: ISODate("2026-11-02T08:00:00Z")
  },
  {
    _id: "lab-003",
    tenantId: "tenant-B",
    status: "OPEN",
    amount: 300,
    createdAt: ISODate("2026-11-03T08:00:00Z")
  }
]);

db.smokeReference.insertOne({
  _id: "known-readonly-fixture",
  status: "ACTIVE",
  updatedAt: new Date()
});
~~~

Các IDs cố định khiến chạy lại `insertMany` trên cùng collection có thể gây duplicate key error. Dùng collection sạch hoặc chuyển sang upsert trong automation lab có idempotency.

### 48.1. Query trước/sau index

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "OPEN"
}).sort({
  createdAt: -1
}).explain("executionStats");
~~~

Tạo index **trong lab**:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);
~~~

Chạy explain lần nữa. Với chỉ ba documents, planner có thể vẫn chọn collection scan; không kết luận index có/không hiệu quả production từ lab bé này.

## 49. Mẫu checklist preflight cho rolling maintenance

- [ ] Change ID, owner, approvals và window có sẵn.
- [ ] Runbook phù hợp MongoDB version và topology.
- [ ] Application SLO và baseline đã lưu.
- [ ] Backup/PIT restore point đã xác minh.
- [ ] Replica set có majority và members khỏe.
- [ ] Secondary lag và oplog window đủ headroom.
- [ ] Disk/CPU/cache không đang bão hòa bất thường.
- [ ] Không có incident P1/P2 chưa được xử lý.
- [ ] Driver version và retry behavior tương thích.
- [ ] TLS/KMS/cluster auth dependencies hợp lệ.
- [ ] Monitoring/exporter/alerts hoạt động.
- [ ] Đã xác định stop-the-line conditions.
- [ ] Có rollback plan đúng phiên bản.
- [ ] Người phê duyệt và operator đã xác nhận liên lạc.

## 50. Checklist postflight và đóng change

### Topology và phiên bản

- [ ] MongoDB binary version per member đúng plan.
- [ ] FCV đúng giai đoạn được phê duyệt.
- [ ] Đúng số PRIMARY/voting members theo topology.
- [ ] Secondaries bắt kịp, lag ổn định.
- [ ] Oplog window đạt yêu cầu.
- [ ] Không heartbeat/election lỗi kéo dài.
- [ ] Sharded members/config servers/mongos bình thường.

### Dữ liệu và ứng dụng

- [ ] Expected namespaces/indexes còn đầy đủ.
- [ ] Test fixture đọc được.
- [ ] Write/transaction smoke test có kiểm soát thành công.
- [ ] Business invariants quan trọng pass.
- [ ] Driver tạo new TLS connection và auth thành công.
- [ ] Change streams/jobs/ETL phục hồi.
- [ ] Multi-tenant ACL và roles không thay bất thường.

### Hiệu năng và an toàn

- [ ] API p95/p99/error rate nằm trong SLO.
- [ ] DB query shapes không regression nghiêm trọng.
- [ ] Connection pool/driver retries bình thường.
- [ ] CPU/cache/disk/queue không bất thường.
- [ ] Backup/PIT/monitoring hoạt động.
- [ ] TLS/secret/KMS policy còn hợp lệ.
- [ ] Không có alert critical chưa giải quyết.
- [ ] Observation window hoàn tất hoặc exception có owner.

### Hồ sơ thay đổi

- [ ] Có actual start/end timestamps UTC.
- [ ] Actions, results và operators ghi đầy đủ.
- [ ] Preflight/postflight evidence lưu với quyền phù hợp.
- [ ] Deviations và incidents liên kết vào change.
- [ ] Rollback/forward-fix decision được ghi.
- [ ] Có phê duyệt đóng change.
- [ ] Follow-ups có owner và deadline.

## 51. Bài tập thực hành và tình huống

Chỉ chạy các lệnh có tác động trên **lab hoặc môi trường được phê duyệt**. Không thực hiện restart/stepdown/restore/FCV changes trên production chỉ để làm bài.

### Bài 1 — Phân biệt khái niệm

Phân biệt alert, incident, problem, change, maintenance và RCA. Một alert secondary lag luôn là incident P1 không?

### Bài 2 — Impact và severity

API có 20% writes timeout trong 15 phút. Hãy xác định thông tin phải thu trước khi đặt severity.

### Bài 3 — SLO/RPO/RTO

Nếu RPO 5 phút, RTO 1 giờ, backup gần nhất cách sự cố 24 giờ thì hệ thống có đáp ứng policy không?

### Bài 4 — Incident roles

Phân công Incident Commander, DBA, app owner và scribe trong một sự cố mất primary.

### Bài 5 — Timeline

Ghi timeline UTC gồm deploy, phát alert, ACK, mitigation, recovery verification.

### Bài 6 — Facts vs hypothesis

“p99 tăng sau deploy” là fact hay root cause? Cần bằng chứng gì để kết luận release gây query regression?

### Bài 7 — MongoDB diagnostics

Chạy `db.hello()`, `db.version()` và `serverStatus` trên lab. Mỗi lệnh trả lời câu hỏi khác nhau thế nào?

### Bài 8 — Counter reset

Vì sao không lấy `opcounters` tổng sau restart trừ tổng trước để suy ra throughput?

### Bài 9 — Replication health

Một secondary lag 45 giây, primary khỏe. Có đủ điều kiện rolling upgrade bước tiếp chưa? Cần xem gì?

### Bài 10 — Oplog window

Một secondary cần offline 12 giờ nhưng oplog window chỉ 6 giờ. Rủi ro và lựa chọn chuẩn bị?

### Bài 11 — Query explain

Vì sao có IXSCAN vẫn chưa chứng minh query được tối ưu? Nêu ba trường phải xem trong executionStats.

### Bài 12 — CurrentOp

Dùng `$currentOp` tìm operations chạy quá 5 giây. Vì sao `killOp` không nên là hành động mặc định?

### Bài 13 — Atlas vs self-managed

Những phần nào của maintenance do Atlas quản lý và ứng dụng vẫn phải tự xác minh?

### Bài 14 — FCV

Phân biệt binary version và FCV. Vì sao đổi FCV có thể ảnh hưởng rollback/downgrade?

### Bài 15 — Majority quorum

Replica set 3 voting members đang có một secondary down. Có nên restart một member khác để nâng cấp ngay không?

### Bài 16 — Rolling maintenance

Hãy vẽ flow bảo trì secondaries trước, primary sau; nêu gates giữa từng member.

### Bài 17 — Change Request

Viết các trường tối thiểu của change ticket cho rolling patch upgrade, gồm rollback, impact và evidence.

### Bài 18 — Preflight backup

Tại sao “backup job succeeded” chưa đủ bằng chứng khả năng phục hồi?

### Bài 19 — Maintenance trở thành incident

Trong lúc patch upgrade, write errors tăng 30%. Các bước đầu tiên và người có quyền quyết định?

### Bài 20 — Postflight topology

Nêu điều kiện để xác nhận replica set khỏe sau planned election.

### Bài 21 — Postflight data

Vì sao `ping` và document count đúng chưa bảo đảm business consistency?

### Bài 22 — New TLS connections

Existing app pools chạy tốt nhưng new client không kết nối được. Cần kiểm tra lớp nào?

### Bài 23 — Driver retry

Khi MongoDB bị quá tải, vì sao retries không giới hạn có thể gây cascade?

### Bài 24 — Sharded cluster

Vì sao phải so per-shard metrics và kiểm tra `mongos`/config servers sau maintenance?

### Bài 25 — SLO verification

Bảo trì lúc 02:00, traffic bình thường rất thấp. Có nên đóng change ngay hay cần observation window qua peak?

### Bài 26 — Rollback

App release mới lỗi, có thể rollback. Nhưng MongoDB FCV vừa nâng và đã dùng feature mới; có thể tùy tiện downgrade không?

### Bài 27 — Secrets

Tại sao không ghi MongoDB URI/private key vào change record?

### Bài 28 — Authorization

Sau upgrade, app authenticate thành công nhưng write bị từ chối. Phân biệt authentication và authorization.

### Bài 29 — Unexpected disk growth

Sau index build, disk tăng nhanh và lag tăng. Lập bước điều tra/mitigation an toàn.

### Bài 30 — Restore correctness

Restore job completed nhưng thiếu order line items. Những business invariants nào cần xác minh?

### Bài 31 — Postmortem

Lập RCA có trigger, contributing factors, impact, detection, mitigation, recovery và action items có owner.

### Bài 32 — Change gate decision

Gate topology PASS, application smoke PASS, nhưng backup agent fail và một secondary lag tăng. Change có được đóng COMPLETED không? Giải thích.

### Bài 33 — Nhật ký thao tác

Viết một execution log bốn dòng có timestamp, actor, action, expected, observed và gate.

### Bài 34 — Diễn tập tổng hợp

Thiết kế runbook upgrade MongoDB cho hệ thống đặt hàng có:

- Replica set ba members.
- Java API và workers.
- SCRAM/TLS.
- Majority writes.
- Backup/PIT.
- SLO p95.
- Change request và approvals.
- Gate cho từng member.
- New-client smoke test.
- Rollback/forward fix và incident escalation.
- Postflight report.

## 52. Tổng kết

Quy trình vận hành MongoDB an toàn không chỉ là chạy đúng lệnh:

1. **Xử lý sự cố:** đánh giá tác động người dùng/dữ liệu, thu bằng chứng, đặt giả thuyết có thể bác bỏ, mitigate an toàn, rồi xác minh recovery và viết RCA.
2. **Ghi nhận thay đổi:** change request phải ghi mục tiêu, scope, version/config trước/sau, approvals, blast radius, runbook, rollback, execution timeline và evidence.
3. **Bảo trì theo checkpoints:** replica set rolling maintenance phải giữ majority, đợi từng member khỏe, xử lý election có kiểm soát và lưu ý oplog window.
4. **Nâng cấp đúng phiên bản:** binary, FCV, driver và database features có compatibility constraints; không downgrade/đổi FCV tự phát.
5. **Kiểm chứng đa lớp:** topology, data invariants, roles/TLS, new MongoClient connections, API SLO, query plans, backup và monitoring đều cần PASS hoặc exception rõ.
6. **Đóng vòng cải tiến:** sau incident/change, review ngưỡng alerts, smoke tests, runbooks và actions có owner/deadline.

Một đợt bảo trì chỉ đáng gọi là **hoàn tất** khi có bằng chứng hệ thống phục vụ đúng dữ liệu, đúng quyền và đúng SLO sau khi thay đổi — không chỉ vì MongoDB process đã khởi động lại.

## Tài liệu tham khảo chính thức

- [MongoDB Manual — Upgrade Self-Managed Deployments](https://www.mongodb.com/docs/manual/release-notes/upgrade/)
- [MongoDB Manual — Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/)
- [MongoDB Manual — Replica Set Maintenance](https://www.mongodb.com/docs/manual/administration/replica-set-maintenance/)
- [MongoDB Manual — rs.status()](https://www.mongodb.com/docs/manual/reference/method/rs.status/)
- [MongoDB Manual — rs.printSecondaryReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printSecondaryReplicationInfo/)
- [MongoDB Manual — rs.printReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printReplicationInfo/)
- [MongoDB Manual — db.hello()](https://www.mongodb.com/docs/manual/reference/method/db.hello/)
- [MongoDB Manual — serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual — CurrentOp](https://www.mongodb.com/docs/manual/reference/operator/aggregation/currentOp/)
- [MongoDB Manual — Troubleshoot Replication Lag](https://www.mongodb.com/docs/manual/tutorial/troubleshoot-replica-sets/)
- [MongoDB Atlas — Configure Maintenance Windows](https://www.mongodb.com/docs/atlas/tutorial/cluster-maintenance-window/)
- [MongoDB Atlas — Alerts](https://www.mongodb.com/docs/atlas/alerts/)
- [MongoDB Atlas — Backup and Restore](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)
- [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/)
- [MongoDB Java Sync Driver — Connection Pool Configuration](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/)
