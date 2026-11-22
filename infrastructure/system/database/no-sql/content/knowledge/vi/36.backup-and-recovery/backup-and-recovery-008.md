# Thời gian lưu, vị trí lưu và bảo vệ bản sao ngoài miền lỗi

Một dịch vụ Java lưu đơn hàng trong NoSQL có ba bản sao dữ liệu trên ba node. Hệ thống còn tạo snapshot mỗi đêm và báo “backup thành công”. Khi một lập trình viên vô tình xóa hàng triệu Order, thao tác xóa được sao chép rất nhanh tới cả ba node. Nhóm vận hành định phục hồi từ snapshot hôm trước, nhưng phát hiện snapshot vẫn nằm trong cùng storage account với database và một tài khoản quản trị bị chiếm quyền đã xóa cả snapshot. Dữ liệu được nhân bản nhiều lần, song **không còn bản sao độc lập để phục hồi**.

Tình huống ấy minh họa ba quyết định bắt buộc phải tách:

1. **Thời gian lưu (retention):** cần giữ bản sao trong bao lâu, với độ hạt phục hồi nào, để chịu được việc phát hiện lỗi muộn?
2. **Vị trí lưu (placement):** bản sao đặt ở volume, node, vùng sẵn sàng, khu vực địa lý, tài khoản và hệ thống lưu trữ nào, nhằm tránh những lỗi chung nào?
3. **Bảo vệ bản sao (protection):** ai có thể đọc, sửa, mã hóa hoặc xóa backup; làm sao xác minh nó còn nguyên vẹn, bất biến theo policy và thực sự có thể restore?

Trong chương **Sao lưu và phục hồi** của module **Database No SQL**, bài học xây dựng chính sách backup theo mục tiêu nghiệp vụ và miền lỗi, phân biệt snapshot, replica, backup, point-in-time recovery (PITR), vùng lưu độc lập và bản sao bất biến. Ví dụ bao gồm cluster tự vận hành, object storage, managed NoSQL, multi-tenant SaaS và những quy trình phục hồi cần được kiểm tra định kỳ.

> **Nguyên tắc trung tâm:** Số lượng bản sao không quan trọng bằng việc mỗi bản sao **có thể phục hồi dữ liệu gì, tại thời điểm nào, dưới những giả định sự cố nào và bằng những danh tính/quyền truy cập nào**. Một bản sao chỉ có giá trị khi đường phục hồi từ nó còn nguyên và đã được kiểm chứng.

## 1. Những khái niệm cần phân biệt trước tiên

| Cơ chế | Mục đích chính | Khả năng bảo vệ | Giới hạn |
|---|---|---|---|
| **Replication** | Availability và chịu lỗi node | Bản sao còn sống khi node hỏng | Xóa nhầm/ghi sai có thể nhân rộng |
| **Local snapshot** | Đóng băng trạng thái tại một mốc | Rollback/backup staging tùy engine | Có thể mất cùng volume hoặc admin |
| **Remote backup** | Lưu bản có thể phục hồi ở đích độc lập | Chịu lỗi theo miền được tách | Phải kiểm upload, consistency, keys |
| **Incremental backup** | Lưu phần thay đổi sau mốc nền | Giảm chi phí sao chép | Phụ thuộc base/chain |
| **PITR** | Khôi phục về mốc trong một khoảng | Hạn chế mất dữ liệu giữa snapshots | Cần log/change history liên tục |
| **Immutable backup** | Chống sửa/xóa trước khi hết hạn | Chống thao tác/hành vi phá hoại trong scope policy | Không chống mất khóa, đọc trái phép hoặc mọi sự cố |
| **Air-gapped/offline copy** | Giảm đường điều khiển liên tục tới backup | Giảm blast radius khi hệ online bị xâm nhập | Có thể tăng RPO/RTO và độ phức tạp |
| **Restore test** | Chứng minh dùng được bản sao | Phát hiện thiếu manifest/key/đường khôi phục | Chỉ chứng minh kịch bản đã thử |

### 1.1. Replica không thay backup

Nếu một lệnh `deleteMany` hợp lệ về mặt cơ chế nhưng sai nghiệp vụ, database sẽ đồng bộ thao tác đó tới các replicas. Replication giúp các node cùng trạng thái mới, **không** lưu một phiên bản trước sự cố để undo.

### 1.2. Snapshot không mặc định độc lập

Snapshot hard-link trong cùng data volume có thể mất khi volume bị xóa. Volume snapshot do cloud provider lưu ngoài volume có thể sống sót trước một số lỗi, nhưng chưa chắc độc lập trước lỗi account, region, quyền admin hay key management.

### 1.3. Backup không nhất thiết phục hồi được tới mọi giây

Một full backup lúc 00:00 chỉ có thể phục hồi tới trạng thái của mốc đó nếu không có transaction/change history để replay. PITR cần được cấu hình, duy trì và xác minh riêng.

### 1.4. “Đã copy file” chưa là “đã có backup”

Một bản chép không consistent với write log, thiếu index metadata, thiếu encryption key hoặc sai engine version có thể không khởi động được. Cần biết thủ tục backup/restore chính thức của sản phẩm.

## 2. Retention, frequency và recovery granularity khác nhau

Ba câu hỏi thường bị nhầm:

~~~text
Backup frequency:
    Bao lâu tạo một restore point?

Retention:
    Mỗi restore point và history được giữ bao lâu?

Recovery granularity:
    Có thể chọn khôi phục tới những mốc nào?
~~~

### 2.1. Ví dụ một snapshot/ngày, giữ 30 ngày

Lúc 03:00 mỗi ngày tạo backup, giữ 30 bản gần nhất. Có thể chọn các mốc hằng ngày; nhưng nếu một lỗi xảy ra lúc 14:00 và không có PITR thì khôi phục bản 03:00 có thể mất những writes sau đó.

### 2.2. Ví dụ full hằng tuần và incremental hằng ngày

Có nhiều restore points hơn, nhưng một incremental phụ thuộc base và những phần lịch sử bắt buộc theo công nghệ backup. Retention phải hiểu dependency graph, không dựa vào tuổi file đơn lẻ.

### 2.3. Ví dụ PITR giữ 7 ngày

Từ snapshot/base và log changes liên tục, hệ có thể hỗ trợ chọn mốc trong bảy ngày gần nhất tùy API. Cần đo được **earliest restorable point** và trạng thái chain thực, không chỉ đọc cấu hình “7 ngày”.

### 2.4. Retention dài chưa bảo đảm RPO tốt

Giữ 5 năm các weekly backups giúp rollback lỗi được phát hiện muộn nhưng không làm độ mất dữ liệu trước một node crash giảm xuống vài giây. Tần suất/capture và durability quyết định RPO.

### 2.5. Backup nhiều chưa bảo đảm RTO tốt

Hàng trăm incremental nhỏ có thể làm restore mất thời gian lâu. RTO phụ thuộc tốc độ tải data, replay log, xây lại indexes, network và validation.

## 3. RPO, RTO và thời gian phát hiện lỗi

**RPO (Recovery Point Objective)** là giới hạn mất dữ liệu theo thời gian được chấp nhận. **RTO (Recovery Time Objective)** là giới hạn thời gian phục hồi chức năng. Cả hai phải được xác định cho sự cố cụ thể, không phải số đo chung của mọi bảng.

### 3.1. RPO không phải backup interval tuyệt đối

Với snapshot mỗi 24 giờ, worst-case data gap có thể gần 24 giờ trong một failure model nhất định, nhưng checkpoint/transaction semantics hoặc replication có thể làm kết quả khác. Đừng hứa RPO 15 phút nếu chỉ có daily snapshots và không có log history phù hợp.

### 3.2. RTO bao gồm cả xác minh

~~~text
RTO =
  detect and declare incident
  + prepare clean environment
  + locate backup and keys
  + download/restore/replay
  + verify consistency and permissions
  + redirect traffic
~~~

Các bước có thể song song; tổng là khái niệm vận hành, không phải một phép cộng cố định cho mọi kịch bản.

### 3.3. Detection lag quyết định retention tối thiểu

Nếu corruption bị phát hiện sau 20 ngày, giữ chỉ 7 ngày history có thể khiến mọi restore point trong window đều chứa dữ liệu hỏng. Retention phải cân nhắc **thời gian phát hiện lỗi nghiệp vụ**, không chỉ thời gian để hệ cảnh báo.

### 3.4. Không có một RPO cho mọi loại lỗi

Mất node có thể phục hồi từ replica gần như liên tục; xóa nhầm dữ liệu cần backup/PITR; ransomware phá account có thể cần immutable/offline copy cũ hơn. Viết RPO/RTO theo threat scenario.

### 3.5. Recovery point cần đo trên ACKed writes

Khi nói “mất 5 phút dữ liệu”, phải xác định những writes đã được xác nhận với caller nhưng không hiện diện sau restore. Đo đó mới gắn với bảo đảm durability.

## 4. Miền lỗi là gì?

**Failure domain** là một nhóm thành phần có thể cùng hỏng vì một sự kiện hoặc một quyền điều khiển chung. Nhiều bản sao đặt trong **cùng một miền lỗi** có thể cùng biến mất.

~~~mermaid
flowchart TD
    ORG["Organization / cloud control plane"] --> ACC1["Production account"]
    ORG --> ACC2["Backup security account"]
    ACC1 --> REG1["Region A"]
    ACC1 --> REG2["Region B"]
    REG1 --> AZ1["Availability Zone 1"]
    REG1 --> AZ2["Availability Zone 2"]
    AZ1 --> HOST["Host / node / volume"]
    ACC2 --> BACK["Protected backup repository"]
~~~

### 4.1. Một số miền lỗi vật lý

Disk, host, rack, power zone, availability zone, data center, region và nhà cung cấp. Mỗi tầng có phạm vi sự cố khác nhau.

### 4.2. Một số miền lỗi logic

Cloud account, IAM organization, admin identity, encryption key, backup scheduler, CI/CD secret, API gateway, DNS và management plane.

### 4.3. Nhiều regions chưa chắc độc lập về bảo mật

Backup ở region B nhưng cùng credentials có quyền `DeleteObject` trên cả hai có thể bị xóa cùng lúc khi credentials bị lộ.

### 4.4. Nhiều accounts chưa chắc độc lập về encryption keys

Nếu mọi bản sao phụ thuộc vào một key có thể bị vô hiệu hóa/xóa từ cùng vai trò admin, backup vẫn có single point of failure về khả năng giải mã.

### 4.5. “Offsite” phải gắn với giả định cụ thể

Đặt object ở bucket khác nhưng vẫn cùng account/region có thể đủ bảo vệ khỏi hỏng volume dữ liệu; chưa chắc đủ với region outage hay account compromise.

## 5. Ma trận sự cố và miền bảo vệ

| Sự cố | Replica cùng cluster | Snapshot cùng volume | Backup khác region | Backup khác account có bảo vệ xóa |
|---|---|---|---|---|
| Hỏng một disk/node | Thường giúp nếu đủ replicas | Có thể mất | Có thể giúp | Có thể giúp |
| Hỏng cả AZ | Phụ thuộc placement | Có thể mất | Có thể giúp | Có thể giúp |
| Region outage | Không nếu cùng region | Không | Có thể giúp | Có thể giúp |
| Xóa dữ liệu nhầm được replicate | Không tự rollback | Có thể có bản cũ | Có thể có bản cũ | Có thể có bản cũ |
| Credentials production bị lộ | Có thể bị tác động | Có thể bị xóa | Có thể bị xóa nếu cùng IAM | Blast radius nhỏ hơn nếu tách thật |
| Backup account/key cũng bị xâm nhập | Không giúp | Không giúp | Có thể bị tác động | Cần immutability/offline/independent controls |
| Dữ liệu lỗi bị ghi từ nhiều tuần trước | Replica có cùng lỗi | Phụ thuộc tuổi snapshot | Phụ thuộc retention | Phụ thuộc retention |

Bảng nói về khả năng bảo vệ, **không cam kết** mọi cloud/service có đúng những bảo đảm này. Trách nhiệm cụ thể phụ thuộc triển khai, cấu hình, chính sách quyền, thời điểm phát hiện và tính toàn vẹn bản sao.

## 6. Quy tắc 3-2-1-1-0: heuristic hữu ích, không phải phép chứng minh

Một cách ghi nhớ chiến lược backup là:

- **3** bản sao dữ liệu (thường tính cả bản production).
- **2** loại media hoặc hệ lưu trữ/đường phụ thuộc khác nhau.
- **1** bản nằm ngoài địa điểm/miền lỗi nguồn.
- **1** bản offline, air-gapped hoặc immutable theo cơ chế được hỗ trợ.
- **0** lỗi chưa được phát hiện trong quá trình xác minh và diễn tập phục hồi.

### 6.1. Không đếm replicas như ba backups độc lập

Ba bản đồng bộ trên cùng hệ có thể cùng nhận lệnh xóa nhầm. Phải xác định copy nào tồn tại ở **lịch sử thời điểm trước lỗi**.

### 6.2. “Hai media” không nhất thiết phải là tape và disk

Mục tiêu là giảm **correlated failure**, chẳng hạn backup repository có control plane/quyền độc lập và một bản offline hoặc WORM. Hai buckets trong một account với cùng role chưa chắc đủ.

### 6.3. “Immutable” không có nghĩa bất khả xâm phạm mọi thứ

Immutability chống sửa/xóa trong phạm vi retention policy và quyền API tương ứng; nó không thay bảo vệ khóa giải mã, kiểm đọc, integrity hay chính sách khóa tài khoản.

### 6.4. Số “0” đòi hỏi restore verification

Checksum thành công là bước tốt nhưng không chứng minh application có thể phục hồi và truy vấn đúng. “Zero unverified errors” nên được hiểu như mục tiêu kiểm chứng, không tuyên bố không thể còn lỗi.

### 6.5. Luôn ưu tiên threat model hơn khẩu hiệu

Một hệ cần đáp ứng mất region có thể chọn hai regions khác nhau; hệ yêu cầu chống ransomware cần tách tài khoản/quyền, WORM và khả năng cấp khóa độc lập. Số lượng copies chỉ là một phần.

## 7. Chính sách theo độ quan trọng dữ liệu

Không nhất thiết giữ cùng retention và tần suất cho mọi loại dữ liệu:

| Nhóm dữ liệu | Rủi ro khi mất | Phương án định hướng |
|---|---|---|
| Đơn hàng/tài chính | Mất nghiệp vụ, tranh chấp | RPO ngắn, recovery history, immutable backup |
| Hồ sơ người dùng | Mất thông tin, rò PII | Backup + quyền truy cập/erasure policy |
| Event/audit ledger | Mất chứng cứ, khó dựng trạng thái | Integrity, retention riêng, append-only controls |
| Search projection | Có thể rebuild từ source | Backup hoặc chiến lược bootstrap nhanh, phụ thuộc RTO |
| Cache/derived recommendations | Có thể tái tạo | Có thể không cần backup bền nếu nguồn đủ |
| Logs phục vụ điều tra | Truy vết/trách nhiệm | Retention theo pháp lý, quyền audit và khóa riêng |

### 7.1. Business value của dữ liệu

Nguồn có thể tái tạo từ source có thẩm quyền khác thì policy khác bản ghi giao dịch không thể phát lại. Nhưng rebuild một search index 10 TB có thể mất nhiều ngày và không đáp ứng RTO, nên có thể vẫn cần snapshot.

### 7.2. Time window của lỗi logic

Một giá sai được ghi tuần trước có thể chỉ được phát hiện sau kỳ kế toán. Cần retention đủ dài để điều tra hoặc có event ledger làm authoritative history.

### 7.3. Không tự giữ vĩnh viễn “cho chắc”

Retention quá dài tạo chi phí, rủi ro rò dữ liệu, nghĩa vụ privacy và phức tạp quản lý keys. Cần policy bảo vệ, lý do pháp lý/nghiệp vụ và lịch hủy.

### 7.4. Policy theo tenant

SaaS có tenants yêu cầu khu vực lưu, retention hoặc mức phục hồi riêng. Không thể dùng một bucket chung vô hạn và giả định đáp ứng tất cả hợp đồng.

## 8. Xây lịch lưu: hourly, daily, weekly, monthly

Một lịch **minh họa**:

~~~text
Recent window:
    hourly restore points for 48 hours

Operational window:
    daily restore points for 30 days

Audit/long-tail window:
    weekly restore points for 12 weeks
    monthly restore points for 12 months
~~~

Đây là giả định để học, không phải mặc định bắt buộc của một hệ NoSQL. Chi tiết retention phải theo mục tiêu phục hồi, dependencies và compliance.

### 8.1. Grandfather–Father–Son (GFS)

GFS giữ bản daily/weekly/monthly thay vì giữ tất cả restore points ở cùng tần suất. Nó giảm số bản giữ lâu nhưng khiến độ hạt phục hồi của lịch sử xa thưa hơn.

### 8.2. Giữ nhiều lịch không tự tạo nhiều copies độc lập

30 daily backups cùng account/region vẫn là một miền lỗi logic và vật lý nhất định. Lịch retention và placement là hai chiều khác nhau.

### 8.3. Mốc giữ phải dựa actual completion time

Một backup “scheduled lúc 02:00” có thể chỉ hoàn tất lúc 04:00; retention và restore point timestamp cần phân biệt schedule, snapshot-consistent time và durable upload-complete time.

### 8.4. Phát hiện corruption muộn

Nếu corruption xảy ra ngày 1 nhưng được phát hiện ngày 22, weekly/monthly backups trước ngày 1 có thể cần thiết. Cần đủ history và công cụ xác định điểm tốt.

### 8.5. Đừng dùng object storage lifecycle xóa mọi thứ theo `lastModified`

Incrementals và full/base có quan hệ phụ thuộc. Nếu lifecycle xóa base trước khi dependent incremental hết hiệu lực, nhiều restore points có thể bị vô dụng.

## 9. Full, incremental và differential có chuỗi phụ thuộc

~~~text
Sunday: Full F0
Monday: Incremental I1
Tuesday: Incremental I2
Wednesday: Incremental I3

To restore Wednesday:
    F0 + required I1/I2/I3 and metadata (implementation dependent)
~~~

### 9.1. Không xóa F0 khi I3 vẫn cần

Một bản full quá tuổi retention nhưng còn là base của incremental phải được giữ hoặc được hợp nhất lại bằng công cụ hỗ trợ.

### 9.2. Differential có semantics khác incremental

Trong mô hình phổ biến, differential chứa thay đổi kể từ full gần nhất; restore cần full + differential mới. Nhưng cách xử lý của backup product cụ thể phải được xác minh.

### 9.3. Incremental tiết kiệm băng thông nhưng tăng RTO

Nhiều layers nhỏ có thể yêu cầu replay/merge phức tạp. Capacity planning phải đo restore toàn chain, không chỉ thời gian upload mỗi incremental.

### 9.4. Synthetic full và chain compaction

Một số hệ hỗ trợ consolidation từ các incrementals thành một base mới. Thao tác này cũng có tài nguyên/consistency và verification riêng, không được giả định copy thủ công đạt kết quả tương tự.

### 9.5. Catalog là nguồn sự thật

Backup inventory cần biết `backupId`, `baseId`, parent dependencies, manifest, scope, data time và restore status. Không chọn file chỉ bằng tên/ngày.

## 10. PITR: muốn giữ theo phút phải có thay đổi liên tục

Một ví dụ:

~~~text
01:00  Consistent base snapshot S
01:00–18:00  Durable change history
13:45  Target point before accidental bulk deletion
14:00  Accidental deletion

PITR to 13:45 requires:
    S + applicable complete changes through 13:45
~~~

### 10.1. Log window là một phần retention

Nếu base snapshot giữ 30 ngày nhưng changes chỉ còn ba ngày, có thể không restore tùy ý một mốc 20 ngày trước. Cần tính **restore chain liên tục**.

### 10.2. Backup và log phải cùng một consistency protocol

Một WAL/oplog/change stream không tự ghép được vào một filesystem copy bất kỳ. Engine/backup tool cần quy tắc checkpoint, transaction boundaries, ordering và compatibility.

### 10.3. Multi-shard transaction

Mỗi shard có stream riêng có thể cần coordination/watermark để chọn mốc consistent. Không lấy wall-clock timestamp tùy ý và replay độc lập như thể toàn cụm có một log tổng.

### 10.4. Cắt retention quá sớm

Nếu xóa một segment log mà một restore point còn cần, tính năng PITR có thể báo không phục hồi được. Cleanup policy phải có dependency awareness.

### 10.5. Earliest restorable timestamp phải được đo

Dashboard nên thể hiện `earliestRestorableAt`, `latestVerifiedRestorableAt`, gaps và trạng thái ingest history, không chỉ con số “PITR enabled”.

## 11. Snapshot nhất quán là điều kiện của backup có giá trị

Trong NoSQL, một ứng dụng có thể cập nhật nhiều documents hoặc partitions trong transaction/workflow.

### 11.1. Crash-consistent vs application-consistent

Snapshot crash-consistent có thể tương đương việc mất điện tại thời điểm chụp và cần WAL replay. Application-consistent thường đòi hỏi engine phối hợp để giảm rủi ro missing/misaligned state.

### 11.2. Một node không đại diện cả cluster

Chụp volume của primary vào lúc 10:00 và secondary lúc 10:10 không tự tạo một ảnh global consistent. Backup multi-node/sharded cluster cần thủ tục vendor-specific.

### 11.3. Các external dependencies

Order ở NoSQL, event ở Kafka và payment state ở service khác không nằm cùng một snapshot vật lý. Khi khôi phục toàn workflow, cần reconcile message offsets, idempotency records và downstream projections.

### 11.4. Xác minh checkpoint

Backup manifest nên lưu source position/consistent timestamp hoặc API-specific token do engine cung cấp, không tự chế từ `System.currentTimeMillis()`.

### 11.5. Khôi phục không chỉ là copy files về đúng chỗ

Schema, indexes, encryption, service account permissions, cluster metadata và client routing cần được phục hồi hoặc tái cấu hình an toàn.

## 12. Tách vật lý: disk, host, AZ, region

### 12.1. Khác disk nhưng cùng node

Bảo vệ được một số lỗi volume, nhưng node hoặc admin xóa toàn host có thể ảnh hưởng cả hai.

### 12.2. Khác node cùng AZ

Giúp trước host failure, song vẫn phụ thuộc power/network/zone và một số control plane chung.

### 12.3. Khác AZ cùng region

Giảm lỗi chung của một AZ; vẫn có rủi ro region-wide outage và account compromise.

### 12.4. Khác region

Giảm rủi ro outage của một region, nhưng phải xét data residency, encryption key availability, chi phí egress, tốc độ restore và dịch vụ hỗ trợ cross-region copy.

### 12.5. Khác provider hoặc offline

Có thể giảm phụ thuộc vào một nhà cung cấp, nhưng tăng công việc bảo đảm format compatibility, network transfer, keys, identity và restore automation. Cần thử restore thực.

## 13. Tách logic: account, tổ chức và danh tính

Một mô hình minh họa:

~~~mermaid
flowchart LR
    APP["Production service credentials"] --> PROD["Production DB/storage"]
    PROD --> BK["Approved backup export role"]
    BK --> REPO["Backup repository in separate account"]
    ADMIN["Backup security admins"] --> REPO
    REST["Scoped recovery operator"] --> REPO
~~~

### 13.1. Application runtime không nên xóa backups

Một API có lỗ hổng injection hoặc lộ environment secrets không nên kéo theo khả năng xóa toàn bộ recovery history.

### 13.2. Backup writer và backup deleter tách quyền

Một vai trò chỉ được tạo/upload có thể giới hạn khả năng xóa bản cũ. Quyền xóa nên được hạn chế và kiểm soát bởi policy; immutable lock có thể thêm một hàng rào.

### 13.3. Tách account chưa đủ nếu root control chung

Nếu một central admin role có thể assume vào cả production và backup account, nó có thể vẫn là single point of compromise. Threat model phải xem toàn IAM trust chain.

### 13.4. Kiểm MFA, break-glass và change approvals

Hành động thay retention, xóa khóa, disable protection hoặc hủy repository cần cơ chế phê duyệt/giám sát phù hợp. Không lưu break-glass credentials ngay trên production host.

### 13.5. Đảm bảo recovery identity tồn tại khi production chết

Trong sự cố account compromise/region outage, người vận hành phải có cách truy cập bản sao và key **mà không phụ thuộc vào hệ thống đã bị mất**.

## 14. Immutability, Object Lock và WORM

**WORM (Write Once Read Many)** hoặc immutable retention giúp chống sửa/xóa bản sao trong một khoảng thời gian được thiết lập.

### 14.1. Hai loại “xóa không được”

Có thể có retention mode được quản trị viên đặc quyền thay đổi/override theo policy và mode chặt hơn mà ngay cả người quản trị cũng không thể rút ngắn trong thời hạn. Semantics cụ thể phụ thuộc nhà cung cấp và cấu hình.

### 14.2. Object versioning không thay immutability

Versioning giúp giữ các phiên bản object khi bị overwrite/delete marker, nhưng nếu cùng credentials có thể xóa vĩnh viễn mọi versions thì vẫn có rủi ro. Retention lock phải được cấu hình đúng scope.

### 14.3. Legal hold khác retention period

Legal hold có thể ngăn xóa độc lập với ngày hết hạn retention. Cần quyền và quy trình gỡ hold riêng, có audit.

### 14.4. Immutability có chi phí

Không thể xóa sớm các backup bị lock khi chi phí tăng, dữ liệu hết nghĩa vụ hoặc policy thay đổi. Lựa chọn khoảng giữ phải cân bằng compliance, privacy và tài chính.

### 14.5. Không bảo đảm không thể đọc trái phép

Immutable backup vẫn có thể bị **đọc** nếu role/keys bị lộ. Encryption, network restrictions và least privilege vẫn cần.

## 15. Offline và air gap: tránh phụ thuộc kết nối liên tục

### 15.1. Logical air gap

Backup repository chỉ chấp nhận writes có phạm vi/đường kết nối kiểm soát, không cho production role xóa hoặc truy cập dài hạn. Đây là tách biệt logic, không luôn là vật lý offline.

### 15.2. Physical offline

Media không luôn gắn mạng làm giảm rủi ro xóa từ production credentials, nhưng tăng độ trễ sao chép/restore, nguy cơ thất lạc vật lý và vận hành thủ công.

### 15.3. Quy trình offline cần kiểm

Media inventory, encryption, custody, kiểm định kỳ, rotation, transport và restore testing. Một băng backup để trong tủ chưa từng thử đọc không phải bằng chứng RTO.

### 15.4. RPO tradeoff

Nếu bản offline được tạo mỗi tuần, nó có thể bảo vệ khỏi ransomware nhưng data gap có thể tới một tuần. Nên kết hợp gần hơn/nhanh hơn ở một lớp khác.

### 15.5. Đừng gọi mọi remote bucket là air gap

Bucket luôn mount/read-write bằng production key không phải air gap theo nghĩa bảo vệ trước compromise của chính key đó.

## 16. Mã hóa dữ liệu khi truyền và khi lưu

### 16.1. In transit

Dùng TLS và authenticated endpoints cho backup transfer, restore API, object storage và control plane. Không dùng URL signed rộng/để lộ trong logs.

### 16.2. At rest

Sử dụng cơ chế encryption được hỗ trợ: provider-managed, customer-managed key hoặc client-side encryption tùy threat model. Cần ghi rõ thuật toán, key provenance và rotation.

### 16.3. Encryption không thay authentication

Kẻ có quyền dùng KMS decrypt và GetObject có thể đọc backup đã mã hóa. IAM và separation of duties là một phần khả năng bảo vệ.

### 16.4. Cross-region key strategy

Một backup được copy qua region có thể cần re-encrypt hoặc key riêng; không tự giả định key ID từ region A có thể giải mã ở B.

### 16.5. Khóa phải sống lâu đủ cho retention

Nếu backup giữ 7 năm nhưng key xóa sau 1 năm, bản sao còn bytes mà không thể restore. Key lifecycle và backup lifecycle phải đồng bộ.

## 17. Key management là một miền lỗi độc lập

### 17.1. Single key failure

Mọi copies cùng dùng một key bị disable/destroy thì không thể giải mã, kể cả copies nằm ở nhiều regions.

### 17.2. Quyền quản lý key

Hạn chế quyền disable/schedule deletion/rotate key và quyền sử dụng decrypt; cần audit, dual-control/break-glass theo policy.

### 17.3. Không ghi raw keys trong backup manifest

Manifest ghi key reference/algorithm/version, không chứa secret materials. Tài liệu restore cần chỉ nơi lấy quyền key an toàn.

### 17.4. Key rotation

Rotation có thể theo cơ chế tự động của KMS hoặc re-encryption; phải đảm bảo old backups vẫn giải mã được. Không assume “rotate xong thì xóa key cũ”.

### 17.5. Mất account và recovery keys

Diễn tập kịch bản cần phục hồi khi production account không dùng được: backup admin phải vẫn xác thực, lấy catalog và keys trong miền độc lập.

## 18. Chống ransomware và thao tác xóa hàng loạt

### 18.1. Ransomware khác lỗi disk

Mã độc có thể sửa dữ liệu nguồn **và** tìm cách xóa backups. Một replica đồng bộ sẽ nhân rộng dữ liệu bị mã hóa nếu ứng dụng ghi hợp lệ.

### 18.2. Bản sao bất biến không nhận sửa sau khi khóa

Đặt immutable retention đúng thời điểm giúp chống xóa/overwrite những bản đó. Nhưng cần phát hiện compromise sớm để tránh mọi restore point tiếp theo đều chỉ chứa dữ liệu hỏng.

### 18.3. Recovery phải sạch

Restore vào môi trường cô lập trước, kiểm credentials, malware, ứng dụng và backup integrity; không khôi phục một tài khoản bị chiếm quyền mà giữ nguyên backdoor.

### 18.4. Tamper-evident audit

Giữ logs backup administration/retention changes trong đường lưu độc lập, có thể kiểm chứng. Một dashboard chỉ báo success nhưng logs cũng bị xóa không đủ điều tra.

### 18.5. Backup identity bị compromise

Phải có runbook để revoke roles, rotate secrets, preserve evidence và ngăn khả năng hủy bản sao còn lại trước khi chuyển sang restore.

## 19. “Backup success” cần nhiều bằng chứng

Một job hoàn thành có thể chỉ nghĩa API chấp nhận yêu cầu. Chu trình xác minh cần:

~~~text
Source consistent checkpoint established
    -> Data and metadata captured
    -> Remote upload completed
    -> Manifest and checksums validated
    -> Encryption/key references recorded
    -> Retention/immutability confirmed
    -> Catalog updated
    -> Periodic isolated restore verified
~~~

### 19.1. Chống partial uploads

Không công bố một backup khả dụng khi một số segments/shards/objects vẫn chưa upload. Catalog chỉ chuyển trạng thái sau khi manifest hoàn chỉnh và các files đều được xác nhận durable.

### 19.2. Checksum chứng minh mức nào?

Checksum có thể phát hiện thay đổi bytes so với bản đã tính, không chứng minh backup consistent hoặc sạch malware. Một checksum lấy sau khi dữ liệu đã hỏng vẫn “đúng” với dữ liệu hỏng.

### 19.3. Restore is the proof

Chỉ restore thực với engine, indexes, permissions, keys và sample invariants mới chứng minh một đường khôi phục có thể vận hành.

### 19.4. Backup có thể thành công nhưng không đúng RPO

Nếu backup hoàn thành trễ ba giờ hoặc PITR connector bị lag, bản mới nhất có thể quá cũ so với RPO.

### 19.5. Backup có thể restore nhưng không đạt RTO

Một TB backup ở region xa với tốc độ tải 50 MB/s có thể mất nhiều giờ trước khi database bắt đầu rebuild indexes. Phải đo end-to-end.

## 20. Backup catalog và manifest

Mỗi backup cần một định danh ổn định và metadata đủ cho trả lời: “Muốn phục hồi tenant T tại ngày D phải lấy những thứ gì?”

| Trường | Ý nghĩa |
|---|---|
| `backupId` | ID duy nhất trong namespace |
| `sourceClusterId` | Cụm/database nguồn |
| `sourceProductVersion` | Engine/version khi tạo |
| `consistentAt` | Mốc dữ liệu có thể phục hồi |
| `createdAt`, `completedAt` | Thời gian xử lý thực |
| `backupType` | Full, incremental, snapshot, PITR base |
| `parentBackupIds` | Các dependencies |
| `manifestDigest` | Hash/checksum manifest |
| `encryptionKeyRef` | Tham chiếu khóa, không phải key |
| `repository`, `region`, `account` | Miền lưu |
| `retentionUntil` | Ngày được phép xét hết hạn |
| `legalHold`, `immutableUntil` | Bảo vệ hủy |
| `verificationStatus` | Upload, integrity, restore-test |
| `scope` | Collection/table/tenant/snapshot group |

### 20.1. Metadata không nên nằm duy nhất ở nguồn production

Nếu production bị mất, catalog cũng phải phục hồi được từ miền độc lập. Có thể sao lưu catalog, policies và restore tooling cùng nhau.

### 20.2. Stable IDs thay đường dẫn file

Không dựa vào `backup-2026-11-14` bằng tên thư mục để suy base/full/region; API/catalog cần quan hệ chính thức.

### 20.3. Không lưu credentials trong manifest

Manifest chứa references, checksums và data scope; secrets và encryption key materials phải được quản lý riêng.

### 20.4. Tính nhất quán của catalog

Khi upload object xong nhưng catalog write thất bại, cần recovery/idempotency để reconcile orphan objects; khi catalog ghi success trước upload xong thì backup không hợp lệ.

## 21. Chọn đích backup cho NoSQL

### 21.1. Object storage

Hợp với backup dài hạn, hỗ trợ versioning, lifecycle, encryption và object locking tùy provider. Cần tính API costs, restore bandwidth, request quotas và dependency-aware retention.

### 21.2. Block/volume snapshots

Hữu ích cho volume recovery, nhưng consistency, quãng lưu và portability phụ thuộc storage backend. Một snapshot volume đơn không tự là backup cluster-wide.

### 21.3. Network file storage

Thuận tiện cho một số công cụ nhưng có thể cùng network/security failure domain; cần throughput và permissions chặt.

### 21.4. Offline media

Giảm đường tấn công từ hệ online nhưng có logistics và RTO khác. Thường là một tầng bổ sung thay vì thay mọi backup gần.

### 21.5. Multi-cloud

Có thể giảm provider correlated failure nhưng tăng complexity, encryption/cert/format compatibility và cost. Kiểm restore trước khi coi đây là bảo vệ thực.

## 22. Offsite copy phải nằm ở một đường workflow được kiểm chứng

Một pipeline minh họa:

~~~mermaid
flowchart TD
    DB["NoSQL source cluster"] --> SNAP["Engine-consistent snapshot"]
    SNAP --> LOCAL["Local staging with finite TTL"]
    LOCAL --> EXP["Backup exporter"]
    EXP --> REM["Remote protected repository"]
    REM --> VERIFY["Manifest + checksum + retention verification"]
    VERIFY --> CAT["Durable independent catalog"]
    CAT --> DRILL["Isolated restore test"]
    VERIFY --> CLEAN["Authorized local snapshot cleanup"]
~~~

### 22.1. Local staging không được giữ mãi

Nếu exporter đã upload verified, local snapshots có thể được dọn qua công cụ chính thức theo policy; không tự xóa trước upload verification.

### 22.2. Cửa sổ backup kéo dài

Một backup 10 TB có thể mất hàng giờ/ngày để copy; source changes vẫn tiếp tục. Phải tính RPO dựa mốc consistentAt và copy lag.

### 22.3. Partial copy

Exporter retry phải biết những object nào đã copy an toàn, stable IDs và checksums. Không đưa backup vào catalog là usable khi thiếu shard/segment.

### 22.4. Network và egress

Cross-region transfer cần bandwidth, quota và chi phí. Nếu đường mạng đứt, backup source/logs có thể tích backlog, ảnh hưởng disk capacity.

### 22.5. Đích nằm ngoài blast radius của nguồn

Nếu production có quyền ghi/xóa vô hạn tại remote repository, “offsite” mới chỉ giải quyết phần địa lý. Thêm IAM separation/retention policy.

## 23. Cross-region replication không đồng nghĩa cross-region backup

### 23.1. Replica chạy theo trạng thái hiện tại

Nếu app ghi hỏng dữ liệu hoặc admin xóa table, replication có thể đồng bộ lỗi. Không có lịch sử đủ sâu để quay lại nếu không triển khai snapshot/PITR.

### 23.2. Region B có thể giúp RTO

Một replica/standby ở region B có thể cho failover nhanh hơn restore từ object storage. Đó là một **availability strategy**, không thay historical backups.

### 23.3. RPO của asynchronous replication

Nếu region A biến mất, asynchronous replica B có thể chậm vài seconds/minutes; đo replication lag và confirmed write outcomes theo model của hệ.

### 23.4. Backup ở region B vẫn cần restore test

Kho bytes ở B không đồng nghĩa có đủ engine version, keys, network, identity, compute capacity và automation để khởi động dịch vụ.

### 23.5. Một chiến lược thường dùng là kết hợp

Replicas/standby phục vụ rapid failover; immutable offsite backups và PITR phục vụ xóa nhầm, corruption và compromise. Chúng giải quyết các loại lỗi khác nhau.

## 24. Khác region nhưng cùng tài khoản: còn rủi ro gì?

Một database ở region A, bucket backup ở region B cùng một cloud account có thể chịu được mất region A, nhưng:

- Admin bị lộ token có quyền xóa cả hai.
- Billing/account suspension có thể ảnh hưởng cùng lúc.
- Một policy sai được áp trên toàn account.
- Key quản lý chung bị disable.
- Backup catalog và restore automation chỉ tồn tại trong account nguồn.

### 24.1. Tách account nếu threat model yêu cầu

Backup account có admin boundary, restricted trust policy và separate key controls giảm blast radius.

### 24.2. Cross-account trust cần tối giản

Role nguồn có thể được phép upload/replicate vào repository nhưng không được xóa các bản đã khóa hoặc thay retention. Mỗi grant phải có business reason.

### 24.3. Kiểm khả năng truy cập khi sự cố

Thử tắt/giả lập không sử dụng production account và xác nhận recovery operators vẫn liệt kê, giải mã và restore backup được từ independent identity.

### 24.4. Không chỉ phân tách bằng tên bucket

Hai bucket names khác nhau không làm chúng độc lập về quyền, encryption key hoặc region.

## 25. Backup cho MongoDB replica set và sharded cluster

MongoDB có cơ chế replication/oplog, journaling và khả năng backup khác nhau theo bản triển khai/managed service.

### 25.1. Replica không là lịch sử

Xóa dữ liệu sai có thể được replicate; cần snapshot/backup và đủ change history cho PITR nếu yêu cầu.

### 25.2. Oplog window

Một backup/PITR workflow có thể dùng oplog hoặc service-managed history; retention phải xét replication/CDC consumers và khả năng resume. Không vào host xóa oplog/journal để lấy disk.

### 25.3. Sharded backup consistency

Chụp snapshots từng shard độc lập mà không phối hợp có thể không cho một ảnh cluster nhất quán, đặc biệt với transactions/migrations. Dùng thủ tục/backup tool được MongoDB deployment hỗ trợ.

### 25.4. Offsite placement

Nếu backup chỉ được giữ trong cùng provider account, kiểm policy mất account/region. Có thể cần export/copy vào protected repository tùy managed service capabilities.

### 25.5. Restore drills

Thử restore vào cluster mới, xác minh users/roles/indexes/shard metadata, sample reads và nghiệp vụ write/replay, không chỉ kiểm storage size.

## 26. Backup cho Cassandra/ScyllaDB

### 26.1. Snapshot dựa trên SSTables

Trong nhiều phiên bản, snapshot dùng hard links tới SSTables cũ. Snapshot tại node là một tập file phục vụ khôi phục nhất định, không tự là offsite backup.

### 26.2. Multi-node/keyspace consistency

Backup cần biết token ranges, schemas, replicas, snapshot timing và consistency assumptions. Chép SSTables từ một node bất kỳ có thể thiếu ranges hoặc không phù hợp khôi phục cluster.

### 26.3. Incremental backup và commitlog

Các cơ chế incremental/commitlog archive có semantics riêng. Không tự suy incremental SSTables + random commitlog segments tạo PITR hoàn chỉnh.

### 26.4. Offsite storage

Upload snapshots và schema/metadata tới đích độc lập, verify manifests/checksums và giữ enough context để rebuild topology.

### 26.5. Retention với hard links

Một snapshot cũ có thể giữ old SSTables khỏi được reclaim sau compaction; cleanup phải dùng công cụ hỗ trợ, kiểm remote backup verification và chain trước khi xóa.

## 27. Backup cho Redis

### 27.1. RDB và AOF không là hai bản sao offsite

Nếu cả `dump.rdb` và AOF ở cùng volume, mất volume có thể mất cả hai. Chúng là cơ chế persistence/recovery, cần copy an toàn ra độc lập khi dữ liệu cần backup.

### 27.2. Snapshot timing và fork/CoW

Quá trình tạo RDB có thể tốn RAM và temp disk dưới write load. Lịch backup phải xét headroom/latency và trạng thái thành công.

### 27.3. AOF rewrite

Không xóa AOF trong lúc rewrite hoặc để giảm disk; engine quản lý chain. Backup phải có consistent state và metadata theo version.

### 27.4. Nếu Redis chỉ là cache

Nếu cache có thể tái tạo từ source và RTO chấp nhận, có thể chọn không backup cache mà giữ scripts/infra để rebuild. Nhưng cần chứng minh source và rebuild capacity thực sự đủ.

### 27.5. Nếu Redis chứa state duy nhất

Backup retention, encryption, restore tests và write durability cần tương ứng business impact; “Redis là cache” không còn đúng trong trường hợp này.

## 28. Backup cho DynamoDB

### 28.1. Service-managed backup/PITR

DynamoDB có khả năng backup và point-in-time recovery theo cấu hình/capabilities của dịch vụ. Cửa sổ retention, regionality và khôi phục phải được xác minh từ API tại thời điểm triển khai.

### 28.2. On-demand backups khác PITR window

Một backup tạo theo yêu cầu lưu state tại một mốc; PITR là khả năng phục hồi theo khoảng. Không suy một backup on-demand cho arbitrary minute recovery.

### 28.3. Cross-account/region controls

Nếu cần độc lập khi account bị compromise, xem cơ chế copy/cross-account backup và storage/backup service permissions được hỗ trợ. Không tự tuyên bố mọi loại backups có thể copy theo cùng API.

### 28.4. Restore tạo nguồn mới

Khôi phục thường cần xem table identity, throughput/capacity, streams, IAM, TTL, indexes và application configuration; bản restore không tự nối vào production routing.

### 28.5. Không có data-dir để dọn

Với managed service, retention, TTL và backup lifecycle được quản lý qua API/policy, không bằng xóa file trên host.

## 29. Backup cho Azure Cosmos DB for NoSQL

### 29.1. Backup mode và policy

Cosmos DB cung cấp các lựa chọn backup/recovery theo account type và configuration. Cần phân biệt periodic vs continuous modes và các điều kiện restore được hỗ trợ ở version/account cụ thể.

### 29.2. Region và tài khoản

Vị trí/độ độc lập của backup phụ thuộc service-managed backup architecture. Không mặc định nhiều read regions tương đương backup ngoài account/control plane.

### 29.3. Logical partitions và restore scope

Khôi phục container/account có thể yêu cầu mapping partition keys, indexing, TTL, throughput, consistency và routing. Tenant-level recovery có thể cần export/rebuild workflow riêng.

### 29.4. Data residency

Cross-region backup/restore phải được xét với quy định địa lý của tenant. Không chép dữ liệu ngoài phạm vi hợp đồng chỉ vì “offsite an toàn hơn”.

### 29.5. Kiểm RTO/RPO qua exercise

Managed PITR có thể giảm công sức tạo backup nhưng không tự đảm bảo thời gian phục hồi application toàn bộ, đặc biệt khi còn downstream projections và external services.

## 30. Backup cho Elasticsearch/OpenSearch

### 30.1. Snapshot repository

Snapshot thường lưu index segments/metadata trong repository có thể dùng incremental/shared data. Không xóa object files trong repository bằng lệnh ngoài API engine.

### 30.2. Delete dependency

Xóa snapshot phải qua supported API để catalog/references được cập nhật. Object lifecycle ngẫu nhiên có thể phá nhiều restore points.

### 30.3. Offsite placement

Repository trên cùng node/data volume có thể mất cùng cluster. Object storage độc lập và quyền hạn được tách giúp bảo vệ tốt hơn.

### 30.4. Restore index không tự phục hồi mọi thứ

Security configurations, templates, ingest pipelines, application aliases, version compatibility và external system state có thể cần phục hồi riêng.

### 30.5. Search projection có thể rebuild?

Nếu NoSQL source đủ dữ liệu và thời gian để reindex thỏa RTO, backup search có thể tối ưu khác. Nếu reindex mất một tuần, snapshot vẫn có giá trị lớn.

## 31. CDC và event log không mặc định là backup

### 31.1. Event streams có retention hữu hạn

Kafka/change feed có thể trim dữ liệu theo thời gian/kích thước, compaction hoặc TTL. Không suy lịch sử ứng dụng luôn còn để rebuild bất kỳ trạng thái nào.

### 31.2. Domain events có thể không đủ reconstruct

Một event `OrderStatusChanged` chỉ chứa status mới có thể thiếu customer/address/price snapshot cần thiết để phục hồi source khi đã mất mọi base snapshot.

### 31.3. Raw CDC phụ thuộc source semantics

CDC record có thể là update delta, có token/ordering theo partition và history window. Không tùy ý ghép mọi partitions thành một consistent snapshot.

### 31.4. Event replay còn có side effects

Replay events để dựng projection không được tự gửi lại payment charge/email. Consumers phải tách reducer/rebuild và external side effect protocols.

### 31.5. CDC là bổ sung cho backup

Nếu được thiết kế đúng, change history hỗ trợ PITR/rebuild. Nhưng backup base, verified schema/manifest và consistent watermark vẫn cần.

## 32. Multi-tenant SaaS: bảo vệ nhưng không vượt phạm vi dữ liệu

### 32.1. Tenants có retention khác nhau

Tenant enterprise yêu cầu khôi phục 90 ngày, tenant trial chỉ cần 7 ngày. Nếu dữ liệu nằm chung snapshot vật lý, delete riêng một tenant có thể không thực hiện theo từng file mà cần data-governance strategy.

### 32.2. Data residency

Tenant giới hạn dữ liệu ở một quốc gia/region có thể không cho copy tới backup account ở địa lý khác. Chọn độc lập ở cấp AZ/account/physical location **trong vùng được phép**.

### 32.3. Cross-tenant recovery

Khôi phục toàn cluster để sửa một tenant có thể làm dữ liệu tenants khác quay về trạng thái cũ. Có thể cần restore vào môi trường cô lập rồi selective merge, giữ version/authorization/idempotency.

### 32.4. Encryption isolation

Per-tenant keys hoặc separate backup repositories có thể giảm blast radius, nhưng tăng cost, catalog complexity và key availability burden.

### 32.5. Không đưa tenantId chưa xác thực vào restore API

Restore một tenant là tác vụ có quyền cao. Caller phải được authorization/audit, không chỉ truyền tenantId trong request rồi đọc dữ liệu.

## 33. Privacy, xóa dữ liệu và legal hold

### 33.1. Xóa ở primary khác xóa ở backup

Một lệnh delete ở source có thể được replicate nhanh nhưng backups vẫn giữ bản cũ theo retention. Phải công bố và thực thi policy phù hợp luật/hợp đồng áp dụng.

### 33.2. Immutable retention có thể xung đột erasure request

Một bản sao WORM có thể không thể xóa sớm; cần có cơ sở lưu trữ hợp pháp, giới hạn truy cập, expiry và quy trình xử lý erase khi hết hold. Không giả định giải pháp kỹ thuật sẽ tự giải quyết nghĩa vụ pháp lý.

### 33.3. Legal hold riêng

Một điều tra có thể yêu cầu giữ dữ liệu lâu hơn retention thông thường. Hold cần scope, owner, ngày review và quyền gỡ.

### 33.4. Restore phải xử lý deletion tombstones

Nếu khôi phục backup trước thời điểm user yêu cầu xóa, dữ liệu có thể xuất hiện lại. Cần **deletion ledger/erasure replay** và kiểm quyền khi restore vào production.

### 33.5. Không lưu PII trong manifest

Backup metadata, object key names và logs có thể lộ tenant/customer IDs. Thiết kế catalog để đủ quản lý nhưng không làm phát tán PII không cần thiết.

## 34. Sao lưu độc lập về quyền và bảo vệ khóa

Một kiến trúc phòng vệ theo lớp:

~~~text
Production role:
    read/write application data
    NO delete backup repository

Backup exporter role:
    create snapshots / upload objects
    NO shorten retention or delete locked objects

Backup security administrator:
    manage policy under approval
    NO unrestricted production application access

Recovery operator:
    read/restore approved backup scope
    NO blanket delete or permanent key destruction
~~~

### 34.1. Không một token dùng cho mọi thứ

Nếu production deployment secret vừa đọc dữ liệu khách hàng, vừa xóa backup và key, attacker chỉ cần lộ một secret để phá recovery.

### 34.2. Thay đổi retention là sự kiện nhạy cảm

Giảm retention từ 90 ngày xuống 1 ngày có thể làm mất khả năng phục hồi trong tương lai. Cần approval/audit và bảo vệ policy.

### 34.3. Break-glass

Quyền khẩn cấp cần tồn tại nhưng được bảo vệ, log và kiểm định kỳ. Không để tất cả recovery credentials trong cùng password manager/session của hệ đã bị compromise mà không có đường dự phòng.

### 34.4. Sau account compromise

Phải thu hồi credentials và xác định **từ lúc nào** attacker có quyền, kiểm backup history/immutability, rồi mới tin restore point nào sạch.

## 35. Vị trí backup và tốc độ phục hồi

Giả sử 5 TB dữ liệu cần tải từ remote repository; băng thông hiệu dụng 500 MB/s trong điều kiện lý tưởng:

\[
T_{\text{download}}
\approx \frac{5{,}000{,}000\ \mathrm{MB}}{500\ \mathrm{MB/s}}
=10{,}000\ \mathrm{s}\approx2.78\ \mathrm{giờ}.
\]

Ví dụ dùng đơn vị decimal và bỏ qua overhead. Thời gian thực có thể dài hơn nhiều do throttling, parallelism, network variability, decryption, index rebuild và checks.

### 35.1. RTO phải bao gồm khối lượng dữ liệu

Một backup ở nơi rất xa có thể an toàn nhưng không đáp ứng RTO 30 phút nếu cần restore 5 TB qua liên kết hạn chế.

### 35.2. Local fast recovery tier

Có thể giữ bản gần region để restore nhanh, kết hợp bản immutable/offsite độc lập để chịu thảm họa. Không chỉ chọn một vị trí.

### 35.3. Data transfer cost

Cross-region replication/backup có egress, API requests, object storage classes và restore charges. Tính cost của **restore drills** nữa, không chỉ phí lưu.

### 35.4. Archive storage class

Tầng lưu trữ rất rẻ có thể yêu cầu thời gian retrieval dài hoặc phí cao. Không dùng archive-only cho bản cần RTO cực ngắn nếu không có fast tier bổ sung.

### 35.5. Khả năng restore đồng thời

Trong region outage, nhiều clusters có thể restore cùng lúc và tranh bandwidth/API quota. Thử trong capacity planning, không giả định tốc độ một test sẽ lặp lại cho 100 tenants.

## 36. Tính chi phí retention có ý thức

Ước lượng đơn giản:

\[
C_{\text{month}} \approx
S_{\text{stored}}\cdot P_{\text{GB-month}}
 + C_{\text{requests}}
 + C_{\text{transfer}}
 + C_{\text{keys}}
 + C_{\text{verification}}
 + C_{\text{restore exercises}}.
\]

### 36.1. Logical backup size khác billable size

Compression/deduplication/shared segments/incrementals có thể giảm bytes; versioning và immutable retention có thể tăng thực tế.

### 36.2. Retention nhân với change rate

Một DB logical 1 TB nhưng dữ liệu thay đổi 200 GB/ngày có incremental history cost khác DB 1 TB gần như bất biến.

### 36.3. Đừng tính “30 snapshots × 1 TB” mặc định

Nếu backup tool deduplicates, physical bytes có thể ít hơn; nếu full copies riêng, có thể gần con số ấy. Đo thực/đọc tool semantics.

### 36.4. Chi phí không được quyết định RPO/RTO một mình

Nếu giảm backup để tiết kiệm gây mất nhiều ngày giao dịch sau sự cố, chính sách có thể không phù hợp. Định giá loss scenarios và yêu cầu business trước.

### 36.5. WORM có nghĩa vụ tài chính

Đặt retention lock 10 năm có thể khiến bản sao không thể xóa sớm dù tạo nhầm. Thử policy với dữ liệu test, review governance trước production.

## 37. Thiết kế deletion/expiration không phá chuỗi phục hồi

Một cleanup job an toàn phải tìm **các restore points thật sự không còn cần**.

### 37.1. Không dựa vào tuổi file duy nhất

Base full từ 35 ngày trước có thể cần cho incremental từ 5 ngày trước. Mtime không nói dependency.

### 37.2. Retention eligibility

Snapshot phải đã quá hạn, không legal hold, không immutability lock, không là required base và không là last-known-good restore point.

### 37.3. Xác nhận backup thay thế

Nếu bản mới nhất upload failed, không được tự xóa last good backup dù nó đã cũ hơn policy nominal.

### 37.4. Dry run và approval

In ra backup ID, reason, retentionUntil, dependencies, location và estimated reclaim bytes. Người chịu trách nhiệm phê duyệt việc xóa đặc biệt.

### 37.5. Chỉ xóa bằng API được hỗ trợ

Snapshot repositories có reference counts/metadata; dùng vendor/backup-tool API, không trực tiếp xóa object/block file khiến những restore points khác hỏng.

## 38. Pseudocode: lập kế hoạch dọn backup mà không xóa

~~~text
function planExpiry(catalog, policy, now):
    keepSet = catalog.findRequiredRestoreChains(policy)
    candidates = []

    for backup in catalog.listBackups():
        if backup.id in keepSet:
            continue
        if now < backup.retentionUntil:
            continue
        if backup.legalHold or backup.immutableUntil > now:
            continue
        if not backup.isVerified:
            continue  // investigate; do not hide failed state
        if backup.isLastKnownGoodForItsScope:
            continue
        if catalog.hasRetainedDependent(backup.id):
            continue

        candidates.add({
            backupId: backup.id,
            location: backup.repositoryId,
            reason: "policy-expired-and-unreferenced"
        })

    return candidates  // DRY RUN ONLY

function executeApproved(plan, approval, repositoryApi):
    require matching approval and operator authorization
    for candidate in plan:
        revalidate catalog, lock, dependencies, policy
        repositoryApi.deleteUsingSupportedOperation(candidate)
    reconcile catalog and test remaining restore chains
~~~

### 38.1. Catalog phải có dependency graph

Chỉ tính `backupAge` không đủ; cần biết full, incremental, PITR base và các đoạn history.

### 38.2. Race condition

Một incremental mới có thể bắt đầu sau lúc lập plan, nên revalidate trước delete. Không coi dry-run result là quyền xóa vĩnh viễn.

### 38.3. Lỗi trong catalog

Nếu catalog thiếu records hoặc có trạng thái không nhất quán, mặc định an toàn là **không xóa** cho tới khi reconcile.

### 38.4. Immutability enforced ở storage

Planner không được là lớp duy nhất chống xóa; repository policy phải từ chối delete trong thời gian lock.

## 39. Java: mô hình backup manifest có kiểu

Ví dụ Java 17+ cho control plane, không gọi thao tác xóa hay đọc dữ liệu production:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Objects;

public record BackupManifest(
    String backupId,
    String sourceCluster,
    String repositoryId,
    Instant consistentAt,
    Instant completedAt,
    BackupKind kind,
    List<String> parentBackupIds,
    Instant retentionUntil,
    Instant immutableUntil,
    boolean legalHold,
    boolean uploadedAndVerified,
    boolean restoreTested
) {
    public enum BackupKind { FULL, INCREMENTAL, PITR_BASE }

    public BackupManifest {
        Objects.requireNonNull(backupId);
        Objects.requireNonNull(sourceCluster);
        Objects.requireNonNull(repositoryId);
        Objects.requireNonNull(consistentAt);
        Objects.requireNonNull(completedAt);
        Objects.requireNonNull(kind);
        Objects.requireNonNull(parentBackupIds);
        Objects.requireNonNull(retentionUntil);
        Objects.requireNonNull(immutableUntil);

        if (backupId.isBlank() || repositoryId.isBlank()
                || sourceCluster.isBlank()) {
            throw new IllegalArgumentException("identity required");
        }
        parentBackupIds = List.copyOf(parentBackupIds);
        if (completedAt.isBefore(consistentAt)) {
            throw new IllegalArgumentException(
                "completion before consistent point"
            );
        }
    }

    public boolean protectedAt(Instant now) {
        return legalHold
            || now.isBefore(retentionUntil)
            || now.isBefore(immutableUntil);
    }
}
~~~

### 39.1. `protectedAt` chỉ là một điều kiện

Không xóa chỉ vì `protectedAt` trả false. Còn dependencies, last-known-good, backup integrity, approval và vendor delete semantics.

### 39.2. Manifest immutable không đồng nghĩa backup immutable

Java `record` ngăn sửa field trong object này; nó **không** bảo vệ object storage khỏi delete. Immutability phải được enforce ở repository và IAM.

### 39.3. `restoreTested` không có nghĩa mọi thời điểm phục hồi được

Nó chỉ nói đã có một cuộc diễn tập được ghi nhận. Nên thêm `lastRestoreVerifiedAt`, target scenario, hash/proof và expiration policy cho evidence.

### 39.4. Versioned metadata

Trong hệ thực, catalog/manifest schema cũng cần versioning, signature/checksum, migration và dữ liệu về engine, key refs, scope/region.

## 40. Java: planner chỉ trả quyết định, không thực thi delete

~~~java
import java.time.Instant;
import java.util.Set;

public enum ExpiryDecision {
    RETAIN_PROTECTED,
    RETAIN_DEPENDENCY,
    RETAIN_LAST_GOOD,
    INVESTIGATE_UNVERIFIED,
    ELIGIBLE_FOR_REVIEW
}

public final class RetentionPlanner {
    public ExpiryDecision evaluate(
            BackupManifest backup,
            Instant now,
            Set<String> requiredByRetainedRestorePoints,
            Set<String> lastKnownGoodBackupIds) {

        if (backup.protectedAt(now)) {
            return ExpiryDecision.RETAIN_PROTECTED;
        }
        if (!backup.uploadedAndVerified()) {
            return ExpiryDecision.INVESTIGATE_UNVERIFIED;
        }
        if (requiredByRetainedRestorePoints.contains(
                backup.backupId())) {
            return ExpiryDecision.RETAIN_DEPENDENCY;
        }
        if (lastKnownGoodBackupIds.contains(backup.backupId())) {
            return ExpiryDecision.RETAIN_LAST_GOOD;
        }
        return ExpiryDecision.ELIGIBLE_FOR_REVIEW;
    }
}
~~~

### 40.1. Set dependencies cần được tính đúng

`requiredByRetainedRestorePoints` phải lấy từ catalog đã kiểm toàn bộ graph full/incremental/PITR. Nếu graph sai, planner này không thể tự biết backup nào cần giữ.

### 40.2. Không có phương thức `delete`

Code cố ý không xóa. Xóa cần approval, revalidation, IAM/repository guardrails, audit và hỗ trợ vendor.

### 40.3. Trạng thái không rõ nên fail closed

Trong implementation production, nếu không truy cập được catalog/dependency service, hãy dừng kế hoạch dọn; không coi unknown là không phụ thuộc.

### 40.4. Retention và immutability là hai lớp

Một backup có thể đã quá nominal retention nhưng vẫn bị storage immutability lock; policy cleanup phải tôn trọng cả hai.

## 41. JUnit: bảo vệ retention và dependency

Một test minh họa cho logic planner:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

final class RetentionPlannerTest {
    private final RetentionPlanner planner =
        new RetentionPlanner();
    private final Instant now =
        Instant.parse("2026-11-14T00:00:00Z");

    private BackupManifest backup(
            boolean legalHold, Instant immutableUntil) {
        return new BackupManifest(
            "full-100",
            "orders-cluster",
            "backup-repo-a",
            Instant.parse("2026-10-01T00:00:00Z"),
            Instant.parse("2026-10-01T01:00:00Z"),
            BackupManifest.BackupKind.FULL,
            List.of(),
            Instant.parse("2026-11-01T00:00:00Z"),
            immutableUntil,
            legalHold,
            true,
            true
        );
    }

    @Test
    void legalHoldPreventsExpiry() {
        var b = backup(true,
            Instant.parse("2026-10-01T00:00:00Z"));
        assertEquals(ExpiryDecision.RETAIN_PROTECTED,
            planner.evaluate(b, now, Set.of(), Set.of()));
    }

    @Test
    void retainedIncrementalKeepsItsBase() {
        var b = backup(false,
            Instant.parse("2026-10-01T00:00:00Z"));
        assertEquals(ExpiryDecision.RETAIN_DEPENDENCY,
            planner.evaluate(
                b, now, Set.of("full-100"), Set.of()
            ));
    }
}
~~~

### 41.1. Đây là unit tests, chưa xác minh hệ backup

Nó chỉ kiểm logic policy trong Java, không chứng minh Object Lock, chain metadata hoặc restore khả dụng ở cloud.

### 41.2. Test hợp đồng repository

Trong môi trường test có quyền, thử tài khoản production **không thể xóa** locked backup; chỉ backup operator được read/restore đúng phạm vi.

### 41.3. Test race và lỗi

Simulate catalog unavailable, new incremental during cleanup, lost ACK after delete API, key disabled, upload incomplete và restore timed out.

## 42. Restore drill: mô phỏng đúng thảm họa

Một bài diễn tập phải bắt đầu từ giả định “thứ gì đã mất”:

~~~text
Scenario:
    Production account unavailable.

Allowed:
    Recovery admin identity in separate account.
    Remote immutable backup repository.
    Independent backup catalog and encryption keys.

Not allowed:
    Existing production VMs, source volumes, source secrets.
~~~

### 42.1. Tạo môi trường sạch

Provision cluster/VM/network/security ở vùng được phép, không ghi đè hệ đang phục vụ.

### 42.2. Chọn restore point

Chọn mốc nằm trước lỗi logic hoặc đủ mới cho RPO, dựa manifest/earliest restorable timestamp đã được xác nhận.

### 42.3. Phục hồi metadata

Collections/tables, indexes, users/roles, encryption refs, TTL config, service endpoints, schema versions và replication topology cần được phục hồi/tái thiết lập.

### 42.4. Kiểm domain correctness

Verify số Order theo tenant, checksums, payment/idempotency records, referential invariants do application quản lý, không chỉ ping DB success.

### 42.5. Đo thời gian thực

Ghi mỗi mốc: phát hiện, quyết định, download, replay, verify, traffic cutover và user-facing functionality. So với RTO.

## 43. Cross-tenant và downstream reconciliation khi restore

### 43.1. Điểm khôi phục ở source không khớp downstream

Kafka consumer, search projection hoặc payment service có thể đã xử lý events **sau** restore point của NoSQL. Nếu khởi động application ngay, state có thể lệch.

### 43.2. Chặn side effects lặp

Restore có thể khiến outbox events cũ xuất hiện lại; consumers cần stable event IDs, idempotent effects và replay policies để không charge/gửi email lần hai.

### 43.3. Per-tenant restore an toàn

Không thay toàn cluster live bằng snapshot cũ chỉ để sửa một tenant. Restore cô lập, lấy dữ liệu/versions cần thiết, kiểm tenant scope và merge có kiểm soát.

### 43.4. Delta sau restore point

Nếu hệ vẫn nhận writes sau thời điểm backup, cần quyết định reconcile, replay hay compensating workflow. Một bản backup “đúng kỹ thuật” có thể chưa đủ cho business closure.

### 43.5. Audit decisions

Ghi rõ những orders/payments nào đã được restore, discarded, replayed, compensated và ai phê duyệt.

## 44. Runbook: mất một node

### 44.1. Mục tiêu

Khôi phục availability và replica count mà không mất acknowledged writes theo durability contract.

### 44.2. Kiểm nguồn còn sống

Cluster quorum, leader election, replica lag, backup state và node disk pressure; đừng vội restore từ bản cũ nếu replication repair đủ.

### 44.3. Cách làm theo engine

Dùng node replacement/replica rebuild thủ tục được hỗ trợ. Không tự copy data directory của node khác trong khi live nếu engine không cho phép.

### 44.4. Nếu cần backup

Chọn mốc phù hợp, kết hợp change history/replay, kiểm remote repository và failover safety.

### 44.5. Bài học

Replication có thể là giải pháp nhanh cho lỗi node, trong khi offsite backup chủ yếu là tầng bảo vệ sự cố lớn hơn.

## 45. Runbook: xóa nhầm hàng triệu records

### 45.1. Khoanh vùng nhanh

Ghi thời điểm thao tác sai, commandIds/query shape, các collections/tenants bị ảnh hưởng; cân nhắc dừng mutation tiếp theo bằng admission control an toàn.

### 45.2. Chọn restore point trước thời điểm xóa

Kiểm earliest restorable point/PITR và độ nhất quán, không chọn bản “mới nhất” nếu nó đã chứa lỗi.

### 45.3. Restore cô lập trước

Đưa backup vào cluster riêng, kiểm các Order cần cứu, sau đó lên kế hoạch selective merge hoặc cutover.

### 45.4. Không quên writes hợp lệ sau lỗi

Rollback toàn database có thể xóa các giao dịch hợp lệ mới được xác nhận sau sự kiện. Cần recovery plan reconcile/merge và business sign-off.

### 45.5. Hậu kiểm

Test guardrails cho bulk delete, permissions, version checks, change review và retention phát hiện lỗi muộn.

## 46. Runbook: region outage

### 46.1. Kiểm mục tiêu và phạm vi

Region A mất, data còn ở region B? Có replica standby, backup store và keys? RPO/RTO của failover khác restore from scratch.

### 46.2. Thay miền triển khai

Provision compute/DB/network/identity trong region được phép; kiểm DNS/routing và data residency trước cutover.

### 46.3. Sử dụng backups khi replica không đủ

Nếu data replica cũng mất/không đáng tin, restore từ offsite repository với manifest và log history.

### 46.4. Cần định nghĩa split-brain

Nếu A hồi phục khi B đã nhận writes, phải có authoritative ownership/fencing và conflict-resolution protocol. Backup không tự giải quyết ghi đồng thời hai phía.

### 46.5. Test từ trước

Đo thời gian network provisioning, retrieval, permissions/key access và rebuild; không chỉ kiểm region B có object backup.

## 47. Runbook: production account bị chiếm quyền

### 47.1. Không tin nguồn đang bị kiểm soát

Account attacker có thể sửa data, disable monitoring, xóa versions hoặc đặt backdoor. Cần preserve evidence và dùng recovery identities độc lập.

### 47.2. Bảo vệ repository

Kiểm immutable retention, legal holds, delete permissions, backup catalog và key management từ miền bảo mật riêng.

### 47.3. Chọn restore point sạch

Phân tích từ thời điểm compromise đến thời điểm phát hiện; bản mới nhất có thể chứa dữ liệu/ứng dụng bị sửa.

### 47.4. Restore trong account sạch

Không tự bring back compromised credentials/IAM settings. Rotate secrets và kiểm application artifact integrity.

### 47.5. Diễn tập về quyền thực

Một bản sao “khác account” không giúp nếu key/catalog vẫn cần login qua account đã bị khóa.

## 48. Dashboard tối thiểu cho retention và offsite protection

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| `lastBackupCompletedAt` | Lần gần nhất backup kết thúc thật? |
| `latestConsistentDataAt` | Mốc dữ liệu mới nhất bảo vệ? |
| `earliestRestorableAt` | Có thể rollback xa bao nhiêu? |
| `backupUploadLag` | Bản chụp đã tới offsite chưa? |
| `backupVerificationFailures` | Manifest/checksum có hỏng? |
| `lastRestoreTestAt` | Lần cuối đã restore test khi nào? |
| `restoreDurationP95` | RTO thực hiện có ổn? |
| `immutableProtectedCopies` | Bao nhiêu bản dưới lock? |
| `unprotectedCopyCount` | Có bản sao dễ bị xóa? |
| `backupCrossRegionAge` | Bản sao ngoài region có mới? |
| `backupCrossAccountAge` | Bản sao ngoài account có mới? |
| `retentionChainGaps` | Chain cần phục hồi có bị thiếu? |
| `keyAccessCheck` | Recovery role còn giải mã được? |
| `repositoryCost` | Dung lượng/chi phí theo tier? |
| `snapshotLocalDiskBytes` | Local staging có tích lũy? |

### 48.1. Alert theo thời gian dữ liệu được bảo vệ

Job báo `SUCCESS` trong khi copy cross-region thất bại thì protection point ngoài miền lỗi vẫn cũ. Alert dựa `latestOffsiteVerifiedConsistentAt`.

### 48.2. Restore test age

Backup hàng ngày nhưng 12 tháng chưa restore test là khoảng trống kiểm chứng. Theo dõi từng database/schema/region recovery path.

### 48.3. Quyền phá hủy cũng là metric

Review các identities có quyền delete/shorten retention/disable key. Một permission drift có thể phá threat model mà không xuất hiện ở storage usage.

### 48.4. Không bắn metric với backupId làm label vô hạn

Ghi IDs chi tiết trong catalog/audit, metrics tổng hợp theo product, repo, region, tier và outcome.

## 49. Thiết kế service-level policy làm nguồn quyết định

Một policy có thể được thể hiện bằng YAML để thảo luận/kiểm tra, **không phải định dạng mặc định của cloud provider**:

~~~yaml
service: "order-service"
database: "nosql-order-store"
owner: "data-platform-team"

objectives:
  nodeFailure:
    rpo: "<approved target>"
    rto: "<approved target>"
  accidentalDeletion:
    rpo: "<approved target>"
    rto: "<approved target>"
    detectionWindow: "<days>"
  regionLoss:
    rpo: "<approved target>"
    rto: "<approved target>"
  accountCompromise:
    cleanRestoreRequired: true

retention:
  pitRWindow: "<supported verified window>"
  hourly: "<count/days>"
  daily: "<count/days>"
  weekly: "<count/weeks>"
  monthly: "<count/months>"
  legalHoldAware: true
  chainDependencyAware: true

placement:
  primaryRegion: "<region>"
  fastRestoreRepository: "<repository ID>"
  offsiteRegion: "<permitted region>"
  protectedBackupAccount: "<separate security boundary>"
  physicalOfflineCopy: "<if required>"
  requiredResidency: "<data residency rules>"

protection:
  immutableRetention: "<duration/mode>"
  encryptionAtRest: required
  encryptionInTransit: required
  keyReference: "<managed key identifier>"
  keyRecoveryIndependentOfProduction: true
  productionIdentityCanDeleteBackups: false
  adminChangesRequireApproval: true

verification:
  uploadManifest: required
  checksums: required
  catalogReplication: required
  restoreDrillFrequency: "<interval>"
  cleanAccountRestoreDrill: "<cadence>"
  assertBusinessInvariants: required

operations:
  cleanupMode: "dry-run then approved vendor API"
  alertOnOffsiteProtectionLag: true
  alertOnRestoreChainGaps: true
  alertOnMissingKeys: true
  auditChanges: true
~~~

### 49.1. Không điền giá trị tùy tiện

Các mục tiêu phải được business/security/operations thống nhất và đo trên product/version/topology cụ thể.

### 49.2. RPO/RTO nên theo failure scenario

Node failover có thể vài phút; account compromise cần môi trường sạch và identity reset nên lâu hơn. Không lấy một con số áp cho mọi tình huống.

### 49.3. Retention không chỉ ở một setting

Snapshot base, incremental history, PITR logs, immutable backup, catalog và keys cần hợp tác. Một `retentionDays` trên cloud UI chưa đủ.

## 50. Một ma trận kiểm tra quyết định

| Nhu cầu | Nếu chỉ có local snapshot | Cần bổ sung |
|---|---|---|
| Chống xóa nhầm | Có thể rollback nếu snapshot trước lỗi | PITR/retention đủ detection window |
| Chống hỏng volume | Có thể mất snapshot | Repository ngoài volume/node |
| Chống AZ loss | Có thể cùng mất | Placement khác AZ/region theo policy |
| Chống region outage | Không đủ nếu cùng region | Cross-region copy/standby + tested restore |
| Chống account compromise | Cùng IAM dễ bị xóa | Cross-account IAM/immutability/offline |
| Chống xóa key | Không giải mã được | Independent key lifecycle and recovery |
| Đáp ứng RTO ngắn | Local restore có thể nhanh | Fast tier, preprovisioning, practiced runbook |
| Khôi phục dữ liệu xóa từ 2 tháng trước | Không nếu retention 7 ngày | Long-tail points/event/audit strategy |
| Tenant data residency | Offsite tùy ý có thể vi phạm | Chọn miền được phép/region-local independence |
| Chứng minh backup dùng được | Snapshot count chưa đủ | End-to-end restore drills và invariants |

## 51. Các sai lầm thường gặp

### “Ba replicas là ba backups”

Sai. Các replicas có thể cùng nhận xóa nhầm/corruption và cùng chịu account/region failure.

### “Snapshot nằm trên ổ khác là đủ độc lập”

Không nếu cùng host/account/region là miền lỗi cần bảo vệ.

### “Backup sang region khác sẽ chống ransomware”

Chưa chắc khi production credentials có thể xóa cả hai regions.

### “Versioning nghĩa không ai xóa được”

Không nếu role có quyền permanent-delete các versions hoặc key bị hủy.

### “Object Lock bảo vệ luôn việc đọc dữ liệu”

Không. Vẫn phải kiểm IAM, encryption và key access.

### “Retention 90 ngày nghĩa PITR 90 ngày”

Không nếu backup points thưa hoặc log history không liên tục.

### “Backup hằng ngày cho RPO 15 phút”

Không nếu không có thay đổi được capture bền ở độ hạt cần thiết.

### “Backup xanh lá là restore được”

Không nếu thiếu manifest, encryption key, engine compatibility hoặc chưa thử khôi phục.

### “Immutable backup không cần restore test”

Sai. Có thể khóa bất biến một bản sao hỏng hoặc không nhất quán.

### “Cứ xóa base full cũ hơn 30 ngày”

Sai nếu incrementals mới vẫn phụ thuộc base.

### “Cứ giữ mọi backup vĩnh viễn”

Không phù hợp cost, privacy, legal hold boundaries và key management.

### “Đã xóa user ở primary thì mọi backup cũng tự xóa”

Không. Cần erasure/retention policy và deletion replay khi restore.

### “Bản backup ở xa luôn tốt hơn”

Không nếu retrieval latency khiến RTO không đạt hoặc dữ liệu vượt residency requirements.

### “RPO/RTO là thuộc tính mặc định của database”

Không. Chúng là mục tiêu ở mức service/failure scenario, phụ thuộc backup, network, application và vận hành.

### “Backup một node đủ cho sharded cluster”

Không tự bảo đảm completeness và consistency của mọi shards/transactions.

### “CDC/Kafka có mọi sự kiện nên khỏi backup”

Không khi retention/compaction, event payload hoặc global consistency không đủ để dựng state.

### “Tài khoản khác là độc lập hoàn toàn”

Không nếu cùng central admin, key và recovery identity có thể bị chiếm cùng lúc.

### “Sao lưu ngoài quốc gia luôn là best practice”

Không nếu hợp đồng/law/data residency cấm. Chọn miền lỗi độc lập trong vùng được phép.

### “Chỉ cần phục hồi DB là hoàn tất”

Không nếu indexes, outbox events, payment state và downstream projections lệch nhau.

### “Xóa backup để giảm chi phí là thao tác storage đơn giản”

Không khi dependency chains, WORM/legal holds và last-known-good recovery points tồn tại.

## 52. Checklist review chính sách backup

1. Đã phân loại dữ liệu theo **business criticality** chưa?
2. Đã xác định **RPO/RTO cho từng loại failure** chưa?
3. Đã tính **detection delay** cho logical corruption/deletion chưa?
4. Lịch tạo backup có đáp ứng độ hạt phục hồi yêu cầu không?
5. Có PITR và đo **earliest restorable point** thực không?
6. Full/incremental/log dependency graph được theo dõi không?
7. Có chống xóa base khi dependent backups còn giữ không?
8. Có bản sao **ngoài volume/node/AZ/region** theo threat model không?
9. Có backup copy ngoài **production IAM/account** khi cần không?
10. Production runtime có bị cấm xóa backup không?
11. Có immutable/offline tier với retention thích hợp không?
12. Object versioning và object lock được phân biệt rõ không?
13. Encryption khi truyền/lưu có được cấu hình và kiểm tra không?
14. Recovery keys có độc lập với production failure không?
15. Có inventory, manifest, checksum và backup catalog bền không?
16. Đích backup có nằm trong data residency được phép không?
17. Có xử lý tenant-specific retention và erasure request không?
18. Backup staging local có cleanup an toàn sau verify không?
19. Có kiểm restore của sharded/multi-node topology không?
20. Có test restore vào **account/region sạch** không?
21. Có test data correctness, indexes, permissions, keys không?
22. Đã đo **end-to-end RTO** với volume dữ liệu thực chưa?
23. Có xử lý replay/outbox/downstream side effects khi restore không?
24. Có alert khi offsite copy hoặc restore verification quá cũ không?
25. Có dự báo repository storage/cost và immutable retention không?
26. Có dry-run/approval và supported cleanup API không?
27. Có theo dõi legal holds và exception approvals không?
28. Có quyền break-glass được diễn tập/audit không?
29. Có kế hoạch khi backup job/metadata bị lỗi hay mất khóa không?
30. Có người sở hữu chính sách, đánh giá định kỳ và cập nhật sau incident không?

## 53. Bài tập thực hành

### Bài 1 — Replica và backup

Một cluster có ba replicas, một admin xóa nhầm collection và lệnh được replicate. Vì sao replica không giúp rollback? Thiết kế một bản sao độc lập theo thời gian.

### Bài 2 — Tính retention

Dữ liệu có thể sai mà chỉ phát hiện sau 21 ngày; công ty giữ backup 7 ngày. Nêu nguy cơ và cách chọn retention tối thiểu dựa trên detection window.

### Bài 3 — Frequency vs retention

So hai chính sách: một snapshot/ngày giữ 90 ngày, một snapshot/giờ giữ 48 giờ. Cái nào có recovery granularity tốt hơn? Cái nào xử lý lỗi phát hiện trễ tốt hơn?

### Bài 4 — PITR

Snapshot lúc 01:00, log history đầy đủ đến 16:00, muốn restore 13:45. Liệt kê điều kiện consistency/chain phải đúng.

### Bài 5 — RPO/RTO

Đơn hàng yêu cầu RPO 15 phút và RTO 2 giờ. Thiết kế baseline snapshot/change history, offsite storage và bài restore test để chứng minh mục tiêu.

### Bài 6 — Failure domains

Ba backups trên ba disks của cùng VM có chống host loss, region outage và admin compromise không? Vẽ phân cấp miền lỗi.

### Bài 7 — Cross-region, same account

Backup ở region B nhưng cùng production IAM role được phép delete. Phân tích khả năng chịu region outage và account compromise riêng.

### Bài 8 — Cross-account

Thiết kế backup account với roles writer/deleter/recovery và key permissions, để production runtime không thể xóa backups.

### Bài 9 — 3-2-1-1-0

Đề xuất kiến trúc đáp ứng heuristic cho dữ liệu Order, giải thích lớp nào bảo vệ node loss, region outage, ransomware và restore errors.

### Bài 10 — WORM

So object versioning, immutable retention và legal hold. Chúng bảo vệ khỏi những thao tác nào, còn rủi ro nào?

### Bài 11 — Key loss

Một backup được lưu 5 năm nhưng key bị xóa sau 1 năm. Tại sao bản sao vô dụng? Thiết kế key lifecycle policy.

### Bài 12 — Offline copy

Một bản offline được chép mỗi tuần. Nêu lợi ích, RPO tradeoff, key protection và cách kiểm định kỳ.

### Bài 13 — GFS

Thiết kế retention 48 giờ hourly, 30 ngày daily, 12 tuần weekly, 12 tháng monthly. Phân biệt restore points và chain dependencies.

### Bài 14 — Incremental base

F0 là full đã 45 ngày, I2 là incremental còn giữ. Có được xóa F0 theo policy 30 ngày không? Cần catalog chứng minh điều gì?

### Bài 15 — Synthetic full

Khi chain quá dài khiến restore lâu, nêu cách tạo base mới bằng công cụ hỗ trợ và những điều cần verify trước khi xóa chain cũ.

### Bài 16 — Manifest

Tạo schema manifest chứa ID, source version, consistentAt, parentBackupIds, checksum, repository/region, retentionUntil, keyRef và verification status.

### Bài 17 — Partial upload

Backup job upload 99/100 objects rồi crash nhưng báo exit code 0. Cần kiểm gì trước khi catalog công bố backup usable?

### Bài 18 — Restore drill

Lập kế hoạch khôi phục NoSQL sang region/account mới, gồm keys, schema, indexes, checksums, query correctness, traffic cutover và đo RTO.

### Bài 19 — Cross-tenant restore

Tenant A bị xóa nhầm, tenants B/C vẫn có writes hợp lệ. Vì sao rollback toàn cluster có thể gây mất dữ liệu? Thiết kế isolated restore và selective merge.

### Bài 20 — Erasure request

Một user yêu cầu xóa dữ liệu nhưng immutable backups còn 90 ngày. Phân biệt mục tiêu privacy, legal retention, access restriction và deletion replay khi restore.

### Bài 21 — Residency

Tenant chỉ cho lưu trong một quốc gia. Cần thiết kế offsite placement ngoài miền lỗi **nhưng vẫn trong vùng được phép** như thế nào?

### Bài 22 — MongoDB

Replica set có secondary lag và oplog window ngắn; backup ở cùng region. Thiết kế cải tiến retention/PITR, replication catch-up và offsite copy.

### Bài 23 — Cassandra

Snapshot hard-link ở node không được upload vì exporter lỗi. Tại sao dọn local snapshot trước khi upload verified nguy hiểm?

### Bài 24 — Redis

Redis dùng AOF và RDB trên cùng volume, chứa dữ liệu session có giá trị nghiệp vụ. Có đáp ứng offsite requirement chưa? Đề xuất đường backup.

### Bài 25 — DynamoDB

Phân biệt backup on-demand, PITR và cross-region/account copy theo khả năng dịch vụ. Nêu các thành phần phải khôi phục ngoài dữ liệu bảng.

### Bài 26 — Cosmos DB

Account có nhiều read regions; một operator nghĩ đó là backup. Giải thích replication và backup khác nhau, xét policy continuous/periodic được hỗ trợ.

### Bài 27 — Elasticsearch

Repository có incremental shared segments, quản trị viên định dùng storage lifecycle để xóa objects quá 30 ngày. Vì sao có thể phá snapshots còn giữ?

### Bài 28 — CDC

Kafka topic chỉ giữ 7 ngày và event không chứa full document. Có thể dùng làm backup cho source NoSQL bị mất sau 30 ngày không? Nêu những giả định còn thiếu.

### Bài 29 — Chi phí

Tính chi phí ước lượng cho 5 TB backup với hai storage tiers, egress, retrieval và restore drill. Giải thích vì sao chỉ lấy giá GB-tháng là chưa đủ.

### Bài 30 — RTO qua mạng

5 TB cần tải qua băng thông hiệu dụng 500 MB/s. Ước lượng thời gian download, rồi liệt kê các bước làm RTO thực tế lớn hơn.

### Bài 31 — Java policy

Viết JUnit tests cho `RetentionPlanner`: legalHold, immutableUntil, dependency, lastKnownGood và trạng thái upload unverified.

### Bài 32 — Race condition trong cleanup

Một incremental backup mới được tạo sau dry run, trước lúc xóa full cũ. Thiết kế revalidation và lock/transaction phù hợp.

### Bài 33 — Account compromise

Sản xuất bị chiếm quyền, backup ở account riêng nhưng dùng cùng KMS key quản lý từ production. Thiết kế lại key/admin trust.

### Bài 34 — Region outage

Một cluster cần chạy lại trong 2 giờ nhưng dữ liệu 10 TB ở archive class có retrieval 12 giờ. Đề xuất fast tier/standby hay tradeoff mục tiêu.

### Bài 35 — Deletion replay

Khôi phục snapshot 30 ngày trước đưa các users đã xóa trở lại. Thiết kế deletion ledger/reconciliation bảo đảm policy erasure sau restore.

### Bài 36 — Dashboard

Chọn 12 metrics để nhận ra backup hết hạn, offsite lag, restore failures, key access issues và retention chain gaps; xác định alert owners.

### Bài 37 — Review policy sai

Một policy viết: “Có 3 replicas nên không cần backup; snapshots giữ 365 ngày trong production account, admin có thể xóa mọi bản; chưa restore test nhưng job báo SUCCESS.” Chỉ ra từng thiếu sót và viết lại.

### Bài 38 — Tình huống tổng hợp

Thiết kế chính sách cho Java order service dùng MongoDB source, Kafka outbox, Redis cache và object-storage backup: RPO/RTO từng failure scenario, full/incremental/PITR, physical và logical placement, IAM/keys, immutable retention, cleanup approvals, restore drill và xử lý event replay.

---

**Kết luận:** Chính sách sao lưu NoSQL phải thiết kế đồng thời **thời gian lưu**, **vị trí lưu** và **khả năng bảo vệ bản sao**. Retention phải đủ để phục hồi sau lỗi được phát hiện muộn và phải giữ nguyên full/incremental/PITR dependencies; backup frequency và recovery granularity phải phù hợp RPO, trong khi restore process và tốc độ tải phải đáp ứng RTO. Bản sao ngoài miền lỗi không chỉ là “khác thư mục”: cần tách volume, node, AZ, region và khi cần **account, IAM, encryption keys, backup catalog và control plane**. Replication phục vụ availability nhưng không thay historical backup; immutability/WORM/offline copy làm giảm khả năng phá hủy nhưng không thay quyền truy cập, kiểm chứng integrity và diễn tập restore. **Chỉ coi một backup là lớp bảo vệ đáng tin khi đã xác định được phạm vi sự cố nó chịu được, thời điểm dữ liệu có thể khôi phục và một quy trình khôi phục đã được thử thành công.**
