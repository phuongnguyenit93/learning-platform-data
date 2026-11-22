# Thử restore định kỳ và ghi nhận bằng chứng phục hồi

> **Chương:** Tự động hóa vận hành  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — hiểu kiến trúc phân tán và mô hình wide-column của Apache Cassandra, đặc biệt partition key, thiết kế bảng theo truy vấn, consistency đọc/ghi; thực hành CQL, replication, compaction, repair, xử lý lỗi và kết nối từ ứng dụng Java.

Một hệ thống có job snapshot chạy hằng đêm, xuất hiện thông báo “backup thành công” trong dashboard và đã lưu nhiều terabyte SSTables lên object storage. Đến lúc một keyspace quan trọng bị xóa nhầm, đội trực ca mới phát hiện file `schema.cql` chưa được bảo quản, một vài node không có bản snapshot đồng thời, credential/KMS của vùng khôi phục chưa được cấp, và thao tác đọc từ Java không thể chạy vì thiếu role. **Backup job màu xanh không chứng minh khả năng phục hồi.**

Một chương trình backup đáng tin cần **diễn tập restore lặp lại trên môi trường cách ly**, đo **RPO (Recovery Point Objective)** và **RTO (Recovery Time Objective)** bằng kết quả thực, kiểm chứng dữ liệu/schema/quyền truy cập/consistency, rồi lưu bằng chứng có thể audit. Đó là mục tiêu của bài này.

**Phạm vi:** Cassandra 4.1/5.0, native CQL, SSTable snapshots/incremental backups, những yêu cầu bổ sung khi có commitlog archive, Java Driver 4.x và automation orchestrator độc lập sản phẩm. Tên lệnh/options khác theo phiên bản; luôn kiểm tra `nodetool help` và tài liệu bản đang dùng. Không coi lệnh trong bài là runbook production sẵn dùng.

> **An toàn quan trọng:** Các bài tập restore chỉ thực hiện trên **cluster lab biệt lập, dữ liệu synthetic, credentials riêng và namespace/đường dẫn được allowlist**. Không `DROP/TRUNCATE` keyspace production, không ghi SSTables vào live production data directory, không thay system keyspaces/host IDs trên cluster đang phục vụ người dùng và không chạy restore thật chỉ vì CI báo chưa có bài test.

## 1. Mục tiêu học tập và tiêu chí thành công

Sau bài này bạn có thể:

1. Phân biệt snapshot, incremental SSTable backup, commitlog archiving, anti-entropy repair và replication; biết loại dữ liệu/tính nhất quán nào mỗi cơ chế **không** bảo đảm.
2. Định nghĩa RPO, RTO, restore scope và workload invariants trước khi triển khai automation.
3. Thiết kế **manifest backup đủ thông tin** để dựng lại schema, topology, table ID/SSTable, phiên bản Cassandra, dữ liệu và cấu hình bảo mật.
4. Chọn đúng đường restore: `sstableloader` stream vào cluster lab có schema tương thích, `nodetool refresh` cho trường hợp local SSTables đúng node/layout, hoặc quy trình full node recovery phù hợp.
5. Hiểu vì sao snapshot từng node không tạo ra **một transaction snapshot nguyên tử của toàn cluster**.
6. Đặt lịch restore drill theo mức rủi ro, có giới hạn đồng thời, deadline, isolation và stop conditions.
7. Xác thực checksum/manifest, object access, encryption/decryption, retention, schema, role, dữ liệu, TTL/tombstone và Java application path.
8. Đo **RPO quan sát** và **RTO quan sát** với timestamp UTC và phân biệt các pha restore, query readiness, application readiness.
9. Tạo evidence ledger, run ID, log/tracing metrics, sample key catalog và báo cáo PASS/FAIL có căn cứ.
10. Thiết kế negative tests như thiếu SSTable component, sai phiên bản, KMS unavailable, thiếu role, restore nửa chừng, quota/disk đầy và khôi phục sau failure.
11. Giải thích lý do **replication/repair không thay thế off-cluster backup**, và vì sao backup có hardlink chưa độc lập khỏi failure domain.
12. Đánh giá rủi ro diễn tập, bảo toàn dữ liệu production, audit truy cập và phân công người phê duyệt.

**Tiêu chí thành công tổng quát:** một restore test chỉ được coi là `PASS` khi **bản backup được chọn thực sự giải mã/đọc được, các phần phụ thuộc đã có, dữ liệu và hành vi ứng dụng khớp mục tiêu, RPO/RTO nằm trong ngưỡng và bằng chứng được lưu bền vững**. Nếu chỉ kiểm tra có file hoặc startup được Cassandra mà chưa đọc đúng dữ liệu, kết quả chỉ là `BACKUP_PRESENT` hay `CLUSTER_BOOTED`, không phải `RESTORE_VERIFIED`.

## 2. Vì sao cần thử restore định kỳ?

### 2.1. Những sự cố không được phát hiện bởi “backup succeeded”

| Khả năng | Backup job có thể vẫn xanh | Restore drill sẽ phát hiện |
|---|---|---|
| Snapshot chỉ có ở hai trong ba node | Có, nếu job tổng hợp sai | Thiếu token ranges/replica coverage trong manifest |
| Hardlink snapshot chưa được copy khỏi node | Có | Mất node/disk là mất cả nguồn lẫn “backup” |
| File object store bị lỗi/thiếu một component | Có | Checksum/TOC SSTable hoặc loader fail |
| Không lưu schema/UDT/index/roles | Có | Cluster đích không thể dựng model hoặc app không có quyền |
| KMS/truststore/key rotation | Có | Không giải mã/khởi động/truy cập được |
| Snapshot bị tạo từ thời điểm quá cũ | Có | Observed data loss vượt RPO |
| TTL/delete đã hết hạn | Có | Kỳ vọng live row sai hoặc resurrection risk |
| Incremental chain có lỗ hổng | Có | RPO thực khác watermark trong dashboard |
| Version incompatibility/SSTable format | Có | Loader/refresh thất bại hoặc phát hiện schema mismatch |
| Disk/RAM/network khôi phục thiếu | Có | Restore quá RTO hoặc hết disk |
| Java Driver không kết nối được | Có | Missing roles/TLS/local DC/routing configuration |

**Khả năng khôi phục là thuộc tính của cả hệ thống**, bao gồm backup, offsite storage, metadata, keys, tài nguyên compute/network, Cassandra topology, CQL schema, tài khoản, runbook và khả năng kiểm tra kết quả.

### 2.2. Phân biệt replication, repair, backup và restore

~~~mermaid
flowchart LR
    A["Mutation Cassandra"] --> B["Replicas theo RF/CL"]
    B --> C["Anti-entropy repair"]
    B --> D["SSTable snapshots"]
    D --> E["Independent off-cluster storage"]
    B --> F["Incremental SSTable copies"]
    F --> E
    G["Optional commitlog archive"] --> E
    E --> H["Restore into isolated cluster"]
    H --> I["Data + app validation"]
    I --> J["Measured RPO/RTO + evidence"]
~~~

- **Replication** duy trì nhiều bản dữ liệu trong các failure domains đã chọn, nhưng có thể nhân rộng thao tác xóa nhầm, bug ứng dụng hoặc corruption ở cấp logic.
- **Repair** đồng bộ dữ liệu giữa replicas đang tồn tại; nếu delete hợp lệ đã được nhân sang mọi replica, repair không lấy lại trạng thái trước khi xóa.
- **Snapshot/incremental backup** là vật liệu phục hồi từ thời điểm đã ghi SSTables và phải được chuyển tới vị trí độc lập, có retention và integrity checks.
- **Commitlog archive** có thể mở rộng khả năng khôi phục đến những mutations sau snapshot nhưng đòi thiết kế segment coverage, timestamp semantics và kiểm thử thực tế.
- **Restore drill** chứng minh một tập vật liệu có thể tái dựng dữ liệu/ứng dụng theo yêu cầu tại thời điểm kiểm thử; nó không làm backup trở nên đầy đủ hơn nếu vẫn còn lỗ hổng.

### 2.3. Failure domains và nghĩa của “độc lập”

Một snapshot dạng hardlink nằm trên cùng filesystem **chưa chống** mất ổ đĩa hoặc xóa volume. Off-cluster copy vào object storage độc lập account/region, với immutability/retention và quyền tối thiểu, tốt hơn nhưng vẫn có thể chịu cùng control plane, credentials hoặc KMS failure. Một bản copy ngoài vùng mà cần **cùng một khóa vừa bị xóa** thì chưa thể phục hồi.

Khi lên lịch drill, định nghĩa rõ:

~~~text
Production cluster -> isolated restore environment
Production backup account -> read-only restore identity with scoped permissions
Backups / encryption keys -> controlled, audited, tested access
No network path from restore client to production native 9042 by default
Cleanup restricted to ephemeral lab resources
Evidence exported to independent, access-controlled storage
~~~

## 3. Chỉ tiêu RPO, RTO, RLO và cách đo

### 3.1. RPO không phải “tuổi của job backup”

**RPO** là lượng thời gian mất dữ liệu tối đa được chấp nhận (ví dụ 15 phút). Trong drill, một cách đo khả dụng là:

\[
\text{observed RPO} =
\text{disaster cut time} -
\text{latest verified recoverable write time}.
\]

**Điều kiện:** “latest verified recoverable write” phải dựa trên ledger/fixture hoặc phép kiểm chứng có ý nghĩa, không chỉ tên file với timestamp mới nhất. Các writes **sau** recovery point nếu cố tình không giữ là **mất mát dự kiến**, không ghi nhầm thành corruption.

Ví dụ minh họa: sự cố giả định lúc 12:00Z; cuối cùng xác minh được mutation ACK lúc 11:52Z đã khôi phục, còn 11:53Z chưa có bằng chứng. Report `observed RPO ≤ 8 phút theo tập writes được kiểm`, không tuyên bố “RPO chính xác 8 phút trên tất cả keyspaces” nếu coverage chỉ gồm 100 keys.

### 3.2. RTO phải có điểm bắt đầu và kết thúc thống nhất

**RTO** là thời gian dịch vụ được phép gián đoạn trước khi phục hồi khả năng phục vụ. Drill:

~~~text
T0         DR declared / start simulated loss
T1         Backup set selected and manifest verified
T2         Isolated infra, keys, schema/roles ready
T3         SSTable stream/restore ends
T4         Cassandra nodes healthy; reads/writes meet required CL
T5         Java application completes representative transactions
T6         Correctness tests and operational checks pass
~~~

Chọn trước định nghĩa “service restored”: có tổ chức dùng `T5` nếu integrity checks tối thiểu đã đạt, có tổ chức dùng `T6`. **Không đo RTO chỉ từ lúc chạy `sstableloader` đến khi lệnh kết thúc**, vì provisioning, decrypt, schema/role creation và validation thường chiếm thời gian lớn.

### 3.3. Recovery Level Objective và mức độ bao phủ

Ngoài RPO/RTO, nên mô tả **khối lượng dịch vụ đã khôi phục**: một table, keyspace, nhiều DC, toàn cluster hay một tenant; cả read/write hay read-only; 1% sample hay mọi partition. RLO ở đây là tên gọi nội bộ cho **mức chức năng/dữ liệu cần đạt**, không phải một metric chuẩn Cassandra.

| Đối tượng | Phạm vi test | Điều không được suy |
|---|---|---|
| Một table | CQL schema, SSTables, keys, TTL, Java repository | Toàn keyspace đã khôi phục |
| Keyspace | Các tables/UDTs/indexes/functions cần thiết, read/write | Tất cả system_auth/credentials đã sẵn |
| Một DC | Local RF/CL, nodes và token ranges | Multi-DC disaster recovery đã đạt |
| Toàn dịch vụ | CQL access + workflows Java/TLS/auth/metrics | Backup toàn tổ chức có thể dùng |
| PITR | Có mục tiêu thời điểm và replay semantics | Bảo đảm truy vấn giữa các table có một commit toàn cục |

### 3.4. Ví dụ SLO drill, không phải chuẩn Cassandra

| Test class | Lịch gợi ý | Mục tiêu gợi ý | Ai phê duyệt |
|---|---|---|---|
| Object/file integrity | Hằng ngày | 100% manifest files tồn tại + checksum match | Backup owner |
| Restore một table synthetic | Hằng tuần | Schema + representative rows + Java query PASS | DB/platform owner |
| Restore keyspace/service | Hằng tháng | RPO/RTO theo tier đã công bố | Service owner + SRE |
| PITR/window boundary | Hằng quý | Time-target includes/excludes đúng fixture | DB recovery owner |
| Cross-region/credential-loss drill | 6–12 tháng/lần | Independent access, region isolation và recovery | Security + DR owner |

Các chu kỳ là **ví dụ quản trị rủi ro**. Tier dịch vụ yêu cầu RPO 0 hoặc recovery near-real-time phải có kiến trúc/chuỗi backup và diễn tập phù hợp hơn; không dùng “mỗi tháng một restore” làm bằng chứng RPO 15 phút.

## 4. Cassandra thực sự backup những gì?

### 4.1. Snapshot = hardlink tới những SSTables hiện có

Apache Cassandra giữ dữ liệu on-disk trong các thành phần SSTable bất biến. `nodetool snapshot` thông thường flush memtables trước khi tạo snapshot để các writes trước thời điểm flush được đưa vào SSTables. Snapshot gồm **hardlinks** tới những SSTable components và thường có `schema.cql` cùng manifest. Tùy release, dùng `--skip-flush` sẽ **bỏ qua dữ liệu còn trong memtable** nếu nó chưa nằm trong SSTable.

~~~text
<data_dir>/<keyspace>/<table>-<table_id>/
  <sstable components...>
  snapshots/
    <tag>/
      <version>-<generation>-Data.db
      <version>-<generation>-Index.db
      <version>-<generation>-Statistics.db
      <version>-<generation>-TOC.txt
      ... (các thành phần tương ứng)
      manifest.json
      schema.cql
  backups/
    <sstable components...>
~~~

Đây là cấu trúc **minh họa**; tên SSTable/đường dẫn thực khác theo phiên bản và install. Đừng chỉ sao chép `Data.db` mà bỏ thiếu `Index.db`, compression info, statistics, TOC. Danh sách file phải lấy từ manifest/actual set.

Ví dụ tạo snapshot trên **node lab**:

~~~bash
nodetool help snapshot
nodetool snapshot --tag drill-20261121 --table events_by_device_day restore_lab
nodetool listsnapshots
~~~

**Một lần `nodetool snapshot` trên node N1 chỉ snapshot dữ liệu local trên N1**; nó không mặc nhiên chụp N2/N3. Coordinator/orchestrator cần snapshot trên **mỗi node được yêu cầu**, lưu tags/timestamps và token coverage. Snapshot của các node có thể khác nhau theo thời gian, và writes tiếp tục xảy ra trong khi chụp.

### 4.2. Incremental backups = hardlinks từ những lần flush/stream

Khi bật `incremental_backups: true` hoặc dùng `nodetool enablebackup`, Cassandra tạo hardlink cho các SSTables sau khi memtable flush/stream vào thư mục `backups/` của table. Chúng không tự chuyển tới object store và không tự dọn dẹp, nên cần pipeline upload/retention riêng.

~~~bash
# Chỉ đọc trạng thái trên node được phép:
nodetool statusbackup

# Đây là lệnh THAY ĐỔI CẤU HÌNH runtime, không nằm trong bước kiểm tra:
# nodetool enablebackup
# nodetool disablebackup
~~~

Một incremental backup **không phải** “danh sách tất cả CQL mutations sau snapshot”. Nó chứa SSTables được flush/stream, không tự bao gồm commitlog chưa archive hay memtable chưa flush. Khi thiết kế chain restore, phải hiểu SSTable generations, compaction, deletions/tombstones và overlap; **không concat file names hay suy row count bằng cộng các SSTables**.

### 4.3. Commitlog archive và PITR là luồng riêng

`commitlog_archiving.properties` có các field như `archive_command`, `restore_command`, `restore_directories`, `restore_point_in_time`, `precision`. Một segment archive có thể đóng góp mutations sau snapshot, nhưng:

- Cần archive được **đủ segments liên quan tới node/table**, không chỉ file gần nhất.
- Lệnh archiving phải thành công và artifact đã được copy ra durable/independent storage; hardlink tại node vẫn có thể mất cùng ổ.
- Mốc PITR dựa trên mutation/write timestamps và semantics của cơ chế replay, **không phải distributed transaction timestamp**.
- Out-of-order/client-supplied timestamps, TTL/delete và writes concurrent có thể làm “khôi phục đúng trạng thái lúc 12:00Z” khó hơn một phép cắt theo arrival time.
- Restore commitlog có nguy cơ ghi đè state nếu làm sai node/segment/schema; chỉ test trong lab có runbook tương thích release.

Ví dụ **tệp cấu hình mô tả**, tuyệt đối không cắm vào production chưa kiểm chứng:

~~~properties
# Đường dẫn và script hoàn toàn là minh họa; script phải có kiểm tra an toàn.
archive_command=/opt/drill/bin/archive-segment %path %name
restore_command=/opt/drill/bin/restore-segment %from %to
restore_directories=/srv/restore-drill/commitlogs
restore_point_in_time=2026:11:21 12:00:00
precision=MICROSECONDS
~~~

Một số bản tài liệu mô tả khi gặp timestamp client lớn hơn mốc PITR, recovery xử lý segment theo quy tắc riêng; việc thứ tự mutation không khớp timestamp khiến một số mutations trước mốc vẫn có thể không được replay. **Đừng hứa PITR tuyệt đối chính xác đến microsecond** nếu chưa có test đủ loại CQL mutations và semantics phiên bản thực. <https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_cl_archive_file.html>.

### 4.4. Không có snapshot nhất quán toàn cụm mặc định

Snapshot từng node được chụp ở thời điểm hơi khác, mỗi node nắm tập SSTables cho token ranges/replicas riêng. Trong một workload đang ghi:

~~~text
N1 snapshot at 11:59:58Z
N2 snapshot at 12:00:04Z
N3 snapshot at 12:00:09Z
~~~

Không thể mặc định các snapshot này thể hiện **một atomic cut tại 12:00:00Z** cho nhiều partitions/tables. Một application backup cần nhất quán ở cấp business workflow có thể đòi **quiesce writers, application barrier/checkpoint, ledger event sequence hoặc chiến lược restore chuyên biệt**. Đừng nhầm thành công của `nodetool snapshot` trên từng node với transaction-level consistency.

### 4.5. Những thứ backup SSTable không tự mang theo

| Phần phụ thuộc | Nơi nên lưu/kiểm chứng |
|---|---|
| Keyspace DDL, table DDL, UDT, index/SAI, materialized views | Schema export có phiên bản và migration order |
| Roles, grants và authentication state | Quy trình riêng cho `system_auth`, không copy hệ thống bừa |
| Cassandra version/JDK/native protocol | Build/cluster manifest |
| `cassandra.yaml`, rack/DC topology, encryption, snitch | Configuration backup có secrets redacted |
| TLS certs/truststores, KMS keys, object credentials | Secret/KMS recovery plan với quyền tối thiểu |
| SSTable version, table IDs, token ownership, RF | Manifest nguồn và mapping restore đích |
| Commitlog archive nếu đòi PITR | Chain, segment checksums, target timestamps |
| Java Driver/Spring Data/DTO/codec compatibility | App release, integration tests, CQL contract |
| Business event log/operation IDs, TTL policy | Fixture ledger và reconciliation plan |

Không sao chép nguyên `system.local`, `system.peers`, token/host-id config và toàn bộ `system_*` từ cluster nguồn sang cluster đích khác topology. Chúng có metadata thuộc cluster và có thể làm hỏng môi trường restore. Backup của `system_auth` cũng có yêu cầu khôi phục riêng; kiểm thử role/grant ở **cluster cách ly** và theo runbook bảo mật thay vì đưa thẳng credentials production vào test.

## 5. Thiết kế một backup manifest có thể tái lập

### 5.1. Đơn vị backup hợp lý

Mỗi backup set được nhận diện bởi **backup_set_id duy nhất** và tập **node/table components**:

~~~text
backup_set_id
  ├── cluster metadata, schema, versions, RF/DC/token/host IDs
  ├── snapshot tag + per-node UTC capture window
  ├── source node A: tables + SSTable file list/checksums
  ├── source node B: tables + SSTable file list/checksums
  ├── source node C: tables + SSTable file list/checksums
  ├── incremental sets and commitlog archive references (if enabled)
  ├── encryption/key references, not plaintext secrets
  └── application verification fixture catalog
~~~

**Đừng chỉ dùng một timestamp hay tên thư mục snapshots làm định danh restore.** Hai node có thể tạo cùng tag nhưng tập SSTable khác nhau, các tables khác nhau và quá trình upload không hoàn tất. Dùng immutable manifest + checksum nội dung.

### 5.2. Manifest YAML minh họa

~~~yaml
manifest_version: "1"
backup_set_id: "cass-restore-lab-20261121T120000Z"
source_cluster: "synthetic-source-lab"
source_cassandra_release: "5.0.x-record-exact-build"
source_schema_revision: "sha256:example"
partitioner: "org.apache.cassandra.dht.Murmur3Partitioner"
dc_replication:
  dc1: 3
snapshot_tag: "drill-20261121"
capture_started_utc: "2026-11-21T11:59:50Z"
capture_finished_utc: "2026-11-21T12:00:12Z"
tables:
  - name: "restore_lab.events_by_device_day"
    schema_object: "schema/restore_lab.cql"
    schema_sha256: "<replace with actual digest>"
nodes:
  - source_node_id: "lab-n1"
    host_id: "synthetic-host-id-1"
    dc: "dc1"
    token_ranges_manifest: "tokens/lab-n1.json"
    files_manifest: "files/lab-n1.json"
  - source_node_id: "lab-n2"
    host_id: "synthetic-host-id-2"
    dc: "dc1"
    token_ranges_manifest: "tokens/lab-n2.json"
    files_manifest: "files/lab-n2.json"
  - source_node_id: "lab-n3"
    host_id: "synthetic-host-id-3"
    dc: "dc1"
    token_ranges_manifest: "tokens/lab-n3.json"
    files_manifest: "files/lab-n3.json"
encryption:
  method: "AES-256-GCM-example"
  key_reference: "alias/restore-test-key"
incremental_chain: []
commitlog_chain: []
fixture_ledger: "fixtures/expected-writes.jsonl"
uploader_version: "record-commit"
status: "SEALED_AFTER_VERIFICATION"
~~~

Các field là **thiết kế metadata riêng của hệ backup**, không phải file Cassandra có thể đọc trực tiếp. Giá trị placeholder không hợp lệ cho khôi phục thật. Khi cần dual-region, lưu location, object version ID, storage account, retention/immutability và encryption context theo mỗi object.

### 5.3. Manifest per-file và SHA-256

Ví dụ:

~~~json
{
  "object": "backup/cass-.../lab-n1/restore_lab/events_by_device_day/ma-1-big-Data.db",
  "size_bytes": 17422389,
  "sha256": "<64 hex chars computed from actual bytes>",
  "sstable_descriptor": "ma-1-big",
  "source_host_id": "synthetic-host-id-1",
  "table_id": "<actual table UUID from source>",
  "uploaded_utc": "2026-11-21T12:03:10Z",
  "storage_version_id": "<actual immutable version id>"
}
~~~

**Checksum phải được kiểm tra sau download/decrypt**, và integrity of manifest cần được bảo vệ bằng chữ ký/MAC, object immutability hoặc trusted hash anchor. Chỉ tính SHA-256 khi upload nhưng không re-hash lúc restore sẽ bỏ sót lỗi corruption ở khâu download, merge hoặc storage gateway.

### 5.4. Watermark và tính đầy đủ

Tách bốn mốc:

~~~text
snapshot_capture_completed_utc
all_nodes_uploaded_and_verified_utc
latest_incremental_sstable_uploaded_utc
latest_commitlog_segment_archived_and_verified_utc
~~~

Chúng không tương đương **latest recoverable business write**. Một segment đã archive có thể không chứa mutation của table cần khôi phục; một SSTable mới upload có thể chỉ chứa dữ liệu của partition khác. Cần marker writes/fixture ledger để chứng minh RPO và coverage theo workload.

### 5.5. Quy tắc seal/retention

Chỉ seal backup set khi:

1. Danh sách source nodes/tables theo phạm vi đã được chốt.
2. Mọi object trong manifest đã có và checksum match.
3. Schema/UDT/index/roles references và key references có thể truy cập theo policy.
4. Metadata Cassandra/SSTable version và token/rack/DC placement được ghi.
5. Backup có retention/immutability, không bị quy trình cleanup xóa ngay trước drill.
6. Các lỗ hổng đã được **ghi thành FAIL/PARTIAL**, không silently giảm scope.

Nếu snapshot tạo từ một node bị Down, manifest phải ghi `MISSING_SOURCE_NODE`. Không giả định RF3 nghĩa có thể restore đầy đủ ngay cả khi thiếu node: dữ liệu có thể chưa đồng bộ hoặc một số writes chỉ nằm ở replicas khác; recovery guarantee cần kiểm tra thật.

## 6. Chọn đúng cơ chế restore: streaming hay local SSTable?

### 6.1. Hai hướng được Cassandra hỗ trợ

| Hướng | Khi phù hợp | Tại sao cần thận trọng |
|---|---|---|
| **`sstableloader`** | Load SSTables vào cluster Cassandra **đã có schema** và có thể có topology/token assignment khác | Tool stream theo token tới replicas của cluster đích; cần tương thích format/schema, disk/network, creds |
| **`nodetool refresh`** | Đã đặt **local SSTables tương thích** vào đúng thư mục dữ liệu của node và muốn Cassandra nhận diện không restart | Phải khớp table ID/layout/node; không tự phân phối data lại các token ranges |
| **Offline node recovery / restore data directory** | Khôi phục node cùng topology từ bản đã chuẩn bị, phù hợp runbook | Metadata system tables/host IDs/tokens/commitlogs đặc biệt nguy hiểm khi đổi cluster |
| **Application-level replay/import** | Có event log/source of truth đủ và muốn dựng state theo logic nghiệp vụ | Không bảo toàn tự động CQL timestamps/TTL/deletes; throughput/RPO do pipeline quyết định |

Chọn trước **restore use case**: dropped table vào cluster mới, node mất disk trong cluster cũ, hay toàn DC mất. Cùng file snapshot nhưng thao tác và validation khác rất nhiều.

### 6.2. Vì sao `sstableloader` thường hợp lý cho lab mới?

Theo tài liệu Apache Cassandra, `sstableloader` đọc SSTables từ một đường dẫn có parent directories thể hiện keyspace/table và **stream phần dữ liệu tới natural replicas theo topology đích**, tạo SSTables mới; nó không tự cleanup source files.

~~~text
/srv/restore-input/
  restore_lab/
    events_by_device_day/
      ma-1-big-Data.db
      ma-1-big-Index.db
      ma-1-big-Statistics.db
      ma-1-big-TOC.txt
      ... complete components for each SSTable
~~~

Với Cassandra 5.0, ví dụ dạng lệnh:

~~~bash
# CHỈ chạy trong restore lab, từ helper/host được kiểm soát.
sstableloader --nodes 10.30.0.11 \
  /srv/restore-input/restore_lab/events_by_device_day
~~~

Trước đó: tạo keyspace/table/UDT/indexes tương thích; xác minh target seed node chỉ thuộc isolated lab; chuẩn bị credentials/TLS/port/internode streaming nếu cần. Đối chiếu `sstableloader --help` theo version; một số công cụ SSTable có ràng buộc quá trình Cassandra trên **host chạy tool** và yêu cầu không dùng trực tiếp cùng live data directory. An toàn nhất là chạy loader với input **read-only copy ở helper host** thay vì mở file SSTable đang phục vụ.

**Đừng gọi `sstableloader` trên mọi bản sao replica cùng key mà không có kế hoạch:** source snapshots của nhiều replicas có SSTables trùng/overlap, deletes/timestamps có thể khác. Pipeline cần quyết định phạm vi source SSTables, repair/reconciliation và kiểm chứng dữ liệu trên topology mới; streaming thành công không tự chứng minh đúng toàn bộ business state.

### 6.3. `nodetool refresh` không thay cho redistribution

`nodetool refresh <keyspace> <table>` yêu cầu đã đặt SSTable files vào **đúng table directory của node đích** và lệnh làm Cassandra nhận diện chúng mà không restart. Nó không:

- Tạo schema/UDT/roles bị thiếu.
- Bù dữ liệu cho token ranges của nodes khác một cách tự động.
- Chuyển một backup của node N1 sang topology mới rồi đảm bảo N2/N3 đủ replicas.
- Kiểm chứng app-level correctness.

Với một fresh cluster khác table ID và token ranges, **sao chép trực tiếp thư mục rồi refresh** có thể lỗi hoặc tạo dữ liệu thiếu/không phù hợp. Nếu drill nhằm phục hồi dropped table sang cluster mới, hãy ưu tiên streaming/restore path đã kiểm chứng thay vì tự thao tác live data dirs.

### 6.4. Tại sao không copy nguyên thư mục `system`?

Các system tables mang node-local identity, peer membership, tokens và schema state. Nếu copy nguyên `system.local` từ cluster A vào B, B có thể có host ID trùng hoặc membership sai. `system_auth` chứa roles/grants có policy riêng và cần phù hợp replication strategy/password handling trên cluster mới. Tách rõ:

~~~text
Cluster identity/configuration: dựng mới theo restore environment
Application schema: tái tạo theo version/migration và validated DDL
Application data SSTables: restore theo path được phê duyệt
Authentication/authorization: test riêng, không bê nguyên môi trường thật
Commitlog/PITR: riêng, node/schema/precision-aware
~~~

### 6.5. Thứ tự objects/schema có thể cần khôi phục

Trong CQL thực tế:

1. Keyspace với replication strategy phù hợp restore lab và tên DC thật.
2. UDTs trước các tables sử dụng chúng; UDF/UDA chỉ khi thực sự phụ thuộc và security policy cho phép.
3. Base tables/columns/PK/clustering/options, TTL/gc_grace, compression/compaction phù hợp.
4. Data SSTables được load theo plan, không chèn raw data vào system tables.
5. Index/SAI/materialized view: kiểm chứng support/rebuild behavior theo release; không tự giả định index snapshot sẽ hoạt động trên cluster mới.
6. Roles/grants/TLS ở môi trường lab; cấu hình driver/service.
7. Repair/consistency và business verification sau load khi cần.

Một file `schema.cql` cho **một table** có thể không chứa đủ UDT/keyspace/roles hoặc dependencies khác. Không báo restore PASS nếu CQL loader import được data nhưng index/query mà ứng dụng dùng vẫn lỗi.

## 7. Preflight bắt buộc trước khi automation khởi chạy

### 7.1. Môi trường đích độc lập

Automation phải xác minh **positive allowlist**, không dựa vào hostname chứa chuỗi `test`:

| Gate | Ví dụ điều kiện | Nếu không đạt |
|---|---|---|
| Namespace/cluster ID | Đúng ID restore-lab do platform cấp | **ABORT** |
| Cloud account/project | Chỉ dedicated non-prod account | **ABORT** |
| Network egress | Không có route đến production Cassandra cluster | **ABORT** |
| Credentials | Chỉ restore identity/read-only backup source, write lab DB | **ABORT** |
| Source data | Synthetic hoặc snapshot đã được phép và xử lý privacy | **ABORT** |
| Restore target | Empty/new table/volume, không có user data | **ABORT** |
| Version/schema | Tương thích SSTable/driver/schema theo matrix | Hold/rebuild test image |
| Capacity | Disk, memory, CPU, network và quota đủ dự kiến | Hold/scale |
| Evidence destination | Audit storage writable, có retention | Hold, không chạy “mù” |
| Cleanup scope | Resource labels/run_id cụ thể, finalizer | Không cho cleanup rộng |

**Không đưa secrets vào logs/manifest**, không cho CI job quyền `DROP` trên production chỉ để tiện làm lại bảng test. Phân quyền tối thiểu giúp sự cố automation không trở thành sự cố dữ liệu.

### 7.2. Kiểm tra sức khỏe target trước khi load

Với isolated Cassandra lab:

~~~bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
nodetool status
nodetool describecluster
nodetool info
nodetool tpstats
nodetool compactionstats
~~~

`nodetool status` là gossip view của node được hỏi; lấy từ nhiều nodes nếu nghi membership/network. Xác minh tên DC/rack với snitch, RF của keyspace, schema agreement, disk headroom, native/internode ports và chính sách TLS. Một cluster `UN` không chứng minh đủ schema, role, query success.

### 7.3. Kiểm tra source manifest và object trước restore

Một file set đạt sơ bộ khi:

- `backup_set_id` tồn tại/đã seal và thuộc đúng cluster nguồn.
- Tất cả node/table/file references có thể tải từ identity dùng cho drill.
- Kích thước, checksum từng component khớp sau download/decrypt.
- DDL có hiệu lực tại thời điểm backup có đầy đủ dependencies.
- Format của SSTables có thể đọc bởi version đã chọn; không assume downgrade từ 5.0 sang 4.1.
- Có kế hoạch xử lý TTL, tombstones, per-node incremental và PITR chain nếu thực hiện.
- Các fixture expected rows/versions/writes có timestamp và nguồn rõ ràng.
- KMS decrypt key còn hoạt động/được phép, truststore/cert của lab sẵn sàng.

**Nếu một component bị thiếu:** phân loại `PRECHECK_FAILED`, không chạy load một tập thiếu rồi gọi lỗi kết quả là Cassandra corruption. Ghi object/version/checksum mismatch vào evidence report; không cố “tự chữa” bằng cách bỏ file khỏi manifest.

### 7.4. Resource budget, rate limit và cửa sổ

Restore có thể tải nhiều GiB/TiB, tạo SSTables, build index, stream giữa nodes, gây compaction và chiếm disk. Đặt:

~~~text
Maximum concurrent drills per failure domain: 1 (ví dụ)
Per-job timeouts: provisioning, download, stream, validate, cleanup
Disk low watermark: theo capacity plan (không dùng magic 10% cho mọi cluster)
Network egress budget: GB/run, MiB/s, approval for cross-region
KMS/API rate quotas: theo provider
SSTableloader throughput/concurrency: bounded and monitored
Stop conditions: disk alert, checksum mismatch, schema failure,
                 target unhealthy, wrong target ID, lost audit sink
~~~

Không chạy cleanup để “giải phóng chỗ” bằng `rm -rf` từ biến đường dẫn rỗng hoặc wildcard. Cleanup phải dùng resource IDs rõ ràng của **đúng run_id**, có dry-run/permission boundary.

### 7.5. Chọn bản backup mà không nhìn vào thời gian upload đơn thuần

Ví dụ một job snapshot ban đêm hoàn tất upload lúc 00:15Z nhưng nội dung là SSTables được chụp từ 00:00–00:05Z. Nếu disaster cut là 01:00Z:

- `upload_finished_utc=00:15Z` chứng minh vật liệu đến remote storage lúc ấy.
- Dữ liệu khôi phục có thể không chứa writes sau snapshot cut.
- RPO không bằng 45 phút chỉ vì 01:00 trừ 00:15; cần biết recoverable mutations thực.
- Nếu có incremental/commitlog, watermark chỉ có ý nghĩa khi **chain hoàn chỉnh** và các late writes/TTL semantics đã được kiểm tra.

Đặt selection policy rõ: latest **sealed + verified** set thỏa location, schema, KMS, version, coverage; không chọn “file mới nhất” chỉ vì timestamp object.

## 8. Pipeline restore drill end-to-end có trạng thái rõ ràng

### 8.1. Kiến trúc một lần diễn tập

~~~mermaid
flowchart TD
    A["Scheduled trigger / approved request"] --> B["Allocate unique run_id + lease"]
    B --> C{"Isolated target and credentials verified?"}
    C -->|No| X["FAIL + evidence, no destructive action"]
    C -->|Yes| D["Select sealed backup set"]
    D --> E["Download/decrypt/verify all SSTable files"]
    E --> F["Provision restore lab + apply schema"]
    F --> G["Restore via approved loader or local path"]
    G --> H["Cassandra health + schema validation"]
    H --> I["CQL data/TTL/delete/integrity validation"]
    I --> J["Java app + role/TLS/consistency tests"]
    J --> K{"RPO/RTO and coverage pass?"}
    K -->|Yes| L["PASS report + immutable evidence"]
    K -->|No| X
    L --> M["Bounded cleanup with run_id"]
    X --> M
~~~

**Quy trình phải fail-closed:** không có credentials, không tải đủ file, schema sai hoặc target cluster ID không đúng thì dừng. Hệ thống luôn phải ghi trạng thái cuối `PASS/FAIL/BLOCKED/ABORTED` và evidence về nguyên nhân; không “green” do test bị skip.

### 8.2. Các pha và exit gate

| Pha | Input | Output/evidence | Điều kiện để đi tiếp |
|---|---|---|---|
| SELECT | Policy, backup index | Backup_set_id + source manifest | SEALED + retention còn |
| PRECHECK | Target ID, identity, schema/version | Allowlist and access attestations | PASS |
| DOWNLOAD | Object versions + KMS | Download logs, bytes, hashes | 100% manifest files verified |
| PROVISION | Version, DC/RF/topology | Cluster IDs, node status, resources | Schema/quorum prerequisites |
| LOAD | Complete SSTable input | Loader logs, bytes, duration, errors | Streaming success, no missing files |
| DATA_CHECK | Fixture ledger, CQL | Per-table/key assertions | Correct rows/cells/TTL/deletes |
| APP_CHECK | Java release, auth/TLS | API/Driver attempts and results | Required contract PASS |
| REPORT | UTC timestamps, metrics | Signed result with links | Valid RPO/RTO + coverage |
| CLEANUP | Resource IDs of run | Destruction audit of lab only | No stale credentials/resources |

**Đo mọi pha với UTC wall clock và monotonic duration**. Thời gian chạy Java/retry kéo dài không thể trừ bằng clock UTC của hai hosts chưa đồng bộ mà không kiểm tra skew. Sự gián đoạn được bắt đầu từ `T0` theo drill contract chứ không phải lúc tool load bắt đầu.

### 8.3. State machine chống báo PASS sai

~~~text
NEW
 -> PRECHECKED
 -> ARTIFACTS_VERIFIED
 -> TARGET_READY
 -> DATA_LOADED
 -> DATA_VERIFIED
 -> APP_VERIFIED
 -> REPORT_SEALED
 -> CLEANED

Any state -> FAILED / ABORTED / BLOCKED
  with reason, evidence, owner, remediation
~~~

Không cho phép transition `TARGET_READY → REPORT_SEALED`, và không đặt `PASS` chỉ vì `sstableloader exit 0`. Cleanup có thể fail ngay cả khi restore PASS; báo `RESTORE_PASS_CLEANUP_FAIL` để không che rủi ro tài nguyên hoặc credential.

### 8.4. At-least-once execution và idempotency

Orchestrator có thể retry job sau network hiccup hoặc pod restart. Restore workflow phải có:

- `run_id` duy nhất, **lease/lock** per environment/backup set.
- Checkpoint per phase, hash inputs và trạng thái durable không phụ thuộc pod memory.
- Idempotent artifact fetch/checksum; không overwrite object versions đã seal.
- Target schema/tables chỉ được tạo **nếu environment ID khớp** và chúng chưa có dữ liệu người dùng.
- Không tự chạy `sstableloader` hai lần lên cùng dữ liệu khi không biết duplicate/timestamp effects; retry pha LOAD có thể cần dựng **fresh isolated target** thay vì “stream thêm lần nữa”.
- Retry network có exponential backoff, bounded attempts và deadline; sai schema/checksum/KMS key bị revoke phải fail nhanh.
- `finally` cleanup chỉ xử lý tài nguyên có tag/owner `run_id` và không xóa evidence.

### 8.5. Chuẩn hóa logs và correlation

Một event JSONL:

~~~json
{
  "run_id": "drill-20261121-a",
  "phase": "DATA_LOADED",
  "event_time_utc": "2026-11-21T12:12:17Z",
  "duration_ms": 143000,
  "backup_set_id": "cass-restore-lab-20261121T120000Z",
  "target_cluster_id": "isolated-drill-a",
  "result": "PASS",
  "files_verified": 128,
  "bytes_loaded": 2304104448,
  "evidence_uri": "audit://restore-drills/drill-20261121-a/loader.json"
}
~~~

Trong triển khai thực, `audit://...` là URI **nội bộ minh họa**. Không gắn raw password, token, KMS plaintext, hostname sensitive hoặc row payload trong events. Mọi metric cần unit, source, UTC time window và scope (node/table/DC).

## 9. Lab một table: restore được và đọc đúng dữ liệu

### 9.1. Chuẩn bị dữ liệu synthetic

Chỉ trên một cluster Cassandra lab nguồn (tên datacenter thật `dc1`), tạo:

~~~sql
CREATE KEYSPACE IF NOT EXISTS restore_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS restore_lab.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    revision int,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Nếu chỉ có **một node** trong lab, tạo keyspace riêng với RF1 và ghi rõ **không kiểm chứng khả năng khôi phục RF3**. Đừng tạo RF3 trên lab một node rồi chạy LOCAL_QUORUM và coi timeouts là lỗi backup.

Fixture:

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO restore_lab.events_by_device_day
  (device_id,event_day,event_time,event_id,event_type,payload,revision)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21','2026-11-21T10:00:00Z',
  22222222-2222-4222-8222-222222222222,
  'created','fixture-a',1
);

INSERT INTO restore_lab.events_by_device_day
  (device_id,event_day,event_time,event_id,event_type,payload,revision)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21','2026-11-21T10:01:00Z',
  33333333-3333-4333-8333-333333333333,
  'confirmed','fixture-b',2
);
~~~

Ghi operation ledger với UTC ACK của từng write, PK, revision, payload hash, CQL timestamp/TTL policy, không chỉ “đã insert hai rows”. Nếu muốn làm RPO test, tạo thêm boundary writes **trước/sau snapshot cut**, có expected inclusion/exclusion rõ.

### 9.2. Snapshot tất cả những node thuộc phạm vi

Orchestrator gọi trên **từng node lab** (ví dụ N1, N2, N3) với một tag:

~~~bash
# Chạy một lần MỖI node nguồn trong isolated lab.
nodetool snapshot --tag drill-20261121 \
  --table events_by_device_day restore_lab
nodetool listsnapshots
~~~

Kết quả phải có timestamp per-node, path table ID, danh sách file từ `manifest.json`/thư mục, checksum/hash, source host ID/DC, size và upload confirmation. Không copy snapshot chỉ từ một node mà âm thầm tuyên đó là “toàn cluster”; nếu cố tình demo restore một replica thì phải gắn nhãn `SINGLE_NODE_SCOPE`.

### 9.3. Export và seal backup artifacts

Trên môi trường backup agent được phép:

1. Lấy file list từ snapshot tag đúng **node/table**, không lấy wildcard từ tất cả tags.
2. Copy file components sang một đường dẫn **ngoài data directory và trên storage độc lập**; hardlink source sẽ không tự trở thành backup offsite.
3. Tính SHA-256 cho từng file và aggregate per-node/per-table manifest.
4. Upload lên object storage với object version/retention policy và encryption.
5. Download sample/sau cùng, xác thực checksum; chỉ seal set khi tất cả required nodes/tables hoàn tất.
6. Giữ schema/migrations, config references, fixture ledger, backup scripts/version và metadata restore source.

Ví dụ một lệnh **đọc file backup đã export**:

~~~bash
sha256sum /srv/export/drill-20261121/lab-n1/restore_lab/events_by_device_day/* 
~~~

Lệnh minh họa trên Linux không phải cách duy nhất; nó in hash từng file trong folder. Nếu folder có subfolders hoặc chứa secrets, phải giới hạn đúng file set từ manifest. Không log nội dung payload.

### 9.4. Dựng cluster đích và schema

Tạo fresh **isolated** cluster đúng Cassandra release, với network cố định chỉ tới lab và credentials mới. Dùng cluster name, host IDs, tokens **mới**; không copy system.local/system.peers của nguồn. Tạo schema:

~~~sql
CREATE KEYSPACE IF NOT EXISTS restore_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS restore_lab.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    revision int,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Không** dùng `CREATE TABLE IF NOT EXISTS` làm bằng chứng schema khớp: nếu bảng có sẵn với columns/PK khác, lệnh có thể không sửa nó. So exported DDL/UDT/options với live table metadata trước khi stream.

### 9.5. Chạy loader trên bản sao chỉ đọc

Sau khi các SSTable components khớp checksum và đã được chuẩn bị trong directory structure đúng:

~~~bash
# Đặt source copy ở helper/host lab, KHÔNG phải data dir Cassandra đang phục vụ.
sstableloader --nodes 10.30.0.11 \
  /srv/restore-input/restore_lab/events_by_device_day
~~~

Lệnh stream tạo SSTables ở các replicas target theo topology. Nếu trong source có nhiều node replicas chứa cùng key, phải có plan tập hợp/merge đúng timestamps/tombstones trước khi gọi loaders; **không copy nhiều lần tùy ý** rồi coi quá trình không gây duplicate effects.

Theo dõi `bytes transferred`, duration, streaming errors, target free disk, CPU/compaction, node status. Exit code 0 có thể chứng minh tool hoàn tất streaming đã yêu cầu, **chưa chứng minh fixture data đúng**.

### 9.6. Verify CQL theo đúng partition key

~~~sql
CONSISTENCY LOCAL_QUORUM;
SELECT event_time,event_id,event_type,payload,revision
FROM restore_lab.events_by_device_day
WHERE device_id=11111111-1111-4111-8111-111111111111
  AND event_day='2026-11-21'
LIMIT 20;
~~~

**Cần so:** số row mong đợi cho PK, event IDs, revision, payload hash và TTL/deletes nếu profile có. Không dùng `SELECT COUNT(*) FROM restore_lab.events_by_device_day` toàn bảng làm kiểm tra bắt buộc trên dataset lớn vì Cassandra không tối ưu full scan kiểu RDBMS; nên dùng fixture key catalog, partition-stratified sampling và business aggregate được precompute.

Sau restore, chạy một write/read synthetic riêng **trên table lab** hoặc một canary table khác để xác minh quyền/CL, đồng thời không phá fixture nguyên bản. Cleanup chỉ xóa resource lab theo run_id, không chạm source snapshot.

## 10. Kiểm chứng dữ liệu, TTL và kết nối Java sau restore

### 10.1. Nhiều lớp xác minh độc lập

| Lớp | Kiểm thử | Điều không được kết luận |
|---|---|---|
| File | SHA-256/size/TOC/SSTable components match | Rows có thể đọc qua Cassandra |
| Schema | Keyspace/table/PK/clustering/UDTs/indexes/role grants | SSTables đã load đầy đủ |
| Cassandra | Node status, successful query CL, no loader errors | Java service đã sẵn sàng |
| Dữ liệu | Fixture PKs, revisions, deletes, TTL và checksum | Tất cả partitions/tenants được bao phủ |
| Driver | CqlSession, TLS/auth/local DC, prepared statements, paging | HTTP/API end-to-end đã đúng |
| Ứng dụng | Read/write canary, serialization, business invariants | Disaster scope hoàn toàn được phục hồi |
| Vận hành | RPO/RTO, disk headroom, compaction/GC/network, alerts | Năng lực hoạt động lâu dài ở tải production |

Không dùng một `SELECT 1` như RDBMS để “test Cassandra ready”: CQL không hỗ trợ như phép thử phổ quát. Dùng một query đúng keyspace/table và key sample đã biết, hoặc health API biết rõ semantics.

### 10.2. Java Driver 4.x: verifier có thể chạy trong test runner

Ví dụ Java 17, Driver 4.19. Mã nhận `CqlSession` **đã cấu hình** auth/TLS/local DC tới restore lab và kiểm tra một partition; không hardcode credentials hoặc endpoints production.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public final class RestoreFixtureVerifier {
    private RestoreFixtureVerifier() {}

    record Expected(String type, String payload, int revision) {}

    public static void verify(CqlSession session) {
        UUID deviceId =
            UUID.fromString("11111111-1111-4111-8111-111111111111");
        LocalDate day = LocalDate.of(2026, 11, 21);
        Map<UUID, Expected> expected = Map.of(
            UUID.fromString("22222222-2222-4222-8222-222222222222"),
            new Expected("created", "fixture-a", 1),
            UUID.fromString("33333333-3333-4333-8333-333333333333"),
            new Expected("confirmed", "fixture-b", 2)
        );

        PreparedStatement ps = session.prepare(
            "SELECT event_id, event_type, payload, revision " +
            "FROM restore_lab.events_by_device_day " +
            "WHERE device_id=? AND event_day=? LIMIT 100");
        BoundStatement stmt = ps.bind(deviceId, day)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setTimeout(Duration.ofSeconds(5))
            .setIdempotent(true);

        List<Row> rows = session.execute(stmt).all();
        Map<UUID, Expected> observed = new HashMap<>();
        for (Row row : rows) {
            UUID id = row.getUuid("event_id");
            Expected value = new Expected(
                row.getString("event_type"),
                row.getString("payload"),
                row.getInt("revision"));
            if (observed.put(id, value) != null) {
                throw new IllegalStateException("Duplicate event_id");
            }
        }
        if (!expected.equals(observed)) {
            throw new IllegalStateException(
                "RESTORE_MISMATCH expected=" + expected.size() +
                " observed=" + observed.size());
        }
    }
}
~~~

**Giới hạn mã mẫu:** dùng `LIMIT 100` và hai fixture IDs, không thay cho sampling hàng triệu partitions. Khi dữ liệu thật, log **hash/fingerprint và counts**, không log payload raw. Code để exception propagates làm CI test fail; không nuốt lỗi rồi xuất PASS. `LOCAL_QUORUM` chỉ hoạt động khi đúng RF/DC và node availability của lab.

### 10.3. Xác minh TTL và tombstones theo thời gian thực

Khi restore một snapshot chụp cách đây bảy ngày, nếu một cell có TTL 1 ngày **thì hôm nay nó đã hết hạn**. Không được đòi nó còn live chỉ vì snapshot từng chứa bytes. TTL được áp dụng theo write timestamp/expiry metadata; restore không tự “khởi động lại TTL từ 0” như INSERT mới.

Ví dụ một fixture có TTL:

~~~sql
INSERT INTO restore_lab.events_by_device_day
 (device_id,event_day,event_time,event_id,event_type,payload,revision)
VALUES (
  11111111-1111-4111-8111-111111111111,
  '2026-11-21','2026-11-21T10:05:00Z',
  44444444-4444-4444-8444-444444444444,
  'ephemeral','expires-in-lab',3
) USING TTL 3600;
~~~

Trong bảng lab còn live:

~~~sql
SELECT event_id, TTL(payload), WRITETIME(payload)
FROM restore_lab.events_by_device_day
WHERE device_id=11111111-1111-4111-8111-111111111111
  AND event_day='2026-11-21'
LIMIT 20;
~~~

`TTL(payload)` là **số giây còn lại** theo cell, `WRITETIME(payload)` phản ánh write timestamp CQL (microseconds theo CQL semantics), không là timestamp backup/upload. Nếu cell hết hạn, query có thể không còn trả row hoặc cột; **đừng thay `NULL` thành “missing backup”** trước khi xem deadline.

Tombstones cần được bảo toàn để dữ liệu đã DELETE không tái xuất hiện trên replica khác. Một restore kết hợp snapshot cũ với replicas live khác có thể tạo zombie data nếu tombstones đã purged sau grace; **chỉ restore trên isolated cluster và dùng recovery plan có timestamp/deletion history rõ**. Không giảm `gc_grace_seconds` để tăng tốc bài test.

### 10.4. Kiểm tra dữ liệu ở phân phối đại diện, không chỉ hai row

Một production-like drill cần:

- **Positive samples:** rows/partitions được kỳ vọng tồn tại, có payload hash/revision/operation ID.
- **Negative samples:** rows đã DELETE, TTL-expired cells, query phải không trả stale live data.
- **Boundary samples:** data trước và sau backup snapshot/PITR cut, late writes, concurrent updates.
- **Wide/hot partitions:** p95/p99/max rows per partition và paging theo query thật.
- **Types:** collections, frozen UDT, blobs, timestamps, counters/LWT nếu ứng dụng dùng; mỗi loại có semantics riêng.
- **Indexes/materialized views:** application queries thực và readiness sau rebuild.
- **Multi-DC:** local DC routing, RF/CL và cross-DC visibility requirements.
- **Auth:** role tối thiểu dùng bởi Java application có quyền SELECT/INSERT/UPDATE chỉ đúng target.

Đặt cỡ mẫu và acceptance gates từ trước; record coverage (%) theo partition/category. Không báo “mọi dữ liệu đúng” từ 100 samples trong backup hàng tỉ rows.

### 10.5. Không thử read consistency bằng cách chọn contact point

Java Driver query coordinator theo load balancing/routing. Kết nối tới một seed host **không ép** query đọc trực tiếp SSTable của host ấy; coordinator có thể liên lạc replicas khác. `ExecutionInfo.getCoordinator()` chỉ cho biết coordinator, không chứng minh data replica nào cung cấp từng cell.

Khi cần chứng minh replica convergence, dùng repair/integrity strategy hoặc tracing có sampling và permissions, không spam `LOCAL_ONE` requests tới một contact point rồi coi đó là node-specific verification.

## 11. Tự động hóa lịch restore drill và chặn thao tác nguy hiểm

### 11.1. Phân tầng lịch: kiểm file ≠ restore

Không cần dựng cluster và stream terabyte dữ liệu mỗi ngày để phát hiện object corruption. Tách:

1. **Daily metadata/file test:** backup job status, immutable objects, checksum samples hoặc full checksums theo budget, KMS reachability, manifest completeness, retention TTL.
2. **Weekly table restore:** lấy một backup set sealed, dựng schema, stream table synthetic/đại diện, CQL + Java verifier.
3. **Monthly service restore:** nhiều keyspaces, roles, app release, representative workload, RPO/RTO thật.
4. **Quarterly PITR/negative drill:** commitlog chain, timestamp boundaries, missing file, wrong version, unavailable KMS và recovery failure.
5. **Yearly regional DR exercise:** khôi phục trong failure domain khác, identity/keys/infra independence, phối hợp teams.

Lịch có thể thay theo tier/RPO: một dịch vụ không chấp nhận mất hơn 5 phút dữ liệu phải có kiểm tra chain/replication liên tục hơn. **Lịch diễn tập** khác **tần suất tạo backup**; đừng coi hai cấu hình là một.

### 11.2. CronJob Kubernetes minh họa với chế độ suspend an toàn

Manifest **tham khảo**, không tự bật chạy khi chưa có namespace, image, service account, network policy, admission policy và storage controls. `suspend: true` giúp bản mẫu không lập tức tạo job:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cassandra-restore-drill
  namespace: restore-drills
spec:
  schedule: "0 2 * * 0"
  timeZone: "Etc/UTC"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 3600
  suspend: true
  successfulJobsHistoryLimit: 2
  failedJobsHistoryLimit: 4
  jobTemplate:
    spec:
      backoffLimit: 0
      activeDeadlineSeconds: 14400
      ttlSecondsAfterFinished: 604800
      template:
        metadata:
          labels:
            app: cassandra-restore-drill
        spec:
          restartPolicy: Never
          serviceAccountName: restore-drill-runner
          containers:
            - name: restore-check
              image: registry.example.invalid/restore-drill@sha256:REPLACE
              command: ["/opt/drill/bin/run-isolated-restore"]
              args:
                - "--scope=synthetic-table"
                - "--target=isolated-restore-lab"
              resources:
                requests:
                  cpu: "500m"
                  memory: "1Gi"
                limits:
                  cpu: "2"
                  memory: "4Gi"
~~~

`registry.example.invalid` và `sha256:REPLACE` là **placeholder**, không phải image thật. `timeZone` yêu cầu Kubernetes hỗ trợ (bản đủ mới, ví dụ 1.27+), nên đối chiếu cluster/version. `concurrencyPolicy: Forbid` tránh **hai Job của cùng CronJob** chồng nhau, **không** bảo vệ khi có restore workflows khác hoặc người chạy tay; cần distributed lock/lease riêng theo target/account. `ttlSecondsAfterFinished` dọn đối tượng Job sau khi hoàn tất, **không thay** cleanup volumes/credentials/cloud resources hoặc lưu bằng chứng ngoài cluster.

Không đưa production KMS credentials vào environment variables/plain YAML. Dùng approved workload identity/secret manager, namespace network isolation, egress allowlist và read-only backup access. Nếu mục tiêu cần quyền tạo/delete cluster, chia permissions cho orchestrator và worker; worker không nên có quyền xóa mọi namespaces.

### 11.3. Pseudocode orchestrator fail-closed

~~~text
function scheduled_restore_drill(policy):
    run_id = allocate_unique_run_id()
    lock = acquire_lease(policy.target_environment)
    if lock is missing:
        record BLOCKED: ANOTHER_DRILL_RUNNING; return

    try:
        assert policy.target_environment in approved_lab_ids
        assert network_and_account_isolation()
        assert not target_has_non_test_data()
        selected = select_latest_sealed_backup(policy.scope)
        verify_manifest_signature_and_access(selected)
        verify_schema_version_compatibility(selected, target_version)
        local_copy = download_with_integrity_verification(selected)
        target = provision_fresh_isolated_cluster(run_id)
        assert target.cluster_id == approved_target_id(run_id)
        apply_validated_schema_and_lab_roles(target)
        stream_approved_sstables(target, local_copy, bounded_concurrency)
        verify_cluster_ready_and_schema(target)
        verify_fixture_ledger_and_negative_cases(target)
        verify_java_workflows_with_lab_credentials(target)
        assert observed_rpo <= policy.rpo
        assert observed_rto <= policy.rto
        seal_report(PASS, evidence)
    catch error:
        seal_report(FAIL_OR_BLOCKED, reason, evidence_so_far)
        notify_owner()
    finally:
        cleanup_only_resources_labeled_with(run_id)
        audit_cleanup_result()
        release_lease(lock)
~~~

Đây là **pseudocode thiết kế**; cần xử lý crash trước khi `seal_report` (durable checkpoints, outbox/report finalizer) và cleanup failure riêng. Tránh pattern `catch: return PASS`; runner phải trả exit code thất bại cho CI/scheduler khi fail.

### 11.4. Phân biệt deadline, retry, backoff và lỗi có thể sửa

| Lỗi | Retry? | Lý do |
|---|---|---|
| Transient object-store 503 | Có giới hạn + exponential backoff | Có thể tự phục hồi |
| Throttle/KMS rate limit | Có giới hạn, giữ quota | Phụ thuộc provider |
| SHA-256 mismatch | **Không retry mù rồi bỏ qua**; điều tra integrity | Có thể corruption hoặc tampering |
| Sai schema/SSTable version | Fail nhanh | Retry không sửa compatibility |
| Không đủ disk | Hold/scale theo policy | Retry có thể lặp outage |
| Wrong cluster/environment ID | ABORT ngay | Nguy cơ ghi vào sai target |
| Partial sstableloader run | Không stream lại bừa | Dựng fresh target hoặc recovery idempotent đã review |
| Missing restore key | BLOCKED, security owner | Không disable encryption |
| Java test fails | FAIL data/app gate | Không bỏ test cho xanh báo cáo |

### 11.5. Alert và escalations

Tạo alerts cho:

- **Missed drill:** không có completed run trong thời hạn policy.
- **Consecutive failures:** n lần FAIL, cùng error class lặp.
- **RPO/RTO breach:** actual vượt mục tiêu dù restore xong.
- **Data correctness breach:** missing/wrong fixtures, TTL/deletes mismatch.
- **Backup coverage gap:** missing node/table/object, recent backup not sealed.
- **Evidence incomplete:** audit sink/manifest signature unavailable.
- **Cleanup leak:** restore volumes, namespace, cloud instances hoặc tokens còn tồn.

Không tạo một alert chỉ khi backup job thất bại: một job có thể thành công lâu dài nhưng restore vẫn không chạy được. Dashboard nên hiển thị **last successful full restore verification** và **độ tuổi của bài diễn tập đáng tin gần nhất**.

## 12. Ghi nhận bằng chứng phục hồi để có thể audit

### 12.1. Bằng chứng theo từng mốc, không chỉ một screenshot

| Evidence ID | Nguồn | Dữ liệu bắt buộc | Câu hỏi nó trả lời |
|---|---|---|---|
| EV-001 | Scheduler/lock | Run ID, trigger, owner, UTC, lease | Drill thật sự đã chạy hay bị skip? |
| EV-002 | Backup index | Backup_set_id, scope, sealed state | Đã chọn đúng vật liệu chưa? |
| EV-003 | Manifest verification | File list, SHA-256, object versions, key reference | Vật liệu toàn vẹn và đọc được không? |
| EV-004 | Target inventory | Cluster ID, IP allowlist, version, RF/DC, config hash | Restore vào đúng cluster cách ly không? |
| EV-005 | Schema apply | DDL hash, UDT/indexes/table options, grants | Schema và privileges đúng không? |
| EV-006 | Streaming tool | Commands redacted, exit status, bytes, time, errors | Tool đã load bao nhiêu? |
| EV-007 | Cassandra state | `status`, JMX/GC/compaction, schema agreement | Target đủ healthy để verify? |
| EV-008 | CQL verifier | Fixture IDs hashed, row versions, TTL/deletes, CL | Dữ liệu đúng không? |
| EV-009 | Java integration | Driver version, local DC, TLS/auth, prepared CQL, outcomes | Ứng dụng có truy cập được không? |
| EV-010 | RPO/RTO report | T0/T5/T6, latest recoverable write, coverage | Có đạt mục tiêu DR không? |
| EV-011 | Cleanup audit | Resource IDs/labels, revoked credentials | Drill có để lại rủi ro không? |

**Bằng chứng phải được liên kết với cùng `run_id` và backup_set_id.** Một log parser thất bại hoặc thiếu metrics cần trở thành `EVIDENCE_GAP`, không tự điền “N/A nên PASS”. Ghi source clock và độ phân giải timestamp (scrape 15s, logs millisecond, etc.).

### 12.2. Report JSON minh họa

~~~json
{
  "run_id": "drill-20261121-a",
  "status": "PASS",
  "backup_set_id": "cass-restore-lab-20261121T120000Z",
  "restore_scope": ["restore_lab.events_by_device_day"],
  "target_cluster_id": "isolated-drill-a",
  "source_cassandra_version": "5.0.x-example",
  "target_cassandra_version": "5.0.x-example",
  "start_utc": "2026-11-21T12:00:00Z",
  "service_recovered_utc": "2026-11-21T12:19:00Z",
  "rto_seconds": 1140,
  "rto_target_seconds": 1800,
  "rpo_upper_bound_seconds": 420,
  "rpo_target_seconds": 900,
  "fixtures_checked": 500,
  "fixtures_failed": 0,
  "negative_cases_checked": 40,
  "data_gate": "PASS",
  "app_gate": "PASS",
  "evidence": ["EV-001", "EV-002", "EV-003", "EV-004",
               "EV-005", "EV-006", "EV-007", "EV-008",
               "EV-009", "EV-010", "EV-011"],
  "cleanup_status": "PASS"
}
~~~

**Đây là số liệu giả định** để minh họa cấu trúc, không phải kết quả từ cluster thật. Nếu chưa chạy test, status phải là `NOT_EXECUTED`. Nếu RPO chỉ được tính từ sample ledger thì ghi `rpo_upper_bound_seconds` cùng coverage/assumptions; không trộn số liệu ảo và real-run trong một báo cáo.

### 12.3. Quy tắc ký/xác thực báo cáo

Nên bảo vệ report/manifest bằng:

- Hash SHA-256 cho artifacts, một manifest chữ ký số hoặc tamper-evident storage.
- Immutable object version IDs và retention theo audit policy.
- Time source đáng tin (UTC), service/version/build information.
- Owner và approval của test, record policy/thresholds dùng khi chấm PASS.
- Redaction policy: không chứa passwords, TLS private keys, PII, raw user data.
- Separate access roles: tạo backup, đọc backup, chạy restore, xét duyệt evidence.

Không chỉ upload một file PDF chụp màn hình “SUCCESS”: có thể thiếu đúng lệnh chạy, source version, số fixtures, schema hash, hoặc RPO/RTO; báo cáo phải drill-down tới raw evidence.

### 12.4. Tách success của từng giai đoạn

Ví dụ kết quả “một nửa”:

~~~yaml
run_id: drill-20261121-b
artifacts_verified: PASS
cluster_provisioned: PASS
sstable_streamed: PASS
schema_verified: PASS
fixture_verification: FAIL
java_app_verification: NOT_RUN
rpo_evaluation: NOT_EVALUABLE
rto_evaluation: NOT_EVALUABLE
overall_status: FAIL
reason: "event_id X restored with wrong revision"
~~~

Trong case này, không gọi “restore 80% thành công” mà phải phân tích wrong data. Các phases khác PASS giúp khoanh vùng vấn đề, **không làm giảm mức nghiêm trọng của data correctness FAIL**.

### 12.5. Watermark của một bài restore tốt

Sau mỗi run, xuất dashboard/trend:

~~~text
last_verified_backup_set
last_verified_restore_utc
days_since_last_success
backup_coverage_percent_by_keyspace
manifest_file_verification_percent
restore_duration_p50/p95 (comparable scope only)
observed_rpo_by_service_tier
observed_rto_by_service_tier
data_invariant_failure_count
cleanup_failure_count
evidence_retention_expiry
~~~

Không gộp RTO của restore **một table 1 GiB** với **toàn cluster 20 TiB** thành một p95 “của Cassandra”. Report theo service tier/scope/topology/dataset size và lưu n để biết sample count đủ ý nghĩa.

### 12.6. Khi nào có thể dùng bằng chứng “không thấy lỗi”?

Không có `ERROR` trong loader logs không chứng minh 100% file integrity. Không có `ReadTimeoutException` trong 10 CQL reads không chứng minh đủ quorum dưới production load. Không có `UNAVAILABLE` lúc 1 node Up không chứng minh multi-DC DR. Chỉ dùng **absence of errors** khi coverage/sampling, log collection và error counters được xác nhận hoạt động; kết hợp với **positive assertions** về dữ liệu và app.

## 13. Negative tests: chứng minh workflow biết dừng và báo FAIL

### 13.1. Bộ tình huống tối thiểu

| Fault được tiêm **chỉ vào bản sao lab** | Kết quả mong đợi | Bằng chứng |
|---|---|---|
| Xóa một SSTable component khỏi **copy** | Integrity gate FAIL trước LOAD | Missing path + manifest diff |
| Thay một byte của `Data.db` trong bản copy | SHA-256 mismatch, ABORT | Expected/actual digests redacted |
| KMS key access denied | BLOCKED, không disable encryption | KMS access error, no plaintext fallback |
| Schema PK/clustering khác bản backup | SCHEMA_MISMATCH, không stream | DDL hash + table metadata diff |
| Version target không đọc được SSTable format | COMPATIBILITY_FAILED | Release/build + loader error |
| Chỉ upload snapshot của một node trong RF3 | COVERAGE_FAILED hoặc scope gắn nhãn partial | Per-node/token manifest |
| Object-store 503 ngắn | Retry bounded, có log attempts; eventual PASS/FAIL | Backoff/elapsed/attempts |
| Disk target đầy trong LOAD | FAIL + stop stream, giữ evidence | Disk free, I/O errors, cleanup audit |
| Job bị kill giữa stream | Không báo PASS; retry phải xử lý partial target | Checkpoint + new target test |
| Java user không có SELECT | APP_AUTH_FAILED | Role/grant and exception class |
| Sai local DC trong Driver | APP_CONNECTIVITY_FAILED | Driver config, node list, errors |
| Dữ liệu đã DELETE lại xuất hiện | DATA_INTEGRITY_FAILED | Fixture/TTL/delete ledger |
| PITR target trước/sau mutation boundary | Bao gồm và loại trừ đúng theo semantics | Write ledger + verified query |
| Evidence object store không ghi được | REPORT_FAILED, overall không SUCCESS | Audit sink error |
| Cleanup quota/dangling resource | RESTORE_PASS_CLEANUP_FAIL | Resource IDs, owner, remediation |

Không sửa trực tiếp snapshot gốc hoặc encrypted object trên production account để tạo negative case. Hãy **tạo bản sao synthetic riêng** và cô lập; sau khi kiểm, hủy theo resource ID của run.

### 13.2. Kiểm lỗi theo thứ tự ưu tiên

1. **Preflight failures** phải chặn trước khi dựng cluster/stream: wrong target, thiếu KMS, checksum, schema/version.
2. **Load failures** không được báo success: disk full, network partition, loader timeout, resource budget exceeded.
3. **Data failures** là blocker nghiêm trọng: wrong revision, missing partition, resurrected delete, TTL semantics sai.
4. **App failures** chặn service readiness: TLS, auth/grants, prepared CQL, codec, consistency.
5. **Reporting/cleanup failures** phải hiển thị rõ, không bị success của các pha trước nuốt mất.

Khi một lệnh trả non-zero, lưu stderr đã redact cùng code/UTC; khi tool bị kill mà không có exit code, báo `UNKNOWN_PROCESS_OUTCOME` và đối chiếu target/stream state. Không “thử lại đến khi PASS” trên cùng data dir sau partial restore mà chưa có idempotency guarantee.

### 13.3. Điểm khác biệt giữa negative test và phá dữ liệu

Ví dụ “xóa một SSTable component” chỉ được làm **trong staging copy do drill tạo**, sau khi kiểm source backup immutable còn nguyên. Test corruption có thể dùng một **fixture file fake đã được tool tạo** thay cho sửa file SSTable thật, miễn parser/checksum gate thật sự bị exercise.

Thao tác `nodetool clearsnapshot` hay xóa source backup không phải cách kiểm thử backup deletion resilience phù hợp nếu không có kế hoạch và phê duyệt. Nếu cần test retention/legal-hold, dùng riêng bucket lab với object lock/versions; không dùng account chứa backups cần cho production.

### 13.4. PITR boundary tests quan trọng

Trong lab, tạo một chuỗi writes có ledger:

~~~text
11:59:50Z  INSERT k1=v1, ACK at agreed CL
12:00:00Z  RESTORE_POINT_TARGET
12:00:10Z  UPDATE k1=v2, ACK
12:00:20Z  DELETE k2, ACK
12:00:25Z  UPDATE k3 USING TIMESTAMP older than k3 previous write
~~~

**Expected:** mốc 12:00 chỉ yêu cầu mutations theo cutoff semantics; value sau cutoff **không** được xuất hiện vì replay sai, nhưng những writes ở snapshot base trước cutoff có thể đã ở đó. Out-of-order client timestamps có thể làm kết quả khác arrival-order expectation; phải thiết kế fixture để biết **event time, write timestamp, arrival time, snapshot capture time** riêng.

Một test PITR thực chất cần:

- Snapshot base và commitlog segments được map theo source node/format, chain liên tục.
- Restore scripts/config và precision matching Cassandra version.
- Không dùng client-supplied timestamps tùy tiện làm chính xác hóa PITR.
- Độc lập đọc dữ liệu trước/sau target và kiểm tra negative samples.
- Không hứa atomic consistency across partitions/tables khi ứng dụng không có transaction barrier.

Nếu bài drill chỉ có snapshots không có commitlog archive chain, hãy ghi `PITR_NOT_CONFIGURED` chứ không báo PITR PASS. Tăng số lần snapshot có thể giúp RPO, nhưng không biến snapshot thành point-in-time transaction log.

### 13.5. Dữ liệu tạo từ workload thật phải có quyền rõ ràng

Nếu testing production-derived backup được cho phép, phải đánh giá:

- PII/regulated data/tenant isolation, data masking có thể thay đổi SSTable contents/PK distribution.
- Encryption at rest/in flight, scoped KMS, storage access audit.
- Output logs/trace chỉ chứa hashes, không có query bind values nhạy cảm.
- Data retention/cleanup độc lập theo thời hạn phê duyệt.
- Legal/compliance requirements của tổ chức, không được chuyển data ra region bất kỳ.

Mặc định **ưu tiên synthetic backup**, hoặc bản backup production đã được khử định danh bằng quy trình được công nhận và kiểm chứng an toàn. Không coi hash thô của user ID dễ đoán là đủ bảo vệ riêng tư.

## 14. Bảo mật, quyền truy cập và vòng đời bản backup

### 14.1. Hai chiều quyền: backup và restore

| Actor | Quyền cần | Quyền không nên có |
|---|---|---|
| Backup agent | Read snapshot local, upload đúng backup prefix | DROP keyspace, read unrelated secrets |
| Restore scheduler | Đọc metadata, tạo run/lock | Native CQL production mutation |
| Restore worker | Read-only sealed backup objects, decrypt theo KMS, write cluster lab | Delete source backups, root toàn cloud account |
| Schema migrator | CREATE/ALTER trong restore namespace lab | ALTER production schema |
| Verifier | SELECT/limited canary write trong lab | Admin data export không giới hạn |
| Evidence writer | Append/write audit run prefix | Rewrite old reports, delete retention objects |
| Cleanup agent | Delete resources tagged run_id trong lab | List/delete all projects/clusters |

**Backup object encryption và database authentication là hai lớp độc lập.** Giải mã được SSTables không chứng minh Java user đã được cấp permission. Ngược lại, một superuser có quyền CQL trong restore cluster không nhất thiết có quyền decrypt các objects.

### 14.2. Kiểm tra key rotation và disaster independence

KMS key rotation an toàn thông thường có key versions và retention; nhưng nếu key bị hủy, backup dù còn intact có thể không giải mã được. Drill:

1. Ghi key alias/ID/version references của backup set, không lưu plaintext DEK.
2. Xác minh restore workload identity có quyền decrypt đúng context.
3. Kiểm thử cross-account/region keys theo DR policy, không mặc định KMS source region sẵn.
4. Kiểm tra audit event của decrypt và revoke after job.
5. Test deny-access **trong sandbox** và xác minh workflow fail-closed.

Không tự export private keys/DB passwords vào backup manifest hay test artifact; mọi kết quả phải redact trước khi lưu report.

### 14.3. Retention cần bảo vệ cả khả năng restore

Chính sách thường cần:

- Immutable snapshot baseline và incremental/commitlog chain **không bị tách rời**.
- Retention đủ cho RPO/RTO/legal hold và thời gian phát hiện xóa nhầm.
- Cleanup phần local hardlinks chỉ sau khi upload/verification/retention policy đạt.
- Chỉ xóa remote objects sau khi không còn backup sets phụ thuộc; có audit.
- Các manifest/schema/keys references còn tồn tại trong toàn retention window.
- Thử restore bản **cũ nhất còn được phép dùng**, không chỉ “latest”.

Nếu retention policy xóa baseline mà giữ incrementals, có thể mất đường khôi phục. Ngược lại, backup nhiều tháng trước khi restore vào hiện tại có thể chứa tombstones/TTL/dữ liệu nhạy cảm đã hết hạn; phải kiểm business/legal semantics trước khi khôi phục vào luồng phục vụ.

### 14.4. Kiểm tra khả năng đổi vùng

Một DR test khác AZ/region cần ghi:

~~~text
source and target failure domains
independent object-store location / immutable version
independent KMS recovery path
new cluster network endpoints, DNS, certificates, truststores
RF/DC strategy and Java Driver local DC
inter-DC streaming/network quotas
schema/roles/secrets availability
manual approvals and audit trail
~~~

Nếu source và target nằm trên cùng failure domain/network identity, phải ghi scope `SAME_REGION_RESTORE` thay vì `REGIONAL_DR_VALIDATED`.

## 15. Các tình huống vận hành và cách đánh giá kết quả

### 15.1. Case A — Backup có đủ files nhưng khôi phục không được

**Bối cảnh:** job snapshot một table chạy 00:00Z, upload 00:10Z, manifest PASS. Khi dựng cluster đích, loader báo không hiểu SSTable version. Target đang dùng Cassandra 4.1 trong khi nguồn 5.0.

**Phân tích:**

1. So version thực và SSTable format, JDK/driver compatibility; không coi backup corruption khi nguyên nhân là downgrade unsupported.
2. Dùng target Cassandra release tương thích hoặc có migration strategy được kiểm chứng.
3. Lưu `COMPATIBILITY_FAILED`, source/target version và loader logs trong evidence.
4. Test lại trên **fresh target**, không vá trực tiếp cluster sản xuất.

**Điểm học:** backup integrity và restore compatibility là hai gates riêng. Việc hash match 100% không bảo đảm phiên bản target đọc được SSTables.

### 15.2. Case B — Stream hoàn tất nhưng service Java vẫn lỗi

**Bối cảnh:** `sstableloader` exit 0, CQL admin SELECT thấy fixtures, nhưng Java Driver trả `UnauthorizedException` hoặc TLS handshake lỗi.

**Phân tích:**

- Khả năng cao schema/data path đã hoạt động trong phạm vi admin, nhưng **application readiness FAIL**.
- Kiểm tra role/grant, `system_auth` recovery plan, secret manager, client truststore/server certificate, local DC.
- Phân biệt `UnauthorizedException` (CQL authorization) với `SSLHandshakeException` (TLS); không retry mù hoặc tắt TLS verification.
- Báo `DATA_PASS_APP_FAIL`, tính RTO service chưa đạt cho đến khi app path hoàn tất.

**Điểm học:** application contract gồm schema, credentials, driver profile, consistency, codec và query shapes; không chỉ SSTables.

### 15.3. Case C — Backup mới nhất nhưng RPO tệ hơn mong muốn

**Bối cảnh giả định:** business mục tiêu RPO 10 phút. Snapshot hoàn tất 12:00Z, upload 12:05Z. Disaster cut 12:45Z; không có incremental upload hoặc commitlog archive. Test khôi phục snapshot chỉ chứng minh writes đến 12:00Z.

**Phân tích:**

- Backup pipeline có thể đúng theo thiết kế, nhưng **RPO policy FAIL**.
- Không lấy `upload_time=12:05Z` làm latest recoverable write.
- Tăng frequency of trustworthy snapshots hoặc triển khai incremental/commitlog capture thích hợp, song vẫn phải kiểm chain thực.
- Phân biệt replication availability với khả năng quay lại snapshot lịch sử khi xóa nhầm dữ liệu.

**Điểm học:** RPO là yêu cầu kiến trúc và kiểm chứng, không được sửa trên dashboard bằng cách chọn một timestamp thuận lợi.

### 15.4. Case D — Restore một table nhưng nhiều API có kết quả sai

**Bối cảnh:** table `events_by_device_day` được restore; các endpoints còn query secondary index/SAI, materialized view, UDT hoặc table denormalized khác.

**Phân tích:**

1. Kiểm schema dependency graph và query fingerprint của tất cả endpoints.
2. Xác định restore scope **một table** không bằng **một service**.
3. Test index build/query readiness và các bảng projection/denormalized được viết riêng.
4. Ghi `RLO: TABLE_ONLY`, không gắn nhãn toàn bộ service recovered.

**Điểm học:** Cassandra được thiết kế theo truy vấn; một luồng nghiệp vụ có thể phụ thuộc nhiều bảng phục vụ nhiều query shapes.

### 15.5. Case E — Restore bản cũ gây lệch TTL/deletion

**Bối cảnh:** một bản snapshot 10 ngày trước chứa record dùng TTL 7 ngày hoặc record đã DELETE sau snapshot. Restore vào hôm nay, ứng dụng kỳ vọng state hiện tại.

**Phân tích:**

- TTL per-cell có thể khiến record đã expire **không live** hôm nay; đó chưa phải lỗi loader.
- Nếu record DELETE sau snapshot, việc restore bản trước DELETE có thể **đúng cho point-in-time backup** nhưng sai cho mục tiêu “state hiện tại”.
- Nếu restore snapshots cũ trộn cùng replicas hiện tại, có thể tạo lệch timestamp/tombstone và nguy cơ zombie.
- Cần xác định restore target time, business recovery invariant và xem xét event replay/deletion ledger.

**Điểm học:** data verification phải so với **expected state tại recovery point**, không luôn so với latest production.

### 15.6. Case F — RTO tăng mạnh khi workload có kích thước thực

**Bối cảnh:** tuần trước restore một table 1 GiB mất 3 phút; lần này restore keyspace 5 TiB tới cross-region chỉ còn 1 Gbit/s egress và làm quá tải target compaction.

**Phân tích:**

1. Benchmark scope/bytes/network/CPU/disk của từng drill, không so hai RTO khác điều kiện như cùng bài.
2. Ước tính **lower bound** thời gian truyền chỉ từ bytes và băng thông: `5 TiB / 1 Gbit/s` có thể mất nhiều giờ/ngày chưa kể overhead.
3. Báo băng thông hiệu dụng, per-phase time và bottleneck.
4. Đánh giá parallelism, compression, snapshot sharding, index rebuild và capacity, nhưng không tăng concurrency vô hạn.

**Điểm học:** RTO phải được thử ở **quy mô đại diện**; restore tiny fixture không chứng minh toàn bộ dữ liệu sẽ kịp SLO.

### 15.7. Quy tắc công bố kết quả

| Tình trạng | Báo cáo đúng | Không ghi |
|---|---|---|
| Không chạy vì preflight fail | `BLOCKED` với lý do | `PASS` |
| Download và checksum PASS, chưa load | `BACKUP_VERIFIED_ONLY` | `RESTORE_VERIFIED` |
| Loader PASS, data FAIL | `DATA_INTEGRITY_FAIL` | `PARTIAL_PASS` không ghi lý do |
| Data PASS, Java FAIL | `DATA_PASS_APP_FAIL` | `SERVICE_RESTORED` |
| Data/app PASS, RPO breach | `RESTORE_WORKED_RPO_FAIL` | `DR_SLO_PASS` |
| RPO/RTO PASS, cleanup fail | `RESTORE_PASS_CLEANUP_FAIL` | `ALL_PASS` |
| All gates PASS, evidence sealed | `RESTORE_VERIFIED` | “Mọi failure mode đều được bảo đảm” |

## 16. Bài tập và câu hỏi tự đánh giá

### Bài 1 — Backup thành công có chứng minh restore không?

Một dashboard hiển thị 100% snapshot/upload jobs thành công suốt 90 ngày, chưa từng test loader/Java.

**Đáp án:** không. Chỉ chứng minh một phần backup pipeline. Cần restore trên cluster biệt lập và xác minh data/app/RPO/RTO.

### Bài 2 — Bản snapshot vẫn ở ổ của node

Operator thấy `snapshots/<tag>` trên cùng volume Cassandra, không có offsite copy. Một disk bị mất.

**Đáp án:** hardlinks cùng filesystem mất theo disk; phải export/verify bản độc lập với failure domain, có retention và key access.

### Bài 3 — Một node đã snapshot có đủ RF3?

Trong cluster RF3 nhiều token ranges, N1 có snapshot và N2/N3 chưa snapshot; có thể báo full cluster backup không?

**Đáp án:** không tự động. Cần coverage theo node/table/token, dữ liệu có thể chưa đồng bộ ở replicas hoặc N1 không sở hữu mọi token range trong cluster. Ghi partial scope.

### Bài 4 — Snapshot với skip-flush

Một write đã ACK và còn trong memtable; job dùng `nodetool snapshot --skip-flush`.

**Đáp án:** snapshot có thể thiếu write chưa vào SSTable; phải kiểm flush semantics và giới hạn RPO. Nếu không có commitlog archive, snapshot này không tự bao gồm memtable.

### Bài 5 — RTO đo sai

Đội báo RTO 2 phút từ lúc `sstableloader` bắt đầu đến lúc kết thúc, nhưng provisioning và Java tests thêm 20 phút.

**Đáp án:** đo theo recovery contract từ `T0` đến service readiness/validation gate; báo per-phase duration nhưng không gọi 2 phút là service RTO.

### Bài 6 — Incremental backup có commitlog không?

Một đội bật `incremental_backups: true` và kỳ vọng replay được mọi mutation trước khi memtable flush.

**Đáp án:** không. Incremental backups lưu hardlinks tới SSTables sau flush/stream; cần commitlog archiving cho phần mutations thuộc mục tiêu PITR, và test chain thực.

### Bài 7 — Chọn restore path

Cluster mới có token ranges và table IDs khác nguồn. Có nên copy raw SSTables vào live data directories rồi `nodetool refresh`?

**Đáp án:** không mặc định. `sstableloader` thường phù hợp hơn khi muốn stream tới natural replicas của topology mới. Refresh dành cho local SSTables đã đặt đúng layout/node và đúng schema.

### Bài 8 — Checksum match nhưng schema sai

Manifest files SHA-256 đều khớp, nhưng target table có clustering order/PK khác.

**Đáp án:** `SCHEMA_MISMATCH`, fail trước LOAD. File integrity không đồng nghĩa CQL compatibility.

### Bài 9 — Node là UN nên ứng dụng sẵn sàng?

Restore cluster tất cả node `UN` nhưng Java user không SELECT được do thiếu grants.

**Đáp án:** không. App readiness FAIL; kiểm auth, TLS, local DC, prepared CQL và business transactions.

### Bài 10 — Restore TTL có “reset” không?

Một row TTL 24 giờ nằm trong snapshot 7 ngày trước; hôm nay restore.

**Đáp án:** TTL metadata không đơn giản reset theo thời điểm restore; cell có thể đã expired. Kiểm expected state tại recovery time.

### Bài 11 — Counter timeout sau PITR

Client tăng counter, nhận timeout, rồi retry; backup/commitlog replay tạo trạng thái khác expected.

**Đáp án:** timeout có unknown outcome, counters không idempotent như set cell. Kiểm operation ledger, write/replay semantics; không tái phát counter tăng tùy tiện.

### Bài 12 — KMS bị revoke

Backup objects vẫn đọc được nhưng decrypt thất bại, đội đề xuất tắt encryption.

**Đáp án:** không. Phải `BLOCKED/FAIL`; theo key recovery/rotation procedure và audit. Không weaken security để tạo test xanh.

### Bài 13 — PITR timestamp quá tự tin

Application dùng client write timestamps out of order nhưng đội tuyên bố cắt tại 12:00Z sẽ khôi phục một trạng thái giao dịch nguyên tử giữa mọi tables.

**Đáp án:** không. PITR replay dựa trên timestamp/segment semantics, Cassandra không có global transaction cut theo một wall clock cho mọi tables. Cần application barrier và validate boundary fixtures.

### Bài 14 — Thay một byte trong staging backup

Checksum mismatch xảy ra sau khi fault inject trên **bản copy** của SSTable. Runner tiếp tục stream vì có 99% files còn nguyên.

**Đáp án:** FAIL/PRECHECK_FAILED; không được âm thầm bỏ component để báo recovery success. Hành vi dừng là mục tiêu negative test.

### Bài 15 — Kết quả service PASS nhưng cleanup thất bại

CQL và Java tests PASS, nhưng namespace lab/KMS grant/volume vẫn tồn tại.

**Đáp án:** tách `RESTORE_PASS_CLEANUP_FAIL` và xử lý tài nguyên/credential với owner, không gọi all-green.

### Bài 16 — Một fixture dùng làm toàn cluster RPO

Trong 10 triệu rows, team kiểm hai rows và thấy latest ACK tại 11:59Z (disaster 12:00Z), rồi báo guaranteed RPO 1 phút.

**Đáp án:** không đủ. Report sample coverage và uncertainty; cần token/partition stratified evidence và backup chain completeness để hỗ trợ phạm vi công bố.

### Checklist trước khi chấp nhận một bài diễn tập

- [ ] Đã ghi source cluster, target lab cluster ID, Cassandra/JDK/Driver versions.
- [ ] Có owner, run_id, backup_set_id, UTC window và lease chống chạy trùng.
- [ ] Target nằm trong allowlist non-prod, không thể ghi vào native Cassandra production.
- [ ] Data source synthetic/được phép, credentials/keys được bảo vệ và có log audit.
- [ ] Schema, UDT, indexes, auth/roles và app release được version/ghi trong manifest.
- [ ] Snapshot bao phủ đủ source nodes/tables/token ranges theo scope được công bố.
- [ ] SSTable components/size/SHA-256/manifest signature đều được verify sau download.
- [ ] Incremental/commitlog chains (nếu dùng) có đủ segments và watermark đã xác minh.
- [ ] Mọi key/key version còn có thể decrypt trong recovery domain.
- [ ] Dùng loader/refresh theo đúng topology/format; không copy system.local/peers giữa clusters.
- [ ] CQL test có partition keys chính xác, tránh full table COUNT(*) trên dataset lớn.
- [ ] Kiểm positive/negative records, TTL/tombstones, latest/old writes và LWT/counter nếu có.
- [ ] Java Driver kiểm đúng CL, local DC, TLS/auth, prepared query và serialization.
- [ ] RPO được tính từ latest **verified recoverable business write** và nêu coverage.
- [ ] RTO tính từ DR start theo contract đến app/data readiness, có per-phase durations.
- [ ] Monitoring target disk/GC/compaction/network và errors dưới tải đại diện.
- [ ] Có ít nhất một negative test để chứng minh fail-closed và không âm thầm bỏ file.
- [ ] Report PASS/FAIL/BLOCKED chỉ dựa trên các gates thực tế, không dự đoán.
- [ ] Evidence được seal, có checksum/retention/links/owner, không chứa secrets/PII.
- [ ] Cleanup chỉ thao tác đúng resources của run_id và có audit/owner nếu thất bại.
- [ ] Lịch diễn tập, tuổi lần PASS cuối và các remediation được giám sát.

## 17. Tài liệu tham khảo

1. Apache Cassandra — [Backups](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/backups.html): snapshots, incremental backups, hard links, `schema.cql`, các restore paths.
2. Apache Cassandra — [nodetool snapshot](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/snapshot.html): tag, table/keyspace scope, `--skip-flush` và giới hạn.
3. Apache Cassandra — [nodetool listsnapshots](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/listsnapshots.html): kiểm tra snapshot list và phân biệt size on disk/true size.
4. Apache Cassandra — [nodetool refresh](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/refresh.html): nạp local SSTables đã được đặt vào node theo layout phù hợp.
5. Apache Cassandra — [sstableloader](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstableloader.html): stream SSTables đến cluster đích theo topology, input path naming, `--nodes`, streaming/TLS options.
6. Apache Cassandra — [commitlog-archiving.properties](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_cl_archive_file.html): archive/restore commands, restore directories, point-in-time và timestamp precision.
7. Apache Cassandra — [cassandra.yaml configuration](https://cassandra.apache.org/doc/latest/cassandra/managing/configuration/cass_yaml_file.html): `incremental_backups`, `auto_snapshot`, `snapshot_before_compaction`, commitlog và storage options.
8. Apache Cassandra — [SSTable tools](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/index.html): các offline tools và điều kiện bảo đảm an toàn khi sử dụng.
9. Apache Cassandra — [Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): anti-entropy, khác biệt với backup, chi phí và phạm vi.
10. Apache Cassandra — [Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html): TTL, deletion markers, grace và nguy cơ zombie data.
11. Apache Cassandra — [Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): table/client request/compaction/disk metrics để theo dõi khi restore.
12. Apache Cassandra — [CQL DDL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html) và [CQL DML](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): NetworkTopologyStrategy, primary keys, TTL, timestamps, read/write semantics.
13. Apache Cassandra Java Driver 4.19 — [Configuration](https://apache.github.io/cassandra-java-driver/4.19.0/core/configuration/): driver profiles, local datacenter, request timeout và TLS/auth patterns.
14. Apache Cassandra Java Driver 4.19 — [Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/): prepared/bound statements, consistency, timeout và idempotence.
15. Apache Cassandra Java Driver 4.19 — [Paging](https://apache.github.io/cassandra-java-driver/4.19.0/core/paging/): cách tiêu thụ ResultSet và số pages thực.
16. Kubernetes — [CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/): schedule/timezone, concurrencyPolicy, suspend, startingDeadlineSeconds; dùng khi orchestration trên Kubernetes.

**Kết luận:** “Có backup” chỉ là bước đầu. Thử restore định kỳ phải chứng minh một bản backup có thể dựng lại **đúng schema, dữ liệu và đường truy cập ứng dụng** ở môi trường cách ly, **trong RPO/RTO đã cam kết**, với bằng chứng bất biến và quy trình dừng an toàn khi bất kỳ gate nào thất bại. Mọi thông báo `PASS` đều cần gắn với **scope, phiên bản, backup_set_id, run_id và điều kiện kiểm chứng**; không được suy rộng kết quả restore một table synthetic thành bảo đảm phục hồi toàn cluster.
