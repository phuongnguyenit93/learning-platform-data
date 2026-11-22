# Lưu bản sao ngoài nút/cụm và bảo vệ quyền truy cập

## Mục tiêu và phạm vi

Apache Cassandra sao chép partition sang nhiều **replica** theo replication factor (RF), giúp hệ thống tiếp tục phục vụ khi một số node hỏng. Tuy nhiên, **replication không phải backup**: lệnh xóa nhầm, dữ liệu bị ghi đè, lỗi phần mềm hoặc thao tác quản trị sai có thể lan đến nhiều replica. Nếu mọi bản sao đều nằm trong cùng một failure domain, một sự cố hạ tầng hoặc tấn công ransomware vẫn có thể làm mất dữ liệu và cả khả năng phục hồi.

Vì thế, trong chương **Sao lưu và phục hồi** thuộc module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, bài này tập trung vào việc **đưa bản sao ra ngoài node/cluster** và **bảo vệ quyền truy cập vào bản sao**. Nội dung gắn với SSTable, partition key, CQL, replication/consistency level, compaction, repair, khôi phục dữ liệu và kiểm chứng từ ứng dụng Java.

Sau khi học, bạn có thể:

1. Phân biệt **replica**, **snapshot cục bộ**, **incremental backup**, **backup ở kho độc lập** và **khả năng khôi phục đã kiểm chứng**.
2. Thiết kế một luồng sao lưu có **manifest, checksum, schema, phiên bản, token/DC metadata**, trạng thái hoàn tất và kho lưu trữ độc lập.
3. Đánh giá rủi ro mất node, mất datacenter, xóa nhầm, lộ dữ liệu hoặc bị kẻ tấn công xóa cả bản sao lưu.
4. Áp dụng **mã hóa khi truyền/lưu trữ**, nguyên tắc quyền tối thiểu, phân tách danh tính, retention, immutability và audit.
5. Lập quy trình **backup → kiểm tra → lưu ngoài cụm → diễn tập restore → đối soát dữ liệu**, thay vì chỉ xác nhận lệnh copy trả thành công.
6. Xây lab CQL và dùng Java Driver kiểm chứng event ID/marker sau khi restore trong môi trường cách ly.

> **Giới hạn:** các lệnh bên dưới chỉ là mẫu cho **lab hoặc quy trình được phê duyệt**. Không tự thay đổi retention, xóa snapshot, sao chép dữ liệu nhạy cảm lên tài khoản cá nhân hoặc restore đè lên cluster đang phục vụ. Tham số `nodetool`, định dạng SSTable và quy trình restore cần đối chiếu đúng phiên bản Cassandra, môi trường và chính sách bảo mật của tổ chức.

## 1. Vì sao RF=3 và snapshot trên cùng node chưa đủ?

Giả sử một keyspace có RF=3 tại `dc_a`. Khi một node mất điện, hai replica còn lại có thể tiếp tục phục vụ một số consistency level như `LOCAL_QUORUM` nếu đủ điều kiện. Nhưng nhiều loại sự cố không đơn giản là “một node chết”:

| Sự cố | Replication giúp gì? | Vì sao vẫn cần backup độc lập? |
| --- | --- | --- |
| Một node mất kết nối, đĩa còn tốt | Replica khác tiếp tục phục vụ; có thể repair/rebuild | Để khôi phục nếu các bản sao khác cũng lỗi hoặc dữ liệu chỉ có ở node mất |
| Cả datacenter lỗi | Nếu cluster có replica ở DC khác, có thể failover | Ghi chỉ ACK local có thể chưa tới DC khác; DC dự phòng cũng có thể gặp sự cố |
| `DELETE` nhầm hoặc `TRUNCATE` nhầm | Mutation xóa có thể được sao chép như dữ liệu bình thường | Muốn quay về trạng thái trước khi xóa cần điểm khôi phục độc lập |
| Ứng dụng ghi đè giá trị sai | Các replica thường hội tụ về giá trị mới | Replica không lưu lịch sử nghiệp vụ bất biến để “undo” |
| Lỗi compaction/định dạng/phiên bản | Một số replica có thể còn bản sao tốt | Lỗi có thể ảnh hưởng diện rộng; cần dữ liệu và công cụ khôi phục khác đường chạy hiện tại |
| Ransomware chiếm tài khoản vận hành | Có thể chiếm quyền cả cluster | Nếu cùng quyền xóa snapshot/backup, kẻ tấn công xóa mọi bản sao |
| Xóa VM/volume/namespace do thao tác sai | Replica ở hạ tầng còn lại có thể sống | Snapshot chỉ nằm cùng volume/cluster có thể mất cùng hạ tầng |

### Bốn khái niệm phải tách bạch

- **Replica:** bản sao đang tham gia xử lý đọc/ghi theo topology và consistency level. Đây là cơ chế sẵn sàng/độ bền trong cụm, **không cung cấp lịch sử khôi phục độc lập**.
- **Snapshot Cassandra:** ảnh chụp các SSTable tại một thời điểm trên **node cục bộ**, thường dùng hard link và cơ chế tệp tin liên quan. Snapshot trong cùng data volume **chưa phải backup ngoài node**.
- **Backup đã xuất ra ngoài cluster:** các file/metadata cần thiết đã được chuyển tới kho lưu trữ tách failure domain, đủ quyền và điều kiện restore, có kiểm tra toàn vẹn.
- **Backup có thể phục hồi:** bản sao đã được **kiểm thử restore** trong môi trường phù hợp và đối soát với dữ liệu kỳ vọng. Một upload báo thành công chưa đạt cấp độ này.

**Đặc biệt:** snapshot giữ tham chiếu đến SSTable cũ; compaction có thể tạo SSTable mới nhưng không giải phóng được byte cũ còn bị snapshot giữ. Dung lượng backup và đĩa local phải được theo dõi riêng.

## 2. Những thành phần nào cần được bảo vệ?

Cassandra lưu mutation trước trong commit log/memtable, rồi flush thành các **SSTable**. Với backup dựa trên snapshot, phần dữ liệu được lưu thường là **các thành phần SSTable** tại điểm chụp; việc restore cần cả bối cảnh schema và topology thích hợp.

~~~mermaid
flowchart LR
    App["Ứng dụng CQL"] --> W["Commit log và memtable"]
    W -->|"Flush"| S["SSTable trên node"]
    S -->|"nodetool snapshot"| L["Snapshot cục bộ"]
    L -->|"Copy + checksum"| O["Kho backup ngoài cụm"]
    SCH["Schema + cấu hình khôi phục"] --> O
    MAN["Manifest + bằng chứng ACK"] --> O
    O -->|"Restore drill"| DR["Cluster thử nghiệm cách ly"]
    DR -->|"Đối soát marker"| V["Báo cáo PASS / GAP"]
~~~

### Danh mục thành phần

| Thành phần | Cần lưu lại gì? | Lý do |
| --- | --- | --- |
| **SSTable components** | `Data.db` và các thành phần đi kèm cùng descriptor, mọi SSTable thuộc snapshot đã chọn | Một file `Data.db` đơn lẻ không tương đương gói SSTable có thể restore |
| **Schema CQL** | Keyspace, bảng, partition/clustering key, UDT, index, tùy chọn bảng, RF theo DC | SSTable không tự cung cấp đầy đủ quy trình tạo lại môi trường |
| **Topology/phiên bản** | Cassandra version, SSTable format, DC/rack/snitch, node/host ID, token ranges nếu cần | Chọn phương pháp restore và bảo đảm replica placement hợp lệ |
| **Thời gian và phạm vi backup** | Tag snapshot, thời điểm start/end, node nào, keyspace/table nào | Snapshot nhiều node không mặc nhiên cùng một mốc transaction toàn cục |
| **Manifest file/checksum** | Danh sách đường dẫn tương đối, kích thước, SHA-256 và trạng thái upload | Phát hiện thiếu file, hỏng byte hoặc nhầm phiên bản |
| **Nguồn sự kiện/ACK** | Operation ID, primary key, marker, thời điểm ACK và trạng thái UNKNOWN | Đối soát completeness sau restore; có thể cần bảo vệ trong kho độc lập |
| **Cấu hình vận hành** | Loại snitch, driver DC, chính sách repair, backup automation, hướng dẫn restore | Hỗ trợ dựng lại cluster mà không khôi phục nhầm danh tính node |
| **Khóa mã hóa và quyền truy cập** | KMS key reference, phiên bản khóa, chính sách quyền, quy trình truy cập khẩn cấp | Dữ liệu mã hóa sẽ không restore được nếu không còn quyền giải mã |

**Không sao chép mù quáng toàn bộ system keyspaces từ cluster cũ vào cluster mới.** Một số bảng hệ thống chứa thông tin node/topology/identity gắn với cluster nguồn; việc khôi phục không đúng có thể gây sai membership hoặc danh tính. Schema, roles và permissions phải được khôi phục theo **quy trình phù hợp phiên bản**, kiểm tra kỹ dữ liệu nhạy cảm như nội dung `system_auth` nếu có.

### Snapshot khác incremental backup và commit log archive

| Phương pháp | Dùng cho | Không nên ngộ nhận |
| --- | --- | --- |
| **Snapshot định kỳ** | Điểm khôi phục đầy đủ tại các thời điểm được chọn | Snapshot chỉ trên đĩa local chưa chống mất node/cluster |
| **Incremental backups** | Lưu SSTable mới sau các flush theo cấu hình, bổ sung cho một mốc full thích hợp | Phải quản lý chuỗi file/phạm vi và restore dependency; không tự giải quyết PITR |
| **Commit log archiving/PITR** | Có thể hỗ trợ khôi phục gần thời điểm mong muốn nếu được thiết kế và thử nghiệm | Cần archive/replay đúng phiên bản, thời điểm, schema và sequencing; không mặc định đã có |
| **CDC/event log ứng dụng** | Hỗ trợ tái dựng các mutation/sự kiện theo logic nghiệp vụ | Không thay tự động backup SSTable hoặc schema đầy đủ |

Một kế hoạch backup phải nêu rõ **loại restore được hỗ trợ**: toàn cluster, một keyspace, một bảng, một số partition, hay phục hồi tại thời điểm (*point-in-time*). Không mặc nhiên coi “có snapshot” là đã hỗ trợ mọi loại.

## 3. Thiết kế failure domain cho kho ngoài cụm

### 3.1. Off-node chưa chắc đã off-cluster

Các vị trí lưu trữ có độ độc lập khác nhau:

| Nơi lưu | Chống mất một node? | Chống mất cả cluster/DC? | Rủi ro còn lại |
| --- | --- | --- | --- |
| Thư mục snapshot trên chính data volume | Không chắc | Không | Cùng disk, VM, quyền hệ thống |
| Volume phụ gắn với cùng VM | Có thể chống lỗi volume chính | Không chắc | Cùng host/tài khoản/region |
| NAS chung với Cassandra | Có thể chống mất một node | Phụ thuộc kiến trúc | Cùng mạng, credential, lỗi chia sẻ |
| Kho object độc lập khác account/project | Thường tốt hơn | Tùy region/replication | Mất credential, xóa nhầm, sai KMS |
| Kho ngoài region hoặc site có quyền tách biệt | Hỗ trợ DR khi mất vùng nguồn | Có thể | Phải đo restore speed, retention và khả năng truy cập |

**“Ngoài cụm” là tách failure domain thực tế**, không chỉ đặt prefix khác trên cùng bucket hoặc copy vào volume cùng node. Nên xác định độc lập tối thiểu ở bốn mặt: **hạ tầng**, **danh tính/quyền**, **khóa mã hóa** và **cơ chế xóa/retention**.

Ví dụ: backup từ cluster ở `dc_a` lên object storage tại region khác nhưng **dùng cùng tài khoản quản trị có quyền xóa bucket và khóa KMS** vẫn chưa có khả năng chống ransomware tốt. Thêm immutable retention và danh tính độc lập mới xử lý được một phần rủi ro này.

### 3.2. Sơ đồ một luồng sao lưu có trách nhiệm

~~~mermaid
flowchart TD
    N1["Node A1 snapshot"] --> T["Backup agent có quyền đọc hẹp"]
    N2["Node A2 snapshot"] --> T
    N3["Node A3 snapshot"] --> T
    T --> C["Băm file + manifest trên kênh tin cậy"]
    C --> U["Upload qua TLS"]
    U --> O["Kho object ngoài cluster"]
    O --> I["Retention / immutable / audit"]
    O --> Q["Tài khoản restore riêng"]
    Q --> R["Cluster phục hồi cách ly"]
    R --> V["Checksum + CQL đối soát"]
    V --> G{"Đạt RTO / RPO đã định?"}
    G -->|Có| P["Backup set được chấp nhận"]
    G -->|Không| F["Ghi GAP, sửa runbook"]
~~~

Sơ đồ là mẫu logic, không yêu cầu mọi node trực tiếp có quyền ghi ra Internet. Trong môi trường hạn chế, một backup agent nội bộ có thể thu từ snapshot qua mạng riêng, sau đó upload bằng danh tính được cấp quyền tối thiểu.

## 4. RPO, RTO và lịch backup phải được định nghĩa trước

**Recovery Point Objective (RPO)** là mức mất dữ liệu tối đa có thể chấp nhận, thường đo theo thời gian. **Recovery Time Objective (RTO)** là khoảng ngừng dịch vụ tối đa chấp nhận trước khi khôi phục phục vụ. Hai đại lượng này ảnh hưởng trực tiếp đến chiến lược sao lưu.

Ví dụ giả định:

- Snapshot đầy đủ mỗi 24 giờ, không có incremental/PITR. Nếu chỉ restore được snapshot gần nhất, **khoảng dữ liệu phát sinh sau mốc snapshot** có nguy cơ không được giữ trong bản phục hồi.
- Mục tiêu RPO 15 phút thì chỉ có snapshot ngày một lần thường **không đáp ứng**; cần lịch snapshot/incremental/commit log archive hoặc nguồn sự kiện khác, được kiểm thử thực tế.
- Backup đã đủ byte nhưng phải tải/stream vài TiB trong nhiều giờ có thể **không đạt RTO** nếu mục tiêu là phục vụ lại trong 30 phút.

### Đừng nhầm replication lag với RPO của backup

`LOCAL_QUORUM` ở DC A chỉ cần quorum local ACK; nó **không bảo đảm** write ngay lập tức có mặt ở DC B. Một backup lấy từ DC B tại thời điểm T có thể thiếu write vừa được ACK ở A nếu replica B chưa nhận mutation. Do đó cần biết **nguồn backup thuộc DC nào, dữ liệu nào đã hội tụ và nguồn manifest ACK nằm ở đâu**.

Đo:

~~~text
RPO observed (một tập event có thứ tự):
  = khoảng từ điểm dữ liệu mới nhất được phục hồi liên tục
    đến mốc sự cố

RTO observed:
  = T_dich_vu_hoat_dong_lai - T_bat_dau_anh_huong
~~~

Các phép tính trên phải đi cùng danh sách **event đã ACK nhưng MISSING/MISMATCH**. Nếu có lỗ hổng rải rác, chỉ một con số giây không biểu diễn hết mất mát. Read timeout trong khi đối soát là **READ_ERROR**, chưa phải bằng chứng dữ liệu đã mất.

| Yêu cầu nghiệp vụ | Hướng thiết kế |
| --- | --- |
| Chỉ cần restore một bản cuối ngày | Full snapshot định kỳ và export off-cluster, test restore |
| Mất tối đa vài phút dữ liệu | Kết hợp cơ chế gần thời gian thực được hỗ trợ và kiểm chứng, ví dụ event log/PITR có kế hoạch |
| Mất một DC nhưng phục vụ trong ít phút | Ngoài backup còn cần kiến trúc ứng dụng failover, data placement và route/CL phù hợp |
| Ransomware có quyền quản trị cluster | Kho tách quyền, immutability, key separation, audit và bản phục hồi đã kiểm thử |
| Yêu cầu xóa dữ liệu theo chính sách | Retention/expiry của backup, restore-time deletion reconciliation và quy trình xử lý dữ liệu nhạy cảm |

## 5. Một backup set đáng tin cần có manifest

Không nên đặt tên `backup-final-new.zip` rồi chỉ lưu một tập file không rõ nguồn. Một **backup set** cần có ID duy nhất và manifest:

~~~yaml
# Ví dụ cấu trúc MANIFEST, không phải schema do Cassandra tự sinh.
backup_id: cassandra-lab-20261121T100000Z
status: COMPLETE
cluster_label: lab-cassandra
cassandra_version: "4.x-example"
keyspace: backup_lab
tables:
  - events_by_run
snapshot_tag: drill-20261121-01
source_dc: datacenter1
source_nodes:
  - node-a
  - node-b
  - node-c
started_at_utc: "2026-11-21T10:00:00Z"
completed_at_utc: "2026-11-21T10:03:00Z"
files:
  - path: node-a/backup_lab/events_by_run-UUID/snapshots/drill-20261121-01/xx-Data.db
    bytes: 12345678
    sha256: "64-hex-characters-computed-at-backup-time"
metadata:
  schema_export: schema.cql
  restore_instructions: runbook-version-7
  encryption_key_reference: "kms:backup-key-alias"
~~~

Đây là **mẫu minh họa**: file path, kích thước và checksum không phải dữ liệu thật. Một manifest thực tế cần một bản ghi **cho từng file** của tất cả SSTable components, tên node/table UUID, checksum tính thật, version và quyết định về phạm vi snapshot. Nó nên được **ký số hoặc bảo vệ tính toàn vẹn**, tránh kẻ tấn công sửa cả dữ liệu lẫn danh sách checksum.

### Trạng thái xuất bản backup set

~~~mermaid
flowchart LR
    A["PLANNED"] --> B["SNAPSHOTTING"]
    B --> C["COPYING"]
    C --> D["VERIFYING"]
    D --> E["COMPLETE"]
    B --> X["FAILED / INCOMPLETE"]
    C --> X
    D --> X
    E --> R["RESTORE_TESTED"]
    R --> Z["RETENTION / EXPIRE theo chính sách"]
~~~

**Chỉ phát hành trạng thái `COMPLETE` sau khi** danh sách file, checksum, upload và metadata thiết yếu khớp với manifest. Một file thiếu, một node bỏ sót, một checksum sai hoặc thiếu schema phải làm set **INCOMPLETE** với lỗi cụ thể. Tránh hiển thị “backup thành công” chỉ vì quá trình snapshot trên node A hoàn tất.

Số node cần snapshot phụ thuộc mục tiêu restore và phạm vi dữ liệu. **Snapshot một node của cluster RF=3 không bao phủ mọi partition** nếu node đó không là replica cho mọi token range. Với bài toán khôi phục toàn keyspace/cluster, cần kế hoạch đảm bảo **tất cả token ranges và bản sao cần thiết** đều được thu đủ, thường dựa trên nhiều node và metadata topology, không phải chọn một node ngẫu nhiên.

## 6. Lab CQL: tạo marker dùng để kiểm chứng backup

Giả sử cluster lab có ba node trong DC tên `datacenter1`, dùng Cassandra phiên bản thống nhất. Nếu topology thực khác, thay RF và tên DC cho đúng; không cố RF=3 trên một node rồi kỳ vọng `LOCAL_QUORUM` hoạt động như ba bản sao.

### 6.1. Kiểm tra cluster

~~~bash
nodetool status
nodetool describecluster
~~~

Trước khi snapshot, ghi tình trạng node `UN` (*Up/Normal*), đường dẫn dữ liệu theo cấu hình thực tế và các hoạt động compaction/repair/streaming có ảnh hưởng. Kiểm tra DC/version trong `cqlsh`:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` phản ánh **node đang trả lời**, không phải thông tin của mọi node. Nếu đang nâng cấp rolling, cần kiểm tra bản tương thích trên tất cả node liên quan.

### 6.2. Tạo bảng theo một partition nhỏ

~~~sql
CREATE KEYSPACE IF NOT EXISTS backup_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS backup_lab.events_by_run (
    run_id text,
    event_id uuid,
    marker text,
    payload text,
    origin text,
    PRIMARY KEY ((run_id), event_id)
);
~~~

- `run_id` là **partition key**, cô lập mỗi lượt thử nghiệm.
- `event_id` là clustering key, làm định danh ổn định khi đối soát.
- `marker` là giá trị ngắn từ nguồn độc lập, không chứa dữ liệu nhạy cảm.
- `payload` chỉ là dữ liệu minh họa; không lưu credential/API token vào bảng lab.
- Không sử dụng TTL hoặc `DELETE` trong lab cơ bản để không trộn chi phí thu hồi dữ liệu với kỹ thuật backup.

**Nếu keyspace/bảng đã tồn tại**, `IF NOT EXISTS` không cập nhật replication hay cấu trúc cũ. Kiểm tra:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'backup_lab';
~~~

### 6.3. Ghi marker ở CL được xác nhận

Trong `cqlsh`:

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO backup_lab.events_by_run
    (run_id, event_id, marker, payload, origin)
VALUES (
    'backup-drill-01',
    11111111-1111-4111-8111-111111111111,
    'BASELINE-A', 'first-known-record', 'lab-writer'
);

INSERT INTO backup_lab.events_by_run
    (run_id, event_id, marker, payload, origin)
VALUES (
    'backup-drill-01',
    22222222-2222-4222-8222-222222222222,
    'BASELINE-B', 'second-known-record', 'lab-writer'
);
~~~

`CONSISTENCY ALL` là lệnh của `cqlsh`; với RF3, yêu cầu ba replica ACK. Chỉ đưa event vào tập **đã ACK** nếu lệnh thực sự trả thành công. Timeout được gắn **UNKNOWN_WRITE**, không mặc định là chưa ghi hoặc đã ghi. Dùng `run_id` mới cho mỗi lượt test để không nhầm với dữ liệu còn từ lần trước.

Kiểm tra baseline:

~~~sql
SELECT event_id, marker
FROM backup_lab.events_by_run
WHERE run_id = 'backup-drill-01';
~~~

Ghi manifest **ngoài Cassandra** gồm `run_id`, `event_id`, `marker`, CL, kết quả ACK thực tế và thời điểm. Manifest nguồn nghiệp vụ giúp phát hiện backup/restore thiếu một event đã được xác nhận. **Đọc hai marker trước backup** không bảo đảm toàn bộ bảng hoặc cluster đã hoàn tất backup.

## 7. Tạo snapshot và chuyển file ra kho ngoài cụm

### 7.1. Chọn điểm chụp và schema

Với bài lab, ngừng writer mới hoặc chốt tập marker dự kiến trước khi chụp, để đối chiếu đơn giản. Trong production, snapshot của nhiều node **không phải một transaction/snapshot toàn cluster nguyên tử**: mỗi node chụp tại thời điểm riêng và write đang bay có thể đã đến một vài replica.

Trước khi copy, xuất schema/keyspace definition và danh sách phiên bản node bằng công cụ quản trị được duyệt. Trong `cqlsh`, có thể dùng:

~~~text
DESCRIBE KEYSPACE backup_lab;
~~~

`DESCRIBE` là lệnh của `cqlsh`, **không phải CQL có thể gửi như một prepared statement từ Java**. Ngoài DDL, cần lưu khung bảo mật/roles và cấu hình khôi phục phù hợp theo runbook; không ghi plaintext secret cùng bộ SSTable khi có thể tách ra.

### 7.2. Tạo snapshot trên những node cần thiết

Ví dụ từ **mỗi node được chọn của lab**, thực hiện theo đúng quy trình đã ghi trong manifest:

~~~bash
# Kiểm tra phiên bản nodetool và option trước khi dùng.
nodetool help snapshot

# Cú pháp thường gặp: chụp một bảng với tag.
nodetool snapshot -t drill-20261121-01 -cf events_by_run backup_lab

# Quan sát snapshot đã được đăng ký trên node đang thao tác.
nodetool listsnapshots
~~~

Thông thường `nodetool snapshot` flush dữ liệu còn trong memtable của bảng trước khi chụp, trừ khi chọn tùy chọn **skip flush** nếu phiên bản hỗ trợ. Nếu bỏ qua flush, các mutation chưa flush có thể không nằm trong các SSTable được snapshot; phải nêu rõ cấu hình và tác động đến RPO. **Snapshot không tự kết hợp trạng thái của mọi node thành ảnh chụp nhất quán về mặt nghiệp vụ.**

Trên mỗi node, snapshot thường nằm dưới thư mục bảng:

~~~text
<data_directory>/<keyspace>/<table>-<table_uuid>/
  snapshots/<tag>/
    <descriptor>-Data.db
    <descriptor>-Index.db
    <descriptor>-Statistics.db
    <descriptor>-TOC.txt
    ... các SSTable components khác tùy version/format ...
~~~

Một bảng có thể nằm trên nhiều `data_directories` hoặc có nhiều descriptor; **không chọn một file `Data.db` duy nhất** rồi xem như đã backup cả bảng. Khi backup nhiều node, đặt prefix theo **node ID/host ID + DC + backup ID**, tránh ghi đè các tệp trùng tên từ các node khác nhau.

### 7.3. Sao chép an toàn, có giới hạn quyền

Lý tưởng, snapshot được chuyển qua **kênh TLS hoặc đường truyền bảo mật tương đương** vào một kho backup **ngoài node/cluster**. Backup agent có quyền đọc thư mục snapshot, nhưng không cần quyền chỉnh sửa SSTable live.

Ví dụ dùng object storage tương thích Amazon S3 trong lab (đây là mẫu, không yêu cầu nhà cung cấp cụ thể):

~~~bash
# Chỉ minh họa: SNAP_DIR phải là snapshot đã xác minh.
# AWS CLI phải dùng identity/role của backup agent, không chứa key trong script.
SNAP_DIR="/var/lib/cassandra/data/backup_lab/events_by_run-<table_uuid>/snapshots/drill-20261121-01"
DEST="s3://<protected-backup-bucket>/cassandra/lab-20261121/node-a/events_by_run/"

# Bucket đã cấu hình chính sách retention, access control và KMS.
aws s3 cp "$SNAP_DIR/" "$DEST" \
  --recursive \
  --sse aws:kms \
  --sse-kms-key-id "alias/backup-kms-key"
~~~

Đây là ví dụ **cú pháp upload**, không chứng minh mọi file đã đủ hay upload có tính atomic. Phải xác thực đích/cấu hình IAM, phiên bản CLI và chính sách KMS trước khi chạy. Với snapshot lớn, nên dùng backup tool có retry, checkpoint, rate limit, checksum và log từng file.

**Không lưu access key/secret vào biến literal của script**, image container, lệnh shell được ghi lịch sử hoặc output của job. Ưu tiên workload identity/instance role với credential ngắn hạn, giới hạn theo bucket/prefix và có thể thu hồi.

### 7.4. Kiểm tra checksum và tính đầy đủ

Đối với từng file trong snapshot:

1. Ghi **đường dẫn tương đối**, bytes và **SHA-256** tính từ nguồn ổn định.
2. Upload và xác nhận object metadata/size/checksum hoặc **đọc lại byte từ đích và băm lại** theo phương pháp hỗ trợ.
3. Đảm bảo không thiếu descriptor/component, node/bảng/range mong muốn và metadata/schema.
4. Kiểm tra **tính toàn vẹn của manifest** (ký số hoặc lưu ở vùng có quyền tách biệt/immutability).
5. Chỉ khi đã đối soát đủ mới ghi trạng thái `COMPLETE` ra catalog backup.

Ví dụ kiểm tra một file trên nguồn/đích sau khi đã lấy về nơi kiểm tra cách ly:

~~~bash
# Hai tệp đại diện cùng một SSTable component; đường dẫn ví dụ.
sha256sum "/path/source-snapshot/xx-Data.db"
sha256sum "/path/verified-download/xx-Data.db"
~~~

**Không dựa vào S3 ETag như một checksum MD5 đáng tin trong mọi tình huống**: multipart upload và chế độ mã hóa có thể làm ETag mang ngữ nghĩa khác. Chọn checksum algorithm/API phù hợp và **kiểm chứng phép đối chiếu từ đầu tới cuối** theo chính sách lưu trữ.

> Snapshot có thể được tạo/giữ bằng hard link tới SSTable trên cùng volume. **Copy file tới object storage** phải tạo bản sao độc lập; chỉ tạo hard link trong cùng máy rồi coi là offsite backup là sai.

## 8. Bảo vệ quyền truy cập: ai được đọc, ghi, xóa và restore?

Backup Cassandra thường chứa dữ liệu thực của khách hàng, trong đó có thể có PII, token nghiệp vụ, thông tin giao dịch hoặc lịch sử xóa. Thậm chí một bản snapshot cũ có thể chứa byte dữ liệu đã không còn được `SELECT` trả về do tombstone/TTL. Vì vậy, **quyền truy cập backup phải ít nhất nghiêm ngặt như quyền đọc dữ liệu production**.

### 8.1. Phân quyền theo vai trò, không theo một tài khoản admin chung

| Vai trò | Quyền cần thiết | Quyền nên tránh |
| --- | --- | --- |
| **Snapshot operator** | Chạy snapshot trên node/bảng được phê duyệt, đọc trạng thái | Tự xóa backup toàn hệ thống hoặc đổi KMS |
| **Backup writer/agent** | Đọc snapshot nguồn; ghi object vào prefix được cấp; tạo metadata cần thiết | Delete/overwrite retention, sửa bucket policy, admin cluster |
| **Backup auditor** | Xem catalog, checksums, logs, trạng thái, báo cáo restore | Đọc payload nhạy cảm nếu không cần; delete object |
| **Restore operator** | Đọc backup trong phạm vi được duyệt, decrypt theo thủ tục, chạy restore vào cluster cách ly | Tùy tiện restore đè production hoặc sửa retention |
| **Security/KMS admin** | Quản lý key policy, giám sát và cấp quyền decrypt có phê duyệt | Quyền đọc mọi dataset và xóa backup cùng lúc nếu không cần |
| **Retention administrator** | Quản lý lịch lưu giữ theo chính sách/tách nhiệm vụ | Một mình xóa mọi bản sao bất biến trước hạn |

Tổ chức nên dùng **phân tách trách nhiệm** và **two-person approval** cho các thao tác phá hủy hoặc truy cập dữ liệu nhạy cảm quy mô lớn. Một tài khoản có thể vừa ghi, sửa manifest, xóa object, vô hiệu hóa retention và hủy KMS key sẽ là **điểm lỗi chung về bảo mật**.

### 8.2. Quyền tối thiểu ở ba lớp

1. **Cassandra/node:** backup agent chỉ đọc đúng thư mục snapshot và metadata cần thiết; tài khoản vận hành không được mặc nhiên có quyền chạy mọi thao tác destructive.
2. **Kho backup:** quyền ghi theo prefix/backup ID, đọc hạn chế, xóa bị khóa hoặc tách role. Bucket/project phải chặn public access.
3. **KMS/credential:** chỉ các job cần mã hóa/giải mã mới được quyền phù hợp, key policy và rotation/lifecycle độc lập, có audit truy cập khóa.

**Mã hóa không thay phân quyền.** Nếu người dùng có quyền giải mã và tải toàn bộ SSTable, backup mã hóa vẫn có thể bị lộ dữ liệu. Ngược lại, IAM đúng nhưng backup copy qua đường truyền không mã hóa có thể lộ nội dung khi đi qua mạng không tin cậy.

### 8.3. Mã hóa khi truyền và khi lưu

- **In transit:** TLS cho kết nối tới object storage; mã hóa tuyến truyền từ node tới backup collector. Xác thực certificate/hostname, tránh bỏ qua TLS verification.
- **At rest:** server-side encryption với KMS hoặc client-side encryption theo chính sách. Kiểm tra key ID/region và quyền decrypt cho tài khoản phục hồi.
- **Key separation:** khóa của kho backup nên được quản lý tách quyền khỏi credential vận hành Cassandra để tránh cùng một sự cố làm mất cả data và key.
- **Key lifecycle:** backup còn retention 90 ngày nhưng KMS key bị hủy sau 30 ngày sẽ **không thể khôi phục**, dù object vẫn nguyên vẹn.
- **Metadata và logs:** manifest/trace có thể tiết lộ host IDs, cấu trúc bảng, tenant IDs; bảo vệ mức tương xứng và tránh log payload.

Khi dùng client-side encryption, checksum phải ghi rõ tính trên **plaintext hay ciphertext** và cách kiểm chứng sau giải mã. Tránh tạo một quy trình nhìn checksum khớp nhưng thực tế không còn mật khẩu/khóa để decrypt.

## 9. Immutability, retention, versioning và chống xóa nhầm

Một tác nhân có quyền xóa hoặc ghi đè backup có thể làm mất khả năng phục hồi ngay cả khi đã chuyển dữ liệu sang region khác. Vì vậy:

- **Versioning:** giữ các phiên bản object/manifest, giúp giảm rủi ro overwrite; nhưng versioning riêng lẻ **không đủ** nếu tài khoản có quyền xóa mọi version.
- **Retention/immutability:** dùng tính năng như Object Lock/WORM nếu nhà cung cấp hỗ trợ, với kỳ hạn và chế độ phù hợp. Cần cấu hình trước và **thử nghiệm** bằng tài khoản backup writer để chứng minh không thể xóa trước hạn.
- **Tách delete permissions:** job backup hàng ngày thường chỉ cần ghi, không cần xóa. Xóa theo retention nên dùng tác nhân/quy trình riêng đã phê duyệt.
- **Cross-account/cross-region copy:** cân nhắc nhiều failure domain khi mục tiêu chống mất vùng hoặc chiếm quyền tài khoản.
- **Audit bất biến:** ghi các hoạt động upload, download, list, delete, policy change, key use, restore và kết quả kiểm chứng; log nên nằm ngoài vùng kẻ tấn công dễ xóa.
- **Restore-read access:** tài khoản khôi phục cần đọc đủ dữ liệu đúng lúc sự cố; nếu policy chỉ cho backup agent ghi mà không có ai được decrypt, quy trình DR vẫn thất bại.

### Thế nào là chính sách retention đúng?

Giữ bản sao càng lâu không phải lúc nào cũng tốt. Phải cân nhắc:

| Yêu cầu | Tác động |
| --- | --- |
| Khôi phục do xóa nhầm phát hiện muộn | Cần đủ lịch sử để quay về một điểm trước khi xóa |
| Chi phí và dung lượng | Full/incremental/compaction có thể tăng nhanh dung lượng |
| Quy định lưu trữ và xóa dữ liệu | Giới hạn thời gian lưu, quy trình xóa/ẩn sau restore |
| Ransomware | Cần ít nhất một khoảng retention bất biến vượt thời gian phát hiện tấn công |
| KMS key lifetime | Giữ khóa decrypt phù hợp với toàn bộ thời gian backup còn tồn tại |
| Backup format compatibility | Có kế hoạch migrate/restore khi nâng cấp nhiều phiên bản Cassandra |

**Đối với yêu cầu xóa dữ liệu cá nhân:** backup bất biến có thể giữ bản ghi đã xóa trên cluster trong thời hạn được phép. Phải có chính sách retention và quy trình **không tái phát hành dữ liệu đã bị yêu cầu xóa khi restore**; ví dụ đối soát danh sách erasure requests sau phục hồi trước khi mở dịch vụ. Không được hứa rằng `DELETE` trong Cassandra sẽ lập tức xóa byte khỏi mọi backup lịch sử.

## 10. Giữ snapshot local an toàn mà không đầy ổ đĩa

Snapshot Cassandra thường không copy ngay toàn bộ data vào một thư mục thứ hai; nhiều SSTable components được tham chiếu bằng hard link. Điều này ban đầu tiết kiệm không gian, nhưng sau compaction các file cũ có thể **không được thu hồi** khi snapshot còn giữ link.

Theo dõi:

~~~bash
# Quan sát trên node thuộc lab/cluster được phép.
nodetool listsnapshots
nodetool tablestats backup_lab.events_by_run
nodetool compactionstats
~~~

Điều kiện trước khi dọn snapshot:

1. Catalog đã đánh dấu backup set **COMPLETE** và bản copy ngoài cụm đã qua checksum.
2. Chính sách lưu giữ bằng chứng và các phiên bản backup trước đã được kiểm tra.
3. Không có restore/drill hay incident đang dùng snapshot local đó.
4. Người có quyền phê duyệt xác nhận đúng **tag/keyspace/node** cần dọn.

Mẫu lệnh quản trị (không chạy nếu chưa xác nhận ở trên):

~~~bash
# Chỉ minh họa cú pháp thường gặp; kiểm tra nodetool help clearsnapshot.
nodetool clearsnapshot -t drill-20261121-01 backup_lab
~~~

**Không xóa bằng `rm -rf` theo glob mơ hồ trong data directory.** Dọn snapshot sai có thể loại bằng chứng và điểm phục hồi cục bộ, trong khi upload ngoài cụm chưa đủ file. Trong production, ưu tiên automation có xác nhận tag cụ thể và audit.

## 11. Diễn tập phục hồi: cách chứng minh bản sao dùng được

### 11.1. Khôi phục trong môi trường cách ly

Một bài diễn tập restore tốt **không phục hồi đè lên cluster production**. Dùng cluster/namespace/network riêng, kiểm soát truy cập, giới hạn egress và không kết nối các consumer nghiệp vụ thật.

Các bước tổng quát:

1. **Chọn backup set `COMPLETE`**, ghi mục tiêu restore, RPO/RTO, phạm vi keyspace/table, chủ sở hữu.
2. **Xác thực quyền truy cập và khóa giải mã** bằng tài khoản restore riêng; kiểm tra TLS, KMS, audit.
3. **Đọc catalog/manifest**, kiểm tra đủ node/file, bytes, checksum, schema, version và thông tin DC/token cần thiết.
4. **Tải file xuống vùng cách ly**, giải mã và kiểm tra lại checksum từ đầu tới cuối.
5. **Tạo schema phù hợp** trong cluster đích bằng quy trình đã duyệt; tránh copy `system.local`/`system.peers` hoặc dữ liệu định danh node cũ vào cluster mới.
6. **Nạp SSTable bằng quy trình restore đúng phiên bản**, có thể là công cụ streaming như `sstableloader` khi phù hợp, hoặc cơ chế restore node/backup tool được hỗ trợ; không tự copy file vào data directory live rồi khởi động tùy tiện.
7. **Chờ streaming/repair cần thiết**, kiểm tra replica placement và node health. Repair không thể tạo lại dữ liệu đã thiếu ở mọi bản sao/nguồn.
8. **Đối soát bằng CQL/Java** theo các event ID đã ACK, thêm kiểm tra schema, TTL/tombstone và một số partition đại diện.
9. **Đo thời gian thực tế** từ mốc bắt đầu restore đến khi synthetic reads/writes trong cluster thử nghiệm đạt điều kiện.
10. **Lưu báo cáo PASS/GAP**: có thể mở dịch vụ hay còn sự kiện thiếu, quyền lỗi, khóa KMS mất, công cụ version không tương thích?

**Phân biệt phương pháp:** khôi phục từng node bằng copy data directory, khôi phục từ SSTable qua streaming và khôi phục toàn cluster theo backup tool là những quy trình khác nhau. Chọn theo version, topology, phạm vi và yêu cầu consistency. Không sao chép tên node/host ID/bootstrapping state giữa cluster nguồn và đích khi chưa có quy trình được xác nhận.

### 11.2. Điều cần kiểm tra ngoài “query trả về”

| Hạng mục | Tiêu chí kiểm chứng |
| --- | --- |
| File | Số file/bytes/checksum từ đích khớp manifest |
| Bảo mật | Đúng role có thể decrypt/restore; role không được cấp quyền vẫn bị từ chối |
| Schema | Primary key, clustering, TTL/compaction/replication phù hợp; UDT/index cần thiết sẵn sàng |
| Dữ liệu | Các event đã ACK trong manifest trả đúng marker theo CL; không gộp READ_ERROR thành MISSING |
| Dữ liệu đã xóa | Xử lý tombstone/TTL đúng và không tái hiện dữ liệu phải bị xóa |
| Topology | Replica đúng DC/RF, node trạng thái ổn, không có streaming lỗi |
| Khả năng phục vụ | Latency, error rate, throughput synthetic tại mức đã định |
| Thời gian | RTO và RPO thực đo được, có lưu mốc thời gian chính xác |
| Quy trình | Không cần secret/person cụ thể không sẵn sàng mới có thể restore |

### 11.3. Biên bản RPO/RTO minh họa

Giả sử một lab có 100 event trong manifest, đều đã nhận ACK trước snapshot. Sau restore:

| Kết quả quan sát giả định | Số lượng |
| --- | ---: |
| `FOUND_MATCH` | 97 |
| `MISSING` | 1 |
| `MISMATCH` | 0 |
| `READ_ERROR` | 2 |

Kết luận đúng là **97 event đã được xác minh đúng, một event chưa tìm thấy tại CL/thời điểm kiểm tra, hai event chưa thể xác minh do lỗi đọc**. Không được báo “mất ba event” hoặc “restore đạt 97% độ đầy đủ cuối cùng”. Để tính RPO theo thời gian phải đối chiếu **timestamp ACK có thứ tự và danh sách ID cụ thể**; chỉ số tổng hợp chưa đủ.

## 12. Java Driver: đối soát marker sau khi restore

Java Driver 4.x có thể kiểm chứng những khóa kỳ vọng trong cluster **phục hồi cách ly**, không phải trong cluster nguồn đang hỏng. Đoạn mã dưới dùng **prepared statement**, `LOCAL_QUORUM` và phân loại kết quả riêng. Giả sử `CqlSession` đã được cấu hình contact points, local DC, TLS/auth và kết nối tới cluster phục hồi; đối với lab một node phải chọn CL tương ứng topology thực.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.util.UUID;

public final class BackupRestoreProbe {
    public enum Check { FOUND_MATCH, MISSING, MISMATCH, READ_ERROR }
    public record Expected(String runId, UUID eventId, String marker) {}

    private final CqlSession session;
    private final PreparedStatement select;

    public BackupRestoreProbe(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT marker FROM backup_lab.events_by_run " +
            "WHERE run_id = ? AND event_id = ?");
    }

    public Check check(Expected event) {
        BoundStatement query = select.bind(
                event.runId(), event.eventId())
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(true);
        try {
            Row row = session.execute(query).one();
            if (row == null) {
                return Check.MISSING;
            }
            String actual = row.getString("marker");
            return event.marker().equals(actual)
                ? Check.FOUND_MATCH : Check.MISMATCH;
        } catch (RuntimeException e) {
            System.err.printf(
                "READ_ERROR run=%s event=%s cause=%s%n",
                event.runId(), event.eventId(),
                e.getClass().getSimpleName());
            return Check.READ_ERROR;
        }
    }
}
~~~

Điểm cần nhớ:

- Danh sách `Expected` phải được **lưu bên ngoài Cassandra** hoặc nguồn giao dịch đáng tin, không dựng lại từ chính bảng đang restore rồi tự tuyên bố đầy đủ.
- `MISSING` là SELECT hoàn tất mà không có hàng; có thể đúng với event đã DELETE hợp lệ. Manifest cần chứa cả trạng thái xóa/hết hạn mong đợi.
- `READ_ERROR` là timeout, unavailable hoặc lỗi khác; **không cộng vào MISSING**. Ghi thêm CL, thời điểm, coordinator và mã lỗi để điều tra.
- Một lần `FOUND_MATCH` ở quorum chứng minh kết quả đọc của khóa đó tại CL đang dùng, **không chứng minh mọi replica hoặc toàn bộ bảng đã giống nhau**.
- Tái sử dụng `CqlSession` và `PreparedStatement`. Nếu manifest có hàng triệu khóa, kiểm tra theo bucket/giới hạn concurrency, không phát hàng triệu query đồng thời làm cluster restore quá tải.
- Đừng đưa marker chứa PII/secret vào log. Dữ liệu audit đối soát cũng cần retention, quyền và mã hóa thích hợp.

## 13. Tình huống sự cố và cách chẩn đoán

| Triệu chứng | Khả năng và cách kiểm tra | Hành động đúng |
| --- | --- | --- |
| Backup job `SUCCESS` nhưng không có snapshot của node B | Job chỉ kiểm tra exit code upload node A; manifest không bao phủ mọi node/range | Đánh dấu set INCOMPLETE, chụp/copy phần còn thiếu, kiểm chứng lại |
| Object storage có file nhưng tải về checksum khác | Upload lỗi, file sai hoặc metadata thiếu; ETag bị hiểu sai | So source SHA-256 và checksum sau download, không publish COMPLETE |
| Snapshot chỉ nằm trong thư mục local | Chưa có bước off-node/off-cluster | Copy tới kho tách failure domain và xác minh |
| Backup mất sau khi admin account bị lộ | Writer có cả quyền xóa/đổi retention/key | Tách IAM/KMS và retention bất biến, audit và kiểm thử quyền từ chối |
| Restore tool không đọc SSTable | Phiên bản/format/schema/config khác hoặc file thiếu | Kiểm tra manifest/compatibility, không tự sửa byte SSTable |
| Restore thành công nhưng query thiếu marker | Snapshot trước ACK hoặc phạm vi backup thiếu; có mutation chưa flush hay bị xóa hợp lệ | Đối soát mốc ACK, snapshot flush, file/range, event log |
| Restore dữ liệu nhưng không truy cập được | KMS key/role/TLS/secrets/config thiếu | Kiểm tra key lifecycle, role break-glass và quyền restore |
| Disk local tăng mạnh sau snapshot | Hard links giữ SSTable cũ sau compaction | Đối chiếu backup COMPLETE rồi dọn đúng tag theo chính sách |
| DC nguồn gặp outage, backup ở cùng vùng không truy cập được | Failure domain chưa đủ độc lập | Lập bản sao ở vùng/site phù hợp, diễn tập khôi phục khi source unavailable |
| Restore làm tái hiện dữ liệu đã yêu cầu xóa | Backup giữ lịch sử cũ hơn mutation xóa | Áp dụng nhật ký erasure/retention và kiểm soát phát hành dữ liệu sau restore |
| Backup bị đọc bởi người không được phép | IAM/KMS quá rộng, bucket public, audit kém | Thu hồi quyền/credential, điều tra truy cập, đóng lỗ hổng và báo cáo sự cố |

### Một lỗi cần phân tích riêng: backup nhất quán về file nhưng không nhất quán về nghiệp vụ

Một snapshot trên node A tại T1 và node B tại T2 có thể đều hợp lệ vật lý. Tuy nhiên, giữa T1 và T2 ứng dụng đã ghi một giao dịch vào nhiều partition/bảng. Tập SSTable từ hai node **không tạo ra snapshot giao dịch toàn cluster**. Tùy phương pháp restore, giá trị nghiệp vụ có thể không khớp mong đợi.

Giải pháp không phải “chạy `nodetool repair` là tự tạo transaction”, mà là **xác định mốc khôi phục/nguồn sự thật, thiết kế consistency, quiesce writers khi có thể, hoặc có event log/outbox để replay/đối soát**. Hệ thống yêu cầu tính nhất quán liên-bảng nghiêm ngặt cần thiết kế ứng dụng phù hợp ngay từ đầu.

## 14. Checklist vận hành cho một backup set

### Trước backup

- [ ] Biết RPO/RTO mục tiêu, phạm vi keyspace/table/DC và người chịu trách nhiệm.
- [ ] Có schema export, Cassandra version, SSTable format, RF/token metadata và restore runbook.
- [ ] Node/cluster đủ khỏe, disk headroom cho snapshot/compaction và tải upload.
- [ ] Đã định nghĩa nguồn manifest ACK hoặc event log ngoài cluster.
- [ ] Danh tính backup agent được cấp quyền đọc snapshot và ghi kho đích **theo nguyên tắc tối thiểu**.
- [ ] Kho đích có mã hóa/TLS, retention, logging, KMS key còn hiệu lực và chặn public access.

### Trong và sau backup

- [ ] Snapshot được chụp trên **đủ node/range** theo kế hoạch, tag/time rõ ràng.
- [ ] Mọi SSTable components của snapshot được liệt kê và copy; không bỏ sót thư mục dữ liệu khác.
- [ ] Manifest chứa file list, bytes, checksums, cluster/node/DC, schema và trạng thái.
- [ ] Kiểm chứng upload/checksum từ đích, không chỉ tin log `copy succeeded`.
- [ ] Chỉ publish `COMPLETE` khi đủ điều kiện; failure được giữ trạng thái INCOMPLETE.
- [ ] Không có credential bí mật/PII lọt vào logs, manifest chia sẻ hoặc chat.
- [ ] Snapshot local được dọn **sau** khi backup off-cluster đủ điều kiện và retention cho phép.

### Định kỳ

- [ ] Diễn tập restore bằng **identity riêng**, trong cluster cách ly.
- [ ] Đối soát marker và dữ liệu đã xóa/hết hạn; không đồng nhất read error với missing.
- [ ] Đo RPO/RTO và băng thông restore thực tế, sửa runbook khi không đạt.
- [ ] Kiểm thử quyền từ chối delete/overwrite và quyền decrypt cần thiết.
- [ ] Kiểm tra vòng đời KMS key, backup format, giữ bản bất biến và hạn dùng.
- [ ] Rà soát quyền của người rời nhóm, access logs, cảnh báo tải xuống bất thường.

## 15. Bài thực hành và câu hỏi tự kiểm tra

**Bài 1 — Replica hay backup?** Cluster RF=3 đặt cả ba replica trên các máy trong cùng một datacenter. Một `DELETE` nhầm được xác nhận ở quorum rồi lan đến replica còn lại. RF=3 có giúp trả dữ liệu về trước DELETE không? Nêu bản sao cần chuẩn bị từ trước.

**Bài 2 — Off-node và failure domain.** So sánh: snapshot trên data volume, copy lên NAS cùng rack, copy tới object storage khác account/region có retention bất biến. Đánh giá khả năng chịu lỗi node, mất DC và xâm nhập tài khoản.

**Bài 3 — Thiết kế manifest.** Với ba node và một bảng có bốn SSTable/descriptor trên mỗi node, liệt kê những thông tin đủ để xác minh không thiếu một component. Vì sao tên `Data.db` đơn lẻ và ETag không tự đủ?

**Bài 4 — Quyền truy cập.** Một service account vừa upload, list, xóa object, chỉnh KMS key policy và đổi retention. Hãy tách thành các vai trò backup writer, auditor, restore operator và KMS admin, kèm cách kiểm tra quyền bị từ chối.

**Bài 5 — Đo RPO.** Snapshot cuối ở 10:00, ứng dụng nhận ACK ba event lúc 10:03, 10:04, 10:05, rồi mất cluster lúc 10:06. Restore chỉ thấy các event trước 10:00. Kết luận gì về RPO quan sát và số event đã ACK bị thiếu? Vì sao cần manifest thay vì chỉ số hàng?

**Bài 6 — Kiểm chứng restore.** Restore trong cluster cách ly trả 8 `FOUND_MATCH`, 1 `MISSING` và 1 `READ_ERROR` cho 10 marker đã ACK. Bạn có thể báo “mất 2 bản ghi” không? Nêu các bước đối soát và kiểm tra tiếp.

**Bài 7 — Dữ liệu đã xóa.** Snapshot trước một yêu cầu xóa thông tin khách hàng vẫn giữ byte của bản ghi đó. Làm thế nào thiết kế retention và quy trình restore để không vô tình phục hồi dữ liệu đã phải xóa?

**Bài 8 — Khi nào dọn snapshot?** Upload từ node A thành công, nhưng checksum một SSTable ở node B sai và manifest chưa `COMPLETE`. Có nên dùng `nodetool clearsnapshot` trên cả cluster để giải phóng disk không? Giải thích rủi ro và điểm dừng.

**Bài 9 — Khóa mã hóa.** Backup object còn 120 ngày nhưng KMS key đã lên lịch hủy sau 30 ngày. Điều gì xảy ra khi restore sau 90 ngày? Thiết kế giám sát để tránh backup “còn file nhưng vô dụng”.

**Bài 10 — Nâng cấp phiên bản.** Cluster đã nâng cấp Cassandra nhưng cần restore bản backup SSTable của phiên bản cũ. Những metadata/điều kiện tương thích nào phải xác minh? Vì sao không thể chỉ copy SSTable vào data directory live của cluster mới?

## Ghi nhớ

**Một backup Cassandra chỉ thật sự có ý nghĩa khi dữ liệu đã rời khỏi failure domain của node/cluster, được bảo vệ khỏi đọc/xóa trái phép, có manifest kiểm chứng và có thể restore trong thời gian chấp nhận.** Replica và snapshot cục bộ không thay backup ngoài cụm. Hãy lưu đủ SSTable components, schema và metadata; tính checksum đầu-cuối; sử dụng TLS, mã hóa/KMS, quyền tối thiểu, retention bất biến và audit. Cuối cùng, **diễn tập restore trong cluster cách ly và đối soát với các event đã ACK**, vì lệnh upload thành công không tự bảo đảm RPO, RTO hay tính đầy đủ dữ liệu nghiệp vụ.
