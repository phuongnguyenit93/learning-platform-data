# Thu thập bằng chứng, khoanh vùng nguyên nhân và kiểm chứng sau sửa lỗi trong MongoDB

Một sự cố MongoDB thường bắt đầu bằng biểu hiện ở ứng dụng: API chậm, timeout, tăng lỗi 5xx, dữ liệu trả về thiếu, thao tác ghi bị từ chối hoặc hệ thống mất khả năng chọn primary. Những biểu hiện này **không tự chỉ ra nguyên nhân**. Timeout có thể do truy vấn quét nhiều document, connection pool cạn, network packet loss, một lần election, I/O disk quá tải, hoặc client dùng read/write concern không phù hợp.

Nếu vội khởi động lại tiến trình, xóa index, tăng timeout hay thay cấu hình replica set trước khi thu thập bằng chứng, đội vận hành có thể làm mất dấu vết, tạo thêm lỗi và khiến lần sự cố sau khó xử lý hơn. Cách làm đáng tin cậy là **thu thập bằng chứng → xây dựng và bác bỏ giả thuyết → thay đổi có kiểm soát → kiểm chứng phục hồi → lưu bài học phòng ngừa**.

Bài học thuộc chương **Xử lý sự cố**, module **Database Engine Document MongoDB**, hướng dẫn chẩn đoán MongoDB từ nhiều tầng: ứng dụng Java, driver/connection pool, mạng, mongod/mongos, query planner/index, replica set, sharding, storage, bảo mật và tính đúng đắn của dữ liệu.

**Nguyên tắc an toàn:** Các lệnh thu thập thông tin trong bài chủ yếu mang tính đọc. Một số lệnh hoặc tùy chọn profiling có tác động lên hiệu năng hoặc có thể làm lộ dữ liệu. Không thực thi restart, killOp, stepDown, force reconfig, repair, drop/delete, thay index hay đổi cấu hình production nếu chưa có đánh giá tác động và quy trình phê duyệt. Trong sự cố, ưu tiên phục hồi dịch vụ có kiểm soát và bảo toàn dữ liệu.

## 1. Mục tiêu của bài học

Sau bài này, bạn có thể:

1. Phân biệt **triệu chứng**, **sự kiện đã quan sát**, **giả thuyết** và **nguyên nhân gốc**.
2. Mở một incident timeline có mốc thời gian thống nhất và mức tin cậy của từng bằng chứng.
3. Thu thập metrics, logs, traces và cấu hình theo thứ tự ít xâm lấn.
4. Dùng các lệnh MongoDB như `hello`, `serverStatus`, `rs.status`, `currentOp`, `explain` đúng bối cảnh.
5. Khoanh vùng vấn đề ở ứng dụng/driver, mạng, truy vấn/index, replication, sharding hoặc storage.
6. Hiểu vì sao server selection timeout không đồng nghĩa một MongoDB server đã ngừng chạy.
7. Đọc query plan và phân biệt nguyên nhân của COLLSCAN, blocking SORT, docs examined cao.
8. Xử lý bằng chứng replica set election, replication lag, write concern và stale reads.
9. Thiết kế thí nghiệm kiểm chứng giả thuyết có thể đảo ngược và ít tác động.
10. Xác nhận sau sửa lỗi bằng cả health, workload, SLO và business/data invariants.
11. Lập runbook incident, evidence ledger, rollback gates và postmortem có khả năng tái hiện.

## 2. Bốn khái niệm không được trộn lẫn

| Khái niệm | Ví dụ | Mức độ chắc chắn |
| --- | --- | --- |
| Triệu chứng | API danh sách đơn hàng p95 tăng từ 120 ms lên 3 s | Người dùng đang thấy |
| Quan sát | `totalDocsExamined` rất lớn, plan có COLLSCAN | Đo được |
| Giả thuyết | Một thay đổi filter khiến index không còn hỗ trợ query | Cần kiểm chứng |
| Nguyên nhân gốc | Release đổi predicate và loại bỏ field equality đứng đầu compound index, gây scan lớn khi traffic tăng | Được chứng minh bằng chuỗi bằng chứng |

Một biểu hiện như “CPU 95%” có thể là **hậu quả** của truy vấn scan chứ không phải nguyên nhân gốc. Một lệnh restart làm CPU giảm không chứng minh restart giải quyết được nguyên nhân.

### 2.1. Nguyên tắc tương quan khác nhân quả

Hai biểu đồ cùng tăng vào 10:05 không chứng minh sự kiện A gây ra B. Cần so sánh thời điểm, đường truyền tác động, bằng chứng độc lập và kết quả sau khi thay đổi có kiểm soát.

### 2.2. Tập trung vào điều có thể bác bỏ

Giả thuyết hữu ích dự đoán được quan sát:

- Nếu thiếu index là nguyên nhân, query plan không dùng index phù hợp và docs examined sẽ cao.
- Nếu pool bị cạn, thời gian chờ lấy connection ở client tăng dù server latency không tăng tương ứng.
- Nếu replica set đang election, logs/topology event và cửa sổ không có writable primary sẽ khớp thời điểm lỗi ghi.

Nếu dữ liệu phủ định dự đoán, cập nhật giả thuyết thay vì cố giữ kết luận ban đầu.

## 3. Mô hình sự cố theo tầng

~~~text
User / Client
      |
      v
API / Business service
      |
      v
MongoDB Java Driver
  - connection pool
  - server selection
  - retry/read preference
      |
      v
Network / TLS / DNS / Proxy
      |
      v
mongos (nếu sharded)
      |
      v
mongod / Replica set
  - elections
  - read/write execution
  - locks/tickets
  - query planner/index
      |
      v
WiredTiger / Memory / CPU / Disk
      |
      v
Data / Durability / Consistency
~~~

Không đi thẳng tới mongod chỉ vì lỗi có chữ MongoDB. API mất connection cũng có thể do DNS, firewall, secret rotation hoặc client pool.

### 3.1. Nhận diện blast radius

Hãy hỏi lỗi ảnh hưởng:

- Một endpoint hay mọi endpoint?
- Một tenant, một collection hay toàn cluster?
- Reads, writes hay cả hai?
- Một app version/pod hay mọi phiên bản?
- Một AZ/region hay tất cả?
- Một shard/replica set member hay toàn deployment?
- Chỉ peak traffic hay cả lúc ít tải?
- Chỉ sau deploy/migration hay không gắn thay đổi nào?

Phạm vi và thời điểm là hai chỉ dấu khoanh vùng rất mạnh.

## 4. Đặt mục tiêu xử lý đúng ngay từ đầu

Trước mọi thao tác thay đổi, xác định:

1. **Mức độ ảnh hưởng:** số requests lỗi, tenants/users bị ảnh hưởng, dữ liệu có nguy cơ mất/sai.
2. **Mức độ khẩn cấp:** SLO đang vi phạm? Có nguy cơ gián đoạn ghi hay data corruption?
3. **Mục tiêu ưu tiên:** giảm tác động người dùng, bảo toàn dữ liệu, khôi phục write path hay đọc báo cáo.
4. **Giới hạn hành động:** ai được duyệt failover/config/index changes?
5. **Đầu mối:** incident commander, database operator, application owner, communications owner.
6. **Mốc thời gian:** thời điểm bắt đầu, các thay đổi gần nhất, thời điểm đo phục hồi.

### 4.1. Mitigation khác root-cause fix

Giảm request rate, rollback một release hoặc chuyển traffic có thể là biện pháp giảm tác động nhanh, trong khi root cause vẫn cần phân tích. Ghi rõ **biện pháp tạm thời** và **sửa tận gốc**.

### 4.2. Không hy sinh dữ liệu để lấy green dashboard

Làm traffic giảm bằng cách tắt validation hoặc bỏ write concern mà không đánh giá durability có thể khiến metrics đẹp nhưng dữ liệu nguy hiểm hơn.

## 5. Quy trình 15 phút đầu

| Khoảng | Việc chính | Kết quả mong muốn |
| --- | --- | --- |
| 0–2 phút | Xác nhận sự cố, phân loại ảnh hưởng, phân công người phụ trách | Incident ID, severity, phạm vi |
| 2–5 phút | Chốt timeline UTC, phiên bản ứng dụng, thay đổi gần nhất | Mốc T0 và suspected changes |
| 5–10 phút | Thu app error rates, p95, driver errors, MongoDB topology/host metrics | Bằng chứng ban đầu |
| 10–15 phút | So sánh baseline, chia nhánh giả thuyết, chọn kiểm tra ít xâm lấn tiếp | Danh sách giả thuyết có ưu tiên |

Đây chỉ là ví dụ trình tự, không phải cam kết thời gian chẩn đoán. Sự cố mất dữ liệu hoặc an ninh nghiêm trọng có thể cần lập tức kích hoạt quy trình riêng.

### 5.1. Những câu cần trả lời trước khi sửa

- Từ lúc nào?
- Ở đâu?
- Điều gì thay đổi?
- Bằng chứng nào khẳng định hoặc bác bỏ?
- Thay đổi dự định có làm gián đoạn người dùng hay mất dữ liệu không?
- Phương án quay lại trạng thái trước là gì?

### 5.2. Không thay đồng thời nhiều biến

Nếu vừa tăng pool size, vừa thêm index, vừa restart replica set, sau đó p95 giảm, rất khó kết luận biện pháp nào hiệu quả và biện pháp nào gây tác dụng phụ.

## 6. Evidence ledger — sổ chứng cứ

Mỗi bằng chứng cần có **nguồn, thời điểm, scope, giá trị và mức tin cậy**.

| ID | Thời điểm UTC | Nguồn | Quan sát | Hướng liên quan |
| --- | --- | --- | --- | --- |
| E01 | 10:03:10 | API metrics | p95 endpoint /bookings tăng | Client symptom |
| E02 | 10:03:13 | Driver logs | Server selection errors tăng | Topology/network |
| E03 | 10:03:15 | Replica status | Không có primary trong một giai đoạn | Election |
| E04 | 10:03:16 | mongod logs | Member election events | Ủng hộ hypothesis |
| E05 | 10:06:00 | App metrics | Writes phục hồi sau primary được chọn | Phục hồi quan sát |

Không ghi “E03 chứng minh network lỗi” nếu chỉ biết primary thay đổi. Chứng cứ phải nói điều thực sự quan sát được.

### 6.1. Tách facts và interpretations

~~~text
FACT:
  Từ 10:03:11 đến 10:03:27 có nhiều server selection timeout.
  Primary changed between status samples.

HYPOTHESIS:
  Election window gây một phần lỗi ghi.

NOT YET KNOWN:
  Vì sao original primary trở nên không khả dụng.
~~~

### 6.2. Lưu bản gốc theo chính sách

Log và metrics gốc có thể cần lưu theo incident ID, nhưng cần giới hạn quyền và redact secrets/PII. Không gửi raw telemetry chứa credentials lên nơi công khai.

## 7. Đồng bộ thời gian và định danh

Một incident có thể trải qua Java JVM, Docker/Kubernetes, Linux host, mongod và hệ thống giám sát ở nhiều timezone.

### 7.1. Dùng mốc UTC thống nhất

Ví dụ:

~~~text
2026-11-14T10:03:14.320Z
~~~

Lưu kèm timezone nếu log nguyên gốc sử dụng giờ địa phương. Phân biệt wall-clock time và monotonic duration; clock skew có thể khiến thứ tự events nhìn sai.

### 7.2. Những định danh cần lưu

- Incident ID.
- Environment, cluster/deployment, region/AZ.
- Replica set, member, shard hoặc mongos nếu có.
- App service, pod/host, version/commit/release.
- Trace ID/request ID và tenant ID đã được mask/hash khi cần.
- Collection/operation category.
- Time window, query shape và workload size.

### 7.3. Không dựa hoàn toàn vào timestamp của một máy

Nếu host có clock skew, timeline cần đối chiếu với nguồn khác như platform events, cluster topology logs và tracing.

## 8. Mẫu incident record

~~~yaml
incidentId: "INC-2026-001"
title: "Booking read latency spike"
environment: "production"
severity: "SEV2"
status: "investigating"
startUtc: "2026-11-14T10:03:00Z"
scope:
  services: ["booking-api"]
  operations: ["find"]
  regions: ["region-a"]
  tenants: "multiple"
impact:
  errorRate: "observed in dashboard"
  p95: "observed above SLO"
changeWindow:
  - "booking-api release"
  - "index migration"
hypotheses:
  - id: H1
    statement: "query shape no longer matches index"
    evidenceFor: ["E01"]
    evidenceAgainst: []
    nextCheck: "capture query shape and explain"
owner: "incident commander"
mitigation: "not applied"
verificationGates:
  - "application p95 below SLO"
  - "business result counts correct"
  - "no new MongoDB errors"
~~~

Điền metrics bằng số liệu quan sát thật, không tự tạo trị số để báo cáo. Có thể dùng incident tracker/ticket thay YAML nếu tổ chức đã có hệ thống.

## 9. Thứ tự ưu tiên nguồn bằng chứng

Một trình tự ít rủi ro:

1. Dashboard sẵn có: traffic, errors, latency, CPU, disk, connections, replica lag.
2. App/driver logs, deployment events, tracing spans.
3. MongoDB logs theo time window.
4. Những lệnh đọc state: hello, rs.status, serverStatus và config.
5. Kiểm tra query/index bằng explain có giới hạn.
6. Profiler/currentOp có scope và thời gian kiểm soát khi thực sự cần.
7. Thí nghiệm canary hoặc thay đổi cấu hình được duyệt.
8. Remediation/failover/rollback nếu có runbook, quyền và đánh giá tác động.

### 9.1. Đừng bật profiler toàn cluster như phản xạ

Profiler ghi thêm dữ liệu và có tác động hiệu năng; mức profiling, slowms và sample rate phải phù hợp load và chính sách bảo mật.

### 9.2. Không lấy “toàn bộ log vĩnh viễn”

Giới hạn time range và members liên quan; ưu tiên logs quanh T0 ± thời gian phù hợp. Khối log quá lớn làm khó phân tích và tăng rủi ro rò PII.

## 10. Thu thập bằng chứng ở ứng dụng

Các tín hiệu quan trọng:

- Request rate và cơ cấu endpoints.
- Error rate theo exception class/status.
- p50/p95/p99 latency, queue time, timeout count.
- Số requests đồng thời và thread pool saturation.
- Database operation duration từ APM spans.
- Driver connection acquisition wait time.
- Server selection failure, network reset, authentication/TLS errors.
- Retry count và timeout budgets.
- Thời điểm deploy, config change, secret rotation.

### 10.1. Phân biệt thời gian ứng dụng và thời gian MongoDB

API p95=3s không chứng minh mongod xử lý query 3s. Có thể 2.8s chờ connection hoặc upstream dependency.

### 10.2. Không log toàn bộ query chứa dữ liệu cá nhân

Ghi **query shape**, collection, operation type, duration, trace ID; mask values nhạy cảm. Tránh log raw auth tokens/payment details.

### 10.3. Trace một request điển hình và một request lỗi

So ứng dụng trước/sau deploy, từng phase và downstream calls. Đừng chọn một trace bất thường rồi suy ra toàn hệ thống.

## 11. Java Driver: phân loại lỗi

Một số nhóm có ý nghĩa khác nhau:

| Nhóm | Khả năng | Hướng kiểm tra |
| --- | --- | --- |
| Server selection timeout | Không tìm server đáp ứng read/write preference | Topology, DNS, election, network |
| MongoSocketException | Kết nối/network bị lỗi | Network/TLS/server reset |
| MongoSecurityException hoặc auth failure | Credentials/roles/auth config | Secret rotation, auth source |
| MongoWriteConcernException | Write acknowledgement không đạt yêu cầu | Replication/majority, disk |
| Duplicate key error | Unique index bị vi phạm | Business key, concurrency |
| MongoCommandException | Server trả mã lỗi cho command | Error code, privileges, semantics |
| Connection acquisition timeout | Pool không cấp connection kịp | Pool usage/queue, slow operations |

Tên exception/capability cụ thể phụ thuộc version driver. Luôn lưu **error class/code** và context, không chỉ message đã bị cắt ngắn.

### 11.1. Timeout không chứng minh write chưa chạy

Một network timeout có thể xảy ra sau khi server đã ghi thành công nhưng response bị mất. Retry ở tầng nghiệp vụ cần idempotency/reconciliation để không ghi đôi.

### 11.2. Retryable writes có giới hạn

Driver có cơ chế retry cho thao tác/topology được hỗ trợ, nhưng không làm mọi workflow liên quan nhiều collections/external systems trở thành exactly-once.

## 12. Thu thập topology nhanh bằng mongosh

Kết nối bằng tài khoản **read-only/monitoring** phù hợp. Các lệnh:

~~~javascript
// Server currently contacted:
db.adminCommand({ hello: 1 });

// Version and selected server details:
db.version();

// Monitoring status, requires suitable privilege:
db.adminCommand({ serverStatus: 1 });
~~~

### 12.1. hello là quan sát của một node/route

`hello` có thể cung cấp thông tin role/isWritablePrimary/secondary, hosts, setName và topology metadata. Khi kết nối qua mongos, response khác khi kết nối trực tiếp mongod.

### 12.2. Đừng đoán một node đại diện toàn cluster

Một node healthy không chứng minh replica set/shard khác healthy. Thu thập đúng phạm vi.

### 12.3. Ưu tiên metrics platform

Atlas/Cloud Manager/Ops Manager hoặc hệ thống quan sát sẵn có thường có lịch sử từ **trước T0**; lệnh mongosh tại thời điểm hiện tại chỉ cho snapshot.

## 13. Đọc serverStatus có ngữ cảnh

Ví dụ chọn vài trường của kết quả khi có quyền:

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson({
  host: s.host,
  process: s.process,
  uptime: s.uptime,
  connections: s.connections,
  opcounters: s.opcounters,
  network: s.network,
  mem: s.mem
});
~~~

### 13.1. Counters thường là tích lũy

Nhiều metrics trong serverStatus là cumulative counters từ lúc process khởi động, không phải QPS/second trực tiếp. Cần lấy hai samples cách nhau một khoảng rồi tính delta/time.

### 13.2. Uptime/restarts

Nếu counters đột ngột reset, cần xem uptime/process restart trước khi kết luận traffic giảm. Một restart cũng có thể làm mất chứng cứ từ counter in-memory.

### 13.3. Connections không bằng requests

Nhiều connections không đồng nghĩa nhiều operations; pool có thể giữ idle connections. Cần so current/available/active và driver pool metrics theo version.

### 13.4. WiredTiger fields thay đổi theo phiên bản

Không viết automation phụ thuộc cứng mọi field ở mọi release. Giữ raw sampling và mapping theo version.

## 14. Thu thập logs của mongod/mongos

Tùy deployment:

~~~text
Linux + systemd:
  journalctl -u mongod --since "2026-11-14 10:00:00 UTC"
  journalctl -u mongod --until "2026-11-14 10:10:00 UTC"

Kubernetes:
  kubectl logs <pod-name> --since=30m --timestamps
  kubectl logs <pod-name> --previous --timestamps

Managed MongoDB:
  Atlas / Ops Manager log and metrics download
~~~

Các lệnh trên chỉ là minh họa: service unit/pod/container names phụ thuộc môi trường. Trong Kubernetes, việc lấy logs có thể cần chọn đúng container và namespace, kiểm tra RBAC.

### 14.1. Tìm tín hiệu theo triệu chứng

- Election/stepdown/topology changes.
- Slow operations/query shape.
- Authentication or TLS failures.
- Connection creation/closure spikes.
- Checkpoint/storage/IO errors.
- Too many open files/disk issues.
- Transaction/write concern errors.
- Sharding migration/router errors.

### 14.2. Không lọc log chỉ bằng một keyword

Lỗi trước/sau T0 có thể dùng thuật ngữ khác nhau. Dùng incident window, component IDs và request/correlation IDs.

### 14.3. Retention và privacy

Logs có thể chứa namespace, query parameters, hostnames, thông tin nhạy cảm hoặc payload. Lưu/trao đổi theo phân quyền.

## 15. Lấy in-memory log khi phù hợp

MongoDB có command đọc một phần in-memory log buffer (tùy phiên bản/quyền và deployment):

~~~javascript
db.adminCommand({ getLog: "global" });
~~~

### 15.1. Buffer không phải full history

Nó có thể chỉ chứa một phần log gần đây và bị ghi đè. Nếu cần phân tích quá khứ, dùng log files/observability retention.

### 15.2. Không dựa vào một log source

Kết hợp host/system logs và application traces để hiểu vì sao lỗi lan từ storage/replication lên API.

## 16. Kiểm tra thao tác đang chạy bằng currentOp

Ví dụ đọc snapshot operations khi có quyền:

~~~javascript
db.currentOp();
~~~

Hoặc qua aggregation `$currentOp` khi topology/permissions hỗ trợ:

~~~javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: true,
      localOps: true
    }
  },
  {
    $project: {
      opid: 1,
      ns: 1,
      secs_running: 1,
      op: 1,
      waitingForLock: 1
    }
  },
  { $limit: 50 }
]);
~~~

### 16.1. `currentOp` là snapshot

Một operation có thể hoàn tất trước khi bạn chạy lệnh. Không thấy slow query trong currentOp không chứng minh không có slow queries.

### 16.2. Không công khai raw command

Current operations có thể chứa query values. Khi đưa vào incident ticket, sanitize fields nhạy cảm.

### 16.3. Không kill operations tùy tiện

`killOp` có thể ảnh hưởng giao dịch, application retries và tính đúng đắn nghiệp vụ. Phải có quyền, tác động/owner và runbook riêng.

## 17. Database profiler: dùng thận trọng

Profiler cho phép ghi thông tin operations vào `system.profile` khi được bật theo mức cấu hình.

Ví dụ xem mức profiling hiện tại:

~~~javascript
db.getProfilingStatus();
~~~

Ví dụ đọc các entries đã tồn tại:

~~~javascript
db.system.profile.find(
  {},
  {
    ts: 1,
    millis: 1,
    ns: 1,
    planSummary: 1
  }
).sort({ ts: -1 }).limit(20);
~~~

### 17.1. Không bật profiling level 2 trên production theo quán tính

Logging tất cả operations có overhead và có thể chứa dữ liệu nhạy cảm. Nếu cần bật, nên chọn scope, thời gian, sampling và người phê duyệt.

### 17.2. Slow query logging cũng có tác động

MongoDB có slow operation logs/cấu hình thresholds khác theo môi trường và version. Đánh giá overhead trước khi chỉnh.

### 17.3. Profiler không thay application tracing

Một slow operation tại server không giải thích đầy đủ thời gian request ở network/pool/backend.

## 18. Query chậm: đo bằng explain

Ví dụ query tenant + status + createdAt:

~~~javascript
db.bookings.find({
  tenantId: "tenant-a",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20).explain("executionStats");
~~~

Tập trung vào:

- winningPlan.
- COLLSCAN, IXSCAN, FETCH.
- Blocking SORT nếu xuất hiện.
- nReturned.
- totalKeysExamined.
- totalDocsExamined.
- executionTimeMillis.
- Query filter/sort/projection và index definitions.

### 18.1. Quy tắc tỷ lệ sơ bộ

Nếu `totalDocsExamined` rất cao so với `nReturned`, query có thể đang đọc nhiều documents không cần thiết. Tuy nhiên, query có aggregation hoặc predicates chọn lọc đặc biệt cần đánh giá theo semantics.

### 18.2. Explain không chính là user latency

Explain có thể ảnh hưởng plan/measurement và không phản ánh network, app queues, serialization hoặc production concurrency. Dùng cùng metrics thực.

### 18.3. Không chạy explain trên query rất nặng thiếu giới hạn

Giữ filter/time range/limit phù hợp trên production và dùng staging representative nếu cần thử nghiệm lớn.

## 19. Thu thập index evidence

Các lệnh đọc:

~~~javascript
db.bookings.getIndexes();

db.bookings.aggregate([
  { $indexStats: {} }
]);
~~~

### 19.1. `$indexStats` là tín hiệu, không kết luận tuyệt đối

Counters có thể reset khi restart hoặc có window không đại diện. Một index ít dùng trong vài giờ không có nghĩa an toàn để drop.

### 19.2. Index candidate từ access pattern

Với equality trên tenantId/status và sort createdAt desc, _id desc:

~~~javascript
// Candidate index; do not create on production
// without approved change and impact assessment.
{
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
}
~~~

### 19.3. Index creation là write/DDL change

Một index build có thể dùng CPU, memory, storage, I/O và làm ảnh hưởng live workload. Chỉ thực hiện theo change management.

### 19.4. Query plan regression

Một release thay field, collation, type hoặc sort có thể khiến compound index cũ không còn phù hợp dù index vẫn tồn tại.

## 20. Truy vấn chậm vì dạng dữ liệu thay đổi

Một số nguyên nhân:

- `createdAt` bị ghi thành string thay vì BSON Date.
- `price` trộn String, NumberInt, Decimal128 không theo schema.
- Query trên nested path khác tên thực.
- Regex không anchor, khó tận dụng index.
- `$in` với danh sách cực lớn.
- `$lookup` không có index trên foreign keys.
- Pagination với skip rất sâu.
- Array lớn tạo nhiều multikey index entries.
- Aggregation group/sort trên dữ liệu quá rộng.

### 20.1. Kiểm tra schema drift trước khi thêm index

Nếu field không tồn tại hoặc sai kiểu, thêm index đôi khi chỉ che symptom. Xác định tại sao writer tạo dữ liệu sai.

### 20.2. Correlate với app release

Một DTO/codec mapping change có thể làm query BSON type khác trước, gây mismatch ngay cả khi bảng dữ liệu không đổi.

## 21. Connection pool exhaustion

Triệu chứng có thể gồm:

- Requests timeout trong lúc chờ MongoDB connection.
- Pool wait queue tăng.
- Active connections sát pool limit.
- Nhiều operations kéo dài làm connections bị giữ lâu.
- Tăng concurrency hoặc leak cursors/sessions.

### 21.1. Đừng chỉ tăng maxPoolSize

Nếu nguyên nhân là slow query giữ connection lâu, tăng pool có thể tăng tải lên mongod và làm tình hình xấu hơn.

### 21.2. Phân biệt client pool và server connections

`serverStatus.connections` là góc nhìn server; acquisition wait time thường cần driver instrumentation/APM metrics.

### 21.3. Các giả thuyết

- Pool quá nhỏ so với sustained concurrency.
- Query latency tăng dẫn tới giữ connection lâu.
- Application tạo MongoClient mới mỗi request.
- Connections không được trả do lifecycle/cursor/session issues.
- Network/TLS handshake làm connection creation chậm.

### 21.4. Verification

Sau sửa, pool wait p95 giảm, error rate giảm, server CPU/IO không bị đẩy quá tải và end-to-end SLO phục hồi.

## 22. Server selection timeout: không tự kết luận mongod down

Java driver chọn server theo topology, read preference, write requirements và server discovery.

Nguyên nhân có thể:

- Không có primary khả dụng khi cần write.
- DNS SRV/hostnames sai hoặc chưa cập nhật.
- TLS certificate/hostname verification lỗi.
- Firewall/network packet loss.
- Driver không reach được members được quảng bá.
- Replica set name/config mismatch.
- Read preference yêu cầu secondary nhưng không secondary nào phù hợp.
- Server selection timeout quá thấp so với failover thực tế.

### 22.1. Lưu topology events từ driver

Các sự kiện thay đổi server description, heartbeat failures và selection errors giúp phân biệt network với election.

### 22.2. Kiểm tra kết nối từ đúng app environment

Một mongosh trên laptop kết nối tốt không chứng minh pod trong private subnet reach được các replica set hosts.

### 22.3. Không “chữa” bằng cách bỏ TLS

Tắt TLS/hostname validation chỉ để kết nối được sẽ tạo rủi ro bảo mật và có thể che cấu hình mạng/chứng chỉ sai.

## 23. Replica set: thông tin cần thu thập

Nếu đang kết nối tới replica set phù hợp và có quyền:

~~~javascript
rs.status();
rs.conf();
db.adminCommand({ hello: 1 });
rs.printSecondaryReplicationInfo();
~~~

Một số helpers không hoạt động hoặc không phù hợp trên mongos/managed deployments; dùng giao diện giám sát chính thức tương ứng.

### 23.1. Quan sát member state

- PRIMARY.
- SECONDARY.
- STARTUP/STARTUP2/RECOVERING/ROLLBACK và các trạng thái khác.
- Health và heartbeat timestamps/messages.
- Election term/primary changes.
- Optime/last applied/durable op times.
- Replication lag và sync source.

### 23.2. Đối chiếu theo nhiều members

Một status snapshot từ một member có thể chưa đủ. Logs/metrics của các members và network events cùng thời điểm là cần thiết.

### 23.3. Không dùng rs.reconfig(force) để “thử”

Forced reconfiguration có thể làm mất dữ liệu hoặc tạo nguy cơ consistency nghiêm trọng. Chỉ theo quy trình recovery chính thức với owner có chuyên môn.

## 24. Elections và majority quorum

Replica set cần đủ **voting majority** để duy trì/elect primary theo cấu hình hiện hành.

~~~text
Voters = 3
Majority = floor(3/2) + 1 = 2

One voter lost:
  Remaining 2 can still form a majority,
  assuming network connectivity and eligible primary.

Two voters lost:
  Remaining 1 lacks majority.
~~~

### 24.1. Primary change thường gây gián đoạn ghi tạm thời

Client retries/topology discovery và election timing ảnh hưởng thời gian phục hồi. Đừng mặc định “có secondary” là writes không gián đoạn.

### 24.2. Khả năng bầu primary khác write durability

Election majority và write concern `"majority"` có liên hệ nhưng không đồng nghĩa mọi acknowledged write luôn an toàn nếu cấu hình/điều kiện đặc biệt chưa được hiểu.

### 24.3. Arbiter không giữ dữ liệu

PSA topology với arbiter có trade-offs về majority write availability/durability. Đừng dùng arbiter như bản sao dữ liệu.

## 25. Replication lag và write concern

Triệu chứng:

- Secondary reads nhìn thấy dữ liệu cũ.
- Writes có `w:"majority"` chậm hoặc timeout.
- Secondary không theo kịp write throughput.
- Lag tăng sau batch/migration hoặc network issue.

### 25.1. Thu evidence theo thời gian

Ghi primary/secondary optime, rate ghi, I/O/CPU, network, oplog window và backlog. Một lần lag spike không đủ để kết luận nguyên nhân.

### 25.2. Write concern error không chứng minh write thất bại

Write có thể đã được apply nhưng không nhận đủ acknowledgements theo concern/timing; outcome ở client cần kiểm tra idempotent theo business operation ID.

### 25.3. Read preference/read concern

Một query đọc SECONDARY có thể trả trạng thái stale nếu không có hợp đồng consistency phù hợp. So sánh “đọc ngay sau ghi” phải biết read preference, read concern và causal/session semantics.

### 25.4. Không hạ write concern chỉ để dập alert

Thay `majority` bằng `w:1` có thể thay durability guarantee. Nếu muốn đổi phải đánh giá rủi ro dữ liệu, RPO và phê duyệt.

## 26. Oplog window và secondary recovery

Nếu secondary lag rất xa hoặc offline quá lâu, nó có thể không còn theo kịp oplog history phù hợp.

### 26.1. Quan sát cần thu

- Oplog window/trend.
- Secondary applied/durable optime.
- Write rate và workload spikes.
- Storage/network availability.
- Initial sync/recovery logs.

### 26.2. Không chỉ nhìn một giá trị lag

Lag lớn có thể do member ngừng, network hoặc I/O. Đặt vào context oplog window và vị trí member.

### 26.3. Rebuild/resync có rủi ro vận hành

Không xóa data files hoặc restart để kích hoạt initial sync tùy tiện. Phải đánh giá quorum, capacity, disk và backup/DR.

## 27. Sharded cluster: mongos, shards và config servers

Với sharded cluster, request đi qua mongos tới shards. Một shard hotspot có thể làm chỉ một số tenants/queries chậm.

Các lệnh quan sát phù hợp khi có quyền:

~~~javascript
sh.status();
db.adminCommand({ listShards: 1 });
~~~

Kết nối tới mongos cho các helper/sharding metadata phù hợp; Atlas và managed deployments có giao diện metrics riêng.

### 27.1. Những câu hỏi quan trọng

- Một shard hay mọi shard chậm?
- Query có shard key equality để target đúng shard không?
- Một tenant lớn tạo hotspot?
- Chunk migrations/balancer activity diễn ra lúc T0?
- Config server replica set có sự cố?
- mongos routers có CPU/network hoặc connection issues?

### 27.2. Scatter-gather

Query thiếu shard-key targeting có thể fan-out tới nhiều shards. Không mặc định số shard tăng sẽ làm một scatter-gather query nhanh hơn.

### 27.3. Balancer và resharding

Đừng disable balancer/move chunks thủ công như thao tác đầu tiên. Thu thập metrics, đánh giá tác động và làm theo runbook/version phù hợp.

## 28. Storage: WiredTiger, cache và disk I/O

Một API chậm có thể do storage hơn là query planner.

Quan sát:

- Host CPU, load average và CPU throttling.
- Memory pressure, swap, OOM kills.
- Disk free space, latency, IOPS, queue depth.
- WiredTiger cache usage, eviction pressure.
- Checkpoint activity và write throughput.
- Storage errors trong logs.
- Container storage limits/volume health.

### 28.1. Disk full là sự cố dữ liệu, không chỉ latency

Khi disk gần hết, MongoDB writes/checkpoints có thể fail. Không xóa file storage hoặc journal thủ công để “giải phóng dung lượng”.

### 28.2. Filesystem/volume

Kiểm tra dung lượng host và persistent volume đúng nơi data/log lưu, không dựa vào filesystem khác trên cùng máy.

### 28.3. Swap và OOM

Một restart sau OOM có thể làm dịch vụ tạm hồi phục nhưng không giải quyết memory leak/misconfiguration.

### 28.4. Metrics cần có baseline

Cache 80% không tự nghĩa “cache xấu”. So eviction activity, I/O latency, page faults, workload và version-specific guidance.

## 29. Đọc host/container metrics

Một số quan sát không thay đổi dữ liệu:

~~~text
Linux:
  df -h
  free -m
  uptime
  iostat -x (nếu có)
  vmstat 1 (quan sát có giới hạn)

Kubernetes:
  kubectl top pod ...
  kubectl describe pod ...
  kubectl get events ...
~~~

### 29.1. Đúng host và đúng time window

CPU thấp tại T+20 phút không bác bỏ CPU saturation ở T0. Dùng lịch sử metrics nếu có.

### 29.2. Cẩn thận trong môi trường container

Container resource limits có thể khiến CPU throttling/OOM dù host còn tài nguyên.

### 29.3. Không tạo quá nhiều diagnostic load

Các lệnh đọc metrics thông thường ít rủi ro, nhưng sampling quá dày/log dumping lớn có thể làm tình hình xấu hơn khi cluster đã quá tải.

## 30. Locking, tickets và contention

MongoDB/WiredTiger có cơ chế concurrency control phức tạp. Khi operations chậm:

- Kiểm tra operation queue và latency.
- Tìm long-running transactions/reads.
- Đối chiếu write hot documents và lock/ticket metrics.
- Xem ticket/wait counters theo version.
- Xác định batch/DDL/index jobs hoạt động cùng thời điểm.

### 30.1. Một document nóng

Nếu hàng nghìn requests cùng update một counter document, contention tăng dù mỗi update atomic.

### 30.2. Long-running transactions

Transactions kéo dài có thể giữ nhiều resources, tăng memory/replication/storage pressure. Không tự kill transaction khi chưa biết business effects/retries.

### 30.3. Không gọi mọi delay là lock

Pool wait, network, storage queue và server scheduling có thể biểu hiện giống nhau ở API. Cần phân tách duration theo tầng.

## 31. Transactions và lỗi ghi

Một operation nhiều documents có thể báo transient transaction error hoặc unknown commit outcome.

### 31.1. Cần giữ error labels/codes

Log exception class, error labels, command category, transaction/session context đã sanitize và thời điểm.

### 31.2. Không retry toàn bộ nghiệp vụ vô điều kiện

Một payment capture hoặc booking confirmation không được thực thi hai lần chỉ vì MongoDB response timeout. Cần idempotency key, stable business ID và reconciliation.

### 31.3. Long transaction không phải giải pháp dữ liệu đúng

Nếu workflow chờ người dùng/payment provider, không giữ MongoDB transaction mở trong toàn bộ quy trình kéo dài.

## 32. Sai dữ liệu: khoanh vùng correctness

Có sự cố không biểu hiện qua CPU/latency:

- Documents bị gắn sai tenant.
- Stock âm sau concurrent decrements.
- Booking bị trùng khoảng.
- Tổng thanh toán bị cộng hai lần.
- Records missing sau migration.
- API đọc stale secondary.
- Một schema version reader diễn giải sai field.
- Backfill ghi đè CDC event mới hơn.

### 32.1. Xác định nguồn sự thật

Hỏi: application state, booking ledger, payment provider, SQL legacy hay MongoDB collection nào canonical?

### 32.2. Evidence phải có invariants

Count theo tenant/status, sum theo currency, uniqueness, version progression, event ID dedup, foreign references, availability overlap.

### 32.3. Không chạy mass updates để sửa khi chưa khoanh vùng

Sửa dữ liệu hàng loạt trên production trong khi chưa xác định root cause có thể xóa chứng cứ và gây thêm sai lệch.

## 33. Ví dụ dữ liệu sai vì read preference

Workflow:

~~~text
T0: write status=PAID to primary
T1: immediate read from secondary
T2: secondary replication catches up
~~~

Read ở T1 có thể thấy PENDING nếu dùng read preference/consistency cho phép stale reads.

### 33.1. Không kết luận write bị mất

Kiểm tra write acknowledgment, read preference, read concern, session/causal consistency và primary/secondary optime.

### 33.2. Business SLO quyết định consistency choice

Nếu read-your-writes là yêu cầu, ứng dụng phải chọn session/read strategy phù hợp; không chỉ tăng sleep ở client.

### 33.3. Stale cache cũng có thể gây giống triệu chứng

Nếu MongoDB primary đã có PAID mà API vẫn trả PENDING, kiểm tra Redis/CDN/app caches và event projection lag.

## 34. Authentication, authorization và TLS

Triệu chứng kết nối lỗi ngay sau secret rotation có thể là:

- Password/credential không đồng bộ giữa pods.
- authSource hoặc username sai.
- Client cert hết hạn hoặc chain không được trust.
- TLS hostname mismatch.
- IP allowlist/firewall thay đổi.
- Role không có quyền đọc collection/command mới.

### 34.1. Thu log an toàn

Lưu error code/class, certificate expiry metadata, service version và secret version label; **không** đưa password/private key vào incident notes.

### 34.2. Không đổi thành admin user để test trực tiếp

Nếu admin credentials hoạt động, điều đó chưa chứng minh app-role hoạt động. Dùng test principal có quyền tương đương production application.

### 34.3. Không tắt bảo mật vì lỗi khó đọc

Việc bỏ TLS/auth để “xác định nguyên nhân” trên production có rủi ro rất lớn. Dùng kiểm tra chứng chỉ và network có kiểm soát.

## 35. Bảng điều hướng triệu chứng → phép đo

| Triệu chứng | Giả thuyết chính | Bằng chứng phân biệt |
| --- | --- | --- |
| API p95 tăng, MongoDB execution time tăng | Query/index/storage | Explain, slow logs, CPU/IO |
| API p95 tăng, MongoDB ổn | Pool/queue/network/app | Traces, pool wait, thread pools |
| Writes timeout theo đợt | Election/network/write concern | rs.status, logs, acknowledgments |
| Secondary reads stale | Replication lag/read preference | Optime, read concern, app config |
| Một collection chậm | Missing index/data skew | Query plan, cardinality |
| Một shard quá tải | Shard-key hotspot/fan-out | Per-shard metrics, targeted queries |
| Tất cả ops chậm, disk latency cao | Storage pressure | Host I/O/WiredTiger |
| Sau deploy chỉ app version mới lỗi | Driver/codec/config regression | Version split, logs, request shape |
| Duplicate key tăng | Retry/upsert/identity issue | Unique index, request IDs |
| Sai totals sau migration | Transform/CDC ordering | Watermark, group counts, hashes |
| 401/auth errors tăng | Secret/TLS/auth changes | Auth logs, cert and role metadata |
| Connection count cao, pool waits | Pool pressure or leaks | Driver metrics, query durations |
| DB restart liên tục | OOM/disk/system events | Host logs, uptime, container events |

Bảng chỉ giúp **ưu tiên giả thuyết**. Một sự cố có thể đồng thời có nhiều nguyên nhân hoặc hệ quả dây chuyền.

## 36. Xếp hạng giả thuyết

Đánh giá mỗi giả thuyết theo:

1. Có khớp time window không?
2. Có giải thích đúng blast radius không?
3. Có phù hợp với architecture không?
4. Có bằng chứng ủng hộ độc lập không?
5. Có bằng chứng phản bác không?
6. Bước kiểm tra tiếp theo có rủi ro thấp không?
7. Nếu đúng, remediation có thể đảo ngược không?

Mẫu:

~~~yaml
hypothesisId: H2
statement: "Pool wait drives API latency"
predictions:
  - "driver acquisition wait increased"
  - "MongoDB server op time did not increase similarly"
evidenceFor:
  - E10
evidenceAgainst:
  - E12
nextCheck: "compare pool metrics by app pod/version"
confidence: "medium"
status: "open"
~~~

### 36.1. Không nâng confidence chỉ bằng số lượng log lines

Một lỗi tạo 1000 dòng cùng thông điệp không bằng 1000 nguồn chứng cứ độc lập.

### 36.2. Quan sát trái giả thuyết rất quý

Nếu các app pods cùng query nhưng chỉ một AZ lỗi, vấn đề query index toàn cluster trở nên ít có khả năng hơn; xem network/AZ routing.

## 37. Thí nghiệm kiểm chứng ít xâm lấn

Thứ tự ưu tiên:

1. So bản release lỗi với bản release khỏe.
2. So tenant/endpoint bị ảnh hưởng với không bị ảnh hưởng.
3. Chạy query explain read-only có scope hẹp.
4. Replay query đã sanitize trên staging có data representative.
5. Dùng canary traffic/một service instance nếu đã có cơ chế.
6. Thực hiện một approved config/index/application change và đo trước/sau.
7. Chỉ sau khi có evidence đầy đủ mới cân nhắc biện pháp destructive/high-impact.

### 37.1. Thiết kế test có falsifiability

Ví dụ “index sẽ giải quyết latency” dự đoán totalDocsExamined và p95 giảm khi query plan đổi sang IXSCAN phù hợp; nếu không giảm, xem thêm network/serialization.

### 37.2. Một biến mỗi lần

Nếu không thể giữ các biến khác ổn định vì incident thay đổi liên tục, ít nhất ghi thời điểm mọi hành động và external events để tránh gán nhầm nguyên nhân.

### 37.3. Không chạy load test trực tiếp khi DB đang quá tải

Replay/read-only vẫn có thể tốn CPU/IO. Tạo staging hoặc dùng canary với giới hạn request rate.

## 38. Quyết định remediation có kiểm soát

Trước khi sửa, ghi:

~~~text
CHANGE:
  What exactly changes?

EVIDENCE:
  Which hypothesis supports the change?

BLAST RADIUS:
  Which services/members/tenants could be affected?

DURABILITY:
  Could this change alter writes, read concern or RPO?

ROLLBACK:
  How to revert without losing committed data?

OBSERVABILITY:
  Which metrics must improve?

OWNER:
  Who approves and executes?

STOP CONDITION:
  When to abort the change?
~~~

### 38.1. Reversible trước irreversible

Rollback app release thường ít xâm lấn hơn force replica set reconfiguration. Nhưng rollback code vẫn có thể không tương thích schema mới hoặc writes đã phát sinh.

### 38.2. Bảo toàn bằng chứng

Chụp cấu hình/metrics/logs cần thiết trước restart khi có thể, không trì hoãn phục hồi khẩn cấp quá mức chỉ để lấy thêm logs.

### 38.3. Không thay đổi durability để có số xanh

Hạ write concern, tắt auth hoặc cho read từ stale secondary phải được coi là thay đổi behavior/độ tin cậy, không phải một “tối ưu timeout”.

## 39. Kiểm chứng sau sửa: bốn lớp

Một lệnh đã chạy thành công **không** đồng nghĩa sự cố đã được giải quyết.

| Lớp | Cần kiểm chứng | Ví dụ |
| --- | --- | --- |
| Infrastructure | Node/pod/disk/network ổn | Không restart loop, disk headroom |
| MongoDB | Topology/ops/lag/query khỏe | Primary, replicas catch up, error counters |
| Application | SLO/error/connection pool hồi phục | p95, 5xx, pool waits, retries |
| Business/data | Invariants, records và side effects đúng | Không double-book, totals đúng |

### 39.1. Có cửa sổ quan sát

Sau thay đổi, đo liên tục đủ lâu để vượt qua peak/cycle liên quan, không kết luận từ một request xanh. Thời lượng do SLO và incident owner chốt.

### 39.2. So baseline đúng điều kiện

Nếu traffic sau sửa giảm 90%, latency thấp chưa chứng minh root cause đã biến mất. So workload tương đương hoặc dùng controlled replay.

### 39.3. Kiểm tra bên không bị ảnh hưởng ban đầu

Thêm index hoặc config change có thể cải thiện một endpoint nhưng làm writes/backup chậm. Kiểm chứng regression ở các workloads lân cận.

## 40. Đặt acceptance criteria đo được

Ví dụ các gates **phải lấy ngưỡng thật từ SLO**, không coi trị số sau là chuẩn chung:

~~~yaml
verification:
  application:
    - "error rate below agreed threshold"
    - "p95 latency within SLO for representative load"
    - "pool acquisition waits normalized"
  mongodb:
    - "healthy primary and intended secondaries"
    - "replication lag within team threshold"
    - "no new storage/auth/network errors"
    - "query plan matches expected access pattern"
  data:
    - "business counts and totals reconcile"
    - "no duplicate booking or stock invariant violation"
    - "committed operations not silently lost"
  operations:
    - "alerts stable through observation window"
    - "rollback procedure still available"
~~~

### 40.1. Mỗi gate có owner và thời điểm

Không chỉ viết “đã ổn định”. Ghi who/when/metric source với evidence IDs.

### 40.2. SLO phục hồi có thể trước root-cause completion

Mitigation có thể dừng ảnh hưởng người dùng, nhưng postmortem/root-cause action items vẫn cần được theo dõi.

## 41. Ví dụ 1: booking feed bất ngờ chậm

**Bối cảnh:** endpoint `GET /bookings?status=PAID` p95 tăng sau release.

### 41.1. Triệu chứng

- Chỉ list endpoint chậm.
- Lookup booking bằng _id vẫn nhanh.
- Query count và documentsExamined tăng.
- Deploy vừa đổi sort/order logic.

### 41.2. Thu bằng chứng

~~~javascript
db.bookings.getIndexes();

db.bookings.find({
  tenantId: "tenant-a",
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20).explain("executionStats");
~~~

### 41.3. Giả thuyết

Query không tận dụng index hỗ trợ cả equality filters và sort, dẫn tới scan/sort lớn khi collection tăng.

### 41.4. Kiểm tra và remediation

So query shape và index trước/sau release. Nếu xác nhận, có thể rollback query thay đổi hoặc bổ sung **candidate** compound index được phê duyệt. Ví dụ:

~~~javascript
// DDL proposal only — requires approved change:
db.bookings.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

### 41.5. Verification

- Explain cho query representative dùng plan như mong đợi.
- totalDocsExamined/nReturned giảm đáng kể nếu đúng hypothesis.
- API p95 ở traffic tương đương về SLO.
- Write latency/index storage impact chấp nhận được.
- Result IDs và pagination vẫn đúng.

### 41.6. Điều không được kết luận vội

Không nói “đã tìm root cause” chỉ vì index xuất hiện. Nếu p95 vẫn cao, cần kiểm tra pool, network, serialization và data skew.

## 42. Ví dụ 2: ghi lỗi trong thời gian election

**Bối cảnh:** nhiều writes báo server selection error trong một khoảng ngắn.

### 42.1. Thu bằng chứng

- App logs: exact error class, time range, affected pods.
- Driver topology/heartbeat events.
- `rs.status()` và logs các members.
- Platform events: node restart, network/AZ issues.
- Majority voter availability.
- Retry/timeouts và business operation IDs.

### 42.2. Các giả thuyết cạnh tranh

H1: Primary election bình thường sau maintenance.

H2: Network partition khiến members không đạt majority.

H3: App pods không reach được hostnames được quảng bá sau topology change.

H4: Server selection timeout quá ngắn so với event bình thường.

### 42.3. Phân biệt

Nếu replica set đã có primary healthy nhưng chỉ một AZ của app vẫn không connect, xem DNS/network từ app AZ hơn là tiếp tục sửa MongoDB election config.

### 42.4. Mitigation và verification

Sau topology ổn định, xác nhận writes được acknowledge theo concern dự kiến, app errors giảm, retries không tạo duplicate records và secondaries catch up.

### 42.5. Tránh lệnh nguy hiểm

Không force rs.reconfig, xóa data directory hoặc rs.stepDown nhiều lần chỉ để thử. Thao tác đó có thể tạo thêm election hoặc rủi ro mất dữ liệu.

## 43. Ví dụ 3: API chậm nhưng mongod metrics bình thường

**Bối cảnh:** API p95 tăng, server query execution time không tăng đáng kể.

### 43.1. Bằng chứng tìm kiếm

- Driver pool acquisition wait time tăng?
- JVM threads blocked, GC pause?
- MongoClient mới cho mỗi request?
- Max pool size và concurrent requests?
- DNS/TLS connection creation chậm?
- Other upstream calls/timeouts?

### 43.2. Kiểm tra giả thuyết

So trace breakdown của một request chậm với query duration từ MongoDB. Nếu phần lớn thời gian nằm ở pool wait, không ưu tiên thêm index.

### 43.3. Hướng sửa

Có thể xử lý client lifecycle, connection pool settings hoặc long-running operations giữ connections. Một thay đổi maxPoolSize phải dựa vào load/capacity, không tăng vô hạn.

### 43.4. Verification

Pool waits giảm, p95 giảm, server load không tăng mất kiểm soát và peak concurrency xử lý ổn.

## 44. Ví dụ 4: replication lag và stale reads

**Bối cảnh:** sau khi xác nhận thanh toán, trang booking thỉnh thoảng vẫn hiển thị PENDING.

### 44.1. Bằng chứng

- Write result và write concern.
- Read preference của endpoint.
- Secondary optime/lag quanh thời điểm đọc.
- Cache/read model staleness.
- Payment/booking event ordering.

### 44.2. Giả thuyết

Read từ secondary chưa apply write hoặc API dùng cache chưa invalidate. Không kết luận write bị mất khi chưa kiểm tra primary state.

### 44.3. Hướng sửa

Chọn read strategy/session semantics đáp ứng read-your-writes; sửa cache invalidation hoặc giảm lag gốc. Tránh `Thread.sleep(1000)` như giải pháp tổng quát.

### 44.4. Verification

Sau write acknowledged, đường đọc bắt buộc nhất quán trả status đúng theo contract; application không tạo request/retry side effects trùng.

## 45. Ví dụ 5: Disk pressure làm writes không ổn định

**Bối cảnh:** MongoDB write latency và host disk latency tăng; gần hết dung lượng volume.

### 45.1. Bằng chứng

- Free space/time trend.
- Host volume IOPS/latency.
- WiredTiger checkpoint metrics.
- MongoDB storage errors/logs.
- Backup/retention/jobs đang chạy.
- Disk growth từ collections/indexes/logs.

### 45.2. Hướng xử lý có kiểm soát

Kiểm tra capacity scaling và approved retention/archive policy. Không tự xóa journal/data files, không chạy `mongod --repair` như bước đầu tiên.

### 45.3. Verification

Disk headroom ổn, I/O latency và checkpoint behavior bình thường, writes acknowledged, secondaries không tụt lag và có backup/restore readiness.

## 46. Ví dụ 6: Data drift sau migration

**Bối cảnh:** báo cáo tổng tiền MongoDB khác hệ thống SQL cũ sau backfill/CDC.

### 46.1. Bằng chứng

- Snapshot/CDC watermark của source.
- Total counts theo tenant/status/ngày.
- Sum theo currency.
- Duplicate business IDs.
- Source log sequence và target applied version.
- Quarantine/failed transform records.

### 46.2. Giả thuyết

- Backfill dùng numeric type sai.
- CDC event replay cộng tổng hai lần.
- Stale backfill ghi đè newer update.
- So baseline ở hai thời điểm khác nhau.
- Timezone mapping làm record lệch ngày.

### 46.3. Không chỉ so tổng count

Hai collections có cùng số documents vẫn có thể sai tenant, amount hoặc status.

### 46.4. Remediation và verification

Sửa transformation/event ordering có idempotency, replay theo nguồn sự thật và reconcile cùng watermark. Kiểm tra dữ liệu mới và old records trước khi đóng incident.

## 47. Kiểm chứng tính đúng đắn nghiệp vụ

Các ví dụ invariants:

~~~text
Booking:
  No overlapping active reservations for the same vehicle
  State transitions follow allowed paths

Inventory:
  Available quantity is never negative
  Reservations are not counted twice

Payment:
  Provider event IDs are not applied twice
  Sum of ledger entries matches authoritative records

Multi-tenant:
  No booking/customer association crosses tenant boundary

Migration:
  Counts, monetary totals and statuses reconcile
  with the same source snapshot / watermark
~~~

### 47.1. Chọn snapshot/timepoint phù hợp

Không so SQL lúc 10:15 với MongoDB mới cập nhật tới 10:10 rồi gọi đó là corruption.

### 47.2. Kiểm tra dữ liệu sau retry/timeouts

Một request có network timeout có thể đã ghi. Reconciliation theo idempotency key/business ID tránh ghi trùng.

### 47.3. Không dùng `countDocuments()` làm bằng chứng duy nhất

Counts bằng nhau không phát hiện đổi sai amount hoặc tenant. Cần business aggregates và sample deep comparisons.

## 48. Phân biệt chữa nguyên nhân và che triệu chứng

| Thao tác | Khi nào có thể giúp | Rủi ro nếu dùng sai |
| --- | --- | --- |
| Rollback app release | Regression vừa deploy | Schema compatibility/data writes |
| Tạo compound index | Query plan thiếu access path | Build load/write overhead |
| Điều chỉnh pool | Demand/capacity mismatch thật | Tăng áp lực mongod |
| Scale resources | CPU/IO saturation có baseline | Chỉ che query bug |
| Thay read preference | Consistency/read availability contract | Stale data |
| Thay write concern | Durability/latency trade-off được chấp thuận | Mất bảo đảm durability |
| Restart member | Process dead/unrecoverable có runbook | Election, cache cold, mất evidence |
| Kích hoạt resync | Secondary không theo kịp oplog với plan rõ | Tải network/disk, quorum risk |
| Kill long op | Operation gây hại có owner/impact | Partial business effects, retries |
| Xóa dữ liệu/index | Retention/change được phê duyệt | Mất dữ liệu/hiệu năng |

Mỗi biện pháp cần evidence, approval, rollback và verification gates riêng.

## 49. Post-fix monitoring window

Không đóng incident ngay sau một lệnh thành công.

### 49.1. Các mốc cần ghi

~~~text
T0  Impact begins
T1  Incident acknowledged
T2  Evidence captured
T3  Hypothesis confirmed
T4  Mitigation applied
T5  Application SLO recovers
T6  Business invariants verified
T7  Observation window ends
T8  Root cause / follow-up tracked
~~~

### 49.2. Theo dõi regression

Sau khi thêm index hoặc scale resources, kiểm tra writes, disk, memory, replication lag, failover readiness và các endpoints không liên quan.

### 49.3. Nếu metric không phục hồi

Không gắn nhãn RESOLVED chỉ vì DBA command thành công. Phải quay lại hypothesis tree và thu thập thêm chứng cứ.

## 50. Postmortem không đổ lỗi

Một postmortem có thể gồm:

1. Tóm tắt tác động người dùng/data.
2. Timeline theo UTC.
3. Facts và evidence IDs.
4. Trigger.
5. Root cause và contributing factors.
6. Why detection/mitigation took time.
7. Actions đã thực hiện, expected và observed effect.
8. Dữ liệu cần reconcile.
9. Preventive actions với owner/deadline.
10. Runbook/alerts/tests cần bổ sung.

### 50.1. Contributing factors khác root cause

Một deploy làm query chậm có thể cùng tồn tại với thiếu index review, staging dataset quá nhỏ và alert chậm. Cần ghi đủ các yếu tố hệ thống để ngăn tái phát.

### 50.2. Không viết root cause khi còn thiếu bằng chứng

Có thể ghi "probable cause" và open follow-up. Độ trung thực về uncertainty quan trọng hơn một kết luận chắc chắn nhưng sai.

## 51. Thiết kế alerts để lần sau có evidence sớm

Các nhóm cảnh báo thường hữu ích:

- Application 5xx/error budget/p95.
- MongoDB read/write latency, slow query trends.
- Connection pool acquisition failures.
- Primary availability/election counts.
- Replication lag và oplog window.
- Disk free space/I/O latency.
- CPU/memory/eviction pressure.
- Authentication/TLS anomalies.
- Sharded cluster hotspot/migration issues.
- Business invariant and reconciliation failures.

### 51.1. Alerts phải action-oriented

Một alert “CPU=80%” thường chưa đủ. Kết hợp symptom impact và duration, có link tới dashboard/runbook.

### 51.2. Đừng tạo alert storm

Nhiều metrics từ cùng một nguyên nhân nên được correlation/routed theo severity. Incident commander cần tín hiệu rõ, không phải hàng nghìn paging notifications.

### 51.3. Giữ historical metrics

Nếu retention quá ngắn, đội vận hành không còn baseline trước T0 để phân tích.

## 52. Checklist thu thập bằng chứng ban đầu

1. Đã xác định incident ID, severity và owners.
2. Mốc bắt đầu và timezone được ghi.
3. Đã mô tả số người dùng/endpoints/tenants bị ảnh hưởng.
4. Có baseline trước sự cố.
5. Có deployment/config changes gần T0.
6. Có request rates, error rates và latency.
7. Phân biệt app time và DB execution time.
8. Có driver exception class/code.
9. Có driver pool/server-selection metrics nếu sẵn có.
10. Có topology/replica/shard scope.
11. Có mongod/mongos logs theo window.
12. Có serverStatus/host CPU/memory/disk snapshots khi phù hợp.
13. Có query shape, index và explain nếu là query issue.
14. Có read/write concern và read preference liên quan.
15. Có business invariants nếu nghi data correctness.
16. Bằng chứng có nguồn/time/scope.
17. Secrets/PII đã được sanitize.
18. Chưa làm mất bằng chứng bằng thay đổi không cần thiết.

## 53. Checklist khoanh vùng nguyên nhân

1. Đã tách symptoms, observations và hypotheses.
2. Có ít nhất một giả thuyết phản biện cho kết luận chính.
3. Mỗi giả thuyết có prediction kiểm chứng được.
4. Phạm vi giả thuyết khớp blast radius.
5. Thời điểm giả thuyết khớp timeline.
6. Đã kiểm tra client vs server latency.
7. Đã kiểm tra network/TLS/DNS khi lỗi kết nối.
8. Đã kiểm tra query plan/index/schema khi lỗi truy vấn.
9. Đã kiểm tra primary/election/lag khi lỗi replication.
10. Đã kiểm tra per-shard khi sharded cluster chỉ lỗi một phần.
11. Đã kiểm tra host/disk/I/O khi nhiều ops chậm.
12. Đã kiểm tra deployment/codec/driver regression.
13. Không suy ra causality chỉ từ correlation.
14. Thí nghiệm có giới hạn tác động.
15. Có decision owner trước high-impact remediation.

## 54. Checklist kiểm chứng sau sửa

1. Biện pháp sửa được ghi rõ, có timestamp.
2. Có rollback/forward-fix contingency.
3. MongoDB primary/secondaries đáp ứng topology yêu cầu.
4. Replication lag và write concern đạt ngưỡng.
5. Không còn storage/network/auth errors mới.
6. Query plan và index coverage được xác minh.
7. App error rate, p95/p99 và pool waits về SLO.
8. Traffic so sánh có tính đại diện.
9. Critical read/write operations thành công.
10. Không có duplicate/out-of-order business effects sau retries.
11. Counts/totals/invariants được reconcile.
12. Không lộ dữ liệu giữa tenants.
13. Các endpoints lân cận không regress.
14. Alerts ổn định qua observation window.
15. Tồn tại evidence link cho từng gate.
16. Incident status được đổi theo quy trình.
17. Root-cause/prevention actions được giao owner.

## 55. Bài tập đọc bằng chứng

### Bài 1 — Triệu chứng hay nguyên nhân?

API p95 tăng, CPU mongod 95%. Viết ba giả thuyết khác nhau và một phép đo phân biệt từng giả thuyết.

### Bài 2 — Timeline

Logs của Java ở UTC+7, mongod ở UTC, Kubernetes events ở UTC. Chuyển các mốc về một timeline nhất quán và giải thích vấn đề clock skew.

### Bài 3 — Error taxonomy

Một request có server selection timeout. Nêu ít nhất bốn nguyên nhân có thể, không chỉ “MongoDB chết”.

### Bài 4 — Driver pool

App latency tăng nhưng server op time gần như không đổi. Thiết kế telemetry phân biệt pool wait và network.

### Bài 5 — Counter vs rate

ServerStatus opcounters tăng từ 10.000 lên 11.200 sau 60 giây. Tính ops/s trung bình trong window, giải thích vì sao không thể so raw counters qua restart.

### Bài 6 — Evidence ledger

Lập bảng 6 evidence rows có timestamp, source, fact và hypothesis mapping cho một election incident.

## 56. Bài tập truy vấn và topology

### Bài 7 — COLLSCAN

Một feed trả 20 docs nhưng examined 500.000. Nêu cách kiểm tra filter/sort/index và candidate index.

### Bài 8 — Blocking SORT

Query có compound index tenantId,createdAt nhưng filter thêm status. Thiết kế explain investigation trước khi tạo index mới.

### Bài 9 — Query mismatch

Driver ghi createdAt dưới dạng string sau deploy. Điều đó ảnh hưởng range query và sorting ra sao?

### Bài 10 — Election

Ba voting members, một member mất. Majority là mấy? Khi mất thêm một voter thì điều gì xảy ra?

### Bài 11 — Lag

Một secondary lag cao và read preference cho phép đọc từ nó. Kiểm tra read-your-writes semantics và cách chứng minh stale reads.

### Bài 12 — Write concern timeout

Một write trả timeout với w:"majority". Vì sao không được giả định write chưa áp dụng? Thiết kế idempotent reconciliation.

### Bài 13 — Shard hotspot

Chỉ tenant lớn trên shard A chậm. Liệt kê bằng chứng phân biệt shard key hotspot với mongos connection bottleneck.

## 57. Bài tập storage, dữ liệu và khắc phục

### Bài 14 — Disk pressure

Disk free thấp, checkpoint latency tăng. Viết runbook an toàn không xóa journal/data files.

### Bài 15 — OOM

Một mongod container restart do OOM. Dữ liệu nào cần thu trước khi thay memory limits? Tại sao restart tạm thời không là root-cause fix?

### Bài 16 — Bookings overlap

Hai requests cùng query không có overlap rồi insert. Thiết kế một invariant và phép kiểm chứng concurrency.

### Bài 17 — Payment duplicate

Webhook retry có thể cộng thanh toán hai lần. Cần kiểm tra event IDs, unique indexes và totals nào?

### Bài 18 — Migration drift

Counts bằng nhau nhưng amount sai. Thiết kế reconciliation theo tenant, ngày, currency và source watermark.

### Bài 19 — Remediation choice

Trong một query incident, so sánh rollback app, tạo index, tăng pool và restart mongod về evidence cần có, risks và verification.

### Bài 20 — Post-fix gates

Đặt tiêu chí rõ cho API, database và business data sau khi sửa một lỗi replica election.

## 58. Bài tập nâng cao

### Bài 21 — Causality

CPU và 5xx cùng tăng sau deploy. Có đủ bằng chứng rằng CPU là nguyên nhân không? Thiết kế timeline và trace comparison.

### Bài 22 — Read concern

Một API phải đọc đúng trạng thái ngay sau write. Xác định các yếu tố read preference/session/read concern cần kiểm tra.

### Bài 23 — CurrentOp

Không thấy operation chậm trong currentOp khi kiểm tra. Có thể kết luận không có slow query không? Nêu ba lý do.

### Bài 24 — Profiler

Thiết kế một kế hoạch profiling có sampling, timebox, privilege, privacy và rollback.

### Bài 25 — Cross-tenant leak

Một $lookup chỉ join theo customerId và trả sai tenant. Thiết kế test fixture và query fix.

### Bài 26 — Incident exercise

Được cung cấp logs giả lập từ app, MongoDB và host với timestamps. Lập evidence ledger, hypothesis ranking và root-cause uncertainty.

### Bài 27 — Change management

Viết một change proposal thêm index với scope, expected benefit, load risk, rollback và acceptance criteria.

### Bài 28 — Postmortem

Viết postmortem không đổ lỗi gồm trigger, root cause, contributing factors, impact, evidence links và action owners.

## 59. Runbook xử lý sự cố MongoDB

~~~text
TRIGGER:
  Alert or user symptom

DECLARE:
  Incident ID, severity, owners, blast radius

STABILIZE:
  Protect data and service
  Use approved low-risk mitigation if urgent

CAPTURE:
  UTC timeline and recent changes
  App/driver errors, latency and traces
  mongod/mongos logs
  Topology, replica/shard status
  Host storage, CPU, memory and network
  Query shape/explain if needed

HYPOTHESIZE:
  Distinguish fact vs inference
  Rank explanations
  Define disconfirming evidence

TEST:
  Read-only diagnostics first
  Scope and timebox each check
  Avoid production load experiments

CHANGE:
  One approved remediation
  Record precise time and owner
  Maintain rollback/forward-fix option

VERIFY:
  Database health and topology
  App p95/errors/pool waits
  Business data and idempotency invariants
  Regression checks on adjacent workloads
  Stable observation window

CLOSE:
  Preserve sanitized evidence
  Record root cause and uncertainty
  Assign prevention tasks and runbook changes
~~~

## 60. Kết luận

Xử lý sự cố MongoDB đáng tin cậy bắt đầu bằng việc **giữ được dấu vết và tách nhận định khỏi bằng chứng**:

- **Thu thập chứng cứ** từ ứng dụng, driver, mạng, mongos/mongod, replica set, sharding, query planner, storage và dữ liệu nghiệp vụ, với timestamp/source rõ.
- **Khoanh vùng nguyên nhân** dựa trên phạm vi ảnh hưởng, timeline, giả thuyết có thể bác bỏ và phép đo ít xâm lấn.
- **Sửa có kiểm soát** với owner, đánh giá tác động, nhất quán/durability và rollback gates.
- **Kiểm chứng sau sửa** trên cả bốn lớp: hạ tầng, MongoDB, ứng dụng và business/data correctness, không chỉ một command thành công.
- **Ngăn tái phát** bằng metrics lịch sử, alerts theo SLO, regression/concurrency tests, schema/index review, runbook và postmortem không đổ lỗi.

Một outage có thể hết biểu hiện trước khi nguyên nhân gốc được xác nhận. Ngược lại, một index hoặc restart thành công không có nghĩa dữ liệu và nghiệp vụ đã phục hồi. Mục tiêu cuối cùng là **khôi phục dịch vụ mà không đánh đổi tính đúng đắn, hiểu được cơ chế sự cố và làm cho lần xử lý tiếp theo nhanh hơn, an toàn hơn và có thể kiểm chứng**.

## Tài liệu tham khảo

- [MongoDB Manual — Monitoring](https://www.mongodb.com/docs/manual/administration/monitoring/)
- [MongoDB Manual — serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB Manual — hello](https://www.mongodb.com/docs/manual/reference/command/hello/)
- [MongoDB Manual — currentOp](https://www.mongodb.com/docs/manual/reference/command/currentOp/)
- [MongoDB Manual — Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Replica Set Status](https://www.mongodb.com/docs/manual/reference/method/rs.status/)
- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [MongoDB Manual — Replication Lag](https://www.mongodb.com/docs/manual/tutorial/troubleshoot-replica-sets/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Manual — WiredTiger](https://www.mongodb.com/docs/manual/core/wiredtiger/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
