# Khôi phục bảng hoặc keyspace vào môi trường cô lập trong Apache Cassandra

## 1. Mục tiêu của một cuộc diễn tập phục hồi

Apache Cassandra là hệ quản trị dữ liệu phân tán theo mô hình **wide-column**. Partition được định vị theo **partition key**, các replica được sắp đặt bằng token và replication strategy, còn ứng dụng Java đọc/ghi bằng CQL với consistency level phù hợp. Khi xảy ra xóa nhầm, lỗi ứng dụng, mất nhiều node hoặc sự cố storage, việc cluster còn replica không đồng nghĩa có thể quay lại dữ liệu cũ một cách an toàn.

Trong chương **Sao lưu và phục hồi** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, bài này tập trung vào câu hỏi:

> Làm sao khôi phục một bảng hoặc cả keyspace từ bộ sao lưu vào **cluster Cassandra riêng biệt**, để kiểm chứng dữ liệu và quy trình mà **không vô tình làm thay đổi production**?

Mục tiêu của môi trường cô lập không nhất thiết là tái tạo hạ tầng với quy mô 100% production. Mục tiêu quan trọng hơn là có một **đích phục hồi có danh tính, dữ liệu, quyền truy cập và đường mạng độc lập**, cho phép thực hiện những việc sau:

1. **Chứng minh backup có thể đọc được**: file SSTable còn đủ, tương thích và qua các bước kiểm tra tính toàn vẹn.
2. **Chứng minh schema có thể tái dựng**: keyspace, table, primary key, type, replication, index và các phụ thuộc cần thiết.
3. **Chứng minh dữ liệu phục hồi đúng** theo mốc thời gian và phạm vi mà backup cho phép.
4. **Đo thời gian khôi phục** để so sánh với RTO và phát hiện các bước chậm.
5. **Phân tích xóa nhầm/corruption** mà không trộn dữ liệu backup cũ vào production.
6. **Cho phép QA/ứng dụng Java truy vấn có kiểm soát** nhằm đối soát key, query shape, TTL, consistency và các quy tắc nghiệp vụ.

**Nguyên tắc an toàn số một:** không thử phục hồi bằng cách copy SSTable hoặc chạy lệnh import trực tiếp vào cụm production trước khi đã kiểm chứng được dữ liệu và kế hoạch thay đổi.

## 2. Backup, replica, repair và restore là những khái niệm khác nhau

| Cơ chế | Mục đích | Có thể lấy lại dữ liệu trước một DELETE đã replicate? | Phù hợp mục tiêu bài học |
|---|---|---|---|
| **Replication** | Giữ các bản sao hiện thời trên nhiều replica | Thông thường **không**: DELETE cũng được replicate | Bảo vệ availability, không thay backup |
| **Repair** | So sánh và đồng bộ khác biệt giữa replica | Không phải cơ chế quay ngược thời gian | Duy trì consistency sau khi cluster hoạt động |
| **Hinted handoff** | Gửi bù mutation khi replica vắng mặt tạm thời | Không: hint có thể chứa DELETE mới | Giảm sai lệch tạm thời giữa replica |
| **Snapshot** | Chụp phiên bản SSTable tại thời điểm được yêu cầu | **Có thể**, nếu snapshot còn dữ liệu và các điều kiện TTL/schema cho phép | Nguồn chính của bài tập restore |
| **Incremental backup** | Lưu thêm SSTable đã flush kể từ mốc được quản lý | Có thể bổ trợ snapshot, nhưng không tự tạo PITR hoàn chỉnh | Phục hồi dữ liệu mới hơn theo chính sách |
| **Commit-log archive** | Lưu các segment log để có thể replay theo quy trình được hỗ trợ | Có thể tham gia point-in-time recovery khi đã cấu hình/kiểm chứng đầy đủ | Chủ đề nâng cao, phụ thuộc phiên bản |
| **Restore vào cluster cô lập** | Tái dựng schema và dữ liệu ở đích độc lập | Có thể dùng backup để xem trạng thái trước sự cố | Nội dung trọng tâm |

**Không có backup độc lập thì replication không phải “phiên bản cũ”.** Nếu tất cả replica đã nhận lệnh xóa hợp lệ, repair thường củng cố sự xóa đó thay vì phục hồi dữ liệu cũ.

## 3. Phạm vi restore: một bảng khác gì cả keyspace?

### 3.1. Restore một bảng

Ví dụ chỉ bảng `commerce.orders_by_id` bị thao tác UPDATE lỗi trong lúc các bảng khác vẫn đúng. Phạm vi hợp lý có thể là:

- Lấy đúng bộ snapshot/SSTable của bảng `orders_by_id`.
- Tái tạo **keyspace và bảng tương thích** trong cluster cô lập.
- Nhập các SSTable cần thiết, kiểm tra row/timestamp/tombstone/TTL.
- Trích xuất tập bản ghi cần thiết hoặc chuẩn bị phương án phục hồi tiếp theo đã được phê duyệt.

Không cần nhập mọi bảng của keyspace nếu cuộc điều tra chỉ nhằm xem một partition bị sửa nhầm. Nhưng phải hiểu dữ liệu của bảng có phụ thuộc vào các bảng khác, UDT, indexing hoặc logic nghiệp vụ không.

### 3.2. Restore cả keyspace

Restore toàn bộ keyspace có phạm vi rộng hơn:

- Keyspace replication settings phải được **chuyển đổi có chủ đích** cho topology của môi trường cô lập.
- Các bảng, user-defined types (UDT), index, materialized view, function/aggregate nếu được sử dụng cần được kiểm kê.
- Phải thu thập dữ liệu của **tất cả bảng** cần phục hồi và kiểm chứng coverage của từng bảng.
- Snapshot trên các node khác nhau không mặc định tạo **một transaction nhất quán toàn keyspace**.

Đối với nghiệp vụ có các bảng denormalized, ví dụ `orders_by_id` và `orders_by_customer`, restore một bảng có thể tạo cái nhìn thiếu hoặc mâu thuẫn với bảng còn lại. Đây là vấn đề thiết kế và consistency của ứng dụng, không chỉ là việc copy file.

### 3.3. Những trường hợp phải cẩn thận hơn

- **Counter table:** không tự replay INSERT/UPDATE counter như row thường; increment có semantics khác và retry có thể nhân đôi.
- **Materialized view / secondary index:** cơ chế tạo/rebuild dữ liệu phụ thuộc phiên bản và tính năng, không mặc định file SSTable base table tự tái dựng mọi cấu trúc.
- **LWT/Paxos:** snapshot bảng dữ liệu không tương đương snapshot đầy đủ trạng thái đồng thuận cho một tập transaction đang chạy.
- **TTL:** dữ liệu có thể **hết hạn theo thời gian thực** sau thời điểm snapshot; restore không làm đồng hồ quay ngược.
- **Tombstone và gc_grace_seconds:** phục hồi thiếu snapshot/SSTable liên quan có thể tái hiện dữ liệu không đúng hoặc mất semantics của delete.
- **CDC, trigger, integration:** phải xác định có nên vô hiệu hóa trên môi trường cô lập để tránh phát sinh side effect.

## 4. Kiến trúc môi trường cô lập an toàn

### 4.1. Cô lập ở nhiều tầng

Một cluster kiểm thử chỉ được gọi là **cô lập** khi ít nhất các yếu tố sau được xem xét.

| Tầng | Yêu cầu cơ bản | Lý do |
|---|---|---|
| **Cluster identity** | `cluster_name` riêng, host ID mới, gossip không trộn production | Tránh node thử nghiệm gia nhập ring thật |
| **Network** | VPC/subnet, firewall, security group và seed chỉ trỏ đến node restore | Tránh trao đổi gossip/stream/CQL với production |
| **Data directories** | Disk và filesystem riêng, không mount nhầm volume production | Tránh ghi đè SSTable, commit log hoặc snapshot gốc |
| **Credentials/TLS** | Identity/secret riêng cho môi trường phục hồi | Không làm lộ khóa hoặc cấp quyền production không cần thiết |
| **Contact points** | CQL client chỉ dùng IP/DNS đích restore | Tránh Java vô tình thực hiện CQL trên production |
| **External side effects** | Tắt hoặc sandbox job, CDC consumer, webhook, email, payment integration | Ngăn dữ liệu cũ gây hành động ngoài ý muốn |
| **Access control** | Quyền hạn tối thiểu, audit, log retention | Dữ liệu backup có thể chứa PII và secrets |
| **Tài nguyên** | Quota CPU/RAM/disk/network riêng, giám sát disk free | Restore/streaming là thao tác I/O nặng |

**Đổi tên keyspace đơn thuần không tạo môi trường cô lập.** Nếu chạy `sstableloader` trỏ đến contact point của production, dữ liệu vẫn được nạp vào cụm thật dù thư mục nguồn nằm trên một máy lab.

### 4.2. Sơ đồ luồng phục hồi

~~~mermaid
flowchart TD
    A["Backup bất biến: snapshot SSTable + metadata"] --> B["Kiểm tra manifest/checksum"]
    B --> C["Staging chỉ đọc; không sửa backup gốc"]
    C --> D["Cluster phục hồi riêng: cluster_name/seeds/network"]
    E["Schema CQL phù hợp + RF trong restore DC"] --> D
    D --> F["sstableloader hoặc nạp SSTable theo runbook"]
    F --> G["Kiểm tra dữ liệu, TTL/tombstone, schema"]
    G --> H["Ứng dụng Java chỉ đọc trên restore cluster"]
    H --> I["Báo cáo RPO/RTO và bằng chứng"]
    I --> J["Giữ phục vụ điều tra hoặc hủy lab theo chính sách"]
    K["Production"] -. "KHÔNG KẾT NỐI NẠP DỮ LIỆU" .-> D
~~~

Lưu ý: mũi tên nét đứt là **ranh giới ngăn kết nối**, không phải một luồng dữ liệu cần thiết. Backup được **sao chép có kiểm soát** từ kho lưu hoặc media sang staging của môi trường cô lập.

### 4.3. Checklist trước khi chạm vào backup

~~~text
[ ] Mục tiêu: chỉ một table hay toàn keyspace?
[ ] Mốc dữ liệu mong muốn, RPO và RTO?
[ ] Xác nhận đúng snapshot tag, thời điểm và nguồn node/DC?
[ ] Có đủ tất cả SSTable components/manifest/schema tương ứng?
[ ] Có backup data khác, incremental backup, commit-log archive không?
[ ] Đã kiểm tra phiên bản SSTable và Cassandra đích tương thích?
[ ] Đích là cluster_name mới, IP/seed riêng và firewall chặn production?
[ ] Thông tin xác thực, certificate và KMS key xử lý an toàn?
[ ] Dung lượng đích đủ cho data, streaming, compaction và headroom?
[ ] Tất cả automation có khả năng phát side effect đã được cô lập?
[ ] Có kế hoạch ghi lại checksums, tiến độ, lỗi và thời điểm thao tác?
~~~

Đừng bắt đầu bằng `nodetool refresh` hoặc `sstableloader` rồi mới tìm xem nguồn dữ liệu là từ đâu.

## 5. Snapshot của Cassandra chứa những gì?

### 5.1. Snapshot dựa trên SSTable

Cassandra sử dụng các tệp **SSTable bất biến**. Snapshot thường dựa trên hard link của những thành phần SSTable tại thời điểm chụp; cấu trúc thư mục có dạng minh họa:

~~~text
/var/lib/cassandra/data/
  commerce/
    orders_by_id-<table-id>/
      snapshots/
        pre_incident_20261121/
          <sstable-component-files>
          <manifest-or-metadata-if-present>
~~~

Đường dẫn thực tế phụ thuộc cấu hình `data_file_directories`, phiên bản và table ID. Một bảng có thể có SSTable trên **nhiều data directory**; chỉ sao lưu một thư mục không đảm bảo đủ bảng.

Snapshot giữ SSTable tại mốc chụp; thao tác `nodetool snapshot` trong cấu hình thông thường sẽ phối hợp flush dữ liệu đang ở memtable, trừ khi dùng lựa chọn bỏ flush như `--skip-flush` nếu được hỗ trợ. **Phải kiểm tra phương thức snapshot và log thực tế**, nhất là khi đánh giá những mutation rất mới.

### 5.2. Lệnh tạo snapshot (minh họa)

Trên các node được yêu cầu trong kế hoạch backup và với cú pháp đúng phiên bản:

~~~bash
# Chụp một table; kiểm tra 'nodetool help snapshot' của bản đang dùng.
nodetool snapshot -t recovery_drill_20261121 -cf orders_by_id commerce

# Chụp toàn keyspace trên node này.
nodetool snapshot -t recovery_drill_20261121 commerce

# Liệt kê snapshot được node biết.
nodetool listsnapshots
~~~

**Cảnh báo:** lệnh trên chỉ chụp **node đang kết nối**, không tự động chụp đủ mọi replica/đủ mọi node của cluster. Cần dùng một cơ chế orchestration có kiểm chứng để thu thập đúng phạm vi token/DC và bảo đảm các node cần thiết đã chụp thành công.

Các tham số như `-cf`, cách truyền keyspace/table, và tên lệnh có thể khác theo phiên bản; luôn dùng `nodetool help snapshot` trước khi thao tác thật.

### 5.3. Snapshot “toàn keyspace” không phải transaction toàn cluster

Ví dụ đơn hàng được ghi đồng thời vào hai bảng:

~~~text
10:00:00  orders_by_id       đã có order O123
10:00:01  snapshot node A
10:00:02  orders_by_customer đã được cập nhật
10:00:03  snapshot node B
~~~

Bộ file từ node A và node B có thể phản ánh các thời điểm hơi khác nhau. Cassandra không tự cung cấp **global snapshot isolation** cho tất cả bảng và tất cả replica chỉ vì operator dùng cùng snapshot tag.

Nếu nghiệp vụ cần trạng thái nhất quán giữa bảng:

- Dùng cửa sổ nghiệp vụ quiesce writes nếu có thể.
- Ghi lại một **restore point** có kiểm chứng ở upstream/event log.
- Thiết kế đối soát và reconciliation sau restore.
- Không tuyên bố “snapshot tag giống nhau” đồng nghĩa mọi bảng ở cùng timestamp.

## 6. Chuẩn bị backup đầy đủ và đáng tin cậy

### 6.1. Kiểm kê những hiện vật cần giữ

| Hiện vật | Vì sao cần |
|---|---|
| **SSTable components** (Data, Index, Summary, Statistics... theo bản) | Tạo thành dữ liệu có thể được đọc/stream lại |
| **Snapshot manifest** nếu có | Kiểm kê file thuộc bộ snapshot |
| **Schema CQL** | Tái dựng keyspace, table, column types, primary key, UDT, index |
| **Metadata của phiên bản** | Đánh giá tương thích SSTable format và tooling |
| **Topology/RF theo DC** | Hiểu token coverage và tính lại replica placement ở đích |
| **Timestamp, timezone và snapshot tag** | Xác định tính mới và phân biệt backup trước/sau sự cố |
| **Checksums và kích thước file** | Phát hiện copy thiếu hoặc file hỏng |
| **Encryption/key material** nếu backup mã hóa | Đọc được backup; bảo mật quyền giải mã |
| **Incremental files / log archive** nếu mục tiêu cần | Phục hồi phần dữ liệu sau snapshot theo khả năng thực tế |
| **Báo cáo backup job success/failure** | Tránh sử dụng bộ snapshot chỉ thành công trên một phần node |

Không giả định snapshot trên **một replica** đại diện toàn bộ bảng của cluster. Một node chỉ giữ các token ranges thuộc replica placement của nó. Muốn restore đầy đủ phải có coverage của **tất cả partition/token ranges**, có thể thu từ nhiều node/DC theo kế hoạch.

### 6.2. Xác minh kiểm kê file mà không đụng backup gốc

Ví dụ thao tác được thực hiện trên **bản staging**, không phải thư mục SSTable của node đang phục vụ:

~~~bash
# Minh họa cho máy staging Linux; đường dẫn phải do operator xác nhận.
find /restore-staging/commerce/orders_by_id -type f -print

# Tạo danh sách hash của dữ liệu staging để đối chiếu manifest nguồn.
# Kết quả cần được đối chiếu với checksum được lưu từ lúc backup.
find /restore-staging/commerce/orders_by_id -type f   -exec sha256sum {} \;
~~~

Không viết lại checksum **sau khi file đã bị hỏng** rồi coi nó là checksum gốc; checksum xác thực phải đến từ manifest/kho backup đáng tin. Khi dùng công cụ copy, phải kiểm tra lỗi, byte count và hash từng tệp. Nên giữ nguyên bản backup bất biến và thao tác trên **working copy**.

### 6.3. Ước lượng dung lượng cần thiết

Giả sử:

- Tổng SSTable thuộc phạm vi restore: **480 GiB**.
- Lượng dữ liệu và replication được phân phối lại ở cluster đích: tùy RF/placement.
- Headroom cho compaction, streaming và các thao tác nền: giả sử lập kế hoạch **thêm 40%** so với tổng bytes đang dự kiến lưu trong lab.

~~~text
Nếu dự kiến data files ở lab ≈ 480 GiB:

Headroom giả định = 480 × 40% = 192 GiB
Tổng ngân sách sơ bộ = 480 + 192 = 672 GiB

Đây là ví dụ tính ngân sách, KHÔNG phải công thức đảm bảo.
~~~

Nếu `sstableloader` stream dữ liệu từ nhiều replica nguồn, có thể có file trùng logical partition và lượng I/O lớn hơn dung lượng cuối cùng. Nếu lab thay RF, cần ước tính lại **dung lượng theo mỗi node**, không chỉ tổng logical bytes. Ngoài data cần chỗ cho commit log, system data, logs, snapshots tạm, compaction và file lỗi/retry.

## 7. Dựng cluster Cassandra cô lập

### 7.1. Không sao chép nguyên data directory của production

Một cách rất nguy hiểm là copy toàn bộ thư mục data/commitlog/system của production sang máy lab rồi đổi IP. Việc này có thể mang theo **host ID, token metadata, gossip state và các dữ liệu hệ thống** không phù hợp cho một cluster mới.

Nên dựng một cluster restore **trống**, khởi tạo danh tính mới, sau đó tạo schema và nạp **chỉ SSTable của user table cần phục hồi** bằng cơ chế được hỗ trợ.

Những điểm cần xác nhận:

- Cassandra version tương thích với nguồn SSTable; đừng mặc định bản mới/khác có thể đọc trực tiếp mọi định dạng cũ.
- `cluster_name`, `seeds`, `listen_address`, `rpc_address`, datacenter/rack/snitch hoàn toàn thuộc lab.
- Có đủ node cho RF mong muốn và đủ nguồn lực disk/network để phục hồi.
- TLS/authentication cùng KMS/key management phù hợp nhưng **không chia sẻ secrets ngoài nhu cầu tối thiểu**.
- Restore node không có đường gossip/stream vào production; firewall được kiểm tra bằng chính sách mạng, không chỉ bằng tên cluster.
- Ứng dụng chỉ đọc/sandbox, không chạy scheduled jobs/CDC consumer ngoài ý muốn.

### 7.2. Một hay nhiều node?

**Lab một node** có thể đủ để kiểm tra một số schema và row nếu phạm vi không đòi quorum/availability. Nhưng khi chỉ có một node, keyspace RF=3 tại DC đó có thể không đáp ứng `LOCAL_QUORUM` hoặc placement như production.

Để kiểm thử **đường đọc/ghi phân tán**, nên cân nhắc một cluster lab có đủ node và RF phù hợp. Trong một lab tối giản, bạn có thể đặt RF=1 **chỉ trong lab** để kiểm tra nội dung backup, đồng thời ghi rõ rằng điều đó **không kiểm chứng được** behavior của RF=3, repair hay outage.

**Không sao chép nguyên replication setting của production khi DC name hoặc số node khác.** Mục tiêu restore là logical data; replication placement phải được thiết kế cho topology cô lập.

## 8. Tái tạo schema trước khi nhập SSTable

### 8.1. Lưu schema dưới dạng CQL

Dùng bản DDL đã lưu trong backup hoặc schema export đáng tin:

~~~cql
-- Ví dụ cqlsh ở cluster NGUỒN khi được phép, chỉ để lấy schema.
DESCRIBE KEYSPACE commerce;
~~~

`DESCRIBE` là lệnh của **cqlsh**, không phải statement dùng trực tiếp qua driver để truy vấn dữ liệu. Trong quy trình phục hồi nên ưu tiên **DDL được lưu cùng backup**, tránh lấy schema hiện tại sau khi một thay đổi sai đã xảy ra.

### 8.2. Tái tạo keyspace và table ở lab

Giả sử lab có datacenter `restore_dc` gồm ba node và sẽ kiểm thử CL local quorum:

~~~cql
CREATE KEYSPACE commerce
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'restore_dc': 3
}
AND durable_writes = true;

CREATE TABLE commerce.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    placed_at timestamp,
    status text,
    total_amount decimal
);
~~~

Tên **`commerce` và `orders_by_id`** được giữ giống logical schema nguồn để giản lược việc import, nhưng **cluster vẫn phải độc lập** nhờ network/identity/host IDs. Tên DC `restore_dc` phải đúng với cấu hình snitch của lab.

Nếu chỉ có **một node** và không cần kiểm tra quorum, cấu hình RF=1 trong DC lab sẽ hợp lý hơn. Khi dùng snapshot của bảng gốc có **UDT**, phải tạo type trước table; với index và view phải xác minh thứ tự tái tạo theo công cụ/phiên bản.

### 8.3. Schema compatibility không chỉ là tên bảng

Để import SSTable thành công, cần kiểm tra:

- **Primary key và clustering columns**: kiểu dữ liệu, thứ tự, clustering order và partition key phải tương thích.
- **Column types, UDT, static columns**: không tùy ý đổi kiểu trước khi nạp.
- **Table options** như compression, compaction, TTL và gc grace: có thể ảnh hưởng cách đọc/hoạt động sau restore.
- **Schema ID**: cluster mới tạo table có table ID mới; cách import phải cho phép ánh xạ hợp lệ, không copy nhầm system metadata của bảng nguồn.
- **SSTable format/version**: phải được công cụ của cluster đích hỗ trợ.
- **Data encryption**: backup có thể yêu cầu khóa giải mã riêng.

Nếu có schema migration giữa ngày snapshot và thời điểm restore, không được mặc định tạo schema hiện tại rồi nạp SSTable cũ. Cần xác định **schema tại restore point**, kiểm chứng tương thích và có quy trình chuyển đổi nếu cần.

## 9. Chọn cơ chế đưa dữ liệu từ backup vào lab

Hai hướng phổ biến có đặc điểm rất khác nhau.

### 9.1. `sstableloader`: nạp dữ liệu qua streaming tới cluster đích

`sstableloader` là công cụ thường được dùng để **stream dữ liệu SSTable có sẵn vào cluster Cassandra đang chạy**, theo token placement và RF của đích. Với môi trường cô lập, đây thường là hướng thích hợp vì dữ liệu được phân phối qua các node của lab thay vì bắt operator tự đoán tệp nào thuộc token range nào.

Quy trình logic:

1. Dựng cluster lab và tạo schema đích tương thích.
2. Copy các SSTable components của snapshot sang staging **nằm ngoài data directories đang chạy**.
3. Đặt file theo **layout nguồn mà `sstableloader` của phiên bản đó chấp nhận**.
4. Trỏ `sstableloader` tới **đúng contact point lab**, với auth/TLS thích hợp.
5. Theo dõi stream progress, errors và dung lượng đĩa trên các node lab.
6. Kiểm chứng dữ liệu đã nạp và kết quả read CQL.

Ví dụ **minh họa** (thay IP và kiểm tra `sstableloader --help` của release):

~~~bash
# Trước tiên xác minh tool và cú pháp của đúng Cassandra release.
sstableloader --help

# THỰC HIỆN CHỈ KHI 10.50.0.11 là contact point của cluster CÔ LẬP.
# /restore-staging/commerce/orders_by_id phải được dựng theo layout
# phù hợp với sstableloader của phiên bản đang sử dụng.
sstableloader -d 10.50.0.11 /restore-staging/commerce/orders_by_id
~~~

**Rất quan trọng:** ví dụ đường dẫn không phải cam kết công cụ mọi version đều nhận được cấu trúc này. Một số release có yêu cầu về tên thư mục chứa table ID và/hoặc tùy chọn target keyspace/table. Hãy xác nhận bằng `sstableloader --help` và thử trên dữ liệu nhỏ trước.

Đây là **tool có thể ghi dữ liệu vào cluster đích**, không phải lệnh chỉ đọc. Phải kiểm tra IP/DNS, certificate, cluster identity và quyền trước khi chạy. **Không bao giờ trỏ `-d` tới seed/contact point production trong một buổi diễn tập restore.**

### 9.2. `nodetool refresh`: đưa SSTable đã copy vào node đích

Một hướng khác, khi cần import **cục bộ** trên node Cassandra đang chạy, là copy những SSTable phù hợp vào đúng **data directory của table đích** rồi yêu cầu node làm mới danh sách SSTable:

~~~bash
# Chỉ minh họa cú pháp; không chạy khi chưa copy và xác minh file an toàn.
nodetool refresh commerce orders_by_id
~~~

Đây **không phải giải pháp thay thế đơn giản cho `sstableloader` trong mọi cluster**:

- Tệp phải nằm đúng table ID/path, có permission và SSTable format tương thích.
- Nếu import trực tiếp tại một node, nó không tự đảm bảo **replication/token coverage toàn cluster** theo topology mới.
- Dữ liệu có thể đụng với SSTable hiện có nếu target không thực sự trống.
- Dữ liệu có version/tombstone cũ có thể bị các mutation mới hơn che hoặc dẫn tới kết quả khó hiểu.
- Nạp sai tệp có thể làm rối trạng thái table và yêu cầu can thiệp vận hành.

Vì vậy `refresh` nên được dùng cho **kịch bản khôi phục cục bộ đã được nhà vận hành xác nhận**, không coi là bước mặc định của mọi bài restore.

### 9.3. Khi nào chọn hướng nào?

| Tiêu chí | `sstableloader` | `nodetool refresh` |
|---|---|---|
| Đích là cluster mới có nhiều node | **Thường phù hợp hơn** nhờ streaming theo placement của đích | Cần tự giải bài toán tệp trên từng node/range |
| Có khác biệt token ownership/RF | Streaming dữ liệu theo replica placement lab | Không tự chuyển tệp tới mọi replica cần có |
| Nguồn là snapshot SSTable | Hỗ trợ theo layout/format/version phù hợp | Có thể dùng nếu file được copy đúng chỗ và tương thích |
| Tác động I/O | Stream qua network, ghi data trên node đích | File copy + refresh cục bộ, vẫn có I/O |
| Rủi ro chạy nhầm production | **Cao nếu chỉ định sai `-d`** | **Cao nếu đang đứng trên node production** |
| Cần thử trên môi trường cô lập | Có, bắt đầu từ bảng nhỏ và kiểm chứng | Có, chỉ theo runbook cụ thể |

**Không nhầm `nodetool rebuild`, `repair` và `refresh`**. Rebuild/repair thường khai thác replica hiện có để đồng bộ; chúng không tự động đọc một bộ snapshot bên ngoài và đưa dữ liệu logic cũ trở về.

## 10. Quy trình phục hồi một bảng bằng snapshot và sstableloader

Phần này trình bày **runbook thao tác**, với ví dụ một bảng `commerce.orders_by_id`. Địa chỉ IP, path và DDL đều là minh họa; luôn làm trên lab có quyền và xác nhận release.

### Bước 1 — Khóa phạm vi và lựa chọn restore point

Ghi nhận:

- Incident ID và lý do restore.
- Bảng/partition nào cần kiểm tra.
- Thời điểm snapshot **trước sự cố**, timezone UTC và kỳ vọng dữ liệu tại thời điểm đó.
- Định nghĩa RPO (dữ liệu có thể mất) và RTO (thời gian khôi phục).
- Bằng chứng snapshot hoàn chỉnh và read access đến nơi lưu.
- Số lượng node/đĩa của lab, RF/CL dự kiến.

Ví dụ sự cố DELETE nhầm lúc 10:00 UTC. Nếu snapshot gần nhất là 09:00 UTC, khôi phục từ snapshot chỉ giúp xem dữ liệu khoảng 09:00, **không tự động giữ được tất cả ghi từ 09:00 đến 10:00**. Muốn phục hồi gần 10:00 cần cơ chế incremental/log/upstream replay phù hợp.

### Bước 2 — Kiểm tra cluster cô lập và chặn đường nhầm production

Xác nhận:

~~~text
Environment: recovery-lab
Cluster name: cassandra-restore-lab
Datacenter: restore_dc
Contact point: 10.50.0.11 (ví dụ)
Production network: DENIED from recovery workload
Schema target: commerce.orders_by_id
Expected RF in restore_dc: 3
~~~

Không dùng shell history chứa credentials dạng plain text nếu có thể; chuẩn bị secret qua phương thức quản lý phù hợp.

### Bước 3 — Xác minh snapshot và stage SSTable

Xem bản manifest, hash, số byte và danh sách file ở từng nguồn. Copy sang staging cô lập, **giữ nguyên backup gốc**. Với snapshot ở nhiều node, phải xác định những partition ranges nào được đại diện và tránh sót dữ liệu nếu một node snapshot thất bại.

Khi có nhiều bản sao của cùng dữ liệu, việc stream lại từ từng bản có thể tăng chi phí hoặc tạo trùng lặp vật lý. Thiết kế danh sách input phải dựa trên coverage/correctness, không chỉ “copy mọi tệp vào một thư mục và hy vọng”.

### Bước 4 — Tạo schema tương thích trên đích

Dùng DDL đúng mốc snapshot hoặc schema đã kiểm thử tương thích. Kiểm tra table metadata qua `DESCRIBE KEYSPACE commerce` tại **lab**, xác nhận RF đủ theo số node lab và không có app production nào đang viết vào target.

### Bước 5 — Nạp dữ liệu

Chạy `sstableloader` từ staging trỏ vào lab, theo dõi output tiến độ và mã lỗi. Với keyspace nhiều bảng, chạy có kế hoạch từng table và theo dõi disk/network/compaction. Không cho quá nhiều task import đồng thời chỉ để giảm RTO trên giấy.

### Bước 6 — Kiểm tra sau import

- `nodetool status`: node lab đúng DC, trạng thái tốt.
- `nodetool netstats`: các stream liên quan không bị treo; theo dõi tiến độ theo peer.
- `nodetool compactionstats`: backlog và disk pressure sau import.
- `DESCRIBE TABLE` và một số `SELECT` theo partition key.
- Đối chiếu sample record, timestamps, row counts theo phương pháp có kiểm soát.
- Xác định TTL/tombstones có khiến dữ liệu nhìn khác so với ngày snapshot.

### Bước 7 — Báo cáo và quyết định sử dụng dữ liệu

Lập biên bản gồm bộ backup nào đã dùng, schema version, checksum, thời gian thực hiện, số lỗi, dữ liệu đối soát, các giới hạn và đề xuất bước tiếp theo. **Không tự động “đồng bộ ngược” dữ liệu từ lab sang production** sau khi thấy vài query đúng.

## 11. Quy trình phục hồi toàn keyspace

Khi cần cả keyspace, không chỉ lặp lại lệnh loader mà phải xét **phụ thuộc schema và tính đầy đủ xuyên bảng**.

### 11.1. Thứ tự phục hồi đề xuất

1. Lập danh sách bảng, UDT, functions/aggregates nếu có, indexes/materialized views, options và các phụ thuộc.
2. Chọn mốc backup/restore point phù hợp cho tất cả bảng; ghi giới hạn về thời điểm snapshot giữa các node.
3. Dựng cluster đích, cấu hình RF/DC phù hợp.
4. Tạo **UDT trước bảng sử dụng UDT**; tạo schema base table theo phiên bản phù hợp.
5. Lập kế hoạch khôi phục dữ liệu base tables và các cấu trúc phụ (index/view) theo runbook riêng.
6. Đối chiếu số partition/record quan trọng của từng bảng cùng tính nhất quán nghiệp vụ giữa các bảng.
7. Chạy validation của ứng dụng trên lab và xác nhận không có side effect.
8. Kết thúc bằng báo cáo RPO/RTO và sai lệch đã biết.

### 11.2. Không giả định schema system là portable

Các keyspace hệ thống của Cassandra chứa topology, danh tính node và trạng thái nội bộ. Không phải tất cả schema/user/role/system tables nên được copy nguyên trạng từ production sang cluster mới.

Các thành phần quản trị như authentication, authorization và schema history cần được thiết kế riêng cho lab. Những công cụ restore chuyên dụng có thể hỗ trợ điều phối; vẫn phải kiểm tra **hệ quả metadata** trước khi thực hiện.

### 11.3. Đối soát các bảng denormalized

Giả sử ứng dụng duy trì:

~~~text
commerce.orders_by_id
  order_id -> customer_id, status, total_amount

commerce.orders_by_customer
  (customer_id, order_id) -> status, total_amount
~~~

Nếu snapshot hai bảng không cùng mốc logic, đơn O123 có thể tồn tại ở bảng đầu nhưng chưa tồn tại hoặc có status khác ở bảng sau. Cassandra không bảo đảm transaction cross-table từ việc copy snapshot nhiều node.

**Tiêu chí phục hồi keyspace phải gồm invariant của nghiệp vụ**, không chỉ việc tất cả table SELECT được dữ liệu.

## 12. Point-in-time recovery: snapshot không tự đủ

### 12.1. Snapshot và incremental backup khác nhau

Một snapshot cho biết trạng thái SSTable ở mốc xác định. Incremental backup thường lưu những SSTable mới khi flush theo chính sách đã kích hoạt; kết hợp chúng có thể giúp lấy lại nhiều dữ liệu hơn, nhưng **không tự cung cấp chính xác trạng thái database tại bất kỳ mili giây nào**.

Vấn đề cần giải quyết:

- File incremental nào phát sinh trước/sau restore point?
- Những mutation chưa flush nằm trong commit log nào?
- Mutation DELETE/TTL và timestamp được giữ thế nào?
- Có thể replay đến một mốc cutoff được công cụ hỗ trợ không?
- Có thể bảo đảm phối hợp giữa các node và keyspace không?

Nếu không có quy trình PITR đã được diễn tập, nên mô tả rõ **“khôi phục từ snapshot tại khoảng thời gian X”**, không hứa **“khôi phục đúng 09:59:59”**.

### 12.2. Commit-log archiving chỉ có tác dụng khi được chuẩn bị trước

Một số bản Cassandra hỗ trợ cấu hình archiving/replay commit log theo phương thức của release. Để đạt điểm phục hồi cụ thể cần đã lưu được đủ segment, metadata, cấu hình restore và kiểm thử thứ tự replay/cutoff trên lab.

**Không tự copy commit log production vào data directory của cluster lab mới** rồi khởi động với kỳ vọng Cassandra sẽ tái hiện transaction đúng. Commit log gắn với format/metadata và tiến trình phục hồi cục bộ; cần quy trình rõ ràng theo phiên bản, đặc biệt với topology và schema khác.

### 12.3. TTL tiếp tục trôi theo thời gian thực

Ví dụ row được ghi vào 08:00 với `TTL 3600` (một giờ), snapshot lúc 08:30, sau đó restore lúc 12:00. Row có thể **đã hết hạn tại 09:00**, dù file snapshot được tạo trước khi hết TTL.

Vì vậy:

- Snapshot giữ dữ liệu/timestamp/TTL semantics, **không đóng băng đồng hồ TTL**.
- Read ở cluster lab sau khi TTL hết hạn có thể không trả row đó.
- Kiểm tra dữ liệu trước/sau TTL phải đánh giá timestamp và mục tiêu nghiệp vụ.
- Không “chữa” bằng cách đổi clock máy restore hoặc sửa timestamp SSTable tùy tiện.

### 12.4. Tombstone và dữ liệu bị xóa

DELETE/TTL tạo tombstone để các replica biết dữ liệu cũ không còn sống. Khi trộn dữ liệu snapshot với dữ liệu mới ở cùng table, timestamp/tombstone có thể che nhau. Với môi trường restore, **đích trống** giúp giảm một lớp phức tạp, nhưng các tombstone nằm trong snapshot vẫn cần giữ semantics.

Không chọn ngẫu nhiên một SSTable có Data.db chứa row mong muốn rồi bỏ qua tombstone ở các SSTable khác. Điều đó có thể hồi sinh dữ liệu đã bị xóa ở restore point hoặc tạo trạng thái không nhất quán.

## 13. Kiểm thử bằng CQL trên môi trường restore

### 13.1. Truy vấn theo partition key

Ví dụ bảng `commerce.orders_by_id`:

~~~cql
-- Chạy trên cqlsh kết nối tới CLUSTER CÔ LẬP.
CONSISTENCY LOCAL_QUORUM;

SELECT order_id, customer_id, placed_at, status, total_amount
FROM commerce.orders_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;
~~~

`LOCAL_QUORUM` chỉ phù hợp nếu RF của DC lab và số replica khỏe có thể đáp ứng. Nếu lab một node RF=1, lựa chọn kiểm thử có thể khác. Hãy luôn ghi CL khi đối soát để kết quả có ngữ cảnh.

### 13.2. Cách kiểm chứng dữ liệu

| Nhóm kiểm tra | Thí dụ | Vì sao hữu ích |
|---|---|---|
| **Key tồn tại** | SELECT theo 10–100 partition key đã biết | Phát hiện thiếu dữ liệu ở phạm vi nghiệp vụ |
| **Giá trị cột** | status, amount, timestamp, UDT/collection | Phát hiện schema/type mismatch |
| **Delete/TTL** | Record lẽ ra đã hết hạn hoặc đã bị xóa | Phát hiện restore không giữ đúng semantics |
| **Phạm vi dữ liệu** | Key ở nhiều token range và DC nguồn | Phát hiện backup thiếu một phần node/range |
| **Tính nhất quán xuyên bảng** | Order tồn tại ở hai bảng denormalized theo invariant | Phát hiện snapshot lệch thời điểm |
| **Ứng dụng** | API/DAO read-only trên lab | Xác minh query thật có chạy và trả đúng dữ liệu |
| **Metadata** | Version/schema, RF, table options, index | Giải thích khác biệt giữa lab và source |

Không dùng `SELECT COUNT(*)` trên bảng rất lớn làm phép thử chính: đếm toàn bảng có thể gây scan tốn tài nguyên và timeout. Nếu cần số lượng, cân nhắc manifest, thống kê bên ngoài, mẫu phân tầng hoặc job đối soát có kiểm soát theo token ranges.

### 13.3. Không chỉ so sánh số row

Hai bản khôi phục có thể có cùng row count nhưng khác amount/status/timestamp, thiếu một số partition và dư một số khác. Nên đối soát **record identity, nội dung và invariant** bằng bộ dữ liệu kiểm thử đại diện.

Khi so checksum:

- File hash xác minh **file backup và bản copy staging** không bị đổi.
- Logical row checksum xác minh **nội dung dữ liệu** sau import, cần chuẩn hóa thứ tự/cách encode.
- Không kỳ vọng SSTable file hash phía lab giống nguồn sau `sstableloader`: import/compaction có thể viết lại file khác về mặt bytes.

## 14. Java Driver 4.x: kiểm chứng restore mà không chạm production

Một ứng dụng Java dành cho phục hồi cần **CqlSession riêng**, contact point và local DC riêng. Ví dụ:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.util.UUID;

// Ví dụ: IP chỉ dành cho cluster restore, KHÔNG phải production.
try (CqlSession lab = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("10.50.0.11", 9042))
        .withLocalDatacenter("restore_dc")
        .build()) {

    PreparedStatement find = lab.prepare(
        "SELECT status, total_amount " +
        "FROM commerce.orders_by_id WHERE order_id = ?"
    );

    UUID orderId =
        UUID.fromString("11111111-1111-1111-1111-111111111111");

    BoundStatement query = find.bind(orderId)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

    Row result = lab.execute(query).one();
    if (result == null) {
        throw new IllegalStateException(
            "Expected restored order was not found");
    }

    String status = result.getString("status");
    BigDecimal amount = result.getBigDecimal("total_amount");

    System.out.println("Restored order: " + status + ", " + amount);
}
~~~

Ví dụ chỉ kiểm chứng **đọc** một partition có key đã biết. Ở production thực tế cần cấu hình auth/TLS, timeouts và driver metrics riêng cho lab. Nếu phải xem dữ liệu nhạy cảm, **không in PII ra stdout hoặc log** như minh họa giá trị nghiệp vụ; dùng so sánh/đếm/tổng hợp và log đã làm sạch.

Các thực hành bảo vệ:

1. Cấu hình client riêng cho lab, **không dùng biến môi trường/secret/contact points mặc định của production**.
2. Account của bài kiểm thử chỉ có **quyền SELECT** khi có thể.
3. Đặt guardrail trong CI/CD để từ chối chạy nếu endpoint không thuộc danh sách lab được phép.
4. Không gửi telemetry/CDC/webhook sang hệ thống production hoặc dịch vụ thanh toán/email thật.
5. Dùng prepared statement và WHERE theo partition key để tránh full scan do test.
6. Đo read p95/p99 và timeout để biết cluster phục hồi đáp ứng được workload kỳ vọng hay chỉ đọc được một vài row.

## 15. Giám sát trong lúc import và sau restore

### 15.1. Lệnh đọc trạng thái

~~~bash
# Xem node, DC/rack, trạng thái và phân bố dữ liệu.
nodetool status

# Stream đang gửi/nhận khi chạy sstableloader và các thao tác khác.
nodetool netstats

# Compaction backlog, disk pressure sau khi nạp dữ liệu.
nodetool compactionstats

# Hàng đợi xử lý nội bộ, dropped messages.
nodetool tpstats

# Thông tin keyspace/table và SSTable theo bản.
nodetool tablestats commerce.orders_by_id
~~~

Tên trường và cách hiển thị khác theo phiên bản. Việc `netstats` không còn phiên stream là một tín hiệu tốt nhưng **chưa đủ** để chứng minh dữ liệu khôi phục hoàn chỉnh; phải kết hợp với exit status của loader, logs, kiểm kê file và kiểm thử CQL.

### 15.2. Dashboard tối thiểu cho restore

| Nhóm | Cần quan sát |
|---|---|
| **Tiến độ** | Bytes/file đã copy, streaming complete/fail, số table đã nhập |
| **Disk** | Free space, write latency, IOPS, throughput, compaction overhead |
| **Network** | Throughput, retransmission, error, timeout |
| **Cassandra** | Node UP/normal, pending compaction, read/write latency, dropped messages |
| **Chất lượng dữ liệu** | Kiểm tra key, logical checksum, TTL/tombstone, invariant |
| **RTO** | Thời gian từ lúc được phép bắt đầu đến khi đọc/kiểm chứng thành công |
| **RPO** | Mốc dữ liệu thực tế được khôi phục so với mốc nghiệp vụ chấp nhận |
| **Bảo mật** | Access logs, quyền đọc, đường truyền và retention của lab |

Các bước copy/restore nên có mốc UTC: bắt đầu, xác minh schema, loader start/finish, validation finish và cleanup. Việc ghi timestamp giúp tính RTO gần thực tế hơn một lời dự đoán thuần từ dung lượng backup.

## 16. Runbook xử lý sự cố trong quá trình phục hồi

### 16.1. Loader báo schema mismatch

**Dấu hiệu:** `sstableloader` không thể nạp file dù table có cùng tên.

Cần kiểm tra:

- Schema đang dùng là schema **tại mốc snapshot** hay schema hiện tại đã thay đổi?
- Primary key/clustering type có khớp không?
- UDT, static column, drop/recreate column có ảnh hưởng?
- Cassandra version/SSTable format có được hỗ trợ không?
- Thư mục staging có đúng layout mà loader đọc không?

Không sửa bừa cột đích hoặc copy SSTable thủ công vào bảng production. Làm việc trên lab, giữ backup gốc và thử lại với schema tương thích đã được kiểm chứng.

### 16.2. Loader chỉ có tiến độ một phần rồi dừng

Kiểm tra **network từ staging đến node lab**, TLS/auth, disk free, streaming sessions, lỗi I/O và compaction. Nếu file nguồn chỉ lấy từ một node production, khả năng thiếu token coverage là vấn đề khác với stream timeout.

Không mặc định restart loader vô hạn khi dữ liệu có thể đã nhập một phần. Cần xác định behavior idempotency/duplicate khi nạp lại theo công cụ, data timestamps và trạng thái target. Với tập dữ liệu quan trọng, có thể an toàn hơn dựng **target lab trống mới** để lặp lại một lần có kiểm soát.

### 16.3. SELECT không thấy row mong đợi

Các khả năng:

1. Backup không chứa partition hoặc nguồn token range chưa được lấy đủ.
2. File snapshot có trước khi row được ghi.
3. TTL đã hết hạn vào ngày khôi phục.
4. Row bị tombstone che theo timestamp.
5. Schema hoặc đường import không đúng.
6. Query dùng sai key/CL hoặc replica chưa khỏe.
7. Backup/incremental segments có thiếu file.

Đừng kết luận “loader thành công tức restore đúng” nếu chưa kiểm thử dữ liệu theo các trường hợp trên.

### 16.4. Lab gần đầy đĩa sau khi nạp

Stream, flush và compaction có thể giữ nhiều SSTable cũ/mới cùng lúc; thêm nữa snapshot, log và staging có thể dùng cùng volume. Kiểm tra `df`, `du` và đường storage đã định nghĩa; giảm/tạm dừng import theo quy trình an toàn nếu cần.

**Không xóa SSTable đang được Cassandra quản lý để lấy lại space** và không xóa backup gốc trước khi bảo đảm bản sao độc lập còn sử dụng được.

### 16.5. Restore thành công nhưng nghiệp vụ vẫn không nhất quán

Ví dụ `orders_by_id` có trạng thái `SHIPPED` trong khi bảng `orders_by_customer` ghi `CONFIRMED`. Đó có thể là dấu hiệu snapshot giữa các bảng không cùng mốc, hoặc nghiệp vụ gốc đã không đồng bộ trước backup.

Phải kiểm tra restore point, log sự kiện nghiệp vụ và quy tắc cập nhật hai bảng, rồi lập một **kế hoạch reconciliation**. Không tự áp dụng luật “bảng nào mới hơn là đúng” khi chưa hiểu timestamp, event order và side effects.

## 17. Những lỗi vận hành đặc biệt nguy hiểm

| Ngộ nhận hoặc hành động | Rủi ro | Nguyên tắc thay thế |
|---|---|---|
| Trỏ `sstableloader -d` đến IP production | Nạp dữ liệu backup cũ vào cụm thật | Network allowlist chỉ dành cho lab và xác nhận identity |
| Copy cả system keyspace/host ID từ production | Trộn danh tính/token metadata | Tạo cluster trống với identity mới |
| Dùng snapshot từ một node để khôi phục toàn keyspace | Thiếu token ranges và nhiều partition | Kiểm tra coverage của tất cả nguồn cần thiết |
| Tạo schema hiện tại rồi nạp SSTable quá cũ | Mismatch hoặc khác semantics | Tái dựng schema tại restore point và đánh giá chuyển đổi |
| Xem snapshot là PITR đến mili giây tùy ý | RPO không đạt | Cần incremental/commit-log/upstream log được diễn tập |
| Bỏ qua TTL và tombstone | Hiểu sai số row hoặc khôi phục dữ liệu đã xóa | Kiểm chứng timestamp/TTL/delete semantics |
| Chạy `COUNT(*)` trên bảng cực lớn để “kiểm thử nhanh” | Full scan, tải cluster và timeout | Sampling, checksums và job đối soát có kiểm soát |
| Xóa SSTable cũ bằng tay khi disk đầy | Mất dữ liệu hoặc hỏng trạng thái table | Capacity/runbook và giám sát |
| So file hash của SSTable sau loader với snapshot gốc | So sánh sai lớp vì file có thể được viết lại | Hash nguồn–staging; logical checksum sau import |
| Cho app restore dùng credentials/endpoint production | Rò rỉ dữ liệu hoặc ghi nhầm | Tách secret, cấu hình và quyền truy cập |
| Kết luận khôi phục thành công sau một SELECT | Bỏ sót partitions, bảng và invariant | Validation theo phạm vi và tiêu chí nghiệp vụ |
| Dùng `repair` để quay ngược DELETE | Repair đồng bộ trạng thái hiện tại, không replay lịch sử | Khôi phục từ backup độc lập và đối soát |
| Cho lab chạy CDC/job gửi ra bên ngoài | Side effect lên downstream | Sandbox hoặc tắt integration |

## 18. Đo RPO, RTO và tiêu chí “restore thành công”

### 18.1. RPO phải là cam kết đã được kiểm chứng

Giả sử dữ liệu bị xóa lúc **10:00 UTC** và bộ snapshot gần nhất hợp lệ lúc **08:30 UTC**. Nếu không có incremental/commit-log/upstream replay thích hợp, mốc dữ liệu phục hồi chỉ được kỳ vọng quanh thời điểm snapshot (và còn giới hạn về snapshot phân tán).

~~~text
Incident time:             10:00 UTC
Snapshot restore point:    08:30 UTC
Khoảng cách danh nghĩa:     90 phút

Không được tuyên bố RPO <= 5 phút chỉ vì
tốc độ sstableloader nhanh hoặc cluster lab UP.
~~~

**RPO** là mức mất dữ liệu nghiệp vụ chấp nhận được khi xảy ra failure scenario; nó không chỉ là độ tuổi file snapshot. Cần xét mutation chưa flush, backup lệch mốc, TTL và sự tồn tại của backup tăng dần.

### 18.2. RTO phải gồm cả kiểm chứng

Ví dụ phân rã thời gian:

| Bước | Thời gian giả định |
|---|---:|
| Cấp hạ tầng và kiểm tra isolation | 25 phút |
| Lấy/copy backup và kiểm checksum | 50 phút |
| Tạo schema, xác minh compatibility | 20 phút |
| Stream SSTable vào lab | 95 phút |
| Đối soát dữ liệu và ứng dụng | 35 phút |
| **Tổng thời gian diễn tập** | **225 phút (3 giờ 45 phút)** |

Đây là con số minh họa, không phải SLA của Cassandra. Phải xác định thời điểm bắt đầu RTO theo quy ước tổ chức, và khi nào môi trường được xem **sẵn sàng sử dụng**. Chỉ báo loader “100%” chưa có nghĩa nghiệp vụ đã phục hồi.

### 18.3. Các mức chứng minh khôi phục

- **Level 1 – File validated:** backup tồn tại, checksum đúng.
- **Level 2 – Schema loaded:** keyspace/table/UDT đúng và cluster lab sẵn sàng.
- **Level 3 – Data loaded:** loader/refresh hoàn thành không lỗi trọng yếu.
- **Level 4 – Logical validation passed:** dữ liệu mẫu, key coverage, TTL/delete semantics và invariant đúng.
- **Level 5 – Application rehearsal passed:** ứng dụng kết nối lab, query/DAO quan trọng chạy, RPO/RTO và an toàn integration được xác nhận.

**Một backup đáng tin là backup đã được restore và kiểm chứng định kỳ**, không chỉ là một job báo “SUCCESS”.

## 19. Bài tập và tình huống có đáp án

### Câu 1 — Vì sao không restore thẳng vào production?

Một operator muốn nhập snapshot cũ vào bảng hiện đang có mutation mới. Điều gì có thể xảy ra?

**Đáp án:** Dữ liệu mới và cũ có thể va chạm theo timestamp/tombstone; dữ liệu được nạp có thể che hoặc bị che bởi mutation khác, tạo trạng thái không thể dự đoán đơn giản. Thao tác có nguy cơ ảnh hưởng hệ thống thật. Trước hết phải restore vào lab và lập kế hoạch dữ liệu rõ ràng.

### Câu 2 — Snapshot từ một node có đủ không?

Keyspace có RF=3 trên sáu node. Bạn chỉ lưu snapshot của node A và muốn khôi phục toàn keyspace. Có bảo đảm đầy đủ không?

**Đáp án:** Không. Node A chỉ giữ những token ranges thuộc nó. Cần kiểm tra nguồn đủ coverage của toàn bộ partition và mọi bảng liên quan.

### Câu 3 — Lab chỉ có một node nhưng RF=3

Bạn tạo keyspace `NetworkTopologyStrategy` với `restore_dc:3`, rồi đọc ở `LOCAL_QUORUM`. Có rủi ro gì?

**Đáp án:** Lab không có đủ replica/node cho RF đó. Quorum có thể không được đáp ứng. Cần tăng số node lab hoặc dùng RF phù hợp với mục tiêu test, và ghi rõ giới hạn khi so với production.

### Câu 4 — Snapshot và TTL

Row được ghi 08:00 với TTL 3600 giây, snapshot 08:30 và restore lúc 12:00. Row có bắt buộc còn visible không?

**Đáp án:** Không. TTL thường hết hạn theo thời gian ghi ban đầu; snapshot không đóng băng TTL. Row có thể đã hết hạn trước lúc restore.

### Câu 5 — Đã copy file đúng checksum nhưng SELECT không thấy dữ liệu

Hãy nêu ba nguyên nhân cần kiểm tra.

**Đáp án:** Sai/mất token coverage, schema không tương thích, TTL expired, tombstone che row, snapshot trước lúc ghi, import chưa hoàn tất, query key/CL sai. Checksum file chỉ xác nhận bản copy không bị thay đổi, chưa xác nhận logical data đầy đủ.

### Câu 6 — sstableloader và refresh

Khi cần nạp snapshot vào cluster lab có token placement khác nguồn, công cụ nào thường phù hợp hơn?

**Đáp án:** `sstableloader` vì stream dữ liệu theo replica placement của cluster đích. `nodetool refresh` là import cục bộ, không tự giải quyết mọi yêu cầu phân bố dữ liệu qua nhiều node.

### Câu 7 — Keyspace nhiều bảng bị lệch mốc

`orders_by_id` và `orders_by_customer` khác status dù cả hai được lấy từ snapshot cùng tag. Có chắc backup bị hỏng không?

**Đáp án:** Không. Snapshot tại node/bảng khác nhau không đảm bảo một giao dịch global nhất quán. Cần đối chiếu timing, luồng ghi và invariant nghiệp vụ.

### Câu 8 — Point-in-time recovery

Snapshot lúc 08:00, incident lúc 10:00. Muốn khôi phục chính xác đến 09:59 thì chỉ cần đổi tên snapshot tag thành 09:59?

**Đáp án:** Không. Tên tag không thay dữ liệu. Cần chuỗi backup/incremental/commit-log archiving hoặc upstream event replay phù hợp, đã kiểm chứng theo release và yêu cầu consistency.

### Câu 9 — Chỉ thấy 1 order đúng

Một lần SELECT thấy đúng O123; có thể tuyên bố cả keyspace khôi phục đủ không?

**Đáp án:** Không. Cần kiểm tra nhiều partition/token ranges, nhiều bảng, sample và logical checksum, TTL/tombstone và các bất biến nghiệp vụ.

### Câu 10 — Restore hết 95 phút nhưng kiểm chứng thêm 35 phút

Theo ví dụ RTO ở phần 18, nếu tính cả cấp hạ tầng/copy/schema và validation thì RTO rehearsal là 95 phút hay 225 phút?

**Đáp án:** 225 phút (3 giờ 45 phút) theo định nghĩa diễn tập minh họa. Thời gian streaming riêng không phải toàn bộ recovery time.

### Câu 11 — Làm sao bảo đảm không có side effect?

Restore cluster mới dùng đúng account và seed của production, rồi service tự khởi động các scheduled jobs gửi email. Có an toàn vì dữ liệu ở máy khác không?

**Đáp án:** Không. Phải cô lập network, seeds, cluster identity, credentials, contact points và integrations. Job/webhook/CDC cần bị tắt hoặc sandbox để không thực hiện hành động thật.

### Câu 12 — File hash khác sau import

Checksum của SSTable trên lab không giống snapshot gốc, nhưng sample data khớp. Có đủ căn cứ nói backup bị corruption?

**Đáp án:** Không. Loader/compaction có thể viết lại SSTable về mặt bytes. File checksum nên dùng so sánh **nguồn và staging**, còn dữ liệu sau import cần kiểm bằng logical checks/invariant.

## 20. Checklist hoàn tất và báo cáo cho nhóm vận hành

~~~text
RESTORE REHEARSAL SUMMARY
-------------------------
Incident / rehearsal ID:
Source backup/snapshot tag:
Source cluster version:
Target isolated cluster_name / DC:
Scope (tables/keyspace):
Schema version / migration notes:
RF / consistency used for validation:
Backup file count and checksum verification:
SSTableloader/refresh method and tool version:
Loaded tables / token coverage:
Streaming, compaction and disk health:
Sample keys checked / logical checksums:
TTL and delete/tombstone validation:
Cross-table application invariants:
Data gaps and known limitations:
Start/end UTC:
RPO achieved / not achieved / unknown:
RTO measured:
Production isolation verification:
Side effects disabled:
Rollback/cleanup plan for lab:
Reviewers / approval:
~~~

Khi điền báo cáo, phân biệt rõ **PASS**, **FAIL** và **UNKNOWN**. Nếu không kiểm chứng được tính đầy đủ của snapshot nguồn, không ghi `PASS` chỉ vì số lượng row mẫu đúng. Nếu chưa có dữ liệu để chứng minh RPO, ghi **UNKNOWN** và đề xuất bổ sung backup/restore drills.

## 21. Tổng kết

Đối với Apache Cassandra, **khôi phục bảng hoặc keyspace vào môi trường cô lập** là một quy trình nhiều bước, không phải chỉ chép file hay chạy một lệnh `nodetool`:

1. **Định nghĩa scope và restore point** trước khi chạm vào backup; biết rõ muốn một bảng hay toàn keyspace.
2. **Tách cluster lab khỏi production** ở network, seeds, host IDs, disk, credentials và external integrations.
3. **Xác minh backup coverage** của toàn bộ token ranges, tables, metadata, checksums và tương thích phiên bản.
4. **Tạo schema phù hợp với snapshot** và RF theo topology của lab; một lab một node không tự kiểm chứng quorum của production.
5. **Ưu tiên cơ chế import có tính đến placement**, như `sstableloader` khi phù hợp, thay vì tự copy SSTable bừa vào các node.
6. **Hiểu giới hạn thời điểm**: snapshot không tạo global transaction snapshot; TTL tiếp tục chạy; PITR cần cơ chế bổ sung đã được kiểm thử.
7. **Đối soát cả dữ liệu và nghiệp vụ**: key coverage, giá trị, delete/tombstone, các bảng denormalized và query Java thực tế.
8. **Đo RPO/RTO theo toàn quy trình**, gồm cấp hạ tầng, copy, import và validation.
9. **Không nhập ngược vào production tự động**. Mọi bước tiếp theo sau rehearsal cần kế hoạch thay đổi, owner và rollback riêng.

Một cuộc diễn tập phục hồi thành công là khi đội vận hành có thể trả lời bằng bằng chứng: **“Tôi biết backup nào đã được dùng, dữ liệu nào phục hồi được, những giới hạn còn tồn tại, thời gian cần thiết, và chắc chắn thao tác thử nghiệm không làm thay đổi cluster production.”**
