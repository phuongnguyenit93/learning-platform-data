# Kiểm thử lỗi node trong môi trường thử nghiệm có kiểm soát với Spring Data Couchbase

> **Chương:** Độ bền ghi  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase bằng Spring Data với document mapping, repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive để bảo đảm hiệu năng, tính nhất quán và khả năng vận hành.

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Thiết kế một **failure drill** cho Couchbase mà không nhầm thử lỗi node với thử timeout của HTTP client.
2. Xây dựng môi trường **staging/lab cô lập** có bucket, Data nodes, replica và workload đủ điều kiện để đánh giá Sync Writes.
3. Lập danh sách preflight, người phê duyệt, stop conditions, kế hoạch rollback và nguồn bằng chứng trước khi tạo lỗi.
4. Phân biệt **node crash**, mất mạng, hard failover, graceful failover, auto-failover, node restart, recovery và rebalance.
5. Tính majority cho bucket 0, 1, 2 replica và nhận biết giới hạn không hỗ trợ Sync Writes khi bucket có 3 replica theo tài liệu Server hiện hành.
6. Kiểm tra **an toàn của các mutation đã được xác nhận**, **khả năng ghi khi suy giảm**, **độ trễ** và **khả năng phục hồi** bằng những tiêu chí tách biệt.
7. Dùng Java SDK, Spring Data repository, `CouchbaseTemplate` và reactive API để tạo workload có ID ổn định, ghi log kết quả và đối soát.
8. Hiểu tại sao `AmbiguousTimeoutException` hoặc `DurabilityAmbiguousException` không chứng minh mutation chắc chắn đã hoặc chưa commit.
9. Xây dựng bài test CAS/idempotency, giám sát p95/p99, phân loại lỗi, soát duplicate, đo RPO/RTO và kiểm tra phục hồi replicas.
10. Chuyển kết quả lab thành đề xuất cấu hình, runbook và acceptance criteria có thể review bởi DBA/SRE, QA và chủ sở hữu nghiệp vụ.

## 2. Quy tắc an toàn: thử lỗi ở lab, không ở production

Bài học mô tả **cách thiết kế và quan sát** fault injection trong cụm Couchbase **chỉ dành riêng cho thử nghiệm**. Các hành động làm gián đoạn Data node chỉ được thực hiện bởi người có thẩm quyền theo runbook tại môi trường được cấp phép. **Không thực hiện bất kỳ lệnh dừng node, hard failover hay cô lập mạng nào trong production** để hoàn thành bài học.

### 2.1. Giới hạn phạm vi được phép

Một thí nghiệm hợp lệ nên có:

- Cluster Couchbase **lab độc lập**, không chia sẻ Data/Index services với production.
- Bucket và dữ liệu **giả lập**, không chứa thông tin khách hàng hay secret thật.
- Network/DNS, credential, tài nguyên và quota riêng.
- Người điều phối: QA/test owner; chủ cluster: DBA/SRE; người chịu trách nhiệm ứng dụng: developer.
- Lịch thao tác và rollback đã được thống nhất; không tự ý kéo dài fault.
- Snapshot/backup test trước khi inject lỗi và cách khôi phục đã được diễn tập.
- Mức tải đặt giới hạn để không ảnh hưởng hạ tầng dùng chung.
- Stop conditions được thống nhất trước khi chạy.

### 2.2. Stop conditions không được bỏ qua

Ngừng fault injection và chuyển sang phục hồi nếu:

1. Có dấu hiệu test traffic đi nhầm vào production hoặc môi trường shared.
2. Cluster không còn đường khôi phục khả thi theo kế hoạch.
3. Lượng dữ liệu thử nghiệm bị mất vượt kịch bản cho phép và điều đó cản trở thu thập bằng chứng.
4. CPU/disk/network chạm mức nguy hiểm khiến việc phục hồi node có rủi ro.
5. Rebalance/failover phát sinh ngoài phạm vi đã phê duyệt.
6. Monitoring, log hoặc correlation bị mất khiến không thể phân loại kết quả.
7. Có người sở hữu hạ tầng yêu cầu dừng.

**Đích của một failure drill không phải làm cụm ngừng hoạt động càng lâu càng tốt**, mà là tạo một biến cố định nghĩa trước, đo tác động, và **phục hồi được một cách kiểm chứng**.

## 3. Điều phải chứng minh: bốn hợp đồng khác nhau

Giả sử một service tạo đơn hàng ở:

~~~text
Bucket: commerce_test
Scope: sales
Collection: orders
Document key: tenant::lab::checkout::run-42-0001
~~~

Một mutation `insert(... MAJORITY)` thành công trước khi node lỗi có thể được đánh giá bằng bốn câu hỏi:

| Hợp đồng | Câu hỏi đo được | Bằng chứng |
|---|---|---|
| **Write durability** | Mutation đã được SDK xác nhận theo mức hiệu lực chưa? | `MutationResult`/response, bucket policy, logs |
| **Data survival** | Sau failover, document đã ack còn truy cập được ở trạng thái kỳ vọng không? | KV get theo ID, fingerprint/checksum |
| **Write availability** | Những mutations mới có còn đạt yêu cầu khi thiếu Data node không? | Success/error rate chia theo level và vBucket |
| **Recovery** | Dịch vụ và mức redundancy ban đầu trở lại sau bao lâu? | Routing, node/vBucket health, rebalance, RTO |

Một thí nghiệm chỉ đo “HTTP endpoint trả 200” **không đủ** để kết luận dữ liệu bền sau mất node. Ngược lại, một `GET` lỗi trong hai giây chuyển chủ cũng chưa đủ để kết luận dữ liệu đã mất vĩnh viễn.

### 3.1. RPO và RTO phải gắn với kịch bản

- **RPO:** phần dữ liệu đã được báo success mà môi trường vẫn chấp nhận có thể mất trong sự cố được định nghĩa.
- **RTO:** thời gian để dịch vụ đạt trở lại trạng thái phục vụ tối thiểu theo SLO.
- **Redundancy recovery time:** thời gian để khôi phục **số bản replica và phân bố** như trước lỗi. Có thể dài hơn RTO của API.

Không gọi các giá trị RPO=0 hay RTO=0 một cách tuyệt đối nếu chưa mô tả **một lỗi Data node**, **hai Data nodes**, **mất rack/zone** hoặc **mất toàn cluster**.

## 4. Kiến trúc lab tối thiểu và biến đầu vào

Couchbase dùng vBucket với một active và số replica cấu hình cho bucket. Để chạy test quorum, cần nhìn **số Data nodes** chứ không chỉ số node tổng.

~~~mermaid
flowchart LR
    Load["Test driver<br/>JUnit / Spring Boot"]
    SDK["Couchbase Java SDK"]
    A["Data node A<br/>Active V42"]
    B["Data node B<br/>Replica V42"]
    C["Data node C<br/>Replica V42"]
    Monitor["Metrics + event timeline"]
    Load --> SDK --> A
    A -->|"Replication"| B
    A -->|"Replication"| C
    A -.-> Monitor
    B -.-> Monitor
    C -.-> Monitor
    Load -.-> Monitor
~~~

Bảng cấu hình thí nghiệm:

| Nhóm lab | Số Data nodes | Bucket replica count | Majority | Test chính |
|---|---:|---:|---:|---|
| **A — học API** | 1 | 0 | 1/1 | Ghi và đọc baseline; **không** kiểm chứng HA |
| **B — một replica** | 2 | 1 | 2/2 | Khi một bản mất khả dụng, durable write có thể không đạt majority |
| **C — hai replicas** | 3 | 2 | 2/3 | Kiểm tra một bản tạm không khả dụng và failover/recovery |
| **D — cấu hình không hỗ trợ** | ≥4 | 3 | Không áp dụng | Negative test cho giới hạn Sync Writes theo Server hiện hành |

**Couchbase Server hiện hành hỗ trợ Sync Writes với tối đa hai replica.** Một bucket cấu hình 3 replicas có thể phục vụ replication thông thường nhưng thao tác yêu cầu synchronous durability không được hỗ trợ. Đây là **negative test**, không phải phương án tăng mức durability.

### 4.1. Ba node tổng chưa chắc đủ

Ví dụ lab có:

~~~text
Node A: Data + Query
Node B: Query + Index
Node C: Index

Số Data nodes thực tế = 1.
~~~

Dù UI hiện ba node, lab này **không** đủ ba Data copies cho bucket 2 replicas. Query/Index replicas cũng không tham gia majority của KV durable writes.

### 4.2. Replica cấu hình không bằng replica đang khỏe

`replicaNumber=2` là mục tiêu phân bố. Nó không tự chứng minh cluster đã tạo đủ active + 2 replicas sau khi vừa thêm node hoặc chưa rebalance. Trước test phải xác minh **vBucket placement**, replica health, active ownership và node service assignments.

### 4.3. Tách failure domains

Nếu có thể, bố trí Data nodes ở các host/zone hoặc Server Groups thích hợp để đánh giá lỗi theo failure domain. Ba container trên cùng một host là **thí nghiệm node/process availability**, không chứng minh chịu mất host vật lý hoặc một zone.

## 5. Chọn bucket type và durability levels trước khi inject fault

Java SDK 3.x cung cấp:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
~~~

| Level | Điều kiện trước khi success | Điều kiện lab cần hỗ trợ |
|---|---|---|
| `NONE` | Không yêu cầu synchronous durability bổ sung từ mutation (trừ minimum bucket) | Baseline ghi thông thường |
| `MAJORITY` | Majority các bản liên quan xác nhận mutation trong bộ nhớ theo giao thức | Replica/quorum phù hợp |
| `MAJORITY_AND_PERSIST_TO_ACTIVE` | Majority và active persist | **Couchbase bucket** có persistence |
| `PERSIST_TO_MAJORITY` | Persist trên majority bản liên quan | **Couchbase bucket**, storage/replicas đủ điều kiện |

Với **Ephemeral bucket**, có thể kiểm thử `MAJORITY` khi topology hỗ trợ, nhưng các level yêu cầu disk persistence không phù hợp. Không dùng Ephemeral lab để kết luận về `PERSIST_TO_MAJORITY` trên Couchbase bucket.

### 5.1. Minimum durability tại bucket

Một bucket có thể đặt mức tối thiểu. Khi client yêu cầu thấp hơn minimum, server vẫn thực thi mức mạnh hơn. Điều này ảnh hưởng test design:

~~~text
Bucket minimum: MAJORITY
Client ghi với DurabilityLevel.NONE

Kết luận KHÔNG HỢP LỆ:
"Đây chắc chắn là ghi NONE."
~~~

Thí nghiệm phải lưu **client requested level** và **minimum bucket level**, không chỉ tên enum trong code. Nếu muốn so baseline `NONE` và `MAJORITY`, dùng bucket policy thích hợp trong lab riêng đã kiểm tra.

### 5.2. Đừng hạ level trong error handler

Nếu muốn kiểm chứng điều kiện `PERSIST_TO_MAJORITY` khi node lỗi, không được bắt timeout rồi retry bằng `NONE` để tăng success rate. Đó là **một thí nghiệm khác** với rủi ro dữ liệu khác.

## 6. Preflight: tờ khai thí nghiệm trước khi chạy

Ví dụ một test charter:

~~~yaml
experimentId: cb-durability-node-fault-2026-11-25-01
environment: isolated-staging
owner:
  application: order-team
  cluster: database-sre
  observer: qa-team
scope:
  bucket: commerce_test
  scope: sales
  collection: orders
  service: order-api-lab
topology:
  dataNodes: 3
  replicas: 2
  bucketType: couchbase
  requiredDurability: MAJORITY
fault:
  target: one designated Data node
  kind: controlled-node-unavailability
  maxDurationSeconds: 90
successCriteria:
  preFaultAckedDocsSurvive: true
  noDuplicateBusinessCommands: true
  recoveryReplicaPlacementVerified: true
stopOn:
  - wrong-environment
  - unexpected-second-node-failure
  - loss-of-observability
  - cannot-recover-with-runbook
~~~

Đây là **mẫu kế hoạch, không phải cấu hình mà Couchbase hoặc test runner tự đọc**. Các thông số thời gian/số node là ví dụ lab và cần được người có quyền phê duyệt.

### 6.1. Tài sản cần chuẩn bị

1. Danh sách node/service và URL monitoring của lab.
2. Snapshot bucket, vBucket active/replica map, server groups.
3. Bucket type, `replicaNumber`, minimum durability và fallback status.
4. Phiên bản Couchbase Server/Capella và Java SDK/Spring Data.
5. Dữ liệu seed đã biết ID, fingerprint, CAS khi cần.
6. Công cụ load generator độc lập, giới hạn ops/s và concurrency.
7. Dashboard/clock đồng bộ đủ cho sự kiện trong cùng timeline.
8. Trình tự điều phối fault và rollback do DBA/SRE kiểm soát.
9. Chủ sở hữu mỗi chỉ số, nơi lưu test report.
10. Quy tắc xóa sạch dữ liệu thử nghiệm khi hoàn tất.

### 6.2. Ghi rõ “không kiểm thử điều gì”

Một lab 3 Data nodes trong cùng host không kiểm thử mất cả host. Một test cô lập mạng chỉ chứng minh phản ứng với network partition phù hợp, không tự chứng minh disk corruption. Một test failover trong cùng cluster không kiểm thử DR mất region.

Giới hạn này phải nằm trong báo cáo kết quả.

## 7. Phân loại fault injection trước khi thực hiện

| Fault được mô phỏng | Giống điều gì? | Không thể tự suy ra |
|---|---|---|
| **Restart Data process** | Tạm mất service, có thể giữ disk | Mất node/disk vật lý vĩnh viễn |
| **Stop một Data node trong lab** | Node không phục vụ tạm thời | Auto-failover chắc chắn xảy ra |
| **Network partition có kiểm soát** | Client/cluster không liên lạc được một node | Dữ liệu đã mất; mọi partition có cùng semantics |
| **Hard failover do admin lab khởi động** | Loại node lỗi khỏi membership | Graceful handoff |
| **Graceful failover do admin lab** | Chuyển vai trò có kế hoạch | Node crash đột ngột |
| **Rebalance sau đổi topology** | Di chuyển/khôi phục active và replica placements | Backup hoặc phục hồi lịch sử |
| **Chặn/giảm I/O storage ở lab** | Persistence bottleneck | Lỗi disk toàn diện hoặc mức durability sai |
| **Drop response sau commit ở test proxy** | Client gặp ambiguous outcome | Node thật đã failover |
| **Kill HTTP client/request** | Caller ngừng chờ | Server rollback KV mutation |

Không gộp mọi loại fault vào một biểu đồ “có lỗi/không lỗi”. Mỗi fault tạo ra một **kịch bản khác và điều kiện quan sát khác**.

### 7.1. Ai chịu trách nhiệm tạo fault?

- DBA/SRE điều phối **Data node, failover/rebalance, disk/network** trong lab.
- Application QA/developer điều phối **test driver, request timeout, fault proxy**.
- Product/business owner phê duyệt **mức rủi ro dữ liệu** được mô phỏng và kết quả chấp nhận.

Bài học không đưa một lệnh phá hủy có thể bị dán nhầm vào production. Các nút thao tác/bản lệnh cụ thể phải nằm trong runbook riêng được kiểm tra target lab.

### 7.2. Không chạy hai fault không phân biệt được

Nếu vừa dừng Data node, vừa giảm disk I/O trên replica, rồi thấy timeout, bạn khó quy nguyên nhân cho quorum hay persistence. Bắt đầu **mỗi lần chỉ một fault**, sau khi có baseline, rồi mới phối hợp lỗi trong kịch bản nâng cao đã phê duyệt.

## 8. Tổ chức test theo các pha có mốc rõ ràng

~~~mermaid
flowchart TD
    Pre["PREPARE<br/>Kiểm tra môi trường, backup và telemetry"]
    Base["BASELINE<br/>Ghi và xác minh data healthy"]
    Inject["INJECT<br/>Một node fault theo runbook"]
    Observe["OBSERVE<br/>Error classes, latency, KV read"]
    Recover["RECOVER<br/>Phục hồi node và rebalance"]
    Verify["VERIFY<br/>Data, replica placement, business invariant"]
    Report["REPORT<br/>RPO, RTO, exceptions, giới hạn"]
    Pre --> Base --> Inject --> Observe --> Recover --> Verify --> Report
~~~

### 8.1. PREPARE

Bảo đảm thí nghiệm có permission, chỉ chạy trên lab, không có traffic ngoài phạm vi và có rollback. Thu thập cấu hình/phân phối vBucket **trước** fault.

### 8.2. BASELINE

Ghi N documents với **stable IDs**, biết mutation nào được SDK xác nhận success. Kiểm tra KV reads và checksum/fingerprint. Ghi p95/p99, throughput, timeout count, replica health.

### 8.3. INJECT

DBA/SRE làm **một hành động** đã phê duyệt trên đúng Data node lab. Ghi timestamp và evidence môi trường đã thay đổi. Không đồng nhất “chạy command thành công” với “vBucket đã failover”.

### 8.4. OBSERVE

Giữ tải thấp/giới hạn. Chia kết quả: success, explicit failures, ambiguous, duplicate, CAS conflict. Đọc lại các ID **đã success trước fault** và ghi trạng thái.

### 8.5. RECOVER

Hoàn nguyên network/process, thực hiện recovery/rebalance theo runbook nếu cần. Không xóa cluster rồi tái tạo mà vẫn gọi là “đã phục hồi” nếu bài test yêu cầu đo RTO từ fault thật.

### 8.6. VERIFY và REPORT

Đối chiếu document IDs/fingerprints, không có duplicate business commands, kiểm tra actual replica placement và service health. Báo cáo cả những **kịch bản chưa được kiểm chứng**.

## 9. Tách ba nhóm dữ liệu test theo thời điểm

Để hiểu kết quả, tạo dữ liệu có tên và ID dễ phân nhóm:

~~~text
run-42::before::0001 ... before::0100
run-42::during::0001 ... during::0100
run-42::after::0001  ... after::0100
~~~

| Nhóm | Khi ghi | Điều đánh giá |
|---|---|---|
| **Before** | Trước node fault, đã nhận `MutationResult` success | Survival của **đã được ack** sau failover |
| **During** | Trong lúc node missing/failover/owner change | Write availability, error classification, ambiguous outcome |
| **After** | Sau recovery/rebalance | Khả năng ghi và redundancy đã phục hồi |

### 9.1. Vì sao phải lưu tập before?

Nếu không lưu danh sách IDs được xác nhận trước sự cố, một kết quả “đọc thấy nhiều document” không chứng minh **tất cả các writes đã ack** còn đúng.

Lưu tập before cùng fingerprint, expected fields và mức durability yêu cầu trong một artifact test **đáng tin cậy nhưng nằm ngoài Couchbase bucket đang bị fault**. Không cần chứa dữ liệu nhạy cảm.

### 9.2. Không áp SLA giống nhau cho mọi pha

During có thể có lỗi kỳ vọng khi quorum không đủ. Một test thành công có thể là **server từ chối xác nhận ghi mà không đạt durability**. Vì vậy đừng đặt tiêu chí “100% writes success trong fault” cho một topology vốn không thể có majority.

## 10. Lab một Data node, không replica: baseline và negative guarantee

Lab A:

~~~text
Data nodes: 1
Bucket replicaNumber: 0
Majority: 1/1
~~~

Một `MAJORITY` mutation có thể báo success theo majority 1/1. Nhưng nếu node duy nhất bị mất hoàn toàn, không có bản replica để promote.

Do đó:

- Dùng lab này để xác nhận mapping Spring Data, SDK options, keyspace và basic CRUD.
- **Không dùng nó làm bằng chứng chịu lỗi Data node**.
- Nếu test restart process giữ disk của Couchbase bucket, có thể thấy dữ liệu sau restart; đó là **restore từ local storage** chứ không chứng minh failover qua replica.
- Không thử hủy dữ liệu thật của test cluster nếu không cần; có thể dùng failure model mô phỏng và document rõ giới hạn.

### 10.1. Negative test khác test thất bại

Một kết quả kiểu “không có replica để cứu dữ liệu khi node/disk biến mất” là **điểm giới hạn kiến trúc được nhận biết**, không phải lý do test automation phải luôn báo đỏ. Acceptance criteria phải nói rõ mong muốn ngay từ đầu.

## 11. Lab hai Data nodes, một replica: majority 2/2

Lab B:

~~~text
Node A: active vBucket V42
Node B: replica vBucket V42
Bucket replicaNumber=1
Required majority=2
~~~

**Bình thường:** A và B đáp ứng majority, mutation `MAJORITY` có thể hoàn tất.

**Replica B không khả dụng:** A có thể còn phục vụ KV; nhưng durable write trên vBucket liên quan thiếu 2/2 và **không được giả định có thể báo success đúng level**.

### 11.1. Thí nghiệm cần chứng minh hai điều

1. **Writes đã ack trước lỗi:** khi điều kiện failover/recovery hợp lệ, dữ liệu có tồn tại theo bảo đảm level hay không?
2. **Writes mới trong degraded state:** hệ thống xử lý thiếu majority thế nào? Có thể timeout, báo durability unavailable/impossible, hoặc báo ambiguous theo thời điểm.

Hai điều độc lập. Dữ liệu cũ còn không có nghĩa có thể tiếp tục write majority trong khi replica chưa phục hồi.

### 11.2. Tính hợp lệ của auto-failover trên lab hai node

Không giả định cluster hai Data nodes sẽ tự failover giống cluster nhiều node hơn; Couchbase có yêu cầu về membership, edition, auto-failover policy và điều kiện an toàn riêng. Dùng **trạng thái failover thực tế** trong log/UI làm bằng chứng, không suy từ việc dừng một process.

### 11.3. Kết luận hợp lệ

“Nếu vBucket thiếu một trong hai bản, mutation cần 2/2 majority không thể được coi thành công ở mức đó trong điều kiện thông thường.” Không suy rộng rằng **tất cả endpoints** hoặc **mọi vBucket** đều lỗi cùng lúc, hay việc rollback/restore đã xảy ra.

## 12. Lab ba Data nodes, hai replicas: majority 2/3

Lab C:

~~~text
Node A: active V42
Node B: replica V42
Node C: replica V42
Required majority=2/3
~~~

Thử làm một replica không khả dụng trong lab và quan sát:

- Nếu active và replica còn lại khỏe, một mutation `MAJORITY` **có thể** vẫn đạt 2/3.
- Nếu active mất, cluster có thể promote replica sau failover theo policy/protocol, nhưng routing sẽ có một khoảng chuyển.
- Những writes pending hoặc response bị mất khi chuyển chủ có thể **ambiguous**.
- Sau fault, số bản dự phòng có thể giảm; cần recovery/rebalance để khôi phục redundancy.

### 12.1. Vì sao không hứa 2-node tolerance?

Một mutation M được ack khi A và B đã có M, nhưng C chưa bắt kịp. Nếu **A và B** bị loại trước khi C nhận M, M có thể mất dù client đã nhận `MAJORITY` success. Đây là giới hạn của durability khi mất những node giữ majority.

Thí nghiệm này cần được xem như **negative guarantee về chuỗi lỗi nhiều node**, không phải rủi ro để tùy tiện phá nhiều nodes trên production.

### 12.2. Thứ tự node lỗi quyết định kết quả

“Có một node lỗi” không nói đủ:

- Node đó giữ active hay replica?
- Replica thứ ba đã nhận mutation chưa?
- Failover chỉ một node hay nhiều node nối tiếp?
- Có active promotion và rebalance giữa các lỗi không?

Test report phải ghi **fault timeline và replica state**, không chỉ số node bị dừng.

## 13. Persistence levels: kiểm thử disk I/O riêng với lỗi quorum

Với `MAJORITY_AND_PERSIST_TO_ACTIVE` hoặc `PERSIST_TO_MAJORITY`, lab phải dùng **Couchbase bucket** có persistence được hỗ trợ; Ephemeral bucket không đáp ứng hai mức này.

| Kịch bản | Biến được tác động | Bằng chứng |
|---|---|---|
| `MAJORITY`, replica khỏe | Xác nhận replication trong bộ nhớ | KV p95/p99 và success |
| `MAJORITY`, replica mất | Khả năng đạt quorum | Lỗi/timeout theo vBucket liên quan |
| `MAJORITY_AND_PERSIST_TO_ACTIVE` | Thêm persistence trên active | Disk latency active |
| `PERSIST_TO_MAJORITY` | Persistence trên majority | Disk latency active/replica |
| Ephemeral + persist level | Level không được hỗ trợ | Lỗi cấu hình, không retry mù |
| Restart node giữ disk | Recovery từ local storage | Khả năng phục hồi theo engine, không phải DR |

Không đồng thời đổi durability, giảm tốc disk và cô lập node; khi đó không phân biệt được thiếu quorum với nghẽn persistence. Giữ cùng document size, concurrency và key distribution để so sánh p95/p99.

### 13.1. Không có latency cố định cho mỗi level

`PERSIST_TO_MAJORITY` có thể chậm hơn `MAJORITY` vì phải đợi disk trên nhiều bản, nhưng không có tỷ lệ “chậm gấp N lần” chung cho mọi cluster. Quan sát disk I/O, mạng giữa Data nodes và pending writes dưới tải đại diện.

## 14. Hard failover, graceful failover, recovery và rebalance

| Sự kiện | Trạng thái cần chứng minh | Không được suy ra |
|---|---|---|
| Dừng node/process | Node không phản hồi | Cluster đã tự failover |
| Hard failover | Node bị loại khỏi membership; replica có thể promote | Dữ liệu tự có đủ replicas ngay |
| Graceful failover | Chuyển vai trò có kế hoạch | Giống hệt crash đột ngột |
| Automatic failover | Cluster tự failover theo policy | Không cần kiểm tra `maxCount`/quorum |
| Node recovery | Node trở lại theo protocol | Dữ liệu cũ trên node tự trở thành authoritative |
| Rebalance | Data owners/copies được phân phối lại | Recovery của backup lịch sử |

**Dừng Data process và failover là hai sự kiện khác nhau.** Nếu muốn đo RTO của failover, ghi lại cả mốc mất node, mốc Cluster Manager xác nhận failover và mốc API phục vụ lại.

### 14.1. Phục hồi API chưa đồng nghĩa phục hồi redundancy

Ví dụ: active A mất, replica B được promote, SDK đã đọc/ghi được trở lại. Nhưng số bản dự phòng có thể chưa bằng lúc khỏe. Cần phân biệt:

- `T_api_recovery` — API đạt mức phục vụ tối thiểu.
- `T_replica_restoration` — sau recovery/rebalance, vBucket copies đạt mục tiêu.

Hai mốc có thể cách nhau đáng kể. Thí nghiệm phải báo cáo cả hai.

### 14.2. Fault nhiều node là một scenario khác

Tài liệu Couchbase cảnh báo mutation được majority ack vẫn có thể mất nếu **toàn bộ Data nodes giữ majority của mutation đó bị failover trước khi bản thứ ba bắt kịp**. Chỉ thử negative scenario này ở lab hủy được, có phê duyệt riêng; không bắt hệ thống production “chứng minh” bằng cách failover hai node.

Nếu edition hỗ trợ, xem xét `maxCount` và `failoverPreserveDurabilityMajority`. Không tự vô hiệu hóa policy để tạo hiệu ứng.

## 15. Kiểm tra trạng thái cluster bằng nguồn read-only

DBA/SRE nên cung cấp dashboard, snapshot hoặc REST read-only khi phù hợp. Tầng ứng dụng không cần credential admin.

| Thuộc tính | Dùng để trả lời |
|---|---|
| Bucket type | Có hỗ trợ mức yêu cầu persistence không? |
| `replicaNumber` | Bao nhiêu Data replicas mong muốn? |
| Actual vBucket map | Active/replica của các key test đang ở node nào? |
| Data node count | Có đủ host để đặt các bản không? |
| Server Groups | Copies có tách failure domain không? |
| Minimum bucket durability | Server có thực thi level mạnh hơn client không? |
| Fallback state | Success có thể bị suy giảm thành active ack không? |
| Auto-failover policy | Failover có tự xảy ra không, giới hạn bao nhiêu? |
| Rebalance status | Cluster đã hoàn tất phân bố lại chưa? |

Ví dụ endpoint đọc bucket trên server self-managed:

~~~text
GET /pools/default/buckets/commerce_test
~~~

Tên field và API có thể khác tùy version/managed deployment. Không đưa admin password vào logs, ví dụ code hoặc artifact chia sẻ; trên Capella dùng API/console được cung cấp. Không lấy một vBucket khỏe đại diện cho toàn bucket.

## 16. Java SDK: một baseline JUnit test, chưa phải fault injection

Ví dụ Java SDK 3.x với `orders` đã được bootstrap trỏ tới `commerce_test.sales.orders`. Không tạo hoặc phá cluster trong đơn vị test này.

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.time.Duration;
import java.util.UUID;
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import org.junit.jupiter.api.Test;

class BaselineDurableWriteTest {
    private final Collection orders;

    // Test framework/fixture phải cung cấp Collection của LAB.
    BaselineDurableWriteTest(Collection orders) {
        this.orders = orders;
    }

    @Test
    void insertAndReadWhenClusterIsHealthy() {
        String id = "lab::baseline::" + UUID.randomUUID();
        String fingerprint = "fp-baseline-42";

        var body = JsonObject.create()
            .put("fingerprint", fingerprint)
            .put("runId", "run-42");

        var ack = orders.insert(
            id, body,
            insertOptions()
                .durability(DurabilityLevel.MAJORITY)
                .timeout(Duration.ofSeconds(8))
        );

        assertNotNull(ack);
        assertEquals(fingerprint,
            orders.get(id).contentAsObject()
                .getString("fingerprint"));
    }
}
~~~

**Giới hạn:** đây là baseline về wiring, mapping KV và requested durability, chưa chứng minh failover/HA. JUnit thuần cần một extension/factory để cung cấp `orders`; nếu dùng Spring Boot Test cần bootstrap bean/constructor phù hợp.

`UUID.randomUUID()` sinh ID cho **một test command mới**, không được sinh lại trong retry của cùng một business command.

## 17. Lưu danh sách mutation đã ack trước fault

Một driver nhỏ có thể tạo bộ dữ liệu xác định:

~~~java
import java.util.ArrayList;
import java.util.List;
import com.couchbase.client.java.json.JsonObject;

record AckedDoc(String id, String fingerprint) {}
List<AckedDoc> acked = new ArrayList<>();

String runId = "run-42";
for (int i = 0; i < 100; i++) {
    String id = "lab::" + runId + "::before::" + i;
    String fp = runId + "::fp::" + i;
    JsonObject body = JsonObject.create()
        .put("runId", runId)
        .put("fingerprint", fp)
        .put("status", "ACKED_BEFORE_FAULT");

    orders.insert(id, body,
        insertOptions().durability(DurabilityLevel.MAJORITY));
    // Chỉ thêm sau khi SDK đã trả SUCCESS rõ ràng.
    acked.add(new AckedDoc(id, fp));
}
~~~

Lưu `acked` vào một artifact test đáng tin **ngoài Couchbase bucket đang chịu fault**, kèm thời điểm, outcome và requested durability. Nếu attempt timeout/ambiguous, chuyển sang tập `UNKNOWN`; không ghi giả là acked.

### 17.1. Tách ba tập before/during/after

- `before`: đã ack rõ ràng trước fault — kiểm tra survival.
- `during`: ghi khi node có lỗi/failover — kiểm tra availability, timeout, ambiguous.
- `after`: ghi khi recovery/rebalance xong — kiểm tra khả năng khôi phục.

Không lấy số attempts gửi để tính tỷ lệ mutation đã acknowledged.

### 17.2. Đọc lại từng ID, không chỉ đếm tổng document

Sau failover, dùng KV `get(id)` và đối chiếu fingerprint/state cho toàn bộ `acked`. Một query SQL++ đếm rows qua GSI có thể stale; số rows tổng cũng không chứng minh những IDs quan trọng đã tồn tại.

## 18. Spring Data entity và repository trong lab

Một entity dành cho kiểm thử:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document(durabilityLevel = DurabilityLevel.MAJORITY)
@Scope("sales")
@Collection("orders")
public class LabOrderDocument {
    @Id private String id;
    @Version private Long version;
    private String runId;
    private String fingerprint;
    private String status;
    // Constructors/getters/setters lược bỏ.
}
~~~

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface LabOrderRepository
        extends CouchbaseRepository<LabOrderDocument, String> {
}
~~~

~~~java
LabOrderDocument saved = repository.save(order);
LabOrderDocument again = repository.findById(saved.getId())
    .orElseThrow();
~~~

`@Document(durabilityLevel = MAJORITY)` mô tả default khi đi qua metadata mapping. `@Version` dùng CAS, không phải durability. `findById` dùng KV theo ID, không cần GSI.

### 18.1. Override một mutation qua CouchbaseTemplate

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;

LabOrderDocument saved = template
    .insertById(LabOrderDocument.class)
    .withDurability(DurabilityLevel.PERSIST_TO_MAJORITY)
    .one(order);
~~~

Ví dụ chọn level cho **operation cụ thể**. Nó không tự tăng replica count hoặc khiến Ephemeral bucket có persistence.

### 18.2. Đừng trộn semantics các đường ghi

- `repository.save`: CRUD abstraction và metadata mapping.
- `template.insertById`: create-only.
- `template.upsertById`: có thể tạo hoặc ghi đè theo semantics API.
- SDK `orders.insert(id, JsonObject)`: không tự đọc Spring entity annotation.

Nếu test fallback/error translation, cần biết code path nào đang gọi server. Một failure test cho SDK direct call không chứng minh repository có cùng exception class.

## 19. Orchestrator và test driver: hai trách nhiệm tách biệt

~~~mermaid
sequenceDiagram
    participant QA as QA Test Driver
    participant SRE as SRE Lab Orchestrator
    participant CB as Couchbase Lab
    participant Evidence as Evidence Store
    QA->>CB: before writes, requested durability
    CB-->>QA: success/error
    QA->>Evidence: Lưu ACKED IDs + fingerprints
    QA->>SRE: READY_FOR_FAULT(runId)
    SRE->>CB: Trigger MỘT fault được phê duyệt
    CB-->>SRE: Node/failover state
    SRE-->>QA: FAULT_OBSERVED(time,node,state)
    QA->>CB: during writes + KV reads
    QA->>Evidence: outcomes, timings, errors
    SRE->>CB: Recovery/rebalance
    SRE-->>QA: RECOVERY_VERIFIED
    QA->>CB: verify ACKED + after writes
    QA->>Evidence: Summary, RPO/RTO, invariants
~~~

**Orchestrator** do DBA/SRE sở hữu, điều khiển node/failover theo runbook. **Test driver** chỉ tạo load có quota, đọc/ghi dữ liệu thử và lưu bằng chứng, không trực tiếp chạy lệnh phá node.

### 19.1. Không đưa hard failover vào JUnit test bình thường

Một `@Test` gọi admin failover có nguy cơ chạy nhầm môi trường khi CI variables sai. Nếu muốn tự động hóa phải dùng công cụ riêng có allowlist môi trường, credentials tách biệt, dry-run, check target, stop conditions và rollback.

### 19.2. Đừng dùng sleep để “xác nhận failover”

`Thread.sleep(5000)` không chứng minh Cluster Manager đã failover node; chỉ transition sang pha “during” khi có evidence từ cluster membership, active owner và event timeline.

## 20. Phân loại kết quả ghi khi node lỗi

| Outcome | Ý nghĩa | Hành động |
|---|---|---|
| SDK success | Operation hoàn tất theo effective level | Vào tập ACKED |
| `AmbiguousTimeoutException` | Có thể đã commit nhưng response mất | Reconciliation, không đổi ID |
| `DurabilityAmbiguousException` | SyncWrite outcome chưa xác định | Không coi rollback chắc chắn |
| `UnambiguousTimeoutException` | SDK xác định request hiện tại không có side effect | Retry có budget nếu business cho phép |
| `DurabilityImpossibleException` | Không thể đáp ứng level/topology | Kiểm tra replicas, không hạ level tự động |
| `DurabilityLevelNotAvailableException` | Level không được server/bucket hỗ trợ | Sửa support/config |
| `DocumentExistsException` | Insert gặp ID đã tồn tại | Đọc/so fingerprint |
| `CasMismatchException` | CAS cũ, có update khác | Đọc lại và đánh giá state |
| `DurableWriteInProgressException` | Key có pending SyncWrite | Backoff giới hạn, kiểm tra hot key |

SDK exceptions có thể được Spring Data dịch/bọc, nên repository integration tests phải xem abstraction và cause chain của phiên bản đang dùng.

### 20.1. Client timeout không phải database rollback

Nếu gateway trả 504, hoặc WebFlux `Mono.timeout` hủy subscription, server có thể vẫn commit mutation đã dispatch. Phân loại này phải có mặt trong báo cáo, không gộp tất cả timeout thành “write thất bại”.

### 20.2. Viết expected outcomes theo fault

Nếu 1 replica bị lỗi trong bucket 1 replica và không có fallback, một kết quả **không thể đạt majority** là expected failure của durability. Ngược lại, một success được ghi khi fallback bật **không chứng minh đã đạt majority** và phải được gắn trạng thái suy giảm bảo đảm.

## 21. Đối soát sau failover bằng stable ID và fingerprint

Một request tạo order trong lab có:

~~~text
Idempotency-Key: run-42-checkout-abc
Stable key:
tenant::lab::checkout::run-42-checkout-abc
Fingerprint:
hash(canonical business request)
~~~

Nếu lần đầu `insert` nhận timeout ambiguous, server **có thể đã commit** trước khi response mất. Nếu retry với key khác, có thể tạo hai documents. Trình tự đúng:

1. Giữ nguyên `Idempotency-Key` và document ID.
2. Đọc KV theo đúng bucket/scope/collection.
3. Nếu document hiện hữu, so tenant, checkout ID, fingerprint và trạng thái.
4. Nếu khớp, ghi nhận business command đã có record phù hợp; vẫn đối chiếu side effects bên ngoài.
5. Nếu khác fingerprint, báo conflict và điều tra.
6. Nếu đọc chưa thấy hoặc Data Service chưa phục vụ, **không suy chắc mutation sẽ không commit**.
7. Giới hạn retry/backoff và đưa outcome chưa rõ vào reconciliation.

### 21.1. Java SDK: phân biệt ba trạng thái đọc lại

~~~java
import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.java.Collection;

enum ReadbackState {
    MATCHED, NOT_VISIBLE_AT_CHECK, DIFFERENT_CONTENT
}

ReadbackState checkAfterFault(
        Collection orders, String id, String expectedFingerprint) {
    try {
        var json = orders.get(id).contentAsObject();
        return expectedFingerprint.equals(
                    json.getString("fingerprint"))
            ? ReadbackState.MATCHED
            : ReadbackState.DIFFERENT_CONTENT;
    } catch (DocumentNotFoundException e) {
        // Không đồng nghĩa rằng một SyncWrite pending
        // chắc chắn sẽ không commit trong tương lai.
        return ReadbackState.NOT_VISIBLE_AT_CHECK;
    }
}
~~~

**Giới hạn mẫu:** timeout kết nối/read failure khác `DocumentNotFoundException` không được chuyển thành NOT_VISIBLE; phải propagate hoặc ghi nhận `UNAVAILABLE` trong workflow. Mẫu này không xác minh persistence/quorum của mutation đã từng ambiguous; nó chỉ kiểm tra **nội dung hiện quan sát được**.

### 21.2. Cùng key nhưng payload khác không được trả thành công

Nếu `insert` retry gặp `DocumentExistsException`, việc trùng key không tự chứng minh đó là cùng order. Fingerprint giúp phát hiện tái sử dụng idempotency key cho lệnh nghiệp vụ khác. Hash phải từ canonical representation, không dựa vào thứ tự trường JSON tùy ý.

### 21.3. Đối soát các sự kiện bên ngoài

Nếu một checkout gọi payment gateway hoặc gửi event Kafka, cần idempotency tại bên ngoài và tham chiếu giao dịch rõ ràng. Couchbase mutation durable **không tự bảo đảm** charge chỉ xảy ra một lần.

## 22. Reactive test: không nhân request khi subscriber retry

Một mutation reactive:

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;
import com.couchbase.client.java.kv.MutationResult;
import reactor.core.publisher.Mono;

Mono<MutationResult> create = orders.reactive().insert(
    stableOrderId,
    body,
    insertOptions().durability(DurabilityLevel.MAJORITY)
);
~~~

Publisher tạo operation khi subscribe. Nếu gắn `retryWhen`, subscription mới có thể gửi lại mutation khi attempt trước đã tới server.

### 22.1. Mẫu không an toàn

~~~java
Mono<?> unsafe = Mono.defer(() ->
    orders.reactive().insert(
        java.util.UUID.randomUUID().toString(),
        body,
        insertOptions().durability(DurabilityLevel.MAJORITY)
    )
).retryWhen(reactor.util.retry.Retry.max(3));
~~~

`Mono.defer` có thể sinh ID mới sau mỗi retry. Một lần insert commit nhưng response thất lạc có thể tạo nhiều order. Không dùng ví dụ này cho hệ thống thật.

### 22.2. Chỉ retry nhóm lỗi đã xác định an toàn

~~~java
String stableId = "tenant::lab::checkout::run-42-checkout-abc";

Mono<MutationResult> controlled = orders.reactive().insert(
    stableId,
    body,
    insertOptions().durability(DurabilityLevel.MAJORITY)
).retryWhen(
    reactor.util.retry.Retry.backoff(
        2, java.time.Duration.ofMillis(150)
    ).filter(error ->
        error instanceof
            com.couchbase.client.core.error.UnambiguousTimeoutException
    )
);
~~~

Đây là ví dụ minh họa, không phải retry policy đầy đủ. Production cần tổng deadline, concurrency cap, SDK exception classification, monitoring và reconciliation cho ambiguous. `Mono.timeout` có thể ngừng đợi tại subscriber nhưng không bảo đảm DB mutation đã bị rollback.

### 22.3. Backpressure không tạo quorum

Giảm concurrency có thể giảm queue và timeout khi cluster quá tải. Nhưng khi bucket một replica mất một Data node, backpressure không tạo bản thứ hai cần cho majority 2/2.

## 23. CAS và update cạnh tranh trong failure drill

Ngoài survival của insert, cần kiểm tra update không ghi đè ngoài ý muốn.

~~~text
T0: order.status=NEW, CAS=V1
T1: A đọc V1 và muốn chuyển PAID
T2: B đọc V1 và muốn chuyển CANCELLED
T3: A replace CAS V1 -> có thể commit
T4: A mất response khi node failover
T5: B replace CAS V1 -> có thể mismatch
~~~

Ví dụ SDK:

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

var previous = orders.get(orderId);
var current = previous.contentAsObject();

if (!"NEW".equals(current.getString("status"))) {
    throw new IllegalStateException("Invalid state transition");
}

orders.replace(
    orderId,
    current.put("status", "PAID"),
    replaceOptions()
        .cas(previous.cas())
        .durability(DurabilityLevel.MAJORITY)
);
~~~

Test phải xác minh:

- Writer dùng CAS V1 cũ không ghi đè một update khác đã commit.
- Nếu CAS mismatch sau timeout, đọc lại và so business command ID trước khi kết luận.
- Không bỏ CAS hoặc `upsert` mù quáng để “vượt lỗi”.
- Nếu bất kỳ attempt nào ambiguous, đưa vào reconciliation, không giả định rollback.

### 23.1. Durability, CAS và transaction độc lập

`DurabilityLevel` đặt mức xác nhận mutation; CAS bảo vệ optimistic concurrency một document; Couchbase Transactions quản lý atomicity nhiều document theo semantics riêng. Một transaction còn có timeout/retry/commit status cần được kiểm thử riêng, nhất là khi callback có thể chạy lại.

Không phát email, Kafka event hoặc charge gateway không idempotent bên trong callback transaction có thể retry.

## 24. SQL++/GSI lag: tránh kết luận mất dữ liệu sai

Index Service nhận thay đổi từ Data Service qua DCP bất đồng bộ. Ngay cả khi `orders.insert(... MAJORITY)` success, SQL++ query `NOT_BOUNDED` theo `status` có thể chưa thấy row vừa ghi.

~~~text
KV get(orderId)      : document hiện có.
SQL++ WHERE status=X : có thể chưa phản ánh ngay.
~~~

Trong thí nghiệm failover:

- **KV get theo ID** là phương án chính để soát các `ACKED` documents.
- SQL++ theo field kiểm thử **Query/Index availability và freshness**, là phép đo phụ riêng.
- `REQUEST_PLUS` có thể chờ index bắt kịp mốc query; có thể tăng query p99 hoặc timeout.
- `consistentWith(MutationState)` dùng token đã biết, không giúp khi mutation ambiguous và không có token thành công.
- `PERSIST_TO_MAJORITY` không buộc GSI cập nhật trước mutation response.

### 24.1. Đừng dùng row count làm bằng chứng duy nhất

Nếu tập before có 100 IDs đã ack, một câu `SELECT COUNT(*)` trả 100 chưa chứng minh đúng 100 IDs đó còn tồn tại; một số record khác có thể bù vào số đếm. Kiểm tra **ID và fingerprint của từng record**.

### 24.2. Sau failover, lỗi SQL++ có thể độc lập với Data Service

Query/Index nodes có thể rollback/rebuild index snapshot hoặc đợi DCP bắt kịp. Không tăng write durability để sửa Query Service lag; đo và điều tra hai đường riêng.

## 25. Checklist quan sát theo từng pha

| Pha | Bằng chứng tối thiểu phải lưu |
|---|---|
| **PREPARE** | Environment ID, cluster version, bucket type, replica count, actual placement, fallback off, owner/approval |
| **BASELINE** | Tập ACKED, fingerprints, success/error counts, KV p95/p99, healthy replica status |
| **INJECT** | Fault kind/target/time, xác nhận target chỉ thuộc lab, orchestrator identity |
| **OBSERVE** | Node/vBucket state, request IDs, outcomes, ambiguous/errors, write availability, HTTP p99 |
| **RECOVER** | Thời gian node phục hồi, failover/rebalance events, disk/network status |
| **VERIFY** | Tập ACKED trước fault còn đúng, unknown outcomes được đối soát, duplicate count, replicas đã đủ |
| **REPORT** | RPO/RTO thực đo, điểm chưa chứng minh, hành động cải tiến, owner |

### 25.1. Mẫu log không lộ bí mật

~~~text
experiment=run-42
phase=DURING
timestamp=2026-11-25T03:10:00Z
service=order-api-test
keyspace=commerce_test.sales.orders
operation=INSERT
documentKeyHash=masked
requestedDurability=MAJORITY
effectiveBucketMinimum=noted-in-test-charter
outcome=AMBIGUOUS
exceptionClass=AmbiguousTimeoutException
elapsedMs=...
attempt=1
reconciliationState=OPEN
~~~

Các trường là **schema logging đề xuất**, không khẳng định SDK tự phát tất cả. Không ghi password, payment token, PII hoặc nguyên document body vào log.

### 25.2. SLI cần chia theo operation và level

Đo riêng `insert`, `replace`, `remove` và có thể sub-document mutations. Một p99 tổng có thể che lỗi chỉ xuất hiện ở `PERSIST_TO_MAJORITY` hoặc một key nóng. Khi fault, phân tách theo pha và loại lỗi; không gộp success, timeout và CAS conflict.

## 26. Kỳ vọng và giới hạn kết quả theo mức durability

| Điều quan sát | Kết luận có thể bảo vệ | Kết luận không được đưa ra |
|---|---|---|
| `MAJORITY` write success, trước fault | Operation đã được ack theo level hiệu lực | Mọi replica đều đã persist |
| Một replica lỗi, write 2/2 không thành công | Cluster không xác nhận được required majority | Mọi tài liệu đã ack trước đó đều mất |
| 2 replicas, một bản mất, write có thể thành công | Có thể vẫn đạt 2/3 khi điều kiện phù hợp | Chắc chắn chịu được hai node loss |
| `PERSIST_TO_MAJORITY` p99 cao | Có phụ thuộc persistence trên majority | Bắt buộc phải hạ level |
| HTTP 504 sau active failover | Caller chưa nhận confirmation | Mutation chắc chắn không commit |
| KV get thấy record | Document hiện quan sát được | Ghi ambiguous trước đó chắc chắn đã đạt mức yêu cầu khi fallback có thể bật |
| SQL++ `NOT_BOUNDED` chưa thấy row | GSI có thể stale | Durable write chắc chắn thất bại |
| Rebalance completed | Hoàn tất thao tác quản trị được báo | Mọi business command đã được đối soát |

### 26.1. Lỗi là một kết quả mong đợi

Khi thiếu majority và fallback tắt, việc **không trả success trái với hợp đồng** chính là hành vi cần xác minh. Đừng chấm test đỏ chỉ vì API không nhận mutation trong fault mà cluster không thể bảo vệ.

### 26.2. Sự hiện diện sau test không chứng minh mọi failure mode

Nếu document còn sau một node restart giữ disk, thí nghiệm không chứng minh khả năng phục hồi khi toàn host/disk mất. Viết giới hạn cụ thể trong báo cáo.

## 27. Ma trận bài test được đề xuất

| ID | Tên test | Cấu hình | Assertion quan trọng |
|---|---|---|---|
| F01 | Baseline majority | 2 Data nodes, 1 replica | Ghi/đọc KV thành công khi khỏe |
| F02 | Replica mất khả dụng | 1 replica, quorum 2/2 | Không âm thầm xác nhận ghi thiếu majority |
| F03 | Một replica tạm lỗi | 2 replicas, quorum 2/3 | Quan sát đường ghi có thể đủ majority |
| F04 | Active lỗi giữa pending write | 2 replicas, one active fault | Ambiguous/retry/idempotency đúng |
| F05 | Graceful failover bảo trì | Lab theo runbook | RTO/owner chuyển, không đếm như hard crash |
| F06 | Rebalance recovery | Thêm/recover Data node | Replica placement đạt mục tiêu |
| F07 | Disk latency | Couchbase bucket, persist level | p99 và timeout theo storage |
| F08 | Duplicate after response loss | Stable ID, giả lập response drop | Không tạo hai order một command |
| F09 | CAS conflict sau failover | Hai writers dùng CAS V1 | Không ghi đè business state trái phép |
| F10 | Bucket minimum | Client level yếu hơn minimum | Không suy rằng effective level bằng yêu cầu yếu |
| F11 | Unsupported replica count | Bucket 3 replicas | Không hỗ trợ Sync Writes theo docs hiện hành |
| F12 | SQL++ index lag | KV success, GSI query | Không chẩn đoán nhầm dữ liệu mất |
| F13 | Fallback mode (tùy chọn) | Lab riêng, approval | Ghi success có thể bị suy giảm bảo đảm |
| F14 | Backup/restore ngoài cluster | Test restore target riêng | RPO/RTO không bị đánh đồng với failover |
| F15 | Two-majority-nodes failure | Lab hủy được, approval riêng | Ghi rõ nguy cơ mất durable write, không hứa two-node tolerance |

Không cần chạy mọi test trong một lần. Ưu tiên F01–F06, F08 và F09 cho ứng dụng; các bài persistence/DR/multiple-fault cần lab, capacity và người điều phối phù hợp.

## 28. Định nghĩa PASS/FAIL bằng RPO, RTO và business invariants

Một failure drill tốt không chấm PASS chỉ vì tất cả API success hoặc một dashboard màu xanh. Các tiêu chí phải tương ứng **failure scenario**.

### 28.1. Những con số cần đo

| SLI | Cách định nghĩa | Không được nhầm với |
|---|---|---|
| **Acked data survival** | Số document `before` được ack và còn đúng fingerprint sau recovery / tổng `before` đã ack | Tổng attempts gửi |
| **Ambiguous reconciliation coverage** | Số unknown outcomes đã có kết luận/owner / tổng unknown outcomes | Tổng timeout count |
| **Write availability** | Tỷ lệ mutation hoàn tất đúng level trong pha được xác định | TCP connection success |
| **KV mutation p95/p99** | Latency SDK theo operation/level/pha | SQL++ query latency |
| **API recovery time** | Từ fault event tới lúc API đạt tiêu chí phục vụ | Thời điểm Data node reboot |
| **Redundancy restoration time** | Từ fault tới khi replica placements trở về mức yêu cầu | API 200 đầu tiên |
| **RPO theo kịch bản** | Mutation đã acknowledged nhưng mất sau sự cố cụ thể | Snapshot backup age duy nhất |
| **RTO theo kịch bản** | Thời gian hoàn thành mức phục vụ đã cam kết | “Một node đã Online” |

### 28.2. Ví dụ acceptance criteria — chỉ minh họa

~~~yaml
experimentId: run-42
failureScenario: one-data-node-unavailable
requiredDurability: MAJORITY
criteria:
  preFaultAckedDocuments:
    survivingExpected: all
    verifyWith: KV-by-id-and-fingerprint
  duplicateBusinessCommands:
    allowed: 0
  ambiguousOutcomes:
    eachMustHave: resolved-or-reconciliation-owner
  writeAvailabilityDuringFault:
    expected: based-on-vbucket-quorum
  serviceRecoveryTarget:
    measuredNotAssumed: true
  redundancyRestored:
    requiredBeforeClosingExperiment: true
  stopOnUnexpectedSecondNodeFailure: true
~~~

Các giá trị như “survivingExpected: all” chỉ có nghĩa khi failure scenario thực sự nằm trong phạm vi bảo vệ và không có fallback làm yếu hợp đồng. Không áp tiêu chí đó cho bài thử cố ý làm mất cả majority hoặc bucket không replica.

### 28.3. Đừng cộng p99 theo cách sai

HTTP API có thể gồm nhiều KV operations, queueing và validation. p99 HTTP không bằng tổng p99 của từng bước theo một công thức chắc chắn, vì các phân phối có tương quan khác nhau. Đo **end-to-end** và ghi request ID để phân tích.

## 29. Stop, rollback và đóng thí nghiệm

### 29.1. Stop conditions ở thời điểm chạy

Người điều phối cần dừng khi:

- Fault ảnh hưởng cluster ngoài allowlist lab.
- Node thứ hai mất ngoài kế hoạch.
- Monitoring bị mất hoặc không còn phân biệt được thời điểm sự kiện.
- Disk/network/CPU chạm ngưỡng nguy hiểm theo runbook.
- Khôi phục node không thành công trong giới hạn phê duyệt.
- Tỷ lệ errors/unknown outcomes vượt ngưỡng điều tra an toàn của lab.
- Có nghi vấn test runner đang gửi business side effect tới dịch vụ thật.

### 29.2. Rollback không phải chỉ restart node

Phục hồi đầy đủ có thể gồm:

1. Gỡ network fault, đưa Data service trở lại theo runbook.
2. Xác minh node membership và active vBucket owner.
3. Thực hiện recovery/rebalance nếu node từng bị failover.
4. Kiểm tra số replicas và vị trí actual của các vBuckets.
5. Đợi health của Data Service và disk/network về baseline phù hợp.
6. Chạy lại smoke test ghi/đọc theo durability level.
7. Đối soát những `UNKNOWN_OUTCOME` trước khi xóa test data.
8. Chỉ dọn dữ liệu và đóng experiment sau khi lưu evidence độc lập.

Nếu cluster không thể phục hồi bằng kế hoạch hiện có, **dừng công việc mở rộng và escalation**, không lặp lại destructive steps để “thử may”.

### 29.3. Kết thúc thí nghiệm cần ba trạng thái riêng

- **Fault stopped:** đã chấm dứt nguyên nhân gây lỗi.
- **Service recovered:** API đáp ứng tiêu chí phục vụ.
- **Data and redundancy verified:** dữ liệu đã ack được đối soát và bản sao đạt cấu hình.

Chỉ trạng thái thứ ba mới đủ để đóng một durability failure drill đúng nghĩa.

## 30. Case study A — replica mất, test driver tưởng toàn bộ ghi phải thành công

**Môi trường:** bucket một replica trên hai Data nodes, majority 2/2. QA dừng node giữ replica trong lab. KV get một số ID vẫn có thể phản hồi qua active.

**Kết quả:** những writes cần `MAJORITY` trên vBucket bị ảnh hưởng không đạt quorum, SDK báo timeout hoặc durability failure. Một kiểm thử viết `assertSuccessForAllWrites()` sẽ FAIL.

**Phân tích đúng:** đây là expected behavior nếu không thể đạt majority; không được coi “vì ứng dụng còn đọc được nên ghi cũng phải luôn thành công”.

**Cải tiến:**

1. Tách kiểm thử **before-acked survival** và **during-fault write availability**.
2. Không bật fallback hoặc tự hạ level chỉ để làm assertion thành công.
3. Ghi tỷ lệ failures theo loại, xác minh SRE phục hồi replica/rebalance.
4. Chỉ đánh giá RPO của writes đã ack rõ ràng trong failure scenario phù hợp.

**Kết luận:** Thử nghiệm đã làm rõ giới hạn availability, không phải chứng minh Couchbase kém bền.

## 31. Case study B — ba Data nodes nhưng test nhầm topology

**Môi trường:** cluster hiển thị ba nodes: A chạy Data, B chạy Query, C chạy Index. Bucket có `replicaNumber=2` trong metadata.

**Sai lầm:** QA nghĩ có active + hai replicas, nên dừng A để kiểm thử failover. Nhưng chỉ có một Data node thật sự, không đủ places cho replicas.

**Hậu quả:** không thể dùng kết quả để đánh giá majority 2/3 hoặc bảo vệ lỗi một Data node. Thí nghiệm ban đầu **không hợp lệ về preflight**.

**Cải tiến:**

- Kiểm tra service assignment, active/replica vBucket placement trước khi inject.
- Dùng ba Data nodes độc lập cho test bucket hai replicas.
- Xác minh rebalance hoàn tất và không còn under-replicated vBuckets.
- Ghi rõ cluster/tier/version/edition, không chỉ count nodes.

**Kết luận:** Nếu điều kiện đầu vào không đúng thì “PASS/FAIL” đều không có giá trị học thuật cho kịch bản đã định.

## 32. Case study C — timeout ambiguous tạo hai đơn

**Môi trường:** một order `insert` `MAJORITY` đã commit nhưng response mất trong lúc Data node failover. API trả timeout. Caller sinh checkout ID mới, gọi lại; insert thứ hai thành công.

**Hậu quả:** hai order cùng một business action; nếu có payment gateway thật, có thể còn dẫn tới double charge.

**Sửa thiết kế:**

1. Client giữ `Idempotency-Key` xuyên mọi HTTP retries.
2. Server tính stable document ID theo tenant + checkout ID.
3. Dùng `insert` create-only, duplicate thì KV read và so fingerprint.
4. Nếu ambiguous chưa xác minh, giữ reconciliation với owner và SLA.
5. Gateway payment dùng idempotency của chính gateway; không charge lại chỉ vì Couchbase timeout.
6. Thêm fault injection “drop response sau commit” trong lab để kiểm tra contract.

**Kết luận:** Dữ liệu bền ở server không bảo đảm caller luôn biết kết quả, nên idempotency là phần bắt buộc của correctness.

## 33. Case study D — success xuất hiện khi thiếu majority vì fallback

**Môi trường:** một lab được cấu hình `durabilityImpossibleFallback` có chủ đích. Bucket một replica, một Data node failover. Một số mutations yêu cầu `MAJORITY` được server báo success trong trạng thái không đủ majority.

**Sai lầm:** ghi báo cáo “Couchbase vẫn đáp ứng `MAJORITY` khi mất replica”.

**Đúng hơn:** Trong chế độ fallback, server có thể báo success với bảo đảm **yếu hơn majority**. Cần gắn mọi kết quả vào trạng thái policy và không sử dụng chúng làm bằng chứng Sync Writes đã đạt quorum.

**Runbook phải có:** owner RPO, thời hạn bật, audit, cảnh báo, hậu kiểm các writes trong cửa sổ suy giảm và cách tắt fallback sau khi redundancy phục hồi.

**Kết luận:** Availability tốt hơn có thể được mua bằng rủi ro mất dữ liệu cao hơn; nếu không ghi nhận policy, kết luận của test sai ngay từ đầu.

## 34. Bài tập thực hành và câu hỏi phỏng vấn

### A — thiết kế preflight

Hãy viết danh sách 10 thông tin cần thu thập trước khi dừng một Data node trong lab. Nêu **hai lý do phải từ chối chạy** dù developer muốn nhanh chóng nhìn thấy lỗi.

### B — tính majority

Điền majority cho bucket có 0, 1 và 2 replicas. Với 3 replicas, vì sao không được tự áp công thức 3/4 rồi kết luận Sync Writes được hỗ trợ?

### C — topology

Cluster có ba node nhưng chỉ hai node chạy Data Service. Bucket đặt hai replicas. Bài thử “mất một node và còn 2/3” có hợp lệ không? Cần sửa gì?

### D — trước/trong/sau fault

Tại sao test phải lưu nhóm `before` đã ack, `during` và `after` riêng? Một timeout ambiguous có được tính vào nhóm `ACKED` không?

### E — failover khác restart

Node Data dừng 30 giây rồi quay lại. Vì sao bạn không thể gọi đây là hard failover nếu không có evidence về membership và replica promotion?

### F — thử một replica

Trong bucket một replica, majority cần hai copies. Nếu replica không khả dụng, vì sao `get(id)` vẫn có thể hoạt động còn `insert(MAJORITY)` lỗi?

### G — thử hai replicas

A active, B/C replica, mutation M được ack trên A+B còn C chưa có. Hai node nào mất nối tiếp có thể khiến M mất? Đây là giới hạn gì của majority?

### H — Java SDK

Viết một test `insert(... MAJORITY)` rồi `get(id)` để kiểm tra baseline. Vì sao không thể chỉ nhìn test đó để công bố RPO=0 khi failover?

### I — Spring Data

Entity có `@Document(durabilityLevel=MAJORITY)` và `@Version`. Annotation nào liên quan replication, annotation nào liên quan CAS? Đường SDK direct `insert(id, JsonObject)` có kế thừa annotation entity không?

### J — ambiguous timeout

Giả sử `insert` timeout đúng lúc node failover. Một lần KV get trả not-found. Có được tạo ID khác để retry không? Trình bày quy trình reconciliation.

### K — reactive resubscribe

Vì sao `Mono.defer(() -> insert(randomUUID(), body))` kết hợp retry có thể tạo duplicate? Thay bằng stable ID và retry filter thế nào?

### L — Query/Index lag

Sau `insert` success, KV get thấy order nhưng SQL++ `NOT_BOUNDED` chưa thấy. Đây có phải bằng chứng durability thất bại không? Nên dùng gì để xác minh survival?

### M — persistence

Dưới tải tương đương, `PERSIST_TO_MAJORITY` p99 tăng trong lab có disk chậm. Điều này chứng minh điều gì? Có được khuyên giảm durability ngay mà không hỏi RPO không?

### N — stop/rollback

Hãy thiết kế stop conditions và rollback cho fault mất một Data node. Tại sao không được đóng bài test chỉ vì HTTP 200 đã xuất hiện trở lại?

### O — report

Lập mẫu báo cáo gồm: environment, version, fault timeline, client requested level, bucket minimum, fallback state, before-acked data survival, ambiguous reconciliation, API RTO và replica restoration.

## 35. Checklist triển khai failure drill an toàn

- [ ] Có approval, runbook và đúng cluster **lab cô lập**.
- [ ] Không có dữ liệu khách hàng, secret hoặc external payment thật.
- [ ] Biết chính xác Data nodes, services và các failure domains.
- [ ] Xác nhận `replicaNumber` **và actual vBucket placement**.
- [ ] Dùng bucket 0–2 replicas cho Sync Writes theo docs Server hiện hành.
- [ ] Không dùng zero replicas để hứa bảo vệ mất Data node.
- [ ] Kiểm tra Couchbase/Ephemeral bucket trước khi test persistence level.
- [ ] Kiểm tra bucket minimum durability và `durabilityImpossibleFallback`.
- [ ] Ghi rõ target Data node, fault kind, thời lượng tối đa và stop conditions.
- [ ] Tách quyền orchestrator quản trị cluster khỏi test driver ứng dụng.
- [ ] Tạo stable IDs/fingerprints và lưu ACKED evidence ngoài bucket test.
- [ ] Tách dữ liệu `before`, `during` và `after`.
- [ ] Đừng đồng nhất dừng process với failover đã hoàn thành.
- [ ] Đo KV p95/p99, write availability, exceptions, SDK retries và HTTP timeout.
- [ ] Phân loại ambiguous, unambiguous, durability impossible, duplicate và CAS conflict.
- [ ] Không retry bằng ID mới khi mutation outcome chưa rõ.
- [ ] Có reconciliation owner và deadline cho mọi unknown outcome.
- [ ] Kiểm tra survival theo **KV ID + fingerprint**, không chỉ SQL++ count.
- [ ] Phân biệt Query/Index lag với lỗi Data replication.
- [ ] Khi failover xong, kiểm tra service recovery **và** replica restoration.
- [ ] Không bật fallback hoặc hạ durability chỉ để cải thiện biểu đồ success.
- [ ] Không chạy nhiều faults cùng lúc nếu chưa phê duyệt và có baseline.
- [ ] Kiểm thử backup/DR riêng với failover nội cluster.
- [ ] Lưu evidence, giới hạn kết luận, RPO/RTO và actions trong báo cáo.
- [ ] Chỉ đóng experiment sau khi khôi phục node/topology và giải quyết outstanding unknown outcomes.

## 36. Tổng kết

**Kiểm thử lỗi node trong Couchbase phải là một thí nghiệm có kiểm soát, không phải một thao tác phá cụm rồi quan sát xem ứng dụng còn chạy hay không.** Cần có lab cô lập, topology đúng, dữ liệu giả, stop conditions, điều phối của DBA/SRE và nguồn bằng chứng độc lập.

Một bài kiểm thử chất lượng phân biệt rõ **mutation đã được ack trước lỗi**, **mutation mới trong lúc thiếu quorum**, **thời gian khôi phục API** và **thời gian khôi phục redundancy**. Với bucket một replica, majority yêu cầu 2/2; với hai replicas, majority yêu cầu 2/3 nhưng **không bảo vệ mọi chuỗi mất hai Data nodes**. Khi cluster không thể đáp ứng durability, việc không trả success ở mức đã hứa có thể chính là hành vi đúng.

Với **Spring Data Couchbase**, `@Document(durabilityLevel = ...)`, `CouchbaseTemplate.withDurability(...)` và Java SDK mutation options giúp đặt yêu cầu; còn **CAS, idempotency, retry budget, reconciliation, Query/Index consistency và backup/DR** bảo vệ những khía cạnh khác. Kết quả thí nghiệm chỉ có giá trị khi đo chính xác, đối soát đủ và ghi rõ **phạm vi bảo đảm lẫn những failure scenarios chưa kiểm thử**.

## Tài liệu tham khảo chính thức

1. [Couchbase Server — Durability](https://docs.couchbase.com/server/current/learn/data/durability.html): majority/quorum, Sync Writes, failure scenarios, giới hạn replica và auto-failover.
2. [Couchbase Server — Failover](https://docs.couchbase.com/server/current/learn/clusters-and-availability/failover.html): hard/graceful failover, recovery và rebalance.
3. [Couchbase Server — Automatic Failover](https://docs.couchbase.com/server/current/learn/clusters-and-availability/automatic-failover.html): auto-failover policy và điều kiện dịch vụ.
4. [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): mutation options, CAS và durability.
5. [Couchbase Java SDK — Handling Errors](https://docs.couchbase.com/java-sdk/current/howtos/error-handling.html): ambiguous/unambiguous timeout, SDK retry/idempotence.
6. [Spring Data Couchbase — Template and Direct Operations](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): entity default và `withDurability(...)`.
7. [Couchbase Server — Server Group Awareness](https://docs.couchbase.com/server/current/learn/clusters-and-availability/groups.html): placement theo failure domains.
8. [Couchbase Server — Bucket Settings (REST)](https://docs.couchbase.com/server/current/rest-api/rest-bucket-create.html): replica count, minimum durability và fallback trong triển khai hỗ trợ.

Những ví dụ số liệu, thời gian và cấu hình fault đều là minh họa giáo dục. Trước khi áp dụng, phải đối chiếu **phiên bản Couchbase Server/Capella, edition, bucket type, số replica thực tế, Java SDK và Spring Data**; QA học thuật chuyên sâu thuộc STEP 6 riêng, không phải nhiệm vụ ghi Markdown ở STEP 4.




